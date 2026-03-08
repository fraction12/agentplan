(function bootProjectPage() {
  const cfg = window.__projectPage;
  if (!cfg) return;
  const VALID_TRANSITIONS = {
    pending: new Set(["in-progress", "done", "skipped", "blocked"]),
    "in-progress": new Set(["done", "failed", "needs-review", "blocked", "pending"]),
    blocked: new Set(["pending", "in-progress"]),
    failed: new Set(["pending", "in-progress"]),
    "needs-review": new Set(["done", "in-progress", "failed"]),
    done: new Set(),
    skipped: new Set(),
  };
  let dragState = null;

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
  let dependencyOptionsCache = null;

  function renderList(items, emptyText, variant = "plain", ticketNum = "") {
    if (!items || items.length === 0) return `<p class="panel-muted">${esc(emptyText)}</p>`;
    return `<ul class="dep-list">${items.map((item) => {
      if (variant === "blocked-by") {
        return `<li class="dep-item">#${esc(item.num)} ${esc(item.title)} <button class="dep-remove-btn" type="button" data-dependency-remove="${esc(item.num)}" data-ticket-num="${esc(ticketNum)}" aria-label="Remove dependency on ticket ${esc(item.num)}">×</button></li>`;
      }
      return `<li class="dep-item">#${esc(item.num)} ${esc(item.title)}</li>`;
    }).join("")}</ul>`;
  }

  function renderSubtasks(ticketNum, subtasks) {
    const listMarkup = (!subtasks || subtasks.length === 0)
      ? '<p class="panel-muted">No subtasks.</p>'
      : `<ul class="subtask-list">${subtasks.map((subtask) => `<li class="subtask-item"><label><input type="checkbox" data-subtask-done="${esc(subtask.num)}" data-ticket-num="${esc(ticketNum)}" ${subtask.status === "done" ? "checked disabled" : ""}><span>#${esc(subtask.num)} ${esc(subtask.title)}</span></label></li>`).join("")}</ul>`;
    return `${listMarkup}<form class="subtask-add-row" data-subtask-add-form data-ticket-num="${esc(ticketNum)}"><input type="text" name="title" placeholder="Add subtask" maxlength="160" autocomplete="off"><button class="btn btn-sm btn-primary" type="submit">Add</button></form>`;
  }

  function renderHistory(history) {
    if (!history || history.length === 0) return '<p class="panel-muted">No audit entries.</p>';
    return `<ul class="audit-timeline">${history.map((item) => `<li class="audit-item"><div class="audit-meta">${esc(item.timestamp)} · ${esc(item.agent || "system")}${item.transition ? ` · ${esc(item.transition.old_state || "(none)")} → ${esc(item.transition.new_state || "")}` : ""}</div><p class="audit-message">${esc(item.message || "")}</p></li>`).join("")}</ul>`;
  }

  function transitionActionMarkup(data) {
    const actionDefs = {
      "in-progress": { label: "Start", className: "btn btn-chain-start", icon: "▶" },
      blocked: { label: "Block", className: "btn", icon: "⏸" },
      failed: { label: "Fail", className: "btn btn-chain-stop", icon: "✕" },
      "needs-review": { label: "Review", className: "btn btn-primary", icon: "↺" },
      done: { label: "Done", className: "btn btn-chain-start", icon: "✓" },
      pending: { label: "Retry", className: "btn btn-primary", icon: "↺" },
      skipped: { label: "Skip", className: "btn btn-chain-stop", icon: "⊘" },
    };
    const actions = Array.from(VALID_TRANSITIONS[data.status] || [])
      .map((status) => ({ status, ...actionDefs[status] }))
      .filter((item) => item.label);
    if (actions.length === 0) return "";
    return `<section class="panel-block review-actions"><h3>Actions</h3><div class="review-actions-row">${actions.map((action) => `<button class="${action.className}" type="button" data-transition-action="${esc(action.status)}" data-ticket-num="${esc(data.num)}">${action.icon} ${action.label}</button>`).join("")}</div></section>`;
  }

  function dependencyPickerMarkup(data) {
    return `<div class="dep-add-row"><button class="btn btn-sm" type="button" data-dependency-toggle="${esc(data.num)}">Add Dependency</button><div class="dep-picker" data-dependency-picker hidden><select data-dependency-select="${esc(data.num)}"><option value="">Select ticket…</option></select><button class="btn btn-sm btn-primary" type="button" data-dependency-add="${esc(data.num)}">Add</button></div></div>`;
  }

  function renderPanel(data) {
    panelId.textContent = `#${data.num}`;
    panelTitle.textContent = data.title || "Ticket details";
    panelContent.innerHTML = `
      <section class="panel-block">
        <h3>Title <button class="ticket-panel-edit-btn" data-edit-field="title" data-edit-num="${esc(data.num)}">✎</button></h3>
        <p class="panel-description">${esc(data.title || "")}</p>
      </section>
      <section class="panel-block">
        <h3>Description <button class="ticket-panel-edit-btn" data-edit-field="description" data-edit-num="${esc(data.num)}">✎</button></h3>
        <p class="panel-description">${esc(data.description || "No description.")}</p>
      </section>
      <section class="panel-block">
        <h3>Priority <button class="ticket-panel-edit-btn" data-edit-field="priority" data-edit-num="${esc(data.num)}">✎</button></h3>
        <p class="panel-description">${esc((data.priority || 'none'))}</p>
      </section>
      <section class="panel-block">
        <h3>Subtasks</h3>
        ${renderSubtasks(data.num, data.subtasks)}
      </section>
      <section class="panel-block">
        <h3>Dependency Graph</h3>
        <div class="dep-grid">
          <div><div class="panel-muted panel-subtitle">blocked by</div>${renderList(data.blocked_by, "No blockers.", "blocked-by", data.num)}${dependencyPickerMarkup(data)}</div>
          <div><div class="panel-muted panel-subtitle">blocks</div>${renderList(data.blocks, "No blocked tickets.")}</div>
        </div>
      </section>
      ${transitionActionMarkup(data)}
      <section class="panel-block">
        <h3>Audit Timeline</h3>
        ${renderHistory(data.audit_history)}
        <form class="dep-add-row" data-ticket-log-form data-ticket-num="${esc(data.num)}">
          <input type="text" name="entry" placeholder="Add log entry" maxlength="2000" autocomplete="off">
          <button class="btn btn-sm btn-primary" type="submit">Log</button>
        </form>
      </section>
      <section class="panel-block">
        <h3>Close Notes</h3>
        <p class="panel-description">${esc(data.close_note || "No close notes.")}</p>
      </section>
      <section class="panel-block">
        <button class="btn btn-danger panel-delete-btn" type="button" data-ticket-delete="${esc(data.num)}">Delete Ticket</button>
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

  async function transitionTicket(ticketNum, status) {
    const response = await fetch(`/api/ticket/${encodeURIComponent(projectSlug)}/${encodeURIComponent(ticketNum)}/transition`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error((payload && payload.error) || `HTTP ${response.status}`);
    return payload;
  }

  async function fetchDependencyOptions() {
    if (dependencyOptionsCache) return dependencyOptionsCache;
    const response = await fetch(`/api/project/${encodeURIComponent(projectSlug)}/tickets-list`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    dependencyOptionsCache = await response.json();
    return dependencyOptionsCache;
  }

  async function updateDependency(ticketNum, action, body) {
    const response = await fetch(`/api/ticket/${encodeURIComponent(projectSlug)}/${encodeURIComponent(ticketNum)}/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error((payload && payload.error) || `HTTP ${response.status}`);
    return payload;
  }

  function chainSummary(chainStatus, chainTicketNum, pauseReason) {
    const status = (chainStatus || "stopped").toLowerCase();
    if (status === "running") return `Automation: running — ticket #${chainTicketNum || "?"}`;
    if (status === "paused") return `Automation: paused — ${pauseReason || "waiting"}`;
    if (status === "done") return "Automation: idle";
    if (status === "stopped") return pauseReason ? `Automation: idle — ${pauseReason}` : "Automation: idle";
    return "Automation: idle";
  }

  function applyChainState(payload) {
    const chainStatus = (payload && payload.chain_status) || "stopped";
    const chainTicketNum = payload && payload.chain_current_ticket_num;
    const pauseReason = payload && payload.chain_pause_reason;
    const normalized = String(chainStatus).toLowerCase();
    if (chainStatusDot) chainStatusDot.className = `chain-dot ${esc(normalized)}`;
    if (chainStatusText) chainStatusText.textContent = chainSummary(normalized, chainTicketNum, pauseReason);
    if (chainStartBtn) chainStartBtn.disabled = normalized === "running";
    if (chainStopBtn) chainStopBtn.disabled = normalized !== "running";
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

  function isTerminalStatus(status) {
    return status === "done" || status === "skipped";
  }

  function canTransitionTo(fromStatus, toStatus) {
    if (!fromStatus || !toStatus || fromStatus === toStatus) return false;
    return VALID_TRANSITIONS[fromStatus]?.has(toStatus) || false;
  }

  function clearDragHighlights() {
    document.querySelectorAll(".kanban-column-body.drag-over").forEach((node) => node.classList.remove("drag-over"));
    document.querySelectorAll(".ticket-link.is-dragging").forEach((node) => node.classList.remove("is-dragging"));
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
      if (dragState && dragState.num === link.dataset.ticketNum) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      loadTicket(link.dataset.ticketNum);
    });
    link.addEventListener("dragstart", (event) => {
      const sourceStatus = link.dataset.ticketStatus || "";
      if (isTerminalStatus(sourceStatus)) {
        event.preventDefault();
        return;
      }
      dragState = { num: link.dataset.ticketNum, sourceStatus };
      link.classList.add("is-dragging");
      if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", link.dataset.ticketNum || "");
      }
    });
    link.addEventListener("dragend", () => {
      dragState = null;
      clearDragHighlights();
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
          link.draggable = !isTerminalStatus(ticket.status || status);
          link.setAttribute("role", "button");
          link.setAttribute("aria-label", `Open ticket #${num} details panel`);
          link.innerHTML = ticketCardMarkup(ticket);
          attachTicketHandler(link);
          body.appendChild(link);
          requestAnimationFrame(() => link.classList.remove("is-entering"));
        } else {
          const firstRect = link.getBoundingClientRect();
          link.dataset.ticketStatus = ticket.status || status;
          link.draggable = !isTerminalStatus(ticket.status || status);
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
    link.draggable = !isTerminalStatus(link.dataset.ticketStatus || "");
    attachTicketHandler(link);
  });

  document.querySelectorAll(".kanban-column-body[data-column-body]").forEach((body) => {
    body.addEventListener("dragenter", (event) => {
      if (!dragState) return;
      const targetStatus = body.dataset.columnBody || "";
      if (!canTransitionTo(dragState.sourceStatus, targetStatus)) return;
      event.preventDefault();
      body.classList.add("drag-over");
    });
    body.addEventListener("dragover", (event) => {
      if (!dragState) return;
      const targetStatus = body.dataset.columnBody || "";
      if (!canTransitionTo(dragState.sourceStatus, targetStatus)) return;
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
      body.classList.add("drag-over");
    });
    body.addEventListener("dragleave", (event) => {
      if (!body.contains(event.relatedTarget)) {
        body.classList.remove("drag-over");
      }
    });
    body.addEventListener("drop", async (event) => {
      if (!dragState) return;
      const targetStatus = body.dataset.columnBody || "";
      const { num, sourceStatus } = dragState;
      clearDragHighlights();
      if (!canTransitionTo(sourceStatus, targetStatus)) return;
      event.preventDefault();
      dragState = null;
      try {
        await transitionTicket(num, targetStatus);
      } catch (error) {
        showToast(error.message || "Failed to update ticket status.");
      }
    });
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
  const projectHeaderMenuButton = document.getElementById("project-header-menu-button");
  const projectHeaderMenu = document.getElementById("project-header-menu");
  let contextPollingTimer = null;

  function closeProjectMenu() {
    if (projectHeaderMenuButton) projectHeaderMenuButton.setAttribute("aria-expanded", "false");
    if (projectHeaderMenu) projectHeaderMenu.hidden = true;
  }

  async function postProjectAction(action, body) {
    const response = await fetch(`/api/project/${encodeURIComponent(projectSlug)}/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : null,
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error((payload && payload.error) || `HTTP ${response.status}`);
    return payload;
  }

  async function handleProjectAction(action) {
    const projectTitle = document.querySelector(".project-title")?.textContent?.trim() || "project";
    try {
      if (action === "delete") {
        const confirmed = await confirmAction("Delete project?", `Delete ${projectTitle}? This removes the project and all related tickets.`, "Delete");
        if (!confirmed) return;
      }

      await postProjectAction(action, action === "close" ? { abandon: false } : null);

      if (action === "delete") {
        window.location.href = "/";
        return;
      }

      showToast(`${action[0].toUpperCase()}${action.slice(1)}d ${projectTitle}.`, "success");
      window.location.reload();
    } catch (error) {
      showToast(error.message || `Failed to ${action} project.`);
    } finally {
      closeProjectMenu();
    }
  }

  panelContent.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-transition-action][data-ticket-num]");
    if (!button) return;
    button.disabled = true;
    try {
      await transitionTicket(button.dataset.ticketNum, button.dataset.transitionAction);
      await loadTicket(button.dataset.ticketNum);
    } catch (_error) {
      button.disabled = false;
    }
  });

  panelContent.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-ticket-delete]");
    if (!button) return;
    const ticketNum = button.dataset.ticketDelete;
    const ticketTitle = panelTitle.textContent || `ticket #${ticketNum}`;
    const confirmed = await confirmAction("Delete ticket?", `Delete ${ticketTitle}? Dependencies pointing to this ticket will be removed.`, "Delete");
    if (!confirmed) return;
    button.disabled = true;
    try {
      const response = await fetch(`/api/ticket/${encodeURIComponent(projectSlug)}/${encodeURIComponent(ticketNum)}/delete`, {
        method: "POST",
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error((payload && payload.error) || `HTTP ${response.status}`);
      closePanel();
      window.location.reload();
    } catch (error) {
      button.disabled = false;
      showToast(error.message || "Failed to delete ticket.");
    }
  });

  panelContent.addEventListener("change", async (event) => {
    const checkbox = event.target.closest("input[data-subtask-done][data-ticket-num]");
    if (!checkbox || !checkbox.checked) return;
    checkbox.disabled = true;
    try {
      const response = await fetch(`/api/ticket/${encodeURIComponent(projectSlug)}/${encodeURIComponent(checkbox.dataset.ticketNum)}/subtask/${encodeURIComponent(checkbox.dataset.subtaskDone)}/done`, {
        method: "POST",
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error((payload && payload.error) || `HTTP ${response.status}`);
      await loadTicket(checkbox.dataset.ticketNum);
    } catch (error) {
      checkbox.disabled = false;
      checkbox.checked = false;
      showToast(error.message || "Failed to complete subtask.");
    }
  });

  panelContent.addEventListener("submit", async (event) => {
    const form = event.target.closest("form[data-subtask-add-form][data-ticket-num]");
    if (!form) return;
    event.preventDefault();
    const input = form.querySelector('input[name="title"]');
    const submitter = form.querySelector('button[type="submit"]');
    const title = (input?.value || "").trim();
    if (!title) {
      input?.focus();
      return;
    }
    try {
      if (submitter) submitter.disabled = true;
      const response = await fetch(`/api/ticket/${encodeURIComponent(projectSlug)}/${encodeURIComponent(form.dataset.ticketNum)}/subtask/add`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error((payload && payload.error) || `HTTP ${response.status}`);
      await loadTicket(form.dataset.ticketNum);
    } catch (error) {
      showToast(error.message || "Failed to add subtask.");
    } finally {
      if (submitter) submitter.disabled = false;
    }
  });

  panelContent.addEventListener("click", async (event) => {
    const toggle = event.target.closest("[data-dependency-toggle]");
    if (toggle) {
      const picker = panelContent.querySelector("[data-dependency-picker]");
      const select = panelContent.querySelector("[data-dependency-select]");
      if (!picker || !select) return;
      const willOpen = picker.hidden;
      picker.hidden = !picker.hidden;
      if (!willOpen) return;
      try {
        const allTickets = await fetchDependencyOptions();
        const currentTicketNum = Number(toggle.dataset.dependencyToggle);
        const existing = new Set(Array.from(panelContent.querySelectorAll("[data-dependency-remove]")).map((node) => Number(node.dataset.dependencyRemove)));
        const options = allTickets.filter((ticket) => ticket.num !== currentTicketNum && !existing.has(ticket.num));
        select.innerHTML = '<option value="">Select ticket…</option>' + options.map((ticket) => `<option value="${ticket.num}">#${ticket.num} ${esc(ticket.title)}</option>`).join("");
        select.focus();
      } catch (error) {
        picker.hidden = true;
        showToast(error.message || "Failed to load ticket list.");
      }
      return;
    }

    const addButton = event.target.closest("[data-dependency-add]");
    if (addButton) {
      const ticketNum = addButton.dataset.dependencyAdd;
      const select = panelContent.querySelector(`[data-dependency-select="${ticketNum}"]`);
      const depNum = Number(select?.value || 0);
      if (!depNum) {
        select?.focus();
        return;
      }
      addButton.disabled = true;
      try {
        await updateDependency(ticketNum, "depend", { on: depNum });
        dependencyOptionsCache = null;
        await loadTicket(ticketNum);
      } catch (error) {
        showToast(error.message || "Failed to add dependency.");
      } finally {
        addButton.disabled = false;
      }
      return;
    }

    const removeButton = event.target.closest("[data-dependency-remove][data-ticket-num]");
    if (removeButton) {
      removeButton.disabled = true;
      try {
        await updateDependency(removeButton.dataset.ticketNum, "undepend", { dep: Number(removeButton.dataset.dependencyRemove) });
        dependencyOptionsCache = null;
        await loadTicket(removeButton.dataset.ticketNum);
      } catch (error) {
        removeButton.disabled = false;
        showToast(error.message || "Failed to remove dependency.");
      }
    }
  });

  panelContent.addEventListener("submit", async (event) => {
    const form = event.target.closest("form[data-ticket-log-form][data-ticket-num]");
    if (!form) return;
    event.preventDefault();
    const input = form.querySelector('input[name="entry"]');
    const submitter = form.querySelector('button[type="submit"]');
    const entry = (input?.value || "").trim();
    if (!entry) {
      input?.focus();
      return;
    }
    try {
      if (submitter) submitter.disabled = true;
      const response = await fetch(`/api/ticket/${encodeURIComponent(projectSlug)}/${encodeURIComponent(form.dataset.ticketNum)}/log`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entry }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error((payload && payload.error) || `HTTP ${response.status}`);
      await loadTicket(form.dataset.ticketNum);
    } catch (error) {
      showToast(error.message || "Failed to add log entry.");
    } finally {
      if (submitter) submitter.disabled = false;
    }
  });

  if (chainStartBtn) {
    chainStartBtn.addEventListener("click", async () => {
      chainStartBtn.disabled = true;
      try {
        await callChainAction("start");
      } catch (error) {
        showToast(error.message || "Failed to start automation.");
        chainStartBtn.disabled = false;
      }
    });
  }

  if (chainStopBtn) {
    chainStopBtn.addEventListener("click", async () => {
      chainStopBtn.disabled = true;
      try {
        await callChainAction("stop");
      } catch (error) {
        showToast(error.message || "Failed to stop automation.");
        chainStopBtn.disabled = false;
      }
    });
  }

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
        renderDirectoryDisplay(directory);
        if (dirWarning) dirWarning.hidden = true;
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
    if (label) label.textContent = isLoading ? "Generating..." : "Generate Repo Context";
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

  if (projectHeaderMenuButton && projectHeaderMenu) {
    projectHeaderMenuButton.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const willOpen = projectHeaderMenu.hidden !== false;
      closeProjectMenu();
      if (willOpen) {
        projectHeaderMenu.hidden = false;
        projectHeaderMenuButton.setAttribute("aria-expanded", "true");
      }
    });

    projectHeaderMenu.addEventListener("click", (event) => {
      const actionButton = event.target.closest("[data-project-action]");
      if (!actionButton) return;
      event.preventDefault();
      event.stopPropagation();
      handleProjectAction(actionButton.dataset.projectAction || "");
    });

    document.addEventListener("click", (event) => {
      if (!event.target.closest(".project-header-actions")) {
        closeProjectMenu();
      }
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeProjectMenu();
      }
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

  // ── Edit Ticket (in panel via data attributes) ──
  let _panelData = null;
  const _origRenderPanel = renderPanel;
  renderPanel = function(data) {
    _panelData = data;
    _origRenderPanel(data);
  };

  panelContent.addEventListener("click", async (evt) => {
    const btn = evt.target.closest("[data-edit-field]");
    if (!btn || !_panelData) return;
    const field = btn.dataset.editField;
    const ticketNum = btn.dataset.editNum;
    const currentValue = _panelData[field] || "";
    const newValue = prompt(`Edit ${field}:`, currentValue);
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
        loadTicket(ticketNum);
      } else {
        showToast(data.error || "Failed to update", "error");
      }
    } catch (err) {
      showToast("Network error", "error");
    }
  });
})();
