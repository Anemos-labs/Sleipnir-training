"""Test harnesses that read shared JSON vectors, one generator per language.

Every harness has the same behaviour: load ``vectors/full.json`` when it exists (the hidden file) and
``vectors/examples.json`` otherwise, call each case's function with the decoded arguments, and compare the result with
``want`` (or require a failure when the case says ``"error": true``). All cases run; at most eight mismatches are
printed. The harness never depends on anything but the repository root as working directory.

Vector file format::

    {"lib": "<slug>", "cases": [
      {"fn": "name", "args": [...], "want": ...},
      {"fn": "name", "args": [...], "error": true}
    ]}

``int``-ish values are JSON integers, ``opt`` is ``null`` when absent, ``list`` is an array.
"""
from __future__ import annotations

from fx import dd

from ._types import Fn, T, camel, fn_name, jbox, pascal, rust_owned, snake


class LibNames:
    """Identifiers derived from a library slug."""

    def __init__(self, slug: str):
        self.slug = slug
        self.snake = snake(slug)  # python module, rust crate, js file stem
        self.flat = "".join(self.snake.split("_"))  # go package
        self.pascal = pascal(slug)  # java/php class, ruby module


# ------------------------------------------------------------------------------------------------------------------
# file layout of the implementation, per language
# ------------------------------------------------------------------------------------------------------------------

def impl_paths(lang: str, n: LibNames) -> list[str]:
    return {
        "python": [f"{n.snake}.py"],
        "go": [f"{n.flat}.go"],
        "rust": ["src/lib.rs"],
        "java": [f"{n.pascal}.java"],
        "javascript": [f"src/{n.snake}.js"],
        "typescript": [f"src/{n.snake}.ts"],
        "ruby": [f"lib/{n.snake}.rb"],
        "php": [f"src/{n.pascal}.php"],
        "c": [f"src/{n.snake}.c", f"include/{n.snake}.h"],
    }[lang]


VERIFY = {
    "python": "python3 -m unittest discover -s tests -v",
    "go": "go test -count=1 ./...",
    "rust": "cargo test --offline --quiet",
    "java": "rm -rf build && mkdir -p build && javac -d build $(find . -name '*.java') && java -cp build TestMain",
    "javascript": "node --test test/*.test.js",
    "typescript": "rm -rf build && tsc -p . && node --test build/test/*.test.js",
    "ruby": "ruby -Ilib -Itest -e 'Dir[\"test/test_*.rb\"].sort.each { |f| require \"./#{f}\" }'",
    "php": "php tests/run.php",
    "c": "mkdir -p build && gcc -std=c11 -O1 -Wall -Wextra -Iinclude -Isrc -o build/tests $(find src tests -name '*.c') && ./build/tests",
}

PROTECT = {"java": ["TestMain.java"]}


def skeleton(lang: str, n: LibNames) -> dict[str, str]:
    """Build files that exist in an otherwise empty target project."""
    if lang == "go":
        return {"go.mod": f"module example.com/{n.flat}\n\ngo 1.21\n"}
    if lang == "rust":
        return {"Cargo.toml": f'[package]\nname = "{n.snake}"\nversion = "0.1.0"\nedition = "2021"\n\n[dependencies]\n'}
    if lang == "typescript":
        return {"tsconfig.json": dd('''
            {
              "compilerOptions": {
                "target": "ES2022",
                "module": "commonjs",
                "outDir": "build",
                "rootDir": ".",
                "strict": true,
                "types": [],
                "skipLibCheck": true
              },
              "include": ["src/**/*.ts", "test/**/*.ts"]
            }
        ''')}
    return {}


# ------------------------------------------------------------------------------------------------------------------
# stubs: compile-ready, fail at run time
# ------------------------------------------------------------------------------------------------------------------

def stub(lang: str, n: LibNames, fns: list[Fn]) -> dict[str, str]:
    from ._types import arg_name, signature, tname, parse_type

    out = []
    if lang == "python":
        for f in fns:
            sig = signature("python", f)
            out.append(f"{sig}:\n    raise NotImplementedError({f.name!r})\n")
        return {f"{n.snake}.py": "\n\n".join(out)}
    if lang == "go":
        body = [f"package {n.flat}\n"]
        for f in fns:
            sig = signature("go", f)
            body.append(f'{sig} {{\n\tpanic("not implemented")\n}}\n')
        return {f"{n.flat}.go": "\n".join(body)}
    if lang == "rust":
        body = []
        for f in fns:
            sig = signature("rust", f).replace("E>", "String>")
            body.append(f"#[allow(unused_variables)]\n{sig} {{\n    todo!()\n}}\n")
        return {"src/lib.rs": "\n".join(body)}
    if lang == "java":
        body = [f"import java.util.*;\n\npublic final class {n.pascal} {{\n    private {n.pascal}() {{}}\n"]
        for f in fns:
            body.append(f"    {signature('java', f)} {{\n        throw new UnsupportedOperationException(\"not implemented\");\n    }}\n")
        body.append("}\n")
        return {f"{n.pascal}.java": "\n".join(body)}
    if lang == "javascript":
        names = ", ".join(fn_name("javascript", f.name) for f in fns)
        body = ["'use strict';\n"]
        for f in fns:
            a = ", ".join(arg_name("javascript", x) for x, _ in f.args)
            body.append(f"function {fn_name('javascript', f.name)}({a}) {{\n  throw new Error('not implemented');\n}}\n")
        body.append(f"module.exports = {{ {names} }};\n")
        return {f"src/{n.snake}.js": "\n".join(body)}
    if lang == "typescript":
        body = []
        for f in fns:
            body.append(f"export {signature('typescript', f)[len('export '):]} {{\n  throw new Error('not implemented');\n}}\n")
        return {f"src/{n.snake}.ts": "\n".join(body)}
    if lang == "ruby":
        body = [f"module {n.pascal}\n"]
        for f in fns:
            a = ", ".join(x for x, _ in f.args)
            body.append(f"  def self.{f.name}({a})\n    raise NotImplementedError, '{f.name}'\n  end\n")
        body.append("end\n")
        return {f"lib/{n.snake}.rb": "\n".join(body)}
    if lang == "php":
        body = ["<?php\n", f"final class {n.pascal}\n{{"]
        for f in fns:
            body.append(f"    {signature('php', f)}\n    {{\n        throw new \\LogicException('not implemented');\n    }}\n")
        body.append("}\n")
        return {f"src/{n.pascal}.php": "\n".join(body)}
    raise ValueError(lang)


