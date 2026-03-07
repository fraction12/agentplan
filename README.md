<p align="center">
  <h1 align="center">agentplan</h1>
  <p align="center"><strong>Asana for AI agents.</strong></p>
</p>

<p align="center">
  <a href="https://pypi.org/project/agentplan/"><img src="https://img.shields.io/pypi/v/agentplan" alt="PyPI version"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License: MIT"></a>
</p>

agentplan is a shared task system for multiple AI agents working on the same project.

- persistent project + ticket queue
- dependency tracking
- ticket ownership + history
- web dashboard for visibility
- local-first SQLite storage

## Install

```bash
pip install agentplan
```

## Quickstart

```bash
# Create a project with starter tickets
agentplan create "Ship v1" \
  --ticket "Set up database" \
  --ticket "Implement API" \
  --ticket "Write tests"

# See what's ready
agentplan next ship-v1

# Claim work
agentplan claim ship-v1 --agent dash

# Mark complete
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

### Claude Code plugin

```bash
/install-plugin github:fraction12/agentplan
```

Or copy manually:

```bash
cp -r plugins/claude-code ~/.claude/plugins/agentplan
```

### Codex skill

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
