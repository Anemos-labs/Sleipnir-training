"""Extract-function refactors (go): a long pricing function becomes small named steps."""
from __future__ import annotations

import json
import re
from string import Template

from fx import Task, dd, family, langs, merged, run

from . import _kit
from ._kit import clike_lib, indent, prove, tabify
from ._go_domains import GO_DOMAINS, GoDomain, seeds_cases_for

clike = _kit.load_clike()

GO_VERIFY = "go test -count=1 ./... && python3 checks/structure.py"
GO_BEHAVIOUR = "go test -count=1 ./..."
GO_STRUCT = "python3 checks/structure.py"


def _imports(text: str) -> str:
    names = [n for n in ("errors", "fmt", "math", "sort", "strings") if re.search(r"\b" + n + r"\.", text)]
    if not names:
        return ""
    if len(names) == 1:
        return f'import "{names[0]}"\n\n'
    return "import (\n" + "".join(f'\t"{n}"\n' for n in names) + ")\n\n"


def _zero(t: str) -> str:
    return {"int": "0", "string": "\"\"", "bool": "false", "float64": "0"}.get(t, "nil" if t.startswith("[]") or t.startswith("map") else t + "{}")


def _fail_inline(body: str, res: str) -> str:
    return re.sub(r"FAIL\((.*)\)\s*$", lambda m: f"return {res}{{}}, {m.group(1)}", body, flags=re.M)


def _fail_extracted(body: str, outs) -> str:
    zeros = ", ".join(_zero(t) for _, t in outs)
    pre = (zeros + ", ") if outs else ""
    return re.sub(r"FAIL\((.*)\)\s*$", lambda m: f"return {pre}{m.group(1)}", body, flags=re.M)


def _sub(stage, params):
    return Template(stage.body).substitute(params).strip("\n")


def build_start(dom: GoDomain, stages, params, header: str) -> str:
    parts = []
    for s in stages:
        parts.append(f"// {s.title}\n" + _fail_inline(_sub(s, params), dom.res))
    body = "\n\n".join(parts) + "\n\n" + dom.epilogue
    text = (f"// {dom.pkgdoc}\npackage {dom.pkg}\n\n@IMPORTS@{header}\n// {dom.funcdoc}\nfunc {dom.func}({dom.sig_name} {dom.inp}) ({dom.res}, error) {{\n" + indent(body, 4) + "\n}\n")
    text = text.replace("@IMPORTS@", _imports(text))
    return tabify(text)


def _helper(s, params):
    sig_in = ", ".join(f"{n} {t}" for n, t in s.ins)
    if s.fails:
        rets = ", ".join(t for _, t in s.outs) + (", " if s.outs else "") + "error"
        rets = rets if s.outs else "error"
        rets_sig = f"({rets})" if "," in rets else rets
        body = _fail_extracted(_sub(s, params), s.outs)
        tail = "return " + ", ".join(n for n, _ in s.outs) + (", nil" if s.outs else "nil")
    else:
        rets_sig = ", ".join(t for _, t in s.outs)
        rets_sig = f"({rets_sig})" if len(s.outs) > 1 else rets_sig
        body = _sub(s, params)
        tail = ("return " + ", ".join(n for n, _ in s.outs)) if s.outs else ""
    doc = f"// {s.doc}\n"
    return f"{doc}func {s.name}({sig_in}) {rets_sig} {{\n" + indent(body + ("\n" + tail if tail else ""), 4) + "\n}\n"


