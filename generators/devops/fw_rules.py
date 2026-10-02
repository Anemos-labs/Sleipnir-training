"""DevOps tasks: iptables rulesets (filter and nat). A documented simulator (given to the agent as tools/fwsim.py) decides what happens to packets the agent has not seen."""
import itertools
import json
import tempfile
import types
from dataclasses import dataclass, field

from fx import dd, family
from generators.devops import _dokit as K
from generators.devops._fwsim import FWSIM

_mod = types.ModuleType("fwsim")
exec(compile(FWSIM, "fwsim.py", "exec"), _mod.__dict__)
fw = _mod

CHECK_FW = r'''
from dolib import *
sys.path.insert(0, "tests")
import fwsim

spec = json.load(open("tests/cases.json", encoding="utf-8"))
try:
    rs = fwsim.parse(read(spec["path"]))
except fwsim.FwError as e:
    die(f"iptables-restore: {spec['path']}: {e}")
rep = Report()
for c in spec["cases"]:
    p = c["pkt"]
    try:
        res = fwsim.simulate(rs, p, spec["config"])
    except fwsim.FwError as e:
        rep.check(False, f"{fwsim.describe(p)}: error: {e}")
        continue
    bad = fwsim.check(res, c["expect"])
    rep.check(not bad, f"{fwsim.describe(p)}: " + "; ".join(bad))
rep.finish()
'''

DOC_NOTE = "`tools/fwsim.py` documents the exact rule syntax and the packet path that the checker simulates; `examples.json` has a few packets with the expected outcome (run `python3 tools/fwsim.py {path} examples.json`)."


def P(s_, d_, proto="tcp", sport=None, dport=None, iif=None, oif=None, state=None, icmp=None, flow=None, **expect):
    p = {"src": s_, "dst": d_, "proto": proto}
    if sport is not None:
        p["sport"] = sport
    elif proto in ("tcp", "udp"):
        p["sport"] = 40000
    if dport is not None:
        p["dport"] = dport
    for k, v in (("iif", iif), ("oif", oif), ("state", state), ("icmp_type", icmp), ("flow", flow)):
        if v is not None:
            p[k] = v
    return {"pkt": p, **({"expect": expect} if expect else {})}


@dataclass
class FwSpec:
    slug: str
    d: int
    prompt: str
    ref: str
    start: str
    config: dict
    examples: list
    cases: list
    wrong: list = field(default_factory=list)
    kind: str = "author"
    path: str = "rules.v4"


def simulate_rules(text, config, pkt):
    with tempfile.NamedTemporaryFile("w", suffix=".rules", delete=False) as f:
        f.write(text)
    return fw.simulate(fw.parse(text), pkt, config)


def make_task(sp: FwSpec):
    for c in sp.examples:
        res = simulate_rules(sp.ref, sp.config, c["pkt"])
        bad = fw.check(res, c["expect"])
        if bad:
            raise RuntimeError(f"{sp.slug}: example {c['pkt']} disagrees with the reference: {bad} (got {res})")
    cases = []
    for c in sp.examples + sp.cases:
        cases.append({"pkt": c["pkt"], "expect": simulate_rules(sp.ref, sp.config, c["pkt"])})
    start = {sp.path: sp.start, "tools/fwsim.py": FWSIM, "examples.json": json.dumps({"config": sp.config, "cases": sp.examples}, indent=1) + "\n",
             "README.md": f"# iptables exercise\n\nEdit `{sp.path}` (iptables-restore format). Run `python3 tools/fwsim.py {sp.path} examples.json` to see what the ruleset does to the example packets.\n"}
    hidden = {"tests/fwsim.py": "# verifier copy of tools/fwsim.py\n" + FWSIM, "tests/cases.json": json.dumps({"path": sp.path, "config": sp.config, "cases": cases}, indent=1) + "\n"}
    t = K.devops_task(sp.slug, sp.d, sp.prompt + "\n\n" + DOC_NOTE.format(path=sp.path), start, {sp.path: sp.ref}, CHECK_FW, hidden, lang="text", kind="fix" if sp.kind == "fix" else "greenfield",
                      tags=["iptables", "firewall", "network", "config"])
    return K.finish(t, wrong=[{sp.path: w} for w in sp.wrong])


SPECS: list[FwSpec] = []


def spec(**kw):
    SPECS.append(FwSpec(**kw))


def filt(policies, rules, extra_chains=(), nat=None):
    """Assemble an iptables-restore file."""
    out = []
    if nat:
        out += ["*nat", ":PREROUTING ACCEPT [0:0]", ":INPUT ACCEPT [0:0]", ":OUTPUT ACCEPT [0:0]", ":POSTROUTING ACCEPT [0:0]"] + nat + ["COMMIT"]
    out += ["*filter", f":INPUT {policies[0]} [0:0]", f":FORWARD {policies[1]} [0:0]", f":OUTPUT {policies[2]} [0:0]"] + [f":{c} - [0:0]" for c in extra_chains] + rules + ["COMMIT"]
    return "\n".join(out) + "\n"


HOST = {"local_ips": ["203.0.113.10"], "ifaddrs": {"eth0": "203.0.113.10"}}
ADMIN, WAN = "192.0.2.0/24", "198.51.100.77"

# 1 --------------------------------------------------------------------------------------------------------------------
spec(slug="single-host-basics", d=2, kind="author", config=HOST,
     prompt=dd('''
        Write `rules.v4` (iptables-restore format) for the single-homed server 203.0.113.10 (interface eth0, plus loopback `lo`):

        - Default policies: INPUT DROP, FORWARD DROP, OUTPUT ACCEPT.
        - Accept everything on the loopback interface, and packets of established or related connections.
        - SSH (tcp port 22) only from the admin network 192.0.2.0/24.
        - Web (tcp ports 80 and 443) from anywhere.
        - ICMP echo requests (ping) from anywhere.
        - Everything else is dropped silently.
     '''),
     start="*filter\n:INPUT ACCEPT [0:0]\n:FORWARD ACCEPT [0:0]\n:OUTPUT ACCEPT [0:0]\nCOMMIT\n",
     ref=filt(("DROP", "DROP", "ACCEPT"), ["-A INPUT -i lo -j ACCEPT", "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A INPUT -p tcp --dport 22 -s 192.0.2.0/24 -j ACCEPT", "-A INPUT -p tcp -m multiport --dports 80,443 -j ACCEPT", "-A INPUT -p icmp --icmp-type echo-request -j ACCEPT"]),
     examples=[P("192.0.2.9", "203.0.113.10", dport=22, iif="eth0", verdict="ACCEPT"), P(WAN, "203.0.113.10", dport=22, iif="eth0", verdict="DROP"), P(WAN, "203.0.113.10", dport=443, iif="eth0", verdict="ACCEPT"),
               P(WAN, "203.0.113.10", "icmp", icmp="echo-request", iif="eth0", verdict="ACCEPT")],
     cases=[P("127.0.0.1", "127.0.0.1", dport=5432, iif="lo"), P(WAN, "203.0.113.10", dport=80, iif="eth0"), P(WAN, "203.0.113.10", dport=8080, iif="eth0"), P("192.0.2.200", "203.0.113.10", dport=22, iif="eth0"), P("192.0.3.1", "203.0.113.10", dport=22, iif="eth0"),
            P(WAN, "203.0.113.10", sport=443, dport=51000, iif="eth0", state="ESTABLISHED"), P(WAN, "203.0.113.10", sport=53, dport=51000, proto="udp", iif="eth0", state="RELATED"), P(WAN, "203.0.113.10", proto="udp", dport=53, iif="eth0"),
            P(WAN, "203.0.113.10", "icmp", icmp="echo-reply", iif="eth0"), P(WAN, "203.0.113.10", "icmp", icmp="echo-request", iif="eth0"), P("192.0.2.5", "203.0.113.10", dport=3306, iif="eth0"), P(WAN, "203.0.113.10", dport=22, iif="eth0", state="ESTABLISHED"),
            P("203.0.113.10", "198.51.100.1", dport=443, oif="eth0", flow="out"), P(WAN, "10.9.9.9", dport=80, iif="eth0", oif="eth1"), P(WAN, "203.0.113.10", proto="udp", dport=443, iif="eth0")],
     wrong=[filt(("DROP", "DROP", "ACCEPT"), ["-A INPUT -i lo -j ACCEPT", "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A INPUT -p tcp --dport 22 -j ACCEPT", "-A INPUT -p tcp -m multiport --dports 80,443 -j ACCEPT", "-A INPUT -p icmp --icmp-type echo-request -j ACCEPT"])])

