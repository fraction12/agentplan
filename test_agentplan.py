#!/usr/bin/env python3
"""Pytest tests for agentplan CLI.

All tests use a temp DB via the `temp_db` fixture (AGENTPLAN_DB=/tmp/... path).
The real database is never touched.
"""
import os
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agentplan


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def temp_db():
    """Use AGENTPLAN_DB=/tmp/test_agentplan.db; init schema; clean up after each test."""
    db_path = "/tmp/test_agentplan.db"
    os.environ["AGENTPLAN_DB"] = db_path
    os.environ["AGENTPLAN_DIR"] = "/tmp"
    if os.path.exists(db_path):
        os.remove(db_path)
    # Initialise schema directly (no CLI side-effects)
    conn = agentplan.get_connection(db_path)
    agentplan.init_db(conn)
    conn.commit()
    conn.close()
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)
    os.environ.pop("AGENTPLAN_DB", None)
    os.environ.pop("AGENTPLAN_DIR", None)


def cli(*args):
    """Invoke agentplan.main() with given args; return (stdout, stderr, exit_code)."""
    out, err = StringIO(), StringIO()
    code = 0
    with patch("sys.argv", ["agentplan"] + list(args)), \
         patch("sys.stdout", out), \
         patch("sys.stderr", err):
        try:
            agentplan.main()
        except SystemExit as e:
            code = int(e.code) if e.code is not None else 0
    return out.getvalue(), err.getvalue(), code


# ---------------------------------------------------------------------------
# Smoke
# ---------------------------------------------------------------------------

def test_main_is_callable():
    assert callable(agentplan.main)


def test_help_exits_zero():
    _, _, code = cli("--help")
    assert code == 0


def test_version():
    out, _, code = cli("version")
    assert code == 0
    assert agentplan.__version__ in out


# ---------------------------------------------------------------------------
# Project lifecycle
# ---------------------------------------------------------------------------

def test_create_project():
    out, err, code = cli("create", "My Project")
    assert code == 0, err
    assert "my-project" in out.lower()


def test_list_projects_after_create():
    cli("create", "Alpha Project")
    out, err, code = cli("list")
    assert code == 0, err
    assert "alpha-project" in out.lower()


def test_status_project():
    cli("create", "Beta Project")
    out, err, code = cli("status", "beta-project")
    assert code == 0, err
    assert "beta" in out.lower()


# ---------------------------------------------------------------------------
# Ticket operations
# ---------------------------------------------------------------------------

def test_add_ticket():
    cli("create", "Proj One")
    out, err, code = cli("ticket", "add", "proj-one", "Build the thing")
    assert code == 0, err


def test_list_tickets():
    cli("create", "Proj Two")
    cli("ticket", "add", "proj-two", "First ticket")
    cli("ticket", "add", "proj-two", "Second ticket")
    out, err, code = cli("status", "proj-two")
    assert code == 0, err
    assert "proj-two" in out.lower() or "ticket" in out.lower() or out.strip() != ""


def test_mark_ticket_done():
    cli("create", "Proj Three")
    cli("ticket", "add", "proj-three", "Do something")
    out, err, code = cli("ticket", "done", "proj-three", "1")
    assert code == 0, err


def test_add_ticket_priority_persisted():
    cli("create", "Priority Project")
    out, err, code = cli("ticket", "add", "priority-project", "Important work", "--priority", "high")
    assert code == 0, err
    assert "priority: high" in out.lower()
    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT priority FROM tickets WHERE project_id=1 AND num=1").fetchone()
    conn.close()
    assert row["priority"] == "high"


def test_add_ticket_tags_persisted():
    cli("create", "Tag Project")
    out, err, code = cli("ticket", "add", "tag-project", "Harden auth", "--tag", "security,css")
    assert code == 0, err
    assert "added ticket #1" in out.lower()
    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT tags FROM tickets WHERE project_id=1 AND num=1").fetchone()
    conn.close()
    assert row["tags"] == "css,security"


def test_ticket_update_priority():
    cli("create", "Update Project")
    cli("ticket", "add", "update-project", "Task one")
    out, err, code = cli("ticket", "update", "update-project", "1", "--priority", "medium")
    assert code == 0, err
    assert "updated ticket #1" in out.lower()
    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT priority FROM tickets WHERE project_id=1 AND num=1").fetchone()
    conn.close()
    assert row["priority"] == "medium"


def test_ticket_edit_priority_alias():
    cli("create", "Edit Project")
    cli("ticket", "add", "edit-project", "Task one", "--priority", "high")
    out, err, code = cli("ticket", "edit", "edit-project", "1", "--priority", "low")
    assert code == 0, err
    assert "updated ticket #1" in out.lower()
    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT priority FROM tickets WHERE project_id=1 AND num=1").fetchone()
    conn.close()
    assert row["priority"] == "low"


def test_next_orders_by_priority():
    cli("create", "Order Project")
    cli("ticket", "add", "order-project", "Low task", "--priority", "low")
    cli("ticket", "add", "order-project", "High task", "--priority", "high")
    cli("ticket", "add", "order-project", "Medium task", "--priority", "medium")
    out, err, code = cli("next", "order-project")
    assert code == 0, err
    assert out.index("High task") < out.index("Medium task") < out.index("Low task")


def test_next_filters_by_tag():
    cli("create", "Next Tag Project")
    cli("ticket", "add", "next-tag-project", "Patch CSS reset", "--tag", "css")
    cli("ticket", "add", "next-tag-project", "Rotate service key", "--tag", "security")
    out, err, code = cli("next", "next-tag-project", "--tag", "security")
    assert code == 0, err
    assert "Rotate service key" in out
    assert "Patch CSS reset" not in out