def build_solution(dom: GoDomain, stages, params, header: str) -> str:
    helpers = [_helper(s, params) for s in stages]
    calls = []
    for s in stages:
        args = ", ".join(n for n, _ in s.ins)
        if s.fails:
            lhs = ", ".join(n for n, _ in s.outs)
            if s.outs:
                calls.append(f"{lhs}, err := {s.name}({args})\nif err != nil {{\n    return {dom.res}{{}}, err\n}}")
            else:
                calls.append(f"if err := {s.name}({args}); err != nil {{\n    return {dom.res}{{}}, err\n}}")
        else:
            outs = ", ".join(n for n, _ in s.outs)
            define = ":=" if not any(n in {x for st in stages[: stages.index(s)] for x, _ in st.outs} for n, _ in s.outs) else "="
            calls.append(f"{outs} {define} {s.name}({args})" if s.outs else f"{s.name}({args})")
    entry = (f"// {dom.funcdoc}\nfunc {dom.func}({dom.sig_name} {dom.inp}) ({dom.res}, error) {{\n" + indent("\n".join(calls) + "\n" + dom.epilogue, 4) + "\n}\n")
    text = f"// {dom.pkgdoc}\npackage {dom.pkg}\n\n@IMPORTS@{header}\n" + "\n".join(helpers) + "\n" + entry
    text = text.replace("@IMPORTS@", _imports(text))
    return tabify(text)


def _go_test(dom: GoDomain, cases, want, sfx: str, mode: str) -> str:
    cj = json.dumps(cases)
    pkg = dom.pkg
    imps = ["encoding/hex", "encoding/json", "fmt", "testing"] if mode == "golden" else ["encoding/json", "reflect", "testing"]
    imp_text = "".join(f'\t"{x}"\n' for x in imps)
    head = (f"package {pkg}_test\n\nimport (\n{imp_text}\n\t\"example.com/{dom.mod}/{pkg}\"\n)\n\n"
            f"const cases{sfx}JSON = `{cj}`\n")
    body = dd(f'''
    type outcome{sfx} struct {{
    \tValue *{pkg}.{dom.res} `json:"value,omitempty"`
    \tErr   string `json:"err,omitempty"`
    }}

    func norm{sfx}(v any) any {{
    \tswitch x := v.(type) {{
    \tcase []any:
    \t\tif len(x) == 0 {{
    \t\t\treturn nil
    \t\t}}
    \t\tfor i := range x {{
    \t\t\tx[i] = norm{sfx}(x[i])
    \t\t}}
    \t\treturn x
    \tcase map[string]any:
    \t\tfor k := range x {{
    \t\t\tx[k] = norm{sfx}(x[k])
    \t\t}}
    \t\treturn x
    \t}}
    \treturn v
    }}

    func outcomes{sfx}() []any {{
    \tvar cases []{pkg}.{dom.inp}
    \tif err := json.Unmarshal([]byte(cases{sfx}JSON), &cases); err != nil {{
    \t\tpanic(err)
    \t}}
    \tvar out []any
    \tfor _, c := range cases {{
    \t\tres, err := {pkg}.{dom.func}(c)
    \t\tvar o outcome{sfx}
    \t\tif err != nil {{
    \t\t\to.Err = err.Error()
    \t\t}} else {{
    \t\t\to.Value = &res
    \t\t}}
    \t\tb, _ := json.Marshal(o)
    \t\tvar v any
    \t\t_ = json.Unmarshal(b, &v)
    \t\tout = append(out, norm{sfx}(v))
    \t}}
    \treturn out
    }}
    ''')
    if mode == "golden":
        tail = dd(f'''
        func TestGolden(t *testing.T) {{
        \tb, _ := json.Marshal(outcomes{sfx}())
        \tfmt.Println("GOLDEN:" + hex.EncodeToString(b))
        }}
        ''')
        return head + "\n" + body + "\n" + tail
    wj = json.dumps(want)
    tail = dd(f'''
    const want{sfx}JSON = `{wj}`

    func Test{sfx}Recorded(t *testing.T) {{
    \tvar want []any
    \tif err := json.Unmarshal([]byte(want{sfx}JSON), &want); err != nil {{
    \t\tt.Fatal(err)
    \t}}
    \tgot := outcomes{sfx}()
    \tif len(got) != len(want) {{
    \t\tt.Fatalf("got %d outcomes, want %d", len(got), len(want))
    \t}}
    \tfor i := range want {{
    \t\tw := norm{sfx}(want[i])
    \t\tif !reflect.DeepEqual(got[i], w) {{
    \t\t\tt.Errorf("case %d: got %v, want %v", i, got[i], w)
    \t\t}}
    \t}}
    }}
    ''')
    return head + "\n" + body + "\n" + tail


