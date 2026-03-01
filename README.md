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
  <a href="#dashboard">Dashboard</a> ·
  <a href="#commands">Commands</a> ·
  <a href="#why-agentplan">Why agentplan?</a> ·
  <a href="https://github.com/fraction12/agentplan/issues">Issues</a>
</p>

<p align="center">
  <img src="docs/demo.svg" alt="agentplan demo" width="700">
</p>

## Agent Loop Demo

```text
$ agentplan create "Launch docs portal" \
    --ticket "Initialize repo + CI" \
    --ticket "Build docs site shell" \
    --ticket "Write auth middleware" \
    --ticket "Add onboarding guide"
Created project 'Launch docs portal' (launch-docs-portal) with 4 ticket(s)

# agent-a atomically claims the next unblocked ticket
$ agentplan claim launch-docs-portal --agent agent-a
▶ Claimed ticket #1: Initialize repo + CI → in-progress (by agent-a)

$ codex exec --full-auto "Initialize repo + CI"
... creates repo scaffolding, CI workflow, pyproject ...

$ agentplan ticket done launch-docs-portal 1 --agent agent-a
✓ Ticket #1: Initialize repo + CI → done (by agent-a)

# agent-b checks what's left
$ agentplan status launch-docs-portal
1/4 done, 0 blocked, next: [2] Build docs site shell
Launch docs portal [active] — 1/4 done
  ✓ 1. Initialize repo + CI [priority: none] [done_by: agent-a]
  ○ 2. Build docs site shell [priority: none]
  ○ 3. Write auth middleware [priority: none]
  ○ 4. Add onboarding guide [priority: none]

# add a high-priority ticket with a due date
$ agentplan ticket add launch-docs-portal "Deploy to production" \
    --priority high --tag deploy --due 2026-03-15
Added ticket #5: Deploy to production [priority: high]

# make deploy depend on docs site shell
$ agentplan depend launch-docs-portal 5 --on 2
Ticket #5 now depends on: [2]

# deploy is now blocked — won't appear in next
$ agentplan next launch-docs-portal
📋 Launch docs portal: [2] Build docs site shell ○ (priority: none), [3] Write auth middleware ○ (priority: none), [4] Add onboarding guide ○ (priority: none)

$ agentplan status launch-docs-portal
1/5 done, 1 blocked, next: [2] Build docs site shell
Launch docs portal [active] — 1/5 done
  ✓ 1. Initialize repo + CI [priority: none] [done_by: agent-a]
  ○ 2. Build docs site shell [priority: none]
  ○ 3. Write auth middleware [priority: none]
  ○ 4. Add onboarding guide [priority: none]
  ⏳ 5. Deploy to production [priority: high] (blocked — waiting on 2)
```

---

Multiple AI agents. One shared work queue. Zero infrastructure.

`agentplan` gives your agents a persistent task queue with dependency resolution. Any agent that can run shell commands can use it — Claude Code, Codex, OpenClaw, or any CLI-capable tool.

No SDK. No framework. No Python dependencies beyond stdlib. Three commands cover 90% of usage:

```bash
agentplan next myproject           # What should I work on?
agentplan ticket done myproject 3  # Done with ticket 3
agentplan ticket add myproject "new thing I found"
```

## Quickstart

```bash
pip install agentplan
```

```bash
agentplan create "Build my app" \
  --ticket "Set up database schema" \
  --ticket "Build API endpoints" \
  --ticket "Write tests" \
  --ticket "Deploy to production"

# tests need API first, deploy needs everything
agentplan depend build-my-app 3 --on 2
agentplan depend build-my-app 4 --on 1,2,3

agentplan next build-my-app
# → [1] Set up database schema ○ (priority: none), [2] Build API endpoints ○ (priority: none)
```

## The Agent Loop

