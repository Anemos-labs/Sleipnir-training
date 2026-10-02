"""A made-up 1-D barcode symbology: encode text to a bar/space string, decode it back (also read backwards) with exact error codes."""
from __future__ import annotations

from fx import family

from generators.greenfield import _kit as K

POOL = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-$/+%:"
NAMES = ["Tribar-16", "Quillcode", "Ferrybar", "Kelpcode-6", "Hollin-3of6", "Tidestripe", "Marshcode"]
LANG_PLAN = ["c", "rust", "python", "go", "c", "rust", "go", "c", "rust", "python", "go", "c"]


def params(rng, level, i):
    alpha = "".join(rng.sample(POOL, 16))
    return {
        "level": level, "name": NAMES[(i + rng.randrange(3)) % len(NAMES)], "alpha": alpha, "w": rng.choice([2, 3]),
        "weight": ["inc", "odd", "alt"][(i + rng.randrange(3)) % 3], "swap": rng.random() < 0.5,
        "decode": level >= 3, "both": level >= 4,
    }


PY = r'''
ALPHA = "@ALPHA@"
W = @W@
WEIGHT = "@WEIGHT@"
SWAP = @SWAP@
HAS_DECODE = @DECODE@
BOTH = @BOTH@
PATS = [p for p in range(64) if bin(p).count("1") == 3]
START = PATS[17 if SWAP else 16]
STOP = PATS[16 if SWAP else 17]


def weight(i):
    if WEIGHT == "inc":
        return i + 1
    if WEIGHT == "odd":
        return 2 * i + 1
    return 1 if i % 2 == 0 else 3


def sym_bars(p):
    out = ""
    for j in range(6):
        bit = (p >> (5 - j)) & 1
        out += ("#" if j % 2 == 0 else ".") * (W if bit else 1)
    return out


def encode(text):
    if not (1 <= len(text) <= 20):
        return "error: length"
    for c in text:
        if c not in ALPHA:
            return "error: char " + c
    vals = [ALPHA.index(c) for c in text]
    chk = sum(weight(i) * v for i, v in enumerate(vals)) % 16
    syms = [START] + [PATS[v] for v in vals] + [PATS[chk], STOP]
    return "".join(sym_bars(p) for p in syms) + "#"


def runs_of(s):
    runs = []
    i = 0
    while i < len(s):
        j = i
        while j < len(s) and s[j] == s[i]:
            j += 1
        runs.append(j - i)
        i = j
    return runs


def attempt(s):
    """('ok', text) or ('err', code) for the string read in its given orientation (width and structure already checked)."""
    runs = runs_of(s)
    if runs[-1] != 1:
        return ("err", "terminator")
    groups = [runs[k:k + 6] for k in range(0, len(runs) - 1, 6)]
    pats = []
    for k, g in enumerate(groups):
        p = 0
        for r in g:
            p = p * 2 + (1 if r == W else 0)
        if p not in PATS:
            return ("err", "symbol %d" % k) if k > 0 else ("err", "start")
        pats.append(p)
    if pats[0] != START:
        return ("err", "start")
    if pats[-1] != STOP:
        return ("err", "stop")
    vals = []
    for k in range(1, len(pats) - 1):
        idx = PATS.index(pats[k])
        if idx >= 16:
            return ("err", "symbol %d" % k)
        vals.append(idx)
    data, chk = vals[:-1], vals[-1]
    if sum(weight(i) * v for i, v in enumerate(data)) % 16 != chk:
        return ("err", "check")
    return ("ok", "".join(ALPHA[v] for v in data))


def decode(bars):
    if any(c not in "#." for c in bars):
        return "error: char"
    s = bars.strip(".")
    if s == "":
        return "error: empty"
    runs = runs_of(s)
    if any(r != 1 and r != W for r in runs):
        return "error: width"
    if len(runs) % 6 != 1 or len(runs) < 25:
        return "error: structure"
    res = attempt(s)
    if BOTH and res[0] == "err" and res[1] in ("terminator", "start"):
        rev = attempt(s[::-1])
        if rev[0] == "ok" or rev[1] not in ("terminator", "start"):
            res = rev
    return res[1] if res[0] == "ok" else "error: " + res[1]


def barcode(op, text):
    if op == "encode":
        return encode(text)
    if HAS_DECODE and op == "decode":
        return decode(text)
    return "error: op"
'''

