"""Histories and event logs in domain clothes (python, fix-py-3): editor undo, an equipment-loan event store, offline-synced counters, frame reassembly."""
from fx import Lib, dd

from generators.fix._pylib3 import chain, register_libs3

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# undotrail: undo/redo with typing coalescing and groups (multi-module)
# ======================================================================================================================

UNDOTRAIL_README = dd('''
    # undotrail

    Undo and redo for a small text editor. Edits are *commands* that can be applied to and taken back from a buffer;
    a history keeps them in undo steps and merges the keystrokes of one typing run into a single step.

    ## `undotrail.buffer`

    `Buffer(text="")` has the attribute `text`.

    * `insert(pos, s)`: put `s` at index `pos` (`0 <= pos <= len(text)`, else `ValueError`).
    * `delete(pos, n) -> str`: remove `n` characters from index `pos` and return them (`ValueError` unless
      `0 <= pos`, `0 <= n` and `pos + n <= len(text)`).

    ## `undotrail.commands`

    * `Insert(pos, text)`: `apply(buf)` inserts, `undo(buf)` removes it again.
    * `Delete(pos, n)`: `apply(buf)` removes `n` characters and remembers them in the attribute `removed` (`None`
      until applied); `undo(buf)` puts `removed` back at `pos`.
    * `merge(prev, nxt) -> command | None`: the single command that has the effect of `prev` followed by `nxt`,
      or `None` when they must stay separate. (Both are expected to have been applied already.)
      * Two `Insert`s merge when `nxt.pos == prev.pos + len(prev.text)`, `prev.text` does not end with a space or a
        newline and `nxt.text` contains no newline: the result is `Insert(prev.pos, prev.text + nxt.text)`.
      * Two `Delete`s merge when `nxt.pos == prev.pos` (forward delete: the result is `Delete(prev.pos, prev.n +
        nxt.n)` with `removed = prev.removed + nxt.removed`) or when `nxt.pos + nxt.n == prev.pos` (backspacing: the
        result is `Delete(nxt.pos, prev.n + nxt.n)` with `removed = nxt.removed + prev.removed`). The forward case is
        tried first. Both must have `removed` set.
      * Anything else does not merge.

    ## `undotrail.history`

    `History(buffer, max_steps=100)` (`ValueError` if `max_steps < 1`; both are kept as attributes). The history keeps a stack of undo steps (a step is
    a list of commands) and a stack of redo steps.

    * `do(cmd)`: apply the command to the buffer and clear the redo stack. Inside a `group()` the command is added to the
      group's step. Otherwise, if the newest undo step is *open* and its last command merges with `cmd`
      (`merge(last, cmd)`), the merged command replaces it; else `cmd` becomes a new open step. When there are more than
      `max_steps` undo steps the oldest ones are dropped.
    * `seal()`: close the newest step, so the next command starts a new one.
    * `group()`: a context manager; every command done inside becomes one undo step (closed when the block ends; a block
      that did nothing leaves no step; nesting a `group()` inside a group simply joins the outer group).
    * `undo() -> bool`: take back the newest step (its commands in reverse order), move it to the redo stack; `False`
      when there is nothing to undo. `redo() -> bool`: re-apply the newest redo step (commands in order) and move it back
      to the undo stack; `False` when there is nothing to redo. After `undo` or `redo` no step is open.
    * `can_undo`, `can_redo` (properties), `undo_steps()` and `redo_steps()` (the numbers of steps).
''')

UNDOTRAIL_BUFFER = dd('''
    """A text buffer."""


    class Buffer:
        def __init__(self, text=""):
            self.text = text

        def insert(self, pos, s):
            if not 0 <= pos <= len(self.text):
                raise ValueError("insert position out of range")
            self.text = self.text[:pos] + s + self.text[pos:]

        def delete(self, pos, n):
            if pos < 0 or n < 0 or pos + n > len(self.text):
                raise ValueError("delete range out of bounds")
            removed = self.text[pos:pos + n]
            self.text = self.text[:pos] + self.text[pos + n:]
            return removed
''')

UNDOTRAIL_COMMANDS = dd('''
    """Editing commands and how they merge."""


    class Insert:
        def __init__(self, pos, text):
            self.pos = pos
            self.text = text

        def apply(self, buf):
            buf.insert(self.pos, self.text)

        def undo(self, buf):
            buf.delete(self.pos, len(self.text))


    class Delete:
        def __init__(self, pos, n):
            self.pos = pos
            self.n = n
            self.removed = None

        def apply(self, buf):
            self.removed = buf.delete(self.pos, self.n)

        def undo(self, buf):
            buf.insert(self.pos, self.removed)


    def merge(prev, nxt):
        if isinstance(prev, Insert) and isinstance(nxt, Insert):
            if nxt.pos == prev.pos + len(prev.text) and not prev.text.endswith((" ", "\\n")) and "\\n" not in nxt.text:
                return Insert(prev.pos, prev.text + nxt.text)
            return None
        if isinstance(prev, Delete) and isinstance(nxt, Delete) and prev.removed is not None and nxt.removed is not None:
            if nxt.pos == prev.pos:
                out = Delete(prev.pos, prev.n + nxt.n)
                out.removed = prev.removed + nxt.removed
                return out
            if nxt.pos + nxt.n == prev.pos:
                out = Delete(nxt.pos, prev.n + nxt.n)
                out.removed = nxt.removed + prev.removed
                return out
        return None
''')

UNDOTRAIL_HISTORY = dd('''
    """Undo and redo stacks."""
    from contextlib import contextmanager

    from .commands import merge


    class History:
        def __init__(self, buffer, max_steps=100):
            if max_steps < 1:
                raise ValueError("max_steps must be at least 1")
            self.buffer = buffer
            self.max_steps = max_steps
            self._undo = []
            self._redo = []
            self._open = False
            self._group = None

        def _trim(self):
            while len(self._undo) > self.max_steps:
                self._undo.pop(0)

        def do(self, cmd):
            cmd.apply(self.buffer)
            self._redo.clear()
            if self._group is not None:
                self._group.append(cmd)
                return
            if self._open and self._undo:
                merged = merge(self._undo[-1][-1], cmd)
                if merged is not None:
                    self._undo[-1][-1] = merged
                    return
            self._undo.append([cmd])
            self._open = True
            self._trim()

        def seal(self):
            self._open = False

        @contextmanager
        def group(self):
            if self._group is not None:
                yield
                return
            self._group = []
            try:
                yield
            finally:
                step, self._group = self._group, None
                if step:
                    self._undo.append(step)
                    self._open = False
                    self._trim()

        def undo(self):
            if not self._undo:
                return False
            step = self._undo.pop()
            for cmd in reversed(step):
                cmd.undo(self.buffer)
            self._redo.append(step)
            self._open = False
            return True

        def redo(self):
            if not self._redo:
                return False
            step = self._redo.pop()
            for cmd in step:
                cmd.apply(self.buffer)
            self._undo.append(step)
            self._open = False
            return True

        @property
        def can_undo(self):
            return bool(self._undo)

        @property
        def can_redo(self):
            return bool(self._redo)

        def undo_steps(self):
            return len(self._undo)

        def redo_steps(self):
            return len(self._redo)
''')

UNDOTRAIL_VISIBLE = dd('''
    import unittest

    from undotrail.buffer import Buffer
    from undotrail.commands import Insert
    from undotrail.history import History


    class BasicTests(unittest.TestCase):
        def test_undo_redo(self):
            buf = Buffer("")
            h = History(buf)
            h.do(Insert(0, "abc"))
            h.seal()
            h.do(Insert(3, "!"))
            self.assertEqual(buf.text, "abc!")
            self.assertTrue(h.undo())
            self.assertEqual(buf.text, "abc")
            self.assertTrue(h.redo())
            self.assertEqual(buf.text, "abc!")


    if __name__ == "__main__":
        unittest.main()
''')

UNDOTRAIL_HIDDEN_BUFFER = dd('''
    import unittest

    from undotrail.buffer import Buffer
    from undotrail.commands import Delete, Insert, merge


    class BufferTests(unittest.TestCase):
        def test_insert(self):
            b = Buffer("held")
            b.insert(3, "lo wor")
            self.assertEqual(b.text, "hello word")
            b.insert(0, ">")
            b.insert(len(b.text), "<")
            self.assertEqual(b.text, ">hello word<")

        def test_insert_errors(self):
            b = Buffer("ab")
            for pos in (-1, 3, 99):
                with self.assertRaises(ValueError):
                    b.insert(pos, "x")
            self.assertEqual(b.text, "ab")
            b.insert(2, "c")
            self.assertEqual(b.text, "abc")

        def test_delete(self):
            b = Buffer("hello world")
            self.assertEqual(b.delete(5, 6), " world")
            self.assertEqual(b.text, "hello")
            self.assertEqual(b.delete(0, 0), "")
            self.assertEqual(b.delete(4, 1), "o")
            self.assertEqual(b.text, "hell")
            self.assertEqual(b.delete(0, 4), "hell")
            self.assertEqual(b.text, "")

        def test_delete_errors(self):
            b = Buffer("abc")
            for pos, n in ((-1, 1), (0, -1), (2, 2), (4, 0), (0, 4)):
                with self.assertRaises(ValueError, msg=(pos, n)):
                    b.delete(pos, n)
            self.assertEqual(b.text, "abc")
            b.delete(3, 0)
            b.delete(1, 2)
            self.assertEqual(b.text, "a")

        def test_default_text(self):
            self.assertEqual(Buffer().text, "")


    class CommandTests(unittest.TestCase):
        def test_insert_command(self):
            b = Buffer("ad")
            c = Insert(1, "bc")
            c.apply(b)
            self.assertEqual(b.text, "abcd")
            c.undo(b)
            self.assertEqual(b.text, "ad")

        def test_delete_command(self):
            b = Buffer("abcd")
            c = Delete(1, 2)
            self.assertIsNone(c.removed)
            c.apply(b)
            self.assertEqual((b.text, c.removed), ("ad", "bc"))
            c.undo(b)
            self.assertEqual(b.text, "abcd")
            c.apply(b)
            self.assertEqual(b.text, "ad")


    def applied(cmd, text):
        buf = Buffer(text)
        cmd.apply(buf)
        return cmd


    class Merging(unittest.TestCase):
        def test_typing_run(self):
            m = merge(Insert(0, "he"), Insert(2, "l"))
            self.assertIsInstance(m, Insert)
            self.assertEqual((m.pos, m.text), (0, "hel"))
            m = merge(Insert(5, "a"), Insert(6, "bc"))
            self.assertEqual((m.pos, m.text), (5, "abc"))

        def test_inserts_that_must_not_merge(self):
            self.assertIsNone(merge(Insert(0, "he"), Insert(3, "l")))          # not adjacent
            self.assertIsNone(merge(Insert(0, "he"), Insert(1, "l")))          # inside the previous text
            self.assertIsNone(merge(Insert(0, "he "), Insert(3, "w")))         # a space ends a run
            self.assertIsNone(merge(Insert(0, "he\\n"), Insert(3, "w")))        # so does a newline
            self.assertIsNone(merge(Insert(0, "he"), Insert(2, "l\\nx")))       # a newline in the new text
            self.assertIsNone(merge(Insert(2, "a"), Insert(0, "b")))

        def test_space_in_new_text_is_fine(self):
            m = merge(Insert(0, "he"), Insert(2, " "))
            self.assertEqual(m.text, "he ")
            m = merge(Insert(0, "a"), Insert(1, "b c"))
            self.assertEqual(m.text, "ab c")

        def test_backspacing(self):
            first = applied(Delete(4, 1), "hello")
            second = applied(Delete(3, 1), "hell")
            m = merge(first, second)
            self.assertIsInstance(m, Delete)
            self.assertEqual((m.pos, m.n, m.removed), (3, 2, "lo"))

        def test_forward_delete(self):
            first = applied(Delete(1, 1), "hello")
            second = applied(Delete(1, 1), "hllo")
            m = merge(first, second)
            self.assertEqual((m.pos, m.n, m.removed), (1, 2, "el"))
            first = applied(Delete(1, 2), "abcdef")
            second = applied(Delete(1, 3), "adef")
            m = merge(first, second)
            self.assertEqual((m.pos, m.n, m.removed), (1, 5, "bcdef"))

        def test_multi_character_backspace(self):
            first = applied(Delete(6, 2), "abcdefgh")
            second = applied(Delete(3, 3), "abcdef")
            m = merge(first, second)
            self.assertEqual((m.pos, m.n, m.removed), (3, 5, "defgh"))

        def test_deletes_that_must_not_merge(self):
            first = applied(Delete(4, 1), "hello world")
            self.assertIsNone(merge(first, applied(Delete(0, 1), "hell world")))
            self.assertIsNone(merge(first, applied(Delete(6, 1), "hell world")))
            self.assertIsNone(merge(first, applied(Delete(2, 1), "hell world")))

        def test_unapplied_deletes_do_not_merge(self):
            self.assertIsNone(merge(Delete(4, 1), Delete(3, 1)))
            self.assertIsNone(merge(applied(Delete(4, 1), "hello"), Delete(3, 1)))

        def test_mixed_commands(self):
            self.assertIsNone(merge(Insert(0, "a"), applied(Delete(0, 1), "a")))
            self.assertIsNone(merge(applied(Delete(0, 1), "a"), Insert(0, "a")))

        def test_merged_command_has_the_same_effect(self):
            b1 = Buffer("")
            for c in (Insert(0, "he"), Insert(2, "llo")):
                c.apply(b1)
            b2 = Buffer("")
            m = merge(Insert(0, "he"), Insert(2, "llo"))
            m.apply(b2)
            self.assertEqual(b1.text, b2.text)
            m.undo(b2)
            self.assertEqual(b2.text, "")


    if __name__ == "__main__":
        unittest.main()
''')

