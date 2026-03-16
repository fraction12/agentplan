#!/usr/bin/env python3
"""agentplan — Project management CLI for AI agents."""

import argparse
import hashlib
import json
import logging
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta

from agentplan.db import (
    check_auto_complete,
    create_role as db_create_role,
    delete_role as db_delete_role,
    ensure as _ensure,
    ensure_space_directory,
    get_space_directory,
    get_connection,
    get_db_path,
    get_subtask_progress_map as _get_subtask_progress_map,
    init_db,
    list_project_slugs,
    get_unblocked as db_get_unblocked,
    list_roles as db_list_roles,
    next_subtask_num as _next_subtask_num,
    next_ticket_num as _next_ticket_num,
    now as _now,
    project_slug_suggestions,
    record_ticket_history as _record_ticket_history,
    resolve_project as db_resolve_project,
    resolve_subtask as db_resolve_subtask,
    resolve_ticket as db_resolve_ticket,
    unique_slug,
    validate_transition,
    update_role as db_update_role,
    create_agent as db_create_agent,
    get_agent as db_get_agent,

    list_agents as db_list_agents,
    delete_agent as db_delete_agent,
    update_agent as db_update_agent,
    get_role as db_get_role,
    route_ticket as db_route_ticket,
    get_chain_state as db_get_chain_state,
    set_chain_state as db_set_chain_state,
    is_valid_iso_local_timestamp,
)

__version__ = "0.9.0"

# ---------------------------------------------------------------------------
# Input validation limits
# ---------------------------------------------------------------------------
MAX_TITLE_LEN = 200
MAX_DESC_LEN = 4000
MAX_NOTES_LEN = 4000
MAX_AGENT_LEN = 100
MAX_LOG_ENTRY_LEN = 4000
MAX_TAG_LEN = 500
MAX_SLUG_LEN = 60  # already enforced via slugify
MAX_LABEL_LEN = 200
MAX_LOCATION_LEN = 2000


AUTO_DETECT_TOOL_COMMANDS = {
    "claude": "claude -p {ticket}",
    "codex": "codex exec {ticket}",
    "aider": "aider --message {ticket}",
    "cursor": "cursor --apply-changes {ticket}",
    "openclaw": "openclaw -s {ticket}",
}

TERMINAL_CHOICES = {"auto", "iterm2", "terminal"}
LOGGER = logging.getLogger(__name__)


def _detect_installed_tools():
    installed = []
    for tool in AUTO_DETECT_TOOL_COMMANDS:
        try:
            result = subprocess.run(
                ["which", tool],
                capture_output=True,
                text=True,
            )
        except OSError:
            continue
        if result.returncode == 0:
            installed.append(tool)
    return installed


def _create_default_agents(conn, tools):
    created = []
    for tool in tools:
        command_template = AUTO_DETECT_TOOL_COMMANDS.get(tool)
        if not command_template:
            continue
        if db_get_agent(conn, tool):
            continue
        db_create_agent(conn, tool, command_template)
        created.append(tool)
    return created


def _validate_len(value, max_len, field_name):
    """Raise CliError if value exceeds max_len."""
    if value and len(value) > max_len:
        fail(
            f"{field_name} is too long ({len(value)} chars; max {max_len}).",
            suggestions=[f"Keep {field_name.lower()} under {max_len} characters."],
        )


def _validate_model_tier(value):
    """Validate model_tier value."""
    if value and value not in MODEL_TIER_CHOICES:
        fail(
            f"Invalid model tier '{value}'.",
            suggestions=[f"Allowed values: {', '.join(MODEL_TIER_CHOICES)}."],
        )
    return value


def _validate_timeout_sec(timeout, flag_name="--timeout"):
    if timeout is None:
        return None
    if timeout <= 0:
        fail(f"{flag_name} must be a positive integer")
    return int(timeout)


def _effective_ticket_timeout_sec(project, ticket, override_timeout=None):
    if override_timeout is not None:
        return override_timeout
    ticket_timeout = ticket["timeout_sec"] if "timeout_sec" in ticket.keys() else None
    if ticket_timeout is not None:
        return int(ticket_timeout)
    project_timeout = project["timeout_sec"] if "timeout_sec" in project.keys() else None
    if project_timeout is not None:
        return int(project_timeout)
    return None


PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2, "none": 3}
PRIORITY_CHOICES = ["high", "medium", "low", "none"]
MODEL_TIER_CHOICES = ["auto", "light", "standard", "reasoning"]
COMPLETION_SHELLS = ["bash", "zsh", "fish"]
TOP_LEVEL_COMMANDS = [
    "init",
    "version",
    "create",
    "ticket",
    "next",
    "claim",
    "reap",
    "status",
    "search",
    "list",
    "archive",
    "attach",
    "log",
    "close",
    "note",
    "depend",
    "undepend",
    "remove",
    "history",
    "subtask",
    "space",
    "doc",
    "role",
    "hook",
    "agent",
    "completion",
    "context",
    "route",
    "spawn-terminal",
    "monitor-process",
    "auto-tag",
    "chain",
    "project",
    "issue",
    "pr",
    "artifact",
]
TICKET_COMMANDS = ["add", "update", "edit", "done", "skip", "start", "block", "fail", "review", "list"]
SUBTASK_COMMANDS = ["add", "done", "list"]
ROLE_COMMANDS = ["list", "add", "remove", "update"]
HOOK_COMMANDS = ["add", "list", "remove"]
AGENT_COMMANDS = ["add", "list", "remove", "update"]
ISSUE_COMMANDS = ["import"]
PR_COMMANDS = ["automate"]
ARTIFACT_COMMANDS = ["status", "verify"]
PROJECT_TOP_LEVEL_COMMANDS = {
    "status",
    "next",
    "claim",
    "reap",
    "archive",
    "attach",
    "log",
    "close",
    "note",
    "depend",
    "undepend",
    "remove",
    "history",
    "context",
    "route",
    "auto-tag",
    "chain",
    "project",
}

CHAIN_DEFAULT_MAX_TICKETS = 50
CHAIN_HARD_MAX_TICKETS = 500
CLAIM_LOCK_TTL_SEC = 20
CLAIM_LOCK_WAIT_SEC = 3


class CliError(Exception):
    """Expected CLI error with optional suggestions and exit code."""

    def __init__(self, message, suggestions=None, exit_code=2):
        super().__init__(message)
        self.message = message
        self.suggestions = suggestions or []
        self.exit_code = exit_code


def fail(message, suggestions=None, exit_code=2):
    """Raise a CliError with optional suggestions and exit code."""
    raise CliError(message, suggestions=suggestions, exit_code=exit_code)


# ---------------------------------------------------------------------------
# Slugify
# ---------------------------------------------------------------------------

def slugify(title):
    """Convert a title to a URL-safe slug (lowercase, alphanumeric + dashes, max 60 chars)."""
    s = title.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s]+", "-", s.strip())
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:60] or "project"



# ---------------------------------------------------------------------------
# Resolve helpers
# ---------------------------------------------------------------------------

def resolve_project(conn, ident):
    """Resolve a project by slug or ID, raising CliError if not found."""
    row = db_resolve_project(conn, ident)
    if not row:
        suggestions = []
        close_matches = project_slug_suggestions(conn, ident)
        if close_matches:
            suggestions.append(f"Did you mean '{close_matches[0]}'?")
        suggestions.append("Run `agentplan list --all` to see all projects.")
        fail(f"Project '{ident}' not found.", suggestions=suggestions)
    return row


def resolve_ticket(conn, project_id, num_str, slug=""):
    """Resolve a ticket by number within a project, raising CliError if not found or invalid."""
    try:
        int(num_str)
    except (ValueError, TypeError):
        fail(
            f"Invalid ticket number '{num_str}'.",
            suggestions=[
                "Ticket IDs must be numeric (for example: `1` or `2`).",
                f"Run `agentplan ticket list {slug or '<project>'}` to see ticket IDs.",
            ],
        )
    row = db_resolve_ticket(conn, project_id, num_str)
    if not row:
        fail(
            f"Ticket #{int(num_str)} not found in project '{slug}'.",
            suggestions=[f"Run `agentplan ticket list {slug}` to see available ticket IDs."],
        )
    return row


def resolve_subtask(conn, ticket_id, num_str, ticket_num, slug=""):
    """Resolve a subtask by number within a ticket, raising CliError if not found or invalid."""
    try:
        int(num_str)
    except (ValueError, TypeError):
        fail(
            f"Invalid subtask number '{num_str}'.",
            suggestions=[
                "Subtask IDs must be numeric (for example: `1`).",
                f"Run `agentplan subtask list {slug or '<project>'} {ticket_num}` to see subtask IDs.",
            ],
        )
    row = db_resolve_subtask(conn, ticket_id, num_str)
    if not row:
        fail(
            f"Subtask #{int(num_str)} not found for ticket #{ticket_num} in project '{slug}'.",
            suggestions=[f"Run `agentplan subtask list {slug} {ticket_num}` to see subtasks."],
        )
    return row


# ---------------------------------------------------------------------------
# Dependency helpers (all use ticket num, not internal id)
# ---------------------------------------------------------------------------

def has_cycle(tickets, ticket_num, new_deps):
    """Return True if setting ticket's deps to new_deps creates a cycle. Uses ticket nums."""
    adj = {}
    for t in tickets:
        adj[t["num"]] = json.loads(t["depends_on"] or "[]")
    adj[ticket_num] = list(new_deps)

    visited, stack = set(), set()

    def dfs(n):
        visited.add(n)
        stack.add(n)
        for d in adj.get(n, []):
            if d not in visited:
                if dfs(d):
                    return True
            elif d in stack:
                return True
        stack.discard(n)
        return False

    return dfs(ticket_num)


def get_unblocked(tickets):
    return db_get_unblocked(tickets)



# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _ticket_icon(status, blocked):
    if status == "done":
        return "✓"
    if status == "skipped":
        return "⊘"
    if status == "in-progress":
        return "▶"
    if status == "blocked":
        return "⛔"
    if status == "failed":
        return "✗"
    if status == "needs-review":
        return "👀"
    return "⏳" if blocked else "○"


def _is_blocked(ticket, done_nums):
    deps = json.loads(ticket["depends_on"] or "[]")
    return any(d not in done_nums for d in deps)


def _priority_value(priority):
    return PRIORITY_ORDER.get((priority or "none").lower(), PRIORITY_ORDER["none"])


def _priority_label(priority):
    return (priority or "none").lower()


def _parse_due_date(raw):
    if raw in (None, ""):
        return None
    value = raw.strip()
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        fail(
            "Invalid due date.",
            suggestions=["Use YYYY-MM-DD format (for example: `2026-03-01`)."],
        )
    return value


def _is_overdue(ticket, today=None):
    due = ticket["due_date"]
    if not due or ticket["status"] in ("done", "skipped"):
        return False
    if today is None:
        today = datetime.now().strftime("%Y-%m-%d")
    return due < today


def _sort_next_items(items):
    return sorted(
        items,
        key=lambda t: (
            0 if _is_overdue(t) else 1,
            _priority_value(t["priority"]),
            0 if t["status"] == "in-progress" else 1,
            t["num"],
        ),
    )


def _parse_tags(tags_arg):
    if not tags_arg:
        return ""
    tags = sorted({t.strip().lower() for t in tags_arg.split(",") if t.strip()})
    return ",".join(tags)


def _validate_role_tags_or_fail(conn, tags_csv):
    if not tags_csv:
        return
    tags = [t.strip().lower() for t in tags_csv.split(",") if t.strip()]
    for tag in tags:
        role_name = None
        if tag.startswith("role:"):
            role_name = tag.split(":", 1)[1].strip()
            if not role_name:
                fail(
                    "Invalid role tag 'role:'.",
                    suggestions=["Use a role tag in the form `role:<name>` (for example: `role:backend`)."],
                )
        elif db_get_role(conn, tag):
            role_name = tag

        if role_name and not db_get_role(conn, role_name):
            fail(
                f"Role '{role_name}' is not registered.",
                suggestions=[f"Add it first with: agentplan role add {role_name}"],
            )


def _ticket_has_tag(ticket, tag):
    if not tag:
        return True
    tags = ticket["tags"] or ""
    target = tag.strip().lower()
    return f",{target}," in f",{tags},"


def _subtask_progress_label(progress):
    if not progress or progress["total"] == 0:
        return ""
    return f"[{progress['done']}/{progress['total']}]"


def _completion_bash_script():
    return """# bash completion for agentplan
_agentplan_completion() {
    local cur args out
    cur="${COMP_WORDS[COMP_CWORD]}"
    args=("${COMP_WORDS[@]:1:$COMP_CWORD}")
    out="$(agentplan __complete bash "$cur" "${args[@]}" 2>/dev/null)"
    COMPREPLY=($(compgen -W "$out" -- "$cur"))
}
complete -F _agentplan_completion agentplan
"""


def _completion_zsh_script():
    return """#compdef agentplan
_agentplan_completion() {
    local cur out
    cur="${words[CURRENT]}"
    out="$(agentplan __complete zsh "$cur" "${words[@]:2:$((CURRENT-2))}" 2>/dev/null)"
    compadd -- ${(f)out}
}
compdef _agentplan_completion agentplan
"""


def _completion_fish_script():
    return """function __agentplan_completion
    set -l tokens (commandline -opc)
    set -e tokens[1]
    set -l current (commandline -ct)
    if test (count $tokens) -gt 0
        set -e tokens[-1]
    end
    agentplan __complete fish "$current" $tokens
end
complete -c agentplan -f -a "(__agentplan_completion)"
"""


def _completion_project_slugs():
    try:
        return list_project_slugs()
    except sqlite3.Error:
        return []


def _completion_filter(items, current):
    prefix = current or ""
    return [item for item in items if item.startswith(prefix)]


def _completion_suggestions(words, current):
    if not words:
        return _completion_filter(TOP_LEVEL_COMMANDS, current)

    command = words[0]
    if command == "completion":
        if len(words) == 1:
            return _completion_filter(COMPLETION_SHELLS, current)
        return []

    if command == "ticket":
        if len(words) == 1:
            return _completion_filter(TICKET_COMMANDS, current)
        if len(words) == 2 and words[1] in TICKET_COMMANDS:
            return _completion_filter(_completion_project_slugs(), current)
        return []

    if command == "subtask":
        if len(words) == 1:
            return _completion_filter(SUBTASK_COMMANDS, current)
        if len(words) == 2 and words[1] in SUBTASK_COMMANDS:
            return _completion_filter(_completion_project_slugs(), current)
        return []

    if command == "role":
        if len(words) == 1:
            return _completion_filter(ROLE_COMMANDS, current)
        return []

    if command == "hook":
        if len(words) == 1:
            return _completion_filter(HOOK_COMMANDS, current)
        if len(words) == 2 and words[1] in HOOK_COMMANDS:
            return _completion_filter(_completion_project_slugs(), current)
        return []

    if command == "agent":
        if len(words) == 1:
            return _completion_filter(AGENT_COMMANDS, current)
        return []

    if command == "issue":
        if len(words) == 1:
            return _completion_filter(ISSUE_COMMANDS, current)
        if len(words) == 2 and words[1] in ISSUE_COMMANDS:
            return _completion_filter(_completion_project_slugs(), current)
        return []

    if command == "pr":
        if len(words) == 1:
            return _completion_filter(PR_COMMANDS, current)
        if len(words) == 2 and words[1] in PR_COMMANDS:
            return _completion_filter(_completion_project_slugs(), current)
        return []

    if command == "artifact":
        if len(words) == 1:
            return _completion_filter(ARTIFACT_COMMANDS, current)
        if len(words) == 2 and words[1] in ARTIFACT_COMMANDS:
            return _completion_filter(_completion_project_slugs(), current)
        return []

    if command in PROJECT_TOP_LEVEL_COMMANDS and len(words) == 1:
        return _completion_filter(_completion_project_slugs(), current)

    return []


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def _extract_role_from_tags(tags):
    parts = [p.strip() for p in (tags or "").split(",") if p.strip()]
    for tag in parts:
        if tag.startswith("role:") and len(tag) > len("role:"):
            return tag.split(":", 1)[1]
    return None


def _infer_working_dir(project_notes):
    notes = project_notes or ""
    patterns = [
        r"(?im)^\s*(?:working[_ -]?dir|workdir|cwd)\s*[:=]\s*(.+?)\s*$",
        r"(?im)^\s*(?:path)\s*[:=]\s*(.+?)\s*$",
    ]
    for pattern in patterns:
        m = re.search(pattern, notes)
        if m:
            value = m.group(1).strip().strip("\"'")
            if value:
                return value
    return os.environ.get("AGENTPLAN_WORKDIR") or os.getcwd()


def _render_command_template(template, project_slug="", ticket_ref="", ticket_id="", project_dir=""):
    command = (template or "").strip()
    return (
        command.replace("{{ticket}}", str(ticket_ref))
        .replace("{{project}}", str(project_slug))
        .replace("{{ticket_id}}", str(ticket_id))
        .replace("{{project_dir}}", shlex.quote(str(project_dir)))
        .replace("{ticket}", str(ticket_ref))
        .replace("{project}", str(project_slug))
        .replace("{ticket_id}", str(ticket_id))
        .replace("{project_dir}", shlex.quote(str(project_dir)))
    )


def _warn_if_missing_project_dir(project):
    project_dir = (project.get("dir") if hasattr(project, "get") else project["dir"]) if project else None
    if project_dir and not os.path.isdir(project_dir):
        print(f"Warning: linked project directory does not exist: {project_dir}")


def _timestamp_after_seconds(seconds):
    return (datetime.now() + timedelta(seconds=int(seconds))).strftime("%Y-%m-%dT%H:%M:%S")


def _runtime_artifact_path(project, artifact_type):
    project_dir = (project.get("dir") if hasattr(project, "get") else project["dir"]) if project else None
    if not project_dir:
        return None
    artifact_dir = os.path.join(project_dir, ".agentplan", "artifacts")
    os.makedirs(artifact_dir, exist_ok=True)
    return os.path.join(artifact_dir, f"{artifact_type}.json")