RS = r'''
const ALPHA: &str = "@ALPHA@";
const W: usize = @W@;
const WEIGHT: &str = "@WEIGHT@";
const SWAP: bool = @SWAP@;
const HAS_DECODE: bool = @DECODE@;
const BOTH: bool = @BOTH@;

fn pats() -> Vec<u32> {
    (0u32..64).filter(|p| p.count_ones() == 3).collect()
}

fn weight(i: usize) -> usize {
    match WEIGHT {
        "inc" => i + 1,
        "odd" => 2 * i + 1,
        _ => if i % 2 == 0 { 1 } else { 3 },
    }
}

fn start_stop() -> (u32, u32) {
    let p = pats();
    if SWAP { (p[17], p[16]) } else { (p[16], p[17]) }
}

fn sym_bars(p: u32) -> String {
    let mut out = String::new();
    for j in 0..6 {
        let bit = (p >> (5 - j)) & 1;
        let ch = if j % 2 == 0 { '#' } else { '.' };
        let n = if bit == 1 { W } else { 1 };
        for _ in 0..n {
            out.push(ch);
        }
    }
    out
}

fn encode(text: &str) -> String {
    let chars: Vec<char> = text.chars().collect();
    if chars.is_empty() || chars.len() > 20 {
        return "error: length".to_string();
    }
    let alpha: Vec<char> = ALPHA.chars().collect();
    let mut vals = Vec::new();
    for c in &chars {
        match alpha.iter().position(|a| a == c) {
            Some(v) => vals.push(v),
            None => return format!("error: char {}", c),
        }
    }
    let chk = vals.iter().enumerate().map(|(i, v)| weight(i) * v).sum::<usize>() % 16;
    let p = pats();
    let (start, stop) = start_stop();
    let mut syms = vec![start];
    for v in &vals {
        syms.push(p[*v]);
    }
    syms.push(p[chk]);
    syms.push(stop);
    let mut out: String = syms.iter().map(|s| sym_bars(*s)).collect();
    out.push('#');
    out
}

fn runs_of(s: &[u8]) -> Vec<usize> {
    let mut runs = Vec::new();
    let mut i = 0;
    while i < s.len() {
        let mut j = i;
        while j < s.len() && s[j] == s[i] {
            j += 1;
        }
        runs.push(j - i);
        i = j;
    }
    runs
}

fn attempt(s: &[u8]) -> Result<String, String> {
    let runs = runs_of(s);
    if *runs.last().unwrap() != 1 {
        return Err("terminator".to_string());
    }
    let p = pats();
    let (start, stop) = start_stop();
    let mut got: Vec<u32> = Vec::new();
    let mut k = 0;
    let mut idx = 0;
    while idx < runs.len() - 1 {
        let mut v = 0u32;
        for r in &runs[idx..idx + 6] {
            v = v * 2 + if *r == W { 1 } else { 0 };
        }
        if !p.contains(&v) {
            return Err(if k > 0 { format!("symbol {}", k) } else { "start".to_string() });
        }
        got.push(v);
        idx += 6;
        k += 1;
    }
    if got[0] != start {
        return Err("start".to_string());
    }
    if *got.last().unwrap() != stop {
        return Err("stop".to_string());
    }
    let mut vals: Vec<usize> = Vec::new();
    for k in 1..got.len() - 1 {
        let ix = p.iter().position(|x| *x == got[k]).unwrap();
        if ix >= 16 {
            return Err(format!("symbol {}", k));
        }
        vals.push(ix);
    }
    let chk = vals.pop().unwrap();
    let sum: usize = vals.iter().enumerate().map(|(i, v)| weight(i) * v).sum();
    if sum % 16 != chk {
        return Err("check".to_string());
    }
    let alpha: Vec<char> = ALPHA.chars().collect();
    Ok(vals.iter().map(|v| alpha[*v]).collect())
}

fn decode(bars: &str) -> String {
    if bars.chars().any(|c| c != '#' && c != '.') {
        return "error: char".to_string();
    }
    let s: &str = bars.trim_matches('.');
    if s.is_empty() {
        return "error: empty".to_string();
    }
    let b = s.as_bytes();
    let runs = runs_of(b);
    if runs.iter().any(|r| *r != 1 && *r != W) {
        return "error: width".to_string();
    }
    if runs.len() % 6 != 1 || runs.len() < 25 {
        return "error: structure".to_string();
    }
    let mut res = attempt(b);
    if BOTH {
        if let Err(e) = &res {
            if e == "terminator" || e == "start" {
                let rb: Vec<u8> = b.iter().rev().cloned().collect();
                let rev = attempt(&rb);
                let take = match &rev {
                    Ok(_) => true,
                    Err(e2) => e2 != "terminator" && e2 != "start",
                };
                if take {
                    res = rev;
                }
            }
        }
    }
    match res {
        Ok(t) => t,
        Err(e) => format!("error: {}", e),
    }
}

/// Encodes or decodes a barcode.
pub fn barcode(op: &str, text: &str) -> String {
    if op == "encode" {
        return encode(text);
    }
    if HAS_DECODE && op == "decode" {
        return decode(text);
    }
    "error: op".to_string()
}
'''

