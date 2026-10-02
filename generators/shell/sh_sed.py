"""Shell tasks: sed scripts with exact expected output (GNU sed 4.9): redaction, continuation lines, sections, hold-space tricks, tails, link rewriting."""
from fx import dd, family
from generators.shell import _shkit as K
from generators.shell._shkit import D, F, L, Run, scn

S = K.ShellSpec
NOTE = " The tests run GNU sed 4.9."


def lines(rows):
    return "".join(r + "\n" for r in rows)


# ------------------------------------------------------------------------------------------------ 1. redaction

REF_REDACT = dd('''
    s/([A-Za-z0-9._+-]+)@([A-Za-z0-9-]+(\\.[A-Za-z0-9-]+)*\\.[A-Za-z]{2,})/***@\\2/g
    s/\\(([0-9]{3})\\) [0-9]{3}-[0-9]{4}/(XXX) XXX-XXXX/g
''')


def make_redact(rng):
    ex = scn("example", {}, Run(stdin="mail ann@example.org or call (555) 123-4567\n"))
    txt = lines(["Contact: j.doe+news@mail.example.co.uk, bob_1@x-y.io; phone (020) 555-0100.", "no pii here: @handle and name@ and (12) 345-6789", "two: a@b.com b@c.org (111) 222-3333 (444) 555-6666",
                 "edge: <x@y.zz> \"q@r.st\" a@b.c", "dots a..b@dom.com", "UPPER@HOST.COM"])
    return ex, [scn("mixed lines", {}, Run(stdin=txt)), scn("empty", {}, Run(stdin=""))]


# ------------------------------------------------------------------------------------------------ 2. continuation lines

REF_UNWRAP = dd('''
    :a
    /\\\\$/{
    N
    s/\\\\\\n[ \\t]*//
    ba
    }
''')


def make_unwrap(rng):
    ex = scn("example", {}, Run(stdin="gcc -o app \\\n    main.c \\\n    util.c\necho done\n"))
    txt = "plain line\nlong command \\\n   --with-option=1 \\\n\t--other \\\nlast piece\n\nsingle \\\nnext\nends with backslash \\\n"
    return ex, [scn("continuations", {}, Run(stdin=txt)), scn("nothing to join", {}, Run(stdin="a\nb\n\nc\n")), scn("only backslash line", {}, Run(stdin="\\\n\\\nx\n"))]


# ------------------------------------------------------------------------------------------------ 3. ini section

REF_SECTION = dd('''
    /^\\[server\\]$/,/^\\[/{
    /^\\[/!p
    }
''')


def make_section(rng):
    ex = scn("example", {}, Run(stdin="[a]\nx=1\n[server]\nport=80\nhost=h\n[b]\ny=2\n"))
    ini = "# top comment\nname=top\n\n[client]\ntimeout=5\n\n[server]\n# listen\nport=8080\n\nworkers = 4\n[servers]\nnot=this\n[ server ]\nnor=this\n[server]\nagain=yes\n[last]\nz=1\n"
    return ex, [scn("sections", {}, Run(stdin=ini), Run(stdin="[server]\nonly=1\n"), Run(stdin="[x]\na=1\n")), scn("empty", {}, Run(stdin=""), Run(stdin="[server]\n[other]\n"))]


# ------------------------------------------------------------------------------------------------ 4. swap names

REF_SWAP = dd('''
    s/^Name: ([^,]+), (.+) (\\([^)]*\\))$/Name: \\2 \\1 \\3/
    t
    s/^Name: ([^,]+), (.+)$/Name: \\2 \\1/
''')


def make_swap(rng):
    ex = scn("example", {}, Run(stdin="Name: Doe, Jane (Dr)\nName: Roe, Rick\nNote: Hello, there\n"))
    txt = lines(["Name: Okafor-Smith, Ngozi Ada (Prof)", "Name: de la Cruz, Ana Maria", "Name: O'Neil, Pat (they/them)", "Name: Solo", "Name: , nobody", "name: Lower, Case", "  Name: Indented, Ivy",
                 "Name: Last, First (A) (B)", "Name: Zed, Zoe ()", "Other: A, B", "Name: A, B, C"])
    return ex, [scn("name variants", {}, Run(stdin=txt)), scn("empty", {}, Run(stdin=""))]


