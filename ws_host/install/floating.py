"""Tools that float with their newest release (0003-kits FR-017): the cloud providers' command lines change often, so what is installed is whatever the publisher says is newest
when ws-host looks, and `ws-host update` looks. Nothing is installed that did not match what the publisher itself publishes for that release: its checksum for the file (GitHub
publishes one for each release file), or its detached signature checked against the publisher's key that ships with ws-host, or, for a package, the registry's integrity string for
the version. Where none can be had, nothing is installed. A newer version is installed beside the one in use and `current` is repointed only when it is complete; the one before it is
kept, so a bad release can be left behind. Standard library only."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from ..core import paths, progress
from ..core.kit import GOARCH, Download, Floating, Resolved
from . import fetch
from .fetch import FetchError

KEEP_VERSIONS = 2            # the one in use and the one before it


# ---- where the publishers answer (each can be pointed elsewhere, for a test) --------------------------------------------------------

def _base(var: str, default: str) -> str:
    return (os.environ.get(var) or default).rstrip("/")


def _get(url: str, headers: dict | None = None, timeout: float = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "ws-host", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except OSError as e:
        raise FetchError("unreachable", f"could not ask {url}: {e}") from e


def _json(url: str, headers: dict | None = None):
    try:
        return json.loads(_get(url, headers))
    except ValueError as e:
        raise FetchError("unreadable", f"{url} did not answer in a form I can read") from e


def _github_headers() -> dict:
    """GitHub answers an anonymous program a few dozen times an hour; a signed-in person's token (read from the environment or from `gh`, never kept or shown) lifts that."""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token and shutil.which("gh"):
        try:
            token = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            token = ""
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"} if token else {"Accept": "application/vnd.github+json"}


# ---- resolvers: what is newest, and the publisher's own word for it -----------------------------------------------------------------

def github(repo: str, assets: dict[str, str]):
    """The newest release of a GitHub repository; `assets` names, per architecture, a pattern for the release file to take."""
    def resolve(arch: str) -> Resolved:
        rel = _json(f"{_base('WS_HOST_GITHUB_API', 'https://api.github.com')}/repos/{repo}/releases/latest", _github_headers())
        pattern = assets.get(arch)
        if not pattern:
            raise FetchError("unsupported-arch", f"{repo} publishes nothing for {arch}")
        found = [a for a in rel.get("assets", []) if re.search(pattern, a.get("name", ""))]
        if not found:
            raise FetchError("no-asset", f"the newest release of {repo} ({rel.get('tag_name')}) has no file for {arch}")
        a = found[0]
        digest = str(a.get("digest") or "")
        sha = digest.split(":", 1)[1] if digest.startswith("sha256:") else ""
        if not sha:                                                   # an older release: a checksum file the publisher put beside it
            for c in rel.get("assets", []):
                if re.search(r"(checksums?|sha256sums?)(\.txt)?$|\.sha256$", c.get("name", ""), re.I):
                    for line in _get(c["browser_download_url"]).decode("utf-8", "replace").splitlines():
                        parts = line.split()
                        if len(parts) >= 1 and (a["name"] in line or c["name"].endswith(".sha256")) and re.fullmatch(r"[0-9a-f]{64}", parts[0]):
                            sha = parts[0]
        if not sha:
            raise FetchError("no-checksum", f"{repo} published no checksum for {a['name']}, so I will not install it")
        tag = str(rel.get("tag_name", ""))
        m = re.search(r"\d+(?:\.\d+)+", tag)               # `v4.5.0`, `2025.9.1` and `azure-dev-cli_1.23.0` are all the version in them
        return Resolved(version=m.group(0) if m else tag.lstrip("v"), url=a["browser_download_url"], sha256=sha)
    return resolve