# ------------------------------------------------------------------------------------------------------------------
# python
# ------------------------------------------------------------------------------------------------------------------

def python_harness(n: LibNames, fns: list[Fn]) -> dict[str, str]:
    return {"tests/test_vectors.py": dd(f'''
        import json
        import os
        import sys
        import unittest

        ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        sys.path.insert(0, ROOT)
        import {n.snake} as lib  # noqa: E402


        def _vector_file():
            full = os.path.join(ROOT, "vectors", "full.json")
            return full if os.path.exists(full) else os.path.join(ROOT, "vectors", "examples.json")


        def _canon(v):
            return json.dumps(v, sort_keys=True, ensure_ascii=False)


        class VectorTest(unittest.TestCase):
            def test_vectors(self):
                with open(_vector_file(), encoding="utf-8") as fh:
                    cases = json.load(fh)["cases"]
                bad = []
                for c in cases:
                    label = "{{}}({{}})".format(c["fn"], ", ".join(_canon(a) for a in c["args"]))
                    fn = getattr(lib, c["fn"], None)
                    if fn is None:
                        bad.append("missing function " + c["fn"])
                        continue
                    try:
                        got, failed = fn(*c["args"]), False
                    except Exception as e:  # noqa: BLE001
                        got, failed = None, True
                    if c.get("error"):
                        if not failed:
                            bad.append("{{}}: expected an error, got {{}}".format(label, _canon(got)))
                    elif failed:
                        bad.append("{{}}: unexpected error, want {{}}".format(label, _canon(c["want"])))
                    elif _canon(got) != _canon(c["want"]):
                        bad.append("{{}}: want {{}}, got {{}}".format(label, _canon(c["want"]), _canon(got)))
                if bad:
                    self.fail("{{}} of {{}} vectors failed:\\n  ".format(len(bad), len(cases)) + "\\n  ".join(bad[:8]))


        if __name__ == "__main__":
            unittest.main()
    ''')}


# ------------------------------------------------------------------------------------------------------------------
# javascript / typescript
# ------------------------------------------------------------------------------------------------------------------

_JS_BODY = '''
function camel(s) {
  return s.replace(/_([a-z0-9])/g, (_m, c) => c.toUpperCase());
}

function norm(v) {
  if (v === undefined) return null;
  if (typeof v === 'number' && Object.is(v, -0)) return 0;
  if (Array.isArray(v)) return v.map(norm);
  return v;
}

test('vectors', () => {
  const file = fs.existsSync('vectors/full.json') ? 'vectors/full.json' : 'vectors/examples.json';
  const cases = JSON.parse(fs.readFileSync(file, 'utf8')).cases;
  const bad = [];
  for (const c of cases) {
    const label = `${c.fn}(${c.args.map((a) => JSON.stringify(a)).join(', ')})`;
    const f = mod[camel(c.fn)];
    if (typeof f !== 'function') {
      bad.push(`missing function ${camel(c.fn)}`);
      continue;
    }
    let got;
    let failed = false;
    try {
      got = norm(f(...c.args));
    } catch (e) {
      failed = true;
    }
    if (c.error) {
      if (!failed) bad.push(`${label}: expected an error, got ${JSON.stringify(got)}`);
    } else if (failed) {
      bad.push(`${label}: unexpected error, want ${JSON.stringify(c.want)}`);
    } else {
      try {
        assert.deepStrictEqual(got, c.want);
      } catch (e) {
        bad.push(`${label}: want ${JSON.stringify(c.want)}, got ${JSON.stringify(got)}`);
      }
    }
  }
  assert.strictEqual(bad.length, 0, `${bad.length} of ${cases.length} vectors failed:\\n  ` + bad.slice(0, 8).join('\\n  '));
});
'''


def javascript_harness(n: LibNames, fns: list[Fn]) -> dict[str, str]:
    head = dd(f'''
        'use strict';
        const test = require('node:test');
        const assert = require('node:assert');
        const fs = require('node:fs');
        const mod = require('../src/{n.snake}.js');
    ''')
    return {"test/vectors.test.js": head + _JS_BODY}


def typescript_harness(n: LibNames, fns: list[Fn]) -> dict[str, str]:
    head = dd(f'''
        declare const require: any;
        const test: any = require('node:test');
        const assert: any = require('node:assert');
        const fs: any = require('node:fs');
        import * as lib from '../src/{n.snake}';
        const mod: any = lib;
    ''')
    body = _JS_BODY.replace("function camel(s)", "function camel(s: string): string").replace(
        "function norm(v)", "function norm(v: any): any").replace("(_m, c) =>", "(_m: string, c: string) =>").replace(
        "const bad = [];", "const bad: string[] = [];").replace("let got;", "let got: any;").replace(
        "c.args.map((a) =>", "c.args.map((a: any) =>").replace("for (const c of cases)", "for (const c of cases as any[])").replace(
        "v.map(norm)", "v.map(norm)").replace("catch (e) {", "catch (_e) {")
    return {"test/vectors.test.ts": head + body}


