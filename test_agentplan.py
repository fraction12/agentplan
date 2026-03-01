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
    assert "## Agent Loop Demo (Terminal Recording Preview)" in content
    assert "<!-- TODO: insert terminal recording GIF here -->" in content
    assert "agent loop" in content.lower()


def test_changelog_exists_and_has_v020_header():
    changelog_path = Path(__file__).resolve().parent / "CHANGELOG.md"
    assert changelog_path.exists(), "CHANGELOG.md should exist at repository root."
    content = changelog_path.read_text(encoding="utf-8")
    assert "# Changelog" in content
    assert "## [Unreleased]" in content
    assert "## [0.2.0]" in content


def test_invalid_arguments_are_human_friendly():
    out, err, code = cli("ticket", "add")
    assert code == 2
    assert out == ""
    assert "Invalid arguments:" in err
    assert "Run `agentplan --help` to see available commands and options." in err
    assert "Traceback" not in err


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
    assert "Use at least one of: `--title`, `--desc`, `--priority`, `--tag`, `--due`." in err


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
    from dashboard import app

    cli("create", "Web Alpha")
    cli("create", "Web Beta")

    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Web Alpha" in body
    assert "Web Beta" in body


def test_dashboard_project_detail_returns_ticket_titles():
    from dashboard import app

    cli("create", "Web Detail")
    cli("ticket", "add", "web-detail", "Dashboard ticket one")
    cli("ticket", "add", "web-detail", "Dashboard ticket two")

    client = app.test_client()
    resp = client.get("/project/web-detail")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Dashboard ticket one" in body
    assert "Dashboard ticket two" in body



def test_dashboard_project_detail_links_to_ticket_detail_view():
    from dashboard import app

    cli("create", "Web Links")
    cli("ticket", "add", "web-links", "Clickable ticket")

    client = app.test_client()
    resp = client.get("/project/web-links")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert '/project/web-links/ticket/1' in body


def test_dashboard_ticket_detail_includes_dependencies_subtasks_history_and_close_note():
    from dashboard import app

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
