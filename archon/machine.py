"""Facts about the machine, read without changing it. Standard library only."""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import env

VERSION_RX = re.compile(r"\d+(?:\.\d+)+(?:[-+.~\w]*)?")


def distro() -> dict:
    """The os-release facts (id, version, pretty name) and whether this is WSL."""
    facts: dict[str, str] = {}
    for f in ("/etc/os-release", "/usr/lib/os-release"):
        try:
            facts = env.parse(Path(f).read_text(encoding="utf-8"))
            break
        except (OSError, env.EnvError):
            continue
    try:
        wsl = "microsoft" in Path("/proc/version").read_text().lower() or bool(os.environ.get("WSL_DISTRO_NAME"))
    except OSError:
        wsl = bool(os.environ.get("WSL_DISTRO_NAME"))
    return {
        "id": facts.get("ID", "unknown"),
        "id_like": facts.get("ID_LIKE", ""),
        "version": facts.get("VERSION_ID", ""),
        "codename": facts.get("VERSION_CODENAME", ""),
        "pretty": facts.get("PRETTY_NAME", platform.system()),
        "arch": platform.machine(),
        "wsl": wsl,
    }


def debian_family(d: dict | None = None) -> bool:
    d = d or distro()
    return d["id"] in ("debian", "ubuntu") or any(x in ("debian", "ubuntu") for x in d["id_like"].split())


def python_version() -> str:
    return ".".join(map(str, sys.version_info[:3]))


def run(argv: list[str], timeout: float = 20, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, **kw)


def program_version(program: str, args: tuple[str, ...] = ("--version",)) -> str | None:
    """The first version-looking token the program prints, or None when it is absent or prints none."""
    exe = shutil.which(program)
    if not exe:
        return None
    try:
        p = run([exe, *args])
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    text = (p.stdout or "") + "\n" + (p.stderr or "")
    for line in text.splitlines():
        m = VERSION_RX.search(line)
        if m:
            return m.group(0)
    return "unknown"


def on_path(directory: Path) -> bool:
    return str(directory) in os.environ.get("PATH", "").split(os.pathsep)
