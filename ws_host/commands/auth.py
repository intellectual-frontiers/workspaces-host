"""`auth status` and `auth new github|gitlab` (0002-repositories-and-trust FR-011): the device-flow login."""
from __future__ import annotations

import os
import re
import select
import shutil
import subprocess

from ..core import config, registry as reg
from ..core.registry import Arg, command
from ..core.resource import Action, FAILED, MISSING, OK, Resource, WsError

CODE_RX = re.compile(r"\b([A-Z0-9]{4}-[A-Z0-9]{4})\b")
URL_RX = re.compile(r"https?://[^\s]+")


def _forges(cfg):
    yield "github", "github.com", "gh"
    for h in cfg.words("WS_HOST_GITLAB_HOSTS"):
        yield "gitlab", h, "glab"


def _signed_in(prog: str, host: str):
    exe = shutil.which(prog)
    if not exe:
        return None
    try:
        p = subprocess.run([exe, "auth", "status", "--hostname", host], capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.returncode == 0


@command("auth", "status", category="read", summary="Say whether you are signed in to GitHub and GitLab")
def auth_status(ctx):
    cfg = config.load()
    rows, actions = [], []
    for forge, host, prog in _forges(cfg):
        s = _signed_in(prog, host)
        label = "GitHub" if forge == "github" else host
        if s is None:
            rows.append({"name": host, "status": "warn", "signed_in": None, "program": prog,
                         "plain": f"I cannot tell: {prog}, the tool that signs you in, is not installed."})
            actions.append(Action(("kit", "add"), "Install the base kit", {"KIT": "base"}))
        elif s:
            rows.append({"name": host, "status": "ok", "signed_in": True, "program": prog, "plain": f"You are signed in to {label}."})
        else:
            rows.append({"name": host, "status": "warn", "signed_in": False, "program": prog, "plain": f"You are not signed in to {label}."})
            fields = {"FORGE": forge} | ({"host": host} if forge == "gitlab" else {})
            actions.append(Action(("auth", "new"), f"Sign in to {label}", fields))
    plain = rows[0]["plain"] if len(rows) == 1 else ("You are signed in everywhere I checked." if all(r["signed_in"] for r in rows) else "You are not signed in everywhere yet.")
    uniq = {(a.words, tuple(sorted(a.fields.items()))): a for a in actions}
    return Resource("auth-status", "forges", {"plain": plain, "forges": rows}, actions=list(uniq.values()))


@command("auth", "new", category="setup", summary="Sign in to GitHub or GitLab with a one-time code",
         args=(Arg("FORGE", "FORGE", positional=True, required=True), Arg("host", help="the host, for a GitLab other than the first configured")),
         surfaces=("cli", "editor"))
def auth_new(ctx, FORGE, host):
    cfg = config.load()
    prog = "gh" if FORGE == "github" else "glab"
    host = host or ("github.com" if FORGE == "github" else (cfg.words("WS_HOST_GITLAB_HOSTS") or ["gitlab.com"])[0])
    exe = shutil.which(prog)
    if not exe:
        raise WsError("missing-program", f"{prog} is not installed", f"I need a tool called {prog} to sign you in, and it is not installed yet.",
                      [Action(("kit", "add"), "Install the base kit", {"KIT": "base"})], status=MISSING)
    argv = [exe, "auth", "login", "--hostname", host, "--web"] + (["--git-protocol", "https"] if prog == "gh" else [])
    if ctx.dry_run:
        yield Resource("auth", host, {"plain": f"Nothing was changed. I would sign you in to {host}.", "would_run": " ".join([prog, *argv[1:]])})
        return
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
    fd = proc.stdout.fileno()
    buf, shown, entered = "", False, False
    while True:
        ready, _, _ = select.select([fd], [], [], 1.0)
        if not ready:
            if proc.poll() is not None:
                break
            continue
        chunk = os.read(fd, 4096)
        if not chunk:
            break
        buf += chunk.decode("utf-8", "replace")
        if not entered and "Press Enter" in buf:
            entered = True
            try:
                proc.stdin.write(b"\n")
                proc.stdin.flush()
            except OSError:
                pass
        if not shown:
            code, url = CODE_RX.search(buf), URL_RX.search(buf[buf.find(CODE_RX.search(buf).group(1)):] if CODE_RX.search(buf) else "")
            if code and url:
                shown = True
                yield Resource("auth-code", host, {"plain": f"To sign in, open {url.group(0)} and type this code: {code.group(1)}",
                                                   "code": code.group(1), "url": url.group(0), "host": host})
    rc = proc.wait()
    proc.stdout.close()
    proc.stdin.close()
    if rc == 0 and prog == "gh":
        subprocess.run([exe, "auth", "setup-git", "--hostname", host], capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    ok = rc == 0
    yield Resource("auth", host, {"plain": f"You are signed in to {host}." if ok else f"Signing in to {host} did not finish.", "signed_in": ok},
                   actions=[] if ok else [Action(("auth", "new"), "Try again", {"FORGE": FORGE})], status=OK if ok else FAILED)
