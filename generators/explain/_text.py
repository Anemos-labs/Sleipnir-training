"""Text-normalisation pipelines (strip, case, regex substitution, zero padding, truncation) rendered in python, javascript, ruby and go.

Only RE2-compatible regex syntax is used (no look-around, no backreferences inside patterns), so every language agrees. The
generator runs all four renderings and keeps a pipeline only when they print identical output; the answer is that output."""
from __future__ import annotations

import random
from dataclasses import dataclass

import fx

from . import _ir as I

SEPS = ["-", "_", ".", "/"]


@dataclass
class Step:
    kind: str
    a: str = ""
    b: str = ""
    n: int = 0


def make_steps(rng: random.Random, tier: int) -> list:
    k = {1: 2, 2: 3, 3: 4, 4: 5, 5: 7}[tier]
    pool = ["upper", "lower", "collapse", "zeros", "padnum", "trunc", "swap", "vowels", "mask", "prefix"]
    wanted: list = []
    if tier >= 2:
        wanted.append("collapse")
    if tier >= 3:
        wanted.append(rng.choice(["zeros", "swap"]))
    if tier >= 4:
        wanted.append(rng.choice(["padnum", "trunc"]))
    rest = [x for x in pool if x not in wanted]
    rng.shuffle(rest)
    while len(wanted) < k - 1:
        wanted.append(rest.pop())
    order = {"upper": 0, "lower": 0, "collapse": 1, "zeros": 2, "swap": 3, "padnum": 4, "vowels": 5, "mask": 5, "trunc": 6, "prefix": 7}
    wanted.sort(key=lambda x: order[x])
    if "upper" in wanted and "lower" in wanted:
        wanted.remove("lower")
    if "swap" in wanted and "zeros" in wanted and rng.random() < 0.5:
        wanted.remove("swap")
    steps = [Step("strip")]
    for w in wanted:
        if w == "collapse":
            steps.append(Step("collapse", b=rng.choice(["-", "_", "."])))
        elif w == "padnum":
            steps.append(Step("padnum", n=rng.randint(3, 5)))
        elif w == "trunc":
            steps.append(Step("trunc", n=rng.randint(6, 10)))
        elif w == "prefix":
            steps.append(Step("prefix", a=rng.choice(["ID-", "X", "N:", "HM_"])))
        else:
            steps.append(Step(w))
    return steps


def inputs(rng: random.Random, n: int) -> list:
    dom = rng.choice(I.DOMAINS)
    out = []
    for _ in range(n):
        pre = rng.choice([w[:rng.randint(2, 4)] for w in dom.nouns])
        pre = pre.upper() if rng.random() < 0.5 else (pre.capitalize() if rng.random() < 0.5 else pre.lower())
        sep = rng.choice([" ", "-", "_", ".", "--", " - ", "/"])
        num = rng.randint(1, 4000)
        digits = str(num).zfill(rng.choice([1, 3, 4, 5]))
        tail = rng.choice(["", "", rng.choice(["a", "B", "x2", "Q7", "ab"]), ""])
        s = f"{pre}{sep}{digits}{(' ' + tail) if tail and rng.random() < 0.5 else tail}"
        s = (" " * rng.choice([0, 0, 1, 2])) + s + (" " * rng.choice([0, 0, 1, 3]))
        out.append(s)
    return out


# ---------------------------------------------------------------------------------------------------------------- python reference
def apply_py(steps: list, s: str) -> str:
    import re
    for st in steps:
        if st.kind == "strip":
            s = s.strip()
        elif st.kind == "upper":
            s = s.upper()
        elif st.kind == "lower":
            s = s.lower()
        elif st.kind == "collapse":
            s = re.sub(r"[^A-Za-z0-9]+", st.b, s)
        elif st.kind == "zeros":
            s = re.sub(r"^([A-Za-z]+)[-_.]?0*(\d+)", r"\1-\2", s)
        elif st.kind == "padnum":
            s = re.sub(r"(\d+)$", lambda m: m.group(1).zfill(st.n), s)
        elif st.kind == "trunc":
            s = s[: st.n]
        elif st.kind == "swap":
            s = re.sub(r"^([A-Za-z]+)[-_.](\d+)$", r"\2-\1", s)
        elif st.kind == "vowels":
            s = re.sub(r"[AEIOUaeiou]", "", s)
        elif st.kind == "mask":
            s = re.sub(r"\d", "#", s)
        elif st.kind == "prefix":
            s = s if s.startswith(st.a) else st.a + s
    return s


