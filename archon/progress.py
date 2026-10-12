"""A one-line spinner for a step that takes a while (0006-onboarding FR-020).

It shows at a person's terminal only, on standard error, after half a second, as one line that is replaced in place; a step that
finishes at once shows nothing. A step that took a while leaves one line behind, and one that failed leaves its reason. Never in
JSON, HTML, a pipe or a file, so a script's output stays clean. Standard library only."""
from __future__ import annotations

import contextlib
import itertools
import json
import os
import sys
import threading
import time

from .style import Style, use_color

ENABLED = True            # the command line turns it off for --json and --html
VARIABLE = "ARCHON_PROGRESS"   # `events`: JSON lines on standard error for an editor or a web page to draw (0011-archon FR-021); `never`: nothing drawn
DELAY = 0.5               # seconds a step runs before anything shows
LEFT_BEHIND = 2.0         # seconds a step must take to leave a line behind

_BRAILLE = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_ASCII = "|/-\\"
_current: "Working | None" = None
_ids = itertools.count(1)


def _utf8() -> bool:
    loc = os.environ.get("LC_ALL") or os.environ.get("LC_CTYPE") or os.environ.get("LANG") or ""
    return "utf" in loc.lower()


def events() -> bool:
    """Whether progress is published as JSON lines for a surface to draw (0011-archon FR-021)."""
    return ENABLED and os.environ.get(VARIABLE) == "events"


def visible(stream=None) -> bool:
    """Whether a spinner may be drawn: an attended person's terminal, not a dumb one, not switched off, and not published as events instead."""
    from . import profile
    stream = stream or sys.stderr
    if not ENABLED or os.environ.get(VARIABLE) in ("never", "events") or os.environ.get("TERM") == "dumb" or not profile.current().attended:
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
        self._events = False
        self._id = 0
        self.started = 0.0
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._thread: threading.Thread | None = None
        self._style = Style(use_color(self.stream))

    def detail(self, text: str, done: int | None = None, total: int | None = None) -> None:
        self.text = text
        if self._events:
            self._emit("update", done=done, total=total)

    def _emit(self, state: str, **more) -> None:
        """One JSON object on its own line of standard error (0011-archon FR-021)."""
        label = self.label
        emoji = ""
        if label and ord(label[0]) > 0x2000:
            emoji, _, label = label.partition(" ")
        doc = {"event": "progress", "step": self._id, "state": state, "emoji": emoji, "label": label, "text": self.text,
               "seconds": round(time.monotonic() - self.started, 1), **{k: v for k, v in more.items() if v is not None}}
        try:
            self.stream.write(json.dumps(doc, ensure_ascii=False) + "\n")
            self.stream.flush()
        except (OSError, ValueError):
            pass

    def __enter__(self) -> "Working":
        global _current
        self.started = time.monotonic()
        self._previous, _current = _current, self
        self._events = events()
        if self._events:
            self._id = next(_ids)
            self._emit("start")
        elif visible(self.stream):
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        return self

    def _spin(self) -> None:
        frames = _BRAILLE if _utf8() else _ASCII
        i = 0
        while not self._stop.wait(0.1):
            elapsed = time.monotonic() - self.started
            if elapsed < DELAY or self._pause.is_set():
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
        if self._events:
            self._emit("failed" if exc_type is not None else "done")
        if self.shown:
            took = time.monotonic() - self.started
            self.stream.write("\r\033[K")
            if exc_type is not None:
                self.stream.write(f"{'❌' if _utf8() else 'x'} {self.label}\n")
            elif took >= LEFT_BEHIND:
                self.stream.write(f"{'✅' if _utf8() else 'ok'} {self.label}\n")
            self.stream.flush()
        return False


@contextlib.contextmanager
def paused():
    """Stop the spinner drawing while something else needs the line: a question the person must see and answer (sudo's password), or text that is its own progress.
    The line is cleared first, so nothing is drawn over what the person is asked, and the spinner goes on afterwards."""
    w = _current if isinstance(_current, Working) and _current._thread else None
    if w is not None:
        w._pause.set()
        time.sleep(0.15)                  # a frame being drawn finishes first
        try:
            w.stream.write("\r\033[K")
            w.stream.flush()
        except (OSError, ValueError):
            pass
    try:
        yield
    finally:
        if w is not None:
            w._pause.clear()


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


def detail(text: str, done: int | None = None, total: int | None = None) -> None:
    """Tell the spinner that is showing, if one is, how far along it is; `done` and `total` (bytes, packages) go to a surface that draws a bar."""
    if _current is not None:
        _current.detail(text, done, total) if isinstance(_current, Working) else _current.detail(text)


def say(line: str) -> None:
    """A line of what is happening, for whoever is watching: standard error, or an event when a surface draws them. Nobody is harmed by one nobody reads."""
    if events():
        sys.stderr.write(json.dumps({"event": "message", "text": line}, ensure_ascii=False) + "\n")
    else:
        sys.stderr.write(line + "\n")
    try:
        sys.stderr.flush()
    except (OSError, ValueError):
        pass


def megabytes(done: int, total: int | None) -> str:
    mb = done / 1_000_000
    return f"{mb:.1f} of {total / 1_000_000:.1f} MB" if total else f"{mb:.1f} MB"


def growth(*folders, what: str = "downloaded"):
    """A probe for a step whose program downloads into `folders` and says nothing: how much they have grown since the step began."""
    def size() -> int:
        total = 0
        for folder in folders:
            for root, _, files in os.walk(folder):
                for f in files:
                    try:
                        total += os.lstat(os.path.join(root, f)).st_size
                    except OSError:
                        pass
        return total
    start = size()

    def probe():
        grown = size() - start
        return f"{grown / 1_000_000:.0f} MB {what}" if grown > 100_000 else ""
    return probe


class _Quiet:
    """A step that draws nothing. `claim` makes it the current step while it runs, so a step inside it adds no second line."""

    def __init__(self, claim: bool = False):
        self.claim = claim

    def __enter__(self):
        global _current
        if self.claim:
            self._previous, _current = _current, self
        return self

    def __exit__(self, *exc):
        global _current
        if self.claim:
            _current = self._previous
        return False

    def detail(self, text: str, *_) -> None:
        pass


def step(label: str, probe=None, announce: bool = False):
    """`with step("📦 Installing chromium"):` around a slow step: the spinner at a terminal, and with `announce`, one plain line at the start
    anywhere else (a log, a pipe) so a long download never looks stuck. Inside another spinner it adds nothing: one line at a time."""
    if _current is not None:
        return _Quiet()
    if events():
        return Working(label, probe=probe)
    if announce and ENABLED and os.environ.get(VARIABLE) != "never" and not visible():
        try:
            sys.stderr.write(label + "...\n")
            sys.stderr.flush()
        except (OSError, ValueError):
            pass
        return _Quiet(claim=True)
    return Working(label, probe=probe)
