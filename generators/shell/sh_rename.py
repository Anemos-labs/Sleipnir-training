"""Shell tasks: batch renaming with awkward file names (spaces, dashes, unicode, globs, collisions, cycles)."""
from fx import dd, family
from generators.shell import _shkit as K
from generators.shell._shkit import D, F, L, Run, scn

S = K.ShellSpec


def content(name):
    return f"payload of {name}\n"


def files_of(names, **kw):
    return {n: F(content(n), **kw) for n in names}


def cmp_oracle(exp_out, exp_tree, res, tree, rc=0):
    p = []
    if res[-1]["stdout"] != exp_out:
        p.append(f"stdout {res[-1]['stdout']!r} != {exp_out!r}")
    if tree != exp_tree:
        p.append(f"tree differs: {sorted(set(tree) ^ set(exp_tree))[:4]}")
    if res[-1]["rc"] != rc:
        p.append(f"rc {res[-1]['rc']}")
    return p


def move(tree, a, b):
    tree[b] = tree.pop(a)


# ------------------------------------------------------------------------------------------------ 1. lowercase extensions

REF_LOWER = dd('''
    #!/usr/bin/env bash
    # Lowercase the extension of every regular file in the current directory.
    shopt -s nullglob dotglob
    for f in *; do
      [ -f "$f" ] && [ ! -L "$f" ] || continue
      case $f in
        *.*) ;;
        *) continue ;;
      esac
      base=${f%.*}
      ext=${f##*.}
      [ -n "$base" ] || continue
      lower=$(printf '%s' "$ext" | tr 'A-Z' 'a-z')
      [ "$ext" = "$lower" ] && continue
      new=$base.$lower
      if [ -e "$new" ] || [ -L "$new" ]; then
        echo "exists: $f"
        continue
      fi
      mv -- "$f" "$new"
    done
''')


def make_lower(rng):
    ex = scn("example", files_of(["Holiday Photo.JPG", "notes.TXT", "-weird.PNG", "README", "photo.jpg", "Draft.Docx"]), Run())
    pool = ["my vacation.JPG", "-dash.Png", "naïve café.TXT", "star*.Md", "q?mark.GIF", "it's.Txt", "tab\there.LOG", "[brackets].CSV", "dollar$HOME.TXT",
            "semi;colon.Pdf", "ünï-çødé.JPEG", "(parens).TXT", "a&b.Zip", "#hash.TXT", "~tilde.TXT", "UPPER.TXT", "already.txt", "noext", "trailing.", "multi.dot.TAR.GZ"]
    a = rng.sample(pool, 12)
    b = {**files_of(["Report.TXT", "report.txt", ".Hidden.LOG", "noext", ".bashrc", "Data.CSV", "data.csv", "Photo.JPG"]),
         "Subdir.D/Inner.TXT": F(content("inner")), "Link.TXT": L("report.txt"), "Other Dir": D()}
    return ex, [
        scn("awkward names", files_of(a), Run()),
        scn("collisions and hidden files", b, Run(), dirs="all"),
        scn("nothing to do", files_of(["a.txt", "b.md", "plain"]), Run()),
        scn("empty directory", {}, Run()),
    ]


def oracle_lower(s, res, tree):
    files = s["files"]
    cur = dict(files)
    out = []
    for n in sorted(k for k, e in files.items() if "/" not in k and e["t"] == "f"):
        if "." not in n:
            continue
        base, _, ext = n.rpartition(".")
        low = "".join(c.lower() if "A" <= c <= "Z" else c for c in ext)
        if not base or low == ext:
            continue
        new = base + "." + low
        if new in cur:
            out.append("exists: " + n)
            continue
        move(cur, n, new)
    return cmp_oracle("".join(l + "\n" for l in out), {k: v for k, v in cur.items() if v["t"] != "d" or True} if False else {k: v for k, v in cur.items()}, res, tree) if False else _o_lower(cur, out, res, tree)


def _o_lower(cur, out, res, tree):
    exp = {k: v for k, v in cur.items() if not (v["t"] == "d" and k.endswith("/"))}
    got = {k: v for k, v in tree.items()}
    probs = []
    if res[-1]["stdout"] != "".join(l + "\n" for l in out):
        probs.append("stdout differs")
    names = lambda t: {k: (v.get("c"), v.get("to")) for k, v in t.items() if v["t"] != "d"}
    if names(exp) != names(got):
        probs.append("files differ")
    return probs


# ------------------------------------------------------------------------------------------------ 2. zero padding

REF_PAD = dd('''
    #!/usr/bin/env bash
    # Pad the first run of digits in every file name to four digits.
    shopt -s nullglob
    for f in *; do
      [ -f "$f" ] || continue
      if [[ $f =~ ^([^0-9]*)([0-9]+)(.*)$ ]]; then
        pre=${BASH_REMATCH[1]}
        num=${BASH_REMATCH[2]}
        post=${BASH_REMATCH[3]}
        [ "${#num}" -lt 4 ] || continue
        new=$pre$(printf '%04d' "$((10#$num))")$post
        if [ -e "$new" ]; then
          echo "conflict: $f"
          continue
        fi
        mv -- "$f" "$new"
      fi
    done
''')


