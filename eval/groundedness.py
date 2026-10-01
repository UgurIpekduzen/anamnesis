"""Groundedness eval: real Vertex AI calls, NOT part of pytest.

Is what the chat agent says backed by what its tools returned? Each scenario
gives the agent fake tool data and one question, then checks the answer with
plain rules — no second model judging the first, so a result means the same
thing every time:

- no ticket key in the answer that the data doesn't contain (no inventions);
- what the data does say is there (real keys, a real date, the citation of
  the ticket that contradicts a saved fact);
- what the data doesn't say isn't claimed ("nothing found" when nothing is);
- no internal fact_id leaks into the answer.

The model isn't deterministic, so every scenario runs several times and is
reported as a pass rate. `task eval:groundedness` prints the table; the
baseline is recorded in eval/groundedness_baseline.md. Exits non-zero when a
scenario falls below --min-rate, which is how a later prompt or tool change
that makes answers worse shows up.

Run with `task eval:groundedness` (optionally `-- --runs 3`). Add a scenario by
appending to SCENARIOS below.
"""

import argparse
import asyncio
import json
import logging
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

import agent.agent as agent_module

# Vertex's per-minute quota is what this eval runs into first: a few calls at
# a time, and a short wait before trying a rate-limited one again.
CONCURRENCY = 2
QUOTA_RETRIES = 3
QUOTA_WAIT_SECONDS = 8

OWNER_UID = "eval@example.com"
TENANT_ID = "eval-tenant"

# Realistic-looking ids: an answer that shows one to the user is a leak.
FACT_IDS = ["9AbXc2QwErTy5UiOp0Lk", "7ZxCv1BnMaSd3FgHj8Kl", "3QwEr4TyUiOp6AsDf9Gh"]


def _fact(fact_id: str, content: str, category: str) -> dict:
    return {
        "fact_id": fact_id,
        "content": content,
        "category": category,
        "source": "chat",
        "created_at": None,
    }


AUTH_FACT = _fact(FACT_IDS[0], "Auth JWT ile refresh token kullanıyor.", "architecture")
CORS_FACT = _fact(FACT_IDS[1], "CORS middleware henüz servislere eklenmedi", "bug")
POSTGRES_FACT = _fact(FACT_IDS[2], "Veritabanı olarak PostgreSQL 15 kullanıyoruz", "architecture")

# Made-up tickets: the eval's data must not carry anyone's real project.
OPEN_ISSUES = [
    "DEMO-90 · Task · To Do · Fatura dışa aktarımına yeniden deneme mantığı ekle",
    "DEMO-141 · Task · To Do · Kullanıcı rehberi taslağını gözden geçir",
    "DEMO-140 · Task · To Do · Bildirim testi ara sıra başarısız oluyor — test izolasyon sorunu",
    "DEMO-139 · Task · To Do · Arama filtresi küçük veri setinde bile yavaş",
    "DEMO-138 · Task · In Progress · Rapor sayfası için sayfalama seçeneklerini değerlendir",
]
DONE_ISSUES = [
    "DEMO-38 · Task · Done · 2026-08-16 · Tüm servislere CORS ayarını ekle ve tarayıcıdan doğrula",
    "DEMO-36 · Task · Done · 2026-08-16 · Ortam değişkenlerini kontrol et — varsayılan değer kalmamış olmalı",
]
PENDING = [
    {
        "content": "Adds an LRU cache for token lookups",
        "category": "decision",
        "similar_to_saved": None,
    },
    {"content": "Uses PostgreSQL 15", "category": "architecture", "similar_to_saved": None},
]

KEY = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")


@dataclass
class Scenario:
    """One groundedness test case: a question, the fake tool data to answer
    it from, and the rule-based check its answer must pass."""

    name: str
    message: str
    check: Callable[[str], str | None]  # None = pass, else why not
    jira_key: str | None = "DEMO"
    open_issues: list = field(default_factory=lambda: list(OPEN_ISSUES))
    open_truncated: bool = False
    done_issues: list = field(default_factory=lambda: list(DONE_ISSUES))
    facts: list = field(default_factory=lambda: [AUTH_FACT, POSTGRES_FACT])
    pending: list = field(default_factory=lambda: list(PENDING))


def keys_in(text: str) -> set[str]:
    """Every ticket-key-shaped substring (e.g. "DEMO-38") found in text."""
    return set(KEY.findall(text))


def real_keys(*lines: list) -> set[str]:
    """Every ticket key that actually appears across one or more lists of
    formatted issue lines (e.g. OPEN_ISSUES, DONE_ISSUES)."""
    return {k for group in lines for line in group for k in keys_in(line)}


def mentions(text: str, words: list[str]) -> bool:
    """Whether text contains any of words, case-insensitively."""
    lowered = text.lower()
    return any(w.lower() in lowered for w in words)


