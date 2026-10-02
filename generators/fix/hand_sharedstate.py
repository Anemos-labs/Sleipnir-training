"""Shared mutable state: aliased containers, shallow copies, mutable defaults. Character sheets (python), a stock tally (ruby)."""
from fx import dd, family
from generators.fix._hand_kit import Base, Bug, tasks_from

# ------------------------------------------------------------------------------------------------------------------
# Base A (python): tabletop character sheets, templates, undo history.
# ------------------------------------------------------------------------------------------------------------------

A_README = dd('''
    # charsheet

    Character sheets for a tabletop campaign tool.

    * `Sheet(name, stats=None, inventory=None, tags=None)`: `stats` is a dict, `inventory` a list of `{"name", "qty"}`
      dicts, `tags` a list of strings. **A sheet owns its data**: the constructor copies what it is given (the
      containers *and* the item dicts), so changing an argument afterwards, or changing the sheet, never affects anything
      else. Two sheets created without arguments never share anything.
    * `sheet.find(name)` returns the item dict or `None`; `add_item(name, qty=1)` adds to the existing item or appends a
      new one and returns the new quantity.
    * `sheet.snapshot()` returns an independent copy of `{"stats", "inventory", "tags"}`; `sheet.restore(snap)` puts it back
      (and may be called again with the same snapshot: restoring must not hand the snapshot's containers to the sheet).
    * `sheet.clone(new_name)` returns an independent copy under a new name.
    * `History`: `commit(sheet)` pushes a snapshot, `undo(sheet)` restores the latest one (returns `False` if there is none).
    * `Template(base).spawn(name, stats=None, extra_items=())`: a new sheet with the template's stats (overridden key by key
      by `stats`), inventory and tags, plus the extra `{"name", "qty"}` items. Spawned sheets are independent of the template
      and of each other.
    * `Party(sheets).give_all(name, qty=1)` gives every member that item (adding to an existing one); every member gets
      its own entry.
''')

A_SHEET = dd('''
    class Sheet:
        def __init__(self, name, stats=None, inventory=None, tags=None):
            self.name = name
            self.stats = dict(stats or {})
            self.inventory = [dict(item) for item in (inventory or [])]
            self.tags = list(tags or [])

        def find(self, name):
            for item in self.inventory:
                if item["name"] == name:
                    return item
            return None

        def add_item(self, name, qty=1):
            item = self.find(name)
            if item is not None:
                item["qty"] += qty
                return item["qty"]
            self.inventory.append({"name": name, "qty": qty})
            return qty

        def snapshot(self):
            return {"stats": dict(self.stats), "inventory": [dict(i) for i in self.inventory], "tags": list(self.tags)}

        def restore(self, snap):
            self.stats = dict(snap["stats"])
            self.inventory = [dict(i) for i in snap["inventory"]]
            self.tags = list(snap["tags"])

        def clone(self, new_name):
            return Sheet(new_name, self.stats, self.inventory, self.tags)
''')

A_HISTORY = dd('''
    class History:
        def __init__(self):
            self._stack = []

        def commit(self, sheet):
            self._stack.append(sheet.snapshot())

        def undo(self, sheet):
            if not self._stack:
                return False
            sheet.restore(self._stack.pop())
            return True

        def depth(self):
            return len(self._stack)
''')

A_TEMPLATE = dd('''
    from .sheet import Sheet


    class Template:
        def __init__(self, base):
            self.base = base

        def spawn(self, name, stats=None, extra_items=()):
            merged = {**self.base.stats, **(stats or {})}
            sheet = Sheet(name, merged, self.base.inventory, self.base.tags)
            for item in extra_items:
                sheet.add_item(item["name"], item["qty"])
            return sheet
''')

A_PARTY = dd('''
    class Party:
        def __init__(self, sheets):
            self.sheets = list(sheets)

        def give_all(self, name, qty=1):
            entry = {"name": name, "qty": qty}
            for sheet in self.sheets:
                existing = sheet.find(name)
                if existing is not None:
                    existing["qty"] += qty
                else:
                    sheet.inventory.append(dict(entry))
''')

