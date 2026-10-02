"""Release versions with ordered pre-release channels: validate, compare, bump, graduate (invented precedence rules)."""
from __future__ import annotations

from fx import family

from generators.greenfield import _kit as K

CHANNELS = [["alpha", "beta", "rc"], ["dawn", "noon", "dusk"], ["spark", "flame", "blaze", "ember"], ["nightly", "preview", "candidate"], ["moss", "fern", "oak"], ["ice", "dew", "rain", "storm"]]
PROJECTS = ["the Quillfeather client", "the Saltmarsh toolkit", "the tide-clock firmware", "the lighthouse dashboard", "the Hollin planner", "the ferry booking SDK"]
LANG_PLAN = ["javascript", "rust", "go", "ruby", "javascript", "rust", "go", "ruby", "javascript", "rust"]


def params(rng, level, i):
    ch = CHANNELS[(i + rng.randrange(2)) % len(CHANNELS)]
    return {"level": level, "project": rng.choice(PROJECTS), "channels": ch, "bump": level >= 2, "pre": level >= 3, "maxn": rng.choice([99, 999, 9999])}


PY = r'''
CHANNELS = @CH_PY@
HAS_BUMP = @BUMP@
HAS_PRE = @PRE@
MAXN = @MAXN@
DG = "0123456789"


def num(s):
    if not (1 <= len(s) <= len(str(MAXN))) or not all(c in DG for c in s) or (len(s) > 1 and s[0] == "0"):
        return None
    v = int(s)
    return v if v <= MAXN else None


def parse(v):
    """(major, minor, patch, channel_index or None, n or None) or None"""
    main, dash, pre = v.partition("-")
    parts = main.split(".")
    if len(parts) != 3:
        return None
    nums = [num(p) for p in parts]
    if None in nums:
        return None
    if not dash:
        return (nums[0], nums[1], nums[2], None, None)
    ch, dot, n = pre.partition(".")
    if not dot or ch not in CHANNELS:
        return None
    nn = num(n)
    if nn is None or nn < 1:
        return None
    return (nums[0], nums[1], nums[2], CHANNELS.index(ch), nn)


def text(t):
    s = "%d.%d.%d" % t[:3]
    if t[3] is not None:
        s += "-%s.%d" % (CHANNELS[t[3]], t[4])
    return s


def key(t):
    return (t[0], t[1], t[2], 1 if t[3] is None else 0, -1 if t[3] is None else t[3], 0 if t[4] is None else t[4])


def release(version, command):
    cur = parse(version)
    if cur is None:
        return "error: version"
    w = command.split(" ")
    if command == "check":
        return "ok"
    if len(w) == 2 and w[0] == "cmp":
        other = parse(w[1])
        if other is None:
            return "error: other"
        a, b = key(cur), key(other)
        return "less" if a < b else "greater" if a > b else "equal"
    if HAS_BUMP and command in ("major", "minor", "patch"):
        m, n, p = cur[0], cur[1], cur[2]
        if command == "major":
            m, n, p = m + 1, 0, 0
        elif command == "minor":
            n, p = n + 1, 0
        elif cur[3] is None:
            p += 1
        if m > MAXN or n > MAXN or p > MAXN:
            return "error: overflow"
        return text((m, n, p, None, None))
    if HAS_PRE and command == "release":
        if cur[3] is None:
            return "error: not a prerelease"
        return text(cur[:3] + (None, None))
    if HAS_PRE and len(w) == 2 and w[0] == "pre":
        if w[1] not in CHANNELS:
            return "error: channel"
        ci = CHANNELS.index(w[1])
        if cur[3] is None:
            if cur[2] + 1 > MAXN:
                return "error: overflow"
            return text((cur[0], cur[1], cur[2] + 1, ci, 1))
        if ci < cur[3]:
            return "error: downgrade"
        if ci == cur[3]:
            if cur[4] + 1 > MAXN:
                return "error: overflow"
            return text(cur[:3] + (ci, cur[4] + 1))
        return text(cur[:3] + (ci, 1))
    return "error: command"
'''

