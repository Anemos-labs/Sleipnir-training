"""Stamp-duty statements for invented jurisdictions: a request text in, an itemised duty statement out."""
from __future__ import annotations

from fx import dd, family

from generators.greenfield import _kit as K

REGIONS = [
    ("the Duchy of Ostrel", "marks"), ("Brannock Reach", "florins"), ("the Tiderow Isles", "shells"),
    ("Quillmere", "crowns"), ("the Hollin Free Cantons", "thalers"), ("Vessper Province", "ducats"),
    ("Lower Karrow", "talents"), ("the Saltmarch League", "groats"), ("Evenmoor", "pence"), ("Dunmarrow Shire", "guilders"),
]
LOT_KWS = ["lot", "parcel", "title", "plot", "deed"]
BUYER_KWS = ["buyer", "purchaser", "acquirer", "party"]
TOTAL_LABELS = ["total", "due", "sum", "payable"]
KINDS = ["house", "flat", "land", "farm"]
BUYERS = ["first", "owner", "investor", "company"]
ROUND_NAMES = {0: "half up", 1: "half down", 2: "nearest 5"}

LANG_PLAN = ["python", "javascript", "go", "rust", "java", "ruby", "c", "python", "go", "javascript", "rust", "java"]


def params(rng, level):
    nb = rng.choice([2, 3, 3, 4])
    lows = [0]
    for _ in range(nb - 1):
        lows.append(lows[-1] + rng.choice([60, 90, 120, 150, 200, 250]) * 1000)
    rates = [0]
    for _ in range(nb - 1):
        rates.append(rates[-1] + rng.choice([50, 75, 100, 125, 150, 200]))
    if rng.random() < 0.5:
        rates[0] = rng.choice([0, 0, 25])
        if rates[0] > rates[1]:
            rates[1] = rates[0] + 25
    kinds = level >= 2
    buyer = level >= 3
    p = {
        "level": level,
        "region": REGIONS[rng.randrange(len(REGIONS))],
        "lot_kw": rng.choice(LOT_KWS),
        "buyer_kw": rng.choice(BUYER_KWS),
        "total": rng.choice(TOTAL_LABELS),
        "bands": list(zip(lows, rates)),
        "kinds": kinds,
        "buyer": buyer,
        "round": rng.choice([0, 0, 1, 2]) if level >= 2 else 0,
        "min_duty": rng.choice([0, 25, 50, 100]) if level >= 2 else 0,
        "farm_pm": rng.choice([500, 600, 750]) if kinds else 1000,
        "land_floor": rng.choice([20000, 30000, 50000]) if kinds else 0,
        "relief": rng.choice([150000, 200000, 250000]) if buyer else 0,
        "sur_investor": rng.choice([200, 300, 400]) if buyer else 0,
        "sur_company": rng.choice([400, 500, 600]) if buyer else 0,
    }
    return p


# ---------------------------------------------------------------------------------------------------------------
# reference solutions
# ---------------------------------------------------------------------------------------------------------------

def _b(lang, v):
    if lang == "python":
        return "True" if v else "False"
    if lang == "ruby":
        return "true" if v else "false"
    if lang == "c":
        return "1" if v else "0"
    return "true" if v else "false"


def _bands(lang, bands):
    pairs = [(lo, r) for lo, r in bands]
    if lang == "python":
        return "[" + ", ".join(f"({a}, {b})" for a, b in pairs) + "]"
    if lang in ("javascript", "ruby"):
        return "[" + ", ".join(f"[{a}, {b}]" for a, b in pairs) + "]"
    if lang == "go":
        return "[][2]int64{" + ", ".join(f"{{{a}, {b}}}" for a, b in pairs) + "}"
    if lang == "rust":
        return "&[" + ", ".join(f"({a}, {b})" for a, b in pairs) + "]"
    if lang == "java":
        return "{" + ", ".join(f"{{{a}L, {b}L}}" for a, b in pairs) + "}"
    if lang == "c":
        return "{" + ", ".join(f"{{{a}LL, {b}LL}}" for a, b in pairs) + "}"
    raise ValueError(lang)


def _subst(lang, tpl, p):
    return K.subst(
        tpl, HAS_KINDS=_b(lang, p["kinds"]), HAS_BUYER=_b(lang, p["buyer"]), LOT_KW=p["lot_kw"], BUYER_KW=p["buyer_kw"],
        TOTAL=p["total"], BANDS=_bands(lang, p["bands"]), ROUND=p["round"], MIN_DUTY=p["min_duty"], FARM_PM=p["farm_pm"],
        LAND_FLOOR=p["land_floor"], RELIEF=p["relief"], SUR_INV=p["sur_investor"], SUR_COM=p["sur_company"],
    )


PY = '''
HAS_KINDS = @HAS_KINDS@
HAS_BUYER = @HAS_BUYER@
LOT_KW = "@LOT_KW@"
BUYER_KW = "@BUYER_KW@"
TOTAL = "@TOTAL@"
BANDS = @BANDS@
ROUND = @ROUND@
MIN_DUTY = @MIN_DUTY@
FARM_PM = @FARM_PM@
LAND_FLOOR = @LAND_FLOOR@
RELIEF = @RELIEF@
SUR_INV = @SUR_INV@
SUR_COM = @SUR_COM@
KINDS = ("house", "flat", "land", "farm")
BUYERS = ("first", "owner", "investor", "company")


def _fields(line):
    return [w for w in line.replace("\\t", " ").split(" ") if w]


def _lot_duty(kind, price, buyer):
    if HAS_KINDS and kind == "land" and price < LAND_FLOOR:
        return 0
    if HAS_BUYER and buyer == "first" and kind in ("house", "flat") and price <= RELIEF:
        return 0
    num = 0  # units of 1/10000
    for i, (lo, rate) in enumerate(BANDS):
        if price > lo:
            top = price
            if i + 1 < len(BANDS) and BANDS[i + 1][0] < price:
                top = BANDS[i + 1][0]
            num += (top - lo) * rate
    num *= FARM_PM if (HAS_KINDS and kind == "farm") else 1000  # units of 1/10^7
    if HAS_BUYER and kind != "land":
        sur = SUR_INV if buyer == "investor" else SUR_COM if buyer == "company" else 0
        num += price * sur * 1000
    if ROUND == 0:
        d = (num + 5000000) // 10000000
    elif ROUND == 1:
        d = (num + 4999999) // 10000000
    else:
        d = (num + 25000000) // 50000000 * 5
    if 0 < d < MIN_DUTY:
        d = MIN_DUTY
    return d


def duty(request):
    buyer = "owner"
    seen_buyer = False
    lots = []
    for idx, line in enumerate(request.split("\\n")):
        f = _fields(line)
        if not f or f[0].startswith("#"):
            continue
        n = idx + 1

        def fail(msg):
            return "error: line %d: %s" % (n, msg)

        if HAS_BUYER and f[0] == BUYER_KW:
            if len(f) != 2:
                return fail("wrong field count")
            if f[1] not in BUYERS:
                return fail("unknown buyer")
            if seen_buyer:
                return fail("duplicate buyer")
            seen_buyer = True
            buyer = f[1]
        elif f[0] == LOT_KW:
            if len(f) != (3 if HAS_KINDS else 2):
                return fail("wrong field count")
            kind = ""
            if HAS_KINDS:
                kind = f[1]
                if kind not in KINDS:
                    return fail("unknown kind")
            ptxt = f[-1]
            if not (1 <= len(ptxt) <= 9 and all(c in "0123456789" for c in ptxt)):
                return fail("bad price")
            lots.append((kind, int(ptxt)))
        else:
            return fail("unknown directive")
    if not lots:
        return "error: no lots"
    out = []
    total = 0
    for kind, price in lots:
        d = _lot_duty(kind, price, buyer)
        total += d
        out.append(("%s %d %d" % (kind, price, d)) if HAS_KINDS else ("%d %d" % (price, d)))
    out.append("%s %d" % (TOTAL, total))
    return "\\n".join(out)
'''

