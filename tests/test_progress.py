"""The spinner for slow steps, and the prompt command (0006-onboarding FR-020, 0003-kits FR-015)."""
import io
import os
import re
import time

from ws_host.core import progress
from .helpers import Home


ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class Tty(io.StringIO):
    def isatty(self):
        return True


class Spinner(Home):
    def setUp(self):
        super().setUp()
        self._saved_progress = (progress.ENABLED, progress.DELAY, progress.LEFT_BEHIND)
        self.addCleanup(lambda: (setattr(progress, "ENABLED", self._saved_progress[0]), setattr(progress, "DELAY", self._saved_progress[1]),
                                 setattr(progress, "LEFT_BEHIND", self._saved_progress[2])))
        progress.ENABLED, progress.DELAY, progress.LEFT_BEHIND = True, 0.15, 0.3
        os.environ.pop("WS_HOST_PROGRESS", None)
        os.environ.pop("NO_COLOR", None)
        os.environ["TERM"] = "xterm"
        os.environ["LANG"] = "C.UTF-8"

    def test_a_step_that_ends_at_once_shows_nothing(self):
        out = Tty()
        with progress.Working("Quick", out):
            pass
        self.assertEqual(out.getvalue(), "")

    def test_a_slow_step_shows_a_spinner_then_leaves_one_line(self):
        out = Tty()
        with progress.Working("Downloading oh-my-posh", out) as w:
            w.detail("1.5 of 3.0 MB")
            time.sleep(0.6)
        text = out.getvalue()
        self.assertIn("Downloading oh-my-posh", text)
        self.assertIn("1.5 of 3.0 MB", text)
        self.assertIn("\r\033[K", text)
        self.assertEqual(ANSI.sub("", text).rstrip("\n").splitlines()[-1].split("\r")[-1].replace("\x1b[K", ""), "✔ Downloading oh-my-posh")

    def test_a_step_that_fails_leaves_a_cross(self):
        out = Tty()
        with self.assertRaises(ValueError):
            with progress.Working("Installing git", out):
                time.sleep(0.4)
                raise ValueError("no")
        self.assertIn("✖ Installing git", ANSI.sub("", out.getvalue()))

    def test_nothing_is_drawn_in_json_a_dumb_terminal_or_when_switched_off(self):
        for how in ("json", "dumb", "never"):
            progress.ENABLED = how != "json"
            os.environ["TERM"] = "dumb" if how == "dumb" else "xterm"
            if how == "never":
                os.environ["WS_HOST_PROGRESS"] = "never"
            out = Tty()
            with progress.Working("Slow", out):
                time.sleep(0.4)
            self.assertEqual(out.getvalue(), "", how)

    def test_a_pipe_gets_nothing_even_when_enabled(self):
        out = io.StringIO()
        with progress.Working("Slow", out):
            time.sleep(0.4)
        self.assertEqual(out.getvalue(), "")

    def test_ascii_frames_without_utf8(self):
        os.environ["LANG"] = "C"
        os.environ.pop("LC_ALL", None)
        os.environ.pop("LC_CTYPE", None)
        out = Tty()
        with progress.Working("Slow", out):
            time.sleep(0.6)
        plain = ANSI.sub("", out.getvalue())
        self.assertNotIn("✔", plain)
        self.assertIn("ok Slow", plain)

    def test_the_command_line_turns_it_off_for_json(self):
        self.run_cmd("command", "list", "--json")
        self.assertFalse(progress.ENABLED)
        self.run_cmd("command", "list")
        self.assertTrue(progress.ENABLED)

    def test_download_progress_reaches_the_spinner(self):
        import hashlib
        from ws_host.install import fetch
        src = self.home.parent / "blob"
        src.write_bytes(b"x" * 300_000)
        seen = []
        orig = progress.detail
        progress.detail = lambda t: seen.append(t)
        self.addCleanup(lambda: setattr(progress, "detail", orig))
        fetch.download(src.as_uri(), hashlib.sha256(src.read_bytes()).hexdigest())
        self.assertTrue(seen and seen[-1] == "0.3 of 0.3 MB", seen)

    def test_megabytes(self):
        self.assertEqual(progress.megabytes(1_500_000, 3_000_000), "1.5 of 3.0 MB")
        self.assertEqual(progress.megabytes(1_500_000, None), "1.5 MB")


