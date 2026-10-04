"""`doctor`: what ws-host needs and what is present (0001-ws-host FR-012). Changes nothing; holds no secret."""
from __future__ import annotations

import shutil

from ..core import config, kits_state, machine, paths, registry as reg
from ..lib import git, repos, trust
from ..core.resource import Action, FAILED, MISSING, OK, Resource


def _check(name, status, detail, **extra):
    return {"name": name, "status": status, "detail": detail, **extra}


def report() -> dict:
    """The doctor's findings as plain data, for `doctor` and for `context`."""
    checks: list[dict] = []
    d = machine.distro()
    py = machine.python_version()
    checks.append(_check("python", "ok" if tuple(map(int, py.split("."))) >= (3, 11) else "fail", f"python {py}"))
    uv = machine.program_version("uv")
    checks.append(_check("uv", "ok" if uv else "fail", f"uv {uv}" if uv else "uv is not installed; see https://docs.astral.sh/uv/", **({} if uv else {"missing": True})))
    git_ver = git_v = machine.program_version("git")
    checks.append(_check("git", "ok" if git_v else "warn", f"git {git_v}" if git_v else "git is not installed; `ws-host kit add base` installs it"))
    checks.append(_check("distribution", "ok" if machine.debian_family(d) else "warn",
                         f"{d['pretty']} ({d['arch']}){' under WSL' if d['wsl'] else ''}"
                         + ("" if machine.debian_family(d) else "; ws-host is built for Debian and Ubuntu")))
    link = paths.bin_dir() / "ws-host"
    checks.append(_check("launcher", "ok" if link.exists() else "warn",
                         str(link) if link.exists() else f"{link} is not there; run install.sh to link it"))
    if link.exists() and not machine.on_path(paths.bin_dir()):
        checks.append(_check("path", "warn", f"{paths.bin_dir()} is not on your PATH; add this line to your shell's startup file: export PATH=\"$HOME/.local/bin:$PATH\""))
    cfg = config.load()
    for p in cfg.problems:
        checks.append(_check("configuration", "fail", p))
    if not cfg.problems:
        checks.append(_check("configuration", "ok", str(paths.config_file()) if paths.config_file().exists() else "no configuration file yet; none is needed"))
    sp = config.secrets_mode_problem()
    checks.append(_check("secrets file", "fail" if sp else "ok", sp or "not present or readable only by you"))
    if git_ver:
        ff = git.out(None, "config", "--global", "--get", "pull.ff")
        checks.append(_check("git pull setting", "ok" if ff == "only" else "warn",
                             "pull.ff is only" if ff == "only" else
                             "git's Sync button may rewrite your work: pull.ff is not set to only; `ws-host workspace set --pull-ff-only` fixes it",
                             **({} if ff == "only" else {"fix": "workspace set --pull-ff-only"})))
    found, _ = repos.known(cfg)
    for rid in sorted(found, key=str):
        ok, _why = trust.trust_state(rid, cfg)
        if ok and trust.kits_changed_since_trust(rid, cfg):
            checks.append(_check("trust", "warn", f"{rid}'s kits have changed since you trusted it; look at them before relying on them"))
        if ok and any((rid.path(cfg) / ".workspaces-host" / "kits").glob("*.py")):
            checks.append(_check("trust", "warn", f"{rid} ships kits of its own; this version of ws-host does not load them yet"))
        theirs = repos.read_needs(rid.path(cfg)).get("WS_HOST_TRUSTED")
        if theirs:
            checks.append(_check("trust", "warn", f"{rid} names organizations as trusted in its own file; that is ignored, only your own configuration can trust"))
    registry = reg.discover()
    for c in registry.conflicts:
        checks.append(_check("registry", "fail", c))
    if not registry.conflicts:
        checks.append(_check("registry", "ok", f"{len(registry.commands)} commands, {len(registry.kits)} kits, no conflicts"))
    kits = kits_state.kit_report(functional=True)
    for k in kits:
        for f in k.get("functional", []):
            if f["status"] != "ok":
                checks.append(_check(f"{k['name']} kit: {f['name']}", "fail" if f["status"] == "fail" else "warn", f["detail"]))
    return {"distro": d, "python": py, "uv": uv, "git": git_v, "checks": checks, "kits": kits}


def _plain(checks) -> str:
    bad = [c for c in checks if c["status"] == "fail"]
    warn = [c for c in checks if c["status"] == "warn"]
    if bad:
        return f"{len(bad)} thing{'s' if len(bad) != 1 else ''} need{'s' if len(bad) == 1 else ''} fixing before ws-host can be trusted; the list below says what."
    if warn:
        return f"Your machine is ready. There {'is' if len(warn) == 1 else 'are'} {len(warn)} suggestion{'s' if len(warn) != 1 else ''} below."
    return "Your machine is ready. Everything ws-host needs is in place."


@reg.command("doctor", category="check", summary="Check what ws-host needs and what is present")
def doctor(ctx):
    r = report()
    status = OK
    if any(c["status"] == "fail" for c in r["checks"]):
        status = MISSING if any(c.get("missing") for c in r["checks"]) else FAILED
    actions = []
    if any(c["name"] == "git" and c["status"] == "warn" for c in r["checks"]):
        actions.append(Action(("kit", "add"), "Install the base kit", {"kit": "base"}))
    if any(c["name"] == "git pull setting" and c["status"] == "warn" for c in r["checks"]):
        actions.append(Action(("workspace", "set"), "Make git's Sync button safe", {"pull_ff_only": True}))
    return Resource("doctor", "machine", {"plain": _plain(r["checks"]), **r}, actions=actions, status=status)
