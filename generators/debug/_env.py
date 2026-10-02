"""'Works on my machine': a test passes locally and fails in CI because of an environment difference.

Every variant is a tiny project whose code silently depends on something in the environment (default text encoding, time zone,
hash seed, case-insensitive file systems, the Python version, line endings, an exported variable, the working directory).  The
CI log is the real output of the failing run (the CI environment is reproduced with environment variables or the real Python
version); the two environment dumps list many differences, only one of which matters.
"""
from __future__ import annotations

import json
import random

from fx import Task, dd, run
from fx.run import merged

from ._engine import KINDS, accepted, hidden_diag

HOME_DUMP = [("HOSTNAME", "marta-laptop", "ci-runner-7f3a"), ("USER", "marta", "runner"), ("SHELL", "/bin/zsh", "/bin/bash"), ("EDITOR", "vim", "(unset)"),
             ("CPU_COUNT", "10", "2"), ("MEMORY_GB", "32", "7"), ("DOCKER", "no", "yes (job container)"), ("GIT_VERSION", "2.45.1", "2.39.5")]


def dump(local: dict, ci: dict) -> tuple[str, str]:
    a = {k: v for k, v, _ in HOME_DUMP}
    b = {k: w for k, _, w in HOME_DUMP}
    a.update(local)
    b.update(ci)
    fmt = lambda d, title: f"# {title}\n" + "".join(f"{k}={v}\n" for k, v in sorted(d.items()))
    return fmt(a, "environment of the developer laptop (where the tests pass)"), fmt(b, "environment of the CI job (where they fail)")


def _pick(pick: int, options: list):
    return options[pick % len(options)]


def _line_of(text: str, needle: str) -> int:
    for i, ln in enumerate(text.split("\n"), 1):
        if needle in ln:
            return i
    raise RuntimeError(needle)


# ---- variants ---------------------------------------------------------------------------------------------------------

def v_encoding(rng, pick=0):
    skin = _pick(pick, [
        dict(pkg="suppliers", mod="loader", fn="load_names", data="data/suppliers.csv", noun="supplier",
             rows=["id,name,city", "1,Müller & Söhne,Köln", "2,Ångström Tools,Malmö", "3,Café Étoile,Lyon", "4,Plain Co,Leeds"]),
        dict(pkg="roster", mod="people", fn="load_names", data="data/staff.csv", noun="staff",
             rows=["id,name,team", "1,Zoë Kowalczyk,Łódź", "2,Núria Vidal,Girona", "3,Jörg Brandt,Bremen", "4,Sam Lee,Leeds"]),
    ])
    code = dd(f'''
        """Loads the {skin["noun"]} list shipped with the repository."""
        import csv


        def {skin["fn"]}(path):
            """Names in file order."""
            with open(path, newline="") as fh:
                return [row["name"] for row in csv.DictReader(fh)]
    ''')
    names = [r.split(",")[1] for r in skin["rows"][1:]]
    test = dd(f'''
        import unittest

        from {skin["pkg"]}.{skin["mod"]} import {skin["fn"]}


        class LoaderTest(unittest.TestCase):
            def test_names(self):
                self.assertEqual({skin["fn"]}("{skin["data"]}"), {names!r})
    ''')
    files = {f"{skin['pkg']}/__init__.py": "", f"{skin['pkg']}/{skin['mod']}.py": code, skin["data"]: "\n".join(skin["rows"]) + "\n", "tests/__init__.py": "", "tests/test_loader.py": test,
             "README.md": f"# {skin['pkg']}\n\nShared {skin['noun']} list loader. Tests: `python3 -m unittest discover -s tests -t .`\n"}
    ci = "LC_ALL=C LANG=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=0 python3 -m unittest discover -s tests -t ."
    local = "LC_ALL=C.UTF-8 python3 -m unittest discover -s tests -t ."
    envs = dump({"LANG": "en_US.UTF-8", "LC_ALL": "(unset)", "PYTHONUTF8": "(unset)", "TZ": "Europe/Berlin"}, {"LANG": "C", "LC_ALL": "C", "PYTHONUTF8": "0", "TZ": "UTC", "PYTHONCOERCECLOCALE": "0"})
    return dict(files=files, ci=ci, local=local, envs=envs, file=f"{skin['pkg']}/{skin['mod']}.py", func=skin["fn"], code_line=_line_of(code, "open(path"),
                diff=["LANG", "LC_ALL", "locale", "encoding", "UTF8"], what="the file is opened with the platform's default encoding, which is ASCII under the C locale of the CI job",
                kw=["encoding", "utf-8", "locale", "open(", "default"], summary="Pass encoding='utf-8' to open(): the default encoding comes from the locale, which is C (ASCII) in CI.",
                title=f"the {skin['noun']} loader")