# 2 --------------------------------------------------------------------------------------------------------------------
spec(slug="rule-order-fix", d=3, kind="fix", config=HOST,
     prompt=dd('''
        `rules.v4` is meant to protect the web server 203.0.113.10 but the order of the rules (and one policy) defeats it. Fix it so that:

        - the abusive networks 198.51.100.0/24 and 203.0.113.64/26 are dropped first, whatever they send, even on established connections and to the web ports;
        - everyone else gets: loopback, established/related, web (tcp 80, 443) from anywhere, SSH (tcp 22) only from 192.0.2.0/24;
        - everything not listed is dropped (the default policy of INPUT must do it), and FORWARD is dropped by default too; OUTPUT is open.
     '''),
     start=filt(("ACCEPT", "ACCEPT", "ACCEPT"), ["-A INPUT -i lo -j ACCEPT", "-A INPUT -p tcp -m multiport --dports 80,443 -j ACCEPT", "-A INPUT -p tcp --dport 22 -s 192.0.2.0/24 -j ACCEPT", "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A INPUT -s 198.51.100.0/24 -j DROP", "-A INPUT -s 203.0.113.64/26 -j DROP"]),
     ref=filt(("DROP", "DROP", "ACCEPT"), ["-A INPUT -s 198.51.100.0/24 -j DROP", "-A INPUT -s 203.0.113.64/26 -j DROP", "-A INPUT -i lo -j ACCEPT", "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A INPUT -p tcp -m multiport --dports 80,443 -j ACCEPT", "-A INPUT -p tcp --dport 22 -s 192.0.2.0/24 -j ACCEPT"]),
     examples=[P("198.51.100.20", "203.0.113.10", dport=443, iif="eth0", verdict="DROP"), P("203.0.113.70", "203.0.113.10", dport=80, iif="eth0", verdict="DROP"), P("192.0.2.5", "203.0.113.10", dport=22, iif="eth0", verdict="ACCEPT"),
               P("203.0.113.20", "203.0.113.10", dport=25, iif="eth0", verdict="DROP")],
     cases=[P("198.51.100.1", "203.0.113.10", dport=80, iif="eth0"), P("198.51.100.255", "203.0.113.10", dport=22, iif="eth0"), P("198.51.100.9", "203.0.113.10", dport=443, iif="eth0", state="ESTABLISHED"), P("203.0.113.64", "203.0.113.10", dport=443, iif="eth0"),
            P("203.0.113.127", "203.0.113.10", dport=80, iif="eth0"), P("203.0.113.128", "203.0.113.10", dport=80, iif="eth0"), P("203.0.113.63", "203.0.113.10", dport=80, iif="eth0"), P("203.0.113.100", "203.0.113.10", dport=22, iif="eth0", state="RELATED"),
            P("192.0.2.77", "203.0.113.10", dport=443, iif="eth0"), P("192.0.2.77", "203.0.113.10", dport=2222, iif="eth0"), P("100.64.1.1", "203.0.113.10", dport=80, iif="eth0"), P("100.64.1.1", "203.0.113.10", dport=22, iif="eth0"), P("100.64.1.1", "203.0.113.10", dport=9999, iif="eth0"),
            P("127.0.0.1", "127.0.0.1", dport=22, iif="lo"), P("100.64.1.1", "10.0.0.7", dport=80, iif="eth0", oif="eth1"), P("100.64.1.1", "203.0.113.10", dport=80, iif="eth0", state="ESTABLISHED")],
     wrong=[filt(("DROP", "DROP", "ACCEPT"), ["-A INPUT -i lo -j ACCEPT", "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A INPUT -s 198.51.100.0/24 -j DROP", "-A INPUT -s 203.0.113.64/26 -j DROP", "-A INPUT -p tcp -m multiport --dports 80,443 -j ACCEPT", "-A INPUT -p tcp --dport 22 -s 192.0.2.0/24 -j ACCEPT"])])

# 3 --------------------------------------------------------------------------------------------------------------------
DB = {"local_ips": ["10.20.0.5"], "ifaddrs": {"eth0": "10.20.0.5"}}
spec(slug="db-allowlist-chain", d=3, kind="author", config=DB,
     prompt=dd('''
        Write `rules.v4` for the database host 10.20.0.5 (eth0). INPUT policy DROP, FORWARD DROP, OUTPUT ACCEPT. Use a user chain named `DBACCESS` for the PostgreSQL rules (tcp port 5432):

        - loopback and established/related traffic are accepted first;
        - PostgreSQL is accepted from 10.20.0.0/16 and from the single host 10.30.0.5;
        - PostgreSQL attempts from anywhere else are logged with the prefix `db-denied ` (note the trailing space) and then dropped;
        - SSH (tcp 22) only from 10.20.1.0/24;
        - monitoring: tcp port 9187 only from 10.20.2.10 and 10.20.2.11.
        Everything else is dropped by the policy (not logged).
     '''),
     start="*filter\n:INPUT ACCEPT [0:0]\n:FORWARD ACCEPT [0:0]\n:OUTPUT ACCEPT [0:0]\nCOMMIT\n",
     ref=filt(("DROP", "DROP", "ACCEPT"), ["-A INPUT -i lo -j ACCEPT", "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A INPUT -p tcp --dport 5432 -j DBACCESS", "-A INPUT -p tcp --dport 22 -s 10.20.1.0/24 -j ACCEPT",
                                         "-A INPUT -p tcp --dport 9187 -s 10.20.2.10 -j ACCEPT", "-A INPUT -p tcp --dport 9187 -s 10.20.2.11 -j ACCEPT",
                                         "-A DBACCESS -s 10.20.0.0/16 -j ACCEPT", "-A DBACCESS -s 10.30.0.5 -j ACCEPT", '-A DBACCESS -j LOG --log-prefix "db-denied "', "-A DBACCESS -j DROP"], extra_chains=["DBACCESS"]),
     examples=[P("10.20.7.7", "10.20.0.5", dport=5432, iif="eth0", verdict="ACCEPT"), P("10.31.0.5", "10.20.0.5", dport=5432, iif="eth0", verdict="DROP", log=["db-denied "]), P("10.20.2.10", "10.20.0.5", dport=9187, iif="eth0", verdict="ACCEPT")],
     cases=[P("10.20.0.1", "10.20.0.5", dport=5432, iif="eth0"), P("10.20.255.254", "10.20.0.5", dport=5432, iif="eth0"), P("10.21.0.1", "10.20.0.5", dport=5432, iif="eth0"), P("10.30.0.5", "10.20.0.5", dport=5432, iif="eth0"), P("10.30.0.6", "10.20.0.5", dport=5432, iif="eth0"),
            P("8.8.8.8", "10.20.0.5", dport=5432, iif="eth0"), P("10.20.1.9", "10.20.0.5", dport=22, iif="eth0"), P("10.20.2.9", "10.20.0.5", dport=22, iif="eth0"), P("10.20.2.11", "10.20.0.5", dport=9187, iif="eth0"), P("10.20.2.12", "10.20.0.5", dport=9187, iif="eth0"),
            P("10.20.2.10", "10.20.0.5", dport=22, iif="eth0"), P("10.20.0.9", "10.20.0.5", proto="udp", dport=5432, iif="eth0"), P("10.20.0.9", "10.20.0.5", dport=3306, iif="eth0"), P("10.99.0.9", "10.20.0.5", dport=5432, iif="eth0", state="ESTABLISHED"),
            P("127.0.0.1", "127.0.0.1", dport=5432, iif="lo"), P("10.20.0.5", "10.20.0.77", dport=5432, oif="eth0", flow="out")],
     wrong=[filt(("DROP", "DROP", "ACCEPT"), ["-A INPUT -i lo -j ACCEPT", "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A INPUT -p tcp --dport 5432 -j DBACCESS", "-A INPUT -p tcp --dport 22 -s 10.20.1.0/24 -j ACCEPT", "-A INPUT -p tcp --dport 9187 -j ACCEPT",
                                         "-A DBACCESS -s 10.20.0.0/16 -j ACCEPT", "-A DBACCESS -s 10.30.0.5 -j ACCEPT", '-A DBACCESS -j LOG --log-prefix "db-denied "', "-A DBACCESS -j DROP"], extra_chains=["DBACCESS"])])

