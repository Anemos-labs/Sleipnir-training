# Contamination scan

8457 tasks scanned: **8341 clean**, 116 warnings, 0 failures.

Reference texts that were in the index (a source that could not be downloaded is not covered):

| source | files fetched | rows |
|---|---|---|
| apps | 1/1 | 2000 |
| bigcodebench | 1/1 | 1140 |
| classeval | 1/1 | 100 |
| cruxeval | 1/1 | 800 |
| exercism | 61/107 | 61 |
| gsm8k | 2/2 | 8792 |
| humaneval | 1/1 | 164 |
| humanevalplus | 1/1 | 164 |
| ifeval | 1/1 | 541 |
| livecodebench | 1/1 | 200 |
| mbpp | 4/4 | 974 |
| mmlu | 1/1 | 14042 |
| sleipnir-bench-and-source | -/- | 17 |
| spider | 2/2 | 8034 |
| swebench | 3/3 | 3019 |

Method: see `tools/contam.py` (8-word prompt shingles, 12-token code shingles with boilerplate removed, rare
benchmark identifiers, avoid-listed subjects). This is evidence of non-overlap with those texts, not proof
that no task resembles some benchmark we did not index.

## Flagged families

| family | flagged tasks |
|---|---|
| fix-py-airlane | 10 |
| fix-py-billnum | 10 |
| fix-py-ferryzones | 10 |
| fix-py-fxdesk | 10 |
| fix-py-gardenstats | 10 |
| fix-py-identcase | 10 |
| fix-py-latbuckets | 10 |
| fix-py-layaway | 10 |
| fix-py-powerbill | 10 |
| fix-py-undotrail | 10 |
| fix-js-cursorpage | 8 |
| security-javascript | 4 |
| fix-hand-date-ranges | 1 |
| games-cinder-replay | 1 |
| optimize-py-algorithms | 1 |
| security-go | 1 |
