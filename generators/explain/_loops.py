"""Loop-reading puzzles (chunking, sliding windows, strides, inclusive bounds, reverse scans, early exit, nested pair search) over a data file,
rendered in python, javascript, go and ruby. All four renderings must print the same lines; the answer is that output."""
from __future__ import annotations

import random

import fx

LANGS = ["python", "javascript", "go", "ruby"]


def make_params(rng: random.Random, tier: int) -> list:
    n = {1: 8, 2: 10, 3: 12, 4: 15, 5: 18}[tier]
    names = {1: ["chunks", "strided", "diffs"], 2: ["chunks", "windows", "strided", "inclusive", "diffs"], 3: ["windows", "until", "reverse", "inclusive", "chunks"],
             4: ["windows", "pairs", "until", "reverse", "strided", "inclusive"], 5: ["windows", "pairs", "until", "reverse", "chunks", "inclusive"]}[tier]
    k = {1: 1, 2: 1, 3: 2, 4: 2, 5: 3}[tier]
    chosen = rng.sample(names, k)
    items = [rng.randint(1, 60) for _ in range(n)]
    tpls = []
    for nm in chosen:
        if nm == "chunks":
            tpls.append(("chunks", {"size": rng.choice([2, 3, 4, 5])}))
        elif nm == "windows":
            off = rng.choice([0, 1])
            tpls.append(("windows", {"size": rng.choice([2, 3, 4]), "off": off, "offs": " + 1" if off else "", "offg": "+1" if off else ""}))
        elif nm == "strided":
            tpls.append(("strided", {"start": rng.choice([0, 1, 2]), "step": rng.choice([2, 3])}))
        elif nm == "diffs":
            tpls.append(("diffs", {}))
        elif nm == "reverse":
            tpls.append(("reverse", {"skip": rng.choice([0, 1, 2])}))
        elif nm == "until":
            tpls.append(("until", {"limit": rng.randint(sum(items) // 4, sum(items) // 2)}))
        elif nm == "pairs":
            i, j = rng.sample(range(n), 2)
            tpls.append(("pairs", {"target": items[i] + items[j]}))
        else:
            lo = rng.randint(0, 3)
            tpls.append(("inclusive", {"lo": lo, "hi": rng.randint(lo + 2, n - 1)}))
    return items, tpls


# ---------------------------------------------------------------------------------------------------------------- renderers
def _py(tpls):
    out = []
    for k, (nm, p) in enumerate(tpls):
        t = {
            "chunks": ["    size = {size}", "    for i in range(0, len(items), size):", '        print(f"batch {{i // size}}: {{sum(items[i:i + size])}}")'],
            "windows": ["    size = {size}", "    for i in range(len(items) - size{offs}):", '        print(f"window {{i}}: {{max(items[i:i + size])}}")'],
            "strided": ["    for i in range({start}, len(items), {step}):", '        print(f"item {{i}}: {{items[i]}}")'],
            "diffs": ["    for i in range(1, len(items)):", "        delta = items[i] - items[i - 1]", "        if delta > 0:", '            print(f"rise {{i}}: {{delta}}")'],
            "reverse": ["    for i in range(len(items) - 1, {skip} - 1, -1):", "        if items[i] % 2 == 0:", '            print(f"{{i}}={{items[i]}}")'],
            "until": ["    total = 0", "    i = 0", "    while i < len(items) and total + items[i] <= {limit}:", "        total += items[i]", "        i += 1", '    print(f"stopped at {{i}} total {{total}}")'],
            "pairs": ["    found = 0", "    for i in range(len(items)):", "        for j in range(i + 1, len(items)):", "            if items[i] + items[j] == {target}:", '                print(f"pair {{i}},{{j}}")', "                found += 1", '    print(f"pairs: {{found}}")'],
            "inclusive": ["    running = 0", "    for i in range({lo}, {hi} + 1):", "        running += items[i]", '        print(f"step {{i}}: {{running}}")'],
        }[nm]
        out += [ln.format(**p) for ln in t]
    code = ['"""Reads the sensor readings and prints a few summaries."""', "", "", "def report(items):"] + out + ["", "", 'if __name__ == "__main__":', '    with open("data/readings.txt") as handle:', "        report([int(x) for x in handle.read().split()])"]
    return {"report.py": "\n".join(code) + "\n"}, "python3 report.py"


def _js(tpls):
    out = []
    for nm, p in tpls:
        t = {
            "chunks": ["  const size = {size};", "  for (let i = 0; i < items.length; i += size) {{", "    const part = items.slice(i, i + size);", "    console.log(`batch ${{Math.floor(i / size)}}: ${{part.reduce((a, b) => a + b, 0)}}`);", "  }}"],
            "windows": ["  const size = {size};", "  for (let i = 0; i < items.length - size{offs}; i++) {{", "    console.log(`window ${{i}}: ${{Math.max(...items.slice(i, i + size))}}`);", "  }}"],
            "strided": ["  for (let i = {start}; i < items.length; i += {step}) {{", "    console.log(`item ${{i}}: ${{items[i]}}`);", "  }}"],
            "diffs": ["  for (let i = 1; i < items.length; i++) {{", "    const delta = items[i] - items[i - 1];", "    if (delta > 0) {{", "      console.log(`rise ${{i}}: ${{delta}}`);", "    }}", "  }}"],
            "reverse": ["  for (let i = items.length - 1; i >= {skip}; i--) {{", "    if (items[i] % 2 === 0) {{", "      console.log(`${{i}}=${{items[i]}}`);", "    }}", "  }}"],
            "until": ["  let total = 0;", "  let i = 0;", "  while (i < items.length && total + items[i] <= {limit}) {{", "    total += items[i];", "    i += 1;", "  }}", "  console.log(`stopped at ${{i}} total ${{total}}`);"],
            "pairs": ["  let found = 0;", "  for (let i = 0; i < items.length; i++) {{", "    for (let j = i + 1; j < items.length; j++) {{", "      if (items[i] + items[j] === {target}) {{", "        console.log(`pair ${{i}},${{j}}`);", "        found += 1;", "      }}", "    }}", "  }}", "  console.log(`pairs: ${{found}}`);"],
            "inclusive": ["  let running = 0;", "  for (let i = {lo}; i <= {hi}; i++) {{", "    running += items[i];", "    console.log(`step ${{i}}: ${{running}}`);", "  }}"],
        }[nm]
        out += [ln.format(**p) for ln in t]
    code = ["'use strict';", "", "const fs = require('fs');", "", "function report(items) {"] + out + ["}", "", "report(fs.readFileSync('data/readings.txt', 'utf8').split(/\\s+/).filter(Boolean).map(Number));"]
    return {"report.js": "\n".join(code) + "\n"}, "node report.js"


def _go(tpls):
    out = []
    for k, (nm, p) in enumerate(tpls):
        t = {
            "chunks": ["\tsize := {size}", "\tfor i := 0; i < len(items); i += size {{", "\t\tend := i + size", "\t\tif end > len(items) {{", "\t\t\tend = len(items)", "\t\t}}", "\t\tsum := 0", "\t\tfor _, v := range items[i:end] {{", "\t\t\tsum += v", "\t\t}}", '\t\tfmt.Printf("batch %d: %d\\n", i/size, sum)', "\t}}"],
            "windows": ["\tsize := {size}", "\tfor i := 0; i < len(items)-size{offg}; i++ {{", "\t\tbest := items[i]", "\t\tfor _, v := range items[i : i+size] {{", "\t\t\tif v > best {{", "\t\t\t\tbest = v", "\t\t\t}}", "\t\t}}", '\t\tfmt.Printf("window %d: %d\\n", i, best)', "\t}}"],
            "strided": ["\tfor i := {start}; i < len(items); i += {step} {{", '\t\tfmt.Printf("item %d: %d\\n", i, items[i])', "\t}}"],
            "diffs": ["\tfor i := 1; i < len(items); i++ {{", "\t\tdelta := items[i] - items[i-1]", "\t\tif delta > 0 {{", '\t\t\tfmt.Printf("rise %d: %d\\n", i, delta)', "\t\t}}", "\t}}"],
            "reverse": ["\tfor i := len(items) - 1; i >= {skip}; i-- {{", "\t\tif items[i]%2 == 0 {{", '\t\t\tfmt.Printf("%d=%d\\n", i, items[i])', "\t\t}}", "\t}}"],
            "until": ["\ttotal := 0", "\tj := 0", "\tfor j < len(items) && total+items[j] <= {limit} {{", "\t\ttotal += items[j]", "\t\tj++", "\t}}", '\tfmt.Printf("stopped at %d total %d\\n", j, total)'],
            "pairs": ["\tfound := 0", "\tfor i := 0; i < len(items); i++ {{", "\t\tfor j := i + 1; j < len(items); j++ {{", "\t\t\tif items[i]+items[j] == {target} {{", '\t\t\t\tfmt.Printf("pair %d,%d\\n", i, j)', "\t\t\t\tfound++", "\t\t\t}}", "\t\t}}", "\t}}", '\tfmt.Printf("pairs: %d\\n", found)'],
            "inclusive": ["\trunning := 0", "\tfor i := {lo}; i <= {hi}; i++ {{", "\t\trunning += items[i]", '\t\tfmt.Printf("step %d: %d\\n", i, running)', "\t}}"],
        }[nm]
        # each template gets its own scope so short names never clash
        out += ["\t{"] + ["\t" + ln.format(**p) for ln in t] + ["\t}"]
    code = ["package main", "", "import (", '\t"fmt"', '\t"os"', ")", "", "func report(items []int) {"] + out + ["}", "", "func main() {", '\tfile, err := os.Open("data/readings.txt")', "\tif err != nil {", "\t\tpanic(err)", "\t}",
            "\tdefer file.Close()", "\tvar items []int", "\tfor {", "\t\tvar v int", "\t\tif _, err := fmt.Fscan(file, &v); err != nil {", "\t\t\tbreak", "\t\t}", "\t\titems = append(items, v)", "\t}", "\treport(items)", "}"]
    return {"go.mod": "module example.com/report\n\ngo 1.21\n", "main.go": "\n".join(code) + "\n"}, "go run ."


def _rb(tpls):
    out = []
    for nm, p in tpls:
        t = {
            "chunks": ["  size = {size}", "  (0...items.length).step(size) do |i|", '    puts "batch #{{i / size}}: #{{items[i, size].sum}}"', "  end"],
            "windows": ["  size = {size}", "  (0...(items.length - size{offs})).each do |i|", '    puts "window #{{i}}: #{{items[i, size].max}}"', "  end"],
            "strided": ["  ({start}...items.length).step({step}) do |i|", '    puts "item #{{i}}: #{{items[i]}}"', "  end"],
            "diffs": ["  (1...items.length).each do |i|", "    delta = items[i] - items[i - 1]", '    puts "rise #{{i}}: #{{delta}}" if delta.positive?', "  end"],
            "reverse": ["  (items.length - 1).downto({skip}) do |i|", '    puts "#{{i}}=#{{items[i]}}" if items[i].even?', "  end"],
            "until": ["  total = 0", "  i = 0", "  while i < items.length && total + items[i] <= {limit}", "    total += items[i]", "    i += 1", "  end", '  puts "stopped at #{{i}} total #{{total}}"'],
            "pairs": ["  found = 0", "  (0...items.length).each do |i|", "    ((i + 1)...items.length).each do |j|", "      next unless items[i] + items[j] == {target}", "", '      puts "pair #{{i}},#{{j}}"', "      found += 1", "    end", "  end", '  puts "pairs: #{{found}}"'],
            "inclusive": ["  running = 0", "  ({lo}..{hi}).each do |i|", "    running += items[i]", '    puts "step #{{i}}: #{{running}}"', "  end"],
        }[nm]
        out += [ln.format(**p) for ln in t]
    code = ["# frozen_string_literal: true", "", "def report(items)"] + out + ["end", "", "report(File.read('data/readings.txt').split.map(&:to_i))"]
    return {"report.rb": "\n".join(code) + "\n"}, "ruby report.rb"


RENDER = {"python": _py, "javascript": _js, "go": _go, "ruby": _rb}


def build(rng: random.Random, lang: str, tier: int):
    for _ in range(20):
        items, tpls = make_params(rng, tier)
        data = "\n".join(str(x) for x in items) + "\n"
        outs = {}
        ok = True
        for lg in LANGS:
            code, cmd = RENDER[lg](tpls)
            res = fx.run({**code, "data/readings.txt": data}, cmd + " 2>&1", timeout=60)
            if not res.ok:
                ok = False
                break
            outs[lg] = [ln for ln in res.out.split("\n") if ln != ""]
        if not ok:
            continue
        if any(outs[lg] != outs["python"] for lg in outs):
            continue
        lines = outs["python"]
        if not (1 <= len(lines) <= 22):
            continue
        code, cmd = RENDER[lang](tpls)
        files = {**code, "data/readings.txt": data, "README.md": "# Reading summaries\n\n`report()` prints a few summaries of the readings in `data/readings.txt`.\n"}
        return files, lines, cmd, tpls, items
    raise RuntimeError("loops: no agreeing program")
