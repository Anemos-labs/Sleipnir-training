"""project-typeset: a line-printer typesetter: a small markup language is wrapped (greedy, optional justification), underlined, quoted,
bulleted and then paginated with orphan/widow control, keep-with-next headings, figures and forced page breaks.
Reference: Python (oracle) and Rust."""
from __future__ import annotations

from fx import family

from generators.project import _kit as K

THEME = "typeset"
TOOLS = ["typeset", "galley", "pagecraft", "folio", "presswork", "leadingd", "lineset", "imposer"]

WORDS = ("the of and a to in is it you that he was for on are with as his they be at one have this from or had by hot word but what some we can out other were all "
         "there when up use your how said an each she which do their time if will way about many then them write would like so these her long make thing see him two has look "
         "more day could go come did number sound no most people my over know water than call first who may down side been now find head stand own page should country found "
         "answer school grow study still learn plant cover food sun four between state keep eye never last let thought city tree cross farm hard start might story saw far sea "
         "draw left late run while press close night real life few north open seem together next white children begin got walk example ease paper group always music those both "
         "mark often letter until mile river car feet care second book carry took science eat room friend began idea fish mountain stop once base hear horse cut sure watch "
         "color face wood main enough plain girl usual young ready above ever red list though feel talk bird soon body dog family direct pose leave song measure door product "
         "black short numeral class wind question happen complete ship area half rock order fire south problem piece told knew pass since top whole king space heard best hour "
         "better true during hundred five remember step early hold west ground interest reach fast verb sing listen six table travel less morning ten simple several vowel "
         "toward war lay against pattern slow center love person money serve appear road map rain rule govern pull cold notice voice unit power town fine certain fly fall "
         "lead cry dark machine note wait plan figure star box noun field rest correct able pound done beauty drive stood contain front teach week final gave green oh quick "
         "develop ocean warm free minute strong special mind behind clear tail produce fact street inch multiply nothing course stay wheel full force blue object decide "
         "surface deep moon island foot system busy test record boat common gold possible plane stead dry wonder laugh thousand ago ran check game shape equate hot miss "
         "brought heat snow tire bring yes distant fill east paint language among").split()
LONG_WORDS = ["internationalization", "supercalifragilisticexpialidocious", "pneumonoultramicroscopicsilicovolcanoconiosis", "https://example.org/a/very/long/path/to/a/resource",
              "configuration_management_database_entry", "antidisestablishmentarianism", "thequickbrownfoxjumpsoverthelazydogagainandagain", "x" * 61, "floccinaucinihilipilification",
              "electroencephalographically", "a_b_c_d_e_f_g_h_i_j_k_l_m_n_o_p_q_r_s_t_u_v_w_x_y_z"]
FIG_NAMES = ["chart", "map", "photo-1", "plot_2", "diagram", "logo", "fig3", "scan", "table-a", "sketch", "x", "Overview"]

PLAN = [
    dict(lang="rust", width=40, height=14, orphans=2, widows=2, keep=True, just=True, upper=True, ul=("=", "-", ""), quote="| ", bullet="-", item_out="* ", long="cut"),
    dict(lang="python", width=36, height=12, orphans=2, widows=1, keep=True, just=False, upper=False, ul=("=", "-", "~"), quote="> ", bullet="*", item_out="- ", long="keep"),
    dict(lang="rust", width=50, height=16, orphans=3, widows=2, keep=False, just=True, upper=True, ul=("#", "=", ""), quote="  | ", bullet="+", item_out="+ ", long="cut"),
    dict(lang="rust", width=32, height=10, orphans=1, widows=1, keep=True, just=True, upper=False, ul=("=", "", ""), quote=": ", bullet="-", item_out="- ", long="keep"),
    dict(lang="python", width=44, height=18, orphans=2, widows=3, keep=True, just=False, upper=True, ul=("-", "-", ""), quote="> ", bullet="*", item_out="o ", long="cut"),
    dict(lang="rust", width=28, height=12, orphans=2, widows=2, keep=True, just=True, upper=True, ul=("=", "-", "."), quote="| ", bullet="-", item_out="- ", long="cut"),
    dict(lang="rust", width=60, height=20, orphans=2, widows=2, keep=False, just=False, upper=False, ul=("=", "-", ""), quote="# ", bullet="*", item_out="* ", long="keep"),
    dict(lang="rust", width=38, height=15, orphans=3, widows=3, keep=True, just=True, upper=True, ul=("*", "-", ""), quote="|", bullet="+", item_out="> ", long="keep"),
]

