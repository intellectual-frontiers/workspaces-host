"""`workspace ensure|status|set` (0002-repositories-and-trust FR-016, FR-017): the one command a person runs first."""
from __future__ import annotations

import shutil

from ..core import config, env, paths, registry as reg
from ..core.registry import Arg, command
from ..core.resource import Action, FAILED, OK, Resource, WsError
from ..lib import completion as completion_lib, git, kitrun, repos, selfupdate, trust as trust_mod, updates
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
    plain = "Everything is in place." if rows and not needs else ("I do not know any repositories yet. Add one with: ws-host repo add github.com/ORG/REPO" if not rows else "Some things need doing; `workspace ensure` does them.")
    return Resource("workspace-status", "workspace", {"plain": plain, "repositories": rows, "kits": kit_rows, "ignored": invalid},
                    actions=[Action(("workspace", "ensure"), "Ensure everything is set up and up to date")] if rows else [])


@command("updates", "status", category="read", summary="Look quietly for news in ws-host and your repositories; changes nothing",
         args=(Arg("fresh", flag=True, help="ask the network even if it was asked a few minutes ago"),), surfaces=("cli", "editor"))
def workspace_updates(ctx, fresh=False):
    r = updates.look(config.load(), ctx.offline, 0 if fresh else updates.FRESH_SECONDS)
    return Resource("workspace-updates", "workspace", {"plain": r["plain"], "waiting": r["waiting"], "items": r["items"], "unreachable": r["unreachable"]},
                    actions=[Action(("update",), "Update everything")] if r["waiting"] else [])


def _step(name, plain):
    return Resource("progress", name, {"plain": plain, "step": name})


@command("workspace", "ensure", category="setup", summary="Install your kits, check sign-in, copy missing repositories, update the rest, set up the editor, check health",
         surfaces=("cli", "editor"))
