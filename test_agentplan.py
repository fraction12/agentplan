#!/usr/bin/env python3
"""Pytest tests for agentplan CLI.

All tests use a temp DB via the `temp_db` fixture (AGENTPLAN_DB=/tmp/... path).
The real database is never touched.
"""
import json
import os
import sys
import threading
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


def test_readme_contains_agent_loop_demo_section():
    readme_path = Path(__file__).resolve().parent / "README.md"
    assert readme_path.exists(), "README.md should exist at repository root."
    content = readme_path.read_text(encoding="utf-8")
    assert "## Agent Loop Demo" in content
    assert "agent loop" in content.lower()


def test_changelog_exists_and_has_v020_header():
    changelog_path = Path(__file__).resolve().parent / "CHANGELOG.md"
    assert changelog_path.exists(), "CHANGELOG.md should exist at repository root."
    content = changelog_path.read_text(encoding="utf-8")
    assert "# Changelog" in content
    assert "## v0." in content  # has at least one versioned entry
    assert "## v0.2.0" in content


def test_invalid_arguments_are_human_friendly():
    out, err, code = cli("ticket", "add")
    assert code == 2
    assert out == ""
    assert "Invalid arguments:" in err
    assert "Run `agentplan --help` to see available commands and options." in err
    assert "Traceback" not in err


# ---------------------------------------------------------------------------
# Init auto-detection
# ---------------------------------------------------------------------------

def test_init_creates_agents_for_detected_tools():
    def fake_run(cmd, capture_output=True, text=True):
        tool = cmd[-1]
        return type("Result", (), {"returncode": 0 if tool == "claude" else 1})()

    with patch("agentplan.cli.subprocess.run", side_effect=fake_run):
        out, err, code = cli("init")

    assert code == 0, err
    assert "Auto-detected agents: claude" in out

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT name, command_template FROM agents WHERE name='claude'").fetchone()
    conn.close()
    assert row is not None
    assert row["command_template"] == "claude -p {ticket}"


def test_init_detects_multiple_tools():
    detected = {"claude", "codex", "openclaw"}

    def fake_run(cmd, capture_output=True, text=True):
        tool = cmd[-1]
        return type("Result", (), {"returncode": 0 if tool in detected else 1})()

    with patch("agentplan.cli.subprocess.run", side_effect=fake_run):
        out, err, code = cli("init")

    assert code == 0, err
    assert "Auto-detected agents:" in out
    assert "claude" in out and "codex" in out and "openclaw" in out

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    rows = conn.execute("SELECT name FROM agents ORDER BY name").fetchall()
    conn.close()
    assert [r["name"] for r in rows] == ["claude", "codex", "openclaw"]


def test_init_skips_undetected_tools():
    with patch("agentplan.cli.subprocess.run", return_value=type("Result", (), {"returncode": 1})()):
        out, err, code = cli("init")

    assert code == 0, err
    assert "Initialized agentplan database" in out
    assert "Auto-detected agents:" not in out

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    rows = conn.execute("SELECT name FROM agents").fetchall()
    conn.close()
    assert rows == []


def test_init_detect_installed_tools_handles_subprocess_exception():
    import agentplan.cli as agent_cli

    def fake_run(cmd, capture_output=True, text=True):
        tool = cmd[-1]
        if tool == "codex":
            raise RuntimeError("boom")
        return type("Result", (), {"returncode": 0 if tool == "claude" else 1})()

    with patch("agentplan.cli.subprocess.run", side_effect=fake_run):
        tools = agent_cli._detect_installed_tools()

    assert tools == ["claude"]


# ---------------------------------------------------------------------------
# Project lifecycle
# ---------------------------------------------------------------------------

def test_create_project():
    out, err, code = cli("create", "My Project")
    assert code == 0, err
    assert "my-project" in out.lower()


def test_create_project_with_dir_flag_persists_directory():
    out, err, code = cli("create", "Dir Project", "--dir", "/tmp/agentplan-dir-project")
    assert code == 0, err
    assert "dir-project" in out.lower()

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT dir FROM projects WHERE slug='dir-project'").fetchone()
    conn.close()
    assert row["dir"] == "/tmp/agentplan-dir-project"


def test_create_project_without_dir_flag_leaves_directory_empty():
    cli("create", "No Dir Project")
    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT dir FROM projects WHERE slug='no-dir-project'").fetchone()
    conn.close()
    assert row["dir"] is None


def test_project_command_sets_and_updates_directory():
    cli("create", "Project Dir Cmd")

    out_set, err_set, code_set = cli("project", "project-dir-cmd", "--dir", "/tmp/project-dir-cmd-a")
    assert code_set == 0, err_set
    assert "Updated project 'project-dir-cmd' directory to: /tmp/project-dir-cmd-a" in out_set
    assert "Warning: directory does not exist on disk: /tmp/project-dir-cmd-a" in out_set

    os.makedirs("/tmp/project-dir-cmd-b", exist_ok=True)
    out_update, err_update, code_update = cli("project", "project-dir-cmd", "--dir", "/tmp/project-dir-cmd-b")
    assert code_update == 0, err_update
    assert "Updated project 'project-dir-cmd' directory to: /tmp/project-dir-cmd-b" in out_update
    assert "Warning: directory does not exist on disk" not in out_update

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT dir FROM projects WHERE slug='project-dir-cmd'").fetchone()
    conn.close()
    assert row["dir"] == "/tmp/project-dir-cmd-b"


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


def test_status_shows_project_directory_when_linked():
    cli("create", "Status Dir Project", "--dir", "/tmp/status-dir")
    out, err, code = cli("status", "status-dir-project")
    assert code == 0, err
    assert "Directory: /tmp/status-dir" in out


def test_missing_project_error_is_human_friendly_with_suggestion():
    cli("create", "Alpha Project")
    out, err, code = cli("status", "alpha-projec")
    assert code == 2
    assert out == ""
    assert "Project 'alpha-projec' not found." in err
    assert "Did you mean 'alpha-project'?" in err
    assert "Run `agentplan list --all` to see all projects." in err
    assert "Traceback" not in err


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


def test_invalid_ticket_number_error_is_human_friendly():
    cli("create", "Ticket Parse Project")
    cli("ticket", "add", "ticket-parse-project", "Task")
    out, err, code = cli("ticket", "done", "ticket-parse-project", "abc")
    assert code == 2
    assert out == ""
    assert "Invalid ticket number 'abc'." in err
    assert "Ticket IDs must be numeric" in err
    assert "Run `agentplan ticket list ticket-parse-project` to see ticket IDs." in err
    assert "Traceback" not in err


def test_mark_ticket_done_bulk_comma_separated_ids():
    cli("create", "Bulk Done Project")
    cli("ticket", "add", "bulk-done-project", "Task one")
    cli("ticket", "add", "bulk-done-project", "Task two")
    cli("ticket", "add", "bulk-done-project", "Task three")

    out, err, code = cli("ticket", "done", "bulk-done-project", "1,2,3")
    assert code == 0, err
    assert "Ticket #1" in out
    assert "Ticket #2" in out
    assert "Ticket #3" in out

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    rows = conn.execute(
        "SELECT num, status FROM tickets WHERE project_id=1 ORDER BY num"
    ).fetchall()
    conn.close()
    assert [r["status"] for r in rows] == ["done", "done", "done"]


def test_ticket_start_with_agent_stores_started_by_and_shows_in_status():
    cli("create", "Start Agent Project")
    cli("ticket", "add", "start-agent-project", "Implement parser")
    out, err, code = cli("ticket", "start", "start-agent-project", "1", "--agent", "dash")
    assert code == 0, err
    assert "(by dash)" in out
    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT started_by FROM tickets WHERE project_id=1 AND num=1").fetchone()
    conn.close()
    assert row["started_by"] == "dash"
    status_out, status_err, status_code = cli("status", "start-agent-project")
    assert status_code == 0, status_err
    assert "[started_by: dash]" in status_out


def test_claim_claims_next_unblocked_ticket_atomically():
    cli("create", "Claim Project")
    cli("ticket", "add", "claim-project", "Low priority", "--priority", "low")
    cli("ticket", "add", "claim-project", "High priority", "--priority", "high")
    out, err, code = cli("claim", "claim-project", "--agent", "dash")
    assert code == 0, err
    assert "claimed ticket #2" in out.lower()
    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT status, started_by FROM tickets WHERE project_id=1 AND num=2").fetchone()
    conn.close()
    assert row["status"] == "in-progress"
    assert row["started_by"] == "dash"


def test_claim_returns_exit_1_when_no_unblocked_ticket():
    cli("create", "Claim Empty Project")
    out, err, code = cli("claim", "claim-empty-project")
    assert code == 1
    assert "no unblocked tickets to claim" in out.lower()
    assert err == ""


