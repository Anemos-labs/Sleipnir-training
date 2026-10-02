# Authoring task families

This corpus is training data for Sleipnir's RL pipeline (`sleipnir rl rollout`). Every task is **original**: written for
this repository, not copied or adapted from a benchmark, a competition, a textbook exercise set or someone's issue
tracker. Read [AVOID.md](AVOID.md) before choosing a subject.

You write **families**: a generator function that deterministically produces `n` tasks that differ *materially* (a
different specification, data, bug or layout; not the same task with renamed identifiers).

```
generators/<category>/<module>.py     your code (one module can register many families)
corpus/<category>/<family>.jsonl      written by tools/build.py (do not edit by hand)
admit/<category>/<family>.json        written by tools/admit.py: one verdict per task
tools/fx/                             the framework: read it, do not edit it (ask the coordinator for changes)
```

## 1. The loop

```sh
cd /home/user/Sleipnir-training
python3 tools/build.py --family 'my-family*' --jobs 1            # run the generator, validate, write the shard
python3 tools/admit.py --family 'my-family*' --concurrency 2      # prove each task sound with `sleipnir rl tasks check`
```

`admit` needs the Sleipnir binary; it is already built at `~/.cache/fx/sleipnir` (or pass `--sleipnir PATH`).
A family is done when `build` reports no problems, `admit` reports **0 failed**, and a second `build --twice` is
byte-identical (determinism). Fix the generator, never the shard.
The machine has 4 cores shared by many authors: use `--jobs 1` / `--concurrency 2`, keep every test under ~20 s, and
never leave a runaway process behind.

## 2. A family

```python
from fx import Task, dd, family

@family("py-ledger-reconcile", category="fix", lang="python", kind="fix", n=12,
        summary="one line: what varies between instances")
def gen(rng, n):                 # rng is a random.Random seeded from the family name: use it for EVERYTHING random
    for i in range(n):
        ...
        yield Task(prompt=..., difficulty=3, start={...}, hidden={...}, solution={...}, verify="...", slug=f"{i+1:02d}-...")
```

* `category` is a directory name under `generators/` (see `fx.CATEGORIES`); `lang` one of `fx.LANGS`.
* `kind` (fixtures): `fix | feature | refactor | greenfield`. For other modes it is a free label (`lookup`, `advice`, ...).
* `n` is the default number of instances; build with `--scale` to change it.
* No wall clock, no `random` without `rng`, no `os.environ`, no set/dict-order dependence, no network. Two builds must
  produce identical bytes.

### Task fields (`fx.Task`)

| field | meaning |
|---|---|
| `prompt` | what the agent is told. Written like a real person asking, not like a spec template. 60+ chars for fixtures. |
| `difficulty` | 1 trivial, 2 easy, 3 medium, 4 hard, 5 expert (see DESIGN.md). Calibrate honestly. |
| `start` | `{path: text}` the repository the agent starts in (source, README/spec, visible tests, build files). |
| `hidden` | `{path: text}` written over the checkout **only when verifying**: the real tests. Never visible to the agent. |
| `solution` | `{path: text}` whole files that differ from `start` after a correct solution (adds or overwrites; no deletes). |
| `verify` | shell command run in the checkout root, exit 0 = pass. Default per language: `fx.langs.VERIFY[lang]`. |
| `protected` | extra globs the agent must not touch. Visible test files are protected automatically (`protect_tests=True`). |
| `pass_mode` | `""` or `"json-score"`: the verifier prints `{"score": 0..1}` as its last line (partial credit; a pass needs 1.0). |
| `team` | `{"mode": "swarm", "agents": 4, "roles": [...]}` for tasks meant for a manager plus workers. |
| `context_window` | e.g. `24000` to force compaction on long-reading tasks. |
| `answer`, `gold_answer` | mode `answer`: the agent's final **message** must contain every string in `answer["contains"]` (`fold=True` ignores case); `gold_answer` is a message that satisfies it. |
| `rubric`, `checks` | mode `rubric`: criteria for a judge plus cheap deterministic checks (see `tools/score_rubric.py`). |
| `notes` | provenance: generator parameters, seeds. Shown in the catalog. |
| `slug` | unique within the family; the id is `<family>-<slug>`. Make it informative (`07-dst-gap`). |

### Modes (`@family(..., mode=...)`)

* **`fixture`** (default): edit a repo; `verify` runs in a *clean* checkout with `hidden` written over it.
  `admit` proves: `verify` **fails** on `start`, **passes** with `solution` applied (so the hidden tests must pass on
  your solution and fail on the untouched start; a task that rewards doing nothing is rejected).
