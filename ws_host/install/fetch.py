"""The download installer (0003-kits FR-006): fetch, verify SHA-256 before unpacking, unpack into a versioned directory,
repoint `current` atomically, link binaries. Standard library only."""
from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from ..core import paths, progress
from ..core.kit import ARCHS, GOARCH, Download, Floating


class FetchError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def arch() -> str:
    m = platform.machine().lower()
    return {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64"}.get(m, m)


def version_dir(d: Download) -> Path:
    return paths.tools_dir() / d.name / d.version


def current_link(d: Download) -> Path:
    return paths.tools_dir() / d.name / "current"


def is_installed(d) -> bool:
    if isinstance(d, Floating):
        from . import floating
        return floating.is_installed(d)
    cur = current_link(d)
    return cur.is_symlink() and os.readlink(cur) == d.version and version_dir(d).is_dir()


def download(url: str, expected: str | None, offline: bool = False) -> Path:
    """Fetch url into the cache and return the file only if its SHA-256 equals `expected`. With none given, the file is kept under its own SHA-256 for the caller to
    check some other way (a signature), and what installs it then names that SHA-256 so that nothing else can be unpacked in its place."""
    if offline:
        raise FetchError("offline", f"{url} is needed and you are offline")
    cache = paths.cache_dir() / "downloads"
    cache.mkdir(parents=True, exist_ok=True)
    final = cache / expected if expected else None
    if final is not None and final.is_file() and _sha(final) == expected:
        return final
    tmp = Path(tempfile.mkstemp(dir=cache, suffix=".part")[1])
    h = hashlib.sha256()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ws-host"})
        with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0) or None
            done = 0
            while chunk := r.read(1 << 16):
                h.update(chunk)
                f.write(chunk)
                done += len(chunk)
                progress.detail(progress.megabytes(done, total))
    except OSError as e:
        tmp.unlink(missing_ok=True)
        raise FetchError("unreachable", f"could not fetch {url}: {e}") from e
    if expected and h.hexdigest() != expected:
        tmp.unlink(missing_ok=True)
        raise FetchError("checksum", f"the file at {url} is not the one this kit expects (its SHA-256 is {h.hexdigest()}, expected {expected}); nothing was installed")
    final = cache / h.hexdigest()
    os.replace(tmp, final)
    return final


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def _safe(member_name: str, dest: Path) -> Path:
    target = (dest / member_name).resolve()
    if dest.resolve() not in target.parents and target != dest.resolve():
        raise FetchError("unsafe-archive", f"the archive holds a path outside its folder: {member_name}")
    return target


def _unpack(archive: Path, d: Download, dest: Path) -> None:
    dest.mkdir(parents=True)
    if d.kind == "file":
        target = dest / next(iter(d.binaries.values()), d.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(archive, target)
        target.chmod(0o755)       # a single downloaded file is a program
        return
    if d.kind == "deb":
        shutil.copy2(archive, dest / f"{d.name}.deb")   # unpacked by an install step (dpkg-deb -x), which every Debian-family host has
        return
    if d.kind == "zip":
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                target = _safe(info.filename, dest)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
                mode = info.external_attr >> 16
                if mode & 0o111:
                    target.chmod(target.stat().st_mode | 0o111)
        return
    with tarfile.open(archive) as t:
        for m in t.getmembers():
            parts = Path(m.name).parts[d.strip:]
            if not parts:
                continue
            m.name = str(Path(*parts))
            _safe(m.name, dest)
            if m.issym() or m.islnk():
                link_target = os.path.normpath(os.path.join(os.path.dirname(m.name), m.linkname)) if m.issym() else m.linkname
                _safe(link_target, dest)
            t.extract(m, dest, filter="tar")


def install(d: Download, offline: bool = False) -> dict:
    """Install one download for this machine. Returns what was done; raises FetchError and leaves nothing half-installed."""
    if isinstance(d, Floating):
        from . import floating
        return floating.install(d, offline)
    a = arch()
    if not d.supports(a):
        raise FetchError("unsupported-arch", f"{d.name} {d.version} is not available for {a} in this kit")
    if is_installed(d) and all(_linked(name) for name in d.binaries):
        return {"name": d.name, "version": d.version, "outcome": "present"}
    root = paths.tools_dir() / d.name
    target = version_dir(d)
    if not target.is_dir():
        with progress.step(f"📥 Downloading {d.name} {d.version}", announce=not offline):
            archive = download(d.url_for(a), d.sha256[a], offline)
        root.mkdir(parents=True, exist_ok=True)
        partial = root / f"{d.version}.partial"
        shutil.rmtree(partial, ignore_errors=True)
        try:
            if d.steps:
                src = root / f"{d.version}.src"
                shutil.rmtree(src, ignore_errors=True)
                _unpack(archive, d, src)
                for step in d.steps:
                    argv = [s.format(src=str(src), dest=str(partial)) for s in step]
                    p = subprocess.run(argv, cwd=str(src), capture_output=True, text=True)
                    if p.returncode != 0:
                        raise FetchError("install-step", f"{' '.join(argv[:2])} failed: {(p.stderr or p.stdout).strip()[-300:]}")
                shutil.rmtree(src, ignore_errors=True)
            else:
                _unpack(archive, d, partial)
            os.replace(partial, target)
        except BaseException:
            shutil.rmtree(partial, ignore_errors=True)
            shutil.rmtree(root / f"{d.version}.src", ignore_errors=True)
            raise
    link = current_link(d)
    tmp = root / "current.new"
    tmp.unlink(missing_ok=True)
    os.symlink(d.version, tmp)
    os.replace(tmp, link)                       # atomic: `current` always names a complete version
    linked = []
    paths.bin_dir().mkdir(parents=True, exist_ok=True)
    for name, rel in d.binaries.items():
        _link_binary(name, link / rel)
        linked.append(name)
    return {"name": d.name, "version": d.version, "outcome": "installed", "linked": linked}


def _linked(name: str) -> bool:
    return os.path.lexists(paths.bin_dir() / name)


def _link_binary(name: str, target: Path) -> None:
    dest = paths.bin_dir() / name
    tmp = paths.bin_dir() / f".{name}.new"
    tmp.unlink(missing_ok=True)
    os.symlink(target, tmp)
    os.replace(tmp, dest)


def link_program(name: str, program: str) -> bool:
    """Link `name` in the person's bin directory to an existing program (fd -> fdfind)."""
    exe = shutil.which(program)
    if not exe:
        return False
    dest = paths.bin_dir() / name
    paths.bin_dir().mkdir(parents=True, exist_ok=True)
    if dest.is_symlink() and os.readlink(dest) == exe:
        return True
    if os.path.lexists(dest):
        return True       # something of the person's is there: leave it
    os.symlink(exe, dest)
    return True