UNDOTRAIL_HIDDEN_HISTORY = dd('''
    import unittest

    from undotrail.buffer import Buffer
    from undotrail.commands import Delete, Insert
    from undotrail.history import History


    def typed(h, pos, text):
        for i, ch in enumerate(text):
            h.do(Insert(pos + i, ch))


    class Construction(unittest.TestCase):
        def test_defaults_and_validation(self):
            h = History(Buffer("x"))
            self.assertEqual((h.max_steps, h.can_undo, h.can_redo, h.undo_steps(), h.redo_steps()), (100, False, False, 0, 0))
            for n in (0, -1):
                with self.assertRaises(ValueError):
                    History(Buffer(), max_steps=n)
            History(Buffer(), max_steps=1)

        def test_nothing_to_undo_or_redo(self):
            h = History(Buffer("x"))
            self.assertFalse(h.undo())
            self.assertFalse(h.redo())
            self.assertEqual(h.buffer.text, "x")


    class Typing(unittest.TestCase):
        def test_a_run_is_one_step(self):
            buf = Buffer("")
            h = History(buf)
            typed(h, 0, "hello")
            self.assertEqual((buf.text, h.undo_steps()), ("hello", 1))
            self.assertTrue(h.undo())
            self.assertEqual(buf.text, "")
            self.assertFalse(h.can_undo)
            self.assertEqual(h.redo_steps(), 1)
            self.assertTrue(h.redo())
            self.assertEqual(buf.text, "hello")

        def test_space_ends_a_run(self):
            buf = Buffer("")
            h = History(buf)
            typed(h, 0, "hi ")
            typed(h, 3, "there")
            self.assertEqual((buf.text, h.undo_steps()), ("hi there", 2))
            h.undo()
            self.assertEqual(buf.text, "hi ")
            h.undo()
            self.assertEqual(buf.text, "")

        def test_newline_ends_a_run(self):
            buf = Buffer("")
            h = History(buf)
            typed(h, 0, "ab")
            h.do(Insert(2, "\\n"))
            typed(h, 3, "cd")
            self.assertEqual(h.undo_steps(), 3)

        def test_cursor_jump_starts_a_new_step(self):
            buf = Buffer("")
            h = History(buf)
            typed(h, 0, "abc")
            h.do(Insert(0, "X"))
            self.assertEqual((buf.text, h.undo_steps()), ("Xabc", 2))
            h.undo()
            self.assertEqual(buf.text, "abc")

        def test_seal_splits_a_run(self):
            buf = Buffer("")
            h = History(buf)
            typed(h, 0, "ab")
            h.seal()
            typed(h, 2, "cd")
            self.assertEqual(h.undo_steps(), 2)
            h.undo()
            self.assertEqual(buf.text, "ab")

        def test_undo_closes_the_run(self):
            buf = Buffer("")
            h = History(buf)
            typed(h, 0, "ab")
            h.seal()
            typed(h, 2, "cd")
            h.undo()
            h.do(Insert(2, "e"))
            h.do(Insert(3, "f"))
            self.assertEqual(buf.text, "abef")
            self.assertEqual(h.undo_steps(), 2)
            h.undo()
            self.assertEqual(buf.text, "ab")

        def test_redo_closes_the_run(self):
            buf = Buffer("")
            h = History(buf)
            typed(h, 0, "ab")
            h.undo()
            h.redo()
            h.do(Insert(2, "c"))
            self.assertEqual(h.undo_steps(), 2)

        def test_new_edit_clears_redo(self):
            buf = Buffer("")
            h = History(buf)
            typed(h, 0, "ab")
            h.seal()
            typed(h, 2, "cd")
            h.undo()
            self.assertTrue(h.can_redo)
            h.do(Insert(2, "z"))
            self.assertFalse(h.can_redo)
            self.assertEqual(h.redo_steps(), 0)
            self.assertFalse(h.redo())
            self.assertEqual(buf.text, "abz")


    class Deleting(unittest.TestCase):
        def test_backspacing_is_one_step(self):
            buf = Buffer("hello")
            h = History(buf)
            h.do(Delete(4, 1))
            h.do(Delete(3, 1))
            h.do(Delete(2, 1))
            self.assertEqual((buf.text, h.undo_steps()), ("he", 1))
            h.undo()
            self.assertEqual(buf.text, "hello")
            h.redo()
            self.assertEqual(buf.text, "he")
            h.undo()
            self.assertEqual(buf.text, "hello")

        def test_forward_delete_is_one_step(self):
            buf = Buffer("hello")
            h = History(buf)
            h.do(Delete(1, 1))
            h.do(Delete(1, 1))
            self.assertEqual((buf.text, h.undo_steps()), ("hlo", 1))
            h.undo()
            self.assertEqual(buf.text, "hello")

        def test_different_kinds_do_not_merge(self):
            buf = Buffer("abc")
            h = History(buf)
            h.do(Delete(2, 1))
            h.do(Insert(2, "z"))
            h.do(Delete(2, 1))
            self.assertEqual(h.undo_steps(), 3)
            for expected in ("abz", "ab", "abc"):
                h.undo()
                self.assertEqual(buf.text, expected)

        def test_redo_after_merged_delete_restores_text(self):
            buf = Buffer("abcdef")
            h = History(buf)
            h.do(Delete(5, 1))
            h.do(Delete(4, 1))
            h.undo()
            h.redo()
            self.assertEqual(buf.text, "abcd")
            h.undo()
            h.redo()
            h.undo()
            self.assertEqual(buf.text, "abcdef")


    class Groups(unittest.TestCase):
        def test_group_is_one_step(self):
            buf = Buffer("abc")
            h = History(buf)
            with h.group():
                h.do(Insert(3, "d"))
                h.do(Insert(4, "e"))
                h.do(Delete(0, 1))
            self.assertEqual((buf.text, h.undo_steps()), ("bcde", 1))
            h.undo()
            self.assertEqual(buf.text, "abc")
            h.redo()
            self.assertEqual(buf.text, "bcde")

        def test_group_commands_do_not_merge_with_each_other_or_with_neighbours(self):
            buf = Buffer("")
            h = History(buf)
            typed(h, 0, "ab")
            with h.group():
                h.do(Insert(2, "c"))
                h.do(Insert(3, "d"))
            typed(h, 4, "ef")
            self.assertEqual(h.undo_steps(), 3)
            h.undo()
            self.assertEqual(buf.text, "abcd")
            h.undo()
            self.assertEqual(buf.text, "ab")

        def test_empty_group_leaves_nothing(self):
            h = History(Buffer("x"))
            with h.group():
                pass
            self.assertEqual(h.undo_steps(), 0)
            self.assertFalse(h.can_undo)

        def test_nested_groups_join_the_outer_one(self):
            buf = Buffer("")
            h = History(buf)
            with h.group():
                h.do(Insert(0, "a"))
                with h.group():
                    h.do(Insert(1, "b"))
                h.do(Insert(2, "c"))
            self.assertEqual(h.undo_steps(), 1)
            h.undo()
            self.assertEqual(buf.text, "")

        def test_group_clears_redo(self):
            buf = Buffer("")
            h = History(buf)
            h.do(Insert(0, "a"))
            h.undo()
            with h.group():
                h.do(Insert(0, "b"))
            self.assertFalse(h.can_redo)

        def test_group_ends_even_after_an_error(self):
            buf = Buffer("")
            h = History(buf)
            with self.assertRaises(ValueError):
                with h.group():
                    h.do(Insert(0, "a"))
                    h.do(Insert(9, "b"))
            self.assertEqual(h.undo_steps(), 1)
            h.do(Insert(1, "c"))
            h.do(Insert(2, "d"))
            self.assertEqual(h.undo_steps(), 2)
            h.undo()
            self.assertEqual(buf.text, "a")

        def test_group_step_is_closed(self):
            buf = Buffer("")
            h = History(buf)
            with h.group():
                h.do(Insert(0, "a"))
            h.do(Insert(1, "b"))
            self.assertEqual(h.undo_steps(), 2)


    class Limits(unittest.TestCase):
        def test_oldest_steps_are_dropped(self):
            buf = Buffer("")
            h = History(buf, max_steps=2)
            for i, ch in enumerate("abc"):
                h.do(Insert(0, ch))
            self.assertEqual((buf.text, h.undo_steps()), ("cba", 2))
            self.assertTrue(h.undo())
            self.assertTrue(h.undo())
            self.assertFalse(h.undo())
            self.assertEqual(buf.text, "a")

        def test_one_step_history(self):
            buf = Buffer("")
            h = History(buf, max_steps=1)
            h.do(Insert(0, "a"))
            h.do(Insert(0, "b"))
            self.assertEqual(h.undo_steps(), 1)
            h.undo()
            self.assertEqual(buf.text, "a")

        def test_groups_count_as_one_step_for_the_limit(self):
            buf = Buffer("")
            h = History(buf, max_steps=2)
            h.do(Insert(0, "a"))
            with h.group():
                h.do(Insert(0, "b"))
                h.do(Insert(0, "c"))
                h.do(Insert(0, "d"))
            h.do(Insert(0, "e"))
            self.assertEqual(h.undo_steps(), 2)
            h.undo()
            self.assertEqual(buf.text, "dcba")
            h.undo()
            self.assertEqual(buf.text, "a")

        def test_a_group_can_push_out_the_oldest_step(self):
            buf = Buffer("")
            h = History(buf, max_steps=2)
            h.do(Insert(0, "a"))
            h.seal()
            h.do(Insert(0, "b"))
            h.seal()
            with h.group():
                h.do(Insert(0, "c"))
            self.assertEqual(h.undo_steps(), 2)
            h.undo()
            h.undo()
            self.assertFalse(h.can_undo)
            self.assertEqual(buf.text, "a")

        def test_redo_can_exceed_nothing(self):
            buf = Buffer("")
            h = History(buf, max_steps=2)
            for ch in "abc":
                h.do(Insert(0, ch))
            h.undo()
            h.undo()
            self.assertEqual(h.redo_steps(), 2)
            h.redo()
            h.redo()
            self.assertEqual((buf.text, h.undo_steps(), h.redo_steps()), ("cba", 2, 0))


    class RoundTrips(unittest.TestCase):
        def test_undo_everything_then_redo_everything(self):
            buf = Buffer("seed")
            h = History(buf)
            snapshots = [buf.text]
            ops = [Insert(4, "s"), Insert(5, "!"), Delete(0, 2), Insert(0, "A"), Delete(1, 1)]
            for op in ops:
                h.do(op)
                h.seal()
                snapshots.append(buf.text)
            for expected in reversed(snapshots[:-1]):
                self.assertTrue(h.undo())
                self.assertEqual(buf.text, expected)
            self.assertFalse(h.can_undo)
            for expected in snapshots[1:]:
                self.assertTrue(h.redo())
                self.assertEqual(buf.text, expected)
            self.assertFalse(h.can_redo)


    if __name__ == "__main__":
        unittest.main()
''')

