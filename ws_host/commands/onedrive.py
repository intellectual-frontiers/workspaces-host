"""`onedrive list|show|add|sync`: a signed-in Microsoft account's OneDrive, through Microsoft Graph (0003-kits FR-021).

Nothing is ever replaced or deleted without `--replace`: `add` leaves a file that is already in OneDrive, `sync` leaves a local file that differs, and both say so."""
from __future__ import annotations

from pathlib import Path

from ..core import progress
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


UPDATE = Arg("update", flag=True, help="copy new files, and replace the ones whose content has changed here; OneDrive keeps each earlier one as a version. Files that are the same are left alone")
EXCLUDE = Arg("exclude", multiple=True, help="leave out names that match this pattern, such as '*.tmp' or '.*' (any part of the path; repeat it for more)")


def _left_out(rel: str, patterns: tuple[str, ...]) -> bool:
    import fnmatch
    parts = rel.split("/")
    return any(fnmatch.fnmatch(rel, p) or any(fnmatch.fnmatch(x, p) for x in parts) for p in patterns)


def _same(local: Path, remote: dict) -> bool:
    """Whether the copy in OneDrive holds this file's bytes: by the checksum OneDrive states, and by size and date when it states none."""
    from ..lib import quickxor
    st = local.stat()
    if st.st_size != remote.get("size"):
        return False
    if remote.get("sha1"):
        return quickxor.sha1_file(local) == remote["sha1"].upper()
    if remote.get("quickxor"):
        return quickxor.quickxor_file(local) == remote["quickxor"]
    import datetime
    try:
        theirs = datetime.datetime.fromisoformat(remote.get("modified", "").replace("Z", "+00:00")).timestamp()
    except ValueError:
        return False
    return st.st_mtime <= theirs


def _verified(local: Path, item: dict) -> bool:
    """After a copy, OneDrive's own checksum of what it now holds, against this file's: True when they agree or it states none."""
    if not item:
        return True
    if item.get("sha1") or item.get("quickxor"):
        return _same(local, {**item, "size": local.stat().st_size})
    return True


ALSO = Arg("also", multiple=True, help="LOCAL=REMOTE: another folder and where it goes; copy several in one run, which signs in once and is much faster than one run each")


def _pairs(local: str, remote: str, also: tuple[str, ...]) -> list[tuple[Path, str]]:
    out = [(Path(local).expanduser(), remote.strip("/"))]
    for item in also:
        src, sep, dest = item.partition("=")
        if not sep or not src or not dest.strip("/"):
            raise WsError("usage", f"--also {item!r} is not LOCAL=REMOTE", "Each --also needs a folder on this machine, an equals sign, and where it goes in OneDrive, such as /home/me/a=Backups/a.", exit_code=2)
        out.append((Path(src).expanduser(), dest.strip("/")))
    return out


@command("onedrive", "add", category="setup", summary="Copy a local file or folder into OneDrive; with --update, new files and changed ones; nothing is replaced unless you say so",
         args=(Arg("local", "LOCAL", positional=True, required=True, help="a file or folder on this machine"),
               Arg("remote", "REMOTE", positional=True, required=True, help="where in OneDrive it goes, from the root, such as Documents/report.docx"), ACCOUNT, REPLACE, UPDATE, EXCLUDE, ALSO),
         surfaces=("cli", "editor"))