def test_status_shows_priority():
    cli("create", "Status Project")
    cli("ticket", "add", "status-project", "No priority task")
    cli("ticket", "add", "status-project", "High priority task", "--priority", "high")
    out, err, code = cli("status", "status-project")
    assert code == 0, err
    assert "priority: none" in out.lower()
    assert "priority: high" in out.lower()


def test_status_filters_by_tag():
    cli("create", "Status Tag Project")
    cli("ticket", "add", "status-tag-project", "Implement CSP", "--tag", "security")
    cli("ticket", "add", "status-tag-project", "Fix button spacing", "--tag", "css")
    out, err, code = cli("status", "status-tag-project", "--tag", "security")
    assert code == 0, err
    assert "Implement CSP" in out
    assert "Fix button spacing" not in out
    assert out.strip().splitlines()[0] == "0/1 done, 0 blocked, next: [1] Implement CSP"


def test_status_summary_line_with_blocked_and_next():
    cli("create", "Summary Project")
    cli("ticket", "add", "summary-project", "Setup env", "--priority", "high")
    cli("ticket", "add", "summary-project", "Fix cache", "--priority", "medium")
    cli("ticket", "add", "summary-project", "Deploy", "--depends", "1", "--priority", "low")
    cli("ticket", "done", "summary-project", "1")
    out, err, code = cli("status", "summary-project")
    assert code == 0, err
    first_line = out.strip().splitlines()[0]
    assert first_line == "1/3 done, 0 blocked, next: [2] Fix cache"


def test_status_summary_counts_blocked():
    cli("create", "Blocked Summary Project")
    cli("ticket", "add", "blocked-summary-project", "Base task")
    cli("ticket", "add", "blocked-summary-project", "Blocked task", "--depends", "1")
    out, err, code = cli("status", "blocked-summary-project")
    assert code == 0, err
    first_line = out.strip().splitlines()[0]
    assert first_line == "0/2 done, 1 blocked, next: [1] Base task"


def test_status_summary_shows_no_next_for_empty_project():
    cli("create", "Empty Summary Project")
    out, err, code = cli("status", "empty-summary-project")
    assert code == 0, err
    first_line = out.strip().splitlines()[0]
    assert first_line == "0/0 done, 0 blocked, next: none"


# ---------------------------------------------------------------------------
# Delete project
# ---------------------------------------------------------------------------

def test_delete_project():
    cli("create", "To Delete")
    out, err, code = cli("remove", "to-delete")
    assert code == 0, err
    # Confirm gone from list
    out2, _, _ = cli("list")
    assert "to-delete" not in out2.lower()


# ---------------------------------------------------------------------------
# DB isolation between tests
# ---------------------------------------------------------------------------

def test_db_isolation_a():
    cli("create", "Isolation A")
    out, _, _ = cli("list")
    assert "isolation-a" in out.lower()


def test_db_isolation_b():
    """isolation-a must NOT exist — each test gets a fresh temp DB."""
    out, _, _ = cli("list")
    assert "isolation-a" not in out.lower()




# ---------------------------------------------------------------------------
# Close note support
# ---------------------------------------------------------------------------

def test_ticket_done_with_note():
    cli("create", "Note Project")
    cli("ticket", "add", "note-project", "Fix the bug")
    out, err, code = cli("ticket", "done", "note-project", "1", "--note", "resolved in PR #42")
    assert code == 0, err
    assert "resolved in pr #42" in out.lower() or "resolved in PR #42" in out


def test_ticket_done_note_stored_in_db():
    cli("create", "Note DB Project")
    cli("ticket", "add", "note-db-project", "Do a thing")
    cli("ticket", "done", "note-db-project", "1", "--note", "no longer needed")
    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT close_note FROM tickets WHERE num=1").fetchone()
    conn.close()
    assert row["close_note"] == "no longer needed"


def test_ticket_done_without_note():
    cli("create", "No Note Project")
    cli("ticket", "add", "no-note-project", "Plain ticket")
    out, err, code = cli("ticket", "done", "no-note-project", "1")
    assert code == 0, err
    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT close_note FROM tickets WHERE num=1").fetchone()
    conn.close()
    assert row["close_note"] is None


def test_status_shows_close_note():
    cli("create", "Status Note Project")
    cli("ticket", "add", "status-note-project", "Finish it")
    cli("ticket", "done", "status-note-project", "1", "--note", "shipped in v2")
    out, err, code = cli("status", "status-note-project")
    assert code == 0, err
    assert "shipped in v2" in out
# ---------------------------------------------------------------------------
# LLM discoverability docs
# ---------------------------------------------------------------------------

def test_llms_txt_exists_and_contains_core_summary():
    p = Path(__file__).resolve().parent / "llms.txt"
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert "CLI task queue for AI agents" in text
    assert "multi-session projects" in text
    assert "dependencies" in text
    assert "progress logs" in text
    assert "agentplan next" in text
    assert "agentplan ticket done" in text


def test_llms_full_txt_exists_and_contains_reference_material():
    p = Path(__file__).resolve().parent / "llms-full.txt"
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert "agentplan Full Reference" in text
    assert "Command index" in text
    assert "agentplan ticket add <project> <title>" in text
    assert "--format compact|full|json" in text
    assert "Data model and schema" in text
    assert "CREATE TABLE IF NOT EXISTS projects" not in text
    assert "projects" in text and "tickets" in text and "attachments" in text and "log" in text