def workspace_ensure(ctx):
    cfg = config.load()
    steps = []
    mine = {k: ["your configuration"] for k in cfg.kits()}
    yield _step("your-kits", "Installing the tools you always want...")
    r = kitrun.ensure(ctx, mine) if not ctx.dry_run else {"status": "ok", "plain": "Would install: " + (", ".join(mine) or "nothing") + "."}
    steps.append({"name": "your-kits", "status": r["status"], "plain": r["plain"]})
    kit_actions = list(r.get("actions", []))
    if cfg.prompt_theme() and not ctx.dry_run:
        yield _step("prompt", "Giving your terminal its prompt...")
        steps.append(_prompt_step(ctx, cfg.prompt_theme()))
    if cfg.modern() and not ctx.dry_run:
        yield _step("modern-cli", "Making your terminal use the modern tools...")
        steps.append(_modern_step(ctx))
    yield _step("completions", "Setting up Tab completion...")
    steps.append(_completion_step())
    yield _step("sign-in", "Checking that you are signed in...")
    a = auth_cmd.auth_status(ctx)
    github = next((f for f in a.data["forges"] if f["name"] == "github.com"), None)
    steps.append({"name": "sign-in", "status": "ok" if all(f["signed_in"] for f in a.data["forges"]) else "warn", "plain": a.data["plain"]})
    if github and github["signed_in"] is False and not ctx.dry_run:
        # 0006-onboarding FR-005: sign in first, once, in one prescribed way, before anything private is copied.
        yield Resource("workspace-ensure", "needs-sign-in",
                       {"plain": "Sign in to GitHub first. It takes a code and a web page, and then you run this again.", "steps": steps,
                        "next": "Run `ws-host auth new github`, follow the code it shows, then run `ws-host workspace ensure` again."},
                       actions=[Action(("auth", "new"), "Sign in to GitHub", {"forge": "github"}), Action(("workspace", "ensure"), "Run this again")] + kit_actions)
        return
    found, invalid = repos.known(cfg)
    if ctx.dry_run:
        rows = [repos.state(r, cfg) for r in sorted(found, key=str)]
        todo = [("would copy " if not r["cloned"] else "would check ") + r["id"] for r in rows]
        if cfg.modern():
            todo.append("would make bash, fish and git use the modern tools")
        if cfg.prompt_theme():
            todo.append(f"would give your terminal the {cfg.prompt_theme()} prompt")
        yield Resource("workspace-ensure", "dry-run", {"plain": "Nothing was changed. This is what I would do.", "steps": steps,
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
    updated = [repos.sync(r, cfg) for r in sorted(repos.known(cfg)[0], key=str) if (r.path(cfg) / ".git").exists()]
    steps.append({"name": "update", "status": "fail" if any(r["outcome"] == "failed" for r in updated) else "ok", "plain": repos.summarize(updated)})
    try:     # ws-host's own copy may just have moved forward; the note a new window shows must follow it
        mine = selfupdate.state(False)
        if mine["git"] and mine["upstream"]:
            selfupdate.write_notice(mine["behind"])
    except OSError:
        pass
    yield _step("kits", "Checking the kits your repositories ask for...")
    declared = {k: v for k, v in declared_kits(cfg).items() if k not in mine}
    kit_result = kitrun.ensure(ctx, declared)
    updates.settle(cfg)
    steps.append({"name": "kits", "status": kit_result["status"], "plain": kit_result["plain"]})
    yield _step("editor", "Checking VS Code...")
    editor_actions = []
    if shutil.which("code"):
        # The editor is part of the setup, not a chore left to the person: the Workspaces Console is built from this clone, the providers in use are
        # enabled and everything they pin is installed, and the managed files are current (0009-workspaces-console FR-052).
        done = None
        for res in vscode_cmd.vscode_ensure(ctx):
            if res.kind == "progress":
                yield res
            else:
                done = res
        if done is None:
            steps.append({"name": "editor", "status": "warn", "plain": "VS Code did not answer. Run `ws-host vscode ensure` to try again."})
        else:
            inner = {r["status"] for r in done.data.get("steps", [])}
            steps.append({"name": "editor", "status": "fail" if done.status == FAILED or "fail" in inner else "warn" if inner - {"ok"} else "ok", "plain": done.data["plain"]})
            editor_actions += list(done.actions)
    else:
        steps.append({"name": "editor", "status": "warn", "plain": "VS Code is not reachable from this terminal yet. Install it on Windows, open it once from here with `code .`, then run `ws-host update`."})
    yield _step("doctor", "Checking this machine's health...")
    d = doctor_cmd.report()
    bad = [c for c in d["checks"] if c["status"] == "fail"]
    steps.append({"name": "doctor", "status": "fail" if bad else "ok", "plain": doctor_cmd._plain(d["checks"])})
    results = added + updated
    failed = any(s["status"] == "fail" for s in steps)
    actions = _auth_actions(results, cfg) + kit_actions + kit_result.get("actions", []) + editor_actions
    plain = ("Everything is up to date." if not failed and not any(r["outcome"] in ("skipped",) for r in results) else
             "Done, with a few things to look at." if not failed else "Done, but some things did not work. The steps below say which.")
    yield Resource("workspace-ensure", "workspace", {"plain": plain, "steps": steps, "repositories": results, "ignored": invalid},
                   actions=actions, status=FAILED if failed else OK)


def _completion_step() -> dict:
    """0006-onboarding FR-023: Tab completes ws-host in bash, and in fish when it is there. Files only; no startup file is touched."""
    done, notes = [], []
    for sh in ("bash", "fish"):
        if sh == "fish" and not (shutil.which("fish") or (paths.bin_dir() / "fish").exists()):
            continue
        try:
            r = completion_lib.install(sh)
        except OSError as e:
            return {"name": "completions", "status": "warn", "plain": f"I could not set up Tab completion for {sh}: {e.strerror or e}. Run `ws-host completion add {sh}` to try again."}
        done.append(sh)
        if r["status"] == "left-alone":
            notes.append(r["plain"])
    return {"name": "completions", "status": "warn" if notes else "ok",
            "plain": " ".join(notes) if notes else f"Tab completes ws-host in {' and '.join(done)}; it starts in a new terminal window."}


def _modern_step(ctx) -> dict:
    """0003-kits FR-019: when the modern tools are here, bash, fish and git use them; it never fails the setup. WS_HOST_MODERN=no opts out."""
    from ..lib import modern
    if not shutil.which("eza") and not (paths.bin_dir() / "eza").exists():
        return {"name": "modern-cli", "status": "ok", "plain": "The modern tools are not installed yet, so your terminal keeps its old commands. `ws-host kit add base` installs them."}
    try:
        r = modern.apply(ctx.offline)
    except WsError as e:
        return {"name": "modern-cli", "status": "warn", "plain": f"{e.plain} Run `ws-host kit add modern-cli` to try again."}
    return {"name": "modern-cli", "status": "ok",
            "plain": ("Made bash, fish and git use the modern tools; it shows in a new terminal window. Icons need a Nerd Font." if r["changed"]
                      else "Your terminal already uses the modern tools.")}


def _prompt_step(ctx, theme: str) -> dict:
    """0006-onboarding FR-022: setup gives bash, and fish when it is there, its prompt; it never fails the setup."""
    done, notes = [], []
    for sh in ("bash", "fish"):
        if sh == "fish" and not (shutil.which("fish") or (paths.bin_dir() / "fish").exists()):
            continue
        try:
            r = shell_cmd.add_prompt(sh, ctx.offline, theme_name=theme, keep_existing=True)
            done.append(sh)
            if r["changed"]:
                notes.append(sh)
        except WsError as e:
            return {"name": "prompt", "status": "warn", "plain": f"{e.plain} Run `ws-host shell add {sh}` to try again."}
    changed = " and ".join(notes)
    return {"name": "prompt", "status": "ok", "plain": (f"Gave {changed} the {theme} prompt; it shows in a new terminal window." if notes
                                                      else "Your terminal already has its prompt.")}


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
