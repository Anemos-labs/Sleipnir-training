"""Layout-driven bit packer: parse a field layout, pack named values to hex and unpack them again (invented wire format)."""
from __future__ import annotations

from fx import family

from generators.greenfield import _kit as K

PY = r'''
ORDER = "@ORDER@"
MAXW = @MAXW@
MAXBITS = @MAXBITS@
SIGNED = @SIGNED@
ENUM = @ENUM@
FIXED = @FIXED@
SUMS = @SUMS@
ARRAYS = @ARRAYS@
VPACK = "@VPACK@"
VUNPACK = "@VUNPACK@"
UPPER = @UPPER@

LOW = "abcdefghijklmnopqrstuvwxyz"
DIG = "0123456789"
HEX = "0123456789abcdefABCDEF"


class Field:
    def __init__(self, name, width, kind="u", scale=0, count=1, names=None):
        self.name, self.width, self.kind, self.scale, self.count, self.names = name, width, kind, scale, count, names or []


def good_name(s, extra=""):
    return 1 <= len(s) <= 8 and s[0] in LOW and all(c in LOW + DIG + extra for c in s)


def parse_field(tok):
    name, colon, spec = tok.partition(":")
    if not colon:
        return None
    pad = ARRAYS and name == "_"
    if not pad and not good_name(name, "_"):
        return None
    i = 0
    while i < len(spec) and spec[i] in DIG:
        i += 1
    wt, rest = spec[:i], spec[i:]
    if not wt or wt[0] == "0" or len(wt) > 2 or int(wt) > MAXW:
        return None
    w = int(wt)
    if pad:
        return Field("_", w, "pad") if rest == "" else None
    if rest == "":
        return None
    k, rest = rest[0], rest[1:]
    if k == "u" or (k == "i" and SIGNED):
        scale, count = 0, 1
        if FIXED and rest[:1] == ".":
            if len(rest) < 2 or rest[1] not in "123":
                return None
            scale, rest = int(rest[1]), rest[2:]
        if ARRAYS and rest[:1] == "*":
            if scale or rest[1:] not in ("2", "3", "4", "5", "6", "7", "8"):
                return None
            count, rest = int(rest[1:]), ""
        if rest != "":
            return None
        return Field(name, w, k, scale, count)
    if k == "e" and ENUM:
        if not (rest.startswith("(") and rest.endswith(")")):
            return None
        names = rest[1:-1].split("|")
        if len(names) > min(16, 1 << w) or len(set(names)) != len(names) or not all(good_name(n) and "_" not in n for n in names):
            return None
        return Field(name, w, "e", 0, 1, names)
    return None


def parse_layout(layout):
    toks = layout.split(" ")
    trailer = ""
    if SUMS and toks[-1] in ("#xor", "#sum"):
        trailer = toks.pop()[1:]
    fields = []
    for t in toks:
        f = parse_field(t)
        if f is None:
            return None
        fields.append(f)
    named = [f.name for f in fields if f.kind != "pad"]
    if not named or len(set(named)) != len(named):
        return None
    if sum(f.width * f.count for f in fields) > MAXBITS:
        return None
    return fields, trailer


def int_text(d):
    return d != "" and all(c in DIG for c in d) and (len(d) == 1 or d[0] != "0") and len(d) <= 9


def parse_value(s, f):
    """integer raw value (scaled for fixed point) or None"""
    neg = s.startswith("-")
    body = s[1:] if neg else s
    if neg and f.kind == "u":
        return None
    ip, dot, fp = body.partition(".")
    if dot and (f.scale == 0 or not (1 <= len(fp) <= f.scale and all(c in DIG for c in fp))):
        return None
    if not int_text(ip):
        return None
    raw = int(ip) * 10 ** f.scale + (int(fp.ljust(f.scale, "0")) if dot else 0)
    if neg:
        if raw == 0:
            return None
        raw = -raw
    lo, hi = (0, (1 << f.width) - 1) if f.kind == "u" else (-(1 << (f.width - 1)), (1 << (f.width - 1)) - 1)
    return raw if lo <= raw <= hi else None


def parse_elem(s, f):
    if f.kind == "e":
        return f.names.index(s) if s in f.names else None
    return parse_value(s, f)


def emit_bits(bits, x, w):
    rng = range(w - 1, -1, -1) if ORDER == "msb" else range(w)
    for b in rng:
        bits.append((x >> b) & 1)


def to_bytes(bits):
    out = []
    for k in range(0, len(bits), 8):
        v = 0
        for j in range(8):
            bit = bits[k + j] if k + j < len(bits) else 0
            v |= bit << (7 - j if ORDER == "msb" else j)
        out.append(v)
    return out


def from_bytes(bs, nbits):
    bits = []
    for k in range(len(bs) * 8):
        b = bs[k // 8]
        bits.append((b >> (7 - k % 8 if ORDER == "msb" else k % 8)) & 1)
    return bits


def fmt_elem(v, f):
    if f.kind == "e":
        return None if v >= len(f.names) else f.names[v]
    if f.scale:
        s = str(abs(v) // 10 ** f.scale) + "." + str(abs(v) % 10 ** f.scale).rjust(f.scale, "0")
        return ("-" if v < 0 else "") + s
    return str(v)


def wire(layout, request):
    lay = parse_layout(layout)
    if lay is None:
        return "error: layout"
    fields, trailer = lay
    words = request.split(" ")
    if words[0] == VPACK:
        return do_pack(fields, trailer, words[1:])
    if words[0] == VUNPACK:
        return do_unpack(fields, trailer, words[1:])
    return "error: request"


def do_pack(fields, trailer, words):
    pairs = []
    for wd in words:
        n, eq, v = wd.partition("=")
        if not eq or n == "" or v == "" or "=" in v:
            return "error: request"
        pairs.append((n, v))
    names = [f.name for f in fields if f.kind != "pad"]
    given = {}
    for n, v in pairs:
        if n not in names:
            return "error: unknown " + n
        if n in given:
            return "error: duplicate " + n
        given[n] = v
    for n in names:
        if n not in given:
            return "error: missing " + n
    bits = []
    for f in fields:
        if f.kind == "pad":
            bits.extend([0] * f.width)
            continue
        items = given[f.name].split(",") if f.count > 1 else [given[f.name]]
        if len(items) != f.count:
            return "error: value " + f.name
        vals = [parse_elem(s, f) for s in items]
        if None in vals:
            return "error: value " + f.name
        for v in vals:
            emit_bits(bits, v & ((1 << f.width) - 1), f.width)
    bs = to_bytes(bits)
    if trailer == "xor":
        c = 0
        for b in bs:
            c ^= b
        bs.append(c)
    elif trailer == "sum":
        bs.append(sum(bs) % 256)
    h = "".join("%02x" % b for b in bs)
    return h.upper() if UPPER else h


def do_unpack(fields, trailer, words):
    if len(words) != 1:
        return "error: request"
    h = words[0]
    if not h or not all(c in HEX for c in h):
        return "error: hex"
    total = sum(f.width * f.count for f in fields)
    nbytes = (total + 7) // 8 + (1 if trailer else 0)
    if len(h) != 2 * nbytes:
        return "error: length"
    bs = [int(h[i:i + 2], 16) for i in range(0, len(h), 2)]
    if trailer:
        body, last = bs[:-1], bs[-1]
        c = 0
        if trailer == "xor":
            for b in body:
                c ^= b
        else:
            c = sum(body) % 256
        if c != last:
            return "error: checksum"
        bs = body
    bits = from_bytes(bs, total)
    pos = 0
    out = []
    pad_ok = True
    decoded = []
    for f in fields:
        vals = []
        for _ in range(f.count):
            chunk = bits[pos:pos + f.width]
            pos += f.width
            x = 0
            if ORDER == "msb":
                for b in chunk:
                    x = (x << 1) | b
            else:
                for j, b in enumerate(chunk):
                    x |= b << j
            vals.append(x)
        if f.kind == "pad":
            if any(vals):
                pad_ok = False
        decoded.append(vals)
    if any(bits[pos:]):
        pad_ok = False
    if not pad_ok:
        return "error: padding"
    for f, vals in zip(fields, decoded):
        if f.kind == "pad":
            continue
        texts = []
        for x in vals:
            if f.kind == "i" and x >= 1 << (f.width - 1):
                x -= 1 << f.width
            t = fmt_elem(x, f)
            if t is None:
                return "error: enum " + f.name
            texts.append(t)
        out.append(f.name + "=" + ",".join(texts))
    return " ".join(out)
'''

