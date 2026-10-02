'use strict';
// The calendar model: year layout, day serial numbers, weekdays, date text.
const MAX_YEAR = 9999;
const NUM_RE = /^(0|[1-9][0-9]{0,5})$/;

class DateError extends Error {}

const mod = (a, n) => ((a % n) + n) % n;

class Model {
  constructor(cal) {
    this.cal = cal;
    this.layouts = { false: this.layout(false), true: this.layout(true) };
    this.yearStart = [0, 1]; // serial of the first day of year y
    this.mdaysBefore = [0, 0]; // weekday-bearing days before year y
    for (let y = 1; y <= MAX_YEAR; y++) {
      const lay = this.layouts[this.isLeap(y)];
      this.yearStart.push(this.yearStart[this.yearStart.length - 1] + lay.length);
      this.mdaysBefore.push(this.mdaysBefore[this.mdaysBefore.length - 1] + lay.mdays);
    }
    this.maxSerial = this.yearStart[MAX_YEAR + 1] - 1;
  }

  isLeap(y) {
    const [a, b, c] = this.cal.leap || [null, null, null];
    if (a === null || y % a !== 0) return false;
    if (b === null || y % b !== 0) return true;
    return c !== null && y % c === 0;
  }

  // Segments of a year in order: ['m', index, length] or ['b', name].
  layout(leap) {
    const cal = this.cal;
    const segs = [];
    const interAfter = (k) => {
      for (const [name, anchor, leapOnly] of cal.inters) {
        if (anchor === k && (leap || !leapOnly)) segs.push(['b', name]);
      }
    };
    cal.months.forEach(([, ln], i) => {
      segs.push(['m', i, ln + (leap && cal.leapmonth === i ? 1 : 0)]);
      interAfter(i);
    });
    interAfter(cal.months.length);
    let length = 0;
    let mdays = 0;
    for (const s of segs) {
      if (s[0] === 'm') {
        length += s[2];
        mdays += s[2];
      } else length += 1;
    }
    return { segs, length, mdays };
  }

  monthLen(i, y) {
    return this.cal.months[i][1] + (this.cal.leapmonth === i && this.isLeap(y) ? 1 : 0);
  }

  maxDay() {
    return Math.max(...this.cal.months.map((m) => m[1])) + (this.cal.leapmonth !== null ? 1 : 0);
  }

  // ['m', month index, day] or ['b', name] for day number doy (1-based) of year y.
  locate(y, doy) {
    let left = doy;
    for (const seg of this.layouts[this.isLeap(y)].segs) {
      if (seg[0] === 'm') {
        if (left <= seg[2]) return ['m', seg[1], left];
        left -= seg[2];
      } else {
        if (left === 1) return ['b', seg[1]];
        left -= 1;
      }
    }
    throw new DateError('internal');
  }

  doyOfMonthDay(y, i, d) {
    let n = 0;
    for (const seg of this.layouts[this.isLeap(y)].segs) {
      if (seg[0] === 'm') {
        if (seg[1] === i) return n + d;
        n += seg[2];
      } else n += 1;
    }
    throw new DateError('internal');
  }

  // Day number of a blank day in year y, or null if that year has no such day.
  doyOfBlank(y, name) {
    let n = 0;
    for (const seg of this.layouts[this.isLeap(y)].segs) {
      if (seg[0] === 'm') n += seg[2];
      else {
        n += 1;
        if (seg[1] === name) return n;
      }
    }
    return null;
  }

  serial(y, doy) {
    return this.yearStart[y] + doy - 1;
  }

  fromSerial(s) {
    if (s < 1 || s > this.maxSerial) throw new DateError(`date out of range (year 1 to ${MAX_YEAR})`);
    let lo = 1;
    let hi = MAX_YEAR;
    while (lo < hi) {
      const mid = Math.floor((lo + hi + 1) / 2);
      if (this.yearStart[mid] <= s) lo = mid;
      else hi = mid - 1;
    }
    return [lo, s - this.yearStart[lo] + 1];
  }

  // Weekday index of a month day, null for a blank day.
  weekday(y, doy) {
    const loc = this.locate(y, doy);
    if (loc[0] === 'b') return null;
    let before = 0;
    for (const seg of this.layouts[this.isLeap(y)].segs) {
      if (seg[0] === 'm') {
        if (seg[1] === loc[1]) break;
        before += seg[2];
      }
    }
    return mod(this.cal.epoch + this.mdaysBefore[y] + before + loc[2] - 1, this.cal.week.length);
  }

  show(y, doy) {
    const loc = this.locate(y, doy);
    const total = this.layouts[this.isLeap(y)].length;
    if (loc[0] === 'b') return `${loc[1]} ${y} [${doy}/${total}]`;
    const wd = this.cal.week[this.weekday(y, doy)];
    return `${wd} ${loc[2]} ${this.cal.months[loc[1]][0]} ${y} [${doy}/${total}]`;
  }

  parseYear(tok) {
    if (!NUM_RE.test(tok)) throw new DateError('bad date');
    const y = parseInt(tok, 10);
    if (y < 1 || y > MAX_YEAR) throw new DateError(`year ${y} out of range (1..${MAX_YEAR})`);
    return y;
  }

  // Parse a date from the front of toks ('D MONTH Y' or 'NAME Y'): [y, doy, tokens used].
  parseDate(toks) {
    if (toks.length === 0) throw new DateError('bad date');
    const names = this.cal.months.map((m) => m[0]);
    if (/^[0-9]+$/.test(toks[0])) {
      if (toks.length < 3 || !NUM_RE.test(toks[0])) throw new DateError('bad date');
      if (!names.includes(toks[1])) throw new DateError(`unknown name '${toks[1]}'`);
      const y = this.parseYear(toks[2]);
      const i = names.indexOf(toks[1]);
      const d = parseInt(toks[0], 10);
      const ln = this.monthLen(i, y);
      if (d < 1 || d > ln) throw new DateError(`day ${d} out of range for ${toks[1]} ${y} (1..${ln})`);
      return [y, this.doyOfMonthDay(y, i, d), 3];
    }
    if (toks.length < 2) throw new DateError('bad date');
    if (!this.cal.inters.some((x) => x[0] === toks[0])) throw new DateError(`unknown name '${toks[0]}'`);
    const y = this.parseYear(toks[1]);
    const doy = this.doyOfBlank(y, toks[0]);
    if (doy === null) throw new DateError(`no such day ${toks[0]} ${y}`);
    return [y, doy, 2];
  }
}

module.exports = { Model, DateError, MAX_YEAR, mod };