def v_timezone(rng, pick=0):
    skin = _pick(pick, [
        dict(pkg="dailystats", mod="buckets", fn="day_key", noun="daily statistics", base=1735689600, ts=1735689600 + 3600 * 23, want="2025-01-01"),
        dict(pkg="metering", mod="days", fn="day_key", noun="meter day roll-up", base=1741046400, ts=1741046400 + 3600 * 22, want="2025-03-04"),
    ])
    code = dd(f'''
        """Day buckets for the {skin["noun"]}: every reading belongs to the UTC calendar day of its timestamp."""
        from datetime import datetime


        def {skin["fn"]}(ts):
            """"YYYY-MM-DD" of the UTC day that contains the Unix timestamp `ts`."""
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    ''')
    test = dd(f'''
        import unittest

        from {skin["pkg"]}.{skin["mod"]} import {skin["fn"]}


        class DayKeyTest(unittest.TestCase):
            def test_late_evening_stays_on_its_day(self):
                self.assertEqual({skin["fn"]}({skin["ts"]}), "{skin["want"]}")

            def test_midnight(self):
                self.assertEqual({skin["fn"]}({skin["base"]}), "{skin["want"]}")
    ''')
    files = {f"{skin['pkg']}/__init__.py": "", f"{skin['pkg']}/{skin['mod']}.py": code, "tests/__init__.py": "", "tests/test_days.py": test,
             "README.md": f"# {skin['pkg']}\n\nDay bucketing for {skin['noun']}. Tests: `python3 -m unittest discover -s tests -t .`\n"}
    ci = "TZ=JST-9 python3 -m unittest discover -s tests -t ."
    local = "TZ=UTC python3 -m unittest discover -s tests -t ."
    envs = dump({"TZ": "UTC", "LANG": "en_GB.UTF-8"}, {"TZ": "Asia/Tokyo (JST-9)", "LANG": "C.UTF-8", "REGION": "ap-northeast-1"})
    return dict(files=files, ci=ci, local=local, envs=envs, file=f"{skin['pkg']}/{skin['mod']}.py", func=skin["fn"], code_line=_line_of(code, "fromtimestamp"),
                diff=["TZ", "timezone", "time zone"], what="datetime.fromtimestamp() converts to the machine's local time zone instead of UTC",
                kw=["timezone", "time zone", "utc", "tz", "local"], summary="Use datetime.fromtimestamp(ts, timezone.utc): fromtimestamp without a tz uses the local zone, which is Asia/Tokyo in CI.",
                title=f"the {skin['noun']}")


