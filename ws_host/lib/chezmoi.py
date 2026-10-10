"""The files ws-host manages for a person, kept by chezmoi (0010-managed-config).

ws-host owns a chezmoi source state (under its data folder) and writes it from code at every use, so it is a cache of what the code says
and never something a person edits. Each managed file is a chezmoi `modify_` script that runs `ws_host.lib.managed` on the file's
current text; chezmoi then does what it is good at: showing what would change (`cat`, `status`), proving a file current (`verify`)
and writing it only when it differs (`apply`). A person's own chezmoi, if they have one, is never read: ws-host passes its own
configuration, state and source on every call, and the `chezmoi` it runs is the one pinned here, fetched and verified like `mise`."""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from ..core import paths
from ..core.kit import Download
from ..core.resource import WsError
from ..install import fetch

VERSION = "2.73.0"          # the newest chezmoi these requirements were tested against: the oldest ws-host accepts, and what it installs when none is here
DOWNLOAD = Download("chezmoi", VERSION, "https://github.com/twpayne/chezmoi/releases/download/v{version}/chezmoi_{version}_linux_{goarch}.tar.gz",
                    {"x86_64": "b597729b687af4488a848240134cb633de8ca0f04e0d26d48f400ee2ac338ffa",
                     "aarch64": "abcb840401d3c1f2356e0f53f5d52aa10d10f572654d9626db9ad0ca4dc03355"}, kind="tar", strip=0)


class ChezmoiMissing(Exception):
    def __init__(self, message: str, offline: bool = False, too_old: bool = False):
        super().__init__(message)
        self.offline, self.too_old = offline, too_old


def version_of(exe: Path | str) -> tuple[int, ...] | None:
    """The version a chezmoi reports, as a tuple of numbers; None when it will not say."""
    try:
        p = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"version v?(\d+)\.(\d+)\.(\d+)", p.stdout)
    return tuple(int(x) for x in m.groups()) if m else None


MINIMUM = tuple(int(x) for x in VERSION.split("."))


def on_path() -> str | None:
    """The chezmoi a person already has: WS_HOST_CHEZMOI if they name one, else the first on their PATH."""
    named = os.environ.get("WS_HOST_CHEZMOI")
    if named:
        if not os.access(named, os.X_OK):
            raise ChezmoiMissing(f"WS_HOST_CHEZMOI names {named}, which is not an executable file")
        return named
    return shutil.which("chezmoi")


def _accept(exe: str) -> Path:
    v = version_of(exe)
    if v is not None and v < MINIMUM:
        raise ChezmoiMissing(f"the chezmoi at {exe} is version {'.'.join(map(str, v))}; ws-host needs {VERSION} or newer. Upgrade it with: chezmoi upgrade", too_old=True)
    return Path(exe)


def program(fetch_it: bool = False, offline: bool = False) -> Path:
    """The chezmoi to run: the person's own (WS_HOST_CHEZMOI, else PATH), which they may upgrade as they like, provided it is not older than VERSION.
    When there is none, the pinned release is fetched and verified, and installed as the person's own: a plain file in their bin folder, which ws-host
    never replaces afterwards."""
    have = on_path()
    if have:
        return _accept(have)
    mine = paths.bin_dir() / "chezmoi"
    if os.access(mine, os.X_OK):                      # installed earlier, and the person's bin folder is not on this PATH
        return _accept(str(mine))
    if not DOWNLOAD.supports(fetch.arch()):
        raise ChezmoiMissing(f"there is no chezmoi for {fetch.arch()}")
    if not fetch_it:
        raise ChezmoiMissing(f"chezmoi is not here yet", offline)
    if offline:
        raise ChezmoiMissing(f"chezmoi {VERSION} is not here, and I am not allowed to download it", True)
    try:
        fetch.install(DOWNLOAD, offline=offline)
    except fetch.FetchError as e:
        raise ChezmoiMissing(f"could not fetch chezmoi {VERSION}: {e.message}", offline)
    src = fetch.version_dir(DOWNLOAD) / "chezmoi"
    paths.bin_dir().mkdir(parents=True, exist_ok=True)
    tmp = paths.bin_dir() / ".chezmoi.new"
    shutil.copy2(src, tmp)
    os.replace(tmp, mine)                             # a copy, not a link into ws-host's store: `chezmoi upgrade` then works on the person's own file
    return mine


class OutsideHome(Exception):
    """A file to manage is not under the person's home folder, which is chezmoi's destination."""


@dataclass(frozen=True)
class Target:
    """One managed file: where it lives, what runs on it (a `ws_host.lib.managed` kind and its arguments), and a name a person can read."""
    name: str
    path: Path
    kind: str
    args: tuple[str, ...] = ()
    keep_existing: bool = False


def source_dir() -> Path:
    return paths.data_dir() / "chezmoi" / "source"


