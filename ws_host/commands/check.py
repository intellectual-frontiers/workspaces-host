"""`check [SECTION...]` (0041-command-line FR-031 to FR-033) and its sections (0001-ws-host FR-013)."""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

from ..core import machine, paths, presentation, registry as reg, types
from ..core.registry import Arg, section
from ..core.resource import FAILED, MISSING, OK, Resource, WsError

types.SECTION.complete = lambda ctx: sorted(reg.discover().sections)


def _f(where: str, message: str, level: str = "error") -> dict:
    return {"level": level, "where": where, "message": message, "next": f"edit {where.split(':')[0].split(' ')[0]}, then run `check`"}


@section("registry", suites=("quick",), summary="no two commands or kits share a name; no module-level third-party import; titles, icons and views are well formed")
def registry_section(ctx):
    r = reg.discover()
    out = [_f("registry", m) for m in r.conflicts]
    for c in r.commands.values():       # 0041 FR-008, FR-010, FR-014: the grammar is closed
        if c.category not in reg.CATEGORIES:
            out.append(_f(c.module, f"'{c.id}' has category '{c.category}', which is not one of {', '.join(reg.CATEGORIES)}"))
        if c.noun and c.verb not in reg.VERBS:
            out.append(_f(c.module, f"'{c.id}' uses the verb '{c.verb}', which is not in the closed set ({', '.join(reg.VERBS)})"))
        if not c.noun and c.words[0] not in reg.REPOWIDE:
            out.append(_f(c.module, f"'{c.id}' has no noun and is not one of the repository-wide commands"))
    out += [_f("ws_host/commands/presentation.py", m) for m in presentation.problems(r)]      # 0041 FR-072
    return out


@section("launcher", suites=("quick",), summary="the launcher and install.sh are executable and pass sh -n")
def launcher_section(ctx):
    out = []
    for name in ("ws-host", "install.sh"):
        f = paths.repo_root() / name
        if not f.is_file():
            out.append(_f(name, "is missing"))
            continue
        if not os.access(f, os.X_OK):
            out.append(_f(name, "is not executable"))
        p = machine.run(["sh", "-n", str(f)])
        if p.returncode:
            out.append(_f(name, f"does not pass sh -n: {p.stderr.strip()}"))
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
    found = [line.strip().lstrip("❎🔴 ") for line in (p.stdout + p.stderr).splitlines() if line.strip().startswith(("❎", "🔴", "error", "spec-kit/"))]
    return [_f(*(m.split(": ", 1) if ": " in m else ("spec-kit", m))) for m in found] or [_f("spec-kit", "the public root's checker failed")]


@section("console", suites=("slow",), programs=("agora",),
         summary="the IF Console serves ws-host in a real VS Code (named, not part of a plain check: it needs VS Code and a display server)")
def console_section(ctx):
    """0004-editor-extension FR-027: the public root's `agora extension test` runs this repository's suite (tests/if_console/vscode) in a real
    VS Code, with ws-host as a workspace folder. It is skipped, naming the cause, where the public root or VS Code is not here."""
    root = _public_root()
    if root is None:
        raise FileNotFoundError("agora")
    import json
    import tempfile
    suite = paths.repo_root() / "tests" / "if_console" / "vscode"
    with tempfile.TemporaryDirectory(prefix="ws-host-console-") as tmp:
        report = Path(tmp) / "report.json"
        p = subprocess.run([str(root / "agora"), "extension", "test", "--suite", str(suite), "--workspace", f"ws-host={paths.repo_root()}",
                            "--report", str(report), "--json"], capture_output=True, text=True, timeout=1800)
        if p.returncode == 3:
            try:
                why = json.loads(p.stdout.strip().splitlines()[-1])["data"].get("message") or "VS Code could not start"
            except (ValueError, KeyError, IndexError):
                why = "VS Code could not start"
            raise FileNotFoundError(f"VS Code ({why})")
        rows = json.loads(report.read_text(encoding="utf-8")).get("tests", []) if report.is_file() else []
    out = [_f(r["name"], f"failed in a real VS Code ({r.get('seconds', 0)}s)") for r in rows if r.get("status") != "passed"]
    if p.returncode not in (0, 1) or (p.returncode == 1 and not out):
        out.append(_f("agora extension test", f"it did not give an answer I could read (exit {p.returncode})"))
    return out


@reg.command("check", category="check", summary="Run the checks of this repository",
             args=(Arg("sections", "SECTION", positional=True, multiple=True), Arg("suite", "SECTION", help="a named set of sections")))
def check(ctx, sections, suite):
    registry = reg.discover()
    names = list(sections)
    if suite:
        names += [s.name for s in registry.sections.values() if suite in s.suites]
        if not any(suite in s.suites for s in registry.sections.values()):
            raise WsError("usage", f"no section is in the suite '{suite}'", f"No check belongs to a set called '{suite}'.", exit_code=2)
    if not names and not suite:
        names = [n for n, s in registry.sections.items() if "slow" not in s.suites]      # a slow section runs when it is named
    results, status = [], OK
    for n in names:
        s = registry.sections.get(n)
        if s is None:
            raise WsError("usage", f"no section '{n}'", f"I do not know a check called '{n}'. The checks are: {', '.join(registry.sections)}.", exit_code=2)
        missing = [p for p in s.programs if not shutil.which(p)] if s.name != "specs" else []
        try:
            findings = s.fn(ctx)
            res = {"name": n, "status": "failed" if findings else "passed", "findings": findings, "notes": [], "data": {}}
        except FileNotFoundError as e:
            res = {"name": n, "status": "skipped", "findings": [], "notes": [], "data": {}, "reason": f"{e} is not on this machine, so this check did not run"}
        if res["status"] == "failed":
            status = FAILED
        elif res["status"] == "skipped" and status == OK:
            status = MISSING   # 0041 FR-033: a skipped section never passes and makes the run non-zero
        results.append(res)
    bad = sum(r["status"] == "failed" for r in results)
    skipped = sum(r["status"] == "skipped" for r in results)
    plain = ("Everything checked is in order." if status == OK else
             f"{bad} check{'s' if bad != 1 else ''} found problems." if bad else f"{skipped} check{'s' if skipped != 1 else ''} could not run, so nothing is proven for them.")
    return Resource("check", "ws-host", {"plain": plain, "suite": suite, "scope": None, "changed": False,
                                         "status": {OK: "passed", FAILED: "failed", MISSING: "skipped"}[status],
                                         "summary": {"run": len(results) - skipped, "passed": len(results) - skipped - bad, "failed": bad, "skipped": skipped},
                                         "sections": results, "skipped_unchanged": []}, status=status)
