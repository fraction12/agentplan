#!/usr/bin/env python3
"""Read-only web dashboard for agentplan projects and tickets."""

import json
import os
import subprocess
import time
from collections import defaultdict
from datetime import datetime
from functools import wraps
from urllib.parse import urlparse

from flask import Flask, abort, render_template_string, request, url_for

from agentplan.db import (
    create_agent,
    delete_agent,
    get_chain_state,
    get_connection,
    list_agents,
    list_roles,
    set_chain_state,
    update_agent,
    validate_transition,
)

from .sse import sse_response
from .templates import (
    ACTIVITY_TEMPLATE,
    AGENTS_TEMPLATE,
    INDEX_TEMPLATE,
    KANBAN_STATUS_LABELS,
    KANBAN_STATUS_ORDER,
    PROJECT_TEMPLATE,
    TAG_TONES,
    TICKET_TEMPLATE,
)

def _db_path():
    return os.environ.get("AGENTPLAN_DB", os.path.expanduser("~/.agentplan/agentplan.db"))


def _is_local_origin(value):
    if not value:
        return False
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    host = (parsed.hostname or "").lower()
    return host in {"localhost", "127.0.0.1"}


def _require_local_origin(fn):
    @wraps(fn)
    def _wrapped(*args, **kwargs):
        origin = request.headers.get("Origin")
        referer = request.headers.get("Referer")
        if origin:
            if not _is_local_origin(origin):
                return ({"error": "forbidden"}, 403)
        elif referer:
            if not _is_local_origin(referer):
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


def _fetch_projects_with_stats(conn):
    projects = conn.execute(
        "SELECT id, slug, title, status, updated_at FROM projects ORDER BY updated_at DESC, id DESC LIMIT 100"
    ).fetchall()
    rows = conn.execute("SELECT project_id, status, COUNT(*) AS c FROM tickets GROUP BY project_id, status").fetchall()

    counts = defaultdict(lambda: defaultdict(int))
    for row in rows:
        counts[row["project_id"]][row["status"]] = row["c"]

    out = []
    for p in projects:
        project_counts = counts[p["id"]]
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
        out.append(
            {
                "id": p["id"],
                "slug": p["slug"],
                "title": p["title"],
                "status": p["status"],
                "updated_at": p["updated_at"],
                "breakdown": breakdown,
                "ticket_count": total,
                "done_count": done,
                "in_flight_count": in_flight,
                "progress_pct": progress,
            }
        )
    return out


def _ticket_matches(ticket, status_filter, priority_filter, tag_filter):
    if status_filter:
        normalized_status = "pending" if status_filter == "todo" else status_filter
        if ticket["status"] != normalized_status:
            return False
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
    }


def _project_stats_payload():
    conn = get_connection(_db_path())
    try:
        projects = _fetch_projects_with_stats(conn)

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
        "active_projects": sum(1 for p in projects if p["status"] != "completed"),
        "tickets_in_flight": sum(p["in_flight_count"] for p in projects),
        "completed_today": int(completed_today or 0),
        "active_agents": int(active_agents or 0),
    }

    return {
        "projects": projects,
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
        SELECT id, num, title, description, status, priority, tags, depends_on, close_note, started_by, done_by, due_date
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
        "subtasks": subtasks,
        "blocked_by": blocked_by,
        "blocks": blocks,
        "audit_history": audit_history,
        "close_note": ticket["close_note"],
    }




def _project_board_payload(slug, status_filter="", priority_filter="", tag_filter=""):
    status_filter = (status_filter or "").strip().lower()
    priority_filter = (priority_filter or "").strip().lower()
    tag_filter = (tag_filter or "").strip().lower()

    conn = get_connection(_db_path())
    try:
        project = conn.execute("SELECT id, slug, title FROM projects WHERE slug=?", (slug,)).fetchone()
        if not project:
            return None

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
        if _ticket_matches(ticket, status_filter, priority_filter, tag_filter):
            grouped[group_key].append(ticket)

    return {
        "project": {"slug": project["slug"], "title": project["title"]},
        "grouped": grouped,
        "chain_status": chain_state.get("status") or "stopped",
        "chain_current_ticket_num": chain_current_ticket_num,
        "chain_pause_reason": chain_state.get("pause_reason"),
        "server_time": datetime.now().isoformat(timespec="seconds"),
    }

