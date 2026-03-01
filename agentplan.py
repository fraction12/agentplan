#!/usr/bin/env python3
"""agentplan — Project management CLI for AI agents."""

import argparse
import difflib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime

__version__ = "0.2.0"
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2, "none": 3}
PRIORITY_CHOICES = ["high", "medium", "low", "none"]


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
# Database helpers
# ---------------------------------------------------------------------------

def get_db_path():
    dir_path = os.environ.get("AGENTPLAN_DIR", os.path.expanduser("~/.agentplan"))
    db_path = os.environ.get("AGENTPLAN_DB", os.path.join(dir_path, "agentplan.db"))
    return dir_path, db_path


def get_connection(db_path=None):
    if db_path is None:
        dir_path, db_path = get_db_path()
        os.makedirs(dir_path, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            num INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            priority TEXT NOT NULL DEFAULT 'none',
            tags TEXT NOT NULL DEFAULT '',
            depends_on TEXT DEFAULT '[]',
            notes TEXT,
            started_by TEXT,
            done_by TEXT,
            due_date TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
            completed_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_ticket_project_num ON tickets(project_id, num);
        CREATE TABLE IF NOT EXISTS ticket_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
            old_state TEXT,
            new_state TEXT NOT NULL,
            changed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_ticket_history_ticket_id ON ticket_history(ticket_id, id);
        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            ticket_id INTEGER REFERENCES tickets(id) ON DELETE CASCADE,
            label TEXT NOT NULL,
            path TEXT,
            url TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            ticket_id INTEGER REFERENCES tickets(id) ON DELETE CASCADE,
            entry TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS subtasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
            num INTEGER NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
            completed_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_subtask_ticket_num ON subtasks(ticket_id, num);
    """)
    # Migration: add num column if missing (upgrade from 0.1.0)
    try:
        conn.execute("SELECT num FROM tickets LIMIT 0")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE tickets ADD COLUMN num INTEGER")
        # Backfill: assign sequential nums per project
        projects = conn.execute("SELECT DISTINCT project_id FROM tickets").fetchall()
        for p in projects:
            rows = conn.execute(
                "SELECT id FROM tickets WHERE project_id=? ORDER BY id", (p[0],)
            ).fetchall()
            for i, r in enumerate(rows, 1):
                conn.execute("UPDATE tickets SET num=? WHERE id=?", (i, r[0]))
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_ticket_project_num ON tickets(project_id, num)
        """)
        conn.commit()
    # Migration: add priority column if missing (upgrade from pre-priority schema)
    try:
        conn.execute("SELECT priority FROM tickets LIMIT 0")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE tickets ADD COLUMN priority TEXT NOT NULL DEFAULT 'none'")
        conn.execute("UPDATE tickets SET priority='none' WHERE priority IS NULL OR priority=''")
        conn.commit()
    # Migration: add close_note column if missing
    try:
        conn.execute("SELECT close_note FROM tickets LIMIT 0")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE tickets ADD COLUMN close_note TEXT")
        conn.commit()
    # Migration: add tags column if missing
    try:
        conn.execute("SELECT tags FROM tickets LIMIT 0")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE tickets ADD COLUMN tags TEXT NOT NULL DEFAULT ''")
        conn.execute("UPDATE tickets SET tags='' WHERE tags IS NULL")
        conn.commit()
    # Migration: add started_by column if missing
    try:
        conn.execute("SELECT started_by FROM tickets LIMIT 0")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE tickets ADD COLUMN started_by TEXT")
        conn.commit()
    # Migration: add done_by column if missing
    try:
        conn.execute("SELECT done_by FROM tickets LIMIT 0")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE tickets ADD COLUMN done_by TEXT")
        conn.commit()
    # Migration: add description column if missing
    try:
        conn.execute("SELECT description FROM tickets LIMIT 0")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE tickets ADD COLUMN description TEXT")
        conn.commit()
    # Migration: add due_date column if missing
    try:
        conn.execute("SELECT due_date FROM tickets LIMIT 0")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE tickets ADD COLUMN due_date TEXT")
        conn.commit()
    # Migration: create subtasks table/index if missing
    conn.execute("""
        CREATE TABLE IF NOT EXISTS subtasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
            num INTEGER NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
            completed_at TEXT
        )
    """)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_subtask_ticket_num ON subtasks(ticket_id, num)")
    conn.commit()


def _now():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _ensure(conn):
    """Auto-init tables so every command works without explicit init."""
    init_db(conn)
    return conn


def _next_ticket_num(conn, project_id):
    """Get next ticket number for a project (1-based, sequential)."""
    row = conn.execute(
        "SELECT MAX(num) FROM tickets WHERE project_id=?", (project_id,)
    ).fetchone()
    return (row[0] or 0) + 1


def _next_subtask_num(conn, ticket_id):
    """Get next subtask number for a ticket (1-based, sequential)."""
    row = conn.execute(
        "SELECT MAX(num) FROM subtasks WHERE ticket_id=?", (ticket_id,)
    ).fetchone()
    return (row[0] or 0) + 1