JS = r'''
'use strict';
const ORDER = '@ORDER@';
const MAXW = @MAXW@;
const MAXBITS = @MAXBITS@;
const SIGNED = @SIGNED@;
const ENUM = @ENUM@;
const FIXED = @FIXED@;
const SUMS = @SUMS@;
const ARRAYS = @ARRAYS@;
const VPACK = '@VPACK@';
const VUNPACK = '@VUNPACK@';
const UPPER = @UPPER@;

const LOW = 'abcdefghijklmnopqrstuvwxyz';
const DIG = '0123456789';
const HEX = '0123456789abcdefABCDEF';

function allIn(s, set) {
  for (const c of s) if (!set.includes(c)) return false;
  return true;
}

function goodName(s, extra) {
  return s.length >= 1 && s.length <= 8 && LOW.includes(s[0]) && allIn(s, LOW + DIG + extra);
}

function parseField(tok) {
  const ci = tok.indexOf(':');
  if (ci < 0) return null;
  const name = tok.slice(0, ci);
  const spec = tok.slice(ci + 1);
  const pad = ARRAYS && name === '_';
  if (!pad && !goodName(name, '_')) return null;
  let i = 0;
  while (i < spec.length && DIG.includes(spec[i])) i++;
  const wt = spec.slice(0, i);
  let rest = spec.slice(i);
  if (wt === '' || wt[0] === '0' || wt.length > 2 || parseInt(wt, 10) > MAXW) return null;
  const width = parseInt(wt, 10);
  if (pad) return rest === '' ? { name: '_', width, kind: 'pad', scale: 0, count: 1, names: [] } : null;
  if (rest === '') return null;
  const k = rest[0];
  rest = rest.slice(1);
  if (k === 'u' || (k === 'i' && SIGNED)) {
    let scale = 0;
    let count = 1;
    if (FIXED && rest.startsWith('.')) {
      if (rest.length < 2 || !'123'.includes(rest[1])) return null;
      scale = parseInt(rest[1], 10);
      rest = rest.slice(2);
    }
    if (ARRAYS && rest.startsWith('*')) {
      const c = rest.slice(1);
      if (scale || !['2', '3', '4', '5', '6', '7', '8'].includes(c)) return null;
      count = parseInt(c, 10);
      rest = '';
    }
    if (rest !== '') return null;
    return { name, width, kind: k, scale, count, names: [] };
  }
  if (k === 'e' && ENUM) {
    if (!(rest.startsWith('(') && rest.endsWith(')'))) return null;
    const names = rest.slice(1, -1).split('|');
    if (names.length > Math.min(16, 2 ** width) || new Set(names).size !== names.length) return null;
    for (const n of names) if (!goodName(n, '') ) return null;
    return { name, width, kind: 'e', scale: 0, count: 1, names };
  }
  return null;
}

function parseLayout(layout) {
  const toks = layout.split(' ');
  let trailer = '';
  if (SUMS && (toks[toks.length - 1] === '#xor' || toks[toks.length - 1] === '#sum')) trailer = toks.pop().slice(1);
  const fields = [];
  for (const t of toks) {
    const f = parseField(t);
    if (f === null) return null;
    fields.push(f);
  }
  const named = fields.filter((f) => f.kind !== 'pad').map((f) => f.name);
  if (named.length === 0 || new Set(named).size !== named.length) return null;
  let total = 0;
  for (const f of fields) total += f.width * f.count;
  if (total > MAXBITS) return null;
  return { fields, trailer, total };
}

function intText(d) {
  return d !== '' && allIn(d, DIG) && (d.length === 1 || d[0] !== '0') && d.length <= 9;
}

function parseValue(s, f) {
  const neg = s.startsWith('-');
  const body = neg ? s.slice(1) : s;
  if (neg && f.kind === 'u') return null;
  const di = body.indexOf('.');
  const ip = di < 0 ? body : body.slice(0, di);
  const fp = di < 0 ? '' : body.slice(di + 1);
  if (di >= 0 && (f.scale === 0 || fp.length < 1 || fp.length > f.scale || !allIn(fp, DIG))) return null;
  if (!intText(ip)) return null;
  let raw = parseInt(ip, 10) * 10 ** f.scale + (di >= 0 ? parseInt(fp.padEnd(f.scale, '0'), 10) : 0);
  if (neg) {
    if (raw === 0) return null;
    raw = -raw;
  }
  let lo = 0;
  let hi = 2 ** f.width - 1;
  if (f.kind === 'i') {
    lo = -(2 ** (f.width - 1));
    hi = 2 ** (f.width - 1) - 1;
  }
  return raw >= lo && raw <= hi ? raw : null;
}

function parseElem(s, f) {
  if (f.kind === 'e') {
    const ix = f.names.indexOf(s);
    return ix < 0 ? null : ix;
  }
  return parseValue(s, f);
}

function emitBits(bits, x, w) {
  if (ORDER === 'msb') for (let b = w - 1; b >= 0; b--) bits.push(Math.floor(x / 2 ** b) % 2);
  else for (let b = 0; b < w; b++) bits.push(Math.floor(x / 2 ** b) % 2);
}

function toBytes(bits) {
  const out = [];
  for (let k = 0; k < bits.length; k += 8) {
    let v = 0;
    for (let j = 0; j < 8; j++) {
      const bit = k + j < bits.length ? bits[k + j] : 0;
      v |= bit << (ORDER === 'msb' ? 7 - j : j);
    }
    out.push(v);
  }
  return out;
}

function fmtElem(v, f) {
  if (f.kind === 'e') return v >= f.names.length ? null : f.names[v];
  if (f.scale) {
    const p = 10 ** f.scale;
    const a = Math.abs(v);
    return (v < 0 ? '-' : '') + String(Math.floor(a / p)) + '.' + String(a % p).padStart(f.scale, '0');
  }
  return String(v);
}

function hex2(b) {
  const h = b.toString(16).padStart(2, '0');
  return UPPER ? h.toUpperCase() : h;
}

function doPack(lay, words) {
  const pairs = [];
  for (const wd of words) {
    const ei = wd.indexOf('=');
    if (ei < 0) return 'error: request';
    const n = wd.slice(0, ei);
    const v = wd.slice(ei + 1);
    if (n === '' || v === '' || v.includes('=')) return 'error: request';
    pairs.push([n, v]);
  }
  const names = lay.fields.filter((f) => f.kind !== 'pad').map((f) => f.name);
  const given = new Map();
  for (const [n, v] of pairs) {
    if (!names.includes(n)) return 'error: unknown ' + n;
    if (given.has(n)) return 'error: duplicate ' + n;
    given.set(n, v);
  }
  for (const n of names) if (!given.has(n)) return 'error: missing ' + n;
  const bits = [];
  for (const f of lay.fields) {
    if (f.kind === 'pad') {
      for (let i = 0; i < f.width; i++) bits.push(0);
      continue;
    }
    const items = f.count > 1 ? given.get(f.name).split(',') : [given.get(f.name)];
    if (items.length !== f.count) return 'error: value ' + f.name;
    const vals = items.map((s) => parseElem(s, f));
    if (vals.includes(null)) return 'error: value ' + f.name;
    for (const v of vals) emitBits(bits, v < 0 ? v + 2 ** f.width : v, f.width);
  }
  const bs = toBytes(bits);
  if (lay.trailer === 'xor') bs.push(bs.reduce((a, b) => a ^ b, 0));
  else if (lay.trailer === 'sum') bs.push(bs.reduce((a, b) => a + b, 0) % 256);
  return bs.map(hex2).join('');
}

function doUnpack(lay, words) {
  if (words.length !== 1) return 'error: request';
  const h = words[0];
  if (h === '' || !allIn(h, HEX)) return 'error: hex';
  const nbytes = Math.floor((lay.total + 7) / 8) + (lay.trailer ? 1 : 0);
  if (h.length !== 2 * nbytes) return 'error: length';
  let bs = [];
  for (let i = 0; i < h.length; i += 2) bs.push(parseInt(h.slice(i, i + 2), 16));
  if (lay.trailer) {
    const body = bs.slice(0, -1);
    const last = bs[bs.length - 1];
    const c = lay.trailer === 'xor' ? body.reduce((a, b) => a ^ b, 0) : body.reduce((a, b) => a + b, 0) % 256;
    if (c !== last) return 'error: checksum';
    bs = body;
  }
  const bits = [];
  for (let k = 0; k < bs.length * 8; k++) bits.push((bs[Math.floor(k / 8)] >> (ORDER === 'msb' ? 7 - (k % 8) : k % 8)) & 1);
  let pos = 0;
  let padOk = true;
  const decoded = [];
  for (const f of lay.fields) {
    const vals = [];
    for (let c = 0; c < f.count; c++) {
      let x = 0;
      for (let j = 0; j < f.width; j++) {
        const b = bits[pos + j];
        if (ORDER === 'msb') x = x * 2 + b;
        else x += b * 2 ** j;
      }
      pos += f.width;
      vals.push(x);
    }
    if (f.kind === 'pad' && vals.some((x) => x !== 0)) padOk = false;
    decoded.push(vals);
  }
  for (let k = pos; k < bits.length; k++) if (bits[k]) padOk = false;
  if (!padOk) return 'error: padding';
  const out = [];
  for (let i = 0; i < lay.fields.length; i++) {
    const f = lay.fields[i];
    if (f.kind === 'pad') continue;
    const texts = [];
    for (let x of decoded[i]) {
      if (f.kind === 'i' && x >= 2 ** (f.width - 1)) x -= 2 ** f.width;
      const t = fmtElem(x, f);
      if (t === null) return 'error: enum ' + f.name;
      texts.push(t);
    }
    out.push(f.name + '=' + texts.join(','));
  }
  return out.join(' ');
}

function wire(layout, request) {
  const lay = parseLayout(layout);
  if (lay === null) return 'error: layout';
  const words = request.split(' ');
  if (words[0] === VPACK) return doPack(lay, words.slice(1));
  if (words[0] === VUNPACK) return doUnpack(lay, words.slice(1));
  return 'error: request';
}

module.exports = { wire };
'''