def make_pad(rng):
    ex = scn("example", files_of(["img_7.png", "img_12.png", "chart-3-final.png", "notes.txt", "take 5.wav"]), Run())
    a = ["scan 3.pdf", "scan 10.pdf", "scan 118.pdf", "-4-up.txt", "frame_0009.png", "v2 draft (copy 3).doc", "x9y10.dat", "cover.jpg", "été 5.txt", "it's 6.txt", "007 bond.txt", "12345.bin", "pad_0.txt"]
    b = ["img_7.png", "img_0007.png", "img_12.png", "take 5.wav", "take 05.wav"]
    return ex, [scn("awkward names", files_of(a), Run()), scn("conflicts", files_of(b), Run()),
                scn("leading zeros kept in value", files_of(["a00001.txt", "b0.txt", "c00.txt", "d000.txt"]), Run()),
                scn("directories are not files", {**files_of(["7.txt"]), "8/9.txt": F("deep\n"), "10": D()}, Run(), dirs="all")]


def oracle_pad(s, res, tree):
    import re
    cur = dict(s["files"])
    out = []
    for n in sorted(k for k, e in s["files"].items() if "/" not in k and e["t"] == "f"):
        m = re.match(r"^([^0-9]*)([0-9]+)(.*)$", n, re.S)
        if not m or len(m.group(2)) >= 4:
            continue
        new = m.group(1) + "%04d" % int(m.group(2)) + m.group(3)
        if new in cur:
            out.append("conflict: " + n)
            continue
        move(cur, n, new)
    return _o_lower(cur, out, res, tree)


# ------------------------------------------------------------------------------------------------ 3. date prefix

REF_DATE = dd('''
    #!/usr/bin/env bash
    # Prefix every regular file with the UTC date of its last modification, unless it already starts with a date.
    shopt -s nullglob
    for f in *; do
      [ -f "$f" ] || continue
      case $f in
        [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]_*) continue ;;
      esac
      d=$(date -u -r "$f" +%F)
      mv -- "$f" "${d}_$f"
    done
''')


def make_date(rng):
    # 1700000000 = 2023-11-14 22:13:20 UTC
    ex = scn("example", {"holiday.txt": F(content("h"), m=1700000000), "-notes": F(content("n"), m=1700100000), "2031-01-01_old.txt": F(content("o"), m=1700000000)}, Run())
    day = 86400
    a = {"two words.txt": F(content("1"), m=1700000000), "late night.log": F(content("2"), m=1700000000 + day - 1 - 80000),
         "midnight.dat": F(content("3"), m=1700000000 + 6000 + 1), "-rf": F(content("4"), m=1735689599), "it's here": F(content("5"), m=1735689600),
         "naïve.txt": F(content("6"), m=951782400), "2020-02-30_bad.txt": F(content("7"), m=1700000000), "2020-02-29_ok.txt": F(content("8"), m=1700000000)}
    b = {"x.txt": F("1\n", m=1709251199), "y.txt": F("2\n", m=1709251200), "z.txt": F("3\n", m=1709164800), "sub/inner.txt": F("4\n", m=1700000000)}
    return ex, [scn("awkward names", a, Run()), scn("day boundaries (leap day)", b, Run(), dirs="all"), scn("empty", {}, Run())]


def oracle_date(s, res, tree):
    import datetime, re
    cur = dict(s["files"])
    for n in sorted(k for k, e in s["files"].items() if "/" not in k and e["t"] == "f"):
        if re.match(r"^\d{4}-\d{2}-\d{2}_", n):
            continue
        d = datetime.datetime.fromtimestamp(s["files"][n].get("m", 1700000000), datetime.timezone.utc).strftime("%Y-%m-%d")
        move(cur, n, f"{d}_{n}")
    return _o_lower(cur, [], res, tree)


# ------------------------------------------------------------------------------------------------ 4. flatten

REF_FLATTEN = dd('''
    #!/usr/bin/env bash
    # Move every file below the current directory into ./flat, resolving name clashes with -1, -2, ...
    shopt -s globstar nullglob dotglob
    mkdir -p flat
    files=()
    while IFS= read -r -d '' f; do
      files+=("$f")
    done < <(find . -path ./flat -prune -o -type f -print0 | LC_ALL=C sort -z)
    for f in "${files[@]}"; do
      f=${f#./}
      name=${f##*/}
      stem=$name
      ext=
      case $name in
        ?*.*) stem=${name%.*}; ext=.${name##*.} ;;
      esac
      target=$name
      i=0
      while [ -e "flat/$target" ]; do
        i=$((i + 1))
        target=$stem-$i$ext
      done
      mv -- "$f" "flat/$target"
    done
    # remove directories that are now empty (but keep flat itself)
    find . -mindepth 1 -type d -empty -not -path ./flat -not -path './flat/*' -delete 2>/dev/null
    find . -mindepth 1 -type d -empty -not -path ./flat -not -path './flat/*' -delete 2>/dev/null
    exit 0
''')