```
┌─────────────────────────────────────────────┐
│  Agent A (cron, every 15 min)               │
│  1. agentplan claim myproject --agent a     │
│  2. Do the work                             │
│  3. agentplan ticket done myproject <id>    │
└─────────────────────────────────────────────┘
         ↕ shared SQLite queue
┌─────────────────────────────────────────────┐
│  Agent B (cron, offset by 8 min)            │
│  1. agentplan status myproject              │
│  2. Review what Agent A did                 │
│  3. agentplan ticket add myproject "..."    │
└─────────────────────────────────────────────┘
```

**Agent A** claims the next unblocked ticket, does the work, marks it done. **Agent B** reviews, spots issues, adds new tickets. The queue is self-sustaining — no coordinator, no orchestrator, no message passing.

### Real-world example: OpenClaw + Codex

```bash
# Cron job fires every 15 minutes
CLAIMED=$(agentplan claim my-redesign --agent codex)
if [ -z "$CLAIMED" ]; then echo "All done"; exit 0; fi

TICKET_ID=$(echo "$CLAIMED" | grep -o '#[0-9]*' | head -1 | tr -d '#')
TASK=$(echo "$CLAIMED" | sed 's/.*: //' | sed 's/ →.*//')

codex exec --full-auto "$TASK"

agentplan ticket done my-redesign "$TICKET_ID"
```

A second cron (running a cheaper model) reviews and adds tickets:

```bash
agentplan status my-redesign
# ...inspect recent changes...
agentplan ticket add my-redesign "Fix: button hover state missing"
```

Two agents, zero coordination code, self-healing work queue.

## Dashboard

agentplan ships a local web dashboard for human oversight. It reads from and writes to the same SQLite database your agents use.

```bash
# Install dashboard dependency
pip install agentplan[dashboard]

# Start and open in browser
agentplan dashboard --open

# Stop the running dashboard
agentplan dashboard --stop

# Custom port
agentplan dashboard --port 8080 --open
```

The dashboard provides:

- **Kanban board** — tickets organized by status (pending, in-progress, done, skipped, blocked) across all active projects
- **Mission Control** — project-level summary with progress bars, agent attribution, and dependency visibility
- **Live activity feed** — real-time audit log of every state transition, claim, and ticket change as agents work

The dashboard is read/write — you can create tickets, update priorities, and mark work done directly from the UI without touching the CLI.

## Why agentplan?

| | agentplan | CrewAI | AutoGen | LangGraph |
|---|---|---|---|---|
| **Install** | `pip install agentplan` | `pip install crewai` | `pip install autogen-agentchat` | `pip install langgraph` |
| **Infrastructure** | None. SQLite file. | Python runtime + config | Python runtime + async | Python runtime + graph def |
| **Works with** | Any agent with a terminal | CrewAI agents only | AutoGen agents only | LangGraph nodes only |
| **Integration** | 3 shell commands | Python SDK | Python SDK | Python SDK |
| **Dependencies** | Zero (stdlib only) | 30+ packages | 20+ packages | 15+ packages |
| **What it is** | Shared task queue | Agent framework | Agent framework | Orchestration framework |

**agentplan is not a framework.** It doesn't run your agents, define roles, or manage conversations. It gives agents that *already exist* a way to coordinate through work.

## Features

