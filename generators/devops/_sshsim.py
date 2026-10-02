"""A small ssh_config resolver (shipped to the agent as tools/sshsim.py, used by the hidden checker)."""

SSHSIM = r'''#!/usr/bin/env python3
"""sshsim.py - what would `ssh -G [-l USER] HOST` print for this ssh_config? (documented subset of ssh_config(5))

    python3 tools/sshsim.py CONFIG HOST [USER]          # prints the effective options of one host
    python3 tools/sshsim.py CONFIG queries.json         # runs {"q": {"host": "...", "user": "..."}, "expect": {...}} cases (user optional)

Rules (as in OpenSSH): the file is read from top to bottom; the first value obtained for an option wins (so specific blocks must come before general ones), except for the options that accumulate:
IdentityFile, CertificateFile, LocalForward, RemoteForward, SendEnv/SetEnv (all values, in order). Options before the first `Host`/`Match` apply to every host.
  * `Host p1 p2 !p3 ...`: matches when the host name typed on the command line matches at least one positive pattern and none of the negated ones; patterns use `*` and `?` and are case-insensitive.
  * `Match all`, `Match originalhost PATTERNS` (the name typed), `Match host PATTERNS` (the target host name: the HostName obtained so far from earlier blocks, else the name typed),
    `Match user PATTERNS` (the remote user: the -l/`user@` value, else the User obtained so far, else the local user `tester`); patterns are comma separated and may be negated with `!`; several criteria on one Match line must all hold.
    `Match exec` and `Include` are not supported.
  * keys are case-insensitive, `Key value` or `Key=value`, values may be double-quoted, `#` starts a comment.
  * accepted options: HostName User Port IdentityFile IdentitiesOnly ProxyJump ProxyCommand ForwardAgent ServerAliveInterval ServerAliveCountMax StrictHostKeyChecking UserKnownHostsFile ControlMaster ControlPath
    ControlPersist Compression LocalForward RemoteForward SetEnv AddKeysToAgent PreferredAuthentications BatchMode ConnectTimeout LogLevel RequestTTY CertificateFile HostKeyAlias
  * defaults: hostname = the name typed, port 22, user = the -l/`user@` value or `tester`. Tokens in values: %h (final host name; inside HostName itself it is the name typed), %n (name typed), %p (port), %r (remote user), %% (a percent sign).
  * `ProxyJump none` switches the option off (the effective value is then `none`); the first value still wins.
Output keys are lower case, as in `ssh -G`.
"""
import fnmatch
import json
import re
import shlex
import sys

OPTS = {"hostname", "user", "port", "identityfile", "identitiesonly", "proxyjump", "proxycommand", "forwardagent", "serveraliveinterval", "serveralivecountmax", "stricthostkeychecking", "userknownhostsfile",
        "controlmaster", "controlpath", "controlpersist", "compression", "localforward", "remoteforward", "setenv", "addkeystoagent", "preferredauthentications", "batchmode", "connecttimeout", "loglevel",
        "requestty", "certificatefile", "hostkeyalias"}
ACC = {"identityfile", "certificatefile", "localforward", "remoteforward", "setenv"}


class SshError(Exception):
    pass


def parse(text):
    blocks = [{"kind": "all", "crit": [], "opts": [], "line": 0}]
    for n, raw in enumerate(text.split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"([A-Za-z]+)\s*(?:=\s*|\s+)(.*)$", line)
        if not m:
            raise SshError(f"line {n}: missing argument")
        key, rest = m.group(1).lower(), m.group(2).strip()
        try:
            words = shlex.split(rest, comments=True)
        except ValueError:
            raise SshError(f"line {n}: unbalanced quotes")
        if key == "host":
            if not words:
                raise SshError(f"line {n}: Host needs a pattern")
            blocks.append({"kind": "host", "crit": [("originalhost", words)], "opts": [], "line": n})
        elif key == "match":
            crit, i = [], 0
            if words == ["all"]:
                blocks.append({"kind": "match", "crit": [], "opts": [], "line": n})
                continue
            while i < len(words):
                c = words[i].lower()
                if c not in ("host", "originalhost", "user") or i + 1 >= len(words):
                    raise SshError(f"line {n}: unsupported Match criterion {words[i]!r} (supported: all, host, originalhost, user)")
                crit.append((c, words[i + 1].split(",")))
                i += 2
            blocks.append({"kind": "match", "crit": crit, "opts": [], "line": n})
        elif key == "include":
            raise SshError(f"line {n}: Include is not supported by this checker")
        elif key in OPTS:
            if not words:
                raise SshError(f"line {n}: {m.group(1)} needs a value")
            blocks[-1]["opts"].append((key, " ".join(words)))
        else:
            raise SshError(f"line {n}: Bad configuration option: {m.group(1)}")
    return blocks


def pat_match(pats, name):
    name = name.lower()
    pos = [p for p in pats if not p.startswith("!")]
    neg = [p[1:] for p in pats if p.startswith("!")]
    if any(fnmatch.fnmatchcase(name, p.lower()) for p in neg):
        return False
    return any(fnmatch.fnmatchcase(name, p.lower()) for p in pos)


def resolve(blocks, host, user=None):
    got = {}
    for b in blocks:
        ok = True
        for kind, pats in b["crit"]:
            if kind == "originalhost":
                ok = ok and pat_match(pats, host)
            elif kind == "host":
                ok = ok and pat_match(pats, got.get("hostname", [host])[0])
            elif kind == "user":
                ok = ok and pat_match(pats, user or got.get("user", ["tester"])[0])
        if not ok:
            continue
        for k, v in b["opts"]:
            if k in ACC:
                got.setdefault(k, []).append(v)
            elif k not in got:
                got[k] = [v]
    out = {}
    hostname = got.get("hostname", [host])[0].replace("%h", host).replace("%n", host).replace("%%", "%")
    port = got.get("port", ["22"])[0]
    ruser = user or got.get("user", ["tester"])[0]

    def tok(s):
        return re.sub(r"%([hnpr%])", lambda m: {"h": hostname, "n": host, "p": port, "r": ruser, "%": "%"}[m.group(1)], s)
    for k, v in got.items():
        out[k] = [tok(x) for x in v] if k in ACC else tok(v[0])
    out["hostname"] = hostname
    out["port"] = int(port) if port.isdigit() else port
    out["user"] = ruser
    return out


def matches(res, expect):
    bad = []
    for k, v in expect.items():
        if res.get(k) != v:
            bad.append(f"{k}: want {v!r}, got {res.get(k)!r}")
    return bad


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    try:
        blocks = parse(open(argv[1], encoding="utf-8").read())
    except SshError as e:
        print(f"{argv[1]}: {e}")
        return 1
    if argv[2].endswith(".json"):
        fails = 0
        for c in json.load(open(argv[2], encoding="utf-8")):
            q = c["q"]
            res = resolve(blocks, q["host"], q.get("user"))
            line = f"{q.get('user', '')}@{q['host']} -> {json.dumps(res, sort_keys=True)}"
            if "expect" in c:
                bad = matches(res, c["expect"])
                line += "   OK" if not bad else "   FAIL: " + "; ".join(bad)
                fails += bool(bad)
            print(line)
        return 1 if fails else 0
    res = resolve(blocks, argv[2], argv[3] if len(argv) > 3 else None)
    for k in sorted(res):
        for v in (res[k] if isinstance(res[k], list) else [res[k]]):
            print(k, v)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
'''