# 4 --------------------------------------------------------------------------------------------------------------------
LAB = {"local_ips": ["172.16.4.2"], "ifaddrs": {"eth0": "172.16.4.2"}}
spec(slug="ports-ranges-negation", d=3, kind="author", config=LAB,
     prompt=dd('''
        Write `rules.v4` for the lab gateway 172.16.4.2 (eth0). INPUT policy DROP, FORWARD DROP, OUTPUT ACCEPT. After the usual loopback and established/related rules, accept on INPUT:

        - tcp ports 8000 to 8100 (inclusive) only from 10.0.0.0/8;
        - udp ports 5000 to 5010 (inclusive) from anywhere **except** the network 10.99.0.0/16;
        - DNS (port 53, both tcp and udp) only from the LAN 192.168.10.0/24;
        - NTP (udp port 123) from anywhere;
        - tcp port 25 from nowhere but 192.168.10.25;
        - ICMP echo requests from anywhere except 203.0.113.0/24.
        Everything else is dropped by the policy.
     '''),
     start="*filter\n:INPUT ACCEPT [0:0]\n:FORWARD ACCEPT [0:0]\n:OUTPUT ACCEPT [0:0]\nCOMMIT\n",
     ref=filt(("DROP", "DROP", "ACCEPT"), ["-A INPUT -i lo -j ACCEPT", "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A INPUT -p tcp --dport 8000:8100 -s 10.0.0.0/8 -j ACCEPT", "-A INPUT -p udp --dport 5000:5010 ! -s 10.99.0.0/16 -j ACCEPT",
                                         "-A INPUT -p tcp --dport 53 -s 192.168.10.0/24 -j ACCEPT", "-A INPUT -p udp --dport 53 -s 192.168.10.0/24 -j ACCEPT", "-A INPUT -p udp --dport 123 -j ACCEPT", "-A INPUT -p tcp --dport 25 -s 192.168.10.25 -j ACCEPT",
                                         "-A INPUT -p icmp --icmp-type echo-request ! -s 203.0.113.0/24 -j ACCEPT"]),
     examples=[P("10.1.1.1", "172.16.4.2", dport=8100, iif="eth0", verdict="ACCEPT"), P("10.99.1.1", "172.16.4.2", "udp", dport=5005, iif="eth0", verdict="DROP"), P("192.168.10.7", "172.16.4.2", "udp", dport=53, iif="eth0", verdict="ACCEPT"),
               P("203.0.113.9", "172.16.4.2", "icmp", icmp="echo-request", iif="eth0", verdict="DROP")],
     cases=[P("10.1.1.1", "172.16.4.2", dport=8000, iif="eth0"), P("10.1.1.1", "172.16.4.2", dport=7999, iif="eth0"), P("10.1.1.1", "172.16.4.2", dport=8101, iif="eth0"), P("11.1.1.1", "172.16.4.2", dport=8050, iif="eth0"), P("10.1.1.1", "172.16.4.2", "udp", dport=8050, iif="eth0"),
            P("1.2.3.4", "172.16.4.2", "udp", dport=5000, iif="eth0"), P("1.2.3.4", "172.16.4.2", "udp", dport=5010, iif="eth0"), P("1.2.3.4", "172.16.4.2", "udp", dport=5011, iif="eth0"), P("1.2.3.4", "172.16.4.2", "tcp", dport=5005, iif="eth0"), P("10.98.255.255", "172.16.4.2", "udp", dport=5005, iif="eth0"),
            P("10.100.0.1", "172.16.4.2", "udp", dport=5005, iif="eth0"), P("192.168.10.7", "172.16.4.2", "tcp", dport=53, iif="eth0"), P("192.168.11.7", "172.16.4.2", "tcp", dport=53, iif="eth0"), P("192.168.11.7", "172.16.4.2", "udp", dport=53, iif="eth0"),
            P("9.9.9.9", "172.16.4.2", "udp", dport=123, iif="eth0"), P("9.9.9.9", "172.16.4.2", "tcp", dport=123, iif="eth0"), P("192.168.10.25", "172.16.4.2", dport=25, iif="eth0"), P("192.168.10.26", "172.16.4.2", dport=25, iif="eth0"), P("192.168.10.25", "172.16.4.2", "udp", dport=25, iif="eth0"),
            P("8.8.8.8", "172.16.4.2", "icmp", icmp="echo-request", iif="eth0"), P("203.0.113.200", "172.16.4.2", "icmp", icmp="echo-request", iif="eth0"), P("8.8.8.8", "172.16.4.2", "icmp", icmp="echo-reply", iif="eth0"), P("203.0.114.1", "172.16.4.2", "icmp", icmp=8, iif="eth0")],
     wrong=[filt(("DROP", "DROP", "ACCEPT"), ["-A INPUT -i lo -j ACCEPT", "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A INPUT -p tcp --dport 8000:8100 -s 10.0.0.0/8 -j ACCEPT", "-A INPUT -p udp --dport 5000:5010 -j ACCEPT",
                                         "-A INPUT -p tcp --dport 53 -s 192.168.10.0/24 -j ACCEPT", "-A INPUT -p udp --dport 53 -s 192.168.10.0/24 -j ACCEPT", "-A INPUT -p udp --dport 123 -j ACCEPT", "-A INPUT -p tcp --dport 25 -s 192.168.10.25 -j ACCEPT",
                                         "-A INPUT -p icmp --icmp-type echo-request ! -s 203.0.113.0/24 -j ACCEPT"])])

# 5 --------------------------------------------------------------------------------------------------------------------
CLI = {"local_ips": ["10.1.1.10"], "ifaddrs": {"eth0": "10.1.1.10"}}
spec(slug="egress-allowlist", d=3, kind="author", config=CLI,
     prompt=dd('''
        Write `rules.v4` for the locked-down workstation 10.1.1.10 (eth0) whose outgoing traffic is restricted. INPUT policy DROP, FORWARD DROP, OUTPUT policy DROP. Rules:

        - INPUT: loopback and established/related traffic only;
        - OUTPUT: loopback and established/related traffic;
        - DNS (port 53, udp and tcp) only to the resolvers 192.0.2.53 and 192.0.2.54;
        - HTTPS (tcp 443) only to the package mirror network 203.0.113.0/28;
        - NTP (udp 123) only to 192.0.2.123;
        - ICMP echo requests to anywhere;
        - every other outgoing packet is logged with the prefix `egress-drop ` and then dropped (so the log rule is the last rule of OUTPUT).
     '''),
     start="*filter\n:INPUT ACCEPT [0:0]\n:FORWARD ACCEPT [0:0]\n:OUTPUT ACCEPT [0:0]\nCOMMIT\n",
     ref=filt(("DROP", "DROP", "DROP"), ["-A INPUT -i lo -j ACCEPT", "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A OUTPUT -o lo -j ACCEPT", "-A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT",
                                         "-A OUTPUT -p udp -d 192.0.2.53 --dport 53 -j ACCEPT", "-A OUTPUT -p udp -d 192.0.2.54 --dport 53 -j ACCEPT", "-A OUTPUT -p tcp -d 192.0.2.53 --dport 53 -j ACCEPT", "-A OUTPUT -p tcp -d 192.0.2.54 --dport 53 -j ACCEPT",
                                         "-A OUTPUT -p tcp -d 203.0.113.0/28 --dport 443 -j ACCEPT", "-A OUTPUT -p udp -d 192.0.2.123 --dport 123 -j ACCEPT", "-A OUTPUT -p icmp --icmp-type echo-request -j ACCEPT",
                                         '-A OUTPUT -j LOG --log-prefix "egress-drop "']),
     examples=[P("10.1.1.10", "192.0.2.53", "udp", dport=53, oif="eth0", flow="out", verdict="ACCEPT"), P("10.1.1.10", "8.8.8.8", "udp", dport=53, oif="eth0", flow="out", verdict="DROP", log=["egress-drop "]),
               P("10.1.1.10", "203.0.113.5", dport=443, oif="eth0", flow="out", verdict="ACCEPT")],
     cases=[P("10.1.1.10", "192.0.2.54", "tcp", dport=53, oif="eth0", flow="out"), P("10.1.1.10", "192.0.2.55", "udp", dport=53, oif="eth0", flow="out"), P("10.1.1.10", "203.0.113.15", dport=443, oif="eth0", flow="out"), P("10.1.1.10", "203.0.113.16", dport=443, oif="eth0", flow="out"),
            P("10.1.1.10", "203.0.113.5", dport=80, oif="eth0", flow="out"), P("10.1.1.10", "192.0.2.123", "udp", dport=123, oif="eth0", flow="out"), P("10.1.1.10", "192.0.2.124", "udp", dport=123, oif="eth0", flow="out"), P("10.1.1.10", "9.9.9.9", "icmp", icmp="echo-request", oif="eth0", flow="out"),
            P("10.1.1.10", "9.9.9.9", "icmp", icmp="echo-reply", oif="eth0", flow="out"), P("127.0.0.1", "127.0.0.1", dport=8080, oif="lo", flow="out"), P("10.1.1.10", "1.1.1.1", dport=443, oif="eth0", flow="out", state="ESTABLISHED"), P("10.1.1.10", "1.1.1.1", dport=22, oif="eth0", flow="out"),
            P("9.9.9.9", "10.1.1.10", dport=22, iif="eth0"), P("9.9.9.9", "10.1.1.10", sport=443, dport=44444, iif="eth0", state="ESTABLISHED"), P("127.0.0.1", "127.0.0.1", dport=22, iif="lo")],
     wrong=[filt(("DROP", "DROP", "DROP"), ["-A INPUT -i lo -j ACCEPT", "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A OUTPUT -o lo -j ACCEPT", "-A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT",
                                         "-A OUTPUT -p udp --dport 53 -j ACCEPT", "-A OUTPUT -p tcp --dport 53 -j ACCEPT", "-A OUTPUT -p tcp -d 203.0.113.0/28 --dport 443 -j ACCEPT", "-A OUTPUT -p udp -d 192.0.2.123 --dport 123 -j ACCEPT", "-A OUTPUT -p icmp --icmp-type echo-request -j ACCEPT",
                                         '-A OUTPUT -j LOG --log-prefix "egress-drop "'])])

