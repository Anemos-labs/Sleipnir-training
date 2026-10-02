"""The text buffer with marks.  Every change is a sequence of primitive edits: ('d', pos, removed text) and ('i', pos, inserted text)."""
import config as C


class Buffer:
    def __init__(self):
        self.text = ""
        self.marks = {}  # name -> [pos, gravity]

    def reset(self, text):
        self.text = text
        self.marks = {}

    def apply(self, prim):
        kind, pos, s = prim
        if kind == "i":
            self.text = self.text[:pos] + s + self.text[pos:]
            for m in self.marks.values():
                if m[0] > pos or (m[0] == pos and m[1] == "right"):
                    m[0] += len(s)
        else:
            self.text = self.text[:pos] + self.text[pos + len(s):]
            for m in self.marks.values():
                if m[0] > pos + len(s):
                    m[0] -= len(s)
                elif m[0] > pos:
                    m[0] = pos


def inverse(prim):
    kind, pos, s = prim
    return ("d" if kind == "i" else "i", pos, s)
