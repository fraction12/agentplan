---
allowed-tools: Bash(agentplan:*)
description: Show and claim the next unblocked ticket
---

# /agentplan:next

Check what work is available and optionally claim it.

## Steps

1. Show the next unblocked ticket:
   ```bash
   agentplan next <project>
   ```
2. If a ticket is available, offer to claim it:
   ```bash
   agentplan claim <project>
   ```
3. Once claimed, read the ticket details and begin work.
4. When done:
   ```bash
   agentplan ticket done <project> <ticket_num>
   agentplan log <project> --ticket <ticket_num> "Summary of what was done"
   ```

## Rules
- Always claim before working (atomic lock prevents conflicts)
- Respect dependencies — only work tickets surfaced by `next`