VOICES = [
    "We need a tiny typesetter for a line printer: it reads a plain-text markup (headings, paragraphs, quotes, bullet items, figures, page breaks) and prints it on pages of a fixed number of lines. `README.md` defines every rule down to the last space. The program is `{tool}`; write it in {Lang}: {run}. Visible examples: `python3 tests/run_examples.py`. The hidden checks include many pagination edge cases.",
    "build {tool} from README.md in {Lang}. text layout: greedy wrapping, headings with underlines, quotes, bullets, figures, then pagination with orphan/widow control. {run}. the README is exact about blank lines between blocks and about where a block may be split. examples: `python3 tests/run_examples.py`",
    "Ticket DOC-{num}: implement the `{tool}` page layout tool (spec in README.md).\n\nLanguage: {Lang}; the program is {run}. Output is compared byte for byte, footers included. Keep the markup reading, the line breaking and the pagination in separate modules, please.",
    "Could you write the page layout program described in README.md? It lays out a small markup language on fixed-size pages, with a few options for width, height, orphans and widows. {Lang} please; the program is {run}. `python3 tests/run_examples.py` runs a few examples; the hidden suite is much bigger and grouped by feature.",
    "Greenfield in {Lang}: `{tool}`, a deterministic text typesetter. The README defines the markup, how every block is turned into lines, and how lines are distributed over pages. {run}. The hidden suite is scored per group (wrapping, blocks, pagination, breaks, options, errors, mixed documents).",
    "README.md has the spec for `{tool}`. Please build it in {Lang} ({run}). Details that decide many checks: when a block may be split between pages, what a heading needs to stay on a page, which lines of an item belong to it, and how the option values are validated. Visible examples: `python3 tests/run_examples.py`.",
    "short version: page layout tool, spec in README.md, {Lang}, call it {tool}. {run}",
    "Please implement the typesetter from README.md in {Lang}, named `{tool}`. How it is run: {run}. The document comes from standard input and the pages go to standard output. It has to be exact about blank lines, split points and the `-- N/M --` footers.",
]


def q(s: str) -> str:
    return '`"' + s + '"`'


# ---------------------------------------------------------------------------------------------------------------
# README
# ---------------------------------------------------------------------------------------------------------------