# ------------------------------------------------------------------------------------------------------------------
# ruby / php
# ------------------------------------------------------------------------------------------------------------------

def ruby_harness(n: LibNames, fns: list[Fn]) -> dict[str, str]:
    return {"test/test_vectors.rb": dd(f'''
        require 'json'
        require '{n.snake}'

        file = File.exist?('vectors/full.json') ? 'vectors/full.json' : 'vectors/examples.json'
        cases = JSON.parse(File.read(file, encoding: 'utf-8'))['cases']
        mod = Object.const_get('{n.pascal}')
        bad = []
        cases.each do |c|
          label = "#{{c['fn']}}(#{{c['args'].map {{ |a| JSON.generate(a) }}.join(', ')}})"
          unless mod.respond_to?(c['fn'])
            bad << "missing function #{{c['fn']}}"
            next
          end
          got = nil
          failed = false
          begin
            got = mod.public_send(c['fn'], *c['args'])
          rescue StandardError, NotImplementedError
            failed = true
          end
          if c['error']
            bad << "#{{label}}: expected an error, got #{{JSON.generate(got)}}" unless failed
          elsif failed
            bad << "#{{label}}: unexpected error, want #{{JSON.generate(c['want'])}}"
          elsif JSON.generate(got) != JSON.generate(c['want'])
            bad << "#{{label}}: want #{{JSON.generate(c['want'])}}, got #{{JSON.generate(got)}}"
          end
        end
        unless bad.empty?
          puts "#{{bad.size}} of #{{cases.size}} vectors failed:"
          bad.first(8).each {{ |b| puts "  #{{b}}" }}
          exit 1
        end
        puts "ok #{{cases.size}} vectors"
    ''')}


def php_harness(n: LibNames, fns: list[Fn]) -> dict[str, str]:
    return {"tests/run.php": dd(f'''
        <?php
        require __DIR__ . '/../src/{n.pascal}.php';

        function camel(string $s): string {{
            return lcfirst(str_replace(' ', '', ucwords(str_replace('_', ' ', $s))));
        }}

        function enc($v): string {{
            return json_encode($v, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        }}

        $file = file_exists('vectors/full.json') ? 'vectors/full.json' : 'vectors/examples.json';
        $cases = json_decode(file_get_contents($file), true, 512, JSON_THROW_ON_ERROR)['cases'];
        $bad = [];
        foreach ($cases as $c) {{
            $label = $c['fn'] . '(' . implode(', ', array_map('enc', $c['args'])) . ')';
            $m = camel($c['fn']);
            if (!method_exists('{n.pascal}', $m)) {{
                $bad[] = "missing function $m";
                continue;
            }}
            $got = null;
            $failed = false;
            try {{
                $got = call_user_func_array(['{n.pascal}', $m], $c['args']);
            }} catch (\\Throwable $e) {{
                $failed = true;
            }}
            if (!empty($c['error'])) {{
                if (!$failed) $bad[] = "$label: expected an error, got " . enc($got);
            }} elseif ($failed) {{
                $bad[] = "$label: unexpected error, want " . enc($c['want']);
            }} elseif (enc($got) !== enc($c['want'])) {{
                $bad[] = "$label: want " . enc($c['want']) . ', got ' . enc($got);
            }}
        }}
        if ($bad) {{
            echo count($bad) . ' of ' . count($cases) . " vectors failed:\\n  " . implode("\\n  ", array_slice($bad, 0, 8)) . "\\n";
            exit(1);
        }}
        echo 'ok ' . count($cases) . " vectors\\n";
    ''')}


# ------------------------------------------------------------------------------------------------------------------
# go
# ------------------------------------------------------------------------------------------------------------------

def _go_conv(t: T, x: str) -> str:
    k = t.kind
    if k == "list":
        inner = t.inner
        if inner.kind == "list":
            from ._types import tname
            return f"vxList({x}, func(e any) {tname('go', inner)} {{ return {_go_conv(inner, 'e')} }})"
        return f"vxList({x}, {_go_scalar_fn(inner)})"
    return f"{_go_scalar_fn(t)}({x})"


def _go_scalar_fn(t: T) -> str:
    return {"i32": "vxI32", "u32": "vxU32", "u8": "vxU8", "int": "vxInt", "bool": "vxBool", "str": "vxStr"}[t.kind]


