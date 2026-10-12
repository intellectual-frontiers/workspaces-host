"""A fetched program: verified by SHA-256 per architecture before anything is unpacked (0003-kits FR-006; 0011-archon FR-016). Standard library only."""
from __future__ import annotations

from dataclasses import dataclass, field

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
