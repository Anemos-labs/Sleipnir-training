"""Calendar arithmetic: month ends, drifting renewals, half-open ranges, ISO weeks, leap days (python booking kit, go datekit)."""
from fx import dd, family, langs
from generators.fix._hand_kit import Base, Bug, tasks_from

# ------------------------------------------------------------------------------------------------------------------
# Base A (python): a booking and subscription calendar kit.
# ------------------------------------------------------------------------------------------------------------------

A_README = dd('''
    # calkit

    Date helpers of a booking and subscription service (`datetime.date` values, no time zones).

    * `add_months(d, n)`: `d` moved by `n` calendar months (negative goes back). If the day does not exist in the target month it is **clamped to the
      last day of that month** (31 Jan + 1 month is 28 or 29 Feb).
    * `renewal_dates(start, every_months, count)`: the next `count` renewals after `start`: the k-th is `add_months(start, k * every_months)`, always
      counted from `start` itself, so a subscription started on 31 Jan renews on the 31st again whenever the month has one.
    * `nights(checkin, checkout)`: number of nights of a stay; `ValueError` unless `checkout` is after `checkin`.
    * `overlaps(a, b)`: do two stays `(start, end)` share a night? Stays are half-open (`end` is the morning of departure), so back-to-back stays do **not**
      overlap and an empty stay (`start == end`) overlaps nothing.
    * `iso_week_label(d)`: `"<ISO year>-W<week>"` with a two-digit week, e.g. `2025-W01`; the ISO year can differ from the calendar year around New Year.
    * `business_days(start, end, holidays=())`: the number of Monday-to-Friday days in `[start, end)` that are not in `holidays` (a holiday on a weekend,
      or outside the range, changes nothing).
    * `age_on(birth, on)`: completed years on date `on`; someone born on 29 February has the birthday on 1 March in common years; `on` before `birth` is a `ValueError`.
''')

A_CAL = dd('''
    import calendar
    from datetime import date, timedelta


    def add_months(d, n):
        total = d.year * 12 + (d.month - 1) + n
        year, month0 = divmod(total, 12)
        month = month0 + 1
        day = min(d.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)


    def renewal_dates(start, every_months, count):
        return [add_months(start, every_months * k) for k in range(1, count + 1)]


    def nights(checkin, checkout):
        if checkout <= checkin:
            raise ValueError("checkout must be after checkin")
        return (checkout - checkin).days


    def overlaps(a, b):
        a0, a1 = a
        b0, b1 = b
        return a0 < a1 and b0 < b1 and a0 < b1 and b0 < a1


    def iso_week_label(d):
        year, week, _ = d.isocalendar()
        return f"{year}-W{week:02d}"


    def business_days(start, end, holidays=()):
        holiday_set = set(holidays)
        count = 0
        d = start
        while d < end:
            if d.weekday() < 5 and d not in holiday_set:
                count += 1
            d += timedelta(days=1)
        return count


    def age_on(birth, on):
        if on < birth:
            raise ValueError("date before birth")
        years = on.year - birth.year
        if (on.month, on.day) < (birth.month, birth.day):
            years -= 1
        return years
''')

A_VISIBLE = {
    "tests/test_cal.py": dd('''
        import unittest
        from datetime import date

        from calkit.cal import add_months, nights, overlaps


        class CalTests(unittest.TestCase):
            def test_add_months_simple(self):
                self.assertEqual(add_months(date(2025, 3, 15), 2), date(2025, 5, 15))

            def test_nights(self):
                self.assertEqual(nights(date(2025, 3, 1), date(2025, 3, 4)), 3)

            def test_overlap(self):
                self.assertTrue(overlaps((date(2025, 3, 1), date(2025, 3, 5)), (date(2025, 3, 3), date(2025, 3, 8))))


        if __name__ == "__main__":
            unittest.main()
    '''),
}

