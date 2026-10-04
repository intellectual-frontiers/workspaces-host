"""What the registry's kits provide and which are present (read only; 0041-command-line FR-060)."""
from __future__ import annotations

import shutil

from . import machine, registry as reg


def kit_report() -> list[dict]:
    out = []
    for name, cls in sorted(reg.discover().kits.items()):
        kit = cls()
        programs, missing = {}, []
        for c in kit.checks():
            if c.program:
                v = machine.program_version(c.program, c.version_args)
                if v is None:
                    missing.append(c.program)
                else:
                    programs[c.program] = v
        out.append({"name": name, "installed": not missing and bool(programs), "programs": programs, "missing": missing})
    return out
