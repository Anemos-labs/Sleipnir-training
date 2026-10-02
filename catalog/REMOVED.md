# Removed from the corpus

| family | tasks | reason |
|---|---|---|
| `fix-go-pathglob` | 8 | A Go glob-matching library whose code shared about 7% of its 12-token windows with Sleipnir's own glob implementation (`internal/rl/env/glob.go`) and mirrored its 64-alternative limit. Sleipnir's source is part of what Sleipnir is measured on (its mined and recall bench tasks), so the family was deleted rather than kept with a warning. |

Anything else flagged by `tools/contam.py` is a warning only (shared idioms, generic identifiers); see `CONTAMINATION.md`.

## Removed for topical overlap with Sleipnir's own bench

A subject that Sleipnir's bench fixtures cover (`docs/AVOID.md` §1) is not used, even in another language or with a different interface:

| what | tasks | overlaps with |
|---|---|---|
| `shell-ini-tools` (get/set/list values in INI files with sed/awk) | 11 | `py-ini` (INI parser) |
| `shell-csv-tools` (CSV pipelines in shell) | 11 | `js-csv`, `greenfield-js-csvtool` |
| `shell-awk-algorithms`: `rpn-line-calculator` and `quoted-csv-records-to-tsv` instances | 2 | `rs-rpn`, `js-csv` |