def _py(steps, name):
    lines = ['"""Normalises raw item codes."""', "import re", "import sys", "", ""]
    lines += ["def clean(raw):", '    """Return the canonical form of a raw code."""', "    s = raw"]
    for st in steps:
        if st.kind == "strip":
            lines.append("    s = s.strip()")
        elif st.kind == "upper":
            lines.append("    s = s.upper()")
        elif st.kind == "lower":
            lines.append("    s = s.lower()")
        elif st.kind == "collapse":
            lines.append(f'    s = re.sub(r"[^A-Za-z0-9]+", "{st.b}", s)')
        elif st.kind == "zeros":
            lines.append('    s = re.sub(r"^([A-Za-z]+)[-_.]?0*(\\d+)", r"\\1-\\2", s)')
        elif st.kind == "padnum":
            lines.append(f'    s = re.sub(r"(\\d+)$", lambda m: m.group(1).zfill({st.n}), s)')
        elif st.kind == "trunc":
            lines.append(f"    s = s[:{st.n}]")
        elif st.kind == "swap":
            lines.append('    s = re.sub(r"^([A-Za-z]+)[-_.](\\d+)$", r"\\2-\\1", s)')
        elif st.kind == "vowels":
            lines.append('    s = re.sub(r"[AEIOUaeiou]", "", s)')
        elif st.kind == "mask":
            lines.append('    s = re.sub(r"\\d", "#", s)')
        elif st.kind == "prefix":
            lines.append(f'    if not s.startswith("{st.a}"):')
            lines.append(f'        s = "{st.a}" + s')
    lines += ["    return s", "", "", 'def main(path="data/inputs.txt"):', '    with open(path) as handle:', "        for i, line in enumerate(handle.read().splitlines()):", '            print(f"{i}: [{clean(line)}]")', "", "", 'if __name__ == "__main__":', "    main()"]
    return {"codes.py": "\n".join(lines) + "\n"}, "python3 codes.py"


def _js(steps, name):
    lines = ["'use strict';", "", "const fs = require('fs');", "", "/** Return the canonical form of a raw code. */", "function clean(raw) {", "  let s = raw;"]
    for st in steps:
        if st.kind == "strip":
            lines.append("  s = s.trim();")
        elif st.kind == "upper":
            lines.append("  s = s.toUpperCase();")
        elif st.kind == "lower":
            lines.append("  s = s.toLowerCase();")
        elif st.kind == "collapse":
            lines.append(f"  s = s.replace(/[^A-Za-z0-9]+/g, '{st.b}');")
        elif st.kind == "zeros":
            lines.append("  s = s.replace(/^([A-Za-z]+)[-_.]?0*(\\d+)/, '$1-$2');")
        elif st.kind == "padnum":
            lines.append(f"  s = s.replace(/(\\d+)$/, (m, g) => g.padStart({st.n}, '0'));")
        elif st.kind == "trunc":
            lines.append(f"  s = s.slice(0, {st.n});")
        elif st.kind == "swap":
            lines.append("  s = s.replace(/^([A-Za-z]+)[-_.](\\d+)$/, '$2-$1');")
        elif st.kind == "vowels":
            lines.append("  s = s.replace(/[AEIOUaeiou]/g, '');")
        elif st.kind == "mask":
            lines.append("  s = s.replace(/\\d/g, '#');")
        elif st.kind == "prefix":
            lines.append(f"  if (!s.startsWith('{st.a}')) {{")
            lines.append(f"    s = '{st.a}' + s;")
            lines.append("  }")
    lines += ["  return s;", "}", "", "const text = fs.readFileSync('data/inputs.txt', 'utf8');", "const rows = text.split('\\n');", "if (rows[rows.length - 1] === '') {", "  rows.pop();", "}",
              "rows.forEach((line, i) => {", "  console.log(`${i}: [${clean(line)}]`);", "});"]
    return {"codes.js": "\n".join(lines) + "\n"}, "node codes.js"


def _rb(steps, name):
    lines = ["# frozen_string_literal: true", "", "# Return the canonical form of a raw code.", "def clean(raw)", "  s = raw.dup"]
    for st in steps:
        if st.kind == "strip":
            lines.append("  s = s.strip")
        elif st.kind == "upper":
            lines.append("  s = s.upcase")
        elif st.kind == "lower":
            lines.append("  s = s.downcase")
        elif st.kind == "collapse":
            lines.append(f"  s = s.gsub(/[^A-Za-z0-9]+/, '{st.b}')")
        elif st.kind == "zeros":
            lines.append("  s = s.sub(/\\A([A-Za-z]+)[-_.]?0*(\\d+)/, '\\1-\\2')")
        elif st.kind == "padnum":
            lines.append(f"  s = s.sub(/(\\d+)\\z/) {{ Regexp.last_match(1).rjust({st.n}, '0') }}")
        elif st.kind == "trunc":
            lines.append(f"  s = s[0, {st.n}]")
        elif st.kind == "swap":
            lines.append("  s = s.sub(/\\A([A-Za-z]+)[-_.](\\d+)\\z/, '\\2-\\1')")
        elif st.kind == "vowels":
            lines.append("  s = s.gsub(/[AEIOUaeiou]/, '')")
        elif st.kind == "mask":
            lines.append("  s = s.gsub(/\\d/, '#')")
        elif st.kind == "prefix":
            lines.append(f"  s = '{st.a}' + s unless s.start_with?('{st.a}')")
    lines += ["  s", "end", "", "File.readlines('data/inputs.txt', chomp: true).each_with_index do |line, i|", "  puts \"#{i}: [#{clean(line)}]\"", "end"]
    return {"codes.rb": "\n".join(lines) + "\n"}, "ruby codes.rb"


