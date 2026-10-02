"""Configuration drift: one environment's config file has a subtle defect; the app logs show the consequence.

A small service (three skins) reads ``config/base.<ext>`` overlaid by ``config/<env>.<ext>``.  The configuration formats are INI,
JSON, TOML and dotenv.  One environment's file carries a defect (misspelt key, number given as text, wrong unit, transposed port,
a reference to a secret under a misspelt name, a stray slash ...).  The simulated service raises the error such a value would
really cause; the run logs of the failing environment and of a healthy one are part of the task.
"""
from __future__ import annotations

import json
import random

from fx import Task, dd, run
from fx.run import merged

from ._engine import KINDS, accepted, hidden_diag

EXT = {"ini": "ini", "json": "json", "toml": "toml", "env": "env"}

LOADERS = {
    "ini": dd('''
        import configparser


        def _parse(path):
            cp = configparser.ConfigParser()
            cp.optionxform = str
            with open(path, encoding="utf-8") as fh:
                cp.read_file(fh)
            return {k: _coerce(v) for k, v in cp["settings"].items()}


        def _coerce(text):
            low = text.strip().lower()
            if low in ("true", "false"):
                return low == "true"
            for conv in (int, float):
                try:
                    return conv(text)
                except ValueError:
                    pass
            return text.strip()
    '''),
    "json": dd('''
        import json


        def _parse(path):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
    '''),
    "toml": dd('''
        import tomllib


        def _parse(path):
            with open(path, "rb") as fh:
                return tomllib.load(fh)
    '''),
    "env": dd('''
        def _parse(path):
            out = {}
            with open(path, encoding="utf-8") as fh:
                for raw in fh:
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    key, _, value = line.partition("=")
                    out[key.strip()] = _coerce(value.strip().strip('"'))
            return out


        def _coerce(text):
            low = text.lower()
            if low in ("true", "false"):
                return low == "true"
            for conv in (int, float):
                try:
                    return conv(text)
                except ValueError:
                    pass
            return text
    '''),
}

CONFIG_PY = '''"""Configuration loading: config/base.{ext} overlaid by config/<env>.{ext}; ${{VAR}} references are resolved from the environment."""
import os
import re

{loader}

class ConfigError(Exception):
    """The configuration cannot be used."""


def _expand(value):
    if not isinstance(value, str):
        return value

    def sub(m):
        name = m.group(1)
        if name not in os.environ:
            raise ConfigError(f"environment variable {{name}} is not set (referenced as ${{{{{{name}}}}}})")
        return os.environ[name]

    return re.sub(r"\\$\\{{(\\w+)\\}}", sub, value)


def load(env):
    cfg = {{}}
    for name in ("base", env):
        cfg.update(_parse(f"config/{{name}}.{ext}"))
    return {{k: _expand(v) for k, v in cfg.items()}}
'''

RUN_PY = '''"""Entry point: python3 run.py ENV   (the scheduler provides the secrets listed in SECRETS)."""
import os
import sys

from {pkg} import service
from {pkg}.config import ConfigError, load

SECRETS = {secrets}


def main(env):
    os.environ.update(SECRETS)
    try:
        cfg = load(env)
    except ConfigError as exc:
        print(f"[{{env}}] cannot load configuration: {{exc}}")
        return 2
    print(f"[{{env}}] loaded {{len(cfg)}} settings")
    service.{entry}(cfg, lambda m: print(f"[{{env}}] {{m}}"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
'''

# ---- skins ----------------------------------------------------------------------------------------------------------

