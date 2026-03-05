"""Dashboard templates and display constants."""

from agentplan.db import VALID_TICKET_STATES

_STATUS_PREFERRED = ["pending", "in-progress", "blocked", "needs-review", "failed", "done", "skipped"]
STATUS_ORDER = [state for state in _STATUS_PREFERRED if state in VALID_TICKET_STATES]
STATUS_LABELS = {state: ("todo" if state == "pending" else state) for state in STATUS_ORDER}
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

INDEX_TEMPLATE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>agentplan mission control</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
      :root {
        --font-heading: 'Playfair Display', Georgia, serif;
        --font-body: 'Inter', ui-sans-serif, sans-serif;
        --font-mono: 'JetBrains Mono', ui-monospace, monospace;
        --fs-h1: 2rem;
        --fs-h2: 1.25rem;
        --fs-card-title: 1rem;
        --fs-nav: 0.875rem;
        --fs-body: 0.875rem;
        --fs-small: 0.75rem;
        --fs-button: 0.75rem;
        --fs-mono: 0.8rem;
        --fw-h1: 700;
        --fw-h2: 600;
        --fw-card-title: 600;
        --fw-nav: 500;
        --fw-body: 400;
        --fw-small: 400;
        --fw-button: 500;
        --fw-mono: 400;

        --color-bg: #0a0e1a;
        --color-bg-alt: #0f1420;
        --color-panel: #151b2b;
        --color-panel-soft: #1b2236;
        --color-text: #e2e8f0;
        --color-muted: #8892a8;
        --color-border: rgba(255, 255, 255, 0.08);
        --color-shadow: rgba(0, 0, 0, 0.42);
        --color-high: #ef4444;
        --color-medium: #f97316;
        --color-low: #8892a8;
        --color-due-overdue: #f87171;

        --status-done: #22c55e;
        --status-in-progress: #3b82f6;
        --status-blocked: #f59e0b;
        --status-pending: #94a3b8;
        --status-needs-review: #facc15;
        --status-failed: #ef4444;
        --status-todo: var(--status-pending);
        --status-skipped: #64748b;
      }

      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: var(--font-body);
        background: var(--color-bg);
        color: var(--color-text);
      }

      .page {
        max-width: 1200px;
        margin: 0 auto;
        padding: 2rem;
      }

      .topbar {
        display: grid;
        grid-template-columns: 1fr auto 1fr;
        align-items: center;
        margin-bottom: 20px;
        padding: 14px 16px;
        background: rgba(255, 255, 255, 0.02);
        border: 1px solid var(--color-border);
        border-radius: 14px;
      }
      .brand { font-family: var(--font-body); font-weight: var(--fw-card-title); font-size: var(--fs-card-title); letter-spacing: -0.01em; }
      .topbar-nav { display: inline-flex; gap: 8px; justify-self: center; }
      .topbar-right { display: flex; align-items: center; gap: 12px; color: var(--color-muted); font-family: var(--font-body); font-weight: var(--fw-body); font-size: var(--fs-body); justify-self: end; }
      .clock {
        font-family: var(--font-body);
        font-weight: var(--fw-body);
        font-size: var(--fs-body);
        color: var(--color-text);
      }
      .top-link {
        color: var(--color-muted);
        border: 1px solid var(--color-border);
        border-radius: 10px;
        padding: 6px 10px;
        text-decoration: none;
        font-family: var(--font-body);
        font-weight: var(--fw-nav);
        font-size: var(--fs-nav);
      }
      .top-link:hover { color: var(--color-text); background: rgba(255,255,255,0.05); }
      .top-link.active { color: var(--color-text); font-weight: var(--fw-nav); text-decoration: underline; }
      .sse-status {
        display: inline-flex;
        align-items: center;
        gap: 6px;
      }
      .status-dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: #64748b;
      }
      .status-dot.connected { background: var(--status-done); box-shadow: 0 0 0 4px rgba(34, 197, 94, 0.15); }
      .status-dot.disconnected { background: #ef4444; box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.15); }

      .stats-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 14px;
        margin-bottom: 18px;
      }
      .stat-card {
        background: var(--color-panel);
        border: 1px solid var(--color-border);
        border-radius: 14px;
        box-shadow: 0 12px 36px var(--color-shadow);
        padding: 16px;
      }
      .stat-label {
        font-family: var(--font-body);
        font-weight: var(--fw-body);
        font-size: var(--fs-small);
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--color-muted);
      }
      .stat-value {
        margin-top: 8px;
        font-family: var(--font-mono);
        font-size: var(--fs-mono);
        font-weight: var(--fw-h1);
        line-height: 1;
      }

      .project-section-title { margin: 0 0 10px; font-family: var(--font-body); font-size: var(--fs-h2); font-weight: var(--fw-h2); letter-spacing: 0.02em; }
      .projects-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 14px;
      }
      .project-section { margin-bottom: 18px; }
      .toggle-row { margin-bottom: 12px; display: flex; justify-content: flex-end; }
      .toggle-label { display: inline-flex; align-items: center; gap: 8px; color: var(--color-muted); font-family: var(--font-body); font-size: var(--fs-small); font-weight: var(--fw-small); }
      .projects-grid.completed .project-card { padding: 12px; opacity: 0.9; }
      .project-link {
        display: block;
        color: inherit;
        text-decoration: none;
      }
      .project-card {
        background: var(--color-panel);
        border: 1px solid var(--color-border);
        border-radius: 14px;
        box-shadow: 0 12px 36px var(--color-shadow);
        padding: 16px;
        transition: transform 0.4s ease, border-color 0.4s ease, box-shadow 0.4s ease, opacity 0.3s ease;
      }
      .project-link:hover .project-card {
        transform: translateY(-1px);
        border-color: rgba(255,255,255,0.16);
      }
      .project-top {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 10px;
      }
      .project-title {
        margin: 0;
        font-family: var(--font-body);
        font-weight: var(--fw-card-title);
        font-size: var(--fs-card-title);
        line-height: 1.2;
      }
      .project-code {
        margin-top: 4px;
        font-family: var(--font-mono);
        font-size: var(--fs-mono);
        color: var(--color-muted);
      }

      .progress-ring {
        --ring-size: 56px;
        --ring-stroke: 3.6;
        --ring-progress: 0;
        --ring-track: rgba(255, 255, 255, 0.14);
        --ring-color: var(--status-in-progress);
        width: var(--ring-size);
        height: var(--ring-size);
        position: relative;
        flex-shrink: 0;
      }
      .progress-ring svg { width: 100%; height: 100%; transform: rotate(-90deg); }
      .progress-ring-track,
      .progress-ring-value { fill: none; stroke-width: var(--ring-stroke); }
      .progress-ring-track { stroke: var(--ring-track); }
      .progress-ring-value {
        stroke: var(--ring-color);
        stroke-linecap: round;
        stroke-dasharray: 100;
        stroke-dashoffset: calc(100 - var(--ring-progress));
        transition: stroke-dashoffset 420ms ease;
      }
      .progress-ring-label {
        position: absolute;
        inset: 0;
        display: grid;
        place-items: center;
        font-size: var(--fs-small);
        font-family: var(--font-mono);
      }

      .project-meta {
        margin-top: 10px;
        display: grid;
        gap: 7px;
      }
      .project-warning {
        margin-top: 6px;
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 2px 8px;
        border-radius: 999px;
        border: 1px solid rgba(245, 158, 11, 0.45);
        background: rgba(120, 53, 15, 0.35);
        color: #fde68a;
        font-size: var(--fs-small);
        font-family: var(--font-body);
      }
      .project-progress-text,
      .project-last-activity {
        font-family: var(--font-body);
        font-weight: var(--fw-body);
        font-size: var(--fs-small);
        color: var(--color-muted);
      }

      .dot-breakdown {
        display: flex;
        flex-wrap: wrap;
        gap: 8px 10px;
      }
      .dot-item {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        font-family: var(--font-body);
        font-weight: var(--fw-body);
        font-size: var(--fs-small);
        color: var(--color-muted);
      }
      .dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
      }
      .dot.pending { background: var(--status-pending); }
      .dot.in-progress { background: var(--status-in-progress); }
      .dot.blocked { background: var(--status-blocked); }
      .dot.needs-review { background: var(--status-needs-review); }
      .dot.failed { background: var(--status-failed); }
      .dot.done { background: var(--status-done); }
      .dot.skipped { background: var(--status-skipped); }

      .empty {
        border: 1px dashed var(--color-border);
        border-radius: 14px;
        padding: 24px;
        color: var(--color-muted);
      }

      @media (max-width: 980px) {
        .stats-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .projects-grid { grid-template-columns: 1fr; }
      }
    </style>
  </head>
  <body>
    <main class="page">
      <header class="topbar">
        <div class="brand">agentplan</div>
        <nav class="topbar-nav">
          <a class="top-link active" href="{{ url_for('index') }}">Home</a>
          <a class="top-link" href="{{ url_for('activity') }}">Activity</a>
          <a class="top-link" href="{{ url_for('agents') }}">Agents</a>
        </nav>
        <div class="topbar-right">
          <span id="live-clock" class="clock">--:--:--</span>
          <span class="sse-status"><span id="sse-dot" class="status-dot"></span><span id="sse-label">connecting…</span></span>
        </div>
      </header>

      <section class="stats-grid" id="stats-grid">
        <article class="stat-card"><div class="stat-label">Active Projects</div><div id="stat-active-projects" class="stat-value">{{ summary.active_projects }}</div></article>
        <article class="stat-card"><div class="stat-label">Tickets In Flight</div><div id="stat-tickets-in-flight" class="stat-value">{{ summary.tickets_in_flight }}</div></article>
        <article class="stat-card"><div class="stat-label">Completed Today</div><div id="stat-completed-today" class="stat-value">{{ summary.completed_today }}</div></article>
        <article class="stat-card"><div class="stat-label">Active Agents</div><div id="stat-active-agents" class="stat-value">{{ summary.active_agents }}</div></article>
      </section>

      {% if projects %}
      <div class="toggle-row">
        <label class="toggle-label"><input id="show-completed" type="checkbox"> Show completed</label>
      </div>

      <section class="project-section" id="active-section">
        <h2 class="project-section-title">Active Projects</h2>
        <section class="projects-grid" id="active-projects-grid">
          {% for project in active_projects %}
          <a class="project-link" href="{{ url_for('project_detail', slug=project.slug) }}" data-project-id="{{ project.id }}" data-project-status="{{ project.status }}">
            <article class="project-card">
              <div class="project-top">
                <div>
                  <h2 class="project-title">{{ project.title }}</h2>
                  <div class="project-code">{{ project.slug }}</div>
                </div>
                <div class="progress-ring" style="--ring-progress: {{ project.progress_pct }};" aria-hidden="true">
                  <svg viewBox="0 0 36 36">
                    <circle class="progress-ring-track" cx="18" cy="18" r="16"></circle>
                    <circle class="progress-ring-value" cx="18" cy="18" r="16"></circle>
                  </svg>
                  <span class="progress-ring-label project-progress-percent">{{ project.progress_pct }}%</span>
                </div>
              </div>
              <div class="project-meta">
                <div class="project-progress-text"><strong class="project-progress-done">{{ project.done_count }}</strong>/<span class="project-progress-total">{{ project.ticket_count }}</span> done</div>
                <div class="dot-breakdown project-breakdown">
                  {% for status in ["pending", "in-progress", "blocked", "needs-review", "failed", "done"] %}
                  <span class="dot-item"><span class="dot {{ status }}"></span><span class="dot-value" data-status="{{ status }}">{{ project.breakdown.get(status, 0) }}</span></span>
                  {% endfor %}
                </div>
                <div class="project-last-activity">Last activity: <span class="project-updated-at" data-timestamp="{{ project.updated_at or '' }}">{{ project.updated_at or "n/a" }}</span></div>
                {% if project.missing_directory %}
                <div class="project-warning" title="Linked directory is missing on disk">⚠ Missing directory</div>
                {% endif %}
              </div>
            </article>
          </a>
          {% endfor %}
        </section>
      </section>

      <section class="project-section" id="completed-section">
        <h2 class="project-section-title">Completed</h2>
        <section class="projects-grid completed" id="completed-projects-grid">
          {% for project in completed_projects %}
          <a class="project-link" href="{{ url_for('project_detail', slug=project.slug) }}" data-project-id="{{ project.id }}" data-project-status="{{ project.status }}">
            <article class="project-card">
              <div class="project-top">
                <div>
                  <h2 class="project-title">{{ project.title }}</h2>
                  <div class="project-code">{{ project.slug }}</div>
                </div>
                <div class="progress-ring" style="--ring-progress: {{ project.progress_pct }};" aria-hidden="true">
                  <svg viewBox="0 0 36 36">
                    <circle class="progress-ring-track" cx="18" cy="18" r="16"></circle>
                    <circle class="progress-ring-value" cx="18" cy="18" r="16"></circle>
                  </svg>
                  <span class="progress-ring-label project-progress-percent">{{ project.progress_pct }}%</span>
                </div>
              </div>
              <div class="project-meta">
                <div class="project-progress-text"><strong class="project-progress-done">{{ project.done_count }}</strong>/<span class="project-progress-total">{{ project.ticket_count }}</span> done</div>
                <div class="project-last-activity">Last activity: <span class="project-updated-at" data-timestamp="{{ project.updated_at or '' }}">{{ project.updated_at or "n/a" }}</span></div>
                {% if project.missing_directory %}
                <div class="project-warning" title="Linked directory is missing on disk">⚠ Missing directory</div>
                {% endif %}
              </div>
            </article>
          </a>
          {% endfor %}
        </section>
      </section>
{% else %}
      <div class="empty">No projects found.</div>
      {% endif %}
    </main>

    <script>
      const statusOrder = ["pending", "in-progress", "blocked", "needs-review", "failed", "done"];

      function setClock(ts) {
        const d = ts ? new Date(ts) : new Date();
        document.getElementById("live-clock").textContent = d.toLocaleTimeString();
      }

      function setConnection(isConnected, label) {
        const dot = document.getElementById("sse-dot");
        const text = document.getElementById("sse-label");
        dot.classList.remove("connected", "disconnected");
        dot.classList.add(isConnected ? "connected" : "disconnected");
        text.textContent = label;
      }

      function renderSummary(summary) {
        document.getElementById("stat-active-projects").textContent = summary.active_projects ?? 0;
        document.getElementById("stat-tickets-in-flight").textContent = summary.tickets_in_flight ?? 0;
        document.getElementById("stat-completed-today").textContent = summary.completed_today ?? 0;
        document.getElementById("stat-active-agents").textContent = summary.active_agents ?? 0;
      }

      function esc(v) {
        return String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
      }

      function formatRelative(ts) {
        if (!ts) return "n/a";
        const d = new Date(ts);
        if (Number.isNaN(d.valueOf())) return esc(ts);
        const now = new Date();
        const diffSec = Math.floor((now - d) / 1000);
        if (diffSec < 60) return "just now";
        if (diffSec < 3600) return `${Math.floor(diffSec / 60)} min ago`;
        if (diffSec < 6 * 3600) return `${Math.floor(diffSec / 3600)} hours ago`;
        const sameDay = now.toDateString() === d.toDateString();
        if (sameDay) return `Today at ${d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`;
        const y = new Date(now); y.setDate(now.getDate() - 1);
        if (y.toDateString() === d.toDateString()) return `Yesterday at ${d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`;
        return d.toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
      }

      function applyRelativeTimes() {
        document.querySelectorAll(".project-updated-at[data-timestamp]").forEach((node) => {
          node.textContent = formatRelative(node.dataset.timestamp || "");
        });
      }

      function projectCard(project, isCompleted) {
        const breakdown = project.breakdown || {};
        const breakdownHtml = isCompleted ? '' : `<div class="dot-breakdown project-breakdown">${statusOrder.map((status) => `<span class="dot-item"><span class="dot ${status}"></span><span class="dot-value" data-status="${status}">${breakdown[status] || 0}</span></span>`).join("")}</div>`;
        const warningHtml = project.missing_directory ? `<div class="project-warning" title="Linked directory is missing on disk">⚠ Missing directory</div>` : "";
        return `<a class="project-link" href="/project/${encodeURIComponent(project.slug)}" data-project-id="${project.id}" data-project-status="${esc(project.status || '')}"><article class="project-card"><div class="project-top"><div><h2 class="project-title">${esc(project.title)}</h2><div class="project-code">${esc(project.slug)}</div></div><div class="progress-ring" style="--ring-progress: ${project.progress_pct || 0};" aria-hidden="true"><svg viewBox="0 0 36 36"><circle class="progress-ring-track" cx="18" cy="18" r="16"></circle><circle class="progress-ring-value" cx="18" cy="18" r="16"></circle></svg><span class="progress-ring-label project-progress-percent">${project.progress_pct || 0}%</span></div></div><div class="project-meta"><div class="project-progress-text"><strong class="project-progress-done">${project.done_count || 0}</strong>/<span class="project-progress-total">${project.ticket_count || 0}</span> done</div>${breakdownHtml}<div class="project-last-activity">Last activity: <span class="project-updated-at" data-timestamp="${esc(project.updated_at || '')}">${formatRelative(project.updated_at)}</span></div>${warningHtml}</div></article></a>`;
      }

      function renderProjects(projects) {
        const showCompleted = document.getElementById("show-completed")?.checked;
        const visible = (projects || []);
        const active = visible.filter((p) => p.status !== "completed");
        const completed = visible.filter((p) => p.status === "completed");

        const activeGrid = document.getElementById("active-projects-grid");
        const completedGrid = document.getElementById("completed-projects-grid");
        if (activeGrid) activeGrid.innerHTML = active.map((p) => projectCard(p, false)).join("");
        const completedSection = document.getElementById("completed-section");
        if (completedSection) completedSection.style.display = showCompleted ? "" : "none";
        if (completedGrid) completedGrid.innerHTML = completed.map((p) => projectCard(p, true)).join("");
      }

      (function subscribe() {
        setClock();
        setInterval(() => setClock(), 1000);

        applyRelativeTimes();

        const completedToggle = document.getElementById("show-completed");
        if (completedToggle) completedToggle.addEventListener("change", () => renderProjects(window.__latestProjects || []));

        if (!window.EventSource) {
          setConnection(false, "SSE unsupported");
          return;
        }

        const source = new EventSource("{{ url_for('events') }}");

        source.addEventListener("open", () => {
          setConnection(true, "connected");
        });

        source.addEventListener("project_stats", (event) => {
          try {
            const payload = JSON.parse(event.data);
            renderSummary(payload.summary || {});
            window.__latestProjects = payload.projects || [];
            renderProjects(window.__latestProjects);
            setClock(payload.server_time || null);
            setConnection(true, "connected");
          } catch (_err) {
            setConnection(false, "parse error");
          }
        });

        source.onerror = () => {
          setConnection(false, "reconnecting…");
        };
      })();
    </script>
  </body>
