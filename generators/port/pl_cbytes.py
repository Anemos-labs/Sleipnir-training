"""Port library whose source language is C: byte-stuffed frames over hex text."""
from fx import dd

from ._portlib import PortLib, register_port
from ._types import Fn

BS_SPEC = dd('''
    A serial link wraps messages in frames. Bytes travel as **hex text** in this library: an even number of ASCII hex digits,
    upper or lower case accepted on input, **lower case** on output; anything else (odd length, other characters, spaces) is an
    error. Three byte values are special: `0x7E` (FLAG, starts a frame), `0x7F` (END, ends a frame) and `0x7D` (ESC).

    * `checksum(payload)` is `(sum of the payload bytes + number of payload bytes) mod 256`.
    * **Stuffing** replaces every special byte `b` inside a frame by two bytes: ESC and `b XOR 0x20`
      (`7e` becomes `7d5e`, `7f` becomes `7d5f`, `7d` becomes `7d5d`).
    * `frame(payload)` is FLAG, then the stuffed bytes of `payload` followed by its checksum, then END. The empty payload is allowed.
      Example: payload `0102` has checksum `05`, the frame is `7e0102057f`.
    * `unstuff(body)` reverses the stuffing of a bare body: an ESC at the very end, an ESC followed by a byte `x` where
      `x XOR 0x20` is not one of the three special values, or a raw FLAG or END byte are errors.
    * `unframe(frame)` requires FLAG first, END last, at least one byte between them, a valid stuffed body in between whose last
      unstuffed byte is the checksum of the unstuffed bytes before it; it returns the payload. Anything else is an error.
    * `count_frames(stream)` counts the valid frames in a byte stream (an invalid stream text is an error). Scan the bytes with a
      single "collecting" state: a FLAG starts collecting (a FLAG seen while already collecting restarts at that FLAG, dropping
      what was collected); an END while collecting ends the candidate frame, which counts if `unframe` accepts it, and
      collecting stops either way; bytes outside a frame, and an END while not collecting, are ignored; an unfinished frame at
      the end does not count. Streams in the tests are at most 1000 bytes long.
''')

BS_FNS = [
    Fn("checksum", [("payload", "str")], "u8", err=True),
    Fn("frame", [("payload", "str")], "str", err=True),
    Fn("unstuff", [("body", "str")], "str", err=True),
    Fn("unframe", [("framed", "str")], "str", err=True),
    Fn("count_frames", [("stream", "str")], "int", err=True),
]

BS_H = dd('''
    #ifndef BYTE_STUFF_H
    #define BYTE_STUFF_H

    #include <stddef.h>
    #include <stdint.h>

    /* All functions return 0 on success and a non-zero value on error. Text results are NUL-terminated and
       must fit in `cap` bytes (including the NUL), otherwise the call fails. */
    int byte_stuff_checksum(const char *payload, uint8_t *out);
    int byte_stuff_frame(const char *payload, char *out, size_t cap);
    int byte_stuff_unstuff(const char *body, char *out, size_t cap);
    int byte_stuff_unframe(const char *framed, char *out, size_t cap);
    int byte_stuff_count_frames(const char *stream, int64_t *out);

    #endif
''')

