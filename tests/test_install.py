import os
import shutil
import subprocess
import sys
import unittest

from .helpers import REPO, Home, git, make_remote


@unittest.skipUnless(shutil.which("git"), "git is needed")
class Install(Home):
    def setUp(self):
        super().setUp()
        self.bare = self.home.parent / "wsh.git"
        subprocess.run(["git", "clone", "--bare", "-q", str(REPO), str(self.bare)], check=True,
                       capture_output=True)  # a local "remote": the repository's committed state
        self.env = {**os.environ, "WS_HOST_URL": str(self.bare), "WS_HOST_HOME": str(self.home / "workspaces"), "WS_HOST_NO_ADVANCE": "1",
                    "WS_HOST_PYTHON": sys.executable}

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
        self.assertIn("git", p.stderr)
        self.assertIn("Fix:", p.stderr)

    def test_install_sh_is_posix_sh_and_executable(self):
        self.assertEqual(subprocess.run(["sh", "-n", str(REPO / "install.sh")]).returncode, 0)
        self.assertTrue(os.access(REPO / "install.sh", os.X_OK))


@unittest.skipUnless(shutil.which("git"), "git is needed")
class Bootstrap(Home):
    """0006-onboarding FR-001: the installer installs what is missing, after saying so, and then sets the workspace up."""

    def setUp(self):
        super().setUp()
        self.bare = self.home.parent / "wsh.git"
        subprocess.run(["git", "clone", "--bare", "-q", str(REPO), str(self.bare)], check=True, capture_output=True)
        self.tools = self.home.parent / "tools"
        self.tools.mkdir()
        for t in ("sh", "env", "dirname", "mkdir", "ln", "cat", "printf", "tr", "sleep", "uname", "chmod", "rm", "grep", "sed", "mktemp", "readlink", "date", "ls", "cp", "mv", "tar", "xz", "tail", "head", "cut", "sha256sum"):
            if shutil.which(t):
                (self.tools / t).symlink_to(shutil.which(t))
        (self.tools / "id").write_text("#!/bin/sh\necho 1000\n")      # an ordinary user, whoever runs the tests
        (self.tools / "id").chmod(0o755)
        self.log = self.home.parent / "apt.log"
        self.real = {"git": shutil.which("git"), "python3": shutil.which("python3")}
        # a stand-in apt-get that "installs" by linking the real program into the tools directory
        (self.tools / "apt-get").write_text(f'#!/bin/sh\necho "apt-get $*" >> "{self.log}"\nfor a in "$@"; do case $a in git) ln -sf {self.real["git"]} "{self.tools}/git";; python3) ln -sf {self.real["python3"]} "{self.tools}/python3";; esac; done\nexit 0\n')
        (self.tools / "apt-get").chmod(0o755)
        (self.tools / "sudo").write_text(f'#!/bin/sh\necho "sudo $*" >> "{self.log}"\n[ "$1" = -v ] && exit 0\nexec "$@"\n')
        (self.tools / "sudo").chmod(0o755)
        self.env = {**os.environ, "PATH": str(self.tools), "WS_HOST_URL": str(self.bare), "WS_HOST_HOME": str(self.home / "workspaces"), "WS_HOST_NO_ADVANCE": "1",
                    "WS_HOST_PYTHON": sys.executable}

    def run_install(self, **extra):
        return subprocess.run(["sh", str(REPO / "install.sh")], capture_output=True, text=True, env={**self.env, **extra})

    def test_it_says_it_will_install_what_is_missing_and_installs_it_through_sudo(self):
        if not git(REPO, "rev-parse", "HEAD", check=False):
            self.skipTest("the repository has no commit yet")
        p = self.run_install()
        self.assertIn("I need to install: git curl wget.", p.stdout)
        self.assertIn("administrator rights", p.stdout)
        log = self.log.read_text()
        self.assertIn("sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq", log)
        self.assertIn("git", log)
        self.assertEqual(log.splitlines()[0], "sudo -v", "the password is asked first, in plain view, before any spinner")
        self.assertTrue((self.home / ".local/bin/ws-host").is_symlink(), p.stdout + p.stderr)

    def test_it_ends_with_the_one_line_that_makes_this_window_find_ws_host(self):
        p = self.run_install(SHELL="/bin/bash")
        self.assertIn("exec bash -l", p.stdout)
        self.assertIn("this window does not know the ws-host command, or your new prompt, yet", p.stdout)

    def test_it_says_nothing_about_the_window_when_ws_host_is_already_on_the_path(self):
        p = self.run_install(PATH=f"{self.tools}:{self.home}/.local/bin")
        self.assertNotIn("One last thing", p.stdout)
        self.assertNotIn("this window does not know", p.stdout)

    def test_the_installer_fetches_no_uv_of_its_own(self):
        text = (REPO / "install.sh").read_text()
        self.assertNotIn("astral.sh", text)
        self.assertIn("WS_HOST_BOOTSTRAP_ONLY=1", text)      # the launcher prepares the runtime, through the pinned mise

    def test_on_a_terminal_a_slow_step_shows_a_spinner_and_a_quick_one_nothing(self):
        import pty
        (self.tools / "apt-get").write_text((self.tools / "apt-get").read_text().replace("exit 0", "case \"$*\" in *install*) sleep 2.3;; esac\nexit 0"))
        chunks = []
        env = {**self.env, "TERM": "xterm", "LANG": "C.UTF-8"}
        saved = os.environ.copy()
        try:
            os.environ.clear()
            os.environ.update(env)
            pty.spawn(["sh", str(REPO / "install.sh")], lambda fd: chunks.append(os.read(fd, 4096)) or chunks[-1])
        finally:
            os.environ.clear()
            os.environ.update(saved)
        text = b"".join(chunks).decode(errors="replace")
        self.assertIn("Installing git", text)
        self.assertIn("\r\x1b[K", text)
        self.assertIn("✅", text)
        self.assertNotIn("Refreshing the package list", text, "the quick step before it shows nothing at all")
        self.assertNotIn("Copying workspaces-host", text, "a quick step shows nothing at all")

    def test_with_no_apt_allowed_it_names_the_command_to_run(self):
        p = self.run_install(WS_HOST_NO_APT="1")
        self.assertEqual(p.returncode, 3)
        self.assertIn("sudo apt install", p.stderr)
        self.assertFalse(self.log.exists())

    def test_without_sudo_it_asks_for_an_administrator(self):
        (self.tools / "sudo").unlink()
        p = self.run_install(WS_HOST_NO_APT="")
        self.assertEqual(p.returncode, 3)
        self.assertIn("ask an administrator", p.stderr)

    def test_a_failing_package_install_is_said_in_plain_words(self):
        (self.tools / "apt-get").write_text("#!/bin/sh\nexit 100\n")
        p = self.run_install()
        self.assertEqual(p.returncode, 3)
        self.assertIn("Fix:", p.stderr)

    def test_unless_told_not_to_it_runs_the_workspace_setup_and_says_what_to_do_about_sign_in(self):
        if not git(REPO, "rev-parse", "HEAD", check=False):
            self.skipTest("the repository has no commit yet")
        (self.tools / "gh").write_text("#!/bin/sh\nexit 1\n")      # not signed in
        (self.tools / "gh").chmod(0o755)
        (self.home / ".config" / "workspaces-host").mkdir(parents=True)
        (self.home / ".config" / "workspaces-host" / "ws-host.env").write_text('WS_HOST_KIT=""\n')
        env = {k: v for k, v in self.env.items() if k != "WS_HOST_NO_ADVANCE"}
        p = subprocess.run(["sh", str(REPO / "install.sh")], capture_output=True, text=True, env=env)
        self.assertIn("Setting up your workspace", p.stdout)
        self.assertIn("Sign in to GitHub first", p.stdout)
        self.assertIn("ws-host auth new github", p.stdout)
