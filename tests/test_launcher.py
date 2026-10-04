import json
import os
import shutil
import subprocess
import unittest

from .helpers import REPO, Home


@unittest.skipUnless(shutil.which("uv"), "uv is needed to run the launcher")
class Launcher(Home):
    def sh(self, *argv, env=None):
        return subprocess.run(argv, capture_output=True, text=True, env={**os.environ, **(env or {})}, cwd=str(self.home))

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

    def test_without_uv_it_exits_3_in_plain_words(self):
        sh = shutil.which("sh")
        safe = self.home / "emptybin"
        safe.mkdir()
        for tool in ("dirname", "readlink"):
            (safe / tool).symlink_to(shutil.which(tool))
        p = self.sh(sh, str(REPO / "ws-host"), "doctor", env={"PATH": str(safe)})
        self.assertEqual(p.returncode, 3)
        self.assertIn("uv", p.stderr)
        self.assertNotIn("Traceback", p.stderr)

    def test_the_launcher_is_posix_sh(self):
        self.assertEqual(subprocess.run(["sh", "-n", str(REPO / "ws-host")]).returncode, 0)
        self.assertTrue((REPO / "ws-host").read_text().startswith("#!/bin/sh"))
        self.assertTrue(os.access(REPO / "ws-host", os.X_OK))

    def test_the_project_files_name_no_dependency(self):
        import tomllib
        d = tomllib.loads((REPO / "pyproject.toml").read_text())
        self.assertEqual(d["project"]["dependencies"], [])
        self.assertTrue((REPO / "uv.lock").is_file())