# 6 --------------------------------------------------------------------------------------------------------------------
GW = {"local_ips": ["203.0.113.2", "10.0.1.1"], "ifaddrs": {"eth0": "203.0.113.2", "eth1": "10.0.1.1"}}
spec(slug="port-forward-gateway", d=4, kind="author", config=GW,
     prompt=dd('''
        Write `rules.v4` for the gateway with WAN interface eth0 (203.0.113.2) and LAN interface eth1 (10.0.1.1/24). Tables `nat` and `filter`:

        - Port forwards (new connections arriving on eth0): tcp port 8080 to the web server 10.0.1.5 port 80; tcp port 2222 to 10.0.1.6 port 22, **only when the client is in 192.0.2.0/24** (others are not forwarded).
        - LAN hosts (10.0.1.0/24, arriving on eth1) are NATed to the WAN address when they leave through eth0 (`MASQUERADE`).
        - Filter: INPUT policy DROP with loopback, established/related and SSH (tcp 22) from the LAN only; FORWARD policy DROP: established/related are forwarded; the two forwarded services are accepted (remember: the filter table sees the destination *after* DNAT);
          the LAN may go anywhere on the WAN (eth1 -> eth0); nothing else is forwarded; OUTPUT policy ACCEPT.
     '''),
     start="*filter\n:INPUT ACCEPT [0:0]\n:FORWARD ACCEPT [0:0]\n:OUTPUT ACCEPT [0:0]\nCOMMIT\n",
     ref=filt(("DROP", "DROP", "ACCEPT"), ["-A INPUT -i lo -j ACCEPT", "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A INPUT -i eth1 -p tcp --dport 22 -j ACCEPT",
                                         "-A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A FORWARD -i eth0 -d 10.0.1.5 -p tcp --dport 80 -j ACCEPT", "-A FORWARD -i eth0 -d 10.0.1.6 -p tcp --dport 22 -j ACCEPT", "-A FORWARD -i eth1 -o eth0 -j ACCEPT"],
                nat=["-A PREROUTING -i eth0 -p tcp --dport 8080 -j DNAT --to-destination 10.0.1.5:80", "-A PREROUTING -i eth0 -p tcp --dport 2222 -s 192.0.2.0/24 -j DNAT --to-destination 10.0.1.6:22", "-A POSTROUTING -s 10.0.1.0/24 -o eth0 -j MASQUERADE"]),
     examples=[P(WAN, "203.0.113.2", dport=8080, iif="eth0", oif="eth1", verdict="ACCEPT", dst="10.0.1.5:80"), P("192.0.2.7", "203.0.113.2", dport=2222, iif="eth0", oif="eth1", verdict="ACCEPT", dst="10.0.1.6:22"),
               P(WAN, "203.0.113.2", dport=2222, iif="eth0", verdict="DROP"), P("10.0.1.20", "93.184.216.34", dport=443, iif="eth1", oif="eth0", verdict="ACCEPT", src="203.0.113.2:40000")],
     cases=[P("1.2.3.4", "203.0.113.2", dport=8080, sport=1234, iif="eth0", oif="eth1"), P("1.2.3.4", "203.0.113.2", dport=8081, iif="eth0", oif="eth1"), P("1.2.3.4", "203.0.113.2", dport=80, iif="eth0"), P("192.0.2.200", "203.0.113.2", dport=2222, sport=50000, iif="eth0", oif="eth1"),
            P("192.0.3.200", "203.0.113.2", dport=2222, iif="eth0", oif="eth1"), P("1.2.3.4", "203.0.113.2", dport=22, iif="eth0"), P("10.0.1.9", "10.0.1.1", dport=22, iif="eth1"), P("10.0.1.9", "10.0.1.1", dport=80, iif="eth1"), P("10.0.1.9", "8.8.8.8", "udp", dport=53, iif="eth1", oif="eth0"),
            P("10.0.1.9", "10.0.1.5", dport=80, iif="eth1", oif="eth1"), P("10.0.1.5", "1.2.3.4", sport=80, dport=1234, iif="eth1", oif="eth0", state="ESTABLISHED"), P("1.2.3.4", "10.0.1.9", dport=22, iif="eth0", oif="eth1"), P("1.2.3.4", "10.0.1.5", sport=1234, dport=80, iif="eth0", oif="eth1", state="ESTABLISHED"),
            P("1.2.3.4", "203.0.113.2", sport=1234, dport=8080, iif="eth0", oif="eth1", state="ESTABLISHED"), P("1.2.3.4", "203.0.113.2", "icmp", icmp="echo-request", iif="eth0"), P("10.0.1.9", "203.0.113.2", dport=22, iif="eth1"), P("10.0.1.77", "1.2.3.4", dport=8080, iif="eth1", oif="eth0")],
     wrong=[filt(("DROP", "DROP", "ACCEPT"), ["-A INPUT -i lo -j ACCEPT", "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A INPUT -i eth1 -p tcp --dport 22 -j ACCEPT",
                                         "-A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A FORWARD -i eth0 -d 203.0.113.2 -p tcp --dport 8080 -j ACCEPT", "-A FORWARD -i eth0 -d 203.0.113.2 -p tcp --dport 2222 -j ACCEPT", "-A FORWARD -i eth1 -o eth0 -j ACCEPT"],
                 nat=["-A PREROUTING -i eth0 -p tcp --dport 8080 -j DNAT --to-destination 10.0.1.5:80", "-A PREROUTING -i eth0 -p tcp --dport 2222 -s 192.0.2.0/24 -j DNAT --to-destination 10.0.1.6:22", "-A POSTROUTING -s 10.0.1.0/24 -o eth0 -j MASQUERADE"])])