def _H(body, text="", max_steps=None):
    """A probe expression: a history over a buffer (named `buf`, history `h`) runs `body`."""
    hist = "History(buf)" if max_steps is None else f"History(buf, max_steps={max_steps})"
    return f"(lambda buf: (lambda h: {body})({hist}))(Buffer({text!r}))"


UNDOTRAIL = Lib(
    name="undotrail", lang="python", title="the undotrail editor history",
    blurb="The text editor uses undotrail to give users undo and redo that treats a burst of typing as one step.",
    files={
        "undotrail/__init__.py": "", "undotrail/buffer.py": UNDOTRAIL_BUFFER, "undotrail/commands.py": UNDOTRAIL_COMMANDS,
        "undotrail/history.py": UNDOTRAIL_HISTORY, "README.md": UNDOTRAIL_README, ".gitignore": GITIGNORE,
    },
    visible_tests={"tests/test_basic.py": UNDOTRAIL_VISIBLE},
    hidden_tests={"tests/test_buffer.py": UNDOTRAIL_HIDDEN_BUFFER, "tests/test_history.py": UNDOTRAIL_HIDDEN_HISTORY},
    mutate=["undotrail/buffer.py", "undotrail/commands.py", "undotrail/history.py"],
    difficulty=3, tags=["editor", "undo", "multi-module"],
    probes=[
        "[(m.pos, m.text) for m in [merge(Insert(0, 'he'), Insert(2, 'l'))]]",
        "merge(Insert(0, 'he '), Insert(3, 'w'))", "merge(Insert(0, 'he'), Insert(2, 'l\\nx'))",
        "(lambda b: [b.insert(1, 'XY'), b.text, b.delete(0, 2), b.text])(Buffer('abc'))",
        "(lambda b: b.delete(2, 2))(Buffer('abc'))",
        _H("[h.do(Insert(0, 'a')), h.do(Insert(1, 'b')), h.do(Insert(2, ' ')), h.do(Insert(3, 'c')), h.undo_steps(), buf.text]"),
        _H("[h.do(Insert(0, 'a')), h.do(Insert(1, 'b')), h.undo(), buf.text, h.redo(), buf.text]"),
        _H("[h.do(Insert(0, 'a')), h.seal(), h.do(Insert(1, 'b')), h.undo_steps()]"),
        _H("[h.do(Delete(4, 1)), h.do(Delete(3, 1)), h.undo_steps(), buf.text, h.undo(), buf.text]", "hello"),
        _H("[h.do(Delete(1, 1)), h.do(Delete(1, 1)), buf.text, h.undo(), buf.text]", "hello"),
        _H("[h.do(Insert(0, 'a')), h.undo(), h.do(Insert(0, 'b')), h.can_redo]"),
        _H("[h.do(Insert(0, c)) for c in 'abc'] + [h.undo_steps(), h.undo(), h.undo(), h.undo(), buf.text]", max_steps=2),
    ],
    probe_import="from undotrail.buffer import Buffer\nfrom undotrail.commands import Insert, Delete, merge\nfrom undotrail.history import History\n",
)

# ======================================================================================================================
# loanlog: an event-sourced equipment-loan desk (multi-module)
# ======================================================================================================================

LOANLOG_README = dd('''
    # loanlog

    The equipment-loan desk of a community workshop, built on event sourcing: nothing is updated in place, every change is
    an event appended to the stream of a workshop, and the current state is the fold of its events.

    ## `loanlog.events`

    `Event(stream, seq, type, version, data)` is a frozen dataclass (`seq` counts from 1 inside a stream). Event types and
    their latest versions: `ItemRegistered` (1), `Loaned` (2), `Returned` (2), `WrittenOff` (2). Old events stay in the
    store as they were written, so they are *upcast* when read: `Loaned` and `Returned` version 1 lack the field
    `borrower` and get `"unknown"`; `WrittenOff` version 1 lacks `reason` and gets `"unspecified"`.

    `upcast(event) -> Event`: the event at its latest version (the original is untouched; `data` is a new dict, the
    version number is raised step by step). `ValueError` for an unknown type or a version below 1 or above the latest.

    ## `loanlog.store`

    `ConcurrencyError` is a `ValueError`. `Store()`:

    * `version(stream) -> int`: the number of events in the stream (`0` for an unknown stream).
    * `append(stream, new_events, expected_version=None) -> list[Event]`: `new_events` is a list of
      `(type, version, data)` tuples. If `expected_version` is not `None` and differs from the stream's current version,
      raise `ConcurrencyError` and store nothing. Otherwise store the events with consecutive `seq` numbers and return
      them (the data is copied). Appending an empty list stores nothing and does not create the stream.
    * `read(stream, after=0) -> list[Event]`: the events with `seq > after` in order (`[]` for an unknown stream).
    * `streams() -> list[str]`: the names of the streams that have events, sorted.

    ## `loanlog.projection`

    The state is `{"stock": {item: {"total": int, "out": int}}, "loans": {borrower: {item: qty}}}`.

    * `initial()` returns the empty state. `apply(state, event) -> state` upcasts the event and returns a *new* state (the
      argument is never modified): `ItemRegistered` adds `qty` to `total` (creating the item); `Loaned` adds `qty` to
      `out` and to the borrower's loan of that item; `Returned` subtracts `qty` from `out` and from the borrower's loan,
      removing a loan that reaches 0 and a borrower with no loans left; `WrittenOff` subtracts `qty` from `total`.
    * `replay(events, state=None) -> state`: fold the events over `state` (the empty state by default).
    * `available(state, item) -> int`: `total - out`, `0` for an unknown item.
    * `Snapshot(stream, version, state)` is a frozen dataclass. `snapshot(store, stream) -> Snapshot` replays the whole
      stream. `load(store, stream, snap=None) -> (state, version)` returns the current state and the stream's version,
      starting from `snap` when given (replaying only the events after `snap.version`; `ValueError` if the snapshot is for
      another stream) and from the beginning otherwise. The snapshot's own state must not be modified.

    ## `loanlog.commands`

    * `decide(state, command) -> list[(type, version, data)]`: turn a command into new events, or `ValueError`. Commands are
      tuples: `("register", item, qty)` gives `ItemRegistered` v1 `{"item", "qty"}`; `("loan", item, qty, borrower)` gives
      `Loaned` v2 `{"item", "qty", "borrower"}`; `("return", item, qty, borrower)` gives `Returned` v2 with the same
      fields; `("writeoff", item, qty, reason)` gives `WrittenOff` v2 `{"item", "qty", "reason"}`. Rules: `qty` must be at
      least 1; a loan or write-off needs `available(state, item) >= qty` (an unknown item has none); a return needs the
      borrower to hold at least `qty` of the item; an unknown command kind is a `ValueError`.
    * `handle(store, stream, command) -> list[Event]`: `load` the stream, `decide`, and append the events with
      `expected_version` set to the version that was loaded.
''')

LOANLOG_EVENTS = dd('''
    """Events and upcasting."""
    from dataclasses import dataclass


    @dataclass(frozen=True)
    class Event:
        stream: str
        seq: int
        type: str
        version: int
        data: dict


    LATEST = {"ItemRegistered": 1, "Loaned": 2, "Returned": 2, "WrittenOff": 2}

    UPCASTERS = {
        ("Loaned", 1): lambda d: {**d, "borrower": "unknown"},
        ("Returned", 1): lambda d: {**d, "borrower": "unknown"},
        ("WrittenOff", 1): lambda d: {**d, "reason": "unspecified"},
    }


    def upcast(event):
        latest = LATEST.get(event.type)
        if latest is None:
            raise ValueError(f"unknown event type {event.type!r}")
        if not 1 <= event.version <= latest:
            raise ValueError(f"bad version {event.version} of {event.type}")
        data, version = dict(event.data), event.version
        while version < latest:
            data = UPCASTERS[(event.type, version)](data)
            version += 1
        return Event(event.stream, event.seq, event.type, version, data)
''')

LOANLOG_STORE = dd('''
    """An in-memory event store."""
    from .events import Event


    class ConcurrencyError(ValueError):
        pass


    class Store:
        def __init__(self):
            self._streams = {}

        def version(self, stream):
            return len(self._streams.get(stream, []))

        def append(self, stream, new_events, expected_version=None):
            current = self.version(stream)
            if expected_version is not None and expected_version != current:
                raise ConcurrencyError(f"expected version {expected_version}, but the stream is at {current}")
            stored = [Event(stream, current + i + 1, t, v, dict(d)) for i, (t, v, d) in enumerate(new_events)]
            if stored:
                self._streams.setdefault(stream, []).extend(stored)
            return stored

        def read(self, stream, after=0):
            return [e for e in self._streams.get(stream, []) if e.seq > after]

        def streams(self):
            return sorted(self._streams)
''')

