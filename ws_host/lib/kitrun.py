"""Planning and installing kits (0003-kits). The commands and `workspace ensure` both come here."""
from __future__ import annotations

from archon import apt, fetch, machine, paths, progress
from ..core import kits_state, registry as reg
from ..core.resource import Action, WsError
from ..core.kit import Floating
from ..install import floating


def _installed(x) -> bool:
    return floating.is_installed(x) if isinstance(x, Floating) else fetch.is_installed(x)


def _install(x, offline: bool) -> dict:
    return floating.install(x, offline) if isinstance(x, Floating) else fetch.install(x, offline=offline)


def get(name: str):
    kits = reg.discover().kits
    if name not in kits:
        raise WsError("unknown-kit", f"no kit '{name}'", f"I do not know a kit called '{name}'. The kits are: {', '.join(sorted(kits))}.",
                      [Action(("kit", "list"), "See the kits")], exit_code=2)
    return kits[name]()


def plan(kit, distro: dict | None = None, resolve: bool = True) -> dict:
    """What installing the kit would do on this machine."""
    d = distro or machine.distro()
    specs = kit.apt(d)
    names, lacking = (apt.resolve(specs) if resolve and apt.available() else (specs, []))
    todo = apt.to_install(names) if resolve and apt.available() else names
    a = fetch.arch()
    downloads = [{"name": x.name, "version": x.version, "url": x.url_for(a) if x.supports(a) else None,
                  "sha256": x.sha256.get(a), "supported": x.supports(a), "installed": _installed(x)} for x in kit.downloads(d)]
    return {"packages": names, "to_install": todo, "unavailable": lacking, "downloads": downloads,
            "requirements": {k: list(v) for k, v in kit.requirements(d).items()},
            "links": {k: list(v) for k, v in kit.links(d).items()}}


def install(ctx, kit, name: str):
    """Install a kit, yielding (step, status, plain) tuples as it goes. Never raises for a step that can be reported."""
    d = machine.distro()
    p = plan(kit, d)
    if p["unavailable"]:
        yield ("packages", "warn", "This distribution has no package for: " + ", ".join(p["unavailable"]) + ". The checks below say whether that matters.")
    if p["to_install"]:
        prefix = apt.sudo_prefix()
        if prefix is None:
            yield ("packages", "warn", f"I cannot install {len(p['to_install'])} packages because there is no sudo on this machine. Ask an administrator to run: apt-get install {' '.join(p['to_install'])}")
        else:
            if prefix:
                yield ("packages", "info", "This needs administrator rights, so I will use sudo to install: " + ", ".join(p["to_install"]) + ".")
            try:
                for kind, line in apt.install_events(p["to_install"]):
                    yield ("packages", "log", line)         # everything apt says, as it says it, so that a long install is never silent
                yield ("packages", "ok", f"Installed {len(p['to_install'])} packages.")
            except apt.AptError as e:
                if e.code == "needs-password":
                    yield ("packages", "warn", f"Installing packages needs your password, and there is no terminal to ask it in. In a terminal, run: ws-host kit add {name}")
                elif e.code == "sudo-denied":
                    yield ("packages", "fail", "sudo did not accept the password, so nothing was installed. Run the command again and type your password when asked.")
                else:
                    yield ("packages", "fail", f"Installing packages failed: {e.message}")
    else:
        yield ("packages", "ok", "All the packages are already installed." if p["packages"] else "This kit needs no packages.")
    for dl in kit.downloads(d):
        try:
            with progress.working(f"📥 Downloading {dl.name}" if not isinstance(dl, Floating) else f"🔎 {dl.name}: looking for the newest release"):
                r = _install(dl, ctx.offline)
            if r["outcome"] == "present":
                yield (f"download {dl.name}", "ok", r.get("note") or (f"{dl.name} {r['version']} is the newest I know of." if isinstance(dl, Floating) else f"{dl.name} {dl.version} was already installed."))
            elif r["outcome"] == "updated":
                yield (f"download {dl.name}", "ok", f"Updated {dl.name} from {r['previous']} to {r['version']}.")
            else:
                yield (f"download {dl.name}", "ok", f"Installed {dl.name} {r.get('version', dl.version)}.")
        except fetch.FetchError as e:
            if e.code == "unsupported-arch":
                yield (f"download {dl.name}", "ok", f"{e.message}; I skipped it, and the distribution's own {dl.name} is used if it has one.")
            else:
                yield (f"download {dl.name}", "missing" if e.code in ("offline",) else "fail", e.message)
    for link, programs in kit.links(d).items():
        for prog in programs:
            if fetch.link_program(link, prog):
                break
    for step in _requirements(ctx, kit, d):
        yield step
    try:
        for st, plain in kit.configure(ctx):
            yield ("configure", st, plain)
    except WsError as e:
        yield ("configure", "fail", e.plain)
    if kit.name == "base" and not ctx.dry_run:
        from ..core import config
        from ..lib import modern
        if config.load().modern() and not modern.configured() and kit.downloads(d):
            yield ("modern-cli", "info", "Tip: run `ws-host kit add modern-cli` to make ls, cat, top, cd and git diff use these modern tools (eza, bat, btop, zoxide, delta), in bash and fish.")


