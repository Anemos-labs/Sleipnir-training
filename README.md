# Sleipnir-training

**8,457 original, machine-checkable tasks in 853 families for training [Sleipnir](https://github.com/Anemos-labs/Sleipnir) with reinforcement
learning, across every kind of work a coding agent is asked to do** — fixing bugs, building programs and games, optimising,
refactoring, writing tests, reviewing, diagnosing failures, SQL and shell, configuration, porting, security, documentation,
research over local documents, long-context memory, swarm projects, honesty and injection resistance, understanding a codebase,
prompts in fifteen languages, and plain conversation.

Every task was written for this repository. None is copied from, or adapted from, a benchmark, a competition, an exercise
set or someone's issue tracker, and the corpus is scanned against the real benchmark texts to prove it
([how](docs/AVOID.md), [result](catalog/CONTAMINATION.md)). Every task is *proven sound* by Sleipnir's own
`rl tasks check`: its verifier fails on the starting state and passes with the reference solution.

| | |
|---|---|
| tasks | 8,457 in 853 families and 23 categories (7,234 fixtures, 1,094 answer-mode, 129 rubric; 153 for a swarm): [`catalog/STATS.md`](catalog/STATS.md) has them by category, difficulty (d1 trivial … d5 expert) and language |
| the list | [`catalog/index.jsonl`](catalog/index.jsonl) (one line per task, with its prompt) and [`catalog/FAMILIES.md`](catalog/FAMILIES.md) |
| the data | [`corpus/<category>/<family>.jsonl`](corpus): self-contained tasks (prompt, start files, hidden verifier files, reference solution) |
| the generators | [`generators/`](generators): deterministic Python (standard library only); they are the source of truth |
| proof of soundness | [`admit/`](admit): one verdict per task from `sleipnir rl tasks check` |

## Use it

```sh
(cd ../Sleipnir && go build -o ~/.cache/fx/sleipnir ./cmd/sleipnir)
make dist CONC=4                       # dist/tasks.jsonl + blobs/ + repos/ (+ train/val/test by family), proven again locally
cd dist && sleipnir rl rollout --tasks tasks.train.jsonl --blobs blobs --group 8 --concurrency 16 \
    --model my-policy --base-url http://vllm:8000/v1 --capture --out runs/r001
```

[docs/USING.md](docs/USING.md) has the details (selection, splits, what the three modes mean for rewards).

## What is in it

| category | what the agent is asked to do | how it is checked |
|---|---|---|
| `fix` | find and repair a bug: bugs injected into 233 specified libraries in 9 languages, plus 34 hand-built multi-file bug families in 7 languages | hidden tests |
| `feature` | add a feature to an existing codebase (slice-composed apps in 6 languages) | hidden tests incl. regressions |
| `greenfield`, `project` | build a program from a specification; long-horizon multi-module builds and migrations (d4–d5) | hidden tests, partial credit on `project` |
| `games` | build, repair or extend game engines with invented rules; write bots scored by a seeded tournament | hidden scenario files, tournament score |
| `refactor`, `optimize` | restructure with behaviour kept; make it fast under deterministic work counters | behaviour tests + structural or operation-count checks |
| `testing`, `review`, `debug` | write tests (scored on hidden mutants), review a change (scored against planted defects), diagnose from logs/traces/bisect series | partial-credit scripts |
| `data`, `shell`, `devops` | SQL against a hidden database, ETL, shell and Makefile work, CI/Docker/systemd/manifest configuration | scripts on hidden inputs |
| `port`, `security` | translate between languages; fix and audit vulnerabilities | target-language hidden tests, exploit tests |
| `docs` | docstrings, READMEs, changelogs with mechanical checks | doctests, extracted snippets, parsers |
| `research`, `recall`, `explain` | answer from a local document corpus; memory under small context windows; understand a codebase | final message or answer file, computed answers |
| `swarm`, `robust` | manager + workers on multi-component repos; blocked/ask-first/injection/secret/scope/false-premise behaviour | integration tests, canaries, manifests |
| `chat`, `i18n` | questions, calculation, constrained writing, small talk, restraint, in 15 languages | computed answers, checkers, rubrics |

Each category exercises something Sleipnir trains: `swarm` and `project` the manager's dispatch and the merge queue; `recall` and
the small `context_window` tasks compaction and `recall`; `robust` the honest-done reward and the hack detectors; `review` the
reviewer role; `explain`, `research` and `chat` answering without editing; `fix` / `feature` / `greenfield` the core edit-test loop.

## Honesty about what this is (read before trusting a number)

* **Authored, not harvested.** I considered public task datasets and used none: the code-task ones are the benchmarks Sleipnir is
  measured on, and the chat/instruction ones carry licence terms and no verifier. Public benchmark *texts* are used only to detect
  overlap (downloaded into a local cache by `tools/contam.py fetch`, never stored here). Covered by the scan: HumanEval(+),
  MBPP, SWE-bench (+Verified, dev), CRUXEval, BigCodeBench, ClassEval, IFEval, GSM8K, MMLU, Spider, APPS (first 2,000
  problems), LiveCodeBench (first 200), Exercism problem descriptions (61 of the 107 slugs available), and Sleipnir's own bench, source and Go standard-library copies. **Not
  covered** (could not be fetched here): Aider's polyglot repository, Terminal-Bench, QuixBugs, DS-1000. The scan is evidence of
  non-overlap with those texts, not a proof that no task resembles some benchmark.
* **Families, not independent samples.** Tasks from one family share a library, a world or a skeleton (e.g. 10 injected bugs in
  one library). They are different tasks with different verifiers, but they are correlated: split by family (`tools/split.py` does).
* **Some checks are weak by construction.** Sleipnir's `verifier.expect` is "the final message contains these strings". An answer
  of `7` is satisfied by any message containing a 7, which a policy could learn to exploit by listing candidates. 159 tasks
  have only strings of three characters or fewer; they are flagged `weak_check` in the catalog and left out of `make dist` unless you pass
  `--keep-weak`. Most other answer tasks use distinctive or bracketed answers or a file checked by a hidden script. Adding a
  stricter `expect` mode to Sleipnir (an anchored regex or an exact-line match) would remove the problem; that is the single most useful change on the harness side.
* **Rubric tasks (129) have no machine verdict.** They carry rubric criteria and cheap checks (`tools/score_rubric.py`) and need a judge; they
  are not part of `dist/`.
* **Limits of the task format.** A task's repository is a single commit and its verifier sees only a diff, so tasks about git history, deleting
  files (a reference solution can only add or overwrite) or anything outside the workspace are not expressible; they are approximated (bisect over a
  patch series, junk files that must stay out of the diff, ...).
* **Timing.** Performance tasks use operation counters, query counters or inputs sized so the naive version is far too slow, not tight wall-clock
  margins; in the final admission every task failed on its start state twice in a row and passed with its reference solution twice in a row (idle 4-core machine, `--repeats 2`).
  A few families run a seeded tournament or wait on child processes; give them generous `wall_s` when running many rollouts in parallel.
* **Mutation families are the volume.** A quarter of the corpus (about 2,100 tasks) is single-token bug injection into 233 specified libraries, with prompts in many
  voices and symptoms taken from what the hidden suite actually reports. They are good for volume and cheap to verify; weight categories (not families)
  when you build a training mix.

## Layout

```
generators/<category>/*.py     the families (deterministic Python); _*.py are helpers
corpus/<category>/<family>.jsonl     generated tasks, one per line (committed so the data is usable without running anything)
admit/<category>/<family>.json       verdicts of `sleipnir rl tasks check`
catalog/                       index.jsonl, STATS.md, FAMILIES.md, CONTAMINATION.md, REMOVED.md, splits.json
tools/                         fx (framework), build.py, admit.py, contam.py, catalog.py, split.py, score_rubric.py
docs/                          AUTHORING.md, AVOID.md, DESIGN.md, USING.md, ASSIGNMENTS.md
```

`make help` lists the targets (`build`, `check`, `admit`, `scan`, `catalog`, `dist`). To add tasks read [docs/AUTHORING.md](docs/AUTHORING.md).

## Licence

Not decided yet (the Sleipnir repository has the same open question). Until the owner picks one, treat the contents as all rights reserved.
