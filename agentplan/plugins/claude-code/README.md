# AgentPlan Claude Code Plugin

Claude Code plugin assets for AgentPlan.

AgentPlan is the shared task board for AI work.

In the Claude Code workflow:
- Claude plans the work and creates tickets in AgentPlan
- Claude claims and executes tickets from AgentPlan
- AgentPlan stores task state, dependencies, and progress history
- Claude loops or cron jobs handle repeated execution when needed

- `.claude-plugin/plugin.json` — plugin manifest
- `rules/agentplan.md` — always-loaded AgentPlan workflow/rules
- `skills/*/SKILL.md` — slash-command skills (`plan`, `next`, `status`, `loop`)