SHIM = "# ws-host kit shim"


def _requirements(ctx, kit, distro: dict):
    """The requirements a kit names, made available by `archon` (0011-archon FR-024) and linked into the person's bin directory as scripts that set the
    requirement's own environment; a program that is not ws-host's own link is never replaced."""
    from pathlib import Path

    from archon import profile, provider, requirements as req

    wanted = kit.requirements(distro)
    if not wanted:
        return
    root = Path(__file__).resolve().parents[2]
    try:
        p = provider.load(root)
        with progress.working("📥 Making " + ", ".join(wanted) + " available"):
            got = {r.name: r for r in req.ensure(p, list(wanted), offline=ctx.offline, profile=profile.current(), say=lambda line: None)}
    except req.Unavailable as e:
        yield (f"requirement {', '.join(wanted)}", "missing" if ctx.offline else "fail", str(e))
        return
    bindir = paths.bin_dir()
    for name, programs in wanted.items():
        r = got[name]
        yield (f"requirement {name}", "ok", f"{name} {r.version} is available ({r.source}).")
        if r.source != "pinned":
            continue                                    # a program on PATH or the package manager's needs no script
        env = {k: v for k, v in r.env.items() if k != "PATH"}
        folder = Path(r.programs[next(iter(r.programs))]).parent
        bindir.mkdir(parents=True, exist_ok=True)
        for prog in programs:
            target, link = folder / prog, bindir / prog
            if not target.exists():
                continue
            if link.exists() or link.is_symlink():
                if SHIM not in (link.read_text(errors="ignore") if link.is_file() and not link.is_symlink() else ""):
                    continue
            exports = "".join(f"{k}='{v}'; export {k}\n" for k, v in sorted(env.items()))
            link.write_text(f"#!/bin/sh\n{SHIM} ({name}, 0003-kits FR-010)\n{exports}exec '{target}' \"$@\"\n")
            link.chmod(0o755)
        yield (f"requirement {name}", "ok", "Linked " + ", ".join(programs) + f" into {bindir}.")


