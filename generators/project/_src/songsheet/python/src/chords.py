"""Chord names and transposition."""
import re

import config as C

SHARPS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLATS = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
LETTER = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
CHORD_RE = re.compile(r"^([A-G][#b]?)([A-Za-z0-9+#()-]*)(?:/([A-G][#b]?))?$")
KEY_RE = re.compile(r"^([A-G][#b]?)(m?)$")


def semitone(note):
    n = LETTER[note[0]]
    if len(note) == 2:
        n += 1 if note[1] == "#" else -1
    return n % 12


def parse_key(text):
    """(semitone, minor) or None."""
    m = KEY_RE.match(text)
    if not m:
        return None
    return semitone(m.group(1)), m.group(2) == "m"


FLAT_SET = {parse_key(k) for k in C.FLAT_KEYS}


def uses_flats(key):
    """True if chords written in `key` (semitone, minor) are spelled with flats."""
    return key in FLAT_SET


def name_of(n, flats):
    return (FLATS if flats else SHARPS)[n % 12]


def key_text(key, flats):
    return name_of(key[0], flats) + ("m" if key[1] else "")


def transpose_chord(text, shift, flats):
    """Transposed chord text; text that is not a chord is returned unchanged."""
    m = CHORD_RE.match(text)
    if not m:
        return text
    root, quality, bass = m.groups()
    out = name_of(semitone(root) + shift, flats) + quality
    if bass:
        out += "/" + name_of(semitone(bass) + shift, flats)
    return out
