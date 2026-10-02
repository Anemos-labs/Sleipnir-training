"""A small iptables-restore simulator (shipped to the agent as tools/fwsim.py, used by the hidden checker)."""

FWSIM = r'''#!/usr/bin/env python3
"""fwsim.py - simulate what an iptables ruleset (iptables-save / iptables-restore format) does to a packet.

    python3 tools/fwsim.py RULES PACKETS.json          # one line per packet, and OK/FAIL for packets that carry an expectation

PACKETS.json: {"config": {"local_ips": [...], "ifaddrs": {"eth0": "203.0.113.2"}}, "cases": [{"pkt": {...}, "expect": {...}}]}
    pkt:    {"flow": "in" | "out", "iif": "eth0", "oif": "eth1", "src": "198.51.100.7", "dst": "203.0.113.2", "proto": "tcp", "sport": 51000, "dport": 22, "state": "NEW", "icmp_type": "echo-request"}
    expect: any subset of {"verdict": "ACCEPT"|"DROP"|"REJECT", "src": "ip[:port]", "dst": "ip[:port]", "log": ["prefix", ...]}

Rules understood (tables `filter` and `nat`; IPv4 only):
  * file: `*table`, `:CHAIN POLICY [0:0]` (user chains have policy `-`), `-A CHAIN ...`, `COMMIT`; `#` comments. Every `-j` to a user chain needs that chain declared.
  * matches: `-p tcp|udp|icmp|all`, `-s`/`-d` ADDRESS[/MASK], `-i`/`-o` IFACE (a trailing `+` is a wildcard: `eth+`), `--sport`/`--dport` PORT|LOW:HIGH (with -p tcp or udp), `-m multiport --dports/--sports A,B,LOW:HIGH`,
    `-m conntrack --ctstate NEW,ESTABLISHED,RELATED,INVALID` (also `-m state --state`), `--icmp-type NAME|NUMBER` (with -p icmp), `-m comment --comment TEXT` (ignored), `-m limit ...` (accepted, always matches here).
    Any match can be negated with `!` before it (`! -s 10.0.0.0/8`, `-s ! 10.0.0.0/8`).
  * targets: ACCEPT, DROP, REJECT [--reject-with X], LOG [--log-prefix TEXT] (does not end the traversal), RETURN, a user chain (jump),
    nat only: DNAT --to-destination IP[:PORT], SNAT --to-source IP, MASQUERADE, REDIRECT --to-ports PORT.
  * traversal: rules in file order; the first rule whose matches all hold and whose target ends the traversal decides; a chain that runs out of rules returns to its caller; the built-in chain's policy applies at the end.
    A packet that is ACCEPTed by a jump to a user chain is accepted for good.

Packet path: flow `in`: nat PREROUTING (only state NEW; DNAT/REDIRECT change the destination) -> if the (new) destination is one of config.local_ips (or any 127.x.x.x address): filter INPUT, otherwise filter FORWARD (the packet needs an `oif`)
-> for forwarded packets with state NEW: nat POSTROUTING (MASQUERADE uses config.ifaddrs[oif], SNAT its address). Flow `out`: filter OUTPUT -> nat POSTROUTING.
The filter rules see the packet as translated by PREROUTING (a FORWARD rule must match the new destination, not the original one).
"""
import ipaddress
import json
import re
import shlex
import sys


class FwError(Exception):
    pass


BUILTIN = {"filter": ["INPUT", "FORWARD", "OUTPUT"], "nat": ["PREROUTING", "INPUT", "OUTPUT", "POSTROUTING"]}
ICMP = {"echo-reply": 0, "destination-unreachable": 3, "echo-request": 8, "time-exceeded": 11}


def parse(text):
    rs, table = {}, None
    committed = True
    for n, raw in enumerate(text.split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            if line.startswith("*"):
                table = line[1:]
                if table not in BUILTIN:
                    raise FwError(f"unsupported table {table!r} (use filter or nat)")
                rs[table] = {c: {"policy": None, "rules": [], "builtin": True} for c in BUILTIN[table]}
                committed = False
            elif line == "COMMIT":
                if table is None:
                    raise FwError("COMMIT outside a table")
                for c, ch in rs[table].items():
                    for r in ch["rules"]:
                        j = r["target"]
                        if j not in ("ACCEPT", "DROP", "REJECT", "LOG", "RETURN", "DNAT", "SNAT", "MASQUERADE", "REDIRECT") and j not in rs[table]:
                            raise FwError(f"rule in chain {c} jumps to {j!r}, which is not a chain of table {table}")
                table, committed = None, True
            elif line.startswith(":"):
                parts = line[1:].split()
                if table is None or len(parts) < 2:
                    raise FwError("bad chain declaration")
                name, pol = parts[0], parts[1]
                if name in BUILTIN[table]:
                    if pol not in ("ACCEPT", "DROP"):
                        raise FwError(f"built-in chain {name} needs policy ACCEPT or DROP")
                    rs[table][name]["policy"] = pol
                else:
                    if pol != "-":
                        raise FwError(f"user chain {name} must have policy -")
                    rs[table][name] = {"policy": None, "rules": [], "builtin": False}
            elif line.startswith("-A"):
                if table is None:
                    raise FwError("rule outside a table")
                chain, rule = parse_rule(shlex.split(line)[1:])
                if chain not in rs[table]:
                    raise FwError(f"no chain named {chain!r} in table {table}")
                if table == "filter" and rule["target"] in ("DNAT", "SNAT", "MASQUERADE", "REDIRECT"):
                    raise FwError(f"target {rule['target']} is only valid in the nat table")
                rs[table][chain]["rules"].append(rule)
            else:
                raise FwError("cannot parse line")
        except FwError as e:
            raise FwError(f"line {n}: {e}")
        except ValueError as e:
            raise FwError(f"line {n}: {e}")
    if not committed:
        raise FwError("missing COMMIT at the end of the last table")
    for t in rs:
        for c in BUILTIN[t]:
            if rs[t][c]["policy"] is None:
                rs[t][c]["policy"] = "ACCEPT"
    return rs


def parse_rule(tok):
    chain = tok[0]
    i, neg = 1, False
    m = {"proto": None, "src": None, "dst": None, "iif": None, "oif": None, "sport": None, "dport": None, "state": None, "icmp": None}
    target, targs = None, {}
    module = None

    def val():
        nonlocal i, neg
        i += 1
        if i < len(tok) and tok[i] == "!":
            neg = not neg
            i += 1
        if i >= len(tok):
            raise FwError("missing option value")
        return tok[i]

    while i < len(tok):
        t = tok[i]
        n0 = neg
        if t == "!":
            neg, i = True, i + 1
            continue
        if t == "-p":
            v = val()
            m["proto"] = (v.lower(), neg)
        elif t in ("-s", "--source"):
            m["src"] = (ipaddress.ip_network(val(), strict=False), neg)
        elif t in ("-d", "--destination"):
            m["dst"] = (ipaddress.ip_network(val(), strict=False), neg)
        elif t in ("-i", "--in-interface"):
            m["iif"] = (val(), neg)
        elif t in ("-o", "--out-interface"):
            m["oif"] = (val(), neg)
        elif t in ("--sport", "--source-port"):
            m["sport"] = (ports(val()), neg)
        elif t in ("--dport", "--destination-port"):
            m["dport"] = (ports(val()), neg)
        elif t in ("--sports", "--source-ports"):
            m["sport"] = (ports(val()), neg)
        elif t in ("--dports", "--destination-ports"):
            m["dport"] = (ports(val()), neg)
        elif t == "-m":
            module = val()
            if module not in ("multiport", "conntrack", "state", "comment", "limit", "tcp", "udp", "icmp"):
                raise FwError(f"unsupported match module {module!r}")
        elif t in ("--ctstate", "--state"):
            m["state"] = (set(val().split(",")), neg)
        elif t == "--icmp-type":
            v = val()
            m["icmp"] = (ICMP[v] if v in ICMP else int(v), neg)
        elif t in ("--comment", "--limit", "--limit-burst"):
            val()
        elif t in ("-j", "-g"):
            target = val()
        elif t == "--reject-with":
            targs["reject"] = val()
        elif t == "--log-prefix":
            targs["prefix"] = val()
        elif t == "--log-level":
            val()
        elif t == "--to-destination":
            targs["to"] = val()
        elif t == "--to-source":
            targs["to"] = val()
        elif t == "--to-ports":
            targs["ports"] = val()
        else:
            raise FwError(f"unknown option {t!r}")
        if t not in ("!",):
            neg = False
        i += 1
    if target is None:
        raise FwError("rule has no -j target")
    if (m["sport"] or m["dport"]) and not (m["proto"] and m["proto"][0] in ("tcp", "udp") and not m["proto"][1]):
        raise FwError("port matches need -p tcp or -p udp")
    if m["icmp"] and not (m["proto"] and m["proto"][0] == "icmp"):
        raise FwError("--icmp-type needs -p icmp")
    return chain, {"m": m, "target": target, "args": targs}


def ports(v):
    out = []
    for part in v.split(","):
        if ":" in part:
            a, b = part.split(":", 1)
            out.append((int(a or 0), int(b or 65535)))
        else:
            out.append((int(part), int(part)))
    for a, b in out:
        if not (0 <= a <= b <= 65535):
            raise FwError(f"bad port range {v!r}")
    return out


def matches(rule, p):
    m = rule["m"]

    def test(key, ok):
        if m[key] is None:
            return True
        return ok(m[key][0]) != m[key][1]
    proto = p.get("proto", "tcp")
    if not test("proto", lambda v: v == "all" or v == proto):
        return False
    if not test("src", lambda v: ipaddress.ip_address(p["src"]) in v):
        return False
    if not test("dst", lambda v: ipaddress.ip_address(p["dst"]) in v):
        return False
    for k, f in (("iif", "iif"), ("oif", "oif")):
        if not test(k, lambda v: p.get(f) is not None and (p[f].startswith(v[:-1]) if v.endswith("+") else p[f] == v)):
            return False
    if not test("sport", lambda v: any(a <= p.get("sport", -1) <= b for a, b in v)):
        return False
    if not test("dport", lambda v: any(a <= p.get("dport", -1) <= b for a, b in v)):
        return False
    if not test("state", lambda v: p.get("state", "NEW") in v):
        return False
    if m["icmp"] is not None:
        t = p.get("icmp_type", 8)
        t = ICMP.get(t, t) if isinstance(t, str) else t
        if not test("icmp", lambda v: v == t):
            return False
    return True


def run_chain(rs, table, name, p, log, depth=0):
    """Return a verdict string or None (chain ended / RETURN)."""
    if depth > 20:
        raise FwError("chain loop")
    for r in rs[table][name]["rules"]:
        if not matches(r, p):
            continue
        t = r["target"]
        if t == "LOG":
            log.append(r["args"].get("prefix", ""))
        elif t in ("ACCEPT", "DROP", "REJECT"):
            return t
        elif t == "RETURN":
            return None
        elif t == "DNAT":
            ip, _, port = r["args"]["to"].partition(":")
            p["dst"] = ip
            if port:
                p["dport"] = int(port)
            return "ACCEPT"
        elif t == "REDIRECT":
            p["dst"] = p["_local"][0]
            if r["args"].get("ports"):
                p["dport"] = int(r["args"]["ports"].split("-")[0])
            return "ACCEPT"
        elif t == "SNAT":
            p["src"] = r["args"]["to"].split(":")[0]
            return "ACCEPT"
        elif t == "MASQUERADE":
            p["src"] = p["_ifaddrs"].get(p.get("oif"), p["src"])
            return "ACCEPT"
        else:
            v = run_chain(rs, table, t, p, log, depth + 1)
            if v is not None:
                return v
    return None


def simulate(rs, pkt, config):
    p = dict(pkt)
    p.setdefault("proto", "tcp")
    p.setdefault("state", "NEW")
    p["_local"] = config.get("local_ips", [])
    p["_ifaddrs"] = config.get("ifaddrs", {})
    log = []
    flow = p.get("flow", "in")
    nat = rs.get("nat")
    flt = rs.get("filter")

    def end(v):
        res = {"verdict": v}
        if v == "ACCEPT":
            res["src"] = p["src"] + (f":{p['sport']}" if "sport" in p and p["proto"] in ("tcp", "udp") else "")
            res["dst"] = p["dst"] + (f":{p['dport']}" if "dport" in p and p["proto"] in ("tcp", "udp") else "")
        if log:
            res["log"] = log
        return res
    if flow == "in":
        if nat and p["state"] == "NEW":
            run_chain(rs, "nat", "PREROUTING", p, log)
        local = p["dst"] in p["_local"] or ipaddress.ip_address(p["dst"]).is_loopback
        chain = "INPUT" if local else "FORWARD"
        if not local and not p.get("oif"):
            raise FwError("a forwarded packet needs an oif")
        v = (run_chain(rs, "filter", chain, p, log) if flt else None) or (flt[chain]["policy"] if flt else "ACCEPT")
        if v != "ACCEPT":
            return end(v)
        if not local and nat and p["state"] == "NEW":
            run_chain(rs, "nat", "POSTROUTING", p, log)
        return end("ACCEPT")
    v = (run_chain(rs, "filter", "OUTPUT", p, log) if flt else None) or (flt["OUTPUT"]["policy"] if flt else "ACCEPT")
    if v != "ACCEPT":
        return end(v)
    if nat and p["state"] == "NEW":
        run_chain(rs, "nat", "POSTROUTING", p, log)
    return end("ACCEPT")


def check(res, expect):
    bad = []
    for k, v in expect.items():
        if res.get(k) != v:
            bad.append(f"{k}: want {v!r}, got {res.get(k)!r}")
    return bad


def describe(p):
    s = f"{p.get('flow', 'in')} {p.get('proto', 'tcp')} {p['src']}" + (f":{p['sport']}" if "sport" in p else "") + f" -> {p['dst']}" + (f":{p['dport']}" if "dport" in p else "")
    extras = [f"{k}={p[k]}" for k in ("iif", "oif", "state", "icmp_type") if k in p]
    return s + (" [" + " ".join(extras) + "]" if extras else "")


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    try:
        rs = parse(open(argv[1], encoding="utf-8").read())
    except FwError as e:
        print(f"iptables-restore: {e}")
        return 1
    data = json.load(open(argv[2], encoding="utf-8"))
    fails = 0
    for c in data["cases"]:
        try:
            res = simulate(rs, c["pkt"], data.get("config", {}))
        except FwError as e:
            print(f"{describe(c['pkt'])} -> error: {e}")
            fails += 1
            continue
        line = f"{describe(c['pkt'])} -> {json.dumps(res, sort_keys=True)}"
        if "expect" in c:
            bad = check(res, c["expect"])
            line += "   OK" if not bad else "   FAIL: " + "; ".join(bad)
            fails += bool(bad)
        print(line)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
'''
