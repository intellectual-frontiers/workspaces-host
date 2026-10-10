"""Making bash, fish and git use the modern tools, through chezmoi (0003-kits FR-019, 0010-managed-config). The `modern-cli` kit and `workspace ensure` both come here."""
from __future__ import annotations

import shutil

from ..core import config, paths
from . import chezmoi, managed

MARK = managed.MODERN_BEGIN


def fish_here() -> bool:
    return bool(shutil.which("fish") or (paths.bin_dir() / "fish").exists())


def _startup(shell: str):
    from ..commands import shell as shell_cmd       # `shell add` is the one place that knows where a shell's startup file is (0003 FR-015)
    return shell_cmd.startup_file(shell)


def icons() -> bool:
    """Icons are on, as the person asked; they need a Nerd Font, and the plain prompt choice leaves them out."""
    return config.load().prompt_theme() != "ws-host-plain"


def targets(with_icons: bool | None = None) -> list[chezmoi.Target]:
    arg = "plain" if not (icons() if with_icons is None else with_icons) else "icons"
    out = [chezmoi.Target("bash modern tools", _startup("bash"), "modern-bash", (arg,))]
    if fish_here():
        out.append(chezmoi.Target("fish modern tools", _startup("fish"), "modern-fish", (arg,)))
    out.append(chezmoi.Target("git pager", paths.home() / ".gitconfig", "modern-git", (arg,)))
    return out


def _resolved(t: chezmoi.Target) -> chezmoi.Target:
    return chezmoi.Target(t.name, t.path.resolve() if t.path.is_symlink() else t.path, t.kind, t.args)


def configured() -> bool:
    """True when bash already has the lines."""
    try:
        return MARK in _startup("bash").read_text(encoding="utf-8")
    except OSError:
        return False


def apply(offline: bool = False, dry_run: bool = False, with_icons: bool | None = None) -> dict:
    """Add or refresh the lines. Returns {changed: [names], files: [paths]}; raises WsError (from chezmoi) when a file cannot be changed."""
    ts = [_resolved(t) for t in targets(with_icons)]
    changed = []
    for t in ts:
        before = chezmoi.current(t)
        try:
            after = managed.with_modern(before, t.kind[len("modern-"):], t.args[0] != "plain")
        except managed.MarkersLost:
            from ..core.resource import WsError
            raise WsError("markers", f"{t.path} has the start marker and no end marker",
                          f"The lines ws-host added to {t.path} have lost their end line, so I left the file alone. Delete the lines from the '>>> workspaces-host' line on, then run this again.")
        if after != before or not t.path.exists():
            changed.append(t)
    if changed and not dry_run:
        chezmoi.apply_targets(changed, offline)
    return {"changed": [t.name for t in changed], "files": [str(t.path) for t in changed]}
