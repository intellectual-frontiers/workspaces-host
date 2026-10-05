"""`vscode add`: install the editor extension (0004-editor-extension FR-016)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from ..core import machine, paths, progress, registry as reg
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


CODE_WAIT = 900     # seconds: the first call downloads VS Code's Linux helper into WSL, which is slow on a slow network


def first_time_in_wsl() -> bool:
    return bool(machine.distro()["wsl"]) and not (paths.home() / ".vscode-server" / "bin").exists()


def run_code(args: list[str], label: str, timeout: int = CODE_WAIT) -> subprocess.CompletedProcess:
    """Run VS Code's `code` command as one visible step: a spinner with the helper's download size, and a plain error when it takes too long.
    The first call in WSL makes Windows' `code` fetch VS Code's Linux helper into ~/.vscode-server and says nothing while it does."""
    probe = progress.folder_megabytes(paths.home() / ".vscode-server", "downloaded") if first_time_in_wsl() else None
    try:
        with progress.working(label, probe):
            return subprocess.run(["code", *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise WsError("code-timeout", f"`code {args[0]}` took longer than {timeout // 60} minutes",
                      "VS Code's `code` command is taking very long, probably because the network is slow. Nothing was lost. Run this again and it will "
                      "carry on from where it got to.", [Action(("vscode", "ensure"), "Try again")], exit_code=1)


def install_extension(dry: bool = False) -> dict:
    """Install the extension (0004-editor-extension FR-016). Returns {plain, did, plan}; raises WsError."""
    ext_id, version = ident()
    folder = f"{ext_id}-{version}"
    ext_dir = target_extensions_dir()
    link, index = ext_dir / folder, ext_dir / "extensions.json"
    src = extension_dir()
    if not (src / "extension.js").is_file():
        raise WsError("missing-extension", "vscode/extension.js is missing", "The extension's files are missing from this copy of ws-host.", exit_code=1)
    plan = {"extension": ext_id, "version": version, "directory": str(ext_dir), "link": str(link), "index": str(index) if index.is_file() else None}
    if dry:
        how = "link it and list it in extensions.json" if index.is_file() else "build a .vsix and install it with `code`" if shutil.which("code") else "link it"
        return {"plain": f"Nothing was changed. I would {how}.", "did": [], "plan": plan}
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
            p = run_code(["--install-extension", str(vsix), "--force"], "Setting up VS Code inside Debian (the first time downloads its helper)")
        if p.returncode != 0:
            raise WsError("code-install", (p.stderr or p.stdout).strip()[-300:], "VS Code's `code` command could not install the extension.")
        notes.append("installed it with `code --install-extension`")
        plain = "The extension is installed. Reload VS Code's window to start it. After ws-host updates, run `ws-host vscode add` again."
    else:
        ext_dir.mkdir(parents=True, exist_ok=True)
        _link(link, src)
        notes.append("linked the extension, but found neither VS Code's list of extensions nor the `code` command")
        plain = "I linked the extension, but VS Code has not been run here yet, so I could not list it. Open VS Code once, then run this again."
    return {"plain": plain, "did": notes, "plan": plan}


def extension_installed() -> bool:
    ext_id, version = ident()
    return (target_extensions_dir() / f"{ext_id}-{version}").exists()


@reg.command("vscode", "add", category="setup", summary="Install the VS Code extension that is the interface for every orchestrator")
def vscode_add(ctx):
    r = install_extension(ctx.dry_run)
    return Resource("vscode-add", r["plan"]["extension"], {"plain": r["plain"], **r["plan"], **({"did": r["did"]} if r["did"] else {})}, status=OK)


def _link(link: Path, src: Path) -> None:
    if link.is_symlink() and Path(os.readlink(link)).resolve() == src.resolve():
        return
    if link.exists() or link.is_symlink():
        if link.is_symlink():
            link.unlink()
        else:
            raise WsError("in-the-way", f"{link} exists and is not a link", f"Something is already at {link}, so I did not replace it.", exit_code=1)
    os.symlink(src, link)


# What `vscode ensure` puts in place so a person does not have to think about it (0006-onboarding FR-007 to FR-009).
RECOMMENDED = (
    ("GitHub.vscode-pull-request-github", "GitHub pull requests and issues, inside the editor"),
    ("eamodio.gitlens", "who changed each line, and when"),
    ("ms-python.python", "Python, which ws-host and its kits are written in"),
    ("asciidoctor.asciidoctor-vscode", "preview of the guide's AsciiDoc pages"),
    ("timonwong.shellcheck", "catches mistakes in shell scripts"),
)


def baseline_settings() -> dict:
    return {
        "files.autoSave": "afterDelay",
        "git.autofetch": True,
        "git.enableSmartCommit": False,
        "workbench.startupEditor": "none",
        "security.workspace.trust.enabled": True,
        "extensions.ignoreRecommendations": False,
        "terminal.integrated.defaultProfile.linux": "fish" if shutil.which("fish") else "bash",
        "terminal.integrated.fontFamily": "'MesloLGS NF', 'CaskaydiaCove Nerd Font', 'DejaVu Sans Mono', monospace",
    }


def settings_file() -> Path:
    """VS Code under WSL keeps machine-wide settings in ~/.vscode-server/data/Machine; elsewhere the user's own file."""
    if machine.distro()["wsl"]:
        return paths.home() / ".vscode-server" / "data" / "Machine" / "settings.json"
    return paths.home() / ".config" / "Code" / "User" / "settings.json"


