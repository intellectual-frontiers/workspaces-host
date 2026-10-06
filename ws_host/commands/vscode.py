"""`vscode ensure`: put VS Code in its recommended state, with the Workspaces Console as its interface (0004-editor-extension).

The extension is the Workspaces Console, built and released from this repository (`console/`, 0007-releases). `vscode ensure` installs the package
of the latest GitHub release after checking its SHA-256, and builds nothing on the person's machine."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path

from ..core import config, machine, paths, progress, registry as reg
from ..core.registry import Arg, command
from ..core.resource import Action, FAILED, OK, Resource, WsError
from ..install import fetch
from ..lib import chezmoi, repos

CONSOLE_ID = "intellectual-frontiers.workspaces-console"
RELEASE_API = "https://api.github.com/repos/intellectual-frontiers/workspaces-host/releases/latest"


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



def stamp_file() -> Path:
    return paths.state_dir() / "workspaces-console"


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


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "ws-host", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def release_package(offline: bool = False) -> dict | None:
    """The public root's newest release that carries the Workspaces Console's package with a SHA-256 digest, as {tag, name, url, sha256}; None when it
    has none, when GitHub cannot be reached or when the package has no digest to check (0004-editor-extension FR-026). Never raises."""
    if offline:
        return None
    try:
        rel = _get_json(RELEASE_API)
        for a in rel.get("assets", []):
            m = re.fullmatch(r"workspaces-console-[0-9][A-Za-z0-9._-]*\.vsix", str(a.get("name", "")))
            digest = str(a.get("digest") or "")
            if m and digest.startswith("sha256:") and re.fullmatch(r"[0-9a-f]{64}", digest[7:]) and str(a.get("browser_download_url", "")).startswith("https://"):
                return {"tag": str(rel.get("tag_name", "")), "name": a["name"], "url": a["browser_download_url"], "sha256": digest[7:]}
    except (OSError, ValueError, AttributeError, KeyError):
        pass
    return None


def download_release(rel: dict) -> Path:
    """Fetch the release package, verify its SHA-256 before anything uses it, and give it the name VS Code needs. Raises fetch.FetchError."""
    with progress.working("📥 Downloading the Workspaces Console"):
        got = fetch.download(rel["url"], rel["sha256"])
    out = paths.cache_dir() / "workspaces-console" / rel["name"]
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(got, out)
    return out


def release_step(ctx, rel: dict, have: set) -> dict:
    name = "Workspaces Console extension"
    current = read_stamp().get("release") == rel["tag"] and CONSOLE_ID in have
    if ctx.dry_run:
        return {"name": name, "status": "already" if current else "would-install",
                "plain": "The Workspaces Console is installed and current." if current else f"I would download and install the Workspaces Console {rel['tag']} from the public root's release."}
    if not current:
        vsix = download_release(rel)
        r = run_code(["--install-extension", str(vsix), "--force"], "📦 Installing the Workspaces Console")
        if r.returncode != 0:
            raise WsError("code-install", (r.stderr or r.stdout).strip()[-300:], "VS Code's `code` command could not install the Workspaces Console.", [Action(("vscode", "ensure"), "Try again")])
        write_stamp(release=rel["tag"], installed=rel["tag"])
    return {"name": name, "status": "already" if current else "installed",
            "plain": "The Workspaces Console is installed and current." if current else f"Installed the Workspaces Console {rel['tag']} from the public root's release, after checking its fingerprint. Reload VS Code's window to start it."}


def local_source() -> bool:
    """Whether this clone holds the Console's source: a clone does, an installed wheel does not. WS_HOST_CONSOLE=release asks for the published release
    instead, as a ws-host without the source would."""
    if os.environ.get("WS_HOST_CONSOLE") == "release":
        return False
    return (paths.repo_root() / "console" / "package.json").is_file()


def local_step(ctx, have: set) -> dict:
    """Build the Console from this clone's own source with ws-host's own Node, and install it (0004-editor-extension FR-026). Nothing is downloaded from a
    release and nothing needs a network but the npm packages the clone's lock names; a rebuild happens only when the source has changed."""
    from ..lib import provider as prov, release, toolchain as tc
    name = "Workspaces Console extension"
    fingerprint = release.source_hash()
    current = read_stamp().get("source") == fingerprint and CONSOLE_ID in have
    if ctx.dry_run:
        return {"name": name, "status": "already" if current else "would-install",
                "plain": "The Workspaces Console is installed and matches this clone." if current else "I would build the Workspaces Console from this clone and install it."}
    if current:
        return {"name": name, "status": "already", "plain": "The Workspaces Console is installed and matches this clone."}
    p = prov.load(paths.repo_root())
    try:
        if p is None or "node" not in p.entries:
            raise release.ReleaseError("no-provider", "ws-host does not declare node", "ws-host's own toolchain does not name Node.js.")
        tc.ensure(p, ["node"], offline=ctx.offline)
        env = tc.environment(p)
        out = paths.cache_dir() / "workspaces-console"
        for old in out.glob("*.vsix"):
            old.unlink()
        vsix = release.build_console_local(out, env)
    except tc.ToolchainError as e:
        raise WsError(f"toolchain-{e.code}", str(e), e.plain, exit_code=e.exit_code)
    except release.ReleaseError as e:
        raise WsError("console-build", str(e), e.plain, [Action(("vscode", "ensure"), "Try again")])
    r = run_code(["--install-extension", str(vsix), "--force"], "📦 Installing the Workspaces Console")
    if r.returncode != 0:
        raise WsError("code-install", (r.stderr or r.stdout).strip()[-300:], "VS Code's `code` command could not install the Workspaces Console.", [Action(("vscode", "ensure"), "Try again")])
    write_stamp(source=fingerprint, installed=fingerprint)
    return {"name": name, "status": "installed", "plain": "Built the Workspaces Console from this clone and installed it. Reload VS Code's window to start it."}


