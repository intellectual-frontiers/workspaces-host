"""Where a person's files live (0001-ws-host FR-007): XDG conventions, read from the environment at each call."""
from __future__ import annotations

import os
from pathlib import Path

APP = "workspaces-host"


def home() -> Path:
    return Path(os.environ.get("HOME") or os.path.expanduser("~"))


def _xdg(var: str, default: str) -> Path:
    v = os.environ.get(var)
    return Path(v) if v and os.path.isabs(v) else home() / default


def config_dir() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config") / APP


def data_dir() -> Path:
    return _xdg("XDG_DATA_HOME", ".local/share") / APP


def state_dir() -> Path:
    return _xdg("XDG_STATE_HOME", ".local/state") / APP


def cache_dir() -> Path:
    return _xdg("XDG_CACHE_HOME", ".cache") / APP


def bin_dir() -> Path:
    return home() / ".local" / "bin"


def config_file() -> Path:
    return config_dir() / "ws-host.env"


def secrets_file() -> Path:
    return config_dir() / "secrets.env"


def tools_dir() -> Path:
    return data_dir() / "tools"


def enabled_dir() -> Path:
    return data_dir() / "enabled"


def logs_dir() -> Path:
    return state_dir() / "logs"


def trust_dir() -> Path:
    return state_dir() / "trust"


def repo_root() -> Path:
    """The clone this code runs from."""
    return Path(__file__).resolve().parents[2]
