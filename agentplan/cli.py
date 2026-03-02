#!/usr/bin/env python3
"""agentplan — Project management CLI for AI agents."""

import argparse
import difflib
import json
import os
import re
import sys
from datetime import datetime

from agentplan.models import HistoryEntry, Project, Subtask, Ticket

from agentplan.db import (
    check_auto_complete,
    ensure as _ensure,
    get_connection,
    get_db_path,
    get_subtask_progress_map as _get_subtask_progress_map,
    has_cycle,
    init_db,
    list_project_slugs,
    next_subtask_num as _next_subtask_num,
    next_ticket_num as _next_ticket_num,
    now as _now,
    project_slug_suggestions,
    record_ticket_history as _record_ticket_history,
    resolve_project as db_resolve_project,
    resolve_subtask as db_resolve_subtask,
    resolve_ticket as db_resolve_ticket,
    unique_slug,
)

__version__ = "0.4.3"

# ---------------------------------------------------------------------------
# Input validation limits
# ---------------------------------------------------------------------------
MAX_TITLE_LEN = 200
MAX_DESC_LEN = 4000
MAX_NOTES_LEN = 4000
MAX_AGENT_LEN = 100
MAX_LOG_ENTRY_LEN = 4000
MAX_TAG_LEN = 500
MAX_SLUG_LEN = 60  # already enforced via slugify


def _validate_len(value, max_len, field_name):
    """Raise CliError if value exceeds max_len."""
    if value and len(value) > max_len:
        fail(
            f"{field_name} is too long ({len(value)} chars; max {max_len}).",
            suggestions=[f"Keep {field_name.lower()} under {max_len} characters."],
        )


PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2, "none": 3}
PRIORITY_CHOICES = ["high", "medium", "low", "none"]
COMPLETION_SHELLS = ["bash", "zsh", "fish"]
TOP_LEVEL_COMMANDS = [
    "init",
    "version",
    "create",
    "ticket",
    "next",
    "claim",
    "status",
    "search",
    "list",
    "archive",
    "attach",
    "log",
    "close",
    "note",
    "depend",
    "undepend",
    "remove",
    "history",
    "subtask",
    "completion",
]
TICKET_COMMANDS = ["add", "update", "edit", "done", "skip", "start", "list"]
SUBTASK_COMMANDS = ["add", "done", "list"]
PROJECT_TOP_LEVEL_COMMANDS = {
    "status",
    "next",
    "claim",
    "archive",
    "attach",
    "log",
    "close",
    "note",
    "depend",
    "undepend",
    "remove",
    "history",
}


class CliError(Exception):
    """Expected CLI error with optional suggestions and exit code."""

    def __init__(self, message, suggestions=None, exit_code=2):
        super().__init__(message)
        self.message = message
        self.suggestions = suggestions or []
        self.exit_code = exit_code


def fail(message, suggestions=None, exit_code=2):
    raise CliError(message, suggestions=suggestions, exit_code=exit_code)


# ---------------------------------------------------------------------------
# Slugify
# ---------------------------------------------------------------------------

def slugify(title):
    s = title.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s]+", "-", s.strip())
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:60] or "project"



# ---------------------------------------------------------------------------
# Resolve helpers
# ---------------------------------------------------------------------------

def resolve_project(conn, ident):
    row = db_resolve_project(conn, ident)
    if not row:
        suggestions = []
        close_matches = project_slug_suggestions(conn, ident)
        if close_matches:
            suggestions.append(f"Did you mean '{close_matches[0]}'?")
        suggestions.append("Run `agentplan list --all` to see all projects.")
        fail(f"Project '{ident}' not found.", suggestions=suggestions)
    return row


def resolve_ticket(conn, project_id, num_str, slug=""):
    try:
        int(num_str)
    except (ValueError, TypeError):
        fail(
            f"Invalid ticket number '{num_str}'.",
            suggestions=[
                "Ticket IDs must be numeric (for example: `1` or `2`).",
                f"Run `agentplan ticket list {slug or '<project>'}` to see ticket IDs.",
            ],
        )
    row = db_resolve_ticket(conn, project_id, num_str)
    if not row:
        fail(
            f"Ticket #{int(num_str)} not found in project '{slug}'.",
            suggestions=[f"Run `agentplan ticket list {slug}` to see available ticket IDs."],
        )
    return row


def resolve_subtask(conn, ticket_id, num_str, ticket_num, slug=""):
    try:
        int(num_str)
    except (ValueError, TypeError):
        fail(
            f"Invalid subtask number '{num_str}'.",
            suggestions=[
                "Subtask IDs must be numeric (for example: `1`).",
                f"Run `agentplan subtask list {slug or '<project>'} {ticket_num}` to see subtask IDs.",
            ],
        )
    row = db_resolve_subtask(conn, ticket_id, num_str)
    if not row:
        fail(
            f"Subtask #{int(num_str)} not found for ticket #{ticket_num} in project '{slug}'.",
            suggestions=[f"Run `agentplan subtask list {slug} {ticket_num}` to see subtasks."],
        )
    return row


# ---------------------------------------------------------------------------
# Dependency helpers (all use ticket num, not internal id)
# ---------------------------------------------------------------------------

def has_cycle(tickets, ticket_num, new_deps):
    """Return True if setting ticket's deps to new_deps creates a cycle. Uses ticket nums."""
    adj = {}
    for t in tickets:
        adj[t["num"]] = json.loads(t["depends_on"] or "[]")
    adj[ticket_num] = list(new_deps)

    visited, stack = set(), set()

    def dfs(n):
        visited.add(n)
        stack.add(n)
        for d in adj.get(n, []):
            if d not in visited:
                if dfs(d):
                    return True
            elif d in stack:
                return True
        stack.discard(n)
        return False

    return dfs(ticket_num)


def get_unblocked(tickets):
    done_nums = {t["num"] for t in tickets if t["status"] in ("done", "skipped")}
    out = []
    for t in tickets:
        if t["status"] != "pending":
            continue
        deps = json.loads(t["depends_on"] or "[]")
        if all(d in done_nums for d in deps):
            out.append(t)
    return out



# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _ticket_icon(status, blocked):
    if status == "done":
        return "✓"
    if status == "skipped":
        return "⊘"
    if status == "in-progress":
        return "▶"
    return "⏳" if blocked else "○"


def _is_blocked(ticket, done_nums):
    deps = json.loads(ticket["depends_on"] or "[]")
    return any(d not in done_nums for d in deps)


def _priority_value(priority):
    return PRIORITY_ORDER.get((priority or "none").lower(), PRIORITY_ORDER["none"])


def _priority_label(priority):
    return (priority or "none").lower()


def _parse_due_date(raw):
    if raw in (None, ""):
        return None
    value = raw.strip()
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        fail(
            "Invalid due date.",
            suggestions=["Use YYYY-MM-DD format (for example: `2026-03-01`)."],
        )
    return value


def _is_overdue(ticket, today=None):
    due = ticket["due_date"]
    if not due or ticket["status"] in ("done", "skipped"):
        return False
    if today is None:
        today = datetime.now().strftime("%Y-%m-%d")
    return due < today


def _sort_next_items(items):
    return sorted(
        items,
        key=lambda t: (
            0 if _is_overdue(t) else 1,
            _priority_value(t["priority"]),
            0 if t["status"] == "in-progress" else 1,
            t["num"],
        ),
    )


def _parse_tags(tags_arg):
    if not tags_arg:
        return ""
    tags = sorted({t.strip().lower() for t in tags_arg.split(",") if t.strip()})
    return ",".join(tags)


def _ticket_has_tag(ticket, tag):
    if not tag:
        return True
    tags = ticket["tags"] or ""
    target = tag.strip().lower()
    return f",{target}," in f",{tags},"


def _subtask_progress_label(progress):
    if not progress or progress["total"] == 0:
        return ""
    return f"[{progress['done']}/{progress['total']}]"


def _completion_bash_script():
    return """# bash completion for agentplan
_agentplan_completion() {
    local cur args out
    cur="${COMP_WORDS[COMP_CWORD]}"
    args=("${COMP_WORDS[@]:1:$COMP_CWORD}")
    out="$(agentplan __complete bash "$cur" "${args[@]}" 2>/dev/null)"
    COMPREPLY=($(compgen -W "$out" -- "$cur"))
}
complete -F _agentplan_completion agentplan
"""


def _completion_zsh_script():
    return """#compdef agentplan
_agentplan_completion() {
    local cur out
    cur="${words[CURRENT]}"
    out="$(agentplan __complete zsh "$cur" "${words[@]:2:$((CURRENT-2))}" 2>/dev/null)"
    compadd -- ${(f)out}
}
compdef _agentplan_completion agentplan
"""


def _completion_fish_script():
    return """function __agentplan_completion
    set -l tokens (commandline -opc)
    set -e tokens[1]
    set -l current (commandline -ct)
    if test (count $tokens) -gt 0
        set -e tokens[-1]
    end
    agentplan __complete fish "$current" $tokens
end
complete -c agentplan -f -a "(__agentplan_completion)"
"""


def _completion_project_slugs():
    try:
        return list_project_slugs()
    except Exception:
        return []


def _completion_filter(items, current):
    prefix = current or ""
    return [item for item in items if item.startswith(prefix)]


def _completion_suggestions(words, current):
    if not words:
        return _completion_filter(TOP_LEVEL_COMMANDS, current)

    command = words[0]
    if command == "completion":
        if len(words) == 1:
            return _completion_filter(COMPLETION_SHELLS, current)
        return []

    if command == "ticket":
        if len(words) == 1:
            return _completion_filter(TICKET_COMMANDS, current)
        if len(words) == 2 and words[1] in TICKET_COMMANDS:
            return _completion_filter(_completion_project_slugs(), current)
        return []

    if command == "subtask":
        if len(words) == 1:
            return _completion_filter(SUBTASK_COMMANDS, current)
        if len(words) == 2 and words[1] in SUBTASK_COMMANDS:
            return _completion_filter(_completion_project_slugs(), current)
        return []

    if command in PROJECT_TOP_LEVEL_COMMANDS and len(words) == 1:
        return _completion_filter(_completion_project_slugs(), current)

    return []


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_init(args):
    dir_path, db_path = get_db_path()
    os.makedirs(dir_path, exist_ok=True)
    conn = get_connection(db_path)
    init_db(conn)
    conn.commit()
    conn.close()
    print(f"Initialized agentplan database at {db_path}")


def cmd_create(args):
    _validate_len(args.title, MAX_TITLE_LEN, "Project title")
    _validate_len(args.notes, MAX_NOTES_LEN, "Notes")
    conn = _ensure(get_connection())
    slug = unique_slug(conn, slugify(args.title))
    conn.execute("INSERT INTO projects (slug, title, notes) VALUES (?,?,?)", (slug, args.title, args.notes))
    pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    n = 0
    for t in args.ticket or []:
        num = n + 1
        conn.execute(
            "INSERT INTO tickets (project_id, num, title) VALUES (?,?,?)",
            (pid, num, t),
        )
        ticket_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        _record_ticket_history(conn, ticket_id, None, "created")
        n += 1
    conn.commit()
    msg = f"Created project '{args.title}' ({slug})"
    if n:
        msg += f" with {n} ticket(s)"
    print(msg)
    conn.close()