JS = r'''
'use strict';

const CHANNELS = @CH_JS@;
const HAS_BUMP = @BUMP@;
const HAS_PRE = @PRE@;
const MAXN = @MAXN@;
const DG = '0123456789';

function num(s) {
  if (!(s.length >= 1 && s.length <= String(MAXN).length) || ![...s].every((c) => DG.includes(c)) || (s.length > 1 && s[0] === '0')) return null;
  const v = parseInt(s, 10);
  return v <= MAXN ? v : null;
}

function parse(v) {
  const di = v.indexOf('-');
  const main = di >= 0 ? v.slice(0, di) : v;
  const parts = main.split('.');
  if (parts.length !== 3) return null;
  const nums = parts.map(num);
  if (nums.includes(null)) return null;
  if (di < 0) return [nums[0], nums[1], nums[2], null, null];
  const pre = v.slice(di + 1);
  const dot = pre.indexOf('.');
  if (dot < 0) return null;
  const ch = pre.slice(0, dot);
  if (!CHANNELS.includes(ch)) return null;
  const nn = num(pre.slice(dot + 1));
  if (nn === null || nn < 1) return null;
  return [nums[0], nums[1], nums[2], CHANNELS.indexOf(ch), nn];
}

function text(t) {
  let s = `${t[0]}.${t[1]}.${t[2]}`;
  if (t[3] !== null) s += `-${CHANNELS[t[3]]}.${t[4]}`;
  return s;
}

function key(t) {
  return [t[0], t[1], t[2], t[3] === null ? 1 : 0, t[3] === null ? -1 : t[3], t[4] === null ? 0 : t[4]];
}

function cmp(a, b) {
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1;
  return 0;
}

function release(version, command) {
  const cur = parse(version);
  if (cur === null) return 'error: version';
  const w = command.split(' ');
  if (command === 'check') return 'ok';
  if (w.length === 2 && w[0] === 'cmp') {
    const other = parse(w[1]);
    if (other === null) return 'error: other';
    const c = cmp(key(cur), key(other));
    return c < 0 ? 'less' : c > 0 ? 'greater' : 'equal';
  }
  if (HAS_BUMP && (command === 'major' || command === 'minor' || command === 'patch')) {
    let [m, n, p] = cur;
    if (command === 'major') { m += 1; n = 0; p = 0; }
    else if (command === 'minor') { n += 1; p = 0; }
    else if (cur[3] === null) p += 1;
    if (m > MAXN || n > MAXN || p > MAXN) return 'error: overflow';
    return text([m, n, p, null, null]);
  }
  if (HAS_PRE && command === 'release') {
    if (cur[3] === null) return 'error: not a prerelease';
    return text([cur[0], cur[1], cur[2], null, null]);
  }
  if (HAS_PRE && w.length === 2 && w[0] === 'pre') {
    if (!CHANNELS.includes(w[1])) return 'error: channel';
    const ci = CHANNELS.indexOf(w[1]);
    if (cur[3] === null) {
      if (cur[2] + 1 > MAXN) return 'error: overflow';
      return text([cur[0], cur[1], cur[2] + 1, ci, 1]);
    }
    if (ci < cur[3]) return 'error: downgrade';
    if (ci === cur[3]) {
      if (cur[4] + 1 > MAXN) return 'error: overflow';
      return text([cur[0], cur[1], cur[2], ci, cur[4] + 1]);
    }
    return text([cur[0], cur[1], cur[2], ci, 1]);
  }
  return 'error: command';
}

module.exports = { release };
'''

