'use strict';
// Command-line front end: reads calendar.txt and a script on standard input.
const fs = require('fs');
const C = require('./config');
const { readCalendar, CalendarError } = require('./calfile');
const { Commands } = require('./commands');
const { Model, DateError } = require('./model');

function main() {
  let text;
  try {
    text = fs.readFileSync('calendar.txt', 'utf8');
  } catch (e) {
    process.stdout.write('error: cannot read calendar.txt\n');
    return 1;
  }
  let cal;
  try {
    cal = readCalendar(text);
  } catch (e) {
    if (!(e instanceof CalendarError)) throw e;
    process.stdout.write(`error: ${e.message}\n`);
    return 1;
  }
  const cmds = new Commands(new Model(cal));
  const table = { date: cmds.date, add: cmds.add, diff: cmds.diff, nth: cmds.nth, next: cmds.next };
  if (C.HAS_SERIAL) table.serial = cmds.serial;
  if (C.HAS_YEAR) table.year = cmds.year;
  let status = 0;
  const out = [];
  for (const raw of fs.readFileSync(0, 'utf8').split('\n')) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const toks = line.split(/\s+/);
    try {
      if (!Object.prototype.hasOwnProperty.call(table, toks[0])) throw new DateError(`unknown command '${toks[0]}'`);
      for (const l of table[toks[0]].call(cmds, toks.slice(1))) out.push(l);
    } catch (e) {
      if (!(e instanceof DateError)) throw e;
      out.push(`error: ${e.message}`);
      status = 1;
    }
  }
  process.stdout.write(out.map((l) => l + '\n').join(''));
  return status;
}

process.exitCode = main();