_WRONG_ARCH = ("armv", "arm32", "i686", "i386", "riscv", "s390", "ppc", "mips", "loong", "386", "x86.", "-32bit")
_WRONG_FILE = ("darwin", "macos", "apple", "windows", "win32", "win64", ".exe", "freebsd", "netbsd", "openbsd", "android", ".deb", ".rpm", ".apk", ".msi", ".pkg", ".dmg", ".sig", ".asc", ".pem",
               ".sbom", ".sha", ".md5", "checksum", "sha256", ".json", ".txt", ".sh", ".intoto", ".sigstore", ".bundle", "source", "src.", "debug", "-symbols")
_ARCHIVES = (".tar.gz", ".tgz", ".tar.xz", ".txz", ".tar.bz2", ".tbz", ".tbz2", ".zip")


def pick_asset(names: list[str], arch: str) -> str | None:
    """The release file for Linux on this architecture, chosen by its name: the one that says linux and the architecture, is not for another system, a package or a signature, and, of the rest,
    is a static (musl) build if there is one, then a plain program or an archive. None when nothing fits; the caller then refuses rather than guess."""
    words = {"x86_64": ("x86_64", "amd64", "x64"), "aarch64": ("aarch64", "arm64")}[arch]
    other = {"x86_64": ("aarch64", "arm64"), "aarch64": ("x86_64", "amd64", "x64")}[arch]
    best, best_score = None, -1
    for n in names:
        low = n.lower()
        if "linux" not in low or not any(w in low for w in words) or any(o in low for o in other):
            continue
        if any(b in low for b in _WRONG_FILE) or any(b in low for b in _WRONG_ARCH):
            continue
        archive = any(low.endswith(e) for e in _ARCHIVES)
        if not archive and low.endswith((".gz", ".xz", ".bz2", ".zst", ".7z")):
            continue
        score = (4 if "musl" in low else 2 if "static" in low else 0) + (0 if "gnueabi" in low else 1) + (1 if archive else 0)
        if score > best_score:
            best, best_score = n, score
    return best


def github_auto(repo: str):
    """The newest release of a GitHub repository, the file for Linux on this architecture chosen by its name, and the checksum GitHub states for it."""
    def resolve(arch: str) -> Resolved:
        api = f"{_base('WS_HOST_GITHUB_API', 'https://api.github.com')}/repos/{repo}/releases"
        rel = _json(f"{api}/latest", _github_headers())
        assets = rel.get("assets", [])
        name = pick_asset([a.get("name", "") for a in assets], arch)
        if not name:        # a release made without its programs (the project's build had not finished, or failed): the newest one before it that has them
            for older in _json(f"{api}?per_page=15", _github_headers()):
                if older.get("draft") or older.get("prerelease"):
                    continue
                name = pick_asset([a.get("name", "") for a in older.get("assets", [])], arch)
                if name:
                    rel, assets = older, older.get("assets", [])
                    break
        if not name:
            raise FetchError("no-asset", f"the newest releases of {repo} (from {rel.get('tag_name')}) have no Linux file for {arch} that I can choose by its name")
        a = next(x for x in assets if x.get("name") == name)
        digest = str(a.get("digest") or "")
        sha = digest.split(":", 1)[1] if digest.startswith("sha256:") else ""
        if not sha:
            for c in assets:
                if re.search(r"(checksums?|sha256sums?)(\.txt)?$|\.sha256(sum)?$", c.get("name", ""), re.I):
                    for line in _get(c["browser_download_url"]).decode("utf-8", "replace").splitlines():
                        parts = line.split()
                        if parts and re.fullmatch(r"[0-9a-f]{64}", parts[0]) and (name in line or c["name"].lower().endswith(".sha256") and c["name"].lower().startswith(name.lower())):
                            sha = parts[0]
        if not sha:
            raise FetchError("no-checksum", f"{repo} published no checksum for {name}, so I will not install it")
        low = name.lower()
        kind = "zip" if low.endswith(".zip") else "tar" if any(low.endswith(e) for e in _ARCHIVES) else "file"
        tag = str(rel.get("tag_name", ""))
        m = re.search(r"\d+(?:\.\d+)+", tag)
        return Resolved(version=m.group(0) if m else tag.lstrip("v"), url=a["browser_download_url"], sha256=sha, kind=kind, asset=name)
    return resolve


