"""cupdesk (python): a league table library extended with unplayed fixtures, form, corrections, deductions, text standings, zones, schedules and tie-breaks."""
import random

from fx import dd
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # cupdesk

    Results and standings for a small football league (Python 3, standard library only): every team plays every other team at
    home and away. Run the tests with `python3 -m unittest discover -s tests`.

    ## Layout

    * `cupdesk/league.py`: `League`, `Match`, `Row`.
    * `tests/`: tests.

    ## Basics

    * `League(name, teams, **options)`: the name must be non-blank and `teams` at least two different non-blank strings, kept in
      the given order (`ValueError`). There are no options yet; unknown options raise `TypeError`. `league.teams` is a tuple.
    * `league.record(home, away, home_goals, away_goals)` stores the result of a game and returns a `Match`
      (`home`, `away`, `home_goals`, `away_goals`, `seq`; `seq` counts 1, 2, 3, ... in the order of recording). Checks, in this
      order, all `ValueError`: both teams must be in the league and different; the goals must be non-negative integers
      (`bool` does not count); the pair `(home, away)` must not have been recorded already (the return game `(away, home)` is a
      different pair). A failed call changes nothing.
    * `league.results()` is a new list of the matches in the order they were recorded.
    * `league.table()` is a list of `Row`s (`team`, `played`, `won`, `drawn`, `lost`, `gf`, `ga`, `points` and the property
      `gd = gf - ga`), one per team, best first. A win is worth 3 points and a draw 1. The order is: more points, then better goal
      difference, then more goals scored, then the team name alphabetically.
''')

LEAGUE = '''\
"""Leagues, matches and tables."""
from dataclasses import dataclass
@@uniq imports


@dataclass(frozen=True)
class Match:
    home: str
    away: str
    home_goals: int
    away_goals: int
    seq: int


@dataclass(frozen=True)
class Row:
    team: str
    played: int
    won: int
    drawn: int
    lost: int
    gf: int
    ga: int
    points: int

    @property
    def gd(self):
        return self.gf - self.ga


def _count(n):
    return isinstance(n, int) and not isinstance(n, bool) and n >= 0


class League:
    def __init__(self, name, teams, **opts):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("a league needs a name")
        teams = list(teams)
        if any(not isinstance(t, str) or not t.strip() for t in teams):
            raise ValueError("team names must be non-blank strings")
        if len(teams) < 2 or len(set(teams)) != len(teams):
            raise ValueError("a league needs at least two different teams")
        @@slot init_opts
        if opts:
            raise TypeError("unknown option(s): " + ", ".join(sorted(opts)))
        self.name = name.strip()
        self.teams = tuple(teams)
        self._matches = {}
        self._seq = 0
        @@slot init

    def _check_pair(self, home, away):
        if home not in self.teams or away not in self.teams:
            raise ValueError(f"unknown team in {home!r} v {away!r}")
        if home == away:
            raise ValueError("a team cannot play itself")

    def record(self, home, away, home_goals, away_goals):
        self._check_pair(home, away)
        if not _count(home_goals) or not _count(away_goals):
            raise ValueError("goals must be non-negative integers")
        if (home, away) in self._matches:
            raise ValueError(f"{home} v {away} has already been played")
        self._seq += 1
        match = Match(home, away, home_goals, away_goals, self._seq)
        self._matches[(home, away)] = match
        @@slot on_record
        return match

    def results(self):
        return sorted(self._matches.values(), key=lambda m: m.seq)

    @@default penalty_method
    def _penalty(self, team):
        return 0
    @@end

    def table(self):
        st = {t: [0, 0, 0, 0, 0, 0] for t in self.teams}  # played, won, drawn, lost, gf, ga
        for m in self._matches.values():
            for team, f, a in ((m.home, m.home_goals, m.away_goals), (m.away, m.away_goals, m.home_goals)):
                s = st[team]
                s[0] += 1
                s[4] += f
                s[5] += a
                s[1 if f > a else 2 if f == a else 3] += 1
        rows = [Row(t, s[0], s[1], s[2], s[3], s[4], s[5], 3 * s[1] + s[2] - self._penalty(t)) for t, s in st.items()]
        @@default sort_rows
        rows.sort(key=lambda r: (-r.points, -r.gd, -r.gf, r.team))
        @@end
        return rows

    @@blocks methods
'''

INIT = '''\
"""League tables."""
from .league import League, Match, Row
@@uniq exports
'''

HELPERS = '''\
import unittest
@@uniq imports

from cupdesk import League

TEAMS = ["Ajax", "Brno", "Cadiz", "Dover"]
SEASON = [
    ("Ajax", "Brno", 1, 0), ("Cadiz", "Dover", 2, 2), ("Brno", "Cadiz", 2, 1), ("Dover", "Ajax", 0, 1),
    ("Ajax", "Cadiz", 0, 0), ("Brno", "Dover", 3, 1), ("Brno", "Ajax", 1, 0), ("Dover", "Cadiz", 1, 0),
    ("Cadiz", "Ajax", 2, 1), ("Dover", "Brno", 1, 1), ("Cadiz", "Brno", 0, 1), ("Ajax", "Dover", 2, 2),
]
# few games, several teams level on points
TIES = [
    ("Dover", "Ajax", 0, 1), ("Cadiz", "Dover", 1, 0), ("Cadiz", "Ajax", 1, 0), ("Ajax", "Brno", 3, 0),
    ("Cadiz", "Brno", 0, 2), ("Dover", "Brno", 1, 0), ("Ajax", "Cadiz", 1, 1),
]


def make_league(results=SEASON, **kw):
    lg = League("Sunday League", TEAMS, **kw)
    for r in results:
        lg.record(*r)
    return lg


def rows(lg):
    return [(r.team, r.played, r.won, r.drawn, r.lost, r.gf, r.ga, r.points) for r in lg.table()]

