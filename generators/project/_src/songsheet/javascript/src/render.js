'use strict';
// Text and HTML rendering.
const C = require('./config');

function chordLine(segs, shiftFn) {
  let out = '';
  let col = 0;
  for (const [chord, text] of segs) {
    if (chord !== null) {
      const c = shiftFn(chord);
      const pos = out ? Math.max(col, out.length + C.GAP) : col;
      out += ' '.repeat(pos - out.length) + c;
    }
    col += text.length;
  }
  return out;
}

function renderText(song, header, shiftFn) {
  const out = [];
  if (song.title !== null) out.push(song.title, '='.repeat(song.title.length));
  out.push(...header);
  for (const sec of song.sections) {
    out.push('');
    if (sec.name || sec.repeat > 1) {
      let label = sec.name ? `[${sec.name}]` : '';
      if (sec.repeat > 1) label += (label ? ' ' : '') + `x${sec.repeat}`;
      out.push(label);
    }
    for (const [kind, data] of sec.lines) {
      if (kind === 'note') out.push(`(note: ${data})`);
      else if (kind === 'chords') out.push(data.map(shiftFn).join('  '));
      else {
        const lyric = data.map((s) => s[1]).join('');
        const cl = chordLine(data, shiftFn);
        if (cl) out.push(cl);
        if (lyric.trim()) out.push(lyric);
        else if (!cl) out.push('');
      }
    }
  }
  return out;
}

const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function slug(name) {
  const s = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  return s || 'section';
}

function renderHtml(song, header, shiftFn) {
  const out = ['<div class="song">'];
  if (song.title !== null) out.push(`<h1>${esc(song.title)}</h1>`);
  for (const h of header) out.push(`<p class="meta">${esc(h)}</p>`);
  for (const sec of song.sections) {
    out.push(`<section class="${slug(sec.name)}">`);
    if (sec.name || sec.repeat > 1) {
      const title = sec.name + (sec.repeat > 1 ? ` x${sec.repeat}` : '');
      out.push(`<h2>${esc(title.trim())}</h2>`);
    }
    for (const [kind, data] of sec.lines) {
      if (kind === 'note') out.push(`<p class="note">${esc(data)}</p>`);
      else if (kind === 'chords') out.push(`<p class="chords">${esc(data.map(shiftFn).join(' '))}</p>`);
      else if (data.every((s) => s[0] === null)) out.push(`<p class="line">${esc(data.map((s) => s[1]).join(''))}</p>`);
      else {
        let parts = '';
        for (const [chord, text] of data) {
          if (chord === null && text === '') continue;
          parts += `<span class="seg"><b class="chord">${chord !== null ? esc(shiftFn(chord)) : ''}</b>${esc(text)}</span>`;
        }
        out.push(`<p class="line">${parts}</p>`);
      }
    }
    out.push('</section>');
  }
  out.push('</div>');
  return out;
}

module.exports = { renderText, renderHtml };
