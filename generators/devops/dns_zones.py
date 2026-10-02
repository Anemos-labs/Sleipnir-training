"""DevOps tasks: DNS master files. A documented zone checker and authoritative-server simulator (given to the agent as tools/zonesim.py) decides what the zone answers."""
import json
import types
from dataclasses import dataclass, field

from fx import dd, family
from generators.devops import _dokit as K
from generators.devops._dnssim import DNSSIM


def pd(text, note):
    """dedent the text first and then append the note (dedenting after the concatenation does nothing)"""
    t = dd(text).rstrip("\n")
    return t + (note if note.startswith("\n") or t.endswith(" ") else " " + note)


_mod = types.ModuleType("zonesim")
exec(compile(DNSSIM, "zonesim.py", "exec"), _mod.__dict__)
zs = _mod

CHECK_DNS = r'''
from dolib import *
sys.path.insert(0, "tests")
import zonesim


spec = json.load(open("tests/cases.json", encoding="utf-8"))
try:
    by = zonesim.load(spec["path"], spec["origin"])
except zonesim.ZoneError as e:
    die(f"zone {spec['origin']}: {e}")
rep = Report()
for c in spec["cases"]:
    q = c["q"]
    res = zonesim.query(by, spec["origin"], q["name"], q["type"])
    bad = zonesim.matches(res, c["expect"])
    rep.check(not bad, f"{q['name']} {q['type']}: " + "; ".join(bad))
rep.finish()
'''


def Q(name, qtype="A", **expect):
    return {"q": {"name": name, "type": qtype}, **({"expect": expect} if expect else {})}


@dataclass
class DnsSpec:
    slug: str
    d: int
    prompt: str
    origin: str
    ref: str
    start: str
    examples: list
    cases: list
    wrong: list = field(default_factory=list)
    kind: str = "author"

    @property
    def path(self):
        return f"zones/{self.origin.rstrip('.')}.zone"


def make_task(sp: DnsSpec):
    by_ref = zs.check(zs.parse(sp.ref, sp.origin), sp.origin)

    def ask(c):
        return zs.query(by_ref, sp.origin, c["q"]["name"], c["q"]["type"])
    for c in sp.examples:
        bad = zs.matches(ask(c), c["expect"])
        if bad:
            raise RuntimeError(f"{sp.slug}: example {c['q']} disagrees with the reference: {bad} (got {ask(c)})")
    cases = []
    for c in sp.examples + sp.cases:
        r = ask(c)
        cases.append({"q": c["q"], "expect": {k: v for k, v in r.items() if k != "note"}})
    start = {sp.path: sp.start, "tools/zonesim.py": DNSSIM, "examples.json": json.dumps(sp.examples, indent=1) + "\n",
             "README.md": f"# DNS zone exercise\n\nEdit `{sp.path}` (origin `{sp.origin}`). `python3 tools/zonesim.py {sp.path} {sp.origin} --check` runs the zone checks, `python3 tools/zonesim.py {sp.path} {sp.origin} examples.json` answers example queries; the docstring of the tool (`python3 tools/zonesim.py`) documents the syntax and the rules.\n"}
    hidden = {"tests/zonesim.py": "# verifier copy of tools/zonesim.py\n" + DNSSIM, "tests/cases.json": json.dumps({"path": sp.path, "origin": sp.origin, "cases": cases}, indent=1) + "\n"}
    t = K.devops_task(sp.slug, sp.d, sp.prompt, start, {sp.path: sp.ref}, CHECK_DNS, hidden, lang="text", kind="fix" if sp.kind == "fix" else "greenfield", tags=["dns", "zone", "bind", "config"])
    return K.finish(t, wrong=[{sp.path: w} for w in sp.wrong])


SPECS: list[DnsSpec] = []


def spec(**kw):
    SPECS.append(DnsSpec(**kw))


NOTE = "\n\n`tools/zonesim.py` checks the zone like `named-checkzone` (rules are in its docstring) and answers queries from it; `examples.json` has a few with the expected answers."
H = "harbor.example."

