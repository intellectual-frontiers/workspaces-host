"""`vscode add`: install the editor extension (0004-editor-extension FR-016)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from ..core import machine, paths, registry as reg
from ..core.resource import Action, FAILED, OK, Resource, WsError

CT = ('<?xml version="1.0" encoding="utf-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
      '<Default Extension=".json" ContentType="application/json"/><Default Extension=".js" ContentType="application/javascript"/>'
      '<Default Extension=".md" ContentType="text/markdown"/><Default Extension=".vsixmanifest" ContentType="text/xml"/></Types>')


def extension_dir() -> Path:
    return paths.repo_root() / "vscode"


def manifest() -> dict:
    return json.loads((extension_dir() / "package.json").read_text(encoding="utf-8"))


def ident(m: dict | None = None) -> tuple[str, str]:
    m = m or manifest()
    return f"{m['publisher']}.{m['name']}", m["version"]


def target_extensions_dir() -> Path:
    """VS Code's WSL mode keeps extensions in ~/.vscode-server (0004 FR-016)."""
    wsl = machine.distro()["wsl"]
    return paths.home() / (".vscode-server" if wsl else ".vscode") / "extensions"


def build_vsix(dest: Path) -> Path:
    m = manifest()
    ext_id, version = ident(m)
    vm = ('<?xml version="1.0" encoding="utf-8"?><PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">'
          f'<Metadata><Identity Language="en-US" Id="{m["name"]}" Version="{version}" Publisher="{m["publisher"]}"/>'
          f'<DisplayName>{m.get("displayName", m["name"])}</DisplayName><Description xml:space="preserve">{m.get("description", "")}</Description></Metadata>'
          '<Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation><Dependencies/>'
          '<Assets><Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/></Assets></PackageManifest>')
    out = dest / f"{ext_id}-{version}.vsix"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CT)
        z.writestr("extension.vsixmanifest", vm)
        for f in sorted(extension_dir().rglob("*")):
            if f.is_file() and "node_modules" not in f.parts:
                z.write(f, "extension/" + f.relative_to(extension_dir()).as_posix())
    return out


def register(index: Path, ext_dir: Path, ext_id: str, version: str, folder: str) -> bool:
    """Add or replace this extension's entry in extensions.json, keeping every other entry. True when it changed."""
    entries = json.loads(index.read_text(encoding="utf-8"))
    entry = {"identifier": {"id": ext_id}, "version": version,
             "location": {"$mid": 1, "path": str(ext_dir / folder), "scheme": "file"}, "relativeLocation": folder,
             "metadata": {"installedTimestamp": 0, "pinned": True, "source": "vsix"}}
    others = [e for e in entries if e.get("identifier", {}).get("id", "").lower() != ext_id.lower()]
    new = others + [entry]
    if new == entries:
        return False
    tmp = index.with_suffix(".json.new")
    tmp.write_text(json.dumps(new), encoding="utf-8")
    os.replace(tmp, index)
    return True


@reg.command("vscode", "add", category="setup", summary="Install the VS Code extension that is the interface for every orchestrator")
def vscode_add(ctx):
    ext_id, version = ident()
    folder = f"{ext_id}-{version}"
    ext_dir = target_extensions_dir()
    link, index = ext_dir / folder, ext_dir / "extensions.json"
    src = extension_dir()
    if not (src / "extension.js").is_file():
        raise WsError("missing-extension", "vscode/extension.js is missing", "The extension's files are missing from this copy of ws-host.", exit_code=1)
    plan = {"extension": ext_id, "version": version, "directory": str(ext_dir), "link": str(link), "index": str(index) if index.is_file() else None}
    if ctx.dry_run:
        how = "link it and list it in extensions.json" if index.is_file() else "build a .vsix and install it with `code`" if shutil.which("code") else "link it"
        return Resource("vscode-add", ext_id, {"plain": f"Nothing was changed. I would {how}.", **plan})
    notes = []
    if index.is_file():
        ext_dir.mkdir(parents=True, exist_ok=True)
        _link(link, src)
        changed = register(index, ext_dir, ext_id, version, folder)
        notes.append("linked the extension" + (" and listed it" if changed else "; it was already listed"))
        plain = "The extension is installed. Reload VS Code's window to start it."
    elif shutil.which("code"):
        with tempfile.TemporaryDirectory() as d:
            vsix = build_vsix(Path(d))
            p = subprocess.run(["code", "--install-extension", str(vsix), "--force"], capture_output=True, text=True, timeout=300)
        if p.returncode != 0:
            raise WsError("code-install", (p.stderr or p.stdout).strip()[-300:], "VS Code's `code` command could not install the extension.")
        notes.append("installed it with `code --install-extension`")
        plain = "The extension is installed. Reload VS Code's window to start it. After ws-host updates, run `ws-host vscode add` again."
    else:
        ext_dir.mkdir(parents=True, exist_ok=True)
        _link(link, src)
        notes.append("linked the extension, but found neither VS Code's list of extensions nor the `code` command")
        plain = "I linked the extension, but VS Code has not been run here yet, so I could not list it. Open VS Code once, then run this again."
    return Resource("vscode-add", ext_id, {"plain": plain, **plan, "did": notes}, status=OK)


def _link(link: Path, src: Path) -> None:
    if link.is_symlink() and Path(os.readlink(link)).resolve() == src.resolve():
        return
    if link.exists() or link.is_symlink():
        if link.is_symlink():
            link.unlink()
        else:
            raise WsError("in-the-way", f"{link} exists and is not a link", f"Something is already at {link}, so I did not replace it.", exit_code=1)
    os.symlink(src, link)
