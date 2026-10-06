"""Installing, finding and pruning a provider's programs (0008-providers FR-006 to FR-015), through `lib/mise.py`. Standard library only."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import mise, provider as prov


class ToolchainError(Exception):
    def __init__(self, code: str, message: str, plain: str | None = None, exit_code: int = 1):
        super().__init__(message)
        self.code, self.plain, self.exit_code = code, plain or message, exit_code


def _mise(p: prov.Provider, args: list[str], offline: bool = False, timeout: int = 1800, label: str | None = None):
    try:
        done = mise.run(args, p.mise_dir, offline=offline, timeout=timeout, label=label)
    except mise.MiseMissing as e:
        raise ToolchainError("no-mise", str(e), f"I need mise to install what {p.name} pins, and {e}. " + ("Run this again with a network." if e.offline else ""),
                             exit_code=3)
    return done


def lockfile(p: prov.Provider) -> Path:
    return p.mise_dir / ".config" / "mise" / "mise.lock"


def _locks(p: prov.Provider) -> dict[str, bytes]:
    """The lock and the dependency locks beside it, by path under the provider's folder."""
    base = lockfile(p).parent
    files = [lockfile(p), *sorted((base / "locks").rglob("*"))] if base.is_dir() else []
    return {str(f.relative_to(p.root)): f.read_bytes() for f in files if f.is_file()}


def lock(p: prov.Provider, offline: bool = False) -> list[str]:
    """Write the translation, then let mise resolve and lock it for both platforms (0008-providers FR-006). Returns the files changed."""
    if p.problems:
        raise ToolchainError("invalid", "; ".join(map(str, p.problems)), f"{p.name}'s declarations have problems: " + "; ".join(map(str, p.problems)), 1)
    changed = prov.write(p)
    if not p.entries:
        return changed
    before = _locks(p)
    done = _mise(p, ["lock", "--platform", ",".join(prov.PLATFORMS)], offline, label=f"🔐 Locking what {p.name} pins")
    if done.returncode != 0:
        raise ToolchainError("lock", (done.stderr or done.stdout).strip()[-400:], "mise could not lock " + p.name + "'s entries: " + " ".join((done.stderr or done.stdout).strip().splitlines()[-3:]))
    after = _locks(p)
    return changed + [k for k in sorted(after) if before.get(k) != after[k]] + [f"{k} (removed)" for k in sorted(before) if k not in after]


def closure(p: prov.Provider, names: list[str]) -> list[str]:
    """The named entries and every entry they need, each once, in an order that installs a need first."""
    out: list[str] = []

    def add(n: str) -> None:
        if n in out:
            return
        for m in p.entries[n].needs:
            add(m)
        out.append(n)

    for n in names:
        if n not in p.entries:
            raise ToolchainError("unknown-entry", n, f"{p.name} pins no entry called '{n}'. Its entries are: {', '.join(sorted(p.entries)) or 'none'}.")
        add(n)
    return out


def ensure(p: prov.Provider, names: list[str] | None, offline: bool = False) -> list[str]:
    """Install the named entries (default: all) from the lock only. Returns the entries now installed."""
    if p.problems:
        raise ToolchainError("invalid", "; ".join(map(str, p.problems)), f"{p.name}'s declarations have problems: " + "; ".join(map(str, p.problems)), 1)
    stale = prov.stale(p)
    if stale:
        raise ToolchainError("stale", ", ".join(stale), f"{p.name}'s generated mise files are older than its entries ({', '.join(stale[:2])}). "
                             f"Run ws-host toolchain generate {p.name} and commit what it writes.")
    wanted = closure(p, names) if names else sorted(p.entries)
    if not wanted:
        return []
    if not lockfile(p).is_file():
        raise ToolchainError("no-lock", "mise.lock", f"{p.name} has no lock yet. Run ws-host toolchain generate {p.name} and commit what it writes.")
    args = ["install", "--locked"] + ([f"{p.entries[n].tool_id()}@{p.entries[n].version}" for n in wanted] if names else [])
    done = _mise(p, args, offline, label=f"📦 Installing {', '.join(wanted)} for {p.name}")
    if done.returncode != 0:
        raise ToolchainError("install", (done.stderr or done.stdout).strip()[-500:], "mise could not install " + ", ".join(wanted) + ": " +
                             " ".join((done.stderr or done.stdout).strip().splitlines()[-3:]))
    return wanted