def merge_settings(f: Path, wanted: dict, dry: bool) -> dict:
    """Add the settings the person has not set; never change one they have. A file with comments is left alone and said so."""
    try:
        text = f.read_text(encoding="utf-8") if f.exists() else "{}"
        current = json.loads(text or "{}")
        if not isinstance(current, dict):
            raise ValueError("not an object")
    except (ValueError, OSError) as e:
        return {"file": str(f), "status": "left-alone", "added": [], "kept": [],
                "plain": f"I left {f.name} alone because I cannot read it safely ({e}); it probably has comments. Add these yourself: "
                         + ", ".join(f"{k} = {json.dumps(v)}" for k, v in wanted.items())}
    added = {k: v for k, v in wanted.items() if k not in current}
    kept = [k for k in wanted if k in current and current[k] != wanted[k]]
    if added and not dry:
        f.parent.mkdir(parents=True, exist_ok=True)
        if f.exists():
            bk = paths.state_dir() / "backups"
            bk.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, bk / "vscode-settings.json")
        merged = {**current, **added}
        tmp = f.with_suffix(".json.new")
        tmp.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, f)
    return {"file": str(f), "status": "would-add" if dry and added else ("added" if added else "unchanged"),
            "added": sorted(added), "kept": sorted(kept), "plain": ""}


@reg.command("vscode", "ensure", category="setup", summary="Put VS Code in its recommended state: the extension, helpful extensions and safe settings",
             surfaces=("cli", "editor"))
def vscode_ensure(ctx):
    steps, status = [], OK
    code = shutil.which("code")
    if not ctx.dry_run:
        # Say what is about to happen, that nothing is needed from the person, and how long it can take, before anything slow starts.
        yield Resource("progress", "vscode-start", {"plain": f"Setting up VS Code: the Workspace extension, {len(RECOMMENDED)} helpful extensions and a few safe settings. "
                                                    "There is nothing for you to do while it works. " +
                                                    ("The first time, VS Code downloads a small helper into Debian, which can take a few minutes on a slow network; the line below "
                                                     "shows how much has arrived." if code and first_time_in_wsl() else "It usually takes under a minute."), "step": "vscode-start"})
    ext = {"name": "Workspace extension", "status": "skipped"}
    try:
        r = install_extension(ctx.dry_run)
        ext = {"name": "Workspace extension", "status": "would-install" if ctx.dry_run else "installed", "plain": r["plain"]}
    except WsError as e:
        ext = {"name": "Workspace extension", "status": "failed", "plain": e.plain}
        status = FAILED
    steps.append(ext)
    have = set()
    if code:
        try:
            p = run_code(["--list-extensions"], "Asking VS Code what is installed")
        except WsError as e:
            yield Resource("vscode-setup", "vscode", {"plain": e.plain, "steps": steps, "settings": {}, "reload": ""},
                           actions=e.actions, status=FAILED)
            return
        have = {l.strip().lower() for l in p.stdout.splitlines() if l.strip()}
    for n, (ext_id, why) in enumerate(RECOMMENDED, 1):
        row = {"name": ext_id, "why": why}
        if not code:
            row["status"] = "skipped"
            row["plain"] = "VS Code's `code` command is not available here yet; open VS Code from this terminal once with `code .`, then run this again."
        elif ext_id.lower() in have:
            row["status"] = "already"
        elif ctx.dry_run:
            row["status"] = "would-install"
        else:
            try:
                q = run_code(["--install-extension", ext_id, "--force"], f"Installing {ext_id} ({n} of {len(RECOMMENDED)})")
            except WsError as e:
                row["status"], row["plain"] = "failed", e.plain
                steps.append(row)
                break
            row["status"] = "installed" if q.returncode == 0 else "failed"
            if q.returncode != 0:
                row["plain"] = (q.stderr or q.stdout).strip()[-200:]
        steps.append(row)
    s = merge_settings(settings_file(), baseline_settings(), ctx.dry_run)
    left = [r for r in steps if r["status"] in ("skipped", "failed")]
    plain = ("Nothing was changed. This is what I would set up." if ctx.dry_run else
             "VS Code is set up." if not left and s["status"] != "left-alone" else
             "VS Code is partly set up. " + ("The steps below say what is left." if left else s["plain"]))
    done = not ctx.dry_run and not left
    yield Resource("vscode-setup", "vscode", {"plain": plain, "steps": [{**r, "status": "ok" if r["status"] in ("installed", "already", "would-install") else "warn" if r["status"] == "skipped" else "fail"} for r in steps],
                                              "settings": s, "reload": "Reload VS Code's window (Ctrl+Shift+P, then Developer: Reload Window) so everything starts." if not ctx.dry_run else "",
                                              **({"next": "Open VS Code in this folder with `code .`, or reload its window if it is open, then press Ctrl+Shift+P and run Workspace: Learn."} if done else {})},
                   actions=[] if not left else [Action(("vscode", "ensure"), "Try again")], status=FAILED if any(r["status"] == "failed" for r in steps) else status)