GO = r'''
package barcode

import (
	"fmt"
	"math/bits"
	"strings"
)

const (
	alpha     = "@ALPHA@"
	w         = @W@
	weightK   = "@WEIGHT@"
	swap      = @SWAP@
	hasDecode = @DECODE@
	both      = @BOTH@
)

func pats() []int {
	var p []int
	for i := 0; i < 64; i++ {
		if bits.OnesCount(uint(i)) == 3 {
			p = append(p, i)
		}
	}
	return p
}

func weight(i int) int {
	switch weightK {
	case "inc":
		return i + 1
	case "odd":
		return 2*i + 1
	}
	if i%2 == 0 {
		return 1
	}
	return 3
}

func startStop() (int, int) {
	p := pats()
	if swap {
		return p[17], p[16]
	}
	return p[16], p[17]
}

func symBars(p int) string {
	var sb strings.Builder
	for j := 0; j < 6; j++ {
		bit := (p >> (5 - j)) & 1
		ch := "#"
		if j%2 == 1 {
			ch = "."
		}
		n := 1
		if bit == 1 {
			n = w
		}
		sb.WriteString(strings.Repeat(ch, n))
	}
	return sb.String()
}

func encode(text string) string {
	if len(text) < 1 || len(text) > 20 {
		return "error: length"
	}
	vals := make([]int, 0, len(text))
	for i := 0; i < len(text); i++ {
		v := strings.IndexByte(alpha, text[i])
		if v < 0 {
			return "error: char " + string(text[i])
		}
		vals = append(vals, v)
	}
	sum := 0
	for i, v := range vals {
		sum += weight(i) * v
	}
	p := pats()
	start, stop := startStop()
	syms := []int{start}
	for _, v := range vals {
		syms = append(syms, p[v])
	}
	syms = append(syms, p[sum%16], stop)
	var sb strings.Builder
	for _, s := range syms {
		sb.WriteString(symBars(s))
	}
	sb.WriteString("#")
	return sb.String()
}

func runsOf(s string) []int {
	var runs []int
	for i := 0; i < len(s); {
		j := i
		for j < len(s) && s[j] == s[i] {
			j++
		}
		runs = append(runs, j-i)
		i = j
	}
	return runs
}

func attempt(s string) (string, string) {
	runs := runsOf(s)
	if runs[len(runs)-1] != 1 {
		return "", "terminator"
	}
	p := pats()
	start, stop := startStop()
	var got []int
	for idx, k := 0, 0; idx < len(runs)-1; idx, k = idx+6, k+1 {
		v := 0
		for _, r := range runs[idx : idx+6] {
			v *= 2
			if r == w {
				v++
			}
		}
		found := false
		for _, x := range p {
			if x == v {
				found = true
			}
		}
		if !found {
			if k > 0 {
				return "", fmt.Sprintf("symbol %d", k)
			}
			return "", "start"
		}
		got = append(got, v)
	}
	if got[0] != start {
		return "", "start"
	}
	if got[len(got)-1] != stop {
		return "", "stop"
	}
	var vals []int
	for k := 1; k < len(got)-1; k++ {
		ix := -1
		for i, x := range p {
			if x == got[k] {
				ix = i
			}
		}
		if ix >= 16 {
			return "", fmt.Sprintf("symbol %d", k)
		}
		vals = append(vals, ix)
	}
	chk := vals[len(vals)-1]
	vals = vals[:len(vals)-1]
	sum := 0
	for i, v := range vals {
		sum += weight(i) * v
	}
	if sum%16 != chk {
		return "", "check"
	}
	var sb strings.Builder
	for _, v := range vals {
		sb.WriteByte(alpha[v])
	}
	return sb.String(), ""
}

func reverse(s string) string {
	b := []byte(s)
	for i, j := 0, len(b)-1; i < j; i, j = i+1, j-1 {
		b[i], b[j] = b[j], b[i]
	}
	return string(b)
}

func decode(bars string) string {
	if strings.Trim(bars, "#.") != "" {
		return "error: char"
	}
	s := strings.Trim(bars, ".")
	if s == "" {
		return "error: empty"
	}
	runs := runsOf(s)
	for _, r := range runs {
		if r != 1 && r != w {
			return "error: width"
		}
	}
	if len(runs)%6 != 1 || len(runs) < 25 {
		return "error: structure"
	}
	text, code := attempt(s)
	if both && code != "" && (code == "terminator" || code == "start") {
		t2, c2 := attempt(reverse(s))
		if c2 == "" || (c2 != "terminator" && c2 != "start") {
			text, code = t2, c2
		}
	}
	if code != "" {
		return "error: " + code
	}
	return text
}

// Barcode encodes or decodes a barcode.
func Barcode(op, text string) string {
	if op == "encode" {
		return encode(text)
	}
	if hasDecode && op == "decode" {
		return decode(text)
	}
	return "error: op"
}
'''

