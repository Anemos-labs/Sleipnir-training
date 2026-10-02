"""Python libraries, theme time/money/scheduling (batch misc-b): club-week calendar rendering, expense-claim workflow with
business-day escalation."""
from fx import Lib, dd, register_libs

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# clubcal: club weeks (week 1 starts on the year's first Monday) and text month calendars
# ======================================================================================================================

CC_README = dd('''
    # clubcal

    Calendar helpers for a rowing club's newsletter. Dates are `datetime.date`.

    ## Club weeks (`clubcal/weeks.py`)

    The club counts weeks its own way: **week 1 of a year starts on the first Monday of that year**. The days before it
    (1 January up to the day before the first Monday) are week 0. A date always belongs to the club year of its own
    calendar year, so the last days of December belong to the last week of their year even when that week reaches into
    January.

    * `first_monday(year)`: the first Monday of the year.
    * `club_week(d)`: the club week number of `d`.
    * `weeks_in_year(year)`: the club week number of 31 December.
    * `week_span(year, n)`: `(first_day, last_day)` of club week `n`, cut to the year (week 0 starts on 1 January; the last
      week ends on 31 December at the latest). `n` outside `0..weeks_in_year(year)`, or `n == 0` in a year that starts on a
      Monday (so it has no week 0), is a `ValueError`.

    ## Rendering (`clubcal/render.py`)

    * `month_grid(year, month, first_weekday=0)`: the month as rows of 7 numbers (0 for the cells that belong to other
      months); `first_weekday` is the weekday the rows start on (Monday is 0, Sunday 6), otherwise `ValueError`.
    * `render_month(year, month, first_weekday=0, marks=(), weeks=False)`: a list of text lines.
      - the title `"March 2025"` centred in 20 columns with trailing spaces removed;
      - the weekday header: the two-letter names `Mo Tu We Th Fr Sa Su`, rotated to start at `first_weekday`, each followed
        by one space, trailing spaces removed;
      - one line per grid row; every day is a cell of 3 characters: the day number right-aligned in 2 characters (two
        spaces for an empty cell) followed by `*` when the day is in `marks` and a space otherwise; the cells are joined
        and trailing spaces removed;
      - with `weeks=True` the header line and every grid line start with a 4-character prefix: spaces on the header, and
        `wNN ` (`NN` the club week of the first day of the month in that row, two digits) on the rows. Week numbers
        only make sense for weeks that start on Monday: `weeks=True` with another `first_weekday` is a `ValueError`.
''')

CC_WEEKS = dd('''
    from datetime import date, timedelta


    def first_monday(year):
        jan1 = date(year, 1, 1)
        return jan1 + timedelta(days=(7 - jan1.weekday()) % 7)


    def club_week(d):
        start = first_monday(d.year)
        if d < start:
            return 0
        return (d - start).days // 7 + 1


    def weeks_in_year(year):
        return club_week(date(year, 12, 31))


    def week_span(year, n):
        if not 0 <= n <= weeks_in_year(year):
            raise ValueError("no such week")
        start = first_monday(year)
        if n == 0:
            if start == date(year, 1, 1):
                raise ValueError("this year has no week 0")
            return date(year, 1, 1), start - timedelta(days=1)
        monday = start + timedelta(days=7 * (n - 1))
        return monday, min(monday + timedelta(days=6), date(year, 12, 31))
''')

CC_RENDER = dd('''
    import calendar
    from datetime import date

    from .weeks import club_week

    MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]


    def month_grid(year, month, first_weekday=0):
        if not 0 <= first_weekday <= 6:
            raise ValueError("first_weekday must be 0..6")
        lead = (date(year, month, 1).weekday() - first_weekday) % 7
        cells = [0] * lead + list(range(1, calendar.monthrange(year, month)[1] + 1))
        cells += [0] * (-len(cells) % 7)
        return [cells[i:i + 7] for i in range(0, len(cells), 7)]


    def render_month(year, month, first_weekday=0, marks=(), weeks=False):
        if weeks and first_weekday != 0:
            raise ValueError("week numbers need weeks that start on Monday")
        lines = [("%s %d" % (MONTHS[month - 1], year)).center(20).rstrip()]
        names = [DAYS[(first_weekday + i) % 7] for i in range(7)]
        lines.append(("    " if weeks else "") + "".join(n + " " for n in names).rstrip())
        for row in month_grid(year, month, first_weekday):
            cells = []
            for day in row:
                text = "%2d" % day if day else "  "
                cells.append(text + ("*" if day in marks else " "))
            head = ""
            if weeks:
                first = next(day for day in row if day)
                head = "w%02d " % club_week(date(year, month, first))
            lines.append((head + "".join(cells)).rstrip())
        return lines
''')

