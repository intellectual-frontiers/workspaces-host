"""Making a command's requirements available (0011-archon FR-008 to FR-016). Standard library only.

A requirement is an entry of `.workspaces-host/toolchain.d/`. Each comes from the first source that yields a program meeting its `minimum`: `path` (a program already on
PATH), `system` (the computer's package manager) and `pinned` (the entry's own verified download, or the `mise` tool or npm package it names, from the lock)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from . import apt, profile as _profile, progress, provider as prov, system, toolchain as tc, versions

PATH, SYSTEM, PINNED = "path", "system", "pinned"
DECLARATION_ERRORS = ("invalid", "stale", "no-lock", "unknown-entry")


@dataclass
class Result:
    name: str
    source: str                                  # path | system | pinned
    version: str
    programs: dict[str, str] = field(default_factory=dict)   # program -> the path to run
    env: dict[str, str] = field(default_factory=dict)        # what it adds to the environment: PATH and the entry's `env`

    def to_dict(self) -> dict:
        return {"name": self.name, "source": self.source, "version": self.version, "programs": self.programs, "environment": self.env}


class Unavailable(Exception):
    """No source yields the requirement (exit status 3, FR-015)."""
    exit_code = 3

    def __init__(self, name: str, minimum: str, reasons: list[tuple[str, str]]):
        self.name, self.minimum, self.reasons = name, minimum, reasons
        needed = f" at {minimum} or newer" if minimum else ""
        super().__init__(f"{name}{needed} is needed and could not be obtained: " + "; ".join(f"{src}: {why}" for src, why in reasons))


def _probe(e: prov.Entry) -> tuple[str | None, str | None]:
    return versions.probe(e.probe_program, e.probe_args)


def _from_path(e: prov.Entry, reasons: list[tuple[str, str]]) -> Result | None:
    exe, found = _probe(e)
    if exe is None:
        reasons.append((PATH, f"{e.probe_program} is not on PATH"))
    elif found is None:
        reasons.append((PATH, f"{exe} prints no version"))
    elif not versions.meets(found, e.minimum):
        reasons.append((PATH, f"{exe} is {found}; {e.minimum} is needed"))
    else:
        return Result(e.name, PATH, found, {e.probe_program: exe})
    return None


def _ask(question: str) -> bool:
    """An attended person is asked before an install that needs administrator rights; the default is yes."""
    import sys
    try:
        sys.stderr.write(question + " [Y/n] ")
        sys.stderr.flush()
        return sys.stdin.readline().strip().lower() in ("", "y", "yes")
    except (OSError, ValueError):
        return False


def _from_system(e: prov.Entry, reasons: list[tuple[str, str]], offline: bool, prof: _profile.Profile, say, ask) -> Result | None:
    manager = system.detect()
    if manager is None:
        reasons.append((SYSTEM, "this computer has no package manager I know (apt, dnf, apk or brew)"))
        return None
    specs = e.packages.get(manager)
    if not specs:
        reasons.append((SYSTEM, f"the entry names no {manager} package"))
        return None
    if offline:
        reasons.append((SYSTEM, "offline, so the package manager cannot be asked or run"))
        return None
    pkg, offered = None, None
    for spec in specs:
        pkg, offered = system.candidate(manager, spec)
        if pkg:
            break
    if not pkg:
        reasons.append((SYSTEM, f"{manager} has none of {', '.join(specs)}"))
        return None
    if not versions.meets(offered, e.minimum):
        reasons.append((SYSTEM, f"{manager} offers {pkg} {offered}; {e.minimum} is needed"))
        return None
    prefix, why = system.administrator(manager)
    if prefix is None:
        reasons.append((SYSTEM, f"{pkg} {offered} is offered, but {why}"))
        return None
    if prof.attended and prefix:
        say(f"\U0001F510 {e.name} needs {pkg} {offered} from {manager}. Administrator rights are needed, and sudo will ask for your password.")
        if not ask(f"Install {pkg} with {manager}?"):
            reasons.append((SYSTEM, "you chose not to install it"))
            return None
    try:
        with progress.step(f"\U0001F4E6 Installing {pkg} {offered} for {e.name}", announce=True):
            for kind, line in system.install_events(manager, pkg):
                if kind in ("step", "done"):
                    say(line)
    except system.SystemInstallError as err:
        reasons.append((SYSTEM, f"installing {pkg} failed: {err.message}"))
        return None
    exe, found = _probe(e)
    if exe is None or found is None or not versions.meets(found, e.minimum):
        reasons.append((SYSTEM, f"{pkg} was installed, but {e.probe_program} then shows {found or 'no version'}; {e.minimum} is needed"))
        return None
    return Result(e.name, SYSTEM, found, {e.probe_program: exe})


def _from_pinned(p: prov.Provider, e: prov.Entry, reasons: list[tuple[str, str]], offline: bool) -> Result | None:
    path = tc.install_path(p, e)
    if path is None:
        try:
            tc.ensure(p, [e.name], offline)
        except tc.ToolchainError as err:
            if err.code in DECLARATION_ERRORS:
                raise
            reasons.append((PINNED, err.plain))
            return None
        path = tc.install_path(p, e)
    if path is None:
        reasons.append((PINNED, "it was installed but cannot be found in the store"))
        return None
    return Result(e.name, PINNED, e.version, {k: str(path / v) for k, v in e.provides.items()}, tc.entry_delta(e, path))


def _libraries(e: prov.Entry, offline: bool, prof: _profile.Profile, say, ask) -> None:
    """The shared libraries a pinned program links against (`system`, FR-022): the ones the computer lacks are installed through its package manager, or the entry fails."""
    if not e.system or not apt.available():
        return
    names, _unavailable = apt.resolve(e.system)
    todo = apt.to_install(names)
    if not todo:
        return
    wanted = ", ".join(todo)
    if offline:
        raise Unavailable(e.name, e.minimum, [("system libraries", f"offline, and {wanted} are missing")])
    prefix, why = system.administrator("apt")
    if prefix is None:
        raise Unavailable(e.name, e.minimum, [("system libraries", f"{wanted} are missing, and {why}")])
    if prof.attended and prefix:
        say(f"\U0001F510 {e.name} needs {wanted} from apt. Administrator rights are needed, and sudo will ask for your password.")
        if not ask(f"Install {wanted} with apt?"):
            raise Unavailable(e.name, e.minimum, [("system libraries", f"{wanted} are missing, and you chose not to install them")])
    try:
        with progress.step(f"\U0001F4E6 Installing {wanted} for {e.name}", announce=True):
            for kind, line in apt.install_events(todo):
                if kind in ("step", "done"):
                    say(line)
    except apt.AptError as err:
        raise Unavailable(e.name, e.minimum, [("system libraries", f"installing {wanted} failed: {err.message}")]) from err


def ensure(p: prov.Provider, names: list[str], *, offline: bool | None = None, profile: _profile.Profile | None = None,
           say=None, ask=None) -> list[Result]:
    """Make the named requirements, and the ones they need, available; raises Unavailable (exit status 3) naming each source tried and why it failed."""
    offline = os.environ.get("ARCHON_OFFLINE", "") not in ("", "0") if offline is None else offline
    prof = profile or _profile.current()
    say = say or progress.say
    ask = ask or _ask
    if p.problems:
        raise tc.ToolchainError("invalid", "; ".join(map(str, p.problems)), f"{p.name}'s declarations have problems: " + "; ".join(map(str, p.problems)), 1)
    results = []
    for name in tc.closure(p, names):
        e = p.entries[name]
        reasons: list[tuple[str, str]] = []
        got = None
        if e.satisfiable_by_computer:
            got = _from_path(e, reasons) or _from_system(e, reasons, offline, prof, say, ask)
        got = got or _from_pinned(p, e, reasons, offline)
        if got is None:
            raise Unavailable(name, e.minimum, reasons)
        if got.source == PINNED:
            _libraries(e, offline, prof, say, ask)
        results.append(got)
    return results


def environment(results: list[Result], base: dict[str, str] | None = None) -> dict[str, str]:
    """`base` (default: this process's environment) with the pinned copies first on PATH and their `env` set. A program from PATH or the system adds nothing (FR-012)."""
    env = dict(os.environ if base is None else base)
    pieces: list[str] = []
    for r in results:
        for k, v in r.env.items():
            if k == "PATH":
                if v not in pieces:
                    pieces.append(v)
            else:
                env[k] = v
    if pieces:
        env["PATH"] = os.pathsep.join([*pieces, env.get("PATH", "")]).rstrip(os.pathsep)
    return env


def available(p: prov.Provider, name: str) -> bool:
    """True when `name` is already met without installing anything: on PATH, or in the store."""
    e = p.entries.get(name)
    if e is None:
        return False
    if e.satisfiable_by_computer:
        exe, found = _probe(e)
        if exe and found and versions.meets(found, e.minimum):
            return True
    return tc.install_path(p, e) is not None


def obtainable(p: prov.Provider, names: list[str], *, offline: bool | None = None) -> list[tuple[str, str]]:
    """The requirements among `names` (and what they need) that can come from no source on this computer, as (name, why); empty when a command naming
    them is runnable here. Nothing is installed (0011-archon FR-004)."""
    offline = os.environ.get("ARCHON_OFFLINE", "") not in ("", "0") if offline is None else offline
    out: list[tuple[str, str]] = []
    for name in tc.closure(p, names):
        e = p.entries[name]
        if available(p, name):
            continue
        if offline:
            out.append((name, "offline, and it is neither on this computer nor in the store"))
        elif e.kind == "archive" and prov.platform() not in e.platforms and not (e.packages.get(system.detect() or "") and e.satisfiable_by_computer):
            out.append((name, f"it has no build for {prov.platform()}"))
    return out
