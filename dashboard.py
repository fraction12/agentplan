#!/usr/bin/env python3
"""Read-only web dashboard for agentplan projects and tickets."""

import json
import os
from collections import defaultdict

from flask import Flask, abort, render_template_string, request, url_for

from db import get_connection

STATUS_ORDER = ["pending", "in-progress", "blocked", "done", "skipped"]
STATUS_LABELS = {
    "pending": "todo",
    "in-progress": "in-progress",
    "blocked": "blocked",
    "done": "done",
    "skipped": "skipped",
}

INDEX_TEMPLATE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>agentplan dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  </head>
  <body class="bg-light">
    <main class="container py-4">
      <div class="d-flex justify-content-between align-items-center mb-3">
        <h1 class="h3 m-0">agentplan dashboard</h1>
        <span class="text-muted small">Read-only viewer</span>
      </div>

      {% if projects %}
      <div class="row g-3">
      {% for project in projects %}
        <div class="col-12 col-md-6">
          <div class="card h-100 shadow-sm">
            <div class="card-body">
              <div class="d-flex justify-content-between align-items-start mb-2">
                <h2 class="h5 mb-0"><a class="text-decoration-none" href="{{ url_for('project_detail', project_id=project.id) }}">{{ project.title }}</a></h2>
                <span class="badge text-bg-secondary">{{ project.slug }}</span>
              </div>
              <p class="text-muted small mb-2">Status: {{ project.status }}</p>
              <div class="mb-2 small">
                <strong>{{ project.done_count }}/{{ project.ticket_count }}</strong> done
                {% if project.ticket_count %}({{ project.progress_pct }}%){% endif %}
              </div>
              <div class="progress mb-3" role="progressbar" aria-label="{{ project.title }} progress" aria-valuenow="{{ project.progress_pct }}" aria-valuemin="0" aria-valuemax="100">
                <div class="progress-bar" style="width: {{ project.progress_pct }}%"></div>
              </div>
              <div class="d-flex flex-wrap gap-1">
                {% for status, count in project.breakdown.items() %}
                <span class="badge rounded-pill text-bg-light border">{{ status }}: {{ count }}</span>
                {% endfor %}
              </div>
            </div>
          </div>
        </div>
      {% endfor %}
      </div>
      {% else %}
      <div class="alert alert-secondary">No projects found.</div>
      {% endif %}
    </main>
  </body>
</html>
"""

PROJECT_TEMPLATE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ project.title }} · agentplan dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  </head>
  <body class="bg-light">
    <main class="container py-4">
      <div class="d-flex justify-content-between align-items-center mb-3">
        <h1 class="h3 m-0">{{ project.title }}</h1>
        <a href="{{ url_for('index') }}" class="btn btn-sm btn-outline-secondary">All projects</a>
      </div>

      <p class="text-muted">{{ project.slug }} · {{ done_count }}/{{ total_count }} done</p>

      <form method="get" class="row g-2 mb-4">
        <div class="col-12 col-sm-4">
          <input type="text" class="form-control" name="status" placeholder="status (e.g. done)" value="{{ filters.status }}">
        </div>
        <div class="col-12 col-sm-4">
          <input type="text" class="form-control" name="priority" placeholder="priority (e.g. high)" value="{{ filters.priority }}">
        </div>
        <div class="col-12 col-sm-4">
          <input type="text" class="form-control" name="tag" placeholder="tag (e.g. refactor)" value="{{ filters.tag }}">
        </div>
        <div class="col-12 d-flex gap-2">
          <button class="btn btn-primary btn-sm" type="submit">Apply filters</button>
          <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('project_detail', project_id=project.id) }}">Reset</a>
        </div>
      </form>

      {% for status in status_order %}
      <section class="mb-4">
        <h2 class="h5 mb-2">{{ status_labels[status] }} <span class="text-muted">({{ grouped[status]|length }})</span></h2>
        {% if grouped[status] %}
        <div class="list-group">
          {% for ticket in grouped[status] %}
          <article class="list-group-item">
            <div class="d-flex justify-content-between align-items-start gap-3">
              <div>
                <div><strong><a class="text-decoration-none" href="{{ url_for('ticket_detail', project_id=project.id, ticket_num=ticket.num) }}">#{{ ticket.num }} {{ ticket.title }}</a></strong></div>
                {% if ticket.description %}<div class="small mt-1">{{ ticket.description }}</div>{% endif %}
                {% if ticket.tags %}<div class="small text-muted mt-1">tags: {{ ticket.tags|join(', ') }}</div>{% endif %}
                {% if ticket.dependencies %}<div class="small text-muted">depends on: {{ ticket.dependencies|join(', ') }}</div>{% endif %}
              </div>
              <div class="text-end">
                <span class="badge text-bg-dark">{{ ticket.priority }}</span>
              </div>
            </div>
          </article>
          {% endfor %}
        </div>
        {% else %}
          <p class="text-muted small mb-0">No tickets.</p>
        {% endif %}
      </section>
      {% endfor %}
    </main>
  </body>
</html>
"""

