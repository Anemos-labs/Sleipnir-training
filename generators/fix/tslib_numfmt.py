"""Locale-aware number, compact and byte-size formatting (typescript): bugs injected into a formatting library."""
from fx import Lib, dd
from generators.fix._lang2 import PACKAGE_JSON, TS_NODE_SHIM, TS_VERIFY, TSCONFIG, register_libs

README = dd(r'''
    # numfmt

    Number formatting for a dashboard that shows figures in five regional styles. TypeScript, no dependencies.
    `import { resolve, groupDigits } from './src/locale'`, `import { formatNumber, scaleRound } from './src/format'`,
    `import { formatCompact, formatBytes } from './src/compact'`.

    ## `src/locale.ts`

    A locale is `{ group, decimal, groupSizes }`. The five locales:

    | tag | group separator | decimal | digit groups (right to left) |
    |---|---|---|---|
    | `en` | `,` | `.` | 3, 3, 3 ... |
    | `de` | `.` | `,` | 3, 3, 3 ... |
    | `fr` | narrow no-break space ` ` | `,` | 3, 3, 3 ... |
    | `ch` | typographic apostrophe `’` | `.` | 3, 3, 3 ... |
    | `in` | `,` | `.` | 3, then 2, 2, 2 ... (`12,34,567`) |

    * `resolve(tag)`: the locale for a tag such as `'en'`, `'EN'` or `'de-AT'`: the part before the first `-` or `_`, lower-cased.
      An unknown language is a `RangeError`.
    * `groupDigits(digits, locale)`: puts the group separator into a string of digits (the integer part, no sign) following
      the locale's group sizes: the rightmost group has `groupSizes[0]` digits, every further group `groupSizes[1]`. Short
      strings are left alone: `groupDigits('1234', en)` is `'1,234'`, `groupDigits('123', en)` is `'123'`.

    ## `src/format.ts`

    * `scaleRound(x, digits)`: `x >= 0` multiplied by `10 ** digits` and rounded to an integer, **ties to even** (`2.5` becomes
      `2`, `3.5` becomes `4`, `0.125` with 2 digits becomes `12`). The tie test is exact on the product: `diff = scaled - floor`.
    * `formatNumber(n, tag = 'en', opts = {})`: options `maxFrac` (default `2`), `minFrac` (default `0`), `accounting` and `plus`.
      `n` must be finite (`RangeError`), `abs(n)` below `1e15` (`RangeError`); `maxFrac` an integer `0..8` and `minFrac` an
      integer `0..maxFrac` (`RangeError`). The absolute value is rounded with `scaleRound(abs, maxFrac)`; the fraction is
      then stripped of trailing zeros but never below `minFrac` digits; the integer part is grouped; the separators come from
      the locale. A negative number whose *rounded* value is not zero gets a `-` in front, or, with `accounting`, is written in
      parentheses without the minus (`(1,234.5)`). With `plus` a positive rounded value gets a `+`. Zero never has a sign.

    ## `src/compact.ts`

    * `formatCompact(n, tag = 'en')`: a short form with the suffixes `K` (thousand), `M`, `B` (billion, `1e9`) and `T` (`1e12`).
      Numbers whose rounded integer is below 1000 are written as integers (ties to even). Otherwise the value is divided by
      the largest unit that fits and rounded to one decimal with `scaleRound`; a trailing `.0` is dropped; if rounding reaches
      `1000` of a unit, the next unit up is used instead (`999950` is `'1M'`, not `'1000K'`; for `T` there is no next unit).
      Negative numbers get a `-`. The decimal separator is the locale's. `n` must be finite (`RangeError`).
    * `formatBytes(n, opts = {})`: `n` is an integer `>= 0` (`RangeError`). Units are `B, kB, MB, GB, TB, PB` with base `1000`, or
      with `opts.binary` `B, KiB, MiB, GiB, TiB, PiB` with base `1024`. The unit is the largest one for which the value is at least
      `1` (`PB` is the last). Bytes are written as integers; other values are rounded to one decimal with `scaleRound` and a
      trailing `.0` is dropped; if rounding reaches the base, the next unit is used (`999950` is `'1 MB'`). The text is value, space,
      unit, with the decimal separator of `opts.locale` (default `'en'`).
''')

