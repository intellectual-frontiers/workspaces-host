"""What the registry's kits provide and which are present (read only; 0041-command-line FR-060)."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from . import machine, registry as reg


def program_present(program: str) -> bool:
    return shutil.which(program) is not None


def kit_report(functional: bool = False) -> list[dict]:
    """Each kit's programs and versions; with `functional`, each functional check's result as well."""
    d = machine.distro()
    out = []
    for name, cls in sorted(reg.discover().kits.items()):
        kit = cls()
        programs, missing, functional_results = {}, [], []
        for c in kit.checks(d):
            if c.program:
                v = machine.program_version(c.program, c.version_args)
                if v is None:
                    missing.append(c.program)
                else:
                    programs[c.program] = v
        installed = not missing and bool(programs)
        if functional and installed:
            for c in kit.checks(d):
                if c.run is None:
                    continue
                gone = [p for p in c.needs if not program_present(p)]
                if gone:
                    functional_results.append({"name": c.name, "status": "skip", "detail": f"needs {', '.join(gone)}"})
                    continue
                with tempfile.TemporaryDirectory() as w:
                    try:
                        functional_results.append({"name": c.name, "status": "ok", "detail": c.run(Path(w)) or "passed"})
                    except AssertionError as e:
                        functional_results.append({"name": c.name, "status": "fail", "detail": str(e)})
                    except Exception as e:  # a check that cannot run is a failed check, never a crash
                        functional_results.append({"name": c.name, "status": "fail", "detail": f"{type(e).__name__}: {e}"})
        out.append({"name": name, "plain": kit.plain, "installed": installed, "programs": programs, "missing": missing,
                    **({"functional": functional_results} if functional else {})})
    return out
