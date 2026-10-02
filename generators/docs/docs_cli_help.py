"""argparse --help (python): every subcommand and argument documented per a stated style (help text, metavars, defaults, epilog); behaviour unchanged."""
from __future__ import annotations

import json

from fx import Task, dd, family, merged, run

from ._kit import prove_docs

CMD = "python3 -m unittest discover -s tests -v"

# arg: dict(flags, type, default, choices, nargs, required, action, help, metavar)
TOOLS = [
    dict(key="seedctl", pkg="seedctl", summary="Manage the community seed bank from the command line.", cmds=[
        dict(name="add", help="receive packets of a seed lot", desc="Add packets of one SKU to the stock.", args=[
            dict(flags=["sku"], help="the SKU, for example VEG-0042"), dict(flags=["qty"], type="int", help="number of packets received"),
            dict(flags=["--note"], default="", help="free text stored with the lot", metavar="TEXT")]),
        dict(name="remove", help="take packets out of the stock", desc="Remove packets of one SKU from the stock.", args=[
            dict(flags=["sku"], help="the SKU to take from"), dict(flags=["qty"], type="int", help="number of packets to remove"),
            dict(flags=["--force"], action="store_true", help="remove even if the lot is reserved")]),
        dict(name="report", help="list SKUs that are running low", desc="Print the SKUs below a stock threshold.", args=[
            dict(flags=["--threshold"], type="int", default=5, help="SKUs with fewer packets than this are listed", metavar="N"),
            dict(flags=["--format"], choices=["text", "csv"], default="text", help="output format")]),
    ], examples=["seedctl add VEG-0042 12 --note spring", "seedctl report --threshold 8 --format csv"]),
    dict(key="ferrytool", pkg="ferrytool", summary="Timetable utilities for the island ferry.", cmds=[
        dict(name="next", help="show the next departure", desc="Find the next sailing after a given time.", args=[
            dict(flags=["time"], help="current time as HH:MM"), dict(flags=["--lead"], type="int", default=10, help="minutes needed to reach the quay", metavar="MINUTES")]),
        dict(name="convert", help="minutes to clock time", desc="Convert minutes after midnight to HH:MM.", args=[
            dict(flags=["minutes"], type="int", help="minutes after midnight"), dict(flags=["--width"], type="int", default=2, help="digits used for the hour", metavar="N")]),
        dict(name="roster", help="check a crew roster file", desc="Validate a crew roster file.", args=[
            dict(flags=["file"], help="path of the roster file"), dict(flags=["--shift"], choices=["early", "late"], help="only check this shift"),
            dict(flags=["--strict"], action="store_true", help="treat warnings as errors")]),
    ], examples=["ferrytool next 07:45 --lead 15", "ferrytool convert 465"]),
    dict(key="tidecalc", pkg="tidecalc", summary="Small calculations for the tide laboratory.", cmds=[
        dict(name="convert", help="convert a length", desc="Convert a length to metres.", args=[
            dict(flags=["value"], type="float", help="the length to convert"), dict(flags=["unit"], choices=["m", "cm", "ft"], help="unit of the value"),
            dict(flags=["--precision"], type="int", default=3, help="digits after the decimal point", metavar="N")]),
        dict(name="stats", help="summary statistics", desc="Print statistics for a list of readings.", args=[
            dict(flags=["values"], type="float", nargs="+", help="the readings to summarise"), dict(flags=["--percentile"], type="int", default=50, help="percentile to report", metavar="P")]),
        dict(name="bucket", help="count readings per bucket", desc="Count readings in buckets.", args=[
            dict(flags=["values"], type="float", nargs="+", help="the readings to count"),
            dict(flags=["--edges"], type="float", nargs="+", required=True, help="ascending bucket boundaries", metavar="EDGE")]),
    ], examples=["tidecalc convert 10 ft --precision 2", "tidecalc stats 1.5 2.5 9 --percentile 90"]),
    dict(key="dutycalc", pkg="dutycalc", summary="Stamp duty helper for the registry office.", cmds=[
        dict(name="calc", help="compute the duty on a price", desc="Compute the duty for a property price.", args=[
            dict(flags=["price"], type="int", help="the price in whole currency units"), dict(flags=["--relief"], choices=["none", "first_home", "heritage"], default="none", help="relief to apply"),
            dict(flags=["--round-to"], type="int", default=1, help="round the duty to a multiple of this", metavar="STEP")]),
        dict(name="split", help="split an amount in shares", desc="Split an amount of cents into equal shares.", args=[
            dict(flags=["cents"], type="int", help="the amount to split, in cents"), dict(flags=["parts"], type="int", help="number of shares")]),
        dict(name="fmt", help="format cents as an amount", desc="Format an amount of cents as text.", args=[
            dict(flags=["cents"], type="int", help="the amount in cents"), dict(flags=["--symbol"], default="", help="currency symbol put in front", metavar="SYM")]),
    ], examples=["dutycalc calc 250000 --relief heritage", "dutycalc split 1000 3"]),
]