# 1 ------------------------------------------------------------------------------------------------------------------
spec(slug="basic-zone", d=2, origin=H, kind="author",
     prompt=pd('''
        Write the zone file `zones/harbor.example.zone` for `harbor.example.`:

        - default TTL one hour; SOA: primary server `ns1.harbor.example.`, contact `hostmaster.harbor.example.`, serial 2024061001, refresh 2h, retry 15m, expire 2w, minimum 5m;
        - name servers `ns1` (192.0.2.1) and `ns2` (192.0.2.2), both inside the zone, and both listed as NS of the apex;
        - the apex has the addresses 192.0.2.10 and 2001:db8::10;
        - `www` is an alias (CNAME) of the apex name `harbor.example.`;
        - mail: the apex has MX 10 pointing to `mail`, and `mail` is 192.0.2.25 with a TTL of 5 minutes (300 s);
        - the apex has the text record `v=spf1 mx -all`;
        - `status` is 192.0.2.50 with a TTL of 60 seconds.
     ''', NOTE),
     start="; harbor.example zone\n",
     ref=dd('''
        $ORIGIN harbor.example.
        $TTL 1h
        @       IN SOA ns1 hostmaster (
                    2024061001 ; serial
                    2h         ; refresh
                    15m        ; retry
                    2w         ; expire
                    5m )       ; minimum
                IN NS  ns1
                IN NS  ns2
                IN A   192.0.2.10
                IN AAAA 2001:db8::10
                IN MX  10 mail
                IN TXT "v=spf1 mx -all"
        ns1     IN A   192.0.2.1
        ns2     IN A   192.0.2.2
        www     IN CNAME @
        mail    300 IN A 192.0.2.25
        status  60 IN A 192.0.2.50
     '''),
     examples=[Q("www.harbor.example.", "A", answer=["www.harbor.example. 3600 CNAME harbor.example.", "harbor.example. 3600 A 192.0.2.10"]), Q("harbor.example.", "MX", answer=["harbor.example. 3600 MX 10 mail.harbor.example."]),
               Q("status.harbor.example.", "A", answer=["status.harbor.example. 60 A 192.0.2.50"]), Q("nothing.harbor.example.", "A", rcode="NXDOMAIN")],
     cases=[Q("harbor.example.", "SOA"), Q("harbor.example.", "NS"), Q("harbor.example.", "A"), Q("harbor.example.", "AAAA"), Q("harbor.example.", "TXT"), Q("harbor.example.", "MX"), Q("www.harbor.example.", "AAAA"), Q("www.harbor.example.", "CNAME"), Q("mail.harbor.example.", "A"),
            Q("mail.harbor.example.", "MX"), Q("ns1.harbor.example.", "A"), Q("ns2.harbor.example.", "A"), Q("ns2.harbor.example.", "AAAA"), Q("status.harbor.example.", "A"), Q("a.status.harbor.example.", "A"), Q("WWW.Harbor.Example.", "A"), Q("example.", "A")],
     wrong=[dd('''
        $ORIGIN harbor.example.
        $TTL 1h
        @ IN SOA ns1 hostmaster ( 2024061001 2h 15m 2w 5m )
          IN NS ns1
          IN NS ns2
          IN A 192.0.2.10
          IN AAAA 2001:db8::10
          IN MX 10 mail
          IN TXT "v=spf1 mx -all"
        ns1 IN A 192.0.2.1
        ns2 IN A 192.0.2.2
        www IN CNAME @
        mail IN A 192.0.2.25
        status 60 IN A 192.0.2.50
     ''')])

# 2 ------------------------------------------------------------------------------------------------------------------

spec(slug="missing-trailing-dots", d=2, origin="lantern.example.", kind="fix",
     prompt=pd('''
        The zone file `zones/lantern.example.zone` fails the zone check (and would answer nonsense): names that were meant to be fully qualified are written without the trailing dot, so the origin is appended a second time.
        The intended zone: name servers `ns1.lantern.example.` and `ns2.lantern.example.`, mail handled by `mx1.lantern.example.` (preference 10) and `mx2.lantern.example.` (preference 20), `www` and `blog` are aliases (CNAME) of `web.lantern.example.`,
        and `files` is an alias of the external name `files.cdn-provider.net.`. Fix the file; the addresses and everything else stay the same.
     ''', NOTE),
     start=dd('''
        $TTL 3600
        @    IN SOA ns1.lantern.example hostmaster.lantern.example. 2024020101 7200 900 1209600 300
             IN NS  ns1.lantern.example
             IN NS  ns2.lantern.example.
             IN MX  10 mx1.lantern.example
             IN MX  20 mx2.lantern.example.
        ns1  IN A 198.51.100.1
        ns2  IN A 198.51.100.2
        mx1  IN A 198.51.100.25
        mx2  IN A 198.51.100.26
        web  IN A 198.51.100.80
        www  IN CNAME web.lantern.example
        blog IN CNAME web.lantern.example
        files IN CNAME files.cdn-provider.net
     '''),
     ref=dd('''
        $ORIGIN lantern.example.
        $TTL 3600
        @    IN SOA ns1.lantern.example. hostmaster.lantern.example. 2024020101 7200 900 1209600 300
             IN NS  ns1.lantern.example.
             IN NS  ns2.lantern.example.
             IN MX  10 mx1.lantern.example.
             IN MX  20 mx2.lantern.example.
        ns1  IN A 198.51.100.1
        ns2  IN A 198.51.100.2
        mx1  IN A 198.51.100.25
        mx2  IN A 198.51.100.26
        web  IN A 198.51.100.80
        www  IN CNAME web.lantern.example.
        blog IN CNAME web.lantern.example.
        files IN CNAME files.cdn-provider.net.
     '''),
     examples=[Q("www.lantern.example.", "A", answer=["www.lantern.example. 3600 CNAME web.lantern.example.", "web.lantern.example. 3600 A 198.51.100.80"]), Q("lantern.example.", "MX", answer=["lantern.example. 3600 MX 10 mx1.lantern.example.", "lantern.example. 3600 MX 20 mx2.lantern.example."]),
               Q("files.lantern.example.", "A", answer=["files.lantern.example. 3600 CNAME files.cdn-provider.net."])],
     cases=[Q("blog.lantern.example.", "A"), Q("lantern.example.", "NS"), Q("lantern.example.", "SOA"), Q("web.lantern.example.", "A"), Q("mx1.lantern.example.", "A"), Q("mx2.lantern.example.", "A"), Q("ns1.lantern.example.", "A"), Q("ns2.lantern.example.", "A"), Q("files.lantern.example.", "CNAME"),
            Q("www.lantern.example.", "CNAME"), Q("nope.lantern.example.", "A"), Q("lantern.example.", "A")],
     wrong=["$ORIGIN lantern.example.\n$TTL 3600\n@ IN SOA ns1 hostmaster 2024020101 7200 900 1209600 300\n IN NS ns1\n IN NS ns2\n IN MX 10 mx1\n IN MX 20 mx2\nns1 IN A 198.51.100.1\nns2 IN A 198.51.100.2\nmx1 IN A 198.51.100.25\nmx2 IN A 198.51.100.26\nweb IN A 198.51.100.80\nwww IN CNAME web\nblog IN CNAME web\nfiles IN CNAME files.cdn-provider.net\n"])

