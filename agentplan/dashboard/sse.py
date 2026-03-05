"""SSE helpers for dashboard."""

from flask import Response, stream_with_context


def sse_response(stream_factory):
    @stream_with_context
    def wrapped():
        yield from stream_factory()

    return Response(
        wrapped(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
