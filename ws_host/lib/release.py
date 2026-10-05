"""Building, checking and publishing a release (0007-releases): the wheel, the app tarball, the Workspaces Console package and their checksums.

Everything here is deterministic: a build of one commit gives byte-identical files, so a person can rebuild a release and compare it
with what was published. Standard library only; the programs it runs (`uv`, `node`, `npm`, `gh`) come from the repository's pinned toolchain
(`mise install --locked`) or the person's own sign-in."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .. import NAME, VERSION
from ..core import paths

EPOCH = 1580601600                      # 2020-02-02T00:00:00Z, the time every file in a release is given
ZIP_TIME = (2020, 2, 2, 0, 0, 0)
SUMS = "SHA256SUMS"
LAUNCHER = """#!/usr/bin/env python3
# ws-host, from a release's app tarball: the program, its library beside it, and nothing to install. Needs python3 (3.11 or later).
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ws_host.__main__ import run  # noqa: E402

run()
"""


class ReleaseError(Exception):
    """Something that stops a release, with the plain sentence to show and the one thing to do."""

    def __init__(self, code: str, message: str, plain: str, do: str | None = None):
        super().__init__(message)
        self.code, self.plain, self.do = code, plain, do


def root() -> Path:
    return paths.repo_root()


def console_dir() -> Path:
    return root() / "console"


def dist_dir() -> Path:
    return root() / "dist"


def names(version: str = VERSION) -> dict[str, str]:
    """The release's assets, by role (0007-releases FR-002)."""
    return {"app": f"ws-host-{version}.tar.gz", "wheel": f"ws_host-{version}-py3-none-any.whl",
            "console": f"workspaces-console-{version}.vsix", "sums": SUMS}


def tag(version: str = VERSION) -> str:
    return f"v{version}"


def console_manifest() -> dict:
    return json.loads((console_dir() / "package.json").read_text(encoding="utf-8"))


def version_problems() -> list[str]:
    """Every place a version is written must say the one version (0007-releases FR-001)."""
    out = []
    if not re.fullmatch(r"\d+\.\d+\.\d+", VERSION):
        out.append(f"ws_host/__init__.py says {VERSION!r}, which is not a version like 1.2.3")
    try:
        pkg = console_manifest()
    except (OSError, ValueError) as e:
        return out + [f"console/package.json cannot be read: {e}"]
    if pkg.get("version") != VERSION:
        out.append(f"console/package.json says {pkg.get('version')!r}, not {VERSION!r}")
    if pkg.get("name") != "workspaces-console":
        out.append(f"console/package.json is named {pkg.get('name')!r}, not 'workspaces-console'")
    return out


def need_program(name: str, hint: str) -> str:
    found = shutil.which(name)
    if not found:
        raise ReleaseError("missing-program", f"{name} is not on PATH", f"I need {name} to build a release, and it is not here. {hint}",
                           "mise install --locked")
    return found


def run(argv: list[str], cwd: Path, what: str, env: dict[str, str] | None = None, timeout: int = 900) -> str:
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout, env={**os.environ, **(env or {})})
    except subprocess.TimeoutExpired:
        raise ReleaseError("timeout", f"{what} took longer than {timeout // 60} minutes", f"{what} is taking very long. Nothing was published; run it again.")
    if p.returncode != 0:
        tail = " ".join((p.stderr or p.stdout).strip().splitlines()[-4:])
        raise ReleaseError("failed", f"{what} failed: {tail}", f"{what} failed: {tail}")
    return p.stdout


# ---- the wheel and the app tarball --------------------------------------------------------------------------------------------

def build_wheel(out: Path) -> Path:
    """`uv build --wheel`: hatchling, pinned in pyproject.toml, writes every file with the one fixed time."""
    uv = need_program("uv", "The repository's pinned toolchain has it.")
    run([uv, "build", "--wheel", "--out-dir", str(out), "--no-build-logs"], root(), "the wheel build", {"SOURCE_DATE_EPOCH": str(EPOCH)})
    wheel = out / names()["wheel"]
    if not wheel.is_file():
        raise ReleaseError("no-wheel", f"{wheel.name} was not made", "The wheel build finished but made no wheel.")
    return wheel