def _record_ticket_history(conn, ticket_id, old_state, new_state):
    conn.execute(
        "INSERT INTO ticket_history (ticket_id, old_state, new_state, changed_at) VALUES (?,?,?,?)",
        (ticket_id, old_state, new_state, _now()),
    )


# ---------------------------------------------------------------------------
# Slugify
# ---------------------------------------------------------------------------

def slugify(title):
    s = title.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s]+", "-", s.strip())
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:60] or "project"


def unique_slug(conn, base):
    slug = base
    i = 2
    while conn.execute("SELECT 1 FROM projects WHERE slug=?", (slug,)).fetchone():
        slug = f"{base[:57]}-{i}"
        i += 1
    return slug


# ---------------------------------------------------------------------------
# Resolve helpers
# ---------------------------------------------------------------------------

def resolve_project(conn, ident):
    row = conn.execute("SELECT * FROM projects WHERE slug=?", (ident,)).fetchone()
    if not row:
        try:
            row = conn.execute("SELECT * FROM projects WHERE id=?", (int(ident),)).fetchone()
        except (ValueError, TypeError):
            pass
    if not row:
        slugs = [r["slug"] for r in conn.execute("SELECT slug FROM projects ORDER BY slug").fetchall()]
        suggestions = []
        close_matches = difflib.get_close_matches(str(ident), slugs, n=1, cutoff=0.6)
        if close_matches:
            suggestions.append(f"Did you mean '{close_matches[0]}'?")
        suggestions.append("Run `agentplan list --all` to see all projects.")
        fail(f"Project '{ident}' not found.", suggestions=suggestions)
    return row


def resolve_ticket(conn, project_id, num_str, slug=""):
    """Resolve a ticket by its per-project number."""
    try:
        num = int(num_str)
    except (ValueError, TypeError):
        fail(
            f"Invalid ticket number '{num_str}'.",
            suggestions=[
                "Ticket IDs must be numeric (for example: `1` or `2`).",
                f"Run `agentplan ticket list {slug or '<project>'}` to see ticket IDs.",
            ],
        )
    row = conn.execute(
        "SELECT * FROM tickets WHERE project_id=? AND num=?", (project_id, num)
    ).fetchone()
    if not row:
        fail(
            f"Ticket #{num} not found in project '{slug}'.",
            suggestions=[f"Run `agentplan ticket list {slug}` to see available ticket IDs."],
        )
    return row


def resolve_subtask(conn, ticket_id, num_str, ticket_num, slug=""):
    """Resolve a subtask by its per-ticket number."""
    try:
        num = int(num_str)
    except (ValueError, TypeError):
        fail(
            f"Invalid subtask number '{num_str}'.",
            suggestions=[
                "Subtask IDs must be numeric (for example: `1`).",
                f"Run `agentplan subtask list {slug or '<project>'} {ticket_num}` to see subtask IDs.",
            ],
        )
    row = conn.execute(
        "SELECT * FROM subtasks WHERE ticket_id=? AND num=?", (ticket_id, num)
    ).fetchone()
    if not row:
        fail(
            f"Subtask #{num} not found for ticket #{ticket_num} in project '{slug}'.",
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


def check_auto_complete(conn, project_id):
    rows = conn.execute("SELECT status FROM tickets WHERE project_id=?", (project_id,)).fetchall()
    if rows and all(r["status"] in ("done", "skipped") for r in rows):
        conn.execute(
            "UPDATE projects SET status='completed', updated_at=? WHERE id=? AND status='active'",
            (_now(), project_id),
        )
        return True
    return False


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


def _get_subtask_progress_map(conn, ticket_ids):
    if not ticket_ids:
        return {}
    placeholders = ",".join("?" for _ in ticket_ids)
    rows = conn.execute(
        f"""
        SELECT
            ticket_id,
            COUNT(*) AS total,
            SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) AS done
        FROM subtasks
        WHERE ticket_id IN ({placeholders})
        GROUP BY ticket_id
        """,
        ticket_ids,
    ).fetchall()
    return {
        row["ticket_id"]: {"done": int(row["done"] or 0), "total": int(row["total"] or 0)}
        for row in rows
    }


def _subtask_progress_label(progress):
    if not progress or progress["total"] == 0:
        return ""
    return f"[{progress['done']}/{progress['total']}]"


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
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    close_note = getattr(args, 'note', None)
    done_by = getattr(args, "agent", None)
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
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    t = resolve_ticket(conn, proj["id"], args.ticket_id, proj["slug"])
    started_by = getattr(args, "agent", None)
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


def cmd_subtask_add(args):
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

    return p


DISPATCH = {
    "init": cmd_init, "create": cmd_create, "next": cmd_next, "claim": cmd_claim, "status": cmd_status,
    "list": cmd_list, "search": cmd_search, "attach": cmd_attach, "log": cmd_log, "close": cmd_close,
    "archive": cmd_archive,
    "note": cmd_note, "depend": cmd_depend, "remove": cmd_remove, "history": cmd_history, "version": cmd_version,
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
