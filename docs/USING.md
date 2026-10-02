# Using the corpus with Sleipnir

## 1. Get ready-to-run tasks

The committed form is the generators plus the corpus shards (`corpus/<category>/<family>.jsonl`, one self-contained task per
line: prompt, start/hidden/solution files, verifier). Sleipnir wants a `tasks.jsonl` whose tasks point at git repositories
and whose hidden files and reference solutions sit in a blob store. `make dist` builds that with Sleipnir's own
materialiser and proves every task again on your machine:

```sh
(cd ../Sleipnir && go build -o ~/.cache/fx/sleipnir ./cmd/sleipnir)     # or set SLEIPNIR=/path/to/sleipnir
make dist CONC=4          # -> dist/tasks.jsonl, dist/blobs/, dist/repos/, plus dist/tasks.{train,val,test}.jsonl
```

`dist/` is a build output (git-ignored). Run Sleipnir **from `dist/`**: the tasks name their repositories relative to it.

## 2. Roll out

```sh
cd dist
sleipnir rl tasks stats tasks.train.jsonl
sleipnir rl rollout --tasks tasks.train.jsonl --blobs blobs --group 8 --concurrency 16 \
    --model my-policy --base-url http://vllm:8000/v1 --capture --out runs/r001
sleipnir rl export runs/r001 --format steps --out export/r001.steps.jsonl
```

Useful selections: `--id 'fix-go-*'` (path.Match wildcards), `-n 200` (deterministic subset), `--mode single` to run swarm
tasks as one agent (the baseline a swarm is compared with). Tasks carry their own budgets (steps, requests, wall-clock,
`context_window` for the memory tasks); `--max-steps`, `--budget-usd` etc. only fill in what a task leaves open.

## 3. Splits

Tasks cut from one family share a library, a world or a skeleton; a per-task random split leaks. `tools/split.py` assigns
whole families to train/val/test (stratified by category, default 90/5/5, seeded) and writes `catalog/splits.json`; `make
dist` writes `dist/tasks.<part>.jsonl`. Evaluate with `sleipnir rl eval --tasks dist/tasks.test.jsonl --exclude
dist/tasks.train.jsonl ...`.

## 4. What the three modes mean for rewards

* **fixture**: the verifier runs in a clean checkout with the agent's diff (minus protected paths) applied and the hidden files
  written. Exit 0 is a pass; `json-score` tasks print `{"score": x}` and pass at 1.0, giving partial credit in the
  reward's `outcome` component.
* **answer**: the final message must contain every expected string (`verifier.expect`); some also run a verifier command on
  the workspace (restraint and secret-handling tasks).
* **rubric**: not part of `dist/` (Sleipnir has no judge in the loop). `catalog/index.jsonl` lists them with their rubric and
  the cheap deterministic checks; `tools/score_rubric.py TASK_ID --message FILE` applies the checks.

## 5. Adding tasks

See `docs/AUTHORING.md`. In short: write a family under `generators/<category>/`, `make build`, `make admit`, `make scan`,
`make catalog`. A task enters the catalog only with an `ok` admission verdict and without a contamination failure.

## 6. Keeping the measurement honest

Do not train on `Sleipnir/bench` or on a benchmark you intend to report. `tools/contam.py scan` re-checks the corpus
against the benchmark texts it can download (`tools/contam.py fetch` builds the index once) and the report in
`catalog/CONTAMINATION.md` says which sources were covered. Run it again whenever tasks are added or you add a benchmark
to your evaluation set: put its texts into `tools/contam.py`'s `SOURCES` first.
