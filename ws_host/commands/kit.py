"""`kit list|show|add` (0003-kits FR-001 to FR-004)."""
from __future__ import annotations

from ..core import kits_state, machine, registry as reg, types
from ..core.registry import Arg, command
from ..core.resource import Action, FAILED, MISSING, OK, Resource, WsError
from ..install import apt, fetch
from ..lib import kitrun

types.KIT.validate = lambda v, ctx: None if v in reg.discover().kits else f"{v!r} is not a kit I have ({', '.join(sorted(reg.discover().kits))})"
types.KIT.complete = lambda ctx: sorted(reg.discover().kits)
KIT_ARG = Arg("KIT", "KIT", positional=True, required=True)


@command("kit", "list", category="read", summary="List the kits and which are installed")
def kit_list(ctx):
    rows = kits_state.kit_report()
    for r in rows:
        r["status"] = "ok" if r["installed"] else "warn"
    n = sum(r["installed"] for r in rows)
    return Resource("kit-list", "kits", {"plain": f"I have {len(rows)} kits; {n} installed on this machine.", "kits": rows},
                    actions=[Action(("kit", "add"), f"Install {r['name']}", {"KIT": r["name"]}) for r in rows if not r["installed"]])


@command("kit", "show", category="read", summary="Show what a kit installs on this machine", args=(KIT_ARG,))
def kit_show(ctx, KIT):
    kit = kitrun.get(KIT)
    d = machine.distro()
    p = kitrun.plan(kit, d)
    return Resource("kit", KIT, {"plain": f"{KIT}: {kit.plain}", "summary": kit.summary, "distribution": d["pretty"], "architecture": fetch.arch(),
                                 "packages": p["packages"], "not_installed": p["to_install"], "unavailable": p["unavailable"],
                                 "downloads": p["downloads"], "links": p["links"],
                                 "checks": [{"name": c.name, "program": c.program, "functional": c.run is not None} for c in kit.checks(d)]},
                    actions=[Action(("kit", "add"), f"Install {KIT}", {"KIT": KIT})])


@command("kit", "add", category="setup", summary="Install a kit (uses sudo for packages, and says so first)", args=(KIT_ARG,))
def kit_add(ctx, KIT):
    kit = kitrun.get(KIT)
    d = machine.distro()
    p = kitrun.plan(kit, d)
    if ctx.dry_run:
        yield Resource("kit-add", KIT, {"plain": f"Nothing was changed. This is what installing {KIT} would do.", "uses_sudo": bool(p["to_install"]) and not apt.is_root(),
                                        "packages_to_install": p["to_install"], "unavailable": p["unavailable"], "downloads": p["downloads"]})
        return
    steps, status = [], OK
    for step, st, plain in kitrun.install(ctx, kit, KIT):
        yield Resource("progress", step, {"plain": plain, "step": step, "status": st})
        steps.append({"name": step, "status": st, "plain": plain})
    results = kits_state.kit_report(functional=True)
    me = [r for r in results if r["name"] == KIT][0]
    bad = [s for s in steps if s["status"] == "fail"]
    failed_checks = [f for f in me.get("functional", []) if f["status"] == "fail"]
    if bad or failed_checks:
        status = FAILED
    elif not me["installed"]:
        status = MISSING if any(s["status"] in ("warn", "missing") for s in steps) else FAILED
    plain = (f"{KIT} is installed and working." if status == OK else
             f"{KIT} is partly installed: {', '.join(me['missing'])} still missing." if me["missing"] else f"{KIT} is installed, but a check failed.")
    yield Resource("kit-add", KIT, {"plain": plain, "steps": steps, "programs": me["programs"], "missing": me["missing"],
                                    "functional": me.get("functional", [])},
                   actions=[] if status == OK else [Action(("kit", "add"), f"Try {KIT} again", {"KIT": KIT})], status=status)
