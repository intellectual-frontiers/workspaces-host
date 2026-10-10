"""`provider list|show|add|remove|run`, `toolchain list|show|generate|ensure|remove`, `system ensure` and the `providers` section of `check` (0008-providers)."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ..core import types
from ..core.registry import Arg, command, section
from ..core.resource import Action, FAILED, MISSING, OK, Resource, WsError
from ..install import apt
from ..lib import provider as prov, toolchain as tc

PROVIDER_ARG = Arg("provider", "PROVIDER", positional=True, help="an enabled provider's name")
PROVIDER_REQ = Arg("provider", "PROVIDER", positional=True, required=True, help="an enabled provider's name")
types.PROVIDER = types.register(types.Type("PROVIDER", ("agora", "example"), lambda v, ctx: None if prov.NAME_RE.fullmatch(v) else f"{v!r} is not a provider name",
                                           lambda ctx: [p.name for p in prov.enabled()]))


def _get(name: str | None) -> prov.Provider:
    if not name:
        have = [p.name for p in prov.enabled()]
        raise WsError("usage", "a provider is required", "Say which provider: " + (", ".join(have) if have else "none is enabled yet; add one with ws-host provider add PATH") + ".", exit_code=2)
    p = prov.get(name)
    if p is None:
        have = [x.name for x in prov.enabled()]
        raise WsError("unknown-provider", name, f"No enabled provider is called '{name}'. " + ("Enabled: " + ", ".join(have) + "." if have else "None is enabled yet.")
                      + " Enable the repository that holds it with: ws-host provider add PATH", [Action(("provider", "list"), "List providers")],
                      status="missing", exit_code=3)
    return p


def _wrap(e: tc.ToolchainError) -> WsError:
    return WsError(f"toolchain-{e.code}", str(e), e.plain, exit_code=e.exit_code, **({"status": "missing"} if e.exit_code == 3 else {}))


def _row(p: prov.Provider) -> dict:
    st = tc.state(p) if not p.problems else {}
    n_ready = sum(v["state"] == "ready" for v in st.values())
    status = "error" if p.problems else ("ok" if n_ready == len(st) else "warn")
    return {"name": p.name, "summary": p.summary, "launcher": p.launcher, "root": str(p.root), "entries": len(p.entries), "ready": n_ready,
            "problems": [str(x) for x in p.problems], "status": status, "via": prov.how_enabled(p.name),
            "plain": p.summary + (f" ({n_ready} of {len(st)} programs installed)" if st else "")}


@command("provider", "list", category="read", summary="List the providers you have enabled")
def provider_list(ctx):
    rows = [_row(p) for p in prov.enabled()]
    plain = (f"{len(rows)} provider{'s are' if len(rows) != 1 else ' is'} enabled: " + ", ".join(r["name"] for r in rows) + ".") if rows else \
        "No provider is enabled yet. Enable one with: ws-host provider add PATH"
    return Resource("provider-list", "providers", {"plain": plain, "providers": rows})


@command("provider", "show", category="read", summary="Show one provider, its launcher and the programs it pins", args=(PROVIDER_REQ,))
def provider_show(ctx, provider):
    p = _get(provider)
    st = tc.state(p) if not p.problems else {}
    row = _row(p)
    acts = [Action(("toolchain", "ensure"), f"Install what {p.name} pins", {"provider": p.name, "all": True})] if any(v["state"] == "missing" for v in st.values()) else []
    return Resource("provider", p.name, {**row, "plain": f"{p.name}: {row['plain']}", "entries": list(st.values()), "protocol": p.protocol,
                                         "environment": tc.delta_of(p) if not p.problems else {}, "store": str(tc.mise.data_dir() / "installs")}, actions=acts)


@command("provider", "add", category="decision", summary="Enable a repository as a provider, so ws-host installs and runs what it declares",
         args=(Arg("path", "PATH", positional=True, required=True, help="the repository's folder"),))
def provider_add(ctx, path):
    root = Path(path).expanduser().resolve()
    p = prov.load(root)
    if p is None:
        raise WsError("not-a-provider", str(root), f"{root} has no {prov.FOLDER}/provider.toml, so it is not a provider.", exit_code=1)
    if p.problems:
        raise WsError("invalid-provider", "; ".join(map(str, p.problems)), f"I did not enable {p.name or root.name}, because " + "; ".join(map(str, p.problems)) + ".", exit_code=1)
    clash = prov.conflicts([x for x in prov.enabled() if x.name != p.name] + [p])
    if clash:
        raise WsError("provider-conflict", "; ".join(clash), "I did not enable " + p.name + ", because " + "; ".join(clash) + ".", exit_code=1)
    link = prov.providers_dir() / p.name
    already = prov.implicit().get(p.name)
    if already is not None and already[0].root.resolve() == root and not link.exists():
        return Resource("provider", p.name, {"plain": f"{p.name} is already in use and needs nothing from you: {already[1]}.", "name": p.name, "root": str(root)}, status=OK)
    if ctx.dry_run:
        return Resource("provider", p.name, {"plain": f"Nothing was changed. I would enable {p.name} from {root}.", "name": p.name, "root": str(root)})
    ctx.confirm(f"This lets {p.name} ({root}) have programs installed and run for it on this machine: {', '.join(sorted(p.entries)) or 'none yet'}.")
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(p.folder)
    return Resource("provider", p.name, {"plain": f"{p.name} is enabled.", "name": p.name, "root": str(root)}, status=OK,
                    actions=[Action(("toolchain", "ensure"), f"Install what {p.name} pins", {"provider": p.name, "all": True})] if p.entries else [])


@command("provider", "remove", category="decision", summary="Stop using a provider (its programs stay until you prune them)", args=(Arg("provider", "PROVIDER", positional=True, required=True),))
def provider_remove(ctx, provider):
    p = _get(provider)
    if not (prov.providers_dir() / p.name).is_symlink():
        raise WsError("not-enabled-by-hand", p.name, f"{p.name} is in use because {prov.how_enabled(p.name)}, not because you enabled it, so there is nothing to remove. "
                      "To stop using a repository's provider, stop trusting it: put WS_HOST_TRUSTED in ~/.config/workspaces-host/ws-host.env without its organization.", exit_code=1)
    if ctx.dry_run:
        return Resource("provider", p.name, {"plain": f"Nothing was changed. I would stop using {p.name}.", "name": p.name})
    ctx.confirm(f"This stops ws-host installing or running anything for {p.name}.")
    (prov.providers_dir() / p.name).unlink()
    return Resource("provider", p.name, {"plain": f"{p.name} is no longer enabled. Its installed programs stay until you run: ws-host toolchain remove --unused", "name": p.name},
                    status=OK, actions=[Action(("toolchain", "remove"), "Remove programs nothing needs", {"unused": True})])


@command("provider", "run", category="build", summary="Run a command with one provider's programs first on PATH",
         args=(PROVIDER_REQ, Arg("argv", positional=True, multiple=True, help="the command, after --"),
               Arg("ensure", "STRING", multiple=True, help="install this program (and what it needs) from the lock first, if it is missing")), surfaces=("cli",))
def provider_run(ctx, provider, argv, ensure):
    p = _get(provider)
    if not argv:
        raise WsError("usage", "a command is required", "Say what to run after --, for example: ws-host provider run " + p.name + " -- chromium --version", exit_code=2)
    if ctx.dry_run:
        return Resource("provider-run", p.name, {"plain": "Nothing was run. I would run: " + " ".join(argv), "argv": list(argv)})
    try:
        missing = [n for n in tc.closure(p, ensure or []) if tc.install_path(p, p.entries[n]) is None]
        if missing:
            tc.ensure(p, missing, offline=ctx.offline)
        env = tc.environment(p)
    except tc.ToolchainError as e:
        raise _wrap(e)
    try:
        proc = subprocess.Popen(list(argv), env=env)
    except OSError as e:
        raise WsError("run-failed", f"{argv[0]}: {e.strerror}", f"I could not start {argv[0]} for {p.name}: {e.strerror}. Is it installed? Try: ws-host toolchain list", exit_code=127 if isinstance(e, FileNotFoundError) else 126)
    status = _wait(proc)
    if ctx.mode == "text":      # the program's own output is the output; only its status is ours
        ctx.exit_code = status
        return None
    return Resource("provider-run", p.name, {"plain": f"{argv[0]} finished with status {status}.", "argv": list(argv), "exit": status},
                    status=OK if status == 0 else FAILED)


def _wait(proc: subprocess.Popen) -> int:
    """The command's status once it ends (0008 FR-013). A Ctrl+C at the terminal reaches the command too, and the command answers it
    (a server stops and says so); this process only waits, and says nothing of its own. A signal that ended the command is its
    status as a shell gives it, 128 plus the signal's number."""
    while True:
        try:
            code = proc.wait()
            break
        except KeyboardInterrupt:
            continue
    return code if code >= 0 else 128 - code


