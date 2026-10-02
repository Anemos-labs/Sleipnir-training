'use strict';
// The script commands.
const C = require('./config');
const { DateError, MAX_YEAR, mod } = require('./model');

const INT_RE = /^[+-]?(0|[1-9][0-9]{0,5})$/;
const UNITS = ['days', 'weeks', 'months', 'years'];
const MAX_COUNT = 50;

const countText = (n, noun) => `${n} ${noun}${Math.abs(n) === 1 ? '' : 's'}`;
const isDigits = (t) => /^[0-9]+$/.test(t);

class Commands {
  constructor(model) {
    this.m = model;
    this.cal = model.cal;
  }

  dateOnly(toks) {
    const [y, doy, used] = this.m.parseDate(toks);
    if (used !== toks.length) throw new DateError('bad date');
    return [y, doy];
  }

  specAndRest(toks) {
    const [y, doy, used] = this.m.parseDate(toks);
    return [y, doy, toks.slice(used)];
  }

  integer(tok) {
    if (!INT_RE.test(tok)) throw new DateError(`bad number '${tok}'`);
    return parseInt(tok, 10);
  }

  monthIndex(name) {
    const i = this.cal.months.findIndex((m) => m[0] === name);
    if (i < 0) throw new DateError(`unknown name '${name}'`);
    return i;
  }

  weekdayIndex(name) {
    const i = this.cal.week.indexOf(name);
    if (i < 0) throw new DateError(`unknown name '${name}'`);
    return i;
  }

  date(toks) {
    const [y, doy] = this.dateOnly(toks);
    return [this.m.show(y, doy)];
  }

  serial(toks) {
    const [y, doy] = this.dateOnly(toks);
    return [String(this.m.serial(y, doy))];
  }

  year(toks) {
    if (toks.length !== 1) throw new DateError('usage: year YEAR');
    const y = this.m.parseYear(toks[0]);
    const lay = this.m.layouts[this.m.isLeap(y)];
    const leap = this.m.isLeap(y);
    const out = [`year ${y}: ${lay.length} days, ${leap ? 'leap' : 'common'}`];
    for (const seg of lay.segs) out.push(seg[0] === 'm' ? `  ${this.cal.months[seg[1]][0]} ${seg[2]}` : `  ~ ${seg[1]}`);
    return out;
  }

  diff(toks) {
    const [y1, d1, rest] = this.specAndRest(toks);
    const [y2, d2] = this.dateOnly(rest);
    return [countText(this.m.serial(y2, d2) - this.m.serial(y1, d1), 'day')];
  }

  add(toks) {
    const [y, doy, rest] = this.specAndRest(toks);
    if (rest.length !== 2) throw new DateError('usage: add DATE N days|weeks|months|years');
    const n = this.integer(rest[0]);
    const unit = rest[1];
    if (!UNITS.includes(unit)) throw new DateError(`bad unit '${unit}'`);
    const s = this.m.serial(y, doy);
    if (unit === 'days' || unit === 'weeks') {
      const [ny, ndoy] = this.m.fromSerial(s + n * (unit === 'weeks' ? this.cal.week.length : 1));
      return [this.m.show(ny, ndoy)];
    }
    const loc = this.m.locate(y, doy);
    if (unit === 'months') {
      if (loc[0] === 'b') throw new DateError('cannot add months to a blank day');
      const nm = this.cal.months.length;
      const total = y * nm + loc[1] + n;
      return [this.place(Math.floor(total / nm), mod(total, nm), loc[2])];
    }
    const ny = y + n;
    if (ny < 1 || ny > MAX_YEAR) throw new DateError(`date out of range (year 1 to ${MAX_YEAR})`);
    if (loc[0] === 'b') {
      const d = this.m.doyOfBlank(ny, loc[1]);
      if (d === null) throw new DateError(`no such day ${loc[1]} ${ny}`);
      return [this.m.show(ny, d)];
    }
    return [this.place(ny, loc[1], loc[2])];
  }

  // Day d of month i in year y, with the overflow rule for days the month does not have.
  place(y, i, d) {
    if (y < 1 || y > MAX_YEAR) throw new DateError(`date out of range (year 1 to ${MAX_YEAR})`);
    const ln = this.m.monthLen(i, y);
    if (d <= ln) return this.m.show(y, this.m.doyOfMonthDay(y, i, d));
    if (C.OVERFLOW === 'clamp') return this.m.show(y, this.m.doyOfMonthDay(y, i, ln));
    if (C.OVERFLOW === 'spill') {
      const [ny, ndoy] = this.m.fromSerial(this.m.serial(y, this.m.doyOfMonthDay(y, i, 1)) + d - 1);
      return this.m.show(ny, ndoy);
    }
    throw new DateError(`no such day ${d} ${this.cal.months[i][0]} ${y}`);
  }

  // [y, doy] of the k-th (or last, k == 0) month day with weekday wd in month i of year y, or null.
  nthInMonth(y, i, k, wd) {
    const ln = this.m.monthLen(i, y);
    const first = this.m.doyOfMonthDay(y, i, 1);
    const w = this.cal.week.length;
    const d1 = mod(wd - this.m.weekday(y, first), w) + 1;
    if (d1 > ln) return null;
    const d = k === 0 ? d1 + Math.floor((ln - d1) / w) * w : d1 + (k - 1) * w;
    return d <= ln ? [y, first + d - 1] : null;
  }