A_VISIBLE = {
    "tests/test_sheet.py": dd('''
        import unittest

        from charsheet.history import History
        from charsheet.sheet import Sheet


        class SheetTests(unittest.TestCase):
            def test_add_item(self):
                s = Sheet("Mira")
                self.assertEqual(s.add_item("torch", 2), 2)
                self.assertEqual(s.add_item("torch"), 3)
                self.assertEqual(s.find("torch")["qty"], 3)

            def test_undo(self):
                s = Sheet("Mira", stats={"str": 10})
                h = History()
                h.commit(s)
                s.stats["str"] = 12
                self.assertTrue(h.undo(s))
                self.assertEqual(s.stats["str"], 10)
                self.assertFalse(h.undo(s))


        if __name__ == "__main__":
            unittest.main()
    '''),
}

A_HIDDEN = {
    "tests/test_hidden_sheet.py": dd('''
        import unittest

        from charsheet.history import History
        from charsheet.party import Party
        from charsheet.sheet import Sheet
        from charsheet.template import Template


        def torchy(name="Mira"):
            return Sheet(name, {"str": 10, "dex": 12}, [{"name": "torch", "qty": 2}, {"name": "rope", "qty": 1}], ["scout"])


        class Ownership(unittest.TestCase):
            def test_fresh_sheets_share_nothing(self):
                a, b = Sheet("a"), Sheet("b")
                a.add_item("torch")
                a.stats["str"] = 9
                a.tags.append("x")
                self.assertEqual((b.inventory, b.stats, b.tags), ([], {}, []))

            def test_constructor_copies_its_arguments(self):
                stats = {"str": 10}
                inv = [{"name": "torch", "qty": 2}]
                tags = ["scout"]
                s = Sheet("a", stats, inv, tags)
                stats["str"] = 99
                inv[0]["qty"] = 99
                inv.append({"name": "rope", "qty": 1})
                tags.append("x")
                self.assertEqual(s.stats, {"str": 10})
                self.assertEqual(s.inventory, [{"name": "torch", "qty": 2}])
                self.assertEqual(s.tags, ["scout"])

            def test_sheet_changes_do_not_leak_into_the_arguments(self):
                inv = [{"name": "torch", "qty": 2}]
                s = Sheet("a", None, inv, None)
                s.add_item("torch", 5)
                self.assertEqual(inv, [{"name": "torch", "qty": 2}])

            def test_add_item_and_find(self):
                s = torchy()
                self.assertEqual(s.add_item("rope", 4), 5)
                self.assertEqual(s.add_item("lamp"), 1)
                self.assertIsNone(s.find("ghost"))
                self.assertEqual([i["name"] for i in s.inventory], ["torch", "rope", "lamp"])


        class Cloning(unittest.TestCase):
            def test_clone_is_independent(self):
                a = torchy()
                b = a.clone("Mirror")
                self.assertEqual(b.name, "Mirror")
                b.add_item("torch", 10)
                b.add_item("axe")
                b.stats["str"] = 18
                b.tags.append("mirror")
                self.assertEqual(a.find("torch")["qty"], 2)
                self.assertIsNone(a.find("axe"))
                self.assertEqual(a.stats["str"], 10)
                self.assertEqual(a.tags, ["scout"])
                self.assertEqual(a.name, "Mira")

            def test_original_changes_do_not_reach_the_clone(self):
                a = torchy()
                b = a.clone("Mirror")
                a.add_item("torch", 3)
                self.assertEqual(b.find("torch")["qty"], 2)


        class Undo(unittest.TestCase):
            def test_undo_restores_quantities_and_lists(self):
                s = torchy()
                h = History()
                h.commit(s)
                s.add_item("torch", 5)
                s.add_item("axe")
                s.stats["str"] = 15
                s.tags.append("hero")
                self.assertTrue(h.undo(s))
                self.assertEqual(s.find("torch")["qty"], 2)
                self.assertIsNone(s.find("axe"))
                self.assertEqual(s.stats, {"str": 10, "dex": 12})
                self.assertEqual(s.tags, ["scout"])

            def test_snapshots_stack(self):
                s = torchy()
                h = History()
                h.commit(s)
                s.add_item("torch")
                h.commit(s)
                s.add_item("torch")
                self.assertEqual(h.depth(), 2)
                h.undo(s)
                self.assertEqual(s.find("torch")["qty"], 3)
                h.undo(s)
                self.assertEqual(s.find("torch")["qty"], 2)
                self.assertFalse(h.undo(s))

            def test_restore_twice_from_the_same_snapshot(self):
                s = torchy()
                snap = s.snapshot()
                s.add_item("torch", 4)
                s.restore(snap)
                s.add_item("torch", 1)
                s.tags.append("later")
                s.restore(snap)
                self.assertEqual(s.find("torch")["qty"], 2)
                self.assertEqual(s.tags, ["scout"])
                self.assertEqual(snap["inventory"][0]["qty"], 2)

            def test_snapshot_is_independent_of_later_changes(self):
                s = torchy()
                snap = s.snapshot()
                s.add_item("torch", 9)
                s.stats["dex"] = 1
                self.assertEqual(snap["inventory"][0]["qty"], 2)
                self.assertEqual(snap["stats"]["dex"], 12)


        class Templates(unittest.TestCase):
            def test_spawned_sheets_are_independent(self):
                t = Template(torchy("base"))
                a = t.spawn("a")
                b = t.spawn("b")
                a.add_item("torch", 5)
                a.tags.append("x")
                a.stats["str"] = 1
                self.assertEqual(b.find("torch")["qty"], 2)
                self.assertEqual(t.base.find("torch")["qty"], 2)
                self.assertEqual(b.tags, ["scout"])
                self.assertEqual(t.base.stats["str"], 10)

            def test_overrides_and_extras(self):
                t = Template(torchy("base"))
                s = t.spawn("c", stats={"dex": 15, "wis": 8}, extra_items=[{"name": "torch", "qty": 3}, {"name": "map", "qty": 1}])
                self.assertEqual(s.stats, {"str": 10, "dex": 15, "wis": 8})
                self.assertEqual(s.find("torch")["qty"], 5)
                self.assertEqual(s.find("map")["qty"], 1)
                self.assertEqual(t.base.find("torch")["qty"], 2)
                self.assertIsNone(t.base.find("map"))


        class Parties(unittest.TestCase):
            def test_give_all_gives_everyone_their_own_entry(self):
                a, b, c = Sheet("a"), Sheet("b"), torchy("c")
                party = Party([a, b, c])
                party.give_all("lantern", 1)
                party.give_all("torch", 2)
                a.add_item("lantern", 4)
                self.assertEqual(a.find("lantern")["qty"], 5)
                self.assertEqual(b.find("lantern")["qty"], 1)
                self.assertEqual(c.find("lantern")["qty"], 1)
                self.assertEqual(c.find("torch")["qty"], 4)
                self.assertEqual(a.find("torch")["qty"], 2)
                self.assertIsNot(a.find("torch"), b.find("torch"))


        if __name__ == "__main__":
            unittest.main()
    '''),
}


