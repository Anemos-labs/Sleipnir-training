"""DevOps tasks: ssh_config. A documented resolver (given to the agent as tools/sshsim.py) tells what `ssh -G` would print for hosts the agent has not seen."""
import json
import types
from dataclasses import dataclass, field

from fx import dd, family
from generators.devops import _dokit as K
from generators.devops._sshsim import SSHSIM

_mod = types.ModuleType("sshsim")
exec(compile(SSHSIM, "sshsim.py", "exec"), _mod.__dict__)
ss = _mod

CHECK_SSH = r'''
from dolib import *
sys.path.insert(0, "tests")
import sshsim

spec = json.load(open("tests/cases.json", encoding="utf-8"))
try:
    blocks = sshsim.parse(read(spec["path"]))
except sshsim.SshError as e:
    die(f"{spec['path']}: {e}")
rep = Report()
for c in spec["cases"]:
    q = c["q"]
    res = sshsim.resolve(blocks, q["host"], q.get("user"))
    bad = sshsim.matches(res, c["expect"])
    rep.check(not bad, f"ssh {'-l ' + q['user'] + ' ' if q.get('user') else ''}{q['host']}: " + "; ".join(bad))
rep.finish()
'''


def S(host, u=None, **expect):
    q = {"host": host}
    if u:
        q["user"] = u
    return {"q": q, **({"expect": expect} if expect else {})}


@dataclass
class SshSpec:
    slug: str
    d: int
    prompt: str
    ref: str
    start: str
    examples: list
    cases: list
    wrong: list = field(default_factory=list)
    kind: str = "author"
    keys: tuple = ("hostname", "user", "port", "identityfile", "proxyjump", "forwardagent", "serveraliveinterval", "identitiesonly", "localforward", "controlpath", "controlmaster")


def make_task(sp: SshSpec):
    blocks = ss.parse(sp.ref)

    def ask(c):
        return ss.resolve(blocks, c["q"]["host"], c["q"].get("user"))
    for c in sp.examples:
        bad = ss.matches(ask(c), c["expect"])
        if bad:
            raise RuntimeError(f"{sp.slug}: example {c['q']} disagrees with the reference: {bad} (got {ask(c)})")
    cases = []
    for c in sp.examples + sp.cases:
        r = ask(c)
        cases.append({"q": c["q"], "expect": {k: v for k, v in r.items() if k in sp.keys}})
    start = {"ssh_config": sp.start, "tools/sshsim.py": SSHSIM, "examples.json": json.dumps(sp.examples, indent=1) + "\n",
             "README.md": "# ssh_config exercise\n\nEdit `ssh_config`. `python3 tools/sshsim.py ssh_config HOST [USER]` prints what `ssh -G` would resolve for a host, `python3 tools/sshsim.py ssh_config examples.json` runs the example queries; `python3 tools/sshsim.py` documents the supported subset of the format.\n"}
    hidden = {"tests/sshsim.py": "# verifier copy of tools/sshsim.py\n" + SSHSIM, "tests/cases.json": json.dumps({"path": "ssh_config", "cases": cases}, indent=1) + "\n"}
    t = K.devops_task(sp.slug, sp.d, sp.prompt, start, {"ssh_config": sp.ref}, CHECK_SSH, hidden, lang="text", kind="fix" if sp.kind == "fix" else "greenfield", tags=["ssh", "ssh_config", "config"])
    return K.finish(t, wrong=[{"ssh_config": w} for w in sp.wrong])


SPECS: list[SshSpec] = []


def spec(**kw):
    SPECS.append(SshSpec(**kw))


NOTE = "\n\n`tools/sshsim.py` resolves hosts against `ssh_config` like `ssh -G` (its docstring lists the supported subset and the rules); `examples.json` has examples with expected values."

