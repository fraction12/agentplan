"""Database layer for agentplan."""

import difflib
import json
import os
import sqlite3
from datetime import datetime

from agentplan.models import Role


VALID_TICKET_STATES = {"pending", "in-progress", "done", "skipped", "blocked", "failed", "needs-review"}

VALID_TRANSITIONS = {
    "pending": {"in-progress", "done", "skipped", "blocked"},
    "in-progress": {"done", "failed", "needs-review", "blocked", "pending"},
    "blocked": {"pending", "in-progress"},
    "failed": {"pending", "in-progress"},
    "needs-review": {"done", "in-progress", "failed"},
    "done": set(),
    "skipped": set(),
}


def validate_transition(from_state, to_state):
    if from_state not in VALID_TICKET_STATES:
        return False, f"Unknown source state: {from_state}"
    if to_state not in VALID_TICKET_STATES:
        return False, f"Unknown target state: {to_state}"
    if from_state == to_state:
        return True, ""
    allowed = VALID_TRANSITIONS.get(from_state, set())
    if to_state in allowed:
        return True, ""
    if not allowed:
        return False, f"Cannot transition from terminal state '{from_state}' to '{to_state}'."
    return False, f"Invalid transition: '{from_state}' -> '{to_state}'. Allowed: {', '.join(sorted(allowed))}."


def get_db_path():
    dir_path = os.environ.get("AGENTPLAN_DIR", os.path.expanduser("~/.agentplan"))
    db_path = os.environ.get("AGENTPLAN_DB", os.path.join(dir_path, "agentplan.db"))
    return dir_path, db_path