RS = r'''
const CHANNELS: &[&str] = &@CH_RS@;
const HAS_BUMP: bool = @BUMP@;
const HAS_PRE: bool = @PRE@;
const MAXN: i64 = @MAXN@;

#[derive(Clone, Copy)]
struct Ver {
    m: i64,
    n: i64,
    p: i64,
    ch: Option<usize>,
    k: i64,
}

fn num(s: &str) -> Option<i64> {
    if s.is_empty() || s.len() > MAXN.to_string().len() || !s.bytes().all(|c| c.is_ascii_digit()) || (s.len() > 1 && s.starts_with('0')) {
        return None;
    }
    let v: i64 = s.parse().ok()?;
    if v <= MAXN { Some(v) } else { None }
}

fn parse(v: &str) -> Option<Ver> {
    let (main, pre) = match v.find('-') {
        Some(i) => (&v[..i], Some(&v[i + 1..])),
        None => (v, None),
    };
    let parts: Vec<&str> = main.split('.').collect();
    if parts.len() != 3 {
        return None;
    }
    let (m, n, p) = (num(parts[0])?, num(parts[1])?, num(parts[2])?);
    match pre {
        None => Some(Ver { m, n, p, ch: None, k: 0 }),
        Some(pre) => {
            let dot = pre.find('.')?;
            let ci = CHANNELS.iter().position(|c| *c == &pre[..dot])?;
            let k = num(&pre[dot + 1..])?;
            if k < 1 {
                return None;
            }
            Some(Ver { m, n, p, ch: Some(ci), k })
        }
    }
}

fn text(t: Ver) -> String {
    match t.ch {
        None => format!("{}.{}.{}", t.m, t.n, t.p),
        Some(c) => format!("{}.{}.{}-{}.{}", t.m, t.n, t.p, CHANNELS[c], t.k),
    }
}

fn key(t: &Ver) -> (i64, i64, i64, i64, i64, i64) {
    (t.m, t.n, t.p, if t.ch.is_none() { 1 } else { 0 }, match t.ch { None => -1, Some(c) => c as i64 }, if t.ch.is_none() { 0 } else { t.k })
}

/// Validates versions, compares and bumps them.
pub fn release(version: &str, command: &str) -> String {
    let cur = match parse(version) {
        Some(c) => c,
        None => return "error: version".to_string(),
    };
    let w: Vec<&str> = command.split(' ').collect();
    if command == "check" {
        return "ok".to_string();
    }
    if w.len() == 2 && w[0] == "cmp" {
        let other = match parse(w[1]) {
            Some(o) => o,
            None => return "error: other".to_string(),
        };
        let (a, b) = (key(&cur), key(&other));
        return if a < b { "less" } else if a > b { "greater" } else { "equal" }.to_string();
    }
    if HAS_BUMP && (command == "major" || command == "minor" || command == "patch") {
        let (mut m, mut n, mut p) = (cur.m, cur.n, cur.p);
        if command == "major" {
            m += 1;
            n = 0;
            p = 0;
        } else if command == "minor" {
            n += 1;
            p = 0;
        } else if cur.ch.is_none() {
            p += 1;
        }
        if m > MAXN || n > MAXN || p > MAXN {
            return "error: overflow".to_string();
        }
        return text(Ver { m, n, p, ch: None, k: 0 });
    }
    if HAS_PRE && command == "release" {
        if cur.ch.is_none() {
            return "error: not a prerelease".to_string();
        }
        return text(Ver { ch: None, k: 0, ..cur });
    }
    if HAS_PRE && w.len() == 2 && w[0] == "pre" {
        let ci = match CHANNELS.iter().position(|c| *c == w[1]) {
            Some(i) => i,
            None => return "error: channel".to_string(),
        };
        return match cur.ch {
            None => {
                if cur.p + 1 > MAXN {
                    "error: overflow".to_string()
                } else {
                    text(Ver { p: cur.p + 1, ch: Some(ci), k: 1, ..cur })
                }
            }
            Some(c) => {
                if ci < c {
                    "error: downgrade".to_string()
                } else if ci == c {
                    if cur.k + 1 > MAXN {
                        "error: overflow".to_string()
                    } else {
                        text(Ver { k: cur.k + 1, ..cur })
                    }
                } else {
                    text(Ver { ch: Some(ci), k: 1, ..cur })
                }
            }
        };
    }
    "error: command".to_string()
}
'''