# 3 ------------------------------------------------------------------------------------------------------------------
O3 = "quarry.example."
spec(slug="cname-conflicts", d=3, origin=O3, kind="fix",
     prompt=pd('''
        `zones/quarry.example.zone` is rejected: it breaks the CNAME rules. Here is what the zone must answer after the repair (keep all other data as it is):

        - `quarry.example.` has the address 203.0.113.10 and MX 10 `mail.quarry.example.`, NS `ns1`/`ns2`; it must not be an alias.
        - `www.quarry.example.` is an alias of `quarry.example.`.
        - `mail.quarry.example.` has the address 203.0.113.25 (an A record; today it is an alias of `smtp`, which is not allowed as a mail exchange target).
        - `docs.quarry.example.` is an alias of `quarry.hosted-docs.net.` and must not carry any other record; the ownership proof `"docs-verify=abc123"` (TXT) goes to `_verify.docs.quarry.example.` instead.
        - `shop.quarry.example.` is an alias of `shops.provider.net.`; the TXT record that is there today is moved to `_note.shop.quarry.example.` unchanged (`"seasonal"`).
     ''', NOTE),
     start=dd('''
        $ORIGIN quarry.example.
        $TTL 1h
        @     IN SOA ns1 hostmaster 2024030301 2h 15m 2w 5m
              IN NS ns1
              IN NS ns2
              IN CNAME web
              IN MX 10 mail
        ns1   IN A 203.0.113.1
        ns2   IN A 203.0.113.2
        web   IN A 203.0.113.10
        www   IN CNAME quarry.example.
        smtp  IN A 203.0.113.25
        mail  IN CNAME smtp
        docs  IN CNAME quarry.hosted-docs.net.
              IN TXT "docs-verify=abc123"
        shop  IN CNAME shops.provider.net.
              IN TXT "seasonal"
     '''),
     ref=dd('''
        $ORIGIN quarry.example.
        $TTL 1h
        @     IN SOA ns1 hostmaster 2024030301 2h 15m 2w 5m
              IN NS ns1
              IN NS ns2
              IN A 203.0.113.10
              IN MX 10 mail
        ns1   IN A 203.0.113.1
        ns2   IN A 203.0.113.2
        web   IN A 203.0.113.10
        www   IN CNAME quarry.example.
        smtp  IN A 203.0.113.25
        mail  IN A 203.0.113.25
        docs  IN CNAME quarry.hosted-docs.net.
        _verify.docs IN TXT "docs-verify=abc123"
        shop  IN CNAME shops.provider.net.
        _note.shop IN TXT "seasonal"
     '''),
     examples=[Q("quarry.example.", "A", answer=["quarry.example. 3600 A 203.0.113.10"]), Q("docs.quarry.example.", "TXT", answer=["docs.quarry.example. 3600 CNAME quarry.hosted-docs.net."]),
               Q("_verify.docs.quarry.example.", "TXT", answer=['_verify.docs.quarry.example. 3600 TXT "docs-verify=abc123"'])],
     cases=[Q("quarry.example.", "MX"), Q("quarry.example.", "NS"), Q("quarry.example.", "CNAME"), Q("www.quarry.example.", "A"), Q("mail.quarry.example.", "A"), Q("mail.quarry.example.", "CNAME"), Q("smtp.quarry.example.", "A"), Q("web.quarry.example.", "A"),
            Q("docs.quarry.example.", "A"), Q("docs.quarry.example.", "CNAME"), Q("shop.quarry.example.", "A"), Q("shop.quarry.example.", "TXT"), Q("_note.shop.quarry.example.", "TXT"), Q("_verify.quarry.example.", "TXT"), Q("verify.docs.quarry.example.", "A")],
     wrong=["$ORIGIN quarry.example.\n$TTL 1h\n@ IN SOA ns1 hostmaster 2024030301 2h 15m 2w 5m\n IN NS ns1\n IN NS ns2\n IN A 203.0.113.10\n IN MX 10 mail\nns1 IN A 203.0.113.1\nns2 IN A 203.0.113.2\nweb IN A 203.0.113.10\nwww IN CNAME quarry.example.\nsmtp IN A 203.0.113.25\nmail IN A 203.0.113.25\ndocs IN CNAME quarry.hosted-docs.net.\n IN TXT \"docs-verify=abc123\"\nshop IN CNAME shops.provider.net.\n"])

