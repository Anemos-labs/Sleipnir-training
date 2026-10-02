'use strict';
// songsheet: renders a song written in the chord-sheet markup as text or HTML, optionally transposed.
const fs = require('fs');
const C = require('./config');
const { keyText, parseKey, transposeChord, usesFlats, mod12 } = require('./chords');
const { parseSong, SongError } = require('./parse');
const { renderHtml, renderText } = require('./render');

function fail(msg) {
  process.stdout.write(`error: ${msg}\n`);
  return 1;
}

function parseArgs(argv) {
  const opts = { format: 'text', transpose: null, to: null, prefer: 'sharps' };
  const known = ['--format', '--transpose'].concat(C.TO_OPT ? ['--to'] : [], C.PREFER_OPT ? ['--prefer'] : []);
  let i = 0;
  while (i < argv.length) {
    const a = argv[i];
    if (!known.includes(a)) throw new Error(`unknown option '${a}'`);
    if (i + 1 >= argv.length) throw new Error(`missing value for ${a}`);
    const v = argv[i + 1];
    i += 2;
    if (a === '--format') {
      if (v !== 'text' && v !== 'html') throw new Error(`bad value '${v}' for --format`);
      opts.format = v;
    } else if (a === '--transpose') {
      if (!/^[+-]?[0-9]{1,2}$/.test(v) || Math.abs(parseInt(v, 10)) > 11) throw new Error(`bad value '${v}' for --transpose`);
      opts.transpose = parseInt(v, 10);
    } else if (a === '--to') {
      if (parseKey(v) === null) throw new Error(`bad value '${v}' for --to`);
      opts.to = v;
    } else {
      if (v !== 'sharps' && v !== 'flats') throw new Error(`bad value '${v}' for --prefer`);
      opts.prefer = v;
    }
  }
  if (opts.transpose !== null && opts.to !== null) throw new Error('--transpose and --to cannot be combined');
  return opts;
}

function main(argv) {
  let opts;
  try {
    opts = parseArgs(argv);
  } catch (e) {
    return fail(e.message);
  }
  let song;
  try {
    song = parseSong(fs.readFileSync(0, 'utf8'));
  } catch (e) {
    if (!(e instanceof SongError)) throw e;
    return fail(e.message);
  }
  const keyIn = song.metaValue('key');
  const key = keyIn ? parseKey(keyIn) : null;
  let shift = opts.transpose || 0;
  if (opts.to !== null) {
    if (key === null) return fail('--to needs a key in the song');
    shift = mod12(parseKey(opts.to)[0] - key[0]);
    if (shift > 6) shift -= 12;
  }
  const capo = parseInt(song.metaValue('capo') || '0', 10);
  const newKey = key ? [mod12(key[0] + shift), key[1]] : null;
  let flats;
  if (newKey !== null) flats = usesFlats([mod12(newKey[0] - (C.CAPO_SHAPES ? capo : 0)), newKey[1]]);
  else flats = opts.prefer === 'flats';
  const chordShift = shift - (C.CAPO_SHAPES ? capo : 0);
  const shiftFn = (chord) => transposeChord(chord, chordShift, flats);
  const header = [];
  if (newKey !== null) header.push('Key: ' + keyText(newKey, C.KEY_OWN_SPELLING ? usesFlats(newKey) : flats));
  if (capo) header.push(`Capo: ${capo}`);
  for (const [name, value] of song.meta) {
    if (name !== 'key' && name !== 'capo') header.push(`${name[0].toUpperCase()}${name.slice(1)}: ${value}`);
  }
  const lines = (opts.format === 'html' ? renderHtml : renderText)(song, header, shiftFn);
  process.stdout.write(lines.map((l) => l + '\n').join(''));
  return 0;
}

process.exitCode = main(process.argv.slice(2));