LOCALE = dd(r'''
    export interface Locale {
      group: string;
      decimal: string;
      groupSizes: [number, number];
    }

    const LOCALES: Record<string, Locale> = {
      en: { group: ",", decimal: ".", groupSizes: [3, 3] },
      de: { group: ".", decimal: ",", groupSizes: [3, 3] },
      fr: { group: " ", decimal: ",", groupSizes: [3, 3] },
      ch: { group: "’", decimal: ".", groupSizes: [3, 3] },
      in: { group: ",", decimal: ".", groupSizes: [3, 2] },
    };

    export function resolve(tag: string): Locale {
      const lang = tag.split(/[-_]/)[0].toLowerCase();
      if (!Object.prototype.hasOwnProperty.call(LOCALES, lang)) throw new RangeError(`unknown locale ${tag}`);
      return LOCALES[lang];
    }

    export function groupDigits(digits: string, locale: Locale): string {
      const [first, rest] = locale.groupSizes;
      if (digits.length <= first) return digits;
      const groups: string[] = [digits.slice(digits.length - first)];
      let end = digits.length - first;
      while (end > 0) {
        groups.unshift(digits.slice(Math.max(0, end - rest), end));
        end -= rest;
      }
      return groups.join(locale.group);
    }
''')

FORMAT = dd(r'''
    import { groupDigits, resolve } from "./locale";

    export interface FormatOptions {
      minFrac?: number;
      maxFrac?: number;
      accounting?: boolean;
      plus?: boolean;
    }

    export function scaleRound(x: number, digits: number): number {
      const scaled = x * 10 ** digits;
      const floor = Math.floor(scaled);
      const diff = scaled - floor;
      if (diff > 0.5) return floor + 1;
      if (diff < 0.5) return floor;
      return floor % 2 === 0 ? floor : floor + 1;
    }

    export function formatNumber(n: number, tag = "en", opts: FormatOptions = {}): string {
      const locale = resolve(tag);
      const maxFrac = opts.maxFrac ?? 2;
      const minFrac = opts.minFrac ?? 0;
      if (!Number.isFinite(n) || Math.abs(n) >= 1e15) throw new RangeError("n must be finite and below 1e15");
      if (!Number.isInteger(maxFrac) || maxFrac < 0 || maxFrac > 8) throw new RangeError("maxFrac must be an integer from 0 to 8");
      if (!Number.isInteger(minFrac) || minFrac < 0 || minFrac > maxFrac) throw new RangeError("minFrac must be an integer from 0 to maxFrac");
      const units = scaleRound(Math.abs(n), maxFrac);
      const digits = String(units).padStart(maxFrac + 1, "0");
      const whole = digits.slice(0, digits.length - maxFrac);
      let frac = digits.slice(digits.length - maxFrac);
      while (frac.length > minFrac && frac.endsWith("0")) frac = frac.slice(0, -1);
      const body = groupDigits(whole, locale) + (frac === "" ? "" : locale.decimal + frac);
      if (units === 0) return body;
      if (n < 0) return opts.accounting ? `(${body})` : `-${body}`;
      return opts.plus ? `+${body}` : body;
    }
''')

