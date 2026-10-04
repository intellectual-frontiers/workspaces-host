"""`repo list|status|add|advance|set` (0002-repositories-and-trust)."""
from __future__ import annotations

from ..core import config, registry as reg, types
from ..core.registry import Arg, command
from ..core.resource import Action, FAILED, OK, Resource, WsError
from ..lib import repos, trust as trust_mod

REPO_ARG = Arg("repo", "REPO", positional=True, help="a repository: host/org/repo, org/repo or repo")


def _validate_repo(value, ctx):
    return None if value else "empty"


types.REPO.validate = _validate_repo
types.REPO.complete = lambda ctx: sorted(map(str, repos.known(config.load())[0]))


def _selected(cfg, repo, all_=False) -> list[repos.RepoId]:
    if repo:
        return [repos.resolve(cfg, repo)]
    return sorted(repos.known(cfg)[0], key=str)


@command("repo", "list", category="read", summary="List the repositories I know")
def repo_list(ctx):
    cfg = config.load()
    found, invalid = repos.known(cfg)
    rows = []
    for rid in sorted(found, key=str):
        ok, why = trust_mod.trust_state(rid, cfg)
        rows.append({"id": str(rid), "path": str(rid.path(cfg)), "cloned": (rid.path(cfg) / ".git").exists(),
                     "trusted": ok, "trust": why, "listed_by": found[rid]})
    n_missing = sum(not r["cloned"] for r in rows)
    plain = (f"I know {len(rows)} repositor{'ies' if len(rows) != 1 else 'y'}; "
             + (f"{n_missing} not copied to this machine yet." if n_missing else "all are on this machine.")) if rows else \
            "I do not know any repositories yet. List some in WS_HOST_REPOS in your configuration."
    actions = [Action(("repo", "add"), "Copy the missing repositories", {"all": True})] if n_missing else []
    return Resource("repo-list", "repositories", {"plain": plain, "repositories": rows, "ignored": invalid}, actions=actions)


@command("repo", "status", category="read", summary="Show the state of one or all repositories", args=(REPO_ARG,))
def repo_status(ctx, repo):
    cfg = config.load()
    rows = [repos.state(r, cfg) for r in _selected(cfg, repo)]
    for r in rows:
        r["status"] = "ok" if r["cloned"] and not (r.get("dirty") or r.get("ahead") or r.get("behind")) else "warn"
    dirty = sum(bool(r.get("dirty")) for r in rows)
    plain = ("Everything is in order." if all(r["status"] == "ok" for r in rows) else
             f"{sum(r['status'] != 'ok' for r in rows)} of {len(rows)} repositories have something to look at.") if rows else "I do not know any repositories yet."
    return Resource("repo-status", repo or "all", {"plain": plain, "repositories": rows},
                    actions=[Action(("repo", "advance"), "Bring them up to date", {"all": True})] if rows else [])


def _actions_for(results, cfg) -> list[Action]:
    acts, seen = [], set()
    for r in results:
        if r.get("auth"):
            rid = repos.parse_id(r["id"])
            for a in repos.sign_in_action(rid, cfg):
                key = (a.words, tuple(sorted(a.fields.items())))
                if key not in seen:
                    seen.add(key)
                    acts.append(a)
    return acts


@command("repo", "add", category="setup", summary="Copy missing repositories to this machine",
         args=(REPO_ARG, Arg("all", flag=True, help="every known repository"), Arg("trust", flag=True, help="also trust them")))
