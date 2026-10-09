"""Looking for news everywhere an update would change something (0006-onboarding FR-026): ws-host's own copy and every repository copied here.

A look is a quiet `git fetch` of each and a count of what is new; it moves nothing. The answer is kept for a few minutes so that several windows
asking at once cost one trip to the network. Standard library only."""
from __future__ import annotations

import json
import subprocess
import time

from ..core import paths
from . import git, repos, selfupdate

FRESH_SECONDS = 300             # an answer this young is given again without asking the network
FETCH_SECONDS = 45              # one repository that is slow does not hold the look up for long


def looked_file():
    return paths.state_dir() / "update-looked.json"


def _cached(max_age: float) -> dict | None:
    try:
        f = looked_file()
        if time.time() - f.stat().st_mtime <= max_age:
            return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return None


def _behind(path, fetch: bool) -> tuple[int, str]:
    """How many commits the shared branch has that this copy lacks, and why it is not known when it is not."""
    if not (path / ".git").exists():
        return 0, ""
    if not git.out(path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"):
        return 0, "not connected to a shared branch"
    if fetch:
        try:
            f = git.run(path, "fetch", "--quiet", timeout=FETCH_SECONDS)
        except subprocess.TimeoutExpired:
            return 0, "slow to answer"
        if f.returncode != 0:
            return 0, "could not be reached"
    counts = git.out(path, "rev-list", "--left-right", "--count", "HEAD...@{u}").split()
    return (int(counts[1]) if len(counts) == 2 else 0), ""


def sentence(items: list[dict]) -> str:
    """The one line a person reads, naming what is new."""
    names = [i["name"] for i in items]
    if not names:
        return "Everything is up to date."
    if names == ["ws-host"]:
        n = items[0]["behind"]
        return f"A newer ws-host is ready ({n} change{'s' if n != 1 else ''}). Update it with:  ws-host update"
    return f"Updates are ready for {', '.join(names)}. Bring everything up to date with:  ws-host update"


def look(cfg, offline: bool = False, max_age: float = 0) -> dict:
    """{waiting, items: [{name, path, behind}], unreachable, plain, looked}; writes the note new terminal windows show."""
    if max_age:
        hit = _cached(max_age)
        if hit is not None:
            return {**hit, "cached": True}
    fetch = not offline
    root = selfupdate.root()
    targets = [("ws-host", root)]
    found, _ = repos.known(cfg)
    for rid in sorted(found, key=str):
        p = rid.path(cfg)
        if p.resolve() != root.resolve():
            targets.append((rid.name, p))
    items, unreachable = [], []
    for name, p in targets:
        n, why = _behind(p, fetch)
        if why and why != "not connected to a shared branch":
            unreachable.append(name)
        if n:
            items.append({"name": name, "path": str(p), "behind": n})
    out = {"waiting": bool(items), "items": items, "unreachable": unreachable, "plain": sentence(items), "looked": int(time.time()), "cached": False}
    paths.state_dir().mkdir(parents=True, exist_ok=True)
    if len(unreachable) < len(targets):                 # a look from local refs alone (offline) is as true as the refs, and clears what has since been settled
        if fetch:
            selfupdate.checked_file().touch()
        if items:
            selfupdate.notice_file().write_text(out["plain"] + "\n", encoding="utf-8")
        elif not unreachable:                    # a note is cleared only when everything was seen
            selfupdate.notice_file().unlink(missing_ok=True)
        looked_file().write_text(json.dumps(out), encoding="utf-8")
    return out


def settle(cfg) -> None:
    """A command has just changed what a repository holds (a refresh, a sync, an update): make the note and the remembered answer true of it now, from local history,
    so that nothing goes on saying news waits that has since been brought in or put aside."""
    try:
        look(cfg, offline=True)
    except Exception:                    # the note is a convenience; it must never make the command that called it fail
        pass
