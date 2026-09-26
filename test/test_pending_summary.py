import src.facts.pending_facts as pending_facts


def _pending(content, category="architecture"):
    return {"pending_fact_id": "p", "content": content, "category": category, "source": "github", "source_url": "u"}


def _serve(monkeypatch, pending, saved=()):
    monkeypatch.setattr(pending_facts, "list_pending_facts", lambda tenant_id, owner_uid: list(pending))
    monkeypatch.setattr(pending_facts, "get_tenant_facts", lambda tenant_id, owner_uid: list(saved))


def test_each_pending_fact_is_listed_with_its_category_and_no_ids_or_urls(monkeypatch):
    _serve(monkeypatch, [_pending("Adds a cache layer", "decision")])

    assert pending_facts.get_pending_facts_summary("t", "o") == {
        "pending": [{"content": "Adds a cache layer", "category": "decision", "similar_to_saved": None}],
        "truncated": False,
    }


def test_a_pending_fact_that_repeats_a_saved_one_is_marked_by_code(monkeypatch):
    saved = [{"fact_id": "f1", "content": "Uses PostgreSQL", "category": "architecture"}]
    _serve(monkeypatch, [_pending("uses postgresql."), _pending("Deploys on Cloud Run")], saved)

    first, second = pending_facts.get_pending_facts_summary("t", "o")["pending"]

    assert first["similar_to_saved"] == "Uses PostgreSQL"
    assert second["similar_to_saved"] is None


def test_the_list_is_capped_and_says_when_there_are_more(monkeypatch):
    _serve(monkeypatch, [_pending(f"Fact number {n}") for n in range(pending_facts.MAX_PENDING_FOR_REVIEW + 5)])

    result = pending_facts.get_pending_facts_summary("t", "o")

    assert len(result["pending"]) == pending_facts.MAX_PENDING_FOR_REVIEW
    assert result["truncated"] is True


def test_a_long_pending_text_is_cut_off(monkeypatch):
    _serve(monkeypatch, [_pending("x" * 500)])

    (item,) = pending_facts.get_pending_facts_summary("t", "o")["pending"]

    assert len(item["content"]) == pending_facts.MAX_PENDING_CONTENT_CHARS and item["content"].endswith("…")


def test_nothing_pending_is_an_empty_list(monkeypatch):
    _serve(monkeypatch, [])

    assert pending_facts.get_pending_facts_summary("t", "o") == {"pending": [], "truncated": False}