def console_step(ctx, cfg, code: str | None, have: set) -> tuple[dict, list[Action]]:
    """Put the Workspaces Console in VS Code: built here from this clone's source, so that everyone who installed ws-host has it with no release to wait for;
    only a ws-host without the source (a wheel) takes the published release, after checking its fingerprint (0007-releases FR-010)."""
    name = "Workspaces Console extension"
    if not code:
        return {"name": name, "status": "skipped", "plain": "VS Code's `code` command is not available here yet; open VS Code from this terminal once with `code .`, then run this again."}, []
    if local_source():
        try:
            return local_step(ctx, have), []
        except WsError as e:
            return {"name": name, "status": "failed", "plain": e.plain}, list(e.actions) or [Action(("vscode", "ensure"), "Try again")]
    rel = release_package(ctx.offline)
    if rel is None:
        return {"name": name, "status": "skipped", "plain": "This ws-host has no copy of the Console's source, and I could not find a published release with a checksum I can verify "
                                                           "(there may be none yet, or GitHub could not be reached), so I did not install it."}, [Action(("vscode", "ensure"), "Try again")]
    try:
        return release_step(ctx, rel, have), []
    except fetch.FetchError as e:
        return {"name": name, "status": "failed", "plain": f"The release package did not pass its check ({e.message[:120]}), so I did not install it."}, [Action(("vscode", "ensure"), "Try again")]


def provider_candidates(cfg) -> list[Path]:
    """The clones this person works in that declare themselves providers (and this clone of ws-host itself), in a stable order, each once."""
    from ..lib import provider as prov
    roots, seen = [], set()
    for r in sorted(repos.known(cfg)[0], key=str):
        roots.append(r.path(cfg))
    roots.append(paths.repo_root())
    out = []
    for root in roots:
        real = root.resolve()
        if real in seen or not (real / prov.FOLDER / "provider.toml").is_file():
            continue
        seen.add(real)
        out.append(real)
    return out


def runtime_rows(ctx, p, actions: list) -> list[dict]:
    """Install everything a provider in use pins (so its Home in the Console shows nothing missing), then the shared libraries its programs link."""
    from ..install import apt
    from ..lib import toolchain as tc
    todo = [n for n, v in tc.state(p).items() if v["state"] != "ready"]
    rows = []
    name = f"Install what {p.name} needs"
    if not todo:
        rows.append({"name": name, "status": "already", "plain": f"Every program {p.name} pins is installed."})
    elif ctx.dry_run:
        rows.append({"name": name, "status": "would-install", "plain": f"I would install {len(todo)} program{'s' if len(todo) != 1 else ''} for {p.name}: " + ", ".join(todo) + "."})
    else:
        done, failed = [], None
        for n in todo:                      # one at a time: each shows its own progress, and one that fails does not hide the others
            try:
                tc.ensure(p, [n], offline=ctx.offline)
                done.append(n)
            except tc.ToolchainError as e:
                failed = e
                break
        if failed is None:
            rows.append({"name": name, "status": "installed", "plain": f"Installed {len(done)} program{'s' if len(done) != 1 else ''} for {p.name}: " + ", ".join(done) + "."})
        else:
            rows.append({"name": name, "status": "failed", "plain": f"Installed {len(done)} of {len(todo)}; then: {failed.plain}"})
            actions.append(Action(("toolchain", "ensure"), f"Install what {p.name} pins", {"provider": p.name, "all": True}))
    libs = sorted({x for e in p.entries.values() for x in e.system})
    if libs:
        names, _missing = apt.resolve(libs)
        need = apt.to_install(names)
        label = f"Install shared libraries for {p.name}"
        if not need:
            rows.append({"name": label, "status": "already", "plain": "The shared libraries its programs need are installed."})
        elif ctx.dry_run:
            rows.append({"name": label, "status": "would-install", "plain": "I would install: " + ", ".join(need) + " (it asks for your password)."})
        else:
            try:
                apt.install(need)
                rows.append({"name": label, "status": "installed", "plain": "Installed " + ", ".join(need) + "."})
            except apt.AptError as e:
                rows.append({"name": label, "status": "skipped", "plain": f"I could not install {', '.join(need)} ({e}). It needs your password: run ws-host system ensure yourself."})
                actions.append(Action(("system", "ensure"), "Install shared libraries"))
    return rows