GO = r'''
package releaser

import (
	"fmt"
	"strconv"
	"strings"
)

const (
	hasBump = @BUMP@
	hasPre  = @PRE@
	maxN    = @MAXN@
)

var channels = @CH_GO@

type ver struct {
	m, n, p int
	ch      int // -1 for none
	k       int
}

func chIndex(s string) int {
	for i, c := range channels {
		if c == s {
			return i
		}
	}
	return -1
}

func num(s string) (int, bool) {
	if len(s) < 1 || len(s) > len(strconv.Itoa(maxN)) || (len(s) > 1 && s[0] == '0') {
		return 0, false
	}
	for i := 0; i < len(s); i++ {
		if s[i] < '0' || s[i] > '9' {
			return 0, false
		}
	}
	v, _ := strconv.Atoi(s)
	return v, v <= maxN
}

func parse(v string) (ver, bool) {
	main, pre, hasPreTxt := strings.Cut(v, "-")
	parts := strings.Split(main, ".")
	if len(parts) != 3 {
		return ver{}, false
	}
	var nums [3]int
	for i, p := range parts {
		x, ok := num(p)
		if !ok {
			return ver{}, false
		}
		nums[i] = x
	}
	t := ver{nums[0], nums[1], nums[2], -1, 0}
	if !hasPreTxt {
		return t, true
	}
	ch, n, dot := strings.Cut(pre, ".")
	ci := chIndex(ch)
	if !dot || ci < 0 {
		return ver{}, false
	}
	k, ok := num(n)
	if !ok || k < 1 {
		return ver{}, false
	}
	t.ch, t.k = ci, k
	return t, true
}

func text(t ver) string {
	s := fmt.Sprintf("%d.%d.%d", t.m, t.n, t.p)
	if t.ch >= 0 {
		s += fmt.Sprintf("-%s.%d", channels[t.ch], t.k)
	}
	return s
}

func key(t ver) [6]int {
	rel, ci, k := 0, t.ch, t.k
	if t.ch < 0 {
		rel, ci, k = 1, -1, 0
	}
	return [6]int{t.m, t.n, t.p, rel, ci, k}
}

func cmp(a, b [6]int) int {
	for i := range a {
		if a[i] != b[i] {
			if a[i] < b[i] {
				return -1
			}
			return 1
		}
	}
	return 0
}

// Release validates versions, compares and bumps them.
func Release(version, command string) string {
	cur, ok := parse(version)
	if !ok {
		return "error: version"
	}
	w := strings.Split(command, " ")
	if command == "check" {
		return "ok"
	}
	if len(w) == 2 && w[0] == "cmp" {
		other, ok := parse(w[1])
		if !ok {
			return "error: other"
		}
		switch c := cmp(key(cur), key(other)); {
		case c < 0:
			return "less"
		case c > 0:
			return "greater"
		}
		return "equal"
	}
	if hasBump && (command == "major" || command == "minor" || command == "patch") {
		m, n, p := cur.m, cur.n, cur.p
		switch {
		case command == "major":
			m, n, p = m+1, 0, 0
		case command == "minor":
			n, p = n+1, 0
		case cur.ch < 0:
			p++
		}
		if m > maxN || n > maxN || p > maxN {
			return "error: overflow"
		}
		return text(ver{m, n, p, -1, 0})
	}
	if hasPre && command == "release" {
		if cur.ch < 0 {
			return "error: not a prerelease"
		}
		cur.ch, cur.k = -1, 0
		return text(cur)
	}
	if hasPre && len(w) == 2 && w[0] == "pre" {
		ci := chIndex(w[1])
		if ci < 0 {
			return "error: channel"
		}
		switch {
		case cur.ch < 0:
			if cur.p+1 > maxN {
				return "error: overflow"
			}
			cur.p++
			cur.ch, cur.k = ci, 1
		case ci < cur.ch:
			return "error: downgrade"
		case ci == cur.ch:
			if cur.k+1 > maxN {
				return "error: overflow"
			}
			cur.k++
		default:
			cur.ch, cur.k = ci, 1
		}
		return text(cur)
	}
	return "error: command"
}
'''

