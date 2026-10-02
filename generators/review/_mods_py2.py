"""Slot modules (python), part 2: tide-aware quay planner, Kestrel transfer duty, podcast chapter files."""
from fx import dd

from ._slots import Bad, Module, Slot, validate_module

# ---------------------------------------------------------------------------------------------------------------------
# Marrow Quay slot planner
# ---------------------------------------------------------------------------------------------------------------------

TIDE_TEMPLATE = dd('''
    """Dock slot planning for Marrow Quay: when may a boat of a given draught lie alongside?"""
    import csv
    import io

    MARGIN_CM = 30  # water we want under the keel


    class TideError(ValueError):
        """Bad tide table or an impossible booking."""


    @@parse@@


    @@height@@


    @@fmt@@


    @@windows@@


    @@safe@@


    class Planner:
        def __init__(self, points):
            self.points = points
            self.bookings = {}  # id -> (boat, draught_cm, start, end) in minutes of the day
            self.next_id = 1

        @@book@@

        @@cancel@@

        @@export@@
''')

_PARSE = dd('''
    def parse_tides(text):
        """Parse "HH:MM,cm" lines for one day. Times must strictly increase; heights are 0..1000 cm."""
        points = []
        for n, raw in enumerate(text.strip().splitlines(), 1):
            raw = raw.strip()
            if not raw or raw.startswith("#"):
                continue
            hhmm, _, cm = raw.partition(",")
            hh, _, mm = hhmm.partition(":")
            minute = int(hh) * 60 + int(mm)
            height = int(cm)
            if not 0 <= minute < 1440 or not 0 <= height <= 1000:
                raise TideError(f"line {n}: out of range")
            if points and minute <= points[-1][0]:
                raise TideError(f"line {n}: times must increase")
            points.append((minute, height))
        if len(points) < 2:
            raise TideError("need at least two tide points")
        return points
''')

_HEIGHT = dd('''
    def height_at(points, minute):
        """Tide height in whole cm at a minute of the day: linear between points (halves round up), flat outside them."""
        if minute <= points[0][0]:
            return points[0][1]
        if minute >= points[-1][0]:
            return points[-1][1]
        for (m0, h0), (m1, h1) in zip(points, points[1:]):
            if m0 <= minute <= m1:
                span = m1 - m0
                return h0 + ((h1 - h0) * (minute - m0) * 2 + span) // (2 * span)
''')

_WINDOWS = dd('''
    def open_windows(points, draught_cm):
        """Half-open (start, end) minute ranges in which a boat with this draught can be alongside."""
        need = draught_cm + MARGIN_CM
        windows, start = [], None
        for minute in range(1440):
            ok = height_at(points, minute) >= need
            if ok and start is None:
                start = minute
            elif not ok and start is not None:
                windows.append((start, minute))
                start = None
        if start is not None:
            windows.append((start, 1440))
        return windows
''')

_BOOK = dd('''
    def book(self, boat, draught_cm, start, duration):
        """Reserve the quay from `start` for `duration` minutes. The whole stay has to fit one open window and
        must not overlap another booking (back-to-back stays are fine). Returns the booking id."""
        end = start + duration
        if duration <= 0 or start < 0 or end > 1440:
            raise TideError("bad stay")
        if not any(w0 <= start and end <= w1 for w0, w1 in open_windows(self.points, draught_cm)):
            raise TideError(f"{boat}: no tide window for that stay")
        for _, _, s, e in self.bookings.values():
            if start < e and s < end:
                raise TideError(f"{boat}: quay busy")
        bid = self.next_id
        self.next_id += 1
        self.bookings[bid] = (boat, draught_cm, start, end)
        return bid
''')

_EXPORT = dd('''
    def export_csv(self):
        """Bookings as CSV text, earliest start first."""
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\\n")
        writer.writerow(["id", "boat", "draught_cm", "start", "end"])
        for bid, (boat, draught, s, e) in sorted(self.bookings.items(), key=lambda kv: (kv[1][2], kv[0])):
            writer.writerow([bid, _safe_cell(boat), draught, fmt_minute(s), fmt_minute(e)])
        return out.getvalue()
''')

