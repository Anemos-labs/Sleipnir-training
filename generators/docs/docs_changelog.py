"""Release notes from a commit list (python-checked): the CHANGELOG entry follows an invented house format that is spelled out in CONTRIBUTING.md."""
from __future__ import annotations

import datetime
import json
import re

from fx import Task, dd, family

from ._kit import prove_docs

CMD = "python3 -m unittest discover -s tests -v"

LIB = r'''import re

TYPE_SECTION = {"feat": "Features", "fix": "Fixes", "perf": "Performance", "docs": "Documentation"}
ORDER = ["Breaking changes", "Features", "Fixes", "Performance", "Documentation"]
SUBJECT_RE = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]*)\))?(?P<bang>!)?: (?P<desc>.*)$")


def parse_commits(text):
    """Commits in the order they appear in the file (newest first)."""
    commits = []
    for block in re.split(r"^commit ", text, flags=re.M)[1:]:
        lines = block.split("\n")
        sha = lines[0].strip()
        date = next(ln.split(":", 1)[1].strip() for ln in lines if ln.startswith("Date:"))
        body = [ln[4:] if ln.startswith("    ") else ln for ln in lines if ln.startswith("    ")]
        subject = body[0].strip()
        footer = ""
        for ln in body[1:]:
            if ln.startswith("BREAKING CHANGE:"):
                footer = ln.split(":", 1)[1].strip()
        m = SUBJECT_RE.match(subject)
        commits.append({"sha": sha, "date": date, "subject": subject, "type": m.group("type"), "scope": m.group("scope") or "",
                        "desc": m.group("desc"), "breaking": bool(m.group("bang")) or bool(footer), "migration": footer})
    return commits


def bump(version, commits):
    major, minor, patch = (int(x) for x in version.split("."))
    if any(c["breaking"] for c in commits):
        return "%d.0.0" % (major + 1)
    if any(c["type"] == "feat" for c in commits):
        return "%d.%d.0" % (major, minor + 1)
    return "%d.%d.%d" % (major, minor, patch + 1)


def live(commits):
    """Drop reverted commits and the reverts themselves."""
    reverted = set()
    out = []
    chrono = list(reversed(commits))
    for c in chrono:
        if c["type"] == "revert":
            target = c["desc"]
            for prev in out:
                if prev["subject"] == target and prev["sha"] not in reverted:
                    reverted.add(prev["sha"])
                    break
        else:
            out.append(c)
    return [c for c in out if c["sha"] not in reverted]


ISSUE_RE = re.compile(r"\s*\(#(\d+)\)")


def item_text(c):
    desc = c["desc"]
    issue = ISSUE_RE.search(desc)
    desc = ISSUE_RE.sub("", desc).strip().rstrip(".")
    text = (c["scope"] + ": " if c["scope"] else "") + desc
    if issue:
        text += " (#%s)" % issue.group(1)
    return text


def entry(commits, previous):
    kept = live(commits)
    version = bump(previous, kept)
    date = max(c["date"] for c in commits)
    sections = {name: [] for name in ORDER}
    for c in kept:
        if c["breaking"]:
            lines = ["- " + item_text(c)]
            if c["migration"]:
                lines.append("  Migration: " + c["migration"])
            sections["Breaking changes"].append(lines)
        elif c["type"] in TYPE_SECTION:
            sections[TYPE_SECTION[c["type"]]].append(["- " + item_text(c)])
    out = ["## [%s] - %s" % (version, date), ""]
    for name in ORDER:
        if sections[name]:
            out.append("### " + name)
            for lines in sections[name]:
                out.extend(lines)
            out.append("")
    return version, out
'''