def go_harness(n: LibNames, fns: list[Fn]) -> dict[str, str]:
    cases = []
    for f in fns:
        call_args = ", ".join(_go_conv(t, f"a[{i}]") for i, t in enumerate(f.atypes))
        name = fn_name("go", f.name)
        rt = f.rtype
        if f.err:
            body = f"r, err := {name}({call_args})\n\t\tif err != nil {{\n\t\t\treturn nil, true, true\n\t\t}}\n\t\treturn vxJ(r), false, true"
        elif rt.is_opt:
            body = f"r, ok := {name}({call_args})\n\t\tif !ok {{\n\t\t\treturn nil, false, true\n\t\t}}\n\t\treturn vxJ(r), false, true"
        else:
            body = f"r := {name}({call_args})\n\t\treturn vxJ(r), false, true"
        cases.append(f'\tcase "{f.name}":\n\t\t{body}')
    switch = "\n".join(cases)
    return {"vectors_test.go": f'''package {n.flat}

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"reflect"
	"strings"
	"testing"
)

type vxCase struct {{
	Fn    string `json:"fn"`
	Args  []any  `json:"args"`
	Want  any    `json:"want"`
	Error bool   `json:"error"`
}}

func vxNorm(v any) any {{
	switch x := v.(type) {{
	case json.Number:
		n, err := x.Int64()
		if err != nil {{
			panic(err)
		}}
		return n
	case []any:
		out := make([]any, len(x))
		for i := range x {{
			out[i] = vxNorm(x[i])
		}}
		return out
	}}
	return v
}}

func vxList[T any](v any, f func(any) T) []T {{
	xs := v.([]any)
	out := make([]T, len(xs))
	for i, x := range xs {{
		out[i] = f(x)
	}}
	return out
}}

func vxStr(v any) string  {{ return v.(string) }}
func vxBool(v any) bool   {{ return v.(bool) }}
func vxInt(v any) int64   {{ return v.(int64) }}
func vxI32(v any) int32   {{ return int32(v.(int64)) }}
func vxU32(v any) uint32  {{ return uint32(v.(int64)) }}
func vxU8(v any) uint8    {{ return uint8(v.(int64)) }}

func vxJ(v any) any {{
	if v == nil {{
		return nil
	}}
	rv := reflect.ValueOf(v)
	switch rv.Kind() {{
	case reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64:
		return rv.Int()
	case reflect.Uint, reflect.Uint8, reflect.Uint16, reflect.Uint32, reflect.Uint64:
		return int64(rv.Uint())
	case reflect.String:
		return rv.String()
	case reflect.Bool:
		return rv.Bool()
	case reflect.Slice:
		out := make([]any, rv.Len())
		for i := range out {{
			out[i] = vxJ(rv.Index(i).Interface())
		}}
		return out
	}}
	panic(fmt.Sprintf("unsupported result type %T", v))
}}

func vxShow(v any) string {{
	b, err := json.Marshal(v)
	if err != nil {{
		return fmt.Sprint(v)
	}}
	return string(b)
}}

func vxCall(fn string, a []any) (got any, failed bool, known bool) {{
	switch fn {{
{switch}
	}}
	return nil, false, false
}}

func vxRun(c vxCase) (got any, failed bool, known bool, pan any) {{
	defer func() {{
		if r := recover(); r != nil {{
			pan = r
		}}
	}}()
	got, failed, known = vxCall(c.Fn, c.Args)
	return
}}

func TestVectors(t *testing.T) {{
	path := "vectors/examples.json"
	if _, err := os.Stat("vectors/full.json"); err == nil {{
		path = "vectors/full.json"
	}}
	raw, err := os.ReadFile(path)
	if err != nil {{
		t.Fatal(err)
	}}
	var doc struct {{
		Cases []vxCase `json:"cases"`
	}}
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.UseNumber()
	if err := dec.Decode(&doc); err != nil {{
		t.Fatal(err)
	}}
	bad := []string{{}}
	for _, c := range doc.Cases {{
		c.Args = vxNorm(c.Args).([]any)
		c.Want = vxNorm(c.Want)
		parts := make([]string, len(c.Args))
		for i, a := range c.Args {{
			parts[i] = vxShow(a)
		}}
		label := c.Fn + "(" + strings.Join(parts, ", ") + ")"
		got, failed, known, pan := vxRun(c)
		switch {{
		case !known:
			bad = append(bad, "missing function "+c.Fn)
		case pan != nil:
			bad = append(bad, fmt.Sprintf("%s: panic: %v", label, pan))
		case c.Error:
			if !failed {{
				bad = append(bad, fmt.Sprintf("%s: expected an error, got %s", label, vxShow(got)))
			}}
		case failed:
			bad = append(bad, fmt.Sprintf("%s: unexpected error, want %s", label, vxShow(c.Want)))
		case !reflect.DeepEqual(got, c.Want):
			bad = append(bad, fmt.Sprintf("%s: want %s, got %s", label, vxShow(c.Want), vxShow(got)))
		}}
	}}
	if len(bad) > 0 {{
		shown := bad
		if len(shown) > 8 {{
			shown = shown[:8]
		}}
		t.Fatalf("%d of %d vectors failed:\\n  %s", len(bad), len(doc.Cases), strings.Join(shown, "\\n  "))
	}}
}}
'''}


# ------------------------------------------------------------------------------------------------------------------
# rust
# ------------------------------------------------------------------------------------------------------------------