# 7 --------------------------------------------------------------------------------------------------------------------
spec(slug="dnat-forward-fix", d=4, kind="fix", config=GW,
     prompt=dd('''
        After the port forwards were added to `rules.v4` nobody from the Internet can reach the internal web server and the LAN has lost its Internet access. The intended behaviour: tcp 8080 on the WAN address is forwarded to 10.0.1.5:80 and reaches the server;
        LAN hosts (10.0.1.0/24 on eth1) go out through eth0 with the WAN address as the source; established traffic flows back; everything else forwarded is dropped (FORWARD policy DROP). Fix the ruleset (it uses a `nat` and a `filter` table).
     '''),
     start=filt(("DROP", "DROP", "ACCEPT"), ["-A INPUT -i lo -j ACCEPT", "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A INPUT -i eth1 -p tcp --dport 22 -j ACCEPT", "-A FORWARD -i eth0 -d 203.0.113.2 -p tcp --dport 8080 -j ACCEPT", "-A FORWARD -i eth0 -o eth1 -m conntrack --ctstate ESTABLISHED -j ACCEPT"],
                nat=["-A PREROUTING -i eth0 -p tcp --dport 8080 -j DNAT --to-destination 10.0.1.5:80", "-A POSTROUTING -s 10.0.1.0/24 -o eth1 -j MASQUERADE"]),
     ref=filt(("DROP", "DROP", "ACCEPT"), ["-A INPUT -i lo -j ACCEPT", "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A INPUT -i eth1 -p tcp --dport 22 -j ACCEPT", "-A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT",
                                         "-A FORWARD -i eth0 -d 10.0.1.5 -p tcp --dport 80 -j ACCEPT", "-A FORWARD -i eth1 -o eth0 -s 10.0.1.0/24 -j ACCEPT"],
                nat=["-A PREROUTING -i eth0 -p tcp --dport 8080 -j DNAT --to-destination 10.0.1.5:80", "-A POSTROUTING -s 10.0.1.0/24 -o eth0 -j MASQUERADE"]),
     examples=[P("1.2.3.4", "203.0.113.2", dport=8080, iif="eth0", oif="eth1", verdict="ACCEPT", dst="10.0.1.5:80"), P("10.0.1.30", "9.9.9.9", dport=443, iif="eth1", oif="eth0", verdict="ACCEPT", src="203.0.113.2:40000")],
     cases=[P("1.2.3.4", "203.0.113.2", dport=8080, iif="eth0", oif="eth1"), P("1.2.3.4", "203.0.113.2", dport=8080, iif="eth0", oif="eth1", state="ESTABLISHED"), P("1.2.3.4", "203.0.113.2", dport=80, iif="eth0", oif="eth1"), P("1.2.3.4", "10.0.1.5", dport=80, iif="eth0", oif="eth1"),
            P("1.2.3.4", "10.0.1.5", dport=22, iif="eth0", oif="eth1"), P("10.0.1.30", "9.9.9.9", "udp", dport=53, iif="eth1", oif="eth0"), P("10.0.1.31", "9.9.9.9", dport=22, iif="eth1", oif="eth0"), P("10.0.2.31", "9.9.9.9", dport=22, iif="eth1", oif="eth0"),
            P("9.9.9.9", "10.0.1.30", sport=443, dport=51000, iif="eth0", oif="eth1", state="ESTABLISHED"), P("9.9.9.9", "10.0.1.30", sport=443, dport=51000, iif="eth0", oif="eth1", state="NEW"), P("10.0.1.30", "10.0.1.5", dport=80, iif="eth1", oif="eth1"),
            P("10.0.1.5", "9.9.9.9", sport=80, dport=51000, iif="eth1", oif="eth0", state="ESTABLISHED"), P("10.0.1.30", "10.0.1.1", dport=22, iif="eth1"), P("1.2.3.4", "203.0.113.2", dport=22, iif="eth0")],
     wrong=[filt(("DROP", "DROP", "ACCEPT"), ["-A INPUT -i lo -j ACCEPT", "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A INPUT -i eth1 -p tcp --dport 22 -j ACCEPT", "-A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT",
                                         "-A FORWARD -i eth0 -d 10.0.1.5 -p tcp --dport 80 -j ACCEPT", "-A FORWARD -i eth1 -o eth0 -j ACCEPT"],
                 nat=["-A PREROUTING -i eth0 -p tcp --dport 8080 -j DNAT --to-destination 10.0.1.5:80"])])

# 8 --------------------------------------------------------------------------------------------------------------------
RT = {"local_ips": ["203.0.113.2", "10.0.1.1", "10.0.9.1", "10.0.2.1"], "ifaddrs": {"eth0": "203.0.113.2", "eth1": "10.0.1.1", "eth2": "10.0.9.1", "eth3": "10.0.2.1"}}
PRIV = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
spec(slug="segmented-router", d=4, kind="author", config=RT,
     prompt=dd('''
        Write `rules.v4` for a router with four interfaces: eth0 = WAN (203.0.113.2), eth1 = staff LAN 10.0.1.0/24, eth2 = guest network 10.0.9.0/24, eth3 = servers 10.0.2.0/24. INPUT policy DROP, FORWARD policy DROP, OUTPUT ACCEPT.

        - INPUT: loopback, established/related; SSH to the router (tcp 22) only from the staff LAN; DNS (udp 53) from the staff and guest networks to the router.
        - FORWARD: established/related are forwarded. Staff -> WAN: anything. Staff -> servers: only tcp ports 22 and 443, and ICMP echo requests. Guest -> WAN: only tcp 80 and 443 and DNS (udp 53), and **never to a private address range**
          (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 : write the guest rules so that the private destinations are refused first). Servers -> WAN: only tcp 443 and udp 53. Everything else is dropped.
        - NAT: everything that leaves through eth0 from 10.0.0.0/8 is masqueraded.
     '''),
     start="*filter\n:INPUT ACCEPT [0:0]\n:FORWARD ACCEPT [0:0]\n:OUTPUT ACCEPT [0:0]\nCOMMIT\n",
     ref=filt(("DROP", "DROP", "ACCEPT"), ["-A INPUT -i lo -j ACCEPT", "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A INPUT -i eth1 -p tcp --dport 22 -j ACCEPT", "-A INPUT -i eth1 -p udp --dport 53 -j ACCEPT", "-A INPUT -i eth2 -p udp --dport 53 -j ACCEPT",
                                         "-A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A FORWARD -i eth1 -o eth0 -j ACCEPT", "-A FORWARD -i eth1 -o eth3 -p tcp -m multiport --dports 22,443 -j ACCEPT", "-A FORWARD -i eth1 -o eth3 -p icmp --icmp-type echo-request -j ACCEPT",
                                         "-A FORWARD -i eth2 -d 10.0.0.0/8 -j DROP", "-A FORWARD -i eth2 -d 172.16.0.0/12 -j DROP", "-A FORWARD -i eth2 -d 192.168.0.0/16 -j DROP", "-A FORWARD -i eth2 -o eth0 -p tcp -m multiport --dports 80,443 -j ACCEPT", "-A FORWARD -i eth2 -o eth0 -p udp --dport 53 -j ACCEPT",
                                         "-A FORWARD -i eth3 -o eth0 -p tcp --dport 443 -j ACCEPT", "-A FORWARD -i eth3 -o eth0 -p udp --dport 53 -j ACCEPT"], nat=["-A POSTROUTING -s 10.0.0.0/8 -o eth0 -j MASQUERADE"]),
     examples=[P("10.0.1.50", "8.8.8.8", "udp", dport=53, iif="eth1", oif="eth0", verdict="ACCEPT", src="203.0.113.2:40000"), P("10.0.9.50", "10.0.1.50", dport=80, iif="eth2", oif="eth1", verdict="DROP"), P("10.0.9.50", "93.184.216.34", dport=443, iif="eth2", oif="eth0", verdict="ACCEPT"),
               P("10.0.1.50", "10.0.2.9", dport=3306, iif="eth1", oif="eth3", verdict="DROP")],
     cases=[P("10.0.1.50", "10.0.2.9", dport=22, iif="eth1", oif="eth3"), P("10.0.1.50", "10.0.2.9", dport=443, iif="eth1", oif="eth3"), P("10.0.1.50", "10.0.2.9", "icmp", icmp="echo-request", iif="eth1", oif="eth3"), P("10.0.1.50", "10.0.2.9", "udp", dport=443, iif="eth1", oif="eth3"),
            P("10.0.9.50", "10.0.2.9", dport=443, iif="eth2", oif="eth3"), P("10.0.9.50", "192.168.1.1", dport=443, iif="eth2", oif="eth0"), P("10.0.9.50", "172.20.0.1", dport=80, iif="eth2", oif="eth0"), P("10.0.9.50", "172.32.0.1", dport=80, iif="eth2", oif="eth0"),
            P("10.0.9.50", "172.15.0.1", dport=80, iif="eth2", oif="eth0"), P("10.0.9.50", "8.8.8.8", "udp", dport=53, iif="eth2", oif="eth0"), P("10.0.9.50", "8.8.8.8", "tcp", dport=53, iif="eth2", oif="eth0"), P("10.0.9.50", "8.8.8.8", dport=22, iif="eth2", oif="eth0"),
            P("10.0.9.50", "10.0.9.1", "udp", dport=53, iif="eth2"), P("10.0.9.50", "10.0.9.1", dport=22, iif="eth2"), P("10.0.1.50", "10.0.1.1", dport=22, iif="eth1"), P("10.0.2.9", "9.9.9.9", dport=443, iif="eth3", oif="eth0"), P("10.0.2.9", "9.9.9.9", dport=25, iif="eth3", oif="eth0"),
            P("10.0.2.9", "10.0.1.50", dport=22, iif="eth3", oif="eth1"), P("10.0.2.9", "9.9.9.9", "udp", dport=53, iif="eth3", oif="eth0"), P("9.9.9.9", "10.0.1.50", sport=443, dport=50000, iif="eth0", oif="eth1", state="ESTABLISHED"), P("9.9.9.9", "10.0.1.50", dport=22, iif="eth0", oif="eth1"),
            P("9.9.9.9", "203.0.113.2", dport=22, iif="eth0"), P("10.0.1.50", "9.9.9.9", dport=25, iif="eth1", oif="eth0"), P("10.0.2.9", "10.0.2.10", dport=22, iif="eth3", oif="eth3")],
     wrong=[filt(("DROP", "DROP", "ACCEPT"), ["-A INPUT -i lo -j ACCEPT", "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A INPUT -i eth1 -p tcp --dport 22 -j ACCEPT", "-A INPUT -i eth1 -p udp --dport 53 -j ACCEPT", "-A INPUT -i eth2 -p udp --dport 53 -j ACCEPT",
                                         "-A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A FORWARD -i eth1 -o eth0 -j ACCEPT", "-A FORWARD -i eth1 -o eth3 -p tcp -m multiport --dports 22,443 -j ACCEPT", "-A FORWARD -i eth1 -o eth3 -p icmp --icmp-type echo-request -j ACCEPT",
                                         "-A FORWARD -i eth2 -p tcp -m multiport --dports 80,443 -j ACCEPT", "-A FORWARD -i eth2 -p udp --dport 53 -j ACCEPT",
                                         "-A FORWARD -i eth3 -o eth0 -p tcp --dport 443 -j ACCEPT", "-A FORWARD -i eth3 -o eth0 -p udp --dport 53 -j ACCEPT"], nat=["-A POSTROUTING -s 10.0.0.0/8 -o eth0 -j MASQUERADE"])])

