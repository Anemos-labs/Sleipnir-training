"""Hidden python helper for algorithmic optimize tasks: counts the python lines executed inside the project package (placed in tests/linemeter.py).

The count is a property of the algorithm and the input, not of the machine, so a budget on it is as deterministic as an operation counter.
"""

TEXT = '''"""Counts executed lines of project code; raises BudgetExceeded as soon as the budget is used up."""
import os
import sys


class BudgetExceeded(BaseException):
    pass


class LineMeter:
    def __init__(self, root, budget=None):
        self.root = os.path.abspath(root) + os.sep
        self.budget = budget
        self.lines = 0
        self._known = {}
        self._previous = None

    def _local(self, frame, event, arg):
        if event == "line":
            self.lines += 1
            if self.budget is not None and self.lines > self.budget:
                raise BudgetExceeded()
        return self._local

    def _global(self, frame, event, arg):
        name = frame.f_code.co_filename
        inside = self._known.get(name)
        if inside is None:
            inside = self._known[name] = os.path.abspath(name).startswith(self.root)
        if inside:
            self.lines += 1
            return self._local
        return None

    def __enter__(self):
        self._previous = sys.gettrace()
        sys.settrace(self._global)
        return self

    def __exit__(self, *exc):
        sys.settrace(self._previous)
        return False
'''