def ensure(ctx, declared: dict[str, list[str]]) -> dict:
    """`workspace ensure`'s kit step (0003 FR-012): install what repositories declare, report what cannot be done."""
    if not declared:
        return {"status": "ok", "plain": "No repository asked for a kit."}
    kits = reg.discover().kits
    notes, bad, actions = [], False, []
    for name in sorted(declared):
        if name not in kits:
            notes.append(f"'{name}' is not a kit I have (asked for by {', '.join(declared[name])}); I have: {', '.join(sorted(kits))}")
            bad = True
            continue
        kit = kits[name]()
        if all(kits_state.program_present(c.program) for c in kit.checks(machine.distro()) if c.program):
            notes.append(f"{name} is already installed")
            continue
        results = []
        for r in install(ctx, kit, name):
            if r[1] == "log":
                apt._say(r[2])                          # a person at a terminal sees it as it happens; the Console's Output panel logs it too
            else:
                results.append(r)
        worst = [r for r in results if r[1] in ("fail",)]
        todo = [r for r in results if r[1] in ("warn", "missing")]
        if worst:
            bad = True
            notes.append(f"{name}: " + "; ".join(r[2] for r in worst))
        elif todo:
            notes.append(f"{name}: " + "; ".join(r[2] for r in todo))
            actions.append(Action(("kit", "add"), f"Finish installing {name}", {"kit": name}))
        else:
            notes.append(f"{name} is installed")
    return {"status": "fail" if bad else "ok", "plain": "; ".join(notes) + ".", "actions": actions}


def refresh_installed(ctx, only: str | None = None) -> dict:
    """`kit sync` and `ws-host update --tools` (0003-kits FR-017): every floating tool that is installed, whichever kit put it there (or only one kit's), is looked at for a newer release and
    brought up to date; one that cannot be looked at is left alone. An ordinary update never does this, so that it stays quick. Returns what was done, in words."""
    if ctx.offline:
        return {"status": "ok", "plain": "You are offline, so I did not look for newer releases of the tools that float.", "tools": 0, "updated": [], "failed": []}
    updated, kept, failed = [], [], []
    seen: set[str] = set()
    kits = reg.discover().kits
    for kit_name, kit_class in sorted(kits.items()):
        if only and kit_name != only:
            continue
        for dl in kit_class().downloads(machine.distro()):
            if not isinstance(dl, Floating) or dl.name in seen or not floating.installed_version(dl):
                continue
            seen.add(dl.name)
            try:
                with floating.looking_fresh():
                    r = _install(dl, ctx.offline)
            except fetch.FetchError as e:
                failed.append(f"{dl.name}: {e.message}")
                continue
            if r["outcome"] == "updated":
                updated.append(f"{dl.name} {r['previous']} to {r['version']}")
            else:
                kept.append(dl.name)
    if not seen:
        return {"status": "ok", "plain": "No tool that floats with its newest release is installed.", "tools": 0}
    parts = ([f"updated {', '.join(updated)}"] if updated else []) + ([f"{len(kept)} already the newest"] if kept else []) + ([f"could not look at {'; '.join(failed)}"] if failed else [])
    return {"status": "ok" if not failed else "warn", "plain": "Tools that float: " + "; ".join(parts) + ".", "tools": len(seen), "updated": updated, "failed": failed}


def verify(only: str | None = None) -> list[dict]:
    """Ask each floating tool's publisher what its newest release is and which file would be taken and how it would be checked, installing nothing (0003-kits FR-018)."""
    arch = fetch.arch()
    rows, seen = [], set()
    for kit_name, kit_class in sorted(reg.discover().kits.items()):
        if only and kit_name != only:
            continue
        for dl in kit_class().downloads(machine.distro()):
            if not isinstance(dl, Floating) or dl.name in seen:
                continue
            seen.add(dl.name)
            try:
                r = dl.resolve(arch)
                how = "its publisher's checksum" if r.sha256 else "its publisher's signature" if r.signature_url else "the registry's integrity record"
                rows.append({"name": dl.name, "status": "ok", "kit": kit_name, "version": r.version, "file": r.asset or r.url.rsplit("/", 1)[-1] or dl.package,
                             "plain": f"the newest is {r.version}" + (f", the file {r.asset}" if r.asset else "") + f", checked by {how}"})
            except fetch.FetchError as e:
                rows.append({"name": dl.name, "status": "fail", "kit": kit_name, "plain": e.message})
    return rows
