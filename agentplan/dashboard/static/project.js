(function bootProjectPage() {
  const cfg = window.__projectPage;
  if (!cfg) return;

  function esc(v) {
    return String(v ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  setClock("project-clock");
  setInterval(() => setClock("project-clock"), 1000);

  const panel = document.getElementById("ticket-panel");
  const backdrop = document.getElementById("ticket-panel-backdrop");
  const closeBtn = document.getElementById("ticket-panel-close");
  const panelId = document.getElementById("panel-ticket-id");
  const panelTitle = document.getElementById("panel-ticket-title");
  const panelContent = document.getElementById("ticket-panel-content");
  const projectSlug = cfg.projectSlug;

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
        <h3>Title <button class="ticket-panel-edit-btn" onclick="editTicketField(${esc(data.num)}, 'title', ${JSON.stringify(data.title || '').replace(/</g,'&lt;')})">✎</button></h3>
        <p class="panel-description">${esc(data.title || "")}</p>
      </section>
      <section class="panel-block">
        <h3>Description <button class="ticket-panel-edit-btn" onclick="editTicketField(${esc(data.num)}, 'description', ${JSON.stringify(data.description || '').replace(/</g,'&lt;')})">✎</button></h3>
        <p class="panel-description">${esc(data.description || "No description.")}</p>
      </section>
      <section class="panel-block">
        <h3>Priority <button class="ticket-panel-edit-btn" onclick="editTicketField(${esc(data.num)}, 'priority', '${esc(data.priority || 'none')}')">✎</button></h3>
        <p class="panel-description">${esc((data.priority || 'none'))}</p>
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
    setTimeout(() => {
      backdrop.hidden = true;
    }, 260);
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

  function renderDirectoryDisplay(directory) {
    if (!dirDisplay) return;
    const value = String(directory || "").trim();
    if (!value) {
      dirDisplay.innerHTML = '<span class="project-dir-empty">No directory set</span>';
      return;
    }
    dirDisplay.innerHTML = `<a href="file://${esc(value)}">${esc(value)}</a>`;
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
    cfg.statusOrder.forEach((status) => {
      (payload.grouped[status] || []).forEach((ticket) => allIncoming.set(String(ticket.num), { status, ticket }));
    });

    document.querySelectorAll(".ticket-link[data-ticket-num]").forEach((node) => {
      if (allIncoming.has(node.dataset.ticketNum)) return;
      node.classList.add("is-leaving");
      setTimeout(() => {
        node.remove();
        cfg.statusOrder.forEach(ensureEmptyState);
      }, 280);
    });

    cfg.statusOrder.forEach((status) => {
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

  document.querySelectorAll(".ticket-link[data-ticket-num]").forEach((link) => {
    attachTicketHandler(link);
  });

  closeBtn.addEventListener("click", closePanel);
  backdrop.addEventListener("click", closePanel);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && panel.classList.contains("is-open")) closePanel();
  });

  const chainStartBtn = document.getElementById("chain-start-btn");
  const chainStopBtn = document.getElementById("chain-stop-btn");
  const chainStatusDot = document.getElementById("chain-status-dot");
  const chainStatusText = document.getElementById("chain-status-text");
  const dirDisplay = document.getElementById("project-dir-display");
  const dirEditBtn = document.getElementById("project-dir-edit-btn");
  const dirInput = document.getElementById("project-dir-input");
  const dirSaveBtn = document.getElementById("project-dir-save-btn");
  const dirCancelBtn = document.getElementById("project-dir-cancel-btn");
  const dirWarning = document.getElementById("project-dir-warning");
  const generateContextBtn = document.getElementById("generate-context-btn");
  let contextPollingTimer = null;

  panelContent.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-review-action][data-ticket-num]");
    if (!button) return;
    button.disabled = true;
    try {
      await callTicketReviewAction(button.dataset.ticketNum, button.dataset.reviewAction);
    } catch (_error) {
      button.disabled = false;
    }
  });

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
    chain_status: cfg.chainStatus,
    chain_current_ticket_num: cfg.chainCurrentTicketNum,
    chain_pause_reason: cfg.chainPauseReason,
  });

  if (dirEditBtn) dirEditBtn.addEventListener("click", enterEditMode);

  if (dirCancelBtn) {
    dirCancelBtn.addEventListener("click", () => {
      dirInput.value = cfg.projectDir || "";
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
        if (!response.ok) throw new Error((payload && payload.error) || `HTTP ${response.status}`);
        renderDirectoryDisplay(payload ? payload.directory : directory);
        const missing = Boolean(payload && payload.directory && payload.exists_on_disk === false);
        if (dirWarning) dirWarning.hidden = !missing;
        exitEditMode();
      } catch (error) {
        showToast(error.message || "Failed to update project directory.");
      }
    });
  }

  function setContextButtonState(isLoading) {
    if (!generateContextBtn) return;
    const label = generateContextBtn.querySelector(".btn-label");
    generateContextBtn.disabled = Boolean(isLoading);
    generateContextBtn.classList.toggle("is-loading", Boolean(isLoading));
    if (label) label.textContent = isLoading ? "Generating..." : "Generate Context";
  }

  function stopContextPolling() {
    if (contextPollingTimer) {
      clearInterval(contextPollingTimer);
      contextPollingTimer = null;
    }
  }

  async function pollContextStatus() {
    try {
      const response = await fetch(`/api/project/${encodeURIComponent(projectSlug)}/context-status`);
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error((payload && payload.error) || `HTTP ${response.status}`);
      if (payload && payload.running) return;
      stopContextPolling();
      setContextButtonState(false);
      window.location.reload();
    } catch (error) {
      stopContextPolling();
      setContextButtonState(false);
      showToast(error.message || "Failed to check context generation status.");
    }
  }

  async function generateContext() {
    setContextButtonState(true);
    try {
      const response = await fetch(`/api/project/${encodeURIComponent(projectSlug)}/generate-context`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error((payload && payload.error) || `HTTP ${response.status}`);
      stopContextPolling();
      contextPollingTimer = setInterval(pollContextStatus, 3000);
      await pollContextStatus();
    } catch (error) {
      stopContextPolling();
      setContextButtonState(false);
      showToast(error.message || "Failed to start context generation.");
    }
  }

  if (generateContextBtn) {
    generateContextBtn.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      generateContext();
    });
  }

  const params = new URLSearchParams({ project: projectSlug });
  if (cfg.filters && cfg.filters.status) params.set("status", cfg.filters.status);
  if (cfg.filters && cfg.filters.priority) params.set("priority", cfg.filters.priority);
  if (cfg.filters && cfg.filters.tag) params.set("tag", cfg.filters.tag);

  subscribeSSE(`/events?${params.toString()}`, {
    onUnsupported: () => setConnection("project-sse-dot", "project-sse-label", false, "SSE unsupported"),
    onOpen: () => setConnection("project-sse-dot", "project-sse-label", true, "connected"),
    onError: () => setConnection("project-sse-dot", "project-sse-label", false, "reconnecting…"),
    events: {
      project_board: (event) => {
        try {
          const payload = JSON.parse(event.data);
          applyBoardUpdate(payload);
          applyChainState(payload);
          setConnection("project-sse-dot", "project-sse-label", true, "connected");
        } catch (_err) {
          setConnection("project-sse-dot", "project-sse-label", false, "parse error");
        }
      },
    },
  });

  // ── Add Ticket Dialog ──
  const addBtn = document.getElementById("add-ticket-btn");
  const dialog = document.getElementById("add-ticket-dialog");
  const addForm = document.getElementById("add-ticket-form");
  const cancelBtn = document.getElementById("add-ticket-cancel");

  if (addBtn && dialog) {
    addBtn.addEventListener("click", () => dialog.showModal());
    cancelBtn.addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (e) => {
      if (e.target === dialog) dialog.close();
    });

    addForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const formData = new FormData(addForm);
      const body = {
        title: formData.get("title"),
        description: formData.get("description"),
        priority: formData.get("priority"),
      };
      try {
        const resp = await fetch(`/api/ticket/${encodeURIComponent(projectSlug)}/add`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const data = await resp.json();
        if (data.ok) {
          dialog.close();
          addForm.reset();
          showToast(`Ticket #${data.num} created`);
          window.location.reload();
        } else {
          showToast(data.error || "Failed to create ticket", "error");
        }
      } catch (err) {
        showToast("Network error", "error");
      }
    });
  }

  // ── Edit Ticket (in panel) ──
  window.editTicketField = async function(ticketNum, field, currentValue) {
    const newValue = prompt(`Edit ${field}:`, currentValue || "");
    if (newValue === null || newValue === currentValue) return;
    try {
      const resp = await fetch(`/api/ticket/${encodeURIComponent(projectSlug)}/${ticketNum}/edit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [field]: newValue }),
      });
      const data = await resp.json();
      if (data.ok) {
        showToast(`Ticket #${ticketNum} updated`);
        openPanel(ticketNum);
      } else {
        showToast(data.error || "Failed to update", "error");
      }
    } catch (err) {
      showToast("Network error", "error");
    }
  };
})();
