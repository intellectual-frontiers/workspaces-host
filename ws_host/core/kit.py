"""The kit base (0041-command-line FR-058): a kit declares, in code, what makes a machine fit for one kind of work.

A kit is a class that subclasses `Kit` in a module under `ws_host/kits/` (or a trusted repository's
`.workspaces-host/kits/`). Standard library only at module level.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

ARCHS = ("x86_64", "aarch64")
GOARCH = {"x86_64": "amd64", "aarch64": "arm64"}


@dataclass
class Download:
    """A fetched tool: verified by SHA-256 per architecture before anything is unpacked (0003-kits FR-006)."""
    name: str
    version: str
    url: str                              # a template: {version}, {arch}, {triple} and {goarch} are filled in
    sha256: dict[str, str]                # per architecture of ARCHS; an architecture not named is unsupported
    binaries: dict[str, str] = field(default_factory=dict)   # link name -> path inside the installed directory
    kind: str = "tar"                     # tar (any tarball), zip, file (one program), or deb (a package unpacked by a step)
    strip: int = 1                        # leading path components removed when unpacking a tarball
    steps: tuple[tuple[str, ...], ...] = ()   # install steps run in the unpacked source: {src} and {dest} are filled in

    def url_for(self, arch: str) -> str:
        return self.url.format(version=self.version, arch=arch, triple=f"{arch}-unknown-linux-gnu", goarch=GOARCH.get(arch, arch))

    def supports(self, arch: str) -> bool:
        return arch in self.sha256


@dataclass
class Resolved:
    """What the newest version of a floating tool is and how to fetch it, found when it is installed (0003-kits FR-017)."""
    version: str
    url: str = ""                         # an archive or one program; empty for a package
    sha256: str = ""                      # the publisher's own checksum of that file, when it publishes one
    signature_url: str = ""               # or a detached signature of it, checked against `key` and `fingerprint`
    key: str = ""                         # a path to the publisher's public key, shipped with ws-host
    fingerprint: str = ""
    integrity: str = ""                   # for a package: the registry's own integrity string for the version, which is checked after the install


@dataclass
class Floating:
    """A tool that floats with its newest release (0003-kits FR-017): no version or checksum is written here. What the newest version is, and the publisher's own checksum
    or signature for it, are found from the publisher when it is installed; nothing is unpacked or run that did not match. `manager` is empty for an archive or a program, `npm`
    or `pip` for a package, installed with ws-host's own Node or uv into a folder of its own."""
    name: str
    resolve: Callable[[str], Resolved]                  # (architecture) -> the newest version
    binaries: dict[str, str] = field(default_factory=dict)   # link name -> path inside the installed directory; {arch} and {goarch} are filled in
    kind: str = "tar"                     # as Download.kind
    strip: int = 1
    steps: tuple[tuple[str, ...], ...] = ()   # install steps; {src} and {dest} are filled in. With `in_place` the steps run in the unpacked source and install into {dest}
    in_place: bool = False                # the tool's own installer writes absolute paths, so it installs where it will stay
    manager: str = ""
    package: str = ""
    version: str = "latest"
    sha256: dict[str, str] = field(default_factory=dict)   # empty: duck-types the pinned kind for the plan

    def url_for(self, arch: str) -> str:
        return "the publisher's newest release, found when it is installed"

    def supports(self, arch: str) -> bool:
        return arch in ARCHS


@dataclass
class Check:
    """A program the kit provides, or a functional check that proves it works."""
    name: str
    program: str | None = None            # a program that must be on PATH
    or_programs: tuple[str, ...] = ()     # ... or, failing that, one of these (ImageMagick 6 names its program convert)
    version_args: tuple[str, ...] = ("--version",)
    run: Callable | None = None           # a functional check: (workdir: Path) -> str, raising AssertionError on failure
    needs: tuple[str, ...] = ()           # programs the functional check runs; it is skipped when one is missing


class Kit:
    name: str = ""
    summary: str = ""
    plain: str = ""                       # one plain sentence for a person: what this kit lets them do

    def apt(self, distro: dict) -> list[str]:
        """Packages the host's package manager installs; `a|b` is the first the distribution has; a name MAY differ by distribution."""
        return []

    def downloads(self, distro: dict) -> list[Download]:
        return []

    def links(self, distro: dict) -> dict[str, tuple[str, ...]]:
        """Names to link into the person's bin directory to the first program that exists, such as fd -> fdfind."""
        return {}

    def checks(self, distro: dict) -> list[Check]:
        return []
