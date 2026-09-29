"""Steps of an encryption key rotation that touch stored data.

Run by hand through the `task secrets:github-key:*` tasks — never part of a
request. Both steps read the key list from GITHUB_TOKEN_ENCRYPTION_KEY, the
same variable the app uses (see src/core/token_encryption.py).
"""

import argparse
import sys

from src.core.firestore_client import get_client
from src.core.token_encryption import UnreadableToken, decrypt_token, rotate_token

# Every collection that stores a token encrypted with this key.
COLLECTIONS = ("github_connections", "jira_connections")


def reencrypt_all_tokens(dry_run: bool = False) -> dict:
    """Rewrite each stored token with the primary (first) key.

    With dry_run nothing is written: each token is only decrypted, which
    shows whether the keys currently configured can still read everything.
    Run it with just the newest key to learn whether the older ones can be
    retired.

    A token no key can read is counted and reported, not fatal, so one
    broken record doesn't stop the rest from being moved.

    Returns:
        {"processed": int, "unreadable": int}
    """
    client = get_client()
    processed = 0
    unreadable = 0
    for name in COLLECTIONS:
        for doc in client.collection(name).stream():
            encrypted = doc.to_dict()["encrypted_token"]
            try:
                if dry_run:
                    decrypt_token(encrypted)
                else:
                    doc.reference.update({"encrypted_token": rotate_token(encrypted)})
            except UnreadableToken:
                unreadable += 1
                # The document id (the owner) is printed so it's known who
                # has to reconnect; the token itself never is.
                print(f"Can't read {name}/{doc.id}: no configured key decrypts it")
                continue
            processed += 1
    return {"processed": processed, "unreadable": unreadable}


def main(argv: list[str] | None = None) -> int:
    """Run the reencrypt/check CLI: reencrypt rewrites every stored token
    with the configured primary key, check only verifies every token is
    still readable without writing anything. Exits non-zero if any token
    couldn't be read with the currently configured keys."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("reencrypt", "check"),
        help="reencrypt: rewrite every token with the first key; "
        "check: only verify that the configured keys can read every token",
    )
    args = parser.parse_args(argv)

    result = reencrypt_all_tokens(dry_run=args.action == "check")
    verb = "readable" if args.action == "check" else "re-encrypted"
    print(f"{result['processed']} token(s) {verb}, {result['unreadable']} unreadable")
    return 1 if result["unreadable"] else 0


if __name__ == "__main__":
    sys.exit(main())
