"""project-songsheet: a converter for an invented chord-sheet markup (inline {chords}, sections, recalls, repeats, notes) to aligned text or
HTML, with transposition, capo shapes and key-dependent spelling.  Reference: Python (oracle) and JavaScript."""
from __future__ import annotations

from fx import family

from generators.project import _kit as K

THEME = "songsheet"
TOOLS = ["songsheet", "chordwright", "lyricforge", "strummer", "capotool", "tabloid", "setlister", "fretwork"]
FLAT_SETS = [
    ["F", "Bb", "Eb", "Ab", "Db", "Gb", "Dm", "Gm", "Cm", "Fm", "Bbm", "Ebm"],
    ["F", "Bb", "Eb", "Ab", "Dm", "Gm", "Cm", "Fm"],
    ["F", "Bb", "Eb", "Ab", "Db", "Dm", "Gm", "Cm", "Fm", "Bbm"],
    ["F", "Bb", "Eb", "Dm", "Gm", "Cm", "Am", "Em"],
    ["Bb", "Eb", "Ab", "Db", "Gb", "Gm", "Cm", "Fm", "Bbm", "Ebm", "Abm"],
    ["F", "Bb", "Eb", "Ab", "Db", "Gb", "Dm", "Gm", "Cm", "Fm"],
    ["F", "Bb", "Ab", "Dm", "Gm", "Fm"],
    ["F", "Bb", "Eb", "Ab", "Db", "Gb", "Dm", "Gm", "Cm", "Fm", "Bbm", "Ebm", "Abm"],
]
PLAN = [
    dict(lang="javascript", gap=1, flats=0, capo=True, recall=True, repeats=True, prefer=True, to=True, own=True),
    dict(lang="python", gap=2, flats=1, capo=False, recall=True, repeats=False, prefer=False, to=True, own=False),
    dict(lang="javascript", gap=1, flats=2, capo=True, recall=False, repeats=True, prefer=True, to=False, own=True),
    dict(lang="python", gap=2, flats=3, capo=True, recall=True, repeats=True, prefer=False, to=True, own=False),
    dict(lang="javascript", gap=1, flats=4, capo=False, recall=True, repeats=False, prefer=True, to=True, own=False),
    dict(lang="python", gap=1, flats=5, capo=True, recall=False, repeats=True, prefer=True, to=False, own=True),
    dict(lang="javascript", gap=2, flats=6, capo=True, recall=True, repeats=True, prefer=False, to=False, own=False),
    dict(lang="python", gap=2, flats=7, capo=False, recall=False, repeats=False, prefer=True, to=True, own=True),
]

VOICES = [
    "Our songbook is written in a home-made markup (inline chords in braces, `[[sections]]`, recalls, notes) and I need a tool that turns it into aligned plain text or HTML, optionally transposed or with capo shapes. `README.md` is the full specification, down to the HTML structure and the rule that picks sharps or flats. The tool is `{tool}`; write it in {Lang}: {run}. Visible examples: `python3 tests/run_examples.py`.",
    "build {tool} from README.md, {Lang}. reads a song on stdin, prints text or html. {run}. the chord-line alignment, the flat/sharp choice after transposing, and the header lines are all specified exactly, don't improvise. examples: `python3 tests/run_examples.py`",
    "Ticket SNG-{num}: chord-sheet renderer `{tool}`.\n\nSpec: README.md (markup, options, text layout, HTML layout, transposition). Language: {Lang}; the program is {run}. Hidden checks compare whole outputs for many songs and option combinations; please keep parser, chord logic and renderers apart.",
    "Could you implement the chord-sheet converter described in README.md? It supports text and HTML output, `--transpose`" + "{extra_opts}" + ", sections, notes and chord-only lines. Please write it in {Lang}; the program is {run}. `python3 tests/run_examples.py` runs a few examples, the hidden suite uses many more songs.",
    "Greenfield in {Lang}: `{tool}`, a renderer for our chord-sheet markup. Everything is in README.md: line types, the alignment algorithm for the chord line, escaping, transposition and the spelling rule. {run}. The hidden checks are grouped (text, html, transpose, spelling, errors, ...) and scored per group.",
    "README.md has the spec for `{tool}`. Please build it in {Lang} ({run}). Tricky bits: chords that would collide in the text layout get pushed right, `--transpose` must pick the spelling from the *key the chords are written in*, and chord-looking-but-invalid words must pass through unchanged. Visible examples: `python3 tests/run_examples.py`.",
    "short version: chord sheet markup -> text/html with transposition, spec in README.md, {Lang}, name it {tool}. {run}",
    "Please implement the songbook converter from README.md in {Lang}, named `{tool}`. How it is run: {run}. Songs come on standard input; options are in the README. Be careful with error precedence (option errors before song errors, first song error wins) and exact output formats.",
]

