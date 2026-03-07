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

- persistent project + ticket queue
- dependency tracking
- ticket ownership + history
- web dashboard for visibility
- local-first SQLite storage

## Start in 3 steps

```bash
# 1) Install
pip install agentplan

# 2) Connect your AI tool
agentplan setup claude
# or
agentplan setup codex

# 3) Tell your AI to plan and execute with AgentPlan
```

## CLI quickstart

```bash
# Create a project with starter tickets
agentplan create "Ship v1" \
  --ticket "Set up database" \
  --ticket "Implement API" \
  --ticket "Write tests"

# See what is ready
agentplan next ship-v1

# Claim work
agentplan claim ship-v1 --agent dash

# Mark complete
agentplan ticket done ship-v1 1 --agent dash
```

## Agent Loop Demo

```bash
agentplan next ship-v1
agentplan claim ship-v1 --agent dash
agentplan ticket done ship-v1 1 --agent dash
```

## Core CLI commands

### Project lifecycle
- `agentplan create`
- `agentplan list`
- `agentplan status`
- `agentplan close`
- `agentplan archive`
- `agentplan remove`

### Ticket workflow
- `agentplan ticket add|list|start|done|skip|block|fail|review|edit|update`
- `agentplan next`
- `agentplan claim`
- `agentplan search`
- `agentplan note`
- `agentplan attach`
- `agentplan history`

### Dependencies + logs
- `agentplan depend`
- `agentplan undepend`
- `agentplan log`

### Utilities
- `agentplan dashboard`
- `agentplan setup`
- `agentplan version`
- `agentplan completion`

## Dashboard

Run the web dashboard:

```bash
agentplan dashboard
```

Open `http://127.0.0.1:5001` to view projects, ticket board state, and activity.

## AI tool setup

Use the built-in setup command to install plugins/skills:

```bash
agentplan setup claude
agentplan setup codex
```

Manual options are still available when you need full control.

### Claude Code plugin (manual)

```bash
/install-plugin github:fraction12/agentplan
```

Or copy manually:

```bash
cp -r plugins/claude-code ~/.claude/plugins/agentplan
```

### Codex skill (manual)

```bash
mkdir -p ~/.codex/skills/agentplan
cp plugins/codex/SKILL.md ~/.codex/skills/agentplan/
```

### OpenClaw skill

```bash
clawhub install agentplan
```

## Notes on advanced orchestration

AgentPlan also contains advanced orchestration/routing surfaces for power users. These are intentionally de-emphasized in the primary UX and documentation.

## Security + docs

- Security policy: `docs/security/security.md`
- Privacy: `docs/security/privacy.md`
- Marketplace docs: `docs/marketplace/`

## License

MIT
