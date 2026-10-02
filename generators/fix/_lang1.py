"""Helpers shared by the golib_* / rslib_* modules (fix-lang-1)."""
import re

from fx import langs


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


def cargo(name: str) -> str:
    """Cargo.toml without dependencies; doc tests are off so indented doc comments never become tests."""
    return langs.cargo_toml(name).replace("[dependencies]", "[lib]\ndoctest = false\n\n[dependencies]")
