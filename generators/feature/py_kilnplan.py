"""kilnplan (python): a pottery-studio kiln planner extended with peaks, rules, loads, cooldowns, overlaps, timeline, energy cost."""
import random

from fx import dd
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # kilnplan

    Planning for a pottery studio's electric kiln (Python 3, standard library only): firing *programs* made of ramp and hold
    segments, and a timeline of scheduled *firings*. Times are whole minutes counted from Monday 00:00 of the planning week.
    Run the tests with `python3 -m unittest discover -s tests`.

    ## Layout

    * `kilnplan/program.py`: `Segment` and `Program`.
    * `kilnplan/kiln.py`: `Kiln` and `Firing`.

    ## Basics

    * `Segment(rate, target, hold=0)`: heat (or cool) at `rate` degrees C per hour until `target` degrees C, then hold
      for `hold` minutes.
    * `Program(name, segments)`: `ValueError` for an empty name, no segments or a rate that is not positive.
      `program.duration(start_temp=20)` is the total number of minutes: every ramp takes `ceil(|target - temp| * 60 / rate)`
      minutes, then the hold, where `temp` is the temperature the previous segment ended at (`start_temp` for the first).
    * `Kiln(name="studio kiln")`: `add_program(program)` (`ValueError` for a duplicate name), `program(name)` (`KeyError`
      for an unknown one).
    * `kiln.schedule(program_name, start, label="", **options)` puts a firing on the timeline and returns a `Firing`
      with `id` (1, 2, ...), `program`, `start`, `end = start + duration` and `label`. `start` must be an integer of
      at least 0 (`ValueError`); there are no options yet and unknown options raise `TypeError`.
    * `kiln.firings()` lists firings ordered by start time, then id; `kiln.firing(id)` and `kiln.cancel(id)` (returns
      the firing) raise `KeyError` for an unknown id.
''')

PROGRAM = '''\
"""Firing programs."""
from dataclasses import dataclass
@@uniq imports


@dataclass(frozen=True)
class Segment:
    rate: int  # degrees C per hour
    target: int  # degrees C
    hold: int = 0  # minutes