JS = '''
'use strict';

const HAS_KINDS = @HAS_KINDS@;
const HAS_BUYER = @HAS_BUYER@;
const LOT_KW = '@LOT_KW@';
const BUYER_KW = '@BUYER_KW@';
const TOTAL = '@TOTAL@';
const BANDS = @BANDS@;
const ROUND = @ROUND@;
const MIN_DUTY = @MIN_DUTY@;
const FARM_PM = @FARM_PM@;
const LAND_FLOOR = @LAND_FLOOR@;
const RELIEF = @RELIEF@;
const SUR_INV = @SUR_INV@;
const SUR_COM = @SUR_COM@;
const KINDS = ['house', 'flat', 'land', 'farm'];
const BUYERS = ['first', 'owner', 'investor', 'company'];

function fields(line) {
  return line.split(/[ \\t]+/).filter((w) => w.length > 0);
}

function lotDuty(kind, price, buyer) {
  if (HAS_KINDS && kind === 'land' && price < LAND_FLOOR) return 0;
  if (HAS_BUYER && buyer === 'first' && (kind === 'house' || kind === 'flat') && price <= RELIEF) return 0;
  let num = 0;
  BANDS.forEach(([lo, rate], i) => {
    if (price > lo) {
      let top = price;
      if (i + 1 < BANDS.length && BANDS[i + 1][0] < price) top = BANDS[i + 1][0];
      num += (top - lo) * rate;
    }
  });
  num *= HAS_KINDS && kind === 'farm' ? FARM_PM : 1000;
  if (HAS_BUYER && kind !== 'land') {
    const sur = buyer === 'investor' ? SUR_INV : buyer === 'company' ? SUR_COM : 0;
    num += price * sur * 1000;
  }
  let d;
  if (ROUND === 0) d = Math.floor((num + 5000000) / 10000000);
  else if (ROUND === 1) d = Math.floor((num + 4999999) / 10000000);
  else d = Math.floor((num + 25000000) / 50000000) * 5;
  if (d > 0 && d < MIN_DUTY) d = MIN_DUTY;
  return d;
}

function duty(request) {
  let buyer = 'owner';
  let seenBuyer = false;
  const lots = [];
  const lines = request.split('\\n');
  for (let i = 0; i < lines.length; i++) {
    const f = fields(lines[i]);
    if (f.length === 0 || f[0].startsWith('#')) continue;
    const fail = (msg) => `error: line ${i + 1}: ${msg}`;
    if (HAS_BUYER && f[0] === BUYER_KW) {
      if (f.length !== 2) return fail('wrong field count');
      if (!BUYERS.includes(f[1])) return fail('unknown buyer');
      if (seenBuyer) return fail('duplicate buyer');
      seenBuyer = true;
      buyer = f[1];
    } else if (f[0] === LOT_KW) {
      if (f.length !== (HAS_KINDS ? 3 : 2)) return fail('wrong field count');
      let kind = '';
      if (HAS_KINDS) {
        kind = f[1];
        if (!KINDS.includes(kind)) return fail('unknown kind');
      }
      const ptxt = f[f.length - 1];
      if (!/^[0-9]{1,9}$/.test(ptxt)) return fail('bad price');
      lots.push([kind, parseInt(ptxt, 10)]);
    } else {
      return fail('unknown directive');
    }
  }
  if (lots.length === 0) return 'error: no lots';
  const out = [];
  let total = 0;
  for (const [kind, price] of lots) {
    const d = lotDuty(kind, price, buyer);
    total += d;
    out.push(HAS_KINDS ? `${kind} ${price} ${d}` : `${price} ${d}`);
  }
  out.push(`${TOTAL} ${total}`);
  return out.join('\\n');
}

module.exports = { duty };
'''

