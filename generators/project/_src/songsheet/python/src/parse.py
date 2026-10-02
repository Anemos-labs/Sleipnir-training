"""Reading a song."""
import re

import config as C
from chords import parse_key


class SongError(Exception):
    pass


class Section:
    def __init__(self, name, repeat):
        self.name = name
        self.repeat = repeat
        self.lines = []  # ("lyric", [(chord|None, text)]) / ("chords", [chord]) / ("note", text)


class Song:
    def __init__(self):
        self.title = None
        self.meta = []  # (name, value) in file order
        self.sections = []

    def meta_value(self, name):
        for k, v in self.meta:
            if k == name:
                return v
        return None


def split_lyric(text, n):
    """Lyric text with {chord} markers -> [(chord or None, text)]."""
    segs = []
    cur_chord, buf = None, []
    i = 0
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text) and text[i + 1] in "{}":
            buf.append(text[i + 1])
            i += 2
        elif c == "{":
            j = text.find("}", i + 1)
            if j < 0:
                raise SongError("line %d: unclosed '{'" % n)
            chord = text[i + 1:j].strip()
            if not chord:
                raise SongError("line %d: empty chord" % n)
            if cur_chord is not None or buf:
                segs.append((cur_chord, "".join(buf)))
            cur_chord, buf = chord, []
            i = j + 1
        else:
            buf.append(c)
            i += 1
    if cur_chord is not None or buf or not segs:
        segs.append((cur_chord, "".join(buf)))
    return segs


def parse_song(text):
    song = Song()
    current = None
    named = {}
    for n, raw in enumerate(text.split("\n"), 1):
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("//"):
            continue
        m = re.match(r"^==\s*(.*?)\s*==$", line)
        if m:
            if song.title is not None:
                raise SongError("line %d: second title" % n)
            if not m.group(1):
                raise SongError("line %d: empty title" % n)
            song.title = m.group(1)
            continue
        if line.startswith(":"):
            parts = line[1:].split(None, 1)
            if len(parts) != 2:
                raise SongError("line %d: bad meta line" % n)
            name, value = parts[0].lower(), parts[1].strip()
            if name == "key" and parse_key(value) is None:
                raise SongError("line %d: bad key '%s'" % (n, value))
            if name == "capo" and not (re.match(r"^[0-9]{1,2}$", value) and 0 <= int(value) <= 11):
                raise SongError("line %d: bad capo '%s'" % (n, value))
            if name in ("key", "capo") and song.meta_value(name) is not None:
                raise SongError("line %d: duplicate '%s'" % (n, name))
            song.meta.append((name, value))
            continue
        m = re.match(r"^\[\[(.+?)\]\](?:\s+x([0-9]))?$", line)
        if m:
            name = m.group(1).strip()
            rep = int(m.group(2)) if m.group(2) else 1
            if m.group(2) and (not C.REPEATS or rep < 2):
                if not C.REPEATS:
                    raise SongError("line %d: repeat marks are not supported" % n)
                raise SongError("line %d: bad repeat count" % n)
            current = Section(name, rep)
            song.sections.append(current)
            named[name] = current
            continue
        if line.startswith(">>"):
            if not C.RECALL:
                raise SongError("line %d: recall is not supported" % n)
            name = line[2:].strip()
            if name not in named:
                raise SongError("line %d: unknown section '%s'" % (n, name))
            sec = Section(name + " (again)", 1)
            sec.lines = list(named[name].lines)
            song.sections.append(sec)
            current = sec
            continue
        if current is None:
            current = Section("", 1)
            song.sections.append(current)
        if line.startswith("!"):
            current.lines.append(("note", line[1:].strip()))
        elif line.startswith(". ") or line == ".":
            current.lines.append(("chords", line[1:].split()))
        else:
            current.lines.append(("lyric", split_lyric(line, n)))
    return song
