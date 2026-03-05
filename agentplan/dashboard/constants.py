"""Dashboard display constants."""

from agentplan.db import VALID_TICKET_STATES

_STATUS_PREFERRED = ["pending", "in-progress", "blocked", "needs-review", "failed", "done", "skipped"]
STATUS_ORDER = [state for state in _STATUS_PREFERRED if state in VALID_TICKET_STATES]

KANBAN_STATUS_ORDER = [state for state in STATUS_ORDER if state != "skipped"]
KANBAN_STATUS_LABELS = {
    "pending": "Todo",
    "in-progress": "In Progress",
    "blocked": "Blocked",
    "needs-review": "Needs Review",
    "failed": "Failed",
    "done": "Done",
}

TAG_TONES = ("blue", "purple", "teal", "amber", "rose")
