"""DevOps tasks: Ansible playbooks repaired against a mechanical lint policy (FQCN, idempotence, handlers, quoting, variables, secrets)."""
import copy
import json
import re

from fx import dd, family
from generators.devops import _dokit as K
from generators.devops import _yamlw as Y

CHECK_ANSIBLE = r'''
from dolib import *

R = json.load(open("tests/rules.json", encoding="utf-8"))
PATH = R["path"]
try:
    docs = yaml_docs(PATH)
except ValueError as e:
    die(f"{PATH} is not valid YAML: {e}")
rep = Report()
if not (len(docs) == 1 and isinstance(docs[0], list) and len(docs[0]) == 1 and isinstance(docs[0][0], dict)):
    die("the playbook must be a YAML list with exactly one play")
play = docs[0][0]
tasks, handlers = as_list(play.get("tasks")), as_list(play.get("handlers"))
META = {"name", "when", "notify", "register", "become", "become_user", "loop", "with_items", "tags", "changed_when", "failed_when", "no_log", "vars", "environment", "args", "delegate_to", "listen", "ignore_errors",
        "retries", "delay", "until", "loop_control", "check_mode", "any_errors_fatal", "async", "poll", "run_once", "block", "rescue", "always"}


def module_of(t):
    ms = [k for k in t if k not in META]
    return (ms[0] if len(ms) == 1 else None), len(ms)


def margs(t, m):
    a = t.get(m)
    return a if isinstance(a, dict) else {}


# R1 structure
for k in ("hosts", "tasks"):
    rep.check(k in play, f"the play needs `{k}`")
rep.check(play.get("hosts") == R["hosts"], f"the play must target hosts: {R['hosts']} (got {play.get('hosts')!r})")

# R2 names
names = []
for lst, what in ((tasks, "task"), (handlers, "handler")):
    for i, t in enumerate(lst):
        if not isinstance(t, dict):
            rep.check(False, f"{what} #{i + 1} is not a mapping")
            continue
        n = t.get("name")
        rep.check(isinstance(n, str) and n.strip() != "", f"{what} #{i + 1} has no name")
        names.append(n)
rep.check(len([n for n in names if n]) == len(set(n for n in names if n)), "task and handler names must be unique")
for need in R["keep"]:
    rep.check(any(isinstance(t, dict) and t.get("name") == need for t in tasks), f"the task {need!r} must stay")

# R3 FQCN
for t in tasks + handlers:
    if not isinstance(t, dict):
        continue
    m, cnt = module_of(t)
    if m is None:
        rep.check(False, f"task {t.get('name')!r}: exactly one module per task is expected (found {cnt})")
        continue
    t["_m"] = m
    if "." not in m:
        rep.check(False, f"task {t.get('name')!r}: module `{m}` must be written with its collection name (ansible.builtin.{m})")
    elif m.startswith("ansible.builtin."):
        t["_m"] = m
    rep.check(m != "ansible.builtin.shell" or re.search(r"[|><&;]", str(t[m] if not isinstance(t[m], dict) else t[m].get("cmd", ""))), f"task {t.get('name')!r}: use ansible.builtin.command unless the command needs a shell feature (pipe, redirect, &&)")

short = lambda m: m.split(".")[-1]
defined = set(R["vars"]) | set((play.get("vars") or {}).keys())
JKW = {"if", "else", "elif", "in", "and", "or", "not", "true", "false", "none", "is", "defined", "undefined", "default", "True", "False", "None", "omit", "item", "inventory_hostname", "hostvars", "groups", "ansible_check_mode", "loop"}


def idents(expr):
    e = re.sub(r"'[^']*'|\"[^\"]*\"", " ", expr)
    e = re.sub(r"\|\s*\w+", " ", e)
    e = re.sub(r"\.\w+", " ", e)
    return [x for x in re.findall(r"[A-Za-z_]\w*", e) if x not in JKW and not x.startswith("ansible_") and not re.fullmatch(r"\d+", x)]


def undefined_in(value, env, tag):
    if isinstance(value, dict):
        for v in value.values():
            undefined_in(v, env, tag)
    elif isinstance(value, list):
        for v in value:
            undefined_in(v, env, tag)
    elif isinstance(value, str):
        for expr in re.findall(r"\{\{(.*?)\}\}", value):
            if "default(" in expr:
                continue
            for x in idents(expr):
                rep.check(x in env, f"{tag}: the variable `{x}` is not defined (play vars, register, facts)")


env = set(defined)
for t in tasks:
    if not isinstance(t, dict):
        continue
    tag = f"task {t.get('name')!r}"
    m = t.get("_m")
    sub = {k: v for k, v in t.items() if k not in ("name", "register", "_m")}
    undefined_in({k: v for k, v in sub.items() if k != "when"}, env, tag)
    w = t.get("when")
    if isinstance(w, str):
        rep.check("{{" not in w, f"{tag}: `when:` is already an expression, do not wrap it in {{{{ }}}}")
        for x in idents(w):
            rep.check(x in env, f"{tag}: the variable `{x}` in `when:` is not defined (it must come from vars or from the `register` of an EARLIER task)")
    if t.get("register"):
        env.add(t["register"])
    sf = margs(t, "ansible.builtin.set_fact")
    env |= set(sf.keys())

# R4 idempotence of command/shell
for t in tasks:
    if not isinstance(t, dict) or not t.get("_m"):
        continue
    if short(t["_m"]) in ("command", "shell"):
        a = {**margs(t, t["_m"]), **(t.get("args") or {})}
        ok = "changed_when" in t or "creates" in a or "removes" in a
        rep.check(ok, f"task {t.get('name')!r}: a command/shell task must be idempotent (give `creates:`/`removes:` in its args or a `changed_when:`)")

# R5 packages, files, services
for t in tasks:
    if not isinstance(t, dict) or not t.get("_m"):
        continue
    m, a, nm = short(t["_m"]), margs(t, t["_m"]), t.get("name")
    if m in ("apt", "package", "yum", "dnf"):
        rep.check("state" in a, f"task {nm!r}: package tasks need an explicit `state:`")
        if m == "apt":
            rep.check(a.get("update_cache") in (True, "yes") and "cache_valid_time" in a, f"task {nm!r}: apt needs `update_cache: true` together with `cache_valid_time:` (no refresh on every run)")
    if m in ("copy", "template", "file"):
        mode = a.get("mode")
        if m != "file" or a.get("state") != "absent":
            rep.check(isinstance(mode, str) and re.fullmatch(r"0?[0-7]{3,4}", mode), f"task {nm!r}: `mode` must be a quoted string like \"0644\" (an unquoted 0644 is read by YAML as the number 420)")
    if m in ("copy", "template"):
        rep.check(str(a.get("dest", "")).startswith("/"), f"task {nm!r}: `dest` must be an absolute path")
        rep.check("owner" in a and "group" in a, f"task {nm!r}: set `owner` and `group`")
    if m == "template":
        src = str(a.get("src", ""))
        rep.check(src in R["templates"], f"task {nm!r}: template {src!r} does not exist (available: {R['templates']})")
    if m == "service" or m == "systemd":
        rep.check("state" in a or "enabled" in a or "daemon_reload" in a, f"task {nm!r}: service tasks need `state:` and/or `enabled:`")
        if t.get("name") in R.get("enable_tasks", []):
            rep.check(a.get("enabled") in (True, "yes") and a.get("state") == "started", f"task {nm!r}: must be `state: started` and `enabled: true`")
    if m in ("user", "mysql_user", "postgresql_user") or any(re.search(r"password|secret|token", k, re.I) for k in a):
        for k, v in a.items():
            if re.search(r"password|secret|token", k, re.I) and not k.endswith("_file") and k not in ("password_lock", "update_password"):
                rep.check(isinstance(v, str) and re.fullmatch(r"\{\{\s*vault_\w+\s*\}\}", v.strip()), f"task {nm!r}: `{k}` must be a `{{{{ vault_... }}}}` variable, not a literal")
                rep.check(t.get("no_log") is True, f"task {nm!r}: set `no_log: true` on tasks that handle a password")

# R6 loops, become
for t in tasks + handlers:
    if isinstance(t, dict):
        rep.check("with_items" not in t, f"task {t.get('name')!r}: use `loop:` instead of `with_items:`")
priv = R["privileged"]
for t in tasks + handlers:
    if not isinstance(t, dict) or not t.get("_m"):
        continue
    m = short(t["_m"])
    needs = m in ("apt", "package", "service", "systemd", "user") or (m in ("copy", "template", "file") and str(margs(t, t["_m"]).get("dest", margs(t, t["_m"]).get("path", ""))).startswith(tuple(priv)))
    eff = t.get("become", play.get("become", False))
    rep.check(not needs or eff is True, f"task {t.get('name')!r}: needs root (`become: true` on the task or on the play)")

# R7 handlers
hnames = {h.get("name") for h in handlers if isinstance(h, dict)}
notified = set()
for t in tasks:
    if isinstance(t, dict):
        for n in as_list(t.get("notify")):
            notified.add(n)
            rep.check(n in hnames, f"task {t.get('name')!r} notifies {n!r}, but no handler has exactly that name")
for h in hnames:
    rep.check(h in notified or any(h in as_list(x.get("listen")) for x in handlers if isinstance(x, dict)), f"handler {h!r} is never notified")
for need, hs in R["notify"].items():
    t = next((t for t in tasks if isinstance(t, dict) and t.get("name") == need), None)
    if t is not None:
        rep.check(sorted(as_list(t.get("notify"))) == sorted(hs), f"task {need!r} must notify exactly {hs}")
rep.finish()
'''


