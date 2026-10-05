"""`update [--check]`: keep ws-host itself current (0041-command-line FR-073, 0006-onboarding FR-025)."""
from __future__ import annotations

from ..core import registry as reg
from ..core.registry import Arg, command
from ..core.resource import Action, OK, Resource
from ..lib import completion, selfupdate


def _report(s: dict) -> dict:
    return {"copy": s["path"], "branch": s["branch"] or "none", "behind": s["behind"], "ahead": s["ahead"], "whats_new": s["news"]}


def _look(ctx, background: bool) -> Resource:
    s = selfupdate.state(True, 60 if background else 30, ctx.offline)
    if s["fetched"] or ctx.offline:
        selfupdate.write_notice(s["behind"])
    elif background:
        selfupdate.checked_file().parent.mkdir(parents=True, exist_ok=True)
        selfupdate.checked_file().touch()           # a network that was down is not asked again at once
    if s["problem"] and not s["upstream"] or (s["problem"] and not s["fetched"] and not ctx.offline):
        return Resource("update-check", "ws-host", {"plain": s["problem"][0].upper() + s["problem"][1:] + ".", **_report(s)})
    if not s["behind"]:
        return Resource("update-check", "ws-host", {"plain": "ws-host is up to date.", **_report(s)})
    why = selfupdate.blocker(s)
    plain = f"A newer ws-host is ready: {s['behind']} change{'s' if s['behind'] != 1 else ''}."
    if why:
        plain += f" I will leave your copy as it is for now, because {why}."
    return Resource("update-check", "ws-host", {"plain": plain, **_report(s)}, actions=[] if why else [Action(("update",), "Update ws-host")])


@command("update", category="setup", summary="Move ws-host to its newest version, only when nothing of yours is in the way; --check only looks",
         args=(Arg("check", flag=True, help="only look for a newer version and say what is new; change nothing"),
               Arg("cached", flag=True, help="with --check: do not use the network; say what the last look found"),
               Arg("background", flag=True, help="with --check: look quietly and leave a note for new terminal windows")),
         surfaces=("cli", "editor"))
def update(ctx, check=False, cached=False, background=False):
    if cached:
        note = selfupdate.read_notice()
        return Resource("update-check", "ws-host", {"plain": note or "As far as the last look knew, ws-host is up to date.", "waiting": bool(note)},
                        actions=[Action(("update",), "Update ws-host")] if note else [])
    if check or background:
        return _look(ctx, background)
    if ctx.dry_run:
        s = selfupdate.state(True, 30, ctx.offline)
        why = selfupdate.blocker(s)
        return Resource("update", "ws-host", {"plain": "Nothing was changed. " + (
            "ws-host is up to date." if not s["behind"] else f"I would move ws-host forward by {s['behind']} change{'s' if s['behind'] != 1 else ''}."
            if not why else f"A newer ws-host is waiting, but I would leave your copy as it is, because {why}."), **_report(s)})
    r = selfupdate.update(ctx.offline)
    if r["outcome"] == "updated":
        try:
            for sh in ("bash", "fish"):
                if sh == "bash" or __import__("shutil").which("fish"):
                    completion.install(sh)       # the commands may have changed; Tab should know
        except OSError:
            pass
    return Resource("update", "ws-host", {"plain": r["plain"], **_report(r), **({"git": r["git"]} if r.get("git") else {})},
                    actions=[Action(("workspace", "ensure"), "Bring your repositories up to date too")] if r["outcome"] == "updated" else [],
                    status=OK)