LOANLOG_PROJECTION = dd('''
    """Folding events into state."""
    import copy
    from dataclasses import dataclass

    from .events import upcast


    def initial():
        return {"stock": {}, "loans": {}}


    def apply(state, event):
        ev = upcast(event)
        new = copy.deepcopy(state)
        d = ev.data
        if ev.type == "ItemRegistered":
            item = new["stock"].setdefault(d["item"], {"total": 0, "out": 0})
            item["total"] += d["qty"]
        elif ev.type == "Loaned":
            new["stock"][d["item"]]["out"] += d["qty"]
            held = new["loans"].setdefault(d["borrower"], {})
            held[d["item"]] = held.get(d["item"], 0) + d["qty"]
        elif ev.type == "Returned":
            new["stock"][d["item"]]["out"] -= d["qty"]
            held = new["loans"][d["borrower"]]
            held[d["item"]] -= d["qty"]
            if held[d["item"]] == 0:
                del held[d["item"]]
            if not held:
                del new["loans"][d["borrower"]]
        else:
            new["stock"][d["item"]]["total"] -= d["qty"]
        return new


    def replay(events, state=None):
        state = initial() if state is None else state
        for event in events:
            state = apply(state, event)
        return state


    def available(state, item):
        entry = state["stock"].get(item)
        return 0 if entry is None else entry["total"] - entry["out"]


    @dataclass(frozen=True)
    class Snapshot:
        stream: str
        version: int
        state: dict


    def snapshot(store, stream):
        return Snapshot(stream, store.version(stream), replay(store.read(stream)))


    def load(store, stream, snap=None):
        if snap is None:
            state, after = initial(), 0
        else:
            if snap.stream != stream:
                raise ValueError("snapshot belongs to another stream")
            state, after = snap.state, snap.version
        state = replay(store.read(stream, after), state)
        return state, store.version(stream)
''')

LOANLOG_COMMANDS = dd('''
    """Commands become events."""
    from .projection import available, load


    def decide(state, command):
        kind = command[0]
        if kind not in ("register", "loan", "return", "writeoff"):
            raise ValueError(f"unknown command {kind!r}")
        item, qty = command[1], command[2]
        if qty < 1:
            raise ValueError("quantity must be at least 1")
        if kind == "register":
            return [("ItemRegistered", 1, {"item": item, "qty": qty})]
        extra = command[3]
        if kind == "loan":
            if available(state, item) < qty:
                raise ValueError(f"not enough {item} on the shelf")
            return [("Loaned", 2, {"item": item, "qty": qty, "borrower": extra})]
        if kind == "return":
            if state["loans"].get(extra, {}).get(item, 0) < qty:
                raise ValueError(f"{extra} does not hold {qty} of {item}")
            return [("Returned", 2, {"item": item, "qty": qty, "borrower": extra})]
        if available(state, item) < qty:
            raise ValueError(f"not enough {item} to write off")
        return [("WrittenOff", 2, {"item": item, "qty": qty, "reason": extra})]


    def handle(store, stream, command):
        state, version = load(store, stream)
        return store.append(stream, decide(state, command), expected_version=version)
''')

LOANLOG_VISIBLE = dd('''
    import unittest

    from loanlog.commands import handle
    from loanlog.projection import available, load
    from loanlog.store import Store


    class BasicTests(unittest.TestCase):
        def test_register_and_loan(self):
            store = Store()
            handle(store, "shop", ("register", "saw", 3))
            handle(store, "shop", ("loan", "saw", 1, "ann"))
            state, version = load(store, "shop")
            self.assertEqual(version, 2)
            self.assertEqual(available(state, "saw"), 2)


    if __name__ == "__main__":
        unittest.main()
''')

LOANLOG_HIDDEN_EVENTS = dd('''
    import unittest

    from loanlog.events import Event, upcast
    from loanlog.store import ConcurrencyError, Store


    def ev(type_, version, data, seq=1, stream="s"):
        return Event(stream, seq, type_, version, data)


    class Upcasting(unittest.TestCase):
        def test_v1_events_get_new_fields(self):
            got = upcast(ev("Loaned", 1, {"item": "saw", "qty": 1}, seq=4, stream="w"))
            self.assertEqual(got, Event("w", 4, "Loaned", 2, {"item": "saw", "qty": 1, "borrower": "unknown"}))
            got = upcast(ev("Returned", 1, {"item": "saw", "qty": 1}))
            self.assertEqual((got.version, got.data["borrower"]), (2, "unknown"))
            got = upcast(ev("WrittenOff", 1, {"item": "saw", "qty": 2}))
            self.assertEqual(got, Event("s", 1, "WrittenOff", 2, {"item": "saw", "qty": 2, "reason": "unspecified"}))

        def test_other_fields_are_kept(self):
            got = upcast(ev("Loaned", 1, {"item": "saw", "qty": 4}))
            self.assertEqual((got.data["item"], got.data["qty"]), ("saw", 4))
            self.assertEqual(sorted(got.data), ["borrower", "item", "qty"])

        def test_current_versions_are_unchanged(self):
            e = ev("Loaned", 2, {"item": "saw", "qty": 1, "borrower": "ann"})
            self.assertEqual(upcast(e), e)
            e = ev("ItemRegistered", 1, {"item": "saw", "qty": 5})
            self.assertEqual(upcast(e), e)
            e = ev("WrittenOff", 2, {"item": "saw", "qty": 1, "reason": "broken"})
            self.assertEqual(upcast(e).data["reason"], "broken")

        def test_the_original_is_not_modified(self):
            e = ev("Loaned", 1, {"item": "saw", "qty": 1})
            upcast(e)
            self.assertEqual((e.version, e.data), (1, {"item": "saw", "qty": 1}))
            fresh = upcast(ev("ItemRegistered", 1, {"item": "x", "qty": 1}))
            self.assertIsNot(fresh.data, e.data)

        def test_bad_events(self):
            for e in (ev("Loaned", 0, {}), ev("Loaned", 3, {}), ev("ItemRegistered", 2, {}), ev("Teleported", 1, {}), ev("Returned", -1, {})):
                with self.assertRaises(ValueError, msg=(e.type, e.version)):
                    upcast(e)

        def test_event_is_frozen(self):
            with self.assertRaises(Exception):
                ev("Loaned", 2, {}).seq = 9


    class StoreTests(unittest.TestCase):
        def test_append_and_read(self):
            s = Store()
            stored = s.append("a", [("ItemRegistered", 1, {"item": "x", "qty": 1}), ("Loaned", 2, {"item": "x", "qty": 1, "borrower": "b"})])
            self.assertEqual([(e.seq, e.type) for e in stored], [(1, "ItemRegistered"), (2, "Loaned")])
            self.assertEqual(s.version("a"), 2)
            more = s.append("a", [("Returned", 2, {"item": "x", "qty": 1, "borrower": "b"})])
            self.assertEqual(more[0].seq, 3)
            self.assertEqual([e.seq for e in s.read("a")], [1, 2, 3])
            self.assertEqual([e.seq for e in s.read("a", after=1)], [2, 3])
            self.assertEqual(s.read("a", after=3), [])
            self.assertEqual(s.read("a", 2)[0].type, "Returned")
            self.assertEqual(stored[0].stream, "a")

        def test_streams_are_independent(self):
            s = Store()
            s.append("b", [("ItemRegistered", 1, {"item": "x", "qty": 1})])
            s.append("a", [("ItemRegistered", 1, {"item": "y", "qty": 1})])
            self.assertEqual(s.streams(), ["a", "b"])
            self.assertEqual(s.version("a"), 1)
            self.assertEqual(s.read("a")[0].seq, 1)
            self.assertEqual(s.version("nope"), 0)
            self.assertEqual(s.read("nope"), [])

        def test_expected_version(self):
            s = Store()
            s.append("a", [("ItemRegistered", 1, {"item": "x", "qty": 1})], expected_version=0)
            s.append("a", [("ItemRegistered", 1, {"item": "x", "qty": 1})], expected_version=1)
            with self.assertRaises(ConcurrencyError):
                s.append("a", [("ItemRegistered", 1, {"item": "x", "qty": 1})], expected_version=1)
            with self.assertRaises(ConcurrencyError):
                s.append("a", [("ItemRegistered", 1, {"item": "x", "qty": 1})], expected_version=5)
            with self.assertRaises(ConcurrencyError):
                s.append("fresh", [("ItemRegistered", 1, {"item": "x", "qty": 1})], expected_version=1)
            self.assertEqual(s.version("a"), 2)
            self.assertEqual(s.version("fresh"), 0)
            self.assertTrue(issubclass(ConcurrencyError, ValueError))

        def test_expected_version_none_means_any(self):
            s = Store()
            s.append("a", [("ItemRegistered", 1, {"item": "x", "qty": 1})])
            s.append("a", [("ItemRegistered", 1, {"item": "x", "qty": 1})], expected_version=None)
            self.assertEqual(s.version("a"), 2)

        def test_empty_append(self):
            s = Store()
            self.assertEqual(s.append("a", []), [])
            self.assertEqual(s.streams(), [])
            self.assertEqual(s.append("a", [], expected_version=0), [])
            with self.assertRaises(ConcurrencyError):
                s.append("a", [], expected_version=2)

        def test_data_is_copied(self):
            s = Store()
            data = {"item": "x", "qty": 1}
            stored = s.append("a", [("ItemRegistered", 1, data)])
            data["qty"] = 99
            self.assertEqual(s.read("a")[0].data["qty"], 1)
            self.assertEqual(stored[0].data["qty"], 1)


    if __name__ == "__main__":
        unittest.main()
''')