# 4 ------------------------------------------------------------------------------------------------------------------
O4 = "meadow.example."
spec(slug="wildcards", d=3, origin=O4, kind="author",
     prompt=pd('''
        Write `zones/meadow.example.zone` for `meadow.example.` (TTL 10 minutes by default, SOA `ns1.meadow.example.` / `admin.meadow.example.`, serial 7, refresh 3600, retry 600, expire 604800, minimum 300; NS `ns1.meadow.example.` = 192.0.2.1 and `ns2.meadow.example.` = 192.0.2.2). Then:

        - every name under `apps.meadow.example.` (at any depth, e.g. `x.apps...` and `a.b.apps...`) resolves to 192.0.2.90, **except** `admin.apps.meadow.example.`, which is 192.0.2.91 (and has no other data, so e.g. its TXT query is empty rather than answered from the wildcard);
        - every name directly or indirectly under `dev.meadow.example.` is an alias (CNAME) of `dev-lb.meadow.example.`, which is 192.0.2.99; `dev.meadow.example.` itself has no records (querying it gives an empty answer, not NXDOMAIN... because names exist below it);
        - `meadow.example.` itself is 192.0.2.10, and nothing else exists: any other name must be NXDOMAIN.
     ''', NOTE),
     start="; meadow zone\n",
     ref=dd('''
        $ORIGIN meadow.example.
        $TTL 10m
        @ IN SOA ns1 admin 7 3600 600 604800 300
          IN NS ns1
          IN NS ns2
          IN A 192.0.2.10
        ns1 IN A 192.0.2.1
        ns2 IN A 192.0.2.2
        *.apps IN A 192.0.2.90
        admin.apps IN A 192.0.2.91
        *.dev IN CNAME dev-lb
        dev-lb IN A 192.0.2.99
     '''),
     examples=[Q("x.apps.meadow.example.", "A", answer=["x.apps.meadow.example. 600 A 192.0.2.90"]), Q("admin.apps.meadow.example.", "TXT", answer=[]), Q("nothing.meadow.example.", "A", rcode="NXDOMAIN"),
               Q("www.dev.meadow.example.", "A", answer=["www.dev.meadow.example. 600 CNAME dev-lb.meadow.example.", "dev-lb.meadow.example. 600 A 192.0.2.99"])],
     cases=[Q("a.b.apps.meadow.example.", "A"), Q("a.b.c.apps.meadow.example.", "A"), Q("apps.meadow.example.", "A"), Q("admin.apps.meadow.example.", "A"), Q("x.admin.apps.meadow.example.", "A"), Q("dev.meadow.example.", "A"), Q("x.dev.meadow.example.", "A"), Q("x.y.dev.meadow.example.", "A"),
            Q("x.dev.meadow.example.", "CNAME"), Q("dev-lb.meadow.example.", "A"), Q("meadow.example.", "A"), Q("other.meadow.example.", "A"), Q("x.other.meadow.example.", "A"), Q("x.apps.meadow.example.", "AAAA"), Q("x.apps.meadow.example.", "CNAME"), Q("ns1.meadow.example.", "A")],
     wrong=["$ORIGIN meadow.example.\n$TTL 10m\n@ IN SOA ns1 admin 7 3600 600 604800 300\n IN NS ns1\n IN NS ns2\n IN A 192.0.2.10\nns1 IN A 192.0.2.1\nns2 IN A 192.0.2.2\n*.apps IN A 192.0.2.90\n*.dev IN CNAME dev-lb\ndev-lb IN A 192.0.2.99\n"])

# 5 ------------------------------------------------------------------------------------------------------------------
O5 = "campus.example."
spec(slug="delegation-glue", d=4, origin=O5, kind="author",
     prompt=pd('''
        Write `zones/campus.example.zone` for `campus.example.` (TTL 1 day by default; SOA `ns1.campus.example.` / `noc.campus.example.`, serial 2024090101, refresh 6h, retry 1h, expire 4w, minimum 1h; apex NS `ns1.campus.example.` = 198.51.100.1 and `ns2.campus.example.` = 198.51.100.2; apex address 198.51.100.10; `www` alias of the apex).
        Then delegate two sub-domains:

        - `eu.campus.example.` is served by `ns1.eu.campus.example.` (198.51.100.101) and `ns2.eu.campus.example.` (198.51.100.102), which sit inside the delegated domain, so their addresses must be given as glue in this zone;
        - `us.campus.example.` is served by `ns1.us.example.net.` and `ns2.us.example.net.` (outside this zone: no glue).
        Queries below a delegation must give a referral (the checker rejects any other data below a delegation that is not glue).
     ''', NOTE),
     start="; campus zone\n",
     ref=dd('''
        $ORIGIN campus.example.
        $TTL 1d
        @ IN SOA ns1 noc 2024090101 6h 1h 4w 1h
          IN NS ns1
          IN NS ns2
          IN A 198.51.100.10
        ns1 IN A 198.51.100.1
        ns2 IN A 198.51.100.2
        www IN CNAME @
        eu IN NS ns1.eu
        eu IN NS ns2.eu
        ns1.eu IN A 198.51.100.101
        ns2.eu IN A 198.51.100.102
        us IN NS ns1.us.example.net.
        us IN NS ns2.us.example.net.
     '''),
     examples=[Q("host.eu.campus.example.", "A", referral=["eu.campus.example. 86400 NS ns1.eu.campus.example.", "eu.campus.example. 86400 NS ns2.eu.campus.example."], glue=["ns1.eu.campus.example. 86400 A 198.51.100.101", "ns2.eu.campus.example. 86400 A 198.51.100.102"]),
               Q("db.us.campus.example.", "A", referral=["us.campus.example. 86400 NS ns1.us.example.net.", "us.campus.example. 86400 NS ns2.us.example.net."], glue=[]), Q("campus.example.", "A", answer=["campus.example. 86400 A 198.51.100.10"])],
     cases=[Q("eu.campus.example.", "A"), Q("eu.campus.example.", "NS"), Q("x.y.eu.campus.example.", "MX"), Q("ns1.eu.campus.example.", "A"), Q("us.campus.example.", "NS"), Q("a.us.campus.example.", "AAAA"), Q("www.campus.example.", "A"), Q("campus.example.", "NS"),
            Q("campus.example.", "SOA"), Q("ns2.campus.example.", "A"), Q("none.campus.example.", "A"), Q("europe.campus.example.", "A")],
     wrong=["$ORIGIN campus.example.\n$TTL 1d\n@ IN SOA ns1 noc 2024090101 6h 1h 4w 1h\n IN NS ns1\n IN NS ns2\n IN A 198.51.100.10\nns1 IN A 198.51.100.1\nns2 IN A 198.51.100.2\nwww IN CNAME @\neu IN NS ns1.eu\neu IN NS ns2.eu\nns1.eu IN A 198.51.100.101\nns2.eu IN A 198.51.100.102\n"])

