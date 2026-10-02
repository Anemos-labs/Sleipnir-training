"""formgate (javascript): a form validation library extended with length, range, choices, patterns, custom checks, messages, coercion, cross-field and nested rules."""
import random

from fx import dd
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # formgate

    Validation for the sign-up and checkout forms of a web shop (Node.js, CommonJS, no dependencies). Run the tests with
    `npm test` (`node --test test/*.test.js`).

    ## Layout

    * `index.js`: exports `Schema`.
    * `src/schema.js`: the validator.

    ## Basics

    * `new Schema(spec)`: `spec` is an object that maps field names to field definitions `{ type, required }` (anything else
      is a `TypeError`, as are definitions that are not objects). `type` is `'string'` (the default), `'number'` or
      `'boolean'` (`RangeError` for another type); `required` is a boolean (`TypeError` otherwise) and defaults to `false`.
      Field names must not be empty (`RangeError`). Keys that a definition does not know are a `TypeError`.
    * `schema.validate(data)` checks a plain object (`TypeError` for anything else) and returns `{ ok, errors, value }`.
      A field is *missing* when it is `undefined`, `null` or an empty string. A missing required field has the error
      `is required`; a missing optional field is skipped. Otherwise the value must have the declared type, else the error is
      `must be a string` / `must be a number` / `must be a boolean` (a number must be finite, so `NaN` and `Infinity` are not
      numbers). Fields that are not declared are ignored.
    * `errors` maps field names to arrays of messages (only fields with problems appear); `ok` is true when `errors` is empty;
      `value` holds the declared fields that were present and valid, under the same names. `validate` never modifies `data`.
''')

SCHEMA = '''\
'use strict';
@@uniq requires

const TYPES = ['string', 'number', 'boolean'];
const RULE_IDS = ['required', 'type'];
@@slot rule_ids

@@blocks helpers

class Schema {
  constructor(spec) {
    if (typeof spec !== 'object' || spec === null || Array.isArray(spec)) throw new TypeError('spec must be an object');
    this.fields = new Map();
    @@slot init
    for (const [name, raw] of Object.entries(spec)) this._addField(name, raw);
  }

  _addField(name, raw) {
    if (name === '') throw new RangeError('field names must not be empty');
    if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) throw new TypeError(`definition of ${name} must be an object`);
    const rule = { ...raw };
    const type = rule.type === undefined ? 'string' : rule.type;
    if (!TYPES.includes(type)) throw new RangeError(`unknown type for ${name}: $<type>`);
    delete rule.type;
    if (rule.required !== undefined && typeof rule.required !== 'boolean') throw new TypeError(`required of ${name} must be a boolean`);
    const def = { name, type, required: rule.required === true };
    delete rule.required;
    @@slot field_options
    const unknown = Object.keys(rule);
    if (unknown.length) throw new TypeError(`unknown key(s) in ${name}: ${unknown.sort().join(', ')}`);
    this.fields.set(name, def);
  }

  @@default message_text
  _text(def, rule, text, params) {
    return text;
  }
  @@end

  @@default peek
  _peek(obj, name) {
    return obj[name];
  }
  @@end

  validate(data) {
    if (typeof data !== 'object' || data === null || Array.isArray(data)) throw new TypeError('data must be an object');
    const errors = {};
    const value = {};
    const fail = (def, rule, text, params = {}) => {
      (errors[def.name] = errors[def.name] || []).push(this._text(def, rule, text, params));
    };
    for (const def of this.fields.values()) {
      const name = def.name;
      @@default read_value
      let v = data[name];
      @@end
      @@slot normalize
      if (v === undefined || v === null || v === '') {
        if (def.required) fail(def, 'required', 'is required');
        continue;
      }
      @@slot coerce
      const okType = def.type === 'number' ? typeof v === 'number' && Number.isFinite(v) : typeof v === def.type;
      if (!okType) {
        fail(def, 'type', `must be a ${def.type}`, { type: def.type });
        continue;
      }
      @@slot checks
      if (!errors[name]) {
        @@default store_value
        value[name] = v;
        @@end
      }
    }
    @@slot form_checks
    return { ok: Object.keys(errors).length === 0, errors, value };
  }

  @@blocks methods
}

module.exports = { Schema };
'''

HEAD = '''\
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
@@uniq requires
const { Schema } = require('../index.js');

const signup = () => new Schema({
  name: { type: 'string', required: true },
  age: { type: 'number' },
  newsletter: { type: 'boolean' },
});
'''

VISIBLE = HEAD + '''
test('valid data', () => {
  const r = signup().validate({ name: 'Ana', age: 31, newsletter: false, extra: 'ignored' });
  assert.deepEqual(r, { ok: true, errors: {}, value: { name: 'Ana', age: 31, newsletter: false } });
});

test('errors', () => {
  const r = signup().validate({ name: '', age: '31', newsletter: 'yes' });
  assert.equal(r.ok, false);
  assert.deepEqual(r.errors, { name: ['is required'], age: ['must be a number'], newsletter: ['must be a boolean'] });
  assert.deepEqual(r.value, {});
  assert.throws(() => new Schema({ a: { type: 'date' } }), RangeError);
});
@@blocks tests
'''

HIDDEN = HEAD + '''
test('base: schema validation', () => {
  for (const bad of [null, undefined, 5, 'x', []]) assert.throws(() => new Schema(bad), TypeError, String(bad));
  assert.throws(() => new Schema({ '': {} }), RangeError);
  for (const bad of [null, 5, 'string', ['x']]) assert.throws(() => new Schema({ a: bad }), TypeError, String(bad));
  for (const bad of ['date', 'array', 'String', null, 5]) assert.throws(() => new Schema({ a: { type: bad } }), RangeError, String(bad));
  for (const bad of ['yes', 1, null, 0]) assert.throws(() => new Schema({ a: { required: bad } }), TypeError, String(bad));
  assert.throws(() => new Schema({ a: { colour: 'red' } }), TypeError);
  assert.throws(() => new Schema({ a: { type: 'string', unknownThing: 1 } }), /unknownThing/);
  assert.ok(new Schema({}));
  assert.ok(new Schema({ a: {}, b: { type: 'number', required: false } }));
});

test('base: validate input', () => {
  const s = signup();
  for (const bad of [null, undefined, 5, 'x', [], () => 1]) assert.throws(() => s.validate(bad), TypeError, String(bad));
  assert.deepEqual(s.validate({}), { ok: false, errors: { name: ['is required'] }, value: {} });
  const data = { name: 'Ana', extra: 1 };
  const copy = JSON.stringify(data);
  s.validate(data);
  assert.equal(JSON.stringify(data), copy);
});

test('base: required and missing', () => {
  const s = signup();
  for (const missing of [undefined, null, '']) {
    assert.deepEqual(s.validate({ name: missing }).errors, { name: ['is required'] }, String(missing));
  }
  assert.equal(s.validate({ name: ' ' }).ok, true);
  assert.deepEqual(s.validate({ name: 'Ana', age: null, newsletter: '' }).value, { name: 'Ana' });
  assert.deepEqual(s.validate({ name: 'Ana', age: undefined }).value, { name: 'Ana' });
  assert.deepEqual(s.validate({ name: 'Ana', age: 0, newsletter: false }).value, { name: 'Ana', age: 0, newsletter: false });
  const t = new Schema({ flag: { type: 'boolean', required: true }, n: { type: 'number', required: true } });
  assert.deepEqual(t.validate({ flag: false, n: 0 }), { ok: true, errors: {}, value: { flag: false, n: 0 } });
  assert.deepEqual(t.validate({ flag: null, n: undefined }).errors, { flag: ['is required'], n: ['is required'] });
});

