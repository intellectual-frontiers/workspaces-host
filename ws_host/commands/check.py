"""`check [SECTION...]` (0041-command-line FR-031 to FR-033) and its sections (0001-ws-host FR-013)."""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

from ..core import machine, paths, registry as reg
from ..core.registry import Arg, section
from ..core.resource import FAILED, MISSING, OK, Resource, WsError


@section("registry", suites=("quick",), summary="no two commands or kits share a name; no module-level third-party import")
def registry_section(ctx):
    return [{"where": "registry", "message": m} for m in reg.discover().conflicts]


@section("launcher", suites=("quick",), summary="the launcher and install.sh are executable and pass sh -n")
def launcher_section(ctx):
    out = []
    for name in ("ws-host", "install.sh"):
        f = paths.repo_root() / name
        if not f.is_file():
            out.append({"where": name, "message": "is missing"})
            continue
        if not os.access(f, os.X_OK):
            out.append({"where": name, "message": "is not executable"})
        p = machine.run(["sh", "-n", str(f)])
        if p.returncode:
            out.append({"where": name, "message": f"does not pass sh -n: {p.stderr.strip()}"})
    return out


def _public_root() -> Path | None:
    """The public root's checker, where it is on the machine: named by the person's workspaces folder, as data."""
    from ..core import config
    explicit = os.environ.get("WS_HOST_PUBLIC_ROOT")
    cands = [Path(explicit)] if explicit else sorted((config.load().workspaces).glob("*/*/.github"))
    for c in cands:
        if (c / "agora").is_file():
            return c
    return None


@section("specs", programs=("agora",), summary="the specs and register pass the public root's checker")
def specs_section(ctx):
    root = _public_root()
    if root is None:
        raise FileNotFoundError("agora")
    p = subprocess.run([str(root / "agora"), "check", "specs", "register", "--root", str(paths.repo_root())],
                       capture_output=True, text=True, timeout=300)
    if p.returncode == 0:
        return []
    return [{"where": "spec-kit", "message": line.strip()} for line in (p.stdout + p.stderr).splitlines()
            if line.strip().startswith(("❎", "🔴", "error", "spec-kit/"))] or [{"where": "spec-kit", "message": "the public root's checker failed"}]


@reg.command("check", category="check", summary="Run the checks of this repository",
             args=(Arg("SECTION", "SECTION", positional=True, multiple=True), Arg("suite", "SECTION", help="a named set of sections")))
def check(ctx, SECTION, suite):
    registry = reg.discover()
    names = list(SECTION)
    if suite:
        names += [s.name for s in registry.sections.values() if suite in s.suites]
        if not any(suite in s.suites for s in registry.sections.values()):
            raise WsError("usage", f"no section is in the suite '{suite}'", f"No check belongs to a set called '{suite}'.", exit_code=2)
    if not names and not suite:
        names = list(registry.sections)
    results, status = [], OK
    for n in names:
        s = registry.sections.get(n)
        if s is None:
            raise WsError("usage", f"no section '{n}'", f"I do not know a check called '{n}'. The checks are: {', '.join(registry.sections)}.", exit_code=2)
        missing = [p for p in s.programs if not shutil.which(p)] if s.name != "specs" else []
        try:
            findings = s.fn(ctx)
            res = {"name": n, "status": "fail" if findings else "ok", "findings": findings}
        except FileNotFoundError as e:
            res = {"name": n, "status": "skip", "findings": [], "reason": f"{e} is not on this machine, so this check did not run"}
        if res["status"] == "fail":
            status = FAILED
        elif res["status"] == "skip" and status == OK:
            status = MISSING   # 0041 FR-033: a skipped section never passes and makes the run non-zero
        results.append(res)
    bad = sum(r["status"] == "fail" for r in results)
    skipped = sum(r["status"] == "skip" for r in results)
    plain = ("Everything checked is in order." if status == OK else
             f"{bad} check{'s' if bad != 1 else ''} found problems." if bad else f"{skipped} check{'s' if skipped != 1 else ''} could not run, so nothing is proven for them.")
    return Resource("check", "ws-host", {"plain": plain, "summary": {"run": len(results) - skipped, "failed": bad, "skipped": skipped},
                                         "sections": results}, status=status)
