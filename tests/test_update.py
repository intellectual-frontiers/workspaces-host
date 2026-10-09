"""Keeping ws-host itself current, and telling a new window when an update waits (0006-onboarding FR-025)."""
import os
from .helpers import Home
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
        code, doc = self.run_json("update", "--check")
        self.assertEqual(code, 0)
        self.assertEqual(doc["data"]["plain"], "ws-host is up to date.")
        self.assertFalse(selfupdate.notice_file().exists())
        self.assertTrue(selfupdate.checked_file().exists())

    def test_news_is_counted_listed_and_left_as_a_note(self):
        self.news(2)
        code, doc = self.run_json("update", "--check")
        self.assertEqual(doc["data"]["behind"], 2)
        self.assertEqual(doc["data"]["whats_new"], ["change 1", "change 0"])
        self.assertIn("2 changes", doc["data"]["plain"])
        self.assertEqual(doc["actions"][0]["cli"], "ws-host update")
        self.assertIn("ws-host update", selfupdate.notice_file().read_text())
        self.assertIn("2 changes", selfupdate.notice_file().read_text())

    def test_cached_reads_the_note_and_uses_no_network(self):
        self.news(1)
        self.run_json("update", "--check")
        for f in self.remotes.rglob("HEAD"):
            pass
        code, doc = self.run_json("update", "--check", "--cached")
        self.assertTrue(doc["data"]["waiting"])
        self.assertIn("1 change", doc["data"]["plain"])

    def test_advance_moves_forward_and_clears_the_note(self):
        self.news(2)
        self.run_json("update", "--check")
        code, doc = self.run_json("update")
        self.assertEqual(code, 0)
        self.assertIn("moved forward by 2 changes", doc["data"]["plain"])
        self.assertTrue((self.copy / "f1.txt").exists())
        self.assertFalse(selfupdate.notice_file().exists())
        code, doc = self.run_json("update")
        self.assertEqual(doc["data"]["plain"], "ws-host is up to date.")

    def test_changes_of_the_persons_are_never_in_the_way(self):
        self.news(1)
        (self.copy / "README.md").write_text("my edit\n")
        before = wgit.snapshot(self.copy)
        code, doc = self.run_json("update")
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
        code, doc = self.run_json("update")
        self.assertIn("both moved on", doc["data"]["plain"])
        self.assertEqual(wgit.snapshot(self.copy), before)

    def test_commits_only_ahead_are_safe_and_mentioned(self):
        (self.copy / "mine.txt").write_text("1\n")
        git(self.copy, "add", "-A")
        git(self.copy, "commit", "-m", "mine")
        code, doc = self.run_json("update")
        self.assertIn("1 commit you have not pushed", doc["data"]["plain"])

    def test_a_dry_run_changes_nothing(self):
        self.news(1)
        before = wgit.snapshot(self.copy)
        code, doc = self.run_json("update", "--dry-run")
        self.assertIn("I would move ws-host forward by 1 change", doc["data"]["plain"])
        self.assertEqual(wgit.snapshot(self.copy), before)

    def test_an_unreachable_remote_is_a_plain_message_and_a_quiet_background_look_still_stamps_the_time(self):
        git(self.copy, "remote", "set-url", "origin", str(self.home.parent / "nowhere"))
        code, doc = self.run_json("update")
        self.assertEqual(code, 0)
        self.assertIn("Your copy was not touched", doc["data"]["plain"])
        code, doc = self.run_json("update", "--check", "--background")
        self.assertEqual(code, 0)
        self.assertTrue(selfupdate.checked_file().exists())

    def test_the_doctor_says_when_an_update_waits_from_the_last_look(self):
        self.news(1)
        self.run_json("update", "--check")
        code, doc = self.run_json("doctor")
        row = [c for c in doc["data"]["checks"] if c["name"] == "ws-host version"][0]
        self.assertEqual(row["status"], "warn")
        self.run_json("update")
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

    def test_workspace_updates_looks_at_repositories_too_and_changes_nothing(self):
        other = self.remote("acme", "site")
        self.run_json("repo", "add", self.rid("acme", "site"))
        code, doc = self.run_json("updates", "status", "--fresh")
        self.assertFalse(doc["data"]["waiting"])
        self.assertFalse(selfupdate.notice_file().exists())
        self.upstream_commit(other, "n.txt", "x\n")
        code, doc = self.run_json("updates", "status", "--fresh")
        self.assertTrue(doc["data"]["waiting"])
        self.assertEqual([i["name"] for i in doc["data"]["items"]], ["site"])
        self.assertIn("site", doc["data"]["plain"])
        self.assertEqual(doc["actions"][0]["cli"], "ws-host update")
        self.assertIn("site", selfupdate.notice_file().read_text())
        self.assertFalse((self.clone_path("acme", "site") / "n.txt").exists(), "a look moves nothing")
        self.upstream_commit(other, "m.txt", "x\n")
        code, doc = self.run_json("updates", "status")
        self.assertEqual(doc["data"]["items"][0]["behind"], 1, "a look a few minutes old is given again without asking the network")

    def test_the_background_look_covers_repositories_for_the_note(self):
        other = self.remote("acme", "site")
        self.run_json("repo", "add", self.rid("acme", "site"))
        self.upstream_commit(other, "n.txt", "x\n")
        self.run_json("update", "--check", "--background")
        self.assertIn("site", selfupdate.notice_file().read_text())

    def test_an_unreachable_remote_leaves_the_last_note_alone(self):
        self.news(1)
        self.run_json("updates", "status", "--fresh")
        had = selfupdate.notice_file().read_text()
        git(self.copy, "remote", "set-url", "origin", str(self.home.parent / "nowhere"))
        code, doc = self.run_json("updates", "status", "--fresh")
        self.assertEqual(code, 0)
        self.assertIn("ws-host", doc["data"]["unreachable"])
        self.assertEqual(selfupdate.notice_file().read_text(), had)


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
        (self.state / "update-available").write_text("A newer ws-host is ready (3 changes). Update it with:  ws-host update\n")
        (self.state / "update-checked").touch()
        out, calls = self.open_window()
        self.assertIn("🔄 A newer ws-host is ready (3 changes)", out)
        self.assertEqual(calls, "", "a recent look is not repeated")

    def test_nothing_is_said_in_vs_codes_own_terminal(self):
        self.state.mkdir(parents=True)
        (self.state / "update-available").write_text("A newer ws-host is ready.\n")
        (self.state / "update-checked").touch()
        out, _ = self.open_window(TERM_PROGRAM="vscode")
        self.assertNotIn("newer ws-host", out)

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
        self.assertIn("update --check --background", calls)

    def test_the_fish_block_is_valid_fish(self):
        import shutil
        fish = shutil.which("fish")
        if not fish:
            self.skipTest("fish is not installed here")
        from ws_host.commands import shell
        f = self.home.parent / "config.fish"
        f.write_text(shell.block("fish"))
        self.assertEqual(subprocess.run([fish, "-n", str(f)]).returncode, 0)


