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

agentplan is **Asana for AI agents** — a shared task board that any AI tool can drive.

- Persistent project + ticket queue
- Dependency tracking with automatic unblocking
- Atomic ticket claiming (safe for concurrent agents)
- Web dashboard for visibility
- Local-first SQLite storage
- Built-in plugins for Claude Code and Codex

## Start in 3 steps

```bash
# 1) Install
pip install agentplan

# 2) Connect your AI tool
agentplan setup claude    # Claude Code
agentplan setup codex     # Codex CLI

# 3) Tell your AI to plan
# In Claude Code: /agentplan:plan
# Or just say: "plan a new project for this repo"
```

## CLI quickstart

```bash
# Create a project
agentplan create "Ship v1" \
  --ticket "Set up database" \
  --ticket "Implement API" \
  --ticket "Write tests"

# See what's ready to work on
agentplan next ship-v1

# Claim the next unblocked ticket
agentplan claim ship-v1

# Mark it done
agentplan ticket done ship-v1 1

# Check progress
agentplan status ship-v1
```

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
| `agentplan ticket start <project> <num>` | Mark ticket in-progress |
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
agentplan dashboard
# or run in background:
agentplan dashboard --background
```

Open `http://127.0.0.1:5001` to view projects, ticket board, and activity. Create and edit tickets directly from the UI.

## AI tool setup

The `setup` command installs plugins from the pip package — no cloning required:

```bash
# Claude Code — registers as a local marketplace plugin
agentplan setup claude

# Codex CLI — copies skill to ~/.codex/skills/
agentplan setup codex
```

After setup, restart your AI tool. The plugin gives your AI four commands:
- `/agentplan:plan` — Create a project from conversation
- `/agentplan:status` — Show project progress
- `/agentplan:loop` — Set up autonomous ticket processing

## Security + docs

- Security policy: `docs/security/security.md`
- Privacy: `docs/security/privacy.md`

## License

MIT
