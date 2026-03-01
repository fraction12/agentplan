#!/usr/bin/env python3
"""Read-only web dashboard for agentplan projects and tickets."""

import json
import os
import time
from collections import defaultdict
from datetime import datetime

from flask import Flask, Response, abort, render_template_string, request, stream_with_context, url_for

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
    <title>agentplan mission control</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
      :root {
        --font-heading: 'Playfair Display', Georgia, serif;
        --font-body: 'Inter', ui-sans-serif, sans-serif;
        --font-mono: 'JetBrains Mono', ui-monospace, monospace;

        --color-bg: #0a0e1a;
        --color-bg-alt: #0f1420;
        --color-panel: #151b2b;
        --color-panel-soft: #1b2236;
        --color-text: #e2e8f0;
        --color-muted: #8892a8;
        --color-border: rgba(255, 255, 255, 0.08);
        --color-shadow: rgba(0, 0, 0, 0.42);

        --color-done: #22c55e;
        --color-in-progress: #3b82f6;
        --color-blocked: #f59e0b;
        --color-todo: #94a3b8;
        --color-skipped: #64748b;
      }

      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: var(--font-body);
        background: var(--color-bg);
        color: var(--color-text);
      }

      .page {
        width: min(1180px, 92vw);
        margin: 0 auto;
        padding: 24px 0 32px;
      }

      .topbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 20px;
        padding: 14px 16px;
        background: rgba(255, 255, 255, 0.02);
        border: 1px solid var(--color-border);
        border-radius: 14px;
      }
      .brand {
        font-weight: 700;
        font-size: 1rem;
        letter-spacing: -0.01em;
      }
      .topbar-right {
        display: flex;
        align-items: center;
        gap: 12px;
        color: var(--color-muted);
        font-size: 0.9rem;
      }
      .clock {
        font-family: var(--font-mono);
        color: var(--color-text);
      }
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
      .status-dot.connected { background: var(--color-done); box-shadow: 0 0 0 4px rgba(34, 197, 94, 0.15); }
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
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--color-muted);
      }
      .stat-value {
        margin-top: 8px;
        font-size: clamp(1.7rem, 4vw, 2.3rem);
        font-weight: 700;
        line-height: 1;
      }

      .projects-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 14px;
      }
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
        transition: transform 140ms ease, border-color 140ms ease;
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
        font-family: var(--font-heading);
        font-size: 1.24rem;
        line-height: 1.2;
      }
      .project-code {
        margin-top: 4px;
        font-family: var(--font-mono);
        font-size: 0.8rem;
        color: var(--color-muted);
      }

      .progress-ring {
        --ring-size: 56px;
        --ring-stroke: 3.6;
        --ring-progress: 0;
        --ring-track: rgba(255, 255, 255, 0.14);
        --ring-color: var(--color-in-progress);
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
        font-size: 0.75rem;
        font-family: var(--font-mono);
      }

      .project-meta {
        margin-top: 10px;
        display: grid;
        gap: 7px;
      }
      .project-progress-text,
      .project-last-activity {
        font-size: 0.86rem;
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
        font-size: 0.8rem;
        color: var(--color-muted);
      }
      .dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
      }
      .dot.todo { background: var(--color-todo); }
      .dot.in-progress { background: var(--color-in-progress); }
      .dot.blocked { background: var(--color-blocked); }
      .dot.done { background: var(--color-done); }
      .dot.skipped { background: var(--color-skipped); }

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
        <div class="brand">⚡ agentplan</div>
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
      <section class="projects-grid" id="projects-grid">
        {% for project in projects %}
        <a class="project-link" href="{{ url_for('project_detail', slug=project.slug) }}" data-project-id="{{ project.id }}">
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
                {% for status in ["todo", "in-progress", "blocked", "done", "skipped"] %}
                <span class="dot-item"><span class="dot {{ status }}"></span><span class="dot-value" data-status="{{ status }}">{{ project.breakdown.get(status, 0) }}</span></span>
                {% endfor %}
              </div>
              <div class="project-last-activity">Last activity: <span class="project-updated-at">{{ project.updated_at or "n/a" }}</span></div>
            </div>
          </article>
        </a>
        {% endfor %}
      </section>
      {% else %}
      <div class="empty">No projects found.</div>
      {% endif %}
    </main>

    <script>
      const statusOrder = ["todo", "in-progress", "blocked", "done", "skipped"];

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

      function renderProjects(projects) {
        const byId = new Map((projects || []).map((p) => [String(p.id), p]));
        document.querySelectorAll("[data-project-id]").forEach((card) => {
          const project = byId.get(card.dataset.projectId);
          if (!project) return;

          const ring = card.querySelector(".progress-ring");
          ring.style.setProperty("--ring-progress", String(project.progress_pct || 0));
          card.querySelector(".project-progress-percent").textContent = `${project.progress_pct || 0}%`;
          card.querySelector(".project-progress-done").textContent = String(project.done_count || 0);
          card.querySelector(".project-progress-total").textContent = String(project.ticket_count || 0);
          card.querySelector(".project-updated-at").textContent = project.updated_at || "n/a";

          const breakdown = project.breakdown || {};
          card.querySelectorAll(".dot-value").forEach((node) => {
            const key = node.dataset.status;
            node.textContent = String(breakdown[key] || 0);
          });
        });
      }

      (function subscribe() {
        setClock();
        setInterval(() => setClock(), 1000);

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
            renderProjects(payload.projects || []);
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
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
      :root {
        --font-heading: 'Playfair Display', Georgia, serif;
        --font-body: 'Inter', ui-sans-serif, sans-serif;
        --font-mono: 'JetBrains Mono', ui-monospace, monospace;
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
      h1, h2, h3, h4, h5, h6 { font-family: var(--font-heading); letter-spacing: -0.01em; }
      .text-muted { color: var(--color-muted) !important; }
      .card { background: var(--color-panel); border: 1px solid var(--color-border); border-radius: 14px; box-shadow: 0 12px 36px var(--color-shadow); color: var(--color-text); }
      .card.priority-high { border-left: 4px solid var(--color-high); }
      .card.priority-medium { border-left: 4px solid var(--color-medium); }
      .card.priority-low, .card.priority-none { border-left: 4px solid var(--color-low); }
      .badge.status-badge { color: #061018; font-weight: 700; }
      .badge.status-done { background: var(--color-done); }
      .badge.status-in-progress { background: var(--color-in-progress); color: #eaf2ff; }
      .badge.status-blocked { background: var(--color-blocked); }
      .badge.status-todo, .badge.status-pending, .badge.status-skipped { background: var(--color-todo); }
      .ticket-id, .project-code { font-family: var(--font-mono); }
      .progress-ring { --ring-size: 42px; --ring-stroke: 4; --ring-progress: 0; --ring-track: rgba(255,255,255,0.14); --ring-color: var(--color-in-progress); width: var(--ring-size); height: var(--ring-size); }
      .progress-ring svg { width: 100%; height: 100%; transform: rotate(-90deg); }
      .progress-ring-track, .progress-ring-value { fill: none; stroke-width: var(--ring-stroke); }
      .progress-ring-track { stroke: var(--ring-track); }
      .progress-ring-value { stroke: var(--ring-color); stroke-linecap: round; stroke-dasharray: 100; stroke-dashoffset: calc(100 - var(--ring-progress)); transition: stroke-dashoffset 450ms ease; }
      .agent-avatar { --avatar-size: 2rem; width: var(--avatar-size); height: var(--avatar-size); border-radius: 999px; display: inline-flex; align-items: center; justify-content: center; font-family: var(--font-mono); font-size: 0.75rem; font-weight: 600; background: var(--color-bg-alt); border: 1px solid var(--color-border); color: var(--color-text); }
      .list-group-item, .form-control { background: var(--color-panel-soft); border-color: var(--color-border); color: var(--color-text); }
      .form-control::placeholder { color: var(--color-muted); }
      .form-control:focus { background: var(--color-panel-soft); color: var(--color-text); border-color: var(--color-in-progress); box-shadow: 0 0 0 0.2rem rgba(59,130,246,0.2); }
      .btn-outline-secondary { color: var(--color-muted); border-color: var(--color-border); }
      .btn-outline-secondary:hover { color: var(--color-text); background: rgba(255,255,255,0.06); }
    </style>
  </head>
  <body>
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
          <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('project_detail', slug=project.slug) }}">Reset</a>
        </div>
      </form>

      {% for status in status_order %}
      <section class="mb-4">
        <h2 class="h5 mb-2">{{ status_labels[status] }} <span class="text-muted">({{ grouped[status]|length }})</span></h2>
        {% if grouped[status] %}
        <div class="list-group">
          {% for ticket in grouped[status] %}
          <article class="list-group-item card priority-{{ ticket.priority|lower }}">
            <div class="d-flex justify-content-between align-items-start gap-3">
              <div>
                <div><strong><a class="text-decoration-none" href="{{ url_for('ticket_detail', slug=project.slug, ticket_num=ticket.num) }}">#{{ ticket.num }} {{ ticket.title }}</a></strong></div>
                {% if ticket.description %}<div class="small mt-1">{{ ticket.description }}</div>{% endif %}
                {% if ticket.tags %}<div class="small text-muted mt-1">tags: {{ ticket.tags|join(', ') }}</div>{% endif %}
                {% if ticket.dependencies %}<div class="small text-muted">depends on: {{ ticket.dependencies|join(', ') }}</div>{% endif %}
              </div>
              <div class="text-end">
                <span class="badge ticket-id" style="background: var(--color-bg-alt); color: var(--color-text); border-color: var(--color-border);">{{ ticket.priority }}</span>
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
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
      :root {
        --font-heading: 'Playfair Display', Georgia, serif;
        --font-body: 'Inter', ui-sans-serif, sans-serif;
        --font-mono: 'JetBrains Mono', ui-monospace, monospace;
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
      h1, h2, h3, h4, h5, h6 { font-family: var(--font-heading); letter-spacing: -0.01em; }
      .text-muted { color: var(--color-muted) !important; }
      .card { background: var(--color-panel); border: 1px solid var(--color-border); border-radius: 14px; box-shadow: 0 12px 36px var(--color-shadow); color: var(--color-text); }
      .card.priority-high { border-left: 4px solid var(--color-high); }
      .card.priority-medium { border-left: 4px solid var(--color-medium); }
      .card.priority-low, .card.priority-none { border-left: 4px solid var(--color-low); }
      .badge.status-badge { color: #061018; font-weight: 700; }
      .badge.status-done { background: var(--color-done); }
      .badge.status-in-progress { background: var(--color-in-progress); color: #eaf2ff; }
      .badge.status-blocked { background: var(--color-blocked); }
      .badge.status-todo, .badge.status-pending, .badge.status-skipped { background: var(--color-todo); }
      .ticket-id, .project-code { font-family: var(--font-mono); }
      .progress-ring { --ring-size: 42px; --ring-stroke: 4; --ring-progress: 0; --ring-track: rgba(255,255,255,0.14); --ring-color: var(--color-in-progress); width: var(--ring-size); height: var(--ring-size); }
      .progress-ring svg { width: 100%; height: 100%; transform: rotate(-90deg); }
      .progress-ring-track, .progress-ring-value { fill: none; stroke-width: var(--ring-stroke); }
      .progress-ring-track { stroke: var(--ring-track); }
      .progress-ring-value { stroke: var(--ring-color); stroke-linecap: round; stroke-dasharray: 100; stroke-dashoffset: calc(100 - var(--ring-progress)); transition: stroke-dashoffset 450ms ease; }
      .agent-avatar { --avatar-size: 2rem; width: var(--avatar-size); height: var(--avatar-size); border-radius: 999px; display: inline-flex; align-items: center; justify-content: center; font-family: var(--font-mono); font-size: 0.75rem; font-weight: 600; background: var(--color-bg-alt); border: 1px solid var(--color-border); color: var(--color-text); }
      .list-group-item, .form-control { background: var(--color-panel-soft); border-color: var(--color-border); color: var(--color-text); }
      .form-control::placeholder { color: var(--color-muted); }
      .form-control:focus { background: var(--color-panel-soft); color: var(--color-text); border-color: var(--color-in-progress); box-shadow: 0 0 0 0.2rem rgba(59,130,246,0.2); }
      .btn-outline-secondary { color: var(--color-muted); border-color: var(--color-border); }
      .btn-outline-secondary:hover { color: var(--color-text); background: rgba(255,255,255,0.06); }
    </style>
  </head>
  <body>
    <main class="container py-4">
      <div class="d-flex justify-content-between align-items-center mb-3">
        <h1 class="h4 m-0">#{{ ticket.num }} {{ ticket.title }}</h1>
        <a href="{{ url_for('project_detail', slug=project.slug) }}" class="btn btn-sm btn-outline-secondary">Back to project</a>
      </div>

      <div class="card shadow-sm mb-3">
        <div class="card-body">
          <div class="d-flex flex-wrap gap-2 mb-2">
            <span class="badge status-badge status-{{ ticket.status }}">{{ ticket.status }}</span>
            <span class="badge ticket-id" style="background: var(--color-bg-alt); color: var(--color-text); border-color: var(--color-border);">priority: {{ ticket.priority }}</span>
            {% if ticket.tags %}
              {% for tag in ticket.tags %}
              <span class="badge rounded-pill" style="background: var(--color-bg-alt); border-color: var(--color-border); color: var(--color-muted);">{{ tag }}</span>
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
          <div class="card h-100 shadow-sm priority-low">
            <div class="card-body">
              <h2 class="h6">Dependencies</h2>
              <div class="small text-muted mb-1">blocked by</div>
              {% if blocked_by %}
              <ul class="mb-3">
                {% for dep in blocked_by %}
                <li><a href="{{ url_for('ticket_detail', slug=project.slug, ticket_num=dep.num) }}">#{{ dep.num }} {{ dep.title }}</a></li>
                {% endfor %}
              </ul>
              {% else %}
              <p class="text-muted small">None.</p>
              {% endif %}

              <div class="small text-muted mb-1">blocks</div>
              {% if blocks %}
              <ul class="mb-0">
                {% for dep in blocks %}
                <li><a href="{{ url_for('ticket_detail', slug=project.slug, ticket_num=dep.num) }}">#{{ dep.num }} {{ dep.title }}</a></li>
                {% endfor %}
              </ul>
              {% else %}
              <p class="text-muted small mb-0">None.</p>
              {% endif %}
            </div>
          </div>
        </div>

        <div class="col-12 col-md-6">
          <div class="card h-100 shadow-sm priority-low">
            <div class="card-body">
              <h2 class="h6">Subtasks</h2>
              {% if subtasks %}
              <ul class="list-group list-group-flush">
                {% for subtask in subtasks %}
                <li class="list-group-item px-0 d-flex justify-content-between align-items-center">
                  <span>#{{ subtask.num }} {{ subtask.title }}</span>
                  <span class="badge status-badge {{ 'status-done' if subtask.status == 'done' else 'status-todo' }}">{{ subtask.status }}</span>
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
    return os.environ.get("AGENTPLAN_DB", os.path.expanduser("~/.agentplan/agentplan.db"))


def _fetch_projects_with_stats(conn):
    projects = conn.execute(
        "SELECT id, slug, title, status, updated_at FROM projects ORDER BY updated_at DESC, id DESC"
    ).fetchall()
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
        in_flight = breakdown["todo"] + breakdown["in-progress"] + breakdown["blocked"]
        progress = int(round((done / total) * 100)) if total else 0
        out.append(
            {
                "id": p["id"],
                "slug": p["slug"],
                "title": p["title"],
                "status": p["status"],
                "updated_at": p["updated_at"],
                "breakdown": breakdown,
                "ticket_count": total,
                "done_count": done,
                "in_flight_count": in_flight,
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


def _project_stats_payload():
    conn = get_connection(_db_path())
    try:
        projects = _fetch_projects_with_stats(conn)

        completed_today = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM tickets
            WHERE status IN ('done', 'skipped')
              AND completed_at IS NOT NULL
              AND date(completed_at) = date('now', 'localtime')
            """
        ).fetchone()["c"]

        active_agents = conn.execute(
            """
            SELECT COUNT(DISTINCT agent) AS c
            FROM (
                SELECT TRIM(started_by) AS agent FROM tickets WHERE started_by IS NOT NULL AND TRIM(started_by) != ''
                UNION
                SELECT TRIM(done_by) AS agent FROM tickets WHERE done_by IS NOT NULL AND TRIM(done_by) != ''
            )
            """
        ).fetchone()["c"]
    finally:
        conn.close()

    summary = {
        "active_projects": sum(1 for p in projects if p["status"] != "completed"),
        "tickets_in_flight": sum(p["in_flight_count"] for p in projects),
        "completed_today": int(completed_today or 0),
        "active_agents": int(active_agents or 0),
    }

    return {
        "projects": projects,
        "summary": summary,
        "server_time": datetime.now().isoformat(timespec="seconds"),
    }



def create_app():
    app = Flask(__name__)

    @app.route("/")
    def index():
        payload = _project_stats_payload()
        return render_template_string(INDEX_TEMPLATE, projects=payload["projects"], summary=payload["summary"])

    @app.route("/api/stats")
    def api_stats():
        return _project_stats_payload()

    @app.route("/events")
    def events():
        interval = max(1, min(int(request.args.get("interval", "2")), 30))

        @stream_with_context
        def event_stream():
            while True:
                payload = _project_stats_payload()
                yield f"event: project_stats\\ndata: {json.dumps(payload)}\\n\\n"
                time.sleep(interval)

        return Response(event_stream(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.route("/project/<slug>")
    def project_detail(slug):
        status_filter = request.args.get("status", "").strip().lower()
        priority_filter = request.args.get("priority", "").strip().lower()
        tag_filter = request.args.get("tag", "").strip().lower()

        conn = get_connection(_db_path())
        try:
            project = conn.execute("SELECT id, slug, title, status FROM projects WHERE slug=?", (slug,)).fetchone()
            if not project:
                abort(404)
            rows = conn.execute(
                """
                SELECT id, num, title, description, status, priority, tags, depends_on
                FROM tickets
                WHERE project_id=?
                ORDER BY num
                """,
                (project["id"],),
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

    @app.route("/project/<slug>/ticket/<int:ticket_num>")
    def ticket_detail(slug, ticket_num):
        conn = get_connection(_db_path())
        try:
            project = conn.execute("SELECT id, slug, title, status FROM projects WHERE slug=?", (slug,)).fetchone()
            if not project:
                abort(404)

            row = conn.execute(
                """
                SELECT id, num, title, description, status, priority, tags, depends_on, close_note
                FROM tickets
                WHERE project_id=? AND num=?
                """,
                (project["id"], ticket_num),
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
                    (project["id"], *dep_nums),
                ).fetchall()
                blocked_by = [dict(r) for r in blocked_rows]

            project_ticket_rows = conn.execute(
                "SELECT num, title, depends_on FROM tickets WHERE project_id=? AND id!=? ORDER BY num",
                (project["id"], ticket["id"]),
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
