"""A small authoritative-DNS simulator for RFC 1035 zone files (shipped to the agent as tools/zonesim.py, used by the hidden checker)."""

DNSSIM = r'''#!/usr/bin/env python3
"""zonesim.py - check a DNS master file the way `named-checkzone` would (documented subset) and answer queries from it like an authoritative server.

    python3 tools/zonesim.py ZONEFILE ORIGIN queries.json         # ORIGIN like example.org.
    python3 tools/zonesim.py ZONEFILE ORIGIN --check              # only the zone checks

queries.json: [{"q": {"name": "www.example.org.", "type": "A"}, "expect": {...}}, ...]  (expect is optional; any subset of rcode, answer, referral, glue)

Master file syntax: `$ORIGIN name`, `$TTL value` (seconds or 1h30m style units s m h d w), records `[owner] [ttl] [class] TYPE rdata` in either TTL/class order; an empty owner repeats the previous owner;
`@` is the origin; a name without a trailing dot is relative to the current origin (`www` -> www.<origin>, `www.example.org` -> www.example.org.<origin> - mind the dot!); `;` starts a comment;
parentheses continue a record over several lines; strings in double quotes. Types: SOA NS A AAAA CNAME MX TXT SRV PTR CAA. `$INCLUDE` and `$GENERATE` are not supported.
rdata: SOA mname rname serial refresh retry expire minimum (the five numbers after the names; the four times may use units: 2h, 15m); MX preference exchange; SRV priority weight port target; CAA flags tag "value"; TXT one or more quoted strings (each at most 255 bytes).

Zone checks (a failure rejects the zone): the first record is the SOA of the origin, exactly one SOA; at least one NS at the apex; every owner is inside the zone; no CNAME at the apex; a name with a CNAME has no other data;
addresses are valid; the exchange of an MX, the target of an SRV and the name server of an NS that lie inside the zone must have an address (A or AAAA) and must not be a CNAME; below a delegation (an NS record at a name other than the apex)
only address records of in-zone name server names (glue) are allowed.

Answers: `rcode` NOERROR or NXDOMAIN; `answer` is a list of "name ttl TYPE rdata" strings (CNAME chain first, then the records of the asked type sorted by rdata); TXT is shown as one concatenated string.
A query at or below a delegation gets `referral` (the NS records) and `glue` instead. Wildcards (`*.name`) answer names that do not exist, as in RFC 4592: only when no record exists at the queried name or at a name below it.
"""
import ipaddress
import json
import re
import sys

TYPES = {"SOA", "NS", "A", "AAAA", "CNAME", "MX", "TXT", "SRV", "PTR", "CAA"}
UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


class ZoneError(Exception):
    pass


def ttl_value(s):
    m = re.fullmatch(r"(?:\d+[smhdwSMHDW]?)+", s)
    if not m:
        return None
    return sum(int(n) * UNITS[(u or "s").lower()] for n, u in re.findall(r"(\d+)([smhdwSMHDW]?)", s))


def absname(n, origin):
    if n == "@":
        return origin
    if n.endswith("."):
        return n.lower()
    return (n + "." + origin).lower()


def logical_lines(text):
    buf, depth, first_blank = "", 0, False
    for raw in text.split("\n"):
        line, q, out = raw, False, ""
        for ch in line:
            if ch == '"':
                q = not q
            if ch == ";" and not q:
                break
            if not q and ch == "(":
                depth += 1
                ch = " "
            elif not q and ch == ")":
                depth -= 1
                ch = " "
            out += ch
        if not buf:
            first_blank = out[:1] in (" ", "\t")
        buf += out + " "
        if depth <= 0:
            if buf.strip():
                yield first_blank, buf
            buf, depth = "", 0
    if buf.strip():
        raise ZoneError("unbalanced parenthesis")


def split_tokens(s):
    toks = re.findall(r'"(?:[^"\\]|\\.)*"|\S+', s)
    return toks


def parse(text, origin):
    origin = origin.lower()
    cur_origin, default_ttl, prev_owner = origin, None, None
    recs = []
    for blank, line in logical_lines(text):
        toks = split_tokens(line)
        if not toks:
            continue
        if toks[0].startswith("$"):
            d = toks[0].upper()
            if d == "$ORIGIN" and len(toks) == 2:
                cur_origin = absname(toks[1], cur_origin)
            elif d == "$TTL" and len(toks) == 2:
                default_ttl = ttl_value(toks[1])
                if default_ttl is None:
                    raise ZoneError(f"bad $TTL {toks[1]!r}")
            else:
                raise ZoneError(f"unsupported or malformed directive {toks[0]}")
            continue
        if blank:
            if prev_owner is None:
                raise ZoneError("a record without an owner name comes first")
            owner = prev_owner
        else:
            owner = absname(toks[0], cur_origin)
            toks = toks[1:]
        prev_owner = owner
        ttl, cls = None, "IN"
        while toks and (ttl_value(toks[0]) is not None or toks[0].upper() == "IN") and toks[0].upper() not in TYPES:
            if toks[0].upper() == "IN":
                cls = "IN"
            else:
                ttl = ttl_value(toks[0])
            toks = toks[1:]
        if not toks or toks[0].upper() not in TYPES:
            raise ZoneError(f"unknown record type in line: {line.strip()[:60]!r}")
        rtype, rd = toks[0].upper(), toks[1:]
        if ttl is None:
            ttl = default_ttl
        if ttl is None:
            raise ZoneError(f"no TTL for {owner} {rtype} (set $TTL or give a TTL)")
        recs.append({"owner": owner, "ttl": ttl, "type": rtype, "rdata": norm_rdata(rtype, rd, cur_origin, owner)})
    return recs


def need(rd, n, rtype):
    if len(rd) != n:
        raise ZoneError(f"{rtype} needs {n} fields, got {len(rd)}")


def uint(s, bits, what):
    if not re.fullmatch(r"\d+", s) or int(s) >= 2 ** bits:
        raise ZoneError(f"bad {what} {s!r}")
    return int(s)


def norm_rdata(rtype, rd, origin, owner):
    if rtype == "A":
        need(rd, 1, "A")
        try:
            return str(ipaddress.IPv4Address(rd[0]))
        except ValueError:
            raise ZoneError(f"bad IPv4 address {rd[0]!r} for {owner}")
    if rtype == "AAAA":
        need(rd, 1, "AAAA")
        try:
            return str(ipaddress.IPv6Address(rd[0]))
        except ValueError:
            raise ZoneError(f"bad IPv6 address {rd[0]!r} for {owner}")
    if rtype in ("NS", "CNAME", "PTR"):
        need(rd, 1, rtype)
        return absname(rd[0], origin)
    if rtype == "MX":
        need(rd, 2, "MX")
        return f"{uint(rd[0], 16, 'MX preference')} {absname(rd[1], origin)}"
    if rtype == "SRV":
        need(rd, 4, "SRV")
        return f"{uint(rd[0], 16, 'priority')} {uint(rd[1], 16, 'weight')} {uint(rd[2], 16, 'port')} {absname(rd[3], origin)}"
    if rtype == "SOA":
        need(rd, 7, "SOA")
        nums = [uint(rd[2], 32, "SOA serial")]
        for x in rd[3:]:
            v = ttl_value(x)
            if v is None or v >= 2 ** 32:
                raise ZoneError(f"bad SOA time value {x!r}")
            nums.append(v)
        return f"{absname(rd[0], origin)} {absname(rd[1], origin)} " + " ".join(str(n) for n in nums)
    if rtype == "CAA":
        need(rd, 3, "CAA")
        return f"{uint(rd[0], 8, 'CAA flags')} {rd[1].lower()} " + json.dumps(rd[2].strip('"'))
    if rtype == "TXT":
        if not rd or not all(t.startswith('"') and t.endswith('"') and len(t) >= 2 for t in rd):
            raise ZoneError(f"TXT data of {owner} must be quoted strings")
        strs = [t[1:-1] for t in rd]
        if any(len(s.encode()) > 255 for s in strs):
            raise ZoneError(f"a TXT string of {owner} is longer than 255 bytes: split it into several quoted strings")
        return json.dumps("".join(strs))
    raise ZoneError("unsupported type " + rtype)


def inside(name, origin):
    return name == origin or name.endswith("." + origin)


def check(recs, origin):
    origin = origin.lower()
    if not recs or recs[0]["type"] != "SOA" or recs[0]["owner"] != origin:
        raise ZoneError(f"the first record must be the SOA of {origin}")
    if sum(r["type"] == "SOA" for r in recs) != 1:
        raise ZoneError("exactly one SOA record is allowed")
    if not any(r["type"] == "NS" and r["owner"] == origin for r in recs):
        raise ZoneError(f"{origin} has no NS records")
    by = {}
    for r in recs:
        if not inside(r["owner"], origin):
            raise ZoneError(f"{r['owner']} is outside the zone {origin} ({r['type']} record): did you forget a trailing dot, or write the origin twice?")
        by.setdefault(r["owner"], []).append(r)
    addr = {n for n, rs in by.items() if any(x["type"] in ("A", "AAAA") for x in rs)}
    cname = {n for n, rs in by.items() if any(x["type"] == "CNAME" for x in rs)}
    for n, rs in by.items():
        if n in cname and (n == origin or any(x["type"] != "CNAME" for x in rs)):
            raise ZoneError(f"{n}: a CNAME cannot coexist with other data" + (" (and is not allowed at the apex)" if n == origin else ""))
    cuts = {n for n, rs in by.items() if n != origin and any(x["type"] == "NS" for x in rs)}
    for n, rs in by.items():
        for r in rs:
            tgt = None
            if r["type"] in ("MX", "NS"):
                tgt = r["rdata"].split()[-1]
            elif r["type"] == "SRV":
                tgt = r["rdata"].split()[-1]
            if tgt and inside(tgt, origin):
                if tgt in cname:
                    raise ZoneError(f"{n} {r['type']} {tgt} is a CNAME (illegal)")
                if tgt not in addr:
                    raise ZoneError(f"{n} {r['type']} {tgt} has no address records (A or AAAA)")
        cut = next((c for c in cuts if n != c and n.endswith("." + c)), None)
        if cut:
            ns_targets = {x["rdata"] for x in by[cut] if x["type"] == "NS"}
            for r in rs:
                if not (r["type"] in ("A", "AAAA") and n in ns_targets):
                    raise ZoneError(f"{n} {r['type']}: data below the delegation {cut} that is not glue")
    return by


def fmt(r):
    return f"{r['owner']} {r['ttl']} {r['type']} {r['rdata']}"


def query(by, origin, name, qtype):
    origin = origin.lower()
    name = name.lower()
    qtype = qtype.upper()
    answer = []
    seen = set()
    while True:
        if not inside(name, origin):
            return {"rcode": "NOERROR", "answer": answer}
        cut = next((c for c in by if c != origin and any(x["type"] == "NS" for x in by[c]) and (name == c or name.endswith("." + c))), None)
        if cut and not (name == cut and qtype in ("DS",)):
            ns = [x for x in by[cut] if x["type"] == "NS"]
            glue = [x for n in {x["rdata"] for x in ns} for x in by.get(n, []) if x["type"] in ("A", "AAAA")]
            return {"rcode": "NOERROR", "answer": answer, "referral": sorted(fmt(x) for x in ns), "glue": sorted(fmt(x) for x in glue)}
        recs = by.get(name)
        synth = None
        if recs is None:
            exists_below = any(n.endswith("." + name) for n in by)
            if exists_below:
                recs = []
            else:
                anc = name.split(".", 1)[1] if "." in name else ""
                while anc and not (anc in by or any(n.endswith("." + anc) for n in by)):
                    anc = anc.split(".", 1)[1] if "." in anc else ""
                w = "*." + anc
                if anc and w in by:
                    recs, synth = by[w], name
                else:
                    return {"rcode": "NXDOMAIN", "answer": answer}
        out = lambda r: dict(r, owner=synth or r["owner"])
        cn = [r for r in recs if r["type"] == "CNAME"]
        if cn and qtype != "CNAME":
            answer.append(fmt(out(cn[0])))
            name = cn[0]["rdata"]
            if name in seen:
                return {"rcode": "NOERROR", "answer": answer, "note": "CNAME loop"}
            seen.add(name)
            continue
        hit = sorted(fmt(out(r)) for r in recs if r["type"] == qtype)
        return {"rcode": "NOERROR", "answer": answer + hit}


def load(path, origin):
    try:
        text = open(path, encoding="utf-8").read()
    except OSError as e:
        raise ZoneError(f"cannot read {path}: {e.strerror}")
    recs = parse(text, origin)
    return check(recs, origin)


def matches(res, expect):
    bad = []
    for k, v in expect.items():
        if res.get(k, [] if k in ("answer", "referral", "glue") else None) != v:
            bad.append(f"{k}: want {v!r}, got {res.get(k)!r}")
    return bad


def main(argv):
    if len(argv) not in (3, 4):
        print(__doc__)
        return 2
    origin = argv[2]
    try:
        by = load(argv[1], origin)
    except ZoneError as e:
        print(f"zone {origin}: {e}")
        return 1
    if len(argv) == 3 or argv[3] == "--check":
        print(f"zone {origin}: loaded {sum(len(v) for v in by.values())} records, OK")
        return 0
    fails = 0
    for c in json.load(open(argv[3], encoding="utf-8")):
        q = c["q"]
        res = query(by, origin, q["name"], q["type"])
        line = f"{q['name']} {q['type']} -> {json.dumps(res)}"
        if "expect" in c:
            bad = matches(res, c["expect"])
            line += "   OK" if not bad else "   FAIL: " + "; ".join(bad)
            fails += bool(bad)
        print(line)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
'''
