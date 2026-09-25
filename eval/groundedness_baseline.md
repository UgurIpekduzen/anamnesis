# Groundedness baseline

What `task eval:groundedness` measured on **2026-09-25**, model `gemini-2.5-flash`
(the agent's model in `agent/agent.py`), 5 runs per scenario, fake tool data.
Compare a later run with this one after changing the instruction, a tool, or
the model: a scenario that drops clearly below its number here got worse.

| Scenario | Passed |
|---|---|
| open Jira issues: real keys only | 5/5 |
| open Jira issues: says the list is cut | 4/5 |
| Jira not linked: says so, invents nothing | 5/5 |
| recently done: real keys and dates | 5/5 |
| saved facts: an unknown topic isn't invented | 5/5 |
| outdated check: the conflict is cited | 5/5 |
| outdated check: nothing conflicts, nothing flagged | 5/5 |
| pending triage: spots a repeat of a saved fact | 5/5 |
| **Overall** | **39/40** |

The one miss: the model wrote "Devamını listeleyemesem de, açık Jira işleriniz
şunlardır…" ("even though I can't list the rest…"). It does hint that there are
more, in words the rule doesn't know; it is left as it is rather than widening
the rule for one sentence.

The scenario data is made up (`DEMO-…` tickets): a first version of this eval
used real ticket titles from a private project and was replaced before it left
the machine, then measured again (40/40 with the real titles, 39/40 with these).

## Read it with these limits in mind

- **One sample of 5 is a small sample.** While the eval was being written the
  same scenarios ran about five times and scored between 36 and 40 of 40. Almost
  every miss turned out to be a check that was too narrow for Turkish
  ("görünmeyen", "benziyor", "kaydetmemişiz"), fixed and pinned by
  `test/test_eval_groundedness.py`. **One was real:** in "outdated check: the
  conflict is cited" the model showed the user a raw `fact_id`
  (`7ZxCv1…`) although the instruction says never to, once in about 25 answers.
  It didn't happen in the recorded run; it is a known intermittent weakness.
- **The checks are rules, not a judge.** They look for real ticket keys, dates,
  the citation of the contradicting ticket, "nothing found" wording, and leaked
  ids. They can't tell that an answer is *worded* badly, and a new phrasing the
  rules don't know can be marked wrong: read the failing answers with
  `--verbose` before trusting a drop.
- **Fake data, real model.** The tools return fixed data, so this measures how
  the model reports what it is given, not whether the tools fetch the right
  thing (the unit tests cover those).

## Cost

One full run (8 scenarios x 5 runs, about 40 agent turns) took between
**2.5 and 7.5 minutes**, depending on how busy Vertex's per-minute quota was:
two calls run at a time and a rate-limited call waits and retries. It costs a
few cents in tokens.

Grading is separate from asking. `--save-answers FILE` keeps the model's
answers and `--replay FILE` grades them again in seconds with no model call,
which is how the checks were reworked without paying for a run each time.
