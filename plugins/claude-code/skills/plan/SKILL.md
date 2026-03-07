# /agentplan:plan

Create a new AgentPlan project for the current workstream, decompose it into actionable tickets, wire dependencies, and present the resulting plan.

## Steps

1. **Create the project linked to current directory**

```bash
agentplan create "<Project Title>" --dir .
```

2. **Decompose scope into small tickets**
   - Add tickets with clear outcomes.
   - Keep each ticket small enough for 1–2 focused sessions.
   - Prefer explicit verbs in titles (e.g., "Add API validation", "Write migration tests").

```bash
agentplan ticket add <project> "<ticket title>" --desc "<done condition>"
```

3. **Add dependencies to encode execution order**
   - Ticket B depending on ticket A:

```bash
agentplan depend <project> <ticket_b_id> --on <ticket_a_id>
```

4. **Show and validate the plan**

```bash
agentplan status <project>
```

## Output format

Return:
- Project name
- Ticket list with IDs
- Dependency chain summary
- Suggested first ticket (from `agentplan next <project>`)

## Notes

- Always include `--dir .` when creating the project from the current repo.
- If scope is large, split into phases and make cross-phase dependencies explicit.
- If user already has a project, skip create and only add/reshape tickets + dependencies.
