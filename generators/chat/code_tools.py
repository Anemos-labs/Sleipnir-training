"""Small technical questions with exactly computable answers: shell pipelines on an attached file, regexes, subnets, file modes,
bit flags and version ranges. The oracle is the real tool (bash, chmod, python re/ipaddress) or an exact solver."""
from __future__ import annotations

import ipaddress
import re

import fx
from fx import family

from . import _common as C

# --------------------------------------------------------------------------------------------------------------------
# chat-shell-pipeline

STREETS = ["quay", "mill", "orchard", "chapel", "tannery", "harbour", "market", "castle", "canal", "park"]
KINDS = ["paid", "refund", "pending", "failed"]
TEAMS = ["ops", "design", "sales", "legal", "infra", "support"]


def _csv_orders(rng, n):
    rows = ["id,street,amount,state,team"]
    for k in range(n):
        rows.append(f"{1000 + k},{rng.choice(STREETS)},{rng.randint(5, 120)},{rng.choice(KINDS)},{rng.choice(TEAMS)}")
    return "\n".join(rows) + "\n"


def _words_file(rng, n):
    pool = ["apple", "pear", "plum", "fig", "lime", "kiwi", "date", "melon", "quince", "mango", "cherry", "grape"]
    return "\n".join(rng.choice(pool) for _ in range(n)) + "\n"


PIPES = [
    # (difficulty, file kind, template, description)
    (1, "csv", "tail -n +2 orders.csv | wc -l", "count"),
    (1, "csv", "cut -d, -f2 orders.csv | sort -u | wc -l", "streets"),
    (2, "csv", "awk -F, 'NR>1 && $4==\"paid\" {s+=$3} END {print s}' orders.csv", "paid sum"),
    (2, "csv", "grep -c ',refund,' orders.csv", "refunds"),
    (2, "csv", "cut -d, -f5 orders.csv | tail -n +2 | sort | uniq -c | sort -k1,1nr -k2,2 | head -3", "top3 team"),
    (3, "csv", "tail -n +2 orders.csv | sort -t, -k3,3nr -k1,1n | head -2 | cut -d, -f1,3", "top2 amount"),
    (3, "csv", "awk -F, 'NR>1 {t[$2]+=$3} END {for (k in t) print t[k], k}' orders.csv | sort -k1,1nr -k2,2 | head -3", "street totals"),
    (3, "csv", "grep ',paid,' orders.csv | cut -d, -f2 | sort | uniq -c | sort -k1,1nr -k2,2 | head -2", "paid by street"),
    (4, "csv", "awk -F, 'NR>1 && $3>=60 {print $5}' orders.csv | sort | uniq -c | awk '$1>=2' | wc -l", "teams with 2+ big"),
    (4, "csv", "tail -n +2 orders.csv | awk -F, '{c[$4]++; s[$4]+=$3} END {for (k in c) print k, s[k]/c[k]}' | sort | head -2", "avg by state"),
    (4, "words", "sort words.txt | uniq -c | sort -k1,1nr -k2,2 | head -3 | awk '{print $2\":\"$1}'", "word freq"),
    (5, "csv", "tail -n +2 orders.csv | sort -t, -k4,4 -k3,3nr | awk -F, '!seen[$4]++ {print $4\":\"$1}'", "max per state"),
    (5, "words", "sort words.txt | uniq -d | wc -l; sort -u words.txt | wc -l; head -n 5 words.txt | tr 'a-z' 'A-Z' | paste -sd,", "multi"),
]


@family("chat-shell-pipeline", category="chat", lang="bash", kind="lookup", n=8, mode="answer",
        summary="what does this shell pipeline print for the attached file? (computed by running it with LC_ALL=C)")
