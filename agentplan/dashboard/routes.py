#!/usr/bin/env python3
"""Read-only web dashboard for agentplan projects and tickets."""

import html
import json
import logging
import os
import subprocess
import threading
import time
from collections import defaultdict
from datetime import datetime
from functools import wraps
from urllib.parse import urlparse

from flask import Flask, abort, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from agentplan.cli import slugify
from agentplan.db import (
    check_auto_complete,
    create_agent,
    delete_agent,
    get_chain_state,
    get_connection,
    get_db_path,
    get_space_directory,
    has_cycle,
    list_agents,
    list_roles,
    next_subtask_num,
    resolve_project,
    resolve_subtask,
    resolve_ticket,
    set_chain_state,
    unique_slug,
    update_agent,
    validate_transition,
)

from .sse import sse_response
from .constants import (
    KANBAN_STATUS_LABELS,
    KANBAN_STATUS_ORDER,
    TAG_TONES,
)

LOGGER = logging.getLogger(__name__)

HOME_STATUS_LABELS = {
    "active": "Active",
    "completed": "Completed",
    "abandoned": "Closed",
    "archived": "Archived",
}

HOME_SECTION_ORDER = [
    ("active", "Active Projects"),
    ("completed", "Completed Projects"),
    ("abandoned", "Closed Projects"),
    ("archived", "Archived Projects"),
]


def _db_path():
    from agentplan.db import get_db_path
    _, db_path = get_db_path()
    return db_path


def _is_loopback_host(host):
    host = (host or "").strip().lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def _effective_port(parsed):
    if parsed.port is not None:
        return parsed.port
    if parsed.scheme == "https":
        return 443
    if parsed.scheme == "http":
        return 80
    return None


def _origin_matches_request_host(value):
    if not value:
        return False
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    origin_host = (parsed.hostname or "").lower()
    if _is_loopback_host(origin_host):
        return True
    request_host = (request.host.split(":", 1)[0] if request.host else "").lower()
    if not request_host or origin_host != request_host:
        return False
    request_scheme = (request.scheme or "").lower()
    origin_scheme = (parsed.scheme or "").lower()
    if not request_scheme or origin_scheme != request_scheme:
        return False
    request_port = _effective_port(urlparse(f"{request_scheme}://{request.host}"))
    origin_port = _effective_port(parsed)
    return request_port is not None and origin_port == request_port


def _require_local_origin(fn):
    @wraps(fn)
    def _wrapped(*args, **kwargs):
        origin = request.headers.get("Origin")
        referer = request.headers.get("Referer")
        if origin:
            if not _origin_matches_request_host(origin):
                return ({"error": "forbidden"}, 403)
        elif referer:
            if not _origin_matches_request_host(referer):
                return ({"error": "forbidden"}, 403)
        return fn(*args, **kwargs)

    return _wrapped


def _detect_tools_status():
    tools = ["claude", "codex", "aider", "cursor", "openclaw"]
    detected = []
    for tool in tools:
        found = False
        try:
            result = subprocess.run(["which", tool], capture_output=True, text=True)
            found = result.returncode == 0
        except Exception:
            found = False
        detected.append({"name": tool, "found": found})
    return detected


def _parse_roles_from_form(form):
    return [value.strip() for value in form.getlist("roles") if value.strip()]


def _titleize_status(status):
    words = [part for part in str(status or "").replace("_", "-").split("-") if part]
    if not words:
        return "Unknown"
    return " ".join(word.capitalize() for word in words)


def _home_status_label(status):
    normalized = (status or "").strip().lower()
    return HOME_STATUS_LABELS.get(normalized, _titleize_status(normalized))


def _group_projects_for_home(projects):
    """Group projects by status (original view)."""
    grouped = defaultdict(list)
    for project in projects:
        grouped[(project.get("status") or "unknown").strip().lower()].append(project)

    sections = []
    for key, title in HOME_SECTION_ORDER:
        items = grouped.pop(key, [])
        sections.append({"key": key, "title": title, "projects": items})

    for key in sorted(grouped):
        items = grouped[key]
        if items:
            sections.append(
                {
                    "key": key,
                    "title": f"{_home_status_label(key)} Projects",
                    "projects": items,
                }
            )

    return sections


def _group_projects_by_space(conn, projects):
    """Group projects by space."""
    # Fetch all spaces
    spaces_data = conn.execute(
        "SELECT id, slug, title FROM spaces ORDER BY slug"
    ).fetchall()
    
    # Create a mapping of space_id -> space info
    spaces_by_id = {}
    spaces_list = []
    for s in spaces_data:
        s_dict = dict(s)
        space_info = {
            "id": s_dict["id"],
            "slug": s_dict["slug"],
            "title": s_dict["title"],
            "doc_count": _count_space_docs(s_dict["slug"]),
            "projects": [],
        }
        spaces_by_id[s_dict["id"]] = space_info
        spaces_list.append(space_info)
    
    # Group projects by space_id
    for project in projects:
        space_id = project.get("space_id")
        if space_id in spaces_by_id:
            spaces_by_id[space_id]["projects"].append(project)
    
    # Move default space to the end
    default_space = None
    other_spaces = []
    for space in spaces_list:
        if space["slug"] == "default":
            default_space = space
        else:
            other_spaces.append(space)
    
    if default_space:
        spaces_list = other_spaces + [default_space]
    
    return spaces_list


def _safe_space_dir(space_slug):
    """Return the realpath for a space dir, or None if it escapes the data directory."""
    safe_slug = secure_filename(space_slug)
    if not safe_slug:
        return None
    data_dir, _ = get_db_path()
    return os.path.join(os.path.realpath(os.path.join(data_dir, "spaces")), safe_slug)


def _safe_doc_path(space_slug, filename):
    """Return (space_dir, fpath) for a doc, or (None, None) if path escapes containment."""
    space_dir = _safe_space_dir(space_slug)
    if space_dir is None:
        return None, None
    safe_name = secure_filename(filename)
    if not safe_name:
        return None, None
    return space_dir, os.path.join(space_dir, safe_name)


def _count_space_docs(space_slug):
    """Count markdown files in space directory."""
    space_dir = _safe_space_dir(space_slug)
    if space_dir is None or not os.path.isdir(space_dir):
        return 0
    try:
        return sum(1 for f in os.listdir(space_dir) if f.endswith(".md"))
    except (OSError, IOError):
        return 0


