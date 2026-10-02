"""songsheet: renders a song written in the chord-sheet markup as text or HTML, optionally transposed."""
import re
import sys

import config as C
from chords import key_text, parse_key, semitone, transpose_chord, uses_flats
from parse import SongError, parse_song
from render import render_html, render_text


def fail(msg):
    print("error: " + msg)
    return 1


def parse_args(argv):
    opts = {"format": "text", "transpose": None, "to": None, "prefer": "sharps"}
    i = 0
    while i < len(argv):
        a = argv[i]
        known = ["--format", "--transpose"] + (["--to"] if C.TO_OPT else []) + (["--prefer"] if C.PREFER_OPT else [])
        if a in known:
            if i + 1 >= len(argv):
                raise ValueError("missing value for %s" % a)
            v = argv[i + 1]
            i += 2
            if a == "--format":
                if v not in ("text", "html"):
                    raise ValueError("bad value '%s' for --format" % v)
                opts["format"] = v
            elif a == "--transpose":
                if not re.match(r"^[+-]?[0-9]{1,2}$", v) or abs(int(v)) > 11:
                    raise ValueError("bad value '%s' for --transpose" % v)
                opts["transpose"] = int(v)
            elif a == "--to":
                if parse_key(v) is None:
                    raise ValueError("bad value '%s' for --to" % v)
                opts["to"] = v
            else:
                if v not in ("sharps", "flats"):
                    raise ValueError("bad value '%s' for --prefer" % v)
                opts["prefer"] = v
        else:
            raise ValueError("unknown option '%s'" % a)
    if opts["transpose"] is not None and opts["to"] is not None:
        raise ValueError("--transpose and --to cannot be combined")
    return opts


def main(argv):
    try:
        opts = parse_args(argv)
    except ValueError as e:
        return fail(str(e))
    try:
        song = parse_song(sys.stdin.read())
    except SongError as e:
        return fail(str(e))
    key_text_in = song.meta_value("key")
    key = parse_key(key_text_in) if key_text_in else None
    shift = opts["transpose"] or 0
    if opts["to"] is not None:
        if key is None:
            return fail("--to needs a key in the song")
        shift = (parse_key(opts["to"])[0] - key[0]) % 12
        if shift > 6:
            shift -= 12
    capo = int(song.meta_value("capo") or 0)
    new_key = ((key[0] + shift) % 12, key[1]) if key else None
    written = None
    if new_key is not None:
        written = ((new_key[0] - (capo if C.CAPO_SHAPES else 0)) % 12, new_key[1])
        flats = uses_flats(written)
    else:
        flats = opts["prefer"] == "flats"
    chord_shift = shift - (capo if C.CAPO_SHAPES else 0)

    def shift_fn(chord):
        return transpose_chord(chord, chord_shift, flats)

    header = []
    if new_key is not None:
        header.append("Key: " + key_text(new_key, uses_flats(new_key) if C.KEY_OWN_SPELLING else flats))
    if capo:
        header.append("Capo: %d" % capo)
    for name, value in song.meta:
        if name not in ("key", "capo"):
            header.append("%s: %s" % (name[:1].upper() + name[1:], value))
    lines = (render_html if opts["format"] == "html" else render_text)(song, header, shift_fn)
    sys.stdout.write("".join(l + "\n" for l in lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