_RS_COMMON = r'''#![allow(dead_code)]
use std::fmt;

#[derive(Debug, Clone, PartialEq)]
pub enum Json {
    Null,
    Bool(bool),
    Int(i64),
    Str(String),
    Arr(Vec<Json>),
    Obj(Vec<(String, Json)>),
}

impl Json {
    pub fn get(&self, key: &str) -> Option<&Json> {
        match self {
            Json::Obj(kv) => kv.iter().find(|(k, _)| k == key).map(|(_, v)| v),
            _ => None,
        }
    }
    pub fn str_(&self) -> &str {
        match self {
            Json::Str(s) => s,
            o => panic!("expected a string, got {}", o),
        }
    }
    pub fn string(&self) -> String {
        self.str_().to_string()
    }
    pub fn int_(&self) -> i64 {
        match self {
            Json::Int(n) => *n,
            o => panic!("expected an integer, got {}", o),
        }
    }
    pub fn i32_(&self) -> i32 {
        self.int_() as i32
    }
    pub fn u32_(&self) -> u32 {
        self.int_() as u32
    }
    pub fn u8_(&self) -> u8 {
        self.int_() as u8
    }
    pub fn bool_(&self) -> bool {
        match self {
            Json::Bool(b) => *b,
            o => panic!("expected a bool, got {}", o),
        }
    }
    pub fn arr(&self) -> &Vec<Json> {
        match self {
            Json::Arr(a) => a,
            o => panic!("expected an array, got {}", o),
        }
    }
    pub fn list<T>(&self, f: &dyn Fn(&Json) -> T) -> Vec<T> {
        self.arr().iter().map(|x| f(x)).collect()
    }
}

impl fmt::Display for Json {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        match self {
            Json::Null => write!(f, "null"),
            Json::Bool(b) => write!(f, "{}", b),
            Json::Int(n) => write!(f, "{}", n),
            Json::Str(s) => {
                write!(f, "\"")?;
                for c in s.chars() {
                    match c {
                        '"' => write!(f, "\\\"")?,
                        '\\' => write!(f, "\\\\")?,
                        '\n' => write!(f, "\\n")?,
                        '\t' => write!(f, "\\t")?,
                        c if (c as u32) < 0x20 => write!(f, "\\u{:04x}", c as u32)?,
                        c => write!(f, "{}", c)?,
                    }
                }
                write!(f, "\"")
            }
            Json::Arr(a) => {
                write!(f, "[")?;
                for (i, x) in a.iter().enumerate() {
                    if i > 0 {
                        write!(f, ",")?;
                    }
                    write!(f, "{}", x)?;
                }
                write!(f, "]")
            }
            Json::Obj(kv) => {
                write!(f, "{{")?;
                for (i, (k, v)) in kv.iter().enumerate() {
                    if i > 0 {
                        write!(f, ",")?;
                    }
                    write!(f, "{}:{}", Json::Str(k.clone()), v)?;
                }
                write!(f, "}}")
            }
        }
    }
}

struct Parser {
    s: Vec<char>,
    i: usize,
}

pub fn parse(src: &str) -> Result<Json, String> {
    let mut p = Parser { s: src.chars().collect(), i: 0 };
    let v = p.value()?;
    p.ws();
    if p.i != p.s.len() {
        return Err("trailing data".to_string());
    }
    Ok(v)
}

impl Parser {
    fn ws(&mut self) {
        while self.i < self.s.len() && self.s[self.i].is_whitespace() {
            self.i += 1;
        }
    }
    fn lit(&mut self, word: &str, v: Json) -> Result<Json, String> {
        let w: Vec<char> = word.chars().collect();
        if self.s[self.i..].starts_with(&w) {
            self.i += w.len();
            Ok(v)
        } else {
            Err(format!("bad literal at {}", self.i))
        }
    }
    fn value(&mut self) -> Result<Json, String> {
        self.ws();
        match self.s.get(self.i).copied() {
            None => Err("unexpected end".to_string()),
            Some('n') => self.lit("null", Json::Null),
            Some('t') => self.lit("true", Json::Bool(true)),
            Some('f') => self.lit("false", Json::Bool(false)),
            Some('"') => Ok(Json::Str(self.string()?)),
            Some('[') => {
                self.i += 1;
                let mut out = Vec::new();
                self.ws();
                if self.s.get(self.i) == Some(&']') {
                    self.i += 1;
                    return Ok(Json::Arr(out));
                }
                loop {
                    out.push(self.value()?);
                    self.ws();
                    match self.s.get(self.i) {
                        Some(',') => self.i += 1,
                        Some(']') => {
                            self.i += 1;
                            return Ok(Json::Arr(out));
                        }
                        _ => return Err(format!("bad array at {}", self.i)),
                    }
                }
            }
            Some('{') => {
                self.i += 1;
                let mut out = Vec::new();
                self.ws();
                if self.s.get(self.i) == Some(&'}') {
                    self.i += 1;
                    return Ok(Json::Obj(out));
                }
                loop {
                    self.ws();
                    let k = self.string()?;
                    self.ws();
                    if self.s.get(self.i) != Some(&':') {
                        return Err(format!("expected ':' at {}", self.i));
                    }
                    self.i += 1;
                    let v = self.value()?;
                    out.push((k, v));
                    self.ws();
                    match self.s.get(self.i) {
                        Some(',') => self.i += 1,
                        Some('}') => {
                            self.i += 1;
                            return Ok(Json::Obj(out));
                        }
                        _ => return Err(format!("bad object at {}", self.i)),
                    }
                }
            }
            Some(c) if c == '-' || c.is_ascii_digit() => {
                let st = self.i;
                self.i += 1;
                while self.i < self.s.len() && self.s[self.i].is_ascii_digit() {
                    self.i += 1;
                }
                let t: String = self.s[st..self.i].iter().collect();
                t.parse::<i64>().map(Json::Int).map_err(|e| format!("{}: {}", t, e))
            }
            Some(c) => Err(format!("unexpected {:?} at {}", c, self.i)),
        }
    }
    fn hex4(&mut self) -> Result<u32, String> {
        if self.i + 4 > self.s.len() {
            return Err("short \\u escape".to_string());
        }
        let t: String = self.s[self.i..self.i + 4].iter().collect();
        self.i += 4;
        u32::from_str_radix(&t, 16).map_err(|e| e.to_string())
    }
    fn string(&mut self) -> Result<String, String> {
        if self.s.get(self.i) != Some(&'"') {
            return Err(format!("expected string at {}", self.i));
        }
        self.i += 1;
        let mut out = String::new();
        loop {
            let c = *self.s.get(self.i).ok_or("unterminated string")?;
            self.i += 1;
            match c {
                '"' => return Ok(out),
                '\\' => {
                    let e = *self.s.get(self.i).ok_or("bad escape")?;
                    self.i += 1;
                    match e {
                        '"' => out.push('"'),
                        '\\' => out.push('\\'),
                        '/' => out.push('/'),
                        'b' => out.push('\u{8}'),
                        'f' => out.push('\u{c}'),
                        'n' => out.push('\n'),
                        'r' => out.push('\r'),
                        't' => out.push('\t'),
                        'u' => {
                            let mut cp = self.hex4()?;
                            if (0xD800..0xDC00).contains(&cp) {
                                if self.s.get(self.i) == Some(&'\\') && self.s.get(self.i + 1) == Some(&'u') {
                                    self.i += 2;
                                    let lo = self.hex4()?;
                                    cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
                                } else {
                                    return Err("lone surrogate".to_string());
                                }
                            }
                            out.push(char::from_u32(cp).ok_or("bad code point")?);
                        }
                        _ => return Err(format!("bad escape \\{}", e)),
                    }
                }
                c => out.push(c),
            }
        }
    }
}
'''


