"""seedswap (python): a seed-swap packet catalogue extended with filters, sorting, formats, paging, audit, hooks, holds."""
import random
import textwrap

from fx import dd
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # seedswap

    A small catalogue for a community seed swap: which packets are on the shelves, how many are left and how well
    they should germinate. Python 3, standard library only.

    ## Layout

    * `seedswap/catalog.py`: `Packet` and `Catalog` (the data and the rules).
    * `seedswap/render.py`: output formats for lists of packets (`FORMATS` maps a name to a function).
    * `seedswap/cli.py`: the command line (`python -m seedswap --db seeds.json <command>`).
    * `tests/`: unit tests, run with `python3 -m unittest discover -s tests`.

    ## Basics

    A `Packet` has `id`, `species`, `variety`, `qty` (units left, always positive while it is on the shelf),
    `harvested` (a `date`), `germ_pct` (0-100, default 80) and `shelf` (default `A1`).

    * `Catalog.add(packet)`: `ValueError` for a duplicate id or `qty <= 0`.
    * `Catalog.get(id)` / `Catalog.remove(id)`: `KeyError` for an unknown id; `remove` returns the packet.
    * `Catalog.take(id, n)`: hands out `n` units and returns how many are left; `ValueError` unless `0 < n <= qty`.
      A packet that reaches zero is removed from the catalogue.
    * `Catalog.packets()`: all packets ordered by id.
    * `Catalog.query(**options)`: packets (ordered by id) that match the options. Unknown options raise `TypeError`.
    * `Catalog.to_dict()` / `Catalog.from_dict(d)`: the JSON-able form that the command line stores in `--db`.

    The command line has `list`, `add`, `take` and `remove`; errors are printed to stderr as `seedswap: <message>`
    with exit status 2. `list` prints a text table (`--format table`, the default): a header row, then one row per
    packet, columns separated by two spaces.
''')

CATALOG = '''\
"""The packet catalogue: what is on the shelves of the seed swap."""
from dataclasses import dataclass
from datetime import date
@@uniq imports