LOANLOG_HIDDEN_PROJECTION = dd('''
    import unittest

    from loanlog.events import Event
    from loanlog.projection import Snapshot, apply, available, initial, load, replay, snapshot
    from loanlog.store import Store


    def e(seq, type_, version, **data):
        return Event("w", seq, type_, version, data)


    LOG = [
        e(1, "ItemRegistered", 1, item="saw", qty=5),
        e(2, "Loaned", 2, item="saw", qty=2, borrower="ann"),
        e(3, "Loaned", 1, item="saw", qty=1),
        e(4, "Returned", 2, item="saw", qty=1, borrower="ann"),
        e(5, "WrittenOff", 1, item="saw", qty=1),
    ]


    class Folding(unittest.TestCase):
        def test_initial(self):
            self.assertEqual(initial(), {"stock": {}, "loans": {}})
            self.assertIsNot(initial(), initial())

        def test_replay(self):
            state = replay(LOG)
            self.assertEqual(state, {
                "stock": {"saw": {"total": 4, "out": 2}},
                "loans": {"ann": {"saw": 1}, "unknown": {"saw": 1}},
            })
            self.assertEqual(available(state, "saw"), 2)
            self.assertEqual(replay([]), initial())

        def test_register_adds_up(self):
            state = replay([e(1, "ItemRegistered", 1, item="a", qty=2), e(2, "ItemRegistered", 1, item="a", qty=3), e(3, "ItemRegistered", 1, item="b", qty=1)])
            self.assertEqual(state["stock"], {"a": {"total": 5, "out": 0}, "b": {"total": 1, "out": 0}})

        def test_loans_accumulate_per_borrower_and_item(self):
            state = replay([
                e(1, "ItemRegistered", 1, item="a", qty=9), e(2, "ItemRegistered", 1, item="b", qty=9),
                e(3, "Loaned", 2, item="a", qty=1, borrower="x"), e(4, "Loaned", 2, item="a", qty=2, borrower="x"),
                e(5, "Loaned", 2, item="b", qty=1, borrower="x"), e(6, "Loaned", 2, item="a", qty=1, borrower="y"),
            ])
            self.assertEqual(state["loans"], {"x": {"a": 3, "b": 1}, "y": {"a": 1}})
            self.assertEqual(state["stock"]["a"]["out"], 4)

        def test_returns_clean_up(self):
            base = [
                e(1, "ItemRegistered", 1, item="a", qty=5), e(2, "ItemRegistered", 1, item="b", qty=5),
                e(3, "Loaned", 2, item="a", qty=2, borrower="x"), e(4, "Loaned", 2, item="b", qty=1, borrower="x"),
            ]
            state = replay(base + [e(5, "Returned", 2, item="a", qty=1, borrower="x")])
            self.assertEqual(state["loans"], {"x": {"a": 1, "b": 1}})
            state = replay(base + [e(5, "Returned", 2, item="a", qty=2, borrower="x")])
            self.assertEqual(state["loans"], {"x": {"b": 1}})
            state = replay(base + [e(5, "Returned", 2, item="a", qty=2, borrower="x"), e(6, "Returned", 2, item="b", qty=1, borrower="x")])
            self.assertEqual(state["loans"], {})
            self.assertEqual(state["stock"], {"a": {"total": 5, "out": 0}, "b": {"total": 5, "out": 0}})

        def test_write_off_reduces_total_only(self):
            state = replay([e(1, "ItemRegistered", 1, item="a", qty=5), e(2, "WrittenOff", 2, item="a", qty=2, reason="rust")])
            self.assertEqual(state["stock"], {"a": {"total": 3, "out": 0}})
            self.assertEqual(available(state, "a"), 3)

        def test_apply_is_pure(self):
            state = replay(LOG[:2])
            before = {"stock": {"saw": {"total": 5, "out": 2}}, "loans": {"ann": {"saw": 2}}}
            self.assertEqual(state, before)
            new = apply(state, LOG[3])
            self.assertEqual(state, before)
            self.assertIsNot(new, state)
            self.assertEqual(new["loans"], {"ann": {"saw": 1}})
            new["stock"]["saw"]["total"] = 99
            self.assertEqual(state["stock"]["saw"]["total"], 5)

        def test_replay_continues_from_a_state(self):
            state = replay(LOG[:3])
            self.assertEqual(replay(LOG[3:], state), replay(LOG))
            self.assertEqual(state["stock"]["saw"]["out"], 3)

        def test_available_for_unknown_items(self):
            self.assertEqual(available(initial(), "nothing"), 0)
            self.assertEqual(available(replay(LOG), "other"), 0)


    class Snapshots(unittest.TestCase):
        def store(self):
            s = Store()
            s.append("w", [("ItemRegistered", 1, {"item": "saw", "qty": 5}), ("Loaned", 2, {"item": "saw", "qty": 2, "borrower": "ann"})])
            return s

        def test_snapshot(self):
            s = self.store()
            snap = snapshot(s, "w")
            self.assertEqual((snap.stream, snap.version), ("w", 2))
            self.assertEqual(snap.state, replay(s.read("w")))
            empty = snapshot(s, "nope")
            self.assertEqual((empty.version, empty.state), (0, initial()))
            with self.assertRaises(Exception):
                snap.version = 3

        def test_load_without_a_snapshot(self):
            s = self.store()
            state, version = load(s, "w")
            self.assertEqual(version, 2)
            self.assertEqual(available(state, "saw"), 3)
            self.assertEqual(load(s, "nope"), (initial(), 0))

        def test_load_from_a_snapshot_replays_only_the_tail(self):
            s = self.store()
            snap = snapshot(s, "w")
            s.append("w", [("Returned", 2, {"item": "saw", "qty": 1, "borrower": "ann"}), ("WrittenOff", 2, {"item": "saw", "qty": 1, "reason": "x"})])
            state, version = load(s, "w", snap)
            self.assertEqual(version, 4)
            self.assertEqual(state, replay(s.read("w")))
            self.assertEqual(state["stock"]["saw"], {"total": 4, "out": 1})
            # the snapshot itself is still the old state
            self.assertEqual(snap.state["stock"]["saw"], {"total": 5, "out": 2})
            self.assertEqual(snap.version, 2)

        def test_a_snapshot_is_trusted(self):
            s = self.store()
            fake = Snapshot("w", 2, {"stock": {"saw": {"total": 100, "out": 0}}, "loans": {}})
            state, version = load(s, "w", fake)
            self.assertEqual((state["stock"]["saw"]["total"], version), (100, 2))

        def test_snapshot_of_another_stream(self):
            s = self.store()
            with self.assertRaises(ValueError):
                load(s, "other", snapshot(s, "w"))

        def test_snapshot_at_the_current_version(self):
            s = self.store()
            snap = snapshot(s, "w")
            state, version = load(s, "w", snap)
            self.assertEqual((state, version), (snap.state, 2))


    if __name__ == "__main__":
        unittest.main()
''')

LOANLOG_HIDDEN_COMMANDS = dd('''
    import unittest

    from loanlog.commands import decide, handle
    from loanlog.projection import available, initial, load, replay
    from loanlog.store import Store


    def state_with(*cmds):
        store = Store()
        for c in cmds:
            handle(store, "w", c)
        return load(store, "w")[0]


    class Deciding(unittest.TestCase):
        def test_register(self):
            self.assertEqual(decide(initial(), ("register", "saw", 3)), [("ItemRegistered", 1, {"item": "saw", "qty": 3})])

        def test_loan(self):
            st = state_with(("register", "saw", 3))
            self.assertEqual(decide(st, ("loan", "saw", 2, "ann")), [("Loaned", 2, {"item": "saw", "qty": 2, "borrower": "ann"})])
            self.assertEqual(decide(st, ("loan", "saw", 3, "ann"))[0][2]["qty"], 3)

        def test_loan_rules(self):
            st = state_with(("register", "saw", 3), ("loan", "saw", 2, "ann"))
            for cmd in (("loan", "saw", 2, "bob"), ("loan", "drill", 1, "bob"), ("loan", "saw", 0, "bob"), ("loan", "saw", -1, "bob")):
                with self.assertRaises(ValueError, msg=cmd):
                    decide(st, cmd)
            self.assertEqual(decide(st, ("loan", "saw", 1, "bob"))[0][0], "Loaned")

        def test_return(self):
            st = state_with(("register", "saw", 3), ("loan", "saw", 2, "ann"))
            self.assertEqual(decide(st, ("return", "saw", 2, "ann")), [("Returned", 2, {"item": "saw", "qty": 2, "borrower": "ann"})])
            self.assertEqual(decide(st, ("return", "saw", 1, "ann"))[0][2]["qty"], 1)

        def test_return_rules(self):
            st = state_with(("register", "saw", 3), ("loan", "saw", 2, "ann"))
            for cmd in (("return", "saw", 3, "ann"), ("return", "saw", 1, "bob"), ("return", "drill", 1, "ann"), ("return", "saw", 0, "ann")):
                with self.assertRaises(ValueError, msg=cmd):
                    decide(st, cmd)

        def test_write_off(self):
            st = state_with(("register", "saw", 3), ("loan", "saw", 2, "ann"))
            self.assertEqual(decide(st, ("writeoff", "saw", 1, "rust")), [("WrittenOff", 2, {"item": "saw", "qty": 1, "reason": "rust"})])
            for cmd in (("writeoff", "saw", 2, "rust"), ("writeoff", "drill", 1, "x"), ("writeoff", "saw", 0, "x")):
                with self.assertRaises(ValueError, msg=cmd):
                    decide(st, cmd)

        def test_register_rules(self):
            for qty in (0, -3):
                with self.assertRaises(ValueError):
                    decide(initial(), ("register", "saw", qty))

        def test_unknown_command(self):
            for cmd in (("steal", "saw", 1), ("Loan", "saw", 1, "x")):
                with self.assertRaises(ValueError):
                    decide(initial(), cmd)


    class Handling(unittest.TestCase):
        def test_sequence(self):
            store = Store()
            handle(store, "w", ("register", "saw", 3))
            handle(store, "w", ("register", "drill", 1))
            handle(store, "w", ("loan", "saw", 2, "ann"))
            handle(store, "w", ("loan", "drill", 1, "bob"))
            handle(store, "w", ("return", "saw", 1, "ann"))
            state, version = load(store, "w")
            self.assertEqual(version, 5)
            self.assertEqual(state["stock"], {"saw": {"total": 3, "out": 1}, "drill": {"total": 1, "out": 1}})
            self.assertEqual(state["loans"], {"ann": {"saw": 1}, "bob": {"drill": 1}})

        def test_returns_the_stored_events(self):
            store = Store()
            got = handle(store, "w", ("register", "saw", 3))
            self.assertEqual([(e.stream, e.seq, e.type) for e in got], [("w", 1, "ItemRegistered")])
            got = handle(store, "w", ("loan", "saw", 1, "ann"))
            self.assertEqual([(e.seq, e.type) for e in got], [(2, "Loaned")])

        def test_failed_commands_store_nothing(self):
            store = Store()
            handle(store, "w", ("register", "saw", 1))
            with self.assertRaises(ValueError):
                handle(store, "w", ("loan", "saw", 2, "ann"))
            self.assertEqual(store.version("w"), 1)
            with self.assertRaises(ValueError):
                handle(store, "other", ("loan", "saw", 1, "ann"))
            self.assertEqual(store.streams(), ["w"])

        def test_streams_do_not_interfere(self):
            store = Store()
            handle(store, "a", ("register", "saw", 1))
            with self.assertRaises(ValueError):
                handle(store, "b", ("loan", "saw", 1, "x"))
            handle(store, "b", ("register", "saw", 1))
            handle(store, "b", ("loan", "saw", 1, "x"))
            self.assertEqual(available(load(store, "a")[0], "saw"), 1)
            self.assertEqual(available(load(store, "b")[0], "saw"), 0)

        def test_old_events_in_the_log_are_understood(self):
            store = Store()
            store.append("w", [("ItemRegistered", 1, {"item": "saw", "qty": 2}), ("Loaned", 1, {"item": "saw", "qty": 1})])
            handle(store, "w", ("loan", "saw", 1, "ann"))
            with self.assertRaises(ValueError):
                handle(store, "w", ("loan", "saw", 1, "bob"))
            handle(store, "w", ("return", "saw", 1, "unknown"))
            state, version = load(store, "w")
            self.assertEqual(version, 4)
            self.assertEqual(state["loans"], {"ann": {"saw": 1}})


    if __name__ == "__main__":
        unittest.main()
''')

_LL = "[('ItemRegistered', 1, {'item': 'saw', 'qty': 5}), ('Loaned', 2, {'item': 'saw', 'qty': 2, 'borrower': 'ann'}), ('Loaned', 1, {'item': 'saw', 'qty': 1}), ('Returned', 2, {'item': 'saw', 'qty': 1, 'borrower': 'ann'}), ('WrittenOff', 1, {'item': 'saw', 'qty': 1})]"


def _LS(body):
    """A probe expression: a store `s` holding the sample log in stream 'w' runs `body`."""
    return f"(lambda s: [s.append('w', {_LL}), {body}][1])(Store())"


