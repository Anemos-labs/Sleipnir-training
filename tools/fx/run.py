"""Run a command against an in-memory file tree, the way a verifier would, for use *while generating* tasks.

This is a convenience for generators (is this mutant killed by the hidden tests? what does the reference solution
print for this input?). It is not the judge: ``tools/admit.py`` runs Sleipnir's own ``rl tasks check``.
Results are cached on disk (key: files + command) so rebuilding a family is cheap.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

CACHE_DIR = Path(os.environ.get("FX_CACHE", Path.home() / ".cache" / "fx")) / "run"
GOCACHE = Path(os.environ.get("FX_GOCACHE", Path.home() / ".cache" / "fx" / "gocache"))
MAX_OUT = 24_000


@dataclass
class Result:
    code: int
    out: str
    timed_out: bool = False
    ms: int = 0

    @property
    def ok(self) -> bool:
        return self.code == 0 and not self.timed_out


def _env(tmp: str) -> dict:
    env = {k: v for k, v in os.environ.items() if not re.search(r"(KEY|TOKEN|SECRET|PASSWORD)", k)}
    GOCACHE.mkdir(parents=True, exist_ok=True)
    env.update(
        GOFLAGS="-mod=mod",
        GOTOOLCHAIN="local",
        GOCACHE=str(GOCACHE),
        GOPATH=str(Path(tmp) / ".gopath"),
        GO111MODULE="on",
        GOPROXY="off",
        TMPDIR=tmp,
        NO_COLOR="1",
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONHASHSEED="0",
        CARGO_NET_OFFLINE="true",
        LC_ALL="C.UTF-8",
        TZ="UTC",
    )
    return env


def write_tree(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        if rel.endswith(".sh"):
            p.chmod(0o755)


def clean_output(out: str, tmp: str = "") -> str:
    """Make output deterministic and shareable: no temp paths, no timings, no addresses."""
    if tmp:
        out = out.replace(tmp, ".")
    out = re.sub(r"/tmp/[^\s:'\"]+", ".", out)
    out = re.sub(r"\b\d+\.\d+s\b", "0.00s", out)
    out = re.sub(r"\(\d+(\.\d+)?m?s\)", "(0ms)", out)
    out = re.sub(r"in \d+\.\d+ ?m?s", "in 0.00s", out)
    out = re.sub(r"0x[0-9a-f]{6,}", "0xADDR", out)
    return out


def run(files: dict[str, str], cmd: str, timeout: int = 90, cache: bool = True) -> Result:
    key = hashlib.sha256(json.dumps([sorted(files.items()), cmd], ensure_ascii=False).encode()).hexdigest()
    cf = CACHE_DIR / key[:2] / f"{key}.json"
    if cache and cf.exists():
        try:
            d = json.loads(cf.read_text())
            return Result(d["code"], d["out"], d.get("timed_out", False), d.get("ms", 0))
        except Exception:  # noqa: BLE001
            pass
    tmp = tempfile.mkdtemp(prefix="fxrun-")
    t0 = time.time()
    try:
        root = Path(tmp) / "w"
        root.mkdir()
        write_tree(root, files)
        p = subprocess.Popen(
            ["bash", "-c", cmd], cwd=root, env=_env(tmp), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, errors="replace", start_new_session=True,
        )
        try:
            out, _ = p.communicate(timeout=timeout)
            res = Result(p.returncode, clean_output(out[-MAX_OUT:], str(root)), ms=int((time.time() - t0) * 1000))
        except subprocess.TimeoutExpired:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            out, _ = p.communicate()
            res = Result(124, clean_output((out or "")[-MAX_OUT:], str(root)), timed_out=True, ms=int((time.time() - t0) * 1000))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if cache:
        cf.parent.mkdir(parents=True, exist_ok=True)
        cf.write_text(json.dumps({"code": res.code, "out": res.out, "timed_out": res.timed_out, "ms": res.ms}))
    return res


def merged(*trees: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for t in trees:
        out.update(t)
    return out