GO = '''
package stampduty

import (
	"fmt"
	"strconv"
	"strings"
)

const (
	hasKinds   = @HAS_KINDS@
	hasBuyer   = @HAS_BUYER@
	lotKw      = "@LOT_KW@"
	buyerKw    = "@BUYER_KW@"
	totalLabel = "@TOTAL@"
	roundMode  = @ROUND@
	minDuty    int64 = @MIN_DUTY@
	farmPm     int64 = @FARM_PM@
	landFloor  int64 = @LAND_FLOOR@
	relief     int64 = @RELIEF@
	surInv     int64 = @SUR_INV@
	surCom     int64 = @SUR_COM@
)

var bands = @BANDS@

func isKind(s string) bool {
	return s == "house" || s == "flat" || s == "land" || s == "farm"
}

func isBuyer(s string) bool {
	return s == "first" || s == "owner" || s == "investor" || s == "company"
}

func fields(line string) []string {
	return strings.FieldsFunc(line, func(r rune) bool { return r == ' ' || r == '\\t' })
}

func lotDuty(kind string, price int64, buyer string) int64 {
	if hasKinds && kind == "land" && price < landFloor {
		return 0
	}
	if hasBuyer && buyer == "first" && (kind == "house" || kind == "flat") && price <= relief {
		return 0
	}
	var num int64
	for i, b := range bands {
		if price > b[0] {
			top := price
			if i+1 < len(bands) && bands[i+1][0] < price {
				top = bands[i+1][0]
			}
			num += (top - b[0]) * b[1]
		}
	}
	if hasKinds && kind == "farm" {
		num *= farmPm
	} else {
		num *= 1000
	}
	if hasBuyer && kind != "land" {
		var sur int64
		if buyer == "investor" {
			sur = surInv
		} else if buyer == "company" {
			sur = surCom
		}
		num += price * sur * 1000
	}
	var d int64
	switch roundMode {
	case 0:
		d = (num + 5000000) / 10000000
	case 1:
		d = (num + 4999999) / 10000000
	default:
		d = (num + 25000000) / 50000000 * 5
	}
	if d > 0 && d < minDuty {
		d = minDuty
	}
	return d
}

type lot struct {
	kind  string
	price int64
}

// Duty renders the duty statement for a request.
func Duty(request string) string {
	buyer := "owner"
	seenBuyer := false
	var lots []lot
	for i, line := range strings.Split(request, "\\n") {
		f := fields(line)
		if len(f) == 0 || strings.HasPrefix(f[0], "#") {
			continue
		}
		fail := func(msg string) string { return fmt.Sprintf("error: line %d: %s", i+1, msg) }
		switch {
		case hasBuyer && f[0] == buyerKw:
			if len(f) != 2 {
				return fail("wrong field count")
			}
			if !isBuyer(f[1]) {
				return fail("unknown buyer")
			}
			if seenBuyer {
				return fail("duplicate buyer")
			}
			seenBuyer = true
			buyer = f[1]
		case f[0] == lotKw:
			want := 2
			if hasKinds {
				want = 3
			}
			if len(f) != want {
				return fail("wrong field count")
			}
			kind := ""
			if hasKinds {
				kind = f[1]
				if !isKind(kind) {
					return fail("unknown kind")
				}
			}
			ptxt := f[len(f)-1]
			if len(ptxt) < 1 || len(ptxt) > 9 || strings.Trim(ptxt, "0123456789") != "" {
				return fail("bad price")
			}
			v, _ := strconv.ParseInt(ptxt, 10, 64)
			lots = append(lots, lot{kind, v})
		default:
			return fail("unknown directive")
		}
	}
	if len(lots) == 0 {
		return "error: no lots"
	}
	var out []string
	var total int64
	for _, l := range lots {
		d := lotDuty(l.kind, l.price, buyer)
		total += d
		if hasKinds {
			out = append(out, fmt.Sprintf("%s %d %d", l.kind, l.price, d))
		} else {
			out = append(out, fmt.Sprintf("%d %d", l.price, d))
		}
	}
	out = append(out, fmt.Sprintf("%s %d", totalLabel, total))
	return strings.Join(out, "\\n")
}
'''

RS = '''
const HAS_KINDS: bool = @HAS_KINDS@;
const HAS_BUYER: bool = @HAS_BUYER@;
const LOT_KW: &str = "@LOT_KW@";
const BUYER_KW: &str = "@BUYER_KW@";
const TOTAL: &str = "@TOTAL@";
const BANDS: &[(i64, i64)] = @BANDS@;
const ROUND: u8 = @ROUND@;
const MIN_DUTY: i64 = @MIN_DUTY@;
const FARM_PM: i64 = @FARM_PM@;
const LAND_FLOOR: i64 = @LAND_FLOOR@;
const RELIEF: i64 = @RELIEF@;
const SUR_INV: i64 = @SUR_INV@;
const SUR_COM: i64 = @SUR_COM@;
const KINDS: [&str; 4] = ["house", "flat", "land", "farm"];
const BUYERS: [&str; 4] = ["first", "owner", "investor", "company"];

fn fields(line: &str) -> Vec<&str> {
    line.split(|c| c == ' ' || c == '\\t').filter(|w| !w.is_empty()).collect()
}

fn lot_duty(kind: &str, price: i64, buyer: &str) -> i64 {
    if HAS_KINDS && kind == "land" && price < LAND_FLOOR {
        return 0;
    }
    if HAS_BUYER && buyer == "first" && (kind == "house" || kind == "flat") && price <= RELIEF {
        return 0;
    }
    let mut num: i64 = 0;
    for (i, &(lo, rate)) in BANDS.iter().enumerate() {
        if price > lo {
            let mut top = price;
            if i + 1 < BANDS.len() && BANDS[i + 1].0 < price {
                top = BANDS[i + 1].0;
            }
            num += (top - lo) * rate;
        }
    }
    num *= if HAS_KINDS && kind == "farm" { FARM_PM } else { 1000 };
    if HAS_BUYER && kind != "land" {
        let sur = if buyer == "investor" { SUR_INV } else if buyer == "company" { SUR_COM } else { 0 };
        num += price * sur * 1000;
    }
    let mut d = match ROUND {
        0 => (num + 5_000_000) / 10_000_000,
        1 => (num + 4_999_999) / 10_000_000,
        _ => (num + 25_000_000) / 50_000_000 * 5,
    };
    if d > 0 && d < MIN_DUTY {
        d = MIN_DUTY;
    }
    d
}

/// Renders the duty statement for a request.
pub fn duty(request: &str) -> String {
    let mut buyer = "owner";
    let mut seen_buyer = false;
    let mut lots: Vec<(&str, i64)> = Vec::new();
    for (idx, line) in request.split('\\n').enumerate() {
        let f = fields(line);
        if f.is_empty() || f[0].starts_with('#') {
            continue;
        }
        let fail = |msg: &str| format!("error: line {}: {}", idx + 1, msg);
        if HAS_BUYER && f[0] == BUYER_KW {
            if f.len() != 2 {
                return fail("wrong field count");
            }
            if !BUYERS.contains(&f[1]) {
                return fail("unknown buyer");
            }
            if seen_buyer {
                return fail("duplicate buyer");
            }
            seen_buyer = true;
            buyer = f[1];
        } else if f[0] == LOT_KW {
            let want = if HAS_KINDS { 3 } else { 2 };
            if f.len() != want {
                return fail("wrong field count");
            }
            let mut kind = "";
            if HAS_KINDS {
                kind = f[1];
                if !KINDS.contains(&kind) {
                    return fail("unknown kind");
                }
            }
            let ptxt = f[f.len() - 1];
            if ptxt.is_empty() || ptxt.len() > 9 || !ptxt.bytes().all(|b| b.is_ascii_digit()) {
                return fail("bad price");
            }
            lots.push((kind, ptxt.parse::<i64>().unwrap()));
        } else {
            return fail("unknown directive");
        }
    }
    if lots.is_empty() {
        return "error: no lots".to_string();
    }
    let mut out: Vec<String> = Vec::new();
    let mut total: i64 = 0;
    for (kind, price) in lots {
        let d = lot_duty(kind, price, buyer);
        total += d;
        out.push(if HAS_KINDS { format!("{} {} {}", kind, price, d) } else { format!("{} {}", price, d) });
    }
    out.push(format!("{} {}", TOTAL, total));
    out.join("\\n")
}
'''