MAIL_SERVICE = dd('''
    """Sends the nightly digest through the SMTP relay named in the configuration."""
    import socket
    import ssl

    WORLD = {("smtp.example.org", 587): "starttls", ("smtp.example.org", 465): "tls", ("relay.internal", 25): "plain"}


    class SMTPError(Exception):
        pass


    def send_digest(cfg, log):
        host = cfg.get("smtp_host", "localhost")
        port = int(cfg.get("smtp_port", 25))
        use_tls = cfg.get("use_tls", False)
        timeout = float(cfg.get("timeout_s", 30))
        log(f"connecting to {host}:{port} tls={use_tls} timeout={timeout:g}s")
        if timeout > 600:
            raise SMTPError(f"timeout of {timeout:g} s exceeds the 600 s job budget")
        mode = WORLD.get((host, port))
        if mode is None:
            if host not in {h for h, _ in WORLD} and host != "localhost":
                raise socket.gaierror(-2, f"Name or service not known: {host!r}")
            raise ConnectionRefusedError(111, f"Connection refused: {host}:{port}")
        if use_tls and mode == "plain":
            raise ssl.SSLError(1, "[SSL: WRONG_VERSION_NUMBER] wrong version number")
        if not use_tls and mode != "plain":
            raise SMTPError("530 5.7.0 Must issue a STARTTLS command first")
        log(f"authenticated as {cfg['from_address']}, sending digest")
        log("digest sent")
''')

MAIL_ENVS = {
    "dev": {"smtp_host": "relay.internal", "smtp_port": 25, "use_tls": False},
    "staging": {"smtp_host": "smtp.example.org", "smtp_port": 587, "use_tls": True, "password": "${SMTP_PASSWORD}"},
    "prod": {"smtp_host": "smtp.example.org", "smtp_port": 465, "use_tls": True, "password": "${SMTP_PASSWORD}"},
    "canary": {"smtp_host": "smtp.example.org", "smtp_port": 587, "use_tls": True, "password": "${SMTP_PASSWORD}"},
}
MAIL_BASE = {"from_address": "digest@lindenrow.example", "retry_limit": 3, "timeout_s": 30}

REPORT_SERVICE = dd('''
    """Builds the nightly sales report from the database named in the configuration."""
    import os

    WORLD = {("db-dev", 5432), ("db-stg", 5432), ("db-prod", 5432)}
    WRITABLE = {"./out", "/srv/reports"}
    ROWS = 2_000_000


    def build_report(cfg, log):
        url = cfg["db_url"]
        host, _, rest = url.split("@", 1)[1].partition(":")
        port = int(rest.split("/")[0])
        batch = cfg.get("batch_size")
        if batch is None:
            batch = 1
            log("batch_size not set, using the default of 1")
        out_dir = cfg.get("output_dir", "")
        log(f"connecting to {host}:{port}, batch_size={batch}, output_dir={out_dir!r}")
        if (host, port) not in WORLD:
            raise ConnectionRefusedError(111, f"Connection refused: {host}:{port}")
        if batch <= 0:
            raise ValueError("batch_size must be positive")
        if out_dir not in WRITABLE:
            raise PermissionError(13, f"Permission denied: {out_dir!r}")
        seconds = (ROWS // batch) * 0.2
        if seconds > 300:
            raise TimeoutError(f"report would need about {seconds:.0f} s, the job budget is 300 s")
        log(f"report written to {out_dir}/sales.csv ({ROWS} rows in {seconds:.0f} s)")
''')

REPORT_ENVS = {
    "dev": {"db_url": "postgres://reports:${REPORTS_DB_PASSWORD}@db-dev:5432/reports", "output_dir": "./out"},
    "staging": {"db_url": "postgres://reports:${REPORTS_DB_PASSWORD}@db-stg:5432/reports", "output_dir": "/srv/reports"},
    "prod": {"db_url": "postgres://reports:${REPORTS_DB_PASSWORD}@db-prod:5432/reports", "output_dir": "/srv/reports"},
    "canary": {"db_url": "postgres://reports:${REPORTS_DB_PASSWORD}@db-prod:5432/reports", "output_dir": "/srv/reports"},
}
REPORT_BASE = {"batch_size": 5000, "timezone": "Europe/Berlin"}

