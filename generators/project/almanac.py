"""project-almanac: a date engine for invented calendars read from a definition file (months, week cycle, blank days outside the
week, leap rules, overflow policies, recurrence rules).  Reference: Python (oracle) and JavaScript."""
from __future__ import annotations

from fx import family

from generators.project import _kit as K

THEME = "almanac"
TOOLS = ["almanac", "sundial", "ephemeris", "calendrix", "hourbook", "datelore", "reckoner", "tithe"]
MONTHS = ["Frost", "Thaw", "Sowing", "Bloom", "Ember", "Gale", "Harvest", "Mistral", "Tidewater", "Lantern", "Hearth", "Rime", "Solace", "Cinder",
          "Verdant", "Wane", "Brume", "Aurel", "Quill", "Fallow", "Marrow", "Thistle", "Ostrel", "Dunmar"]
WEEKDAYS = ["Sunwick", "Moonrow", "Tideday", "Windmark", "Emberday", "Stoneday", "Leafday", "Starday", "Riverday"]
BLANKS = ["Midwinter", "Longnight", "Founding", "Hollowday", "Stillday", "Lanternfeast", "Turnday", "Reaping", "Greeting", "Dayless"]
MAX_YEAR = 9999

PLAN = [
    dict(lang="javascript", style="day", parts=3, overflow="clamp", short="skip", serial=True, year=True, W=7, nm=12, nb=2),
    dict(lang="python", style="month", parts=2, overflow="spill", short="clamp", serial=True, year=False, W=6, nm=10, nb=1),
    dict(lang="javascript", style="day", parts=2, overflow="error", short="skip", serial=False, year=True, W=5, nm=13, nb=3),
    dict(lang="python", style="day", parts=3, overflow="spill", short="skip", serial=True, year=True, W=8, nm=9, nb=2),
    dict(lang="javascript", style="month", parts=3, overflow="clamp", short="clamp", serial=False, year=False, W=7, nm=11, nb=2),
    dict(lang="python", style="month", parts=3, overflow="error", short="clamp", serial=True, year=True, W=5, nm=12, nb=1),
    dict(lang="javascript", style="day", parts=2, overflow="spill", short="clamp", serial=True, year=False, W=6, nm=8, nb=3),
    dict(lang="python", style="day", parts=3, overflow="clamp", short="skip", serial=False, year=True, W=9, nm=10, nb=2),
]

VOICES = [
    "We need a date engine for the calendar of a game world. The calendar itself is *data* (`calendar.txt`: months, a week cycle, blank days that belong to no week, leap rules) and `README.md` defines every rule, command and message. The tool is `{tool}`, in {Lang}: the program is {run}. Run the visible examples with `python3 tests/run_examples.py`; the hidden checks use other calendars and many more dates.",
    "build {tool} per README.md, {Lang}. calendar.txt is read from the working dir, commands from stdin. {run}. examples: `python3 tests/run_examples.py`. careful with: blank days (no weekday!), leap years, and the rule for month arithmetic when the target month is shorter.",
    "Ticket CAL-{num}: implement the `{tool}` command-line calendar calculator (spec: README.md).\n\nNotes from the requester: the calendar is not Gregorian; do not hard-code anything. Weekday computation, serial numbers, `add`, `diff`, `nth` and `next` must all follow the README exactly, including the order in which input errors are reported. Language: {Lang}; the program is {run}.",
    "Could you write `{tool}` for me? It reads an invented calendar from `calendar.txt` (the README lists the directives and all the validation messages) and answers date questions from a script on standard input. Please use {Lang} and keep parsing, the calendar model and the commands in separate modules. The program is {run}; `python3 tests/run_examples.py` runs a few examples.",
    "Greenfield task in {Lang}: a date calculator for custom calendars, named `{tool}`. Everything is in README.md, from the year layout (months, blank days, leap days) to the `next` recurrence rules and error texts. The program is {run}. Hidden checks are grouped by command and use several different calendars, so nothing may be hard-coded.",
    "README.md describes `{tool}`; please implement it in {Lang} ({run}). The checks compare complete output, so the exact formats matter: the date line with its `[day/length]` suffix, the wording of the errors, and what `none` means for `nth`. Use `python3 tests/run_examples.py` for the visible ones.",
    "short version: calendar calculator, spec in README.md, {Lang}, name it {tool}. it has to handle leap rules, blank days and weeks that don't divide the year. {run}",
    "Please implement the calendar tool described in README.md. Name: `{tool}`. Language: {Lang}. How it is run: {run}. The tool must work for any calendar file following the grammar (week length 2 to 9, up to dozens of months, several blank days, a leap rule with two or three parts), not just the one in the examples; the hidden checks do use other files.",
]


