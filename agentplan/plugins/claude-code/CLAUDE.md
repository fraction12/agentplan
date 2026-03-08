# AgentPlan Rules for Claude Code

AgentPlan is installed and available in this environment.

AgentPlan is the task board system for AI work sessions.
- You (Claude Code) own implementation and execution.
- AgentPlan owns planning state, dependencies, and ticket lifecycle.
- Use AgentPlan as the shared backlog, not as the execution runtime.

## Core workflow (always follow)

1. **Before starting implementation:** claim work atomically.
   - Run: `agentplan claim <project>`
   - This prevents multiple sessions from taking the same ticket.
2. Execute the claimed ticket.
3. When complete:
   - Mark done: `agentplan ticket done <project> <ticket_id>`
   - Add a progress log: `agentplan log <project> --ticket <ticket_id> "<summary>"`
4. Repeat until no unblocked tickets remain.

## Project setup conventions

When creating a project for the current repo/folder, always link directory context:
- `agentplan create "<Project Title>" --dir .`

This allows AgentPlan to map project work to the active directory.

## Dependency rules

- Use dependencies to model execution order.
- `agentplan next <project>` only returns tickets that are unblocked.
- Do not start blocked tickets early.
- Add dependency edges explicitly using `agentplan depend`.

## Ticket granularity

Keep tickets small and executable.
- Target size: **1–2 focused sessions** per ticket.
- Break large efforts into multiple dependent tickets.
- Prefer clear, action-oriented ticket titles.

## Primary commands to use

### Create project

```bash
agentplan create --help
usage: agentplan create [-h] [--ticket TICKET] [--notes NOTES] [--dir DIR]
                        [--timeout TIMEOUT]
                        title
```

### Add ticket

```bash
agentplan ticket add --help
usage: agentplan ticket add [-h] [--desc DESC] [--depends DEPENDS]
                            [--notes NOTES] [--tag TAG]
                            [--priority {high,medium,low}] [--due DUE]
                            [--timeout TIMEOUT] [--role ROLE]
                            project title
```

### Claim next ticket (atomic)

```bash
agentplan claim --help
usage: agentplan claim [-h] [--agent AGENT] [--tag TAG] [--timeout TIMEOUT]
                       project
```

### Show next unblocked ticket(s)

```bash
agentplan next --help
usage: agentplan next [-h] [--format {compact,json}] [--tag TAG] [project]
```

### Log progress

```bash
agentplan log --help
usage: agentplan log [-h] [--ticket TICKET] project parts [parts ...]
```

### Show status

```bash
agentplan status --help
usage: agentplan status [-h] [--format {compact,full,json}] [--tag TAG]
                        [project]
```

### Add dependency

```bash
agentplan depend --help
usage: agentplan depend [-h] --on ON project ticket_id
```

### Ticket state transitions

```bash
agentplan ticket done <project> <ticket_num>     # Mark ticket complete
agentplan ticket fail <project> <ticket_num> [--reason REASON]  # Mark failed
agentplan ticket skip <project> <ticket_num>     # Skip ticket
agentplan ticket edit <project> <ticket_num> [--title TITLE] [--desc DESC] [--priority {high,medium,low}]
agentplan ticket list <project> [--status STATUS]
```

## Advanced commands

Advanced orchestration, routing, CI, and other internal/power-user surfaces exist in AgentPlan, but they are not the primary workflow for new users. Prefer the core commands above unless the user explicitly asks for an advanced flow.

## Default operating pattern

For each iteration:
1. `agentplan next <project>`
2. `agentplan claim <project>`
3. Implement the claimed ticket
4. Validate (tests/build as appropriate)
5. `agentplan ticket done <project> <ticket_id>`
6. `agentplan log <project> --ticket <ticket_id> "<what changed + validation>"`

If no ticket is returned by `agentplan next`, the project may be complete or fully blocked. Check:
- `agentplan status <project>`