def readme(p: dict, tool: str, lang: str, by_name: dict) -> str:
    o: list[str] = []
    w = o.append
    W, H, O, WD = p["width"], p["height"], p["orphans"], p["widows"]
    quote_w = len(p["quote"])
    w(f"# {tool}: a plain-text page layout tool\n")
    w(f"`{tool}` reads a small markup document on standard input and lays it out on pages of a fixed width and height, like the typesetter of a line printer: "
      "blocks are wrapped into lines, lines are distributed over pages, every page gets a footer. Everything is counted in characters and lines (the input is ASCII), so the output is fully determined by the rules below.\n")
    w(f"Build and run it as {K.how_to_run(lang, tool)}. Usage:\n")
    w(K.fence(f"{tool} [--width N] [--height N] [--orphans N] [--widows N]" + (" [--justify]" if p["just"] else "") + " < document\n"))
    w("The pages go to standard output. The exit status is 0, or 1 if an `error:` line was printed (see sections 1 and 5).\n")
    w("## 1. Options\n")
    w("Options are read left to right, **before** the document is read.\n")
    w(f"* `--width N`: the page width in characters, 10 to 120; default **{W}**.")
    w(f"* `--height N`: the number of lines of a page, 4 to 80, footer not counted; default **{H}**.")
    w(f"* `--orphans N`: the fewest lines of a split block allowed at the bottom of a page, 1 to 4; default **{O}**.")
    w(f"* `--widows N`: the fewest lines of a split block allowed at the top of the next page, 1 to 4; default **{WD}**.")
    if p["just"]:
        w("* `--justify`: justify the text (section 3). It takes no value.")
    else:
        w("* There is no justification: `--justify` is an unknown option.")
    w("")
    w("A value is **1 to 3 ASCII digits** (leading zeros are fine: `040` is 40) that lies in the range of the option; if the same option is repeated the last value wins. "
      "The first problem found stops everything: the program prints one line and exits with status 1, without reading the document:\n")
    w("* `error: unknown option 'X'`: an argument that is not one of the options above (this includes plain words and forms such as `--width=30`);")
    w("* `error: missing value for --width`: the option is the last argument;")
    w("* `error: bad value 'X' for --width`: the argument after the option is not a valid value; it is taken as the value whatever it looks like (`--width --justify` is a bad value `'--justify'`), "
      "and the same message form (with the option name) is used for the other three options.\n")
    w("## 2. Reading the document\n")
    w("The input is split at newline characters; the lines are numbered from 1. Each line loses its **trailing white space** (spaces and tabs; white space always means space or tab, and *trimmed* means with white space removed at both ends). "
      "A line with nothing left is **blank**. A blank line only ends the paragraph, quote or item that is open (below) and is otherwise ignored; it does not count as a separator by itself (separators are decided in section 4).\n")
    w("Every other line is classified by the **first** rule that applies:\n")
    w("1. A line that is exactly `@break` is a **page break** block.")
    w("2. A line that *starts with* `@figure` must have the form `@figure NAME HEIGHT`: one or more spaces, a name of letters, digits, `_` and `-`, one or more spaces, "
      "a height of one or two digits that is at least 1, and nothing else; it is a **figure** block. Anything else is the error `bad figure` (section 5).")
    w("3. A line of one to three `#` followed by nothing or by a space and text is a **heading** block of that level (1 to 3); its text is what follows the `#`s, trimmed. "
      "A heading without text is the error `empty heading`. More than three `#`, or a `#` that is followed by another character (`#tag`), is not a heading.")
    w("4. A line starting with `>` is a line of a **quote**: drop the `>` and then one space if there is one; the rest, trimmed, is the quote text. "
      "If the open block is a quote, the text is appended to it (joined by one space); otherwise a new quote block starts.")
    w(f"5. A line starting with {q(p['bullet'] + ' ')} (the character `{p['bullet']}` and a space) starts a new **item** block; its text is the rest of the line, trimmed. "
      f"Other bullet characters mean nothing here: a line starting with `{'*' if p['bullet'] != '*' else '+'} ` is ordinary text.")
    w("6. If the open block is an item and the line starts with **two spaces**, its trimmed text is appended to the item (joined by one space): a continuation line.")
    w("7. If the open block is a paragraph, the trimmed line is appended to it (joined by one space), whatever its indentation.")
    w("8. Otherwise the trimmed line starts a new **paragraph** block.\n")
    w("The *open block* is the paragraph, quote or item that the previous non-blank rule line created or extended; it is closed by a blank line, by a break, figure or heading, and by a line that starts a different kind of block "
      "(so a paragraph line right after a quote starts a new paragraph, and an item line right after a paragraph starts an item, neither needing a blank line). "
      "Two item lines in a row make two items (rule 5 always starts a new item).\n")
    w("An item is **joined** when its first line comes directly after (the first line or a continuation line of) the previous item, with no line in between. Joined items form a tight list, see section 4.\n")
    w("## 3. Turning blocks into lines\n")
    w("The text of a block is a list of *words* (separated by white space). **Wrapping** to a width `n` is greedy: put words on a line, separated by single spaces, as long as the line stays at most `n` characters; the next word starts a new line. "
      + ("A word longer than `n` is **cut**: whatever is on the current line is finished first, then the word is cut into pieces of exactly `n` characters, each piece on its own line, and the last piece (1 to `n` characters) is then treated like an ordinary word, so the following words may join it. "
         if p["long"] == "cut" else
         "A word longer than `n` is **kept whole**: it gets a line of its own (the line before it is finished first) which is simply longer than `n`; words after it start a new line, since nothing fits next to it. ")
      + "Text without words wraps to one empty line.\n")
    w("* **Paragraph**: wrapped to the page width.")
    w(f"* **Quote**: wrapped to the page width minus {quote_w} (at least 1); every line gets the prefix {q(p['quote'])}.")
    w("* **Item**: wrapped to the page width minus 2 (at least 1); the first line gets the prefix " + q(p["item_out"]) + ", every other line two spaces.")
    ul1, ul2, ul3 = p["ul"]
    w(f"* **Heading**: the text" + (" of a level-1 heading is converted to upper case first" if p["upper"] else "") + ", wrapped to the page width. " +
      "Below the heading lines comes an **underline** line made of the underline character repeated as often as the *longest heading line* is long; the characters are " +
      ", ".join(f"`{c}` for level {i}" if c else f"none for level {i}" for i, c in enumerate(p["ul"], 1)) + " (no underline line at all for a level without one).")
    w("* **Figure**: the line `[figure NAME]` followed by HEIGHT-1 lines `[ ]`; HEIGHT lines in all.")
    w("* **Page break**: no lines.\n")
    if p["just"]:
        w("**Justification** (only with `--justify`) applies to paragraphs, quotes and items, never to headings or figures. Every line of such a block except its **last** line is padded to the wrapping width of that block "
          "(page width, page width minus the quote prefix, page width minus 2): the single spaces between words are widened so that the line gets exactly that length. With `g` gaps and `d` characters to add, "
          "every gap gets `d / g` extra spaces (integer division) and the **leftmost** `d % g` gaps one more. Lines with a single word, and lines already at least as long as the width, are left as they are. The prefixes are added afterwards.\n")
    w("No output line ends with a space (trailing spaces, for instance of the quote prefix on an empty quote line, are removed from every output line; this does not change how many lines there are).\n")
    w("## 4. Pages\n")
    w("A page holds at most `--height` lines (the footer is not counted). The blocks are placed in document order, on the current page, starting with an empty first page. "
      "**Separator**: a block placed on a page that already has lines is preceded by one empty line, except an item that is *joined* when the block placed just before it on this page was an item, which has no separator. "
      "On an empty page there is never a separator, so no page starts with an empty line. The separator takes part in every calculation below (\"fits\" always includes it).\n")
    w("* **Page break**: if the current page has lines, a new empty page starts. Otherwise nothing happens (also at the start of the document, and several breaks in a row count as one).")
    w("* **Figures and headings are never split.** A figure needs all its lines. A heading needs its lines (underline included)" +
      (", plus the lookahead below" if p["keep"] else "") +
      ". If the current page has lines and the need does not fit in the room that is left (height, minus the lines used, minus the separator), a new page starts first; the block is then placed. "
      "On an empty page it is always placed, even if it is taller than the page (the page is then longer than `--height`).")
    if p["keep"]:
        w("* **Headings stay with what follows (keep with next).** The lookahead of a heading is: *nothing* if it is the last block or if a page break follows; "
          "all the lines of a following figure; for a following paragraph, quote or item, the first `min(L, ORPHANS)` lines of it, where `L` is the number of its lines (and ORPHANS the value in effect); "
          "for a following heading, all its lines plus one separator line plus *its* lookahead, recursively. The need of the heading is its own lines, plus one separator line, plus the lookahead (just its own lines when the lookahead is nothing). "
          "This is only a count of lines: it does not check that the following block could really be split there.")
    w("* **Paragraphs, quotes and items may be split between pages.** Let `n` be the number of lines of the block and `room` the number of lines left on the current page after the separator. "
      "If `n <= room` the block is placed whole. Otherwise look for the **largest** `k` with `1 <= k <= min(room, n-1)`, `k >= ORPHANS` and `n-k >= WIDOWS`: the first `k` lines are placed on the current page (after the separator), "
      "a new page starts, and the remaining `n-k` lines are handled in exactly the same way on the new page (they may be split again). "
      "If there is no such `k`: when the current page has lines, a new page starts and the block is handled again on the empty page (it loses its separator); "
      "when the current page is already empty, the page is filled with the first `--height` lines of the block, a new page starts and the rest is handled the same way (the rules cannot be met, the block is cut at the page end).")
    w("* After the last block, a trailing empty page (created by a final page break or by a split that ended exactly at a page end) is discarded, unless it is the only page. An empty document is one empty page.\n")
    w("**Output.** For each page, its lines, then the footer `-- N/M --` (`N` the page number from 1, `M` the number of pages), each line ending with a newline; an empty line separates a footer from the next page. "
      "So an empty document prints just `-- 1/1 --`.\n")
    w("## 5. Document errors\n")
    w("A document error prints exactly one line, `error: line N: MESSAGE`, nothing else (no pages), exit status 1. `N` is the line number in the input. The messages are `bad figure` and `empty heading` (section 2), "
      "and `figure NAME is taller than a page` (a figure whose HEIGHT is greater than the value of `--height` in effect; `N` is the line of the figure). "
      "The document is checked in two passes: first the whole document is read (the first line that is a `bad figure` or an `empty heading` is reported), and only if that succeeds the figures are checked against the page height, the first too tall figure in document order being reported.\n")
    w("## 6. Examples\n")
    ex = [(c, r) for (c, r) in by_name.values() if c.visible]
    for c, r in ex[:3]:
        w(K.show_case(tool, c, r))
    w("The visible examples (`tests/examples.json`, run with `python3 tests/run_examples.py`) use the same format as the hidden checks.")
    return "\n".join(o) + "\n"