# 1 ------------------------------------------------------------------------------------------------------------------
spec(slug="jump-host-basics", d=1, kind="author",
     prompt=dd('''
        Write `ssh_config` for these hosts (what `ssh <name>` must resolve to):

        - `bastion`: real name `bastion.corp.example`, user `ops`, port 2222;
        - `app1`, `app2`, `app3` (any `app` followed by one character): real name `<name>.corp.example`, user `deploy`, port 22, reached through the jump host `bastion`;
        - every other host: nothing special (defaults).
     ''' + NOTE),
     start="# ssh client configuration\n",
     ref=dd('''
        Host bastion
            HostName bastion.corp.example
            User ops
            Port 2222

        Host app?
            HostName %h.corp.example
            User deploy
            ProxyJump bastion
     '''),
     examples=[S("bastion", hostname="bastion.corp.example", user="ops", port=2222), S("app2", hostname="app2.corp.example", user="deploy", port=22, proxyjump="bastion"), S("other", hostname="other", user="tester", port=22)],
     cases=[S("app1"), S("app3"), S("app10"), S("app"), S("APP4"), S("bastion", "root"), S("app2", "alice"), S("db1"), S("bastion2"), S("web.example.org", "bob")],
     wrong=["Host bastion\n    HostName bastion.corp.example\n    User ops\n    Port 2222\n\nHost app?\n    HostName app?.corp.example\n    User deploy\n    ProxyJump bastion\n"])

# 2 ------------------------------------------------------------------------------------------------------------------
spec(slug="first-match-wins-fix", d=2, kind="fix",
     prompt=dd('''
        `ssh_config` is meant to give every host `ServerAliveInterval 30` and `ForwardAgent no`, and the build server a user and port of its own, but `ssh build.corp.example` connects as the default user on port 22.
        Required: `build.corp.example` -> user `ci`, port 2200, `IdentityFile ~/.ssh/ci_ed25519`; `*.corp.example` (other hosts) -> user `deploy`; all hosts -> ServerAliveInterval 30 and ForwardAgent no. Fix the file.
     ''' + NOTE),
     start=dd('''
        Host *
            ServerAliveInterval 30
            ForwardAgent no
            User deploy
            Port 22

        Host *.corp.example
            User deploy

        Host build.corp.example
            User ci
            Port 2200
            IdentityFile ~/.ssh/ci_ed25519
     '''),
     ref=dd('''
        Host build.corp.example
            User ci
            Port 2200
            IdentityFile ~/.ssh/ci_ed25519

        Host *.corp.example
            User deploy

        Host *
            ServerAliveInterval 30
            ForwardAgent no
     '''),
     examples=[S("build.corp.example", user="ci", port=2200, identityfile=["~/.ssh/ci_ed25519"], serveraliveinterval="30"), S("git.corp.example", user="deploy", port=22, forwardagent="no"), S("example.org", user="tester", serveraliveinterval="30")],
     cases=[S("build.corp.example", "alice"), S("deploy.corp.example"), S("corp.example"), S("x.y.corp.example"), S("build2.corp.example"), S("BUILD.corp.example"), S("github.com"), S("github.com", "git")],
     wrong=["Host *.corp.example\n    User deploy\n\nHost build.corp.example\n    User ci\n    Port 2200\n    IdentityFile ~/.ssh/ci_ed25519\n\nHost *\n    ServerAliveInterval 30\n    ForwardAgent no\n"])

# 3 ------------------------------------------------------------------------------------------------------------------
spec(slug="negated-patterns", d=3, kind="author",
     prompt=dd('''
        Write `ssh_config` for the corp network:

        - every host of `*.corp.example` is reached through the jump host `bastion.corp.example` (ProxyJump) and logs in as `deploy` - **except** `bastion.corp.example` itself, which is reached directly (no ProxyJump), as user `ops`, port 2222;
        - the lab machines `*.lab.corp.example` are reachable directly (no jump host: the effective ProxyJump is `none`) and log in as `lab`;
        - hosts outside corp.example have no special settings.
        Tip: patterns can be negated with `!`, and the first value found wins.
     ''' + NOTE),
     start="# ssh client configuration\n",
     ref=dd('''
        Host bastion.corp.example
            User ops
            Port 2222

        Host *.lab.corp.example
            User lab
            ProxyJump none

        Host *.corp.example !bastion.corp.example
            User deploy
            ProxyJump bastion.corp.example
     '''),
     examples=[S("bastion.corp.example", user="ops", port=2222), S("git.corp.example", user="deploy", proxyjump="bastion.corp.example"), S("gpu1.lab.corp.example", user="lab", proxyjump="none"), S("example.org", user="tester")],
     cases=[S("bastion.corp.example", "root"), S("a.corp.example", "bob"), S("a.b.corp.example"), S("x.lab.corp.example"), S("lab.corp.example"), S("corp.example"), S("bastion.lab.corp.example"), S("mycorp.example"), S("BASTION.CORP.EXAMPLE"), S("git.corp.example", "ci")],
     wrong=["Host *.corp.example\n    User deploy\n    ProxyJump bastion.corp.example\n\nHost bastion.corp.example\n    User ops\n    Port 2222\n\nHost *.lab.corp.example\n    User lab\n    ProxyJump none\n"])

