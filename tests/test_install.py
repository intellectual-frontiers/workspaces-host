import os
import shutil
import subprocess
import unittest

from .helpers import REPO, Home, git, make_remote


@unittest.skipUnless(shutil.which("uv") and shutil.which("git"), "uv and git are needed")
class Install(Home):
    def setUp(self):
        super().setUp()
        self.bare = self.home.parent / "wsh.git"
        subprocess.run(["git", "clone", "--bare", "-q", str(REPO), str(self.bare)], check=True,
                       capture_output=True)  # a local "remote": the repository's committed state
        self.env = {**os.environ, "WS_HOST_URL": str(self.bare), "WS_HOST_HOME": str(self.home / "workspaces"),
                    "PATH": f"{os.path.dirname(shutil.which('uv'))}:{os.environ['PATH']}"}

    def install(self):
        return subprocess.run(["sh", str(REPO / "install.sh")], capture_output=True, text=True, env=self.env)

    def test_install_clones_links_and_runs_doctor_and_is_repeatable(self):
        if not git(REPO, "rev-parse", "HEAD", check=False):
            self.skipTest("the repository has no commit yet")
        p = self.install()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        target = self.home / "workspaces/github.com/intellectual-frontiers/workspaces-host"
        self.assertTrue((target / ".git").is_dir())
        link = self.home / ".local/bin/ws-host"
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.path.realpath(link), str(target / "ws-host"))
        self.assertIn("Your machine is ready", p.stdout)
        again = self.install()
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)

    def test_a_second_run_leaves_a_clone_with_edits_alone(self):
        if not git(REPO, "rev-parse", "HEAD", check=False):
            self.skipTest("the repository has no commit yet")
        self.install()
        target = self.home / "workspaces/github.com/intellectual-frontiers/workspaces-host"
        (target / "pyproject.toml").write_text("# my edit\n")
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual((target / "pyproject.toml").read_text(), "# my edit\n")

    def test_it_says_in_plain_words_what_is_missing(self):
        sh = shutil.which("sh")
        env = {**self.env, "PATH": str(self.home)}
        p = subprocess.run([sh, str(REPO / "install.sh")], capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 3)
        self.assertIn("python3", p.stderr)
        self.assertIn("Fix:", p.stderr)

    def test_install_sh_is_posix_sh_and_executable(self):
        self.assertEqual(subprocess.run(["sh", "-n", str(REPO / "install.sh")]).returncode, 0)
        self.assertTrue(os.access(REPO / "install.sh", os.X_OK))