# ---------------------------------------------------------------------------------------------------------------
# documents
# ---------------------------------------------------------------------------------------------------------------

PROBE = r'''
import json, sys
sys.path.insert(0, "src")
import config as C
import blocks as B
import paginate as P
KEEP0 = C.KEEP

def lay(d, o=None, wd=None, keep=None):
    C.KEEP = KEEP0 if keep is None else keep
    bl = B.parse(d["src"])
    for b in bl:
        b.lines = B.render(b, d["w"], d["just"])
        if b.kind == "figure" and b.height > d["h"]:
            raise B.DocError("tall")
    return P.paginate(bl, d["h"], d["o"] if o is None else o, d["wd"] if wd is None else wd)

res = []
for d in json.load(sys.stdin):
    try:
        base = lay(d)
        res.append({"pages": len(base), "lines": sum(len(x) for x in base), "orphan": lay(d, o=1) != base, "widow": lay(d, wd=1) != base,
                    "keep": lay(d, keep=not KEEP0) != base, "tall": max(len(x) for x in base) > d["h"]})
    except B.DocError:
        res.append(None)
print(json.dumps(res))
'''


class Gen:
    def __init__(self, rng, p):
        self.rng = rng
        self.p = p

    def text(self, n, longp=0.0):
        r = self.rng
        out = []
        for _ in range(n):
            if r.random() < longp:
                out.append(r.choice(LONG_WORDS))
                continue
            wd = r.choice(WORDS)
            if r.random() < 0.07:
                wd = wd.capitalize()
            if r.random() < 0.08:
                wd += r.choice([",", ".", ";", "!", "?", ")"])
            out.append(wd)
        return out

    def src_lines(self, words, maxlines=4, indent=False, ragged=True):
        """Split words over 1..maxlines source lines, with some messy white space."""
        r = self.rng
        k = r.randint(1, maxlines) if len(words) > 4 else 1
        cuts = sorted(r.sample(range(1, len(words)), k - 1)) if k > 1 else []
        parts, last = [], 0
        for c in cuts + [len(words)]:
            parts.append(words[last:c])
            last = c
        lines = []
        for i, part in enumerate(parts):
            sep = " "
            line = sep.join(part)
            if ragged and r.random() < 0.12:
                line = line.replace(" ", "  ", 1)
            if ragged and r.random() < 0.06:
                line = line.replace(" ", "\t", 1)
            if ragged and r.random() < 0.15:
                line += r.choice(["  ", " ", "\t"])
            if i > 0 and indent:
                line = "  " * r.randint(1, 2) + line
            elif i > 0 and ragged and r.random() < 0.1:
                line = " " + line
            lines.append(line)
        return lines

    def heading(self, level=None, maxw=6):
        r = self.rng
        level = level or r.choice([1, 2, 2, 3])
        words = [w.capitalize() if i == 0 else w for i, w in enumerate(self.text(r.randint(1, maxw)))]
        gap = " " if r.random() > 0.1 else "   "
        return ["#" * level + gap + " ".join(words) + (" " if r.random() < 0.1 else "")]

    def para(self, lo=6, hi=30, longp=0.0, lines=4):
        return self.src_lines(self.text(self.rng.randint(lo, hi), longp), maxlines=lines)

    def quote(self):
        r = self.rng
        ls = self.src_lines(self.text(r.randint(4, 22)), maxlines=3, ragged=False)
        out = []
        for ln in ls:
            form = r.random()
            out.append(">" + ln if form < 0.2 else ("> " + ln if form < 0.85 else ">  " + ln))
        if r.random() < 0.05:
            out.insert(r.randint(0, len(out)), ">")
        return out

    def items(self):
        r = self.rng
        out = []
        loose = r.random() < 0.3
        for i in range(r.randint(2, 5)):
            ls = self.src_lines(self.text(r.randint(2, 16)), maxlines=2, indent=True, ragged=False)
            out.append(self.p["bullet"] + " " + ls[0])
            out += ls[1:]
            if loose and i:
                out.insert(len(out) - len(ls), "")
        return out

    def figure(self, maxh):
        r = self.rng
        return ["@figure %s%s%d" % (r.choice(FIG_NAMES), " " if r.random() < 0.9 else "   ", r.randint(1, max(1, maxh)))]

    def trap(self):
        """A line that looks like markup but is plain text."""
        r = self.rng
        other = "*" if self.p["bullet"] != "*" else "+"
        return [r.choice(["#hashtag is not a heading", "#### four hashes make text", "@note this is just text", "@breaks are not breaks", f"{other} not an item here",
                          self.p["bullet"] + "glued to a word", "#1 priority", "@ at sign", "  indented first line of a paragraph"])]

    def blocks(self, nblocks, maxfig, mix, longp=0.0, breaks=0.0):
        """A document as a list of source lines."""
        r = self.rng
        kinds = list(mix)
        weights = [mix[k] for k in kinds]
        out: list[str] = []
        prev = None
        for i in range(nblocks):
            kind = r.choices(kinds, weights)[0]
            if kind == "heading":
                b = self.heading()
            elif kind == "para":
                b = self.para(longp=longp)
            elif kind == "quote":
                b = self.quote()
            elif kind == "items":
                b = self.items()
            elif kind == "figure":
                b = self.figure(maxfig)
            elif kind == "trap":
                b = self.trap()
            else:
                b = ["@break"]
            if out:
                same = (prev == kind and kind in ("para", "quote", "items", "trap")) or (prev == "items" and kind == "para")
                tight = r.random() < 0.18 and not same and kind != "trap" and prev not in ("trap", "items")
                if kind == "heading" and r.random() < 0.15:
                    tight = True
                if not tight:
                    out += [""] * (1 if r.random() < 0.85 else r.randint(2, 3))
                    if r.random() < 0.04:
                        out[-1] = "  "
            out += b
            prev = kind
            if breaks and r.random() < breaks and kind != "break":
                out += ["", "@break"]
                prev = "break"
        return out