def _rs_conv(t: T, x: str, depth: int = 0) -> str:
    k = t.kind
    if k == "list":
        v = f"e{depth}"
        inner = t.inner
        if inner.kind == "list":
            return f"&{x}.list(&|{v}| {_rs_owned_conv(inner, v, depth + 1)})"
        return f"&{x}.list(&|{v}| {_rs_owned_conv(inner, v, depth + 1)})"
    if k == "str":
        return f"{x}.str_()"
    return {"i32": f"{x}.i32_()", "u32": f"{x}.u32_()", "u8": f"{x}.u8_()", "int": f"{x}.int_()", "bool": f"{x}.bool_()"}[k]


def _rs_owned_conv(t: T, x: str, depth: int) -> str:
    """Conversion producing an owned value of ``rust_owned(t)``."""
    k = t.kind
    if k == "list":
        v = f"e{depth}"
        return f"{x}.list(&|{v}| {_rs_owned_conv(t.inner, v, depth + 1)})"
    if k == "str":
        return f"{x}.string()"
    return {"i32": f"{x}.i32_()", "u32": f"{x}.u32_()", "u8": f"{x}.u8_()", "int": f"{x}.int_()", "bool": f"{x}.bool_()"}[k]


def rust_harness(n: LibNames, fns: list[Fn]) -> dict[str, str]:
    arms = []
    for f in fns:
        args = ", ".join(_rs_conv(t, f"a[{i}]") for i, t in enumerate(f.atypes))
        call = f"{n.snake}::{fn_name('rust', f.name)}({args})"
        if f.err:
            arms.append(f'        "{f.name}" => {call}.map(|v| v.j()).map_err(|_| ()),')
        else:
            arms.append(f'        "{f.name}" => Ok({call}.j()),')
    arm_text = "\n".join(arms)
    main = f'''mod common;
use common::Json;
use std::panic::{{catch_unwind, AssertUnwindSafe}};

trait ToJ {{
    fn j(&self) -> Json;
}}
impl ToJ for i32 {{
    fn j(&self) -> Json {{
        Json::Int(*self as i64)
    }}
}}
impl ToJ for u32 {{
    fn j(&self) -> Json {{
        Json::Int(*self as i64)
    }}
}}
impl ToJ for u8 {{
    fn j(&self) -> Json {{
        Json::Int(*self as i64)
    }}
}}
impl ToJ for i64 {{
    fn j(&self) -> Json {{
        Json::Int(*self)
    }}
}}
impl ToJ for bool {{
    fn j(&self) -> Json {{
        Json::Bool(*self)
    }}
}}
impl ToJ for String {{
    fn j(&self) -> Json {{
        Json::Str(self.clone())
    }}
}}
impl<T: ToJ> ToJ for Vec<T> {{
    fn j(&self) -> Json {{
        Json::Arr(self.iter().map(|x| x.j()).collect())
    }}
}}
impl<T: ToJ> ToJ for Option<T> {{
    fn j(&self) -> Json {{
        match self {{
            Some(x) => x.j(),
            None => Json::Null,
        }}
    }}
}}

fn call(f: &str, a: &[Json]) -> Option<Result<Json, ()>> {{
    Some(match f {{
{arm_text}
        _ => return None,
    }})
}}

#[test]
fn vectors() {{
    let path = if std::path::Path::new("vectors/full.json").exists() {{ "vectors/full.json" }} else {{ "vectors/examples.json" }};
    let text = std::fs::read_to_string(path).expect("read vectors");
    let doc = common::parse(&text).expect("parse vectors");
    let cases = doc.get("cases").expect("cases").arr().clone();
    let mut bad: Vec<String> = Vec::new();
    for c in &cases {{
        let f = c.get("fn").unwrap().str_().to_string();
        let args = c.get("args").unwrap().arr().clone();
        let label = format!("{{}}({{}})", f, args.iter().map(|a| a.to_string()).collect::<Vec<_>>().join(", "));
        let is_err = c.get("error").is_some();
        let res = catch_unwind(AssertUnwindSafe(|| call(&f, &args)));
        match res {{
            Err(_) => bad.push(format!("{{}}: panic", label)),
            Ok(None) => bad.push(format!("missing function {{}}", f)),
            Ok(Some(Err(()))) => {{
                if !is_err {{
                    bad.push(format!("{{}}: unexpected error, want {{}}", label, c.get("want").unwrap()));
                }}
            }}
            Ok(Some(Ok(got))) => {{
                if is_err {{
                    bad.push(format!("{{}}: expected an error, got {{}}", label, got));
                }} else if &got != c.get("want").unwrap() {{
                    bad.push(format!("{{}}: want {{}}, got {{}}", label, c.get("want").unwrap(), got));
                }}
            }}
        }}
    }}
    if !bad.is_empty() {{
        panic!("{{}} of {{}} vectors failed:\\n  {{}}", bad.len(), cases.len(), bad.iter().take(8).cloned().collect::<Vec<_>>().join("\\n  "));
    }}
}}
'''
    return {"tests/common/mod.rs": _RS_COMMON, "tests/vectors.rs": main}


# ------------------------------------------------------------------------------------------------------------------
# java
# ------------------------------------------------------------------------------------------------------------------

def _java_conv(t: T, x: str, depth: int = 0) -> str:
    k = t.kind
    if k == "list":
        v = f"e{depth}"
        return f"TestMain.<{jbox(t.inner)}>list({x}, {v} -> {_java_conv(t.inner, v, depth + 1)})"
    return {
        "i32": f"((Long) {x}).intValue()",
        "u8": f"((Long) {x}).intValue()",
        "u32": f"(Long) {x}",
        "int": f"(Long) {x}",
        "bool": f"(Boolean) {x}",
        "str": f"(String) {x}",
    }[k]


