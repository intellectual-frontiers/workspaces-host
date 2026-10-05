"""`shell add bash|fish [--plain]`: the oh-my-posh prompt with a ws-host theme, in the shell a person names (0003-kits FR-015).

It is the one place ws-host edits a shell startup file. Setup runs it by default (WS_HOST_PROMPT=no opts out); a clearly marked block is added to
~/.bashrc or to fish's config.fish, a copy of the file is kept first, and a second run changes nothing."""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from ..core import paths, registry as reg
from ..core.registry import Arg, command
from ..core.resource import Action, OK, Resource, WsError
from ..install import fetch
from ..kits import shell as shell_kit

BEGIN = "# >>> workspaces-host: prompt (ws-host shell add {shell}) >>>"
END = "# <<< workspaces-host <<<"
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


COMMENT = ("# Delete these lines to go back to your old prompt. To change the look, edit the theme name on the next lines: ws-host-pretty needs a\n"
           "# Nerd Font in your terminal, ws-host-plain does not. Or run: ws-host shell add {shell} --plain")


def block(shell: str, theme_name: str = shell_kit.PRETTY) -> str:
    theme = _theme_text(theme_name)
    comment = COMMENT.format(shell=shell)
    if shell == "bash":
        body = (f'{comment}\n'
                'case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) PATH="$HOME/.local/bin:$PATH" ;; esac\n'
                'if command -v oh-my-posh >/dev/null 2>&1; then\n'
                f'  eval "$(oh-my-posh init bash --config "{theme}")"\n'
                'fi')
    else:
        body = (f'{comment}\n'
                'if status is-interactive\n'
                '  fish_add_path -g $HOME/.local/bin\n'
                '  if command -q oh-my-posh\n'
                f'    oh-my-posh init fish --config "{theme}" | source\n'
                '  end\n'
                'end')
    return f"{BEGIN.format(shell=shell)}\n{body}\n{END}\n"


def configured(shell: str) -> bool:
    try:
        return BEGIN.format(shell=shell) in startup_file(shell).read_text(encoding="utf-8")
    except OSError:
        return False


def _with_block(text: str, shell: str, theme_name: str = shell_kit.PRETTY) -> str:
    """The file's text with the block added, or the existing block replaced; nothing outside the markers is touched."""
    new = block(shell, theme_name)
    begin = BEGIN.format(shell=shell)
    if begin in text:
        head, _, rest = text.partition(begin)
        _, _, tail = rest.partition(END + "\n")
        if END not in rest:
            raise WsError("markers", f"{startup_file(shell)} has the start marker and no end marker",
                          "The block ws-host added to your shell file has lost its end line, so I left the file alone. Delete the lines from the "
                          "'>>> workspaces-host' line on, then run this again.")
        return head + new + tail
    return text + ("" if not text or text.endswith("\n") else "\n") + ("\n" if text else "") + new


def add_prompt(shell: str, offline: bool = False, dry_run: bool = False, theme_name: str = shell_kit.PRETTY, keep_existing: bool = False) -> dict:
    """Give `shell` the prompt block; raises WsError when it cannot. `shell add` replaces an existing block; `workspace advance` passes
    keep_existing, so a theme a person edited into the block is never put back."""
    target = startup_file(shell)
    real = target.resolve() if target.is_symlink() else target
    before = real.read_text(encoding="utf-8") if real.exists() else ""
    after = before if keep_existing and BEGIN.format(shell=shell) in before else _with_block(before, shell, theme_name)
    if shell == "fish" and not shutil.which("fish") and not (paths.bin_dir() / "fish").exists():
        raise WsError("no-fish", "fish is not installed", "fish is not installed yet. Install it first, then run this again.",
                      [Action(("kit", "add"), "Install fish and oh-my-posh", {"kit": "shell"})], status="missing")
    if dry_run:
        return {"file": str(target), "changed": after != before, "lines": block(shell, theme_name).splitlines(), "backup": None}
    if not (shutil.which("oh-my-posh") or (paths.bin_dir() / "oh-my-posh").exists()):
        from ..core import progress
        try:
            with progress.working("Downloading oh-my-posh"):
                fetch.install(shell_kit.POSH, offline=offline)
        except fetch.FetchError as e:
            raise WsError("download", e.message, "I could not download oh-my-posh, so I left your shell file alone. Check your network and run this again.")
    backup = None
    if after != before:
        if real.exists():
            backup = paths.state_dir() / "backups" / f"{real.name}.{time.strftime('%Y%m%d-%H%M%S')}"
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(real, backup)
        real.parent.mkdir(parents=True, exist_ok=True)
        tmp = real.with_name(f".{real.name}.ws-host.new")
        tmp.write_text(after, encoding="utf-8")
        if real.exists():
            shutil.copymode(real, tmp)
        os.replace(tmp, real)
    return {"file": str(target), "theme": theme_name, "changed": after != before, "backup": str(backup) if backup else None}


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