# 9 --------------------------------------------------------------------------------------------------------------------
PX = {"local_ips": ["10.0.1.1", "203.0.113.2"], "ifaddrs": {"eth0": "203.0.113.2", "eth1": "10.0.1.1"}}
spec(slug="transparent-proxy-redirect", d=3, kind="author", config=PX,
     prompt=dd('''
        The gateway (WAN eth0 203.0.113.2, LAN eth1 10.0.1.1, 10.0.1.0/24) runs a caching proxy on tcp port 3128 and must silently send all web traffic of the LAN through it.

        - nat: new tcp connections arriving on eth1 for destination port 80 are redirected to local port 3128 (`REDIRECT`), except those whose destination is inside the LAN itself (10.0.1.0/24).
        - filter INPUT (policy DROP): loopback, established/related, tcp 3128 from the LAN (eth1), tcp 22 from the LAN.
        - filter FORWARD (policy DROP): established/related; LAN (eth1) to the WAN (eth0) tcp 443 and 53 (tcp and udp). Plain web traffic (port 80) is never forwarded directly, it only reaches the proxy through the redirect.
        - nat POSTROUTING: masquerade LAN traffic leaving through eth0. OUTPUT policy ACCEPT.
     '''),
     start="*filter\n:INPUT ACCEPT [0:0]\n:FORWARD ACCEPT [0:0]\n:OUTPUT ACCEPT [0:0]\nCOMMIT\n",
     ref=filt(("DROP", "DROP", "ACCEPT"), ["-A INPUT -i lo -j ACCEPT", "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A INPUT -i eth1 -p tcp --dport 3128 -j ACCEPT", "-A INPUT -i eth1 -p tcp --dport 22 -j ACCEPT",
                                         "-A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A FORWARD -i eth1 -o eth0 -p tcp --dport 443 -j ACCEPT", "-A FORWARD -i eth1 -o eth0 -p tcp --dport 53 -j ACCEPT", "-A FORWARD -i eth1 -o eth0 -p udp --dport 53 -j ACCEPT"],
                nat=["-A PREROUTING -i eth1 -p tcp --dport 80 ! -d 10.0.1.0/24 -j REDIRECT --to-ports 3128", "-A POSTROUTING -s 10.0.1.0/24 -o eth0 -j MASQUERADE"]),
     examples=[P("10.0.1.40", "93.184.216.34", dport=80, iif="eth1", oif="eth0", verdict="ACCEPT", dst="10.0.1.1:3128"), P("10.0.1.40", "93.184.216.34", dport=443, iif="eth1", oif="eth0", verdict="ACCEPT", src="203.0.113.2:40000"),
               P("10.0.1.40", "10.0.1.99", dport=80, iif="eth1", oif="eth1", verdict="DROP")],
     cases=[P("10.0.1.40", "1.2.3.4", dport=80, iif="eth1", oif="eth0", state="ESTABLISHED"), P("10.0.1.40", "1.2.3.4", dport=8080, iif="eth1", oif="eth0"), P("10.0.1.40", "10.0.1.1", dport=3128, iif="eth1"), P("10.0.1.40", "10.0.1.1", dport=80, iif="eth1"),
            P("10.0.1.40", "10.0.1.1", dport=22, iif="eth1"), P("1.2.3.4", "203.0.113.2", dport=3128, iif="eth0"), P("1.2.3.4", "203.0.113.2", dport=80, iif="eth0"), P("1.2.3.4", "203.0.113.2", dport=22, iif="eth0"), P("10.0.1.40", "8.8.8.8", "udp", dport=53, iif="eth1", oif="eth0"),
            P("10.0.1.40", "8.8.8.8", "tcp", dport=53, iif="eth1", oif="eth0"), P("10.0.1.40", "8.8.8.8", "udp", dport=123, iif="eth1", oif="eth0"), P("10.0.1.40", "1.2.3.4", dport=22, iif="eth1", oif="eth0"), P("1.2.3.4", "10.0.1.40", dport=80, iif="eth0", oif="eth1"),
            P("203.0.113.5", "203.0.113.2", dport=80, iif="eth0"), P("10.0.1.40", "10.0.1.50", dport=443, iif="eth1", oif="eth1")],
     wrong=[filt(("DROP", "DROP", "ACCEPT"), ["-A INPUT -i lo -j ACCEPT", "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A INPUT -i eth1 -p tcp --dport 3128 -j ACCEPT", "-A INPUT -i eth1 -p tcp --dport 22 -j ACCEPT",
                                         "-A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A FORWARD -i eth1 -o eth0 -p tcp --dport 443 -j ACCEPT", "-A FORWARD -i eth1 -o eth0 -p tcp --dport 53 -j ACCEPT", "-A FORWARD -i eth1 -o eth0 -p udp --dport 53 -j ACCEPT"],
                 nat=["-A PREROUTING -i eth1 -p tcp --dport 80 -j REDIRECT --to-ports 3128", "-A POSTROUTING -s 10.0.1.0/24 -o eth0 -j MASQUERADE"])])

# 10 -------------------------------------------------------------------------------------------------------------------
spec(slug="log-then-drop-scans", d=2, kind="author", config=HOST,
     prompt=dd('''
        Write `rules.v4` for the server 203.0.113.10 (eth0). INPUT policy ACCEPT this time, FORWARD DROP, OUTPUT ACCEPT. Add rules at the top of INPUT so that:

        - loopback is accepted first;
        - new connection attempts (state NEW) to the telnet port (tcp 23) or to the SMB port (tcp 445) are logged with the prefix `scan ` and then dropped; established connections are not affected;
        - packets from the network 198.51.100.0/24 are dropped without logging;
        - everything else is accepted (by the policy).
     '''),
     start="*filter\n:INPUT ACCEPT [0:0]\n:FORWARD ACCEPT [0:0]\n:OUTPUT ACCEPT [0:0]\nCOMMIT\n",
     ref=filt(("ACCEPT", "DROP", "ACCEPT"), ["-A INPUT -i lo -j ACCEPT", '-A INPUT -p tcp -m multiport --dports 23,445 -m conntrack --ctstate NEW -j LOG --log-prefix "scan "', "-A INPUT -p tcp -m multiport --dports 23,445 -m conntrack --ctstate NEW -j DROP", "-A INPUT -s 198.51.100.0/24 -j DROP"]),
     examples=[P("1.2.3.4", "203.0.113.10", dport=23, iif="eth0", verdict="DROP", log=["scan "]), P("198.51.100.5", "203.0.113.10", dport=80, iif="eth0", verdict="DROP"), P("1.2.3.4", "203.0.113.10", dport=80, iif="eth0", verdict="ACCEPT")],
     cases=[P("1.2.3.4", "203.0.113.10", dport=445, iif="eth0"), P("1.2.3.4", "203.0.113.10", dport=445, iif="eth0", state="ESTABLISHED"), P("1.2.3.4", "203.0.113.10", dport=23, iif="eth0", state="RELATED"), P("1.2.3.4", "203.0.113.10", "udp", dport=445, iif="eth0"),
            P("198.51.100.5", "203.0.113.10", dport=23, iif="eth0"), P("198.51.100.5", "203.0.113.10", dport=445, iif="eth0", state="ESTABLISHED"), P("198.51.101.5", "203.0.113.10", dport=80, iif="eth0"), P("127.0.0.1", "127.0.0.1", dport=23, iif="lo"), P("1.2.3.4", "203.0.113.10", dport=22, iif="eth0"),
            P("1.2.3.4", "203.0.113.10", dport=24, iif="eth0"), P("1.2.3.4", "10.5.5.5", dport=80, iif="eth0", oif="eth1"), P("1.2.3.4", "203.0.113.10", "icmp", icmp="echo-request", iif="eth0")],
     wrong=[filt(("ACCEPT", "DROP", "ACCEPT"), ["-A INPUT -i lo -j ACCEPT", '-A INPUT -p tcp -m multiport --dports 23,445 -j LOG --log-prefix "scan "', "-A INPUT -p tcp -m multiport --dports 23,445 -j DROP", "-A INPUT -s 198.51.100.0/24 -j DROP"])])