'''

VISIBLE = HELPERS + '''
class BasicTests(unittest.TestCase):
    def test_record_and_results(self):
        lg = make_league()
        m = lg.results()[0]
        self.assertEqual((m.home, m.away, m.home_goals, m.away_goals, m.seq), ("Ajax", "Brno", 1, 0, 1))
        self.assertEqual(len(lg.results()), 12)
        with self.assertRaises(ValueError):
            lg.record("Ajax", "Brno", 2, 2)
        with self.assertRaises(ValueError):
            lg.record("Ajax", "Ajax", 0, 0)
        with self.assertRaises(ValueError):
            lg.record("Ajax", "Zed", 0, 0)

    def test_table(self):
        lg = make_league()
        self.assertEqual([r.team for r in lg.table()], ["Brno", "Ajax", "Dover", "Cadiz"])
        top = lg.table()[0]
        self.assertEqual((top.points, top.gd, top.played), (13, 4, 6))
    @@blocks tests
'''

HIDDEN = HELPERS + '''
class FeatureTests(unittest.TestCase):
    def test_base_league_validation(self):
        for name in ["", "  ", None, 3]:
            with self.assertRaises(ValueError, msg=repr(name)):
                League(name, TEAMS)
        for teams in [[], ["A"], ["A", "A"], ["A", ""], ["A", " "], ["A", 5], ["A", None]]:
            with self.assertRaises(ValueError, msg=repr(teams)):
                League("x", teams)
        with self.assertRaises(TypeError):
            League("x", TEAMS, colour="red")
        lg = League("  Cup  ", ("B", "A", "C"))
        self.assertEqual((lg.name, lg.teams), ("Cup", ("B", "A", "C")))
        self.assertEqual([r.team for r in lg.table()], ["A", "B", "C"])
        self.assertEqual(lg.results(), [])

    def test_base_record_rules(self):
        lg = make_league()
        before = (rows(lg), len(lg.results()))
        bad = [("Ajax", "Brno", 0, 0), ("Zed", "Brno", 0, 0), ("Ajax", "Zed", 0, 0), ("Ajax", "Ajax", 1, 1), (None, "Ajax", 0, 0),
               ("Brno", "Cadiz", 1, 1), ("Dover", "Ajax", -1, 0)]
        for args in bad:
            with self.assertRaises(ValueError, msg=repr(args)):
                lg.record(*args)
        for hg, ag in [(1.5, 0), (0, "1"), (True, 0), (0, None), (-1, 0), (0, -2)]:
            fresh = League("x", TEAMS)
            with self.assertRaises(ValueError, msg=repr((hg, ag))):
                fresh.record("Ajax", "Brno", hg, ag)
            self.assertEqual(fresh.results(), [])
        self.assertEqual((rows(lg), len(lg.results())), before)
        fresh = League("x", TEAMS)
        fresh.record("Ajax", "Brno", 0, 0)
        self.assertEqual(fresh.record("Brno", "Ajax", 2, 1).seq, 2)
        self.assertEqual([m.seq for m in fresh.results()], [1, 2])
        self.assertEqual([m.seq for m in make_league().results()], list(range(1, 13)))

    def test_base_table(self):
        lg = make_league()
        self.assertEqual(rows(lg), REF_SEASON)
        self.assertEqual([r.gd for r in lg.table()], [4, 0, -2, -2])
        fresh = League("x", TEAMS)
        self.assertEqual(rows(fresh), [(t, 0, 0, 0, 0, 0, 0, 0) for t in TEAMS])

    def test_base_table_order(self):
        # level on points: goal difference, then goals scored, then name
        lg = League("x", ["Zed", "Yan", "Xia", "Wim"])
        lg.record("Zed", "Yan", 1, 1)
        lg.record("Xia", "Wim", 2, 2)
        self.assertEqual([r.team for r in lg.table()], ["Wim", "Xia", "Yan", "Zed"])
        lg.record("Yan", "Xia", 3, 1)
        lg.record("Wim", "Zed", 1, 0)
        self.assertEqual(rows(lg), REF_LEVEL)
    @@blocks tests