class Program:
    def __init__(self, name, segments):
        if not name:
            raise ValueError("a program needs a name")
        if not segments:
            raise ValueError("a program needs at least one segment")
        for s in segments:
            if s.rate <= 0:
                raise ValueError("rate must be positive")
            @@slot segment_checks
        self.name = name
        self.segments = tuple(segments)

    def duration(self, start_temp=20):
        minutes, temp = 0, start_temp
        for s in self.segments:
            minutes += -(-abs(s.target - temp) * 60 // s.rate) + s.hold
            temp = s.target
        return minutes

    @@blocks methods
'''

KILN = '''\
"""The kiln and its timeline."""
from dataclasses import dataclass
@@uniq imports


@dataclass
class Firing:
    id: int
    program: str
    start: int
    end: int
    label: str = ""
    @@slot firing_fields

@@blocks classes

class Kiln:
    def __init__(self, name="studio kiln"):
        self.name = name
        self._programs = {}
        self._firings = {}
        self._next = 1
        @@slot init

    def add_program(self, program):
        if program.name in self._programs:
            raise ValueError(f"duplicate program: {program.name}")
        self._programs[program.name] = program

    def program(self, name):
        try:
            return self._programs[name]
        except KeyError:
            raise KeyError(f"no such program: {name}") from None

    def schedule(self, program_name, start, label="", **opts):
        prog = self.program(program_name)
        if not isinstance(start, int) or isinstance(start, bool) or start < 0:
            raise ValueError("start must be an integer of at least 0")
        @@slot schedule_pre
        if opts:
            raise TypeError("unknown option(s): " + ", ".join(sorted(opts)))
        @@slot schedule_checks
        extra = {}
        @@slot firing_extra
        firing = Firing(self._next, program_name, start, start + prog.duration(), label, **extra)
        self._next += 1
        self._firings[firing.id] = firing
        @@slot on_schedule
        return firing

    def firings(self):
        return sorted(self._firings.values(), key=lambda f: (f.start, f.id))

    def firing(self, firing_id):
        try:
            return self._firings[firing_id]
        except KeyError:
            raise KeyError(f"no such firing: {firing_id}") from None

    def cancel(self, firing_id):
        firing = self.firing(firing_id)
        del self._firings[firing_id]
        @@slot on_cancel
        return firing

    @@blocks methods
'''

INIT = '''\
"""Kiln planning."""
from .kiln import Firing, Kiln
from .program import Program, Segment
@@uniq exports
'''

HELPERS = '''\
import unittest
@@uniq imports

from kilnplan import Firing, Kiln, Program, Segment


def make_kiln():
    k = Kiln("studio")
    k.add_program(Program("bisque", [Segment(100, 600), Segment(150, 950, 15)]))
    k.add_program(Program("glaze", [Segment(120, 1000, 10), Segment(60, 1240, 20)]))
    k.add_program(Program("quick", [Segment(200, 500)]))
    k.add_program(Program("warm", [Segment(100, 200, 7)]))
    return k

'''

VISIBLE = HELPERS + '''
class BasicTests(unittest.TestCase):
    def test_durations(self):
        k = make_kiln()
        self.assertEqual(k.program("bisque").duration(), 503)
        self.assertEqual(k.program("glaze").duration(), 760)
        self.assertEqual(k.program("quick").duration(), 144)
        self.assertEqual(Program("odd", [Segment(45, 100)]).duration(), 107)
        self.assertEqual(k.program("bisque").duration(start_temp=100), 455)

    def test_schedule_and_cancel(self):
        k = make_kiln()
        f = k.schedule("bisque", 2000, "shelf A")
        self.assertEqual((f.id, f.program, f.start, f.end, f.label), (1, "bisque", 2000, 2503, "shelf A"))
        g = k.schedule("quick", 100)
        self.assertEqual([x.id for x in k.firings()], [2, 1])
        self.assertIs(k.cancel(1), f)
        self.assertEqual([x.id for x in k.firings()], [2])
        with self.assertRaises(KeyError):
            k.firing(1)
    @@blocks tests
'''

HIDDEN = HELPERS + '''
class FeatureTests(unittest.TestCase):
    def test_base_rules(self):
        k = make_kiln()
        with self.assertRaises(ValueError):
            Program("", [Segment(10, 100)])
        with self.assertRaises(ValueError):
            Program("x", [])
        with self.assertRaises(ValueError):
            Program("x", [Segment(0, 100)])
        with self.assertRaises(ValueError):
            k.add_program(Program("quick", [Segment(10, 100)]))
        with self.assertRaises(KeyError):
            k.program("nope")
        with self.assertRaises(KeyError):
            k.schedule("nope", 0)
        for bad in (-1, 1.5, "9", True):
            with self.assertRaises(ValueError):
                k.schedule("quick", bad)
        with self.assertRaises(TypeError):
            k.schedule("quick", 0, colour="red")
        self.assertEqual(k.firings(), [])
        self.assertEqual(k.schedule("quick", 10_000).id, 1)
        self.assertEqual(k.schedule("warm", 20_000, label="x").label, "x")
        with self.assertRaises(KeyError):
            k.cancel(7)
        self.assertEqual(k.schedule("quick", 30_000).id, 3)
        self.assertEqual(Program("down", [Segment(100, 800), Segment(50, 300)]).duration(20), 468 + 600)
    @@blocks tests
'''


def make_slices(rng: random.Random):
    rate_max = rng.choice([400, 600, 800])
    target_max = rng.choice([1260, 1300, 1350])
    hold_max = rng.choice([480, 720, 960])
    capacity = rng.choice([12, 20, 24, 30])
    cool_default = rng.choice([80, 100, 120])
    S = []

    S.append(Slice(
        id="peak-temp", title="Peak temperature", d=1,
        pitch=("Glaze notes always ask for the highest temperature of a firing.",
               "People want to see at a glance how hot a program gets."),
        reqs=("`Program.peak()` returns the highest `target` among its segments (an int).",),
        code={
            "kilnplan/program.py::methods": '''
                def peak(self):
                    return max(s.target for s in self.segments)
            ''',
        },
        readme="## Peak temperature\n\n`Program.peak()` is the highest target temperature of the program.\n",
        vtests='''
            def test_peak_basic(self):
                self.assertEqual(make_kiln().program("glaze").peak(), 1240)
        ''',
        tests='''
            def test_peak(self):
                k = make_kiln()
                self.assertEqual(k.program("bisque").peak(), 950)
                self.assertEqual(k.program("quick").peak(), 500)
                self.assertEqual(Program("down", [Segment(100, 800), Segment(100, 300)]).peak(), 800)
                self.assertEqual(Program("flat", [Segment(100, 300)]).peak(), 300)
        ''',
    ))

    S.append(Slice(
        id="busy-total", title="Total firing time", d=1,
        pitch=("The studio bills kiln time by the hour and needs the total across the week.",
               "We want one number: how many minutes the kiln is booked."),
        reqs=("`Kiln.booked_minutes()` returns the sum of `end - start` over all scheduled firings (0 when there are none). Cancelled firings do not count.",),
        code={
            "kilnplan/kiln.py::methods": '''
                def booked_minutes(self):
                    return sum(f.end - f.start for f in self._firings.values())
            ''',
        },
        readme="## Total firing time\n\n`Kiln.booked_minutes()` sums `end - start` over the scheduled firings.\n",
        vtests='''
            def test_booked_basic(self):
                k = make_kiln()
                k.schedule("quick", 0)
                self.assertEqual(k.booked_minutes(), 144)
        ''',
        tests='''
            def test_booked_minutes(self):
                k = make_kiln()
                self.assertEqual(k.booked_minutes(), 0)
                a = k.schedule("quick", 10_000)
                k.schedule("bisque", 20_000)
                self.assertEqual(k.booked_minutes(), 144 + 503)
                k.cancel(a.id)
                self.assertEqual(k.booked_minutes(), 503)
        ''',
    ))

    S.append(Slice(
        id="segment-rules", title="Segment limits", d=2,
        pitch=("Somebody typed a ramp rate of 6000 and the kiln sitter almost believed it.",
               "The elements and the shelves have physical limits; programs outside them must be refused."),
        reqs=(f"A `Program` only accepts segments within these limits (inclusive), otherwise `ValueError`: `rate` 1 to {rate_max}, `target` 20 to {target_max}, `hold` 0 to {hold_max}.",
              "The checks apply to every segment of the program; the existing checks (name, at least one segment, positive rate) stay."),
        code={
            "kilnplan/program.py::segment_checks": f'''
                if s.rate > {rate_max}:
                    raise ValueError("rate is too high")
                if not 20 <= s.target <= {target_max}:
                    raise ValueError("target is outside 20..{target_max}")
                if not 0 <= s.hold <= {hold_max}:
                    raise ValueError("hold is outside 0..{hold_max}")
            ''',
        },
        readme=f"## Segment limits\n\nRates go up to {rate_max} degrees per hour, targets are 20 to {target_max} degrees and holds 0 to {hold_max} minutes; anything else is a `ValueError`.\n",
        vtests='''
            def test_segment_limit_basic(self):
                with self.assertRaises(ValueError):
                    Program("x", [Segment(100, 5000)])
        ''',
        tests=fmt('''
            def test_segment_limits(self):
                Program("edge", [Segment(__R__, __T__, __H__), Segment(1, 20, 0)])
                for bad in (Segment(__R__ + 1, 500), Segment(100, __T__ + 1), Segment(100, 19), Segment(100, 500, __H__ + 1), Segment(100, 500, -1)):
                    with self.assertRaises(ValueError):
                        Program("bad", [bad])
                with self.assertRaises(ValueError):
                    Program("bad", [Segment(100, 500), Segment(100, 500, __H__ + 1)])
                with self.assertRaises(ValueError):
                    Program("bad", [Segment(-5, 500)])
        ''', R=rate_max, T=target_max, H=hold_max),
    ))

    S.append(Slice(
        id="load-limit", title="Kiln load", d=2,
        pitch=("The big kiln only takes so many pots and people keep overloading it.",
               "Each firing should say how many pieces it holds and respect the kiln's capacity."),
        reqs=(f"`schedule(..., pieces=1)` takes a new option `pieces` (an integer of at least 1, default 1) and stores it on the `Firing` as `pieces`. `Kiln.capacity` is the most pieces one firing may hold, {capacity} by default; `Kiln.set_capacity(n)` changes it (`n` an integer of at least 1, otherwise `ValueError`).",
              "A firing with more pieces than the capacity, or a `pieces` that is not an integer of at least 1, is a `ValueError` and nothing is scheduled. Lowering the capacity does not touch firings that already exist."),
        code={
            "kilnplan/kiln.py::firing_fields": "pieces: int = 1",
            "kilnplan/kiln.py::firing_extra": 'extra["pieces"] = pieces',
            "kilnplan/kiln.py::init": f"self.capacity = {capacity}",
            "kilnplan/kiln.py::schedule_pre": "pieces = opts.pop(\"pieces\", 1)",
            "kilnplan/kiln.py::schedule_checks": '''
                if not isinstance(pieces, int) or isinstance(pieces, bool) or not 1 <= pieces <= self.capacity:
                    raise ValueError(f"pieces must be an integer from 1 to {self.capacity}")
            ''',
            "kilnplan/kiln.py::methods": '''
                def set_capacity(self, n):
                    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
                        raise ValueError("capacity must be an integer of at least 1")
                    self.capacity = n
            ''',
        },
        readme=fmt(dd('''
            ## Kiln load

            `schedule(..., pieces=1)` records how many pieces the firing holds (`Firing.pieces`); `Kiln.capacity` (default __C__) is
            the limit and `Kiln.set_capacity(n)` changes it. Too many or invalid pieces are a `ValueError`.
        '''), C=capacity),
        vtests='''
            def test_pieces_default(self):
                self.assertEqual(make_kiln().schedule("quick", 0).pieces, 1)
        ''',
        tests=fmt('''
            def test_pieces(self):
                k = make_kiln()
                self.assertEqual(k.capacity, __C__)
                self.assertEqual(k.schedule("quick", 10_000, pieces=__C__).pieces, __C__)
                self.assertEqual(k.schedule("quick", 20_000, "x", pieces=3).label, "x")
                for bad in (0, -1, __C__ + 1, 2.5, "4", True):
                    with self.assertRaises(ValueError):
                        k.schedule("quick", 30_000, pieces=bad)
                self.assertEqual(len(k.firings()), 2)
                self.assertEqual(k.schedule("quick", 40_000).id, 3)

            def test_capacity_changes(self):
                k = make_kiln()
                big = k.schedule("quick", 10_000, pieces=__C__)
                k.set_capacity(5)
                self.assertEqual(k.capacity, 5)
                self.assertEqual(big.pieces, __C__)
                with self.assertRaises(ValueError):
                    k.schedule("quick", 20_000, pieces=6)
                k.schedule("quick", 20_000, pieces=5)
                for bad in (0, -3, 1.5, "9"):
                    with self.assertRaises(ValueError):
                        k.set_capacity(bad)
                self.assertEqual(k.capacity, 5)
                k.set_capacity(100)
                self.assertEqual(k.schedule("quick", 30_000, pieces=100).pieces, 100)
        ''', C=capacity),
    ))

    S.append(Slice(
        id="cooldown", title="Cooling time", d=2,
        pitch=("The kiln cannot be opened or reloaded straight after a firing; it needs to cool.",
               "Plans must show when the kiln is actually free again."),
        reqs=(f"`Program.cooldown_minutes(rate)` is the time the kiln needs to cool from the last segment's `target` down to 60 degrees C at `rate` degrees per hour: `ceil((target - 60) * 60 / rate)`, or 0 when the target is 60 or lower.",
              f"`Kiln.cooling_rate` is the rate used for scheduling, {cool_default} degrees per hour by default; `Kiln.set_cooling_rate(rate)` changes it (an integer from 1 to 500, otherwise `ValueError`).",
              "A `Firing` gets `free_at`: its `end` plus the cooldown of its program at the cooling rate in force when it was scheduled (later changes of the rate do not move it)."),
        code={
            "kilnplan/program.py::methods": '''
                def cooldown_minutes(self, rate):
                    last = self.segments[-1].target
                    return -(-(last - 60) * 60 // rate) if last > 60 else 0
            ''',
            "kilnplan/kiln.py::firing_fields": "free_at: int = 0",
            "kilnplan/kiln.py::firing_extra": 'extra["free_at"] = start + prog.duration() + prog.cooldown_minutes(self.cooling_rate)',
            "kilnplan/kiln.py::init": f"self.cooling_rate = {cool_default}",
            "kilnplan/kiln.py::methods": '''
                def set_cooling_rate(self, rate):
                    if not isinstance(rate, int) or isinstance(rate, bool) or not 1 <= rate <= 500:
                        raise ValueError("cooling rate must be an integer from 1 to 500")
                    self.cooling_rate = rate
            ''',
        },
        readme=fmt(dd('''
            ## Cooling time

            `Program.cooldown_minutes(rate)` is `ceil((last target - 60) * 60 / rate)` (0 at or below 60 degrees). The kiln's
            `cooling_rate` (default __R__ degrees per hour, `set_cooling_rate` takes 1 to 500) decides `Firing.free_at = end + cooldown`.
        '''), R=cool_default),
        vtests='''
            def test_cooldown_basic(self):
                self.assertEqual(make_kiln().program("warm").cooldown_minutes(100), 84)
        ''',
        tests=fmt('''
            def test_cooldown_minutes(self):
                k = make_kiln()
                self.assertEqual(k.program("bisque").cooldown_minutes(100), 534)
                self.assertEqual(k.program("quick").cooldown_minutes(100), 264)
                self.assertEqual(k.program("quick").cooldown_minutes(70), 378)
                self.assertEqual(k.program("warm").cooldown_minutes(100), 84)
                self.assertEqual(Program("cold", [Segment(10, 60)]).cooldown_minutes(100), 0)
                self.assertEqual(Program("cold", [Segment(10, 40)]).cooldown_minutes(100), 0)
                self.assertEqual(Program("tiny", [Segment(10, 61)]).cooldown_minutes(100), 1)

            def test_free_at(self):
                k = make_kiln()
                self.assertEqual(k.cooling_rate, __D__)
                f = k.schedule("bisque", 1000)
                self.assertEqual(f.end, 1503)
                self.assertEqual(f.free_at, 1503 + -(-890 * 60 // __D__))
                k.set_cooling_rate(200)
                g = k.schedule("bisque", 10_000)
                self.assertEqual(g.free_at, 10_000 + 503 + 267)
                self.assertEqual(f.free_at, 1503 + -(-890 * 60 // __D__))
                self.assertEqual(k.firing(g.id).free_at, g.free_at)

            def test_cooling_rate_validation(self):
                k = make_kiln()
                for bad in (0, -5, 501, 1.5, "100", True):
                    with self.assertRaises(ValueError):
                        k.set_cooling_rate(bad)
                self.assertEqual(k.cooling_rate, __D__)
                k.set_cooling_rate(1)
                k.set_cooling_rate(500)
                self.assertEqual(k.cooling_rate, 500)
        ''', D=cool_default),
    ))

    S.append(Slice(
        id="overlap", title="No double booking", d=3,
        pitch=("Two potters booked the kiln for overlapping firings and one batch was ruined.",
               "The schedule must refuse a firing that collides with another."),
        reqs=("`schedule` raises the new error `kilnplan.Overlap` (a subclass of `ValueError`, exported from the package) when the new firing's interval `[start, end)` overlaps the interval `[start, end)` of an existing firing: they overlap when each starts before the other ends, so back-to-back firings are fine. `Overlap.firing` is the existing firing in the way (the earliest by start time, then id).",
              "The check runs after the existing validation of the arguments and options. A rejected call changes nothing (it uses no firing id). Cancelled firings no longer block anything."),
        code={
            "kilnplan/kiln.py::classes": '''
                class Overlap(ValueError):
                    """The new firing collides with an existing one."""

                    def __init__(self, firing):
                        super().__init__(f"overlaps firing {firing.id}")
                        self.firing = firing
            ''',
            "kilnplan/kiln.py::schedule_checks": '''
                busy_end = start + prog.duration()
                @@slot busy_end_extra
                for other in self.firings():
                    if start < self._busy_until(other) and other.start < busy_end:
                        raise Overlap(other)
            ''',
            "kilnplan/kiln.py::methods": '''
                def _busy_until(self, firing):
                    @@default busy_of
                    return firing.end
                    @@end
            ''',
            "kilnplan/__init__.py::exports": "from .kiln import Overlap",
        },
        readme=dd('''
            ## No double booking

            `schedule` raises `kilnplan.Overlap` (a `ValueError`, with `.firing` the one in the way) when `[start, end)` overlaps an
            existing firing; back-to-back firings are fine and nothing changes on rejection.
        '''),
        vtests='''
            def test_overlap_basic(self):
                from kilnplan import Overlap
                k = make_kiln()
                k.schedule("bisque", 1000)
                with self.assertRaises(Overlap):
                    k.schedule("quick", 1100)
        ''',
        tests='''
            def test_overlap_detection(self):
                from kilnplan import Overlap
                k = make_kiln()
                a = k.schedule("quick", 10_000)
                with self.assertRaises(Overlap) as cm:
                    k.schedule("quick", 10_100)
                self.assertIs(cm.exception.firing, a)
                self.assertIsInstance(cm.exception, ValueError)
                with self.assertRaises(Overlap):
                    k.schedule("bisque", 9_700)
                with self.assertRaises(Overlap):
                    k.schedule("warm", 10_050)
                self.assertEqual(len(k.firings()), 1)
                self.assertEqual(k.schedule("quick", 20_000).id, 2)

            def test_overlap_boundaries_and_cancel(self):
                from kilnplan import Overlap
                k = make_kiln()
                a = k.schedule("quick", 10_000)
                busy = getattr(a, "free_at", a.end)
                self.assertEqual(k.schedule("warm", busy + 5_000).id, 2)
                self.assertEqual(k.schedule("warm", 10_000 - 115 - 600).id, 3)
                with self.assertRaises(Overlap):
                    k.schedule("warm", 10_000 - 114)
                k.cancel(a.id)
                self.assertEqual(k.schedule("quick", 10_000).id, 4)

            def test_overlap_after_validation(self):
                k = make_kiln()
                k.schedule("quick", 10_000)
                with self.assertRaises(TypeError):
                    k.schedule("quick", 10_050, colour=1)
                with self.assertRaises(ValueError):
                    k.schedule("quick", -5)
                with self.assertRaises(KeyError):
                    k.schedule("nope", 10_050)
        ''',
        cross={
            "cooldown": {
                "reqs": ("A firing keeps the kiln busy until its `free_at`, not just its `end`: the busy interval of every firing is `[start, free_at)`, for the existing firings and for the new one.",),
                "code": {
                    "kilnplan/kiln.py::busy_of": "return firing.free_at",
                    "kilnplan/kiln.py::busy_end_extra": "busy_end += prog.cooldown_minutes(self.cooling_rate)",
                },
                "tests": '''
                    def test_cooldown_blocks_the_kiln(self):
                        from kilnplan import Overlap
                        k = make_kiln()
                        a = k.schedule("quick", 10_000)
                        with self.assertRaises(Overlap):
                            k.schedule("warm", a.end + 5)
                        self.assertEqual(k.schedule("warm", a.free_at).id, 2)
                        b = k.schedule("warm", 1_000)
                        with self.assertRaises(Overlap):
                            k.schedule("warm", b.start - 100)
                '''},
        },
    ))

    S.append(Slice(
        id="timeline", title="Weekly timeline", d=2,
        pitch=("The studio wall plan is handwritten every Monday.",
               "A printed schedule of the week's firings would save the Monday scramble."),
        reqs=("`Kiln.timeline()` returns one line per firing in the usual order (by start, then id): `DAY HH:MM -> DAY HH:MM PROGRAM`, then ` (LABEL)` when the label is not empty; every line ends with a newline and an empty timeline is the empty string.",
              "Minute 0 is Monday 00:00. `DAY` is `Mon`, `Tue`, `Wed`, `Thu`, `Fri`, `Sat` or `Sun`, and it wraps around after Sunday (minute 10080 is Monday again); `HH:MM` is zero-padded 24-hour time. The end is shown for the firing's `end`."),
        code={
            "kilnplan/kiln.py::methods": '''
                def timeline(self):
                    def stamp(minute):
                        day = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][(minute // 1440) % 7]
                        return f"{day} {minute % 1440 // 60:02d}:{minute % 60:02d}"

                    lines = []
                    for f in self.firings():
                        line = f"{stamp(f.start)} -> {stamp(f.end)} {f.program}"
                        if f.label:
                            line += f" ({f.label})"
                        lines.append(line + "\\n")
                    return "".join(lines)
            ''',
        },
        readme=dd('''
            ## Weekly timeline

            `Kiln.timeline()` prints `DAY HH:MM -> DAY HH:MM PROGRAM (LABEL)` per firing; minute 0 is Monday 00:00 and the days wrap.
        '''),
        vtests='''
            def test_timeline_basic(self):
                k = make_kiln()
                k.schedule("quick", 540)
                self.assertTrue(k.timeline().startswith("Mon 09:00 -> "))
        ''',
        tests='''
            def test_timeline_lines(self):
                k = make_kiln()
                self.assertEqual(k.timeline(), "")
                k.schedule("quick", 540, "shelf A")
                k.schedule("bisque", 1440 + 22 * 60 + 5)
                self.assertEqual(k.timeline(), "Mon 09:00 -> Mon 11:24 quick (shelf A)\\nTue 22:05 -> Wed 06:28 bisque\\n")

            def test_timeline_wraps_the_week(self):
                k = make_kiln()
                k.schedule("quick", 10_080 + 600)
                k.schedule("warm", 6 * 1440 + 23 * 60)
                self.assertEqual(k.timeline(), "Sun 23:00 -> Mon 00:55 warm\\nMon 10:00 -> Mon 12:24 quick\\n")
        ''',
    ))

    S.append(Slice(
        id="energy-cost", title="Energy cost", d=4,
        pitch=("Electricity is the studio's biggest bill and night rates are far cheaper, but nobody knows what a firing costs.",
               "Members should see what a firing costs, including the cheaper night tariff."),
        reqs=("Power draw depends on the **target** of the segment being fired: below 500 degrees C 4 kW, from 500 to 999 degrees 8 kW, 1000 degrees and above 12 kW. A segment's whole time (its ramp minutes plus its hold) is drawn at the power of its own target; ramps are computed from 20 degrees C at the start of the firing, exactly as `Program.duration` does.",
              "`Kiln.set_tariff(day, night, night_from=22, night_to=6)` sets the price in cents per kWh for daytime and night (integers of at least 0; hours integers from 0 to 23, otherwise `ValueError`). Minute `m` of the timeline is a night minute when its hour `(m // 60) % 24` satisfies `hour >= night_from or hour < night_to` (if `night_from < night_to` the night is `night_from <= hour < night_to`; if they are equal there is no night). The default tariff is 30 cents for day and night alike.",
              "`Kiln.cost_cents(firing_id)` is the cost of that firing: the sum over each of its minutes (firing start to `end`) of `kW * price`, divided by 60 and rounded to the nearest cent with halves up, i.e. `(sum + 30) // 60`. The price used is the tariff in force when `cost_cents` is called. Unknown firing: `KeyError`."),
        code={
            "kilnplan/program.py::methods": '''
                def power_profile(self):
                    """(minutes, kW) for each segment, from 20 degrees C."""
                    out, temp = [], 20
                    for s in self.segments:
                        minutes = -(-abs(s.target - temp) * 60 // s.rate) + s.hold
                        kw = 4 if s.target < 500 else 8 if s.target < 1000 else 12
                        out.append((minutes, kw))
                        temp = s.target
                    return out
            ''',
            "kilnplan/kiln.py::init": "self._tariff = (30, 30, 22, 6)",
            "kilnplan/kiln.py::methods": '''
                def set_tariff(self, day, night, night_from=22, night_to=6):
                    for v in (day, night):
                        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                            raise ValueError("prices must be integers of at least 0")
                    for h in (night_from, night_to):
                        if not isinstance(h, int) or isinstance(h, bool) or not 0 <= h <= 23:
                            raise ValueError("hours must be integers from 0 to 23")
                    self._tariff = (day, night, night_from, night_to)

                def cost_cents(self, firing_id):
                    f = self.firing(firing_id)
                    day, night, n_from, n_to = self._tariff
                    total, minute = 0, f.start
                    for minutes, kw in self.program(f.program).power_profile():
                        for _ in range(minutes):
                            hour = (minute // 60) % 24
                            if n_from < n_to:
                                is_night = n_from <= hour < n_to
                            else:
                                is_night = n_from != n_to and (hour >= n_from or hour < n_to)
                            total += kw * (night if is_night else day)
                            minute += 1
                    return (total + 30) // 60
            ''',
        },
        readme=dd('''
            ## Energy cost

            Segments draw 4 kW (target below 500 degrees), 8 kW (500 to 999) or 12 kW (1000 and up) for their whole time.
            `Kiln.set_tariff(day, night, night_from=22, night_to=6)` sets cents per kWh (default 30 flat) and
            `Kiln.cost_cents(firing_id)` sums `kW * price` over every minute, divided by 60 and rounded half up.
        '''),
        vtests='''
            def test_cost_basic(self):
                k = make_kiln()
                f = k.schedule("quick", 0)
                self.assertEqual(k.cost_cents(f.id), 576)
        ''',
        tests='''
            def test_cost_flat_and_rounding(self):
                k = make_kiln()
                q = k.schedule("quick", 0)
                self.assertEqual(k.cost_cents(q.id), 576)
                w = k.schedule("warm", 10_000)
                k.set_tariff(25, 25)
                self.assertEqual(k.cost_cents(w.id), 192)
                b = k.schedule("bisque", 20_000)
                k.set_tariff(30, 30)
                self.assertEqual(k.cost_cents(b.id), (348 * 8 * 30 + 155 * 8 * 30) // 60)
                g = k.schedule("glaze", 30_000)
                self.assertEqual(k.cost_cents(g.id), (500 * 12 * 30 + 260 * 12 * 30) // 60)
                with self.assertRaises(KeyError):
                    k.cost_cents(99)

            def test_cost_night_tariff(self):
                k = make_kiln()
                k.set_tariff(50, 20)
                f = k.schedule("quick", 21 * 60 + 30)
                self.assertEqual(k.cost_cents(f.id), 8 * (30 * 50 + 114 * 20) // 60)
                day = k.schedule("quick", 1440 + 8 * 60)
                self.assertEqual(k.cost_cents(day.id), 8 * 144 * 50 // 60)
                k.set_tariff(50, 20, night_from=1, night_to=3)
                early = k.schedule("quick", 2 * 1440)
                self.assertEqual(k.cost_cents(early.id), 8 * (60 * 50 + 84 * 20) // 60)

            def test_cost_tariff_windows_and_errors(self):
                k = make_kiln()
                w = k.schedule("warm", 0)
                k.set_tariff(60, 10, night_from=0, night_to=1)
                self.assertEqual(k.cost_cents(w.id), (4 * (60 * 10 + 55 * 60)) // 60)
                k.set_tariff(60, 10, night_from=5, night_to=5)
                self.assertEqual(k.cost_cents(w.id), (4 * 115 * 60) // 60)
                for bad in ((-1, 5), (5, -1), (1.5, 5)):
                    with self.assertRaises(ValueError):
                        k.set_tariff(*bad)
                for bad in (24, -1, 2.5):
                    with self.assertRaises(ValueError):
                        k.set_tariff(10, 10, night_from=bad)
                    with self.assertRaises(ValueError):
                        k.set_tariff(10, 10, night_to=bad)
                self.assertEqual(k.cost_cents(w.id), (4 * 115 * 60) // 60)
        ''',
    ))
    order = ["peak-temp", "busy-total", "segment-rules", "load-limit", "cooldown", "overlap", "timeline", "energy-cost"]
    S.sort(key=lambda x: order.index(x.id))
    return S


APP = App(
    name="kilnplan", lang="python", title="the kiln planning library", role="the studio manager", key="KILN",
    base={
        "README.md": README + "\n@@blocks features\n",
        "kilnplan/__init__.py": INIT,
        "kilnplan/program.py": PROGRAM,
        "kilnplan/kiln.py": KILN,
        ".gitignore": "__pycache__/\n*.pyc\n",
    },
    visible={"tests/test_basic.py": VISIBLE},
    hidden={"tests/test_features.py": HIDDEN},
)

register_app("feature-py-kilnplan", APP, make_slices, n=16, summary="pottery kiln planner: peak, limits, load, cooldown, overlaps, timeline, energy cost")
