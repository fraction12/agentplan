<p align="center">
  <h1 align="center">agentplan</h1>
  <p align="center"><strong>A shared to-do list for AI agents.</strong></p>
</p>

<p align="center">
  <a href="https://pypi.org/project/agentplan/"><img src="https://img.shields.io/pypi/v/agentplan" alt="PyPI version"></a>
  <a href="https://pypi.org/project/agentplan/"><img src="https://img.shields.io/pypi/dm/agentplan" alt="PyPI downloads"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License: MIT"></a>
  <a href="https://github.com/fraction12/agentplan"><img src="https://img.shields.io/github/stars/fraction12/agentplan" alt="GitHub stars"></a>
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> ·
  <a href="#the-agent-loop">The Agent Loop</a> ·
  <a href="#commands">Commands</a> ·
  <a href="#dashboard">Dashboard</a> ·
  <a href="#why-agentplan">Why agentplan?</a> ·
  <a href="https://github.com/fraction12/agentplan/issues">Issues</a>
</p>

## Agent Loop Demo

```text
$ agentplan create "Launch docs portal" \
    --ticket "Initialize repo + CI" \
    --ticket "Build docs site shell" \
    --ticket "Write auth middleware" \
    --ticket "Add onboarding guide"
Created project 'Launch docs portal' (launch-docs-portal) with 4 ticket(s)

# agent-a checks what to work on
$ agentplan next launch-docs-portal
📋 Launch docs portal: [1] Initialize repo + CI ○ (priority: none), [2] Build docs site shell ○ (priority: none), [3] Write auth middleware ○ (priority: none), [4] Add onboarding guide ○ (priority: none)

# agent-a does the work, then marks it done
$ agentplan ticket done launch-docs-portal 1 --agent agent-a
✓ Ticket #1: Initialize repo + CI → done (by agent-a)

# agent-b reviews status
$ agentplan status launch-docs-portal
1/4 done, 0 blocked, next: [2] Build docs site shell
Launch docs portal [active] — 1/4 done
  ✓ 1. Initialize repo + CI [priority: none] [done_by: agent-a]
  ○ 2. Build docs site shell [priority: none]
  ○ 3. Write auth middleware [priority: none]
  ○ 4. Add onboarding guide [priority: none]

# agent-b discovers follow-up work
$ agentplan ticket add launch-docs-portal "Harden CI cache keys"
Added ticket #5: Harden CI cache keys [priority: none]

# ticket 5 depends on ticket 1 (already done — so it's immediately unblocked)
$ agentplan depend launch-docs-portal 5 --on 1
Ticket #5 now depends on: [1]

# agent-c checks the queue — ticket 5 is unblocked and ready
$ agentplan next launch-docs-portal
📋 Launch docs portal: [2] Build docs site shell ○ (priority: none), [3] Write auth middleware ○ (priority: none), [4] Add onboarding guide ○ (priority: none), [5] Harden CI cache keys ○ (priority: none)

# loop continues until queue drains
```

---

Multiple AI agents. One shared work queue. Zero infrastructure.

`agentplan` is a CLI that gives your agents a persistent task queue with dependency resolution. Any agent that can run shell commands can use it — Claude Code, Codex, OpenClaw, or any CLI-capable agent.

No SDK. No framework. No Python dependencies beyond stdlib. Just three commands:

```bash
agentplan next myproject           # What should I work on?
agentplan ticket done myproject 3  # Done with ticket 3
agentplan ticket add myproject "new thing I found"  # Add work
```

That's the entire integration.

## Quickstart

```bash
pip install agentplan
```

```bash
# Create a project with tickets
agentplan create "Build my app" \
  --ticket "Set up database schema" \
  --ticket "Build API endpoints" \
  --ticket "Write tests" \
  --ticket "Deploy to production"
# Created project 'Build my app' (build-my-app) with 4 ticket(s)

# Add dependencies — tests need API, deploy needs everything
agentplan depend build-my-app 3 --on 2
# Ticket #3 now depends on: [2]
agentplan depend build-my-app 4 --on 1,2,3
# Ticket #4 now depends on: [1, 2, 3]

# Ask what's next (only unblocked tickets are returned)
agentplan next build-my-app
# 📋 Build my app: [1] Set up database schema ○ (priority: none), [2] Build API endpoints ○ (priority: none)
```

## The Agent Loop

The real power of `agentplan` is what happens when you connect it to autonomous agents. Here's the pattern:

```
┌─────────────────────────────────────────────┐
│  Agent A (cron, every 15 min)               │
│  1. agentplan next myproject                │
│  2. Do the work                             │
│  3. agentplan ticket done myproject <id>    │
└─────────────────────────────────────────────┘
         ↕ shared queue
┌─────────────────────────────────────────────┐
│  Agent B (cron, offset by 8 min)            │
│  1. agentplan status myproject              │
│  2. Review what Agent A did                 │
│  3. agentplan ticket add myproject "..."    │
└─────────────────────────────────────────────┘
```

**Agent A** pulls the next unblocked ticket, does the work, marks it done. **Agent B** reviews the work, spots issues, adds new tickets. The queue is self-sustaining — no coordinator, no orchestrator, no message passing. Just a shared pile of work.

### Real-world example: OpenClaw + Codex

This is how we actually use it — an [OpenClaw](https://openclaw.ai) agent coordinating with OpenAI Codex:

```bash
# Cron job fires every 15 minutes
NEXT=$(agentplan next my-redesign --format compact)

if [ -z "$NEXT" ]; then
  echo "All done — killing crons"
  exit 0
fi

# Spawn Codex to do the work
codex exec --full-auto "$NEXT"

# Mark done
agentplan ticket done my-redesign "$TICKET_ID"
```

A second cron (running a cheaper model) reviews and adds tickets:

```bash
# Review cron — offset by 8 minutes
agentplan status my-redesign
# ... inspect recent changes ...
agentplan ticket add my-redesign "Fix: button hover state missing"
```

Two agents, zero coordination code, self-healing work queue.

## Dashboard

agentplan ships with a built-in web dashboard for real-time visibility across all your projects.

```bash
# Launch the dashboard (opens in your default browser)
agentplan dashboard --open

# Stop it
agentplan dashboard --stop
```

The dashboard includes:

- **Mission Control home** — project cards with progress rings showing ticket completion
- **Kanban board** — tickets organized by status (pending / in-progress / done / blocked)
- **Ticket detail panel** — slide-over with full ticket info, subtasks, history, and notes
- **Live activity feed** — real-time stream of state transitions as agents work
- **Server-Sent Events (SSE)** — no polling; the UI updates the instant anything changes

The Flask dependency is optional — install it separately:

```bash
pip install agentplan[dashboard]
```

## Why agentplan?

| | agentplan | CrewAI | AutoGen | LangGraph |
|---|---|---|---|---|
| **Install** | `pip install agentplan` | `pip install crewai` | `pip install autogen-agentchat` | `pip install langgraph` |
| **Infrastructure** | None. Single SQLite file. | Python runtime + config | Python runtime + async | Python runtime + graph def |
| **Works with** | Any agent with a terminal | CrewAI agents only | AutoGen agents only | LangGraph nodes only |
| **Integration** | 3 shell commands | Python SDK | Python SDK | Python SDK |
| **Dependencies** | Single package, 0 deps | 30+ packages | 20+ packages | 15+ packages |
| **What it is** | Shared task queue | Agent framework | Agent framework | Orchestration framework |

**agentplan is not a framework.** It doesn't run your agents, define their roles, or manage their conversations. It gives agents that *already exist* a way to coordinate through work.

You already have agents. agentplan gives them a shared to-do list.

## Features

- **Dependency graph** — `next` returns only unblocked tickets; dependencies auto-unblock when blockers complete
- **Circular dependency detection** — prevents invalid dependency graphs before they're created
- **Priority levels** — `high`, `medium`, `low` with smart ordering so urgent work surfaces first
- **Tags** — label tickets with comma-separated tags; filter `next` and `status` by tag
- **Subtasks** — break tickets into smaller steps tracked within the ticket
- **Due dates** — set `--due YYYY-MM-DD`; overdue tickets are prioritized automatically
- **Agent attribution** — pass `--agent <name>` on `start` / `done` for full audit trails
- **Parallel-safe claims** — `claim` uses SQLite `BEGIN IMMEDIATE` to prevent double-assignment across concurrent agents
- **Audit log** — every state transition (pending → in-progress → done) is recorded with timestamp and agent
- **Search** — full-text search across ticket titles and descriptions in all projects
- **Archive / unarchive** — archive completed or abandoned projects without deleting them
- **Ticket editing** — update title, description, priority, tags, or due date at any time
- **Built-in web dashboard** — Kanban board with live SSE updates (Flask optional)
- **Shell completions** — bash, zsh, and fish completions via `agentplan completion <shell>`
- **Multiple output formats** — `full`, `compact` (~50 tokens, ideal for agent prompts), and `json`
- **Auto-completion** — projects close automatically when all tickets are done or skipped
- **Zero runtime dependencies** — Python stdlib only; Flask is an optional extra for the dashboard

## Commands

### Project management

```
agentplan create <title> [--ticket "..."] [--notes "..."]              Create a project with optional inline tickets
agentplan status [project] [--format full|compact|json] [--tag <tag>]  Project status and ticket list
agentplan list [--status active|completed|archived|all] [--all]        List all projects
agentplan close <project> [--abandon]                                  Close (complete or abandon) a project
agentplan archive <project>                                            Archive a project
agentplan remove <project> [--ticket <id>]                             Delete a project or specific ticket
```

### Tickets

```
agentplan ticket add <project> <title> [--desc "..."] [--priority high|medium|low] [--tag tag1,tag2] [--due YYYY-MM-DD] [--depends <ids>]
agentplan ticket done <project> <id...> [--agent <name>] [--note "..."]    Mark done (space or comma-separated IDs)
agentplan ticket skip <project> <id...>                                    Skip ticket(s)
agentplan ticket start <project> <id> [--agent <name>]                     Mark in-progress
agentplan ticket edit <project> <id> [--title "..."] [--desc "..."] [--priority ...] [--tag ...] [--due ...]
agentplan ticket list <project>                                             List all tickets
```

### Agent workflow

```
agentplan next [project] [--format compact|json] [--tag <tag>]   Next unblocked ticket(s)
agentplan claim <project> [--agent <name>] [--tag <tag>]         Atomically claim next unblocked ticket
```

### Dependencies

```
agentplan depend <project> <ticket_id> --on <ids>      Add dependency (comma-separated IDs)
agentplan undepend <project> <ticket_id> --on <ids>    Remove a dependency
```

### Subtasks

```
agentplan subtask add <project> <ticket_id> <title>    Add a subtask to a ticket
agentplan subtask done <project> <ticket_id> <id>      Mark subtask done
agentplan subtask list <project> <ticket_id>           List subtasks
```

### Notes, logs, attachments

```
agentplan note <project> [ticket_id] <text>            Set a note on a project or ticket
agentplan log <project> <entry>                        Add a timestamped log entry
agentplan attach <project> <label> <location>          Attach a file or URL reference
```

### History & search

```
agentplan history <project> <ticket_id>    Show full state-transition history for a ticket
agentplan search <query>                   Search ticket titles/descriptions across all projects
```

### Utilities

```
agentplan completion {bash|zsh|fish}                              Print shell completion script
agentplan version                                                 Show installed version
agentplan dashboard [--port N] [--host H] [--open] [--stop]      Web dashboard
```

## Output Formats

**Full** (default for `status`):
```
0/4 done, 2 blocked, next: [1] Set up database schema
Build my app [active] — 0/4 done
  ○ 1. Set up database schema [priority: none]
  ○ 2. Build API endpoints [priority: none]
  ⏳ 3. Write tests [priority: none] (blocked — waiting on 2)
  ⏳ 4. Deploy to production [priority: none] (blocked — waiting on 1, 2, 3)
```

**Compact** (~50 tokens, optimized for agent context windows):
```
📋 Build my app: [1] Set up database schema ○ (priority: none), [2] Build API endpoints ○ (priority: none)
```

**JSON** (for programmatic use):
```json
{"id": 1, "title": "Set up database schema", "status": "pending", "project": "build-my-app"}
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `AGENTPLAN_DIR` | `~/.agentplan` | Database directory |
| `AGENTPLAN_DB` | `~/.agentplan/agentplan.db` | Database file path |

## Compatible Platforms

agentplan works with any agent or tool that can execute shell commands:

- **[OpenClaw](https://openclaw.ai)** — Multi-agent orchestration via cron jobs
- **[Claude Code](https://docs.anthropic.com/en/docs/claude-code)** — Anthropic's CLI agent
- **[OpenAI Codex](https://openai.com/index/openai-codex/)** — OpenAI's coding agent
- **Cron jobs** — Scheduled autonomous work loops
- **CI/CD pipelines** — GitHub Actions, Jenkins, etc.
- **Any terminal** — If it can run `agentplan next`, it can coordinate

## License

MIT — [Dushyant Garg](https://github.com/fraction12), 2026