# 4 ------------------------------------------------------------------------------------------------------------------
spec(slug="identity-file-order", d=3, kind="author",
     prompt=dd('''
        Write `ssh_config`. `IdentityFile` accumulates: every matching block adds a key, in file order (that is the order in which ssh tries them). Requirements (the effective `identityfile` list per host):

        - `github.com`: only `~/.ssh/github_ed25519` (and `IdentitiesOnly yes` so no other key is offered);
        - `*.corp.example`: first `~/.ssh/corp_ed25519`, then the default key `~/.ssh/id_ed25519`;
        - `gitlab.corp.example` (it matches the previous rule too): first `~/.ssh/gitlab_ed25519`, then `~/.ssh/corp_ed25519`, then `~/.ssh/id_ed25519`, with `IdentitiesOnly yes`;
        - every other host: just `~/.ssh/id_ed25519`.
        (A key that must appear for all hosts as the last one is a hint for where `Host *` goes.)
     ''' + NOTE),
     start="# ssh client configuration\n",
     ref=dd('''
        Host github.com
            IdentityFile ~/.ssh/github_ed25519
            IdentitiesOnly yes

        Host gitlab.corp.example
            IdentityFile ~/.ssh/gitlab_ed25519
            IdentitiesOnly yes

        Host *.corp.example
            IdentityFile ~/.ssh/corp_ed25519

        Host * !github.com
            IdentityFile ~/.ssh/id_ed25519
     '''),
     examples=[S("github.com", identityfile=["~/.ssh/github_ed25519"], identitiesonly="yes"), S("gitlab.corp.example", identityfile=["~/.ssh/gitlab_ed25519", "~/.ssh/corp_ed25519", "~/.ssh/id_ed25519"]), S("example.org", identityfile=["~/.ssh/id_ed25519"])],
     cases=[S("wiki.corp.example"), S("corp.example"), S("gitlab.example"), S("a.gitlab.corp.example"), S("git.github.com"), S("bitbucket.org"), S("gitlab.corp.example", "git"), S("github.com", "git")],
     wrong=["Host github.com\n    IdentityFile ~/.ssh/github_ed25519\n    IdentitiesOnly yes\n\nHost *.corp.example\n    IdentityFile ~/.ssh/corp_ed25519\n\nHost gitlab.corp.example\n    IdentityFile ~/.ssh/gitlab_ed25519\n    IdentitiesOnly yes\n\nHost * !github.com\n    IdentityFile ~/.ssh/id_ed25519\n"])

# 5 ------------------------------------------------------------------------------------------------------------------
spec(slug="match-blocks", d=4, kind="author",
     prompt=dd('''
        Write `ssh_config` using `Match` where needed:

        - `db` is an alias: `HostName db1.corp.example`, user `dba`;
        - for every connection whose **target host name** (after the HostName above has been applied) matches `db*.corp.example`: `Port 5022` and `IdentityFile ~/.ssh/db_ed25519`. So both `ssh db` and `ssh db2.corp.example` get them;
        - whenever the remote user is `root` (`ssh -l root host` / `root@host`) on a `*.corp.example` host (as typed): `IdentityFile ~/.ssh/root_ed25519` first, `IdentitiesOnly yes`, and `ForwardAgent no`;
        - everything else: `ForwardAgent yes`.
        `Match host` sees the host name after earlier blocks of the file have set `HostName`; `Match originalhost` sees what was typed. First value wins.
     ''' + NOTE),
     start="# ssh client configuration\n",
     ref=dd('''
        Host db
            HostName db1.corp.example
            User dba

        Match host db*.corp.example
            Port 5022
            IdentityFile ~/.ssh/db_ed25519

        Match user root originalhost *.corp.example
            IdentityFile ~/.ssh/root_ed25519
            IdentitiesOnly yes
            ForwardAgent no

        Host *
            ForwardAgent yes
     '''),
     examples=[S("db", hostname="db1.corp.example", user="dba", port=5022, identityfile=["~/.ssh/db_ed25519"]), S("db2.corp.example", port=5022), S("web.corp.example", "root", identityfile=["~/.ssh/root_ed25519"], forwardagent="no", identitiesonly="yes")],
     cases=[S("web.corp.example"), S("web.corp.example", "alice"), S("db2.corp.example", "root"), S("db", "root"), S("db"), S("db.corp.example"), S("dbx.corp.example"), S("example.org", "root"), S("example.org"), S("db3.example.org"), S("bastion.corp.example", "root")],
     wrong=["Host db\n    HostName db1.corp.example\n    User dba\n\nMatch originalhost db*.corp.example\n    Port 5022\n    IdentityFile ~/.ssh/db_ed25519\n\nMatch user root originalhost *.corp.example\n    IdentityFile ~/.ssh/root_ed25519\n    IdentitiesOnly yes\n    ForwardAgent no\n\nHost *\n    ForwardAgent yes\n"])