def play_for(rng, i):
    p = PROJECTS[i % len(PROJECTS)]
    tasks = [copy.deepcopy(t) for t in p["tasks"]]
    return {"name": p["title"], "hosts": p["hosts"], "become": True, "vars": dict(p["vars"]), "tasks": tasks, "handlers": copy.deepcopy(p["handlers"])}, p


def T(name, module, margs_, **kw):
    t = {"name": name, module: margs_}
    t.update(kw)
    return t


def pb(title, hosts, vars_, tasks, handlers, templates, privileged, keep, notify):
    return dict(title=title, hosts=hosts, vars=vars_, tasks=tasks, handlers=handlers, templates=templates, privileged=privileged, keep=keep, notify=notify)


PROJECTS = [
    pb("Configure the lanternbook web tier", "web", {"site_name": "lanternbook", "web_port": 8080, "app_user": "www-data"},
       [T("Install nginx", "ansible.builtin.apt", {"name": "nginx", "state": "present", "update_cache": True, "cache_valid_time": 3600}),
        T("Create the web root", "ansible.builtin.file", {"path": "/var/www/{{ site_name }}", "state": "directory", "owner": "{{ app_user }}", "group": "{{ app_user }}", "mode": "0755"}),
        T("Deploy the site configuration", "ansible.builtin.template", {"src": "site.conf.j2", "dest": "/etc/nginx/conf.d/{{ site_name }}.conf", "owner": "root", "group": "root", "mode": "0644"}, notify="Reload nginx"),
        T("Check the nginx configuration", "ansible.builtin.command", "nginx -t", changed_when=False),
        T("Enable and start nginx", "ansible.builtin.service", {"name": "nginx", "state": "started", "enabled": True})],
       [T("Reload nginx", "ansible.builtin.service", {"name": "nginx", "state": "reloaded"})], ["site.conf.j2", "nginx.conf.j2"], ["/etc", "/var/www"], ["Install nginx", "Deploy the site configuration"], {"Deploy the site configuration": ["Reload nginx"]}),
    pb("Provision the kilnworks database", "db", {"db_name": "bookings", "db_user": "kiln", "vault_db_password": "{{ lookup('env', 'DB_PASS') }}", "pg_data": "/var/lib/postgresql/16/main"},
       [T("Install PostgreSQL", "ansible.builtin.apt", {"name": ["postgresql", "python3-psycopg2"], "state": "present", "update_cache": True, "cache_valid_time": 3600}),
        T("Create the application role", "community.postgresql.postgresql_user", {"name": "{{ db_user }}", "password": "{{ vault_db_password }}", "state": "present"}, become_user="postgres", no_log=True),
        T("Check whether the database exists", "ansible.builtin.command", "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='{{ db_name }}'\"", register="db_exists", changed_when=False, become_user="postgres"),
        T("Create the database", "ansible.builtin.command", "createdb {{ db_name }} -O {{ db_user }}", when="db_exists.stdout != '1'", become_user="postgres", changed_when=True),
        T("Deploy the postgres tuning file", "ansible.builtin.copy", {"src": "tuning.conf", "dest": "/etc/postgresql/16/main/conf.d/tuning.conf", "owner": "postgres", "group": "postgres", "mode": "0640"}, notify="Restart PostgreSQL"),
        T("Enable and start PostgreSQL", "ansible.builtin.service", {"name": "postgresql", "state": "started", "enabled": True})],
       [T("Restart PostgreSQL", "ansible.builtin.service", {"name": "postgresql", "state": "restarted"})], ["pg_hba.conf.j2"], ["/etc", "/var/lib"], ["Install PostgreSQL", "Create the database"], {"Deploy the postgres tuning file": ["Restart PostgreSQL"]}),
    pb("Roll out the quill-print agents", "agents", {"agent_version": "2.4.1", "agent_dir": "/opt/quill-agent", "service_user": "quill"},
       [T("Create the service user", "ansible.builtin.user", {"name": "{{ service_user }}", "system": True, "shell": "/usr/sbin/nologin"}),
        T("Create the agent directory", "ansible.builtin.file", {"path": "{{ agent_dir }}", "state": "directory", "owner": "{{ service_user }}", "group": "{{ service_user }}", "mode": "0750"}),
        T("Unpack the agent", "ansible.builtin.command", "tar -xzf /tmp/agent-{{ agent_version }}.tgz -C {{ agent_dir }}", args={"creates": "{{ agent_dir }}/bin/agent"}),
        T("Install the unit file", "ansible.builtin.template", {"src": "agent.service.j2", "dest": "/etc/systemd/system/quill-agent.service", "owner": "root", "group": "root", "mode": "0644"}, notify=["Reload systemd", "Restart agent"]),
        T("Enable and start the agent", "ansible.builtin.service", {"name": "quill-agent", "state": "started", "enabled": True})],
       [T("Reload systemd", "ansible.builtin.systemd", {"daemon_reload": True}), T("Restart agent", "ansible.builtin.service", {"name": "quill-agent", "state": "restarted"})], ["agent.service.j2"], ["/etc", "/opt"],
       ["Create the service user", "Unpack the agent"], {"Install the unit file": ["Reload systemd", "Restart agent"]}),
    pb("Harden the moth-ledger hosts", "ledger", {"ssh_port": 2222, "allowed_users": ["ops", "audit"], "banner_text": "Authorised use only"},
       [T("Install fail2ban", "ansible.builtin.apt", {"name": "fail2ban", "state": "present", "update_cache": True, "cache_valid_time": 3600}),
        T("Write the sshd drop-in", "ansible.builtin.template", {"src": "sshd_hardening.conf.j2", "dest": "/etc/ssh/sshd_config.d/10-hardening.conf", "owner": "root", "group": "root", "mode": "0600"}, notify="Restart sshd"),
        T("Write the login banner", "ansible.builtin.copy", {"content": "{{ banner_text }}\n", "dest": "/etc/issue.net", "owner": "root", "group": "root", "mode": "0644"}),
        T("Lock the unused accounts", "ansible.builtin.user", {"name": "{{ item }}", "password_lock": True}, loop=["games", "news", "uucp"]),
        T("Enable and start fail2ban", "ansible.builtin.service", {"name": "fail2ban", "state": "started", "enabled": True})],
       [T("Restart sshd", "ansible.builtin.service", {"name": "ssh", "state": "restarted"})], ["sshd_hardening.conf.j2"], ["/etc"], ["Install fail2ban", "Write the sshd drop-in"], {"Write the sshd drop-in": ["Restart sshd"]}),
]


