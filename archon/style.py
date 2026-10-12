"""Colour and emoji for a person's terminal (0006-onboarding FR-016). Standard library only."""
from __future__ import annotations


class Style:
    """Colour and emoji for a person's terminal (0006-onboarding FR-016). Off when the output is a pipe, a file or NO_COLOR is set."""

    def __init__(self, on: bool):
        self.on = on

    def _c(self, code: str, s: str) -> str:
        return f"\033[{code}m{s}\033[0m" if self.on else s

    def bold(self, s): return self._c("1", s)
    def dim(self, s): return self._c("2", s)
    def cyan(self, s): return self._c("1;36", s)
    def green(self, s): return self._c("32", s)
    def yellow(self, s): return self._c("33", s)
    def red(self, s): return self._c("31", s)

    def mark(self, status: str) -> str:
        if not self.on:
            return {"ok": "ok", "passed": "passed", "warn": "warning", "fail": "FAILED", "failed": "FAILED", "skip": "skipped", "skipped": "skipped"}.get(status, status)
        return {"ok": "✅", "passed": "✅", "warn": "⚠️ ", "fail": "❌", "failed": "❌", "skip": "⏭️ ", "skipped": "⏭️ "}.get(status, status)


PLAIN = Style(False)


def use_color(out) -> bool:
    """Colour only for a person at a terminal; NO_COLOR and TERM=dumb turn it off, WS_HOST_COLOR=always or never decides."""
    import os
    want = os.environ.get("WS_HOST_COLOR", "")
    if want in ("always", "never"):
        return want == "always"
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    try:
        return bool(out.isatty())
    except (AttributeError, ValueError):
        return False