# 6 ------------------------------------------------------------------------------------------------------------------
KEY = "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAu1SU1LfVLPHCozMxH2Mo4lgOEePzNm0tRgeLezV6ffAt0gunVTLw7onLRnrq0/IzW7yWR7QkrmBL7jTKEn5u+qKhbwKfBstIs+bMY2Zkp18gnTxKLxoS2tFczGkPLPgizskuemMghRniWaoLcyehkd3qqGElvW/VDL5AaWTg0nLVkjRo9z+40RQzuVaE8AkAFmxZzow3x+VJYKdjykkJ0iT9wCS0DRTXu269V264Vf/3jvredZiKRkgwlL9xNAwxXFg0x/XFw005UWVRIkdgcKWTjpBP2dPwVZ4WWC+9aGVd+Gyn1o0CLelf4rEjGoXtAPLvFPU8XV9"
O6 = "postbox.example."
spec(slug="mail-records", d=3, origin=O6, kind="author",
     prompt=pd(f'''
        Write `zones/postbox.example.zone` for `postbox.example.` (default TTL 1h; SOA `ns1.postbox.example.` / `postmaster.postbox.example.`, serial 11, refresh 7200, retry 900, expire 1209600, minimum 300; NS `ns1` = 192.0.2.1 and `ns2` = 192.0.2.2 inside the zone). Mail setup:

        - MX records of the apex: preference 10 `mx1.postbox.example.` (192.0.2.25), preference 20 `mx2.postbox.example.` (192.0.2.26), preference 30 the external `relay.backup-mx.net.`;
        - the apex text record (SPF): `v=spf1 mx ip4:192.0.2.0/24 -all`;
        - DMARC: `_dmarc.postbox.example.` TXT `v=DMARC1; p=quarantine; rua=mailto:dmarc@postbox.example`;
        - DKIM: `sel1._domainkey.postbox.example.` TXT `v=DKIM1; k=rsa; p=` followed by this public key (a single TXT string must not exceed 255 bytes, so write it as several quoted strings, which resolvers join):
          `{KEY}`
        - `autoconfig` and `imap` are aliases of `mx1.postbox.example.`; `_imaps._tcp.postbox.example.` has SRV 0 1 993 `mx1.postbox.example.` (an SRV target must not be an alias).
     ''', NOTE),
     start="; postbox zone\n",
     ref=dd(f'''
        $ORIGIN postbox.example.
        $TTL 1h
        @ IN SOA ns1 postmaster 11 7200 900 1209600 300
          IN NS ns1
          IN NS ns2
          IN MX 10 mx1
          IN MX 20 mx2
          IN MX 30 relay.backup-mx.net.
          IN TXT "v=spf1 mx ip4:192.0.2.0/24 -all"
        ns1 IN A 192.0.2.1
        ns2 IN A 192.0.2.2
        mx1 IN A 192.0.2.25
        mx2 IN A 192.0.2.26
        _dmarc IN TXT "v=DMARC1; p=quarantine; rua=mailto:dmarc@postbox.example"
        sel1._domainkey IN TXT ( "v=DKIM1; k=rsa; p={KEY[:200]}"
                                 "{KEY[200:]}" )
        autoconfig IN CNAME mx1
        imap IN CNAME mx1
        _imaps._tcp IN SRV 0 1 993 mx1
     '''),
     examples=[Q("postbox.example.", "MX", answer=["postbox.example. 3600 MX 10 mx1.postbox.example.", "postbox.example. 3600 MX 20 mx2.postbox.example.", "postbox.example. 3600 MX 30 relay.backup-mx.net."]), Q("_dmarc.postbox.example.", "TXT", answer=['_dmarc.postbox.example. 3600 TXT "v=DMARC1; p=quarantine; rua=mailto:dmarc@postbox.example"'])],
     cases=[Q("postbox.example.", "TXT"), Q("sel1._domainkey.postbox.example.", "TXT"), Q("imap.postbox.example.", "A"), Q("autoconfig.postbox.example.", "A"), Q("_imaps._tcp.postbox.example.", "SRV"), Q("mx1.postbox.example.", "A"), Q("mx2.postbox.example.", "A"), Q("postbox.example.", "NS"),
            Q("_domainkey.postbox.example.", "TXT"), Q("sel2._domainkey.postbox.example.", "TXT"), Q("postbox.example.", "A"), Q("_dmarc.postbox.example.", "MX")],
     wrong=[f'$ORIGIN postbox.example.\n$TTL 1h\n@ IN SOA ns1 postmaster 11 7200 900 1209600 300\n IN NS ns1\n IN NS ns2\n IN MX 10 mx1\n IN MX 20 mx2\n IN MX 30 relay.backup-mx.net.\n IN TXT "v=spf1 mx -all"\nns1 IN A 192.0.2.1\nns2 IN A 192.0.2.2\nmx1 IN A 192.0.2.25\nmx2 IN A 192.0.2.26\n_dmarc IN TXT "v=DMARC1; p=quarantine; rua=mailto:dmarc@postbox.example"\nsel1._domainkey IN TXT "v=DKIM1; k=rsa; p={KEY[:200]}" "{KEY[200:]}"\nautoconfig IN CNAME mx1\nimap IN CNAME mx1\n_imaps._tcp IN SRV 0 1 993 mx1\n'])