def build(rng, i):
    play, p = play_for(rng, i)
    rules = {"path": "playbook.yml", "hosts": p["hosts"], "keep": p["keep"], "vars": [], "templates": p["templates"], "privileged": p["privileged"], "notify": p["notify"],
             "enable_tasks": [t["name"] for t in p["tasks"] if t["name"].startswith("Enable and start")]}
    return play, {"p": p, "rules": rules}


def render(play, ctx):
    return {"playbook.yml": "---\n" + Y.roundtrip([play])}


def find(play, pred):
    return next(t for t in play["tasks"] if pred(t))


def by_module(play, sub):
    return find(play, lambda t: any(k.endswith("." + sub) or k == sub for k in t))


def d_short(play, ctx, rng):
    for t in play["tasks"] + play["handlers"]:
        for k in list(t):
            if k.startswith("ansible.builtin."):
                t[k.split(".")[-1]] = t.pop(k)
                return {}
    return {}


def d_short_all(play, ctx, rng):
    for t in play["tasks"][:2]:
        for k in list(t):
            if k.startswith("ansible.builtin."):
                t[k.split(".")[-1]] = t.pop(k)
    return {}


def d_no_changed(play, ctx, rng):
    t = next((t for t in play["tasks"] if "ansible.builtin.command" in t and "changed_when" in t), None)
    if t is None:
        t = next(t for t in play["tasks"] if "ansible.builtin.command" in t)
        t.get("ansible.builtin.command")
        t.pop("args", None)
    else:
        del t["changed_when"]
    return {"a": t["name"]}