# ------------------------------------------------------------------------------------------------ 5. adjacent duplicates

REF_ADJ = dd('''
    $!N
    /^\\(.*\\)\\n\\1$/!P
    D
''')


def make_adj(rng):
    ex = scn("example", {}, Run(stdin="a\na\nb\nb\nb\na\n"))
    txt = lines(["x", "x", "x", "y", "", "", "z", "z", "x", "x ", "x", "  ", "  ", "w"])
    return ex, [scn("runs", {}, Run(stdin=txt), Run(stdin="solo\n"), Run(stdin="same\nsame\n"), Run(stdin="")), scn("no trailing newline", {}, Run(stdin="a\na\nb"))]


# ------------------------------------------------------------------------------------------------ 6. paragraphs on one line

REF_PARA = dd('''
    /^$/d
    :a
    $!{
    N
    /\\n$/!ba
    }
    s/\\n$/\\x01/
    s/\\n/ /g
    /\\x01$/!s/$/\\x01/
    s/\\x01/\\n/
''')


def make_para(rng):
    ex = scn("example", {}, Run(stdin="one\ntwo\n\nthree\n"))
    txt = "first line\nsecond line\nthird\n\n\nsecond para\nhas two lines\n\n  indented start\nend  \n\nlast alone\n"
    return ex, [scn("paragraphs", {}, Run(stdin=txt), Run(stdin="a\n\nb\n\nc\n"), Run(stdin="\n\nonly\n\n\n")), scn("edge", {}, Run(stdin="x\ny\n"), Run(stdin=""))]


# ------------------------------------------------------------------------------------------------ 7. trim

REF_TRIM = dd('''
    s/^[[:space:]]+//
    s/[[:space:]]+$//
    s/[[:space:]]+/ /g
    /^$/{
    x
    s/^N$/P/
    x
    d
    }
    x
    /^P$/{
    s/.*/N/
    x
    s/^/\\n/
    b
    }
    s/.*/N/
    x
''')


def make_trim(rng):
    ex = scn("example", {}, Run(stdin="\n\n  hello    world  \n\n\n\nbye\n\n"))
    txt = "   \n\t\n  first   line\twith\ttabs  \n\n   \n\nsecond  line\n  \n\n\nthird\n\n\n   \n"
    return ex, [scn("messy text", {}, Run(stdin=txt), Run(stdin="  x  \n"), Run(stdin="x\n\ny\n")), scn("blank only and empty", {}, Run(stdin="\n\n  \n"), Run(stdin=""))]


# ------------------------------------------------------------------------------------------------ 8. csv quoting

REF_QCSV = dd('''
    s/"/""/g
    s/^/"/
    s/$/"/
    s/,/","/g
''')


def make_qcsv(rng):
    ex = scn("example", {}, Run(stdin="a,b c,d\n"))
    txt = lines(["id,name,note", "1,Ann,says \"hi\"", "2,,", "3, padded ,x", "", "solo", ",lead", "trail,", "q\"q,\"\""])
    return ex, [scn("lines", {}, Run(stdin=txt)), scn("empty", {}, Run(stdin=""))]


# ------------------------------------------------------------------------------------------------ 9. markdown links

REF_MDLINK = dd('''
    s/!\\[/\\x01[/g
    s/\\[([^]]+)\\]\\(([^)]+)\\)/\\1 <\\2>/g
    s/\\x01\\[/![/g
''')


