"""Schema-driven form validation with nested paths (javascript): bugs injected into a validation library."""
from fx import Lib, dd
from generators.fix._lang2 import JS_VERIFY, PACKAGE_JSON, register_libs

README = dd(r'''
    # formcheck

    Validates and cleans form submissions against a schema. CommonJS:
    `const { validate } = require('./src/validate')`, `const { checkString, checkNumber, checkBoolean, isMissing } = require('./src/rules')`,
    `const { join } = require('./src/path')`.

    ## Paths (`src/path.js`)

    `join(parent, key)` builds an error path: a numeric `key` gives `parent[key]`; a string key gives `parent.key`, or just
    `key` when `parent` is `''`. So `join(join('', 'items'), 0)` is `'items[0]'` and `join('items[0]', 'sku')` is
    `'items[0].sku'`.

    ## Field rules (`src/rules.js`)

    * `isMissing(v)` is true for `undefined`, `null` and strings that are empty or only whitespace.
    * `checkString(rule, raw)` returns `{ value }` or `{ error }`. A non-string is `{ error: 'type' }`. The value is trimmed
      (unless `rule.trim === false`), then lower-cased if `rule.lower`. Then, in this order and stopping at the first
      failure: `minLen` (`'minLen'`), `maxLen` (`'maxLen'`), `pattern` (a RegExp that must match, `'pattern'`),
      `oneOf` (array of allowed values, `'oneOf'`). Lengths are those of the cleaned value.
    * `checkNumber(rule, raw)`: accepts finite numbers, and strings that after trimming look like `-12` or `3.5` (optional
      minus, digits, optional `.digits`), which are converted. Anything else, including `NaN` and `Infinity`, is
      `{ error: 'type' }`. Then `integer` (`'integer'`), `min` (`'min'`), `max` (`'max'`), both limits inclusive.
    * `checkBoolean(raw)`: booleans pass; strings `true`/`on` and `false`/`off` (trimmed, any case) are converted;
      anything else is `{ error: 'type' }`.

    ## `validate(schema, data, opts = {})` (`src/validate.js`)

    Returns `{ ok, errors, value }`. `errors` is an array of `{ path, code }` in the order the problems were found, `ok`
    is `errors.length === 0`, and `value` is the cleaned data. A `schema` is an object mapping field names to field
    rules; its optional key `$rules` holds cross-field rules (it is not a field). If `data` is not a plain object
    (an array, `null`, a number, ...) the result has the single error `{ path: '', code: 'type' }` and `value` is `{}`.

    A *field rule* has a `type` (`string`, `number`, `boolean`, `array` or `object`), optional `required` (default
    `false`) and optional `default`, plus the type's own settings.

    1. **Missing values.** If the input is missing (`isMissing`): a `required` field adds `{ path, code: 'required' }`;
       otherwise a field with a `default` gets that default as its value (the default is not validated), and a field
       without one is left out of `value`.
    2. **Present values** are checked by type: `string`, `number` and `boolean` use the checks above (their `error` becomes
       the error `code`; the cleaned value goes into `value`).
    3. `array`: the input must be an array (else `'type'`). `minItems` and `maxItems` compare its length (`'minItems'`,
       `'maxItems'`) and are reported before the items are looked at. Every item is validated with the rule in `of`,
       and items are always required, so a missing item is a `'required'` error at its index. Item paths are
       `field[0]`, `field[1]`, ... With `unique: true`, if no item had an error and two cleaned items are equal
       (compared by `JSON.stringify`), the error `'unique'` is reported at the array's path.
    4. `object`: the input must be a plain object (not an array, not `null`; else `'type'`); its `fields` is a nested schema
       (with its own optional `$rules`), validated with paths such as `address.zip`.
    5. **Unknown keys** of an object are dropped from `value`; with `opts.strict` each one adds `{ path, code: 'unknown' }`
       (after the field errors of that object and before its `$rules`).
    6. **Cross-field rules** run last for their object, in array order, on the cleaned values:
       * `{ type: 'sameAs', field, other }`: when both are present in the cleaned object and differ (`!==`), error
         `'sameAs'` at `field`'s path.
       * `{ type: 'requiredIf', field, when: { field, equals } }`: when the cleaned `when.field` is `=== equals` and
         `field` is absent from the cleaned object, error `'required'` at `field`'s path.
       * `{ type: 'atLeastOne', fields }`: when none of `fields` is present, error `'atLeastOne'` at the *object's* path
         (`''` for the top level).
    7. A field is present in the cleaned object when its key exists, even if the value is `false`, `0` or `''`.
    8. Any other `type` is a `TypeError`, thrown when a present value of such a field is checked.
''')

