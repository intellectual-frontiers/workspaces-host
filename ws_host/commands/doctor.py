"""`doctor`: what ws-host needs and what is present (0001-ws-host FR-012). Changes nothing; holds no secret."""
from __future__ import annotations

import shutil

from ..core import config, kits_state, machine, paths, registry as reg
from ..lib import git, repos, selfupdate, trust
from ..core.resource import Action, FAILED, MISSING, OK, Resource, command_line


INSTALLER = "curl -fsSL https://raw.githubusercontent.com/intellectual-frontiers/workspaces-host/main/install.sh | sh"


def _check(name, status, detail, action=None, cli=None, todo=None, **extra):
    """One finding. A warning or a failure is actionable (0001-ws-host FR-017): `action` is (words, label, fields) of a ws-host command that
    fixes it, `cli` the exact line to type, `todo` what the person does themselves when no command does it."""
    c = {"name": name, "status": status, "detail": detail, **extra}
    if action:
        c["action"] = action
    if cli:
        c["cli"] = cli
    if todo:
        c["todo"] = todo
    return c


def _actionable(checks: list[dict]) -> list[Action]:
    """The actions the findings carry, in order, and for each finding its fix: the action's index, the line to type, or what to do."""
    actions: list[Action] = []
    for c in checks:
        act = c.pop("action", None)
        if c["status"] not in ("warn", "fail"):
            continue
        if act:
            words, label, fields = act
            a = Action(words, label, fields)
            idx = next((i for i, x in enumerate(actions) if (x.words, x.fields) == (a.words, a.fields)), None)
            if idx is None:
                actions.append(a)
                idx = len(actions) - 1
            c["action"] = idx
            c.setdefault("cli", command_line(a, reg.discover()))
        if not c.get("action") and not c.get("cli") and not c.get("todo"):
            c["todo"] = "Run `ws-host context` and paste what it prints to a person or an AI, and ask what to do about this."
    return actions


def report() -> dict:
    """The doctor's findings as plain data, for `doctor`, `context` and `workspace ensure`."""
    return _build()[0]


