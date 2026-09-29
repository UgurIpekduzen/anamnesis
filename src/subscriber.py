import base64
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

from src.facts.facts import create_fact
from src.core.log import log

# A push carries one fact (at most 2000 characters, base64 in a JSON envelope),
# so a body this large is not a delivery. Read nothing past it.
MAX_BODY_BYTES = 64 * 1024


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
            # .get, not [] — messages published before this
            # field have none, and should still default to "chat".
            source=payload.get("source", "chat"),
        )
    except (KeyError, ValueError, json.JSONDecodeError):
        # A malformed payload will never succeed on retry, but we
        # still return a non-2xx (rather than silently ack-ing) so
        # Pub/Sub's existing retry/DLQ policy eventually routes it to
        # the dead-letter topic instead of just dropping it — same
        # intent as the old pull-based nack() path.
        # The size only, never the body: it holds a fact's text, and logs are
        # kept and read more widely than the facts themselves.
        log("WARNING", "malformed_push_message", size=len(body))
        return 400

    log("INFO", "fact_written", tenant_id=payload["tenant_id"])
    return 200


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Cloud Run's own health/startup probes.
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", ""))
            if length < 0:
                raise ValueError
        except ValueError:
            self._respond(400)
            return
        if length > MAX_BODY_BYTES:
            self._respond(413)
            return
        self._respond(_process_push_message(self.rfile.read(length)))

    def _respond(self, status):
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass  # Cloud Run's own request logging covers this; stay quiet.


def run():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), _Handler)
    log("INFO", "subscriber_listening", port=port)
    server.serve_forever()


if __name__ == "__main__":
    run()
