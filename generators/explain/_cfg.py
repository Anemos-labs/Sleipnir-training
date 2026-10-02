"""Layered configuration loaders (python, javascript, go, ruby) with INI-like files, environment variables and command-line overrides.

The precedence order, the locked keys, which files exist and the names of the layers are all decided by the generated code, not by the README.
Truth is simulated here and checked against the real loader (the generated program is run with the scenario)."""
from __future__ import annotations

import random
from dataclasses import dataclass

import fx

from . import _ir as I

SECTIONS = {
    "db": ["host", "port", "pool_size", "timeout_ms", "retries"],
    "http": ["timeout_ms", "max_body_kb", "keepalive_s", "workers"],
    "cache": ["ttl_s", "max_items", "shards"],
    "log": ["level", "sample_pct", "retain_days"],
    "queue": ["depth", "batch", "visibility_s"],
    "limits": ["burst", "per_minute", "daily"],
}
LEVELS = ["debug", "info", "warn", "error"]
ENVS = ["dev", "staging", "prod", "qa", "canary"]
LAYER_ORDER_POOL = ["site", "env", "local", "environ", "cli"]


@dataclass
class Cfg:
    lang: str
    name: str
    keys: list                      # dotted keys, definition order
    files: dict                     # layer -> {key: value}   (file layers only)
    present: dict                   # layer -> bool (file exists in the repo)
    layers: list                    # precedence, lowest first
    locked: list
    env_name: str                   # default APP_ENV when unset
    layer_label: dict               # layer -> name as written in the code
    noun: str