def arg_code(a, with_help, rules, rng_keep):
    parts = [repr(f) for f in a["flags"]]
    kw = []
    if "type" in a:
        kw.append(f"type={a['type']}")
    if a.get("action"):
        kw.append(f"action={a['action']!r}")
    if "default" in a:
        kw.append(f"default={a['default']!r}")
    if a.get("choices"):
        kw.append(f"choices={a['choices']!r}")
    if a.get("nargs"):
        kw.append(f"nargs={a['nargs']!r}")
    if a.get("required"):
        kw.append("required=True")
    if with_help:
        if rules["metavar"] and a.get("metavar") and not a.get("choices"):
            kw.append(f"metavar={a['metavar']!r}")
        text = a["help"]
        if rules["defaults"] and a.get("default") not in (None, "", False) and a["flags"][0].startswith("-") and not a.get("action"):
            text += " (default: %(default)s)"
        kw.append(f"help={text!r}")
    return "p.add_argument(" + ", ".join(parts + kw) + ")"


def source(tool, with_help, rules, keep_help=None):
    keep_help = keep_help or set()
    lines = [f'"""{tool["summary"]}"""', "import argparse", "import json", "", "", "def build_parser():"]
    epi = ""
    if with_help and rules["epilog"]:
        ex = "\\n".join("  " + e for e in tool["examples"])
        epi = f", epilog=\"examples:\\n{ex}\", formatter_class=argparse.RawDescriptionHelpFormatter"
    desc = f", description={tool['summary']!r}" if with_help else ""
    lines.append(f'    parser = argparse.ArgumentParser(prog="{tool["key"]}"{desc}{epi})')
    lines.append('    sub = parser.add_subparsers(dest="command", required=True)')
    for c in tool["cmds"]:
        extra = f", help={c['help']!r}, description={c['desc']!r}" if with_help else ""
        lines.append(f'    p = sub.add_parser("{c["name"]}"{extra})')
        for a in c["args"]:
            use = with_help or (c["name"], a["flags"][0]) in keep_help
            lines.append("    " + arg_code(a, use, rules if with_help else {"metavar": False, "defaults": False}, None))
        lines.append("    p.set_defaults(handler=handle)")
    lines += ["    return parser", "", "", "def handle(args):",
              '    shown = {k: v for k, v in sorted(vars(args).items()) if k not in ("handler", "command")}',
              '    print(args.command + ": " + json.dumps(shown))', "    return 0", "", "", "def main(argv=None):",
              "    args = build_parser().parse_args(argv)", "    return args.handler(args)", "", "", 'if __name__ == "__main__":', "    raise SystemExit(main())", ""]
    return "\n".join(lines)


def argv_cases(tool):
    out = []
    for c in tool["cmds"]:
        pos = [a for a in c["args"] if not a["flags"][0].startswith("-")]
        base = [c["name"]]
        for a in pos:
            ty = a.get("type")
            v = {"int": "7", "float": "2.5"}.get(ty, "x")
            if a.get("choices"):
                v = a["choices"][0]
            base += [v] * (2 if a.get("nargs") else 1)
        req = [a for a in c["args"] if a.get("required")]
        for a in req:
            base += [a["flags"][0], "1", "2"]
        out.append(base)
        for a in c["args"]:
            if a["flags"][0].startswith("-") and not a.get("required"):
                if a.get("action"):
                    out.append(base + [a["flags"][0]])
                elif a.get("choices"):
                    out.append(base + [a["flags"][0], a["choices"][-1]])
                else:
                    out.append(base + [a["flags"][0], "3"])
        out.append(c["name"].split() + ["--bogus"])
        out.append(base[:1])
    out.append([])
    out.append(["nonsense"])
    return out


