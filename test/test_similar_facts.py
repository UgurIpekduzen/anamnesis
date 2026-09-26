import pytest

from src.facts.similar_facts import MAX_SIMILAR, find_similar_facts


def _fact(fact_id, content, category="architecture"):
    return {"fact_id": fact_id, "content": content, "category": category}


@pytest.mark.parametrize(
    "new",
    [
        "Uses PostgreSQL",
        "uses postgresql.",
        "  Uses   PostgreSQL  ",
        "Uses PostgreSQL 15",  # a small edit
        "The backend uses PostgreSQL",  # contains the saved text
    ],
)
def test_the_same_fact_worded_slightly_differently_is_found(new):
    facts = [_fact("f1", "Uses PostgreSQL")]

    assert [f["fact_id"] for f in find_similar_facts(new, facts)] == ["f1"]


@pytest.mark.parametrize("new", ["Deploys on Cloud Run", "Uses MongoDB for events", "todo"])
def test_a_different_fact_is_not_flagged(new):
    assert find_similar_facts(new, [_fact("f1", "Uses PostgreSQL")]) == []


def test_a_short_text_inside_a_longer_one_is_not_a_match_by_itself():
    assert find_similar_facts("todo", [_fact("f1", "Write the todo list for the migration next week")]) == []


def test_a_duplicate_in_another_category_is_still_found():
    (found,) = find_similar_facts("Uses PostgreSQL", [_fact("f1", "Uses PostgreSQL", category="decision")])

    assert found == {"fact_id": "f1", "content": "Uses PostgreSQL", "category": "decision"}


def test_the_list_is_capped():
    facts = [_fact(f"f{n}", f"Uses PostgreSQL {n}") for n in range(MAX_SIMILAR + 3)]

    assert len(find_similar_facts("Uses PostgreSQL", facts)) == MAX_SIMILAR


def test_the_most_alike_come_first():
    facts = [_fact("far", "Uses PostgreSQL for the events store"), _fact("near", "Uses PostgreSQL")]

    assert find_similar_facts("Uses PostgreSQL 15", facts)[0]["fact_id"] == "near"


def test_empty_text_and_missing_content_never_match():
    assert find_similar_facts("", [_fact("f1", "Uses PostgreSQL")]) == []
    assert find_similar_facts("Uses PostgreSQL", [{"fact_id": "f1", "content": None, "category": "bug"}]) == []