MIX_ALL = {"heading": 3, "para": 5, "quote": 1.5, "items": 2, "figure": 1, "trap": 0.4}
MIX_TEXT = {"para": 1}
MIX_HEADS = {"heading": 4, "para": 5, "items": 1.5, "quote": 1}
MIX_PAGES = {"heading": 2.5, "para": 5, "quote": 1.5, "items": 2.5, "figure": 1.2}


def text_of(lines: list[str], final_newline: bool = True) -> str:
    return "\n".join(lines) + ("\n" if final_newline else "")


def opt_args(p: dict, d: dict, rng) -> list[str]:
    """Command-line options that set the page parameters of candidate `d` (sometimes spelled out although they are the default)."""
    args: list[str] = []
    spec = [("--width", d["w"], p["width"]), ("--height", d["h"], p["height"]), ("--orphans", d["o"], p["orphans"]), ("--widows", d["wd"], p["widows"])]
    rng.shuffle(spec)
    for name, v, default in spec:
        if v != default or rng.random() < 0.25:
            args += [name, str(v)]
    if d["just"]:
        args.append("--justify")
    return args


def make_cases(p: dict, tool: str, rng, py_solution) -> list[K.Case]:
    g = Gen(rng, p)
    cases: list[K.Case] = []
    cnt: dict[str, int] = {}

    def add(group, src, args, visible=False):
        cnt[group] = cnt.get(group, 0) + 1
        cases.append(K.Case(name=f"{group}-{cnt[group]:02d}", group=group, args=args, stdin=src, visible=visible))

    def cand(lines, w=None, h=None, o=None, wd=None, just=None, final_nl=True):
        return dict(src=text_of(lines, final_nl), w=w or p["width"], h=h or p["height"], o=o or p["orphans"], wd=wd or p["widows"], just=bool(just))

    def probed(cands):
        return K.probe(py_solution, tool, PROBE, cands)

    def choose(make, flag, count, tries=120, minpages=2, extra=None):
        """`count` candidates for which the oracle's answer depends on the rule `flag`."""
        cs = [make() for _ in range(tries)]
        fl = probed(cs)
        good = [c for c, f in zip(cs, fl) if f and f[flag] and f["pages"] >= minpages and not f["tall"] and (extra is None or extra(f))]
        if len(good) < count:
            raise K.BuildError(f"typeset: only {len(good)} candidates with {flag} (wanted {count})")
        return good[:count]

    def valid(make, count, tries=60):
        cs = [make() for _ in range(tries)]
        fl = probed(cs)
        good = [c for c, f in zip(cs, fl) if f and not f["tall"]]
        return good[:count]

    # ---- wrapping: paragraphs only, many widths, long words, white space
    widths = [None, 10, 12, 17, 25, 33, 60, 120]
    for i, wv in enumerate(widths):
        lines = g.blocks(rng.randint(2, 5), 3, MIX_TEXT, longp=0.0 if i < 3 else 0.12)
        if i == 1:
            lines = g.blocks(4, 3, MIX_TEXT, longp=0.3)
        d = cand(lines, w=wv, h=80)
        add("wrap", d["src"], opt_args(p, dict(d, just=False), rng) + [])
    add("wrap", "\n", [])
    add("wrap", "   \n\t\n\n", ["--width", "20"])
    add("wrap", "one\n", ["--width", "10"])
    add("wrap", "no final newline at the end of this document", ["--width", "15"])
    add("wrap", "  leading spaces\n\ttab\tseparated   words\t \n", ["--width", "30"])
    add("wrap", (("w" * 24) + " ") * 3 + "\n" + "z" * 50 + " end\n", ["--width", "24"])
    add("wrap", "ab " * 40 + "\n", ["--width", "10"])

    # ---- blocks: every block kind, one tall page
    for i in range(6):
        lines = g.blocks(rng.randint(5, 9), 4, MIX_ALL, longp=0.04)
        d = cand(lines, h=80, w=rng.choice([p["width"], p["width"], 20, 31, 64]))
        add("blocks", d["src"], opt_args(p, dict(d, just=False), rng), visible=(i == 0))
    other = "*" if p["bullet"] != "*" else "+"
    add("blocks", "\n".join(["# Title", "##    Spaced   out  ", "### Third level heading that is long enough to wrap around", "#### not a heading", "#hash", "@figure a 2", "@figure  b-1   3 ",
                             "> quote  with   spacing", ">tight", ">   wide", ">", "", f"{p['bullet']} one", f"{p['bullet']} two", "  continues here", "", f"{p['bullet']} three", "tail text", f"{other} not an item"]) + "\n", [])
    add("blocks", f"{p['bullet']} first item\n{p['bullet']} second item that wraps because it is long enough for that\n  and has a continuation line\n    and another\n\n{p['bullet']} loose item\n{p['bullet']} tight again\npara after items\n"
        f"{p['bullet']} item after para\n{p['bullet']}glued\n", ["--width", "24"])
    add("blocks", "para one\n> quote\nmore para?\n# heading\ntext\n## sub\n- x\n* y\n+ z\n", ["--height", "40"])
    add("blocks", f"> a\n>\n> b\n\n>\n\n{p['bullet']} x\n", ["--width", "12"])
    add("blocks", "\n".join(["@figure map 3", "@figure plot 1", "", "@figure big 9", "text", "@break", "@break", "@break", "text after breaks"]) + "\n", ["--height", "20"])
    heads = "\n\n".join(["# the first heading of the document that is long", "## second level heading with many words in it", "### third level heading with many words in it too"]) + "\n"
    add("blocks", heads, ["--width", "16", "--height", "40"])
    add("blocks", heads, ["--width", "40", "--height", "40"])

    # ---- justify
    if p["just"]:
        for i in range(5):
            lines = g.blocks(rng.randint(3, 6), 3, {"para": 4, "quote": 2, "items": 2, "heading": 1}, longp=0.06)
            d = cand(lines, h=80, w=rng.choice([p["width"], 22, 29, 45, 70]), just=True)
            add("justify", d["src"], opt_args(p, d, rng))
        add("justify", "a b c d e f g h i j k l m n o p q r s t u v w x y z\n", ["--width", "11", "--justify"])
        add("justify", "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi\n> alpha beta gamma delta epsilon zeta eta theta iota\n" + p["bullet"] + " alpha beta gamma delta epsilon zeta eta theta iota kappa\n", ["--width", "18", "--justify"])
        add("justify", "supercalifragilisticexpialidocious is a long word and so is antidisestablishmentarianism ok\n", ["--width", "15", "--justify"])

    # ---- pagination, guided: the widow/orphan rules or the keep rule change the answer
    mk = lambda: cand(g.blocks(rng.randint(8, 16), 5, MIX_PAGES, longp=0.03, breaks=0.0), h=rng.randint(7, 24), w=rng.choice([p["width"], p["width"], 26, 34, 48]), o=rng.randint(1, 4), wd=rng.randint(1, 4),
                      just=p["just"] and rng.random() < 0.4)
    pick_pages = choose(mk, "orphan", 3, minpages=3) + choose(mk, "widow", 3, minpages=3)
    # a small document to show in the README
    small = None
    for _ in range(200):
        lines = g.blocks(rng.randint(2, 4), 3, {"heading": 2, "para": 4, "items": 1}, breaks=0.0)
        d = cand(lines, h=rng.randint(6, 9), w=rng.choice([p["width"], 28, 24]), o=p["orphans"], wd=p["widows"])
        f = probed([d])[0]
        if f and not f["tall"] and 2 <= f["pages"] <= 3 and f["lines"] <= 26 and (f["orphan"] or f["widow"] or f["keep"]):
            small = d
            break
    if small is None:
        raise K.BuildError("typeset: no small paging example")
    add("pages", small["src"], opt_args(p, small, rng) if (small["h"] != p["height"] or small["w"] != p["width"]) else ["--height", str(small["h"])], visible=True)
    for d in pick_pages:
        add("pages", d["src"], opt_args(p, d, rng))
    for d in valid(lambda: cand(g.blocks(rng.randint(10, 18), 6, MIX_PAGES, longp=0.03), h=rng.randint(8, 30), w=rng.choice([p["width"], 30, 52])), 3):
        add("pages", d["src"], opt_args(p, d, rng))

    # ---- keep with next / headings at the bottom of a page
    mkh = lambda: cand(g.blocks(rng.randint(8, 16), 4, MIX_HEADS, breaks=0.04), h=rng.randint(7, 20), w=rng.choice([p["width"], 28, 36, 50]), o=rng.randint(1, 3), wd=rng.randint(1, 3))
    group = "keep" if p["keep"] else "headings"
    for d in choose(mkh, "keep", 6 if p["keep"] else 5, minpages=2):
        add(group, d["src"], opt_args(p, d, rng))
    for lines, args in [
        (["# A", "## B", "### C", "text under the chain of headings"], ["--height", "5"]),
        (["para " * 5, "", "# Last heading"], ["--height", "4"]),
        (["# A", "", "@break", "", "text"], ["--height", "6"]),
        (["text one two three four five six seven eight nine ten", "", "# Heading", "", "@figure f 3", "", "tail"], ["--height", "8", "--width", "20"]),
    ]:
        add(group, text_of(lines), args)

    # ---- widows and orphans, deterministic scenarios
    base = " ".join(["w%d" % i for i in range(1, 60)])  # a paragraph of known length
    for h, o, wd in [(5, 2, 2), (5, 3, 3), (4, 4, 4), (6, 1, 4), (7, 4, 1), (9, 3, 2), (4, 1, 1)]:
        add("widows", text_of(["short", "", base, "", "tail para", "", base]), ["--width", "30", "--height", str(h), "--orphans", str(o), "--widows", str(wd)])
    for d in choose(lambda: cand(g.blocks(rng.randint(7, 12), 3, {"para": 5, "items": 3, "quote": 2, "heading": 1}), h=rng.randint(5, 12), w=rng.choice([20, 28, 40]), o=rng.randint(2, 4), wd=rng.randint(2, 4)), "widow", 4, minpages=3):
        add("widows", d["src"], opt_args(p, d, rng))

    # ---- page breaks and figures
    for i in range(5):
        lines = g.blocks(rng.randint(6, 12), 6, {"para": 3, "figure": 3, "heading": 2, "items": 1, "break": 1.2}, breaks=0.1)
        d = cand(lines, h=rng.randint(8, 18), w=rng.choice([p["width"], 30]), o=rng.randint(1, 3), wd=rng.randint(1, 3))
        f = probed([d])[0]
        if f is None or f["tall"]:
            d = cand(g.blocks(8, 3, {"para": 3, "figure": 2, "break": 1}), h=12)
        add("breaks", d["src"], opt_args(p, d, rng))
    add("breaks", "@break\n@break\n\ntext\n\n@break\n", ["--height", "6"])
    add("breaks", "@break\n", [])
    add("breaks", "@figure a 4\n@figure b 4\n@figure c 4\n@figure d 1\n", ["--height", "9"])
    add("breaks", "text\n\n@figure a 5\n\ntext\n", ["--height", "7"])
    add("breaks", "@figure a 5\n", ["--height", "5"])
    add("breaks", "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron\n\n@break\n", ["--width", "20", "--height", "5"])

    # ---- options
    base_doc = "# Title\n\nSome text for the options checks, long enough to wrap in narrow pages.\n\n- item one\n- item two\n"
    sets = [
        ["--width", "25"], ["--height", "5"], ["--orphans", "3", "--widows", "1"], ["--width", "20", "--width", "30"], ["--width", "040"], ["--height", "004"],
        ["--widows", "4", "--orphans", "4", "--height", "20"], ["--width", "120", "--height", "80"], ["--width", "10", "--height", "4", "--orphans", "1", "--widows", "1"],
    ]
    if p["just"]:
        sets += [["--justify"], ["--justify", "--width", "22"], ["--width", "22", "--justify", "--justify"]]
    for a in sets:
        add("options", base_doc, a)
    bad = [
        ["--width", "9"], ["--width", "121"], ["--width", "1000"], ["--width", "x"], ["--width", "-5"], ["--width", "+20"], ["--width", ""], ["--width", "2.5"],
        ["--height", "3"], ["--height", "81"], ["--orphans", "0"], ["--orphans", "5"], ["--widows", "0"], ["--widows", "5"], ["--widows", "one"],
        ["--width"], ["--height"], ["--orphans"], ["--widows"], ["--width", "30", "--height"],
        ["--width", "--height", "10"], ["--bogus"], ["--width=30"], ["width", "30"], ["-w", "30"], ["extra"], ["--WIDTH", "30"],
        ["--width", "30", "--unknown", "--height", "99"], ["--height", "99", "--bogus"], ["--orphans", "9", "--width"],
    ]
    bad.append(["--justify"] if not p["just"] else ["--justify", "now"])
    if p["just"]:
        bad.append(["--width", "--justify"])
    for a in bad:
        add("options", base_doc, a)
    add("options", "@figure oops\n", ["--width", "0"])  # an option error wins over a document error
    add("options", "", ["--height", "7"])

    # ---- document errors
    errs = [
        ["text", "@figure", "more"], ["@figure a"], ["@figure a 0"], ["@figure a 100"], ["@figure a b"], ["@figure a 3 x"], ["@figures x 3"], ["@figure x\t3"], ["@figure bad!name 3"],
        ["@figure  ok   2", "", "@figure ok 03"], ["@figure x 3 ", "", "@figure y 2  "], ["# Fine", "", "#", "", "@figure"], ["# ", "text"], ["text", "##   ", "more"],
        ["@figure a 20", "", "@figure b"], ["@figure a 12", "@figure b 6", "", "text"], ["", "", "@figure tall 9", "", "# H"], ["@figure a 8", "# ", "@figure b 9"],
    ]
    for i, lines in enumerate(errs):
        args = [] if i % 3 else ["--height", "8"]
        add("errors", text_of(lines), args, visible=(i == 1))
    add("errors", "#### x\n#tag\n@ x\n# real\n", ["--height", "5"])
    add("errors", "@figure a 5\n@figure b 6\n", ["--height", "5"])

    # ---- mixed documents with random options
    for i in range(10):
        lines = g.blocks(rng.randint(12, 28), 7, MIX_ALL, longp=0.04, breaks=0.04)
        d = cand(lines, h=rng.randint(8, 40), w=rng.choice([p["width"], 24, 30, 44, 72]), o=rng.randint(1, 4), wd=rng.randint(1, 4), just=p["just"] and rng.random() < 0.5)
        f = probed([d])[0]
        if f is None or f["tall"]:
            d["h"] = 40
        add("mixed", d["src"], opt_args(p, d, rng))
    return cases