TICKET_TEMPLATE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>#{{ ticket.num }} {{ ticket.title }} · {{ project.title }} · agentplan dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  </head>
  <body class="bg-light">
    <main class="container py-4">
      <div class="d-flex justify-content-between align-items-center mb-3">
        <h1 class="h4 m-0">#{{ ticket.num }} {{ ticket.title }}</h1>
        <a href="{{ url_for('project_detail', project_id=project.id) }}" class="btn btn-sm btn-outline-secondary">Back to project</a>
      </div>

      <div class="card shadow-sm mb-3">
        <div class="card-body">
          <div class="d-flex flex-wrap gap-2 mb-2">
            <span class="badge text-bg-primary">{{ ticket.status }}</span>
            <span class="badge text-bg-dark">priority: {{ ticket.priority }}</span>
            {% if ticket.tags %}
              {% for tag in ticket.tags %}
              <span class="badge rounded-pill text-bg-light border">{{ tag }}</span>
              {% endfor %}
            {% endif %}
          </div>
          <h2 class="h6">Description</h2>
          {% if ticket.description %}
          <p class="mb-0">{{ ticket.description }}</p>
          {% else %}
          <p class="text-muted mb-0">No description.</p>
          {% endif %}
          {% if ticket.close_note %}
          <hr>
          <h2 class="h6">Close notes</h2>
          <p class="mb-0">{{ ticket.close_note }}</p>
          {% endif %}
        </div>
      </div>

      <div class="row g-3 mb-3">
        <div class="col-12 col-md-6">
          <div class="card h-100 shadow-sm">
            <div class="card-body">
              <h2 class="h6">Dependencies</h2>
              <div class="small text-muted mb-1">blocked by</div>
              {% if blocked_by %}
              <ul class="mb-3">
                {% for dep in blocked_by %}
                <li><a href="{{ url_for('ticket_detail', project_id=project.id, ticket_num=dep.num) }}">#{{ dep.num }} {{ dep.title }}</a></li>
                {% endfor %}
              </ul>
              {% else %}
              <p class="text-muted small">None.</p>
              {% endif %}

              <div class="small text-muted mb-1">blocks</div>
              {% if blocks %}
              <ul class="mb-0">
                {% for dep in blocks %}
                <li><a href="{{ url_for('ticket_detail', project_id=project.id, ticket_num=dep.num) }}">#{{ dep.num }} {{ dep.title }}</a></li>
                {% endfor %}
              </ul>
              {% else %}
              <p class="text-muted small mb-0">None.</p>
              {% endif %}
            </div>
          </div>
        </div>

        <div class="col-12 col-md-6">
          <div class="card h-100 shadow-sm">
            <div class="card-body">
              <h2 class="h6">Subtasks</h2>
              {% if subtasks %}
              <ul class="list-group list-group-flush">
                {% for subtask in subtasks %}
                <li class="list-group-item px-0 d-flex justify-content-between align-items-center">
                  <span>#{{ subtask.num }} {{ subtask.title }}</span>
                  <span class="badge {{ 'text-bg-success' if subtask.status == 'done' else 'text-bg-secondary' }}">{{ subtask.status }}</span>
                </li>
                {% endfor %}
              </ul>
              {% else %}
              <p class="text-muted small mb-0">No subtasks.</p>
              {% endif %}
            </div>
          </div>
        </div>
      </div>

      <div class="card shadow-sm">
        <div class="card-body">
          <h2 class="h6">History / audit log</h2>
          {% if history %}
          <ul class="list-group list-group-flush">
            {% for item in history %}
            <li class="list-group-item px-0">
              <div class="small text-muted">{{ item.changed_at }}</div>
              <div>{{ item.message }}</div>
            </li>
            {% endfor %}
          </ul>
          {% else %}
          <p class="text-muted small mb-0">No history yet.</p>
          {% endif %}
        </div>
      </div>
    </main>
  </body>
