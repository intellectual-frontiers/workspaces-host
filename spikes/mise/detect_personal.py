"""Prototype: how ws-host detects a person's own tools, read-only: Homebrew (brew 7) for custom tools, and direnv. Standard library only.

Neither is required and neither is ever installed, configured or updated by ws-host. They are suggestions for personal or custom use,
reported by `doctor` so that a person's own setup is understood and so that a provider's pinned tools, which come first on PATH
inside a provider, are never shadowed by accident. Checked against a real Homebrew 7.0.8 on Ubuntu 24.04 and Debian 12.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

BREW_CANDIDATES = ("/home/linuxbrew/.linuxbrew/bin/brew", "~/.linuxbrew/bin/brew")      # the default prefix, then a per-user one
HOOK_FILES = ("~/.bashrc", "~/.bash_profile", "~/.profile", "~/.config/fish/config.fish", "~/.zshrc")


def _run(argv: list[str], **env: str) -> str:
    p = subprocess.run(argv, capture_output=True, text=True, timeout=60, env={**os.environ, **env})
    return p.stdout.strip() if p.returncode == 0 else ""


def find(name: str, extra: tuple[str, ...] = ()) -> Path | None:
    for c in [shutil.which(name), *(os.path.expanduser(e) for e in extra)]:
        if c and os.access(c, os.X_OK):
            return Path(c)
    return None


def brew() -> dict:
    exe = find("brew", BREW_CANDIDATES)
    if exe is None:
        return {"present": False, "plain": "Homebrew is not installed. That is fine: nothing here needs it. It is a good place for your own, custom tools."}
    quiet = {"HOMEBREW_NO_AUTO_UPDATE": "1", "HOMEBREW_NO_ANALYTICS": "1", "HOMEBREW_NO_ENV_HINTS": "1"}
    first = (_run([str(exe), "--version"], **quiet).splitlines() or ["unknown"])[0]
    m = re.match(r"Homebrew (\d+)\.", first)
    major = int(m.group(1)) if m else 0
    chosen = _run([str(exe), "leaves"], **quiet).split()            # what the person asked for; `list` also holds dependencies
    return {"present": True, "version": first, "major": major, "older_than_7": 0 < major < 7, "prefix": _run([str(exe), "--prefix"], **quiet),
            "on_path": shutil.which("brew") is not None, "chosen": chosen,
            "plain": f"{first} at {_run([str(exe), '--prefix'], **quiet)}; you chose {len(chosen)} formulae. They are yours: ws-host reads them and never changes them."}


def direnv() -> dict:
    exe = find("direnv")
    if exe is None:
        return {"present": False, "plain": "direnv is not installed. That is fine: ws-host does not need it."}
    hooked = [h for h in HOOK_FILES if os.path.exists(os.path.expanduser(h)) and "direnv hook" in Path(os.path.expanduser(h)).read_text(errors="replace")]
    return {"present": True, "version": _run([str(exe), "version"]), "hooked_in": hooked,
            "plain": "direnv is installed" + (f" and hooked in {', '.join(hooked)}" if hooked else "") + ". It is yours; mise does not support using it together with mise's own activation, "
                     "so if you use both and PATH looks wrong inside a provider, try without the direnv hook first."}


def mise_activation() -> dict:
    hooked = [h for h in HOOK_FILES if os.path.exists(os.path.expanduser(h)) and "mise activate" in Path(os.path.expanduser(h)).read_text(errors="replace")]
    return {"hooked_in": hooked}


def shadows(brew_info: dict, pinned_programs: set[str]) -> list[str]:
    """Programs brew links that are named like one a provider pins, so `doctor` can warn that outside a provider the brew one may win
    and inside a provider never does. It compares program names in brew's bin directory, not formula names (`ripgrep` provides `rg`)."""
    bindir = Path(brew_info.get("prefix", "")) / "bin"
    try:
        return sorted({f.name for f in bindir.iterdir()} & pinned_programs)
    except OSError:
        return []


if __name__ == "__main__":
    print(json.dumps({"brew": brew(), "direnv": direnv(), "mise_activation": mise_activation()}, indent=2))