def create_app():
    app = Flask(__name__)

    @app.route("/")
    def index():
        payload = _project_stats_payload()
        projects = payload["projects"]
        active_projects = [p for p in projects if p["status"] != "completed" and p["status"] != "archived"]
        completed_projects = [p for p in projects if p["status"] == "completed"]
        return render_template_string(
            INDEX_TEMPLATE,
            projects=projects,
            active_projects=active_projects,
            completed_projects=completed_projects,
            summary=payload["summary"],
        )

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
        status_filter = request.args.get("status", "")
        priority_filter = request.args.get("priority", "")
        tag_filter = request.args.get("tag", "")

        def event_stream():
            while True:
                stats_payload = _project_stats_payload()
                activity_payload = _activity_feed_payload()
                yield f"event: project_stats\ndata: {json.dumps(stats_payload)}\n\n"
                yield f"event: activity_feed\ndata: {json.dumps(activity_payload)}\n\n"
                if project_slug:
                    board_payload = _project_board_payload(project_slug, status_filter, priority_filter, tag_filter)
                    if board_payload is not None:
                        yield f"event: project_board\ndata: {json.dumps(board_payload)}\n\n"
                time.sleep(interval)

        return sse_response(event_stream)

    @app.route("/activity")
    def activity():
        return render_template_string(ACTIVITY_TEMPLATE)

    @app.route("/agents")
    def agents():
        conn = get_connection(_db_path())
        try:
            agents_data = list_agents(conn)
            roles_data = list_roles(conn)
        finally:
            conn.close()
        return render_template_string(
            AGENTS_TEMPLATE,
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

    @app.route("/project/<slug>")
    def project_detail(slug):
        status_filter = request.args.get("status", "").strip().lower()
        priority_filter = request.args.get("priority", "").strip().lower()
        tag_filter = request.args.get("tag", "").strip().lower()

        conn = get_connection(_db_path())
        try:
            project = conn.execute("SELECT id, slug, title, status FROM projects WHERE slug=?", (slug,)).fetchone()
            if not project:
                abort(404)
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
            if _ticket_matches(ticket, status_filter, priority_filter, tag_filter):
                grouped[group_key].append(ticket)

        chain_status = (chain.get("status") or "stopped").lower()
        chain_pause_reason = chain.get("pause_reason")
        if chain_status == "running":
            chain_text = f"Chain: running — ticket #{chain_current_ticket_num or '?'}"
        elif chain_status == "paused":
            chain_text = f"Chain: paused — {chain_pause_reason or 'waiting'}"
        else:
            chain_text = "Chain: idle"

        return render_template_string(
            PROJECT_TEMPLATE,
            project=project,
            grouped=grouped,
            status_order=KANBAN_STATUS_ORDER,
            status_labels=KANBAN_STATUS_LABELS,
            done_count=done_count,
            total_count=len(rows),
            filters={"status": status_filter, "priority": priority_filter, "tag": tag_filter},
            available_tags=available_tags,
            chain=chain,
            chain_current_ticket_num=chain_current_ticket_num,
            chain_pause_reason=chain_pause_reason,
            chain_text=chain_text,
        )

    @app.route("/api/chain/<slug>/start", methods=["POST"])
    @_require_local_origin
    def api_chain_start(slug):
        conn = get_connection(_db_path())
        try:
            project = conn.execute("SELECT id, slug FROM projects WHERE slug=?", (slug,)).fetchone()
            if not project:
                abort(404)
            state = get_chain_state(conn, project["id"]) or {}
            if (state.get("status") or "").lower() == "running":
                return ({"error": "chain already running"}, 409)
            set_chain_state(conn, project["id"], "running")
        finally:
            conn.close()

        subprocess.Popen(
            ["agentplan", "chain", slug],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {"ok": True}

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

    def _update_ticket_state(conn, project_id, ticket_num, new_status):
        ticket = conn.execute(
            "SELECT id, status FROM tickets WHERE project_id=? AND num=?",
            (project_id, ticket_num),
        ).fetchone()
        if not ticket:
            return False, None

        ok, reason = validate_transition(ticket["status"], new_status)
        if not ok:
            return None, reason

        ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        updates = {"status": new_status, "claimed_at": None}
        if new_status == "done":
            updates["completed_at"] = ts
        elif new_status == "pending":
            updates["completed_at"] = None
            updates["close_note"] = None
        elif new_status == "skipped":
            updates["completed_at"] = ts

        set_clause = ", ".join(f"{key}=?" for key in updates.keys())
        conn.execute(
            f"UPDATE tickets SET {set_clause} WHERE id=?",
            (*updates.values(), ticket["id"]),
        )
        conn.execute(
            "INSERT INTO ticket_history (ticket_id, old_state, new_state, changed_at) VALUES (?,?,?,?)",
            (ticket["id"], ticket["status"], new_status, ts),
        )
        conn.commit()
        return True, None

    @app.route("/api/ticket/<slug>/<int:ticket_num>/done", methods=["POST"])
    @_require_local_origin
    def api_ticket_mark_done(slug, ticket_num):
        conn = get_connection(_db_path())
        try:
            project = conn.execute("SELECT id FROM projects WHERE slug=?", (slug,)).fetchone()
            if not project:
                abort(404)
            updated, reason = _update_ticket_state(conn, project["id"], ticket_num, "done")
            if updated is False:
                abort(404)
            if updated is None:
                return ({"error": reason}, 400)
            return {"ok": True}
        finally:
            conn.close()

    @app.route("/api/ticket/<slug>/<int:ticket_num>/retry", methods=["POST"])
    @_require_local_origin
    def api_ticket_retry(slug, ticket_num):
        conn = get_connection(_db_path())
        try:
            project = conn.execute("SELECT id FROM projects WHERE slug=?", (slug,)).fetchone()
            if not project:
                abort(404)
            updated, reason = _update_ticket_state(conn, project["id"], ticket_num, "pending")
            if updated is False:
                abort(404)
            if updated is None:
                return ({"error": reason}, 400)
            return {"ok": True}
        finally:
            conn.close()

    @app.route("/api/ticket/<slug>/<int:ticket_num>/skip", methods=["POST"])
    @_require_local_origin
    def api_ticket_skip(slug, ticket_num):
        conn = get_connection(_db_path())
        try:
            project = conn.execute("SELECT id FROM projects WHERE slug=?", (slug,)).fetchone()
            if not project:
                abort(404)
            updated, reason = _update_ticket_state(conn, project["id"], ticket_num, "skipped")
            if updated is False:
                abort(404)
            if updated is None:
                return ({"error": reason}, 400)
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

        return render_template_string(
            TICKET_TEMPLATE,
            project=project,
            ticket=payload,
            subtasks=payload["subtasks"],
            blocked_by=payload["blocked_by"],
            blocks=payload["blocks"],
            history=history,
        )

    return app

