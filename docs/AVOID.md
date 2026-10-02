# What not to build tasks from

The corpus exists to train Sleipnir; Sleipnir is also *measured* on benchmarks and on its own bench suite. Anything
that resembles those items would inflate the measurement. Tasks must therefore be original, and `tools/contam.py`
scans every task against the real benchmark texts (n-gram overlap) and against this list.

## 1. Sleipnir's own bench (`Sleipnir/bench/`) — never reuse

Fixtures: `go-jsonpath` (JSONPath subset), `go-lru` (LRU cache), `go-ratelimit` (rate limiter / token bucket),
`go-wordfreq` (word frequency), `greenfield-go-mdlite` (mini Markdown), `greenfield-js-csvtool` (CSV tool),
`greenfield-py-todoapi` (TODO REST API), `java-eventbus` (event bus), `java-matrix` (matrix arithmetic), `js-csv` (CSV
parser), `js-eventemitter` (event emitter), `js-slugify` (slugify), `py-ini` (INI parser), `py-intervals` (interval
merging), `py-roman` (Roman numerals), `rs-bitset` (bit set), `rs-rpn` (RPN calculator).
Also: the Go standard-library copies ("std-mini") that the mutation tasks use, and the Sleipnir source and git history
(the mined and recall tasks come from it). Do not use any of these subjects, and never clone, vendor or mutate the Go
standard library or Sleipnir.

## 2. Public benchmarks and exercise sets — never reuse or lightly rephrase

HumanEval / HumanEval+ / HumanEval-X, MBPP / MBPP+, APPS, CodeContests, LiveCodeBench, LeetCode/Codeforces/AtCoder
style puzzles, SWE-bench (all variants), SWE-smith, Multi-SWE, Aider polyglot (Exercism), Exercism exercises in
general, Terminal-Bench, BigCodeBench, ClassEval, DS-1000, CRUXEval, RepoBench, CodeXGLUE, Defects4J, BugsInPy,
QuixBugs, ManyBugs, Spider/BIRD (text-to-SQL), IFEval, MMLU/GSM8K/MATH style questions, GAIA, tau-bench, WebArena,
AgentBench, SWE-Lancer.

Avoid the **subjects** these use as bare puzzles: FizzBuzz, two-sum, palindromes, anagrams, Fibonacci, primes/sieve,
Roman numerals, run-length encoding (plain), bracket matching (plain), Luhn / ISBN validators, leap years, word count,
bank account, bowling score, pig latin, rot13/Caesar/atbash/rail-fence, Pascal's triangle, spiral matrix, matrix
transpose, Collatz, perfect numbers, pangram, isogram, nucleotide count/RNA transcription/protein translation, Hamming
distance, grade school roster, scrabble score, queen attack, robot simulator, tournament table, minesweeper annotate,
connect (hex game), game of life (plain Conway), zebra puzzle, two-bucket, knapsack (plain), N-queens, sudoku solver,
LRU cache, trie, union-find, Dijkstra on a bare graph, etc.

The Exercism slugs, for reference (do not build tasks that are these exercises): acronym, affine-cipher, all-your-base,
allergies, alphametics, anagram, armstrong-numbers, atbash-cipher, bank-account, beer-song, binary-search, bob, bowling,
change, circular-buffer, clock, collatz-conjecture, complex-numbers, connect, crypto-square, custom-set, darts, diamond,
difference-of-squares, diffie-hellman, dnd-character, dominoes, etl, flatten-array, food-chain, forth, gigasecond,
go-counting, grade-school, grains, grep, hamming, hangman, hello-world, high-scores, house, isbn-verifier, isogram,
kindergarten-garden, knapsack, largest-series-product, leap, list-ops, luhn, markdown, matching-brackets, matrix,
meetup, minesweeper, nth-prime, nucleotide-count, ocr-numbers, palindrome-products, pangram, pascals-triangle,
perfect-numbers, phone-number, pig-latin, poker, prime-factors, protein-translation, proverb, pythagorean-triplet,
queen-attack, rail-fence-cipher, raindrops, rational-numbers, react, rectangles, resistor-color, rest-api,
reverse-string, rna-transcription, robot-simulator, roman-numerals, rotational-cipher, run-length-encoding,
saddle-points, satellite, say, scrabble-score, secret-handshake, series, sgf-parsing, sieve, simple-linked-list,
sublist, space-age, spiral-matrix, sum-of-multiples, tournament, transpose, triangle, twelve-days, two-bucket, two-fer,
variable-length-quantity, word-count, wordy, yacht, zebra-puzzle, zipper.

## 3. Real repositories and issues

Do not copy code, tests, issues or commit messages from open-source projects, and do not "recreate" a known bug from
one. Do not mine GitHub. Everything here is authored.

## 4. What to do instead

Pick a *specific, slightly unusual domain* and invent its rules: the pricing quirks of a ferry timetable, a lab
sample-tracking label format, a tabletop-game initiative tracker with house rules, a tide-aware dock scheduler, a
podcast-chapter file format, a fictional unit system, a stamp-duty calculator for an invented jurisdiction. A task is
yours when someone who knows every benchmark could not recognise it. Games are welcome but with original rules and
APIs (not a plain Tic-Tac-Toe or plain Conway).