def _persist_runtime_artifact(conn, project, artifact_type, payload):
    artifact_path = _runtime_artifact_path(project, artifact_type)
    if not artifact_path:
        return None
    payload_with_meta = dict(payload or {})
    payload_with_meta["recorded_at"] = _now()
    encoded = json.dumps(payload_with_meta, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    tmp_path = f"{artifact_path}.tmp.{uuid.uuid4().hex}"
    with open(tmp_path, "wb") as f:
        f.write(encoded)
    os.replace(tmp_path, artifact_path)
    conn.execute(
        """
        INSERT INTO runtime_artifacts (project_id, artifact_type, path, sha256, recorded_at)
        VALUES (?,?,?,?,?)
        ON CONFLICT(project_id, artifact_type) DO UPDATE SET
          path=excluded.path,
          sha256=excluded.sha256,
          recorded_at=excluded.recorded_at
        """,
        (project["id"], artifact_type, artifact_path, digest, _now()),
    )
    conn.commit()
    return {"path": artifact_path, "sha256": digest}


def _load_runtime_artifact(conn, project, artifact_type):
    row = conn.execute(
        """
        SELECT * FROM runtime_artifacts
        WHERE project_id=? AND artifact_type=?
        """,
        (project["id"], artifact_type),
    ).fetchone()
    if not row:
        return None
    path = row["path"]
    if not path or not os.path.isfile(path):
        return {"ok": False, "error": f"artifact file missing: {path}"}
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as exc:
        return {"ok": False, "error": f"failed reading artifact: {exc}"}
    digest = hashlib.sha256(raw).hexdigest()
    if digest != row["sha256"]:
        return {"ok": False, "error": "sha256 mismatch", "expected": row["sha256"], "actual": digest}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return {"ok": False, "error": f"invalid artifact json: {exc}"}
    return {"ok": True, "path": path, "sha256": digest, "payload": payload}


def _set_chain_state_with_artifact(
    conn,
    project,
    status,
    current_ticket_id=None,
    pause_reason=None,
    heartbeat_at=None,
    deadline_at=None,
    stop_reason=None,
):
    db_set_chain_state(
        conn,
        project["id"],
        status,
        current_ticket_id=current_ticket_id,
        pause_reason=pause_reason,
        heartbeat_at=heartbeat_at,
        deadline_at=deadline_at,
    )
    payload = {
        "project_id": project["id"],
        "project_slug": project["slug"],
        "status": status,
        "current_ticket_id": current_ticket_id,
        "pause_reason": pause_reason,
        "heartbeat_at": heartbeat_at,
        "deadline_at": deadline_at,
        "stop_reason": stop_reason,
    }
    try:
        _persist_runtime_artifact(conn, project, "chain-state", payload)
    except OSError as exc:
        print(f"Warning: failed writing runtime artifact: {exc}", file=sys.stderr)


def _acquire_claim_lock(conn, project_id, owner, ttl_sec=CLAIM_LOCK_TTL_SEC, wait_sec=CLAIM_LOCK_WAIT_SEC):
    deadline = time.monotonic() + max(float(wait_sec), 0.0)
    while True:
        now_ts = _now()
        expires_ts = _timestamp_after_seconds(ttl_sec)
        updated = conn.execute(
            """
            INSERT INTO claim_locks (project_id, lock_owner, lock_acquired_at, lock_expires_at)
            VALUES (?,?,?,?)
            ON CONFLICT(project_id) DO UPDATE SET
              lock_owner=excluded.lock_owner,
              lock_acquired_at=excluded.lock_acquired_at,
              lock_expires_at=excluded.lock_expires_at
            WHERE claim_locks.lock_expires_at <= excluded.lock_acquired_at
               OR claim_locks.lock_owner = excluded.lock_owner
            """,
            (project_id, owner, now_ts, expires_ts),
        ).rowcount
        if updated == 1:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


def _release_claim_lock(conn, project_id, owner):
    conn.execute("DELETE FROM claim_locks WHERE project_id=? AND lock_owner=?", (project_id, owner))


def _http_json_get(url, token):
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "agentplan/issue-import")
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_github_issues(repo, label, state, token):
    issues = []
    for page in range(1, 11):
        query = urllib.parse.urlencode(
            {
                "state": state,
                "per_page": 100,
                "page": page,
                "labels": label,
            }
        )
        url = f"https://api.github.com/repos/{repo}/issues?{query}"
        batch = _http_json_get(url, token)
        if not isinstance(batch, list):
            fail("GitHub API returned an unexpected issues payload.")
        if not batch:
            break
        for item in batch:
            if item.get("pull_request"):
                continue
            issues.append(item)
        if len(batch) < 100:
            break
    return issues


def _slugify_branch_part(value, fallback):
    part = slugify(value or "")
    return part or fallback


def _run_cmd(argv, cwd=None, capture_output=True):
    return subprocess.run(
        argv,
        cwd=cwd,
        capture_output=capture_output,
        text=True,
    )


def _iterm2_running():
    try:
        result = subprocess.run(["pgrep", "-x", "iTerm2"], capture_output=True, text=True)
    except OSError:
        return False
    return result.returncode == 0