class WholeUpgrade(Home):
    """0006-onboarding FR-025: `update` brings everything current with the newest code, in one command."""

    def setUp(self):
        super().setUp()
        os.environ.pop("WS_HOST_UPDATE_SELF_ONLY")
        self.log = self.home / "calls.log"
        stub = self.home / "ws-host-stub"
        stub.write_text(f'#!/bin/sh\necho "$@" >> "{self.log}"\nexit ${{STUB_EXIT:-0}}\n')
        stub.chmod(0o755)
        os.environ["WS_HOST_LAUNCHER"] = str(stub)
        import unittest.mock
        self.patch = unittest.mock.patch("ws_host.lib.selfupdate.update", lambda offline=False: {
            "outcome": "updated", "plain": "ws-host moved forward by 2 changes.", "path": "x", "branch": "main", "behind": 2, "ahead": 0, "news": []})
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_it_updates_ws_host_then_runs_the_rest_with_the_newest_code_and_cleans_up(self):
        code, out = self.run_cmd("update")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.log.read_text().splitlines(), ["workspace ensure", "toolchain remove --unused"])
        self.assertIn("ws-host moved forward by 2 changes", out)

    def test_offline_is_passed_on_and_a_failed_setup_is_the_commands_status(self):
        os.environ["STUB_EXIT"] = "3"
        code, out = self.run_cmd("update", "--offline")
        self.assertEqual(code, 3)
        self.assertEqual(self.log.read_text().splitlines()[0], "workspace ensure --offline")

    def test_a_dry_run_changes_nothing_and_runs_nothing(self):
        code, out = self.run_cmd("update", "--dry-run")
        self.assertFalse(self.log.exists())

    def test_json_answers_with_one_document_naming_each_step(self):
        code, doc = self.run_json("update")
        self.assertEqual([s["command"] for s in doc["data"]["steps"]], ["ws-host workspace ensure", "ws-host toolchain remove --unused"])


class SettledNews(Workspace):
    """The note and the remembered answer follow what a command just did, so nothing goes on saying news waits that has been brought in or put aside."""

    def setUp(self):
        super().setUp()
        self.up = self.remote("acme", "site")
        self.config(WS_HOST_REPOS=self.rid("acme", "site"))
        self.run_json("repo", "add", "--all")
        self.path = self.clone_path("acme", "site")

    def test_a_clean_refresh_clears_the_note_that_news_waits(self):
        import os
        (self.path / "mine.txt").write_text("m\n")
        git(self.path, "add", "-A")
        git(self.path, "commit", "-m", "Mine")
        self.upstream_commit(self.up, "t.txt", "t\n", msg="Theirs")
        code, doc = self.run_json("updates", "status", "--fresh")
        self.assertTrue(doc["data"]["waiting"])
        self.assertTrue(selfupdate.notice_file().exists())
        os.environ["WS_HOST_SURFACE"] = "editor"
        self.addCleanup(lambda: os.environ.pop("WS_HOST_SURFACE", None))
        code, doc = self.run_json("repo", "advance", "site", "--clean", "--confirmed")
        self.assertEqual(code, 0, doc)
        self.assertFalse(selfupdate.notice_file().exists(), "the note was cleared")
        code, doc = self.run_json("updates", "status")           # the remembered answer, a few minutes old, is the new one
        self.assertFalse(doc["data"]["waiting"])

    def test_bringing_news_in_clears_it_too(self):
        self.upstream_commit(self.up, "t.txt", "t\n")
        self.run_json("updates", "status", "--fresh")
        self.assertTrue(selfupdate.notice_file().exists())
        self.run_json("repo", "sync", "--all")
        self.assertFalse(selfupdate.notice_file().exists())
