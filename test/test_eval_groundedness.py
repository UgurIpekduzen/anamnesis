"""The groundedness eval's own checks (eval/groundedness.py), on answers the
real model gave. The eval itself calls the model and isn't part of pytest;
what is worth pinning here is the grading: Turkish inflects, so a rule that is
too narrow marks a right answer wrong (it happened, four times, while the
eval was being written), and one that is too loose lets a made-up answer pass.
"""

import pytest

from eval import groundedness as g

FACT_ID = g.FACT_IDS[1]


@pytest.mark.parametrize(
    "check, answer",
    [
        (g.check_open_list, "Açık işler: DEMO-90, DEMO-141, DEMO-140, DEMO-139 ve DEMO-138."),
        (g.check_open_list_cut, "DEMO-90 DEMO-141 DEMO-140 DEMO-139 DEMO-138\n\nListede görünmeyen başka açık işler de var."),
        (g.check_not_linked, "Bu projenin bağlantılı bir Jira proje anahtarı bulunmamaktadır."),
        (g.check_recently_done, "DEMO-38 ve DEMO-36, 16 Ağustos 2026'da tamamlandı."),
        (g.check_unknown_topic, "Önbellekleme (caching) hakkında alınmış bir kararı bulamıyorum."),
        (g.check_unknown_topic, "Önbellekleme (caching) hakkında alınmış bir karara dair herhangi bir kayıt bulamadım."),
        (g.check_unknown_topic, "Önbellekleme (caching) ile ilgili bir karar kaydetmemişiz."),
        (g.check_conflict_is_cited, "Bu fact güncel olmayabilir: DEMO-38, 2026-08-16'da tamamlanmış görünüyor."),
        (
            g.check_no_conflict,
            "Kayıtlı hiçbir fact'in yakın zamandaki aktiviteyle çeliştiğini gösteren bir durum bulunmamaktadır.",
        ),
        (g.check_no_conflict, "Yakın zamanda biten DEMO-38 ve DEMO-36, fact'lerinizle çelişen herhangi bir bilgi içermiyor."),
        (g.check_pending_repeat, "'Uses PostgreSQL 15' kaydettiğimiz PostgreSQL 15 fact'ine benziyor; onaylamana gerek yok."),
    ],
)
def test_a_right_answer_passes(check, answer):
    """A correctly grounded model answer passes its matching check function."""
    assert check(answer) is None


@pytest.mark.parametrize(
    "check, answer, why",
    [
        (g.check_open_list, "Açık işler: DEMO-90, DEMO-777, DEMO-141, DEMO-140.", "invented"),
        (g.check_open_list, "Açık işler: DEMO-90.", "lists only"),
        (g.check_open_list_cut, "DEMO-90 DEMO-141 DEMO-140 DEMO-139 DEMO-138", "cut short"),
        (g.check_not_linked, "Açık işleriniz: DEMO-90 ve DEMO-141.", "invented"),
        (g.check_not_linked, "Şu an açık iş yok.", "no linked Jira"),
        (g.check_recently_done, "DEMO-38 ve DEMO-99 tamamlandı, 16 Ağustos'ta.", "invented"),
        (g.check_recently_done, "DEMO-38 tamamlandı.", "no date"),
        (g.check_unknown_topic, "Önbellekleme için Redis kullanmaya karar verdik.", "nothing was found"),
        (g.check_unknown_topic, "Bir kayıt bulamadım ama Redis kullanılıyor olabilir.", "made up"),
        (g.check_conflict_is_cited, "Bu fact güncel olmayabilir.", "doesn't cite DEMO-38"),
        (g.check_conflict_is_cited, f"DEMO-38 çelişiyor (fact {FACT_ID}).", "leaked"),
        (g.check_no_conflict, "Auth JWT fact'i güncel olmayabilir, DEMO-38 ile çelişiyor.", "out of date"),
        (g.check_pending_repeat, "Bekleyen iki fact var: LRU önbelleği ve Uses PostgreSQL 15.", "repeats"),
        (g.check_pending_repeat, "PostgreSQL öğesi zaten kayıtlı, onu onayladım.", "approved"),
    ],
)
def test_a_wrong_answer_is_caught(check, answer, why):
    """A wrong or ungrounded model answer fails its matching check function
    with a message naming the specific reason."""
    assert why in check(answer)


def test_a_crashed_turn_is_not_a_failed_answer():
    """grade() reports a None answer as CRASHED and an empty answer as
    "no answer", distinct outcomes rather than a plain grading failure."""
    scenario = g.SCENARIOS[0]

    assert g.grade(scenario, None) == g.CRASHED
    assert g.grade(scenario, "") == "no answer"


def test_replaying_grades_saved_answers_without_a_model(tmp_path, monkeypatch):
    """main(replay=...) grades previously saved answers from a file and
    never calls the model."""
    import asyncio
    import json

    saved = {g.SCENARIOS[3].name: ["DEMO-38 tamamlandı, 2026-08-16.", "DEMO-38 tamamlandı."]}
    path = tmp_path / "answers.json"
    path.write_text(json.dumps(saved), encoding="utf-8")

    def no_model(*args, **kwargs):
        """Fail the test if replay mode calls the model instead of reusing saved answers."""
        raise AssertionError("replay must not call the model")

    monkeypatch.setattr(g, "get_answer", no_model)

    exit_code = asyncio.run(g.main(runs=5, min_rate=0.9, only=None, verbose=False, save=None, replay=str(path)))

    assert exit_code == 1  # one of the two answers has no date, so 50% < 90%