def go_golden(files, dom, cases):
    t = _go_test(dom, cases, None, "G", "golden")
    r = run(merged(files, {f"{dom.pkg}/golden_test.go": t}), f"go test -count=1 -run TestGolden -v ./{dom.pkg}/", timeout=120)
    m = re.search(r"GOLDEN:([0-9a-f]+)", r.out)
    if not r.ok or not m:
        raise RuntimeError("go golden run failed:\n" + r.out[-2500:])
    return json.loads(bytes.fromhex(m.group(1)).decode())


PROMPTS_ALL = [
    "`{func}` in `{pkg}/{file}` has grown to {n} lines: it validates, prices and explains in one block, and every rule change means reading all of it. Split it into small "
    "named functions (one per rule or step) so that `{func}` reads as an outline. No function in the package may be longer than {limit} lines (blank lines and comments "
    "don't count). Results and error messages must stay exactly as they are, and `{func}` keeps its signature.",
    "refactor `{func}` ({pkg}/{file}) into steps. limit: {limit} lines per function. same output & same errors for all inputs. tests in the repo must keep passing.",
    "Review comment on the {topic} code: \"`{func}` is {n} lines of interleaved rules. Please extract helpers so that each rule can be read (and changed) on its own; "
    "I'd like no function above {limit} lines.\" Behaviour has to stay identical, including the exact error text and the order of the explanation lines.",
    "We're about to add three more rules to {topic} and `{func}` in `{pkg}/{file}` is already {n} lines long. Do the preparatory refactoring: pull each rule out into its own "
    "unexported function, keep `{func}` as the exported entry point with the same signature, and keep every function under {limit} lines. Same results and errors as before.",
]
PROMPTS_ONE = [
    "In `{pkg}/{file}`, `{func}` mixes several rules. Pull the {title} logic out into an unexported function called `{fname}` and call it from `{func}`. Behaviour must not change.",
    "First step of breaking up `{func}` ({pkg}/{file}): extract the {title} block into a function named `{fname}`. Only that block; everything else stays, results and errors identical.",
]


@family("refactor-go-extract-steps", category="refactor", lang="go", kind="refactor", n=12,
        summary="split a long Go pricing function into small named steps (whole function or one named helper)")