JV = '''
import java.util.ArrayList;
import java.util.List;

public class Stampduty {
    static final boolean HAS_KINDS = @HAS_KINDS@;
    static final boolean HAS_BUYER = @HAS_BUYER@;
    static final String LOT_KW = "@LOT_KW@";
    static final String BUYER_KW = "@BUYER_KW@";
    static final String TOTAL = "@TOTAL@";
    static final long[][] BANDS = @BANDS@;
    static final int ROUND = @ROUND@;
    static final long MIN_DUTY = @MIN_DUTY@;
    static final long FARM_PM = @FARM_PM@;
    static final long LAND_FLOOR = @LAND_FLOOR@;
    static final long RELIEF = @RELIEF@;
    static final long SUR_INV = @SUR_INV@;
    static final long SUR_COM = @SUR_COM@;

    static boolean oneOf(String s, String... opts) {
        for (String o : opts) if (o.equals(s)) return true;
        return false;
    }

    static List<String> fields(String line) {
        List<String> out = new ArrayList<>();
        for (String w : line.split("[ \\t]+")) if (!w.isEmpty()) out.add(w);
        return out;
    }

    static long lotDuty(String kind, long price, String buyer) {
        if (HAS_KINDS && kind.equals("land") && price < LAND_FLOOR) return 0;
        if (HAS_BUYER && buyer.equals("first") && (kind.equals("house") || kind.equals("flat")) && price <= RELIEF) return 0;
        long num = 0;
        for (int i = 0; i < BANDS.length; i++) {
            if (price > BANDS[i][0]) {
                long top = price;
                if (i + 1 < BANDS.length && BANDS[i + 1][0] < price) top = BANDS[i + 1][0];
                num += (top - BANDS[i][0]) * BANDS[i][1];
            }
        }
        num *= (HAS_KINDS && kind.equals("farm")) ? FARM_PM : 1000;
        if (HAS_BUYER && !kind.equals("land")) {
            long sur = buyer.equals("investor") ? SUR_INV : buyer.equals("company") ? SUR_COM : 0;
            num += price * sur * 1000;
        }
        long d;
        if (ROUND == 0) d = (num + 5000000L) / 10000000L;
        else if (ROUND == 1) d = (num + 4999999L) / 10000000L;
        else d = (num + 25000000L) / 50000000L * 5;
        if (d > 0 && d < MIN_DUTY) d = MIN_DUTY;
        return d;
    }

    public static String duty(String request) {
        String buyer = "owner";
        boolean seenBuyer = false;
        List<String> kinds = new ArrayList<>();
        List<Long> prices = new ArrayList<>();
        String[] lines = request.split("\\n", -1);
        for (int i = 0; i < lines.length; i++) {
            List<String> f = fields(lines[i]);
            if (f.isEmpty() || f.get(0).startsWith("#")) continue;
            String at = "error: line " + (i + 1) + ": ";
            if (HAS_BUYER && f.get(0).equals(BUYER_KW)) {
                if (f.size() != 2) return at + "wrong field count";
                if (!oneOf(f.get(1), "first", "owner", "investor", "company")) return at + "unknown buyer";
                if (seenBuyer) return at + "duplicate buyer";
                seenBuyer = true;
                buyer = f.get(1);
            } else if (f.get(0).equals(LOT_KW)) {
                if (f.size() != (HAS_KINDS ? 3 : 2)) return at + "wrong field count";
                String kind = "";
                if (HAS_KINDS) {
                    kind = f.get(1);
                    if (!oneOf(kind, "house", "flat", "land", "farm")) return at + "unknown kind";
                }
                String ptxt = f.get(f.size() - 1);
                if (!ptxt.matches("[0-9]{1,9}")) return at + "bad price";
                kinds.add(kind);
                prices.add(Long.parseLong(ptxt));
            } else {
                return at + "unknown directive";
            }
        }
        if (prices.isEmpty()) return "error: no lots";
        StringBuilder out = new StringBuilder();
        long total = 0;
        for (int i = 0; i < prices.size(); i++) {
            long d = lotDuty(kinds.get(i), prices.get(i), buyer);
            total += d;
            out.append(HAS_KINDS ? kinds.get(i) + " " + prices.get(i) + " " + d : prices.get(i) + " " + d).append("\\n");
        }
        out.append(TOTAL).append(" ").append(total);
        return out.toString();
    }
}
'''

