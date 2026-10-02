"""pollroom (python): a small polling library extended with changed and retracted votes, quorum, tie-breaks, weights, shares and ranked ballots."""
import random

from fx import dd
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # pollroom

    Polls for a residents' association (Python 3, standard library only): a question, a few options and one ballot per voter.
    Run the tests with `python3 -m unittest discover -s tests`.

    ## Layout

    * `pollroom/poll.py`: `Poll` and `Ballot`.
    * `tests/`: tests.

    ## Basics

    * `Poll(question, options, **options)`: the question must be a non-blank string and the options at least two different
      non-blank strings, kept in the given order (`ValueError`). `poll.question` is the stripped question and `poll.options`
      a tuple. There are no further options yet; unknown ones raise `TypeError`.
    * `poll.vote(voter, choice)` records a ballot. Checks in this order: the voter must be a non-blank string, the choice one
      of the options, the voter must not have voted already (all `ValueError`), then unknown keyword options (`TypeError`).
      A failed call changes nothing.
    * `poll.voters()` is the sorted list of voter names, `poll.total()` the number of votes.
    * `poll.tally()` is a dict with every option (in option order, 0 for options nobody chose) and its number of votes.
    * `poll.winner()` is the option with strictly the most votes, or `None` when nobody voted or the top is tied.
    * `poll.report()` has one line `OPTION: COUNT` per option in option order, each ending in a newline.
''')

POLL = '''\
"""Polls and ballots."""
from dataclasses import dataclass
@@uniq imports


@dataclass
class Ballot:
    voter: str
    ranking: tuple
    seq: int
    @@slot ballot_fields

    @property
    def choice(self):
        return self.ranking[0]


class Poll:
    def __init__(self, question, options, **opts):
        if not isinstance(question, str) or not question.strip():
            raise ValueError("a poll needs a question")
        options = list(options)
        if any(not isinstance(o, str) or not o.strip() for o in options):
            raise ValueError("options must be non-blank strings")
        if len(options) < 2 or len(set(options)) != len(options):
            raise ValueError("a poll needs at least two different options")
        @@slot init_opts
        if opts:
            raise TypeError("unknown option(s): " + ", ".join(sorted(opts)))
        self.question = question.strip()
        self.options = tuple(options)
        self._ballots = {}
        self._seq = 0
        @@slot init

    def _cast(self, voter, ranking, opts):
        if not isinstance(voter, str) or not voter.strip():
            raise ValueError("a voter needs a name")
        for o in ranking:
            if o not in self.options:
                raise ValueError(f"unknown option: {o!r}")
        if len(set(ranking)) != len(ranking):
            raise ValueError("an option can be ranked only once")
        if voter in self._ballots:
            raise ValueError(f"{voter} has already voted")
        @@slot cast_opts
        if opts:
            raise TypeError("unknown option(s): " + ", ".join(sorted(opts)))
        extra = {}
        @@slot ballot_extra
        self._seq += 1
        self._ballots[voter] = Ballot(voter, tuple(ranking), self._seq, **extra)

    def vote(self, voter, choice, **opts):
        self._cast(voter, (choice,), opts)

    @@default weight_method
    def _weight(self, ballot):
        return 1
    @@end

    def voters(self):
        return sorted(self._ballots)

    def total(self):
        return sum(self._weight(b) for b in self._ballots.values())

    def tally(self):
        counts = {o: 0 for o in self.options}
        for b in self._ballots.values():
            counts[b.choice] += self._weight(b)
        return counts

    def winner(self):
        counts = self.tally()
        @@slot winner_pre
        top = max(counts.values())
        if top == 0:
            return None
        leaders = [o for o in self.options if counts[o] == top]
        if len(leaders) == 1:
            return leaders[0]
        @@default tie_rule
        return None
        @@end

    def report(self):
        return "".join(f"{o}: {n}\\n" for o, n in self.tally().items())

    @@blocks methods
'''

INIT = '''\
"""Polls."""
from .poll import Ballot, Poll
@@uniq exports
'''

HELPERS = '''\
import unittest
@@uniq imports

from pollroom import Poll

VOTES = [("ana", "ramen"), ("bob", "pizza"), ("cy", "ramen"), ("dee", "salad"), ("eli", "ramen")]


def make_poll(votes=VOTES, **kw):
    p = Poll("Lunch on Friday?", ["pizza", "ramen", "salad"], **kw)
    for voter, choice in votes:
        p.vote(voter, choice)
    return p

'''

VISIBLE = HELPERS + '''
class BasicTests(unittest.TestCase):
    def test_vote_and_tally(self):
        p = make_poll()
        self.assertEqual(p.tally(), {"pizza": 1, "ramen": 3, "salad": 1})
        self.assertEqual(p.winner(), "ramen")
        self.assertEqual(p.total(), 5)
        self.assertEqual(p.voters(), ["ana", "bob", "cy", "dee", "eli"])

    def test_rules(self):
        p = make_poll()
        with self.assertRaises(ValueError):
            p.vote("ana", "pizza")
        with self.assertRaises(ValueError):
            p.vote("fay", "sushi")
        with self.assertRaises(ValueError):
            Poll("x", ["only"])
        self.assertEqual(p.report(), "pizza: 1\\nramen: 3\\nsalad: 1\\n")
        self.assertIsNone(make_poll([("a", "pizza"), ("b", "ramen")]).winner())
    @@blocks tests
