# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## v0.7.0 - 2026-03-05

### Added
- GitHub Marketplace Phase 1 foundation:
  - `actions/setup` and `actions/run-chain` with documented inputs/outputs
  - `.github/workflows/agentplan-marketplace.yml` starter workflow
  - CI/headless execution mode for chain/context via `AGENTPLAN_CI=1`
- Issue import + runtime artifacts command surfaces:
  - `agentplan issue import ...`
  - `agentplan artifact status|verify ...`
- One-way GitHub Issue → ticket import adapter and mapping storage
- PR automation scaffolding with deterministic naming/logging conventions
- Runtime artifact integrity tracking and verification support
- Marketplace docs pack:
  - `docs/marketplace/quickstart.md`
  - `docs/marketplace/support.md`
  - `docs/marketplace/submission-readiness-report.md`
  - real screenshot assets for listing
- Security/trust docs and deployment hardening guides:
  - privacy, security posture, reverse proxy auth examples, secure self-hosted dashboard guide
- New CI quality workflows for trust badges:
  - `ci.yml`, `codeql.yml`, `scorecard.yml`

### Changed
- Context generation prompt now investigation-driven and AGENTS.md-style:
  - compact status summaries + capped active-ticket list
  - explicit discovery command instructions
  - strict structured `.agentplan.md` output contract
- Prompt handoff for spawned agents now uses robust temp-file + bash variable pattern across paths
- Chain/headless monitoring and routing error messages hardened for CI UAT scenarios
- Marketplace/readme docs updated with action-first installation path and trust links
- Terminology normalized from partner-specific naming to generic “design partner” references

### Tests
- Expanded suite to cover marketplace actions, routing/guardrails, issue/artifact surfaces, and CI chain behavior
- 242 tests passing

## v0.6.4 - 2026-03-05

### Added
- Agent-powered project context generation from both CLI and dashboard
  - CLI `agentplan context <project>` now runs through configured writer-role agent
  - Dashboard adds **Generate Context** button in Project Context panel
- New dashboard APIs:
  - `POST /api/project/<slug>/generate-context`
  - `GET /api/project/<slug>/context-status`
- Writer-agent routing helper (`get_agent_by_role`) and associated validation/error flows

### Changed
- Context prompt is now **investigation-driven** (AGENTS.md/CLAUDE.md style):
  - Uses ticket status summaries + capped open/in-progress list (instead of full ticket dump)
  - Instructs agents to run discovery commands (`agentplan ticket list ...`, `ls`, `rg`, key-file inspection)
  - Enforces structured `.agentplan.md` output sections (summary, architecture, runbook, guardrails, etc.)
- Unified spawn command rendering to use robust prompt-file pattern across context + chain paths
  - Prevents AppleScript/shell escaping issues and long-prompt truncation
  - Uses temp prompt files + bash variable handoff for terminal-spawned agents
- Context generation now supports update-vs-regenerate behavior explicitly (preserve valid sections vs full rewrite)

### Fixed
- Terminal-spawned context generation for Claude writer agent (removed broken `-m` usage path)
- Prompt delivery failures caused by inline shell substitution for large payloads

### Tests
- Expanded coverage for context APIs, writer-role resolution, prompt construction, and status polling
- 225 tests passing

## v0.6.3 - 2026-03-05

### Changed
- **Dashboard architecture refactor** — monolithic `templates.py` (2400 lines) split into proper Flask structure:
  - `templates/base.html` — shared layout (nav, head, CSS/JS links, block definitions)
  - `templates/home.html`, `activity.html`, `agents.html`, `project.html` — page templates extending base
  - `templates/ticket.html` — standalone ticket detail page
  - `static/style.css` — single deduplicated stylesheet for all pages
  - `static/dashboard.js` — shared JS utilities (toast, clock, SSE connection)
  - `static/project.js` — project-specific JS (kanban, ticket panel, directory edit, chain controls)
  - `static/agents.js` — agents page JS (edit row toggle)
  - `constants.py` — Python constants (status labels, tag tones)
- Routes use Flask `render_template()` instead of raw Jinja2 `Template()` strings
- No visual or functional changes — pixel-identical output, all 216 tests passing
- Zero new dependencies, zero build step, `pip install agentplan` still works

## v0.6.2 - 2026-03-05

### Added
- `agentplan project <slug> --dir ~/path` command to set/update project directory without using notes
- Dashboard: editable directory field on project detail page (inline edit with Save/Cancel)
- Dashboard: "Start Work" button shows error toast when no directory is linked
- Dashboard: warning badge on project cards when linked directory doesn't exist on disk
- Dashboard: Agents page now shows clock + connection status indicator (matching Home/Activity)
- Dashboard: Agents table — collapsible edit rows with Edit/Cancel toggle, Delete as text link
- Dashboard: Detected Tools and Add Agent split into separate cards
- Tests for directory guards, dashboard directory API, chain start rejection (216 tests, was 209)

### Changed
- CLI `chain start` now hard-errors (instead of warning) when no project directory is linked
- Unified CSS variables across all 4 dashboard templates (Home, Activity, Agents, Project)
- Normalized `.btn` styles across all pages (consistent padding, border-radius, variants)
- Agents page nav links use `--fs-nav` (0.875rem) matching other pages
- Activity page status label changed from "live" to "connected" for consistency
- Project detail: smaller kanban column headers, tighter filter dropdowns, Project Context uses body font
- Role checkboxes use horizontal flex-wrap layout instead of stacked column
- Directory inline edit — single field replaces text in place (no duplicate display)

