"""The `mise` ws-host installs programs with (0008-providers FR-006 to FR-008): one exact version, fetched and verified by ws-host itself, run in
safe mode from a configuration and a store that are ws-host's own."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ..core import paths
from ..core.kit import Download
from ..install import fetch



def _pins() -> dict[str, str]:
    """ws_host/bootstrap.env: the one place the launcher and this module read mise's version and checksums from."""
    out = {}
    for line in (Path(__file__).resolve().parents[1] / "bootstrap.env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


PINS = _pins()
VERSION = PINS["MISE_VERSION"]
_URL = "https://mise.jdx.dev/v{version}/mise-v{version}-linux-%s.tar.xz"
DOWNLOADS = {
    "x86_64": Download("mise", VERSION, _URL % "x64", {"x86_64": PINS["MISE_SHA256_X86_64"]}, kind="tar", strip=1),
    "aarch64": Download("mise", VERSION, _URL % "arm64", {"aarch64": PINS["MISE_SHA256_AARCH64"]}, kind="tar", strip=1),
}


class MiseMissing(Exception):
    """`mise` is not here and could not be fetched."""

    def __init__(self, message: str, offline: bool = False):
        super().__init__(message)
        self.offline = offline


def download() -> Download:
    d = DOWNLOADS.get(fetch.arch())
    if d is None:
        raise MiseMissing(f"there is no mise for {fetch.arch()}")
    return d


def named() -> Path | None:
    v = os.environ.get("WS_HOST_MISE")
    return Path(v) if v else None


def program(fetch_it: bool = False, offline: bool = False) -> Path:
    """The mise to run: the one named in WS_HOST_MISE, else the pinned release in ws-host's own tools folder, fetched first when asked."""
    n = named()
    if n is not None:
        if not os.access(n, os.X_OK):
            raise MiseMissing(f"WS_HOST_MISE names {n}, which is not an executable file")
        return n
    d = download()
    exe = fetch.version_dir(d) / "bin" / "mise"
    if exe.is_file():
        return exe
    if not fetch_it:
        raise MiseMissing(f"mise {VERSION} is not here yet", offline)
    if offline:
        raise MiseMissing(f"mise {VERSION} is not here, and I am not allowed to download it", True)
    try:
        fetch.install(d, offline=offline)
    except fetch.FetchError as e:
        raise MiseMissing(f"could not fetch mise {VERSION}: {e.message}", offline)
    return exe


def data_dir() -> Path:
    return paths.data_dir() / "mise" / "data"


def environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    """The environment `mise` runs in: ws-host's own configuration, state, cache and store, safe mode, and nothing from a repository."""
    config = paths.state_dir() / "mise" / "config"
    config.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    for k in [k for k in env if k.startswith("MISE_")]:
        del env[k]
    env.update({"MISE_DATA_DIR": str(data_dir()), "MISE_CACHE_DIR": str(paths.cache_dir() / "mise"), "MISE_STATE_DIR": str(paths.state_dir() / "mise" / "state"),
                "MISE_CONFIG_DIR": str(config), "MISE_SAFE": "1", "MISE_YES": "1",
                "NO_COLOR": "1", "MISE_QUIET": "1"})
    env.update(extra or {})
    return env


def run(args: list[str], mise_dir: Path, offline: bool = False, fetch_it: bool = True, timeout: int = 1800) -> subprocess.CompletedProcess:
    """`mise -C <mise_dir> ARGS...`, searching for configuration in that folder only, never above it."""
    exe = program(fetch_it=fetch_it, offline=offline)
    env = environment({"MISE_CEILING_PATHS": str(mise_dir.parent)})
    if offline:
        env["MISE_OFFLINE"] = "1"
    return subprocess.run([str(exe), "-C", str(mise_dir), *args], capture_output=True, text=True, timeout=timeout, env=env)
