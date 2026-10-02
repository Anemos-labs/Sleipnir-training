"""Feature-slice composition: one small application, many "add this feature" tasks.

An ``App`` is a set of file *templates* (source, README, build files, visible tests, hidden tests). Templates contain
marker lines that a ``Slice`` fills in:

    @@slot NAME      lines of every active slice that targets NAME, tight (no blank line between fragments)
    @@blocks NAME    same, fragments separated by one blank line
    @@uniq NAME      same as slot, but identical lines are emitted once (imports)
    @@default NAME   the text up to ``@@end`` is the default; an active slice may *replace* it (API evolution)
    ...
    @@end

A marker line is replaced by the fragments re-indented to the marker's indentation; with no fragments it vanishes
(or, for ``default``, the default text stays). A slice's ``code`` maps ``"path::NAME"`` to a fragment (``T::`` and
``V::`` alias the first hidden / visible test file, ``R::`` the README). ``tests`` / ``vtests`` go to the ``tests`` slot of
the hidden / visible test file. ``cross[other_id]`` holds extra fragments, files, tests and requirements that only exist when
*both* slices are implemented, so slices can interact (an export that must include the audit trail, ...).

``compose_tasks`` plans tasks: each asks for one to three slices that are missing from a start repository built from a
random subset of the other slices (closed under ``needs``). The hidden tests are the tests of everything implemented
(regressions) plus the requested slices; the request text is rendered in one of several voices from the slices'
``pitch`` / ``reqs`` / ``example`` (the ``reqs`` are the complete contract, so every voice is fair).
"""
from __future__ import annotations

import random
import re
import textwrap
from dataclasses import dataclass, field

from fx import Task, langs
from fx.core import Family, register

_MARK = re.compile(r"^([ \t]*)@@(slot|blocks|uniq|default) ([A-Za-z0-9_.-]+)[ \t]*$")
_END = re.compile(r"^[ \t]*@@end[ \t]*$")


@dataclass
class Slice:
    id: str
    title: str
    d: int = 2
    needs: tuple = ()
    conflicts: tuple = ()
    pitch: tuple = ()
    reqs: tuple = ()
    example: str = ""
    code: dict = field(default_factory=dict)
    files: dict = field(default_factory=dict)
    readme: str = ""
    tests: str = ""
    vtests: str = ""
    cross: dict = field(default_factory=dict)


@dataclass
class App:
    name: str  # repository / package name, as it appears in prompts
    lang: str
    title: str  # what people call it: "the seed library tool"
    base: dict  # path -> template (sources, README.md with @@blocks features, build files)
    visible: dict  # path -> template (visible tests: `@@blocks tests` gets vtests)
    hidden: dict  # path -> template (hidden tests: `@@blocks tests` gets tests)
    role: str = "a user"  # "a volunteer at the seed swap"
    key: str = "APP"  # ticket key
    verify: str = ""
    timeout_s: int = 120

    def __post_init__(self):
        self.verify = self.verify or langs.VERIFY[self.lang]


# --------------------------------------------------------------------------------------------- rendering


def fmt(text: str, **kw) -> str:
    """Replace ``__KEY__`` tokens (safe in every language, unlike str.format with code braces)."""
    for k, v in kw.items():
        text = text.replace(f"__{k}__", str(v))
    return text


def _reindent(frag: str, indent: str) -> list[str]:
    text = textwrap.dedent(frag).strip("\n")
    return [(indent + ln) if ln.strip() else "" for ln in text.split("\n")]


def _expand_once(template: str, path: str, frags: dict) -> str:
    lines = template.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        m = _MARK.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        indent, kind, name = m.groups()
        fr = frags.get(f"{path}::{name}", [])
        if kind == "default":
            j = i + 1
            while j < len(lines) and not _END.match(lines[j]):
                j += 1
            if j >= len(lines):
                raise ValueError(f"{path}: @@default {name} without @@end")
            if fr:
                out.extend(_reindent(fr[-1], indent))
            else:
                out.extend(lines[i + 1 : j])
            i = j + 1
            continue
        if fr:
            if kind == "blocks":
                for k, f in enumerate(fr):
                    if k:
                        out.append("")
                    out.extend(_reindent(f, indent))
            else:
                seen = set()
                for f in fr:
                    for ln in _reindent(f, indent):
                        if kind == "uniq":
                            if ln in seen:
                                continue
                            seen.add(ln)
                        out.append(ln)
        i += 1
    return "\n".join(out)


