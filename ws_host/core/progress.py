"""A one-line spinner for a step that takes a while (0006-onboarding FR-020).

It shows at a person's terminal only, on standard error, after half a second, as one line that is replaced in place; a step that
finishes at once shows nothing. A step that took a while leaves one line behind, and one that failed leaves its reason. Never in
JSON, HTML, a pipe or a file, so a script's output stays clean. Standard library only."""
from __future__ import annotations

import os
import sys
import threading
import time

from .render import Style, use_color

ENABLED = True            # the command line turns it off for --json and --html
DELAY = 0.5               # seconds a step runs before anything shows
LEFT_BEHIND = 2.0         # seconds a step must take to leave a line behind

_BRAILLE = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_ASCII = "|/-\\"
_current: "Working | None" = None


def _utf8() -> bool:
    loc = os.environ.get("LC_ALL") or os.environ.get("LC_CTYPE") or os.environ.get("LANG") or ""
    return "utf" in loc.lower()


def visible(stream=None) -> bool:
    """Whether a spinner may be drawn: a person's terminal, not a dumb one, and not switched off."""
    stream = stream or sys.stderr
    if not ENABLED or os.environ.get("WS_HOST_PROGRESS") == "never" or os.environ.get("TERM") == "dumb":
        return False
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False


class Working:
    """`with Working("Copying the guide"):` around the slow call; `detail()` adds "12 of 40 MB" and the like."""

    def __init__(self, label: str, stream=None, probe=None):
        self.label, self.stream, self.text, self.probe = label, stream or sys.stderr, "", probe
        self.shown = False
        self.started = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._style = Style(use_color(self.stream))

    def detail(self, text: str) -> None:
        self.text = text

    def __enter__(self) -> "Working":
        global _current
        self.started = time.monotonic()
        self._previous, _current = _current, self
        if visible(self.stream):
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        return self

    def _spin(self) -> None:
        frames = _BRAILLE if _utf8() else _ASCII
        i = 0
        while not self._stop.wait(0.1):
            elapsed = time.monotonic() - self.started
            if elapsed < DELAY:
                continue
            self.shown = True
            if self.probe:
                try:
                    self.text = self.probe() or self.text
                except Exception:        # a progress hint must never break the step it describes
                    self.probe = None
            line = f"{self._style.cyan(frames[i % len(frames)])} {self.label}" + (f" {self._style.dim(self.text)}" if self.text else "") \
                   + self._style.dim(f" ({int(elapsed)}s)")
            self.stream.write("\r\033[K" + line)
            self.stream.flush()
            i += 1

    def __exit__(self, exc_type, exc, tb) -> bool:
        global _current
        self._stop.set()
        if self._thread:
            self._thread.join()
        _current = self._previous
        if self.shown:
            took = time.monotonic() - self.started
            self.stream.write("\r\033[K")
            if exc_type is not None:
                self.stream.write(f"{self._style.red('✖' if _utf8() else 'x')} {self.label}\n")
            elif took >= LEFT_BEHIND:
                self.stream.write(f"{self._style.green('✔' if _utf8() else 'ok')} {self.label}\n")
            self.stream.flush()
        return False


def working(label: str, probe=None) -> Working:
    """`probe`, if given, is asked on every tick for text such as "42.0 MB so far"."""
    return Working(label, probe=probe)


def folder_megabytes(path, what: str = "so far"):
    """A probe for a step whose program downloads into `path` and says nothing: how large the folder has grown."""
    def probe():
        total = 0
        for root, _, files in os.walk(path):
            for f in files:
                try:
                    total += os.lstat(os.path.join(root, f)).st_size
                except OSError:
                    pass
        return f"{total / 1_000_000:.0f} MB {what}" if total else ""
    return probe


def detail(text: str) -> None:
    """Tell the spinner that is showing, if one is, how far along it is."""
    if _current is not None:
        _current.detail(text)


def megabytes(done: int, total: int | None) -> str:
    mb = done / 1_000_000
    return f"{mb:.1f} of {total / 1_000_000:.1f} MB" if total else f"{mb:.1f} MB"