def v_hashseed(rng, pick=0):
    skin = _pick(pick, [
        dict(pkg="tagcloud", mod="render", fn="join_tags", noun="tag cloud", tags=["design", "ops", "billing"]),
        dict(pkg="labels", mod="merge", fn="join_labels", noun="label merger", tags=["urgent", "bug", "docs"]),
    ])
    code = dd(f'''
        """Builds the comma separated tag line shown on a card: every tag once, in alphabetical order."""


        def {skin["fn"]}(tags):
            """Unique tags, alphabetical, joined with commas."""
            return ",".join(set(tags))
    ''')
    want = ",".join(sorted(skin["tags"]))
    test = dd(f'''
        import unittest

        from {skin["pkg"]}.{skin["mod"]} import {skin["fn"]}


        class JoinTest(unittest.TestCase):
            def test_alphabetical_and_unique(self):
                tags = {skin["tags"] + skin["tags"][:2]!r}
                self.assertEqual({skin["fn"]}(tags), "{want}")
    ''')
    files = {f"{skin['pkg']}/__init__.py": "", f"{skin['pkg']}/{skin['mod']}.py": code, "tests/__init__.py": "", "tests/test_join.py": test,
             "README.md": f"# {skin['pkg']}\n\nTag line rendering for the {skin['noun']}. Tests: `python3 -m unittest discover -s tests -t .`\n"}
    seed = good_seed = None
    for s_ in range(0, 60):
        r = run(files, f"PYTHONHASHSEED={s_} python3 -m unittest discover -s tests -t . 2>&1", timeout=60)
        if r.ok and good_seed is None:
            good_seed = s_
        if not r.ok and seed is None:
            seed = s_
        if seed is not None and good_seed is not None:
            break
    if seed is None or good_seed is None:
        raise RuntimeError("no failing/passing hash seed")
    ci = f"PYTHONHASHSEED={seed} python3 -m unittest discover -s tests -t ."
    local = f"PYTHONHASHSEED={good_seed} python3 -m unittest discover -s tests -t ."
    envs = dump({"PYTHONHASHSEED": f"{good_seed} (exported by the team's .envrc)", "TZ": "Europe/Berlin"}, {"PYTHONHASHSEED": str(seed), "TZ": "UTC"})
    return dict(files=files, ci=ci, local=local, envs=envs, file=f"{skin['pkg']}/{skin['mod']}.py", func=skin["fn"], code_line=_line_of(code, "set(tags)"),
                diff=["PYTHONHASHSEED", "hash", "seed", "ordering", "set"], what="the iteration order of a set of strings depends on the hash seed, and the output is not sorted",
                kw=["sorted", "set", "order", "hash", "seed", "random"], summary="Sort the unique tags (sorted(set(tags))): set order of strings depends on PYTHONHASHSEED, which is fixed to 0 locally and different in CI.",
                title=f"the {skin['noun']}")


def v_case(rng, pick=0):
    skin = _pick(pick, [
        dict(pkg="mailer", mod="templates", fn="load_template", dir="templates", good="welcome.html", bad="Templates/Welcome.html", noun="welcome-mail templates"),
        dict(pkg="invoicer", mod="layouts", fn="load_layout", dir="layouts", good="invoice.tpl", bad="Layouts/Invoice.tpl", noun="invoice layouts"),
    ])
    code = dd(f'''
        """Loads the {skin["noun"]} that ship with the repository."""
        import os

        ROOT = os.path.dirname(os.path.abspath(__file__))


        def {skin["fn"]}():
            """The text of the default template."""
            with open(os.path.join(ROOT, "..", "{skin["bad"]}"), encoding="utf-8") as fh:
                return fh.read()
    ''')
    test = dd(f'''
        import unittest

        from {skin["pkg"]}.{skin["mod"]} import {skin["fn"]}


        class TemplateTest(unittest.TestCase):
            def test_default_template_has_placeholder(self):
                self.assertIn("{{{{name}}}}", {skin["fn"]}())
    ''')
    files = {f"{skin['pkg']}/__init__.py": "", f"{skin['pkg']}/{skin['mod']}.py": code, f"{skin['dir']}/{skin['good']}": "<p>Hello {{name}}, welcome aboard.</p>\n", "tests/__init__.py": "", "tests/test_templates.py": test,
             "README.md": f"# {skin['pkg']}\n\n{skin['noun'].capitalize()}. Tests: `python3 -m unittest discover -s tests -t .`\n"}
    ci = "python3 -m unittest discover -s tests -t ."
    local = None
    envs = dump({"OS": "macOS 14.5 (APFS volume, case-insensitive)", "FILESYSTEM": "apfs (case-insensitive, case-preserving)"}, {"OS": "Ubuntu 22.04 (container)", "FILESYSTEM": "overlayfs on ext4 (case-sensitive)"})
    return dict(files=files, ci=ci, local=local, envs=envs, file=f"{skin['pkg']}/{skin['mod']}.py", func=skin["fn"], code_line=_line_of(code, "open(os.path.join"),
                diff=["case", "filesystem", "file system", "macOS", "APFS", "case-sensitive"], what=f"the code opens {skin['bad']!r} but the file is {skin['dir']}/{skin['good']}: this only works on a case-insensitive file system",
                kw=["case", "file name", "filename", "path", "insensitive", "sensitive"], summary=f"Use the exact path {skin['dir']}/{skin['good']}: macOS is case-insensitive and hides the wrong capitalisation, Linux CI is case-sensitive.",
                title=f"the {skin['noun']} loader")