PATH = dd(r'''
    'use strict';

    function join(parent, key) {
      if (typeof key === 'number') return `${parent}[${key}]`;
      return parent === '' ? key : `${parent}.${key}`;
    }

    module.exports = { join };
''')

RULES = dd(r'''
    'use strict';

    const TRUE_WORDS = new Set(['true', 'on']);
    const FALSE_WORDS = new Set(['false', 'off']);

    function isMissing(v) {
      return v === undefined || v === null || (typeof v === 'string' && v.trim() === '');
    }

    function checkString(rule, raw) {
      if (typeof raw !== 'string') return { error: 'type' };
      let v = rule.trim === false ? raw : raw.trim();
      if (rule.lower) v = v.toLowerCase();
      if (rule.minLen !== undefined && v.length < rule.minLen) return { error: 'minLen' };
      if (rule.maxLen !== undefined && v.length > rule.maxLen) return { error: 'maxLen' };
      if (rule.pattern && !rule.pattern.test(v)) return { error: 'pattern' };
      if (rule.oneOf && !rule.oneOf.includes(v)) return { error: 'oneOf' };
      return { value: v };
    }

    function checkNumber(rule, raw) {
      let v;
      if (typeof raw === 'number') {
        v = raw;
      } else if (typeof raw === 'string' && /^-?\d+(\.\d+)?$/.test(raw.trim())) {
        v = Number(raw.trim());
      } else {
        return { error: 'type' };
      }
      if (!Number.isFinite(v)) return { error: 'type' };
      if (rule.integer && !Number.isInteger(v)) return { error: 'integer' };
      if (rule.min !== undefined && v < rule.min) return { error: 'min' };
      if (rule.max !== undefined && v > rule.max) return { error: 'max' };
      return { value: v };
    }

    function checkBoolean(raw) {
      if (typeof raw === 'boolean') return { value: raw };
      if (typeof raw === 'string') {
        const word = raw.trim().toLowerCase();
        if (TRUE_WORDS.has(word)) return { value: true };
        if (FALSE_WORDS.has(word)) return { value: false };
      }
      return { error: 'type' };
    }

    module.exports = { isMissing, checkString, checkNumber, checkBoolean };
''')

VALIDATE = dd(r'''
    'use strict';

    const { join } = require('./path');
    const { isMissing, checkString, checkNumber, checkBoolean } = require('./rules');

    function isPlainObject(v) {
      return typeof v === 'object' && v !== null && !Array.isArray(v);
    }

    function validateField(rule, raw, path, errors, opts) {
      if (isMissing(raw)) {
        if (rule.required) {
          errors.push({ path, code: 'required' });
          return { present: false };
        }
        if (rule.default !== undefined) return { present: true, value: rule.default };
        return { present: false };
      }
      let res;
      if (rule.type === 'string') res = checkString(rule, raw);
      else if (rule.type === 'number') res = checkNumber(rule, raw);
      else if (rule.type === 'boolean') res = checkBoolean(raw);
      else if (rule.type === 'array') return validateArray(rule, raw, path, errors, opts);
      else if (rule.type === 'object') return validateNested(rule, raw, path, errors, opts);
      else throw new TypeError(`unknown field type ${rule.type}`);
      if (res.error) {
        errors.push({ path, code: res.error });
        return { present: false };
      }
      return { present: true, value: res.value };
    }

    function validateArray(rule, raw, path, errors, opts) {
      if (!Array.isArray(raw)) {
        errors.push({ path, code: 'type' });
        return { present: false };
      }
      if (rule.minItems !== undefined && raw.length < rule.minItems) {
        errors.push({ path, code: 'minItems' });
        return { present: false };
      }
      if (rule.maxItems !== undefined && raw.length > rule.maxItems) {
        errors.push({ path, code: 'maxItems' });
        return { present: false };
      }
      const before = errors.length;
      const out = [];
      raw.forEach((item, i) => {
        const r = validateField({ ...rule.of, required: true }, item, join(path, i), errors, opts);
        if (r.present) out.push(r.value);
      });
      if (rule.unique && errors.length === before) {
        const seen = new Set(out.map((v) => JSON.stringify(v)));
        if (seen.size !== out.length) errors.push({ path, code: 'unique' });
      }
      return { present: true, value: out };
    }

    function validateNested(rule, raw, path, errors, opts) {
      if (!isPlainObject(raw)) {
        errors.push({ path, code: 'type' });
        return { present: false };
      }
      return { present: true, value: validateObject(rule.fields, raw, path, errors, opts) };
    }

    function validateObject(schema, data, path, errors, opts) {
      const out = {};
      for (const key of Object.keys(schema)) {
        if (key === '$rules') continue;
        const r = validateField(schema[key], data[key], join(path, key), errors, opts);
        if (r.present) out[key] = r.value;
      }
      if (opts.strict) {
        for (const key of Object.keys(data)) {
          if (!(key in schema) || key === '$rules') errors.push({ path: join(path, key), code: 'unknown' });
        }
      }
      for (const rule of schema.$rules || []) {
        if (rule.type === 'sameAs') {
          if (rule.field in out && rule.other in out && out[rule.field] !== out[rule.other]) {
            errors.push({ path: join(path, rule.field), code: 'sameAs' });
          }
        } else if (rule.type === 'requiredIf') {
          if (out[rule.when.field] === rule.when.equals && !(rule.field in out)) {
            errors.push({ path: join(path, rule.field), code: 'required' });
          }
        } else if (rule.type === 'atLeastOne') {
          if (!rule.fields.some((f) => f in out)) errors.push({ path, code: 'atLeastOne' });
        }
      }
      return out;
    }

    function validate(schema, data, opts = {}) {
      const errors = [];
      if (!isPlainObject(data)) return { ok: false, errors: [{ path: '', code: 'type' }], value: {} };
      const value = validateObject(schema, data, '', errors, opts);
      return { ok: errors.length === 0, errors, value };
    }

    module.exports = { validate };
''')