IMG_SERVICE = dd('''
    """Fetches and resizes product images from the CDN named in the configuration."""
    from urllib.parse import urlsplit

    CDN = {"https://img.example.net", "https://img-stg.example.net", "http://localhost:8081"}


    def render_hero(cfg, log):
        base = cfg["cdn_base_url"]
        width = cfg.get("max_width", 800)
        quality = cfg.get("quality", 80)
        cache = cfg.get("cache_dir", "")
        url = base + "/hero.webp"
        log(f"fetching {url} (max_width={width}, quality={quality})")
        parts = urlsplit(url)
        if not parts.scheme:
            raise ValueError(f"unknown url type: {url!r}")
        if f"{parts.scheme}://{parts.netloc}" not in CDN:
            raise ConnectionError(f"cannot resolve host {parts.netloc!r}")
        if "//" in parts.path:
            raise FileNotFoundError(f"404 Not Found: {url}")
        if not isinstance(quality, int) or not 1 <= quality <= 100:
            raise ValueError(f"quality must be an integer from 1 to 100, got {quality!r}")
        if width > 4096:
            raise ValueError("max_width above 4096 is not supported")
        if not cache:
            raise OSError("cache directory not set: refusing to run without a cache")
        log(f"resized to {width}px, cached in {cache}")
''')

IMG_ENVS = {
    "dev": {"cdn_base_url": "http://localhost:8081/v2"},
    "staging": {"cdn_base_url": "https://img-stg.example.net/v2"},
    "prod": {"cdn_base_url": "https://img.example.net/v2", "api_key": "${IMGPROXY_KEY}"},
    "canary": {"cdn_base_url": "https://img.example.net/v2", "api_key": "${IMGPROXY_KEY}"},
}
IMG_BASE = {"max_width": 1600, "quality": 80, "cache_dir": "/var/cache/imgproxy"}

SKINS = [
    dict(name="mailer", pkg="mailer", title="the nightly digest mailer", service=MAIL_SERVICE, entry="send_digest", envs=MAIL_ENVS, base=MAIL_BASE,
         secrets={"SMTP_PASSWORD": "s3cret"}, keys=dict(host="smtp_host", port="smtp_port", tls="use_tls", timeout="timeout_s", secret="password"),
         defects=["typo-key", "bool-string", "unit", "port", "env-ref", "host-slash"]),
    dict(name="reports", pkg="reports", title="the nightly sales report job", service=REPORT_SERVICE, entry="build_report", envs=REPORT_ENVS, base=REPORT_BASE,
         secrets={"REPORTS_DB_PASSWORD": "pg-pass"}, keys=dict(batch="batch_size", out="output_dir", url="db_url"),
         defects=["typed-number", "typo-key", "port", "env-ref", "path"]),
    dict(name="imgproxy", pkg="imgproxy", title="the product image proxy", service=IMG_SERVICE, entry="render_hero", envs=IMG_ENVS, base=IMG_BASE,
         secrets={"IMGPROXY_KEY": "k-1234"}, keys=dict(url="cdn_base_url", width="max_width", quality="quality", cache="cache_dir"),
         defects=["url-slash", "url-scheme", "unit", "typed-number", "typo-key", "env-ref"]),
]


# ---- rendering configs ----------------------------------------------------------------------------------------------

def render(fmt: str, data: dict, note: str = "") -> str:
    if fmt == "json":
        return json.dumps(data, indent=2) + "\n"
    lines = []
    if fmt == "ini":
        lines.append("[settings]")
    for k, v in data.items():
        if fmt == "toml":
            val = json.dumps(v) if not isinstance(v, bool) else ("true" if v else "false")
            lines.append(f"{k} = {val}")
        elif fmt == "ini":
            lines.append(f"{k} = {str(v).lower() if isinstance(v, bool) else v}")
        else:
            lines.append(f"{k}={str(v).lower() if isinstance(v, bool) else v}")
    head = {"toml": "# ", "ini": "; ", "env": "# "}.get(fmt, "")
    return (f"{head}{note}\n" if note and head else "") + "\n".join(lines) + "\n"