def aws_cli(arch: str) -> Resolved:
    """The AWS CLI's own newest version (its changelog's first release), the zip for it, and AWS's detached signature, checked against AWS's key."""
    base = _base("WS_HOST_AWS_CLI_URL", "https://awscli.amazonaws.com")
    log = _get(_base("WS_HOST_AWS_CLI_CHANGELOG", "https://raw.githubusercontent.com/aws/aws-cli/v2/CHANGELOG.rst")).decode("utf-8", "replace")
    m = re.search(r"^(\d+\.\d+\.\d+)$", log, re.M)
    if not m:
        raise FetchError("unreadable", "I could not read which AWS CLI version is newest")
    url = f"{base}/awscli-exe-linux-{arch}-{m.group(1)}.zip"
    return Resolved(version=m.group(1), url=url, signature_url=url + ".sig", key=str(AWS_KEY), fingerprint=AWS_FINGERPRINT)


AWS_KEY = Path(__file__).resolve().parents[1] / "data" / "keys" / "aws-cli.asc"
AWS_FINGERPRINT = "FB5DB77FD5C118B80511ADA8A6310ACC4672475C"      # published by AWS at docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html


def sqlite_org(arch: str) -> Resolved:
    """SQLite's own newest command-line tools (sqlite3, sqldiff, sqlite3_analyzer): sqlite.org lists the newest version, each file and its SHA3-256 on its download page."""
    page = _get(_base("WS_HOST_SQLITE_URL", "https://www.sqlite.org") + "/download.html").decode("utf-8", "replace")
    word = {"x86_64": "x64", "aarch64": "arm64"}.get(arch)
    for m in re.finditer(r"^PRODUCT,([\d.]+),(\S*?sqlite-tools-linux-(\w+)-\d+\.zip),\d+,([0-9a-f]{64})\s*$", page, re.M):
        if m.group(3) == word:
            return Resolved(version=m.group(1), url=f"{_base('WS_HOST_SQLITE_URL', 'https://www.sqlite.org')}/{m.group(2)}", sha3=m.group(4), kind="zip")
    raise FetchError("unsupported-arch", f"sqlite.org publishes no command-line tools for {arch}")


def npm(package: str):
    def resolve(arch: str) -> Resolved:
        doc = _json(f"{_base('WS_HOST_NPM_REGISTRY', 'https://registry.npmjs.org')}/{package.replace('/', '%2f')}/latest")
        return Resolved(version=str(doc["version"]), integrity=str((doc.get("dist") or {}).get("integrity") or ""))
    return resolve


def pypi(package: str):
    def resolve(arch: str) -> Resolved:
        doc = _json(f"{_base('WS_HOST_PYPI', 'https://pypi.org')}/pypi/{package}/json")
        return Resolved(version=str(doc["info"]["version"]))
    return resolve


# ---- checking ------------------------------------------------------------------------------------------------------------------------

