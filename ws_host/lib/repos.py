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


_TRAILERS = ("co-authored-by:", "claude-session:", "signed-off-by:", "reviewed-by:", "https://claude.ai/")


def _why(body: str) -> str:
    """What a commit says about why it was made: the first paragraph of its message after the subject, without the trailers tools append."""
    paras, cur = [], []
    for line in body.splitlines():
        if line.strip().lower().startswith(_TRAILERS):
            continue
        if line.strip():
            cur.append(line.strip())
        elif cur:
            paras.append(" ".join(cur))
            cur = []
    if cur:
        paras.append(" ".join(cur))
    text = paras[0] if paras else ""
    return text if len(text) <= 400 else text[:397].rstrip() + "..."


def _area(path: str) -> str:
    parts = path.split("/")
    return "/".join(parts[:2]) if len(parts) >= 3 else parts[0]


def _side(path, rng: str, diff: str, limit: int) -> dict:
    """One side of a repository's history: how many commits, who made them and when, what part of the repository they touched, and the newest `limit` of them
    with what each says about why it was made."""
    from collections import Counter
    import time
    total = int(git.out(path, "rev-list", "--count", rng) or 0)
    if not total:
        return {"count": 0, "authors": [], "areas": [], "commits": [], "more": 0}
    meta = git.out(path, "log", rng, "--format=%an\x1f%ct").splitlines()
    names = Counter(m.split("\x1f")[0] for m in meta)
    times = sorted(int(m.split("\x1f")[1]) for m in meta if "\x1f" in m)
    areas = Counter(_area(f) for f in git.out(path, "diff", "--name-only", diff).splitlines() if f)
    raw = git.run(path, "log", rng, f"--max-count={limit}", "--name-only", "--format=\x1e%h\x1f%an\x1f%aI\x1f%P\x1f%s\x1f%b\x1d").stdout
    commits = []
    for chunk in raw.split("\x1e")[1:]:
        head, _, files = chunk.partition("\x1d")
        h, an, date, parents, subject, body = (head.split("\x1f") + [""] * 6)[:6]
        names_in = [f for f in files.splitlines() if f.strip()]
        merge = len(parents.split()) > 1
        commits.append({"id": f"{h}  {subject}", "author": an, "date": date[:10], "files": len(names_in),
                        "text": _why(body) or ("A merge of two lines of work; it adds no change of its own." if merge else "No reason is given in its message.")})
    day = lambda t: time.strftime("%Y-%m-%d", time.localtime(t))
    return {"count": total, "authors": [{"name": n, "commits": c} for n, c in names.most_common(5)], "first": day(times[0]) if times else "", "last": day(times[-1]) if times else "",
            "areas": [{"name": a, "files": c} for a, c in areas.most_common(6)], "commits": commits, "more": max(0, total - len(commits))}