  nth(toks) {
    if (toks.length !== 5 || toks[2] !== 'of') throw new DateError('usage: nth K|last WEEKDAY of MONTH YEAR');
    let k;
    if (toks[0] === 'last') k = 0;
    else if (/^[1-9]$/.test(toks[0])) k = parseInt(toks[0], 10);
    else throw new DateError(`bad number '${toks[0]}'`);
    const wd = this.weekdayIndex(toks[1]);
    const i = this.monthIndex(toks[3]);
    const y = this.m.parseYear(toks[4]);
    const r = this.nthInMonth(y, i, k, wd);
    return [r ? this.m.show(r[0], r[1]) : 'none'];
  }

  next(toks) {
    const k = toks.indexOf('from');
    if (k < 0) throw new DateError('usage: next RULE from DATE [count N]');
    const rule = toks.slice(0, k);
    const [y0, d0, rest] = this.specAndRest(toks.slice(k + 1));
    let count = 5;
    if (rest.length) {
      if (rest.length !== 2 || rest[0] !== 'count') throw new DateError('usage: next RULE from DATE [count N]');
      if (!/^[1-9][0-9]{0,2}$/.test(rest[1]) || parseInt(rest[1], 10) > MAX_COUNT) throw new DateError(`bad count '${rest[1]}'`);
      count = parseInt(rest[1], 10);
    }
    const start = this.m.serial(y0, d0);
    const out = [];
    const gen = this.occurrences(rule, y0, start);
    for (const s of gen) {
      out.push(this.m.show(...this.m.fromSerial(s)));
      if (out.length === count) break;
    }
    return out;
  }

  // Serial numbers of the occurrences (>= start) of a rule, in order; ends after the last year.
  occurrences(rule, y0, start) {
    const m = this.m;
    const pos = /^[1-9][0-9]{0,2}$/;
    if (rule.length === 3 && rule[0] === 'every' && (rule[2] === 'days' || rule[2] === 'weeks')) {
      if (!pos.test(rule[1])) throw new DateError(`bad number '${rule[1]}'`);
      return this.every(start, parseInt(rule[1], 10) * (rule[2] === 'weeks' ? this.cal.week.length : 1));
    }
    if (rule.length === 2 && rule[0] === 'monthly' && isDigits(rule[1])) {
      if (!pos.test(rule[1]) || parseInt(rule[1], 10) > m.maxDay()) throw new DateError(`day ${rule[1]} never occurs`);
      return this.monthlyDay(parseInt(rule[1], 10), y0, start);
    }
    if (rule.length === 3 && rule[0] === 'monthly') {
      let k;
      if (rule[1] === 'last') k = 0;
      else if (/^[1-9]$/.test(rule[1])) k = parseInt(rule[1], 10);
      else throw new DateError(`bad number '${rule[1]}'`);
      return this.monthlyWeekday(k, this.weekdayIndex(rule[2]), y0, start);
    }
    if (rule.length === 3 && rule[0] === 'yearly') {
      if (!pos.test(rule[1])) throw new DateError(`bad number '${rule[1]}'`);
      const i = this.monthIndex(rule[2]);
      if (parseInt(rule[1], 10) > this.cal.months[i][1] + (this.cal.leapmonth === i ? 1 : 0)) throw new DateError(`day ${rule[1]} never occurs`);
      return this.yearly(parseInt(rule[1], 10), i, y0, start);
    }
    if (rule.length === 2 && rule[0] === 'blank') {
      if (!this.cal.inters.some((x) => x[0] === rule[1])) throw new DateError(`unknown name '${rule[1]}'`);
      return this.blank(rule[1], y0, start);
    }
    throw new DateError('bad rule');
  }

  *every(start, step) {
    for (let s = start; s <= this.m.maxSerial; s += step) yield s;
  }

  *monthlyDay(d, y0, start) {
    const m = this.m;
    for (let y = y0; y <= MAX_YEAR; y++) {
      for (let i = 0; i < this.cal.months.length; i++) {
        const ln = m.monthLen(i, y);
        if (d > ln && C.SHORT_MONTH === 'skip') continue;
        const s = m.serial(y, m.doyOfMonthDay(y, i, Math.min(d, ln)));
        if (s >= start) yield s;
      }
    }
  }

  *monthlyWeekday(k, wd, y0, start) {
    for (let y = y0; y <= MAX_YEAR; y++) {
      for (let i = 0; i < this.cal.months.length; i++) {
        const r = this.nthInMonth(y, i, k, wd);
        if (r && this.m.serial(r[0], r[1]) >= start) yield this.m.serial(r[0], r[1]);
      }
    }
  }

  *yearly(d, i, y0, start) {
    const m = this.m;
    for (let y = y0; y <= MAX_YEAR; y++) {
      if (d <= m.monthLen(i, y)) {
        const s = m.serial(y, m.doyOfMonthDay(y, i, d));
        if (s >= start) yield s;
      }
    }
  }

  *blank(name, y0, start) {
    for (let y = y0; y <= MAX_YEAR; y++) {
      const doy = this.m.doyOfBlank(y, name);
      if (doy !== null && this.m.serial(y, doy) >= start) yield this.m.serial(y, doy);
    }
  }
}

module.exports = { Commands };