def _tar_entry(name: str, data: bytes | None, mode: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.mtime, info.uid, info.gid, info.uname, info.gname, info.mode = EPOCH, 0, 0, "", "", mode
    if data is None:
        info.type = tarfile.DIRTYPE
    else:
        info.size = len(data)
    return info


def build_app_tarball(wheel: Path, out: Path, version: str = VERSION) -> Path:
    """The wheel's own files laid out as a program that runs where it is unpacked: `bin/ws-host` and `lib/ws_host/`. Nothing else is in it,
    so the code is the wheel's code, byte for byte."""
    top = f"ws-host-{version}"
    files: dict[str, bytes] = {}
    with zipfile.ZipFile(wheel) as z:
        for info in z.infolist():
            if info.filename.startswith("ws_host/") and not info.is_dir():
                files[f"{top}/lib/{info.filename}"] = z.read(info)
    files[f"{top}/bin/ws-host"] = LAUNCHER.encode()
    dirs = sorted({"/".join(n.split("/")[:i]) for n in files for i in range(1, len(n.split("/")))})
    target = out / names(version)["app"]
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for d in dirs:
            tar.addfile(_tar_entry(d, None, 0o755))
        for n in sorted(files):
            tar.addfile(_tar_entry(n, files[n], 0o755 if n.endswith("/bin/ws-host") else 0o644), io.BytesIO(files[n]))
    with open(target, "wb") as f, gzip.GzipFile(filename="", mode="wb", fileobj=f, mtime=0, compresslevel=9) as gz:
        gz.write(raw.getvalue())
    return target


# ---- the Workspaces Console ---------------------------------------------------------------------------------------------------

L10N_CALL = re.compile(r"""(?<![\w.])t\(\s*(?:'((?:[^'\\\n]|\\.)*)'|"((?:[^"\\\n]|\\.)*)"|`([^`$]*)`)""")


def _unescape(raw: str) -> str:
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), raw).replace("\\'", "'").replace('\\"', '"').replace("\\n", "\n")


def l10n_messages(src: Path) -> list[str]:
    """Every message the code gives `t(...)`: its own English is the key, so a translation replaces the value."""
    found: set[str] = set()
    for p in sorted(src.rglob("*.ts")):
        for m in L10N_CALL.finditer(p.read_text(encoding="utf-8")):
            found.add(_unescape(next(g for g in m.groups() if g is not None)))
    return sorted(found)


