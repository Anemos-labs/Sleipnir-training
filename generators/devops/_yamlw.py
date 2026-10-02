"""A small YAML writer (block style) for generating configuration files from python models, plus a ruby-based reader
used to prove that what we wrote parses back to the same data."""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile

_RESERVED = {"true", "false", "null", "yes", "no", "on", "off", "~", "y", "n"}
_PLAIN = re.compile(r"^[A-Za-z_./@][A-Za-z0-9_./@ +-]*$")
_NUMLIKE = re.compile(r"^[-+]?(\d[\d_]*)(\.\d*)?([eE][-+]?\d+)?$|^0[xob][0-9a-fA-F]+$|^\d+(:\d+)+$|^\.\d+$")


class Raw:
    """A scalar written verbatim (e.g. an unquoted 3.10) that stands for ``value`` once parsed."""

    def __init__(self, text: str, value):
        self.text, self.value = text, value


def unraw(o):
    if isinstance(o, Raw):
        return o.value
    if isinstance(o, dict):
        return {k: unraw(v) for k, v in o.items()}
    if isinstance(o, list):
        return [unraw(x) for x in o]
    return o


def scalar(v, force_quote: bool = False) -> str:
    if isinstance(v, Raw):
        return v.text
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v)
    if force_quote or s == "" or s.lower() in _RESERVED or _NUMLIKE.match(s) or not _PLAIN.match(s) or s.endswith((" ", ":")) or s.startswith(("- ", "? ")) or ": " in s or " #" in s:
        return json.dumps(s, ensure_ascii=False)
    return s


def dump(obj, indent: int = 0, flow_lists: bool = False, key_quote: set | None = None) -> str:
    pad = " " * indent
    out: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            ks = scalar(k) if not (isinstance(k, str) and k in ("on",)) else k
            out.extend(_entry(pad, ks, v, indent, flow_lists))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_item(pad, v, indent, flow_lists))
    else:
        out.append(pad + scalar(obj))
    return "\n".join(out) + ("\n" if indent == 0 else "")


def _entry(pad, ks, v, indent, flow):
    if v is None:
        return [f"{pad}{ks}:"]
    if isinstance(v, dict):
        if not v:
            return [f"{pad}{ks}: {{}}"]
        return [f"{pad}{ks}:"] + dump(v, indent + 2, flow).split("\n")
    if isinstance(v, list):
        if not v:
            return [f"{pad}{ks}: []"]
        if flow and all(not isinstance(x, (dict, list)) for x in v) and len(v) <= 6:
            return [f"{pad}{ks}: [" + ", ".join(scalar(x) for x in v) + "]"]
        return [f"{pad}{ks}:"] + dump(v, indent + 2, flow).split("\n")
    if isinstance(v, str) and "\n" in v:
        lines = v.rstrip("\n").split("\n")
        return [f"{pad}{ks}: |"] + [f"{pad}  {l}" if l else "" for l in lines]
    return [f"{pad}{ks}: {scalar(v)}"]


def _item(pad, v, indent, flow):
    if isinstance(v, dict):
        if not v:
            return [f"{pad}- {{}}"]
        lines = dump(v, indent + 2, flow).split("\n")
        lines[0] = f"{pad}- " + lines[0][indent + 2:]
        return lines
    if isinstance(v, list):
        lines = dump(v, indent + 2, flow).split("\n")
        lines[0] = f"{pad}- " + lines[0][indent + 2:]
        return lines
    if isinstance(v, str) and "\n" in v:
        lines = v.rstrip("\n").split("\n")
        return [f"{pad}- |"] + [f"{pad}  {l}" if l else "" for l in lines]
    return [f"{pad}- {scalar(v)}"]


RUBY = r'''
require "yaml"
require "json"
require "date"
def conv(o)
  case o
  when Hash then o.each_with_object({}) { |(k, v), h| h[k.to_s] = conv(v) }
  when Array then o.map { |x| conv(x) }
  when Date, Time then o.to_s
  when Symbol then o.to_s
  else o
  end
end
begin
  docs = YAML.parse_stream(File.read(ARGV[0])).children.map { |d| conv(d.to_ruby) }
  puts JSON.generate(docs)
rescue Psych::Exception => e
  puts JSON.generate({"__error__" => e.message})
  exit 3
end
'''


def load_all(text: str) -> list:
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "a.yml"), "w", encoding="utf-8").write(text)
        open(os.path.join(d, "y.rb"), "w").write(RUBY)
        p = subprocess.run(["ruby", os.path.join(d, "y.rb"), os.path.join(d, "a.yml")], capture_output=True, text=True, timeout=30)
        if p.returncode != 0:
            raise ValueError(p.stdout.strip() or p.stderr.strip())
        return json.loads(p.stdout)


def stringify_keys(o):
    if isinstance(o, dict):
        return {("true" if k is True else str(k)): stringify_keys(v) for k, v in o.items()}
    if isinstance(o, list):
        return [stringify_keys(x) for x in o]
    return o


def roundtrip(model) -> str:
    """dump the model, parse it with ruby, and require identical data (``on`` becomes the key "true" under YAML 1.1)."""
    text = dump(model)
    docs = load_all(text)
    want = stringify_keys(unraw({("true" if k == "on" else k): v for k, v in model.items()} if isinstance(model, dict) else model))
    if len(docs) != 1 or docs[0] != want:
        raise RuntimeError("yaml writer does not round-trip:\n" + text[:600])
    return text
