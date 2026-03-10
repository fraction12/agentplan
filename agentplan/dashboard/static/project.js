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
  const panelTitleEditBtn = document.getElementById("panel-title-edit-btn");
  const panelMenuButton = document.getElementById("ticket-panel-menu-button");
  const panelMenu = document.getElementById("ticket-panel-menu");
  const projectSlug = cfg.projectSlug;
  let dependencyOptionsCache = null;
  let activeDependencyPicker = null;
  const FIELD_EDITOR_CONFIG = {
    title: {
      type: "input",
      title: "Edit title",
      label: "Title",
      help: "Update the ticket title.",
      emptyMessage: "Title cannot be empty.",
      normalize: (value) => String(value || "").trim(),
    },
    description: {
      type: "textarea",
      title: "Edit description",
      label: "Description",
      help: "Update the ticket description.",
      normalize: (value) => String(value || "").trim(),
    },
    priority: {
      type: "select",
      title: "Edit priority",
      label: "Priority",
      help: "Choose one of the supported priority levels.",
      normalize: (value) => String(value || "none").trim().toLowerCase(),
      isValid: (value) => ["high", "medium", "low", "none"].includes(value),
      emptyMessage: "Choose a valid priority.",
    },
    model_tier: {
      type: "select",
      title: "Edit model tier",
      label: "Model Tier",
      help: "Choose the capability level needed for this task.",
      normalize: (value) => String(value || "auto").trim().toLowerCase(),
      isValid: (value) => ["auto", "light", "standard", "reasoning"].includes(value),
      emptyMessage: "Choose a valid model tier.",
    },
  };
  let activeFieldEdit = null;

  function renderSubtasks(ticketNum, subtasks) {
    const listMarkup = (!subtasks || subtasks.length === 0)
      ? '<p class="panel-muted">No subtasks.</p>'
      : `<ul class="subtask-list">${subtasks.map((subtask) => `<li class="subtask-item"><label><input type="checkbox" data-subtask-done="${esc(subtask.num)}" data-ticket-num="${esc(ticketNum)}" ${subtask.status === "done" ? "checked disabled" : ""}><span>#${esc(subtask.num)} ${esc(subtask.title)}</span></label></li>`).join("")}</ul>`;
    return `${listMarkup}<form class="subtask-add-row" data-subtask-add-form data-ticket-num="${esc(ticketNum)}"><input type="text" name="title" placeholder="Add subtask" maxlength="160" autocomplete="off"><button class="btn btn-sm btn-primary" type="submit">Add</button></form>`;
  }

  function renderDependencyChips(items, ticketNum, direction) {
    if (!items || items.length === 0) return '<p class="panel-muted">None.</p>';
    return `<div class="dep-chip-list">${items.map((item) => `<span class="dep-chip">#${esc(item.num)} ${esc(item.title)}<button class="dep-chip-remove" type="button" data-dependency-remove="${esc(item.num)}" data-ticket-num="${esc(ticketNum)}" data-dependency-direction="${esc(direction)}" aria-label="Remove dependency link for ticket ${esc(item.num)}">×</button></span>`).join("")}</div>`;
  }

  function renderDependencyPicker(data, direction) {
    const isOpen = activeDependencyPicker
      && String(activeDependencyPicker.ticketNum) === String(data.num)
      && activeDependencyPicker.direction === direction;
    return `
      <div class="dep-inline-picker" data-dependency-picker="${esc(direction)}" data-ticket-num="${esc(data.num)}" ${isOpen ? "" : "hidden"}>
        <input class="dep-search-input" type="text" value="${esc(isOpen ? activeDependencyPicker.query || "" : "")}" placeholder="Search tickets" autocomplete="off" data-dependency-search="${esc(direction)}" data-ticket-num="${esc(data.num)}">
        <div class="dep-search-results" data-dependency-results="${esc(direction)}" data-ticket-num="${esc(data.num)}"></div>
      </div>
    `;
  }

  function renderDependencyRow(data, direction, label, items) {
    const isOpen = activeDependencyPicker
      && String(activeDependencyPicker.ticketNum) === String(data.num)
      && activeDependencyPicker.direction === direction;
    return `
      <div class="dep-section-row" data-dependency-row="${esc(direction)}" data-ticket-num="${esc(data.num)}">
        <div class="dep-row-header">
          <div class="dep-row-label">${esc(label)}</div>
          <button class="dep-add-trigger" type="button" data-dependency-picker-open="${esc(direction)}" data-ticket-num="${esc(data.num)}" aria-expanded="${isOpen ? "true" : "false"}">+</button>
        </div>
        ${renderDependencyChips(items, data.num, direction)}
        ${renderDependencyPicker(data, direction)}
      </div>
    `;
  }

  function renderDependencySection(data) {
    return `
      <section class="panel-block">
        <h3>Dependencies</h3>
        <div class="dep-section">
          ${renderDependencyRow(data, "blocked_by", "Blocked by", data.blocked_by || [])}
          ${renderDependencyRow(data, "blocking", "Blocking", data.blocks || [])}
        </div>
      </section>
    `;
  }

  function renderPanel(data) {
    panelId.textContent = `#${data.num}`;
    panelTitle.textContent = data.title || "Ticket details";
    if (panelTitleEditBtn) {
      panelTitleEditBtn.dataset.editNum = String(data.num || "");
      panelTitleEditBtn.hidden = false;
    }
    if (panelMenuButton) {
      panelMenuButton.dataset.ticketNum = String(data.num || "");
      panelMenuButton.hidden = false;
    }
    panelContent.innerHTML = `
      <section class="panel-block">
        <h3>Description <button class="ticket-panel-edit-btn" data-edit-field="description" data-edit-num="${esc(data.num)}">✎</button></h3>
        <p class="panel-description">${esc(data.description || "No description.")}</p>
      </section>
      <section class="panel-block">
        <h3>Priority <button class="ticket-panel-edit-btn" data-edit-field="priority" data-edit-num="${esc(data.num)}">✎</button></h3>
        <p class="panel-description">${esc((data.priority || 'none'))}</p>
      </section>
      <section class="panel-block">
        <h3>Model Tier <button class="ticket-panel-edit-btn" data-edit-field="model_tier" data-edit-num="${esc(data.num)}">✎</button></h3>
        <p class="panel-description">${esc((data.model_tier || 'auto'))}</p>
      </section>
      <section class="panel-block">
        <h3>Subtasks</h3>
        ${renderSubtasks(data.num, data.subtasks)}
      </section>
      ${renderDependencySection(data)}
    `;
  }

  function closePanelMenu({ restoreFocus = false } = {}) {
    if (panelMenuButton) panelMenuButton.setAttribute("aria-expanded", "false");
    if (panelMenu) panelMenu.hidden = true;
    if (restoreFocus) panelMenuButton?.focus();
  }

  function resetPanelHeaderActions() {
    closePanelMenu();
    activeDependencyPicker = null;
    if (panelTitleEditBtn) {
      panelTitleEditBtn.hidden = true;
      delete panelTitleEditBtn.dataset.editNum;
    }
    if (panelMenuButton) {
      panelMenuButton.hidden = true;
      delete panelMenuButton.dataset.ticketNum;
    }
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
    closePanelMenu();
    closeDependencyPicker();
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
    resetPanelHeaderActions();
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

  const fieldDialog = document.getElementById("ticket-field-dialog");
  const fieldForm = document.getElementById("ticket-field-form");
  const fieldDialogTitle = document.getElementById("ticket-field-dialog-title");
  const fieldDialogHelp = document.getElementById("ticket-field-dialog-help");
  const fieldInputRow = document.getElementById("ticket-field-input-row");
  const fieldInputLabel = document.getElementById("ticket-field-input-label");
  const fieldInput = document.getElementById("ticket-field-input");
  const fieldTextareaRow = document.getElementById("ticket-field-textarea-row");
  const fieldTextareaLabel = document.getElementById("ticket-field-textarea-label");
  const fieldTextarea = document.getElementById("ticket-field-textarea");
  const fieldSelectRow = document.getElementById("ticket-field-select-row");
  const fieldSelectLabel = document.getElementById("ticket-field-select-label");
  const fieldSelect = document.getElementById("ticket-field-select");
  const fieldError = document.getElementById("ticket-field-error");
  const fieldCancelBtn = document.getElementById("ticket-field-cancel");
  const fieldSaveBtn = document.getElementById("ticket-field-save");

  function clearFieldEditorError() {
    if (!fieldError) return;
    fieldError.hidden = true;
    fieldError.textContent = "";
  }

  function setFieldEditorError(message) {
    if (!fieldError) return;
    fieldError.textContent = message;
    fieldError.hidden = false;
  }

  function activeFieldControl() {
    if (!activeFieldEdit) return null;
    const editor = FIELD_EDITOR_CONFIG[activeFieldEdit.field];
    if (!editor) return null;
    if (editor.type === "textarea") return fieldTextarea;
    if (editor.type === "select") return fieldSelect;
    return fieldInput;
  }

  function setActiveFieldValue(value) {
    const control = activeFieldControl();
    if (!control) return;
    control.value = String(value ?? "");
  }

  function getActiveFieldValue() {
    const control = activeFieldControl();
    if (!control) return "";
    return control.value;
  }

  function closeFieldEditor() {
    activeFieldEdit = null;
    clearFieldEditorError();
    if (fieldForm) fieldForm.reset();
    if (fieldSaveBtn) fieldSaveBtn.disabled = false;
    if (fieldDialog?.open) fieldDialog.close();
  }

  function openFieldEditor(field, ticketNum, currentValue) {
    const editor = FIELD_EDITOR_CONFIG[field];
    if (!editor || !fieldDialog) return;
    activeFieldEdit = { field, ticketNum, originalValue: editor.normalize ? editor.normalize(currentValue) : String(currentValue ?? "") };
    clearFieldEditorError();
    if (fieldDialogTitle) fieldDialogTitle.textContent = editor.title;
    if (fieldDialogHelp) fieldDialogHelp.textContent = editor.help;
    if (fieldInputLabel) fieldInputLabel.textContent = editor.label;
    if (fieldTextareaLabel) fieldTextareaLabel.textContent = editor.label;
    if (fieldSelectLabel) fieldSelectLabel.textContent = editor.label;
    if (fieldInputRow) fieldInputRow.hidden = editor.type !== "input";
    if (fieldTextareaRow) fieldTextareaRow.hidden = editor.type !== "textarea";
    if (fieldSelectRow) fieldSelectRow.hidden = editor.type !== "select";
    if (editor.type === "select" && fieldSelect) {
      const optionSets = {
        priority: [["none","None"],["high","High"],["medium","Medium"],["low","Low"]],
        model_tier: [["auto","Auto"],["light","Light"],["standard","Standard"],["reasoning","Reasoning"]],
      };
      const opts = optionSets[field] || optionSets.priority;
      fieldSelect.innerHTML = opts.map(([v,l]) => `<option value="${v}">${l}</option>`).join("");
    }
    setActiveFieldValue(activeFieldEdit.originalValue);
    fieldDialog.showModal();
    const control = activeFieldControl();
    if (control) {
      control.focus();
      if (typeof control.select === "function" && editor.type !== "select") control.select();
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

  function dependencyCandidates(ticketNum, direction, query = "") {
    if (!dependencyOptionsCache || !_panelData) return [];
    const currentTicketNum = Number(ticketNum);
    const existing = new Set(
      (direction === "blocked_by" ? (_panelData.blocked_by || []) : (_panelData.blocks || []))
        .map((item) => Number(item.num)),
    );
    const normalizedQuery = String(query || "").trim().toLowerCase();
    return dependencyOptionsCache.filter((ticket) => {
      if (Number(ticket.num) === currentTicketNum) return false;
      if (existing.has(Number(ticket.num))) return false;
      const haystack = `#${ticket.num} ${ticket.title || ""}`.toLowerCase();
      return !normalizedQuery || haystack.includes(normalizedQuery);
    });
  }

  function renderDependencySearchResults(ticketNum, direction) {
    const results = panelContent.querySelector(`[data-dependency-results="${direction}"][data-ticket-num="${ticketNum}"]`);
    if (!results) return;
    const query = activeDependencyPicker?.query || "";
    const matches = dependencyCandidates(ticketNum, direction, query);
    if (matches.length === 0) {
      results.innerHTML = '<p class="panel-muted">No matching tickets.</p>';
      return;
    }
    results.innerHTML = matches.map((ticket) => `<button class="dep-search-result" type="button" data-dependency-pick="${esc(ticket.num)}" data-ticket-num="${esc(ticketNum)}" data-dependency-direction="${esc(direction)}">#${esc(ticket.num)} ${esc(ticket.title)}</button>`).join("");
  }

  async function openDependencyPicker(ticketNum, direction) {
    await fetchDependencyOptions();
    activeDependencyPicker = { ticketNum: String(ticketNum), direction, query: "" };
    if (_panelData) renderPanel(_panelData);
    requestAnimationFrame(() => {
      const input = panelContent.querySelector(`[data-dependency-search="${direction}"][data-ticket-num="${ticketNum}"]`);
      if (!input) return;
      input.focus();
      renderDependencySearchResults(ticketNum, direction);
    });
  }

  function closeDependencyPicker({ restoreFocus = false } = {}) {
    const ticketNum = activeDependencyPicker?.ticketNum;
    const direction = activeDependencyPicker?.direction;
    activeDependencyPicker = null;
    if (_panelData) {
      renderPanel(_panelData);
      if (restoreFocus && ticketNum && direction) {
        requestAnimationFrame(() => {
          panelContent.querySelector(`[data-dependency-picker-open="${direction}"][data-ticket-num="${ticketNum}"]`)?.focus();
        });
      }
    }
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
      <div class="pill-row"><span class="priority-pill p-${esc((ticket.priority || "none").toLowerCase())}">${esc((ticket.priority || "none").toLowerCase())}</span>${ticket.model_tier && ticket.model_tier !== "auto" ? `<span class="tag-pill tag-purple">${esc(ticket.model_tier)}</span>` : ""}${tags || ""}</div>
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
    if (fieldDialog?.open) return;
    if (event.key !== "Escape") return;
    if (panelMenu && !panelMenu.hidden) {
      closePanelMenu({ restoreFocus: true });
      return;
    }
    if (activeDependencyPicker) {
      closeDependencyPicker({ restoreFocus: true });
      return;
    }
    if (panel.classList.contains("is-open")) closePanel();
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
  const projectHeaderMenuButton = document.getElementById("project-header-menu-button");
  const projectHeaderMenu = document.getElementById("project-header-menu");

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

  async function deleteTicket(ticketNum) {
    const ticketTitle = panelTitle.textContent || `ticket #${ticketNum}`;
    const confirmed = await confirmAction("Delete ticket?", `Delete ${ticketTitle}? Dependencies pointing to this ticket will be removed.`, "Delete");
    if (!confirmed) return;
    try {
      const response = await fetch(`/api/ticket/${encodeURIComponent(projectSlug)}/${encodeURIComponent(ticketNum)}/delete`, {
        method: "POST",
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error((payload && payload.error) || `HTTP ${response.status}`);
      closePanel();
      window.location.reload();
    } catch (error) {
      showToast(error.message || "Failed to delete ticket.");
    }
  }

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
    const pickerTrigger = event.target.closest("[data-dependency-picker-open][data-ticket-num]");
    if (pickerTrigger) {
      const ticketNum = pickerTrigger.dataset.ticketNum;
      const direction = pickerTrigger.dataset.dependencyPickerOpen;
      const isSamePicker = activeDependencyPicker
        && String(activeDependencyPicker.ticketNum) === String(ticketNum)
        && activeDependencyPicker.direction === direction;
      if (isSamePicker) {
        closeDependencyPicker();
        return;
      }
      try {
        await openDependencyPicker(ticketNum, direction);
      } catch (error) {
        activeDependencyPicker = null;
        showToast(error.message || "Failed to load ticket list.");
      }
      return;
    }

    const pickButton = event.target.closest("[data-dependency-pick][data-ticket-num][data-dependency-direction]");
    if (pickButton) {
      const ticketNum = pickButton.dataset.ticketNum;
      const depNum = Number(pickButton.dataset.dependencyPick);
      const direction = pickButton.dataset.dependencyDirection;
      pickButton.disabled = true;
      try {
        if (direction === "blocking") {
          await updateDependency(depNum, "depend", { on: Number(ticketNum) });
        } else {
          await updateDependency(ticketNum, "depend", { on: depNum });
        }
        dependencyOptionsCache = null;
        activeDependencyPicker = null;
        await loadTicket(ticketNum);
      } catch (error) {
        showToast(error.message || "Failed to add dependency.");
      }
      return;
    }

    const removeButton = event.target.closest("[data-dependency-remove][data-ticket-num][data-dependency-direction]");
    if (removeButton) {
      removeButton.disabled = true;
      try {
        const currentTicketNum = Number(removeButton.dataset.ticketNum);
        const targetTicketNum = Number(removeButton.dataset.dependencyRemove);
        if (removeButton.dataset.dependencyDirection === "blocking") {
          await updateDependency(targetTicketNum, "undepend", { dep: currentTicketNum });
        } else {
          await updateDependency(currentTicketNum, "undepend", { dep: targetTicketNum });
        }
        dependencyOptionsCache = null;
        activeDependencyPicker = null;
        await loadTicket(currentTicketNum);
      } catch (error) {
        removeButton.disabled = false;
        showToast(error.message || "Failed to remove dependency.");
      }
    }
  });

  panelContent.addEventListener("input", (event) => {
    const input = event.target.closest("[data-dependency-search][data-ticket-num]");
    if (!input || !activeDependencyPicker) return;
    activeDependencyPicker.query = input.value || "";
    renderDependencySearchResults(input.dataset.ticketNum, input.dataset.dependencySearch);
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

  if (panelMenuButton && panelMenu) {
    panelMenuButton.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const willOpen = panelMenu.hidden !== false;
      closePanelMenu();
      if (willOpen) {
        panelMenu.hidden = false;
        panelMenuButton.setAttribute("aria-expanded", "true");
        panelMenu.querySelector(".kebab-menu-item")?.focus();
      }
    });

    panelMenu.addEventListener("click", async (event) => {
      const deleteButton = event.target.closest("[data-ticket-delete-overflow]");
      if (!deleteButton) return;
      event.preventDefault();
      event.stopPropagation();
      closePanelMenu();
      const ticketNum = panelMenuButton.dataset.ticketNum;
      if (!ticketNum) return;
      await deleteTicket(ticketNum);
    });

    document.addEventListener("click", (event) => {
      if (!event.target.closest(".ticket-panel-menu-wrap")) {
        closePanelMenu();
      }
    });
  }

  document.addEventListener("click", (event) => {
    if (!activeDependencyPicker) return;
    const currentRow = panelContent.querySelector(`[data-dependency-row="${activeDependencyPicker.direction}"][data-ticket-num="${activeDependencyPicker.ticketNum}"]`);
    if (currentRow && !currentRow.contains(event.target)) {
      closeDependencyPicker();
    }
  });

  const params = new URLSearchParams({ project: projectSlug });
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
        model_tier: formData.get("model_tier"),
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
    openFieldEditor(field, ticketNum, currentValue);
  });

  if (panelTitleEditBtn) {
    panelTitleEditBtn.addEventListener("click", () => {
      if (!_panelData) return;
      openFieldEditor("title", _panelData.num, _panelData.title || "");
    });
  }

  if (fieldCancelBtn) {
    fieldCancelBtn.addEventListener("click", closeFieldEditor);
  }

  if (fieldDialog) {
    fieldDialog.addEventListener("click", (event) => {
      if (event.target === fieldDialog) closeFieldEditor();
    });
    fieldDialog.addEventListener("close", () => {
      activeFieldEdit = null;
      clearFieldEditorError();
      if (fieldSaveBtn) fieldSaveBtn.disabled = false;
    });
  }

  if (fieldForm) {
    fieldForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!activeFieldEdit) return;
      const editor = FIELD_EDITOR_CONFIG[activeFieldEdit.field];
      if (!editor) return;
      const normalized = editor.normalize ? editor.normalize(getActiveFieldValue()) : getActiveFieldValue();
      if (editor.emptyMessage && !normalized) {
        setFieldEditorError(editor.emptyMessage);
        activeFieldControl()?.focus();
        return;
      }
      if (editor.isValid && !editor.isValid(normalized)) {
        setFieldEditorError(editor.emptyMessage || "Enter a valid value.");
        activeFieldControl()?.focus();
        return;
      }
      if (normalized === activeFieldEdit.originalValue) {
        closeFieldEditor();
        return;
      }
      if (fieldSaveBtn) fieldSaveBtn.disabled = true;
      clearFieldEditorError();
      try {
        const ticketNum = activeFieldEdit.ticketNum;
        const field = activeFieldEdit.field;
        const resp = await fetch(`/api/ticket/${encodeURIComponent(projectSlug)}/${ticketNum}/edit`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ [field]: normalized }),
        });
        const data = await resp.json().catch(() => null);
        if (!resp.ok) throw new Error((data && data.error) || `HTTP ${resp.status}`);
        closeFieldEditor();
        showToast(`Ticket #${ticketNum} updated`);
        loadTicket(ticketNum);
      } catch (err) {
        if (fieldSaveBtn) fieldSaveBtn.disabled = false;
        setFieldEditorError(err.message || "Failed to update ticket.");
      }
    });
  }

})();
