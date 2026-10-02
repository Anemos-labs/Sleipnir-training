import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;

/** quill: a scripted text editor core (buffer, marks, undo tree, wildcard search). */
public class Main {
    static final class CmdError extends Exception {
        CmdError(String m) {
            super(m);
        }
    }

    private final TextBuffer buf = new TextBuffer();
    private final History hist = new History(buf);
    private String reg = null;
    private final StringBuilder out = new StringBuilder();
    private int errors = 0;

    private void say(String line) {
        out.append(line).append('\n');
    }

    static String unescape(String text) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            if (c == '\\' && i + 1 < text.length() && "nt\\".indexOf(text.charAt(i + 1)) >= 0) {
                char e = text.charAt(i + 1);
                sb.append(e == 'n' ? '\n' : e == 't' ? '\t' : '\\');
                i++;
            } else {
                sb.append(c);
            }
        }
        return sb.toString();
    }

    static String escape(String text) {
        return text.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t");
    }

    static int num(String tok) throws CmdError {
        if (!tok.matches("[0-9]{1,9}")) throw new CmdError("bad number '" + tok + "'");
        return Integer.parseInt(tok);
    }

    private int pos(String tok) throws CmdError {
        int p = num(tok);
        if (p > buf.text.length()) throw new CmdError("position " + p + " out of range (0.." + buf.text.length() + ")");
        return p;
    }

    private int[] span(String ptok, String ltok) throws CmdError {
        int p = num(ptok);
        int ln = num(ltok);
        if (ln < 1) throw new CmdError("bad length '" + ltok + "'");
        if (p + ln > buf.text.length()) throw new CmdError("range " + p + "+" + ln + " beyond end (" + buf.text.length() + ")");
        return new int[] {p, ln};
    }

    private void done(History.Node node) {
        say("node " + node.id);
    }

    private List<Wild.Tok> pattern(String tok) throws CmdError {
        try {
            return Wild.compile(tok);
        } catch (Wild.WildError e) {
            throw new CmdError("bad pattern: " + e.getMessage());
        }
    }

    private List<TextBuffer.Prim> prims(TextBuffer.Prim... ps) {
        List<TextBuffer.Prim> l = new ArrayList<>();
        for (TextBuffer.Prim p : ps) if (p != null) l.add(p);
        return l;
    }

    private void cLoad(String rest) {
        buf.reset(unescape(rest));
        hist.reset();
        say("loaded " + buf.text.length() + " chars");
    }

    private void cIns(List<String> args, String rest) throws CmdError {
        if (args.isEmpty()) throw new CmdError("usage: ins POS TEXT");
        int p = pos(args.get(0));
        String text = unescape(rest);
        if (text.isEmpty()) throw new CmdError("nothing to insert");
        done(hist.commit(prims(new TextBuffer.Prim('i', p, text)), "ins@" + p + "+" + text.length()));
    }

    private void cDel(String[] args) throws CmdError {
        if (args.length != 2) throw new CmdError("usage: del POS LEN");
        int[] s = span(args[0], args[1]);
        done(hist.commit(prims(new TextBuffer.Prim('d', s[0], buf.text.substring(s[0], s[0] + s[1]))), "del@" + s[0] + "-" + s[1]));
    }

    private void cRep(List<String> args, String rest) throws CmdError {
        if (args.size() < 2) throw new CmdError("usage: rep POS LEN TEXT");
        int[] s = span(args.get(0), args.get(1));
        String text = unescape(rest);
        List<TextBuffer.Prim> l = prims(new TextBuffer.Prim('d', s[0], buf.text.substring(s[0], s[0] + s[1])), text.isEmpty() ? null : new TextBuffer.Prim('i', s[0], text));
        done(hist.commit(l, "rep@" + s[0] + "-" + s[1] + "+" + text.length()));
    }

    private void cShow() {
        if (buf.text.isEmpty()) {
            say("(empty)");
            return;
        }
        String[] lines = buf.text.split("\n", -1);
        for (int i = 0; i < lines.length; i++) say((i + 1) + "|" + lines[i]);
    }

    private void cMark(String[] args) throws CmdError {
        if (args.length != 2 && args.length != 3) throw new CmdError("usage: mark NAME POS [left|right]");
        if (!args[0].matches("[A-Za-z][A-Za-z0-9_]{0,15}")) throw new CmdError("bad mark name '" + args[0] + "'");
        int p = pos(args[1]);
        String g = Config.DEFAULT_GRAVITY;
        if (args.length == 3) {
            if (!args[2].equals("left") && !args[2].equals("right")) throw new CmdError("bad gravity '" + args[2] + "'");
            g = args[2];
        }
        buf.marks.put(args[0], new TextBuffer.Mark(p, g));
        say("mark " + args[0] + "=" + p + " " + g);
    }

    private void cUnmark(String[] args) throws CmdError {
        if (args.length != 1) throw new CmdError("usage: unmark NAME");
        if (!buf.marks.containsKey(args[0])) throw new CmdError("no such mark '" + args[0] + "'");
        buf.marks.remove(args[0]);
        say("unmarked " + args[0]);
    }

    private void cMarks() {
        if (buf.marks.isEmpty()) say("(no marks)");
        for (var e : buf.marks.entrySet()) say(e.getKey() + "=" + e.getValue().pos + " " + e.getValue().gravity);
    }

    private void cAt(String[] args) throws CmdError {
        if (args.length != 1) throw new CmdError("usage: at NAME");
        TextBuffer.Mark m = buf.marks.get(args[0]);
        if (m == null) throw new CmdError("no such mark '" + args[0] + "'");
        say(String.valueOf(m.pos));
    }

    private void cUndo(String[] args) throws CmdError {
        if (args.length > 1) throw new CmdError("usage: undo [N]");
        int n = args.length > 0 ? num(args[0]) : 1;
        if (n < 1) throw new CmdError("bad number '0'");
        if (hist.cur.parent == null) throw new CmdError("nothing to undo");
        hist.undo(n);
        say("node " + hist.cur.id);
    }

    private void cRedo(String[] args) throws CmdError {
        if (args.length > 1) throw new CmdError("usage: redo [N]");
        int n = args.length > 0 ? num(args[0]) : 1;
        if (n < 1) throw new CmdError("bad number '0'");
        if (hist.nextChild() == null) throw new CmdError("nothing to redo");
        hist.redo(n);
        say("node " + hist.cur.id);
    }

    private void cGoto(String[] args) throws CmdError {
        if (args.length != 1) throw new CmdError("usage: goto ID");
        int n = num(args[0]);
        if (n >= hist.nodes.size()) throw new CmdError("no such node " + n);
        hist.gotoNode(hist.nodes.get(n));
        say("node " + n);
    }

    private void cTree() {
        for (String l : hist.treeLines()) say(l);
    }

    private void cFind(String[] args) throws CmdError {
        if ((args.length != 1 && args.length != 3) || (args.length == 3 && !args[1].equals("from"))) throw new CmdError("usage: find PATTERN [from POS]");
        List<Wild.Tok> toks = pattern(args[0]);
        int start = args.length == 3 ? pos(args[2]) : 0;
        int[] m = Wild.findFrom(toks, buf.text, start);
        say(m == null ? "not found" : "found " + m[0] + " " + m[1]);
    }

    private void cCount(String[] args) throws CmdError {
        if (args.length != 1) throw new CmdError("usage: count PATTERN");
        say(String.valueOf(Wild.findAll(pattern(args[0]), buf.text).size()));
    }

    private void cSub(List<String> args, String rest, boolean every) throws CmdError {
        if (args.isEmpty()) throw new CmdError("usage: " + (every ? "suball" : "sub") + " PATTERN TEXT");
        List<Wild.Tok> toks = pattern(args.get(0));
        String text = unescape(rest);
        List<int[]> ms = Wild.findAll(toks, buf.text);
        if (!every && ms.size() > 1) ms = ms.subList(0, 1);
        if (ms.isEmpty()) {
            say("0 replaced");
            return;
        }
        if (every && !Config.SUB_GROUP) {
            for (int k = ms.size() - 1; k >= 0; k--) {
                int s = ms.get(k)[0];
                int ln = ms.get(k)[1];
                List<TextBuffer.Prim> one = prims(ln > 0 ? new TextBuffer.Prim('d', s, buf.text.substring(s, s + ln)) : null, text.isEmpty() ? null : new TextBuffer.Prim('i', s, text));
                if (one.isEmpty()) continue;
                hist.commit(one, "sub@" + s + "-" + ln + "+" + text.length());
            }
            say(ms.size() + " replaced, node " + hist.cur.id);
            return;
        }
        List<TextBuffer.Prim> ps = new ArrayList<>();
        for (int k = ms.size() - 1; k >= 0; k--) {
            int s = ms.get(k)[0];
            int ln = ms.get(k)[1];
            if (ln > 0) ps.add(new TextBuffer.Prim('d', s, buf.text.substring(s, s + ln)));
            if (!text.isEmpty()) ps.add(new TextBuffer.Prim('i', s, text));
        }
        if (ps.isEmpty()) {
            say(ms.size() + " replaced");
            return;
        }
        hist.commit(ps, (every ? "suball" : "sub") + " x" + ms.size());
        say(ms.size() + " replaced, node " + hist.cur.id);
    }

    private void cYank(String[] args) throws CmdError {
        if (args.length != 2) throw new CmdError("usage: yank POS LEN");
        int[] s = span(args[0], args[1]);
        reg = buf.text.substring(s[0], s[0] + s[1]);
        say("yanked " + s[1]);
    }

    private void cPut(String[] args) throws CmdError {
        if (args.length != 1) throw new CmdError("usage: put POS");
        if (reg == null) throw new CmdError("register is empty");
        int p = pos(args[0]);
        done(hist.commit(prims(new TextBuffer.Prim('i', p, reg)), "put@" + p + "+" + reg.length()));
    }

    private static String[] words(String s) {
        String t = s.trim();
        return t.isEmpty() ? new String[0] : t.split("\\s+");
    }

    void run(String raw) {
        String line = raw.strip();
        if (line.isEmpty() || line.startsWith("#")) return;
        int sp = line.indexOf(' ');
        String cmd = sp < 0 ? line : line.substring(0, sp);
        String rest = sp < 0 ? "" : line.substring(sp + 1);
        String[] args = words(rest);
        try {
            switch (cmd) {
                case "load":
                    cLoad(rest);
                    break;
                case "ins":
                case "rep":
                case "sub":
                case "suball": {
                    int nargs = cmd.equals("rep") ? 2 : 1;
                    String tail = rest.replaceFirst("^ +", "");
                    List<String> ws = new ArrayList<>();
                    for (int k = 0; k < nargs; k++) {
                        int i = tail.indexOf(' ');
                        String w;
                        if (i < 0) {
                            w = tail;
                            tail = "";
                        } else {
                            w = tail.substring(0, i);
                            tail = tail.substring(i + 1);
                        }
                        if (!w.isEmpty()) ws.add(w);
                    }
                    if (cmd.equals("ins")) cIns(ws, tail);
                    else if (cmd.equals("rep")) cRep(ws, tail);
                    else cSub(ws, tail, cmd.equals("suball"));
                    break;
                }
                case "del":
                    cDel(args);
                    break;
                case "show":
                    cShow();
                    break;
                case "text":
                    say("\"" + escape(buf.text) + "\"");
                    break;
                case "mark":
                    cMark(args);
                    break;
                case "unmark":
                    cUnmark(args);
                    break;
                case "marks":
                    cMarks();
                    break;
                case "at":
                    cAt(args);
                    break;
                case "undo":
                    cUndo(args);
                    break;
                case "redo":
                    cRedo(args);
                    break;
                case "goto":
                    cGoto(args);
                    break;
                case "tree":
                    cTree();
                    break;
                case "find":
                    cFind(args);
                    break;
                case "count":
                    cCount(args);
                    break;
                case "yank":
                    if (!Config.HAS_REGISTER) throw new CmdError("unknown command 'yank'");
                    cYank(args);
                    break;
                case "put":
                    if (!Config.HAS_REGISTER) throw new CmdError("unknown command 'put'");
                    cPut(args);
                    break;
                default:
                    throw new CmdError("unknown command '" + cmd + "'");
            }
        } catch (CmdError e) {
            say("error: " + e.getMessage());
            errors++;
        }
    }

    public static void main(String[] argv) throws IOException {
        InputStream in = System.in;
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        byte[] chunk = new byte[8192];
        int n;
        while ((n = in.read(chunk)) > 0) bos.write(chunk, 0, n);
        Main ed = new Main();
        for (String raw : bos.toString("UTF-8").split("\n", -1)) ed.run(raw);
        System.out.print(ed.out);
        System.out.flush();
        System.exit(ed.errors > 0 ? 1 : 0);
    }
}