def lines_of(s):
    return [x for x in s.split("\n")]


# ---------------------------------------------------------------------------------------------------------------
# calendar construction (generator side)
# ---------------------------------------------------------------------------------------------------------------

class Cal:
    def __init__(self, rng, p):
        self.p = p
        self.rng = rng
        self.week = rng.sample(WEEKDAYS, p["W"])
        names = rng.sample(MONTHS, p["nm"])
        base = rng.choice([[28, 30, 31], [24, 30, 36], [20, 25, 30], [30, 31, 32], [26, 28, 29]])
        self.months = [(n, rng.choice(base)) for n in names]
        self.blank_names = rng.sample(BLANKS, p["nb"] + 1)
        self.inters = []  # (name, anchor, leap_only)
        for b in self.blank_names[: p["nb"]]:
            self.inters.append((b, rng.choice(list(range(p["nm"])) + [p["nm"]] * 2), False))
        a = rng.choice([3, 4, 4, 5, 6, 7, 8])
        self.leap = (a, a * rng.choice([20, 25, 30]), None)
        if p["parts"] == 3:
            self.leap = (a, a * rng.choice([20, 25]), a * rng.choice([40, 50, 100]))
        self.leapmonth = None
        self.leapday = None
        if p["style"] == "day":
            self.leapday = self.blank_names[p["nb"]]
            self.inters.append((self.leapday, rng.choice(list(range(p["nm"])) + [p["nm"]]), True))
        else:
            self.leapmonth = rng.randrange(p["nm"])
        self.epoch = rng.randrange(p["W"])

    def is_leap(self, y):
        a, b, c = self.leap
        if y % a != 0:
            return False
        if b is None or y % b != 0:
            return True
        return c is not None and y % c == 0

    def month_len(self, i, y):
        return self.months[i][1] + (1 if self.leapmonth == i and self.is_leap(y) else 0)

    def text(self, rng, mutate=None):
        out = ["# calendar of the realm of " + rng.choice(["Ostrel", "Dunmar", "Quillon", "the Reach", "Verrin", "Tarn"])]
        out.append("week " + " ".join(self.week))
        out.append(f"epoch {self.week[self.epoch]}")
        out.append("")
        for n, ln in self.months:
            out.append(f"month {n} {ln}" + (f"   # {rng.choice(['cold', 'wet', 'dry', 'long', 'short'])}" if rng.random() < 0.2 else ""))
        out.append("")
        for name, anchor, leap_only in self.inters:
            if not leap_only:
                out.append(f"blank {name} after " + ("end" if anchor == len(self.months) else self.months[anchor][0]))
        out.append("leap " + " ".join(str(v) for v in self.leap if v is not None))
        if self.leapday:
            anchor = [x for x in self.inters if x[0] == self.leapday][0][1]
            out.append(f"leapday {self.leapday} after " + ("end" if anchor == len(self.months) else self.months[anchor][0]))
        if self.leapmonth is not None:
            out.append(f"leapmonth {self.months[self.leapmonth][0]}")
        return "\n".join(out) + "\n"


def interesting_years(cal):
    ys = {1, 2, 3, 4, 5, 9998, 9999, 9997}
    for v in cal.leap:
        if v:
            for m in (1, 2, 3, 5, 20, 25, 40, 50, 99, 100):
                for dlt in (-1, 0, 1):
                    y = m * v + dlt
                    if 1 <= y <= MAX_YEAR:
                        ys.add(y)
    return sorted(ys)


# ---------------------------------------------------------------------------------------------------------------
# README
# ---------------------------------------------------------------------------------------------------------------

