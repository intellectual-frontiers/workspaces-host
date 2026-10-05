"""`workspace advance|status|set` (0002-repositories-and-trust FR-016, FR-017): the one command a person runs first."""
from __future__ import annotations

import shutil

from ..core import config, env, registry as reg
from ..core.registry import Arg, command
from ..core.resource import Action, FAILED, OK, Resource, WsError
from ..lib import git, kitrun, repos, trust as trust_mod
from . import auth as auth_cmd, doctor as doctor_cmd, shell as shell_cmd, vscode as vscode_cmd


def declared_kits(cfg) -> dict[str, list[str]]:
    """The kits cloned repositories name in their own files (information: needs no trust to read)."""
    out: dict[str, list[str]] = {}
    for rid in repos.known(cfg)[0]:
        p = rid.path(cfg)
        if (p / ".git").exists():
            for k in env.words(repos.read_needs(p).get("WS_HOST_KIT")):
                out.setdefault(k, []).append(str(rid))
    return out


def pull_ff() -> str:
    return git.out(None, "config", "--global", "--get", "pull.ff")


@command("workspace", "status", category="read", summary="Say how this machine and your repositories stand")
def workspace_status(ctx):
    cfg = config.load()
    found, invalid = repos.known(cfg)
    rows = [repos.state(r, cfg) for r in sorted(found, key=str)]
    kits = declared_kits(cfg)
    have = {k["name"]: k["installed"] for k in doctor_cmd.kits_state.kit_report()}
    kit_rows = [{"name": k, "status": "ok" if have.get(k) else "warn", "installed": bool(have.get(k)), "needed_by": v} for k, v in sorted(kits.items())]
    needs = sum(not r["cloned"] or r.get("behind") for r in rows) + sum(not k["installed"] for k in kit_rows)
    plain = "Everything is in place." if rows and not needs else ("I do not know any repositories yet. Add one with: ws-host repo add github.com/ORG/REPO" if not rows else "Some things need doing; `workspace advance` does them.")
    return Resource("workspace-status", "workspace", {"plain": plain, "repositories": rows, "kits": kit_rows, "ignored": invalid},
                    actions=[Action(("workspace", "advance"), "Bring everything up to date")] if rows else [])


def _step(name, plain):
    return Resource("progress", name, {"plain": plain, "step": name})


@command("workspace", "advance", category="setup", summary="Install your kits, check sign-in, copy missing repositories, update the rest, set up the editor, check health",
         surfaces=("cli", "editor"))
