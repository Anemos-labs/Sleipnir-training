import java.util.ArrayList;
import java.util.List;

/** The undo tree. */
final class History {
    static final class Node {
        final int id;
        final Node parent;
        final List<TextBuffer.Prim> prims;
        final String label;
        final List<Node> children = new ArrayList<>();
        Node last;

        Node(int id, Node parent, List<TextBuffer.Prim> prims, String label) {
            this.id = id;
            this.parent = parent;
            this.prims = prims;
            this.label = label;
        }
    }

    final TextBuffer buf;
    List<Node> nodes = new ArrayList<>();
    Node cur;

    History(TextBuffer buf) {
        this.buf = buf;
        reset();
    }

    void reset() {
        nodes = new ArrayList<>();
        nodes.add(new Node(0, null, new ArrayList<>(), "(start)"));
        cur = nodes.get(0);
    }

    Node commit(List<TextBuffer.Prim> prims, String label) {
        for (TextBuffer.Prim p : prims) buf.apply(p);
        Node node = new Node(nodes.size(), cur, prims, label);
        nodes.add(node);
        cur.children.add(node);
        cur.last = node;
        cur = node;
        return node;
    }

    void up() {
        Node node = cur;
        for (int i = node.prims.size() - 1; i >= 0; i--) buf.apply(node.prims.get(i).inverse());
        node.parent.last = node;
        cur = node.parent;
    }

    void down(Node child) {
        for (TextBuffer.Prim p : child.prims) buf.apply(p);
        cur.last = child;
        cur = child;
    }

    void undo(int n) {
        for (int done = 0; done < n && cur.parent != null; done++) up();
    }

    Node nextChild() {
        if (cur.children.isEmpty()) return null;
        return Config.REDO_MODE.equals("visited") ? cur.last : cur.children.get(cur.children.size() - 1);
    }

    void redo(int n) {
        for (int done = 0; done < n; done++) {
            Node child = nextChild();
            if (child == null) break;
            down(child);
        }
    }

    void gotoNode(Node target) {
        List<Node> path = new ArrayList<>();
        for (Node t = target; t != null; t = t.parent) path.add(t);
        while (!path.contains(cur)) up();
        int idx = path.indexOf(cur);
        for (int i = idx - 1; i >= 0; i--) down(path.get(i));
    }

    List<String> treeLines() {
        List<String> out = new ArrayList<>();
        walk(nodes.get(0), 0, out);
        return out;
    }

    private void walk(Node node, int depth, List<String> out) {
        out.add("  ".repeat(depth) + node.id + " " + node.label + (node == cur ? " <" : ""));
        for (Node c : node.children) walk(c, depth + 1, out);
    }
}