RB = r'''
module Releaser
  CHANNELS = @CH_RB@
  HAS_BUMP = @BUMP@
  HAS_PRE = @PRE@
  MAXN = @MAXN@
  DG = '0123456789'

  def self.num(s)
    return nil if s.length < 1 || s.length > MAXN.to_s.length || !s.each_char.all? { |c| DG.include?(c) } || (s.length > 1 && s[0] == '0')
    v = s.to_i
    v <= MAXN ? v : nil
  end

  def self.parse(v)
    di = v.index('-')
    main = di ? v[0...di] : v
    parts = main.split('.', -1)
    return nil if parts.length != 3
    nums = parts.map { |p| num(p) }
    return nil if nums.include?(nil)
    return [nums[0], nums[1], nums[2], nil, nil] unless di
    pre = v[(di + 1)..]
    dot = pre.index('.')
    return nil unless dot
    ch = pre[0...dot]
    return nil unless CHANNELS.include?(ch)
    nn = num(pre[(dot + 1)..])
    return nil if nn.nil? || nn < 1
    [nums[0], nums[1], nums[2], CHANNELS.index(ch), nn]
  end

  def self.text(t)
    s = "#{t[0]}.#{t[1]}.#{t[2]}"
    s += "-#{CHANNELS[t[3]]}.#{t[4]}" unless t[3].nil?
    s
  end

  def self.key(t)
    [t[0], t[1], t[2], t[3].nil? ? 1 : 0, t[3].nil? ? -1 : t[3], t[4].nil? ? 0 : t[4]]
  end

  def self.release(version, command)
    cur = parse(version)
    return 'error: version' if cur.nil?
    w = command.split(/ /, -1)
    return 'ok' if command == 'check'
    if w.length == 2 && w[0] == 'cmp'
      other = parse(w[1])
      return 'error: other' if other.nil?
      c = key(cur) <=> key(other)
      return c < 0 ? 'less' : c > 0 ? 'greater' : 'equal'
    end
    if HAS_BUMP && %w[major minor patch].include?(command)
      m, n, p = cur[0], cur[1], cur[2]
      if command == 'major'
        m += 1
        n = 0
        p = 0
      elsif command == 'minor'
        n += 1
        p = 0
      elsif cur[3].nil?
        p += 1
      end
      return 'error: overflow' if m > MAXN || n > MAXN || p > MAXN
      return text([m, n, p, nil, nil])
    end
    if HAS_PRE && command == 'release'
      return 'error: not a prerelease' if cur[3].nil?
      return text([cur[0], cur[1], cur[2], nil, nil])
    end
    if HAS_PRE && w.length == 2 && w[0] == 'pre'
      return 'error: channel' unless CHANNELS.include?(w[1])
      ci = CHANNELS.index(w[1])
      if cur[3].nil?
        return 'error: overflow' if cur[2] + 1 > MAXN
        return text([cur[0], cur[1], cur[2] + 1, ci, 1])
      end
      return 'error: downgrade' if ci < cur[3]
      if ci == cur[3]
        return 'error: overflow' if cur[4] + 1 > MAXN
        return text([cur[0], cur[1], cur[2], ci, cur[4] + 1])
      end
      return text([cur[0], cur[1], cur[2], ci, 1])
    end
    'error: command'
  end
end
'''


def sol(lang, p):
    ch = p["channels"]
    src = {"python": PY, "javascript": JS, "rust": RS, "go": GO, "ruby": RB}[lang]
    b = lambda v: ("True" if v else "False") if lang == "python" else ("true" if v else "false")  # noqa: E731
    return K.subst(
        src, BUMP=b(p["bump"]), PRE=b(p["pre"]), MAXN=p["maxn"], CH_PY="[" + ", ".join(f'"{c}"' for c in ch) + "]", CH_JS="[" + ", ".join(f"'{c}'" for c in ch) + "]",
        CH_RS="[" + ", ".join(f'"{c}"' for c in ch) + "]", CH_GO="[]string{" + ", ".join(f'"{c}"' for c in ch) + "}", CH_RB="[" + ", ".join(f"'{c}'" for c in ch) + "]",
    ).lstrip("\n")