def install_path(p: prov.Provider, e: prov.Entry) -> Path | None:
    """Where an entry is installed, or None when it is not."""
    if e.kind == "archive":
        d = mise.data_dir() / "installs" / f"http-{e.name}" / e.version
        return d if d.is_dir() else None
    done = _mise(p, ["where", f"{e.tool_id()}@{e.version}"])
    path = Path(done.stdout.strip()) if done.returncode == 0 and done.stdout.strip() else None
    return path if path and path.is_dir() else None


def state(p: prov.Provider) -> dict[str, dict]:
    """Each entry's version, state and path, in name order."""
    out = {}
    for n in sorted(p.entries):
        e = p.entries[n]
        path = install_path(p, e)
        out[n] = {"name": n, "version": e.version, "kind": e.kind, "summary": e.summary, "state": "ready" if path else "missing", "path": str(path) if path else None,
                  "provides": {k: str(path / v) if path else v for k, v in e.provides.items()}, "needs": list(e.needs)}
    return out


def environment(p: prov.Provider, base: dict[str, str] | None = None) -> dict[str, str]:
    """A provider's environment (0008-providers FR-013): its entries' programs first on PATH and their `env` set, over `base` (default: this process's).
    A variable several entries set holds each value, in entry-name order, joined by a colon."""
    env = dict(os.environ if base is None else base)
    delta = delta_of(p)
    for k, v in delta.items():
        if k == "PATH":
            continue
        env[k] = v
    env["PATH"] = os.pathsep.join(filter(None, [delta.get("PATH", ""), env.get("PATH", "")]))
    return env


def delta_of(p: prov.Provider) -> dict[str, str]:
    """What a provider's installed entries add to an environment: PATH pieces and variables, nothing else."""
    plat = prov.platform()
    pieces: list[str] = []
    values: dict[str, list[str]] = {}
    for n in sorted(p.entries):
        e = p.entries[n]
        path = install_path(p, e)
        if path is None:
            continue
        b = e.bin_dir(plat)
        if b is not None:
            d = str(path / b) if b not in ("", ".") else str(path)
            if d not in pieces:
                pieces.append(d)
        for k, v in e.env.items():
            values.setdefault(k, []).append(v.replace("{dir}", str(path)))
    out = {k: ":".join(v) for k, v in values.items()}
    if pieces:
        out["PATH"] = os.pathsep.join(pieces)
    return out


def prune(providers: list[prov.Provider], dry_run: bool, offline: bool = False) -> list[dict]:
    """Remove stored programs no enabled provider's lock names (0008-providers FR-015). Returns what was (or would be) removed."""
    keep: set[Path] = set()
    for p in providers:
        for e in p.entries.values():
            path = install_path(p, e)
            if path is not None:
                keep.add(path.resolve())
    root = mise.data_dir() / "installs"
    removed = []
    for tool in sorted(root.iterdir()) if root.is_dir() else []:
        if not tool.is_dir() or tool.is_symlink():
            continue
        for ver in sorted(tool.iterdir()):
            if ver.is_symlink() or not ver.is_dir():
                continue
            if ver.resolve() not in keep:
                size = sum(f.stat().st_size for f in ver.rglob("*") if f.is_file())
                removed.append({"name": tool.name, "version": ver.name, "bytes": size, "status": "would remove" if dry_run else "removed"})
                if not dry_run:
                    shutil.rmtree(ver)
        if not dry_run:
            left = [c for c in tool.iterdir() if not c.is_symlink()]
            if not left:
                shutil.rmtree(tool, ignore_errors=True)
            else:
                for c in tool.iterdir():
                    if c.is_symlink() and not c.exists():
                        c.unlink()
    return removed
