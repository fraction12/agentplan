---
name: "agentplan"
description: "Use when planning, tracking, or executing multi-ticket projects. AgentPlan is the shared task board for AI work sessions — create projects, break work into tickets, claim tickets atomically, and track progress across tools."
---

# AgentPlan Skill

## When to use
- User asks to plan or build something with multiple steps
- Working through an existing agentplan project
- Need to check what's next, claim work, or mark tickets done
- Coordinating work with Claude Code or other AI tools through a shared backlog

## Core idea

AgentPlan is the source of truth for project state.

Codex does the work.
AgentPlan stores:
- ticket queue
- dependency order
- claim state
- progress history

## Core workflow
1. **Before starting:** `agentplan claim <project>` (atomic lock)
2. **Do the work** for the claimed ticket
3. **When done:** `agentplan ticket done <project> <num>` + `agentplan log <project> --ticket <num> "summary"`
4. **Repeat** until `agentplan next <project>` returns nothing

## Creating a project
```bash
agentplan create "Project Title" --dir .
agentplan ticket add <project> "Ticket title" --priority high --desc "Details"
agentplan depend <project> 2 --on 1   # ticket 2 depends on ticket 1
```

## Key commands
```bash
agentplan create "Title" --dir .                    # Create project linked to cwd
agentplan ticket add <proj> "Title" [--priority P] [--desc D] [--depends N]
agentplan next <project>                            # Show next unblocked ticket
agentplan claim <project>                           # Atomically claim next ticket
agentplan ticket done <proj> <num>                  # Mark complete
agentplan ticket fail <proj> <num> --reason "why"   # Mark failed
agentplan ticket skip <proj> <num>                  # Skip ticket
agentplan ticket edit <proj> <num> [--title T] [--desc D] [--priority P]
agentplan ticket list <proj> [--status S]           # List tickets
agentplan log <proj> "message" --ticket <num>       # Log progress
agentplan status [project]                          # Project overview
agentplan depend <proj> <num> --on <dep>            # Add dependency
agentplan search "query"                            # Search across projects
agentplan list                                      # List all projects
agentplan close <project>                           # Close project
agentplan note <proj> "text"                        # Add project note
agentplan attach <proj> "label" "path"              # Attach file/URL
agentplan remove <proj> [--ticket N]                # Remove project/ticket
agentplan dashboard [--background]                  # Launch web dashboard
```

## Rules
- Always claim before working (prevents conflicts)
- Respect dependencies — only work unblocked tickets
- Keep tickets small (1-2 sessions each)
- Log meaningful progress, not busywork
- Link projects to directories with `--dir .`
- If Claude and Codex are both working, use AgentPlan as the shared backlog instead of separate private plans
