(function bootAgentsPage() {
  const clockId = "agent-clock";
  const dotId = "agent-sse-dot";
  const labelId = "agent-sse-label";

  setClock(clockId);
  setInterval(() => setClock(clockId), 1000);

  subscribeSSE("/events", {
    onUnsupported: () => setConnection(dotId, labelId, false, "SSE unsupported"),
    onOpen: () => setConnection(dotId, labelId, true, "connected"),
    onError: () => setConnection(dotId, labelId, false, "reconnecting…"),
    events: {
      project_stats: (event) => {
        try {
          const payload = JSON.parse(event.data);
          setClock(clockId, payload.server_time || null);
          setConnection(dotId, labelId, true, "connected");
        } catch (_err) {
          setConnection(dotId, labelId, false, "parse error");
        }
      },
    },
  });

  function setEditRowOpen(rowKey, isOpen) {
    const row = document.querySelector(`[data-edit-row="${rowKey}"]`);
    const toggle = document.querySelector(`[data-edit-toggle="${rowKey}"]`);
    if (!row || !toggle) return;
    row.hidden = !isOpen;
    toggle.textContent = isOpen ? "Close" : "Edit";
    toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
  }

  document.querySelectorAll("[data-edit-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const rowKey = button.getAttribute("data-edit-toggle");
      const row = document.querySelector(`[data-edit-row="${rowKey}"]`);
      const opening = row ? row.hidden : false;
      document.querySelectorAll("[data-edit-row]").forEach((otherRow) => {
        const otherKey = otherRow.getAttribute("data-edit-row");
        setEditRowOpen(otherKey, false);
      });
      setEditRowOpen(rowKey, opening);
    });
  });

  document.querySelectorAll("[data-edit-cancel]").forEach((button) => {
    button.addEventListener("click", () => {
      const rowKey = button.getAttribute("data-edit-cancel");
      setEditRowOpen(rowKey, false);
    });
  });
})();
