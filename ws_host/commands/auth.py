"""`auth status` and `auth new github|gitlab|microsoft` (0002-repositories-and-trust FR-011, FR-025): the device-flow login."""
from __future__ import annotations

import os
import re
import select
import shutil
import subprocess

from ..core import config, registry as reg
from ..core.registry import Arg, command
from ..core.resource import Action, FAILED, MISSING, OK, Resource, WsError
from ..lib import graph

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
            actions.append(Action(("kit", "add"), "Install the base kit", {"kit": "base"}))
        elif s:
            rows.append({"name": host, "status": "ok", "signed_in": True, "program": prog, "plain": f"You are signed in to {label}."})
        else:
            rows.append({"name": host, "status": "warn", "signed_in": False, "program": prog, "plain": f"You are not signed in to {label}."})
            fields = {"forge": forge} | ({"host": host} if forge == "gitlab" else {})
            actions.append(Action(("auth", "new"), f"Sign in to {label}", fields))
    if graph.kit_here() or graph.accounts():
        for label in graph.accounts() or ["default"]:
            try:
                graph.token_for(label)
                rows.append({"name": f"microsoft {label}", "status": "ok", "signed_in": True, "program": "msauth", "plain": f"You are signed in to Microsoft as '{label}'."})
            except WsError:
                rows.append({"name": f"microsoft {label}", "status": "warn", "signed_in": False, "program": "msauth", "plain": f"You are not signed in to Microsoft as '{label}'."})
                actions.append(Action(("auth", "new"), f"Sign in to Microsoft ({label})", {"forge": "microsoft", "host": label}))
    plain = rows[0]["plain"] if len(rows) == 1 else ("You are signed in everywhere I checked." if all(r["signed_in"] for r in rows) else "You are not signed in everywhere yet.")
    uniq = {(a.words, tuple(sorted(a.fields.items()))): a for a in actions}
    return Resource("auth-status", "forges", {"plain": plain, "forges": rows}, actions=list(uniq.values()))


@command("auth", "new", category="setup", summary="Sign in to GitHub, GitLab or Microsoft with a one-time code",
         args=(Arg("forge", "FORGE", positional=True, required=True, help="github, gitlab or microsoft"),
               Arg("host", help="the host, for a GitLab other than the first configured; for Microsoft, a name for this account, such as work (default: default)")),
         surfaces=("cli", "editor"))
def auth_new(ctx, forge, host):
    if forge == "microsoft":
        yield from _microsoft_new(ctx, host or "default")
        return
    cfg = config.load()
    prog = "gh" if forge == "github" else "glab"
    host = host or ("github.com" if forge == "github" else (cfg.words("WS_HOST_GITLAB_HOSTS") or ["gitlab.com"])[0])
    exe = shutil.which(prog)
    if not exe:
        raise WsError("missing-program", f"{prog} is not installed", f"I need a tool called {prog} to sign you in, and it is not installed yet.",
                      [Action(("kit", "add"), "Install the base kit", {"kit": "base"})], status=MISSING)
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
                   actions=[] if ok else [Action(("auth", "new"), "Try again", {"forge": forge})], status=OK if ok else FAILED)


def _microsoft_new(ctx, label: str):
    """The one-time code and the page to type it in, from Microsoft's own library; no password or token is typed or shown here."""
    if not graph.kit_here():
        raise graph.need_kit()
    if ctx.dry_run:
        yield Resource("auth", label, {"plain": f"Nothing was changed. I would sign you in to Microsoft as '{label}'.", "would_run": "ws-host auth new microsoft --host " + label})
        return
    if graph.app_for(label) is None:
        _ask_app(ctx, label)           # asks at a terminal and keeps the answers; where nothing can be asked, says what to do and stops
    note, done = "", None
    for ev in graph.sign_in(label):
        if ev.get("event") == "code":
            yield Resource("auth-code", label, {"plain": f"To sign in, open {ev['url']} and type this code: {ev['code']}", "code": ev["code"], "url": ev["url"], "host": label,
                                                   "hint": "If Microsoft then says 'You don't have access to this', your organization has not allowed the shared sign-in app: run `ws-host help onedrive` for how to register your own."})
        elif ev.get("event") == "note":
            note = ev["message"]
        elif ev.get("event") in ("done", "error"):
            done = ev
    ok = bool(done) and done.get("event") == "done"
    who = f" ({done['username']})" if ok and done.get("username") else ""
    plain = (f"You are signed in to Microsoft as '{label}'{who}." + (f" {note}" if note else "")) if ok else \
        f"Signing in to Microsoft did not finish" + (f": {done['message']}" if done and done.get("message") else ".") + (" A work account may need an administrator to approve the app; the guide says how to use your own." if not ok else "")
    yield Resource("auth", label, {"plain": plain, "signed_in": ok}, actions=[] if ok else [Action(("auth", "new"), "Try again", {"forge": "microsoft", "host": label})],
                   status=OK if ok else FAILED)