A_HIDDEN = {
    "tests/test_hidden_cal.py": dd('''
        import unittest
        from datetime import date

        from calkit.cal import add_months, age_on, business_days, iso_week_label, nights, overlaps, renewal_dates


        def D(y, m, d):
            return date(y, m, d)


        class Months(unittest.TestCase):
            def test_clamping(self):
                self.assertEqual(add_months(D(2023, 1, 31), 1), D(2023, 2, 28))
                self.assertEqual(add_months(D(2024, 1, 31), 1), D(2024, 2, 29))
                self.assertEqual(add_months(D(2025, 3, 31), 1), D(2025, 4, 30))
                self.assertEqual(add_months(D(2025, 5, 31), 1), D(2025, 6, 30))
                self.assertEqual(add_months(D(2024, 2, 29), 12), D(2025, 2, 28))
                self.assertEqual(add_months(D(2024, 2, 29), 48), D(2028, 2, 29))

            def test_negative_and_year_rollover(self):
                self.assertEqual(add_months(D(2024, 3, 31), -1), D(2024, 2, 29))
                self.assertEqual(add_months(D(2024, 3, 31), -13), D(2023, 2, 28))
                self.assertEqual(add_months(D(2025, 1, 15), -1), D(2024, 12, 15))
                self.assertEqual(add_months(D(2025, 11, 30), 3), D(2026, 2, 28))
                self.assertEqual(add_months(D(2025, 12, 31), 2), D(2026, 2, 28))
                self.assertEqual(add_months(D(2025, 6, 10), 0), D(2025, 6, 10))
                self.assertEqual(add_months(D(2025, 6, 10), 24), D(2027, 6, 10))

            def test_renewals_are_counted_from_the_start_date(self):
                self.assertEqual(renewal_dates(D(2024, 1, 31), 1, 4), [D(2024, 2, 29), D(2024, 3, 31), D(2024, 4, 30), D(2024, 5, 31)])
                self.assertEqual(renewal_dates(D(2025, 1, 30), 1, 3), [D(2025, 2, 28), D(2025, 3, 30), D(2025, 4, 30)])
                self.assertEqual(renewal_dates(D(2025, 8, 31), 3, 3), [D(2025, 11, 30), D(2026, 2, 28), D(2026, 5, 31)])
                self.assertEqual(renewal_dates(D(2025, 1, 15), 12, 2), [D(2026, 1, 15), D(2027, 1, 15)])
                self.assertEqual(renewal_dates(D(2025, 1, 15), 1, 0), [])


        class Stays(unittest.TestCase):
            def test_nights(self):
                self.assertEqual(nights(D(2025, 2, 27), D(2025, 3, 2)), 3)
                self.assertEqual(nights(D(2024, 2, 27), D(2024, 3, 2)), 4)
                self.assertEqual(nights(D(2025, 12, 31), D(2026, 1, 1)), 1)
                for a, b in ((D(2025, 3, 1), D(2025, 3, 1)), (D(2025, 3, 2), D(2025, 3, 1))):
                    with self.assertRaises(ValueError):
                        nights(a, b)

            def test_back_to_back_stays_do_not_overlap(self):
                self.assertFalse(overlaps((D(2025, 3, 1), D(2025, 3, 5)), (D(2025, 3, 5), D(2025, 3, 9))))
                self.assertFalse(overlaps((D(2025, 3, 5), D(2025, 3, 9)), (D(2025, 3, 1), D(2025, 3, 5))))

            def test_overlapping_stays(self):
                a = (D(2025, 3, 1), D(2025, 3, 5))
                for b in ((D(2025, 3, 4), D(2025, 3, 9)), (D(2025, 2, 25), D(2025, 3, 2)), (D(2025, 3, 2), D(2025, 3, 3)), (D(2025, 2, 1), D(2025, 4, 1)), a):
                    self.assertTrue(overlaps(a, b), b)
                    self.assertTrue(overlaps(b, a), b)

            def test_disjoint_stays(self):
                self.assertFalse(overlaps((D(2025, 3, 1), D(2025, 3, 5)), (D(2025, 3, 6), D(2025, 3, 9))))
                self.assertFalse(overlaps((D(2025, 3, 1), D(2025, 3, 5)), (D(2025, 1, 1), D(2025, 2, 1))))

            def test_empty_stays_overlap_nothing(self):
                self.assertFalse(overlaps((D(2025, 3, 3), D(2025, 3, 3)), (D(2025, 3, 1), D(2025, 3, 5))))
                self.assertFalse(overlaps((D(2025, 3, 1), D(2025, 3, 5)), (D(2025, 3, 5), D(2025, 3, 5))))


        class Weeks(unittest.TestCase):
            def test_iso_labels(self):
                cases = {D(2025, 1, 1): "2025-W01", D(2024, 12, 30): "2025-W01", D(2024, 12, 29): "2024-W52", D(2021, 1, 3): "2020-W53",
                         D(2026, 1, 1): "2026-W01", D(2025, 3, 5): "2025-W10", D(2025, 12, 31): "2026-W01", D(2020, 12, 31): "2020-W53"}
                for d, want in cases.items():
                    self.assertEqual(iso_week_label(d), want, d)

            def test_business_days(self):
                self.assertEqual(business_days(D(2025, 3, 3), D(2025, 3, 10)), 5)
                self.assertEqual(business_days(D(2025, 3, 3), D(2025, 3, 3)), 0)
                self.assertEqual(business_days(D(2025, 3, 1), D(2025, 3, 3)), 0)
                self.assertEqual(business_days(D(2025, 3, 3), D(2025, 3, 4)), 1)
                self.assertEqual(business_days(D(2025, 3, 1), D(2025, 4, 1)), 21)

            def test_holidays(self):
                hol = [D(2025, 3, 5)]
                self.assertEqual(business_days(D(2025, 3, 3), D(2025, 3, 10), hol), 4)
                self.assertEqual(business_days(D(2025, 3, 3), D(2025, 3, 10), [D(2025, 3, 8), D(2025, 3, 9)]), 5)
                self.assertEqual(business_days(D(2025, 3, 3), D(2025, 3, 10), [D(2024, 12, 25), D(2026, 1, 1)]), 5)
                self.assertEqual(business_days(D(2025, 3, 3), D(2025, 3, 10), [D(2025, 3, 5), D(2025, 3, 5), D(2025, 3, 6)]), 3)
                self.assertEqual(business_days(D(2025, 3, 3), D(2025, 3, 10), [D(2025, 3, 10)]), 5)


        class Ages(unittest.TestCase):
            def test_ordinary_birthdays(self):
                self.assertEqual(age_on(D(2000, 6, 15), D(2025, 6, 14)), 24)
                self.assertEqual(age_on(D(2000, 6, 15), D(2025, 6, 15)), 25)
                self.assertEqual(age_on(D(2000, 6, 15), D(2025, 12, 31)), 25)
                self.assertEqual(age_on(D(2025, 1, 1), D(2025, 1, 1)), 0)

            def test_leap_day_births(self):
                born = D(2000, 2, 29)
                self.assertEqual(age_on(born, D(2025, 2, 28)), 24)
                self.assertEqual(age_on(born, D(2025, 3, 1)), 25)
                self.assertEqual(age_on(born, D(2024, 2, 29)), 24)
                self.assertEqual(age_on(born, D(2023, 3, 1)), 23)

            def test_before_birth(self):
                with self.assertRaises(ValueError):
                    age_on(D(2000, 1, 1), D(1999, 12, 31))


        if __name__ == "__main__":
            unittest.main()
    '''),
}


