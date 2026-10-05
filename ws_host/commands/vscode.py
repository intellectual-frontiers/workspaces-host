"""`vscode ensure`: put VS Code in its recommended state, with the IF Console as its interface (0004-editor-extension FR-001 to FR-010).

The extension is the IF Console of the public root (0043-if-console in `.github`), built there by `agora extension build` and installed
with `code --install-extension`. ws-host holds no extension of its own."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from ..core import config, machine, paths, progress, registry as reg
from ..core.resource import Action, FAILED, OK, Resource, WsError
from ..install import fetch
from ..lib import git, repos, trust as trust_mod

CONSOLE_ID = "intellectual-frontiers.if-console"
OLD_IDS = ("intellectual-frontiers.workspaces-host",)       # the extension ws-host shipped before it used the IF Console
PUBLIC_ROOT = config.STARTER_REPOS[0]
BUILD_WAIT = 1800
RELEASE_API = "https://api.github.com/repos/intellectual-frontiers/.github/releases/latest"


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



def public_root(cfg) -> tuple[repos.RepoId, Path]:
    rid = repos.parse_id(PUBLIC_ROOT)
    return rid, rid.path(cfg)


def stamp_file() -> Path:
    return paths.state_dir() / "if-console"


def read_stamp() -> dict:
    try:
        return dict(l.split("=", 1) for l in stamp_file().read_text(encoding="utf-8").splitlines() if "=" in l)
    except OSError:
        return {}


def write_stamp(**kv) -> None:
    now = {**read_stamp(), **kv}
    stamp_file().parent.mkdir(parents=True, exist_ok=True)
    stamp_file().write_text("".join(f"{k}={v}\n" for k, v in sorted(now.items())), encoding="utf-8")


def console_installed_here() -> bool:
    """What the last `vscode ensure` recorded: cheap, and no call to VS Code. `workspace ensure` reads it to say what to do."""
    return bool(read_stamp().get("installed"))


def newest_vsix(root: Path) -> Path | None:
    found = sorted((root / "build").glob("if-console-*.vsix"), key=lambda p: p.stat().st_mtime)
    return found[-1] if found else None


def build_console(root: Path) -> Path:
    """Build the IF Console's package with the public root's own command line (0043-if-console FR-027). Raises WsError."""
    launcher = root / "agora"
    if not os.access(launcher, os.X_OK):
        raise WsError("no-builder", f"{launcher} is not there", "The public root's command line is missing, so I cannot build the IF Console. Update the public root first.",
                      [Action(("repo", "sync"), "Update the repositories", {"all": True})])
    try:
        with progress.working("Building the IF Console (the first time takes a minute or two)"):
            p = subprocess.run([str(launcher), "extension", "build"], cwd=str(root), capture_output=True, text=True, timeout=BUILD_WAIT)
    except subprocess.TimeoutExpired:
        raise WsError("build-timeout", "the build took too long", "Building the IF Console is taking very long, probably because the network is slow. Nothing was lost; run this again and it carries on.",
                      [Action(("vscode", "ensure"), "Try again")], exit_code=1)
    if p.returncode != 0:
        tail = " ".join((p.stderr or p.stdout).strip().splitlines()[-3:])
        raise WsError("build-failed", f"agora extension build exited {p.returncode}: {tail}", "I could not build the IF Console. " + (tail or ""),
                      [Action(("vscode", "ensure"), "Try again")], exit_code=1)
    vsix = newest_vsix(root)
    if vsix is None:
        raise WsError("no-package", "the build made no .vsix", "The build finished but made no package, so there is nothing to install.", exit_code=1)
    return vsix


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "ws-host", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def release_package(offline: bool = False) -> dict | None:
    """The public root's newest release that carries the IF Console's package with a SHA-256 digest, as {tag, name, url, sha256}; None when it
    has none, when GitHub cannot be reached or when the package has no digest to check (0004-editor-extension FR-026). Never raises."""
    if offline:
        return None
    try:
        rel = _get_json(RELEASE_API)
        for a in rel.get("assets", []):
            m = re.fullmatch(r"if-console-[0-9][A-Za-z0-9._-]*\.vsix", str(a.get("name", "")))
            digest = str(a.get("digest") or "")
            if m and digest.startswith("sha256:") and re.fullmatch(r"[0-9a-f]{64}", digest[7:]) and str(a.get("browser_download_url", "")).startswith("https://"):
                return {"tag": str(rel.get("tag_name", "")), "name": a["name"], "url": a["browser_download_url"], "sha256": digest[7:]}
    except (OSError, ValueError, AttributeError, KeyError):
        pass
    return None


def download_release(rel: dict) -> Path:
    """Fetch the release package, verify its SHA-256 before anything uses it, and give it the name VS Code needs. Raises fetch.FetchError."""
    with progress.working("Downloading the IF Console"):
        got = fetch.download(rel["url"], rel["sha256"])
    out = paths.cache_dir() / "if-console" / rel["name"]
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(got, out)
    return out


def release_step(ctx, rel: dict, have: set) -> dict:
    name = "IF Console extension"
    current = read_stamp().get("release") == rel["tag"] and CONSOLE_ID in have
    if ctx.dry_run:
        return {"name": name, "status": "already" if current else "would-install",
                "plain": "The IF Console is installed and current." if current else f"I would download and install the IF Console {rel['tag']} from the public root's release."}
    if not current:
        vsix = download_release(rel)
        r = run_code(["--install-extension", str(vsix), "--force"], "Installing the IF Console")
        if r.returncode != 0:
            raise WsError("code-install", (r.stderr or r.stdout).strip()[-300:], "VS Code's `code` command could not install the IF Console.", [Action(("vscode", "ensure"), "Try again")])
        write_stamp(release=rel["tag"], installed=rel["tag"])
    for old in OLD_IDS:
        if old in have:
            run_code(["--uninstall-extension", old], f"Removing the older {old.split('.')[-1]} extension")
    return {"name": name, "status": "already" if current else "installed",
            "plain": "The IF Console is installed and current." if current else f"Installed the IF Console {rel['tag']} from the public root's release, after checking its fingerprint. Reload VS Code's window to start it."}


def console_step(ctx, cfg, code: str | None, have: set) -> tuple[dict, list[Action]]:
    """Build the IF Console if the public root changed, install it if it is not there, and remove the extension ws-host used to ship."""
    name = "IF Console extension"
    rid, root = public_root(cfg)
    if not code:
        return {"name": name, "status": "skipped", "plain": "VS Code's `code` command is not available here yet; open VS Code from this terminal once with `code .`, then run this again."}, []
    note = ""
    rel = release_package(ctx.offline)
    if rel:
        try:
            return release_step(ctx, rel, have), []      # a published, verified package needs no build and no trust (FR-026)
        except fetch.FetchError as e:
            note = f" The release package could not be used ({e.message[:120]}), so I built it instead."
    if not (root / ".git").exists():
        return {"name": name, "status": "skipped", "plain": f"The public root ({rid.name}) is not on this machine yet, and the IF Console is built from it. Copy it first."}, \
               [Action(("workspace", "ensure"), "Ensure everything is set up and up to date")]
    ok, why = trust_mod.trust_state(rid, cfg)
    if not ok:
        trust_action = [Action(("repo", "set"), "Trust the public root", {"repo": str(rid), "trusted": True})]
        if ctx.dry_run:
            return {"name": name, "status": "would-install", "plain": "I would ask you to trust the public root, then build and install the IF Console."}, trust_action
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return {"name": name, "status": "skipped", "plain": "The IF Console is built by running the public root's own code, so you decide first whether to trust it."}, trust_action
        try:
            ctx.confirm(f"The IF Console is built by running code from {rid}. Trust it?")
            trust_mod.grant(rid, cfg)
        except WsError:
            return {"name": name, "status": "skipped", "plain": "You did not trust the public root, so I did not build the IF Console. Nothing was changed."}, trust_action
    head = git.out(root, "rev-parse", "HEAD")
    vsix = newest_vsix(root)
    stale = read_stamp().get("built") != head or vsix is None
    installed = CONSOLE_ID in have
    if ctx.dry_run:
        what = "build and install" if stale else "install" if not installed else "keep"
        return {"name": name, "status": "would-install" if what != "keep" else "already", "plain": f"I would {what} the IF Console." if what != "keep" else "The IF Console is installed and current."}, []
    built = False
    if stale:
        vsix = build_console(root)
        write_stamp(built=head)
        built = True
    if built or not installed:
        r = run_code(["--install-extension", str(vsix), "--force"], "Installing the IF Console")
        if r.returncode != 0:
            raise WsError("code-install", (r.stderr or r.stdout).strip()[-300:], "VS Code's `code` command could not install the IF Console.", [Action(("vscode", "ensure"), "Try again")])
        write_stamp(installed=head)
    for old in OLD_IDS:
        if old in have:
            run_code(["--uninstall-extension", old], f"Removing the older {old.split('.')[-1]} extension")
    plain = (("Built and installed the IF Console. Reload VS Code's window to start it." if built else
             "Installed the IF Console. Reload VS Code's window to start it." if not installed else "The IF Console is installed and current.") + note)
    return {"name": name, "status": "installed" if (built or not installed) else "already", "plain": plain}, []


def workspace_file(cfg) -> Path:
    return cfg.workspaces / "workspaces.code-workspace"


# What every workspace file opens with, added only where the person has not chosen a value (0004-editor-extension FR-028).
WORKSPACE_SETTINGS = {
    "window.title": "Workspaces${separator}${rootName}${separator}${activeEditorShort}",
    "explorer.compactFolders": False,
}


def workspace_step(cfg, dry: bool) -> dict:
    """A multi-root workspace of the repositories you work in, so the IF Console shows each repository's command line (0043 FR-007)."""
    f = workspace_file(cfg)
    wanted = []
    for r in sorted(repos.known(cfg)[0], key=str):
        if (r.path(cfg) / ".git").exists():
            try:
                rel = os.path.relpath(r.path(cfg), f.parent)
            except ValueError:
                rel = str(r.path(cfg))
            wanted.append({"path": rel, "name": r.name})
    name = "Workspace file"
    try:
        current = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        if not isinstance(current, dict):
            raise ValueError("not an object")
    except (ValueError, OSError) as e:
        return {"name": name, "status": "skipped", "plain": f"I left {f} alone because I cannot read it safely ({e})."}
    folders = list(current.get("folders", []))
    have = {os.path.normpath(os.path.join(f.parent, x.get("path", ""))) for x in folders if isinstance(x, dict)}
    add = [w for w in wanted if os.path.normpath(os.path.join(f.parent, w["path"])) not in have]
    settings = dict(current.get("settings", {})) if isinstance(current.get("settings", {}), dict) else {}
    recs = list(current.get("extensions", {}).get("recommendations", [])) if isinstance(current.get("extensions", {}), dict) else []
    fill = {k: v for k, v in WORKSPACE_SETTINGS.items() if k not in settings}
    want_rec = CONSOLE_ID not in recs
    if not f.exists() and not add:
        fill, want_rec = {}, False
    if not add and not fill and not want_rec:
        return {"name": name, "status": "already", "plain": f"{f.name} already lists your repositories." if f.exists() else "No repository is copied yet, so there is no workspace file to make."}
    if dry:
        return {"name": name, "status": "would-install", "plain": f"I would add {len(add)} repositor{'ies' if len(add) != 1 else 'y'} and the standard settings to {f}."}
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".code-workspace.new")
    out = {**current, "folders": folders + add, "settings": {**settings, **fill}}
    if want_rec:
        out["extensions"] = {**(current.get("extensions") if isinstance(current.get("extensions"), dict) else {}), "recommendations": recs + [CONSOLE_ID]}
    tmp.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, f)
    return {"name": name, "status": "installed", "plain": f"{f} lists your repositories. Open it in VS Code with `code {f}` (or File, Open Workspace from File) and always start from it, so every repository is in one window."}


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