def key_line(fmt: str, text: str, key: str) -> int:
    for i, ln in enumerate(text.split("\n"), 1):
        s = ln.strip()
        if fmt == "json" and s.startswith(f'"{key}"'):
            return i
        if fmt != "json" and (s.startswith(f"{key} =") or s.startswith(f"{key}=")):
            return i
    raise RuntimeError(f"key {key} not found")


def apply_defect(skin: dict, fmt: str, env: str, defect: str, cfgs: dict, rng: random.Random):
    """Mutates the config dicts; returns (file, key, kind, what) where file is the env name or "base", or None when the defect
    does not apply to this skin/format."""
    typed = fmt in ("json", "toml")
    d = cfgs[env]
    name = skin["name"]
    if defect == "typo-key":
        if name == "mailer":
            d["smtp_hots"] = d.pop("smtp_host")
            return env, "smtp_hots", "config-error", "the key is spelled `smtp_hots`, so the service silently falls back to its built-in default host"
        if name == "reports":
            cfgs["base"]["batchsize"] = cfgs["base"].pop("batch_size")
            return "base", "batchsize", "config-error", "the key is spelled `batchsize`, so the service silently uses its default batch size of 1"
        cfgs["base"]["cache_dri"] = cfgs["base"].pop("cache_dir")
        return "base", "cache_dri", "config-error", "the key is spelled `cache_dri`, so the service sees no cache directory"
    if defect == "bool-string" and typed and name == "mailer":
        if env != "dev" and "dev" not in cfgs:
            return None
        env = "dev"
        d = cfgs["dev"]
        d["use_tls"] = "false"
        return "dev", "use_tls", "type-confusion", "the boolean is written as the quoted string \"false\", and any non-empty string is true"
    if defect == "unit" and name == "mailer":
        d["timeout_s"] = rng.choice([30000, 45000, 90000])
        return env, "timeout_s", "config-error", "the value is in milliseconds although the setting is in seconds"
    if defect == "unit" and name == "imgproxy":
        cfgs["base"]["quality"] = rng.choice([0.8, 0.85, 0.75])
        return "base", "quality", "config-error", "quality is given as a fraction instead of an integer percentage"
    if defect == "port":
        if name == "mailer":
            p = d["smtp_port"]
            d["smtp_port"] = int(str(p)[::-1]) if str(p)[::-1] != str(p) else p + 1
            return env, "smtp_port", "config-error", "two digits of the port are transposed"
        if name == "reports":
            d["db_url"] = d["db_url"].replace(":5432", ":5342")
            return env, "db_url", "config-error", "the database port is 5342 instead of 5432"
        return None
    if defect == "env-ref":
        if name == "mailer":
            if "password" not in d:
                return None
            d["password"] = "${SMTP_PASSWD}"
            return env, "password", "config-error", "the secret is referenced under a misspelt environment variable name"
        if name == "reports":
            d["db_url"] = d["db_url"].replace("REPORTS_DB_PASSWORD", "REPORT_DB_PASSWORD")
            return env, "db_url", "config-error", "the secret is referenced under a misspelt environment variable name"
        if "api_key" in d:
            d["api_key"] = "${IMGPROXY_API_KEY}"
            return env, "api_key", "config-error", "the secret is referenced under a misspelt environment variable name"
        return None
    if defect == "host-slash" and name == "mailer":
        d["smtp_host"] = d["smtp_host"] + "/"
        return env, "smtp_host", "config-error", "a stray slash after the host name makes it unresolvable"
    if defect == "typed-number" and typed:
        if name == "reports":
            cfgs["base"]["batch_size"] = str(cfgs["base"]["batch_size"])
            return "base", "batch_size", "type-confusion", "the number is written as a quoted string, so comparisons with integers fail"
        if name == "imgproxy":
            cfgs["base"]["max_width"] = str(cfgs["base"]["max_width"])
            return "base", "max_width", "type-confusion", "the number is written as a quoted string, so comparisons with integers fail"
        return None
    if defect == "path" and name == "reports":
        d["output_dir"] = "/srv/report"
        return env, "output_dir", "config-error", "the output directory is misspelt (/srv/report): it does not exist or is not writable"
    if defect == "url-slash" and name == "imgproxy":
        d["cdn_base_url"] = d["cdn_base_url"] + "/"
        return env, "cdn_base_url", "config-error", "a trailing slash makes the joined URL contain a double slash, which the CDN answers with 404"
    if defect == "url-scheme" and name == "imgproxy":
        d["cdn_base_url"] = d["cdn_base_url"].split("://", 1)[1]
        return env, "cdn_base_url", "config-error", "the URL has no scheme (http:// or https://)"
    return None