def leaked_id(text: str) -> str | None:
    """Why text fails, if it contains a raw internal fact_id — None if it
    doesn't leak one."""
    return next((f"leaked a fact_id ({i[:6]}…)" for i in FACT_IDS if i in text), None)


def only_real_keys(answer: str, allowed: set[str]) -> str | None:
    """Why answer fails, if it cites a ticket key outside allowed — None if
    every key it mentions is real."""
    invented = keys_in(answer) - allowed
    return f"invented ticket keys: {sorted(invented)}" if invented else None


def first_problem(*problems: str | None) -> str | None:
    """The first non-None reason among problems, or None if they all
    passed."""
    return next((p for p in problems if p), None)


OPEN = real_keys(OPEN_ISSUES)
DONE = real_keys(DONE_ISSUES)


def check_open_list(answer: str) -> str | None:
    """Why answer fails the "list my open Jira issues" scenario: an invented
    key, too few of the real open issues shown, or a leaked fact_id."""
    shown = keys_in(answer) & OPEN
    return first_problem(
        only_real_keys(answer, OPEN),
        None if len(shown) >= 3 else f"lists only {len(shown)} of the {len(OPEN)} open issues",
        leaked_id(answer),
    )


def check_open_list_cut(answer: str) -> str | None:
    """Same as check_open_list, plus: the answer must say the open-issue
    list was truncated (this scenario's data has more than fit)."""
    return first_problem(
        check_open_list(answer),
        None
        if mentions(
            answer,
            [
                "daha fazla",
                "daha eski",
                "listelenme",
                "gösterilme",
                "görünmeyen",
                "başka açık",
                "more",
            ],
        )
        else "doesn't say the list is cut short",
    )


def check_not_linked(answer: str) -> str | None:
    """Why answer fails when no Jira project is linked: it must say so and
    invent no ticket keys at all."""
    return first_problem(
        f"invented ticket keys: {sorted(keys_in(answer))}" if keys_in(answer) else None,
        None
        if mentions(answer, ["bağlı", "bağlan", "link"])
        else "doesn't say there is no linked Jira project",
    )


def check_recently_done(answer: str) -> str | None:
    """Why answer fails the "recently done" scenario: an invented key, none
    of the real finished issues named, or no date from the data given."""
    return first_problem(
        only_real_keys(answer, DONE),
        None if keys_in(answer) & DONE else "names none of the finished issues",
        None
        if mentions(answer, ["2026-08-16", "16 Ağustos", "16.08.2026", "Ağustos"])
        else "gives no date from the data",
    )


def check_unknown_topic(answer: str) -> str | None:
    """Why answer fails when asked about a topic with no saved fact: it must
    say nothing was found, not invent a decision, and not leak a fact_id."""
    return first_problem(
        None
        if mentions(
            answer,
            # Stems, because Turkish inflects: bulamadım, bulamıyorum,
            # bulunamadı, bulunmamaktadır ...
            [
                "bulam",
                "bulunam",
                "bulunma",
                "bulunmuyor",
                "yok",
                "kaydedilmemiş",
                "kaydetmemi",
                "rastlam",
                "not found",
                "couldn't find",
                "no record",
            ],
        )
        else "doesn't say nothing was found",
        "made up a caching decision"
        if mentions(answer, ["Redis", "Memcached", "LRU", "TTL"])
        else None,
        leaked_id(answer),
    )


def check_conflict_is_cited(answer: str) -> str | None:
    """Why answer fails when a saved fact is contradicted by a real, done
    ticket: it must cite that ticket by key, not invent others, and not
    leak a fact_id."""
    return first_problem(
        None
        if "DEMO-38" in answer
        else "doesn't cite DEMO-38, the ticket that contradicts the saved fact",
        only_real_keys(answer, DONE),
        leaked_id(answer),
    )


# What the model says when it does find something out of date. Sentences that
# say nothing was found ("çeliştiğini gösteren bir durum bulunmamaktadır") vary
# too much to list, so the check looks for the flagging phrases instead.
FLAG_PHRASES = [
    "güncel olmayabilir",
    "güncelliğini yitirmiş olabilir",
    "may be outdated",
    "çelişiyor",
    "çelişmektedir",
    "eskimiş",
    "eski kalmış",
    "artık geçerli değil",
    "güncellenmesi gerek",
]


def check_no_conflict(answer: str) -> str | None:
    """Why answer fails when nothing actually conflicts: it must not call a
    saved fact out of date, and not leak a fact_id.

    Citing the recent tickets is fine ("none of them contradicts your
    facts"): what counts is whether it calls a saved fact out of date.
    """
    return first_problem(
        "calls a saved fact out of date though nothing conflicts"
        if mentions(answer, FLAG_PHRASES)
        else None,
        leaked_id(answer),
    )