RB = '''
module Stampduty
  HAS_KINDS = @HAS_KINDS@
  HAS_BUYER = @HAS_BUYER@
  LOT_KW = '@LOT_KW@'
  BUYER_KW = '@BUYER_KW@'
  TOTAL = '@TOTAL@'
  BANDS = @BANDS@
  ROUND = @ROUND@
  MIN_DUTY = @MIN_DUTY@
  FARM_PM = @FARM_PM@
  LAND_FLOOR = @LAND_FLOOR@
  RELIEF = @RELIEF@
  SUR_INV = @SUR_INV@
  SUR_COM = @SUR_COM@
  KINDS = %w[house flat land farm]
  BUYERS = %w[first owner investor company]

  def self.lot_duty(kind, price, buyer)
    return 0 if HAS_KINDS && kind == 'land' && price < LAND_FLOOR
    return 0 if HAS_BUYER && buyer == 'first' && %w[house flat].include?(kind) && price <= RELIEF
    num = 0
    BANDS.each_with_index do |(lo, rate), i|
      next unless price > lo
      top = price
      top = BANDS[i + 1][0] if i + 1 < BANDS.length && BANDS[i + 1][0] < price
      num += (top - lo) * rate
    end
    num *= (HAS_KINDS && kind == 'farm') ? FARM_PM : 1000
    if HAS_BUYER && kind != 'land'
      sur = buyer == 'investor' ? SUR_INV : buyer == 'company' ? SUR_COM : 0
      num += price * sur * 1000
    end
    d = case ROUND
        when 0 then (num + 5_000_000) / 10_000_000
        when 1 then (num + 4_999_999) / 10_000_000
        else (num + 25_000_000) / 50_000_000 * 5
        end
    d = MIN_DUTY if d > 0 && d < MIN_DUTY
    d
  end

  def self.duty(request)
    buyer = 'owner'
    seen_buyer = false
    lots = []
    request.split("\\n", -1).each_with_index do |line, idx|
      f = line.split(/[ \\t]+/).reject(&:empty?)
      next if f.empty? || f[0].start_with?('#')
      at = "error: line #{idx + 1}: "
      if HAS_BUYER && f[0] == BUYER_KW
        return at + 'wrong field count' if f.length != 2
        return at + 'unknown buyer' unless BUYERS.include?(f[1])
        return at + 'duplicate buyer' if seen_buyer
        seen_buyer = true
        buyer = f[1]
      elsif f[0] == LOT_KW
        return at + 'wrong field count' if f.length != (HAS_KINDS ? 3 : 2)
        kind = ''
        if HAS_KINDS
          kind = f[1]
          return at + 'unknown kind' unless KINDS.include?(kind)
        end
        ptxt = f[-1]
        return at + 'bad price' unless ptxt.match?(/\\A[0-9]{1,9}\\z/)
        lots << [kind, ptxt.to_i]
      else
        return at + 'unknown directive'
      end
    end
    return 'error: no lots' if lots.empty?
    total = 0
    out = lots.map do |kind, price|
      d = lot_duty(kind, price, buyer)
      total += d
      HAS_KINDS ? "#{kind} #{price} #{d}" : "#{price} #{d}"
    end
    out << "#{TOTAL} #{total}"
    out.join("\\n")
  end
end
'''

C = '''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "stampduty.h"

#define HAS_KINDS @HAS_KINDS@
#define HAS_BUYER @HAS_BUYER@
#define LOT_KW "@LOT_KW@"
#define BUYER_KW "@BUYER_KW@"
#define TOTAL "@TOTAL@"
#define ROUND @ROUND@
#define MIN_DUTY @MIN_DUTY@LL
#define FARM_PM @FARM_PM@LL
#define LAND_FLOOR @LAND_FLOOR@LL
#define RELIEF @RELIEF@LL
#define SUR_INV @SUR_INV@LL
#define SUR_COM @SUR_COM@LL

static const long long BANDS[][2] = @BANDS@;
#define NBANDS ((int)(sizeof BANDS / sizeof BANDS[0]))

static const char *KINDS[] = {"house", "flat", "land", "farm"};
static const char *BUYERS[] = {"first", "owner", "investor", "company"};

static int in_list(const char *s, const char **list, int n) {
    for (int i = 0; i < n; i++)
        if (strcmp(s, list[i]) == 0) return 1;
    return 0;
}

static long long lot_duty(const char *kind, long long price, const char *buyer) {
    if (HAS_KINDS && strcmp(kind, "land") == 0 && price < LAND_FLOOR) return 0;
    if (HAS_BUYER && strcmp(buyer, "first") == 0 && (strcmp(kind, "house") == 0 || strcmp(kind, "flat") == 0) && price <= RELIEF) return 0;
    long long num = 0;
    for (int i = 0; i < NBANDS; i++) {
        if (price > BANDS[i][0]) {
            long long top = price;
            if (i + 1 < NBANDS && BANDS[i + 1][0] < price) top = BANDS[i + 1][0];
            num += (top - BANDS[i][0]) * BANDS[i][1];
        }
    }
    num *= (HAS_KINDS && strcmp(kind, "farm") == 0) ? FARM_PM : 1000;
    if (HAS_BUYER && strcmp(kind, "land") != 0) {
        long long sur = strcmp(buyer, "investor") == 0 ? SUR_INV : strcmp(buyer, "company") == 0 ? SUR_COM : 0;
        num += price * sur * 1000;
    }
    long long d;
    if (ROUND == 0) d = (num + 5000000LL) / 10000000LL;
    else if (ROUND == 1) d = (num + 4999999LL) / 10000000LL;
    else d = (num + 25000000LL) / 50000000LL * 5;
    if (d > 0 && d < MIN_DUTY) d = MIN_DUTY;
    return d;
}

static char *dupstr(const char *s) {
    char *r = malloc(strlen(s) + 1);
    strcpy(r, s);
    return r;
}

static char *fail_at(int n, const char *msg) {
    char *r = malloc(strlen(msg) + 40);
    sprintf(r, "error: line %d: %s", n, msg);
    return r;
}

/* splits line (in place) into fields separated by spaces/tabs; returns the count */
static int split_fields(char *line, char **f, int max) {
    int n = 0;
    char *p = line;
    while (*p) {
        while (*p == ' ' || *p == '\\t') *p++ = 0;
        if (!*p) break;
        if (n < max) f[n] = p;
        n++;
        while (*p && *p != ' ' && *p != '\\t') p++;
    }
    return n;
}

char *duty(const char *request) {
    char buyer[16] = "owner";
    int seen_buyer = 0;
    size_t cap = 16, nl = 0;
    char (*kinds)[8] = malloc(cap * 8);
    long long *prices = malloc(cap * sizeof(long long));
    const char *p = request;
    int lineno = 0;
    char *res = NULL;
    while (1) {
        const char *e = strchr(p, '\\n');
        size_t len = e ? (size_t)(e - p) : strlen(p);
        char *line = malloc(len + 1);
        memcpy(line, p, len);
        line[len] = 0;
        lineno++;
        char *f[8];
        int nf = split_fields(line, f, 8);
        if (nf > 0 && f[0][0] != '#') {
            if (HAS_BUYER && strcmp(f[0], BUYER_KW) == 0) {
                if (nf != 2) res = fail_at(lineno, "wrong field count");
                else if (!in_list(f[1], BUYERS, 4)) res = fail_at(lineno, "unknown buyer");
                else if (seen_buyer) res = fail_at(lineno, "duplicate buyer");
                else {
                    seen_buyer = 1;
                    strcpy(buyer, f[1]);
                }
            } else if (strcmp(f[0], LOT_KW) == 0) {
                char *kind = "";
                if (nf != (HAS_KINDS ? 3 : 2)) res = fail_at(lineno, "wrong field count");
                else {
                    if (HAS_KINDS) {
                        kind = f[1];
                        if (!in_list(kind, KINDS, 4)) res = fail_at(lineno, "unknown kind");
                    }
                    if (!res) {
                        char *pt = f[nf - 1];
                        size_t pl = strlen(pt);
                        int ok = pl >= 1 && pl <= 9;
                        for (size_t k = 0; ok && k < pl; k++)
                            if (pt[k] < '0' || pt[k] > '9') ok = 0;
                        if (!ok) res = fail_at(lineno, "bad price");
                        else {
                            if (nl == cap) {
                                cap *= 2;
                                kinds = realloc(kinds, cap * 8);
                                prices = realloc(prices, cap * sizeof(long long));
                            }
                            strcpy(kinds[nl], kind);
                            prices[nl] = atoll(pt);
                            nl++;
                        }
                    }
                }
            } else {
                res = fail_at(lineno, "unknown directive");
            }
        }
        free(line);
        if (res || !e) break;
        p = e + 1;
    }
    if (!res && nl == 0) res = dupstr("error: no lots");
    if (!res) {
        size_t ocap = 64 + nl * 48;
        res = malloc(ocap);
        res[0] = 0;
        long long total = 0;
        char tmp[96];
        for (size_t i = 0; i < nl; i++) {
            long long d = lot_duty(kinds[i], prices[i], buyer);
            total += d;
            if (HAS_KINDS) sprintf(tmp, "%s %lld %lld\\n", kinds[i], prices[i], d);
            else sprintf(tmp, "%lld %lld\\n", prices[i], d);
            strcat(res, tmp);
        }
        sprintf(tmp, "%s %lld", TOTAL, total);
        strcat(res, tmp);
    }
    free(kinds);
    free(prices);
    return res;
}
'''