TIDEWATCH = Module(
    name="py-quayplan", lang="python", path="harbor/quay.py", difficulty=3,
    title="Quay planner: tide windows, bookings and CSV export",
    blurb="The `harbor` package plans which boats can lie alongside Marrow Quay at which time, given the day's tide table.",
    intro=dd('''
        The harbour office books the quay by hand from a printed tide table. This change adds the first version of the planner
        that does it from the table itself:
    '''),
    outro=dd('''
        Boat names are typed in by skippers on the booking form. Checked against last Tuesday's table and three hand-made
        bookings; no automated tests yet.
    '''),
    new_file=True,
    template=TIDE_TEMPLATE,
    ctx={"README.md": dd('''
        # harbor

        Planning tools for Marrow Quay. `harbor/quay.py` turns a tide table into windows in which a boat may come
        alongside and keeps the day's bookings.
    '''), "harbor/__init__.py": '"""Harbour planning."""\n'},
    scenario=dd('''
        from harbor.quay import Planner, TideError, fmt_minute, height_at, open_windows, parse_tides

        TABLE = """
        # Marrow Quay, one tide day
        00:00,120
        03:00,420
        06:30,150
        09:45,480
        13:00,100
        16:15,520
        19:30,160
        23:00,380
        """
        points = parse_tides(TABLE)
        for m in (0, 95, 180, 400, 1439):
            print(f"height at {fmt_minute(m)}: {height_at(points, m)} cm")
        print("windows for 3.0 m:", [(fmt_minute(a), fmt_minute(b)) for a, b in open_windows(points, 300)])
        print("windows for 4.4 m:", [(fmt_minute(a), fmt_minute(b)) for a, b in open_windows(points, 440)])
        for bad in ("00:00,100\\n06:00,400\\n06:00,420\\n12:00,100\\n", "00:00,100\\n24:00,300\\n", "07:00,100"):
            try:
                pts = parse_tides(bad)
                print("table accepted:", open_windows(pts, 200)[:2])
            except TideError as exc:
                print("table refused:", exc)
        plan = Planner(points)
        stays = [("Gannet", 300, 150, 90), ("Skua", 300, 240, 11), ("Tern", 300, 240, 30), ("Petrel", 440, 580, 10),
                 ("Fulmar", 250, 1350, 90), ("=cmd|' /C calc'!A0", 200, 520, 20), ("Auk", 200, 1380, 60), ("-Swift", 200, 560, 10),
                 ("@home", 200, 540, 15), ("Shag", 300, 230, 40)]
        for boat, draught, start, dur in stays:
            try:
                print(f"book {boat}: id {plan.book(boat, draught, start, dur)}")
            except TideError as exc:
                print(f"book {boat}: refused ({exc})")
        try:
            plan.cancel(2)
            plan.cancel(2)
        except TideError as exc:
            print("cancel:", exc)
        print(plan.export_csv(), end="")
    '''),
    slots=[
        Slot("parse", "parse_tides", _PARSE, [
            Bad(_PARSE.replace("minute <= points[-1][0]", "minute < points[-1][0]"), "validation", "equal times are accepted (`<` instead of `<=`), so a table with a repeated minute passes validation and later interpolates across a zero-length step", ("strictly", "increase", "duplicate", "equal", "<")),
            Bad(_PARSE.replace("0 <= minute < 1440", "0 <= minute <= 1440"), "off-by-one", "`24:00` is accepted as a minute of the day although the valid range ends at 23:59 (1439)", ("1440", "24:00", "range", "<=")),
        ], note="adds `parse_tides()` with range and ordering validation"),
        Slot("height", "height_at", _HEIGHT, [
            Bad(_HEIGHT.replace("((h1 - h0) * (minute - m0) * 2 + span) // (2 * span)", "(h1 - h0) * (minute - m0) // span"), "logic", "the interpolation is floored instead of rounded half up, so heights are biased low whenever the tide is rising", ("floor", "round", "half", "interpolat")),
            Bad(_HEIGHT.replace('''    if minute <= points[0][0]:
        return points[0][1]
    if minute >= points[-1][0]:
        return points[-1][1]
''', ""), "error-handling", "the clamps before the first and after the last point are gone, so such minutes fall out of the loop and the function returns None", ("clamp", "None", "outside", "first", "last"), kind="null-handling"),
        ], note="adds `height_at()`: tide height at any minute by linear interpolation"),
        Slot("fmt", "fmt_minute", dd('''
            def fmt_minute(m):
                """HH:MM for a minute of the day; the end of the day (1440) is written 24:00."""
                return f"{m // 60:02d}:{m % 60:02d}"
        '''), [
            Bad(dd('''
                def fmt_minute(m):
                    """HH:MM for a minute of the day; the end of the day (1440) is written 24:00."""
                    return f"{m // 60 % 24:02d}:{m % 60:02d}"
            '''), "off-by-one", "the hour wraps at 24 so the end of the day prints as 00:00, making a stay that ends at midnight look as if it ends before it starts", ("24", "midnight", "wrap", "1440")),
        ], note="adds `fmt_minute()` for display"),
        Slot("windows", "open_windows", _WINDOWS, [
            Bad(_WINDOWS.replace(">= need", "> need"), "off-by-one", "a boat needs the height to be at least draught + margin; `>` rejects the minute where it is exactly equal", (">=", "exactly", "equal", "margin")),
            Bad(_WINDOWS.replace("need = draught_cm + MARGIN_CM", "need = draught_cm"), "logic", "the safety margin under the keel is not applied", ("margin", "MARGIN_CM", "keel", "need")),
            Bad(_WINDOWS.replace('''    if start is not None:
        windows.append((start, 1440))
''', ""), "logic", "a window that is still open at midnight is never closed, so the last window of the day is dropped", ("midnight", "last", "still open", "1440")),
            Bad(_WINDOWS.replace("windows.append((start, minute))", "windows.append((start, minute - 1))"), "off-by-one", "the end of a window is minute - 1 although windows are half-open, which shortens every window by one minute", ("half-open", "minute - 1", "end", "shorter")),
        ], note="adds `open_windows()`: the minutes in which a given draught fits"),
        Slot("safe", "_safe_cell", dd('''
            def _safe_cell(cell):
                """Neutralise cells that a spreadsheet would run as a formula."""
                return "'" + cell if cell[:1] in ("=", "+", "-", "@") else cell
        '''), [
            Bad(dd('''
                def _safe_cell(cell):
                    """Neutralise cells that a spreadsheet would run as a formula."""
                    return "'" + cell if cell[:1] == "=" else cell
            '''), "security", "only a leading `=` is neutralised; `+`, `-` and `@` also start a formula in spreadsheets (CSV injection)", ("formula", "injection", "+", "@", "csv")),
            Bad(dd('''
                def _safe_cell(cell):
                    """Neutralise cells that a spreadsheet would run as a formula."""
                    return cell
            '''), "security", "boat names are exported verbatim, so a name such as `=cmd|...` becomes a formula when the CSV is opened (CSV injection)", ("formula", "injection", "csv", "sanitis", "escape")),
        ], note="escapes formula-like cells in the CSV export"),
        Slot("book", "Planner.book", _BOOK, [
            Bad(_BOOK.replace("w0 <= start and end <= w1", "w0 <= start < w1"), "logic", "only the start of the stay is checked against the window, so a stay may run past the end of the tide window", ("window", "end", "whole", "fit")),
            Bad(_BOOK.replace("start < e and s < end", "start <= e and s <= end"), "off-by-one", "closed-interval overlap test: a stay that starts exactly when another ends is refused although back-to-back stays are allowed", ("<=", "back-to-back", "overlap", "adjacent")),
            Bad(_BOOK.replace("end > 1440", "end >= 1440"), "off-by-one", "a stay that ends exactly at midnight (1440) is rejected", ("1440", ">=", "midnight")),
            Bad(_BOOK.replace("    self.next_id += 1\n", ""), "logic", "next_id is never incremented, so every booking gets id 1 and overwrites the previous one", ("next_id", "increment", "overwrite", "id")),
        ], note="adds `Planner.book()`: window and overlap checks, back-to-back stays allowed"),
        Slot("cancel", "Planner.cancel", dd('''
            def cancel(self, bid):
                """Cancel a booking; an unknown id is a TideError."""
                if bid not in self.bookings:
                    raise TideError(f"no booking {bid}")
                del self.bookings[bid]
        '''), [
            Bad(dd('''
                def cancel(self, bid):
                    """Cancel a booking; an unknown id is a TideError."""
                    self.bookings.pop(bid, None)
            '''), "error-handling", "cancelling an unknown (or already cancelled) booking silently succeeds although the docstring promises a TideError", ("pop", "unknown", "silently", "TideError")),
        ], note="adds `Planner.cancel()`"),
        Slot("export", "Planner.export_csv", _EXPORT, [
            Bad(_EXPORT.replace("key=lambda kv: (kv[1][2], kv[0])", "key=lambda kv: kv[0]"), "logic", "rows are ordered by booking id instead of earliest start", ("sorted", "order", "start", "key")),
            Bad(_EXPORT.replace("_safe_cell(boat)", "boat"), "security", "the boat name is written without `_safe_cell`, so the formula guard is bypassed", ("_safe_cell", "formula", "injection", "csv")),
        ], note="adds `Planner.export_csv()`, earliest start first"),
    ],
)