* **`answer`**: the verdict is the agent's final message (plus `verify` if given). Use for questions about a repo,
  chat with a checkable result, research and recall. `answer.contains` must NOT occur in the prompt. Compute answers
  *programmatically* from the files you generate, never by hand. Gold-answer admission is checked by `admit`.
  When you can, prefer a **file answer** (the agent writes `answer.json`; a hidden checker script verifies it) as a
  fixture: it is proven by the real checker.
* **`rubric`**: not machine-verifiable; carries a rubric. Use sparingly and only where no check is possible.

### Languages and commands

Offline, no package installs, standard library only. Available: python3.11 (`unittest`; **no pytest**), go1.25
(`go test`; `go.mod` via `fx.langs.go_mod(name)`), node22 (`node --test test/*.test.js`: a bare directory argument fails on this Node, CommonJS or ESM), rust/cargo
(`cargo test --offline`, no dependencies), java (JDK 17+, plain `TestMain` with asserts; no JUnit), gcc/g++, ruby, php,
tsc, bash. `fx.langs.VERIFY` has the conventional command per language. Generators may run code while generating
(`fx.run(files, cmd)` executes a file tree in a temp dir and caches results) — use it to *compute expected values from
the reference solution* instead of typing them, and to confirm that a bug is really caught.

## 3. Quality bar (read this twice)

1. **Verifiable and fair.** The hidden tests check *documented* behaviour only. If a test needs a decision the prompt
   or README never makes, the task is unfair: document it (README in `start`) or drop the test. A correct solution
   different from yours must pass.
2. **Not gameable.** Hidden tests must not be passable by special-casing inputs or editing tests; vary inputs; include
   boundary and negative cases. Tests live in `hidden/` (and visible examples in `start/`); never let hidden content leak
   into `start` or the prompt (the validator checks the obvious cases).
3. **Material variety inside a family.** Instances differ in spec, data, structure, bug type or difficulty, and the
   prompts read differently (different voice, different amount of detail, different reporter: a user, CI output, a code
   review comment, a ticket, a terse chat message, a detailed brief). Do not generate "the same task with 12 name
   swaps". 10 instances of one family should look like 10 different tickets.
4. **Realistic.** Small but real-looking projects: README, sensible layout, idiomatic code, comments where a human
   would write them. Prompts mention only what a user would know (symptoms, goals, constraints), never the hidden tests
   or "the solution".
5. **Difficulty spread.** Within a family and across your category, cover difficulty 1 through 5 deliberately (about
   15% d1, 25% d2, 30% d3, 20% d4, 10% d5). Difficulty = how much code must be read, how subtle the defect or spec,
   how many files change, how many requirements interact. A d5 task may need 100+ agent steps.
6. **Sound runtime.** Tests finish in seconds, are deterministic (no sleeps, no real time, no randomness unseeded, no
   network, no ports), never depend on the agent's cwd beyond the repo root, and print readable failures.
7. **Original.** See AVOID.md. Do not reproduce known exercises, benchmark problems, famous katas or code from open
   source projects. Own domains, own rules, own data. If a subject feels like "that classic problem", change the rules
   until it is yours.

## 4. Using `fx.Lib` for bug-injection volume

One correct, specified library becomes many fix tasks: see `generators/fix/py_proration.py` (python) and
`generators/fix/go_colorkit.py` (go). Provide: a README that *is* the specification, a 50–200 line implementation with
real logic (branches, boundaries, arithmetic), visible tests (a few, pass), hidden tests (thorough, pass on the correct
implementation and kill most mutants: boundaries, negatives, empties, ordering, rounding, error cases), and optional
`probes` (python: expressions whose repr differs when the bug is present; they power the "a user reports" prompts).
`register_libs([...], n=10)` registers `fix-<lang prefix>-<name>` (py, go, js, ts, rs, java, c, cpp, php). The builder keeps only mutants that compile, are caught
by the hidden suite, and do not hang. Aim for libraries where the hidden suite kills >= 20 mutants.
`Lib.blurb` must be a complete sentence naming its subject ("The invoicing service uses these helpers to ...").

## 5. Other exemplars

* answer-mode with computed answers and a small context window: `generators/recall/layered_config.py`
* rubric-mode: `generators/chat/advice_rubric.py`

## 6. Rules of the road

* Edit only your own `generators/<category>/` modules (and their shards/verdicts). Do not edit `tools/` (tell the
  coordinator what you need). Do not `git commit`; the coordinator commits.
* Module names must be unique within a category directory and must not start with `_` if they register families;
  helper modules start with `_` (`generators/data/_sqlgen.py`) and are imported with
  `from generators.data import _sqlgen` or relative imports.
* A build failure in one family must not break others: keep generators independent.
* Finish by running `python3 tools/build.py --category <yours> --twice --jobs 1` and
  `python3 tools/admit.py --category <yours> --concurrency 2`, and report: families, tasks per family, difficulty and
  language histogram, anything flaky or unfair you noticed, ideas you did not get to.