def cmd_ticket_add(args):
    _validate_len(args.title, MAX_TITLE_LEN, "Ticket title")
    _validate_len(args.desc, MAX_DESC_LEN, "Description")
    _validate_len(args.notes, MAX_NOTES_LEN, "Notes")
    _validate_len(getattr(args, "tag", None), MAX_TAG_LEN, "Tags")
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    deps = []
    if args.depends:
        deps = [int(x.strip()) for x in args.depends.split(",")]
        for d in deps:
            resolve_ticket(conn, proj["id"], d, proj["slug"])
    num = _next_ticket_num(conn, proj["id"])
    tags = _parse_tags(args.tag)
    due_date = _parse_due_date(getattr(args, "due", None))
    conn.execute(
        "INSERT INTO tickets (project_id, num, title, description, priority, tags, depends_on, notes, due_date) VALUES (?,?,?,?,?,?,?,?,?)",
        (proj["id"], num, args.title, args.desc, args.priority or "none", tags, json.dumps(deps), args.notes, due_date),
    )
    ticket_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    _record_ticket_history(conn, ticket_id, None, "created")
    if deps:
        tickets = conn.execute("SELECT * FROM tickets WHERE project_id=?", (proj["id"],)).fetchall()
        if has_cycle(tickets, num, deps):
            conn.execute("DELETE FROM tickets WHERE project_id=? AND num=?", (proj["id"], num))
            conn.commit()
            conn.close()
            fail(
                "Circular dependency detected.",
                suggestions=["Remove one of the dependency links to break the cycle."],
            )
    # Reopen completed/abandoned projects when new tickets are added
    conn.execute(
        "UPDATE projects SET status='active', updated_at=? WHERE id=? AND status IN ('completed','abandoned','archived')",
        (_now(), proj["id"]),
    )
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    conn.commit()
    if proj["status"] in ("completed", "abandoned"):
        print(f"📂 Reopened project '{proj['slug']}' (was {proj['status']})")
    print(f"Added ticket #{num}: {args.title} [priority: {_priority_label(args.priority)}]")
    conn.close()


def cmd_ticket_update(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    t = resolve_ticket(conn, proj["id"], args.ticket_id, proj["slug"])

    updates = []
    values = []
    if args.title is not None:
        updates.append("title=?")
        values.append(args.title)
    if args.notes is not None:
        updates.append("notes=?")
        values.append(args.notes)
    if args.depends is not None:
        deps = [int(x.strip()) for x in args.depends.split(",") if x.strip()]
        for d in deps:
            resolve_ticket(conn, proj["id"], d, proj["slug"])
        tickets = conn.execute("SELECT * FROM tickets WHERE project_id=?", (proj["id"],)).fetchall()
        if has_cycle(tickets, t["num"], deps):
            conn.close()
            fail(
                "Circular dependency detected.",
                suggestions=["Adjust `--depends` so tickets do not reference each other in a loop."],
            )
        updates.append("depends_on=?")
        values.append(json.dumps(sorted(set(deps))))
    if args.priority is not None:
        updates.append("priority=?")
        values.append(args.priority)

    if not updates:
        conn.close()
        fail(
            "No updates provided.",
            suggestions=["Use at least one of: `--title`, `--notes`, `--depends`, `--priority`."],
        )

    values.append(t["id"])
    conn.execute(f"UPDATE tickets SET {', '.join(updates)} WHERE id=?", values)
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    conn.commit()
    print(f"Updated ticket #{t['num']}.")
    conn.close()


def cmd_ticket_edit(args):
    _validate_len(args.title, MAX_TITLE_LEN, "Ticket title")
    _validate_len(args.desc, MAX_DESC_LEN, "Description")
    _validate_len(getattr(args, "tag", None), MAX_TAG_LEN, "Tags")
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    t = resolve_ticket(conn, proj["id"], args.ticket_id, proj["slug"])

    updates = []
    values = []
    if args.title is not None:
        updates.append("title=?")
        values.append(args.title)
    if args.desc is not None:
        updates.append("description=?")
        values.append(args.desc)
    if args.priority is not None:
        updates.append("priority=?")
        values.append(args.priority)
    if args.tag is not None:
        updates.append("tags=?")
        values.append(_parse_tags(args.tag))
    if args.due is not None:
        updates.append("due_date=?")
        values.append(_parse_due_date(args.due))

    if not updates:
        conn.close()
        fail(
            "No updates provided.",
            suggestions=["Use at least one of: `--title`, `--desc`, `--priority`, `--tag`, `--due`."],
        )

    values.append(t["id"])
    conn.execute(f"UPDATE tickets SET {', '.join(updates)} WHERE id=?", values)
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    conn.commit()
    print(f"Updated ticket #{t['num']}.")
    conn.close()


def _expand_ticket_ids(ticket_ids):
    """Expand ticket ID args to support comma-separated values (e.g. 1,2,3)."""
    expanded = []
    for raw in ticket_ids:
        parts = [p.strip() for p in raw.split(",")]
        expanded.extend(p for p in parts if p)
    return expanded


def cmd_ticket_done(args):
    close_note = getattr(args, 'note', None)
    done_by = getattr(args, "agent", None)
    _validate_len(close_note, MAX_NOTES_LEN, "Close note")
    _validate_len(done_by, MAX_AGENT_LEN, "Agent name")
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    for num_str in _expand_ticket_ids(args.ticket_ids):
        t = resolve_ticket(conn, proj["id"], num_str, proj["slug"])
        conn.execute(
            "UPDATE tickets SET status='done', completed_at=?, close_note=?, done_by=? WHERE id=?",
            (_now(), close_note, done_by, t["id"])
        )
        _record_ticket_history(conn, t["id"], t["status"], "done")
        msg = f"✓ Ticket #{t['num']}: {t['title']} → done"
        if close_note:
            msg += f" [{close_note}]"
        if done_by:
            msg += f" (by {done_by})"
        print(msg)
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    was_active = proj["status"] == "active"
    if check_auto_complete(conn, proj["id"]) and was_active:
        print(f"🎉 All tickets done — project '{proj['slug']}' auto-completed!")
    conn.commit()
    conn.close()


def cmd_ticket_skip(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    for num_str in args.ticket_ids:
        t = resolve_ticket(conn, proj["id"], num_str, proj["slug"])
        conn.execute("UPDATE tickets SET status='skipped', completed_at=? WHERE id=?", (_now(), t["id"]))
        _record_ticket_history(conn, t["id"], t["status"], "skipped")
        print(f"⊘ Ticket #{t['num']}: {t['title']} → skipped")
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    check_auto_complete(conn, proj["id"])
    conn.commit()
    conn.close()


def cmd_ticket_start(args):
    started_by = getattr(args, "agent", None)
    _validate_len(started_by, MAX_AGENT_LEN, "Agent name")
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    t = resolve_ticket(conn, proj["id"], args.ticket_id, proj["slug"])
    conn.execute(
        "UPDATE tickets SET status='in-progress', started_by=? WHERE id=?",
        (started_by, t["id"]),
    )
    _record_ticket_history(conn, t["id"], t["status"], "started")
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    conn.commit()
    msg = f"▶ Ticket #{t['num']}: {t['title']} → in-progress"
    if started_by:
        msg += f" (by {started_by})"
    print(msg)
    conn.close()


def _claim_next_ticket(conn, project_id, started_by=None, tag=None):
    """Atomically claim the next unblocked pending ticket for a project."""
    tag_filter = (tag or "").strip().lower()
    conn.execute("BEGIN IMMEDIATE")
    try:
        tickets = conn.execute(
            "SELECT * FROM tickets WHERE project_id=? ORDER BY num", (project_id,)
        ).fetchall()
        done_nums = {t["num"] for t in tickets if t["status"] in ("done", "skipped")}
        candidates = [
            t for t in tickets
            if t["status"] == "pending"
            and not _is_blocked(t, done_nums)
            and _ticket_has_tag(t, tag_filter)
        ]
        candidates = _sort_next_items(candidates)
        if not candidates:
            conn.rollback()
            return None

        chosen = candidates[0]
        updated = conn.execute(
            "UPDATE tickets SET status='in-progress', started_by=? WHERE id=? AND status='pending'",
            (started_by, chosen["id"]),
        ).rowcount
        if updated != 1:
            conn.rollback()
            return None

        _record_ticket_history(conn, chosen["id"], chosen["status"], "started")
        conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), project_id))
        claimed = conn.execute("SELECT * FROM tickets WHERE id=?", (chosen["id"],)).fetchone()
        conn.commit()
        return claimed
    except Exception:
        conn.rollback()
        raise


