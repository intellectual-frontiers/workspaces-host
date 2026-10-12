"""Versions of programs, compared the way a person reads them (0011-archon FR-010). Standard library only."""
from __future__ import annotations

import os
import re
import shutil
import subprocess

FIRST = re.compile(r"(?<![\w.])v?(\d+(?:\.\d+)+)")
WHOLE = re.compile(r"(?:version|v)\s*\"?(\d+)\"?(?![\d.])", re.IGNORECASE)


def parse(text: str) -> tuple[int, ...] | None:
    """The dot-separated whole numbers a version starts with, ignoring an epoch (`2:`) and whatever a distribution adds after them
    (a revision such as `-1~deb12u1`, a suffix such as `+dfsg`); None when it starts with none."""
    s = text.strip()
    if re.match(r"^\d+:", s):
        s = s.split(":", 1)[1]
    m = re.match(r"^v?(\d+(?:\.\d+)*)", s)
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def meets(found: str, minimum: str) -> bool:
    """True when `found` is at least `minimum`; a missing part counts as 0."""
    a, b = parse(found), parse(minimum)
    if a is None or b is None:
        return False
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) >= b + (0,) * (width - len(b))


def first_in(text: str) -> str | None:
    """The first version-looking word a program printed."""
    m = FIRST.search(text) or WHOLE.search(text)
    return m.group(1) if m else None


def probe(program: str, args: list[str] | tuple[str, ...] = ("--version",), path: str | None = None, timeout: float = 20) -> tuple[str | None, str | None]:
    """(the program's path, its version) as found on `path` (default PATH); (None, None) when it is absent, (path, None) when it prints no version."""
    exe = shutil.which(program, path=path)
    if not exe:
        return None, None
    try:
        p = subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL, env={**os.environ, **({"PATH": path} if path else {})})
    except (OSError, subprocess.TimeoutExpired):
        return exe, None
    return exe, first_in((p.stdout or "") + "\n" + (p.stderr or ""))
