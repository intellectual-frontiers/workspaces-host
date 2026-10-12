"""Python environments from a repository's `uv.lock` (0011-archon FR-017). Standard library only.

A set of dependency groups of `pyproject.toml` is synced, frozen, into one environment inside the user's cache: nothing is resolved, upgraded or installed
that the lock does not hold, and no interpreter or site-packages that `archon` did not create is touched."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from . import progress

READY = ".archon-ready"
UV_HINT = "install uv (https://docs.astral.sh/uv/getting-started/installation/)"
DEFAULT_PYTHON = ">=3.14"


class EnvError(Exception):
    """An environment that cannot be prepared (exit status 3)."""
    exit_code = 3

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def requires_python(project: Path) -> str:
    """The Python the repository allows, from the one place it is written: `requires-python` in its pyproject.toml."""
    try:
        spec = tomllib.loads((Path(project) / "pyproject.toml").read_text(encoding="utf-8"))["project"]["requires-python"]
        return spec if isinstance(spec, str) and spec.strip() else DEFAULT_PYTHON
    except (OSError, ValueError, KeyError):
        return DEFAULT_PYTHON


def uv() -> str:
    exe = shutil.which("uv")
    if not exe:
        raise EnvError("missing-program", f"uv is needed and is not on PATH: {UV_HINT}")
    return exe


def cache_dir() -> Path:
    p = subprocess.run([uv(), "cache", "dir"], capture_output=True, text=True)
    if p.returncode != 0 or not p.stdout.strip():
        raise EnvError("uv-cache", "uv could not say where its cache is")
    return Path(p.stdout.strip())


def env_dir(project: Path, groups: list[str], cache: Path) -> Path:
    """One environment per set of groups and per lock: a lock that changes makes a new one, and the old is left to uv's cache to forget."""
    lock = Path(project) / "uv.lock"
    stamp = hashlib.sha256(lock.read_bytes() + "\n".join(sorted(groups)).encode()).hexdigest()[:16]
    return cache / "archon" / f"{'+'.join(sorted(groups))[:60]}-{stamp}"


def python_of(env: Path) -> Path:
    return env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def prepare(project: Path, groups: list[str], *, offline: bool | None = None, python: str | None = None, packages: list[str] | None = None,
            command: str = "the command") -> Path:
    """The Python of an environment holding exactly the locked packages of `groups`, creating it with uv if needed. Raises EnvError (exit 3) naming
    the packages and the command to run once online when offline and uv's cache lacks something."""
    project = Path(project)
    offline = os.environ.get("ARCHON_OFFLINE", "") not in ("", "0") if offline is None else offline
    if not (project / "uv.lock").is_file():
        raise EnvError("no-lock", f"{project / 'uv.lock'} is missing; the dependency groups {', '.join(groups)} cannot be installed from nothing")
    cache = cache_dir()
    env = env_dir(project, groups, cache)
    py = python_of(env)
    if py.is_file() and (env / READY).is_file():
        return py
    argv = [uv(), "sync", "--quiet", "--frozen", *[a for g in groups for a in ("--only-group", g)], "--project", str(project),
            "--python", python or sys.executable, *(["--offline"] if offline else [])]
    with progress.step(f"\U0001F4E6 Preparing the packages {', '.join(groups)} need", progress.growth(cache), announce=True):
        p = subprocess.run(argv, capture_output=True, text=True, env={**os.environ, "UV_PROJECT_ENVIRONMENT": str(env)})
    if p.returncode != 0:
        shutil.rmtree(env, ignore_errors=True)
        names = ", ".join(packages or groups)
        if offline:
            raise EnvError("offline", f"offline: {names} are needed and uv's cache lacks something; run {command} once online to fill the cache")
        raise EnvError("sync", f"uv could not prepare the environment of {', '.join(groups)}: {p.stderr.strip()[-400:]}")
    (env / READY).write_text("\n".join(sorted(groups)) + "\n", encoding="utf-8")
    return py
