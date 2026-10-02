"""Python libraries, theme time/money/scheduling (batch sched-b): meeting-room bookings, dose schedules, court
deadlines, a small cron-like scheduler, booking quotas."""
from fx import Lib, dd, register_libs

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# roomclash: meeting-room bookings with cleaning buffers, capacity and slot search
# ======================================================================================================================

RC_README = dd('''
    # roomclash

    Meeting-room booking for an office. Times are whole minutes on one absolute time line (minute `0` is midnight of
    day 0, so day `d` starts at `d * 1440`).

    A booking is `Booking(room, start, end, owner, people)`. Rooms and their capacities: `Aurora` 8, `Birch` 4,
    `Cedar` 12.

    * `validate(booking)`: `ValueError` for an unknown room, `end <= start`, a booking that does not stay inside one
      day (`start // 1440 != (end - 1) // 1440`), fewer than 1 person or more people than the room holds.
    * `gap_needed(a, b)`: the cleaning gap the room needs between two meetings: 10 minutes, but `0` when both have the
      same owner.
    * `clashes(a, b)`: true when both are in the same room and the later one (ordered by `(start, end)`) starts before
      the earlier one ends **plus** the gap needed. Touching with enough gap is fine.
    * `find_conflicts(bookings)`: after validating every booking, the sorted list of index pairs `(i, j)`, `i < j`, of
      bookings that clash.
    * `find_slot(bookings, room, people, duration, earliest, latest_end, owner, step=15)`: the earliest start that is
      a multiple of `step` (counted from midnight of day 0), at least `earliest`, such that the new booking would stay
      inside one day, end at or before `latest_end` and clash with none of `bookings`. Candidates that would cross
      midnight are skipped (the search continues at the next midnight). `None` when nothing fits. A room that is too
      small for `people` is a `ValueError`.
    * `suggest_room(bookings, people, start, end, owner)`: the free room with the smallest capacity that holds
      `people` (ties by name), or `None`. An invalid time range is a `ValueError`.
    * `busy_minutes(bookings, room, lo, hi)`: the minutes of `[lo, hi)` in which the room is booked; overlapping
      bookings are not counted twice; other rooms are ignored.
''')

RC_SRC = dd('''
    from collections import namedtuple

    Booking = namedtuple("Booking", "room start end owner people")

    CAPACITY = {"Aurora": 8, "Birch": 4, "Cedar": 12}
    BUFFER = 10
    DAY = 1440


    def validate(b):
        if b.room not in CAPACITY:
            raise ValueError(f"unknown room {b.room!r}")
        if b.end <= b.start:
            raise ValueError("a booking must end after it starts")
        if b.start // DAY != (b.end - 1) // DAY:
            raise ValueError("a booking must stay inside one day")
        if not 1 <= b.people <= CAPACITY[b.room]:
            raise ValueError("number of people does not fit the room")


    def gap_needed(a, b):
        return 0 if a.owner == b.owner else BUFFER


    def clashes(a, b):
        if a.room != b.room:
            return False
        first, second = (a, b) if (a.start, a.end) <= (b.start, b.end) else (b, a)
        return second.start < first.end + gap_needed(first, second)


    def find_conflicts(bookings):
        for b in bookings:
            validate(b)
        pairs = []
        for i in range(len(bookings)):
            for j in range(i + 1, len(bookings)):
                if clashes(bookings[i], bookings[j]):
                    pairs.append((i, j))
        return pairs


    def find_slot(bookings, room, people, duration, earliest, latest_end, owner, step=15):
        validate(Booking(room, 0, duration, owner, people))
        start = -(-earliest // step) * step
        while start + duration <= latest_end:
            if start // DAY != (start + duration - 1) // DAY:
                start = (start // DAY + 1) * DAY
                continue
            candidate = Booking(room, start, start + duration, owner, people)
            if not any(clashes(candidate, b) for b in bookings):
                return start
            start += step
        return None


    def suggest_room(bookings, people, start, end, owner):
        for room in sorted(CAPACITY, key=lambda r: (CAPACITY[r], r)):
            if CAPACITY[room] < people:
                continue
            candidate = Booking(room, start, end, owner, people)
            validate(candidate)
            if not any(clashes(candidate, b) for b in bookings):
                return room
        return None


    def busy_minutes(bookings, room, lo, hi):
        spans = sorted((max(b.start, lo), min(b.end, hi)) for b in bookings if b.room == room)
        total = 0
        reach = lo
        for start, end in spans:
            if end <= start:
                continue
            start = max(start, reach)
            if end > start:
                total += end - start
                reach = end
        return total
''')

RC_VISIBLE = dd('''
    import unittest

    from roomclash.rooms import Booking, clashes, find_conflicts


    class BasicTests(unittest.TestCase):
        def test_overlap(self):
            a = Booking("Aurora", 600, 660, "ann", 4)
            b = Booking("Aurora", 630, 700, "bob", 4)
            self.assertTrue(clashes(a, b))

        def test_other_room(self):
            a = Booking("Aurora", 600, 660, "ann", 4)
            b = Booking("Birch", 600, 660, "bob", 2)
            self.assertEqual(find_conflicts([a, b]), [])


    if __name__ == "__main__":
        unittest.main()
''')