def providers_steps(ctx, cfg) -> tuple[list[dict], list[Action]]:
    """Enable the clones that declare themselves providers, and fetch the runtime their launchers start with, so the Workspaces Console opens with
    its views ready and nothing left for a person to work out (0009-workspaces-console FR-009). Enabling is a decision: it is asked at the terminal
    in plain words, and never answered for the person."""
    from ..lib import provider as prov, toolchain as tc
    from . import provider as prov_cmd
    rows, actions = [], []
    if cfg.get("WS_HOST_PROVIDERS", "yes").strip().lower() in ("no", "false", "0", "off"):
        return rows, actions
    for root in provider_candidates(cfg):
        p = prov.load(root)
        if p is None or p.problems:
            continue
        name = f"Enable {p.name} for ws-host"
        have = prov.get(p.name)
        if have is not None and have.root.resolve() == root:
            row = {"name": name, "status": "already", "plain": f"{p.name} is in use: {prov.how_enabled(p.name)}."}
        elif ctx.dry_run:
            row = {"name": name, "status": "would-install", "plain": f"I would ask you to let ws-host use {p.name} ({root}), so the Workspaces Console can show it."}
        else:
            try:
                prov_cmd.provider_add(ctx, str(root))
                row = {"name": name, "status": "installed", "plain": f"{p.name} is enabled."}
            except WsError as e:
                row = {"name": name, "status": "skipped", "plain": e.plain + f" Until it is enabled the Workspaces Console cannot show {p.name}. To do it yourself: ws-host provider add {root}"}
                actions.append(Action(("provider", "add"), f"Enable {p.name}", {"path": str(root)}))
                rows.append(row)
                continue
            have = prov.get(p.name)
        rows.append(row)
        if have is not None:
            rows.extend(runtime_rows(ctx, have, actions))
    return rows, actions


def workspace_file(cfg) -> Path:
    return cfg.workspaces / "workspaces.code-workspace"


# What every workspace file opens with, added only where the person has not chosen a value (0004-editor-extension FR-028).
WORKSPACE_SETTINGS = {
    "window.title": "Workspaces${separator}${rootName}${separator}${activeEditorShort}",
    "explorer.compactFolders": False,
}


def workspace_step(cfg, dry: bool) -> dict:
    """A multi-root workspace of the repositories you work in, so the Workspaces Console shows each repository's command line (0043 FR-007)."""
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
    return {"name": name, "status": "installed", "plain": f"{f} lists your repositories. Open it in VS Code with `code {f}` (or File, Open Workspace from File) to see every repository in one window. Make other *.code-workspace files in {f.parent} for a Git service or an organization of your own; I only manage this one."}


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


def settings_target(wanted: dict) -> chezmoi.Target:
    return chezmoi.Target("VS Code settings", settings_file(), "vscode-settings", (json.dumps(wanted),))


def merge_settings(f: Path, wanted: dict, dry: bool) -> dict:
    """Add the settings the person has not set; never change one they have; chezmoi writes the file. A file with comments is left alone and said so."""
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
        chezmoi.apply_targets([settings_target(wanted)])
    return {"file": str(f), "status": "would-add" if dry and added else ("added" if added else "unchanged"),
            "added": sorted(added), "kept": sorted(kept), "plain": ""}


@reg.command("vscode", "ensure", category="setup", summary="Put VS Code in its recommended state: the Workspaces Console, helpful extensions and safe settings",
             surfaces=("cli", "editor"))
