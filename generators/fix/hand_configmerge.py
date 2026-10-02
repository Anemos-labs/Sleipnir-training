"""Layered configuration: precedence, coercion, falsy values, aliasing. python settings, js option merger, ruby config helpers."""
from fx import dd, family
from generators.fix._hand_kit import Base, Bug, tasks_from

# ------------------------------------------------------------------------------------------------------------------
# Base A (python): defaults < file < environment < command line.
# ------------------------------------------------------------------------------------------------------------------

A_README = dd('''
    # settings

    Layered configuration for a service. `settings.loader.load(defaults, file_data=None, env=None, cli=None)` builds the
    effective settings from four layers; **later layers win**: defaults < file < environment < command line.

    ## `settings.merge.deep_merge(base, override)`
    Returns a new dict. Dicts are merged recursively; every other value (lists included) in `override` replaces the base
    value. A `None` in `override` means "not given": it never replaces anything and is never added. Falsy values that are not
    `None` (`0`, `False`, `""`, `[]`) are real values and do override. Neither argument is modified and the result shares no
    dict or list with them.

    ## `settings.coerce.coerce(text, like)`
    Converts the text of an environment variable to the type of the default `like`: `bool` (`1 true yes on` /
    `0 false no off`, any case, otherwise `ValueError`), `int`, `float` (`ValueError` for bad numbers), `list` (comma
    separated, items stripped, empty text is `[]`), anything else stays a string.

    ## `settings.loader`
    * `from_env(env, defaults, prefix="APP_")`: variables starting with the prefix; the rest of the name, split at `__`
      and lower-cased, is the path (`APP_DB__PORT` is `db.port`). The value is coerced to the type of the default at that path;
      a path with no default stays a string.
    * `parse_cli(args)`: `["--set", "db.port=6000", "--set", "debug=true"]` gives `{"db": {"port": 6000}, "debug": True}`:
      each value is parsed as JSON when it is valid JSON and is a string otherwise; anything that is not a `--set key=value`
      pair is a `ValueError`.
''')

A_MERGE = dd('''
    def _copy(value):
        if isinstance(value, dict):
            return {k: _copy(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_copy(v) for v in value]
        return value


    def deep_merge(base, override):
        out = {k: _copy(v) for k, v in base.items()}
        for key, value in override.items():
            if value is None:
                continue
            if isinstance(value, dict) and isinstance(out.get(key), dict):
                out[key] = deep_merge(out[key], value)
            else:
                out[key] = _copy(value)
        return out
''')

A_COERCE = dd('''
    TRUE = {"1", "true", "yes", "on"}
    FALSE = {"0", "false", "no", "off"}


    def coerce(text, like):
        if isinstance(like, bool):
            word = text.strip().lower()
            if word in TRUE:
                return True
            if word in FALSE:
                return False
            raise ValueError(f"not a boolean: {text!r}")
        if isinstance(like, int):
            return int(text)
        if isinstance(like, float):
            return float(text)
        if isinstance(like, list):
            return [part.strip() for part in text.split(",")] if text.strip() else []
        return text
''')

A_LOADER = dd('''
    import json

    from .coerce import coerce
    from .merge import deep_merge

    _MISSING = object()


    def _lookup(defaults, path):
        node = defaults
        for part in path:
            if not isinstance(node, dict) or part not in node:
                return _MISSING
            node = node[part]
        return node


    def from_env(env, defaults, prefix="APP_"):
        out = {}
        for name in sorted(env):
            if not name.startswith(prefix):
                continue
            path = [part.lower() for part in name[len(prefix):].split("__") if part]
            if not path:
                continue
            like = _lookup(defaults, path)
            node = out
            for part in path[:-1]:
                node = node.setdefault(part, {})
            node[path[-1]] = env[name] if like is _MISSING else coerce(env[name], like)
        return out


    def parse_cli(args):
        out = {}
        args = list(args)
        while args:
            flag = args.pop(0)
            if flag != "--set" or not args:
                raise ValueError(f"expected --set key=value, got {flag!r}")
            pair = args.pop(0)
            if "=" not in pair:
                raise ValueError(f"expected key=value, got {pair!r}")
            key, raw = pair.split("=", 1)
            try:
                value = json.loads(raw)
            except ValueError:
                value = raw
            node = out
            parts = key.split(".")
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = value
        return out


    def load(defaults, file_data=None, env=None, cli=None):
        cfg = deep_merge(defaults, file_data or {})
        cfg = deep_merge(cfg, from_env(env or {}, defaults))
        cfg = deep_merge(cfg, parse_cli(cli or []))
        return cfg
''')