def readme(p, api, lang, examples):
    ch = p["channels"]
    L = [f"# Release versions for {p['project']}", ""]
    L.append(f"The release engineers of {p['project']} use a house version scheme. `release(version, command)` checks versions, compares them and computes the next version.")
    L.append("")
    L.append("## Versions")
    L.append("")
    L.append(f"A **version** is `MAJOR.MINOR.PATCH`, optionally followed by a pre-release part `-CHANNEL.N`. Numbers (`MAJOR`, `MINOR`, `PATCH`, `N`) are written in decimal with ASCII digits, no sign, no leading zeros (`0` itself is fine), "
             f"and may not exceed {p['maxn']}. `N` is at least 1. `CHANNEL` is one of " + ", ".join(f"`{c}`" for c in ch) + f", in this order from **lowest to highest**. Examples: `1.4.0`, `0.9.12-{ch[0]}.3`. Nothing else is a version (no blanks, no `v` prefix, no build metadata).")
    L.append("")
    L.append("**Precedence** (used by `cmp`): compare `MAJOR`, then `MINOR`, then `PATCH` numerically; if they are all equal a version **without** a pre-release part is greater than one with it; "
             "two pre-release versions compare by channel order, then by `N`.")
    L.append("")
    L.append("## Commands")
    L.append("")
    L.append("`version` is validated first: if it is not a version the result is `error: version`, whatever the command is. The `command` text is split at **single spaces** (so a doubled or trailing space gives an unknown command). Commands:")
    L.append("")
    L.append("* `check`: the result is `ok`.")
    L.append("* `cmp OTHER`: exactly one more word. If `OTHER` is not a version the result is `error: other`; otherwise `less`, `equal` or `greater` (is `version` less than, equal to or greater than `OTHER`).")
    if p["bump"]:
        L.append("* `major`: `MAJOR+1.0.0`. `minor`: `MAJOR.MINOR+1.0`. Both drop any pre-release part.")
        L.append("* `patch`: if the version has a pre-release part, only that part is dropped (the version *graduates*: `1.2.4-" + ch[1] + ".2` becomes `1.2.4`); otherwise `PATCH` is increased by one.")
        L.append(f"  Any bump that would make a number exceed {p['maxn']} gives `error: overflow`.")
    if p["pre"]:
        L.append("* `release`: drops the pre-release part; `error: not a prerelease` if there is none.")
        L.append(f"* `pre CHANNEL`: `CHANNEL` must be one of the channels (otherwise `error: channel`). If the version has no pre-release part the result is the next patch version with `-CHANNEL.1` (`1.2.3` becomes `1.2.4-{ch[0]}.1`). "
                 "If it has a pre-release part: a target channel *lower* than the current one is `error: downgrade`; the *same* channel increases `N` by one; a *higher* channel keeps `MAJOR.MINOR.PATCH` and restarts at `-CHANNEL.1`. "
                 f"A result with a number above {p['maxn']} is `error: overflow` (checked after the other rules).")
    L.append("")
    L.append("Any other command (an unknown word, the wrong number of words, a command this version does not offer" + (", wrong case" if True else "") + ") gives `error: command`. Results are plain text without a trailing newline.")
    L.append("")
    L.append(K.interface_section(api, lang))
    L.append("## Examples")
    L.append("")
    L.append("| version | command | result |")
    L.append("|---|---|---|")
    for (v, c), out in examples:
        L.append(f"| `{v}` | `{c}` | `{out}` |")
    L.append("")
    L.append(K.run_hint(lang, api.mod))
    return "\n".join(L) + "\n"