# 11 -------------------------------------------------------------------------------------------------------------------
spec(slug="return-chain-fix", d=3, kind="fix", config=HOST,
     prompt=dd('''
        `rules.v4` uses a user chain `TRUSTED` to give some partners access to the API port (tcp 8443), but two things go wrong: untrusted clients can still reach the API, and the trusted partners cannot get to SSH any more.
        The intended behaviour: INPUT policy DROP; loopback and established/related first; **tcp 8443** is accepted only from 192.0.2.0/24 and 198.51.100.64/27 (the chain `TRUSTED` is for exactly these checks, keep using it);
        **tcp 22** is accepted from 192.0.2.0/24 only; the web (tcp 80 and 443) is open to everyone; anything else is dropped by the policy. FORWARD DROP, OUTPUT ACCEPT. Fix the file.
     '''),
     start=filt(("DROP", "DROP", "ACCEPT"), ["-A INPUT -i lo -j ACCEPT", "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A INPUT -p tcp --dport 8443 -j TRUSTED", "-A INPUT -p tcp --dport 8443 -j ACCEPT", "-A INPUT -p tcp -m multiport --dports 80,443 -j ACCEPT",
                                         "-A TRUSTED -s 192.0.2.0/24 -j RETURN", "-A TRUSTED -s 198.51.100.64/27 -j RETURN", "-A TRUSTED -j DROP"], extra_chains=["TRUSTED"]),
     ref=filt(("DROP", "DROP", "ACCEPT"), ["-A INPUT -i lo -j ACCEPT", "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A INPUT -p tcp --dport 8443 -j TRUSTED", "-A INPUT -p tcp --dport 22 -s 192.0.2.0/24 -j ACCEPT", "-A INPUT -p tcp -m multiport --dports 80,443 -j ACCEPT",
                                         "-A TRUSTED -s 192.0.2.0/24 -j ACCEPT", "-A TRUSTED -s 198.51.100.64/27 -j ACCEPT", "-A TRUSTED -j DROP"], extra_chains=["TRUSTED"]),
     examples=[P("192.0.2.9", "203.0.113.10", dport=8443, iif="eth0", verdict="ACCEPT"), P("1.2.3.4", "203.0.113.10", dport=8443, iif="eth0", verdict="DROP"), P("192.0.2.9", "203.0.113.10", dport=22, iif="eth0", verdict="ACCEPT")],
     cases=[P("198.51.100.64", "203.0.113.10", dport=8443, iif="eth0"), P("198.51.100.95", "203.0.113.10", dport=8443, iif="eth0"), P("198.51.100.96", "203.0.113.10", dport=8443, iif="eth0"), P("198.51.100.63", "203.0.113.10", dport=8443, iif="eth0"), P("198.51.100.70", "203.0.113.10", dport=22, iif="eth0"),
            P("1.2.3.4", "203.0.113.10", dport=22, iif="eth0"), P("1.2.3.4", "203.0.113.10", dport=443, iif="eth0"), P("1.2.3.4", "203.0.113.10", dport=80, iif="eth0"), P("192.0.2.9", "203.0.113.10", dport=9000, iif="eth0"), P("192.0.2.9", "203.0.113.10", "udp", dport=8443, iif="eth0"),
            P("1.2.3.4", "203.0.113.10", dport=8443, iif="eth0", state="ESTABLISHED"), P("127.0.0.1", "127.0.0.1", dport=8443, iif="lo")],
     wrong=[filt(("DROP", "DROP", "ACCEPT"), ["-A INPUT -i lo -j ACCEPT", "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A INPUT -p tcp --dport 8443 -j TRUSTED", "-A INPUT -p tcp --dport 22 -j ACCEPT", "-A INPUT -p tcp -m multiport --dports 80,443 -j ACCEPT",
                                         "-A TRUSTED -s 192.0.2.0/24 -j ACCEPT", "-A TRUSTED -s 198.51.100.64/27 -j ACCEPT", "-A TRUSTED -j DROP"], extra_chains=["TRUSTED"])])

