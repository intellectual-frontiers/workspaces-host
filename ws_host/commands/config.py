"""`config show|check|ensure`: the files ws-host manages for a person, kept by chezmoi (0010-managed-config)."""
from __future__ import annotations

import re

from ..core import registry as reg
from ..core.registry import command
from ..core.resource import Action, FAILED, MISSING, OK, Resource, WsError
from ..kits import shell as shell_kit
from ..lib import chezmoi, managed
from . import shell as shell_cmd
from . import vscode as vscode_cmd

THEME_IN_BLOCK = re.compile(r'--config "([^"]+)"')


def managed_targets() -> list[chezmoi.Target]:
    """The files this person has asked ws-host to manage: each shell startup file that holds ws-host's block (with the theme written in it,
    so a theme a person chose stays), and VS Code's settings file when it is there."""
    out = []
    for sh in ("bash", "fish"):
        f = shell_cmd.startup_file(sh)
        text = chezmoi.current(chezmoi.Target("", f, sh))
        if managed.BEGIN.format(shell=sh) in text:
            m = THEME_IN_BLOCK.search(text.partition(managed.BEGIN.format(shell=sh))[2])
            out.append(chezmoi.Target(f"{sh} prompt", f.resolve() if f.is_symlink() else f, sh, (m.group(1) if m else shell_cmd._theme_text(shell_kit.PRETTY),)))
    from ..lib import modern
    for t in modern.targets():
        if managed.MODERN_BEGIN in chezmoi.current(t):
            out.append(modern._resolved(t))
    vs = vscode_cmd.settings_target(vscode_cmd.baseline_settings())
    if vs.path.exists():
        out.append(vs)
    return out


def _state(t: chezmoi.Target, offline: bool) -> dict:
    try:
        after = chezmoi.would_be(t, offline)
    except chezmoi.ChezmoiMissing:
        raise
    except RuntimeError as e:
        return {"name": t.name, "file": str(t.path), "state": "error", "plain": f"{t.name}: chezmoi could not work it out ({e})", "status": "error"}
    cur = chezmoi.current(t)
    if after == cur:
        return {"name": t.name, "file": str(t.path), "state": "current", "plain": f"{t.name} ({t.path}) is as ws-host would write it.", "status": "ok"}
    return {"name": t.name, "file": str(t.path), "state": "stale", "plain": f"{t.name} ({t.path}) differs from what this ws-host would write; run `ws-host config ensure`.",
            "status": "warn"}


def _states(offline: bool) -> list[dict]:
    targets = managed_targets()
    if not targets:
        return []
    try:
        chezmoi.render(targets)
        return [_state(t, offline) for t in targets]
    except chezmoi.ChezmoiMissing as e:
        raise WsError("missing-chezmoi", str(e), chezmoi.missing_plain(e), status="missing", exit_code=3)
    except chezmoi.OutsideHome as e:
        raise WsError("outside-home", f"{e} is not under your home folder", f"I only manage files under your home folder, and {e} is not.")


@command("config", "show", category="read", summary="List the files ws-host manages for you and whether each is current")
def config_show(ctx):
    rows = _states(ctx.offline)
    plain = ("ws-host manages no file of yours yet. `ws-host shell add bash` or `ws-host vscode ensure` starts one." if not rows else
             f"ws-host manages {len(rows)} file{'s' if len(rows) != 1 else ''} of yours; " +
             ("all are current." if all(r['state'] == 'current' for r in rows) else "some are older than this ws-host would write."))
    return Resource("config-list", "config", {"plain": plain, "files": rows}, status=OK)


@command("config", "check", category="check", summary="Say whether the files ws-host manages are as this ws-host would write them")
def config_check(ctx):
    rows = _states(ctx.offline)
    stale = [r for r in rows if r["state"] != "current"]
    plain = "Every managed file is current." if not stale else f"{len(stale)} managed file{'s are' if len(stale) != 1 else ' is'} not current: " + ", ".join(r["name"] for r in stale) + "."
    return Resource("config-check", "config", {"plain": plain, "files": rows}, status=FAILED if stale else OK,
                    actions=[Action(("config", "ensure"), "Bring them up to date")] if stale else [])


@command("config", "ensure", category="setup", summary="Bring the files ws-host manages up to date, keeping a copy of each first")
def config_ensure(ctx):
    targets = managed_targets()
    rows = []
    if ctx.dry_run:
        rows = _states(ctx.offline)
        return Resource("config-ensure", "config", {"plain": "Nothing was changed. " + (f"I would update {sum(r['state'] != 'current' for r in rows)} of {len(rows)} managed files." if rows else "ws-host manages no file of yours yet."),
                                                    "files": rows}, status=OK)
    backups = shell_cmd.chezmoi.apply_targets(targets, ctx.offline) if targets else []
    for t, b in zip(targets, backups):
        rows.append({"name": t.name, "file": str(t.path), "state": "updated" if b else "current", "backup": b})
    changed = [r for r in rows if r["state"] == "updated"]
    plain = (f"Updated {len(changed)} of {len(rows)} managed files; a copy of each is in ws-host's state folder." if changed else
             "Nothing needed changing." if rows else "ws-host manages no file of yours yet.")
    return Resource("config-ensure", "config", {"plain": plain, "files": rows}, status=OK)
