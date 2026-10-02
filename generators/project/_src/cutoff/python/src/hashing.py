"""Content digests: FNV-1a (32 bit) over the UTF-8 bytes, shown as eight lower-case hex digits."""


def digest(text: str) -> str:
    h = 0x811C9DC5
    for b in text.encode("utf-8"):
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return "%08x" % h