TITLES = ["Harbour Lights", "The Long Way Round", "Salt & Pepper Moon", "Quiet Mill", "Lantern <Song>", "Red Door Blues", "Orchard Waltz", "Tin Roof Rain"]
WORDS = ["walking", "down", "the", "road", "I", "found", "a", "stone", "under", "winter", "sky", "singing", "loud", "lonely", "river", "home", "again", "light", "harbour",
         "morning", "bells", "ringing", "old", "friend", "hold", "on", "tight", "&", "<3", "\"quote\""]
KEY_CHORDS = {
    "C": ["C", "Am", "F", "G", "Em", "Dm", "G7", "Cmaj7"], "G": ["G", "Em", "C", "D", "Bm", "D7", "Am"], "D": ["D", "Bm", "G", "A", "F#m", "A7", "Em"],
    "Em": ["Em", "C", "G", "D", "Am", "B7", "Bm"], "Am": ["Am", "F", "C", "G", "Dm", "E7", "Em"], "F": ["F", "Dm", "Bb", "C", "Gm", "C7", "Am"],
    "Bb": ["Bb", "Gm", "Eb", "F", "Cm", "F7", "Dm"], "Dm": ["Dm", "Bb", "F", "C", "Gm", "A7", "Am"], "E": ["E", "C#m", "A", "B", "F#m", "B7", "G#m"],
}