JV = r'''
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class Bitwire {
    static final boolean MSB = "@ORDER@".equals("msb");
    static final int MAXW = @MAXW@;
    static final int MAXBITS = @MAXBITS@;
    static final boolean SIGNED = @SIGNED@;
    static final boolean ENUM = @ENUM@;
    static final boolean FIXED = @FIXED@;
    static final boolean SUMS = @SUMS@;
    static final boolean ARRAYS = @ARRAYS@;
    static final String VPACK = "@VPACK@";
    static final String VUNPACK = "@VUNPACK@";
    static final boolean UPPER = @UPPER@;

    static final String LOW = "abcdefghijklmnopqrstuvwxyz";
    static final String DIG = "0123456789";
    static final String HEX = "0123456789abcdefABCDEF";

    static class Field {
        String name;
        int width;
        char kind;
        int scale;
        int count = 1;
        List<String> names = new ArrayList<>();
    }

    static class Layout {
        List<Field> fields = new ArrayList<>();
        String trailer = "";
        int total;
    }

    static boolean allIn(String s, String set) {
        for (int i = 0; i < s.length(); i++) if (set.indexOf(s.charAt(i)) < 0) return false;
        return true;
    }

    static boolean goodName(String s, String extra) {
        return s.length() >= 1 && s.length() <= 8 && LOW.indexOf(s.charAt(0)) >= 0 && allIn(s, LOW + DIG + extra);
    }

    static Field parseField(String tok) {
        int ci = tok.indexOf(':');
        if (ci < 0) return null;
        String name = tok.substring(0, ci);
        String spec = tok.substring(ci + 1);
        boolean pad = ARRAYS && name.equals("_");
        if (!pad && !goodName(name, "_")) return null;
        int i = 0;
        while (i < spec.length() && DIG.indexOf(spec.charAt(i)) >= 0) i++;
        String wt = spec.substring(0, i);
        String rest = spec.substring(i);
        if (wt.isEmpty() || wt.charAt(0) == '0' || wt.length() > 2 || Integer.parseInt(wt) > MAXW) return null;
        Field f = new Field();
        f.name = name;
        f.width = Integer.parseInt(wt);
        if (pad) {
            if (!rest.isEmpty()) return null;
            f.name = "_";
            f.kind = 'p';
            return f;
        }
        if (rest.isEmpty()) return null;
        char k = rest.charAt(0);
        rest = rest.substring(1);
        if (k == 'u' || (k == 'i' && SIGNED)) {
            f.kind = k;
            if (FIXED && rest.startsWith(".")) {
                if (rest.length() < 2 || "123".indexOf(rest.charAt(1)) < 0) return null;
                f.scale = rest.charAt(1) - '0';
                rest = rest.substring(2);
            }
            if (ARRAYS && rest.startsWith("*")) {
                String c = rest.substring(1);
                if (f.scale != 0 || !(c.length() == 1 && c.charAt(0) >= '2' && c.charAt(0) <= '8')) return null;
                f.count = c.charAt(0) - '0';
                rest = "";
            }
            return rest.isEmpty() ? f : null;
        }
        if (k == 'e' && ENUM) {
            if (!(rest.startsWith("(") && rest.endsWith(")"))) return null;
            String[] names = rest.substring(1, rest.length() - 1).split("\\|", -1);
            Set<String> seen = new HashSet<>();
            for (String n : names) {
                if (!goodName(n, "")) return null;
                seen.add(n);
                f.names.add(n);
            }
            if (names.length > Math.min(16, 1 << f.width) || seen.size() != names.length) return null;
            f.kind = 'e';
            return f;
        }
        return null;
    }

    static Layout parseLayout(String layout) {
        String[] toks = layout.split(" ", -1);
        int n = toks.length;
        Layout lay = new Layout();
        if (SUMS && (toks[n - 1].equals("#xor") || toks[n - 1].equals("#sum"))) {
            lay.trailer = toks[n - 1].substring(1);
            n--;
        }
        Set<String> seen = new HashSet<>();
        int named = 0;
        for (int i = 0; i < n; i++) {
            Field f = parseField(toks[i]);
            if (f == null) return null;
            if (f.kind != 'p') {
                named++;
                if (!seen.add(f.name)) return null;
            }
            lay.total += f.width * f.count;
            lay.fields.add(f);
        }
        if (named == 0 || lay.total > MAXBITS) return null;
        return lay;
    }

    static boolean intText(String d) {
        return !d.isEmpty() && allIn(d, DIG) && (d.length() == 1 || d.charAt(0) != '0') && d.length() <= 9;
    }

    static long pow10(int n) {
        long p = 1;
        for (int i = 0; i < n; i++) p *= 10;
        return p;
    }

    /** raw value or Long.MIN_VALUE when invalid */
    static long parseValue(String s, Field f) {
        final long BAD = Long.MIN_VALUE;
        boolean neg = s.startsWith("-");
        String body = neg ? s.substring(1) : s;
        if (neg && f.kind == 'u') return BAD;
        int di = body.indexOf('.');
        String ip = di < 0 ? body : body.substring(0, di);
        String fp = di < 0 ? "" : body.substring(di + 1);
        if (di >= 0 && (f.scale == 0 || fp.length() < 1 || fp.length() > f.scale || !allIn(fp, DIG))) return BAD;
        if (!intText(ip)) return BAD;
        long raw = Long.parseLong(ip) * pow10(f.scale);
        if (di >= 0) {
            StringBuilder sb = new StringBuilder(fp);
            while (sb.length() < f.scale) sb.append('0');
            raw += Long.parseLong(sb.toString());
        }
        if (neg) {
            if (raw == 0) return BAD;
            raw = -raw;
        }
        long lo = 0, hi = (1L << f.width) - 1;
        if (f.kind == 'i') {
            lo = -(1L << (f.width - 1));
            hi = (1L << (f.width - 1)) - 1;
        }
        return raw >= lo && raw <= hi ? raw : BAD;
    }

    static long parseElem(String s, Field f) {
        if (f.kind == 'e') {
            int ix = f.names.indexOf(s);
            return ix < 0 ? Long.MIN_VALUE : ix;
        }
        return parseValue(s, f);
    }

    static void emitBits(List<Integer> bits, long x, int w) {
        if (MSB) for (int b = w - 1; b >= 0; b--) bits.add((int) ((x >> b) & 1));
        else for (int b = 0; b < w; b++) bits.add((int) ((x >> b) & 1));
    }

    static String fmtElem(long v, Field f) {
        if (f.kind == 'e') return v >= f.names.size() ? null : f.names.get((int) v);
        if (f.scale > 0) {
            long p = pow10(f.scale);
            long a = Math.abs(v);
            String frac = Long.toString(a % p);
            while (frac.length() < f.scale) frac = "0" + frac;
            return (v < 0 ? "-" : "") + (a / p) + "." + frac;
        }
        return Long.toString(v);
    }

    static String hex2(int b) {
        String h = String.format("%02x", b);
        return UPPER ? h.toUpperCase() : h;
    }

    static String doPack(Layout lay, String[] words) {
        List<String[]> pairs = new ArrayList<>();
        for (String wd : words) {
            int ei = wd.indexOf('=');
            if (ei < 0) return "error: request";
            String n = wd.substring(0, ei);
            String v = wd.substring(ei + 1);
            if (n.isEmpty() || v.isEmpty() || v.indexOf('=') >= 0) return "error: request";
            pairs.add(new String[] { n, v });
        }
        List<String> names = new ArrayList<>();
        for (Field f : lay.fields) if (f.kind != 'p') names.add(f.name);
        java.util.Map<String, String> given = new java.util.HashMap<>();
        for (String[] p : pairs) {
            if (!names.contains(p[0])) return "error: unknown " + p[0];
            if (given.containsKey(p[0])) return "error: duplicate " + p[0];
            given.put(p[0], p[1]);
        }
        for (String n : names) if (!given.containsKey(n)) return "error: missing " + n;
        List<Integer> bits = new ArrayList<>();
        for (Field f : lay.fields) {
            if (f.kind == 'p') {
                for (int i = 0; i < f.width; i++) bits.add(0);
                continue;
            }
            String[] items = f.count > 1 ? given.get(f.name).split(",", -1) : new String[] { given.get(f.name) };
            if (items.length != f.count) return "error: value " + f.name;
            long[] vals = new long[items.length];
            for (int i = 0; i < items.length; i++) {
                vals[i] = parseElem(items[i], f);
                if (vals[i] == Long.MIN_VALUE) return "error: value " + f.name;
            }
            for (long v : vals) emitBits(bits, v & ((1L << f.width) - 1), f.width);
        }
        List<Integer> bs = new ArrayList<>();
        for (int k = 0; k < bits.size(); k += 8) {
            int v = 0;
            for (int j = 0; j < 8; j++) {
                int bit = k + j < bits.size() ? bits.get(k + j) : 0;
                v |= bit << (MSB ? 7 - j : j);
            }
            bs.add(v);
        }
        if (lay.trailer.equals("xor")) {
            int c = 0;
            for (int b : bs) c ^= b;
            bs.add(c);
        } else if (lay.trailer.equals("sum")) {
            int c = 0;
            for (int b : bs) c += b;
            bs.add(c % 256);
        }
        StringBuilder sb = new StringBuilder();
        for (int b : bs) sb.append(hex2(b));
        return sb.toString();
    }

    static String doUnpack(Layout lay, String[] words) {
        if (words.length != 1) return "error: request";
        String h = words[0];
        if (h.isEmpty() || !allIn(h, HEX)) return "error: hex";
        int nbytes = (lay.total + 7) / 8 + (lay.trailer.isEmpty() ? 0 : 1);
        if (h.length() != 2 * nbytes) return "error: length";
        int[] bs = new int[nbytes];
        for (int i = 0; i < nbytes; i++) bs[i] = Integer.parseInt(h.substring(2 * i, 2 * i + 2), 16);
        int blen = nbytes;
        if (!lay.trailer.isEmpty()) {
            int c = 0;
            for (int i = 0; i < nbytes - 1; i++) c = lay.trailer.equals("xor") ? c ^ bs[i] : c + bs[i];
            if (lay.trailer.equals("sum")) c %= 256;
            if (c != bs[nbytes - 1]) return "error: checksum";
            blen = nbytes - 1;
        }
        int[] bits = new int[blen * 8];
        for (int k = 0; k < bits.length; k++) bits[k] = (bs[k / 8] >> (MSB ? 7 - (k % 8) : k % 8)) & 1;
        int pos = 0;
        boolean padOk = true;
        long[][] decoded = new long[lay.fields.size()][];
        for (int fi = 0; fi < lay.fields.size(); fi++) {
            Field f = lay.fields.get(fi);
            long[] vals = new long[f.count];
            for (int c = 0; c < f.count; c++) {
                long x = 0;
                for (int j = 0; j < f.width; j++) {
                    int b = bits[pos + j];
                    if (MSB) x = x * 2 + b;
                    else x |= (long) b << j;
                }
                pos += f.width;
                vals[c] = x;
                if (f.kind == 'p' && x != 0) padOk = false;
            }
            decoded[fi] = vals;
        }
        for (int k = pos; k < bits.length; k++) if (bits[k] != 0) padOk = false;
        if (!padOk) return "error: padding";
        StringBuilder out = new StringBuilder();
        for (int fi = 0; fi < lay.fields.size(); fi++) {
            Field f = lay.fields.get(fi);
            if (f.kind == 'p') continue;
            StringBuilder t = new StringBuilder();
            for (int c = 0; c < f.count; c++) {
                long x = decoded[fi][c];
                if (f.kind == 'i' && x >= (1L << (f.width - 1))) x -= 1L << f.width;
                String s = fmtElem(x, f);
                if (s == null) return "error: enum " + f.name;
                if (c > 0) t.append(',');
                t.append(s);
            }
            if (out.length() > 0) out.append(' ');
            out.append(f.name).append('=').append(t);
        }
        return out.toString();
    }

    public static String wire(String layout, String request) {
        Layout lay = parseLayout(layout);
        if (lay == null) return "error: layout";
        String[] words = request.split(" ", -1);
        String[] rest = java.util.Arrays.copyOfRange(words, 1, words.length);
        if (words[0].equals(VPACK)) return doPack(lay, rest);
        if (words[0].equals(VUNPACK)) return doUnpack(lay, rest);
        return "error: request";
    }
}
'''