def _build() -> tuple[dict, list[Action]]:
    checks: list[dict] = []
    d = machine.distro()
    py = machine.python_version()
    checks.append(_check("python", "ok" if tuple(map(int, py.split("."))) >= (3, 11) else "fail", f"python {py}",
                         cli="sudo apt install python3", todo="ws-host needs Python 3.11 or later: Debian 12 or newer and Ubuntu 24.04 or newer have it."))
    uv = machine.program_version("uv")
    checks.append(_check("uv", "ok" if uv else "fail", f"uv {uv}" if uv else "uv is not installed; see https://docs.astral.sh/uv/",
                         cli="curl -LsSf https://astral.sh/uv/install.sh | sh", **({} if uv else {"missing": True})))
    git_ver = git_v = machine.program_version("git")
    checks.append(_check("git", "ok" if git_v else "warn", f"git {git_v}" if git_v else "git is not installed; `ws-host kit add base` installs it",
                         action=(("kit", "add"), "Install the base kit", {"kit": "base"})))
    checks.append(_check("distribution", "ok" if machine.debian_family(d) else "warn",
                         f"{d['pretty']} ({d['arch']}){' under WSL' if d['wsl'] else ''}"
                         + ("" if machine.debian_family(d) else "; ws-host is built for Debian and Ubuntu"),
                         todo="Use Debian or Ubuntu: in WSL on Windows, or in a virtual machine or a container on a Mac."))
    link = paths.bin_dir() / "ws-host"
    checks.append(_check("launcher", "ok" if link.exists() else "warn",
                         str(link) if link.exists() else f"{link} is not there; run install.sh to link it", cli=INSTALLER))
    if link.exists() and not machine.on_path(paths.bin_dir()):
        checks.append(_check("path", "warn", f"{paths.bin_dir()} is not on your PATH, so a new terminal window may not find ws-host",
                              cli="exec bash -l", todo="That starts a new login shell, which finds it. Or close this window and open a new one."))
    note = selfupdate.read_notice()
    checks.append(_check("ws-host version", "warn" if note else "ok", note.split("  ")[0] if note else "up to date, as far as the last look knew",
                         action=(("update",), "Update ws-host", {}) if note else None))
    cfg = config.load()
    for p in cfg.problems:
        checks.append(_check("configuration", "fail", p, cli=f"code {paths.config_file()}", todo="Open your settings file and fix the line named."))
    unknown = sorted(set(cfg.values) - set(config.KEYS))
    if unknown:
        checks.append(_check("configuration", "warn", f"{paths.config_file()} has keys ws-host does not use: {', '.join(unknown)}",
                             cli=f"code {paths.config_file()}", todo="Open your settings file and remove or correct the lines named."))
    if not cfg.problems and not unknown:
        checks.append(_check("configuration", "ok", str(paths.config_file()) if paths.config_file().exists() else "no configuration file yet; none is needed"))
    sp = config.secrets_mode_problem()
    checks.append(_check("secrets file", "fail" if sp else "ok", sp or "not present or readable only by you", cli=f"chmod 600 {paths.secrets_file()}"))
    if git_ver:
        ff = git.out(None, "config", "--global", "--get", "pull.ff")
        checks.append(_check("git pull setting", "ok" if ff == "only" else "warn",
                             "pull.ff is only" if ff == "only" else
                             "git's Sync button may rewrite your work: pull.ff is not set to only; `ws-host workspace set --pull-ff-only` fixes it",
                             action=None if ff == "only" else (("workspace", "set"), "Make git's Sync button safe", {"pull_ff_only": True})))
    found, _ = repos.known(cfg)
    for rid in sorted(found, key=str):
        ok, _why = trust.trust_state(rid, cfg)
        if ok and trust.kits_changed_since_trust(rid, cfg):
            checks.append(_check("trust", "warn", f"{rid}'s kits have changed since you trusted it; look at them before relying on them",
                                  cli=f"git -C {rid.path(cfg)} log -p -3 -- .workspaces-host", todo="Read what changed, and if you do not recognise it, stop trusting the repository."))
        if ok and any((rid.path(cfg) / ".workspaces-host" / "kits").glob("*.py")):
            checks.append(_check("trust", "warn", f"{rid} ships kits of its own; this version of ws-host does not load them yet",
                                  todo="Nothing to do now: ws-host does not run them. Ask the repository's owner if you expected it to."))
        theirs = repos.read_needs(rid.path(cfg)).get("WS_HOST_TRUSTED")
        if theirs:
            checks.append(_check("trust", "warn", f"{rid} names organizations as trusted in its own file; that is ignored, only your own configuration can trust",
                                  todo="Nothing to do: it is ignored. To trust an organization yourself, add it to WS_HOST_TRUSTED in your own settings file."))
    registry = reg.discover()
    for c in registry.conflicts:
        checks.append(_check("registry", "fail", c, todo="This is a fault in ws-host or in a module added to it: fix or remove the module named, then run ws-host doctor again."))
    if not registry.conflicts:
        checks.append(_check("registry", "ok", f"{len(registry.commands)} commands, {len(registry.kits)} kits, no conflicts"))
    kits = kits_state.kit_report(functional=True)
    for k in kits:
        for f in k.get("functional", []):
            if f["status"] != "ok":
                checks.append(_check(f"{k['name']} kit: {f['name']}", "fail" if f["status"] == "fail" else "warn", f["detail"],
                                     action=(("kit", "add"), f"Install {k['name']} again", {"kit": k["name"]})))
    actions = _actionable(checks)
    return {"distro": d, "python": py, "uv": uv, "git": git_v, "checks": checks, "kits": kits}, actions


def _plain(checks) -> str:
    bad = [c for c in checks if c["status"] == "fail"]
    warn = [c for c in checks if c["status"] == "warn"]
    if bad:
        return f"{len(bad)} thing{'s' if len(bad) != 1 else ''} need{'s' if len(bad) == 1 else ''} fixing before ws-host can be trusted; each one says what to do."
    if warn:
        return f"Your machine is ready, with {len(warn)} suggestion{'s' if len(warn) != 1 else ''}."
    return "Your machine is ready. Everything ws-host needs is in place."


@reg.command("doctor", category="check", summary="Check what ws-host needs and what is present")
def doctor(ctx):
    r, actions = _build()
    status = OK
    if any(c["status"] == "fail" for c in r["checks"]):
        status = MISSING if any(c.get("missing") for c in r["checks"]) else FAILED
    return Resource("doctor", "machine", {"plain": _plain(r["checks"]), **r}, actions=actions, status=status)
