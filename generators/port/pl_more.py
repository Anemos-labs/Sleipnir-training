"""More port libraries: property transfer duty with money text (Python / PHP / Ruby), podcast chapter marks (Python / Ruby / TypeScript) and a 12-bit CRC asset tag (C / Rust / Python)."""
from fx import dd

from ._portlib import PortLib, register_port
from ._types import Fn

# ======================================================================================================================
# stamp-duty: progressive duty bands with per-band rounding, relief and surcharge, plus strict money text
# ======================================================================================================================

SD_SPEC = dd('''
    The land registry of the fictional state of Verdania charges **transfer duty** on property purchases. All amounts are whole **cents** (integers); the price of a purchase is at most 10^12 cents.

    Standard bands (the amount of the price that falls into each band is charged at that band's rate in basis points, 1 bp = 0.01 %):

    | band | from (cents) | up to (cents) | rate |
    |---|---|---|---|
    | 1 | 0 | 20,000,000 | 0 bp |
    | 2 | 20,000,000 | 35,000,000 | 250 bp |
    | 3 | 35,000,000 | 75,000,000 | 475 bp |
    | 4 | 75,000,000 | no limit | 710 bp |

    * The duty of one band is `portion * rate / 10000` **rounded half up to a whole cent per band** (`(portion * rate + 5000) div 10000`); the duty is the sum of the four rounded amounts. `band_table(price)` lists the four amounts.
    * **First-time buyers** (`first_time`) of a property that costs at most 60,000,000 cents pay no duty up to 35,000,000 and the usual rates above (band 3 and 4 as in the table; the 250 bp band does not apply to them). Above 60,000,000 cents there is no relief and the standard bands apply.
    * **Additional property** (`additional`) adds a surcharge of 300 bp of the *whole price*, rounded half up to a cent, to the standard duty. A purchase cannot be both first-time and additional.
    * `duty_cents(price, first_time, additional)` is the duty. A price outside 0..10^12 or the impossible combination is an error. `effective_bp(price, first_time, additional)` is `floor(duty * 10000 / price)` (0 for a price of 0).
    * `price_for_duty(duty)` is the highest price in 0..10^12 whose **standard** duty (no relief, no surcharge) is not more than `duty` (a negative `duty` is an error; a duty that is at least the duty of 10^12 gives 10^12).
    * `format_money(cents)` writes `[-]D,DDD,DDD.CC`: thousands separators in the dollars, always two decimals, `-` for negative amounts (`0.05`, `1,234.50`, `-12.00`). `|cents|` is at most 10^15.
    * `parse_money(text)` reads exactly that notation, and plain digits without separators too: an optional `-`, the dollars (`0`, or a digit 1-9 followed by digits with no leading zeros, with at most 13 digits; either without any comma or with the commas in correct groups of three, `1,234,567`), and either nothing or a `.` and exactly two digits.
      Without decimals the amount is whole dollars (`12` is 1200 cents). `-0` and `-0.00` are 0. Anything else (spaces, `+`, `1,23`, `1234,567`, `.5`, `1.5`, `007`, a sign after the digits, non-ASCII digits, a newline at the end) is an error.
''')

SD_FNS = [
    Fn("duty_cents", [("price", "int"), ("first_time", "bool"), ("additional", "bool")], "int", err=True),
    Fn("effective_bp", [("price", "int"), ("first_time", "bool"), ("additional", "bool")], "int", err=True),
    Fn("band_table", [("price", "int")], "list<int>", err=True),
    Fn("price_for_duty", [("duty", "int")], "int", err=True),
    Fn("format_money", [("cents", "int")], "str", err=True),
    Fn("parse_money", [("text", "str")], "int", err=True),
]

SD_PY = dd(r'''
import re

MAX_PRICE = 10 ** 12
_STANDARD = [(0, 20000000, 0), (20000000, 35000000, 250), (35000000, 75000000, 475), (75000000, None, 710)]
_RELIEF = [(0, 35000000, 0), (35000000, 75000000, 475), (75000000, None, 710)]
_PLAIN = re.compile(r"(-?)(0|[1-9][0-9]*)(?:\.([0-9]{2}))?")
_GROUPED = re.compile(r"(-?)([1-9][0-9]{0,2}(?:,[0-9]{3})+)(?:\.([0-9]{2}))?")


def _bands(price, bands):
    out = []
    for lo, hi, bp in bands:
        top = price if hi is None else min(price, hi)
        portion = max(0, top - lo)
        out.append((portion * bp + 5000) // 10000)
    return out


def _check_price(price):
    if not 0 <= price <= MAX_PRICE:
        raise ValueError("price out of range")


def duty_cents(price, first_time, additional):
    _check_price(price)
    if first_time and additional:
        raise ValueError("cannot be both first-time and additional")
    if first_time and price <= 60000000:
        return sum(_bands(price, _RELIEF))
    duty = sum(_bands(price, _STANDARD))
    if additional:
        duty += (price * 300 + 5000) // 10000
    return duty


def effective_bp(price, first_time, additional):
    duty = duty_cents(price, first_time, additional)
    return 0 if price == 0 else duty * 10000 // price


def band_table(price):
    _check_price(price)
    return _bands(price, _STANDARD)


def price_for_duty(duty):
    if duty < 0:
        raise ValueError("negative duty")
    if duty >= sum(_bands(MAX_PRICE, _STANDARD)):
        return MAX_PRICE
    lo, hi = 0, MAX_PRICE
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if sum(_bands(mid, _STANDARD)) <= duty:
            lo = mid
        else:
            hi = mid
    return lo


def format_money(cents):
    if abs(cents) > 10 ** 15:
        raise ValueError("amount out of range")
    sign = "-" if cents < 0 else ""
    dollars, rest = divmod(abs(cents), 100)
    return "%s%s.%02d" % (sign, "{:,}".format(dollars), rest)


def parse_money(text):
    m = _PLAIN.fullmatch(text) or _GROUPED.fullmatch(text)
    if not m:
        raise ValueError("bad money text")
    digits = m.group(2).replace(",", "")
    if len(digits) > 13:
        raise ValueError("amount too large")
    cents = int(digits) * 100 + int(m.group(3) or 0)
    return -cents if m.group(1) else cents
''')