def _a_prompts():
    p = {}
    p["clamp"] = lambda c: (
        "The monthly billing run crashed on the 31st of a long month with `ValueError: day is out of range for month` while moving a "
        "customer's billing date by one month:\n\n```\n"
        + c.bad_run("from datetime import date\nfrom calkit.cal import add_months\nadd_months(date(2025, 1, 31), 1)\n").splitlines()[-1]
        + "\n```\n\nThe README says the day is clamped to the last day of the target month."
    )
    p["drift"] = (
        "Subscriptions that start at the end of a month drift: a customer who started on 31 January is billed on the 29th of February (fine) and then on "
        "the 29th of March, April, May... instead of going back to the 31st. Each renewal date must be computed from the original start date."
    )
    p["overlap"] = (
        "The booking engine refuses a guest who arrives on the day another guest leaves (check-in 5 March, previous check-out 5 March). Stays are half-open: "
        "the departure morning does not occupy the room that night."
    )
    p["iso"] = (
        "The weekly report is labelled `2024-W01` for 30 December 2024, which is a week we already used in January 2024. The week label must use the ISO "
        "year that goes with the week number (that day is in `2025-W01`)."
    )
    p["bd-end"] = (
        "The delivery estimate counts one working day too many: from Monday to the next Monday we say 6 working days, but it is 5. The end date is the day "
        "of arrival, which is not counted (ranges are half-open, as everywhere else in the calendar kit)."
    )
    p["holidays"] = (
        "Business-day counts come out too low in months with holidays that fall on a weekend or outside the period: every date in the holiday list is "
        "subtracted, even a Saturday, even a date in another year. Only weekday holidays inside the range should reduce the count (and a date listed twice counts once)."
    )
    p["leap-age"] = (
        "The age check crashes for customers born on 29 February whenever the check date is in a common year (`ValueError: day is out of range for month`). "
        "They should turn a year older on 1 March."
    )
    return p


