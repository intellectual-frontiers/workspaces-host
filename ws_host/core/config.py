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
    "WS_HOST_REPOS": "the repositories you work in, as host/org/repo, space-separated (the two starter repositories when you say nothing)",
    "WS_HOST_KIT": "kits to install for you whatever your repositories ask, space-separated (base, shell and embedded-sql when you say nothing; empty for none)",
    "WS_HOST_PROMPT": "the prompt setup gives bash and fish: pretty when you say nothing (needs a Nerd Font), plain (emoji and box lines only), or no to keep your own",
    "WS_HOST_MODERN": "whether setup makes bash, fish and git use the modern tools (eza, bat, zoxide, delta): yes when you say nothing, no to keep the old commands",
    "WS_HOST_PROVIDERS": "whether VS Code setup asks to enable the repositories that declare themselves providers: yes when you say nothing, no to enable them yourself",
    "WS_HOST_TRUSTED": "organizations whose repositories you trust, space-separated; only your own file can set this (intellectual-frontiers, the organization ws-host itself comes from, when you say nothing; empty to trust none)",
}
# The keys a repository's own `.workspaces-host/ws-host.env` may hold (0001-ws-host, 0002-repositories-and-trust FR-002).
REPO_KEYS = {
    "WS_HOST_KIT": "the kit the repository's tools need",
    "WS_HOST_REPOS": "the repositories it is worked beside, as host/org/repo, space-separated",
    "WS_HOST_VERSION": "the release of ws-host the repository is pinned to, where it pins one",
}


# The repositories a person gets until they choose their own: the shared public examples and this tool (0006-onboarding FR-010).
DEFAULT_KITS = ("base", "shell", "embedded-sql")       # the everyday tools, and a terminal that is a pleasure to look at (0006-onboarding FR-004, FR-022)
STARTER_REPOS = ("github.com/intellectual-frontiers/.github", "github.com/intellectual-frontiers/workspaces-host")


@dataclass
class Config:
    values: dict[str, str] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    def get(self, key: str, default: str = "") -> str:
        return self.values.get(key, default)

    def words(self, key: str) -> list[str]:
        return env.words(self.values.get(key))

    def repos(self) -> list[str]:
        """The repositories the person lists, or the starter repositories until their own file says otherwise."""
        return self.words("WS_HOST_REPOS") if "WS_HOST_REPOS" in self.values else list(STARTER_REPOS)

    def kits(self) -> list[str]:
        """The kits the person always wants: base and shell unless their own file says otherwise (0006-onboarding FR-004)."""
        return self.words("WS_HOST_KIT") if "WS_HOST_KIT" in self.values else list(DEFAULT_KITS)

    def prompt_theme(self) -> str | None:
        """The theme setup gives the shells: ws-host-pretty, ws-host-plain, or None when the person keeps their own prompt (FR-022)."""
        v = self.get("WS_HOST_PROMPT", "pretty").strip().lower()
        if v in ("no", "false", "0", "off", "none"):
            return None
        return "ws-host-plain" if v == "plain" else "ws-host-pretty"

    def modern(self) -> bool:
        """Whether setup makes the shells and git use the modern tools (0003-kits FR-019): yes unless the person says no."""
        return self.get("WS_HOST_MODERN", "yes").strip().lower() not in ("no", "false", "0", "off", "none")

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


def add_repo(identifier: str) -> bool:
    """Put a repository on the person's own list, keeping every other line of their file. True when it was added."""
    cfg = load()
    current = cfg.repos()
    if identifier in current:
        return False
    new = " ".join(current + [identifier])
    f = paths.config_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    lines = f.read_text(encoding="utf-8").splitlines() if f.exists() else []
    out, done = [], False
    for ln in lines:
        if ln.strip().startswith("WS_HOST_REPOS="):
            out.append(f'WS_HOST_REPOS="{new}"')
            done = True
        else:
            out.append(ln)
    if not done:
        out.append(f'WS_HOST_REPOS="{new}"')
    tmp = f.with_suffix(".env.new")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.replace(tmp, f)
    return True