def readme(p: dict, cal: Cal, tool: str, lang: str, by_name: dict) -> str:
    o: list[str] = []
    w = o.append
    day_style = p["style"] == "day"
    cmds = ["date", "diff", "add", "nth", "next"] + (["serial"] if p["serial"] else []) + (["year"] if p["year"] else [])
    w(f"# {tool}: a date engine for custom calendars\n")
    w(f"`{tool}` answers date questions for an invented calendar. The calendar is **data**: it is read from the file `calendar.txt` in the current directory "
      "(months, a week cycle, *blank days* that belong to no week, a leap rule). Questions come as a script on standard input; answers go to standard output. "
      "Nothing is hard-coded: the hidden checks use calendars other than the ones in the examples.\n")
    w(f"Build and run it as {K.how_to_run(lang, tool)}. The program reads `calendar.txt`, then the whole of standard input, runs the script line by line and exits. "
      "The exit status is `1` if any `error:` line was printed (including a calendar error), otherwise `0`.\n")
    w("## 1. calendar.txt\n")
    w("Lines are split into words at white space; `#` starts a comment that runs to the end of the line; lines without words are skipped (they still count for line numbers, which start at 1). "
      "The directives, in any order except where noted:\n")
    w("* `week NAME NAME ...`: the names of the days of the week, 2 to 9 of them, once in the file. Day number 0 is the first name.")
    w("* `epoch NAME`: the weekday of the first day of the first month of year 1 (once).")
    w("* `month NAME DAYS`: the next month of the year, in order; `DAYS` is 1 to 60. At least one month.")
    w("* `blank NAME after MONTH`: a **blank day** called `NAME` (any number of them) placed right after the last day of the month `MONTH`, or at the very end of the year if the word is `end` instead of a month. "
      "Several blank days after the same place keep the order of the file.")
    w("* `leap A [B [C]]`: the leap rule (at most once; " + ("1 to 3" if p["parts"] == 3 else "1 or 2") + " numbers: " +
      ("a year `Y` is a leap year if `Y` is divisible by `A` and either not divisible by `B` or divisible by `C`; with only `A` and `B`, if divisible by `A` but not by `B`; with `A` only, if divisible by `A`)." if p["parts"] == 3 else
       "a year `Y` is a leap year if `Y` is divisible by `A` and, when `B` is given, not divisible by `B`). ") + " Each number is 2 to 9999. Without a `leap` line there are no leap years.")
    if day_style:
        w("* `leapday NAME after MONTH`: like `blank`, but the day exists **only in leap years** (at most once; needs a `leap` line *before* it in the file).")
    else:
        w("* `leapmonth MONTH`: in leap years the month `MONTH` has one more day (at most once; needs a `leap` line *before* it in the file; the month must already be defined above).")
    w("\nA **name** (week day, month, blank day) is a letter followed by letters and digits, and is none of the reserved words `from count of last after end days weeks months years every monthly yearly blank`. "
      "Month names and blank day names must be different from each other and from earlier ones; week day names must differ among themselves (week day names may equal month names). "
      "Numbers are `0` or digits without a leading zero, at most six digits.\n")
    w("A problem prints `error: calendar.txt:LINE: MESSAGE` (or, for a missing file, `error: cannot read calendar.txt`) and the program stops with status 1 without reading the script. "
      "The first problem in file order wins; the message is one of: `unknown directive 'WORD'`; `bad line` (wrong number of words, or `after` missing); `bad name 'X'`; `duplicate name 'X'`; "
      "`bad number 'X'`; `number 'X' out of range`; `duplicate 'DIRECTIVE'` (for `week`, `epoch`, `leap`" + (", `leapday`" if day_style else ", `leapmonth`") + "); "
      "`no leap rule for '" + ("leapday" if day_style else "leapmonth") + "'`; `unknown month 'X'`" + (" (also for a `blank` or `leapday` anchor, which is checked after the whole file has been read, at the line of the directive)" if True else "") +
      "; `unknown weekday 'X'` (the `epoch`, checked at the end, at the line of the `epoch` directive). "
      "Within one line the checks run in this order: shape (`bad line`), names (`bad name`, `duplicate name`), then `duplicate '...'` and `no leap rule for '...'`, then numbers and month references (`bad number`, `number out of range`, `unknown month`). "
      "Finally, if nothing else was wrong: `error: calendar.txt: missing 'week'`, then `missing 'month'`, then `missing 'epoch'` (these have no line number).\n")
    w("## 2. The year\n")
    w("A year is a sequence of **days**: the days of month 1, then the blank days placed after month 1, then month 2, and so on; blank days anchored at `end` come last. "
      + ("In a leap year the `leapday` is part of the sequence (at its place, among the other blank days after the same anchor in file order); in other years it is absent. " if day_style else
         "In a leap year the leap month has one more day. ") +
      "Year numbers run from 1 to 9999. The **day of the year** (`doy`) counts all days, blank days included, starting at 1.\n")
    w("**Weekdays.** Only days of months have a weekday; blank days have none and are *skipped by the weekday cycle*. "
      "Count the month days since the first day of year 1 (that day has count 0): a month day with count `c` has weekday index `(epoch + c) mod W`, where `W` is the length of the week.\n")
    w("**Serial numbers.** The first day of year 1 has serial 1 and every following day (blank days included) the next number. Serials are unique over years 1 to 9999.\n")
    w("## 3. Dates in the script\n")
    w("A date is written `D MONTH Y` (a day of a month) or `NAME Y` (a blank day" + (", also the leap day" if day_style else "") + "). The kind is decided by the first word: all digits means a month day. "
      "It is checked in this order, and the first failure is reported as `error: MESSAGE`:\n")
    w("1. too few words, or a number that is not `0` or digits without leading zero (at most six digits): `bad date`;")
    w("2. a month (or blank day) name that is not defined: `unknown name 'X'`;")
    w("3. the year outside 1..9999: `year Y out of range (1..9999)`;")
    w("4. for a month day: the day outside the month's length in that year: `day D out of range for MONTH Y (1..L)`;")
    w("5. for a blank day that does not exist in that year" + (" (the leap day in a common year)" if day_style else "") + ": `no such day NAME Y`.")
    w("\nA date used by a command must take **all** the words the command gives it, so `date 3 MONTH 5 7` is a `bad date`.\n")
    w("The canonical text of a date (the *show format*) is `WEEKDAY D MONTH Y [DOY/LEN]` for a month day, `NAME Y [DOY/LEN]` for a blank day, where `LEN` is the number of days of that year.\n")
    w("## 4. Commands\n")
    w("Blank lines and lines starting with `#` are ignored. The first word is the command: " + ", ".join(f"`{c}`" for c in cmds) + ". Anything else: `error: unknown command 'WORD'`. "
      "Errors never stop the script. `DATE` below means the words of one date.\n")
    w("* `date DATE`: prints the show format.")
    if p["serial"]:
        w("* `serial DATE`: prints the serial number.")
    if p["year"]:
        w("* `year Y`: prints `year Y: LEN days, leap` (or `common`), then one line per segment of that year in order: two spaces, the month name and its length in that year (`  Frost 30`), or two spaces, `~`, a space and the blank day name (`  ~ Midwinter`). "
          "A wrong word count prints `error: usage: year YEAR`; `Y` is checked like the year of a date (`bad date`, then `year Y out of range (1..9999)`).")
    w("* `diff DATE DATE`: prints the number of days from the first date to the second (serial difference, negative if the second is earlier) as `N days`; the noun is `day` when `N` is 1 or -1.")
    w("* `add DATE N UNIT`: `N` is an integer with an optional sign (`bad number 'X'` otherwise), `UNIT` one of `days weeks months years` (`bad unit 'X'`); a wrong word count after the date prints `error: usage: add DATE N days|weeks|months|years`. "
      "Prints the show format of the result.")
    w("  * `days`: move `N` days along the serial numbers (blank days count as days). `weeks`: move `N * W` days. A result before serial 1 or after the last day of year 9999 is `error: date out of range (year 1 to 9999)`.")
    w("  * `months`: only for month days (a blank day gives `error: cannot add months to a blank day`). Number the months of all years consecutively (year `Y`, month index `i` counted from 0 is `Y * M + i` with `M` the number of months) and move by `N` (floor division for negative totals). "
      "The day stays `D`. A target year outside 1..9999 is `error: date out of range (year 1 to 9999)`. If the target month (in the target year) is shorter than `D`: ")
    ow = {"clamp": "the result is the **last day** of the target month.",
          "spill": "the result is the day `D - 1` days after the first day of the target month, counted along the serial numbers (so it may land in a blank day or in the next month; beyond year 9999 it is `error: date out of range (year 1 to 9999)`).",
          "error": "the command prints `error: no such day D MONTH Y` with the target month and year."}[p["overflow"]]
    w("    " + ow)
    w("  * `years`: move to year `Y + N` (outside 1..9999: `error: date out of range (year 1 to 9999)`) keeping month and day with the same overflow rule as for months; a blank day keeps its name and "
      "`error: no such day NAME Y` is printed (with the target year) if that year has no such day.")
    w("* `nth K WEEKDAY of MONTH Y`: `K` is `1` to `9` (one digit, nonzero) or `last`. Prints the show format of the `K`th (or last) day of month `MONTH` in year `Y` whose weekday is `WEEKDAY`, or `none` if there is no such day. "
      "Wrong word count or missing `of`: `error: usage: nth K|last WEEKDAY of MONTH YEAR`; checks, in order: `K` (`bad number 'X'`), the weekday name (`unknown name 'X'`), the month name (`unknown name 'X'`), the year (as in dates).")
    w("* `next RULE from DATE [count N]`: prints the next occurrences of a recurrence rule, one show-format line each, starting with the first occurrence that is **not before** `DATE`; `N` (default 5) is 1 to 50 (`bad count 'X'`; after the date only `count N` may follow, else `error: usage: next RULE from DATE [count N]`; no `from` gives the same usage text). "
      "If the calendar runs out (after the last day of year 9999) fewer lines are printed (possibly none). The rules (every number is 1 to 3 digits, nonzero):")
    w("  * `every K days` and `every K weeks`: `DATE` itself, then every `K` days (every `K * W` days) along the serial numbers, blank days counting as days. `bad number 'X'` for a bad `K`.")
    w("  * `monthly D`: day `D` of each month in turn, starting with the months of the year of `DATE` (earlier ones are not occurrences). " +
      ("A month shorter than `D` has no occurrence (skipped)." if p["short"] == "skip" else "In a month shorter than `D` the occurrence is the last day of the month.") +
      " If `D` is more than the longest month (counting the extra day of a leap month) the rule is `error: day D never occurs`.")
    w("  * `monthly K WEEKDAY` (`K` is `1` to `9` or `last`): the `K`th (or last) day with that weekday of each month; months without one are skipped. Errors: `bad number 'X'`, `unknown name 'X'`.")
    w("  * `yearly D MONTH`: day `D` of `MONTH` in each year (a year in which the month is too short is skipped); `unknown name 'X'` for the month; `error: day D never occurs` if `D` exceeds the month's longest length.")
    w("  * `blank NAME`: the blank day `NAME` in each year that has it" + (" (the leap day only in leap years)" if day_style else "") + "; `unknown name 'X'` if there is no such blank day in the calendar.")
    w("  * anything else: `error: bad rule`.")
    w("\nThe rule is checked (in the order of the list above, after `from` and the date were parsed and the count) before anything is printed, so an error prints no date lines. "
      "The checks in `next` run in this order: `from` present; the date; the `count` part; then the rule.\n")
    w("## 5. Examples\n")
    ex = [(c, r) for (c, r) in by_name.values() if c.visible]
    for c, r in ex[:3]:
        w(K.show_case(tool, c, r))
    w("The visible examples (`tests/examples.json`, `python3 tests/run_examples.py`) use the same layout as the hidden checks: a `calendar.txt`, a script, the expected output.")
    return "\n".join(o) + "\n"