BS_C = dd(r'''
#include "byte_stuff.h"

#include <string.h>

#define MAXB 4096
#define FLAG 0x7E
#define END 0x7F
#define ESC 0x7D

static int hexval(int c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static int parse_hex(const char *s, uint8_t *buf, size_t *n) {
    size_t len = strlen(s);
    if (len % 2 != 0 || len / 2 > MAXB) return -1;
    for (size_t i = 0; i < len / 2; i++) {
        int h = hexval((unsigned char)s[2 * i]);
        int l = hexval((unsigned char)s[2 * i + 1]);
        if (h < 0 || l < 0) return -1;
        buf[i] = (uint8_t)(h << 4 | l);
    }
    *n = len / 2;
    return 0;
}

static int emit_hex(const uint8_t *b, size_t n, char *out, size_t cap) {
    static const char digits[] = "0123456789abcdef";
    if (cap < 2 * n + 1) return -1;
    for (size_t i = 0; i < n; i++) {
        out[2 * i] = digits[b[i] >> 4];
        out[2 * i + 1] = digits[b[i] & 15];
    }
    out[2 * n] = '\0';
    return 0;
}

static uint8_t sum_of(const uint8_t *p, size_t n) {
    unsigned s = (unsigned)n;
    for (size_t i = 0; i < n; i++) s += p[i];
    return (uint8_t)(s & 0xFF);
}

static int is_special(int b) { return b == FLAG || b == END || b == ESC; }

/* unstuff the bytes in[0..n) into out; returns the number of bytes or -1 */
static int unstuff_bytes(const uint8_t *in, size_t n, uint8_t *out) {
    size_t m = 0;
    for (size_t i = 0; i < n; i++) {
        uint8_t b = in[i];
        if (b == FLAG || b == END) return -1;
        if (b == ESC) {
            if (i + 1 >= n) return -1;
            i++;
            uint8_t c = in[i] ^ 0x20;
            if (!is_special(c)) return -1;
            out[m++] = c;
        } else {
            out[m++] = b;
        }
    }
    return (int)m;
}

static int unframe_bytes(const uint8_t *f, size_t n, uint8_t *payload, size_t *plen) {
    uint8_t tmp[MAXB];
    if (n < 3 || f[0] != FLAG || f[n - 1] != END) return -1;
    int m = unstuff_bytes(f + 1, n - 2, tmp);
    if (m < 1) return -1;
    if (sum_of(tmp, (size_t)m - 1) != tmp[m - 1]) return -1;
    memcpy(payload, tmp, (size_t)m - 1);
    *plen = (size_t)m - 1;
    return 0;
}

int byte_stuff_checksum(const char *payload, uint8_t *out) {
    uint8_t buf[MAXB];
    size_t n;
    if (parse_hex(payload, buf, &n)) return -1;
    *out = sum_of(buf, n);
    return 0;
}

int byte_stuff_frame(const char *payload, char *out, size_t cap) {
    uint8_t buf[MAXB + 1], res[2 * MAXB + 8];
    size_t n, m = 0;
    if (parse_hex(payload, buf, &n)) return -1;
    buf[n] = sum_of(buf, n);
    res[m++] = FLAG;
    for (size_t i = 0; i <= n; i++) {
        if (is_special(buf[i])) {
            res[m++] = ESC;
            res[m++] = buf[i] ^ 0x20;
        } else {
            res[m++] = buf[i];
        }
    }
    res[m++] = END;
    return emit_hex(res, m, out, cap);
}

int byte_stuff_unstuff(const char *body, char *out, size_t cap) {
    uint8_t buf[MAXB], res[MAXB];
    size_t n;
    if (parse_hex(body, buf, &n)) return -1;
    int m = unstuff_bytes(buf, n, res);
    if (m < 0) return -1;
    return emit_hex(res, (size_t)m, out, cap);
}

int byte_stuff_unframe(const char *framed, char *out, size_t cap) {
    uint8_t buf[MAXB], payload[MAXB];
    size_t n, plen;
    if (parse_hex(framed, buf, &n)) return -1;
    if (unframe_bytes(buf, n, payload, &plen)) return -1;
    return emit_hex(payload, plen, out, cap);
}

int byte_stuff_count_frames(const char *stream, int64_t *out) {
    uint8_t buf[MAXB], payload[MAXB];
    size_t n, plen, start = 0;
    int collecting = 0;
    int64_t count = 0;
    if (parse_hex(stream, buf, &n)) return -1;
    for (size_t i = 0; i < n; i++) {
        if (buf[i] == FLAG) {
            collecting = 1;
            start = i;
        } else if (buf[i] == END && collecting) {
            if (unframe_bytes(buf + start, i - start + 1, payload, &plen) == 0) count++;
            collecting = 0;
        }
    }
    *out = count;
    return 0;
}
''')

BS_PY = dd(r'''
FLAG, END, ESC = 0x7E, 0x7F, 0x7D
_HEX = "0123456789abcdefABCDEF"


def _parse(text):
    if len(text) % 2 or any(c not in _HEX for c in text):
        raise ValueError("bad hex")
    return bytes(int(text[i:i + 2], 16) for i in range(0, len(text), 2))


def _hex(b):
    return "".join("%02x" % x for x in b)


def _sum(b):
    return (sum(b) + len(b)) & 0xFF


def checksum(payload):
    return _sum(_parse(payload))


def frame(payload):
    body = _parse(payload)
    body += bytes([_sum(body)])
    out = bytearray([FLAG])
    for b in body:
        if b in (FLAG, END, ESC):
            out += bytes([ESC, b ^ 0x20])
        else:
            out.append(b)
    out.append(END)
    return _hex(out)


def _unstuff(b):
    out, i = bytearray(), 0
    while i < len(b):
        x = b[i]
        if x in (FLAG, END):
            raise ValueError("raw special byte")
        if x == ESC:
            i += 1
            if i >= len(b) or (b[i] ^ 0x20) not in (FLAG, END, ESC):
                raise ValueError("bad escape")
            out.append(b[i] ^ 0x20)
        else:
            out.append(x)
        i += 1
    return bytes(out)


def unstuff(body):
    return _hex(_unstuff(_parse(body)))


def _unframe(f):
    if len(f) < 3 or f[0] != FLAG or f[-1] != END:
        raise ValueError("bad framing")
    body = _unstuff(f[1:-1])
    if len(body) < 1 or _sum(body[:-1]) != body[-1]:
        raise ValueError("bad checksum")
    return body[:-1]


def unframe(framed):
    return _hex(_unframe(_parse(framed)))


def count_frames(stream):
    data = _parse(stream)
    count, start = 0, None
    for i, b in enumerate(data):
        if b == FLAG:
            start = i
        elif b == END and start is not None:
            try:
                _unframe(data[start:i + 1])
                count += 1
            except ValueError:
                pass
            start = None
    return count
''')