# ---- toolchain ---------------------------------------------------------------------------------------------------------

def _all_rows() -> list[dict]:
    rows = []
    for p in prov.enabled():
        for v in (tc.state(p) if not p.problems else {}).values():
            rows.append({"provider": p.name, "name": v["name"], "version": v["version"], "state": v["state"], "status": "ok" if v["state"] == "ready" else "warn",
                         "plain": f"{p.name}: {v['summary']} ({v['version']}, {v['state']})"})
    return rows


@command("toolchain", "list", category="read", summary="List the programs enabled providers pin and whether each is installed")
def toolchain_list(ctx):
    rows = _all_rows()
    n = sum(r["state"] == "ready" for r in rows)
    return Resource("toolchain-list", "toolchain", {"plain": f"{n} of {len(rows)} pinned programs are installed." if rows else "No enabled provider pins any program.", "entries": rows},
                    actions=[Action(("toolchain", "ensure"), "Install what is missing", {"all": True})] if n < len(rows) else [])


@command("toolchain", "show", category="read", summary="Show one pinned program: version, where it is, what it provides and sets",
         args=(Arg("name", "STRING", positional=True, required=True), Arg("provider", "PROVIDER", help="the provider that pins it")))
def toolchain_show(ctx, name, provider):
    p = _get(provider or _only_provider(name))
    st = tc.state(p)
    if name not in st:
        raise WsError("unknown-entry", name, f"{p.name} pins no program called '{name}'. It pins: {', '.join(sorted(st)) or 'nothing'}.", exit_code=1)
    v = st[name]
    return Resource("toolchain", name, {"plain": f"{name} {v['version']} for {p.name} is {v['state']}.", "provider": p.name, **v, "environment": p.entries[name].env},
                    actions=[Action(("toolchain", "ensure"), f"Install {name}", {"name": name, "provider": p.name})] if v["state"] == "missing" else [])