# 7 ------------------------------------------------------------------------------------------------------------------
O7 = "2.0.192.in-addr.arpa."
spec(slug="reverse-zone", d=3, origin=O7, kind="author",
     prompt=pd('''
        Write the reverse zone `zones/2.0.192.in-addr.arpa.zone` for the network 192.0.2.0/24 (origin `2.0.192.in-addr.arpa.`; default TTL 1h; SOA `ns1.harbor.example.` / `hostmaster.harbor.example.`, serial 5, refresh 7200, retry 900, expire 1209600, minimum 300; NS `ns1.harbor.example.` and `ns2.harbor.example.`, both outside this zone).
        PTR records (the owner name is the last octet, relative to the origin):

        - 192.0.2.1 -> `ns1.harbor.example.`, 192.0.2.2 -> `ns2.harbor.example.`
        - 192.0.2.10 -> `harbor.example.`
        - 192.0.2.25 -> `mail.harbor.example.` (TTL 5 minutes)
        - 192.0.2.50 and 192.0.2.51 -> `status.harbor.example.`  (two PTR records for the same name are fine, one per address)
        - 192.0.2.100 -> `vpn.harbor.example.`
     ''', NOTE),
     start="; reverse zone\n",
     ref=dd('''
        $ORIGIN 2.0.192.in-addr.arpa.
        $TTL 1h
        @ IN SOA ns1.harbor.example. hostmaster.harbor.example. 5 7200 900 1209600 300
          IN NS ns1.harbor.example.
          IN NS ns2.harbor.example.
        1   IN PTR ns1.harbor.example.
        2   IN PTR ns2.harbor.example.
        10  IN PTR harbor.example.
        25  300 IN PTR mail.harbor.example.
        50  IN PTR status.harbor.example.
        51  IN PTR status.harbor.example.
        100 IN PTR vpn.harbor.example.
     '''),
     examples=[Q("1.2.0.192.in-addr.arpa.", "PTR", answer=["1.2.0.192.in-addr.arpa. 3600 PTR ns1.harbor.example."]), Q("25.2.0.192.in-addr.arpa.", "PTR", answer=["25.2.0.192.in-addr.arpa. 300 PTR mail.harbor.example."]), Q("3.2.0.192.in-addr.arpa.", "PTR", rcode="NXDOMAIN")],
     cases=[Q("2.2.0.192.in-addr.arpa.", "PTR"), Q("10.2.0.192.in-addr.arpa.", "PTR"), Q("50.2.0.192.in-addr.arpa.", "PTR"), Q("51.2.0.192.in-addr.arpa.", "PTR"), Q("100.2.0.192.in-addr.arpa.", "PTR"), Q("101.2.0.192.in-addr.arpa.", "PTR"), Q("2.0.192.in-addr.arpa.", "NS"), Q("2.0.192.in-addr.arpa.", "SOA"),
            Q("1.2.0.192.in-addr.arpa.", "A"), Q("200.2.0.192.in-addr.arpa.", "PTR"), Q("1.3.0.192.in-addr.arpa.", "PTR")],
     wrong=["$ORIGIN 2.0.192.in-addr.arpa.\n$TTL 1h\n@ IN SOA ns1.harbor.example. hostmaster.harbor.example. 5 7200 900 1209600 300\n IN NS ns1.harbor.example.\n IN NS ns2.harbor.example.\n1 IN PTR ns1.harbor.example.\n2 IN PTR ns2.harbor.example.\n10 IN PTR harbor.example.\n25 IN PTR mail.harbor.example.\n50 IN PTR status.harbor.example.\n100 IN PTR vpn.harbor.example.\n"])

