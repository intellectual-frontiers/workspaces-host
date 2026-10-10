"""Planning and installing kits (0003-kits). The commands and `workspace ensure` both come here."""
from __future__ import annotations

from ..core import kits_state, machine, progress, registry as reg
from ..core.resource import Action, WsError
from ..core.kit import Floating
from ..install import apt, fetch


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
                  "sha256": x.sha256.get(a), "supported": x.supports(a), "installed": fetch.is_installed(x)} for x in kit.downloads(d)]
    return {"packages": names, "to_install": todo, "unavailable": lacking, "downloads": downloads,
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
                r = fetch.install(dl, offline=ctx.offline)
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
    from ..install import floating
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
                    r = fetch.install(dl, offline=ctx.offline)
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
    from ..install import floating
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