def make_mdlink(rng):
    ex = scn("example", {}, Run(stdin="see [the docs](https://example.org/docs) now\n"))
    txt = lines(["[a](b) and [c d](e/f) twice", "image ![logo](img/logo.png) stays, link [here](x) goes", "no link [text] (not a link) [x]", "[empty]()", "nested [a [b]](c)", "end [z](y)", "![only](image)", "[one](1)[two](2)"])
    return ex, [scn("links", {}, Run(stdin=txt)), scn("empty", {}, Run(stdin=""))]


# ------------------------------------------------------------------------------------------------ 10. last three lines

REF_TAIL = dd('''
    :a
    $q
    N
    4,$D
    ba
''')


def make_tail(rng):
    ex = scn("example", {}, Run(stdin="1\n2\n3\n4\n5\n"))
    return ex, [scn("lengths", {}, Run(stdin=lines(str(i) for i in range(1, 12))), Run(stdin="a\nb\nc\n"), Run(stdin="a\nb\n"), Run(stdin="a\n"), Run(stdin=""), Run(stdin="x\ny\nz\nw")),
                scn("blank and odd lines", {}, Run(stdin="\n\nkeep\n\nlast two\n  \n"))]


# ------------------------------------------------------------------------------------------------ 11. fix: strip tags

BUG_TAGS = dd('''
    s/<.*>//g
    s/&nbsp;/ /g
    s/&amp;/\\&/g
    s/&lt;/</g
    s/&gt;/>/g
''')
REF_TAGS = dd('''
    s/<[^>]*>//g
    s/&nbsp;/ /g
    s/&lt;/</g
    s/&gt;/>/g
    s/&amp;/\\&/g
''')


def make_tags(rng):
    ex = scn("example", {}, Run(stdin="<p>Fish &amp; <b>chips</b></p>\n"))
    txt = lines(["<h1>Title</h1> text <a href=\"x\">link</a> tail", "plain &amp;lt; stays &lt;", "a&nbsp;b &gt; c &amp; d", "<br/>", "no tags", "<p class=\"a b\">x</p><p>y</p>", "&amp;amp;"])
    return ex, [scn("html lines", {}, Run(stdin=txt)), scn("empty", {}, Run(stdin=""))]


# ------------------------------------------------------------------------------------------------ 12. rename identifier

REF_RENAME = dd('''
    s/\\bold_name\\b/new_name/g
''')


def make_rename(rng):
    ex = scn("example", {}, Run(stdin="x = old_name + 1\n"))
    txt = lines(["old_name = old_name2 + x_old_name", "call(old_name)", "old_name.field; old_name_ ; _old_name; old-name; OLD_NAME", "# old_name in a comment", "old_name old_name old_name", "xold_name", "old_name9"])
    return ex, [scn("identifiers", {}, Run(stdin=txt)), scn("empty", {}, Run(stdin=""))]