def expand(template: str, path: str, frags: dict) -> str:
    """Expand markers; fragments may themselves contain markers (other slices' cross fragments fill them)."""
    text = template
    for _ in range(4):
        text = _expand_once(text, path, frags)
        if not any(_MARK.match(ln) for ln in text.split("\n")):
            break
    else:
        raise ValueError(f"{path}: markers nest too deeply")
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    text = re.sub(r"\n\n\n(?=[ \t]+\S)", "\n\n", text)  # one blank line between indented blocks
    return text.rstrip("\n") + "\n" if text.strip() else text


def _alias(app: App, key: str) -> str:
    path, name = key.split("::")
    if path == "T":
        path = sorted(app.hidden)[0]
    elif path == "V":
        path = sorted(app.visible)[0]
    elif path == "R":
        path = "README.md"
    return f"{path}::{name}"


def _collect(app: App, ordered: list, active: set, kind: str) -> tuple[dict, dict]:
    """Fragments and extra files of the active slices. ``kind``: 'v' puts vtests into the visible test slot,
    't' puts tests into the hidden slot."""
    frags: dict = {}
    files: dict = {}
    vpath = sorted(app.visible)[0]
    hpath = sorted(app.hidden)[0]

    def add_all(s_or_x, tests_attr_owner=None):
        for k, v in (s_or_x.get("code") or {}).items():
            frags.setdefault(_alias(app, k), []).append(v)
        for p, t in (s_or_x.get("files") or {}).items():
            files[p] = t
        if s_or_x.get("readme"):
            frags.setdefault("README.md::features", []).append(s_or_x["readme"])
        if kind == "v" and s_or_x.get("vtests"):
            frags.setdefault(f"{vpath}::tests", []).append(s_or_x["vtests"])
        if kind == "t" and s_or_x.get("tests"):
            frags.setdefault(f"{hpath}::tests", []).append(s_or_x["tests"])

    def asdict(s):
        return {"code": s.code, "files": s.files, "readme": s.readme, "tests": s.tests, "vtests": s.vtests}

    for s in ordered:
        if s.id in active:
            add_all(asdict(s))
    for s in ordered:  # cross fragments last, so they can override a default replaced by the plain slice
        if s.id in active:
            for other, x in s.cross.items():
                if other in active:
                    add_all(x)
    return frags, files


def _render_tree(templates: dict, frags: dict) -> dict:
    return {p: expand(t, p, frags) for p, t in templates.items()}


# --------------------------------------------------------------------------------------------- planning


def _closure_ok(by_id: dict, present: set, targets: set) -> set:
    """Make ``present`` closed under ``needs`` (pulling in what is needed, dropping what needs a target) and free of
    conflicts with the targets."""
    present = set(present) - set(targets)
    for _ in range(12):
        changed = False
        everything = present | set(targets)
        for sid in sorted(present):
            s = by_id[sid]
            if any(c in everything for c in s.conflicts) or any(sid in by_id[o].conflicts for o in everything if o != sid):
                present.discard(sid)
                changed = True
                break
            if any(nd in targets for nd in s.needs):
                present.discard(sid)
                changed = True
                break
            miss = [nd for nd in s.needs if nd not in present]
            if miss:
                present.update(miss)
                changed = True
        for t in targets:
            for nd in by_id[t].needs:
                if nd not in targets and nd not in present:
                    present.add(nd)
                    changed = True
        if not changed:
            break
    return present


