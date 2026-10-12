"""The providers in use on this computer (0008-providers FR-010): the ones a person enabled with `provider add` and the ones that need no enabling."""
from __future__ import annotations

import os
from pathlib import Path

from archon import paths
from archon.provider import FOLDER, Provider, load

from ..core import config
from . import repos, trust


def providers_dir() -> Path:
    return paths.config_dir() / "providers.d"


def explicit() -> list[Provider]:
    """The providers a person enabled with `provider add`: the links in their providers folder; a link that no longer leads to a provider is skipped."""
    out = []
    d = providers_dir()
    for link in sorted(d.iterdir()) if d.is_dir() else []:
        folder = Path(os.path.realpath(link))
        if folder.name != FOLDER:
            continue
        p = load(folder.parent)
        if p is not None and p.name == link.name:
            out.append(p)
    return out


def implicit() -> dict[str, tuple[Provider, str]]:
    """The providers that need no `provider add`, with why (0008-providers FR-010): the clone of ws-host that is running, which is the code the person
    installed, and every cloned repository the person trusts (0002 FR-012), which includes the organization ws-host itself comes from."""
    out: dict[str, tuple[Provider, str]] = {}
    if os.environ.get("WS_HOST_IMPLICIT") == "no":      # the tests' own homes, where nothing is in use until a test enables it
        return out
    own = load(paths.repo_root())
    if own is not None and not own.problems:
        out[own.name] = (own, "this is the ws-host you are running")
    try:
        cfg = config.load()
        for rid in sorted(repos.known(cfg)[0], key=str):
            if not (rid.path(cfg) / FOLDER / "provider.toml").is_file():
                continue
            ok, why = trust.trust_state(rid, cfg)
            p = load(rid.path(cfg)) if ok else None
            if p is not None and p.name not in out:
                out[p.name] = (p, why)
    except Exception:             # a broken configuration must not stop a provider that was enabled by hand
        pass
    return out


def enabled() -> list[Provider]:
    """Every provider in use, in name order: the ones a person enabled by hand, then those that need no enabling (see `implicit`); by hand wins a name."""
    by_name = {p.name: p for p in explicit()}
    for name, (p, _why) in implicit().items():
        by_name.setdefault(name, p)
    return [by_name[n] for n in sorted(by_name)]


def how_enabled(name: str) -> str:
    """Why a provider is in use, in plain words."""
    if any(p.name == name for p in explicit()):
        return "you enabled it"
    return implicit().get(name, (None, "not enabled"))[1]


def conflicts(providers: list[Provider]) -> list[str]:
    """Two providers declaring one entry name and version differently (0008-providers FR-009), one sentence for each pair."""
    seen: dict[tuple[str, str], tuple[str, str]] = {}
    out = []
    for p in sorted(providers, key=lambda x: x.name):
        for e in p.entries.values():
            key = (e.name, e.version)
            sig = e.signature()
            if key in seen and seen[key][1] != sig:
                out.append(f"{seen[key][0]} and {p.name} both declare {e.name} {e.version}, but not the same file; give one of them another name or version")
            seen.setdefault(key, (p.name, sig))
    return out


def get(name: str) -> Provider | None:
    for p in enabled():
        if p.name == name:
            return p
    return None
