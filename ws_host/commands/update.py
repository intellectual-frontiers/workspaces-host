"""`update [--check]`: bring everything current with one command (0041-command-line FR-073, 0006-onboarding FR-025): ws-host itself, then, with the newest code,
every repository, the kits, the editor, what the providers in use pin, and what nothing pins any more."""
from __future__ import annotations

import json
import os
import subprocess
import sys

from ..core import config, paths
from ..core import registry as reg
from ..core.registry import Arg, command
from ..core.resource import Action, OK, Resource
from ..lib import completion, selfupdate, updates


def _report(s: dict) -> dict:
    return {"copy": s["path"], "branch": s["branch"] or "none", "behind": s["behind"], "ahead": s["ahead"], "whats_new": s["news"]}


def _look(ctx, background: bool) -> Resource:
    looked = None
    if background:
        looked = updates.look(config.load(), ctx.offline)          # repositories too, so the note a new terminal shows is true of all of them
    s = selfupdate.state(True, 60 if background else 30, ctx.offline)
    if looked is not None and (s["fetched"] or ctx.offline):
        pass                                                         # the look above wrote the note
    elif s["fetched"] or ctx.offline:
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


def _launcher() -> str:
    return os.environ.get("WS_HOST_LAUNCHER") or str(paths.repo_root() / "ws-host")      # the variable is for tests


def _child(ctx, words: list[str]) -> tuple[int, list[dict]]:
    """Run another ws-host command with the newest code. At a person's terminal it shares the terminal, so its spinners, its progress and the questions it asks
    (enabling a repository is the person's own yes) work as ever; for a program reading JSON it answers as JSON."""
    argv = [_launcher(), *words] + (["--offline"] if ctx.offline else [])
    if ctx.mode == "text":
        return subprocess.run(argv).returncode, []
    p = subprocess.run([*argv, "--json"], capture_output=True, text=True, env={**os.environ, "WS_HOST_PROGRESS": "always"})
    docs = []
    for line in p.stdout.splitlines():
        try:
            docs.append(json.loads(line))
        except ValueError:
            pass
    return p.returncode, docs


def _upgrade(ctx, tools=False):
    """ws-host first; then, in a new process so that it is the newest code that does the rest: repositories, kits, editor and what providers pin, then the
    clean-up of what nothing pins any more. With `tools`, also the tools that float with their newest release (the cloud CLIs, the modern command-line tools), which an ordinary update leaves alone
    so that it stays quick (0003-kits FR-017)."""
    r = selfupdate.update(ctx.offline)
    first = {"plain": r["plain"], **_report(r)}
    if ctx.mode == "text":
        yield Resource("progress", "update-ws-host", {"plain": "🔄 " + r["plain"], "step": "update-ws-host"})
    results, worst = [], 0
    for words in (["workspace", "ensure"], *([["kit", "sync"]] if tools else []), ["toolchain", "remove", "--unused"]):
        code, docs = _child(ctx, words)
        results.append({"command": "ws-host " + " ".join(words), "exit": code})
        if docs:
            results[-1]["answer"] = docs[-1].get("data", {}).get("plain", "")
        if words[0] == "workspace":
            worst = code
        if code == 3 and words[0] == "workspace":
            break
    if ctx.mode != "text":
        yield Resource("update", "ws-host", {"plain": r["plain"] + " " + " ".join(x.get("answer", "") for x in results if x.get("answer")), "ws_host": first, "steps": results},
                       status=OK if worst == 0 else FAILED)
    ctx.exit_code = worst or None


@command("update", category="setup", summary="Bring everything up to date: ws-host, your repositories, the editor and what they need; only where nothing of yours is in the way; --check only looks",
         args=(Arg("check", flag=True, help="only look for a newer version and say what is new; change nothing"),
               Arg("cached", flag=True, help="with --check: do not use the network; say what the last look found"),
               Arg("background", flag=True, help="with --check: look quietly and leave a note for new terminal windows"),
               Arg("tools", flag=True, help="also bring the tools that float with their newest release up to date (the cloud CLIs, the modern command-line tools); an ordinary update leaves them alone")),
         surfaces=("cli", "editor"))
def update(ctx, check=False, cached=False, background=False, tools=False):
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
    if not ctx.dry_run and not os.environ.get("WS_HOST_UPDATE_SELF_ONLY"):
        return _upgrade(ctx, tools)
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