def readme(p: dict, tool: str, lang: str, by_name: dict) -> str:
    o: list[str] = []
    w = o.append
    flats = p["flat_keys"]
    w(f"# {tool}: a renderer for chord sheets\n")
    w(f"`{tool}` reads a song written in a small line-based markup from **standard input** and writes it to standard output as aligned plain text or as HTML, optionally transposed. "
      "Everything the output depends on is defined here; nothing is read except standard input and the command line.\n")
    w(f"Build and run it as {K.how_to_run(lang, tool)}. Usage: `{tool} [OPTION...] < song`. Exit status 1 and a single `error:` line on standard output when something is wrong (no other output then), otherwise 0.\n")
    w("## 1. The markup\n")
    w("The song is read line by line. Trailing white space of every line is removed first. These line types are recognised, in this order (the first that applies wins):\n")
    w("1. a line that is empty after that, or starts with `//`: ignored.")
    w("2. **title** `== TEXT ==` (spaces around `TEXT` optional): the title of the song. A second title is `error: line N: second title`, an empty `TEXT` is `error: line N: empty title`.")
    w("3. **meta** `:NAME VALUE`: `NAME` is the first word (case folded to lower case), `VALUE` the rest of the line trimmed; a line without a value is `error: line N: bad meta line`. "
      "Meta lines are kept in file order. `:key` takes a key (a note `A`-`G` with optional `#` or `b`, then an optional `m` for minor, e.g. `Em`, `F#`, `Bbm`; else `error: line N: bad key 'VALUE'`); "
      "`:capo` takes a number 0 to 11 (else `error: line N: bad capo 'VALUE'`); each of these two may appear once (`error: line N: duplicate 'NAME'`). Any other name is free text.")
    if p["repeats"]:
        w("4. **section** `[[NAME]]` or `[[NAME]] xK` (`K` one digit, 2 to 9: the section is *repeated* `K` times; `x0`, `x1` give `error: line N: bad repeat count`): starts a new section. `NAME` is trimmed.")
    else:
        w("4. **section** `[[NAME]]`: starts a new section. `NAME` is trimmed. (A repeat suffix such as `x2` is not supported here: `error: line N: repeat marks are not supported`.)")
    if p["recall"]:
        w("5. **recall** `>> NAME`: starts a new section called `NAME (again)` that contains a copy of the lines of the most recent earlier section called `NAME` (`error: line N: unknown section 'NAME'` if there is none). Later lines belong to the new section.")
    else:
        w("5. a line starting with `>>`: `error: line N: recall is not supported`.")
    w("6. **note** `!TEXT`: an annotation (`TEXT` trimmed, may be empty).")
    w("7. **chord line** `. CHORD CHORD ...` (a dot, then a space or the end of the line): chords only, separated by white space.")
    w("8. anything else: a **lyric line** with inline chords written `{CHORD}` (white space inside the braces is trimmed). `\\{` and `\\}` are a literal brace; a `}` without `{` is an ordinary character; "
      "`{` without a closing `}` on the line is `error: line N: unclosed '{'`; `{}` or `{ }` is `error: line N: empty chord`.")
    w("\nLines before the first section belong to an unnamed section. Lines of every kind except title and meta belong to the current section. The first error in file order is the one reported.\n")
    w("A lyric line is a list of **segments** `(chord or none, text)`: first the text before the first chord, as a segment without chord (present only if that text is not empty, or if the line has no chords at all, "
      "in which case it is the one segment holding the whole line), then, for every chord, a segment with that chord and the text that follows it up to the next chord (possibly empty).\n")
    w("## 2. Chords and transposition\n")
    w("A **chord** is a root note `A`-`G` with an optional `#` or `b`, a quality made of letters, digits and `+ # ( ) -` (possibly empty), and optionally `/` and a bass note (root with optional `#`/`b`). "
      "Anything else (`N.C.`, `x`, `||`) is not a chord and is never changed by transposition.\n")
    w("Notes have semitone numbers `C=0 D=2 E=4 F=5 G=7 A=9 B=11`, `#` adds 1 and `b` subtracts 1, modulo 12 (so `Cb` is `B`, `B#` is `C`). To **transpose** a chord by `S` semitones, move its root (and its bass note, if any) by `S` modulo 12 and keep the quality text. "
      "Notes are written with one of two tables: **sharps** `C C# D D# E F F# G G# A A# B`, or **flats** `C Db D Eb E F Gb G Ab A Bb B`.\n")
    w(f"**Which table.** Keys are written as in `:key`. A key is *flat* when it is one of: {', '.join('`' + k + '`' for k in flats)} (compared by semitone and minor/major, so `A#` is the same key as `Bb`). All other keys are sharp. "
      "The table used for the chords is the one of the key the chords are written in" +
      (", which is the transposed key lowered by the capo number when the song has a capo (see below)" if p["capo"] else ", i.e. the transposed key") +
      (". If the song has no `:key`, the table is sharps" + (" unless `--prefer flats` is given" if p["prefer"] else "") + ".") +
      (" The `Key:` header line is written with the table of the transposed key itself." if p["own"] else " The `Key:` header line is written with the same table as the chords."))
    w("")
    w("## 3. Options\n")
    opts = ["`--format text|html` (default `text`)", "`--transpose N`: shift every chord and the key by `N` semitones (an integer, optional sign, -11 to 11)"]
    if p["to"]:
        opts.append("`--to KEY`: transpose to `KEY` (a key as in `:key`). Only the root of `KEY` is used: the shift is `(root of KEY - root of the song key) mod 12`, taking 7 to 11 as the negative shifts -5 to -1 (so the shift is between -5 and 6); the song keeps its own major/minor. "
                    "Needs a `:key` in the song (`error: --to needs a key in the song`, found after the song was read without errors). Cannot be combined with `--transpose`.")
    if p["prefer"]:
        opts.append("`--prefer sharps|flats`: the table to use when the song has no `:key` (default `sharps`)")
    for x in opts:
        w("* " + x)
    w("\nOptions come in `NAME VALUE` pairs and are read left to right; the last repeat of an option wins. Option errors are reported before the song is read, the first one wins: `error: unknown option 'X'` (any other word), `error: missing value for --X`, "
      "`error: bad value 'V' for --X`; at the end, `error: --transpose and --to cannot be combined`" if p["to"] else "\nOptions come in `NAME VALUE` pairs and are read left to right; the last repeat of an option wins. Option errors are reported before the song is read, the first one wins: `error: unknown option 'X'` (any other word), `error: missing value for --X`, `error: bad value 'V' for --X`")
    w(".\n")
    if p["capo"]:
        w("**Capo.** With `:capo N` (N > 0) the chords are printed as *shapes*: they are shifted down by `N` semitones in addition to any transposition (shift = transposition - N, modulo 12 on the notes). The key (if any) is *not* lowered. "
          "The header shows `Capo: N`.\n")
    else:
        w("**Capo.** `:capo N` is information only: the header shows `Capo: N` (when `N` is not 0) and the chords are not changed.\n")
    w("## 4. Text output\n")
    w("Lines are produced in this order, one per output line:\n")
    w("1. If there is a title: the title, then a line of `=` as long as the title.")
    w("2. The **header lines**: `Key: K` (when the song has a key; `K` is the key after transposition, root written with a table as described above, then `m` if minor), `Capo: N` (when the capo is not 0), then the other meta lines in file order as `Name: value` (the name with its first letter in upper case).")
    w("3. For every section, in order: an empty line; then, if the section has a name or a repeat count above 1, its label line: `[NAME]`, followed by ` xK` if the repeat count is `K > 1` (just `xK` if the name is empty); then its lines:")
    w("   * a note: `(note: TEXT)`;")
    w("   * a chord line: the chords (transposed) joined by two spaces;")
    w("   * a lyric line: the lyric (all segment texts joined) preceded, if the line has chords, by the **chord line**: start with an empty string; for each chord, in order, let `col` be the number of lyric characters before it; "
      f"the chord is placed at column `col`, but at least {p['gap']} space{'s' if p['gap'] > 1 else ''} after the end of the previous chord (when there is one): pad with spaces to that column and append the chord. "
      "The chord line has no trailing spaces; the lyric is printed as it is (not shifted). If the lyric is empty or only white space after removing the chords, only the chord line is printed; a lyric line without chords is printed as it is (an empty one gives an empty line).")
    w("\nThere is no trailing blank line and no blank line after the last section.\n")
    w("## 5. HTML output\n")
    w("One element per output line, exactly in this form (`ESC(x)` replaces `&` by `&amp;`, `<` by `&lt;`, `>` by `&gt;`, `\"` by `&quot;`, in this order of treatment of a character, nothing else):\n")
    w("```\n<div class=\"song\">\n<h1>ESC(title)</h1>                       (only with a title)\n<p class=\"meta\">ESC(header line)</p>        (one per header line of the text output, same text)\n<section class=\"SLUG\">\n<h2>ESC(label)</h2>                       (only with a name or repeat count > 1; label as in the text output without brackets)\n...lines...\n</section>\n</div>\n```")
    w("`SLUG` is the section name in lower case with every run of characters other than `a-z0-9` replaced by one `-`, and leading and trailing `-` removed; `section` if that leaves nothing. The label for the `<h2>` is the name, followed by ` xK` for a repeat count above 1, trimmed of white space at both ends.\n")
    w("Lines inside a section:\n")
    w("* note: `<p class=\"note\">ESC(text)</p>`;")
    w("* chord line: `<p class=\"chords\">ESC(chords joined by one space)</p>` (chords transposed);")
    w("* lyric line without chords: `<p class=\"line\">ESC(text)</p>`;")
    w("* lyric line with chords: `<p class=\"line\">` followed by one `<span class=\"seg\"><b class=\"chord\">ESC(chord)</b>ESC(text)</span>` per segment (the chord transposed; for a segment without chord the `<b>` element is empty), then `</p>`. Segments without chord and with empty text do not occur.")
    w("\n## 6. Examples\n")
    ex = [(c, r) for (c, r) in by_name.values() if c.visible]
    for c, r in ex[:3]:
        w(K.show_case(tool, c, r))
    w("The visible examples (`tests/examples.json`, run with `python3 tests/run_examples.py`) use the same format as the hidden checks: command line, standard input, expected output and exit status.")
    return "\n".join(o) + "\n"