def gen(rng, n):
    modes = ["one"] * 3 + ["all"] * 9
    rng.shuffle(modes)
    doms = list(GO_DOMAINS) * 4
    rng.shuffle(doms)
    for i in range(n):
        dom, mode = doms[i], modes[i]
        params = dom.params(rng)
        subs = {k: v for k, v in params.items() if not k.startswith("_")}
        header = Template(dom.header).substitute(subs)
        opts = [s for s in dom.stages if s.optional]
        k = rng.choice([2, 3]) if mode == "one" else rng.choice([3, 4, 5, len(opts)])
        keep = {s.name for s in rng.sample(opts, min(k, len(opts)))}
        stages = [s for s in dom.stages if not s.optional or s.name in keep]
        start_src = build_start(dom, stages, subs, header)
        sol_src = build_solution(dom, stages, subs, header)
        rel = f"{dom.pkg}/{dom.file}"
        cases = (seeds_cases_for(params) if dom.key == "seeds" else dom.cases)(rng, 30)
        base = {"go.mod": langs.go_mod(dom.mod), rel: start_src}
        want = go_golden(base, dom, cases)
        okc = [j for j, w in enumerate(want) if "value" in w]
        errc = [j for j, w in enumerate(want) if "err" in w]
        vis_idx = okc[:3] + errc[:1]
        vis = _go_test(dom, [cases[j] for j in vis_idx], [want[j] for j in vis_idx], "Ex", "test")
        hid = _go_test(dom, cases, want, "Rec", "test")
        entry_fns = clike.functions_text(start_src, "go", rel)
        entry = [f for f in entry_fns if f.name == dom.func][0]
        n_lines = entry.loc
        sol_fns = clike.functions_text(sol_src, "go", rel)
        tag = ["extract-function"]
        if mode == "all":
            limit = max(14, -(-(max(f.loc for f in sol_fns) + 2) // 5) * 5)
            if n_lines <= limit + 6:
                limit = max(12, max(f.loc for f in sol_fns) + 1)
            if n_lines <= limit + 5:
                raise RuntimeError(f"{dom.key}: entry {n_lines} lines vs limit {limit}")
            struct = dd(f'''
            import clike as C

            FILES = C.files([".go"], dirs=[{json.dumps(dom.pkg)}])
            LIMIT = {limit}
            problems = []
            fns = C.all_functions(FILES, "go")
            if {json.dumps(dom.func)} not in [f.name for f in fns]:
                problems.append("the exported entry point {dom.func} is missing")
            for f in fns:
                if f.loc > LIMIT:
                    problems.append("%s:%s has %d lines (limit %d)" % (f.file, f.name, f.loc, LIMIT))
            if len(fns) < {max(3, len(stages) - 1)}:
                problems.append("expected the logic to be spread over at least {max(3, len(stages) - 1)} functions, found %d" % len(fns))
            C.report(problems)
            ''')
            prompt = rng.choice(PROMPTS_ALL).format(func=dom.func, pkg=dom.pkg, file=dom.file, n=n_lines, limit=limit, topic=dom.topic)
            d = 2 if len(stages) <= 4 else 3 if len(stages) <= 6 else 4
            tag.append("split-long-function")
        else:
            st = rng.choice([s for s in stages if not s.fails])
            stage_loc = len([ln for ln in _sub(st, subs).splitlines() if ln.strip()])
            struct = dd(f'''
            import re

            import clike as C

            FILES = C.files([".go"], dirs=[{json.dumps(dom.pkg)}])
            NAME = {json.dumps(st.name)}
            ENTRY = {json.dumps(dom.func)}
            START_LINES = {n_lines}
            STAGE_LINES = {stage_loc}
            problems = []
            fns = C.all_functions(FILES, "go")
            names = [f.name for f in fns]
            if NAME not in names:
                problems.append("expected a function called " + NAME)
            entry = [f for f in fns if f.name == ENTRY]
            if not entry:
                problems.append("entry point " + ENTRY + " is missing")
            else:
                if not re.search(r"\\b" + NAME + r"\\(", entry[0].body):
                    problems.append(ENTRY + " should call " + NAME)
                if entry[0].loc > START_LINES - max(2, STAGE_LINES - 3):
                    problems.append("%s still has %d lines; the extracted logic should have left it" % (ENTRY, entry[0].loc))
            C.report(problems)
            ''')
            prompt = rng.choice(PROMPTS_ONE).format(func=dom.func, pkg=dom.pkg, file=dom.file, title=st.title, fname=st.name)
            d = 1 if stage_loc <= 6 else 2
            tag.append("single-extraction")
        start = {**base, f"{dom.pkg}/example_test.go": vis}
        hidden = {f"{dom.pkg}/behaviour_test.go": hid, "checks/structure.py": struct, **clike_lib()}
        solution = {rel: sol_src}
        prove(f"{dom.key}-{mode}", start, hidden, solution, GO_BEHAVIOUR, GO_STRUCT, GO_VERIFY)
        yield Task(slug=f"{i + 1:02d}-{dom.key}-{mode}", prompt=prompt, difficulty=d, start=start, hidden=hidden, solution=solution, verify=GO_VERIFY,
                   tags=tag, notes={"domain": dom.key, "mode": mode, "stages": [s.name for s in stages]})