# ---------------------------------------------------------------------------------------------------------------------
# Kestrel Isles transfer duty
# ---------------------------------------------------------------------------------------------------------------------

DUTY_TEMPLATE = dd('''
    """Transfer duty for the Kestrel Isles. Prices and duty are whole pounds (ints)."""
    import re

    # (threshold, percent): the percent applies to the part of the price above the threshold, up to the next threshold
    BANDS = [(0, 0), (150_000, 2), (300_000, 5), (750_000, 9), (1_500_000, 12)]
    FIRST_HOME_FREE = 400_000  # first-home buyers pay nothing up to this price ...
    FIRST_HOME_END = 500_000  # ... and the full duty from this price; in between the duty is phased in linearly
    SURCHARGE_PCT = 3  # non-resident buyers pay this percent of the *whole* price on top
    SECOND_HOME_PCT = 2  # so do buyers of a second home (the two surcharges add up)

    _cache = {}


    @@validate@@


    @@bands@@


    @@relief@@


    @@quote@@


    @@parse@@


    @@money@@
''')

_D_VALIDATE = dd('''
    def validate_price(price):
        """A price is a positive int number of pounds, at most 50 million."""
        if isinstance(price, bool) or not isinstance(price, int):
            raise ValueError(f"price must be an int, got {price!r}")
        if not 0 < price <= 50_000_000:
            raise ValueError(f"price out of range: {price}")
''')
_D_BANDS = dd('''
    def band_duty(price):
        """Marginal duty over BANDS, floored to whole pounds; also the per-band breakdown."""
        parts = []
        total = 0
        for i, (low, pct) in enumerate(BANDS):
            high = BANDS[i + 1][0] if i + 1 < len(BANDS) else None
            if price <= low:
                break
            top = price if high is None else min(price, high)
            amount = (top - low) * pct // 100
            parts.append((low, top, amount))
            total += amount
        return total, parts
''')
_D_RELIEF = dd('''
    def first_home_duty(price, duty):
        """Duty after first-home relief: nothing up to FIRST_HOME_FREE, phased in linearly up to FIRST_HOME_END."""
        if price <= FIRST_HOME_FREE:
            return 0
        if price >= FIRST_HOME_END:
            return duty
        return duty * (price - FIRST_HOME_FREE) // (FIRST_HOME_END - FIRST_HOME_FREE)
''')
_D_QUOTE = dd('''
    def quote(price, first_home=False, resident=True, second_home=False):
        """Duty, surcharge and total for a purchase. Relief is only for resident first-home buyers."""
        validate_price(price)
        key = (price, first_home, resident, second_home)
        if key in _cache:
            return dict(_cache[key])
        duty, _ = band_duty(price)
        if first_home and resident:
            duty = first_home_duty(price, duty)
        pct = (0 if resident else SURCHARGE_PCT) + (SECOND_HOME_PCT if second_home else 0)
        surcharge = price * pct // 100
        result = {"duty": duty, "surcharge": surcharge, "total": duty + surcharge}
        _cache[key] = result
        return dict(result)
''')
_D_PARSE = dd('''
    def parse_price(text):
        """Parse a price typed on the form: optional pound sign, thousands commas allowed ("1,250,000", "£90000")."""
        m = re.fullmatch(r"£?\\s*(\\d{1,3}(?:,\\d{3})+|\\d+)", text.strip())
        if not m:
            raise ValueError(f"not a price: {text!r}")
        return int(m.group(1).replace(",", ""))
''')
_D_MONEY = dd('''
    def money(n):
        """£ with thousands separators: 1234567 -> £1,234,567."""
        return "£" + f"{n:,}"
''')

