# /agentplan:next

Show the next unblocked ticket for a project and offer to claim it immediately.

## Steps

1. Query next unblocked work:

```bash
agentplan next <project>
```

2. Interpret result:
   - If a ticket is returned: summarize ticket ID/title (and key description notes if present).
   - If no ticket is returned: report that no unblocked tickets are currently available.

3. Offer to claim and begin:
   - Suggest running:

```bash
agentplan claim <project>
```

   - If user confirms execution, claim ticket before implementation begins.

## Output format

- **Next ticket:** `<id> <title>` (or "none")
- **Why this is next:** mention unblocked/dependency state
- **Action:** "Claim now and start" (or "Project complete / all remaining tickets blocked")

## Guardrails

- Do not start coding from this skill alone; this skill is for surfacing and optionally claiming the next task.
- Respect dependency ordering implied by AgentPlan (`next` is dependency-aware).
