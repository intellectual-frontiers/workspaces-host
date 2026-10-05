"""Prototype: how ws-host would detect a user's own Homebrew (brew 7) and the tools they installed with it. Standard library only.

Detection is read-only: it never installs, updates or changes brew. It reports what is there so `doctor` can say so and so that
a provider's pinned tools, which always come first on PATH, are never shadowed by a custom one by accident.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

CANDIDATES = ("/home/linuxbrew/.linuxbrew/bin/brew", "~/.linuxbrew/bin/brew")     # the default prefix, then a per-user one


def find_brew() -> Path | None:
    found = shutil.which("brew")
    for c in ([found] if found else []) + [os.path.expanduser(c) for c in CANDIDATES]:
        if c and os.access(c, os.X_OK):
            return Path(c)
    return None


def run(brew: Path, *args: str) -> str:
    env = {**os.environ, "HOMEBREW_NO_AUTO_UPDATE": "1", "HOMEBREW_NO_ANALYTICS": "1", "HOMEBREW_NO_ENV_HINTS": "1"}
    p = subprocess.run([str(brew), *args], capture_output=True, text=True, timeout=60, env=env)
    return p.stdout.strip() if p.returncode == 0 else ""


def detect() -> dict:
    brew = find_brew()
    if brew is None:
        return {"present": False, "plain": "Homebrew is not installed. That is fine: ws-host and its providers do not need it."}
    version = run(brew, "--version").splitlines()[0] if run(brew, "--version") else "unknown"
    prefix = run(brew, "--prefix")
    major = int(version.split()[1].split(".")[0]) if version.startswith("Homebrew ") and version.split()[1][0].isdigit() else 0
    formulae = {n: v for n, _, v in (l.partition(" ") for l in run(brew, "list", "--formula", "--versions").splitlines())}
    return {"present": True, "version": version, "major": major, "prefix": prefix, "formulae": formulae,
            "plain": f"{version} is at {prefix} with {len(formulae)} formulae, which are yours: ws-host reads them and never changes them.",
            "old": major < 7}


if __name__ == "__main__":
    print(json.dumps(detect(), indent=2))