@reg.command("vscode", "ensure", category="setup", summary="Put VS Code in its recommended state: the IF Console, helpful extensions and safe settings",
             surfaces=("cli", "editor"))
def vscode_ensure(ctx):
    steps, status, actions = [], OK, []
    code = shutil.which("code")
    cfg = config.load()
    if not ctx.dry_run:
        # Say what is about to happen, that nothing is needed from the person, and how long it can take, before anything slow starts.
        yield Resource("progress", "vscode-start", {"plain": f"Setting up VS Code: the IF Console, {len(RECOMMENDED)} helpful extensions and a few safe settings. "
                                                    "There is nothing for you to do while it works. " +
                                                    ("The first time, VS Code downloads a small helper into Debian and the IF Console is built, which can take a few minutes "
                                                     "on a slow network; the line below shows how it is going." if code and first_time_in_wsl() else
                                                     "It usually takes a few minutes the first time and under a minute after."), "step": "vscode-start"})
    have = set()
    if code:
        try:
            p = run_code(["--list-extensions"], "Asking VS Code what is installed")
        except WsError as e:
            yield Resource("vscode-setup", "vscode", {"plain": e.plain, "steps": steps, "settings": {}, "reload": ""}, actions=e.actions, status=FAILED)
            return
        have = {l.strip().lower() for l in p.stdout.splitlines() if l.strip()}
    try:
        step, more = console_step(ctx, cfg, code, have)
    except WsError as e:
        step, more = {"name": "IF Console extension", "status": "failed", "plain": e.plain}, list(e.actions)
        status = FAILED
    steps.append(step)
    actions += more
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
    steps.append(workspace_step(cfg, ctx.dry_run))
    s = merge_settings(settings_file(), baseline_settings(), ctx.dry_run)
    left = [r for r in steps if r["status"] in ("skipped", "failed")]
    plain = ("Nothing was changed. This is what I would set up." if ctx.dry_run else
             "VS Code is set up." if not left and s["status"] != "left-alone" else
             "VS Code is partly set up. " + ("The steps below say what is left." if left else s["plain"]))
    done = not ctx.dry_run and not left
    yield Resource("vscode-setup", "vscode", {"plain": plain, "steps": [{**r, "status": "ok" if r["status"] in ("installed", "already", "would-install") else "warn" if r["status"] == "skipped" else "fail"} for r in steps],
                                              "settings": s, "reload": "Reload VS Code's window (Ctrl+Shift+P, then Developer: Reload Window) so everything starts." if not ctx.dry_run else "",
                                              **({"next": f"Open {workspace_file(cfg)} in VS Code (File, Open Workspace from File), then press Ctrl+Shift+P and run IF Console: Learn a Topic."} if done else {})},
                   actions=(actions or []) + ([] if not left or actions else [Action(("vscode", "ensure"), "Try again")]),
                   status=FAILED if any(r["status"] == "failed" for r in steps) else status)
