<p align="center">
  <h1 align="center">agentplan</h1>
  <p align="center"><strong>Asana for AI agents — a task board that any AI tool can drive.</strong></p>
</p>

<p align="center">
  <a href="https://pypi.org/project/agentplan/"><img src="https://img.shields.io/pypi/v/agentplan" alt="PyPI version"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License: MIT"></a>
  <a href="https://pypi.org/project/agentplan/"><img src="https://img.shields.io/pypi/dm/agentplan" alt="PyPI downloads"></a>
  <img src="https://img.shields.io/pypi/pyversions/agentplan" alt="Python versions">
  <a href="https://scorecard.dev/viewer/?uri=github.com/fraction12/agentplan"><img src="https://api.scorecard.dev/projects/github.com/fraction12/agentplan/badge" alt="OpenSSF Scorecard"></a>
  <a href="https://github.com/fraction12/agentplan/actions/workflows/ci.yml"><img src="https://github.com/fraction12/agentplan/actions/workflows/ci.yml/badge.svg" alt="Tests"></a>
</p>

agentplan is **Asana for AI agents** — a shared task board that AI tools can use as the source of truth for work.

- **Spaces & Docs** — organize projects into spaces with markdown documents
- Persistent project + ticket queue with dependency tracking
- Atomic ticket claiming (safe for concurrent agents)
- Model tier routing (`light` / `standard` / `reasoning` / `auto`)
- Web dashboard with live SSE updates
- Local-first SQLite storage
- Built-in plugins for Claude Code and Codex

## Start in 3 steps

```bash
# 1) Install
pip install agentplan

# On macOS (Homebrew Python):
pipx install agentplan

# 2) Connect your AI tool
agentplan setup claude    # Claude Code
agentplan setup codex     # Codex CLI

# 3) Tell your AI to plan
# In Claude Code: /agentplan:plan
# Or just say: "plan a new project for this repo"
```

## Typical workflow

1. Open Claude Code, Codex, or another supported AI tool.
2. Ask it to create an AgentPlan project for the current repo.
3. Let it break the work into tickets with dependencies.
4. Have the AI tool work ticket-by-ticket using `agentplan next` and `agentplan claim`.
5. Use the dashboard to monitor progress and inspect ticket state.

Short version: plan in the AI tool, track in AgentPlan, execute through the AI tool's own loop.

## Quickstart

```bash
# Create a project linked to the current repo
agentplan create "Ship v1" --dir .

# Add tickets with model tiers for AI routing
agentplan ticket add ship-v1 "Set up database" --priority high --model standard
agentplan ticket add ship-v1 "Implement API" --priority high --model standard
agentplan ticket add ship-v1 "Write tests" --priority medium --model light

# Add dependencies
agentplan depend ship-v1 2 --on 1
agentplan depend ship-v1 3 --on 2

# Work through tickets
agentplan next ship-v1       # See what's ready
agentplan claim ship-v1      # Atomically claim the next one
agentplan ticket done ship-v1 1

# Check progress
agentplan status ship-v1
```

## Spaces & Docs

Spaces organize projects and documents into logical groups. Documents are plain markdown files on disk — no database overhead, no lock-in.

```bash
# Create a space
agentplan space create "Backend" --desc "API and data layer"

# Move a project into a space
agentplan project ship-v1 --space backend

# Add documents to a space
agentplan doc add backend "Architecture" --content "# Architecture\n\nSystem design notes."
agentplan doc add backend "Runbook"

# List and read docs
agentplan doc list backend
agentplan doc show backend architecture.md

# Search across docs and tickets
agentplan search "database migration"
```

Every project belongs to a space. Unassigned projects go to the `default` space automatically. Documents live at `~/.agentplan/spaces/<slug>/*.md` — edit them with any tool.

## Model tiers

Every ticket can carry a `--model` tier that tells the executing agent how much capability the task needs:

| Tier | Use when |
|------|----------|
| `light` | Mechanical work — rename files, update configs, fix typos |
| `standard` | Clear implementation — build from a spec, write tests, refactor |
| `reasoning` | Architectural judgment — system design, subtle debugging, tradeoff evaluation |
| `auto` | Unknown complexity — the executing agent decides at runtime (default) |