def _a_prompts():
    p = {}
    p["default-shared"] = (
        "Every new character in the tool starts with the same inventory as the last one I edited: add a torch to Mira and "
        "a freshly created Bran already carries it. Characters created with an explicit inventory are fine. Please find out "
        "why blank sheets are connected."
    )
    p["clone-shallow"] = (
        "Cloning a character for the \"mirror image\" spell and then spending the clone's torches also spends the "
        "original's, and the clone's tags show up on the original. `clone()` is supposed to give an independent copy."
    )
    p["items-shared"] = (
        "I spawn three guards from a template that has `torch x2`. When the first guard burns a torch, all three (and the "
        "template) show `torch x1`. Adding items works fine, only changing the quantity of an existing item is shared. "
        "Lists and dicts of the sheets themselves seem separate."
    )
    p["snapshot-ref"] = (
        "Undo in the sheet editor does nothing useful: after a commit, changing a stat and pressing undo, the stat stays "
        "changed. The history shows the right depth, so the commit happens. I suspect `snapshot()`."
    )
    p["give-all-shared"] = (
        "After the party gets a shared lantern with `give_all`, when one player adds a second lantern to their own sheet "
        "everybody in the party ends up with two. The README says every member gets their own entry."
    )
    p["items-and-snapshot"] = (
        "Two odd things in the sheet tool that I could only reproduce with a test script: quantities of spawned sheets are "
        "linked together, and after an undo the item quantities are still the new ones even though the stats come back. "
        "Please fix the sharing wherever it happens; the visible tests are not enough to catch it."
    )
    return p