def onedrive_add(ctx, local, remote, account=None, replace=False, update=False, exclude=(), also=()):
    pairs = _pairs(local, remote, tuple(also))
    for src, _ in pairs:
        if not src.exists():
            raise WsError("no-such-file", f"{src} is not there", f"I cannot find {src} on this machine.", exit_code=2)
    d = graph.Drive(_label(account))
    listed: dict[str, dict[str, dict]] = {}

    def listing(folder: str) -> dict[str, dict]:
        """What is in a folder of OneDrive. A folder whose parent does not hold it is empty, so nothing is asked about it: a first copy of a big tree asks about its top and no further."""
        if folder not in listed:
            if folder:
                parent, _, name = folder.rpartition("/")
                held = listing(parent).get(name)
                listed[folder] = d.listing(folder) if held and held.get("kind") == "folder" else {}
            else:
                listed[folder] = d.listing(folder)
        return listed[folder]

    def ensure_folder(fol: str) -> None:
        parent, _, name = fol.rpartition("/")
        if name in listing(parent):
            return
        d.make_folder(fol)
        listing(parent)[name] = {"name": name, "kind": "folder"}
        listed[fol] = {}

    rows, parts = [], []
    totals = {"new": 0, "updated": 0, "same": 0, "left": 0, "wrong": 0}
    with progress.step("📤 Copying to OneDrive"):
        for number, (src, base) in enumerate(pairs, 1):
            progress.detail(f"{number} of {len(pairs)}: {base}")
            if src.is_file():
                files = [(src, base)]
            else:
                files = [(f, f"{base}/{f.relative_to(src).as_posix()}") for f in sorted(src.rglob("*"))
                         if f.is_file() and not _left_out(f.relative_to(src).as_posix(), tuple(exclude))]
            wanted = {base} | {r.rpartition("/")[0] for _, r in files}
            folders = [] if src.is_file() else sorted({"/".join(w.split("/")[:i]) for w in wanted for i in range(1, len(w.split("/")) + 1)}, key=lambda x: x.count("/"))
            if not ctx.dry_run:
                for fol in folders:
                    if fol:
                        ensure_folder(fol)
            counts = {"new": 0, "updated": 0, "same": 0, "left": 0, "wrong": 0}
            for f, r in files:
                folder, _, name = r.rpartition("/")
                there = listing(folder).get(name)
                if there is None:
                    action = "new"
                elif replace:
                    action = "updated"
                elif update:
                    if _same(f, there):
                        counts["same"] += 1
                        rows.append({"name": r, "status": "ok", "plain": f"{r} is already up to date."})
                        continue
                    action = "updated"
                else:
                    counts["left"] += 1
                    rows.append({"name": r, "status": "skipped", "plain": f"{r} is already in OneDrive, so I left it (--update copies it if it changed, --replace always does)."})
                    continue
                if ctx.dry_run:
                    rows.append({"name": r, "status": "would-add", "plain": f"Would copy {f.name} ({_human(f.stat().st_size)}) to {r} ({'new' if action == 'new' else 'changed'})."})
                    counts[action] += 1
                    continue
                n, item = d.upload(f, r)
                counts[action] += 1
                if _verified(f, item):
                    rows.append({"name": r, "status": "ok", "plain": f"{'Copied' if action == 'new' else 'Updated'} {f.name} ({_human(n)}) to {r}."})
                else:
                    counts["wrong"] += 1
                    rows.append({"name": r, "status": "warn", "plain": f"Copied {f.name} to {r}, but OneDrive's checksum for it is not this file's. Run the command again; if it stays, tell whoever looks after ws-host."})
            for k, v in counts.items():
                totals[k] += v
            parts.append({"remote": base, "new": counts["new"], "updated": counts["updated"], "unchanged": counts["same"], "left": counts["left"], "checksum_differs": counts["wrong"]})
    if ctx.dry_run:
        plain = (f"Nothing was changed. I would copy {totals['new']} new file(s) and update {totals['updated']}"
                 + (f"; {totals['same']} are already up to date" if totals["same"] else "") + (f"; {totals['left']} that are there would be left" if totals["left"] else "") + ".")
    else:
        plain = (f"Copied {totals['new']} new file(s) and updated {totals['updated']}" + (f"; {totals['same']} were already up to date" if totals["same"] else "")
                 + (f"; {totals['left']} already there were left as they are" if totals["left"] else "") + ".")
    return Resource("onedrive-add", remote, {"plain": plain, "files": rows, "parts": parts, "account": d.label, "new": totals["new"], "updated": totals["updated"], "unchanged": totals["same"],
                                              "left": totals["left"], "checksum_differs": totals["wrong"]}, status=OK)


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