class ShellAdd(Home):
    def setUp(self):
        super().setUp()
        self.bin = self.home / ".local" / "bin"
        self.bin.mkdir(parents=True)
        (self.bin / "oh-my-posh").write_text("#!/bin/sh\n")      # present, so nothing is downloaded
        (self.bin / "oh-my-posh").chmod(0o755)
        self.bashrc = self.home / ".bashrc"
        self.bashrc.write_text("alias a=b\nexport X=1")

    def test_it_adds_one_marked_block_and_keeps_a_copy(self):
        code, out = self.run_cmd("shell", "add", "bash")
        self.assertEqual(code, 0, out)
        text = self.bashrc.read_text()
        self.assertTrue(text.startswith("alias a=b\nexport X=1\n"))
        self.assertEqual(text.count("# >>> workspaces-host: prompt (ws-host shell add bash) >>>"), 1)
        self.assertIn("oh-my-posh init bash --config", text)
        self.assertIn("coach.omp.json", text)
        self.assertTrue(text.rstrip().endswith("# <<< workspaces-host <<<"))
        backups = list((self.paths.state_dir() / "backups").iterdir())
        self.assertEqual([b.read_text() for b in backups], ["alias a=b\nexport X=1"])

    def test_a_second_run_changes_nothing(self):
        self.run_cmd("shell", "add", "bash")
        first = self.bashrc.read_text()
        code, doc = self.run_json("shell", "add", "bash")
        self.assertEqual(code, 0)
        self.assertFalse(doc["data"]["changed"])
        self.assertEqual(self.bashrc.read_text(), first)
        self.assertEqual(len(list((self.paths.state_dir() / "backups").iterdir())), 1)

    def test_a_dry_run_changes_nothing(self):
        code, doc = self.run_json("shell", "add", "bash", "--dry-run")
        self.assertEqual(code, 0)
        self.assertTrue(doc["data"]["changed"])
        self.assertEqual(self.bashrc.read_text(), "alias a=b\nexport X=1")
        self.assertFalse((self.paths.state_dir() / "backups").exists())

    def test_the_text_outside_the_markers_is_never_touched(self):
        self.run_cmd("shell", "add", "bash")
        text = self.bashrc.read_text()
        self.bashrc.write_text("# mine\n" + text + "alias after=1\n")
        self.run_cmd("shell", "add", "bash")
        got = self.bashrc.read_text()
        self.assertTrue(got.startswith("# mine\n") and got.endswith("alias after=1\n"))
        self.assertEqual(got.count("workspaces-host: prompt"), 1)

    def test_a_block_that_lost_its_end_is_refused(self):
        self.bashrc.write_text("alias a=b\n# >>> workspaces-host: prompt (ws-host shell add bash) >>>\nrm -rf x\n")
        before = self.bashrc.read_text()
        code, out = self.run_cmd("shell", "add", "bash")
        self.assertNotEqual(code, 0)
        self.assertIn("left the file alone", out)
        self.assertEqual(self.bashrc.read_text(), before)

    def test_a_symbolic_link_is_written_through(self):
        real = self.home / "dotfiles" / "bashrc"
        real.parent.mkdir()
        real.write_text("alias a=b\n")
        self.bashrc.unlink()
        self.bashrc.symlink_to(real)
        self.run_cmd("shell", "add", "bash")
        self.assertTrue(self.bashrc.is_symlink())
        self.assertIn("oh-my-posh init bash", real.read_text())

    def test_fish_needs_fish_first_and_then_gets_its_own_config(self):
        os.environ["PATH"] = "/nonexistent"
        code, doc = self.run_json("shell", "add", "fish")
        self.assertEqual(doc["error"]["code"] if "error" in doc else doc["data"].get("code"), "no-fish")
        self.assertFalse((self.home / ".config" / "fish").exists())
        (self.bin / "fish").write_text("#!/bin/sh\n")
        code, out = self.run_cmd("shell", "add", "fish")
        self.assertEqual(code, 0, out)
        text = (self.home / ".config" / "fish" / "config.fish").read_text()
        self.assertIn("oh-my-posh init fish --config", text)
        self.assertIn("status is-interactive", text)

    def test_it_never_changes_the_login_shell_or_etc_shells(self):
        before = os.environ.get("SHELL")
        self.run_cmd("shell", "add", "bash")
        self.assertEqual(os.environ.get("SHELL"), before)

    def test_an_unknown_shell_is_a_usage_error(self):
        code, _ = self.run_cmd("shell", "add", "zsh")
        self.assertEqual(code, 2)

    def test_the_start_page_offers_it(self):
        code, doc = self.run_json("help", "start")
        self.assertIn("shell add bash", str(doc))
