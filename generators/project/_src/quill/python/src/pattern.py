"""The wildcard pattern language of find / sub / count."""
import config as C


class PatternError(Exception):
    pass


def compile_pattern(p):
    """Pattern text -> list of tokens: ('lit', c) ('any',) ('star',) ('digit',) ('set', negate, [(lo, hi)...]) ('bol',) ('eol',)."""
    toks = []
    i, n = 0, len(p)
    while i < n:
        c = p[i]
        if c == "\\":
            if i + 1 >= n:
                raise PatternError("trailing backslash")
            e = p[i + 1]
            toks.append(("lit", {"n": "\n", "t": "\t", "s": " "}.get(e, e)))
            i += 2
        elif c == "?":
            toks.append(("any",))
            i += 1
        elif c == "*":
            toks.append(("star",))
            i += 1
        elif c == "#" and C.HAS_DIGIT:
            toks.append(("digit",))
            i += 1
        elif c == "[" and C.HAS_CLASSES:
            j = i + 1
            neg = j < n and p[j] == "^"
            if neg:
                j += 1
            ranges = []
            while j < n and p[j] != "]":
                ch = p[j]
                if ch == "\\":
                    if j + 1 >= n:
                        raise PatternError("trailing backslash")
                    ch = {"n": "\n", "t": "\t", "s": " "}.get(p[j + 1], p[j + 1])
                    j += 1
                if j + 2 < n and p[j + 1] == "-" and p[j + 2] != "]":
                    hi = p[j + 2]
                    j += 2
                    if hi == "\\":
                        if j + 1 >= n:
                            raise PatternError("trailing backslash")
                        hi = {"n": "\n", "t": "\t", "s": " "}.get(p[j + 1], p[j + 1])
                        j += 1
                    if hi < ch:
                        raise PatternError("bad range")
                    ranges.append((ch, hi))
                else:
                    ranges.append((ch, ch))
                j += 1
            if j >= n:
                raise PatternError("unterminated class")
            if not ranges:
                raise PatternError("empty class")
            toks.append(("set", neg, ranges))
            i = j + 1
        elif c == "^" and C.HAS_ANCHORS and i == 0:
            toks.append(("bol",))
            i += 1
        elif c == "$" and C.HAS_ANCHORS and i == n - 1:
            toks.append(("eol",))
            i += 1
        else:
            toks.append(("lit", c))
            i += 1
    return toks


def match_here(toks, ti, text, pos):
    """End position of a match of toks[ti:] starting at pos, trying greedy options first; None if there is none."""
    while ti < len(toks):
        t = toks[ti]
        k = t[0]
        if k == "star":
            end = pos
            while end < len(text) and text[end] != "\n":
                end += 1
            for e in range(end, pos - 1, -1):
                r = match_here(toks, ti + 1, text, e)
                if r is not None:
                    return r
            return None
        if k == "bol":
            if not (pos == 0 or text[pos - 1] == "\n"):
                return None
        elif k == "eol":
            if not (pos == len(text) or text[pos] == "\n"):
                return None
        else:
            if pos >= len(text):
                return None
            ch = text[pos]
            if k == "lit":
                ok = ch == t[1]
            elif k == "any":
                ok = ch != "\n"
            elif k == "digit":
                ok = "0" <= ch <= "9"
            else:
                inside = any(lo <= ch <= hi for lo, hi in t[2])
                ok = inside != t[1]
            if not ok:
                return None
            pos += 1
        ti += 1
    return pos


def find_from(toks, text, start):
    """(start, length) of the first match at or after start, or None."""
    for s in range(start, len(text) + 1):
        e = match_here(toks, 0, text, s)
        if e is not None:
            return s, e - s
    return None


def find_all(toks, text, start=0):
    """Non-overlapping matches, left to right; after an empty match the search resumes one character later."""
    out = []
    pos = start
    while pos <= len(text):
        m = find_from(toks, text, pos)
        if m is None:
            break
        out.append(m)
        pos = m[0] + m[1] if m[1] > 0 else m[0] + 1
    return out