KESTREL = Module(
    name="py-isleduty", lang="python", path="kestrel/duty.py", difficulty=3,
    title="Add transfer duty calculator with first-home relief and surcharges",
    blurb="The `kestrel` package is the calculator behind the Kestrel Isles land registry's online duty estimate.",
    intro=dd('''
        The registry's duty estimate is currently a spreadsheet. This PR ports the rules into code so the website can call it:
    '''),
    outro=dd('''
        Spot-checked against five worked examples from the registry's guidance leaflet.
    '''),
    new_file=True,
    template=DUTY_TEMPLATE,
    ctx={"README.md": dd('''
        # kestrel

        Duty rules of the Kestrel Isles land registry. `kestrel/duty.py` has `quote()`; `parse_price()` and `money()` are for
        the web form.
    '''), "kestrel/__init__.py": '"""Kestrel Isles registry tools."""\n'},
    scenario=dd('''
        from kestrel.duty import band_duty, money, parse_price, quote

        for price in (100_000, 150_000, 150_001, 299_999, 450_000, 750_000, 1_000_000, 2_000_000):
            print(f"{money(price):>12} duty {band_duty(price)[0]}")
        print("breakdown 800k:", band_duty(800_000)[1])
        print("breakdown 750k:", band_duty(750_000)[1])
        cases = [(350_000, True, True, False), (400_001, True, True, False), (450_000, True, True, False), (500_000, True, True, False),
                 (450_000, True, False, False), (600_000, False, False, True), (600_000, False, True, True), (200_000, False, True, False)]
        for price, fh, res, second in cases:
            print(f"quote {price} first_home={fh} resident={res} second_home={second}: {quote(price, fh, res, second)}")
        print("again:", quote(450_000, False, True, False), quote(450_000, True, True, False))
        edited = quote(450_000, False, True, False)
        edited["total"] = -1
        print("after the caller edited its copy:", quote(450_000, False, True, False))
        for bad in (0, -5, 50_000_001, True, 99.5, "1000"):
            try:
                quote(bad)
                print("accepted", repr(bad))
            except ValueError as exc:
                print("refused:", exc)
        for text in ("£1,250,000", "90000", " 12,34 ", "1,2345", "£", "12 000"):
            try:
                print(f"parse {text!r}:", parse_price(text))
            except ValueError as exc:
                print("parse refused:", exc)
    '''),
    slots=[
        Slot("validate", "validate_price", _D_VALIDATE, [
            Bad(_D_VALIDATE.replace("if not 0 < price <=", "if not 0 <= price <="), "validation", "a price of 0 is accepted although a price must be positive", ("zero", "0", "positive", "<=")),
            Bad(_D_VALIDATE.replace("isinstance(price, bool) or ", ""), "validation", "bool is a subclass of int, so `True` is accepted as a price of 1", ("bool", "True", "isinstance")),
        ], note="validates prices (positive int, at most 50 million)"),
        Slot("bands", "band_duty", _D_BANDS, [
            Bad(_D_BANDS.replace("if price <= low:", "if price < low:"), "off-by-one", "a price exactly on a threshold starts a new empty band (`<` instead of `<=`), which adds a zero-width band to the breakdown", ("threshold", "<", "empty", "breakdown")),
            Bad(_D_BANDS.replace("amount = (top - low) * pct // 100", "amount = price * pct // 100"), "logic", "the percentage is applied to the whole price instead of the part inside the band (marginal rates become flat rates)", ("marginal", "whole price", "band", "top - low")),
            Bad(_D_BANDS.replace("min(price, high)", "high"), "logic", "every band is charged up to its upper threshold even when the price is lower, so cheap properties are overcharged", ("min", "price", "high", "cap")),
        ], note="adds `band_duty()`: marginal duty by band with a breakdown"),
        Slot("relief", "first_home_duty", _D_RELIEF, [
            Bad(_D_RELIEF.replace("duty * (price - FIRST_HOME_FREE) // (FIRST_HOME_END - FIRST_HOME_FREE)", "duty // (FIRST_HOME_END - FIRST_HOME_FREE) * (price - FIRST_HOME_FREE)"), "logic", "the division is done before the multiplication, so the integer division truncates the duty to almost nothing and the phase-in yields 0 for every realistic price", ("division", "order", "truncat", "precision"), kind="rounding"),
            Bad(_D_RELIEF.replace("(price - FIRST_HOME_FREE) // (FIRST_HOME_END - FIRST_HOME_FREE)", "(FIRST_HOME_END - price) // (FIRST_HOME_END - FIRST_HOME_FREE)"), "logic", "the phase-in runs backwards: the nearer the price is to FIRST_HOME_END the *less* duty is charged", ("phase", "backwards", "reversed", "FIRST_HOME_END")),
        ], note="adds first-home relief, phased in linearly between 400k and 500k"),
        Slot("quote", "quote", _D_QUOTE, [
            Bad(_D_QUOTE.replace("key = (price, first_home, resident, second_home)", "key = price"), "logic", "the memo cache is keyed by price only, so a later quote with different buyer flags returns the stale result of an earlier one", ("cache", "key", "stale", "flags"), kind="stale-cache"),
            Bad(_D_QUOTE.replace("if first_home and resident:", "if first_home:"), "logic", "relief is granted to non-resident first-home buyers although it is for residents only", ("resident", "relief", "first_home")),
            Bad(_D_QUOTE.replace("surcharge = price * pct // 100", "surcharge = duty * pct // 100"), "logic", "the surcharge is a percentage of the duty instead of the whole price", ("surcharge", "duty", "whole price")),
            Bad(_D_QUOTE.replace("        return dict(_cache[key])\n", "        return _cache[key]\n"), "api-misuse", "the cached dict itself is returned, so a caller that mutates the result corrupts the cache for everyone", ("mutable", "copy", "cache", "shared"), kind="state-mutation"),
        ], note="adds `quote()` with relief, surcharges and a memo cache"),
        Slot("parse", "parse_price", _D_PARSE, [
            Bad(_D_PARSE.replace("fullmatch", "match"), "validation", "re.match instead of fullmatch lets trailing junk through (\"12 000\" parses as 12)", ("match", "fullmatch", "trailing", "junk")),
            Bad(_D_PARSE.replace(r"(\d{1,3}(?:,\d{3})+|\d+)", r"([\d,]+)"), "validation", "the number pattern accepts any mix of digits and commas, so \"12,34\" parses as 1234", ("comma", "thousands", "pattern", "[\\d,]")),
        ], note="adds `parse_price()` for the web form"),
        Slot("money", "money", _D_MONEY, [
            Bad(_D_MONEY.replace('f"{n:,}"', 'f"{n:_}"'), "api-misuse", "the `_` format option groups with underscores (£1_234_567), not commas", ("_", "separator", "comma", "format")),
        ], nit=_D_MONEY.replace('"£" + f"{n:,}"', 'f"£{n:,}"'), note="adds `money()` formatting"),
    ],
)