def make_flatten(rng):
    ex = scn("example", {"a/photo.jpg": F("a1\n"), "b/photo.jpg": F("b1\n"), "b/c/photo.jpg": F("bc1\n"), "top.txt": F("top\n")}, Run())
    a = {"vacation/day 1/img.png": F("1\n"), "vacation/day 2/img.png": F("2\n"), "vacation/img.png": F("3\n"), "img.png": F("4\n"),
         "-odd/-x.txt": F("5\n"), "-odd/x.txt": F("6\n"), "x.txt": F("7\n"), "docs/archive.tar.gz": F("8\n"), "docs/old/archive.tar.gz": F("9\n"),
         "docs/.hidden": F("10\n"), ".hidden": F("11\n"), "empty dir/deeper/none": D(), "noext/Makefile": F("12\n"), "Makefile": F("13\n")}
    b = {"flat/img.png": F("existing\n"), "s/img.png": F("new\n"), "s/img-1.png": F("another\n")}
    return ex, [scn("nested clashes", a, Run(), dirs="all"), scn("existing flat dir", b, Run(), dirs="all"), scn("already flat", {"one.txt": F("1\n"), "two.txt": F("2\n")}, Run(), dirs="all")]


# ------------------------------------------------------------------------------------------------ 5. artist/title/year

REF_SWAP = dd('''
    #!/usr/bin/env bash
    # "Artist - Title (Year).ext"  ->  "Year - Artist - Title.ext"
    shopt -s nullglob
    re='^(.+) - (.+) \\(([0-9]{4})\\)(\\.[^.]+)$'
    for f in *; do
      [ -f "$f" ] || continue
      if [[ $f =~ $re ]]; then
        new="${BASH_REMATCH[3]} - ${BASH_REMATCH[1]} - ${BASH_REMATCH[2]}${BASH_REMATCH[4]}"
        mv -- "$f" "$new"
      else
        echo "unmatched: $f"
      fi
    done
''')


def make_swap(rng):
    ex = scn("example", files_of(["Mina Sol - Low Tide (2019).flac", "The Drifters - Harbour Lights (1964).mp3", "notes.txt"]), Run())
    a = ["Band - Song - Live (2001).ogg", "Mx. Quill - Ça va (1999).mp3", "A - B (2000).wav", "Duo - Intro (3).mp3", "Solo - Untitled (20014).mp3",
         "Solo - Two Parts (2012) (2013).mp3", "Fo & Ba - It's (Not) Over (2022).flac", "Name - Title (2005)", "- - ( 1999).mp3", "Name - Title(2005).mp3",
         "Artist - Title (1999).tar.gz", "Ünï - Çø (2010).opus"]
    return ex, [scn("awkward and unmatched", files_of(a), Run())]


def oracle_swap(s, res, tree):
    import re
    cur = dict(s["files"])
    out = []
    for n in sorted(k for k, e in s["files"].items() if "/" not in k and e["t"] == "f"):
        m = re.match(r"^(.+) - (.+) \(([0-9]{4})\)(\.[^.]+)$", n)
        if not m:
            out.append("unmatched: " + n)
            continue
        move(cur, n, f"{m.group(3)} - {m.group(1)} - {m.group(2)}{m.group(4)}")
    return _o_lower(cur, out, res, tree)


# ------------------------------------------------------------------------------------------------ 6. sanitize

REF_SANITIZE = dd('''
    #!/usr/bin/env bash
    # Make file names safe: [A-Za-z0-9._-] only, runs of '_' collapsed, no leading '-' or '.' .
    shopt -s nullglob
    for f in *; do
      [ -f "$f" ] || continue
      new=$(printf '%s' "$f" | sed -E 's/[^A-Za-z0-9._-]/_/g; s/_+/_/g; s/^[-.]+/_/')
      [ "$new" = "$f" ] && continue
      base=${new%.*}
      ext=
      case $new in ?*.*) ext=.${new##*.} ;; esac
      [ -n "$ext" ] || base=$new
      i=1
      cand=$new
      while [ -e "$cand" ]; do
        i=$((i + 1))
        cand=$base-$i$ext
      done
      mv -- "$f" "$cand"
    done
''')


def make_sanitize(rng):
    ex = scn("example", files_of(["my file (1).txt", "-notes.md", ".profile", "ok_name.txt", "été.txt"]), Run())
    a = ["two  spaces.txt", "a - b.txt", "dollar$HOME.txt", "it's.txt", 'say "hi".txt', "[x]  [y].csv", "-rf.txt", "--", ".hidden file", "résumé final.pdf", "trailing space .txt",
         "semi;colon&amp.txt", "a b.txt", "a_b.txt", "a  b.txt", "emoji 🙂.txt", "tab\tname.txt", "new\nline.txt"]
    return ex, [scn("awkward names and clashes", files_of(a), Run())]


def oracle_sanitize(s, res, tree):
    import re
    cur = dict(s["files"])
    for n in sorted(k for k, e in s["files"].items() if "/" not in k and e["t"] == "f"):
        new = re.sub(r"[^A-Za-z0-9._-]", "_", n)
        new = re.sub(r"_+", "_", new)
        new = re.sub(r"^[-.]+", "_", new)
        if new == n:
            continue
        base, ext = (new.rsplit(".", 1)[0], "." + new.rsplit(".", 1)[1]) if re.match(r"^.+\.[^.]*$", new) and not new.startswith(".") else (new, "")
        # emulate the shell: ext only when new has a dot after at least one char
        if "." in new and new.index(".") > 0:
            base, ext = new.rsplit(".", 1)[0], "." + new.rsplit(".", 1)[1]
        else:
            base, ext = new, ""
        cand, i = new, 1
        while cand in cur:
            i += 1
            cand = f"{base}-{i}{ext}"
        move(cur, n, cand)
    return _o_lower(cur, [], res, tree)