SD_PHP = dd(r'''
<?php
final class StampDuty
{
    private const MAX_PRICE = 1000000000000;

    private static function bands(int $price, bool $relief): array
    {
        $table = $relief
            ? [[0, 35000000, 0], [35000000, 75000000, 475], [75000000, null, 710]]
            : [[0, 20000000, 0], [20000000, 35000000, 250], [35000000, 75000000, 475], [75000000, null, 710]];
        $out = [];
        foreach ($table as [$lo, $hi, $bp]) {
            $top = $hi === null ? $price : min($price, $hi);
            $portion = max(0, $top - $lo);
            $out[] = intdiv($portion * $bp + 5000, 10000);
        }
        return $out;
    }

    private static function checkPrice(int $price): void
    {
        if ($price < 0 || $price > self::MAX_PRICE) throw new InvalidArgumentException('price out of range');
    }

    public static function dutyCents(int $price, bool $firstTime, bool $additional): int
    {
        self::checkPrice($price);
        if ($firstTime && $additional) throw new InvalidArgumentException('cannot be both');
        if ($firstTime && $price <= 60000000) return array_sum(self::bands($price, true));
        $duty = array_sum(self::bands($price, false));
        if ($additional) $duty += intdiv($price * 300 + 5000, 10000);
        return $duty;
    }

    public static function effectiveBp(int $price, bool $firstTime, bool $additional): int
    {
        $duty = self::dutyCents($price, $firstTime, $additional);
        return $price === 0 ? 0 : intdiv($duty * 10000, $price);
    }

    public static function bandTable(int $price): array
    {
        self::checkPrice($price);
        return self::bands($price, false);
    }

    public static function priceForDuty(int $duty): int
    {
        if ($duty < 0) throw new InvalidArgumentException('negative duty');
        if ($duty >= array_sum(self::bands(self::MAX_PRICE, false))) return self::MAX_PRICE;
        $lo = 0;
        $hi = self::MAX_PRICE;
        while ($hi - $lo > 1) {
            $mid = intdiv($lo + $hi, 2);
            if (array_sum(self::bands($mid, false)) <= $duty) $lo = $mid; else $hi = $mid;
        }
        return $lo;
    }

    public static function formatMoney(int $cents): string
    {
        if (abs($cents) > 1000000000000000) throw new InvalidArgumentException('amount out of range');
        $sign = $cents < 0 ? '-' : '';
        $abs = abs($cents);
        return sprintf('%s%s.%02d', $sign, number_format(intdiv($abs, 100), 0, '.', ','), $abs % 100);
    }

    public static function parseMoney(string $text): int
    {
        if (!preg_match('/\A(-?)(0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+)(?:\.([0-9]{2}))?\z/', $text, $m)) {
            throw new InvalidArgumentException('bad money text');
        }
        $digits = str_replace(',', '', $m[2]);
        if (strlen($digits) > 13) throw new InvalidArgumentException('amount too large');
        $cents = intval($digits) * 100 + (isset($m[3]) && $m[3] !== '' ? intval($m[3]) : 0);
        return $m[1] === '-' ? -$cents : $cents;
    }
}
''')

SD_RB = dd(r'''
module StampDuty
  MAX_PRICE = 10**12
  STANDARD = [[0, 20_000_000, 0], [20_000_000, 35_000_000, 250], [35_000_000, 75_000_000, 475], [75_000_000, nil, 710]].freeze
  RELIEF = [[0, 35_000_000, 0], [35_000_000, 75_000_000, 475], [75_000_000, nil, 710]].freeze
  MONEY = /\A(-?)(0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+)(?:\.([0-9]{2}))?\z/

  def self.bands(price, table)
    table.map do |lo, hi, bp|
      top = hi.nil? ? price : [price, hi].min
      portion = [0, top - lo].max
      (portion * bp + 5000) / 10_000
    end
  end

  def self.check_price(price)
    raise ArgumentError, 'price out of range' if price < 0 || price > MAX_PRICE
  end

  def self.duty_cents(price, first_time, additional)
    check_price(price)
    raise ArgumentError, 'cannot be both' if first_time && additional
    return bands(price, RELIEF).sum if first_time && price <= 60_000_000
    duty = bands(price, STANDARD).sum
    duty += (price * 300 + 5000) / 10_000 if additional
    duty
  end

  def self.effective_bp(price, first_time, additional)
    duty = duty_cents(price, first_time, additional)
    price == 0 ? 0 : duty * 10_000 / price
  end

  def self.band_table(price)
    check_price(price)
    bands(price, STANDARD)
  end

  def self.price_for_duty(duty)
    raise ArgumentError, 'negative duty' if duty < 0
    return MAX_PRICE if duty >= bands(MAX_PRICE, STANDARD).sum
    lo = 0
    hi = MAX_PRICE
    while hi - lo > 1
      mid = (lo + hi) / 2
      if bands(mid, STANDARD).sum <= duty
        lo = mid
      else
        hi = mid
      end
    end
    lo
  end

  def self.format_money(cents)
    raise ArgumentError, 'amount out of range' if cents.abs > 10**15
    dollars, rest = cents.abs.divmod(100)
    grouped = dollars.to_s.reverse.scan(/\d{1,3}/).join(',').reverse
    format('%s%s.%02d', cents < 0 ? '-' : '', grouped, rest)
  end

  def self.parse_money(text)
    m = MONEY.match(text)
    raise ArgumentError, 'bad money text' if m.nil?
    digits = m[2].delete(',')
    raise ArgumentError, 'amount too large' if digits.length > 13
    cents = digits.to_i * 100 + (m[3] || '0').to_i
    m[1] == '-' ? -cents : cents
  end
end
''')


