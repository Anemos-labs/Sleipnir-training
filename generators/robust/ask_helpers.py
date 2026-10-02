"""Tiny shared helper (not a family module: imported by ask.py)."""
import re


def render_text(template, data):
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(data[m.group(1)]), template)