def config_task(rng: random.Random, i: int, skin: dict, fmt: str, defect: str, fail_env: str) -> Task | None:
    cfgs = {"base": dict(skin["base"])}
    for e, v in skin["envs"].items():
        cfgs[e] = dict(v)
    res = apply_defect(skin, fmt, fail_env, defect, cfgs, rng)
    if res is None:
        return None
    defect_file, key, kind, what = res
    if defect == "bool-string":
        fail_env = "dev"
    pkg = skin["pkg"]
    ext = EXT[fmt]
    files = {
        f"{pkg}/__init__.py": f'"""{skin["title"].capitalize()}."""\n',
        f"{pkg}/config.py": CONFIG_PY.format(ext=ext, loader=LOADERS[fmt]),
        f"{pkg}/service.py": skin["service"],
        "run.py": RUN_PY.format(pkg=pkg, secrets=repr(skin["secrets"]), entry=skin["entry"]),
        "README.md": dd(f'''
            # {pkg}

            {skin["title"].capitalize()}. Run it for an environment with `python3 run.py <env>`; settings come from `config/base.{ext}`
            overlaid by `config/<env>.{ext}`. Environments: {", ".join(skin["envs"])}. `${{NAME}}` in a value is replaced by the environment
            variable `NAME`; the scheduler provides the secrets.
        '''),
    }
    texts = {}
    for name, data in cfgs.items():
        text = render(fmt, data, note=f"{name} settings")
        texts[name] = text
        files[f"config/{name}.{ext}"] = text
    everywhere = defect_file == "base"
    others = [e for e in skin["envs"] if e != fail_env]
    ok_env = rng.choice([e for e in others if e != "dev"] or others)
    runs = {e: run(files, f"python3 run.py {e} 2>&1", timeout=60) for e in (fail_env, ok_env)}
    if runs[fail_env].ok or (runs[ok_env].ok == everywhere):
        raise RuntimeError(f"{pkg}/{defect}/{fmt}: unexpected outcome (fail env ok={runs[fail_env].ok}, other env ok={runs[ok_env].ok}, everywhere={everywhere})")
    start = dict(files)
    for e, r in runs.items():
        start[f"logs/{e}-run.log"] = r.out.strip() + "\n"
    path = f"config/{defect_file}.{ext}"
    kline = key_line(fmt, texts[defect_file], key)
    log_lines = start[f"logs/{fail_env}-run.log"].strip().split("\n")
    windows = [{"file": path, "start": kline, "end": kline}, {"file": f"logs/{fail_env}-run.log", "start": 1, "end": len(log_lines)}]
    schema = ("Write `diagnosis.json`: an object with exactly these keys: `root_cause_file` (the config file that is wrong), `key` (the setting name as it is written in that file, "
              "or as it should be written), `kind` (one of " + ", ".join(KINDS) + "), `evidence_lines` (a list of `path:line` strings: the bad setting and the log lines that show its effect) "
              "and `fix_summary` (one or two sentences: what the file should contain instead).")
    if everywhere:
        voices = [
            f"Since the config cleanup {skin['title']} fails in every environment (`logs/` has the output of two of them). The code was not touched. Find the setting that is wrong. {schema}",
            f"{pkg} stopped working everywhere; the output of two environments is in `logs/`. Only configuration changed. Which setting is the culprit? {schema}",
            f"Nothing runs any more since the settings were reshuffled. Look at the run logs under `logs/` and the files under `config/` and tell me what is wrong. {schema}",
        ]
    else:
        voices = [
            f"`python3 run.py {fail_env}` fails for {skin['title']} while `{ok_env}` is fine; the last deploy changed configuration only. The logs of both runs are in `logs/`. Find the configuration mistake. {schema}",
            f"{fail_env} is broken, {ok_env} works, same code. I compared the files by eye and gave up. What is wrong with the configuration of {skin['title']}? (`logs/` has the output of both runs.) {schema}",
            f"Incident: {skin['title']} failed in {fail_env} after the config refactor. Output of the failing and of a healthy run is in `logs/`. Pinpoint the offending setting. {schema}",
            f"After this morning's change {pkg} no longer works in {fail_env}. Healthy comparison run: {ok_env}. The code was not touched. Where is the bug in the configuration? {schema}",
        ]
    prompt = rng.choice(voices)
    accept_keys = [key] + ([key[:-2]] if defect == "typo-key" else [])
    if defect == "typo-key":
        accept_keys = [{"smtp_hots": "smtp_host", "batchsize": "batch_size", "cache_dri": "cache_dir"}[key], key]
    spec = {"answer_file": "diagnosis.json", "fields": {
        "root_cause_file": {"type": "path", "accept": [path]},
        "key": {"type": "string_in", "accept": accept_keys},
        "kind": {"type": "enum", "allowed": KINDS, "accept": accepted(kind)},
        "evidence_lines": {"type": "evidence", "windows": windows, "slack": 1},
        "fix_summary": {"type": "text", "min_len": 20, "any": [key, "config", "should", "instead", "value", "fix", "spell", "rename"]},
    }}
    gold = {"root_cause_file": path, "key": key, "kind": kind, "evidence_lines": [f"{path}:{kline}", f"logs/{fail_env}-run.log:{len(log_lines)}"], "fix_summary": f"{what}; correct the value of {key}."}
    d = {"typo-key": 3, "bool-string": 3, "unit": 2, "port": 2, "env-ref": 2, "host-slash": 2, "typed-number": 3, "path": 2, "url-slash": 3, "url-scheme": 2}[defect]
    d = min(5, d + (1 if fmt in ("env", "ini") and defect == "typo-key" else 0) + (1 if everywhere else 0))
    return Task(
        slug=f"{i:02d}-{skin['name']}-{defect}-{fmt}", prompt=prompt, difficulty=d, kind="fix", lang="python", start=start, hidden=hidden_diag(spec),
        solution={"diagnosis.json": json.dumps(gold, indent=1) + "\n"}, verify="python3 _verify/check.py", pass_mode="json-score", protected=sorted(start),
        timeout_s=60, tags=["config-drift", defect, fmt], notes={"skin": skin["name"], "format": fmt, "defect": defect, "env": fail_env, "key": key, "what": what},
    )


def config_family(rng: random.Random, n: int):
    i, guard = 0, 0
    combos = [(s, d) for s in SKINS for d in s["defects"]]
    rng.shuffle(combos)
    while i < n and guard < n * 20:
        s, d = combos[guard % len(combos)]
        guard += 1
        fmt = rng.choice(["ini", "json", "toml", "env"])
        env = rng.choice(["staging", "prod", "canary"])
        t = config_task(rng, i + 1, s, fmt, d, env)
        if t is not None:
            i += 1
            yield t
