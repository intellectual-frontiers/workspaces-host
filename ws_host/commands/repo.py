"""`repo list|status|add|sync|set` (0002-repositories-and-trust)."""
from __future__ import annotations

from ..core import config, paths, progress, registry as reg, types
from ..core.registry import Arg, command
from ..core.resource import Action, FAILED, OK, Resource, WsError
from ..lib import git, repos, trust as trust_mod

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
        cloned = (rid.path(cfg) / ".git").exists()
        rows.append({"id": str(rid), "path": str(rid.path(cfg)), "cloned": cloned, "status": "ok" if cloned else "pending",
                     "trusted": ok, "trust": why, "listed_by": found[rid]})
    n_missing = sum(not r["cloned"] for r in rows)
    plain = (f"I know {len(rows)} repositor{'ies' if len(rows) != 1 else 'y'}; "
             + (f"{n_missing} not copied to this machine yet." if n_missing else "all are on this machine.")) if rows else \
            "I do not know any repositories yet. Add one with: ws-host repo add github.com/ORG/REPO"
    actions = [Action(("repo", "add"), "Copy the missing repositories", {"all": True})] if n_missing else []
    return Resource("repo-list", "repositories", {"plain": plain, "repositories": rows, "ignored": invalid}, actions=actions)


@command("repo", "status", category="read", summary="Show the state of one or all repositories; --details says what is incoming and what is only here, and why",
         args=(REPO_ARG,
               Arg("details", flag=True, help="list the commits on each side, who made them, when, what they touched and what each says about why"),
               Arg("limit", "STRING", help="with --details: how many commits to list on each side (default 20)"),
               Arg("fetch", flag=True, help="with --details: ask GitHub for news first, so that what is listed is current")))
def repo_status(ctx, repo, details=False, limit=None, fetch=False):
    cfg = config.load()
    chosen = _selected(cfg, repo)
    if details and fetch and not ctx.offline:
        for r in chosen:
            p = r.path(cfg)
            if (p / ".git").exists():
                with progress.working(f"🔄 Asking GitHub about {r.name}"):
                    git.run(p, "fetch", "--quiet")
    rows = [repos.state(r, cfg) for r in chosen]
    for r, rid in zip(rows, chosen):
        r["status"] = "ok" if r["cloned"] and not (r.get("dirty") or r.get("ahead") or r.get("behind")) else "warn"
        if details:
            r.update(repos.explain(rid, cfg, max(1, int(limit or 20))))
    dirty = sum(bool(r.get("dirty")) for r in rows)
    plain = ("Everything is in order." if all(r["status"] == "ok" for r in rows) else
             f"{sum(r['status'] != 'ok' for r in rows)} of {len(rows)} repositories have something to look at.") if rows else "I do not know any repositories yet."
    if details and any(r.get("explain") and r["status"] != "ok" for r in rows):
        plain += " Each one says below what is incoming, what is only here, and why."
    behind = any(r.get("behind") or r.get("ahead") for r in rows)
    fresh_acts = [Action(("repo", "advance"), f"Start {r['id'].rsplit('/', 1)[-1]} fresh from GitHub (keeps a backup)", {"repo": r["id"], "clean": True})
                  for r in rows if r.get("cloned") and r.get("upstream") and (r.get("ahead") or r.get("dirty"))]
    acts = [Action(("repo", "sync"), "Bring them up to date", {"all": True})] if rows else []
    if behind and not details:
        acts.insert(0, Action(("repo", "status"), "Explain what changed and why", {"details": True}))
    return Resource("repo-status", repo or "all", {"plain": plain, "repositories": rows}, actions=acts + (fresh_acts if details else []))


@command("repo", "advance", category="decision", summary="Clean refresh: make a repository exactly what is on its shared branch, keeping what was only here in a backup branch",
         args=(Arg("repo", "REPO", positional=True, required=True),
               Arg("clean", flag=True, help="say that you mean it: what is only here is put aside in a backup branch and the repository becomes what GitHub has")))
