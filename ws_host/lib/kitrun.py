"""Planning and installing kits (0003-kits). The commands and `workspace advance` both come here."""
from __future__ import annotations

from ..core import kits_state, machine, registry as reg
from ..core.resource import Action, WsError
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
                apt.install(p["to_install"])
                yield ("packages", "ok", f"Installed {len(p['to_install'])} packages.")
            except apt.AptError as e:
                if e.code == "needs-password":
                    yield ("packages", "warn", f"Installing packages needs your password, and there is no terminal to ask it in. In a terminal, run: ws-host kit add {name}")
                else:
                    yield ("packages", "fail", f"Installing packages failed: {e.message}")
    else:
        yield ("packages", "ok", "All the packages are already installed." if p["packages"] else "This kit needs no packages.")
    for dl in kit.downloads(d):
        try:
            r = fetch.install(dl, offline=ctx.offline)
            yield (f"download {dl.name}", "ok", f"{dl.name} {dl.version} was already installed." if r["outcome"] == "present" else f"Installed {dl.name} {dl.version}.")
        except fetch.FetchError as e:
            yield (f"download {dl.name}", "missing" if e.code in ("offline",) else "fail", e.message)
    for link, programs in kit.links(d).items():
        for prog in programs:
            if fetch.link_program(link, prog):
                break


def ensure(ctx, declared: dict[str, list[str]]) -> dict:
    """`workspace advance`'s kit step (0003 FR-012): install what repositories declare, report what cannot be done."""
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
        results = list(install(ctx, kit, name))
        worst = [r for r in results if r[1] in ("fail",)]
        todo = [r for r in results if r[1] in ("warn", "missing")]
        if worst:
            bad = True
            notes.append(f"{name}: " + "; ".join(r[2] for r in worst))
        elif todo:
            notes.append(f"{name}: " + "; ".join(r[2] for r in todo))
            actions.append(Action(("kit", "add"), f"Finish installing {name}", {"KIT": name}))
        else:
            notes.append(f"{name} is installed")
    return {"status": "fail" if bad else "ok", "plain": "; ".join(notes) + ".", "actions": actions}