# ---------------------------------------------------------------------------------------------------------------------
# podcast chapter files
# ---------------------------------------------------------------------------------------------------------------------

CHAPTER_TEMPLATE = dd('''
    """Podcast chapter files: parse "TIMECODE Title" lines, compute durations, export WebVTT and split-file names."""
    import os
    import re

    TIMECODE = re.compile(r"(?:(\\d+):)?(\\d{1,2}):(\\d{2})(?:\\.(\\d{1,3}))?")


    class ChapterError(ValueError):
        """The chapter file is malformed."""


    @@timecode@@


    @@fmt@@


    @@parse@@


    @@durations@@


    @@webvtt@@


    @@slug@@


    @@paths@@
''')

_C_TIMECODE = dd('''
    def parse_timecode(text):
        """"[H:]MM:SS[.mmm]" -> milliseconds. Minutes and seconds below 60 (hours unbounded when present)."""
        m = TIMECODE.fullmatch(text.strip())
        if not m:
            raise ChapterError(f"bad timecode: {text!r}")
        hours, minutes, seconds = int(m.group(1) or 0), int(m.group(2)), int(m.group(3))
        if minutes >= 60 or seconds >= 60:
            raise ChapterError(f"bad timecode: {text!r}")
        millis = int((m.group(4) or "0").ljust(3, "0"))
        return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis
''')
_C_FMT = dd('''
    def format_timecode(ms):
        """Milliseconds -> "HH:MM:SS.mmm"."""
        seconds, millis = divmod(ms, 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"
''')
_C_PARSE = dd('''
    def parse_chapters(text):
        """Chapters as (start_ms, title), sorted by start. `#` lines and blank lines are ignored. Duplicate starts are
        an error. If nothing starts at 0 an implicit "Intro" chapter is added."""
        found = {}
        for n, raw in enumerate(text.splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            stamp, _, title = line.partition(" ")
            start = parse_timecode(stamp)
            if start in found:
                raise ChapterError(f"line {n}: two chapters start at {format_timecode(start)}")
            found[start] = title.strip() or f"Chapter {len(found) + 1}"
        chapters = sorted(found.items())
        if not chapters or chapters[0][0] != 0:
            chapters.insert(0, (0, "Intro"))
        return chapters
''')
_C_DURATIONS = dd('''
    def durations(chapters, total_ms):
        """(title, length_ms) per chapter; a chapter ends where the next one starts, the last at total_ms."""
        out = []
        for i, (start, title) in enumerate(chapters):
            end = chapters[i + 1][0] if i + 1 < len(chapters) else total_ms
            if end <= start:
                raise ChapterError(f"chapter {title!r} would be empty or negative")
            out.append((title, end - start))
        return out
''')
_C_WEBVTT = dd('''
    def to_webvtt(chapters, total_ms):
        """A WebVTT chapters track."""
        lines = ["WEBVTT", ""]
        for i, (start, title) in enumerate(chapters):
            end = chapters[i + 1][0] if i + 1 < len(chapters) else total_ms
            lines.append(f"{format_timecode(start)} --> {format_timecode(end)}")
            lines.append(title)
            lines.append("")
        return "\\n".join(lines)
''')
_C_SLUG = dd('''
    def slugify(title):
        """Lower-case ASCII slug for a file name: runs of other characters become one '-'."""
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        return slug or "chapter"
''')
_C_PATHS = dd('''
    def split_paths(chapters, out_dir):
        """Target file for each chapter's audio: <out_dir>/<NN>-<slug>.mp3 (NN from 01)."""
        paths = []
        for i, (_, title) in enumerate(chapters, 1):
            paths.append(os.path.join(out_dir, f"{i:02d}-{slugify(title)}.mp3"))
        return paths
''')