HARNESS = '''import contextlib, importlib, io, json, sys
sys.path.insert(0, ".")
cli = importlib.import_module("PKG.cli")

def outcome(argv):
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return {"code": code, "stdout": out.getvalue()}
'''

STYLE_TEXT = {
    "base": "* Every subcommand has `help=` (the line in the command list) and `description=` (the text at the top of its own help).\n* Every argument and option has a `help=` text of at least three words.",
    "metavar": "* Options that take a value (and have no fixed list of `choices`) have an upper-case `metavar`, such as `N` or `TEXT`, so the usage line does not show the lower-case internal name.",
    "defaults": "* If an option has a default other than empty/false, its help says what it is (`%(default)s` does that).",
    "epilog": "* The main parser has an `epilog` with at least two example command lines, each on its own line starting with the program name.",
}

PROMPTS = [
    "`{prog} --help` and the help of its subcommands are nearly empty: no descriptions, no help for the arguments. Follow `HELP-STYLE.md` and document the whole command line in "
    "`{pkg}/cli.py`. Behaviour (parsing and output) must not change; the help is checked by walking the parser.",
    "Please finish the help texts of the `{prog}` tool. `HELP-STYLE.md` lists what every subcommand and option needs. Only the argparse declarations may change (the actual behaviour has to stay identical).",
    "ticket: \"{prog} --help is useless\". Make the help complete following HELP-STYLE.md (subcommand descriptions, argument help{extra_words}). Do not change how arguments are parsed or what the commands print.",
]


@family("docs-cli-help", category="docs", lang="python", kind="feature", n=8,
        summary="complete argparse help (descriptions, per-argument help, metavars, shown defaults, epilog) by walking the parser; parsing behaviour must not change")