1. **Dependency resolution** — `next` and `claim` return only unblocked tickets; blocked tickets show what they're waiting on
2. **Circular dependency detection** — invalid dependency graphs are rejected before they happen
3. **Priority levels** — `high`, `medium`, `low`, or `none` per ticket; highest-priority unblocked work surfaces first
4. **Tags** — label tickets with `--tag` and filter `claim` by tag for role-based agent routing
5. **Subtasks** — lightweight checklists inside tickets (`subtask add/done/list`)
6. **Due dates** — set `--due YYYY-MM-DD` per ticket; visible in status output
7. **Agent attribution** — `--agent <name>` on `claim`/`done`/`start`; tracked in history and status
8. **Parallel-safe claims** — `claim` is atomic; two agents racing won't grab the same ticket
9. **Audit log / history** — every state transition timestamped and queryable via `history`
10. **Search** — full-text search across ticket titles and descriptions across all projects
11. **Archive** — remove completed or abandoned projects from the active list
12. **Ticket editing** — update title, description, priority, tags, or due date after creation
13. **Dashboard** — local web UI with Kanban board, Mission Control, and live activity feed
14. **Shell completions** — bash, zsh, and fish tab-completion via `agentplan completion`
15. **Auto-completion** — projects close automatically when all tickets are done or skipped
16. **Multiple output formats** — `full`, `compact` (~50 tokens for agent context windows), and `json`
17. **Zero dependencies** — Python stdlib only; no virtual environment required

## Commands

### Projects

```bash
agentplan create <title> [--ticket "..."] [--ticket "..."]
agentplan list [--status active|closed|archived]
agentplan status [project]
agentplan close <project> [--abandon]
agentplan archive <project>
agentplan remove <project>
```

### Tickets

```bash
agentplan ticket add <project> <title> [--priority high|medium|low] [--tag TAGS] [--due YYYY-MM-DD] [--desc TEXT] [--depends IDS]
agentplan ticket done <project> <id...> [--agent NAME]
agentplan ticket skip <project> <id...>
agentplan ticket start <project> <id> [--agent NAME]
agentplan ticket edit <project> <id> [--title TEXT] [--priority ...] [--tag TAGS] [--due DATE]
agentplan ticket list <project>
```

### Queue

```bash
agentplan next [project] [--tag TAG]
agentplan claim <project> [--agent NAME] [--tag TAG]
```

### Dependencies

```bash
agentplan depend <project> <ticket_id> --on <id[,id,...]>
agentplan undepend <project> <ticket_id> --on <id>
```

### Subtasks

```bash
agentplan subtask add <project> <ticket_id> <title>
agentplan subtask done <project> <ticket_id> <subtask_id>
agentplan subtask list <project> <ticket_id>
```

### Search & History

```bash
agentplan search <query>
agentplan history <project> <ticket_id>
```

### Dashboard

```bash
agentplan dashboard [--port PORT] [--open] [--stop]
```

### Misc

```bash
agentplan completion {bash|zsh|fish}
agentplan version
```

## Output Formats

**Full** (default):

```
Launch docs portal [active] — 1/5 done
  ✓ 1. Initialize repo + CI [priority: none] [done_by: agent-a]
  ○ 2. Build docs site shell [priority: none]
  ○ 3. Write auth middleware [priority: none]
  ○ 4. Add onboarding guide [priority: none]
  ⏳ 5. Deploy to production [priority: high] (blocked — waiting on 2)
```

**Compact** (~50 tokens, optimized for agent context windows):

```
📋 Launch docs portal: [2] Build docs site shell ○ (priority: none), [3] Write auth middleware ○ (priority: none), [4] Add onboarding guide ○ (priority: none)
```

**JSON** (`--format json`): machine-readable for scripting and agent parsing.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `AGENTPLAN_DIR` | `~/.agentplan` | Database directory |
| `AGENTPLAN_DB` | `~/.agentplan/agentplan.db` | Full path override |

## Compatible Platforms

agentplan works with any agent or tool that can execute shell commands:

- **[OpenClaw](https://openclaw.ai)** — Multi-agent orchestration via cron jobs
- **[Claude Code](https://docs.anthropic.com/en/docs/claude-code)** — Anthropic's CLI agent
- **[OpenAI Codex](https://openai.com/index/openai-codex/)** — OpenAI's coding agent
- **Cron jobs** — Scheduled autonomous work loops
- **CI/CD pipelines** — GitHub Actions, Jenkins, etc.
- **Any terminal** — If it can run a shell command, it can coordinate

## License

MIT — [Dushyant Garg](https://github.com/fraction12), 2026
