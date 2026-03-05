"""agentplan dashboard package."""

import threading
import webbrowser

from .routes import create_app, _fetch_projects_with_stats, _ticket_matches


app = create_app()


def run_dashboard(host="127.0.0.1", port=5001, open_browser=False):
    if open_browser:
        def _open():
            webbrowser.open(f"http://localhost:{port}")

        threading.Timer(0.6, _open).start()
    app.run(host=host, port=port, threaded=True)


__all__ = [
    "app",
    "create_app",
    "run_dashboard",
    "_fetch_projects_with_stats",
    "_ticket_matches",
]