SPEC = dd('''
    # Contributing: release notes

    `CHANGELOG.md` has one entry per release, newest first, followed by the link list. When a release is cut, whoever
    cuts it writes the entry from the commits since the last release (`commits.txt` holds them, newest first).

    1. The entry starts with `## [VERSION] - DATE`. DATE is the date of the newest commit. VERSION is the version of the
       latest entry in `CHANGELOG.md`, bumped: major if any commit is breaking (a `!` after the type or scope, or a
       `BREAKING CHANGE:` line in the body), otherwise minor if any commit is a `feat`, otherwise patch. Lower numbers
       reset to 0.
    2. Sections come in this order and are left out when empty: `### Breaking changes`, `### Features`, `### Fixes`,
       `### Performance`, `### Documentation`.
    3. Types: `feat` -> Features, `fix` -> Fixes, `perf` -> Performance, `docs` -> Documentation. A breaking commit is
       listed only under Breaking changes, whatever its type. Commits of any other type (`chore`, `ci`, `test`, `style`,
       `refactor`, `build`) are not listed.
    4. A `revert: <subject>` commit cancels the earlier commit whose full subject equals `<subject>`: neither of them
       is listed.
    5. An item reads `- scope: description` (just `- description` without a scope). The description is the commit
       subject after `type(scope): `, without a trailing period; an issue reference `(#N)` anywhere in it is moved to the
       end as ` (#N)`.
    6. Items within a section are ordered by commit date, oldest first (commits with the same date keep the order of
       their appearance in the file, oldest first, which is bottom to top).
    7. A breaking item that has a `BREAKING CHANGE:` line gets a second line, indented by two spaces:
       `  Migration: <text after BREAKING CHANGE:>`.
    8. Add `[VERSION]: https://git.example/compare/vPREVIOUS...vVERSION` as the first line of the link list at the end of
       the file.
    9. Older entries stay exactly as they are.
''')

SCOPES = ["parser", "cli", "export", "api", "ui", "db", "sync", "tides"]
FEATS = ["add harmonic overtides to the predictor", "export tables as ical", "support half-hourly rows", "add a --station flag", "cache constituent files",
         "show moon phase in the header", "accept feet as an input unit", "add dark theme", "support multiple time zones", "batch import of gauge readings"]
FIXES = ["handle a leap day in the table header", "stop crashing on empty station files", "round heights half up", "fix off-by-one in the last row", "keep the sort order stable",
         "escape commas in station names", "use UTC for the cache key", "fix flaky reconnect to the gauge", "clamp negative depths to zero", "report the right line number in errors"]
PERFS = ["speed up table rendering", "avoid re-reading the constituent file", "use a prefix sum for daily ranges", "stream large exports"]
DOCS = ["explain the cache directory", "add a quick start", "document exit codes", "fix typos in the install guide"]
OTHERS = [("chore", "bump dependencies"), ("ci", "run tests on 3.12"), ("test", "cover leap years"), ("refactor", "split the renderer"), ("style", "format with black"), ("build", "pin the toolchain")]


def make_commits(rng, k, with_revert, breaking):
    kinds = []
    kinds += [("feat", rng.choice(FEATS)) for _ in range(rng.randrange(1, 4))]
    kinds += [("fix", rng.choice(FIXES)) for _ in range(rng.randrange(1, 4))]
    if rng.random() < 0.6:
        kinds.append(("perf", rng.choice(PERFS)))
    if rng.random() < 0.6:
        kinds.append(("docs", rng.choice(DOCS)))
    kinds += [rng.choice(OTHERS) for _ in range(rng.randrange(1, 4))]
    rng.shuffle(kinds)
    kinds = kinds[:k] if len(kinds) > k else kinds
    day = datetime.date(2026, 2, 3) + datetime.timedelta(days=rng.randrange(0, 20))
    commits = []
    for kind, desc in kinds:
        scope = rng.choice(SCOPES) if rng.random() < 0.7 else ""
        issue = rng.randrange(20, 400) if rng.random() < 0.6 else None
        d = desc[0].lower() + desc[1:]
        if issue:
            d = d + " (#%d)" % issue if rng.random() < 0.6 else d.replace(" ", " (#%d) " % issue, 1)
        if rng.random() < 0.2:
            d += "."
        commits.append({"type": kind, "scope": scope, "desc": d, "bang": False, "footer": ""})
    if breaking:
        c = rng.choice([c for c in commits if c["type"] in ("feat", "fix", "refactor", "perf")] or commits)
        c["bang"] = True
        if rng.random() < 0.7:
            c["footer"] = rng.choice(["the config key `tz` is now `timezone`", "rows are now one per half hour", "the --legacy flag is gone", "exports use UTC instead of local time"])
    chrono = []
    for c in commits:
        day += datetime.timedelta(days=rng.choice([0, 0, 1, 2]))
        chrono.append({**c, "date": day.isoformat()})
    if with_revert:
        target = rng.choice([c for c in chrono if c["type"] in ("feat", "fix") and not c["bang"]] or chrono)
        day += datetime.timedelta(days=1)
        subj = subject(target)
        chrono.append({"type": "revert", "scope": "", "desc": subj, "bang": False, "footer": "", "date": day.isoformat()})
    return chrono


