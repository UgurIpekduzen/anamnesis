"""Back up, restore and wipe the whole Firestore database (APPCE-120).

    python -m src.db_backup dump FILE      read the database into a JSON file
    python -m src.db_backup load FILE      write a dump into the EMULATOR
    python -m src.db_backup verify FILE    compare the database with a dump (read-only)
    python -m src.db_backup restore FILE   show what writing a dump here would change
    python -m src.db_backup restore FILE --confirm-project PROJECT_ID   ...and write it
    python -m src.db_backup wipe           count what a wipe would delete
    python -m src.db_backup wipe --confirm-project PROJECT_ID   ...and delete it

The database is whatever get_client() points at: the emulator when
FIRESTORE_EMULATOR_HOST is set, the real project otherwise. A dump holds the
user's real data (project names, facts, encrypted tokens), so it belongs under
backups/, which is git-ignored, and nowhere else.
"""

import argparse
import base64
import json
import os
import sys
from datetime import datetime, timezone

from src.firestore_client import get_client

FORMAT_VERSION = 1


def _encode(value):
    # Only the types this app stores. An unknown one stops the dump instead of
    # being written as something that would load back as different data.
    if isinstance(value, datetime):
        return {"__type": "datetime", "value": value.astimezone(timezone.utc).isoformat()}
    if isinstance(value, bytes):
        return {"__type": "bytes", "value": base64.b64encode(value).decode("ascii")}
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Can't back up a value of type {type(value).__name__}: {value!r}")


def _decode(value):
    if isinstance(value, dict):
        if value.get("__type") == "datetime":
            return datetime.fromisoformat(value["value"])
        if value.get("__type") == "bytes":
            return base64.b64decode(value["value"])
        return {key: _decode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode(item) for item in value]
    return value


def _document_refs(parent):
    """Every document under `parent` (the client or a document), children after
    their parent. list_documents also returns a document that has no fields of
    its own but has subcollections, which a plain stream() would skip."""
    for collection in parent.collections():
        for ref in collection.list_documents():
            yield ref
            yield from _document_refs(ref)