def _source_name(rel: Path) -> Path:
    """chezmoi's name for the modify script of `rel`: dot_ for a leading dot in every part, and modify_ on the file."""
    parts = [("dot_" + p[1:]) if p.startswith(".") else p for p in rel.parts]
    parts[-1] = "modify_" + parts[-1]
    return Path(*parts)


def _script(t: Target, also: tuple[Target, ...] = ()) -> str:
    """The modify script for a file; when several managed things share it (the prompt and the modern tools share a shell's startup file), one script runs them in turn."""
    root = Path(__file__).resolve().parents[2]
    if also:
        argv = [sys.executable, "-m", "ws_host.lib.managed", "chain", json.dumps([[x.kind, *x.args] for x in (t, *also)])]
    else:
        argv = [sys.executable, "-m", "ws_host.lib.managed", t.kind, *t.args]
    return ("#!/bin/sh\n# Written by `ws-host config ensure`; chezmoi runs it on the file's text. Do not edit: the next run rewrites it.\n"
            f"PYTHONPATH={shlex.quote(str(root))} PYTHONDONTWRITEBYTECODE=1 exec {' '.join(shlex.quote(a) for a in argv)}\n")


def render(targets: list[Target]) -> Path:
    """Write the source state for exactly these targets, replacing what was there."""
    src = source_dir()
    shutil.rmtree(src, ignore_errors=True)
    src.mkdir(parents=True)
    by_path: dict[Path, list[Target]] = {}
    for t in targets:
        by_path.setdefault(t.path, []).append(t)
    for group in by_path.values():
        t = group[0]
        try:
            rel = t.path.relative_to(paths.home())
        except ValueError:
            raise OutsideHome(str(t.path))
        f = src / _source_name(rel)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(_script(t, tuple(group[1:])), encoding="utf-8")
        f.chmod(0o755)
    return src


def _run(args: list[str], env_extra: dict[str, str] | None = None, offline: bool = False, stdin_ok: bool = True) -> subprocess.CompletedProcess:
    exe = program(fetch_it=True, offline=offline)
    state = paths.state_dir() / "chezmoi"
    state.mkdir(parents=True, exist_ok=True)
    config = state / "chezmoi.toml"
    if not config.exists():
        config.write_text("# ws-host's own chezmoi configuration: empty on purpose.\n", encoding="utf-8")
    base = [str(exe), "--source", str(source_dir()), "--destination", str(paths.home()), "--config", str(config),
            "--persistent-state", str(state / "state.boltdb"), "--cache", str(paths.cache_dir() / "chezmoi"), "--no-tty", "--no-pager", "--force"]
    env = {k: v for k, v in os.environ.items() if not k.startswith("CHEZMOI")}
    env.update(env_extra or {})
    return subprocess.run(base + args, capture_output=True, text=True, env=env, timeout=120, stdin=subprocess.DEVNULL)


def _env(t: Target) -> dict[str, str]:
    return {"WS_HOST_KEEP_BLOCK": "1" if t.keep_existing else "0"}


def would_be(t: Target, offline: bool = False) -> str:
    """The text the file would have after `apply`."""
    p = _run(["cat", str(t.path)], _env(t), offline)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout).strip()[-300:])
    return p.stdout


def current(t: Target) -> str:
    try:
        return t.path.read_text(encoding="utf-8")
    except OSError:
        return ""


def is_current(t: Target, offline: bool = False) -> bool:
    return would_be(t, offline) == current(t) and t.path.exists()


def apply(t: Target, offline: bool = False) -> str | None:
    """Make the file what the script says, keeping a copy of what was there first. Returns the backup's path, or None."""
    after = would_be(t, offline)
    before = current(t)
    if after == before and t.path.exists():
        return None
    backup = None
    real = t.path.resolve() if t.path.is_symlink() else t.path
    if real.exists():
        backup = paths.state_dir() / "backups" / f"{real.name}.{time.strftime('%Y%m%d-%H%M%S')}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(real, backup)
    real.parent.mkdir(parents=True, exist_ok=True)
    p = _run(["apply", str(t.path)], _env(t), offline)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout).strip()[-300:])
    return str(backup) if backup else None


def apply_targets(targets: list[Target], offline: bool = False) -> list[str | None]:
    """Write the source state for these targets and have chezmoi apply each; the backups' paths, in order."""
    try:
        render(targets)
        return [apply(t, offline) for t in targets]
    except ChezmoiMissing as e:
        raise WsError("missing-chezmoi", str(e), missing_plain(e), status="missing", exit_code=3)
    except OutsideHome as e:
        raise WsError("outside-home", f"{e} is not under your home folder", f"I only manage files under your home folder, and {e} is not.")
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        raise WsError("chezmoi", str(e), f"chezmoi could not change the file, so it was left as it was: {e}")


def missing_plain(e: ChezmoiMissing) -> str:
    if e.too_old:
        return f"{e} Then run this again."
    return ("I need a small tool called chezmoi to change your files safely, and " +
            ("I may not download it while you are offline. Run this again with a network." if e.offline else "I could not get it. Check your network and run this again."))