def gen(rng, n):
    tools = list(TOOLS) * 2
    rng.shuffle(tools)
    for i in range(n):
        tool = tools[i]
        rules = {"metavar": rng.random() < 0.7, "defaults": rng.random() < 0.7, "epilog": rng.random() < 0.6}
        keep = {(c["name"], a["flags"][0]) for c in tool["cmds"] for a in c["args"] if rng.random() < 0.25}
        start_src = source(tool, False, rules, keep)
        sol_src = source(tool, True, rules)
        pkg = tool["pkg"]
        path = f"{pkg}/cli.py"
        cases = argv_cases(tool)
        harness = HARNESS.replace("PKG", pkg)
        script = harness + f"\nCASES = {json.dumps(cases)}\nprint(json.dumps([outcome(c) for c in CASES]))\n"
        files = {path: start_src, f"{pkg}/__init__.py": ""}
        r = run(merged(files, {"_golden.py": script}), "python3 _golden.py", timeout=60)
        if not r.ok:
            raise RuntimeError("golden failed:\n" + r.out[-1500:])
        want = json.loads(r.out.strip().splitlines()[-1])
        rules_text = [STYLE_TEXT["base"]] + [STYLE_TEXT[k] for k in ("metavar", "defaults", "epilog") if rules[k]]
        style = "# Help style\n\nThe command line interface is documented through argparse itself:\n\n" + "\n".join(rules_text) + "\n"
        vis_idx = [j for j, w in enumerate(want) if w["code"] == 0][:2]
        vis = (HARNESS.replace("PKG", pkg) + "\n\nimport unittest\n\n\nclass BehaviourTests(unittest.TestCase):\n"
               + "".join(f"    def test_example_{k + 1}(self):\n        self.assertEqual(outcome({cases[j]!r}), {want[j]!r})\n\n" for k, j in enumerate(vis_idx))
               + "\nif __name__ == '__main__':\n    unittest.main()\n")
        start = {**files, "HELP-STYLE.md": style, "tests/test_behaviour.py": vis}
        test = dd(f'''
        import argparse
        import importlib
        import unittest

        import docscheck as D

        RULES = {rules!r}
        PKG = {json.dumps(pkg)}
        ''') + "\n" + HARNESS.replace("PKG", pkg).replace("cli = importlib.import_module(\"" + pkg + ".cli\")", "cli = importlib.import_module(PKG + \".cli\")") + dd(f'''
        CASES = {json.dumps(cases)}
        WANT = {json.dumps(want)}


        def subparsers(parser):
            for action in parser._actions:
                if isinstance(action, argparse._SubParsersAction):
                    return action
            raise AssertionError("no subcommands")


        class HelpTests(unittest.TestCase):
            def test_behaviour_is_unchanged(self):
                for argv, want in zip(CASES, WANT):
                    self.assertEqual(outcome(argv), want, argv)

            def test_every_subcommand_is_described(self):
                parser = cli.build_parser()
                sub = subparsers(parser)
                listed = {{a.dest: (a.help or "") for a in sub._choices_actions}}
                for name, p in sub.choices.items():
                    self.assertTrue(listed.get(name, "").strip(), "subcommand %s has no help= for the command list" % name)
                    self.assertTrue((p.description or "").strip(), "subcommand %s has no description" % name)
                    self.assertTrue(p.format_help())

            def test_every_argument_has_help(self):
                parser = cli.build_parser()
                for name, p in subparsers(parser).choices.items():
                    for a in p._actions:
                        if isinstance(a, argparse._HelpAction):
                            continue
                        text = a.help if a.help not in (None, argparse.SUPPRESS) else ""
                        self.assertGreaterEqual(D.words(text), 3, "%s: %s needs a help text of at least three words" % (name, a.dest))

            def test_value_options_have_metavars(self):
                if not RULES["metavar"]:
                    self.skipTest("not required")
                parser = cli.build_parser()
                for name, p in subparsers(parser).choices.items():
                    for a in p._actions:
                        if a.option_strings and a.nargs != 0 and not a.choices and not isinstance(a, argparse._HelpAction):
                            self.assertTrue(a.metavar and str(a.metavar).isupper(), "%s: option %s needs an upper-case metavar" % (name, a.option_strings[0]))

            def test_defaults_are_shown(self):
                if not RULES["defaults"]:
                    self.skipTest("not required")
                parser = cli.build_parser()
                for name, p in subparsers(parser).choices.items():
                    text = p.format_help()
                    for a in p._actions:
                        if a.option_strings and a.default not in (None, "", False, argparse.SUPPRESS) and not isinstance(a, argparse._HelpAction):
                            self.assertIn(str(a.default), text, "%s: the default of %s is not mentioned in the help" % (name, a.option_strings[0]))

            def test_epilog_has_examples(self):
                if not RULES["epilog"]:
                    self.skipTest("not required")
                parser = cli.build_parser()
                epilog = parser.epilog or ""
                lines = [ln for ln in epilog.split("\\n") if ln.strip().startswith(parser.prog + " ")]
                self.assertGreaterEqual(len(lines), 2, "the main parser's epilog needs two example command lines")
                self.assertTrue(parser.format_help())
        ''')
        hidden = {"tests/docscheck.py": DOCSCHECK_MIN, "tests/test_cli_help.py": test}
        solution = {path: sol_src}
        prove_docs(f"{tool['key']}-{i}", start, hidden, solution, CMD, "python3 -m unittest discover -s tests -p 'test_beh*.py'")
        extra_words = ", metavars" * rules["metavar"] + ", shown defaults" * rules["defaults"] + ", an epilog with examples" * rules["epilog"]
        prompt = rng.choice(PROMPTS).format(prog=tool["key"], pkg=pkg, extra_words=extra_words)
        d = 1 + sum(rules.values()) // 2 + (1 if len(tool["cmds"]) >= 3 else 0)
        yield Task(slug=f"{i + 1:02d}-{tool['key']}-{sum(rules.values())}rules", prompt=prompt, difficulty=min(d, 3), start=start, hidden=hidden, solution=solution, verify=CMD,
                   tags=["argparse", "cli", "help-text"], notes={"tool": tool["key"], "rules": rules})


DOCSCHECK_MIN = '''import re


def words(text):
    return len(re.findall(r"[A-Za-z0-9]+", text))
'''
