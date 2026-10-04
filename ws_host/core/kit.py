"""The kit base (0041-command-line FR-058): a kit declares, in code, what makes a machine fit for one kind of work.

A kit is a class that subclasses `Kit` in a module under `ws_host/kits/` (or a trusted repository's
`.workspaces-host/kits/`). Standard library only at module level.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

ARCHS = ("x86_64", "aarch64")


@dataclass
class Download:
    name: str
    version: str
    url: str                              # a template: {version} and {arch} are filled in
    sha256: dict[str, str]                # per architecture
    binaries: dict[str, str] = field(default_factory=dict)   # link name -> path inside the unpacked directory
    strip: int = 1                        # leading path components removed when unpacking

    def url_for(self, arch: str) -> str:
        return self.url.format(version=self.version, arch=arch)


@dataclass
class Check:
    """A program the kit provides, or a functional check that proves it works."""
    name: str
    program: str | None = None            # a program that must be on PATH
    version_args: tuple[str, ...] = ("--version",)
    run: Callable | None = None           # a functional check: (workdir: Path) -> None, raising AssertionError on failure
    needs: tuple[str, ...] = ()           # programs the functional check runs
    note: str = ""


class Kit:
    name: str = ""
    summary: str = ""
    plain: str = ""                       # one plain sentence for a person: what this kit lets them do
    needs: tuple[str, ...] = ()           # names of kits that must be installed first

    def apt(self, distro: dict) -> list[str]:
        """Packages the host's package manager installs; a name MAY differ by distribution (`distro` is os-release)."""
        return []

    def downloads(self) -> list[Download]:
        return []

    def checks(self) -> list[Check]:
        return []
