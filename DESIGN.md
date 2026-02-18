# agentplan — Design Document

*Version 0.1.0 | February 2026*

## Problem

AI agents lose track of multi-step work across sessions. Context compaction destroys in-progress plans. The agent needs to re-derive "what's next?" every time it wakes up.

**Core need:** Persist a task graph and answer "what should I work on next?" instantly.

## Architecture

- **Single Python file** (`agentplan.py`), zero external dependencies
- **SQLite database** at `~/.agentplan/agentplan.db` (WAL mode)
- **Env overrides:** `AGENTPLAN_DIR`, `AGENTPLAN_DB`
- **Terminology:** Projects → Tickets → Attachments/Log entries

## Schema

```sql
CREATE TABLE projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',  -- active, paused, completed, abandoned
    notes TEXT,
    created_at TEXT, updated_at TEXT
);

CREATE TABLE tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, in-progress, done, skipped
    depends_on TEXT DEFAULT '[]',  -- JSON array of ticket IDs
    notes TEXT,
    created_at TEXT, completed_at TEXT
);

CREATE TABLE attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    ticket_id INTEGER REFERENCES tickets(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    path TEXT, url TEXT, notes TEXT, created_at TEXT
);

CREATE TABLE log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    ticket_id INTEGER REFERENCES tickets(id) ON DELETE CASCADE,
    entry TEXT NOT NULL, created_at TEXT
);
```

## Key Features

### 1. Dependency Resolution (`next`)
The killer feature. `agentplan next` computes which tickets are unblocked — all their dependencies are done or skipped. This is what makes it better than a markdown checklist.

### 2. Circular Dependency Detection
DFS cycle check runs on every `depend` and `ticket add --depends`. Prevents invalid graphs.

### 3. Auto-Complete
When the last pending/in-progress ticket is marked done or skipped, the project auto-completes.

### 4. Compact Output
`status --format compact` produces ~50-80 token summaries for bootstrap hook injection.

### 5. Slugify
Title → lowercase, strip non-alphanumeric (keep hyphens/spaces), spaces to hyphens, cap at 60 chars. Collision: append -2, -3, etc.

## Commands

| Command | Description |
|---------|-------------|
| `init` | Initialize database |
| `create <title> [--ticket ...] [--notes ...]` | Create project with optional tickets |
| `ticket add <project> <title> [--depends] [--notes]` | Add ticket |
| `ticket done <project> <id...>` | Mark ticket(s) done |
| `ticket skip <project> <id...>` | Skip ticket(s) |
| `ticket start <project> <id>` | Mark in-progress |
| `ticket list <project> [--status]` | List tickets |
| `next [project]` | Show unblocked tickets |
| `status [project] [--format compact\|full\|json]` | Project status |
| `list [--status active\|completed\|all]` | List projects |
| `attach <project> <label> <path-or-url> [--ticket]` | Attach file/URL |
| `log <project> <entry> [--ticket]` | Add log entry |
| `close <project> [--abandon]` | Close project |
| `note <project> [--ticket] <text>` | Set note |
| `depend <project> <id> --on <ids>` | Add dependencies |
| `remove <project> [--ticket]` | Remove project/ticket |
| `version` | Show version |

## Exit Codes

- **0:** Success
- **1:** No results (empty — for hooks)
- **2:** User error

## Output Formats

### Full
```
My Project [active] — 3/5 done
  ✓ 1. Setup
  ✓ 2. Build
  ▶ 3. Test (in-progress)
  ⏳ 4. Deploy (blocked — waiting on 3)
  ○ 5. Docs
```

### Compact
```
📋 My Project: 3/5 done | Next: [3] Test ▶, [5] Docs ○
```

### JSON
Full structured data for programmatic consumption.