</html>
"""

ACTIVITY_TEMPLATE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Live activity · agentplan dashboard</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
      :root {
        --font-heading: 'Playfair Display', Georgia, serif;
        --font-body: 'Inter', ui-sans-serif, sans-serif;
        --font-mono: 'JetBrains Mono', ui-monospace, monospace;
        --fs-h1: 2rem;
        --fs-h2: 1.25rem;
        --fs-card-title: 1rem;
        --fs-nav: 0.875rem;
        --fs-body: 0.875rem;
        --fs-small: 0.75rem;
        --fs-button: 0.75rem;
        --fs-mono: 0.8rem;
        --fw-h1: 700;
        --fw-h2: 600;
        --fw-card-title: 600;
        --fw-nav: 500;
        --fw-body: 400;
        --fw-small: 400;
        --fw-button: 500;
        --fw-mono: 400;

        --color-bg: #0a0e1a;
        --color-bg-alt: #0f1420;
        --color-panel: #151b2b;
        --color-panel-soft: #1b2236;
        --color-text: #e2e8f0;
        --color-muted: #8892a8;
        --color-border: rgba(255, 255, 255, 0.08);
        --color-shadow: rgba(0, 0, 0, 0.42);
        --color-high: #ef4444;
        --color-medium: #f97316;
        --color-low: #8892a8;
        --color-due-overdue: #f87171;

        --status-done: #22c55e;
        --status-in-progress: #3b82f6;
        --status-blocked: #f59e0b;
        --status-pending: #94a3b8;
        --status-needs-review: #facc15;
        --status-failed: #ef4444;
        --status-todo: var(--status-pending);
        --status-skipped: #64748b;
      }
      * { box-sizing: border-box; }
      body { margin: 0; font-family: var(--font-body); background: var(--color-bg); color: var(--color-text); }
      .page { max-width: 1200px; margin: 0 auto; padding: 2rem; }
      .topbar {
        display: grid;
        grid-template-columns: 1fr auto 1fr;
        align-items: center;
        margin-bottom: 20px;
        padding: 14px 16px;
        background: rgba(255, 255, 255, 0.02);
        border: 1px solid var(--color-border);
        border-radius: 14px;
      }
      .brand { font-family: var(--font-body); font-weight: var(--fw-card-title); font-size: var(--fs-card-title); letter-spacing: -0.01em; }
      .topbar-nav { display: inline-flex; gap: 8px; justify-self: center; }
      .topbar-right { display: flex; align-items: center; gap: 12px; color: var(--color-muted); font-family: var(--font-body); font-weight: var(--fw-body); font-size: var(--fs-body); justify-self: end; }
      .clock { font-family: var(--font-body); font-weight: var(--fw-body); font-size: var(--fs-body); color: var(--color-text); }
      .top-link {
        color: var(--color-muted);
        border: 1px solid var(--color-border);
        border-radius: 10px;
        padding: 6px 10px;
        text-decoration: none;
        font-family: var(--font-body);
        font-weight: var(--fw-nav);
        font-size: var(--fs-nav);
      }
      .top-link:hover { color: var(--color-text); background: rgba(255,255,255,0.05); }
      .top-link.active { color: var(--color-text); font-weight: var(--fw-nav); text-decoration: underline; }
      .sse-status { display: inline-flex; align-items: center; gap: 6px; font-size: var(--fs-small); color: var(--color-muted); }
      .status-dot { width: 10px; height: 10px; border-radius: 50%; background: #64748b; }
      .status-dot.connected { background: var(--status-done); box-shadow: 0 0 0 0 rgba(34,197,94,0.55); animation: pulse-live 1.6s infinite; }
      .status-dot.disconnected { background: #ef4444; box-shadow: 0 0 0 4px rgba(239,68,68,0.15); animation: none; }

      .activity-shell {
        background: var(--color-panel);
        border: 1px solid var(--color-border);
        border-radius: 14px;
        box-shadow: 0 12px 36px var(--color-shadow);
        padding: 14px;
      }
      .filters-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
      .filter-pill {
        border: 1px solid var(--color-border);
        background: transparent;
        color: var(--color-muted);
        border-radius: 999px;
        padding: 5px 11px;
        font-family: var(--font-body);
        font-weight: var(--fw-button);
        font-size: var(--fs-button);
        cursor: pointer;
      }
      .filter-pill.active { background: var(--color-panel-soft); color: var(--color-text); }
      .presence-line { margin: 0 0 12px; color: var(--color-muted); font-family: var(--font-body); font-size: var(--fs-small); }

      .feed { max-height: 72vh; overflow: auto; display: grid; gap: 8px; padding-right: 2px; }
      .feed-day {
        margin-top: 10px;
        padding-bottom: 4px;
        border-bottom: 1px solid var(--color-border);
        color: var(--color-muted);
        font-family: var(--font-body);
        font-weight: var(--fw-card-title);
        font-size: var(--fs-small);
        text-transform: uppercase;
        letter-spacing: 0.06em;
      }
      .feed-row { overflow: hidden;
        border: 1px solid var(--color-border);
        border-left: 3px solid var(--color-muted);
        border-radius: 10px;
        background: var(--color-panel-soft);
        padding: 8px 10px;
      }
      .feed-line { display: flex; align-items: center; gap: 8px; min-width: 0; white-space: nowrap; }
      .feed-agent { font-family: var(--font-mono); font-size: var(--fs-mono); font-weight: var(--fw-mono); color: #c6d2ea; flex: 0 0 auto; }
      .feed-action { flex: 1 1 0; font-family: var(--font-body); font-weight: var(--fw-body); font-size: var(--fs-body); color: var(--color-text); overflow: hidden; text-overflow: ellipsis; min-width: 0; }
      .feed-action.log { font-style: italic; }
      .ticket-link { color: var(--status-in-progress); text-decoration: none; }
      .ticket-link:hover { text-decoration: underline; }
      .feed-time { margin-left: auto; flex: 0 0 auto; font-family: var(--font-mono); font-size: var(--fs-mono); font-weight: var(--fw-mono); color: var(--color-muted); }
      .count-badge {
        flex: 0 0 auto;
        border: 1px solid var(--color-border);
        border-radius: 999px;
        padding: 1px 7px;
        font-family: var(--font-mono);
        font-size: var(--fs-mono);
        font-weight: var(--fw-mono);
        color: var(--color-muted);
        background: rgba(255,255,255,0.03);
      }

      .feed-row.action-done { border-left-color: var(--status-done); }
      .feed-row.action-started, .feed-row.action-in-progress { border-left-color: var(--status-in-progress); }
      .feed-row.action-blocked { border-left-color: var(--status-blocked); }
      .feed-row.action-created, .feed-row.action-other, .feed-row.action-log { border-left-color: var(--color-muted); }
      .feed-row.action-skipped { border-left-color: var(--status-skipped); }

      @keyframes pulse-live {
        0% { box-shadow: 0 0 0 0 rgba(34,197,94,0.55); }
        70% { box-shadow: 0 0 0 8px rgba(34,197,94,0); }
        100% { box-shadow: 0 0 0 0 rgba(34,197,94,0); }
      }
    </style>
  </head>
  <body>
    <main class="page">
      <header class="topbar">
        <div class="brand">agentplan</div>
        <nav class="topbar-nav">
          <a href="{{ url_for('index') }}" class="top-link">Home</a>
          <a href="{{ url_for('activity') }}" class="top-link active">Activity</a>
          <a href="{{ url_for('agents') }}" class="top-link">Agents</a>
        </nav>
        <div class="topbar-right">
          <span class="sse-status"><span id="sse-dot" class="status-dot"></span><span id="sse-label">connecting…</span></span>
          <span id="live-clock" class="clock">--:--:--</span>
        </div>
      </header>

      <section class="activity-shell">
        <div id="agent-filters" class="filters-row"></div>
        <div id="action-filters" class="filters-row"></div>
        <p id="presence-line" class="presence-line" hidden></p>
        <div id="feed" class="feed"></div>
      </section>
    </main>

    <script>
      const FEED_LIMIT = 300;
      const ACTION_OPTIONS = ["all", "created", "started", "done", "blocked", "skipped", "log"];
      const feedState = { events: [], activeAgent: "all", activeAction: "all" };

      function setClock(ts) {
        const d = ts ? new Date(ts) : new Date();
        document.getElementById("live-clock").textContent = d.toLocaleTimeString();
      }

      function setConnection(isConnected, label) {
        const dot = document.getElementById("sse-dot");
        const text = document.getElementById("sse-label");
        dot.classList.remove("connected", "disconnected");
        dot.classList.add(isConnected ? "connected" : "disconnected");
        text.textContent = label;
      }

      function esc(v) {
        return String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
      }

      function relativeTime(ts) {
        const d = new Date(ts || "");
        if (Number.isNaN(d.valueOf())) return "";
        const diff = Math.max(0, Math.floor((Date.now() - d.valueOf()) / 1000));
        if (diff < 60) return `${diff}s ago`;
        if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
        if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
        return `${Math.floor(diff / 86400)}d ago`;
      }

      function dayLabel(ts) {
        const d = new Date(ts || "");
        if (Number.isNaN(d.valueOf())) return "Unknown";
        const now = new Date();
        if (d.toDateString() === now.toDateString()) return "Today";
        const y = new Date(now); y.setDate(now.getDate() - 1);
        if (d.toDateString() === y.toDateString()) return "Yesterday";
        return d.toLocaleDateString([], { month: "short", day: "numeric" });
      }

      function ticketNum(item) {
        const m = String(item.ticket_label || "").match(/#(\\d+)/);
        return m ? m[1] : "";
      }

      function renderPresence(presence) {
        const line = document.getElementById("presence-line");
        if (!presence || presence.length === 0) {
          line.hidden = true;
          line.textContent = "";
          return;
        }
        line.hidden = false;
        const parts = presence.map((a) => `${esc(a.name)} (${esc(relativeTime(a.last_seen))})`);
        line.innerHTML = `Active agents ${parts.join(" · ")}`;
      }

      function renderAgentFilters(events) {
        const wrap = document.getElementById("agent-filters");
        const agents = [...new Set((events || []).map((e) => (e.agent || "system")))].sort();
        const options = ["all", ...agents];
        wrap.innerHTML = "";
        options.forEach((agent) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = `filter-pill${feedState.activeAgent === agent ? " active" : ""}`;
          btn.textContent = agent === "all" ? "All" : agent;
          btn.addEventListener("click", () => {
            feedState.activeAgent = agent;
            renderAgentFilters(events);
            renderFeed();
          });
          wrap.appendChild(btn);
        });
      }

      function renderActionFilters() {
        const wrap = document.getElementById("action-filters");
        wrap.innerHTML = "";
        ACTION_OPTIONS.forEach((action) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = `filter-pill${feedState.activeAction === action ? " active" : ""}`;
          btn.textContent = action === "all" ? "All" : action;
          btn.addEventListener("click", () => {
            feedState.activeAction = action;
            renderActionFilters();
            renderFeed();
          });
          wrap.appendChild(btn);
        });
      }

      function collapseCreated(rows) {
        const collapsed = [];
        for (let i = 0; i < rows.length; ) {
          const start = rows[i];
          if (start.action_type !== "created" || !start.project_slug) { collapsed.push(start); i += 1; continue; }
          const startTs = new Date(start.timestamp || "").valueOf();
          const group = [start];
          let j = i + 1;
          while (j < rows.length) {
            const next = rows[j];
            const nextTs = new Date(next.timestamp || "").valueOf();
            if (next.action_type !== "created" || next.project_slug !== start.project_slug || Number.isNaN(nextTs) || Number.isNaN(startTs) || Math.abs(nextTs - startTs) > 60000) break;
            group.push(next);
            j += 1;
          }
          if (group.length >= 3) {
            collapsed.push({
              id: `bulk-${start.id}`,
              timestamp: start.timestamp,
              agent: start.agent || "system",
              action_type: "created",
              project_slug: start.project_slug,
              project_title: start.project_title,
              collapsed_count: group.length,
              ticket_label: "",
            });
            i = j;
          } else {
            collapsed.push(...group);
            i = j;
          }
        }
        return collapsed;
      }

      function renderRow(item) {
        const actionType = item.action_type || "other";
        const agent = esc(item.agent || "system");
        const project = esc(item.project_slug || "-");
        const ticket = ticketNum(item);
        const verbMap = { created: "created", started: "started", done: "completed", blocked: "blocked", skipped: "skipped" };
        const verb = verbMap[actionType] || "updated";

        let detail = '';
        if (item.collapsed_count) {
          detail = `${esc(String(item.collapsed_count))} tickets created in ${project}`;
        } else if (actionType === "log") {
          const raw = item.action || "logged update"; detail = esc(raw.length > 120 ? raw.slice(0, 117) + "…" : raw);
        } else {
          detail = `${verb}${ticket ? ` ${esc("#" + ticket)}` : ""} in ${project}`;
        }

        const ticketHref = ticket && item.project_slug ? `/project/${encodeURIComponent(item.project_slug)}#ticket-${ticket}` : "";
        const ticketHtml = (!item.collapsed_count && ticket && item.project_slug) ? ` <a class="ticket-link" href="${esc(ticketHref)}">${esc("#" + ticket)}</a>` : "";
        const badgeHtml = item.collapsed_count ? `<span class="count-badge">${esc(String(item.collapsed_count))}</span>` : "";
        const actionClass = actionType === "log" ? "feed-action log" : "feed-action";

        return `<div class="feed-line"><span class="feed-agent">${agent}</span><span class="${actionClass}">${detail}${ticketHtml}</span>${badgeHtml}<span class="feed-time">${esc(relativeTime(item.timestamp))}</span></div>`;
      }

      function renderFeed() {
        const container = document.getElementById("feed");
        const pinnedBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 28;
        container.innerHTML = "";

        let rows = feedState.events.slice();
        rows = rows.filter((item) => (feedState.activeAgent === "all" || (item.agent || "system") === feedState.activeAgent));
        rows = rows.filter((item) => (feedState.activeAction === "all" || (item.action_type || "other") === feedState.activeAction));
        rows = collapseCreated(rows);

        let lastDay = "";
        rows.forEach((item) => {
          const day = dayLabel(item.timestamp);
          if (day !== lastDay) {
            const header = document.createElement("div");
            header.className = "feed-day";
            header.textContent = day;
            container.appendChild(header);
            lastDay = day;
          }
          const row = document.createElement("article");
          row.className = `feed-row action-${item.action_type || "other"}`;
          row.innerHTML = renderRow(item);
          container.appendChild(row);
        });

        if (pinnedBottom || feedState.events.length <= 4) container.scrollTop = container.scrollHeight;
      }

      function applyActivity(payload) {
        feedState.events = (payload.events || []).slice(-FEED_LIMIT);
        renderAgentFilters(feedState.events);
        renderActionFilters();
        renderPresence(payload.active_agents || []);
        renderFeed();
      }

      (function boot() {
        setClock();
        setInterval(() => setClock(), 1000);

        if (!window.EventSource) {
          setConnection(false, "reconnecting");
          return;
        }

        const source = new EventSource("{{ url_for('events') }}");
        source.addEventListener("open", () => setConnection(true, "live"));
        source.addEventListener("activity_feed", (event) => {
          try {
            const payload = JSON.parse(event.data);
            applyActivity(payload);
            setClock(payload.server_time || null);
            setConnection(true, "live");
          } catch (_err) {
            setConnection(false, "reconnecting");
          }
        });
        source.onerror = () => setConnection(false, "reconnecting");
      })();
    </script>
  </body>
</html>
"""