# 8 ------------------------------------------------------------------------------------------------------------------
O8 = "vane.example."
spec(slug="ttl-layers", d=3, origin=O8, kind="author",
     prompt=pd('''
        Write `zones/vane.example.zone` for `vane.example.` where TTLs matter (the checker asks for them). Default TTL 5 minutes; SOA `ns1.vane.example.` / `ops.vane.example.`, serial 42, refresh 1h, retry 10m, expire 1w, minimum 5m.
        Records:

        - apex NS `ns1` and `ns2` (inside the zone, 198.51.100.1 and 198.51.100.2): TTL 1 day; their A records TTL 1 day as well;
        - apex A 198.51.100.10: TTL 90 minutes; apex MX 10 `mail.vane.example.`: default TTL; `mail` A 198.51.100.25: TTL 12 hours;
        - `www` CNAME of the apex: TTL 1 hour 30 minutes (5400 s); `api` A 198.51.100.30 and 198.51.100.31: default TTL;
        - `static` A 198.51.100.40: TTL 7 days; `canary` A 198.51.100.50: TTL 30 seconds;
        - the SOA record itself has the default TTL.
     ''', NOTE),
     start="; vane zone\n",
     ref=dd('''
        $ORIGIN vane.example.
        $TTL 5m
        @ IN SOA ns1 ops 42 1h 10m 1w 5m
          1d IN NS ns1
          1d IN NS ns2
          90m IN A 198.51.100.10
          IN MX 10 mail
        ns1 1d IN A 198.51.100.1
        ns2 1d IN A 198.51.100.2
        mail 12h IN A 198.51.100.25
        www 1h30m IN CNAME @
        api IN A 198.51.100.30
            IN A 198.51.100.31
        static 7d IN A 198.51.100.40
        canary 30 IN A 198.51.100.50
     '''),
     examples=[Q("vane.example.", "A", answer=["vane.example. 5400 A 198.51.100.10"]), Q("static.vane.example.", "A", answer=["static.vane.example. 604800 A 198.51.100.40"]), Q("api.vane.example.", "A", answer=["api.vane.example. 300 A 198.51.100.30", "api.vane.example. 300 A 198.51.100.31"])],
     cases=[Q("vane.example.", "SOA"), Q("vane.example.", "NS"), Q("vane.example.", "MX"), Q("ns1.vane.example.", "A"), Q("ns2.vane.example.", "A"), Q("mail.vane.example.", "A"), Q("www.vane.example.", "A"), Q("www.vane.example.", "CNAME"), Q("canary.vane.example.", "A"), Q("canary.vane.example.", "AAAA")],
     wrong=["$ORIGIN vane.example.\n$TTL 5m\n@ IN SOA ns1 ops 42 1h 10m 1w 5m\n 1d IN NS ns1\n 1d IN NS ns2\n 90m IN A 198.51.100.10\n IN MX 10 mail\nns1 1d IN A 198.51.100.1\nns2 1d IN A 198.51.100.2\nmail 12h IN A 198.51.100.25\nwww 1h IN CNAME @\napi IN A 198.51.100.30\n IN A 198.51.100.31\nstatic 7d IN A 198.51.100.40\ncanary 30 IN A 198.51.100.50\n"])

# 9 ------------------------------------------------------------------------------------------------------------------
O9 = "relay.example."
spec(slug="srv-and-caa", d=3, origin=O9, kind="author",
     prompt=pd('''
        Write `zones/relay.example.zone` for `relay.example.` (default TTL 1h; SOA `ns1.relay.example.` / `dns.relay.example.`, serial 9, refresh 3h, retry 30m, expire 2w, minimum 10m; NS `ns1` = 203.0.113.1 and `ns2` = 203.0.113.2). Service records:

        - `_sip._tcp.relay.example.`: SRV priority 10 weight 60 port 5060 to `sip1.relay.example.` and priority 10 weight 40 port 5060 to `sip2.relay.example.`, and a fallback priority 20 weight 0 port 5060 to `sip3.relay.example.`; the three hosts are 203.0.113.61, .62 and .63;
        - `_xmpp-client._tcp.relay.example.`: SRV 5 0 5222 to `chat.relay.example.` (203.0.113.70);
        - certificate policy (CAA on the apex): `0 issue "letsencrypt.org"`, `0 issuewild ";"` (no wildcard certificates), `0 iodef "mailto:security@relay.example"`;
        - the apex has the address 203.0.113.10.
     ''', NOTE),
     start="; relay zone\n",
     ref=dd('''
        $ORIGIN relay.example.
        $TTL 1h
        @ IN SOA ns1 dns 9 3h 30m 2w 10m
          IN NS ns1
          IN NS ns2
          IN A 203.0.113.10
          IN CAA 0 issue "letsencrypt.org"
          IN CAA 0 issuewild ";"
          IN CAA 0 iodef "mailto:security@relay.example"
        ns1 IN A 203.0.113.1
        ns2 IN A 203.0.113.2
        sip1 IN A 203.0.113.61
        sip2 IN A 203.0.113.62
        sip3 IN A 203.0.113.63
        chat IN A 203.0.113.70
        _sip._tcp IN SRV 10 60 5060 sip1
                  IN SRV 10 40 5060 sip2
                  IN SRV 20 0 5060 sip3
        _xmpp-client._tcp IN SRV 5 0 5222 chat
     '''),
     examples=[Q("_xmpp-client._tcp.relay.example.", "SRV", answer=["_xmpp-client._tcp.relay.example. 3600 SRV 5 0 5222 chat.relay.example."]), Q("relay.example.", "CAA", answer=['relay.example. 3600 CAA 0 iodef "mailto:security@relay.example"', 'relay.example. 3600 CAA 0 issue "letsencrypt.org"', 'relay.example. 3600 CAA 0 issuewild ";"'])],
     cases=[Q("_sip._tcp.relay.example.", "SRV"), Q("_sip._udp.relay.example.", "SRV"), Q("sip1.relay.example.", "A"), Q("sip3.relay.example.", "A"), Q("chat.relay.example.", "A"), Q("relay.example.", "A"), Q("relay.example.", "NS"), Q("_tcp.relay.example.", "SRV"), Q("sip.relay.example.", "A")],
     wrong=['$ORIGIN relay.example.\n$TTL 1h\n@ IN SOA ns1 dns 9 3h 30m 2w 10m\n IN NS ns1\n IN NS ns2\n IN A 203.0.113.10\n IN CAA 0 issue "letsencrypt.org"\n IN CAA 0 iodef "mailto:security@relay.example"\nns1 IN A 203.0.113.1\nns2 IN A 203.0.113.2\nsip1 IN A 203.0.113.61\nsip2 IN A 203.0.113.62\nsip3 IN A 203.0.113.63\nchat IN A 203.0.113.70\n_sip._tcp IN SRV 10 60 5060 sip1\n IN SRV 10 40 5060 sip2\n IN SRV 20 0 5060 sip3\n_xmpp-client._tcp IN SRV 5 0 5222 chat\n'])

