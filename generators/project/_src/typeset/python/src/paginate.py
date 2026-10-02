"""Pagination: placing blocks on pages of a fixed number of lines."""
import config as C


def next_min(blocks, i, orphans):
    """Lines the block after position i must be able to put on the same page as a heading at i (None: no requirement)."""
    if i + 1 >= len(blocks):
        return None
    n = blocks[i + 1]
    if n.kind == "break":
        return None
    if n.kind == "figure":
        return len(n.lines)
    if n.kind == "heading":
        rest = next_min(blocks, i + 1, orphans)
        return len(n.lines) + (1 + rest if rest is not None else 0)
    return min(len(n.lines), orphans)


def paginate(blocks, height, orphans, widows):
    pages = [[]]
    prev = None  # kind of the last block placed on the current page

    def sep_for(b):
        if not pages[-1]:
            return 0
        return 0 if (b.kind == "item" and b.joined and prev == "item") else 1

    def new_page():
        nonlocal prev
        pages.append([])
        prev = None

    for i, b in enumerate(blocks):
        if b.kind == "break":
            if pages[-1]:
                new_page()
            continue
        lines = list(b.lines)
        if b.kind in ("heading", "figure"):
            need = len(lines)
            if b.kind == "heading" and C.KEEP:
                nm = next_min(blocks, i, orphans)
                if nm is not None:
                    need += 1 + nm
            if pages[-1] and need > height - len(pages[-1]) - sep_for(b):
                new_page()
            pages[-1] += [""] * sep_for(b) + lines
            prev = b.kind
            continue
        while True:
            s = sep_for(b)
            remaining = height - len(pages[-1]) - s
            if len(lines) <= remaining:
                pages[-1] += [""] * s + lines
                prev = b.kind
                break
            ks = [k for k in range(min(remaining, len(lines) - 1), 0, -1) if k >= orphans and len(lines) - k >= widows]
            if ks:
                pages[-1] += [""] * s + lines[: ks[0]]
                lines = lines[ks[0]:]
            elif not pages[-1]:
                pages[-1] += lines[:height]  # nothing satisfies the rules even on an empty page: fill it
                lines = lines[height:]
            new_page()
    if len(pages) > 1 and not pages[-1]:
        pages.pop()
    return pages