LOANLOG = Lib(
    name="loanlog", lang="python", title="the loanlog event store",
    blurb="The workshop's loan desk keeps every tool loan as an event and relies on loanlog to rebuild the shelf and the borrowers' lists from them.",
    files={
        "loanlog/__init__.py": "", "loanlog/events.py": LOANLOG_EVENTS, "loanlog/store.py": LOANLOG_STORE,
        "loanlog/projection.py": LOANLOG_PROJECTION, "loanlog/commands.py": LOANLOG_COMMANDS,
        "README.md": LOANLOG_README, ".gitignore": GITIGNORE,
    },
    visible_tests={"tests/test_basic.py": LOANLOG_VISIBLE},
    hidden_tests={
        "tests/test_events.py": LOANLOG_HIDDEN_EVENTS, "tests/test_projection.py": LOANLOG_HIDDEN_PROJECTION,
        "tests/test_commands.py": LOANLOG_HIDDEN_COMMANDS,
    },
    mutate=["loanlog/events.py", "loanlog/store.py", "loanlog/projection.py", "loanlog/commands.py"],
    difficulty=4, tags=["event-sourcing", "cqrs", "multi-module"],
    probes=[
        "upcast(Event('w', 4, 'Loaned', 1, {'item': 'saw', 'qty': 1}))",
        "upcast(Event('w', 1, 'WrittenOff', 1, {'item': 'saw', 'qty': 2}))",
        "upcast(Event('w', 1, 'Loaned', 3, {}))",
        _LS("load(s, 'w')"), _LS("s.read('w', after=3)"), _LS("s.version('w')"),
        _LS("available(load(s, 'w')[0], 'saw')"),
        _LS("load(s, 'w', Snapshot('w', 2, replay(s.read('w')[:2])))"),
        _LS("snapshot(s, 'w').version"),
        _LS("[handle(s, 'w', ('loan', 'saw', 2, 'bob')), load(s, 'w')[0]['loans']]"),
        _LS("handle(s, 'w', ('loan', 'saw', 3, 'bob'))"),
        _LS("handle(s, 'w', ('return', 'saw', 1, 'ann'))"),
        "decide(initial(), ('register', 'saw', 3))", "decide(replay([Event('w', 1, 'ItemRegistered', 1, {'item': 'saw', 'qty': 3})]), ('writeoff', 'saw', 1, 'rust'))",
        "Store().append('a', [], expected_version=0)", "Store().streams()",
    ],
    probe_import=(
        "from loanlog.events import Event, upcast\nfrom loanlog.store import Store\n"
        "from loanlog.projection import initial, apply, replay, available, Snapshot, snapshot, load\n"
        "from loanlog.commands import decide, handle\n"
    ),
)

# ======================================================================================================================
# stallsync: counters and maps that merge after offline market days
# ======================================================================================================================

STALLSYNC_README = dd('''
    # stallsync

    Market stalls count sales and keep price lists on tablets that are offline most of the day. When the tablets meet again
    their copies are *merged*; the result must not depend on the order or on how often merging happens.

    ## `PNCounter(replica)`

    A counter that can go up and down; `replica` stays available as an attribute. It remembers, per replica name, the total of that replica's increments and the
    total of its decrements.

    * `incr(n=1)` and `decr(n=1)` record `n` more increments or decrements for *this* counter's replica (`ValueError` if
      `n < 1`). `value` (property) is all increments minus all decrements (it may be negative).
    * `merge(other) -> PNCounter`: a new counter for `self.replica` that has, for every replica name, the larger of the
      two counters' increment totals and the larger of their decrement totals. Neither operand changes.
    * `state() -> dict`: `{"inc": {...}, "dec": {...}}` with the per-replica totals, each dict ordered by replica name
      (only replicas that have a total appear).

    ## `LWWMap(replica)`

    A map where the last writer wins; `replica` stays available as an attribute. Every write carries a timestamp `ts` (an integer given by the caller).

    * `set(key, value, ts)` and `remove(key, ts)` write for this map's replica. A write takes effect only if its pair
      `(ts, replica)` is **greater** than the pair of the entry the key currently has (compared as a tuple, so equal
      timestamps are decided by the larger replica name; a write with an equal or smaller pair is ignored). A removal
      is an entry too (a tombstone) and blocks older writes.
    * `get(key, default=None)`: the value if the key's winning entry is a `set`, else `default`.
    * `items() -> list[(key, value)]`: the live entries sorted by key; `len(m)` is their number; `key in m` tells whether
      a key is live.
    * `merge(other) -> LWWMap`: a new map for `self.replica` that keeps, per key, the entry with the greater
      `(ts, replica)` pair (`self`'s entry when the pairs are equal). Neither operand changes.
''')

STALLSYNC_SRC = dd('''
    """Mergeable counters and maps."""


    class PNCounter:
        def __init__(self, replica):
            self.replica = replica
            self._inc = {}
            self._dec = {}

        def incr(self, n=1):
            if n < 1:
                raise ValueError("n must be at least 1")
            self._inc[self.replica] = self._inc.get(self.replica, 0) + n

        def decr(self, n=1):
            if n < 1:
                raise ValueError("n must be at least 1")
            self._dec[self.replica] = self._dec.get(self.replica, 0) + n

        @property
        def value(self):
            return sum(self._inc.values()) - sum(self._dec.values())

        def merge(self, other):
            out = PNCounter(self.replica)
            for name in set(self._inc) | set(other._inc):
                out._inc[name] = max(self._inc.get(name, 0), other._inc.get(name, 0))
            for name in set(self._dec) | set(other._dec):
                out._dec[name] = max(self._dec.get(name, 0), other._dec.get(name, 0))
            return out

        def state(self):
            return {"inc": dict(sorted(self._inc.items())), "dec": dict(sorted(self._dec.items()))}


    class LWWMap:
        def __init__(self, replica):
            self.replica = replica
            self._entries = {}

        def _write(self, key, ts, value, alive):
            current = self._entries.get(key)
            if current is None or (ts, self.replica) > (current[0], current[1]):
                self._entries[key] = (ts, self.replica, value, alive)

        def set(self, key, value, ts):
            self._write(key, ts, value, True)

        def remove(self, key, ts):
            self._write(key, ts, None, False)

        def get(self, key, default=None):
            entry = self._entries.get(key)
            return entry[2] if entry is not None and entry[3] else default

        def __contains__(self, key):
            entry = self._entries.get(key)
            return entry is not None and entry[3]

        def __len__(self):
            return sum(1 for e in self._entries.values() if e[3])

        def items(self):
            return sorted(((k, e[2]) for k, e in self._entries.items() if e[3]), key=lambda kv: kv[0])

        def merge(self, other):
            out = LWWMap(self.replica)
            for key in set(self._entries) | set(other._entries):
                mine, theirs = self._entries.get(key), other._entries.get(key)
                if mine is None:
                    out._entries[key] = theirs
                elif theirs is None or (mine[0], mine[1]) >= (theirs[0], theirs[1]):
                    out._entries[key] = mine
                else:
                    out._entries[key] = theirs
            return out
''')

STALLSYNC_VISIBLE = dd('''
    import unittest

    from stallsync.crdt import LWWMap, PNCounter


    class BasicTests(unittest.TestCase):
        def test_counter(self):
            a, b = PNCounter("a"), PNCounter("b")
            a.incr(5)
            b.incr(3)
            self.assertEqual(a.merge(b).value, 8)

        def test_map(self):
            m = LWWMap("a")
            m.set("apples", 3, ts=1)
            self.assertEqual(m.get("apples"), 3)


    if __name__ == "__main__":
        unittest.main()
''')