# ---------------------------------------------------------------------------------------------------------------
# cases
# ---------------------------------------------------------------------------------------------------------------

class Gen:
    def __init__(self, cal: Cal, p, rng):
        self.cal, self.p, self.rng = cal, p, rng
        self.years = interesting_years(cal)

    def year(self):
        return self.rng.choice(self.years) if self.rng.random() < 0.7 else self.rng.randint(1, MAX_YEAR)

    def date(self, y=None, kind=None):
        cal, rng = self.cal, self.rng
        y = y or self.year()
        if kind is None:
            kind = "blank" if (cal.inters and rng.random() < 0.22) else "month"
        if kind == "blank":
            cands = [n for n, _, lo in cal.inters if not lo or cal.is_leap(y)]
            return f"{rng.choice(cands)} {y}"
        i = rng.randrange(len(cal.months))
        ln = cal.month_len(i, y)
        d = rng.choice([1, ln, max(1, ln - 1), rng.randint(1, ln), rng.randint(1, ln)])
        return f"{d} {cal.months[i][0]} {y}"

    def pair(self):
        return self.date(), self.date()

    def rule(self):
        cal, rng = self.cal, self.rng
        kind = rng.choice(["every", "every", "monthly", "monthly", "mweek", "yearly", "blank"])
        if kind == "every":
            return f"every {rng.choice([1, 2, 3, 7, 10, 30, 100, 400])} {rng.choice(['days', 'weeks'])}"
        if kind == "monthly":
            top = max(ln for _, ln in cal.months) + (1 if cal.leapmonth is not None else 0)
            return f"monthly {rng.choice([1, 2, 7, 15, top - 2, top - 1, top, top, top + 1 if rng.random() < 0.15 else top - 3])}"
        if kind == "mweek":
            return f"monthly {rng.choice(['1', '2', '3', '4', '5', '6', 'last'])} {rng.choice(cal.week)}"
        if kind == "yearly":
            i = rng.randrange(len(cal.months))
            return f"yearly {rng.choice([1, 10, cal.months[i][1], cal.months[i][1] + (1 if cal.leapmonth == i else 0)])} {cal.months[i][0]}"
        names = [n for n, _, _ in cal.inters]
        return f"blank {rng.choice(names)}" if names else "every 3 days"