def d_shell_simple(play, ctx, rng):
    t = next(t for t in play["tasks"] if "ansible.builtin.command" in t)
    t["ansible.builtin.shell"] = t.pop("ansible.builtin.command")
    return {"a": t["name"]}


def d_mode_int(play, ctx, rng):
    t = by_module(play, "template") if any("ansible.builtin.template" in x for x in play["tasks"]) else by_module(play, "copy")
    k = next(k for k in t if k.startswith("ansible.builtin."))
    t[k]["mode"] = Y.Raw("0644", 420)
    return {"a": t["name"]}


def d_undef(play, ctx, rng):
    for t in play["tasks"]:
        for k, v in t.items():
            if k.startswith("ansible.builtin.") and isinstance(v, dict):
                for key in ("path", "dest", "src", "name"):
                    if isinstance(v.get(key), str):
                        m = re.search(r"\{\{\s*(\w+)\s*\}\}", v[key])
                        if m and m.group(1) in play["vars"]:
                            v[key] = v[key].replace(m.group(0), "{{ " + m.group(1)[:-1] + " }}")
                            return {"a": t["name"]}
    raise RuntimeError("no variable to break")


def d_notify_typo(play, ctx, rng):
    t = next(t for t in play["tasks"] if "notify" in t)
    n = t["notify"]
    if isinstance(n, list):
        t["notify"] = [n[0].lower()] + n[1:]
    else:
        t["notify"] = n.replace("Reload", "reload").replace("Restart", "restart")
    return {"a": t["name"]}