def repo_advance(ctx, repo, clean=False):
    if not clean:
        raise WsError("usage", "give --clean to make it match the shared branch", "To throw away what is only here and start from what is on GitHub, add --clean. A backup branch keeps what was here.", exit_code=2)
    cfg = config.load()
    rid = repos.resolve(cfg, repo)
    try:
        plan = repos.fresh_plan(rid, cfg)
    except repos.FreshError as e:
        raise WsError(f"refresh-{e.code}", e.plain, e.plain, exit_code=1)
    lose = []
    if plan["ahead"]:
        lose.append(f"{plan['ahead']} commit{'s' if plan['ahead'] != 1 else ''} that {plan['upstream']} does not have")
    if plan["uncommitted"]:
        lose.append(f"{len(plan['uncommitted'])} change{'s' if len(plan['uncommitted']) != 1 else ''} you have not committed")
    saved = " Both are kept in a backup branch, so nothing is lost." if lose else ""
    if ctx.dry_run:
        return Resource("repo", str(rid), {"plain": f"Nothing was changed. I would make {rid.name} exactly {plan['upstream']}" + (", putting aside " + " and ".join(lose) + "." + saved if lose else "; it has nothing only here to put aside."),
                                           "would_drop_commits": plan["ahead"], "would_drop_changes": plan["uncommitted"], "would_move_forward": plan["behind"], "backup": bool(lose),
                                           "untracked_files": "left where they are"})
    ctx.confirm(f"This makes {rid.name} exactly what is on {plan['upstream']}" + (" and puts aside " + " and ".join(lose) + "." + saved if lose else "."))
    try:
        r = repos.fresh(rid, cfg, ctx.offline)
    except repos.FreshError as e:
        raise WsError(f"refresh-{e.code}", e.plain, e.plain, exit_code=1)
    kept = (f" What was only here is kept in the branch {r['backup']}; to look at it: git switch {r['backup']}." if r["backup"] else "")
    return Resource("repo", str(rid), {"plain": f"{rid.name} is now exactly {r['upstream']}." + kept, **r}, status=OK)


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
         args=(REPO_ARG, Arg("all", flag=True, help="every known repository"), Arg("trust", flag=True, help="also trust them")), surfaces=("cli", "editor"))
def repo_add(ctx, repo, all, trust: bool):
    cfg = config.load()
    listed = None
    rid_new = repos.parse_id(repo) if repo else None
    if rid_new is not None and str(rid_new) not in set(cfg.repos()) and rid_new not in repos.known(cfg)[0]:
        listed = str(rid_new)       # 0006-onboarding FR-011: naming a new repository puts it on the person's own list
    found, _ = repos.known(cfg)
    chosen = _selected(cfg, repo)
    trust_these: list[repos.RepoId] = []
    if trust:
        # Only repositories the person lists or names: never those only another repository's file names (0002 FR-014).
        own = {repos.parse_id(e) for e in cfg.repos()}
        trust_these = [r for r in chosen if repo or r in own]
    if ctx.dry_run:
        rows = [{"id": str(r), "outcome": "would-copy" if not (r.path(cfg) / ".git").exists() else "present", "status": "ok",
                 "plain": f"I would copy {r.name} to {r.path(cfg)}." if not (r.path(cfg) / ".git").exists() else f"{r.name} is already here."}
                for r in chosen]
        return Resource("repo-add", "dry-run", {"plain": "Nothing was changed. This is what I would do.", "repositories": rows,
                                                 "would_trust": [str(r) for r in trust_these], **({"would_list": listed} if listed else {})})
    if trust:
        ctx.confirm("This lets these repositories' code run on your machine: " + ", ".join(map(str, trust_these)) + ".")
    if listed:
        config.add_repo(listed)
        cfg = config.load()
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
    try:         # a repository that arrives joins the VS Code workspace, so the Workspaces Console shows its command line at once
        from . import vscode as vscode_cmd
        if vscode_cmd.workspace_file(cfg).exists():
            vscode_cmd.workspace_step(cfg, False)
    except Exception:
        pass
    bad = any(r["outcome"] == "failed" for r in results)
    data = {"plain": repos.summarize(results) + (f" I added {listed} to your list in {paths.config_file()}." if listed else ""), "repositories": results}
    if listed:
        data["listed"] = listed
    if trust:
        data["trusted"] = [str(r) for r in trust_these if (r.path(cfg) / ".git").exists()]
    return Resource("repo-add", "all" if not repo else repo, data, actions=_actions_for(results, cfg), status=FAILED if bad else OK)



@command("repo", "sync", category="setup", summary="Bring repositories up to date, never touching your work",
         args=(REPO_ARG, Arg("all", flag=True, help="every cloned repository")), surfaces=("cli", "editor"))
def repo_sync(ctx, repo, all):
    cfg = config.load()
    chosen = _selected(cfg, repo)
    if ctx.dry_run:
        rows = [repos.state(r, cfg) | {"outcome": "would-check", "status": "ok"} for r in chosen]
        return Resource("repo-sync", "dry-run", {"plain": "Nothing was changed. This is where each repository stands now.", "repositories": rows})
    results = [repos.sync(r, cfg) for r in chosen]
    bad = any(r["outcome"] == "failed" for r in results)
    return Resource("repo-sync", repo or "all", {"plain": repos.summarize(results), "repositories": results},
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