def _plan(rng: random.Random, slices: list, n: int) -> list[tuple[list[str], set]]:
    by_id = {s.id: s for s in slices}
    ids = [s.id for s in slices]
    plans: list[tuple[list[str], set]] = []
    order: list[str] = []
    while len(order) < n:
        perm = ids[:]
        rng.shuffle(perm)
        order += perm
    bundle_slots = {i for i in range(n) if i % 4 == 3}
    for i in range(n):
        primary = order[i]
        targets = [primary]
        if i in bundle_slots:
            k = rng.choice([2, 2, 3]) if n >= 8 else 2
            cands = [x for x in ids if x != primary and not set(by_id[x].conflicts) & {primary} and primary not in by_id[x].conflicts]
            rng.shuffle(cands)
            for c in cands:
                if len(targets) >= k:
                    break
                if any(c in by_id[t].conflicts or t in by_id[c].conflicts for t in targets):
                    continue
                targets.append(c)
        tset = set(targets)
        # a target's dependency on another target must come with the dependency ordered first; fine by slice order
        p = rng.choice([0.0, 0.3, 0.5, 0.7, 0.9, 1.0]) if i % 5 else rng.choice([0.0, 0.15])
        present = {x for x in ids if x not in tset and rng.random() < p}
        present = _closure_ok(by_id, present, tset)
        targets.sort(key=ids.index)
        plans.append((targets, present))
    return plans


def difficulty(slices_by_id: dict, targets: list, present: set) -> int:
    ts = [slices_by_id[t] for t in targets]
    final = set(targets) | present
    cross = 0
    for sid in final:
        for other in slices_by_id[sid].cross:
            if other in final and (sid in targets or other in targets):
                cross += 1
    score = max(s.d for s in ts) + 0.4 * (len(ts) - 1) + 0.25 * cross + (0.3 if len(present) >= 7 else 0.0)
    if len(ts) == 1 and ts[0].d == 1:
        score = min(score, 1.45)  # a lone trivial request stays trivial, however large the repository
    return max(1, min(5, int(score + 0.5)))


# --------------------------------------------------------------------------------------------- voices

_PEOPLE = ["Marta", "Dev", "Ines", "Tomasz", "Priya", "Jonas", "Amara", "Luka", "Wen", "Noor", "Hana", "Rafi", "Sunniva", "Teodor"]
_PRIORITY = ["Low", "Medium", "Medium", "High"]
_CLOSERS = [
    "Keep the existing tests passing.",
    "Existing behaviour must not change for callers that do not use this.",
    "Please update the README as well.",
    "No new dependencies, please.",
    "Match the style of the surrounding code.",
    "",
    "",
]


def _join_titles(ts: list) -> str:
    names = [t.title for t in ts]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _lc(s: str) -> str:
    return s[:1].lower() + s[1:] if s and not s[:2].isupper() else s


def _items(rng, targets: list, reqs_extra: dict, with_pitch: bool = True) -> list:
    out = []
    for s in targets:
        pitch = rng.choice(list(s.pitch)) if s.pitch and with_pitch else ""
        out.append((s, pitch, list(s.reqs) + list(reqs_extra.get(s.id, []))))
    return out


def _fence(example: str) -> str:
    return "```\n" + example.strip("\n") + "\n```" if example else ""


def _v_ticket(rng, app, items, closer, detail):
    n = rng.randint(100, 960)
    head = f"{app.key}-{n}  {_join_titles([i[0] for i in items])}\nType: Feature | Priority: {rng.choice(_PRIORITY)} | Component: {app.name}\n"
    body = []
    for s, pitch, reqs in items:
        sec = []
        if len(items) > 1:
            sec.append(f"{s.title}")
        if pitch:
            sec.append(pitch)
        sec.append("Acceptance criteria:\n" + "\n".join(f"* {r}" for r in reqs))
        if detail and s.example:
            sec.append("Example:\n" + _fence(s.example))
        body.append("\n\n".join(sec))
    return head + "\n" + "\n\n".join(body) + ("\n\n" + closer if closer else "")