@family("project-typeset", category="project", lang="rust", kind="greenfield", n=8,
        summary="a line-printer typesetter: markup reading, greedy wrapping and justification, underlined headings, quotes, tight/loose lists, figures, pagination with orphan/widow control and keep-with-next headings")
def gen(rng, n):
    for i in range(n):
        plan = dict(PLAN[i])
        tool = TOOLS[i]
        lang = plan.pop("lang")
        p = dict(plan)
        cfg = dict(WIDTH=p["width"], HEIGHT=p["height"], ORPHANS=p["orphans"], WIDOWS=p["widows"], KEEP=p["keep"], JUSTIFY_OPT=p["just"], UPPER_H1=p["upper"],
                   UL1=p["ul"][0], UL2=p["ul"][1], UL3=p["ul"][2], QUOTE=p["quote"], BULLET=p["bullet"], ITEM_OUT=p["item_out"], LONG_WORD=p["long"])
        py_sol = K.merged(K.load_src(THEME, "python", tool), K.render_config("python", cfg))
        sol = py_sol if lang == "python" else K.merged(K.load_src(THEME, lang, tool), K.render_config(lang, cfg))
        cases = make_cases(p, tool, rng, py_sol)
        prompt = VOICES[i % len(VOICES)].format(tool=tool, Lang=K.LANG_NAME[lang], run=K.how_to_run(lang, tool), num=7300 + i * 23)
        nfeat = sum([p["keep"], p["just"], p["orphans"] > 1 or p["widows"] > 1, p["long"] == "cut", p["upper"]])
        yield K.project_task(
            theme=THEME, tool=tool, lang=lang, cases=cases, solution=sol, py_solution=py_sol,
            readme=lambda by_name, p=p, tool=tool, lang=lang: readme(p, tool, lang, by_name),
            prompt=prompt, difficulty=3 if nfeat <= 1 else (4 if nfeat <= 4 else 5), slug=f"{i + 1:02d}-{tool}-{'keep' if p['keep'] else 'free'}-{lang}",
            notes={k_: v for k_, v in p.items() if k_ != "ul"} | {"ul": "".join(p["ul"])}, tags=["text", "layout"],
        )
