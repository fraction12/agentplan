"""Database layer for agentplan."""

import difflib
import json
import os
import sqlite3
from datetime import datetime

from models import HistoryEntry, Project, Subtask, Ticket


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
    conn.executescript(
        """
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
    """
    )

    try:
        conn.execute("SELECT num FROM tickets LIMIT 0")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE tickets ADD COLUMN num INTEGER")
        projects = conn.execute("SELECT DISTINCT project_id FROM tickets").fetchall()
        for p in projects:
            rows = conn.execute("SELECT id FROM tickets WHERE project_id=? ORDER BY id", (p[0],)).fetchall()
            for i, r in enumerate(rows, 1):
                conn.execute("UPDATE tickets SET num=? WHERE id=?", (i, r[0]))
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_ticket_project_num ON tickets(project_id, num)")
        conn.commit()

    migrations = [
        ("priority", "ALTER TABLE tickets ADD COLUMN priority TEXT NOT NULL DEFAULT 'none'", "UPDATE tickets SET priority='none' WHERE priority IS NULL OR priority=''") ,
        ("close_note", "ALTER TABLE tickets ADD COLUMN close_note TEXT", None),
        ("tags", "ALTER TABLE tickets ADD COLUMN tags TEXT NOT NULL DEFAULT ''", "UPDATE tickets SET tags='' WHERE tags IS NULL"),
        ("started_by", "ALTER TABLE tickets ADD COLUMN started_by TEXT", None),
        ("done_by", "ALTER TABLE tickets ADD COLUMN done_by TEXT", None),
        ("description", "ALTER TABLE tickets ADD COLUMN description TEXT", None),
        ("due_date", "ALTER TABLE tickets ADD COLUMN due_date TEXT", None),
    ]
    for col, alter_sql, fix_sql in migrations:
        try:
            conn.execute(f"SELECT {col} FROM tickets LIMIT 0")
        except sqlite3.OperationalError:
            conn.execute(alter_sql)
            if fix_sql:
                conn.execute(fix_sql)
            conn.commit()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS subtasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
            num INTEGER NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
            completed_at TEXT
        )
        """
    )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_subtask_ticket_num ON subtasks(ticket_id, num)")
    conn.commit()


def now():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def ensure(conn):
    init_db(conn)
    return conn


def next_ticket_num(conn, project_id):
    row = conn.execute("SELECT MAX(num) FROM tickets WHERE project_id=?", (project_id,)).fetchone()
    return (row[0] or 0) + 1


def next_subtask_num(conn, ticket_id):
    row = conn.execute("SELECT MAX(num) FROM subtasks WHERE ticket_id=?", (ticket_id,)).fetchone()
    return (row[0] or 0) + 1


def record_ticket_history(conn, ticket_id, old_state, new_state):
    conn.execute(
        "INSERT INTO ticket_history (ticket_id, old_state, new_state, changed_at) VALUES (?,?,?,?)",
        (ticket_id, old_state, new_state, now()),
    )


def unique_slug(conn, base):
    slug = base
    i = 2
    while conn.execute("SELECT 1 FROM projects WHERE slug=?", (slug,)).fetchone():
        slug = f"{base[:57]}-{i}"
        i += 1
    return slug


def resolve_project(conn, ident):
    row = conn.execute("SELECT * FROM projects WHERE slug=?", (ident,)).fetchone()
    if not row:
        try:
            row = conn.execute("SELECT * FROM projects WHERE id=?", (int(ident),)).fetchone()
        except (ValueError, TypeError):
            pass
    return row


def project_slug_suggestions(conn, ident):
    slugs = [r["slug"] for r in conn.execute("SELECT slug FROM projects ORDER BY slug").fetchall()]
    return difflib.get_close_matches(str(ident), slugs, n=1, cutoff=0.6)


def resolve_ticket(conn, project_id, num_str):
    try:
        num = int(num_str)
    except (ValueError, TypeError):
        return None
    return conn.execute("SELECT * FROM tickets WHERE project_id=? AND num=?", (project_id, num)).fetchone()


def resolve_subtask(conn, ticket_id, num_str):
    try:
        num = int(num_str)
    except (ValueError, TypeError):
        return None
    return conn.execute("SELECT * FROM subtasks WHERE ticket_id=? AND num=?", (ticket_id, num)).fetchone()


def project_tickets(conn, project_id):
    return conn.execute("SELECT * FROM tickets WHERE project_id=? ORDER BY num", (project_id,)).fetchall()


def tickets_by_status(conn, project_id, status):
    if status == "all":
        return project_tickets(conn, project_id)
    return conn.execute("SELECT * FROM tickets WHERE project_id=? AND status=? ORDER BY num", (project_id, status)).fetchall()


def list_project_slugs():
    conn = get_connection()
    try:
        return [row["slug"] for row in conn.execute("SELECT slug FROM projects ORDER BY slug").fetchall()]
    finally:
        conn.close()


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


def has_cycle(tickets, ticket_num, new_deps):
    adj = {t["num"]: json.loads(t["depends_on"] or "[]") for t in tickets}
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


def check_auto_complete(conn, project_id):
    rows = conn.execute("SELECT status FROM tickets WHERE project_id=?", (project_id,)).fetchall()
    if rows and all(r["status"] in ("done", "skipped") for r in rows):
        conn.execute("UPDATE projects SET status='completed', updated_at=? WHERE id=? AND status='active'", (now(), project_id))
        return True
    return False


def get_subtask_progress_map(conn, ticket_ids):
    if not ticket_ids:
        return {}
    placeholders = ",".join("?" for _ in ticket_ids)
    rows = conn.execute(
        f"""
        SELECT ticket_id, COUNT(*) AS total, SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) AS done
        FROM subtasks
        WHERE ticket_id IN ({placeholders})
        GROUP BY ticket_id
        """,
        ticket_ids,
    ).fetchall()
    return {row["ticket_id"]: {"done": int(row["done"] or 0), "total": int(row["total"] or 0)} for row in rows}
