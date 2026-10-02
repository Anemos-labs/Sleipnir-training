'use strict';
// Chord names and transposition.
const C = require('./config');

const SHARPS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
const FLATS = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B'];
const LETTER = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
const CHORD_RE = /^([A-G][#b]?)([A-Za-z0-9+#()-]*)(?:\/([A-G][#b]?))?$/;
const KEY_RE = /^([A-G][#b]?)(m?)$/;

const mod12 = (n) => ((n % 12) + 12) % 12;

function semitone(note) {
  let n = LETTER[note[0]];
  if (note.length === 2) n += note[1] === '#' ? 1 : -1;
  return mod12(n);
}

// [semitone, minor] or null
function parseKey(text) {
  const m = KEY_RE.exec(text);
  return m ? [semitone(m[1]), m[2] === 'm'] : null;
}

const FLAT_SET = new Set(C.FLAT_KEYS.map((k) => parseKey(k).join(',')));

// True if chords written in `key` are spelled with flats.
function usesFlats(key) {
  return FLAT_SET.has(key.join(','));
}

function nameOf(n, flats) {
  return (flats ? FLATS : SHARPS)[mod12(n)];
}

function keyText(key, flats) {
  return nameOf(key[0], flats) + (key[1] ? 'm' : '');
}

// Transposed chord text; text that is not a chord is returned unchanged.
function transposeChord(text, shift, flats) {
  const m = CHORD_RE.exec(text);
  if (!m) return text;
  let out = nameOf(semitone(m[1]) + shift, flats) + m[2];
  if (m[3]) out += '/' + nameOf(semitone(m[3]) + shift, flats);
  return out;
}

module.exports = { parseKey, usesFlats, keyText, transposeChord, mod12 };