def _only_provider(name: str) -> str | None:
    have = [p.name for p in prov.enabled() if name in p.entries]
    if len(have) > 1:
        raise WsError("ambiguous", name, f"{', '.join(have)} all pin '{name}'. Say which with --provider.", exit_code=2)
    return have[0] if have else None


@command("toolchain", "generate", category="generate", summary="Write a provider's mise configuration and lock from its entries",
         args=(PROVIDER_ARG, Arg("root", "PATH", help="a provider's folder not yet enabled (used by its own build)")))
def toolchain_generate(ctx, provider, root):
    p = prov.load(Path(root).expanduser().resolve()) if root else _get(provider)
    if p is None:
        raise WsError("not-a-provider", str(root), f"{root} has no {prov.FOLDER}/provider.toml.", exit_code=1)
    if p.problems:
        raise WsError("invalid-provider", "; ".join(map(str, p.problems)), f"{p.name}'s declarations have problems: " + "; ".join(map(str, p.problems)), exit_code=1)
    if ctx.dry_run:
        return Resource("toolchain-generate", p.name, {"plain": "Nothing was written. These files are out of date: " + (", ".join(prov.stale(p)) or "none"), "stale": prov.stale(p)})
    try:
        changed = tc.lock(p, offline=ctx.offline)
    except tc.ToolchainError as e:
        raise _wrap(e)
    return Resource("toolchain-generate", p.name, {"plain": (f"I wrote {len(changed)} file{'s' if len(changed) != 1 else ''}; commit them." if changed else "Nothing changed; the files are current."),
                                                   "changed": changed}, status=OK)


@command("toolchain", "ensure", category="setup", summary="Install pinned programs from the lock, only from the lock",
         args=(Arg("name", "STRING", positional=True, help="one program (and what it needs); with --all, every program"), Arg("provider", "PROVIDER"), Arg("all", flag=True, help="every program of the provider, or of every provider")))
