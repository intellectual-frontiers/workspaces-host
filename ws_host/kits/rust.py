"""The `rust` kit: Rust through the `cargo` requirement of archon, the one copy a computer holds, plus a C toolchain (0003-kits FR-010)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ..core.kit import Check, Download, Kit

MINIMUM = (1, 92)     # www.intellectualfrontiers.com needs 1.92 or later (the same as the cargo requirement's minimum)
PROGRAMS = ("rustc", "cargo", "rustdoc", "rustfmt", "cargo-fmt", "cargo-clippy", "clippy-driver")


def new_enough(work: Path) -> str:
    out = subprocess.run(["cargo", "--version"], capture_output=True, text=True).stdout
    m = re.search(r"cargo (\d+)\.(\d+)", out)
    assert m, f"cargo printed {out!r}"
    assert (int(m.group(1)), int(m.group(2))) >= MINIMUM, f"cargo {m.group(1)}.{m.group(2)} is older than {MINIMUM[0]}.{MINIMUM[1]}"
    return out.strip()


def compiles(work: Path) -> str:
    (work / "h.rs").write_text('fn main() { println!("hello {}", 2 + 3); }\n')
    p = subprocess.run(["rustc", "--edition", "2024", "h.rs", "-o", "h"], cwd=work, capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, "rustc could not compile a program: " + (p.stderr or "")[-300:]
    out = subprocess.run([str(work / "h")], capture_output=True, text=True).stdout
    assert "hello 5" in out, f"the compiled program printed {out!r}"
    return "rustc compiles and runs a program (edition 2024)"


class Rust(Kit):
    name = "rust"
    summary = "Rust (the one copy archon installs for the repositories), build-essential, cmake, pkg-config, perl"
    plain = "the Rust compiler and cargo, for building the company's Rust programs."

    def apt(self, distro):
        return ["build-essential", "cmake", "pkg-config", "perl", "ca-certificates"]

    def requirements(self, distro):
        return {"cargo": PROGRAMS}

    def checks(self, distro):
        return [Check("rustc", "rustc"), Check("cargo", "cargo"), Check("cc", "cc"), Check("cmake", "cmake"), Check("pkg-config", "pkg-config"), Check("perl", "perl"),
                Check("cargo is 1.92 or later", run=new_enough, needs=("cargo",)),
                Check("rustc compiles a program", run=compiles, needs=("rustc", "cc"))]