def make_cases(rng, p, ns):
    ch = p["channels"]
    mx = p["maxn"]
    cases = []

    def add(v, c):
        cases.append((v, c))

    def rv(pre=None):
        m, n, q = rng.randrange(0, 12), rng.randrange(0, 12), rng.randrange(0, 20)
        s = f"{m}.{n}.{q}"
        if pre or (pre is None and p["pre"] and rng.random() < 0.4):
            s += f"-{rng.choice(ch)}.{rng.randrange(1, 6)}"
        return s

    add(rv(False), "check")
    a, b = rv(False), rv(False)
    add(a, f"cmp {b}")
    add(rv(False), "major" if p["bump"] else "check")
    nex = len(cases)
    for _ in range(10):
        add(rv(), "check")
    for _ in range(14):
        add(rv(), f"cmp {rv()}")
    for v in ["0.0.0", "1.2.3", "10.20.30", f"{mx}.{mx}.{mx}", "1.0.0", f"0.0.{mx}", "0.0.1"]:
        add(v, "check")
        add(v, f"cmp {v}")
    for v in ["", "1", "1.2", "1.2.3.4", "01.2.3", "1.02.3", "1.2.03", "a.b.c", "1.2.x", "1..3", ".1.2", "1.2.", "-1.2.3", "1.-2.3", "+1.2.3", "1.2.3+5", "v1.2.3", "1.2.3 ", " 1.2.3", "1.2.3-", "1.2.3-.1", "1.2.3-x.1", f"1.2.3-{ch[0]}", f"1.2.3-{ch[0]}.", f"1.2.3-{ch[0]}.0", f"1.2.3-{ch[0]}.01", f"1.2.3-{ch[0]}.x",
              f"1.2.3-{ch[0].upper()}.1", f"1.2.3-{ch[0]}.1.2", f"1.2.3-{ch[0]}-1", f"1.2.3-{ch[0]}.1-{ch[1]}.1", f"{mx + 1}.0.0", f"0.{mx + 1}.0", f"0.0.{mx + 1}", f"1.2.3-{ch[0]}.{mx + 1}", f"1.2.3-{ch[0]}.{mx}", f"1,2,3", "1.2.3\n", "1.2.3-", "--", "1.2.3--", "1.2.3-" + ch[0] + ".1-"]:
        add(v, "check")
        add(v, "cmp 1.0.0")
        if p["bump"]:
            add(v, "patch")
    # cmp semantics
    base = "1.2.3"
    for o in ["1.2.3", "1.2.4", "1.2.2", "1.3.0", "1.1.9", "2.0.0", "0.9.9", "1.2.10", "1.10.0", "10.0.0", "1.2.3-" + ch[0] + ".1", "1.2.3-" + ch[-1] + ".9", "1.2.4-" + ch[0] + ".1", "1.2.2-" + ch[-1] + ".1"]:
        add(base, f"cmp {o}")
        add(o, f"cmp {base}")
    for x, y in [(0, 0), (0, 1), (1, 0), (1, 1)]:
        for n in (1, 2, 10):
            add(f"3.0.0-{ch[x]}.{n}", f"cmp 3.0.0-{ch[y]}.{n}")
            add(f"3.0.0-{ch[x]}.{n}", f"cmp 3.0.0-{ch[y]}.{n + 1}")
            add(f"3.0.0-{ch[x]}.{n + 1}", f"cmp 3.0.0-{ch[y]}.{n}")
    add(f"3.0.0-{ch[-1]}.99", f"cmp 3.0.0-{ch[0]}.1")
    add(f"3.0.0-{ch[0]}.1", f"cmp 3.0.0-{ch[-1]}.99")
    add("3.0.0-" + ch[-1] + ".1", "cmp 3.0.0")
    add("3.0.0", "cmp 3.0.0-" + ch[-1] + ".1")
    add("3.0.1-" + ch[0] + ".1", "cmp 3.0.0")
    add("1.2.3", "cmp")
    add("1.2.3", "cmp ")
    add("1.2.3", "cmp bogus")
    add("1.2.3", "cmp 1.2.3 1.2.3")
    add("1.2.3", "cmp  1.2.3")
    add("bogus", "cmp bogus")
    add("bogus", "cmp 1.2.3")
    add("1.2.3", "cmp 1.2")
    add("1.2.3", "CMP 1.2.3")
    add(f"{mx}.0.0", f"cmp {mx}.0.1")
    add(f"{mx}.{mx}.{mx}-{ch[-1]}.{mx}", f"cmp {mx}.{mx}.{mx}-{ch[-1]}.{mx}")
    if p["bump"]:
        for v in ["0.0.0", "1.2.3", f"{mx}.0.0", f"0.{mx}.0", f"0.0.{mx}", f"{mx}.{mx}.{mx}", f"1.{mx}.{mx}", "9.9.9", "10.99.100", f"1.2.3-{ch[0]}.1", f"1.2.3-{ch[-1]}.7", f"{mx}.0.0-{ch[0]}.1", f"0.{mx}.0-{ch[0]}.1", f"0.0.{mx}-{ch[0]}.1", f"{mx}.{mx}.{mx}-{ch[-1]}.1", "0.0.0-" + ch[0] + ".1"]:
            for c in ("major", "minor", "patch"):
                add(v, c)
        for c in ["Major", "MAJOR", "majors", "major ", " major", "major minor", "bump", "next", "", " ", "patch 1", "minor 1", "major  ", "mayor", "minor\n", "pre", "release", "cmp"]:
            add("1.2.3", c)
    else:
        for c in ["major", "minor", "patch", "release", "pre " + ch[0]]:
            add("1.2.3", c)
    if p["pre"]:
        for v in ["1.2.3", "0.0.0", f"1.2.{mx}", f"{mx}.{mx}.{mx}", "1.2.3-" + ch[0] + ".1", "1.2.3-" + ch[0] + ".9", f"1.2.3-{ch[0]}.{mx}", f"1.2.3-{ch[-1]}.{mx}", f"1.2.{mx}-{ch[0]}.1", f"{mx}.0.0-{ch[-1]}.5", "1.2.3-" + ch[-1] + ".2"]:
            for c in ch:
                add(v, f"pre {c}")
            add(v, "release")
        for c in ["pre", "pre ", "pre x", "pre " + ch[0].upper(), "pre " + ch[0] + " ", "pre  " + ch[0], "pre " + ch[0] + " " + ch[1], "pre-" + ch[0], "pre " + ch[0] + ".1", "Release", "release ", "release now", "prerelease " + ch[0], "pre 1"]:
            add("1.2.3", c)
            add(f"1.2.3-{ch[0]}.1", c)
        for v in ["bogus", "1.2", ""]:
            add(v, "pre " + ch[0])
            add(v, "release")
    else:
        for c in ["pre " + ch[0], "release"]:
            add("1.2.3", c)
    out, seen = [], set()
    for c in cases:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out, nex