def get_connection(db_path=None):
    if db_path is None:
        dir_path, db_path = get_db_path()
        os.makedirs(dir_path, exist_ok=True)
    is_new = not os.path.exists(db_path)
    conn = sqlite3.connect(db_path)
    if is_new and os.path.exists(db_path):
        os.chmod(db_path, 0o600)
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
            dir TEXT,
            timeout_sec INTEGER,
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
            claimed_at TEXT,
            claim_timeout INTEGER,
            timeout_sec INTEGER,
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
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS hooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            event TEXT NOT NULL DEFAULT 'on-complete',
            hook_type TEXT NOT NULL,
            target TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            command_template TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS agent_roles (
            agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
            role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            PRIMARY KEY (agent_id, role_id)
        );

        CREATE TABLE IF NOT EXISTS chain_state (
            project_id INTEGER PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
            status TEXT NOT NULL,
            current_ticket_id INTEGER REFERENCES tickets(id) ON DELETE SET NULL,
            pause_reason TEXT,
            heartbeat_at TEXT,
            deadline_at TEXT,
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime'))
        );
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
        ("claimed_at", "ALTER TABLE tickets ADD COLUMN claimed_at TEXT", None),
        ("claim_timeout", "ALTER TABLE tickets ADD COLUMN claim_timeout INTEGER", None),
        ("timeout_sec", "ALTER TABLE tickets ADD COLUMN timeout_sec INTEGER", None),
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            event TEXT NOT NULL DEFAULT 'on-complete',
            hook_type TEXT NOT NULL,
            target TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime'))
        )
        """)


    try:
        conn.execute("SELECT priority FROM agents LIMIT 0")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE agents ADD COLUMN priority INTEGER NOT NULL DEFAULT 0")

    # Project-level directory link
    try:
        conn.execute("SELECT dir FROM projects LIMIT 0")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE projects ADD COLUMN dir TEXT")

    # Project-level timeout default (seconds)
    try:
        conn.execute("SELECT timeout_sec FROM projects LIMIT 0")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE projects ADD COLUMN timeout_sec INTEGER")

    # Chain heartbeat/deadline tracking
    for col in ("heartbeat_at", "deadline_at"):
        try:
            conn.execute(f"SELECT {col} FROM chain_state LIMIT 0")
        except sqlite3.OperationalError:
            conn.execute(f"ALTER TABLE chain_state ADD COLUMN {col} TEXT")

    conn.commit()


def now():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def is_valid_iso_local_timestamp(value):
    if value in (None, ""):
        return True
    if not isinstance(value, str):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return False
    return True


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


def create_role(conn, name, description=None):
    conn.execute(
        "INSERT INTO roles (name, description) VALUES (?, ?)",
        (name, description),
    )
    row = conn.execute("SELECT * FROM roles WHERE id = last_insert_rowid()").fetchone()
    conn.commit()
    return Role.from_row(row)


def get_role(conn, name_or_id):
    row = None
    try:
        role_id = int(name_or_id)
        row = conn.execute("SELECT * FROM roles WHERE id=?", (role_id,)).fetchone()
    except (ValueError, TypeError):
        pass
    if row is None:
        row = conn.execute(
            "SELECT * FROM roles WHERE LOWER(name)=LOWER(?)",
            (str(name_or_id),),
        ).fetchone()
    return Role.from_row(row) if row else None


def list_roles(conn):
    rows = conn.execute("SELECT * FROM roles ORDER BY id").fetchall()
    return [Role.from_row(row) for row in rows]


def delete_role(conn, name_or_id):
    role = get_role(conn, name_or_id)
    if not role:
        return False
    deleted = conn.execute("DELETE FROM roles WHERE id=?", (role.id,)).rowcount > 0
    if deleted:
        conn.commit()
    return deleted


def update_role(conn, name_or_id, new_name=None, new_description=None):
    role = get_role(conn, name_or_id)
    if not role:
        return None

    updates = []
    values = []
    if new_name is not None:
        updates.append("name=?")
        values.append(new_name)
    if new_description is not None:
        updates.append("description=?")
        values.append(new_description)

    if not updates:
        return role

    values.append(role.id)
    conn.execute(f"UPDATE roles SET {', '.join(updates)} WHERE id=?", values)
    conn.commit()
    return get_role(conn, role.id)


def get_unblocked(tickets):
    """Return only pending tickets whose dependencies are fully done/skipped.

    blocked/failed/needs-review are intentionally excluded until manually transitioned.
    """
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


# ---------------------------------------------------------------------------
# Agent registry (ticket #10)
# ---------------------------------------------------------------------------

def create_agent(conn, name, command_template, role_names=None, priority=0):
    conn.execute(
        "INSERT INTO agents (name, command_template, priority) VALUES (?, ?, ?)",
        (name, command_template, int(priority)),
    )
    agent_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    if role_names:
        for rname in role_names:
            role = get_role(conn, rname)
            if role:
                conn.execute(
                    "INSERT OR IGNORE INTO agent_roles (agent_id, role_id) VALUES (?, ?)",
                    (agent_id, role.id),
                )
    conn.commit()
    return get_agent(conn, agent_id)


def get_agent(conn, name_or_id):
    row = None
    try:
        aid = int(name_or_id)
        row = conn.execute("SELECT * FROM agents WHERE id=?", (aid,)).fetchone()
    except (ValueError, TypeError):
        pass
    if row is None:
        row = conn.execute("SELECT * FROM agents WHERE name=?", (str(name_or_id),)).fetchone()
    if row is None:
        return None
    agent = dict(row)
    role_rows = conn.execute(
        "SELECT r.name FROM roles r JOIN agent_roles ar ON ar.role_id=r.id WHERE ar.agent_id=?",
        (agent["id"],),
    ).fetchall()
    agent["roles"] = [r["name"] for r in role_rows]
    return agent


def list_agents(conn):
    rows = conn.execute("SELECT * FROM agents ORDER BY priority ASC, id ASC").fetchall()
    agents = []
    for row in rows:
        a = dict(row)
        role_rows = conn.execute(
            "SELECT r.name FROM roles r JOIN agent_roles ar ON ar.role_id=r.id WHERE ar.agent_id=?",
            (a["id"],),
        ).fetchall()
        a["roles"] = [r["name"] for r in role_rows]
        agents.append(a)
    return agents


def delete_agent(conn, name_or_id):
    agent = get_agent(conn, name_or_id)
    if not agent:
        return False
    conn.execute("DELETE FROM agents WHERE id=?", (agent["id"],))
    conn.commit()
    return True


def update_agent(conn, name_or_id, new_name=None, new_command_template=None, role_names=None, new_priority=None):
    agent = get_agent(conn, name_or_id)
    if not agent:
        return None
    updates, values = [], []
    if new_name is not None:
        updates.append("name=?"); values.append(new_name)
    if new_command_template is not None:
        updates.append("command_template=?"); values.append(new_command_template)
    if new_priority is not None:
        updates.append("priority=?"); values.append(int(new_priority))
    if updates:
        values.append(agent["id"])
        conn.execute(f"UPDATE agents SET {', '.join(updates)} WHERE id=?", values)
    if role_names is not None:
        conn.execute("DELETE FROM agent_roles WHERE agent_id=?", (agent["id"],))
        for rname in role_names:
            role = get_role(conn, rname)
            if role:
                conn.execute(
                    "INSERT OR IGNORE INTO agent_roles (agent_id, role_id) VALUES (?, ?)",
                    (agent["id"], role.id),
                )
    conn.commit()
    return get_agent(conn, agent["id"])


def route_ticket(conn, ticket, default_agent_name=None):
    """Route a ticket to an agent.

    Matching is first-match-wins: agents are ordered by priority ASC then id ASC.
    Lower priority numbers win.
    """
    tags = (ticket["tags"] if isinstance(ticket, dict) else ticket["tags"]) or ""
    role_names = []
    for part in tags.split(","):
        tag = part.strip()
        if tag.lower().startswith("role:") and len(tag) > len("role:"):
            role_name = tag.split(":", 1)[1].strip()
            if role_name:
                role_names.append(role_name.lower())

    if role_names:
        placeholders = ",".join("?" for _ in role_names)
        row = conn.execute(
            f"""
            SELECT a.id
            FROM agents a
            JOIN agent_roles ar ON ar.agent_id = a.id
            JOIN roles r ON r.id = ar.role_id
            WHERE LOWER(r.name) IN ({placeholders})
            ORDER BY a.priority ASC, a.id ASC
            LIMIT 1
            """,
            role_names,
        ).fetchone()
        if row:
            return get_agent(conn, row["id"])

    if default_agent_name:
        return get_agent(conn, default_agent_name)
    return None


# ---------------------------------------------------------------------------
# Chain state persistence (ticket #23)
# ---------------------------------------------------------------------------

def get_chain_state(conn, project_id):
    row = conn.execute(
        "SELECT * FROM chain_state WHERE project_id=?",
        (project_id,),
    ).fetchone()
    return dict(row) if row else None


def set_chain_state(
    conn,
    project_id,
    status,
    current_ticket_id=None,
    pause_reason=None,
    heartbeat_at=None,
    deadline_at=None,
):
    conn.execute(
        """
        INSERT INTO chain_state (
            project_id, status, current_ticket_id, pause_reason, heartbeat_at, deadline_at, updated_at
        )
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(project_id) DO UPDATE SET
            status=excluded.status,
            current_ticket_id=excluded.current_ticket_id,
            pause_reason=excluded.pause_reason,
            heartbeat_at=excluded.heartbeat_at,
            deadline_at=excluded.deadline_at,
            updated_at=excluded.updated_at
        """,
        (project_id, status, current_ticket_id, pause_reason, heartbeat_at, deadline_at, now()),
    )
    conn.commit()


def clear_chain_state(conn, project_id):
    conn.execute("DELETE FROM chain_state WHERE project_id=?", (project_id,))
    conn.commit()