# ------------------------------------------------------------------------------------------------ 7. prefix with undo

REF_UNDO = dd('''
    #!/usr/bin/env bash
    # rn.sh [-n] PREFIX   add PREFIX to every regular file in the current directory (log in .rename.log)
    # rn.sh --undo        reverse the last run
    set -u
    log=.rename.log
    if [ "${1:-}" = "--undo" ]; then
      [ -f "$log" ] || { echo "nothing to undo" >&2; exit 1; }
      tac "$log" | while IFS=$'\\t' read -r old new; do
        mv -- "$new" "$old"
      done
      rm -f -- "$log"
      exit 0
    fi
    dry=0
    if [ "${1:-}" = "-n" ]; then dry=1; shift; fi
    if [ $# -ne 1 ] || [ -z "$1" ]; then echo "usage: rn.sh [-n] PREFIX | --undo" >&2; exit 2; fi
    prefix=$1
    shopt -s nullglob
    for f in *; do
      [ -f "$f" ] || continue
      case $f in "$prefix"*) continue ;; esac
      new=$prefix$f
      if [ -e "$new" ]; then echo "skip: $f" >&2; continue; fi
      if [ "$dry" = 1 ]; then
        printf '%s -> %s\\n' "$f" "$new"
      else
        mv -- "$f" "$new"
        printf '%s\\t%s\\n' "$f" "$new" >> "$log"
      fi
    done
''')


def make_undo(rng):
    ex = scn("example", files_of(["a.txt", "b c.txt", "-d"]), Run("-n", "old_"))
    plain = ["a.txt", "b c.txt", "-d", "old_keep.txt", "it's.md", "ünï.txt", "star*.txt"]
    return ex, [
        scn("dry run touches nothing", files_of(plain), Run("-n", "old_")),
        scn("rename", files_of(plain), Run("old_")),
        scn("rename then undo", files_of(plain), Run("2031-"), Run("--undo")),
        scn("prefix that makes a name clash", files_of(["x.txt", "p_x.txt", "y.txt"]), Run("p_")),
        scn("undo without log", files_of(["x.txt"]), Run("--undo", rc=True, stderr="nonempty")),
        scn("bad usage", files_of(["x.txt"]), Run("-n", stdout="exact", stderr="nonempty"), Run()),
    ]


# ------------------------------------------------------------------------------------------------ 8. sniff

REF_SNIFF = dd('''
    #!/usr/bin/env bash
    # Give extension-less files an extension based on their first bytes.
    shopt -s nullglob dotglob
    for f in *; do
      [ -f "$f" ] || continue
      case $f in *.*) continue ;; esac
      magic=$(head -c 8 -- "$f" | od -An -tx1 | tr -d ' \\n')
      ext=
      case $magic in
        89504e470d0a1a0a) ext=png ;;
        474946383961*|474946383761*) ext=gif ;;
        25504446*) ext=pdf ;;
        504b0304*) ext=zip ;;
        ffd8ff*) ext=jpg ;;
        2321*) ext=sh ;;
      esac
      if [ -z "$ext" ]; then
        echo "unknown: $f"
        continue
      fi
      [ -e "$f.$ext" ] && { echo "exists: $f.$ext"; continue; }
      mv -- "$f" "$f.$ext"
    done
''')

PNG = "\x89PNG\r\n\x1a\n"


def make_sniff(rng):
    # file contents are text in the scenario format, so use only magics that are valid UTF-8: gif, pdf, zip, sh, plus a utf-8 safe stand-in for jpg is impossible
    ex = scn("example", {"blob1": F("GIF89a...."), "blob2": F("%PDF-1.7\n"), "blob3": F("hello\n"), "keep.txt": F("x")}, Run())
    a = {"report": F("%PDF-1.4\n%abc"), "anim": F("GIF87a\x01\x00"), "archive": F("PK\x03\x04rest"), "run me": F("#!/bin/sh\necho\n"), "-odd": F("%PDF-"),
         "empty": F(""), "notes": F("plain text\n"), "pic": F("GIF8"), "short": F("%PD"), ".dotfile": F("PK\x03\x04"), "dir.d/inside": F("PK\x03\x04")}
    b = {"x": F("%PDF-1"), "x.pdf": F("already\n"), "y": F("#!/bin/bash\n")}
    return ex, [scn("assorted magics", a, Run(), dirs="all"), scn("target exists", b, Run())]


# ------------------------------------------------------------------------------------------------ 9. strip versions