test('base: types', () => {
  const s = new Schema({ s: {}, n: { type: 'number' }, b: { type: 'boolean' } });
  const r = s.validate({ s: 5, n: '5', b: 'true' });
  assert.deepEqual(r.errors, { s: ['must be a string'], n: ['must be a number'], b: ['must be a boolean'] });
  for (const bad of [NaN, Infinity, -Infinity, '1', true, {}, []]) {
    assert.deepEqual(s.validate({ n: bad }).errors, { n: ['must be a number'] }, String(bad));
  }
  for (const bad of [0, 1, 'false', {}, []]) assert.deepEqual(s.validate({ b: bad }).errors, { b: ['must be a boolean'] }, String(bad));
  for (const bad of [true, 5, {}, ['a']]) assert.deepEqual(s.validate({ s: bad }).errors, { s: ['must be a string'] }, String(bad));
  assert.deepEqual(s.validate({ s: 'x', n: -1.5, b: true }).value, { s: 'x', n: -1.5, b: true });
  assert.deepEqual(s.validate({ s: 'x', n: 5, b: 'nope' }).value, { s: 'x', n: 5 });
  assert.equal(s.validate({ s: 'ok' }).errors.s, undefined);
});
@@blocks tests
'''


def make_slices(rng: random.Random):
    kw = rng.choice([("oneOf", "must be one of"), ("oneOf", "must be one of")])
    max_len_cap = rng.choice([50, 100])
    S = []

    S.append(Slice(
        id="length", title="String length", d=1,
        pitch=("Usernames of one letter and notes of ten thousand characters made it through the sign-up form.",
               "String fields need minimum and maximum lengths."),
        reqs=("String fields accept `minLength` and `maxLength` (integers of at least 0; `TypeError` otherwise, and also for a field that is not a `'string'`; `minLength` above `maxLength` is a `RangeError`). A string shorter than `minLength` has the error `must be at least N characters`, a longer one `must be at most N characters` (`character` when N is 1). Length counts UTF-16 code units (`string.length`). The checks only run for values of the right type, and all failed rules of a field are reported, `minLength` before `maxLength`.",),
        code={
            "src/schema.js::rule_ids": "RULE_IDS.push('minLength', 'maxLength');",
            "src/schema.js::field_options": '''
                for (const key of ['minLength', 'maxLength']) {
                  if (rule[key] === undefined) continue;
                  if (type !== 'string') throw new TypeError(`${key} only applies to strings (${name})`);
                  if (!Number.isInteger(rule[key]) || rule[key] < 0) throw new TypeError(`${key} of ${name} must be an integer of at least 0`);
                  def[key] = rule[key];
                  delete rule[key];
                }
                if (def.minLength !== undefined && def.maxLength !== undefined && def.minLength > def.maxLength) {
                  throw new RangeError(`minLength of ${name} is above maxLength`);
                }
            ''',
            "src/schema.js::checks": '''
                if (def.minLength !== undefined && v.length < def.minLength) {
                  fail(def, 'minLength', `must be at least ${def.minLength} character${def.minLength === 1 ? '' : 's'}`, { min: def.minLength });
                }
                if (def.maxLength !== undefined && v.length > def.maxLength) {
                  fail(def, 'maxLength', `must be at most ${def.maxLength} character${def.maxLength === 1 ? '' : 's'}`, { max: def.maxLength });
                }
            ''',
        },
        readme="## String length\n\n`minLength` / `maxLength` on string fields: `must be at least N characters` / `must be at most N characters` (`character` for 1). A reversed pair is a `RangeError`.\n",
        vtests='''
          test('length basic', () => {
            const s = new Schema({ name: { minLength: 2 } });
            assert.deepEqual(s.validate({ name: 'A' }).errors, { name: ['must be at least 2 characters'] });
          });
        ''',
        tests='''
          test('length rules', () => {
            const s = new Schema({ name: { required: true, minLength: 3, maxLength: 5 }, one: { minLength: 1, maxLength: 1 } });
            assert.deepEqual(s.validate({ name: 'ab', one: 'xy' }).errors, { name: ['must be at least 3 characters'], one: ['must be at most 1 character'] });
            assert.deepEqual(s.validate({ name: 'abcdef' }).errors, { name: ['must be at most 5 characters'] });
            assert.equal(s.validate({ name: 'abc', one: 'x' }).ok, true);
            assert.equal(s.validate({ name: 'abcde' }).ok, true);
            assert.deepEqual(s.validate({ name: '' }).errors, { name: ['is required'] });
            assert.deepEqual(s.validate({ name: 'abc', one: 7 }).errors, { one: ['must be a string'] });
            const opt = new Schema({ nick: { minLength: 3 } });
            assert.deepEqual(opt.validate({}), { ok: true, errors: {}, value: {} });
            assert.deepEqual(opt.validate({ nick: '' }).value, {});
            const zero = new Schema({ s: { minLength: 0, maxLength: 0 } });
            assert.equal(zero.validate({ s: 'a' }).errors.s[0], 'must be at most 0 characters');
          });

          test('length options are validated', () => {
            for (const bad of [-1, 1.5, '3', null, NaN]) assert.throws(() => new Schema({ a: { minLength: bad } }), TypeError, String(bad));
            for (const bad of [-1, 1.5, '3', null]) assert.throws(() => new Schema({ a: { maxLength: bad } }), TypeError, String(bad));
            assert.throws(() => new Schema({ a: { type: 'number', minLength: 1 } }), TypeError);
            assert.throws(() => new Schema({ a: { type: 'boolean', maxLength: 1 } }), TypeError);
            assert.throws(() => new Schema({ a: { minLength: 5, maxLength: 4 } }), RangeError);
            assert.ok(new Schema({ a: { minLength: 4, maxLength: 4 } }));
          });
        ''',
    ))

    S.append(Slice(
        id="range", title="Number ranges", d=1,
        pitch=("Somebody ordered minus three tickets and a quantity of 2.5 pizzas.",
               "Number fields need bounds and a whole-number check."),
        reqs=("Number fields accept `min`, `max` (finite numbers) and `integer` (a boolean); they are a `TypeError` for other values and for fields that are not of type `'number'`; `min` above `max` is a `RangeError`. With `integer: true` a number with a fraction has the error `must be a whole number`; a number below `min` has `must be at least N`, one above `max` `must be at most N`. The checks only run for finite numbers and all failed rules are reported, in the order whole number, minimum, maximum.",),
        code={
            "src/schema.js::rule_ids": "RULE_IDS.push('integer', 'min', 'max');",
            "src/schema.js::field_options": '''
                for (const key of ['min', 'max']) {
                  if (rule[key] === undefined) continue;
                  if (type !== 'number') throw new TypeError(`${key} only applies to numbers (${name})`);
                  if (typeof rule[key] !== 'number' || !Number.isFinite(rule[key])) throw new TypeError(`${key} of ${name} must be a finite number`);
                  def[key] = rule[key];
                  delete rule[key];
                }
                if (rule.integer !== undefined) {
                  if (type !== 'number') throw new TypeError(`integer only applies to numbers (${name})`);
                  if (typeof rule.integer !== 'boolean') throw new TypeError(`integer of ${name} must be a boolean`);
                  def.integer = rule.integer;
                  delete rule.integer;
                }
                if (def.min !== undefined && def.max !== undefined && def.min > def.max) throw new RangeError(`min of ${name} is above max`);
            ''',
            "src/schema.js::checks": '''
                if (def.integer && !Number.isInteger(v)) fail(def, 'integer', 'must be a whole number');
                if (def.min !== undefined && v < def.min) fail(def, 'min', `must be at least ${def.min}`, { min: def.min });
                if (def.max !== undefined && v > def.max) fail(def, 'max', `must be at most ${def.max}`, { max: def.max });
            ''',
        },
        readme="## Number ranges\n\n`min`, `max` and `integer` on number fields: `must be at least N`, `must be at most N`, `must be a whole number` (in that order: whole number, minimum, maximum).\n",
        vtests='''
          test('range basic', () => {
            const s = new Schema({ qty: { type: 'number', min: 1 } });
            assert.deepEqual(s.validate({ qty: 0 }).errors, { qty: ['must be at least 1'] });
          });
        ''',
        tests='''
          test('range rules', () => {
            const s = new Schema({ qty: { type: 'number', required: true, integer: true, min: 1, max: 10 } });
            assert.deepEqual(s.validate({ qty: 0 }).errors, { qty: ['must be at least 1'] });
            assert.deepEqual(s.validate({ qty: 11 }).errors, { qty: ['must be at most 10'] });
            assert.deepEqual(s.validate({ qty: 2.5 }).errors, { qty: ['must be a whole number'] });
            assert.deepEqual(s.validate({ qty: -0.5 }).errors, { qty: ['must be a whole number', 'must be at least 1'] });
            assert.equal(s.validate({ qty: 1 }).ok, true);
            assert.equal(s.validate({ qty: 10 }).ok, true);
            assert.deepEqual(s.validate({ qty: '5' }).errors, { qty: ['must be a number'] });
            assert.deepEqual(s.validate({ qty: NaN }).errors, { qty: ['must be a number'] });
            const f = new Schema({ price: { type: 'number', min: 0.5, max: 99.99 }, t: { type: 'number', integer: false } });
            assert.deepEqual(f.validate({ price: 0.49, t: 1.5 }).errors, { price: ['must be at least 0.5'] });
            assert.deepEqual(f.validate({ price: 100 }).errors, { price: ['must be at most 99.99'] });
            assert.equal(f.validate({ price: 0.5, t: 2 }).ok, true);
            const neg = new Schema({ temp: { type: 'number', min: -10, max: -1 } });
            assert.deepEqual(neg.validate({ temp: 0 }).errors, { temp: ['must be at most -1'] });
            assert.equal(neg.validate({}).ok, true);
          });

          test('range options are validated', () => {
            for (const bad of ['1', null, NaN, Infinity, true]) assert.throws(() => new Schema({ a: { type: 'number', min: bad } }), TypeError, String(bad));
            for (const bad of ['1', null, -Infinity]) assert.throws(() => new Schema({ a: { type: 'number', max: bad } }), TypeError, String(bad));
            for (const bad of ['yes', 1, null]) assert.throws(() => new Schema({ a: { type: 'number', integer: bad } }), TypeError, String(bad));
            assert.throws(() => new Schema({ a: { min: 1 } }), TypeError);
            assert.throws(() => new Schema({ a: { type: 'boolean', max: 1 } }), TypeError);
            assert.throws(() => new Schema({ a: { type: 'string', integer: true } }), TypeError);
            assert.throws(() => new Schema({ a: { type: 'number', min: 5, max: 4 } }), RangeError);
            assert.ok(new Schema({ a: { type: 'number', min: 4, max: 4 } }));
          });
        ''',
        cross={
            "length": {"tests": '''
              test('length and range side by side', () => {
                const s = new Schema({ code: { minLength: 2 }, qty: { type: 'number', min: 2 } });
                assert.deepEqual(s.validate({ code: 'a', qty: 1 }).errors, { code: ['must be at least 2 characters'], qty: ['must be at least 2'] });
              });
            '''},
        },
    ))

    S.append(Slice(
        id="oneof", title="Allowed values", d=1,
        pitch=("The country field accepted 'Narnia' because it is just a text box.",
               "Fields need a list of allowed values."),
        reqs=("Fields accept `oneOf`, a non-empty array of values of the field's type (`TypeError` for anything else, also for values of the wrong type). A value that is not in the list has the error `must be one of: a, b, c` (the allowed values written with `String()` and joined with `, `, in the order given). Comparison is strict. The check only runs for values of the right type.",),
        code={
            "src/schema.js::rule_ids": "RULE_IDS.push('oneOf');",
            "src/schema.js::field_options": '''
                if (rule.oneOf !== undefined) {
                  if (!Array.isArray(rule.oneOf) || rule.oneOf.length === 0) throw new TypeError(`oneOf of ${name} must be a non-empty array`);
                  const same = (x) => (type === 'number' ? typeof x === 'number' && Number.isFinite(x) : typeof x === type);
                  if (!rule.oneOf.every(same)) throw new TypeError(`oneOf of ${name} must only hold $<type> values`);
                  def.oneOf = [...rule.oneOf];
                  delete rule.oneOf;
                }
            ''',
            "src/schema.js::checks": '''
                if (def.oneOf && !def.oneOf.includes(v)) {
                  fail(def, 'oneOf', `must be one of: ${def.oneOf.map(String).join(', ')}`, { values: def.oneOf.map(String).join(', ') });
                }
            ''',
        },
        readme="## Allowed values\n\n`oneOf: [...]` lists the allowed values; other values get `must be one of: a, b, c`.\n",
        vtests='''
          test('oneOf basic', () => {
            const s = new Schema({ size: { oneOf: ['S', 'M', 'L'] } });
            assert.deepEqual(s.validate({ size: 'XL' }).errors, { size: ['must be one of: S, M, L'] });
          });
        ''',
        tests='''
          test('oneOf rules', () => {
            const s = new Schema({
              size: { required: true, oneOf: ['S', 'M', 'L'] },
              level: { type: 'number', oneOf: [1, 2.5, 3] },
              mode: { type: 'boolean', oneOf: [true] },
            });
            assert.deepEqual(s.validate({ size: 'XL' }).errors, { size: ['must be one of: S, M, L'] });
            assert.deepEqual(s.validate({ size: 'm' }).errors, { size: ['must be one of: S, M, L'] });
            assert.deepEqual(s.validate({ size: 'S', level: 2 }).errors, { level: ['must be one of: 1, 2.5, 3'] });
            assert.deepEqual(s.validate({ size: 'S', mode: false }).errors, { mode: ['must be one of: true'] });
            assert.deepEqual(s.validate({ size: 'S', level: 2.5, mode: true }), { ok: true, errors: {}, value: { size: 'S', level: 2.5, mode: true } });
            assert.deepEqual(s.validate({ size: 5 }).errors, { size: ['must be a string'] });
            assert.deepEqual(s.validate({}).errors, { size: ['is required'] });
          });

          test('oneOf options are validated', () => {
            for (const bad of [[], 'abc', null, 5, {}]) assert.throws(() => new Schema({ a: { oneOf: bad } }), TypeError, String(bad));
            assert.throws(() => new Schema({ a: { oneOf: ['a', 1] } }), TypeError);
            assert.throws(() => new Schema({ a: { type: 'number', oneOf: ['1'] } }), TypeError);
            assert.throws(() => new Schema({ a: { type: 'number', oneOf: [NaN] } }), TypeError);
            assert.throws(() => new Schema({ a: { type: 'boolean', oneOf: [1] } }), TypeError);
            const list = ['x', 'y'];
            const s = new Schema({ a: { oneOf: list } });
            list.push('z');
            assert.equal(s.validate({ a: 'z' }).ok, false);
          });
        ''',
        cross={
            "length": {
                "reqs": ("`oneOf` and the length rules are independent: all failed rules are reported, `minLength`, `maxLength`, then `oneOf`.",),
                "tests": '''
                  test('oneOf comes after the length rules', () => {
                    const s = new Schema({ code: { minLength: 3, oneOf: ['abc', 'abcd'] } });
                    assert.deepEqual(s.validate({ code: 'ab' }).errors, { code: ['must be at least 3 characters', 'must be one of: abc, abcd'] });
                  });
                '''},
            "range": {
                "reqs": ("`oneOf` is checked after the range rules.",),
                "tests": '''
                  test('oneOf comes after the range rules', () => {
                    const s = new Schema({ n: { type: 'number', min: 5, oneOf: [10, 20] } });
                    assert.deepEqual(s.validate({ n: 3 }).errors, { n: ['must be at least 5', 'must be one of: 10, 20'] });
                  });
                '''},
        },
    ))

    S.append(Slice(
        id="pattern", title="Patterns", d=2,
        pitch=("Postcodes like 'hello' and phone numbers with letters keep arriving.",
               "String fields need a format check."),
        reqs=("String fields accept `pattern`, a `RegExp` (`TypeError` for anything else, and for fields that are not strings). A string that the expression does not match anywhere has the error `has the wrong format`. The check must give the same answer every time: a global or sticky expression must not remember where the previous test stopped. The check only runs for strings, after the other rules of the field (so it is the last message).",),
        code={
            "src/schema.js::rule_ids": "RULE_IDS.push('pattern');",
            "src/schema.js::field_options": '''
                if (rule.pattern !== undefined) {
                  if (type !== 'string') throw new TypeError(`pattern only applies to strings (${name})`);
                  if (!(rule.pattern instanceof RegExp)) throw new TypeError(`pattern of ${name} must be a RegExp`);
                  def.pattern = rule.pattern;
                  delete rule.pattern;
                }
            ''',
            "src/schema.js::checks": '''
                if (def.pattern) {
                  def.pattern.lastIndex = 0;
                  if (!def.pattern.test(v)) fail(def, 'pattern', 'has the wrong format');
                }
            ''',
        },
        readme="## Patterns\n\n`pattern: /^\\d{5}$/` on string fields: a string without a match has the error `has the wrong format`.\n",
        vtests='''
          test('pattern basic', () => {
            const s = new Schema({ zip: { pattern: /^\\d{5}$/ } });
            assert.deepEqual(s.validate({ zip: 'abc' }).errors, { zip: ['has the wrong format'] });
          });
        ''',
        tests='''
          test('pattern rules', () => {
            const s = new Schema({ zip: { required: true, pattern: /^\\d{5}$/ }, tag: { pattern: /#\\w+/g } });
            assert.deepEqual(s.validate({ zip: '1234' }).errors, { zip: ['has the wrong format'] });
            assert.deepEqual(s.validate({ zip: '12345x' }).errors, { zip: ['has the wrong format'] });
            assert.equal(s.validate({ zip: '12345' }).ok, true);
            assert.equal(s.validate({ zip: '12345', tag: 'so #cool' }).ok, true);
            assert.equal(s.validate({ zip: '12345', tag: 'so #cool' }).ok, true);
            assert.equal(s.validate({ zip: '12345', tag: 'so #cool' }).ok, true);
            assert.deepEqual(s.validate({ zip: '12345', tag: 'plain' }).errors, { tag: ['has the wrong format'] });
            assert.deepEqual(s.validate({ zip: 5 }).errors, { zip: ['must be a string'] });
            assert.deepEqual(s.validate({ zip: '' }).errors, { zip: ['is required'] });
            const sticky = new Schema({ w: { pattern: /ab/y } });
            assert.equal(sticky.validate({ w: 'abab' }).ok, true);
            assert.equal(sticky.validate({ w: 'abab' }).ok, true);
          });

          test('pattern options are validated', () => {
            for (const bad of ['^a$', null, 5, {}, ['a']]) assert.throws(() => new Schema({ a: { pattern: bad } }), TypeError, String(bad));
            assert.throws(() => new Schema({ a: { type: 'number', pattern: /a/ } }), TypeError);
            assert.throws(() => new Schema({ a: { type: 'boolean', pattern: /a/ } }), TypeError);
          });
        ''',
        cross={
            "length": {"tests": '''
              test('pattern is the last message', () => {
                const s = new Schema({ code: { minLength: 4, maxLength: 5, pattern: /^[a-z]+$/ } });
                assert.deepEqual(s.validate({ code: 'A1' }).errors, { code: ['must be at least 4 characters', 'has the wrong format'] });
                assert.deepEqual(s.validate({ code: 'ABCDEFG' }).errors, { code: ['must be at most 5 characters', 'has the wrong format'] });
              });
            '''},
            "oneof": {"tests": '''
              test('pattern comes after oneOf', () => {
                const s = new Schema({ code: { oneOf: ['a1', 'b2'], pattern: /^[a-z]$/ } });
                assert.deepEqual(s.validate({ code: 'zz' }).errors, { code: ['must be one of: a1, b2', 'has the wrong format'] });
              });
            '''},
        },
    ))

    S.append(Slice(
        id="custom", title="Custom checks", d=2,
        pitch=("The shop needs rules that no schema keyword can express, such as 'the voucher code must exist'.",
               "Fields need a hook for checks written in code."),
        reqs=("A field definition accepts `check`, a function (`TypeError` otherwise). It is called as `check(value, data)` with the value that passed the type check and the whole input object, after all the other rules of the field, and returns `undefined` or `true` when the value is fine, a string for one error message, or an array of strings for several; anything else is treated as fine. The messages are added to the field's errors as they are. Exceptions thrown by the function are not caught.",),
        code={
            "src/schema.js::field_options": '''
                if (rule.check !== undefined) {
                  if (typeof rule.check !== 'function') throw new TypeError(`check of ${name} must be a function`);
                  def.check = rule.check;
                  delete rule.check;
                }
            ''',
            "src/schema.js::checks": '''
                if (def.check) {
                  const res = def.check(v, data);
                  const list = typeof res === 'string' ? [res] : Array.isArray(res) ? res.filter((m) => typeof m === 'string') : [];
                  for (const m of list) (errors[name] = errors[name] || []).push(m);
                }
            ''',
        },
        readme="## Custom checks\n\n`check(value, data)` returns `undefined`/`true` (fine), a message string or an array of strings; it runs last and only for values of the right type.\n",
        vtests='''
          test('check basic', () => {
            const s = new Schema({ code: { check: (v) => (v.startsWith('X') ? undefined : 'must start with X') } });
            assert.deepEqual(s.validate({ code: 'Y1' }).errors, { code: ['must start with X'] });
          });
        ''',
        tests='''
          test('custom checks', () => {
            const seen = [];
            const s = new Schema({
              code: { required: true, check: (v, data) => { seen.push([v, data.other]); return v === 'ok' ? true : `${v} is not valid`; } },
              multi: { check: (v) => (v.length < 3 ? ['too short', 'really too short'] : undefined) },
              odd: { type: 'number', check: (v) => (v % 2 === 1 ? undefined : false) },
              weird: { check: () => 42 },
            });
            assert.deepEqual(s.validate({ code: 'ok', other: 1 }).ok, true);
            assert.deepEqual(s.validate({ code: 'bad', other: 2 }).errors, { code: ['bad is not valid'] });
            assert.deepEqual(seen, [['ok', 1], ['bad', 2]]);
            assert.deepEqual(s.validate({ code: 'ok', multi: 'ab' }).errors, { multi: ['too short', 'really too short'] });
            assert.equal(s.validate({ code: 'ok', multi: 'abc' }).ok, true);
            assert.equal(s.validate({ code: 'ok', odd: 4 }).ok, true);
            assert.equal(s.validate({ code: 'ok', weird: 'x' }).ok, true);
            seen.length = 0;
            s.validate({});
            s.validate({ code: 5 });
            s.validate({ code: '' });
            assert.deepEqual(seen, []);
          });

          test('custom check options are validated', () => {
            for (const bad of ['yes', null, 5, {}, /a/]) assert.throws(() => new Schema({ a: { check: bad } }), TypeError, String(bad));
          });
        ''',
        cross={
            "length": {"tests": '''
              test('check comes after the length rules', () => {
                const s = new Schema({ code: { minLength: 3, check: () => 'custom' } });
                assert.deepEqual(s.validate({ code: 'a' }).errors, { code: ['must be at least 3 characters', 'custom'] });
                assert.deepEqual(s.validate({ code: 'abc' }).errors, { code: ['custom'] });
              });
            '''},
            "pattern": {"tests": '''
              test('check comes after the pattern', () => {
                const s = new Schema({ code: { pattern: /^\\d+$/, check: () => 'custom' } });
                assert.deepEqual(s.validate({ code: 'a' }).errors, { code: ['has the wrong format', 'custom'] });
              });
            '''},
        },
    ))

    S.append(Slice(
        id="messages", title="Custom messages", d=3,
        pitch=("The shop is localised and the English error messages show up on the German pages.",
               "Every field needs its own wording for the error messages."),
        reqs=("A field definition accepts `messages`, an object that replaces the built-in message of a rule: the keys are the rule ids that exist (`required` and `type`, plus `minLength`, `maxLength`, `integer`, `min`, `max`, `oneOf` and `pattern` for the rules the schema has), the values are non-empty strings (`TypeError` for other values, for a `messages` that is not an object and for an unknown key). The text may contain placeholders in angle brackets: `<label>` is the field name and, where the rule has them, `<min>`, `<max>`, `<type>` and `<values>` (the allowed values joined with `, `); unknown placeholders are left as they are. Rules without a custom text keep the built-in one; messages returned by custom `check` functions are not touched.",),
        code={
            "src/schema.js::field_options": '''
                if (rule.messages !== undefined) {
                  if (typeof rule.messages !== 'object' || rule.messages === null || Array.isArray(rule.messages)) {
                    throw new TypeError(`messages of ${name} must be an object`);
                  }
                  for (const [k, text] of Object.entries(rule.messages)) {
                    if (!RULE_IDS.includes(k)) throw new TypeError(`unknown message key in ${name}: ${k}`);
                    if (typeof text !== 'string' || text === '') throw new TypeError(`message ${k} of ${name} must be a non-empty string`);
                  }
                  def.messages = { ...rule.messages };
                  delete rule.messages;
                }
            ''',
            "src/schema.js::message_text": '''
                _text(def, rule, text, params) {
                  const custom = def.messages && def.messages[rule];
                  if (custom === undefined) return text;
                  const all = { label: def.name, ...params };
                  return custom.replace(/<(\\w+)>/g, (m, k) => (k in all ? String(all[k]) : m));
                }
            ''',
        },
        readme="## Custom messages\n\n`messages: { required: '<label> fehlt', minLength: 'zu kurz (mindestens <min>)' }` replaces the built-in texts of a field; placeholders `<label>`, `<min>`, `<max>`, `<type>`, `<values>`.\n",
        vtests='''
          test('messages basic', () => {
            const s = new Schema({ name: { required: true, messages: { required: '<label> fehlt' } } });
            assert.deepEqual(s.validate({}).errors, { name: ['name fehlt'] });
          });
        ''',
        tests='''
          test('custom messages', () => {
            const s = new Schema({
              name: { required: true, messages: { required: 'please give a <label>', type: '<label> must be <type>-like' } },
              age: { type: 'number', messages: { type: 'age <oops> <label>' } },
              plain: { required: true },
            });
            assert.deepEqual(s.validate({ name: '' , plain: 1 }).errors, { name: ['please give a name'], plain: ['must be a string'] });
            assert.deepEqual(s.validate({ name: 5, plain: 'x' }).errors, { name: ['name must be string-like'] });
            assert.deepEqual(s.validate({ name: 'a', age: 'x', plain: 'x' }).errors, { age: ['age <oops> age'] });
            assert.deepEqual(s.validate({ name: 'a' }).errors, { plain: ['is required'] });
            assert.deepEqual(s.validate({ name: 'a', plain: 'b' }), { ok: true, errors: {}, value: { name: 'a', plain: 'b' } });
          });

          test('messages are validated', () => {
            for (const bad of ['x', null, 5, ['required']]) assert.throws(() => new Schema({ a: { messages: bad } }), TypeError, String(bad));
            for (const bad of ['', 5, null, {}]) assert.throws(() => new Schema({ a: { messages: { required: bad } } }), TypeError, String(bad));
            assert.throws(() => new Schema({ a: { messages: { nonsense: 'x' } } }), TypeError);
            assert.throws(() => new Schema({ a: { messages: { required: 'ok', other: 'x' } } }), /other/);
            assert.ok(new Schema({ a: { messages: {} } }));
          });
        ''',
        cross={
            "length": {"tests": '''
              test('length messages', () => {
                const s = new Schema({ code: { minLength: 3, maxLength: 5, messages: { minLength: '<label>: at least <min>!', maxLength: '<label>: at most <max>!' } } });
                assert.deepEqual(s.validate({ code: 'a' }).errors, { code: ['code: at least 3!'] });
                assert.deepEqual(s.validate({ code: 'abcdef' }).errors, { code: ['code: at most 5!'] });
              });
            '''},
            "range": {"tests": '''
              test('range messages', () => {
                const s = new Schema({ n: { type: 'number', integer: true, min: 1, max: 3, messages: { integer: 'whole <label>', min: '>= <min>', max: '<= <max>' } } });
                assert.deepEqual(s.validate({ n: 0.5 }).errors, { n: ['whole n', '>= 1'] });
                assert.deepEqual(s.validate({ n: 7 }).errors, { n: ['<= 3'] });
              });
            '''},
            "oneof": {"tests": '''
              test('oneOf messages', () => {
                const s = new Schema({ size: { oneOf: ['S', 'M'], messages: { oneOf: '<label> is not in [<values>]' } } });
                assert.deepEqual(s.validate({ size: 'XL' }).errors, { size: ['size is not in [S, M]'] });
              });
            '''},
            "pattern": {"tests": '''
              test('pattern messages', () => {
                const s = new Schema({ zip: { pattern: /^\\d+$/, messages: { pattern: 'bad <label>' } } });
                assert.deepEqual(s.validate({ zip: 'x' }).errors, { zip: ['bad zip'] });
              });
            '''},
            "custom": {"tests": '''
              test('custom check messages are not touched', () => {
                const s = new Schema({ a: { required: true, check: () => 'custom <label>', messages: { required: 'req' } } });
                assert.deepEqual(s.validate({ a: 'x' }).errors, { a: ['custom <label>'] });
                assert.deepEqual(s.validate({}).errors, { a: ['req'] });
              });
            '''},
        },
    ))

    S.append(Slice(
        id="coerce", title="Coercion and trimming", d=3,
        pitch=("Form posts arrive as strings: the age is '42' and the checkbox is 'true', and every field has stray blanks.",
               "Fields should be able to convert what a browser sends into real types."),
        reqs=("A field definition accepts `trim` (a boolean, only for `'string'` fields: `TypeError` otherwise) and `coerce` (a boolean, `TypeError` otherwise). With `trim` a string value is trimmed before anything else is looked at, so a blank string is *missing*, and the trimmed value is what is checked and returned.",
              "With `coerce` a value of the wrong type is converted before the type check: for a number field a string that holds a decimal number (optional sign, digits, optional fraction, surrounding blanks allowed, e.g. `' 42 '` or `-3.5`) becomes that number; for a boolean field the strings `true` and `false` (any case, surrounding blanks allowed) become booleans; for a string field a number or boolean becomes `String(value)`. Everything else is left alone and fails the type check as before. The converted value is what the later rules see and what `value` holds."),
        code={
            "src/schema.js::field_options": '''
                for (const key of ['trim', 'coerce']) {
                  if (rule[key] === undefined) continue;
                  if (typeof rule[key] !== 'boolean') throw new TypeError(`${key} of ${name} must be a boolean`);
                  if (key === 'trim' && type !== 'string') throw new TypeError(`trim only applies to strings (${name})`);
                  def[key] = rule[key];
                  delete rule[key];
                }
            ''',
            "src/schema.js::normalize": '''
                if (def.trim && typeof v === 'string') v = v.trim();
            ''',
            "src/schema.js::coerce": '''
                if (def.coerce) {
                  if (def.type === 'number' && typeof v === 'string' && /^\\s*[+-]?(\\d+\\.?\\d*|\\.\\d+)\\s*$/.test(v)) v = Number(v);
                  else if (def.type === 'boolean' && typeof v === 'string' && /^\\s*(true|false)\\s*$/i.test(v)) v = v.trim().toLowerCase() === 'true';
                  else if (def.type === 'string' && (typeof v === 'number' || typeof v === 'boolean')) v = String(v);
                }
            ''',
        },
        readme="## Coercion and trimming\n\n`trim: true` trims strings first (blank means missing); `coerce: true` converts numeric strings, `'true'`/`'false'` and numbers/booleans to the declared type before checking.\n",
        vtests='''
          test('coerce basic', () => {
            const s = new Schema({ age: { type: 'number', coerce: true } });
            assert.deepEqual(s.validate({ age: '42' }).value, { age: 42 });
          });
        ''',
        tests='''
          test('trim', () => {
            const s = new Schema({ name: { required: true, trim: true }, note: { trim: true }, raw: {} });
            assert.deepEqual(s.validate({ name: '  Ana  ', note: '\\t x\\n', raw: ' keep ' }).value, { name: 'Ana', note: 'x', raw: ' keep ' });
            assert.deepEqual(s.validate({ name: '   ' }).errors, { name: ['is required'] });
            assert.deepEqual(s.validate({ name: 'a', note: '   ' }).value, { name: 'a' });
            assert.deepEqual(s.validate({ name: 5 }).errors, { name: ['must be a string'] });
            const data = { name: '  Ana ' };
            s.validate(data);
            assert.equal(data.name, '  Ana ');
          });

          test('coerce', () => {
            const s = new Schema({ n: { type: 'number', coerce: true }, b: { type: 'boolean', coerce: true }, s: { coerce: true }, plain: { type: 'number' } });
            const ok = s.validate({ n: ' 42 ', b: ' TRUE ', s: 7 });
            assert.deepEqual(ok, { ok: true, errors: {}, value: { n: 42, b: true, s: '7' } });
            assert.deepEqual(s.validate({ n: '-3.5', b: 'false', s: false }).value, { n: -3.5, b: false, s: 'false' });
            assert.deepEqual(s.validate({ n: '+.5' }).value, { n: 0.5 });
            assert.deepEqual(s.validate({ n: '7.' }).value, { n: 7 });
            assert.deepEqual(s.validate({ n: 5, b: true, s: 'x' }).value, { n: 5, b: true, s: 'x' });
            assert.deepEqual(s.validate({ n: '4e2' }).errors, { n: ['must be a number'] });
            assert.deepEqual(s.validate({ n: 'abc' }).errors, { n: ['must be a number'] });
            assert.deepEqual(s.validate({ n: '1 2' }).errors, { n: ['must be a number'] });
            assert.deepEqual(s.validate({ b: 'yes' }).errors, { b: ['must be a boolean'] });
            assert.deepEqual(s.validate({ b: 1 }).errors, { b: ['must be a boolean'] });
            assert.deepEqual(s.validate({ s: {} }).errors, { s: ['must be a string'] });
            assert.deepEqual(s.validate({ plain: '5' }).errors, { plain: ['must be a number'] });
            assert.deepEqual(s.validate({ n: NaN }).errors, { n: ['must be a number'] });
          });

          test('trim and coerce options are validated', () => {
            for (const bad of ['yes', 1, null]) {
              assert.throws(() => new Schema({ a: { coerce: bad } }), TypeError, String(bad));
              assert.throws(() => new Schema({ a: { trim: bad } }), TypeError, String(bad));
            }
            assert.throws(() => new Schema({ a: { type: 'number', trim: true } }), TypeError);
            assert.throws(() => new Schema({ a: { type: 'boolean', trim: false } }), TypeError);
            assert.ok(new Schema({ a: { type: 'number', coerce: true }, b: { trim: true, coerce: true } }));
          });
        ''',
        cross={
            "range": {"tests": '''
              test('coerced numbers meet the range rules', () => {
                const s = new Schema({ qty: { type: 'number', coerce: true, integer: true, min: 1, max: 5 } });
                assert.deepEqual(s.validate({ qty: '3' }).value, { qty: 3 });
                assert.deepEqual(s.validate({ qty: '9' }).errors, { qty: ['must be at most 5'] });
                assert.deepEqual(s.validate({ qty: '2.5' }).errors, { qty: ['must be a whole number'] });
              });
            '''},
            "length": {"tests": '''
              test('trimmed strings meet the length rules', () => {
                const s = new Schema({ name: { trim: true, minLength: 3 }, code: { coerce: true, maxLength: 2 } });
                assert.deepEqual(s.validate({ name: ' ab ' }).errors, { name: ['must be at least 3 characters'] });
                assert.deepEqual(s.validate({ name: 'abc', code: 123 }).errors, { code: ['must be at most 2 characters'] });
                assert.deepEqual(s.validate({ name: ' abc ', code: 12 }).value, { name: 'abc', code: '12' });
              });
            '''},
            "oneof": {"tests": '''
              test('coerced values meet oneOf', () => {
                const s = new Schema({ level: { type: 'number', coerce: true, oneOf: [1, 2] }, on: { type: 'boolean', coerce: true, oneOf: [true] } });
                assert.deepEqual(s.validate({ level: '2', on: 'true' }).value, { level: 2, on: true });
                assert.deepEqual(s.validate({ level: '3', on: 'false' }).errors, { level: ['must be one of: 1, 2'], on: ['must be one of: true'] });
              });
            '''},
        },
    ))

    S.append(Slice(
        id="cross", title="Rules across fields", d=3,
        pitch=("The sign-up form accepted a password confirmation that did not match, and contact details with neither phone nor email.",
               "Some rules involve several fields at once."),
        reqs=("`schema.mustMatch(a, b)` adds a rule: when both fields are present and valid (no errors of their own), they must be strictly equal, otherwise field `b` gets the error `must match a`. `schema.atLeastOne(names)` adds a rule: when none of the listed fields is present (`undefined`, `null` or empty string), the error `at least one of a, b is required` is added under the key `*`. Both validate their arguments (`RangeError` for names the schema does not have, `TypeError` for a `names` that is not a non-empty array of strings; `mustMatch` needs two different names) and return the schema for chaining. The rules run after all field checks, in the order they were added; `ok` and `errors` include them, `value` is not affected by them. `mustMatch` compares the values as they end up in `value`, while `atLeastOne` looks at the raw input.",),
        code={
            "src/schema.js::init": "this.rules = [];",
            "src/schema.js::form_checks": '''
                for (const r of this.rules) {
                  if (r.kind === 'match') {
                    if (!errors[r.a] && !errors[r.b] && this._peek(value, r.a) !== undefined && this._peek(value, r.b) !== undefined
                      && this._peek(value, r.a) !== this._peek(value, r.b)) {
                      (errors[r.b] = errors[r.b] || []).push(`must match ${r.a}`);
                    }
                  } else {
                    const present = r.names.some((n) => {
                      const x = this._peek(data, n);
                      return x !== undefined && x !== null && x !== '';
                    });
                    if (!present) (errors['*'] = errors['*'] || []).push(`at least one of ${r.names.join(', ')} is required`);
                  }
                }
            ''',
            "src/schema.js::methods": '''
                mustMatch(a, b) {
                  for (const n of [a, b]) if (!this.fields.has(n)) throw new RangeError(`unknown field: ${n}`);
                  if (a === b) throw new RangeError('mustMatch needs two different fields');
                  this.rules.push({ kind: 'match', a, b });
                  return this;
                }

                atLeastOne(names) {
                  if (!Array.isArray(names) || names.length === 0 || !names.every((n) => typeof n === 'string')) {
                    throw new TypeError('names must be a non-empty array of strings');
                  }
                  for (const n of names) if (!this.fields.has(n)) throw new RangeError(`unknown field: ${n}`);
                  this.rules.push({ kind: 'any', names: [...names] });
                  return this;
                }
            ''',
        },
        readme="## Rules across fields\n\n`schema.mustMatch(a, b)` (error `must match a` on `b`) and `schema.atLeastOne([...])` (error under `*`) run after the field checks; both return the schema.\n",
        vtests='''
          test('cross basic', () => {
            const s = new Schema({ password: { required: true }, confirm: {} }).mustMatch('password', 'confirm');
            assert.deepEqual(s.validate({ password: 'a', confirm: 'b' }).errors, { confirm: ['must match password'] });
          });
        ''',
        tests='''
          test('mustMatch', () => {
            const s = new Schema({ password: { required: true }, confirm: { required: true } });
            assert.equal(s.mustMatch('password', 'confirm'), s);
            assert.deepEqual(s.validate({ password: 'secret', confirm: 'secret' }), { ok: true, errors: {}, value: { password: 'secret', confirm: 'secret' } });
            assert.deepEqual(s.validate({ password: 'secret', confirm: 'Secret' }).errors, { confirm: ['must match password'] });
            assert.deepEqual(s.validate({ password: 'secret' }).errors, { confirm: ['is required'] });
            assert.deepEqual(s.validate({ password: 5, confirm: 'xx' }).errors, { password: ['must be a string'] });
            assert.deepEqual(s.validate({ password: 'secret', confirm: 5 }).errors, { confirm: ['must be a string'] });
            assert.deepEqual(s.validate({ password: 'secret', confirm: 'x' }).value, { password: 'secret', confirm: 'x' });
            const n = new Schema({ a: { type: 'number' }, b: { type: 'number' } }).mustMatch('a', 'b');
            assert.equal(n.validate({ a: 0, b: 0 }).ok, true);
            assert.deepEqual(n.validate({ a: 0, b: 1 }).errors, { b: ['must match a'] });
            assert.equal(n.validate({ a: 3 }).ok, true);
            assert.equal(n.validate({}).ok, true);
          });

          test('atLeastOne', () => {
            const s = new Schema({ email: {}, phone: {}, fax: {}, name: { required: true } });
            s.atLeastOne(['email', 'phone']);
            assert.equal(s.validate({ name: 'a', phone: '123' }).ok, true);
            assert.deepEqual(s.validate({ name: 'a' }).errors, { '*': ['at least one of email, phone is required'] });
            assert.deepEqual(s.validate({ name: 'a', email: '', phone: null }).errors, { '*': ['at least one of email, phone is required'] });
            assert.deepEqual(s.validate({ email: 'x' }).errors, { name: ['is required'] });
            assert.deepEqual(s.validate({ name: 'a', fax: 'f' }).errors, { '*': ['at least one of email, phone is required'] });
            assert.deepEqual(s.validate({}).errors, { name: ['is required'], '*': ['at least one of email, phone is required'] });
            s.atLeastOne(['fax']);
            assert.deepEqual(s.validate({ name: 'a', email: 'x' }).errors, { '*': ['at least one of fax is required'] });
            const bad = new Schema({ n: { type: 'number' }, e: {} }).atLeastOne(['n', 'e']);
            assert.equal(bad.validate({ n: 'x' }).errors['*'], undefined);
          });

          test('rules are validated', () => {
            const s = new Schema({ a: {}, b: {} });
            assert.throws(() => s.mustMatch('a', 'zzz'), RangeError);
            assert.throws(() => s.mustMatch('zzz', 'a'), RangeError);
            assert.throws(() => s.mustMatch('a', 'a'), RangeError);
            for (const bad of [[], 'a', null, [1], ['a', 5], {}]) assert.throws(() => s.atLeastOne(bad), TypeError, String(bad));
            assert.throws(() => s.atLeastOne(['a', 'zzz']), RangeError);
            assert.equal(s.validate({}).ok, true);
          });
        ''',
        cross={
            "coerce": {"tests": '''
              test('matching happens after coercion', () => {
                const s = new Schema({ a: { type: 'number', coerce: true }, b: { type: 'number', coerce: true } }).mustMatch('a', 'b');
                assert.equal(s.validate({ a: '5', b: 5 }).ok, true);
                assert.deepEqual(s.validate({ a: '5', b: '6' }).errors, { b: ['must match a'] });
              });
            '''},
        },
    ))

    S.append(Slice(
        id="nested", title="Nested data", d=4,
        pitch=("Checkout posts address.city and address.zip as an object and the validator only looks at the top level.",
               "Fields inside nested objects need to be validated too."),
        reqs=("A field name may be a dotted path such as `address.city`: each part must be a word (`[A-Za-z_][A-Za-z0-9_]*`), otherwise `RangeError`. The value is read by walking the input along the path; when a part is missing or the thing along the way is not a plain object (a string, an array, `null`), the field counts as missing. Errors are reported under the full dotted name, and `value` is built as nested objects with the same structure (`{ address: { city: 'Oslo' } }`), only containing valid fields, so a path that has no valid field leaves no empty objects behind. Names without a dot work as before.",
              "Two fields whose paths collide (`a` and `a.b`) are a `RangeError` when the schema is built (in either order). `data` is never modified."),
        code={
            "src/schema.js::helpers": '''
                const PATH = /^[A-Za-z_][A-Za-z0-9_]*(\\.[A-Za-z_][A-Za-z0-9_]*)*$/;

                function isObject(x) {
                  return typeof x === 'object' && x !== null && !Array.isArray(x);
                }

                function getPath(obj, path) {
                  let cur = obj;
                  for (const part of path.split('.')) {
                    if (!isObject(cur)) return undefined;
                    cur = cur[part];
                  }
                  return cur;
                }

                function setPath(obj, path, v) {
                  const parts = path.split('.');
                  let cur = obj;
                  for (const part of parts.slice(0, -1)) {
                    if (!isObject(cur[part])) cur[part] = {};
                    cur = cur[part];
                  }
                  cur[parts[parts.length - 1]] = v;
                }
            ''',
            "src/schema.js::init": "this.paths = [];",
            "src/schema.js::field_options": '''
                if (!PATH.test(name)) throw new RangeError(`bad field path: ${name}`);
                for (const other of this.paths) {
                  if (other.startsWith(name + '.') || name.startsWith(other + '.')) throw new RangeError(`field paths collide: ${other} and ${name}`);
                }
                this.paths.push(name);
            ''',
            "src/schema.js::read_value": "let v = getPath(data, name);",
            "src/schema.js::store_value": "setPath(value, name, v);",
            "src/schema.js::peek": '''
                _peek(obj, name) {
                  return getPath(obj, name);
                }
            ''',
        },
        readme="## Nested data\n\nField names can be dotted paths (`address.city`): read by walking the input, errors under the dotted name, `value` rebuilt as nested objects. Colliding paths (`a` and `a.b`) are a `RangeError`.\n",
        vtests='''
          test('nested basic', () => {
            const s = new Schema({ 'address.city': { required: true } });
            assert.deepEqual(s.validate({ address: { city: 'Oslo' } }).value, { address: { city: 'Oslo' } });
          });
        ''',
        tests='''
          test('nested values and errors', () => {
            const s = new Schema({
              name: { required: true },
              'address.city': { required: true },
              'address.zip': { type: 'number' },
              'contact.phone.mobile': {},
            });
            const good = s.validate({ name: 'Ana', address: { city: 'Oslo', zip: 123, street: 'x' }, contact: { phone: { mobile: '555' } }, extra: 1 });
            assert.deepEqual(good, { ok: true, errors: {}, value: { name: 'Ana', address: { city: 'Oslo', zip: 123 }, contact: { phone: { mobile: '555' } } } });
            const bad = s.validate({ name: 'Ana', address: { zip: 'x' } });
            assert.deepEqual(bad.errors, { 'address.city': ['is required'], 'address.zip': ['must be a number'] });
            assert.deepEqual(bad.value, { name: 'Ana' });
            assert.deepEqual(s.validate({ name: 'Ana', address: 'Oslo' }).errors, { 'address.city': ['is required'] });
            assert.deepEqual(s.validate({ name: 'Ana', address: ['Oslo'] }).errors, { 'address.city': ['is required'] });
            assert.deepEqual(s.validate({ name: 'Ana', address: null }).errors, { 'address.city': ['is required'] });
            assert.deepEqual(s.validate({ name: 'Ana', address: { city: 'Oslo' }, contact: 5 }).value, { name: 'Ana', address: { city: 'Oslo' } });
            assert.deepEqual(s.validate({ name: 'Ana', address: { city: 'Oslo' }, contact: { phone: 'x' } }).value, { name: 'Ana', address: { city: 'Oslo' } });
          });

          test('nested input is not modified', () => {
            const s = new Schema({ 'a.b': { required: true } });
            const data = { a: { b: 'x', c: 1 } };
            const r = s.validate(data);
            r.value.a.b = 'changed';
            assert.deepEqual(data, { a: { b: 'x', c: 1 } });
          });

          test('field paths are validated', () => {
            for (const bad of ['a.', '.a', 'a..b', 'a b', 'a.1', '1a', 'a-b', 'a.b-c', '.']) assert.throws(() => new Schema({ [bad]: {} }), RangeError, bad);
            assert.throws(() => new Schema({ a: {}, 'a.b': {} }), RangeError);
            assert.throws(() => new Schema({ 'a.b': {}, a: {} }), RangeError);
            assert.throws(() => new Schema({ 'a.b.c': {}, 'a.b': {} }), RangeError);
            assert.ok(new Schema({ 'a.b': {}, 'a.c': {}, ab: {}, 'a_b.c': {} }));
          });
        ''',
        cross={
            "cross": {
                "reqs": ("The rules of `mustMatch` and `atLeastOne` use the same dotted names; `mustMatch` reports under the second field's dotted name.",),
                "tests": '''
                  test('rules with nested names', () => {
                    const s = new Schema({ 'login.password': { required: true }, 'login.confirm': {}, 'contact.email': {}, 'contact.phone': {} });
                    s.mustMatch('login.password', 'login.confirm').atLeastOne(['contact.email', 'contact.phone']);
                    assert.deepEqual(s.validate({ login: { password: 'a', confirm: 'b' } }).errors, { 'login.confirm': ['must match login.password'], '*': ['at least one of contact.email, contact.phone is required'] });
                    assert.equal(s.validate({ login: { password: 'a', confirm: 'a' }, contact: { phone: '1' } }).ok, true);
                  });
                '''},
            "messages": {"tests": '''
              test('messages with nested names', () => {
                const s = new Schema({ 'a.b': { required: true, messages: { required: '<label> needed' } } });
                assert.deepEqual(s.validate({}).errors, { 'a.b': ['a.b needed'] });
              });
            '''},
            "coerce": {"tests": '''
              test('coercion in nested fields', () => {
                const s = new Schema({ 'order.qty': { type: 'number', coerce: true }, 'order.note': { trim: true } });
                assert.deepEqual(s.validate({ order: { qty: '3', note: ' hi ' } }).value, { order: { qty: 3, note: 'hi' } });
              });
            '''},
        },
    ))

    return S


APP = App(
    name="formgate", lang="javascript", title="the form validation library", role="a web shop developer", key="FORM",
    base={
        "README.md": README + "\n@@blocks features\n",
        "package.json": '{\n  "name": "formgate",\n  "version": "1.0.0",\n  "private": true,\n  "main": "index.js",\n  "scripts": {\n    "test": "node --test test/*.test.js"\n  }\n}\n',
        "index.js": "'use strict';\nmodule.exports = require('./src/schema');\n",
        "src/schema.js": SCHEMA,
        ".gitignore": "node_modules/\n",
    },
    visible={"test/basic.test.js": VISIBLE},
    hidden={"test/features.test.js": HIDDEN},
    verify="node --test test/*.test.js",
)

register_app("feature-js-formgate", APP, make_slices, n=18, summary="form validation: lengths, ranges, choices, patterns, custom checks, messages, coercion, cross-field and nested rules")
