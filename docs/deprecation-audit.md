# Deprecation Audit: Orchestration Surface

This audit was run for branch `feat/deprecate-orchestration`.

## Commands targeted to hide from user-facing surfaces

- `chain`
- `route`
- `spawn-terminal`
- `monitor-process`
- `auto-tag`
- `reap`
- `role` (and subcommands)
- `agent` (and subcommands)
- `hook` (and subcommands)

## Core commands kept visible

- `create`, `ticket`, `next`, `claim`, `status`, `search`, `list`, `log`, `close`, `archive`, `note`, `depend`, `undepend`, `remove`, `history`, `attach`, `dashboard`, `setup`, `version`, `completion`

## User-facing reference locations audited

- `agentplan/cli.py`
- `README.md`
- `docs/` markdown files (including marketplace/security docs)
- `agentplan/dashboard/templates/*`
- `agentplan/dashboard/static/*`
- `agentplan/dashboard/routes.py`

## Outcome

- Deprecated orchestration commands are now suppressed from `agentplan --help`.
- Dashboard no longer links to/advertises agents management and chain control buttons.
- README now focuses on AgentPlan as task management (“Asana for AI agents”).
- Docs that still mention orchestration now carry an advanced/internal notice.
- Code paths remain present for power users invoking commands directly.
