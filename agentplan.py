#!/usr/bin/env python3
"""agentplan — Project management CLI for AI agents."""

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime

__version__ = "0.1.1"


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
            status TEXT NOT NULL DEFAULT 'pending',
            depends_on TEXT DEFAULT '[]',
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
            completed_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_ticket_project_num ON tickets(project_id, num);
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
        print(f"Error: Project '{ident}' not found.", file=sys.stderr)
        sys.exit(2)
    return row


def resolve_ticket(conn, project_id, num_str, slug=""):
    """Resolve a ticket by its per-project number."""
    try:
        num = int(num_str)
    except (ValueError, TypeError):
        print(f"Error: Invalid ticket number '{num_str}'.", file=sys.stderr)
        sys.exit(2)
    row = conn.execute(
        "SELECT * FROM tickets WHERE project_id=? AND num=?", (project_id, num)
    ).fetchone()
    if not row:
        print(f"Error: Ticket #{num} not found in project '{slug}'.", file=sys.stderr)
        sys.exit(2)
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
    conn.execute(
        "INSERT INTO tickets (project_id, num, title, depends_on, notes) VALUES (?,?,?,?,?)",
        (proj["id"], num, args.title, json.dumps(deps), args.notes),
    )
    if deps:
        tickets = conn.execute("SELECT * FROM tickets WHERE project_id=?", (proj["id"],)).fetchall()
        if has_cycle(tickets, num, deps):
            conn.execute("DELETE FROM tickets WHERE project_id=? AND num=?", (proj["id"], num))
            conn.commit()
            conn.close()
            print("Error: Circular dependency detected.", file=sys.stderr)
            sys.exit(2)
    # Reopen completed/abandoned projects when new tickets are added
    conn.execute(
        "UPDATE projects SET status='active', updated_at=? WHERE id=? AND status IN ('completed','abandoned')",
        (_now(), proj["id"]),
    )
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    conn.commit()
    if proj["status"] in ("completed", "abandoned"):
        print(f"📂 Reopened project '{proj['slug']}' (was {proj['status']})")
    print(f"Added ticket #{num}: {args.title}")
    conn.close()


