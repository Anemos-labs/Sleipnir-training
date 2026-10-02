"""Replace if/else and switch ladders on a type code with polymorphism or lookup (java)."""
from __future__ import annotations

import json
import re
from string import Template

from fx import Task, dd, family, langs, merged, run

from . import _kit
from ._kit import clike_lib, indent, prove

JAVA_VERIFY = "rm -rf build && mkdir -p build && javac -d build $(find . -name '*.java') && java -cp build TestMain && python3 checks/structure.py"
JAVA_BEHAVIOUR = "rm -rf build && mkdir -p build && javac -d build $(find . -name '*.java') && java -cp build TestMain"
JAVA_STRUCT = "python3 checks/structure.py"

# ----------------------------------------------------------------------------------------------------------------
# domains
# ----------------------------------------------------------------------------------------------------------------
DOMAINS = [
    dict(key="dues", pkg="harbour", cls="DuesCalculator", method="dues", iface="VesselClass", topic="harbour dues",
         params="int tonnage, int days", args_decl="String vesselClass, int tonnage, int days", kind_arg="vesselClass", unit_arg="tonnage",
         result="int", err="unknown vessel class: ", names=["ferry", "trawler", "yacht", "tanker", "sloop", "tug", "barge", "cruiser"],
         post="cents * days", pre='if (tonnage <= 0 || days <= 0) {\n    throw new IllegalArgumentException("tonnage and days must be positive");\n}',
         call_args=lambda r: [("%s" % json.dumps(r.choice([1, 40, 250, 1200, 9000, 0]))), json.dumps(r.choice([1, 2, 3, 5, 14, 0]))],
         what="vessel class", entry_doc="Dues in cents for a stay."),
    dict(key="refund", pkg="ticketing", cls="RefundPolicy", method="refund", iface="TicketRule", topic="ticket refunds",
         params="int priceCents, int daysBefore", args_decl="String kind, int priceCents, int daysBefore", kind_arg="kind", unit_arg="priceCents",
         result="int", err="no refund rule for ", names=["standard", "flex", "student", "group", "season", "promo", "vip", "voucher"],
         post="Math.max(0, cents)", pre='if (priceCents < 0 || daysBefore < 0) {\n    throw new IllegalArgumentException("negative input");\n}',
         call_args=lambda r: [json.dumps(r.choice([0, 500, 2000, 4500, 12000])), json.dumps(r.choice([0, 1, 3, 7, 14, 30, 90]))],
         what="ticket kind", entry_doc="Refund in cents for a cancelled ticket."),
]

BODY_FORMS = [
    lambda r, u, d: f"cents = {r.randrange(1, 40) * 25} + {r.randrange(1, 9)} * {u};",
    lambda r, u, d: f"cents = Math.max({r.randrange(1, 30) * 50}, {r.randrange(1, 9)} * {u} / {r.choice([2, 5, 10])});",
    lambda r, u, d: f"int base = {r.randrange(2, 40) * 25};\nif ({u} > {r.randrange(5, 40) * 25}) {{\n    base += {r.randrange(1, 5)} * ({u} / {r.choice([10, 25, 50])});\n}}\ncents = base;",
    lambda r, u, d: f"cents = {u} * {r.randrange(1, 9)} / {r.choice([3, 4, 5, 8])};\nif ({d} > {r.randrange(2, 8)}) {{\n    cents = cents - cents / {r.choice([5, 10])};\n}}",
    lambda r, u, d: f"cents = {r.randrange(1, 20) * 50} + {u} / {r.choice([4, 10, 20])} + {d} * {r.randrange(1, 6) * 5};",
]


def _forms(rng, dom, k):
    names = rng.sample(dom["names"], k)
    unit = dom["unit_arg"]
    other = "days" if dom["key"] == "dues" else "daysBefore"
    return [(n, rng.choice(BODY_FORMS)(rng, unit, other)) for n in names]


def _cap(s):
    return s[0].upper() + s[1:]


def _start_src(dom, cases, mode_switch):
    pkg, cls = dom["pkg"], dom["cls"]
    k = dom["kind_arg"]
    lines = [f"package {pkg};", "", f"/** {dom['entry_doc']} */", f"public class {cls} {{", f"    public int {dom['method']}({dom['args_decl']}) {{"]
    lines += ["        " + ln for ln in dom["pre"].splitlines()]
    lines.append("        int cents;")
    if mode_switch:
        lines.append(f"        switch ({k}) {{")
        for name, body in cases:
            lines.append(f'            case "{name}":')
            lines += ["                " + ln for ln in body.splitlines()]
            lines.append("                break;")
        lines += ["            default:", f'                throw new IllegalArgumentException("{dom["err"]}" + {k});', "        }"]
    else:
        for i, (name, body) in enumerate(cases):
            lines.append(f'        {"if" if i == 0 else "} else if"} ({k}.equals("{name}")) {{')
            lines += ["            " + ln for ln in body.splitlines()]
        lines += ["        } else {", f'            throw new IllegalArgumentException("{dom["err"]}" + {k});', "        }"]
    lines += [f"        return {dom['post']};", "    }", "}", ""]
    return "\n".join(lines)


