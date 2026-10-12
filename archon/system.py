"""The computer's package manager as a source of programs (0011-archon FR-011). Standard library only.

Supported: `apt`, `dnf`, `apk` and `brew`. A manager is used only when it offers a version the requirement accepts, installs non-interactively, and
runs with administrator rights only as root or through `sudo` (without a password when nobody is attending)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess

from . import apt


class SystemInstallError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


PROGRAMS = {"apt": "apt-get", "dnf": "dnf", "apk": "apk", "brew": "brew"}


def detect(path: str | None = None) -> str | None:
    """The package manager this computer has, in the order apt, dnf, apk, brew; None when it has none."""
    for name, program in PROGRAMS.items():
        if shutil.which(program, path=path):
            return name
    return None


def _run(argv: list[str], timeout: float = 90) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(argv, 1, "", str(e))


def candidate(manager: str, spec: str) -> tuple[str | None, str | None]:
    """(the package to use, the version the manager offers) for `a|b` (the first it has); (None, None) when it has none."""
    for pkg in spec.split("|"):
        version = _offered(manager, pkg)
        if version:
            return pkg, version
    return None, None


def _offered(manager: str, pkg: str) -> str | None:
    if manager == "apt":
        for line in _run(["apt-cache", "policy", pkg]).stdout.splitlines():
            if line.strip().startswith("Candidate:"):
                v = line.split(":", 1)[1].strip()
                return None if v in ("(none)", "") else v
        return None
    if manager == "dnf":
        out = _run(["dnf", "-q", "repoquery", "--latest-limit=1", "--qf", "%{version}", pkg]).stdout.strip().splitlines()
        return out[0].strip() if out else None
    if manager == "apk":
        lines = _run(["apk", "policy", pkg]).stdout.splitlines()
        for line in lines[1:]:
            if line.strip().endswith(":") and line.startswith(" "):
                return line.strip().rstrip(":")
        return None
    if manager == "brew":
        p = _run(["brew", "info", "--json=v2", pkg])
        try:
            return json.loads(p.stdout)["formulae"][0]["versions"]["stable"]
        except (ValueError, KeyError, IndexError):
            return None
    return None


def administrator(manager: str) -> tuple[list[str] | None, str]:
    """(the command prefix that gives administrator rights, why not when None). Homebrew never runs as root and needs none."""
    if manager == "brew":
        return ([], "") if os.geteuid() != 0 else (None, "Homebrew refuses to run as root")
    prefix = apt.sudo_prefix()
    if prefix is None:
        return None, "this is not root and there is no sudo"
    if prefix == ["sudo", "-n"] and subprocess.run(["sudo", "-n", "true"], capture_output=True, stdin=subprocess.DEVNULL).returncode != 0:
        return None, "sudo needs a password and nobody can type it here"
    return prefix, ""


def install_events(manager: str, pkg: str):
    """Install one package non-interactively, as a stream of (kind, text) like `apt.install_events`. Raises SystemInstallError."""
    prefix, why = administrator(manager)
    if prefix is None:
        raise SystemInstallError("no-rights", why)
    if manager == "apt":
        try:
            yield from apt.install_events([pkg])
        except apt.AptError as e:
            raise SystemInstallError(e.code, e.message) from e
        return
    argv = {"dnf": ["dnf", "install", "-y", pkg], "apk": ["apk", "add", "--no-cache", pkg], "brew": ["brew", "install", pkg]}[manager]
    yield ("step", f"\U0001F4E6 Installing {pkg}")
    status, lines = yield from apt.stream([*prefix, *argv])
    if status != 0:
        tail = [x.strip() for x in lines if x.strip()][-3:]
        raise SystemInstallError("failed", " ".join(tail) or f"{argv[0]} failed")
    yield ("done", f"Installed {pkg}.")
