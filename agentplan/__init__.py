#!/usr/bin/env python3
"""agentplan — Project management CLI for AI agents.

Thin entry point that wires CLI and DB modules.
"""

from agentplan.db import get_connection, init_db, ensure_space_directory
from agentplan.cli import __version__, _claim_next_ticket, main
from agentplan.models import HistoryEntry, Project, Subtask, Ticket


if __name__ == "__main__":
    main()