def gen_pipe(rng, n):
    plan = [1, 2, 2, 3, 3, 3, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(100):
            cands = [p for p in PIPES if p[0] == d]
            dd, fk, tmpl, tag = rng.choice(cands)
            files = {}
            if fk == "csv":
                files["orders.csv"] = _csv_orders(rng, rng.randint(25, 45) if d < 4 else rng.randint(60, 120))
            else:
                files["words.txt"] = _words_file(rng, rng.randint(25, 60))
            cmd = "export LC_ALL=C; " + tmpl
            res = fx.run(files, cmd, timeout=20)
            if not res.ok or not res.out.strip():
                continue
            lines = [ln.strip() for ln in res.out.strip().split("\n") if ln.strip()]
            if len(lines) > 6:
                continue
            contains = []
            for ln in lines:
                ln = re.sub(r"\s+", " ", ln)
                contains.append(ln)
            fname = next(iter(files))
            intro = rng.choice([f"I have a file called {fname} in this folder and a one-liner someone gave me. I'd like to know what it will print before I run it on the real data.",
                                f"Can you tell me what this pipeline prints for {fname} (it's in the working directory)? It's from a runbook and I don't want surprises.",
                                f"explain-by-example please: {fname} is attached, here is the command. what comes out?"])
            ask = rng.choice(["What is the exact output? If it prints several lines, give them all in order.", "What does it print? Exact output please, all lines.",
                              "Give me the output, every line."])
            if "uniq -c" in tmpl:
                ask += " (Don't worry about the leading spaces that uniq -c adds.)"
            prompt = C.chat(rng, intro, ask, f"```sh\nexport LC_ALL=C\n{tmpl}\n```", C.register_for(rng))
            keep = C.unseen(prompt, contains, False, min_keep=len(contains))
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{tag.replace(' ', '-')}-d{d}", prompt, d, keep, "\n".join(lines), start=files, tags=["shell", "pipelines"], notes={"pipeline": tmpl})
            break
        else:
            raise RuntimeError("pipe: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-regex-match

IDS_POOL = ["AB123-EU", "ab123-EU", "XY9-US", "QR456-US", "QR456-us", "MN007-EU", "M0007-EU", "ZZ999-EU ", "PL12-EU", "TT321-XX", "AA000-US", "KL730-EU", "KL73-EU", "BB555-EUR"]
LOGLINES = ["warn: disk 91% on vol3", "info: disk 45% on vol1", "error: disk 100% on vol12", "warn: cpu 88% on node7", "error: mem 97% on vol3", "info: disk 7% on vol9", "warn: disk 9% on vol4",
            "ERROR: disk 99% on vol2", "debug: disk 93% on vol1"]
PHRASES = ["order #4821 shipped to Ghent", "order #77 cancelled", "order #12345 pending (rush)", "invoice #309 paid", "order #5 shipped to Cork (gift)", "order #610 shipped to Porto",
           "return of order #4821", "order # shipped to Nowhere", "order #4821 shipped to ghent"]


@family("chat-regex-match", category="chat", lang="text", kind="lookup", n=8, mode="answer",
        summary="which lines does this regex match, what does re.sub produce, what does a lazy or greedy group capture (python re is the oracle)")
def gen_regex(rng, n):
    plan = [2, 2, 2, 3, 3, 4, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(100):
            kind = rng.choice({2: ["count"], 3: ["count", "sub"], 4: ["sub", "greedy", "findall"], 5: ["greedy", "findall_nested", "sub_backref"]}[d])
            if kind == "count":
                pat, lines = rng.choice([
                    (r"^[A-Z]{2}\d{3}-(EU|US)$", rng.sample(IDS_POOL, 9)),
                    (r"^(warn|error): disk \d{2,3}% on vol\d+$", rng.sample(LOGLINES, 7)),
                    (r"\bvol[0-9]\b", rng.sample(LOGLINES, 7)),
                ])
                hits = [j + 1 for j, ln in enumerate(lines) if re.search(pat, ln)]
                if not hits or len(hits) == len(lines):
                    continue
                ask = "How many of the numbered lines does `re.search` find a match in, and what is the number of the last matching line? Lines are the text between the quotes (the trailing space on some line, if any, is part of it)."
                contains = [f"{len(hits)}", f"{hits[-1]}"]
                gold = f"{len(hits)} matches; last is line {hits[-1]}"
                data = "\n".join(f"{j + 1}: \"{ln}\"" for j, ln in enumerate(lines))
                mid = f"Pattern (Python, case-sensitive): `{pat}`"
            elif kind == "sub":
                text = rng.choice(PHRASES)
                pat, repl = rng.choice([(r"#(\d+)", r"No.\1"), (r"\s+", "_"), (r"(\w+) (\w+)", r"\2 \1"), (r"[aeiou]", "*")])
                out = re.sub(pat, repl, text)
                if out == text:
                    continue
                ask = "What exactly does `re.sub(pattern, repl, text)` return?"
                contains = [out]
                gold = out
                data = f"text = {text!r}\npattern = r'{pat}'\nrepl = r'{repl}'"
                mid = ""
            elif kind == "greedy":
                s = rng.choice(["<b>alpha</b> and <b>beta</b> and <i>gamma</i>", "[1,2][3,4,5][6]", "name='ann' role='dev' team='ops'", "start-a-end ... start-b-end ... start-c-end"])
                pat = {"<b>alpha</b> and <b>beta</b> and <i>gamma</i>": r"<b>(.*)</b>", "[1,2][3,4,5][6]": r"\[(.*)\]", "name='ann' role='dev' team='ops'": r"role='(.*)'",
                       "start-a-end ... start-b-end ... start-c-end": r"start-(.*?)-end"}[s]
                m = re.search(pat, s)
                ask = "With `m = re.search(pattern, s)`: how many characters long is `m.group(1)`, how many is `m.group(0)`, and what is `m.end()`?"
                contains = [str(len(m.group(1))), str(len(m.group(0))), str(m.end())]
                gold = f"len(group(1)) = {len(m.group(1))}; len(group(0)) = {len(m.group(0))}; end = {m.end()} (group(1) = {m.group(1)!r})"
                data = f"s = {s!r}\npattern = r'{pat}'"
                mid = ""
            elif kind in ("findall", "findall_nested"):
                s = rng.choice(["a1b22c333d4444", "tel 020-7946-0958, alt 0161-496-0000", "v1.2.3 v10.20.30 v4.5", "x=10;y=-3;z=7;w=-12"])
                pat = {"a1b22c333d4444": r"[a-z](\d+)", "tel 020-7946-0958, alt 0161-496-0000": r"(\d{3,4})-(\d{3,4})-(\d{4})", "v1.2.3 v10.20.30 v4.5": r"v(\d+)\.(\d+)\.(\d+)",
                       "x=10;y=-3;z=7;w=-12": r"([a-z])=(-?\d+)"}[s]
                res_ = re.findall(pat, s)
                flat = [int(x) for item in res_ for x in (item if isinstance(item, tuple) else (item,))]
                ask = "How many items does `re.findall(pattern, s)` return, and what is the sum of all the captured numbers if I convert every captured piece with int()?"
                contains = [str(len(res_)), str(sum(flat))]
                gold = f"{len(res_)} items ({res_}); sum {sum(flat)}"
                data = f"s = {s!r}\npattern = r'{pat}'"
                mid = ""
            else:  # sub_backref
                s = rng.choice(["the the cat sat on on the mat", "paid paid twice and then then thrice", "go go go now now"])
                pat = r"\b(\w+) \1\b"
                out = re.sub(pat, r"\1", s)
                ask = f"What does `re.sub(pattern, r'\\1', s)` return, and how many substitutions does it make (see `re.subn`)?"
                cnt = re.subn(pat, r"\1", s)[1]
                contains = [out, str(cnt)]
                gold = f"{out!r}; {cnt} substitutions"
                data = f"s = {s!r}\npattern = r'{pat}'"
                mid = ""
            intro = rng.choice(["I keep misjudging what my regexes will do, so I'd rather ask before shipping this.", "regex sanity check for a log-scrubbing script, python 3.11",
                                "Our linter regex is behaving oddly and I want to understand it by hand first."])
            prompt = C.chat(rng, intro + (" " + mid if mid else ""), ask, C.block(data), C.register_for(rng))
            keep = C.unseen(prompt, contains, False, min_keep=len(contains))
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{kind}", prompt, d, keep, gold, tags=["regex", "reading"], notes={"kind": kind})
            break
        else:
            raise RuntimeError("regex: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-subnet-math


@family("chat-subnet-math", category="chat", lang="text", kind="lookup", n=8, mode="answer",
        summary="IPv4 subnet arithmetic: network/broadcast, usable hosts, same-subnet checks, sizing, splitting, summarising (ipaddress is the oracle)")
def gen_subnet(rng, n):
    plan = [1, 2, 2, 3, 3, 3, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(100):
            kind = rng.choice({1: ["basic"], 2: ["basic", "samenet"], 3: ["sizing", "split"], 4: ["split", "summarise", "samenet2"], 5: ["summarise", "overlap"]}[d])
            a = rng.choice([10, 172, 192])
            oct2 = rng.randint(16, 31) if a == 172 else (168 if a == 192 else rng.randint(0, 200))
            if kind == "basic":
                pre = rng.randint(20, 29)
                ip = f"{a}.{oct2}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
                net = ipaddress.ip_network(f"{ip}/{pre}", strict=False)
                contains = [str(net.network_address), str(net.broadcast_address), str(net.num_addresses - 2)]
                intro = f"A colleague gave me the address {ip}/{pre} for a new office VLAN."
                ask = "What are the network address, the broadcast address, and the number of usable host addresses (exclude network and broadcast)?"
                gold = f"network {contains[0]}, broadcast {contains[1]}, {contains[2]} usable hosts"
            elif kind == "samenet":
                pre = rng.randint(24, 28)
                base = ipaddress.ip_network(f"{a}.{oct2}.{rng.randint(0, 255)}.0/{pre}", strict=False)
                h1 = base.network_address + rng.randint(1, base.num_addresses - 2)
                if rng.random() < 0.5:
                    h2 = base.network_address + rng.randint(1, base.num_addresses - 2)
                else:
                    h2 = base.broadcast_address + rng.randint(1, 5)
                same = ipaddress.ip_network(f"{h1}/{pre}", strict=False) == ipaddress.ip_network(f"{h2}/{pre}", strict=False)
                intro = f"Two machines have the addresses {h1} and {h2}, both configured with the netmask for a /{pre}."
                ask = "Are they in the same subnet (answer yes or no), and what is the network address of the first one?"
                contains = [str(ipaddress.ip_network(f'{h1}/{pre}', strict=False).network_address), "yes" if same else "no"]
                gold = f"{'yes' if same else 'no'}; network {contains[0]}"
            elif kind == "samenet2":
                pre = rng.randint(19, 23)
                base = ipaddress.ip_network(f"{a}.{oct2}.{rng.randint(0, 255)}.0/{pre}", strict=False)
                h1 = base.network_address + rng.randint(1, base.num_addresses - 2)
                h2 = h1 + rng.choice([-300, -200, 100, 400, 600, 900, 1200])
                gw = base.network_address + 1
                intro = f"Hosts {h1} and {h2} are both configured as /{pre}. The gateway is {gw}."
                ask = "Give me the network address (as written in CIDR, like a.b.c.d/nn) of the first host's subnet, and say whether the second host is on that subnet (yes or no)."
                same = h2 in base
                contains = [str(base), "yes" if same else "no"]
                gold = f"{base}; {'yes' if same else 'no'}"
            elif kind == "sizing":
                need = rng.choice([14, 28, 60, 100, 200, 450, 900])
                pre = 32
                while (2 ** (32 - pre)) - 2 < need:
                    pre -= 1
                net = ipaddress.ip_network(f"{a}.{oct2}.{rng.randint(0, 3) * 4}.0/{pre}", strict=False)
                intro = f"I need a subnet that holds {need} hosts, and it should start at the block {a}.{oct2}.{net.network_address.packed[2]}.0 (rounded down to the right boundary)."
                ask = "What is the longest prefix length that still fits all of them (counting network and broadcast as unusable), and what are the network and broadcast addresses for that block?"
                contains = [f"/{pre}", str(net.network_address), str(net.broadcast_address)]
                gold = f"/{pre}, network {net.network_address}, broadcast {net.broadcast_address}"
            elif kind == "split":
                k = rng.choice([4, 8])
                pre = rng.choice([22, 23, 24])
                base = ipaddress.ip_network(f"{a}.{oct2}.{rng.randint(0, 255) // (2 ** (24 - pre)) * (2 ** (24 - pre))}.0/{pre}", strict=False)
                extra = {4: 2, 8: 3}[k]
                subs = list(base.subnets(prefixlen_diff=extra))
                j = rng.randint(2, k - 1)
                intro = f"We are carving {base} into {k} equal subnets for different teams, numbered from 1 in address order."
                ask = f"What is the CIDR of subnet {j}, and what are its first and last usable host addresses?"
                s = subs[j - 1]
                hosts = list(s.hosts())
                contains = [str(s), str(hosts[0]), str(hosts[-1])]
                gold = f"{s}, hosts {hosts[0]} - {hosts[-1]}"
            elif kind == "summarise":
                pre = 24
                start = rng.randint(0, 40) * 4
                cnt = rng.choice([4, 4, 8])
                nets = [ipaddress.ip_network(f"{a}.{oct2}.{(start + j) % 256}.0/24") for j in range(cnt)]
                coll = list(ipaddress.collapse_addresses(nets))
                if len(coll) != 1:
                    continue
                intro = f"A router needs a single summary route for these networks: " + ", ".join(str(x) for x in nets) + "."
                ask = "What is the smallest single CIDR block that covers all of them? Also, how many addresses does that block contain?"
                contains = [str(coll[0]), str(coll[0].num_addresses)]
                gold = f"{coll[0]} ({coll[0].num_addresses} addresses)"
            else:  # overlap
                nets = []
                for _ in range(5):
                    pre = rng.choice([22, 23, 24, 25, 26])
                    nets.append(ipaddress.ip_network(f"{a}.{oct2}.{rng.randint(0, 7) * 8 + rng.randint(0, 3)}.0/{pre}", strict=False))
                nets = list(dict.fromkeys(nets))
                pairs = [(x, y) for ix, x in enumerate(nets) for y in nets[ix + 1:] if x.overlaps(y)]
                if not pairs or len(nets) < 5:
                    continue
                intro = "These five allocations are supposedly disjoint: " + ", ".join(f"{chr(65 + j)} = {x}" for j, x in enumerate(nets)) + "."
                ask = "How many pairs of them overlap, and what is the largest single block (by number of addresses) among the ones that overlap something? Give the pair count then the block as CIDR."
                inv = [x for x in nets if any(x.overlaps(y) for y in nets if y != x)]
                big = max(inv, key=lambda x: (x.num_addresses, str(x)))
                if sum(1 for x in inv if x.num_addresses == big.num_addresses) != 1:
                    continue
                contains = [str(len(pairs)), str(big)]
                gold = f"{len(pairs)} overlapping pairs; largest overlapping block {big}"
            prompt = C.chat(rng, intro, ask, None, C.register_for(rng))
            keep = C.unseen(prompt, contains, True, min_keep=1)
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{kind}", prompt, d, keep, gold, fold=True, tags=["networking", "subnets"], notes={"kind": kind})
            break
        else:
            raise RuntimeError("subnet: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-file-modes


@family("chat-file-modes", category="chat", lang="bash", kind="lookup", n=8, mode="answer",
        summary="what permissions does ls show after this umask / chmod sequence (run for real with chmod and stat)")
def gen_modes(rng, n):
    plan = [2, 2, 2, 3, 3, 4, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(100):
            um = rng.choice(["022", "027", "077", "002", "037"])
            cmds = []
            pool_f = ["chmod u+x f", "chmod g-r f", "chmod o= f", "chmod a+r f", "chmod 640 f", "chmod g=u f", "chmod u-w,g+w f", "chmod go-rwx f", "chmod 0755 f", "chmod a-x f", "chmod o+w f"]
            pool_d = ["chmod g+s d", "chmod o-rx d", "chmod u-x d", "chmod a+X d", "chmod 2750 d", "chmod g+w d", "chmod 711 d", "chmod +t d", "chmod u=rwx,g=rx,o= d"]
            k = {2: 1, 3: 2, 4: 3, 5: 5}[d]
            for _ in range(k):
                cmds.append(rng.choice(pool_f))
            if d >= 3:
                for _ in range(1 if d == 3 else 2):
                    cmds.append(rng.choice(pool_d))
            script = f"umask {um}\ntouch f\nmkdir d\n" + "\n".join(cmds) + "\n"
            files = {"run.sh": script}
            res = fx.run(files, "bash run.sh >/dev/null 2>&1; stat -c '%A %a' f d", timeout=10)
            if not res.ok:
                continue
            ln = [x.strip() for x in res.out.strip().split("\n")]
            if len(ln) != 2:
                continue
            fmode, dmode = ln[0].split(" ")[0], ln[1].split(" ")[0]
            foct, doct = ln[0].split(" ")[1], ln[1].split(" ")[1]
            listing = "\n".join(["umask " + um, "touch f", "mkdir d"] + cmds)
            intro = rng.choice(["Permissions question for my deploy script. Starting from an empty directory on Linux (GNU coreutils), I run these commands in order:",
                                "I want to be sure what mode bits my files end up with. Fresh empty directory, bash, GNU chmod:",
                                "can you tell me what the permission bits look like after this sequence? empty dir, linux"])
            if d <= 2:
                ask = "What does `ls -l` show in the permission column for `f` (like -rw-r--r--), and what is its octal mode?"
                contains = [fmode, foct]
                gold = f"f: {fmode} ({foct})"
            else:
                ask = "At the end, what is the permission column that `ls -ld` shows for `f` and for `d` (like -rw-r--r-- and drwxr-xr-x), and what are the octal modes of both (include the leading special digit for d if any, as `stat -c %a` prints it)?"
                contains = [fmode, dmode, foct, doct]
                gold = f"f: {fmode} ({foct}); d: {dmode} ({doct})"
            prompt = C.chat(rng, intro, ask, C.block(listing), C.register_for(rng))
            keep = C.unseen(prompt, contains, False, min_keep=1)
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-umask{um}-d{d}", prompt, d, keep, gold, tags=["unix", "permissions"], notes={"umask": um, "cmds": cmds})
            break
        else:
            raise RuntimeError("modes: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-bitflags

DEVICES = [("pump controller", ["RUN", "FAULT", "LOW_LEVEL", "OVERTEMP", "MANUAL", "PRIMED", "LOCKED", "ALARM"]),
           ("greenhouse hub", ["HEATER", "FAN", "VENT", "DOOR", "MIST", "LIGHTS", "FROST", "SENSOR_OK"]),
           ("garage door unit", ["OPEN", "CLOSED", "MOVING", "OBSTRUCT", "LEARN", "LIGHT", "REMOTE", "ERROR"]),
           ("beehive monitor", ["WEIGHT_OK", "TEMP_HIGH", "HUMID_HIGH", "LID", "BATT_LOW", "TX", "SWARM", "CAL"])]


@family("chat-bitflags", category="chat", lang="text", kind="lookup", n=8, mode="answer",
        summary="decode and edit a status byte of an invented device: which flags are set, what is the byte after set/clear/toggle operations")
def gen_bits(rng, n):
    plan = [1, 2, 2, 3, 3, 3, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(100):
            dev, names = rng.choice(DEVICES)
            bit = list(range(8))
            rng.shuffle(bit)
            flags = {nm: b for nm, b in zip(names, bit)}
            ordered = sorted(flags.items(), key=lambda kv: kv[1])
            val = rng.randint(1, 254)
            table = "\n".join(f"bit {b}: {nm}" for nm, b in ordered)
            setnames = [nm for nm, b in ordered if val >> b & 1]
            if d == 1:
                ask = f"The device reported {val} (decimal). Which flags are set? List them in bit order starting from bit 0, and give the count."
                contains = [", ".join(setnames)] if False else [nm for nm in setnames]
                contains = [nm for nm in setnames] if False else [str(len(setnames)), setnames[0]]
                gold = f"{len(setnames)} flags: {', '.join(setnames)}"
                intro = f"I'm reading a status byte from a {dev}. Bit assignments from the vendor sheet:"
                keepc = [str(len(setnames)), val and f"{val:#04x}"]
                contains = [str(len(setnames))]
                ask = f"The device just reported 0x{val:02x}. How many flags are set, and what is the decimal value of the byte?"
                contains = [str(len(setnames)), str(val)]
                gold = f"{len(setnames)} flags set; {val} decimal"
            else:
                ops = []
                cur = val
                for _ in range({2: 1, 3: 2, 4: 3, 5: 4}[d]):
                    op = rng.choice(["set", "clear", "toggle"])
                    nm, b = rng.choice(ordered)
                    if op == "set":
                        cur |= 1 << b
                    elif op == "clear":
                        cur &= ~(1 << b) & 0xFF
                    else:
                        cur ^= 1 << b
                    ops.append((op, nm))
                if cur == val:
                    continue
                intro = f"I'm scripting a {dev}. Its status byte has these bits (vendor sheet):"
                optxt = "; ".join(f"{op} {nm}" for op, nm in ops)
                ask = f"The byte reads 0x{val:02x}. I then apply these changes in order: {optxt}. What is the final byte in hex (two digits, written like 0x2c) and as decimal?"
                contains = [f"0x{cur:02x}", str(cur)]
                if d >= 4:
                    ask += " Also, how many flags are set at the end?"
                    contains.append(f"{bin(cur).count('1')} flags")
                gold = f"0x{cur:02x} ({cur}); {bin(cur).count('1')} flags set"
            prompt = C.chat(rng, intro, ask, C.block(table), C.register_for(rng))
            keep = C.unseen(prompt, contains, True, min_keep=1)
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-{dev.split()[0]}-d{d}", prompt, d, keep, gold, fold=True, tags=["bits", "hex"], notes={"device": dev})
            break
        else:
            raise RuntimeError("bits: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-version-range


def _v(s):
    return tuple(int(x) for x in s.split("."))


def _sat(v, rule):
    t = _v(v)
    for tok in rule.split(","):
        tok = tok.strip()
        if tok.startswith("^"):
            lo = _v(tok[1:])
            hi = (lo[0] + 1, 0, 0) if lo[0] > 0 else ((0, lo[1] + 1, 0) if lo[1] > 0 else (0, 0, lo[2] + 1))
            if not (lo <= t < hi):
                return False
        elif tok.startswith("~"):
            lo = _v(tok[1:])
            if not (lo <= t < (lo[0], lo[1] + 1, 0)):
                return False
        elif tok.startswith(">="):
            if not t >= _v(tok[2:]):
                return False
        elif tok.startswith("<="):
            if not t <= _v(tok[2:]):
                return False
        elif tok.startswith(">"):
            if not t > _v(tok[1:]):
                return False
        elif tok.startswith("<"):
            if not t < _v(tok[1:]):
                return False
        elif tok.startswith("!="):
            if t == _v(tok[2:]):
                return False
        else:
            if t != _v(tok):
                return False
    return True


@family("chat-version-range", category="chat", lang="text", kind="lookup", n=8, mode="answer",
        summary="which published versions (in an attached list) satisfy a constraint written in a defined mini-syntax: caret, tilde, comparisons, exclusions")
def gen_vrange(rng, n):
    plan = [2, 2, 2, 3, 3, 4, 4, 5]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(100):
            N = {2: 10, 3: 14, 4: 20, 5: 28}[d]
            vs = set()
            while len(vs) < N:
                vs.add(f"{rng.choice([0, 0, 1, 1, 2, 3])}.{rng.randint(0, 9)}.{rng.randint(0, 9)}")
            vs = sorted(vs, key=_v)
            base = rng.choice(vs)
            hi = rng.choice(vs)
            if d == 2:
                rule = rng.choice([f"^{base}", f"~{base}"])
            elif d == 3:
                rule = rng.choice([f">={base},<{max(base, hi, key=_v)}", f"^{base},!={rng.choice(vs)}", f"~{base},>{min(vs, key=_v)}"])
            elif d == 4:
                lo2 = min(base, hi, key=_v)
                hi2 = max(base, hi, key=_v)
                rule = f">={lo2},<={hi2},!={rng.choice(vs)},!={rng.choice(vs)}"
            else:
                zero = [v for v in vs if _v(v)[0] == 0]
                b0 = rng.choice(zero) if zero else base
                rule = f"^{b0},<={max(vs, key=_v)},!={rng.choice(vs)}"
            ok = [v for v in vs if _sat(v, rule)]
            if len(ok) < 2 or len(ok) == len(vs):
                continue
            files = {"versions.txt": "\n".join(rng.sample(vs, len(vs))) + "\n"}
            intro = rng.choice(["Our package registry lists the published versions of a library in versions.txt (one per line, in no particular order).",
                                "I have a list of released versions in versions.txt and a constraint someone wrote in our internal range syntax.",
                                "versions.txt is the list of tags from the tool I'm pinning."])
            syntax = ("Range syntax (comma means AND): `^x.y.z` allows versions >= x.y.z and below the next major, except that for 0.y.z it allows only up to the next minor (so ^0.3.1 means >=0.3.1 <0.4.0), "
                      "and for 0.0.z only that exact patch; `~x.y.z` means >=x.y.z and <x.(y+1).0; `>=`, `>`, `<=`, `<` compare as expected; `!=v` excludes one version; a bare `v` means exactly v. Versions compare by numeric major, minor, patch.")
            ask = f"Which versions in versions.txt satisfy `{rule}`? Tell me how many there are, the lowest one and the highest one."
            contains = [str(len(ok)), ok[0], ok[-1]]
            gold = f"{len(ok)} versions; lowest {ok[0]}, highest {ok[-1]}"
            prompt = C.chat(rng, intro, ask, None, C.register_for(rng), spec=syntax)
            keep = C.unseen(prompt, contains, True, min_keep=2)
            if keep is None:
                continue
            yield C.answer_task(f"{i + 1:02d}-d{d}", prompt, d, keep, gold, fold=True, start=files, tags=["versions", "constraints"], notes={"rule": rule})
            break
        else:
            raise RuntimeError("vrange: no instance")