def _base_a() -> Base:
    P = _a_prompts()
    good = {"README.md": A_README, "charsheet/__init__.py": '"""Character sheets."""\n', "charsheet/sheet.py": A_SHEET,
            "charsheet/history.py": A_HISTORY, "charsheet/template.py": A_TEMPLATE, "charsheet/party.py": A_PARTY}
    sh, pa = "charsheet/sheet.py", "charsheet/party.py"
    items = ("        self.inventory = [dict(item) for item in (inventory or [])]\n", "        self.inventory = list(inventory or [])\n")
    snap = ('        return {"stats": dict(self.stats), "inventory": [dict(i) for i in self.inventory], "tags": list(self.tags)}\n',
            '        return {"stats": dict(self.stats), "inventory": list(self.inventory), "tags": list(self.tags)}\n')
    bugs = [
        Bug("default-inventory-shared", 2, {sh: [
            ("    def __init__(self, name, stats=None, inventory=None, tags=None):\n", "    def __init__(self, name, stats=None, inventory=[], tags=None):\n"),
            ("        self.inventory = [dict(item) for item in (inventory or [])]\n", "        self.inventory = inventory\n")]}, P["default-shared"]),
        Bug("clone-shares-containers", 3, {sh: [("        return Sheet(new_name, self.stats, self.inventory, self.tags)\n",
                                                 "        import copy\n\n        twin = copy.copy(self)\n        twin.name = new_name\n        return twin\n")]}, P["clone-shallow"]),
        Bug("constructor-shares-item-dicts", 3, {sh: [items]}, P["items-shared"]),
        Bug("snapshot-by-reference", 3, {sh: [("        return {\"stats\": dict(self.stats), \"inventory\": [dict(i) for i in self.inventory], \"tags\": list(self.tags)}\n",
                                               "        return {\"stats\": self.stats, \"inventory\": self.inventory, \"tags\": self.tags}\n")]}, P["snapshot-ref"]),
        Bug("give-all-same-dict", 4, {pa: [("                sheet.inventory.append(dict(entry))\n", "                sheet.inventory.append(entry)\n")]}, P["give-all-shared"]),
        Bug("items-and-snapshot-shallow", 5, {sh: [items, snap]}, P["items-and-snapshot"]),
    ]
    return Base("charsheet", "python", good, A_VISIBLE, A_HIDDEN, bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base B (ruby): a stock tally with a ledger, settings and helpers.
# ------------------------------------------------------------------------------------------------------------------

B_README = dd('''
    # stocktally

    Small stock-keeping helpers (Ruby 3, `minitest`).

    ## `Stocktally::Ledger`
    * `record(sku, delta, bin: "A", note: nil)` appends an entry (a `Struct` with `sku`, `delta`, `bin`, `note`) and returns
      the ledger; `balance(sku)` sums the deltas; `skus` lists the distinct skus, sorted.
    * `notes_by_bin` returns a **plain** Hash `bin => [notes in entry order]` containing only bins that have at least one note
      (entries without a note are ignored; looking up another bin gives `nil`).
    * `snapshot` returns copies of the entries: later changes to the ledger, or to its entries, never show in a snapshot.

    ## `Stocktally`
    * `Stocktally.label(name)` returns a new, stripped, upper-case string; the argument is never modified.
    * `Stocktally.unique_sorted(skus)` returns a new sorted array without duplicates; the argument is never modified (and it
      works when there are no duplicates).

    ## `Stocktally::Settings`
    * `verbose` is `true` unless it was set; `verbose = false` must stick.
    * `bins` is the list of bin names: `%w[A B C]` unless set. Every Settings object owns its list (adding a bin to one never
      affects another object or the defaults), and `bins=` stores a copy of the array it is given.
''')

B_MAIN = dd('''
    require "stocktally/ledger"
    require "stocktally/settings"
    require "stocktally/util"
''')

B_LEDGER = dd('''
    module Stocktally
      Entry = Struct.new(:sku, :delta, :bin, :note)

      class Ledger
        attr_reader :entries

        def initialize
          @entries = []
        end

        def record(sku, delta, bin: "A", note: nil)
          @entries << Entry.new(sku, delta, bin, note)
          self
        end

        def balance(sku)
          @entries.select { |e| e.sku == sku }.sum(&:delta)
        end

        def skus
          @entries.map(&:sku).uniq.sort
        end

        def notes_by_bin
          @entries.each_with_object({}) do |e, groups|
            (groups[e.bin] ||= []) << e.note if e.note
          end
        end

        def snapshot
          @entries.map(&:dup)
        end
      end
    end
''')

B_SETTINGS = dd('''
    module Stocktally
      DEFAULT_BINS = %w[A B C].freeze

      class Settings
        attr_writer :verbose

        def verbose
          @verbose = true if @verbose.nil?
          @verbose
        end

        def bins
          @bins ||= DEFAULT_BINS.dup
        end

        def bins=(list)
          @bins = list.dup
        end
      end
    end
''')

B_UTIL = dd('''
    module Stocktally
      def self.label(name)
        name.strip.upcase
      end

      def self.unique_sorted(skus)
        skus.uniq.sort
      end
    end
''')

B_VISIBLE = {
    "test/test_basic.rb": dd('''
        require "minitest/autorun"
        require "stocktally"

        class TestBasic < Minitest::Test
          def test_balance
            l = Stocktally::Ledger.new
            l.record("nut", 5).record("nut", -2).record("bolt", 1)
            assert_equal 3, l.balance("nut")
            assert_equal %w[bolt nut], l.skus
          end

          def test_label
            assert_equal "NUT-A", Stocktally.label("  nut-a ")
          end

          def test_default_bins
            assert_equal %w[A B C], Stocktally::Settings.new.bins
          end
        end
    '''),
}

B_HIDDEN = {
    "test/test_hidden_stocktally.rb": dd('''
        require "minitest/autorun"
        require "stocktally"

        class TestHiddenStocktally < Minitest::Test
          def ledger
            Stocktally::Ledger.new
              .record("nut", 5, bin: "A", note: "first")
              .record("bolt", 2, bin: "B")
              .record("nut", -1, bin: "A", note: "damaged")
              .record("cog", 7, bin: "C", note: "new")
          end

          def test_notes_by_bin_is_a_plain_hash_of_arrays
            notes = ledger.notes_by_bin
            assert_equal({ "A" => %w[first damaged], "C" => %w[new] }, notes)
            assert_nil notes["B"]
            assert_nil notes["Z"]
            refute notes.key?("Z")
            assert_equal 2, notes.size
          end

          def test_notes_by_bin_of_an_empty_ledger
            assert_equal({}, Stocktally::Ledger.new.notes_by_bin)
          end

          def test_label_returns_a_new_string
            raw = "  nut-a "
            assert_equal "NUT-A", Stocktally.label(raw)
            assert_equal "  nut-a ", raw
            already = "BOLT"
            assert_equal "BOLT", Stocktally.label(already)
            assert_equal "BOLT", already
          end

          def test_label_of_a_frozen_string
            assert_equal "ABC", Stocktally.label("abc".freeze)
          end

          def test_unique_sorted_without_duplicates
            assert_equal %w[a b c], Stocktally.unique_sorted(%w[c a b])
          end

          def test_unique_sorted_with_duplicates_leaves_the_argument_alone
            input = %w[b a b c a]
            assert_equal %w[a b c], Stocktally.unique_sorted(input)
            assert_equal %w[b a b c a], input
          end

          def test_verbose
            s = Stocktally::Settings.new
            assert_equal true, s.verbose
            s.verbose = false
            assert_equal false, s.verbose
            s.verbose = true
            assert_equal true, s.verbose
            t = Stocktally::Settings.new
            t.verbose = false
            assert_equal false, t.verbose
          end

          def test_bins_are_per_object_and_the_default_is_untouched
            a = Stocktally::Settings.new
            a.bins << "D"
            b = Stocktally::Settings.new
            assert_equal %w[A B C D], a.bins
            assert_equal %w[A B C], b.bins
            assert_equal %w[A B C], Stocktally::DEFAULT_BINS
            assert Stocktally::DEFAULT_BINS.frozen?
          end

          def test_bins_setter_stores_a_copy
            s = Stocktally::Settings.new
            mine = %w[X Y]
            s.bins = mine
            mine << "Z"
            assert_equal %w[X Y], s.bins
            s.bins << "W"
            assert_equal %w[X Y Z], mine
          end

          def test_snapshot_is_independent
            l = ledger
            snap = l.snapshot
            l.entries.first.delta = 100
            l.record("late", 1)
            assert_equal 5, snap.first.delta
            assert_equal 4, snap.size
            assert_equal 5, l.snapshot.size
            assert_equal 99, l.balance("nut")
          end

          def test_snapshot_entries_can_be_changed_freely
            l = ledger
            snap = l.snapshot
            snap.first.note = "edited"
            assert_equal "first", l.entries.first.note
            assert_equal 7, l.balance("cog")
          end
        end
    '''),
}


def _b_prompts():
    p = {}
    p["notes-default"] = (
        "The notes report is always empty (`notes_by_bin` returns `{}`) although entries with notes are recorded, and a "
        "teammate says that asking for a missing bin gives back a weird empty array instead of nil. Please fix it in the ledger."
    )
    p["label-mutates"] = (
        "`Stocktally.label(sku)` changes the string it is given: the SKU column in the import preview gets upper-cased and "
        "stripped *in place*, and for strings that are already upper case the method returns nil, which then blows up "
        "further down. The label must be a new string."
    )
    p["verbose-or"] = (
        "`settings.verbose = false` has no effect: verbose stays true. Switching it to true works. I think the getter does not "
        "know the difference between \"not set\" and false."
    )
    p["uniq-bang"] = (
        "`Stocktally.unique_sorted` raises `NoMethodError: undefined method 'sort' for nil` when the list has no duplicates "
        "(an already clean list), and for lists with duplicates the caller's array is changed behind its back."
    )
    p["bins-shared"] = (
        "Adding a bin to one settings object (`settings.bins << \"D\"`) adds it to every settings object created later in "
        "the same process, and our test suite now depends on the order tests run in. The default list is supposed to be "
        "constant."
    )
    p["snapshot-shallow"] = (
        "Audit snapshots of the ledger are not snapshots: when a correction later edits an entry (`entries.first.delta = ...`), "
        "the snapshot taken before it shows the new value too, but appended entries are not shown. Please make snapshots real copies."
    )
    p["bins-and-snapshot"] = (
        "Two bugs that look unrelated: (1) the default bins list leaks between settings objects, and (2) editing an entry "
        "after taking a ledger snapshot changes the snapshot. The unit tests we ship only look at single objects, so "
        "they pass. Please fix both."
    )
    return p


def _base_b() -> Base:
    P = _b_prompts()
    good = {"README.md": B_README, "lib/stocktally.rb": B_MAIN, "lib/stocktally/ledger.rb": B_LEDGER,
            "lib/stocktally/settings.rb": B_SETTINGS, "lib/stocktally/util.rb": B_UTIL}
    le, se, ut = "lib/stocktally/ledger.rb", "lib/stocktally/settings.rb", "lib/stocktally/util.rb"
    shared_bins = [("  DEFAULT_BINS = %w[A B C].freeze\n", "  DEFAULT_BINS = %w[A B C]\n"), ("      @bins ||= DEFAULT_BINS.dup\n", "      @bins ||= DEFAULT_BINS\n")]
    shallow = ("      @entries.map(&:dup)\n", "      @entries.dup\n")
    bugs = [
        Bug("notes-hash-default-array", 2, {le: [("      @entries.each_with_object({}) do |e, groups|\n        (groups[e.bin] ||= []) << e.note if e.note\n      end\n",
                                                  "      groups = Hash.new([])\n      @entries.each { |e| groups[e.bin] << e.note if e.note }\n      groups\n")]}, P["notes-default"]),
        Bug("label-mutates-argument", 2, {ut: [("    name.strip.upcase\n", "    name.strip!\n    name.upcase!\n    name\n")]}, P["label-mutates"]),
        Bug("verbose-or-equals", 1, {se: [("      @verbose = true if @verbose.nil?\n      @verbose\n", "      @verbose ||= true\n")]}, P["verbose-or"]),
        Bug("unique-bang-returns-nil", 3, {ut: [("    skus.uniq.sort\n", "    skus.uniq!.sort\n")]}, P["uniq-bang"]),
        Bug("default-bins-shared", 3, {se: shared_bins}, P["bins-shared"]),
        Bug("snapshot-shares-entries", 3, {le: [shallow]}, P["snapshot-shallow"]),
        Bug("bins-and-snapshot", 5, {se: shared_bins, le: [shallow]}, P["bins-and-snapshot"]),
    ]
    return Base("stocktally", "ruby", good, B_VISIBLE, B_HIDDEN, bugs)


@family("fix-hand-shared-state", category="fix", lang="python", kind="fix", n=13,
        summary="aliased containers, shallow copies and shared defaults: character sheets (python), a stock tally (ruby)")
def gen(rng, n):
    return tasks_from([_base_a(), _base_b()])