def v_pyversion(rng, pick=0):
    skin = _pick(pick, [
        dict(pkg="uploader", mod="chunks", fn="send_in_batches", noun="bulk uploader"),
        dict(pkg="notifier", mod="digest", fn="send_in_batches", noun="digest sender"),
    ])
    code = dd(f'''
        """Splits a list of items into batches before handing them to the {skin["noun"]}."""
        from itertools import batched


        def {skin["fn"]}(items, size, send):
            """Calls send(batch) for every batch of at most `size` items; returns the number of batches."""
            n = 0
            for batch in batched(items, size):
                send(list(batch))
                n += 1
            return n
    ''')
    test = dd(f'''
        import unittest

        from {skin["pkg"]}.{skin["mod"]} import {skin["fn"]}


        class BatchTest(unittest.TestCase):
            def test_batches(self):
                sent = []
                self.assertEqual({skin["fn"]}(list(range(7)), 3, sent.append), 3)
                self.assertEqual(sent, [[0, 1, 2], [3, 4, 5], [6]])
    ''')
    files = {f"{skin['pkg']}/__init__.py": "", f"{skin['pkg']}/{skin['mod']}.py": code, "tests/__init__.py": "", "tests/test_batches.py": test,
             "README.md": f"# {skin['pkg']}\n\nBatching for the {skin['noun']}. Needs Python 3.12. Tests: `python3 -m unittest discover -s tests -t .`\n"}
    ci = "python3 -m unittest discover -s tests -t ."
    envs = dump({"PYTHON": "3.12.4 (pyenv)", "PIP_VERSION": "24.0"}, {"PYTHON": "3.11 (the CI image's system interpreter)", "PIP_VERSION": "23.0.1"})
    return dict(files=files, ci=ci, local=None, envs=envs, file=f"{skin['pkg']}/{skin['mod']}.py", func=skin["fn"], code_line=_line_of(code, "from itertools import batched"),
                diff=["python", "version", "3.12", "3.11", "interpreter"], what="itertools.batched exists only from Python 3.12, and the CI image runs 3.11",
                kw=["batched", "3.12", "3.11", "version", "python"], summary="itertools.batched needs Python 3.12; CI has 3.11. Write the batching with slicing (or upgrade the CI interpreter).",
                title=f"the {skin['noun']}")


