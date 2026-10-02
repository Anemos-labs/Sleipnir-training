"""Reading the document into blocks and wrapping their text into lines."""
import re

import config as C


class DocError(Exception):
    pass


class Block:
    def __init__(self, kind, line, text="", level=0, name="", height=0, joined=False):
        self.kind = kind  # para quote item heading figure break
        self.line = line
        self.text = text
        self.level = level
        self.name = name
        self.height = height
        self.joined = joined  # an item directly after (a line of) another item
        self.lines = []


HEADING = re.compile(r"^(#{1,3})( .*)?$")
FIGURE = re.compile(r"^@figure +([A-Za-z0-9_-]+) +([0-9]{1,2})$")


def parse(src):
    blocks = []
    cur = None  # the open paragraph, quote or item
    last_item_line = -10
    for n, raw in enumerate(src.split("\n"), 1):
        line = raw.rstrip()
        if not line.strip():
            cur = None
            continue
        if line == "@break":
            blocks.append(Block("break", n))
            cur = None
        elif line.startswith("@figure"):
            m = FIGURE.match(line)
            if not m or int(m.group(2)) < 1:
                raise DocError("line %d: bad figure" % n)
            blocks.append(Block("figure", n, name=m.group(1), height=int(m.group(2))))
            cur = None
        elif HEADING.match(line):
            m = HEADING.match(line)
            text = (m.group(2) or "").strip()
            if not text:
                raise DocError("line %d: empty heading" % n)
            blocks.append(Block("heading", n, text=text, level=len(m.group(1))))
            cur = None
        elif line.startswith(">"):
            body = line[1:]
            body = body[1:] if body.startswith(" ") else body
            if cur is not None and cur.kind == "quote":
                cur.text += " " + body.strip()
            else:
                cur = Block("quote", n, text=body.strip())
                blocks.append(cur)
        elif line.startswith(C.BULLET + " "):
            cur = Block("item", n, text=line[2:].strip(), joined=(last_item_line == n - 1))
            blocks.append(cur)
            last_item_line = n
        elif cur is not None and cur.kind == "item" and line.startswith("  "):
            cur.text += " " + line.strip()
            last_item_line = n
        elif cur is not None and cur.kind == "para":
            cur.text += " " + line.strip()
        else:
            cur = Block("para", n, text=line.strip())
            blocks.append(cur)
    return blocks


def wrap(text, width):
    """Greedy wrapping on single spaces; a word longer than the width is cut into pieces of `width` characters (or kept whole)."""
    lines, cur = [], ""
    for word in text.split():
        while len(word) > width and C.LONG_WORD == "cut":
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(word[:width])
            word = word[width:]
        if not cur:
            cur = word
        elif len(cur) + 1 + len(word) <= width:
            cur += " " + word
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [""]


def justify(line, width):
    """Pad the gaps of a line to `width`, giving the extra spaces to the leftmost gaps first."""
    words = line.split(" ")
    if len(words) < 2 or len(line) >= width:
        return line
    gaps = len(words) - 1
    base, more = divmod(width - len(line), gaps)
    out = words[0]
    for i, w in enumerate(words[1:]):
        out += " " * (1 + base + (1 if i < more else 0)) + w
    return out


def body_lines(text, width, do_justify):
    lines = wrap(text, width)
    if do_justify:
        lines = [justify(l, width) for l in lines[:-1]] + lines[-1:]
    return lines


def render(block, width, do_justify):
    k = block.kind
    if k == "heading":
        text = block.text.upper() if (block.level == 1 and C.UPPER_H1) else block.text
        lines = wrap(text, width)
        ch = {1: C.UL1, 2: C.UL2, 3: C.UL3}[block.level]
        return lines + ([ch * max(len(l) for l in lines)] if ch else [])
    if k == "figure":
        return ["[figure %s]" % block.name] + ["[ ]"] * (block.height - 1)
    if k == "quote":
        w = max(1, width - len(C.QUOTE))
        return [C.QUOTE + l for l in body_lines(block.text, w, do_justify)]
    if k == "item":
        lines = body_lines(block.text, max(1, width - 2), do_justify)
        return [C.ITEM_OUT + lines[0]] + ["  " + l for l in lines[1:]]
    return body_lines(block.text, width, do_justify)
