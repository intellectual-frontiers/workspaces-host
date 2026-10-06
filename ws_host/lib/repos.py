"""Known repositories, their state, and updating them without harm (0002-repositories-and-trust)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..core import config, env, progress
from ..core.resource import Action, WsError
from . import git

ID_RX = re.compile(r"^([A-Za-z0-9.-]+)/([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+)$")
GITLAB_HOSTS_DEFAULT = ("gitlab.com",)


@dataclass(frozen=True)
class RepoId:
    host: str
    org: str
    name: str

    def __str__(self) -> str:
        return f"{self.host}/{self.org}/{self.name}"

    def path(self, cfg: config.Config) -> Path:
        return cfg.workspaces / self.host / self.org / self.name

    @property
    def url(self) -> str:
        return f"https://{self.host}/{self.org}/{self.name}"


def parse_id(text: str) -> RepoId | None:
    m = ID_RX.match(text.strip())
    return RepoId(*m.groups()) if m else None


def read_needs(path: Path) -> dict[str, str]:
    """A repository's `.workspaces-host/ws-host.env`: information, readable without trust (0041 FR-062)."""
    try:
        return env.load(path / ".workspaces-host" / "ws-host.env")
    except env.EnvError:
        return {}


def known(cfg: config.Config) -> tuple[dict[RepoId, list[str]], list[str]]:
    """Every known repository with what named it, and the entries that were not repository identifiers (0002 FR-002)."""
    found: dict[RepoId, list[str]] = {}
    invalid: list[str] = []
    queue: list[tuple[str, str]] = [(e, "your configuration") for e in cfg.repos()]
    while queue:
        entry, source = queue.pop(0)
        rid = parse_id(entry)
        if rid is None:
            invalid.append(f"{entry} (listed by {source})")
            continue
        first = rid not in found
        found.setdefault(rid, [])
        if source not in found[rid]:
            found[rid].append(source)
        if first:
            p = rid.path(cfg)
            if (p / ".git").exists():
                queue += [(e, str(rid)) for e in env.words(read_needs(p).get("WS_HOST_REPOS"))]
    return found, invalid


def resolve(cfg: config.Config, text: str) -> RepoId:
    """A full identifier, or `<org>/<repo>` or `<repo>` when exactly one known repository matches (FR-001)."""
    rid = parse_id(text)
    if rid:
        return rid
    every = list(known(cfg)[0])
    hits = [r for r in every if f"{r.org}/{r.name}" == text or r.name == text]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise WsError("unknown-repository", f"no known repository matches '{text}'",
                      f"I do not know a repository called '{text}'. Run `ws-host repo list` to see the ones I know.",
                      [Action(("repo", "list"), "See known repositories")], exit_code=2)
    raise WsError("ambiguous-repository", f"'{text}' matches {', '.join(map(str, hits))}",
                  f"'{text}' could mean more than one repository: {', '.join(map(str, hits))}. Use the full name.", exit_code=2)


def sign_in_action(rid: RepoId, cfg: config.Config) -> list[Action]:
    gitlab = set(cfg.words("WS_HOST_GITLAB_HOSTS")) | set(GITLAB_HOSTS_DEFAULT)
    if rid.host == "github.com":
        return [Action(("auth", "new"), "Sign in to GitHub", {"forge": "github"})]
    if rid.host in gitlab:
        return [Action(("auth", "new"), "Sign in to GitLab", {"forge": "gitlab", "host": rid.host})]
    return []


def clone(rid: RepoId, cfg: config.Config) -> dict:
    dest = rid.path(cfg)
    if (dest / ".git").exists():
        return {"id": str(rid), "path": str(dest), "outcome": "current", "status": "ok", "plain": f"{rid.name} is already here."}
    dest.parent.mkdir(parents=True, exist_ok=True)
    with progress.working(f"📂 Copying {rid.name}"):
        p = git.run(None, "clone", "--quiet", rid.url, str(dest))
    if p.returncode == 0:
        return {"id": str(rid), "path": str(dest), "outcome": "cloned", "status": "ok", "plain": f"Copied {rid.name} to {dest}."}
    why = git.reason(p)
    auth = git.is_auth_failure(p.stderr)
    return {"id": str(rid), "path": str(dest), "outcome": "failed", "status": "fail", "auth": auth,
            "plain": (f"I could not copy {rid.name}: you are not signed in to {rid.host}, or you cannot see it." if auth
                      else f"I could not copy {rid.name}."),
            "git": why}