def verify_signature(file: Path, signature: Path, key: Path, fingerprint: str) -> None:
    """The file is what the key's owner signed: the key shipped with ws-host must have the fingerprint it is known by, and the signature must be a good one from it."""
    if not shutil.which("gpg"):
        raise FetchError("no-gpg", "gpg is needed to check the signature, and it is not installed; the kit's packages include it")
    with tempfile.TemporaryDirectory() as home:
        env = {**os.environ, "GNUPGHOME": home}
        os.chmod(home, 0o700)
        shown = subprocess.run(["gpg", "--batch", "--with-colons", "--show-keys", str(key)], capture_output=True, text=True, env=env)
        if fingerprint.upper() not in shown.stdout.upper():
            raise FetchError("wrong-key", "the key shipped with ws-host is not the one this tool is signed with; nothing was installed")
        subprocess.run(["gpg", "--batch", "--import", str(key)], capture_output=True, text=True, env=env, check=False)
        v = subprocess.run(["gpg", "--batch", "--status-fd", "1", "--verify", str(signature), str(file)], capture_output=True, text=True, env=env)
        good = [l.split() for l in v.stdout.splitlines() if l.startswith("[GNUPG:] VALIDSIG")]
        if v.returncode != 0 or not any(fingerprint.upper() in (x.upper() for x in parts) for parts in good):
            raise FetchError("bad-signature", "the signature on the download is not a good one from the publisher's key; nothing was installed")


def _fetch_checked(r: Resolved, offline: bool) -> str:
    """Download what `r` names and return its SHA-256, having proved the file is the publisher's: by the publisher's checksum, or by its signature."""
    if r.sha256:
        fetch.download(r.url, r.sha256, offline)
        return r.sha256
    if r.sha3:
        archive = fetch.download(r.url, None, offline)
        if hashlib.sha3_256(archive.read_bytes()).hexdigest() != r.sha3:
            archive.unlink(missing_ok=True)
            raise FetchError("checksum", f"the file at {r.url} is not the one its publisher lists (its SHA3-256 differs); nothing was installed")
        return archive.name
    if r.signature_url:
        archive = fetch.download(r.url, None, offline)
        with tempfile.TemporaryDirectory() as t:
            sig = Path(t) / "file.sig"
            sig.write_bytes(_get(r.signature_url))
            verify_signature(archive, sig, Path(r.key), r.fingerprint)
        return archive.name
    raise FetchError("no-checksum", "the publisher gave no checksum or signature for this download, so I will not install it")


# ---- state -----------------------------------------------------------------------------------------------------------------------------

def _root(f: Floating) -> Path:
    return paths.tools_dir() / f.name


def installed_version(f: Floating) -> str:
    link = _root(f) / "current"
    return os.readlink(link) if link.is_symlink() else ""


def _binaries(f: Floating, arch: str) -> dict[str, str]:
    return {k: v.format(arch=arch, goarch=GOARCH.get(arch, arch)) for k, v in f.binaries.items()}


def is_installed(f: Floating) -> bool:
    v = installed_version(f)
    return bool(v) and (_root(f) / v).is_dir() and all(os.path.lexists(paths.bin_dir() / n) for n in f.binaries)


_FRESH = False


@contextlib.contextmanager
def looking_fresh():
    """Inside this, a look for a newer release is always made: a person asked for the kit by name, or an update is running."""
    global _FRESH
    was, _FRESH = _FRESH, True
    try:
        yield
    finally:
        _FRESH = was


# ---- installing ------------------------------------------------------------------------------------------------------------------------

def _own_env() -> tuple[dict, str]:
    """ws-host's own Node and uv, which it pins, first on PATH; and the name of the provider that pins them. Where ws-host has no toolchain of its own to give
    (a wheel, a test), the Node and uv already on PATH are used, and nothing is lost but the guarantee of which version."""
    from ..lib import provider as prov, toolchain as tc
    p = prov.load(paths.repo_root())
    if p is not None:
        wanted = [n for n in ("node", "uv", "python") if n in p.entries]
        try:
            tc.ensure(p, wanted)
            return tc.environment(p), p.name
        except tc.ToolchainError:
            pass
    return dict(os.environ), ""


def _run(argv: list[str], env: dict | None = None, cwd: Path | None = None, what: str = "") -> None:
    p = subprocess.run(argv, capture_output=True, text=True, env=env, cwd=str(cwd) if cwd else None)
    if p.returncode != 0:
        tail = " ".join((p.stderr or p.stdout).strip().splitlines()[-3:])
        raise FetchError("install-step", f"{what or ' '.join(argv[:2])} failed: {tail}")