'''

HIDDEN = HELPERS + '''
class FeatureTests(unittest.TestCase):
    def test_base_poll_validation(self):
        for q in ["", "   ", None, 5]:
            with self.assertRaises(ValueError, msg=repr(q)):
                Poll(q, ["a", "b"])
        for opts in [[], ["a"], ["a", "a"], ["a", ""], ["a", " "], ["a", 5], ["a", None]]:
            with self.assertRaises(ValueError, msg=repr(opts)):
                Poll("q", opts)
        with self.assertRaises(TypeError):
            Poll("q", ["a", "b"], colour="red")
        p = Poll("  Which?  ", ("b", "a", "c"))
        self.assertEqual((p.question, p.options), ("Which?", ("b", "a", "c")))
        self.assertEqual(p.tally(), {"b": 0, "a": 0, "c": 0})
        self.assertEqual(list(p.tally()), ["b", "a", "c"])
        self.assertEqual((p.winner(), p.total(), p.voters(), p.report()), (None, 0, [], "b: 0\\na: 0\\nc: 0\\n"))

    def test_base_vote_rules(self):
        p = make_poll()
        before = (p.tally(), p.voters(), p.total())
        for voter, choice in [("", "pizza"), ("  ", "pizza"), (None, "pizza"), (5, "pizza"), ("fay", "sushi"), ("fay", None),
                              ("fay", ["pizza"]), ("fay", "Pizza"), ("ana", "pizza"), ("ana", "sushi")]:
            with self.assertRaises(ValueError, msg=repr((voter, choice))):
                p.vote(voter, choice)
        with self.assertRaises(TypeError):
            p.vote("fay", "pizza", colour="red")
        with self.assertRaises(ValueError):
            p.vote("ana", "pizza", colour="red")
        self.assertEqual((p.tally(), p.voters(), p.total()), before)
        p.vote("fay", "pizza")
        self.assertEqual(p.tally(), {"pizza": 2, "ramen": 3, "salad": 1})
        self.assertEqual(p.voters()[:2], ["ana", "bob"])

    def test_base_winner_and_report(self):
        p = make_poll([("a", "pizza"), ("b", "ramen"), ("c", "ramen"), ("d", "pizza")])
        self.assertIsNone(p.winner())
        p.vote("e", "salad")
        self.assertIsNone(p.winner())
        p.vote("f", "salad")
        self.assertIsNone(p.winner())
        p.vote("g", "pizza")
        self.assertEqual(p.winner(), "pizza")
        self.assertEqual(p.report(), "pizza: 3\\nramen: 2\\nsalad: 2\\n")
        self.assertEqual(p.voters(), ["a", "b", "c", "d", "e", "f", "g"])
        self.assertIsNone(make_poll([]).winner())
        self.assertEqual(make_poll([("a", "salad")]).winner(), "salad")
    @@blocks tests