COMPACT = dd(r'''
    import { scaleRound } from "./format";
    import { resolve } from "./locale";

    const COMPACT_UNITS: [number, string][] = [
      [1e12, "T"],
      [1e9, "B"],
      [1e6, "M"],
      [1e3, "K"],
    ];

    function oneDecimal(tenths: number, decimal: string): string {
      const whole = Math.floor(tenths / 10);
      const frac = tenths % 10;
      return frac === 0 ? String(whole) : `${whole}${decimal}${frac}`;
    }

    export function formatCompact(n: number, tag = "en"): string {
      const locale = resolve(tag);
      if (!Number.isFinite(n)) throw new RangeError("n must be finite");
      const abs = Math.abs(n);
      const sign = n < 0 && scaleRound(abs, 0) > 0 ? "-" : "";
      const small = scaleRound(abs, 0);
      if (small < 1000) return sign + String(small);
      let i = COMPACT_UNITS.findIndex(([v]) => abs >= v);
      if (i < 0) i = COMPACT_UNITS.length - 1;
      let tenths = scaleRound(abs / COMPACT_UNITS[i][0], 1);
      if (tenths >= 10000 && i > 0) {
        i -= 1;
        tenths = scaleRound(abs / COMPACT_UNITS[i][0], 1);
      }
      return sign + oneDecimal(tenths, locale.decimal) + COMPACT_UNITS[i][1];
    }

    export function formatBytes(n: number, opts: { binary?: boolean; locale?: string } = {}): string {
      if (!Number.isInteger(n) || n < 0) throw new RangeError("n must be a non-negative integer");
      const locale = resolve(opts.locale ?? "en");
      const base = opts.binary ? 1024 : 1000;
      const units = opts.binary ? ["B", "KiB", "MiB", "GiB", "TiB", "PiB"] : ["B", "kB", "MB", "GB", "TB", "PB"];
      let i = 0;
      let value = n;
      while (value >= base && i < units.length - 1) {
        value /= base;
        i++;
      }
      if (i === 0) return `${n} B`;
      let tenths = scaleRound(value, 1);
      if (tenths >= base * 10 && i < units.length - 1) {
        i++;
        tenths = scaleRound(value / base, 1);
      }
      return `${oneDecimal(tenths, locale.decimal)} ${units[i]}`;
    }
''')

VISIBLE = dd(r'''
    import { test } from "node:test";
    import assert from "node:assert/strict";
    import { resolve, groupDigits } from "../src/locale";
    import { formatNumber } from "../src/format";

    test("grouping", () => {
      assert.equal(groupDigits("1234567", resolve("en")), "1,234,567");
    });

    test("english and german", () => {
      assert.equal(formatNumber(1234.5, "en"), "1,234.5");
      assert.equal(formatNumber(1234.5, "de"), "1.234,5");
    });
''')