```bash
agentplan ticket add my-project "Fix typo in README" --model light
agentplan ticket add my-project "Build auth module" --model standard
agentplan ticket add my-project "Design plugin architecture" --model reasoning
```

## AI tool setup

```bash
# Claude Code — registers as a local marketplace plugin
agentplan setup claude

# Codex CLI — copies the skill into ~/.codex/skills/
agentplan setup codex
```

After setup, restart the AI tool.

### Claude Code

- `/agentplan:plan` creates a project and tickets from the conversation
- `/agentplan:status` shows project progress
- `/agentplan:loop` generates instructions for Claude's own loop or cron-driven workflow

### Codex

- Use the installed `agentplan` skill
- Create a project, add tickets, and work from `agentplan next` / `agentplan claim`
- Share the backlog if Claude and Codex are both working on the same repo

## CLI reference

### Projects

| Command | Description |
|---------|-------------|
| `agentplan create` | Create a project (with optional `--ticket` flags) |
| `agentplan list` | List all projects |
| `agentplan status <project>` | Show project progress and ticket states |
| `agentplan close <project>` | Close a completed project |
| `agentplan archive <project>` | Archive a project |
| `agentplan remove <project>` | Permanently remove a project |

### Tickets

| Command | Description |
|---------|-------------|
| `agentplan ticket add <project> "title"` | Add a ticket (`--model`, `--priority`) |
| `agentplan ticket list <project>` | List tickets |
| `agentplan ticket done <project> <num>` | Mark ticket done |
| `agentplan ticket skip <project> <num>` | Skip a ticket |
| `agentplan ticket block <project> <num>` | Block a ticket |
| `agentplan ticket fail <project> <num>` | Mark ticket failed |
| `agentplan ticket edit <project> <num>` | Edit ticket details |
| `agentplan next <project>` | Show next unblocked tickets |
| `agentplan claim <project>` | Atomically claim the next unblocked ticket |
| `agentplan search <query>` | Search across all projects and docs |

### Spaces & Docs

| Command | Description |
|---------|-------------|
| `agentplan space create "name"` | Create a space |
| `agentplan space list` | List all spaces |
| `agentplan space show <slug>` | Show space details, projects, and docs |
| `agentplan space update <slug>` | Update space title or description |
| `agentplan space delete <slug>` | Delete a space (projects become unassigned) |
| `agentplan doc add <space> "title"` | Create a markdown document |
| `agentplan doc list <space>` | List documents in a space |
| `agentplan doc show <space> <file>` | Print document content |
| `agentplan doc path <space> <file>` | Print absolute file path |
| `agentplan doc remove <space> <file>` | Delete a document |

### Dependencies, logs, and notes

| Command | Description |
|---------|-------------|
| `agentplan depend <project> <ticket> --on <dep>` | Add dependency |
| `agentplan undepend <project> <ticket> --on <dep>` | Remove dependency |
| `agentplan log <project>` | Add a log entry |
| `agentplan note <project>` | Set a note on project or ticket |
| `agentplan attach <project>` | Attach a file or URL |
| `agentplan history <project> <ticket>` | Show ticket state transitions |

### Utilities

| Command | Description |
|---------|-------------|
| `agentplan setup [claude\|codex]` | Install AI tool plugin |
| `agentplan dashboard` | Launch web dashboard |
| `agentplan completion` | Print shell completion script |

## Dashboard

```bash
# Install with dashboard extras (requires Flask)
pip install "agentplan[dashboard]"

agentplan dashboard
# or run in background:
agentplan dashboard --background
```

Open `http://127.0.0.1:5001` to view projects, kanban board, and activity feed. The dashboard supports:

- Live updates via SSE (server-sent events)
- Space navigation with project grouping
- Document viewing and editing
- Ticket creation and status changes
- Model tier badges on kanban cards

## Security + docs

- Security policy: `docs/security/security.md`
- Privacy: `docs/security/privacy.md`

## License

MIT