def _wrapper(name: str, script: Path, provider: str) -> str:
    launcher = paths.repo_root() / "ws-host"
    if not provider:
        return f'#!/bin/sh\nexec "{script}" "$@"\n'
    return ("#!/bin/sh\n"
            f"# written by ws-host: runs {name} with ws-host's own Node first on PATH, wherever that Node is now\n"
            f'WSH="$(command -v ws-host || echo \'{launcher}\')"\n'
            f'exec "$WSH" provider run {provider} -- "{script}" "$@"\n')


def _install_package(f: Floating, r: Resolved, target: Path, arch: str) -> dict[str, str]:
    """A package into a folder of its own, built where it will stay; returns the binaries to link."""
    env, provider = _own_env()
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    if f.manager == "npm":
        npm = shutil.which("npm", path=env["PATH"])
        if not npm:
            raise FetchError("no-npm", "ws-host's Node has no npm")
        _run([npm, "install", "--prefix", str(target), "--no-audit", "--no-fund", "--loglevel=error", f"{f.package}@{r.version}"], env=env, what=f"npm install {f.package}")
        lock = target / "node_modules" / ".package-lock.json"
        if r.integrity and lock.is_file():
            held = (json.loads(lock.read_text()).get("packages", {}).get(f"node_modules/{f.package}") or {}).get("integrity")
            if held and held != r.integrity:
                raise FetchError("integrity", f"npm installed {f.package} {r.version} with a different integrity than the registry states; nothing was installed")
        (target / "bin").mkdir()
        out = {}
        # The package's own program starts with `#!/usr/bin/env node`; a person's terminal may have no Node, so what is linked asks ws-host to run it with its own.
        for name in f.binaries:
            w = target / "bin" / name
            w.write_text(_wrapper(name, _root(f) / "current" / "node_modules" / ".bin" / name, provider))
            w.chmod(0o755)
            out[name] = f"bin/{name}"
        return out
    if f.manager == "pip":
        uv = shutil.which("uv", path=env["PATH"])
        if not uv:
            raise FetchError("no-uv", "ws-host's toolchain has no uv")
        try:        # a Python of uv's own stays put when ws-host's pinned Python moves on; failing that (no way to fetch one), any Python that is new enough
            _run([uv, "venv", "--python", "3.12", "--managed-python", "--quiet", str(target)], env=env, what="uv venv")
        except FetchError:
            shutil.rmtree(target, ignore_errors=True)
            target.mkdir(parents=True)
            _run([uv, "venv", "--python", ">=3.10", "--quiet", str(target)], env=env, what="uv venv")
        _run([uv, "pip", "install", "--quiet", "--python", str(target / "bin" / "python"), f"{f.package}=={r.version}"], env=env, what=f"uv pip install {f.package}")
        return _binaries(f, arch)
    raise FetchError("unknown-manager", f"I do not know how to install a {f.manager!r} package")


def _install_in_place(f: Floating, conc: Download, target: Path, archive: Path) -> None:
    """A tool whose own installer writes absolute paths: unpack it, run the installer into the folder it will stay in."""
    src = _root(f) / f"{conc.version}.src"
    shutil.rmtree(target, ignore_errors=True)
    shutil.rmtree(src, ignore_errors=True)
    target.mkdir(parents=True)
    try:
        fetch._unpack(archive, conc, src)
        for step in f.steps:
            _run([s.format(src=str(src), dest=str(target)) for s in step], cwd=src, what=" ".join(step[:1]))
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(src, ignore_errors=True)


def _locate(target: Path, wanted: dict[str, str]) -> dict[str, str]:
    """Where each program is in what was unpacked: the shallowest executable file with one of the names it may have."""
    found: dict[str, str] = {}
    files = [p for p in target.rglob("*") if p.is_file() and not p.is_symlink()]
    for link, names in wanted.items():
        cands = names.split("|")
        hits = sorted((p for p in files if p.name in cands and os.access(p, os.X_OK)), key=lambda p: (len(p.relative_to(target).parts), cands.index(p.name)))
        if not hits:
            raise FetchError("no-program", f"{link} is not in what the release holds, so I installed nothing")
        found[link] = str(hits[0].relative_to(target))
    return found