CC = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "barcode.h"

#define ALPHA "@ALPHA@"
#define W @W@
#define WEIGHT_KIND @WEIGHTK@
#define SWAP @SWAP@
#define HAS_DECODE @DECODE@
#define BOTH @BOTH@

static int PATS[20];

static void init_pats(void) {
    int n = 0;
    for (int p = 0; p < 64; p++) {
        int c = 0;
        for (int b = 0; b < 6; b++) c += (p >> b) & 1;
        if (c == 3) PATS[n++] = p;
    }
}

static int weight(int i) {
    if (WEIGHT_KIND == 0) return i + 1;
    if (WEIGHT_KIND == 1) return 2 * i + 1;
    return i % 2 == 0 ? 1 : 3;
}

static char *dupstr(const char *s) {
    char *r = malloc(strlen(s) + 1);
    strcpy(r, s);
    return r;
}

static int sym_bars(int p, char *out) {
    int n = 0;
    for (int j = 0; j < 6; j++) {
        int bit = (p >> (5 - j)) & 1;
        int cnt = bit ? W : 1;
        for (int k = 0; k < cnt; k++) out[n++] = (j % 2 == 0) ? '#' : '.';
    }
    return n;
}

static char *encode(const char *text) {
    size_t len = strlen(text);
    if (len < 1 || len > 20) return dupstr("error: length");
    int vals[20];
    for (size_t i = 0; i < len; i++) {
        const char *q = strchr(ALPHA, text[i]);
        if (!q || text[i] == 0) {
            char buf[32];
            sprintf(buf, "error: char %c", text[i]);
            return dupstr(buf);
        }
        vals[i] = (int)(q - ALPHA);
    }
    int sum = 0;
    for (size_t i = 0; i < len; i++) sum += weight((int)i) * vals[i];
    int start = SWAP ? PATS[17] : PATS[16];
    int stop = SWAP ? PATS[16] : PATS[17];
    char *out = malloc((len + 3) * 6 * W + 8);
    int n = 0;
    n += sym_bars(start, out + n);
    for (size_t i = 0; i < len; i++) n += sym_bars(PATS[vals[i]], out + n);
    n += sym_bars(PATS[sum % 16], out + n);
    n += sym_bars(stop, out + n);
    out[n++] = '#';
    out[n] = 0;
    return out;
}

/* returns 0 on success (text filled) or an error code string in *err */
static int attempt(const char *s, size_t len, char *text, char *err) {
    int runs[1024];
    int nr = 0;
    for (size_t i = 0; i < len;) {
        size_t j = i;
        while (j < len && s[j] == s[i]) j++;
        runs[nr++] = (int)(j - i);
        i = j;
    }
    int start = SWAP ? PATS[17] : PATS[16];
    int stop = SWAP ? PATS[16] : PATS[17];
    if (runs[nr - 1] != 1) { strcpy(err, "terminator"); return 1; }
    int got[256];
    int ng = 0;
    for (int idx = 0, k = 0; idx < nr - 1; idx += 6, k++) {
        int v = 0;
        for (int r = 0; r < 6; r++) v = v * 2 + (runs[idx + r] == W ? 1 : 0);
        int found = 0;
        for (int x = 0; x < 20; x++) if (PATS[x] == v) found = 1;
        if (!found) {
            if (k > 0) sprintf(err, "symbol %d", k); else strcpy(err, "start");
            return 1;
        }
        got[ng++] = v;
    }
    if (got[0] != start) { strcpy(err, "start"); return 1; }
    if (got[ng - 1] != stop) { strcpy(err, "stop"); return 1; }
    int vals[256];
    int nv = 0;
    for (int k = 1; k < ng - 1; k++) {
        int ix = -1;
        for (int x = 0; x < 20; x++) if (PATS[x] == got[k]) ix = x;
        if (ix >= 16) { sprintf(err, "symbol %d", k); return 1; }
        vals[nv++] = ix;
    }
    int chk = vals[nv - 1];
    nv--;
    int sum = 0;
    for (int i = 0; i < nv; i++) sum += weight(i) * vals[i];
    if (sum % 16 != chk) { strcpy(err, "check"); return 1; }
    for (int i = 0; i < nv; i++) text[i] = ALPHA[vals[i]];
    text[nv] = 0;
    return 0;
}