def prompt(rng, p, api, lang):
    where = api.short(lang)
    fn = api.name(lang)
    ln = K.LANG_NAME[lang]
    cmds = ["`check`", "`cmp`"] + (["`major`, `minor`, `patch`"] if p["bump"] else []) + (["`pre`, `release`"] if p["pre"] else [])
    cl = ", ".join(cmds)
    opts = [
        f"{p['project'].capitalize()} has its own version scheme (pre-release channels in a fixed order). Write `{fn}(version, command)` in {ln}, in {where}: commands {cl}. The rules (precedence, graduation, overflow) are in README.md. {K.closer(rng)}",
        f"Small {ln} utility: implement `{fn}` ({where}) as described in README.md. Commands: {cl}. Watch the error order: the version is validated before the command.",
        f"release versioning helper, {ln}. `{fn}` in {where}; README.md has the scheme and the commands ({cl}). {K.closer(rng)}",
        f"Please implement the version tool from README.md ({ln}; `{fn}`; {where}). It supports {cl}. Hidden checks include boundary numbers ({p['maxn']}) and malformed versions.",
    ]
    return rng.choice(opts).strip()


@family("greenfield-releaser", category="greenfield", lang="mixed", kind="greenfield", n=10,
        summary="release versions with ordered pre-release channels: strict validation, precedence, bump/graduate/pre-release commands, overflow limits")
def gen(rng, n):
    levels = [1, 1, 2, 2, 2, 3, 3, 3, 1, 3]
    for i in range(n):
        lang = LANG_PLAN[i % len(LANG_PLAN)]
        level = levels[i % len(levels)]
        p = params(rng, level, i)
        api = K.Api(mod="releaser", fn="release", args=["version", "command"], arg_docs=["the version text", "the command, e.g. `check`, `cmp 1.2.3`" + (", `patch`" if p["bump"] else "") + (", `pre rc`" if p["pre"] else "")],
                    ret_doc="the result text", doc="release version tool")
        py_src = sol("python", p)
        ns = K.py_namespace(py_src)
        cases, nex = make_cases(rng, p, ns)
        sols = {lang: sol(lang, p), "python": py_src}
        examples = [(c, ns["release"](*c)) for c in cases[:nex]]
        rd = readme(p, api, lang, examples)
        yield K.lib_task(
            api=api, lang=lang, readme=rd, solutions=sols, cases=cases, examples=nex, prompt=prompt(rng, p, api, lang),
            difficulty=level, slug=f"{i + 1:02d}-{lang}-{p['channels'][0]}-l{level}", oracle=(None if lang == "python" else ns["release"]),
            tags=["parser", "versions"], notes={"level": level, "channels": p["channels"], "maxn": p["maxn"]},
        )
