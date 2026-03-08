function showToast(message, tone = "error", stackId = "toast-stack") {
  const stack = document.getElementById(stackId);
  if (!stack) return;
  const toast = document.createElement("div");
  toast.className = `toast ${tone}`;
  toast.textContent = message || "Request failed.";
  stack.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 4500);
}

function setClock(elementId, ts) {
  const element = document.getElementById(elementId);
  if (!element) return;
  const date = ts ? new Date(ts) : new Date();
  element.textContent = date.toLocaleTimeString();
}

function setConnection(dotId, labelId, isConnected, label) {
  const dot = document.getElementById(dotId);
  const text = document.getElementById(labelId);
  if (!dot || !text) return;
  dot.classList.remove("connected", "disconnected");
  dot.classList.add(isConnected ? "connected" : "disconnected");
  text.textContent = label;
}

function subscribeSSE(url, handlers = {}) {
  if (!window.EventSource) {
    if (typeof handlers.onUnsupported === "function") {
      handlers.onUnsupported();
    }
    return null;
  }

  const source = new EventSource(url);

  if (typeof handlers.onOpen === "function") {
    source.addEventListener("open", handlers.onOpen);
  }

  if (handlers.events && typeof handlers.events === "object") {
    Object.entries(handlers.events).forEach(([eventName, handler]) => {
      if (typeof handler === "function") {
        source.addEventListener(eventName, handler);
      }
    });
  }

  if (typeof handlers.onError === "function") {
    source.onerror = handlers.onError;
  }

  return source;
}

function ensureConfirmDialog() {
  let dialog = document.getElementById("global-confirm-dialog");
  if (dialog) return dialog;

  dialog = document.createElement("dialog");
  dialog.id = "global-confirm-dialog";
  dialog.className = "confirm-dialog";
  dialog.innerHTML = `
    <form method="dialog" class="confirm-dialog-form">
      <div class="confirm-dialog-copy">
        <h3 class="confirm-dialog-title"></h3>
        <p class="confirm-dialog-message"></p>
      </div>
      <div class="confirm-dialog-actions">
        <button type="button" class="btn confirm-dialog-cancel">Cancel</button>
        <button type="submit" class="btn btn-danger confirm-dialog-confirm" value="confirm">Confirm</button>
      </div>
    </form>
  `;
  document.body.appendChild(dialog);
  return dialog;
}

function confirmAction(title, message, confirmLabel = "Confirm") {
  const dialog = ensureConfirmDialog();
  const titleNode = dialog.querySelector(".confirm-dialog-title");
  const messageNode = dialog.querySelector(".confirm-dialog-message");
  const confirmBtn = dialog.querySelector(".confirm-dialog-confirm");
  const cancelBtn = dialog.querySelector(".confirm-dialog-cancel");

  titleNode.textContent = title || "Confirm action";
  messageNode.textContent = message || "";
  confirmBtn.textContent = confirmLabel || "Confirm";

  return new Promise((resolve) => {
    let settled = false;

    function finish(result) {
      if (settled) return;
      settled = true;
      dialog.removeEventListener("close", onClose);
      dialog.removeEventListener("cancel", onCancel);
      cancelBtn.removeEventListener("click", onCancelClick);
      resolve(result);
    }

    function onClose() {
      finish(dialog.returnValue === "confirm");
      dialog.returnValue = "";
    }

    function onCancel(event) {
      event.preventDefault();
      dialog.close("cancel");
    }

    function onCancelClick() {
      dialog.close("cancel");
    }

    dialog.addEventListener("close", onClose);
    dialog.addEventListener("cancel", onCancel);
    cancelBtn.addEventListener("click", onCancelClick);

    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    } else {
      finish(window.confirm(message || title || "Confirm action"));
      return;
    }

    confirmBtn.focus();
  });
}

window.confirmAction = confirmAction;