def sd_cases(rng):
    edges = [0, 1, 19999999, 20000000, 20000001, 34999999, 35000000, 35000001, 59999999, 60000000, 60000001, 74999999, 75000000, 75000001, 199999999, 350000000, 600000000, 10 ** 12 - 1, 10 ** 12, 10 ** 12 + 1, -1, 50, 99, 100, 20000003, 40000000, 80000000]
    out = [("duty_cents", [40000000, False, False]), ("duty_cents", [40000000, True, False]), ("duty_cents", [40000000, False, True]), ("effective_bp", [80000000, False, False]), ("band_table", [80000000]), ("price_for_duty", [1000000]),
           ("format_money", [123456]), ("parse_money", ["1,234.56"])]
    for p in edges:
        out.append(("band_table", [p]))
        for ft, ad in [(False, False), (True, False), (False, True), (True, True)]:
            out.append(("duty_cents", [p, ft, ad]))
            out.append(("effective_bp", [p, ft, ad]))
    for _ in range(40):
        p = rng.choice([rng.randint(0, 80000000), rng.randint(0, 10 ** 12), rng.randint(19000000, 36000000), rng.randint(59000000, 61000000), rng.randint(74000000, 76000000)])
        ft, ad = rng.choice([(False, False), (True, False), (False, True)])
        out.append(("duty_cents", [p, ft, ad]))
        out.append(("effective_bp", [p, ft, ad]))
        out.append(("band_table", [p]))
    for d in [0, 1, 2, 5, 6, 7, 4999, 5000, 5001, 375000, 375001, 1000000, 1337500, 2000000, 3557500, 3557501, 100000000, 7100000000, 7200000000, 10 ** 11, 10 ** 12, -1, -100]:
        out.append(("price_for_duty", [d]))
    for _ in range(15):
        out.append(("price_for_duty", [rng.randint(0, 80000000)]))
    for c in [0, 5, 99, 100, 101, 123456, 100000, 99999999, 100000000, 123456789012, -5, -100, -123456, 10 ** 15, -(10 ** 15), 10 ** 15 + 1, -(10 ** 15) - 1, 1000, 100050, 987654321]:
        out.append(("format_money", [c]))
    for _ in range(20):
        out.append(("format_money", [rng.randint(-10 ** 13, 10 ** 13)]))
    texts = ["0", "0.00", "-0", "-0.00", "12", "12.00", "12.5", "12.345", "1,234.50", "1,234", "1234.50", "1234", "12,34", "1,23", "1234,567", "1,234,567.89", "1,234,5678", ",123", "123,", "1,,234", ".5", "5.", "1.5", "007", "-007", "00", "0,000", "+12", "- 12", "-12", "12-", "-1,000.00",
             "1 234", " 12", "12 ", "12\n", "\u0661\u0662", "12.\u0665\u0665", "1e3", "0x10", "12.00.00", "", "-", ".", "1,000,000,000,000.00", "9,999,999,999,999.99", "99999999999999.99", "9999999999999.99", "10,000,000,000,000", "1000000000000000", "1.00", "0.01", "0.1", "-0.01", "999,999", "1,000", "100,000,000", "01,000", "1,000.0",
             "1,000.000", "1.000", "12,345.6", "$12", "12 00", "\u00bd", "1\u202f000", "1,0000"]
    for t in texts:
        out.append(("parse_money", [t]))
    for _ in range(30):
        c = rng.randint(-10 ** 12, 10 ** 12)
        out.append(("parse_money", [_fmt(c)]))
        out.append(("parse_money", [_fmt(c).replace(",", "")]))
    return out


def _fmt(c):
    sign = "-" if c < 0 else ""
    d, r = divmod(abs(c), 100)
    return "%s%s.%02d" % (sign, "{:,}".format(d), r)


SD = PortLib(
    slug="stamp-duty",
    title="property transfer duty",
    blurb="The land registry of an invented state charges transfer duty in bands with per-band rounding, relief for first-time buyers and a surcharge, and prints amounts with strict money notation.",
    spec=SD_SPEC,
    fns=SD_FNS,
    impls={"python": {"stamp_duty.py": SD_PY}, "php": {"src/StampDuty.php": SD_PHP}, "ruby": {"lib/stamp_duty.rb": SD_RB}},
    cases=sd_cases,
    difficulty=2,
    n_examples=10,
    pairs=[("python", "php", "full"), ("php", "ruby", "full"), ("ruby", "python", "stub"), ("python", "ruby", "stub")],
    traps=["integer division and rounding per band", "PHP integer/float arithmetic", "strict money grammar (grouping, trailing newline, non-ASCII digits)", "inverse of a step function by search"],
    tags=["money", "rounding", "strict-parsing"],
)
register_port(SD, __name__)

# ======================================================================================================================
# chapter-marks: podcast chapter lists
# ======================================================================================================================

CM_SPEC = dd('''
    Podcast chapters are written one per line as `<timestamp> <title>`. Everything is counted in **milliseconds**.

    * **Timestamps** have two forms: `H:MM:SS` with 1 to 3 hour digits and exactly two digits each for minutes and seconds (minutes and seconds 00..59), or `M:SS` with 1 to 3 minute digits (any value, so `75:30` is allowed) and two second digits (00..59).
      Either may end in a fraction: a `.` and 1 to 3 digits, padded on the right with zeros (`.5` is 500 ms, `.05` is 50 ms, `.123` is 123 ms). ASCII digits only; no signs, no spaces. `parse_ts(text)` returns the milliseconds, anything else is an error.
    * `fmt_ts(ms)` is the canonical text `HH:MM:SS.mmm` (hours at least two digits, no upper limit: `3600000` is `01:00:00.000`, `360000000` is `100:00:00.000`); a negative `ms` is an error.
    * **Chapter lists.** *White space* is a space or a tab and nothing else (a no-break space or a carriage return in the middle of a title is just a character). Lines end with `\\n` or `\\r\\n`; a line is skipped when it is empty after trimming white space or when its first non-blank character is `#`.
      Every other line is a timestamp, then at least one white space character, then the title: it is trimmed, and every run of white space inside it becomes one space. A title must have 1 to 200 characters (Unicode code points) after that. A line without a title or with a bad timestamp is an error.
    * `normalize(text)` sorts the chapters by time (equal times keep their order) and writes them as `fmt_ts(ms) + " " + title` joined by `\\n` (no final newline). It is an error when there are no chapters, when two chapters have the same time, or when the earliest does not start at 0.
    * `durations(text, total_ms)` is the length of every chapter in sorted order: the next start minus its own start, the last one up to `total_ms`; `total_ms` must be greater than the last start (else an error).
    * `chapter_at(text, ms, total_ms)` is the title of the chapter that contains the time `ms` (a chapter lasts from its start up to, not including, the next start), with `0 <= ms < total_ms` (else an error); the same list rules apply.
''')

CM_FNS = [
    Fn("parse_ts", [("text", "str")], "int", err=True),
    Fn("fmt_ts", [("ms", "int")], "str", err=True),
    Fn("normalize", [("text", "str")], "str", err=True),
    Fn("durations", [("text", "str"), ("total_ms", "int")], "list<int>", err=True),
    Fn("chapter_at", [("text", "str"), ("ms", "int"), ("total_ms", "int")], "str", err=True),
]

