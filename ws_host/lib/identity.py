"""Whose commits they are (0002-repositories-and-trust FR-027): the name and email git puts on a commit, set from the GitHub account a person signs in with, and optionally a work address
for the repositories of the organizations they trust. It writes git's own configuration through `git config`, never a file of its own making except the small one an `includeIf` names."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from archon import paths
from ..core import config
from . import git, trust

EMAIL_RX = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")


def valid_email(value: str) -> bool:
    return bool(EMAIL_RX.match(value or ""))


def valid_name(value: str) -> bool:
    return bool(value) and value == value.strip() and len(value) <= 100 and not any(c in value for c in "<>\n\r\x00")


def github_profile() -> dict | None:
    """The signed-in GitHub account's name, login and id, from `gh`; None when it cannot say. Its email is not used: most people keep it private, and the noreply address is always right."""
    exe = shutil.which("gh")
    if not exe:
        return None
    try:
        p = subprocess.run([exe, "api", "user"], capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
        d = json.loads(p.stdout) if p.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    return d if isinstance(d, dict) and d.get("login") else None


def noreply(profile: dict) -> str:
    """GitHub's address for a person who keeps their own private: it links the commits to the account, and a push that carries it is never refused for exposing an email."""
    return f"{profile['id']}+{profile['login']}@users.noreply.github.com" if profile.get("id") else f"{profile['login']}@users.noreply.github.com"


def current() -> dict[str, str]:
    return {"name": git.out(None, "config", "--global", "--get", "user.name"), "email": git.out(None, "config", "--global", "--get", "user.email")}


def work_file(org: str) -> Path:
    return paths.config_dir() / "git" / f"{org}.gitconfig"


def _tilde(path: Path) -> str:
    try:
        return "~/" + str(path.relative_to(paths.home())).rstrip("/")
    except ValueError:
        return str(path)


def condition(cfg: config.Config, org: str) -> str:
    return f"gitdir:{_tilde(cfg.workspaces / 'github.com' / org)}/"


def work_email(cfg: config.Config) -> dict[str, str]:
    """The work address in use for each trusted organization's folder, where one is set."""
    out = {}
    for org in sorted(trust.trusted_orgs(cfg)):
        f = work_file(org)
        if f.exists():
            v = git.out(None, "config", "--file", str(f), "--get", "user.email")
            if v:
                out[org] = v
    return out


def _set_work(cfg: config.Config, email: str | None) -> list[str]:
    """Use `email` (or none, to take it away) for the folder of every trusted organization, by an `includeIf` that names a small file; returns the organizations changed."""
    changed = []
    for org in sorted(trust.trusted_orgs(cfg)):
        f = work_file(org)
        key = f"includeif.{condition(cfg, org)}.path"
        have = git.out(None, "config", "--global", "--get-all", key).splitlines()
        if email:
            f.parent.mkdir(parents=True, exist_ok=True)
            was = git.out(None, "config", "--file", str(f), "--get", "user.email")
            git.run(None, "config", "--file", str(f), "user.email", email)
            if str(f) not in have:
                git.run(None, "config", "--global", "--add", key, str(f))
            if was != email:
                changed.append(org)
        elif have or f.exists():
            for v in have:
                git.run(None, "config", "--global", "--unset-all", key)
            f.unlink(missing_ok=True)
            changed.append(org)
    return changed


def ensure(cfg: config.Config, name: str | None = None, email: str | None = None, work: str | None = None, from_github: bool = True, dry_run: bool = False) -> dict:
    """Make commits go in as the person. A name or address that was asked for (an argument, or WS_HOST_GIT_NAME and WS_HOST_GIT_EMAIL) is set; one that is only worked out from the GitHub account is set
    only where git has none, so what a person set themselves is never changed. `work` is a work address for the trusted organizations' folders (`none` takes it away)."""
    now = current()
    asked_name = name or cfg.get("WS_HOST_GIT_NAME") or None
    asked_email = email or cfg.get("WS_HOST_GIT_EMAIL") or None
    profile = github_profile() if from_github and (not now["name"] or not now["email"] or not asked_name or not asked_email) else None
    want_name = asked_name or (None if now["name"] else (profile or {}).get("name"))
    want_email = asked_email or (None if now["email"] else (noreply(profile) if profile else None))
    result: dict = {"changed": [], "name": now["name"], "email": now["email"], "needs_name": False, "github": (profile or {}).get("login", ""), "work": work_email(cfg)}
    if want_name and want_name != now["name"]:
        result["changed"].append("name")
        result["name"] = want_name
    if want_email and want_email != now["email"]:
        result["changed"].append("email")
        result["email"] = want_email
    result["needs_name"] = not result["name"]
    if dry_run:
        if work:
            result["changed"] += [f"work email for {o}" for o in sorted(trust.trusted_orgs(cfg))]
            result["work"] = {} if work == "none" else {o: work for o in sorted(trust.trusted_orgs(cfg))}
        return result
    if "name" in result["changed"]:
        git.run(None, "config", "--global", "user.name", result["name"])
    if "email" in result["changed"]:
        git.run(None, "config", "--global", "user.email", result["email"])
    if ("name" in result["changed"] or "email" in result["changed"]) and not work:
        for org in work_email(cfg):                     # a work address already in use must still come later in the file than the address just written
            key = f"includeif.{condition(cfg, org)}.path"
            git.run(None, "config", "--global", "--unset-all", key)
            git.run(None, "config", "--global", "--add", key, str(work_file(org)))
    if work:        # after the global address is written: an `includeIf` counts only where it comes later in the file
        result["changed"] += [f"work email for {o}" for o in _set_work(cfg, None if work == "none" else work)]
        result["work"] = {} if work == "none" else {o: work for o in sorted(trust.trusted_orgs(cfg))}
    return result


def sentence(r: dict) -> str:
    if r["needs_name"]:
        return "Git has no name for your commits yet. Run  ws-host workspace set --git-name \"Your Name\"  (and --git-email if you want an address other than GitHub's)."
    who = f"{r['name']} <{r['email']}>" if r["email"] else r["name"]
    extra = "".join(f"; in {o}'s folder, {e}" for o, e in r["work"].items())
    return f"Commits will be made as {who}{extra}."