def cmd_claim(args):
    _validate_len(getattr(args, "agent", None), MAX_AGENT_LEN, "Agent name")
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    claimed = _claim_next_ticket(
        conn,
        proj["id"],
        started_by=getattr(args, "agent", None),
        tag=getattr(args, "tag", None),
    )
    if not claimed:
        print("No unblocked tickets to claim.")
        conn.close()
        sys.exit(1)
    msg = f"▶ Claimed ticket #{claimed['num']}: {claimed['title']} → in-progress"
    if claimed["started_by"]:
        msg += f" (by {claimed['started_by']})"
    print(msg)
    conn.close()


def cmd_ticket_list(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    filt = args.status or "all"
    if filt == "all":
        tickets = conn.execute(
            "SELECT * FROM tickets WHERE project_id=? ORDER BY num", (proj["id"],)
        ).fetchall()
    else:
        tickets = conn.execute(
            "SELECT * FROM tickets WHERE project_id=? AND status=? ORDER BY num",
            (proj["id"], filt),
        ).fetchall()
    if not tickets:
        print("No tickets found.")
        conn.close()
        sys.exit(1)
    done_nums = {
        r["num"]
        for r in conn.execute(
            "SELECT num, status FROM tickets WHERE project_id=?", (proj["id"],)
        ).fetchall()
        if r["status"] in ("done", "skipped")
    }
    subtask_progress = _get_subtask_progress_map(conn, [t["id"] for t in tickets])
    for t in tickets:
        blocked = _is_blocked(t, done_nums)
        icon = _ticket_icon(t["status"], blocked)
        progress = _subtask_progress_label(subtask_progress.get(t["id"]))
        progress_segment = f" {progress}" if progress else ""
        line = f"  {icon} {t['num']}. {t['title']}{progress_segment} [priority: {_priority_label(t['priority'])}]"
        if t["status"] == "in-progress":
            line += " (in-progress)"
            if t["started_by"]:
                line += f" [started_by: {t['started_by']}]"
        elif blocked and t["status"] == "pending":
            deps = json.loads(t["depends_on"] or "[]")
            waiting = [str(d) for d in deps if d not in done_nums]
            line += f" (blocked — waiting on {', '.join(waiting)})"
        elif t["status"] == "done" and t["done_by"]:
            line += f" [done_by: {t['done_by']}]"
        print(line)
        if t["description"]:
            print(f"       Description: {t['description']}")
    conn.close()


def cmd_next(args):
    conn = _ensure(get_connection())
    fmt = args.format or "compact"
    tag_filter = (args.tag or "").strip().lower()
    if args.project:
        projects = [resolve_project(conn, args.project)]
    else:
        projects = conn.execute("SELECT * FROM projects WHERE status='active' ORDER BY id").fetchall()
    if not projects:
        print("No active projects.")
        conn.close()
        sys.exit(1)

    results = []
    for p in projects:
        tickets = conn.execute(
            "SELECT * FROM tickets WHERE project_id=? ORDER BY num", (p["id"],)
        ).fetchall()
        items = [t for t in tickets if t["status"] == "in-progress"] + get_unblocked(tickets)
        if tag_filter:
            items = [t for t in items if _ticket_has_tag(t, tag_filter)]
        items = _sort_next_items(items)
        if items:
            results.append((p, items))

    if not results:
        print("No unblocked tickets.")
        conn.close()
        sys.exit(1)

    if fmt == "json":
        payload = []
        for p, items in results:
            t = items[0]
            payload.append(
                {
                    "id": t["num"],
                    "title": t["title"],
                    "status": t["status"],
                    "project": p["slug"],
                }
            )
        if args.project:
            print(json.dumps(payload[0], ensure_ascii=False))
        else:
            print(json.dumps(payload, ensure_ascii=False))
        conn.close()
        return

    for p, items in results:
        parts = []
        for t in items:
            m = "▶" if t["status"] == "in-progress" else "○"
            parts.append(f"[{t['num']}] {t['title']} {m} (priority: {_priority_label(t['priority'])})")
        print(f"📋 {p['title']}: {', '.join(parts)}")
    conn.close()


def cmd_status(args):
    conn = _ensure(get_connection())
    fmt = args.format or "full"
    tag_filter = (args.tag or "").strip().lower()
    if args.project:
        projects = [resolve_project(conn, args.project)]
    else:
        projects = conn.execute("SELECT * FROM projects WHERE status='active' ORDER BY id").fetchall()
    if not projects:
        print("No active projects.")
        conn.close()
        sys.exit(1)
    for p in projects:
        all_tickets = conn.execute(
            "SELECT * FROM tickets WHERE project_id=? ORDER BY num", (p["id"],)
        ).fetchall()
        subtask_progress = _get_subtask_progress_map(conn, [t["id"] for t in all_tickets])
        tickets = [t for t in all_tickets if _ticket_has_tag(t, tag_filter)] if tag_filter else all_tickets
        done_nums = {t["num"] for t in all_tickets if t["status"] in ("done", "skipped")}
        done_count = sum(1 for t in tickets if t["status"] in ("done", "skipped"))
        total = len(tickets)
        open_tickets = [t for t in tickets if t["status"] in ("pending", "in-progress")]
        blocked_count = sum(1 for t in open_tickets if _is_blocked(t, done_nums))
        unblocked_open = [t for t in open_tickets if not _is_blocked(t, done_nums)]
        next_ticket = _sort_next_items(unblocked_open)[0] if unblocked_open else None

        if fmt == "json":
            data = {
                "id": p["id"], "slug": p["slug"], "title": p["title"],
                "status": p["status"], "notes": p["notes"],
                "done": done_count, "total": total,
                "blocked": blocked_count,
                "next": (
                    {"num": next_ticket["num"], "title": next_ticket["title"]}
                    if next_ticket
                    else None
                ),
                "tickets": [
                    {
                        **dict(t),
                        "subtasks_done": subtask_progress.get(t["id"], {}).get("done", 0),
                        "subtasks_total": subtask_progress.get(t["id"], {}).get("total", 0),
                    }
                    for t in tickets
                ],
            }
            print(json.dumps(data, indent=2))
            continue

        if fmt == "compact":
            items = _sort_next_items(unblocked_open)
            parts = []
            for t in items[:3]:
                progress = _subtask_progress_label(subtask_progress.get(t["id"]))
                progress_segment = f" {progress}" if progress else ""
                marker = "▶" if t["status"] == "in-progress" else "○"
                parts.append(
                    f"[{t['num']}] {t['title']}{progress_segment} {marker} ({_priority_label(t['priority'])})"
                )
            nxt = ", ".join(parts)
            line = f"📋 {p['title']}: {done_count}/{total} done"
            if nxt:
                line += f" | Next: {nxt}"
            print(line)
            continue

        # Full
        summary = f"{done_count}/{total} done, {blocked_count} blocked, next: "
        summary += f"[{next_ticket['num']}] {next_ticket['title']}" if next_ticket else "none"
        print(summary)
        print(f"{p['title']} [{p['status']}] — {done_count}/{total} done")
        for t in tickets:
            blocked = _is_blocked(t, done_nums)
            icon = _ticket_icon(t["status"], blocked)
            progress = _subtask_progress_label(subtask_progress.get(t["id"]))
            progress_segment = f" {progress}" if progress else ""
            line = f"  {icon} {t['num']}. {t['title']}{progress_segment} [priority: {_priority_label(t['priority'])}]"
            if t["status"] == "in-progress":
                line += " (in-progress)"
                if t["started_by"]:
                    line += f" [started_by: {t['started_by']}]"
            elif blocked and t["status"] == "pending":
                deps = json.loads(t["depends_on"] or "[]")
                waiting = [str(d) for d in deps if d not in done_nums]
                line += f" (blocked — waiting on {', '.join(waiting)})"
            elif t["status"] == "done" and t["done_by"]:
                line += f" [done_by: {t['done_by']}]"
            print(line)
            if t["description"]:
                print(f"       Description: {t['description']}")
            if t["status"] == "done" and t["close_note"]:
                print(f"       Note: {t['close_note']}")

        atts = conn.execute(
            "SELECT * FROM attachments WHERE project_id=? ORDER BY id", (p["id"],)
        ).fetchall()
        if atts:
            print("\n  📎 Attachments:")
            for a in atts:
                target = a["path"] or a["url"] or ""
                extra = f" (ticket #{a['ticket_id']})" if a["ticket_id"] else ""
                print(f"    {a['label']} → {target}{extra}")

        logs = conn.execute(
            "SELECT * FROM log WHERE project_id=? ORDER BY id DESC LIMIT 5", (p["id"],)
        ).fetchall()
        if logs:
            print("\n  📝 Recent log:")
            for l in reversed(logs):
                print(f"    {l['created_at'][:10]}: {l['entry']}")

        if p["notes"]:
            print(f"\n  Notes: {p['notes']}")
        print()
    conn.close()


def cmd_list(args):
    conn = _ensure(get_connection())
    if getattr(args, "all", False):
        projects = conn.execute("SELECT * FROM projects ORDER BY id").fetchall()
        filt = "all"
    else:
        filt = args.status or "active"
        if filt == "all":
            projects = conn.execute(
                "SELECT * FROM projects WHERE status!='archived' ORDER BY id"
            ).fetchall()
        else:
            projects = conn.execute(
                "SELECT * FROM projects WHERE status=? ORDER BY id", (filt,)
            ).fetchall()
    if not projects:
        if filt == "all":
            print("No projects.")
        else:
            print(f"No {filt} projects.")
        conn.close()
        sys.exit(1)
    for p in projects:
        rows = conn.execute(
            "SELECT status FROM tickets WHERE project_id=?", (p["id"],)
        ).fetchall()
        dc = sum(1 for r in rows if r["status"] in ("done", "skipped"))
        prog = f"{dc}/{len(rows)} done" if rows else "no tickets"
        print(f"  {p['slug']} [{p['status']}] — {prog}")
    conn.close()


def cmd_archive(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    if proj["status"] not in ("completed", "abandoned"):
        conn.close()
        fail(
            "Only completed or abandoned projects can be archived.",
            suggestions=["Run `agentplan close <project>` first (or `--abandon`) before archiving."],
        )
    conn.execute(
        "UPDATE projects SET status=?, updated_at=? WHERE id=?",
        ("archived", _now(), proj["id"]),
    )
    conn.commit()
    print(f"Archived project '{proj['slug']}'")
    conn.close()


def cmd_search(args):
    conn = _ensure(get_connection())
    query = (args.query or "").strip()
    if not query:
        conn.close()
        fail("Search query cannot be empty.", suggestions=["Run `agentplan search <text>` with a keyword."])

    like = f"%{query.lower()}%"
    rows = conn.execute(
        """
        SELECT
            p.slug AS project_slug,
            t.num AS ticket_num,
            t.title AS ticket_title
        FROM tickets t
        JOIN projects p ON p.id = t.project_id
        WHERE
            LOWER(t.title) LIKE ?
            OR LOWER(COALESCE(t.description, '')) LIKE ?
        ORDER BY p.slug, t.num
        """,
        (like, like),
    ).fetchall()
    if not rows:
        print("No matching tickets found.")
        conn.close()
        sys.exit(1)

    for row in rows:
        print(f"{row['project_slug']} #{row['ticket_num']}: {row['ticket_title']}")
    conn.close()


def cmd_attach(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    ticket_id = None
    if args.ticket:
        t = resolve_ticket(conn, proj["id"], args.ticket, proj["slug"])
        ticket_id = t["id"]
    loc = args.location
    is_url = loc.startswith(("http://", "https://"))
    conn.execute(
        "INSERT INTO attachments (project_id, ticket_id, label, path, url) VALUES (?,?,?,?,?)",
        (proj["id"], ticket_id, args.label, None if is_url else loc, loc if is_url else None),
    )
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    conn.commit()
    print(f"📎 Attached '{args.label}' → {loc}")
    conn.close()


def cmd_log(args):
    _validate_len(args.entry, MAX_LOG_ENTRY_LEN, "Log entry")
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    ticket_id = None
    if args.ticket:
        t = resolve_ticket(conn, proj["id"], args.ticket, proj["slug"])
        ticket_id = t["id"]
    conn.execute(
        "INSERT INTO log (project_id, ticket_id, entry) VALUES (?,?,?)",
        (proj["id"], ticket_id, args.entry),
    )
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    conn.commit()
    print(f"📝 Logged: {args.entry}")
    conn.close()


def cmd_close(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    st = "abandoned" if args.abandon else "completed"
    conn.execute("UPDATE projects SET status=?, updated_at=? WHERE id=?", (st, _now(), proj["id"]))
    conn.commit()
    print(f"{'Abandoned' if args.abandon else 'Completed'} project '{proj['slug']}'")
    conn.close()


def cmd_note(args):
    _validate_len(args.text, MAX_NOTES_LEN, "Note text")
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    if args.ticket:
        t = resolve_ticket(conn, proj["id"], args.ticket, proj["slug"])
        conn.execute("UPDATE tickets SET notes=? WHERE id=?", (args.text, t["id"]))
        conn.commit()
        print(f"Updated note on ticket #{t['num']}")
    else:
        conn.execute(
            "UPDATE projects SET notes=?, updated_at=? WHERE id=?",
            (args.text, _now(), proj["id"]),
        )
        conn.commit()
        print(f"Updated note on project '{proj['slug']}'")
    conn.close()


def cmd_depend(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    t = resolve_ticket(conn, proj["id"], args.ticket_id, proj["slug"])
    new_deps = [int(x.strip()) for x in args.on.split(",")]
    for d in new_deps:
        resolve_ticket(conn, proj["id"], d, proj["slug"])
    existing = json.loads(t["depends_on"] or "[]")
    merged = list(set(existing + new_deps))
    tickets = conn.execute("SELECT * FROM tickets WHERE project_id=?", (proj["id"],)).fetchall()
    if has_cycle(tickets, t["num"], merged):
        conn.close()
        fail(
            "Circular dependency detected.",
            suggestions=["Remove one of the dependency links to break the cycle."],
        )
    conn.execute("UPDATE tickets SET depends_on=? WHERE id=?", (json.dumps(sorted(merged)), t["id"]))
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    conn.commit()
    print(f"Ticket #{t['num']} now depends on: {sorted(merged)}")
    conn.close()


def cmd_undepend(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    t = resolve_ticket(conn, proj["id"], args.ticket_id, proj["slug"])
    dep_id = int(args.dep_id)
    resolve_ticket(conn, proj["id"], dep_id, proj["slug"])

    existing = json.loads(t["depends_on"] or "[]")
    if dep_id not in existing:
        conn.close()
        fail(
            f"Ticket #{t['num']} does not depend on ticket #{dep_id}.",
            suggestions=["Run `agentplan status <project>` to review current dependencies."],
        )

    updated = [d for d in existing if d != dep_id]
    conn.execute("UPDATE tickets SET depends_on=? WHERE id=?", (json.dumps(updated), t["id"]))
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    conn.commit()
    print(f"Removed dependency #{dep_id} from ticket #{t['num']}.")
    conn.close()


def cmd_remove(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    if args.ticket:
        t = resolve_ticket(conn, proj["id"], args.ticket, proj["slug"])
        tnum = t["num"]
        conn.execute("DELETE FROM tickets WHERE id=?", (t["id"],))
        # Clean up dangling deps
        others = conn.execute(
            "SELECT id, depends_on FROM tickets WHERE project_id=?", (proj["id"],)
        ).fetchall()
        for o in others:
            deps = json.loads(o["depends_on"] or "[]")
            if tnum in deps:
                deps.remove(tnum)
                conn.execute("UPDATE tickets SET depends_on=? WHERE id=?", (json.dumps(deps), o["id"]))
        conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
        conn.commit()
        print(f"Removed ticket #{tnum}: {t['title']}")
    else:
        slug = proj["slug"]
        conn.execute("DELETE FROM projects WHERE id=?", (proj["id"],))
        conn.commit()
        print(f"Removed project '{slug}'")
    conn.close()


def cmd_history(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    ticket = resolve_ticket(conn, proj["id"], args.ticket_id, proj["slug"])
    rows = conn.execute(
        "SELECT old_state, new_state, changed_at FROM ticket_history WHERE ticket_id=? ORDER BY id",
        (ticket["id"],),
    ).fetchall()
    if not rows:
        print(f"No history found for ticket #{ticket['num']}.")
        conn.close()
        return
    print(f"History for {proj['slug']} ticket #{ticket['num']}: {ticket['title']}")
    for row in rows:
        old_state = row["old_state"] if row["old_state"] is not None else "-"
        print(f"  {row['changed_at']} | {old_state} -> {row['new_state']}")
    conn.close()


def cmd_version(_args):
    print(f"agentplan {__version__}")

def cmd_dashboard(args):
    import socket
    import subprocess

    port = args.port

    if getattr(args, "stop", False):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            in_use = s.connect_ex(("127.0.0.1", port)) == 0
        if not in_use:
            print(f"No dashboard running on port {port}")
            return
        try:
            result = subprocess.run(
                f"lsof -ti:{port} | xargs kill",
                shell=True,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                print("Dashboard stopped")
            else:
                print(f"Failed to stop dashboard: {result.stderr.strip()}")
        except Exception as e:
            print(f"Error stopping dashboard: {e}")
        return

    try:
        from agentplan.dashboard import run_dashboard
    except ImportError:
        print('Error: Flask not installed. Run: pip install agentplan[dashboard]', file=__import__('sys').stderr)
        __import__("sys").exit(1)
    run_dashboard(host=args.host, port=args.port, open_browser=getattr(args, "open_browser", False))



def cmd_completion(args):
    scripts = {
        "bash": _completion_bash_script,
        "zsh": _completion_zsh_script,
        "fish": _completion_fish_script,
    }
    print(scripts[args.shell](), end="")


def cmd_internal_complete(args):
    suggestions = _completion_suggestions(args.words, args.current)
    print("\n".join(sorted(set(suggestions))))


def cmd_subtask_add(args):
    _validate_len(args.title, MAX_TITLE_LEN, "Subtask title")
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    ticket = resolve_ticket(conn, proj["id"], args.ticket_id, proj["slug"])
    num = _next_subtask_num(conn, ticket["id"])
    conn.execute(
        "INSERT INTO subtasks (ticket_id, num, title) VALUES (?,?,?)",
        (ticket["id"], num, args.title),
    )
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    conn.commit()
    print(f"Added subtask #{num} to ticket #{ticket['num']}: {args.title}")
    conn.close()


def cmd_subtask_done(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    ticket = resolve_ticket(conn, proj["id"], args.ticket_id, proj["slug"])
    subtask = resolve_subtask(conn, ticket["id"], args.subtask_id, ticket["num"], proj["slug"])
    conn.execute(
        "UPDATE subtasks SET status='done', completed_at=? WHERE id=?",
        (_now(), subtask["id"]),
    )
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    conn.commit()
    print(f"✓ Subtask #{subtask['num']} on ticket #{ticket['num']}: {subtask['title']} → done")
    conn.close()


def cmd_subtask_list(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    ticket = resolve_ticket(conn, proj["id"], args.ticket_id, proj["slug"])
    subtasks = conn.execute(
        "SELECT * FROM subtasks WHERE ticket_id=? ORDER BY num",
        (ticket["id"],),
    ).fetchall()
    if not subtasks:
        print(f"No subtasks found for ticket #{ticket['num']}.")
        conn.close()
        return
    for s in subtasks:
        icon = "✓" if s["status"] == "done" else "○"
        print(f"  {icon} {s['num']}. {s['title']}")
    conn.close()


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------

class FriendlyArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        fail(
            f"Invalid arguments: {message}",
            suggestions=["Run `agentplan --help` to see available commands and options."],
        )


def build_parser():
    p = FriendlyArgumentParser(prog="agentplan", description="Project management CLI for AI agents")
    p.add_argument("--version", action="version", version=f"agentplan {__version__}")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("init", help="Initialize database")
    sub.add_parser("version", help="Show version")

    dash_p = sub.add_parser("dashboard", help="Launch web dashboard")
    dash_p.add_argument("--port", type=int, default=5001, help="Port to listen on (default: 5001)")
    dash_p.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    dash_p.add_argument("--open", action="store_true", dest="open_browser", help="Open dashboard in default browser")
    dash_p.add_argument("--stop", action="store_true", help="Stop the running dashboard")

    c = sub.add_parser("create", help="Create a project")
    c.add_argument("title")
    c.add_argument("--ticket", action="append", help="Add inline ticket(s)")
    c.add_argument("--notes")

    tp = sub.add_parser("ticket", help="Manage tickets")
    ts = tp.add_subparsers(dest="ticket_command")
    a = ts.add_parser("add")
    a.add_argument("project"); a.add_argument("title"); a.add_argument("--desc"); a.add_argument("--depends"); a.add_argument("--notes")
    a.add_argument("--tag", help="Comma-separated tags (e.g. security,css)")
    a.add_argument("--priority", choices=PRIORITY_CHOICES[:-1], default="none")
    a.add_argument("--due", help="Due date in YYYY-MM-DD format")
    u = ts.add_parser("update")
    u.add_argument("project"); u.add_argument("ticket_id")
    u.add_argument("--title"); u.add_argument("--notes"); u.add_argument("--depends")
    u.add_argument("--priority", choices=PRIORITY_CHOICES)
    e = ts.add_parser("edit")
    e.add_argument("project"); e.add_argument("ticket_id")
    e.add_argument("--title"); e.add_argument("--desc"); e.add_argument("--tag")
    e.add_argument("--priority", choices=PRIORITY_CHOICES)
    e.add_argument("--due", help="Due date in YYYY-MM-DD format")
    d = ts.add_parser("done")
    d.add_argument("project"); d.add_argument("ticket_ids", nargs="+", help="Ticket IDs (space or comma-separated, e.g. 1 2 or 1,2,3)")
    d.add_argument("--note", help="Optional closing note/reason")
    d.add_argument("--agent", help="Agent name marking ticket done (e.g. dash)")
    s = ts.add_parser("skip")
    s.add_argument("project"); s.add_argument("ticket_ids", nargs="+")
    st = ts.add_parser("start")
    st.add_argument("project"); st.add_argument("ticket_id")
    st.add_argument("--agent", help="Agent name starting ticket (e.g. dash)")
    tl = ts.add_parser("list")
    tl.add_argument("project"); tl.add_argument("--status", choices=["pending", "done", "in-progress", "skipped", "all"])

    n = sub.add_parser("next", help="Show next unblocked tickets")
    n.add_argument("project", nargs="?")
    n.add_argument("--format", choices=["compact", "json"], default="compact")
    n.add_argument("--tag", help="Filter by a single tag")

    clm = sub.add_parser("claim", help="Atomically claim the next unblocked ticket in a project")
    clm.add_argument("project")
    clm.add_argument("--agent", help="Agent name claiming ticket (e.g. dash)")
    clm.add_argument("--tag", help="Filter by a single tag")

    ss = sub.add_parser("status", help="Project status")
    ss.add_argument("project", nargs="?")
    ss.add_argument("--format", choices=["compact", "full", "json"], default="full")
    ss.add_argument("--tag", help="Filter tickets by a single tag")

    srch = sub.add_parser("search", help="Search ticket titles and descriptions across all projects")
    srch.add_argument("query")

    ls = sub.add_parser("list", help="List projects")
    ls.add_argument("--status", choices=["active", "completed", "paused", "abandoned", "archived", "all"], default="active")
    ls.add_argument("--all", action="store_true", help="Include archived projects")

    ar = sub.add_parser("archive", help="Archive a completed or abandoned project")
    ar.add_argument("project")

    at = sub.add_parser("attach", help="Attach file or URL")
    at.add_argument("project"); at.add_argument("label"); at.add_argument("location"); at.add_argument("--ticket")

    lg = sub.add_parser("log", help="Add log entry")
    lg.add_argument("project"); lg.add_argument("entry"); lg.add_argument("--ticket")

    cl = sub.add_parser("close", help="Close a project")
    cl.add_argument("project"); cl.add_argument("--abandon", action="store_true")

    nt = sub.add_parser("note", help="Set note on project or ticket")
    nt.add_argument("project"); nt.add_argument("text"); nt.add_argument("--ticket")

    dp = sub.add_parser("depend", help="Add ticket dependencies")
    dp.add_argument("project"); dp.add_argument("ticket_id"); dp.add_argument("--on", required=True)

    udp = sub.add_parser("undepend", help="Remove a ticket dependency")
    udp.add_argument("project"); udp.add_argument("ticket_id"); udp.add_argument("--on", dest="dep_id", required=True, metavar="dep_id")

    rm = sub.add_parser("remove", help="Remove project or ticket")
    rm.add_argument("project"); rm.add_argument("--ticket")

    hs = sub.add_parser("history", help="Show ticket state transition history")
    hs.add_argument("project")
    hs.add_argument("ticket_id")

    sp = sub.add_parser("subtask", help="Manage ticket subtasks")
    sps = sp.add_subparsers(dest="subtask_command")
    sa = sps.add_parser("add")
    sa.add_argument("project"); sa.add_argument("ticket_id"); sa.add_argument("title")
    sd = sps.add_parser("done")
    sd.add_argument("project"); sd.add_argument("ticket_id"); sd.add_argument("subtask_id")
    sl = sps.add_parser("list")
    sl.add_argument("project"); sl.add_argument("ticket_id")

    cp = sub.add_parser("completion", help="Print shell completion script")
    cp.add_argument("shell", choices=COMPLETION_SHELLS)

    internal = sub.add_parser("__complete", help=argparse.SUPPRESS)
    internal.add_argument("shell", choices=COMPLETION_SHELLS, help=argparse.SUPPRESS)
    internal.add_argument("current", help=argparse.SUPPRESS)
    internal.add_argument("words", nargs="*", help=argparse.SUPPRESS)

    return p


DISPATCH = {
    "init": cmd_init, "create": cmd_create, "next": cmd_next, "claim": cmd_claim, "status": cmd_status,
    "list": cmd_list, "search": cmd_search, "attach": cmd_attach, "log": cmd_log, "close": cmd_close,
    "archive": cmd_archive,
    "note": cmd_note, "depend": cmd_depend, "undepend": cmd_undepend, "remove": cmd_remove, "history": cmd_history, "version": cmd_version, "dashboard": cmd_dashboard,
    "completion": cmd_completion, "__complete": cmd_internal_complete,
}

TICKET_DISPATCH = {
    "add": cmd_ticket_add, "done": cmd_ticket_done, "skip": cmd_ticket_skip,
    "start": cmd_ticket_start, "list": cmd_ticket_list,
    "update": cmd_ticket_update, "edit": cmd_ticket_edit,
}

SUBTASK_DISPATCH = {
    "add": cmd_subtask_add,
    "done": cmd_subtask_done,
    "list": cmd_subtask_list,
}


def main():
    parser = build_parser()
    try:
        args = parser.parse_args()
        if not args.command:
            parser.print_help()
            fail(
                "No command provided.",
                suggestions=["Run `agentplan --help` to see available commands."],
            )
        if args.command == "ticket":
            if not getattr(args, "ticket_command", None):
                parser.parse_args(["ticket", "--help"])
            TICKET_DISPATCH[args.ticket_command](args)
        elif args.command == "subtask":
            if not getattr(args, "subtask_command", None):
                parser.parse_args(["subtask", "--help"])
            SUBTASK_DISPATCH[args.subtask_command](args)
        else:
            DISPATCH[args.command](args)
    except CliError as e:
        print(f"Error: {e.message}", file=sys.stderr)
        for suggestion in e.suggestions:
            print(f"Suggestion: {suggestion}", file=sys.stderr)
        sys.exit(e.exit_code)
    except SystemExit:
        raise
    except Exception as e:
        print("Error: Unexpected failure while running agentplan.", file=sys.stderr)
        print(f"Suggestion: Re-run with valid arguments or `agentplan --help`. ({e})", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
