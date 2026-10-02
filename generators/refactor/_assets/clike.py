"""Structural analysis helpers for C-like languages (go, javascript, java, rust): functions, lengths, shapes.

This is a lexical analyser, not a parser: comments and literals are blanked, braces are matched, and function
headers are recognised per language. It is meant for coarse structural limits (lengths, duplicates, counts)."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEYWORDS = {"if", "for", "while", "switch", "catch", "synchronized", "try", "else", "do", "return", "new", "match", "loop",
            "select", "func", "function", "sizeof", "throw", "await", "typeof", "super", "this", "with"}


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def exists(rel):
    return os.path.exists(os.path.join(ROOT, rel))


def files(exts, dirs=("src", "lib", "."), skip=("test", "tests", "node_modules", "target", "build", "checks", "vendor")):
    """Source files with one of the extensions below the given directories (relative paths, sorted, de-duplicated)."""
    out = []
    for d in dirs:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for dp, dns, fns in os.walk(base):
            dns[:] = sorted(x for x in dns if x not in skip and not x.startswith("."))
            for fn in sorted(fns):
                if fn.endswith(tuple(exts)) and not fn.endswith(("_test.go", ".test.js", ".test.ts", "Test.java")):
                    out.append(os.path.relpath(os.path.join(dp, fn), ROOT).replace(os.sep, "/"))
        if d == ".":
            pass
    seen, res = set(), []
    for f in sorted(out):
        if f not in seen:
            seen.add(f)
            res.append(f)
    return res


def clean(src, lang):
    """Blank comments and the insides of string/char/regex literals (newlines are kept, so line numbers survive)."""
    out = []
    i, n = 0, len(src)
    prev_sig = ""
    while i < n:
        c = src[i]
        two = src[i:i + 2]
        if two == "//":
            j = src.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
            continue
        if two == "/*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("".join("\n" if ch == "\n" else " " for ch in src[i:j]))
            i = j
            continue
        if lang == "rust" and c == "r" and re.match(r'r#*"', src[i:i + 8]) and not (i > 0 and (src[i - 1].isalnum() or src[i - 1] == "_")):
            m = re.match(r'r(#*)"', src[i:])
            term = '"' + m.group(1)
            j = src.find(term, i + len(m.group(0)))
            j = n if j < 0 else j + len(term)
            out.append("".join("\n" if ch == "\n" else " " for ch in src[i:j]))
            i = j
            prev_sig = '"'
            continue
        if c == '"' or (c == "'" and lang != "rust" and lang != "go") or (c == "`" and lang in ("javascript", "go")):
            q = c
            j = i + 1
            while j < n:
                if src[j] == "\\" and q != "`" or (src[j] == "\\" and lang == "javascript"):
                    j += 2
                    continue
                if src[j] == q:
                    break
                if src[j] == "\n" and q != "`":
                    break
                j += 1
            j = min(n, j + 1)
            out.append(q + "".join("\n" if ch == "\n" else " " for ch in src[i + 1:j - 1]) + (q if j - 1 > i else ""))
            i = j
            prev_sig = q
            continue
        if c == "'" and lang in ("rust", "go"):
            # char literal ('a', '\n', '\u{1F600}') versus lifetime ('a) in rust
            m = re.match(r"'(\\.[^']*|[^\\'])'", src[i:])
            if m:
                out.append("'" + " " * (len(m.group(0)) - 2) + "'")
                i += len(m.group(0))
                prev_sig = "'"
                continue
        if c == "/" and lang == "javascript" and (prev_sig in "(,=:[!&|?{};" or prev_sig == "" or re.search(r"\breturn\s*$", "".join(out)[-8:])):
            j = i + 1
            in_class = False
            while j < n and src[j] != "\n":
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "[":
                    in_class = True
                elif src[j] == "]":
                    in_class = False
                elif src[j] == "/" and not in_class:
                    break
                j += 1
            if j < n and src[j] == "/":
                j += 1
                while j < n and src[j].isalpha():
                    j += 1
                out.append("/" + " " * (j - i - 2) + "/")
                i = j
                prev_sig = "/"
                continue
        out.append(c)
        if not c.isspace():
            prev_sig = c
        i += 1
    return "".join(out)


def match_brace(text, i):
    depth = 0
    for j in range(i, len(text)):
        ch = text[j]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return j
    return len(text) - 1


def _first_body_brace(text, pos, stop_semicolon=True):
    """Index of the '{' that opens a body after a header starting at pos, skipping parens/brackets; -1 on ';' first."""
    depth = 0
    j = pos
    n = len(text)
    while j < n:
        ch = text[j]
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif depth == 0 and ch == "{":
            return j
        elif depth == 0 and ch == ";" and stop_semicolon:
            return -1
        j += 1
    return -1


_PATTERNS = {
    "go": [re.compile(r"(?m)^func\s*(?:\([^)]*\)\s*)?([A-Za-z_]\w*)")],
    "rust": [re.compile(r"\bfn\s+([A-Za-z_]\w*)")],
    "javascript": [
        re.compile(r"\bfunction\s*\*?\s*([A-Za-z_$][\w$]*)\s*\("),
        re.compile(r"(?m)^[ \t]*(?:export\s+)?(?:async\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function\b[^(]*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*(?:=>)?\s*(?=\{)"),
        re.compile(r"(?m)^[ \t]*(?:static\s+)?(?:async\s+)?(?:get\s+|set\s+)?(?:\*\s*)?([A-Za-z_$#][\w$]*)\s*\([^)]*\)\s*(?=\{)"),
        re.compile(r"(?m)^[ \t]*([A-Za-z_$][\w$]*)\s*:\s*(?:async\s*)?(?:function\b[^(]*)?\([^)]*\)\s*(?:=>)?\s*(?=\{)"),
    ],
    "java": [
        re.compile(r"(?m)^[ \t]*(?:@\w+(?:\([^)]*\))?\s+)*(?:(?:public|protected|private|static|final|abstract|synchronized|native|default|strictfp)\s+)*"
                   r"(?:<[^>]+>\s+)?[\w.<>\[\],?& ]+?\s+([A-Za-z_]\w*)\s*\([^;{}]*\)\s*(?:throws\s+[\w.,\s]+)?(?=\{)"),
        re.compile(r"(?m)^[ \t]*(?:(?:public|protected|private)\s+)?([A-Z]\w*)\s*\([^;{}]*\)\s*(?:throws\s+[\w.,\s]+)?(?=\{)"),
    ],
}


class Fn:
    def __init__(self, name, file, line0, line1, loc, body):
        self.name, self.file, self.line0, self.line1, self.loc, self.body = name, file, line0, line1, loc, body

    def __repr__(self):
        return f"{self.file}:{self.name}({self.loc} lines)"


def functions(rel, lang):
    return functions_text(read(rel), lang, rel)


def functions_text(src, lang, rel="<mem>"):
    text = clean(src, lang)
    found = {}
    for pat in _PATTERNS[lang]:
        for m in pat.finditer(text):
            name = m.group(1)
            if name in KEYWORDS:
                continue
            b = _first_body_brace(text, m.end() if lang in ("javascript", "java") and text[m.end():m.end() + 1] == "{" else m.end(), stop_semicolon=True)
            if b < 0:
                continue
            e = match_brace(text, b)
            start_line = text.count("\n", 0, m.start()) + 1
            if lang in ("javascript", "java") and not text[m.start():m.start() + 1].strip():
                start_line = text.count("\n", 0, m.start() + len(m.group(0)) - len(m.group(0).lstrip())) + 1
            end_line = text.count("\n", 0, e) + 1
            key = b
            if key in found:
                continue
            body = text[b:e + 1]
            lines = text.splitlines()[start_line - 1:end_line]
            nloc = sum(1 for ln in lines if ln.strip())
            found[key] = Fn(name, rel, start_line, end_line, nloc, body)
    return [found[k] for k in sorted(found)]


def all_functions(rels, lang):
    out = []
    for r in rels:
        out.extend(functions(r, lang))
    return out


_ID = re.compile(r"[A-Za-z_$][\w$]*")
_NUM = re.compile(r"\b\d[\w.]*\b")
_STR = re.compile(r"([\"'`])[^\n]*?\1|\"\s*\"|'\s*'|`[^`]*`")
_LANG_KW = {
    "go": {"func", "if", "else", "for", "range", "return", "switch", "case", "default", "break", "continue", "var", "const", "type",
           "struct", "interface", "map", "chan", "go", "defer", "nil", "true", "false", "make", "append", "len", "cap", "string", "int",
           "error", "bool", "float64", "fmt"},
    "rust": {"fn", "let", "mut", "if", "else", "for", "while", "loop", "match", "return", "pub", "impl", "struct", "enum", "use", "self",
             "Self", "true", "false", "None", "Some", "Ok", "Err", "as", "in", "ref", "String", "Vec", "Option", "Result", "str", "usize",
             "i64", "u64", "u32", "i32", "f64", "bool"},
    "javascript": {"function", "const", "let", "var", "if", "else", "for", "while", "return", "new", "throw", "try", "catch", "switch",
                   "case", "default", "break", "continue", "async", "await", "class", "this", "null", "undefined", "true", "false", "of",
                   "in", "typeof"},
    "java": {"public", "private", "protected", "static", "final", "if", "else", "for", "while", "return", "new", "throw", "try", "catch",
             "switch", "case", "default", "break", "continue", "class", "this", "null", "true", "false", "int", "long", "double", "boolean",
             "String", "void", "List", "Map", "var"},
}


def shape(body, lang):
    """Token shape of a function body with identifiers and literals abstracted (keywords and punctuation kept)."""
    kw = _LANG_KW[lang]
    t = _STR.sub("S", body)
    t = _NUM.sub("N", t)
    t = _ID.sub(lambda m: m.group(0) if m.group(0) in kw or m.group(0) in ("S", "N") else "I", t)
    return re.sub(r"\s+", "", t)


def duplicate_functions(rels, lang, min_tokens=120):
    """Groups of functions with the same abstract shape (same control flow, different names/literals)."""
    seen = {}
    for fn in all_functions(rels, lang):
        s = shape(fn.body, lang)
        if len(s) < min_tokens:
            continue
        seen.setdefault(s, []).append(f"{fn.file}:{fn.name}")
    return [v for v in seen.values() if len(v) > 1]


def total_loc_text(src, lang):
    return sum(1 for ln in clean(src, lang).splitlines() if ln.strip())


def count(text_or_rels, pattern, lang=None, flags=0):
    """Count regex matches in cleaned text of a file list (or a raw string)."""
    pat = re.compile(pattern, flags)
    if isinstance(text_or_rels, str):
        return len(pat.findall(text_or_rels))
    n = 0
    for rel in text_or_rels:
        n += len(pat.findall(clean(read(rel), lang) if lang else read(rel)))
    return n


def total_loc(rels, lang):
    n = 0
    for rel in rels:
        n += sum(1 for ln in clean(read(rel), lang).splitlines() if ln.strip())
    return n


def report(problems):
    if problems:
        print("structure check failed:")
        for p in problems:
            print("  - " + p)
        raise SystemExit(1)
    print("structure check passed")
