'use strict';
// trials: runs a suite of tests with scoped fixtures from suite.txt.
const fs = require('fs');
const C = require('./config');
const { Runner } = require('./runner');
const { readSuite, SuiteError } = require('./suite');

function main(argv) {
  const opts = { only: null, failFast: false, retries: 0, skipSlow: false, list: false };
  try {
    for (let i = 0; i < argv.length; ) {
      const a = argv[i];
      if (a === '--only') {
        if (i + 1 >= argv.length) throw new Error('missing value for --only');
        opts.only = argv[i + 1];
        i += 2;
      } else if (a === '--retries' && C.HAS_RETRIES) {
        if (i + 1 >= argv.length) throw new Error('missing value for --retries');
        if (!/^[0-5]$/.test(argv[i + 1])) throw new Error(`bad value '${argv[i + 1]}' for --retries`);
        opts.retries = parseInt(argv[i + 1], 10);
        i += 2;
      } else if (a === '--fail-fast') {
        opts.failFast = true;
        i += 1;
      } else if (a === '--skip-slow' && C.HAS_SKIP_SLOW) {
        opts.skipSlow = true;
        i += 1;
      } else if (a === '--list') {
        opts.list = true;
        i += 1;
      } else throw new Error(`unknown option '${a}'`);
    }
  } catch (e) {
    process.stdout.write(`error: ${e.message}\n`);
    return 1;
  }
  let text;
  try {
    text = fs.readFileSync('suite.txt', 'utf8');
  } catch (e) {
    process.stdout.write('error: cannot read suite.txt\n');
    return 1;
  }
  let suite;
  try {
    suite = readSuite(text);
  } catch (e) {
    if (!(e instanceof SuiteError)) throw e;
    process.stdout.write(`error: ${e.message}\n`);
    return 1;
  }
  const out = [];
  const runner = new Runner(suite.fixtures, suite.tests, suite.modules, opts, (l) => out.push(l));
  let status;
  if (opts.list) {
    for (const [t, name] of runner.expanded()) {
      if (opts.only === null || name.includes(opts.only)) out.push(`${t.module}/${name}` + (t.marks.length ? `  [${t.marks.join(' ')}]` : ''));
    }
    status = 0;
  } else status = runner.run() ? 1 : 0;
  process.stdout.write(out.map((l) => l + '\n').join(''));
  return status;
}

process.exitCode = main(process.argv.slice(2));
