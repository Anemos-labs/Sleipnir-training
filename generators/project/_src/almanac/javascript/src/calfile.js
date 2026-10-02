'use strict';
// Reader for calendar.txt.
const C = require('./config');

const NAME_RE = /^[A-Za-z][A-Za-z0-9]*$/;
const NUM_RE = /^(0|[1-9][0-9]{0,5})$/;
const RESERVED = new Set(['from', 'count', 'of', 'last', 'after', 'end', 'days', 'weeks', 'months', 'years', 'every', 'monthly', 'yearly', 'blank']);

class CalendarError extends Error {}

function fail(n, msg) {
  throw new CalendarError(`calendar.txt:${n}: ${msg}`);
}

function number(tok, n, lo, hi) {
  if (!NUM_RE.test(tok)) fail(n, `bad number '${tok}'`);
  const v = parseInt(tok, 10);
  if (v < lo || v > hi) fail(n, `number '${tok}' out of range`);
  return v;
}

function badName(name) {
  return !NAME_RE.test(name) || RESERVED.has(name);
}

function readCalendar(text) {
  const cal = { week: [], months: [], inters: [], leap: null, leapmonth: null, epoch: null, leapday: null };
  const seen = new Set();
  let epochName = null;
  let epochLine = 0;
  const pending = [];

  const claim = (name, n) => {
    if (badName(name)) fail(n, `bad name '${name}'`);
    if (seen.has(name)) fail(n, `duplicate name '${name}'`);
    seen.add(name);
  };

  text.split('\n').forEach((raw, idx) => {
    const n = idx + 1;
    const w = raw.split('#')[0].split(/\s+/).filter((x) => x !== '');
    if (w.length === 0) return;
    const d = w[0];
    if (d === 'week') {
      if (w.length - 1 < 2 || w.length - 1 > 9) fail(n, 'bad line');
      const names = w.slice(1);
      for (const name of names) if (badName(name)) fail(n, `bad name '${name}'`);
      const dup = names.find((x) => names.indexOf(x) !== names.lastIndexOf(x));
      if (dup !== undefined) fail(n, `duplicate name '${dup}'`);
      if (cal.week.length) fail(n, "duplicate 'week'");
      cal.week = names;
    } else if (d === 'month') {
      if (w.length !== 3) fail(n, 'bad line');
      claim(w[1], n);
      cal.months.push([w[1], number(w[2], n, 1, C.MAX_MONTH)]);
    } else if (d === 'blank' || (d === 'leapday' && C.LEAP_STYLE === 'day')) {
      if (w.length !== 4 || w[2] !== 'after') fail(n, 'bad line');
      claim(w[1], n);
      if (d === 'leapday') {
        if (cal.leapday !== null) fail(n, "duplicate 'leapday'");
        if (cal.leap === null) fail(n, "no leap rule for 'leapday'");
        cal.leapday = w[1];
      }
      cal.inters.push([w[1], w[3], d === 'leapday']);
      pending.push([cal.inters.length - 1, w[3], n]);
    } else if (d === 'leapmonth' && C.LEAP_STYLE === 'month') {
      if (w.length !== 2) fail(n, 'bad line');
      if (cal.leapmonth !== null) fail(n, "duplicate 'leapmonth'");
      if (cal.leap === null) fail(n, "no leap rule for 'leapmonth'");
      const i = cal.months.findIndex((m) => m[0] === w[1]);
      if (i < 0) fail(n, `unknown month '${w[1]}'`);
      cal.leapmonth = i;
    } else if (d === 'leap') {
      if (w.length - 1 < 1 || w.length - 1 > C.LEAP_PARTS) fail(n, 'bad line');
      if (cal.leap !== null) fail(n, "duplicate 'leap'");
      const vals = w.slice(1).map((t) => number(t, n, 2, 9999));
      while (vals.length < 3) vals.push(null);
      cal.leap = vals;
    } else if (d === 'epoch') {
      if (w.length !== 2) fail(n, 'bad line');
      if (epochName !== null) fail(n, "duplicate 'epoch'");
      epochName = w[1];
      epochLine = n;
    } else {
      fail(n, `unknown directive '${d}'`);
    }
  });
  const names = cal.months.map((m) => m[0]);
  for (const [idx, anchor, n] of pending) {
    if (anchor === 'end') cal.inters[idx][1] = names.length;
    else if (names.includes(anchor)) cal.inters[idx][1] = names.indexOf(anchor);
    else fail(n, `unknown month '${anchor}'`);
  }
  if (!cal.week.length) throw new CalendarError("calendar.txt: missing 'week'");
  if (!cal.months.length) throw new CalendarError("calendar.txt: missing 'month'");
  if (epochName === null) throw new CalendarError("calendar.txt: missing 'epoch'");
  if (!cal.week.includes(epochName)) fail(epochLine, `unknown weekday '${epochName}'`);
  cal.epoch = cal.week.indexOf(epochName);
  return cal;
}

module.exports = { readCalendar, CalendarError };