# 10 -----------------------------------------------------------------------------------------------------------------
O10 = "orchard.example."
spec(slug="zone-repair-mixed", d=4, origin=O10, kind="fix",
     prompt=pd('''
        The zone file `zones/orchard.example.zone` was edited by three people and no longer loads. Repair it so that it passes the zone check and answers like this (everything not listed stays as it is):

        - `orchard.example.` has addresses 192.0.2.10 and 2001:db8::10, MX 10 `mail.orchard.example.`, NS `ns1.orchard.example.` and `ns2.orchard.example.` (both in the zone);
        - `mail.orchard.example.` = 192.0.2.25; `www` and `shop` are aliases of the apex; `ns1` = 192.0.2.1, `ns2` = 192.0.2.2;
        - `lab.orchard.example.` is delegated to `ns.lab.orchard.example.` (192.0.2.200, glue in this zone); `old.orchard.example.` no longer exists.
        - the SPF text of the apex is `v=spf1 mx -all`; the long text `notes` is the concatenation of the two quoted strings in the file.
     ''', NOTE),
     start=dd('''
        $ORIGIN orchard.example.
        @ IN SOA ns1 hostmaster 2024051701 7200 900 1209600
          IN NS ns1
          IN NS ns2.orchard.example
          IN A 192.0.2.10
          IN AAAA 2001:db8::10
          IN MX 10 mail
          IN TXT v=spf1 mx -all
        ns1 IN A 192.0.2.1
        ns2 IN A 192.0.2.2
        mail IN A 192.0.2.25
        www IN CNAME @
        shop IN CNAME orchard.example.
              IN A 192.0.2.10
        lab IN NS ns.lab
        ns.lab IN A 192.0.2.200
        host.lab IN A 192.0.2.201
        old IN A 192.0.2.99
        notes IN TXT "first part of the note, " "second part"
     '''),
     ref=dd('''
        $ORIGIN orchard.example.
        $TTL 3600
        @ IN SOA ns1 hostmaster 2024051701 7200 900 1209600 300
          IN NS ns1
          IN NS ns2.orchard.example.
          IN A 192.0.2.10
          IN AAAA 2001:db8::10
          IN MX 10 mail
          IN TXT "v=spf1 mx -all"
        ns1 IN A 192.0.2.1
        ns2 IN A 192.0.2.2
        mail IN A 192.0.2.25
        www IN CNAME @
        shop IN CNAME orchard.example.
        lab IN NS ns.lab
        ns.lab IN A 192.0.2.200
        notes IN TXT "first part of the note, " "second part"
     '''),
     examples=[Q("shop.orchard.example.", "A", answer=["shop.orchard.example. 3600 CNAME orchard.example.", "orchard.example. 3600 A 192.0.2.10"]), Q("x.lab.orchard.example.", "A", glue=["ns.lab.orchard.example. 3600 A 192.0.2.200"]), Q("old.orchard.example.", "A", rcode="NXDOMAIN")],
     cases=[Q("orchard.example.", "TXT"), Q("orchard.example.", "SOA"), Q("orchard.example.", "NS"), Q("orchard.example.", "MX"), Q("orchard.example.", "AAAA"), Q("www.orchard.example.", "A"), Q("mail.orchard.example.", "A"), Q("notes.orchard.example.", "TXT"), Q("lab.orchard.example.", "NS"),
            Q("host.lab.orchard.example.", "A"), Q("ns2.orchard.example.", "A"), Q("shop.orchard.example.", "CNAME")],
     wrong=["$ORIGIN orchard.example.\n$TTL 3600\n@ IN SOA ns1 hostmaster 2024051701 7200 900 1209600 300\n IN NS ns1\n IN NS ns2.orchard.example.\n IN A 192.0.2.10\n IN AAAA 2001:db8::10\n IN MX 10 mail\n IN TXT \"v=spf1 mx -all\"\nns1 IN A 192.0.2.1\nns2 IN A 192.0.2.2\nmail IN A 192.0.2.25\nwww IN CNAME @\nshop IN CNAME orchard.example.\nlab IN NS ns.lab\nns.lab IN A 192.0.2.200\nold IN A 192.0.2.99\nnotes IN TXT \"first part of the note, \" \"second part\"\n"])


def _tasks(rng, n):
    return [make_task(s) for s in SPECS[:n]]


@family("devops-dns-zones", category="devops", lang="text", kind="fix", n=len(SPECS),
        summary="write or repair DNS zone files judged by a documented zone checker and authoritative-answer simulator: trailing dots, CNAME rules, wildcards, delegation and glue, TTLs, mail and service records")
def dns_zones(rng, n):
    return _tasks(rng, n)