def _v_chat(rng, app, items, closer, detail):
    opener = rng.choice(["Hey, got a small one for", "Could you pick up a change in", "Hi! Next thing for", "Quick request for", "Hey, I need something added to"])
    parts = []
    for s, pitch, reqs in items:
        t = ((pitch + " ") if pitch else "") + "What I need: " + " ".join(reqs)
        if len(items) > 1:
            t = f"({s.title}) " + t
        if detail and s.example:
            t += "\nFor example:\n" + _fence(s.example)
        parts.append(t)
    return f"{opener} {app.name}.\n\n" + "\n\n".join(parts) + ("\n\n" + closer if closer else "")


def _v_design(rng, app, items, closer, detail):
    title = _join_titles([i[0] for i in items])
    out = [f"# Design note: {title}", f"Status: approved | Owner: {rng.choice(_PEOPLE)}", ""]
    for s, pitch, reqs in items:
        if len(items) > 1:
            out.append(f"## {s.title}")
        if pitch:
            out += ["### Motivation" if len(items) == 1 else "Motivation:", pitch, ""]
        out.append("### Behaviour" if len(items) == 1 else "Behaviour:")
        out += [f"{k + 1}. {r}" for k, r in enumerate(reqs)]
        out.append("")
        if detail and s.example:
            out += ["### Example" if len(items) == 1 else "Example:", _fence(s.example), ""]
    out += ["## Out of scope", "Anything not described above; everything that works today keeps working as it does." + (" " + closer if closer else "")]
    return "\n".join(out)


def _v_bullets(rng, app, items, closer, detail):
    head = rng.choice([f"Changes wanted in {app.name}:", f"Next steps for {app.name}:", f"{app.name} backlog item, ready to build:"])
    out = [head, ""]
    for s, pitch, reqs in items:
        out.append(f"- {s.title}" + (f": {pitch}" if pitch else ""))
        out += [f"  - {r}" for r in reqs]
        if detail and s.example:
            out.append("  - example:")
            out += ["    " + ln for ln in _fence(s.example).split("\n")]
    if closer:
        out += ["", closer]
    return "\n".join(out)


def _v_email(rng, app, items, closer, detail):
    me = rng.choice(_PEOPLE)
    subj = _join_titles([i[0] for i in items])
    out = [f"Subject: {subj}", "", "Hi,", ""]
    for s, pitch, reqs in items:
        if pitch:
            out.append(pitch + (" Could you build this into " + app.name + "?" if s is items[0][0] else ""))
        out.append("What we agreed it should do:" if len(items) == 1 else f"{s.title}, what we agreed it should do:")
        out += [f" * {r}" for r in reqs]
        if detail and s.example:
            out += ["", "An example:", _fence(s.example)]
        out.append("")
    if closer:
        out += [closer, ""]
    out += ["Thanks,", me]
    return "\n".join(out)


def _v_story(rng, app, items, closer, detail):
    out = []
    for s, pitch, reqs in items:
        out.append(f"As {app.role}, I need {_lc(s.title)} in {app.name}." + (f" {pitch}" if pitch else ""))
        out.append("Done when:")
        out += [f"- {r}" for r in reqs]
        if detail and s.example:
            out += ["", _fence(s.example)]
        out.append("")
    if closer:
        out.append(closer)
    return "\n".join(out).strip()


def _v_notes(rng, app, items, closer, detail):
    """A terse hand-off note: numbered, clipped."""
    out = [rng.choice([f"{app.name}: tasks from the planning call.", f"For {app.name} - notes from standup.", f"{app.name}, short version:"]), ""]
    k = 1
    for s, pitch, reqs in items:
        out.append(f"{k}. {s.title}" + (f" ({_lc(pitch)})" if pitch and detail else ""))
        for r in reqs:
            out.append(f"   - {r}")
        if detail and s.example:
            out += ["   " + ln for ln in _fence(s.example).split("\n")]
        k += 1
    if closer:
        out += ["", closer]
    return "\n".join(out)


