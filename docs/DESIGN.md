# Design

## What this is

A corpus of **original, machine-checkable tasks** for Sleipnir's RL environment (`sleipnir rl rollout --tasks ...`),
spread over every kind of work a coding agent is asked to do: fixing, building, speeding up, refactoring, testing,
reviewing, diagnosing, data and shell work, configuration, porting, security, documentation, research, long-context
memory, swarm projects, honesty and robustness, and plain conversation.

Sources of truth are the **generators** in `generators/` (deterministic Python, standard library only). Their output,
the **corpus** shards in `corpus/<category>/<family>.jsonl`, is committed so the data is usable without running them.
`tools/admit.py` materialises tasks with Sleipnir's own `rl taskgen fixture` and proves them sound with
`rl tasks check`; the per-task verdicts are committed in `admit/`.

## Difficulty scale

| d | name | what it asks of the agent | typical size |
|---|---|---|---|
| 1 | trivial | one obvious change in one file; the symptom names the place | < 30 agent steps |
| 2 | easy | find the place, one or two edits, a clear spec | ~30 steps |
| 3 | medium | read several files, reconcile spec and code, handle edge cases | ~45 steps |
| 4 | hard | several interacting requirements or a subtle defect; multi-file changes; design choices | ~70 steps |
| 5 | expert | large or deceptive: multi-component, long-context, performance or concurrency reasoning | 100+ steps |

## Modes

* `fixture`: edit a repository; a hidden verifier runs in a clean checkout. Proven by `rl tasks check` (fails on the
  start, passes with the reference solution).
* `answer`: the final message must contain the expected strings (plus an optional verifier command).
* `rubric`: open-ended; carries a rubric and cheap deterministic checks. Needs a judge or `tools/score_rubric.py`.

## Provenance and contamination

Everything is authored for this repository (see `docs/AVOID.md`). `tools/contam.py` compares every task against the
texts of public benchmarks (downloaded into a local cache, never stored here) and against Sleipnir's own bench and
source; the scan report is committed in `catalog/CONTAMINATION.md`.