def _install_auto(f: Floating, conc: Download, target: Path, archive: Path) -> None:
    """A release file chosen by its name: unpack it where it will stay and find the programs in it."""
    shutil.rmtree(target, ignore_errors=True)
    wanted = dict(conc.binaries)
    try:
        if conc.kind == "file":                      # one program, kept under the name it is linked by
            conc.binaries = {k: k for k in wanted}
            fetch._unpack(archive, conc, target)
        else:
            fetch._unpack(archive, conc, target)
            conc.binaries = _locate(target, wanted)
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise


def _prune(f: Floating, keep: set[str]) -> None:
    root = _root(f)
    versions = sorted((p for p in root.iterdir() if p.is_dir() and not p.is_symlink() and not p.name.endswith((".src", ".partial"))), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in versions[KEEP_VERSIONS:]:
        if old.name not in keep:
            shutil.rmtree(old, ignore_errors=True)


def install(f: Floating, offline: bool = False, fresh: bool | None = None) -> dict:
    """Install the newest version if none is installed, and, only when asked (`kit sync`, `ws-host update --tools`, `kit add`, which set `fresh`), look for a newer one. What is installed is never
    looked into otherwise, so that an ordinary update stays quick; a look that cannot be made leaves what is installed alone and is not an error."""
    arch = fetch.arch()
    if not f.supports(arch):
        raise FetchError("unsupported-arch", f"{f.name} is not available for {arch}")
    fresh = (_FRESH or os.environ.get("WS_HOST_KITS_FRESH") == "1") if fresh is None else fresh
    have = installed_version(f)
    ok = is_installed(f)
    if ok and (offline or not fresh):
        return {"name": f.name, "version": have, "outcome": "present"}
    if offline:
        raise FetchError("offline", f"{f.name} is needed and you are offline")
    try:
        with progress.step(f"🔎 Looking for the newest {f.name}", announce=not offline):
            r = f.resolve(arch)
    except FetchError as e:
        if ok:
            return {"name": f.name, "version": have, "outcome": "present", "note": f"I could not look for a newer {f.name} ({e.message}); what is installed is kept."}
        raise
    if ok and r.version == have:
        return {"name": f.name, "version": have, "outcome": "present"}
    if offline:
        raise FetchError("offline", f"{f.name} is needed and you are offline")
    target = _root(f) / r.version
    conc = Download(f.name, r.version, r.url, {arch: r.sha256 or "-"}, binaries=_binaries(f, arch), kind=r.kind or f.kind, strip=0 if f.auto else f.strip, steps=() if f.in_place or f.auto else f.steps)
    _root(f).mkdir(parents=True, exist_ok=True)
    if f.manager:
        with progress.step(f"📦 Installing {f.name} {r.version}", announce=not offline):
            conc.binaries = _install_package(f, r, target, arch)
    else:
        label = f"📥 Downloading {f.name} {r.version}"
        with progress.step(label, announce=not offline):
            sha = _fetch_checked(r, offline)
        conc.sha256 = {arch: sha}
        if f.in_place:
            with progress.step(f"📦 Installing {f.name} {r.version}", announce=not offline):
                _install_in_place(f, conc, target, fetch.download(r.url, sha, offline))
        elif f.auto:
            _install_auto(f, conc, target, fetch.download(r.url, sha, offline))
    done = fetch.install(conc, offline)           # unpacks what is not in place yet, repoints `current`, links the programs
    _prune(f, {r.version, have})
    return {**done, "name": f.name, "version": r.version, "previous": have, "outcome": "updated" if have else "installed"}