HIDDEN = dd(r'''
    import { test } from "node:test";
    import assert from "node:assert/strict";
    import { resolve, groupDigits } from "../src/locale";
    import { formatNumber, scaleRound } from "../src/format";
    import { formatCompact, formatBytes } from "../src/compact";

    const en = resolve("en");
    const indian = resolve("in");

    test("resolve", () => {
      assert.deepEqual(resolve("en"), { group: ",", decimal: ".", groupSizes: [3, 3] });
      assert.deepEqual(resolve("de"), { group: ".", decimal: ",", groupSizes: [3, 3] });
      assert.deepEqual(resolve("fr"), { group: " ", decimal: ",", groupSizes: [3, 3] });
      assert.deepEqual(resolve("ch"), { group: "’", decimal: ".", groupSizes: [3, 3] });
      assert.deepEqual(resolve("in"), { group: ",", decimal: ".", groupSizes: [3, 2] });
      assert.equal(resolve("EN"), resolve("en"));
      assert.equal(resolve("de-AT"), resolve("de"));
      assert.equal(resolve("fr_CA"), resolve("fr"));
      assert.equal(resolve("En-gb").decimal, ".");
    });

    test("resolve rejects unknown tags", () => {
      for (const bad of ["xx", "", "english", "-en", "constructor", "toString"]) assert.throws(() => resolve(bad), RangeError, bad);
    });

    test("groupDigits: threes", () => {
      assert.equal(groupDigits("", en), "");
      assert.equal(groupDigits("7", en), "7");
      assert.equal(groupDigits("123", en), "123");
      assert.equal(groupDigits("1234", en), "1,234");
      assert.equal(groupDigits("12345", en), "12,345");
      assert.equal(groupDigits("123456", en), "123,456");
      assert.equal(groupDigits("1234567", en), "1,234,567");
      assert.equal(groupDigits("123456789", en), "123,456,789");
      assert.equal(groupDigits("1234567890", en), "1,234,567,890");
      assert.equal(groupDigits("1234567", resolve("de")), "1.234.567");
      assert.equal(groupDigits("1234567", resolve("fr")), "1 234 567");
      assert.equal(groupDigits("1234567", resolve("ch")), "1’234’567");
    });

    test("groupDigits: the Indian pattern", () => {
      assert.equal(groupDigits("123", indian), "123");
      assert.equal(groupDigits("1234", indian), "1,234");
      assert.equal(groupDigits("12345", indian), "12,345");
      assert.equal(groupDigits("123456", indian), "1,23,456");
      assert.equal(groupDigits("1234567", indian), "12,34,567");
      assert.equal(groupDigits("12345678", indian), "1,23,45,678");
      assert.equal(groupDigits("123456789", indian), "12,34,56,789");
      assert.equal(groupDigits("1234567890", indian), "1,23,45,67,890");
    });

    test("scaleRound ties to even", () => {
      assert.equal(scaleRound(0, 2), 0);
      assert.equal(scaleRound(0.5, 0), 0);
      assert.equal(scaleRound(1.5, 0), 2);
      assert.equal(scaleRound(2.5, 0), 2);
      assert.equal(scaleRound(3.5, 0), 4);
      assert.equal(scaleRound(4.5, 0), 4);
      assert.equal(scaleRound(2.4, 0), 2);
      assert.equal(scaleRound(2.6, 0), 3);
      assert.equal(scaleRound(0.125, 2), 12);
      assert.equal(scaleRound(0.375, 2), 38);
      assert.equal(scaleRound(0.625, 2), 62);
      assert.equal(scaleRound(0.875, 2), 88);
      assert.equal(scaleRound(0.126, 2), 13);
      assert.equal(scaleRound(0.124, 2), 12);
      assert.equal(scaleRound(1234.5, 1), 12345);
      assert.equal(scaleRound(7, 3), 7000);
      assert.equal(scaleRound(0.25, 1), 2);
      assert.equal(scaleRound(0.75, 1), 8);
    });

    test("formatNumber: grouping and decimals per locale", () => {
      assert.equal(formatNumber(0), "0");
      assert.equal(formatNumber(7), "7");
      assert.equal(formatNumber(1234567.891), "1,234,567.89");
      assert.equal(formatNumber(1234567.891, "de"), "1.234.567,89");
      assert.equal(formatNumber(1234567.891, "fr"), "1 234 567,89");
      assert.equal(formatNumber(1234567.891, "ch"), "1’234’567.89");
      assert.equal(formatNumber(1234567.891, "in"), "12,34,567.89");
      assert.equal(formatNumber(999.999), "1,000");
      assert.equal(formatNumber(0.5), "0.5");
      assert.equal(formatNumber(12.3), "12.3");
      assert.equal(formatNumber(100), "100");
      assert.equal(formatNumber(1000), "1,000");
      assert.equal(formatNumber(99999.5, "in", { maxFrac: 0 }), "1,00,000");
    });

    test("formatNumber: rounding ties to even", () => {
      assert.equal(formatNumber(2.5, "en", { maxFrac: 0 }), "2");
      assert.equal(formatNumber(3.5, "en", { maxFrac: 0 }), "4");
      assert.equal(formatNumber(0.125), "0.12");
      assert.equal(formatNumber(0.375), "0.38");
      assert.equal(formatNumber(-2.5, "en", { maxFrac: 0 }), "-2");
      assert.equal(formatNumber(-3.5, "en", { maxFrac: 0 }), "-4");
      assert.equal(formatNumber(1.25, "en", { maxFrac: 1 }), "1.2");
      assert.equal(formatNumber(1.75, "en", { maxFrac: 1 }), "1.8");
      assert.equal(formatNumber(0.126), "0.13");
    });

    test("formatNumber: fraction digits", () => {
      assert.equal(formatNumber(1.5, "en", { minFrac: 2 }), "1.50");
      assert.equal(formatNumber(1, "en", { minFrac: 2 }), "1.00");
      assert.equal(formatNumber(1, "de", { minFrac: 2 }), "1,00");
      assert.equal(formatNumber(1.234, "en", { minFrac: 1, maxFrac: 3 }), "1.234");
      assert.equal(formatNumber(1.2, "en", { minFrac: 1, maxFrac: 3 }), "1.2");
      assert.equal(formatNumber(1.2, "en", { minFrac: 3, maxFrac: 3 }), "1.200");
      assert.equal(formatNumber(1.2349, "en", { maxFrac: 3 }), "1.235");
      assert.equal(formatNumber(1.5, "en", { maxFrac: 0 }), "2");
      assert.equal(formatNumber(0.00005, "en", { maxFrac: 8 }), "0.00005");
      assert.equal(formatNumber(0.00005, "en", { maxFrac: 4 }), "0");
      assert.equal(formatNumber(10, "en", { maxFrac: 0, minFrac: 0 }), "10");
      assert.equal(formatNumber(1000.5, "en", { maxFrac: 1, minFrac: 1 }), "1,000.5");
    });

    test("formatNumber: signs", () => {
      assert.equal(formatNumber(-1234.5), "-1,234.5");
      assert.equal(formatNumber(-0.001), "0");
      assert.equal(formatNumber(-0), "0");
      assert.equal(formatNumber(-0.004, "en", { minFrac: 2 }), "0.00");
      assert.equal(formatNumber(-0.005, "en", { minFrac: 2 }), "0.00");
      assert.equal(formatNumber(-0.006), "-0.01");
      assert.equal(formatNumber(-1234.5, "en", { accounting: true }), "(1,234.5)");
      assert.equal(formatNumber(1234.5, "en", { accounting: true }), "1,234.5");
      assert.equal(formatNumber(-0.001, "en", { accounting: true }), "0");
      assert.equal(formatNumber(1234.5, "en", { plus: true }), "+1,234.5");
      assert.equal(formatNumber(0, "en", { plus: true }), "0");
      assert.equal(formatNumber(0.001, "en", { plus: true }), "0");
      assert.equal(formatNumber(-5, "en", { plus: true }), "-5");
      assert.equal(formatNumber(-5, "en", { plus: true, accounting: true }), "(5)");
      assert.equal(formatNumber(-1234.5, "de"), "-1.234,5");
    });

    test("formatNumber: validation", () => {
      assert.throws(() => formatNumber(NaN), RangeError);
      assert.throws(() => formatNumber(Infinity), RangeError);
      assert.throws(() => formatNumber(1e15), RangeError);
      assert.throws(() => formatNumber(-1e15), RangeError);
      assert.doesNotThrow(() => formatNumber(999999999999999));
      assert.throws(() => formatNumber(1, "xx"), RangeError);
      assert.throws(() => formatNumber(1, "en", { maxFrac: -1 }), RangeError);
      assert.throws(() => formatNumber(1, "en", { maxFrac: 9 }), RangeError);
      assert.throws(() => formatNumber(1, "en", { maxFrac: 1.5 }), RangeError);
      assert.throws(() => formatNumber(1, "en", { minFrac: -1 }), RangeError);
      assert.throws(() => formatNumber(1, "en", { minFrac: 3, maxFrac: 2 }), RangeError);
      assert.throws(() => formatNumber(1, "en", { minFrac: 1.5 }), RangeError);
      assert.throws(() => formatNumber(1, "en", { minFrac: 3 }), RangeError);
      assert.doesNotThrow(() => formatNumber(1, "en", { minFrac: 8, maxFrac: 8 }));
      assert.doesNotThrow(() => formatNumber(1, "en", { minFrac: 0, maxFrac: 0 }));
    });

    test("formatCompact: small numbers stay whole", () => {
      assert.equal(formatCompact(0), "0");
      assert.equal(formatCompact(7), "7");
      assert.equal(formatCompact(999), "999");
      assert.equal(formatCompact(999.4), "999");
      assert.equal(formatCompact(2.5), "2");
      assert.equal(formatCompact(3.5), "4");
      assert.equal(formatCompact(-12), "-12");
      assert.equal(formatCompact(-0.2), "0");
    });

    test("formatCompact: thousands to trillions", () => {
      assert.equal(formatCompact(1000), "1K");
      assert.equal(formatCompact(1049), "1K");
      assert.equal(formatCompact(1050), "1K");
      assert.equal(formatCompact(1051), "1.1K");
      assert.equal(formatCompact(1500), "1.5K");
      assert.equal(formatCompact(12345), "12.3K");
      assert.equal(formatCompact(999499), "999.5K");
      assert.equal(formatCompact(1250000), "1.2M");
      assert.equal(formatCompact(1350000), "1.4M");
      assert.equal(formatCompact(7300000), "7.3M");
      assert.equal(formatCompact(2000000000), "2B");
      assert.equal(formatCompact(2450000000), "2.4B");
      assert.equal(formatCompact(2550000000), "2.6B");
      assert.equal(formatCompact(1e12), "1T");
      assert.equal(formatCompact(3.25e12), "3.2T");
      assert.equal(formatCompact(4.2e15), "4200T");
    });

    test("formatCompact: rounding up into the next unit", () => {
      assert.equal(formatCompact(999.5), "1K");
      assert.equal(formatCompact(999500), "999.5K");
      assert.equal(formatCompact(999950), "1M");
      assert.equal(formatCompact(999949), "999.9K");
      assert.equal(formatCompact(999950000), "1B");
      assert.equal(formatCompact(999949999), "999.9M");
      assert.equal(formatCompact(999950000000), "1T");
      assert.equal(formatCompact(999999), "1M");
    });

    test("formatCompact: signs and locales", () => {
      assert.equal(formatCompact(-1500), "-1.5K");
      assert.equal(formatCompact(-999950), "-1M");
      assert.equal(formatCompact(1500, "de"), "1,5K");
      assert.equal(formatCompact(2450000000, "fr"), "2,4B");
      assert.equal(formatCompact(1500, "in"), "1.5K");
      assert.throws(() => formatCompact(NaN), RangeError);
      assert.throws(() => formatCompact(Infinity), RangeError);
      assert.throws(() => formatCompact(1, "zz"), RangeError);
    });

    test("formatBytes: decimal units", () => {
      assert.equal(formatBytes(0), "0 B");
      assert.equal(formatBytes(1), "1 B");
      assert.equal(formatBytes(999), "999 B");
      assert.equal(formatBytes(1000), "1 kB");
      assert.equal(formatBytes(1500), "1.5 kB");
      assert.equal(formatBytes(1049), "1 kB");
      assert.equal(formatBytes(1050), "1 kB");
      assert.equal(formatBytes(1051), "1.1 kB");
      assert.equal(formatBytes(123456), "123.5 kB");
      assert.equal(formatBytes(1500000), "1.5 MB");
      assert.equal(formatBytes(2400000000), "2.4 GB");
      assert.equal(formatBytes(5e12), "5 TB");
      assert.equal(formatBytes(3.3e15), "3.3 PB");
      assert.equal(formatBytes(4.2e18), "4200 PB");
    });

    test("formatBytes: binary units", () => {
      assert.equal(formatBytes(1023, { binary: true }), "1023 B");
      assert.equal(formatBytes(1024, { binary: true }), "1 KiB");
      assert.equal(formatBytes(1536, { binary: true }), "1.5 KiB");
      assert.equal(formatBytes(1048576, { binary: true }), "1 MiB");
      assert.equal(formatBytes(5 * 1024 ** 3, { binary: true }), "5 GiB");
      assert.equal(formatBytes(1024 ** 4 * 1.5, { binary: true }), "1.5 TiB");
      assert.equal(formatBytes(1000, { binary: true }), "1000 B");
      assert.equal(formatBytes(1024 ** 5 * 2, { binary: true }), "2 PiB");
    });

    test("formatBytes: rounding into the next unit", () => {
      assert.equal(formatBytes(999949), "999.9 kB");
      assert.equal(formatBytes(999950), "1 MB");
      assert.equal(formatBytes(999999), "1 MB");
      assert.equal(formatBytes(999950000), "1 GB");
      assert.equal(formatBytes(1048575, { binary: true }), "1 MiB");
      assert.equal(formatBytes(1048524, { binary: true }), "1023.9 KiB");
      assert.equal(formatBytes(1048525, { binary: true }), "1 MiB");
    });

    test("formatBytes: locale and validation", () => {
      assert.equal(formatBytes(1500, { locale: "de" }), "1,5 kB");
      assert.equal(formatBytes(1500, { locale: "fr", binary: true }), "1,5 KiB");
      assert.throws(() => formatBytes(-1), RangeError);
      assert.throws(() => formatBytes(1.5), RangeError);
      assert.throws(() => formatBytes(NaN), RangeError);
      assert.throws(() => formatBytes(10, { locale: "xx" }), RangeError);
    });
''')