# 6 ------------------------------------------------------------------------------------------------------------------
spec(slug="forwards-and-multiplexing", d=3, kind="author",
     prompt=dd('''
        Write `ssh_config`:

        - `tunnel`: `HostName bastion.corp.example`, user `ops`, port 2222, and two local forwards (`LocalForward` takes `LISTENPORT HOST:PORT`): `5432 db1.corp.example:5432` and `8080 intranet.corp.example:80`;
        - connection sharing for every host: `ControlMaster auto`, `ControlPath ~/.ssh/cm-%r@%h:%p`, `ControlPersist 10m` (the checker sees the path with the tokens expanded for each host: for `tunnel` it is `~/.ssh/cm-ops@bastion.corp.example:2222`);
        - `ServerAliveInterval 30` for every host except the ones named `unstable-*`, which get 10.
     ''' + NOTE),
     start="# ssh client configuration\n",
     ref=dd('''
        Host tunnel
            HostName bastion.corp.example
            User ops
            Port 2222
            LocalForward 5432 db1.corp.example:5432
            LocalForward 8080 intranet.corp.example:80

        Host unstable-*
            ServerAliveInterval 10

        Host *
            ServerAliveInterval 30
            ControlMaster auto
            ControlPath ~/.ssh/cm-%r@%h:%p
            ControlPersist 10m
     '''),
     examples=[S("tunnel", hostname="bastion.corp.example", user="ops", port=2222, localforward=["5432 db1.corp.example:5432", "8080 intranet.corp.example:80"], controlpath="~/.ssh/cm-ops@bastion.corp.example:2222"),
               S("unstable-lab", serveraliveinterval="10"), S("example.org", serveraliveinterval="30", controlpath="~/.ssh/cm-tester@example.org:22")],
     cases=[S("unstable-"), S("unstable-a", "bob"), S("tunnel", "alice"), S("x.example.org", "carol"), S("stable-unstable-x"), S("unstablehost")],
     wrong=["Host tunnel\n    HostName bastion.corp.example\n    User ops\n    Port 2222\n    LocalForward 5432 db1.corp.example:5432\n    LocalForward 8080 intranet.corp.example:80\n\nHost *\n    ServerAliveInterval 30\n    ControlMaster auto\n    ControlPath ~/.ssh/cm-%r@%h:%p\n    ControlPersist 10m\n\nHost unstable-*\n    ServerAliveInterval 10\n"])

# 7 ------------------------------------------------------------------------------------------------------------------
spec(slug="syntax-errors-fix", d=2, kind="fix",
     prompt=dd('''
        `ssh -G` refuses `ssh_config` ("Bad configuration option", "missing argument", unterminated quote). The intended meaning: `staging` is `staging.corp.example`, user `deploy`, port 2200, key `~/.ssh/stage key` (a path with a space, so it needs quotes),
        `*.corp.example` uses user `deploy` too, and every host gets `ServerAliveInterval 20`. Repair the file keeping that meaning.
     ''' + NOTE),
     start=dd('''
        Host staging
            HostNme staging.corp.example
            User deploy
            Port
            IdentityFile "~/.ssh/stage key

        Host *.corp.example
            User deploy

        Host *
            ServerAliveInterval = 20
            Compresion yes
     '''),
     ref=dd('''
        Host staging
            HostName staging.corp.example
            User deploy
            Port 2200
            IdentityFile "~/.ssh/stage key"

        Host *.corp.example
            User deploy

        Host *
            ServerAliveInterval 20
     '''),
     examples=[S("staging", hostname="staging.corp.example", user="deploy", port=2200, identityfile=["~/.ssh/stage key"], serveraliveinterval="20"), S("git.corp.example", user="deploy", port=22)],
     cases=[S("staging", "root"), S("staging.corp.example"), S("x.corp.example", "bob"), S("example.org"), S("example.org", "alice")],
     wrong=["Host staging\n    HostName staging.corp.example\n    User deploy\n    Port 2200\n    IdentityFile ~/.ssh/stage key\n"])