def subject(c):
    return f"{c['type']}{('(' + c['scope'] + ')') if c['scope'] else ''}{'!' if c['bang'] else ''}: {c['desc']}"


def render(chrono):
    out = []
    for n, c in enumerate(reversed(chrono)):
        sha = "%07x" % (0x3f2a9c1 + 7919 * n)
        out.append(f"commit {sha}\nDate: {c['date']}\n\n    {subject(c)}\n")
        if c["footer"]:
            out[-1] += f"\n    BREAKING CHANGE: {c['footer']}\n"
    return "\n".join(out)


def old_changelog(rng, version):
    major, minor, patch = (int(x) for x in version.split("."))
    entries = []
    prev = None
    versions = [f"{major}.{minor}.{patch}"]
    if minor > 0:
        versions.append(f"{major}.{minor - 1}.0")
    versions.append(f"{major}.{max(0, minor - 2)}.0" if minor > 1 else f"{max(major - 1, 0)}.9.0")
    text = "# Changelog\n\nAll notable changes to tidebook are documented here. The format is described in CONTRIBUTING.md.\n\n"
    links = []
    for j, v in enumerate(versions):
        when = datetime.date(2026, 1, 20) - datetime.timedelta(days=23 * j)
        text += f"## [{v}] - {when.isoformat()}\n\n### Fixes\n- cli: tidy the help text (#{10 + j})\n\n"
        nxt = versions[j + 1] if j + 1 < len(versions) else None
        links.append(f"[{v}]: https://git.example/compare/v{nxt}...v{v}" if nxt else f"[{v}]: https://git.example/releases/tag/v{v}")
    return text + "\n".join(links) + "\n"


def solution_changelog(old, commits_text):
    ns = {}
    exec(LIB, ns)
    commits = ns["parse_commits"](commits_text)
    m = re.search(r"^## \[(\d+\.\d+\.\d+)\]", old, re.M)
    prev = m.group(1)
    version, lines = ns["entry"](commits, prev)
    block = "\n".join(lines).rstrip("\n") + "\n\n"
    first = old.index("## [")
    head, rest = old[:first], old[first:]
    link_at = rest.index("[" + prev + "]:")
    # the link list starts at the first line that begins with "[x.y.z]:"
    mm = re.search(r"^\[\d+\.\d+\.\d+\]: ", rest, re.M)
    body, links = rest[: mm.start()], rest[mm.start():]
    new_link = f"[{version}]: https://git.example/compare/v{prev}...v{version}\n"
    return head + block + body + new_link + links, version, prev


PROMPTS = [
    "We are cutting the next release of tidebook. Write the new entry at the top of `CHANGELOG.md` from the unreleased commits in `commits.txt`, following the rules in `CONTRIBUTING.md` "
    "(version bump, sections, ordering, reverts, link list). Leave the older entries alone.",
    "release prep: update CHANGELOG.md for the commits in commits.txt. CONTRIBUTING.md has the format (version number, date, section order, which commit types count, how reverts and breaking changes are written, the compare link). "
    "Don't touch the existing entries.",
    "Can you draft the changelog entry for the unreleased commits? The conventions are in `CONTRIBUTING.md`; the commits are listed newest first in `commits.txt`. I need the right version number, the right date, "
    "the right items in the right sections, and the new compare link at the top of the link list.",
]


