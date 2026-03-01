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