'''


def ref_irv(options, ballots, elim_last):
    """Independent reference for instant-runoff counting. ballots: list of (ranking, weight)."""
    remaining = list(options)
    rounds = []
    while True:
        counts = {o: 0 for o in remaining}
        active = 0
        for ranking, w in ballots:
            for o in ranking:
                if o in counts:
                    counts[o] += w
                    active += w
                    break
        rounds.append(dict(counts))
        if active == 0:
            return None, rounds
        top = max(counts.values())
        if top * 2 > active:
            return [o for o in remaining if counts[o] == top][0], rounds
        low = min(counts.values())
        tied = [o for o in remaining if counts[o] == low]
        remaining.remove(tied[-1] if elim_last else tied[0])


def make_slices(rng: random.Random):
    modes = rng.choice([("none", "listed", "first-vote"), ("none", "order", "earliest")])
    max_w = rng.choice([5, 10])
    elim_last = rng.choice([True, False])
    elim_word = "the one listed last in `poll.options`" if elim_last else "the one listed first in `poll.options`"
    S = []

    S.append(Slice(
        id="change-vote", title="Changing a vote", d=1,
        pitch=("Residents click the wrong option and then have to ask the organiser to delete their ballot by hand.",
               "A voter who made a mistake needs to be able to correct the vote."),
        reqs=("`poll.change(voter, choice)` replaces the vote of a voter who has already voted. The choice must be an option (`ValueError`, checked first); a voter without a vote is a `KeyError`. A failed call changes nothing. Unknown keyword options raise `TypeError`.",
              "A changed vote counts as if it had been cast at the moment of the change, and it is a plain single-choice vote."),
        code={
            "pollroom/poll.py::methods": '''
                def change(self, voter, choice, **opts):
                    old = self._ballots.get(voter)
                    if choice not in self.options:
                        raise ValueError(f"unknown option: {choice!r}")
                    if old is None:
                        raise KeyError(f"{voter} has not voted")
                    @@slot change_opts
                    del self._ballots[voter]
                    try:
                        self._cast(voter, (choice,), opts)
                    except Exception:
                        self._ballots[voter] = old
                        raise
            ''',
        },
        readme="## Changing a vote\n\n`poll.change(voter, choice)` replaces an existing vote (`ValueError` for an unknown option, `KeyError` for a voter who has not voted). A changed vote counts as cast at the time of the change.\n",
        vtests='''
            def test_change_basic(self):
                p = make_poll()
                p.change("ana", "salad")
                self.assertEqual(p.tally()["salad"], 2)
        ''',
        tests='''
            def test_change_vote(self):
                p = make_poll()
                p.change("ana", "salad")
                p.change("bob", "salad")
                self.assertEqual(p.tally(), {"pizza": 0, "ramen": 2, "salad": 3})
                self.assertEqual(p.winner(), "salad")
                self.assertEqual((p.total(), len(p.voters())), (5, 5))
                p.change("ana", "salad")
                self.assertEqual(p.tally()["salad"], 3)

            def test_change_errors(self):
                p = make_poll()
                before = p.tally()
                with self.assertRaises(KeyError):
                    p.change("zed", "pizza")
                with self.assertRaises(ValueError):
                    p.change("ana", "sushi")
                with self.assertRaises(ValueError):
                    p.change("zed", "sushi")
                with self.assertRaises(TypeError):
                    p.change("ana", "pizza", colour="red")
                self.assertEqual(p.tally(), before)
                self.assertEqual(p.voters(), ["ana", "bob", "cy", "dee", "eli"])
        ''',
    ))

    S.append(Slice(
        id="retract", title="Retracting a vote", d=1,
        pitch=("A resident moved out before the poll closed and their vote still counts.",
               "Voters need to be able to withdraw their vote."),
        reqs=("`poll.retract(voter)` removes the vote of a voter and returns the option that voter had chosen (for a ballot with several preferences: the first one). A voter without a vote is a `KeyError`. After a retraction the voter may vote again.",),
        code={
            "pollroom/poll.py::methods": '''
                def retract(self, voter):
                    ballot = self._ballots.pop(voter, None)
                    if ballot is None:
                        raise KeyError(f"{voter} has not voted")
                    return ballot.choice
            ''',
        },
        readme="## Retracting a vote\n\n`poll.retract(voter)` removes a vote and returns the option that had been chosen; `KeyError` for a voter without a vote. The voter may vote again afterwards.\n",
        vtests='''
            def test_retract_basic(self):
                p = make_poll()
                self.assertEqual(p.retract("ana"), "ramen")
                self.assertEqual(p.total(), 4)
        ''',
        tests='''
            def test_retract(self):
                p = make_poll()
                self.assertEqual(p.retract("bob"), "pizza")
                self.assertEqual(p.tally(), {"pizza": 0, "ramen": 3, "salad": 1})
                self.assertEqual(p.voters(), ["ana", "cy", "dee", "eli"])
                with self.assertRaises(KeyError):
                    p.retract("bob")
                with self.assertRaises(KeyError):
                    p.retract("nobody")
                p.vote("bob", "salad")
                self.assertEqual(p.tally()["salad"], 2)
                self.assertEqual(p.retract("bob"), "salad")
                for voter in list(p.voters()):
                    p.retract(voter)
                self.assertEqual((p.total(), p.winner(), p.voters()), (0, None, []))
        ''',
    ))

    S.append(Slice(
        id="quorum", title="Quorum", d=2,
        pitch=("A poll with two voters out of two hundred was declared decided.",
               "A poll should only have a winner once enough people have voted."),
        reqs=("`Poll(..., quorum=1)` takes a new option `quorum`, an integer of at least 1 (anything else, `bool` included, is a `ValueError`); `poll.quorum` returns it and `poll.has_quorum()` says whether `poll.total()` has reached it.",
              "`poll.winner()` returns `None` while the quorum is not reached, however clear the lead is."),
        code={
            "pollroom/poll.py::init_opts": '''
                quorum = opts.pop("quorum", 1)
                if not isinstance(quorum, int) or isinstance(quorum, bool) or quorum < 1:
                    raise ValueError("quorum must be an integer of at least 1")
            ''',
            "pollroom/poll.py::init": "self.quorum = quorum",
            "pollroom/poll.py::winner_pre": '''
                if not self.has_quorum():
                    return None
            ''',
            "pollroom/poll.py::methods": '''
                def has_quorum(self):
                    return self.total() >= self.quorum
            ''',
        },
        readme="## Quorum\n\n`Poll(..., quorum=N)` (integer >= 1, default 1): `poll.quorum`, `poll.has_quorum()` and a `winner()` that stays `None` until the total has reached the quorum.\n",
        vtests='''
            def test_quorum_basic(self):
                p = make_poll(quorum=6)
                self.assertFalse(p.has_quorum())
        ''',
        tests='''
            def test_quorum(self):
                self.assertEqual(make_poll().quorum, 1)
                p = make_poll(quorum=5)
                self.assertEqual((p.quorum, p.has_quorum(), p.winner()), (5, True, "ramen"))
                q = make_poll(quorum=6)
                self.assertEqual((q.has_quorum(), q.winner()), (False, None))
                q.vote("fay", "ramen")
                self.assertEqual((q.has_quorum(), q.winner()), (True, "ramen"))
                self.assertEqual(q.tally()["ramen"], 4)
                empty = make_poll([])
                self.assertEqual((empty.has_quorum(), empty.winner()), (False, None))
                one = make_poll([("a", "salad")], quorum=1)
                self.assertEqual((one.has_quorum(), one.winner()), (True, "salad"))

            def test_quorum_validation(self):
                for bad in [0, -1, 2.5, "3", None, True]:
                    with self.assertRaises(ValueError, msg=repr(bad)):
                        make_poll(quorum=bad)
                with self.assertRaises(TypeError):
                    make_poll(quorom=3)
        ''',
        cross={
            "retract": {
                "reqs": ("A retraction can take the poll below the quorum again.",),
                "tests": '''
                    def test_retract_can_lose_the_quorum(self):
                        p = make_poll(quorum=5)
                        p.retract("ana")
                        self.assertEqual((p.has_quorum(), p.winner()), (False, None))
                        p.vote("ana", "ramen")
                        self.assertEqual(p.winner(), "ramen")
                '''},
            "weights": {
                "reqs": ("The quorum is measured in total weight (`poll.total()`).",),
                "tests": '''
                    def test_quorum_counts_weight(self):
                        p = make_poll([("a", "pizza")], quorum=4)
                        self.assertIsNone(p.winner())
                        p.vote("b", "pizza", weight=3)
                        self.assertEqual((p.total(), p.has_quorum(), p.winner()), (4, True, "pizza"))
                '''},
        },
    ))

    m_none, m_listed, m_first = modes
    S.append(Slice(
        id="tiebreak", title="Tie-breaks", d=3,
        pitch=("The block party poll ended 12 to 12 and nobody could say which date had won.",
               "Polls need a rule that settles a tie for first place."),
        reqs=(f"`Poll(..., tiebreak=\"{m_none}\")` takes a new option `tiebreak`: `\"{m_none}\"` (the default, a tie has no winner, as before), `\"{m_listed}\"` (the tied option that is listed first in `poll.options` wins) or `\"{m_first}\"` (the tied option whose earliest remaining ballot was cast first wins). Anything else is a `ValueError`; `poll.tiebreak` returns the mode.",
              "The rule only decides ties for the top place in `winner()`; `tally()` is not affected. A vote that was changed counts as cast at the time of the change."),
        code={
            "pollroom/poll.py::init_opts": f'''
                tiebreak = opts.pop("tiebreak", "{m_none}")
                if tiebreak not in ("{m_none}", "{m_listed}", "{m_first}"):
                    raise ValueError(f"unknown tiebreak: {{tiebreak!r}}")
            ''',
            "pollroom/poll.py::init": "self.tiebreak = tiebreak",
            "pollroom/poll.py::tie_rule": f'''
                if self.tiebreak == "{m_listed}":
                    return leaders[0]
                if self.tiebreak == "{m_first}":
                    first = {{o: min(b.seq for b in self._ballots.values() if b.choice == o) for o in leaders}}
                    return min(leaders, key=lambda o: first[o])
                return None
            ''',
        },
        readme=f"## Tie-breaks\n\n`Poll(..., tiebreak=...)`: `\"{m_none}\"` (default: ties have no winner), `\"{m_listed}\"` (first listed wins) or `\"{m_first}\"` (the tied option whose earliest ballot came first wins).\n",
        vtests=fmt('''
            def test_tiebreak_basic(self):
                p = make_poll([("a", "pizza"), ("b", "ramen")], tiebreak="__L__")
                self.assertEqual(p.winner(), "pizza")
        ''', L=m_listed),
        tests=fmt('''
            def test_tiebreak_modes(self):
                votes = [("a", "salad"), ("b", "ramen"), ("c", "pizza"), ("d", "ramen"), ("e", "salad")]
                self.assertIsNone(make_poll(votes).winner())
                self.assertIsNone(make_poll(votes, tiebreak="__N__").winner())
                self.assertEqual(make_poll(votes, tiebreak="__L__").winner(), "ramen")
                self.assertEqual(make_poll(votes, tiebreak="__F__").winner(), "salad")
                p = make_poll(votes, tiebreak="__F__")
                self.assertEqual((p.tiebreak, make_poll().tiebreak), ("__F__", "__N__"))
                self.assertEqual(p.tally(), {"pizza": 1, "ramen": 2, "salad": 2})

            def test_tiebreak_only_matters_for_ties(self):
                for mode in ("__N__", "__L__", "__F__"):
                    p = make_poll(tiebreak=mode)
                    self.assertEqual(p.winner(), "ramen")
                    empty = make_poll([], tiebreak=mode)
                    self.assertIsNone(empty.winner())
                three = [("a", "ramen"), ("b", "salad"), ("c", "pizza")]
                self.assertEqual(make_poll(three, tiebreak="__L__").winner(), "pizza")
                self.assertEqual(make_poll(three, tiebreak="__F__").winner(), "ramen")

            def test_tiebreak_validation(self):
                for bad in ["", "random", None, 1, "None"]:
                    with self.assertRaises(ValueError, msg=repr(bad)):
                        make_poll(tiebreak=bad)
        ''', N=m_none, L=m_listed, F=m_first),
        cross={
            "change-vote": {"tests": fmt('''
                def test_changed_votes_count_as_new(self):
                    p = make_poll([("a", "pizza"), ("b", "ramen")], tiebreak="__F__")
                    self.assertEqual(p.winner(), "pizza")
                    p.change("a", "pizza")
                    self.assertEqual(p.winner(), "ramen")
                    q = make_poll([("a", "pizza"), ("b", "ramen"), ("c", "salad")], tiebreak="__F__")
                    q.change("a", "salad")
                    q.change("c", "ramen")
                    self.assertEqual(q.tally(), {"pizza": 0, "ramen": 2, "salad": 1})
                    self.assertEqual(q.winner(), "ramen")
            ''', F=m_first)},
            "retract": {"tests": fmt('''
                def test_retract_changes_the_first_vote(self):
                    p = make_poll([("a", "pizza"), ("b", "ramen"), ("c", "ramen"), ("d", "pizza")], tiebreak="__F__")
                    self.assertEqual(p.winner(), "pizza")
                    p.retract("a")
                    p.vote("e", "pizza")
                    self.assertEqual(p.winner(), "ramen")
            ''', F=m_first)},
            "weights": {
                "reqs": ("Ties are decided on the weighted counts.",),
                "tests": fmt('''
                    def test_tiebreak_on_weighted_counts(self):
                        p = make_poll([("a", "pizza"), ("b", "ramen")], tiebreak="__L__")
                        p.vote("c", "ramen", weight=2)
                        p.vote("d", "pizza", weight=2)
                        self.assertEqual(p.winner(), "pizza")
                        p.vote("e", "ramen")
                        self.assertEqual(p.winner(), "ramen")
                ''', L=m_listed)},
        },
    ))

    S.append(Slice(
        id="weights", title="Weighted votes", d=3,
        pitch=("Board members' votes should count for more than a visitor's in the association's polls.",
               "Some voters carry more weight than others."),
        reqs=(f"`poll.vote(voter, choice, weight=1)` takes a new keyword `weight`, an integer from 1 to {max_w} (`bool` and anything else is a `ValueError`; checked after the other `ValueError` checks of `vote`). `tally()`, `total()` and `winner()` count weights instead of ballots, so `total()` is the sum of the weights.",
              "`poll.voters()` is not affected."),
        code={
            "pollroom/poll.py::ballot_fields": "weight: int = 1",
            "pollroom/poll.py::cast_opts": f'''
                weight = opts.pop("weight", 1)
                if not isinstance(weight, int) or isinstance(weight, bool) or not 1 <= weight <= {max_w}:
                    raise ValueError("weight must be an integer from 1 to {max_w}")
            ''',
            "pollroom/poll.py::ballot_extra": 'extra["weight"] = weight',
            "pollroom/poll.py::weight_method": '''
                def _weight(self, ballot):
                    return ballot.weight
            ''',
        },
        readme=f"## Weighted votes\n\n`poll.vote(voter, choice, weight=1)` with a weight from 1 to {max_w}; `tally()`, `total()` and `winner()` count weights.\n",
        vtests='''
            def test_weight_basic(self):
                p = make_poll()
                p.vote("fay", "pizza", weight=4)
                self.assertEqual(p.tally()["pizza"], 5)
        ''',
        tests=fmt('''
            def test_weighted_counts(self):
                p = make_poll()
                p.vote("fay", "pizza", weight=2)
                p.vote("gus", "salad", weight=__M__)
                self.assertEqual(p.tally(), {"pizza": 3, "ramen": 3, "salad": 1 + __M__})
                self.assertEqual(p.total(), 5 + 2 + __M__)
                self.assertEqual(p.winner(), "salad")
                self.assertEqual(len(p.voters()), 7)
                self.assertEqual(p.report(), f"pizza: 3\\nramen: 3\\nsalad: {1 + __M__}\\n")

            def test_weight_validation(self):
                p = make_poll()
                before = p.tally()
                for bad in [0, -1, __M__ + 1, 1.5, "2", None, True]:
                    with self.assertRaises(ValueError, msg=repr(bad)):
                        p.vote("fay", "pizza", weight=bad)
                with self.assertRaises(ValueError):
                    p.vote("ana", "pizza", weight=1)
                with self.assertRaises(ValueError):
                    p.vote("fay", "sushi", weight=0)
                with self.assertRaises(TypeError):
                    p.vote("fay", "pizza", weight=2, colour="red")
                self.assertEqual(p.tally(), before)
                p.vote("fay", "pizza", weight=__M__)
                self.assertEqual(p.tally()["pizza"], 1 + __M__)
        ''', M=max_w),
        cross={
            "change-vote": {
                "reqs": ("`change(voter, choice)` keeps the weight of the old vote unless a new `weight` keyword is given.",),
                "code": {"pollroom/poll.py::change_opts": 'opts.setdefault("weight", old.weight)'},
                "tests": '''
                    def test_change_keeps_the_weight(self):
                        p = make_poll()
                        p.vote("fay", "pizza", weight=3)
                        p.change("fay", "salad")
                        self.assertEqual(p.tally(), {"pizza": 1, "ramen": 3, "salad": 4})
                        p.change("fay", "ramen", weight=2)
                        self.assertEqual(p.tally(), {"pizza": 1, "ramen": 5, "salad": 1})
                        with self.assertRaises(ValueError):
                            p.change("fay", "pizza", weight=0)
                        self.assertEqual(p.tally(), {"pizza": 1, "ramen": 5, "salad": 1})
                '''},
            "retract": {"tests": '''
                def test_retract_removes_the_weight(self):
                    p = make_poll()
                    p.vote("fay", "pizza", weight=3)
                    p.retract("fay")
                    self.assertEqual((p.tally()["pizza"], p.total()), (1, 5))
            '''},
        },
    ))

    S.append(Slice(
        id="shares", title="Percentage shares", d=3,
        pitch=("The newsletter prints the results as percentages and the rounded numbers add up to 99 or 101.",
               "Results should be shown as whole percentages that always add up to 100."),
        reqs=("`poll.shares()` returns a dict with every option in option order and its share of the vote as a whole percentage. The exact share is `count * 100 / total`; every option first gets the rounded-down value and the points still missing from 100 go, one each, to the options with the largest fractional part (ties: the option listed first). The shares always add up to exactly 100. A poll without votes gives 0 for every option.",),
        code={
            "pollroom/poll.py::methods": '''
                def shares(self):
                    counts = self.tally()
                    total = sum(counts.values())
                    if total == 0:
                        return {o: 0 for o in self.options}
                    shares = {o: counts[o] * 100 // total for o in self.options}
                    order = sorted(self.options, key=lambda o: (-(counts[o] * 100 % total), self.options.index(o)))
                    for o in order[: 100 - sum(shares.values())]:
                        shares[o] += 1
                    return shares
            ''',
        },
        readme="## Percentage shares\n\n`poll.shares()` gives whole percentages that add up to 100: rounded down first, the remaining points go to the largest fractional parts (ties: listed first). No votes: all zeros.\n",
        vtests='''
            def test_shares_basic(self):
                p = make_poll()
                self.assertEqual(sum(p.shares().values()), 100)
        ''',
        tests='''
            def test_shares(self):
                self.assertEqual(make_poll().shares(), {"pizza": 20, "ramen": 60, "salad": 20})
                thirds = make_poll([("a", "pizza"), ("b", "ramen"), ("c", "salad")])
                self.assertEqual(thirds.shares(), {"pizza": 34, "ramen": 33, "salad": 33})
                seven = make_poll([("a", "pizza"), ("b", "pizza"), ("c", "ramen"), ("d", "ramen"), ("e", "salad"), ("f", "salad"), ("g", "salad")])
                self.assertEqual(seven.shares(), {"pizza": 29, "ramen": 28, "salad": 43})
                self.assertEqual(make_poll([]).shares(), {"pizza": 0, "ramen": 0, "salad": 0})
                self.assertEqual(make_poll([("a", "salad")]).shares(), {"pizza": 0, "ramen": 0, "salad": 100})

            def test_shares_always_add_up(self):
                votes = [("v%d" % i, ["pizza", "ramen", "salad"][(i * i + i // 3) % 3]) for i in range(1, 30)]
                for n in range(1, len(votes) + 1):
                    p = make_poll(votes[:n])
                    s = p.shares()
                    self.assertEqual(sum(s.values()), 100, n)
                    self.assertEqual(list(s), ["pizza", "ramen", "salad"])
                    tally = p.tally()
                    for o in s:
                        self.assertTrue(abs(s[o] * n - tally[o] * 100) < n, (n, o))
        ''',
        cross={
            "weights": {"tests": '''
                def test_shares_use_weights(self):
                    p = make_poll([("a", "pizza"), ("b", "ramen")])
                    p.vote("c", "salad", weight=2)
                    self.assertEqual(p.shares(), {"pizza": 25, "ramen": 25, "salad": 50})
                    p.vote("d", "pizza", weight=3)
                    self.assertEqual(p.shares(), {"pizza": 57, "ramen": 14, "salad": 29})
            '''},
        },
    ))

    # reference data for the ranked-ballot slice
    options = ["pizza", "ramen", "salad"]
    ballots = [
        ("ana", ["ramen", "pizza"]), ("bob", ["pizza", "salad"]), ("cy", ["ramen", "salad"]), ("dee", ["salad", "pizza"]),
        ("eli", ["salad", "ramen"]), ("fay", ["pizza"]), ("gus", ["ramen", "pizza", "salad"]),
    ]
    win, rounds = ref_irv(options, [(r, 1) for _, r in ballots], elim_last)
    wballots = [(r, w) for (_, r), w in zip(ballots, [1, 1, 1, 1, 1, 1, 1])]
    wwin, wrounds = ref_irv(options, [(r, (3 if v == "dee" else 1)) for v, r in ballots], elim_last)
    # a poll where a later round decides: 4 options listed a, b, c, d
    four = ["north", "south", "east", "west"]
    four_ballots = [
        (["north", "east"], 1), (["north", "east"], 1), (["south", "east", "north"], 1), (["south", "west"], 1),
        (["east", "south"], 1), (["east", "west", "north"], 1), (["west", "south", "east"], 1), (["west"], 1), (["west", "north"], 1),
    ]
    fwin, frounds = ref_irv(four, four_ballots, elim_last)
    cast = "\n                ".join(f'p.rank_vote("{v}", {r!r})' for v, r in ballots)
    four_cast = "\n                ".join(f'q.rank_vote("v{i}", {r!r})' for i, (r, _) in enumerate(four_ballots))

    S.append(Slice(
        id="ranked", title="Ranked ballots and instant runoff", d=4,
        pitch=("Three candidates split the vote and the winner got 38 percent, so people want to rank their choices.",
               "The association wants to run polls where voters rank their preferences."),
        reqs=("`poll.rank_vote(voter, ranking)` records a ballot with several preferences: `ranking` is a list or tuple of 1 to len(options) different options, best first. It follows the rules of `vote` (the voter check, then the options, then \"already voted\"; a ranking with an option twice, an empty ranking or an unknown option is a `ValueError`), and in `tally()`, `winner()` and the other readers a ranked ballot counts for its first preference.",
              f"`poll.instant_runoff()` returns a `Runoff` (new class in `pollroom/runoff.py`, exported from the package) with `winner` and `rounds`. Counting works in rounds: in each round every ballot counts for its best-ranked option that has not been eliminated (ballots with no such option are exhausted and ignored), and `rounds` gets a dict with the counts of all remaining options in option order. If an option has more than half of the counted ballots it wins. Otherwise the option with the fewest counted ballots is eliminated; if several are tied for fewest, {elim_word} among them is eliminated. With no ballots at all `winner` is `None` and `rounds` holds the single all-zero round."),
        files={
            "pollroom/runoff.py": f'''\
"""Instant-runoff counting."""
from dataclasses import dataclass, field


@dataclass
class Runoff:
    winner: object
    rounds: list = field(default_factory=list)


def count(poll):
    remaining = list(poll.options)
    rounds = []
    while True:
        counts = {{o: 0 for o in remaining}}
        counted = 0
        for ballot in poll._ballots.values():
            for o in ballot.ranking:
                if o in counts:
                    w = poll._weight(ballot)
                    counts[o] += w
                    counted += w
                    break
        rounds.append(dict(counts))
        if counted == 0:
            return Runoff(None, rounds)
        top = max(counts.values())
        if top * 2 > counted:
            return Runoff(next(o for o in remaining if counts[o] == top), rounds)
        fewest = min(counts.values())
        tied = [o for o in remaining if counts[o] == fewest]
        remaining.remove(tied[{-1 if elim_last else 0}])
''',
        },
        code={
            "pollroom/__init__.py::exports": "from .runoff import Runoff",
            "pollroom/poll.py::methods": '''
                def rank_vote(self, voter, ranking, **opts):
                    ranking = tuple(ranking)
                    if not ranking:
                        raise ValueError("a ranking needs at least one option")
                    self._cast(voter, ranking, opts)

                def instant_runoff(self):
                    from .runoff import count

                    return count(self)
            ''',
        },
        readme=f"## Ranked ballots and instant runoff\n\n`poll.rank_vote(voter, ranking)` records several preferences (a ballot counts for its first preference everywhere else). `poll.instant_runoff()` returns a `Runoff(winner, rounds)`: ballots count for their best remaining option, more than half wins, otherwise the option with the fewest ballots is eliminated (on ties {elim_word}).\n",
        vtests='''
            def test_rank_vote_basic(self):
                p = make_poll([])
                p.rank_vote("ana", ["ramen", "pizza"])
                self.assertEqual(p.tally()["ramen"], 1)
        ''',
        tests=fmt('''
            def ranked_poll(self):
                p = make_poll([])
                __CAST__
                return p

            def test_first_preferences_count_everywhere_else(self):
                p = self.ranked_poll()
                self.assertEqual(p.tally(), {"pizza": 2, "ramen": 3, "salad": 2})
                self.assertEqual((p.winner(), p.total()), ("ramen", 7))
                self.assertEqual(p.voters(), ["ana", "bob", "cy", "dee", "eli", "fay", "gus"])
                p.vote("hal", "pizza")
                self.assertEqual(p.tally()["pizza"], 3)

            def test_instant_runoff(self):
                r = self.ranked_poll().instant_runoff()
                self.assertEqual(r.winner, __WIN__)
                self.assertEqual(r.rounds, __ROUNDS__)
                from pollroom import Runoff
                self.assertIsInstance(r, Runoff)

            def test_runoff_with_more_rounds(self):
                q = Poll("Where?", __FOUR__)
                __FOURCAST__
                r = q.instant_runoff()
                self.assertEqual(r.winner, __FWIN__)
                self.assertEqual(r.rounds, __FROUNDS__)

            def test_runoff_edge_cases(self):
                empty = make_poll([])
                r = empty.instant_runoff()
                self.assertEqual((r.winner, r.rounds), (None, [{"pizza": 0, "ramen": 0, "salad": 0}]))
                one = make_poll([])
                one.rank_vote("a", ["salad", "pizza"])
                r = one.instant_runoff()
                self.assertEqual((r.winner, r.rounds), ("salad", [{"pizza": 0, "ramen": 0, "salad": 1}]))
                plain = make_poll()
                r = plain.instant_runoff()
                self.assertEqual((r.winner, len(r.rounds)), ("ramen", 1))
                tied = make_poll([("a", "pizza"), ("b", "ramen")])
                r = tied.instant_runoff()
                self.assertEqual(r.winner, __TIEWIN__)
                self.assertEqual(r.rounds[0], {"pizza": 1, "ramen": 1, "salad": 0})
                self.assertEqual(len(r.rounds), 3)

            def test_rank_vote_validation(self):
                p = make_poll([])
                p.rank_vote("ana", ("ramen",))
                before = p.tally()
                for voter, ranking in [("fay", []), ("fay", ()), ("fay", ["ramen", "ramen"]), ("fay", ["sushi"]), ("fay", ["ramen", "sushi"]),
                                       ("", ["ramen"]), (None, ["ramen"]), ("ana", ["pizza"]), ("fay", "ramen")]:
                    with self.assertRaises(ValueError, msg=repr((voter, ranking))):
                        p.rank_vote(voter, ranking)
                with self.assertRaises(TypeError):
                    p.rank_vote("fay", ["ramen"], colour="red")
                self.assertEqual(p.tally(), before)
                p.rank_vote("fay", ["pizza", "ramen", "salad"])
                self.assertEqual(p.voters(), ["ana", "fay"])
        ''', CAST=cast, WIN=repr(win), ROUNDS=repr(rounds), FOUR=repr(four), FOURCAST=four_cast, FWIN=repr(fwin), FROUNDS=repr(frounds),
            TIEWIN=repr(ref_irv(options, [(["pizza"], 1), (["ramen"], 1)], elim_last)[0])),
        cross={
            "change-vote": {
                "reqs": ("`change` replaces a ranked ballot by a single-choice vote.",),
                "tests": '''
                    def test_change_replaces_a_ranking(self):
                        p = make_poll([])
                        p.rank_vote("ana", ["ramen", "pizza", "salad"])
                        p.rank_vote("bob", ["salad", "pizza"])
                        p.change("ana", "pizza")
                        r = p.instant_runoff()
                        self.assertEqual(p.tally(), {"pizza": 1, "ramen": 0, "salad": 1})
                        self.assertEqual(r.rounds[0], {"pizza": 1, "ramen": 0, "salad": 1})
                '''},
            "retract": {"tests": '''
                def test_retract_returns_the_first_preference(self):
                    p = make_poll([])
                    p.rank_vote("ana", ["salad", "pizza"])
                    self.assertEqual(p.retract("ana"), "salad")
                    self.assertEqual(p.instant_runoff().winner, None)
            '''},
            "weights": {
                "reqs": ("Weights count in every round of the runoff.",),
                "tests": fmt('''
                    def test_runoff_uses_weights(self):
                        heavy = Poll("Lunch?", ["pizza", "ramen", "salad"])
                        for voter, ranking in [__PAIRS__]:
                            heavy.rank_vote(voter, ranking, weight=3 if voter == "dee" else 1)
                        r = heavy.instant_runoff()
                        self.assertEqual(r.winner, __WWIN__)
                        self.assertEqual(r.rounds, __WROUNDS__)
                ''', PAIRS=", ".join(f'("{v}", {r!r})' for v, r in ballots), WWIN=repr(wwin), WROUNDS=repr(wrounds))},
            "tiebreak": {"tests": '''
                def test_runoff_does_not_use_the_tiebreak_option(self):
                    p = make_poll([], tiebreak="%s")
                    p.rank_vote("a", ["pizza"])
                    p.rank_vote("b", ["ramen"])
                    self.assertEqual(len(p.instant_runoff().rounds), 3)
            ''' % m_first},
        },
    ))

    return S


APP = App(
    name="pollroom", lang="python", title="the polling library", role="the residents' association secretary", key="POLL",
    base={
        "README.md": README + "\n@@blocks features\n",
        "pollroom/__init__.py": INIT,
        "pollroom/poll.py": POLL,
        ".gitignore": "__pycache__/\n*.pyc\n",
    },
    visible={"tests/test_basic.py": VISIBLE},
    hidden={"tests/test_features.py": HIDDEN},
)

register_app("feature-py-pollroom", APP, make_slices, n=18, summary="residents' polls: changed votes, quorum, tie-breaks, weights, shares, ranked ballots")