# ---------------------------------------------------------------------------------------------------------------
# cases
# ---------------------------------------------------------------------------------------------------------------

def song(rng, p, key=None, with_capo=False, rich=True, errors=None):
    k = key or rng.choice(list(KEY_CHORDS))
    pool = KEY_CHORDS.get(k, KEY_CHORDS["C"])
    lines = []
    if rng.random() < 0.9:
        lines.append(f"== {rng.choice(TITLES)} ==")
    if key is not False:
        lines.append(f":key {k}")
    if with_capo:
        lines.append(f":capo {rng.randint(1, 7)}")
    if rng.random() < 0.5:
        lines.append(f":{rng.choice(['artist', 'tempo', 'year'])} {rng.choice(['Mira Vale', '96', '1984', 'The Tin Roofs'])}")
    names = []
    for s in range(rng.randint(2, 4)):
        nm = rng.choice(["Verse 1", "Chorus", "Bridge", "Verse 2", "Outro", "Intro", "Pre-Chorus (soft)"])
        names.append(nm)
        rep = f" x{rng.randint(2, 4)}" if (p["repeats"] and rng.random() < 0.3) else ""
        lines.append(f"[[{nm}]]{rep}")
        for _ in range(rng.randint(2, 4)):
            r = rng.random()
            if r < 0.12:
                lines.append(". " + " ".join(rng.choice(pool + ["N.C.", "x2"]) for _ in range(rng.randint(2, 5))))
            elif r < 0.2 and rich:
                lines.append("!" + rng.choice(["slowly", "tacet", "half time & soft", "<capo on 2>"]))
            else:
                ws = [rng.choice(WORDS) for _ in range(rng.randint(3, 7))]
                out = []
                for w_ in ws:
                    if rng.random() < 0.45:
                        c = rng.choice(pool + (["Bb/D", "F#m7b5", "Dsus4", "C#7#9", "Eb", "G/B"] if rich and rng.random() < 0.3 else []))
                        if rng.random() < 0.3 and len(w_) > 3:
                            h = rng.randint(1, len(w_) - 1)
                            out.append(w_[:h] + "{" + c + "}" + w_[h:])
                        else:
                            out.append("{" + c + "}" + w_)
                    else:
                        out.append(w_)
                line = " ".join(out)
                if rng.random() < 0.1:
                    line = "  " + line
                if rng.random() < 0.08:
                    line = "{" + rng.choice(pool) + "}{" + rng.choice(pool) + "}"
                lines.append(line)
        if p["recall"] and rng.random() < 0.25 and names:
            lines.append(">> " + rng.choice(names))
        if rng.random() < 0.2:
            lines.append("// a comment")
        if rng.random() < 0.2:
            lines.append("")
    return "\n".join(lines) + "\n"


