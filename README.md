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

- Persistent project + ticket queue
- Dependency tracking with automatic unblocking
- Atomic ticket claiming (safe for concurrent agents)
- Web dashboard for visibility
- Local-first SQLite storage
- Built-in plugins for Claude Code and Codex

## What AgentPlan Is

AgentPlan is the coordination layer for AI work.

Use it to:
- create a project for a repo
- break work into small tickets
- track dependencies and progress
- let agents claim the next unblocked task
- watch the work move in the dashboard

AgentPlan is not the main execution engine. Claude Code, Codex, and other tools do the planning and implementation work. AgentPlan keeps the shared backlog, ticket state, and history in one place.

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

Short version: plan in the AI tool, track in AgentPlan, execute through the AI tool's own loop or scheduled workflow.

## Quickstart

```bash
# Create a project linked to the current repo
agentplan create "Ship v1" --dir .

# Add a few tickets
agentplan ticket add ship-v1 "Set up database" --priority high
agentplan ticket add ship-v1 "Implement API" --priority high
agentplan ticket add ship-v1 "Write tests" --priority medium

# Add dependencies where needed
agentplan depend ship-v1 2 --on 1
agentplan depend ship-v1 3 --on 2

# See what's ready to work on
agentplan next ship-v1

# Claim the next unblocked ticket
agentplan claim ship-v1

# Mark it done
agentplan ticket done ship-v1 1

# Check progress
agentplan status ship-v1
```

## AI tool setup

The `setup` command installs plugins from the pip package, so the AI tool can understand the AgentPlan workflow without cloning anything extra:

```bash
# Claude Code — registers as a local marketplace plugin
agentplan setup claude

# Codex CLI — copies the skill into ~/.codex/skills/
agentplan setup codex
```

After setup, restart the AI tool.

### Claude Code flow

- `/agentplan:plan` creates a project and tickets from the conversation
- `/agentplan:status` shows project progress
- `/agentplan:loop` generates the prompt/instructions for Claude's own loop or cron-driven workflow

### Codex flow

- use the installed `agentplan` skill
- create a project, add tickets, and work from `agentplan next` / `agentplan claim`
- keep AgentPlan as the shared backlog if Claude and Codex are both working on the same repo

## Core CLI commands

### Project lifecycle

| Command | Description |
|---------|-------------|
| `agentplan create` | Create a project (with optional `--ticket` flags) |
| `agentplan list` | List all projects |
| `agentplan status <project>` | Show project progress and ticket states |
| `agentplan close <project>` | Close a completed project |
| `agentplan archive <project>` | Archive a project |
| `agentplan remove <project>` | Permanently remove a project |

### Ticket workflow

| Command | Description |
|---------|-------------|
| `agentplan ticket add <project> "title"` | Add a ticket |
| `agentplan ticket list <project>` | List tickets |
| `agentplan ticket done <project> <num>` | Mark ticket done |
| `agentplan ticket skip <project> <num>` | Skip a ticket |
| `agentplan ticket block <project> <num>` | Block a ticket |
| `agentplan ticket fail <project> <num>` | Mark ticket failed |
| `agentplan ticket edit <project> <num>` | Edit ticket details |
| `agentplan next <project>` | Show next unblocked tickets |
| `agentplan claim <project>` | Atomically claim the next unblocked ticket |
| `agentplan search <query>` | Search tickets across all projects |

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
# install with dashboard extras (requires Flask)
pip install "agentplan[dashboard]"

agentplan dashboard
# or run in background:
agentplan dashboard --background
```

Open `http://127.0.0.1:5001` to view projects, ticket board, and activity. Create and edit tickets directly from the UI.

## Advanced workflows

AgentPlan also includes advanced and power-user surfaces for orchestration, CI, and other automation-heavy workflows. Those are intentionally de-emphasized in the main UX.

If you are evaluating AgentPlan for the first time, start with:
- project creation
- tickets and dependencies
- `next` and `claim`
- dashboard visibility
- Claude/Codex plugin flow

## Security + docs

- Security policy: `docs/security/security.md`
- Privacy: `docs/security/privacy.md`
- Canonical docs alignment baseline: `docs/docs-alignment-canonical-story.md`

## License

MIT
