---
allowed-tools: Bash(agentplan:*)
description: Show project overview and ticket status
---

# /agentplan:status

Display the current state of an AgentPlan project. Auto-detect the project from the current directory when possible.

## Steps

1. **Find the project.** If the user didn't specify one, detect it from the current directory:
   ```bash
   agentplan list
   ```
   Match against projects linked to the current working directory. If multiple match or none match, ask the user which project.

2. **Show status:**
   ```bash
   agentplan status <project>
   ```

3. **Summarize clearly:**
   - Total tickets and completion percentage
   - What's done, what's in progress, what's blocked
   - What ticket is next (unblocked and ready)
   - Any failed tickets that need attention