SPECS = [
    S("redact-emails-phones", 2,
      "Write `redact.sed`: mask the local part of e-mail addresses and the digits of phone numbers in text. The README gives the exact patterns." + NOTE,
      "`sed -E -f redact.sed` reads text on standard input and writes it back with every e-mail address `LOCAL@DOMAIN` rewritten to `***@DOMAIN` and every phone number of the form `(ddd) ddd-dddd` rewritten to `(XXX) XXX-XXXX`, everything else unchanged. "
      "`LOCAL` is one or more of `A-Za-z0-9._+-`; `DOMAIN` consists of labels of `A-Za-z0-9-` separated by dots and ends in a dot plus at least two letters (`a@b.c` is not an address). Several matches per line must all be replaced.",
      REF_REDACT, make_redact, script="redact.sed", runner=("sed", "-E", "-f"), title="Redact e-mails and phone numbers", wrong=("s/@.*//\n",)),
    S("join-continuation-lines", 3,
      "Write `unwrap.sed` which joins shell-style continuation lines (a trailing backslash) into single lines." + NOTE,
      "`sed -f unwrap.sed` reads text on standard input. Whenever a line ends with a backslash, remove that backslash and the line break after it, as well as the leading blanks (spaces and tabs) of the following line, and repeat for the joined line (several continuations in a row). "
      "A last line that ends with a backslash but has no following line stays as it is. Lines without a trailing backslash are printed unchanged.",
      REF_UNWRAP, make_unwrap, script="unwrap.sed", runner=("sed", "-f"), title="Join continuation lines", wrong=("s/\\\\$//\n",)),
    S("ini-section-body", 3,
      "Write `section.sed`: print the body of the `[server]` section of an INI file." + NOTE,
      "`sed -n -f section.sed` reads an INI file on standard input and prints every line that belongs to a section whose header line is exactly `[server]` (all lines after the header up to, not including, the next line that starts with `[`, or to the end of the file), "
      "the header itself excluded; comments and blank lines inside the section are printed too. If the section appears several times all bodies are printed in order. Headers like `[servers]` or `[ server ]` are different sections.",
      REF_SECTION, make_section, script="section.sed", runner=("sed", "-n", "-f"), title="INI section body", wrong=("/^\\[server\\]$/,/^\\[/p\n",)),
    S("surname-first-to-given-first", 3,
      "Write `swap.sed` that rewrites `Name: Surname, Given (Title)` lines as `Name: Given Surname (Title)`." + NOTE,
      "`sed -E -f swap.sed` rewrites every line of the form `Name: SURNAME, GIVEN` or `Name: SURNAME, GIVEN (TITLE)` into `Name: GIVEN SURNAME` / `Name: GIVEN SURNAME (TITLE)`. `SURNAME` is the text up to the **first** comma (non-empty, so it contains no comma), `GIVEN` is everything after `, ` "
      "up to the optional title, which is the last parenthesised group at the very end of the line, preceded by a space. Lines that do not start with `Name: ` or have no comma after a non-empty surname are unchanged.",
      REF_SWAP, make_swap, script="swap.sed", runner=("sed", "-E", "-f"), title="Surname first to given first", wrong=("s/^Name: ([^,]+), (.+)$/Name: \\2 \\1/\n",)),
    S("squeeze-adjacent-duplicates", 3,
      "Write `adjacent.sed`, a sed-only version of `uniq`: drop a line when it is identical to the line just before it." + NOTE,
      "`sed -f adjacent.sed` prints the standard input with every line removed that is exactly equal to the previous line (so `a a a b a` becomes `a b a`; lines that differ in a trailing space are different). Blank lines are lines too. A final line without trailing newline is handled like any other.",
      REF_ADJ, make_adj, script="adjacent.sed", runner=("sed", "-f"), title="sed uniq", wrong=("p\n",)),
    S("paragraphs-to-single-lines", 4,
      "Write `paragraphs.sed` that turns every paragraph (a block of consecutive non-empty lines) into one line, words separated by single spaces, and puts one blank line after each." + NOTE,
      "`sed -f paragraphs.sed` reads text on standard input. Paragraphs are separated by one or more empty lines (lines with no characters at all). Each paragraph becomes a single line made of its lines joined with one space (the lines are otherwise unchanged: do not trim them). "
      "Every output paragraph is followed by exactly one empty line (so the output ends with an empty line); empty lines at the start of the input and surplus empty lines between paragraphs produce no output. The test inputs end with a newline.",
      REF_PARA, make_para, script="paragraphs.sed", runner=("sed", "-f"), title="Paragraphs on one line", wrong=("s/$/ /\n",)),
    S("trim-and-squeeze-text", 4,
      "Write `clean.sed` to tidy text: trim every line, squeeze inner blanks, collapse runs of blank lines and drop blank lines at the start and the end." + NOTE,
      "`sed -E -f clean.sed` processes standard input as follows: remove leading and trailing whitespace of every line, replace every run of whitespace (blanks and tabs) inside a line by a single space, "
      "then collapse any run of blank lines (lines empty after trimming) into one blank line, and delete all blank lines at the very beginning and at the very end of the text. Nothing else changes.",
      REF_TRIM, make_trim, script="clean.sed", runner=("sed", "-E", "-f"), title="Tidy text", wrong=("s/^[[:space:]]+//\ns/[[:space:]]+$//\n",)),
    S("quote-every-csv-field", 2,
      "Write `quote.sed` to wrap every comma-separated field of every line in double quotes, doubling quotes that are already inside." + NOTE,
      "`sed -f quote.sed` reads simple comma separated lines (no commas inside fields) and writes each field enclosed in double quotes, a double quote inside a field doubled: `he said \"hi\",x` becomes `\"he said \"\"hi\"\"\",\"x\"`. Empty fields become `\"\"`, and so does an empty line. Whitespace is kept as is.",
      REF_QCSV, make_qcsv, script="quote.sed", runner=("sed", "-f"), title="Quote CSV fields", wrong=("s/^/\"/\ns/$/\"/\n",)),
    S("markdown-links-to-text", 3,
      "Write `links.sed` converting Markdown links `[text](url)` to `text <url>` but leaving images (`![alt](src)`) alone." + NOTE,
      "`sed -E -f links.sed` rewrites every inline link `[TEXT](URL)` (`TEXT` and `URL` non-empty, no `]` in the text, no `)` in the url) to `TEXT <URL>`, all occurrences on a line. An image `![ALT](SRC)` (the `[` is directly preceded by `!`) is not a link and stays exactly as written. "
      "Anything that does not match the link shape (`[x]`, `[empty]()`, text in brackets followed by a space and parentheses) is untouched.",
      REF_MDLINK, make_mdlink, script="links.sed", runner=("sed", "-E", "-f"), title="Markdown links to plain text", wrong=("s/\\[(.*)\\]\\((.*)\\)/\\1 <\\2>/g\n",)),
    S("last-three-lines", 4,
      "Write `tail3.sed`: print only the last three lines of the input, using sed alone." + NOTE,
      "`sed -f tail3.sed` prints the last three lines of standard input (all of them if there are fewer than three), like `tail -n 3`, without reading the whole input into memory at once (a sliding window); a final line without trailing newline stays without one, as GNU sed does.",
      REF_TAIL, make_tail, script="tail3.sed", runner=("sed", "-f"), title="sed tail", wrong=("$p\n",)),
    S("fix-strip-html-tags", 2,
      "`strip.sed` should remove HTML tags and decode a few entities, but it deletes everything between the first `<` and the last `>` on a line and mis-decodes `&amp;lt;`. Fix it." + NOTE,
      "`sed -E -f strip.sed` removes every tag (`<`, then anything except `>`, then `>`) from each line and decodes the entities `&nbsp;` (to a space), `&lt;`, `&gt;` and `&amp;` exactly once: the text `&amp;lt;` must become `&lt;`, not `<`. Text that is not part of a tag stays unchanged.",
      REF_TAGS, make_tags, script="strip.sed", runner=("sed", "-E", "-f"), buggy=BUG_TAGS, title="Strip HTML tags", wrong=(BUG_TAGS,)),
    S("rename-identifier-whole-word", 2,
      "Write `rename.sed` to rename the identifier `old_name` to `new_name` in source text, but only where it is a whole identifier." + NOTE,
      "`sed -f rename.sed` replaces every occurrence of `old_name` that is a whole word by `new_name`; `old_name2`, `x_old_name`, `_old_name`, `old_name_` and `OLD_NAME` are other identifiers and stay. A dot, parenthesis or hyphen next to it counts as a word boundary. Everything else is unchanged.",
      REF_RENAME, make_rename, script="rename.sed", runner=("sed", "-f"), title="Rename an identifier", wrong=("s/old_name/new_name/g\n",)),
]


@family("shell-sed-scripts", category="shell", lang="bash", kind="feature", n=len(SPECS),
        summary="sed scripts with exact output: redaction, continuation lines, INI sections, hold space, tails, Markdown links, whole-word renames")
def sed_scripts(rng, n):
    return K.shell_tasks("sed-scripts", SPECS, rng, n)
