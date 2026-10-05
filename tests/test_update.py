"""Keeping ws-host itself current, and telling a new window when an update waits (0006-onboarding FR-025)."""
import os
import subprocess
import time

from ws_host.core import paths
from ws_host.lib import selfupdate, git as wgit
from .helpers import Workspace, git


class Update(Workspace):
    def setUp(self):
        super().setUp()
        self.upstream = self.remote("intellectual-frontiers", "workspaces-host")
        self.copy = self.home.parent / "copy"
        git(self.home.parent, "clone", str(self.remotes / "github.com/intellectual-frontiers/workspaces-host"), str(self.copy))
        real = paths.repo_root
        paths.repo_root = lambda: self.copy
        self.addCleanup(lambda: setattr(paths, "repo_root", real))

    def news(self, n=2):
        for i in range(n):
            self.upstream_commit(self.upstream, f"f{i}.txt", "x\n", msg=f"change {i}")

    def test_nothing_new_says_so_and_leaves_no_note(self):
        code, doc = self.run_json("update", "status")
        self.assertEqual(code, 0)
        self.assertEqual(doc["data"]["plain"], "ws-host is up to date.")
        self.assertFalse(selfupdate.notice_file().exists())
        self.assertTrue(selfupdate.checked_file().exists())

    def test_news_is_counted_listed_and_left_as_a_note(self):
        self.news(2)
        code, doc = self.run_json("update", "status")
        self.assertEqual(doc["data"]["behind"], 2)
        self.assertEqual(doc["data"]["whats_new"], ["change 1", "change 0"])
        self.assertIn("2 changes", doc["data"]["plain"])
        self.assertEqual(doc["actions"][0]["cli"], "ws-host update advance")
        self.assertIn("ws-host update advance", selfupdate.notice_file().read_text())
        self.assertIn("2 changes", selfupdate.notice_file().read_text())

    def test_cached_reads_the_note_and_uses_no_network(self):
        self.news(1)
        self.run_json("update", "status")
        for f in self.remotes.rglob("HEAD"):
            pass
        code, doc = self.run_json("update", "status", "--cached")
        self.assertTrue(doc["data"]["waiting"])
        self.assertIn("1 change", doc["data"]["plain"])

    def test_advance_moves_forward_and_clears_the_note(self):
        self.news(2)
        self.run_json("update", "status")
        code, doc = self.run_json("update", "advance")
        self.assertEqual(code, 0)
        self.assertIn("moved forward by 2 changes", doc["data"]["plain"])
        self.assertTrue((self.copy / "f1.txt").exists())
        self.assertFalse(selfupdate.notice_file().exists())
        code, doc = self.run_json("update", "advance")
        self.assertEqual(doc["data"]["plain"], "ws-host is up to date.")

    def test_changes_of_the_persons_are_never_in_the_way(self):
        self.news(1)
        (self.copy / "README.md").write_text("my edit\n")
        before = wgit.snapshot(self.copy)
        code, doc = self.run_json("update", "advance")
        self.assertEqual(code, 0)
        self.assertIn("changes you have not committed", doc["data"]["plain"])
        self.assertIn("Your work is safe", doc["data"]["plain"])
        self.assertEqual(wgit.snapshot(self.copy), before)
        self.assertTrue(selfupdate.notice_file().exists(), "the note stays until the update is done")

    def test_commits_that_diverged_are_left_alone(self):
        self.news(1)
        (self.copy / "mine.txt").write_text("1\n")
        git(self.copy, "add", "-A")
        git(self.copy, "commit", "-m", "mine")
        before = wgit.snapshot(self.copy)
        code, doc = self.run_json("update", "advance")
        self.assertIn("both moved on", doc["data"]["plain"])
        self.assertEqual(wgit.snapshot(self.copy), before)

    def test_commits_only_ahead_are_safe_and_mentioned(self):
        (self.copy / "mine.txt").write_text("1\n")
        git(self.copy, "add", "-A")
        git(self.copy, "commit", "-m", "mine")
        code, doc = self.run_json("update", "advance")
        self.assertIn("1 commit you have not pushed", doc["data"]["plain"])

    def test_a_dry_run_changes_nothing(self):
        self.news(1)
        before = wgit.snapshot(self.copy)
        code, doc = self.run_json("update", "advance", "--dry-run")
        self.assertIn("I would move ws-host forward by 1 change", doc["data"]["plain"])
        self.assertEqual(wgit.snapshot(self.copy), before)

    def test_an_unreachable_remote_is_a_plain_message_and_a_quiet_background_look_still_stamps_the_time(self):
        git(self.copy, "remote", "set-url", "origin", str(self.home.parent / "nowhere"))
        code, doc = self.run_json("update", "advance")
        self.assertEqual(code, 0)
        self.assertIn("Your copy was not touched", doc["data"]["plain"])
        code, doc = self.run_json("update", "status", "--background")
        self.assertEqual(code, 0)
        self.assertTrue(selfupdate.checked_file().exists())

    def test_the_doctor_says_when_an_update_waits_from_the_last_look(self):
        self.news(1)
        self.run_json("update", "status")
        code, doc = self.run_json("doctor")
        row = [c for c in doc["data"]["checks"] if c["name"] == "ws-host version"][0]
        self.assertEqual(row["status"], "warn")
        self.run_json("update", "advance")
        code, doc = self.run_json("doctor")
        self.assertEqual([c for c in doc["data"]["checks"] if c["name"] == "ws-host version"][0]["status"], "ok")

    def test_due_after_six_hours(self):
        self.assertTrue(selfupdate.due())
        selfupdate.checked_file().parent.mkdir(parents=True, exist_ok=True)
        selfupdate.checked_file().touch()
        self.assertFalse(selfupdate.due())
        old = time.time() - 7 * 3600
        os.utime(selfupdate.checked_file(), (old, old))
        self.assertTrue(selfupdate.due())


