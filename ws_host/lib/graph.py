"""OneDrive through Microsoft Graph (0003-kits FR-021): the signed-in account's files, over Graph's REST API with a token that Microsoft's own library (the `microsoft` kit's
azure-identity, run by `msauth`) obtained. Standard library only, so it is tested against a stand-in Graph."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from ..core import config, paths
from ..core.resource import Action, WsError

SIMPLE_LIMIT = 4 * 1024 * 1024          # a file up to this is sent in one request; a larger one through an upload session
CHUNK = 32 * 320 * 1024                 # an upload session takes pieces that are a multiple of 320 KiB
KIT = "microsoft"
PACKAGE_DIR = "microsoft-identity"


def base() -> str:
    return (os.environ.get("WS_HOST_GRAPH_URL") or "https://graph.microsoft.com/v1.0").rstrip("/")


def state_file(label: str) -> Path:
    return paths.state_dir() / "microsoft" / f"{label}.json"


def accounts() -> list[str]:
    d = paths.state_dir() / "microsoft"
    return sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []


def venv_python() -> Path:
    return paths.tools_dir() / PACKAGE_DIR / "current" / "bin" / "python"


def kit_here() -> bool:
    return venv_python().exists()


def need_kit() -> WsError:
    return WsError("missing-kit", "the microsoft kit is not installed", "I need the Microsoft sign-in library, and it is not installed yet.",
                   [Action(("kit", "add"), "Install the microsoft kit", {"kit": KIT})], status="missing")


def _run_msauth(*args: str, stdout=subprocess.PIPE, text=True) -> subprocess.Popen:
    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(x for x in (str(root), os.environ.get("PYTHONPATH", "")) if x), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.Popen([str(venv_python()), "-m", "ws_host.lib.msauth", *args], stdout=stdout, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=text, env=env)


def sign_in(label: str):
    """Yields the lines `msauth login` prints, as dicts; the last is `done` or `error`."""
    cfg = config.load()
    f = state_file(label)
    proc = _run_msauth("login", label, str(f), cfg.get("WS_HOST_MICROSOFT_CLIENT_ID") or "14d82eec-204b-4c2f-b7e8-296a70dab67e", cfg.get("WS_HOST_MICROSOFT_TENANT") or "common")
    for line in proc.stdout:
        try:
            yield json.loads(line)
        except ValueError:
            continue
    rc = proc.wait()
    if rc != 0:
        yield {"event": "error", "message": (proc.stderr.read() or "").strip()[-300:] or "the sign-in did not finish"}


def _token(label: str) -> str:
    """The access token for `label`; raises WsError, with the way to sign in again, when there is none."""
    if not state_file(label).exists():
        raise WsError("not-signed-in", f"not signed in to Microsoft as {label}", f"You are not signed in to Microsoft as '{label}'.",
                      [Action(("auth", "new"), "Sign in to Microsoft", {"forge": "microsoft", "host": label})], status="missing")
    if not kit_here():
        raise need_kit()
    proc = _run_msauth("token", str(state_file(label)))
    out, err = proc.communicate(timeout=120)
    for line in out.splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("event") == "token":
            return d["token"]
    raise WsError("signed-out", f"the Microsoft sign-in for {label} has expired", f"Your Microsoft sign-in as '{label}' has expired, so I need you to sign in again.",
                  [Action(("auth", "new"), "Sign in to Microsoft", {"forge": "microsoft", "host": label})], status="missing")


token_for = _token          # the seam a test replaces


class Drive:
    """One account's OneDrive. Paths are from the root of the drive, `Documents/report.docx`."""

    def __init__(self, label: str):
        self.label = label
        self._tok = token_for(label)

    def _call(self, method: str, url: str, data: bytes | None = None, headers: dict | None = None, auth: bool = True, raw: bool = False):
        h = {"User-Agent": "ws-host", **(headers or {})}
        if auth:
            h["Authorization"] = f"Bearer {self._tok}"
        req = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read()
                return body if raw else (json.loads(body) if body else {})
        except urllib.error.HTTPError as e:
            raise WsError("graph", f"Graph said {e.code} for {method} {urllib.parse.urlparse(url).path}", self._why(e),
                          [Action(("auth", "new"), "Sign in again", {"forge": "microsoft", "host": self.label})] if e.code == 401 else []) from e
        except OSError as e:
            raise WsError("unreachable", f"could not reach {url}: {e}", "I could not reach Microsoft. Check your network and try again.") from e

    @staticmethod
    def _why(e: urllib.error.HTTPError) -> str:
        try:
            msg = json.loads(e.read()).get("error", {}).get("message", "")
        except (ValueError, OSError):
            msg = ""
        if e.code == 401:
            return "Microsoft did not accept the sign-in; sign in again."
        if e.code == 403:
            return "Microsoft says this account is not allowed to do that" + (f": {msg}" if msg else ".") + " A work account may need an administrator to approve the app."
        if e.code == 404:
            return "That file or folder is not in your OneDrive."
        return msg or "Microsoft refused the request."

    def _item(self, path: str) -> str:
        p = path.strip("/")
        return f"{base()}/me/drive/root" + (f":/{urllib.parse.quote(p)}:" if p else "")

    def me(self) -> dict:
        d = self._call("GET", f"{base()}/me")
        return {"name": d.get("displayName", ""), "email": d.get("mail") or d.get("userPrincipalName", "")}

    def show(self, path: str) -> dict:
        return self._entry(self._call("GET", self._item(path)))

    @staticmethod
    def _entry(d: dict) -> dict:
        folder = "folder" in d
        return {"name": d.get("name", ""), "kind": "folder" if folder else "file", "size": d.get("size", 0), "modified": d.get("lastModifiedDateTime", ""),
                "children": (d.get("folder") or {}).get("childCount"), "id": d.get("id", ""), "web_url": d.get("webUrl", "")}

    def children(self, path: str) -> list[dict]:
        url = self._item(path) + "/children?$top=200"
        out = []
        while url:
            d = self._call("GET", url)
            out += [self._entry(x) for x in d.get("value", [])]
            url = d.get("@odata.nextLink")
        return out

    def download(self, path: str, dest: Path) -> int:
        meta = self._call("GET", self._item(path) + "?select=@microsoft.graph.downloadUrl,size")
        link = meta.get("@microsoft.graph.downloadUrl")
        if not link:
            raise WsError("not-a-file", f"{path} is not a file", f"'{path}' is a folder, so there is nothing to download as one file.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".part")
        try:
            req = urllib.request.Request(link, headers={"User-Agent": "ws-host"})       # a link Microsoft made for this file: no sign-in is sent to it
            with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f)
        except OSError as e:
            tmp.unlink(missing_ok=True)
            raise WsError("unreachable", f"download failed: {e}", "The download did not finish, so I kept nothing of it.") from e
        os.replace(tmp, dest)
        return dest.stat().st_size

    def upload(self, src: Path, remote: str) -> int:
        size = src.stat().st_size
        target = self._item(remote)
        if size <= SIMPLE_LIMIT:
            self._call("PUT", target + "/content", src.read_bytes(), {"Content-Type": "application/octet-stream"})
            return size
        sess = self._call("POST", target + "/createUploadSession", json.dumps({"item": {"@microsoft.graph.conflictBehavior": "replace"}}).encode(),
                          {"Content-Type": "application/json"})
        url = sess["uploadUrl"]
        with open(src, "rb") as f:
            start = 0
            while start < size:
                chunk = f.read(CHUNK)
                end = start + len(chunk) - 1
                self._call("PUT", url, chunk, {"Content-Range": f"bytes {start}-{end}/{size}"}, auth=False)
                start = end + 1
        return size

    def make_folder(self, remote: str) -> None:
        parent, _, name = remote.strip("/").rpartition("/")
        try:            # `fail`, never `replace`: a folder that is there is kept, with everything in it
            self._call("POST", self._item(parent) + "/children", json.dumps({"name": name, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"}).encode(),
                       {"Content-Type": "application/json"})
        except WsError as e:
            if "409" not in e.message:
                raise


def safe_name(name: str) -> bool:
    """A name Microsoft sent that is safe to make a local file of: no folder parts, nothing hidden by dots alone."""
    return bool(name) and name not in (".", "..") and "/" not in name and "\\" not in name and "\x00" not in name
