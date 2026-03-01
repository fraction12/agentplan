#!/usr/bin/env python3
"""agentplan — Project management CLI for AI agents.

Thin entry point that wires CLI and DB modules.
"""

from db import get_connection, init_db
from cli import __version__, _claim_next_ticket, main


if __name__ == "__main__":
    main()