def vscode_ensure(ctx):
    steps, status, actions = [], OK, []
    code = shutil.which("code")
    cfg = config.load()
    if not ctx.dry_run:
        # Say what is about to happen, that nothing is needed from the person, and how long it can take, before anything slow starts.
        yield Resource("progress", "vscode-start", {"plain": f"Setting up VS Code: the Workspaces Console, {len(RECOMMENDED)} helpful extensions and a few safe settings. "
                                                    "There is nothing for you to do while it works. " +
                                                    ("The first time, VS Code downloads a small helper into Debian and the Workspaces Console is built, which can take a few minutes "
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
        step, more = {"name": "Workspaces Console extension", "status": "failed", "plain": e.plain}, list(e.actions)
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
                q = run_code(["--install-extension", ext_id, "--force"], f"📦 Installing {ext_id} ({n} of {len(RECOMMENDED)})")
            except WsError as e:
                row["status"], row["plain"] = "failed", e.plain
                steps.append(row)
                break
            row["status"] = "installed" if q.returncode == 0 else "failed"
            if q.returncode != 0:
                row["plain"] = (q.stderr or q.stdout).strip()[-200:]
        steps.append(row)
    steps.append(workspace_step(cfg, ctx.dry_run))
    more_steps, more_actions = providers_steps(ctx, cfg)
    steps += more_steps
    actions += more_actions
    s = merge_settings(settings_file(), baseline_settings(), ctx.dry_run)
    left = [r for r in steps if r["status"] in ("skipped", "failed")]
    plain = ("Nothing was changed. This is what I would set up." if ctx.dry_run else
             "VS Code is set up." if not left and s["status"] != "left-alone" else
             "VS Code is partly set up. " + ("The steps below say what is left." if left else s["plain"]))
    done = not ctx.dry_run and not left
    yield Resource("vscode-setup", "vscode", {"plain": plain, "steps": [{**r, "status": "ok" if r["status"] in ("installed", "already", "would-install") else "warn" if r["status"] == "skipped" else "fail"} for r in steps],
                                              "settings": s, "reload": "Reload VS Code's window (Ctrl+Shift+P, then Developer: Reload Window) so everything starts." if not ctx.dry_run and any(r["status"] == "installed" for r in steps) else "",
                                              **({"next": f"Open {workspace_file(cfg)} in VS Code (File, Open Workspace from File), then press Ctrl+Shift+P and run Workspaces Console: Learn a Topic."} if done else {})},
                   actions=(actions or []) + ([] if not left or actions else [Action(("vscode", "ensure"), "Try again")]),
                   status=FAILED if any(r["status"] == "failed" for r in steps) else status)


@command("vscode", "check", category="check", summary="Run a provider's tests of the Workspaces Console in a real VS Code under a display server",
         args=(Arg("suite", "PATH", required=True, help="a folder whose index.js exports run()"),
               Arg("workspace", "STRING", multiple=True, help="a folder of the test workspace, NAME=PATH or PATH"),
               Arg("report", "PATH", help="where to write the report of each test"),
               Arg("first", "PATH", help="the clone whose command line is the workspace's first folder (default: this repository)")), surfaces=("cli",))
def vscode_test(ctx, suite, workspace, report, first):
    """0009-workspaces-console FR-034: another provider's suite runs against the Console with this machine's pinned VS Code."""
    from pathlib import Path
    from .check import run_console_suite
    folders = []
    for w in workspace or []:
        name, _, path = w.partition("=") if "=" in w else (Path(w).name, "", w)
        folders.append({"name": name, "path": str(Path(path).resolve())})
    if not (Path(suite) / "index.js").is_file():
        raise WsError("no-suite", suite, f"{suite} has no index.js, so there is no suite to run.", exit_code=2)
    try:
        rows, p = run_console_suite(Path(suite).resolve(), folders, Path(report) if report else None, Path(first).resolve() if first else None)
    except FileNotFoundError as e:
        raise WsError("missing-program", str(e), f"I could not start VS Code for the tests: {e} is not on this machine.", status="missing", exit_code=3)
    bad = [r for r in rows if r.get("status") != "passed"]
    plain = f"{len(rows) - len(bad)} of {len(rows)} tests passed in a real VS Code." + (" " + "; ".join(r["name"] for r in bad) if bad else "")
    return Resource("vscode-test", "console", {"plain": plain, "tests": rows, "findings": [f"{r['name']}: {str(r.get('reason', ''))[:160]}" for r in bad]},
                    status=OK if p.returncode == 0 and not bad else FAILED)