def _base_a() -> Base:
    P = _a_prompts()
    good = {"README.md": A_README, "calkit/__init__.py": '"""Booking calendar helpers."""\n', "calkit/cal.py": A_CAL}
    c = "calkit/cal.py"
    bugs = [
        Bug("overlap-counts-touching-stays", 1, {c: [("    return a0 < a1 and b0 < b1 and a0 < b1 and b0 < a1\n", "    return a0 < a1 and b0 < b1 and a0 <= b1 and b0 <= a1\n")]}, P["overlap"]),
        Bug("business-days-include-the-end-date", 2, {c: [("    while d < end:\n", "    while d <= end:\n")]}, P["bd-end"]),
        Bug("day-not-clamped-to-the-month", 3, {c: [("    day = min(d.day, calendar.monthrange(year, month)[1])\n", "    day = d.day\n")]}, P["clamp"]),
        Bug("renewals-chained-from-the-previous-one", 3, {c: [("    return [add_months(start, every_months * k) for k in range(1, count + 1)]\n",
                                                               "    out = []\n    current = start\n    for _ in range(count):\n        current = add_months(current, every_months)\n        out.append(current)\n    return out\n")]}, P["drift"]),
        Bug("iso-week-with-the-calendar-year", 3, {c: [("    year, week, _ = d.isocalendar()\n", "    _, week, _ = d.isocalendar()\n    year = d.year\n")]}, P["iso"]),
        Bug("every-holiday-is-subtracted", 3, {c: [("        if d.weekday() < 5 and d not in holiday_set:\n            count += 1\n", "        if d.weekday() < 5:\n            count += 1\n"),
                                                    ("    return count\n\n\ndef age_on", "    return count - len(list(holidays))\n\n\ndef age_on")]}, P["holidays"]),
        Bug("leap-day-birthday-built-with-replace", 3, {c: [("    years = on.year - birth.year\n    if (on.month, on.day) < (birth.month, birth.day):\n        years -= 1\n    return years\n",
                                                             "    birthday = birth.replace(year=on.year)\n    return on.year - birth.year - (1 if on < birthday else 0)\n")]}, P["leap-age"]),
    ]
    return Base("calkit", "python", good, A_VISIBLE, A_HIDDEN, bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base B (go): date helpers.
# ------------------------------------------------------------------------------------------------------------------

B_README = dd('''
    # datekit

    Calendar helpers on `time.Time` (Go; locations are respected, no UTC conversion unless stated).

    * `AddMonths(t, n)`: `t` moved by `n` months (negative goes back); a day that does not exist in the target month is clamped to the last day of it
      (31 Jan + 1 month = 28 or 29 Feb, never March). The time of day and the location are kept.
    * `DaysIn(year, month)`: number of days of the month, leap years included.
    * `DaysBetween(a, b)`: calendar days from the date of `a` to the date of `b`, each date read in its own location; times of day are ignored; negative if `b`
      is earlier. (11 pm and 1 am the next day are 1 day apart.)
    * `StartOfWeek(t, weekStart)`: midnight, in `t`'s location, of the latest `weekStart` day on or before `t`.
    * `Quarter(t)`: the quarter of the year, 1 to 4.
''')

B_DATEKIT = dd('''
    package datekit

    import "time"

    // DaysIn is the number of days of a month.
    func DaysIn(year int, m time.Month) int {
    	return time.Date(year, m+1, 0, 0, 0, 0, 0, time.UTC).Day()
    }

    // AddMonths adds n months, clamping the day to the end of the target month.
    func AddMonths(t time.Time, n int) time.Time {
    	y, m, d := t.Date()
    	total := y*12 + int(m) - 1 + n
    	ty, tm := total/12, time.Month(total%12+1)
    	if last := DaysIn(ty, tm); d > last {
    		d = last
    	}
    	return time.Date(ty, tm, d, t.Hour(), t.Minute(), t.Second(), t.Nanosecond(), t.Location())
    }

    // DaysBetween counts calendar days between the dates of a and b.
    func DaysBetween(a, b time.Time) int {
    	ay, am, ad := a.Date()
    	by, bm, bd := b.Date()
    	da := time.Date(ay, am, ad, 0, 0, 0, 0, time.UTC)
    	db := time.Date(by, bm, bd, 0, 0, 0, 0, time.UTC)
    	return int(db.Sub(da).Hours() / 24)
    }

    // StartOfWeek is midnight of the latest weekStart day on or before t.
    func StartOfWeek(t time.Time, weekStart time.Weekday) time.Time {
    	back := (int(t.Weekday()) - int(weekStart) + 7) % 7
    	y, m, d := t.Date()
    	return time.Date(y, m, d-back, 0, 0, 0, 0, t.Location())
    }

    // Quarter is the quarter of the year, 1 to 4.
    func Quarter(t time.Time) int {
    	return (int(t.Month())-1)/3 + 1
    }
''')

B_VISIBLE = {
    "datekit_test.go": dd('''
        package datekit

        import (
        	"testing"
        	"time"
        )

        func TestSimple(t *testing.T) {
        	d := time.Date(2025, 3, 15, 10, 0, 0, 0, time.UTC)
        	if got := AddMonths(d, 2); got.Month() != time.May || got.Day() != 15 {
        		t.Fatalf("got %v", got)
        	}
        	if Quarter(d) != 1 || DaysIn(2025, time.April) != 30 {
        		t.Fatal("quarter or days")
        	}
        }
    '''),
}


def _b_hidden() -> dict:
    return {"datekit_hidden_test.go": dd('''
        package datekit

        import (
        	"testing"
        	"time"
        )

        func date(y int, m time.Month, d int) time.Time { return time.Date(y, m, d, 0, 0, 0, 0, time.UTC) }

        func TestAddMonthsClamps(t *testing.T) {
        	cases := []struct {
        		from time.Time
        		n    int
        		want time.Time
        	}{
        		{date(2023, 1, 31), 1, date(2023, 2, 28)},
        		{date(2024, 1, 31), 1, date(2024, 2, 29)},
        		{date(2025, 3, 31), 1, date(2025, 4, 30)},
        		{date(2024, 2, 29), 12, date(2025, 2, 28)},
        		{date(2024, 2, 29), 48, date(2028, 2, 29)},
        		{date(2024, 3, 31), -1, date(2024, 2, 29)},
        		{date(2024, 3, 31), -13, date(2023, 2, 28)},
        		{date(2025, 1, 15), -1, date(2024, 12, 15)},
        		{date(2025, 12, 31), 2, date(2026, 2, 28)},
        		{date(2025, 6, 10), 0, date(2025, 6, 10)},
        		{date(2025, 10, 31), 4, date(2026, 2, 28)},
        	}
        	for _, c := range cases {
        		if got := AddMonths(c.from, c.n); !got.Equal(c.want) {
        			t.Errorf("AddMonths(%s, %d) = %s, want %s", c.from.Format("2006-01-02"), c.n, got.Format("2006-01-02"), c.want.Format("2006-01-02"))
        		}
        	}
        }

        func TestAddMonthsKeepsTimeAndLocation(t *testing.T) {
        	zone := time.FixedZone("x", 5*3600)
        	in := time.Date(2025, 1, 31, 23, 59, 58, 999, zone)
        	got := AddMonths(in, 1)
        	want := time.Date(2025, 2, 28, 23, 59, 58, 999, zone)
        	if !got.Equal(want) || got.Location() != zone || got.Nanosecond() != 999 {
        		t.Fatalf("got %v, want %v", got, want)
        	}
        }

        func TestDaysIn(t *testing.T) {
        	cases := map[[2]int]int{{2024, 2}: 29, {2023, 2}: 28, {1900, 2}: 28, {2000, 2}: 29, {2025, 4}: 30, {2025, 12}: 31, {2025, 1}: 31, {2100, 2}: 28}
        	for k, want := range cases {
        		if got := DaysIn(k[0], time.Month(k[1])); got != want {
        			t.Errorf("DaysIn(%d, %d) = %d, want %d", k[0], k[1], got, want)
        		}
        	}
        }

        func TestDaysBetween(t *testing.T) {
        	at := func(y int, m time.Month, d, h, min int) time.Time { return time.Date(y, m, d, h, min, 0, 0, time.UTC) }
        	cases := []struct {
        		a, b time.Time
        		want int
        	}{
        		{at(2025, 3, 1, 23, 0), at(2025, 3, 2, 1, 0), 1},
        		{at(2025, 3, 1, 9, 0), at(2025, 3, 1, 17, 0), 0},
        		{at(2025, 3, 2, 1, 0), at(2025, 3, 1, 23, 0), -1},
        		{at(2024, 2, 28, 12, 0), at(2024, 3, 1, 12, 0), 2},
        		{at(2025, 12, 31, 23, 59), at(2026, 1, 1, 0, 1), 1},
        		{at(2025, 1, 1, 0, 0), at(2025, 12, 31, 23, 59), 364},
        		{at(2025, 3, 1, 0, 0), at(2025, 3, 8, 0, 0), 7},
        	}
        	for _, c := range cases {
        		if got := DaysBetween(c.a, c.b); got != c.want {
        			t.Errorf("DaysBetween(%s, %s) = %d, want %d", c.a.Format(time.RFC3339), c.b.Format(time.RFC3339), got, c.want)
        		}
        	}
        	east := time.FixedZone("east", 5*3600)
        	west := time.FixedZone("west", -8*3600)
        	a := time.Date(2025, 3, 1, 23, 30, 0, 0, east)
        	b := time.Date(2025, 3, 2, 0, 10, 0, 0, west)
        	if got := DaysBetween(a, b); got != 1 {
        		t.Errorf("dates in their own locations: got %d, want 1", got)
        	}
        }

        func TestStartOfWeek(t *testing.T) {
        	cases := []struct {
        		t     time.Time
        		start time.Weekday
        		want  time.Time
        	}{
        		{time.Date(2025, 3, 5, 15, 30, 0, 0, time.UTC), time.Monday, date(2025, 3, 3)},
        		{time.Date(2025, 3, 9, 8, 0, 0, 0, time.UTC), time.Monday, date(2025, 3, 3)},
        		{time.Date(2025, 3, 3, 23, 59, 0, 0, time.UTC), time.Monday, date(2025, 3, 3)},
        		{time.Date(2025, 3, 5, 15, 30, 0, 0, time.UTC), time.Sunday, date(2025, 3, 2)},
        		{time.Date(2025, 3, 9, 8, 0, 0, 0, time.UTC), time.Sunday, date(2025, 3, 9)},
        		{time.Date(2025, 3, 1, 12, 0, 0, 0, time.UTC), time.Monday, date(2025, 2, 24)},
        		{time.Date(2025, 3, 7, 12, 0, 0, 0, time.UTC), time.Saturday, date(2025, 3, 1)},
        		{time.Date(2025, 3, 8, 12, 0, 0, 0, time.UTC), time.Saturday, date(2025, 3, 8)},
        		{time.Date(2025, 1, 1, 12, 0, 0, 0, time.UTC), time.Monday, date(2024, 12, 30)},
        	}
        	for _, c := range cases {
        		if got := StartOfWeek(c.t, c.start); !got.Equal(c.want) {
        			t.Errorf("StartOfWeek(%s, %v) = %s, want %s", c.t.Format("2006-01-02 Mon"), c.start, got.Format("2006-01-02 Mon"), c.want.Format("2006-01-02 Mon"))
        		}
        	}
        	zone := time.FixedZone("x", 3*3600)
        	got := StartOfWeek(time.Date(2025, 3, 5, 15, 30, 0, 0, zone), time.Monday)
        	if got.Location() != zone || got.Hour() != 0 || got.Day() != 3 {
        		t.Errorf("location or midnight lost: %v", got)
        	}
        }

        func TestQuarter(t *testing.T) {
        	want := []int{1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4}
        	for m := 1; m <= 12; m++ {
        		if got := Quarter(date(2025, time.Month(m), 15)); got != want[m-1] {
        			t.Errorf("Quarter(month %d) = %d, want %d", m, got, want[m-1])
        		}
        	}
        }
    ''')}


def _b_prompts():
    p = {}
    p["normalises"] = (
        "Adding a month to 31 January gives 3 March (2 March in a leap year) in our billing dates: the day overflows into the next month instead "
        "of stopping at the end of February."
    )
    p["days-between"] = (
        "\"Days since last visit\" says 0 for a customer who visited at 11 pm and came back at 1 am the next day, and the nightly report counts "
        "one day too few whenever the times of day are not equal. Calendar days, not 24-hour blocks."
    )
    p["week"] = (
        "Weekly statistics for Sundays land in the *next* week: with weeks starting on Monday, Sunday 9 March is attributed to the week starting "
        "Monday 10 March (in the future) instead of 3 March."
    )
    p["quarter"] = (
        "Revenue for the last month of every quarter (March, June, September, December) is reported in the next quarter. Other months are right."
    )
    p["leap"] = (
        "February never has 29 days in our scheduling library, so appointments on 29 February are rejected as invalid, while the standard library "
        "accepts them. `DaysIn` should handle leap years."
    )
    return p


def _base_b() -> Base:
    P = _b_prompts()
    good = {"README.md": B_README, "go.mod": langs.go_mod("datekit"), "datekit.go": B_DATEKIT}
    f = "datekit.go"
    bugs = [
        Bug("quarter-from-month-over-three", 1, {f: [("\treturn (int(t.Month())-1)/3 + 1\n", "\treturn int(t.Month())/3 + 1\n")]}, P["quarter"]),
        Bug("days-in-ignores-leap-years", 1, {f: [("\treturn time.Date(year, m+1, 0, 0, 0, 0, 0, time.UTC).Day()\n", "\treturn []int{31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31}[m-1]\n")]}, P["leap"]),
        Bug("add-months-overflows-into-the-next-month", 3, {f: [("\ty, m, d := t.Date()\n\ttotal := y*12 + int(m) - 1 + n\n\tty, tm := total/12, time.Month(total%12+1)\n\tif last := DaysIn(ty, tm); d > last {\n\t\td = last\n\t}\n\treturn time.Date(ty, tm, d, t.Hour(), t.Minute(), t.Second(), t.Nanosecond(), t.Location())\n",
                                                               "\treturn t.AddDate(0, n, 0)\n")]}, P["normalises"]),
        Bug("days-between-truncates-24-hour-blocks", 3, {f: [("\tay, am, ad := a.Date()\n\tby, bm, bd := b.Date()\n\tda := time.Date(ay, am, ad, 0, 0, 0, 0, time.UTC)\n\tdb := time.Date(by, bm, bd, 0, 0, 0, 0, time.UTC)\n\treturn int(db.Sub(da).Hours() / 24)\n", "\treturn int(b.Sub(a).Hours() / 24)\n")]}, P["days-between"]),
        Bug("week-start-goes-forward-on-sundays", 2, {f: [("\tback := (int(t.Weekday()) - int(weekStart) + 7) % 7\n", "\tback := int(t.Weekday()) - int(weekStart)\n")]}, P["week"]),
    ]
    return Base("datekit", "go", good, B_VISIBLE, _b_hidden(), bugs)


@family("fix-hand-date-ranges", category="fix", lang="python", kind="fix", n=12,
        summary="calendar arithmetic: month ends, drifting renewals, half-open ranges, ISO weeks, leap days (python, go)")
def gen(rng, n):
    return tasks_from([_base_a(), _base_b()])