LIB = Lib(
    name="numfmt", lang="typescript", title="the numfmt formatting library",
    blurb="The analytics dashboard prints its figures with numfmt in five regional number styles, compact forms and file sizes.",
    files={"package.json": PACKAGE_JSON % "numfmt", "tsconfig.json": TSCONFIG, "types/node-shim.d.ts": TS_NODE_SHIM,
           "src/locale.ts": LOCALE, "src/format.ts": FORMAT, "src/compact.ts": COMPACT, "README.md": README, ".gitignore": "node_modules/\nbuild/\n"},
    visible_tests={"test/basic.test.ts": VISIBLE},
    hidden_tests={"test/full.test.ts": HIDDEN},
    mutate=["src/format.ts", "src/compact.ts", "src/locale.ts"], difficulty=2, tags=["formatting", "i18n", "numbers"],
    verify=TS_VERIFY,
    probe_import="const { resolve, groupDigits } = require('./build/src/locale');\nconst { formatNumber, scaleRound } = require('./build/src/format');\nconst { formatCompact, formatBytes } = require('./build/src/compact');",
    probes=[
        "groupDigits('1234567', resolve('in'))", "groupDigits('123456', resolve('in'))", "groupDigits('1234', resolve('en'))", "groupDigits('123', resolve('de'))",
        "scaleRound(2.5, 0)", "scaleRound(3.5, 0)", "scaleRound(0.125, 2)", "scaleRound(0.375, 2)",
        "formatNumber(1234567.891, 'de')", "formatNumber(1234567.891, 'in')", "formatNumber(2.5, 'en', { maxFrac: 0 })", "formatNumber(1.5, 'en', { minFrac: 2 })",
        "formatNumber(-0.001)", "formatNumber(-1234.5, 'en', { accounting: true })", "formatNumber(1234.5, 'en', { plus: true })", "formatNumber(999.999)", "formatNumber(1, 'en', { minFrac: 3 })",
        "formatCompact(999950)", "formatCompact(1051)", "formatCompact(1250000)", "formatCompact(-1500)", "formatCompact(1500, 'de')", "formatCompact(999.5)", "formatCompact(4.2e15)",
        "formatBytes(999950)", "formatBytes(1500)", "formatBytes(1536, { binary: true })", "formatBytes(1048575, { binary: true })", "formatBytes(1000, { binary: true })", "formatBytes(-1)",
    ],
)

register_libs([LIB], n=8)