def make_cases(p: dict, cal: Cal, tool: str, rng) -> list[K.Case]:
    g = Gen(cal, p, rng)
    base_text = cal.text(rng)
    cases: list[K.Case] = []
    cnt: dict[str, int] = {}

    def add(group, lines, visible=False, files=None):
        cnt[group] = cnt.get(group, 0) + 1
        cases.append(K.Case(name=f"{group}-{cnt[group]:02d}", group=group, stdin="\n".join(lines) + "\n", files=files if files is not None else {"calendar.txt": base_text}, visible=visible))

    # date / serial / year
    for k in range(4):
        lines = []
        for _ in range(12):
            d = g.date()
            lines.append("date " + d)
            if p["serial"] and rng.random() < 0.4:
                lines.append("serial " + d)
        if p["year"]:
            lines += [f"year {y}" for y in rng.sample(g.years, 1 if k == 0 else 3)]
        add("date", lines[:8] if k == 0 else lines, visible=(k == 0))
    # weekday cycle over many consecutive days (blank days do not advance the week)
    for k in range(2):
        y = g.year()
        i = rng.randrange(len(cal.months))
        lines = [f"add {cal.month_len(i, y)} {cal.months[i][0]} {y} {n} days" for n in range(0, 5)]
        lines += [f"add {cal.month_len(i, y)} {cal.months[i][0]} {y} {n} weeks" for n in (1, -1, 52)]
        add("weekday", lines)
    # add
    for unit, count in (("days", 3), ("weeks", 2), ("months", 4), ("years", 4)):
        for k in range(count):
            lines = []
            for _ in range(12):
                d = g.date()
                if unit in ("days", "weeks"):
                    n = rng.choice([0, 1, -1, 7, -7, rng.randint(-400, 400), rng.randint(-5000, 5000), rng.randint(-200000, 200000)])
                elif unit == "months":
                    n = rng.choice([0, 1, -1, 12, -12, rng.randint(-40, 40), rng.randint(-300, 300)])
                else:
                    n = rng.choice([0, 1, -1, 4, -4, rng.randint(-30, 30), rng.randint(-500, 500)])
                lines.append(f"add {d} {n if rng.random() < 0.7 else '+' + str(abs(n)) if n >= 0 else n} {unit}")
            add(f"add-{unit}", lines, visible=False)
    # month-end overflow: the last days of the longest months moved to shorter months and leap months
    for k in range(3):
        lines = []
        longest = max(range(len(cal.months)), key=lambda i: cal.months[i][1])
        for _ in range(10):
            y = g.year()
            i = longest if rng.random() < 0.6 else rng.randrange(len(cal.months))
            d = cal.month_len(i, y)
            n = rng.choice([1, 2, 3, -1, -2, 11, 13, 12, -12, 24])
            lines.append(f"add {d} {cal.months[i][0]} {y} {n} {rng.choice(['months', 'months', 'years'])}")
        if cal.leapmonth is not None:
            ly = next(y for y in range(1, 100) if cal.is_leap(y))
            lm = cal.months[cal.leapmonth][0]
            lines += [f"add {cal.month_len(cal.leapmonth, ly)} {lm} {ly} 1 years", f"add {cal.month_len(cal.leapmonth, ly)} {lm} {ly} 4 years", f"add {cal.month_len(cal.leapmonth, ly)} {lm} {ly} -{cal.leap[0]} years"]
        if cal.leapday:
            ly = next(y for y in range(1, 100) if cal.is_leap(y))
            lines += [f"add {cal.leapday} {ly} 1 years", f"add {cal.leapday} {ly} {cal.leap[0]} years", f"add {cal.leapday} {ly} 1 days", f"add {cal.leapday} {ly} 1 months"]
        add("overflow", lines)
    # diff
    for k in range(3):
        lines = []
        for _ in range(10):
            a, b = g.pair()
            lines.append(f"diff {a} {b}")
            if rng.random() < 0.3:
                lines.append(f"diff {a} {a}")
        lines.append(f"diff 1 {cal.months[0][0]} 1 {cal.months[-1][1]} {cal.months[-1][0]} 9999")
        add("diff", lines, visible=False)
    # nth
    for k in range(3):
        lines = []
        for _ in range(12):
            y = g.year()
            lines.append(f"nth {rng.choice(['1', '2', '3', '4', '5', '6', '7', 'last'])} {rng.choice(cal.week)} of {rng.choice(cal.months)[0]} {y}")
        add("nth", lines)
    # next
    for k in range(5):
        lines = []
        for _ in range(7):
            r = g.rule()
            c = rng.choice(["", "", " count 1", " count 3", " count 12", " count 50"])
            lines.append(f"next {r} from {g.date()}{c}")
        if k == 0:
            lines.append(f"next every 400 days from 1 {cal.months[0][0]} 9990 count 50")
            lines.append(f"next yearly 1 {cal.months[0][0]} from 1 {cal.months[0][0]} 9998 count 10")
        add("next", lines, visible=(k == 0 and False))
    # errors in the script
    m0, m1 = cal.months[0][0], cal.months[1][0]
    blanks = [n for n, _, _ in cal.inters]
    for k in range(3):
        lines = ["", "# a comment", "frob 1", "date", f"date 0 {m0} 5", f"date 99 {m0} 5", f"date 5 Nowhere 5", f"date 5 {m0} 0", f"date 5 {m0} 10000", f"date 5 {m0} 1000000",
                 f"date 05 {m0} 5", f"date 5 {m0}", f"date {m0} 5", f"date 5 {m0} 5 extra", f"date {blanks[0]}", f"date {blanks[0]} 7 8", f"date 5 {m0} x",
                 "serial 5", "year 5 6", "year x", "year 0",
                 f"diff 5 {m0} 5", f"diff 5 {m0} 5 6 {m1} 5 7", f"add 5 {m0} 5", f"add 5 {m0} 5 x days", f"add 5 {m0} 5 1 fortnights", f"add 5 {m0} 5 1 days extra", f"add 5 {m0} 5 1.5 days",
                 f"add 1 {m0} 1 -1 days", f"add 1 {m0} 1 -1 years", f"add 1 {m0} 1 -1 months", f"add 1 {m0} 9999 99999 days", f"add 1 {m0} 9999 1 years", f"add 1 {m0} 9999 12 months",
                 f"nth 1 {cal.week[0]} {m0} 5", f"nth 0 {cal.week[0]} of {m0} 5", f"nth first {cal.week[0]} of {m0} 5", f"nth 1 Nope of {m0} 5", f"nth 1 {cal.week[0]} of Nope 5", f"nth 1 {cal.week[0]} of {m0} 0",
                 f"next every 3 days", f"next every 3 days from 5 {m0} 5 count 0", f"next every 3 days from 5 {m0} 5 count 51", f"next every 3 days from 5 {m0} 5 more 5", f"next every 0 days from 5 {m0} 5",
                 f"next every 3 fortnights from 5 {m0} 5", f"next monthly 99 from 5 {m0} 5", f"next monthly 0 from 5 {m0} 5", f"next monthly x {cal.week[0]} from 5 {m0} 5", f"next monthly 2 Nope from 5 {m0} 5",
                 f"next yearly 5 Nope from 5 {m0} 5", f"next yearly 99 {m0} from 5 {m0} 5", f"next blank Nope from 5 {m0} 5", f"next bogus from 5 {m0} 5", f"next from 5 {m0} 5",
                 f"date {blanks[0]} 5", "date 1 " + m0 + " 1  "]
        if cal.leapday:
            lines += [f"date {cal.leapday} 1", f"date {cal.leapday} {cal.leap[0]}", f"next blank {cal.leapday} from 1 {m0} 1 count 4", f"next blank {cal.leapday} from 1 {m0} 9990 count 4"]
        rng.shuffle(lines)
        add("errors", lines)
    # calendar file errors
    good = base_text.split("\n")
    first_month = cal.months[0][0]

    def variant(edit):
        ls = list(good)
        edit(ls)
        return "\n".join(ls) + "\n"

    def line_of(prefix):
        return next(i for i, x in enumerate(good) if x.startswith(prefix))

    muts = [
        ("unknown directive", lambda ls: ls.insert(3, "frobnicate 1")),
        ("duplicate week", lambda ls: ls.insert(3, "week A B C")),
        ("week too short", lambda ls: ls.__setitem__(line_of("week"), "week Solo")),
        ("week too long", lambda ls: ls.__setitem__(line_of("week"), "week " + " ".join(f"D{i}" for i in range(10)))),
        ("month zero", lambda ls: ls.insert(line_of("month"), "month Zero 0")),
        ("month 61", lambda ls: ls.insert(line_of("month") + 1, "month Big 61")),
        ("month word", lambda ls: ls.insert(line_of("month"), "month Bad x1")),
        ("month leading zero", lambda ls: ls.insert(line_of("month"), "month Lead 07")),
        ("duplicate month", lambda ls: ls.append(f"month {first_month} 3")),
        ("reserved name", lambda ls: ls.insert(line_of("month"), "month from 3")),
        ("bad name", lambda ls: ls.insert(line_of("month"), "month 9lives 3")),
        ("blank anchor", lambda ls: ls.append("blank Extra after Nowhere")),
        ("blank no after", lambda ls: ls.append("blank Extra before end")),
        ("blank dup name", lambda ls: ls.append(f"blank {first_month} after end")),
        ("epoch unknown", lambda ls: ls.__setitem__(line_of("epoch"), "epoch Nodayname")),
        ("missing epoch", lambda ls: ls.pop(line_of("epoch"))),
        ("missing week", lambda ls: ls.pop(line_of("week"))),
        ("missing month", lambda ls: [ls.pop(i) for i in reversed(range(len(ls))) if ls[i].startswith("month")]),
        ("leap one number too many", lambda ls: ls.__setitem__(line_of("leap "), "leap 4 100 400 800")),
        ("leap bad number", lambda ls: ls.__setitem__(line_of("leap "), "leap four 100")),
        ("leap out of range", lambda ls: ls.__setitem__(line_of("leap "), "leap 1 100")),
        ("duplicate leap", lambda ls: ls.append("leap 4 100")),
        ("leap style other", lambda ls: ls.append("leapmonth " + first_month if p["style"] == "day" else "leapday Extra after end")),
        ("epoch twice", lambda ls: ls.append("epoch " + cal.week[0])),
        ("no leap rule", lambda ls: (ls.pop(line_of("leap ")), None)[1]),
    ]
    rng.shuffle(muts)
    for name, edit in muts[:16]:
        try:
            text = variant(edit)
        except StopIteration:
            continue
        add("calendar", [f"date 1 {first_month} 1"], files={"calendar.txt": text})
    add("calendar", [f"date 1 {first_month} 1"], files={})
    return cases