def _iterm2_installed():
    if os.path.exists("/Applications/iTerm.app"):
        return True
    try:
        result = subprocess.run(
            ["mdfind", "kMDItemCFBundleIdentifier == 'com.googlecode.iterm2'"],
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return result.returncode == 0 and bool((result.stdout or "").strip())


def _terminal_preference(explicit=None):
    pref = (explicit or os.environ.get("AGENTPLAN_TERMINAL", "auto") or "auto").strip().lower()
    return pref if pref in TERMINAL_CHOICES else "auto"


def _is_ci_mode():
    raw = (os.environ.get("AGENTPLAN_CI") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _spawn_headless_subprocess(command, cwd=None):
    return subprocess.Popen(
        command,
        shell=True,
        executable="/bin/bash",
        cwd=cwd,
        stdout=None,
        stderr=None,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


def detect_terminal_app(preference=None):
    """Detect available terminal app (iTerm2 or Terminal) based on preference and availability."""
    pref = _terminal_preference(preference)
    if pref == "terminal":
        return "terminal"
    if pref == "iterm2":
        return "iterm2" if (_iterm2_running() or _iterm2_installed()) else "terminal"
    if _iterm2_running() or _iterm2_installed():
        return "iterm2"
    return "terminal"


def _escape_applescript_string(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _build_terminal_command(command, title=None):
    wrapped = f"bash -lc {shlex.quote(command)}"
    if title:
        title_cmd = f"printf '\\033]1;%s\\007' {shlex.quote(title)}"
        return f"{title_cmd}; {wrapped}"
    return wrapped


def _run_osascript(script):
    return subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=10,
    )


def spawn_terminal(command: str, title: str = None) -> int:
    """Spawn a new terminal window running the given command. Returns 0 on success, 1 on failure."""
    terminal = detect_terminal_app()
    cmd = _build_terminal_command(command, title=title)
    escaped = _escape_applescript_string(cmd)

    if terminal == "iterm2":
        script = (
            'tell application "iTerm2"\n'
            '    create window with default profile\n'
            '    tell current session of current window\n'
            f'        write text "{escaped}"\n'
            '    end tell\n'
            'end tell'
        )
        try:
            result = _run_osascript(script)
            if result.returncode == 0:
                return 0
            LOGGER.warning("iTerm2 osascript failed: %s", (result.stderr or "").strip())
        except Exception as exc:
            LOGGER.warning("iTerm2 osascript failed: %s", exc)
        terminal = "terminal"

    script = (
        'tell application "Terminal"\n'
        '    activate\n'
        f'    do script "{escaped}"\n'
        'end tell'
    )
    try:
        result = _run_osascript(script)
        if result.returncode == 0:
            return 0
        LOGGER.warning("Terminal osascript failed: %s", (result.stderr or "").strip())
    except Exception as exc:
        LOGGER.warning("Terminal osascript failed: %s", exc)
    return 1


def _get_ticket_status(project_slug, ticket_num):
    conn = _ensure(get_connection())
    try:
        proj = resolve_project(conn, project_slug)
        ticket = resolve_ticket(conn, proj["id"], ticket_num, proj["slug"])
        return ticket["status"], ticket["id"]
    finally:
        conn.close()


def _record_monitor_history(project_slug, ticket_num, old_state, message):
    try:
        conn = _ensure(get_connection())
        try:
            proj = resolve_project(conn, project_slug)
            ticket = resolve_ticket(conn, proj["id"], ticket_num, proj["slug"])
            _record_ticket_history(conn, ticket["id"], old_state, message)
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        LOGGER.warning("Failed to record monitor history for %s#%s: %s", project_slug, ticket_num, exc)


def _get_exit_code_for_pid(pid):
    try:
        result = subprocess.run(
            ["ps", "-o", "exit_code=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as exc:
        LOGGER.warning("Failed to query exit code for pid %s: %s", pid, exc)
        return None

    if result.returncode != 0:
        return None

    output = (result.stdout or "").strip()
    if not output:
        return None
    first_line = output.splitlines()[0].strip()
    try:
        return int(first_line)
    except ValueError:
        return None


def _is_zombie_process(pid):
    status_path = f"/proc/{pid}/status"
    if not os.path.exists(status_path):
        return False
    try:
        with open(status_path, "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("State:"):
                    parts = line.split()
                    return len(parts) >= 2 and parts[1].upper().startswith("Z")
    except Exception as exc:
        LOGGER.warning("Failed to inspect /proc status for pid %s: %s", pid, exc)
    return False


def _pid_is_alive(pid):
    if pid <= 0:
        return True

    try:
        waited_pid, _ = os.waitpid(pid, os.WNOHANG)
        if waited_pid == pid:
            return False
    except ChildProcessError:
        # Not our child process; fall back to non-blocking OS-level checks.
        pass
    except Exception as exc:
        LOGGER.warning("Unexpected waitpid error for pid %s: %s", pid, exc)

    if _is_zombie_process(pid):
        return False

    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except Exception as exc:
        LOGGER.warning("Unexpected os.kill error for pid %s: %s", pid, exc)
        return True


def monitor_process(pid: int, project_slug: str, ticket_num: int, timeout_sec: int = 3600) -> dict:
    """Monitor a running process and track its status against a ticket, returning result dict with exit code and ticket status."""
    start = time.monotonic()
    last_heartbeat = start
    poll_interval = 5
    heartbeat_interval = 60
    terminal_states = {"done", "failed", "needs-review"}

    ticket_status = "unknown"
    timed_out = False
    exit_code = None

    while True:
        now_mono = time.monotonic()
        elapsed = now_mono - start
        if elapsed >= timeout_sec:
            timed_out = True
            break

        try:
            current_status, _ = _get_ticket_status(project_slug, ticket_num)
            ticket_status = current_status
            if current_status in terminal_states:
                return {
                    "pid": pid,
                    "exit_code": None,
                    "ticket_status": current_status,
                    "timed_out": False,
                }
        except Exception as exc:
            LOGGER.warning("Failed reading ticket status for %s#%s: %s", project_slug, ticket_num, exc)

        if now_mono - last_heartbeat >= heartbeat_interval:
            _record_monitor_history(
                project_slug,
                ticket_num,
                ticket_status,
                f"monitor-heartbeat: pid={pid} elapsed={int(elapsed)}s",
            )
            last_heartbeat = now_mono

        alive = _pid_is_alive(pid)

        if not alive:
            exit_code = _get_exit_code_for_pid(pid)
            try:
                current_status, _ = _get_ticket_status(project_slug, ticket_num)
                ticket_status = current_status
            except Exception:
                pass
            break

        time.sleep(poll_interval)

    return {
        "pid": pid,
        "exit_code": exit_code,
        "ticket_status": ticket_status,
        "timed_out": timed_out,
    }


def cmd_monitor_process(args):
    """Monitor a running process and track its status against a ticket."""
    if not isinstance(args.pid, int) or args.pid <= 0:
        fail("--pid must be a positive integer")
    timeout = getattr(args, "timeout", None)
    if timeout is not None and timeout <= 0:
        fail("--timeout must be a positive integer")
    result = monitor_process(args.pid, args.project, args.ticket_id, timeout_sec=args.timeout)
    print(json.dumps(result))




def _next_chain_candidate(conn, project_id):
    tickets = conn.execute(
        "SELECT * FROM tickets WHERE project_id=? ORDER BY num", (project_id,)
    ).fetchall()
    items = [t for t in tickets if t["status"] == "in-progress"] + get_unblocked(tickets)
    items = _sort_next_items(items)
    return items[0] if items else None


def _render_agent_command(template, ticket, project, project_dir=None):
    try:
        project_slug = project["slug"]
    except (KeyError, TypeError):
        project_slug = str(project)

    try:
        ticket_num = ticket["num"]
    except (KeyError, TypeError, ValueError):
        ticket_num = int(ticket)

    if project_dir is None:
        try:
            project_dir = project.get("dir") if hasattr(project, "get") else project["dir"]
        except (KeyError, AttributeError, TypeError):
            project_dir = None

    ticket_ref = f"{project_slug} {ticket_num}"
    rendered = _render_command_template(
        template,
        project_slug=project_slug,
        ticket_ref=ticket_ref,
        ticket_id=ticket_num,
        project_dir=project_dir or "",
    )
    return rendered


def _mark_ticket_failed_for_timeout(conn, project, ticket, timeout_sec):
    reason = f"timeout: no progress for {timeout_sec}s"
    conn.execute(
        "UPDATE tickets SET status='failed', close_note=?, completed_at=NULL, claimed_at=NULL WHERE id=?",
        (reason, ticket["id"]),
    )
    _record_ticket_history(conn, ticket["id"], ticket["status"], "failed")
    conn.execute(
        "INSERT INTO log (project_id, ticket_id, entry) VALUES (?,?,?)",
        (project["id"], ticket["id"], reason),
    )
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), project["id"]))
    conn.commit()
    return reason


def _parse_local_timestamp(ts):
    if not ts:
        return None
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None


def _latest_ticket_heartbeat(conn, project_id, ticket_id):
    row = conn.execute(
        "SELECT created_at FROM log WHERE project_id=? AND ticket_id=? ORDER BY id DESC LIMIT 1",
        (project_id, ticket_id),
    ).fetchone()
    return _parse_local_timestamp(row["created_at"]) if row else None


def _monitor_chain_ticket(conn, project, ticket, pid, timeout_sec):
    poll_interval = 5
    timeout_sec = int(timeout_sec)
    now_dt = datetime.now()
    deadline_dt = now_dt + timedelta(seconds=timeout_sec)

    _set_chain_state_with_artifact(
        conn,
        project,
        "running",
        current_ticket_id=ticket["id"],
        pause_reason=None,
        heartbeat_at=now_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        deadline_at=deadline_dt.strftime("%Y-%m-%dT%H:%M:%S"),
    )

    while True:
        refreshed = conn.execute("SELECT * FROM tickets WHERE id=?", (ticket["id"],)).fetchone()
        if refreshed and refreshed["status"] in {"done", "failed", "needs-review", "blocked"}:
            return {
                "ticket_status": refreshed["status"],
                "timed_out": False,
            }

        latest_hb = _latest_ticket_heartbeat(conn, project["id"], ticket["id"])
        if latest_hb and latest_hb > now_dt:
            now_dt = latest_hb
            deadline_dt = now_dt + timedelta(seconds=timeout_sec)
            _set_chain_state_with_artifact(
                conn,
                project,
                "running",
                current_ticket_id=ticket["id"],
                pause_reason=None,
                heartbeat_at=now_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                deadline_at=deadline_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            )

        current_time = datetime.now()
        if current_time > deadline_dt:
            return {
                "ticket_status": refreshed["status"] if refreshed else "unknown",
                "timed_out": True,
            }

        alive = _pid_is_alive(pid) if pid > 0 else True

        if not alive:
            refreshed = conn.execute("SELECT * FROM tickets WHERE id=?", (ticket["id"],)).fetchone()
            return {
                "ticket_status": refreshed["status"] if refreshed else "unknown",
                "timed_out": False,
            }

        time.sleep(poll_interval)


def cmd_chain(args):
    """Execute a chain of tickets in sequence via configured agents."""
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    chain_timeout_override = _validate_timeout_sec(getattr(args, "timeout", None))
    run_started_at = time.monotonic()
    max_tickets = args.max_tickets
    if max_tickets is None:
        env_cap = (os.environ.get("AGENTPLAN_MAX_TICKETS_PER_RUN") or "").strip()
        if env_cap:
            try:
                max_tickets = int(env_cap)
            except ValueError:
                conn.close()
                fail("AGENTPLAN_MAX_TICKETS_PER_RUN must be an integer.")
        else:
            max_tickets = CHAIN_DEFAULT_MAX_TICKETS
    if max_tickets <= 0:
        conn.close()
        fail("--max-tickets must be a positive integer.")
    if max_tickets > CHAIN_HARD_MAX_TICKETS:
        conn.close()
        fail(
            f"--max-tickets exceeds hard cap ({CHAIN_HARD_MAX_TICKETS}).",
            suggestions=[f"Use a value between 1 and {CHAIN_HARD_MAX_TICKETS}."],
        )
    max_runtime_sec = getattr(args, "max_runtime", None)
    if max_runtime_sec is not None and max_runtime_sec <= 0:
        conn.close()
        fail("--max-runtime must be a positive integer.")
    max_budget_usd = getattr(args, "max_budget", None)
    if max_budget_usd is not None and max_budget_usd <= 0:
        conn.close()
        fail("--max-budget-usd must be a positive number.")
    cost_per_ticket_usd = getattr(args, "cost_per_ticket", 0.0)
    if cost_per_ticket_usd is None:
        cost_per_ticket_usd = 0.0
    if cost_per_ticket_usd < 0:
        conn.close()
        fail("--cost-per-ticket-usd cannot be negative.")

    if getattr(args, "status", False):
        state = db_get_chain_state(conn, proj["id"])
        if not state:
            print("Chain status: idle")
        else:
            current = "none"
            if state.get("current_ticket_id"):
                row = conn.execute("SELECT num FROM tickets WHERE id=?", (state["current_ticket_id"],)).fetchone()
                if row:
                    current = f"#{row['num']}"
            print(f"Chain status: {state['status']}")
            print(f"Current ticket: {current}")
            print(f"Pause reason: {state.get('pause_reason') or '(none)'}")
            print(f"Heartbeat: {state.get('heartbeat_at') or '(none)'}")
            print(f"Deadline: {state.get('deadline_at') or '(none)'}")
        conn.close()
        return

    if getattr(args, "stop", False):
        state = db_get_chain_state(conn, proj["id"])
        if state and state.get("status") == "running":
            _set_chain_state_with_artifact(
                conn,
                proj,
                "stopped",
                current_ticket_id=state.get("current_ticket_id"),
                pause_reason="stop requested",
                stop_reason="stop requested",
            )
            print("Chain stop requested. Will stop after current ticket.")
        else:
            _set_chain_state_with_artifact(
                conn,
                proj,
                "stopped",
                pause_reason="stop requested",
                stop_reason="stop requested",
            )
            print("Chain marked stopped.")
        conn.close()
        return

    state = db_get_chain_state(conn, proj["id"]) or {}
    if (state.get("status") or "").lower() == "running":
        conn.close()
        fail(
            f"Chain already running for project '{proj['slug']}'.",
            suggestions=[f"Run `agentplan chain {proj['slug']} --status` to inspect the current run."],
        )

    project_dir = (proj["dir"] if "dir" in proj.keys() else None) or ""
    if not project_dir.strip():
        conn.close()
        fail(
            f"No directory linked to project '{proj['slug']}'. Set one with: agentplan project {proj['slug']} --dir ~/path/to/repo"
        )

    processed = 0
    _warn_if_missing_project_dir(proj)
    _set_chain_state_with_artifact(conn, proj, "running", current_ticket_id=None, pause_reason=None)
    print(f"Starting chain for project '{proj['slug']}'")

    while True:
        if processed >= max_tickets:
            reason = f"max tickets reached ({processed}/{max_tickets})"
            print(f"Stopped: {reason}.")
            _set_chain_state_with_artifact(
                conn,
                proj,
                "stopped",
                current_ticket_id=None,
                pause_reason=reason,
                stop_reason=reason,
            )
            break

        state = db_get_chain_state(conn, proj["id"])
        if state and state.get("status") == "stopped" and processed > 0:
            print("Chain stop acknowledged.")
            _set_chain_state_with_artifact(
                conn,
                proj,
                "stopped",
                current_ticket_id=None,
                pause_reason="stop requested",
                stop_reason="stop requested",
            )
            break

        elapsed_sec = int(time.monotonic() - run_started_at)
        if max_runtime_sec is not None and elapsed_sec >= max_runtime_sec:
            reason = f"max runtime reached ({elapsed_sec}s/{max_runtime_sec}s)"
            print(f"Stopped: {reason}.")
            _set_chain_state_with_artifact(
                conn,
                proj,
                "stopped",
                current_ticket_id=None,
                pause_reason=reason,
                stop_reason=reason,
            )
            break

        if max_budget_usd is not None:
            projected = (processed + 1) * float(cost_per_ticket_usd)
            if projected > float(max_budget_usd):
                reason = (
                    f"budget cap reached (projected ${projected:.2f} > max ${float(max_budget_usd):.2f})"
                )
                print(f"Stopped: {reason}.")
                _set_chain_state_with_artifact(
                    conn,
                    proj,
                    "stopped",
                    current_ticket_id=None,
                    pause_reason=reason,
                    stop_reason=reason,
                )
                break

        ticket = _next_chain_candidate(conn, proj["id"])
        if not ticket:
            print("No more unblocked tickets. Chain complete.")
            _set_chain_state_with_artifact(conn, proj, "done", current_ticket_id=None, pause_reason=None)
            break

        agent = db_route_ticket(conn, ticket, default_agent_name=args.default_agent)
        if not agent:
            reason = f"no routeable agent for ticket #{ticket['num']}"
            _set_chain_state_with_artifact(conn, proj, "paused", current_ticket_id=ticket["id"], pause_reason=reason)
            conn.close()
            fail(
                f"No routeable agent for ticket #{ticket['num']} in project '{proj['slug']}'.",
                suggestions=[
                    f"Set a fallback agent for chain runs: `agentplan chain {proj['slug']} --default-agent <agent-name>`.",
                    f"Tag ticket #{ticket['num']} with a role mapped to an agent (for example: `agentplan ticket edit {proj['slug']} {ticket['num']} --tag role:backend`).",
                    "Inspect routing config with: `agentplan role list` and `agentplan agent list`.",
                ],
            )

        timeout_sec = _effective_ticket_timeout_sec(proj, ticket, override_timeout=chain_timeout_override)
        if timeout_sec is None:
            timeout_sec = 3600

        command = _render_agent_command(
            agent.get("command_template"),
            ticket,
            proj,
            project_dir=project_dir,
        )
        deadline_preview = (datetime.now() + timedelta(seconds=timeout_sec)).strftime("%Y-%m-%dT%H:%M:%S")
        start_msg = f"chain-start: ticket #{ticket['num']} timeout={timeout_sec}s deadline={deadline_preview}"
        conn.execute(
            "INSERT INTO log (project_id, ticket_id, entry) VALUES (?,?,?)",
            (proj["id"], ticket["id"], start_msg),
        )
        conn.commit()

        print(f"→ Ticket #{ticket['num']} via agent '{agent['name']}' (timeout {timeout_sec}s)")
        if _is_ci_mode():
            try:
                proc = _spawn_headless_subprocess(command, cwd=project_dir)
            except OSError as exc:
                reason = f"failed to start headless agent command: {exc}"
                print(f"Paused: {reason}")
                _set_chain_state_with_artifact(conn, proj, "paused", current_ticket_id=ticket["id"], pause_reason=reason)
                break
            pid = proc.pid
            print(f"Started headless agent command (pid={pid})")
        else:
            pid = spawn_terminal(command, title=f"agentplan:{agent['name']}")

        result = _monitor_chain_ticket(conn, proj, ticket, pid, timeout_sec=timeout_sec)
        refreshed = conn.execute("SELECT * FROM tickets WHERE id=?", (ticket["id"],)).fetchone()
        status = result.get("ticket_status") or (refreshed["status"] if refreshed else "unknown")

        if result.get("timed_out"):
            reason = _mark_ticket_failed_for_timeout(conn, proj, refreshed or ticket, timeout_sec)
            print(f"Paused: ticket #{ticket['num']} timed out ({timeout_sec}s)")
            _set_chain_state_with_artifact(conn, proj, "paused", current_ticket_id=ticket["id"], pause_reason=reason)
            break

        if status == "done":
            processed += 1
            print(f"✓ Ticket #{ticket['num']} done; continuing")
            _set_chain_state_with_artifact(conn, proj, "running", current_ticket_id=None, pause_reason=None)
            continue

        if status in {"blocked", "failed", "needs-review"}:
            reason = f"ticket #{ticket['num']} ended as {status}"
            print(f"Paused: {reason}")
            _set_chain_state_with_artifact(conn, proj, "paused", current_ticket_id=ticket["id"], pause_reason=reason)
            break

        reason = f"ticket #{ticket['num']} ended with status {status}"
        print(f"Paused: {reason}")
        _set_chain_state_with_artifact(conn, proj, "paused", current_ticket_id=ticket["id"], pause_reason=reason)
        break

    conn.close()

def cmd_context(args):
    """Display ticket context and commands for agent execution."""
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)

    if args.ticket_id:
        ticket = resolve_ticket(conn, proj["id"], args.ticket_id, proj["slug"])

        role = _extract_role_from_tags(ticket["tags"]) or "unassigned"
        deps = json.loads(ticket["depends_on"] or "[]")

        dep_lines = []
        for dep_num in deps:
            dep_ticket = db_resolve_ticket(conn, proj["id"], dep_num)
            if dep_ticket:
                dep_lines.append(f"  #{dep_ticket['num']}: {dep_ticket['title']} [{dep_ticket['status']}]")
            else:
                dep_lines.append(f"  #{dep_num}: (missing ticket) [unknown]")
        if not dep_lines:
            dep_lines = ["  (none)"]

        agent_name = args.agent or "<name>"
        workdir = _infer_working_dir(proj["notes"])
        _, db_path = get_db_path()
        claim_timeout = (
            f"{ticket['claim_timeout']} seconds"
            if ticket["claim_timeout"] is not None
            else "not set"
        )

        lines = [
            "=== AGENTPLAN CONTEXT BLOCK ===",
            f"Project: {proj['slug']} ({proj['title']}) [{proj['status']}]",
            f"Ticket: #{ticket['num']} — {ticket['title']}",
            f"Priority: {_priority_label(ticket['priority'])}",
            f"Status: {ticket['status']}",
            f"Role: {role}",
            f"Tags: {ticket['tags'] or '(none)'}",
            f"Description: {ticket['description'] or '(none)'}",
            "",
            "Dependencies:",
            *dep_lines,
            "",
            "Commands:",
            f"  agentplan ticket start {proj['slug']} {ticket['num']} --agent {agent_name}",
            f"  agentplan ticket done {proj['slug']} {ticket['num']} --agent {agent_name}",
            f"  agentplan ticket block {proj['slug']} {ticket['num']} --reason \"...\"",
            f"  agentplan ticket fail {proj['slug']} {ticket['num']} --reason \"...\"",
            f"  agentplan log {proj['slug']} {ticket['num']} \"message\"",
            "",
            f"Working dir: {workdir}",
            f"DB: {db_path}",
            f"Claim timeout: {claim_timeout}",
            "==============================",
        ]
        print("\n".join(lines))
        conn.close()
        return

    print("Project context generation has been removed. Use `agentplan status {0}` for project overview.".format(proj["slug"]))
    conn.close()


def cmd_route(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    ticket = resolve_ticket(conn, proj["id"], args.ticket_id, proj["slug"])
    agent = db_route_ticket(conn, ticket, default_agent_name=args.default_agent)
    conn.close()

    if not agent:
        fail(
            f"No routeable agent for ticket #{ticket['num']} in project '{proj['slug']}'.",
            suggestions=[
                f"Retry with a fallback: `agentplan route {proj['slug']} {ticket['num']} --default-agent <agent-name>`.",
                f"Assign a role tag that matches a registered agent (for example: `agentplan ticket edit {proj['slug']} {ticket['num']} --tag role:backend`).",
                "Inspect routing config with: `agentplan role list` and `agentplan agent list`.",
            ],
        )

    print(agent["name"])
    if getattr(args, "terminal_pref", None):
        os.environ["AGENTPLAN_TERMINAL"] = args.terminal_pref
    if getattr(args, "terminal", False):
        command = _render_agent_command(
            agent.get("command_template"),
            ticket,
            proj,
            project_dir=proj["dir"] if "dir" in proj.keys() else None,
        )
        pid = spawn_terminal(command, title=f"agentplan:{agent['name']}")
        if getattr(args, "monitor", False):
            def _monitor_runner():
                result = monitor_process(pid, proj["slug"], ticket["num"], timeout_sec=3600)
                _record_monitor_history(
                    proj["slug"],
                    ticket["num"],
                    result.get("ticket_status", "unknown"),
                    f"monitor-result: {json.dumps(result, sort_keys=True)}",
                )

            thread = threading.Thread(target=_monitor_runner, daemon=True)
            thread.start()


def cmd_spawn_terminal(args):
    if getattr(args, "terminal_pref", None):
        os.environ["AGENTPLAN_TERMINAL"] = args.terminal_pref
    spawn_terminal(args.command, title=getattr(args, "title", None))


def _ticket_has_role_tag(ticket):
    tags = (ticket["tags"] or "").split(",")
    for tag in tags:
        val = tag.strip().lower()
        if val.startswith("role:") and len(val) > len("role:"):
            return True
    return False


def _choose_autotag_agent(conn, requested_name=None):
    if requested_name:
        agent = db_get_agent(conn, requested_name)
        if not agent:
            fail(f"Agent '{requested_name}' not found.")
        if not (agent.get("command_template") or "").strip():
            fail(f"Agent '{requested_name}' has no command template configured.")
        return agent

    for agent in db_list_agents(conn):
        if (agent.get("command_template") or "").strip():
            return agent
    return None


def _invoke_autotag_ai(command_template, prompt, ticket_text):
    if command_template:
        rendered = command_template.replace("{ticket}", ticket_text).replace("{prompt}", prompt)
        argv = shlex.split(rendered)
    else:
        argv = ["claude", "-p", prompt]

    result = subprocess.run(argv, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"command failed: {' '.join(argv)}")

    return (result.stdout or "").strip()


def _normalize_role_prediction(raw):
    text = (raw or "").strip()
    if not text:
        return ""
    first = text.splitlines()[0].strip()
    first = first.strip("`'\" ")
    first = re.sub(r"[^a-zA-Z0-9_-]", "", first)
    return first.lower()


def cmd_auto_tag(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    roles = [r.name.lower() for r in db_list_roles(conn)]
    if not roles:
        conn.close()
        fail("No roles configured.", suggestions=["Add roles first with: agentplan role add <name>"])

    selected_agent = _choose_autotag_agent(conn, requested_name=getattr(args, "agent", None))
    command_template = selected_agent["command_template"] if selected_agent else None
    agent_label = selected_agent["name"] if selected_agent else "claude"

    if not command_template and not shutil.which("claude"):
        conn.close()
        fail(
            "No configured agent command_template found and fallback 'claude' is unavailable.",
            suggestions=["Add an agent: agentplan agent add <name> --command '<cmd>'"],
        )

    tickets = conn.execute(
        "SELECT * FROM tickets WHERE project_id=? ORDER BY num",
        (proj["id"],),
    ).fetchall()
    if args.ticket is not None:
        tickets = [t for t in tickets if t["num"] == args.ticket]
        if not tickets:
            conn.close()
            fail(
                f"Ticket #{args.ticket} not found in project '{proj['slug']}'.",
                suggestions=[f"Run `agentplan ticket list {proj['slug']}` to see available ticket IDs."],
            )

    processed = 0
    changed = 0
    for t in tickets:
        if _ticket_has_role_tag(t):
            print(f"Skipping ticket #{t['num']}: already has role tag")
            continue

        processed += 1
        prompt = (
            f"Given these roles: {', '.join(roles)}, classify the following ticket title+description into one role. "
            f"Reply with just the role name. Ticket: {t['title']}. {t['description'] or ''}"
        )
        ticket_text = f"{t['title']}. {t['description'] or ''}".strip()

        try:
            raw = _invoke_autotag_ai(command_template, prompt, ticket_text)
        except Exception as e:
            print(f"Warning: ticket #{t['num']} auto-tag failed via {agent_label}: {e}", file=sys.stderr)
            continue

        predicted = _normalize_role_prediction(raw)
        role = db_get_role(conn, predicted)
        if not role:
            print(
                f"Warning: ticket #{t['num']} returned unknown role '{predicted or raw}'. Skipping.",
                file=sys.stderr,
            )
            continue

        new_tag = f"role:{role.name}"
        existing_tags = [x.strip() for x in (t["tags"] or "").split(",") if x.strip()]
        updated_tags = ",".join(existing_tags + [new_tag]) if existing_tags else new_tag

        if args.dry_run:
            print(f"[dry-run] ticket #{t['num']} -> {new_tag}")
        else:
            conn.execute("UPDATE tickets SET tags=? WHERE id=?", (updated_tags, t["id"]))
            _record_ticket_history(conn, t["id"], t["status"], f"auto-tag:{role.name}")
            print(f"Tagged ticket #{t['num']} -> {new_tag}")
            changed += 1

    if not args.dry_run and changed:
        conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
        conn.commit()
    elif args.dry_run:
        conn.rollback()

    if processed == 0:
        print("No untagged tickets found.")
    conn.close()


def cmd_init(args):
    """Initialize the agentplan database and auto-detect installed AI tools."""
    dir_path, db_path = get_db_path()
    os.makedirs(dir_path, exist_ok=True)
    conn = get_connection(db_path)
    init_db(conn)
    detected_tools = _detect_installed_tools()
    created_agents = _create_default_agents(conn, detected_tools)
    conn.commit()
    conn.close()
    print(f"Initialized agentplan database at {db_path}")
    if created_agents:
        print(f"Auto-detected agents: {', '.join(created_agents)}")


def cmd_create(args):
    """Create a new project with optional inline tickets and directory link."""
    _validate_len(args.title, MAX_TITLE_LEN, "Project title")
    _validate_len(args.notes, MAX_NOTES_LEN, "Notes")
    timeout_sec = _validate_timeout_sec(getattr(args, "timeout", None))
    conn = _ensure(get_connection())
    
    # Validate and resolve space
    space_slug = getattr(args, "space", "default")
    space_row = conn.execute("SELECT id FROM spaces WHERE slug=?", (space_slug,)).fetchone()
    if not space_row:
        conn.close()
        fail(f"Space '{space_slug}' does not exist.")
    space_id = space_row[0]
    
    slug = unique_slug(conn, slugify(args.title))
    conn.execute(
        "INSERT INTO projects (slug, title, notes, dir, timeout_sec, space_id) VALUES (?,?,?,?,?,?)",
        (slug, args.title, args.notes, args.dir, timeout_sec, space_id),
    )
    pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    n = 0
    for t in args.ticket or []:
        num = n + 1
        conn.execute(
            "INSERT INTO tickets (project_id, num, title) VALUES (?,?,?)",
            (pid, num, t),
        )
        ticket_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        _record_ticket_history(conn, ticket_id, None, "created")
        n += 1
    conn.commit()
    msg = f"Created project '{args.title}' ({slug})"
    if n:
        msg += f" with {n} ticket(s)"
    print(msg)
    conn.close()


def cmd_project(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    
    # Check that at least one flag is provided
    dir_path = (args.dir or "").strip() if hasattr(args, 'dir') else ""
    space_slug = (args.space or "").strip() if hasattr(args, 'space') else ""
    
    if not dir_path and not space_slug:
        conn.close()
        fail("Missing arguments.", suggestions=["Use: agentplan project <slug> --dir ~/path/to/repo", "Or: agentplan project <slug> --space <space-slug>"])
    
    updates = []
    params = []
    resolved_dir = None
    
    # Handle --dir flag
    if dir_path:
        resolved_dir = os.path.expanduser(dir_path)
        if not os.path.exists(resolved_dir):
            print(f"Warning: directory does not exist on disk: {resolved_dir}")
        updates.append("dir=?")
        params.append(resolved_dir)
    
    # Handle --space flag
    if space_slug:
        # Validate that the space exists
        space_row = conn.execute("SELECT id FROM spaces WHERE slug=?", (space_slug,)).fetchone()
        if not space_row:
            conn.close()
            fail(f"Space '{space_slug}' does not exist.", suggestions=["Use: agentplan space list"])
        space_id = space_row[0]
        updates.append("space_id=?")
        params.append(space_id)
    
    # Add updated_at timestamp
    updates.append("updated_at=?")
    params.append(_now())
    params.append(proj["id"])
    
    # Execute update
    update_stmt = "UPDATE projects SET " + ", ".join(updates) + " WHERE id=?"
    conn.execute(update_stmt, params)
    conn.commit()
    conn.close()
    
    # Print confirmation messages
    if dir_path and space_slug:
        print(f"Updated project '{proj['slug']}' directory to: {resolved_dir} and moved to space '{space_slug}'")
    elif dir_path:
        print(f"Updated project '{proj['slug']}' directory to: {resolved_dir}")
    else:
        print(f"Moved project '{proj['slug']}' to space '{space_slug}'")


def cmd_space_create(args):
    """Create a new space."""
    args.slug = slugify(args.slug) or ""
    if not args.slug:
        fail("Invalid space slug.", suggestions=["Use alphanumeric characters and dashes."])
    args.slug = args.slug.lower()
    _validate_len(args.slug, MAX_SLUG_LEN, "Space slug")
    title = (args.title or "").strip()
    if not title:
        title = args.slug.replace("-", " ").title()
    _validate_len(title, MAX_TITLE_LEN, "Space title")
    description = (args.description or "").strip()
    if description:
        _validate_len(description, MAX_DESC_LEN, "Space description")
    
    conn = _ensure(get_connection())
    
    # Check if space already exists
    existing = conn.execute("SELECT id FROM spaces WHERE slug=?", (args.slug,)).fetchone()
    if existing:
        conn.close()
        fail(f"Space '{args.slug}' already exists.")
    
    # Insert space into database
    conn.execute(
        "INSERT INTO spaces (slug, title, description) VALUES (?,?,?)",
        (args.slug, title, description if description else None),
    )
    conn.commit()
    
    # Create space directory
    space_dir = ensure_space_directory(args.slug)
    
    conn.close()
    msg = f"Created space '{args.slug}'"
    if title != args.slug:
        msg += f" ({title})"
    print(msg)


def cmd_space_list(args):
    """List all spaces with project and doc counts."""
    conn = _ensure(get_connection())
    
    # Get all spaces
    spaces = conn.execute("SELECT id, slug, title FROM spaces ORDER BY slug").fetchall()
    
    if not spaces:
        conn.close()
        print("No spaces found.")
        return
    
    # Get dir path for reading docs
    dir_path, _ = get_db_path()
    
    # Prepare rows for display
    rows = []
    for space in spaces:
        space_id = space["id"]
        slug = space["slug"]
        title = space["title"]
        
        # Count projects in this space
        proj_result = conn.execute("SELECT COUNT(*) as cnt FROM projects WHERE space_id=?", (space_id,)).fetchone()
        proj_count = proj_result["cnt"] if proj_result else 0
        
        # Count docs (markdown files) in this space's directory
        space_dir = os.path.join(dir_path, "spaces", slug)
        doc_count = 0
        if os.path.isdir(space_dir):
            doc_count = len([f for f in os.listdir(space_dir) if f.endswith(".md")])
        
        # Mark default space
        marker = " (default)" if slug == "default" else ""
        rows.append((slug, title + marker, proj_count, doc_count))
    
    conn.close()
    
    # Display as table
    print(f"{'SLUG':<20} {'TITLE':<30} {'PROJECTS':<10} {'DOCS'}")
    print("-" * 70)
    
    # Sort: non-default spaces first, then default last
    non_default = [r for r in rows if "(default)" not in r[1]]
    default = [r for r in rows if "(default)" in r[1]]
    sorted_rows = non_default + default
    
    for slug, title, proj_count, doc_count in sorted_rows:
        print(f"{slug:<20} {title:<30} {proj_count:<10} {doc_count}")


def cmd_space_show(args):
    """Show details about a specific space."""
    _validate_len(args.slug, MAX_SLUG_LEN, "Space slug")
    conn = _ensure(get_connection())
    
    # Get space details
    space = conn.execute("SELECT id, slug, title, description, created_at, updated_at FROM spaces WHERE slug=?", (args.slug,)).fetchone()
    if not space:
        conn.close()
        fail(f"Space '{args.slug}' not found.")
    
    space_id = space["id"]
    title = space["title"]
    description = space["description"]
    created_at = space["created_at"]
    updated_at = space["updated_at"]
    
    # Get projects in this space
    projects = conn.execute("SELECT id, slug, title, status FROM projects WHERE space_id=? ORDER BY slug", (space_id,)).fetchall()
    
    # Get docs in this space
    dir_path, _ = get_db_path()
    space_dir = os.path.join(dir_path, "spaces", args.slug)
    docs = []
    if os.path.isdir(space_dir):
        docs = sorted([f for f in os.listdir(space_dir) if f.endswith(".md")])
    
    conn.close()
    
    # Display space details
    print(f"Space: {title}")
    print(f"Slug:  {args.slug}")
    if description:
        print(f"Description: {description}")
    print(f"Created: {created_at}")
    print(f"Updated: {updated_at}")
    print()
    
    # Display projects
    print(f"Projects ({len(projects)}):")
    if projects:
        for proj in projects:
            status = proj["status"]
            marker = f" [{status}]" if status != "active" else ""
            print(f"  - {proj['slug']:<30} {proj['title']}{marker}")
    else:
        print("  (none)")
    print()
    
    # Display docs
    print(f"Docs ({len(docs)}):")
    if docs:
        for doc in docs:
            print(f"  - {doc}")
    else:
        print("  (none)")


def cmd_space_update(args):
    """Update a space's title and/or description."""
    _validate_len(args.slug, MAX_SLUG_LEN, "Space slug")
    conn = _ensure(get_connection())
    
    # Get existing space
    space = conn.execute("SELECT id, slug, title, description FROM spaces WHERE slug=?", (args.slug,)).fetchone()
    if not space:
        conn.close()
        fail(f"Space '{args.slug}' not found.")
    
    updates = []
    values = []
    
    # Update title if provided
    if args.title is not None:
        title = args.title.strip()
        _validate_len(title, MAX_TITLE_LEN, "Space title")
        updates.append("title=?")
        values.append(title)
    
    # Update description if provided
    if args.description is not None:
        description = args.description.strip()
        if description:
            _validate_len(description, MAX_DESC_LEN, "Space description")
            updates.append("description=?")
            values.append(description)
        else:
            # Allow clearing description with empty string
            updates.append("description=?")
            values.append(None)
    
    if not updates:
        conn.close()
        fail(
            "No updates provided.",
            suggestions=["Use at least one of: `--title`, `--description`."],
        )
    
    # Update the space
    updates.append("updated_at=?")
    values.append(_now())
    values.append(space["id"])
    
    conn.execute(f"UPDATE spaces SET {', '.join(updates)} WHERE id=?", values)
    conn.commit()
    print(f"Updated space '{args.slug}'.")
    conn.close()


def cmd_space_delete(args):
    """Delete a space, orphaning its projects (sets space_id to NULL) and removing docs on disk."""
    _validate_len(args.slug, MAX_SLUG_LEN, "Space slug")
    conn = _ensure(get_connection())
    
    # Get space details
    space = conn.execute("SELECT id, slug, title FROM spaces WHERE slug=?", (args.slug,)).fetchone()
    if not space:
        conn.close()
        fail(f"Space '{args.slug}' not found.")
    
    space_id = space["id"]
    
    # Prevent deletion of default space
    if args.slug == "default":
        conn.close()
        fail("Cannot delete the default space.")
    
    # Count projects in this space
    proj_count_result = conn.execute("SELECT COUNT(*) as cnt FROM projects WHERE space_id=?", (space_id,)).fetchone()
    proj_count = proj_count_result["cnt"] if proj_count_result else 0
    
    # Count docs (markdown files) in this space's directory
    dir_path, _ = get_db_path()
    space_dir = os.path.join(dir_path, "spaces", args.slug)
    doc_count = 0
    if os.path.isdir(space_dir):
        doc_count = len([f for f in os.listdir(space_dir) if f.endswith(".md")])
    
    # Ask for confirmation
    confirmation_message = f"This will delete the space and orphan {proj_count} projects. {doc_count} docs will be removed."
    print(confirmation_message)
    if not getattr(args, "force", False):
        confirmation_input = input(f"Type the space slug to confirm: ").strip()
        if confirmation_input != args.slug:
            conn.close()
            print("Deletion cancelled.")
            return
    
    # Reassign all projects in this space to no space (orphan them)
    conn.execute("UPDATE projects SET space_id = NULL WHERE space_id = ?", (space_id,))
    
    # Delete the space row
    conn.execute("DELETE FROM spaces WHERE id=?", (space_id,))
    conn.commit()
    
    # Delete the space directory from disk
    if os.path.isdir(space_dir):
        shutil.rmtree(space_dir)
    
    print(f"Deleted space '{args.slug}'. {proj_count} projects reassigned to no space.")
    conn.close()


def _validate_doc_file_path(space, filename):
    """Validate space and filename, return absolute file path. Raises CliError if invalid."""
    space = (space or "").strip()
    filename = (filename or "").strip()
    
    if not space:
        fail("Space slug is required.", suggestions=["Use: agentplan doc <command> <space> <filename>"])
    if not filename:
        fail("Filename is required.", suggestions=["Use: agentplan doc <command> <space> <filename>"])
    
    # Validate that space exists
    conn = _ensure(get_connection())
    space_row = conn.execute("SELECT id FROM spaces WHERE slug=?", (space,)).fetchone()
    if not space_row:
        conn.close()
        fail(f"Space '{space}' not found.", suggestions=["Create it first with: agentplan space create <slug>"])
    conn.close()
    
    # Get space directory and validate file path
    space_dir = os.path.realpath(get_space_directory(space))
    file_path = os.path.realpath(os.path.join(space_dir, filename))
    if not file_path.startswith(space_dir + os.sep):
        fail("Invalid filename.", suggestions=["Filenames must not contain path traversal characters."])
    
    # Check if file exists
    if not os.path.isfile(file_path):
        fail(f"File not found: {filename}", suggestions=[f"Check the file exists in space '{space}' with: agentplan doc list {space}"])
    
    return file_path


def cmd_doc_add(args):
    """Create a new document in a space."""
    space = (args.space or "").strip()
    title = (args.title or "").strip()
    
    if not space:
        fail("Space slug is required.", suggestions=["Use: agentplan doc add <space> '<title>'"])
    if not title:
        fail("Document title is required.", suggestions=["Use: agentplan doc add <space> '<title>'"])
    
    # Validate that space exists
    conn = _ensure(get_connection())
    space_row = conn.execute("SELECT id FROM spaces WHERE slug=?", (space,)).fetchone()
    if not space_row:
        conn.close()
        fail(f"Space '{space}' not found.", suggestions=["Create it first with: agentplan space create <slug>"])
    conn.close()
    
    # Slugify the title for the filename
    slug = slugify(title)
    
    # Get space directory
    space_dir = ensure_space_directory(space)
    
    # Build file path
    file_path = os.path.join(space_dir, f"{slug}.md")
    
    # Check if file already exists
    if os.path.exists(file_path):
        fail(f"Document already exists at {file_path}", suggestions=["Use a different title or check the existing file."])
    
    # Determine content source and read content
    content = ""
    
    if args.file:
        # Mode 2: --file <path> = copy content from existing file
        file_arg = os.path.expanduser(args.file)
        if not os.path.isfile(file_arg):
            fail(f"Source file not found: {file_arg}")
        try:
            with open(file_arg, "r", encoding="utf-8") as f:
                content = f.read()
        except IOError as e:
            fail(f"Failed to read source file: {e}")
    elif args.stdin:
        # Mode 3: --stdin = read from stdin
        try:
            content = sys.stdin.read()
        except IOError as e:
            fail(f"Failed to read from stdin: {e}")
    # else: Mode 1 = create empty file, no content needed
    
    # Warn if content exceeds 1MB
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > 1024 * 1024:
        print(f"Warning: document content exceeds 1MB ({len(content_bytes)} bytes)", file=sys.stderr)
    
    # Write file
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
    except IOError as e:
        fail(f"Failed to write document: {e}")
    
    print(file_path)


def cmd_doc_list(args):
    """List all documents in a space."""
    space = (args.space or "").strip()
    
    if not space:
        fail("Space slug is required.", suggestions=["Use: agentplan doc list <space>"])
    
    # Validate that space exists
    conn = _ensure(get_connection())
    space_row = conn.execute("SELECT id FROM spaces WHERE slug=?", (space,)).fetchone()
    if not space_row:
        conn.close()
        fail(f"Space '{space}' not found.", suggestions=["Create it first with: agentplan space create <slug>"])
    conn.close()
    
    # Get space directory
    space_dir = get_space_directory(space)
    
    # List all .md files in the directory
    docs = []
    if os.path.isdir(space_dir):
        for filename in sorted(os.listdir(space_dir)):
            if filename.endswith(".md"):
                file_path = os.path.join(space_dir, filename)
                try:
                    stat_info = os.stat(file_path)
                    size_bytes = stat_info.st_size
                    modified_timestamp = stat_info.st_mtime
                    
                    # Format size as human-readable (e.g., 4.2 KB)
                    if size_bytes < 1024:
                        size_str = f"{size_bytes} B"
                    elif size_bytes < 1024 * 1024:
                        size_str = f"{size_bytes / 1024:.1f} KB"
                    else:
                        size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
                    
                    # Format modified date
                    modified_date = datetime.fromtimestamp(modified_timestamp).strftime("%Y-%m-%d")
                    
                    docs.append((filename, size_str, modified_date))
                except OSError:
                    pass
    
    # Display results
    if docs:
        for filename, size_str, modified_date in docs:
            print(f"  - {filename} ({size_str}, modified {modified_date})")
    else:
        print("(no documents)")


def cmd_doc_show(args):
    """Print raw markdown content of a document to stdout."""
    file_path = _validate_doc_file_path(args.space, args.filename)
    
    # Large file warning
    file_size = os.path.getsize(file_path)
    if file_size > 1_000_000 and not getattr(args, "force", False):
        fail(f"File is large ({file_size} bytes). Use --force to display anyway.")
    
    # Read and print the file content
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            sys.stdout.write(f.read())
    except IOError as e:
        fail(f"Failed to read document: {e}")


def cmd_doc_path(args):
    """Print the absolute file path of a document to stdout."""
    file_path = _validate_doc_file_path(args.space, args.filename)
    print(os.path.abspath(file_path))


def cmd_doc_remove(args):
    """Delete a document from a space."""
    file_path = _validate_doc_file_path(args.space, args.filename)
    space = (args.space or "").strip()
    filename = (args.filename or "").strip()
    
    # Ask for confirmation
    if not getattr(args, "force", False):
        confirmation_input = input(f"Delete document '{filename}'? Type the filename to confirm: ").strip()
        if confirmation_input != filename:
            print("Deletion cancelled.")
            return
    
    # Delete the file
    try:
        os.remove(file_path)
    except OSError as e:
        fail(f"Failed to delete document: {e}")
    
    print(f"Deleted document '{filename}' from space '{space}'.")


def cmd_ticket_add(args):
    """Add a new ticket to a project with optional description, tags, priority, and dependencies."""
    _validate_len(args.title, MAX_TITLE_LEN, "Ticket title")
    _validate_len(args.desc, MAX_DESC_LEN, "Description")
    _validate_len(args.notes, MAX_NOTES_LEN, "Notes")
    _validate_len(getattr(args, "tag", None), MAX_TAG_LEN, "Tags")
    # Validate non-database fields early, before opening connection
    due_date = _parse_due_date(getattr(args, "due", None))
    timeout_sec = _validate_timeout_sec(getattr(args, "timeout", None))
    model_tier = getattr(args, "model", None) or "auto"
    _validate_model_tier(model_tier)
    
    conn = _ensure(get_connection())
    try:
        proj = resolve_project(conn, args.project)
        # Ticket #17: validate --role against registered roles
        role_tag = None
        if getattr(args, "role", None):
            role = db_get_role(conn, args.role)
            if not role:
                fail(
                    f"Role '{args.role}' is not registered.",
                    suggestions=["Add it first with: agentplan role add " + args.role],
                )
            role_tag = f"role:{role.name}"
        deps = []
        if args.depends:
            deps = [int(x.strip()) for x in args.depends.split(",")]
            for d in deps:
                resolve_ticket(conn, proj["id"], d, proj["slug"])
        num = _next_ticket_num(conn, proj["id"])
        tags = _parse_tags(args.tag)
        _validate_role_tags_or_fail(conn, tags)
        if role_tag:
            existing = [t for t in tags.split(",") if t] if tags else []
            if role_tag not in existing:
                existing.append(role_tag)
            tags = ",".join(existing)
        _validate_role_tags_or_fail(conn, tags)
        conn.execute(
            "INSERT INTO tickets (project_id, num, title, description, priority, tags, depends_on, notes, due_date, timeout_sec, model_tier) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (proj["id"], num, args.title, args.desc, args.priority or "none", tags, json.dumps(deps), args.notes, due_date, timeout_sec, model_tier),
        )
        ticket_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        _record_ticket_history(conn, ticket_id, None, "created")
        if deps:
            tickets = conn.execute("SELECT * FROM tickets WHERE project_id=?", (proj["id"],)).fetchall()
            if has_cycle(tickets, num, deps):
                conn.execute("DELETE FROM tickets WHERE project_id=? AND num=?", (proj["id"], num))
                conn.commit()
                fail(
                    "Circular dependency detected.",
                    suggestions=["Remove one of the dependency links to break the cycle."],
                )
        # Reopen completed/abandoned projects when new tickets are added
        conn.execute(
            "UPDATE projects SET status='active', updated_at=? WHERE id=? AND status IN ('completed','abandoned','archived')",
            (_now(), proj["id"]),
        )
        conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
        conn.commit()
        if proj["status"] in ("completed", "abandoned"):
            print(f"📂 Reopened project '{proj['slug']}' (was {proj['status']})")
        print(f"Added ticket #{num}: {args.title} [priority: {_priority_label(args.priority)}]")
    finally:
        conn.close()


def cmd_ticket_update(args):
    if args.title is not None:
        _validate_len(args.title, MAX_TITLE_LEN, "Ticket title")
    if args.notes is not None:
        _validate_len(args.notes, MAX_NOTES_LEN, "Notes")
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    t = resolve_ticket(conn, proj["id"], args.ticket_id, proj["slug"])

    updates = []
    values = []
    if args.title is not None:
        updates.append("title=?")
        values.append(args.title)
    if args.notes is not None:
        updates.append("notes=?")
        values.append(args.notes)
    if args.depends is not None:
        deps = [int(x.strip()) for x in args.depends.split(",") if x.strip()]
        for d in deps:
            resolve_ticket(conn, proj["id"], d, proj["slug"])
        tickets = conn.execute("SELECT * FROM tickets WHERE project_id=?", (proj["id"],)).fetchall()
        if has_cycle(tickets, t["num"], deps):
            conn.close()
            fail(
                "Circular dependency detected.",
                suggestions=["Adjust `--depends` so tickets do not reference each other in a loop."],
            )
        updates.append("depends_on=?")
        values.append(json.dumps(sorted(set(deps))))
    if args.priority is not None:
        updates.append("priority=?")
        values.append(args.priority)

    if not updates:
        conn.close()
        fail(
            "No updates provided.",
            suggestions=["Use at least one of: `--title`, `--notes`, `--depends`, `--priority`."],
        )

    values.append(t["id"])
    conn.execute(f"UPDATE tickets SET {', '.join(updates)} WHERE id=?", values)
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    conn.commit()
    print(f"Updated ticket #{t['num']}.")
    conn.close()


def cmd_ticket_edit(args):
    _validate_len(args.title, MAX_TITLE_LEN, "Ticket title")
    _validate_len(args.desc, MAX_DESC_LEN, "Description")
    _validate_len(getattr(args, "tag", None), MAX_TAG_LEN, "Tags")
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    t = resolve_ticket(conn, proj["id"], args.ticket_id, proj["slug"])

    updates = []
    values = []
    if args.title is not None:
        updates.append("title=?")
        values.append(args.title)
    if args.desc is not None:
        updates.append("description=?")
        values.append(args.desc)
    if args.priority is not None:
        updates.append("priority=?")
        values.append(args.priority)
    if args.tag is not None:
        parsed_tags = _parse_tags(args.tag)
        _validate_role_tags_or_fail(conn, parsed_tags)
        updates.append("tags=?")
        values.append(parsed_tags)
    if args.due is not None:
        updates.append("due_date=?")
        values.append(_parse_due_date(args.due))
    if args.timeout is not None:
        updates.append("timeout_sec=?")
        values.append(_validate_timeout_sec(args.timeout))
    if getattr(args, "model", None) is not None:
        _validate_model_tier(args.model)
        updates.append("model_tier=?")
        values.append(args.model)

    if not updates:
        conn.close()
        fail(
            "No updates provided.",
            suggestions=["Use at least one of: `--title`, `--desc`, `--priority`, `--tag`, `--due`, `--timeout`, `--model`."],
        )

    values.append(t["id"])
    conn.execute(f"UPDATE tickets SET {', '.join(updates)} WHERE id=?", values)
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    conn.commit()
    print(f"Updated ticket #{t['num']}.")
    conn.close()


def _expand_ticket_ids(ticket_ids):
    """Expand ticket ID args to support comma-separated values (e.g. 1,2,3)."""
    expanded = []
    for raw in ticket_ids:
        parts = [p.strip() for p in raw.split(",")]
        expanded.extend(p for p in parts if p)
    return expanded


def _validate_ticket_transition_or_fail(ticket, to_state):
    ok, reason = validate_transition(ticket["status"], to_state)
    if not ok:
        fail(
            f"Ticket #{ticket['num']} transition blocked: {reason}",
            suggestions=[f"Current state is '{ticket['status']}'. Choose a valid transition."],
        )


def _fire_webhook_hook(target, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        target,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5):
        return


def _fire_command_hook(target, payload):
    """Execute a DB-persisted command hook safely without a shell."""
    rendered_target = _render_agent_command(target, payload["ticket_id"], payload["project"])
    argv = shlex.split(rendered_target, posix=True)
    if not argv:
        raise ValueError("empty command hook target")

    env = os.environ.copy()
    env.update(
        {
            "AGENTPLAN_TICKET_ID": str(payload["ticket_id"]),
            "AGENTPLAN_TITLE": str(payload["ticket_title"]),
            "AGENTPLAN_PROJECT": str(payload["project"]),
            "AGENTPLAN_STATUS": str(payload["status"]),
            "AGENTPLAN_AGENT": str(payload["agent"] or ""),
        }
    )
    subprocess.run(
        argv,
        shell=False,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        check=False,
    )


def _fire_chain_hook(project_slug, default_agent_name=None):
    """Launch the next chain candidate in a new terminal (fire-and-forget)."""
    chain_conn = _ensure(get_connection())
    try:
        proj = resolve_project(chain_conn, project_slug)
        ticket = _next_chain_candidate(chain_conn, proj["id"])
        if not ticket:
            return

        agent = db_route_ticket(chain_conn, ticket, default_agent_name=default_agent_name)
        if not agent:
            return

        command = _render_agent_command(
            agent.get("command_template"),
            ticket,
            proj,
            project_dir=proj["dir"] if "dir" in proj.keys() else None,
        )
        spawn_terminal(command, title=f"agentplan:{agent['name']}")
    finally:
        chain_conn.close()


def _fire_on_complete_hooks(conn, project, ticket, agent_name=None):
    hooks = conn.execute(
        "SELECT * FROM hooks WHERE project_id=? AND event='on-complete' ORDER BY id",
        (project["id"],),
    ).fetchall()
    if not hooks:
        return
    payload = {
        "ticket_id": ticket["num"],
        "ticket_title": ticket["title"],
        "project": project["slug"],
        "status": "done",
        "agent": agent_name,
    }
    for hook in hooks:
        try:
            if hook["hook_type"] == "webhook":
                _fire_webhook_hook(hook["target"], payload)
            elif hook["hook_type"] == "command":
                _fire_command_hook(hook["target"], payload)
            elif hook["hook_type"] == "chain":
                _fire_chain_hook(project["slug"], default_agent_name=agent_name)
            else:
                print(f"Warning: unsupported hook type '{hook['hook_type']}' for hook #{hook['id']}", file=sys.stderr)
        except Exception as e:
            print(f"Warning: hook #{hook['id']} failed: {e}", file=sys.stderr)


def cmd_ticket_done(args):
    close_note = getattr(args, 'note', None)
    done_by = getattr(args, "agent", None)
    _validate_len(close_note, MAX_NOTES_LEN, "Close note")
    _validate_len(done_by, MAX_AGENT_LEN, "Agent name")
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    completed_tickets = []
    for num_str in _expand_ticket_ids(args.ticket_ids):
        t = resolve_ticket(conn, proj["id"], num_str, proj["slug"])
        _validate_ticket_transition_or_fail(t, "done")
        conn.execute(
            "UPDATE tickets SET status='done', completed_at=?, close_note=?, done_by=?, claimed_at=NULL WHERE id=?",
            (_now(), close_note, done_by, t["id"])
        )
        _record_ticket_history(conn, t["id"], t["status"], "done")
        completed_tickets.append(t)
        msg = f"✓ Ticket #{t['num']}: {t['title']} → done"
        if close_note:
            msg += f" [{close_note}]"
        if done_by:
            msg += f" (by {done_by})"
        print(msg)
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    was_active = proj["status"] == "active"
    if check_auto_complete(conn, proj["id"]) and was_active:
        print(f"🎉 All tickets done — project '{proj['slug']}' auto-completed!")
    conn.commit()
    conn.close()

    hooks_conn = _ensure(get_connection())
    try:
        for t in completed_tickets:
            _fire_on_complete_hooks(hooks_conn, proj, t, agent_name=done_by)
    finally:
        hooks_conn.close()


def cmd_ticket_skip(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    for num_str in _expand_ticket_ids(args.ticket_ids):
        t = resolve_ticket(conn, proj["id"], num_str, proj["slug"])
        _validate_ticket_transition_or_fail(t, "skipped")
        conn.execute("UPDATE tickets SET status='skipped', completed_at=?, claimed_at=NULL WHERE id=?", (_now(), t["id"]))
        _record_ticket_history(conn, t["id"], t["status"], "skipped")
        print(f"⊘ Ticket #{t['num']}: {t['title']} → skipped")
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    check_auto_complete(conn, proj["id"])
    conn.commit()
    conn.close()


def cmd_ticket_start(args):
    started_by = getattr(args, "agent", None)
    _validate_len(started_by, MAX_AGENT_LEN, "Agent name")
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    t = resolve_ticket(conn, proj["id"], args.ticket_id, proj["slug"])
    _validate_ticket_transition_or_fail(t, "in-progress")
    conn.execute(
        "UPDATE tickets SET status='in-progress', started_by=? WHERE id=?",
        (started_by, t["id"]),
    )
    _record_ticket_history(conn, t["id"], t["status"], "started")
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    conn.commit()
    msg = f"▶ Ticket #{t['num']}: {t['title']} → in-progress"
    if started_by:
        msg += f" (by {started_by})"
    print(msg)
    conn.close()


def _set_ticket_state_with_reason(args, to_state, symbol):
    reason = getattr(args, "reason", None)
    _validate_len(reason, MAX_NOTES_LEN, "Reason")
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    t = resolve_ticket(conn, proj["id"], args.ticket_id, proj["slug"])
    _validate_ticket_transition_or_fail(t, to_state)
    conn.execute(
        "UPDATE tickets SET status=?, close_note=?, completed_at=NULL, claimed_at=NULL WHERE id=?",
        (to_state, reason, t["id"]),
    )
    _record_ticket_history(conn, t["id"], t["status"], to_state)
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    conn.commit()
    msg = f"{symbol} Ticket #{t['num']}: {t['title']} → {to_state}"
    if reason:
        msg += f" [{reason}]"
    print(msg)
    conn.close()


def cmd_ticket_block(args):
    _set_ticket_state_with_reason(args, "blocked", "⛔")


def cmd_ticket_fail(args):
    _set_ticket_state_with_reason(args, "failed", "✗")


def cmd_ticket_review(args):
    _set_ticket_state_with_reason(args, "needs-review", "👀")


def _reap_expired_claims(conn, project_id):
    expired_claims = conn.execute(
        """
        SELECT * FROM tickets
        WHERE project_id=?
          AND status='in-progress'
          AND claim_timeout IS NOT NULL
          AND claimed_at IS NOT NULL
          AND (
            claim_timeout <= 0
            OR (
              claim_timeout > 0
              AND julianday(replace(claimed_at, 'T', ' ')) IS NOT NULL
              AND julianday('now') > (julianday(replace(claimed_at, 'T', ' ')) + (claim_timeout / 86400.0))
            )
          )
        """,
        (project_id,),
    ).fetchall()

    reclaimed_count = 0
    for t in expired_claims:
        reclaimed = conn.execute(
            "UPDATE tickets SET status='pending', claimed_at=NULL, claim_timeout=NULL WHERE id=? AND status='in-progress'",
            (t["id"],),
        ).rowcount
        if reclaimed == 1:
            reclaimed_count += 1
            # Reclaiming is an action; the ticket transitions back into pending.
            _record_ticket_history(conn, t["id"], t["status"], "pending")

    return reclaimed_count


def _claim_next_ticket(conn, project_id, started_by=None, tag=None):
    """Atomically claim the next unblocked pending ticket for a project."""
    tag_filter = (tag or "").strip().lower()
    lock_owner = f"pid-{os.getpid()}-thr-{threading.get_ident()}"
    conn.execute("BEGIN IMMEDIATE")
    try:
        if not _acquire_claim_lock(conn, project_id, lock_owner):
            conn.rollback()
            return None

        _reap_expired_claims(conn, project_id)

        tickets = conn.execute(
            "SELECT * FROM tickets WHERE project_id=? ORDER BY num", (project_id,)
        ).fetchall()
        done_nums = {t["num"] for t in tickets if t["status"] in ("done", "skipped")}
        candidates = [
            t for t in tickets
            if t["status"] == "pending"
            and not _is_blocked(t, done_nums)
            and _ticket_has_tag(t, tag_filter)
        ]
        candidates = _sort_next_items(candidates)
        if not candidates:
            _release_claim_lock(conn, project_id, lock_owner)
            conn.rollback()
            return None

        chosen = candidates[0]
        claimed_at = _now()
        if not is_valid_iso_local_timestamp(claimed_at):
            raise ValueError("internal error: invalid claimed_at timestamp")
        updated = conn.execute(
            "UPDATE tickets SET status='in-progress', started_by=?, claimed_at=? WHERE id=? AND status='pending'",
            (started_by, claimed_at, chosen["id"]),
        ).rowcount
        if updated != 1:
            _release_claim_lock(conn, project_id, lock_owner)
            conn.rollback()
            return None

        _record_ticket_history(conn, chosen["id"], chosen["status"], "started")
        conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), project_id))
        _release_claim_lock(conn, project_id, lock_owner)
        claimed = conn.execute("SELECT * FROM tickets WHERE id=?", (chosen["id"],)).fetchone()
        conn.commit()
        return claimed
    except Exception:
        conn.rollback()
        raise


def cmd_claim(args):
    """Atomically claim the next unblocked ticket in a project for an agent."""
    _validate_len(getattr(args, "agent", None), MAX_AGENT_LEN, "Agent name")
    timeout = getattr(args, "timeout", None)
    if timeout is not None and timeout <= 0:
        fail("--timeout must be a positive integer")

    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    claimed = _claim_next_ticket(
        conn,
        proj["id"],
        started_by=getattr(args, "agent", None),
        tag=getattr(args, "tag", None),
    )
    if not claimed:
        print("No unblocked tickets to claim.")
        conn.close()
        sys.exit(1)

    if timeout is not None:
        conn.execute(
            "UPDATE tickets SET claim_timeout=? WHERE id=?",
            (timeout, claimed["id"]),
        )
        conn.commit()
        claimed = conn.execute("SELECT * FROM tickets WHERE id=?", (claimed["id"],)).fetchone()

    model_tier = claimed["model_tier"] if "model_tier" in claimed.keys() else "auto"
    msg = f"▶ Claimed ticket #{claimed['num']}: {claimed['title']} → in-progress"
    if model_tier != "auto":
        msg += f" [model: {model_tier}]"
    if claimed["started_by"]:
        msg += f" (by {claimed['started_by']})"
    print(msg)
    conn.close()


def cmd_reap(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    conn.execute("BEGIN IMMEDIATE")
    try:
        reclaimed_count = _reap_expired_claims(conn, proj["id"])
        if reclaimed_count:
            conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise

    if reclaimed_count:
        print(f"Reclaimed {reclaimed_count} expired ticket(s).")
    else:
        print("No expired claims to reclaim.")
    conn.close()


def cmd_ticket_list(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    filt = args.status or "all"
    if filt == "all":
        tickets = conn.execute(
            "SELECT * FROM tickets WHERE project_id=? ORDER BY num", (proj["id"],)
        ).fetchall()
    else:
        tickets = conn.execute(
            "SELECT * FROM tickets WHERE project_id=? AND status=? ORDER BY num",
            (proj["id"], filt),
        ).fetchall()
    if not tickets:
        print("No tickets found.")
        conn.close()
        sys.exit(1)
    done_nums = {
        r["num"]
        for r in conn.execute(
            "SELECT num, status FROM tickets WHERE project_id=?", (proj["id"],)
        ).fetchall()
        if r["status"] in ("done", "skipped")
    }
    subtask_progress = _get_subtask_progress_map(conn, [t["id"] for t in tickets])
    for t in tickets:
        blocked = _is_blocked(t, done_nums)
        icon = _ticket_icon(t["status"], blocked)
        progress = _subtask_progress_label(subtask_progress.get(t["id"]))
        progress_segment = f" {progress}" if progress else ""
        model_tier = t["model_tier"] if "model_tier" in t.keys() else "auto"
        tier_segment = f" [model: {model_tier}]" if model_tier != "auto" else ""
        line = f"  {icon} {t['num']}. {t['title']}{progress_segment} [priority: {_priority_label(t['priority'])}]{tier_segment}"
        if t["status"] == "in-progress":
            line += " (in-progress)"
            if t["started_by"]:
                line += f" [started_by: {t['started_by']}]"
        elif blocked and t["status"] == "pending":
            deps = json.loads(t["depends_on"] or "[]")
            waiting = [str(d) for d in deps if d not in done_nums]
            line += f" (blocked — waiting on {', '.join(waiting)})"
        elif t["status"] == "done" and t["done_by"]:
            line += f" [done_by: {t['done_by']}]"
        print(line)
        if t["description"]:
            print(f"       Description: {t['description']}")
    conn.close()


def cmd_next(args):
    """Show next unblocked tickets ready for work (dependencies satisfied)."""
    conn = _ensure(get_connection())
    fmt = args.format or "compact"
    tag_filter = (args.tag or "").strip().lower()
    
    # Resolve space if provided
    space_id = None
    space_slug = getattr(args, "space", None)
    if space_slug:
        space_row = conn.execute("SELECT id FROM spaces WHERE slug=?", (space_slug,)).fetchone()
        if not space_row:
            conn.close()
            fail(f"Space '{space_slug}' does not exist.")
        space_id = space_row[0]
    
    if args.project:
        projects = [resolve_project(conn, args.project)]
    else:
        if space_id:
            projects = conn.execute("SELECT * FROM projects WHERE status='active' AND space_id=? ORDER BY id", (space_id,)).fetchall()
        else:
            projects = conn.execute("SELECT * FROM projects WHERE status='active' ORDER BY id").fetchall()
    if not projects:
        msg = "No active projects."
        if space_slug:
            msg += f" in space '{space_slug}'."
        print(msg)
        conn.close()
        sys.exit(1)

    results = []
    for p in projects:
        _reap_expired_claims(conn, p["id"])
        conn.commit()
        tickets = conn.execute(
            "SELECT * FROM tickets WHERE project_id=? ORDER BY num", (p["id"],)
        ).fetchall()
        items = [t for t in tickets if t["status"] == "in-progress"] + get_unblocked(tickets)
        if tag_filter:
            items = [t for t in items if _ticket_has_tag(t, tag_filter)]
        items = _sort_next_items(items)
        if items:
            results.append((p, items))

    if not results:
        print("No unblocked tickets.")
        conn.close()
        sys.exit(1)

    if fmt == "json":
        payload = []
        for p, items in results:
            t = items[0]
            model_tier = t["model_tier"] if "model_tier" in t.keys() else "auto"
            payload.append(
                {
                    "id": t["num"],
                    "title": t["title"],
                    "status": t["status"],
                    "project": p["slug"],
                    "model_tier": model_tier,
                }
            )
        if args.project:
            print(json.dumps(payload[0], ensure_ascii=False))
        else:
            print(json.dumps(payload, ensure_ascii=False))
        conn.close()
        return

    for p, items in results:
        parts = []
        for t in items:
            m = "▶" if t["status"] == "in-progress" else "○"
            model_tier = t["model_tier"] if "model_tier" in t.keys() else "auto"
            tier_segment = f" [model: {model_tier}]" if model_tier != "auto" else ""
            parts.append(f"[{t['num']}] {t['title']} {m} (priority: {_priority_label(t['priority'])}){tier_segment}")
        print(f"📋 {p['title']}: {', '.join(parts)}")
    conn.close()


def cmd_status(args):
    """Show status of a project or space with ticket breakdown and progress."""
    conn = _ensure(get_connection())
    fmt = args.format or "full"
    tag_filter = (args.tag or "").strip().lower()
    space_slug = getattr(args, "space", None)
    
    # Handle space + project conflict
    if args.project and space_slug:
        conn.close()
        fail(
            "Cannot specify both --project and --space.",
            suggestions=["Choose either: `agentplan status <project>` or `agentplan status --space <space>`"],
        )
    
    # Get space_id if space is provided
    space_id = None
    if space_slug:
        space_row = conn.execute("SELECT id FROM spaces WHERE slug=?", (space_slug,)).fetchone()
        if not space_row:
            conn.close()
            fail(f"Space '{space_slug}' does not exist.")
        space_id = space_row[0]
    
    if args.project:
        projects = [resolve_project(conn, args.project)]
    elif space_id:
        # Get all active projects in the space
        projects = conn.execute(
            "SELECT * FROM projects WHERE status='active' AND space_id=? ORDER BY id",
            (space_id,)
        ).fetchall()
    else:
        projects = conn.execute("SELECT * FROM projects WHERE status='active' ORDER BY id").fetchall()
    if not projects:
        if space_slug:
            print(f"No active projects in space '{space_slug}'.")
        else:
            print("No active projects.")
        conn.close()
        sys.exit(1)
    
    # If showing space-level status, compute aggregate stats
    if space_id and not args.project:
        all_space_tickets = []
        all_space_done_count = 0
        all_space_failed_count = 0
        all_space_needs_review_count = 0
        all_space_blocked_count = 0
        
        for p in projects:
            p_tickets = conn.execute(
                "SELECT * FROM tickets WHERE project_id=? ORDER BY num", (p["id"],)
            ).fetchall()
            all_space_tickets.extend(p_tickets)
            all_space_done_count += sum(1 for t in p_tickets if t["status"] in ("done", "skipped"))
            all_space_failed_count += sum(1 for t in p_tickets if t["status"] == "failed")
            all_space_needs_review_count += sum(1 for t in p_tickets if t["status"] == "needs-review")
            
            p_done_nums = {t["num"] for t in p_tickets if t["status"] in ("done", "skipped")}
            open_tickets = [t for t in p_tickets if t["status"] in ("pending", "in-progress")]
            all_space_blocked_count += sum(1 for t in open_tickets if _is_blocked(t, p_done_nums))
            all_space_blocked_count += sum(1 for t in p_tickets if t["status"] == "blocked")
        
        total_space_tickets = len(all_space_tickets)
        
        # Print aggregate status
        _extra = ""
        if all_space_failed_count:
            _extra += f", {all_space_failed_count} failed"
        if all_space_needs_review_count:
            _extra += f", {all_space_needs_review_count} needs-review"
        
        print(f"📋 Space '{space_slug}': {all_space_done_count}/{total_space_tickets} done, {all_space_blocked_count} blocked{_extra}")
        print(f"  Across {len(projects)} project(s)")
        
        # List individual projects for reference
        for p in projects:
            p_tickets = conn.execute(
                "SELECT * FROM tickets WHERE project_id=? ORDER BY num", (p["id"],)
            ).fetchall()
            p_done = sum(1 for t in p_tickets if t["status"] in ("done", "skipped"))
            p_total = len(p_tickets)
            print(f"    - {p['slug']}: {p_done}/{p_total} done")
        
        conn.close()
        return
    
    for p in projects:
        all_tickets = conn.execute(
            "SELECT * FROM tickets WHERE project_id=? ORDER BY num", (p["id"],)
        ).fetchall()
        subtask_progress = _get_subtask_progress_map(conn, [t["id"] for t in all_tickets])
        tickets = [t for t in all_tickets if _ticket_has_tag(t, tag_filter)] if tag_filter else all_tickets
        done_nums = {t["num"] for t in all_tickets if t["status"] in ("done", "skipped")}
        done_count = sum(1 for t in tickets if t["status"] in ("done", "skipped"))
        total = len(tickets)
        failed_count = sum(1 for t in tickets if t["status"] == "failed")
        needs_review_count = sum(1 for t in tickets if t["status"] == "needs-review")
        manual_blocked_count = sum(1 for t in tickets if t["status"] == "blocked")
        open_tickets = [t for t in tickets if t["status"] in ("pending", "in-progress")]
        dependency_blocked_count = sum(1 for t in open_tickets if _is_blocked(t, done_nums))
        blocked_count = manual_blocked_count + dependency_blocked_count
        unblocked_open = [t for t in open_tickets if not _is_blocked(t, done_nums)]
        next_ticket = _sort_next_items(unblocked_open)[0] if unblocked_open else None

        if fmt == "json":
            data = {
                "id": p["id"], "slug": p["slug"], "title": p["title"],
                "status": p["status"], "notes": p["notes"], "dir": p["dir"] if "dir" in p.keys() else None,
                "done": done_count, "total": total,
                "blocked": blocked_count,
                "failed": failed_count,
                "needs_review": needs_review_count,
                "next": (
                    {"num": next_ticket["num"], "title": next_ticket["title"]}
                    if next_ticket
                    else None
                ),
                "tickets": [
                    {
                        **dict(t),
                        "subtasks_done": subtask_progress.get(t["id"], {}).get("done", 0),
                        "subtasks_total": subtask_progress.get(t["id"], {}).get("total", 0),
                    }
                    for t in tickets
                ],
            }
            print(json.dumps(data, indent=2))
            continue

        if fmt == "compact":
            items = _sort_next_items(unblocked_open)
            parts = []
            for t in items[:3]:
                progress = _subtask_progress_label(subtask_progress.get(t["id"]))
                progress_segment = f" {progress}" if progress else ""
                marker = "▶" if t["status"] == "in-progress" else "○"
                parts.append(
                    f"[{t['num']}] {t['title']}{progress_segment} {marker} ({_priority_label(t['priority'])})"
                )
            nxt = ", ".join(parts)
            _extra = ""
            if failed_count:
                _extra += f", {failed_count} failed"
            if needs_review_count:
                _extra += f", {needs_review_count} needs-review"
            line = f"📋 {p['title']}: {done_count}/{total} done, {blocked_count} blocked{_extra}"
            if nxt:
                line += f" | Next: {nxt}"
            print(line)
            continue

        # Full
        _extra2 = ""
        if failed_count:
            _extra2 += f", {failed_count} failed"
        if needs_review_count:
            _extra2 += f", {needs_review_count} needs-review"
        summary = f"{done_count}/{total} done, {blocked_count} blocked{_extra2}, next: "
        summary += f"[{next_ticket['num']}] {next_ticket['title']}" if next_ticket else "none"
        print(summary)
        print(f"{p['title']} [{p['status']}] — {done_count}/{total} done")
        if p["dir"] if "dir" in p.keys() else None:
            print(f"Directory: {p['dir']}")
        for t in tickets:
            blocked = _is_blocked(t, done_nums)
            icon = _ticket_icon(t["status"], blocked)
            progress = _subtask_progress_label(subtask_progress.get(t["id"]))
            progress_segment = f" {progress}" if progress else ""
            model_tier = t["model_tier"] if "model_tier" in t.keys() else "auto"
            tier_segment = f" [model: {model_tier}]" if model_tier != "auto" else ""
            line = f"  {icon} {t['num']}. {t['title']}{progress_segment} [priority: {_priority_label(t['priority'])}]{tier_segment}"
            if t["status"] == "in-progress":
                line += " (in-progress)"
                if t["started_by"]:
                    line += f" [started_by: {t['started_by']}]"
            elif blocked and t["status"] == "pending":
                deps = json.loads(t["depends_on"] or "[]")
                waiting = [str(d) for d in deps if d not in done_nums]
                line += f" (blocked — waiting on {', '.join(waiting)})"
            elif t["status"] == "done" and t["done_by"]:
                line += f" [done_by: {t['done_by']}]"
            print(line)
            if t["description"]:
                print(f"       Description: {t['description']}")
            if t["status"] == "done" and t["close_note"]:
                print(f"       Note: {t['close_note']}")

        atts = conn.execute(
            "SELECT * FROM attachments WHERE project_id=? ORDER BY id", (p["id"],)
        ).fetchall()
        if atts:
            print("\n  📎 Attachments:")
            for a in atts:
                target = a["path"] or a["url"] or ""
                extra = f" (ticket #{a['ticket_id']})" if a["ticket_id"] else ""
                print(f"    {a['label']} → {target}{extra}")

        logs = conn.execute(
            "SELECT * FROM log WHERE project_id=? ORDER BY id DESC LIMIT 5", (p["id"],)
        ).fetchall()
        if logs:
            print("\n  📝 Recent log:")
            for l in reversed(logs):
                print(f"    {l['created_at'][:10]}: {l['entry']}")

        if p["notes"]:
            print(f"\n  Notes: {p['notes']}")
        print()
    conn.close()


def cmd_list(args):
    conn = _ensure(get_connection())
    
    # Resolve space if provided
    space_id = None
    space_slug = getattr(args, "space", None)
    if space_slug:
        space_row = conn.execute("SELECT id FROM spaces WHERE slug=?", (space_slug,)).fetchone()
        if not space_row:
            conn.close()
            fail(f"Space '{space_slug}' does not exist.")
        space_id = space_row[0]
    
    if getattr(args, "all", False):
        if space_id:
            projects = conn.execute("SELECT * FROM projects WHERE space_id=? ORDER BY id", (space_id,)).fetchall()
        else:
            projects = conn.execute("SELECT * FROM projects ORDER BY id").fetchall()
        filt = "all"
    else:
        filt = args.status or "active"
        if filt == "all":
            if space_id:
                projects = conn.execute(
                    "SELECT * FROM projects WHERE status!='archived' AND space_id=? ORDER BY id", (space_id,)
                ).fetchall()
            else:
                projects = conn.execute(
                    "SELECT * FROM projects WHERE status!='archived' ORDER BY id"
                ).fetchall()
        else:
            if space_id:
                projects = conn.execute(
                    "SELECT * FROM projects WHERE status=? AND space_id=? ORDER BY id", (filt, space_id)
                ).fetchall()
            else:
                projects = conn.execute(
                    "SELECT * FROM projects WHERE status=? ORDER BY id", (filt,)
                ).fetchall()
    if not projects:
        if filt == "all":
            msg = "No projects."
        else:
            msg = f"No {filt} projects."
        if space_slug:
            msg += f" in space '{space_slug}'."
        else:
            msg += ""
        print(msg if msg.endswith('.') else msg)
        conn.close()
        sys.exit(1)
    for p in projects:
        rows = conn.execute(
            "SELECT status FROM tickets WHERE project_id=?", (p["id"],)
        ).fetchall()
        dc = sum(1 for r in rows if r["status"] in ("done", "skipped"))
        prog = f"{dc}/{len(rows)} done" if rows else "no tickets"
        print(f"  {p['slug']} [{p['status']}] — {prog}")
    conn.close()


def cmd_archive(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    if proj["status"] not in ("completed", "abandoned"):
        conn.close()
        fail(
            "Only completed or abandoned projects can be archived.",
            suggestions=["Run `agentplan close <project>` first (or `--abandon`) before archiving."],
        )
    conn.execute(
        "UPDATE projects SET status=?, updated_at=? WHERE id=?",
        ("archived", _now(), proj["id"]),
    )
    conn.commit()
    print(f"Archived project '{proj['slug']}'")
    conn.close()


def cmd_search(args):
    conn = _ensure(get_connection())
    query = (args.query or "").strip()
    if not query:
        conn.close()
        fail("Search query cannot be empty.", suggestions=["Run `agentplan search <text>` with a keyword."])

    query_lower = query.lower()
    like = f"%{query_lower}%"
    
    docs_results = []
    tickets_results = []
    
    # Search docs unless --tickets-only is set
    if not args.tickets_only:
        dir_path, _ = get_db_path()
        spaces_dir = os.path.join(dir_path, "spaces")
        
        if os.path.isdir(spaces_dir):
            # Get all spaces or filter by --space flag
            if args.space:
                spaces_to_search = [args.space]
            else:
                spaces_to_search = [d for d in os.listdir(spaces_dir) if os.path.isdir(os.path.join(spaces_dir, d))]
            
            # Search docs in each space
            for space_slug in spaces_to_search:
                space_path = os.path.join(spaces_dir, space_slug)
                if not os.path.isdir(space_path):
                    continue
                
                for filename in os.listdir(space_path):
                    if not filename.endswith(".md"):
                        continue
                    
                    filepath = os.path.join(space_path, filename)
                    try:
                        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                            if query_lower in content.lower():
                                docs_results.append({
                                    "type": "doc",
                                    "space_slug": space_slug,
                                    "filename": filename,
                                    "content": content[:200] + ("..." if len(content) > 200 else "")
                                })
                    except (IOError, OSError):
                        pass
    
    # Search tickets unless --docs-only is set
    if not args.docs_only:
        query_sql = """
        SELECT
            p.slug AS project_slug,
            p.space_id,
            s.slug AS space_slug,
            t.num AS ticket_num,
            t.title AS ticket_title
        FROM tickets t
        JOIN projects p ON p.id = t.project_id
        LEFT JOIN spaces s ON p.space_id = s.id
        WHERE
            (LOWER(t.title) LIKE ? OR LOWER(COALESCE(t.description, '')) LIKE ?)
        """
        
        if args.space:
            query_sql += " AND s.slug = ? "
            tickets_results = conn.execute(
                query_sql + " ORDER BY p.slug, t.num",
                (like, like, args.space)
            ).fetchall()
        else:
            tickets_results = conn.execute(
                query_sql + " ORDER BY p.slug, t.num",
                (like, like)
            ).fetchall()
    
    conn.close()
    
    # Check if we have any results
    if not docs_results and not tickets_results:
        print("No matching docs or tickets found.")
        sys.exit(1)
    
    # Display docs first
    if docs_results:
        print(f"📄 Docs ({len(docs_results)}):")
        for doc in docs_results:
            print(f"  {doc['space_slug']}: {doc['filename']}")
        print()
    
    # Display tickets
    if tickets_results:
        print(f"🎫 Tickets ({len(tickets_results)}):")
        for row in tickets_results:
            space_info = f" [{row['space_slug']}]" if row['space_slug'] else ""
            print(f"  {row['project_slug']} #{row['ticket_num']}: {row['ticket_title']}{space_info}")
    


def cmd_attach(args):
    _validate_len(args.label, MAX_LABEL_LEN, "Attachment label")
    _validate_len(args.location, MAX_LOCATION_LEN, "Attachment location")
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    ticket_id = None
    if args.ticket:
        t = resolve_ticket(conn, proj["id"], args.ticket, proj["slug"])
        ticket_id = t["id"]
    loc = args.location
    is_url = loc.startswith(("http://", "https://"))
    conn.execute(
        "INSERT INTO attachments (project_id, ticket_id, label, path, url) VALUES (?,?,?,?,?)",
        (proj["id"], ticket_id, args.label, None if is_url else loc, loc if is_url else None),
    )
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    conn.commit()
    print(f"📎 Attached '{args.label}' → {loc}")
    conn.close()


def cmd_log(args):
    parts = list(getattr(args, "parts", []) or [])
    ticket_ref = getattr(args, "ticket", None)
    if ticket_ref is None and len(parts) >= 2 and str(parts[0]).isdigit():
        ticket_ref = parts[0]
        parts = parts[1:]
    entry = " ".join(parts).strip()
    _validate_len(entry, MAX_LOG_ENTRY_LEN, "Log entry")

    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    ticket_id = None
    ticket = None
    if ticket_ref:
        ticket = resolve_ticket(conn, proj["id"], ticket_ref, proj["slug"])
        ticket_id = ticket["id"]
    conn.execute(
        "INSERT INTO log (project_id, ticket_id, entry) VALUES (?,?,?)",
        (proj["id"], ticket_id, entry),
    )

    if ticket and ticket["status"] == "in-progress":
        timeout_sec = _effective_ticket_timeout_sec(proj, ticket)
        if timeout_sec:
            now_dt = datetime.now()
            deadline_dt = now_dt + timedelta(seconds=timeout_sec)
            state = db_get_chain_state(conn, proj["id"])
            if state:
                _set_chain_state_with_artifact(
                    conn,
                    proj,
                    state["status"],
                    current_ticket_id=state.get("current_ticket_id"),
                    pause_reason=state.get("pause_reason"),
                    heartbeat_at=now_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                    deadline_at=deadline_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                )

    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    conn.commit()
    print(f"📝 Logged: {entry}")
    conn.close()


def cmd_close(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    st = "abandoned" if args.abandon else "completed"
    conn.execute("UPDATE projects SET status=?, updated_at=? WHERE id=?", (st, _now(), proj["id"]))
    conn.commit()
    print(f"{'Abandoned' if args.abandon else 'Completed'} project '{proj['slug']}'")
    conn.close()


def cmd_note(args):
    _validate_len(args.text, MAX_NOTES_LEN, "Note text")
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    if args.ticket:
        t = resolve_ticket(conn, proj["id"], args.ticket, proj["slug"])
        conn.execute("UPDATE tickets SET notes=? WHERE id=?", (args.text, t["id"]))
        conn.commit()
        print(f"Updated note on ticket #{t['num']}")
    else:
        conn.execute(
            "UPDATE projects SET notes=?, updated_at=? WHERE id=?",
            (args.text, _now(), proj["id"]),
        )
        conn.commit()
        print(f"Updated note on project '{proj['slug']}'")
    conn.close()


def cmd_depend(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    t = resolve_ticket(conn, proj["id"], args.ticket_id, proj["slug"])
    new_deps = [int(x.strip()) for x in args.on.split(",")]
    for d in new_deps:
        resolve_ticket(conn, proj["id"], d, proj["slug"])
    existing = json.loads(t["depends_on"] or "[]")
    merged = list(set(existing + new_deps))
    tickets = conn.execute("SELECT * FROM tickets WHERE project_id=?", (proj["id"],)).fetchall()
    if has_cycle(tickets, t["num"], merged):
        conn.close()
        fail(
            "Circular dependency detected.",
            suggestions=["Remove one of the dependency links to break the cycle."],
        )
    conn.execute("UPDATE tickets SET depends_on=? WHERE id=?", (json.dumps(sorted(merged)), t["id"]))
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    conn.commit()
    print(f"Ticket #{t['num']} now depends on: {sorted(merged)}")
    conn.close()


def cmd_undepend(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    t = resolve_ticket(conn, proj["id"], args.ticket_id, proj["slug"])
    dep_id = int(args.dep_id)
    resolve_ticket(conn, proj["id"], dep_id, proj["slug"])

    existing = json.loads(t["depends_on"] or "[]")
    if dep_id not in existing:
        conn.close()
        fail(
            f"Ticket #{t['num']} does not depend on ticket #{dep_id}.",
            suggestions=["Run `agentplan status <project>` to review current dependencies."],
        )

    updated = [d for d in existing if d != dep_id]
    conn.execute("UPDATE tickets SET depends_on=? WHERE id=?", (json.dumps(updated), t["id"]))
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    conn.commit()
    print(f"Removed dependency #{dep_id} from ticket #{t['num']}.")
    conn.close()


def cmd_remove(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    if args.ticket:
        t = resolve_ticket(conn, proj["id"], args.ticket, proj["slug"])
        tnum = t["num"]
        conn.execute("DELETE FROM tickets WHERE id=?", (t["id"],))
        # Clean up dangling deps
        others = conn.execute(
            "SELECT id, depends_on FROM tickets WHERE project_id=?", (proj["id"],)
        ).fetchall()
        for o in others:
            deps = json.loads(o["depends_on"] or "[]")
            if tnum in deps:
                deps.remove(tnum)
                conn.execute("UPDATE tickets SET depends_on=? WHERE id=?", (json.dumps(deps), o["id"]))
        conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
        conn.commit()
        print(f"Removed ticket #{tnum}: {t['title']}")
    else:
        slug = proj["slug"]
        conn.execute("DELETE FROM projects WHERE id=?", (proj["id"],))
        conn.commit()
        print(f"Removed project '{slug}'")
    conn.close()


def cmd_history(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    ticket = resolve_ticket(conn, proj["id"], args.ticket_id, proj["slug"])
    rows = conn.execute(
        "SELECT old_state, new_state, changed_at FROM ticket_history WHERE ticket_id=? ORDER BY id",
        (ticket["id"],),
    ).fetchall()
    if not rows:
        print(f"No history found for ticket #{ticket['num']}.")
        conn.close()
        return
    print(f"History for {proj['slug']} ticket #{ticket['num']}: {ticket['title']}")
    for row in rows:
        old_state = row["old_state"] if row["old_state"] is not None else "-"
        print(f"  {row['changed_at']} | {old_state} -> {row['new_state']}")
    conn.close()


def cmd_hook_add(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    conn.execute(
        "INSERT INTO hooks (project_id, event, hook_type, target, created_at) VALUES (?,?,?,?,?)",
        (proj["id"], args.event, args.hook_type, args.target, _now()),
    )
    hook_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    print(f"Added hook #{hook_id} to project '{proj['slug']}' ({args.hook_type} {args.event}).")
    conn.close()


def cmd_hook_list(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    hooks = conn.execute(
        "SELECT id, event, hook_type, target, created_at FROM hooks WHERE project_id=? ORDER BY id",
        (proj["id"],),
    ).fetchall()
    if not hooks:
        print("No hooks found.")
        conn.close()
        return
    for h in hooks:
        print(f"{h['id']}: [{h['event']}] {h['hook_type']} -> {h['target']}")
    conn.close()


def cmd_hook_remove(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    deleted = conn.execute(
        "DELETE FROM hooks WHERE project_id=? AND id=?",
        (proj["id"], args.hook_id),
    ).rowcount
    if not deleted:
        conn.close()
        fail(f"Hook #{args.hook_id} not found for project '{proj['slug']}'.")
    conn.commit()
    print(f"Removed hook #{args.hook_id} from project '{proj['slug']}'.")
    conn.close()


def cmd_version(_args):
    print(f"agentplan {__version__}")

def cmd_dashboard(args):
    import socket
    import subprocess

    port = args.port

    if getattr(args, "stop", False):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            in_use = s.connect_ex(("127.0.0.1", port)) == 0
        if not in_use:
            print(f"No dashboard running on port {port}")
            return
        try:
            result = subprocess.run(
                ["/usr/sbin/lsof" if os.path.exists("/usr/sbin/lsof") else "lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True,
                check=False,
            )
            pids = []
            for line in (result.stdout or "").splitlines():
                line = line.strip()
                if line.isdigit():
                    pids.append(int(line))

            if not pids:
                print(f"No dashboard process found on port {port}")
                return

            for pid in pids:
                try:
                    os.kill(pid, 15)
                except ProcessLookupError:
                    continue
            print("Dashboard stopped")
        except Exception as e:
            print(f"Error stopping dashboard: {e}")
        return

    try:
        from agentplan.dashboard import run_dashboard
    except ImportError:
        print('Error: Flask not installed. Run: pip install agentplan[dashboard]', file=__import__('sys').stderr)
        __import__("sys").exit(1)

    if getattr(args, "background", False):
        import sys
        if not hasattr(os, "fork"):
            print("Error: --background requires a POSIX system (macOS/Linux). On Windows, run the dashboard in a separate terminal.", file=sys.stderr)
            sys.exit(1)
        pid = os.fork()
        if pid > 0:
            print(f"Dashboard running in background (pid {pid}) at http://{args.host}:{args.port}")
            print(f"Stop with: agentplan dashboard --stop")
            return
        # Child process: detach from terminal
        os.setsid()
        sys.stdin.close()
        devnull = open(os.devnull, "w")
        sys.stdout = devnull
        sys.stderr = devnull
        run_dashboard(host=args.host, port=args.port, open_browser=False)
        return

    run_dashboard(host=args.host, port=args.port, open_browser=getattr(args, "open_browser", False))



def _get_plugin_dir():
    """Get the path to bundled plugin files inside the installed package."""
    return os.path.join(os.path.dirname(__file__), "plugins")


def _install_plugin(source_dir, dest_dir, label):
    """Copy plugin files from package to destination."""
    import shutil
    if not os.path.isdir(source_dir):
        print(f"  ✗ Plugin files not found at {source_dir}")
        return False
    if os.path.exists(dest_dir):
        shutil.rmtree(dest_dir)
    shutil.copytree(source_dir, dest_dir)
    print(f"  ✓ Installed agentplan plugin to {dest_dir}")
    return True


def _setup_claude_marketplace(source_dir):
    """Set up agentplan as a local Claude Code marketplace and install the plugin."""
    import shutil
    import subprocess

    marketplace_dir = os.path.expanduser("~/.agentplan/marketplace")
    plugin_dest = os.path.join(marketplace_dir, "agentplan")

    if not os.path.isdir(source_dir):
        print(f"  ✗ Plugin files not found at {source_dir}")
        return False

    # Copy plugin files into marketplace directory
    os.makedirs(marketplace_dir, exist_ok=True)
    if os.path.exists(plugin_dest):
        shutil.rmtree(plugin_dest)
    shutil.copytree(source_dir, plugin_dest)

    # Create marketplace manifest
    manifest_dir = os.path.join(marketplace_dir, ".claude-plugin")
    os.makedirs(manifest_dir, exist_ok=True)
    manifest = {
        "name": "agentplan",
        "description": "Agentplan plugin marketplace",
        "owner": {"name": "agentplan", "email": ""},
        "plugins": [{
            "name": "agentplan",
            "description": "Asana for AI agents — task management, ticket tracking, and autonomous work loops",
            "version": __version__,
            "source": "./agentplan",
            "author": {"name": "agentplan", "email": ""},
        }],
    }
    with open(os.path.join(manifest_dir, "marketplace.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"  ✓ Plugin files staged at {marketplace_dir}")

    # Register marketplace (idempotent — re-add updates it)
    try:
        subprocess.run(
            ["claude", "plugin", "marketplace", "add", marketplace_dir, "--scope", "user"],
            capture_output=True, text=True, check=True,
        )
        print("  ✓ Registered agentplan marketplace")
    except FileNotFoundError:
        print("  ✗ 'claude' CLI not found — is Claude Code installed?")
        return False
    except subprocess.CalledProcessError as e:
        # Already added is fine
        if "already" not in (e.stderr or "").lower():
            print(f"  ⚠ Marketplace registration: {(e.stderr or '').strip()}")

    # Install plugin from marketplace
    try:
        result = subprocess.run(
            ["claude", "plugin", "install", "agentplan@agentplan", "--scope", "user"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print("  ✓ Installed agentplan plugin in Claude Code")
        else:
            stderr = (result.stderr or "").strip()
            if "already" in stderr.lower():
                # Update instead
                subprocess.run(
                    ["claude", "plugin", "update", "agentplan@agentplan"],
                    capture_output=True, text=True,
                )
                print("  ✓ Updated agentplan plugin in Claude Code")
            else:
                print(f"  ⚠ Plugin install: {stderr}")
                return False
    except Exception as e:
        print(f"  ⚠ Could not install plugin: {e}")
        return False

    return True


def cmd_setup(args):
    tool = getattr(args, "tool", None)
    install = getattr(args, "install", False)
    plugin_dir = _get_plugin_dir()

    if install or tool:
        # Auto-install mode
        installed = False
        if tool == "claude" or (install and tool is None):
            src = os.path.join(plugin_dir, "claude-code")
            if _setup_claude_marketplace(src):
                installed = True
                print("  → Restart Claude Code to load the plugin.")
                print("  → Try: /agentplan:plan to create a project from chat.\n")

        if tool == "codex" or (install and tool is None):
            src = os.path.join(plugin_dir, "codex")
            dst = os.path.expanduser("~/.codex/skills/agentplan")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if _install_plugin(src, dst, "Codex"):
                installed = True
                print("  → Codex will load the skill automatically.\n")

        if tool == "openclaw" or (install and tool is None):
            src = os.path.join(plugin_dir, "claude-code")
            dst = os.path.expanduser("~/.openclaw/workspace/skills/agentplan")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if _install_plugin(src, dst, "OpenClaw"):
                installed = True
                print("  → OpenClaw will load the skill automatically.\n")

        if installed:
            return
        elif tool:
            print(f"\n  ✗ Failed to install agentplan plugin for {tool}.\n")
            return

    header = """
  ┌──────────────────────────────────────────────────────────┐
  │  agentplan — Asana for AI Agents                         │
  │                                                          │
  │  Step 1: pip install agentplan          ✓ done           │
  │  Step 2: Install the plugin (run one of the below)       │
  │  Step 3: Tell your AI to plan something!                 │
  └──────────────────────────────────────────────────────────┘

  Install the plugin for your AI tool:

    agentplan setup claude       # installs to ~/.claude/plugins/
    agentplan setup codex        # installs to ~/.codex/skills/
    agentplan setup openclaw     # installs to ~/.openclaw/workspace/skills/

  Quick start: tell your AI "plan a new project" and it handles the rest.
"""
    print(header)


def cmd_completion(args):
    scripts = {
        "bash": _completion_bash_script,
        "zsh": _completion_zsh_script,
        "fish": _completion_fish_script,
    }
    print(scripts[args.shell](), end="")


def cmd_internal_complete(args):
    suggestions = _completion_suggestions(args.words, args.current)
    print("\n".join(sorted(set(suggestions))))


def cmd_subtask_add(args):
    _validate_len(args.title, MAX_TITLE_LEN, "Subtask title")
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    ticket = resolve_ticket(conn, proj["id"], args.ticket_id, proj["slug"])
    num = _next_subtask_num(conn, ticket["id"])
    conn.execute(
        "INSERT INTO subtasks (ticket_id, num, title) VALUES (?,?,?)",
        (ticket["id"], num, args.title),
    )
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    conn.commit()
    print(f"Added subtask #{num} to ticket #{ticket['num']}: {args.title}")
    conn.close()


def cmd_subtask_done(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    ticket = resolve_ticket(conn, proj["id"], args.ticket_id, proj["slug"])
    subtask = resolve_subtask(conn, ticket["id"], args.subtask_id, ticket["num"], proj["slug"])
    conn.execute(
        "UPDATE subtasks SET status='done', completed_at=? WHERE id=?",
        (_now(), subtask["id"]),
    )
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    conn.commit()
    print(f"✓ Subtask #{subtask['num']} on ticket #{ticket['num']}: {subtask['title']} → done")
    conn.close()


def cmd_subtask_list(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    ticket = resolve_ticket(conn, proj["id"], args.ticket_id, proj["slug"])
    subtasks = conn.execute(
        "SELECT * FROM subtasks WHERE ticket_id=? ORDER BY num",
        (ticket["id"],),
    ).fetchall()
    if not subtasks:
        print(f"No subtasks found for ticket #{ticket['num']}.")
        conn.close()
        return
    for s in subtasks:
        icon = "✓" if s["status"] == "done" else "○"
        print(f"  {icon} {s['num']}. {s['title']}")
    conn.close()


def cmd_role_list(_args):
    conn = _ensure(get_connection())
    roles = db_list_roles(conn)
    if not roles:
        print("No roles found.")
        conn.close()
        return

    print("id  name      description")
    for role in roles:
        print(f"{role.id:<3} {role.name:<9} {role.description or ''}")
    conn.close()


def cmd_role_add(args):
    conn = _ensure(get_connection())
    try:
        role = db_create_role(conn, args.name, args.description)
        print(f"Added role '{role.name}'.")
    except Exception as e:
        conn.close()
        fail(f"Could not add role '{args.name}': {e}")
    conn.close()


def cmd_role_remove(args):
    conn = _ensure(get_connection())
    deleted = db_delete_role(conn, args.name)
    if not deleted:
        conn.close()
        fail(f"Role '{args.name}' not found.")
    print(f"Removed role '{args.name}'.")
    conn.close()


def cmd_role_update(args):
    if args.new_name is None and args.description is None:
        fail(
            "No updates provided.",
            suggestions=["Use at least one of: `--name`, `--description`."],
        )
    conn = _ensure(get_connection())
    role = db_update_role(
        conn,
        args.name,
        new_name=args.new_name,
        new_description=args.description,
    )
    if not role:
        conn.close()
        fail(f"Role '{args.name}' not found.")
    print(f"Updated role '{role.name}'.")
    conn.close()


def _validate_agent_command_template_or_fail(command_template):
    template = (command_template or "").strip()
    placeholder_pattern = re.compile(r"(\{\{(?:ticket|project|ticket_id)\}\}|\{(?:ticket|project|ticket_id)\})")
    if placeholder_pattern.search(template):
        return
    fail(
        "Agent command template must include '{{ticket}}' placeholder (or {project}/{ticket_id} placeholder variants).",
        suggestions=["Example: --command 'codex exec {{ticket}}'"],
    )


def _warn_if_command_missing(command_template):
    template = (command_template or "").strip()
    if not template:
        return
    try:
        argv = shlex.split(template)
    except ValueError:
        return
    if not argv:
        return
    base_cmd = argv[0]
    if shutil.which(base_cmd) is None:
        print(
            f"Warning: command '{base_cmd}' not found on PATH. Agent was saved, but execution may fail.",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Agent registry commands (ticket #10)
# ---------------------------------------------------------------------------

def cmd_agent_add(args):
    """Register a new agent with command template and optional role assignments."""
    command_template = getattr(args, "command_template", None)
    if command_template is None:
        command_template = getattr(args, "command", None)
    _validate_agent_command_template_or_fail(command_template)
    conn = _ensure(get_connection())
    roles = [r.strip() for r in args.roles.split(",")] if args.roles else []
    # Validate roles exist
    for rname in roles:
        if not db_get_role(conn, rname):
            conn.close()
            fail(f"Role '{rname}' not found. Add it first with: agentplan role add {rname}")
    try:
        agent = db_create_agent(conn, args.name, command_template, role_names=roles, priority=getattr(args, "priority", 0))
    except sqlite3.IntegrityError:
        conn.close()
        raise CliError(f"Agent '{args.name}' already exists.")
    _warn_if_command_missing(command_template)
    role_str = ", ".join(agent["roles"]) if agent["roles"] else "(none)"
    print(f"Added agent '{agent['name']}' with roles: {role_str}")
    conn.close()


def cmd_agent_list(_args):
    """List all registered agents with their command templates and role mappings."""
    conn = _ensure(get_connection())
    agents = db_list_agents(conn)
    conn.close()
    if not agents:
        print("No agents registered.")
        return
    print(f"{'id':<4} {'name':<20} {'roles':<30} command_template")
    for a in agents:
        roles_str = ", ".join(a["roles"]) if a["roles"] else "(none)"
        print(f"{a['id']:<4} {a['name']:<20} {roles_str:<30} {a['command_template']}")


def cmd_agent_remove(args):
    """Remove a registered agent from the system."""
    conn = _ensure(get_connection())
    if not db_delete_agent(conn, args.name):
        conn.close()
        fail(f"Agent '{args.name}' not found.")
    print(f"Removed agent '{args.name}'.")
    conn.close()


def cmd_agent_update(args):
    """Update an agent's name, command template, roles, or priority."""
    command_template = getattr(args, "command_template", None)
    if command_template is None:
        command_template = getattr(args, "command", None)
    if args.new_name is None and command_template is None and args.roles is None and args.priority is None:
        fail("No updates provided.", suggestions=["Use --name, --command, --roles, or --priority."])
    conn = _ensure(get_connection())
    role_names = None
    if args.roles is not None:
        role_names = [r.strip() for r in args.roles.split(",")] if args.roles else []
        for rname in role_names:
            if not db_get_role(conn, rname):
                conn.close()
                fail(f"Role '{rname}' not found.")
    if command_template is not None:
        _validate_agent_command_template_or_fail(command_template)
    try:
        agent = db_update_agent(
            conn, args.name,
            new_name=args.new_name,
            new_command_template=command_template,
            role_names=role_names,
            new_priority=getattr(args, "priority", None),
        )
    except sqlite3.IntegrityError:
        conn.close()
        conflict_name = args.new_name or args.name
        raise CliError(f"Agent '{conflict_name}' already exists.")
    if not agent:
        conn.close()
        fail(f"Agent '{args.name}' not found.")
    if command_template is not None:
        _warn_if_command_missing(command_template)
    print(f"Updated agent '{agent['name']}'.")
    conn.close()


def cmd_issue_import(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    repo = (args.repo or os.environ.get("GITHUB_REPOSITORY") or "").strip()
    token = (args.token or os.environ.get("GITHUB_TOKEN") or "").strip()
    if not repo:
        conn.close()
        fail("GitHub repo is required (use --repo or GITHUB_REPOSITORY).")
    if "/" not in repo:
        conn.close()
        fail("GitHub repo must be in OWNER/REPO format.")
    if not token:
        conn.close()
        fail("GitHub token is required (use --token or GITHUB_TOKEN).")

    try:
        issues = _fetch_github_issues(repo, args.label, args.state, token)
    except urllib.error.HTTPError as exc:
        conn.close()
        fail(f"GitHub API request failed: HTTP {exc.code}.")
    except urllib.error.URLError as exc:
        conn.close()
        fail(f"GitHub API request failed: {exc.reason}.")

    imported = 0
    updated = 0
    skipped = 0
    for issue in issues:
        issue_number = int(issue.get("number"))
        issue_title = (issue.get("title") or "").strip() or f"Issue #{issue_number}"
        issue_body = (issue.get("body") or "").strip()
        issue_url = issue.get("html_url") or f"https://github.com/{repo}/issues/{issue_number}"
        issue_state = (issue.get("state") or "open").strip().lower()

        existing = conn.execute(
            """
            SELECT * FROM issue_sync_map
            WHERE project_id=? AND repo=? AND issue_number=?
            """,
            (proj["id"], repo, issue_number),
        ).fetchone()

        description = (
            f"Imported from GitHub issue {repo}#{issue_number}\n"
            f"Source: {issue_url}\n\n"
            f"{issue_body}"
        ).strip()
        tags = _parse_tags(f"github-issue,github:{repo.lower()},issue:{issue_number}")

        if existing:
            if args.dry_run:
                print(f"[dry-run] would sync existing issue #{issue_number} -> ticket #{existing['ticket_id']}")
                skipped += 1
                continue
            conn.execute(
                """
                UPDATE tickets
                SET title=?, description=?
                WHERE id=?
                """,
                (issue_title, description, existing["ticket_id"]),
            )
            conn.execute(
                """
                UPDATE issue_sync_map
                SET issue_state=?, issue_url=?, last_synced_at=?
                WHERE id=?
                """,
                (issue_state, issue_url, _now(), existing["id"]),
            )
            updated += 1
            continue

        if args.dry_run:
            print(f"[dry-run] would import issue #{issue_number}: {issue_title}")
            skipped += 1
            continue

        next_num = _next_ticket_num(conn, proj["id"])
        conn.execute(
            """
            INSERT INTO tickets (
                project_id, num, title, description, status, priority, tags, depends_on, notes, created_at
            )
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (proj["id"], next_num, issue_title, description, "pending", "none", tags, "[]", None, _now()),
        )
        ticket_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            """
            INSERT INTO issue_sync_map (project_id, ticket_id, repo, issue_number, issue_url, issue_state, last_synced_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (proj["id"], ticket_id, repo, issue_number, issue_url, issue_state, _now()),
        )
        _record_ticket_history(conn, ticket_id, None, "imported-from-github-issue")
        imported += 1

    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (_now(), proj["id"]))
    conn.commit()
    conn.close()
    print(
        f"Issue import complete for {repo} label={args.label}: "
        f"imported={imported}, updated={updated}, skipped={skipped}."
    )


def _ensure_command_available(binary, install_hint):
    if shutil.which(binary):
        return
    fail(
        f"Required command '{binary}' is not available on PATH.",
        suggestions=[install_hint],
    )


def cmd_pr_automate(args):
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    ticket = resolve_ticket(conn, proj["id"], args.ticket_id, proj["slug"])
    conn.close()

    project_dir = (proj["dir"] if "dir" in proj.keys() else None) or ""
    if not project_dir:
        fail(f"No directory linked to project '{proj['slug']}'.")

    _ensure_command_available("git", "Install git and retry.")
    _ensure_command_available("gh", "Install GitHub CLI (`gh`) and authenticate with `gh auth login`.")

    branch_part = _slugify_branch_part(ticket["title"], f"ticket-{ticket['num']}")
    branch_name = f"agentplan/{proj['slug']}/t{ticket['num']}-{branch_part}"[:120]
    commit_msg = f"agentplan({proj['slug']}): ticket #{ticket['num']} {ticket['title']}"
    pr_title = f"[agentplan] {proj['slug']} ticket #{ticket['num']}: {ticket['title']}"
    pr_body = "\n".join(
        [
            "## Summary",
            f"- Project: `{proj['slug']}`",
            f"- Ticket: `#{ticket['num']}`",
            f"- Title: {ticket['title']}",
            "",
            "## Agentplan Context",
            f"- Generated by `agentplan pr automate {proj['slug']} --ticket-id {ticket['num']}`",
        ]
    )

    commands = [
        ["git", "checkout", "-B", branch_name],
        ["git", "add", "-A"],
        ["git", "diff", "--cached", "--quiet"],
    ]
    if args.dry_run:
        print("PR automation plan:")
        print(f"- branch: {branch_name}")
        print(f"- commit: {commit_msg}")
        print(f"- title: {pr_title}")
        print(f"- base: {args.base}")
        for cmd in commands:
            print(f"  $ {' '.join(shlex.quote(c) for c in cmd)}")
        print(f"  $ gh pr list --head {branch_name} --state open --json number,url")
        print("  $ gh pr create|edit ...")
        return

    checkout = _run_cmd(commands[0], cwd=project_dir)
    if checkout.returncode != 0:
        fail(f"git checkout failed: {(checkout.stderr or checkout.stdout or '').strip()}")

    add = _run_cmd(commands[1], cwd=project_dir)
    if add.returncode != 0:
        fail(f"git add failed: {(add.stderr or add.stdout or '').strip()}")

    staged_check = _run_cmd(commands[2], cwd=project_dir, capture_output=False)
    has_staged_changes = staged_check.returncode != 0
    if has_staged_changes:
        commit = _run_cmd(["git", "commit", "-m", commit_msg], cwd=project_dir)
        if commit.returncode != 0:
            fail(f"git commit failed: {(commit.stderr or commit.stdout or '').strip()}")
        push = _run_cmd(["git", "push", "-u", "origin", branch_name], cwd=project_dir)
        if push.returncode != 0:
            fail(f"git push failed: {(push.stderr or push.stdout or '').strip()}")

    existing_pr = _run_cmd(
        ["gh", "pr", "list", "--head", branch_name, "--state", "open", "--json", "number,url"],
        cwd=project_dir,
    )
    if existing_pr.returncode != 0:
        fail(f"gh pr list failed: {(existing_pr.stderr or existing_pr.stdout or '').strip()}")

    pr_rows = []
    try:
        pr_rows = json.loads((existing_pr.stdout or "[]").strip() or "[]")
    except json.JSONDecodeError:
        pr_rows = []

    if pr_rows:
        number = str(pr_rows[0]["number"])
        edit = _run_cmd(
            ["gh", "pr", "edit", number, "--title", pr_title, "--body", pr_body, "--base", args.base],
            cwd=project_dir,
        )
        if edit.returncode != 0:
            fail(f"gh pr edit failed: {(edit.stderr or edit.stdout or '').strip()}")
        print(f"Updated PR #{number} for branch '{branch_name}'.")
        return

    create = _run_cmd(
        ["gh", "pr", "create", "--title", pr_title, "--body", pr_body, "--base", args.base, "--head", branch_name],
        cwd=project_dir,
    )
    if create.returncode != 0:
        fail(f"gh pr create failed: {(create.stderr or create.stdout or '').strip()}")
    print(f"Created PR for branch '{branch_name}'.")


def cmd_artifact_status(args):
    """Show the status and metadata of a project's runtime chain-state artifact."""
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    data = _load_runtime_artifact(conn, proj, "chain-state")
    if not data:
        conn.close()
        print("No runtime artifact found.")
        return
    if not data.get("ok"):
        conn.close()
        print(f"Artifact status: invalid ({data.get('error')})")
        sys.exit(1)
    payload = data["payload"]
    print(f"Artifact path: {data['path']}")
    print(f"Artifact sha256: {data['sha256']}")
    print(f"Chain status: {payload.get('status') or 'unknown'}")
    print(f"Recorded at: {payload.get('recorded_at') or '(none)'}")
    conn.close()


def cmd_artifact_verify(args):
    """Verify the integrity of a project's runtime chain-state artifact."""
    conn = _ensure(get_connection())
    proj = resolve_project(conn, args.project)
    data = _load_runtime_artifact(conn, proj, "chain-state")
    conn.close()
    if not data:
        fail("No runtime artifact found for this project.")
    if not data.get("ok"):
        fail(f"Runtime artifact integrity check failed: {data.get('error')}")
    print(f"Integrity OK: {data['path']} ({data['sha256']})")


# CLI parser
# ---------------------------------------------------------------------------

class FriendlyArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        fail(
            f"Invalid arguments: {message}",
            suggestions=["Run `agentplan --help` to see available commands and options."],
        )


_DEPRECATED_COMMANDS = frozenset({
    "chain", "route", "spawn-terminal", "monitor-process", "auto-tag",
    "reap", "role", "hook", "agent",
})


def _add_deprecated_parser(sub, name, **kwargs):
    """Add a subparser that is completely hidden from --help output."""
    p = sub.add_parser(name, **kwargs)
    # Remove from the choices display list so it doesn't appear in --help
    if hasattr(sub, '_choices_actions'):
        sub._choices_actions = [
            a for a in sub._choices_actions if a.dest != name
        ]
    return p


def build_parser():
    p = FriendlyArgumentParser(prog="agentplan", description="Project management CLI for AI agents")
    p.add_argument("--version", action="version", version=f"agentplan {__version__}")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("init", help="Initialize database")
    sub.add_parser("version", help="Show version")

    dash_p = sub.add_parser("dashboard", help="Launch web dashboard")
    dash_p.add_argument("--port", type=int, default=5001, help="Port to listen on (default: 5001)")
    dash_p.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    dash_p.add_argument("--open", action="store_true", dest="open_browser", help="Open dashboard in default browser")
    dash_p.add_argument("--stop", action="store_true", help="Stop the running dashboard")
    dash_p.add_argument("--background", action="store_true", help="Run dashboard as a background process")

    c = sub.add_parser("create", help="Create a project")
    c.add_argument("title")
    c.add_argument("--ticket", action="append", help="Add inline ticket(s)")
    c.add_argument("--notes")
    c.add_argument("--dir", help="Link this project to a local directory")
    c.add_argument("--timeout", type=int, help="Default per-ticket timeout in seconds for this project")
    c.add_argument("--space", default="default", help="Space to assign this project to (defaults to 'default')")

    prj = sub.add_parser("project", help="Update project settings")
    prj.add_argument("project", help="Project slug or name")
    prj.add_argument("--dir", help="Set or update the linked local directory")
    prj.add_argument("--space", help="Move project to a different space (by slug)")

    sp = sub.add_parser("space", help="Manage spaces")
    sps = sp.add_subparsers(dest="space_command")
    sc = sps.add_parser("create")
    sc.add_argument("slug", help="Space slug (lowercase, no spaces)")
    sc.add_argument("--title", help="Display title for the space")
    sc.add_argument("--description", help="Description of the space")
    sl = sps.add_parser("list")
    # No arguments for list command
    sh = sps.add_parser("show")
    sh.add_argument("slug", help="Space slug")
    su = sps.add_parser("update")
    su.add_argument("slug", help="Space slug")
    su.add_argument("--title", help="New display title for the space")
    su.add_argument("--description", help="New description for the space")
    sd = sps.add_parser("delete")
    sd.add_argument("slug", help="Space slug")
    sd.add_argument("--force", action="store_true", help="Skip confirmation prompt")

    doc = sub.add_parser("doc", help="Manage documents in spaces")
    docs = doc.add_subparsers(dest="doc_command")
    da = docs.add_parser("add", help="Create a new document")
    da.add_argument("space", help="Space slug")
    da.add_argument("title", help="Document title")
    da.add_argument("--file", help="Copy content from existing file (--file <path>)")
    da.add_argument("--stdin", action="store_true", help="Read content from stdin")
    dl = docs.add_parser("list", help="List all documents in a space")
    dl.add_argument("space", help="Space slug")
    ds = docs.add_parser("show", help="Print raw markdown content of a document")
    ds.add_argument("space", help="Space slug")
    ds.add_argument("filename", help="Filename (e.g., 'my-doc.md')")
    ds.add_argument("--force", action="store_true", help="Show even if file is large (>1MB)")
    dp = docs.add_parser("path", help="Print the absolute file path of a document")
    dp.add_argument("space", help="Space slug")
    dp.add_argument("filename", help="Filename (e.g., 'my-doc.md')")
    dr = docs.add_parser("remove", help="Delete a document from a space")
    dr.add_argument("space", help="Space slug")
    dr.add_argument("filename", help="Filename (e.g., 'my-doc.md')")
    dr.add_argument("--force", action="store_true", help="Skip confirmation prompt")

    tp = sub.add_parser("ticket", help="Manage tickets")
    ts = tp.add_subparsers(dest="ticket_command")
    a = ts.add_parser("add")
    a.add_argument("project"); a.add_argument("title"); a.add_argument("--desc"); a.add_argument("--depends"); a.add_argument("--notes")
    a.add_argument("--tag", help="Comma-separated tags (e.g. security,css)")
    a.add_argument("--priority", choices=PRIORITY_CHOICES[:-1], default="none")
    a.add_argument("--due", help="Due date in YYYY-MM-DD format")
    a.add_argument("--timeout", type=int, help="Per-ticket timeout in seconds")
    a.add_argument("--role", help="Assign a registered role to this ticket (must exist in role registry)")
    a.add_argument("--model", choices=MODEL_TIER_CHOICES, default="auto", help="Model tier: auto, light, standard, reasoning")
    u = ts.add_parser("update")
    u.add_argument("project"); u.add_argument("ticket_id")
    u.add_argument("--title"); u.add_argument("--notes"); u.add_argument("--depends")
    u.add_argument("--priority", choices=PRIORITY_CHOICES)
    e = ts.add_parser("edit")
    e.add_argument("project"); e.add_argument("ticket_id")
    e.add_argument("--title"); e.add_argument("--desc"); e.add_argument("--tag")
    e.add_argument("--priority", choices=PRIORITY_CHOICES)
    e.add_argument("--due", help="Due date in YYYY-MM-DD format")
    e.add_argument("--timeout", type=int, help="Per-ticket timeout in seconds")
    e.add_argument("--model", choices=MODEL_TIER_CHOICES, help="Model tier: auto, light, standard, reasoning")
    d = ts.add_parser("done")
    d.add_argument("project"); d.add_argument("ticket_ids", nargs="+", help="Ticket IDs (space or comma-separated, e.g. 1 2 or 1,2,3)")
    d.add_argument("--note", help="Optional closing note/reason")
    d.add_argument("--agent", help="Agent name marking ticket done (e.g. dash)")
    s = ts.add_parser("skip")
    s.add_argument("project"); s.add_argument("ticket_ids", nargs="+")
    st = ts.add_parser("start")
    st.add_argument("project"); st.add_argument("ticket_id")
    st.add_argument("--agent", help="Agent name starting ticket (e.g. dash)")
    tb = ts.add_parser("block")
    tb.add_argument("project"); tb.add_argument("ticket_id")
    tb.add_argument("--reason", help="Optional reason for blocking")
    tf = ts.add_parser("fail")
    tf.add_argument("project"); tf.add_argument("ticket_id")
    tf.add_argument("--reason", help="Optional reason for failing")
    tr = ts.add_parser("review")
    tr.add_argument("project"); tr.add_argument("ticket_id")
    tr.add_argument("--reason", help="Optional reason for review")
    tl = ts.add_parser("list")
    tl.add_argument("project"); tl.add_argument("--status", choices=["pending", "done", "in-progress", "skipped", "blocked", "failed", "needs-review", "all"])

    n = sub.add_parser("next", help="Show next unblocked tickets")
    n.add_argument("project", nargs="?")
    n.add_argument("--format", choices=["compact", "json"], default="compact")
    n.add_argument("--tag", help="Filter by a single tag")
    n.add_argument("--space", help="Show next unblocked tickets from projects in a specific space")

    clm = sub.add_parser("claim", help="Atomically claim the next unblocked ticket in a project")
    clm.add_argument("project")
    clm.add_argument("--agent", help="Agent name claiming ticket (e.g. dash)")
    clm.add_argument("--tag", help="Filter by a single tag")
    clm.add_argument("--timeout", type=int, help="Claim timeout in seconds")

    rp = _add_deprecated_parser(sub, "reap")
    rp.add_argument("project", help="Project slug or name")

    ss = sub.add_parser("status", help="Project status")
    ss.add_argument("project", nargs="?")
    ss.add_argument("--format", choices=["compact", "full", "json"], default="full")
    ss.add_argument("--tag", help="Filter tickets by a single tag")
    ss.add_argument("--space", help="Scope status to projects in a specific space (by slug)")

    srch = sub.add_parser("search", help="Search doc content and ticket titles/descriptions across all projects")
    srch.add_argument("query")
    srch.add_argument("--space", help="Filter by space slug")
    srch.add_argument("--docs-only", action="store_true", help="Search only doc content")
    srch.add_argument("--tickets-only", action="store_true", help="Search only tickets")

    ls = sub.add_parser("list", help="List projects")
    ls.add_argument("--status", choices=["active", "completed", "paused", "abandoned", "archived", "all"], default="active")
    ls.add_argument("--all", action="store_true", help="Include archived projects")
    ls.add_argument("--space", help="Filter projects by space slug")

    ar = sub.add_parser("archive", help="Archive a completed or abandoned project")
    ar.add_argument("project")

    at = sub.add_parser("attach", help="Attach file or URL")
    at.add_argument("project"); at.add_argument("label"); at.add_argument("location"); at.add_argument("--ticket")

    lg = sub.add_parser("log", help="Add log entry")
    lg.add_argument("project")
    lg.add_argument("parts", nargs="+", help="Either '<message>' or '<ticket_id> <message>'")
    lg.add_argument("--ticket")

    cl = sub.add_parser("close", help="Close a project")
    cl.add_argument("project"); cl.add_argument("--abandon", action="store_true")

    nt = sub.add_parser("note", help="Set note on project or ticket")
    nt.add_argument("project"); nt.add_argument("text"); nt.add_argument("--ticket")

    dp = sub.add_parser("depend", help="Add ticket dependencies")
    dp.add_argument("project"); dp.add_argument("ticket_id"); dp.add_argument("--on", required=True)

    udp = sub.add_parser("undepend", help="Remove a ticket dependency")
    udp.add_argument("project"); udp.add_argument("ticket_id"); udp.add_argument("--on", dest="dep_id", required=True, metavar="dep_id")

    rm = sub.add_parser("remove", help="Remove project or ticket")
    rm.add_argument("project"); rm.add_argument("--ticket")

    hs = sub.add_parser("history", help="Show ticket state transition history")
    hs.add_argument("project")
    hs.add_argument("ticket_id")

    ctx = sub.add_parser("context", help="Show ticket context block")
    ctx.add_argument("project")
    ctx.add_argument("ticket_id", nargs="?")
    ctx.add_argument("--agent", help="Agent name for command templates")

    rt = _add_deprecated_parser(sub, "route")
    rt.add_argument("project")
    rt.add_argument("ticket_id")
    rt.add_argument("--default-agent", dest="default_agent", help="Fallback agent name if no role match")
    rt.add_argument("--terminal", action="store_true", help="Spawn the routed agent command in a visible terminal")
    rt.add_argument("--monitor", action="store_true", help="When used with --terminal, monitor the spawned PID in a background thread")
    rt.add_argument("--terminal-pref", choices=sorted(TERMINAL_CHOICES), help="Terminal preference override (or use AGENTPLAN_TERMINAL)")

    stp = _add_deprecated_parser(sub, "spawn-terminal")
    stp.add_argument("command")
    stp.add_argument("--title", help="Optional terminal title")
    stp.add_argument("--terminal-pref", choices=sorted(TERMINAL_CHOICES), help="Terminal preference override (or use AGENTPLAN_TERMINAL)")

    mp = _add_deprecated_parser(sub, "monitor-process")
    mp.add_argument("project")
    mp.add_argument("ticket_id", type=int)
    mp.add_argument("pid", type=int)
    mp.add_argument("--timeout", type=int, default=3600, help="Timeout in seconds (default: 3600)")

    atg = _add_deprecated_parser(sub, "auto-tag")
    atg.add_argument("project")
    atg.add_argument("--ticket", type=int, help="Tag only a specific ticket number")
    atg.add_argument("--dry-run", action="store_true", help="Show predicted tags without writing changes")
    atg.add_argument("--agent", help="Use a specific configured agent name")

    ch = _add_deprecated_parser(sub, "chain")
    ch.add_argument("project")
    ch.add_argument("--status", action="store_true", help="Show chain status")
    ch.add_argument("--stop", action="store_true", help="Request stop after current ticket")
    ch.add_argument("--default-agent", dest="default_agent", help="Fallback agent name if no role match")
    ch.add_argument("--max-tickets", type=int, help="Maximum tickets to process this run")
    ch.add_argument("--timeout", type=int, help="Override per-ticket timeout in seconds")
    ch.add_argument("--max-runtime", type=int, help="Maximum runtime in seconds for this run")
    ch.add_argument("--max-budget-usd", dest="max_budget", type=float, help="Budget cap in USD for this run")
    ch.add_argument(
        "--cost-per-ticket-usd",
        dest="cost_per_ticket",
        type=float,
        default=0.0,
        help="Estimated USD cost per processed ticket (used with --max-budget-usd)",
    )

    issue = sub.add_parser("issue", help="GitHub issue adapters")
    issue_sub = issue.add_subparsers(dest="issue_command")
    issue_import = issue_sub.add_parser("import", help="Import GitHub issues into project tickets")
    issue_import.add_argument("project")
    issue_import.add_argument("--repo", help="GitHub repo in owner/repo format (defaults to GITHUB_REPOSITORY)")
    issue_import.add_argument("--label", default="agentplan", help="GitHub label to sync (default: agentplan)")
    issue_import.add_argument("--state", choices=["open", "closed", "all"], default="open")
    issue_import.add_argument("--token", help="GitHub token (defaults to GITHUB_TOKEN)")
    issue_import.add_argument("--dry-run", action="store_true")

    pr = sub.add_parser("pr", help="Pull request automation")
    pr_sub = pr.add_subparsers(dest="pr_command")
    pr_auto = pr_sub.add_parser("automate", help="Create/update branch, commit and PR for one ticket")
    pr_auto.add_argument("project")
    pr_auto.add_argument("--ticket-id", required=True)
    pr_auto.add_argument("--base", default="main", help="PR base branch (default: main)")
    pr_auto.add_argument("--dry-run", action="store_true")

    artifact = sub.add_parser("artifact", help="Runtime artifacts")
    artifact_sub = artifact.add_subparsers(dest="artifact_command")
    artifact_status = artifact_sub.add_parser("status", help="Show runtime artifact summary")
    artifact_status.add_argument("project")
    artifact_verify = artifact_sub.add_parser("verify", help="Verify runtime artifact integrity")
    artifact_verify.add_argument("project")

    sp = sub.add_parser("subtask", help="Manage ticket subtasks")
    sps = sp.add_subparsers(dest="subtask_command")
    sa = sps.add_parser("add")
    sa.add_argument("project"); sa.add_argument("ticket_id"); sa.add_argument("title")
    sd = sps.add_parser("done")
    sd.add_argument("project"); sd.add_argument("ticket_id"); sd.add_argument("subtask_id")
    sl = sps.add_parser("list")
    sl.add_argument("project"); sl.add_argument("ticket_id")

    rp = _add_deprecated_parser(sub, "role")
    rps = rp.add_subparsers(dest="role_command")
    rl = rps.add_parser("list", help=argparse.SUPPRESS)
    ra = rps.add_parser("add", help=argparse.SUPPRESS)
    ra.add_argument("name")
    ra.add_argument("--description")
    rr = rps.add_parser("remove", help=argparse.SUPPRESS)
    rr.add_argument("name")
    ru = rps.add_parser("update", help=argparse.SUPPRESS)
    ru.add_argument("name")
    ru.add_argument("--name", dest="new_name")
    ru.add_argument("--description")

    hp = _add_deprecated_parser(sub, "hook")
    hps = hp.add_subparsers(dest="hook_command")
    ha = hps.add_parser("add", help=argparse.SUPPRESS)
    ha.add_argument("project")
    ha.add_argument("--event", choices=["on-complete"], default="on-complete")
    ha.add_argument("--type", dest="hook_type", choices=["webhook", "command", "chain"], required=True)
    ha.add_argument("--target", required=True)
    hl = hps.add_parser("list", help=argparse.SUPPRESS)
    hl.add_argument("project")
    hr = hps.add_parser("remove", help=argparse.SUPPRESS)
    hr.add_argument("project")
    hr.add_argument("hook_id", type=int)

    agp = _add_deprecated_parser(sub, "agent")
    agps = agp.add_subparsers(dest="agent_command")
    ag_add = agps.add_parser("add", help=argparse.SUPPRESS)
    ag_add.add_argument("name", help="Agent name")
    ag_add.add_argument("--command", dest="command_template", required=True, help="Command template (e.g. 'claude -p {ticket}')")
    ag_add.add_argument("--roles", help="Comma-separated list of role names to assign")
    ag_add.add_argument("--role", dest="roles", help=argparse.SUPPRESS)
    ag_add.add_argument("--priority", type=int, default=0, help="Agent routing priority (lower number wins)")
    ag_list = agps.add_parser("list", help=argparse.SUPPRESS)
    ag_rm = agps.add_parser("remove", help=argparse.SUPPRESS)
    ag_rm.add_argument("name")
    ag_upd = agps.add_parser("update", help=argparse.SUPPRESS)
    ag_upd.add_argument("name")
    ag_upd.add_argument("--name", dest="new_name", help="New name")
    ag_upd.add_argument("--command", dest="command_template", help="New command template")
    ag_upd.add_argument("--roles", help="New comma-separated roles (replaces existing)")
    ag_upd.add_argument("--priority", type=int, help="New routing priority (lower number wins)")

    setup_p = sub.add_parser("setup", help="Show getting-started instructions for your AI tool")
    setup_p.add_argument("tool", nargs="?", choices=["claude", "codex", "openclaw"], help="AI tool to configure (default: show all)")

    cp = sub.add_parser("completion", help="Print shell completion script")
    cp.add_argument("shell", choices=COMPLETION_SHELLS)

    internal = sub.add_parser("__complete", help=argparse.SUPPRESS)
    internal.add_argument("shell", choices=COMPLETION_SHELLS, help=argparse.SUPPRESS)
    internal.add_argument("current", help=argparse.SUPPRESS)
    internal.add_argument("words", nargs="*", help=argparse.SUPPRESS)

    # Set custom metavar to hide deprecated commands from the choices display
    visible_cmds = [name for name in sub.choices if name not in _DEPRECATED_COMMANDS and name != "__complete"]
    for action in p._subparsers._group_actions:
        if hasattr(action, 'choices') and action.choices is sub.choices:
            action.metavar = "{" + ",".join(visible_cmds) + "}"

    return p


DISPATCH = {
    "init": cmd_init, "create": cmd_create, "project": cmd_project, "next": cmd_next, "claim": cmd_claim, "reap": cmd_reap, "status": cmd_status,
    "list": cmd_list, "search": cmd_search, "attach": cmd_attach, "log": cmd_log, "close": cmd_close,
    "archive": cmd_archive,
    "note": cmd_note, "depend": cmd_depend, "undepend": cmd_undepend, "remove": cmd_remove, "history": cmd_history, "version": cmd_version, "dashboard": cmd_dashboard,
    "setup": cmd_setup, "completion": cmd_completion, "__complete": cmd_internal_complete,
    "context": cmd_context,
    "route": cmd_route,
    "spawn-terminal": cmd_spawn_terminal,
    "monitor-process": cmd_monitor_process,
    "auto-tag": cmd_auto_tag,
    "chain": cmd_chain,
}

TICKET_DISPATCH = {
    "add": cmd_ticket_add, "done": cmd_ticket_done, "skip": cmd_ticket_skip,
    "start": cmd_ticket_start, "block": cmd_ticket_block, "fail": cmd_ticket_fail,
    "review": cmd_ticket_review, "list": cmd_ticket_list,
    "update": cmd_ticket_update, "edit": cmd_ticket_edit,
}

SUBTASK_DISPATCH = {
    "add": cmd_subtask_add,
    "done": cmd_subtask_done,
    "list": cmd_subtask_list,
}

SPACE_DISPATCH = {
    "create": cmd_space_create,
    "list": cmd_space_list,
    "show": cmd_space_show,
    "update": cmd_space_update,
    "delete": cmd_space_delete,
}

DOC_DISPATCH = {
    "add": cmd_doc_add,
    "list": cmd_doc_list,
    "show": cmd_doc_show,
    "path": cmd_doc_path,
    "remove": cmd_doc_remove,
}

ROLE_DISPATCH = {
    "list": cmd_role_list,
    "add": cmd_role_add,
    "remove": cmd_role_remove,
    "update": cmd_role_update,
}

HOOK_DISPATCH = {
    "add": cmd_hook_add,
    "list": cmd_hook_list,
    "remove": cmd_hook_remove,
}

AGENT_DISPATCH = {
    "add": cmd_agent_add,
    "list": cmd_agent_list,
    "remove": cmd_agent_remove,
    "update": cmd_agent_update,
}

ISSUE_DISPATCH = {
    "import": cmd_issue_import,
}

PR_DISPATCH = {
    "automate": cmd_pr_automate,
}

ARTIFACT_DISPATCH = {
    "status": cmd_artifact_status,
    "verify": cmd_artifact_verify,
}


def main():
    parser = build_parser()
    try:
        args = parser.parse_args()
        if not args.command:
            # Check if this is a first-time user (no projects yet)
            try:
                conn = get_connection()
                projects = conn.execute("SELECT COUNT(*) as cnt FROM projects").fetchone()
                conn.close()
                if projects and projects["cnt"] == 0:
                    print("  Welcome to agentplan — Asana for AI Agents\n")
                    print("  Get started: agentplan setup\n")
                    return
            except Exception:
                pass
            parser.print_help()
            fail(
                "No command provided.",
                suggestions=["Run `agentplan --help` to see available commands."],
            )
        if args.command == "ticket":
            if not getattr(args, "ticket_command", None):
                parser.parse_args(["ticket", "--help"])
            TICKET_DISPATCH[args.ticket_command](args)
        elif args.command == "subtask":
            if not getattr(args, "subtask_command", None):
                parser.parse_args(["subtask", "--help"])
            SUBTASK_DISPATCH[args.subtask_command](args)
        elif args.command == "space":
            if not getattr(args, "space_command", None):
                parser.parse_args(["space", "--help"])
            SPACE_DISPATCH[args.space_command](args)
        elif args.command == "doc":
            if not getattr(args, "doc_command", None):
                parser.parse_args(["doc", "--help"])
            DOC_DISPATCH[args.doc_command](args)
        elif args.command == "role":
            if not getattr(args, "role_command", None):
                parser.parse_args(["role", "--help"])
            ROLE_DISPATCH[args.role_command](args)
        elif args.command == "hook":
            if not getattr(args, "hook_command", None):
                parser.parse_args(["hook", "--help"])
            HOOK_DISPATCH[args.hook_command](args)
        elif args.command == "agent":
            if not getattr(args, "agent_command", None):
                parser.parse_args(["agent", "--help"])
            AGENT_DISPATCH[args.agent_command](args)
        elif args.command == "issue":
            if not getattr(args, "issue_command", None):
                parser.parse_args(["issue", "--help"])
            ISSUE_DISPATCH[args.issue_command](args)
        elif args.command == "pr":
            if not getattr(args, "pr_command", None):
                parser.parse_args(["pr", "--help"])
            PR_DISPATCH[args.pr_command](args)
        elif args.command == "artifact":
            if not getattr(args, "artifact_command", None):
                parser.parse_args(["artifact", "--help"])
            ARTIFACT_DISPATCH[args.artifact_command](args)
        else:
            DISPATCH[args.command](args)
    except CliError as e:
        print(f"Error: {e.message}", file=sys.stderr)
        for suggestion in e.suggestions:
            print(f"Suggestion: {suggestion}", file=sys.stderr)
        sys.exit(e.exit_code)
    except SystemExit:
        raise
    except Exception as e:
        print("Error: Unexpected failure while running agentplan.", file=sys.stderr)
        print(f"Suggestion: Re-run with valid arguments or `agentplan --help`. ({e})", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