static char *decode(const char *bars) {
    size_t n = strlen(bars);
    for (size_t i = 0; i < n; i++)
        if (bars[i] != '#' && bars[i] != '.') return dupstr("error: char");
    size_t a = 0, b = n;
    while (a < b && bars[a] == '.') a++;
    while (b > a && bars[b - 1] == '.') b--;
    if (a == b) return dupstr("error: empty");
    size_t len = b - a;
    char *s = malloc(len + 1);
    memcpy(s, bars + a, len);
    s[len] = 0;
    /* runs, for the width and structure checks */
    int nr = 0;
    for (size_t i = 0; i < len;) {
        size_t j = i;
        while (j < len && s[j] == s[i]) j++;
        int r = (int)(j - i);
        if (r != 1 && r != W) { free(s); return dupstr("error: width"); }
        nr++;
        i = j;
    }
    if (nr % 6 != 1 || nr < 25) { free(s); return dupstr("error: structure"); }
    char text[512], err[64];
    int bad = attempt(s, len, text, err);
    if (BOTH && bad && (strcmp(err, "terminator") == 0 || strcmp(err, "start") == 0)) {
        char *rv = malloc(len + 1);
        for (size_t i = 0; i < len; i++) rv[i] = s[len - 1 - i];
        rv[len] = 0;
        char text2[512], err2[64];
        int bad2 = attempt(rv, len, text2, err2);
        free(rv);
        if (!bad2 || (strcmp(err2, "terminator") != 0 && strcmp(err2, "start") != 0)) {
            bad = bad2;
            strcpy(text, text2);
            strcpy(err, err2);
        }
    }
    free(s);
    if (bad) {
        char buf[96];
        sprintf(buf, "error: %s", err);
        return dupstr(buf);
    }
    return dupstr(text);
}