SOURCES = {"python": PY, "javascript": JS, "go": GO, "rust": RS, "java": JV, "ruby": RB, "c": C}


def solution_for(lang, p):
    return _subst(lang, SOURCES[lang], p).lstrip("\n")


# ---------------------------------------------------------------------------------------------------------------
# README
# ---------------------------------------------------------------------------------------------------------------

def readme(p, api, lang, examples):
    region, unit = p["region"]
    lot, buyer = p["lot_kw"], p["buyer_kw"]
    kinds, has_buyer = p["kinds"], p["buyer"]
    bands = p["bands"]
    L = [f"# Stamp duty for {region}", ""]
    L.append(f"The land registry of {region} charges *stamp duty* on every purchase. This library turns a purchase request "
             f"(a small text) into a duty statement (another text). All amounts are whole {unit}; there are no decimals "
             f"in the input or the output.")
    L.append("")
    L.append("## Request format")
    L.append("")
    L.append("A request is a text with one directive per line (lines end with `\\n`; a final line without `\\n` is fine). "
             "Fields are separated by one or more spaces or tabs, and leading or trailing blanks are ignored. Blank lines "
             "and lines whose first non-blank character is `#` are skipped, but they still count when numbering lines "
             "(the first line is line 1). Directive names" + (" and kinds" if kinds else "") + " are lower-case and case-sensitive.")
    L.append("")
    if kinds:
        L.append(f"* `{lot} <kind> <price>`: one purchased lot. `<kind>` is `house`, `flat`, `land` or `farm`. At least one lot is required.")
    else:
        L.append(f"* `{lot} <price>`: one purchased lot. At least one lot is required.")
    if has_buyer:
        L.append(f"* `{buyer} <type>`: who is buying; `<type>` is `first`, `owner`, `investor` or `company`. It applies to every lot "
                 f"of the request wherever the line appears, and may be given at most once. Without it the buyer type is `owner`.")
    L.append("")
    L.append("A `<price>` is one to nine ASCII digits (leading zeros are fine, `007` is 7). Nothing else is a valid price: "
             "no sign, decimal point, separator or exponent.")
    L.append("")
    L.append("## Duty of one lot")
    L.append("")
    L.append("All arithmetic is exact (integers or fractions); rounding happens once, in the rounding step. The steps are:")
    L.append("")
    step = 1
    ex = []
    if kinds:
        ex.append(f"the kind is `land` and the price is below {p['land_floor']}")
    if has_buyer:
        ex.append(f"the buyer type is `first`, the kind is `house` or `flat`, and the price is {p['relief']} or less")
    if ex:
        L.append(f"{step}. **Exemption.** The duty of the lot is `0`, and all later steps are skipped, if " + ", or if ".join(ex) + ".")
        step += 1
    L.append(f"{step}. **Band duty.** The price is taxed in marginal bands: the part of the price above a band's lower bound, "
             f"up to the next band's lower bound, is charged at that band's rate. Rates are in basis points (1 bp = 0.01%).")
    L.append("")
    L.append("   | price above | rate (bp) |")
    L.append("   |---|---|")
    for lo, r in bands:
        L.append(f"   | {lo} | {r} |")
    L.append("")
    L.append("   The last band has no upper bound. A price equal to a lower bound has nothing in that band yet.")
    step += 1
    if kinds:
        L.append(f"{step}. **Farms.** For a `farm` lot the band duty is multiplied by {p['farm_pm']}/1000.")
        step += 1
    if has_buyer:
        L.append(f"{step}. **Surcharge.** For every lot that is not `land`, `price x bp / 10000` is added, where `bp` is "
                 f"{p['sur_investor']} for an `investor`, {p['sur_company']} for a `company` and 0 for any other buyer type.")
        step += 1
    rn = {0: "to the nearest whole number, ties (exactly .5) rounding up",
          1: "to the nearest whole number, ties (exactly .5) rounding down",
          2: "to the nearest multiple of 5, ties (exactly halfway between two multiples of 5) rounding up"}[p["round"]]
    L.append(f"{step}. **Rounding.** The exact sum of the previous steps is rounded {rn}.")
    step += 1
    if p["min_duty"]:
        L.append(f"{step}. **Minimum.** A lot whose rounded duty is greater than 0 but smaller than {p['min_duty']} pays {p['min_duty']} instead. "
                 f"A rounded duty of 0 stays 0.")
        step += 1
    L.append("")
    L.append("## Statement")
    L.append("")
    if kinds:
        L.append(f"One line `<kind> <price> <duty>` per lot, in request order (the price is printed as a plain integer, "
                 f"without leading zeros), then a last line `{p['total']} <sum of all lot duties>`. Lines are joined with `\\n`; "
                 f"there is no trailing newline.")
    else:
        L.append(f"One line `<price> <duty>` per lot, in request order (the price is printed as a plain integer, without "
                 f"leading zeros), then a last line `{p['total']} <sum of all lot duties>`. Lines are joined with `\\n`; there "
                 f"is no trailing newline.")
    L.append("")
    L.append("## Errors")
    L.append("")
    L.append("Lines are examined in order and the first problem decides the result, which is then *only* the error text "
             "(no statement). Within one line the checks run in the order listed.")
    L.append("")
    ck = ["`error: line N: unknown directive`: the first field is not a directive of this format"]
    ck.append("`error: line N: wrong field count`: the directive has too many or too few fields"
              + (" (a `" + lot + "` line needs exactly 3 fields, a `" + buyer + "` line exactly 2)" if has_buyer else
                 (" (a `" + lot + "` line needs exactly 3 fields)" if kinds else " (a `" + lot + "` line needs exactly 2 fields)")))
    if kinds:
        ck.append("`error: line N: unknown kind`")
    ck.append("`error: line N: bad price`")
    if has_buyer:
        ck.append(f"`error: line N: unknown buyer` (on a `{buyer}` line)")
        ck.append(f"`error: line N: duplicate buyer` (a second `{buyer}` line whose type is valid)")
    ck.append("`error: no lots`: the request has no `" + lot + "` line at all (including an empty request)")
    for c in ck:
        L.append(f"* {c}")
    L.append("")
    L.append("`N` is the 1-based line number of the offending line.")
    L.append("")
    L.append(K.interface_section(api, lang))
    L.append("## Examples")
    L.append("")
    for args, out in examples:
        L.append("Request:")
        L.append("")
        L.append(K.fence(args[0]))
        L.append("Statement:")
        L.append("")
        L.append(K.fence(out))
    L.append(K.run_hint(lang, api.mod))
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------------------------------------------
# cases
# ---------------------------------------------------------------------------------------------------------------

