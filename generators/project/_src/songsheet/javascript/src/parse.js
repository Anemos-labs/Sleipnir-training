'use strict';
// Reading a song.
const C = require('./config');
const { parseKey } = require('./chords');

class SongError extends Error {}

class Section {
  constructor(name, repeat) {
    this.name = name;
    this.repeat = repeat;
    this.lines = []; // ['lyric', [[chord|null, text]]] / ['chords', [chord]] / ['note', text]
  }
}

class Song {
  constructor() {
    this.title = null;
    this.meta = [];
    this.sections = [];
  }

  metaValue(name) {
    const e = this.meta.find((x) => x[0] === name);
    return e ? e[1] : null;
  }
}

// Lyric text with {chord} markers -> [[chord|null, text]]
function splitLyric(text, n) {
  const segs = [];
  let curChord = null;
  let buf = '';
  let i = 0;
  while (i < text.length) {
    const c = text[i];
    if (c === '\\' && i + 1 < text.length && (text[i + 1] === '{' || text[i + 1] === '}')) {
      buf += text[i + 1];
      i += 2;
    } else if (c === '{') {
      const j = text.indexOf('}', i + 1);
      if (j < 0) throw new SongError(`line ${n}: unclosed '{'`);
      const chord = text.slice(i + 1, j).trim();
      if (!chord) throw new SongError(`line ${n}: empty chord`);
      if (curChord !== null || buf !== '') segs.push([curChord, buf]);
      curChord = chord;
      buf = '';
      i = j + 1;
    } else {
      buf += c;
      i += 1;
    }
  }
  if (curChord !== null || buf !== '' || segs.length === 0) segs.push([curChord, buf]);
  return segs;
}

function parseSong(text) {
  const song = new Song();
  let current = null;
  const named = new Map();
  text.split('\n').forEach((raw, idx) => {
    const n = idx + 1;
    const line = raw.replace(/\s+$/, '');
    if (!line.trim()) return;
    if (line.startsWith('//')) return;
    let m = /^==\s*(.*?)\s*==$/.exec(line);
    if (m) {
      if (song.title !== null) throw new SongError(`line ${n}: second title`);
      if (!m[1]) throw new SongError(`line ${n}: empty title`);
      song.title = m[1];
      return;
    }
    if (line.startsWith(':')) {
      const body = line.slice(1).trim();
      const sp = body.search(/\s/);
      if (sp < 0) throw new SongError(`line ${n}: bad meta line`);
      const name = body.slice(0, sp).toLowerCase();
      const value = body.slice(sp).trim();
      if (name === 'key' && parseKey(value) === null) throw new SongError(`line ${n}: bad key '${value}'`);
      if (name === 'capo' && !(/^[0-9]{1,2}$/.test(value) && parseInt(value, 10) <= 11)) throw new SongError(`line ${n}: bad capo '${value}'`);
      if ((name === 'key' || name === 'capo') && song.metaValue(name) !== null) throw new SongError(`line ${n}: duplicate '${name}'`);
      song.meta.push([name, value]);
      return;
    }
    m = /^\[\[(.+?)\]\](?:\s+x([0-9]))?$/.exec(line);
    if (m) {
      const name = m[1].trim();
      const rep = m[2] ? parseInt(m[2], 10) : 1;
      if (m[2] && (!C.REPEATS || rep < 2)) {
        if (!C.REPEATS) throw new SongError(`line ${n}: repeat marks are not supported`);
        throw new SongError(`line ${n}: bad repeat count`);
      }
      current = new Section(name, rep);
      song.sections.push(current);
      named.set(name, current);
      return;
    }
    if (line.startsWith('>>')) {
      if (!C.RECALL) throw new SongError(`line ${n}: recall is not supported`);
      const name = line.slice(2).trim();
      if (!named.has(name)) throw new SongError(`line ${n}: unknown section '${name}'`);
      const sec = new Section(`${name} (again)`, 1);
      sec.lines = named.get(name).lines.slice();
      song.sections.push(sec);
      current = sec;
      return;
    }
    if (current === null) {
      current = new Section('', 1);
      song.sections.push(current);
    }
    if (line.startsWith('!')) current.lines.push(['note', line.slice(1).trim()]);
    else if (line.startsWith('. ') || line === '.') current.lines.push(['chords', line.slice(1).split(/\s+/).filter(Boolean)]);
    else current.lines.push(['lyric', splitLyric(line, n)]);
  });
  return song;
}

module.exports = { parseSong, SongError };
