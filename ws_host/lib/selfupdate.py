"""Keeping ws-host itself current (0006-onboarding FR-025): look for news, say so cheaply, and move forward only when it is safe.

Looking is a `git fetch` of ws-host's own copy; moving is a fast-forward and nothing else, exactly as for every repository (0002 FR-007).
A short note in the state directory lets a new terminal window say an update waits without running anything. Standard library only."""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from ..core import paths
from . import git

CHECK_EVERY_MINUTES = 360       # a new window looks again in the background at most this often


def root() -> Path:
    return paths.repo_root()


def checked_file() -> Path:
    return paths.state_dir() / "update-checked"


def notice_file() -> Path:
    return paths.state_dir() / "update-available"


def read_notice() -> str:
    try:
        return notice_file().read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def write_notice(behind: int) -> None:
    """The one line a new terminal window shows, or no file when ws-host is current."""
    d = paths.state_dir()
    d.mkdir(parents=True, exist_ok=True)
    checked_file().touch()
    if behind > 0:
        notice_file().write_text(f"A newer ws-host is ready ({behind} change{'s' if behind != 1 else ''}). Update it with:  ws-host update advance\n",
                                 encoding="utf-8")
    else:
        notice_file().unlink(missing_ok=True)


def state(fetch: bool = True, timeout: float = 60, offline: bool = False) -> dict:
    """Where ws-host's own copy stands against its shared branch. Never changes anything but git's own record of the remote."""
    r = root()
    s = {"path": str(r), "git": (r / ".git").exists(), "fetched": False, "behind": 0, "ahead": 0, "branch": "", "upstream": "",
         "dirty": False, "operation": None, "news": [], "problem": ""}
    if not s["git"]:
        s["problem"] = "this copy of ws-host is not a git copy, so I cannot look for news"
        return s
    s["branch"] = git.out(r, "symbolic-ref", "--short", "-q", "HEAD")
    s["upstream"] = git.out(r, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if fetch and not offline:
        try:
            f = git.run(r, "fetch", "--quiet", timeout=timeout)
            s["fetched"] = f.returncode == 0
            if f.returncode != 0:
                s["problem"] = "I could not reach GitHub to look for news: " + git.reason(f)
        except subprocess.TimeoutExpired:
            s["problem"] = f"looking for news took longer than {int(timeout)} seconds"
    if not s["upstream"]:
        s["problem"] = s["problem"] or "this copy is not connected to a shared branch"
        return s
    counts = git.out(r, "rev-list", "--left-right", "--count", "HEAD...@{u}").split()
    if len(counts) == 2:
        s["ahead"], s["behind"] = int(counts[0]), int(counts[1])
    s["dirty"] = bool(git.run(r, "status", "--porcelain=v1", "--untracked-files=no").stdout.strip())
    s["operation"] = git.operation_in_progress(r)
    if s["behind"]:
        s["news"] = [l for l in git.out(r, "log", "--format=%s", "-n", "8", "HEAD..@{u}").splitlines() if l]
    return s


def blocker(s: dict) -> str:
    """Why a move forward would not be safe, in plain words, or an empty string."""
    if s["problem"] and not s["upstream"]:
        return s["problem"]
    if s["operation"]:
        return f"{s['operation']} is in progress in it"
    if not s["branch"]:
        return "it is not on a branch"
    if s["dirty"]:
        return "it has changes you have not committed yet"
    if s["ahead"] and s["behind"]:
        return "your commits and the shared ones have both moved on, so they cannot be joined without your say-so"
    return ""


def advance(offline: bool = False) -> dict:
    """Fetch, then fast-forward only. Returns {outcome, behind, news, plain, ...}; a blocker is a plain reason and never an error."""
    s = state(True, 120, offline)
    if s["problem"] and not s["fetched"] and not offline:
        return {**s, "outcome": "unreachable", "plain": s["problem"] + ". Your copy was not touched."}
    why = blocker(s)
    if not s["behind"]:
        write_notice(0)
        note = f" It holds {s['ahead']} commit{'s' if s['ahead'] != 1 else ''} you have not pushed yet; they are safe." if s["ahead"] else ""
        return {**s, "outcome": "current", "plain": "ws-host is up to date." + note}
    if why:
        write_notice(s["behind"])
        return {**s, "outcome": "skipped", "plain": f"A newer ws-host is waiting, but I left your copy exactly as it was, because {why}. Your work is safe."}
    m = git.run(root(), "merge", "--ff-only", "--quiet", "@{u}")
    if m.returncode != 0:
        write_notice(s["behind"])
        return {**s, "outcome": "skipped", "plain": "A newer ws-host is waiting, but git would have had to overwrite something of yours, so I left your copy as it was. Your work is safe.",
                "git": git.reason(m)}
    write_notice(0)
    return {**s, "outcome": "updated", "plain": f"ws-host moved forward by {s['behind']} change{'s' if s['behind'] != 1 else ''}. Your next ws-host command already uses it."}


def due() -> bool:
    try:
        return time.time() - checked_file().stat().st_mtime > CHECK_EVERY_MINUTES * 60
    except OSError:
        return True