def make_cfg(rng: random.Random, lang: str, tier: int) -> Cfg:
    dom = rng.choice(I.DOMAINS)
    secs = rng.sample(sorted(SECTIONS), {1: 2, 2: 2, 3: 3, 4: 4, 5: 5}[tier])
    keys = []
    for s in secs:
        for k in rng.sample(SECTIONS[s], rng.randint(2, min(4, len(SECTIONS[s])))):
            keys.append(f"{s}.{k}")
    nlayers = {1: 2, 2: 3, 3: 4, 4: 5, 5: 5}[tier]
    pool = ["env", "environ", "cli", "site", "local"]
    chosen = ["env", "cli", "environ"] if tier >= 2 else ["env", "cli"]
    if tier >= 3:
        chosen.append("site")
    if tier >= 4:
        chosen.append("local")
    chosen = chosen[:nlayers] if tier < 3 else chosen
    order = list(chosen)
    rng.shuffle(order)
    layers = ["defaults"] + order
    env_name = rng.choice(["dev", "staging", "prod"])
    files = {}
    present = {}
    all_layers = [l for l in layers if l in ("defaults", "site", "env", "local")]

    def val(key):
        if key.endswith("level"):
            return rng.choice(LEVELS)
        if key.endswith(".host"):
            return rng.choice(["db1.internal", "db2.internal", "10.0.4.7", "pg.local", "10.0.9.2"])
        return str(rng.randint(2, 900))

    for l in all_layers:
        present[l] = True
        if l == "defaults":
            files[l] = {k: val(k) for k in keys}
        else:
            n = rng.randint(max(2, len(keys) // 3), max(3, (2 * len(keys)) // 3))
            files[l] = {k: val(k) for k in rng.sample(keys, min(n, len(keys)))}
    if "local" in layers and rng.random() < 0.5:
        present["local"] = False       # gitignored: referenced by the loader but not in the repo
        files["local"] = {}
    locked = []
    if tier >= 3:
        locked = rng.sample([k for k in keys if k.endswith(("host", "level", "port", "workers", "ttl_s", "retries"))] or keys[:1], 1)
    label = {"defaults": "defaults", "site": rng.choice(["site", "shared", "site"]), "env": rng.choice(["env", "stage", "env"]), "local": rng.choice(["local", "dev_overrides", "local"]),
             "environ": rng.choice(["environ", "process_env", "environ"]), "cli": rng.choice(["cli", "flags", "cli"])}
    return Cfg(lang, dom.name, keys, files, present, layers, locked, env_name, label, dom.title)


def scenario(rng: random.Random, c: Cfg, tier: int) -> dict:
    env = rng.choice([e for e in ENVS if e != c.env_name] + [c.env_name]) if rng.random() < 0.7 else None
    environ: dict = {}
    cli: dict = {}
    n_env = rng.randint(1, 1 + tier // 2)
    n_cli = rng.randint(1, 1 + tier // 2)
    for k in rng.sample(c.keys, min(n_env, len(c.keys))):
        environ[k] = _newval(rng, k)
    for k in rng.sample(c.keys, min(n_cli, len(c.keys))):
        cli[k] = _newval(rng, k)
    return {"app_env": env, "environ": environ, "cli": cli}


def _newval(rng, k):
    if k.endswith("level"):
        return rng.choice(LEVELS)
    if k.endswith(".host"):
        return rng.choice(["replica.internal", "10.1.1.9", "pg-ro.local"])
    return str(rng.randint(2, 900))


def simulate(c: Cfg, sc: dict, env_files: dict) -> tuple:
    """(values, provenance): the effective value of every key and the layer that supplied it"""
    env = sc["app_env"] or c.env_name
    sources = {"defaults": c.files["defaults"], "site": c.files.get("site", {}), "local": c.files.get("local", {}) if c.present.get("local", False) else {},
               "env": env_files.get(env, {}), "environ": sc["environ"], "cli": sc["cli"]}
    sources = {k: dict(v) for k, v in sources.items()}
    vals: dict = {}
    prov: dict = {}
    for layer in c.layers:
        for k, v in sources.get(layer, {}).items():
            if k in c.locked and layer in ("environ", "cli"):
                continue
            vals[k] = v
            prov[k] = c.layer_label[layer]
    return vals, prov


def env_files_for(rng, c: Cfg) -> dict:
    """the per-environment files: env name -> {key: value}; the dev/staging/prod trio, each overriding a few keys"""
    out = {}
    names = ["dev", "staging", "prod"]
    for n in names:
        sub = rng.sample(c.keys, rng.randint(2, max(2, len(c.keys) // 2)))
        out[n] = {k: (rng.choice(LEVELS) if k.endswith("level") else (rng.choice(["db1.internal", "db3.internal"]) if k.endswith(".host") else str(rng.randint(2, 900)))) for k in sub}
    return out


def _ini(values: dict, title: str) -> str:
    by: dict = {}
    for k, v in values.items():
        s, kk = k.split(".", 1)
        by.setdefault(s, []).append((kk, v))
    out = [f"# {title}"]
    for s, kv in by.items():
        out.append("")
        out.append(f"[{s}]")
        out += [f"{k} = {v}" for k, v in kv]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------------------------------------------- code
def render(c: Cfg, env_files: dict) -> dict:
    files = {}
    files["config/defaults.ini"] = _ini(c.files["defaults"], "Built-in defaults")
    if "site" in c.layers:
        files["config/site.ini"] = _ini(c.files["site"], "Settings shared by every environment")
    for n, vals in env_files.items():
        files[f"config/{n}.ini"] = _ini(vals, f"Overrides for {n}")
    if "local" in c.layers and c.present["local"]:
        files["config/local.ini"] = _ini(c.files["local"], "Developer overrides (not committed upstream)")
    layer_names = ", ".join(f'"{c.layer_label[l]}"' for l in c.layers)
    lock = ", ".join(f'"{k}"' for k in c.locked)
    files.update({"python": _py, "javascript": _js, "go": _go, "ruby": _rb}[c.lang](c, layer_names, lock))
    files["README.md"] = (f"# {c.noun} settings\n\nSettings are read from the INI-style files in `config/`, from `APP_*` environment variables and from `--set key=value` flags.\n"
                          f"Run the program to print the effective configuration; the loader source says how the pieces are combined.\n")
    return files


def _lab(c, l):
    return c.layer_label[l]


def _py(c, layer_names, lock):
    lab = {l: _lab(c, l) for l in ("defaults", "site", "env", "local", "environ", "cli")}
    code = f'''"""Layered settings: files, environment, command line."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "config"
LOCKED = {{{lock}}}
LAYERS = [{layer_names}]  # lowest priority first


def read_ini(path):
    values = {{}}
    section = ""
    if not path.exists():
        return values
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("["):
            section = line[1:-1].strip()
            continue
        key, _, value = line.partition("=")
        values[f"{{section}}.{{key.strip()}}"] = value.strip()
    return values


def from_environ(known):
    found = {{}}
    for name in known:
        var = "APP_" + name.replace(".", "_").upper()
        if var in os.environ:
            found[name] = os.environ[var]
    return found


def from_cli(argv):
    found = {{}}
    i = 0
    while i < len(argv):
        if argv[i] == "--set" and i + 1 < len(argv):
            key, _, value = argv[i + 1].partition("=")
            found[key] = value
            i += 1
        i += 1
    return found


def load(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    env = os.environ.get("APP_ENV", "{c.env_name}")
    defaults = read_ini(ROOT / "defaults.ini")
    sources = {{
        "{lab['defaults']}": defaults,
        "{lab['site']}": read_ini(ROOT / "site.ini"),
        "{lab['env']}": read_ini(ROOT / f"{{env}}.ini"),
        "{lab['local']}": read_ini(ROOT / "local.ini"),
        "{lab['environ']}": from_environ(defaults),
        "{lab['cli']}": from_cli(argv),
    }}
    merged = {{}}
    for layer in LAYERS:
        for key, value in sources[layer].items():
            if key in LOCKED and layer in ("{lab['environ']}", "{lab['cli']}"):
                continue
            merged[key] = value
    return merged
'''
    main = '"""Prints the effective configuration."""\nfrom .config import load\n\nfor key, value in sorted(load().items()):\n    print(f"{key}={value}")\n'
    return {f"app/__init__.py": "", "app/config.py": code, "app/__main__.py": main}


def _js(c, layer_names, lock):
    lab = {l: _lab(c, l) for l in ("defaults", "site", "env", "local", "environ", "cli")}
    code = f'''\'use strict\';

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..', 'config');
const LOCKED = new Set([{lock}]);
const LAYERS = [{layer_names}]; // lowest priority first

function readIni(file) {{
  const values = {{}};
  if (!fs.existsSync(file)) {{
    return values;
  }}
  let section = '';
  for (const raw of fs.readFileSync(file, 'utf8').split('\\n')) {{
    const line = raw.split('#')[0].trim();
    if (!line) {{
      continue;
    }}
    if (line.startsWith('[')) {{
      section = line.slice(1, -1).trim();
      continue;
    }}
    const at = line.indexOf('=');
    values[`${{section}}.${{line.slice(0, at).trim()}}`] = line.slice(at + 1).trim();
  }}
  return values;
}}

function fromEnviron(known) {{
  const found = {{}};
  for (const name of Object.keys(known)) {{
    const variable = 'APP_' + name.replace('.', '_').toUpperCase();
    if (variable in process.env) {{
      found[name] = process.env[variable];
    }}
  }}
  return found;
}}

function fromCli(argv) {{
  const found = {{}};
  for (let i = 0; i < argv.length; i++) {{
    if (argv[i] === '--set' && i + 1 < argv.length) {{
      const at = argv[i + 1].indexOf('=');
      found[argv[i + 1].slice(0, at)] = argv[i + 1].slice(at + 1);
      i++;
    }}
  }}
  return found;
}}

function load(argv = process.argv.slice(2)) {{
  const env = process.env.APP_ENV || '{c.env_name}';
  const defaults = readIni(path.join(ROOT, 'defaults.ini'));
  const sources = {{
    '{lab['defaults']}': defaults,
    '{lab['site']}': readIni(path.join(ROOT, 'site.ini')),
    '{lab['env']}': readIni(path.join(ROOT, `${{env}}.ini`)),
    '{lab['local']}': readIni(path.join(ROOT, 'local.ini')),
    '{lab['environ']}': fromEnviron(defaults),
    '{lab['cli']}': fromCli(argv),
  }};
  const merged = {{}};
  for (const layer of LAYERS) {{
    for (const [key, value] of Object.entries(sources[layer])) {{
      if (LOCKED.has(key) && (layer === '{lab['environ']}' || layer === '{lab['cli']}')) {{
        continue;
      }}
      merged[key] = value;
    }}
  }}
  return merged;
}}

module.exports = {{ load, readIni }};
'''
    main = "'use strict';\n\nconst { load } = require('./config');\n\nconst merged = load();\nfor (const key of Object.keys(merged).sort()) {\n  console.log(`${key}=${merged[key]}`);\n}\n"
    return {"src/config.js": code, "src/main.js": main, "package.json": f'{{\n  "name": "{c.name}",\n  "version": "1.0.0"\n}}\n'}


def _go(c, layer_names, lock):
    lab = {l: _lab(c, l) for l in ("defaults", "site", "env", "local", "environ", "cli")}
    lockset = ", ".join(f'"{k}": true' for k in c.locked)
    code = f'''package main

import (
	"os"
	"path/filepath"
	"strings"
)

var locked = map[string]bool{{{lockset}}}

// layers lists the sources, lowest priority first.
var layers = []string{{{layer_names}}}

func readINI(path string) map[string]string {{
	values := map[string]string{{}}
	data, err := os.ReadFile(path)
	if err != nil {{
		return values
	}}
	section := ""
	for _, raw := range strings.Split(string(data), "\\n") {{
		line := strings.TrimSpace(strings.SplitN(raw, "#", 2)[0])
		if line == "" {{
			continue
		}}
		if strings.HasPrefix(line, "[") {{
			section = strings.TrimSpace(line[1 : len(line)-1])
			continue
		}}
		parts := strings.SplitN(line, "=", 2)
		values[section+"."+strings.TrimSpace(parts[0])] = strings.TrimSpace(parts[1])
	}}
	return values
}}

func fromEnviron(known map[string]string) map[string]string {{
	found := map[string]string{{}}
	for name := range known {{
		variable := "APP_" + strings.ToUpper(strings.ReplaceAll(name, ".", "_"))
		if value, ok := os.LookupEnv(variable); ok {{
			found[name] = value
		}}
	}}
	return found
}}

func fromCLI(args []string) map[string]string {{
	found := map[string]string{{}}
	for i := 0; i < len(args); i++ {{
		if args[i] == "--set" && i+1 < len(args) {{
			parts := strings.SplitN(args[i+1], "=", 2)
			found[parts[0]] = parts[1]
			i++
		}}
	}}
	return found
}}

func load(args []string) map[string]string {{
	root := filepath.Join("config")
	env := os.Getenv("APP_ENV")
	if env == "" {{
		env = "{c.env_name}"
	}}
	defaults := readINI(filepath.Join(root, "defaults.ini"))
	sources := map[string]map[string]string{{
		"{lab['defaults']}": defaults,
		"{lab['site']}":     readINI(filepath.Join(root, "site.ini")),
		"{lab['env']}":      readINI(filepath.Join(root, env+".ini")),
		"{lab['local']}":    readINI(filepath.Join(root, "local.ini")),
		"{lab['environ']}":  fromEnviron(defaults),
		"{lab['cli']}":      fromCLI(args),
	}}
	merged := map[string]string{{}}
	for _, layer := range layers {{
		for key, value := range sources[layer] {{
			if locked[key] && (layer == "{lab['environ']}" || layer == "{lab['cli']}") {{
				continue
			}}
			merged[key] = value
		}}
	}}
	return merged
}}
'''
    main = '''package main

import (
	"fmt"
	"os"
	"sort"
)

func main() {
	merged := load(os.Args[1:])
	keys := make([]string, 0, len(merged))
	for k := range merged {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		fmt.Printf("%s=%s\\n", k, merged[k])
	}
}
'''
    return {"go.mod": f"module example.com/{c.name}\n\ngo 1.21\n", "config.go": code, "main.go": main}


def _rb(c, layer_names, lock):
    lab = {l: _lab(c, l) for l in ("defaults", "site", "env", "local", "environ", "cli")}
    lockset = ", ".join(f"'{k}'" for k in c.locked)
    code = f'''# frozen_string_literal: true

module Settings
  ROOT = File.expand_path('../config', __dir__)
  LOCKED = [{lockset}].freeze
  LAYERS = [{layer_names.replace('"', "'")}].freeze # lowest priority first

  def self.read_ini(path)
    values = {{}}
    return values unless File.exist?(path)

    section = ''
    File.readlines(path).each do |raw|
      line = raw.split('#', 2).first.to_s.strip
      next if line.empty?

      if line.start_with?('[')
        section = line[1..-2].strip
        next
      end
      key, value = line.split('=', 2)
      values["#{{section}}.#{{key.strip}}"] = value.strip
    end
    values
  end

  def self.from_environ(known)
    known.keys.each_with_object({{}}) do |name, found|
      var = 'APP_' + name.tr('.', '_').upcase
      found[name] = ENV[var] if ENV.key?(var)
    end
  end

  def self.from_cli(argv)
    found = {{}}
    i = 0
    while i < argv.length
      if argv[i] == '--set' && i + 1 < argv.length
        key, value = argv[i + 1].split('=', 2)
        found[key] = value
        i += 1
      end
      i += 1
    end
    found
  end

  def self.load(argv)
    env = ENV.fetch('APP_ENV', '{c.env_name}')
    defaults = read_ini(File.join(ROOT, 'defaults.ini'))
    sources = {{
      '{lab['defaults']}' => defaults,
      '{lab['site']}' => read_ini(File.join(ROOT, 'site.ini')),
      '{lab['env']}' => read_ini(File.join(ROOT, "#{{env}}.ini")),
      '{lab['local']}' => read_ini(File.join(ROOT, 'local.ini')),
      '{lab['environ']}' => from_environ(defaults),
      '{lab['cli']}' => from_cli(argv)
    }}
    merged = {{}}
    LAYERS.each do |layer|
      sources[layer].each do |key, value|
        next if LOCKED.include?(key) && ['{lab['environ']}', '{lab['cli']}'].include?(layer)

        merged[key] = value
      end
    end
    merged
  end
end
'''
    main = "#!/usr/bin/env ruby\n# frozen_string_literal: true\n\nrequire_relative '../lib/settings'\n\nSettings.load(ARGV).sort.each { |key, value| puts \"#{key}=#{value}\" }\n"
    return {"lib/settings.rb": code, "bin/app": main}


CMD = {"python": "python3 -m app", "javascript": "node src/main.js", "go": "go run .", "ruby": "ruby bin/app"}


def command(c: Cfg, sc: dict) -> str:
    """the shell command line (with environment variables) for a scenario"""
    envs = []
    if sc["app_env"]:
        envs.append(f"APP_ENV={sc['app_env']}")
    for k, v in sc["environ"].items():
        envs.append("APP_" + k.replace(".", "_").upper() + f"={v}")
    flags = " ".join(f"--set {k}={v}" for k, v in sc["cli"].items())
    return " ".join(envs + [CMD[c.lang]] + ([flags] if flags else []))


def run_real(c: Cfg, files: dict, sc: dict) -> dict:
    res = fx.run(files, command(c, sc) + " 2>/dev/null", timeout=60)
    if not res.ok:
        raise RuntimeError(res.out[-300:])
    return dict(ln.split("=", 1) for ln in res.out.strip().split("\n") if "=" in ln)