def d_dead_handler(play, ctx, rng):
    play["handlers"].append(T("Flush caches", "ansible.builtin.command", "sync", changed_when=False))
    return {}


def d_dup_name(play, ctx, rng):
    play["tasks"][1]["name"] = play["tasks"][0]["name"]
    return {"a": play["tasks"][0]["name"]}


def d_no_name(play, ctx, rng):
    t = play["tasks"][2]
    del t["name"]
    # keep the key order tidy: name first is not needed
    return {}


def d_with_items(play, ctx, rng):
    t = next((t for t in play["tasks"] if "loop" in t), None)
    if t is not None:
        t["with_items"] = t.pop("loop")
        return {"_phr": [0]}
    play["tasks"].append({"name": "Create the data directories", "ansible.builtin.file": {"path": "/var/lib/{{ item }}", "state": "directory", "owner": "root", "group": "root", "mode": "0755"}, "with_items": ["a", "b"]})
    return {"_phr": [0]}


def d_when_braces(play, ctx, rng):
    t = next((t for t in play["tasks"] if "when" in t), None)
    if t is None:
        t = play["tasks"][-1]
        t["when"] = "{{ ansible_os_family == 'Debian' }}"
    else:
        t["when"] = "{{ " + t["when"] + " }}"
    return {"a": t["name"]}


