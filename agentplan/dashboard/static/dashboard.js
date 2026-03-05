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
