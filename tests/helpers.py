"""Shared fixtures: real temporary git repositories and a local bare "remote"; nothing mocked."""
from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GIT_ENV = {"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "T",
           "GIT_COMMITTER_EMAIL": "t@example.com", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
           "GIT_TERMINAL_PROMPT": "0"}


def git(cwd, *args, check=True):
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env={**os.environ, **GIT_ENV})
    if check and p.returncode:
        raise AssertionError(f"git {' '.join(args)} failed: {p.stderr}")
    return p.stdout.strip()


class Home(unittest.TestCase):
    """A throwaway HOME with XDG directories inside it, so no test touches the person's real files."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name).resolve() / "home"
        self.home.mkdir()
        self._saved = dict(os.environ)
        real_home = Path(os.environ.get("HOME", "~")).expanduser()
        for var, sub in (("RUSTUP_HOME", ".rustup"), ("CARGO_HOME", ".cargo")):   # a throwaway HOME must not hide the machine's own toolchains
            if var not in os.environ and (real_home / sub).exists():
                os.environ[var] = str(real_home / sub)
        os.environ.update({"HOME": str(self.home), **GIT_ENV})
        for k in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "WS_HOST_SURFACE", "WS_HOST_OFFLINE",
                  "WS_HOST_PUBLIC_ROOT", "WS_HOST_IN_GROUP"):
            os.environ.pop(k, None)
        self.addCleanup(self._restore)
        from ws_host.core import paths
        self.paths = paths

    def _restore(self):
        os.environ.clear()
        os.environ.update(self._saved)

    def run_cmd(self, *argv):
        """(exit code, stdout) of an in-process run."""
        from ws_host.core import cli, registry
        out, err = io.StringIO(), io.StringIO()
        code = cli.run(list(argv), out=out, err=err)
        return code, out.getvalue()

    def run_json(self, *argv):
        code, out = self.run_cmd(*argv, "--json")
        return code, json.loads(out.strip().splitlines()[-1])


def make_remote(base: Path, name="remote", files=None) -> tuple[Path, Path]:
    """A local bare repository with one commit on main, and a working copy that pushes to it."""
    bare, work = base / f"{name}.git", base / f"{name}-work"
    bare.mkdir(parents=True)
    git(bare, "init", "--bare", "-b", "main")
    work.mkdir(parents=True)
    git(work, "init", "-b", "main")
    for fn, content in (files or {"README.md": "hello\n"}).items():
        p = work / fn
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    git(work, "add", "-A")
    git(work, "commit", "-m", "first")
    git(work, "remote", "add", "origin", str(bare))
    git(work, "push", "-u", "origin", "main")
    return bare, work


class Workspace(Home):
    """A person's machine: HOME, a configuration file, and local bare 'remotes' that stand in for GitHub.

    git's own `url.<base>.insteadOf` maps https://github.com/ to a local directory, so the code under test runs its real
    `git clone` and `git fetch` with no hook of its own.
    """

    def setUp(self):
        super().setUp()
        self.remotes = self.home.parent / "remotes"
        self.work = self.home.parent / "work"
        os.environ.update({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": f"url.{self.remotes}/github.com/.insteadOf",
                           "GIT_CONFIG_VALUE_0": "https://github.com/"})
        self.root = self.home / "workspaces"

    def config(self, **kw):
        self.paths.config_dir().mkdir(parents=True, exist_ok=True)
        kw.setdefault("WS_HOST_KIT", "")      # a test never installs kits unless it says so
        kw.setdefault("WS_HOST_REPOS", "")    # nor copies the starter repositories
        kw.setdefault("WS_HOST_PROMPT", "no")  # nor edits a shell file
        self.paths.config_file().write_text("".join(f'{k}="{v}"\n' for k, v in kw.items()))

    def remote(self, org, name, files=None):
        bare = self.remotes / "github.com" / org / name
        bare.mkdir(parents=True)
        git(bare, "init", "--bare", "-b", "main")
        w = self.work / org / name
        w.mkdir(parents=True)
        git(w, "init", "-b", "main")
        for fn, content in (files or {"README.md": "hello\n"}).items():
            f = w / fn
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(content)
        git(w, "add", "-A")
        git(w, "commit", "-m", "first")
        git(w, "remote", "add", "origin", str(bare))
        git(w, "push", "-u", "origin", "main")
        return w

    def upstream_commit(self, work, fn, content, msg="upstream"):
        (work / fn).parent.mkdir(parents=True, exist_ok=True)
        (work / fn).write_text(content)
        git(work, "add", "-A")
        git(work, "commit", "-m", msg)
        git(work, "push", "origin", "main")

    def clone_path(self, org, name):
        return self.root / "github.com" / org / name

    def rid(self, org, name):
        return f"github.com/{org}/{name}"