CM_PY = dd(r'''
import re

_TS = re.compile(r"(?:([0-9]{1,3}):([0-5][0-9])|([0-9]{1,3})):([0-5][0-9])(?:\.([0-9]{1,3}))?")
_WS = " \t"


def parse_ts(text):
    m = _TS.fullmatch(text)
    if not m:
        raise ValueError("bad timestamp")
    hours_form = m.group(1) is not None
    if hours_form:
        total = (int(m.group(1)) * 60 + int(m.group(2))) * 60 + int(m.group(4))
    else:
        total = int(m.group(3)) * 60 + int(m.group(4))
    frac = m.group(5)
    return total * 1000 + (int(frac.ljust(3, "0")) if frac else 0)


def fmt_ts(ms):
    if ms < 0:
        raise ValueError("negative time")
    secs, milli = divmod(ms, 1000)
    mins, sec = divmod(secs, 60)
    hours, minute = divmod(mins, 60)
    return "%02d:%02d:%02d.%03d" % (hours, minute, sec, milli)


def _collapse(title):
    out = []
    pending = False
    for ch in title:
        if ch in _WS:
            pending = bool(out)
        else:
            if pending:
                out.append(" ")
                pending = False
            out.append(ch)
    return "".join(out)


def _chapters(text):
    items = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip(_WS)
        if not line or line[0] == "#":
            continue
        cut = 0
        while cut < len(line) and line[cut] not in _WS:
            cut += 1
        stamp, title = line[:cut], _collapse(line[cut:].strip(_WS))
        if not title or len(title) > 200:
            raise ValueError("bad chapter title")
        items.append((parse_ts(stamp), title))
    items.sort(key=lambda it: it[0])
    if not items or items[0][0] != 0:
        raise ValueError("the first chapter must start at 0")
    if any(a[0] == b[0] for a, b in zip(items, items[1:])):
        raise ValueError("two chapters start at the same time")
    return items


def normalize(text):
    return "\n".join("%s %s" % (fmt_ts(ms), title) for ms, title in _chapters(text))


def durations(text, total_ms):
    items = _chapters(text)
    if total_ms <= items[-1][0]:
        raise ValueError("total is not after the last chapter start")
    starts = [ms for ms, _ in items] + [total_ms]
    return [b - a for a, b in zip(starts, starts[1:])]


def chapter_at(text, ms, total_ms):
    items = _chapters(text)
    if not 0 <= ms < total_ms or total_ms <= items[-1][0]:
        raise ValueError("time out of range")
    title = items[0][1]
    for start, name in items:
        if start <= ms:
            title = name
    return title
''')

CM_RB = dd(r'''
module ChapterMarks
  TS = /\A(?:([0-9]{1,3}):([0-5][0-9])|([0-9]{1,3})):([0-5][0-9])(?:\.([0-9]{1,3}))?\z/
  BLANKS = " \t"

  def self.parse_ts(text)
    m = TS.match(text)
    raise ArgumentError, 'bad timestamp' if m.nil?
    total = if m[1]
              (m[1].to_i * 60 + m[2].to_i) * 60 + m[4].to_i
            else
              m[3].to_i * 60 + m[4].to_i
            end
    total * 1000 + (m[5] ? m[5].ljust(3, '0').to_i : 0)
  end

  def self.fmt_ts(ms)
    raise ArgumentError, 'negative time' if ms < 0
    secs, milli = ms.divmod(1000)
    mins, sec = secs.divmod(60)
    hours, minute = mins.divmod(60)
    format('%02d:%02d:%02d.%03d', hours, minute, sec, milli)
  end

  def self.trim(text)
    a = 0
    b = text.length
    a += 1 while a < b && BLANKS.include?(text[a])
    b -= 1 while b > a && BLANKS.include?(text[b - 1])
    text[a...b]
  end

  def self.collapse(title)
    out = +''
    pending = false
    title.each_char do |ch|
      if BLANKS.include?(ch)
        pending = !out.empty?
      else
        if pending
          out << ' '
          pending = false
        end
        out << ch
      end
    end
    out
  end

  def self.chapters(text)
    items = []
    text.gsub("\r\n", "\n").split("\n", -1).each do |raw|
      line = trim(raw)
      next if line.empty? || line[0] == '#'
      cut = 0
      cut += 1 while cut < line.length && !BLANKS.include?(line[cut])
      title = collapse(trim(line[cut..]))
      raise ArgumentError, 'bad chapter title' if title.empty? || title.length > 200
      items << [parse_ts(line[0...cut]), title]
    end
    items = items.each_with_index.sort_by { |(ms, _), i| [ms, i] }.map(&:first)
    raise ArgumentError, 'the first chapter must start at 0' if items.empty? || items[0][0] != 0
    items.each_cons(2) { |a, b| raise ArgumentError, 'same start' if a[0] == b[0] }
    items
  end

  def self.normalize(text)
    chapters(text).map { |ms, title| "#{fmt_ts(ms)} #{title}" }.join("\n")
  end

  def self.durations(text, total_ms)
    items = chapters(text)
    raise ArgumentError, 'total is not after the last chapter start' if total_ms <= items[-1][0]
    starts = items.map(&:first) + [total_ms]
    starts.each_cons(2).map { |a, b| b - a }
  end

  def self.chapter_at(text, ms, total_ms)
    items = chapters(text)
    raise ArgumentError, 'time out of range' if ms < 0 || ms >= total_ms || total_ms <= items[-1][0]
    title = items[0][1]
    items.each { |start, name| title = name if start <= ms }
    title
  end
end
''')