@dataclass
class Packet:
    id: str
    species: str
    variety: str
    qty: int
    harvested: date
    germ_pct: int = 80
    shelf: str = "A1"

    def to_dict(self):
        return {
            "id": self.id,
            "species": self.species,
            "variety": self.variety,
            "qty": self.qty,
            "harvested": self.harvested.isoformat(),
            "germ_pct": self.germ_pct,
            "shelf": self.shelf,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(d["id"], d["species"], d["variety"], int(d["qty"]), date.fromisoformat(d["harvested"]),
                   int(d.get("germ_pct", 80)), d.get("shelf", "A1"))

@@blocks classes

class Catalog:
    def __init__(self):
        self._packets = {}
        @@slot init

    def add(self, packet):
        if packet.id in self._packets:
            raise ValueError(f"duplicate packet id: {packet.id}")
        if packet.qty <= 0:
            raise ValueError("quantity must be positive")
        self._packets[packet.id] = packet
        @@slot on_add

    def get(self, pid):
        try:
            return self._packets[pid]
        except KeyError:
            raise KeyError(f"no such packet: {pid}") from None

    def remove(self, pid):
        packet = self.get(pid)
        del self._packets[pid]
        @@slot on_remove
        return packet

    @@default take_sig
    def take(self, pid, n):
    @@end
        packet = self.get(pid)
        @@default take_check
        if n <= 0 or n > packet.qty:
            raise ValueError(f"cannot take {n} from {pid} (have {packet.qty})")
        @@end
        packet.qty -= n
        left = packet.qty
        if left == 0:
            del self._packets[pid]
        @@slot on_take
        return left

    def packets(self):
        return [self._packets[k] for k in sorted(self._packets)]

    def query(self, **opts):
        rows = self.packets()
        @@slot query
        if opts:
            raise TypeError("unknown option(s): " + ", ".join(sorted(opts)))
        return rows

    @@blocks methods

    def to_dict(self):
        d = {"packets": [p.to_dict() for p in self.packets()]}
        @@slot to_dict
        return d

    @classmethod
    def from_dict(cls, d):
        cat = cls()
        for item in d.get("packets", []):
            cat._packets[item["id"]] = Packet.from_dict(item)
        @@slot from_dict
        return cat
'''

RENDER = '''\
"""Output formats for lists of packets."""
@@uniq imports

COLUMNS = ["id", "species", "variety", "qty", "harvested", "germ_pct", "shelf"]


@@default table_sig
def table(rows):
@@end
    """Plain aligned text: a header row, then one row per packet, two spaces between columns."""
    @@default table_cells
    header = list(COLUMNS)
    cells = [[p.harvested.isoformat() if c == "harvested" else str(getattr(p, c)) for c in COLUMNS] for p in rows]
    @@end
    widths = [max([len(h)] + [len(r[i]) for r in cells]) for i, h in enumerate(header)]
    lines = ["  ".join(h.ljust(w) for h, w in zip(header, widths)).rstrip()]
    for r in cells:
        lines.append("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip())
    return "\\n".join(lines) + "\\n"

@@blocks renderers

FORMATS = {"table": table}
@@slot formats
'''

CLI = '''\
"""Command line front end: python -m seedswap --db seeds.json <command>."""
import argparse
import json
import os
import sys
from datetime import date
@@uniq imports

from . import render
from .catalog import Catalog, Packet


def load(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return Catalog.from_dict(json.load(f))
    return Catalog()


def save(cat, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cat.to_dict(), f, indent=2, sort_keys=True)
        f.write("\\n")


def build_parser():
    p = argparse.ArgumentParser(prog="seedswap", description="Seed swap catalogue")
    p.add_argument("--db", default="seeds.json", help="catalogue file (default: seeds.json)")
    sub = p.add_subparsers(dest="cmd", required=True)

    ls = sub.add_parser("list", help="show packets")
    ls.add_argument("--format", choices=sorted(render.FORMATS), default="table")
    @@slot list_flags

    add = sub.add_parser("add", help="add a packet")
    add.add_argument("id")
    add.add_argument("species")
    add.add_argument("variety")
    add.add_argument("qty", type=int)
    add.add_argument("harvested", help="YYYY-MM-DD")
    add.add_argument("--germ", type=int, default=80, help="germination percent")
    add.add_argument("--shelf", default="A1")

    take = sub.add_parser("take", help="hand out units of a packet")
    take.add_argument("id")
    take.add_argument("n", type=int)
    @@slot take_flags

    rm = sub.add_parser("remove", help="remove a packet")
    rm.add_argument("id")
    @@slot subcommands
    return p


def cmd_list(args, cat, out):
    opts = {}
    @@slot list_opts
    @@default list_rows
    rows = cat.query(**opts)
    @@end
    @@default list_render
    out.write(render.FORMATS[args.format](rows))
    @@end
    @@slot list_footer
    return 0


def cmd_add(args, cat, out):
    cat.add(Packet(args.id, args.species, args.variety, args.qty, date.fromisoformat(args.harvested), args.germ, args.shelf))
    save(cat, args.db)
    out.write(f"added {args.id}\\n")


def cmd_take(args, cat, out):
    @@slot take_pre
    @@default take_call
    left = cat.take(args.id, args.n)
    @@end
    save(cat, args.db)
    out.write(f"{args.id}: {left} left\\n")


def cmd_remove(args, cat, out):
    cat.remove(args.id)
    save(cat, args.db)
    out.write(f"removed {args.id}\\n")

@@blocks commands

COMMANDS = {"list": cmd_list, "add": cmd_add, "take": cmd_take, "remove": cmd_remove}
@@slot registry


def main(argv=None, out=None):
    out = out if out is not None else sys.stdout
    args = build_parser().parse_args(argv)
    cat = load(args.db)
    try:
        return COMMANDS[args.cmd](args, cat, out) or 0
    except (ValueError, KeyError) as e:
        print(f"seedswap: {e.args[0] if e.args else e}", file=sys.stderr)
        return 2
'''

TEST_HELPERS = '''\
import contextlib
import io
import os
import tempfile
import unittest
from datetime import date
@@uniq imports

from seedswap import cli, render
from seedswap.catalog import Catalog, Packet


def mk(pid, species, variety, qty, harvested, germ=80, shelf="A1"):
    return Packet(pid, species, variety, qty, harvested, germ, shelf)


def stock():
    cat = Catalog()
    cat.add(mk("bean-02", "bean", "Provider", 40, date(2023, 8, 20), 92, "B1"))
    cat.add(mk("kale-01", "Kale", "Red Russian", 25, date(2024, 10, 3), 70, "C2"))
    cat.add(mk("tom-01", "tomato", "Roma", 10, date(2024, 9, 1), 85, "A1"))
    cat.add(mk("tom-02", "Tomato", "Brandywine, pink", 4, date(2022, 9, 14), 60, "A1"))
    cat.add(mk("basil-01", "basil", "Genovese", 12, date(2024, 6, 30), 78, "A2"))
    return cat


def ids(rows):
    return [p.id for p in rows]


class CliCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db = os.path.join(self._tmp.name, "seeds.json")

    def seed(self, cat=None):
        cli.save(cat or stock(), self.db)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err):
            code = cli.main(["--db", self.db, *argv], out=out)
        return code, out.getvalue(), err.getvalue()

    def catalog(self):
        return cli.load(self.db)
'''

VISIBLE = TEST_HELPERS + '''

class BasicTests(CliCase):
    def test_add_get_remove(self):
        cat = Catalog()
        cat.add(mk("a-1", "pea", "Alderman", 5, date(2024, 1, 1)))
        self.assertEqual(cat.get("a-1").variety, "Alderman")
        with self.assertRaises(ValueError):
            cat.add(mk("a-1", "pea", "Other", 5, date(2024, 1, 1)))
        with self.assertRaises(ValueError):
            cat.add(mk("a-2", "pea", "Other", 0, date(2024, 1, 1)))
        self.assertEqual(cat.remove("a-1").id, "a-1")
        with self.assertRaises(KeyError):
            cat.get("a-1")

    def test_take(self):
        cat = stock()
        self.assertEqual(cat.take("tom-01", 4), 6)
        self.assertEqual(cat.take("tom-01", 6), 0)
        with self.assertRaises(KeyError):
            cat.get("tom-01")
        with self.assertRaises(ValueError):
            cat.take("tom-02", 5)

    def test_packets_and_query(self):
        cat = stock()
        self.assertEqual(ids(cat.packets()), ["basil-01", "bean-02", "kale-01", "tom-01", "tom-02"])
        self.assertEqual(ids(cat.query()), ids(cat.packets()))
        with self.assertRaises(TypeError):
            cat.query(colour="red")

    def test_round_trip(self):
        cat = Catalog.from_dict(stock().to_dict())
        self.assertEqual(ids(cat.packets()), ids(stock().packets()))
        self.assertEqual(cat.get("tom-02").harvested, date(2022, 9, 14))

    def test_cli_list_and_take(self):
        self.seed()
        code, out, _ = self.run_cli("list")
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(lines[0].split(), ["id", "species", "variety", "qty", "harvested", "germ_pct", "shelf"])
        self.assertEqual(lines[1].split()[:2], ["basil-01", "basil"])
        code, out, _ = self.run_cli("take", "tom-01", "3")
        self.assertEqual((code, out), (0, "tom-01: 7 left\\n"))
        self.assertEqual(self.catalog().get("tom-01").qty, 7)

    def test_cli_error(self):
        self.seed()
        code, out, err = self.run_cli("take", "nope-1", "1")
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("seedswap: "))
        self.assertEqual(out, "")
    @@blocks tests
'''

HIDDEN = TEST_HELPERS + '''

class FeatureTests(CliCase):
    def test_base_behaviour(self):
        cat = stock()
        self.assertEqual(cat.take("tom-01", 10), 0)
        self.assertEqual(ids(cat.packets()), ["basil-01", "bean-02", "kale-01", "tom-02"])
        code, out, _ = self.run_cli("add", "pea-01", "pea", "Alderman", "5", "2024-02-02", "--germ", "90", "--shelf", "D4")
        self.assertEqual((code, out), (0, "added pea-01\\n"))
        pea = self.catalog().get("pea-01")
        self.assertEqual((pea.species, pea.qty, pea.germ_pct, pea.shelf), ("pea", 5, 90, "D4"))
        code, out, _ = self.run_cli("remove", "pea-01")
        self.assertEqual((code, out), (0, "removed pea-01\\n"))
    @@blocks tests
'''


def _attr_filter(rng):
    v = rng.choice(["species", "shelf", "variety"])
    if v == "species":
        return dict(
            kw="species", title="Species filter", flag="--species",
            rule="`Catalog.query(species=NAME)` returns only the packets whose species equals NAME, compared case-insensitively (`Tomato` matches `tomato`). It is an exact comparison, not a prefix or substring match.",
            readme="`Catalog.query(species=NAME)` keeps packets whose species equals `NAME` ignoring case (exact match, not a substring).",
            cond='p.species.lower() == want', prep='want = opts.pop("species").lower()',
            pitch=("People keep asking to see only the tomatoes, or only the beans, without scrolling the whole shelf.",
                   "Browsing the whole catalogue gets old fast when you only care about one species."),
            value="tomato", ids=["tom-01", "tom-02"], ids_qty=["tom-02", "tom-01"], ids_g80=["tom-01"],
            extra='''
                self.assertEqual(ids(cat.query(species="KALE")), ["kale-01"])
                self.assertEqual(cat.query(species="tom"), [])
                self.assertEqual(cat.query(species="onion"), [])
            ''',
            cli_value="Bean", cli_ids=["bean-02"],
        )
    if v == "shelf":
        return dict(
            kw="shelf", title="Shelf filter", flag="--shelf",
            rule="`Catalog.query(shelf=CODE)` returns only the packets stored on that shelf. Shelf codes are compared exactly, case included (`A1` does not match `a1`).",
            readme="`Catalog.query(shelf=CODE)` keeps packets on that shelf; the comparison is exact and case-sensitive.",
            cond='p.shelf == want', prep='want = opts.pop("shelf")',
            pitch=("Volunteers restocking a shelf want the list for that one shelf.",
                   "When we tidy the swap table we go shelf by shelf; the list should be able to show just one."),
            value="A1", ids=["tom-01", "tom-02"], ids_qty=["tom-02", "tom-01"], ids_g80=["tom-01"],
            extra='''
                self.assertEqual(cat.query(shelf="a1"), [])
                self.assertEqual(ids(cat.query(shelf="B1")), ["bean-02"])
                self.assertEqual(cat.query(shelf="A"), [])
            ''',
            cli_value="C2", cli_ids=["kale-01"],
        )
    return dict(
        kw="variety", title="Variety search", flag="--variety",
        rule="`Catalog.query(variety=TEXT)` returns the packets whose variety contains TEXT as a substring, ignoring case (`pink` finds `Brandywine, pink`).",
        readme="`Catalog.query(variety=TEXT)` keeps packets whose variety contains `TEXT` (substring, case-insensitive).",
        cond='want in p.variety.lower()', prep='want = opts.pop("variety").lower()',
        pitch=("Nobody remembers the exact variety name, they remember a piece of it.",
               "People search for 'pink' or 'Roma' and expect to find the packet."),
        value="ro", ids=["bean-02", "tom-01"], ids_qty=["tom-01", "bean-02"], ids_g80=["bean-02", "tom-01"],
        extra='''
            self.assertEqual(ids(cat.query(variety="PINK")), ["tom-02"])
            self.assertEqual(ids(cat.query(variety="red russian")), ["kale-01"])
            self.assertEqual(cat.query(variety="zzz"), [])
        ''',
        cli_value="pink", cli_ids=["tom-02"],
    )


def make_slices(rng: random.Random):
    low = rng.choice([2, 3, 5])
    per_page = rng.choice([10, 20, 25])
    noun = rng.choice(["history", "ledger"])
    langs = rng.sample([
        ("es", ["id", "especie", "variedad", "cant.", "cosecha", "germ_%", "estante"], "%d/%m/%Y", "dd/mm/yyyy", "14/09/2022"),
        ("fr", ["id", "espèce", "variété", "qté", "récolte", "germ_%", "étagère"], "%d.%m.%Y", "dd.mm.yyyy", "14.09.2022"),
        ("de", ["id", "art", "sorte", "menge", "ernte", "keim_%", "regal"], "%d.%m.%y", "dd.mm.yy", "14.09.22"),
        ("it", ["id", "specie", "varietà", "q.tà", "raccolto", "germ_%", "scaffale"], "%d-%m-%Y", "dd-mm-yyyy", "14-09-2022"),
    ], 2)
    A = _attr_filter(rng)
    kw = A["kw"]
    S = []
    attr_tests = (
        "def test_attr_filter(self):\n"
        "    cat = stock()\n"
        f"    self.assertEqual(ids(cat.query({kw}=\"{A['value']}\")), {A['ids']!r})\n"
        "    self.assertEqual(ids(cat.query()), ids(cat.packets()))\n"
        + textwrap.indent(dd(A["extra"]), "    ") + "\n"
        "def test_attr_filter_cli(self):\n"
        "    self.seed()\n"
        f"    code, out, _ = self.run_cli(\"list\", \"{A['flag']}\", \"{A['cli_value']}\")\n"
        "    self.assertEqual(code, 0)\n"
        f"    self.assertEqual([r.split()[0] for r in out.splitlines()[1:]], {A['cli_ids']!r})\n"
        "    code, out, _ = self.run_cli(\"list\")\n"
        "    self.assertEqual(len(out.splitlines()), 6)\n"
    )

    S.append(Slice(
        id="attr-filter", title=A["title"], d=1,
        pitch=A["pitch"],
        reqs=(A["rule"],
              f"`seedswap list {A['flag']} VALUE` does the same from the command line.",
              "Without the option nothing changes."),
        code={
            "seedswap/catalog.py::query": f'''
                if "{kw}" in opts:
                    {A["prep"]}
                    rows = [p for p in rows if {A["cond"]}]
            ''',
            "seedswap/cli.py::list_flags": f'ls.add_argument("{A["flag"]}", default=None, help="only packets matching this {kw}")',
            "seedswap/cli.py::list_opts": f'''
                if args.{kw} is not None:
                    opts["{kw}"] = args.{kw}
            ''',
        },
        readme=f"## {A['title']}\n\n{A['readme']} On the command line: `seedswap list {A['flag']} VALUE`.\n",
        vtests=f'''
            def test_attr_filter(self):
                self.assertEqual(ids(stock().query({kw}="{A['value']}")), {A['ids']!r})
        ''',
        tests=attr_tests,
    ))

    S.append(Slice(
        id="min-germ", title="Minimum germination filter", d=1,
        pitch=("Old packets with poor germination end up on the swap table; the volunteers want to hide the weak ones.",
               "We want to be able to list only packets that are still worth sowing."),
        reqs=("`Catalog.query(min_germ=N)` keeps packets whose `germ_pct` is at least `N` (inclusive). `N` must be an integer from 0 to 100, otherwise `ValueError`.",
              "`seedswap list --min-germ N` does the same on the command line; a bad value is reported like any other `ValueError` (message on stderr, exit status 2)."),
        code={
            "seedswap/catalog.py::query": '''
                if "min_germ" in opts:
                    floor = opts.pop("min_germ")
                    if not isinstance(floor, int) or isinstance(floor, bool) or not 0 <= floor <= 100:
                        raise ValueError("min_germ must be an integer between 0 and 100")
                    rows = [p for p in rows if p.germ_pct >= floor]
            ''',
            "seedswap/cli.py::list_flags": 'ls.add_argument("--min-germ", type=int, default=None, help="only packets with at least this germination percent")',
            "seedswap/cli.py::list_opts": '''
                if args.min_germ is not None:
                    opts["min_germ"] = args.min_germ
            ''',
        },
        readme=dd('''
            ## Minimum germination

            `Catalog.query(min_germ=N)` keeps packets with `germ_pct >= N` (`N` is an int in 0-100, else `ValueError`).
            Command line: `seedswap list --min-germ N`.
        '''),
        vtests='''
            def test_min_germ(self):
                self.assertEqual(ids(stock().query(min_germ=90)), ["bean-02"])
        ''',
        tests='''
            def test_min_germ(self):
                cat = stock()
                self.assertEqual(ids(cat.query(min_germ=85)), ["bean-02", "tom-01"])
                self.assertEqual(ids(cat.query(min_germ=0)), ids(cat.packets()))
                self.assertEqual(cat.query(min_germ=100), [])
                for bad in (-1, 101, 80.5, "80"):
                    with self.assertRaises(ValueError):
                        cat.query(min_germ=bad)

            def test_min_germ_cli(self):
                self.seed()
                code, out, _ = self.run_cli("list", "--min-germ", "78")
                self.assertEqual(code, 0)
                self.assertEqual([r.split()[0] for r in out.splitlines()[1:]], ["basil-01", "bean-02", "tom-01"])
                code, out, err = self.run_cli("list", "--min-germ", "150")
                self.assertEqual(code, 2)
                self.assertTrue(err.startswith("seedswap: "))
        ''',
        cross={
            "attr-filter": {"tests": fmt('''
                def test_min_germ_with_filter(self):
                    cat = stock()
                    self.assertEqual(ids(cat.query(__KW__="__VALUE__", min_germ=80)), __IDS__)
            ''', KW=kw, VALUE=A["value"], IDS=repr(A["ids_g80"]))},
        },
    ))

    S.append(Slice(
        id="sort", title="Sorting", d=2,
        pitch=("The list is always ordered by id, which is not how anyone browses: people want the biggest stock or the newest harvest first.",
               "Volunteers want to sort the shelf list by quantity or harvest date."),
        reqs=("`Catalog.query(sort=KEY, desc=False)` orders the result by `KEY`, one of `id`, `species`, `qty`, `harvested`, `germ_pct`. Anything else is a `ValueError`. String keys (`id`, `species`) compare case-insensitively.",
              "Ties keep id order (ascending), also when `desc=True`: `desc=True` reverses the key order only.",
              "`desc=True` without `sort` is a `ValueError`; `desc` defaults to `False`.",
              "`seedswap list --sort KEY [--desc]` exposes both options. `--desc` without `--sort` is an error (exit status 2, message on stderr).",
              "Sorting applies to the packets that remain after any filters."),
        example="$ seedswap list --sort qty --desc\n(largest stock first; equal quantities in id order)",
        code={
            "seedswap/catalog.py::query": '''
                sort_key = opts.pop("sort", None)
                descending = opts.pop("desc", False)
                if sort_key is None:
                    if descending:
                        raise ValueError("desc requires sort")
                else:
                    if sort_key not in ("id", "species", "qty", "harvested", "germ_pct"):
                        raise ValueError(f"cannot sort by {sort_key!r}")

                    def _key(p, _k=sort_key):
                        v = getattr(p, _k)
                        return v.lower() if isinstance(v, str) else v

                    rows.sort(key=_key, reverse=bool(descending))
            ''',
            "seedswap/cli.py::list_flags": '''
                ls.add_argument("--sort", choices=["id", "species", "qty", "harvested", "germ_pct"], default=None)
                ls.add_argument("--desc", action="store_true", help="reverse the sort order")
            ''',
            "seedswap/cli.py::list_opts": '''
                if args.sort:
                    opts["sort"] = args.sort
                if args.desc:
                    opts["desc"] = True
            ''',
        },
        readme=dd('''
            ## Sorting

            `Catalog.query(sort=KEY, desc=False)`: `KEY` is `id`, `species`, `qty`, `harvested` or `germ_pct` (else
            `ValueError`); strings compare ignoring case. Equal keys stay in id order even with `desc=True`; `desc`
            without `sort` is a `ValueError`. Sorting runs after filtering. Command line: `--sort KEY [--desc]`.
        '''),
        vtests='''
            def test_sort_qty(self):
                self.assertEqual(ids(stock().query(sort="qty"))[:2], ["tom-02", "tom-01"])
        ''',
        tests='''
            def test_sort_keys(self):
                cat = stock()
                self.assertEqual(ids(cat.query(sort="qty")), ["tom-02", "tom-01", "basil-01", "kale-01", "bean-02"])
                self.assertEqual(ids(cat.query(sort="qty", desc=True)), ["bean-02", "kale-01", "basil-01", "tom-01", "tom-02"])
                self.assertEqual(ids(cat.query(sort="harvested")), ["tom-02", "bean-02", "basil-01", "tom-01", "kale-01"])
                self.assertEqual(ids(cat.query(sort="germ_pct", desc=True)), ["bean-02", "tom-01", "basil-01", "kale-01", "tom-02"])

            def test_sort_ties_and_case(self):
                cat = stock()
                # species: basil, bean, Kale, tomato, Tomato; the two tomatoes tie and stay in id order
                self.assertEqual(ids(cat.query(sort="species")), ["basil-01", "bean-02", "kale-01", "tom-01", "tom-02"])
                self.assertEqual(ids(cat.query(sort="species", desc=True)), ["tom-01", "tom-02", "kale-01", "bean-02", "basil-01"])
                self.assertEqual(ids(cat.query(sort="id", desc=True)), ["tom-02", "tom-01", "kale-01", "bean-02", "basil-01"])

            def test_sort_errors(self):
                cat = stock()
                with self.assertRaises(ValueError):
                    cat.query(sort="shelf")
                with self.assertRaises(ValueError):
                    cat.query(desc=True)
                self.assertEqual(ids(cat.query(desc=False)), ids(cat.packets()))

            def test_sort_cli(self):
                self.seed()
                code, out, _ = self.run_cli("list", "--sort", "qty", "--desc")
                self.assertEqual(code, 0)
                self.assertEqual([r.split()[0] for r in out.splitlines()[1:]], ["bean-02", "kale-01", "basil-01", "tom-01", "tom-02"])
                code, out, err = self.run_cli("list", "--desc")
                self.assertEqual(code, 2)
                self.assertTrue(err.startswith("seedswap: "))
        ''',
        cross={
            "attr-filter": {"tests": fmt('''
                def test_sort_after_filter(self):
                    cat = stock()
                    self.assertEqual(ids(cat.query(__KW__="__VALUE__", sort="qty")), __IDSQ__)
                    self.assertEqual(ids(cat.query(sort="qty", __KW__="__VALUE__", desc=True)), __IDSQ__[::-1])
            ''', KW=kw, VALUE=A["value"], IDSQ=repr(A["ids_qty"]))},
            "min-germ": {"tests": '''
                def test_sort_after_min_germ(self):
                    self.assertEqual(ids(stock().query(min_germ=75, sort="qty")), ["tom-01", "basil-01", "bean-02"])
            '''},
        },
    ))

    S.append(Slice(
        id="json-format", title="JSON output", d=2,
        pitch=("The dashboard script has to parse the table output with awk; it would much rather get JSON.",
               "We want to feed the list into other tools, so a machine-readable format is needed."),
        reqs=("`seedswap list --format json` prints a JSON array with one object per packet, in the same order the table would show them. Each object has exactly the keys of `Packet.to_dict()`.",
              "An empty result prints `[]`.",
              "`render.FORMATS['json']` is a function from the list of packets to the text to print (ending with a newline), like the table format, so `--format json` shows up in `--help` through the existing `choices`."),
        code={
            "seedswap/render.py::imports": "import json",
            "seedswap/render.py::renderers": '''
                def json_rows(rows):
                    """A JSON array of packet objects."""
                    return json.dumps([p.to_dict() for p in rows], indent=2, sort_keys=True) + "\\n"
            ''',
            "seedswap/render.py::formats": 'FORMATS["json"] = json_rows',
        },
        readme=dd('''
            ## JSON output

            `seedswap list --format json` prints a JSON array of packet objects (the keys of `Packet.to_dict()`), in table
            order; an empty list is `[]`. `render.FORMATS["json"]` is the function behind it.
        '''),
        vtests='''
            def test_json_format(self):
                self.assertIn("json", render.FORMATS)
        ''',
        tests='''
            def test_json_format(self):
                import json
                rows = stock().query()
                data = json.loads(render.FORMATS["json"](rows))
                self.assertEqual(data, [p.to_dict() for p in rows])
                self.assertEqual(json.loads(render.FORMATS["json"]([])), [])
                self.assertTrue(render.FORMATS["json"](rows).endswith("\\n"))

            def test_json_cli(self):
                import json
                self.seed()
                code, out, _ = self.run_cli("list", "--format", "json")
                self.assertEqual(code, 0)
                data = json.loads(out)
                self.assertEqual([d["id"] for d in data], ["basil-01", "bean-02", "kale-01", "tom-01", "tom-02"])
                self.assertEqual(set(data[0]), {"id", "species", "variety", "qty", "harvested", "germ_pct", "shelf"})
                self.assertEqual(data[4]["harvested"], "2022-09-14")
        ''',
        cross={
            "sort": {"tests": '''
                def test_json_follows_sort(self):
                    import json
                    self.seed()
                    code, out, _ = self.run_cli("list", "--format", "json", "--sort", "qty")
                    self.assertEqual([d["id"] for d in json.loads(out)][:2], ["tom-02", "tom-01"])
            '''},
        },
    ))

    S.append(Slice(
        id="csv-format", title="CSV output", d=2,
        pitch=("The treasurer pastes the packet list into a spreadsheet every month.",
               "People want to open the list in a spreadsheet."),
        reqs=("`seedswap list --format csv` prints the packets as CSV: first a header row with the column names `id,species,variety,qty,harvested,germ_pct,shelf`, then one row per packet in the same order as the table, `harvested` as `YYYY-MM-DD`.",
              "Comma-separated, lines end with a single `\\n`; a field containing a comma, a double quote or a newline is wrapped in double quotes with inner quotes doubled (standard CSV quoting).",
              "With no packets only the header row is printed.",
              "`render.FORMATS['csv']` is the function behind it (packets in, text out)."),
        code={
            "seedswap/render.py::imports": "import csv\nimport io",
            "seedswap/render.py::renderers": '''
                def csv_rows(rows):
                    """Header row plus one CSV row per packet."""
                    buf = io.StringIO()
                    w = csv.writer(buf, lineterminator="\\n")
                    w.writerow(COLUMNS)
                    for p in rows:
                        d = p.to_dict()
                        w.writerow([d[c] for c in COLUMNS])
                    return buf.getvalue()
            ''',
            "seedswap/render.py::formats": 'FORMATS["csv"] = csv_rows',
        },
        readme=dd('''
            ## CSV output

            `seedswap list --format csv`: a header row (`id,species,variety,qty,harvested,germ_pct,shelf`) then one row per
            packet, `\\n` line ends, standard quoting for fields with commas, quotes or newlines. No packets: header only.
        '''),
        vtests='''
            def test_csv_format(self):
                self.assertIn("csv", render.FORMATS)
        ''',
        tests='''
            def test_csv_text(self):
                rows = stock().query()
                text = render.FORMATS["csv"](rows)
                lines = text.split("\\n")
                self.assertEqual(lines[0], "id,species,variety,qty,harvested,germ_pct,shelf")
                self.assertEqual(lines[1], "basil-01,basil,Genovese,12,2024-06-30,78,A2")
                self.assertEqual(lines[5], 'tom-02,Tomato,"Brandywine, pink",4,2022-09-14,60,A1')
                self.assertEqual(lines[6], "")
                self.assertEqual(render.FORMATS["csv"]([]), "id,species,variety,qty,harvested,germ_pct,shelf\\n")

            def test_csv_quotes(self):
                cat = Catalog()
                cat.add(mk("q-1", "pea", 'The "Big" one', 3, date(2024, 1, 5)))
                text = render.FORMATS["csv"](cat.query())
                self.assertEqual(text.split("\\n")[1], 'q-1,pea,"The ""Big"" one",3,2024-01-05,80,A1')

            def test_csv_cli(self):
                import csv as csvmod
                import io as iomod
                self.seed()
                code, out, _ = self.run_cli("list", "--format", "csv")
                self.assertEqual(code, 0)
                table = list(csvmod.reader(iomod.StringIO(out)))
                self.assertEqual(len(table), 6)
                self.assertEqual(table[5][2], "Brandywine, pink")
        ''',
        cross={
            "sort": {"tests": '''
                def test_csv_follows_sort(self):
                    self.seed()
                    code, out, _ = self.run_cli("list", "--format", "csv", "--sort", "qty", "--desc")
                    self.assertEqual([ln.split(",")[0] for ln in out.splitlines()[1:3]], ["bean-02", "kale-01"])
            '''},
        },
    ))

    S.append(Slice(
        id="paging", title="Paging", d=3,
        pitch=("The swap catalogue now has hundreds of packets and the list scrolls off the screen.",
               "Long listings are unusable on the tablet at the swap table; we need pages."),
        reqs=(f"`Catalog.page(page, per_page={per_page}, **options)` returns a dict with `items` (the packets of that page), `page` (as requested), `pages` (the number of pages, at least 1) and `total` (how many packets match the options). `per_page` defaults to {per_page}.",
              "Pages are numbered from 1. The extra options go to `Catalog.query`, so a page is cut from the filtered and sorted result. A page past the last one has empty `items`. `page < 1` or `per_page < 1` is a `ValueError`.",
              "`seedswap list --page N [--per-page M]` prints that page in the chosen format; `--per-page` alone means page 1, and `--page` alone uses the default page size.",
              "After a `table` listing of a page the command prints one more line, `page N of K (T packets)`. Other formats print no such line. Without `--page` and `--per-page` the listing is unchanged. A bad page or size is reported like any other `ValueError` (stderr, exit status 2)."),
        example="$ seedswap list --page 2 --per-page 2\nid        species  ...\nkale-01   Kale     ...\ntom-01    tomato   ...\npage 2 of 3 (5 packets)",
        code={
            "seedswap/catalog.py::classes": f"PER_PAGE = {per_page}",
            "seedswap/catalog.py::methods": '''
                def page(self, page, per_page=PER_PAGE, **opts):
                    if page < 1 or per_page < 1:
                        raise ValueError("page and per_page must be at least 1")
                    rows = self.query(**opts)
                    start = (page - 1) * per_page
                    return {
                        "items": rows[start:start + per_page],
                        "page": page,
                        "pages": max(1, -(-len(rows) // per_page)),
                        "total": len(rows),
                    }
            ''',
            "seedswap/cli.py::imports": "from .catalog import PER_PAGE",
            "seedswap/cli.py::list_flags": '''
                ls.add_argument("--page", type=int, default=None, help="show this page (1-based)")
                ls.add_argument("--per-page", type=int, default=None, help=f"packets per page (default {PER_PAGE})")
            ''',
            "seedswap/cli.py::list_rows": '''
                if args.page is not None or args.per_page is not None:
                    info = cat.page(1 if args.page is None else args.page, PER_PAGE if args.per_page is None else args.per_page, **opts)
                    rows = info["items"]
                else:
                    info = None
                    rows = cat.query(**opts)
            ''',
            "seedswap/cli.py::list_footer": '''
                if info is not None and args.format == "table":
                    out.write(f"page {info['page']} of {info['pages']} ({info['total']} packets)\\n")
            ''',
        },
        readme=fmt(dd('''
            ## Paging

            `Catalog.page(page, per_page=__PP__, **options)` returns `{"items", "page", "pages", "total"}`; `options` are
            handed to `query`. Pages count from 1, a page past the end has no items, `pages` is at least 1, and
            `page < 1` / `per_page < 1` raise `ValueError`. On the command line `list --page N --per-page M` prints that
            page, and after a table also `page N of K (T packets)`.
        '''), PP=per_page),
        vtests='''
            def test_page_exists(self):
                self.assertEqual(stock().page(1)["total"], 5)
        ''',
        tests=fmt('''
            def bulk(self, n):
                cat = Catalog()
                for i in range(n):
                    cat.add(mk(f"p-{i:03d}", "pea" if i % 2 else "bean", f"V{i}", i + 1, date(2024, 1, 1), 50 + i % 50))
                return cat

            def test_page_basics(self):
                cat = stock()
                p = cat.page(2, 2)
                self.assertEqual((ids(p["items"]), p["page"], p["pages"], p["total"]), (["kale-01", "tom-01"], 2, 3, 5))
                self.assertEqual(ids(cat.page(3, 2)["items"]), ["tom-02"])
                p = cat.page(4, 2)
                self.assertEqual((p["items"], p["page"], p["pages"], p["total"]), ([], 4, 3, 5))
                p = cat.page(1, per_page=5)
                self.assertEqual((len(p["items"]), p["pages"]), (5, 1))

            def test_page_empty_and_errors(self):
                p = Catalog().page(1)
                self.assertEqual((p["items"], p["pages"], p["total"]), ([], 1, 0))
                for args in ((0,), (-3,), (1, 0)):
                    with self.assertRaises(ValueError):
                        stock().page(*args)

            def test_page_default_size(self):
                cat = self.bulk(53)
                pages = -(-53 // __PP__)
                first = cat.page(1)
                self.assertEqual(len(first["items"]), __PP__)
                self.assertEqual((first["pages"], first["total"]), (pages, 53))
                self.assertEqual(len(cat.page(pages)["items"]), 53 - __PP__ * (pages - 1))
                self.assertEqual(cat.page(pages + 1)["items"], [])
                self.assertEqual(ids(first["items"])[0], "p-000")

            def test_page_cli(self):
                self.seed()
                code, out, _ = self.run_cli("list", "--page", "2", "--per-page", "2")
                lines = out.splitlines()
                self.assertEqual(code, 0)
                self.assertEqual([ln.split()[0] for ln in lines[1:3]], ["kale-01", "tom-01"])
                self.assertEqual(lines[3:], ["page 2 of 3 (5 packets)"])
                code, out, _ = self.run_cli("list", "--per-page", "4")
                self.assertEqual(out.splitlines()[-1], "page 1 of 2 (5 packets)")
                self.assertEqual(len(out.splitlines()), 6)
                code, out, _ = self.run_cli("list", "--page", "9", "--per-page", "2")
                self.assertEqual(code, 0)
                self.assertEqual(len(out.splitlines()), 2)
                self.assertEqual(out.splitlines()[-1], "page 9 of 3 (5 packets)")
                code, out, _ = self.run_cli("list")
                self.assertEqual(len(out.splitlines()), 6)
                self.assertFalse(out.splitlines()[-1].startswith("page "))
                code, out, err = self.run_cli("list", "--page", "0")
                self.assertEqual((code, out), (2, ""))
                self.assertTrue(err.startswith("seedswap: "))
        ''', PP=per_page),
        cross={
            "attr-filter": {"tests": fmt('''
                def test_page_of_filtered(self):
                    p = stock().page(1, 1, __KW__="__VALUE__")
                    self.assertEqual((ids(p["items"]), p["pages"], p["total"]), (__FIRST__, __N__, __N__))
            ''', KW=kw, VALUE=A["value"], FIRST=repr(A["ids"][:1]), N=len(A["ids"]))},
            "sort": {"tests": '''
                def test_page_of_sorted(self):
                    p = stock().page(2, 2, sort="qty", desc=True)
                    self.assertEqual(ids(p["items"]), ["basil-01", "tom-01"])
                    self.assertEqual(p["total"], 5)
            '''},
            "json-format": {"tests": '''
                def test_page_json_has_no_footer(self):
                    import json
                    self.seed()
                    code, out, _ = self.run_cli("list", "--format", "json", "--page", "2", "--per-page", "2")
                    self.assertEqual([d["id"] for d in json.loads(out)], ["kale-01", "tom-01"])
            '''},
            "csv-format": {"tests": '''
                def test_page_csv_has_no_footer(self):
                    self.seed()
                    code, out, _ = self.run_cli("list", "--format", "csv", "--page", "3", "--per-page", "2")
                    self.assertEqual(out.splitlines()[1:], ["tom-02,Tomato,\\"Brandywine, pink\\",4,2022-09-14,60,A1"])
            '''},
        },
    ))

    S.append(Slice(
        id="audit-log", title="Change log", d=3,
        pitch=("When the shelf count and the catalogue disagree, nobody can tell who took what.",
               "We need a trail of what changed in the catalogue and when, kept with the data."),
        reqs=("Every successful `Catalog.add`, `remove` and `take` appends an entry to the catalogue's change log. A call that raises an error appends nothing. An entry is a dict with `seq` (1 for the first entry, then 1 more each time), `op` (`add`, `remove` or `take`), `id` (the packet id) and `delta` (the change in units: `+qty` for add, minus the removed packet's `qty` for remove, `-n` for take).",
              f"`Catalog.{noun}(pid=None)` returns copies of the entries, oldest first; with `pid` only that packet's entries.",
              "The log is stored in `to_dict()` under the key `audit` and restored by `from_dict`; a dict without that key gives an empty log, and `seq` continues after a reload.",
              f"`seedswap {noun} [ID]` prints one line per entry, `#<seq> <op> <id> <delta>`, with the delta written with an explicit sign (`+12`, `-3`). The log lives in the `--db` file, so it survives between invocations."),
        example=f"$ seedswap take tom-01 3\n$ seedswap {noun} tom-01\n#3 add tom-01 +10\n#6 take tom-01 -3",
        code={
            "seedswap/catalog.py::init": "self._audit = []",
            "seedswap/catalog.py::on_add": 'self._record("add", packet.id, packet.qty)',
            "seedswap/catalog.py::on_remove": 'self._record("remove", pid, -packet.qty)',
            "seedswap/catalog.py::on_take": 'self._record("take", pid, -n)',
            "seedswap/catalog.py::methods": f'''
                def _record(self, op, pid, delta):
                    self._audit.append({{"seq": len(self._audit) + 1, "op": op, "id": pid, "delta": delta}})

                def {noun}(self, pid=None):
                    return [dict(e) for e in self._audit if pid is None or e["id"] == pid]
            ''',
            "seedswap/catalog.py::to_dict": 'd["audit"] = [dict(e) for e in self._audit]',
            "seedswap/catalog.py::from_dict": 'cat._audit = [dict(e) for e in d.get("audit", [])]',
            "seedswap/cli.py::subcommands": f'''
                hist = sub.add_parser("{noun}", help="show the change log")
                hist.add_argument("id", nargs="?", default=None)
            ''',
            "seedswap/cli.py::commands": f'''
                def cmd_{noun}(args, cat, out):
                    for e in cat.{noun}(args.id):
                        out.write(f"#{{e['seq']}} {{e['op']}} {{e['id']}} {{e['delta']:+d}}\\n")
            ''',
            "seedswap/cli.py::registry": f'COMMANDS["{noun}"] = cmd_{noun}',
        },
        readme=fmt(dd('''
            ## Change log

            Each successful `add`, `remove` and `take` is recorded as `{"seq", "op", "id", "delta"}` (`seq` counts from 1;
            `delta` is `+qty`, `-qty` or `-n`). `Catalog.__NOUN__(pid=None)` returns copies of the entries (oldest first, only
            `pid`'s when given). The log is saved in `to_dict()["audit"]`, and `seedswap __NOUN__ [ID]` prints
            `#<seq> <op> <id> <delta>` lines (delta always signed).
        '''), NOUN=noun),
        vtests=fmt('''
            def test_log_exists(self):
                cat = Catalog()
                cat.add(mk("a-1", "pea", "Alderman", 5, date(2024, 1, 1)))
                self.assertEqual(len(cat.__NOUN__()), 1)
        ''', NOUN=noun),
        tests=fmt('''
            def test_log_entries(self):
                cat = Catalog()
                cat.add(mk("a-1", "pea", "Alderman", 5, date(2024, 1, 1)))
                cat.add(mk("b-1", "bean", "Provider", 9, date(2024, 1, 2)))
                cat.take("a-1", 2)
                with self.assertRaises(ValueError):
                    cat.add(mk("a-1", "pea", "Dup", 1, date(2024, 1, 1)))
                with self.assertRaises(ValueError):
                    cat.take("b-1", 50)
                with self.assertRaises(KeyError):
                    cat.remove("zz-9")
                cat.remove("b-1")
                self.assertEqual(cat.__NOUN__(), [
                    {"seq": 1, "op": "add", "id": "a-1", "delta": 5},
                    {"seq": 2, "op": "add", "id": "b-1", "delta": 9},
                    {"seq": 3, "op": "take", "id": "a-1", "delta": -2},
                    {"seq": 4, "op": "remove", "id": "b-1", "delta": -9},
                ])
                self.assertEqual([e["seq"] for e in cat.__NOUN__("a-1")], [1, 3])
                self.assertEqual(cat.__NOUN__("nobody"), [])
                cat.__NOUN__()[0]["delta"] = 99
                self.assertEqual(cat.__NOUN__()[0]["delta"], 5)

            def test_log_persists(self):
                cat = stock()
                cat.take("tom-01", 1)
                again = Catalog.from_dict(cat.to_dict())
                self.assertEqual(again.__NOUN__(), cat.__NOUN__())
                self.assertEqual(cat.to_dict()["audit"], cat.__NOUN__())
                again.take("tom-01", 1)
                self.assertEqual(again.__NOUN__()[-1], {"seq": 7, "op": "take", "id": "tom-01", "delta": -1})
                self.assertEqual(Catalog.from_dict({"packets": []}).__NOUN__(), [])

            def test_log_cli(self):
                self.seed()
                self.run_cli("take", "tom-01", "3")
                code, out, _ = self.run_cli("__NOUN__", "tom-01")
                self.assertEqual((code, out.splitlines()), (0, ["#3 add tom-01 +10", "#6 take tom-01 -3"]))
                code, out, _ = self.run_cli("__NOUN__")
                self.assertEqual(len(out.splitlines()), 6)
                self.run_cli("remove", "kale-01")
                code, out, _ = self.run_cli("__NOUN__", "kale-01")
                self.assertEqual(out.splitlines(), ["#2 add kale-01 +25", "#7 remove kale-01 -25"])
        ''', NOUN=noun),
    ))

    S.append(Slice(
        id="import-csv", title="CSV import", d=3,
        pitch=("Swap members send their packet lists as spreadsheets and someone retypes them by hand.",
               "Bulk loading a donated collection should not mean one `add` per packet."),
        reqs=("`Catalog.import_csv(text)` adds packets from CSV text and returns a report object with `added` (an int) and `skipped` (a list of `(line, reason)` pairs, `reason` a non-empty string). The first line is the header; `line` counts input lines from 1, so the first data row is line 2 (a blank line is ignored but still counts).",
              "Columns are matched by header name, in any order: `id`, `species`, `variety`, `qty`, `harvested` are required; `germ_pct` and `shelf` are optional (defaults 80 and `A1`); other columns are ignored. Input with no header, or without all required columns, raises `ValueError` and imports nothing.",
              "A bad row is skipped (and reported) rather than aborting the import: too few fields, an empty `id`/`species`/`variety`, a `qty` or `germ_pct` that is not an integer, a `qty` that is not positive, a date that is not `YYYY-MM-DD`, or an `id` that already exists (in the catalogue or earlier in the same file). Good rows are added through the normal `add` rules. Skips are listed in file order.",
              "`seedswap import FILE` reads a UTF-8 file, saves the catalogue and prints `imported N, skipped M` followed by one line `line L: reason` per skipped row. Exit status 0 when nothing was skipped, 1 when something was. An unreadable file or a bad header is an error like any other (stderr, exit status 2)."),
        example="$ seedswap import donated.csv\nimported 41, skipped 2\nline 17: qty is not a number\nline 30: duplicate id",
        code={
            "seedswap/catalog.py::imports": "import csv\nimport io",
            "seedswap/catalog.py::classes": '''
                class ImportReport:
                    def __init__(self):
                        self.added = 0
                        self.skipped = []
            ''',
            "seedswap/catalog.py::methods": '''
                def import_csv(self, text):
                    report = ImportReport()
                    header = None
                    for line, row in enumerate(csv.reader(io.StringIO(text)), start=1):
                        if not any(c.strip() for c in row):
                            continue
                        if header is None:
                            header = [c.strip() for c in row]
                            missing = [c for c in ("id", "species", "variety", "qty", "harvested") if c not in header]
                            if missing:
                                raise ValueError("missing column: " + ", ".join(missing))
                            continue
                        rec = dict(zip(header, (c.strip() for c in row)))
                        if len(row) < len(header):
                            report.skipped.append((line, "too few fields"))
                            continue
                        try:
                            if not (rec["id"] and rec["species"] and rec["variety"]):
                                raise ValueError("empty id, species or variety")
                            germ = int(rec["germ_pct"]) if rec.get("germ_pct") else 80
                            packet = Packet(rec["id"], rec["species"], rec["variety"], int(rec["qty"]),
                                            date.fromisoformat(rec["harvested"]), germ, rec.get("shelf") or "A1")
                            self.add(packet)
                        except ValueError as e:
                            report.skipped.append((line, str(e)))
                            continue
                        report.added += 1
                    if header is None:
                        raise ValueError("no header row")
                    return report
            ''',
            "seedswap/cli.py::subcommands": '''
                imp = sub.add_parser("import", help="add packets from a CSV file")
                imp.add_argument("file")
            ''',
            "seedswap/cli.py::commands": '''
                def cmd_import(args, cat, out):
                    try:
                        with open(args.file, encoding="utf-8", newline="") as f:
                            text = f.read()
                    except OSError as e:
                        raise ValueError(f"cannot read {args.file}: {e.strerror}") from None
                    report = cat.import_csv(text)
                    save(cat, args.db)
                    out.write(f"imported {report.added}, skipped {len(report.skipped)}\\n")
                    for line, reason in report.skipped:
                        out.write(f"line {line}: {reason}\\n")
                    return 1 if report.skipped else 0
            ''',
            "seedswap/cli.py::registry": 'COMMANDS["import"] = cmd_import',
        },
        readme=dd('''
            ## CSV import

            `Catalog.import_csv(text)` returns a report with `added` and `skipped` (`(line, reason)` pairs; the header is
            line 1). Columns are matched by name; `id`, `species`, `variety`, `qty`, `harvested` are required, `germ_pct`
            and `shelf` optional. Bad rows (too few fields, empty text, non-numeric or non-positive numbers, bad date,
            duplicate id) are skipped, the rest is added. `seedswap import FILE` prints `imported N, skipped M` and one
            `line L: reason` per skipped row (exit status 1 if any were skipped).
        '''),
        vtests='''
            def test_import_exists(self):
                self.assertEqual(Catalog().import_csv("id,species,variety,qty,harvested\\n").added, 0)
        ''',
        tests='''
            def test_import_rows(self):
                cat = Catalog()
                cat.add(mk("lett-09", "lettuce", "Existing", 5, date(2024, 1, 1)))
                text = ("shelf,id,species,variety,qty,harvested,extra\\n"
                        "B2,lett-01,lettuce,Oakleaf,30,2024-05-05,x\\n"
                        "\\n"
                        'B2,lett-02,lettuce,"Red, crisp",x,2024-05-06,x\\n'
                        "B3,lett-03,lettuce,Cos,12,2024-13-01,x\\n"
                        "B3,lett-01,lettuce,Dup,12,2024-05-07,x\\n"
                        "B4,lett-04,lettuce,Butterhead,0,2024-05-08,x\\n"
                        "B4,lett-05,lettuce,Cos\\n"
                        "B5,lett-06,lettuce,Little Gem,8,2024-05-09,x\\n"
                        "B5,lett-09,lettuce,Clash,8,2024-05-09,x\\n"
                        ",lett-07,lettuce,No shelf,3,2024-05-10,x\\n")
                rep = cat.import_csv(text)
                self.assertEqual(rep.added, 3)
                self.assertEqual([ln for ln, _ in rep.skipped], [4, 5, 6, 7, 8, 10])
                self.assertTrue(all(isinstance(r, str) and r for _, r in rep.skipped))
                self.assertEqual(ids(cat.packets()), ["lett-01", "lett-06", "lett-07", "lett-09"])
                p = cat.get("lett-01")
                self.assertEqual((p.shelf, p.germ_pct, p.qty, p.variety, p.harvested), ("B2", 80, 30, "Oakleaf", date(2024, 5, 5)))
                self.assertEqual(cat.get("lett-07").shelf, "A1")
                self.assertEqual(cat.get("lett-09").variety, "Existing")

            def test_import_optional_columns(self):
                cat = Catalog()
                rep = cat.import_csv("id,species,variety,qty,harvested,germ_pct\\nr-1,radish,Cherry,20,2024-04-01,95\\n")
                self.assertEqual((rep.added, rep.skipped), (1, []))
                self.assertEqual(cat.get("r-1").germ_pct, 95)
                rep = cat.import_csv("id,species,variety,qty,harvested,germ_pct\\nr-2,radish,Cherry,20,2024-04-01,lots\\n")
                self.assertEqual((rep.added, [ln for ln, _ in rep.skipped]), (0, [2]))

            def test_import_header_errors(self):
                for text in ("", "\\n\\n", "id,species,qty,harvested\\nx,y,1,2024-01-01\\n"):
                    cat = Catalog()
                    with self.assertRaises(ValueError):
                        cat.import_csv(text)
                    self.assertEqual(cat.packets(), [])

            def test_import_cli(self):
                self.seed()
                path = os.path.join(os.path.dirname(self.db), "batch.csv")
                with open(path, "w", encoding="utf-8") as f:
                    f.write("id,species,variety,qty,harvested\\nl-1,leek,Musselburgh,15,2024-03-03\\nl-2,leek,Bandit,zero,2024-03-04\\nl-3,leek,Lancelot,9,2024-03-05\\nl-1,leek,Dup,9,2024-03-05\\n")
                code, out, _ = self.run_cli("import", path)
                lines = out.splitlines()
                self.assertEqual(code, 1)
                self.assertEqual(lines[0], "imported 2, skipped 2")
                self.assertEqual([ln.split(":")[0] for ln in lines[1:]], ["line 3", "line 5"])
                self.assertEqual(self.catalog().get("l-3").qty, 9)
                with open(path, "w", encoding="utf-8") as f:
                    f.write("id,species,variety,qty,harvested\\nl-4,leek,Carentan,4,2024-03-03\\n")
                code, out, _ = self.run_cli("import", path)
                self.assertEqual((code, out), (0, "imported 1, skipped 0\\n"))
                code, out, err = self.run_cli("import", path + ".missing")
                self.assertEqual((code, out), (2, ""))
                self.assertTrue(err.startswith("seedswap: "))
        ''',
        cross={
            "audit-log": {
                "reqs": ("Imported rows are recorded in the change log like any other `add` (one entry per added row, none for skipped rows).",),
                "tests": fmt('''
                    def test_import_is_logged(self):
                        cat = Catalog()
                        cat.import_csv("id,species,variety,qty,harvested\\na-1,pea,X,4,2024-01-01\\na-1,pea,Y,4,2024-01-01\\na-2,pea,Z,6,2024-01-01\\n")
                        self.assertEqual([(e["seq"], e["op"], e["id"], e["delta"]) for e in cat.__NOUN__()], [(1, "add", "a-1", 4), (2, "add", "a-2", 6)])
                ''', NOUN=noun)},
            "csv-format": {
                "reqs": ("A file written by `seedswap list --format csv` must import cleanly into an empty catalogue and reproduce the same packets.",),
                "tests": '''
                    def test_import_reads_csv_output(self):
                        text = render.FORMATS["csv"](stock().query())
                        cat = Catalog()
                        rep = cat.import_csv(text)
                        self.assertEqual((rep.added, rep.skipped), (5, []))
                        self.assertEqual([p.to_dict() for p in cat.packets()], [p.to_dict() for p in stock().packets()])
                '''},
        },
    ))

    S.append(Slice(
        id="low-stock-hook", title="Low-stock hooks", d=3,
        pitch=("The swap table wants a nudge to restock before a packet runs out, and other scripts want to react to changes.",
               "Other parts of the swap tooling (labels, the mailing list) need to be told when the catalogue changes."),
        reqs=("`Catalog.on(event, fn)` registers `fn` for `event`, one of `added`, `removed`, `low_stock` (anything else: `ValueError`), and returns `fn`. `Catalog.off(event, fn)` removes one registration of `fn` (`ValueError` if there is none, or for an unknown event). Handlers run synchronously, in registration order, with the packet as the only argument; registering the same function twice calls it twice.",
              "`add` fires `added` after the packet is in the catalogue. `remove` fires `removed` after it is gone.",
              f"`take` fires `low_stock` when the units left are between 1 and {low} inclusive (the handler sees the packet with its new `qty`). A `take` that leaves 0 units removes the packet and fires `removed` instead (never `low_stock`). A `take` that leaves more than {low} fires nothing.",
              f"`seedswap take ID N` prints `low stock: ID (K left)` on stdout, before the usual `ID: K left` line, when the take fires `low_stock`."),
        code={
            "seedswap/catalog.py::classes": f"LOW_STOCK = {low}",
            "seedswap/catalog.py::init": '''self._handlers = {"added": [], "removed": [], "low_stock": []}''',
            "seedswap/catalog.py::on_add": 'self._emit("added", packet)',
            "seedswap/catalog.py::on_remove": 'self._emit("removed", packet)',
            "seedswap/catalog.py::on_take": '''
                if left == 0:
                    self._emit("removed", packet)
                elif left <= LOW_STOCK:
                    self._emit("low_stock", packet)
            ''',
            "seedswap/catalog.py::methods": '''
                def on(self, event, fn):
                    if event not in self._handlers:
                        raise ValueError(f"unknown event: {event}")
                    self._handlers[event].append(fn)
                    return fn

                def off(self, event, fn):
                    if event not in self._handlers:
                        raise ValueError(f"unknown event: {event}")
                    try:
                        self._handlers[event].remove(fn)
                    except ValueError:
                        raise ValueError("handler is not registered") from None

                def _emit(self, event, packet):
                    for fn in list(self._handlers[event]):
                        fn(packet)
            ''',
            "seedswap/cli.py::take_pre": 'cat.on("low_stock", lambda p: out.write(f"low stock: {p.id} ({p.qty} left)\\n"))',
        },
        readme=fmt(dd('''
            ## Hooks

            `Catalog.on(event, fn)` / `Catalog.off(event, fn)` manage handlers for `added`, `removed` and `low_stock`; they
            run synchronously in registration order and receive the packet. `take` fires `low_stock` when 1 to __LOW__
            units remain, and `removed` (not `low_stock`) when it empties the packet. `seedswap take` prints
            `low stock: ID (K left)` before its usual line when that happens.
        '''), LOW=low),
        vtests='''
            def test_hook_added(self):
                cat = Catalog()
                seen = []
                cat.on("added", seen.append)
                cat.add(mk("a-1", "pea", "Alderman", 5, date(2024, 1, 1)))
                self.assertEqual([p.id for p in seen], ["a-1"])
        ''',
        tests=fmt('''
            def test_hook_events(self):
                LOW = __LOW__
                cat = Catalog()
                seen = []
                cat.on("added", lambda p: seen.append(("added", p.id)))
                cat.on("removed", lambda p: seen.append(("removed", p.id)))
                cat.on("low_stock", lambda p: seen.append(("low", p.id, p.qty)))
                cat.add(mk("a-1", "pea", "Alderman", 12, date(2024, 1, 1)))
                cat.take("a-1", 2)
                self.assertEqual(seen, [("added", "a-1")])
                cat.take("a-1", 10 - LOW)
                cat.take("a-1", 1)
                cat.take("a-1", LOW - 1)
                self.assertEqual(seen, [("added", "a-1"), ("low", "a-1", LOW), ("low", "a-1", LOW - 1), ("removed", "a-1")])
                cat.add(mk("b-1", "bean", "Provider", 2, date(2024, 1, 1)))
                cat.remove("b-1")
                self.assertEqual(seen[-2:], [("added", "b-1"), ("removed", "b-1")])

            def test_hook_state_when_fired(self):
                cat = Catalog()
                states = []
                cat.on("added", lambda p: states.append(cat.get(p.id).qty))
                cat.on("removed", lambda p: states.append(p.id in [q.id for q in cat.packets()]))
                cat.add(mk("a-1", "pea", "Alderman", 3, date(2024, 1, 1)))
                cat.remove("a-1")
                self.assertEqual(states, [3, False])

            def test_hook_registration(self):
                cat = Catalog()
                calls = []
                def first(p): calls.append("first")
                def second(p): calls.append("second")
                self.assertIs(cat.on("added", first), first)
                cat.on("added", second)
                cat.on("added", first)
                cat.add(mk("a-1", "pea", "Alderman", 3, date(2024, 1, 1)))
                self.assertEqual(calls, ["first", "second", "first"])
                cat.off("added", first)
                calls.clear()
                cat.add(mk("a-2", "pea", "Alderman", 3, date(2024, 1, 1)))
                self.assertEqual(calls, ["second", "first"])
                with self.assertRaises(ValueError):
                    cat.on("exploded", first)
                with self.assertRaises(ValueError):
                    cat.off("exploded", first)
                with self.assertRaises(ValueError):
                    cat.off("removed", first)

            def test_low_stock_cli(self):
                self.seed()
                code, out, _ = self.run_cli("take", "kale-01", str(25 - __LOW__))
                self.assertEqual((code, out.splitlines()), (0, ["low stock: kale-01 (__LOW__ left)", "kale-01: __LOW__ left"]))
                code, out, _ = self.run_cli("take", "bean-02", "1")
                self.assertEqual(out, "bean-02: 39 left\\n")
                code, out, _ = self.run_cli("take", "kale-01", str(__LOW__))
                self.assertEqual(out, "kale-01: 0 left\\n")
        ''', LOW=low),
    ))

    S.append(Slice(
        id="localised-table", title="Localised table", d=3,
        pitch=("The swap runs in several countries and the volunteers print the list for the table.",
               "Our Spanish and French volunteers would like the printed list in their language."),
        reqs=(f"`render.table(rows, lang=\"en\")` takes an optional language code: `en` (today's output), " + ", ".join(f"`{c[0]}`" for c in langs) + ". An unknown code is a `ValueError`.",
              "A language changes only the header labels and the date format; the layout stays exactly the table's (same widths, padding and separators).",
              *(f"`{c[0]}`: headers `{' '.join(c[1])}` (in the usual column order), dates as `{c[3]}` (for example 2022-09-14 shows as `{c[4]}`)." for c in langs),
              "`seedswap list --lang CODE` (default `en`) selects it for the table format; an unknown code is reported like any other `ValueError` (stderr, exit status 2). Other formats ignore `--lang`."),
        code={
            "seedswap/render.py::table_sig": "LANGS = {\n    \"en\": (COLUMNS, \"%Y-%m-%d\"),\n" + "".join(f"    {c[0]!r}: ({c[1]!r}, {c[2]!r}),\n" for c in langs) + "}\n\n\ndef table(rows, lang=\"en\"):",
            "seedswap/render.py::table_cells": '''
                try:
                    labels, datefmt = LANGS[lang]
                except KeyError:
                    raise ValueError(f"unknown language: {lang}") from None
                header = list(labels)
                cells = [[p.harvested.strftime(datefmt) if c == "harvested" else str(getattr(p, c)) for c in COLUMNS] for p in rows]
            ''',
            "seedswap/cli.py::list_flags": 'ls.add_argument("--lang", default="en", help="language of the table")',
            "seedswap/cli.py::list_render": '''
                show = render.FORMATS[args.format]
                out.write(show(rows, lang=args.lang) if args.format == "table" else show(rows))
            ''',
        },
        readme=dd('''
            ## Languages

            `render.table(rows, lang="en")` also speaks ''' + ", ".join(c[0] for c in langs) + '''. A language changes the header labels and
            the date format only. `seedswap list --lang CODE` picks it for the table format; unknown codes are errors.
        '''),
        vtests='''
            def test_table_default_lang(self):
                self.assertEqual(render.table(stock().query()).splitlines()[0].split()[0], "id")
        ''',
        tests=fmt('''
            def expected(self, header, cells):
                widths = [max(len(c) for c in col) for col in zip(header, *cells)]
                rows = [header] + cells
                return "".join("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() + "\\n" for r in rows)

            def test_langs(self):
                rows = stock().query()
                self.assertEqual(render.table(rows, lang="en"), render.table(rows))
                en_header = ["id", "species", "variety", "qty", "harvested", "germ_pct", "shelf"]
                self.assertEqual(render.table(rows), self.expected(en_header, [[p.id, p.species, p.variety, str(p.qty), p.harvested.isoformat(), str(p.germ_pct), p.shelf] for p in rows]))
                for code, header, fmt_, shown in __LANGS__:
                    cells = [[p.id, p.species, p.variety, str(p.qty), p.harvested.strftime(fmt_), str(p.germ_pct), p.shelf] for p in rows]
                    self.assertEqual(render.table(rows, lang=code), self.expected(header, cells))
                    self.assertIn(shown, render.table(rows, lang=code))
                with self.assertRaises(ValueError):
                    render.table(rows, lang="xx")

            def test_lang_cli(self):
                self.seed()
                code, out, _ = self.run_cli("list", "--lang", "__L1__")
                self.assertEqual(code, 0)
                self.assertEqual(out.splitlines()[0].split(), __H1__)
                code, out, _ = self.run_cli("list", "--lang", "en")
                self.assertEqual(out.splitlines()[0].split()[1], "species")
                code, out, err = self.run_cli("list", "--lang", "zz")
                self.assertEqual((code, out), (2, ""))
                self.assertTrue(err.startswith("seedswap: "))
        ''', LANGS=repr([(c[0], c[1], c[2], c[4]) for c in langs]), L1=langs[0][0], H1=repr(langs[0][1])),
        cross={
            "json-format": {"tests": fmt('''
                def test_lang_ignored_by_json(self):
                    import json
                    self.seed()
                    code, out, _ = self.run_cli("list", "--format", "json", "--lang", "__L1__")
                    self.assertEqual(code, 0)
                    self.assertEqual(json.loads(out)[4]["harvested"], "2022-09-14")
            ''', L1=langs[0][0])},
            "paging": {
                "reqs": ("The `page N of K (T packets)` footer is not translated.",),
                "tests": fmt('''
                    def test_footer_stays_english(self):
                        self.seed()
                        code, out, _ = self.run_cli("list", "--lang", "__L1__", "--page", "1", "--per-page", "2")
                        self.assertEqual(out.splitlines()[-1], "page 1 of 3 (5 packets)")
                ''', L1=langs[0][0])},
        },
    ))

    S.append(Slice(
        id="reservations", title="Reservations", d=4,
        pitch=("Members ask us to hold seeds for them until the next swap day, and right now anyone at the table can hand them out.",
               "We need a way to set packets aside for a named person without removing them from the catalogue."),
        reqs=("`Catalog.reserve(pid, who, n)` holds `n` units of a packet for `who`. `n` must be positive and at most the packet's `available` units, else `ValueError`; an unknown packet is a `KeyError`. Reserving again for the same person adds to their hold.",
              "`Catalog.available(pid)` is `qty` minus all held units; `Catalog.reserved(pid)` returns a copy of the holds as `{who: units}` (empty dict when there are none); `Catalog.release(pid, who)` drops that person's hold and returns the number of units it held (0 if none). All three raise `KeyError` for an unknown packet.",
              "`Catalog.take(pid, n, who=None)` (the old two-argument call still works): without `who` it may only hand out `available` units; with `who` it may hand out the person's own held units plus the available ones, and uses up their hold first. A take that breaks these limits is a `ValueError` and changes nothing. Holds that are used up disappear from `reserved`.",
              "Removing a packet drops its holds. Holds are saved by `to_dict()` under the key `holds` as `{packet id: {who: units}}` (only packets that have holds) and restored by `from_dict`.",
              "Command line: `seedswap reserve ID WHO N` prints `reserved N of ID for WHO`; `seedswap release ID WHO` prints `released N of ID from WHO` (N may be 0); `seedswap take ID N --who WHO` takes against a hold. Both new commands save the catalogue."),
        example="$ seedswap reserve tom-01 ana 4\nreserved 4 of tom-01 for ana\n$ seedswap take tom-01 8     # only 6 available\nseedswap: cannot take 8 from tom-01 (have 10, 6 available)",
        code={
            "seedswap/catalog.py::init": "self._holds = {}",
            "seedswap/catalog.py::on_remove": "self._holds.pop(pid, None)",
            "seedswap/catalog.py::take_sig": "def take(self, pid, n, who=None):",
            "seedswap/catalog.py::take_check": '''
                mine = self._holds.get(pid, {}).get(who, 0) if who is not None else 0
                if n <= 0 or n > self.available(pid) + mine:
                    raise ValueError(f"cannot take {n} from {pid} (have {packet.qty}, {self.available(pid)} available)")
            ''',
            "seedswap/catalog.py::on_take": '''
                if mine:
                    holds = self._holds[pid]
                    holds[who] -= min(n, mine)
                    if holds[who] == 0:
                        del holds[who]
                    if not holds:
                        del self._holds[pid]
            ''',
            "seedswap/catalog.py::methods": '''
                def available(self, pid):
                    return self.get(pid).qty - sum(self._holds.get(pid, {}).values())

                def reserved(self, pid):
                    self.get(pid)
                    return dict(self._holds.get(pid, {}))

                def reserve(self, pid, who, n):
                    if n <= 0:
                        raise ValueError("n must be positive")
                    if n > self.available(pid):
                        raise ValueError(f"only {self.available(pid)} of {pid} available")
                    holds = self._holds.setdefault(pid, {})
                    holds[who] = holds.get(who, 0) + n
                    @@slot hold_reserve

                def release(self, pid, who):
                    self.get(pid)
                    holds = self._holds.get(pid, {})
                    n = holds.pop(who, 0)
                    if not holds:
                        self._holds.pop(pid, None)
                    @@slot hold_release
                    return n
            ''',
            "seedswap/catalog.py::to_dict": 'd["holds"] = {pid: dict(h) for pid, h in sorted(self._holds.items())}',
            "seedswap/catalog.py::from_dict": 'cat._holds = {pid: dict(h) for pid, h in d.get("holds", {}).items()}',
            "seedswap/cli.py::take_flags": 'take.add_argument("--who", default=None, help="take against this person\'s hold")',
            "seedswap/cli.py::take_call": "left = cat.take(args.id, args.n, who=args.who)",
            "seedswap/cli.py::subcommands": '''
                res = sub.add_parser("reserve", help="hold units for a person")
                res.add_argument("id")
                res.add_argument("who")
                res.add_argument("n", type=int)
                rel = sub.add_parser("release", help="drop a person's hold")
                rel.add_argument("id")
                rel.add_argument("who")
            ''',
            "seedswap/cli.py::commands": '''
                def cmd_reserve(args, cat, out):
                    cat.reserve(args.id, args.who, args.n)
                    save(cat, args.db)
                    out.write(f"reserved {args.n} of {args.id} for {args.who}\\n")


                def cmd_release(args, cat, out):
                    n = cat.release(args.id, args.who)
                    save(cat, args.db)
                    out.write(f"released {n} of {args.id} from {args.who}\\n")
            ''',
            "seedswap/cli.py::registry": 'COMMANDS["reserve"] = cmd_reserve\nCOMMANDS["release"] = cmd_release',
        },
        readme=dd('''
            ## Reservations

            `Catalog.reserve(pid, who, n)` holds units for a person (at most `available(pid)`); `release(pid, who)` drops the
            hold and returns its size; `reserved(pid)` is `{who: units}`. `take(pid, n, who=None)` may only use available
            units, or, with `who`, that person's hold first plus available units. Removing a packet drops its holds; holds
            are saved as `to_dict()["holds"]`. Command line: `reserve ID WHO N`, `release ID WHO`, `take ID N --who WHO`.
        '''),
        vtests='''
            def test_reserve_basic(self):
                cat = stock()
                cat.reserve("tom-01", "ana", 4)
                self.assertEqual(cat.available("tom-01"), 6)
        ''',
        tests='''
            def test_reserve_and_available(self):
                cat = stock()
                cat.reserve("tom-01", "ana", 4)
                cat.reserve("tom-01", "ben", 3)
                cat.reserve("tom-01", "ana", 1)
                self.assertEqual(cat.reserved("tom-01"), {"ana": 5, "ben": 3})
                self.assertEqual(cat.available("tom-01"), 2)
                for args in (("tom-01", "cy", 3), ("tom-01", "cy", 0), ("tom-01", "cy", -1)):
                    with self.assertRaises(ValueError):
                        cat.reserve(*args)
                with self.assertRaises(KeyError):
                    cat.reserve("nope", "cy", 1)
                self.assertEqual(cat.reserved("tom-02"), {})
                self.assertEqual(cat.release("tom-01", "ana"), 5)
                self.assertEqual(cat.release("tom-01", "ana"), 0)
                self.assertEqual(cat.available("tom-01"), 7)
                cat.reserved("tom-01")["zed"] = 99
                self.assertEqual(cat.reserved("tom-01"), {"ben": 3})
                for fn in (cat.available, cat.reserved):
                    with self.assertRaises(KeyError):
                        fn("nope")
                with self.assertRaises(KeyError):
                    cat.release("nope", "ana")

            def test_take_respects_holds(self):
                cat = stock()
                cat.reserve("tom-01", "ana", 6)
                with self.assertRaises(ValueError):
                    cat.take("tom-01", 5)
                self.assertEqual(cat.get("tom-01").qty, 10)
                self.assertEqual(cat.take("tom-01", 4), 6)
                with self.assertRaises(ValueError):
                    cat.take("tom-01", 1)
                with self.assertRaises(ValueError):
                    cat.take("tom-01", 1, who="ben")
                self.assertEqual(cat.take("tom-01", 2, who="ana"), 4)
                self.assertEqual(cat.reserved("tom-01"), {"ana": 4})
                self.assertEqual(cat.available("tom-01"), 0)
                with self.assertRaises(ValueError):
                    cat.take("tom-01", 5, who="ana")
                self.assertEqual(cat.take("tom-01", 4, who="ana"), 0)
                with self.assertRaises(KeyError):
                    cat.get("tom-01")
                self.assertEqual(cat.to_dict()["holds"], {})

            def test_take_uses_hold_first(self):
                cat = stock()
                cat.reserve("tom-01", "ana", 6)
                cat.reserve("tom-01", "ben", 2)
                self.assertEqual(cat.take("tom-01", 8, who="ana"), 2)
                self.assertEqual(cat.reserved("tom-01"), {"ben": 2})
                self.assertEqual(cat.available("tom-01"), 0)

            def test_remove_drops_holds_and_save_load(self):
                cat = stock()
                cat.reserve("tom-01", "ana", 6)
                cat.reserve("kale-01", "ben", 1)
                self.assertEqual(cat.to_dict()["holds"], {"kale-01": {"ben": 1}, "tom-01": {"ana": 6}})
                again = Catalog.from_dict(cat.to_dict())
                self.assertEqual(again.reserved("tom-01"), {"ana": 6})
                self.assertEqual(again.available("kale-01"), 24)
                cat.remove("tom-01")
                cat.add(mk("tom-01", "tomato", "Roma", 10, date(2024, 9, 1)))
                self.assertEqual(cat.reserved("tom-01"), {})
                self.assertEqual(Catalog.from_dict({"packets": []}).to_dict()["holds"], {})

            def test_reservations_cli(self):
                self.seed()
                code, out, _ = self.run_cli("reserve", "bean-02", "ana", "4")
                self.assertEqual((code, out), (0, "reserved 4 of bean-02 for ana\\n"))
                self.assertEqual(self.catalog().reserved("bean-02"), {"ana": 4})
                code, out, err = self.run_cli("take", "bean-02", "37")
                self.assertEqual((code, out), (2, ""))
                self.assertTrue(err.startswith("seedswap: "))
                code, out, _ = self.run_cli("take", "bean-02", "10", "--who", "ana")
                self.assertEqual((code, out), (0, "bean-02: 30 left\\n"))
                code, out, _ = self.run_cli("release", "bean-02", "ana")
                self.assertEqual((code, out), (0, "released 0 of bean-02 from ana\\n"))
                self.run_cli("reserve", "kale-01", "ben", "5")
                code, out, _ = self.run_cli("release", "kale-01", "ben")
                self.assertEqual((code, out), (0, "released 5 of kale-01 from ben\\n"))
                self.assertEqual(self.catalog().reserved("kale-01"), {})
        ''',
        cross={
            "audit-log": {
                "reqs": ("`reserve` and `release` are recorded in the change log as well: `reserve` with `op` `reserve` and `delta` `+n`; `release` with `op` `release` and `delta` minus the units released (nothing is recorded when 0 units were held).",),
                "code": {
                    "seedswap/catalog.py::hold_reserve": 'self._record("reserve", pid, n)',
                    "seedswap/catalog.py::hold_release": '''
                        if n:
                            self._record("release", pid, -n)
                    ''',
                },
                "tests": fmt('''
                    def test_holds_are_logged(self):
                        cat = Catalog()
                        cat.add(mk("a-1", "pea", "Alderman", 9, date(2024, 1, 1)))
                        cat.reserve("a-1", "ana", 4)
                        cat.release("a-1", "nobody")
                        cat.release("a-1", "ana")
                        self.assertEqual([(e["op"], e["delta"]) for e in cat.__NOUN__()], [("add", 9), ("reserve", 4), ("release", -4)])
                ''', NOUN=noun)},
            "low-stock-hook": {"tests": '''
                def test_low_stock_still_fires_for_holders(self):
                    cat = Catalog()
                    seen = []
                    cat.on("low_stock", lambda p: seen.append(p.qty))
                    cat.add(mk("a-1", "pea", "Alderman", 9, date(2024, 1, 1)))
                    cat.reserve("a-1", "ana", 8)
                    cat.take("a-1", 8, who="ana")
                    self.assertEqual(seen, [1])
            '''},
        },
    ))
    return S


APP = App(
    name="seedswap", lang="python", title="the seed swap catalogue", role="a volunteer at the seed swap", key="SEED",
    base={
        "README.md": README + "\n@@blocks features\n",
        "seedswap/__init__.py": '"""seedswap: a catalogue for a community seed swap."""\n',
        "seedswap/__main__.py": "from .cli import main\n\nraise SystemExit(main())\n",
        "seedswap/catalog.py": CATALOG,
        "seedswap/render.py": RENDER,
        "seedswap/cli.py": CLI,
        ".gitignore": "__pycache__/\n*.pyc\nseeds.json\n",
    },
    visible={"tests/test_basic.py": VISIBLE},
    hidden={"tests/test_features.py": HIDDEN},
)

register_app("feature-py-seedswap", APP, make_slices, n=22, summary="seed swap catalogue: filters, sort, formats, paging, audit, hooks, holds")
