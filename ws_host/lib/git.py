"""Git, run the way 0041-command-line FR-063 requires: never prompting, in a stable language."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

AUTH_FAILURES = ("could not read Username", "could not read Password", "Authentication failed", "terminal prompts disabled",
                 "HTTP Basic: Access denied", "Invalid username or password")


def env() -> dict:
    return {**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C", "LANG": "C", "GCM_INTERACTIVE": "never"}


def run(cwd, *args: str, timeout: float = 600) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=None if cwd is None else str(cwd), capture_output=True, text=True,
                          timeout=timeout, env=env())


def out(cwd, *args: str) -> str:
    p = run(cwd, *args)
    return p.stdout.strip() if p.returncode == 0 else ""


def reason(p: subprocess.CompletedProcess) -> str:
    """Git's own words for why it failed."""
    lines = [l.strip() for l in (p.stderr or p.stdout or "").splitlines() if l.strip()]
    return " ".join(lines[-3:]) if lines else f"git exited {p.returncode}"


def is_auth_failure(text: str) -> bool:
    return any(m in text for m in AUTH_FAILURES)


def git_dir(path: Path) -> Path | None:
    d = out(path, "rev-parse", "--absolute-git-dir")
    return Path(d) if d else None


def operation_in_progress(path: Path) -> str | None:
    d = git_dir(path)
    if not d:
        return None
    for marker, name in (("rebase-merge", "a rebase"), ("rebase-apply", "a rebase"), ("MERGE_HEAD", "a merge"),
                         ("CHERRY_PICK_HEAD", "a cherry-pick"), ("REVERT_HEAD", "a revert"), ("BISECT_LOG", "a bisect")):
        if (d / marker).exists():
            return name
    return None


def snapshot(path: Path) -> dict:
    """What 'exactly as it was' means (0002-repositories-and-trust FR-008): HEAD, branch, index, tracked-file state."""
    return {"head": out(path, "rev-parse", "HEAD"), "branch": out(path, "symbolic-ref", "-q", "HEAD"),
            "status": run(path, "status", "--porcelain=v1", "--untracked-files=all").stdout,
            "index": out(path, "ls-files", "--stage"), "stash": out(path, "stash", "list"),
            "operation": operation_in_progress(path)}