def java_harness(n: LibNames, fns: list[Fn]) -> dict[str, str]:
    arms = []
    for f in fns:
        args = ", ".join(_java_conv(t, f"a.get({i})") for i, t in enumerate(f.atypes))
        arms.append(f'            case "{f.name}": return {n.pascal}.{fn_name("java", f.name)}({args});')
    arm_text = "\n".join(arms)
    return {"TestMain.java": f'''import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;

public class TestMain {{
    static final Object UNKNOWN = new Object();

    // ---- minimal JSON reader: null, Boolean, Long, String, List<Object>, Map<String,Object> ----
    static final class Parser {{
        final String s;
        int i = 0;
        Parser(String s) {{ this.s = s; }}
        void ws() {{ while (i < s.length() && Character.isWhitespace(s.charAt(i))) i++; }}
        Object value() {{
            ws();
            char c = s.charAt(i);
            if (c == '"') return string();
            if (c == '[') {{
                i++;
                List<Object> out = new ArrayList<>();
                ws();
                if (s.charAt(i) == ']') {{ i++; return out; }}
                while (true) {{
                    out.add(value());
                    ws();
                    char d = s.charAt(i++);
                    if (d == ']') return out;
                    if (d != ',') throw new IllegalStateException("bad array at " + i);
                }}
            }}
            if (c == '{{') {{
                i++;
                Map<String, Object> out = new LinkedHashMap<>();
                ws();
                if (s.charAt(i) == '}}') {{ i++; return out; }}
                while (true) {{
                    ws();
                    String k = string();
                    ws();
                    if (s.charAt(i++) != ':') throw new IllegalStateException("expected ':' at " + i);
                    out.put(k, value());
                    ws();
                    char d = s.charAt(i++);
                    if (d == '}}') return out;
                    if (d != ',') throw new IllegalStateException("bad object at " + i);
                }}
            }}
            if (s.startsWith("null", i)) {{ i += 4; return null; }}
            if (s.startsWith("true", i)) {{ i += 4; return Boolean.TRUE; }}
            if (s.startsWith("false", i)) {{ i += 5; return Boolean.FALSE; }}
            int st = i;
            if (c == '-') i++;
            while (i < s.length() && Character.isDigit(s.charAt(i))) i++;
            return Long.valueOf(s.substring(st, i));
        }}
        String string() {{
            if (s.charAt(i) != '"') throw new IllegalStateException("expected string at " + i);
            i++;
            StringBuilder b = new StringBuilder();
            while (true) {{
                char c = s.charAt(i++);
                if (c == '"') return b.toString();
                if (c != '\\\\') {{ b.append(c); continue; }}
                char e = s.charAt(i++);
                switch (e) {{
                    case 'n': b.append('\\n'); break;
                    case 't': b.append('\\t'); break;
                    case 'r': b.append('\\r'); break;
                    case 'b': b.append('\\b'); break;
                    case 'f': b.append('\\f'); break;
                    case 'u': b.append((char) Integer.parseInt(s.substring(i, i + 4), 16)); i += 4; break;
                    default: b.append(e);
                }}
            }}
        }}
    }}

    @SuppressWarnings("unchecked")
    static <T> List<T> list(Object v, Function<Object, T> f) {{
        List<T> out = new ArrayList<>();
        for (Object x : (List<Object>) v) out.add(f.apply(x));
        return out;
    }}

    static Object toJ(Object v) {{
        if (v == null) return null;
        if (v instanceof Integer) return Long.valueOf((Integer) v);
        if (v instanceof Long || v instanceof Boolean || v instanceof String) return v;
        if (v instanceof List) {{
            List<Object> out = new ArrayList<>();
            for (Object x : (List<?>) v) out.add(toJ(x));
            return out;
        }}
        throw new IllegalStateException("unsupported result type " + v.getClass().getName());
    }}

    static String show(Object v) {{
        if (v == null) return "null";
        if (v instanceof String) {{
            StringBuilder b = new StringBuilder("\\"");
            for (char c : ((String) v).toCharArray()) {{
                if (c == '"') b.append("\\\\\\"");
                else if (c == '\\\\') b.append("\\\\\\\\");
                else if (c == '\\n') b.append("\\\\n");
                else if (c < 0x20) b.append(String.format("\\\\u%04x", (int) c));
                else b.append(c);
            }}
            return b.append('"').toString();
        }}
        if (v instanceof List) {{
            StringBuilder b = new StringBuilder("[");
            boolean first = true;
            for (Object x : (List<?>) v) {{
                if (!first) b.append(',');
                first = false;
                b.append(show(x));
            }}
            return b.append(']').toString();
        }}
        return String.valueOf(v);
    }}

    static Object call(String fn, List<Object> a) throws Exception {{
        switch (fn) {{
{arm_text}
            default: return UNKNOWN;
        }}
    }}

    @SuppressWarnings("unchecked")
    public static void main(String[] args) throws IOException {{
        String path = Files.exists(Paths.get("vectors/full.json")) ? "vectors/full.json" : "vectors/examples.json";
        String text = new String(Files.readAllBytes(Paths.get(path)), StandardCharsets.UTF_8);
        Map<String, Object> doc = (Map<String, Object>) new Parser(text).value();
        List<Object> cases = (List<Object>) doc.get("cases");
        List<String> bad = new ArrayList<>();
        for (Object o : cases) {{
            Map<String, Object> c = (Map<String, Object>) o;
            String fn = (String) c.get("fn");
            List<Object> a = (List<Object>) c.get("args");
            StringBuilder lb = new StringBuilder(fn).append('(');
            for (int k = 0; k < a.size(); k++) lb.append(k > 0 ? ", " : "").append(show(a.get(k)));
            String label = lb.append(')').toString();
            boolean isErr = Boolean.TRUE.equals(c.get("error"));
            Object got = null;
            boolean failed = false;
            try {{
                got = call(fn, a);
                if (got == UNKNOWN) {{ bad.add("missing function " + fn); continue; }}
                got = toJ(got);
            }} catch (Throwable e) {{
                failed = true;
            }}
            if (isErr) {{
                if (!failed) bad.add(label + ": expected an error, got " + show(got));
            }} else if (failed) {{
                bad.add(label + ": unexpected error, want " + show(c.get("want")));
            }} else if (!Objects.equals(got, c.get("want"))) {{
                bad.add(label + ": want " + show(c.get("want")) + ", got " + show(got));
            }}
        }}
        if (!bad.isEmpty()) {{
            System.out.println(bad.size() + " of " + cases.size() + " vectors failed:");
            for (int k = 0; k < Math.min(8, bad.size()); k++) System.out.println("  " + bad.get(k));
            System.exit(1);
        }}
        System.out.println("ok " + cases.size() + " vectors");
    }}
}}
'''}