def check_pending_repeat(answer: str) -> str | None:
    """Why answer fails when a pending fact repeats one already saved: it
    must name the repeated item, say it's a repeat, and not claim it was
    approved (only the user can do that)."""
    return first_problem(
        None if "postgresql" in answer.lower() else "doesn't mention the PostgreSQL item",
        None
        if mentions(
            answer,
            [
                "zaten",
                "already",
                "tekrar",
                "aynı",
                "duplicate",
                "kayıtlı",
                "benz",
                "similar",
                "eşleş",
            ],
        )
        else "doesn't say the PostgreSQL item repeats a saved fact",
        "claims it approved something" if mentions(answer, ["onayladım", "approved it"]) else None,
    )


SCENARIOS = [
    Scenario("open Jira issues: real keys only", "Açık Jira işlerim neler?", check_open_list),
    Scenario(
        "open Jira issues: says the list is cut",
        "Açık Jira işlerim neler?",
        check_open_list_cut,
        open_truncated=True,
    ),
    Scenario(
        "Jira not linked: says so, invents nothing",
        "Açık Jira işlerim neler?",
        check_not_linked,
        jira_key=None,
    ),
    Scenario(
        "recently done: real keys and dates",
        "Son zamanlarda hangi Jira işleri tamamlandı?",
        check_recently_done,
    ),
    Scenario(
        "saved facts: an unknown topic isn't invented",
        "Önbellekleme (caching) hakkında ne karar verdik?",
        check_unknown_topic,
    ),
    Scenario(
        "outdated check: the conflict is cited",
        "Kayıtlı fact'lerim güncel mi?",
        check_conflict_is_cited,
        facts=[AUTH_FACT, CORS_FACT],
    ),
    Scenario(
        "outdated check: nothing conflicts, nothing flagged",
        "Kayıtlı fact'lerim güncel mi?",
        check_no_conflict,
    ),
    Scenario(
        "pending triage: spots a repeat of a saved fact",
        "Bekleyen fact'lerden hangilerini onaylamalıyım?",
        check_pending_repeat,
    ),
]

# The originals, taken once: the tools are looked up by name when the agent is
# built, so each scenario swaps fakes in and they must not stack.
_ORIGINALS = {
    name: getattr(agent_module, name)
    for name in (
        "get_tenant_facts",
        "get_fact",
        "get_jira_status",
        "get_jira_recently_done",
        "get_github_status",
        "get_github_history",
        "get_pending_facts_summary",
        "get_owned_tenant",
        "get_jira_credentials",
    )
}


def _install_fakes(s: Scenario) -> None:
    def fake(name, body):
        """Wrap body as a fake replacement for the real tool called name,
        copying the real tool's __name__/__doc__ so ADK's model-facing
        schema is unaffected by the swap."""
        original = _ORIGINALS[name]

        def wrapper(*args, **kwargs):
            """Call body, ignoring the real tool's own arguments/behavior."""
            return body(*args, **kwargs)

        # ADK builds the model's tool schema from the name and docstring.
        wrapper.__name__, wrapper.__doc__ = original.__name__, original.__doc__
        return wrapper

    m = agent_module
    m.get_tenant_facts = fake("get_tenant_facts", lambda *a, **k: s.facts)
    m.get_fact = lambda tenant_id, fact_id, owner_uid: next(
        f for f in s.facts if f["fact_id"] == fact_id
    )
    m.get_jira_status = fake(
        "get_jira_status", lambda *a, **k: {"issues": s.open_issues, "truncated": s.open_truncated}
    )
    m.get_jira_recently_done = fake(
        "get_jira_recently_done", lambda *a, **k: {"issues": s.done_issues, "truncated": False}
    )
    m.get_github_status = fake(
        "get_github_status", lambda *a, **k: {"pull_requests": [], "issues": []}
    )
    m.get_github_history = fake(
        "get_github_history",
        lambda *a, **k: {"pull_requests": [], "issues": [], "truncated": False},
    )
    m.get_pending_facts_summary = fake(
        "get_pending_facts_summary", lambda *a, **k: {"pending": s.pending, "truncated": False}
    )
    m.get_owned_tenant = lambda tenant_id, owner_uid: {
        "jira_project_key": s.jira_key,
        "github_repo": None,
    }
    m.get_jira_credentials = lambda owner_uid: {
        "email": "e@example.com",
        "token": "t",
        "base_url": "https://x",
    }


CRASHED = "the turn crashed"


