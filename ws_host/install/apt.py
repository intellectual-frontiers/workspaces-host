"""The package installer: the distribution's package manager, through sudo (0003-kits FR-005). Standard library only."""
from __future__ import annotations

import os
import shutil
import subprocess


class AptError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def available() -> bool:
    return shutil.which("apt-get") is not None


def is_root() -> bool:
    return os.geteuid() == 0


def interactive() -> bool:
    import sys
    return sys.stdin.isatty() and sys.stdout.isatty()


def sudo_prefix() -> list[str] | None:
    """[] when already administrator, ['sudo'] (or ['sudo', '-n'] with no terminal) when sudo exists, None when neither."""
    if is_root():
        return []
    if shutil.which("sudo") is None:
        return None
    return ["sudo"] if interactive() else ["sudo", "-n"]


def _run(argv, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, **kw)


def installed(package: str) -> bool:
    p = _run(["dpkg-query", "-W", "-f=${Status}", package])
    return p.returncode == 0 and "install ok installed" in p.stdout


def has_candidate(package: str) -> bool:
    p = _run(["apt-cache", "policy", package])
    for line in p.stdout.splitlines():
        if line.strip().startswith("Candidate:"):
            return "(none)" not in line
    return False


def resolve(specs: list[str]) -> tuple[list[str], list[str]]:
    """(the packages to use, the specs this distribution has none of). `a|b` picks the first with a candidate."""
    names, missing = [], []
    for spec in specs:
        for alt in spec.split("|"):
            if installed(alt) or has_candidate(alt):
                names.append(alt)
                break
        else:
            missing.append(spec)
    return names, missing


def to_install(names: list[str]) -> list[str]:
    return [n for n in names if not installed(n)]


HEARTBEAT_SECONDS = 10      # a quiet step says that it is still working, and what it last said, at least this often
LOCK_WAIT_SECONDS = 180     # another package manager holding the lock is waited for, and apt says who holds it, instead of failing at once


def _say(line: str) -> None:
    """The default way lines reach a person: standard error, so that a program reading JSON on standard output is not disturbed."""
    import sys
    try:
        sys.stderr.write(line + "\n")
        sys.stderr.flush()
    except (OSError, ValueError):
        pass


def authenticate(packages: list[str]) -> None:
    """Ask for the administrator's password where the person can see and answer it, before anything else is drawn on the line. Nothing to do when
    already administrator, when the password was given a moment ago, or with no terminal (then the install says it needs one)."""
    if sudo_prefix() != ["sudo"]:
        return
    if subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode == 0:
        return
    from ..core import progress
    with progress.paused():
        _say("\U0001F510 Administrator rights are needed to install: " + ", ".join(packages) + ".")
        _say("   sudo will ask for your password now. Nothing shows as you type; press Enter when done.")
        r = subprocess.run(["sudo", "-v"])
    if r.returncode != 0:
        raise AptError("sudo-denied", "sudo did not accept the password")


def _stream(argv: list[str]):
    """Run a command and give its output line by line as it happens, and, when it says nothing for a while, a sign that it is still working. Returns (status, lines)."""
    import queue
    import threading
    import time
    p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True, bufsize=1, errors="replace")
    q: queue.Queue = queue.Queue()

    def pump():
        for line in p.stdout:
            q.put(line.rstrip("\n"))
        q.put(None)
    threading.Thread(target=pump, daemon=True).start()
    started = last = time.monotonic()
    lines: list[str] = []
    while True:
        try:
            line = q.get(timeout=1)
        except queue.Empty:
            now = time.monotonic()
            if now - last >= HEARTBEAT_SECONDS:
                last = now
                said = next((x for x in reversed(lines) if x.strip()), "")
                yield ("heartbeat", f"\u23f3 Still working, {int(now - started)}s so far" + (f". It last said: {said}" if said else ". It has not said anything yet."))
            continue
        if line is None:
            break
        lines.append(line)
        last = time.monotonic()
        if line.strip():
            yield ("line", "   " + line)
    status = p.wait()
    p.stdout.close()
    return status, lines


def install_events(packages: list[str]):
    """Install the packages non-interactively, as a stream of (kind, text): `step` (what is about to happen), `line` (what apt said, as it said it),
    `heartbeat` (it is still working) and `done`. Raises AptError when it may not run or the package manager fails."""
    import time
    prefix = sudo_prefix()
    if prefix is None:
        raise AptError("no-sudo", "sudo is not available")
    authenticate(packages)
    env = ["env", "DEBIAN_FRONTEND=noninteractive"]
    lock = ["-o", f"DPkg::Lock::Timeout={LOCK_WAIT_SECONDS}"]
    started = time.monotonic()
    yield ("step", "\U0001F4CB Refreshing the package list")
    status, lines = yield from _stream([*prefix, *env, "apt-get", "update", "-q", *lock])
    if status != 0 and prefix == ["sudo", "-n"] and "password" in "\n".join(lines).lower():
        raise AptError("needs-password", "sudo needs a password and there is no terminal to ask it in")
    yield ("step", "\U0001F4E6 Installing " + ", ".join(packages))
    status, lines = yield from _stream([*prefix, *env, "apt-get", "install", "-y", "--no-install-recommends", *lock, *packages])
    if status != 0:
        if "password" in "\n".join(lines).lower() and prefix == ["sudo", "-n"]:
            raise AptError("needs-password", "sudo needs a password and there is no terminal to ask it in")
        tail = [x.strip() for x in lines if x.strip()][-3:]
        raise AptError("apt-failed", " ".join(tail) if tail else "apt-get failed")
    yield ("done", f"Installed {len(packages)} package{'s' if len(packages) != 1 else ''} in {int(time.monotonic() - started)}s.")


def install(packages: list[str], say=None) -> subprocess.CompletedProcess:
    """Install the packages, showing everything apt says as it says it (to `say`, by default standard error): a long install is never silent."""
    say = say or _say
    text: list[str] = []
    from ..core import progress
    with progress.paused():            # a spinner would be drawn over the lines; apt's own words are the progress
        for kind, line in install_events(packages):
            text.append(line)
            say(line if kind != "done" else "\u2705 " + line)
    return subprocess.CompletedProcess(["apt-get", "install", *packages], 0, "\n".join(text), "")
