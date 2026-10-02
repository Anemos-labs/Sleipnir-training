"""The undo tree."""
import config as C
from buffer import inverse


class Node:
    def __init__(self, nid, parent, prims, label):
        self.id = nid
        self.parent = parent
        self.prims = prims
        self.label = label
        self.children = []
        self.last = None  # the child redo goes to


class History:
    def __init__(self, buf):
        self.buf = buf
        self.reset()

    def reset(self):
        self.nodes = [Node(0, None, [], "(start)")]
        self.cur = self.nodes[0]

    def commit(self, prims, label):
        """Apply the primitive edits as one new node below the current one."""
        for p in prims:
            self.buf.apply(p)
        node = Node(len(self.nodes), self.cur, prims, label)
        self.nodes.append(node)
        self.cur.children.append(node)
        self.cur.last = node
        self.cur = node
        return node

    def up(self):
        node = self.cur
        for p in reversed(node.prims):
            self.buf.apply(inverse(p))
        node.parent.last = node
        self.cur = node.parent

    def down(self, child):
        for p in child.prims:
            self.buf.apply(p)
        self.cur.last = child
        self.cur = child

    def undo(self, n):
        done = 0
        while done < n and self.cur.parent is not None:
            self.up()
            done += 1
        return done

    def next_child(self):
        if not self.cur.children:
            return None
        return self.cur.last if C.REDO_MODE == "visited" else self.cur.children[-1]

    def redo(self, n):
        done = 0
        while done < n:
            child = self.next_child()
            if child is None:
                break
            self.down(child)
            done += 1
        return done

    def goto(self, target):
        path = []
        t = target
        while t is not None:
            path.append(t)
            t = t.parent
        on_path = {x.id for x in path}
        while self.cur.id not in on_path:
            self.up()
        down = path[: path.index(self.cur)][::-1]
        for child in down:
            self.down(child)

    def tree_lines(self):
        out = []

        def walk(node, depth):
            out.append("  " * depth + "%d %s" % (node.id, node.label) + (" <" if node is self.cur else ""))
            for c in node.children:
                walk(c, depth + 1)

        walk(self.nodes[0], 0)
        return out