@family("project-almanac", category="project", lang="javascript", kind="greenfield", n=8,
        summary="a date engine for invented calendars from a definition file: blank days outside the week, leap rules, overflow policies, recurrence rules")
def gen(rng, n):
    for i in range(n):
        plan = dict(PLAN[i])
        tool = TOOLS[i]
        lang = plan.pop("lang")
        p = dict(plan)
        cal = Cal(rng, p)
        cfg = dict(MAX_MONTH=60, LEAP_STYLE=p["style"], LEAP_PARTS=p["parts"], OVERFLOW=p["overflow"], SHORT_MONTH=p["short"], HAS_SERIAL=p["serial"], HAS_YEAR=p["year"])
        cases = make_cases(p, cal, tool, rng)
        py_sol = K.merged(K.load_src(THEME, "python", tool), K.render_config("python", cfg))
        sol = py_sol if lang == "python" else K.merged(K.load_src(THEME, lang, tool), K.render_config(lang, cfg))
        voice = VOICES[i % len(VOICES)]
        prompt = voice.format(tool=tool, Lang=K.LANG_NAME[lang], run=K.how_to_run(lang, tool), num=5100 + i * 41)
        nfeat = sum([p["style"] == "month", p["overflow"] != "clamp", p["parts"] == 3, p["short"] == "clamp", p["W"] >= 8])
        yield K.project_task(
            theme=THEME, tool=tool, lang=lang, cases=cases, solution=sol, py_solution=py_sol,
            readme=lambda by_name, p=p, cal=cal, tool=tool, lang=lang: readme(p, cal, tool, lang, by_name),
            prompt=prompt, difficulty=4 if nfeat <= 2 else 5, slug=f"{i + 1:02d}-{tool}-{p['style']}-{p['overflow']}",
            notes={"week": p["W"], "months": p["nm"], "blanks": p["nb"], "style": p["style"], "overflow": p["overflow"], "short": p["short"], "leap": list(cal.leap)},
            extra_start={}, tags=["calendar", "dates"],
        )