def dump(path: str) -> int:
    client = get_client()
    documents = []
    for ref in _document_refs(client):
        snapshot = ref.get()
        if snapshot.exists:
            documents.append({"path": ref.path, "data": _encode(snapshot.to_dict())})
    payload = {
        "format": FORMAT_VERSION,
        "project": client.project,
        "taken_at": datetime.now(timezone.utc).isoformat(),
        "documents": documents,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    return len(documents)


def _read_dump(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    if payload.get("format") != FORMAT_VERSION:
        raise SystemExit(f"Unknown dump format: {payload.get('format')!r}")
    return payload


def load(path: str) -> int:
    # The quick way into the emulator, with nothing to confirm. Against the
    # real database it refuses: that is restore()'s job, which shows what it
    # would change first.
    if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        raise SystemExit(
            "Refusing to load: FIRESTORE_EMULATOR_HOST is not set, so this would write to the real database. "
            "Use restore to write a dump there on purpose."
        )
    payload = _read_dump(path)
    client = get_client()
    for document in payload["documents"]:
        client.document(document["path"]).set(_decode(document["data"]))
    return len(payload["documents"])


def verify(path: str) -> dict:
    """Compare the database with a dump, document by document. Read-only, and
    unlike restore it doesn't care which project the dump came from, so it can
    check a dump that was loaded into the emulator.

    Returns:
        {"same": n, "different": n, "missing": n, "extra": n}: missing are in the
        dump but not in the database, extra the other way round.
    """
    payload = _read_dump(path)
    client = get_client()
    expected = {document["path"]: _decode(document["data"]) for document in payload["documents"]}

    result = {"same": 0, "different": 0, "missing": 0, "extra": 0}
    for doc_path, data in expected.items():
        current = client.document(doc_path).get()
        if not current.exists:
            result["missing"] += 1
        elif current.to_dict() != data:
            result["different"] += 1
        else:
            result["same"] += 1
    for ref in _document_refs(client):
        if ref.path not in expected and ref.get().exists:
            result["extra"] += 1
    return result


def restore(path: str, confirm_project: str | None) -> dict:
    """Write a dump into the database get_client() points at, real or emulator.

    Without confirm_project it only reports. It adds what is missing and writes
    over what differs; what the dump doesn't have is left alone, never deleted.
    The dump must have been taken from this same project, so another project's
    data can't be written here by mistake.

    Returns:
        {"new": n, "changed": n, "unchanged": n, "written": bool}
    """
    payload = _read_dump(path)
    client = get_client()
    if payload["project"] != client.project:
        raise SystemExit(
            f"This dump is from project '{payload['project']}', not '{client.project}'; nothing was written."
        )
    if confirm_project is not None and confirm_project != client.project:
        raise SystemExit(f"--confirm-project must be exactly '{client.project}'; nothing was written.")

    counts = {"new": 0, "changed": 0, "unchanged": 0}
    to_write = []
    for document in payload["documents"]:
        ref = client.document(document["path"])
        data = _decode(document["data"])
        current = ref.get()
        if not current.exists:
            counts["new"] += 1
            to_write.append((ref, data))
        elif current.to_dict() != data:
            counts["changed"] += 1
            to_write.append((ref, data))
        else:
            counts["unchanged"] += 1

    if confirm_project is None:
        return {**counts, "written": False}
    # Firestore allows 500 writes per batch.
    for start in range(0, len(to_write), 400):
        batch = client.batch()
        for ref, data in to_write[start : start + 400]:
            batch.set(ref, data)
        batch.commit()
    return {**counts, "written": True}


def wipe(confirm_project: str | None) -> tuple[int, bool]:
    """Count (and, when confirm_project is this database's project id, delete)
    every document. Returns (documents, deleted)."""
    client = get_client()
    refs = list(_document_refs(client))
    # The same number a dump reports: a parent with no fields of its own is only
    # a path to its subcollections, not a document.
    count = sum(1 for ref in refs if ref.get().exists)
    if confirm_project is None:
        return count, False
    if confirm_project != client.project:
        raise SystemExit(f"--confirm-project must be exactly '{client.project}'; nothing was deleted.")
    # Children come after their parent in `refs`, so delete in reverse.
    for ref in reversed(refs):
        ref.delete()
    return count, True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.db_backup")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("dump").add_argument("file")
    commands.add_parser("load").add_argument("file")
    commands.add_parser("verify").add_argument("file")
    restore_parser = commands.add_parser("restore")
    restore_parser.add_argument("file")
    restore_parser.add_argument("--confirm-project")
    commands.add_parser("wipe").add_argument("--confirm-project")
    args = parser.parse_args(argv)

    target = "emulator" if os.environ.get("FIRESTORE_EMULATOR_HOST") else "REAL database"
    project = get_client().project
    print(f"{args.command}: {target}, project {project}")

    if args.command == "dump":
        print(f"Wrote {dump(args.file)} documents to {args.file}")
    elif args.command == "load":
        print(f"Loaded {load(args.file)} documents")
    elif args.command == "verify":
        result = verify(args.file)
        print(f"{result['same']} same, {result['different']} different, {result['missing']} missing, {result['extra']} extra")
        if result["different"] or result["missing"] or result["extra"]:
            return 1
        print("OK: the database holds exactly what the dump holds.")
    elif args.command == "restore":
        result = restore(args.file, args.confirm_project)
        summary = f"{result['new']} new, {result['changed']} would be overwritten, {result['unchanged']} already the same"
        if result["written"]:
            print(f"Restored: {summary.replace('would be overwritten', 'overwritten')}")
        else:
            print(f"Would write: {summary}. Nothing was written; add --confirm-project {project} to write it.")
    else:
        count, deleted = wipe(args.confirm_project)
        if deleted:
            print(f"Deleted {count} documents")
        else:
            print(f"Would delete {count} documents. Nothing was deleted; add --confirm-project {project} to delete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