A_VISIBLE = {
    "tests/test_loader.py": dd('''
        import unittest

        from settings.loader import load

        DEFAULTS = {"name": "svc", "debug": False, "db": {"host": "localhost", "port": 5432}, "tags": ["a"]}


        class LoaderTests(unittest.TestCase):
            def test_defaults_only(self):
                self.assertEqual(load(DEFAULTS), DEFAULTS)

            def test_file_overrides_defaults(self):
                cfg = load(DEFAULTS, {"db": {"port": 6000}})
                self.assertEqual(cfg["db"], {"host": "localhost", "port": 6000})

            def test_env_int(self):
                cfg = load(DEFAULTS, env={"APP_DB__PORT": "7000"})
                self.assertEqual(cfg["db"]["port"], 7000)


        if __name__ == "__main__":
            unittest.main()
    '''),
}

A_HIDDEN = {
    "tests/test_hidden_loader.py": dd('''
        import copy
        import unittest

        from settings.coerce import coerce
        from settings.loader import from_env, load, parse_cli
        from settings.merge import deep_merge

        DEFAULTS = {
            "name": "svc",
            "debug": True,
            "workers": 4,
            "ratio": 0.5,
            "db": {"host": "localhost", "port": 5432, "pool": {"min": 1, "max": 5}},
            "tags": ["a", "b"],
        }


        class Merge(unittest.TestCase):
            def test_nested_merge_keeps_siblings(self):
                out = deep_merge(DEFAULTS, {"db": {"pool": {"max": 9}}})
                self.assertEqual(out["db"], {"host": "localhost", "port": 5432, "pool": {"min": 1, "max": 9}})

            def test_lists_are_replaced(self):
                self.assertEqual(deep_merge({"tags": ["a", "b"]}, {"tags": ["c"]}), {"tags": ["c"]})
                self.assertEqual(deep_merge({"tags": ["a", "b"]}, {"tags": []}), {"tags": []})

            def test_falsy_values_override(self):
                out = deep_merge({"a": 5, "b": True, "c": "x", "d": [1], "e": {"k": 1}}, {"a": 0, "b": False, "c": "", "d": [], "e": {}})
                self.assertEqual(out, {"a": 0, "b": False, "c": "", "d": [], "e": {"k": 1}})

            def test_none_means_not_given(self):
                out = deep_merge({"a": 1, "b": {"c": 2}}, {"a": None, "b": {"c": None, "d": None}, "z": None})
                self.assertEqual(out, {"a": 1, "b": {"c": 2}})

            def test_arguments_are_not_modified_and_nothing_is_shared(self):
                base = copy.deepcopy(DEFAULTS)
                over = {"db": {"port": 1}, "tags": ["z"], "extra": {"x": [1]}}
                snapshot_b, snapshot_o = copy.deepcopy(base), copy.deepcopy(over)
                out = deep_merge(base, over)
                self.assertEqual(base, snapshot_b)
                self.assertEqual(over, snapshot_o)
                out["db"]["pool"]["max"] = 99
                out["tags"].append("w")
                out["extra"]["x"].append(2)
                self.assertEqual(base, snapshot_b)
                self.assertEqual(over, snapshot_o)

            def test_type_change_replaces(self):
                self.assertEqual(deep_merge({"a": {"b": 1}}, {"a": 3}), {"a": 3})
                self.assertEqual(deep_merge({"a": 3}, {"a": {"b": 1}}), {"a": {"b": 1}})


        class Coercion(unittest.TestCase):
            def test_booleans(self):
                for text in ("1", "true", "TRUE", "Yes", "on", " ON "):
                    self.assertIs(coerce(text, False), True, text)
                for text in ("0", "false", "False", "no", "OFF", ""):
                    if text == "":
                        with self.assertRaises(ValueError):
                            coerce(text, True)
                    else:
                        self.assertIs(coerce(text, True), False, text)
                with self.assertRaises(ValueError):
                    coerce("maybe", True)

            def test_numbers_and_lists(self):
                self.assertEqual(coerce("12", 0), 12)
                self.assertEqual(coerce("0.25", 1.0), 0.25)
                self.assertEqual(coerce("a, b ,c", []), ["a", "b", "c"])
                self.assertEqual(coerce("", ["x"]), [])
                self.assertEqual(coerce("hello", "x"), "hello")
                with self.assertRaises(ValueError):
                    coerce("12abc", 0)


        class Environment(unittest.TestCase):
            def test_paths_are_lowercased_and_split(self):
                env = {"APP_DB__HOST": "db.internal", "APP_DB__POOL__MAX": "20", "APP_DEBUG": "false", "OTHER": "x", "APP_TAGS": "x,y"}
                self.assertEqual(from_env(env, DEFAULTS), {"db": {"host": "db.internal", "pool": {"max": 20}}, "debug": False, "tags": ["x", "y"]})

            def test_unknown_paths_stay_strings(self):
                self.assertEqual(from_env({"APP_NEW__THING": "42"}, DEFAULTS), {"new": {"thing": "42"}})

            def test_a_custom_prefix(self):
                self.assertEqual(from_env({"SVC_WORKERS": "8", "APP_WORKERS": "2"}, DEFAULTS, prefix="SVC_"), {"workers": 8})


        class CommandLine(unittest.TestCase):
            def test_parse(self):
                self.assertEqual(parse_cli(["--set", "db.port=6000", "--set", "debug=true", "--set", "name=hello", "--set", "tags=[1,2]"]),
                                 {"db": {"port": 6000}, "debug": True, "name": "hello", "tags": [1, 2]})

            def test_errors(self):
                for bad in (["--set"], ["--set", "novalue"], ["--put", "a=1"], ["a=1"]):
                    with self.assertRaises(ValueError, msg=bad):
                        parse_cli(bad)


        class Precedence(unittest.TestCase):
            def test_each_layer_beats_the_one_before(self):
                file_data = {"workers": 2, "name": "from-file", "db": {"host": "file-host"}}
                env = {"APP_WORKERS": "3", "APP_DB__HOST": "env-host"}
                cli = ["--set", "workers=5"]
                cfg = load(DEFAULTS, file_data, env, cli)
                self.assertEqual(cfg["workers"], 5)
                self.assertEqual(cfg["db"]["host"], "env-host")
                self.assertEqual(cfg["name"], "from-file")
                self.assertEqual(cfg["db"]["port"], 5432)
                cfg = load(DEFAULTS, file_data, env)
                self.assertEqual(cfg["workers"], 3)

            def test_environment_can_switch_things_off(self):
                cfg = load(DEFAULTS, env={"APP_DEBUG": "0", "APP_WORKERS": "0"})
                self.assertIs(cfg["debug"], False)
                self.assertEqual(cfg["workers"], 0)

            def test_loading_twice_gives_the_same_result_and_leaves_defaults_alone(self):
                defaults = copy.deepcopy(DEFAULTS)
                first = load(defaults, {"db": {"pool": {"max": 50}}, "tags": ["z"]}, {"APP_DB__PORT": "1"})
                second = load(defaults)
                self.assertEqual(defaults, DEFAULTS)
                self.assertEqual(second, DEFAULTS)
                first["db"]["pool"]["max"] = -1
                first["tags"].append("q")
                self.assertEqual(load(defaults), DEFAULTS)


        if __name__ == "__main__":
            unittest.main()
    '''),
}


