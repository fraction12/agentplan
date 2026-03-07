---
allowed-tools: Bash(agentplan:*)
description: Create a project plan with tickets from conversation
---

# /agentplan:plan

Create a new AgentPlan project for the current workstream, decompose it into actionable tickets, wire dependencies, and present the resulting plan.

## Steps

1. Understand what the user wants to build (from conversation context or ask).
2. Create the project:
   ```bash
   agentplan create "<Project Title>" --dir .
   ```
3. Break the work into tickets. Each ticket should be 1–2 focused sessions:
   ```bash
   agentplan ticket add <project> "Ticket title" --priority high --desc "Details"
   ```
4. Add dependencies between tickets where order matters:
   ```bash
   agentplan depend <project> <ticket> --on <dependency>
   ```
5. Show the result:
   ```bash
   agentplan status <project>
   ```

## Guidelines
- Keep tickets granular and action-oriented
- Use priorities: high for blockers, medium for core work, low for polish
- Wire dependencies so `agentplan next` returns the right ticket at the right time
- Link the project to the current directory with `--dir .`