ENTRA = "https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade"
GUIDE = (
    "To sign in to a work Microsoft account I need two numbers from an app that your organization has registered, because many organizations do not allow the shared one.\n"
    "If nobody has registered one for you, you can, in two minutes, at " + ENTRA + " :\n"
    "  1. New registration; give it any name, such as ws-host. Choose the account type your organization uses (\"this organizational directory only\" is fine).\n"
    "  2. Authentication: add the platform \"Mobile and desktop applications\" with the redirect https://login.microsoftonline.com/common/oauth2/nativeclient, and turn on \"Allow public client flows\".\n"
    "  3. API permissions: add the Microsoft Graph delegated permissions Files.ReadWrite.All and User.Read, and click \"Grant admin consent\" if it is there.\n"
    "  4. On the app's Overview page, copy the \"Application (client) ID\" and the \"Directory (tenant) ID\".\n"
    "For a home account (outlook.com, hotmail.com, live.com) you need no app: type shared.")


def _plain_missing(label: str) -> str:
    return (GUIDE + f"\nThen run:  ws-host auth set microsoft CLIENT_ID TENANT --host {label}\nor, at a terminal, run  ws-host auth new microsoft --host {label}  again and answer the two questions.")


def _ask_app(ctx, label: str) -> None:
    """The one place a person is asked for the app's IDs (0002 FR-026): at a terminal, in plain words, checked as typed and kept for this account, so no environment variable or file is ever edited by hand."""
    from ..core import types
    if not ctx.interactive():
        raise WsError("needs-input", f"ws-host needs the app that signs {label} in to Microsoft", _plain_missing(label),
                      [Action(("auth", "set"), "Enter the app's IDs", {"forge": "microsoft", "host": label}), Action(("auth", "new"), "Sign in once they are set", {"forge": "microsoft", "host": label})],
                      status=MISSING)
    print(GUIDE + "\n")
    client = _ask("Application (client) ID, or shared", types.CLIENTID)
    tenant = "common" if client == "shared" else _ask("Directory (tenant) ID, or your organization's domain such as example.com", types.TENANT)
    graph.save_profile(label, client, tenant)
    print(f"Saved for '{label}'. You will not be asked again.\n")


def _ask(question: str, typ) -> str:
    for _ in range(4):
        try:
            answer = input(f"{question}: ").strip()
        except EOFError:
            break
        problem = typ.validate(answer, None) if answer else "nothing was typed"
        if not problem:
            return answer
        print(f"  {problem}")
    raise WsError("needs-input", "no valid answer was given", "I did not get a valid answer, so I stopped. Run the command again when you have the value.", exit_code=2)


@command("auth", "set", category="setup", summary="Tell ws-host which app signs a Microsoft account in, from an app registration of your own",
         args=(Arg("forge", "FORGE", positional=True, required=True, help="microsoft"),
               Arg("client_id", "CLIENTID", positional=True, required=True, help="the Application (client) ID of your app registration, or shared for Microsoft's own app"),
               Arg("tenant", "TENANT", positional=True, required=True, help="the Directory (tenant) ID or your organization's domain; say common with shared"),
               Arg("host", help="the name of the account, such as work (default: default)")),
         surfaces=("cli", "editor"))
def auth_set(ctx, forge, client_id, tenant, host=None):
    if forge != "microsoft":
        raise WsError("usage", "only microsoft has settings to set", "Only a Microsoft account needs this. GitHub and GitLab sign in without it.", exit_code=2)
    label = host or "default"
    tenant = "common" if client_id == "shared" else tenant
    if ctx.dry_run:
        return Resource("auth", label, {"plain": f"Nothing was changed. I would remember that '{label}' signs in with that app.", "account": label})
    graph.save_profile(label, client_id, tenant)
    return Resource("auth", label, {"plain": f"Saved. '{label}' will sign in with that app. Next: ws-host auth new microsoft --host {label}", "account": label, "client_id": client_id, "tenant": tenant,
                                    "next": f"ws-host auth new microsoft --host {label}"},
                    actions=[Action(("auth", "new"), "Sign in now", {"forge": "microsoft", "host": label})], status=OK)