class NewWindow(Workspace):
    """The lines in the prompt block that tell a new terminal window about an update."""

    def setUp(self):
        super().setUp()
        self.state = self.home / ".local/state/workspaces-host"
        self.bin = self.home.parent / "shim"
        self.bin.mkdir()
        self.log = self.home.parent / "calls.log"
        (self.bin / "ws-host").write_text(f'#!/bin/sh\necho "$*" >> "{self.log}"\n')
        (self.bin / "ws-host").chmod(0o755)
        from ws_host.commands import shell
        lines = shell.block("bash").splitlines()
        start = next(i for i, l in enumerate(lines) if l.startswith("# ws-host looks for a newer"))
        self.snippet = "\n".join(lines[start:-1])

    def open_window(self, **env):
        p = subprocess.run(["bash", "-c", self.snippet], capture_output=True, text=True, timeout=30,
                           env={**os.environ, "HOME": str(self.home), "PATH": f"{self.bin}:{os.environ['PATH']}", "XDG_STATE_HOME": "", **env})
        time.sleep(0.4)             # the background look is not waited for
        return p.stdout, (self.log.read_text() if self.log.exists() else "")

    def test_a_waiting_update_is_shown_once_per_window(self):
        self.state.mkdir(parents=True)
        (self.state / "update-available").write_text("A newer ws-host is ready (3 changes). Update it with:  ws-host update advance\n")
        (self.state / "update-checked").touch()
        out, calls = self.open_window()
        self.assertIn("🔄 A newer ws-host is ready (3 changes)", out)
        self.assertEqual(calls, "", "a recent look is not repeated")

    def test_no_colour_when_asked(self):
        self.state.mkdir(parents=True)
        (self.state / "update-available").write_text("A newer ws-host is ready.\n")
        (self.state / "update-checked").touch()
        out, _ = self.open_window(NO_COLOR="1")
        self.assertNotIn("\x1b", out)
        self.assertIn("A newer ws-host is ready.", out)

    def test_nothing_is_shown_when_nothing_waits(self):
        self.state.mkdir(parents=True)
        (self.state / "update-checked").touch()
        out, calls = self.open_window()
        self.assertEqual((out, calls), ("", ""))

    def test_an_old_look_is_repeated_in_the_background_and_a_new_window_does_not_wait_for_it(self):
        self.state.mkdir(parents=True)
        (self.state / "update-checked").touch()
        old = time.time() - 7 * 3600
        os.utime(self.state / "update-checked", (old, old))
        (self.bin / "ws-host").write_text(f'#!/bin/sh\nsleep 2\necho "$*" >> "{self.log}"\n')
        start = time.time()
        out, calls = self.open_window()
        self.assertLess(time.time() - start, 1.5)

    def test_the_first_window_ever_looks_too(self):
        out, calls = self.open_window()
        self.assertIn("update status --background", calls)

    def test_the_fish_block_is_valid_fish(self):
        import shutil
        fish = shutil.which("fish")
        if not fish:
            self.skipTest("fish is not installed here")
        from ws_host.commands import shell
        f = self.home.parent / "config.fish"
        f.write_text(shell.block("fish"))
        self.assertEqual(subprocess.run([fish, "-n", str(f)]).returncode, 0)