CC_VISIBLE = dd('''
    import unittest
    from datetime import date

    from clubcal.weeks import club_week, first_monday


    class BasicTests(unittest.TestCase):
        def test_first_monday(self):
            self.assertEqual(first_monday(2025), date(2025, 1, 6))

        def test_week_one(self):
            self.assertEqual(club_week(date(2025, 1, 6)), 1)


    if __name__ == "__main__":
        unittest.main()
''')

CC_HIDDEN = dd('''
    import calendar
    import unittest
    from datetime import date, timedelta

    from clubcal.render import month_grid, render_month
    from clubcal.weeks import club_week, first_monday, week_span, weeks_in_year

    D = date


    class Weeks(unittest.TestCase):
        def test_first_mondays(self):
            table = {2023: D(2023, 1, 2), 2024: D(2024, 1, 1), 2025: D(2025, 1, 6), 2026: D(2026, 1, 5), 2027: D(2027, 1, 4),
                     2022: D(2022, 1, 3), 2021: D(2021, 1, 4)}
            for year, monday in table.items():
                self.assertEqual(first_monday(year), monday, year)

        def test_week_numbers(self):
            table = {D(2025, 1, 1): 0, D(2025, 1, 5): 0, D(2025, 1, 6): 1, D(2025, 1, 12): 1, D(2025, 1, 13): 2, D(2025, 12, 29): 52,
                     D(2025, 12, 31): 52, D(2024, 1, 1): 1, D(2024, 12, 30): 53, D(2024, 12, 31): 53, D(2026, 1, 1): 0, D(2026, 1, 5): 1,
                     D(2023, 1, 1): 0, D(2023, 1, 2): 1}
            for day, week in table.items():
                self.assertEqual(club_week(day), week, day)

        def test_weeks_in_year(self):
            self.assertEqual([weeks_in_year(y) for y in (2022, 2023, 2024, 2025, 2026, 2027)], [52, 52, 53, 52, 52, 52])

        def test_week_numbers_increase_with_the_date(self):
            day = D(2025, 1, 1)
            last = -1
            while day.year == 2025:
                week = club_week(day)
                self.assertGreaterEqual(week, last)
                self.assertEqual(week, 0 if day < D(2025, 1, 6) else (day - D(2025, 1, 6)).days // 7 + 1)
                last = week
                day += timedelta(days=1)

        def test_spans(self):
            self.assertEqual(week_span(2025, 0), (D(2025, 1, 1), D(2025, 1, 5)))
            self.assertEqual(week_span(2025, 1), (D(2025, 1, 6), D(2025, 1, 12)))
            self.assertEqual(week_span(2025, 2), (D(2025, 1, 13), D(2025, 1, 19)))
            self.assertEqual(week_span(2025, 52), (D(2025, 12, 29), D(2025, 12, 31)))
            self.assertEqual(week_span(2024, 53), (D(2024, 12, 30), D(2024, 12, 31)))
            self.assertEqual(week_span(2023, 0), (D(2023, 1, 1), D(2023, 1, 1)))
            self.assertEqual(week_span(2026, 0), (D(2026, 1, 1), D(2026, 1, 4)))
            self.assertEqual(week_span(2024, 1), (D(2024, 1, 1), D(2024, 1, 7)))

        def test_spans_are_consistent_with_club_week(self):
            for year in (2023, 2024, 2025):
                for n in range(1, weeks_in_year(year) + 1):
                    first, last = week_span(year, n)
                    self.assertEqual(club_week(first), n)
                    self.assertEqual(club_week(last), n)
                    self.assertEqual(first.year, year)
                    self.assertEqual(last.year, year)

        def test_span_errors(self):
            for year, n in ((2024, 0), (2025, 53), (2025, -1), (2024, 54), (2027, 53), (2022, 53)):
                with self.assertRaises(ValueError, msg=(year, n)):
                    week_span(year, n)
            week_span(2024, 53)


    class Grid(unittest.TestCase):
        def test_matches_the_standard_library(self):
            for first in range(7):
                for year in (2024, 2025, 2026):
                    for month in range(1, 13):
                        self.assertEqual(month_grid(year, month, first), calendar.Calendar(first).monthdayscalendar(year, month), (first, year, month))

        def test_shape(self):
            self.assertEqual(month_grid(2025, 3)[0], [0, 0, 0, 0, 0, 1, 2])
            self.assertEqual(month_grid(2025, 3)[-1], [31, 0, 0, 0, 0, 0, 0])
            self.assertEqual(month_grid(2025, 3, 6)[0], [0, 0, 0, 0, 0, 0, 1])
            self.assertEqual(len(month_grid(2021, 2)), 4)    # a February that starts on a Monday
            self.assertEqual(len(month_grid(2026, 2)), 5)
            self.assertEqual(len(month_grid(2026, 3)), 6)    # 31 days starting on a Sunday
            self.assertEqual(month_grid(2026, 2)[0], [0, 0, 0, 0, 0, 0, 1])

        def test_first_weekday_range(self):
            for first in (-1, 7, 10):
                with self.assertRaises(ValueError):
                    month_grid(2025, 3, first)
            month_grid(2025, 3, 6)


    class Render(unittest.TestCase):
        def test_plain_month(self):
            self.assertEqual(render_month(2025, 3), [
                "     March 2025",
                "Mo Tu We Th Fr Sa Su",
                "                1  2",
                " 3  4  5  6  7  8  9",
                "10 11 12 13 14 15 16",
                "17 18 19 20 21 22 23",
                "24 25 26 27 28 29 30",
                "31"])

        def test_marks(self):
            lines = render_month(2025, 3, marks=(3, 14, 31))
            self.assertEqual(lines[2:], [
                "                1  2",
                " 3* 4  5  6  7  8  9",
                "10 11 12 13 14*15 16",
                "17 18 19 20 21 22 23",
                "24 25 26 27 28 29 30",
                "31*"])
            self.assertEqual(lines[:2], render_month(2025, 3)[:2])

        def test_other_first_weekday(self):
            self.assertEqual(render_month(2025, 3, first_weekday=6), [
                "     March 2025",
                "Su Mo Tu We Th Fr Sa",
                "                   1",
                " 2  3  4  5  6  7  8",
                " 9 10 11 12 13 14 15",
                "16 17 18 19 20 21 22",
                "23 24 25 26 27 28 29",
                "30 31"])
            lines = render_month(2025, 3, first_weekday=3, marks=(1,))
            self.assertEqual(lines[1], "Th Fr Sa Su Mo Tu We")
            self.assertEqual(lines[2], "       1* 2  3  4  5")
            self.assertEqual(lines[-1], "27 28 29 30 31")

        def test_title_is_centred(self):
            self.assertEqual(render_month(2025, 5)[0], "      May 2025")
            self.assertEqual(render_month(2025, 9)[0], "   September 2025")
            self.assertEqual(render_month(2025, 2)[0], "   February 2025")

        def test_week_numbers(self):
            self.assertEqual(render_month(2025, 2, weeks=True), [
                "   February 2025",
                "    Mo Tu We Th Fr Sa Su",
                "w04                 1  2",
                "w05  3  4  5  6  7  8  9",
                "w06 10 11 12 13 14 15 16",
                "w07 17 18 19 20 21 22 23",
                "w08 24 25 26 27 28"])
            self.assertEqual(render_month(2024, 12, weeks=True)[-2:], ["w52 23 24 25 26 27 28 29", "w53 30 31"])

        def test_week_zero_is_shown(self):
            lines = render_month(2025, 1, weeks=True)
            self.assertEqual(lines[2], "w00        1  2  3  4  5")
            self.assertEqual(lines[3], "w01  6  7  8  9 10 11 12")

        def test_week_numbers_need_monday_weeks(self):
            with self.assertRaises(ValueError):
                render_month(2025, 3, first_weekday=6, weeks=True)
            with self.assertRaises(ValueError):
                render_month(2025, 3, first_weekday=1, weeks=True)

        def test_no_trailing_spaces(self):
            for line in render_month(2025, 3, marks=(2, 30, 31)) + render_month(2024, 2, 6) + render_month(2025, 2, weeks=True):
                self.assertEqual(line, line.rstrip())


    if __name__ == "__main__":
        unittest.main()
''')