# 12 -------------------------------------------------------------------------------------------------------------------
spec(slug="edge-firewall-policy", d=5, kind="author", config=RT,
     prompt=dd('''
        Write the complete `rules.v4` for the edge router (eth0 = WAN 203.0.113.2, eth1 = staff 10.0.1.0/24, eth2 = guests 10.0.9.0/24, eth3 = servers 10.0.2.0/24). Policies: INPUT DROP, FORWARD DROP, OUTPUT ACCEPT. Requirements (all of them):

        1. Loopback and established/related traffic are accepted in INPUT and FORWARD, before anything else except rule 2.
        2. Packets from the bogon/abuse list 198.51.100.0/24 and 192.0.2.128/25 are dropped first in INPUT and FORWARD (before even established/related).
        3. Router management: SSH (tcp 22) to the router from the staff LAN, and from the single admin host 192.0.2.10 on the WAN. HTTPS (tcp 443) on the router's WAN address is not open.
        4. DNS (udp and tcp 53) to the router from staff and guests. ICMP echo requests to the router from anywhere except guests.
        5. Port forwards on the WAN address: tcp 443 -> 10.0.2.20:8443 (web front end), tcp 25 -> 10.0.2.25:25 (mail), udp 51820 -> 10.0.2.30:51820 (VPN). All three are accepted by the forward filter (after translation) and nothing else from the WAN is forwarded.
        6. Staff may reach everything on the WAN and the servers network; guests may only go to the WAN (tcp 80, 443, udp 53) and never to private ranges 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16; servers may reach the WAN only on tcp 443 and udp 53.
        7. Everything leaving through eth0 from 10.0.0.0/8 is masqueraded.
        8. Dropped new connections coming from the guest network into the router itself (not forwarded) are logged with the prefix `guest-in ` and dropped.
     '''),
     start="*filter\n:INPUT ACCEPT [0:0]\n:FORWARD ACCEPT [0:0]\n:OUTPUT ACCEPT [0:0]\nCOMMIT\n",
     ref=filt(("DROP", "DROP", "ACCEPT"), [
         "-A INPUT -s 198.51.100.0/24 -j DROP", "-A INPUT -s 192.0.2.128/25 -j DROP", "-A INPUT -i lo -j ACCEPT", "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT",
         "-A INPUT -i eth1 -p tcp --dport 22 -j ACCEPT", "-A INPUT -i eth0 -s 192.0.2.10 -p tcp --dport 22 -j ACCEPT", "-A INPUT -i eth1 -p udp --dport 53 -j ACCEPT", "-A INPUT -i eth1 -p tcp --dport 53 -j ACCEPT",
         "-A INPUT -i eth2 -p udp --dport 53 -j ACCEPT", "-A INPUT -i eth2 -p tcp --dport 53 -j ACCEPT", "-A INPUT -p icmp --icmp-type echo-request ! -i eth2 -j ACCEPT", '-A INPUT -i eth2 -m conntrack --ctstate NEW -j LOG --log-prefix "guest-in "', "-A INPUT -i eth2 -j DROP",
         "-A FORWARD -s 198.51.100.0/24 -j DROP", "-A FORWARD -s 192.0.2.128/25 -j DROP", "-A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A FORWARD -i eth0 -d 10.0.2.20 -p tcp --dport 8443 -j ACCEPT", "-A FORWARD -i eth0 -d 10.0.2.25 -p tcp --dport 25 -j ACCEPT",
         "-A FORWARD -i eth0 -d 10.0.2.30 -p udp --dport 51820 -j ACCEPT", "-A FORWARD -i eth1 -o eth0 -j ACCEPT", "-A FORWARD -i eth1 -o eth3 -j ACCEPT",
         "-A FORWARD -i eth2 -d 10.0.0.0/8 -j DROP", "-A FORWARD -i eth2 -d 172.16.0.0/12 -j DROP", "-A FORWARD -i eth2 -d 192.168.0.0/16 -j DROP", "-A FORWARD -i eth2 -o eth0 -p tcp -m multiport --dports 80,443 -j ACCEPT", "-A FORWARD -i eth2 -o eth0 -p udp --dport 53 -j ACCEPT",
         "-A FORWARD -i eth3 -o eth0 -p tcp --dport 443 -j ACCEPT", "-A FORWARD -i eth3 -o eth0 -p udp --dport 53 -j ACCEPT"],
                nat=["-A PREROUTING -i eth0 -p tcp --dport 443 -j DNAT --to-destination 10.0.2.20:8443", "-A PREROUTING -i eth0 -p tcp --dport 25 -j DNAT --to-destination 10.0.2.25:25", "-A PREROUTING -i eth0 -p udp --dport 51820 -j DNAT --to-destination 10.0.2.30:51820",
                     "-A POSTROUTING -s 10.0.0.0/8 -o eth0 -j MASQUERADE"]),
     examples=[P("1.2.3.4", "203.0.113.2", dport=443, iif="eth0", oif="eth3", verdict="ACCEPT", dst="10.0.2.20:8443"), P("198.51.100.4", "203.0.113.2", dport=443, iif="eth0", oif="eth3", verdict="DROP"), P("10.0.9.9", "10.0.9.1", dport=22, iif="eth2", verdict="DROP", log=["guest-in "]),
               P("192.0.2.10", "203.0.113.2", dport=22, iif="eth0", verdict="ACCEPT")],
     cases=[P("1.2.3.4", "203.0.113.2", dport=25, iif="eth0", oif="eth3"), P("1.2.3.4", "203.0.113.2", "udp", dport=51820, iif="eth0", oif="eth3"), P("1.2.3.4", "203.0.113.2", "tcp", dport=51820, iif="eth0", oif="eth3"), P("1.2.3.4", "203.0.113.2", dport=80, iif="eth0", oif="eth3"),
            P("1.2.3.4", "203.0.113.2", dport=22, iif="eth0"), P("192.0.2.11", "203.0.113.2", dport=22, iif="eth0"), P("192.0.2.130", "203.0.113.2", dport=22, iif="eth0"), P("192.0.2.200", "203.0.113.2", dport=443, iif="eth0", oif="eth3"), P("192.0.2.130", "203.0.113.2", dport=22, iif="eth0", state="ESTABLISHED"),
            P("198.51.100.200", "203.0.113.2", "icmp", icmp="echo-request", iif="eth0"), P("1.2.3.4", "203.0.113.2", "icmp", icmp="echo-request", iif="eth0"), P("10.0.9.9", "10.0.9.1", "icmp", icmp="echo-request", iif="eth2"), P("10.0.1.9", "10.0.1.1", "icmp", icmp="echo-request", iif="eth1"),
            P("10.0.1.9", "10.0.1.1", dport=22, iif="eth1"), P("10.0.1.9", "10.0.1.1", "udp", dport=53, iif="eth1"), P("10.0.9.9", "10.0.9.1", "udp", dport=53, iif="eth2"), P("10.0.9.9", "10.0.9.1", "tcp", dport=53, iif="eth2"), P("10.0.9.9", "10.0.9.1", "tcp", dport=443, iif="eth2", state="ESTABLISHED"),
            P("10.0.9.9", "10.0.9.1", dport=443, iif="eth2"), P("10.0.1.9", "10.0.2.5", dport=3306, iif="eth1", oif="eth3"), P("10.0.1.9", "9.9.9.9", dport=25, iif="eth1", oif="eth0"), P("10.0.9.9", "9.9.9.9", dport=443, iif="eth2", oif="eth0"), P("10.0.9.9", "9.9.9.9", dport=25, iif="eth2", oif="eth0"),
            P("10.0.9.9", "192.168.0.5", dport=443, iif="eth2", oif="eth0"), P("10.0.9.9", "10.0.1.7", dport=80, iif="eth2", oif="eth1"), P("10.0.2.5", "9.9.9.9", dport=443, iif="eth3", oif="eth0"), P("10.0.2.5", "9.9.9.9", dport=80, iif="eth3", oif="eth0"), P("10.0.2.5", "10.0.1.7", dport=22, iif="eth3", oif="eth1"),
            P("9.9.9.9", "10.0.1.7", dport=22, iif="eth0", oif="eth1"), P("9.9.9.9", "10.0.2.5", dport=3306, iif="eth0", oif="eth3"), P("9.9.9.9", "10.0.1.7", sport=443, dport=50000, iif="eth0", oif="eth1", state="ESTABLISHED"), P("198.51.100.7", "10.0.1.7", sport=443, dport=50000, iif="eth0", oif="eth1", state="ESTABLISHED"),
            P("10.0.1.9", "198.51.100.7", dport=80, iif="eth1", oif="eth0"), P("10.0.1.9", "9.9.9.9", dport=80, iif="eth1", oif="eth0")],
     wrong=[filt(("DROP", "DROP", "ACCEPT"), [
         "-A INPUT -i lo -j ACCEPT", "-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A INPUT -s 198.51.100.0/24 -j DROP", "-A INPUT -s 192.0.2.128/25 -j DROP",
         "-A INPUT -i eth1 -p tcp --dport 22 -j ACCEPT", "-A INPUT -i eth0 -s 192.0.2.10 -p tcp --dport 22 -j ACCEPT", "-A INPUT -i eth1 -p udp --dport 53 -j ACCEPT", "-A INPUT -i eth1 -p tcp --dport 53 -j ACCEPT",
         "-A INPUT -i eth2 -p udp --dport 53 -j ACCEPT", "-A INPUT -i eth2 -p tcp --dport 53 -j ACCEPT", "-A INPUT -p icmp --icmp-type echo-request ! -i eth2 -j ACCEPT", '-A INPUT -i eth2 -m conntrack --ctstate NEW -j LOG --log-prefix "guest-in "', "-A INPUT -i eth2 -j DROP",
         "-A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT", "-A FORWARD -s 198.51.100.0/24 -j DROP", "-A FORWARD -s 192.0.2.128/25 -j DROP", "-A FORWARD -i eth0 -d 10.0.2.20 -p tcp --dport 8443 -j ACCEPT", "-A FORWARD -i eth0 -d 10.0.2.25 -p tcp --dport 25 -j ACCEPT",
         "-A FORWARD -i eth0 -d 10.0.2.30 -p udp --dport 51820 -j ACCEPT", "-A FORWARD -i eth1 -o eth0 -j ACCEPT", "-A FORWARD -i eth1 -o eth3 -j ACCEPT",
         "-A FORWARD -i eth2 -d 10.0.0.0/8 -j DROP", "-A FORWARD -i eth2 -d 172.16.0.0/12 -j DROP", "-A FORWARD -i eth2 -d 192.168.0.0/16 -j DROP", "-A FORWARD -i eth2 -o eth0 -p tcp -m multiport --dports 80,443 -j ACCEPT", "-A FORWARD -i eth2 -o eth0 -p udp --dport 53 -j ACCEPT",
         "-A FORWARD -i eth3 -o eth0 -p tcp --dport 443 -j ACCEPT", "-A FORWARD -i eth3 -o eth0 -p udp --dport 53 -j ACCEPT"],
                  nat=["-A PREROUTING -i eth0 -p tcp --dport 443 -j DNAT --to-destination 10.0.2.20:8443", "-A PREROUTING -i eth0 -p tcp --dport 25 -j DNAT --to-destination 10.0.2.25:25", "-A PREROUTING -i eth0 -p udp --dport 51820 -j DNAT --to-destination 10.0.2.30:51820",
                       "-A POSTROUTING -s 10.0.0.0/8 -o eth0 -j MASQUERADE"])])


def _tasks(rng, n):
    return [make_task(s) for s in SPECS[:n]]


@family("devops-firewall-rules", category="devops", lang="text", kind="fix", n=len(SPECS),
        summary="write or repair iptables rulesets judged by a documented simulator: rule order, user chains, multiport, negation, DNAT before FORWARD, masquerade, egress filtering")
def firewall_rules(rng, n):
    return _tasks(rng, n)