def explain(rid: RepoId, cfg: config.Config, limit: int = 20) -> dict:
    """What `repo status --details` adds: what is incoming from the shared branch, what is only here, and why those are not the same thing, in plain words.
    Reads local history only (the person's last fetch), changes nothing."""
    path = rid.path(cfg)
    if not (path / ".git").exists() or not git.out(path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"):
        return {}
    inc = _side(path, "HEAD..@{u}", "HEAD...@{u}", limit)
    out = _side(path, "@{u}..HEAD", "@{u}...HEAD", limit)
    # A commit with the same change under a different name (a rebase, a squash, a copy of it) is not news: git cherry marks those with a minus.
    same_out = sum(1 for l in git.out(path, "cherry", "@{u}", "HEAD").splitlines() if l.startswith("-"))
    same_in = sum(1 for l in git.out(path, "cherry", "HEAD", "@{u}").splitlines() if l.startswith("-"))
    plural = lambda n: f"{n} commit{'s' if n != 1 else ''}"
    are = lambda n: "is" if n == 1 else "are"
    who = lambda side: ", ".join(f"{a['name']} ({a['commits']})" for a in side["authors"][:3])
    parts = []
    if inc["count"]:
        parts.append(f"{plural(inc['count'])} {are(inc['count'])} on the shared branch and not here yet, made by {who(inc)} between {inc['first']} and {inc['last']}.")
    if out["count"]:
        parts.append(f"{plural(out['count'])} {are(out['count'])} here and not on the shared branch yet, made by {who(out)} between {out['first']} and {out['last']}.")
    if inc["count"] and out["count"]:
        parts.append("Both sides moved on, so git cannot just move forward and ws-host will not join them without your say-so.")
        if same_out or same_in:
            parts.append(f"{same_out} of the commits here and {same_in} of the incoming ones carry changes the other side already has under a different commit name, which usually means history was "
                         "rewritten (a rebase or a squash) somewhere; those are not new work.")
    elif not parts:
        parts.append("Nothing differs from the shared branch as of the last time it was fetched.")
    elif inc["count"]:
        parts.append("`ws-host repo sync` brings them in; nothing of yours is touched.")
    return {"incoming": inc, "outgoing": out, "same_change_outgoing": same_out, "same_change_incoming": same_in, "explain": " ".join(parts)}


class FreshError(Exception):
    def __init__(self, code: str, plain: str):
        super().__init__(plain)
        self.code, self.plain = code, plain


def fresh_plan(rid: RepoId, cfg: config.Config) -> dict:
    """What a clean refresh would drop, from local history: the commits only here and the changes not committed. Raises FreshError when it must not go ahead."""
    path = rid.path(cfg)
    if not (path / ".git").exists():
        raise FreshError("not-cloned", f"{rid.name} is not on this machine yet, so there is nothing to refresh. Copy it first.")
    op = git.operation_in_progress(path)
    if op:
        raise FreshError("operation", f"{op} is in progress in {rid.name}. Finish it or cancel it first (for example `git {op.split()[0]} --abort`), then try again.")
    branch = git.out(path, "symbolic-ref", "--short", "-q", "HEAD")
    if not branch:
        raise FreshError("no-branch", f"{rid.name} is not on a branch, so I do not know which shared branch to make it match.")
    upstream = git.out(path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if not upstream:
        raise FreshError("no-upstream", f"{rid.name}'s branch {branch} is not connected to a shared branch, so there is nothing to match it to.")
    counts = git.out(path, "rev-list", "--left-right", "--count", "HEAD...@{u}").split()
    ahead, behind = (int(counts[0]), int(counts[1])) if len(counts) == 2 else (0, 0)
    changed = [l[3:] for l in git.out(path, "status", "--porcelain=v1", "--untracked-files=no").splitlines() if l.strip()]
    return {"path": path, "branch": branch, "upstream": upstream, "ahead": ahead, "behind": behind, "uncommitted": changed}


def fresh(rid: RepoId, cfg: config.Config, offline: bool = False) -> dict:
    """The clean refresh: make the repository exactly what is on its shared branch, and keep what was only here in a backup branch that is never deleted for you.
    Files that git does not track are left where they are. The caller has already had the person's yes."""
    import time
    plan = fresh_plan(rid, cfg)
    path = plan["path"]
    if not offline:
        f = git.run(path, "fetch", "--quiet")
        if f.returncode != 0:
            raise FreshError("unreachable", f"I could not reach GitHub to ask what is fresh: {git.reason(f)}. Nothing was changed.")
        plan = fresh_plan(rid, cfg)
    backup = ""
    if plan["ahead"] or plan["uncommitted"]:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = "HEAD"
        if plan["uncommitted"]:
            made = git.out(path, "stash", "create", "ws-host: changes not committed before a clean refresh")
            target = made or "HEAD"           # a stash commit's first parent is HEAD, so one branch keeps both the commits and the changes
        backup = f"ws-host-backup/{stamp}"
        b = git.run(path, "branch", backup, target)
        if b.returncode != 0:
            raise FreshError("backup-failed", f"I could not make the backup branch, so I changed nothing: {git.reason(b)}")
    r = git.run(path, "reset", "--hard", plan["upstream"])
    if r.returncode != 0:
        raise FreshError("reset-failed", f"git could not make {rid.name} match {plan['upstream']}: {git.reason(r)}. The backup branch {backup or '(none was needed)'} is intact.")
    return {"id": str(rid), "path": str(path), "branch": plan["branch"], "upstream": plan["upstream"], "dropped_commits": plan["ahead"], "dropped_changes": len(plan["uncommitted"]),
            "moved_forward": plan["behind"], "backup": backup}


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