_VOICES = {"ticket": _v_ticket, "chat": _v_chat, "design": _v_design, "bullets": _v_bullets, "email": _v_email, "story": _v_story, "notes": _v_notes}
_STYLE_ORDER = ["ticket", "chat", "design", "bullets", "email", "story", "notes", "pointer"]


def _slug_of(items) -> str:
    return "-".join(i[0].id for i in items)[:40]


def render_request(rng, app: App, targets: list, reqs_extra: dict, style: str) -> tuple[str, dict]:
    """The prompt text and any extra start files (the ``pointer`` style keeps the contract in docs/requests/)."""
    closer = rng.choice(_CLOSERS)
    detail = rng.random() < 0.65
    if style == "pointer":
        items = _items(rng, targets, reqs_extra)
        doc = _v_design(rng, app, items, "", True)
        slug = _slug_of(items).replace("_", "-")
        path = f"docs/requests/{slug}.md"
        opener = rng.choice([
            f"The request for the next change to {app.name} is written up in `{path}`. Please implement it as described there.",
            f"Can you take the change described in `{path}`? That note is the full spec; the README covers how things work today.",
            f"There is a design note in `{path}` for a change to {app.name}. Implement what it asks for.",
        ])
        return (opener + (" " + closer if closer else "")), {path: doc}
    items = _items(rng, targets, reqs_extra, with_pitch=rng.random() < 0.85)
    return _VOICES[style](rng, app, items, closer, detail), {}


# --------------------------------------------------------------------------------------------- tasks


def _cross_reqs(by_id: dict, final: set, targets: list) -> dict:
    extra: dict = {}
    for sid in sorted(final):
        s = by_id[sid]
        for other, x in s.cross.items():
            if other in final and (sid in targets or other in targets) and x.get("reqs"):
                owner = sid if sid in targets else other
                extra.setdefault(owner, []).extend(x["reqs"])
    return extra


def compose_tasks(rng: random.Random, app: App, make_slices, n: int, *, family_name: str = "") -> list[Task]:
    canon = make_slices(random.Random(0))
    ids = [s.id for s in canon]
    plans = _plan(rng, canon, n)
    styles = _STYLE_ORDER[:]
    rng.shuffle(styles)
    tasks: list[Task] = []
    for i, (targets, present) in enumerate(plans):
        trng = random.Random(rng.getrandbits(48))
        slices = make_slices(trng)
        by_id = {s.id: s for s in slices}
        final = set(targets) | present
        # start repository
        f_present, files_present = _collect(app, slices, present, "v")
        f_final, files_final = _collect(app, slices, final, "t")
        start = _render_tree(app.base, f_present)
        start.update(_render_tree(app.visible, f_present))
        start.update(files_present)
        src_final = _render_tree(app.base, f_final)
        src_final.update(files_final)
        hidden = _render_tree(app.hidden, f_final)
        solution = {p: t for p, t in src_final.items() if start.get(p) != t}
        style = styles[i % len(styles)]
        tg = [by_id[t] for t in targets]
        extra = _cross_reqs(by_id, final, targets)
        prompt, extra_files = render_request(trng, app, tg, extra, style)
        start.update(extra_files)
        d = difficulty(by_id, targets, present)
        slug = f"{i + 1:02d}-" + "+".join(t.replace("_", "-") for t in targets)
        tasks.append(Task(
            slug=slug[:60],
            prompt=prompt,
            difficulty=d,
            start=start,
            hidden=hidden,
            solution=solution,
            verify=app.verify,
            timeout_s=app.timeout_s,
            tags=["feature-slice", style, *[f"slice:{t}" for t in targets]],
            notes={"app": app.name, "targets": targets, "present": [x for x in ids if x in present], "style": style},
        ))
    return tasks


def register_app(name: str, app: App, make_slices, n: int, summary: str) -> None:
    fam = Family(name=name, category="feature", lang=app.lang, kind="feature", n=n, summary=summary)

    def gen(rng, count, _app=app, _mk=make_slices, _name=name):
        return compose_tasks(rng, _app, _mk, count, family_name=_name)

    gen.__module__ = make_slices.__module__
    register(fam, gen)