STALLSYNC_HIDDEN = dd('''
    import itertools
    import unittest

    from stallsync.crdt import LWWMap, PNCounter


    def counter(replica, incs=(), decs=()):
        c = PNCounter(replica)
        for n in incs:
            c.incr(n)
        for n in decs:
            c.decr(n)
        return c


    class Counter(unittest.TestCase):
        def test_basic(self):
            c = PNCounter("a")
            self.assertEqual((c.value, c.state()), (0, {"inc": {}, "dec": {}}))
            c.incr()
            c.incr(4)
            c.decr(2)
            self.assertEqual(c.value, 3)
            self.assertEqual(c.state(), {"inc": {"a": 5}, "dec": {"a": 2}})
            c.decr(10)
            self.assertEqual(c.value, -7)
            d = PNCounter("d")
            d.decr()
            d.decr()
            self.assertEqual((d.value, d.state()), (-2, {"inc": {}, "dec": {"d": 2}}))

        def test_validation(self):
            c = PNCounter("a")
            for n in (0, -1):
                with self.assertRaises(ValueError):
                    c.incr(n)
                with self.assertRaises(ValueError):
                    c.decr(n)
            self.assertEqual(c.value, 0)

        def test_merge_adds_different_replicas(self):
            a = counter("a", [5], [2])
            b = counter("b", [3])
            for m in (a.merge(b), b.merge(a)):
                self.assertEqual(m.value, 6)
                self.assertEqual(m.state(), {"inc": {"a": 5, "b": 3}, "dec": {"a": 2}})
            self.assertEqual(a.merge(b).replica, "a")
            self.assertEqual(b.merge(a).replica, "b")

        def test_merge_takes_the_maximum_for_the_same_replica(self):
            old = counter("a", [5], [1])
            new = counter("a", [5, 2], [1, 1])
            m = old.merge(new)
            self.assertEqual(m.state(), {"inc": {"a": 7}, "dec": {"a": 2}})
            self.assertEqual(new.merge(old).state(), m.state())
            self.assertEqual(m.value, 5)

        def test_merge_is_idempotent_commutative_associative(self):
            cs = [counter("a", [5], [2]), counter("b", [3, 1]), counter("c", [], [4]), counter("a", [5, 5], [2, 1])]
            for x in cs:
                self.assertEqual(x.merge(x).state(), x.state())
            for x, y in itertools.permutations(cs, 2):
                self.assertEqual(x.merge(y).state(), y.merge(x).state())
            for x, y, z in itertools.permutations(cs, 3):
                self.assertEqual(x.merge(y).merge(z).state(), x.merge(y.merge(z)).state())

        def test_merge_does_not_change_the_operands(self):
            a = counter("a", [5])
            b = counter("b", [3], [1])
            a.merge(b)
            self.assertEqual(a.state(), {"inc": {"a": 5}, "dec": {}})
            self.assertEqual(b.state(), {"inc": {"b": 3}, "dec": {"b": 1}})

        def test_merged_counter_keeps_counting_for_its_replica(self):
            a = counter("a", [5])
            m = a.merge(counter("b", [3]))
            m.incr(2)
            m.decr(1)
            self.assertEqual(m.state(), {"inc": {"a": 7, "b": 3}, "dec": {"a": 1}})
            self.assertEqual(m.value, 9)
            self.assertEqual(a.value, 5)

        def test_state_is_sorted_by_replica(self):
            m = counter("z", [1]).merge(counter("b", [1])).merge(counter("m", [1]))
            self.assertEqual(list(m.state()["inc"]), ["b", "m", "z"])
            big = counter("e", [1], [1])
            for name in ("a", "d", "b", "c"):
                big = big.merge(counter(name, [1], [1]))
            self.assertEqual(list(big.state()["inc"]), ["a", "b", "c", "d", "e"])
            self.assertEqual(list(big.state()["dec"]), ["a", "b", "c", "d", "e"])

        def test_stale_merge_cannot_lower_the_total(self):
            a = counter("a", [10])
            stale = counter("a", [3])
            self.assertEqual(a.merge(stale).value, 10)
            self.assertEqual(stale.merge(a).value, 10)


    class Map(unittest.TestCase):
        def test_set_get(self):
            m = LWWMap("a")
            self.assertIsNone(m.get("x"))
            self.assertEqual(m.get("x", 0), 0)
            m.set("x", 1, 5)
            m.set("y", 2, 5)
            self.assertEqual((m.get("x"), m.get("y")), (1, 2))
            self.assertEqual(len(m), 2)
            self.assertIn("x", m)
            self.assertNotIn("z", m)
            self.assertEqual(m.items(), [("x", 1), ("y", 2)])

        def test_items_are_sorted_by_key(self):
            m = LWWMap("a")
            for k in ("pear", "apple", "fig"):
                m.set(k, len(k), 1)
            self.assertEqual([k for k, _ in m.items()], ["apple", "fig", "pear"])

        def test_later_timestamp_wins_locally(self):
            m = LWWMap("a")
            m.set("x", "old", 5)
            m.set("x", "new", 6)
            self.assertEqual(m.get("x"), "new")
            m.set("x", "older", 4)
            self.assertEqual(m.get("x"), "new")
            m.set("x", "same", 6)
            self.assertEqual(m.get("x"), "new")

        def test_remove(self):
            m = LWWMap("a")
            m.set("x", 1, 5)
            m.remove("x", 6)
            self.assertIsNone(m.get("x"))
            self.assertNotIn("x", m)
            self.assertEqual((len(m), m.items()), (0, []))
            m.set("x", 2, 5)
            self.assertNotIn("x", m)
            m.set("x", 3, 7)
            self.assertEqual(m.get("x"), 3)
            m.remove("x", 7)
            self.assertEqual(m.get("x"), 3)
            m.remove("never-set", 1)
            self.assertEqual(len(m), 1)
            m.set("never-set", 1, 0)
            self.assertNotIn("never-set", m)

        def test_falsy_values_are_live(self):
            m = LWWMap("a")
            m.set("zero", 0, 1)
            m.set("none", None, 1)
            self.assertIn("zero", m)
            self.assertIn("none", m)
            self.assertEqual(len(m), 2)
            self.assertEqual(m.get("zero", "dflt"), 0)

        def test_merge_picks_the_newer_entry(self):
            a, b = LWWMap("a"), LWWMap("b")
            a.set("x", "from-a", 5)
            b.set("x", "from-b", 6)
            a.set("only-a", 1, 1)
            b.set("only-b", 2, 1)
            for m in (a.merge(b), b.merge(a)):
                self.assertEqual(m.items(), [("only-a", 1), ("only-b", 2), ("x", "from-b")])

        def test_equal_timestamps_go_to_the_larger_replica(self):
            a, b = LWWMap("a"), LWWMap("b")
            a.set("x", "from-a", 5)
            b.set("x", "from-b", 5)
            for m in (a.merge(b), b.merge(a)):
                self.assertEqual(m.get("x"), "from-b")
            c, d = LWWMap("b"), LWWMap("a")
            c.set("y", "from-b", 7)
            d.set("y", "from-a", 7)
            self.assertEqual(c.merge(d).get("y"), "from-b")

        def test_tombstones_travel(self):
            a, b = LWWMap("a"), LWWMap("b")
            a.set("x", 1, 5)
            b.merge(a)
            b2 = b.merge(a)
            b2.remove("x", 6)
            self.assertEqual(a.merge(b2).items(), [])
            self.assertEqual(b2.merge(a).items(), [])
            a.set("x", 9, 8)
            self.assertEqual(a.merge(b2).items(), [("x", 9)])
            self.assertEqual(b2.merge(a).items(), [("x", 9)])

        def test_remove_loses_to_a_later_set_and_wins_over_an_earlier_one(self):
            a, b = LWWMap("a"), LWWMap("b")
            a.set("x", 1, 5)
            b.remove("x", 4)
            self.assertEqual(a.merge(b).get("x"), 1)
            b.remove("x", 6)
            self.assertNotIn("x", a.merge(b))

        def test_merge_laws(self):
            maps = []
            for name, writes in (("a", [("x", 1, 1), ("y", 2, 5)]), ("b", [("x", 3, 2), ("z", 4, 1)]), ("c", [("y", 5, 5), ("x", 6, 2)])):
                m = LWWMap(name)
                for k, v, ts in writes:
                    m.set(k, v, ts)
                maps.append(m)
            maps[1].remove("z", 3)
            for x in maps:
                self.assertEqual(x.merge(x).items(), x.items())
            for x, y in itertools.permutations(maps, 2):
                self.assertEqual(x.merge(y).items(), y.merge(x).items())
            for x, y, z in itertools.permutations(maps, 3):
                self.assertEqual(x.merge(y).merge(z).items(), x.merge(y.merge(z)).items())

        def test_merge_keeps_the_receivers_entry_on_exact_ties(self):
            a1, a2 = LWWMap("a"), LWWMap("a")
            a1.set("x", "first", 5)
            a2.set("x", "second", 5)
            self.assertEqual(a1.merge(a2).get("x"), "first")
            self.assertEqual(a2.merge(a1).get("x"), "second")

        def test_merge_is_pure_and_keeps_the_replica(self):
            a, b = LWWMap("a"), LWWMap("b")
            a.set("x", 1, 1)
            b.set("y", 2, 1)
            m = a.merge(b)
            self.assertEqual((a.items(), b.items()), ([("x", 1)], [("y", 2)]))
            self.assertEqual(m.replica, "a")
            m.set("x", 5, 2)
            m.set("q", 1, 1)
            self.assertEqual(a.get("x"), 1)
            self.assertNotIn("q", a)
            self.assertEqual(b.merge(a).replica, "b")

        def test_writes_after_a_merge_use_the_merged_replica_name(self):
            a, b = LWWMap("a"), LWWMap("b")
            b.set("x", "b", 5)
            m = a.merge(b)
            m.set("x", "a-again", 5)       # (5, "a") is below the entry's (5, "b")
            self.assertEqual(m.get("x"), "b")
            m.set("x", "a-later", 6)
            self.assertEqual(m.get("x"), "a-later")


    if __name__ == "__main__":
        unittest.main()
''')

