"""`shell add bash|fish [--plain]`: the oh-my-posh prompt with a ws-host theme, in the shell a person names (0003-kits FR-015).

It is the one place ws-host edits a shell startup file, and chezmoi does the writing (0010-managed-config). Setup runs it by default (WS_HOST_PROMPT=no opts out); a clearly marked block is added to
~/.bashrc or to fish's config.fish, a copy of the file is kept first, and a second run changes nothing."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from ..core import paths, registry as reg
from ..core.registry import Arg, command
from ..core.resource import Action, OK, Resource, WsError
from ..install import fetch
from ..kits import shell as shell_kit

from ..lib import chezmoi, managed
from ..lib.managed import BEGIN, END, COMMENT

SHELL_ARG = Arg("shell", "SHELL", positional=True, required=True, help="bash or fish")
PLAIN_ARG = Arg("plain", flag=True, help="use ws-host-plain, which needs no Nerd Font")


def startup_file(shell: str) -> Path:
    if shell == "bash":
        return paths.home() / ".bashrc"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return (Path(xdg) if xdg and os.path.isabs(xdg) else paths.home() / ".config") / "fish" / "config.fish"


def _theme_text(name: str) -> str:
    t = shell_kit.theme_path(name)
    try:
        return "$HOME/" + str(t.relative_to(paths.home()))
    except ValueError:
        return str(t)


def block(shell: str, theme_name: str = shell_kit.PRETTY) -> str:
    return managed.block(shell, _theme_text(theme_name))


def configured(shell: str) -> bool:
    try:
        return BEGIN.format(shell=shell) in startup_file(shell).read_text(encoding="utf-8")
    except OSError:
        return False


def target(shell: str, theme_name: str = shell_kit.PRETTY, keep_existing: bool = False) -> chezmoi.Target:
    """The startup file as a managed target: a symbolic link is followed, so the file it points to is the one that changes."""
    f = startup_file(shell)
    return chezmoi.Target(f"{shell} prompt", f.resolve() if f.is_symlink() else f, shell, (_theme_text(theme_name),), keep_existing)


def add_prompt(shell: str, offline: bool = False, dry_run: bool = False, theme_name: str = shell_kit.PRETTY, keep_existing: bool = False) -> dict:
    """Give `shell` the prompt block, through chezmoi; raises WsError when it cannot. `shell add` replaces an existing block; `workspace ensure`
    passes keep_existing, so a theme a person edited into the block is never put back."""
    t = target(shell, theme_name, keep_existing)
    shown = startup_file(shell)
    before = chezmoi.current(t)
    try:
        after = managed.with_block(before, shell, _theme_text(theme_name), keep_existing)
    except managed.MarkersLost:
        raise WsError("markers", f"{shown} has the start marker and no end marker",
                      "The block ws-host added to your shell file has lost its end line, so I left the file alone. Delete the lines from the "
                      "'>>> workspaces-host' line on, then run this again.")
    if shell == "fish" and not shutil.which("fish") and not (paths.bin_dir() / "fish").exists():
        raise WsError("no-fish", "fish is not installed", "fish is not installed yet. Install it first, then run this again.",
                      [Action(("kit", "add"), "Install fish and oh-my-posh", {"kit": "shell"})], status="missing")
    if dry_run:
        return {"file": str(shown), "changed": after != before, "lines": block(shell, theme_name).splitlines(), "backup": None}
    if not (shutil.which("oh-my-posh") or (paths.bin_dir() / "oh-my-posh").exists()):
        from ..core import progress
        try:
            with progress.working("📥 Downloading oh-my-posh"):
                fetch.install(shell_kit.POSH, offline=offline)
        except fetch.FetchError as e:
            raise WsError("download", e.message, "I could not download oh-my-posh, so I left your shell file alone. Check your network and run this again.")
    backup = None
    if after != before:
        backup = chezmoi.apply_targets([t], offline)[0]
    return {"file": str(shown), "theme": theme_name, "changed": after != before, "backup": backup}


@command("shell", "add", category="setup", summary="Give bash or fish the ws-host oh-my-posh prompt (again, or the plain one)",
         args=(SHELL_ARG, PLAIN_ARG), surfaces=("cli", "editor"))
def shell_add(ctx, shell, plain=False):
    r = add_prompt(shell, ctx.offline, ctx.dry_run, shell_kit.PLAIN if plain else shell_kit.PRETTY)
    if ctx.dry_run:
        return Resource("shell-add", shell, {"plain": f"Nothing was changed. I would add a few marked lines to {r['file']}.", **r})
    reload = f"exec {shell}"
    plain = (f"Your {shell} prompt is set up. Open a new terminal window, or type {reload} to see it here." if r["changed"]
             else f"Your {shell} prompt was already set up, so nothing changed.")
    return Resource("shell-add", shell, {"plain": plain, **r, "undo": f"Delete the lines between '>>> workspaces-host' and '<<< workspaces-host' in {r['file']}.",
                                          "next": reload}, status=OK)