def _solution_classes(dom, cases):
    pkg, cls, iface = dom["pkg"], dom["cls"], dom["iface"]
    unit = dom["unit_arg"]
    other = "days" if dom["key"] == "dues" else "daysBefore"
    files = {f"src/{pkg}/{iface}.java": f"package {pkg};\n\n/** One pricing rule; the calculator picks the rule by name. */\ninterface {iface} {{\n    int cents(int {unit}, int {other});\n}}\n"}
    for name, body in cases:
        c = _cap(name)
        b = "\n".join("        " + ln for ln in body.splitlines())
        files[f"src/{pkg}/{c}{iface}.java"] = (f"package {pkg};\n\nfinal class {c}{iface} implements {iface} {{\n    @Override\n    public int cents(int {unit}, int {other}) {{\n"
                                              f"        int cents;\n{b}\n        return cents;\n    }}\n}}\n")
    reg = "\n".join(f'        rules.put("{n}", new {_cap(n)}{iface}());' for n, _ in cases)
    pre = "\n".join("        " + ln for ln in dom["pre"].splitlines())
    k = dom["kind_arg"]
    files[f"src/{pkg}/{cls}.java"] = (
        f"package {pkg};\n\nimport java.util.HashMap;\nimport java.util.Map;\n\n/** {dom['entry_doc']} */\npublic class {cls} {{\n"
        f"    private final Map<String, {iface}> rules = new HashMap<>();\n\n    public {cls}() {{\n{reg}\n    }}\n\n"
        f"    public int {dom['method']}({dom['args_decl']}) {{\n{pre}\n        {iface} rule = rules.get({k});\n        if (rule == null) {{\n"
        f"            throw new IllegalArgumentException(\"{dom['err']}\" + {k});\n        }}\n        int cents = rule.cents({unit}, {'days' if dom['key'] == 'dues' else 'daysBefore'});\n"
        f"        return {dom['post']};\n    }}\n}}\n")
    return files


def _harness(dom, calls, sfx="", want=None, golden=False):
    pkg, cls = dom["pkg"], dom["cls"]
    rows = ",\n".join("        {" + ", ".join(json.dumps(a) if isinstance(a, str) else str(a) for a in c) + "}" for c in calls)
    cast = ", ".join(f"({'String' if i == 0 else 'Integer'}) c[{i}]" for i in range(len(calls[0])))
    common = (f"import {pkg}.{cls};\n\npublic class {{CLASS}} {{\n    static final Object[][] CASES = {{\n{rows}\n    }};\n\n"
              f"    static String outcome(Object[] c) {{\n        {cls} calc = new {cls}();\n        try {{\n            return String.valueOf(calc.{dom['method']}({cast}));\n"
              f"        }} catch (RuntimeException e) {{\n            return \"!\" + e.getClass().getSimpleName() + \": \" + e.getMessage();\n        }}\n    }}\n")
    if golden:
        return common.replace("{CLASS}", "GoldenMain") + ("\n    public static void main(String[] args) {\n        for (int i = 0; i < CASES.length; i++) {\n"
                                                         "            System.out.println(\"GOLDEN|\" + i + \"|\" + outcome(CASES[i]));\n        }\n    }\n}\n")
    wl = ",\n".join("        " + json.dumps(w) for w in want)
    return common.replace("{CLASS}", sfx) + (f"\n    static final String[] WANT = {{\n{wl}\n    }};\n\n    static int run() {{\n        int failures = 0;\n"
                                             "        for (int i = 0; i < CASES.length; i++) {\n            String got = outcome(CASES[i]);\n            if (!got.equals(WANT[i])) {\n"
                                             "                System.out.println(\"case \" + i + \": got \" + got + \", want \" + WANT[i]);\n                failures++;\n            }\n        }\n"
                                             "        return failures;\n    }\n}\n")


def java_golden(files, dom, calls):
    t = _harness(dom, calls, golden=True)
    r = run(merged(files, {"GoldenMain.java": t}), "mkdir -p build && javac -d build $(find . -name '*.java') && java -cp build GoldenMain", timeout=120)
    lines = [ln for ln in r.out.splitlines() if ln.startswith("GOLDEN|")]
    if not r.ok or len(lines) != len(calls):
        raise RuntimeError("java golden run failed:\n" + r.out[-2500:])
    return [ln.split("|", 2)[2] for ln in lines]


TESTMAIN = '''public class TestMain {
    public static void main(String[] args) {
        int failures = ExampleTest.run() + BehaviourTest.run();
        if (failures > 0) {
            System.out.println(failures + " failing checks");
            System.exit(1);
        }
        System.out.println("all checks passed");
    }
}
'''

