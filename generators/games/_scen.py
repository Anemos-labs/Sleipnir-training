"""Scenario harnesses for the games category.

A game family ships an *adapter* (engine specific glue, visible to the agent: it shows exactly how the API is called)
plus a *driver* (generic, per language) that replays every scenario file under the data directory:

    # scenario <name>
    > verb args          one command; the adapter maps it to engine calls and returns a string
    = expected reply     the exact reply; "\\n" inside a reply stands for a newline, "\\\\" for a backslash

The hidden tests of a family are more scenario files dropped into the same data directory. Expected replies are
recorded from the reference solution by running a *record driver* over a script (same syntax, no ``=`` lines, plus the
directive ``~ rand N SEED [every=K] [emit=v1,v2] [junk=a|b]`` that plays N random legal moves and emits checks).

Adapter contract (per language):
  python      tests/adapter.py     class Adapter: run(self, verb, args) -> str
  javascript  test/adapter.js      class Adapter { run(verb, args) } exported as { Adapter }
  go          adapter_test.go      type adapter struct{...}; func (a *adapter) run(verb, args string) string
  rust        tests/adapter/mod.rs pub struct Adapter; Adapter::new(); run(&mut self, verb, args) -> String
  java        test/Adapter.java    class Adapter { String run(String verb, String args) }
  c           tests/adapter.{h,c}  void adapter_reset(void); void adapter_run(const char*verb,const char*args,char*out,size_t cap)
Every adapter must implement the verb ``legal`` (sorted legal moves joined by "," or "-" when none) and ``do <move>``
for the random player to work.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from fx.run import CACHE_DIR, _env, write_tree

DATA_DIR = {"python": "tests/data", "javascript": "test/data", "go": "testdata", "rust": "tests/data", "java": "test/data", "c": "tests/data"}

VERIFY = {
    "python": "python3 -m unittest discover -s tests -v",
    "javascript": "node --test test/*.test.js",
    "go": "go test -count=1 ./...",
    "rust": "cargo test --offline --quiet",
    "java": "rm -rf build && mkdir -p build && javac -d build $(find . -name '*.java') && java -cp build TestMain",
    "c": "mkdir -p build && gcc -std=c11 -O1 -Wall -Wextra -Iinclude -Isrc -o build/tests $(find src tests -name '*.c') && ./build/tests",
}


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("\n", "\\n")


# ======================================================================================================== python

PY_CHECK = r'''"""Replays every scenario file in tests/data/ against the engine through tests/adapter.py.