def v_crlf(rng, pick=0):
    skin = _pick(pick, [
        dict(pkg="ratecards", mod="parse", fn="active_total", data="data/rates.txt", noun="rate card",
             rows=["eu-west,12,active", "eu-east,7,retired", "us-east,20,active", "us-west,5,active"]),
        dict(pkg="licences", mod="parse", fn="active_total", data="data/seats.txt", noun="licence list",
             rows=["design,12,active", "legacy,7,retired", "analytics,20,active", "chat,5,active"]),
    ])
    code = dd(f'''
        """Totals for the {skin["noun"]}: one `name,amount,status` line per entry."""


        def {skin["fn"]}(path):
            """Sum of the amounts of all entries whose status is exactly "active"."""
            total = 0
            with open(path, newline="") as fh:
                for line in fh.read().split("\\n"):
                    if not line:
                        continue
                    name, amount, status = line.split(",")
                    if status == "active":
                        total += int(amount)
            return total
    ''')
    test = dd(f'''
        import unittest

        from {skin["pkg"]}.{skin["mod"]} import {skin["fn"]}


        class TotalTest(unittest.TestCase):
            def test_total(self):
                self.assertEqual({skin["fn"]}("{skin["data"]}"), 37)
    ''')
    files = {f"{skin['pkg']}/__init__.py": "", f"{skin['pkg']}/{skin['mod']}.py": code, skin["data"]: "\r\n".join(skin["rows"]) + "\r\n", "tests/__init__.py": "", "tests/test_total.py": test,
             "README.md": f"# {skin['pkg']}\n\nTotals for the {skin['noun']}. Tests: `python3 -m unittest discover -s tests -t .`\n"}
    ci = "python3 -m unittest discover -s tests -t ."
    envs = dump({"OS": "macOS 14.5", "GIT_AUTOCRLF": "input (checkout keeps LF)", "FILE_ENDINGS": "data files are LF in the working tree"},
                {"OS": "Ubuntu 22.04 (container)", "GIT_AUTOCRLF": "false (checkout keeps the committed bytes)", "FILE_ENDINGS": "data files are CRLF (committed from Windows)"})
    return dict(files=files, ci=ci, local=None, envs=envs, file=f"{skin['pkg']}/{skin['mod']}.py", func=skin["fn"], code_line=_line_of(code, 'status == "active"'),
                diff=["CRLF", "line ending", "autocrlf", "newline", "\\r"], what="the data file has CRLF line endings, so the last field is 'active\\r' and never equals 'active'; the parser only splits on LF",
                kw=["crlf", "\\r", "line ending", "strip", "newline", "splitlines"], summary="Parse with splitlines()/strip(): the data file is committed with CRLF line endings, so the last field carries a trailing '\\r'.",
                title=f"the {skin['noun']} totals")


def v_envvar(rng, pick=0):
    skin = _pick(pick, [
        dict(pkg="exporter", mod="paths", fn="export_path", var="EXPORT_DIR", noun="export job", value="$HOME/exports"),
        dict(pkg="archiver", mod="paths", fn="archive_path", var="ARCHIVE_ROOT", noun="archive job", value="$HOME/archive"),
    ])
    code = dd(f'''
        """Where the {skin["noun"]} writes its files."""
        import os


        def {skin["fn"]}(name):
            """Full path of the output file `name` below the directory given by ${skin["var"]}."""
            return os.path.join(os.environ["{skin["var"]}"], name)
    ''')
    test = dd(f'''
        import unittest

        from {skin["pkg"]}.{skin["mod"]} import {skin["fn"]}


        class PathTest(unittest.TestCase):
            def test_path_ends_with_name(self):
                self.assertTrue({skin["fn"]}("report.csv").endswith("report.csv"))
    ''')
    files = {f"{skin['pkg']}/__init__.py": "", f"{skin['pkg']}/{skin['mod']}.py": code, "tests/__init__.py": "", "tests/test_paths.py": test,
             "README.md": f"# {skin['pkg']}\n\nOutput paths for the {skin['noun']}. Tests: `python3 -m unittest discover -s tests -t .`\n"}
    ci = "env -u " + skin["var"] + " python3 -m unittest discover -s tests -t ."
    envs = dump({skin["var"]: skin["value"] + " (exported in ~/.zshrc)"}, {skin["var"]: "(unset)"})
    return dict(files=files, ci=ci, local=None, envs=envs, file=f"{skin['pkg']}/{skin['mod']}.py", func=skin["fn"], code_line=_line_of(code, "os.environ["),
                diff=[skin["var"], "environment variable", "env var", "unset", "exported"], what=f"the code requires the environment variable {skin['var']}, which the developer exports in a shell profile and the CI job does not set",
                kw=[skin["var"], "environment", "unset", "default", "keyerror", "getenv"], summary=f"{skin['var']} is exported locally but not set in CI; use a default or configure the variable for the job.",
                title=f"the {skin['noun']} paths")