PROMPTS_TABLE = [
    "`{cls}.{method}` in `{pkg}/{cls}.java` decides the price with a {kind} ladder over the {what}: {k} branches, each with its own formula. Every new {what} adds another "
    "branch to a method nobody wants to touch. Refactor it so the rule for each {what} is separate from the dispatching: use polymorphism (an interface with one class per {what}) "
    "or a lookup of behaviours, your choice. `{method}` keeps its signature, results and exception messages, and no `if/else if` chain or `switch` over the {what} may remain "
    "(at most {bound} such branches in the whole project).",
    "Replace the {kind} ladder in `{cls}.{method}` ({pkg}/{cls}.java) with something extensible. The {k} {what}s should each live in their own unit; the method only looks the right "
    "one up. Behaviour, including the `IllegalArgumentException` messages, must stay identical. Leave at most {bound} `else if`/`case` branches in the sources.",
    "refactor: {kind} on {what} in `{pkg}/{cls}.java` -> strategy per {what} (interface + one class each is fine, a map of lambdas is fine too). same results, same exceptions. "
    "no ladder left (max {bound} else-if/case branches in the project).",
]
PROMPTS_CLASSES = [
    "`{cls}.{method}` in `{pkg}/{cls}.java` is a {kind} ladder over the {what}. Introduce an interface `{iface}` with one implementing class per {what} (so {k} classes, "
    "named like `{ex}{iface}`) and have `{cls}` look the right one up. The signature of `{method}`, its results and its exception messages stay the same. "
    "No `if/else if` chain or `switch` over the {what} may remain (at most {bound} such branches in the project).",
    "Strategy pattern please: in `{pkg}/{cls}.java` turn the {k} branches of the {kind} ladder in `{method}` into classes implementing a common interface `{iface}` "
    "(one file per class, e.g. `{ex}{iface}.java`), and make `{cls}` dispatch to them. Same behaviour, same error messages, no ladder left.",
]


@family("refactor-java-strategy", category="refactor", lang="java", kind="refactor", n=10,
        summary="if-else/switch ladders over a type code become strategy classes or a lookup of behaviours")
def gen(rng, n):
    order = list(DOMAINS) * 6
    rng.shuffle(order)
    for i in range(n):
        dom = order[i]
        k = rng.choice([4, 5, 6, 7])
        sw = rng.random() < 0.4
        cases = _forms(rng, dom, k)
        cls, pkg = dom["cls"], dom["pkg"]
        start_src = _start_src(dom, cases, sw)
        sol = _solution_classes(dom, cases)
        base = {f"src/{pkg}/{cls}.java": start_src}
        calls = []
        for j in range(26):
            kind = rng.choice([n for n, _ in cases] + ([f"nothing{j}"] if j % 9 == 8 else []))
            calls.append([kind] + [int(x) for x in dom["call_args"](rng)])
        want = java_golden(base, dom, calls)
        vis_idx = [j for j, w in enumerate(want) if not w.startswith("!")][:3] + [j for j, w in enumerate(want) if w.startswith("!")][:1]
        vis = _harness(dom, [calls[j] for j in vis_idx], "ExampleTest", [want[j] for j in vis_idx])
        hid = _harness(dom, calls, "BehaviourTest", want)
        bound = 1
        struct = dd(f'''
        import clike as C

        FILES = C.files([".java"], dirs=["src"])
        problems = []
        n = C.count(FILES, r"\\belse\\s+if\\b|\\bcase\\b\\s+[^:;\\n]+:|\\bswitch\\s*\\(", "java")
        if n > {bound}:
            problems.append("%d else-if / case / switch branches remain in the sources (at most {bound} expected)" % n)
        C.report(problems)
        ''')
        if rng.random() < 0.5:
            prompt_t = rng.choice(PROMPTS_CLASSES)
            struct = struct.replace("C.report(problems)", dd(f'''
            text = "".join(C.clean(C.read(f), "java") for f in FILES)
            impls = len(__import__("re").findall(r"\\bimplements\\s+{dom['iface']}\\b", text))
            if impls < {k}:
                problems.append("expected {k} classes implementing {dom['iface']}, found %d" % impls)
            C.report(problems)
            '''))
            d = 3
        else:
            prompt_t = rng.choice(PROMPTS_TABLE)
            d = 3 if k <= 5 else 4
        if sw and d == 3 and rng.random() < 0.3:
            d = 2
        start = {**base, "tests/ExampleTest.java": vis}
        hidden = {"tests/BehaviourTest.java": hid, "tests/TestMain.java": TESTMAIN, "checks/structure.py": struct, **clike_lib()}
        solution = sol
        prove(dom["key"], start, hidden, solution, JAVA_BEHAVIOUR, JAVA_STRUCT, JAVA_VERIFY)
        prompt = rng.choice([prompt_t]).format(cls=cls, method=dom["method"], pkg=pkg, kind="`switch`" if sw else "`if/else if`", what=dom["what"], k=k, bound=bound,
                                               iface=dom["iface"], ex=_cap(cases[0][0]))
        yield Task(slug=f"{i + 1:02d}-{dom['key']}-{k}", prompt=prompt, difficulty=d, start=start, hidden=hidden, solution=solution, verify=JAVA_VERIFY,
                   tags=["strategy", "polymorphism", "conditional-ladder"], notes={"domain": dom["key"], "branches": k, "switch": sw})