'''


# ----------------------------------------------------------------------------------------------------- reference

def ref_stats(teams, matches):
    st = {t: dict(p=0, w=0, d=0, l=0, gf=0, ga=0) for t in teams}
    for h, a, x, y in matches:
        for t, f, g in ((h, x, y), (a, y, x)):
            st[t]["p"] += 1
            st[t]["gf"] += f
            st[t]["ga"] += g
        if x > y:
            st[h]["w"] += 1
            st[a]["l"] += 1
        elif x < y:
            st[a]["w"] += 1
            st[h]["l"] += 1
        else:
            st[h]["d"] += 1
            st[a]["d"] += 1
    for t in st:
        st[t]["pts"] = 3 * st[t]["w"] + st[t]["d"]
        st[t]["gd"] = st[t]["gf"] - st[t]["ga"]
    return st


def ref_rank(teams, matches, pen, criteria):
    st = ref_stats(teams, matches)
    pen = pen or {}

    def val(t, c):
        return {"points": st[t]["pts"] - pen.get(t, 0), "gd": st[t]["gd"], "gf": st[t]["gf"], "wins": st[t]["w"]}[c]

    def rk(group, crit):
        if len(group) <= 1:
            return list(group)
        if not crit:
            return sorted(group)
        c, rest = crit[0], crit[1:]
        if c == "h2h":
            sub = [m for m in matches if m[0] in group and m[1] in group]
            mini = ref_stats(group, sub)

            def keyf(t):
                return (mini[t]["pts"], mini[t]["gd"], mini[t]["gf"])
        else:
            def keyf(t):
                return val(t, c)
        buckets = {}
        for t in group:
            buckets.setdefault(keyf(t), []).append(t)
        out = []
        for k in sorted(buckets, reverse=True):
            out += rk(buckets[k], rest)
        return out

    return rk(list(teams), ["points"] + list(criteria))


def ref_rows(teams, matches, pen=None, criteria=("gd", "gf")):
    st = ref_stats(teams, matches)
    pen = pen or {}
    return [(t, st[t]["p"], st[t]["w"], st[t]["d"], st[t]["l"], st[t]["gf"], st[t]["ga"], st[t]["pts"] - pen.get(t, 0))
            for t in ref_rank(teams, matches, pen, criteria)]


TEAMS = ["Ajax", "Brno", "Cadiz", "Dover"]
SEASON = [
    ("Ajax", "Brno", 1, 0), ("Cadiz", "Dover", 2, 2), ("Brno", "Cadiz", 2, 1), ("Dover", "Ajax", 0, 1),
    ("Ajax", "Cadiz", 0, 0), ("Brno", "Dover", 3, 1), ("Brno", "Ajax", 1, 0), ("Dover", "Cadiz", 1, 0),
    ("Cadiz", "Ajax", 2, 1), ("Dover", "Brno", 1, 1), ("Cadiz", "Brno", 0, 1), ("Ajax", "Dover", 2, 2),
]
TIES = [
    ("Dover", "Ajax", 0, 1), ("Cadiz", "Dover", 1, 0), ("Cadiz", "Ajax", 1, 0), ("Ajax", "Brno", 3, 0),
    ("Cadiz", "Brno", 0, 2), ("Dover", "Brno", 1, 0), ("Ajax", "Cadiz", 1, 1),
]
LEVEL = [("Zed", "Yan", 1, 1), ("Xia", "Wim", 2, 2), ("Yan", "Xia", 3, 1), ("Wim", "Zed", 1, 0)]


def lit(x):
    return repr(x)


def ref_circle(teams, double=False):
    ts = list(teams)
    if len(ts) % 2:
        ts.append(None)
    n = len(ts)
    rounds = []
    for r in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = ts[i], ts[n - 1 - i]
            if a is None or b is None:
                continue
            pairs.append((a, b) if (r + i) % 2 == 0 else (b, a))
        rounds.append(pairs)
        ts = [ts[0]] + [ts[-1]] + ts[1:-1]
    if double:
        rounds = rounds + [[(b, a) for a, b in rd] for rd in rounds]
    return rounds


def make_slices(rng: random.Random):
    form_n = rng.choice([3, 5])
    labels = rng.choice([("W", "D", "L"), ("w", "d", "l")])
    S = []

    S.append(Slice(
        id="unplayed", title="Games still to play", d=1,
        pitch=("Two teams never met at home and nobody noticed until the last matchday.",
               "The secretary wants the list of games that have not been played yet."),
        reqs=("`league.unplayed()` returns the pairs `(home, away)` that have not been recorded yet, as a list of tuples ordered by the position of the home team in `league.teams`, then by the position of the away team. A team never plays itself, so a fresh league of `n` teams has `n * (n - 1)` unplayed pairs.",),
        code={
            "cupdesk/league.py::methods": '''
                def unplayed(self):
                    return [(h, a) for h in self.teams for a in self.teams if h != a and (h, a) not in self._matches]
            ''',
        },
        readme="## Games still to play\n\n`league.unplayed()` lists the `(home, away)` pairs without a result, ordered by home team position, then away team position.\n",
        vtests='''
            def test_unplayed_basic(self):
                lg = make_league(SEASON[:10])
                self.assertEqual(len(lg.unplayed()), 2)
        ''',
        tests=fmt('''
            def test_unplayed(self):
                fresh = League("x", TEAMS)
                self.assertEqual(len(fresh.unplayed()), 12)
                self.assertEqual(fresh.unplayed()[:4], [("Ajax", "Brno"), ("Ajax", "Cadiz"), ("Ajax", "Dover"), ("Brno", "Ajax")])
                self.assertEqual(make_league().unplayed(), [])
                lg = make_league(SEASON[:10])
                self.assertEqual(lg.unplayed(), __A__)
                lg.record("Cadiz", "Brno", 0, 0)
                self.assertEqual(lg.unplayed(), [("Ajax", "Dover")])
                two = League("x", ["B", "A"])
                self.assertEqual(two.unplayed(), [("B", "A"), ("A", "B")])
                two.record("A", "B", 0, 0)
                self.assertEqual(two.unplayed(), [("B", "A")])
        ''', A=lit([(h, a) for h in TEAMS for a in TEAMS if h != a and (h, a) not in {(m[0], m[1]) for m in SEASON[:10]}])),
    ))

    S.append(Slice(
        id="form", title="Recent form", d=2,
        pitch=("The match programme prints the last results of every team and somebody types them in by hand.",
               "Fans want to see how a team has done in its latest games."),
        reqs=(f"`league.form(team, n={form_n})` returns a string with one letter per game of the team, `{labels[0]}` for a win, `{labels[1]}` for a draw and `{labels[2]}` for a defeat, for the last `n` games the team played (home or away) in the order they were recorded, oldest first; fewer games give a shorter string, no games an empty one. An unknown team is a `KeyError`; `n` must be an integer of at least 1 (`ValueError`).",),
        code={
            "cupdesk/league.py::methods": f'''
                def form(self, team, n={form_n}):
                    if team not in self.teams:
                        raise KeyError(team)
                    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
                        raise ValueError("n must be an integer of at least 1")
                    letters = []
                    for m in self.results():
                        if team not in (m.home, m.away):
                            continue
                        mine, theirs = (m.home_goals, m.away_goals) if team == m.home else (m.away_goals, m.home_goals)
                        letters.append("{labels[0]}" if mine > theirs else "{labels[1]}" if mine == theirs else "{labels[2]}")
                    return "".join(letters[-n:])
            ''',
        },
        readme=f"## Recent form\n\n`league.form(team, n={form_n})` is a string of `{labels[0]}`/`{labels[1]}`/`{labels[2]}` for the team's last `n` games in recording order, oldest first.\n",
        vtests='''
            def test_form_basic(self):
                self.assertEqual(len(make_league().form("Ajax", 5)), 5)
        ''',
        tests=fmt('''
            def test_form(self):
                lg = make_league()
                self.assertEqual(lg.form("Ajax", 6), __AJAX6__)
                self.assertEqual(lg.form("Brno", 6), __BRNO6__)
                self.assertEqual(lg.form("Ajax", 2), __AJAX6__[-2:])
                self.assertEqual(lg.form("Dover", 100), __DOVER__)
                self.assertEqual(lg.form("Cadiz"), __CADIZ__[-__N__:])
                fresh = League("x", TEAMS)
                self.assertEqual(fresh.form("Ajax"), "")
                fresh.record("Brno", "Ajax", 2, 1)
                self.assertEqual((fresh.form("Ajax"), fresh.form("Brno"), fresh.form("Cadiz")), ("__L__", "__W__", ""))

            def test_form_errors(self):
                lg = make_league()
                with self.assertRaises(KeyError):
                    lg.form("Zed")
                for bad in [0, -1, 1.5, "2", None, True]:
                    with self.assertRaises(ValueError, msg=repr(bad)):
                        lg.form("Ajax", bad)
        ''', N=form_n, W=labels[0], L=labels[2],
            AJAX6=lit(_form("Ajax", labels)), BRNO6=lit(_form("Brno", labels)), DOVER=lit(_form("Dover", labels)), CADIZ=lit(_form("Cadiz", labels))),
    ))

    S.append(Slice(
        id="corrections", title="Corrections and voided games", d=2,
        pitch=("A referee's report changed a score after the fact and the only fix was to rebuild the league.",
               "Recorded results need to be correctable and removable."),
        reqs=("`league.correct(home, away, home_goals, away_goals)` replaces the result of a game that was recorded and returns the new `Match`, which keeps the `seq` of the old one (so the recording order does not change). The checks of `record` apply to the arguments (same order, same `ValueError`s), except that the pair must already exist: a pair that was not recorded is a `KeyError`, checked after the team and goal checks.",
              "`league.void(home, away)` removes a recorded game and returns its `Match` (`KeyError` when the pair was not recorded; teams that are not in the league are a `ValueError`). Sequence numbers of later games do not change, and the next `record` still gets the next unused number. A voided pair can be recorded again."),
        code={
            "cupdesk/league.py::methods": '''
                def correct(self, home, away, home_goals, away_goals):
                    self._check_pair(home, away)
                    if not _count(home_goals) or not _count(away_goals):
                        raise ValueError("goals must be non-negative integers")
                    old = self._matches.get((home, away))
                    if old is None:
                        raise KeyError((home, away))
                    new = Match(home, away, home_goals, away_goals, old.seq)
                    self._matches[(home, away)] = new
                    return new

                def void(self, home, away):
                    self._check_pair(home, away)
                    try:
                        return self._matches.pop((home, away))
                    except KeyError:
                        raise KeyError((home, away)) from None
            ''',
        },
        readme="## Corrections and voided games\n\n`league.correct(home, away, hg, ag)` replaces a result (keeping its `seq`; `KeyError` if the pair was not recorded), `league.void(home, away)` removes one and returns it. Later `seq` numbers stay as they are.\n",
        vtests='''
            def test_correct_basic(self):
                lg = make_league()
                lg.correct("Ajax", "Brno", 0, 3)
                self.assertEqual(lg.results()[0].home_goals, 0)
        ''',
        tests=fmt('''
            def test_correct(self):
                lg = make_league()
                m = lg.correct("Ajax", "Brno", 0, 3)
                self.assertEqual((m.home_goals, m.away_goals, m.seq), (0, 3, 1))
                self.assertEqual(lg.results()[0], m)
                self.assertEqual([x.seq for x in lg.results()], list(range(1, 13)))
                self.assertEqual(rows(lg), __A__)

            def test_correct_errors(self):
                lg = make_league(SEASON[:3])
                before = rows(lg)
                with self.assertRaises(KeyError):
                    lg.correct("Cadiz", "Ajax", 1, 1)
                for args in [("Ajax", "Zed", 1, 1), ("Ajax", "Ajax", 1, 1), ("Zed", "Ajax", 1, 1), ("Ajax", "Brno", -1, 0), ("Ajax", "Brno", 1.5, 0)]:
                    with self.assertRaises(ValueError, msg=repr(args)):
                        lg.correct(*args)
                with self.assertRaises(ValueError):
                    lg.correct("Cadiz", "Cadiz", -1, 0)
                with self.assertRaises(ValueError):
                    lg.correct("Cadiz", "Ajax", -1, 0)
                self.assertEqual(rows(lg), before)

            def test_void(self):
                lg = make_league()
                gone = lg.void("Brno", "Cadiz")
                self.assertEqual((gone.home, gone.away, gone.home_goals, gone.seq), ("Brno", "Cadiz", 2, 3))
                self.assertEqual(len(lg.results()), 11)
                self.assertEqual([m.seq for m in lg.results()], [1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12])
                self.assertEqual(rows(lg), __B__)
                with self.assertRaises(KeyError):
                    lg.void("Brno", "Cadiz")
                with self.assertRaises(ValueError):
                    lg.void("Brno", "Zed")
                with self.assertRaises(ValueError):
                    lg.void("Brno", "Brno")
                again = lg.record("Brno", "Cadiz", 0, 0)
                self.assertEqual(again.seq, 13)
                self.assertEqual(lg.results()[-1], again)
        ''', A=lit(ref_rows(TEAMS, [("Ajax", "Brno", 0, 3)] + SEASON[1:])), B=lit(ref_rows(TEAMS, [m for m in SEASON if (m[0], m[1]) != ("Brno", "Cadiz")]))),
    ))

    S.append(Slice(
        id="deductions", title="Points deductions", d=2,
        pitch=("A club fielded an ineligible player and the federation took three points away.",
               "The table has to support points deductions imposed by the federation."),
        reqs=("`league.deduct(team, points, reason=\"\")` takes `points` (a positive integer, `bool` excluded) off the points of a team and records the reason (unknown team: `ValueError`; invalid points: `ValueError`, checked after the team). Several deductions add up, and `Row.points` in `table()` is the earned points minus all deductions (it can become negative), which also decides the order.",
              "`league.deductions()` returns the deductions as a new list of `(team, points, reason)` tuples in the order they were made."),
        code={
            "cupdesk/league.py::init": "self._deductions = []",
            "cupdesk/league.py::penalty_method": '''
                def _penalty(self, team):
                    return sum(p for t, p, _ in self._deductions if t == team)
            ''',
            "cupdesk/league.py::methods": '''
                def deduct(self, team, points, reason=""):
                    if team not in self.teams:
                        raise ValueError(f"unknown team: {team!r}")
                    if not isinstance(points, int) or isinstance(points, bool) or points < 1:
                        raise ValueError("points must be a positive integer")
                    self._deductions.append((team, points, reason))

                def deductions(self):
                    return list(self._deductions)
            ''',
        },
        readme="## Points deductions\n\n`league.deduct(team, points, reason=\"\")` removes points (cumulative, may go negative) and `league.deductions()` lists them as `(team, points, reason)`; `table()` uses the reduced points for the order.\n",
        vtests='''
            def test_deduct_basic(self):
                lg = make_league()
                lg.deduct("Brno", 3, "paperwork")
                self.assertEqual(lg.table()[0].points, 10)
        ''',
        tests=fmt('''
            def test_deductions(self):
                lg = make_league()
                lg.deduct("Brno", 6, "ineligible player")
                lg.deduct("Cadiz", 1)
                lg.deduct("Brno", 2, "late payment")
                self.assertEqual(rows(lg), __A__)
                self.assertEqual(lg.deductions(), [("Brno", 6, "ineligible player"), ("Cadiz", 1, ""), ("Brno", 2, "late payment")])
                lg.deductions().clear()
                self.assertEqual(len(lg.deductions()), 3)
                self.assertEqual(League("x", TEAMS).deductions(), [])

            def test_deduction_can_go_negative(self):
                lg = League("x", ["A", "B"])
                lg.deduct("B", 4, "fraud")
                self.assertEqual([(r.team, r.points) for r in lg.table()], [("A", 0), ("B", -4)])

            def test_deduction_validation(self):
                lg = make_league()
                before = rows(lg)
                for args in [("Zed", 3), ("Zed", 0), ("Ajax", 0), ("Ajax", -1), ("Ajax", 1.5), ("Ajax", "3"), ("Ajax", True), ("Ajax", None)]:
                    with self.assertRaises(ValueError, msg=repr(args)):
                        lg.deduct(*args)
                self.assertEqual((rows(lg), lg.deductions()), (before, []))
        ''', A=lit(ref_rows(TEAMS, SEASON, {"Brno": 8, "Cadiz": 1}))),
    ))

    S.append(Slice(
        id="standings", title="Text standings", d=2,
        pitch=("The club newsletter wants the table as plain text and it keeps getting the columns wrong.",
               "The league needs a printable standings table."),
        reqs=("`league.standings_text()` returns one line per row of `table()`, each ending in a newline: the position (1 for the first row, right-aligned in 2 characters), a space, the team name left-aligned to the width of the longest team name, a space, then played, won, drawn and lost each right-aligned in 2 characters and separated by single spaces, a space, goals for right-aligned in 3 characters, a hyphen, goals against left-aligned in 3 characters, a space, and the points right-aligned in 3 characters. Trailing spaces are removed. Positions are simply the row numbers (teams on equal terms do not share one).",),
        code={
            "cupdesk/league.py::methods": '''
                def standings_text(self):
                    table = self.table()
                    width = max(len(r.team) for r in table)
                    lines = []
                    for pos, r in enumerate(table, 1):
                        line = (f"{pos:>2} {r.team:<{width}} {r.played:>2} {r.won:>2} {r.drawn:>2} {r.lost:>2} "
                                f"{r.gf:>3}-{r.ga:<3} {r.points:>3}")
                        lines.append(line.rstrip() + "\\n")
                    return "".join(lines)
            ''',
        },
        readme="## Text standings\n\n`league.standings_text()` prints the table one row per line: position, team, played, won, drawn, lost, `GF-GA`, points, with fixed column widths.\n",
        vtests='''
            def test_standings_basic(self):
                self.assertTrue(make_league().standings_text().startswith(" 1 Brno"))
        ''',
        tests=fmt('''
            def test_standings_text(self):
                self.assertEqual(make_league().standings_text(), __A__)
                self.assertEqual(League("x", ["A", "Bb"]).standings_text(), __EMPTY__)
                lg = League("x", ["Long Name FC", "B"])
                lg.record("B", "Long Name FC", 12, 100)
                self.assertEqual(lg.standings_text(), __LONG__)
        ''', A=lit("".join(
            f"{pos:>2} {t:<5} {p:>2} {w:>2} {d:>2} {l:>2} {gf:>3}-{ga:<3} {pts:>3}".rstrip() + "\n"
            for pos, (t, p, w, d, l, gf, ga, pts) in enumerate(ref_rows(TEAMS, SEASON), 1))),
            EMPTY=lit(_std([("A", 0, 0, 0, 0, 0, 0, 0), ("Bb", 0, 0, 0, 0, 0, 0, 0)])),
            LONG=lit(_std([("Long Name FC", 1, 1, 0, 0, 100, 12, 3), ("B", 1, 0, 0, 1, 12, 100, 0)]))),
        cross={
            "deductions": {"tests": '''
                def test_standings_use_deducted_points(self):
                    lg = make_league()
                    lg.deduct("Brno", 20)
                    lines = lg.standings_text().splitlines()
                    self.assertTrue(lines[-1].startswith(" 4 Brno"))
                    self.assertTrue(lines[-1].endswith(" -7"))
            '''},
        },
    ))

    S.append(Slice(
        id="zones", title="Promotion and relegation zones", d=2,
        pitch=("The end-of-season report has to say who goes up and who goes down.",
               "The league needs to mark the promoted and relegated teams."),
        reqs=("`league.zones(promote=0, relegate=0)` returns a dict with every team (keys in table order) and its zone: `\"promoted\"` for the first `promote` rows of `table()`, `\"relegated\"` for the last `relegate` rows and `\"\"` for the others. Both arguments must be integers of at least 0 (`bool` excluded) and together at most the number of teams (`ValueError`).",),
        code={
            "cupdesk/league.py::methods": '''
                def zones(self, promote=0, relegate=0):
                    for n in (promote, relegate):
                        if not isinstance(n, int) or isinstance(n, bool) or n < 0:
                            raise ValueError("promote and relegate must be integers of at least 0")
                    if promote + relegate > len(self.teams):
                        raise ValueError("more zones than teams")
                    table = self.table()
                    out = {}
                    for i, r in enumerate(table):
                        out[r.team] = "promoted" if i < promote else "relegated" if i >= len(table) - relegate else ""
                    return out
            ''',
        },
        readme="## Promotion and relegation zones\n\n`league.zones(promote=0, relegate=0)` maps each team (in table order) to `\"promoted\"`, `\"relegated\"` or `\"\"`; both numbers are integers >= 0 and add up to at most the number of teams.\n",
        vtests='''
            def test_zones_basic(self):
                self.assertEqual(make_league().zones(promote=1)["Brno"], "promoted")
        ''',
        tests='''
            def test_zones(self):
                lg = make_league()
                self.assertEqual(lg.zones(promote=1, relegate=1), {"Brno": "promoted", "Ajax": "", "Dover": "", "Cadiz": "relegated"})
                self.assertEqual(list(lg.zones(promote=1, relegate=1)), ["Brno", "Ajax", "Dover", "Cadiz"])
                self.assertEqual(lg.zones(), {"Brno": "", "Ajax": "", "Dover": "", "Cadiz": ""})
                self.assertEqual(set(lg.zones(promote=2, relegate=2).values()), {"promoted", "relegated"})
                self.assertEqual(lg.zones(relegate=3), {"Brno": "", "Ajax": "relegated", "Dover": "relegated", "Cadiz": "relegated"})
                self.assertEqual(lg.zones(promote=4), {"Brno": "promoted", "Ajax": "promoted", "Dover": "promoted", "Cadiz": "promoted"})

            def test_zone_validation(self):
                lg = make_league()
                for args in [(3, 2), (5, 0), (0, 5), (-1, 0), (0, -1), (1.5, 0), ("1", 0), (None, 0), (True, 0), (0, True)]:
                    with self.assertRaises(ValueError, msg=repr(args)):
                        lg.zones(*args)
        ''',
        cross={
            "deductions": {"tests": '''
                def test_zones_follow_deductions(self):
                    lg = make_league()
                    lg.deduct("Brno", 20)
                    self.assertEqual(lg.zones(promote=1, relegate=1), {"Ajax": "promoted", "Dover": "", "Cadiz": "", "Brno": "relegated"})
            '''},
        },
    ))

    f_single = ref_circle(TEAMS)
    f_odd = ref_circle(["Ajax", "Brno", "Cadiz", "Dover", "Elba"])
    f_double = ref_circle(["Ajax", "Brno", "Cadiz"], double=True)
    f_six = ref_circle(["A", "B", "C", "D", "E", "F"])

    S.append(Slice(
        id="fixtures", title="Fixture schedule", d=3,
        pitch=("The league secretary draws up the season calendar by hand every year.",
               "The league should generate the fixture list by itself."),
        reqs=("`league.fixtures(double=False)` returns the round-robin schedule as a list of rounds, each a list of `(home, away)` tuples, using the circle method: take the teams in `league.teams` order and, when their number is odd, append a bye (nobody) as an extra team. For round `r` (0-based) pair position `i` with position `n - 1 - i` for `i` in `0 .. n/2 - 1` (`n` is the number of positions); the home team is the one in position `i` when `(r + i)` is even and the other one when it is odd; pairs with the bye are left out. After each round the list is rotated: the first position stays and the last one moves to the second position (`[a, b, c, d]` becomes `[a, d, b, c]`). There are `n - 1` rounds.",
              "With `double=True` the schedule is followed by the same rounds again, in the same order, with home and away swapped in every pair. `fixtures` does not depend on which games have been played; it does not change anything."),
        code={
            "cupdesk/league.py::methods": '''
                def fixtures(self, double=False):
                    ts = list(self.teams)
                    if len(ts) % 2:
                        ts.append(None)
                    n = len(ts)
                    rounds = []
                    for r in range(n - 1):
                        pairs = []
                        for i in range(n // 2):
                            a, b = ts[i], ts[n - 1 - i]
                            if a is None or b is None:
                                continue
                            pairs.append((a, b) if (r + i) % 2 == 0 else (b, a))
                        rounds.append(pairs)
                        ts = [ts[0]] + [ts[-1]] + ts[1:-1]
                    if double:
                        rounds = rounds + [[(b, a) for a, b in rd] for rd in rounds]
                    return rounds
            ''',
        },
        readme="## Fixture schedule\n\n`league.fixtures(double=False)` returns the rounds of the circle-method schedule (home team of position `i` when `r + i` is even; odd leagues get a bye; `double=True` adds the reverse legs).\n",
        vtests=f'''
            def test_fixtures_basic(self):
                rounds = League("x", TEAMS).fixtures()
                self.assertEqual(len(rounds), 3)
                self.assertEqual(rounds[0], {lit(f_single[0])})
        ''',
        tests=fmt('''
            def test_fixtures_even(self):
                self.assertEqual(League("x", TEAMS).fixtures(), __A__)
                six = League("x", ["A", "B", "C", "D", "E", "F"]).fixtures()
                self.assertEqual(six, __SIX__)
                games = [g for rd in six for g in rd]
                self.assertEqual(len(games), 15)
                self.assertEqual(len({frozenset(g) for g in games}), 15)
                for rd in six:
                    self.assertEqual(len({t for g in rd for t in g}), 6)

            def test_fixtures_odd_leagues_have_byes(self):
                lg = League("x", ["Ajax", "Brno", "Cadiz", "Dover", "Elba"])
                self.assertEqual(lg.fixtures(), __ODD__)
                for rd in lg.fixtures():
                    self.assertEqual(len(rd), 2)
                three = League("x", ["A", "B", "C"]).fixtures()
                self.assertEqual([len(rd) for rd in three], [1, 1, 1])

            def test_fixtures_double(self):
                lg = League("x", ["Ajax", "Brno", "Cadiz"])
                self.assertEqual(lg.fixtures(double=True), __DOUBLE__)
                self.assertEqual(lg.fixtures(double=False), lg.fixtures())
                self.assertEqual(len(League("x", TEAMS).fixtures(True)), 6)
                lg.record("Ajax", "Brno", 1, 0)
                self.assertEqual(lg.fixtures(), League("x", ["Ajax", "Brno", "Cadiz"]).fixtures())
                two = League("x", ["A", "B"])
                self.assertEqual(two.fixtures(), [[("A", "B")]])
                self.assertEqual(two.fixtures(True), [[("A", "B")], [("B", "A")]])
        ''', A=lit(f_single), SIX=lit(f_six), ODD=lit(f_odd), DOUBLE=lit(f_double)),
        cross={
            "unplayed": {
                "reqs": ("Every `(home, away)` pair of `fixtures(double=True)` is a pair that `unplayed()` lists in a fresh league, and vice versa.",),
                "tests": '''
                    def test_double_schedule_covers_unplayed(self):
                        lg = League("x", TEAMS)
                        scheduled = {g for rd in lg.fixtures(True) for g in rd}
                        self.assertEqual(scheduled, set(lg.unplayed()))
                        lg.record("Ajax", "Brno", 1, 0)
                        self.assertEqual(scheduled - set(lg.unplayed()), {("Ajax", "Brno")})
                '''},
        },
    ))

    crit_pairs = {
        "default": ref_rows(TEAMS, TIES, None, ("gd", "gf")),
        "h2h": ref_rows(TEAMS, TIES, None, ("h2h", "gd", "gf")),
        "wins": ref_rows(TEAMS, TIES, None, ("wins", "gd", "gf")),
        "gf": ref_rows(TEAMS, TIES, None, ("gf", "gd")),
        "gf_only": ref_rows(TEAMS, TIES, None, ("gf",)),
        "h2h_last": ref_rows(TEAMS, TIES, None, ("gd", "h2h")),
    }
    pen_h2h = ref_rows(TEAMS, TIES, {"Cadiz": 3}, ("h2h", "gd", "gf"))
    level_order = ref_rank(["Zed", "Yan", "Xia", "Wim"], LEVEL, None, ("gd", "gf"))

    S.append(Slice(
        id="tiebreak", title="Configurable tie-breaks", d=4,
        pitch=("The league rules changed: head-to-head results now decide between teams level on points, and the table code ignores that.",
               "Different competitions break ties differently and the league needs to support that."),
        reqs=("`League(..., criteria=(\"gd\", \"gf\"))` takes an option `criteria`, a tuple (or list) of distinct names from `\"gd\"` (goal difference), `\"gf\"` (goals scored), `\"wins\"` (number of wins) and `\"h2h\"` (head-to-head); an empty tuple is fine; anything else (an unknown name, a repeated name, a non-sequence) is a `ValueError`. `league.criteria` returns it as a tuple. The default `(\"gd\", \"gf\")` is the order of the base rules.",
              "`table()` ranks the teams by points first. Teams that are level are then compared by the first criterion (higher is better); teams that are still level on it are compared by the next one, and so on, each time only among the teams that are still level. `\"h2h\"` compares the teams of the current level group by a mini table built only from the recorded games between those teams (points, then goal difference, then goals scored, in that order, higher is better; no other criteria inside the mini table). Teams still level after all criteria are ordered by name."),
        code={
            "cupdesk/league.py::init_opts": '''
                criteria = opts.pop("criteria", ("gd", "gf"))
                try:
                    criteria = tuple(criteria)
                except TypeError:
                    raise ValueError("criteria must be a sequence of names") from None
                if len(set(criteria)) != len(criteria) or any(c not in ("gd", "gf", "wins", "h2h") for c in criteria):
                    raise ValueError("criteria must be distinct names from gd, gf, wins and h2h")
            ''',
            "cupdesk/league.py::init": "self.criteria = criteria",
            "cupdesk/league.py::sort_rows": '''
                rows = self._rank(rows, ("points",) + self.criteria)
            ''',
            "cupdesk/league.py::methods": '''
                def _rank(self, group, criteria):
                    if len(group) <= 1:
                        return list(group)
                    if not criteria:
                        return sorted(group, key=lambda r: r.team)
                    first, rest = criteria[0], criteria[1:]
                    if first == "h2h":
                        names = {r.team for r in group}
                        mini = {t: [0, 0, 0] for t in names}  # points, gd, gf
                        for m in self._matches.values():
                            if m.home in names and m.away in names:
                                for team, f, a in ((m.home, m.home_goals, m.away_goals), (m.away, m.away_goals, m.home_goals)):
                                    mini[team][0] += 3 if f > a else 1 if f == a else 0
                                    mini[team][1] += f - a
                                    mini[team][2] += f

                        def key(r):
                            return tuple(mini[r.team])
                    else:
                        def key(r):
                            return {"points": r.points, "gd": r.gd, "gf": r.gf, "wins": r.won}[first]
                    buckets = {}
                    for r in group:
                        buckets.setdefault(key(r), []).append(r)
                    out = []
                    for k in sorted(buckets, reverse=True):
                        out += self._rank(buckets[k], rest)
                    return out
            ''',
        },
        readme="## Configurable tie-breaks\n\n`League(..., criteria=(\"gd\", \"gf\"))` with names from `gd`, `gf`, `wins` and `h2h`. Teams level on points are compared by the criteria in order, each time only among those still level; `h2h` uses a mini table (points, goal difference, goals scored) of the games between the level teams. Names decide the rest.\n",
        vtests='''
            def test_criteria_basic(self):
                lg = make_league(TIES, criteria=("gd", "gf"))
                self.assertEqual(lg.criteria, ("gd", "gf"))
        ''',
        tests=fmt('''
            def test_default_criteria(self):
                lg = make_league(TIES)
                self.assertEqual(lg.criteria, ("gd", "gf"))
                self.assertEqual(rows(lg), __DEFAULT__)
                self.assertEqual(rows(make_league(TIES, criteria=["gd", "gf"])), __DEFAULT__)
                self.assertEqual(rows(make_league()), __SEASON__)

            def test_criteria_change_the_order(self):
                self.assertEqual(rows(make_league(TIES, criteria=("h2h", "gd", "gf"))), __H2H__)
                self.assertEqual(rows(make_league(TIES, criteria=("wins", "gd", "gf"))), __WINS__)
                self.assertEqual(rows(make_league(TIES, criteria=("gf", "gd"))), __GF__)
                self.assertEqual(rows(make_league(TIES, criteria=("gf",))), __GFONLY__)
                self.assertEqual(rows(make_league(TIES, criteria=("gd", "h2h"))), __H2HLAST__)
                self.assertEqual([r[0] for r in rows(make_league(TIES, criteria=()))], __NOCRIT__)

            def test_h2h_is_a_mini_table(self):
                lg = League("x", ["Zed", "Yan", "Xia", "Wim"], criteria=("h2h", "gd", "gf"))
                for r in __LEVEL__:
                    lg.record(*r)
                self.assertEqual([r.team for r in lg.table()], __LEVELORDER__)
                self.assertEqual(lg.criteria, ("h2h", "gd", "gf"))

            def test_criteria_validation(self):
                for bad in [("points",), ("gd", "gd"), ("name",), "gd", 5, None, ("gd", "xyz"), ("GD",)]:
                    with self.assertRaises(ValueError, msg=repr(bad)):
                        make_league(criteria=bad)
                self.assertEqual(League("x", TEAMS, criteria=()).criteria, ())
                with self.assertRaises(TypeError):
                    League("x", TEAMS, criterion=("gd",))
        ''', SEASON=lit(REF_SEASON), DEFAULT=lit(crit_pairs["default"]), H2H=lit(crit_pairs["h2h"]), WINS=lit(crit_pairs["wins"]), GF=lit(crit_pairs["gf"]),
            GFONLY=lit(crit_pairs["gf_only"]), H2HLAST=lit(crit_pairs["h2h_last"]),
            NOCRIT=lit([r[0] for r in ref_rows(TEAMS, TIES, None, ())]), LEVEL=lit(LEVEL),
            LEVELORDER=lit(ref_rank(["Zed", "Yan", "Xia", "Wim"], LEVEL, None, ("h2h", "gd", "gf")))),
        cross={
            "deductions": {
                "reqs": ("The head-to-head mini table is built from game results only: deductions are not part of it, but they do count in the points that are compared first.",),
                "tests": fmt('''
                    def test_h2h_ignores_deductions_but_points_do_not(self):
                        lg = make_league(TIES, criteria=("h2h", "gd", "gf"))
                        lg.deduct("Cadiz", 3)
                        self.assertEqual(rows(lg), __A__)
                ''', A=lit(pen_h2h)),
            },
            "corrections": {"tests": fmt('''
                def test_h2h_follows_corrections(self):
                    lg = make_league(TIES, criteria=("h2h", "gd", "gf"))
                    lg.correct("Cadiz", "Ajax", 0, 2)
                    self.assertEqual([r[0] for r in rows(lg)], __A__)
            ''', A=lit([r[0] for r in ref_rows(TEAMS, [m if (m[0], m[1]) != ("Cadiz", "Ajax") else ("Cadiz", "Ajax", 0, 2) for m in TIES], None, ("h2h", "gd", "gf"))]))},
        },
    ))

    return S


def _std(rows_):
    width = max(len(r[0]) for r in rows_)
    return "".join(f"{pos:>2} {t:<{width}} {p:>2} {w:>2} {d:>2} {l:>2} {gf:>3}-{ga:<3} {pts:>3}".rstrip() + "\n"
                   for pos, (t, p, w, d, l, gf, ga, pts) in enumerate(rows_, 1))


def _form(team, labels):
    out = ""
    for h, a, x, y in SEASON:
        if team not in (h, a):
            continue
        mine, theirs = (x, y) if team == h else (y, x)
        out += labels[0] if mine > theirs else labels[1] if mine == theirs else labels[2]
    return out


REF_SEASON = ref_rows(TEAMS, SEASON)
REF_LEVEL = ref_rows(["Zed", "Yan", "Xia", "Wim"], LEVEL)

APP = App(
    name="cupdesk", lang="python", title="the league table library", role="the league secretary", key="CUP",
    base={
        "README.md": README + "\n@@blocks features\n",
        "cupdesk/__init__.py": INIT,
        "cupdesk/league.py": LEAGUE,
        ".gitignore": "__pycache__/\n*.pyc\n",
    },
    visible={"tests/test_basic.py": VISIBLE},
    hidden={"tests/test_features.py": HIDDEN.replace("REF_SEASON", repr(REF_SEASON)).replace("REF_LEVEL", repr(REF_LEVEL))},
)

register_app("feature-py-cupdesk", APP, make_slices, n=18, summary="league tables: unplayed games, form, corrections, deductions, text standings, zones, fixture schedule, tie-breaks")