def v_cwd(rng, pick=0):
    skin = _pick(pick, [
        dict(pkg="pricing", mod="table", fn="load_prices", data="data/prices.csv", noun="price table", rows=["sku,pence", "A100,1250", "B200,899", "C300,45"]),
        dict(pkg="gazetteer", mod="places", fn="load_places", data="data/places.csv", noun="place index", rows=["code,name", "ABD,Aberdeen", "BRS,Bristol", "LDS,Leeds"]),
    ])
    code = dd(f'''
        """Loads the {skin["noun"]} that ships with the repository."""
        import csv


        def {skin["fn"]}():
            """Mapping of the first column to the second."""
            with open("{skin["data"]}", newline="", encoding="utf-8") as fh:
                rows = list(csv.reader(fh))[1:]
            return {{r[0]: r[1] for r in rows}}
    ''')
    test = dd(f'''
        import unittest

        from {skin["pkg"]}.{skin["mod"]} import {skin["fn"]}


        class LoadTest(unittest.TestCase):
            def test_has_three_rows(self):
                self.assertEqual(len({skin["fn"]}()), 3)
    ''')
    files = {f"{skin['pkg']}/__init__.py": "", f"{skin['pkg']}/{skin['mod']}.py": code, skin["data"]: "\n".join(skin["rows"]) + "\n", "tests/__init__.py": "", "tests/test_load.py": test,
             "README.md": f"# {skin['pkg']}\n\nThe {skin['noun']}. Tests: from the repository root, `python3 -m unittest discover -s tests -t .`\n"}
    ci = "cd tests && python3 -m unittest discover -s . -t .."
    envs = dump({"RUN_FROM": "repository root (python3 -m unittest discover -s tests -t .)"}, {"RUN_FROM": "tests/ (the CI template does `cd tests` before running)"})
    return dict(files=files, ci=ci, local=None, envs=envs, file=f"{skin['pkg']}/{skin['mod']}.py", func=skin["fn"], code_line=_line_of(code, "open("),
                diff=["working directory", "cwd", "RUN_FROM", "relative path", "run from"], what=f"the data file is opened with a path relative to the current working directory ({skin['data']}), which differs between the laptop and CI",
                kw=["working directory", "cwd", "relative", "path", "__file__"], summary=f"Build the path from __file__ (the package location) instead of the current directory: CI runs the tests from tests/, so {skin['data']} is not found.",
                title=f"the {skin['noun']} loader")


VARIANTS = [("encoding", v_encoding), ("timezone", v_timezone), ("hashseed", v_hashseed), ("case", v_case), ("pyversion", v_pyversion), ("crlf", v_crlf),
            ("envvar", v_envvar), ("cwd", v_cwd)]
LEVEL = {"encoding": 3, "timezone": 3, "hashseed": 4, "case": 2, "pyversion": 2, "crlf": 4, "envvar": 2, "cwd": 3}


