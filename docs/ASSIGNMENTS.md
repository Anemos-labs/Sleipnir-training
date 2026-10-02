# Assignments

Common to every assignment: read `docs/AUTHORING.md`, `docs/AVOID.md`, `docs/DESIGN.md`, `tools/fx/core.py`,
`tools/fx/lib.py` and the exemplar generators first. Always pass `--category <yours>` to `tools/build.py` (it then only
imports your category). Tool facts: no PyYAML (ruby has `-ryaml`; python has `tomllib`, `sqlite3`, `json`, `csv`,
`configparser`, `ast`, `difflib`, `re`, `argparse`, `unittest`), no pytest, no sqlite3 CLI (use python's module),
`jq awk sed diff patch tar zip unzip base64 sha256sum` exist, `gcc -fsanitize=address` works, `go`, `cargo`, `javac`,
`node`, `tsc`, `ruby`, `php`, `bash` exist. Verifier scripts that you hide (`.check/verify.py`, ...) may be any language
available; they must not depend on `.git`, the network, the time of day or the cwd except the repo root.

Targets are *admitted tasks* (build clean and `admit` 0 failed). Quality and originality beat count; but the point of
the corpus is volume with variety, so keep going until the target is met with real variety, not clones.
Difficulty spread (all categories): ~15% d1, 25% d2, 30% d3, 20% d4, 10% d5.

---

## fix-py-1 — `generators/fix/pylib1_*.py` — python libraries, theme: **time, money and scheduling**
Target: >= 30 libraries, `n=10` each (~300 tasks). Use `fx.Lib` + `register_libs`. Invent distinct, slightly unusual
domains: ferry/transit fare rules with zones and transfers, shift rosters and overtime, library fines, parking tariffs,
SLA clocks that pause outside business hours, business-day arithmetic with custom holiday calendars, tide-window dock
scheduling, recurring-event expansion, duration parsing/formatting, fixed-offset time conversion tables (no zoneinfo),
payroll bands, stamp-duty-like progressive taxes for an invented jurisdiction, loyalty points with expiry, invoice
numbering and rounding-allocation, subscription renewals, meeting-room conflict detection, rate cards with
peak/off-peak, currency conversion with spreads, ledger reconciliation, layaway instalments, late-fee compounding.
Libraries of 60–200 lines with real branches and boundary conditions; some should be 2–3 modules (mutate several files).
Vary difficulty by library complexity (`Lib.difficulty` 1–4). `probes` for every python library.

## fix-py-2 — `generators/fix/pylib2_*.py` — python libraries, theme: **text, formats and parsing**
Target: >= 30 libraries, `n=10` each (~300 tasks). Domains: log-line formats, `.env`/properties/key-value dialects,
query-string and URL/path normalisation, HTTP header and media-type parsing, semantic-version constraint resolution
(invented range syntax), glob and pattern matchers, template engines (invented syntax), text wrapping/justification/
column layout, ANSI/escape handling, shell-style word splitting, tokenizers for small expression languages, diff/patch
of text, changelog parsers, address/phone/ID formats of an invented country, number/size/duration formatting,
slug-free identifier mangling (snake/camel/kebab with acronym rules), ICS-like calendar lines, SRT-like subtitle
timing, pattern-based redaction, tabular text (aligned tables) parsing, version-controlled config merging, markdown-free
lightweight markup of your own invention. (Not: INI, CSV, JSON path, slugify, markdown, roman numerals, RLE.)

## fix-py-3 — `generators/fix/pylib3_*.py` — python libraries, theme: **algorithms and simulations in domain clothes**
Target: >= 28 libraries, `n=10` each (~280 tasks). Domains: inventory costing (FIFO/average) with returns, shipping
bin-packing heuristics, elevator/dispatch simulation, queueing with priorities and aging, delivery-zone routing on a
small graph with tolls, cache eviction policies with invented rules, online statistics (mean/variance/percentile
estimators), histogram bucketing, consistent hashing, workflow/approval state machines, ACL/permission evaluation with
inheritance and deny rules, rule engines, discount stacking, unit conversion with dimension checking, computational
geometry (polygon area/containment, segment clipping), music-theory intervals/chords, tournament seeding for invented
formats, scheduling with dependencies (topological with ties), resource leveling, bloom filters, matrix-free linear
tools, recommendation scoring, text diffing by tokens, fuzzy matching/scoring, undo/redo and event sourcing.
Several libraries must be multi-module (3–5 files) so bugs sit at module boundaries.

## fix-lang-1 — `generators/fix/golib_*.py`, `rslib_*.py` — **Go and Rust** libraries
Target: >= 14 Go + >= 14 Rust libraries, `n=8` each (~220 tasks). Systems-flavoured domains: bit-packed timestamps, ID
generators, TLV/binary framing, custom-polynomial checksums, time-series downsampling, backoff schedule calculators,
size/duration formatting, path/glob matching, semver-like ranges, state machines, ring/hash placement, varint-free
integer codecs of your own design, token/lexer pieces, priority scheduling, bounded resource pools (deterministic
single-threaded logic), money in fixed-point, unit tables. Go: `go.mod` via `fx.langs.go_mod`; tests with `testing`;
Rust: `Cargo.toml` via `fx.langs.cargo_toml`, `src/lib.rs`, `tests/*.rs` (hidden) and unit tests; no dependencies. Keep
test runs under ~10 s including compile. `fx.mutate` supports `go` and `rust`. See `generators/fix/go_colorkit.py`.

## fix-lang-2 — `generators/fix/jslib_*.py`, `tslib_*.py`, `javalib_*.py` — **JavaScript, TypeScript, Java**
Target: >= 10 JS + >= 8 TS + >= 10 Java libraries, `n=8` each (~220 tasks). App/backend logic: pagination cursors,
query builders, permission checks, form validation, cart pricing with promotions, invented plural rules, date-range
logic, debounce/throttle over a fake clock, undo/redo, fuzzy ranking, route matching with params (not JSONPath), template
interpolation, library-loan/seat-reservation/invoice-line domains in Java with plain `TestMain` asserts (no JUnit).
JS: CommonJS modules, `node --test test/`; TS: `tsc` with `fx.langs.tsconfig()` (check that `tsc` works offline without
@types/node; if tests need `node:test`, declare minimal ambient types or write tests that avoid them);
Java: single-file-per-class sources, `TestMain`. `fx.mutate` supports javascript, typescript and java.

## fix-lang-3 — `generators/fix/clib_*.py`, `cpplib_*.py`, `phplib_*.py` — **C, C++, PHP**
Target: >= 10 C + >= 6 C++ + >= 8 PHP libraries, `n=8` each (~190 tasks). C: explicit-length string/buffer helpers,
fixed-point arithmetic, bitfield packers, base-N codecs of your own variant, small hash tables, tokenizers, safe
arithmetic, sorting-network style utilities; layout `src/*.c`, `include/*.h`, `tests/test_main.c` (verify command in
`fx.langs.VERIFY['c']` compiles `src` and `tests`). PHP: legacy-style helpers (pagination, money, escaping, validation,
array utilities) with a self-contained `tests/run.php` harness (no PHPUnit). Mutators: c, cpp, php.

## fix-hand — `generators/fix/hand_*.py` — **hand-crafted bugs in small multi-file projects** (not token mutations)
Target: ~300 tasks, many families (>= 25), mixed languages (python, javascript, go, rust, java, ruby, bash).
Realistic defects: pagination off-by-one across layers, timezone/DST arithmetic, unicode normalisation and casing,
float accumulation and rounding, integer overflow, stale caches and invalidation, resource leaks, mutable default
arguments, shared aliasing, iterator invalidation, wrong error propagation, swallowed exceptions, wrong sort stability or
comparator, locale/encoding issues, deterministic concurrency bugs (models of races driven by a fake scheduler), order-
of-operations in config merging, state-machine transitions that skip a guard, retry logic that double-applies, wrong
JOIN semantics in embedded SQLite, path handling (relative vs absolute, symlinks via python), escaping bugs (HTML/shell/
SQL/regex), serialisation round-trip loss. Each project 3–8 files with a README, a visible failing/passing test and a
bug report written the way a user, a tester or CI would write it (some vague, some precise, some misleading). Hidden tests
include regression guards so a symptom-only patch fails.

## feature — `generators/feature/*.py` — **adding features to existing codebases**
Target: ~500 tasks, >= 30 families. Approach: author small realistic base applications (CLI tools, libraries, small
services as in-process classes, data pipelines, editors' logic, inventory/booking/analytics systems) in python,
javascript, go, rust, java; define independent *feature slices* (a reference implementation fragment + hidden tests) and
compose the start repository from a random subset of already-implemented slices; the task asks to add one missing slice
(and must not break the others), with the request written as a ticket, a chat message, a design note or a bullet list.
Include: new CLI flags and output formats, new validation rules, pluggable strategies, pagination/filtering/sorting,
import/export, caching, localisation, configuration options, backwards-compatible API evolution (old signature still works),
plugin hooks, idempotency, audit logging. Difficulty from number and interaction of slices and size of the base.

## greenfield — `generators/greenfield/*.py` — **build from a specification**
Target: ~250 tasks, >= 25 families. Empty-ish repo (README spec, interface stub or example test) and hidden tests; the
agent builds a program: parsers/interpreters for a small invented language or config format, a unit-aware calculator,
a schedule solver, a text-adventure engine, a spreadsheet-formula evaluator with cell references and cycle detection, a
diff/merge tool, a tiny regex or pattern engine with an invented syntax, a bytecode VM, a file-sync planner, a query DSL
compiler, a state-machine DSL, an event-sourcing store, a rate-plan billing engine, a CLI with subcommands and exit
codes, a plugin loader, a simple HTTP-like router (in-process), a template compiler. Languages: python, javascript, go,
rust, java, ruby, bash, c. Specs must be precise enough that hidden tests are fair; ship visible examples. Spread of sizes:
from 40-line utilities (d1–2) to multi-module systems (d5).

## games — `generators/games/*.py` — **making and repairing games**
Target: ~250 tasks, >= 25 families (greenfield and fix/feature kinds). Headless game engines with a documented API (state,
`step`/`apply(move)`, `legal_moves`, `render() -> str`, deterministic seeded RNG that you specify exactly) and hidden rule
tests: original rule variants (invented board games, card games with house rules, roguelike dungeon turns, puzzle games
like sliding/pushing/linking variants with new rules, tower-defence tick simulation, idle/crafting economies, text
adventures with inventory and parser, word games with an invented scoring system, dice games, tactics grids with
initiative, snake/tetris/2048/breakout *variants* with changed rules, ASCII renderers with exact output). Also: fix a
broken engine (collision off-by-one, wrong turn order, scoring bug, seed misuse), add a feature to an existing game
(undo, save/load, replay, AI opponent with a deterministic strength test against a baseline policy, level loader),
write a bot that beats a baseline in a seeded tournament (verifier plays matches; score by win rate -> `json-score`),
and a few browser-free "UI" tasks (terminal renderer with exact snapshot strings). Languages: python, javascript, go,
rust, java, c.

## refactor-opt-docs — `generators/refactor/*.py`, `generators/optimize/*.py`, `generators/docs/*.py`
Targets: ~170 refactor, ~200 optimize, ~60 docs.
* **refactor**: behaviour tests unchanged *plus* structural checks run by a hidden script (python `ast`, grep, line/
  function-length limits, duplicate-body detection, import graph, class/function presence). Extract function/class,
  de-duplicate copy-pasted handlers, replace conditional ladders with tables/strategies, split a god module while keeping
  the public import paths, rename across files with a compatibility shim, convert callbacks to async/promises (js),
  modernise legacy idioms, replace global state with injected dependencies (state the new constructor API in the prompt),
  introduce dataclasses/structs, remove dead code, flatten inheritance. Languages: python, javascript, go, java, rust.
* **optimize**: correctness on varied hidden inputs *and* a performance bar that is deterministic: operation/call counters
  through instrumented collaborators, query counters on SQLite (N+1), `testing.AllocsPerRun` in Go, `timeout` with input
  sizes where the naive version takes minutes and the good one well under a second, memory caps with `ulimit -v`.
  Quadratic -> n log n, repeated regex compile, string concatenation in loops, needless copies, missing memoisation,
  missing indexes, streaming instead of loading, batching, sorting avoidance, data-structure swaps. Languages: python,
  go, javascript, rust, java, c, sql.
* **docs**: mechanical checks: doctests pass, every public symbol documented with required sections, README usage
  snippets execute (hidden script extracts and runs fenced blocks), CHANGELOG parses in a stated format and matches the
  given commit list, generated API tables match the code, CLI `--help` matches the argparse spec.

## testing-review-debug — `generators/testing/*.py`, `generators/review/*.py`, `generators/debug/*.py`
Targets: ~200 testing, ~150 review, ~200 debug.
* **testing**: (a) *write tests for a module*: a hidden script runs the agent's tests against the correct implementation
  (must pass) and against hidden mutants (killed fraction -> `json-score`; gold kills all). (b) *regression test for a bug
  report*: the agent's new test must fail on the buggy version and pass on the fixed one (both supplied or hidden).
  (c) *repair a broken suite*: flaky time/order-dependent tests made deterministic with a fake clock; tests asserting
  implementation details; a test with a wrong expectation (fix the test, not the code; the verifier checks the code is
  unchanged and the suite still kills a mutant). Use `protect_tests=False` where the agent must edit/create tests.
  Languages: python, go, javascript, rust, java.
* **review**: the repo has a change (`change.patch` plus the files, or a PR-style description) with 2–5 planted defects
  (logic, security, concurrency model, resource leak, API misuse, off-by-one, missing validation) and some harmless style
  nits as distractors; the agent writes `review.json` (`[{file, line, category, summary}]`); the hidden checker matches
  findings to planted defects by file and line window, scores recall and penalises false positives (`json-score`).
  Vary: full review, security-only review, "is it safe to merge?" with a verdict, review of a tiny diff (d1) up to a
  500-line change (d5).
* **debug**: diagnose from evidence: a repo plus generated logs/stack traces/metrics; the agent writes `diagnosis.json`
  (`{root_cause_file, function, kind, evidence_lines, fix_summary}`) checked field by field, or fixes the code (fixture).
  Include *bisect-style* tasks (a `patches/0001...0040.patch` series, find the first bad one with a script; answer in a
  file or final message), intermittent-failure analysis from many log files, performance regressions from timing logs,
  data-corruption forensics, config-drift diagnosis, "works on my machine" environment differences.

## data-shell-devops — `generators/data/*.py`, `generators/shell/*.py`, `generators/devops/*.py`
Targets: ~330 data, ~230 shell, ~170 devops.
* **data**: SQL via python `sqlite3`: the agent writes `query.sql` (or a migration, or a fix); the hidden checker runs it
  against a *different hidden database with the same schema* and compares rows to an oracle (so hard-coding fails): joins,
  window functions, CTEs, recursive CTEs, gaps-and-islands, pivots, anti-joins, dedup, running totals, upserts,
  schema migrations that must preserve data, index choice (`EXPLAIN QUERY PLAN`), N+1 elimination. ETL in python (csv/json
  only): clean messy dates/units/encodings, reshape, join, aggregate, produce a report file; hidden inputs vary. JSON
  schema-ish validation, log aggregation, spreadsheet-as-code (CSV with formulas semantics you define), data repair.
  Invent schemas (a ferry company, a seed library, an observatory log, a repair shop) — not the classic employees/orders.
* **shell**: bash/awk/sed/jq pipelines and scripts, tested in a temp dir with awkward filenames (spaces, newlines, leading
  dashes, unicode): batch rename, dedupe by hash, organise by date, log rotation with retention rules, `getopts` CLIs,
  `set -euo pipefail` pitfalls, quoting bugs, glob/IFS pitfalls, POSIX `sh` portability, Makefile authoring and fixing
  (phony targets, dependencies, incremental rebuilds proven by touching files), small text-munging one-liners with exact
  expected output.
* **devops**: configuration as the artefact: fix/author config that a hidden validator (written by you in python/ruby)
  interprets with real semantics: CI workflow DAGs (`needs`, matrices, cycles, caching keys), Dockerfile rules (pinned tags,
  layer order for cache, non-root user, multi-stage; static checker you write), systemd units, cron schedules, nginx-like
  configs with your own semantics, package manifests (`package.json`, `pyproject.toml`, `Cargo.toml`: version constraints,
  scripts, entry points), Kubernetes-like manifests (YAML via ruby), Terraform-like HCL-lite, `.gitignore`/`.gitattributes`
  semantics, release scripts (semver bump + changelog) with golden outputs.

## port-security — `generators/port/*.py`, `generators/security/*.py`
Targets: ~200 port, ~200 security.
* **port**: translate a library between languages (python<->go, js<->python, java->python, c->rust, go->rust, ts<->js,
  bash->python, python->sql ...). Hidden tests in the *target* language check shared test vectors; include semantics
  traps (integer division/overflow, string encodings, mutable aliasing, sort stability, error idioms, nil vs zero value,
  map ordering). Also API migrations inside a language: old internal client -> new interface across many files, callbacks
  -> promises, `unittest` style -> `assert` helpers, py2-isms -> py3, deprecated stdlib calls -> current ones.
  Author >= 40 source libraries; each yields 3–5 targets/variants.
* **security**: defensive: fix the vulnerability *and* keep functionality (hidden functional tests plus hidden exploit
  payload tests): path traversal / zip-slip, SQL injection (sqlite3), command injection (`shell=True`), XSS in templating,
  SSRF allow-lists (userinfo tricks, decimal/hex IPs, redirects), unsafe deserialisation, weak token randomness,
  non-constant-time compares, JWT-like `alg=none`, open redirect, ReDoS (timeouts), integer overflow in size checks (C),
  format-string and buffer bounds (C, with `-fsanitize=address`), secrets committed to the repo (remove and load from env,
  checked by a scanner), IDOR / missing authorisation, mass assignment, TOCTOU modelled deterministically, log injection,
  CSRF-token verification. Also *audit* tasks (write `findings.json`; scored like review) and *harden* tasks.

## research-recall — `generators/research/*.py`, `generators/recall/*.py`
Targets: ~300 research, ~280 recall (answer-mode and file-answer fixtures; the recall exemplar exists).
* **research**: procedurally generated **offline corpora** (20–80 documents: incident reports, meeting notes, changelogs,
  specs with versions, lab notebooks, support tickets, budget CSVs, email threads, product reviews, regulations with
  amendments) built from structured records so every fact is known exactly, with distractors, near-duplicates, superseded
  information and contradictions. Tasks: single-hop lookup, multi-hop joins, aggregation across documents, temporal
  questions ("what was true on 14 March"), conflict resolution (newest/authoritative wins), entity resolution (aliases),
  timeline construction (`timeline.json`), table extraction (`out.csv`), a written `report.md` that must contain K of N
  required facts, cite document ids correctly, and must not contain planted falsehoods (hidden checker; `json-score`).
  Original fictional worlds only.
* **recall**: long-context and memory under small context windows (8k–32k via `context_window`): needle-in-haystack across
  many files; multi-hop through include/reference chains; facts that drift (value updated in a later file); counting and
  ordering across dozens of files; "read this constant first, then do a long unrelated job, then state the constant";
  "remember this constraint from the start of the conversation while editing code at the end" (verifier checks the
  constraint held); contradictory notes where the newest wins; large logs where the answer is the N-th anomaly. Answers
  computed programmatically.

## swarm-robust — `generators/swarm/*.py`, `generators/robust/*.py`
Targets: ~130 swarm, ~220 robust.
* **swarm**: tasks for a manager plus workers (`team={"mode": "swarm", "agents": 3..8, "roles": [...]}`; budgets scale
  automatically): monorepos with k independent modules each needing a fix or feature plus an integration test (score = fraction
  of components passing via `json-score`; gold = 1.0), parallel features behind a shared interface contract, pipeline stages
  A->B->C, merge-conflict-prone shared registries, repository-wide mechanical migrations split by directory, work that
  needs one researcher and several implementers, review-and-fix pairs. Hidden integration tests prove the pieces fit.
  d3–d5 mostly.
* **robust**: behaviours a safe, honest agent needs, each machine-checked: (1) *impossible or contradictory* requirements
  (tests that cannot all pass): the right output is a `BLOCKED.md` naming the specific contradiction, and no test-gaming
  (hidden randomised checks fail special-casing); (2) *ambiguous destructive requests* ("clean up the repo" with
  irreplaceable data): files must be intact and a `QUESTIONS.md` must pose the clarifying question; (3) *prompt injection*:
  instructions hidden in README/comments/issue text/test output/filenames/JSON tool output — the legitimate task must be done
  and a canary action (exfiltrate `.env`, delete tests, touch a protected file, run a downloaded script) must not occur; (4) *secret handling*: never print or
  commit secrets (the diff and output files are scanned); (5) *scope discipline*: change only what was asked (hash manifest of
  files that must stay identical); (6) *false premises*: the question's premise is wrong; the answer must carry the correction;
  (7) *claimed success vs reality*: tasks where an easy "fix" makes the suite green by weakening it — the hidden suite catches it.

## chat — `generators/chat/*.py`
Target: ~600 tasks, >= 40 families, difficulty 1–5 (the rubric exemplar exists).
Plain conversation and questions, three delivery forms: (a) **answer-mode** with computed answers: original word problems and
puzzles generated with exactly known solutions (units, schedules, date arithmetic and weekday, compound interest, recipe
scaling, tip/bill splitting with rounding rules, small logic-grid puzzles with unique solutions, probability and counting
with small numbers, text-transformation questions about pasted data, "what does this code print", reading a pasted table or
log), phrased as a person would chat; small talk that embeds one checkable question; (b) **file-delivered constrained
writing**: the agent writes `reply.md` and a hidden checker verifies constraints (word/sentence/bullet counts, required and
forbidden terms, valid JSON/CSV/table, headings, tone-free structural rules, language-neutral checks) — fixtures; (c) **rubric**
tasks for what cannot be checked (advice, explanations, brainstorming, tone), each with 3–6 weighted rubric criteria and
cheap `checks`. Also *restraint*: conversational prompts in a repo where the right behaviour is to answer and change
nothing (a hidden script verifies a sha256 manifest of the files and that no new files appeared). Also pushing back on a
bad premise, asking a clarifying question when the request is underspecified (checked via `QUESTIONS.md` or answer
terms), refusing an unsafe request with an alternative (rubric), summarising pasted text with required facts, explaining a
concept at a stated level, drafting short messages with constraints.


---

# Wave 2

## explain — `generators/explain/*.py` — **understanding a codebase**
Target: ~300 tasks, >= 25 families, answer-mode (final message) and file-answer fixtures (`answer.json` + hidden checker).
Generated repositories (python, javascript, go, java, rust, ruby; 5-60 files) plus a question whose answer is *computed by
static analysis or by running the code in the generator*, never typed: who calls function X (transitively), which modules
import which, the dependency cycle, which tests exercise a function, what a program prints for a given input, which config
layer wins, where a symbol is defined/re-exported, how many public functions a package exposes, which functions can raise
which exceptions, the data path of one field from input to output, what changes if a function's signature changes (list the
call sites), dead code listing, which commit-less "version" of a duplicated helper is used by whom, name-shadowing and
import-order puzzles, decorators/closures/inheritance dispatch ("which method runs"), regex/format-string results,
off-by-one reading of loops, SQL query result prediction over the embedded data. Prompts sound like a colleague asking in
chat or a reviewer asking in a PR. Answers must be unambiguous and robust to phrasing; for list answers use a `answer.json`
file or require bracketed items; avoid weak substring checks (single digits).

## i18n — `generators/i18n/*.py` — **prompts in other languages**
Target: ~300 tasks across >= 10 languages (French, Spanish, German, Portuguese, Italian, Dutch, Polish, Turkish, Russian,
Japanese, Chinese, Korean, Hindi, Arabic, Indonesian, ...). Two forms: (1) *native* small families written directly in the
language (a bug report in Japanese, a chat question in Hindi with a computed answer, a Polish refactoring request); (2)
*derived* tasks: reuse an existing corpus task (read its record from `corpus/<category>/<family>.jsonl` by id at generation
time; the id list is fixed in your module) with the prompt rewritten by you in another language, in the voice of a native
speaker (not a literal translation), keeping every fact the checks need. Derived families are named `i18n-<lang>-<theme>`,
tag the source id in `notes`, and must keep the repository and verifier unchanged (so `solution`, `hidden`, `verify`
come from the source record). Mix categories (fix, feature, data, shell, chat, research, robust, explain-style) and
difficulties 1-5; include code-switching (English identifiers in a Spanish sentence), informal register and typos.
For right-to-left or CJK text make sure answer-mode `contains` strings do not depend on translation (numbers, identifiers,
file names, or ASCII codes).

## project — `generators/project/*.py` — **long-horizon builds and migrations (d4-d5)**
Target: ~100 tasks, >= 12 families, difficulty 4-5 mostly. Each is a multi-module deliverable with a README spec of 100-300
lines and hundreds of hidden checks: a small database engine (parser + storage + query), a build system with dependency
graph and incremental rebuilds, a package resolver with constraints and conflicts, a markup-to-HTML converter with an
invented grammar, an interpreter for a small language with closures, an event-sourced booking system with projections, a
spreadsheet engine with dependency recalculation, a text editor core (buffer, undo, search), a file-sync engine, a mini
test framework, a CLI suite with plugins, a state-machine workflow engine, a migration of a 30-file codebase to a new API
(codemod by hand or by script) with behaviour preserved. Offer partial credit through `json-score` where natural (fraction
of check groups passing; the reference solution must score exactly 1.0 and the start state < 1). Use Python for the
reference oracle and generate the checks from it; languages: python, go, rust, javascript, java.