STALLSYNC = Lib(
    name="stallsync", lang="python", title="the stallsync replicated counters (`stallsync/crdt.py`)",
    blurb="The market stalls' tablets use stallsync to merge their sales counters and price lists when they meet again after an offline day.",
    files={"stallsync/__init__.py": "", "stallsync/crdt.py": STALLSYNC_SRC, "README.md": STALLSYNC_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": STALLSYNC_VISIBLE},
    hidden_tests={"tests/test_full.py": STALLSYNC_HIDDEN},
    mutate=["stallsync/crdt.py"], difficulty=3, tags=["crdt", "replication"],
    probes=[
        "(lambda a, b: (a.incr(5), a.decr(2), b.incr(3), a.merge(b).state())[-1])(PNCounter('a'), PNCounter('b'))",
        "(lambda old, new: (old.incr(5), old.decr(1), new.incr(5), new.incr(2), new.decr(1), new.decr(1), old.merge(new).state())[-1])(PNCounter('a'), PNCounter('a'))",
        "(lambda a, s: (a.incr(10), s.incr(3), a.merge(s).value)[-1])(PNCounter('a'), PNCounter('a'))",
        "PNCounter('b').merge(PNCounter('a')).replica",
        "(lambda z, b, m: (z.incr(1), b.incr(1), m.incr(1), list(z.merge(b).merge(m).state()['inc']))[-1])(PNCounter('z'), PNCounter('b'), PNCounter('m'))",
        "(lambda a, b: (a.set('x', 'from-a', 5), b.set('x', 'from-b', 5), a.merge(b).get('x'))[2])(LWWMap('a'), LWWMap('b'))",
        "(lambda m: (m.set('x', 'old', 5), m.set('x', 'older', 4), m.set('x', 'same', 5), m.get('x'))[3])(LWWMap('a'))",
        "(lambda m: (m.set('x', 1, 5), m.remove('x', 6), m.set('x', 2, 5), m.get('x', 'gone'))[3])(LWWMap('a'))",
        "(lambda m: (m.set('x', 3, 7), m.remove('x', 7), m.get('x'))[2])(LWWMap('a'))",
        "(lambda m: (m.set('zero', 0, 1), len(m), 'zero' in m))(LWWMap('a'))",
        "(lambda a, b: (a.set('x', 1, 5), b.remove('x', 6), a.merge(b).items(), b.merge(a).items()))(LWWMap('a'), LWWMap('b'))",
        "(lambda m: (m.set('pear', 1, 1), m.set('apple', 1, 1), m.items()))(LWWMap('a'))",
    ],
    probe_import="from stallsync.crdt import PNCounter, LWWMap\n",
)

# ======================================================================================================================
# frameseq: reassembling telemetry frames that arrive out of order
# ======================================================================================================================

FRAMESEQ_README = dd('''
    # frameseq

    A weather buoy sends numbered telemetry frames over a flaky radio link. Frames arrive late, twice or not at all; the
    shore station must hand them on in order. Sequence numbers are 16 bit and wrap around: after 65535 comes 0.

    ## `Reassembler(window=8, start=0)`

    `window` (also an attribute) is the number of frames the station is willing to hold back (`ValueError` unless
    `1 <= window <= 32768`);
    `start` is the first sequence number it expects (taken modulo 65536). The attribute `next` is the sequence number it
    waits for.

    * `receive(seq, payload) -> list`: `seq` must be in `0..65535` (`ValueError` otherwise). Let
      `d = (seq - next) mod 65536`. Then:
      * `d >= 65536 - window`: the frame is *behind* `next` by at most `window` frames, i.e. it was already delivered:
        count it as a duplicate and return `[]`;
      * otherwise `d >= window`: it is too far away (ahead beyond the window, or far behind): count it as dropped and
        return `[]`;
      * otherwise (`d < window`): if that sequence number is already held back, count a duplicate and return `[]`; else
        hold the payload. Then deliver: while the frame numbered `next` is held, remove it, `next` moves on by one
        (modulo 65536) and its payload is appended to the result. Return the delivered payloads in order (possibly empty)
        and add their number to the delivered count.
    * `stats() -> dict`: `{"delivered": n, "duplicates": n, "dropped": n}` (a fresh dict each time).
    * `pending() -> int`: how many frames are held back.
    * `missing() -> list[int]`: the sequence numbers the station is still waiting for below the highest held frame: all
      numbers from `next` up to (not including) the held frame that is farthest ahead which are not held themselves, in
      order of distance from `next` and modulo 65536; `[]` when nothing is held.
''')

FRAMESEQ_SRC = dd('''
    """Reassembling frames with wrapping sequence numbers."""

    SPACE = 65536


    class Reassembler:
        def __init__(self, window=8, start=0):
            if not 1 <= window <= SPACE // 2:
                raise ValueError("window must be between 1 and 32768")
            self.window = window
            self.next = start % SPACE
            self._held = {}
            self._stats = {"delivered": 0, "duplicates": 0, "dropped": 0}

        def receive(self, seq, payload):
            if not 0 <= seq < SPACE:
                raise ValueError("sequence numbers are 16 bit")
            d = (seq - self.next) % SPACE
            if d >= SPACE - self.window:
                self._stats["duplicates"] += 1
                return []
            if d >= self.window:
                self._stats["dropped"] += 1
                return []
            if seq in self._held:
                self._stats["duplicates"] += 1
                return []
            self._held[seq] = payload
            out = []
            while self.next in self._held:
                out.append(self._held.pop(self.next))
                self.next = (self.next + 1) % SPACE
            self._stats["delivered"] += len(out)
            return out

        def stats(self):
            return dict(self._stats)

        def pending(self):
            return len(self._held)

        def missing(self):
            if not self._held:
                return []
            far = max((s - self.next) % SPACE for s in self._held)
            wanted = [(self.next + i) % SPACE for i in range(far)]
            return [s for s in wanted if s not in self._held]
''')

FRAMESEQ_VISIBLE = dd('''
    import unittest

    from frameseq.reassemble import Reassembler


    class BasicTests(unittest.TestCase):
        def test_in_order(self):
            r = Reassembler()
            self.assertEqual(r.receive(0, "a"), ["a"])
            self.assertEqual(r.receive(1, "b"), ["b"])

        def test_out_of_order(self):
            r = Reassembler()
            self.assertEqual(r.receive(1, "b"), [])
            self.assertEqual(r.receive(0, "a"), ["a", "b"])


    if __name__ == "__main__":
        unittest.main()
''')

FRAMESEQ_HIDDEN = dd('''
    import unittest

    from frameseq.reassemble import Reassembler


    class Construction(unittest.TestCase):
        def test_defaults(self):
            r = Reassembler()
            self.assertEqual((r.window, r.next, r.pending(), r.missing()), (8, 0, 0, []))
            self.assertEqual(r.stats(), {"delivered": 0, "duplicates": 0, "dropped": 0})

        def test_validation(self):
            for w in (0, -1, 32769, 70000):
                with self.assertRaises(ValueError):
                    Reassembler(window=w)
            Reassembler(window=1)
            Reassembler(window=32768)

        def test_start_is_taken_modulo(self):
            self.assertEqual(Reassembler(start=65536 + 5).next, 5)
            self.assertEqual(Reassembler(start=-1).next, 65535)

        def test_sequence_range(self):
            r = Reassembler()
            for seq in (-1, 65536, 100000):
                with self.assertRaises(ValueError):
                    r.receive(seq, "x")
            self.assertEqual(r.stats(), {"delivered": 0, "duplicates": 0, "dropped": 0})


    class Ordering(unittest.TestCase):
        def test_in_order(self):
            r = Reassembler()
            for i, p in enumerate("abc"):
                self.assertEqual(r.receive(i, p), [p])
            self.assertEqual((r.next, r.stats()["delivered"]), (3, 3))

        def test_gap_then_fill(self):
            r = Reassembler(window=4)
            self.assertEqual(r.receive(1, "b"), [])
            self.assertEqual(r.receive(3, "d"), [])
            self.assertEqual(r.pending(), 2)
            self.assertEqual(r.receive(0, "a"), ["a", "b"])
            self.assertEqual(r.next, 2)
            self.assertEqual(r.receive(2, "c"), ["c", "d"])
            self.assertEqual((r.next, r.pending()), (4, 0))
            self.assertEqual(r.stats(), {"delivered": 4, "duplicates": 0, "dropped": 0})

        def test_reverse_order(self):
            r = Reassembler(window=5)
            for seq in (4, 3, 2, 1):
                self.assertEqual(r.receive(seq, str(seq)), [])
            self.assertEqual(r.receive(0, "0"), ["0", "1", "2", "3", "4"])
            self.assertEqual(r.next, 5)

        def test_payloads_can_be_anything(self):
            r = Reassembler()
            self.assertEqual(r.receive(0, None), [None])
            self.assertEqual(r.receive(1, 0), [0])
            self.assertEqual(r.receive(2, ""), [""])


    class Windows(unittest.TestCase):
        def test_window_edge_ahead(self):
            r = Reassembler(window=4)
            self.assertEqual(r.receive(3, "d"), [])          # d = 3 < 4: held
            self.assertEqual(r.pending(), 1)
            self.assertEqual(r.receive(4, "e"), [])          # d = 4: dropped
            self.assertEqual(r.stats()["dropped"], 1)
            self.assertEqual(r.pending(), 1)
            self.assertEqual(r.receive(1000, "x"), [])
            self.assertEqual(r.stats()["dropped"], 2)

        def test_window_of_one(self):
            r = Reassembler(window=1)
            self.assertEqual(r.receive(1, "b"), [])
            self.assertEqual(r.stats()["dropped"], 1)
            self.assertEqual(r.receive(0, "a"), ["a"])

        def test_the_window_moves_with_next(self):
            r = Reassembler(window=4)
            r.receive(0, "a")
            r.receive(1, "b")
            self.assertEqual(r.receive(5, "f"), [])
            self.assertEqual(r.pending(), 1)               # d = 3 relative to next = 2
            self.assertEqual(r.receive(6, "g"), [])
            self.assertEqual(r.stats()["dropped"], 1)

        def test_duplicates_of_delivered_frames(self):
            r = Reassembler(window=4)
            for i in range(6):
                r.receive(i, i)
            for seq in (5, 4, 3, 2):
                self.assertEqual(r.receive(seq, "again"), [])
            self.assertEqual(r.stats()["duplicates"], 4)
            self.assertEqual(r.receive(1, "old"), [])        # five frames behind: beyond the duplicate zone
            self.assertEqual(r.stats(), {"delivered": 6, "duplicates": 4, "dropped": 1})

        def test_duplicate_of_a_held_frame(self):
            r = Reassembler(window=4)
            r.receive(2, "c")
            self.assertEqual(r.receive(2, "c-again"), [])
            self.assertEqual(r.stats()["duplicates"], 1)
            self.assertEqual(r.pending(), 1)
            self.assertEqual(r.receive(0, "a"), ["a"])
            self.assertEqual(r.receive(1, "b"), ["b", "c"])

        def test_first_payload_wins(self):
            r = Reassembler(window=4)
            r.receive(1, "first")
            r.receive(1, "second")
            self.assertEqual(r.receive(0, "a"), ["a", "first"])

        def test_big_window_boundaries(self):
            r = Reassembler(window=32768)
            self.assertEqual(r.receive(32767, "x"), [])
            self.assertEqual(r.pending(), 1)
            self.assertEqual(r.receive(32768, "y"), [])      # d = 32768 >= window and < 65536 - window? no: equal, so behind
            self.assertEqual(r.stats()["duplicates"], 1)


    class Wraparound(unittest.TestCase):
        def test_wrap(self):
            r = Reassembler(window=4, start=65534)
            self.assertEqual(r.receive(65535, "y"), [])
            self.assertEqual(r.receive(0, "z"), [])
            self.assertEqual(r.pending(), 2)
            self.assertEqual(r.receive(65534, "x"), ["x", "y", "z"])
            self.assertEqual(r.next, 1)

        def test_duplicate_across_the_wrap(self):
            r = Reassembler(window=4, start=65534)
            for seq, p in ((65534, "x"), (65535, "y"), (0, "z")):
                r.receive(seq, p)
            self.assertEqual(r.receive(65535, "y2"), [])
            self.assertEqual(r.receive(65534, "x2"), [])
            self.assertEqual(r.stats(), {"delivered": 3, "duplicates": 2, "dropped": 0})

        def test_next_wraps_to_zero(self):
            r = Reassembler(window=4, start=65535)
            self.assertEqual(r.receive(65535, "a"), ["a"])
            self.assertEqual(r.next, 0)
            self.assertEqual(r.receive(0, "b"), ["b"])
            self.assertEqual(r.next, 1)

        def test_far_ahead_across_the_wrap_is_dropped(self):
            r = Reassembler(window=4, start=65534)
            self.assertEqual(r.receive(3, "x"), [])
            self.assertEqual(r.stats()["dropped"], 1)
            self.assertEqual(r.receive(1, "y"), [])
            self.assertEqual(r.pending(), 1)


    class Missing(unittest.TestCase):
        def test_missing(self):
            r = Reassembler(window=8)
            self.assertEqual(r.missing(), [])
            r.receive(3, "d")
            r.receive(5, "f")
            self.assertEqual(r.missing(), [0, 1, 2, 4])
            r.receive(0, "a")
            self.assertEqual(r.missing(), [1, 2, 4])
            self.assertEqual(r.receive(1, "b"), ["b"])
            self.assertEqual(r.receive(2, "c"), ["c", "d"])
            self.assertEqual((r.next, r.pending()), (4, 1))
            self.assertEqual(r.missing(), [4])
            self.assertEqual(r.receive(4, "e"), ["e", "f"])
            self.assertEqual(r.missing(), [])
            self.assertEqual(r.pending(), 0)

        def test_missing_after_delivery(self):
            r = Reassembler(window=8)
            r.receive(0, "a")
            r.receive(2, "c")
            self.assertEqual(r.missing(), [1])
            r.receive(4, "e")
            self.assertEqual(r.missing(), [1, 3])

        def test_missing_across_the_wrap(self):
            r = Reassembler(window=8, start=65533)
            r.receive(1, "x")
            self.assertEqual(r.missing(), [65533, 65534, 65535, 0])
            r.receive(65534, "y")
            self.assertEqual(r.missing(), [65533, 65535, 0])

        def test_stats_is_a_copy(self):
            r = Reassembler()
            s = r.stats()
            s["delivered"] = 99
            self.assertEqual(r.stats()["delivered"], 0)


    if __name__ == "__main__":
        unittest.main()
''')

FRAMESEQ = Lib(
    name="frameseq", lang="python", title="the frameseq reassembler (`frameseq/reassemble.py`)",
    blurb="The shore station of the weather buoy network uses frameseq to put telemetry frames back in order when the radio link delivers them late or twice.",
    files={"frameseq/__init__.py": "", "frameseq/reassemble.py": FRAMESEQ_SRC, "README.md": FRAMESEQ_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": FRAMESEQ_VISIBLE},
    hidden_tests={"tests/test_full.py": FRAMESEQ_HIDDEN},
    mutate=["frameseq/reassemble.py"], difficulty=3, tags=["sequence-numbers", "reassembly"],
    probes=[
        chain("Reassembler(window=4)", ["receive(1, 'b')", "receive(3, 'd')", "receive(0, 'a')", "receive(2, 'c')", "stats()"]),
        chain("Reassembler(window=4)", ["receive(3, 'd')", "receive(4, 'e')", "pending()", "stats()"]),
        chain("Reassembler(window=4, start=65534)", ["receive(65535, 'y')", "receive(0, 'z')", "receive(65534, 'x')", "next"]),
        chain("Reassembler(window=4, start=65534)", ["receive(65534, 'x')", "receive(65535, 'y')", "receive(0, 'z')", "receive(65535, 'y2')", "stats()"]),
        chain("Reassembler(window=4)", ["receive(0, 'a')", "receive(1, 'b')", "receive(2, 'c')", "receive(3, 'd')", "receive(4, 'e')", "receive(5, 'f')", "receive(2, 'old')", "receive(1, 'older')", "stats()"]),
        chain("Reassembler(window=8)", ["receive(3, 'd')", "receive(5, 'f')", "missing()", "receive(0, 'a')", "missing()"]),
        chain("Reassembler(window=8, start=65533)", ["receive(1, 'x')", "missing()"]),
        chain("Reassembler(window=4)", ["receive(1, 'first')", "receive(1, 'second')", "receive(0, 'a')"]),
        chain("Reassembler(window=1)", ["receive(1, 'b')", "stats()", "receive(0, 'a')"]),
        "Reassembler(start=-1).next", "Reassembler(window=0)",
    ],
    probe_import="from frameseq.reassemble import Reassembler\n",
)

LIBS = [UNDOTRAIL, LOANLOG, STALLSYNC, FRAMESEQ]
register_libs3(LIBS, n=10)