def env_task(rng: random.Random, i: int, name: str, fn, pick: int = 0) -> Task:
    v = fn(rng, pick)
    files = v["files"]
    r = run(files, v["ci"] + " 2>&1", timeout=60)
    if r.ok:
        raise RuntimeError(f"env variant {name}: the CI command passes")
    start = dict(files)
    start["ci.log"] = f"$ {v['ci']}\n" + r.out.strip() + "\n"
    if v["local"]:
        rl = run(files, v["local"] + " 2>&1", timeout=60)
        if not rl.ok:
            raise RuntimeError(f"env variant {name}: the local command fails: {rl.out[-400:]}")
        start["local.log"] = f"$ {v['local']}\n" + rl.out.strip() + "\n"
    else:
        start["local.log"] = "$ python3 -m unittest discover -s tests -t .\n..\n----------------------------------------------------------------------\nRan 1 test in 0.001s\n\nOK\n"
    start["env-local.txt"], start["env-ci.txt"] = v["envs"]
    ci_lines = start["ci.log"].strip().split("\n")
    path = v["file"]
    windows = [{"file": path, "start": v["code_line"], "end": v["code_line"]}, {"file": "ci.log", "start": 1, "end": len(ci_lines)}]
    schema = ("Write `diagnosis.json`: an object with exactly these keys: `root_cause_file` (the source file that has the hidden dependency), `function` (the function in it), "
              "`difference` (the environment difference that makes it fail: name the variable, setting or tool), `kind` (one of " + ", ".join(KINDS) + "), "
              "`evidence_lines` (a list of `path:line` strings: the dependent code and the telling log lines) and `fix_summary` (one or two sentences).")
    voices = [
        f"The tests for {v['title']} pass on my laptop and fail in CI. The CI output is in `ci.log`, my local run in `local.log`, and `env-local.txt` / `env-ci.txt` list the two environments (a lot of the differences are irrelevant). Find out why. {schema}",
        f"works on my machine: CI is red for {v['title']} (`ci.log`), green locally (`local.log`). Both environments are described in `env-local.txt` and `env-ci.txt`. Diagnose it, don't just retry the job. {schema}",
        f"I keep rerunning the CI job and it keeps failing, while the same commit passes for me. Logs and environment dumps are in the repo root (`ci.log`, `local.log`, `env-*.txt`). What is the real cause? {schema}",
        f"Please look at the failing CI job of {v['title']}. I know the two environments differ in many ways (see `env-local.txt`, `env-ci.txt`); I need to know which difference matters and where the code depends on it. {schema}",
    ]
    prompt = rng.choice(voices)
    spec = {"answer_file": "diagnosis.json", "fields": {
        "root_cause_file": {"type": "path", "accept": [path]},
        "function": {"type": "name", "accept": [v["func"]]},
        "difference": {"type": "string_in", "accept": v["diff"]},
        "kind": {"type": "enum", "allowed": KINDS, "accept": accepted("environment") + ["config-error"]},
        "evidence_lines": {"type": "evidence", "windows": windows, "slack": 1},
        "fix_summary": {"type": "text", "min_len": 20, "any": v["kw"]},
    }}
    gold = {"root_cause_file": path, "function": v["func"], "difference": v["diff"][0], "kind": "environment", "evidence_lines": [f"{path}:{v['code_line']}", f"ci.log:{len(ci_lines)}"],
            "fix_summary": v["summary"]}
    return Task(
        slug=f"{i:02d}-{name}", prompt=prompt, difficulty=LEVEL[name], kind="fix", lang="python", start=start, hidden=hidden_diag(spec),
        solution={"diagnosis.json": json.dumps(gold, indent=1) + "\n"}, verify="python3 _verify/check.py", pass_mode="json-score", protected=sorted(start),
        timeout_s=60, tags=["works-on-my-machine", name], notes={"variant": name, "what": v["what"]},
    )


def env_family(rng: random.Random, n: int):
    i = 0
    plan = [name for name, _ in VARIANTS] * 3
    fns = dict(VARIANTS)
    for k in range(n):
        name = plan[k % len(plan)]
        yield env_task(rng, k + 1, name, fns[name], k // len(VARIANTS))