## v0.6.1 - 2026-03-05

### Fixed
- `spawn_terminal()` now returns non-zero when both iTerm2 and Terminal.app fail to launch
- `monitor_process()` uses `os.waitpid` to properly detect zombie/terminated processes instead of `os.kill(pid, 0)`
- `cmd_chain()` now rejects re-entry when a chain is already running (CLI parity with dashboard API guard)
- `/api/chain/start` rolls back DB state on `Popen` failure instead of leaving chain permanently stuck as "running"

### Added
- Tests for dashboard chain start/stop API, review panel actions, CLI chain re-entry guard, terminal spawn hard-failure
- Tests for auto-tag AI tool unavailability (`FileNotFoundError`) and malformed/empty model output handling
- 209 tests (was 200)

## v0.6.0 - 2026-03-05

### Added
- **Project directories** — `agentplan create --dir ~/path/to/project` links a project to a codebase
- **`.agentplan.md` context files** — per-project context that gets injected into every agent turn (working dir, verify commands, conventions, hands-off zones)
- **Auto-context generation** — if no `.agentplan.md` exists, agents are instructed to create one by scanning the project before starting work
- **`agentplan context` command** — view the project's `.agentplan.md`, with `--regenerate` to reset it
- **Dashboard: project directory** — shown in the project page top bar
- **Dashboard: Project Context panel** — collapsible section rendering `.agentplan.md` as formatted markdown
- **Directory validation** — chain controller warns if linked directory doesn't exist on disk
- 200 tests (was 186)

### Changed
- Dashboard context panel is collapsible (collapsed by default) to save space
- System prompt injection now includes `.agentplan.md` content when available

## v0.5.0 - 2026-03-04

### Added
- **Roles system** — first-class role objects (coding, research, writing, etc.) with full CRUD operations
- **Agent registry** — register agents with command templates, assigned roles, and priority ordering
- **Auto-detection** — `agentplan init` scans for installed AI tools (Claude, Codex, Aider, Cursor, OpenClaw) and auto-registers them
- **Ticket routing** — `agentplan route` matches ticket role tags to registered agents; priority-based selection when multiple agents handle the same role
- **Event hooks** — on-complete hooks supporting commands, webhooks, and agent chains; hooks fire post-commit for data integrity
- **Stale claim handling** — `--timeout` flag on `claim`, `agentplan reap` command, auto-reap on `next`
- **Expanded state machine** — new ticket states: `blocked`, `failed`, `needs-review` with validated transitions; invalid transitions rejected with error messages
- **Dashboard control plane** — Start Work / Stop buttons for chain controller, real-time progress view, 6-column full-width Kanban board
- **Dashboard Agents page** — configure agents, assign roles, edit command templates, auto-detected tools panel
- **Dashboard review panel** — Mark Done / Retry / Skip actions for failed and needs-review tickets
- **Agent chaining** — sequential chain controller: route → spawn → monitor → repeat
- **Terminal spawning** — `route --terminal` opens agent in a visible terminal window
- **Auto-tagging** — classify untagged tickets into roles using a configured AI tool
- **Agent command template validation** — requires real placeholder patterns (`{ticket}`, `{{ticket}}`, etc.)
- **Agent priority routing** — lower number = higher priority; `ORDER BY priority ASC`
- 186 tests (was 104)

### Changed
- **Dashboard refactored into package** — split monolithic `dashboard.py` into `dashboard/__init__.py`, `routes.py`, `templates.py`, `sse.py`
- Dashboard status constants now derive from single source of truth in `db.py`
- Kanban grid expanded from 4 to 6 columns (full-width layout)
- Dashboard binds to `127.0.0.1` by default (was `0.0.0.0`); use `--host` to expose
- README rewritten for v0.5 with roles, routing, hooks, stale claims, and state machine documentation
- Marketing site updated with v0.5 features, comparison table, and terminal demo
- `llms.txt` and `llms-full.txt` updated with complete v0.5 command reference

### Security
- Hook command execution switched from `shell=True` to `shell=False` with `shlex.split()` — eliminates command injection
- Dashboard CSRF protection — Origin/Referer header checking on all state-mutating endpoints
- Dashboard stop command no longer uses `shell=True` pipeline
- Chain controller guards against duplicate runners (409 Conflict on double-start)

### Fixed
- `claimed_at` and `claim_timeout` properly enforced in claim/reap logic
- Reclaim history records correct state (`pending`, not `reclaimed`)
- Dashboard project stats and Kanban grouping include all ticket states
- Dashboard state transitions validated (same rules as CLI)
- Dead imports cleaned across cli.py, db.py, dashboard/routes.py
- Connection handling standardized (context managers over manual close)
- `--timeout` rejects negative/zero values
- Mixed-case role tags route correctly (case-insensitive matching)

## v0.4.3 - 2026-03-01

### Changed
- Kanban ticket cards: removed left color bar, added priority pills (high/medium/low) inline with tag pills
- Removed status color legend from project detail page
- Project nav bar: added clock + moved SSE status to right side, matching home and activity pages
- Removed project slug subtitle from project page nav bar

### Fixed
- Project page topbar-right alignment (justify-self: end was missing)
- JS syntax error in kanban card template literal

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
