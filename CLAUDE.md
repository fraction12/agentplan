# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is agentplan

A shared task system for multiple AI agents working on the same project. Pure Python CLI with SQLite storage, a Flask web dashboard, and plugins for Claude Code and Codex. Zero required dependencies (Flask is optional for the dashboard).

## Build & Test Commands

```bash
# Install in editable mode with dev deps
pip install -e ".[dev]"

# Install with dashboard support
pip install -e ".[dev,dashboard]"

# Run all tests
AGENTPLAN_DB=/tmp/test_agentplan.db pytest test_agentplan.py -v

# Run a single test
AGENTPLAN_DB=/tmp/test_agentplan.db pytest test_agentplan.py -v -k "test_name"

# Run marketplace action tests
pytest test_marketplace_actions.py -v

# Launch the dashboard locally
agentplan dashboard
```

There is no linter or formatter configured in the project.

## Architecture

### Module layout

- **`agentplan/cli.py`** (~4150 lines) — The entire CLI. Flat dispatch: `main()` uses argparse with subcommands, each mapped to a `cmd_*` function. Contains all business logic for project/ticket lifecycle, chain orchestration, hooks, agent spawning, and terminal management.
- **`agentplan/db.py`** — SQLite database layer. Schema creation via `init_db()` with inline migrations (ALTER TABLE). WAL mode, foreign keys enabled. All queries use parameterized SQL.
- **`agentplan/models.py`** — Frozen dataclasses (`Project`, `Ticket`, `Subtask`, `HistoryEntry`, `Role`) with `from_row()` constructors for sqlite3.Row.
- **`agentplan/dashboard/`** — Flask web dashboard. `routes.py` has all endpoints. `sse.py` handles server-sent events for live updates. `constants.py` has kanban display config.
- **`agentplan/plugins/`** — Bundled plugins installed by `agentplan setup`. Claude Code plugin uses `commands/*.md` format (the canonical format). Codex plugin uses `SKILL.md`.

### Key patterns

- **Connection lifecycle**: `conn = _ensure(get_connection())` opens + initializes schema. Close with `conn.close()` at end of each `cmd_*` function. No context managers used.
- **Ticket state machine**: States are `pending → in-progress → done|failed|needs-review|blocked|skipped`. Transitions validated by `VALID_TRANSITIONS` dict in `db.py`. Terminal states: `done`, `skipped`.
- **Dependency tracking**: `depends_on` is a JSON array of ticket nums stored as TEXT. `get_unblocked()` returns pending tickets whose deps are all done/skipped. `has_cycle()` runs DFS before adding edges.
- **Claim locking**: `_acquire_claim_lock` in cli.py uses `claim_locks` table with TTL-based expiry for multi-agent atomic claims.
- **Slug resolution**: Projects identified by slug (auto-generated from title) or numeric ID. `resolve_project()` tries slug first, then int ID.
- **Version**: Single source in `cli.py` as `__version__`, re-exported from `__init__.py`.

### Database

SQLite with WAL mode. Default path: `~/.agentplan/agentplan.db`. Override with `AGENTPLAN_DB` env var (used by tests). Schema lives in `init_db()` — initial `executescript` block plus migration checks that `ALTER TABLE` for columns added over time.

### Dashboard

Flask app at `agentplan/dashboard/`. Binds to `127.0.0.1:5001`. Has CSRF protection via Origin/Referer checking (`_require_local_origin` decorator). SSE endpoint at `/api/events` for live project stats. Templates in `dashboard/templates/`, static assets in `dashboard/static/`.

### Plugin system

Plugin assets live under `agentplan/plugins/`.

The `commands/*.md` format is the current standard. `agentplan setup` copies from the package-bundled `agentplan/plugins/` directory.

## Commit conventions

Use conventional commit prefixes: `feat:`, `fix:`, `docs:`, `test:`, `chore:`. Branch names: `feat/<desc>`, `fix/<desc>`, etc.

## Environment variables

- `AGENTPLAN_DB` — Override database path (critical for tests)
- `AGENTPLAN_DIR` — Override config/data directory (default: `~/.agentplan`)
