"""Text and HTML rendering."""
import re

import config as C


def chord_line(segs, shift_fn):
    out = ""
    col = 0
    for chord, text in segs:
        if chord is not None:
            c = shift_fn(chord)
            pos = max(col, len(out) + C.GAP) if out else col
            out += " " * (pos - len(out)) + c
        col += len(text)
    return out


def render_text(song, header, shift_fn):
    out = []
    if song.title is not None:
        out += [song.title, "=" * len(song.title)]
    out += header
    for sec in song.sections:
        out.append("")
        if sec.name or sec.repeat > 1:
            label = "[%s]" % sec.name if sec.name else ""
            if sec.repeat > 1:
                label += (" " if label else "") + "x%d" % sec.repeat
            out.append(label)
        for kind, data in sec.lines:
            if kind == "note":
                out.append("(note: %s)" % data)
            elif kind == "chords":
                out.append("  ".join(shift_fn(c) for c in data))
            else:
                lyric = "".join(t for _, t in data)
                cl = chord_line(data, shift_fn)
                if cl:
                    out.append(cl)
                if lyric.strip():
                    out.append(lyric)
                elif not cl:
                    out.append("")
    return out


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "section"


def render_html(song, header, shift_fn):
    out = ['<div class="song">']
    if song.title is not None:
        out.append("<h1>%s</h1>" % esc(song.title))
    for h in header:
        out.append('<p class="meta">%s</p>' % esc(h))
    for sec in song.sections:
        out.append('<section class="%s">' % slug(sec.name))
        if sec.name or sec.repeat > 1:
            title = sec.name + (" x%d" % sec.repeat if sec.repeat > 1 else "")
            out.append("<h2>%s</h2>" % esc(title.strip()))
        for kind, data in sec.lines:
            if kind == "note":
                out.append('<p class="note">%s</p>' % esc(data))
            elif kind == "chords":
                out.append('<p class="chords">%s</p>' % esc(" ".join(shift_fn(c) for c in data)))
            elif all(c is None for c, _ in data):
                out.append('<p class="line">%s</p>' % esc("".join(t for _, t in data)))
            else:
                parts = []
                for chord, text in data:
                    if chord is None and text == "":
                        continue
                    parts.append('<span class="seg"><b class="chord">%s</b>%s</span>' % (esc(shift_fn(chord)) if chord is not None else "", esc(text)))
                out.append('<p class="line">%s</p>' % "".join(parts))
        out.append("</section>")
    out.append("</div>")
    return out