char *barcode(const char *op, const char *text) {
    init_pats();
    if (strcmp(op, "encode") == 0) return encode(text);
    if (HAS_DECODE && strcmp(op, "decode") == 0) return decode(text);
    return dupstr("error: op");
}
'''


def _b(lang, v):
    if lang == "python":
        return "True" if v else "False"
    if lang == "c":
        return "1" if v else "0"
    return "true" if v else "false"


def sol(lang, p):
    src = {"python": PY, "rust": RS, "go": GO, "c": CC}[lang]
    return K.subst(src, ALPHA=p["alpha"], W=p["w"], WEIGHT=p["weight"], WEIGHTK={"inc": 0, "odd": 1, "alt": 2}[p["weight"]], SWAP=_b(lang, p["swap"]),
                   DECODE=_b(lang, p["decode"]), BOTH=_b(lang, p["both"])).lstrip("\n")


# ---------------------------------------------------------------------------------------------------------------

def readme(p, api, lang, examples):
    W = p["w"]
    wt = {"inc": "`i + 1`", "odd": "`2*i + 1`", "alt": "1 for even `i` and 3 for odd `i`"}[p["weight"]]
    L = [f"# {p['name']}: a small bar code", ""]
    L.append(f"{p['name']} is the symbology printed on the parcel tags of a river ferry company. A code is a string of `#` (bar modules) and `.` (space modules). "
             "The tool encodes text into such a string" + (" and decodes it back" if p["decode"] else "") + ".")
    L.append("")
    L.append("## Symbols")
    L.append("")
    L.append("* The **data alphabet** has 16 characters; the value of a character is its position (0-15) in this string: `" + p["alpha"] + "`.")
    L.append("* A **symbol** is made of 6 *elements*, alternating bar, space, bar, space, bar, space (it starts with a bar and ends with a space). Each element is either "
             f"*narrow* (1 module) or *wide* ({W} modules). A symbol's **pattern** says which elements are wide: a 6-bit number whose most significant bit belongs to the first element (1 = wide). "
             "So the pattern `100101` is a wide bar, narrow space, narrow bar, wide space, narrow bar, wide space.")
    L.append("* Only patterns with exactly three wide elements (three 1 bits) are valid. Number the valid patterns 0, 1, 2, ... in increasing numeric order (there are 20: `000111` is number 0, `001011` is number 1, ..., `111000` is number 19). "
             "Pattern number `v` (0-15) is the symbol of the data character with value `v`. Pattern number " + ("17" if p["swap"] else "16") + " is the **START** symbol and number " + ("16" if p["swap"] else "17") + " is the **STOP** symbol; numbers 18 and 19 are never used.")
    L.append("")
    L.append("## Layout of a code")
    L.append("")
    L.append("START, then one symbol per data character, then one **check** symbol, then STOP, all written one after the other with no gaps, and finally one single `#` module (the *terminator*). "
             "The code therefore always begins and ends with a bar.")
    L.append("")
    L.append(f"**Check symbol**: take the values `v0, v1, ...` of the data characters in order, compute `s = sum(v_i * weight(i))` where `weight(i)` is {wt} (`i` counts from 0), and use the symbol of pattern number `s mod 16` "
             "(a *data* symbol: its value is `s mod 16`).")
    L.append("")
    L.append("## Operations")
    L.append("")
    L.append("`barcode(op, text)` dispatches on `op` (an exact word):")
    L.append("")
    L.append("* **`encode`**: `text` is the data (1 to 20 characters, every character from the alphabet; matching is case-sensitive). The result is the code. "
             "If the length is not between 1 and 20 the result is `error: length` (this is checked first); otherwise the first character that is not in the alphabet gives `error: char X` (with that character as `X`).")
    if p["decode"]:
        L.append("* **`decode`**: `text` is a code; the result is the data text without START, check and STOP, or one of these errors, checked **in this order**:")
        L.append("")
        steps = [
            "`error: char`: some character is neither `#` nor `.`;",
            "then leading and trailing `.` characters (the quiet zone around a printed code) are removed; if nothing is left: `error: empty`;",
            f"the rest is cut into *runs* (maximal groups of equal characters; the first run is a bar run). If any run is not exactly 1 or {W} modules long: `error: width`;",
            "if the number of runs is not of the form `6k + 1` or is less than 25 (START, one data symbol, check, STOP and the terminator need 25): `error: structure`;",
        ]
        n = 5
        if p["both"]:
            pass
        for s_ in steps:
            L.append(f"1. {s_}")
        L.append("")
        L.append("Then the code is read symbol by symbol (the first 6 runs, the next 6, ..., leaving the last run for the terminator), each group of 6 runs becoming a pattern (wide = 1). "
                 "The **reading checks**, in order, report the first failure:")
        L.append("")
        L.append("1. `error: terminator`: the last run is not exactly 1 module long;")
        L.append("2. any group whose pattern is not one of the 20 valid patterns: `error: start` if it is the very first group, otherwise `error: symbol K` (`K` counts the groups from 0, START being group 0) for the first such group;")
        L.append("3. the first group is not START: `error: start`;")
        L.append("4. the last group is not STOP: `error: stop`;")
        L.append("5. any group between START and STOP that is not a data symbol (pattern number 16 to 19): `error: symbol K` for the first such group;")
        L.append("6. the check symbol (the last data-type group before STOP) does not match the data: `error: check`.")
        L.append("")
        if p["both"]:
            L.append("**Reading backwards.** A tag may be scanned upside down. Do the width and structure checks as above (they do not depend on direction), then apply the reading checks to the code as given. "
                     "If that fails with `terminator` or `start` (the code does not look like a forward code), apply the same reading checks to the *reversed* string (the characters in reverse order; the trimmed code starts and ends with a bar, so the reversed string "
                     "is again a candidate). If the reversed reading does **not** fail with `terminator` or `start`, its result (the data text or its error, with `K` counted in the reversed reading) is the result; otherwise the result is the error of the forward reading. "
                     "A code that reads correctly forwards is never reversed.")
        else:
            L.append("The code is only read in the given direction.")
        L.append("")
    L.append("Any other `op` (including `decode` when it is not offered here) gives `error: op`.")
    L.append("")
    L.append(K.interface_section(api, lang))
    L.append("## Examples")
    L.append("")
    L.append("| op | text | result |")
    L.append("|---|---|---|")
    for (op, text), out in examples:
        L.append(f"| `{op}` | `{text}` | `{out}` |")
    L.append("")
    L.append(K.run_hint(lang, api.mod))
    return "\n".join(L) + "\n"


def make_cases(rng, p, ns):
    alpha = p["alpha"]
    W = p["w"]
    barcode = ns["barcode"]
    cases = []

    def add(op, t):
        cases.append((op, t))

    def rtext(n=None):
        n = n or rng.randrange(1, 12)
        return "".join(rng.choice(alpha) for _ in range(n))

    t0 = rtext(4)
    add("encode", t0)
    t1 = rtext(8)
    add("encode", t1)
    if p["decode"]:
        add("decode", barcode("encode", rtext(5)))
    else:
        add("encode", alpha[0])
    nex = len(cases)
    for n in (1, 2, 3, 5, 6, 7, 9, 10, 15, 19, 20):
        add("encode", rtext(n))
    add("encode", alpha)
    add("encode", alpha + alpha[:4])
    add("encode", alpha[::-1])
    add("encode", alpha[0] * 20)
    add("encode", alpha[15] * 20)
    add("encode", "")
    add("encode", alpha[0] * 21)
    add("encode", alpha[0] * 40)
    add("encode", rtext(3) + "a" + rtext(2))
    add("encode", "a")
    add("encode", " ")
    add("encode", rtext(3) + " ")
    c_out = [c for c in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-$/+%:abc.# " if c not in alpha]
    for c in c_out[:6]:
        add("encode", rtext(2) + c + rtext(2))
    if len(c_out) >= 2:
        add("encode", c_out[0] + c_out[1])
        add("encode", rtext(1) + c_out[1] + c_out[0])
    add("encode", rtext(21) + "~")
    add("encode", alpha[3] * 25 + "~")
    for op in ("Encode", "ENCODE", "enc", "", "encode ", "decode" if not p["decode"] else "verify"):
        add(op, t0)
    if not p["decode"]:
        add("decode", barcode("encode", t0))
        add("decode", "#.#.#")
    if p["decode"]:
        goods = [rtext(n) for n in (1, 2, 4, 7, 12, 20)] + [alpha, alpha[::-1]]
        for g in goods:
            enc = barcode("encode", g)
            add("decode", enc)
            add("decode", "..." + enc + ".")
            if p["both"]:
                add("decode", enc[::-1])
                add("decode", ".." + enc[::-1] + "....")
        for g in goods[:3]:
            enc = barcode("encode", g)
            # flip single modules
            pos = sorted(rng.sample(range(len(enc)), min(8, len(enc))))
            for k in pos:
                flipped = enc[:k] + ("." if enc[k] == "#" else "#") + enc[k + 1:]
                add("decode", flipped)
            # delete / insert modules
            k = rng.randrange(1, len(enc) - 1)
            add("decode", enc[:k] + enc[k + 1:])
            add("decode", enc[:k] + enc[k] + enc[k:])
            add("decode", enc[:-1])
            add("decode", enc[1:])
            add("decode", enc + "#")
            add("decode", enc + ".#")
            add("decode", enc[:6 * 4])
            add("decode", enc[:-6])
            add("decode", enc.replace("#", "#.", 1))
        # structured errors
        runs_ok = ns["runs_of"](barcode("encode", rtext(3)))
        add("decode", "")
        add("decode", ".")
        add("decode", "......")
        add("decode", "#")
        add("decode", "##")
        add("decode", "#.")
        add("decode", ".#.")
        add("decode", "#.#.#.#")
        add("decode", "#" * 3 if W != 3 else "#" * 4)
        add("decode", "#" * (W + 1) + "." + "#" * W)
        add("decode", "x")
        add("decode", "#.#x#")
        add("decode", "# . #")
        add("decode", barcode("encode", t0) + "\n")
        add("decode", " " + barcode("encode", t0))
        add("decode", barcode("encode", t0).replace("#", "1").replace(".", "0"))
        add("decode", barcode("encode", t0).lower())
        add("decode", "#.".join(["#"] * 6))
        # bad symbols: build from pattern lists
        pats = ns["PATS"]
        start, stop = ns["START"], ns["STOP"]
        sym = ns["sym_bars"]

        def build(plist, term="#"):
            return "".join(sym(x) for x in plist) + term

        v = [alpha.index(c) for c in rtext(3)]
        chk = sum(ns["weight"](i) * x for i, x in enumerate(v)) % 16
        good = [start] + [pats[x] for x in v] + [pats[chk], stop]
        add("decode", build(good))
        add("decode", build(good, "#") + "." * 3)
        for k in range(len(good)):
            for repl in (pats[18], pats[19], start, stop, 0b110110, 0b000001, 0b111111, 0b010101):
                if repl == good[k]:
                    continue
                g2 = list(good)
                g2[k] = repl
                add("decode", build(g2))
        g2 = list(good)
        g2[0], g2[-1] = g2[-1], g2[0]
        add("decode", build(g2))
        add("decode", build(good[1:] + [stop]))
        add("decode", build(good[:-1] + [start]))
        add("decode", build([start, pats[3], stop]))
        add("decode", build([start, pats[3], pats[3], stop]))
        add("decode", build([start] + [pats[2]] * 3 + [stop]))
        add("decode", build([start, pats[chk if False else 0], stop, pats[0], stop]))
        g3 = list(good)
        g3[2] = pats[(v[1] + 1) % 16]
        add("decode", build(g3))
        for tm in ("##", "#.", "###", "." * 2):
            add("decode", "".join(sym(x) for x in good) + tm)
        # wrong check
        for delta in range(1, 16, 4):
            g4 = list(good)
            g4[-2] = pats[(chk + delta) % 16]
            add("decode", build(g4))
        if p["both"]:
            for g in (good,):
                enc = build(g)
                add("decode", enc[::-1])
                g2 = list(good)
                g2[2] = pats[18]
                add("decode", build(g2)[::-1])
                g2 = list(good)
                g2[-2] = pats[(chk + 1) % 16]
                add("decode", build(g2)[::-1])
                g2 = list(good)
                g2[0] = pats[18]
                add("decode", build(g2)[::-1])
                g2 = list(good)
                g2[-1] = pats[5]
                add("decode", build(g2)[::-1])
                add("decode", build([stop, pats[1], pats[1], start])[::-1])
                add("decode", build([stop] + good[1:-1] + [start]))
                add("decode", build([stop] + good[1:-1] + [start])[::-1])
                add("decode", enc[::-1][:-1])
                add("decode", enc[::-1] + "#")
            # palindromic-ish ambiguity: START/STOP swapped
            add("decode", build([stop] + good[1:-1] + [start]))
            for _ in range(6):
                t = rtext(rng.randrange(1, 9))
                enc = barcode("encode", t)
                k = rng.randrange(len(enc))
                bad = enc[:k] + ("." if enc[k] == "#" else "#") + enc[k + 1:]
                add("decode", bad[::-1])
        else:
            for g in goods[:3]:
                add("decode", barcode("encode", g)[::-1])
        for _ in range(8):
            t = rtext(rng.randrange(1, 9))
            enc = barcode("encode", t)
            k = rng.randrange(len(enc))
            add("decode", enc[:k] + ("." if enc[k] == "#" else "#") + enc[k + 1:])
    out, seen = [], set()
    for c in cases:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out, nex


def prompt(rng, p, api, lang):
    where = api.where(lang)
    fn = api.name(lang)
    ln = K.LANG_NAME[lang]
    dec = "encoder and decoder" if p["decode"] else "encoder"
    opts = [
        f"The ferry company's parcel tags use a bar code of their own design, {p['name']}. Please write the {dec} in {ln}: `{fn}(op, text)` in {where}. README.md describes the symbols, the check symbol and every error text. {K.closer(rng)}",
        f"Implement `{fn}` ({ln}, {where}) following README.md: it turns text into a string of `#` and `.` modules" + (" and back, rejecting damaged codes with precise errors" if p["decode"] else "") + f". The pattern table is not listed in the README, you have to derive it from the rule. {K.closer(rng)}",
        f"{ln} task: {p['name']} bar code {dec}. spec: README.md; code goes in {where}; single entry point `{fn}`. watch the weights of the check symbol" + (" and the order of the decode errors" if p["decode"] else "") + ".",
        f"Build the {p['name']} {dec} described in README.md ({ln}). Entry point `{fn}` in {where}. Hidden checks go through every error path."
        if p["decode"] else f"Build the {p['name']} encoder described in README.md ({ln}). Entry point `{fn}` in {where}. Hidden checks cover each character class and the length limits.",
    ]
    return rng.choice(opts).strip()


@family("greenfield-barcode", category="greenfield", lang="mixed", kind="greenfield", n=10,
        summary="invented wide/narrow bar-code symbology: derived pattern table, weighted check symbol, decoding with ordered errors and backwards reading")
def gen(rng, n):
    levels = [2, 3, 3, 4, 4, 3, 4, 2, 4, 3]
    diffs = [2, 3, 3, 4, 4, 3, 4, 2, 5, 3]
    for i in range(n):
        lang = LANG_PLAN[i % len(LANG_PLAN)]
        level = levels[i % len(levels)]
        p = params(rng, level, i)
        api = K.Api(mod="barcode", fn="barcode", args=["op", "text"],
                    arg_docs=["the operation: `encode`" + (" or `decode`" if p["decode"] else ""), "the data text (for `encode`) or the code string (for `decode`)"],
                    ret_doc="the code, the data, or an `error: ...` text", doc="bar code encoder/decoder")
        py_src = sol("python", p)
        ns = K.py_namespace(py_src)
        cases, nex = make_cases(rng, p, ns)
        sols = {lang: sol(lang, p), "python": py_src}
        examples = [(c, ns["barcode"](*c)) for c in cases[:nex]]
        rd = readme(p, api, lang, examples)
        yield K.lib_task(
            api=api, lang=lang, readme=rd, solutions=sols, cases=cases, examples=nex, prompt=prompt(rng, p, api, lang),
            difficulty=diffs[i % len(diffs)], slug=f"{i + 1:02d}-{lang}-{p['name'].lower().replace(' ', '-')}-w{p['w']}-l{level}",
            oracle=(None if lang == "python" else ns["barcode"]), tags=["encoding", "checksum"],
            notes={"level": level, "w": p["w"], "weight": p["weight"], "swap": p["swap"]},
        )