def _a_prompts():
    p = {}
    p["env-vs-file"] = (
        "We set `APP_WORKERS=3` in the container to scale a service, but the value from `/etc/svc.json` (2) wins. The docs "
        "and the 12-factor guidance both say the environment beats the config file. Command-line flags do beat both, as expected."
    )
    p["bool-text"] = lambda c: (
        "`APP_DEBUG=false` leaves debug switched on. Others are right: `APP_DEBUG=0` also stays on. I printed what the "
        "coercion gives for the text \"false\": "
        + c.probe("from settings.coerce import coerce\nprint(coerce('false', True))\n")[1]
        + ". It must understand false/no/off/0."
    )
    p["falsy"] = (
        "There is no way to turn a feature off or set a number to zero from the environment or the file when the default is "
        "something else: `APP_WORKERS=0` and `\"debug\": false` in the JSON file are both ignored and the default stays. "
        "`None` is meant to be 'not given', but 0, False and empty strings are real values."
    )
    p["lists"] = (
        "The `tags` setting grows: with default `[\"a\", \"b\"]` and a config file that says `\"tags\": [\"c\"]` we get `a b c`. "
        "Overriding a list must replace it."
    )
    p["mutated-defaults"] = (
        "Heisenbug in the settings loader: the second request in a process sometimes sees the previous request's overrides. In the unit "
        "test I could reproduce it by loading twice with the same defaults dict: the defaults themselves had been changed by "
        "the first load. I did not find where."
    )
    p["env-case-and-mutation"] = (
        "Two things in the settings loader: environment variables for nested options (`APP_DB__HOST`) are silently ignored, "
        "and values from one `load()` call leak into later calls in the same process. The existing tests pass; they "
        "only use top-level lower-case names and a single load."
    )
    return p