REF_STRIP = dd('''
    #!/usr/bin/env bash
    # libfoo-1.2.3.so -> libfoo.so : drop a "-<digits>(.<digits>)*" suffix that sits right before the extension
    shopt -s nullglob
    re='^(.+)-[0-9]+(\\.[0-9]+)*(\\.[^.0-9][^.]*)$'
    for f in *; do
      [ -f "$f" ] || continue
      [[ $f =~ $re ]] || continue
      new=${BASH_REMATCH[1]}${BASH_REMATCH[3]}
      if [ -e "$new" ]; then
        echo "keep: $f"
        continue
      fi
      mv -- "$f" "$new"
    done
''')


def make_strip(rng):
    ex = scn("example", files_of(["libfoo-1.2.3.so", "tool-2.txt", "setup-1.0.exe", "plain.txt"]), Run())
    a = ["lib foo-10.4.so", "a-b-3.1.2.tar", "x-1.2.gz", "-v-1.0.md", "name-1.2.3", "name-1.2.3.4.5.dat", "v1-2.txt", "pkg-1.2a.txt", "pkg-.5.txt", "libfoo-1.so", "libfoo.so",
         "ünï-2.0.txt", "w-1-2.txt", "q-007.log", "z--1.txt"]
    return ex, [scn("awkward names", files_of(a), Run())]


def oracle_strip(s, res, tree):
    import re
    cur = dict(s["files"])
    out = []
    for n in sorted(k for k, e in s["files"].items() if "/" not in k and e["t"] == "f"):
        m = re.match(r"^(.+)-[0-9]+(\.[0-9]+)*(\.[^.0-9][^.]*)$", n)
        if not m:
            continue
        new = m.group(1) + m.group(3)
        if new in cur:
            out.append("keep: " + n)
            continue
        move(cur, n, new)
    return _o_lower(cur, out, res, tree)


# ------------------------------------------------------------------------------------------------ 10. mapping with cycles

REF_MAP = dd('''
    #!/usr/bin/env bash
    # Apply renames listed in a CSV (old,new), even when they swap or chain.
    # usage: remap.sh MAPPING.csv
    set -eu
    map=$1
    tmp=$(mktemp -d ./.remap.XXXXXX)
    olds=()
    news=()
    while IFS=, read -r a b; do
      a=${a#\\"}; a=${a%\\"}; a=${a//\\"\\"/\\"}
      b=${b#\\"}; b=${b%\\"}; b=${b//\\"\\"/\\"}
      olds+=("$a")
      news+=("$b")
    done < <(python3 - "$map" <<'PY'
    import csv, sys
    for row in csv.reader(open(sys.argv[1], newline="")):
        if len(row) == 2 and row[0] != "old":
            print(row[0].replace("\\\\", "\\\\\\\\") + "," + row[1])
    PY
    )
    echo placeholder > /dev/null
    rm -rf "$tmp"
''')

# The CSV-mapping reference is easier and less error prone in pure bash with a small awk quoting parser; written below.
REF_MAP = dd('''
    #!/usr/bin/env bash
    # remap.sh MAPPING.csv : apply "old,new" renames from a CSV file, even when they swap or chain.
    # Fields may be double-quoted (with "" for a quote); no field contains a line break.
    set -eu
    map=$1
    parse() {
      awk -v RS='\\n' '
        function field(s,   out, i, c, q) {
          out = ""; q = 0
          for (i = 1; i <= length(s); i++) {
            c = substr(s, i, 1)
            if (q) { if (c == "\\"") { if (substr(s, i + 1, 1) == "\\"") { out = out "\\""; i++ } else q = 0 } else out = out c }
            else if (c == "\\"") q = 1
            else out = out c
          }
          return out
        }
        NR == 1 && $0 == "old,new" { next }
        {
          line = $0; n = 0; cur = ""; q = 0
          for (i = 1; i <= length(line); i++) {
            c = substr(line, i, 1)
            if (c == "\\"") q = !q
            if (c == "," && !q) { f[++n] = cur; cur = "" } else cur = cur c
          }
          f[++n] = cur
          printf "%s\\0%s\\0", field(f[1]), field(f[2])
        }' "$map"
    }
    olds=(); news=()
    while IFS= read -r -d '' a && IFS= read -r -d '' b; do
      olds+=("$a"); news+=("$b")
    done < <(parse)
    # step 1: move every source that exists to a unique temporary name
    tmp=.remap.$$
    mkdir "$tmp"
    i=0
    for ((k = 0; k < ${#olds[@]}; k++)); do
      if [ -e "${olds[k]}" ] || [ -L "${olds[k]}" ]; then
        mv -- "${olds[k]}" "$tmp/$k"
      else
        echo "missing: ${olds[k]}"
        olds[k]=
      fi
    done
    # step 2: move them to their final names
    for ((k = 0; k < ${#olds[@]}; k++)); do
      [ -n "${olds[k]}" ] || continue
      mkdir -p -- "$(dirname -- "${news[k]}")"
      mv -- "$tmp/$k" "${news[k]}"
    done
    rmdir "$tmp"
''')


