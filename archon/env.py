"""Environment files in os-release(5) / systemd EnvironmentFile syntax (0041-command-line FR-047).

`KEY=value`, the value optionally in single or double quotes, `#` starting a comment on a line of its own, no variable
expansion, no line continuation. A list is space-separated values on one line.
"""
from __future__ import annotations

import re
from pathlib import Path

KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class EnvError(ValueError):
    def __init__(self, message: str, line: int):
        super().__init__(f"line {line}: {message}")
        self.line = line


def _value(raw: str, lineno: int) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] in "'\"":
        if raw[-1] != raw[0]:
            raise EnvError("a quoted value is not closed", lineno)
        inner = raw[1:-1]
        if raw[0] == '"':
            inner = re.sub(r'\\(["\\])', r"\1", inner)
        return inner
    if raw and raw[0] in "'\"":
        raise EnvError("a quoted value is not closed", lineno)
    return raw


def parse(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for lineno, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        key, sep, raw = s.partition("=")
        key = key.strip()
        if not sep or not KEY.match(key):
            raise EnvError("expected KEY=value", lineno)
        out[key] = _value(raw, lineno)
    return out


def load(path: Path) -> dict[str, str]:
    """The file's values, or {} when it is absent. A malformed file raises EnvError."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    return parse(text)


def words(value: str | None) -> list[str]:
    return (value or "").split()