def make_cases(p: dict, tool: str, rng) -> list[K.Case]:
    cases: list[K.Case] = []
    cnt: dict[str, int] = {}

    def add(group, args, stdin, visible=False):
        cnt[group] = cnt.get(group, 0) + 1
        cases.append(K.Case(name=f"{group}-{cnt[group]:02d}", group=group, args=args, stdin=stdin, visible=visible))

    # plain text and html
    for k in range(4):
        add("text", [], song(rng, p, with_capo=bool(k % 2) and p["capo"]), visible=(k == 0))
    for k in range(4):
        add("html", ["--format", "html"], song(rng, p, with_capo=bool(k % 2) and p["capo"]), visible=(k == 0))
    add("html", ["--format", "html", "--transpose", "2"], song(rng, p))
    # transposition
    for k in range(6):
        n = rng.choice([1, 2, 3, 5, 7, -1, -2, -5, -7, 11, -11, 0, 6])
        add("transpose", ["--transpose", str(n)] + (["--format", "html"] if k % 3 == 2 else []), song(rng, p, with_capo=bool(k % 2) and p["capo"]), visible=(k == 1))
    for k in range(3):
        add("transpose", ["--transpose", rng.choice(["+3", "-4", "12", "x", "1.5", "-0", "+0"])], song(rng, p))
    # spelling: every key, transposed so that the flat/sharp decision changes
    for key in rng.sample(list(KEY_CHORDS), 6):
        n = rng.choice([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, -1, -2, -3, -4, -5])
        add("spelling", ["--transpose", str(n)], song(rng, p, key=key, rich=True))
    # no key
    for k in range(3):
        extra = []
        if p["prefer"]:
            extra = ["--prefer", rng.choice(["flats", "sharps"])]
        add("no-key", ["--transpose", str(rng.randint(1, 10))] + extra, song(rng, p, key=False))
    # target key
    if p["to"]:
        for k in range(5):
            key = rng.choice(list(KEY_CHORDS))
            tgt = rng.choice(["C", "D", "E", "F", "G", "A", "B", "Bb", "Eb", "F#", "C#", "Ab", "Em", "Bbm"])
            add("to-key", ["--to", tgt] + (["--format", "html"] if k == 4 else []), song(rng, p, key=key, with_capo=p["capo"] and k % 2 == 1))
        add("to-key", ["--to", "G"], song(rng, p, key=False))
        add("to-key", ["--to", "G", "--transpose", "2"], song(rng, p))
        add("to-key", ["--to", "H"], song(rng, p))
    # capo
    if p["capo"]:
        for k in range(4):
            add("capo", ["--transpose", str(rng.choice([0, 2, -2, 5]))], song(rng, p, key=rng.choice(list(KEY_CHORDS)), with_capo=True))
    else:
        add("capo", [], ":key G\n:capo 3\n[[A]]\n{G}hello {Em}there\n")
    # alignment
    for k in range(3):
        lines = ["== Align ==", ":key C", "[[Tight]]"]
        for _ in range(5):
            chords = rng.sample(["C", "Am7", "F#m7b5", "Cmaj7", "G/B", "Dsus4", "E", "Bb"], rng.randint(2, 4))
            text = ""
            for c in chords:
                text += "{" + c + "}" + rng.choice(["a", "go", "me", "stay", "x", ""]) + rng.choice([" ", "", "  "])
            lines.append(text.rstrip())
        lines += ["{C}", "{C}{G}{Am}{F}", "plain", "   {G}indented lyric", "", "{C} ", "{Am}trailing  "]
        add("align", [], "\n".join(lines) + "\n", visible=False)
    # escapes and html
    add("escape", [], "== A & B ==\n[[Verse <1>]]\nsay \\{this\\} and {C}that} and {G}\"quote\" & <b>\n!5 > 3 & 2 < 4\n", visible=False)
    add("escape", ["--format", "html"], "== A & B ==\n[[Verse <1>]]\nsay \\{this\\} and {C}that} and {G}\"quote\" & <b>\n!5 > 3 & 2 < 4\n. C G <x>\n")
    add("escape", ["--format", "html"], "[[ Odd  Name!! ]]\n{C}x\n[[!!]]\n{G}y\n[[Ünï]]\n")
    # recall / repeat
    if p["recall"] or p["repeats"]:
        for k in range(3):
            lines = ["== R ==", ":key Em", "[[Chorus]]" + (" x2" if p["repeats"] else ""), "{Em}oh {C}sing", "!loud", "[[Verse]]", "{G}one {D}two"]
            if p["recall"]:
                lines += [">> Chorus", "{Am}after", ">> Verse", ">> Chorus"]
            if p["repeats"]:
                lines += ["[[Coda]] x" + rng.choice(["3", "9"]), ". Em C"]
            add("structure", ["--transpose", str(k)] + (["--format", "html"] if k == 2 else []), "\n".join(lines) + "\n")
    # errors: options
    base = song(rng, p)
    bad_opts = [["--format"], ["--format", "pdf"], ["--transpose"], ["--transpose", "12"], ["--transpose", "-12"], ["--bogus", "1"], ["text"], ["--format", "text", "--format", "html"],
                ["--transpose", "1", "--transpose", "2"], ["--prefer", "flats"], ["--to", "G"], ["--transpose", "x", "--bogus", "y"], ["--bogus", "1", "--transpose"]]
    for a in bad_opts:
        add("options", a, base)
    # errors: song
    bad_songs = ["== A ==\n== B ==\n", "==  ==\n", "== A ==\n:key\n", ":key H\n", ":key em\n", ":key Em\n:key G\n", ":capo 12\n", ":capo x\n", ":capo 3\n:capo 4\n", "[[A]] x1\n", "[[A]] x0\n", "[[A]] x2\n{C}a\n",
                 ">> Nope\n", "[[A]]\n{C}a\n>> A\n>> B\n", "{C\n", "a {C} b {G\n", "{}\n", "{ }x\n", "ok {C}\nbad {\n", "[[A]]\n!note\n. \n.\n", "\\{C}no chord}\n", ":Artist  Someone Else  \n:Year 1999\n", "a}b {C}c\n", "", "\n\n// only comments\n"]
    rng.shuffle(bad_songs)
    for s in bad_songs[:16]:
        add("song-errors", rng.choice([[], ["--format", "html"], ["--transpose", "2"]]), s)
    # chord grammar
    chordtests = "[[Chords]]\n. C C# Db Dm7 Dsus4 C7#9 F#m7b5 G/B Bb/D E#m Fb Cb/E# c x N.C. C/ /G C// Cm(maj7) C+ Caug C-5 H Cb5 B#dim\n{C#}a{Fb}b{N.C.}c{C/}d{Cadd9/F#}e\n"
    for n in (0, 1, 3, -2, 6):
        add("chord-grammar", ["--transpose", str(n)] + (["--format", "html"] if n == 6 else []), ":key C\n" + chordtests)
    # sessions
    for k in range(8):
        args = []
        if rng.random() < 0.8:
            args += ["--transpose", str(rng.randint(-11, 11))]
        if rng.random() < 0.4:
            args += ["--format", "html"]
        if p["prefer"] and rng.random() < 0.3:
            args += ["--prefer", rng.choice(["flats", "sharps"])]
        add("sessions", args, song(rng, p, key=rng.choice([False, None, None]), with_capo=p["capo"] and rng.random() < 0.5))
    return cases