def state(rid: RepoId, cfg: config.Config) -> dict:
    """What `repo status` reports for one repository, from local refs only."""
    path = rid.path(cfg)
    s = {"id": str(rid), "path": str(path), "cloned": (path / ".git").exists()}
    if not s["cloned"]:
        return {**s, "plain": f"{rid.name} is not copied yet."}
    branch = git.out(path, "symbolic-ref", "--short", "-q", "HEAD")
    upstream = git.out(path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    dirty = bool(git.run(path, "status", "--porcelain=v1", "--untracked-files=no").stdout.strip())
    ahead = behind = None
    if upstream:
        counts = git.out(path, "rev-list", "--left-right", "--count", "HEAD...@{u}").split()
        if len(counts) == 2:
            ahead, behind = int(counts[0]), int(counts[1])
    parts = []
    if dirty:
        parts.append("has changes you have not committed")
    if ahead:
        parts.append(f"{ahead} commit{'s' if ahead != 1 else ''} not pushed")
    if behind:
        parts.append(f"{behind} new commit{'s' if behind != 1 else ''} to fetch")
    return {**s, "branch": branch or None, "upstream": upstream or None, "ahead": ahead, "behind": behind, "dirty": dirty,
            "operation": git.operation_in_progress(path),
            "plain": f"{rid.name}: " + ("; ".join(parts) if parts else "nothing to do.")}


def _skip(rid: RepoId, why: str, detail: str | None = None) -> dict:
    r = {"id": str(rid), "outcome": "skipped", "status": "skip",
         "plain": f"Your changes in {rid.name} are safe. It was not updated because {why}."}
    if detail:
        r["git"] = detail
    return r


def sync(rid: RepoId, cfg: config.Config) -> dict:
    """Fetch, then fast-forward only; anything else leaves the repository exactly as it was (0002 FR-007 to FR-010)."""
    path = rid.path(cfg)
    if not (path / ".git").exists():
        return {"id": str(rid), "outcome": "missing", "status": "skip", "plain": f"{rid.name} is not copied yet, so there is nothing to update."}
    with progress.working(f"🔄 Checking {rid.name} for news"):
        f = git.run(path, "fetch", "--quiet")
    if f.returncode != 0:
        auth = git.is_auth_failure(f.stderr)
        return {"id": str(rid), "path": str(path), "outcome": "failed", "status": "fail", "auth": auth,
                "plain": (f"I could not check {rid.name} for news: you are not signed in to {rid.host}. Your copy was not touched."
                          if auth else f"I could not check {rid.name} for news. Your copy was not touched."),
                "git": git.reason(f)}
    op = git.operation_in_progress(path)
    if op:
        return _skip(rid, f"{op} is in progress in it")
    if not git.out(path, "symbolic-ref", "-q", "HEAD"):
        return _skip(rid, "it is not on a branch")
    if not git.out(path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"):
        return _skip(rid, "it is not connected to a shared branch")
    if git.run(path, "status", "--porcelain=v1", "--untracked-files=no").stdout.strip():
        return _skip(rid, "it has changes you have not committed yet")
    counts = git.out(path, "rev-list", "--left-right", "--count", "HEAD...@{u}").split()
    ahead, behind = int(counts[0]), int(counts[1])
    if ahead and behind:
        return _skip(rid, "your commits and the shared ones have both moved on, so they cannot be joined without your say-so")
    if not behind:
        note = f" It holds {ahead} commit{'s' if ahead != 1 else ''} you have not pushed yet; they are safe." if ahead else ""
        return {"id": str(rid), "path": str(path), "outcome": "current", "status": "ok", "ahead": ahead,
                "plain": f"{rid.name} is up to date.{note}"}
    m = git.run(path, "merge", "--ff-only", "--quiet", "@{u}")
    if m.returncode != 0:
        return _skip(rid, "git would have had to overwrite something of yours", git.reason(m))
    return {"id": str(rid), "path": str(path), "outcome": "updated", "status": "ok", "commits": behind,
            "plain": f"{rid.name} moved forward by {behind} commit{'s' if behind != 1 else ''}."}


def summarize(results: list[dict]) -> str:
    n = lambda o: sum(r["outcome"] == o for r in results)
    bits = []
    if n("cloned"):
        bits.append(f"copied {n('cloned')}")
    if n("updated"):
        bits.append(f"updated {n('updated')}")
    if n("current"):
        bits.append(f"{n('current')} already up to date")
    text = ("Done: " + ", ".join(bits) + ".") if bits else "Nothing needed doing."
    if n("skipped") or n("missing"):
        k = n("skipped") + n("missing")
        text += f" {k} left alone to keep your work safe."
    if n("failed"):
        text += f" {n('failed')} could not be reached."
    return text