def make_map(rng):
    ex = scn("example", {**files_of(["a.txt", "b.txt", "c.txt"]), "map.csv": F("old,new\na.txt,b.txt\nb.txt,a.txt\nc.txt,c2.txt\n")}, Run("map.csv"))
    csv_a = 'old,new\n"two, words.txt",simple.txt\nsimple2.txt,"with ""quotes"".txt"\n-lead.txt,nested/dir/moved.txt\nghost.txt,never.txt\nx1,x2\nx2,x3\nx3,x1\n'
    a = {**files_of(["two, words.txt", "simple2.txt", "-lead.txt", "x1", "x2", "x3", "keep.txt"]), "map.csv": F(csv_a)}
    csv_b = "old,new\np,q\nq,r\nr,p\n"
    b = {**files_of(["p", "q", "r"]), "m.csv": F(csv_b)}
    csv_c = "old,new\nnew.txt,old.txt\nold.txt,new.txt\n"
    c = {**files_of(["new.txt", "old.txt", "other"]), "swap.csv": F(csv_c)}
    return ex, [scn("quotes, commas, chains, missing", a, Run("map.csv"), dirs="all"), scn("three-cycle", b, Run("m.csv")), scn("swap", c, Run("swap.csv"))]


# ------------------------------------------------------------------------------------------------ 11. fix quoting

BUGGY_FIX = dd('''
    #!/bin/bash
    # rename every .txt file in this folder to .md
    for f in $(ls *.txt); do
      mv $f ${f%.txt}.md
    done
''')

REF_FIX = dd('''
    #!/bin/bash
    # rename every .txt file in this folder to .md
    shopt -s nullglob
    for f in *.txt; do
      mv -- "$f" "${f%.txt}.md"
    done
''')


def make_fix(rng):
    ex = scn("example", files_of(["notes.txt", "my report.txt", "readme.md"]), Run())
    a = ["two words.txt", "-dash.txt", "star*.txt", "it's.txt", "naïve café.txt", "[b].txt", "plain.txt", "weird\nname.txt", "x.TXT", ".txt", "tail.txt.bak", "double.txt.txt"]
    return ex, [scn("awkward names", files_of(a), Run()), scn("no txt files", files_of(["a.md"]), Run(rc=True))]


def oracle_fix(s, res, tree):
    cur = dict(s["files"])
    for n in sorted(k for k, e in s["files"].items() if "/" not in k and e["t"] == "f"):
        if n.endswith(".txt"):
            move(cur, n, n[:-4] + ".md")
    return _o_lower(cur, [], res, tree)


# ------------------------------------------------------------------------------------------------ specs