def workspace_advance(ctx):
    cfg = config.load()
    steps = []
    mine = {k: ["your configuration"] for k in cfg.kits()}
    yield _step("your-kits", "Installing the tools you always want...")
    r = kitrun.ensure(ctx, mine) if not ctx.dry_run else {"status": "ok", "plain": "Would install: " + (", ".join(mine) or "nothing") + "."}
    steps.append({"name": "your-kits", "status": r["status"], "plain": r["plain"]})
    kit_actions = list(r.get("actions", []))
    yield _step("sign-in", "Checking that you are signed in...")
    a = auth_cmd.auth_status(ctx)
    github = next((f for f in a.data["forges"] if f["name"] == "github.com"), None)
    steps.append({"name": "sign-in", "status": "ok" if all(f["signed_in"] for f in a.data["forges"]) else "warn", "plain": a.data["plain"]})
    if github and github["signed_in"] is False and not ctx.dry_run:
        # 0006-onboarding FR-005: sign in first, once, in one prescribed way, before anything private is copied.
        yield Resource("workspace-advance", "needs-sign-in",
                       {"plain": "Sign in to GitHub first. It takes a code and a web page, and then you run this again.", "steps": steps,
                        "next": "Run `ws-host auth new github`, follow the code it shows, then run `ws-host workspace advance` again."},
                       actions=[Action(("auth", "new"), "Sign in to GitHub", {"forge": "github"}), Action(("workspace", "advance"), "Run this again")] + kit_actions)
        return
    found, invalid = repos.known(cfg)
    if ctx.dry_run:
        rows = [repos.state(r, cfg) for r in sorted(found, key=str)]
        todo = [("would copy " if not r["cloned"] else "would check ") + r["id"] for r in rows]
        yield Resource("workspace-advance", "dry-run", {"plain": "Nothing was changed. This is what I would do.", "steps": steps,
                                                        "would": todo, "kits": declared_kits(cfg)})
        return
    yield _step("copy", "Copying repositories that are missing...")
    added = []
    pending = sorted(found, key=str)
    seen = set()
    while pending:
        for r in pending:
            seen.add(r)
            if not (r.path(cfg) / ".git").exists():
                added.append(repos.clone(r, cfg))
        pending = [r for r in sorted(repos.known(cfg)[0], key=str) if r not in seen]
    steps.append({"name": "copy", "status": "fail" if any(r["outcome"] == "failed" for r in added) else "ok",
                  "plain": repos.summarize(added) if added else "Nothing was missing."})
    yield _step("update", "Bringing repositories up to date...")
    updated = [repos.advance(r, cfg) for r in sorted(repos.known(cfg)[0], key=str) if (r.path(cfg) / ".git").exists()]
    steps.append({"name": "update", "status": "fail" if any(r["outcome"] == "failed" for r in updated) else "ok", "plain": repos.summarize(updated)})
    yield _step("kits", "Checking the kits your repositories ask for...")
    declared = {k: v for k, v in declared_kits(cfg).items() if k not in mine}
    kit_result = kitrun.ensure(ctx, declared)
    steps.append({"name": "kits", "status": kit_result["status"], "plain": kit_result["plain"]})
    yield _step("editor", "Checking VS Code...")
    editor_actions = []
    if shutil.which("code"):
        try:
            if not vscode_cmd.extension_installed():
                er = vscode_cmd.install_extension(False)
                steps.append({"name": "editor", "status": "ok", "plain": er["plain"]})
            else:
                steps.append({"name": "editor", "status": "ok", "plain": "The VS Code extension is installed."})
            editor_actions.append(Action(("vscode", "advance"), "Set up VS Code with the recommended extensions and settings"))
        except WsError as e:
            steps.append({"name": "editor", "status": "fail", "plain": e.plain})
    else:
        steps.append({"name": "editor", "status": "warn", "plain": "VS Code is not reachable from this terminal yet. Install it on Windows, open it once from here with `code .`, then run `ws-host vscode advance`."})
    yield _step("doctor", "Checking this machine's health...")
    d = doctor_cmd.report()
    bad = [c for c in d["checks"] if c["status"] == "fail"]
    steps.append({"name": "doctor", "status": "fail" if bad else "ok", "plain": doctor_cmd._plain(d["checks"])})
    results = added + updated
    failed = any(s["status"] == "fail" for s in steps)
    prompt_actions = [] if shell_cmd.configured("bash") else [Action(("shell", "add"), "Give bash the coach prompt", {"shell": "bash"})]
    actions = _auth_actions(results, cfg) + kit_actions + kit_result.get("actions", []) + editor_actions + prompt_actions
    plain = ("Everything is up to date." if not failed and not any(r["outcome"] in ("skipped",) for r in results) else
             "Done, with a few things to look at." if not failed else "Done, but some things did not work. The steps below say which.")
    yield Resource("workspace-advance", "workspace", {"plain": plain, "steps": steps, "repositories": results, "ignored": invalid},
                   actions=actions, status=FAILED if failed else OK)


def _auth_actions(results, cfg):
    acts, seen = [], set()
    for r in results:
        if r.get("auth"):
            for a in repos.sign_in_action(repos.parse_id(r["id"]), cfg):
                k = (a.words, tuple(sorted(a.fields.items())))
                if k not in seen:
                    seen.add(k)
                    acts.append(a)
    return acts


@command("workspace", "set", category="setup", summary="Make git's Sync button safe: set pull.ff to only",
         args=(Arg("pull_ff_only", flag=True, help="set git's pull.ff to only"),), surfaces=("cli", "editor"))
def workspace_set(ctx, pull_ff_only):
    if not pull_ff_only:
        raise WsError("usage", "name what to set: --pull-ff-only", "Tell me what to change. The one thing I can set is --pull-ff-only.", exit_code=2)
    if ctx.dry_run:
        return Resource("workspace", "git", {"plain": "Nothing was changed. I would set git's pull.ff to only.", "from": pull_ff() or "unset"})
    before = pull_ff()
    p = git.run(None, "config", "--global", "pull.ff", "only")
    if p.returncode != 0:
        raise WsError("git-config", git.reason(p), "I could not change your git settings.")
    return Resource("workspace", "git", {"plain": "Git's Sync button now only moves forward, and never rewrites your work.", "from": before or "unset", "to": "only"})