def _list_space_docs(space_slug):
    """List markdown files in a space directory with metadata."""
    space_dir = _safe_space_dir(space_slug)
    if space_dir is None:
        return []
    docs = []
    if not os.path.isdir(space_dir):
        return docs
    try:
        for fname in sorted(os.listdir(space_dir)):
            if not fname.endswith(".md"):
                continue
            safe_fname = secure_filename(fname)
            if not safe_fname:
                continue
            fpath = os.path.join(space_dir, safe_fname)
            try:
                stat = os.stat(fpath)
                docs.append({
                    "filename": fname,
                    "size": stat.st_size,
                    "size_display": _human_size(stat.st_size),
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%b %-d"),
                    "modified_iso": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
            except OSError:
                continue
    except (OSError, IOError):
        pass
    return docs


def _human_size(nbytes):
    """Format bytes as human-readable size."""
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}" if unit != "B" else f"{nbytes} B"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"


def _fetch_projects_with_stats(conn):
    projects = conn.execute(
        "SELECT id, slug, title, status, updated_at, dir, space_id FROM projects ORDER BY updated_at DESC, id DESC LIMIT 100"
    ).fetchall()
    
    # Fetch space information
    spaces_data = conn.execute(
        "SELECT id, slug, title FROM spaces ORDER BY slug"
    ).fetchall()
    spaces_by_id = {}
    space_doc_counts = {}
    for s in spaces_data:
        s_dict = dict(s)
        spaces_by_id[s_dict["id"]] = {"slug": s_dict["slug"], "title": s_dict["title"]}
        space_doc_counts[s_dict["slug"]] = _count_space_docs(s_dict["slug"])
    
    rows = conn.execute("SELECT project_id, status, COUNT(*) AS c FROM tickets GROUP BY project_id, status").fetchall()

    counts = defaultdict(lambda: defaultdict(int))
    for row in rows:
        counts[row["project_id"]][row["status"]] = row["c"]

    out = []
    for p in projects:
        p_dict = dict(p)
        project_counts = counts[p_dict["id"]]
        breakdown = {
            "pending": int(project_counts.get("pending", 0)),
            "in-progress": int(project_counts.get("in-progress", 0)),
            "blocked": int(project_counts.get("blocked", 0)),
            "done": int(project_counts.get("done", 0)),
            "skipped": int(project_counts.get("skipped", 0)),
            "failed": int(project_counts.get("failed", 0)),
            "needs-review": int(project_counts.get("needs-review", 0)),
        }
        total = sum(breakdown.values())
        done = breakdown["done"] + breakdown["skipped"]
        in_flight = (
            breakdown["pending"]
            + breakdown["in-progress"]
            + breakdown["blocked"]
            + breakdown["failed"]
            + breakdown["needs-review"]
        )
        progress = int(round((done / total) * 100)) if total else 0
        
        # Get space info — preserve NULL as unassigned
        space_id = p_dict.get("space_id")
        space_info = spaces_by_id.get(space_id) if space_id else None
        space_slug = space_info["slug"] if space_info else None
        space_title = space_info["title"] if space_info else "Unassigned"
        
        out.append(
            {
                "id": p_dict["id"],
                "slug": p_dict["slug"],
                "title": p_dict["title"],
                "status": p_dict["status"],
                "updated_at": p_dict["updated_at"],
                "space_id": space_id,
                "space_slug": space_slug,
                "space_title": space_title,
                "space_doc_count": space_doc_counts.get(space_slug, 0),
                "breakdown": breakdown,
                "ticket_count": total,
                "done_count": done,
                "in_flight_count": in_flight,
                "progress_pct": progress,
                "missing_directory": bool(p_dict["dir"] and not os.path.isdir(p_dict["dir"])),
                "status_label": _home_status_label(p_dict["status"]),
            }
        )
    return out


def _ticket_matches(ticket, priority_filter, tag_filter):
    if priority_filter:
        ticket_priority = str(ticket.get("priority") or "").strip().lower()
        if ticket_priority != priority_filter:
            return False
    if tag_filter:
        tags = {t.strip().lower() for t in (ticket["tags"] or "").split(",") if t.strip()}
        if tag_filter not in tags:
            return False
    return True


def _normalize_ticket(row):
    tags = [t.strip() for t in (row["tags"] or "").split(",") if t.strip()]
    try:
        dependencies = json.loads(row["depends_on"] or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        dependencies = []

    assignee = (row["started_by"] or row["done_by"] or "").strip()
    initials = "".join(part[0] for part in assignee.split()[:2]).upper() if assignee else ""
    if assignee and not initials:
        initials = assignee[:2].upper()

    due_date = (row["due_date"] or "").strip()
    is_overdue = False
    if due_date:
        try:
            due_dt = datetime.strptime(due_date, "%Y-%m-%d").date()
            is_overdue = due_dt < datetime.now().date() and row["status"] not in ("done", "skipped")
        except ValueError:
            is_overdue = False

    tag_tones = {tag: TAG_TONES[sum(ord(ch) for ch in tag) % len(TAG_TONES)] for tag in tags}

    model_tier = row["model_tier"] if "model_tier" in row.keys() else "auto"

    return {
        "id": row["id"],
        "num": row["num"],
        "title": row["title"],
        "description": row["description"] or "",
        "status": row["status"],
        "priority": str(row["priority"]).strip() if row["priority"] is not None else "",
        "tags": tags,
        "tag_tones": tag_tones,
        "dependencies": dependencies,
        "assignee": assignee,
        "assignee_initials": initials,
        "due_date": due_date,
        "is_overdue": is_overdue,
        "model_tier": model_tier,
    }


def _project_stats_payload():
    conn = get_connection(_db_path())
    try:
        projects = _fetch_projects_with_stats(conn)

        all_spaces = [
            dict(row)
            for row in conn.execute(
                "SELECT id, slug, title FROM spaces ORDER BY slug"
            ).fetchall()
        ]

        completed_today = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM tickets
            WHERE status IN ('done', 'skipped')
              AND completed_at IS NOT NULL
              AND date(completed_at) = date('now', 'localtime')
            """
        ).fetchone()["c"]

        active_agents = conn.execute(
            """
            SELECT COUNT(DISTINCT agent) AS c
            FROM (
                SELECT TRIM(started_by) AS agent FROM tickets WHERE started_by IS NOT NULL AND TRIM(started_by) != ''
                UNION
                SELECT TRIM(done_by) AS agent FROM tickets WHERE done_by IS NOT NULL AND TRIM(done_by) != ''
            )
            """
        ).fetchone()["c"]
    finally:
        conn.close()

    summary = {
        "active_projects": sum(1 for p in projects if p["status"] == "active"),
        "tickets_in_flight": sum(p["in_flight_count"] for p in projects),
        "completed_today": int(completed_today or 0),
        "active_agents": int(active_agents or 0),
    }

    return {
        "projects": projects,
        "spaces": all_spaces,
        "summary": summary,
        "server_time": datetime.now().isoformat(timespec="seconds"),
    }





def _extract_agent(entry):
    text = (entry or "").strip()
    if not text:
        return "system"
    if "(by " in text:
        marker = text.split("(by ", 1)[1]
        return marker.split(")", 1)[0].strip() or "system"
    tokens = text.replace("✓", "").replace("🎉", "").strip().split()
    if len(tokens) >= 2 and tokens[1].lower() in {"started", "completed", "closed", "claimed", "reopened", "blocked", "unblocked", "abandoned"}:
        return tokens[0]
    return "system"



def _status_action_meta(new_state):
    mapping = {
        "done": ("done", "✅", "marked done"),
        "skipped": ("done", "⏭️", "skipped"),
        "in-progress": ("started", "🚀", "started"),
        "blocked": ("blocked", "⛔", "blocked"),
        "pending": ("other", "🔄", "moved to todo"),
    }
    return mapping.get((new_state or "").strip().lower(), ("other", "📝", f"changed to {(new_state or 'updated').strip()}"))


def _log_action_meta(entry):
    raw = (entry or "").strip()
    lowered = raw.lower()
    if "create" in lowered:
        return "created", "🆕", "created"
    if "block" in lowered:
        return "blocked", "⛔", "blocked"
    if "done" in lowered or "completed" in lowered or "closed" in lowered:
        return "done", "✅", "completed"
    if "start" in lowered or "claimed" in lowered:
        return "started", "🚀", "started"
    if "skip" in lowered:
        return "skipped", "⏭️", "skipped"
    return "log", "📝", raw or "logged update"


def _activity_feed_payload(limit=300):
    conn = get_connection(_db_path())
    try:
        log_rows = conn.execute(
            """
            SELECT l.id AS event_id, l.created_at AS timestamp, l.entry, p.slug AS project_slug, p.title AS project_title, t.num AS ticket_num
            FROM log l
            JOIN projects p ON p.id = l.project_id
            LEFT JOIN tickets t ON t.id = l.ticket_id
            ORDER BY l.created_at DESC, l.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        history_rows = conn.execute(
            """
            SELECT h.id AS event_id, h.changed_at AS timestamp, h.old_state, h.new_state,
                   t.num AS ticket_num, t.started_by, t.done_by,
                   p.slug AS project_slug, p.title AS project_title
            FROM ticket_history h
            JOIN tickets t ON t.id = h.ticket_id
            JOIN projects p ON p.id = t.project_id
            ORDER BY h.changed_at DESC, h.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    events = []
    for row in log_rows:
        action_type, emoji, action = _log_action_meta(row["entry"])
        events.append(
            {
                "id": f"log:{row['event_id']}",
                "timestamp": row["timestamp"],
                "agent": _extract_agent(row["entry"]),
                "action": action,
                "action_type": action_type,
                "emoji": emoji,
                "ticket_label": f"#{row['ticket_num']}" if row["ticket_num"] else "#-",
                "project_slug": row["project_slug"],
                "project_title": row["project_title"],
            }
        )

    for row in history_rows:
        action_type, emoji, action = _status_action_meta(row["new_state"])
        agent = "system"
        if row["new_state"] in ("done", "skipped") and (row["done_by"] or "").strip():
            agent = row["done_by"].strip()
        elif row["new_state"] == "in-progress" and (row["started_by"] or "").strip():
            agent = row["started_by"].strip()
        events.append(
            {
                "id": f"history:{row['event_id']}",
                "timestamp": row["timestamp"],
                "agent": agent,
                "action": action,
                "action_type": action_type,
                "emoji": emoji,
                "ticket_label": f"#{row['ticket_num']}" if row["ticket_num"] else "#-",
                "project_slug": row["project_slug"],
                "project_title": row["project_title"],
            }
        )

    events.sort(key=lambda item: (item.get("timestamp") or "", item["id"]))
    if len(events) > limit:
        events = events[-limit:]

    projects = sorted({item["project_slug"] for item in events if item.get("project_slug")})

    now_dt = datetime.now()
    latest_by_agent = {}
    for item in reversed(events):
        agent = (item.get("agent") or "").strip()
        if not agent or agent == "system" or agent in latest_by_agent:
            continue
        try:
            ts = datetime.fromisoformat(item["timestamp"])
        except (TypeError, ValueError):
            continue
        if (now_dt - ts).total_seconds() <= 3600:
            latest_by_agent[agent] = item["timestamp"]

    active_agents = [
        {"name": name, "last_seen": ts}
        for name, ts in sorted(latest_by_agent.items(), key=lambda pair: pair[1], reverse=True)
    ]

    return {
        "events": events,
        "projects": projects,
        "active_agents": active_agents,
        "server_time": datetime.now().isoformat(timespec="seconds"),
    }

def _ticket_detail_payload(conn, project_id, ticket_num):
    row = conn.execute(
        """
        SELECT id, num, title, description, status, priority, tags, depends_on, close_note, started_by, done_by, due_date, model_tier
        FROM tickets
        WHERE project_id=? AND num=?
        """,
        (project_id, ticket_num),
    ).fetchone()
    if not row:
        return None

    ticket = _normalize_ticket(row)
    ticket["close_note"] = row["close_note"] or ""

    subtasks = [dict(r) for r in conn.execute(
        "SELECT num, title, status FROM subtasks WHERE ticket_id=? ORDER BY num",
        (ticket["id"],),
    ).fetchall()]

    dep_nums = ticket["dependencies"]
    blocked_by = []
    if dep_nums:
        placeholders = ",".join("?" for _ in dep_nums)
        blocked_rows = conn.execute(
            f"SELECT num, title FROM tickets WHERE project_id=? AND num IN ({placeholders}) ORDER BY num",
            (project_id, *dep_nums),
        ).fetchall()
        blocked_by = [dict(r) for r in blocked_rows]

    project_ticket_rows = conn.execute(
        "SELECT num, title, depends_on FROM tickets WHERE project_id=? AND id!=? ORDER BY num",
        (project_id, ticket["id"]),
    ).fetchall()
    blocks = []
    for r in project_ticket_rows:
        try:
            ticket_deps = json.loads(r["depends_on"] or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            ticket_deps = []
        if ticket["num"] in ticket_deps:
            blocks.append({"num": r["num"], "title": r["title"]})

    history_rows = conn.execute(
        "SELECT changed_at, old_state, new_state FROM ticket_history WHERE ticket_id=? ORDER BY id DESC",
        (ticket["id"],),
    ).fetchall()
    log_rows = conn.execute(
        "SELECT created_at, entry FROM log WHERE ticket_id=? ORDER BY id DESC",
        (ticket["id"],),
    ).fetchall()

    audit_history = []
    for r in history_rows:
        old_state = r["old_state"] or "(none)"
        new_state = r["new_state"] or ""
        audit_history.append(
            {
                "timestamp": r["changed_at"],
                "agent": "system",
                "message": f"state transition: {old_state} → {new_state}",
                "transition": {"old_state": old_state, "new_state": new_state},
            }
        )
    for r in log_rows:
        entry = r["entry"] or ""
        audit_history.append(
            {
                "timestamp": r["created_at"],
                "agent": _extract_agent(entry),
                "message": entry,
                "transition": None,
            }
        )
    audit_history.sort(key=lambda item: item["timestamp"], reverse=True)

    return {
        "id": ticket["id"],
        "num": ticket["num"],
        "title": ticket["title"],
        "status": ticket["status"],
        "priority": ticket["priority"],
        "description": ticket["description"],
        "model_tier": ticket.get("model_tier", "auto"),
        "subtasks": subtasks,
        "blocked_by": blocked_by,
        "blocks": blocks,
        "audit_history": audit_history,
        "close_note": ticket["close_note"],
    }




def _project_board_payload(slug, priority_filter="", tag_filter=""):
    priority_filter = (priority_filter or "").strip().lower()
    tag_filter = (tag_filter or "").strip().lower()

    conn = get_connection(_db_path())
    try:
        project = conn.execute("SELECT id, slug, title FROM projects WHERE slug=?", (slug,)).fetchone()
        if not project:
            return None

        rows = conn.execute(
            """
            SELECT id, num, title, description, status, priority, tags, depends_on, started_by, done_by, due_date, model_tier
            FROM tickets
            WHERE project_id=?
            ORDER BY num
            LIMIT 1000
            """,
            (project["id"],),
        ).fetchall()

        ticket_ids = [row["id"] for row in rows]
        subtask_progress = {}
        if ticket_ids:
            placeholders = ",".join("?" for _ in ticket_ids)
            progress_rows = conn.execute(
                f"""
                SELECT ticket_id, COUNT(*) AS total, SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) AS done
                FROM subtasks
                WHERE ticket_id IN ({placeholders})
                GROUP BY ticket_id
                """,
                ticket_ids,
            ).fetchall()
            subtask_progress = {
                r["ticket_id"]: {"done": int(r["done"] or 0), "total": int(r["total"] or 0)} for r in progress_rows
            }

        chain_state = get_chain_state(conn, project["id"]) or {}
        chain_current_ticket_num = None
        if chain_state.get("current_ticket_id"):
            ticket_row = conn.execute(
                "SELECT num FROM tickets WHERE id=?",
                (chain_state["current_ticket_id"],),
            ).fetchone()
            if ticket_row:
                chain_current_ticket_num = ticket_row["num"]
    finally:
        conn.close()

    ticket_status_map = {row["num"]: row["status"] for row in rows}

    grouped = {s: [] for s in KANBAN_STATUS_ORDER}
    for row in rows:
        ticket = _normalize_ticket(row)
        subtask = subtask_progress.get(ticket["id"], {"done": 0, "total": 0})
        ticket["subtask_done"] = subtask["done"]
        ticket["subtask_total"] = subtask["total"]
        ticket["subtask_pct"] = int(round((subtask["done"] / subtask["total"]) * 100)) if subtask["total"] else 0
        ticket["active_agent"] = bool(ticket["assignee"] and ticket["status"] == "in-progress")

        is_blocked = (
            ticket["status"] == "pending"
            and bool(ticket["dependencies"])
            and any(ticket_status_map.get(dep_num) not in ("done", "skipped") for dep_num in ticket["dependencies"])
        )
        group_key = "blocked" if is_blocked else ticket["status"]
        if group_key == "skipped":
            group_key = "done"
        if group_key not in grouped:
            continue
        if _ticket_matches(ticket, priority_filter, tag_filter):
            grouped[group_key].append(ticket)

    done_count = len(grouped.get("done", []))
    total_count = sum(len(grouped[s]) for s in KANBAN_STATUS_ORDER)

    return {
        "project": {"slug": project["slug"], "title": project["title"]},
        "grouped": grouped,
        "done_count": done_count,
        "total_count": total_count,
        "chain_status": chain_state.get("status") or "stopped",
        "chain_current_ticket_num": chain_current_ticket_num,
        "chain_pause_reason": chain_state.get("pause_reason"),
        "server_time": datetime.now().isoformat(timespec="seconds"),
    }

def create_app():
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
        static_url_path="/static",
    )

    @app.route("/")
    def index():
        payload = _project_stats_payload()
        projects = payload["projects"]
        conn = get_connection(_db_path())
        try:
            home_spaces = _group_projects_by_space(conn, projects)
        finally:
            conn.close()
        return render_template(
            "home.html",
            projects=projects,
            spaces=payload.get("spaces", []),
            home_sections=_group_projects_for_home(projects),
            home_spaces=home_spaces,
            summary=payload["summary"],
        )

    @app.route("/favicon.ico")
    def favicon():
        return redirect(url_for("static", filename="favicon.svg"), code=308)

    @app.route("/api/stats")
    def api_stats():
        return _project_stats_payload()

    @app.route("/events")
    @app.route("/stream")
    def events():
        try:
            interval = max(1, min(int(request.args.get("interval", "2")), 30))
        except (ValueError, TypeError):
            interval = 2
        project_slug = (request.args.get("project") or "").strip()
        priority_filter = request.args.get("priority", "")
        tag_filter = request.args.get("tag", "")

        def event_stream():
            while True:
                stats_payload = _project_stats_payload()
                activity_payload = _activity_feed_payload()
                yield f"event: project_stats\ndata: {json.dumps(stats_payload)}\n\n"
                yield f"event: activity_feed\ndata: {json.dumps(activity_payload)}\n\n"
                if project_slug:
                    board_payload = _project_board_payload(project_slug, priority_filter, tag_filter)
                    if board_payload is not None:
                        yield f"event: project_board\ndata: {json.dumps(board_payload)}\n\n"
                time.sleep(interval)

        return sse_response(event_stream)

    @app.route("/activity")
    def activity():
        return render_template("activity.html")

    @app.route("/agents")
    def agents():
        conn = get_connection(_db_path())
        try:
            agents_data = list_agents(conn)
            roles_data = list_roles(conn)
        finally:
            conn.close()
        return render_template(
            "agents.html",
            agents=agents_data,
            roles=roles_data,
            detected_tools=_detect_tools_status(),
        )

    @app.route("/agents/add", methods=["POST"])
    @_require_local_origin
    def add_agent():
        name = (request.form.get("name") or "").strip()
        command_template = (request.form.get("command_template") or "").strip()
        if not name or not command_template:
            return ("Missing name or command template", 400)
        conn = get_connection(_db_path())
        try:
            create_agent(conn, name, command_template, role_names=_parse_roles_from_form(request.form))
        except Exception:
            return ("Unable to add agent", 400)
        finally:
            conn.close()
        return agents()

    @app.route("/agents/<name>/edit", methods=["POST"])
    @_require_local_origin
    def edit_agent(name):
        command_template = (request.form.get("command_template") or "").strip()
        if not command_template:
            return ("Missing command template", 400)
        conn = get_connection(_db_path())
        try:
            updated = update_agent(
                conn,
                name,
                new_command_template=command_template,
                role_names=_parse_roles_from_form(request.form),
            )
            if not updated:
                return ("Agent not found", 404)
        except Exception:
            return ("Unable to update agent", 400)
        finally:
            conn.close()
        return agents()

    @app.route("/agents/<name>/delete", methods=["POST"])
    @_require_local_origin
    def delete_agent_route(name):
        conn = get_connection(_db_path())
        try:
            if not delete_agent(conn, name):
                return ("Agent not found", 404)
        finally:
            conn.close()
        return agents()

    @app.route("/space/<slug>")
    def space_detail(slug):
        conn = get_connection(_db_path())
        try:
            space_row = conn.execute(
                "SELECT id, slug, title, description FROM spaces WHERE slug=?", (slug,)
            ).fetchone()
            if not space_row:
                abort(404)
            space = dict(space_row)

            # Get projects in this space
            proj_rows = conn.execute(
                "SELECT id, slug, title, status, updated_at, dir, space_id FROM projects WHERE space_id=? ORDER BY updated_at DESC",
                (space["id"],),
            ).fetchall()
            projects = []
            for p in proj_rows:
                pd = dict(p)
                stats = conn.execute(
                    "SELECT COUNT(*) as total, SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) as done FROM tickets WHERE project_id=?",
                    (pd["id"],),
                ).fetchone()
                pd["ticket_count"] = stats["total"]
                pd["done_count"] = stats["done"]
                pd["progress_pct"] = round(100 * stats["done"] / stats["total"]) if stats["total"] else 0
                pd["status_label"] = HOME_STATUS_LABELS.get(pd["status"], pd["status"])
                pd["missing_directory"] = bool(pd.get("dir") and not os.path.isdir(os.path.expanduser(pd["dir"])))
                projects.append(pd)

            # Get docs from filesystem
            docs = _list_space_docs(slug)
        finally:
            conn.close()

        return render_template(
            "space_detail.html",
            space=space,
            projects=projects,
            docs=docs,
        )

    @app.route("/space/<slug>/doc/<filename>")
    def space_doc_editor(slug, filename):
        conn = get_connection(_db_path())
        try:
            space_row = conn.execute(
                "SELECT id, slug, title FROM spaces WHERE slug=?", (slug,)
            ).fetchone()
            if not space_row:
                abort(404)
            space = dict(space_row)
        finally:
            conn.close()

        # Validate filename
        if "/" in filename or "\\" in filename or filename.startswith("."):
            abort(400)
        if not filename.endswith(".md"):
            abort(400)

        space_dir, fpath = _safe_doc_path(slug, filename)
        if space_dir is None or fpath is None:
            abort(400)
        if not os.path.isfile(fpath):
            abort(404)

        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
        except (OSError, IOError):
            abort(500)

        return render_template(
            "doc_editor.html",
            space=space,
            filename=filename,
            content=content,
            filepath=fpath,
        )

    @app.route("/api/space/<slug>/doc/add", methods=["POST"])
    @_require_local_origin
    def api_add_doc(slug):
        conn = get_connection(_db_path())
        try:
            space_row = conn.execute(
                "SELECT id FROM spaces WHERE slug=?", (slug,)
            ).fetchone()
            if not space_row:
                abort(404)
        finally:
            conn.close()

        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        if not title:
            return {"error": "Title is required"}, 400

        # Slugify title to filename
        fname = slugify(title) or "untitled"
        if not fname.endswith(".md"):
            fname += ".md"

        space_dir, fpath = _safe_doc_path(slug, fname)
        if space_dir is None or fpath is None:
            return {"error": "Invalid filename"}, 400
        os.makedirs(space_dir, exist_ok=True)

        if os.path.exists(fpath):
            return {"error": "File already exists"}, 409

        try:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(f"# {title}\n")
        except (OSError, IOError):
            return {"error": "Failed to create file"}, 500

        # Sanitize for response — html.escape prevents any reflected XSS
        safe_slug = html.escape(slug, quote=True)
        safe_fname = html.escape(fname, quote=True)
        return {"ok": True, "filename": safe_fname, "redirect": f"/space/{safe_slug}/doc/{safe_fname}"}

    @app.route("/api/space/<slug>/doc/<filename>", methods=["POST"])
    @_require_local_origin
    def api_save_doc(slug, filename):
        conn = get_connection(_db_path())
        try:
            space_row = conn.execute(
                "SELECT id FROM spaces WHERE slug=?", (slug,)
            ).fetchone()
            if not space_row:
                abort(404)
        finally:
            conn.close()

        if "/" in filename or "\\" in filename or filename.startswith("."):
            abort(400)
        if not filename.endswith(".md"):
            abort(400)

        space_dir, fpath = _safe_doc_path(slug, filename)
        if space_dir is None or fpath is None:
            abort(400)
        if not os.path.isfile(fpath):
            abort(404)

        data = request.get_json(silent=True) or {}
        content = data.get("content")
        if content is None:
            return {"error": "Missing content"}, 400
        if len(content) > 5_000_000:
            return {"error": "Content too large (max 5MB)"}, 413

        try:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(content)
        except (OSError, IOError):
            return {"error": "Failed to save file"}, 500

        return {"ok": True}

    @app.route("/project/<slug>")
    def project_detail(slug):
        priority_filter = request.args.get("priority", "").strip().lower()
        tag_filter = request.args.get("tag", "").strip().lower()

        conn = get_connection(_db_path())
        try:
            project = conn.execute("SELECT id, slug, title, status, dir, space_id FROM projects WHERE slug=?", (slug,)).fetchone()
            if not project:
                abort(404)

            space_info = None
            if project["space_id"]:
                space_row = conn.execute(
                    "SELECT slug, title FROM spaces WHERE id=?", (project["space_id"],)
                ).fetchone()
                if space_row:
                    space_info = dict(space_row)

            rows = conn.execute(
                """
                SELECT id, num, title, description, status, priority, tags, depends_on, started_by, done_by, due_date
                FROM tickets
                WHERE project_id=?
                ORDER BY num
                LIMIT 1000
                """,
                (project["id"],),
            ).fetchall()

            available_tags = sorted(
                {
                    tag.strip()
                    for row in rows
                    for tag in (row["tags"] or "").split(",")
                    if tag.strip()
                },
                key=lambda value: value.lower(),
            )

            ticket_ids = [row["id"] for row in rows]
            subtask_progress = {}
            if ticket_ids:
                placeholders = ",".join("?" for _ in ticket_ids)
                progress_rows = conn.execute(
                    f"""
                    SELECT ticket_id, COUNT(*) AS total, SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) AS done
                    FROM subtasks
                    WHERE ticket_id IN ({placeholders})
                    GROUP BY ticket_id
                    """,
                    ticket_ids,
                ).fetchall()
                subtask_progress = {
                    r["ticket_id"]: {"done": int(r["done"] or 0), "total": int(r["total"] or 0)} for r in progress_rows
                }

            chain = get_chain_state(conn, project["id"]) or {}
            chain_current_ticket_num = None
            if chain.get("current_ticket_id"):
                chain_ticket_row = conn.execute(
                    "SELECT num FROM tickets WHERE id=?",
                    (chain["current_ticket_id"],),
                ).fetchone()
                if chain_ticket_row:
                    chain_current_ticket_num = chain_ticket_row["num"]
        finally:
            conn.close()

        ticket_status_map = {row["num"]: row["status"] for row in rows}

        grouped = {s: [] for s in KANBAN_STATUS_ORDER}
        done_count = 0
        for row in rows:
            ticket = _normalize_ticket(row)
            if ticket["status"] in ("done", "skipped"):
                done_count += 1

            subtask = subtask_progress.get(ticket["id"], {"done": 0, "total": 0})
            ticket["subtask_done"] = subtask["done"]
            ticket["subtask_total"] = subtask["total"]
            ticket["subtask_pct"] = int(round((subtask["done"] / subtask["total"]) * 100)) if subtask["total"] else 0
            ticket["active_agent"] = bool(ticket["assignee"] and ticket["status"] == "in-progress")

            is_blocked = (
                ticket["status"] == "pending"
                and bool(ticket["dependencies"])
                and any(ticket_status_map.get(dep_num) not in ("done", "skipped") for dep_num in ticket["dependencies"])
            )
            group_key = "blocked" if is_blocked else ticket["status"]
            if group_key == "skipped":
                group_key = "done"
            if group_key not in grouped:
                continue
            if _ticket_matches(ticket, priority_filter, tag_filter):
                grouped[group_key].append(ticket)

        chain_status = (chain.get("status") or "stopped").lower()
        chain_pause_reason = chain.get("pause_reason")
        if chain_status == "running":
            chain_text = f"Automation: running — ticket #{chain_current_ticket_num or '?'}"
        elif chain_status == "paused":
            chain_text = f"Automation: paused — {chain_pause_reason or 'waiting'}"
        else:
            chain_text = "Automation: idle"

        return render_template(
            "project.html",
            project=project,
            grouped=grouped,
            status_order=KANBAN_STATUS_ORDER,
            status_labels=KANBAN_STATUS_LABELS,
            done_count=done_count,
            total_count=len(rows),
            filters={"priority": priority_filter, "tag": tag_filter},
            available_tags=available_tags,
            chain=chain,
            chain_current_ticket_num=chain_current_ticket_num,
            chain_pause_reason=chain_pause_reason,
            chain_text=chain_text,
            directory_warning=bool(project["dir"] and not os.path.isdir(project["dir"])),
            space_info=space_info,
        )

    @app.route("/api/chain/<slug>/start", methods=["POST"])
    @_require_local_origin
    def api_chain_start(slug):
        conn = get_connection(_db_path())
        try:
            project = conn.execute("SELECT id, slug, dir FROM projects WHERE slug=?", (slug,)).fetchone()
            if not project:
                abort(404)
            project_dir = (project["dir"] or "").strip()
            if not project_dir:
                return (
                    {
                        "error": (
                            f"No directory linked to project '{project['slug']}'. "
                            "Set it on the project page before starting work."
                        )
                    },
                    400,
                )
            if project["dir"] and not os.path.isdir(project["dir"]):
                print(f"Warning: linked project directory does not exist: {project['dir']}")
            state = get_chain_state(conn, project["id"]) or {}
            if (state.get("status") or "").lower() == "running":
                return ({"error": "chain already running"}, 409)
            try:
                subprocess.Popen(
                    ["agentplan", "chain", slug],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )
            except OSError:
                LOGGER.exception("failed to start chain process")
                return ({"error": "failed to start chain process"}, 500)
            set_chain_state(conn, project["id"], "running")
            return {"ok": True}
        finally:
            conn.close()

    @app.route("/api/chain/<slug>/stop", methods=["POST"])
    @_require_local_origin
    def api_chain_stop(slug):
        conn = get_connection(_db_path())
        try:
            project = conn.execute("SELECT id FROM projects WHERE slug=?", (slug,)).fetchone()
            if not project:
                abort(404)
            set_chain_state(conn, project["id"], "stopped", pause_reason="stop requested")
            return {"ok": True}
        finally:
            conn.close()

    @app.route("/api/project/<slug>/directory", methods=["POST"])
    @_require_local_origin
    def api_project_directory(slug):
        payload = request.get_json(silent=True) or {}
        raw_directory = payload.get("directory")
        if raw_directory and not isinstance(raw_directory, str):
            abort(400)

        raw_dir = raw_directory.strip() if isinstance(raw_directory, str) else ""
        directory = os.path.expanduser(raw_dir) if raw_dir else None
        directory = os.path.realpath(directory) if directory else directory

        sensitive_dirs = {
            "/",
            "/bin",
            "/dev",
            "/etc",
            "/proc",
            "/sbin",
            "/sys",
            "/usr/bin",
            "/usr/sbin",
            "/var/root",
        }
        if directory and directory in sensitive_dirs:
            return ({"error": "directory points to a sensitive system path"}, 400)

        conn = get_connection(_db_path())
        try:
            project = conn.execute("SELECT id FROM projects WHERE slug=?", (slug,)).fetchone()
            if not project:
                abort(404)
            ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            conn.execute(
                "UPDATE projects SET dir=?, updated_at=? WHERE id=?",
                (directory, ts, project["id"]),
            )
            conn.commit()
            return {"ok": True, "has_directory": bool(directory)}
        finally:
            conn.close()

    @app.route("/api/project/create", methods=["POST"])
    @_require_local_origin
    def api_project_create():
        conn = get_connection(_db_path())
        try:
            data = request.get_json(silent=True) or {}
            title = (data.get("title") or "").strip()
            if not title:
                return ({"error": "title is required"}, 400)
            description = (data.get("description") or "").strip()
            directory = (data.get("directory") or "").strip()
            directory = os.path.expanduser(directory) if directory else None
            slug = unique_slug(conn, slugify(title))
            # Assign default space_id to match CLI behavior
            default_space = conn.execute(
                "SELECT id FROM spaces WHERE slug='default'"
            ).fetchone()
            space_id = default_space["id"] if default_space else None
            conn.execute(
                "INSERT INTO projects (slug, title, notes, dir, space_id) VALUES (?,?,?,?,?)",
                (slug, title, description, directory, space_id),
            )
            conn.commit()
            return redirect(url_for("project_detail", slug=slug), code=303)
        finally:
            conn.close()

    def _transition_error_response(reason):
        if reason and "terminal state" in reason:
            return ({"error": "Cannot transition ticket from a terminal state."}, 400)
        if reason and ("Unknown source state" in reason or "Unknown target state" in reason):
            return ({"error": "Unknown ticket state."}, 400)
        return ({"error": "Invalid ticket state transition."}, 400)

    @app.route("/api/project/<slug>/close", methods=["POST"])
    @_require_local_origin
    def api_project_close(slug):
        conn = get_connection(_db_path())
        try:
            project = resolve_project(conn, slug)
            if not project:
                abort(404)
            data = request.get_json(silent=True) or {}
            status = "abandoned" if data.get("abandon") else "completed"
            ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            conn.execute("UPDATE projects SET status=?, updated_at=? WHERE id=?", (status, ts, project["id"]))
            conn.commit()
            return {"ok": True, "status": status}
        finally:
            conn.close()

    @app.route("/api/project/<slug>/archive", methods=["POST"])
    @_require_local_origin
    def api_project_archive(slug):
        conn = get_connection(_db_path())
        try:
            project = resolve_project(conn, slug)
            if not project:
                abort(404)
            ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            conn.execute("UPDATE projects SET status=?, updated_at=? WHERE id=?", ("archived", ts, project["id"]))
            conn.commit()
            return {"ok": True, "status": "archived"}
        finally:
            conn.close()

    @app.route("/api/project/<slug>/delete", methods=["POST"])
    @_require_local_origin
    def api_project_delete(slug):
        conn = get_connection(_db_path())
        try:
            project = resolve_project(conn, slug)
            if not project:
                abort(404)
            conn.execute("DELETE FROM projects WHERE id=?", (project["id"],))
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    def _update_ticket_state(conn, project, ticket_num, new_status):
        ticket = resolve_ticket(conn, project["id"], ticket_num)
        if not ticket:
            return False, None

        ok, reason = validate_transition(ticket["status"], new_status)
        if not ok:
            return None, reason

        ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        completed_at = None
        claimed_at = ticket["claimed_at"]
        close_note = ticket["close_note"]
        if new_status in {"done", "skipped"}:
            completed_at = ts
            claimed_at = None
        else:
            if new_status != "in-progress":
                claimed_at = None
        if new_status == "pending":
            close_note = None

        conn.execute(
            "UPDATE tickets SET status=?, completed_at=?, claimed_at=?, close_note=? WHERE id=?",
            (new_status, completed_at, claimed_at, close_note, ticket["id"]),
        )
        conn.execute(
            "INSERT INTO ticket_history (ticket_id, old_state, new_state, changed_at) VALUES (?,?,?,?)",
            (ticket["id"], ticket["status"], new_status, ts),
        )
        conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (ts, project["id"]))
        if project["status"] == "active":
            check_auto_complete(conn, project["id"])
        conn.commit()
        return True, None

    @app.route("/api/project/<slug>/tickets-list")
    def api_project_tickets_list(slug):
        conn = get_connection(_db_path())
        try:
            project = resolve_project(conn, slug)
            if not project:
                abort(404)
            rows = conn.execute(
                "SELECT num, title, status FROM tickets WHERE project_id=? ORDER BY num",
                (project["id"],),
            ).fetchall()
            return [{"num": row["num"], "title": row["title"], "status": row["status"]} for row in rows]
        finally:
            conn.close()

    @app.route("/api/ticket/<slug>/<int:ticket_num>/transition", methods=["POST"])
    @_require_local_origin
    def api_ticket_transition(slug, ticket_num):
        conn = get_connection(_db_path())
        try:
            project = resolve_project(conn, slug)
            if not project:
                abort(404)
            data = request.get_json(silent=True) or {}
            new_status = (data.get("status") or "").strip()
            if not new_status:
                return ({"error": "status is required"}, 400)
            updated, reason = _update_ticket_state(conn, project, ticket_num, new_status)
            if updated is False:
                abort(404)
            if updated is None:
                return _transition_error_response(reason)
            return {"ok": True}
        finally:
            conn.close()

    @app.route("/api/ticket/<slug>/<int:ticket_num>/done", methods=["POST"])
    @_require_local_origin
    def api_ticket_mark_done(slug, ticket_num):
        conn = get_connection(_db_path())
        try:
            project = resolve_project(conn, slug)
            if not project:
                abort(404)
            updated, reason = _update_ticket_state(conn, project, ticket_num, "done")
            if updated is False:
                abort(404)
            if updated is None:
                return _transition_error_response(reason)
            return {"ok": True}
        finally:
            conn.close()

    @app.route("/api/ticket/<slug>/<int:ticket_num>/retry", methods=["POST"])
    @_require_local_origin
    def api_ticket_retry(slug, ticket_num):
        conn = get_connection(_db_path())
        try:
            project = resolve_project(conn, slug)
            if not project:
                abort(404)
            updated, reason = _update_ticket_state(conn, project, ticket_num, "pending")
            if updated is False:
                abort(404)
            if updated is None:
                return _transition_error_response(reason)
            return {"ok": True}
        finally:
            conn.close()

    @app.route("/api/ticket/<slug>/<int:ticket_num>/skip", methods=["POST"])
    @_require_local_origin
    def api_ticket_skip(slug, ticket_num):
        conn = get_connection(_db_path())
        try:
            project = resolve_project(conn, slug)
            if not project:
                abort(404)
            updated, reason = _update_ticket_state(conn, project, ticket_num, "skipped")
            if updated is False:
                abort(404)
            if updated is None:
                return _transition_error_response(reason)
            return {"ok": True}
        finally:
            conn.close()

    @app.route("/api/ticket/<slug>/add", methods=["POST"])
    @_require_local_origin
    def api_ticket_add(slug):
        conn = get_connection(_db_path())
        try:
            project = conn.execute("SELECT id FROM projects WHERE slug=?", (slug,)).fetchone()
            if not project:
                abort(404)
            data = request.get_json(silent=True) or {}
            title = (data.get("title") or "").strip()
            if not title:
                return ({"error": "Title is required"}, 400)
            desc = (data.get("description") or "").strip()
            priority = data.get("priority", "none")
            if priority not in ("high", "medium", "low", "none"):
                priority = "none"
            model_tier = data.get("model_tier", "auto")
            if model_tier not in ("auto", "light", "standard", "reasoning"):
                model_tier = "auto"
            # Get next ticket number
            row = conn.execute(
                "SELECT COALESCE(MAX(num), 0) + 1 AS next_num FROM tickets WHERE project_id=?",
                (project["id"],),
            ).fetchone()
            num = row["next_num"]
            ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            conn.execute(
                "INSERT INTO tickets (project_id, num, title, description, priority, tags, depends_on, notes, model_tier) VALUES (?,?,?,?,?,?,?,?,?)",
                (project["id"], num, title, desc, priority, "", "[]", "", model_tier),
            )
            ticket_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute(
                "INSERT INTO ticket_history (ticket_id, old_state, new_state, changed_at) VALUES (?,?,?,?)",
                (ticket_id, None, "created", ts),
            )
            conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (ts, project["id"]))
            conn.commit()
            return {"ok": True, "num": num}
        finally:
            conn.close()

    @app.route("/api/ticket/<slug>/<int:ticket_num>/edit", methods=["POST"])
    @_require_local_origin
    def api_ticket_edit(slug, ticket_num):
        conn = get_connection(_db_path())
        try:
            project = conn.execute("SELECT id FROM projects WHERE slug=?", (slug,)).fetchone()
            if not project:
                abort(404)
            ticket = conn.execute(
                "SELECT id, title, description, priority FROM tickets WHERE project_id=? AND num=?",
                (project["id"], ticket_num),
            ).fetchone()
            if not ticket:
                abort(404)
            data = request.get_json(silent=True) or {}
            updates = {}
            if "title" in data:
                title = (data["title"] or "").strip()
                if title:
                    updates["title"] = title
            if "description" in data:
                updates["description"] = (data["description"] or "").strip()
            if "priority" in data:
                p = data["priority"]
                if p in ("high", "medium", "low", "none"):
                    updates["priority"] = p
            if "model_tier" in data:
                mt = data["model_tier"]
                if mt in ("auto", "light", "standard", "reasoning"):
                    updates["model_tier"] = mt
            if not updates:
                return ({"error": "No valid fields to update"}, 400)
            ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            set_clause = ", ".join(f"{key}=?" for key in updates.keys())
            conn.execute(
                f"UPDATE tickets SET {set_clause} WHERE id=?",
                (*updates.values(), ticket["id"]),
            )
            conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (ts, project["id"]))
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    @app.route("/api/ticket/<slug>/<int:ticket_num>/delete", methods=["POST"])
    @_require_local_origin
    def api_ticket_delete(slug, ticket_num):
        conn = get_connection(_db_path())
        try:
            project = resolve_project(conn, slug)
            if not project:
                abort(404)
            ticket = resolve_ticket(conn, project["id"], ticket_num)
            if not ticket:
                abort(404)

            conn.execute("DELETE FROM tickets WHERE id=?", (ticket["id"],))
            others = conn.execute(
                "SELECT id, depends_on FROM tickets WHERE project_id=?",
                (project["id"],),
            ).fetchall()
            for other in others:
                deps = json.loads(other["depends_on"] or "[]")
                if ticket["num"] in deps:
                    deps.remove(ticket["num"])
                    conn.execute(
                        "UPDATE tickets SET depends_on=? WHERE id=?",
                        (json.dumps(deps), other["id"]),
                    )

            ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (ts, project["id"]))
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    @app.route("/api/ticket/<slug>/<int:ticket_num>/subtask/add", methods=["POST"])
    @_require_local_origin
    def api_ticket_subtask_add(slug, ticket_num):
        conn = get_connection(_db_path())
        try:
            project = resolve_project(conn, slug)
            if not project:
                abort(404)
            ticket = resolve_ticket(conn, project["id"], ticket_num)
            if not ticket:
                abort(404)
            data = request.get_json(silent=True) or {}
            title = (data.get("title") or "").strip()
            if not title:
                return ({"error": "title is required"}, 400)

            num = next_subtask_num(conn, ticket["id"])
            conn.execute(
                "INSERT INTO subtasks (ticket_id, num, title) VALUES (?,?,?)",
                (ticket["id"], num, title),
            )
            ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (ts, project["id"]))
            conn.commit()
            return {"ok": True, "num": num}
        finally:
            conn.close()

    @app.route("/api/ticket/<slug>/<int:ticket_num>/subtask/<int:subtask_num>/done", methods=["POST"])
    @_require_local_origin
    def api_ticket_subtask_done(slug, ticket_num, subtask_num):
        conn = get_connection(_db_path())
        try:
            project = resolve_project(conn, slug)
            if not project:
                abort(404)
            ticket = resolve_ticket(conn, project["id"], ticket_num)
            if not ticket:
                abort(404)
            subtask = resolve_subtask(conn, ticket["id"], subtask_num)
            if not subtask:
                abort(404)

            ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            conn.execute(
                "UPDATE subtasks SET status='done', completed_at=? WHERE id=?",
                (ts, subtask["id"]),
            )
            conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (ts, project["id"]))
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    @app.route("/api/ticket/<slug>/<int:ticket_num>/depend", methods=["POST"])
    @_require_local_origin
    def api_ticket_depend(slug, ticket_num):
        conn = get_connection(_db_path())
        try:
            project = resolve_project(conn, slug)
            if not project:
                abort(404)
            ticket = resolve_ticket(conn, project["id"], ticket_num)
            if not ticket:
                abort(404)
            data = request.get_json(silent=True) or {}
            dep_num = data.get("on")
            dep_ticket = resolve_ticket(conn, project["id"], dep_num)
            if not dep_ticket:
                abort(404)

            existing = json.loads(ticket["depends_on"] or "[]")
            merged = sorted(set(existing + [int(dep_num)]))
            tickets = conn.execute("SELECT * FROM tickets WHERE project_id=?", (project["id"],)).fetchall()
            if has_cycle(tickets, ticket["num"], merged):
                return ({"error": "Circular dependency detected."}, 400)

            conn.execute("UPDATE tickets SET depends_on=? WHERE id=?", (json.dumps(merged), ticket["id"]))
            ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (ts, project["id"]))
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    @app.route("/api/ticket/<slug>/<int:ticket_num>/undepend", methods=["POST"])
    @_require_local_origin
    def api_ticket_undepend(slug, ticket_num):
        conn = get_connection(_db_path())
        try:
            project = resolve_project(conn, slug)
            if not project:
                abort(404)
            ticket = resolve_ticket(conn, project["id"], ticket_num)
            if not ticket:
                abort(404)
            data = request.get_json(silent=True) or {}
            dep_num = data.get("dep")
            dep_ticket = resolve_ticket(conn, project["id"], dep_num)
            if not dep_ticket:
                abort(404)

            existing = json.loads(ticket["depends_on"] or "[]")
            if int(dep_num) not in existing:
                return ({"error": f"Ticket #{ticket['num']} does not depend on ticket #{int(dep_num)}."}, 400)

            updated = [dep for dep in existing if dep != int(dep_num)]
            conn.execute("UPDATE tickets SET depends_on=? WHERE id=?", (json.dumps(updated), ticket["id"]))
            ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (ts, project["id"]))
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    @app.route("/api/ticket/<slug>/<int:ticket_num>/log", methods=["POST"])
    @_require_local_origin
    def api_ticket_log(slug, ticket_num):
        conn = get_connection(_db_path())
        try:
            project = resolve_project(conn, slug)
            if not project:
                abort(404)
            ticket = resolve_ticket(conn, project["id"], ticket_num)
            if not ticket:
                abort(404)
            data = request.get_json(silent=True) or {}
            entry = (data.get("entry") or "").strip()
            if not entry:
                return ({"error": "entry is required"}, 400)

            ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            conn.execute(
                "INSERT INTO log (project_id, ticket_id, entry, created_at) VALUES (?,?,?,?)",
                (project["id"], ticket["id"], entry, ts),
            )
            conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (ts, project["id"]))
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    @app.route("/api/ticket/<slug>/<int:ticket_num>")
    def api_ticket_detail(slug, ticket_num):
        conn = get_connection(_db_path())
        try:
            project = conn.execute("SELECT id, slug, title, status FROM projects WHERE slug=?", (slug,)).fetchone()
            if not project:
                abort(404)
            payload = _ticket_detail_payload(conn, project["id"], ticket_num)
            if not payload:
                abort(404)
            chain_state = get_chain_state(conn, project["id"]) or {}
            chain_current_ticket_num = None
            if chain_state.get("current_ticket_id"):
                chain_ticket_row = conn.execute("SELECT num FROM tickets WHERE id=?", (chain_state["current_ticket_id"],)).fetchone()
                if chain_ticket_row:
                    chain_current_ticket_num = chain_ticket_row["num"]
            payload["project"] = {"slug": project["slug"], "title": project["title"]}
            payload["chain_status"] = chain_state.get("status") or "stopped"
            payload["chain_current_ticket_num"] = chain_current_ticket_num
            payload["chain_pause_reason"] = chain_state.get("pause_reason")
            return payload
        finally:
            conn.close()

    @app.route("/project/<slug>/ticket/<int:ticket_num>")
    def ticket_detail(slug, ticket_num):
        conn = get_connection(_db_path())
        try:
            project = conn.execute("SELECT id, slug, title, status FROM projects WHERE slug=?", (slug,)).fetchone()
            if not project:
                abort(404)
            payload = _ticket_detail_payload(conn, project["id"], ticket_num)
            if not payload:
                abort(404)
        finally:
            conn.close()

        history = [
            {"changed_at": item["timestamp"], "message": item["message"]}
            for item in payload["audit_history"]
        ]

        return render_template(
            "ticket.html",
            project=project,
            ticket=payload,
            subtasks=payload["subtasks"],
            blocked_by=payload["blocked_by"],
            blocks=payload["blocks"],
            history=history,
        )

    return app
