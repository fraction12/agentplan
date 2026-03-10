---
allowed-tools: Bash(agentplan:*), AskUserQuestion
description: Create a project plan with tickets from conversation
---

# /agentplan:plan

Collaborate with the user to create a new AgentPlan project, break work into tickets, wire dependencies, and present the plan.

## Steps

1. **Understand the goal.** Ask the user what they want to build if not clear from context.

2. **Create the project:**
   ```bash
   agentplan create "<Project Title>" --dir .
   ```

3. **Break work into tickets.** Each ticket should be 1–2 focused sessions of work. Create them in dependency order, and assign a model tier based on task complexity:
   ```bash
   agentplan ticket add <project> "Ticket title" --priority high --desc "Details" --model standard
   ```
   Model tiers: `light` (mechanical), `standard` (clear implementation), `reasoning` (architectural judgment), `auto` (unknown — default).

4. **Wire dependencies** between tickets where execution order matters:
   ```bash
   agentplan depend <project> <ticket> --on <dependency>
   ```

5. **Show the result:**
   ```bash
   agentplan status <project>
   ```

6. **Ask the user** if they want to adjust anything (add/remove tickets, change priorities, edit dependencies).

## Guidelines

- Keep tickets granular and action-oriented
- Use priorities: high for blockers, medium for core work, low for polish
- Wire dependencies so `agentplan next` returns the right ticket at the right time
- Always link the project to the current directory with `--dir .`
- After showing the plan, ask: "Want to adjust anything, or should we start working?"