def d_no_become(play, ctx, rng):
    play["become"] = False
    return {}


def d_plain_pw(play, ctx, rng):
    t = next((t for t in play["tasks"] if t.get("no_log")), None)
    if t is not None:
        k = next(k for k in t if k.startswith("community.") or k.startswith("ansible.builtin."))
        t[k]["password"] = "s3cret-pass"
        return {"_phr": [0]}
    play["tasks"].append({"name": "Set the service password", "ansible.builtin.user": {"name": "svc", "password": "hunter2"}})
    return {"_phr": [0]}


def d_no_nolog(play, ctx, rng):
    t = next((t for t in play["tasks"] if t.get("no_log")), None)
    if t is not None:
        del t["no_log"]
        return {"_phr": [0]}
    play["tasks"].append({"name": "Set the service password", "ansible.builtin.user": {"name": "svc", "password": "{{ vault_svc_password }}"}})
    return {"_phr": [0]}


def d_template_src(play, ctx, rng):
    t = next((t for t in play["tasks"] if "ansible.builtin.template" in t), None)
    if t is None:
        play["tasks"].append({"name": "Render extra config", "ansible.builtin.template": {"src": "extra.conf.j2", "dest": "/etc/extra.conf", "owner": "root", "group": "root", "mode": "0644"}})
    else:
        t["ansible.builtin.template"]["src"] = t["ansible.builtin.template"]["src"].replace(".j2", "")
    return {}


def d_apt_cache(play, ctx, rng):
    t = next((t for t in play["tasks"] if "ansible.builtin.apt" in t), None)
    if t is None:
        return {}
    t["ansible.builtin.apt"].pop("update_cache", None)
    t["ansible.builtin.apt"].pop("cache_valid_time", None)
    return {}


def d_svc_state(play, ctx, rng):
    t = next(t for t in play["tasks"] if t["name"].startswith("Enable and start"))
    k = next(k for k in t if k.startswith("ansible.builtin."))
    t[k].pop("enabled", None)
    return {"a": t["name"]}


def d_yaml(play, ctx, rng):
    def post(files):
        t = files["playbook.yml"]
        i = t.index("  tasks:\n") + len("  tasks:\n")
        t = t[:i] + t[i:].replace("\n    - name:", "\n   - name:", 1)
        try:
            Y.load_all(t)
        except ValueError:
            files["playbook.yml"] = t
            return files
        raise RuntimeError("indent defect did not break the YAML")
    return {"_post": post}