def toolchain_ensure(ctx, name, provider, all):
    if not name and not all:
        raise WsError("usage", "say a program or --all", "Say which program to install, or --all for everything the provider pins.", exit_code=2)
    targets = [_get(provider)] if provider else ([p for p in prov.enabled() if name in p.entries] if name else prov.enabled())
    if not targets:
        raise WsError("unknown-entry", name or "", f"No enabled provider pins '{name}'.", exit_code=1)
    if ctx.dry_run:
        return Resource("toolchain-ensure", "dry-run", {"plain": "Nothing was installed. I would install: " + ", ".join(f"{p.name}/{n}" for p in targets for n in (tc.closure(p, [name]) if name else sorted(p.entries))),})
    done = []
    for p in targets:
        try:
            done += [f"{p.name}/{n}" for n in tc.ensure(p, [name] if name else None, offline=ctx.offline)]
        except tc.ToolchainError as e:
            raise _wrap(e)
    return Resource("toolchain-ensure", name or "all", {"plain": ("Installed and ready: " + ", ".join(done) + ".") if done else "There was nothing to install.", "installed": done}, status=OK)


@command("toolchain", "remove", category="setup", summary="Remove stored programs no enabled provider pins", args=(Arg("unused", flag=True, help="required: the programs nothing pins"),))
def toolchain_remove(ctx, unused):
    if not unused:
        raise WsError("usage", "say --unused", "I only remove programs nothing pins. Add --unused.", exit_code=2)
    try:
        rows = tc.prune(prov.enabled(), ctx.dry_run, ctx.offline)
    except tc.ToolchainError as e:
        raise _wrap(e)
    total = sum(r["bytes"] for r in rows)
    verb = "would remove" if ctx.dry_run else "removed"
    return Resource("toolchain-remove", "unused", {"plain": (f"Nothing was changed. I {verb} {len(rows)} program{'s' if len(rows) != 1 else ''}, {total:,} bytes." if ctx.dry_run else
                                                             f"I {verb} {len(rows)} program{'s' if len(rows) != 1 else ''}, {total:,} bytes.") if rows else "Nothing is unused.", "removed": rows}, status=OK)


# ---- system ------------------------------------------------------------------------------------------------------------

@command("system", "ensure", category="setup", summary="Install the shared libraries enabled providers' programs need (uses sudo, and says so first)")
def system_ensure(ctx):
    specs = sorted({s for p in prov.enabled() for e in p.entries.values() for s in e.system})
    if not specs:
        return Resource("system-ensure", "system", {"plain": "No enabled provider needs shared libraries.", "installed": [], "unavailable": []}, status=OK)
    names, missing = apt.resolve(specs)
    todo = apt.to_install(names)
    if ctx.dry_run:
        return Resource("system-ensure", "system", {"plain": "Nothing was installed. I would install: " + (", ".join(todo) or "nothing") + ("; this distribution has none of: " + ", ".join(missing) if missing else ""),
                                                   "uses_sudo": bool(todo) and not apt.is_root(), "installed": todo, "unavailable": missing})
    if todo:
        try:
            apt.install(todo)
        except apt.AptError as e:
            raise WsError(f"system-{e.code}", str(e), f"I could not install {', '.join(todo)}: {e}.", exit_code=1)
    return Resource("system-ensure", "system", {"plain": ("Installed " + ", ".join(todo) + "." if todo else "Everything is already installed.") + (" This distribution has none of: " + ", ".join(missing) + "." if missing else ""),
                                               "installed": todo, "unavailable": missing}, status=MISSING if missing else OK)


# ---- check -------------------------------------------------------------------------------------------------------------

@section("providers", summary="every enabled provider's declarations are valid, their generated mise files are current and no two disagree about a program")
def providers_section(ctx):
    """0008-providers FR-005, FR-006, FR-009."""
    found = []
    have = prov.enabled()
    for p in have:
        found += [{"level": "error", "where": f"{p.name}: {x.where}", "message": x.message, "next": "fix the file"} for x in p.problems]
        if not p.problems:
            found += [{"level": "error", "where": f"{p.name}: {f}", "message": "is not what the entries say now", "next": f"run `ws-host toolchain generate {p.name}` and commit it"}
                      for f in prov.stale(p)]
    found += [{"level": "error", "where": "providers", "message": c, "next": "rename or re-version one entry"} for c in prov.conflicts(have)]
    return found