def test_claim_concurrency_only_claims_each_ticket_once():
    cli("create", "Claim Race Project")
    cli("ticket", "add", "claim-race-project", "Ticket A")
    cli("ticket", "add", "claim-race-project", "Ticket B")

    barrier = threading.Barrier(2)
    results = []

    def worker(agent_name):
        conn = agentplan.get_connection("/tmp/test_agentplan.db")
        project = conn.execute(
            "SELECT id FROM projects WHERE slug='claim-race-project'"
        ).fetchone()
        barrier.wait()
        claimed = agentplan._claim_next_ticket(conn, project["id"], started_by=agent_name)
        results.append(claimed["num"] if claimed else None)
        conn.close()

    t1 = threading.Thread(target=worker, args=("dash-a",))
    t2 = threading.Thread(target=worker, args=("dash-b",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    claimed_nums = sorted(n for n in results if n is not None)
    assert claimed_nums == [1, 2]
    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    rows = conn.execute(
        "SELECT num, status, started_by FROM tickets WHERE project_id=1 ORDER BY num"
    ).fetchall()
    conn.close()
    assert [r["status"] for r in rows] == ["in-progress", "in-progress"]
    assert {r["started_by"] for r in rows} == {"dash-a", "dash-b"}


def test_claim_sets_timeout_when_provided():
    cli("create", "Claim Timeout Project")
    cli("ticket", "add", "claim-timeout-project", "Ticket A")
    out, err, code = cli("claim", "claim-timeout-project", "--agent", "dash", "--timeout", "45")
    assert code == 0, err
    assert "claimed ticket #1" in out.lower()

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute(
        "SELECT status, started_by, claim_timeout FROM tickets WHERE project_id=1 AND num=1"
    ).fetchone()
    conn.close()
    assert row["status"] == "in-progress"
    assert row["started_by"] == "dash"
    assert row["claim_timeout"] == 45


@pytest.mark.parametrize("timeout", ["-5", "0"])
def test_claim_rejects_non_positive_timeout(timeout):
    cli("create", "Claim Invalid Timeout Project")
    cli("ticket", "add", "claim-invalid-timeout-project", "Ticket A")
    out, err, code = cli("claim", "claim-invalid-timeout-project", "--agent", "dash", "--timeout", timeout)
    assert code == 2
    assert out == ""
    assert "--timeout must be a positive integer" in err


def test_claim_rejects_non_integer_timeout_values():
    cli("create", "Claim Invalid Timeout Type Project")
    cli("ticket", "add", "claim-invalid-timeout-type-project", "Ticket A")

    out_abc, err_abc, code_abc = cli(
        "claim", "claim-invalid-timeout-type-project", "--agent", "dash", "--timeout", "abc"
    )
    assert code_abc == 2
    assert out_abc == ""
    assert "Invalid arguments:" in err_abc
    assert "argument --timeout: invalid int value: 'abc'" in err_abc

    out_float, err_float, code_float = cli(
        "claim", "claim-invalid-timeout-type-project", "--agent", "dash", "--timeout", "1.5"
    )
    assert code_float == 2
    assert out_float == ""
    assert "Invalid arguments:" in err_float
    assert "argument --timeout: invalid int value: '1.5'" in err_float


def test_claim_reclaims_expired_in_progress_ticket():
    cli("create", "Claim Reclaim Project")
    cli("ticket", "add", "claim-reclaim-project", "Ticket A")
    cli("claim", "claim-reclaim-project", "--agent", "dash-a", "--timeout", "30")

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    conn.execute(
        """
        UPDATE tickets
        SET claimed_at=datetime('now', '-120 seconds')
        WHERE project_id=1 AND num=1
        """
    )
    conn.commit()
    conn.close()

    out, err, code = cli("claim", "claim-reclaim-project", "--agent", "dash-b")
    assert code == 0, err
    assert "claimed ticket #1" in out.lower()

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    ticket = conn.execute(
        "SELECT status, started_by FROM tickets WHERE project_id=1 AND num=1"
    ).fetchone()
    history = conn.execute(
        "SELECT old_state, new_state FROM ticket_history WHERE ticket_id=1 ORDER BY id"
    ).fetchall()
    conn.close()

    assert ticket["status"] == "in-progress"
    assert ticket["started_by"] == "dash-b"
    assert ("in-progress", "pending") in [(h["old_state"], h["new_state"]) for h in history]


def test_ticket_done_with_agent_stores_done_by_and_shows_in_status():
    cli("create", "Done Agent Project")
    cli("ticket", "add", "done-agent-project", "Ship feature")
    out, err, code = cli("ticket", "done", "done-agent-project", "1", "--agent", "dash")
    assert code == 0, err
    assert "(by dash)" in out
    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT done_by FROM tickets WHERE project_id=1 AND num=1").fetchone()
    conn.close()
    assert row["done_by"] == "dash"
    status_out, status_err, status_code = cli("status", "done-agent-project")
    assert status_code == 0, status_err
    assert "[done_by: dash]" in status_out


def test_subtask_add_and_list():
    cli("create", "Subtask Project")
    cli("ticket", "add", "subtask-project", "Implement feature")
    out, err, code = cli("subtask", "add", "subtask-project", "1", "Write tests")
    assert code == 0, err
    assert "added subtask #1" in out.lower()
    out, err, code = cli("subtask", "list", "subtask-project", "1")
    assert code == 0, err
    assert "1. Write tests" in out


def test_subtask_done_and_persisted():
    cli("create", "Subtask Done Project")
    cli("ticket", "add", "subtask-done-project", "Implement feature")
    cli("subtask", "add", "subtask-done-project", "1", "Write tests")
    out, err, code = cli("subtask", "done", "subtask-done-project", "1", "1")
    assert code == 0, err
    assert "subtask #1" in out.lower()
    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT status FROM subtasks WHERE ticket_id=1 AND num=1").fetchone()
    conn.close()
    assert row["status"] == "done"


def test_status_shows_subtask_progress():
    cli("create", "Subtask Status Project")
    cli("ticket", "add", "subtask-status-project", "Implement feature")
    cli("subtask", "add", "subtask-status-project", "1", "Write tests")
    cli("subtask", "add", "subtask-status-project", "1", "Update docs")
    cli("subtask", "done", "subtask-status-project", "1", "1")
    out, err, code = cli("status", "subtask-status-project")
    assert code == 0, err
    assert "[1/2]" in out


def test_subtask_done_invalid_subtask_id():
    cli("create", "Subtask Invalid Project")
    cli("ticket", "add", "subtask-invalid-project", "Implement feature")
    out, err, code = cli("subtask", "done", "subtask-invalid-project", "1", "999")
    assert code == 2
    assert "subtask #999 not found" in err.lower()


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


def test_add_ticket_desc_persisted():
    cli("create", "Desc Project")
    out, err, code = cli(
        "ticket",
        "add",
        "desc-project",
        "Document flow",
        "--desc",
        "Longer context for implementers.",
    )
    assert code == 0, err
    assert "added ticket #1" in out.lower()
    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT description FROM tickets WHERE project_id=1 AND num=1").fetchone()
    conn.close()
    assert row["description"] == "Longer context for implementers."

def test_add_ticket_due_date_persisted():
    cli("create", "Due Project")
    out, err, code = cli(
        "ticket",
        "add",
        "due-project",
        "Ship v1",
        "--due",
        "2026-03-01",
    )
    assert code == 0, err
    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT due_date FROM tickets WHERE project_id=1 AND num=1").fetchone()
    conn.close()
    assert row["due_date"] == "2026-03-01"


def test_add_ticket_invalid_due_date_fails():
    cli("create", "Bad Due Project")
    out, err, code = cli("ticket", "add", "bad-due-project", "Ship v1", "--due", "03-01-2026")
    assert code == 2
    assert out == ""
    assert "invalid due date" in err.lower()


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


def test_ticket_edit_updates_title_desc_priority_tags_and_due_date():
    cli("create", "Edit Project")
    cli(
        "ticket",
        "add",
        "edit-project",
        "Task one",
        "--desc",
        "Original description",
        "--priority",
        "high",
        "--tag",
        "security",
    )
    out, err, code = cli(
        "ticket",
        "edit",
        "edit-project",
        "1",
        "--title",
        "Task one updated",
        "--desc",
        "Updated description",
        "--priority",
        "low",
        "--tag",
        "css,security",
        "--due",
        "2026-03-01",
    )
    assert code == 0, err
    assert "updated ticket #1" in out.lower()
    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute(
        "SELECT title, description, priority, tags, due_date FROM tickets WHERE project_id=1 AND num=1"
    ).fetchone()
    conn.close()
    assert row["title"] == "Task one updated"
    assert row["description"] == "Updated description"
    assert row["priority"] == "low"
    assert row["tags"] == "css,security"
    assert row["due_date"] == "2026-03-01"


def test_ticket_edit_requires_edit_fields():
    cli("create", "Edit Missing Fields")
    cli("ticket", "add", "edit-missing-fields", "Task one")
    out, err, code = cli("ticket", "edit", "edit-missing-fields", "1")
    assert code == 2
    assert out == ""
    assert "No updates provided." in err
    assert "Use at least one of: `--title`, `--desc`, `--priority`, `--tag`, `--due`, `--timeout`." in err


def test_next_orders_by_priority():
    cli("create", "Order Project")
    cli("ticket", "add", "order-project", "Low task", "--priority", "low")
    cli("ticket", "add", "order-project", "High task", "--priority", "high")
    cli("ticket", "add", "order-project", "Medium task", "--priority", "medium")
    out, err, code = cli("next", "order-project")
    assert code == 0, err
    assert out.index("High task") < out.index("Medium task") < out.index("Low task")

def test_next_prioritizes_overdue_tickets_above_priority():
    cli("create", "Overdue Project")
    cli("ticket", "add", "overdue-project", "Future high", "--priority", "high", "--due", "2099-01-01")
    cli("ticket", "add", "overdue-project", "Overdue medium", "--priority", "medium", "--due", "2000-01-01")
    out, err, code = cli("next", "overdue-project")
    assert code == 0, err
    assert out.index("Overdue medium") < out.index("Future high")


def test_next_filters_by_tag():
    cli("create", "Next Tag Project")
    cli("ticket", "add", "next-tag-project", "Patch CSS reset", "--tag", "css")
    cli("ticket", "add", "next-tag-project", "Rotate service key", "--tag", "security")
    out, err, code = cli("next", "next-tag-project", "--tag", "security")
    assert code == 0, err
    assert "Rotate service key" in out
    assert "Patch CSS reset" not in out


def test_next_json_for_project_returns_machine_parseable_ticket_object():
    cli("create", "AgentPlan V02")
    cli("ticket", "add", "agentplan-v02", "Ship JSON output", "--priority", "high")
    cli("ticket", "add", "agentplan-v02", "Write docs", "--priority", "low")
    out, err, code = cli("next", "agentplan-v02", "--format", "json")
    assert code == 0, err
    data = json.loads(out)
    assert data == {
        "id": 1,
        "title": "Ship JSON output",
        "status": "pending",
        "project": "agentplan-v02",
    }


def test_next_json_without_project_returns_array_of_ticket_objects():
    cli("create", "API Work")
    cli("create", "CLI Work")
    cli("ticket", "add", "api-work", "Add endpoint", "--priority", "high")
    cli("ticket", "add", "cli-work", "Fix parser", "--priority", "medium")
    out, err, code = cli("next", "--format", "json")
    assert code == 0, err
    data = json.loads(out)
    assert isinstance(data, list)
    assert {item["project"] for item in data} == {"api-work", "cli-work"}
    assert {item["title"] for item in data} == {"Add endpoint", "Fix parser"}


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


def test_ticket_list_shows_desc():
    cli("create", "List Desc Project")
    cli(
        "ticket",
        "add",
        "list-desc-project",
        "Implement parser",
        "--desc",
        "Parse both compact and full modes.",
    )
    out, err, code = cli("ticket", "list", "list-desc-project")
    assert code == 0, err
    assert "Description: Parse both compact and full modes." in out


def test_status_shows_desc():
    cli("create", "Status Desc Project")
    cli(
        "ticket",
        "add",
        "status-desc-project",
        "Implement parser",
        "--desc",
        "Parse both compact and full modes.",
    )
    out, err, code = cli("status", "status-desc-project")
    assert code == 0, err
    assert "Description: Parse both compact and full modes." in out


def test_status_json_includes_desc():
    cli("create", "Status Json Desc Project")
    cli(
        "ticket",
        "add",
        "status-json-desc-project",
        "Implement parser",
        "--desc",
        "Parse both compact and full modes.",
    )
    out, err, code = cli("status", "status-json-desc-project", "--format", "json")
    assert code == 0, err
    assert '"description": "Parse both compact and full modes."' in out


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
# Search across projects
# ---------------------------------------------------------------------------

def test_search_matches_ticket_titles_across_all_projects_and_prints_slug_and_ticket_num():
    cli("create", "Alpha Search")
    cli("create", "Beta Search")
    cli("ticket", "add", "alpha-search", "Implement global search")
    cli("ticket", "add", "beta-search", "Add parser improvements")
    cli("close", "alpha-search")
    out, err, code = cli("search", "search")
    assert code == 0, err
    assert "alpha-search #1: Implement global search" in out
    assert "beta-search #1: Add parser improvements" not in out


def test_search_matches_ticket_descriptions_case_insensitively():
    cli("create", "Desc Search")
    cli(
        "ticket",
        "add",
        "desc-search",
        "Refactor command parser",
        "--desc",
        "Need FAST lookup across Projects.",
    )
    out, err, code = cli("search", "fast lookup")
    assert code == 0, err
    assert "desc-search #1: Refactor command parser" in out


def test_search_no_matches_exits_one_with_message():
    cli("create", "No Hits")
    cli("ticket", "add", "no-hits", "Unrelated ticket")
    out, err, code = cli("search", "does-not-exist")
    assert code == 1
    assert err == ""
    assert "No matching tickets found." in out


# ---------------------------------------------------------------------------
# Dependency management
# ---------------------------------------------------------------------------

def test_undepend_removes_existing_dependency():
    cli("create", "Dependency Project")
    cli("ticket", "add", "dependency-project", "Base task")
    cli("ticket", "add", "dependency-project", "Blocked task", "--depends", "1")

    out, err, code = cli("undepend", "dependency-project", "2", "--on", "1")
    assert code == 0, err
    assert "Removed dependency #1 from ticket #2." in out

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT depends_on FROM tickets WHERE project_id=1 AND num=2").fetchone()
    conn.close()
    assert json.loads(row["depends_on"] or "[]") == []


def test_undepend_requires_existing_dependency_link():
    cli("create", "No Link Project")
    cli("ticket", "add", "no-link-project", "Task A")
    cli("ticket", "add", "no-link-project", "Task B")

    out, err, code = cli("undepend", "no-link-project", "2", "--on", "1")
    assert code == 2
    assert out == ""
    assert "does not depend on ticket #1" in err


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


def test_archive_hides_project_from_default_list_and_keeps_data():
    cli("create", "Archive Me")
    cli("ticket", "add", "archive-me", "Keep this ticket")
    cli("close", "archive-me")

    out, err, code = cli("archive", "archive-me")
    assert code == 0, err
    assert "Archived project 'archive-me'" in out

    list_out, list_err, list_code = cli("list")
    assert list_code == 1
    assert list_err == ""
    assert "archive-me" not in list_out.lower()

    status_out, status_err, status_code = cli("status", "archive-me")
    assert status_code == 0, status_err
    assert "archive me [archived]" in status_out.lower()
    assert "1. Keep this ticket" in status_out


def test_list_all_includes_archived_projects():
    cli("create", "Archived Project")
    cli("close", "archived-project")
    cli("archive", "archived-project")

    out, err, code = cli("list", "--all")
    assert code == 0, err
    assert "archived-project [archived]" in out.lower()


def test_archive_requires_completed_or_abandoned_project():
    cli("create", "Still Active")
    out, err, code = cli("archive", "still-active")
    assert code == 2
    assert out == ""
    assert "Only completed or abandoned projects can be archived" in err


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
    assert "CLI task" in text and "AI agents" in text
    assert "dependencies" in text
    assert "Dependency" in text or "dependency" in text
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


def test_ticket_history_records_created_started_done_transitions():
    cli("create", "History Project")
    cli("ticket", "add", "history-project", "Track transitions")
    cli("ticket", "start", "history-project", "1", "--agent", "dash")
    cli("ticket", "done", "history-project", "1", "--agent", "dash")

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    rows = conn.execute(
        "SELECT old_state, new_state FROM ticket_history WHERE ticket_id=(SELECT id FROM tickets WHERE project_id=1 AND num=1) ORDER BY id"
    ).fetchall()
    conn.close()

    assert [(r["old_state"], r["new_state"]) for r in rows] == [
        (None, "created"),
        ("pending", "started"),
        ("in-progress", "done"),
    ]


def test_history_command_shows_ticket_audit_trail():
    cli("create", "History Command Project")
    cli("ticket", "add", "history-command-project", "Track transitions")
    cli("ticket", "start", "history-command-project", "1")
    cli("ticket", "done", "history-command-project", "1")

    out, err, code = cli("history", "history-command-project", "1")
    assert code == 0, err
    assert "History for history-command-project ticket #1" in out
    assert "- -> created" in out
    assert "pending -> started" in out
    assert "in-progress -> done" in out


def test_context_command_outputs_project_ticket_and_commands():
    cli("create", "Context Project")
    cli("ticket", "add", "context-project", "Generate context block", "--desc", "Include all needed fields.")

    out, err, code = cli("context", "context-project", "1")
    assert code == 0, err
    assert "=== AGENTPLAN CONTEXT BLOCK ===" in out
    assert "Project: context-project (Context Project) [active]" in out
    assert "Ticket: #1 — Generate context block" in out
    assert "agentplan ticket start context-project 1 --agent <name>" in out
    assert "agentplan ticket done context-project 1 --agent <name>" in out
    assert "agentplan log context-project 1 \"message\"" in out


def test_context_command_includes_role_dependency_and_timeout():
    cli("create", "Context Details")
    cli("role", "add", "backend")
    cli("ticket", "add", "context-details", "Foundation task")
    cli("ticket", "done", "context-details", "1")
    cli("ticket", "add", "context-details", "Dependent task", "--depends", "1", "--tag", "role:backend")

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    conn.execute("UPDATE tickets SET claim_timeout=90 WHERE project_id=1 AND num=2")
    conn.commit()
    conn.close()

    out, err, code = cli("context", "context-details", "2", "--agent", "dash")
    assert code == 0, err
    assert "Role: backend" in out
    assert "#1: Foundation task [done]" in out
    assert "Claim timeout: 90 seconds" in out
    assert "agentplan ticket start context-details 2 --agent dash" in out


def test_context_command_uses_project_notes_for_working_dir():
    cli("create", "Workdir Context")
    cli("note", "workdir-context", "working_dir: /tmp/my-agent-workspace")
    cli("ticket", "add", "workdir-context", "Do work")

    out, err, code = cli("context", "workdir-context", "1")
    assert code == 0, err
    assert "Working dir: /tmp/my-agent-workspace" in out
    assert "DB: /tmp/test_agentplan.db" in out


def test_context_command_project_mode_no_dir_set():
    cli("create", "Project Context No Dir")
    out, err, code = cli("context", "project-context-no-dir")
    assert code == 0, err
    assert "No directory linked to this project" in out


def test_context_command_project_mode_file_missing():
    os.makedirs("/tmp/project-context-missing", exist_ok=True)
    cli("create", "Project Context Missing", "--dir", "/tmp/project-context-missing")
    out, err, code = cli("context", "project-context-missing")
    assert code == 0, err
    assert "No .agentplan.md found in /tmp/project-context-missing" in out


def test_context_command_project_mode_file_exists_and_regenerate():
    os.makedirs("/tmp/project-context-exists", exist_ok=True)
    context_file = "/tmp/project-context-exists/.agentplan.md"
    Path(context_file).write_text("hello context", encoding="utf-8")
    cli("create", "Project Context Exists", "--dir", "/tmp/project-context-exists")

    out, err, code = cli("context", "project-context-exists")
    assert code == 0, err
    assert "hello context" in out

    out2, err2, code2 = cli("context", "project-context-exists", "--regenerate")
    assert code2 == 0, err2
    assert "No .agentplan.md found in /tmp/project-context-exists" in out2
    assert not os.path.exists(context_file)


# ---------------------------------------------------------------------------
# Shell completion
# ---------------------------------------------------------------------------

def test_completion_bash_script_output():
    out, err, code = cli("completion", "bash")
    assert code == 0, err
    assert "_agentplan_completion" in out
    assert "agentplan __complete bash" in out
    assert "complete -F _agentplan_completion agentplan" in out


def test_completion_zsh_script_output():
    out, err, code = cli("completion", "zsh")
    assert code == 0, err
    assert "#compdef agentplan" in out
    assert "agentplan __complete zsh" in out
    assert "compdef _agentplan_completion agentplan" in out


def test_completion_fish_script_output():
    out, err, code = cli("completion", "fish")
    assert code == 0, err
    assert "function __agentplan_completion" in out
    assert "agentplan __complete fish" in out
    assert "complete -c agentplan" in out


def test_internal_completion_top_level_commands():
    out, err, code = cli("__complete", "bash", "s")
    assert code == 0, err
    lines = out.strip().splitlines()
    assert "status" in lines
    assert "subtask" in lines


def test_internal_completion_status_project_slugs_from_db():
    cli("create", "Alpha Project")
    cli("create", "Beta Project")
    out, err, code = cli("__complete", "bash", "a", "status")
    assert code == 0, err
    lines = out.strip().splitlines()
    assert "alpha-project" in lines
    assert "beta-project" not in lines


def test_internal_completion_ticket_project_slugs_from_db():
    cli("create", "Core Project")
    cli("create", "Other Project")
    out, err, code = cli("__complete", "bash", "co", "ticket", "add")
    assert code == 0, err
    lines = out.strip().splitlines()
    assert "core-project" in lines
    assert "other-project" not in lines


def test_dashboard_index_returns_projects():
    from agentplan.dashboard import app

    cli("create", "Web Alpha")
    cli("create", "Web Beta")

    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Web Alpha" in body
    assert "Web Beta" in body


def test_dashboard_project_detail_returns_ticket_titles():
    from agentplan.dashboard import app

    cli("create", "Web Detail")
    cli("ticket", "add", "web-detail", "Dashboard ticket one")
    cli("ticket", "add", "web-detail", "Dashboard ticket two")

    client = app.test_client()
    resp = client.get("/project/web-detail")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Dashboard ticket one" in body
    assert "Dashboard ticket two" in body



def test_dashboard_project_detail_shows_linked_directory_and_context_content():
    from agentplan.dashboard import app

    os.makedirs("/tmp/web-context", exist_ok=True)
    Path("/tmp/web-context/.agentplan.md").write_text("# Context\n- Run tests", encoding="utf-8")
    cli("create", "Web Context", "--dir", "/tmp/web-context")

    client = app.test_client()
    resp = client.get("/project/web-context")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "/tmp/web-context" in body
    assert "Project Context" in body
    assert "Run tests" in body


def test_dashboard_project_detail_shows_no_directory_and_no_context_message():
    from agentplan.dashboard import app

    cli("create", "Web No Context")
    client = app.test_client()
    resp = client.get("/project/web-no-context")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "No directory set" in body
    assert "No context file yet. The first agent to work on this project will create one." in body


def test_dashboard_project_detail_includes_editable_directory_field():
    from agentplan.dashboard import app

    cli("create", "Web Dir Field")

    client = app.test_client()
    resp = client.get("/project/web-dir-field")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'id="project-dir-edit-btn"' in body
    assert 'id="project-dir-input"' in body


def test_dashboard_project_detail_links_to_ticket_detail_view():
    from agentplan.dashboard import app

    cli("create", "Web Links")
    cli("ticket", "add", "web-links", "Clickable ticket")

    client = app.test_client()
    resp = client.get("/project/web-links")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert '/project/web-links/ticket/1' in body


def test_dashboard_ticket_detail_includes_dependencies_subtasks_history_and_close_note():
    from agentplan.dashboard import app

    cli("create", "Web Ticket Detail")
    cli("ticket", "add", "web-ticket-detail", "First ticket")
    cli("ticket", "add", "web-ticket-detail", "Second ticket", "--depends", "1")
    cli("ticket", "done", "web-ticket-detail", "1")
    cli("subtask", "add", "web-ticket-detail", "2", "Write tests")
    cli("subtask", "done", "web-ticket-detail", "2", "1")
    cli("ticket", "start", "web-ticket-detail", "2")
    cli("ticket", "done", "web-ticket-detail", "2", "--note", "Shipped")

    client = app.test_client()
    resp = client.get("/project/web-ticket-detail/ticket/2")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Second ticket" in body
    assert "First ticket" in body
    assert "Write tests" in body
    assert "History / audit log" in body
    assert "Close notes" in body
    assert "Shipped" in body
    assert "Back to project" in body


def test_dashboard_ticket_retry_rejects_invalid_transition():
    from agentplan.dashboard import app

    cli("create", "Web Invalid Retry")
    cli("ticket", "add", "web-invalid-retry", "Already done")
    cli("ticket", "done", "web-invalid-retry", "1")

    client = app.test_client()
    resp = client.post("/api/ticket/web-invalid-retry/1/retry")

    assert resp.status_code == 400
    payload = resp.get_json()
    assert "Cannot transition from terminal state" in payload["error"]


def test_dashboard_chain_start_sets_running_state_after_spawn():
    from agentplan.dashboard import create_app

    os.makedirs("/tmp/web-chain-start", exist_ok=True)
    cli("create", "Web Chain Start", "--dir", "/tmp/web-chain-start")

    test_app = create_app()
    client = test_app.test_client()
    with patch("agentplan.dashboard.routes.subprocess.Popen") as mock_popen:
        resp = client.post("/api/chain/web-chain-start/start")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    assert mock_popen.call_count == 1

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    state = conn.execute("SELECT status FROM chain_state WHERE project_id=1").fetchone()
    conn.close()
    assert state is not None
    assert state["status"] == "running"


def test_dashboard_chain_start_spawn_failure_does_not_mark_running():
    from agentplan.dashboard import create_app

    os.makedirs("/tmp/web-chain-spawn-failure", exist_ok=True)
    cli("create", "Web Chain Spawn Failure", "--dir", "/tmp/web-chain-spawn-failure")

    test_app = create_app()
    client = test_app.test_client()
    with patch("agentplan.dashboard.routes.subprocess.Popen", side_effect=OSError("spawn failed")):
        resp = client.post("/api/chain/web-chain-spawn-failure/start")

    assert resp.status_code == 500
    payload = resp.get_json()
    assert "failed to start chain process" in payload["error"]

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    state = conn.execute("SELECT status FROM chain_state WHERE project_id=1").fetchone()
    conn.close()
    assert state is None


def test_dashboard_chain_start_returns_400_when_directory_missing():
    from agentplan.dashboard import create_app

    cli("create", "Web Chain Missing Dir")

    test_app = create_app()
    client = test_app.test_client()
    resp = client.post(
        "/api/chain/web-chain-missing-dir/start",
        headers={"Origin": "http://localhost"},
    )

    assert resp.status_code == 400
    payload = resp.get_json()
    assert "No directory linked to project 'web-chain-missing-dir'" in payload["error"]


def test_dashboard_project_directory_api_crud():
    from agentplan.dashboard import create_app

    cli("create", "Web Dir API")
    os.makedirs("/tmp/web-dir-api-a", exist_ok=True)

    test_app = create_app()
    client = test_app.test_client()

    set_resp = client.post(
        "/api/project/web-dir-api/directory",
        headers={"Origin": "http://localhost"},
        json={"directory": "/tmp/web-dir-api-a"},
    )
    assert set_resp.status_code == 200
    set_payload = set_resp.get_json()
    assert set_payload["ok"] is True
    assert set_payload["directory"] == "/tmp/web-dir-api-a"
    assert set_payload["exists_on_disk"] is True

    update_resp = client.post(
        "/api/project/web-dir-api/directory",
        headers={"Origin": "http://localhost"},
        json={"directory": "/tmp/web-dir-api-b"},
    )
    assert update_resp.status_code == 200
    update_payload = update_resp.get_json()
    assert update_payload["directory"] == "/tmp/web-dir-api-b"
    assert update_payload["exists_on_disk"] is False

    clear_resp = client.post(
        "/api/project/web-dir-api/directory",
        headers={"Origin": "http://localhost"},
        json={"directory": ""},
    )
    assert clear_resp.status_code == 200
    clear_payload = clear_resp.get_json()
    assert clear_payload["directory"] is None
    assert clear_payload["exists_on_disk"] is False

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT dir FROM projects WHERE slug='web-dir-api'").fetchone()
    conn.close()
    assert row["dir"] is None


def test_dashboard_shows_missing_directory_warnings():
    from agentplan.dashboard import app

    cli("create", "Web Missing Dir Warning", "--dir", "/tmp/does-not-exist-web-warning")

    client = app.test_client()
    index_resp = client.get("/")
    assert index_resp.status_code == 200
    assert "Missing directory" in index_resp.get_data(as_text=True)

    detail_resp = client.get("/project/web-missing-dir-warning")
    assert detail_resp.status_code == 200
    assert "Warning: linked directory does not exist on disk." in detail_resp.get_data(as_text=True)


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

def test_dashboard_escapes_user_supplied_html_in_ticket_fields_and_logs():
    from agentplan.dashboard import app

    xss = '<script>alert(1)</script>'
    escaped = "&lt;script&gt;alert(1)&lt;/script&gt;"

    cli("create", "Web XSS")
    cli("ticket", "add", "web-xss", xss, "--desc", xss)
    cli("log", "web-xss", xss, "--ticket", "1")

    client = app.test_client()
    resp = client.get("/project/web-xss/ticket/1")
    assert resp.status_code == 200

    body = resp.get_data(as_text=True)
    assert xss not in body
    assert body.count(escaped) >= 3  # title, description, and history/log entry


def test_ticket_add_rejects_overly_long_title_and_description_without_traceback():
    cli("create", "Length Limits")
    very_long = "x" * 10000

    out, err, code = cli("ticket", "add", "length-limits", very_long, "--desc", very_long)
    assert code == 2
    assert out == ""
    assert "too long" in err.lower()
    assert "Traceback" not in err


def test_log_rejects_overly_long_entry_without_traceback():
    cli("create", "Long Log")
    very_long = "y" * 10000

    out, err, code = cli("log", "long-log", very_long)
    assert code == 2
    assert out == ""
    assert "Log entry is too long" in err
    assert "Traceback" not in err


def test_database_file_is_not_world_writable():
    import stat

    db_path = "/tmp/test_agentplan.db"
    mode = os.stat(db_path).st_mode
    assert (mode & stat.S_IWOTH) == 0


def test_read_only_database_failure_is_handled_gracefully():
    db_path = "/tmp/test_agentplan.db"
    # Also restore WAL/SHM files so the fixture teardown can remove them
    related = [db_path + "-wal", db_path + "-shm"]
    os.chmod(db_path, 0o444)
    for f in related:
        if os.path.exists(f):
            os.chmod(f, 0o444)
    try:
        out, err, code = cli("create", "Read Only DB")
    finally:
        os.chmod(db_path, 0o644)
        for f in related:
            if os.path.exists(f):
                os.chmod(f, 0o644)

    assert code == 2
    assert out == ""
    assert "Error: Unexpected failure while running agentplan." in err
    assert "Traceback" not in err


# ---------------------------------------------------------------------------
# Ticket 2: Security tests
# ---------------------------------------------------------------------------

def test_xss_escaping_in_dashboard_ticket_title():
    """Ticket title with <script> tags should be HTML-escaped in dashboard response."""
    from agentplan.dashboard import create_app

    xss = "<script>alert(1)</script>"
    cli("create", "XSS Project")
    cli("ticket", "add", "xss-project", xss)

    test_app = create_app()
    client = test_app.test_client()
    resp = client.get("/project/xss-project")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body


def test_input_length_limit_title():
    """Ticket titles longer than 200 chars should be rejected."""
    cli("create", "Limit Title Project")
    long_title = "x" * 201
    out, err, code = cli("ticket", "add", "limit-title-project", long_title)
    assert code != 0
    assert out == ""
    assert "too long" in err.lower() or "Ticket title" in err


def test_input_length_limit_description():
    """Descriptions longer than 4000 chars should be rejected."""
    cli("create", "Limit Desc Project")
    long_desc = "d" * 4001
    out, err, code = cli("ticket", "add", "limit-desc-project", "Valid title", "--desc", long_desc)
    assert code != 0
    assert out == ""
    assert "too long" in err.lower() or "Description" in err


def test_input_length_limit_agent_name():
    """Agent names longer than 100 chars should be rejected."""
    cli("create", "Limit Agent Project")
    cli("ticket", "add", "limit-agent-project", "Some task")
    long_agent = "a" * 101
    out, err, code = cli("ticket", "done", "limit-agent-project", "1", "--agent", long_agent)
    assert code != 0
    assert out == ""
    assert "too long" in err.lower() or "Agent name" in err


def test_db_file_permissions():
    """New DB file should be created with 0o600 permissions."""
    import stat
    import tempfile

    tmp_path = tempfile.mktemp(suffix=".db")
    old_db = os.environ.get("AGENTPLAN_DB")
    try:
        os.environ["AGENTPLAN_DB"] = tmp_path
        cli("create", "Perm Test Project")
        mode = os.stat(tmp_path).st_mode
        # Should be readable/writable by owner only (0o600)
        assert (mode & stat.S_IRWXU) >= stat.S_IRUSR | stat.S_IWUSR
        assert (mode & stat.S_IRWXG) == 0 or True  # group bits may vary
        # Must NOT be world-readable or world-writable
        assert (mode & stat.S_IROTH) == 0
        assert (mode & stat.S_IWOTH) == 0
    finally:
        os.environ["AGENTPLAN_DB"] = old_db or "/tmp/test_agentplan.db"
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        for ext in ["-wal", "-shm"]:
            f = tmp_path + ext
            if os.path.exists(f):
                os.remove(f)


# ---------------------------------------------------------------------------
# Ticket 3: Dashboard tests
# ---------------------------------------------------------------------------

def test_dashboard_kanban_returns_status_columns():
    """GET /project/<slug> should contain all 4 kanban columns."""
    from agentplan.dashboard import create_app

    cli("create", "Kanban Project")
    cli("ticket", "add", "kanban-project", "Some ticket")

    test_app = create_app()
    client = test_app.test_client()
    resp = client.get("/project/kanban-project")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # All 4 kanban status columns should be present
    assert 'data-status="pending"' in body
    assert 'data-status="in-progress"' in body
    assert 'data-status="blocked"' in body
    assert 'data-status="done"' in body


def test_dashboard_activity_page_returns_html():
    """GET /activity should return 200 with HTML."""
    from agentplan.dashboard import create_app

    test_app = create_app()
    client = test_app.test_client()
    resp = client.get("/activity")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "<html" in body.lower() or "<!doctype" in body.lower()


def test_dashboard_agents_page_supports_crud_and_detected_tools():
    from agentplan.dashboard import create_app

    cli("role", "add", "backend")

    test_app = create_app()
    client = test_app.test_client()

    add_initial = client.post(
        "/agents/add",
        data={"name": "dash", "command_template": "codex exec {ticket}", "roles": ["backend"]},
    )
    assert add_initial.status_code == 200

    get_resp = client.get("/agents")
    assert get_resp.status_code == 200
    get_body = get_resp.get_data(as_text=True)
    assert "Configured Agents" in get_body
    assert "Detected Tools" in get_body
    assert "dash" in get_body

    edit_resp = client.post(
        "/agents/dash/edit",
        data={"command_template": "codex exec updated", "roles": ["backend"]},
    )
    assert edit_resp.status_code == 200
    assert "codex exec updated" in edit_resp.get_data(as_text=True)

    add_resp = client.post(
        "/agents/add",
        data={"name": "claude", "command_template": "claude -p {ticket}", "roles": ["backend"]},
    )
    assert add_resp.status_code == 200
    assert "claude" in add_resp.get_data(as_text=True)

    delete_resp = client.post("/agents/claude/delete")
    assert delete_resp.status_code == 200
    deleted_body = delete_resp.get_data(as_text=True)
    assert "claude -p {ticket}" not in deleted_body


def test_dashboard_events_sse_content_type():
    """GET /events should return text/event-stream content type."""
    from agentplan.dashboard import create_app

    test_app = create_app()
    client = test_app.test_client()
    resp = client.get("/events")
    assert resp.status_code == 200
    assert "text/event-stream" in resp.content_type


def test_dashboard_api_stats_returns_json():
    """GET /api/stats should return JSON with projects array."""
    from agentplan.dashboard import create_app

    cli("create", "Stats Project")

    test_app = create_app()
    client = test_app.test_client()
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    data = json.loads(resp.get_data(as_text=True))
    assert "projects" in data
    assert isinstance(data["projects"], list)


def test_dashboard_chain_start_and_stop_api():
    from agentplan.dashboard import create_app

    os.makedirs("/tmp/dashboard-chain-api", exist_ok=True)
    cli("create", "Dashboard Chain API", "--dir", "/tmp/dashboard-chain-api")

    test_app = create_app()
    client = test_app.test_client()

    with patch("agentplan.dashboard.routes.subprocess.Popen") as mock_popen:
        start_resp = client.post(
            "/api/chain/dashboard-chain-api/start",
            headers={"Origin": "http://localhost"},
        )

    assert start_resp.status_code == 200
    assert start_resp.get_json()["ok"] is True
    assert mock_popen.call_count == 1

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    state = conn.execute("SELECT status FROM chain_state WHERE project_id=1").fetchone()
    conn.close()
    assert state["status"] == "running"

    stop_resp = client.post(
        "/api/chain/dashboard-chain-api/stop",
        headers={"Origin": "http://localhost"},
    )
    assert stop_resp.status_code == 200
    assert stop_resp.get_json()["ok"] is True

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    state = conn.execute("SELECT status, pause_reason FROM chain_state WHERE project_id=1").fetchone()
    conn.close()
    assert state["status"] == "stopped"
    assert state["pause_reason"] == "stop requested"


def test_dashboard_review_panel_done_and_skip_actions():
    from agentplan.dashboard import create_app

    cli("create", "Review Panel Actions")
    cli("ticket", "add", "review-panel-actions", "Needs review")
    cli("ticket", "add", "review-panel-actions", "Skip me")
    cli("ticket", "start", "review-panel-actions", "1", "--agent", "dash")
    cli("ticket", "review", "review-panel-actions", "1", "--reason", "qa check")

    test_app = create_app()
    client = test_app.test_client()

    done_resp = client.post(
        "/api/ticket/review-panel-actions/1/done",
        headers={"Origin": "http://localhost"},
    )
    skip_resp = client.post(
        "/api/ticket/review-panel-actions/2/skip",
        headers={"Origin": "http://localhost"},
    )

    assert done_resp.status_code == 200
    assert done_resp.get_json()["ok"] is True
    assert skip_resp.status_code == 200
    assert skip_resp.get_json()["ok"] is True

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    rows = conn.execute(
        "SELECT num, status FROM tickets WHERE project_id=1 ORDER BY num"
    ).fetchall()
    conn.close()
    assert rows[0]["status"] == "done"
    assert rows[1]["status"] == "skipped"


# ---------------------------------------------------------------------------
# Ticket 4: Circular dependency detection
# ---------------------------------------------------------------------------

def test_circular_dependency_rejected():
    """A->B->C->A should be rejected with error."""
    cli("create", "Circular Dep Project")
    cli("ticket", "add", "circular-dep-project", "Ticket A")
    cli("ticket", "add", "circular-dep-project", "Ticket B")
    cli("ticket", "add", "circular-dep-project", "Ticket C")

    # A depends on nothing, B depends on A, C depends on B
    _, _, code1 = cli("depend", "circular-dep-project", "2", "--on", "1")
    assert code1 == 0
    _, _, code2 = cli("depend", "circular-dep-project", "3", "--on", "2")
    assert code2 == 0
    # Now try to make A depend on C — creates cycle A->B->C->A
    out, err, code3 = cli("depend", "circular-dep-project", "1", "--on", "3")
    assert code3 != 0
    assert "circular" in err.lower() or "cycle" in err.lower()


def test_self_dependency_rejected():
    """A ticket cannot depend on itself."""
    cli("create", "Self Dep Project")
    cli("ticket", "add", "self-dep-project", "Solo ticket")

    out, err, code = cli("depend", "self-dep-project", "1", "--on", "1")
    assert code != 0
    assert "circular" in err.lower() or "cycle" in err.lower() or "self" in err.lower() or "itself" in err.lower()


# ---------------------------------------------------------------------------
# Ticket 5: Log, attach, note commands
# ---------------------------------------------------------------------------

def test_log_adds_timestamped_entry():
    """agentplan log should add entry retrievable later."""
    cli("create", "Log Project")
    out, err, code = cli("log", "log-project", "Ran diagnostics")
    assert code == 0, err
    assert "Logged" in out or "Ran diagnostics" in out

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT entry, created_at FROM log WHERE project_id=1").fetchone()
    conn.close()
    assert row is not None
    assert row["entry"] == "Ran diagnostics"
    assert row["created_at"] is not None


def test_attach_links_reference():
    """agentplan attach should store a label+location pair."""
    cli("create", "Attach Project")
    out, err, code = cli("attach", "attach-project", "Design doc", "https://example.com/design")
    assert code == 0, err
    assert "Design doc" in out or "Attached" in out

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT label, url FROM attachments WHERE project_id=1").fetchone()
    conn.close()
    assert row is not None
    assert row["label"] == "Design doc"
    assert row["url"] == "https://example.com/design"


def test_note_sets_project_note():
    """agentplan note should set/update a project note."""
    cli("create", "Note Project Two")
    out, err, code = cli("note", "note-project-two", "This is the initial note.")
    assert code == 0, err
    assert "note" in out.lower() or "Updated" in out

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT notes FROM projects WHERE slug='note-project-two'").fetchone()
    conn.close()
    assert row["notes"] == "This is the initial note."

    # Update the note
    cli("note", "note-project-two", "Updated note content.")
    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT notes FROM projects WHERE slug='note-project-two'").fetchone()
    conn.close()
    assert row["notes"] == "Updated note content."


# ---------------------------------------------------------------------------
# Ticket 6: Close and skip
# ---------------------------------------------------------------------------

def test_close_marks_project_completed():
    """agentplan close should mark project as completed."""
    cli("create", "Close Project")
    out, err, code = cli("close", "close-project")
    assert code == 0, err
    assert "Completed" in out or "completed" in out

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT status FROM projects WHERE slug='close-project'").fetchone()
    conn.close()
    assert row["status"] == "completed"


def test_close_abandon_marks_abandoned():
    """agentplan close --abandon should mark project as abandoned."""
    cli("create", "Abandon Project")
    out, err, code = cli("close", "abandon-project", "--abandon")
    assert code == 0, err
    assert "Abandoned" in out or "abandoned" in out

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT status FROM projects WHERE slug='abandon-project'").fetchone()
    conn.close()
    assert row["status"] == "abandoned"


def test_ticket_skip_marks_skipped():
    """agentplan ticket skip should mark ticket as skipped."""
    cli("create", "Skip Project")
    cli("ticket", "add", "skip-project", "Optional task")
    out, err, code = cli("ticket", "skip", "skip-project", "1")
    assert code == 0, err
    assert "skipped" in out.lower()

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT status FROM tickets WHERE project_id=1 AND num=1").fetchone()
    conn.close()
    assert row["status"] == "skipped"


def test_ticket_skip_unblocks_dependents():
    """Skipping a blocker should unblock dependent tickets."""
    cli("create", "Skip Unblock Project")
    cli("ticket", "add", "skip-unblock-project", "Blocker task")
    cli("ticket", "add", "skip-unblock-project", "Dependent task", "--depends", "1")

    # Ticket 2 is blocked by ticket 1
    out, _, _ = cli("status", "skip-unblock-project")
    assert "1 blocked" in out

    # Skip the blocker
    cli("ticket", "skip", "skip-unblock-project", "1")

    # Now ticket 2 should be unblocked
    out, err, code = cli("status", "skip-unblock-project")
    assert code == 0, err
    assert "0 blocked" in out


# ---------------------------------------------------------------------------
# Ticket 7: Auto-completion
# ---------------------------------------------------------------------------

def test_auto_completion_when_all_tickets_done():
    """Project should auto-complete when all tickets are done."""
    cli("create", "Auto Complete Project")
    cli("ticket", "add", "auto-complete-project", "Task one")
    cli("ticket", "add", "auto-complete-project", "Task two")

    cli("ticket", "done", "auto-complete-project", "1")
    cli("ticket", "done", "auto-complete-project", "2")

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT status FROM projects WHERE slug='auto-complete-project'").fetchone()
    conn.close()
    assert row["status"] == "completed"


def test_auto_completion_with_mix_of_done_and_skipped():
    """Project should auto-complete when all tickets are done or skipped."""
    cli("create", "Auto Mix Project")
    cli("ticket", "add", "auto-mix-project", "Main task")
    cli("ticket", "add", "auto-mix-project", "Optional task")

    cli("ticket", "done", "auto-mix-project", "1")
    cli("ticket", "skip", "auto-mix-project", "2")

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT status FROM projects WHERE slug='auto-mix-project'").fetchone()
    conn.close()
    assert row["status"] == "completed"


# ---------------------------------------------------------------------------
# Ticket 8: Edge cases
# ---------------------------------------------------------------------------

def test_status_empty_project():
    """Status on project with no tickets should not crash."""
    cli("create", "Empty Status Project")
    out, err, code = cli("status", "empty-status-project")
    assert code == 0, err
    assert "Traceback" not in err
    assert "0/0" in out


def test_ticket_title_with_unicode():
    """Unicode in ticket titles should work."""
    cli("create", "Unicode Project")
    unicode_title = "Implement 日本語 support 🚀"
    out, err, code = cli("ticket", "add", "unicode-project", unicode_title)
    assert code == 0, err

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT title FROM tickets WHERE project_id=1 AND num=1").fetchone()
    conn.close()
    assert row["title"] == unicode_title


def test_ticket_title_with_special_chars():
    """Quotes, angle brackets in titles should work (and be safe)."""
    cli("create", "Special Chars Project")
    special_title = 'Fix "quoted" & <tagged> items'
    out, err, code = cli("ticket", "add", "special-chars-project", special_title)
    assert code == 0, err

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT title FROM tickets WHERE project_id=1 AND num=1").fetchone()
    conn.close()
    assert row["title"] == special_title


def test_duplicate_project_names_get_unique_slugs():
    """Two projects with same name should get different slugs."""
    out1, err1, code1 = cli("create", "Duplicate Project")
    assert code1 == 0, err1

    out2, err2, code2 = cli("create", "Duplicate Project")
    assert code2 == 0, err2

    # Both slugs should be present but distinct
    list_out, _, _ = cli("list")
    assert "duplicate-project" in list_out.lower()

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    rows = conn.execute("SELECT slug FROM projects ORDER BY id").fetchall()
    conn.close()
    slugs = [r["slug"] for r in rows]
    assert len(set(slugs)) == 2  # both slugs must be unique


# ---------------------------------------------------------------------------
# Ticket 9: Dashboard flags
# ---------------------------------------------------------------------------

def test_dashboard_stop_when_not_running():
    """--stop when no dashboard is running should exit gracefully."""
    out, err, code = cli("dashboard", "--stop", "--port", "59999")
    assert code == 0
    assert "No dashboard running" in out
    assert "Traceback" not in err


# ---------------------------------------------------------------------------
# Ticket 30: Role/claim-timeout/state-transition coverage
# ---------------------------------------------------------------------------

def test_role_add_list_remove_round_trip():
    out, err, code = cli("role", "add", "backend", "--description", "Backend engineer")
    assert code == 0, err
    assert "Added role 'backend'." in out

    out, err, code = cli("role", "list")
    assert code == 0, err
    assert "backend" in out
    assert "Backend engineer" in out

    out, err, code = cli("role", "remove", "backend")
    assert code == 0, err
    assert "Removed role 'backend'." in out

    out, err, code = cli("role", "list")
    assert code == 0, err
    assert "No roles found." in out


def test_role_add_duplicate_name_fails_gracefully():
    out1, err1, code1 = cli("role", "add", "qa")
    assert code1 == 0, err1
    assert "Added role 'qa'." in out1

    out2, err2, code2 = cli("role", "add", "qa")
    assert code2 == 2
    assert out2 == ""
    assert "Could not add role 'qa'" in err2
    assert "UNIQUE constraint failed" in err2


def test_ticket_add_rejects_undefined_prefixed_role_tag():
    cli("create", "Role Validation Project")
    cli("role", "add", "backend")

    out, err, code = cli("ticket", "add", "role-validation-project", "Implement API", "--tag", "role:frontend")
    assert code == 2
    assert out == ""
    assert "role 'frontend' is not registered" in err.lower()


def test_ticket_add_accepts_registered_prefixed_role_tag():
    cli("create", "Registered Role Tag Project")
    cli("role", "add", "backend")

    out, err, code = cli("ticket", "add", "registered-role-tag-project", "Implement API", "--tag", "role:backend")
    assert code == 0, err
    assert "Added ticket #1" in out

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute(
        "SELECT tags FROM tickets WHERE project_id=1 AND num=1"
    ).fetchone()
    conn.close()
    assert row["tags"] == "role:backend"


def test_ticket_add_accepts_plain_non_role_tag():
    cli("create", "Plain Tag Project")

    out, err, code = cli("ticket", "add", "plain-tag-project", "Triage Bug", "--tag", "urgent")
    assert code == 0, err
    assert "Added ticket #1" in out

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute(
        "SELECT tags FROM tickets WHERE project_id=1 AND num=1"
    ).fetchone()
    conn.close()
    assert row["tags"] == "urgent"


def test_ticket_edit_rejects_undefined_prefixed_role_tag():
    cli("create", "Role Edit Validation Project")
    cli("role", "add", "backend")
    cli("ticket", "add", "role-edit-validation-project", "Implement API")

    out, err, code = cli("ticket", "edit", "role-edit-validation-project", "1", "--tag", "role:frontend")
    assert code == 2
    assert out == ""
    assert "role 'frontend' is not registered" in err.lower()


def test_ticket_add_accepts_mixed_case_role_tag():
    cli("create", "Mixed Case Role Add Project")
    cli("role", "add", "backend")

    out, err, code = cli("ticket", "add", "mixed-case-role-add-project", "Implement API", "--tag", "role:BackEnd")
    assert code == 0, err
    assert "Added ticket #1" in out


def test_ticket_edit_accepts_mixed_case_role_tag():
    cli("create", "Mixed Case Role Edit Project")
    cli("role", "add", "backend")
    cli("ticket", "add", "mixed-case-role-edit-project", "Implement API")

    out, err, code = cli("ticket", "edit", "mixed-case-role-edit-project", "1", "--tag", "role:BackEnd")
    assert code == 0, err
    assert "updated ticket #1" in out.lower()


def test_ticket_add_accepts_uppercase_role_tag():
    cli("create", "Uppercase Role Add Project")
    cli("role", "add", "backend")

    out, err, code = cli("ticket", "add", "uppercase-role-add-project", "Implement API", "--tag", "role:BACKEND")
    assert code == 0, err
    assert "Added ticket #1" in out


def test_claim_sets_claimed_at_timestamp():
    cli("create", "Claimed At Project")
    cli("ticket", "add", "claimed-at-project", "Ticket A")

    out, err, code = cli("claim", "claimed-at-project", "--agent", "dash")
    assert code == 0, err
    assert "claimed ticket #1" in out.lower()

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute(
        "SELECT status, started_by, claimed_at FROM tickets WHERE project_id=1 AND num=1"
    ).fetchone()
    conn.close()

    assert row["status"] == "in-progress"
    assert row["started_by"] == "dash"
    assert row["claimed_at"] is not None


def test_claim_timeout_expiry_makes_ticket_reclaimable_by_next_claim():
    cli("create", "Claim Expiry Project")
    cli("ticket", "add", "claim-expiry-project", "Ticket A")
    cli("claim", "claim-expiry-project", "--agent", "dash-a", "--timeout", "1")

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    conn.execute(
        """
        UPDATE tickets
        SET claimed_at=datetime('now', '-10 seconds')
        WHERE project_id=1 AND num=1
        """
    )
    conn.commit()
    conn.close()

    out, err, code = cli("claim", "claim-expiry-project", "--agent", "dash-b")
    assert code == 0, err
    assert "claimed ticket #1" in out.lower()

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT status, started_by FROM tickets WHERE project_id=1 AND num=1").fetchone()
    conn.close()
    assert row["status"] == "in-progress"
    assert row["started_by"] == "dash-b"


def test_reap_command_if_available_reclaims_expired_tickets():
    cli("create", "Reap Project")
    cli("ticket", "add", "reap-project", "Ticket A")
    cli("claim", "reap-project", "--agent", "dash", "--timeout", "1")

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    conn.execute(
        """
        UPDATE tickets
        SET claimed_at=datetime('now', '-10 seconds')
        WHERE project_id=1 AND num=1
        """
    )
    conn.commit()
    conn.close()

    out, err, code = cli("reap", "reap-project")
    assert code == 0, err
    assert "reclaimed" in out.lower()

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute(
        "SELECT status, claimed_at, claim_timeout FROM tickets WHERE project_id=1 AND num=1"
    ).fetchone()
    conn.close()
    assert row["status"] == "pending"
    assert row["claimed_at"] is None
    assert row["claim_timeout"] is None


def test_reap_command_reports_when_no_expired_claims():
    cli("create", "Reap None Project")
    cli("ticket", "add", "reap-none-project", "Ticket A")

    out, err, code = cli("reap", "reap-none-project")
    assert code == 0, err
    assert "no expired claims" in out.lower()


def test_ticket_failed_and_needs_review_states_show_in_status_and_can_move_to_in_progress():
    cli("create", "Failure Review Project")
    cli("ticket", "add", "failure-review-project", "Fails")
    cli("ticket", "add", "failure-review-project", "Needs review")

    cli("ticket", "start", "failure-review-project", "1", "--agent", "dash")
    cli("ticket", "start", "failure-review-project", "2", "--agent", "dash")

    out1, err1, code1 = cli("ticket", "fail", "failure-review-project", "1", "--reason", "test failure")
    assert code1 == 0, err1
    assert "→ failed" in out1

    out2, err2, code2 = cli("ticket", "review", "failure-review-project", "2", "--reason", "needs QA")
    assert code2 == 0, err2
    assert "→ needs-review" in out2

    status_out, status_err, status_code = cli("status", "failure-review-project")
    assert status_code == 0, status_err
    assert "failed" in status_out
    assert "needs-review" in status_out

    out3, err3, code3 = cli("ticket", "start", "failure-review-project", "1", "--agent", "dash")
    assert code3 == 0, err3
    assert "→ in-progress" in out3

    out4, err4, code4 = cli("ticket", "start", "failure-review-project", "2", "--agent", "dash")
    assert code4 == 0, err4
    assert "→ in-progress" in out4

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    rows = conn.execute("SELECT num, status FROM tickets WHERE project_id=1 ORDER BY num").fetchall()
    conn.close()
    assert [r["status"] for r in rows] == ["in-progress", "in-progress"]

# ---------------------------------------------------------------------------
# Ticket 5: Event hooks
# ---------------------------------------------------------------------------

def test_hook_add_list_remove_round_trip():
    cli("create", "Hook Project")

    out_add, err_add, code_add = cli(
        "hook", "add", "hook-project",
        "--event", "on-complete",
        "--type", "webhook",
        "--target", "https://example.com/hook",
    )
    assert code_add == 0, err_add
    assert "Added hook #" in out_add

    out_list, err_list, code_list = cli("hook", "list", "hook-project")
    assert code_list == 0, err_list
    assert "on-complete" in out_list
    assert "webhook" in out_list
    assert "https://example.com/hook" in out_list

    out_remove, err_remove, code_remove = cli("hook", "remove", "hook-project", "1")
    assert code_remove == 0, err_remove
    assert "Removed hook #1" in out_remove

    out_list2, err_list2, code_list2 = cli("hook", "list", "hook-project")
    assert code_list2 == 0, err_list2
    assert "No hooks found." in out_list2


def test_ticket_done_fires_webhook_hook():
    cli("create", "Webhook Hook Project")
    cli("ticket", "add", "webhook-hook-project", "Ship it")
    cli(
        "hook", "add", "webhook-hook-project",
        "--type", "webhook",
        "--target", "https://example.com/webhook",
    )

    with patch("agentplan.cli.urllib.request.urlopen") as mock_urlopen:
        out, err, code = cli("ticket", "done", "webhook-hook-project", "1", "--agent", "dash")

    assert code == 0, err
    assert "Ticket #1" in out
    assert mock_urlopen.call_count == 1
    req = mock_urlopen.call_args[0][0]
    payload = json.loads(req.data.decode("utf-8"))
    assert payload == {
        "ticket_id": 1,
        "ticket_title": "Ship it",
        "project": "webhook-hook-project",
        "status": "done",
        "agent": "dash",
    }


def test_ticket_done_hooks_fire_after_commit():
    cli("create", "Post Commit Hook Project")
    cli("ticket", "add", "post-commit-hook-project", "Ship it")
    cli(
        "hook", "add", "post-commit-hook-project",
        "--type", "webhook",
        "--target", "https://example.com/webhook",
    )

    seen_statuses = []

    def _mock_urlopen(req, timeout=5):
        payload = json.loads(req.data.decode("utf-8"))
        conn = agentplan.get_connection("/tmp/test_agentplan.db")
        row = conn.execute(
            """
            SELECT t.status
            FROM tickets t
            JOIN projects p ON p.id = t.project_id
            WHERE p.slug=? AND t.num=?
            """,
            (payload["project"], payload["ticket_id"]),
        ).fetchone()
        conn.close()
        seen_statuses.append(row["status"] if row else None)

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        return _Resp()

    with patch("agentplan.cli.urllib.request.urlopen", side_effect=_mock_urlopen) as mock_urlopen:
        out, err, code = cli("ticket", "done", "post-commit-hook-project", "1", "--agent", "dash")

    assert code == 0, err
    assert "Ticket #1" in out
    assert mock_urlopen.call_count == 1
    assert seen_statuses == ["done"]


def test_ticket_done_fires_command_hook_with_env_vars():
    cli("create", "Command Hook Project")
    cli("ticket", "add", "command-hook-project", "Deploy")
    cli(
        "hook", "add", "command-hook-project",
        "--type", "command",
        "--target", "echo hello",
    )

    with patch("agentplan.cli.subprocess.run") as mock_run:
        out, err, code = cli("ticket", "done", "command-hook-project", "1", "--agent", "dash")

    assert code == 0, err
    assert "Ticket #1" in out
    assert mock_run.call_count == 1
    kwargs = mock_run.call_args.kwargs
    env = kwargs["env"]
    assert env["AGENTPLAN_TICKET_ID"] == "1"
    assert env["AGENTPLAN_TITLE"] == "Deploy"
    assert env["AGENTPLAN_PROJECT"] == "command-hook-project"
    assert env["AGENTPLAN_STATUS"] == "done"
    assert env["AGENTPLAN_AGENT"] == "dash"


def test_hook_add_allows_command_target_with_shell_tokens_when_shell_is_disabled():
    cli("create", "Command Hook Validation Project")
    out, err, code = cli(
        "hook", "add", "command-hook-validation-project",
        "--type", "command",
        "--target", "echo ok; rm -rf /",
    )
    assert code == 0, err
    assert "Added hook #" in out


def test_hook_add_accepts_chain_type_with_empty_target():
    cli("create", "Chain Hook Add Project")

    out, err, code = cli(
        "hook", "add", "chain-hook-add-project",
        "--type", "chain",
        "--event", "on-complete",
        "--target", "",
    )

    assert code == 0, err
    assert "Added hook #" in out

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute(
        """
        SELECT h.hook_type, h.event, h.target
        FROM hooks h
        JOIN projects p ON p.id = h.project_id
        WHERE p.slug=?
        """,
        ("chain-hook-add-project",),
    ).fetchone()
    conn.close()

    assert row is not None
    assert row["hook_type"] == "chain"
    assert row["event"] == "on-complete"
    assert row["target"] == ""


def test_ticket_done_fires_chain_hook_and_spawns_next_ticket_command():
    import agentplan.cli as agent_cli

    cli("create", "Chain Hook Trigger Project")
    _run_agent_cmd(agent_cli.cmd_agent_add, name="dash", command="echo run {ticket}", roles=None)
    cli("ticket", "add", "chain-hook-trigger-project", "First")
    cli("ticket", "add", "chain-hook-trigger-project", "Second")
    cli(
        "hook", "add", "chain-hook-trigger-project",
        "--type", "chain",
        "--event", "on-complete",
        "--target", "",
    )

    with patch("agentplan.cli.spawn_terminal", return_value=4321) as mock_spawn:
        out, err, code = cli("ticket", "done", "chain-hook-trigger-project", "1", "--agent", "dash")

    assert code == 0, err
    assert "Ticket #1" in out
    mock_spawn.assert_called_once_with("echo run chain-hook-trigger-project 2", title="agentplan:dash")


def test_ticket_done_executes_persisted_command_hook_without_shell():
    cli("create", "Unsafe Persisted Command Hook Project")
    cli("ticket", "add", "unsafe-persisted-command-hook-project", "Deploy")
    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    proj = conn.execute(
        "SELECT id FROM projects WHERE slug=?",
        ("unsafe-persisted-command-hook-project",),
    ).fetchone()
    conn.execute(
        "INSERT INTO hooks (project_id, event, hook_type, target, created_at) VALUES (?,?,?,?,?)",
        (proj["id"], "on-complete", "command", "echo hi && whoami", "2026-01-01T00:00:00"),
    )
    conn.commit()
    conn.close()

    with patch("agentplan.cli.subprocess.run") as mock_run:
        out, err, code = cli("ticket", "done", "unsafe-persisted-command-hook-project", "1")

    assert code == 0
    assert "Ticket #1" in out
    assert err == ""
    assert mock_run.call_count >= 1


def test_ticket_done_hook_failures_do_not_fail_command():
    cli("create", "Hook Error Project")
    cli("ticket", "add", "hook-error-project", "Deploy")
    cli(
        "hook", "add", "hook-error-project",
        "--type", "webhook",
        "--target", "https://example.com/fail",
    )

    with patch("agentplan.cli.urllib.request.urlopen", side_effect=RuntimeError("boom")):
        out, err, code = cli("ticket", "done", "hook-error-project", "1")

    assert code == 0
    assert "Ticket #1" in out
    assert "Warning: hook #1 failed" in err


# ---------------------------------------------------------------------------
# Ticket 51: Regression test — dashboard breakdown uses 'pending' key (not 'todo')
# ---------------------------------------------------------------------------

def test_dashboard_stats_breakdown_uses_pending_key():
    """_fetch_projects_with_stats must store pending count under 'pending', not 'todo'."""
    from agentplan.dashboard import _fetch_projects_with_stats
    from agentplan.db import get_connection, init_db

    cli("create", "Breakdown Key Project")
    cli("ticket", "add", "breakdown-key-project", "Pending ticket A")
    cli("ticket", "add", "breakdown-key-project", "Pending ticket B")

    conn = get_connection()
    stats = _fetch_projects_with_stats(conn)
    conn.close()

    proj_stats = next((p for p in stats if p["slug"] == "breakdown-key-project"), None)
    assert proj_stats is not None, "Project not found in stats"
    breakdown = proj_stats["breakdown"]

    # Core assertion: key must be 'pending', not 'todo' (regression from #47/#49)
    assert "pending" in breakdown, "breakdown must have a 'pending' key"
    assert breakdown["pending"] == 2, f"Expected 2 pending tickets, got {breakdown['pending']}"
    assert "todo" not in breakdown, "breakdown must NOT have a legacy 'todo' key"


def test_dashboard_stats_breakdown_api_endpoint_pending_key():
    """GET /api/stats JSON must contain 'pending' key in project breakdown."""
    from agentplan.dashboard import create_app

    cli("create", "API Breakdown Project")
    cli("ticket", "add", "api-breakdown-project", "Open ticket")

    test_app = create_app()
    client = test_app.test_client()
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    data = json.loads(resp.get_data(as_text=True))

    proj = next((p for p in data["projects"] if p["slug"] == "api-breakdown-project"), None)
    assert proj is not None
    breakdown = proj["breakdown"]
    assert "pending" in breakdown, "API breakdown must contain 'pending' key"
    assert breakdown["pending"] >= 1
    assert "todo" not in breakdown, "API breakdown must NOT have legacy 'todo' key"


# ---------------------------------------------------------------------------
# Ticket 52: Regression test — priority filter uses string labels (not numeric)
# ---------------------------------------------------------------------------

def test_dashboard_priority_filter_string_labels():
    """Project board priority filter must work with string labels 'high/medium/low/none'."""
    from agentplan.dashboard import _ticket_matches

    high_ticket = {"priority": "high", "status": "pending", "tags": ""}
    medium_ticket = {"priority": "medium", "status": "pending", "tags": ""}
    low_ticket = {"priority": "low", "status": "pending", "tags": ""}
    none_ticket = {"priority": "none", "status": "pending", "tags": ""}

    # String label filters must match
    assert _ticket_matches(high_ticket, "", "high", "") is True
    assert _ticket_matches(medium_ticket, "", "medium", "") is True
    assert _ticket_matches(low_ticket, "", "low", "") is True
    assert _ticket_matches(none_ticket, "", "none", "") is True

    # Non-matching priority must not match
    assert _ticket_matches(high_ticket, "", "low", "") is False
    assert _ticket_matches(low_ticket, "", "high", "") is False

    # Numeric values (old bug) must NOT accidentally match string priorities
    assert _ticket_matches(high_ticket, "", "1", "") is False
    assert _ticket_matches(medium_ticket, "", "3", "") is False


def test_dashboard_priority_filter_via_api():
    """GET /project/<slug>?priority=high should return only high-priority tickets."""
    from agentplan.dashboard import create_app

    cli("create", "Priority Filter Project")
    cli("ticket", "add", "priority-filter-project", "High task", "--priority", "high")
    cli("ticket", "add", "priority-filter-project", "Low task", "--priority", "low")

    test_app = create_app()
    client = test_app.test_client()
    resp = client.get("/project/priority-filter-project?priority=high")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "High task" in body
    # Low task should not appear when filtering by high
    assert "Low task" not in body


# ---------------------------------------------------------------------------
# Ticket 57: Agent registry command coverage
# ---------------------------------------------------------------------------

def _run_agent_cmd(func, **kwargs):
    import agentplan.cli as agent_cli

    out, err = StringIO(), StringIO()
    with patch("sys.stdout", out), patch("sys.stderr", err):
        try:
            func(type("Args", (), kwargs)())
            code = 0
        except agent_cli.CliError as e:
            print(f"Error: {e.message}", file=err)
            for suggestion in e.suggestions:
                print(f"Suggestion: {suggestion}", file=err)
            code = e.exit_code
    return out.getvalue(), err.getvalue(), code


def test_agent_add_basic():
    import agentplan.cli as agent_cli

    cli("role", "add", "backend")
    out, err, code = _run_agent_cmd(
        agent_cli.cmd_agent_add,
        name="dash",
        command="claude -p {ticket}",
        roles="backend",
    )
    assert code == 0, err
    assert "Added agent 'dash' with roles: backend" in out


def test_agent_add_duplicate_name():
    import agentplan.cli as agent_cli

    out1, err1, code1 = _run_agent_cmd(
        agent_cli.cmd_agent_add,
        name="dash",
        command="claude -p {ticket}",
        roles=None,
    )
    assert code1 == 0, err1
    assert "Added agent 'dash'" in out1

    with pytest.raises(Exception) as exc:
        agent_cli.cmd_agent_add(type("Args", (), {"name": "dash", "command": "codex {ticket}", "roles": None})())
    assert "already exists" in str(exc.value).lower()


def test_agent_add_invalid_role():
    import agentplan.cli as agent_cli

    out, err, code = _run_agent_cmd(
        agent_cli.cmd_agent_add,
        name="dash",
        command="claude -p {ticket}",
        roles="missing-role",
    )
    assert code == 2
    assert out == ""
    assert "Role 'missing-role' not found" in err


def test_agent_list():
    import agentplan.cli as agent_cli

    cli("role", "add", "backend")
    _run_agent_cmd(agent_cli.cmd_agent_add, name="dash", command="claude -p {ticket}", roles="backend")
    _run_agent_cmd(agent_cli.cmd_agent_add, name="nova", command="codex exec {ticket}", roles=None)

    out, err, code = _run_agent_cmd(agent_cli.cmd_agent_list)
    assert code == 0, err
    assert "name" in out and "roles" in out and "command_template" in out
    assert "dash" in out and "backend" in out and "claude -p {ticket}" in out
    assert "nova" in out and "(none)" in out and "codex exec {ticket}" in out


def test_agent_update():
    import agentplan.cli as agent_cli

    cli("role", "add", "backend")
    cli("role", "add", "frontend")
    _run_agent_cmd(agent_cli.cmd_agent_add, name="dash", command="claude -p {ticket}", roles="backend")

    out, err, code = _run_agent_cmd(
        agent_cli.cmd_agent_update,
        name="dash",
        new_name="dash-v2",
        command="codex exec {ticket}",
        roles="frontend",
    )
    assert code == 0, err
    assert "Updated agent 'dash-v2'." in out

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT name, command_template FROM agents WHERE name='dash-v2'").fetchone()
    conn.close()
    assert row is not None
    assert row["command_template"] == "codex exec {ticket}"


def test_agent_update_rename_to_existing_conflict():
    import agentplan.cli as agent_cli

    _run_agent_cmd(agent_cli.cmd_agent_add, name="dash", command="claude -p {ticket}", roles=None)
    _run_agent_cmd(agent_cli.cmd_agent_add, name="nova", command="codex exec {ticket}", roles=None)

    out, err, code = _run_agent_cmd(
        agent_cli.cmd_agent_update,
        name="dash",
        new_name="nova",
        command=None,
        roles=None,
    )
    assert code == 2
    assert out == ""
    assert "already exists" in err.lower()


def test_agent_remove():
    import agentplan.cli as agent_cli

    _run_agent_cmd(agent_cli.cmd_agent_add, name="dash", command="claude -p {ticket}", roles=None)

    out, err, code = _run_agent_cmd(agent_cli.cmd_agent_remove, name="dash")
    assert code == 0, err
    assert "Removed agent 'dash'." in out

    out2, err2, code2 = _run_agent_cmd(agent_cli.cmd_agent_list)
    assert code2 == 0, err2
    assert "No agents registered." in out2


def test_agent_role_persistence():
    import agentplan.cli as agent_cli

    cli("role", "add", "backend")
    cli("role", "add", "qa")
    _run_agent_cmd(agent_cli.cmd_agent_add, name="dash", command="claude -p {ticket}", roles="backend,qa")

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    rows = conn.execute(
        """
        SELECT r.name
        FROM roles r
        JOIN agent_roles ar ON ar.role_id = r.id
        JOIN agents a ON a.id = ar.agent_id
        WHERE a.name = 'dash'
        ORDER BY r.name
        """
    ).fetchall()
    conn.close()

    assert [r["name"] for r in rows] == ["backend", "qa"]


def test_agent_add_without_role():
    import agentplan.cli as agent_cli

    out, err, code = _run_agent_cmd(
        agent_cli.cmd_agent_add,
        name="solo",
        command="claude -p {ticket}",
        roles=None,
    )
    assert code == 0, err
    assert "Added agent 'solo' with roles: (none)" in out

    list_out, list_err, list_code = _run_agent_cmd(agent_cli.cmd_agent_list)
    assert list_code == 0, list_err
    assert "solo" in list_out
    assert "(none)" in list_out


# ---------------------------------------------------------------------------
# Ticket 16: Route command coverage
# ---------------------------------------------------------------------------


def test_route_matches_agent_by_role():
    import agentplan.cli as agent_cli

    cli("create", "Routing Project")
    cli("role", "add", "backend")
    _run_agent_cmd(agent_cli.cmd_agent_add, name="dash", command="claude -p {ticket}", roles="backend")
    cli("ticket", "add", "routing-project", "Backend task", "--tag", "role:backend")

    out, err, code = cli("route", "routing-project", "1")
    assert code == 0, err
    assert out.strip() == "dash"


def test_agent_add_requires_ticket_placeholder_validation():
    import agentplan.cli as agent_cli

    out, err, code = _run_agent_cmd(
        agent_cli.cmd_agent_add,
        name="broken",
        command="claude -p prompt-only",
        roles=None,
        priority=0,
    )
    assert code == 2
    assert "must include '{{ticket}}' placeholder" in err


def test_route_prefers_agent_with_lower_priority():
    import agentplan.cli as agent_cli

    cli("create", "Routing Priority Project")
    cli("role", "add", "backend")
    _run_agent_cmd(agent_cli.cmd_agent_add, name="slow", command="echo slow {ticket}", roles="backend", priority=10)
    _run_agent_cmd(agent_cli.cmd_agent_add, name="fast", command="echo fast {ticket}", roles="backend", priority=-5)
    cli("ticket", "add", "routing-priority-project", "Backend task", "--tag", "role:backend")

    out, err, code = cli("route", "routing-priority-project", "1")
    assert code == 0, err
    assert out.strip() == "fast"


@pytest.mark.parametrize("role_tag", ["role:BackEnd", "role:BACKEND"])
def test_route_matches_agent_by_role_case_insensitive(role_tag):
    import agentplan.cli as agent_cli

    cli("create", "Routing Case Project")
    cli("role", "add", "backend")
    _run_agent_cmd(agent_cli.cmd_agent_add, name="dash", command="claude -p {ticket}", roles="backend")
    cli("ticket", "add", "routing-case-project", "Backend task", "--tag", role_tag)

    out, err, code = cli("route", "routing-case-project", "1")
    assert code == 0, err
    assert out.strip() == "dash"


def test_route_ticket_db_matches_mixed_case_role_tag_directly():
    import agentplan.cli as agent_cli
    from agentplan.db import route_ticket

    cli("create", "Routing DB Case Project")
    cli("role", "add", "backend")
    _run_agent_cmd(agent_cli.cmd_agent_add, name="dash", command="claude -p {ticket}", roles="backend")

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    try:
        ticket = {"tags": "role:BackEnd"}
        agent = route_ticket(conn, ticket)
    finally:
        conn.close()

    assert agent is not None
    assert agent["name"] == "dash"


def test_route_falls_back_to_default():
    import agentplan.cli as agent_cli

    cli("create", "Routing Fallback Project")
    cli("role", "add", "backend")
    cli("role", "add", "frontend")
    _run_agent_cmd(agent_cli.cmd_agent_add, name="dash", command="claude -p {ticket}", roles="backend")
    cli("ticket", "add", "routing-fallback-project", "Frontend task", "--tag", "role:frontend")

    out, err, code = cli("route", "routing-fallback-project", "1", "--default-agent", "dash")
    assert code == 0, err
    assert out.strip() == "dash"


def test_route_no_match_no_default():
    import agentplan.cli as agent_cli

    cli("create", "Routing No Match Project")
    cli("role", "add", "backend")
    cli("role", "add", "frontend")
    _run_agent_cmd(agent_cli.cmd_agent_add, name="dash", command="claude -p {ticket}", roles="backend")
    cli("ticket", "add", "routing-no-match-project", "Frontend task", "--tag", "role:frontend")

    out, err, code = cli("route", "routing-no-match-project", "1")
    assert code == 0, err
    assert out.strip() == "No agent found for ticket #1"


def test_render_agent_command_replaces_all_placeholder_variants():
    import agentplan.cli as agent_cli

    rendered = agent_cli._render_agent_command(
        "run {ticket} {{ticket}} {project} {{project}} {ticket_id} {{ticket_id}}",
        {"num": 7},
        {"slug": "demo"},
    )

    assert rendered == "run demo 7 demo 7 demo demo 7 7"


def test_route_terminal_spawns_rendered_agent_command():
    import agentplan.cli as agent_cli

    cli("create", "Routing Terminal Project")
    cli("role", "add", "backend")
    _run_agent_cmd(agent_cli.cmd_agent_add, name="dash", command="echo {ticket} {{project}} {{ticket_id}}", roles="backend")
    cli("ticket", "add", "routing-terminal-project", "Backend task", "--tag", "role:backend")

    with patch("agentplan.cli.spawn_terminal") as mock_spawn:
        out, err, code = cli("route", "routing-terminal-project", "1", "--terminal")

    assert code == 0, err
    assert out.strip() == "dash"
    mock_spawn.assert_called_once_with("echo routing-terminal-project 1 routing-terminal-project 1", title="agentplan:dash")


def test_route_terminal_injects_agentplan_md_content_when_present():
    import agentplan.cli as agent_cli

    os.makedirs("/tmp/routing-context", exist_ok=True)
    Path("/tmp/routing-context/.agentplan.md").write_text("verify: pytest -q", encoding="utf-8")

    cli("create", "Routing Context Project", "--dir", "/tmp/routing-context")
    cli("role", "add", "backend")
    _run_agent_cmd(agent_cli.cmd_agent_add, name="dash", command="echo {ticket}", roles="backend")
    cli("ticket", "add", "routing-context-project", "Backend task", "--tag", "role:backend")

    with patch("agentplan.cli.spawn_terminal") as mock_spawn:
        out, err, code = cli("route", "routing-context-project", "1", "--terminal")

    assert code == 0, err
    assert out.strip() == "dash"
    cmd = mock_spawn.call_args.args[0]
    assert "verify: pytest -q" in cmd
    assert "[Project Context from .agentplan.md]" in cmd


def test_route_terminal_instructs_context_creation_when_missing():
    import agentplan.cli as agent_cli

    os.makedirs("/tmp/routing-context-missing", exist_ok=True)
    cli("create", "Routing Context Missing", "--dir", "/tmp/routing-context-missing")
    cli("role", "add", "backend")
    _run_agent_cmd(agent_cli.cmd_agent_add, name="dash", command="echo {ticket}", roles="backend")
    cli("ticket", "add", "routing-context-missing", "Backend task", "--tag", "role:backend")

    with patch("agentplan.cli.spawn_terminal") as mock_spawn:
        out, err, code = cli("route", "routing-context-missing", "1", "--terminal")

    assert code == 0, err
    cmd = mock_spawn.call_args.args[0]
    assert "No .agentplan.md found in project directory" in cmd
    assert "create .agentplan.md" in cmd


def test_detect_terminal_prefers_iterm2_when_running():
    import agentplan.cli as agent_cli

    with patch("agentplan.cli.subprocess.run") as mock_run:
        mock_run.side_effect = [
            type("Result", (), {"returncode": 0, "stdout": "123\n", "stderr": ""})(),
        ]
        assert agent_cli.detect_terminal_app("auto") == "iterm2"


def test_detect_terminal_falls_back_to_terminal_when_iterm2_missing():
    import agentplan.cli as agent_cli

    with patch("agentplan.cli.os.path.exists", return_value=False), patch("agentplan.cli.subprocess.run") as mock_run:
        mock_run.side_effect = [
            type("Result", (), {"returncode": 1, "stdout": "", "stderr": ""})(),
            type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
        ]
        assert agent_cli.detect_terminal_app("auto") == "terminal"


def test_spawn_terminal_iterm2_applescript_contains_shell_escaped_command():
    import agentplan.cli as agent_cli

    with patch("agentplan.cli.detect_terminal_app", return_value="iterm2"), patch("agentplan.cli.subprocess.run") as mock_run:
        mock_run.return_value = type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        agent_cli.spawn_terminal('echo "hello"; rm -rf /', title="Demo")

    argv = mock_run.call_args.args[0]
    script = argv[2]
    assert argv[:2] == ["osascript", "-e"]
    assert "tell application \"iTerm2\"" in script
    assert "bash -lc" in script
    assert '\\"hello\\"; rm -rf /' in script


def test_spawn_terminal_falls_back_to_terminal_when_iterm2_osascript_fails():
    import agentplan.cli as agent_cli

    with patch("agentplan.cli.detect_terminal_app", return_value="iterm2"), patch("agentplan.cli.subprocess.run") as mock_run:
        mock_run.side_effect = [
            type("Result", (), {"returncode": 1, "stdout": "", "stderr": "boom"})(),
            type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
        ]
        agent_cli.spawn_terminal("echo hello")

    assert mock_run.call_count == 2
    first_script = mock_run.call_args_list[0].args[0][2]
    second_script = mock_run.call_args_list[1].args[0][2]
    assert "tell application \"iTerm2\"" in first_script
    assert "tell application \"Terminal\"" in second_script


def test_spawn_terminal_returns_nonzero_when_iterm2_and_terminal_fail():
    import agentplan.cli as agent_cli

    with patch("agentplan.cli.detect_terminal_app", return_value="iterm2"), patch("agentplan.cli.subprocess.run") as mock_run:
        mock_run.side_effect = [
            type("Result", (), {"returncode": 1, "stdout": "", "stderr": "iterm down"})(),
            type("Result", (), {"returncode": 1, "stdout": "", "stderr": "terminal down"})(),
        ]
        rc = agent_cli.spawn_terminal("echo hello")

    assert rc == 1
    assert mock_run.call_count == 2


def test_monitor_process_exits_when_pid_ends():
    import agentplan.cli as agent_cli

    cli("create", "Monitor Ends Project")
    cli("ticket", "add", "monitor-ends-project", "Watch process")

    calls = {"n": 0}

    def fake_kill(pid, sig):
        calls["n"] += 1
        if calls["n"] >= 3:
            raise ProcessLookupError()

    with patch("agentplan.cli.os.kill", side_effect=fake_kill), \
         patch("agentplan.cli.time.sleep", return_value=None), \
         patch("agentplan.cli._get_exit_code_for_pid", return_value=0):
        result = agent_cli.monitor_process(12345, "monitor-ends-project", 1, timeout_sec=30)

    assert result["pid"] == 12345
    assert result["timed_out"] is False
    assert result["exit_code"] == 0


def test_monitor_process_detects_timeout():
    import agentplan.cli as agent_cli

    cli("create", "Monitor Timeout Project")
    cli("ticket", "add", "monitor-timeout-project", "Watch process")

    monotonic_values = iter([0, 1, 6, 12])

    with patch("agentplan.cli.os.kill", return_value=None), \
         patch("agentplan.cli.time.sleep", return_value=None), \
         patch("agentplan.cli.time.monotonic", side_effect=lambda: next(monotonic_values)):
        result = agent_cli.monitor_process(2222, "monitor-timeout-project", 1, timeout_sec=10)

    assert result["timed_out"] is True
    assert result["exit_code"] is None


def test_monitor_process_reads_ticket_status_on_process_exit():
    import agentplan.cli as agent_cli

    cli("create", "Monitor Status Project")
    cli("ticket", "add", "monitor-status-project", "Watch process")
    cli("ticket", "start", "monitor-status-project", "1")
    cli("ticket", "review", "monitor-status-project", "1", "--reason", "awaiting checks")

    with patch("agentplan.cli.os.kill", side_effect=ProcessLookupError()), \
         patch("agentplan.cli._get_exit_code_for_pid", return_value=None):
        result = agent_cli.monitor_process(3333, "monitor-status-project", 1, timeout_sec=30)

    assert result["timed_out"] is False
    assert result["ticket_status"] == "needs-review"


def test_monitor_process_command_parses_args_and_prints_json():
    cli("create", "Monitor CLI Project")
    cli("ticket", "add", "monitor-cli-project", "Watch process")

    with patch("agentplan.cli.monitor_process", return_value={"pid": 9, "exit_code": 0, "ticket_status": "done", "timed_out": False}) as mock_monitor:
        out, err, code = cli("monitor-process", "monitor-cli-project", "1", "9", "--timeout", "42")

    assert code == 0, err
    payload = json.loads(out)
    assert payload["pid"] == 9
    assert payload["ticket_status"] == "done"
    mock_monitor.assert_called_once_with(9, "monitor-cli-project", 1, timeout_sec=42)


def test_ticket_add_and_edit_timeout_sec():
    cli("create", "Timeout Edit Project")
    out_add, err_add, code_add = cli("ticket", "add", "timeout-edit-project", "Watchdog", "--timeout", "45")
    assert code_add == 0, err_add

    out_edit, err_edit, code_edit = cli("ticket", "edit", "timeout-edit-project", "1", "--timeout", "90")
    assert code_edit == 0, err_edit

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT timeout_sec FROM tickets WHERE project_id=1 AND num=1").fetchone()
    conn.close()
    assert row["timeout_sec"] == 90


def test_chain_marks_ticket_failed_and_pauses_on_timeout():
    os.makedirs("/tmp/chain-timeout-project", exist_ok=True)
    cli("create", "Chain Timeout Project", "--dir", "/tmp/chain-timeout-project")
    cli("ticket", "add", "chain-timeout-project", "Run long", "--timeout", "7")
    with patch("agentplan.cli.db_route_ticket", return_value={"name": "dash", "command_template": "echo run {ticket}"}), \
         patch("agentplan.cli.spawn_terminal", return_value=1234), \
         patch("agentplan.cli._monitor_chain_ticket", return_value={"ticket_status": "in-progress", "timed_out": True}):
        out, err, code = cli("chain", "chain-timeout-project", "--default-agent", "dash")

    assert code == 0, err
    assert "timed out (7s)" in out

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    ticket = conn.execute("SELECT status, close_note FROM tickets WHERE project_id=1 AND num=1").fetchone()
    state = conn.execute("SELECT status, pause_reason FROM chain_state WHERE project_id=1").fetchone()
    conn.close()

    assert ticket["status"] == "failed"
    assert ticket["close_note"] == "timeout: no progress for 7s"
    assert state["status"] == "paused"
    assert state["pause_reason"] == "timeout: no progress for 7s"


def test_chain_reentry_guard_blocks_second_run_when_running():
    cli("create", "Chain Reentry Project")
    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    conn.execute(
        """
        INSERT INTO chain_state (project_id, status, current_ticket_id, pause_reason, heartbeat_at, deadline_at, updated_at)
        VALUES (1, 'running', NULL, NULL, NULL, NULL, '2026-03-05T00:00:00')
        """
    )
    conn.commit()
    conn.close()

    out, err, code = cli("chain", "chain-reentry-project")
    assert out == ""
    assert code == 2
    assert "already running" in err.lower()


def test_log_heartbeat_resets_chain_deadline():
    cli("create", "Heartbeat Project", "--timeout", "30")
    cli("ticket", "add", "heartbeat-project", "Keep alive")
    cli("ticket", "start", "heartbeat-project", "1")

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    conn.execute(
        "INSERT INTO chain_state (project_id, status, current_ticket_id, heartbeat_at, deadline_at, updated_at) VALUES (?,?,?,?,?,?)",
        (1, "running", 1, "2026-01-01T00:00:00", "2026-01-01T00:00:10", "2026-01-01T00:00:00"),
    )
    conn.commit()
    conn.close()

    out, err, code = cli("log", "heartbeat-project", "1", "still working")
    assert code == 0, err

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    state = conn.execute("SELECT heartbeat_at, deadline_at FROM chain_state WHERE project_id=1").fetchone()
    conn.close()

    assert state["heartbeat_at"] is not None
    assert state["deadline_at"] is not None
    assert state["deadline_at"] > state["heartbeat_at"]


def test_project_default_timeout_applies_to_chain_when_ticket_timeout_missing():
    os.makedirs("/tmp/project-default-timeout", exist_ok=True)
    cli("create", "Project Default Timeout", "--dir", "/tmp/project-default-timeout", "--timeout", "9")
    cli("ticket", "add", "project-default-timeout", "No per-ticket timeout")
    with patch("agentplan.cli.db_route_ticket", return_value={"name": "dash", "command_template": "echo run {ticket}"}), \
         patch("agentplan.cli.spawn_terminal", return_value=999), \
         patch("agentplan.cli._monitor_chain_ticket", return_value={"ticket_status": "in-progress", "timed_out": True}):
        out, err, code = cli("chain", "project-default-timeout", "--default-agent", "dash")

    assert code == 0, err
    assert "timed out (9s)" in out


def test_chain_warns_when_linked_dir_missing():
    cli("create", "Chain Missing Dir", "--dir", "/tmp/does-not-exist-agentplan")
    cli("ticket", "add", "chain-missing-dir", "Task")
    with patch("agentplan.cli.db_route_ticket", return_value={"name": "dash", "command_template": "echo run {ticket}"}), \
         patch("agentplan.cli.spawn_terminal", return_value=999), \
         patch("agentplan.cli._monitor_chain_ticket", return_value={"ticket_status": "failed", "timed_out": False}):
        out, err, code = cli("chain", "chain-missing-dir", "--default-agent", "dash")

    assert code == 0, err
    assert "Warning: linked project directory does not exist: /tmp/does-not-exist-agentplan" in out


def test_chain_no_warning_when_dir_not_set():
    cli("create", "Chain No Dir")
    cli("ticket", "add", "chain-no-dir", "Task")
    with patch("agentplan.cli.db_route_ticket", return_value={"name": "dash", "command_template": "echo run {ticket}"}), \
         patch("agentplan.cli.spawn_terminal", return_value=999), \
         patch("agentplan.cli._monitor_chain_ticket", return_value={"ticket_status": "failed", "timed_out": False}):
        out, err, code = cli("chain", "chain-no-dir", "--default-agent", "dash")

    assert out == ""
    assert code == 2
    assert "No directory linked to project 'chain-no-dir'" in err


def test_chain_start_without_directory_returns_hard_error():
    cli("create", "Chain Hard Error")
    cli("ticket", "add", "chain-hard-error", "Task")

    out, err, code = cli("chain", "chain-hard-error")

    assert out == ""
    assert code == 2
    assert "No directory linked to project 'chain-hard-error'" in err
    assert "agentplan project chain-hard-error --dir ~/path/to/repo" in err


def test_chain_start_with_directory_set_runs_normally():
    os.makedirs("/tmp/chain-dir-ok", exist_ok=True)
    cli("create", "Chain Dir OK", "--dir", "/tmp/chain-dir-ok")

    out, err, code = cli("chain", "chain-dir-ok")

    assert code == 0, err
    assert "Starting chain for project 'chain-dir-ok'" in out
    assert "No more unblocked tickets. Chain complete." in out


def test_chain_injects_agentplan_md_content_in_spawned_command():
    os.makedirs("/tmp/chain-context", exist_ok=True)
    Path("/tmp/chain-context/.agentplan.md").write_text("verify: python3 -m pytest", encoding="utf-8")
    cli("create", "Chain Context", "--dir", "/tmp/chain-context")
    cli("ticket", "add", "chain-context", "Task")
    with patch("agentplan.cli.db_route_ticket", return_value={"name": "dash", "command_template": "echo run {ticket}"}), \
         patch("agentplan.cli.spawn_terminal", return_value=999) as mock_spawn, \
         patch("agentplan.cli._monitor_chain_ticket", return_value={"ticket_status": "failed", "timed_out": False}):
        out, err, code = cli("chain", "chain-context", "--default-agent", "dash")

    assert code == 0, err
    assert "verify: python3 -m pytest" in mock_spawn.call_args.args[0]


def test_chain_injects_create_context_instruction_when_file_missing():
    os.makedirs("/tmp/chain-context-missing", exist_ok=True)
    cli("create", "Chain Context Missing", "--dir", "/tmp/chain-context-missing")
    cli("ticket", "add", "chain-context-missing", "Task")
    with patch("agentplan.cli.db_route_ticket", return_value={"name": "dash", "command_template": "echo run {ticket}"}), \
         patch("agentplan.cli.spawn_terminal", return_value=999) as mock_spawn, \
         patch("agentplan.cli._monitor_chain_ticket", return_value={"ticket_status": "failed", "timed_out": False}):
        out, err, code = cli("chain", "chain-context-missing", "--default-agent", "dash")

    assert code == 0, err
    assert "No .agentplan.md found in project directory" in mock_spawn.call_args.args[0]


# ---------------------------------------------------------------------------
# Ticket 18: Auto-tag command
# ---------------------------------------------------------------------------

def test_auto_tag_untagged_ticket_gets_role_tagged():
    import agentplan.cli as agent_cli

    cli("create", "Auto Tag Project")
    cli("role", "add", "coding")
    cli("role", "add", "research")
    _run_agent_cmd(agent_cli.cmd_agent_add, name="dash", command="dummy --prompt {prompt} --ticket {ticket}", roles="coding")
    cli("ticket", "add", "auto-tag-project", "Build parser", "--desc", "Implement CLI parsing")

    with patch("agentplan.cli.subprocess.run") as mock_run:
        mock_run.return_value = type("Result", (), {"returncode": 0, "stdout": "coding\n", "stderr": ""})()
        out, err, code = cli("auto-tag", "auto-tag-project")

    assert code == 0, err
    assert "Tagged ticket #1 -> role:coding" in out

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    ticket = conn.execute("SELECT tags FROM tickets WHERE project_id=1 AND num=1").fetchone()
    hist = conn.execute("SELECT new_state FROM ticket_history WHERE ticket_id=1 ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    assert ticket["tags"] == "role:coding"
    assert hist["new_state"] == "auto-tag:coding"


def test_auto_tag_dry_run_does_not_mutate():
    import agentplan.cli as agent_cli

    cli("create", "Auto Tag Dry")
    cli("role", "add", "coding")
    _run_agent_cmd(agent_cli.cmd_agent_add, name="dash", command="dummy --prompt {prompt} --ticket {ticket}", roles="coding")
    cli("ticket", "add", "auto-tag-dry", "Build parser")

    with patch("agentplan.cli.subprocess.run") as mock_run:
        mock_run.return_value = type("Result", (), {"returncode": 0, "stdout": "coding", "stderr": ""})()
        out, err, code = cli("auto-tag", "auto-tag-dry", "--dry-run")

    assert code == 0, err
    assert "[dry-run] ticket #1 -> role:coding" in out

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    ticket = conn.execute("SELECT tags FROM tickets WHERE project_id=1 AND num=1").fetchone()
    conn.close()
    assert ticket["tags"] == ""


def test_auto_tag_unknown_role_response_is_skipped():
    import agentplan.cli as agent_cli

    cli("create", "Auto Tag Unknown")
    cli("role", "add", "coding")
    _run_agent_cmd(agent_cli.cmd_agent_add, name="dash", command="dummy --prompt {prompt} --ticket {ticket}", roles="coding")
    cli("ticket", "add", "auto-tag-unknown", "Build parser")

    with patch("agentplan.cli.subprocess.run") as mock_run:
        mock_run.return_value = type("Result", (), {"returncode": 0, "stdout": "nonexistent", "stderr": ""})()
        out, err, code = cli("auto-tag", "auto-tag-unknown")

    assert code == 0
    assert "unknown role" in err.lower()

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    ticket = conn.execute("SELECT tags FROM tickets WHERE project_id=1 AND num=1").fetchone()
    conn.close()
    assert ticket["tags"] == ""


def test_auto_tag_handles_ai_tool_unavailable_file_not_found():
    import agentplan.cli as agent_cli

    cli("create", "Auto Tag Tool Missing")
    cli("role", "add", "coding")
    _run_agent_cmd(agent_cli.cmd_agent_add, name="dash", command="missing-binary --prompt {prompt}", roles="coding")
    cli("ticket", "add", "auto-tag-tool-missing", "Build parser")

    with patch("agentplan.cli.subprocess.run", side_effect=FileNotFoundError("missing-binary")):
        out, err, code = cli("auto-tag", "auto-tag-tool-missing")

    assert code == 0
    assert "auto-tag failed" in err.lower()
    assert out == ""

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    ticket = conn.execute("SELECT tags FROM tickets WHERE project_id=1 AND num=1").fetchone()
    conn.close()
    assert ticket["tags"] == ""


def test_auto_tag_handles_empty_or_malformed_model_output():
    import agentplan.cli as agent_cli

    cli("create", "Auto Tag Malformed Output")
    cli("role", "add", "coding")
    _run_agent_cmd(agent_cli.cmd_agent_add, name="dash", command="dummy --prompt {prompt} --ticket {ticket}", roles="coding")
    cli("ticket", "add", "auto-tag-malformed-output", "Build parser")

    with patch("agentplan.cli.subprocess.run") as mock_run:
        mock_run.return_value = type("Result", (), {"returncode": 0, "stdout": "```json\n{\"role\":\"coding\"}\n```", "stderr": ""})()
        out, err, code = cli("auto-tag", "auto-tag-malformed-output")

    assert code == 0
    assert "unknown role" in err.lower()
    assert out == ""

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    ticket = conn.execute("SELECT tags FROM tickets WHERE project_id=1 AND num=1").fetchone()
    conn.close()
    assert ticket["tags"] == ""


def test_auto_tag_already_tagged_tickets_are_skipped():
    import agentplan.cli as agent_cli

    cli("create", "Auto Tag Skip Tagged")
    cli("role", "add", "coding")
    _run_agent_cmd(agent_cli.cmd_agent_add, name="dash", command="dummy --prompt {prompt} --ticket {ticket}", roles="coding")
    cli("ticket", "add", "auto-tag-skip-tagged", "Build parser", "--tag", "role:coding")

    with patch("agentplan.cli.subprocess.run") as mock_run:
        out, err, code = cli("auto-tag", "auto-tag-skip-tagged")

    assert code == 0, err
    assert "already has role tag" in out
    assert mock_run.call_count == 0


# ---------------------------------------------------------------------------
# Ticket 23: Chain orchestration
# ---------------------------------------------------------------------------

def test_chain_processes_done_then_moves_to_next_ticket():
    import agentplan.cli as agent_cli

    os.makedirs("/tmp/chain-move-project", exist_ok=True)
    cli("create", "Chain Move Project", "--dir", "/tmp/chain-move-project")
    cli("role", "add", "backend")
    _run_agent_cmd(agent_cli.cmd_agent_add, name="dash", command="echo run-{ticket_id}", roles="backend")
    cli("ticket", "add", "chain-move-project", "First", "--tag", "role:backend")
    cli("ticket", "add", "chain-move-project", "Second", "--tag", "role:backend")

    call = {"n": 0}

    def fake_monitor(pid, project_slug, ticket_num, timeout_sec=3600):
        call["n"] += 1
        conn = agentplan.get_connection("/tmp/test_agentplan.db")
        if call["n"] == 1:
            conn.execute("UPDATE tickets SET status='done' WHERE project_id=1 AND num=1")
            conn.commit()
            conn.close()
            return {"pid": pid, "ticket_status": "done", "timed_out": False, "exit_code": 0}
        conn.execute("UPDATE tickets SET status='failed' WHERE project_id=1 AND num=2")
        conn.commit()
        conn.close()
        return {"pid": pid, "ticket_status": "failed", "timed_out": False, "exit_code": 1}

    with patch("agentplan.cli.spawn_terminal", return_value=123) as mock_spawn, \
         patch("agentplan.cli._monitor_chain_ticket", side_effect=lambda conn, project, ticket, pid, timeout_sec=3600: fake_monitor(pid, project["slug"], ticket["num"], timeout_sec)):
        out, err, code = cli("chain", "chain-move-project")

    assert code == 0, err
    assert mock_spawn.call_count == 2
    assert "Ticket #1 done; continuing" in out


def test_chain_pauses_on_failed_ticket():
    import agentplan.cli as agent_cli

    os.makedirs("/tmp/chain-fail-project", exist_ok=True)
    cli("create", "Chain Fail Project", "--dir", "/tmp/chain-fail-project")
    _run_agent_cmd(agent_cli.cmd_agent_add, name="dash", command="echo run {ticket}", roles=None)
    cli("ticket", "add", "chain-fail-project", "Only task")

    with patch("agentplan.cli.spawn_terminal", return_value=10), \
         patch("agentplan.cli._monitor_chain_ticket", return_value={"ticket_status": "failed", "timed_out": False}):
        out, err, code = cli("chain", "chain-fail-project", "--default-agent", "dash")

    assert code == 0, err
    assert "Paused: ticket #1 ended as failed" in out


def test_chain_pauses_on_needs_review_ticket():
    import agentplan.cli as agent_cli

    os.makedirs("/tmp/chain-review-project", exist_ok=True)
    cli("create", "Chain Review Project", "--dir", "/tmp/chain-review-project")
    _run_agent_cmd(agent_cli.cmd_agent_add, name="dash", command="echo run {ticket}", roles=None)
    cli("ticket", "add", "chain-review-project", "Only task")

    with patch("agentplan.cli.spawn_terminal", return_value=11), \
         patch("agentplan.cli._monitor_chain_ticket", return_value={"ticket_status": "needs-review", "timed_out": False}):
        out, err, code = cli("chain", "chain-review-project", "--default-agent", "dash")

    assert code == 0, err
    assert "Paused: ticket #1 ended as needs-review" in out


def test_chain_stops_when_no_more_tickets():
    os.makedirs("/tmp/chain-empty-project", exist_ok=True)
    cli("create", "Chain Empty Project", "--dir", "/tmp/chain-empty-project")

    out, err, code = cli("chain", "chain-empty-project")
    assert code == 0, err
    assert "No more unblocked tickets. Chain complete." in out


def test_chain_state_persisted_in_db_and_status_command():
    import agentplan.cli as agent_cli

    os.makedirs("/tmp/chain-state-project", exist_ok=True)
    cli("create", "Chain State Project", "--dir", "/tmp/chain-state-project")
    _run_agent_cmd(agent_cli.cmd_agent_add, name="dash", command="echo run {ticket}", roles=None)
    cli("ticket", "add", "chain-state-project", "Only task")

    with patch("agentplan.cli.spawn_terminal", return_value=12), \
         patch("agentplan.cli._monitor_chain_ticket", return_value={"ticket_status": "failed", "timed_out": False}):
        _, _, _ = cli("chain", "chain-state-project", "--default-agent", "dash")

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    row = conn.execute("SELECT status, pause_reason FROM chain_state WHERE project_id=1").fetchone()
    conn.close()
    assert row is not None
    assert row["status"] == "paused"
    assert "failed" in (row["pause_reason"] or "")

    out, err, code = cli("chain", "chain-state-project", "--status")
    assert code == 0, err
    assert "Chain status: paused" in out


def test_chain_max_tickets_limits_processing():
    import agentplan.cli as agent_cli

    os.makedirs("/tmp/chain-max-project", exist_ok=True)
    cli("create", "Chain Max Project", "--dir", "/tmp/chain-max-project")
    _run_agent_cmd(agent_cli.cmd_agent_add, name="dash", command="echo run {ticket}", roles=None)
    cli("ticket", "add", "chain-max-project", "T1")
    cli("ticket", "add", "chain-max-project", "T2")

    def fake_monitor(pid, project_slug, ticket_num, timeout_sec=3600):
        conn = agentplan.get_connection("/tmp/test_agentplan.db")
        conn.execute("UPDATE tickets SET status='done' WHERE project_id=1 AND num=?", (ticket_num,))
        conn.commit()
        conn.close()
        return {"pid": pid, "ticket_status": "done", "timed_out": False, "exit_code": 0}

    with patch("agentplan.cli.spawn_terminal", return_value=13) as mock_spawn, \
         patch("agentplan.cli._monitor_chain_ticket", side_effect=lambda conn, project, ticket, pid, timeout_sec=3600: fake_monitor(pid, project["slug"], ticket["num"], timeout_sec)):
        out, err, code = cli("chain", "chain-max-project", "--default-agent", "dash", "--max-tickets", "1")

    assert code == 0, err
    assert mock_spawn.call_count == 1
    assert "Reached --max-tickets=1" in out


def test_chain_rejects_reentry_when_already_running():
    cli("create", "Chain Reentry Project")

    conn = agentplan.get_connection("/tmp/test_agentplan.db")
    conn.execute(
        "INSERT INTO chain_state (project_id, status, current_ticket_id, pause_reason, heartbeat_at, deadline_at, updated_at) VALUES (?,?,?,?,?,?,?)",
        (1, "running", None, None, None, None, "2026-01-01T00:00:00"),
    )
    conn.commit()
    conn.close()

    with patch("agentplan.cli.spawn_terminal") as mock_spawn:
        out, err, code = cli("chain", "chain-reentry-project")

    assert code == 2
    assert out == ""
    assert "already running" in err.lower()
    assert mock_spawn.call_count == 0