@family("docs-changelog", category="docs", lang="text", kind="feature", n=6,
        summary="write a CHANGELOG entry from a conventional-commit list following a stated format (bump, sections, reverts, breaking migration lines, links)")
def gen(rng, n):
    for i in range(n):
        k = rng.choice([5, 6, 8, 10])
        with_revert = i % 3 == 2 or rng.random() < 0.2
        breaking = i % 2 == 1 or rng.random() < 0.2
        version = f"{rng.choice([1, 2, 3])}.{rng.randrange(2, 9)}.{rng.randrange(0, 5)}"
        chrono = make_commits(rng, k, with_revert, breaking)
        commits_text = render(chrono)
        old = old_changelog(rng, version)
        sol, new_version, prev = solution_changelog(old, commits_text)
        start = {"CHANGELOG.md": old, "commits.txt": commits_text, "CONTRIBUTING.md": SPEC, "README.md": "# tidebook\n\nTide tables from the command line. Releases are documented in CHANGELOG.md.\n"}
        test = dd(f'''
        import re
        import unittest

        LIB = {LIB!r}
        ORIGINAL = {old!r}
        COMMITS = {commits_text!r}


        def norm(lines):
            return [ln.rstrip() for ln in lines if ln.strip()]


        class ChangelogTests(unittest.TestCase):
            def setUp(self):
                ns = {{}}
                exec(LIB, ns)
                self.commits = ns["parse_commits"](COMMITS)
                prev = re.search(r"^## \\[(\\d+\\.\\d+\\.\\d+)\\]", ORIGINAL, re.M).group(1)
                self.prev = prev
                self.version, self.expected = ns["entry"](self.commits, prev)
                self.text = open("CHANGELOG.md", encoding="utf-8").read()

            def split(self, text):
                first = text.index("## [")
                link = re.search(r"^\\[\\d+\\.\\d+\\.\\d+\\]: ", text, re.M)
                entries = re.split(r"(?m)^(?=## \\[)", text[first:link.start()])
                return text[:first], [e for e in entries if e.strip()], text[link.start():]

            def test_new_entry_matches_the_rules(self):
                head, entries, links = self.split(self.text)
                self.assertEqual(norm(entries[0].split("\\n")), norm(self.expected), "the newest entry is wrong")

            def test_older_entries_are_untouched(self):
                head, entries, links = self.split(self.text)
                _, old_entries, old_links = self.split(ORIGINAL)
                self.assertEqual([norm(e.split("\\n")) for e in entries[1:]], [norm(e.split("\\n")) for e in old_entries])
                self.assertEqual(norm(head.split("\\n")), norm(self.split(ORIGINAL)[0].split("\\n")))

            def test_link_list(self):
                head, entries, links = self.split(self.text)
                lines = norm(links.split("\\n"))
                want_first = "[%s]: https://git.example/compare/v%s...v%s" % (self.version, self.prev, self.version)
                self.assertEqual(lines[0], want_first)
                _, _, old_links = self.split(ORIGINAL)
                self.assertEqual(lines[1:], norm(old_links.split("\\n")))
        ''')
        hidden = {"tests/test_changelog.py": test}
        solution = {"CHANGELOG.md": sol}
        prove_docs(f"changelog-{i}", start, hidden, solution, CMD)
        listed = sum(1 for ln in sol.split("\n")[:60] if ln.startswith("- "))
        d = 2 if (not with_revert and not breaking) else 3 if not (with_revert and breaking) else 4
        yield Task(slug=f"{i + 1:02d}-{new_version.replace('.', '-')}-{'revert-' if with_revert else ''}{'breaking' if breaking else 'plain'}", prompt=rng.choice(PROMPTS),
                   difficulty=d, start=start, hidden=hidden, solution=solution, verify=CMD, tags=["changelog", "conventional-commits", "release-notes"],
                   notes={"commits": len(chrono), "revert": with_revert, "breaking": breaking, "version": new_version})