A scenario file has `# scenario <name>` headers, each followed by pairs of lines: `> verb args` (a command for the
adapter) and `= text` (the exact reply; a newline inside a reply is written \n and a backslash \\)."""
import glob
import os
import unittest

from adapter import Adapter

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def esc(s):
    return str(s).replace("\\", "\\\\").replace("\n", "\\n")


def load_scenarios(path):
    out, pending = [], None
    with open(path, encoding="utf-8") as f:
        for raw in f.read().split("\n"):
            if raw.startswith("# scenario"):
                out.append((raw[len("# scenario"):].strip(), []))
            elif raw.startswith("> "):
                pending = raw[2:]
            elif raw.startswith("=") and pending is not None and out:
                out[-1][1].append((pending, raw[2:]))
                pending = None
    return out


class ScenarioTest(unittest.TestCase):
    def test_scenarios(self):
        files = sorted(glob.glob(os.path.join(DATA, "*.txt")))
        self.assertTrue(files, "no scenario files in tests/data")
        for path in files:
            for name, steps in load_scenarios(path):
                with self.subTest(file=os.path.basename(path), scenario=name):
                    adapter = Adapter()
                    for i, (cmd, want) in enumerate(steps, 1):
                        verb, _, args = cmd.partition(" ")
                        got = esc(adapter.run(verb, args))
                        if got != want:
                            self.fail("step %d: > %s\n  expected: %s\n  got:      %s" % (i, cmd, want, got))


if __name__ == "__main__":
    unittest.main()
'''

PY_REC = r'''import sys

sys.path.insert(0, "tests")
from adapter import Adapter


def esc(s):
    return str(s).replace("\\", "\\\\").replace("\n", "\\n")


def lcg(x):
    return (x * 1103515245 + 12345) & 0x7FFFFFFF


out = []
a = None


def step(cmd):
    verb, _, args = cmd.partition(" ")
    got = a.run(verb, args)
    out.append("> " + cmd)
    out.append("= " + esc(got))
    return got


def rand(spec):
    junk = []
    if " junk=" in spec:
        spec, j = spec.split(" junk=", 1)
        junk = j.split("|")
    toks = spec.split()
    n, seed = int(toks[0]), int(toks[1])
    every, emit = 0, []
    for t in toks[2:]:
        if t.startswith("every="):
            every = int(t[6:])
        elif t.startswith("emit="):
            emit = t[5:].split(",")
    x = seed
    for i in range(n):
        legal = a.run("legal", "")
        if legal == "-":
            break
        moves = legal.split(",")
        x = lcg(x)
        if junk and (x >> 8) % 4 == 0:
            x = lcg(x)
            jm = junk[(x >> 8) % len(junk)]
            if jm not in moves:
                step("do " + jm)
        x = lcg(x)
        step("do " + moves[(x >> 8) % len(moves)])
        if every and (i + 1) % every == 0:
            for v in emit:
                step(v)
    for v in emit:
        step(v)


for line in open("rec.script", encoding="utf-8").read().split("\n"):
    if line.startswith("# scenario"):
        a = Adapter()
        out.append(line)
    elif line.startswith("> "):
        step(line[2:])
    elif line.startswith("~ rand "):
        rand(line[7:])
open("rec.out", "w", encoding="utf-8").write("\n".join(out) + "\n")
'''

# ======================================================================================================== javascript

JS_CHECK = r'''// Replays every scenario file in test/data/ against the engine through test/adapter.js.
// A scenario file has `# scenario <name>` headers, each followed by pairs of lines: `> verb args` (a command for the
// adapter) and `= text` (the exact reply; a newline inside a reply is written \n and a backslash \\).
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const { Adapter } = require('./adapter');

const esc = (s) => String(s).replace(/\\/g, '\\\\').replace(/\n/g, '\\n');

function loadScenarios(file) {
  const out = [];
  let pending = null;
  for (const raw of fs.readFileSync(file, 'utf8').split('\n')) {
    if (raw.startsWith('# scenario')) out.push({ name: raw.slice('# scenario'.length).trim(), steps: [] });
    else if (raw.startsWith('> ')) pending = raw.slice(2);
    else if (raw.startsWith('=') && pending !== null && out.length) {
      out[out.length - 1].steps.push([pending, raw.slice(2)]);
      pending = null;
    }
  }
  return out;
}

const dir = path.join(__dirname, 'data');
const files = fs.readdirSync(dir).filter((n) => n.endsWith('.txt')).sort();
test('scenario files exist', () => assert.ok(files.length > 0, 'no scenario files in test/data'));
for (const f of files) {
  for (const sc of loadScenarios(path.join(dir, f))) {
    test(`${f}: ${sc.name}`, () => {
      const adapter = new Adapter();
      sc.steps.forEach(([cmd, want], i) => {
        const sp = cmd.indexOf(' ');
        const verb = sp < 0 ? cmd : cmd.slice(0, sp);
        const args = sp < 0 ? '' : cmd.slice(sp + 1);
        const got = esc(adapter.run(verb, args));
        assert.strictEqual(got, want, `step ${i + 1}: > ${cmd}\n  expected: ${want}\n  got:      ${got}`);
      });
    });
  }
}
'''

JS_REC = r'''const fs = require('fs');
const { Adapter } = require('./test/adapter');

const esc = (s) => String(s).replace(/\\/g, '\\\\').replace(/\n/g, '\\n');
const lcg = (x) => Number((BigInt(x) * 1103515245n + 12345n) & 0x7fffffffn);
const out = [];
let a = null;

function step(cmd) {
  const sp = cmd.indexOf(' ');
  const verb = sp < 0 ? cmd : cmd.slice(0, sp);
  const args = sp < 0 ? '' : cmd.slice(sp + 1);
  const got = a.run(verb, args);
  out.push('> ' + cmd);
  out.push('= ' + esc(got));
  return got;
}

function rand(spec) {
  let junk = [];
  const ji = spec.indexOf(' junk=');
  if (ji >= 0) { junk = spec.slice(ji + 6).split('|'); spec = spec.slice(0, ji); }
  const toks = spec.split(/\s+/);
  const n = parseInt(toks[0], 10), seed = parseInt(toks[1], 10);
  let every = 0, emit = [];
  for (const t of toks.slice(2)) {
    if (t.startsWith('every=')) every = parseInt(t.slice(6), 10);
    else if (t.startsWith('emit=')) emit = t.slice(5).split(',');
  }
  let x = seed;
  for (let i = 0; i < n; i++) {
    const legal = a.run('legal', '');
    if (legal === '-') break;
    const moves = legal.split(',');
    x = lcg(x);
    if (junk.length && ((x >> 8) % 4) === 0) {
      x = lcg(x);
      const jm = junk[(x >> 8) % junk.length];
      if (!moves.includes(jm)) step('do ' + jm);
    }
    x = lcg(x);
    step('do ' + moves[(x >> 8) % moves.length]);
    if (every && (i + 1) % every === 0) for (const v of emit) step(v);
  }
  for (const v of emit) step(v);
}

for (const line of fs.readFileSync('rec.script', 'utf8').split('\n')) {
  if (line.startsWith('# scenario')) { a = new Adapter(); out.push(line); }
  else if (line.startsWith('> ')) step(line.slice(2));
  else if (line.startsWith('~ rand ')) rand(line.slice(7));
}
fs.writeFileSync('rec.out', out.join('\n') + '\n');
'''

# ======================================================================================================== go

GO_CHECK = r'''package @@PKG@@

// Replays every scenario file in testdata/ against the engine through the adapter (adapter_test.go).
// A scenario file has `# scenario <name>` headers, each followed by pairs of lines: `> verb args` (a command for the
// adapter) and `= text` (the exact reply; a newline inside a reply is written \n and a backslash \\).

import (
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"
)

type scenarioStep struct{ cmd, want string }

type scenario struct {
	name  string
	steps []scenarioStep
}

func esc(s string) string {
	return strings.ReplaceAll(strings.ReplaceAll(s, "\\", "\\\\"), "\n", "\\n")
}

func loadScenarios(path string) ([]scenario, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var out []scenario
	pending, have := "", false
	for _, line := range strings.Split(string(b), "\n") {
		switch {
		case strings.HasPrefix(line, "# scenario"):
			out = append(out, scenario{name: strings.TrimSpace(line[len("# scenario"):])})
		case strings.HasPrefix(line, "> "):
			pending, have = line[2:], true
		case strings.HasPrefix(line, "=") && have && len(out) > 0:
			want := ""
			if len(line) > 2 {
				want = line[2:]
			}
			out[len(out)-1].steps = append(out[len(out)-1].steps, scenarioStep{pending, want})
			have = false
		}
	}
	return out, nil
}

func TestScenarios(t *testing.T) {
	files, _ := filepath.Glob("testdata/*.txt")
	sort.Strings(files)
	if len(files) == 0 {
		t.Fatal("no scenario files in testdata/")
	}
	for _, f := range files {
		scs, err := loadScenarios(f)
		if err != nil {
			t.Fatal(err)
		}
		for _, sc := range scs {
			sc := sc
			t.Run(filepath.Base(f)+"/"+sc.name, func(t *testing.T) {
				a := &adapter{}
				for i, st := range sc.steps {
					verb, args, _ := strings.Cut(st.cmd, " ")
					got := esc(a.run(verb, args))
					if got != st.want {
						t.Fatalf("step %d: > %s\n  expected: %s\n  got:      %s", i+1, st.cmd, st.want, got)
					}
				}
			})
		}
	}
}
'''

GO_REC = r'''package @@PKG@@

import (
	"os"
	"strconv"
	"strings"
	"testing"
)

func esc(s string) string {
	return strings.ReplaceAll(strings.ReplaceAll(s, "\\", "\\\\"), "\n", "\\n")
}

func lcg(x uint64) uint64 { return (x*1103515245 + 12345) & 0x7FFFFFFF }

func TestRecord(t *testing.T) {
	raw, err := os.ReadFile("rec.script")
	if err != nil {
		t.Fatal(err)
	}
	var out []string
	var a *adapter
	step := func(cmd string) string {
		verb, args, _ := strings.Cut(cmd, " ")
		got := a.run(verb, args)
		out = append(out, "> "+cmd, "= "+esc(got))
		return got
	}
	rand := func(spec string) {
		var junk []string
		if i := strings.Index(spec, " junk="); i >= 0 {
			junk = strings.Split(spec[i+6:], "|")
			spec = spec[:i]
		}
		toks := strings.Fields(spec)
		n, _ := strconv.Atoi(toks[0])
		seed, _ := strconv.Atoi(toks[1])
		every := 0
		var emit []string
		for _, tk := range toks[2:] {
			if strings.HasPrefix(tk, "every=") {
				every, _ = strconv.Atoi(tk[6:])
			} else if strings.HasPrefix(tk, "emit=") {
				emit = strings.Split(tk[5:], ",")
			}
		}
		x := uint64(seed)
		for i := 0; i < n; i++ {
			legal := a.run("legal", "")
			if legal == "-" {
				break
			}
			moves := strings.Split(legal, ",")
			x = lcg(x)
			if len(junk) > 0 && (x>>8)%4 == 0 {
				x = lcg(x)
				jm := junk[(x>>8)%uint64(len(junk))]
				found := false
				for _, m := range moves {
					if m == jm {
						found = true
					}
				}
				if !found {
					step("do " + jm)
				}
			}
			x = lcg(x)
			step("do " + moves[(x>>8)%uint64(len(moves))])
			if every > 0 && (i+1)%every == 0 {
				for _, v := range emit {
					step(v)
				}
			}
		}
		for _, v := range emit {
			step(v)
		}
	}
	for _, line := range strings.Split(string(raw), "\n") {
		switch {
		case strings.HasPrefix(line, "# scenario"):
			a = &adapter{}
			out = append(out, line)
		case strings.HasPrefix(line, "> "):
			step(line[2:])
		case strings.HasPrefix(line, "~ rand "):
			rand(line[7:])
		}
	}
	if err := os.WriteFile("rec.out", []byte(strings.Join(out, "\n")+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
}
'''

# ======================================================================================================== rust

RS_CHECK = r'''// Replays every scenario file in tests/data/ against the engine through tests/adapter/mod.rs.
// A scenario file has `# scenario <name>` headers, each followed by pairs of lines: `> verb args` (a command for the
// adapter) and `= text` (the exact reply; a newline inside a reply is written \n and a backslash \\).
mod adapter;

use std::fs;

fn esc(s: &str) -> String {
    s.replace('\\', "\\\\").replace('\n', "\\n")
}

#[test]
fn scenarios() {
    let mut files: Vec<_> = fs::read_dir("tests/data")
        .expect("tests/data")
        .map(|e| e.unwrap().path())
        .filter(|p| p.extension().map_or(false, |x| x == "txt"))
        .collect();
    files.sort();
    assert!(!files.is_empty(), "no scenario files in tests/data");
    let mut failures: Vec<String> = Vec::new();
    for f in files {
        let text = fs::read_to_string(&f).unwrap();
        let fname = f.file_name().unwrap().to_string_lossy().to_string();
        let mut name = String::new();
        let mut a = adapter::Adapter::new();
        let mut pending: Option<String> = None;
        let mut idx = 0;
        let mut dead = false;
        for line in text.split('\n') {
            if let Some(rest) = line.strip_prefix("# scenario") {
                name = rest.trim().to_string();
                a = adapter::Adapter::new();
                pending = None;
                idx = 0;
                dead = false;
            } else if let Some(cmd) = line.strip_prefix("> ") {
                pending = Some(cmd.to_string());
            } else if line.starts_with('=') && pending.is_some() && !dead {
                let want = if line.len() > 2 { &line[2..] } else { "" };
                let cmd = pending.take().unwrap();
                idx += 1;
                let (verb, args) = match cmd.split_once(' ') {
                    Some((v, r)) => (v, r),
                    None => (cmd.as_str(), ""),
                };
                let got = esc(&a.run(verb, args));
                if got != want {
                    failures.push(format!("{} / {}: step {}: > {}\n  expected: {}\n  got:      {}", fname, name, idx, cmd, want, got));
                    dead = true;
                }
            }
        }
    }
    if !failures.is_empty() {
        panic!("{} scenario(s) failed:\n{}", failures.len(), failures.join("\n"));
    }
}
'''

RS_REC = r'''mod adapter;

use std::fs;

fn esc(s: &str) -> String {
    s.replace('\\', "\\\\").replace('\n', "\\n")
}

fn lcg(x: u64) -> u64 {
    (x.wrapping_mul(1103515245).wrapping_add(12345)) & 0x7FFFFFFF
}

fn step(a: &mut adapter::Adapter, out: &mut Vec<String>, cmd: &str) -> String {
    let (verb, args) = match cmd.split_once(' ') {
        Some((v, r)) => (v, r),
        None => (cmd, ""),
    };
    let got = a.run(verb, args);
    out.push(format!("> {}", cmd));
    out.push(format!("= {}", esc(&got)));
    got
}

fn rand(a: &mut adapter::Adapter, out: &mut Vec<String>, spec: &str) {
    let mut spec = spec.to_string();
    let mut junk: Vec<String> = Vec::new();
    if let Some(i) = spec.find(" junk=") {
        junk = spec[i + 6..].split('|').map(|s| s.to_string()).collect();
        spec.truncate(i);
    }
    let toks: Vec<&str> = spec.split_whitespace().collect();
    let n: usize = toks[0].parse().unwrap();
    let seed: u64 = toks[1].parse().unwrap();
    let mut every = 0usize;
    let mut emit: Vec<String> = Vec::new();
    for t in &toks[2..] {
        if let Some(v) = t.strip_prefix("every=") {
            every = v.parse().unwrap();
        } else if let Some(v) = t.strip_prefix("emit=") {
            emit = v.split(',').map(|s| s.to_string()).collect();
        }
    }
    let mut x = seed;
    for i in 0..n {
        let legal = a.run("legal", "");
        if legal == "-" {
            break;
        }
        let moves: Vec<&str> = legal.split(',').collect();
        x = lcg(x);
        if !junk.is_empty() && (x >> 8) % 4 == 0 {
            x = lcg(x);
            let jm = junk[((x >> 8) % junk.len() as u64) as usize].clone();
            if !moves.contains(&jm.as_str()) {
                step(a, out, &format!("do {}", jm));
            }
        }
        x = lcg(x);
        let mv = moves[((x >> 8) % moves.len() as u64) as usize].to_string();
        step(a, out, &format!("do {}", mv));
        if every > 0 && (i + 1) % every == 0 {
            for v in &emit {
                step(a, out, v);
            }
        }
    }
    for v in &emit {
        step(a, out, v);
    }
}

#[test]
fn record() {
    let raw = fs::read_to_string("rec.script").unwrap();
    let mut out: Vec<String> = Vec::new();
    let mut a = adapter::Adapter::new();
    for line in raw.split('\n') {
        if line.starts_with("# scenario") {
            a = adapter::Adapter::new();
            out.push(line.to_string());
        } else if let Some(c) = line.strip_prefix("> ") {
            step(&mut a, &mut out, c);
        } else if let Some(s) = line.strip_prefix("~ rand ") {
            rand(&mut a, &mut out, s);
        }
    }
    fs::write("rec.out", out.join("\n") + "\n").unwrap();
}
'''

# ======================================================================================================== java

JAVA_CHECK = r'''import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Replays every scenario file in test/data/ against the engine through Adapter.
 * A scenario file has "# scenario name" headers, each followed by pairs of lines: "> verb args" (a command for the
 * adapter) and "= text" (the exact reply; a newline inside a reply is written \n and a backslash \\).
 */
public class TestMain {
    static String esc(String s) {
        return s.replace("\\", "\\\\").replace("\n", "\\n");
    }

    public static void main(String[] args) throws IOException {
        List<Path> files = new ArrayList<>();
        try (DirectoryStream<Path> ds = Files.newDirectoryStream(Paths.get("test", "data"), "*.txt")) {
            for (Path p : ds) files.add(p);
        }
        Collections.sort(files);
        if (files.isEmpty()) {
            System.out.println("no scenario files in test/data");
            System.exit(1);
        }
        int scenarios = 0, failed = 0;
        for (Path f : files) {
            String name = "";
            Adapter a = null;
            String pending = null;
            boolean dead = false;
            int idx = 0;
            for (String line : new String(Files.readAllBytes(f), StandardCharsets.UTF_8).split("\n", -1)) {
                if (line.startsWith("# scenario")) {
                    name = line.substring("# scenario".length()).trim();
                    a = new Adapter();
                    pending = null;
                    dead = false;
                    idx = 0;
                    scenarios++;
                } else if (line.startsWith("> ")) {
                    pending = line.substring(2);
                } else if (line.startsWith("=") && pending != null && !dead && a != null) {
                    String want = line.length() > 2 ? line.substring(2) : "";
                    String cmd = pending;
                    pending = null;
                    idx++;
                    int sp = cmd.indexOf(' ');
                    String verb = sp < 0 ? cmd : cmd.substring(0, sp);
                    String rest = sp < 0 ? "" : cmd.substring(sp + 1);
                    String got;
                    try {
                        got = esc(a.run(verb, rest));
                    } catch (RuntimeException e) {
                        got = "EXCEPTION " + e;
                    }
                    if (!got.equals(want)) {
                        System.out.println("FAIL " + f.getFileName() + " / " + name + ": step " + idx + ": > " + cmd);
                        System.out.println("  expected: " + want);
                        System.out.println("  got:      " + got);
                        failed++;
                        dead = true;
                    }
                }
            }
        }
        System.out.println(scenarios + " scenarios, " + failed + " failed");
        if (failed > 0) System.exit(1);
    }
}
'''

JAVA_REC = r'''import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class RecMain {
    static List<String> out = new ArrayList<>();
    static Adapter a;

    static String esc(String s) {
        return s.replace("\\", "\\\\").replace("\n", "\\n");
    }

    static long lcg(long x) {
        return (x * 1103515245L + 12345L) & 0x7FFFFFFFL;
    }

    static String step(String cmd) {
        int sp = cmd.indexOf(' ');
        String verb = sp < 0 ? cmd : cmd.substring(0, sp);
        String rest = sp < 0 ? "" : cmd.substring(sp + 1);
        String got = a.run(verb, rest);
        out.add("> " + cmd);
        out.add("= " + esc(got));
        return got;
    }

    static void rand(String spec) {
        List<String> junk = new ArrayList<>();
        int ji = spec.indexOf(" junk=");
        if (ji >= 0) {
            junk = Arrays.asList(spec.substring(ji + 6).split("\\|"));
            spec = spec.substring(0, ji);
        }
        String[] toks = spec.trim().split("\\s+");
        int n = Integer.parseInt(toks[0]);
        long x = Long.parseLong(toks[1]);
        int every = 0;
        String[] emit = new String[0];
        for (int i = 2; i < toks.length; i++) {
            if (toks[i].startsWith("every=")) every = Integer.parseInt(toks[i].substring(6));
            else if (toks[i].startsWith("emit=")) emit = toks[i].substring(5).split(",");
        }
        for (int i = 0; i < n; i++) {
            String legal = a.run("legal", "");
            if (legal.equals("-")) break;
            List<String> moves = Arrays.asList(legal.split(","));
            x = lcg(x);
            if (!junk.isEmpty() && ((x >> 8) % 4) == 0) {
                x = lcg(x);
                String jm = junk.get((int) ((x >> 8) % junk.size()));
                if (!moves.contains(jm)) step("do " + jm);
            }
            x = lcg(x);
            step("do " + moves.get((int) ((x >> 8) % moves.size())));
            if (every > 0 && (i + 1) % every == 0) for (String v : emit) step(v);
        }
        for (String v : emit) step(v);
    }

    public static void main(String[] args) throws IOException {
        String raw = new String(Files.readAllBytes(Paths.get("rec.script")), StandardCharsets.UTF_8);
        for (String line : raw.split("\n", -1)) {
            if (line.startsWith("# scenario")) {
                a = new Adapter();
                out.add(line);
            } else if (line.startsWith("> ")) {
                step(line.substring(2));
            } else if (line.startsWith("~ rand ")) {
                rand(line.substring(7));
            }
        }
        Files.write(Paths.get("rec.out"), (String.join("\n", out) + "\n").getBytes(StandardCharsets.UTF_8));
    }
}
'''

# ======================================================================================================== c

C_ADAPTER_H = r'''#ifndef ADAPTER_H
#define ADAPTER_H
#include <stddef.h>

/* Test glue: maps scenario commands to engine calls. Both functions are implemented in tests/adapter.c. */
void adapter_reset(void);
void adapter_run(const char *verb, const char *args, char *out, size_t cap);

#endif
'''

C_CHECK = r'''/* Replays every scenario file in tests/data/ against the engine through tests/adapter.c.
 * A scenario file has "# scenario <name>" headers, each followed by pairs of lines: "> verb args" (a command for the
 * adapter) and "= text" (the exact reply; a newline inside a reply is written \n and a backslash \\). */
#include <dirent.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "adapter.h"

#define BUF (1 << 16)

static void esc(const char *s, char *out, size_t cap) {
    size_t n = 0;
    for (; *s && n + 3 < cap; s++) {
        if (*s == '\\') { out[n++] = '\\'; out[n++] = '\\'; }
        else if (*s == '\n') { out[n++] = '\\'; out[n++] = 'n'; }
        else out[n++] = *s;
    }
    out[n] = 0;
}

static int cmp_str(const void *a, const void *b) { return strcmp(*(char *const *)a, *(char *const *)b); }

static char *dupstr(const char *s) {
    char *p = malloc(strlen(s) + 1);
    strcpy(p, s);
    return p;
}

static char line[BUF], pending[BUF], reply[BUF], escaped[BUF * 2];

int main(void) {
    DIR *d = opendir("tests/data");
    if (!d) { puts("no tests/data directory"); return 1; }
    char *names[256];
    int nfiles = 0;
    struct dirent *e;
    while ((e = readdir(d)) != NULL && nfiles < 256) {
        size_t l = strlen(e->d_name);
        if (l > 4 && strcmp(e->d_name + l - 4, ".txt") == 0) names[nfiles++] = dupstr(e->d_name);
    }
    closedir(d);
    if (nfiles == 0) { puts("no scenario files in tests/data"); return 1; }
    qsort(names, nfiles, sizeof(char *), cmp_str);
    int scenarios = 0, failed = 0;
    for (int fi = 0; fi < nfiles; fi++) {
        char path[512];
        snprintf(path, sizeof path, "tests/data/%s", names[fi]);
        FILE *f = fopen(path, "r");
        if (!f) { printf("cannot open %s\n", path); return 1; }
        char name[256] = "";
        int have = 0, dead = 0, idx = 0;
        while (fgets(line, sizeof line, f)) {
            size_t len = strlen(line);
            while (len > 0 && (line[len - 1] == '\n' || line[len - 1] == '\r')) line[--len] = 0;
            if (strncmp(line, "# scenario", 10) == 0) {
                const char *p = line + 10;
                while (*p == ' ') p++;
                snprintf(name, sizeof name, "%s", p);
                adapter_reset();
                have = 0; dead = 0; idx = 0;
                scenarios++;
            } else if (strncmp(line, "> ", 2) == 0) {
                snprintf(pending, sizeof pending, "%s", line + 2);
                have = 1;
            } else if (line[0] == '=' && have && !dead) {
                const char *want = len > 2 ? line + 2 : "";
                have = 0;
                idx++;
                char *sp = strchr(pending, ' ');
                const char *args = "";
                char verb[128];
                if (sp) { snprintf(verb, sizeof verb, "%.100s", pending); verb[sp - pending < 100 ? sp - pending : 100] = 0; args = sp + 1; }
                else snprintf(verb, sizeof verb, "%.100s", pending);
                adapter_run(verb, args, reply, sizeof reply);
                esc(reply, escaped, sizeof escaped);
                if (strcmp(escaped, want) != 0) {
                    printf("FAIL %s / %s: step %d: > %s\n  expected: %s\n  got:      %s\n", names[fi], name, idx, pending, want, escaped);
                    failed++;
                    dead = 1;
                }
            }
        }
        fclose(f);
    }
    printf("%d scenarios, %d failed\n", scenarios, failed);
    return failed ? 1 : 0;
}
'''

C_REC = r'''#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "adapter.h"

#define BUF (1 << 16)

static char line[BUF], reply[BUF], escaped[BUF * 2], legal[BUF];
static FILE *outf;

static void esc(const char *s, char *out, size_t cap) {
    size_t n = 0;
    for (; *s && n + 3 < cap; s++) {
        if (*s == '\\') { out[n++] = '\\'; out[n++] = '\\'; }
        else if (*s == '\n') { out[n++] = '\\'; out[n++] = 'n'; }
        else out[n++] = *s;
    }
    out[n] = 0;
}

static unsigned long long lcg(unsigned long long x) { return (x * 1103515245ULL + 12345ULL) & 0x7FFFFFFFULL; }

static void step(const char *cmd) {
    char verb[128];
    const char *args = "";
    const char *sp = strchr(cmd, ' ');
    if (sp) { snprintf(verb, sizeof verb, "%.100s", cmd); verb[sp - cmd < 100 ? sp - cmd : 100] = 0; args = sp + 1; }
    else snprintf(verb, sizeof verb, "%.100s", cmd);
    adapter_run(verb, args, reply, sizeof reply);
    esc(reply, escaped, sizeof escaped);
    fprintf(outf, "> %s\n= %s\n", cmd, escaped);
}

static int in_list(char **moves, int n, const char *m) {
    for (int i = 0; i < n; i++) if (strcmp(moves[i], m) == 0) return 1;
    return 0;
}

static void rand_play(char *spec) {
    char *junk[64];
    int njunk = 0;
    char *ji = strstr(spec, " junk=");
    if (ji) {
        *ji = 0;
        char *p = ji + 6;
        while (njunk < 64) {
            junk[njunk++] = p;
            char *bar = strchr(p, '|');
            if (!bar) break;
            *bar = 0;
            p = bar + 1;
        }
    }
    int n = (int)strtol(strtok(spec, " "), NULL, 10);
    unsigned long long x = strtoull(strtok(NULL, " "), NULL, 10);
    int every = 0;
    char emit[16][64];
    int nemit = 0;
    char *tk;
    while ((tk = strtok(NULL, " ")) != NULL) {
        if (strncmp(tk, "every=", 6) == 0) every = atoi(tk + 6);
        else if (strncmp(tk, "emit=", 5) == 0) {
            char *p = tk + 5;
            while (nemit < 16) {
                char *c = strchr(p, ',');
                if (c) *c = 0;
                snprintf(emit[nemit++], 64, "%s", p);
                if (!c) break;
                p = c + 1;
            }
        }
    }
    for (int i = 0; i < n; i++) {
        adapter_run("legal", "", legal, sizeof legal);
        if (strcmp(legal, "-") == 0) break;
        char *moves[1024];
        int nm = 0;
        char *p = legal;
        while (nm < 1024) {
            moves[nm++] = p;
            char *c = strchr(p, ',');
            if (!c) break;
            *c = 0;
            p = c + 1;
        }
        x = lcg(x);
        if (njunk && ((x >> 8) % 4) == 0) {
            x = lcg(x);
            const char *jm = junk[(x >> 8) % njunk];
            if (!in_list(moves, nm, jm)) { char cmd[256]; snprintf(cmd, sizeof cmd, "do %s", jm); step(cmd); }
        }
        x = lcg(x);
        char cmd[256];
        snprintf(cmd, sizeof cmd, "do %s", moves[(x >> 8) % nm]);
        step(cmd);
        if (every && (i + 1) % every == 0) for (int k = 0; k < nemit; k++) step(emit[k]);
    }
    for (int k = 0; k < nemit; k++) step(emit[k]);
}

int main(void) {
    FILE *f = fopen("rec.script", "r");
    outf = fopen("rec.out", "w");
    if (!f || !outf) return 1;
    while (fgets(line, sizeof line, f)) {
        size_t len = strlen(line);
        while (len > 0 && (line[len - 1] == '\n' || line[len - 1] == '\r')) line[--len] = 0;
        if (strncmp(line, "# scenario", 10) == 0) { adapter_reset(); fprintf(outf, "%s\n", line); }
        else if (strncmp(line, "> ", 2) == 0) step(line + 2);
        else if (strncmp(line, "~ rand ", 7) == 0) rand_play(line + 7);
    }
    fclose(outf);
    return 0;
}
'''


def check_files(lang: str, adapter: dict[str, str], pkg: str = "") -> dict[str, str]:
    """The visible harness: adapter files (engine glue, passed in) plus the generic driver."""
    files = dict(adapter)
    if lang == "python":
        files["tests/test_scenarios.py"] = PY_CHECK
    elif lang == "javascript":
        files["test/scenarios.test.js"] = JS_CHECK
    elif lang == "go":
        files["scenarios_test.go"] = GO_CHECK.replace("@@PKG@@", pkg)
    elif lang == "rust":
        files["tests/scenarios.rs"] = RS_CHECK
    elif lang == "java":
        files["test/TestMain.java"] = JAVA_CHECK
    elif lang == "c":
        files["tests/adapter.h"] = C_ADAPTER_H
        files["tests/test_main.c"] = C_CHECK
    else:
        raise ValueError(lang)
    return files


def _rec_files(lang: str, adapter: dict[str, str], pkg: str) -> tuple[dict[str, str], str]:
    files = dict(adapter)
    if lang == "python":
        files["rec.py"] = PY_REC
        return files, "python3 rec.py"
    if lang == "javascript":
        files["rec.js"] = JS_REC
        return files, "node rec.js"
    if lang == "go":
        files["rec_test.go"] = GO_REC.replace("@@PKG@@", pkg)
        return files, "go test -count=1 -run TestRecord ./..."
    if lang == "rust":
        files["tests/record.rs"] = RS_REC
        return files, "cargo test --offline --quiet --test record"
    if lang == "java":
        files["test/RecMain.java"] = JAVA_REC
        return files, "rm -rf build && mkdir -p build && javac -d build $(find . -name '*.java' ! -name TestMain.java) && java -cp build RecMain"
    if lang == "c":
        files["tests/adapter.h"] = C_ADAPTER_H
        files["tests/rec_main.c"] = C_REC
        return files, "mkdir -p build && gcc -std=c11 -O1 -Wall -Wextra -Iinclude -Isrc -o build/rec $(find src -name '*.c') tests/adapter.c tests/rec_main.c && ./build/rec"
    raise ValueError(lang)


_REC_CACHE = CACHE_DIR.parent / "games-rec"


def record(lang: str, solution: dict[str, str], adapter: dict[str, str], script: str, pkg: str = "", timeout: int = 120) -> str:
    """Run the record driver on the *reference solution* and return the scenario data text (with ``=`` lines).
    ``solution`` must contain every non-test file of the project (engine, build files)."""
    rec, cmd = _rec_files(lang, adapter, pkg)
    files = dict(solution)
    files.update(rec)
    files["rec.script"] = script
    key = hashlib.sha256(json.dumps([sorted(files.items()), cmd], ensure_ascii=False).encode()).hexdigest()
    cf = _REC_CACHE / key[:2] / f"{key}.txt"
    if cf.exists():
        return cf.read_text(encoding="utf-8")
    tmp = tempfile.mkdtemp(prefix="fxrec-")
    try:
        root = Path(tmp) / "w"
        root.mkdir()
        write_tree(root, files)
        p = subprocess.run(["bash", "-c", cmd], cwd=root, env=_env(tmp), stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           errors="replace", timeout=timeout)
        outp = root / "rec.out"
        if p.returncode != 0 or not outp.exists():
            raise RuntimeError(f"record run failed ({lang}, exit {p.returncode}):\n{(p.stdout + p.stderr)[-3000:]}")
        text = outp.read_text(encoding="utf-8")
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
    cf.parent.mkdir(parents=True, exist_ok=True)
    cf.write_text(text, encoding="utf-8")
    return text
