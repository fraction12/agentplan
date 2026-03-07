# /agentplan:status

Display project progress in a concise, readable format.

## Steps

1. Run:

```bash
agentplan status <project>
```

2. Parse and present:
   - Overall completion (done/total)
   - Active/in-progress tickets
   - Next unblocked ticket(s)
   - Blocked tickets and dependency reason (if shown)
   - Any high-priority tickets

## Output format

Use this structure:

- **Project:** `<name>`
- **Progress:** `<done>/<total>`
- **In progress:** `<ticket list or none>`
- **Next up:** `<ticket list or none>`
- **Blocked:** `<ticket list or none>`
- **Risks/notes:** `<short summary>`

## Notes

- Prefer concise summaries over raw CLI dumps.
- If project not found, report error and suggest `agentplan list`.