VISIBLE = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { validate } = require('../src/validate');
    const { join } = require('../src/path');

    test('join', () => {
      assert.equal(join('items', 0), 'items[0]');
      assert.equal(join('', 'name'), 'name');
    });

    test('a valid signup', () => {
      const schema = { name: { type: 'string', required: true }, age: { type: 'number' } };
      const r = validate(schema, { name: '  Ada ', age: '36' });
      assert.equal(r.ok, true);
      assert.deepEqual(r.value, { name: 'Ada', age: 36 });
    });
''')

HIDDEN = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { validate } = require('../src/validate');
    const { join } = require('../src/path');
    const { isMissing, checkString, checkNumber, checkBoolean } = require('../src/rules');

    const codes = (r) => r.errors.map((e) => `${e.path}:${e.code}`);

    test('join', () => {
      assert.equal(join('', 'a'), 'a');
      assert.equal(join('a', 'b'), 'a.b');
      assert.equal(join('a', 0), 'a[0]');
      assert.equal(join('a[0]', 'b'), 'a[0].b');
      assert.equal(join('', 3), '[3]');
      assert.equal(join(join(join('', 'items'), 2), 'sku'), 'items[2].sku');
    });

    test('isMissing', () => {
      for (const v of [undefined, null, '', '   ', '\t\n']) assert.equal(isMissing(v), true);
      for (const v of [0, false, 'a', ' a ', [], {}, NaN]) assert.equal(isMissing(v), false);
    });

    test('checkString trims, lowers and checks in order', () => {
      assert.deepEqual(checkString({}, '  hi  '), { value: 'hi' });
      assert.deepEqual(checkString({ trim: false }, '  hi  '), { value: '  hi  ' });
      assert.deepEqual(checkString({ lower: true }, ' HeLLo '), { value: 'hello' });
      assert.deepEqual(checkString({}, 5), { error: 'type' });
      assert.deepEqual(checkString({}, ['a']), { error: 'type' });
      assert.deepEqual(checkString({ minLen: 3 }, ' ab '), { error: 'minLen' });
      assert.deepEqual(checkString({ minLen: 3 }, ' abc '), { value: 'abc' });
      assert.deepEqual(checkString({ maxLen: 3 }, ' abcd '), { error: 'maxLen' });
      assert.deepEqual(checkString({ maxLen: 3 }, ' abc '), { value: 'abc' });
      assert.deepEqual(checkString({ maxLen: 4, trim: false }, ' abc '), { error: 'maxLen' });
      assert.deepEqual(checkString({ pattern: /^[a-z]+$/ }, 'abc1'), { error: 'pattern' });
      assert.deepEqual(checkString({ pattern: /^[a-z]+$/ }, 'abc'), { value: 'abc' });
      assert.deepEqual(checkString({ oneOf: ['red', 'blue'] }, 'green'), { error: 'oneOf' });
      assert.deepEqual(checkString({ oneOf: ['red', 'blue'], lower: true }, ' RED '), { value: 'red' });
    });

    test('checkString reports the first failing check', () => {
      assert.deepEqual(checkString({ minLen: 5, pattern: /^\d+$/, oneOf: ['x'] }, 'ab'), { error: 'minLen' });
      assert.deepEqual(checkString({ maxLen: 1, pattern: /^\d+$/, oneOf: ['x'] }, 'ab'), { error: 'maxLen' });
      assert.deepEqual(checkString({ minLen: 1, pattern: /^\d+$/, oneOf: ['x'] }, 'ab'), { error: 'pattern' });
      assert.deepEqual(checkString({ minLen: 1, pattern: /^\w+$/, oneOf: ['x'] }, 'ab'), { error: 'oneOf' });
    });

    test('checkNumber conversions', () => {
      assert.deepEqual(checkNumber({}, 5), { value: 5 });
      assert.deepEqual(checkNumber({}, -2.5), { value: -2.5 });
      assert.deepEqual(checkNumber({}, 0), { value: 0 });
      assert.deepEqual(checkNumber({}, '12'), { value: 12 });
      assert.deepEqual(checkNumber({}, ' -3.5 '), { value: -3.5 });
      assert.deepEqual(checkNumber({}, '0.25'), { value: 0.25 });
      for (const bad of ['1e3', '1.', '.5', '+4', '1,5', 'abc', '--1', '1 2', NaN, Infinity, -Infinity, true, [], {}]) {
        assert.deepEqual(checkNumber({}, bad), { error: 'type' }, String(bad));
      }
    });

    test('checkNumber limits are inclusive', () => {
      assert.deepEqual(checkNumber({ min: 1 }, 0), { error: 'min' });
      assert.deepEqual(checkNumber({ min: 1 }, 1), { value: 1 });
      assert.deepEqual(checkNumber({ max: 10 }, 11), { error: 'max' });
      assert.deepEqual(checkNumber({ max: 10 }, 10), { value: 10 });
      assert.deepEqual(checkNumber({ min: 0, max: 0 }, 0), { value: 0 });
      assert.deepEqual(checkNumber({ integer: true }, 2.5), { error: 'integer' });
      assert.deepEqual(checkNumber({ integer: true }, '2.0'), { value: 2 });
      assert.deepEqual(checkNumber({ integer: true }, 4), { value: 4 });
      assert.deepEqual(checkNumber({ integer: true, min: 5 }, 2.5), { error: 'integer' });
      assert.deepEqual(checkNumber({ min: 5, max: 1 }, 3), { error: 'min' });
      assert.deepEqual(checkNumber({ min: -5 }, '-5'), { value: -5 });
    });

    test('checkBoolean', () => {
      assert.deepEqual(checkBoolean(true), { value: true });
      assert.deepEqual(checkBoolean(false), { value: false });
      assert.deepEqual(checkBoolean('true'), { value: true });
      assert.deepEqual(checkBoolean(' ON '), { value: true });
      assert.deepEqual(checkBoolean('False'), { value: false });
      assert.deepEqual(checkBoolean('off'), { value: false });
      for (const bad of ['yes', 'no', '1', '0', 1, 0, null, 'truee', [], {}]) assert.deepEqual(checkBoolean(bad), { error: 'type' }, String(bad));
    });

    test('flat form: cleaned values and result shape', () => {
      const schema = {
        name: { type: 'string', required: true, maxLen: 10 },
        age: { type: 'number', integer: true, min: 0 },
        news: { type: 'boolean' },
        nick: { type: 'string' },
      };
      const r = validate(schema, { name: ' Ada ', age: '36', news: 'on', extra: 1 });
      assert.deepEqual(r, { ok: true, errors: [], value: { name: 'Ada', age: 36, news: true } });
    });

    test('required fields', () => {
      const schema = { a: { type: 'string', required: true }, b: { type: 'number', required: true }, c: { type: 'boolean', required: true } };
      const r = validate(schema, { a: '  ', b: null });
      assert.equal(r.ok, false);
      assert.deepEqual(codes(r), ['a:required', 'b:required', 'c:required']);
      assert.deepEqual(r.value, {});
    });

    test('zero and false are present values', () => {
      const schema = { n: { type: 'number', required: true }, f: { type: 'boolean', required: true } };
      const r = validate(schema, { n: 0, f: false });
      assert.deepEqual(r, { ok: true, errors: [], value: { n: 0, f: false } });
    });

    test('defaults fill missing values only', () => {
      const schema = { role: { type: 'string', default: 'guest' }, n: { type: 'number', default: 0 }, on: { type: 'boolean', default: false }, k: { type: 'string', required: true, default: 'x' } };
      const r = validate(schema, { role: ' ', n: undefined });
      assert.deepEqual(r.value, { role: 'guest', n: 0, on: false });
      assert.deepEqual(codes(r), ['k:required']);
      const given = validate(schema, { role: 'admin', n: 5, on: 'true', k: 'y' });
      assert.deepEqual(given.value, { role: 'admin', n: 5, on: true, k: 'y' });
    });

    test('defaults are not validated', () => {
      const r = validate({ code: { type: 'string', minLen: 5, default: 'ab' } }, {});
      assert.deepEqual(r, { ok: true, errors: [], value: { code: 'ab' } });
    });

    test('type errors and invalid values are dropped from value', () => {
      const schema = { a: { type: 'number' }, b: { type: 'string' }, c: { type: 'boolean' }, d: { type: 'string' } };
      const r = validate(schema, { a: 'x', b: 5, c: 'maybe', d: 'ok' });
      assert.deepEqual(codes(r), ['a:type', 'b:type', 'c:type']);
      assert.deepEqual(r.value, { d: 'ok' });
    });

    test('errors follow schema order and show the first failure of each field', () => {
      const schema = { z: { type: 'string', minLen: 3 }, a: { type: 'number', min: 10 }, m: { type: 'string', pattern: /^\d+$/ } };
      const r = validate(schema, { m: 'x', a: 3, z: 'q' });
      assert.deepEqual(codes(r), ['z:minLen', 'a:min', 'm:pattern']);
    });

    test('arrays: items, paths and cleaned values', () => {
      const schema = { tags: { type: 'array', of: { type: 'string', minLen: 2, lower: true } } };
      const ok = validate(schema, { tags: [' Red ', 'BLUE'] });
      assert.deepEqual(ok.value, { tags: ['red', 'blue'] });
      const bad = validate(schema, { tags: ['ok', 'x', 4, '  '] });
      assert.deepEqual(codes(bad), ['tags[1]:minLen', 'tags[2]:type', 'tags[3]:required']);
      assert.deepEqual(bad.value, { tags: ['ok'] });
    });

    test('arrays: not an array, item counts', () => {
      const schema = { xs: { type: 'array', of: { type: 'number' }, minItems: 2, maxItems: 3 } };
      assert.deepEqual(codes(validate(schema, { xs: 'nope' })), ['xs:type']);
      assert.deepEqual(codes(validate(schema, { xs: {} })), ['xs:type']);
      assert.deepEqual(codes(validate(schema, { xs: [1] })), ['xs:minItems']);
      assert.deepEqual(codes(validate(schema, { xs: [1, 2] })), []);
      assert.deepEqual(codes(validate(schema, { xs: [1, 2, 3] })), []);
      assert.deepEqual(codes(validate(schema, { xs: [1, 2, 3, 4] })), ['xs:maxItems']);
      assert.deepEqual(codes(validate(schema, { xs: ['a'] })), ['xs:minItems']);
      assert.deepEqual(codes(validate(schema, { xs: ['a', 'b', 'c', 'd'] })), ['xs:maxItems']);
      assert.deepEqual(validate(schema, { xs: [1] }).value, {});
      assert.deepEqual(validate(schema, { xs: [1, 2, 3, 4] }).value, {});
      assert.deepEqual(validate(schema, { xs: 'nope' }).value, {});
      assert.deepEqual(validate(schema, { xs: [1, 2] }).value, { xs: [1, 2] });
    });

    test('empty arrays are values, not missing', () => {
      const schema = { xs: { type: 'array', of: { type: 'number' }, required: true } };
      assert.deepEqual(validate(schema, { xs: [] }), { ok: true, errors: [], value: { xs: [] } });
      assert.deepEqual(codes(validate(schema, {})), ['xs:required']);
      assert.deepEqual(codes(validate({ xs: { type: 'array', of: { type: 'number' }, minItems: 1 } }, { xs: [] })), ['xs:minItems']);
    });

    test('arrays: unique', () => {
      const schema = { xs: { type: 'array', unique: true, of: { type: 'string' } } };
      assert.deepEqual(codes(validate(schema, { xs: ['a', 'b', 'a'] })), ['xs:unique']);
      assert.deepEqual(codes(validate(schema, { xs: ['a', ' a '] })), ['xs:unique']);
      assert.deepEqual(codes(validate(schema, { xs: ['a', 'b'] })), []);
      assert.deepEqual(codes(validate(schema, { xs: ['a', 5, 'a'] })), ['xs[1]:type']);
      const nums = { xs: { type: 'array', unique: true, of: { type: 'number' } } };
      assert.deepEqual(codes(validate(nums, { xs: ['1', 1] })), ['xs:unique']);
      assert.deepEqual(codes(validate(nums, { xs: ['1', '01'] })), ['xs:unique']);
      assert.deepEqual(codes(validate({ xs: { type: 'array', of: { type: 'string' } } }, { xs: ['a', 'a'] })), []);
    });

    test('nested objects', () => {
      const schema = {
        name: { type: 'string', required: true },
        address: { type: 'object', fields: { street: { type: 'string', required: true }, zip: { type: 'string', pattern: /^\d{5}$/ } } },
      };
      const ok = validate(schema, { name: 'A', address: { street: ' 1 Main ', zip: '12345', junk: true } });
      assert.deepEqual(ok.value, { name: 'A', address: { street: '1 Main', zip: '12345' } });
      const bad = validate(schema, { name: '', address: { zip: '1234' } });
      assert.deepEqual(codes(bad), ['name:required', 'address.street:required', 'address.zip:pattern']);
      assert.deepEqual(bad.value, { address: {} });
    });

    test('nested objects: wrong shapes and absence', () => {
      const schema = { a: { type: 'object', fields: { x: { type: 'number' } } } };
      assert.deepEqual(codes(validate(schema, { a: [] })), ['a:type']);
      assert.deepEqual(codes(validate(schema, { a: 'str' })), ['a:type']);
      assert.deepEqual(codes(validate(schema, { a: 5 })), ['a:type']);
      assert.deepEqual(validate(schema, {}).value, {});
      assert.deepEqual(validate(schema, { a: null }).value, {});
      assert.deepEqual(codes(validate({ a: { type: 'object', required: true, fields: {} } }, {})), ['a:required']);
      assert.deepEqual(validate(schema, { a: {} }).value, { a: {} });
    });

    test('arrays of objects', () => {
      const schema = {
        items: { type: 'array', required: true, minItems: 1, of: { type: 'object', fields: { sku: { type: 'string', required: true }, qty: { type: 'number', integer: true, min: 1 } } } },
      };
      const r = validate(schema, { items: [{ sku: 'a', qty: '2' }, { qty: 0 }, 'x', { sku: 'c', qty: 1.5 }] });
      assert.deepEqual(codes(r), ['items[1].sku:required', 'items[1].qty:min', 'items[2]:type', 'items[3].qty:integer']);
      assert.deepEqual(r.value, { items: [{ sku: 'a', qty: 2 }, {}, { sku: 'c' }] });
    });

    test('top level must be a plain object', () => {
      for (const bad of [null, undefined, [], 'x', 5, true]) {
        assert.deepEqual(validate({ a: { type: 'string' } }, bad), { ok: false, errors: [{ path: '', code: 'type' }], value: {} });
      }
    });

    test('unknown keys are only an error in strict mode', () => {
      const schema = { a: { type: 'string', required: true } };
      assert.deepEqual(validate(schema, { a: 'x', b: 1 }).errors, []);
      const r = validate({ ...schema, o: { type: 'object', fields: { k: { type: 'string' } } } }, { b: 1, a: '', o: { k: 'v', z: 0 }, c: 2 }, { strict: true });
      assert.deepEqual(codes(r), ['a:required', 'o.z:unknown', 'b:unknown', 'c:unknown']);
      const clean = validate(schema, { a: 'x' }, { strict: true });
      assert.deepEqual(clean, { ok: true, errors: [], value: { a: 'x' } });
    });

    test('strict mode does not flag $rules or declared fields', () => {
      const schema = { a: { type: 'string' }, $rules: [{ type: 'atLeastOne', fields: ['a'] }] };
      assert.deepEqual(validate(schema, { a: 'x' }, { strict: true }).errors, []);
    });

    test('sameAs', () => {
      const schema = {
        password: { type: 'string', required: true, minLen: 4 },
        confirm: { type: 'string' },
        $rules: [{ type: 'sameAs', field: 'confirm', other: 'password' }],
      };
      assert.deepEqual(codes(validate(schema, { password: 'secret', confirm: 'secreT' })), ['confirm:sameAs']);
      assert.deepEqual(codes(validate(schema, { password: 'secret', confirm: ' secret ' })), []);
      assert.deepEqual(codes(validate(schema, { password: 'secret' })), []);
      assert.deepEqual(codes(validate(schema, { confirm: 'secret' })), ['password:required']);
      assert.deepEqual(codes(validate(schema, { password: 'abc', confirm: 'abc' })), ['password:minLen']);
      const nums = { a: { type: 'number' }, b: { type: 'number' }, $rules: [{ type: 'sameAs', field: 'b', other: 'a' }] };
      assert.deepEqual(codes(validate(nums, { a: '1', b: 1 })), []);
      assert.deepEqual(codes(validate(nums, { a: 0, b: '0' })), []);
      assert.deepEqual(codes(validate(nums, { a: 0, b: '1' })), ['b:sameAs']);
    });

    test('requiredIf', () => {
      const schema = {
        country: { type: 'string', required: true },
        state: { type: 'string' },
        $rules: [{ type: 'requiredIf', field: 'state', when: { field: 'country', equals: 'US' } }],
      };
      assert.deepEqual(codes(validate(schema, { country: 'US' })), ['state:required']);
      assert.deepEqual(codes(validate(schema, { country: 'US', state: 'WA' })), []);
      assert.deepEqual(codes(validate(schema, { country: 'FR' })), []);
      assert.deepEqual(codes(validate(schema, { country: ' US ', state: ' ' })), ['state:required']);
      const flag = {
        gift: { type: 'boolean' },
        note: { type: 'string' },
        $rules: [{ type: 'requiredIf', field: 'note', when: { field: 'gift', equals: true } }],
      };
      assert.deepEqual(codes(validate(flag, { gift: 'on' })), ['note:required']);
      assert.deepEqual(codes(validate(flag, { gift: 'off' })), []);
      assert.deepEqual(codes(validate(flag, {})), []);
    });

    test('requiredIf counts defaults as present, atLeastOne counts false and 0', () => {
      const schema = {
        mode: { type: 'string', default: 'fast' },
        speed: { type: 'number', default: 0 },
        $rules: [{ type: 'requiredIf', field: 'speed', when: { field: 'mode', equals: 'fast' } }],
      };
      assert.deepEqual(codes(validate(schema, {})), []);
      const any = { a: { type: 'number' }, b: { type: 'boolean' }, $rules: [{ type: 'atLeastOne', fields: ['a', 'b'] }] };
      assert.deepEqual(codes(validate(any, { a: 0 })), []);
      assert.deepEqual(codes(validate(any, { b: 'off' })), []);
    });

    test('atLeastOne reports at the object path', () => {
      const schema = {
        email: { type: 'string' },
        phone: { type: 'string' },
        $rules: [{ type: 'atLeastOne', fields: ['email', 'phone'] }],
      };
      assert.deepEqual(validate(schema, {}).errors, [{ path: '', code: 'atLeastOne' }]);
      assert.deepEqual(codes(validate(schema, { email: ' ' })), [':atLeastOne']);
      assert.deepEqual(codes(validate(schema, { phone: '1' })), []);
      const nested = { contact: { type: 'object', fields: schema } };
      assert.deepEqual(validate(nested, { contact: {} }).errors, [{ path: 'contact', code: 'atLeastOne' }]);
    });

    test('nested $rules use nested paths and run after the fields', () => {
      const schema = {
        acct: {
          type: 'object',
          fields: {
            pin: { type: 'string', required: true },
            pin2: { type: 'string' },
            $rules: [{ type: 'sameAs', field: 'pin2', other: 'pin' }],
          },
        },
        last: { type: 'string', required: true },
      };
      const r = validate(schema, { acct: { pin: '1', pin2: '2' } });
      assert.deepEqual(codes(r), ['acct.pin2:sameAs', 'last:required']);
    });

    test('rules run in array order and see cleaned values', () => {
      const schema = {
        a: { type: 'string' },
        b: { type: 'string' },
        $rules: [
          { type: 'atLeastOne', fields: ['a', 'b'] },
          { type: 'requiredIf', field: 'b', when: { field: 'a', equals: 'x' } },
          { type: 'sameAs', field: 'b', other: 'a' },
        ],
      };
      assert.deepEqual(codes(validate(schema, {})), [':atLeastOne']);
      assert.deepEqual(codes(validate(schema, { a: ' x ' })), ['b:required']);
      assert.deepEqual(codes(validate(schema, { a: 'x', b: 'y' })), ['b:sameAs']);
    });

    test('unknown field types are a programming error', () => {
      assert.throws(() => validate({ a: { type: 'date' } }, { a: 'x' }), TypeError);
      assert.deepEqual(validate({ a: { type: 'date' } }, {}).ok, true);
    });

    test('data is not modified', () => {
      const data = { tags: [' A '], who: { n: ' x ' } };
      const copy = JSON.stringify(data);
      validate({ tags: { type: 'array', of: { type: 'string', lower: true } }, who: { type: 'object', fields: { n: { type: 'string' } } } }, data);
      assert.equal(JSON.stringify(data), copy);
    });
''')

