import base64
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

from src.facts import create_fact


def _process_push_message(body: bytes) -> int:
    """Handle one Pub/Sub push request body.

    Returns the HTTP status code to respond with — 200 acks the
    message, anything else lets Pub/Sub's retry/DLQ policy (see
    pubsub.tf) take over.
    """
    try:
        envelope = json.loads(body)
        data = base64.b64decode(envelope["message"]["data"])
        payload = json.loads(data.decode("utf-8"))
        create_fact(
            tenant_id=payload["tenant_id"],
            content=payload["content"],
            category=payload["category"],
            # .get, not [] — messages published before APPCE-81 added this
            # field have none, and should still default to "chat".
            source=payload.get("source", "chat"),
        )
    except (KeyError, ValueError, json.JSONDecodeError):
        # A malformed payload will never succeed on retry, but we
        # still return a non-2xx (rather than silently ack-ing) so
        # Pub/Sub's existing retry/DLQ policy eventually routes it to
        # the dead-letter topic instead of just dropping it — same
        # intent as the old pull-based nack() path (APPCE-30).
        print(f"Malformed push message, returning 400: {body!r}")
        return 400

    print(f"Wrote fact for tenant '{payload['tenant_id']}'")
    return 200


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Cloud Run's own health/startup probes.
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        status = _process_push_message(body)
        self.send_response(status)
        self.end_headers()

    def log_message(self, *args):
        pass  # Cloud Run's own request logging covers this; stay quiet.


def run():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), _Handler)
    print(f"Listening on 0.0.0.0:{port} for Pub/Sub push messages...", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    run()