AGENTS_TEMPLATE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Agent Setup · agentplan dashboard</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
      :root {
        --font-heading: 'Playfair Display', Georgia, serif;
        --font-body: 'Inter', ui-sans-serif, sans-serif;
        --font-mono: 'JetBrains Mono', ui-monospace, monospace;
        --fs-h1: 2rem;
        --fs-h2: 1.25rem;
        --fs-card-title: 1rem;
        --fs-nav: 0.875rem;
        --fs-body: 0.875rem;
        --fs-small: 0.75rem;
        --fs-button: 0.75rem;
        --fs-mono: 0.8rem;
        --fw-h1: 700;
        --fw-h2: 600;
        --fw-card-title: 600;
        --fw-nav: 500;
        --fw-body: 400;
        --fw-small: 400;
        --fw-button: 500;
        --fw-mono: 400;
        --color-bg: #0a0e1a;
        --color-bg-alt: #0f1420;
        --color-panel: #151b2b;
        --color-panel-soft: #1b2236;
        --color-text: #e2e8f0;
        --color-muted: #8892a8;
        --color-border: rgba(255, 255, 255, 0.08);
        --color-shadow: rgba(0, 0, 0, 0.42);
        --color-high: #ef4444;
        --color-medium: #f97316;
        --color-low: #8892a8;
        --color-due-overdue: #f87171;
        --status-done: #22c55e;
        --status-in-progress: #3b82f6;
        --status-blocked: #f59e0b;
        --status-pending: #94a3b8;
        --status-needs-review: #facc15;
        --status-failed: #ef4444;
        --status-todo: var(--status-pending);
        --status-skipped: #64748b;
      }
      * { box-sizing: border-box; }
      body { margin: 0; font-family: var(--font-body); background: var(--color-bg); color: var(--color-text); }
      .page { max-width: 1200px; margin: 0 auto; padding: 2rem; }
      .topbar {
        display: grid;
        grid-template-columns: 1fr auto 1fr;
        align-items: center;
        margin-bottom: 16px;
        padding: 14px 16px;
        background: rgba(255,255,255,0.02);
        border: 1px solid var(--color-border);
        border-radius: 14px;
      }
      .brand { font-family: var(--font-body); font-weight: var(--fw-card-title); font-size: var(--fs-card-title); letter-spacing: -0.01em; }
      .topbar-nav { display: inline-flex; gap: 8px; justify-self: center; }
      .topbar-right { display: flex; align-items: center; gap: 12px; color: var(--color-muted); font-family: var(--font-body); font-weight: var(--fw-body); font-size: var(--fs-body); justify-self: end; }
      .clock { font-family: var(--font-body); font-weight: var(--fw-body); font-size: var(--fs-body); color: var(--color-text); }
      .top-link { color: var(--color-muted); border: 1px solid var(--color-border); border-radius: 10px; padding: 6px 10px; text-decoration: none; font-family: var(--font-body); font-weight: var(--fw-nav); font-size: var(--fs-nav); }
      .top-link:hover { color: var(--color-text); background: rgba(255,255,255,0.05); }
      .top-link.active { color: var(--color-text); text-decoration: underline; }
      .sse-status { display: inline-flex; align-items: center; gap: 6px; }
      .status-dot { width: 10px; height: 10px; border-radius: 50%; background: #64748b; }
      .status-dot.connected { background: var(--status-done); box-shadow: 0 0 0 4px rgba(34, 197, 94, 0.15); }
      .status-dot.disconnected { background: #ef4444; box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.15); }
      .grid { display: grid; grid-template-columns: 2fr 1fr; gap: 14px; }
      .card { background: var(--color-panel); border: 1px solid var(--color-border); border-radius: 14px; padding: 14px; }
      .title { margin: 0 0 10px; font-size: 1rem; }
      .table { width: 100%; border-collapse: collapse; }
      .table th, .table td { padding: 8px 6px; border-bottom: 1px solid var(--color-border); vertical-align: top; text-align: left; }
      .table th { color: var(--color-muted); font-size: 0.8rem; font-weight: 500; text-transform: uppercase; letter-spacing: 0.04em; }
      .mono { font-family: var(--font-mono); font-size: 0.8rem; }
      .muted { color: var(--color-muted); }
      .roles { display: flex; flex-wrap: wrap; gap: 6px; }
      .pill { border: 1px solid var(--color-border); border-radius: 999px; padding: 2px 8px; font-size: 0.75rem; background: var(--color-panel-soft); }
      .form-grid { display: grid; gap: 8px; }
      input[type="text"] { width: 100%; background: var(--color-panel-soft); border: 1px solid var(--color-border); color: var(--color-text); border-radius: 10px; padding: 8px; }
      .role-list { max-height: 130px; overflow: auto; border: 1px solid var(--color-border); border-radius: 10px; padding: 8px; background: rgba(255,255,255,0.02); }
      .role-item { display: block; margin-bottom: 6px; font-size: 0.85rem; }
      .btn { border: 1px solid var(--color-border); border-radius: 10px; padding: 6px 10px; background: transparent; color: var(--color-muted); cursor: pointer; }
      .btn:hover { color: var(--color-text); background: rgba(255,255,255,0.05); }
      .btn-danger { border-color: rgba(239,68,68,0.4); color: #fca5a5; }
      .tool-grid { display: grid; gap: 8px; }
      .tool-row { display: flex; justify-content: space-between; border: 1px solid var(--color-border); border-radius: 10px; padding: 8px; background: rgba(255,255,255,0.02); }
      @media (max-width: 980px) { .grid { grid-template-columns: 1fr; } }
    </style>
  </head>
  <body>
    <main class="page">
      <header class="topbar">
        <div class="brand">agentplan</div>
        <nav class="topbar-nav">
          <a class="top-link" href="{{ url_for('index') }}">Home</a>
          <a class="top-link" href="{{ url_for('activity') }}">Activity</a>
          <a class="top-link active" href="{{ url_for('agents') }}">Agents</a>
        </nav>
        <div class="topbar-right">
          <span id="agent-clock" class="clock">--:--:--</span>
          <span class="sse-status"><span id="agent-sse-dot" class="status-dot"></span><span id="agent-sse-label">connecting…</span></span>
        </div>
      </header>

      <section class="grid">
        <div class="card">
          <h2 class="title">Configured Agents</h2>
          {% if agents %}
          <table class="table">
            <thead><tr><th>Name</th><th>Command Template</th><th>Roles</th><th>Actions</th></tr></thead>
            <tbody>
              {% for agent in agents %}
              <tr>
                <td class="mono">{{ agent.name }}</td>
                <td class="mono">{{ agent.command_template }}</td>
                <td>
                  <div class="roles">
                    {% for role in agent.roles %}<span class="pill">{{ role }}</span>{% endfor %}
                    {% if not agent.roles %}<span class="muted">(none)</span>{% endif %}
                  </div>
                </td>
                <td>
                  <form class="form-grid" method="post" action="{{ url_for('edit_agent', name=agent.name) }}">
                    <input type="text" name="command_template" value="{{ agent.command_template }}" required>
                    <div class="role-list">
                    {% for role in roles %}
                      <label class="role-item"><input type="checkbox" name="roles" value="{{ role.name }}" {{ 'checked' if role.name in agent.roles else '' }}> {{ role.name }}</label>
                    {% endfor %}
                    </div>
                    <button class="btn" type="submit">Save</button>
                  </form>
                  <form method="post" action="{{ url_for('delete_agent_route', name=agent.name) }}" style="margin-top:6px;">
                    <button class="btn btn-danger" type="submit">Delete</button>
                  </form>
                </td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
          {% else %}
          <p class="muted">No agents configured.</p>
          {% endif %}
        </div>

        <div class="card">
          <h2 class="title">Detected Tools</h2>
          <div class="tool-grid">
          {% for tool in detected_tools %}
            <div class="tool-row"><span class="mono">{{ tool.name }}</span><span class="{{ '' if tool.found else 'muted' }}">{{ 'found' if tool.found else 'missing' }}</span></div>
          {% endfor %}
          </div>

          <h2 class="title" style="margin-top:16px;">Add Agent</h2>
          <form class="form-grid" method="post" action="{{ url_for('add_agent') }}">
            <input type="text" name="name" placeholder="name" required>
            <input type="text" name="command_template" placeholder="command template" required>
            <div class="role-list">
            {% for role in roles %}
              <label class="role-item"><input type="checkbox" name="roles" value="{{ role.name }}"> {{ role.name }}</label>
            {% endfor %}
            {% if not roles %}<div class="muted">No roles available yet.</div>{% endif %}
            </div>
            <button class="btn" type="submit">Add Agent</button>
          </form>
        </div>
      </section>
    </main>
    <script>
      function setClock(ts) {
        const d = ts ? new Date(ts) : new Date();
        document.getElementById("agent-clock").textContent = d.toLocaleTimeString();
      }

      function setConnection(isConnected, label) {
        const dot = document.getElementById("agent-sse-dot");
        const text = document.getElementById("agent-sse-label");
        dot.classList.remove("connected", "disconnected");
        dot.classList.add(isConnected ? "connected" : "disconnected");
        text.textContent = label;
      }

      (function subscribe() {
        setClock();
        setInterval(() => setClock(), 1000);

        if (!window.EventSource) {
          setConnection(false, "SSE unsupported");
          return;
        }

        const source = new EventSource("{{ url_for('events') }}");
        source.addEventListener("open", () => setConnection(true, "connected"));
        source.addEventListener("project_stats", (event) => {
          try {
            const payload = JSON.parse(event.data);
            setClock(payload.server_time || null);
            setConnection(true, "connected");
          } catch (_err) {
            setConnection(false, "parse error");
          }
        });
        source.onerror = () => setConnection(false, "reconnecting…");
      })();
    </script>
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
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
      :root {
        --font-heading: 'Playfair Display', Georgia, serif;
        --font-body: 'Inter', ui-sans-serif, sans-serif;
        --font-mono: 'JetBrains Mono', ui-monospace, monospace;
        --fs-h1: 2rem;
        --fs-h2: 1.25rem;
        --fs-card-title: 1rem;
        --fs-nav: 0.875rem;
        --fs-body: 0.875rem;
        --fs-small: 0.75rem;
        --fs-button: 0.75rem;
        --fs-mono: 0.8rem;
        --fw-h1: 700;
        --fw-h2: 600;
        --fw-card-title: 600;
        --fw-nav: 500;
        --fw-body: 400;
        --fw-small: 400;
        --fw-button: 500;
        --fw-mono: 400;
        --color-bg: #0a0e1a;
        --color-bg-alt: #0f1420;
        --color-panel: #151b2b;
        --color-panel-soft: #1b2236;
        --color-text: #e2e8f0;
        --color-muted: #8892a8;
        --color-border: rgba(255, 255, 255, 0.08);
        --color-shadow: rgba(0, 0, 0, 0.42);
        --color-high: #ef4444;
        --color-medium: #f97316;
        --color-low: #8892a8;
        --color-due-overdue: #f87171;
        --status-done: #22c55e;
        --status-in-progress: #3b82f6;
        --status-blocked: #f59e0b;
        --status-pending: #94a3b8;
        --status-needs-review: #facc15;
        --status-failed: #ef4444;
        --status-todo: var(--status-pending);
        --status-skipped: #64748b;
      }
      * { box-sizing: border-box; }
      body { margin: 0; font-family: var(--font-body); background: var(--color-bg); color: var(--color-text); }
      h1, h2, h3, h4, h5, h6 { letter-spacing: -0.01em; font-family: var(--font-body); } h1 { font-family: var(--font-heading); }
      .page { max-width: 100%; margin: 0 auto; padding: 2rem 3rem; }
      .topbar {
        display: grid;
        grid-template-columns: 1fr auto 1fr;
        align-items: center;
        gap: 14px;
        margin-bottom: 16px;
        padding: 14px 16px;
        background: rgba(255, 255, 255, 0.02);
        border: 1px solid var(--color-border);
        border-radius: 14px;
      }
      .topbar-left { display: flex; align-items: center; gap: 12px; min-width: 0; }
      .topbar-nav { display: inline-flex; gap: 8px; justify-self: center; }
      .brand { font-family: var(--font-body); font-weight: var(--fw-card-title); font-size: var(--fs-card-title); }
      .project-title { margin: 0 0 6px; font-family: var(--font-heading); font-size: var(--fs-h1); font-weight: var(--fw-h1); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .project-dir { margin: 0 0 10px; font-family: var(--font-mono); font-size: var(--fs-mono); color: var(--color-muted); }
      .project-dir a { color: #93c5fd; text-decoration: none; }
      .project-dir a:hover { text-decoration: underline; }
      .project-dir-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
      .project-dir-empty { color: var(--color-muted); font-style: italic; }
      .btn-sm { padding: 3px 8px; font-size: 0.8rem; }
      .project-dir-input {
        flex: 1;
        max-width: min(640px, 72vw);
        background: var(--color-panel-soft);
        border: 1px solid var(--color-border);
        color: var(--color-text);
        border-radius: 6px;
        padding: 4px 8px;
        font-family: var(--font-mono);
        font-size: var(--fs-mono);
      }
      .project-dir-input:focus {
        outline: none;
        border-color: rgba(59,130,246,0.6);
      }
        color: var(--color-muted);
        font-size: var(--fs-small);
      }
      .project-dir-warning {
        margin: 0 0 10px;
        color: #fde68a;
        font-size: var(--fs-small);
      }
      .project-code { font-family: var(--font-mono); font-size: var(--fs-mono); color: var(--color-muted); text-transform: uppercase; letter-spacing: 0.08em; }
      .topbar-right { display: flex; align-items: center; gap: 12px; justify-self: end; color: var(--color-muted); font-family: var(--font-body); font-size: var(--fs-body); }
      .sse-status { display: inline-flex; align-items: center; gap: 6px; font-family: var(--font-body); font-weight: var(--fw-body); font-size: var(--fs-small); color: var(--color-muted); }
      .status-dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: #64748b;
      }
      .status-dot.connected {
        background: #22c55e;
        box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.55);
        animation: pulse-live 1.6s infinite;
      }
      .status-dot.disconnected {
        background: #ef4444;
        box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.15);
        animation: none;
      }
      .btn-back {
        color: var(--color-muted);
        border: 1px solid var(--color-border);
        border-radius: 10px;
        padding: 7px 10px;
        text-decoration: none;
        font-family: var(--font-body);
        font-weight: var(--fw-nav);
        font-size: var(--fs-nav);
      }
      .btn-back:hover { color: var(--color-text); background: rgba(255, 255, 255, 0.05); }
      .btn-back.active { color: var(--color-text); font-weight: var(--fw-nav); text-decoration: underline; }

      .project-meta { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin: 0 0 16px; color: var(--color-muted); font-family: var(--font-body); font-weight: var(--fw-body); font-size: var(--fs-small); }
      .context-panel { margin: 0 0 16px; border: 1px solid var(--color-border); border-radius: 10px; background: rgba(255,255,255,0.02); }
      .context-panel summary { padding: 12px; cursor: pointer; font-size: var(--fs-h2); font-family: var(--font-heading); font-weight: var(--fw-heading); list-style: none; display: flex; align-items: center; gap: 8px; }
      .context-panel summary::before { content: "▸"; transition: transform 0.2s; }
      .context-panel[open] summary::before { transform: rotate(90deg); }
      .context-panel summary::-webkit-details-marker { display: none; }
      .context-panel .context-body { padding: 0 12px 12px; }
      .context-content { font-size: var(--fs-body); line-height: 1.45; }
      .context-empty { color: var(--color-muted); font-size: var(--fs-small); }
      .legend-strip {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        margin: 0 0 12px;
        padding: 10px 12px;
        border: 1px solid var(--color-border);
        border-radius: 12px;
        background: rgba(255, 255, 255, 0.02);
      }
      .legend-item { display: inline-flex; align-items: center; gap: 6px; font-family: var(--font-body); font-weight: var(--fw-body); font-size: var(--fs-small); color: var(--color-muted); }
      .legend-dot { width: 8px; height: 8px; border-radius: 999px; }
      .legend-dot.pending { background: var(--status-pending); }
      .legend-dot.in-progress { background: var(--status-in-progress); }
      .legend-dot.blocked { background: var(--status-blocked); }
      .legend-dot.needs-review { background: var(--status-needs-review); }
      .legend-dot.failed { background: var(--status-failed); }
      .legend-dot.done { background: var(--status-done); }
      .legend-dot.skipped { background: var(--status-skipped); }
      .kanban-grid { display: grid; grid-template-columns: repeat(6, minmax(180px, 1fr)); gap: 14px; align-items: start; }
      .kanban-column {
        background: rgba(255, 255, 255, 0.015);
        border: 1px solid var(--color-border);
        border-radius: 14px;
        min-height: 220px;
        display: flex;
        flex-direction: column;
      }
      .kanban-column-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px 12px 10px;
        border-bottom: 1px solid var(--color-border);
      }
      .kanban-column-title { margin: 0; font-size: var(--fs-h2); font-family: var(--font-body); font-weight: var(--fw-h2); text-transform: uppercase; letter-spacing: 0.05em; color: var(--color-muted); }
      .kanban-count {
        min-width: 1.65rem;
        height: 1.65rem;
        padding: 0 7px;
        border-radius: 999px;
        border: 1px solid var(--color-border);
        background: var(--color-bg-alt);
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-family: var(--font-mono);
        font-size: var(--fs-mono);
      }
      .kanban-column-body { padding: 10px; display: grid; gap: 10px; overflow-y: auto; max-height: 70vh; }
      .kanban-empty { color: var(--color-muted); font-family: var(--font-body); font-weight: var(--fw-body); font-size: var(--fs-small); margin: 4px; }
      .ticket-link { text-decoration: none; color: inherit; display: block; cursor: pointer; transition: transform 0.42s ease, opacity 0.3s ease; }
      .ticket-card {
        position: relative;
        background: var(--color-panel);
        border: 1px solid var(--color-border);
        border-radius: 12px;
        box-shadow: 0 12px 36px var(--color-shadow);
        padding: 10px;
        transition: transform 0.4s ease, border-color 0.4s ease, box-shadow 0.4s ease, opacity 0.3s ease;
      }
      .priority-pill { display: inline-block; font-family: var(--font-body); font-size: 0.65rem; font-weight: 500; padding: 2px 8px; border-radius: 8px; text-transform: uppercase; letter-spacing: 0.04em; }
      .priority-pill.p-high { background: rgba(239,68,68,0.15); color: #f87171; }
      .priority-pill.p-medium { background: rgba(249,115,22,0.15); color: #fb923c; }
      .priority-pill.p-low { background: rgba(136,146,168,0.1); color: var(--color-muted); }
      .priority-pill.p-none { display: none; }
      .pill-row { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; align-items: center; }
      .ticket-link:hover .ticket-card, .ticket-link:focus-visible .ticket-card { transform: translateY(-1px); border-color: rgba(59,130,246,0.55); }
      .ticket-link.is-entering { opacity: 0; transform: translateY(10px) scale(0.98); }
      .ticket-link.is-leaving { opacity: 0; transform: translateY(-6px) scale(0.98); pointer-events: none; }
      .ticket-card.has-active-agent::after {
        content: "";
        position: absolute;
        top: 8px;
        right: 8px;
        width: 8px;
        height: 8px;
        border-radius: 999px;
        background: #22c55e;
        box-shadow: 0 0 0 0 rgba(34,197,94,0.65);
        animation: pulse-live 1.6s infinite;
      }

      @keyframes pulse-live {
        0% { box-shadow: 0 0 0 0 rgba(34,197,94,0.55); }
        70% { box-shadow: 0 0 0 8px rgba(34,197,94,0); }
        100% { box-shadow: 0 0 0 0 rgba(34,197,94,0); }
      }

      .ticket-head { display: flex; justify-content: space-between; gap: 8px; align-items: flex-start; margin-bottom: 8px; }
      .ticket-id { font-family: var(--font-mono); color: var(--color-muted); font-size: var(--fs-mono); font-weight: var(--fw-mono); }
      .ticket-title { margin: 2px 0 0; font-family: var(--font-body); font-size: var(--fs-card-title); font-weight: var(--fw-card-title); line-height: 1.32; word-break: break-word; overflow: hidden; }
      .ticket-due { font-family: var(--font-body); font-weight: var(--fw-body); font-size: var(--fs-small); color: var(--color-muted); white-space: nowrap; }
      .ticket-due.overdue { color: var(--color-due-overdue); font-weight: var(--fw-card-title); }
      .tag-row { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
      .tag-pill {
        border-radius: 999px;
        padding: 2px 8px;
        font-family: var(--font-body);
        font-weight: var(--fw-button);
        font-size: var(--fs-small);
        border: 1px solid transparent;
      }
      .tag-blue { background: rgba(59,130,246,0.18); color: #bfdbfe; border-color: rgba(59,130,246,0.35); }
      .tag-purple { background: rgba(168,85,247,0.17); color: #e9d5ff; border-color: rgba(168,85,247,0.35); }
      .tag-teal { background: rgba(20,184,166,0.17); color: #99f6e4; border-color: rgba(20,184,166,0.35); }
      .tag-amber { background: rgba(245,158,11,0.18); color: #fde68a; border-color: rgba(245,158,11,0.35); }
      .tag-rose { background: rgba(244,63,94,0.18); color: #fecdd3; border-color: rgba(244,63,94,0.35); }
      .agent-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
      .agent-avatar {
        --avatar-size: 1.5rem;
        width: var(--avatar-size);
        height: var(--avatar-size);
        border-radius: 999px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-family: var(--font-body);
        font-size: var(--fs-small);
        font-weight: var(--fw-card-title);
        background: var(--color-bg-alt);
        border: 1px solid var(--color-border);
        color: var(--color-text);
      }
      .agent-name { font-family: var(--font-body); font-weight: var(--fw-body); font-size: var(--fs-small); color: var(--color-muted); }
      .progress-meta { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; color: var(--color-muted); font-family: var(--font-mono); font-size: var(--fs-mono); font-weight: var(--fw-mono); }
      .mini-progress {
        height: 5px;
        border-radius: 999px;
        background: var(--color-bg-alt);
        overflow: hidden;
        border: 1px solid var(--color-border);
      }
      .mini-progress-value {
        height: 100%;
        background: linear-gradient(90deg, #3b82f6, #22c55e);
        width: var(--progress, 0%);
      }
      .filters {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 8px;
        margin-bottom: 16px;
      }
      .filters select {
        width: 100%;
        background: var(--color-panel-soft);
        border: 1px solid var(--color-border);
        color: var(--color-text);
        border-radius: 10px;
        padding: 8px 10px;
        font-family: var(--font-body);
        font-weight: var(--fw-body);
        font-size: var(--fs-body);
      }
      .filter-actions { grid-column: 1 / -1; display: flex; gap: 8px; }
      .btn { border: 1px solid var(--color-border); border-radius: 10px; padding: 7px 10px; text-decoration: none; font-family: var(--font-body); font-weight: var(--fw-button); font-size: var(--fs-button); color: var(--color-muted); background: transparent; cursor: pointer; }
      .btn:hover { color: var(--color-text); background: rgba(255,255,255,0.05); }
      .btn-primary { background: rgba(59,130,246,0.18); color: #dbeafe; border-color: rgba(59,130,246,0.35); }
      .btn-chain-start { background: rgba(34, 197, 94, 0.2); color: #dcfce7; border-color: rgba(34, 197, 94, 0.45); }
      .btn-chain-stop { background: rgba(239, 68, 68, 0.16); color: #fecaca; border-color: rgba(239, 68, 68, 0.35); }
      .btn:disabled { opacity: 0.45; cursor: not-allowed; }
      .chain-status {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        margin: 0 0 12px;
        padding: 10px 12px;
        border: 1px solid var(--color-border);
        border-radius: 12px;
        background: rgba(255, 255, 255, 0.02);
        color: var(--color-muted);
        font-size: var(--fs-small);
      }
      .chain-dot { width: 8px; height: 8px; border-radius: 999px; background: #64748b; }
      .chain-dot.running { background: #22c55e; }
      .chain-dot.paused { background: #facc15; }
      .chain-dot.stopped, .chain-dot.done { background: #64748b; }
      .review-actions { display: grid; gap: 8px; }
      .review-actions-row { display: flex; flex-wrap: wrap; gap: 8px; }
      .toast-stack {
        position: fixed;
        right: 16px;
        bottom: 16px;
        z-index: 120;
        display: grid;
        gap: 8px;
      }
      .toast {
        padding: 10px 12px;
        border-radius: 10px;
        border: 1px solid var(--color-border);
        background: var(--color-panel-soft);
        color: var(--color-text);
        max-width: min(460px, 88vw);
        font-family: var(--font-body);
        font-size: var(--fs-small);
      }
      .toast.error {
        border-color: rgba(239, 68, 68, 0.45);
        background: rgba(127, 29, 29, 0.35);
      }

      .ticket-panel-backdrop {
        position: fixed;
        inset: 0;
        background: rgba(2, 6, 23, 0.6);
        backdrop-filter: blur(2px);
        opacity: 0;
        pointer-events: none;
        transition: opacity 220ms ease;
        z-index: 40;
      }
      .ticket-panel {
        position: fixed;
        top: 0;
        right: 0;
        width: min(520px, 96vw);
        height: 100vh;
        background: linear-gradient(180deg, rgba(21,27,43,0.98), rgba(15,20,32,0.98));
        border-left: 1px solid var(--color-border);
        box-shadow: -24px 0 64px rgba(0,0,0,0.55);
        transform: translateX(100%);
        transition: transform 280ms cubic-bezier(.22,.61,.36,1);
        z-index: 50;
        display: flex;
        flex-direction: column;
      }
      .ticket-panel.is-open { transform: translateX(0); }
      .ticket-panel-backdrop.is-open { opacity: 1; pointer-events: auto; }
      .ticket-panel-header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 12px;
        padding: 16px;
        border-bottom: 1px solid var(--color-border);
      }
      .ticket-panel-id { font-family: var(--font-mono); font-size: var(--fs-mono); color: var(--color-muted); }
      .ticket-panel-title { margin: 4px 0 0; font-family: var(--font-body); font-weight: var(--fw-card-title); font-size: var(--fs-card-title); line-height: 1.25; }
      .ticket-panel-close {
        flex-shrink: 0;
        width: 32px;
        height: 32px;
        border-radius: 10px;
        border: 1px solid var(--color-border);
        background: transparent;
        color: var(--color-muted);
        cursor: pointer;
      }
      .ticket-panel-close:hover { color: var(--color-text); background: rgba(255,255,255,0.05); }
      .panel-subtitle { margin-bottom: 6px; }
      .ticket-panel-content { padding: 16px; overflow-y: auto; display: grid; gap: 14px; }
      .panel-block {
        background: rgba(255,255,255,0.02);
        border: 1px solid var(--color-border);
        border-radius: 12px;
        padding: 12px;
      }
      .panel-block h3 {
        margin: 0 0 10px;
        font-size: var(--fs-h2);
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-family: var(--font-body);
        font-weight: var(--fw-card-title);
        color: var(--color-muted);
      }
      .panel-muted { margin: 0; color: var(--color-muted); font-family: var(--font-body); font-weight: var(--fw-body); font-size: var(--fs-small); }
      .panel-description { margin: 0; white-space: pre-wrap; line-height: 1.45; font-family: var(--font-body); font-weight: var(--fw-body); font-size: var(--fs-body); }
      .subtask-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
      .subtask-item { display: grid; grid-template-columns: auto 1fr; gap: 8px; align-items: center; font-family: var(--font-body); font-weight: var(--fw-body); font-size: var(--fs-body); }
      .subtask-item input { accent-color: #3b82f6; }
      .dep-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
      .dep-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
      .dep-item { font-family: var(--font-body); font-weight: var(--fw-body); font-size: var(--fs-body); color: #c7d2fe; }
      .audit-timeline { list-style: none; margin: 0; padding: 0 0 0 14px; border-left: 1px solid var(--color-border); display: grid; gap: 10px; }
      .audit-item { position: relative; }
      .audit-item::before {
        content: "";
        position: absolute;
        left: -19px;
        top: 4px;
        width: 8px;
        height: 8px;
        border-radius: 999px;
        background: #3b82f6;
        box-shadow: 0 0 0 4px rgba(59,130,246,0.2);
      }
      .audit-meta { font-family: var(--font-mono); color: var(--color-muted); font-size: var(--fs-mono); margin-bottom: 2px; }
      .audit-message { margin: 0; font-size: var(--fs-body); line-height: 1.35; }

      @media (max-width: 1180px) {
        .kanban-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      }
      @media (max-width: 760px) {
        .page { width: min(620px, 94vw); }
        .topbar { flex-direction: column; align-items: flex-start; }
        .filters { grid-template-columns: 1fr; }
        .kanban-grid { grid-template-columns: 1fr; }
      }
    </style>
  </head>
  <body>
    <main class="page">
      <header class="topbar">
        <div class="topbar-left">
          <div>
            <div class="brand">agentplan</div>
          </div>
        </div>
        <nav class="topbar-nav">
          <a href="{{ url_for('index') }}" class="btn-back">Home</a>
          <a href="{{ url_for('activity') }}" class="btn-back">Activity</a>
          <a href="{{ url_for('agents') }}" class="btn-back">Agents</a>
        </nav>
        <div class="topbar-right">
          <button id="chain-start-btn" class="btn btn-chain-start" type="button">▶ Start Work</button>
          <button id="chain-stop-btn" class="btn btn-chain-stop" type="button">■ Stop</button>
          <span id="project-clock" class="clock"></span>
          <span class="sse-status"><span id="project-sse-dot" class="status-dot disconnected" aria-hidden="true"></span><span id="project-sse-label">connecting…</span></span>
        </div>
      </header>

      <h1 class="project-title">{{ project.title }}</h1>
      <div class="project-dir-row" id="project-dir-row">
        <span id="project-dir-display" class="project-dir">
        {%- if project.dir -%}
          <a href="file://{{ project.dir }}">{{ project.dir }}</a>
        {%- else -%}
          <span class="project-dir-empty">No directory set</span>
        {%- endif -%}
        </span>
        <input id="project-dir-input" class="project-dir-input" name="directory" type="text" value="{{ project.dir or '' }}" placeholder="~/path/to/repo" hidden>
        <button id="project-dir-edit-btn" class="btn btn-sm" type="button">Edit</button>
        <button id="project-dir-save-btn" class="btn btn-sm btn-primary" type="button" hidden>Save</button>
        <button id="project-dir-cancel-btn" class="btn btn-sm" type="button" hidden>Cancel</button>
      </div>
      <div id="project-dir-warning" class="project-dir-warning" {% if not directory_warning %}hidden{% endif %}>⚠ Linked directory does not exist on disk.</div>

      <div id="chain-status" class="chain-status">
        <span id="chain-status-dot" class="chain-dot {{ chain.status if chain and chain.status else 'stopped' }}"></span>
        <span id="chain-status-text">{{ chain_text }}</span>
      </div>

      <div class="project-meta">
        <span>{{ done_count }}/{{ total_count }} done</span>
      </div>

      <details class="context-panel" aria-label="project context">
        <summary>Project Context</summary>
        <div class="context-body">
        {% if context_payload.exists %}
        <div class="context-content">{{ context_payload.html|safe }}</div>
        {% else %}
        <div class="context-empty">No context file yet. The first agent to work on this project will create one.</div>
        {% endif %}
        </div>
      </details>

      <form method="get" class="filters" aria-label="filters">
        <select name="status" aria-label="Status filter">
          <option value="" {{ "selected" if not filters.status else "" }}>All statuses</option>
          {% for status in ["pending", "in-progress", "blocked", "needs-review", "failed", "done"] %}
          <option value="{{ status }}" {{ "selected" if filters.status == status else "" }}>{{ status }}</option>
          {% endfor %}
        </select>
        <select name="priority" aria-label="Priority filter">
          <option value="" {{ "selected" if not filters.priority else "" }}>All priorities</option>
          {% for priority in ["high", "medium", "low", "none"] %}
          <option value="{{ priority }}" {{ "selected" if filters.priority == priority else "" }}>{{ priority | capitalize }}</option>
          {% endfor %}
        </select>
        <select name="tag" aria-label="Tag filter">
          <option value="" {{ "selected" if not filters.tag else "" }}>All tags</option>
          {% for tag in available_tags %}
          <option value="{{ tag }}" {{ "selected" if filters.tag == tag|lower else "" }}>{{ tag }}</option>
          {% endfor %}
        </select>
        <div class="filter-actions">
          <button class="btn btn-primary" type="submit">Apply filters</button>
          <a class="btn" href="{{ url_for('project_detail', slug=project.slug) }}">Reset</a>
        </div>
      </form>

      <section class="kanban-grid" aria-label="kanban board">
        {% for status in status_order %}
        <article class="kanban-column" data-status="{{ status }}">
          <header class="kanban-column-header">
            <h2 class="kanban-column-title">{{ status_labels[status] }}</h2>
            <span class="kanban-count" data-count-for="{{ status }}">{{ grouped[status]|length }}</span>
          </header>
          <div class="kanban-column-body" data-column-body="{{ status }}">
            {% if grouped[status] %}
              {% for ticket in grouped[status] %}
              <a class="ticket-link" href="{{ url_for('ticket_detail', slug=project.slug, ticket_num=ticket.num) }}" data-ticket-num="{{ ticket.num }}" data-ticket-status="{{ status }}" role="button" aria-label="Open ticket #{{ ticket.num }} details panel">
                <article class="ticket-card priority-{{ ticket.priority|lower }} {{ "has-active-agent" if ticket.active_agent else "" }}">
                  <div class="ticket-head">
                    <div>
                      <div class="ticket-id">#{{ ticket.num }}</div>
                      <div class="ticket-title">{{ ticket.title }}</div>
                    </div>
                    {% if ticket.due_date %}
                    <div class="ticket-due {{ 'overdue' if ticket.is_overdue else '' }}">{{ ticket.due_date }}</div>
                    {% endif %}
                  </div>

                  <div class="pill-row">
                    <span class="priority-pill p-{{ ticket.priority|lower }}">{{ ticket.priority|lower }}</span>
                    {% for tag in (ticket.tags or []) %}
                    <span class="tag-pill tag-{{ ticket.tag_tones.get(tag, 'blue') }}">{{ tag }}</span>
                    {% endfor %}
                  </div>

                  {% if ticket.assignee %}
                  <div class="agent-row">
                    <span class="agent-avatar">{{ ticket.assignee_initials }}</span>
                    <span class="agent-name">{{ ticket.assignee }}</span>
                  </div>
                  {% endif %}

                  {% if ticket.subtask_total > 0 %}
                  <div class="progress-meta">
                    <span>subtasks</span>
                    <span>{{ ticket.subtask_done }}/{{ ticket.subtask_total }}</span>
                  </div>
                  <div class="mini-progress" role="img" aria-label="subtask progress">
                    <div class="mini-progress-value" style="--progress: {{ ticket.subtask_pct }}%;"></div>
                  </div>
                  {% endif %}
                </article>
              </a>
              {% endfor %}
            {% else %}
              <p class="kanban-empty">No tickets.</p>
            {% endif %}
          </div>
        </article>
        {% endfor %}
      </section>
      <div id="ticket-panel-backdrop" class="ticket-panel-backdrop" hidden></div>
      <aside id="ticket-panel" class="ticket-panel" aria-hidden="true" aria-label="Ticket detail panel">
        <header class="ticket-panel-header">
          <div>
            <div id="panel-ticket-id" class="ticket-panel-id">Ticket</div>
            <h2 id="panel-ticket-title" class="ticket-panel-title">Loading…</h2>
          </div>
          <button id="ticket-panel-close" class="ticket-panel-close" type="button" aria-label="Close ticket detail">✕</button>
        </header>
        <div id="ticket-panel-content" class="ticket-panel-content"></div>
      </aside>
      <div id="toast-stack" class="toast-stack" aria-live="polite" aria-atomic="true"></div>

    </main>
    <script>

      function setClock(ts) {
        const el = document.getElementById("project-clock");
        if (!el) return;
        const d = ts ? new Date(ts) : new Date();
        el.textContent = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });
      }
      setClock();
      setInterval(() => setClock(), 1000);

      (() => {
        const panel = document.getElementById("ticket-panel");
        const backdrop = document.getElementById("ticket-panel-backdrop");
        const closeBtn = document.getElementById("ticket-panel-close");
        const panelId = document.getElementById("panel-ticket-id");
        const panelTitle = document.getElementById("panel-ticket-title");
        const panelContent = document.getElementById("ticket-panel-content");
        const projectSlug = {{ project.slug|tojson }};

        function esc(v) {
          return String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
        }

        function renderList(items, emptyText) {
          if (!items || items.length === 0) return `<p class="panel-muted">${esc(emptyText)}</p>`;
          return `<ul class="dep-list">${items.map((item) => `<li class="dep-item">#${esc(item.num)} ${esc(item.title)}</li>`).join("")}</ul>`;
        }

        function renderSubtasks(subtasks) {
          if (!subtasks || subtasks.length === 0) return '<p class="panel-muted">No subtasks.</p>';
          return `<ul class="subtask-list">${subtasks.map((subtask) => `<li class="subtask-item"><input type="checkbox" disabled ${subtask.status === "done" ? "checked" : ""}><span>#${esc(subtask.num)} ${esc(subtask.title)}</span></li>`).join("")}</ul>`;
        }

        function renderHistory(history) {
          if (!history || history.length === 0) return '<p class="panel-muted">No audit entries.</p>';
          return `<ul class="audit-timeline">${history.map((item) => `<li class="audit-item"><div class="audit-meta">${esc(item.timestamp)} · ${esc(item.agent || "system")}${item.transition ? ` · ${esc(item.transition.old_state || "(none)")} → ${esc(item.transition.new_state || "")}` : ""}</div><p class="audit-message">${esc(item.message || "")}</p></li>`).join("")}</ul>`;
        }

        function renderPanel(data) {
          panelId.textContent = `#${data.num}`;
          panelTitle.textContent = data.title || "Ticket details";
          const showReviewActions = data.status === "failed" || data.status === "needs-review";
          panelContent.innerHTML = `
            <section class="panel-block">
              <h3>Description</h3>
              <p class="panel-description">${esc(data.description || "No description.")}</p>
            </section>
            <section class="panel-block">
              <h3>Subtasks</h3>
              ${renderSubtasks(data.subtasks)}
            </section>
            <section class="panel-block">
              <h3>Dependency Graph</h3>
              <div class="dep-grid">
                <div><div class="panel-muted panel-subtitle">blocked by</div>${renderList(data.blocked_by, "No blockers.")}</div>
                <div><div class="panel-muted panel-subtitle">blocks</div>${renderList(data.blocks, "No blocked tickets.")}</div>
              </div>
            </section>
            ${showReviewActions ? `<section class="panel-block review-actions"><h3>Review Actions</h3><div class="review-actions-row"><button class="btn btn-chain-start" type="button" data-review-action="done" data-ticket-num="${esc(data.num)}">✓ Mark Done</button><button class="btn btn-primary" type="button" data-review-action="retry" data-ticket-num="${esc(data.num)}">↺ Retry</button><button class="btn btn-chain-stop" type="button" data-review-action="skip" data-ticket-num="${esc(data.num)}">⊘ Skip</button></div></section>` : ""}
            <section class="panel-block">
              <h3>Audit Timeline</h3>
              ${renderHistory(data.audit_history)}
            </section>
            <section class="panel-block">
              <h3>Close Notes</h3>
              <p class="panel-description">${esc(data.close_note || "No close notes.")}</p>
            </section>
          `;
        }

        function openPanel() {
          backdrop.hidden = false;
          panel.setAttribute("aria-hidden", "false");
          requestAnimationFrame(() => {
            backdrop.classList.add("is-open");
            panel.classList.add("is-open");
          });
        }

        function closePanel() {
          panel.classList.remove("is-open");
          backdrop.classList.remove("is-open");
          panel.setAttribute("aria-hidden", "true");
          setTimeout(() => { backdrop.hidden = true; }, 260);
        }

        async function loadTicket(ticketNum) {
          panelId.textContent = `#${ticketNum}`;
          panelTitle.textContent = "Loading…";
          panelContent.innerHTML = '<section class="panel-block"><p class="panel-muted">Fetching ticket details…</p></section>';
          openPanel();
          try {
            const response = await fetch(`/api/ticket/${encodeURIComponent(projectSlug)}/${encodeURIComponent(ticketNum)}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            renderPanel(data);
          } catch (error) {
            panelContent.innerHTML = `<section class="panel-block"><p class="panel-muted">Failed to load ticket details (${esc(error.message)}).</p></section>`;
          }
        }

        document.querySelectorAll(".ticket-link[data-ticket-num]").forEach((link) => {
          link.addEventListener("click", (event) => {
            if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
            event.preventDefault();
            loadTicket(link.dataset.ticketNum);
          });
        });

        closeBtn.addEventListener("click", closePanel);
        backdrop.addEventListener("click", closePanel);
        document.addEventListener("keydown", (event) => {
          if (event.key === "Escape" && panel.classList.contains("is-open")) closePanel();
        });

        const statusOrder = ["pending", "in-progress", "blocked", "needs-review", "failed", "done"];
        const filters = {{ filters|tojson }};
        const chainStartBtn = document.getElementById("chain-start-btn");
        const chainStopBtn = document.getElementById("chain-stop-btn");
        const chainStatusDot = document.getElementById("chain-status-dot");
        const chainStatusText = document.getElementById("chain-status-text");
        const toastStack = document.getElementById("toast-stack");
        const dirDisplay = document.getElementById("project-dir-display");
        const dirEditBtn = document.getElementById("project-dir-edit-btn");
        const dirInput = document.getElementById("project-dir-input");
        const dirSaveBtn = document.getElementById("project-dir-save-btn");
        const dirCancelBtn = document.getElementById("project-dir-cancel-btn");
        const dirWarning = document.getElementById("project-dir-warning");

        function showToast(message, tone = "error") {
          if (!toastStack) return;
          const toast = document.createElement("div");
          toast.className = `toast ${tone}`;
          toast.textContent = message || "Request failed.";
          toastStack.appendChild(toast);
          setTimeout(() => {
            toast.remove();
          }, 4500);
        }

        function renderDirectoryDisplay(directory) {
          if (!dirDisplay) return;
          const value = String(directory || "").trim();
          if (!value) {
            dirDisplay.innerHTML = `<span class="project-dir-empty">No directory set</span>`;
            return;
          }
          dirDisplay.innerHTML = `<a href="file://${esc(value)}">${esc(value)}</a>`;
        }

        function enterEditMode() {
          dirDisplay.hidden = true;
          dirEditBtn.hidden = true;
          dirInput.hidden = false;
          dirSaveBtn.hidden = false;
          dirCancelBtn.hidden = false;
          dirInput.focus();
          dirInput.select();
        }

        function exitEditMode() {
          dirInput.hidden = true;
          dirSaveBtn.hidden = true;
          dirCancelBtn.hidden = true;
          dirDisplay.hidden = false;
          dirEditBtn.hidden = false;
        }

        async function callTicketReviewAction(ticketNum, action) {
          const response = await fetch(`/api/ticket/${encodeURIComponent(projectSlug)}/${encodeURIComponent(ticketNum)}/${encodeURIComponent(action)}`, { method: "POST" });
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          await loadTicket(ticketNum);
        }

        panelContent.addEventListener("click", async (event) => {
          const button = event.target.closest("button[data-review-action][data-ticket-num]");
          if (!button) return;
          button.disabled = true;
          try {
            await callTicketReviewAction(button.dataset.ticketNum, button.dataset.reviewAction);
          } catch (error) {
            button.disabled = false;
          }
        });

        function chainSummary(chainStatus, chainTicketNum, pauseReason) {
          const status = (chainStatus || "stopped").toLowerCase();
          if (status === "running") return `Chain: running — ticket #${chainTicketNum || "?"}`;
          if (status === "paused") return `Chain: paused — ${pauseReason || "waiting"}`;
          if (status === "done") return "Chain: idle";
          if (status === "stopped") return pauseReason ? `Chain: idle — ${pauseReason}` : "Chain: idle";
          return "Chain: idle";
        }

        function applyChainState(payload) {
          const chainStatus = (payload && payload.chain_status) || "stopped";
          const chainTicketNum = payload && payload.chain_current_ticket_num;
          const pauseReason = payload && payload.chain_pause_reason;
          const normalized = String(chainStatus).toLowerCase();
          chainStatusDot.className = `chain-dot ${esc(normalized)}`;
          chainStatusText.textContent = chainSummary(normalized, chainTicketNum, pauseReason);
          chainStartBtn.disabled = normalized === "running";
          chainStopBtn.disabled = normalized !== "running";
        }

        async function callChainAction(action) {
          const response = await fetch(`/api/chain/${encodeURIComponent(projectSlug)}/${encodeURIComponent(action)}`, { method: "POST" });
          const payload = await response.json().catch(() => null);
          if (!response.ok) throw new Error((payload && payload.error) || `HTTP ${response.status}`);
          return payload;
        }

        chainStartBtn.addEventListener("click", async () => {
          chainStartBtn.disabled = true;
          try {
            await callChainAction("start");
          } catch (error) {
            showToast(error.message || "Failed to start chain.");
            chainStartBtn.disabled = false;
          }
        });

        chainStopBtn.addEventListener("click", async () => {
          chainStopBtn.disabled = true;
          try {
            await callChainAction("stop");
          } catch (error) {
            showToast(error.message || "Failed to stop chain.");
            chainStopBtn.disabled = false;
          }
        });

        applyChainState({
          chain_status: {{ (chain.status if chain else 'stopped')|tojson }},
          chain_current_ticket_num: {{ chain_current_ticket_num|tojson }},
          chain_pause_reason: {{ chain_pause_reason|tojson }},
        });

        if (dirEditBtn) {
          dirEditBtn.addEventListener("click", enterEditMode);
        }

        if (dirCancelBtn) {
          dirCancelBtn.addEventListener("click", () => {
            dirInput.value = {{ (project.dir or "")|tojson }};
            exitEditMode();
          });
        }

        if (dirSaveBtn) {
          dirSaveBtn.addEventListener("click", async () => {
            const directory = (dirInput.value || "").trim();
            try {
              const response = await fetch(`/api/project/${encodeURIComponent(projectSlug)}/directory`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ directory }),
              });
              const payload = await response.json().catch(() => null);
              if (!response.ok) {
                throw new Error((payload && payload.error) || `HTTP ${response.status}`);
              }
              renderDirectoryDisplay(payload ? payload.directory : directory);
              const missing = Boolean(payload && payload.directory && payload.exists_on_disk === false);
              if (dirWarning) dirWarning.hidden = !missing;
              exitEditMode();
            } catch (error) {
              showToast(error.message || "Failed to update project directory.");
            }
          });
        }

        function setConnection(isConnected, label) {
          const dot = document.getElementById("project-sse-dot");
          const text = document.getElementById("project-sse-label");
          dot.classList.remove("connected", "disconnected");
          dot.classList.add(isConnected ? "connected" : "disconnected");
          text.textContent = label;
        }

        function ticketCardMarkup(ticket) {
          const tags = (ticket.tags || []).map((tag) => `<span class="tag-pill tag-${esc((ticket.tag_tones || {})[tag] || "blue")}">${esc(tag)}</span>`).join("");
          const assignee = ticket.assignee ? `<div class="agent-row"><span class="agent-avatar">${esc(ticket.assignee_initials || "")}</span><span class="agent-name">${esc(ticket.assignee)}</span></div>` : "";
          const due = ticket.due_date ? `<div class="ticket-due ${ticket.is_overdue ? "overdue" : ""}">${esc(ticket.due_date)}</div>` : "";
          const subtask = ticket.subtask_total > 0 ? `<div class="progress-meta"><span>subtasks</span><span>${ticket.subtask_done}/${ticket.subtask_total}</span></div><div class="mini-progress" role="img" aria-label="subtask progress"><div class="mini-progress-value" style="--progress: ${ticket.subtask_pct}%;"></div></div>` : "";
          return `<article class="ticket-card priority-${esc((ticket.priority || "none").toLowerCase())} ${ticket.active_agent ? "has-active-agent" : ""}">
            <div class="ticket-head"><div><div class="ticket-id">#${ticket.num}</div><div class="ticket-title">${esc(ticket.title)}</div></div>${due}</div>
            <div class="pill-row"><span class="priority-pill p-${esc((ticket.priority || "none").toLowerCase())}">${esc((ticket.priority || "none").toLowerCase())}</span>${tags || ""}</div>
            ${assignee}
            ${subtask}
          </article>`;
        }

        function animateFlip(node, firstRect) {
          const lastRect = node.getBoundingClientRect();
          const dx = firstRect.left - lastRect.left;
          const dy = firstRect.top - lastRect.top;
          node.style.transform = `translate(${dx}px, ${dy}px)`;
          requestAnimationFrame(() => {
            node.style.transition = "transform 0.42s ease";
            node.style.transform = "translate(0, 0)";
            setTimeout(() => {
              node.style.transition = "";
              node.style.transform = "";
            }, 440);
          });
        }

        function attachTicketHandler(link) {
          link.addEventListener("click", (event) => {
            if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
            event.preventDefault();
            loadTicket(link.dataset.ticketNum);
          });
        }

        function ensureEmptyState(status) {
          const body = document.querySelector(`[data-column-body="${status}"]`);
          if (!body) return;
          const hasCards = body.querySelector(".ticket-link");
          let empty = body.querySelector(".kanban-empty");
          if (!hasCards && !empty) {
            empty = document.createElement("p");
            empty.className = "kanban-empty";
            empty.textContent = "No tickets.";
            body.appendChild(empty);
          }
          if (hasCards && empty) empty.remove();
        }

        function applyBoardUpdate(payload) {
          if (!payload || !payload.grouped) return;
          const allIncoming = new Map();
          statusOrder.forEach((status) => {
            (payload.grouped[status] || []).forEach((ticket) => allIncoming.set(String(ticket.num), { status, ticket }));
          });

          document.querySelectorAll(".ticket-link[data-ticket-num]").forEach((node) => {
            if (allIncoming.has(node.dataset.ticketNum)) return;
            node.classList.add("is-leaving");
            setTimeout(() => {
              node.remove();
              statusOrder.forEach(ensureEmptyState);
            }, 280);
          });

          statusOrder.forEach((status) => {
            const body = document.querySelector(`[data-column-body="${status}"]`);
            if (!body) return;
            const desired = payload.grouped[status] || [];
            desired.forEach((ticket) => {
              const num = String(ticket.num);
              let link = document.querySelector(`.ticket-link[data-ticket-num="${num}"]`);
              if (!link) {
                link = document.createElement("a");
                link.className = "ticket-link is-entering";
                link.href = `/project/${encodeURIComponent(projectSlug)}/ticket/${encodeURIComponent(num)}`;
                link.dataset.ticketNum = num;
                link.dataset.ticketStatus = status;
                link.setAttribute("role", "button");
                link.setAttribute("aria-label", `Open ticket #${num} details panel`);
                link.innerHTML = ticketCardMarkup(ticket);
                attachTicketHandler(link);
                body.appendChild(link);
                requestAnimationFrame(() => link.classList.remove("is-entering"));
              } else {
                const firstRect = link.getBoundingClientRect();
                link.dataset.ticketStatus = status;
                link.innerHTML = ticketCardMarkup(ticket);
                if (link.parentElement !== body) {
                  body.appendChild(link);
                  animateFlip(link, firstRect);
                }
              }
            });

            desired.forEach((ticket) => {
              const node = body.querySelector(`.ticket-link[data-ticket-num="${ticket.num}"]`);
              if (node) body.appendChild(node);
            });

            const count = document.querySelector(`[data-count-for="${status}"]`);
            if (count) count.textContent = String(desired.length);
            ensureEmptyState(status);
          });
        }

        if (!window.EventSource) {
          setConnection(false, "SSE unsupported");
          return;
        }

        const params = new URLSearchParams({ project: projectSlug });
        if (filters.status) params.set("status", filters.status);
        if (filters.priority) params.set("priority", filters.priority);
        if (filters.tag) params.set("tag", filters.tag);

        const source = new EventSource(`/events?${params.toString()}`);
        source.addEventListener("open", () => setConnection(true, "connected"));
        source.addEventListener("project_board", (event) => {
          try {
            const payload = JSON.parse(event.data);
            applyBoardUpdate(payload);
            applyChainState(payload);
            setConnection(true, "connected");
          } catch (_err) {
            setConnection(false, "parse error");
          }
        });
        source.onerror = () => setConnection(false, "reconnecting…");
      })();
    </script>
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
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
      :root {
        --font-heading: 'Playfair Display', Georgia, serif;
        --font-body: 'Inter', ui-sans-serif, sans-serif;
        --font-mono: 'JetBrains Mono', ui-monospace, monospace;
        --fs-h1: 2rem;
        --fs-h2: 1.25rem;
        --fs-card-title: 1rem;
        --fs-nav: 0.875rem;
        --fs-body: 0.875rem;
        --fs-small: 0.75rem;
        --fs-button: 0.75rem;
        --fs-mono: 0.8rem;
        --fw-h1: 700;
        --fw-h2: 600;
        --fw-card-title: 600;
        --fw-nav: 500;
        --fw-body: 400;
        --fw-small: 400;
        --fw-button: 500;
        --fw-mono: 400;
        --color-bg: #0a0e1a;
        --color-bg-alt: #0f1420;
        --color-panel: #151b2b;
        --color-panel-soft: #1b2236;
        --color-text: #e2e8f0;
        --color-muted: #8892a8;
        --color-border: rgba(255,255,255,0.08);
        --color-shadow: rgba(0,0,0,0.42);
        --color-high: #ef4444;
        --color-medium: #f97316;
        --color-low: #8892a8;
        --color-done: #22c55e;
        --color-in-progress: #3b82f6;
        --color-blocked: #f59e0b;
        --color-todo: #94a3b8;
      }
      body { font-family: var(--font-body); background: var(--color-bg) !important; color: var(--color-text); }
      h1, h2, h3, h4, h5, h6 { letter-spacing: -0.01em; font-family: var(--font-body); } h1 { font-family: var(--font-heading); }
      .text-muted { color: var(--color-muted) !important; }
      .card { background: var(--color-panel); border: 1px solid var(--color-border); border-radius: 14px; box-shadow: 0 12px 36px var(--color-shadow); color: var(--color-text); }
      .card.priority-high { border-left: 4px solid var(--color-high); }
      .card.priority-medium { border-left: 4px solid var(--color-medium); }
      .card.priority-low, .card.priority-none { border-left: 4px solid var(--color-low); }
      .badge.status-badge { color: #061018; font-weight: var(--fw-button); }
      .badge.status-done { background: var(--status-done); }
      .badge.status-in-progress { background: var(--status-in-progress); color: #eaf2ff; }
      .badge.status-blocked { background: var(--status-blocked); }
      .badge.status-todo, .badge.status-pending, .badge.status-skipped { background: var(--status-todo); }
      .priority-pill, .tag-pill-muted { background: var(--color-bg-alt); border-color: var(--color-border); }
      .priority-pill { color: var(--color-text); }
      .tag-pill-muted { color: var(--color-muted); }
      .ticket-id, .project-code { font-family: var(--font-mono); }
      .progress-ring { --ring-size: 42px; --ring-stroke: 4; --ring-progress: 0; --ring-track: rgba(255,255,255,0.14); --ring-color: var(--status-in-progress); width: var(--ring-size); height: var(--ring-size); }
      .progress-ring svg { width: 100%; height: 100%; transform: rotate(-90deg); }
      .progress-ring-track, .progress-ring-value { fill: none; stroke-width: var(--ring-stroke); }
      .progress-ring-track { stroke: var(--ring-track); }
      .progress-ring-value { stroke: var(--ring-color); stroke-linecap: round; stroke-dasharray: 100; stroke-dashoffset: calc(100 - var(--ring-progress)); transition: stroke-dashoffset 450ms ease; }
      .agent-avatar { --avatar-size: 2rem; width: var(--avatar-size); height: var(--avatar-size); border-radius: 999px; display: inline-flex; align-items: center; justify-content: center; font-family: var(--font-body); font-size: var(--fs-small); font-weight: var(--fw-card-title); background: var(--color-bg-alt); border: 1px solid var(--color-border); color: var(--color-text); }
      .list-group-item, .form-control { background: var(--color-panel-soft); border-color: var(--color-border); color: var(--color-text); }
      .form-control::placeholder { color: var(--color-muted); }
      .form-control:focus { background: var(--color-panel-soft); color: var(--color-text); border-color: var(--status-in-progress); box-shadow: 0 0 0 0.2rem rgba(59,130,246,0.2); }
      .btn-outline-secondary { color: var(--color-muted); border-color: var(--color-border); font-family: var(--font-body); font-weight: var(--fw-button); font-size: var(--fs-small); }
      .btn-outline-secondary:hover { color: var(--color-text); background: rgba(255,255,255,0.06); }
      .ticket-page-title { font-family: var(--font-heading); font-size: var(--fs-h1); font-weight: var(--fw-h1); }
      .ticket-section-title { font-family: var(--font-body); font-size: var(--fs-h2); font-weight: var(--fw-h2); }
      .body-text { font-family: var(--font-body); font-weight: var(--fw-body); font-size: var(--fs-body); }
      .secondary-text { font-family: var(--font-body); font-weight: var(--fw-body); font-size: var(--fs-small); color: var(--color-muted) !important; }
      .btn, .badge { font-family: var(--font-body); }
      .btn, .btn-sm { font-weight: var(--fw-button); font-size: var(--fs-small); }
      .pill { font-family: var(--font-body); font-weight: var(--fw-button); font-size: var(--fs-small); }
    </style>
  </head>
  <body>
    <main class="container py-4 page">
      <div class="d-flex justify-content-between align-items-center mb-3">
        <h1 class="m-0 ticket-page-title">#{{ ticket.num }} {{ ticket.title }}</h1>
        <a href="{{ url_for('project_detail', slug=project.slug) }}" class="btn btn-sm btn-outline-secondary">Back to project</a>
      </div>

      <div class="card shadow-sm mb-3">
        <div class="card-body">
          <div class="d-flex flex-wrap gap-2 mb-2">
            <span class="badge status-badge status-{{ ticket.status }}">{{ ticket.status }}</span>
            <span class="badge ticket-id pill priority-pill">priority: {{ ticket.priority }}</span>
            {% if ticket.tags %}
              {% for tag in ticket.tags %}
              <span class="badge rounded-pill pill tag-pill-muted">{{ tag }}</span>
              {% endfor %}
            {% endif %}
          </div>
          <h2 class="ticket-section-title">Description</h2>
          {% if ticket.description %}
          <p class="mb-0 body-text">{{ ticket.description }}</p>
          {% else %}
          <p class="text-muted mb-0 secondary-text">No description.</p>
          {% endif %}
          {% if ticket.close_note %}
          <hr>
          <h2 class="ticket-section-title">Close notes</h2>
          <p class="mb-0 body-text">{{ ticket.close_note }}</p>
          {% endif %}
        </div>
      </div>

      <div class="row g-3 mb-3">
        <div class="col-12 col-md-6">
          <div class="card h-100 shadow-sm priority-low">
            <div class="card-body">
              <h2 class="ticket-section-title">Dependencies</h2>
              <div class="small text-muted mb-1 secondary-text">blocked by</div>
              {% if blocked_by %}
              <ul class="mb-3">
                {% for dep in blocked_by %}
                <li class="body-text"><a href="{{ url_for('ticket_detail', slug=project.slug, ticket_num=dep.num) }}"><span class="ticket-id">#{{ dep.num }}</span> {{ dep.title }}</a></li>
                {% endfor %}
              </ul>
              {% else %}
              <p class="text-muted small secondary-text">None.</p>
              {% endif %}

              <div class="small text-muted mb-1 secondary-text">blocks</div>
              {% if blocks %}
              <ul class="mb-0">
                {% for dep in blocks %}
                <li class="body-text"><a href="{{ url_for('ticket_detail', slug=project.slug, ticket_num=dep.num) }}"><span class="ticket-id">#{{ dep.num }}</span> {{ dep.title }}</a></li>
                {% endfor %}
              </ul>
              {% else %}
              <p class="text-muted small mb-0 secondary-text">None.</p>
              {% endif %}
            </div>
          </div>
        </div>

        <div class="col-12 col-md-6">
          <div class="card h-100 shadow-sm priority-low">
            <div class="card-body">
              <h2 class="ticket-section-title">Subtasks</h2>
              {% if subtasks %}
              <ul class="list-group list-group-flush">
                {% for subtask in subtasks %}
                <li class="list-group-item px-0 d-flex justify-content-between align-items-center">
                  <span class="body-text"><span class="ticket-id">#{{ subtask.num }}</span> {{ subtask.title }}</span>
                  <span class="badge status-badge pill {{ 'status-done' if subtask.status == 'done' else 'status-todo' }}">{{ subtask.status }}</span>
                </li>
                {% endfor %}
              </ul>
              {% else %}
              <p class="text-muted small mb-0 secondary-text">No subtasks.</p>
              {% endif %}
            </div>
          </div>
        </div>
      </div>

      <div class="card shadow-sm">
        <div class="card-body">
          <h2 class="ticket-section-title">History / audit log</h2>
          {% if history %}
          <ul class="list-group list-group-flush">
            {% for item in history %}
            <li class="list-group-item px-0">
              <div class="small text-muted ticket-id secondary-text">{{ item.changed_at }}</div>
              <div class="body-text">{{ item.message }}</div>
            </li>
            {% endfor %}
          </ul>
          {% else %}
          <p class="text-muted small mb-0 secondary-text">No history yet.</p>
          {% endif %}
        </div>
      </div>
    </main>
  </body>
</html>
"""