async def get_answer(s: Scenario, index: int, gate: asyncio.Semaphore) -> str | None:
    """The agent's answer, or None if the turn could not finish at all (quota,
    network). That says nothing about the model's answers, so it stays out of
    the pass rate."""
    message = types.Content(role="user", parts=[types.Part(text=s.message)])
    async with gate:
        for attempt in range(QUOTA_RETRIES + 1):
            runner = Runner(
                agent=agent_module.build_agent(OWNER_UID, TENANT_ID),
                app_name="anamnesis-eval-groundedness",
                session_service=InMemorySessionService(),
                auto_create_session=True,
            )
            answer = ""
            try:
                async for event in runner.run_async(
                    user_id=OWNER_UID, session_id=f"g-{index}-{attempt}", new_message=message
                ):
                    if event.is_final_response() and event.content and event.content.parts:
                        # All the text parts: an answer can arrive split in several.
                        answer = "".join(part.text or "" for part in event.content.parts)
            except Exception as exc:
                if (
                    "RESOURCE_EXHAUSTED" in repr(exc) or "429" in repr(exc)
                ) and attempt < QUOTA_RETRIES:
                    await asyncio.sleep(QUOTA_WAIT_SECONDS * (attempt + 1))
                    continue
                return None
            return answer
    return None


def grade(s: Scenario, answer: str | None) -> str | None:
    """Why a run failed, or None if it passed."""
    if answer is None:
        return CRASHED
    return s.check(answer) if answer else "no answer"


async def main(
    runs: int,
    min_rate: float,
    only: str | None,
    verbose: bool,
    save: str | None,
    replay: str | None,
) -> int:
    """Run every scenario (or only those matching `only`), print a pass-rate
    table, and return 1 if any scenario falls below min_rate, else 0.

    Args:
        runs (int): How many times to run each scenario, since the model
            isn't deterministic.
        min_rate (float): The pass rate (0-1) a scenario must reach.
        only (str | None): If given, skip scenarios whose name doesn't
            contain this text.
        verbose (bool): Print the full answer of every failed run.
        save (str | None): If given, write every collected answer to this
            file as JSON, for later --replay.
        replay (str | None): If given, grade the answers saved in this file
            instead of calling the model again.
    """
    # ADK prints a stack trace for every rate-limited call it goes on to retry;
    # the retries in get_answer handle those, so that is only noise here.
    logging.disable(logging.ERROR)
    gate = asyncio.Semaphore(CONCURRENCY)
    # --replay grades answers saved earlier, with no model call: the checks can
    # be reworked in seconds and for free. Only new answers cost tokens.
    saved = json.load(open(replay, encoding="utf-8")) if replay else {}
    collected: dict[str, list[str | None]] = {}
    rows = []
    below = 0
    for s in SCENARIOS:
        if only and only.lower() not in s.name.lower():
            continue
        if replay:
            answers = saved.get(s.name, [])
        else:
            _install_fakes(s)
            answers = list(await asyncio.gather(*[get_answer(s, i, gate) for i in range(runs)]))
        if not answers:
            continue
        collected[s.name] = answers
        results = [grade(s, a) for a in answers]
        crashed = results.count(CRASHED)
        counted = len(answers) - crashed
        failures = Counter(r for r in results if r and r != CRASHED)
        passed = counted - sum(failures.values())
        rate = passed / counted if counted else 0.0
        below += rate < min_rate
        rows.append((s.name, passed, counted, crashed))
        note = f"  ({crashed} crashed, not counted)" if crashed else ""
        print(f"  {s.name:<52} {passed}/{counted}{note}")
        for reason, count in failures.most_common():
            print(f"      x{count}  {reason}")
        if verbose:
            for reason, answer in zip(results, answers):
                if reason and reason != CRASHED:
                    print(f"      --- {reason}\n      {(answer or '').strip()[:600]!r}")

    if save:
        json.dump(collected, open(save, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\nAnswers saved to {save}; grade them again with --replay {save}")
    total = sum(r[1] for r in rows)
    count = sum(r[2] for r in rows)
    print(
        f"\nOverall: {total}/{count} runs passed ({total / count:.0%})"
        if count
        else "\nNo scenario matched."
    )
    print(
        f"FAIL: {below} scenario(s) below {min_rate:.0%}"
        if below
        else f"OK: every scenario is at or above {min_rate:.0%}"
    )
    return 1 if below else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=5, help="repetitions per scenario (default 5)")
    parser.add_argument(
        "--min-rate", type=float, default=0.8, help="pass rate a scenario must reach (default 0.8)"
    )
    parser.add_argument("--only", help="run only scenarios whose name contains this text")
    parser.add_argument(
        "--verbose", action="store_true", help="print the answer of every failed run"
    )
    parser.add_argument(
        "--save-answers", metavar="FILE", help="write the model's answers to FILE (JSON)"
    )
    parser.add_argument(
        "--replay", metavar="FILE", help="grade the answers saved in FILE: no model call, no tokens"
    )
    args = parser.parse_args()
    sys.exit(
        asyncio.run(
            main(args.runs, args.min_rate, args.only, args.verbose, args.save_answers, args.replay)
        )
    )