CM_TS = dd(r'''
const TS = /^(?:([0-9]{1,3}):([0-5][0-9])|([0-9]{1,3})):([0-5][0-9])(?:\.([0-9]{1,3}))?$/;

function isBlank(c: string): boolean {
  return c === ' ' || c === '\t';
}

export function parseTs(text: string): number {
  const m = TS.exec(text);
  if (!m) throw new Error('bad timestamp');
  const total = m[1] !== undefined ? (parseInt(m[1], 10) * 60 + parseInt(m[2], 10)) * 60 + parseInt(m[4], 10) : parseInt(m[3], 10) * 60 + parseInt(m[4], 10);
  return total * 1000 + (m[5] !== undefined ? parseInt(m[5].padEnd(3, '0'), 10) : 0);
}

function pad(n: number, width: number): string {
  return String(n).padStart(width, '0');
}

export function fmtTs(ms: number): string {
  if (ms < 0) throw new Error('negative time');
  const secs = Math.floor(ms / 1000);
  const milli = ms - secs * 1000;
  const mins = Math.floor(secs / 60);
  const sec = secs - mins * 60;
  const hours = Math.floor(mins / 60);
  const minute = mins - hours * 60;
  return pad(hours, 2) + ':' + pad(minute, 2) + ':' + pad(sec, 2) + '.' + pad(milli, 3);
}

function trim(text: string[]): string[] {
  let a = 0;
  let b = text.length;
  while (a < b && isBlank(text[a])) a++;
  while (b > a && isBlank(text[b - 1])) b--;
  return text.slice(a, b);
}

function collapse(title: string[]): string {
  let out = '';
  let pending = false;
  for (const ch of title) {
    if (isBlank(ch)) {
      pending = out.length > 0;
    } else {
      if (pending) {
        out += ' ';
        pending = false;
      }
      out += ch;
    }
  }
  return out;
}

function chapters(text: string): Array<[number, string]> {
  const items: Array<[number, string, number]> = [];
  text.replace(/\r\n/g, '\n').split('\n').forEach((raw) => {
    const line = trim(Array.from(raw));
    if (line.length === 0 || line[0] === '#') return;
    let cut = 0;
    while (cut < line.length && !isBlank(line[cut])) cut++;
    const title = collapse(trim(line.slice(cut)));
    const count = Array.from(title).length;
    if (count === 0 || count > 200) throw new Error('bad chapter title');
    items.push([parseTs(line.slice(0, cut).join('')), title, items.length]);
  });
  items.sort((a, b) => a[0] - b[0] || a[2] - b[2]);
  if (items.length === 0 || items[0][0] !== 0) throw new Error('the first chapter must start at 0');
  for (let i = 1; i < items.length; i++) {
    if (items[i][0] === items[i - 1][0]) throw new Error('two chapters start at the same time');
  }
  return items.map((it): [number, string] => [it[0], it[1]]);
}

export function normalize(text: string): string {
  return chapters(text).map(([ms, title]) => fmtTs(ms) + ' ' + title).join('\n');
}

export function durations(text: string, totalMs: number): number[] {
  const items = chapters(text);
  if (totalMs <= items[items.length - 1][0]) throw new Error('total is not after the last chapter start');
  const starts = items.map((it) => it[0]).concat([totalMs]);
  return starts.slice(1).map((b, i) => b - starts[i]);
}

export function chapterAt(text: string, ms: number, totalMs: number): string {
  const items = chapters(text);
  if (ms < 0 || ms >= totalMs || totalMs <= items[items.length - 1][0]) throw new Error('time out of range');
  let title = items[0][1];
  for (const [start, name] of items) {
    if (start <= ms) title = name;
  }
  return title;
}
''')

CM_LISTS = [
    "00:00 Intro\n02:30 Interview with Ana\n45:10.5 Listener mail\n1:02:03.25 Outro",
    "0:00 Start\r\n1:00 Middle\r\n2:00 End\r\n",
    "# chapters\n\n  00:00\tCold open  \n 01:30   The  big   topic \n\t# a comment\n10:00 Wrap-up",
    "05:00 Second\n00:00 First\n05:00.001 Third",
    "00:00 Only",
    "0:00 caf\u00e9 \u2603 \U0001f600\n1:00 \u00a0nbsp\u00a0 title",
    "0:00 A\n1:00 B\n1:00 C",
    "0:00 A\n1:00 B\n2:00",
    "0:00 A\n1:00",
    "0:01 Late start",
    "",
    "# nothing but a comment\n\n",
    "0:00 " + "x" * 200 + "\n1:00 B",
    "0:00 " + "x" * 201 + "\n1:00 B",
    "0:00 " + "\u00e9" * 200,
    "0:00 " + "\U0001f600" * 200,
    "0:00 " + "\U0001f600" * 201,
    "0:00 A\n0:60 B",
    "0:00 A\n75:30 B",
    "0:00 A\n1:2:03 B",
    "0:00 A\n1:02:03 B",
    "0:00 A\n999:59:59.999 B",
    "0:00 A\n1000:00:00 B",
    "0:00 A\n0:5 B",
    "0:00 A\n00:00:00:00 B",
    "0:00 A\n 1:00 B\n\u00a02:00 C",
    "0:00\u00a0A",
    "0:00 A\rB\n1:00 C",
    "0:00 A\n1:00.5 B\n1:00.50 C",
    "0:00 A\n1:00.5 B\n1:00.05 C\n1:00.123 D\n1:00.9999 E",
    "0:00 A\n-1:00 B",
    "0:00 A\n+1:00 B",
    "\u0660:00 A",
    "0:00 A\n\uff11:00 B",
    "0:00 A\n1:00B",
    "0:00A",
    "0:00 A\t\tB\t C",
    "\ufeff0:00 A",
    "0:00 A\n1:00 B\n\n\n2:00 C\n",
    "0:00 A\n#1:00 B\n2:00 C",
    "0:00 A\n # indented comment\n2:00 C",
]


def cm_cases(rng):
    out = [("parse_ts", ["1:02:03.5"]), ("fmt_ts", [3723500]), ("normalize", [CM_LISTS[0]]), ("durations", [CM_LISTS[1], 200000]), ("chapter_at", [CM_LISTS[1], 90000, 200000]), ("parse_ts", ["75:30"])]
    stamps = ["0:00", "00:00", "0:00.0", "0:00.000", "0:00.5", "0:00.05", "0:00.005", "0:00.1234", "0:59", "0:60", "1:00", "59:59", "99:59", "999:59", "1000:00", "1:00:00", "1:00:00.001", "01:02:03", "001:02:03", "0001:02:03", "999:59:59.999", "1:60:00", "1:00:60", "1:0:00", "1:00:0",
              "0:0", "00", "0", "", ":", "0:", ":00", "1::00", "a:00", "0:0a", "0 :00", " 0:00", "0:00 ", "0:00\n", "-0:00", "+0:00", "0:00.", "0:00.a", ".5", "0:00,5", "\u0660:00", "0:\u0660\u0660", "\uff10:00", "1:00:00:00", "12:34:56.789", "2:03.50", "75:30.25", "100:00:00"]
    for s in stamps:
        out.append(("parse_ts", [s]))
    for _ in range(25):
        h, m, sec, ms = rng.randint(0, 999), rng.randint(0, 59), rng.randint(0, 59), rng.randint(0, 999)
        out.append(("parse_ts", ["%d:%02d:%02d.%03d" % (h, m, sec, ms)]))
        out.append(("parse_ts", ["%d:%02d" % (rng.randint(0, 999), sec)]))
    for ms in [0, 1, 999, 1000, 59999, 60000, 3599999, 3600000, 3723500, 86399999, 86400000, 359999999, 360000000, 3599999999999, -1, -3600000, 10 ** 12, 2 ** 40]:
        out.append(("fmt_ts", [ms]))
    for _ in range(15):
        out.append(("fmt_ts", [rng.randint(0, 10 ** 12)]))
    for text in CM_LISTS:
        out.append(("normalize", [text]))
        for total in (10 ** 7, 3000, 1, 0, 60000, 61000, 1000000000):
            out.append(("durations", [text, total]))
        for ms, total in [(0, 10 ** 7), (59999, 10 ** 7), (60000, 10 ** 7), (150000, 10 ** 7), (3722999, 10 ** 7), (9999999, 10 ** 7), (10 ** 7, 10 ** 7), (-1, 10 ** 7), (0, 0), (500, 1000), (0, 1), (300000, 400000), (300000, 300001)]:
            out.append(("chapter_at", [text, ms, total]))
    return out


