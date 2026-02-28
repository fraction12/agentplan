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
  <a href="#why-agentplan">Why agentplan?</a> ·
  <a href="https://discord.com/invite/clawd">Community</a>
</p>

---

Multiple AI agents. One shared work queue. Zero infrastructure.

`agentplan` is a CLI that gives your agents a persistent task queue with dependency resolution. Any agent that can run shell commands can use it — Claude Code, Codex, GPT, Cursor, Windsurf, [OpenClaw](https://openclaw.ai), or your own.

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

# Add dependencies — tests need API, deploy needs everything
agentplan depend build-my-app 3 --on 2
agentplan depend build-my-app 4 --on 1,2,3

# Ask what's next
agentplan next build-my-app
# → [1] Set up database schema
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

## Why agentplan?

| | agentplan | CrewAI | AutoGen | LangGraph |
|---|---|---|---|---|
| **Install** | `pip install agentplan` | `pip install crewai` | `pip install autogen-agentchat` | `pip install langgraph` |
| **Infrastructure** | None. Single SQLite file. | Python runtime + config | Python runtime + async | Python runtime + graph def |
| **Works with** | Any agent with a terminal | CrewAI agents only | AutoGen agents only | LangGraph nodes only |
| **Integration** | 3 shell commands | Python SDK | Python SDK | Python SDK |
| **Dependencies** | Zero (stdlib only) | 30+ packages | 20+ packages | 15+ packages |
| **What it is** | Shared task queue | Agent framework | Agent framework | Orchestration framework |

**agentplan is not a framework.** It doesn't run your agents, define their roles, or manage their conversations. It gives agents that *already exist* a way to coordinate through work.

You already have agents. agentplan gives them a shared to-do list.

## Features

- **Dependency resolution** — `next` returns only unblocked tickets. No manual sequencing.
- **Circular dependency detection** — prevents invalid dependency graphs before they happen.
- **Auto-completion** — projects close automatically when all tickets are done or skipped.
- **Multiple output formats** — `full`, `compact` (~50 tokens, ideal for agent prompts), and `json`.
- **Progress logging** — timestamped entries for cross-session continuity.
- **Attachments** — link files, URLs, or references to any project or ticket.
- **Zero dependencies** — Python stdlib only. Single file. No virtual environment needed.
- **SQLite storage** — fast, reliable, single-file persistence at `~/.agentplan/agentplan.db`.

## Commands

```
agentplan create <title> [--ticket "..."]   # Create project with tickets
agentplan ticket add <project> <title>      # Add a ticket
agentplan ticket done <project> <id...>     # Mark ticket(s) done
agentplan ticket skip <project> <id...>     # Skip ticket(s)
agentplan ticket start <project> <id>       # Mark in-progress
agentplan ticket list <project>             # List all tickets
agentplan next [project]                    # Next unblocked ticket
agentplan status [project]                  # Project status
agentplan depend <project> <id> --on <ids>  # Add dependencies
agentplan log <project> <entry>             # Log progress
agentplan attach <project> <label> <loc>    # Attach file/URL
agentplan close <project> [--abandon]       # Close project
agentplan list [--status ...]               # List all projects
agentplan remove <project> [--ticket <id>]  # Remove project/ticket
agentplan version                           # Show version
```

## Output Formats

**Full** (default):
```
My Project [active] — 2/4 done
  ✓ 1. Setup
  ✓ 2. Build
  ▶ 3. Test (in-progress)
  ⏳ 4. Deploy (blocked — waiting on 3)
```

**Compact** (~50 tokens, optimized for agent context windows):
```
📋 My Project: 2/4 done | Next: [3] Test ▶
```

**JSON** (for programmatic use):
```json
{"id": 1, "slug": "my-project", "title": "My Project", "status": "active", "done": 2, "total": 4}
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
- **[Cursor](https://cursor.sh)** / **[Windsurf](https://codeium.com/windsurf)** — AI-powered editors
- **Cron jobs** — Scheduled autonomous work loops
- **CI/CD pipelines** — GitHub Actions, Jenkins, etc.
- **Any terminal** — If it can run `agentplan next`, it can coordinate

## License

MIT — [Dushyant Garg](https://github.com/fraction12), 2026