CC = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "bitwire.h"

#define MSB @MSB@
#define MAXW @MAXW@
#define MAXBITS @MAXBITS@
#define SIGNED @SIGNED@
#define ENUM @ENUM@
#define FIXED @FIXED@
#define SUMS @SUMS@
#define ARRAYS @ARRAYS@
#define VPACK "@VPACK@"
#define VUNPACK "@VUNPACK@"
#define UPPER @UPPER@

#define MAXF 70
#define BAD (-4611686018427387904LL)

typedef struct {
    char name[16];
    int width;
    char kind; /* 'u' 'i' 'e' 'p' */
    int scale;
    int count;
    int nn;
    char en[16][16];
} Field;

typedef struct {
    Field f[MAXF];
    int n;
    char trailer; /* 0, 'x' or 's' */
    int total;
} Layout;

static char *dupstr(const char *s) {
    char *r = malloc(strlen(s) + 1);
    strcpy(r, s);
    return r;
}

static char *fail2(const char *a, const char *b) {
    char *r = malloc(strlen(a) + strlen(b) + 2);
    sprintf(r, "%s%s", a, b);
    return r;
}

static int in_set(char c, const char *set) {
    return c != 0 && strchr(set, c) != NULL;
}

static int all_in(const char *s, size_t n, const char *set) {
    for (size_t i = 0; i < n; i++)
        if (!in_set(s[i], set)) return 0;
    return 1;
}

static int good_name(const char *s, size_t n, int under) {
    if (n < 1 || n > 8 || !in_set(s[0], "abcdefghijklmnopqrstuvwxyz")) return 0;
    return all_in(s, n, under ? "abcdefghijklmnopqrstuvwxyz0123456789_" : "abcdefghijklmnopqrstuvwxyz0123456789");
}

static int parse_field(const char *tok, Field *f) {
    const char *colon = strchr(tok, ':');
    if (!colon) return 0;
    size_t nl = (size_t)(colon - tok);
    int pad = ARRAYS && nl == 1 && tok[0] == '_';
    if (!pad && !good_name(tok, nl, 1)) return 0;
    const char *p = colon + 1, *q = p;
    while (*q >= '0' && *q <= '9') q++;
    size_t wl = (size_t)(q - p);
    if (wl == 0 || p[0] == '0' || wl > 2) return 0;
    int w = atoi(p);
    if (w > MAXW) return 0;
    memset(f, 0, sizeof *f);
    f->width = w;
    f->count = 1;
    const char *rest = q;
    if (pad) {
        if (*rest) return 0;
        strcpy(f->name, "_");
        f->kind = 'p';
        return 1;
    }
    memcpy(f->name, tok, nl);
    f->name[nl] = 0;
    if (!*rest) return 0;
    char k = *rest++;
    if (k == 'u' || (SIGNED && k == 'i')) {
        f->kind = k;
        if (FIXED && rest[0] == '.') {
            if (!rest[1] || !strchr("123", rest[1])) return 0;
            f->scale = rest[1] - '0';
            rest += 2;
        }
        if (ARRAYS && rest[0] == '*') {
            if (f->scale || !(rest[1] >= '2' && rest[1] <= '8' && rest[2] == 0)) return 0;
            f->count = rest[1] - '0';
            rest += 2;
        }
        return *rest == 0;
    }
    if (ENUM && k == 'e') {
        size_t len = strlen(rest);
        if (len < 2 || rest[0] != '(' || rest[len - 1] != ')') return 0;
        const char *s = rest + 1, *end = rest + len - 1;
        int lim = (1 << w) < 16 ? (1 << w) : 16;
        while (1) {
            const char *e = s;
            while (e < end && *e != '|') e++;
            size_t n = (size_t)(e - s);
            if (!good_name(s, n, 0)) return 0;
            if (f->nn >= lim) return 0;
            memcpy(f->en[f->nn], s, n);
            f->en[f->nn][n] = 0;
            for (int i = 0; i < f->nn; i++)
                if (strcmp(f->en[i], f->en[f->nn]) == 0) return 0;
            f->nn++;
            if (e >= end) break;
            s = e + 1;
        }
        f->kind = 'e';
        return 1;
    }
    return 0;
}

static int parse_layout(const char *layout, Layout *L) {
    char *copy = dupstr(layout);
    char *toks[MAXF + 1];
    int nt = 0, ok = 1;
    char *p = copy;
    for (;;) {
        char *e = strchr(p, ' ');
        if (nt >= MAXF) { ok = 0; break; }
        toks[nt++] = p;
        if (!e) break;
        *e = 0;
        p = e + 1;
    }
    memset(L, 0, sizeof *L);
    if (ok && SUMS && (strcmp(toks[nt - 1], "#xor") == 0 || strcmp(toks[nt - 1], "#sum") == 0)) {
        L->trailer = toks[nt - 1][1];
        nt--;
    }
    int named = 0;
    for (int i = 0; ok && i < nt; i++) {
        if (!parse_field(toks[i], &L->f[L->n])) { ok = 0; break; }
        Field *f = &L->f[L->n];
        if (f->kind != 'p') {
            named++;
            for (int j = 0; j < L->n; j++)
                if (L->f[j].kind != 'p' && strcmp(L->f[j].name, f->name) == 0) ok = 0;
        }
        L->total += f->width * f->count;
        L->n++;
    }
    if (ok && (named == 0 || L->total > MAXBITS)) ok = 0;
    free(copy);
    return ok;
}

static int int_text(const char *d, size_t n) {
    return n >= 1 && n <= 9 && all_in(d, n, "0123456789") && (n == 1 || d[0] != '0');
}

static long long pow10ll(int n) {
    long long p = 1;
    while (n-- > 0) p *= 10;
    return p;
}

static long long parse_value(const char *s, const Field *f) {
    int neg = s[0] == '-';
    const char *body = neg ? s + 1 : s;
    if (neg && f->kind == 'u') return BAD;
    const char *dot = strchr(body, '.');
    size_t il = dot ? (size_t)(dot - body) : strlen(body);
    size_t fl = dot ? strlen(dot + 1) : 0;
    if (dot && (f->scale == 0 || fl < 1 || fl > (size_t)f->scale || !all_in(dot + 1, fl, "0123456789"))) return BAD;
    if (!int_text(body, il)) return BAD;
    long long raw = 0;
    for (size_t i = 0; i < il; i++) raw = raw * 10 + (body[i] - '0');
    raw *= pow10ll(f->scale);
    if (dot) {
        long long fr = 0;
        for (int i = 0; i < f->scale; i++) fr = fr * 10 + ((size_t)i < fl ? dot[1 + i] - '0' : 0);
        raw += fr;
    }
    if (neg) {
        if (raw == 0) return BAD;
        raw = -raw;
    }
    long long lo = 0, hi = (1LL << f->width) - 1;
    if (f->kind == 'i') {
        lo = -(1LL << (f->width - 1));
        hi = (1LL << (f->width - 1)) - 1;
    }
    return raw >= lo && raw <= hi ? raw : BAD;
}

static long long parse_elem(const char *s, const Field *f) {
    if (f->kind == 'e') {
        for (int i = 0; i < f->nn; i++)
            if (strcmp(f->en[i], s) == 0) return i;
        return BAD;
    }
    return parse_value(s, f);
}

static void emit_bits(unsigned char *bits, int *nb, long long x, int w) {
#if MSB
    for (int b = w - 1; b >= 0; b--) bits[(*nb)++] = (unsigned char)((x >> b) & 1);
#else
    for (int b = 0; b < w; b++) bits[(*nb)++] = (unsigned char)((x >> b) & 1);
#endif
}