RC_HIDDEN = dd('''
    import unittest

    from roomclash.rooms import Booking, busy_minutes, clashes, find_conflicts, find_slot, gap_needed, suggest_room, validate

    B = Booking


    class Validate(unittest.TestCase):
        def test_ok(self):
            validate(B("Aurora", 600, 660, "ann", 4))
            validate(B("Aurora", 1380, 1440, "ann", 8))
            validate(B("Birch", 1440, 1441, "ann", 1))
            validate(B("Cedar", 600, 660, "ann", 12))

        def test_errors(self):
            bad = [B("Atrium", 600, 660, "a", 2), B("Aurora", 660, 660, "a", 2), B("Aurora", 660, 600, "a", 2),
                   B("Aurora", 1400, 1500, "a", 2), B("Aurora", 1439, 1441, "a", 2), B("Aurora", 600, 660, "a", 0),
                   B("Birch", 600, 660, "a", 5), B("Aurora", 600, 660, "a", 9), B("Cedar", 600, 660, "a", 13),
                   B("Aurora", 600, 660, "a", -1)]
            for b in bad:
                with self.assertRaises(ValueError, msg=b):
                    validate(b)


    class Clashes(unittest.TestCase):
        def test_buffer_between_owners(self):
            a = B("Aurora", 600, 660, "ann", 4)
            self.assertFalse(clashes(a, B("Aurora", 670, 700, "bob", 4)))
            self.assertTrue(clashes(a, B("Aurora", 669, 700, "bob", 4)))
            self.assertTrue(clashes(B("Aurora", 669, 700, "bob", 4), a))

        def test_same_owner_needs_no_buffer(self):
            a = B("Aurora", 600, 660, "ann", 4)
            self.assertFalse(clashes(a, B("Aurora", 660, 700, "ann", 4)))
            self.assertTrue(clashes(a, B("Aurora", 659, 700, "ann", 4)))

        def test_later_booking_given_first(self):
            later = B("Aurora", 700, 760, "bob", 4)
            earlier = B("Aurora", 600, 695, "ann", 4)
            self.assertTrue(clashes(later, earlier))
            self.assertTrue(clashes(earlier, later))
            self.assertFalse(clashes(later, B("Aurora", 600, 690, "ann", 4)))

        def test_other_rooms_never_clash(self):
            self.assertFalse(clashes(B("Aurora", 600, 660, "a", 2), B("Birch", 600, 660, "b", 2)))

        def test_nested_and_equal_starts(self):
            self.assertTrue(clashes(B("Aurora", 600, 720, "a", 2), B("Aurora", 620, 640, "b", 2)))
            self.assertTrue(clashes(B("Aurora", 620, 640, "b", 2), B("Aurora", 600, 720, "a", 2)))
            self.assertTrue(clashes(B("Aurora", 600, 630, "a", 2), B("Aurora", 600, 700, "b", 2)))
            self.assertTrue(clashes(B("Aurora", 600, 700, "a", 2), B("Aurora", 600, 630, "a", 2)))

        def test_gap(self):
            self.assertEqual(gap_needed(B("A", 0, 1, "ann", 1), B("A", 0, 1, "bob", 1)), 10)
            self.assertEqual(gap_needed(B("A", 0, 1, "ann", 1), B("A", 0, 1, "ann", 1)), 0)


    class Conflicts(unittest.TestCase):
        def test_pairs(self):
            bookings = [B("Aurora", 600, 660, "ann", 4), B("Aurora", 665, 700, "bob", 4), B("Birch", 600, 660, "ann", 2),
                        B("Aurora", 700, 720, "ann", 4)]
            self.assertEqual(find_conflicts(bookings), [(0, 1), (1, 3)])

        def test_none(self):
            self.assertEqual(find_conflicts([]), [])
            self.assertEqual(find_conflicts([B("Aurora", 600, 660, "a", 1)]), [])

        def test_all_pairs_are_found_in_order(self):
            bookings = [B("Cedar", 600, 700, "a", 2), B("Cedar", 650, 750, "b", 2), B("Cedar", 690, 800, "c", 2)]
            self.assertEqual(find_conflicts(bookings), [(0, 1), (0, 2), (1, 2)])

        def test_validates(self):
            with self.assertRaises(ValueError):
                find_conflicts([B("Aurora", 600, 660, "a", 1), B("Nowhere", 600, 660, "a", 1)])


    class Slot(unittest.TestCase):
        BOOKED = [B("Aurora", 600, 660, "ann", 4), B("Aurora", 700, 760, "bob", 4)]

        def test_earliest_free_slot(self):
            self.assertEqual(find_slot(self.BOOKED, "Aurora", 4, 30, 600, 900, "cy"), 780)
            self.assertEqual(find_slot(self.BOOKED, "Aurora", 4, 30, 0, 900, "cy"), 0)
            self.assertEqual(find_slot(self.BOOKED, "Aurora", 4, 30, 400, 900, "cy"), 405)

        def test_grid_alignment(self):
            self.assertEqual(find_slot([], "Aurora", 4, 30, 601, 900, "cy"), 615)
            self.assertEqual(find_slot([], "Aurora", 4, 30, 600, 900, "cy"), 600)
            self.assertEqual(find_slot([], "Aurora", 4, 30, 601, 900, "cy", step=30), 630)
            self.assertEqual(find_slot([], "Aurora", 4, 30, 601, 900, "cy", step=1), 601)

        def test_same_owner_squeezes_in(self):
            self.assertEqual(find_slot(self.BOOKED, "Aurora", 4, 20, 600, 900, "bob"), 675)
            self.assertEqual(find_slot(self.BOOKED, "Aurora", 4, 20, 600, 900, "cy"), 780)

        def test_latest_end(self):
            self.assertEqual(find_slot(self.BOOKED, "Aurora", 4, 30, 600, 810, "cy"), 780)
            self.assertIsNone(find_slot(self.BOOKED, "Aurora", 4, 30, 600, 809, "cy"))
            self.assertIsNone(find_slot(self.BOOKED, "Aurora", 4, 30, 600, 800, "cy"))

        def test_other_rooms_are_ignored(self):
            self.assertEqual(find_slot(self.BOOKED, "Birch", 2, 30, 600, 900, "cy"), 600)

        def test_midnight_is_skipped(self):
            self.assertEqual(find_slot([], "Aurora", 2, 60, 1400, 3000, "x"), 1440)
            self.assertEqual(find_slot([], "Aurora", 2, 30, 1410, 3000, "x"), 1410)
            self.assertEqual(find_slot([], "Aurora", 2, 31, 1410, 3000, "x"), 1440)

        def test_full_room(self):
            full = [B("Cedar", 0, 600, "a", 2), B("Cedar", 600, 1200, "a", 2)]
            self.assertIsNone(find_slot(full, "Cedar", 2, 30, 0, 1000, "a"))
            self.assertEqual(find_slot(full, "Cedar", 2, 30, 0, 1300, "a"), 1200)
            self.assertEqual(find_slot(full, "Cedar", 2, 30, 0, 1300, "b"), 1215)

        def test_capacity_error(self):
            with self.assertRaises(ValueError):
                find_slot([], "Birch", 5, 30, 600, 900, "cy")
            with self.assertRaises(ValueError):
                find_slot([], "Atrium", 1, 30, 600, 900, "cy")
            with self.assertRaises(ValueError):
                find_slot([], "Birch", 2, 0, 600, 900, "cy")


    class Suggest(unittest.TestCase):
        BOOKED = [B("Birch", 600, 660, "ann", 4)]

        def test_smallest_free_room(self):
            self.assertEqual(suggest_room(self.BOOKED, 3, 700, 760, "bob"), "Birch")
            self.assertEqual(suggest_room(self.BOOKED, 3, 600, 660, "bob"), "Aurora")
            self.assertEqual(suggest_room(self.BOOKED, 3, 665, 700, "bob"), "Aurora")
            self.assertEqual(suggest_room(self.BOOKED, 3, 670, 700, "bob"), "Birch")
            self.assertEqual(suggest_room(self.BOOKED, 3, 660, 700, "ann"), "Birch")

        def test_size_requirements(self):
            self.assertEqual(suggest_room([], 1, 600, 660, "x"), "Birch")
            self.assertEqual(suggest_room([], 4, 600, 660, "x"), "Birch")
            self.assertEqual(suggest_room([], 5, 600, 660, "x"), "Aurora")
            self.assertEqual(suggest_room([], 8, 600, 660, "x"), "Aurora")
            self.assertEqual(suggest_room([], 9, 600, 660, "x"), "Cedar")
            self.assertIsNone(suggest_room([], 13, 600, 660, "x"))

        def test_everything_taken(self):
            booked = [B("Birch", 600, 660, "a", 1), B("Aurora", 600, 660, "a", 1), B("Cedar", 600, 660, "a", 1)]
            self.assertIsNone(suggest_room(booked, 2, 620, 640, "b"))
            self.assertEqual(suggest_room(booked, 9, 620, 640, "b"), None)

        def test_bad_range(self):
            with self.assertRaises(ValueError):
                suggest_room([], 2, 660, 660, "x")
            with self.assertRaises(ValueError):
                suggest_room([], 2, 1400, 1500, "x")


    class Busy(unittest.TestCase):
        def test_union(self):
            bookings = [B("Aurora", 600, 660, "a", 1), B("Aurora", 640, 700, "b", 1), B("Aurora", 720, 780, "c", 1), B("Birch", 0, 1000, "d", 1)]
            self.assertEqual(busy_minutes(bookings, "Aurora", 0, 1440), 160)
            self.assertEqual(busy_minutes(bookings, "Aurora", 650, 740), 70)
            self.assertEqual(busy_minutes(bookings, "Birch", 0, 1440), 1000)
            self.assertEqual(busy_minutes(bookings, "Cedar", 0, 1440), 0)

        def test_nested_and_touching(self):
            bookings = [B("Aurora", 600, 800, "a", 1), B("Aurora", 650, 700, "b", 1), B("Aurora", 800, 900, "c", 1)]
            self.assertEqual(busy_minutes(bookings, "Aurora", 0, 1440), 300)

        def test_clipping(self):
            bookings = [B("Aurora", 600, 660, "a", 1)]
            self.assertEqual(busy_minutes(bookings, "Aurora", 630, 1000), 30)
            self.assertEqual(busy_minutes(bookings, "Aurora", 0, 630), 30)
            self.assertEqual(busy_minutes(bookings, "Aurora", 660, 700), 0)
            self.assertEqual(busy_minutes(bookings, "Aurora", 0, 600), 0)
            self.assertEqual(busy_minutes(bookings, "Aurora", 620, 640), 20)

        def test_empty_ranges(self):
            bookings = [B("Aurora", 600, 660, "a", 1)]
            self.assertEqual(busy_minutes(bookings, "Aurora", 700, 650), 0)
            self.assertEqual(busy_minutes(bookings, "Aurora", 630, 630), 0)
            self.assertEqual(busy_minutes([], "Aurora", 0, 1440), 0)

        def test_order_of_the_input(self):
            bookings = [B("Aurora", 720, 780, "c", 1), B("Aurora", 640, 700, "b", 1), B("Aurora", 600, 660, "a", 1)]
            self.assertEqual(busy_minutes(bookings, "Aurora", 0, 1440), 160)


    if __name__ == "__main__":
        unittest.main()
''')