@family("project-songsheet", category="project", lang="javascript", kind="greenfield", n=8,
        summary="a chord-sheet markup to aligned text/HTML converter: transposition with key-dependent spelling, capo shapes, recalls, repeats, escaping")
def gen(rng, n):
    for i in range(n):
        plan = dict(PLAN[i])
        tool = TOOLS[i]
        lang = plan.pop("lang")
        p = dict(plan)
        p["flat_keys"] = FLAT_SETS[p["flats"]]
        cfg = dict(GAP=p["gap"], FLAT_KEYS=p["flat_keys"], CAPO_SHAPES=p["capo"], RECALL=p["recall"], REPEATS=p["repeats"], PREFER_OPT=p["prefer"],
                   TO_OPT=p["to"], KEY_OWN_SPELLING=p["own"])
        cases = make_cases(p, tool, rng)
        py_sol = K.merged(K.load_src(THEME, "python", tool), K.render_config("python", cfg))
        sol = py_sol if lang == "python" else K.merged(K.load_src(THEME, lang, tool), K.render_config(lang, cfg))
        extra = (", `--to`" if p["to"] else "") + (", `--prefer`" if p["prefer"] else "")
        prompt = VOICES[i % len(VOICES)].format(tool=tool, Lang=K.LANG_NAME[lang], run=K.how_to_run(lang, tool), num=7100 + i * 13, extra_opts=extra)
        nfeat = sum([p["capo"], p["recall"], p["repeats"], p["prefer"], p["to"], p["own"]])
        yield K.project_task(
            theme=THEME, tool=tool, lang=lang, cases=cases, solution=sol, py_solution=py_sol,
            readme=lambda by_name, p=p, tool=tool, lang=lang: readme(p, tool, lang, by_name),
            prompt=prompt, difficulty=3 if nfeat <= 2 else (4 if nfeat <= 4 else 5), slug=f"{i + 1:02d}-{tool}-{lang}",
            notes={"gap": p["gap"], "flat_keys": p["flat_keys"], "capo_shapes": p["capo"], "recall": p["recall"], "repeats": p["repeats"], "to": p["to"], "prefer": p["prefer"]},
            tags=["markup", "music", "html"],
        )