CM = PortLib(
    slug="chapter-marks",
    title="podcast chapter marks",
    blurb="A podcast tool reads chapter lists typed by hand, normalises them and answers duration and lookup questions; the timestamp and white-space rules must come out identically in every language.",
    spec=CM_SPEC,
    fns=CM_FNS,
    impls={"python": {"chapter_marks.py": CM_PY}, "ruby": {"lib/chapter_marks.rb": CM_RB}, "typescript": {"src/chapter_marks.ts": CM_TS}},
    cases=cm_cases,
    difficulty=3,
    n_examples=10,
    pairs=[("python", "ruby", "full"), ("ruby", "typescript", "full"), ("typescript", "python", "stub"), ("python", "typescript", "stub")],
    traps=["white space is only space and tab (strip/split/trim defaults differ)", "code points versus UTF-16 units in length limits", "stable sort", "fraction digits padded on the right", "CRLF handling"],
    tags=["parsing", "unicode", "time"],
)
register_port(CM, __name__)

# ======================================================================================================================
# crc-tags: 12-bit CRC asset tags (C -> Rust / Python)
# ======================================================================================================================

CT_SPEC = dd('''
    Asset tags carry a 12-bit CRC. **CRC-12** here means: width 12, polynomial `0x80F`, initial value 0, input bytes processed most-significant bit first (no reflection), no final XOR. For every byte `b` (of the UTF-8 encoding of a text, or of the given bytes) do
    `crc ^= b << 4`, then eight times: if bit 11 (`0x800`) of `crc` is set `crc = ((crc << 1) ^ 0x80F) & 0xFFF`, otherwise `crc = (crc << 1) & 0xFFF`.

    * `crc12(text)` is the CRC-12 of the UTF-8 bytes of `text` (non-ASCII text matters: bytes above 0x7F must not be sign-extended). `crc12("")` is 0.
    * `crc12_hex(hex)` is the CRC-12 of the bytes written as hex text: an even number of ASCII hex digits (either case), possibly none; anything else is an error.
    * `crc12_parts(parts)` is the CRC-12 of the concatenation of the UTF-8 bytes of all parts (computed by continuing the CRC from one part to the next).
    * A **tag** is `PFX-NNNNN-CCC`: a prefix of 2 to 4 capital ASCII letters, a dash, a 5-digit number (zero padded, 00000..99999), a dash and three **upper-case** hex digits, the CRC-12 of the text before the last dash (`PFX-NNNNN`, as ASCII).
      `tag_make(prefix, number)` builds a tag (an invalid prefix or a number outside 0..99999 is an error). `tag_check(tag)` is true exactly for well-formed tags with the right CRC (lower-case hex digits, other lengths, other characters, a wrong CRC all give false; it never fails).
      `tag_number(tag)` is the number of a valid tag (an invalid tag is an error). `tag_next(tag)` is the tag with the next number and a fresh CRC (an invalid tag, or the number 99999, is an error).
''')

CT_FNS = [
    Fn("crc12", [("text", "str")], "u32"),
    Fn("crc12_hex", [("hex", "str")], "u32", err=True),
    Fn("crc12_parts", [("parts", "list<str>")], "u32"),
    Fn("tag_make", [("prefix", "str"), ("number", "int")], "str", err=True),
    Fn("tag_check", [("tag", "str")], "bool"),
    Fn("tag_number", [("tag", "str")], "int", err=True),
    Fn("tag_next", [("tag", "str")], "str", err=True),
]

CT_H = dd('''
    #ifndef CRC_TAGS_H
    #define CRC_TAGS_H

    #include <stddef.h>
    #include <stdint.h>

    /* Functions that can fail return 0 on success and a non-zero value on error; results go through `out`.
       Text results are NUL-terminated and must fit in `cap` bytes (including the NUL), otherwise the call fails. */
    uint32_t crc_tags_crc12(const char *text);
    int crc_tags_crc12_hex(const char *hex, uint32_t *out);
    uint32_t crc_tags_crc12_parts(const char *const *parts, size_t parts_len);
    int crc_tags_tag_make(const char *prefix, int64_t number, char *out, size_t cap);
    int crc_tags_tag_check(const char *tag);
    int crc_tags_tag_number(const char *tag, int64_t *out);
    int crc_tags_tag_next(const char *tag, char *out, size_t cap);

    #endif
''')

