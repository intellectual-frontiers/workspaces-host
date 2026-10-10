"""The `base` kit: a standard userland, git and the forges' tools, scripting and data tools, images, a browser."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from ..core.kit import Check, Download, Floating, Kit
from ..install import floating
from . import _tools


def _run(argv, cwd=None, input=None, timeout=120, env=None):
    p = subprocess.run(argv, cwd=cwd, input=input, capture_output=True, text=True, timeout=timeout, env={**os.environ, **(env or {})})
    return p


def _expect(argv, want, **kw):
    p = _run(argv, **kw)
    out = (p.stdout or "") + (p.stderr or "")
    assert p.returncode == 0, f"{' '.join(argv[:2])} failed: {out.strip()[:200]}"
    assert want in out, f"{' '.join(argv[:2])} printed {out.strip()[:100]!r}, expected {want!r}"


def userland(work: Path) -> str:
    """Each standard tool does one small real job (0003-kits FR-008)."""
    (work / "a.txt").write_text("alpha\nbeta\n")
    (work / "b.txt").write_text("alpha\ngamma\n")
    _expect(["sed", "s/alpha/ALPHA/", "a.txt"], "ALPHA", cwd=work)
    _expect(["find", ".", "-name", "a.txt"], "a.txt", cwd=work)
    _expect(["xargs", "echo", "x"], "x y", cwd=work, input="y\n")
    assert _run(["diff", "a.txt", "b.txt"], cwd=work).returncode == 1, "diff did not see a difference"
    assert _run(["cmp", "a.txt", "a.txt"], cwd=work).returncode == 0, "cmp found a file different from itself"
    (work / "p.diff").write_text(_run(["diff", "-u", "a.txt", "b.txt"], cwd=work).stdout)
    _run(["cp", "a.txt", "c.txt"], cwd=work)
    assert _run(["patch", "c.txt", "p.diff"], cwd=work).returncode == 0, "patch could not apply a diff"
    assert (work / "c.txt").read_text() == "alpha\ngamma\n", "patch changed the wrong thing"
    assert _run(["tar", "cf", "t.tar", "a.txt", "b.txt"], cwd=work).returncode == 0
    _expect(["tar", "tf", "t.tar"], "b.txt", cwd=work)
    for packer, ext in (("gzip", "gz"), ("bzip2", "bz2"), ("xz", "xz")):
        data = work / f"d_{packer}.txt"
        data.write_text("round trip\n")
        assert _run([packer, "-k", str(data)], cwd=work).returncode == 0, f"{packer} failed"
        assert _run([packer, "-dc", f"{data}.{ext}"], cwd=work).stdout == "round trip\n", f"{packer} did not round-trip"
    assert _run(["zip", "-q", "z.zip", "a.txt"], cwd=work).returncode == 0, "zip failed"
    _expect(["unzip", "-p", "z.zip", "a.txt"], "alpha", cwd=work)
    _expect(["file", "a.txt"], "text", cwd=work)
    _expect(["sh", "-c", "which sh"], "sh")
    _expect(["ps", "-p", str(os.getpid())], str(os.getpid()))
    assert _run(["hostname"]).stdout.strip(), "hostname printed nothing"
    assert _run(["tput", "-V"]).returncode == 0, "tput failed"
    (work / "src").mkdir()
    (work / "src" / "f").write_text("x")
    assert _run(["rsync", "-a", "src/", "dst/"], cwd=work).returncode == 0 and (work / "dst" / "f").exists(), "rsync failed"
    _expect(["bc"], "5", input="2+3\n")
    _expect(["grep", "beta", "a.txt"], "beta", cwd=work)
    _expect(["awk", "{print $1}", "a.txt"], "alpha", cwd=work)
    assert _run(["less", "--version"]).returncode == 0, "less failed"
    return "sed find xargs diff cmp patch tar gzip bzip2 xz zip unzip file which ps hostname tput rsync bc grep awk less all work"


def _magick() -> list[str]:
    return ["magick"] if shutil.which("magick") else ["convert"]


def webp(work: Path) -> str:
    """ImageMagick writes and reads WebP, and cwebp and dwebp round-trip a picture (0003-kits FR-008)."""
    out = work / "out.webp"
    p = _run([*_magick(), "-size", "16x16", "xc:red", str(out)])
    assert p.returncode == 0 and out.is_file(), f"ImageMagick could not write WebP: {(p.stderr or '').strip()[:200]}"
    ident = ["identify"] if not shutil.which("magick") else ["magick", "identify"]
    _expect([*ident, str(out)], "WEBP")
    png = work / "in.png"
    assert _run([*_magick(), "-size", "16x16", "xc:blue", str(png)]).returncode == 0
    assert _run(["cwebp", "-quiet", str(png), "-o", str(work / "c.webp")]).returncode == 0, "cwebp failed"
    assert _run(["dwebp", "-quiet", str(work / "c.webp"), "-o", str(work / "d.png")]).returncode == 0, "dwebp failed"
    return "ImageMagick reads and writes WebP; cwebp and dwebp round-trip"


def chromium(work: Path) -> str:
    p = _run(["chromium", "--headless", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--dump-dom", "data:text/html,<p>hello kit</p>"], timeout=90)
    assert "hello kit" in p.stdout, f"chromium did not print the page: {(p.stderr or '').strip()[-200:]}"
    return "chromium prints a page headlessly"


# Chrome for Testing, for a distribution whose own Chromium package is a snap (Ubuntu). It is built for x86_64 only.
CHROME_VERSION = "154.0.8037.92"
CHROME = Download("chrome-for-testing", CHROME_VERSION,
                  "https://storage.googleapis.com/chrome-for-testing-public/{version}/linux64/chrome-linux64.zip",
                  {"x86_64": "ff43322f335e436b2f4dcdfeeec5db032299e335a7e8c1c618b326e100ce8732"},
                  binaries={"chromium": "chrome-linux64/chrome"}, kind="zip")
GLAB_VERSION = "1.120.0"
GLAB = Download("glab", GLAB_VERSION, "https://gitlab.com/gitlab-org/cli/-/releases/v{version}/downloads/glab_{version}_linux_{goarch}.tar.gz",
                {"x86_64": "4e6c59de9f7ed2f304bf93aad01ea8f8a69584f0450ce90ad696ef81f69c69aa",
                 "aarch64": "c60ebb4cb36f276714847a118845b9b4e69f46a8080c68b21ca63f158722cdea"},
                binaries={"glab": "bin/glab"}, strip=0)
DUCKDB = Floating("duckdb", floating.github("duckdb/duckdb", {"x86_64": r"^duckdb_cli-linux-amd64\.zip$", "aarch64": r"^duckdb_cli-linux-(arm64|aarch64)\.zip$"}),
                  binaries={"duckdb": "duckdb"}, kind="zip")
# sqlite.org builds the command-line tools for x86-64 only; elsewhere the distribution's sqlite3 (installed above) is the one used
SQLITE = Floating("sqlite", floating.sqlite_org, binaries={"sqlite3": "sqlite3", "sqldiff": "sqldiff", "sqlite3_analyzer": "sqlite3_analyzer"}, kind="zip", auto=True, archs=("x86_64",))

USERLAND = [("sed", ("--version",)), ("find", ("--version",)), ("xargs", ("--version",)), ("diff", ("--version",)), ("cmp", ("--version",)),
            ("patch", ("--version",)), ("tar", ("--version",)), ("gzip", ("--version",)), ("unzip", ("-v",)), ("zip", ("-v",)),
            ("bzip2", ("--version",)), ("xz", ("--version",)), ("file", ("--version",)), ("less", ("--version",)), ("which", ("-v",)),
            ("ps", ("--version",)), ("hostname", ("--version",)), ("tput", ("-V",)), ("rsync", ("--version",)), ("bc", ("--version",)),
            ("grep", ("--version",)), ("awk", ("--version",))]


class Base(Kit):
    name = "base"
    summary = "Standard userland, git, gh, glab, jq, ripgrep, fd, curl, wget, python3, uv, Node.js, ImageMagick with WebP, sqlite3, DuckDB, shellcheck, Chromium"
    plain = "the everyday tools every repository assumes: git, GitHub and GitLab sign-in, search, images, a browser."

    def apt(self, distro):
        pkgs = ["coreutils", "sed", "findutils", "diffutils", "patch", "tar", "gzip", "unzip", "zip", "bzip2", "xz-utils", "file", "less",
                "debianutils", "procps", "hostname", "ncurses-bin", "rsync", "bc", "grep", "gawk",
                "git", "gh", "jq", "ripgrep", "fd-find", "curl", "wget", "bash-completion", "ca-certificates", "python3", "nodejs", "npm",
                "imagemagick", "webp", "libmagickcore-7.q16-10-extra|libmagickcore-6.q16-7-extra|libmagickcore-6.q16-6-extra", "sqlite3", "shellcheck"]
        if distro["id"] == "debian":
            pkgs.append("chromium")
        else:   # Ubuntu's chromium package is a snap, which a container or a server cannot run: the fetched build is used (downloads)
            pkgs += ["libnss3", "libatk1.0-0t64|libatk1.0-0", "libatk-bridge2.0-0t64|libatk-bridge2.0-0", "libcups2t64|libcups2", "libdrm2",
                     "libxkbcommon0", "libxcomposite1", "libxdamage1", "libxfixes3", "libxrandr2", "libgbm1", "libasound2t64|libasound2",
                     "libpango-1.0-0", "libcairo2", "libx11-6", "libxcb1", "libxext6", "fonts-liberation"]
        if distro["id"] == "debian" and distro.get("codename") not in ("bookworm", "bullseye"):
            pkgs.append("glab")
        return pkgs

    def downloads(self, distro):
        out = [DUCKDB, SQLITE]
        if not (distro["id"] == "debian" and distro.get("codename") not in ("bookworm", "bullseye")):
            out.append(GLAB)
        if distro["id"] != "debian":
            out.append(CHROME)
        return out + list(_tools.TOOLS)

    def links(self, distro):
        return {"fd": ("fdfind",)}

    def checks(self, distro):
        c = [Check(n, n, a) for n, a in USERLAND]
        c += [Check("git", "git"), Check("gh", "gh"), Check("glab", "glab"), Check("jq", "jq"), Check("rg", "rg"), Check("fd", "fd"),
              Check("curl", "curl"), Check("wget", "wget"), Check("python3", "python3"), Check("uv", "uv"), Check("node", "node"),
              Check("ImageMagick", "magick", or_programs=("convert",)), Check("cwebp", "cwebp", ("-version",)), Check("dwebp", "dwebp", ("-version",)),
              Check("sqlite3", "sqlite3"), Check("duckdb", "duckdb"), Check("shellcheck", "shellcheck"), Check("chromium", "chromium")]
        c += _tools.checks()
        c += [Check("userland works", run=userland, needs=("sed", "find", "xargs", "diff", "cmp", "patch", "tar", "gzip", "bzip2", "xz", "zip", "unzip", "file", "which", "ps", "hostname", "tput", "rsync", "bc", "grep", "awk", "less")),
              Check("ImageMagick reads and writes WebP", run=webp, needs=("cwebp", "dwebp", "magick|identify")),
              Check("Chromium prints a page", run=chromium, needs=("chromium",))]
        return c