DEFECTS = {
    "short-module": (d_short, ["ansible-lint complains: a module is used with its short name", "lint error fqcn[action-core]: use the fully qualified collection name"]),
    "short-modules": (d_short_all, ["ansible-lint: several tasks use short module names instead of FQCN", "the first tasks use `apt:` / `file:` style short names, which our lint rejects"]),
    "no-changed": (d_no_changed, ["the task `{a}` always reports `changed` (a command without `changed_when` or `creates`)", "`{a}` is not idempotent; a second run changes things again"]),
    "shell-simple": (d_shell_simple, ["`{a}` uses `shell` for a plain command", "lint: `{a}` should use `command`, there is no shell feature in it"]),
    "mode-int": (d_mode_int, ["the file mode of `{a}` ends up as 0o644 in decimal (644) on the target... something is off with the YAML", "`{a}` creates the file with a strange mode (we wrote 0644 unquoted)"]),
    "undef-var": (d_undef, ["the run fails: `{a}` references an undefined variable", "`'release_dir' is undefined`-style failure in `{a}`"]),
    "notify-typo": (d_notify_typo, ["the handler of `{a}` never runs", "`{a}` notifies a handler that does not exist (the error is about the name)"]),
    "dead-handler": (d_dead_handler, ["there is a handler that no task ever notifies", "lint: unused handler"]),
    "dup-name": (d_dup_name, ["two tasks are named `{a}`", "duplicate task names break `--start-at-task` and the lint"]),
    "no-name": (d_no_name, ["a task has no name", "lint: unnamed task"]),
    "with-items": (d_with_items, ["a task still uses the deprecated `with_items`", "lint: replace with_items by loop"]),
    "when-braces": (d_when_braces, ["`{a}` has a `when:` wrapped in Jinja braces", "warning: conditional statements should not include jinja2 templating delimiters (`{a}`)"]),
    "no-become": (d_no_become, ["tasks fail with permission denied: the play no longer escalates privileges", "`become` was switched off for the whole play"]),
    "plain-password": (d_plain_pw, ["a password is written in clear text in the playbook", "the secret scan found a literal password"]),
    "no-nolog": (d_no_nolog, ["the password task logs its arguments (no `no_log`)", "a task that sets a password is missing `no_log: true`"]),
    "template-src": (d_template_src, ["a template source does not exist", "`Could not find or access` a template file during the run"]),
    "apt-cache": (d_apt_cache, ["the package index is never refreshed (or is refreshed on every run)", "apt installs fail with 404 on a fresh host; `update_cache` / `cache_valid_time` are missing"]),
    "svc-state": (d_svc_state, ["`{a}` does not enable the service at boot", "after a reboot the service stays down (`{a}`)"]),
    "yaml": (d_yaml, ["`ansible-playbook` stops with a YAML syntax error", "the playbook does not parse after the last edit (indentation)"]),
}


def docs(play, ctx):
    r = ctx["rules"]
    md = dd(f'''
        # Playbook rules

        `playbook.yml` is parsed as YAML (Ruby's Psych: YAML 1.1, so `0644` unquoted is the number 420) and linted mechanically:

        1. One play on `hosts: {r["hosts"]}`; every task and handler has a unique, non-empty `name`; the tasks {", ".join("`" + k + "`" for k in r["keep"])} stay.
        2. Modules use their fully qualified collection name (`ansible.builtin.copy`, not `copy`). `ansible.builtin.shell` is only for commands that need a shell feature (a pipe, a redirect, `&&`); otherwise `ansible.builtin.command`.
        3. Every command/shell task is idempotent: it has `creates:`/`removes:` in its args or a `changed_when:`.
        4. Package tasks have an explicit `state`; `apt` has `update_cache: true` together with `cache_valid_time`. `copy`/`template`/`file` have a `mode` given as a quoted string such as `"0644"`; `copy`/`template` have an absolute `dest`, an `owner` and a `group`;
           `template` sources exist among {r["templates"]}. Service tasks have `state` or `enabled`, and the tasks named `Enable and start ...` have `state: started` and `enabled: true`.
        5. Variables used in `{{ }}` (and in `when:`) are defined: play `vars`, the `register` of an EARLIER task, `set_fact`, `item`, or Ansible facts (`ansible_*`), or the expression has a `default(...)`.
           `when:` never contains `{{ }}`. Use `loop:` instead of `with_items:`.
        6. Passwords, secrets and tokens in module arguments are `{{{{ vault_... }}}}` variables and the task has `no_log: true`.
        7. Privilege: tasks that install packages, manage services or users, or write below {", ".join("`" + p + "`" for p in r["privileged"])} run with `become: true` (on the play or the task).
        8. Handlers: every `notify` names an existing handler exactly; every handler is notified by some task. Required notifications: {"; ".join(f"`{k}` -> " + ", ".join(v) for k, v in r["notify"].items())}.
    ''')
    return {"PLAYBOOK_RULES.md": md, "README.md": f"# {ctx['p']['title']}\n\nOne playbook, `playbook.yml`; the templates and files it refers to exist in the repository (names in `PLAYBOOK_RULES.md`). Rules: `PLAYBOOK_RULES.md`.\n"}