CT_C = dd(r'''
#include "crc_tags.h"

#include <stdio.h>
#include <string.h>

static uint32_t crc_bytes(const unsigned char *p, size_t n, uint32_t crc) {
    for (size_t i = 0; i < n; i++) {
        crc ^= (uint32_t)p[i] << 4;
        for (int k = 0; k < 8; k++) {
            if (crc & 0x800u) crc = ((crc << 1) ^ 0x80Fu) & 0xFFFu;
            else crc = (crc << 1) & 0xFFFu;
        }
    }
    return crc;
}

uint32_t crc_tags_crc12(const char *text) {
    return crc_bytes((const unsigned char *)text, strlen(text), 0);
}

static int hexval(int c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

int crc_tags_crc12_hex(const char *hex, uint32_t *out) {
    size_t len = strlen(hex);
    uint32_t crc = 0;
    if (len % 2 != 0) return -1;
    for (size_t i = 0; i < len; i += 2) {
        int h = hexval((unsigned char)hex[i]);
        int l = hexval((unsigned char)hex[i + 1]);
        unsigned char b;
        if (h < 0 || l < 0) return -1;
        b = (unsigned char)(h << 4 | l);
        crc = crc_bytes(&b, 1, crc);
    }
    *out = crc;
    return 0;
}

uint32_t crc_tags_crc12_parts(const char *const *parts, size_t parts_len) {
    uint32_t crc = 0;
    for (size_t i = 0; i < parts_len; i++) crc = crc_bytes((const unsigned char *)parts[i], strlen(parts[i]), crc);
    return crc;
}

static int is_upper(int c) { return c >= 'A' && c <= 'Z'; }
static int is_digit(int c) { return c >= '0' && c <= '9'; }

int crc_tags_tag_make(const char *prefix, int64_t number, char *out, size_t cap) {
    size_t n = strlen(prefix);
    char body[32];
    if (n < 2 || n > 4 || number < 0 || number > 99999) return -1;
    for (size_t i = 0; i < n; i++) if (!is_upper((unsigned char)prefix[i])) return -1;
    snprintf(body, sizeof body, "%s-%05d", prefix, (int)number);
    if (cap < strlen(body) + 5) return -1;
    snprintf(out, cap, "%s-%03X", body, (unsigned)crc_tags_crc12(body));
    return 0;
}

/* parses a well-formed tag: returns the length of the prefix (2..4) or -1 */
static int parse_tag(const char *tag, int64_t *number) {
    size_t n = strlen(tag);
    size_t p = 0;
    int64_t value = 0;
    char body[32];
    unsigned crc = 0;
    while (p < n && is_upper((unsigned char)tag[p])) p++;
    if (p < 2 || p > 4 || n != p + 10 || tag[p] != '-' || tag[p + 6] != '-') return -1;
    for (size_t i = p + 1; i < p + 6; i++) {
        if (!is_digit((unsigned char)tag[i])) return -1;
        value = value * 10 + (tag[i] - '0');
    }
    for (size_t i = p + 7; i < n; i++) {
        int c = (unsigned char)tag[i];
        int v = is_digit(c) ? c - '0' : (c >= 'A' && c <= 'F') ? c - 'A' + 10 : -1;
        if (v < 0) return -1;
        crc = crc << 4 | (unsigned)v;
    }
    memcpy(body, tag, p + 6);
    body[p + 6] = '\0';
    if (crc != crc_tags_crc12(body)) return -1;
    *number = value;
    return (int)p;
}

int crc_tags_tag_check(const char *tag) {
    int64_t number;
    return parse_tag(tag, &number) >= 0;
}

int crc_tags_tag_number(const char *tag, int64_t *out) {
    int64_t number;
    if (parse_tag(tag, &number) < 0) return -1;
    *out = number;
    return 0;
}

int crc_tags_tag_next(const char *tag, char *out, size_t cap) {
    int64_t number;
    char prefix[8];
    int p = parse_tag(tag, &number);
    if (p < 0 || number >= 99999) return -1;
    memcpy(prefix, tag, (size_t)p);
    prefix[p] = '\0';
    return crc_tags_tag_make(prefix, number + 1, out, cap);
}
''')

CT_PY = dd(r'''
import re

_TAG = re.compile(r"([A-Z]{2,4})-([0-9]{5})-([0-9A-F]{3})")
_HEX = re.compile(r"(?:[0-9A-Fa-f]{2})*")


def _crc(data, crc=0):
    for b in data:
        crc ^= b << 4
        for _ in range(8):
            crc = ((crc << 1) ^ 0x80F) & 0xFFF if crc & 0x800 else (crc << 1) & 0xFFF
    return crc


def crc12(text):
    return _crc(text.encode("utf-8"))


def crc12_hex(hex):
    if not _HEX.fullmatch(hex):
        raise ValueError("bad hex text")
    return _crc(bytes.fromhex(hex))


def crc12_parts(parts):
    crc = 0
    for part in parts:
        crc = _crc(part.encode("utf-8"), crc)
    return crc


def tag_make(prefix, number):
    if not re.fullmatch(r"[A-Z]{2,4}", prefix) or not 0 <= number <= 99999:
        raise ValueError("bad tag parts")
    body = "%s-%05d" % (prefix, number)
    return "%s-%03X" % (body, crc12(body))


def tag_check(tag):
    m = _TAG.fullmatch(tag)
    return bool(m) and int(m.group(3), 16) == crc12(tag[:-4])


def tag_number(tag):
    if not tag_check(tag):
        raise ValueError("invalid tag")
    return int(tag.split("-")[1])


def tag_next(tag):
    number = tag_number(tag)
    if number >= 99999:
        raise ValueError("number overflow")
    return tag_make(tag.split("-")[0], number + 1)
''')

CT_RS = dd(r'''
fn crc_bytes(data: &[u8], mut crc: u32) -> u32 {
    for &b in data {
        crc ^= (b as u32) << 4;
        for _ in 0..8 {
            crc = if crc & 0x800 != 0 { ((crc << 1) ^ 0x80F) & 0xFFF } else { (crc << 1) & 0xFFF };
        }
    }
    crc
}

pub fn crc12(text: &str) -> u32 {
    crc_bytes(text.as_bytes(), 0)
}

pub fn crc12_hex(hex: &str) -> Result<u32, String> {
    let b = hex.as_bytes();
    if b.len() % 2 != 0 || !b.iter().all(|c| c.is_ascii_hexdigit()) {
        return Err("bad hex text".to_string());
    }
    let bytes: Vec<u8> = b.chunks(2).map(|p| u8::from_str_radix(std::str::from_utf8(p).unwrap(), 16).unwrap()).collect();
    Ok(crc_bytes(&bytes, 0))
}

pub fn crc12_parts(parts: &[String]) -> u32 {
    parts.iter().fold(0, |crc, p| crc_bytes(p.as_bytes(), crc))
}

pub fn tag_make(prefix: &str, number: i64) -> Result<String, String> {
    let n = prefix.len();
    if !(2..=4).contains(&n) || !prefix.bytes().all(|c| c.is_ascii_uppercase()) || !(0..=99999).contains(&number) {
        return Err("bad tag parts".to_string());
    }
    let body = format!("{}-{:05}", prefix, number);
    Ok(format!("{}-{:03X}", body, crc12(&body)))
}

fn parse_tag(tag: &str) -> Option<(String, i64)> {
    let b = tag.as_bytes();
    let p = b.iter().take_while(|c| c.is_ascii_uppercase()).count();
    if !(2..=4).contains(&p) || b.len() != p + 10 || b[p] != b'-' || b[p + 6] != b'-' {
        return None;
    }
    if !b[p + 1..p + 6].iter().all(|c| c.is_ascii_digit()) {
        return None;
    }
    if !b[p + 7..].iter().all(|c| c.is_ascii_digit() || (b'A'..=b'F').contains(c)) {
        return None;
    }
    let crc = u32::from_str_radix(&tag[p + 7..], 16).ok()?;
    if crc != crc12(&tag[..p + 6]) {
        return None;
    }
    Some((tag[..p].to_string(), tag[p + 1..p + 6].parse().ok()?))
}

pub fn tag_check(tag: &str) -> bool {
    parse_tag(tag).is_some()
}

pub fn tag_number(tag: &str) -> Result<i64, String> {
    parse_tag(tag).map(|t| t.1).ok_or_else(|| "invalid tag".to_string())
}

pub fn tag_next(tag: &str) -> Result<String, String> {
    let (prefix, number) = parse_tag(tag).ok_or_else(|| "invalid tag".to_string())?;
    if number >= 99999 {
        return Err("number overflow".to_string());
    }
    tag_make(&prefix, number + 1)
}
''')


