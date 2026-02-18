# agentplan

Project management CLI for AI agents. Track multi-step work with dependency resolution across sessions.

## Why?

AI agents lose context between sessions. `agentplan` persists a task graph in SQLite and instantly answers: **"What should I work on next?"**

The killer feature is **dependency resolution** — `agentplan next` computes which tickets are unblocked (all dependencies done/skipped). This is what makes it better than a markdown checklist.

## Install

```bash
pip install .
```

Or run directly:

```bash
python agentplan.py <command>
```

## Quick Start

```bash
# Create a project with tickets
agentplan create "Build my app" \
  --ticket "Write code" \
  --ticket "Write tests" \
  --ticket "Deploy"

# Add dependencies
agentplan depend build-my-app 2 --on 1    # tests depend on code
agentplan depend build-my-app 3 --on 1,2  # deploy depends on both

# What's next?
agentplan next
# 📋 Build my app: [1] Write code ○

# Work on it
agentplan ticket start build-my-app 1
agentplan ticket done build-my-app 1

# What's next now?
agentplan next
# 📋 Build my app: [2] Write tests ○

# Check status
agentplan status build-my-app
# Build my app [active] — 1/3 done
#   ✓ 1. Write code
#   ○ 2. Write tests
#   ⏳ 3. Deploy (blocked — waiting on 2)
```

## Commands

```
agentplan init                              # Initialize database
agentplan create <title> [--ticket "..."]   # Create project
agentplan ticket add <project> <title>      # Add ticket
agentplan ticket done <project> <id...>     # Mark done
agentplan ticket skip <project> <id...>     # Skip ticket
agentplan ticket start <project> <id>       # Mark in-progress
agentplan ticket list <project>             # List tickets
agentplan next [project]                    # Show unblocked tickets
agentplan status [project] [--format ...]   # Project status
agentplan list [--status ...]               # List projects
agentplan attach <project> <label> <loc>    # Attach file/URL
agentplan log <project> <entry>             # Add log entry
agentplan close <project> [--abandon]       # Close project
agentplan note <project> <text>             # Set note
agentplan depend <project> <id> --on <ids>  # Add dependencies
agentplan remove <project> [--ticket <id>]  # Remove project/ticket
agentplan version                           # Show version
```

## Features

- **Dependency resolution** — `next` shows only unblocked tickets
- **Circular dependency detection** — prevents invalid dependency graphs
- **Auto-complete** — project completes when all tickets are done/skipped
- **Multiple output formats** — full, compact (~50 tokens), JSON
- **Attachments** — link files and URLs to projects or tickets
- **Progress log** — timestamped entries for what happened
- **Zero dependencies** — stdlib only, single Python file

## Output Formats

**Full** (`--format full`, default):
```
My Project [active] — 2/4 done
  ✓ 1. Setup
  ✓ 2. Build
  ▶ 3. Test (in-progress)
  ⏳ 4. Deploy (blocked — waiting on 3)
```

**Compact** (`--format compact`):
```
📋 My Project: 2/4 done | Next: [3] Test ▶
```

**JSON** (`--format json`):
```json
{"id": 1, "slug": "my-project", "title": "My Project", ...}
```

## Configuration

| Env Variable | Default | Description |
|---|---|---|
| `AGENTPLAN_DIR` | `~/.agentplan` | Database directory |
| `AGENTPLAN_DB` | `~/.agentplan/agentplan.db` | Database file path |

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | No results (for hook scripts) |
| 2 | User error |

## License

MIT — Dushyant Garg, 2026
