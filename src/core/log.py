"""Structured log lines.

Cloud Run turns a JSON line on stdout into a structured entry and reads its
"severity" field, so an error can be found with `severity>=ERROR` and alerted
on. A bare print() is always INFO there, whatever it says.
"""

import json


def log(severity: str, event: str, **fields) -> None:
    """Write one JSON log line.

    Args:
        severity: A Cloud Logging level: "INFO", "WARNING" or "ERROR".
        event: A short snake_case name for what happened.
        **fields: Details, written as given — never pass a secret or a token.
    """
    print(json.dumps({"severity": severity, "event": event, **fields}, ensure_ascii=False, default=str), flush=True)