static int split(char *s, char **out, int max) {
    int n = 0;
    for (;;) {
        char *e = strchr(s, ' ');
        if (n < max) out[n] = s;
        n++;
        if (!e) break;
        *e = 0;
        s = e + 1;
    }
    return n;
}

static char *do_pack(const Layout *L, char **w, int nw) {
    char *pn[256], *pv[256];
    if (nw > 256) return dupstr("error: request");
    for (int i = 0; i < nw; i++) {
        char *eq = strchr(w[i], '=');
        if (!eq) return dupstr("error: request");
        *eq = 0;
        pn[i] = w[i];
        pv[i] = eq + 1;
        if (!pn[i][0] || !pv[i][0] || strchr(pv[i], '=')) return dupstr("error: request");
    }
    char *given[MAXF];
    for (int i = 0; i < MAXF; i++) given[i] = NULL;
    for (int i = 0; i < nw; i++) {
        int ix = -1;
        for (int j = 0; j < L->n; j++)
            if (L->f[j].kind != 'p' && strcmp(L->f[j].name, pn[i]) == 0) ix = j;
        if (ix < 0) return fail2("error: unknown ", pn[i]);
        if (given[ix]) return fail2("error: duplicate ", pn[i]);
        given[ix] = pv[i];
    }
    for (int j = 0; j < L->n; j++)
        if (L->f[j].kind != 'p' && !given[j]) return fail2("error: missing ", L->f[j].name);
    unsigned char bits[256];
    int nb = 0;
    for (int j = 0; j < L->n; j++) {
        const Field *f = &L->f[j];
        if (f->kind == 'p') {
            for (int i = 0; i < f->width; i++) bits[nb++] = 0;
            continue;
        }
        long long vals[8];
        char *s = given[j];
        int cnt = 0;
        if (f->count > 1) {
            for (;;) {
                char *e = strchr(s, ',');
                if (cnt >= f->count) return fail2("error: value ", f->name);
                if (e) *e = 0;
                vals[cnt++] = parse_elem(s, f);
                if (!e) break;
                s = e + 1;
            }
            if (cnt != f->count) return fail2("error: value ", f->name);
        } else {
            vals[cnt++] = parse_elem(s, f);
        }
        for (int i = 0; i < cnt; i++)
            if (vals[i] == BAD) return fail2("error: value ", f->name);
        for (int i = 0; i < cnt; i++) emit_bits(bits, &nb, vals[i] & ((1LL << f->width) - 1), f->width);
    }
    int nbytes = (nb + 7) / 8;
    unsigned char bs[40];
    for (int k = 0; k < nbytes; k++) {
        int v = 0;
        for (int j = 0; j < 8; j++) {
            int bit = k * 8 + j < nb ? bits[k * 8 + j] : 0;
            v |= bit << (MSB ? 7 - j : j);
        }
        bs[k] = (unsigned char)v;
    }
    int len = nbytes;
    if (L->trailer) {
        int c = 0;
        for (int k = 0; k < nbytes; k++) c = L->trailer == 'x' ? c ^ bs[k] : c + bs[k];
        bs[len++] = (unsigned char)(c % 256);
    }
    char *out = malloc((size_t)len * 2 + 1);
    for (int k = 0; k < len; k++) sprintf(out + 2 * k, UPPER ? "%02X" : "%02x", bs[k]);
    return out;
}

static char *do_unpack(const Layout *L, char **w, int nw) {
    if (nw != 1) return dupstr("error: request");
    const char *h = w[0];
    size_t hl = strlen(h);
    if (hl == 0 || !all_in(h, hl, "0123456789abcdefABCDEF")) return dupstr("error: hex");
    int nbytes = (L->total + 7) / 8 + (L->trailer ? 1 : 0);
    if (hl != (size_t)nbytes * 2) return dupstr("error: length");
    int bs[40];
    for (int i = 0; i < nbytes; i++) {
        char t[3] = {h[2 * i], h[2 * i + 1], 0};
        bs[i] = (int)strtol(t, NULL, 16);
    }
    int blen = nbytes;
    if (L->trailer) {
        int c = 0;
        for (int i = 0; i < nbytes - 1; i++) c = L->trailer == 'x' ? c ^ bs[i] : c + bs[i];
        if (L->trailer == 's') c %= 256;
        if (c != bs[nbytes - 1]) return dupstr("error: checksum");
        blen = nbytes - 1;
    }
    int nbits = blen * 8;
    unsigned char bits[400];
    for (int k = 0; k < nbits; k++) bits[k] = (unsigned char)((bs[k / 8] >> (MSB ? 7 - (k % 8) : k % 8)) & 1);
    int pos = 0, pad_ok = 1;
    long long dec[MAXF][8];
    for (int j = 0; j < L->n; j++) {
        const Field *f = &L->f[j];
        for (int c = 0; c < f->count; c++) {
            long long x = 0;
            for (int b = 0; b < f->width; b++) {
#if MSB
                x = x * 2 + bits[pos + b];
#else
                x |= (long long)bits[pos + b] << b;
#endif
            }
            pos += f->width;
            dec[j][c] = x;
            if (f->kind == 'p' && x != 0) pad_ok = 0;
        }
    }
    for (int k = pos; k < nbits; k++)
        if (bits[k]) pad_ok = 0;
    if (!pad_ok) return dupstr("error: padding");
    char out[4096];
    out[0] = 0;
    for (int j = 0; j < L->n; j++) {
        const Field *f = &L->f[j];
        if (f->kind == 'p') continue;
        if (out[0]) strcat(out, " ");
        strcat(out, f->name);
        strcat(out, "=");
        for (int c = 0; c < f->count; c++) {
            long long x = dec[j][c];
            char t[64];
            if (f->kind == 'i' && x >= (1LL << (f->width - 1))) x -= 1LL << f->width;
            if (f->kind == 'e') {
                if (x >= f->nn) return fail2("error: enum ", f->name);
                strcpy(t, f->en[x]);
            } else if (f->scale) {
                long long p = pow10ll(f->scale), a = x < 0 ? -x : x;
                sprintf(t, "%s%lld.%0*lld", x < 0 ? "-" : "", a / p, f->scale, a % p);
            } else {
                sprintf(t, "%lld", x);
            }
            if (c) strcat(out, ",");
            strcat(out, t);
        }
    }
    return dupstr(out);
}