CHAPTERS = Module(
    name="py-chapterfile", lang="python", path="chapters/marks.py", difficulty=2,
    title="Chapter file support: parse, durations, WebVTT and split names",
    blurb="The `chapters` package prepares chapter markers for a podcast hosting site.",
    intro=dd('''
        Editors send us chapter lists as plain text. This adds the library side so the upload page can validate them and the
        publisher can build the WebVTT track and the per-chapter audio file names:
    '''),
    outro=dd('''
        Titles come from the editors' text files, which we receive by e-mail, so treat them as untrusted when they end up in
        file names.
    '''),
    new_file=True,
    template=CHAPTER_TEMPLATE,
    ctx={"README.md": dd('''
        # chapters

        Chapter-marker helpers. `chapters/marks.py` parses the editors' chapter text files.
    '''), "chapters/__init__.py": '"""Chapter markers."""\n'},
    scenario=dd('''
        from chapters.marks import (ChapterError, durations, format_timecode, parse_chapters, parse_timecode, slugify, split_paths,
                                    to_webvtt)

        for t in ("0:05", "12:34.5", "1:02:03.045", "59:59", "60:00", "1:75", "7", "00:00:01", "1:30abc"):
            try:
                print(f"timecode {t!r}: {parse_timecode(t)} ms")
            except ChapterError as exc:
                print(f"timecode {t!r}: refused")
        for ms in (0, 999, 61_001, 3_723_004, 360_000_000):
            print("format", ms, format_timecode(ms))
        TEXT = """
        # shownotes for episode 41
        00:10 Cold open
        02:30.250 The harbour story
        01:05:00 Listener mail: ../../etc/passwd
        45:00
        """
        chapters = parse_chapters(TEXT)
        print(chapters)
        try:
            parse_chapters("00:00 A\\n0:00 B\\n")
        except ChapterError as exc:
            print("duplicate:", exc)
        print(parse_chapters("# nothing\\n"))
        print(parse_chapters("00:00.5 Start\\n"))
        try:
            print(durations([(0, "a"), (1000, "b")], 1000))
        except ChapterError as exc:
            print("zero length:", exc)
        print(durations(chapters, 4_000_000))
        try:
            print(durations(chapters, 3_000_000))
        except ChapterError as exc:
            print("too short:", exc)
        print(to_webvtt(chapters, 4_000_000))
        for title in ("Q&A -- part 1", "  ", "Ünïcode café", "../../etc/passwd"):
            print(repr(title), "->", slugify(title))
        print(split_paths(chapters, "out/ep41"))
    '''),
    slots=[
        Slot("timecode", "parse_timecode", _C_TIMECODE, [
            Bad(_C_TIMECODE.replace("if minutes >= 60 or seconds >= 60:", "if minutes > 60 or seconds > 60:"), "off-by-one", "`> 60` lets 60 minutes or 60 seconds through; the valid range ends at 59", ("60", ">=", "59", "range")),
            Bad(_C_TIMECODE.replace('(m.group(4) or "0").ljust(3, "0")', '(m.group(4) or "0").rjust(3, "0")'), "logic", "fractions are padded on the left, so `.5` means 5 ms instead of 500 ms", ("ljust", "rjust", "fraction", "pad")),
            Bad(_C_TIMECODE.replace("TIMECODE.fullmatch(text.strip())", "TIMECODE.match(text.strip())"), "validation", "match() instead of fullmatch() accepts trailing junk after a valid prefix", ("match", "fullmatch", "trailing")),
        ], note="adds `parse_timecode()` for `[H:]MM:SS[.mmm]`"),
        Slot("fmt", "format_timecode", _C_FMT, [
            Bad(_C_FMT.replace("{millis:03d}", "{millis}"), "logic", "milliseconds are not zero padded, so 1 ms prints as `.1`", ("zero", "pad", "03d", "millis")),
            Bad(_C_FMT.replace("hours, minutes = divmod(minutes, 60)", "hours, minutes = divmod(minutes, 60)\n    hours %= 24"), "off-by-one", "hours wrap at 24 so a 25 hour recording prints as 01:...", ("24", "wrap", "hours", "%=")),
        ], note="adds `format_timecode()`"),
        Slot("parse", "parse_chapters", _C_PARSE, [
            Bad(_C_PARSE.replace('''        if start in found:
            raise ChapterError(f"line {n}: two chapters start at {format_timecode(start)}")
''', ""), "validation", "duplicate start times are not rejected: the later line silently replaces the earlier one", ("duplicate", "silently", "found", "start")),
            Bad(_C_PARSE.replace("chapters[0][0] != 0", "chapters[0][0] > 1000"), "logic", "the implicit Intro chapter is only added when the first chapter starts more than a second in, which leaves a gap before it", ("Intro", "implicit", "!= 0", "first")),
            Bad(_C_PARSE.replace("chapters = sorted(found.items())", "chapters = list(found.items())"), "logic", "chapters are left in file order instead of being sorted by start time", ("sorted", "order", "start")),
        ], note="adds `parse_chapters()`: sorting, duplicate detection, implicit Intro"),
        Slot("durations", "durations", _C_DURATIONS, [
            Bad(_C_DURATIONS.replace("if end <= start:", "if end < start:"), "off-by-one", "a zero-length chapter is accepted (`<` instead of `<=`)", ("zero", "empty", "<=", "end")),
            Bad(_C_DURATIONS.replace("else total_ms", "else total_ms - start"), "logic", "the last chapter's end is computed as total_ms - start, so its length is wrong", ("last", "total_ms", "end")),
        ], note="adds `durations()`"),
        Slot("webvtt", "to_webvtt", _C_WEBVTT, [
            Bad(_C_WEBVTT.replace('f"{format_timecode(start)} --> {format_timecode(end)}"', 'f"{format_timecode(start)} -> {format_timecode(end)}"'), "logic", "the cue separator is `->` but WebVTT requires `-->`", ("-->", "separator", "cue", "WebVTT")),
            Bad(_C_WEBVTT.replace("else total_ms", "else start"), "logic", "the last cue ends at its own start time, so it has zero length", ("last", "cue", "total_ms")),
        ], note="adds `to_webvtt()`"),
        Slot("slug", "slugify", _C_SLUG, [
            Bad(_C_SLUG.replace('[^a-z0-9]+', '[^a-z0-9.]+'), "security", "dots survive in the slug, so a title like `../../etc/passwd` keeps `..` and can steer the output path outside the directory", ("path", "traversal", "..", "dot")),
            Bad(_C_SLUG.replace('.strip("-")', ""), "logic", "leading and trailing dashes are not stripped, so `Q&A!` becomes `q-a-`", ("strip", "dash", "trailing")),
        ], note="adds `slugify()` for file names"),
        Slot("paths", "split_paths", _C_PATHS, [
            Bad(_C_PATHS.replace("enumerate(chapters, 1)", "enumerate(chapters)"), "off-by-one", "numbering starts at 00 although file names are numbered from 01", ("enumerate", "start", "01", "numbering")),
            Bad(_C_PATHS.replace("os.path.join(out_dir, f\"{i:02d}-{slugify(title)}.mp3\")", "out_dir + \"/\" + f\"{i:02d}-{title}.mp3\""), "security", "the raw title is used in the path instead of the slug, so a title with `/` or `..` escapes the output directory", ("slugify", "title", "path", "traversal")),
        ], note="adds `split_paths()` for the per-chapter audio files"),
    ],
)

MODULES = [TIDEWATCH, KESTREL, CHAPTERS]
for _m in MODULES:
    validate_module(_m)