</html>
"""


def _db_path():
    return os.environ.get("AGENTPLAN_DB", os.path.expanduser("~/.openclaw/workspace/agentplan.db"))


def _fetch_projects_with_stats(conn):
    projects = conn.execute("SELECT id, slug, title, status FROM projects ORDER BY updated_at DESC, id DESC").fetchall()
    rows = conn.execute("SELECT project_id, status, COUNT(*) AS c FROM tickets GROUP BY project_id, status").fetchall()

    counts = defaultdict(lambda: defaultdict(int))
    for row in rows:
        counts[row["project_id"]][row["status"]] = row["c"]

    out = []
    for p in projects:
        project_counts = counts[p["id"]]
        breakdown = {
            "todo": int(project_counts.get("pending", 0)),
            "in-progress": int(project_counts.get("in-progress", 0)),
            "blocked": int(project_counts.get("blocked", 0)),
            "done": int(project_counts.get("done", 0)),
            "skipped": int(project_counts.get("skipped", 0)),
        }
        total = sum(breakdown.values())
        done = breakdown["done"] + breakdown["skipped"]
        progress = int(round((done / total) * 100)) if total else 0
        out.append(
            {
                "id": p["id"],
                "slug": p["slug"],
                "title": p["title"],
                "status": p["status"],
                "breakdown": breakdown,
                "ticket_count": total,
                "done_count": done,
                "progress_pct": progress,
            }
        )
    return out


def _ticket_matches(ticket, status_filter, priority_filter, tag_filter):
    if status_filter:
        normalized_status = "pending" if status_filter == "todo" else status_filter
        if ticket["status"] != normalized_status:
            return False
    if priority_filter and (ticket["priority"] or "none").lower() != priority_filter:
        return False
    if tag_filter:
        tags = {t.strip().lower() for t in (ticket["tags"] or "").split(",") if t.strip()}
        if tag_filter not in tags:
            return False
    return True


def _normalize_ticket(row):
    tags = [t.strip() for t in (row["tags"] or "").split(",") if t.strip()]
    try:
        dependencies = json.loads(row["depends_on"] or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        dependencies = []
    return {
        "id": row["id"],
        "num": row["num"],
        "title": row["title"],
        "description": row["description"] or "",
        "status": row["status"],
        "priority": row["priority"] or "none",
        "tags": tags,
        "dependencies": dependencies,
    }


def create_app():
    app = Flask(__name__)

    @app.route("/")
    def index():
        conn = get_connection(_db_path())
        try:
            projects = _fetch_projects_with_stats(conn)
        finally:
            conn.close()
        return render_template_string(INDEX_TEMPLATE, projects=projects)

    @app.route("/project/<int:project_id>")
    def project_detail(project_id):
        status_filter = request.args.get("status", "").strip().lower()
        priority_filter = request.args.get("priority", "").strip().lower()
        tag_filter = request.args.get("tag", "").strip().lower()

        conn = get_connection(_db_path())
        try:
            project = conn.execute("SELECT id, slug, title, status FROM projects WHERE id=?", (project_id,)).fetchone()
            if not project:
                abort(404)
            rows = conn.execute(
                """
                SELECT id, num, title, description, status, priority, tags, depends_on
                FROM tickets
                WHERE project_id=?
                ORDER BY num
                """,
                (project_id,),
            ).fetchall()
        finally:
            conn.close()

        grouped = {s: [] for s in STATUS_ORDER}
        done_count = 0
        for row in rows:
            ticket = _normalize_ticket(row)
            if ticket["status"] in ("done", "skipped"):
                done_count += 1
            is_blocked = bool(ticket["dependencies"]) and ticket["status"] == "pending"
            group_key = "blocked" if is_blocked else ticket["status"]
            if group_key not in grouped:
                grouped[group_key] = []
            if _ticket_matches(ticket, status_filter, priority_filter, tag_filter):
                grouped[group_key].append(ticket)

        return render_template_string(
            PROJECT_TEMPLATE,
            project=project,
            grouped=grouped,
            status_order=STATUS_ORDER,
            status_labels=STATUS_LABELS,
            done_count=done_count,
            total_count=len(rows),
            filters={"status": status_filter, "priority": priority_filter, "tag": tag_filter},
        )


    @app.route("/project/<int:project_id>/ticket/<int:ticket_num>")
    def ticket_detail(project_id, ticket_num):
        conn = get_connection(_db_path())
        try:
            project = conn.execute("SELECT id, slug, title, status FROM projects WHERE id=?", (project_id,)).fetchone()
            if not project:
                abort(404)

            row = conn.execute(
                """
                SELECT id, num, title, description, status, priority, tags, depends_on, close_note
                FROM tickets
                WHERE project_id=? AND num=?
                """,
                (project_id, ticket_num),
            ).fetchone()
            if not row:
                abort(404)

            ticket = _normalize_ticket(row)
            ticket["close_note"] = row["close_note"] or ""

            subtasks = conn.execute(
                "SELECT num, title, status FROM subtasks WHERE ticket_id=? ORDER BY num",
                (ticket["id"],),
            ).fetchall()

            dep_nums = ticket["dependencies"]
            blocked_by = []
            if dep_nums:
                placeholders = ",".join("?" for _ in dep_nums)
                blocked_rows = conn.execute(
                    f"SELECT num, title FROM tickets WHERE project_id=? AND num IN ({placeholders}) ORDER BY num",
                    (project_id, *dep_nums),
                ).fetchall()
                blocked_by = [dict(r) for r in blocked_rows]

            project_ticket_rows = conn.execute(
                "SELECT num, title, depends_on FROM tickets WHERE project_id=? AND id!=? ORDER BY num",
                (project_id, ticket["id"]),
            ).fetchall()
            blocks = []
            for r in project_ticket_rows:
                try:
                    ticket_deps = json.loads(r["depends_on"] or "[]")
                except (TypeError, ValueError, json.JSONDecodeError):
                    ticket_deps = []
                if ticket["num"] in ticket_deps:
                    blocks.append({"num": r["num"], "title": r["title"]})

            history_rows = conn.execute(
                "SELECT changed_at, old_state, new_state FROM ticket_history WHERE ticket_id=? ORDER BY id DESC",
                (ticket["id"],),
            ).fetchall()
            log_rows = conn.execute(
                "SELECT created_at, entry FROM log WHERE ticket_id=? ORDER BY id DESC",
                (ticket["id"],),
            ).fetchall()
        finally:
            conn.close()

        history = []
        for r in history_rows:
            old_state = r["old_state"] or "(none)"
            history.append({"changed_at": r["changed_at"], "message": f"state: {old_state} → {r['new_state']}"})
        for r in log_rows:
            history.append({"changed_at": r["created_at"], "message": r["entry"]})
        history.sort(key=lambda item: item["changed_at"], reverse=True)

        return render_template_string(
            TICKET_TEMPLATE,
            project=project,
            ticket=ticket,
            subtasks=subtasks,
            blocked_by=blocked_by,
            blocks=blocks,
            history=history,
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
