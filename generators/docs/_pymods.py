"""Small python modules (source blocks plus documentation metadata) used by the docs families.

Each module is a list of independent function blocks, so an instance can pick a subset. ``meta`` carries what a good docstring
says; the doctest examples are *evaluated at generation time* to get their outputs, never typed by hand.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Fn:
    name: str
    src: str  # the function source without a docstring
    summary: str
    args: dict  # name -> description
    returns: str = ""  # description, "" when the function returns nothing
    raises: dict = field(default_factory=dict)  # exception name -> description
    examples: list = field(default_factory=list)  # expressions (evaluated in the module namespace)
    errors: list = field(default_factory=list)  # expressions that must raise
    note: str = ""
    old_name: str = ""  # name used by the stale README
    needs: list = field(default_factory=list)  # names of functions this one calls


@dataclass
class Mod:
    key: str
    pkg: str
    mod: str
    summary: str
    header: str  # imports and constants
    funcs: list
    setup: str = ""  # python executed before the examples (e.g. build a sample stock)


SEEDBANK = Mod(
    key="seedbank", pkg="seedbank", mod="inventory", summary="Stock keeping for a community seed bank.",
    header='SKU_PREFIXES = ("VEG", "HRB", "FLW")\n',
    funcs=[
        Fn("parse_sku", '''def parse_sku(code):
    prefix, _, rest = code.partition("-")
    if prefix not in SKU_PREFIXES or not rest.isdigit():
        raise ValueError("bad sku: %r" % code)
    return prefix, int(rest)
''', "Split a SKU such as `VEG-0042` into its prefix and number.", {"code": "the SKU text, `<prefix>-<digits>`"}, "a `(prefix, number)` tuple",
           {"ValueError": "if the prefix is unknown or the number part is not made of digits"}, ['parse_sku("VEG-0042")', 'parse_sku("FLW-7")'], ['parse_sku("XYZ-1")', 'parse_sku("VEG-4x")']),
        Fn("add_lot", '''def add_lot(stock, sku, qty):
    if qty <= 0:
        raise ValueError("quantity must be positive")
    parse_sku(sku)
    stock[sku] = stock.get(sku, 0) + qty
    return stock[sku]
''', "Add packets of a SKU to the stock.", {"stock": "mapping of SKU to packet count, modified in place", "sku": "the SKU to add to", "qty": "number of packets, must be positive"},
           "the new packet count of the SKU", {"ValueError": "if `qty` is not positive or the SKU is malformed"}, ['add_lot({}, "VEG-1", 3)', 'add_lot({"VEG-1": 2}, "VEG-1", 5)'], ['add_lot({}, "VEG-1", 0)']),
        Fn("remove_lot", '''def remove_lot(stock, sku, qty):
    have = stock.get(sku, 0)
    if qty <= 0 or qty > have:
        raise ValueError("cannot remove %d of %s (have %d)" % (qty, sku, have))
    stock[sku] = have - qty
    if stock[sku] == 0:
        del stock[sku]
    return have - qty
''', "Take packets of a SKU out of the stock.", {"stock": "mapping of SKU to packet count, modified in place", "sku": "the SKU to take from", "qty": "number of packets to remove"},
           "the packets left after the removal (0 removes the SKU)", {"ValueError": "if `qty` is not positive or more than the stock holds"}, ['remove_lot({"VEG-1": 5}, "VEG-1", 2)', 'remove_lot({"VEG-1": 5}, "VEG-1", 5)'],
           ['remove_lot({"VEG-1": 1}, "VEG-1", 2)']),
        Fn("low_stock", '''def low_stock(stock, threshold=5):
    return sorted(sku for sku, qty in stock.items() if qty < threshold)
''', "List the SKUs that are running low.", {"stock": "mapping of SKU to packet count", "threshold": "SKUs with fewer packets than this are low"}, "the low SKUs in alphabetical order", {},
           ['low_stock({"VEG-1": 2, "HRB-4": 9, "FLW-2": 4})', 'low_stock({"VEG-1": 2, "HRB-4": 9}, threshold=10)']),
        Fn("reorder_plan", '''def reorder_plan(stock, targets):
    plan = {}
    for sku, want in sorted(targets.items()):
        missing = want - stock.get(sku, 0)
        if missing > 0:
            plan[sku] = missing
    return plan
''', "Work out how many packets to order to reach the target levels.", {"stock": "mapping of SKU to packet count", "targets": "mapping of SKU to the desired packet count"},
           "mapping of SKU to the number of packets to order (only SKUs that are short)", {}, ['reorder_plan({"VEG-1": 2}, {"VEG-1": 5, "HRB-2": 3})', 'reorder_plan({"VEG-1": 9}, {"VEG-1": 5})']),
        Fn("format_label", '''def format_label(sku, qty):
    prefix, number = parse_sku(sku)
    return "%s #%04d x%d" % (prefix, number, qty)
''', "Format the text printed on a packet label.", {"sku": "the SKU of the packet", "qty": "packets in the lot"}, "the label text, for example `VEG #0042 x3`",
           {"ValueError": "if the SKU is malformed"}, ['format_label("VEG-42", 3)', 'format_label("HRB-7", 10)'], ['format_label("nope", 1)']),
        Fn("total_packets", '''def total_packets(stock):
    return sum(stock.values())
''', "Count all packets in the stock.", {"stock": "mapping of SKU to packet count"}, "the total number of packets", {}, ['total_packets({"VEG-1": 2, "HRB-4": 9})', "total_packets({})"]),
    ])

FERRY = Mod(
    key="ferry", pkg="ferryops", mod="schedule", summary="Timetable helpers for the island ferry.",
    header="DAY_MINUTES = 24 * 60\n",
    funcs=[
        Fn("parse_time", '''def parse_time(text):
    hours, sep, minutes = text.partition(":")
    if not sep or not hours.isdigit() or not minutes.isdigit():
        raise ValueError("expected HH:MM, got %r" % text)
    h, m = int(hours), int(minutes)
    if h > 23 or m > 59:
        raise ValueError("time out of range: %r" % text)
    return h * 60 + m
''', "Convert `HH:MM` text to minutes after midnight.", {"text": "a 24-hour time such as `07:45`"}, "minutes after midnight", {"ValueError": "if the text is not `HH:MM` or is out of range"},
           ['parse_time("07:45")', 'parse_time("00:00")', 'parse_time("23:59")'], ['parse_time("7.45")', 'parse_time("24:00")']),
        Fn("format_time", '''def format_time(minutes):
    minutes %= DAY_MINUTES
    return "%02d:%02d" % (minutes // 60, minutes % 60)
''', "Convert minutes after midnight to `HH:MM`, wrapping past midnight.", {"minutes": "minutes after midnight, may exceed one day"}, "the time as `HH:MM`", {},
           ["format_time(465)", "format_time(1500)", "format_time(0)"]),
        Fn("next_departure", '''def next_departure(times, now):
    later = [t for t in sorted(times) if t >= now]
    if later:
        return later[0]
    return min(times) + DAY_MINUTES if times else None
''', "Find the next sailing at or after a given time.", {"times": "departure times in minutes after midnight, any order", "now": "the current time in minutes after midnight"},
           "the next departure, tomorrow's first one (plus one day of minutes) if none is left today, or `None` without any sailings", {}, ["next_departure([420, 600, 900], 500)", "next_departure([420, 600], 700)", "next_departure([], 10)"]),
        Fn("crossing_duration", '''def crossing_duration(departure, arrival):
    if arrival < departure:
        arrival += DAY_MINUTES
    return arrival - departure
''', "Length of a crossing, allowing for arrival after midnight.", {"departure": "departure in minutes after midnight", "arrival": "arrival in minutes after midnight"},
           "the duration in minutes", {}, ["crossing_duration(420, 495)", "crossing_duration(1430, 20)"]),
        Fn("overlap", '''def overlap(a, b):
    start = max(a[0], b[0])
    end = min(a[1], b[1])
    return max(0, end - start)
''', "Minutes two time windows share.", {"a": "first window as `(start, end)` minutes", "b": "second window as `(start, end)` minutes"}, "the shared minutes, 0 when the windows are disjoint", {},
           ["overlap((60, 120), (90, 200))", "overlap((0, 10), (20, 30))"]),
        Fn("slots_between", '''def slots_between(start, end, step):
    if step <= 0:
        raise ValueError("step must be positive")
    return list(range(start, end, step))
''', "List evenly spaced departure slots.", {"start": "first slot in minutes", "end": "exclusive upper bound in minutes", "step": "minutes between slots, must be positive"},
           "the slots from `start` up to (not including) `end`", {"ValueError": "if `step` is not positive"}, ["slots_between(420, 520, 30)", "slots_between(10, 10, 5)"], ["slots_between(0, 10, 0)"]),
        Fn("validate_roster", '''def validate_roster(roster):
    seen = set()
    for crew, shift in roster:
        if crew in seen:
            raise ValueError("%s is rostered twice" % crew)
        seen.add(crew)
        if shift not in ("early", "late"):
            raise ValueError("unknown shift %r for %s" % (shift, crew))
    return len(seen)
''', "Check a crew roster.", {"roster": "list of `(crew name, shift)` pairs, shift is `early` or `late`"}, "the number of crew members rostered",
           {"ValueError": "if somebody appears twice or a shift is unknown"}, ['validate_roster([("Ana", "early"), ("Bo", "late")])'], ['validate_roster([("Ana", "early"), ("Ana", "late")])']),
    ])

TIDELAB = Mod(
    key="tidelab", pkg="tidelab", mod="units", summary="Unit conversions and small statistics for the tide laboratory.",
    header='FEET_PER_METRE = 3.28084\nUNITS = ("m", "ft", "cm")\n',
    funcs=[
        Fn("to_metres", '''def to_metres(value, unit):
    if unit == "m":
        return float(value)
    if unit == "cm":
        return value / 100.0
    if unit == "ft":
        return round(value / FEET_PER_METRE, 4)
    raise ValueError("unknown unit: %r" % unit)
''', "Convert a length to metres.", {"value": "the length", "unit": "one of `m`, `cm` or `ft`"}, "the length in metres", {"ValueError": "if the unit is not known"},
           ['to_metres(250, "cm")', 'to_metres(10, "ft")', 'to_metres(2, "m")'], ['to_metres(1, "yd")']),
        Fn("clamp", '''def clamp(value, low, high):
    if low > high:
        raise ValueError("low must not exceed high")
    return max(low, min(high, value))
''', "Limit a value to a range.", {"value": "the number to limit", "low": "smallest allowed value", "high": "largest allowed value"}, "`value`, or the nearest bound if it is outside",
           {"ValueError": "if `low` is greater than `high`"}, ["clamp(5, 0, 3)", "clamp(-2, 0, 3)", "clamp(2, 0, 3)"], ["clamp(1, 5, 0)"]),
        Fn("bucketize", '''def bucketize(values, edges):
    counts = [0] * (len(edges) + 1)
    for v in values:
        i = 0
        while i < len(edges) and v >= edges[i]:
            i += 1
        counts[i] += 1
    return counts
''', "Count values per bucket.", {"values": "the numbers to count", "edges": "ascending bucket boundaries; a value equal to an edge goes to the upper bucket"},
           "a list with one count per bucket (`len(edges) + 1` entries)", {}, ["bucketize([1, 5, 9, 10, 25], [5, 10])", "bucketize([], [1])"]),
        Fn("moving_average", '''def moving_average(values, window):
    if window < 1:
        raise ValueError("window must be at least 1")
    out = []
    for i in range(len(values) - window + 1):
        chunk = values[i:i + window]
        out.append(sum(chunk) / window)
    return out
''', "Average over a sliding window.", {"values": "the readings", "window": "number of readings per average, at least 1"},
           "the averages, one per full window (empty if there are fewer readings than `window`)", {"ValueError": "if `window` is smaller than 1"}, ["moving_average([1, 2, 3, 4], 2)", "moving_average([5], 3)"],
           ["moving_average([1, 2], 0)"]),
        Fn("percentile", '''def percentile(values, p):
    if not values:
        raise ValueError("no values")
    if not 0 <= p <= 100:
        raise ValueError("p must be between 0 and 100")
    ordered = sorted(values)
    index = round((len(ordered) - 1) * p / 100)
    return ordered[index]
''', "Nearest-rank style percentile of a list.", {"values": "the numbers, any order", "p": "percentile between 0 and 100"}, "the value at that percentile",
           {"ValueError": "if `values` is empty or `p` is outside 0-100"}, ["percentile([5, 1, 9, 3], 50)", "percentile([7], 100)"], ["percentile([], 50)", "percentile([1], 101)"]),
        Fn("normalise_name", '''def normalise_name(name):
    return " ".join(part.capitalize() for part in name.replace("_", " ").split())
''', "Turn an identifier-like station name into a display name.", {"name": "a name such as `north_quay`"}, "the name with spaces and capitals, e.g. `North Quay`", {},
           ['normalise_name("north_quay")', 'normalise_name("  harbour   MOUTH ")']),
    ])

DUTY = Mod(
    key="duty", pkg="stampduty", mod="rules", summary="Money and band helpers for a stamp-duty calculator.",
    header='RELIEFS = {"first_home": 50, "heritage": 20}\n',
    funcs=[
        Fn("parse_money", '''def parse_money(text):
    whole, _, frac = text.strip().partition(".")
    if not whole.isdigit() or len(frac) > 2 or (frac and not frac.isdigit()):
        raise ValueError("not an amount: %r" % text)
    return int(whole) * 100 + int((frac + "00")[:2])
''', "Parse an amount such as `12.50` into cents.", {"text": "digits with at most two decimals"}, "the amount in cents", {"ValueError": "if the text is not a plain decimal amount"},
           ['parse_money("12.50")', 'parse_money("7")', 'parse_money(" 0.05 ")'], ['parse_money("1.234")', 'parse_money("-3")']),
        Fn("format_money", '''def format_money(cents):
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return "%s%d.%02d" % (sign, cents // 100, cents % 100)
''', "Format cents as an amount with two decimals.", {"cents": "the amount in cents, may be negative"}, "the amount as text", {}, ["format_money(1250)", "format_money(-5)", "format_money(0)"]),
        Fn("band_duty", '''def band_duty(price, bands):
    total = 0
    lower = 0
    for upper, rate in bands:
        top = price if upper is None else min(price, upper)
        if top > lower:
            total += (top - lower) * rate // 100
        if upper is None or price <= upper:
            break
        lower = upper
    return total
''', "Duty charged band by band.", {"price": "the price in whole currency units", "bands": "ascending `(upper limit or None, percent)` pairs; the last band has no limit"},
           "the duty in whole currency units, rounded down per band", {}, ["band_duty(250000, [(100000, 0), (200000, 2), (None, 5)])", "band_duty(50000, [(100000, 0), (None, 5)])"]),
        Fn("apply_relief", '''def apply_relief(duty, kind):
    if kind not in RELIEFS:
        raise ValueError("unknown relief: %r" % kind)
    return duty - duty * RELIEFS[kind] // 100
''', "Reduce a duty amount by a named relief.", {"duty": "the duty before relief", "kind": "`first_home` or `heritage`"}, "the duty after the relief", {"ValueError": "if the relief is unknown"},
           ['apply_relief(1000, "first_home")', 'apply_relief(1000, "heritage")'], ['apply_relief(1000, "other")']),
        Fn("round_to", '''def round_to(amount, step):
    if step <= 0:
        raise ValueError("step must be positive")
    return (amount + step // 2) // step * step
''', "Round an amount to the nearest multiple of a step (halves round up).", {"amount": "the amount to round", "step": "the multiple to round to, must be positive"},
           "the rounded amount", {"ValueError": "if `step` is not positive"}, ["round_to(1234, 5)", "round_to(1235, 10)", "round_to(7, 5)"], ["round_to(10, 0)"]),
        Fn("split_evenly", '''def split_evenly(cents, parts):
    if parts < 1:
        raise ValueError("parts must be at least 1")
    base, extra = divmod(cents, parts)
    return [base + (1 if i < extra else 0) for i in range(parts)]
''', "Split an amount into nearly equal shares that add up exactly.", {"cents": "the total to split", "parts": "number of shares, at least 1"},
           "the shares; the first ones are one cent larger when the split is uneven", {"ValueError": "if `parts` is smaller than 1"}, ["split_evenly(10, 3)", "split_evenly(9, 3)"], ["split_evenly(5, 0)"]),
    ])

for _f in SEEDBANK.funcs:
    if _f.name in ("add_lot", "format_label"):
        _f.needs = ["parse_sku"]

MODULES = [SEEDBANK, FERRY, TIDELAB, DUTY]


def pick(mod, rng, k):
    """k random functions plus whatever they call, in module order."""
    chosen = rng.sample(mod.funcs, min(k, len(mod.funcs)))
    names = {f.name for f in chosen}
    for f in list(chosen):
        names.update(f.needs)
    return [f for f in mod.funcs if f.name in names]

# stale-README drift: (old name used by the README, new name in the code)
RENAMES = {
    "seedbank": {"add_lot": "receive_lot", "low_stock": "running_low"},
    "ferry": {"parse_time": "minutes_from_text", "format_time": "text_from_minutes"},
    "tidelab": {"to_metres": "length_to_metres", "moving_average": "rolling_mean"},
    "duty": {"parse_money": "cents_from_text", "format_money": "text_from_cents"},
}


def source(mod: Mod, funcs: list, docstrings: dict | None = None, renames: dict | None = None) -> str:
    """Module text for the chosen functions; `docstrings` maps function name -> docstring text (already indented lines are added here)."""
    parts = [f'"""{mod.summary}"""\n\n{mod.header}']
    for f in funcs:
        text = f.src
        if docstrings and f.name in docstrings:
            doc = docstrings[f.name]
            lines = doc.strip("\n").split("\n")
            if len(lines) == 1:
                block = f'    """{lines[0]}"""\n'
            else:
                block = '    """' + lines[0] + "\n" + "\n".join(("    " + ln) if ln.strip() else "" for ln in lines[1:]) + '\n    """\n'
            head, _, rest = text.partition("\n")
            text = head + "\n" + block + rest
        if renames:
            for old, new in renames.items():
                text = text.replace(f"def {old}(", f"def {new}(").replace(f" {old}(", f" {new}(")
        parts.append(text)
    return "\n\n".join(parts)