LIB = Lib(
    name="formcheck", lang="javascript", title="the formcheck validator",
    blurb="The signup and checkout forms of the web app are validated by formcheck: a schema and the raw submission in, errors with paths and cleaned values out.",
    files={"package.json": PACKAGE_JSON % "formcheck", "src/path.js": PATH, "src/rules.js": RULES, "src/validate.js": VALIDATE,
           "README.md": README, ".gitignore": "node_modules/\n"},
    visible_tests={"test/basic.test.js": VISIBLE},
    hidden_tests={"test/full.test.js": HIDDEN},
    mutate=["src/validate.js", "src/rules.js", "src/path.js"], difficulty=2, tags=["validation", "forms"],
    verify=JS_VERIFY,
    probe_import="const { validate } = require('./src/validate');\nconst { join } = require('./src/path');\nconst { isMissing, checkString, checkNumber, checkBoolean } = require('./src/rules');",
    probes=[
        "join('items[0]', 'sku')",
        "join('a', 0)",
        "isMissing('   ')",
        'isMissing(0)',
        "checkString({ minLen: 3 }, ' ab ')",
        "checkString({ maxLen: 3 }, ' abc ')",
        "checkString({ oneOf: ['red', 'blue'], lower: true }, ' RED ')",
        'checkNumber({ min: 1 }, 1)',
        'checkNumber({ max: 10 }, 11)',
        "checkNumber({}, ' -3.5 ')",
        "checkNumber({}, '1e3')",
        'checkNumber({ integer: true }, 2.5)',
        "checkBoolean(' ON ')",
        "checkBoolean('yes')",
        "validate({ a: { type: 'string', required: true }, b: { type: 'number', required: true } }, { a: '  ', b: null }).errors",
        "validate({ role: { type: 'string', default: 'guest' }, n: { type: 'number', default: 0 } }, { role: ' ' }).value",
        "validate({ xs: { type: 'array', of: { type: 'number' }, minItems: 2, maxItems: 3 } }, { xs: [1] }).errors.map((e) => e.path + ':' + e.code)",
        "validate({ xs: { type: 'array', of: { type: 'number' }, minItems: 2, maxItems: 3 } }, { xs: [1, 2, 3, 4] }).errors.map((e) => e.path + ':' + e.code)",
        "validate({ xs: { type: 'array', unique: true, of: { type: 'string' } } }, { xs: ['a', ' a '] }).errors.map((e) => e.path + ':' + e.code)",
        "validate({ tags: { type: 'array', of: { type: 'string', minLen: 2 } } }, { tags: ['ok', 'x', 4, '  '] }).errors.map((e) => e.path + ':' + e.code)",
        "validate({ name: { type: 'string', required: true }, address: { type: 'object', fields: { street: { type: 'string', required: true } } } }, { name: '', address: {} }).errors.map((e) => e.path + ':' + e.code)",
        "validate({ a: { type: 'string', required: true } }, { a: '', b: 1 }, { strict: true }).errors.map((e) => e.path + ':' + e.code)",
        "validate({ p: { type: 'string' }, c: { type: 'string' }, $rules: [{ type: 'sameAs', field: 'c', other: 'p' }] }, { p: 'secret', c: 'secreT' }).errors.map((e) => e.path + ':' + e.code)",
        "validate({ country: { type: 'string' }, state: { type: 'string' }, $rules: [{ type: 'requiredIf', field: 'state', when: { field: 'country', equals: 'US' } }] }, { country: 'US' }).errors.map((e) => e.path + ':' + e.code)",
        "validate({ email: { type: 'string' }, $rules: [{ type: 'atLeastOne', fields: ['email'] }] }, {}).errors",
        "validate({ a: { type: 'string' } }, [])",
    ],
)

register_libs([LIB], n=8)
