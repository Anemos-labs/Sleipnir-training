"""Helpers shared by the golib_* / rslib_* modules (fix-lang-1)."""
import re

from fx import Family, langs, mutation_tasks, register
from fx.lib import LANG_PREFIX


def gosrc(s: str) -> str:
    """Turn the leading 4-space groups of every line into tabs (what gofmt would produce)."""
    out = []
    for line in s.split("\n"):
        m = re.match(r"^( +)", line)
        if m:
            n = len(m.group(1))
            line = "\t" * (n // 4) + " " * (n % 4) + line[n:]
        out.append(line)
    return "\n".join(out)


CARGO_CONFIG = '[env]\nRUST_BACKTRACE = { value = "0", force = true }\n'


def cargo(name: str) -> str:
    """Cargo.toml without dependencies; doc tests are off so indented doc comments never become tests."""
    return langs.cargo_toml(name).replace("[dependencies]", "[lib]\ndoctest = false\n\n[dependencies]")


_THREAD_ID = re.compile(r"(thread '[^']*') \(\d+\) panicked")
_RUST_NOTE = re.compile(r"^note: run with `RUST_BACKTRACE=\d` .*\n?", re.M)


def clean_prompt(prompt: str) -> str:
    """Drop run-specific noise a test runner prints (rust thread ids, the backtrace hint)."""
    prompt = _THREAD_ID.sub(r"\1 panicked", prompt)
    return _RUST_NOTE.sub("", prompt)


def register_libs(libs, n: int = 8, category: str = "fix") -> None:
    """Like fx.register_libs (one family `fix-<lang>-<name>` per library) with run-specific noise removed from prompts."""
    for lib in libs:
        fam = Family(name=f"fix-{LANG_PREFIX.get(lib.lang, lib.lang)}-{lib.name}", category=category, lang=lib.lang, kind="fix", n=n,
                     summary=f"injected bugs in {lib.title} ({lib.lang})")

        def gen(rng, count, _lib=lib):
            return [t.with_(prompt=clean_prompt(t.prompt)) for t in mutation_tasks(_lib, rng, count)]

        register(fam, gen)