def ct_cases(rng):
    prefixes = ["AB", "XYZ", "ABCD", "QZ", "ZZZZ", "AA"]
    out = [("crc12", ["123456789"]), ("crc12_hex", ["313233"]), ("crc12_parts", [["12", "345", "6789"]]), ("tag_make", ["AB", 1]), ("tag_check", ["AB-00001-000"]), ("tag_number", [_ct_tag("AB", 7)]), ("tag_next", [_ct_tag("AB", 7)])]
    for t in ["", "a", "A", "abc", "123456789", "The quick brown fox", "caf\u00e9", "\u00e9\u00e9\u00e9", "\u2603", "\U0001f600", "AB-00001", "PFX-12345", "\x01", "a\x01b", "\x7f", "\u00ff", "\u0080", "line\nbreak", " ", "~" * 50, "\u00e9" * 20]:
        out.append(("crc12", [t]))
    for h in ["", "00", "ff", "FF", "fF", "313233", "c3a9", "C3A9", "0", "abc", "zz", "0g", " 00", "00 ", "0x00", "00\n", "\uff10\uff10", "e29883", "00" * 10, "a" * 7, "G1", "-1", "ab cd"]:
        out.append(("crc12_hex", [h]))
    for _ in range(12):
        n = rng.randint(0, 12)
        out.append(("crc12_hex", ["".join(rng.choice("0123456789abcdefABCDEF") for _ in range(2 * n))]))
    for parts in [[], [""], ["a"], ["a", "b"], ["ab"], ["", "a", ""], ["caf", "\u00e9"], ["\u00e9"], ["12", "345", "6789"], ["x"] * 30, ["\U0001f600", "\u2603"], ["\x01"], ["a", "", "b", ""]]:
        out.append(("crc12_parts", [parts]))
    for _ in range(10):
        out.append(("crc12_parts", [[rng.choice(["", "a", "bc", "\u00e9", "xyz123", "\u2603"]) for _ in range(rng.randint(0, 6))]]))
    for prefix in prefixes:
        for number in (0, 1, 99, 12345, 99999):
            out.append(("tag_make", [prefix, number]))
    for prefix, number in [("A", 1), ("ABCDE", 1), ("ab", 1), ("Ab", 1), ("A1", 1), ("", 1), ("AB", -1), ("AB", 100000), ("AB", 2 ** 40), ("\u00c9\u00c9", 1), ("AB ", 1), ("A\u00dfC", 5), ("AB-", 5), ("ZZ", 99999), ("ZZ", 100000)]:
        out.append(("tag_make", [prefix, number]))
    for _ in range(15):
        out.append(("tag_make", [rng.choice(prefixes), rng.randint(0, 99999)]))
    tags = [_ct_tag(rng.choice(prefixes), rng.choice([0, 1, 99998, 99999, rng.randint(0, 99999)])) for _ in range(25)]
    mutated = []
    for t in tags[:12]:
        i = rng.randrange(len(t))
        mutated.append(t[:i] + rng.choice("0123456789ABCDEFXYz-") + t[i + 1:])
    for t in tags + mutated + [t.lower() for t in tags[:3]] + [t[:-3] + t[-3:].lower() for t in tags] + [t[:-3] + t[-3:].lower() for t in [_ct_tag('AB', n) for n in range(10, 40)]] + [t + " " for t in tags[:3]] + [" " + t for t in tags[:2]] + [t + "\n" for t in tags[:2]] + [t[:-1] for t in tags[:3]] + [t + "0" for t in tags[:3]]:
        out.append(("tag_check", [t]))
        out.append(("tag_number", [t]))
        out.append(("tag_next", [t]))
    for t in ["", "AB", "AB-00001", "AB-00001-", "AB-00001-000", "A-00001-000", "ABCDE-00001-000", "AB-0001-000", "AB-000001-000", "AB-0000a-000", "AB_00001-000", "ab-00001-000", "AB-00001-0000", "AB-00001-00", "\u00c9B-00001-000", "AB-\u0661\u0662\u0663\u0664\u0665-000"]:
        out.append(("tag_check", [t]))
        out.append(("tag_number", [t]))
        out.append(("tag_next", [t]))
    return out


def _ct_tag(prefix, number):
    crc = 0
    for b in ("%s-%05d" % (prefix, number)).encode():
        crc ^= b << 4
        for _ in range(8):
            crc = ((crc << 1) ^ 0x80F) & 0xFFF if crc & 0x800 else (crc << 1) & 0xFFF
    return "%s-%05d-%03X" % (prefix, number, crc)


CT = PortLib(
    slug="crc-tags",
    title="12-bit CRC asset tags",
    blurb="An inventory firmware stamps asset tags with a 12-bit CRC and the back office tools in other languages have to compute exactly the same check digits, text in any language included.",
    spec=CT_SPEC,
    fns=CT_FNS,
    impls={"c": {"src/crc_tags.c": CT_C, "include/crc_tags.h": CT_H}, "python": {"crc_tags.py": CT_PY}, "rust": {"src/lib.rs": CT_RS}},
    cases=ct_cases,
    difficulty=3,
    n_examples=10,
    pairs=[("c", "rust", "full"), ("c", "python", "full"), ("rust", "python", "stub"), ("python", "rust", "stub")],
    traps=["signed char sign extension in C", "12-bit masking", "UTF-8 bytes versus characters", "strict ASCII-only tag grammar", "CRC state carried across parts"],
    tags=["crc", "bits", "c-source"],
)
register_port(CT, __name__)