# ------------------------------------------------------------------------------------------------------------------
# c (source language only): cases are compiled into the test program
# ------------------------------------------------------------------------------------------------------------------

def _c_str(s: str) -> str:
    out = ['"']
    for b in s.encode("utf-8"):
        if b in (0x22, 0x5C):
            out.append("\\" + chr(b))
        elif 0x20 <= b < 0x7F:
            out.append(chr(b))
        else:
            out.append("\\%03o" % b)
    out.append('"')
    return "".join(out)


def c_harness(n: LibNames, fns: list[Fn], cases: list[dict]) -> dict[str, str]:
    byname = {f.name: f for f in fns}
    lines = []
    for idx, c in enumerate(cases):
        f = byname[c["fn"]]
        pre, args = [], []
        for j, (t, v) in enumerate(zip(f.atypes, c["args"])):
            if t.is_list:
                el = t.inner
                if el.kind == "str":
                    pre.append(f"const char *xs{j}[] = {{{', '.join(_c_str(x) for x in v) or 'NULL'}}};")
                else:
                    cty = {"i32": "int32_t", "u32": "uint32_t", "u8": "uint8_t", "int": "int64_t", "bool": "int"}[el.kind]
                    pre.append(f"{cty} xs{j}[] = {{{', '.join(str(int(x)) for x in v) or '0'}}};")
                args.append(f"xs{j}, {len(v)}")
            elif t.kind == "str":
                args.append(_c_str(v))
            elif t.kind == "bool":
                args.append("1" if v else "0")
            elif t.kind == "u32":
                args.append(f"{v}u")
            elif t.kind == "int":
                args.append(f"INT64_C({v})")
            else:
                args.append(str(v))
        rt = f.rtype
        label = f"{c['fn']}#{idx}"
        name = f"{n.snake}_{f.name}"
        body = " ".join(pre)
        want = c.get("want")
        if rt.kind == "str":
            call = f"char out[8192]; int rc = {name}({', '.join(args)}{', ' if args else ''}out, sizeof out);"
            if c.get("error"):
                chk = f'check_err("{label}", rc);'
            else:
                chk = f'check_str("{label}", rc, out, {_c_str(want)});'
        elif f.err:
            cty = {"i32": "int32_t", "u32": "uint32_t", "u8": "uint8_t", "int": "int64_t", "bool": "int"}[rt.kind]
            call = f"{cty} out = 0; int rc = {name}({', '.join(args)}{', ' if args else ''}&out);"
            chk = f'check_err("{label}", rc);' if c.get("error") else f'check_int("{label}", rc, (int64_t) out, INT64_C({int(want)}));'
        else:
            call = f"int64_t got = (int64_t) {name}({', '.join(args)});"
            chk = f'check_int("{label}", 0, got, INT64_C({int(want)}));'
        lines.append(f"    {{ {body} {call} {chk} }}")
    text = f'''#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "{n.snake}.h"

static int failures = 0;
static int total = 0;

static void fail(const char *label, const char *msg) {{
    failures++;
    if (failures <= 8) printf("  %s: %s\\n", label, msg);
}}

static void check_err(const char *label, int rc) {{
    total++;
    if (rc == 0) fail(label, "expected an error");
}}

static void check_str(const char *label, int rc, const char *got, const char *want) {{
    total++;
    char msg[600];
    if (rc != 0) {{ fail(label, "unexpected error"); return; }}
    if (strcmp(got, want) != 0) {{
        snprintf(msg, sizeof msg, "want \\"%s\\", got \\"%s\\"", want, got);
        fail(label, msg);
    }}
}}

static void check_int(const char *label, int rc, int64_t got, int64_t want) {{
    total++;
    char msg[200];
    if (rc != 0) {{ fail(label, "unexpected error"); return; }}
    if (got != want) {{
        snprintf(msg, sizeof msg, "want %lld, got %lld", (long long) want, (long long) got);
        fail(label, msg);
    }}
}}

int main(void) {{
{chr(10).join(lines)}
    if (failures) {{
        printf("%d of %d vectors failed\\n", failures, total);
        return 1;
    }}
    printf("ok %d vectors\\n", total);
    return 0;
}}
'''
    return {"tests/test_main.c": text}


HARNESS = {
    "python": python_harness,
    "javascript": javascript_harness,
    "typescript": typescript_harness,
    "ruby": ruby_harness,
    "php": php_harness,
    "go": go_harness,
    "rust": rust_harness,
    "java": java_harness,
}
