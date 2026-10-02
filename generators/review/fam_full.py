"""Full-review families: one per language, over the slot modules of that language."""
from fx import family

from . import _engine as E
from ._mods_go1 import MODULES as GO1
from ._mods_java1 import MODULES as JAVA1
from ._mods_js1 import MODULES as JS1
from ._mods_py1 import MODULES as PY1
from ._mods_py2 import MODULES as PY2
from ._mods_py3 import MODULES as PY3
from ._mods_py4 import MODULES as PY4
from ._mods_rs1 import MODULES as RS1

PY = PY1 + PY2 + PY3 + PY4
GO = GO1
JS = JS1
JAVA = JAVA1
RS = RS1


def _reg(name, lang, mods, n, summary):
    @family(name, category="review", lang=lang, kind="feature", n=n, summary=summary)
    def gen(rng, count, _mods=mods):
        yield from E.review_family(_mods, rng, count, "full")

    return gen


_reg("review-py-full", "python", PY, 27, "review a python PR (PR.md + change.patch) with 1-5 planted defects; scored by recall minus false positives")
_reg("review-go-full", "go", GO, 18, "review a go PR with planted defects (races, leaks, traversal, ignored errors)")
_reg("review-js-full", "javascript", JS, 18, "review a javascript PR with planted defects (async misuse, XSS, date maths, coercion)")
_reg("review-java-full", "java", JAVA, 18, "review a java PR with planted defects (locking, resources, zip slip, SQL injection)")
_reg("review-rs-full", "rust", RS, 12, "review a rust PR with planted defects (panics, unsafe input handling, permissions, injection)")