BS_RS = dd(r'''
const FLAG: u8 = 0x7E;
const END: u8 = 0x7F;
const ESC: u8 = 0x7D;

fn parse(text: &str) -> Result<Vec<u8>, String> {
    let b = text.as_bytes();
    if b.len() % 2 != 0 || !b.iter().all(|c| c.is_ascii_hexdigit()) {
        return Err("bad hex".to_string());
    }
    Ok((0..b.len() / 2).map(|i| u8::from_str_radix(&text[2 * i..2 * i + 2], 16).unwrap()).collect())
}

fn to_hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{:02x}", x)).collect()
}

fn sum_of(b: &[u8]) -> u8 {
    b.iter().fold(b.len() as u32, |acc, &x| acc + x as u32) as u8
}

fn special(b: u8) -> bool {
    b == FLAG || b == END || b == ESC
}

pub fn checksum(payload: &str) -> Result<u8, String> {
    Ok(sum_of(&parse(payload)?))
}

pub fn frame(payload: &str) -> Result<String, String> {
    let mut body = parse(payload)?;
    body.push(sum_of(&body));
    let mut out = vec![FLAG];
    for b in body {
        if special(b) {
            out.push(ESC);
            out.push(b ^ 0x20);
        } else {
            out.push(b);
        }
    }
    out.push(END);
    Ok(to_hex(&out))
}

fn unstuff_bytes(b: &[u8]) -> Result<Vec<u8>, String> {
    let mut out = Vec::new();
    let mut i = 0;
    while i < b.len() {
        let x = b[i];
        if x == FLAG || x == END {
            return Err("raw special byte".to_string());
        }
        if x == ESC {
            i += 1;
            if i >= b.len() || !special(b[i] ^ 0x20) {
                return Err("bad escape".to_string());
            }
            out.push(b[i] ^ 0x20);
        } else {
            out.push(x);
        }
        i += 1;
    }
    Ok(out)
}

pub fn unstuff(body: &str) -> Result<String, String> {
    Ok(to_hex(&unstuff_bytes(&parse(body)?)?))
}

fn unframe_bytes(f: &[u8]) -> Result<Vec<u8>, String> {
    if f.len() < 3 || f[0] != FLAG || f[f.len() - 1] != END {
        return Err("bad framing".to_string());
    }
    let body = unstuff_bytes(&f[1..f.len() - 1])?;
    match body.split_last() {
        Some((&last, rest)) if sum_of(rest) == last => Ok(rest.to_vec()),
        _ => Err("bad checksum".to_string()),
    }
}

pub fn unframe(framed: &str) -> Result<String, String> {
    Ok(to_hex(&unframe_bytes(&parse(framed)?)?))
}

pub fn count_frames(stream: &str) -> Result<i64, String> {
    let data = parse(stream)?;
    let mut count = 0;
    let mut start: Option<usize> = None;
    for (i, &b) in data.iter().enumerate() {
        if b == FLAG {
            start = Some(i);
        } else if b == END {
            if let Some(s) = start {
                if unframe_bytes(&data[s..=i]).is_ok() {
                    count += 1;
                }
                start = None;
            }
        }
    }
    Ok(count)
}
''')


def _frame(payload: bytes) -> str:
    body = payload + bytes([(sum(payload) + len(payload)) & 0xFF])
    out = bytearray([0x7E])
    for b in body:
        if b in (0x7E, 0x7F, 0x7D):
            out += bytes([0x7D, b ^ 0x20])
        else:
            out.append(b)
    out.append(0x7F)
    return out.hex()