# 8 ------------------------------------------------------------------------------------------------------------------
spec(slug="client-policy", d=5, kind="author",
     prompt=dd('''
        Write the complete `ssh_config` of an engineer. Everything below must hold (the checker resolves many hosts):

        1. Defaults for all hosts: `ServerAliveInterval 30`, `ForwardAgent no`, `IdentityFile ~/.ssh/id_ed25519` as the last key tried.
        2. `bastion.corp.example`: user `ops`, port 2222, no jump host, key `~/.ssh/ops_ed25519` first.
        3. All other `*.corp.example` hosts: jump through `bastion.corp.example`, user `deploy`, key `~/.ssh/corp_ed25519` before the default; `*.lab.corp.example` has no jump host (`ProxyJump none`) and user `lab`.
        4. Short aliases: `web` and `api` are `web.corp.example` / `api.corp.example` (use `%h`), and keep every setting of the host they point to (a `Match host` block can do that); `ForwardAgent yes` for `api` only.
        5. `github.com`: user `git`, only the key `~/.ssh/github_ed25519`, `IdentitiesOnly yes`.
        6. Whenever the remote user is `root` (`root@host` or `-l root`), on any host: `~/.ssh/root_ed25519` is the first key tried and `IdentitiesOnly yes` is set; other settings are not affected (keys accumulate).
     '''),
     start="# ssh client configuration\n",
     ref=dd('''
        Match user root
            IdentityFile ~/.ssh/root_ed25519
            IdentitiesOnly yes

        Host github.com
            User git
            IdentityFile ~/.ssh/github_ed25519
            IdentitiesOnly yes

        Host api
            ForwardAgent yes

        Host web api
            HostName %h.corp.example

        Host bastion.corp.example
            User ops
            Port 2222
            IdentityFile ~/.ssh/ops_ed25519

        Host *.lab.corp.example
            User lab
            ProxyJump none

        Match host *.corp.example !host bastion.corp.example
            User deploy
            ProxyJump bastion.corp.example
            IdentityFile ~/.ssh/corp_ed25519

        Host *
            ServerAliveInterval 30
            ForwardAgent no
            IdentityFile ~/.ssh/id_ed25519
     '''.replace("Match host *.corp.example !host bastion.corp.example", "Match host *.corp.example,!bastion.corp.example")),
     examples=[S("web", hostname="web.corp.example", user="deploy", proxyjump="bastion.corp.example", identityfile=["~/.ssh/corp_ed25519", "~/.ssh/id_ed25519"], forwardagent="no"), S("api", forwardagent="yes", hostname="api.corp.example"),
               S("github.com", user="git", identityfile=["~/.ssh/github_ed25519", "~/.ssh/id_ed25519"], identitiesonly="yes")],
     cases=[S("bastion.corp.example"), S("bastion.corp.example", "root"), S("git.corp.example"), S("gpu.lab.corp.example"), S("web", "root"), S("api", "root"), S("example.org", "root"), S("example.org"), S("github.com", "root"), S("a.b.corp.example"), S("corp.example")],
     wrong=["Host *\n    ServerAliveInterval 30\n    ForwardAgent no\n    IdentityFile ~/.ssh/id_ed25519\n"])


def _tasks(rng, n):
    return [make_task(s) for s in SPECS[:n]]


@family("devops-ssh-config", category="devops", lang="text", kind="fix", n=len(SPECS),
        summary="write or repair ssh_config files judged by a documented ssh -G resolver: first-match-wins, negated patterns, accumulating IdentityFile, Match host/user, token expansion")
def ssh_config(rng, n):
    return _tasks(rng, n)
