import java.util.Map;
import java.util.TreeMap;

/** The text buffer with marks. Every change is a sequence of primitive edits (kind 'd' or 'i', position, text). */
final class TextBuffer {
    static final class Prim {
        final char kind;
        final int pos;
        final String s;

        Prim(char kind, int pos, String s) {
            this.kind = kind;
            this.pos = pos;
            this.s = s;
        }

        Prim inverse() {
            return new Prim(kind == 'i' ? 'd' : 'i', pos, s);
        }
    }

    static final class Mark {
        int pos;
        final String gravity;

        Mark(int pos, String gravity) {
            this.pos = pos;
            this.gravity = gravity;
        }
    }

    String text = "";
    final Map<String, Mark> marks = new TreeMap<>();

    void reset(String t) {
        text = t;
        marks.clear();
    }

    void apply(Prim p) {
        if (p.kind == 'i') {
            text = text.substring(0, p.pos) + p.s + text.substring(p.pos);
            for (Mark m : marks.values()) {
                if (m.pos > p.pos || (m.pos == p.pos && m.gravity.equals("right"))) m.pos += p.s.length();
            }
        } else {
            text = text.substring(0, p.pos) + text.substring(p.pos + p.s.length());
            for (Mark m : marks.values()) {
                if (m.pos > p.pos + p.s.length()) m.pos -= p.s.length();
                else if (m.pos > p.pos) m.pos = p.pos;
            }
        }
    }
}