def _base_a() -> Base:
    P = _a_prompts()
    good = {"README.md": A_README, "settings/__init__.py": '"""Layered settings."""\n', "settings/merge.py": A_MERGE,
            "settings/coerce.py": A_COERCE, "settings/loader.py": A_LOADER}
    mg, co, lo = "settings/merge.py", "settings/coerce.py", "settings/loader.py"
    mutate = ("    out = {k: _copy(v) for k, v in base.items()}\n    for key", "    out = base\n    for key")
    envcase = ("        path = [part.lower() for part in name[len(prefix):].split(\"__\") if part]\n", "        path = [part for part in name[len(prefix):].split(\"__\") if part]\n")
    bugs = [
        Bug("environment-below-file", 2, {lo: [("    cfg = deep_merge(defaults, file_data or {})\n    cfg = deep_merge(cfg, from_env(env or {}, defaults))\n",
                                                "    cfg = deep_merge(defaults, from_env(env or {}, defaults))\n    cfg = deep_merge(cfg, file_data or {})\n")]}, P["env-vs-file"]),
        Bug("bool-from-truthiness", 2, {co: [("        word = text.strip().lower()\n        if word in TRUE:\n            return True\n        if word in FALSE:\n            return False\n        raise ValueError(f\"not a boolean: {text!r}\")\n",
                                              "        return bool(text)\n")]}, P["bool-text"]),
        Bug("falsy-overrides-ignored", 2, {mg: [("        if value is None:\n            continue\n", "        if not value:\n            continue\n")]}, P["falsy"]),
        Bug("lists-are-concatenated", 2, {mg: [("        if isinstance(value, dict) and isinstance(out.get(key), dict):\n            out[key] = deep_merge(out[key], value)\n",
                                                "        if isinstance(value, dict) and isinstance(out.get(key), dict):\n            out[key] = deep_merge(out[key], value)\n        elif isinstance(value, list) and isinstance(out.get(key), list):\n            out[key] = out[key] + _copy(value)\n")]}, P["lists"]),
        Bug("merge-modifies-its-base", 4, {mg: [mutate]}, P["mutated-defaults"]),
        Bug("env-names-not-lowered-and-base-modified", 5, {mg: [mutate], lo: [envcase]}, P["env-case-and-mutation"]),
    ]
    return Base("settings", "python", good, A_VISIBLE, A_HIDDEN, bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base B (javascript): option merging for a CLI toolkit.
# ------------------------------------------------------------------------------------------------------------------

B_README = dd('''
    # optmerge

    Option handling for a command line toolkit (CommonJS).

    * `mergeConfig(...layers)` returns a new object: later layers override earlier ones. Plain objects merge recursively;
      arrays and every other value replace. `undefined` means "not given" and never overrides; **`null`, `0`, `false` and
      `''` are real values** and do override. The keys `__proto__`, `constructor` and `prototype` are ignored at every level
      (a parsed JSON file must not be able to alter `Object.prototype`). The result shares no object or array with any layer, and
      the layers are not modified.
    * `pick(obj, path, fallback)`: value at a dotted path (`'a.b.c'`); `fallback` is returned **only** when the path does not
      exist or its value is `undefined`: `null`, `0`, `false` and `''` are returned as they are.
''')

B_MERGE = dd('''
    'use strict';

    const FORBIDDEN = new Set(['__proto__', 'constructor', 'prototype']);

    function isPlain(v) {
      return v !== null && typeof v === 'object' && !Array.isArray(v);
    }

    function clone(v) {
      if (Array.isArray(v)) return v.map(clone);
      if (isPlain(v)) {
        const out = {};
        for (const k of Object.keys(v)) if (!FORBIDDEN.has(k)) out[k] = clone(v[k]);
        return out;
      }
      return v;
    }

    function mergeInto(target, layer) {
      for (const key of Object.keys(layer)) {
        if (FORBIDDEN.has(key)) continue;
        const value = layer[key];
        if (value === undefined) continue;
        if (isPlain(value) && isPlain(target[key])) mergeInto(target[key], value);
        else target[key] = clone(value);
      }
      return target;
    }

    function mergeConfig(...layers) {
      const out = {};
      for (const layer of layers) if (layer) mergeInto(out, layer);
      return out;
    }

    function pick(obj, path, fallback) {
      let node = obj;
      for (const part of path.split('.')) {
        if (node === null || node === undefined || !Object.prototype.hasOwnProperty.call(Object(node), part)) return fallback;
        node = node[part];
      }
      return node === undefined ? fallback : node;
    }

    module.exports = { mergeConfig, pick };
''')

B_VISIBLE = {
    "test/merge.test.js": dd('''
        const test = require('node:test');
        const assert = require('node:assert');
        const { mergeConfig, pick } = require('../src/merge');

        test('nested merge', () => {
          assert.deepStrictEqual(mergeConfig({ a: 1, b: { c: 2, d: 3 } }, { b: { c: 9 } }), { a: 1, b: { c: 9, d: 3 } });
        });

        test('pick', () => {
          assert.strictEqual(pick({ a: { b: 5 } }, 'a.b', 0), 5);
          assert.strictEqual(pick({}, 'a.b', 'dflt'), 'dflt');
        });
    '''),
}

B_HIDDEN = {
    "test/hidden_merge.test.js": dd('''
        const test = require('node:test');
        const assert = require('node:assert');
        const { mergeConfig, pick } = require('../src/merge');

        test('arrays are replaced, not merged index by index', () => {
          assert.deepStrictEqual(mergeConfig({ list: [1, 2, 3] }, { list: [9] }), { list: [9] });
          assert.deepStrictEqual(mergeConfig({ list: [1, 2, 3] }, { list: [] }), { list: [] });
          assert.deepStrictEqual(mergeConfig({ a: { list: ['x', 'y'] } }, { a: { list: ['z'] } }), { a: { list: ['z'] } });
        });

        test('undefined is not given, everything else is a value', () => {
          const out = mergeConfig({ a: 1, b: 2, c: 'x', d: true, e: { f: 1 } }, { a: undefined, b: 0, c: '', d: false, e: null });
          assert.deepStrictEqual(out, { a: 1, b: 0, c: '', d: false, e: null });
        });

        test('three layers, later wins', () => {
          assert.deepStrictEqual(mergeConfig({ a: 1, b: 1, c: 1 }, { b: 2, c: 2 }, { c: 3 }), { a: 1, b: 2, c: 3 });
          assert.deepStrictEqual(mergeConfig(), {});
          assert.deepStrictEqual(mergeConfig(undefined, { a: 1 }, null), { a: 1 });
        });

        test('forbidden keys cannot pollute prototypes', () => {
          const evil = JSON.parse('{"__proto__": {"polluted": "yes"}, "a": {"__proto__": {"deep": 1}, "ok": 1}, "constructor": {"prototype": {"c": 1}}}');
          const out = mergeConfig({}, evil);
          assert.strictEqual({}.polluted, undefined);
          assert.strictEqual({}.deep, undefined);
          assert.strictEqual({}.c, undefined);
          assert.strictEqual(Object.prototype.polluted, undefined);
          assert.deepStrictEqual(Object.keys(out), ['a']);
          assert.deepStrictEqual(out.a, { ok: 1 });
        });

        test('the result shares nothing with the layers and the layers stay as they were', () => {
          const base = { db: { opts: { retries: 3 }, hosts: ['a'] } };
          const over = { db: { extra: { x: [1] } } };
          const snapshot = JSON.stringify([base, over]);
          const out = mergeConfig(base, over);
          out.db.opts.retries = 99;
          out.db.hosts.push('b');
          out.db.extra.x.push(2);
          assert.strictEqual(JSON.stringify([base, over]), snapshot);
        });

        test('merging into an empty start copies nested objects too', () => {
          const layer = { a: { b: { c: 1 } } };
          const out = mergeConfig(layer);
          out.a.b.c = 2;
          assert.strictEqual(layer.a.b.c, 1);
        });

        test('pick returns the fallback only when nothing is there', () => {
          const obj = { a: { zero: 0, no: false, empty: '', nil: null, undef: undefined, deep: { x: 1 } } };
          assert.strictEqual(pick(obj, 'a.zero', 9), 0);
          assert.strictEqual(pick(obj, 'a.no', 9), false);
          assert.strictEqual(pick(obj, 'a.empty', 9), '');
          assert.strictEqual(pick(obj, 'a.nil', 9), null);
          assert.strictEqual(pick(obj, 'a.undef', 9), 9);
          assert.strictEqual(pick(obj, 'a.missing', 9), 9);
          assert.strictEqual(pick(obj, 'a.deep.x', 9), 1);
          assert.strictEqual(pick(obj, 'a.deep.x.y', 9), 9);
          assert.strictEqual(pick(obj, 'nope.deeper', 'f'), 'f');
          assert.strictEqual(pick({ a: null }, 'a.b', 'f'), 'f');
        });
    '''),
}


def _b_prompts():
    p = {}
    p["or-fallback"] = (
        "`pick(config, 'retry.count', 3)` returns 3 when the config says `retry.count: 0`, and `pick(config, 'cache.enabled', true)` "
        "returns true when the config explicitly disables the cache. The fallback is for missing values only."
    )
    p["arrays-by-index"] = (
        "Overriding a list option with a shorter list keeps the tail of the old one: base `hosts: ['a','b','c']` with an override "
        "`hosts: ['x']` gives `['x','b','c']`. An array in a later layer should replace the whole array."
    )
    p["proto"] = (
        "Security scan finding: loading a user-supplied JSON file through `mergeConfig` can set properties on `Object.prototype` "
        "(`{\"__proto__\": {\"isAdmin\": true}}` makes every object `isAdmin`). The README says those keys are ignored at every level. "
        "Please fix it; the visible tests do not cover it."
    )
    p["undefined-wins"] = (
        "Options passed as `{ verbose: undefined }` (from optional CLI flags that were not given) wipe out the default: the "
        "merged config has `verbose: undefined`. `undefined` is supposed to mean 'not given', whereas `null`, `0`, `false` and "
        "`''` are real values."
    )
    return p


def _base_b() -> Base:
    P = _b_prompts()
    good = {"README.md": B_README, "src/merge.js": B_MERGE, "package.json": '{\n  "name": "optmerge",\n  "version": "1.0.0",\n  "private": true\n}\n'}
    m = "src/merge.js"
    bugs = [
        Bug("pick-uses-or", 2, {m: [("  return node === undefined ? fallback : node;\n", "  return node || fallback;\n")]}, P["or-fallback"]),
        Bug("arrays-merged-by-index", 3, {m: [("    if (isPlain(value) && isPlain(target[key])) mergeInto(target[key], value);\n    else target[key] = clone(value);\n",
                                                "    if ((isPlain(value) && isPlain(target[key])) || (Array.isArray(value) && Array.isArray(target[key]))) mergeInto(target[key], value);\n    else target[key] = clone(value);\n")]}, P["arrays-by-index"]),
        Bug("undefined-overrides", 1, {m: [("    if (value === undefined) continue;\n", "")]}, P["undefined-wins"]),
        Bug("prototype-keys-allowed", 4, {m: [("const FORBIDDEN = new Set(['__proto__', 'constructor', 'prototype']);", "const FORBIDDEN = new Set([]);")]}, P["proto"]),
    ]
    return Base("optmerge", "javascript", good, B_VISIBLE, B_HIDDEN, bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base C (ruby): config helpers.
# ------------------------------------------------------------------------------------------------------------------

C_README = dd('''
    # cfgkit

    Configuration helpers (Ruby 3, minitest).

    * `Cfg.deep_merge(base, over)`: a new Hash. Keys are normalised to Strings (symbols become strings) at every level. Hashes merge
      recursively, any other value in `over` replaces; `nil` in `over` is "not given". Neither argument is modified.
    * `Cfg.to_int(text)`: the Integer written in `text` (surrounding whitespace allowed, optional sign, decimal digits only);
      anything else (`"12abc"`, `""`, `"1.5"`, `"0x1A"`) raises `ArgumentError`. Leading zeros are decimal (`"08"` is 8).
    * `Cfg.fetch(config, path, default = nil)`: value at a dotted path in a String-keyed config; `default` is returned only when the
      path is missing; `false`, `0`, `""` and `nil` values stored in the config are returned as they are.
''')

C_CFG = dd('''
    module Cfg
      def self.stringify(value)
        return value unless value.is_a?(Hash)

        value.each_with_object({}) { |(k, v), out| out[k.to_s] = stringify(v) }
      end

      def self.deep_merge(base, over)
        out = stringify(base)
        over.each do |key, value|
          next if value.nil?

          key = key.to_s
          if value.is_a?(Hash) && out[key].is_a?(Hash)
            out[key] = deep_merge(out[key], value)
          else
            out[key] = stringify(value)
          end
        end
        out
      end

      def self.to_int(text)
        Integer(text.strip, 10)
      end

      def self.fetch(config, path, default = nil)
        node = config
        path.split(".").each do |part|
          return default unless node.is_a?(Hash) && node.key?(part)

          node = node[part]
        end
        node
      end
    end
''')

C_MAIN = 'require "cfg"\n'

C_VISIBLE = {
    "test/test_basic.rb": dd('''
        require "minitest/autorun"
        require "cfg"

        class TestBasic < Minitest::Test
          def test_merge
            assert_equal({ "a" => 1, "b" => { "c" => 3, "d" => 4 } }, Cfg.deep_merge({ "a" => 1, "b" => { "c" => 2, "d" => 4 } }, { "b" => { "c" => 3 } }))
          end

          def test_to_int
            assert_equal 42, Cfg.to_int(" 42 ")
          end

          def test_fetch
            assert_equal 5, Cfg.fetch({ "a" => { "b" => 5 } }, "a.b")
          end
        end
    '''),
}

C_HIDDEN = {
    "test/test_hidden_cfg.rb": dd('''
        require "minitest/autorun"
        require "cfg"

        class TestHiddenCfg < Minitest::Test
          def test_nested_hashes_merge_recursively
            base = { "db" => { "host" => "h", "pool" => { "min" => 1, "max" => 5 } } }
            out = Cfg.deep_merge(base, { "db" => { "pool" => { "max" => 9 } } })
            assert_equal({ "db" => { "host" => "h", "pool" => { "min" => 1, "max" => 9 } } }, out)
          end

          def test_symbol_and_string_keys_are_the_same_key
            out = Cfg.deep_merge({ db: { host: "h", port: 1 } }, { "db" => { "port" => 2 }, name: "x" })
            assert_equal({ "db" => { "host" => "h", "port" => 2 }, "name" => "x" }, out)
          end

          def test_nil_is_not_given_and_falsy_values_override
            out = Cfg.deep_merge({ "a" => 1, "b" => true, "c" => "x" }, { "a" => nil, "b" => false, "c" => "", "d" => nil })
            assert_equal({ "a" => 1, "b" => false, "c" => "" }, out)
          end

          def test_arguments_are_not_modified
            base = { "db" => { "host" => "h" }, "tags" => ["a"] }
            over = { "db" => { "port" => 1 } }
            snap = Marshal.dump([base, over])
            out = Cfg.deep_merge(base, over)
            out["db"]["host"] = "changed"
            assert_equal snap, Marshal.dump([base, over])
          end

          def test_merging_twice_gives_the_same_result
            defaults = { "db" => { "host" => "h" } }
            first = Cfg.deep_merge(defaults, { "db" => { "host" => "x" } })
            second = Cfg.deep_merge(defaults, {})
            assert_equal "x", first["db"]["host"]
            assert_equal({ "db" => { "host" => "h" } }, second)
            assert_equal({ "db" => { "host" => "h" } }, defaults)
          end

          def test_to_int_accepts_only_integers
            assert_equal 12, Cfg.to_int("12")
            assert_equal(-7, Cfg.to_int(" -7 "))
            assert_equal 8, Cfg.to_int("08")
            assert_equal 5, Cfg.to_int("+5")
            ["12abc", "", "1.5", "0x1A", "abc", "1 2", " "].each do |bad|
              assert_raises(ArgumentError, bad.inspect) { Cfg.to_int(bad) }
            end
          end

          def test_fetch_returns_stored_falsy_values
            cfg = { "a" => { "zero" => 0, "no" => false, "empty" => "", "nil" => nil, "deep" => { "x" => 1 } } }
            assert_equal 0, Cfg.fetch(cfg, "a.zero", 9)
            assert_equal false, Cfg.fetch(cfg, "a.no", 9)
            assert_equal "", Cfg.fetch(cfg, "a.empty", 9)
            assert_nil Cfg.fetch(cfg, "a.nil", 9)
            assert_equal 1, Cfg.fetch(cfg, "a.deep.x", 9)
            assert_equal 9, Cfg.fetch(cfg, "a.missing", 9)
            assert_equal 9, Cfg.fetch(cfg, "a.deep.x.y", 9)
            assert_equal "d", Cfg.fetch(cfg, "nope.deeper", "d")
            assert_nil Cfg.fetch(cfg, "a.missing")
          end
        end
    '''),
}


def _c_prompts():
    p = {}
    p["shallow"] = (
        "Overriding one nested option wipes its siblings: base `{db: {host: h, port: 1}}` plus override `{db: {port: 2}}` gives "
        "`{db: {port: 2}}`, the host is gone. Nested hashes are supposed to merge."
    )
    p["to-i"] = (
        "A typo in an environment variable (`WORKERS=12abc`) silently becomes 12, and `WORKERS=` (empty) becomes 0 and starts "
        "zero workers. Integer parsing should be strict and raise `ArgumentError` for anything that is not a decimal integer."
    )
    p["fetch-or"] = (
        "`Cfg.fetch(config, 'cache.enabled', true)` returns true although the config says `cache.enabled: false`; likewise a "
        "configured `0` comes back as the default. Defaults are for missing keys only."
    )
    return p


def _base_c() -> Base:
    P = _c_prompts()
    good = {"README.md": C_README, "lib/cfg.rb": C_CFG}
    f = "lib/cfg.rb"
    bugs = [
        Bug("hashes-not-merged-deeply", 2, {f: [("      if value.is_a?(Hash) && out[key].is_a?(Hash)\n        out[key] = deep_merge(out[key], value)\n      else\n        out[key] = stringify(value)\n      end\n",
                                                 "      out[key] = stringify(value)\n")]}, P["shallow"]),
        Bug("to-int-is-lenient", 2, {f: [("    Integer(text.strip, 10)\n", "    text.to_i\n")]}, P["to-i"]),
        Bug("fetch-falls-back-on-falsy", 2, {f: [("    node\n  end\nend\n", "    node || default\n  end\nend\n")]}, P["fetch-or"]),
    ]
    return Base("cfgkit", "ruby", good, C_VISIBLE, C_HIDDEN, bugs)


@family("fix-hand-config-merge", category="fix", lang="python", kind="fix", n=13,
        summary="layered configuration: precedence, coercion, falsy values and aliasing (python settings, js option merger, ruby helpers)")
def gen(rng, n):
    return tasks_from([_base_a(), _base_b(), _base_c()])
