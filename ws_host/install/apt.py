"""The package installer: the distribution's package manager, through sudo (0003-kits FR-005). Standard library only."""
from __future__ import annotations

import os
import shutil
import subprocess


class AptError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def available() -> bool:
    return shutil.which("apt-get") is not None


def is_root() -> bool:
    return os.geteuid() == 0


def interactive() -> bool:
    import sys
    return sys.stdin.isatty() and sys.stdout.isatty()


def sudo_prefix() -> list[str] | None:
    """[] when already administrator, ['sudo'] (or ['sudo', '-n'] with no terminal) when sudo exists, None when neither."""
    if is_root():
        return []
    if shutil.which("sudo") is None:
        return None
    return ["sudo"] if interactive() else ["sudo", "-n"]


def _run(argv, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, **kw)


def installed(package: str) -> bool:
    p = _run(["dpkg-query", "-W", "-f=${Status}", package])
    return p.returncode == 0 and "install ok installed" in p.stdout


def has_candidate(package: str) -> bool:
    p = _run(["apt-cache", "policy", package])
    for line in p.stdout.splitlines():
        if line.strip().startswith("Candidate:"):
            return "(none)" not in line
    return False


def resolve(specs: list[str]) -> tuple[list[str], list[str]]:
    """(the packages to use, the specs this distribution has none of). `a|b` picks the first with a candidate."""
    names, missing = [], []
    for spec in specs:
        for alt in spec.split("|"):
            if installed(alt) or has_candidate(alt):
                names.append(alt)
                break
        else:
            missing.append(spec)
    return names, missing


def to_install(names: list[str]) -> list[str]:
    return [n for n in names if not installed(n)]


def install(packages: list[str]) -> subprocess.CompletedProcess:
    """Install the packages non-interactively. Raises AptError when it may not run or the package manager fails."""
    prefix = sudo_prefix()
    if prefix is None:
        raise AptError("no-sudo", "sudo is not available")
    env = ["env", "DEBIAN_FRONTEND=noninteractive"]
    if prefix:
        u = _run([*prefix, *env, "apt-get", "update", "-qq"])
        if u.returncode != 0 and prefix == ["sudo", "-n"] and "password" in (u.stderr or "").lower():
            raise AptError("needs-password", "sudo needs a password and there is no terminal to ask it in")
    else:
        u = _run([*env, "apt-get", "update", "-qq"])
    p = _run([*prefix, *env, "apt-get", "install", "-y", "-qq", "--no-install-recommends", *packages])
    if p.returncode != 0:
        if "password" in (p.stderr or "").lower() and prefix == ["sudo", "-n"]:
            raise AptError("needs-password", "sudo needs a password and there is no terminal to ask it in")
        raise AptError("apt-failed", (p.stderr or p.stdout).strip().splitlines()[-1] if (p.stderr or p.stdout).strip() else "apt-get failed")
    return p
