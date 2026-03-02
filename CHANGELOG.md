# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## v0.4.2 - 2026-03-01

### Changed
- Activity feed redesigned — Linear/Vercel-style with colored left borders, no emoji, one-line rows, pill filters, day grouping, bulk event collapsing, clickable ticket refs
- Typography standardized across all dashboard pages — Playfair Display for h1 only, Inter for everything else, JetBrains Mono for data/IDs
- Show completed toggle on home page (was Show archived)
- Activity log text truncated to 120 chars to prevent horizontal overflow
- Flask dashboard runs threaded for reliable SSE connections

### Fixed
- Undefined JS function call on activity page (applyRelativeTimes)
- Feed rows no longer cause horizontal scroll on long log messages
- h2-h6 forced to Inter to prevent Playfair inheritance

## v0.4.1 - 2026-03-01

### Fixed
- SSE activity feed was never rendering — escaped newlines (`\\n`) replaced with real newlines

### Changed
- Dashboard dropdown filters (status, priority, tags) replace free-text inputs
- Color legend bar on project detail view
- Home page split into Active and Completed project sections, archived hidden by default
- Standardized nav bar across all dashboard pages
- Human-readable relative timestamps on home page project cards
- Activity feed grouped by day, bulk-created events collapsed, agent/action filter pills

## v0.4.0 - 2026-03-01

### Added
- `Makefile` with full release automation (`make release V=x.y.z`) — dirty tree check, semver validation, changelog gate, git tags, cross-platform sed
- Terminal demo GIF in README hero section
- 104 tests total (was 74) — new coverage for security, dashboard, circular deps, log/attach/note, close/skip, auto-completion, edge cases

### Changed
- **Package restructure** — flat modules (`db.py`, `cli.py`, `models.py`, `dashboard.py`) moved into `agentplan/` package directory. Eliminates PyPI dependency confusion risk.
- Repo cleaned: removed stale pre-restructure files, build artifacts, `DESIGN.md`, `requirements.txt`, duplicate `tests/` directory

### Security
- XSS fix in dashboard activity feed — all user-derived values now HTML-escaped before `innerHTML` injection
- Input length limits: titles 200 chars, descriptions 4000, agent names 100
- Database file created with `0o600` permissions (owner-only read/write)
- Query limits on dashboard endpoints (`LIMIT 100` projects, `LIMIT 1000` tickets)

### Fixed
- Dashboard blocked logic — tickets now correctly unblock when dependencies complete (was checking for presence of deps, not their status)
- Activity feed SSE — Kanban page now receives `project_board` events
- Kanban card overflow — done column scrolls instead of spilling

## v0.3.7 - 2026-03-01

### Added
- **Dashboard complete redesign** — dark theme design system, Mission Control home with SVG progress rings, Kanban board with 4-column layout, ticket detail slide-over panel with deps graph and audit timeline, live activity feed with SSE
- `agentplan dashboard --stop` command to kill running dashboard
- `agentplan dashboard --open` flag to launch in default browser

### Changed
- Complete README rewrite with verified CLI output for all examples
- Marketing site redesigned with Hatchet-style dark navy theme (Playfair Display/Inter/JetBrains Mono)
- `llms.txt` rewritten with "When to use agentplan", agent loop pattern, full command reference
- PyPI classifiers expanded (19 keywords, Beta status, AI classifiers, Python 3.13/3.14)
- GitHub repo polish: homepage URL, description, topics, social preview image

## v0.3.0 - 2026-03-01

### Added
- **Web dashboard** — Flask app with project overview, ticket detail, live SSE updates (`agentplan dashboard`)
- **Marketing site** — `docs/index.html` landing page, `docs/quickstart.html`, hosted via GitHub Pages
- `agentplan dashboard` CLI subcommand

### Changed
- **Package split** — `agentplan.py` refactored into `db.py`, `cli.py`, `models.py`, `dashboard.py`
- `undepend` now uses `--on` flag for API consistency with `depend`

## v0.2.0 - 2026-03-01

### Added
- Ticket priority support with `--priority` and priority-aware ordering in `next`
- Close notes on `ticket done` via `--note`
- Ticket labels/tags via `--tag`, plus filtering in `next`, `status`, and `claim`
- Subtasks/checklists with `subtask add|done|list` and progress indicators
- Agent identity tracking with `--agent` on `ticket start`, `ticket done`, and `claim`
- Atomic `claim` command for concurrency-safe ticket claiming
- Ticket descriptions on create with `ticket add --desc`
- `ticket edit` command with `--title`, `--desc`, `--priority`, `--tag`, and `--due`
- Due dates (`--due`) with overdue-aware prioritization in `next`
- Cross-project full-text ticket search with `search`
- `archive` command for completed/abandoned projects
- Bulk completion support in `ticket done` (space-separated and comma-separated IDs)
- JSON output for `next --format json` and `status --format json`
- Ticket state audit log with `history` (state transitions + timestamps)
- Shell completion generation for `bash`, `zsh`, and `fish` via `completion`
- Human-friendly CLI errors with actionable suggestions
- `llms.txt` and `llms-full.txt` for agent discoverability
- `CONTRIBUTING.md` with setup, testing, and PR guidance

### Changed
- `list` now hides archived projects by default and supports `--all` to include them
- Status output includes a concise summary line and richer ticket metadata display
- Adding a new ticket can reopen projects in `completed`, `abandoned`, or `archived`

## v0.1.1 - 2026-02-28

### Fixed
- Per-project ticket numbers (tickets now start at 1 within each project)
- Reopen completed/abandoned projects when new tickets are added

## v0.1.0 - 2026-02-28

### Added
- Initial release
- `create` projects with inline `--ticket` flags
- `ticket add`, `ticket done`, `ticket skip`, `ticket start`, `ticket list`
- `next` command returns unblocked tickets
- `depend` command for ticket dependencies with auto-unblock
- `status` and `list` commands
- `close` with optional `--abandon` flag
- SQLite storage at `~/.agentplan/agentplan.db`
- `AGENTPLAN_DB` / `AGENTPLAN_DIR` environment variable overrides
- Zero runtime dependencies (Python stdlib only)