ROOMCLASH = Lib(
    name="roomclash", lang="python", title="the meeting-room booking checks (`roomclash/rooms.py`)",
    blurb="The office booking tool detects clashes, finds free slots and suggests rooms with the roomclash module.",
    files={"roomclash/__init__.py": "", "roomclash/rooms.py": RC_SRC, "README.md": RC_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": RC_VISIBLE},
    hidden_tests={"tests/test_full.py": RC_HIDDEN},
    mutate=["roomclash/rooms.py"], difficulty=3, tags=["rooms", "bookings", "intervals"],
    probes=[
        "clashes(Booking('Aurora', 600, 660, 'ann', 4), Booking('Aurora', 669, 700, 'bob', 4))",
        "clashes(Booking('Aurora', 600, 660, 'ann', 4), Booking('Aurora', 670, 700, 'bob', 4))",
        "clashes(Booking('Aurora', 600, 660, 'ann', 4), Booking('Aurora', 660, 700, 'ann', 4))",
        "find_conflicts([Booking('Aurora', 600, 660, 'ann', 4), Booking('Aurora', 665, 700, 'bob', 4), Booking('Aurora', 700, 720, 'ann', 4)])",
        "find_slot([Booking('Aurora', 600, 660, 'ann', 4), Booking('Aurora', 700, 760, 'bob', 4)], 'Aurora', 4, 30, 600, 900, 'cy')",
        "find_slot([Booking('Aurora', 600, 660, 'ann', 4), Booking('Aurora', 700, 760, 'bob', 4)], 'Aurora', 4, 20, 600, 900, 'bob')",
        "find_slot([], 'Aurora', 2, 60, 1400, 3000, 'x')", "find_slot([], 'Aurora', 4, 30, 601, 900, 'cy')",
        "suggest_room([Booking('Birch', 600, 660, 'ann', 4)], 3, 665, 700, 'bob')", "suggest_room([], 9, 600, 660, 'x')",
        "busy_minutes([Booking('Aurora', 600, 660, 'a', 1), Booking('Aurora', 640, 700, 'b', 1), Booking('Aurora', 720, 780, 'c', 1)], 'Aurora', 0, 1440)",
    ],
    probe_import="from roomclash.rooms import *",
)

# ======================================================================================================================
# dosetimes: medication schedule inside waking hours with a minimum gap, and adherence
# ======================================================================================================================

DT_README = dd('''
    # dosetimes

    Medication reminders for a care app. Times are whole minutes on one absolute time line (minute `0` is midnight of
    day 0; day `d` starts at `d * 1440`).

    * `clamp_to_wake(t, wake)`: `wake` is `(first, last)` minutes of the day. A time before `first` on its day moves to
      `first`, a time after `last` moves to `last` (same day); a time inside the window is unchanged.
    * `dose_times(first, interval_hours, doses, wake=(420, 1320))`: `doses` times. Dose `i` is nominally at
      `first + i * interval_hours * 60`; it is moved into the waking window with `clamp_to_wake`; if that leaves it
      less than 240 minutes after the previous dose it is moved to exactly 240 minutes after the previous dose (even
      if that is outside the window). `interval_hours <= 0` or `doses < 0` is a `ValueError`.
    * `next_dose(last_taken, interval_hours, now)`: the earliest time that is not before `now` and at least
      `interval_hours` after the last dose taken.
    * `match_doses(schedule, taken)`: for each scheduled time (in the order given) whether a taken time covers it: the
      earliest still unused taken time (taking `taken` sorted) within 60 minutes either way (60 included). One taken
      time covers at most one dose. Returns a list of booleans.
    * `adherence_percent(schedule, taken)`: covered doses as a whole percent, rounded down; `100` for an empty schedule.
''')

DT_SRC = dd('''
    DAY = 1440
    MIN_GAP = 240
    TOLERANCE = 60


    def clamp_to_wake(t, wake):
        day, minute = divmod(t, DAY)
        return day * DAY + min(max(minute, wake[0]), wake[1])


    def dose_times(first, interval_hours, doses, wake=(420, 1320)):
        if interval_hours <= 0 or doses < 0:
            raise ValueError("interval must be positive and doses not negative")
        times = []
        for i in range(doses):
            actual = clamp_to_wake(first + i * interval_hours * 60, wake)
            if times and actual < times[-1] + MIN_GAP:
                actual = times[-1] + MIN_GAP
            times.append(actual)
        return times


    def next_dose(last_taken, interval_hours, now):
        return max(now, last_taken + interval_hours * 60)


    def match_doses(schedule, taken):
        pool = sorted(taken)
        used = set()
        covered = []
        for when in schedule:
            hit = None
            for k, t in enumerate(pool):
                if k not in used and abs(t - when) <= TOLERANCE:
                    hit = k
                    break
            if hit is not None:
                used.add(hit)
            covered.append(hit is not None)
        return covered


    def adherence_percent(schedule, taken):
        if not schedule:
            return 100
        return sum(match_doses(schedule, taken)) * 100 // len(schedule)
''')

DT_VISIBLE = dd('''
    import unittest

    from dosetimes.schedule import clamp_to_wake, dose_times


    class BasicTests(unittest.TestCase):
        def test_clamp_early(self):
            self.assertEqual(clamp_to_wake(1440, (420, 1320)), 1860)

        def test_plain_schedule(self):
            self.assertEqual(dose_times(480, 12, 3), [480, 1200, 1920])


    if __name__ == "__main__":
        unittest.main()
''')

DT_HIDDEN = dd('''
    import unittest

    from dosetimes.schedule import adherence_percent, clamp_to_wake, dose_times, match_doses, next_dose

    WAKE = (420, 1320)


    class Clamp(unittest.TestCase):
        def test_values(self):
            table = {0: 420, 419: 420, 420: 420, 800: 800, 1320: 1320, 1321: 1320, 1439: 1320, 1440: 1860, 1440 + 500: 1940,
                     2 * 1440 + 1400: 2 * 1440 + 1320}
            for t, want in table.items():
                self.assertEqual(clamp_to_wake(t, WAKE), want, t)

        def test_other_window(self):
            self.assertEqual(clamp_to_wake(100, (0, 1439)), 100)
            self.assertEqual(clamp_to_wake(1500, (600, 900)), 1440 + 600)
            self.assertEqual(clamp_to_wake(1300, (600, 900)), 900)


    class Times(unittest.TestCase):
        def test_inside_the_window(self):
            self.assertEqual(dose_times(480, 12, 4), [480, 1200, 1920, 2640])
            self.assertEqual(dose_times(480, 8, 2), [480, 960])

        def test_moved_into_the_window(self):
            self.assertEqual(dose_times(480, 8, 4), [480, 960, 1860, 2100])
            self.assertEqual(dose_times(360, 6, 5), [420, 720, 1080, 1860, 2100])

        def test_late_evening(self):
            self.assertEqual(dose_times(1380, 24, 2), [1320, 1440 + 1320])

        def test_minimum_gap(self):
            self.assertEqual(dose_times(600, 3, 3), [600, 840, 1080])
            self.assertEqual(dose_times(600, 2, 3), [600, 840, 1080])
            self.assertEqual(dose_times(1200, 2, 2), [1200, 1440])

        def test_gap_can_leave_the_window(self):
            got = dose_times(1200, 1, 3)
            self.assertEqual(got, [1200, 1440, 1680])

        def test_exact_gap_is_enough(self):
            self.assertEqual(dose_times(600, 4, 3), [600, 840, 1080])
            self.assertEqual(dose_times(480, 4, 3), [480, 720, 960])

        def test_counts_and_errors(self):
            self.assertEqual(dose_times(480, 8, 0), [])
            self.assertEqual(dose_times(480, 8, 1), [480])
            for interval, doses in ((0, 3), (-8, 3), (8, -1)):
                with self.assertRaises(ValueError):
                    dose_times(480, interval, doses)

        def test_custom_window(self):
            self.assertEqual(dose_times(300, 12, 3, wake=(360, 1200)), [360, 1020, 1800])


    class Next(unittest.TestCase):
        def test_values(self):
            self.assertEqual(next_dose(480, 8, 900), 960)
            self.assertEqual(next_dose(480, 8, 1000), 1000)
            self.assertEqual(next_dose(480, 8, 960), 960)
            self.assertEqual(next_dose(480, 8, 0), 960)
            self.assertEqual(next_dose(480, 4, 700), 720)


    class Matching(unittest.TestCase):
        def test_basic(self):
            self.assertEqual(match_doses([480, 960, 1440], [470, 1000, 3000]), [True, True, False])
            self.assertEqual(match_doses([], [1, 2]), [])
            self.assertEqual(match_doses([480], []), [False])

        def test_tolerance_is_sixty_inclusive(self):
            for taken, covered in ((540, True), (541, False), (420, True), (419, False), (480, True)):
                self.assertEqual(match_doses([480], [taken]), [covered], taken)

        def test_a_taken_time_covers_one_dose(self):
            self.assertEqual(match_doses([480, 500], [490]), [True, False])
            self.assertEqual(match_doses([480, 500], [490, 495]), [True, True])
            self.assertEqual(match_doses([480, 500], [495, 490]), [True, True])

        def test_earliest_unused_time_is_taken(self):
            # 430 and 520 both cover 480; the earlier 430 is used, which leaves 520 for the dose at 560
            self.assertEqual(match_doses([480, 560], [520, 430]), [True, True])
            self.assertEqual(match_doses([480, 600], [520, 430]), [True, False])

        def test_schedule_order(self):
            self.assertEqual(match_doses([500, 480], [490]), [True, False])

        def test_input_is_not_modified(self):
            taken = [520, 430]
            match_doses([480], taken)
            self.assertEqual(taken, [520, 430])


    class Adherence(unittest.TestCase):
        def test_values(self):
            self.assertEqual(adherence_percent([480, 960, 1440], [470, 1000, 3000]), 66)
            self.assertEqual(adherence_percent([480, 960], [480, 960]), 100)
            self.assertEqual(adherence_percent([480, 960], []), 0)
            self.assertEqual(adherence_percent([480, 960, 1440, 1920], [480, 1440, 1920]), 75)
            self.assertEqual(adherence_percent([1, 2, 3, 4, 5, 6, 7], [1, 2, 3, 4, 5, 6]), 85)

        def test_empty_schedule(self):
            self.assertEqual(adherence_percent([], []), 100)
            self.assertEqual(adherence_percent([], [5, 6]), 100)


    if __name__ == "__main__":
        unittest.main()
''')

DOSETIMES = Lib(
    name="dosetimes", lang="python", title="the medication schedule helpers (`dosetimes/schedule.py`)",
    blurb="The care app plans medication reminders inside waking hours and scores adherence with dosetimes.",
    files={"dosetimes/__init__.py": "", "dosetimes/schedule.py": DT_SRC, "README.md": DT_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": DT_VISIBLE},
    hidden_tests={"tests/test_full.py": DT_HIDDEN},
    mutate=["dosetimes/schedule.py"], difficulty=2, tags=["medication", "schedule", "windows"],
    probes=[
        "clamp_to_wake(1440, (420, 1320))", "clamp_to_wake(1321, (420, 1320))", "dose_times(480, 8, 4)", "dose_times(360, 6, 5)",
        "dose_times(1200, 1, 3)", "dose_times(480, 12, 4)", "next_dose(480, 8, 900)", "next_dose(480, 8, 1000)",
        "match_doses([480, 960, 1440], [470, 1000, 3000])", "match_doses([480, 500], [490])", "match_doses([480], [541])",
        "match_doses([480, 560], [520, 430])", "adherence_percent([480, 960, 1440], [470, 1000, 3000])", "adherence_percent([], [])",
    ],
    probe_import="from dosetimes.schedule import *",
)

# ======================================================================================================================
# courtdays: filing deadlines counted in calendar or open days
# ======================================================================================================================

CD_README = dd('''
    # courtdays

    Deadline arithmetic for a court registry. Dates are `datetime.date`. The registry is **open** Monday to Friday
    except on the given `holidays`.

    * `is_open(d, holidays=())` and `next_open(d, holidays=())`: whether the registry is open that day, and the first
      open day on or after `d`.
    * `add_open_days(d, n, holidays=())`: `n` open days after `d`; `d` itself is never counted and need not be open.
      `n == 0` gives `next_open(d, holidays)`.
    * `deadline(served, days, holidays=(), kind="calendar", clear=False, post=False)`: the last day to file after a
      document was served on `served`.
      - The length is `days`, plus 1 when `clear` (clear days: the day of service and the day of filing do not count),
        plus 2 when `post` (service by post).
      - For `kind="calendar"` the length is added as calendar days and, if the result is not an open day, the deadline
        moves on to the next open day. For `kind="business"` the length is counted in open days with `add_open_days`.
      - `days < 0` or any other `kind` is a `ValueError`.
    * `is_timely(deadline_date, filed_on, filed_minute, cutoff=1020)`: a filing on a day before the deadline is in
      time; on the deadline day only when `filed_minute <= cutoff` (minutes since midnight, 1020 is 17:00); after it,
      never.
    * `open_days_left(today, deadline_date, holidays=())`: the number of open days in `(today, deadline_date]`; `0` when
      the deadline is not after `today`.
''')

CD_SRC = dd('''
    from datetime import timedelta

    CLEAR_EXTRA = 1
    POST_EXTRA = 2


    def is_open(d, holidays=()):
        return d.weekday() < 5 and d not in holidays


    def next_open(d, holidays=()):
        while not is_open(d, holidays):
            d += timedelta(days=1)
        return d


    def add_open_days(d, n, holidays=()):
        if n == 0:
            return next_open(d, holidays)
        for _ in range(n):
            d = next_open(d + timedelta(days=1), holidays)
        return d


    def deadline(served, days, holidays=(), kind="calendar", clear=False, post=False):
        if days < 0:
            raise ValueError("days must not be negative")
        if kind not in ("calendar", "business"):
            raise ValueError(f"unknown kind {kind!r}")
        total = days + (CLEAR_EXTRA if clear else 0) + (POST_EXTRA if post else 0)
        if kind == "business":
            return add_open_days(served, total, holidays)
        return next_open(served + timedelta(days=total), holidays)


    def is_timely(deadline_date, filed_on, filed_minute, cutoff=1020):
        if filed_on < deadline_date:
            return True
        if filed_on == deadline_date:
            return filed_minute <= cutoff
        return False


    def open_days_left(today, deadline_date, holidays=()):
        count = 0
        d = today + timedelta(days=1)
        while d <= deadline_date:
            if is_open(d, holidays):
                count += 1
            d += timedelta(days=1)
        return count
''')

CD_VISIBLE = dd('''
    import unittest
    from datetime import date

    from courtdays.deadlines import deadline, is_open, next_open


    class BasicTests(unittest.TestCase):
        def test_weekend(self):
            self.assertFalse(is_open(date(2025, 3, 8)))

        def test_next_open(self):
            self.assertEqual(next_open(date(2025, 3, 8)), date(2025, 3, 10))

        def test_calendar_deadline(self):
            self.assertEqual(deadline(date(2025, 3, 7), 7), date(2025, 3, 14))


    if __name__ == "__main__":
        unittest.main()
''')

CD_HIDDEN = dd('''
    import unittest
    from datetime import date

    from courtdays.deadlines import add_open_days, deadline, is_open, is_timely, next_open, open_days_left

    D = date
    HOL = {D(2025, 3, 17)}  # a Monday


    class Open(unittest.TestCase):
        def test_is_open(self):
            self.assertTrue(is_open(D(2025, 3, 7)))
            self.assertTrue(is_open(D(2025, 3, 10)))
            self.assertFalse(is_open(D(2025, 3, 8)))
            self.assertFalse(is_open(D(2025, 3, 9)))
            self.assertTrue(is_open(D(2025, 3, 17)))
            self.assertFalse(is_open(D(2025, 3, 17), HOL))
            self.assertTrue(is_open(D(2025, 3, 18), HOL))

        def test_next_open(self):
            self.assertEqual(next_open(D(2025, 3, 7)), D(2025, 3, 7))
            self.assertEqual(next_open(D(2025, 3, 8)), D(2025, 3, 10))
            self.assertEqual(next_open(D(2025, 3, 9)), D(2025, 3, 10))
            self.assertEqual(next_open(D(2025, 3, 16), HOL), D(2025, 3, 18))
            self.assertEqual(next_open(D(2025, 3, 16), {D(2025, 3, 17), D(2025, 3, 18)}), D(2025, 3, 19))
            self.assertEqual(next_open(D(2025, 3, 14), {D(2025, 3, 14)}), D(2025, 3, 17))

        def test_add_open_days(self):
            fri = D(2025, 3, 7)
            self.assertEqual(add_open_days(fri, 1), D(2025, 3, 10))
            self.assertEqual(add_open_days(fri, 5), D(2025, 3, 14))
            self.assertEqual(add_open_days(fri, 6), D(2025, 3, 17))
            self.assertEqual(add_open_days(fri, 6, HOL), D(2025, 3, 18))
            self.assertEqual(add_open_days(fri, 0), fri)
            self.assertEqual(add_open_days(D(2025, 3, 8), 0), D(2025, 3, 10))
            self.assertEqual(add_open_days(D(2025, 3, 8), 1), D(2025, 3, 10))
            self.assertEqual(add_open_days(D(2025, 3, 8), 2), D(2025, 3, 11))
            self.assertEqual(add_open_days(D(2025, 3, 16), 1, HOL), D(2025, 3, 18))
            self.assertEqual(add_open_days(D(2025, 3, 16), 0, HOL), D(2025, 3, 18))


    class Deadline(unittest.TestCase):
        SERVED = D(2025, 3, 7)

        def test_calendar_days_roll_forward(self):
            table = {0: D(2025, 3, 7), 7: D(2025, 3, 14), 8: D(2025, 3, 18), 9: D(2025, 3, 18), 10: D(2025, 3, 18),
                     11: D(2025, 3, 18), 12: D(2025, 3, 19)}
            for days, want in table.items():
                self.assertEqual(deadline(self.SERVED, days, HOL), want, days)

        def test_without_holidays(self):
            self.assertEqual(deadline(self.SERVED, 8), D(2025, 3, 17))
            self.assertEqual(deadline(self.SERVED, 9), D(2025, 3, 17))
            self.assertEqual(deadline(self.SERVED, 10), D(2025, 3, 17))

        def test_clear_days(self):
            self.assertEqual(deadline(self.SERVED, 6, HOL, clear=True), D(2025, 3, 14))
            self.assertEqual(deadline(self.SERVED, 7, HOL, clear=True), D(2025, 3, 18))
            self.assertEqual(deadline(self.SERVED, 7, clear=True), D(2025, 3, 17))

        def test_service_by_post(self):
            self.assertEqual(deadline(self.SERVED, 5, HOL, post=True), D(2025, 3, 14))
            self.assertEqual(deadline(self.SERVED, 6, HOL, post=True), D(2025, 3, 18))

        def test_clear_and_post(self):
            self.assertEqual(deadline(self.SERVED, 4, HOL, clear=True, post=True), D(2025, 3, 14))
            self.assertEqual(deadline(self.SERVED, 5, HOL, clear=True, post=True), D(2025, 3, 18))
            self.assertEqual(deadline(self.SERVED, 2, kind="business", clear=True, post=True), D(2025, 3, 14))

        def test_business_days(self):
            table = {0: D(2025, 3, 7), 1: D(2025, 3, 10), 5: D(2025, 3, 14), 6: D(2025, 3, 18), 7: D(2025, 3, 19)}
            for days, want in table.items():
                self.assertEqual(deadline(self.SERVED, days, HOL, kind="business"), want, days)
            self.assertEqual(deadline(self.SERVED, 6, kind="business"), D(2025, 3, 17))

        def test_business_with_extras(self):
            self.assertEqual(deadline(self.SERVED, 5, HOL, kind="business", clear=True), D(2025, 3, 18))
            self.assertEqual(deadline(self.SERVED, 3, HOL, kind="business", post=True), D(2025, 3, 14))
            self.assertEqual(deadline(self.SERVED, 4, HOL, kind="business", post=True), D(2025, 3, 18))

        def test_served_on_a_weekend(self):
            sat = D(2025, 3, 8)
            self.assertEqual(deadline(sat, 2), D(2025, 3, 10))
            self.assertEqual(deadline(sat, 3), D(2025, 3, 11))
            self.assertEqual(deadline(sat, 1, kind="business"), D(2025, 3, 10))
            self.assertEqual(deadline(sat, 0, kind="business"), D(2025, 3, 10))

        def test_errors(self):
            with self.assertRaises(ValueError):
                deadline(self.SERVED, -1)
            with self.assertRaises(ValueError):
                deadline(self.SERVED, 5, kind="weekly")
            with self.assertRaises(ValueError):
                deadline(self.SERVED, 5, kind="")


    class Timely(unittest.TestCase):
        DL = D(2025, 3, 18)

        def test_before_on_after(self):
            self.assertTrue(is_timely(self.DL, D(2025, 3, 17), 1439))
            self.assertTrue(is_timely(self.DL, D(2025, 3, 1), 0))
            self.assertFalse(is_timely(self.DL, D(2025, 3, 19), 0))
            self.assertFalse(is_timely(self.DL, D(2025, 4, 1), 100))

        def test_cutoff_on_the_day(self):
            self.assertTrue(is_timely(self.DL, self.DL, 0))
            self.assertTrue(is_timely(self.DL, self.DL, 1020))
            self.assertFalse(is_timely(self.DL, self.DL, 1021))
            self.assertTrue(is_timely(self.DL, self.DL, 600, cutoff=600))
            self.assertFalse(is_timely(self.DL, self.DL, 601, cutoff=600))


    class Left(unittest.TestCase):
        def test_counts(self):
            self.assertEqual(open_days_left(D(2025, 3, 7), D(2025, 3, 18), HOL), 6)
            self.assertEqual(open_days_left(D(2025, 3, 7), D(2025, 3, 18)), 7)
            self.assertEqual(open_days_left(D(2025, 3, 17), D(2025, 3, 18), HOL), 1)
            self.assertEqual(open_days_left(D(2025, 3, 7), D(2025, 3, 8)), 0)
            self.assertEqual(open_days_left(D(2025, 3, 7), D(2025, 3, 10)), 1)

        def test_nothing_left(self):
            self.assertEqual(open_days_left(D(2025, 3, 18), D(2025, 3, 18)), 0)
            self.assertEqual(open_days_left(D(2025, 3, 19), D(2025, 3, 18)), 0)

        def test_today_is_not_counted_but_the_deadline_is(self):
            self.assertEqual(open_days_left(D(2025, 3, 10), D(2025, 3, 11)), 1)
            self.assertEqual(open_days_left(D(2025, 3, 10), D(2025, 3, 14)), 4)


    if __name__ == "__main__":
        unittest.main()
''')

COURTDAYS = Lib(
    name="courtdays", lang="python", title="the court filing-deadline calculator (`courtdays/deadlines.py`)",
    blurb="The court registry's case system computes filing deadlines and the days left with the courtdays module.",
    files={"courtdays/__init__.py": "", "courtdays/deadlines.py": CD_SRC, "README.md": CD_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": CD_VISIBLE},
    hidden_tests={"tests/test_full.py": CD_HIDDEN},
    mutate=["courtdays/deadlines.py"], difficulty=2, tags=["deadlines", "calendar", "legal"],
    probes=[
        "next_open(date(2025, 3, 16), {date(2025, 3, 17)})", "add_open_days(date(2025, 3, 7), 6, {date(2025, 3, 17)})",
        "add_open_days(date(2025, 3, 8), 0)", "deadline(date(2025, 3, 7), 8, {date(2025, 3, 17)})",
        "deadline(date(2025, 3, 7), 7, clear=True)", "deadline(date(2025, 3, 7), 6, post=True)",
        "deadline(date(2025, 3, 7), 4, clear=True, post=True)", "deadline(date(2025, 3, 7), 6, kind='business')",
        "deadline(date(2025, 3, 7), 5, {date(2025, 3, 17)}, kind='business', clear=True)", "deadline(date(2025, 3, 8), 3)",
        "is_timely(date(2025, 3, 18), date(2025, 3, 18), 1021)", "is_timely(date(2025, 3, 18), date(2025, 3, 18), 1020)",
        "open_days_left(date(2025, 3, 7), date(2025, 3, 18), {date(2025, 3, 17)})",
    ],
    probe_import="from datetime import date\nfrom courtdays.deadlines import *",
)

# ======================================================================================================================
# cronish: a small schedule language ("every 15m between 08:00-18:00 on weekdays") and its next fire time
# ======================================================================================================================

CN_README = dd('''
    # cronish

    A small job-schedule language for a task runner. Instants are naive `datetime` objects.

    ## Language (`cronish/parse.py`)

        schedule := times [" on " days]
        times    := "at " T (" and " T)*
                  | "every " N ("m" | "h") [" between " T "-" T]
        days     := "daily" | "weekdays" | "weekends" | "day " D ("," D)* | weekday ("," weekday)*

    The text is case-insensitive and any run of whitespace counts as one space; leading and trailing whitespace is
    ignored. Anything that does not fit is a `ValueError`. Without `on` the days are `daily`.

    * `T` is `HH:MM`, two digits each. As a time of day (after `at`, or the start of a window) it runs from `00:00` to
      `23:59`; the end of a `between` window may also be `24:00`. Minutes above 59 are invalid.
    * `at T and T`: those minutes of the day (duplicates merged, sorted).
    * `every N m` / `every N h`: a step of `N` minutes or `N` hours (`1 <= step <= 1440` minutes). The runs are the window
      start, start + step, ... **strictly before** the window end. Without `between` the window is `00:00-24:00`.
      The window end must be after its start.
    * `weekdays` is Monday to Friday, `weekends` Saturday and Sunday, a weekday list uses `mon tue wed thu fri sat sun`
      separated by commas (spaces after a comma are fine), `day 1,15` are days of the month (1 to 31). Months that
      lack a listed day simply have no run on it.

    `parse(text)` returns `Schedule(minutes, weekdays, monthdays)`: `minutes` a sorted tuple of minutes of the day,
    `weekdays` a frozenset of weekday numbers (Monday is 0) or `None`, `monthdays` a frozenset or `None`; `None` means
    "no restriction" (both are `None` for `daily`).

    ## Running (`cronish/fire.py`)

    * `matches_day(schedule, d)`: whether the date `d` is allowed by `weekdays` and `monthdays`.
    * `next_fire(schedule, after)`: the first run **strictly after** `after` (seconds count: 09:30:01 is after a 09:30
      run). It looks at most 800 days ahead and raises `ValueError` if nothing is found.
    * `fire_times(schedule, start, end)`: every run `t` with `start <= t < end`, in order.
''')

CN_PARSE = dd('''
    import re
    from collections import namedtuple

    Schedule = namedtuple("Schedule", "minutes weekdays monthdays")

    DOW = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    _TIME = re.compile(r"^(\\d\\d):(\\d\\d)$")
    _AT = re.compile(r"^at (\\d\\d:\\d\\d(?: and \\d\\d:\\d\\d)*)$")
    _EVERY = re.compile(r"^every (\\d+)(m|h)(?: between (\\d\\d:\\d\\d)-(\\d\\d:\\d\\d))?$")


    def parse_time(text, allow_24=False):
        m = _TIME.match(text)
        if not m:
            raise ValueError(f"bad time {text!r}")
        hours, minutes = int(m.group(1)), int(m.group(2))
        if minutes > 59 or hours > 24 or (hours == 24 and (minutes != 0 or not allow_24)):
            raise ValueError(f"bad time {text!r}")
        return hours * 60 + minutes


    def parse_days(text):
        if text == "daily":
            return None, None
        if text == "weekdays":
            return frozenset(range(5)), None
        if text == "weekends":
            return frozenset((5, 6)), None
        if text.startswith("day "):
            days = set()
            for part in text[4:].split(","):
                part = part.strip()
                if not part.isdigit() or not 1 <= int(part) <= 31:
                    raise ValueError(f"bad day of month {part!r}")
                days.add(int(part))
            return None, frozenset(days)
        names = [part.strip() for part in text.split(",")]
        if any(name not in DOW for name in names):
            raise ValueError(f"bad weekday list {text!r}")
        return frozenset(DOW.index(name) for name in names), None


    def parse(text):
        body = " ".join(text.lower().split())
        days_text = "daily"
        if " on " in body:
            body, _, days_text = body.partition(" on ")
        m = _AT.match(body)
        if m:
            minutes = sorted({parse_time(t) for t in m.group(1).split(" and ")})
        else:
            m = _EVERY.match(body)
            if not m:
                raise ValueError("cannot read the schedule")
            step = int(m.group(1)) * (1 if m.group(2) == "m" else 60)
            if not 1 <= step <= 1440:
                raise ValueError("step out of range")
            low, high = 0, 1440
            if m.group(3):
                low = parse_time(m.group(3))
                high = parse_time(m.group(4), allow_24=True)
                if high <= low:
                    raise ValueError("window must end after it starts")
            minutes = list(range(low, high, step))
        weekdays, monthdays = parse_days(days_text)
        return Schedule(tuple(minutes), weekdays, monthdays)
''')

CN_FIRE = dd('''
    from datetime import datetime, timedelta

    MAX_DAYS = 800


    def matches_day(schedule, d):
        if schedule.weekdays is not None and d.weekday() not in schedule.weekdays:
            return False
        return schedule.monthdays is None or d.day in schedule.monthdays


    def _runs(schedule, day):
        midnight = datetime(day.year, day.month, day.day)
        return [midnight + timedelta(minutes=m) for m in schedule.minutes]


    def next_fire(schedule, after):
        day = after.date()
        for _ in range(MAX_DAYS):
            if matches_day(schedule, day):
                for t in _runs(schedule, day):
                    if t > after:
                        return t
            day += timedelta(days=1)
        raise ValueError("the schedule never fires")


    def fire_times(schedule, start, end):
        found = []
        day = start.date()
        while day <= end.date():
            if matches_day(schedule, day):
                found.extend(t for t in _runs(schedule, day) if start <= t < end)
            day += timedelta(days=1)
        return found
''')

CN_VISIBLE = dd('''
    import unittest
    from datetime import datetime

    from cronish.fire import next_fire
    from cronish.parse import parse


    class BasicTests(unittest.TestCase):
        def test_parse_at(self):
            self.assertEqual(parse("at 09:30").minutes, (570,))

        def test_next_fire(self):
            s = parse("at 09:30 on weekdays")
            self.assertEqual(next_fire(s, datetime(2025, 3, 7, 10, 0)), datetime(2025, 3, 10, 9, 30))


    if __name__ == "__main__":
        unittest.main()
''')

CN_HIDDEN = dd('''
    import unittest
    from datetime import datetime

    from cronish.fire import fire_times, matches_day, next_fire
    from cronish.parse import Schedule, parse

    DT = datetime
    ALL = frozenset(range(7))


    class ParseTimes(unittest.TestCase):
        def test_at(self):
            self.assertEqual(parse("at 09:30"), Schedule((570,), None, None))
            self.assertEqual(parse("at 00:00"), Schedule((0,), None, None))
            self.assertEqual(parse("at 23:59").minutes, (1439,))
            self.assertEqual(parse("at 17:00 and 09:30").minutes, (570, 1020))
            self.assertEqual(parse("at 09:00 and 09:00").minutes, (540,))
            self.assertEqual(parse("at 06:00 and 12:00 and 18:00").minutes, (360, 720, 1080))

        def test_every(self):
            self.assertEqual(parse("every 15m between 08:00-09:00").minutes, (480, 495, 510, 525))
            self.assertEqual(parse("every 2h").minutes, tuple(range(0, 1440, 120)))
            self.assertEqual(parse("every 90m between 00:00-24:00").minutes, tuple(range(0, 1440, 90)))
            self.assertEqual(parse("every 1440m").minutes, (0,))
            self.assertEqual(parse("every 24h").minutes, (0,))
            self.assertEqual(parse("every 5h between 22:00-24:00").minutes, (1320,))
            self.assertEqual(parse("every 30m between 09:00-10:30").minutes, (540, 570, 600))
            self.assertEqual(parse("every 30m between 09:00-10:31").minutes, (540, 570, 600, 630))
            self.assertEqual(parse("every 1m between 10:00-10:03").minutes, (600, 601, 602))
            self.assertEqual(parse("every 1h between 23:00-24:00").minutes, (1380,))

        def test_case_and_spaces(self):
            self.assertEqual(parse("  AT   09:30   ON   MON  "), parse("at 09:30 on mon"))
            self.assertEqual(parse("Every  15M Between 08:00-09:00"), parse("every 15m between 08:00-09:00"))

        def test_bad_times(self):
            for text in ("at 24:00", "at 9:30", "at 09:60", "at 09:5", "at 0930", "at 25:00", "at 09:30 and", "at 09:30 and 24:00",
                         "at", "at ", "at 09:30 09:45", "at 09:30, 10:00", "every 15m between 24:00-24:00", "every 15m between 09:00-25:00",
                         "every 15m between 8:00-9:00"):
                with self.assertRaises(ValueError, msg=text):
                    parse(text)

        def test_bad_steps_and_windows(self):
            for text in ("every 0m", "every 0h", "every 1441m", "every 25h", "every m", "every 15", "every 15x", "every 1.5h",
                         "every -5m", "every 15m between 10:00-09:00", "every 15m between 10:00-10:00", "every 15m between 10:00",
                         "every 15m between", "every 15 m", "every 15m 08:00-09:00"):
                with self.assertRaises(ValueError, msg=text):
                    parse(text)

        def test_garbage(self):
            for text in ("", "daily", "on mon", "at 09:30 on", "at 09:30 daily", "at 09:30 on mon on tue", "run at 09:30", "at 09:30 on  "):
                with self.assertRaises(ValueError, msg=text):
                    parse(text)


    class ParseDays(unittest.TestCase):
        def test_named_sets(self):
            self.assertEqual(parse("at 09:30").weekdays, None)
            self.assertEqual(parse("at 09:30 on daily"), Schedule((570,), None, None))
            self.assertEqual(parse("at 09:30 on weekdays"), Schedule((570,), frozenset(range(5)), None))
            self.assertEqual(parse("at 09:30 on weekends"), Schedule((570,), frozenset((5, 6)), None))

        def test_weekday_lists(self):
            self.assertEqual(parse("at 09:30 on mon").weekdays, frozenset({0}))
            self.assertEqual(parse("at 09:30 on mon,wed,fri").weekdays, frozenset({0, 2, 4}))
            self.assertEqual(parse("at 09:30 on Sun, sat").weekdays, frozenset({5, 6}))
            self.assertEqual(parse("at 09:30 on tue,tue").weekdays, frozenset({1}))
            self.assertEqual(parse("at 09:30 on thu").monthdays, None)

        def test_month_days(self):
            self.assertEqual(parse("at 09:30 on day 1,15"), Schedule((570,), None, frozenset({1, 15})))
            self.assertEqual(parse("at 09:30 on day 31").monthdays, frozenset({31}))
            self.assertEqual(parse("at 09:30 on day 7, 21").monthdays, frozenset({7, 21}))

        def test_bad_days(self):
            for text in ("at 09:30 on day 0", "at 09:30 on day 32", "at 09:30 on day", "at 09:30 on day 1,,2", "at 09:30 on day x",
                         "at 09:30 on day -1", "at 09:30 on funday", "at 09:30 on mon,", "at 09:30 on monday", "at 09:30 on mon-fri",
                         "at 09:30 on mon tue", "at 09:30 on days 1", "at 09:30 on weekday"):
                with self.assertRaises(ValueError, msg=text):
                    parse(text)


    class Days(unittest.TestCase):
        def test_matches_day(self):
            weekdays = parse("at 09:30 on weekdays")
            self.assertTrue(matches_day(weekdays, DT(2025, 3, 7)))
            self.assertFalse(matches_day(weekdays, DT(2025, 3, 8)))
            self.assertTrue(matches_day(parse("at 09:30"), DT(2025, 3, 9)))
            first_and_last = parse("at 09:30 on day 1,31")
            self.assertTrue(matches_day(first_and_last, DT(2025, 3, 31)))
            self.assertTrue(matches_day(first_and_last, DT(2025, 4, 1)))
            self.assertFalse(matches_day(first_and_last, DT(2025, 4, 30)))

        def test_both_restrictions_would_have_to_hold(self):
            both = Schedule((570,), frozenset({0}), frozenset({3}))
            self.assertTrue(matches_day(both, DT(2025, 3, 3)))
            self.assertFalse(matches_day(both, DT(2025, 3, 10)))
            self.assertFalse(matches_day(both, DT(2025, 3, 4)))


    class Next(unittest.TestCase):
        def test_weekdays(self):
            s = parse("at 09:30 on weekdays")
            self.assertEqual(next_fire(s, DT(2025, 3, 7, 10, 0)), DT(2025, 3, 10, 9, 30))
            self.assertEqual(next_fire(s, DT(2025, 3, 3, 9, 29)), DT(2025, 3, 3, 9, 30))
            self.assertEqual(next_fire(s, DT(2025, 3, 3, 9, 30)), DT(2025, 3, 4, 9, 30))
            self.assertEqual(next_fire(s, DT(2025, 3, 3, 9, 30, 1)), DT(2025, 3, 4, 9, 30))
            self.assertEqual(next_fire(s, DT(2025, 3, 8, 12, 0)), DT(2025, 3, 10, 9, 30))
            self.assertEqual(next_fire(s, DT(2025, 3, 3, 0, 0)), DT(2025, 3, 3, 9, 30))

        def test_two_times_one_weekday(self):
            s = parse("at 06:00 and 18:00 on mon")
            self.assertEqual(next_fire(s, DT(2025, 3, 3, 6, 0)), DT(2025, 3, 3, 18, 0))
            self.assertEqual(next_fire(s, DT(2025, 3, 3, 18, 0)), DT(2025, 3, 10, 6, 0))
            self.assertEqual(next_fire(s, DT(2025, 3, 4, 0, 0)), DT(2025, 3, 10, 6, 0))
            self.assertEqual(next_fire(s, DT(2025, 3, 3, 5, 59)), DT(2025, 3, 3, 6, 0))

        def test_month_days(self):
            s = parse("at 12:00 on day 31")
            self.assertEqual(next_fire(s, DT(2025, 1, 31, 12, 0)), DT(2025, 3, 31, 12, 0))
            self.assertEqual(next_fire(s, DT(2025, 4, 1, 0, 0)), DT(2025, 5, 31, 12, 0))
            self.assertEqual(next_fire(s, DT(2025, 12, 31, 12, 0)), DT(2026, 1, 31, 12, 0))
            s = parse("at 12:00 on day 29")
            self.assertEqual(next_fire(s, DT(2025, 1, 30, 0, 0)), DT(2025, 3, 29, 12, 0))
            self.assertEqual(next_fire(s, DT(2024, 1, 30, 0, 0)), DT(2024, 2, 29, 12, 0))

        def test_every(self):
            s = parse("every 15m between 08:00-09:00 on mon")
            self.assertEqual(next_fire(s, DT(2025, 3, 3, 8, 40)), DT(2025, 3, 3, 8, 45))
            self.assertEqual(next_fire(s, DT(2025, 3, 3, 8, 45)), DT(2025, 3, 10, 8, 0))
            self.assertEqual(next_fire(s, DT(2025, 3, 3, 7, 0)), DT(2025, 3, 3, 8, 0))
            self.assertEqual(next_fire(s, DT(2025, 3, 3, 8, 0)), DT(2025, 3, 3, 8, 15))

        def test_daily_rolls_over_midnight(self):
            s = parse("at 00:00")
            self.assertEqual(next_fire(s, DT(2025, 3, 3, 23, 59)), DT(2025, 3, 4, 0, 0))
            self.assertEqual(next_fire(s, DT(2025, 12, 31, 0, 0)), DT(2026, 1, 1, 0, 0))

        def test_far_ahead(self):
            s = parse("at 12:00 on day 29")
            self.assertEqual(next_fire(s, DT(2025, 2, 28, 12, 0)), DT(2025, 3, 29, 12, 0))


    class FireTimes(unittest.TestCase):
        def test_window_and_weekdays(self):
            s = parse("every 30m between 09:00-10:30 on weekdays")
            got = fire_times(s, DT(2025, 3, 7, 9, 45), DT(2025, 3, 10, 9, 30))
            self.assertEqual(got, [DT(2025, 3, 7, 10, 0), DT(2025, 3, 10, 9, 0)])

        def test_start_inclusive_end_exclusive(self):
            s = parse("at 09:30 on mon")
            self.assertEqual(fire_times(s, DT(2025, 3, 3, 9, 30), DT(2025, 3, 3, 9, 31)), [DT(2025, 3, 3, 9, 30)])
            self.assertEqual(fire_times(s, DT(2025, 3, 3, 9, 29), DT(2025, 3, 3, 9, 30)), [])
            self.assertEqual(fire_times(s, DT(2025, 3, 3, 9, 30, 30), DT(2025, 3, 4)), [])

        def test_several_days(self):
            s = parse("at 06:00 and 18:00 on mon,thu")
            got = fire_times(s, DT(2025, 3, 3), DT(2025, 3, 11))
            self.assertEqual(got, [DT(2025, 3, 3, 6), DT(2025, 3, 3, 18), DT(2025, 3, 6, 6), DT(2025, 3, 6, 18), DT(2025, 3, 10, 6), DT(2025, 3, 10, 18)])

        def test_month_days(self):
            s = parse("at 08:00 on day 1,15,31")
            got = fire_times(s, DT(2025, 1, 1), DT(2025, 4, 2))
            self.assertEqual(got, [DT(2025, 1, 1, 8), DT(2025, 1, 15, 8), DT(2025, 1, 31, 8), DT(2025, 2, 1, 8), DT(2025, 2, 15, 8),
                                   DT(2025, 3, 1, 8), DT(2025, 3, 15, 8), DT(2025, 3, 31, 8), DT(2025, 4, 1, 8)])

        def test_empty(self):
            s = parse("at 09:30")
            self.assertEqual(fire_times(s, DT(2025, 3, 3, 10), DT(2025, 3, 3, 10)), [])
            self.assertEqual(fire_times(s, DT(2025, 3, 4), DT(2025, 3, 3)), [])
            self.assertEqual(len(fire_times(parse("every 1h"), DT(2025, 3, 3), DT(2025, 3, 5))), 48)


    if __name__ == "__main__":
        unittest.main()
''')

CRONISH = Lib(
    name="cronish", lang="python", title="the job-schedule language (`cronish/`)",
    blurb="The task runner reads schedules such as `every 15m between 08:00-18:00 on weekdays` and finds their next run with cronish.",
    files={"cronish/__init__.py": "", "cronish/parse.py": CN_PARSE, "cronish/fire.py": CN_FIRE, "README.md": CN_README,
           ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": CN_VISIBLE},
    hidden_tests={"tests/test_full.py": CN_HIDDEN},
    mutate=["cronish/parse.py", "cronish/fire.py"], difficulty=4, tags=["scheduler", "parsing", "calendar"],
    probes=[
        "parse('at 17:00 and 09:30').minutes", "parse('every 30m between 09:00-10:30').minutes", "parse('every 5h between 22:00-24:00').minutes",
        "parse('at 09:30 on Sun, sat')", "parse('at 09:30 on day 31')", "parse('every 15m between 10:00-10:00')", "parse('at 24:00')",
        "parse('every 1441m')", "parse('at 09:30 on day 32')",
        "next_fire(parse('at 09:30 on weekdays'), datetime(2025, 3, 3, 9, 30))", "next_fire(parse('at 09:30 on weekdays'), datetime(2025, 3, 3, 9, 29))",
        "next_fire(parse('at 12:00 on day 31'), datetime(2025, 1, 31, 12, 0))", "next_fire(parse('at 12:00 on day 29'), datetime(2024, 1, 30))",
        "fire_times(parse('every 30m between 09:00-10:30 on weekdays'), datetime(2025, 3, 7, 9, 45), datetime(2025, 3, 10, 9, 30))",
    ],
    probe_import="from datetime import datetime\nfrom cronish.parse import *\nfrom cronish.fire import *",
)

# ======================================================================================================================
# classquota: rolling-window booking quota for fitness classes
# ======================================================================================================================

CQ_README = dd('''
    # classquota

    Booking limits of a gym's class app. Dates are `datetime.date`, instants `datetime.datetime`.

    * `effective_status(status, cancelled_at=None, class_start=None)`: `status` is one of `booked`, `attended`, `no_show`,
      `cancelled`. A booking cancelled **less than 12 hours** before the class starts is a `late_cancel`; cancelled 12
      hours or more before it stays `cancelled`. For `cancelled` both `cancelled_at` and `class_start` are required
      (`ValueError` otherwise); any other status is returned unchanged. An unknown status is a `ValueError`.
    * `counts_toward_quota(status)`: everything counts except `cancelled`.
    * `can_book(history, class_day, quota=4, window=7)`: `history` is a list of `(day, effective_status)`. A member may
      book a class on `class_day` when **every** run of `window` consecutive days that contains `class_day` holds fewer
      than `quota` bookings that count.
    * `next_available(history, from_day, quota=4, window=7, horizon=60)`: the first day `d` with
      `from_day <= d <= from_day + horizon days` on which `can_book` is true, or `None`.
    * `remaining_quota(history, today, quota=4, window=7)`: the quota left in the `window` days starting on `today`
      (`today` included): `max(0, quota - counted bookings in [today, today + window - 1])`.
''')

CQ_SRC = dd('''
    from datetime import timedelta

    QUOTA = 4
    WINDOW = 7
    CANCEL_HOURS = 12
    KNOWN = ("booked", "attended", "no_show", "cancelled")


    def effective_status(status, cancelled_at=None, class_start=None):
        if status not in KNOWN:
            raise ValueError(f"unknown status {status!r}")
        if status != "cancelled":
            return status
        if cancelled_at is None or class_start is None:
            raise ValueError("a cancellation needs both instants")
        if class_start - cancelled_at < timedelta(hours=CANCEL_HOURS):
            return "late_cancel"
        return "cancelled"


    def counts_toward_quota(status):
        return status != "cancelled"


    def _counted(history):
        return [day for day, status in history if counts_toward_quota(status)]


    def can_book(history, class_day, quota=QUOTA, window=WINDOW):
        counted = _counted(history)
        for back in range(window):
            low = class_day - timedelta(days=back)
            high = low + timedelta(days=window - 1)
            if sum(1 for day in counted if low <= day <= high) >= quota:
                return False
        return True


    def next_available(history, from_day, quota=QUOTA, window=WINDOW, horizon=60):
        for offset in range(horizon + 1):
            day = from_day + timedelta(days=offset)
            if can_book(history, day, quota, window):
                return day
        return None


    def remaining_quota(history, today, quota=QUOTA, window=WINDOW):
        last = today + timedelta(days=window - 1)
        used = sum(1 for day in _counted(history) if today <= day <= last)
        return max(0, quota - used)
''')

CQ_VISIBLE = dd('''
    import unittest
    from datetime import date, datetime

    from classquota.quota import can_book, effective_status


    class BasicTests(unittest.TestCase):
        def test_late_cancel(self):
            start = datetime(2025, 3, 10, 18, 0)
            self.assertEqual(effective_status("cancelled", datetime(2025, 3, 10, 12, 0), start), "late_cancel")

        def test_empty_history(self):
            self.assertTrue(can_book([], date(2025, 3, 10)))


    if __name__ == "__main__":
        unittest.main()
''')

CQ_HIDDEN = dd('''
    import unittest
    from datetime import date, datetime

    from classquota.quota import can_book, counts_toward_quota, effective_status, next_available, remaining_quota

    D = date
    HISTORY = [(D(2025, 3, 3), "attended"), (D(2025, 3, 4), "booked"), (D(2025, 3, 5), "no_show")]


    class Status(unittest.TestCase):
        START = datetime(2025, 3, 10, 18, 0)

        def test_cancellation_notice(self):
            self.assertEqual(effective_status("cancelled", datetime(2025, 3, 10, 6, 0), self.START), "cancelled")
            self.assertEqual(effective_status("cancelled", datetime(2025, 3, 10, 6, 1), self.START), "late_cancel")
            self.assertEqual(effective_status("cancelled", datetime(2025, 3, 9, 6, 0), self.START), "cancelled")
            self.assertEqual(effective_status("cancelled", datetime(2025, 3, 10, 17, 59), self.START), "late_cancel")

        def test_other_statuses_are_unchanged(self):
            for status in ("booked", "attended", "no_show"):
                self.assertEqual(effective_status(status), status)
                self.assertEqual(effective_status(status, datetime(2025, 3, 10, 17, 0), self.START), status)

        def test_errors(self):
            with self.assertRaises(ValueError):
                effective_status("cancelled")
            with self.assertRaises(ValueError):
                effective_status("cancelled", datetime(2025, 3, 10, 1, 0))
            with self.assertRaises(ValueError):
                effective_status("cancelled", None, self.START)
            with self.assertRaises(ValueError):
                effective_status("waitlisted")

        def test_counting(self):
            self.assertFalse(counts_toward_quota("cancelled"))
            for status in ("booked", "attended", "no_show", "late_cancel"):
                self.assertTrue(counts_toward_quota(status), status)


    class CanBook(unittest.TestCase):
        def test_quota_three(self):
            table = {D(2025, 3, 6): False, D(2025, 3, 7): False, D(2025, 3, 8): False, D(2025, 3, 9): False, D(2025, 3, 10): True,
                     D(2025, 3, 11): True, D(2025, 3, 12): True, D(2025, 2, 26): True, D(2025, 2, 27): False, D(2025, 2, 28): False}
            for day, ok in table.items():
                self.assertEqual(can_book(HISTORY, day, quota=3), ok, day)

        def test_default_quota_is_four(self):
            self.assertTrue(can_book(HISTORY, D(2025, 3, 6)))
            more = HISTORY + [(D(2025, 3, 6), "booked")]
            self.assertFalse(can_book(more, D(2025, 3, 7)))
            self.assertTrue(can_book(more, D(2025, 3, 10)))
            self.assertFalse(can_book(more, D(2025, 3, 9)))

        def test_cancelled_do_not_count_late_cancels_do(self):
            hist = [(D(2025, 3, 3), "cancelled"), (D(2025, 3, 4), "booked"), (D(2025, 3, 5), "late_cancel")]
            self.assertTrue(can_book(hist, D(2025, 3, 6), quota=3))
            self.assertFalse(can_book(hist, D(2025, 3, 6), quota=2))

        def test_window_length(self):
            hist = [(D(2025, 3, 3), "booked"), (D(2025, 3, 4), "booked")]
            self.assertFalse(can_book(hist, D(2025, 3, 6), quota=2, window=7))
            self.assertTrue(can_book(hist, D(2025, 3, 6), quota=2, window=3))
            self.assertTrue(can_book(hist, D(2025, 3, 7), quota=2, window=3))
            self.assertTrue(can_book(hist, D(2025, 3, 6), quota=2, window=2))
            self.assertFalse(can_book(hist, D(2025, 3, 5), quota=2, window=3))
            self.assertTrue(can_book(hist, D(2025, 3, 5), quota=2, window=2))
            self.assertFalse(can_book(hist, D(2025, 3, 4), quota=2, window=2))
            self.assertFalse(can_book(hist, D(2025, 3, 9), quota=2, window=7))
            self.assertTrue(can_book(hist, D(2025, 3, 10), quota=2, window=7))

        def test_empty_history_and_quota_zero(self):
            self.assertTrue(can_book([], D(2025, 3, 6), quota=1))
            self.assertFalse(can_book([], D(2025, 3, 6), quota=0))

        def test_any_window_containing_the_day_counts(self):
            hist = [(D(2025, 3, 1), "booked"), (D(2025, 3, 2), "booked"), (D(2025, 3, 10), "booked"), (D(2025, 3, 11), "booked")]
            self.assertTrue(can_book(hist, D(2025, 3, 6), quota=3))
            self.assertFalse(can_book(hist, D(2025, 3, 6), quota=2))
            self.assertTrue(can_book(hist, D(2025, 3, 7), quota=3))


    class Next(unittest.TestCase):
        def test_first_free_day(self):
            self.assertEqual(next_available(HISTORY, D(2025, 3, 6), quota=3), D(2025, 3, 10))
            self.assertEqual(next_available(HISTORY, D(2025, 3, 10), quota=3), D(2025, 3, 10))
            self.assertEqual(next_available(HISTORY, D(2025, 3, 6)), D(2025, 3, 6))

        def test_horizon(self):
            self.assertEqual(next_available(HISTORY, D(2025, 3, 6), quota=3, horizon=4), D(2025, 3, 10))
            self.assertIsNone(next_available(HISTORY, D(2025, 3, 6), quota=3, horizon=3))
            self.assertIsNone(next_available(HISTORY, D(2025, 3, 6), quota=0))

        def test_default_horizon(self):
            self.assertEqual(next_available([], D(2025, 3, 6), quota=0, horizon=0), None)
            hist = [(D(2025, 3, 6), "booked")]
            self.assertEqual(next_available(hist, D(2025, 3, 6), quota=1), D(2025, 3, 13))


    class Remaining(unittest.TestCase):
        def test_values(self):
            self.assertEqual(remaining_quota(HISTORY, D(2025, 3, 3)), 1)
            self.assertEqual(remaining_quota(HISTORY, D(2025, 3, 3), quota=3), 0)
            self.assertEqual(remaining_quota(HISTORY, D(2025, 3, 4), quota=3), 1)
            self.assertEqual(remaining_quota(HISTORY, D(2025, 3, 6), quota=3), 3)

        def test_window_edges(self):
            self.assertEqual(remaining_quota(HISTORY, D(2025, 2, 26), quota=3), 1)
            self.assertEqual(remaining_quota(HISTORY, D(2025, 2, 25), quota=3), 2)
            self.assertEqual(remaining_quota(HISTORY, D(2025, 2, 24), quota=3), 3)
            self.assertEqual(remaining_quota(HISTORY, D(2025, 3, 3), quota=3, window=2), 1)
            self.assertEqual(remaining_quota(HISTORY, D(2025, 3, 5), quota=3, window=1), 2)

        def test_never_negative(self):
            self.assertEqual(remaining_quota(HISTORY, D(2025, 3, 3), quota=2), 0)

        def test_cancelled_do_not_count(self):
            self.assertEqual(remaining_quota([(D(2025, 3, 3), "cancelled")], D(2025, 3, 3)), 4)


    if __name__ == "__main__":
        unittest.main()
''')

CLASSQUOTA = Lib(
    name="classquota", lang="python", title="the class booking quota rules (`classquota/quota.py`)",
    blurb="The gym's class app decides whether a member may book another class using classquota.",
    files={"classquota/__init__.py": "", "classquota/quota.py": CQ_SRC, "README.md": CQ_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": CQ_VISIBLE},
    hidden_tests={"tests/test_full.py": CQ_HIDDEN},
    mutate=["classquota/quota.py"], difficulty=2, tags=["quota", "rolling-window", "bookings"],
    probes=[
        "effective_status('cancelled', datetime(2025, 3, 10, 6, 0), datetime(2025, 3, 10, 18, 0))",
        "effective_status('cancelled', datetime(2025, 3, 10, 6, 1), datetime(2025, 3, 10, 18, 0))",
        "counts_toward_quota('late_cancel')", "can_book(HISTORY, date(2025, 3, 9), quota=3)", "can_book(HISTORY, date(2025, 3, 10), quota=3)",
        "can_book(HISTORY, date(2025, 3, 6))", "can_book([(date(2025, 3, 3), 'cancelled')], date(2025, 3, 4), quota=1)",
        "next_available(HISTORY, date(2025, 3, 6), quota=3)", "next_available(HISTORY, date(2025, 3, 6), quota=3, horizon=3)",
        "remaining_quota(HISTORY, date(2025, 3, 3))", "remaining_quota(HISTORY, date(2025, 3, 3), quota=2)",
    ],
    probe_import=("from datetime import date, datetime\nfrom classquota.quota import *\n"
                  "HISTORY = [(date(2025, 3, 3), 'attended'), (date(2025, 3, 4), 'booked'), (date(2025, 3, 5), 'no_show')]"),
)

register_libs([ROOMCLASH, DOSETIMES, COURTDAYS, CRONISH, CLASSQUOTA], n=10)
