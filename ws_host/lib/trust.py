"""Trust: a link in the person's own data directory, the sites-available/sites-enabled pattern (0002 FR-012 to FR-015)."""
from __future__ import annotations

import os
from pathlib import Path

from ..core import config, env, paths
from . import git
from .repos import RepoId


def link_path(rid: RepoId) -> Path:
    return paths.enabled_dir() / rid.name


def record_path(rid: RepoId) -> Path:
    return paths.trust_dir() / f"{rid.host}__{rid.org}__{rid.name}.env"


def trusted_orgs(cfg: config.Config) -> set[str]:
    """From the person's own configuration only; no repository's file can add to it (FR-013)."""
    return set(cfg.words("WS_HOST_TRUSTED"))


def _links_here(rid: RepoId, cfg: config.Config) -> bool:
    link = link_path(rid)
    if not os.path.lexists(link):
        return False
    target = Path(os.path.normpath(link.parent / os.readlink(link))) if link.is_symlink() else None
    return target == rid.path(cfg) / ".workspaces-host"


def trust_state(rid: RepoId, cfg: config.Config) -> tuple[bool, str]:
    if _links_here(rid, cfg):
        return True, "you trusted it"
    if rid.org in trusted_orgs(cfg):
        return True, f"your configuration trusts {rid.org}"
    return False, "not trusted"


def grant(rid: RepoId, cfg: config.Config) -> None:
    link = link_path(rid)
    link.parent.mkdir(parents=True, exist_ok=True)
    target = rid.path(cfg) / ".workspaces-host"
    if os.path.lexists(link):
        if _links_here(rid, cfg):
            return
        raise FileExistsError(f"{link} already trusts a different repository named {rid.name}")
    home = paths.home()
    try:
        within = target.resolve().relative_to(home.resolve()) is not None and link.parent.resolve().relative_to(home.resolve()) is not None
    except ValueError:
        within = False
    os.symlink(os.path.relpath(target, link.parent) if within else str(target), link)
    rec = record_path(rid)
    rec.parent.mkdir(parents=True, exist_ok=True)
    rec.write_text(f"WS_HOST_TRUST_REPO={rid}\nWS_HOST_TRUST_COMMIT={git.out(rid.path(cfg), 'rev-parse', 'HEAD')}\n", encoding="utf-8")


def revoke(rid: RepoId, cfg: config.Config) -> bool:
    link = link_path(rid)
    had = _links_here(rid, cfg)
    if had:
        link.unlink()
    record_path(rid).unlink(missing_ok=True)
    return had


def kits_changed_since_trust(rid: RepoId, cfg: config.Config) -> bool | None:
    """True when `.workspaces-host/kits/` differs from the commit trust was granted at; None when unknown."""
    try:
        commit = env.load(record_path(rid)).get("WS_HOST_TRUST_COMMIT")
    except env.EnvError:
        return None
    if not commit:
        return None
    path = rid.path(cfg)
    if not (path / ".git").exists():
        return None
    p = git.run(path, "diff", "--quiet", commit, "--", ".workspaces-host/kits")
    if p.returncode == 1:
        return True
    if p.returncode != 0:
        return None
    return bool(git.run(path, "status", "--porcelain", "--", ".workspaces-host/kits").stdout.strip())