def repo_add(ctx, repo, all, trust: bool):
    cfg = config.load()
    found, _ = repos.known(cfg)
    chosen = _selected(cfg, repo)
    trust_these: list[repos.RepoId] = []
    if trust:
        # Only repositories the person lists or names: never those only another repository's file names (0002 FR-014).
        own = {repos.parse_id(e) for e in cfg.words("WS_HOST_REPOS")}
        trust_these = [r for r in chosen if repo or r in own]
    if ctx.dry_run:
        rows = [{"id": str(r), "outcome": "would-copy" if not (r.path(cfg) / ".git").exists() else "present", "status": "ok",
                 "plain": f"I would copy {r.name} to {r.path(cfg)}." if not (r.path(cfg) / ".git").exists() else f"{r.name} is already here."}
                for r in chosen]
        return Resource("repo-add", "dry-run", {"plain": "Nothing was changed. This is what I would do.", "repositories": rows,
                                                 "would_trust": [str(r) for r in trust_these]})
    if trust:
        ctx.confirm("This lets these repositories' code run on your machine: " + ", ".join(map(str, trust_these)) + ".")
    results, done, pending = [], set(), chosen
    # Cloning a repository can reveal more repositories in its own list: go until nothing new is missing.
    while pending:
        for r in pending:
            done.add(r)
            results.append(repos.clone(r, cfg))
        pending = [] if repo else [r for r in sorted(repos.known(cfg)[0], key=str) if r not in done]
    if trust:
        for r in trust_these:
            if (r.path(cfg) / ".git").exists():
                try:
                    trust_mod.grant(r, cfg)
                except FileExistsError as e:
                    raise WsError("trust-conflict", str(e), "Another repository with the same name is already trusted, so I did not trust this one.")
    bad = any(r["outcome"] == "failed" for r in results)
    data = {"plain": repos.summarize(results), "repositories": results}
    if trust:
        data["trusted"] = [str(r) for r in trust_these if (r.path(cfg) / ".git").exists()]
    return Resource("repo-add", "all" if not repo else repo, data, actions=_actions_for(results, cfg), status=FAILED if bad else OK)



@command("repo", "advance", category="setup", summary="Bring repositories up to date, never touching your work",
         args=(REPO_ARG, Arg("all", flag=True, help="every cloned repository")))
def repo_advance(ctx, repo, all):
    cfg = config.load()
    chosen = _selected(cfg, repo)
    if ctx.dry_run:
        rows = [repos.state(r, cfg) | {"outcome": "would-check", "status": "ok"} for r in chosen]
        return Resource("repo-advance", "dry-run", {"plain": "Nothing was changed. This is where each repository stands now.", "repositories": rows})
    results = [repos.advance(r, cfg) for r in chosen]
    bad = any(r["outcome"] == "failed" for r in results)
    return Resource("repo-advance", repo or "all", {"plain": repos.summarize(results), "repositories": results},
                    actions=_actions_for(results, cfg), status=FAILED if bad else OK)


@command("repo", "set", category="decision", summary="Trust or stop trusting a repository's code",
         args=(Arg("repo", "REPO", positional=True, required=True), Arg("trusted", flag=True), Arg("untrusted", flag=True)))
def repo_set(ctx, repo, trusted, untrusted):
    if bool(trusted) == bool(untrusted):
        raise WsError("usage", "give exactly one of --trusted and --untrusted", "Say whether to trust it (--trusted) or stop trusting it (--untrusted).", exit_code=2)
    cfg = config.load()
    rid = repos.resolve(cfg, repo)
    if trusted:
        if not (rid.path(cfg) / ".git").exists():
            raise WsError("not-cloned", f"{rid} is not cloned", f"{rid.name} is not on this machine yet, so there is nothing to trust. Copy it first.",
                          [Action(("repo", "add"), "Copy it", {"repo": str(rid)})])
        if ctx.dry_run:
            return Resource("repo", str(rid), {"plain": f"Nothing was changed. I would trust {rid.name}.", "would_trust": str(rid)})
        ctx.confirm(f"This lets code from {rid} run on your machine.")
        try:
            trust_mod.grant(rid, cfg)
        except FileExistsError as e:
            raise WsError("trust-conflict", str(e), "Another repository with the same name is already trusted, so I did not trust this one.")
        return Resource("repo", str(rid), {"plain": f"You now trust {rid.name}. Its kits and its tools may run.", "trusted": True,
                                           "trust": trust_mod.trust_state(rid, cfg)[1]})
    if ctx.dry_run:
        return Resource("repo", str(rid), {"plain": f"Nothing was changed. I would stop trusting {rid.name}.", "would_untrust": str(rid)})
    ctx.confirm(f"This stops code from {rid} running on your machine.")
    had = trust_mod.revoke(rid, cfg)
    still, why = trust_mod.trust_state(rid, cfg)
    return Resource("repo", str(rid), {"plain": f"You no longer trust {rid.name}." if not still else
                                       f"I removed your own trust of {rid.name}, but your configuration still trusts {rid.org}.",
                                       "trusted": still, "trust": why, "had_link": had})