def hidden(play, ctx):
    return {"tests/rules.json": json.dumps(ctx["rules"], indent=1) + "\n"}


def prompt(rng, ctx, texts, vague):
    p = ctx["p"]
    return K.fix_prompt(rng, "playbook.yml", f"playbook \"{p['title']}\"", texts, "PLAYBOOK_RULES.md", vague, [
        f"`playbook.yml` ({p['title']}) fails our ansible-lint policy (`PLAYBOOK_RULES.md`) and some of it fails at run time. Fix everything wrong without dropping tasks or changing what the play configures.",
        f"The playbook `playbook.yml` of '{p['title']}' doesn't satisfy `PLAYBOOK_RULES.md`. Make it compliant and keep all tasks and handlers that are fine.",
    ])


def wrong(play, ctx):
    w1 = copy.deepcopy(play)
    w1["tasks"] = w1["tasks"][1:]
    w2 = copy.deepcopy(play)
    w2["handlers"] = []
    return [render(w1, ctx), render(w2, ctx)]


PLAN = [
    {"keys": ["short-module"], "d": 1, "proj": 0}, {"keys": ["mode-int"], "d": 2, "proj": 0}, {"keys": ["notify-typo"], "d": 2, "proj": 2}, {"keys": ["no-changed", "with-items"], "proj": 1}, {"keys": ["when-braces", "dup-name"], "proj": 3},
    {"keys": ["undef-var", "apt-cache"], "proj": 0}, {"keys": ["plain-password", "no-nolog"], "proj": 1}, {"keys": ["no-become", "template-src"], "proj": 2}, {"keys": ["yaml", "short-modules", "svc-state"], "proj": 3},
    {"keys": ["shell-simple", "dead-handler", "no-name"], "proj": 0}, {"keys": ["mode-int", "notify-typo", "undef-var", "no-changed"], "proj": 2}, {"keys": ["short-modules", "dead-handler", "plain-password", "with-items", "no-become"], "proj": 1, "vague": True, "d": 5},
    {"keys": ["yaml", "template-src", "apt-cache", "mode-int", "svc-state", "when-braces"], "proj": 3, "vague": True, "d": 5}, {"keys": ["dup-name"], "d": 1, "proj": 1}, {"keys": ["no-become"], "d": 2, "proj": 0},
]


def _build(rng, i):
    play, ctx = build(rng, PLAN[i]["proj"])
    return play, ctx


@family("devops-ansible-playbooks", category="devops", lang="text", kind="fix", n=len(PLAN),
        summary="repair Ansible playbooks against a mechanical lint policy: FQCN, idempotent commands, YAML 1.1 octal modes, handlers, undefined variables, vault secrets, become")
def ansible_playbooks(rng, n):
    return K.fix_tasks(rng, n, prefix="ansible", plan=PLAN, build=_build, render=render, defects=DEFECTS, docs=docs, hidden=hidden, check=CHECK_ANSIBLE, prompt=prompt, wrong=wrong, tags=["ansible", "playbook", "yaml"])
