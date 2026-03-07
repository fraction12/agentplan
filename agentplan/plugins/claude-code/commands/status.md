---
allowed-tools: Bash(agentplan:*)
description: Show project overview and ticket status
---

# /agentplan:status

Display the current state of an AgentPlan project.

## Steps

1. Show project overview:
   ```bash
   agentplan status <project>
   ```
2. For detailed per-ticket view:
   ```bash
   agentplan status <project> --format full
   ```

## Output
Present the status clearly: how many tickets done, what's in progress, what's blocked, what's next.
