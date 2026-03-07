---
allowed-tools: Bash(agentplan:*)
description: Generate a work loop to autonomously process tickets
---

# /agentplan:loop

Generate the exact prompt for Claude Code's `/loop` command to autonomously work through AgentPlan tickets.

## Generated loop prompt

Fill in `<project>` and use with `/loop`:

```
Use AgentPlan as the source of truth for this work loop.

Project: <project>

Loop algorithm:
1) Run: agentplan next <project>
2) If no unblocked ticket is returned:
   - Report: "No unblocked tickets remain for <project>."
   - Stop.
3) If a ticket is returned:
   a. Run: agentplan claim <project>
      - If claim returns no ticket (race/lock), go back to step 1.
   b. Read the claimed ticket fully (title, description, dependencies, notes).
   c. Implement exactly what the ticket asks.
   d. Run relevant validation (tests/build/lint) for the changed scope.
   e. Commit code with a clear message describing the ticket outcome.
   f. Mark done: agentplan ticket done <project> <ticket_num>
   g. Log outcome: agentplan log <project> --ticket <ticket_num> "Completed: <what changed>. Validation: <what passed>."
   h. Continue loop from step 1.

Failure handling:
- If implementation cannot be completed, mark failed:
  agentplan ticket fail <project> <ticket_num> --reason "<blocked by / error summary>"
- Then report the blocker clearly and stop.

Rules:
- Do not start work without claiming first.
- Respect dependencies; only work tickets surfaced by next/claim.
- Keep changes scoped to the claimed ticket.
- Repeat until no unblocked tickets remain.
```

## Output
Return the filled prompt with `<project>` replaced by the target project name.
