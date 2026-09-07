import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from src.facts import create_fact
from src.pubsub_client import get_subscriber_client, subscription_path

SUBSCRIPTION_ID = "fact-events-sub"


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass  # Cloud Run's own request logging covers this; stay quiet.


def _serve_health_check() -> None:
    # Cloud Run expects every service to listen on $PORT and answer health
    # checks, but this process is otherwise a pure Pub/Sub pull loop with
    # no HTTP surface — this thread exists only to satisfy that.
    port = int(os.environ.get("PORT", 8080))
    try:
        server = HTTPServer(("0.0.0.0", port), _HealthHandler)
        print(f"Health check server listening on 0.0.0.0:{port}", flush=True)
        server.serve_forever()
    except Exception:
        # A daemon thread's exception doesn't reliably surface in Cloud
        # Run's log parser otherwise — print it explicitly so a silent
        # bind/listen failure is diagnosable instead of just timing out
        # the startup probe with no explanation.
        import traceback

        traceback.print_exc()


def _handle_message(message) -> None:
    payload = json.loads(message.data.decode("utf-8"))
    create_fact(
        tenant_id=payload["tenant_id"],
        content=payload["content"],
        category=payload["category"],
    )
    # Tell Pub/Sub the message was processed; an unacked message is
    # redelivered after the ack deadline elapses.
    message.ack()
    print(f"Wrote fact for tenant '{payload['tenant_id']}'")


def run():
    threading.Thread(target=_serve_health_check, daemon=True).start()

    subscriber = get_subscriber_client()
    subscription = subscription_path(SUBSCRIPTION_ID)

    streaming_pull_future = subscriber.subscribe(subscription, callback=_handle_message)
    print(f"Listening on {subscription}... (Ctrl+C to stop)")

    with subscriber:
        try:
            streaming_pull_future.result()
        except KeyboardInterrupt:
            streaming_pull_future.cancel()
            streaming_pull_future.result()


if __name__ == "__main__":
    run()