def bs_cases(rng):
    out = [("checksum", ["0102"]), ("frame", ["0102"]), ("frame", ["7e"]), ("unstuff", ["017d5e02"]), ("unframe", ["7e010205" + "7f"]), ("count_frames", [_frame(b"ab") + "00" + _frame(b"cd")])]
    pls = ["", "00", "01", "0102", "ff", "7e", "7f", "7d", "7e7f7d", "7d5e", "deadBEEF", "00ff00ff", "ffffffff", "10" * 20, "7d" * 5, "a5", "FF", "0A0b"]
    for p in pls:
        out.append(("checksum", [p]))
        out.append(("frame", [p]))
    for p in ["0", "abc", "zz", "12 34", "0x12", "12\n", "١٢", "gg", "-1", "fffff"]:
        out.append(("checksum", [p]))
        out.append(("frame", [p]))
        out.append(("unstuff", [p]))
        out.append(("unframe", [p]))
        out.append(("count_frames", [p]))
    for b in ["", "00", "7d5e", "7d5f", "7d5d", "7d", "017d", "7d00", "7d5c", "7e", "7f", "01027e", "017f02", "7d7d", "7d5e7d5f7d5d", "0102030405", "7D5E", "7d5E", "7d1e", "7d3f"]:
        out.append(("unstuff", [b]))
    frames = [_frame(bytes.fromhex(p)) for p in ["", "00", "0102", "7e", "7f7d7e", "deadbeef", "ff" * 10]]
    for f in frames:
        out.append(("unframe", [f]))
        out.append(("unframe", [f.upper()]))
        out.append(("unframe", [f[2:]]))
        out.append(("unframe", [f[:-2]]))
        out.append(("unframe", ["7e" + f]))
        out.append(("unframe", [f + "00"]))
        flip = f[:4] + ("00" if f[4:6] != "00" else "01") + f[6:]
        out.append(("unframe", [flip]))
    for f in ["", "7e", "7f", "7e7f", "7e007f", "7e017f", "7e007e7f", "7e7d7f", "7e017d7f", "7e7f7f", "7f007e", "7e00", "007f", "7e0000007f"]:
        out.append(("unframe", [f]))
    garbage = ["", "00", "ff", "7f", "7f7f", "0102", "7e", "7e7e", "7e7e7e", "7e00"]
    for _ in range(20):
        parts = []
        for _ in range(rng.randint(0, 6)):
            r = rng.random()
            if r < 0.5:
                parts.append(rng.choice(frames))
            elif r < 0.7:
                parts.append(rng.choice(garbage))
            elif r < 0.85:
                f = rng.choice(frames)
                parts.append(f[:rng.randint(2, max(2, len(f) - 2))])
            else:
                parts.append("".join(rng.choice("0123456789abcdef") for _ in range(2 * rng.randint(0, 5))))
        out.append(("count_frames", ["".join(parts)]))
    out.append(("count_frames", [""]))
    out.append(("count_frames", [frames[2] * 3]))
    out.append(("count_frames", ["7e01" + frames[2]]))
    out.append(("count_frames", [frames[2][:-2] + frames[2]]))
    out.append(("count_frames", ["7f" + frames[2] + "7f"]))
    out.append(("count_frames", [frames[2] + "7e"]))
    out.append(("count_frames", ["7e7f" + frames[1]]))
    out.append(("count_frames", ["7e000000" + "7f" + frames[1]]))
    for _ in range(12):
        p = bytes(rng.choice([0x00, 0x01, 0x7D, 0x7E, 0x7F, 0x20, 0x5E, 0xFF, rng.randint(0, 255)]) for _ in range(rng.randint(0, 12)))
        fr = _frame(p)
        out.append(("frame", [p.hex()]))
        out.append(("unframe", [fr]))
        out.append(("checksum", [p.hex()]))
        out.append(("count_frames", [fr + fr]))
    return out


BS = PortLib(
    slug="byte-stuff",
    title="byte-stuffed serial frames",
    blurb="A firmware team's host tools talk to a serial device that wraps messages in flagged, byte-stuffed, checksummed frames; the C reference code is being replaced.",
    spec=BS_SPEC,
    fns=BS_FNS,
    impls={"c": {"src/byte_stuff.c": BS_C, "include/byte_stuff.h": BS_H}, "rust": {"src/lib.rs": BS_RS}, "python": {"byte_stuff.py": BS_PY}},
    cases=bs_cases,
    difficulty=3,
    traps=["escape handling", "u8 arithmetic wrap (checksum)", "strict hex", "state machine restart on FLAG"],
    tags=["binary-framing", "c"],
    pairs=[("c", "rust", "full"), ("c", "python", "full"), ("rust", "python", "stub"), ("python", "rust", "stub")],
    diff_adj={"c>python": 0},
)
register_port(BS, __name__)