def write_l10n(ext: Path) -> int:
    messages = l10n_messages(ext / "src")
    (ext / "l10n").mkdir(exist_ok=True)
    (ext / "l10n" / "bundle.l10n.json").write_text(json.dumps({m: m for m in messages}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(messages)


def normalize_zip(path: Path) -> None:
    """Rewrite a zip with the fixed time and fixed attributes, entries in their original order, so that the same inputs are the same bytes."""
    with zipfile.ZipFile(path) as z:
        entries = [(i, z.read(i)) for i in z.infolist()]
    tmp = path.with_suffix(path.suffix + ".new")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        for info, data in entries:
            n = zipfile.ZipInfo(info.filename, ZIP_TIME)
            n.compress_type, n.external_attr, n.create_system = zipfile.ZIP_DEFLATED, (0o644 << 16) | (0o40000 << 16 if info.is_dir() else 0), 3
            out.writestr(n, data)
    os.replace(tmp, path)


def build_console(out: Path, tests: bool = True) -> tuple[Path, list[dict]]:
    """Type-check, lint, test, bundle and pack the Console from its own npm lock (0007-releases FR-005, FR-006). Returns the package and the steps."""
    ext = console_dir()
    node = need_program("node", "The repository's pinned toolchain has it.")
    npm = need_program("npm", "The repository's pinned toolchain has it.")
    steps: list[dict] = []

    def step(label: str, argv: list[str], env: dict[str, str] | None = None) -> str:
        text = run(argv, ext, label, env)
        steps.append({"name": label, "status": "ok"})
        return text

    step("Install the Console's locked packages", [npm, "ci", "--ignore-scripts", "--no-audit", "--no-fund"])
    tsc = str(ext / "node_modules" / "typescript" / "bin" / "tsc")
    step("Type-check the Console (strict)", [node, tsc, "--noEmit", "--pretty", "false", "-p", "."])
    step("Type-check the Console's panel (strict)", [node, tsc, "--noEmit", "--pretty", "false", "-p", "src/webview"])
    step("Lint the Console (no warnings)", [node, str(ext / "node_modules" / "eslint" / "bin" / "eslint.js"), ".", "--max-warnings", "0"])
    if tests:
        step("Compile the Console's tests", [node, "esbuild.mjs", "test"])
        test_files = sorted(str(p.relative_to(ext)) for p in (ext / "out" / "test").glob("*.test.js"))
        text = step("Run the Console's unit tests", [node, "--test", "--test-reporter=tap", *test_files], {"NODE_OPTIONS": ""})
        counts = {k: int(m.group(1)) for k in ("tests", "pass", "fail", "skipped") if (m := re.search(rf"^# {k} (\d+)", text, re.M))}
        steps[-1]["plain"] = f"{counts.get('pass', 0)} of {counts.get('tests', 0)} passed, {counts.get('skipped', 0)} skipped"
    step("Bundle the Console", [node, "esbuild.mjs", "bundle"])
    steps.append({"name": "Write the translation bundle", "status": "ok", "plain": f"{write_l10n(ext)} messages"})
    target = out / names()["console"]
    step("Pack the Console", [node, str(ext / "node_modules" / "@vscode" / "vsce" / "vsce"), "package", "--no-dependencies", "--skip-license",
                              "--allow-missing-repository", "--no-rewrite-relative-links", "--out", str(target)])
    normalize_zip(target)
    return target, steps


# ---- checksums and the whole build ----------------------------------------------------------------------------------------------

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_sums(out: Path) -> Path:
    n = names()
    lines = [f"{sha256(out / n[k])}  {n[k]}\n" for k in ("app", "wheel", "console")]
    (out / SUMS).write_text("".join(lines), encoding="utf-8")
    return out / SUMS


def read_sums(out: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in (out / SUMS).read_text(encoding="utf-8").splitlines():
        m = re.fullmatch(r"([0-9a-f]{64})  (\S+)", line)
        if m:
            found[m.group(2)] = m.group(1)
    return found


def build(out: Path, tests: bool = True) -> list[dict]:
    """Make every asset of the release into `out` (empty first), then its checksums. Raises ReleaseError."""
    problems = version_problems()
    if problems:
        raise ReleaseError("version", "; ".join(problems), "The version is not the same everywhere: " + "; ".join(problems) + ".")
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    steps: list[dict] = []
    wheel = build_wheel(out)
    steps.append({"name": "Build the wheel", "status": "ok", "plain": wheel.name})
    app = build_app_tarball(wheel, out)
    steps.append({"name": "Make the app tarball from the wheel's files", "status": "ok", "plain": app.name})
    _vsix, console_steps = build_console(out, tests)
    steps += console_steps
    write_sums(out)
    steps.append({"name": "Write the checksums", "status": "ok", "plain": SUMS})
    return steps


# ---- checking -------------------------------------------------------------------------------------------------------------------

@dataclass
class Finding:
    name: str
    ok: bool
    plain: str


def check(out: Path, rebuild: bool = False) -> list[Finding]:
    """What a release must be before it is published (0007-releases FR-007 to FR-013). Never writes outside temporary directories."""
    n = names()
    found: list[Finding] = []

    def add(name: str, ok: bool, plain: str) -> None:
        found.append(Finding(name, ok, plain))

    problems = version_problems()
    add("One version everywhere", not problems, "; ".join(problems) or f"{VERSION} in ws_host and the Console")
    missing = [v for v in n.values() if not (out / v).is_file()]
    add("Every asset is there", not missing, ("missing: " + ", ".join(missing)) if missing else ", ".join(n.values()))
    if missing:
        return found
    sums = read_sums(out)
    bad = [k for k in ("app", "wheel", "console") if sums.get(n[k]) != sha256(out / n[k])]
    add("The checksums match", not bad, ("they differ for " + ", ".join(n[k] for k in bad)) if bad else "SHA256SUMS lists all three and each matches")
    if bad:
        return found       # what the files hold is not what was built, so reading them proves nothing
    with zipfile.ZipFile(out / n["wheel"]) as z:
        wnames = set(z.namelist())
        meta = z.read(next(x for x in wnames if x.endswith("METADATA"))).decode()
    add("The wheel names this version", f"Version: {VERSION}" in meta and "Requires-Dist" not in meta, "metadata says " + VERSION + " and needs no package")
    with zipfile.ZipFile(out / n["console"]) as z:
        v = set(z.namelist())
        pkg = json.loads(z.read("extension/package.json"))
    must = {"extension/dist/extension.js", "extension/dist/webview.js", "extension/media/icon.png", "extension/l10n/bundle.l10n.json"}
    leaks = sorted(x for x in v if x.startswith(("extension/src/", "extension/test/", "extension/node_modules/")) or x.endswith(".map") or x.endswith("package-lock.json"))
    add("The Console package holds what it runs and nothing else", must <= v and not leaks and pkg.get("version") == VERSION,
        ("missing " + ", ".join(sorted(must - v))) if not must <= v else ("leaks " + ", ".join(leaks[:3])) if leaks else f"{len(v)} files, version {pkg.get('version')}")
    with tempfile.TemporaryDirectory(prefix="ws-host-release-") as tmp:
        t = Path(tmp)
        with tarfile.open(out / n["app"]) as tar:
            tar.extractall(t, filter="data")
        env = {**os.environ, "HOME": str(t / "home"), "PYTHONDONTWRITEBYTECODE": "1"}
        env.pop("PYTHONPATH", None)
        p = subprocess.run([str(t / f"ws-host-{VERSION}" / "bin" / "ws-host"), "--version"], capture_output=True, text=True, env=env, timeout=120)
        add("The app tarball runs where it is unpacked", p.returncode == 0 and VERSION in p.stdout, (p.stdout or p.stderr).strip().splitlines()[0] if (p.stdout or p.stderr).strip() else "no output")
        q = subprocess.run([str(t / f"ws-host-{VERSION}" / "bin" / "ws-host"), "command", "list", "--json"], capture_output=True, text=True, env=env, timeout=120)
        try:
            count = len(json.loads(q.stdout)["data"]["commands"])
        except (ValueError, KeyError, TypeError):
            count = 0
        add("It finds its commands", count > 0, f"{count} commands")
    if rebuild:
        with tempfile.TemporaryDirectory(prefix="ws-host-rebuild-") as tmp:
            try:
                build(Path(tmp) / "again", tests=False)
            except ReleaseError as e:
                add("A rebuild gives the same bytes", False, e.plain)
            else:
                diff = [n[k] for k in ("app", "wheel", "console") if sha256(Path(tmp) / "again" / n[k]) != sha256(out / n[k])]
                add("A rebuild gives the same bytes", not diff, ("different: " + ", ".join(diff)) if diff else "all three are byte-identical")
    return found


# ---- publishing -----------------------------------------------------------------------------------------------------------------

def git(*args: str) -> str:
    p = subprocess.run(["git", *args], cwd=root(), capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else ""


def publish_problems(out: Path) -> list[str]:
    """What must be true before anything is uploaded (0007-releases FR-008): a clean tree, a pushed commit, a new tag, a checked release."""
    out_problems = []
    if git("status", "--porcelain"):
        out_problems.append("there are changes that are not committed")
    head = git("rev-parse", "HEAD")
    if not head:
        out_problems.append("this is not a git clone")
    elif not git("branch", "-r", "--contains", head):
        out_problems.append("this commit has not been pushed")
    if git("tag", "--list", tag()):
        out_problems.append(f"the tag {tag()} already exists")
    failed = [f.name for f in check(out) if not f.ok] if out.is_dir() and (out / SUMS).is_file() else ["the release is not built"]
    if failed:
        out_problems.append("the release does not pass its checks (" + ", ".join(failed) + ")")
    return out_problems


def notes(out: Path) -> str:
    """The release's description: what each file is, and its checksum, which is what a consumer pins (0007-releases FR-010)."""
    n = names()
    s = read_sums(out)
    base = f"https://github.com/intellectual-frontiers/workspaces-host/releases/download/{tag()}"
    return "\n".join([
        f"ws-host {VERSION} and the Workspaces Console {VERSION}.", "",
        "| File | What it is | SHA-256 |", "|---|---|---|",
        f"| `{n['app']}` | the program and its library, unpacked and run where they are | `{s[n['app']]}` |",
        f"| `{n['wheel']}` | the same code as a Python wheel, for `uv tool install` | `{s[n['wheel']]}` |",
        f"| `{n['console']}` | the VS Code extension, for `code --install-extension` | `{s[n['console']]}` |", "",
        "Pin a file by its address and checksum; do not follow a tag. For mise:", "", "```toml",
        f'[tools."http:ws-host"]', f'version = "{VERSION}"', "strip_components = 1", 'bin_path = "bin"',
        '[tools."http:ws-host".platforms]', f'linux-x64 = {{ url = "{base}/{n["app"]}", checksum = "sha256:{s[n["app"]]}" }}',
        f'linux-arm64 = {{ url = "{base}/{n["app"]}", checksum = "sha256:{s[n["app"]]}" }}', "```", "",
        "A release is rebuilt with `ws-host release check --rebuild` and must give the same checksums.", ""])


def publish(out: Path) -> str:
    """Create the tag and the GitHub release with its assets, with the person's own `gh` sign-in. Returns gh's output (the release address)."""
    gh = need_program("gh", "Install it with `ws-host kit add base`, then sign in with `ws-host auth new github`.")
    n = names()
    with tempfile.TemporaryDirectory(prefix="ws-host-notes-") as tmp:
        nf = Path(tmp) / "notes.md"
        nf.write_text(notes(out), encoding="utf-8")
        return run([gh, "release", "create", tag(), *(str(out / v) for v in n.values()), "--title", f"{NAME} {VERSION}", "--notes-file", str(nf),
                    "--target", git("rev-parse", "HEAD")], root(), "creating the GitHub release", timeout=900)
