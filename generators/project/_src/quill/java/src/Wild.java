import java.util.ArrayList;
import java.util.List;

/** The wildcard pattern language of find / sub / count. */
final class Wild {
    static final class WildError extends Exception {
        WildError(String m) {
            super(m);
        }
    }

    static final class Tok {
        final String kind; // lit any star digit set bol eol
        final char ch;
        final boolean neg;
        final List<char[]> ranges;

        Tok(String kind, char ch, boolean neg, List<char[]> ranges) {
            this.kind = kind;
            this.ch = ch;
            this.neg = neg;
            this.ranges = ranges;
        }
    }

    private static char escaped(char e) {
        if (e == 'n') return '\n';
        if (e == 't') return '\t';
        if (e == 's') return ' ';
        return e;
    }

    static List<Tok> compile(String p) throws WildError {
        List<Tok> toks = new ArrayList<>();
        int i = 0;
        int n = p.length();
        while (i < n) {
            char c = p.charAt(i);
            if (c == '\\') {
                if (i + 1 >= n) throw new WildError("trailing backslash");
                toks.add(new Tok("lit", escaped(p.charAt(i + 1)), false, null));
                i += 2;
            } else if (c == '?') {
                toks.add(new Tok("any", ' ', false, null));
                i++;
            } else if (c == '*') {
                toks.add(new Tok("star", ' ', false, null));
                i++;
            } else if (c == '#' && Config.HAS_DIGIT) {
                toks.add(new Tok("digit", ' ', false, null));
                i++;
            } else if (c == '[' && Config.HAS_CLASSES) {
                int j = i + 1;
                boolean neg = j < n && p.charAt(j) == '^';
                if (neg) j++;
                List<char[]> ranges = new ArrayList<>();
                while (j < n && p.charAt(j) != ']') {
                    char ch = p.charAt(j);
                    if (ch == '\\') {
                        if (j + 1 >= n) throw new WildError("trailing backslash");
                        ch = escaped(p.charAt(j + 1));
                        j++;
                    }
                    if (j + 2 < n && p.charAt(j + 1) == '-' && p.charAt(j + 2) != ']') {
                        char hi = p.charAt(j + 2);
                        j += 2;
                        if (hi == '\\') {
                            if (j + 1 >= n) throw new WildError("trailing backslash");
                            hi = escaped(p.charAt(j + 1));
                            j++;
                        }
                        if (hi < ch) throw new WildError("bad range");
                        ranges.add(new char[] {ch, hi});
                    } else {
                        ranges.add(new char[] {ch, ch});
                    }
                    j++;
                }
                if (j >= n) throw new WildError("unterminated class");
                if (ranges.isEmpty()) throw new WildError("empty class");
                toks.add(new Tok("set", ' ', neg, ranges));
                i = j + 1;
            } else if (c == '^' && Config.HAS_ANCHORS && i == 0) {
                toks.add(new Tok("bol", ' ', false, null));
                i++;
            } else if (c == '$' && Config.HAS_ANCHORS && i == n - 1) {
                toks.add(new Tok("eol", ' ', false, null));
                i++;
            } else {
                toks.add(new Tok("lit", c, false, null));
                i++;
            }
        }
        return toks;
    }

    /** End position of a match of toks[ti..] starting at pos (greedy options first), or -1. */
    static int matchHere(List<Tok> toks, int ti, String text, int pos) {
        while (ti < toks.size()) {
            Tok t = toks.get(ti);
            switch (t.kind) {
                case "star": {
                    int end = pos;
                    while (end < text.length() && text.charAt(end) != '\n') end++;
                    for (int e = end; e >= pos; e--) {
                        int r = matchHere(toks, ti + 1, text, e);
                        if (r >= 0) return r;
                    }
                    return -1;
                }
                case "bol":
                    if (!(pos == 0 || text.charAt(pos - 1) == '\n')) return -1;
                    break;
                case "eol":
                    if (!(pos == text.length() || text.charAt(pos) == '\n')) return -1;
                    break;
                default: {
                    if (pos >= text.length()) return -1;
                    char ch = text.charAt(pos);
                    boolean ok;
                    if (t.kind.equals("lit")) ok = ch == t.ch;
                    else if (t.kind.equals("any")) ok = ch != '\n';
                    else if (t.kind.equals("digit")) ok = ch >= '0' && ch <= '9';
                    else {
                        boolean inside = false;
                        for (char[] r : t.ranges) if (r[0] <= ch && ch <= r[1]) inside = true;
                        ok = inside != t.neg;
                    }
                    if (!ok) return -1;
                    pos++;
                }
            }
            ti++;
        }
        return pos;
    }

    /** {start, length} of the first match at or after start, or null. */
    static int[] findFrom(List<Tok> toks, String text, int start) {
        for (int s = start; s <= text.length(); s++) {
            int e = matchHere(toks, 0, text, s);
            if (e >= 0) return new int[] {s, e - s};
        }
        return null;
    }

    /** Non-overlapping matches, left to right; after an empty match the search resumes one character later. */
    static List<int[]> findAll(List<Tok> toks, String text) {
        List<int[]> out = new ArrayList<>();
        int pos = 0;
        while (pos <= text.length()) {
            int[] m = findFrom(toks, text, pos);
            if (m == null) break;
            out.add(m);
            pos = m[1] > 0 ? m[0] + m[1] : m[0] + 1;
        }
        return out;
    }
}
