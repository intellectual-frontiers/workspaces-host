"""The person's configuration (0001-ws-host FR-008), read from their own files only."""
from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field
from pathlib import Path

from . import env, paths


@dataclass
class Config:
    values: dict[str, str] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    def get(self, key: str, default: str = "") -> str:
        return self.values.get(key, default)

    def words(self, key: str) -> list[str]:
        return env.words(self.values.get(key))

    @property
    def workspaces(self) -> Path:
        v = self.values.get("WS_HOST_WORKSPACES")
        if v:
            return Path(os.path.expanduser(v))
        return paths.home() / "workspaces"


def load() -> Config:
    cfg = Config()
    try:
        cfg.values.update(env.load(paths.config_file()))
    except env.EnvError as e:
        cfg.problems.append(f"{paths.config_file()}: {e}")
    return cfg


def secrets_mode_problem() -> str | None:
    """None when secrets.env is absent or readable only by its owner."""
    f = paths.secrets_file()
    try:
        mode = stat.S_IMODE(f.stat().st_mode)
    except FileNotFoundError:
        return None
    if mode & 0o077:
        return f"{f} can be read by others (mode {mode:o}); run: chmod 600 {f}"
    return None


def load_secrets() -> dict[str, str]:
    """The secrets, refused unless only the owner can read the file."""
    if secrets_mode_problem():
        return {}
    try:
        return env.load(paths.secrets_file())
    except env.EnvError:
        return {}