def _go(steps, name):
    uses_strings = True
    lines = ["package main", "", "import (", '\t"bufio"', '\t"fmt"', '\t"os"', '\t"regexp"', '\t"strings"', ")", ""]
    pats = []
    body = []
    for st in steps:
        if st.kind == "strip":
            body.append("\ts = strings.TrimSpace(s)")
        elif st.kind == "upper":
            body.append("\ts = strings.ToUpper(s)")
        elif st.kind == "lower":
            body.append("\ts = strings.ToLower(s)")
        elif st.kind == "collapse":
            body.append(f'\ts = regexp.MustCompile(`[^A-Za-z0-9]+`).ReplaceAllString(s, "{st.b}")')
        elif st.kind == "zeros":
            body.append('\ts = regexp.MustCompile(`^([A-Za-z]+)[-_.]?0*(\\d+)`).ReplaceAllString(s, "${1}-${2}")')
        elif st.kind == "padnum":
            body.append(f"\ts = regexp.MustCompile(`\\d+$`).ReplaceAllStringFunc(s, func(m string) string {{")
            body.append(f"\t\tif len(m) >= {st.n} {{")
            body.append("\t\t\treturn m")
            body.append("\t\t}")
            body.append(f'\t\treturn strings.Repeat("0", {st.n}-len(m)) + m')
            body.append("\t})")
        elif st.kind == "trunc":
            body.append(f"\tif len(s) > {st.n} {{")
            body.append(f"\t\ts = s[:{st.n}]")
            body.append("\t}")
        elif st.kind == "swap":
            body.append('\ts = regexp.MustCompile(`^([A-Za-z]+)[-_.](\\d+)$`).ReplaceAllString(s, "${2}-${1}")')
        elif st.kind == "vowels":
            body.append('\ts = regexp.MustCompile(`[AEIOUaeiou]`).ReplaceAllString(s, "")')
        elif st.kind == "mask":
            body.append('\ts = regexp.MustCompile(`\\d`).ReplaceAllString(s, "#")')
        elif st.kind == "prefix":
            body.append(f'\tif !strings.HasPrefix(s, "{st.a}") {{')
            body.append(f'\t\ts = "{st.a}" + s')
            body.append("\t}")
    lines += ["// clean returns the canonical form of a raw code.", "func clean(raw string) string {", "\ts := raw"] + body + ["\treturn s", "}", "",
              "func main() {", '\tfile, err := os.Open("data/inputs.txt")', "\tif err != nil {", "\t\tpanic(err)", "\t}", "\tdefer file.Close()", "\tscanner := bufio.NewScanner(file)", "\ti := 0",
              "\tfor scanner.Scan() {", '\t\tfmt.Printf("%d: [%s]\\n", i, clean(scanner.Text()))', "\t\ti++", "\t}", "}"]
    return {"go.mod": f"module example.com/{name}\n\ngo 1.21\n", "main.go": "\n".join(lines) + "\n"}, "go run ."


RENDER = {"python": _py, "javascript": _js, "ruby": _rb, "go": _go}


def build(rng: random.Random, lang: str, tier: int, n_inputs: int, n_extra: int = 3):
    """(files, outputs per input line, run command, steps, extra inputs with their outputs); all four renderings must agree"""
    for _ in range(25):
        steps = make_steps(rng, tier)
        ins = inputs(rng, n_inputs)
        extra = [x.strip() for x in inputs(rng, n_extra)]
        all_ins = ins + extra
        # inputs must survive the lines/readlines round trip
        text = "\n".join(all_ins) + "\n"
        expect = [apply_py(steps, s) for s in all_ins]
        outs = {}
        ok = True
        for lg in ("python", "javascript", "ruby", "go"):
            code, cmd = RENDER[lg](steps, "codes")
            files = {**code, "data/inputs.txt": text}
            res = fx.run(files, cmd + " 2>&1", timeout=60)
            lines = res.out.split("\n")
            if lines and lines[-1] == "":
                lines.pop()
            if not res.ok or len(lines) != len(all_ins):
                ok = False
                break
            outs[lg] = lines
        if not ok:
            continue
        ref = [f"{i}: [{e}]" for i, e in enumerate(expect)]
        if any(outs[lg] != ref for lg in outs):
            continue
        code, cmd = RENDER[lang](steps, "codes")
        text_file = "\n".join(ins) + "\n"
        files = {**code, "data/inputs.txt": text_file, "README.md": "# Code cleaner\n\n`clean()` turns the raw item codes in `data/inputs.txt` into their canonical form; running the script prints one bracketed result per input line.\n"}
        return files, ins, expect[: len(ins)], cmd, steps, list(zip(extra, expect[len(ins):]))
    raise RuntimeError("text pipeline: no agreeing pipeline")
