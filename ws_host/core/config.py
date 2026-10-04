"""The person's configuration (0001-ws-host FR-008), read from their own files only."""
from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field
from pathlib import Path

from . import env, paths


# The keys a person's configuration may hold (0001-ws-host FR-008). The guide's file reference is generated from this.
KEYS = {
    "WS_HOST_GIT_NAME": "the name to put on your commits",
    "WS_HOST_GIT_EMAIL": "the email to put on your commits",
    "WS_HOST_WORKSPACES": "the folder repositories are copied under (default ~/workspaces)",
    "WS_HOST_GITLAB_HOSTS": "GitLab hosts you sign in to, space-separated",
    "WS_HOST_REPOS": "the repositories you work in, as host/org/repo, space-separated",
    "WS_HOST_TRUSTED": "organizations whose repositories you trust, space-separated; only your own file can set this",
}
# The keys a repository's own `.workspaces-host/ws-host.env` may hold (0001-ws-host, 0002-repositories-and-trust FR-002).
REPO_KEYS = {
    "WS_HOST_KIT": "the kit the repository's tools need",
    "WS_HOST_REPOS": "the repositories it is worked beside, as host/org/repo, space-separated",
    "WS_HOST_VERSION": "the release of ws-host the repository is pinned to, where it pins one",
}


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
