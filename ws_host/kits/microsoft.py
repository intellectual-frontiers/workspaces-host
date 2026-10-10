"""The `microsoft` kit: Microsoft's own sign-in library, so that `ws-host auth new microsoft` and the `onedrive` commands can reach a personal or work account (0003-kits FR-021)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from ..core.kit import Check, Floating, Kit
from ..install import floating

IDENTITY = Floating("microsoft-identity", floating.pypi("azure-identity"), binaries={"ms-python": "bin/python"}, manager="pip", package="azure-identity")


def imports(work: Path) -> str:
    from ..lib import graph
    py = graph.venv_python()
    p = subprocess.run([str(py), "-c", "import azure.identity as a; print(a.__version__ if hasattr(a, '__version__') else 'ok')"], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, "Microsoft's sign-in library does not load: " + (p.stderr or "")[-300:]
    return "azure-identity " + p.stdout.strip()


class Microsoft(Kit):
    name = "microsoft"
    summary = "Microsoft's sign-in library (azure-identity) and ms-python, a Python that has it, for ws-host auth new microsoft and the onedrive commands"
    plain = "sign in to a personal or work Microsoft account, and list, copy and fetch files in its OneDrive."

    def apt(self, distro):
        return ["ca-certificates"]

    def downloads(self, distro):
        return [IDENTITY]

    def checks(self, distro):
        return [Check("ms-python", "ms-python"), Check("Microsoft sign-in library loads", run=imports, needs=("ms-python",))]
