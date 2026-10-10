"""`onedrive list|show|add|sync`: a signed-in Microsoft account's OneDrive, through Microsoft Graph (0003-kits FR-021).

Nothing is ever replaced or deleted without `--replace`: `add` leaves a file that is already in OneDrive, `sync` leaves a local file that differs, and both say so."""
from __future__ import annotations

from pathlib import Path

from ..core.registry import Arg, command
from ..core.resource import Action, OK, Resource, WsError
from ..lib import graph

ACCOUNT = Arg("account", help="the sign-in to use, as named in `ws-host auth new microsoft --host NAME` (needed only with more than one)")
REPLACE = Arg("replace", flag=True, help="replace a file that is already there")


def _label(account: str | None) -> str:
    have = graph.accounts()
    if account:
        return account
    if len(have) == 1:
        return have[0]
    if not have:
        raise WsError("not-signed-in", "not signed in to Microsoft", "You are not signed in to Microsoft yet.",
                      [Action(("auth", "new"), "Sign in to Microsoft", {"forge": "microsoft"})], status="missing")
    raise WsError("which-account", "more than one Microsoft sign-in", f"You are signed in to more than one Microsoft account ({', '.join(have)}). Say which with --account.", exit_code=2)


def _human(n: int) -> str:
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} bytes"


@command("onedrive", "list", category="read", summary="List the files and folders in a OneDrive folder",
         args=(Arg("path", "PATH", positional=True, help="a folder in OneDrive, from its root (the root when left out)"), ACCOUNT))
def onedrive_list(ctx, path="", account=None):
    d = graph.Drive(_label(account))
    rows = d.children(path or "")
    rows.sort(key=lambda r: (r["kind"] != "folder", r["name"].lower()))
    shown = [{**r, "plain": f"{r['name']}/" if r["kind"] == "folder" else f"{r['name']}  ({_human(r['size'])})"} for r in rows]
    where = f"/{path.strip('/')}" if path and path.strip("/") else "the top of your OneDrive"
    return Resource("onedrive-list", path or "/", {"plain": f"{len(rows)} item{'s' if len(rows) != 1 else ''} in {where}.", "items": shown, "account": d.label})


@command("onedrive", "show", category="read", summary="Show one file or folder in OneDrive",
         args=(Arg("path", "PATH", positional=True, required=True, help="a file or folder in OneDrive"), ACCOUNT))
def onedrive_show(ctx, path, account=None):
    d = graph.Drive(_label(account))
    e = d.show(path)
    plain = f"{e['name']} is a {e['kind']}" + (f" of {_human(e['size'])}" if e["kind"] == "file" else f" with {e['children']} items") + f", last changed {e['modified'][:10]}."
    return Resource("onedrive-show", path, {"plain": plain, **e, "account": d.label})


@command("onedrive", "add", category="setup", summary="Copy a local file or folder into OneDrive; nothing already there is replaced unless you say so",
         args=(Arg("local", "LOCAL", positional=True, required=True, help="a file or folder on this machine"),
               Arg("remote", "REMOTE", positional=True, required=True, help="where in OneDrive it goes, from the root, such as Documents/report.docx"), ACCOUNT, REPLACE),
         surfaces=("cli", "editor"))
def onedrive_add(ctx, local, remote, account=None, replace=False):
    src = Path(local).expanduser()
    if not src.exists():
        raise WsError("no-such-file", f"{src} is not there", f"I cannot find {src} on this machine.", exit_code=2)
    d = graph.Drive(_label(account))
    files = [(src, remote.strip("/"))] if src.is_file() else [(f, f"{remote.strip('/')}/{f.relative_to(src).as_posix()}") for f in sorted(src.rglob("*")) if f.is_file()]
    wanted = {remote.strip("/")} | {r.rpartition("/")[0] for _, r in files}
    folders = [] if src.is_file() else sorted({"/".join(w.split("/")[:i]) for w in wanted for i in range(1, len(w.split("/")) + 1)}, key=lambda x: x.count("/"))
    rows, sent = [], 0
    if not ctx.dry_run:
        for fol in folders:
            if fol:
                d.make_folder(fol)
    for f, r in files:
        try:
            d.show(r)
            exists = True
        except WsError as e:
            if "404" not in e.message:
                raise
            exists = False
        if exists and not replace:
            rows.append({"name": r, "status": "skipped", "plain": f"{r} is already in OneDrive, so I left it (--replace changes that)."})
            continue
        if ctx.dry_run:
            rows.append({"name": r, "status": "would-add", "plain": f"Would copy {f.name} ({_human(f.stat().st_size)}) to {r}."})
            continue
        n = d.upload(f, r)
        sent += 1
        rows.append({"name": r, "status": "ok", "plain": f"Copied {f.name} ({_human(n)}) to {r}."})
    skipped = sum(r["status"] == "skipped" for r in rows)
    if ctx.dry_run:
        plain = f"Nothing was changed. I would copy {sum(r['status'] == 'would-add' for r in rows)} file(s)" + (f" and leave {skipped} that are already there." if skipped else ".")
    else:
        plain = f"Copied {sent} file(s) to OneDrive" + (f"; {skipped} already there were left as they are." if skipped else ".")
    return Resource("onedrive-add", remote, {"plain": plain, "files": rows, "account": d.label}, status=OK)


@command("onedrive", "sync", category="setup", summary="Copy a OneDrive file or folder to this machine; a local file that differs is kept unless you say so",
         args=(Arg("remote", "REMOTE", positional=True, required=True, help="a file or folder in OneDrive, from its root"),
               Arg("local", "LOCAL", positional=True, required=True, help="the folder on this machine it goes into"), ACCOUNT, REPLACE),
         surfaces=("cli", "editor"))
def onedrive_sync(ctx, remote, local, account=None, replace=False):
    d = graph.Drive(_label(account))
    root = d.show(remote)
    dest = Path(local).expanduser()
    todo = []           # (remote path, local path, size)

    def walk(rpath: str, lpath: Path):
        for e in d.children(rpath):
            if not graph.safe_name(e["name"]):
                continue
            rp, lp = f"{rpath.strip('/')}/{e['name']}".strip("/"), lpath / e["name"]
            walk(rp, lp) if e["kind"] == "folder" else todo.append((rp, lp, e["size"]))

    if root["kind"] == "folder":
        walk(remote, dest)
    else:
        todo.append((remote.strip("/"), dest / root["name"], root["size"]))
    rows, got = [], 0
    for rp, lp, size in todo:
        if lp.exists() and lp.stat().st_size == size:
            rows.append({"name": str(lp), "status": "ok", "plain": f"{lp} is already here."})
            continue
        if lp.exists() and not replace:
            rows.append({"name": str(lp), "status": "skipped", "plain": f"{lp} is here and differs, so I left it (--replace changes that)."})
            continue
        if ctx.dry_run:
            rows.append({"name": str(lp), "status": "would-add", "plain": f"Would copy {rp} ({_human(size)}) to {lp}."})
            continue
        d.download(rp, lp)
        got += 1
        rows.append({"name": str(lp), "status": "ok", "plain": f"Copied {rp} ({_human(size)}) to {lp}."})
    skipped = sum(r["status"] == "skipped" for r in rows)
    plain = (f"Nothing was changed. I would copy {sum(r['status'] == 'would-add' for r in rows)} file(s)." if ctx.dry_run else
             f"Copied {got} file(s) from OneDrive" + (f"; {skipped} different local file(s) were left as they are." if skipped else "."))
    return Resource("onedrive-sync", remote, {"plain": plain, "files": rows, "account": d.label}, status=OK)