char *wire(const char *layout, const char *request) {
    Layout *L = malloc(sizeof *L);
    if (!parse_layout(layout, L)) {
        free(L);
        return dupstr("error: layout");
    }
    char *req = dupstr(request);
    char *words[300];
    int nw = split(req, words, 300);
    char *res;
    if (nw > 299) res = dupstr("error: request");
    else if (strcmp(words[0], VPACK) == 0) res = do_pack(L, words + 1, nw - 1);
    else if (strcmp(words[0], VUNPACK) == 0) res = do_unpack(L, words + 1, nw - 1);
    else res = dupstr("error: request");
    free(req);
    free(L);
    return res;
}
'''



def sol(lang, p):
    src = {"python": PY, "javascript": JS, "java": JV, "c": CC}[lang]
    if lang == "python":
        b = lambda v: "True" if v else "False"  # noqa: E731
    elif lang == "c":
        b = lambda v: "1" if v else "0"  # noqa: E731
    else:
        b = lambda v: "true" if v else "false"  # noqa: E731
    return K.subst(
        src, ORDER=p["order"], MSB="1" if p["order"] == "msb" else "0", MAXW=p["maxw"], MAXBITS=p["maxbits"], SIGNED=b(p["signed"]), ENUM=b(p["enum"]),
        FIXED=b(p["fixed"]), SUMS=b(p["sums"]), ARRAYS=b(p["arrays"]), VPACK=p["verbs"][0], VUNPACK=p["verbs"][1], UPPER=b(p["upper"]),
    ).lstrip("\n")


# ---------------------------------------------------------------------------------------------------------------
# layout construction for tests


U_NAMES = ["id", "seq", "batt", "hum", "count", "rate", "zone", "tick", "gain", "lane", "bin", "slot", "hops", "ttl", "rpm", "lux"]
I_NAMES = ["temp", "depth", "drift", "offset", "delta", "trim", "bias", "tilt"]
E_SETS = [("state", ["idle", "run", "fault"]), ("trend", ["fall", "flat", "rise"]), ("door", ["open", "shut", "ajar", "stuck"]), ("mode", ["off", "eco", "auto", "boost"]),
          ("tide", ["ebb", "slack", "flood"]), ("lamp", ["dark", "dim", "lit"]), ("wind", ["calm", "gusty"])]
F_NAMES = ["volt", "ph", "load", "flow", "dose"]


def lay_str(specs, trailer=""):
    toks = []
    for s in specs:
        if s["kind"] == "pad":
            toks.append(f"_:{s['w']}")
        elif s["kind"] == "e":
            toks.append(f"{s['name']}:{s['w']}e(" + "|".join(s["names"]) + ")")
        else:
            t = f"{s['name']}:{s['w']}{s['kind']}"
            if s["scale"]:
                t += f".{s['scale']}"
            if s["count"] > 1:
                t += f"*{s['count']}"
            toks.append(t)
    if trailer:
        toks.append("#" + trailer)
    return " ".join(toks)


def fmt_raw(rng, raw, scale):
    if scale == 0:
        return str(raw)
    a = abs(raw)
    ip, fp = divmod(a, 10 ** scale)
    fs = str(fp).rjust(scale, "0")
    d = rng.randint(len(fs.rstrip("0")), scale)
    return ("-" if raw < 0 else "") + str(ip) + ("." + fs[:d] if d else "")


def elem_range(s):
    w = s["w"]
    return (0, 2 ** w - 1) if s["kind"] == "u" else (-(2 ** (w - 1)), 2 ** (w - 1) - 1)


def elem_text(rng, s, mode="rand"):
    if s["kind"] == "e":
        return rng.choice(s["names"]) if mode == "rand" else s["names"][0 if mode in ("min", "zero") else -1]
    lo, hi = elem_range(s)
    raw = {"min": lo, "max": hi, "zero": 0 if lo <= 0 else lo, "rand": rng.randint(lo, hi)}[mode]
    if mode == "rand" and rng.random() < 0.25:
        raw = rng.choice([lo, hi, 0 if lo <= 0 else lo, 1 if hi >= 1 else 0, -1 if lo < 0 else 0])
    return fmt_raw(rng, raw, s["scale"])


def value_text(rng, s, mode="rand"):
    return ",".join(elem_text(rng, s, mode) for _ in range(s["count"]))


def make_specs(rng, p, nf, full=False):
    """A random layout for the level's features, at most maxbits wide."""
    mw = p["maxw"]
    used_u, used_i, used_f, used_e = set(), set(), set(), set()
    out = []

    def fresh(pool, used):
        for _ in range(30):
            n = rng.choice(pool)
            if n not in used:
                used.add(n)
                return n
        return None

    def add_u():
        n = fresh(U_NAMES, used_u)
        if n:
            out.append({"name": n, "w": rng.randint(1, mw), "kind": "u", "scale": 0, "count": 1})

    def add_i():
        n = fresh(I_NAMES, used_i)
        if n:
            out.append({"name": n, "w": rng.randint(2, mw), "kind": "i", "scale": 0, "count": 1})

    def add_e():
        cand = [e for e in E_SETS if e[0] not in used_e]
        if not cand:
            return
        name, names = rng.choice(cand)
        used_e.add(name)
        w = max(1, (len(names) - 1).bit_length()) + rng.choice([0, 0, 1])
        out.append({"name": name, "w": min(w, mw), "kind": "e", "scale": 0, "count": 1, "names": names})

    def add_f():
        n = fresh(F_NAMES, used_f)
        if n:
            out.append({"name": n, "w": rng.randint(4, mw), "kind": rng.choice("ui") if p["signed"] else "u", "scale": rng.randint(1, 3), "count": 1})

    def add_a():
        n = fresh(["buf", "taps", "lanes", "bins", "ring"], used_u)
        if n:
            out.append({"name": n, "w": rng.randint(2, max(2, min(mw, 6))), "kind": rng.choice("ui") if p["signed"] else "u", "scale": 0, "count": rng.randint(2, 4)})

    def add_p():
        out.append({"name": "_", "w": rng.randint(1, 4), "kind": "pad", "scale": 0, "count": 1})

    adders = [add_u, add_u]
    if p["signed"]:
        adders += [add_i]
    if p["enum"]:
        adders += [add_e]
    if p["fixed"]:
        adders += [add_f]
    if p["arrays"]:
        adders += [add_a, add_p]
    if full:
        for a in dict.fromkeys(adders):
            a()
    while len(out) < nf:
        rng.choice(adders)()
    # squeeze to the bit budget
    def total():
        return sum(s["w"] * s["count"] for s in out)

    guard = 0
    while total() > p["maxbits"] and guard < 200:
        guard += 1
        s = rng.choice(out)
        if s["kind"] == "e":
            if s["w"] > max(1, (len(s["names"]) - 1).bit_length()):
                s["w"] -= 1
        elif s["w"] > (2 if s["kind"] == "i" else 1):
            s["w"] -= 1
        elif len(out) > 2:
            out.remove(s)
    if not any(s["kind"] != "pad" for s in out):
        add_u()
    rng.shuffle(out)
    return out


def total_bits(specs):
    return sum(s["w"] * s["count"] for s in specs)


def req_pack(p, specs, vals):
    return " ".join([p["verbs"][0]] + [f"{s['name']}={v}" for s, v in vals])


def named(specs):
    return [s for s in specs if s["kind"] != "pad"]


def make_cases(rng, p, ns):
    wire = ns["wire"]
    vp, vu = p["verbs"]
    cases = []
    level = p["level"]

    def add(layout, req):
        cases.append((layout, req))

    layouts = []  # (specs, trailer)
    layouts.append(([{"name": "a", "w": 3, "kind": "u", "scale": 0, "count": 1}, {"name": "b", "w": 5, "kind": "u", "scale": 0, "count": 1}], ""))
    nf = lambda: rng.randint(2, 3 + level)  # noqa: E731
    for k in range(4):
        sp = make_specs(rng, p, nf(), full=(k == 0 and level >= 3))
        layouts.append((sp, rng.choice(["xor", "sum", ""]) if p["sums"] and k != 1 else ""))
    sp = make_specs(rng, p, 3)
    layouts.append((sp, ""))
    # exact-fit and single-bit layouts
    layouts.append(([{"name": "f", "w": 1, "kind": "u", "scale": 0, "count": 1}], ""))
    wide = []
    bits = 0
    while bits + p["maxw"] <= p["maxbits"]:
        wide.append({"name": "w%d" % len(wide), "w": p["maxw"], "kind": "u", "scale": 0, "count": 1})
        bits += p["maxw"]
    if bits < p["maxbits"]:
        wide.append({"name": "w%d" % len(wide), "w": p["maxbits"] - bits, "kind": "u", "scale": 0, "count": 1})
    layouts.append((wide, "xor" if p["sums"] else ""))

    first_valid = None
    for li, (specs, tr) in enumerate(layouts):
        lay = lay_str(specs, tr)
        ns_ = named(specs)
        # valid packs, with round trips
        for rep in range(3 if li else 2):
            vals = [(s, value_text(rng, s)) for s in ns_]
            rq = req_pack(p, specs, vals)
            add(lay, rq)
            hx = wire(lay, rq)
            assert not hx.startswith("error"), (lay, rq, hx)
            add(lay, f"{vu} {hx}")
            if li == 0 and rep == 0:
                first_valid = (lay, rq, hx)
        for mode in ("min", "max", "zero"):
            vals = [(s, value_text(rng, s, mode)) for s in ns_]
            rq = req_pack(p, specs, vals)
            add(lay, rq)
            hx = wire(lay, rq)
            add(lay, f"{vu} {hx}")
        vals = [(s, value_text(rng, s)) for s in ns_]
        base = req_pack(p, specs, vals)
        hx = wire(lay, base)
        # order of the fields in the request does not matter
        sh = vals[:]
        rng.shuffle(sh)
        add(lay, req_pack(p, specs, sh))
        # request errors
        add(lay, base + " " + vals[0][0]["name"] + "=1")  # duplicate
        add(lay, base + " zz9=1")
        add(lay, base + " ")
        add(lay, base.replace(" ", "  ", 1))
        add(lay, vp)
        add(lay, vp + " ")
        add(lay, vp.upper() + base[len(vp):])
        add(lay, " " + base)
        add(lay, base + " " + vals[0][0]["name"])
        if len(vals) > 1:
            add(lay, " ".join(base.split(" ")[:-1]))  # missing last
            add(lay, " ".join(base.split(" ")[:1] + base.split(" ")[2:]))  # missing first
        add(lay, base.replace("=", "==", 1))
        add(lay, base + " =5")
        add(lay, base + " q=")
        add(lay, base + " r")
        # value errors, one field at a time
        for s in rng.sample(ns_, min(len(ns_), 3)):
            others = [(t, value_text(rng, t)) for t in ns_]

            def with_(txt):
                return req_pack(p, specs, [(t, (txt if t is s else v)) for t, v in others])

            lo, hi = elem_range(s) if s["kind"] != "e" else (0, 0)
            bads = []
            if s["kind"] == "e":
                bads = ["Zzz", s["names"][0].upper(), str(0), s["names"][0] + "x", "x"]
            else:
                sc = 10 ** s["scale"]
                bads = [fmt_raw(rng, hi + 1, s["scale"]), fmt_raw(rng, lo - 1, s["scale"]) if lo < 0 else "-1", "007", "+5", "-0", "1e2", "0x1", "5.", ".5", "1 ", "99999999999999999999999",
                        "-" + "9" * 30, "1.2.3", "a", "1,5" if s["count"] == 1 else "1", fmt_raw(rng, hi, s["scale"]) + "0" * 3 if hi else "1"]
                if s["scale"]:
                    bads += ["1." + "5" * (s["scale"] + 1), "1.0" + "0" * s["scale"]]
                else:
                    bads += ["1.0", "1.5"]
                if s["count"] > 1:
                    good = [elem_text(rng, s) for _ in range(s["count"])]
                    bads += [",".join(good[:-1]), ",".join(good + [good[0]]), ",".join(good[:-1]) + ",", "," + ",".join(good[1:]), ",".join([good[0], ""] + good[2:]),
                             ",".join(good[:-1] + ["999999"])]
            for b in rng.sample(bads, min(len(bads), 5)):
                add(lay, with_(b))
        # unpack errors
        if hx and not hx.startswith("error"):
            add(lay, f"{vu} {hx.upper()}")
            add(lay, f"{vu} {hx}00")
            add(lay, f"{vu} {hx[:-2]}")
            add(lay, f"{vu} {hx[:-1]}")
            add(lay, f"{vu} 0x{hx}")
            add(lay, f"{vu} {hx[:-1]}g")
            add(lay, f"{vu} ")
            add(lay, vu)
            add(lay, f"{vu} {hx} {hx}")
            add(lay, f"{vu}  {hx}")
            add(lay, f"{vu} {hx} ")
            bsx = [int(hx[i:i + 2], 16) for i in range(0, len(hx), 2)]
            body = bsx[:-1] if tr else bsx
            nbits = total_bits(specs)

            def seal(b2):
                b2 = list(b2)
                if tr == "xor":
                    c = 0
                    for x in b2:
                        c ^= x
                    b2.append(c)
                elif tr == "sum":
                    b2.append(sum(b2) % 256)
                s2 = "".join("%02x" % x for x in b2)
                return s2.upper() if p["upper"] else s2

            bits = ns["from_bytes"](body, nbits)
            if nbits % 8:
                b3 = bits[:]
                b3[nbits + rng.randrange(8 - nbits % 8)] = 1
                add(lay, f"{vu} {seal(ns['to_bytes'](b3))}")
            if tr:
                for d in (1, 2, 16):
                    bb = bsx[:]
                    bb[-1] = (bb[-1] + d) % 256
                    s2 = "".join("%02x" % x for x in bb)
                    add(lay, f"{vu} {s2}")
                bb = bsx[:]
                bb[0] ^= 1
                add(lay, f"{vu} " + "".join("%02x" % x for x in bb))
            # field-level surgery: all ones in each field (enum overflow, signed extremes)
            pos = 0
            for s in specs:
                wdt = s["w"] * s["count"]
                if s["kind"] in ("e", "pad"):
                    for val in ((1 << s["w"]) - 1, 1 if s["kind"] == "pad" else (len(s["names"]) if len(s["names"]) < (1 << s["w"]) else 0)):
                        b3 = bits[:]
                        pp = pos
                        if p["order"] == "msb":
                            for j in range(s["w"] - 1, -1, -1):
                                b3[pp] = (val >> j) & 1
                                pp += 1
                        else:
                            for j in range(s["w"]):
                                b3[pp] = (val >> j) & 1
                                pp += 1
                        add(lay, f"{vu} {seal(ns['to_bytes'](b3))}")
                pos += wdt
    # layout errors
    lay_ok = lay_str(layouts[0][0])
    badl = ["", " ", "a:3u  b:5u", " a:3u", "a:3u ", "a:3u,b:5u", "a:3u b:5u c", "a:3 b:5u", "a:u", "a3u", ":3u", "a:0u", "a:03u", "a:" + str(p["maxw"] + 1) + "u", "a:100u", "A:3u", "1a:3u", "a-b:3u", "abcdefghi:3u",
            "a:3u a:2u", "a:3x", "a:3U", "a:+3u", "a:-3u", "a:3u b:", "a:3u:5u", "a:3u b:5u!", "#xor", "a:3u #xor #xor", "a:3u #crc", "#xor a:3u", "_:3", "a:3u _:3", "a:3u*2", "a:3u.1", "a:3e(x|y)", "a:3i", "a:3ux",
            lay_str(wide) + " zz:1u",
            " ".join("z%d:%du" % (i, p["maxw"]) for i in range(p["maxbits"] // p["maxw"] + 1)),
            "a:2u b:" + str(min(p["maxw"], 2)) + "u " + " ".join("c%d:1u" % i for i in range(p["maxbits"])),
            "a:3i b:5u" if not p["signed"] else "a:3i b:5i #xor" if not p["sums"] else "a:3u b:5u #xor extra"]
    if p["signed"]:
        badl += ["a:1i b:0i", "a:3i b:5u c:", "a:3I"]
    if p["enum"]:
        badl += ["a:2e", "a:2e()", "a:2e(x)y", "a:2e(x|)", "a:2e(|x)", "a:2e(x||y)", "a:1e(x|y|z)", "a:2e(x|x)", "a:2e(X|y)", "a:2e(x|y", "a:2ex|y)", "a:3e(1a|b)", "a:3e(a_b|c)", "a:3e(" + "|".join("n%d" % i for i in range(9)) + ")",
                 "a:5e(" + "|".join("n%d" % i for i in range(17)) + ")", "a:2e(abcdefghi|b)", "a:2e (x|y)"]
    if p["fixed"]:
        badl += ["a:5u.0", "a:5u.4", "a:5u.", "a:5u.x", "a:5u.12", "a:5u.1.1", "a:5.1u", "a:5e(x|y).1"]
    if p["arrays"]:
        badl += ["a:3u*", "a:3u*1", "a:3u*9", "a:3u*10", "a:3u*0", "a:3u*2*2", "a:3u.1*2", "a:3u*2.1", "_:3 _:4", "_:0 a:2u", "_:", "_:3u a:1u", "_ :3 a:1u", "__:3 a:1u", "a:3e(x|y)*2", "_:" + str(p["maxw"] + 1) + " a:1u", "a:2u _:2*2", "_:1"]
    else:
        badl += ["_:3 a:2u", "a:2u*2"]
    for bl in badl:
        add(bl, f"{vp} a=1")
        if rng.random() < 0.3:
            add(bl, "nonsense")
    # layout error beats request error
    add("", "nonsense")
    add("a:0u", "")
    # request not a command
    for rq in ["", " ", "nonsense", "pack a=1", "unpack 00", vp.upper(), vp + "x", "x" + vp, vp[:-1], " " + vu + " 00", vp + "\t" + "a=1", vp + "\ta=1", vu + "\n00"]:
        add(lay_ok, rq)
    # dedupe preserving order, keep the examples first
    nex = 0
    ex = []
    lay0, rq0, hx0 = first_valid
    ex.append((lay0, rq0))
    ex.append((lay0, f"{vu} {hx0}"))
    # a richer example from the first full layout
    sp1, tr1 = layouts[1]
    vals = [(s, value_text(rng, s)) for s in named(sp1)]
    l1 = lay_str(sp1, tr1)
    rq1 = req_pack(p, sp1, vals)
    ex.append((l1, rq1))
    ex.append((l1, f"{vu} {wire(l1, rq1)}"))
    if level >= 2:
        s0 = named(sp1)[0]
        lo, hi = elem_range(s0) if s0["kind"] != "e" else (0, 0)
        bad = (str(hi + 1) if s0["kind"] != "e" else "nope") if s0["scale"] == 0 else "-"
        ex.append((l1, req_pack(p, sp1, [(s, (bad if s is s0 else v)) for s, v in vals])))
    nex = len(ex)
    allc = ex + cases
    out, seen = [], set()
    for c in allc:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out, nex, first_valid


def worked(p, ns, layout, request):
    """Bit-level walk through the first example, for the README."""
    lay = ns["parse_layout"](layout)
    fields, trailer = lay
    given = dict(w.split("=") for w in request.split(" ")[1:])
    parts = []
    bits = []
    for f in fields:
        if f.kind == "pad":
            vals = ["0"] * f.width
            parts.append(f"`_` -> `{''.join(vals)}`")
            bits.extend([0] * f.width)
            continue
        items = given[f.name].split(",") if f.count > 1 else [given[f.name]]
        for it in items:
            v = ns["parse_elem"](it, f)
            b = []
            ns["emit_bits"](b, v & ((1 << f.width) - 1), f.width)
            bits.extend(b)
            parts.append(f"`{f.name}={it}` -> `{''.join(map(str, b))}`")
    return parts, "".join(map(str, bits))


def readme(p, api, lang, examples, first_valid, ns):
    vp, vu = p["verbs"]
    L = [f"# Packed wire format for {p['theme'][0]}", ""]
    L.append(f"{p['theme'][1]} `wire(layout, request)` packs named values into a short byte string (written as hex) and unpacks it again. The *layout* describes the fields; the *request* says what to do.")
    L.append("")
    L.append("## Layouts")
    L.append("")
    L.append("A layout is a list of field specs separated by **single spaces** (a doubled, leading or trailing space makes the layout invalid). Each spec is `NAME:WIDTH` followed by a kind:")
    L.append("")
    L.append(f"* `NAME` is 1 to 8 characters: a lower-case ASCII letter, then lower-case letters, digits or `_`. Names are unique in a layout.")
    L.append(f"* `WIDTH` is the number of bits, written in decimal without leading zeros, from 1 to {p['maxw']}.")
    L.append("* kind `u`: an unsigned integer, `0` to `2^WIDTH - 1`.")
    if p["signed"]:
        L.append("* kind `i`: a signed integer in two's complement, `-2^(WIDTH-1)` to `2^(WIDTH-1) - 1`.")
    if p["enum"]:
        L.append("* kind `e(NAME0|NAME1|...)` (directly after the width): a choice from a list of names. Each name follows the same rules as a field name but may not contain `_`; at most 16 names, no repeats, and at most `2^WIDTH` of them. The name at position `k` (counting from 0) is stored as the number `k`.")
    if p["fixed"]:
        L.append("* `u` or `i` may be followed by `.D` with `D` one of `1`, `2`, `3`: a fixed-point number with `D` decimal places. The stored integer is the value times `10^D` (so `3.25` with `.2` is stored as `325`); the range rule applies to the stored integer. Example: `temp:12i.1`.")
    if p["arrays"]:
        L.append("* `u` or `i` (without `.D`) may be followed by `*COUNT` with `COUNT` one of `2` to `8`: an array of that many values, each `WIDTH` bits wide (`ring:5i*3`).")
        L.append("* `_:WIDTH` is a reserved gap of `WIDTH` bits (no kind). It has no name, is not part of a request and is written as zero bits.")
    if p["sums"]:
        L.append("* The layout may end with one extra word, `#xor` or `#sum` (not a field): see *Checksum* below.")
    L.append(f"* The fields (arrays count `COUNT` times, gaps count too) must add up to at most {p['maxbits']} bits.")
    L.append("")
    L.append("Anything else is an invalid layout, for example another kind letter, a missing width or a repeated name. A layout also needs at least one named field.")
    L.append("")
    L.append("## Packing")
    L.append("")
    L.append("The bits of all fields are produced in layout order, first field first. Values are written as follows:")
    L.append("")
    if p["order"] == "msb":
        L.append("* Within a field the **most significant bit comes first** (signed values in two's complement).")
        L.append("* The bit string is padded on the right with `0` bits to a whole number of bytes and cut into bytes from the left; the first bit of a byte is its most significant bit.")
    else:
        L.append("* Within a field the **least significant bit comes first** (signed values in two's complement).")
        L.append("* The produced bits are numbered `0, 1, 2, ...` in order. Bit number `k` is bit `k mod 8` of byte `k div 8`, where bit 0 of a byte is its *least* significant bit. Bits of the last byte that no field uses are `0`.")
    L.append("")
    if p["sums"]:
        L.append("### Checksum")
        L.append("")
        L.append("With `#xor` one more byte is appended after the field bytes: the bitwise XOR of all field bytes. With `#sum` it is the sum of all field bytes modulo 256. Without a trailer there is no extra byte.")
        L.append("")
    L.append("The result is lower-case hex, two digits per byte, no separators." if not p["upper"] else "The result is **upper-case** hex, two digits per byte, no separators.")
    parts, bitstr = worked(p, ns, first_valid[0], first_valid[1])
    L.append("")
    L.append(f"Worked example (layout `{first_valid[0]}`, request `{first_valid[1]}`): the fields produce " + ", ".join(parts) + f", that is the bit string `{bitstr}`" + f"; the result is `{first_valid[2]}`.")
    L.append("")
    L.append("## Requests")
    L.append("")
    L.append("The request is split at **single spaces**; the first word selects the operation (case-sensitive).")
    L.append("")
    L.append(f"* `{vp} NAME=VALUE ...`: one `NAME=VALUE` word for every named field, in any order. The result is the hex string.")
    L.append(f"* `{vu} HEX`: exactly one more word. The result lists every named field in **layout order** as `NAME=VALUE`, joined by single spaces.")
    L.append("")
    L.append("**Value text.** Integers are written in decimal ASCII digits: no `+`, no leading zeros (`0` itself is fine), no blanks, no exponent; a leading `-` is allowed for signed fields only and `-0` is not a number." if p["signed"] else
             "**Value text.** Integers are written in decimal ASCII digits: no sign, no leading zeros (`0` itself is fine), no blanks, no exponent.")
    if p["enum"]:
        L.append("An enum value is one of the names, spelt exactly.")
    if p["fixed"]:
        L.append("A fixed-point value is `INT` or `INT.FRAC` where `FRAC` has between 1 and `D` digits (so `5`, `5.5` and `5.50` are all fine for `.2`, but `5.` and `5.555` are not); " + ("a leading `-` is allowed for signed fields, and a negative zero such as `-0.00` is not a value. " if p["signed"] else "") + "Unpacking always writes exactly `D` decimal places (`5.50`).")
    if p["arrays"]:
        L.append("An array value is its `COUNT` element values joined by `,` (no blanks), for example `3,-2,0`; unpacking prints them the same way.")
    L.append("A value that is not valid text or is out of range is an invalid value. There is no limit on the number of digits that may be *written*: a long digit string is just out of range.")
    L.append("")
    L.append("## Errors")
    L.append("")
    L.append("The result is an error text instead of data in these cases. Check in this order and report the first that applies.")
    L.append("")
    L.append("1. `error: layout`: the layout is invalid (even when the request is wrong too).")
    L.append(f"2. `error: request`: the first word is neither `{vp}` nor `{vu}`; for `{vp}`, a word that is not of the form `NAME=VALUE` (a missing `=`, an empty name or value, or a second `=`) anywhere in the request; for `{vu}`, a number of words other than one.")
    L.append(f"3. for `{vp}`, walking the words from left to right: `error: unknown NAME` for a name that is not a named field of the layout, `error: duplicate NAME` for a name seen before.")
    L.append(f"4. `error: missing NAME`: the first named field (layout order) that has no word.")
    L.append(f"5. `error: value NAME`: the first named field (layout order) with an invalid or out-of-range value.")
    L.append(f"6. for `{vu}`: `error: hex` if the word is empty or has a character that is not a hex digit (either case is accepted), then `error: length` unless it has exactly the number of digits the layout needs (the field bytes" + (" plus the checksum byte" if p["sums"] else "") + ")," + (" then `error: checksum` if the checksum byte does not match the others," if p["sums"] else "") +
             (" then `error: padding` if a gap or an unused bit of the last byte is not zero," if p["arrays"] else " then `error: padding` if an unused bit of the last byte is not zero,") + (" then `error: enum NAME` for the first enum field whose stored number has no name." if p["enum"] else ""))
    L.append("")
    L.append(K.interface_section(api, lang))
    L.append("## Examples")
    L.append("")
    L.append("| layout | request | result |")
    L.append("|---|---|---|")
    for (lay, rq), out in examples:
        L.append(f"| `{lay}` | `{rq}` | `{out}` |")
    L.append("")
    L.append(K.run_hint(lang, api.mod))
    return "\n".join(L) + "\n"


def prompt(rng, p, api, lang):
    where = api.short(lang)
    fn = api.name(lang)
    ln = K.LANG_NAME[lang]
    vp, vu = p["verbs"]
    feats = ["unsigned"] + (["signed"] if p["signed"] else []) + (["enum"] if p["enum"] else []) + (["fixed-point"] if p["fixed"] else []) + (["array and gap"] if p["arrays"] else [])
    fl = ", ".join(feats)
    opts = [
        f"Records for {p['theme'][0]} are bit-packed. Write `{fn}(layout, request)` in {ln}, in {where}: it parses a field layout and does `{vp}` / `{vu}` as README.md describes ({fl} fields). {K.closer(rng)}",
        f"Implement the bit-packing helper from README.md in {ln} ({where}; `{fn}`). Field kinds in this version: {fl}. Error priority matters, and the hidden tests probe malformed layouts. {K.closer(rng)}",
        f"{ln} task: a layout-driven bit packer (`{fn}`, {where}). Read README.md for the layout syntax, the {p['order'].upper()}-first bit order and the error texts. {K.closer(rng)}",
        f"Build `{fn}` ({where}) in {ln}. It turns `{vp} name=value ...` into hex and `{vu} HEX` back into values for a layout you parse yourself; the spec is README.md. Hidden checks cover range edges and bad input.",
    ]
    return rng.choice(opts).strip()


THEMES = [
    ("the tide-gauge beacons", "The tide-gauge beacons send very small radio records."),
    ("the greenhouse sensor mesh", "The greenhouse sensors report over a slow serial link."),
    ("the kiln controller bus", "The kiln controllers share a narrow bus."),
    ("the hive monitor tags", "The hive monitor tags have only a few bytes of payload."),
    ("the ferry door panels", "The ferry door panels chatter over a legacy link."),
    ("the seed-vault loggers", "The seed-vault loggers store compact records."),
]


def params(rng, level, i):
    return {
        "level": level, "order": rng.choice(["msb", "lsb"]), "maxw": rng.choice([8, 12, 16]) if level >= 2 else rng.choice([8, 12]), "maxbits": rng.choice([32, 48, 64]),
        "signed": level >= 2, "enum": level >= 3, "fixed": level >= 4, "sums": level >= 4, "arrays": level >= 5,
        "verbs": rng.choice([("pack", "unpack"), ("enc", "dec"), ("put", "get"), ("write", "read"), ("squash", "expand")]),
        "upper": rng.random() < 0.35, "theme": THEMES[(i + rng.randrange(2)) % len(THEMES)],
    }


LANG_PLAN = ["c", "java", "javascript", "java", "c", "python", "java", "c"]
LEVELS = [1, 1, 2, 2, 3, 3, 4, 5]


@family("greenfield-bitwire", category="greenfield", lang="mixed", kind="greenfield", n=8,
        summary="layout-driven bit packer: parse a field layout (unsigned/signed/enum/fixed-point/array/gap), pack and unpack hex, with a strict error priority and optional checksum")
def gen(rng, n):
    for i in range(n):
        lang = LANG_PLAN[i % len(LANG_PLAN)]
        level = LEVELS[i % len(LEVELS)]
        p = params(rng, level, i)
        api = K.Api(mod="bitwire", fn="wire", args=["layout", "request"], arg_docs=["the field layout text", f"the request: `{p['verbs'][0]} NAME=VALUE ...` or `{p['verbs'][1]} HEX`"],
                    ret_doc="the hex string, the field list or an error text", doc="layout-driven bit packer")
        py_src = sol("python", p)
        ns = K.py_namespace(py_src)
        cases, nex, first_valid = make_cases(rng, p, ns)
        sols = {lang: sol(lang, p), "python": py_src}
        examples = [(c, ns["wire"](*c)) for c in cases[:nex]]
        rd = readme(p, api, lang, examples, first_valid, ns)
        yield K.lib_task(
            api=api, lang=lang, readme=rd, solutions=sols, cases=cases, examples=nex, prompt=prompt(rng, p, api, lang),
            difficulty=level, slug=f"{i + 1:02d}-{lang}-{p['order']}-l{level}", oracle=(None if lang == "python" else ns["wire"]),
            tags=["parser", "binary"], notes={"level": level, "order": p["order"], "maxw": p["maxw"], "maxbits": p["maxbits"]},
        )