CLUBCAL = Lib(
    name="clubcal", lang="python", title="the club-week calendar (`clubcal/`)",
    blurb="The rowing club's newsletter prints month calendars with its own week numbering using clubcal.",
    files={"clubcal/__init__.py": "", "clubcal/weeks.py": CC_WEEKS, "clubcal/render.py": CC_RENDER, "README.md": CC_README,
           ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": CC_VISIBLE},
    hidden_tests={"tests/test_full.py": CC_HIDDEN},
    mutate=["clubcal/weeks.py", "clubcal/render.py"], difficulty=2, tags=["calendar", "weeks", "rendering"],
    probes=[
        "first_monday(2023)", "first_monday(2025)", "club_week(date(2025, 1, 5))", "club_week(date(2025, 1, 6))", "club_week(date(2024, 12, 31))",
        "weeks_in_year(2024)", "week_span(2025, 0)", "week_span(2025, 52)", "week_span(2024, 53)", "week_span(2025, 53)",
        "month_grid(2025, 3)[0]", "month_grid(2025, 3, 6)[0]", "len(month_grid(2026, 3))",
        "render_month(2025, 3, marks=(3, 14, 31))[2:5]", "render_month(2025, 3, first_weekday=6)[:3]", "render_month(2025, 2, weeks=True)[2:4]",
        "render_month(2025, 1, weeks=True)[2]",
    ],
    probe_import="from datetime import date\nfrom clubcal.weeks import *\nfrom clubcal.render import *",
)

# ======================================================================================================================
# claimflow: expense-claim approval workflow with approver counts and business-day escalation
# ======================================================================================================================

CF_README = dd('''
    # claimflow

    Expense-claim approval for a finance team. Amounts are `int` cents; dates are `datetime.date`.

    ## Calendar helpers (`claimflow/sla.py`)

    A business day is a weekday (Mon to Fri) that is not in `holidays` (an optional collection of dates).

    * `business_days_between(start, end, holidays=())`: the business days in `(start, end]` (`start` excluded); `0` when
      `end <= start`.
    * `add_business_days(d, n, holidays=())`: `n >= 0` business days after `d` (`d` is not counted, and need not be a
      business day); `n == 0` returns `d`.
    * `escalation_level(waiting_days)`: `0` up to 3 business days of waiting, `1` from 4 to 7, `2` from 8.
    * `payment_date(approved_on, holidays=())`: claims are paid on Fridays: take the date 2 business days after
      `approved_on`, move to the first Friday on or after it; when that Friday is not a business day, pay on the last
      business day before it.

    ## Claims (`claimflow/claims.py`)

    `required_approvals(amount)`: 1 approver up to and including 50000 cents, 2 up to and including 200000, otherwise 3.

    `Claim(claim_id, owner, amount)` (a non-positive amount is a `ValueError`) starts in state `"draft"` with
    `submitted_on`, `approved_on` of `None`, an empty `approvers` list and an empty `reason`. Every method below raises
    `ValueError` when it is not allowed in the current state:

    * `submit(on)`: only from `draft`; the state becomes `submitted` and `submitted_on` is set.
    * `approve(by, on)`: only from `submitted`. The owner cannot approve their own claim, nobody can approve twice
      (`ValueError`). The approver is appended to `approvers`; once there are `required_approvals(amount)` approvers the
      state becomes `approved` and `approved_on` is set to `on`.
    * `reject(by, on, reason)`: only from `submitted`. The owner cannot reject their own claim and the reason must not be
      blank (`ValueError`). The state becomes `rejected`, `reason` holds the stripped reason and `approvers` is emptied.
    * `withdraw()`: from `draft` or `submitted`; the state becomes `withdrawn` and `approvers` is emptied.
    * `reopen()`: only from `rejected`; back to `draft` with `submitted_on` `None`, no approvers and an empty reason.
    * `waiting_days(today, holidays=())`: for a `submitted` claim the business days since `submitted_on`
      (`business_days_between`), otherwise `0`.
    * `escalation(today, holidays=())`: `escalation_level` of `waiting_days`.
''')

CF_SLA = dd('''
    from datetime import timedelta

    ESCALATE_AFTER = (3, 7)


    def is_business_day(d, holidays=()):
        return d.weekday() < 5 and d not in holidays


    def business_days_between(start, end, holidays=()):
        count = 0
        d = start + timedelta(days=1)
        while d <= end:
            if is_business_day(d, holidays):
                count += 1
            d += timedelta(days=1)
        return count


    def add_business_days(d, n, holidays=()):
        for _ in range(n):
            d += timedelta(days=1)
            while not is_business_day(d, holidays):
                d += timedelta(days=1)
        return d


    def escalation_level(waiting_days):
        if waiting_days <= ESCALATE_AFTER[0]:
            return 0
        if waiting_days <= ESCALATE_AFTER[1]:
            return 1
        return 2


    def payment_date(approved_on, holidays=()):
        d = add_business_days(approved_on, 2, holidays)
        d += timedelta(days=(4 - d.weekday()) % 7)
        while not is_business_day(d, holidays):
            d -= timedelta(days=1)
        return d
''')

CF_CLAIMS = dd('''
    from .sla import business_days_between, escalation_level

    LIMITS = ((50_000, 1), (200_000, 2))


    def required_approvals(amount):
        for limit, needed in LIMITS:
            if amount <= limit:
                return needed
        return 3


    class Claim:
        def __init__(self, claim_id, owner, amount):
            if amount <= 0:
                raise ValueError("amount must be positive")
            self.claim_id = claim_id
            self.owner = owner
            self.amount = amount
            self.state = "draft"
            self.submitted_on = None
            self.approved_on = None
            self.approvers = []
            self.reason = ""

        def _need(self, *states):
            if self.state not in states:
                raise ValueError(f"not possible while the claim is {self.state!r}")

        def submit(self, on):
            self._need("draft")
            self.state = "submitted"
            self.submitted_on = on

        def approve(self, by, on):
            self._need("submitted")
            if by == self.owner:
                raise ValueError("nobody approves their own claim")
            if by in self.approvers:
                raise ValueError("this person has already approved")
            self.approvers.append(by)
            if len(self.approvers) >= required_approvals(self.amount):
                self.state = "approved"
                self.approved_on = on

        def reject(self, by, on, reason):
            self._need("submitted")
            if by == self.owner:
                raise ValueError("nobody rejects their own claim")
            if not reason.strip():
                raise ValueError("a reason is required")
            self.state = "rejected"
            self.reason = reason.strip()
            self.approvers = []

        def withdraw(self):
            self._need("draft", "submitted")
            self.state = "withdrawn"
            self.approvers = []

        def reopen(self):
            self._need("rejected")
            self.state = "draft"
            self.submitted_on = None
            self.approvers = []
            self.reason = ""

        def waiting_days(self, today, holidays=()):
            if self.state != "submitted":
                return 0
            return business_days_between(self.submitted_on, today, holidays)

        def escalation(self, today, holidays=()):
            return escalation_level(self.waiting_days(today, holidays))
''')

CF_VISIBLE = dd('''
    import unittest
    from datetime import date

    from claimflow.claims import Claim, required_approvals
    from claimflow.sla import escalation_level


    class BasicTests(unittest.TestCase):
        def test_levels(self):
            self.assertEqual(escalation_level(8), 2)

        def test_small_claim_needs_one_approver(self):
            self.assertEqual(required_approvals(20_000), 1)

        def test_submit(self):
            c = Claim("c1", "ann", 30_000)
            c.submit(date(2025, 3, 3))
            self.assertEqual(c.state, "submitted")


    if __name__ == "__main__":
        unittest.main()
''')

CF_HIDDEN = dd('''
    import unittest
    from datetime import date

    from claimflow.claims import Claim, required_approvals
    from claimflow.sla import add_business_days, business_days_between, escalation_level, payment_date

    D = date
    HOL = {D(2025, 3, 17)}  # a Monday


    class Calendar(unittest.TestCase):
        def test_between(self):
            fri = D(2025, 3, 7)
            table = {D(2025, 3, 7): 0, D(2025, 3, 8): 0, D(2025, 3, 10): 1, D(2025, 3, 14): 5, D(2025, 3, 17): 5, D(2025, 3, 18): 6,
                     D(2025, 3, 3): 0}
            for end, days in table.items():
                self.assertEqual(business_days_between(fri, end, HOL), days, end)
            self.assertEqual(business_days_between(fri, D(2025, 3, 17)), 6)
            self.assertEqual(business_days_between(fri, D(2025, 3, 18)), 7)

        def test_start_day_is_excluded_end_day_included(self):
            self.assertEqual(business_days_between(D(2025, 3, 10), D(2025, 3, 11)), 1)
            self.assertEqual(business_days_between(D(2025, 3, 9), D(2025, 3, 10)), 1)
            self.assertEqual(business_days_between(D(2025, 3, 8), D(2025, 3, 9)), 0)

        def test_add(self):
            fri = D(2025, 3, 7)
            want = [D(2025, 3, 7), D(2025, 3, 10), D(2025, 3, 11), D(2025, 3, 12), D(2025, 3, 13), D(2025, 3, 14), D(2025, 3, 18), D(2025, 3, 19)]
            self.assertEqual([add_business_days(fri, n, HOL) for n in range(8)], want)
            self.assertEqual(add_business_days(fri, 6), D(2025, 3, 17))
            self.assertEqual(add_business_days(D(2025, 3, 8), 0), D(2025, 3, 8))
            self.assertEqual(add_business_days(D(2025, 3, 8), 1), D(2025, 3, 10))
            self.assertEqual(add_business_days(D(2025, 3, 16), 1, HOL), D(2025, 3, 18))

        def test_escalation_levels(self):
            table = {0: 0, 1: 0, 3: 0, 4: 1, 7: 1, 8: 2, 20: 2}
            for waiting, level in table.items():
                self.assertEqual(escalation_level(waiting), level, waiting)

        def test_payment_dates(self):
            table = {D(2025, 3, 3): D(2025, 3, 7), D(2025, 3, 4): D(2025, 3, 7), D(2025, 3, 5): D(2025, 3, 7), D(2025, 3, 6): D(2025, 3, 14),
                     D(2025, 3, 7): D(2025, 3, 14), D(2025, 3, 8): D(2025, 3, 14), D(2025, 3, 10): D(2025, 3, 14),
                     D(2025, 3, 12): D(2025, 3, 14), D(2025, 3, 13): D(2025, 3, 21)}
            for approved, paid in table.items():
                self.assertEqual(payment_date(approved), paid, approved)

        def test_payment_on_a_holiday_friday(self):
            friday_off = {D(2025, 3, 14)}
            self.assertEqual(payment_date(D(2025, 3, 6), friday_off), D(2025, 3, 13))
            self.assertEqual(payment_date(D(2025, 3, 10), friday_off), D(2025, 3, 13))
            self.assertEqual(payment_date(D(2025, 3, 6), {D(2025, 3, 13), D(2025, 3, 14)}), D(2025, 3, 12))
            self.assertEqual(payment_date(D(2025, 3, 3), friday_off), D(2025, 3, 7))
            self.assertEqual(payment_date(D(2025, 3, 12), friday_off), D(2025, 3, 21))


    class Approvals(unittest.TestCase):
        def test_thresholds(self):
            self.assertEqual([required_approvals(a) for a in (1, 50_000, 50_001, 200_000, 200_001, 10_000_000)], [1, 1, 2, 2, 3, 3])

        def test_amount_must_be_positive(self):
            for amount in (0, -1):
                with self.assertRaises(ValueError):
                    Claim("c", "ann", amount)


    class Workflow(unittest.TestCase):
        def claim(self, amount=30_000):
            c = Claim("c1", "ann", amount)
            c.submit(D(2025, 3, 3))
            return c

        def test_new_claim(self):
            c = Claim("c1", "ann", 30_000)
            self.assertEqual((c.state, c.submitted_on, c.approved_on, c.approvers, c.reason), ("draft", None, None, [], ""))
            self.assertEqual((c.claim_id, c.owner, c.amount), ("c1", "ann", 30_000))

        def test_submit(self):
            c = self.claim()
            self.assertEqual((c.state, c.submitted_on), ("submitted", D(2025, 3, 3)))

        def test_small_claim_is_approved_by_one(self):
            c = self.claim()
            c.approve("bob", D(2025, 3, 5))
            self.assertEqual((c.state, c.approved_on, c.approvers), ("approved", D(2025, 3, 5), ["bob"]))

        def test_big_claim_needs_two_different_people(self):
            c = self.claim(80_000)
            c.approve("bob", D(2025, 3, 4))
            self.assertEqual((c.state, c.approved_on), ("submitted", None))
            with self.assertRaises(ValueError):
                c.approve("bob", D(2025, 3, 5))
            c.approve("cy", D(2025, 3, 6))
            self.assertEqual((c.state, c.approved_on, c.approvers), ("approved", D(2025, 3, 6), ["bob", "cy"]))

        def test_huge_claim_needs_three(self):
            c = self.claim(250_000)
            for who in ("bob", "cy"):
                c.approve(who, D(2025, 3, 4))
                self.assertEqual(c.state, "submitted")
            c.approve("di", D(2025, 3, 5))
            self.assertEqual(c.state, "approved")

        def test_owner_cannot_decide(self):
            c = self.claim()
            with self.assertRaises(ValueError):
                c.approve("ann", D(2025, 3, 4))
            with self.assertRaises(ValueError):
                c.reject("ann", D(2025, 3, 4), "no")
            self.assertEqual(c.state, "submitted")
            self.assertEqual(c.approvers, [])

        def test_reject(self):
            c = self.claim(80_000)
            c.approve("bob", D(2025, 3, 4))
            with self.assertRaises(ValueError):
                c.reject("cy", D(2025, 3, 5), "   ")
            with self.assertRaises(ValueError):
                c.reject("cy", D(2025, 3, 5), "")
            self.assertEqual(c.state, "submitted")
            c.reject("cy", D(2025, 3, 5), "  missing receipt ")
            self.assertEqual((c.state, c.reason, c.approvers), ("rejected", "missing receipt", []))

        def test_reopen(self):
            c = self.claim()
            c.reject("bob", D(2025, 3, 4), "missing receipt")
            c.reopen()
            self.assertEqual((c.state, c.submitted_on, c.reason, c.approvers), ("draft", None, "", []))
            c.submit(D(2025, 3, 10))
            self.assertEqual((c.state, c.submitted_on), ("submitted", D(2025, 3, 10)))

        def test_withdraw(self):
            c = Claim("c1", "ann", 30_000)
            c.withdraw()
            self.assertEqual(c.state, "withdrawn")
            c = self.claim(80_000)
            c.approve("bob", D(2025, 3, 4))
            c.withdraw()
            self.assertEqual((c.state, c.approvers), ("withdrawn", []))

        def test_forbidden_transitions(self):
            draft = Claim("c1", "ann", 30_000)
            for call in (lambda: draft.approve("bob", D(2025, 3, 4)), lambda: draft.reject("bob", D(2025, 3, 4), "no"), draft.reopen):
                with self.assertRaises(ValueError):
                    call()
            approved = self.claim()
            approved.approve("bob", D(2025, 3, 4))
            for call in (lambda: approved.submit(D(2025, 3, 5)), lambda: approved.approve("cy", D(2025, 3, 5)),
                         lambda: approved.reject("cy", D(2025, 3, 5), "no"), approved.withdraw, approved.reopen):
                with self.assertRaises(ValueError):
                    call()
            self.assertEqual(approved.state, "approved")
            done = self.claim()
            done.withdraw()
            for call in (lambda: done.submit(D(2025, 3, 5)), done.withdraw, done.reopen, lambda: done.approve("bob", D(2025, 3, 5))):
                with self.assertRaises(ValueError):
                    call()
            rejected = self.claim()
            rejected.reject("bob", D(2025, 3, 4), "no")
            for call in (lambda: rejected.submit(D(2025, 3, 5)), rejected.withdraw, lambda: rejected.approve("cy", D(2025, 3, 5))):
                with self.assertRaises(ValueError):
                    call()
            submitted = self.claim()
            with self.assertRaises(ValueError):
                submitted.submit(D(2025, 3, 6))
            with self.assertRaises(ValueError):
                submitted.reopen()


    class Waiting(unittest.TestCase):
        def claim(self):
            c = Claim("c1", "ann", 30_000)
            c.submit(D(2025, 3, 3))
            return c

        def test_waiting_days(self):
            c = self.claim()
            self.assertEqual(c.waiting_days(D(2025, 3, 3)), 0)
            self.assertEqual(c.waiting_days(D(2025, 3, 7)), 4)
            self.assertEqual(c.waiting_days(D(2025, 3, 10)), 5)
            self.assertEqual(c.waiting_days(D(2025, 3, 18), HOL), 10)
            self.assertEqual(c.waiting_days(D(2025, 3, 18)), 11)

        def test_escalation_levels(self):
            c = self.claim()
            days = (6, 7, 10, 12, 13, 14, 17, 18, 19)
            self.assertEqual([c.escalation(D(2025, 3, d)) for d in days], [0, 1, 1, 1, 2, 2, 2, 2, 2])
            self.assertEqual([c.escalation(D(2025, 3, d), HOL) for d in days], [0, 1, 1, 1, 2, 2, 2, 2, 2])
            self.assertEqual(c.escalation(D(2025, 3, 12), {D(2025, 3, 10)}), 1)
            self.assertEqual(c.escalation(D(2025, 3, 13), {D(2025, 3, 10)}), 1)
            self.assertEqual(c.escalation(D(2025, 3, 14), {D(2025, 3, 10)}), 2)

        def test_only_submitted_claims_wait(self):
            draft = Claim("c1", "ann", 30_000)
            self.assertEqual(draft.waiting_days(D(2025, 6, 1)), 0)
            self.assertEqual(draft.escalation(D(2025, 6, 1)), 0)
            c = self.claim()
            c.approve("bob", D(2025, 3, 5))
            self.assertEqual(c.waiting_days(D(2025, 6, 1)), 0)
            self.assertEqual(c.escalation(D(2025, 6, 1)), 0)
            r = self.claim()
            r.reject("bob", D(2025, 3, 5), "no")
            self.assertEqual(r.escalation(D(2025, 6, 1)), 0)


    if __name__ == "__main__":
        unittest.main()
''')

CLAIMFLOW = Lib(
    name="claimflow", lang="python", title="the expense-claim workflow (`claimflow/`)",
    blurb="The finance team's expense tool routes claims through approval, escalates slow ones and sets payment dates with claimflow.",
    files={"claimflow/__init__.py": "", "claimflow/sla.py": CF_SLA, "claimflow/claims.py": CF_CLAIMS, "README.md": CF_README,
           ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": CF_VISIBLE},
    hidden_tests={"tests/test_full.py": CF_HIDDEN},
    mutate=["claimflow/sla.py", "claimflow/claims.py"], difficulty=3, tags=["workflow", "approvals", "business-days"],
    probes=[
        "business_days_between(date(2025, 3, 7), date(2025, 3, 17), {date(2025, 3, 17)})", "add_business_days(date(2025, 3, 7), 6, {date(2025, 3, 17)})",
        "escalation_level(3)", "escalation_level(4)", "escalation_level(7)", "escalation_level(8)", "payment_date(date(2025, 3, 5))",
        "payment_date(date(2025, 3, 6))", "payment_date(date(2025, 3, 6), {date(2025, 3, 14)})", "payment_date(date(2025, 3, 13))",
        "required_approvals(50_000)", "required_approvals(50_001)", "required_approvals(200_001)",
    ],
    probe_import="from datetime import date\nfrom claimflow.sla import *\nfrom claimflow.claims import *",
)

register_libs([CLUBCAL, CLAIMFLOW], n=10)
