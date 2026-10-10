import json
import os
import shutil
import hashlib
import stat
import subprocess
import sys
import tarfile
import unittest

from .helpers import REPO, Home


class Launcher(Home):
    def sh(self, *argv, env=None):
        return subprocess.run(argv, capture_output=True, text=True, env={**os.environ, "WS_HOST_PYTHON": sys.executable, **(env or {})}, cwd=str(self.home))

    def test_it_runs_from_any_directory(self):
        p = self.sh(str(REPO / "ws-host"), "command", "list", "--json")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["kind"], "command-list")

    def test_it_finds_the_clone_through_a_symbolic_link(self):
        bin_ = self.home / ".local" / "bin"
        bin_.mkdir(parents=True)
        (bin_ / "ws-host").symlink_to(REPO / "ws-host")
        p = self.sh(str(bin_ / "ws-host"), "doctor", "--json")
        self.assertEqual(p.returncode, 0, p.stderr)
        launcher = [c for c in json.loads(p.stdout)["data"]["checks"] if c["name"] == "launcher"][0]
        self.assertEqual(launcher["status"], "ok")

    def test_a_relative_symbolic_link_works_too(self):
        (self.home / "x").mkdir()
        rel = os.path.relpath(REPO / "ws-host", self.home / "x")
        (self.home / "x" / "w").symlink_to(rel)
        p = self.sh(str(self.home / "x" / "w"), "--version")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("ws-host", p.stdout)

    def runtime_env(self, **extra):
        """No WS_HOST_PYTHON: the launcher must find or make its own runtime, in a home that has none."""
        env = {k: v for k, v in os.environ.items() if k not in ("WS_HOST_PYTHON", "WS_HOST_MISE", "WS_HOST_OFFLINE")}
        return {**env, "HOME": str(self.home), "XDG_DATA_HOME": str(self.home / "data"), "XDG_CACHE_HOME": str(self.home / "cache"),
                "XDG_STATE_HOME": str(self.home / "state"), **extra}

    def pins(self):
        return dict(l.split("=", 1) for l in (REPO / "ws_host" / "bootstrap.env").read_text().splitlines() if "=" in l and not l.startswith("#"))

    def test_offline_with_no_runtime_it_exits_3_in_plain_words(self):
        p = subprocess.run(["sh", str(REPO / "ws-host"), "doctor"], capture_output=True, text=True, env=self.runtime_env(WS_HOST_OFFLINE="1"))
        self.assertEqual(p.returncode, 3)
        self.assertIn("not allowed to download", p.stderr)
        self.assertNotIn("Traceback", p.stderr)

    def test_a_fetched_mise_that_is_not_the_pinned_one_is_refused_before_it_is_unpacked(self):
        bad = self.home / "mise.tar.xz"
        bad.write_bytes(b"not the pinned archive")
        p = subprocess.run(["sh", str(REPO / "ws-host"), "doctor"], capture_output=True, text=True,
                           env=self.runtime_env(WS_HOST_MISE_URL=f"file://{bad}"))
        self.assertEqual(p.returncode, 3)
        self.assertIn("not the one ws-host expects", p.stderr)
        self.assertFalse(list((self.home / "data").glob("workspaces-host/tools/mise/*/bin/mise")))

    def test_the_first_run_installs_the_pinned_python_and_uv_with_mise_and_then_runs_on_them(self):
        """A stand-in mise (named in WS_HOST_MISE) records what it was asked and lays out the store the way mise does."""
        pins = self.pins()
        store = self.home / "data" / "workspaces-host" / "mise" / "data" / "installs"
        mise = self.home / "mise"
        mise.write_text(f"""#!/bin/sh
echo "$MISE_SAFE $MISE_DATA_DIR $*" > "{self.home}/mise.args"
mkdir -p "{store}/python/{pins['PYTHON_VERSION']}/bin" "{store}/uv/{pins['UV_VERSION']}/.mise-bins"
ln -sf "{sys.executable}" "{store}/python/{pins['PYTHON_VERSION']}/bin/python3"
printf '#!/bin/sh\nexit 0\n' > "{store}/uv/{pins['UV_VERSION']}/.mise-bins/uv"; chmod +x "{store}/uv/{pins['UV_VERSION']}/.mise-bins/uv"
""")
        mise.chmod(0o755)
        p = subprocess.run(["sh", str(REPO / "ws-host"), "command", "list", "--json"], capture_output=True, text=True,
                           env=self.runtime_env(WS_HOST_MISE=str(mise)), cwd=str(self.home))
        self.assertEqual(p.returncode, 0, p.stderr)
        args = (self.home / "mise.args").read_text().split()
        self.assertEqual(args[0], "1")                                                  # safe mode
        self.assertEqual(args[1], str(self.home / "data" / "workspaces-host" / "mise" / "data"))
        self.assertEqual(args[2:], ["install", f"python@{pins['PYTHON_VERSION']}", f"uv@{pins['UV_VERSION']}"])
        (self.home / "mise.args").unlink()
        again = subprocess.run(["sh", str(REPO / "ws-host"), "command", "list", "--json"], capture_output=True, text=True,
                               env=self.runtime_env(WS_HOST_MISE=str(mise)), cwd=str(self.home))
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertFalse((self.home / "mise.args").exists(), "a runtime that is already there is not installed again")

    def test_the_pins_agree_with_the_providers_entries_and_the_mise_in_the_code(self):
        import tomllib
        from ws_host.lib import mise
        pins = self.pins()
        self.assertEqual(mise.VERSION, pins["MISE_VERSION"])
        for tool in ("python", "uv"):
            entry = tomllib.loads((REPO / ".workspaces-host" / "toolchain.d" / f"{tool}.toml").read_text())
            self.assertEqual(entry["version"], pins[f"{tool.upper()}_VERSION"], tool)
        for tool in ("python", "uv"):          # the repository's own development toolchain agrees too
            self.assertIn(f'{tool} = "{pins[tool.upper() + "_VERSION"]}"', (REPO / ".config" / "mise" / "conf.d" / "python.toml").read_text())

    def test_the_launcher_is_posix_sh(self):
        self.assertEqual(subprocess.run(["sh", "-n", str(REPO / "ws-host")]).returncode, 0)
        self.assertTrue((REPO / "ws-host").read_text().startswith("#!/bin/sh"))
        self.assertTrue(os.access(REPO / "ws-host", os.X_OK))

    def test_the_project_files_name_no_dependency(self):
        import tomllib
        d = tomllib.loads((REPO / "pyproject.toml").read_text())
        self.assertEqual(d["project"]["dependencies"], [])
        self.assertTrue((REPO / "uv.lock").is_file())


class PythonPin(unittest.TestCase):
    """The newest Python is the one everything runs on: ws-host's own pin, its package floor, and the pin in every sibling repository that is here (0001-ws-host FR-003)."""

    def pin(self, root, rel=".workspaces-host/toolchain.d/python.toml"):
        import re
        m = re.search(r'^version = "([^"]+)"', (root / rel).read_text(), re.M)
        return m.group(1)

    def test_the_floor_in_pyproject_is_the_pinned_minor_version(self):
        import re
        pinned = self.pin(REPO)
        floor = re.search(r'requires-python = ">=([0-9.]+)"', (REPO / "pyproject.toml").read_text()).group(1)
        self.assertEqual(floor, ".".join(pinned.split(".")[:2]))
        self.assertIn(f"PYTHON_VERSION={pinned}", (REPO / "ws_host" / "bootstrap.env").read_text())

    def test_every_sibling_repository_that_is_here_pins_the_same_python(self):
        pinned = self.pin(REPO)
        for root in sorted(REPO.parent.iterdir()):
            if root != REPO and (root / ".workspaces-host" / "toolchain.d" / "python.toml").is_file():
                self.assertEqual(self.pin(root), pinned, f"{root.name} pins another Python than ws-host does")