def make_cases(rng, p, ns):
    duty = ns["duty"]
    lot, bw = p["lot_kw"], p["buyer_kw"]
    kinds = p["kinds"]
    bands = p["bands"]
    cases: list[tuple] = []

    def L(kind, price, kw=None):
        return f"{kw or lot} {kind} {price}" if kinds else f"{kw or lot} {price}"

    def add(*lines, nl=False):
        t = "\n".join(lines) + ("\n" if nl else "")
        cases.append((t,))

    # examples
    ex_kinds = ["house", "flat", "land", "farm"]
    def rk():
        return rng.choice(ex_kinds)
    p1 = rng.randrange(40, 700) * 1000
    add(L(rk(), p1))
    add(L(rk(), rng.randrange(30, 500) * 1000), L(rk(), rng.randrange(30, 900) * 1000))
    if p["buyer"]:
        add(f"{bw} {rng.choice(['investor', 'company', 'first'])}", L("house", rng.randrange(100, 600) * 1000), "# note", L("land", rng.randrange(20, 120) * 1000))
    else:
        add("# two lots", L(rk(), rng.randrange(50, 600) * 1000), "", L(rk(), rng.randrange(50, 600) * 1000))
    nex = len(cases)
    # band boundaries
    for lo, _ in bands[1:]:
        for kk in ([rng.choice(["house", "flat"])] if kinds else [None]):
            add(L(kk, lo - 1), L(kk, lo), L(kk, lo + 1))
            add(L(kk, lo + rng.randrange(2, 5000)))
    add(L("house", 0) if kinds else L(None, 0))
    add(L("house", bands[-1][0] + 123456) if kinds else L(None, bands[-1][0] + 123456))
    if kinds:
        for k in KINDS:
            add(L(k, bands[-1][0] - rng.randrange(1, 30000)), L(k, bands[1][0] + rng.randrange(1, 9000)))
        add(L("land", p["land_floor"] - 1), L("land", p["land_floor"]), L("land", p["land_floor"] + 1))
        add(*[L(k, rng.randrange(20, 400) * 1000) for k in ex_kinds])
    # rounding ties
    # tie search is done with exact arithmetic replicated here (independent of rounding mode)
    def exact7(kind, price, buyer):
        if kinds and kind == "land" and price < p["land_floor"]:
            return None
        if p["buyer"] and buyer == "first" and kind in ("house", "flat") and price <= p["relief"]:
            return None
        num = 0
        for i, (lo, rate) in enumerate(bands):
            if price > lo:
                top = price if (i + 1 >= len(bands) or bands[i + 1][0] >= price) else bands[i + 1][0]
                num += (top - lo) * rate
        num *= p["farm_pm"] if (kinds and kind == "farm") else 1000
        if p["buyer"] and kind != "land":
            sur = p["sur_investor"] if buyer == "investor" else p["sur_company"] if buyer == "company" else 0
            num += price * sur * 1000
        return num
    tie_kind = "house" if kinds else ""
    for base in (bands[-1][0] + 7, bands[1][0] + 11, (bands[1][0] + bands[-1][0]) // 2 + 3):
        lo = base
        for pr in range(lo, lo + 300000):
            e = exact7(tie_kind, pr, "owner")
            if e is None:
                continue
            m = e % (10000000 if p["round"] != 2 else 50000000)
            half = 5000000 if p["round"] != 2 else 25000000
            if m == half:
                add(L(tie_kind or None, pr), L(tie_kind or None, pr + 1))
                break
    if p["min_duty"]:
        k0 = tie_kind or None
        for pr in range(bands[1][0] + 1, bands[1][0] + 40000):
            e = exact7(tie_kind, pr, "owner")
            d = ns["_lot_duty"](tie_kind, pr, "owner")
            if e and 0 < d <= p["min_duty"] // 2 + 1 and d < p["min_duty"]:
                add(L(k0, pr), L(k0, bands[1][0] + 1))
                break
        add(L(k0, bands[1][0]), L(k0, bands[1][0] + 1))
    # buyers
    if p["buyer"]:
        for b in BUYERS:
            add(f"{bw} {b}", L("house", p["relief"]), L("flat", p["relief"] + 1), L("land", p["land_floor"] + 5000), L("farm", rng.randrange(80, 500) * 1000))
        add(L("flat", p["relief"] - 1), f"{bw} first", L("farm", p["relief"]), L("land", p["relief"]))
        add(f"{bw} investor", L("flat", rng.randrange(50, 150) * 1000), L("land", rng.randrange(30, 90) * 1000))
        add(f"  {bw}\tcompany  ", f"\t{L('house', rng.randrange(100, 800) * 1000)}")
    # formatting
    k = "house" if kinds else None
    add("", "# header", f"   {L(k, rng.randrange(30, 300) * 1000)}", "\t# indented comment", L(k, rng.randrange(30, 300) * 1000), "", nl=True)
    add(f"{lot}\t{'flat' if kinds else '00' + str(rng.randrange(10, 99))}  {'0' + str(rng.randrange(100000, 300000)) if kinds else str(rng.randrange(100000, 300000))}")
    add(L(k, 999999999), L(k, 7))
    add(L(k, "000" + str(rng.randrange(100, 900) * 1000)))
    # errors
    add("")
    add("# only a comment", "   ", "\t")
    add(L(k, 120000), "frobnicate 12", L(k, 5))
    add(f"{lot}")
    add(L(k, 100000) + " extra")
    add(f"{lot} 1 2 3 4")
    add(L(k, "-5"))
    add(L(k, "12.5"))
    add(L(k, "1,000"))
    add(L(k, "1e5"))
    add(L(k, "1234567890"))
    add(L(k, "12o4"))
    add(L(k, "+500"))
    add(L(k, "12 000"))
    add(L(k, 5), f"{lot.upper()} {'house ' if kinds else ''}100000")
    add("# top", "", f"{lot}s 5", L(k, "abc"))
    if kinds:
        add(L("barn", 5000))
        add(L("House", 5000))
        add(L("barn", "x"), L("land", 5))
        add(f"{lot} house", L("flat", 5))
    if p["buyer"]:
        add(f"{bw} tourist", L("house", 100000))
        add(f"{bw} first", L("house", 100000), f"{bw} owner")
        add(f"{bw} first", f"{bw} wizard")
        add(f"{bw}", L("house", 5))
        add(f"{bw} first extra", L("house", 5))
        add(L("house", 100000), f"{bw} Investor")
        add(L("house", 100000), f"{bw} investor", L("flat", 50000), f"{bw} company")
        add(f"{bw} company", "oops", f"{bw} bad")
        add(f"{bw} company", L("house", "9x"), f"{bw} company")
    else:
        add(f"buyer first", L(k, 100000))
    add(f"{lot}x {'house ' if kinds else ''}500")
    # random deals
    for _ in range(5):
        lines = []
        if p["buyer"] and rng.random() < 0.8:
            lines.append(f"{bw} {rng.choice(BUYERS)}")
        for _ in range(rng.randrange(1, 6)):
            lines.append(L(rng.choice(ex_kinds) if kinds else None, rng.randrange(1, 1200) * rng.choice([1, 10, 100, 1000])))
        if p["buyer"] and lines[0].startswith(bw) and rng.random() < 0.4:
            lines.append(lines.pop(0))
        add(*lines)
    # unique, keep examples first
    out, seen = [], set()
    for c in cases:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out, nex


# ---------------------------------------------------------------------------------------------------------------
# prompts
# ---------------------------------------------------------------------------------------------------------------

def prompt(rng, p, api, lang, level):
    region, unit = p["region"]
    where = api.where(lang)
    fn = api.name(lang)
    ln = K.LANG_NAME[lang]
    opts = [
        f"Could you write the stamp-duty calculator for {region} in {ln}? The whole rulebook is in README.md (bands, exemptions, "
        f"the statement layout and the error texts). The entry point is `{fn}`, to be implemented in {where}. {K.closer(rng)}",
        f"I'm building a tiny conveyancing helper and need the duty maths for {region} as a {ln} library. README.md has the spec: "
        f"request format in, statement out, errors as plain text. Implement `{fn}` in {where}; the visible tests show the call shape "
        f"and there are more checks behind them. {K.closer(rng)}",
        f"Task: implement `{fn}` ({ln}) following README.md. It converts a purchase request into the duty statement used by the land "
        f"registry of {region}. Where: {where}. Work from the README only; the exact rounding and error rules are spelled out there.",
        f"our clerks in {region} still do duty by hand. please turn the rules in README.md into code ({ln}, function `{fn}`, "
        f"{where}). watch the band boundaries and the error line numbers. {K.closer(rng)}",
        f"Greenfield job: the repo has a README.md describing how {region} computes stamp duty on a request text, plus a stub for `{fn}` "
        f"and a few example tests. Replace the stub with a real implementation ({ln}). {K.closer(rng)}",
    ]
    return rng.choice(opts).strip()


@family("greenfield-stampduty", category="greenfield", lang="mixed", kind="greenfield", n=12,
        summary="stamp-duty statement from a request text: marginal bands, exemptions, surcharges, rounding mode, line-numbered errors")
def gen(rng, n):
    levels = [1, 1, 2, 2, 2, 3, 3, 3, 3, 2, 3, 1]
    for i in range(n):
        lang = LANG_PLAN[i % len(LANG_PLAN)]
        level = levels[i % len(levels)]
        p = params(rng, level)
        api = K.Api(mod="stampduty", fn="duty", args=["request"], arg_docs=["the purchase request text"], ret_doc="the duty statement (or an error line)",
                    doc=f"stamp duty for {p['region'][0]}")
        py_src = solution_for("python", p)
        ns = K.py_namespace(py_src)
        cases, nex = make_cases(rng, p, ns)
        sols = {lang: solution_for(lang, p)}
        sols["python"] = py_src
        examples_out = [(c, ns["duty"](*c)) for c in cases[:nex]]
        rd = readme(p, api, lang, examples_out)
        yield K.lib_task(
            api=api, lang=lang, readme=rd, solutions=sols, cases=cases, examples=nex,
            prompt=prompt(rng, p, api, lang, level), difficulty=level, slug=f"{i + 1:02d}-{lang}-{p['region'][0].lower().replace(' ', '-').replace('the-', '')}",
            oracle=(None if lang == "python" else ns["duty"]), tags=["parser", "money"],
            notes={"level": level, "bands": p["bands"], "round": p["round"], "min_duty": p["min_duty"]},
        )
