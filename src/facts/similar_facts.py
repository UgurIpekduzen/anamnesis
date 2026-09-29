"""Detects near-duplicate facts by plain text comparison, so the UI can warn
before saving a fact that already exists in another wording — deliberately
not a model call, since it needs to give the same answer every time."""

import re
from difflib import SequenceMatcher

# Two facts this alike are almost certainly the same thing said twice. Tuned
# to catch rewordings and small edits ("Uses PostgreSQL" / "Uses PostgreSQL
# 15") without flagging every pair that merely shares a topic.
SIMILARITY_THRESHOLD = 0.75

# A short text contained in a longer one only counts as the same fact when
# it is long enough to be specific; "todo" inside anything is not a match.
MIN_CONTAINED_CHARS = 12

MAX_SIMILAR = 3


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.lower())).strip()


def _similarity(a: str, b: str) -> float:
    if len(a) >= MIN_CONTAINED_CHARS and len(b) >= MIN_CONTAINED_CHARS and (a in b or b in a):
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def find_similar_facts(content: str, facts: list[dict]) -> list[dict]:
    """The saved facts that say (nearly) the same thing as `content`.

    A plain text comparison, no model call: it has to give the same answer
    every time, and it runs on every confirmation to save a fact. Facts in
    any category count — a duplicate filed under another category is still
    a duplicate.

    Returns:
        Up to MAX_SIMILAR facts ({"fact_id", "content", "category"}), the
        most alike first; empty when nothing is close.
    """
    wanted = _normalize(content)
    if not wanted:
        return []
    scored = []
    for fact in facts:
        score = _similarity(wanted, _normalize(fact.get("content") or ""))
        if score >= SIMILARITY_THRESHOLD:
            scored.append((score, fact))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {"fact_id": fact["fact_id"], "content": fact["content"], "category": fact["category"]}
        for _, fact in scored[:MAX_SIMILAR]
    ]