SPECS = [
    S("fix-ls-loop", 1,
      "`tidy.sh` is supposed to turn every `.txt` file in the folder into `.md`, and it works until somebody has a file with a space or a dash in its name. Fix it so it handles any file name.",
      "`tidy.sh` renames every `*.txt` file in the current directory to the same name with `.md` instead. It must work for every file name: spaces, leading dashes, glob characters, quotes, even line breaks. Only files whose name ends in `.txt` are touched; a name that is just `.txt` is a valid (hidden) file and becomes `.md`.",
      REF_FIX, make_fix, buggy=BUGGY_FIX, oracle=oracle_fix, title="Rename .txt to .md", wrong=(BUGGY_FIX,)),
    S("lowercase-extensions", 1,
      "Write `tidy.sh` so that it lowercases the extension of every file in the current directory (`IMG_01.JPG` becomes `IMG_01.jpg`). Details, including what to do when the lowercase name is already taken, are in the README.",
      "Run as `bash tidy.sh` inside a directory. For every **regular file** directly in it (hidden files included; directories and symlinks are left alone) lowercase the extension, i.e. the part after the *last* dot, ASCII letters only. "
      "A name has no extension if it has no dot, or if the only dot is the first character (`.bashrc`); such names, and names whose extension is already lowercase or empty (`trailing.`), are untouched. "
      "If the new name already exists (as a file, directory or symlink) do not overwrite anything: leave the file alone and print `exists: <old name>` on its own line, in byte-wise sorted order of the old names. Nothing else is printed.",
      REF_LOWER, make_lower, oracle=oracle_lower, title="Lowercase file extensions",
      wrong=("""#!/bin/bash
for f in *.*; do
  new="${f%.*}.$(echo "${f##*.}" | tr A-Z a-z)"
  [ "$f" != "$new" ] && mv "$f" "$new"
done
""",)),
    S("zero-pad-numbers", 2,
      "Our scanner names files `scan 3.pdf`, `scan 10.pdf`, `scan 118.pdf` and they sort badly. Write `tidy.sh` that pads the first number in every file name to four digits, as described in the README.",
      "Run as `bash tidy.sh` in a directory. For every regular file directly in it: find the **first run of digits** in the name; if that run is shorter than four digits, pad it on the left with zeros to exactly four digits "
      "(`scan 3.pdf` -> `scan 0003.pdf`, `007 bond.txt` -> `0007 bond.txt`); runs of four or more digits and names without digits are untouched. "
      "If the new name already exists, do not overwrite: leave the file and print `conflict: <old name>` on its own line (files processed in byte-wise sorted order). Nothing else is printed. Directories are ignored.",
      REF_PAD, make_pad, oracle=oracle_pad, title="Zero-pad the first number",
      wrong=("""#!/bin/bash
for f in *; do
  [ -f "$f" ] || continue
  n=$(echo "$f" | grep -o '[0-9]*' | head -1)
  [ -n "$n" ] || continue
  new=$(echo "$f" | sed "s/$n/$(printf %04d $n)/")
  [ "$f" != "$new" ] && mv -- "$f" "$new"
done
""",)),
    S("date-prefix", 2,
      "Add the last-modified date (UTC, `YYYY-MM-DD_`) in front of every file in a folder, but don't do it twice to files that already carry such a prefix. Please write `tidy.sh` per the README.",
      "Run as `bash tidy.sh` in a directory. Every regular file directly in it is renamed to `<date>_<old name>` where `<date>` is the UTC calendar date of the file's modification time as `YYYY-MM-DD`. "
      "A file whose name already starts with `dddd-dd-dd_` (digits only, the exact shape, whether or not it is a real calendar date) is left alone. Directories are not touched and nothing is printed. "
      "The tests set modification times explicitly and run with `TZ=UTC`.",
      REF_DATE, make_date, oracle=oracle_date, title="Date prefixes from modification time",
      wrong=("""#!/bin/bash
for f in *; do
  [ -f "$f" ] || continue
  d=$(date -r "$f" +%Y-%m-%d)
  case "$f" in $d*) continue;; esac
  mv -- "$f" "${d}_$f"
done
""",)),
    S("flatten-tree", 4,
      "I have a messy tree of subfolders and want every file moved into a single `flat/` folder. Name clashes must not lose data; write `tidy.sh` as the README describes.",
      "Run as `bash tidy.sh` at the top of a tree. Move every file found anywhere below the current directory (hidden files included, symlinks not involved) into `./flat/` (created if missing; files already in `flat/` stay where they are). "
      "Process the files in byte-wise sorted order of their relative path (`LC_ALL=C sort`). A moved file keeps its base name; if that name is already taken inside `flat/`, insert `-1`, `-2`, ... "
      "before the extension (everything after the last dot of the base name; none if the name has no dot or only a leading dot) using the smallest number that is free: `photo.jpg`, `photo-1.jpg`, `photo-2.jpg`; `archive.tar.gz` becomes `archive.tar-1.gz`. "
      "Afterwards remove every directory that is left empty (nested ones too), except `flat` itself. Print nothing.",
      REF_FLATTEN, make_flatten, title="Flatten a tree",
      wrong=("""#!/bin/bash
mkdir -p flat
find . -path ./flat -prune -o -type f -print | while read f; do mv "$f" flat/ ; done
""",)),
    S("artist-title-year", 3,
      "Music files are named `Artist - Title (Year).ext` and I want `Year - Artist - Title.ext` instead. Write `tidy.sh`; the README lists the exact pattern and what to do with files that do not fit it.",
      "Run as `bash tidy.sh` in a directory. A file name that matches `<artist> - <title> (<year>)<ext>` is renamed to `<year> - <artist> - <title><ext>`. The pattern is: `<artist>` and `<title>` are any non-empty text; "
      "the first is separated from the second by ` - ` and the **last** ` (dddd)` before the extension is the year (exactly four digits); `<ext>` is a final dot followed by non-dot characters. "
      "When several splits are possible the artist is the **longest** possible prefix before a ` - ` (greedy), as a regular expression `^(.+) - (.+) \\(([0-9]{4})\\)(\\.[^.]+)$` would give. "
      "Names that do not match are left alone and reported as `unmatched: <name>` lines (byte-wise sorted order). Only regular files directly in the directory are considered.",
      REF_SWAP, make_swap, oracle=oracle_swap, title="Reorder music file names",
      wrong=("""#!/bin/bash
for f in *.*; do
  artist=${f%% - *}; rest=${f#* - }; title=${rest% (*}; year=${rest##* (}; year=${year%%)*}; ext=${f##*.}
  mv "$f" "$year - $artist - $title.$ext"
done
""",)),
    S("sanitize-names", 3,
      "Some of the files we receive have names that break our build tools. Write `tidy.sh` that rewrites them to a safe alphabet; the rules and the tie-breaking for clashes are in the README.",
      "Run as `bash tidy.sh` in a directory. For every regular file directly in it compute a safe name: replace every character outside `A-Z a-z 0-9 . _ -` with `_` (one `_` per *character*, not per byte), "
      "then collapse every run of `_` into a single `_`, then replace the run of `-`/`.` characters at the very start of the name (if any) by one `_`. "
      "If the result equals the old name nothing happens. If the result is already taken by another file (existing or created earlier in this run), put `-2`, `-3`, ... before the extension "
      "(the part after the last dot, if the name has a dot that is not its first character) using the smallest free number. Files are processed in byte-wise sorted order. Nothing is printed.",
      REF_SANITIZE, make_sanitize, oracle=oracle_sanitize, title="Safe file names",
      wrong=("""#!/bin/bash
for f in *; do
  new=$(echo "$f" | tr -c 'A-Za-z0-9._-' '_')
  [ "$f" != "$new" ] && mv -- "$f" "$new"
done
""",)),
    S("sniff-extensions", 3,
      "Write `tidy.sh` to give extension-less files a proper extension by looking at their first bytes (png, gif, pdf, zip, jpg, shell scripts). The README lists the signatures.",
      "Run as `bash tidy.sh` in a directory. Consider every regular file directly in it (hidden ones too) whose name contains **no dot at all**. Look at the first bytes of the file: "
      "`89 50 4E 47 0D 0A 1A 0A` -> `.png`; `GIF87a` or `GIF89a` -> `.gif`; `%PDF` -> `.pdf`; `PK\\x03\\x04` -> `.zip`; `FF D8 FF` -> `.jpg`; `#!` -> `.sh`. "
      "Rename `name` to `name.<ext>`; if that target exists leave the file and print `exists: <target>`; if no signature matches (including empty files and files shorter than the signature) leave it and print `unknown: <name>`. "
      "Lines are printed in byte-wise sorted order of the original names. Nothing else is printed.",
      REF_SNIFF, make_sniff, title="Extensions from file signatures",
      wrong=("""#!/bin/bash
for f in *; do
  [ -f "$f" ] || continue
  case "$f" in *.*) continue;; esac
  head -c 4 "$f" | grep -q PDF && mv "$f" "$f.pdf"
done
""",)),
    S("strip-version-suffix", 3,
      "Build artefacts are named like `libfoo-1.2.3.so` and I need the version stripped (`libfoo.so`) without damaging other files. Write `tidy.sh` following the README.",
      "Run as `bash tidy.sh` in a directory. A regular file whose name has the form `<stem>-<version><ext>` is renamed to `<stem><ext>`, where `<version>` is one or more digits optionally followed by groups of `.` and digits "
      "(`1`, `1.2`, `1.2.3.4`), `<ext>` starts with a dot, then a character that is neither a dot nor a digit, then any non-dot characters (`.so`, `.tar`, `.gz`), and `<stem>` is non-empty and may itself contain dashes "
      "(the **last** `-<version>` right before the extension is the one removed). Names that do not fit exactly (`name-1.2.3`, `pkg-1.2a.txt`, no extension) are left alone. "
      "If the stripped name already exists, keep the original and print `keep: <name>` (byte-wise order). Nothing else is printed.",
      REF_STRIP, make_strip, oracle=oracle_strip, title="Strip version suffixes",
      wrong=("""#!/bin/bash
for f in *-[0-9]*; do
  new=$(echo "$f" | sed -E 's/-[0-9.]+//')
  [ -e "$new" ] || mv -- "$f" "$new"
done
""",)),
    S("undoable-prefix", 4,
      "Write `rn.sh`, a small batch-prefix tool with a dry-run mode and an undo. The README spells out the interface, the log format and the error cases.",
      "`bash rn.sh [-n] PREFIX` adds `PREFIX` in front of the name of every regular file in the current directory, except files that already start with `PREFIX` "
      "(hidden files are not considered). Files are processed in byte-wise sorted order. If the new name is already taken the file is skipped with `skip: <name>` on **stderr**. "
      "Each performed rename appends one line `<old>`, a TAB, `<new>` to `.rename.log` in the current directory. With `-n` nothing is renamed or logged and each rename that would happen is printed on stdout as `<old> -> <new>`.\n\n"
      "`bash rn.sh --undo` reverses the renames recorded in `.rename.log` (last one first) and then deletes the log; with no log it prints a message on stderr and exits with status 1. "
      "Wrong usage (no PREFIX, an empty PREFIX, more than one argument besides the flag) prints a usage line on stderr and exits with status 2 without touching anything. File names in the tests contain no TABs or line breaks.",
      REF_UNDO, make_undo, script="rn.sh", title="Batch prefix with dry run and undo",
      wrong=("""#!/bin/bash
for f in *; do [ -f "$f" ] && mv "$f" "$1$f"; done
""",)),
    S("remap-from-csv", 5,
      "Write `remap.sh MAPPING.csv`: it applies a list of renames from a CSV file, including swaps and cycles, quoted names and moves into new folders. The README has the exact format and the reporting rules.",
      "`bash remap.sh MAPPING.csv` reads the CSV (header line `old,new`, then one rename per line) and renames every `old` to `new`, relative to the current directory. Fields may be double-quoted "
      "(a quote inside a quoted field is written `\"\"`; commas inside quotes belong to the name); no field contains a line break. "
      "All renames are applied **as if simultaneously**: `a -> b` together with `b -> a` swaps the two files, and `x1 -> x2, x2 -> x3, x3 -> x1` rotates them. "
      "If an `old` does not exist print `missing: <old>` (in CSV order) and skip that line. The parent directories of a `new` are created when needed. Nothing is overwritten except by this simultaneous semantics "
      "(`new` names that are not themselves renamed sources never exist in the tests). Exit status 0.",
      REF_MAP, make_map, script="remap.sh", title="Apply renames from a CSV",
      wrong=("""#!/bin/bash
tail -n +2 "$1" | while IFS=, read -r a b; do mv "$a" "$b"; done
""",)),
]


@family("shell-batch-rename", category="shell", lang="bash", kind="feature", n=len(SPECS),
        summary="renaming files in bulk with awkward names: extensions, padding, dates, flattening, sanitising, undo, CSV mappings")
def batch_rename(rng, n):
    return K.shell_tasks("batch-rename", SPECS, rng, n)