def cmd_ticket_done(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    for num_str in args.ticket_ids:
        t = resolve_ticket(conn, proj["id"], num_str, proj["slug"])
        conn.execute("UPDATE tickets SET status='done', completed_at=? WHERE id=?", (_now(), t["id"]))
        print(f"✓ Ticket #{t['num']}: {t['title']} → done")
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
        print(f"⊘ Ticket #{t['num']}: {t['title']} → skipped")
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    check_auto_complete(conn, proj["id"])
    conn.commit()
    conn.close()


def cmd_ticket_start(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    t = resolve_ticket(conn, proj["id"], args.ticket_id, proj["slug"])
    conn.execute("UPDATE tickets SET status='in-progress' WHERE id=?", (t["id"],))
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    conn.commit()
    print(f"▶ Ticket #{t['num']}: {t['title']} → in-progress")
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
    for t in tickets:
        blocked = _is_blocked(t, done_nums)
        icon = _ticket_icon(t["status"], blocked)
        line = f"  {icon} {t['num']}. {t['title']}"
        if t["status"] == "in-progress":
            line += " (in-progress)"
        elif blocked and t["status"] == "pending":
            deps = json.loads(t["depends_on"] or "[]")
            waiting = [str(d) for d in deps if d not in done_nums]
            line += f" (blocked — waiting on {', '.join(waiting)})"
        print(line)
    conn.close()


def cmd_next(args):
    conn = _ensure(get_connection())
    if args.project:
        projects = [resolve_project(conn, args.project)]
    else:
        projects = conn.execute("SELECT * FROM projects WHERE status='active' ORDER BY id").fetchall()
    if not projects:
        print("No active projects.")
        conn.close()
        sys.exit(1)
    found = False
    for p in projects:
        tickets = conn.execute(
            "SELECT * FROM tickets WHERE project_id=? ORDER BY num", (p["id"],)
        ).fetchall()
        items = [t for t in tickets if t["status"] == "in-progress"] + get_unblocked(tickets)
        if items:
            found = True
            parts = []
            for t in items:
                m = "▶" if t["status"] == "in-progress" else "○"
                parts.append(f"[{t['num']}] {t['title']} {m}")
            print(f"📋 {p['title']}: {', '.join(parts)}")
    if not found:
        print("No unblocked tickets.")
        conn.close()
        sys.exit(1)
    conn.close()


def cmd_status(args):
    conn = _ensure(get_connection())
    fmt = args.format or "full"
    if args.project:
        projects = [resolve_project(conn, args.project)]
    else:
        projects = conn.execute("SELECT * FROM projects WHERE status='active' ORDER BY id").fetchall()
    if not projects:
        print("No active projects.")
        conn.close()
        sys.exit(1)
    for p in projects:
        tickets = conn.execute(
            "SELECT * FROM tickets WHERE project_id=? ORDER BY num", (p["id"],)
        ).fetchall()
        done_count = sum(1 for t in tickets if t["status"] in ("done", "skipped"))
        total = len(tickets)
        done_nums = {t["num"] for t in tickets if t["status"] in ("done", "skipped")}

        if fmt == "json":
            data = {
                "id": p["id"], "slug": p["slug"], "title": p["title"],
                "status": p["status"], "notes": p["notes"],
                "done": done_count, "total": total,
                "tickets": [dict(t) for t in tickets],
            }
            print(json.dumps(data, indent=2))
            continue

        if fmt == "compact":
            items = [t for t in tickets if t["status"] == "in-progress"] + get_unblocked(tickets)
            nxt = ", ".join(
                f"[{t['num']}] {t['title']} {'▶' if t['status']=='in-progress' else '○'}"
                for t in items[:3]
            )
            line = f"📋 {p['title']}: {done_count}/{total} done"
            if nxt:
                line += f" | Next: {nxt}"
            print(line)
            continue

        # Full
        print(f"{p['title']} [{p['status']}] — {done_count}/{total} done")
        for t in tickets:
            blocked = _is_blocked(t, done_nums)
            icon = _ticket_icon(t["status"], blocked)
            line = f"  {icon} {t['num']}. {t['title']}"
            if t["status"] == "in-progress":
                line += " (in-progress)"
            elif blocked and t["status"] == "pending":
                deps = json.loads(t["depends_on"] or "[]")
                waiting = [str(d) for d in deps if d not in done_nums]
                line += f" (blocked — waiting on {', '.join(waiting)})"
            print(line)

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
    filt = args.status or "active"
    if filt == "all":
        projects = conn.execute("SELECT * FROM projects ORDER BY id").fetchall()
    else:
        projects = conn.execute(
            "SELECT * FROM projects WHERE status=? ORDER BY id", (filt,)
        ).fetchall()
    if not projects:
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
        print("Error: Circular dependency detected.", file=sys.stderr)
        conn.close()
        sys.exit(2)
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


def cmd_version(_args):
    print(f"agentplan {__version__}")


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(prog="agentplan", description="Project management CLI for AI agents")
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
    a.add_argument("project"); a.add_argument("title"); a.add_argument("--depends"); a.add_argument("--notes")
    d = ts.add_parser("done")
    d.add_argument("project"); d.add_argument("ticket_ids", nargs="+")
    s = ts.add_parser("skip")
    s.add_argument("project"); s.add_argument("ticket_ids", nargs="+")
    st = ts.add_parser("start")
    st.add_argument("project"); st.add_argument("ticket_id")
    tl = ts.add_parser("list")
    tl.add_argument("project"); tl.add_argument("--status", choices=["pending", "done", "in-progress", "skipped", "all"])

    n = sub.add_parser("next", help="Show next unblocked tickets")
    n.add_argument("project", nargs="?")

    ss = sub.add_parser("status", help="Project status")
    ss.add_argument("project", nargs="?")
    ss.add_argument("--format", choices=["compact", "full", "json"], default="full")

    ls = sub.add_parser("list", help="List projects")
    ls.add_argument("--status", choices=["active", "completed", "paused", "abandoned", "all"], default="active")

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

    return p


DISPATCH = {
    "init": cmd_init, "create": cmd_create, "next": cmd_next, "status": cmd_status,
    "list": cmd_list, "attach": cmd_attach, "log": cmd_log, "close": cmd_close,
    "note": cmd_note, "depend": cmd_depend, "remove": cmd_remove, "version": cmd_version,
}

TICKET_DISPATCH = {
    "add": cmd_ticket_add, "done": cmd_ticket_done, "skip": cmd_ticket_skip,
    "start": cmd_ticket_start, "list": cmd_ticket_list,
}


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(2)
    try:
        if args.command == "ticket":
            if not getattr(args, "ticket_command", None):
                parser.parse_args(["ticket", "--help"])
            TICKET_DISPATCH[args.ticket_command](args)
        else:
            DISPATCH[args.command](args)
    except SystemExit:
        raise
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
