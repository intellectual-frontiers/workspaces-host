"""0002-repositories-and-trust: the rules that came from real defects, as tests with real git repositories."""
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

from ws_host.lib import git as wgit
from .helpers import Workspace, git


class Listing(Workspace):
    def test_known_repositories_come_from_the_person_and_from_listed_clones(self):
        a = self.remote("acme", "site", {"README.md": "x", ".workspaces-host/ws-host.env": 'WS_HOST_KIT=press\nWS_HOST_REPOS="github.com/acme/lib github.com/acme/docs"\n'})
        self.remote("acme", "lib")
        self.remote("acme", "docs")
        self.config(WS_HOST_REPOS=self.rid("acme", "site"))
        _, doc = self.run_json("repo", "list")
        self.assertEqual([r["id"] for r in doc["data"]["repositories"]], [self.rid("acme", "site")])  # nothing cloned yet: nothing to read
        code, _ = self.run_json("repo", "add", "--all")
        self.assertEqual(code, 0)
        _, doc = self.run_json("repo", "list")
        ids = {r["id"]: r for r in doc["data"]["repositories"]}
        self.assertEqual(set(ids), {self.rid("acme", x) for x in ("site", "lib", "docs")})
        self.assertEqual(ids[self.rid("acme", "lib")]["listed_by"], [self.rid("acme", "site")])
        self.assertTrue(all(r["cloned"] for r in ids.values()))

    def test_a_short_name_resolves_when_unique_and_is_refused_when_ambiguous(self):
        self.config(WS_HOST_REPOS="github.com/a/site github.com/b/site github.com/a/lib")
        code, doc = self.run_json("repo", "status", "lib")
        self.assertEqual(code, 0)
        code, doc = self.run_json("repo", "status", "site")
        self.assertEqual((code, doc["data"]["code"]), (2, "ambiguous-repository"))
        code, doc = self.run_json("repo", "status", "nothing")
        self.assertEqual((code, doc["data"]["code"]), (2, "unknown-repository"))

    def test_entries_that_are_not_identifiers_are_reported_and_ignored(self):
        self.config(WS_HOST_REPOS="github.com/a/b notarepo")
        _, doc = self.run_json("repo", "list")
        self.assertEqual(len(doc["data"]["repositories"]), 1)
        self.assertIn("notarepo", doc["data"]["ignored"][0])

    def test_a_repository_file_is_read_without_trust(self):
        self.remote("acme", "site", {"x": "1", ".workspaces-host/ws-host.env": 'WS_HOST_REPOS="github.com/acme/lib"\n'})
        self.config(WS_HOST_REPOS=self.rid("acme", "site"))
        self.run_cmd("repo", "add", "site")
        _, doc = self.run_json("repo", "list")
        self.assertIn(self.rid("acme", "lib"), [r["id"] for r in doc["data"]["repositories"]])
        self.assertFalse(self.paths.enabled_dir().exists())


class Cloning(Workspace):
    def test_add_clones_into_the_layout_and_trusts_nothing(self):
        self.remote("acme", "site")
        self.config(WS_HOST_REPOS=self.rid("acme", "site"))
        code, doc = self.run_json("repo", "add", "--all")
        self.assertEqual(code, 0)
        self.assertTrue((self.clone_path("acme", "site") / ".git").is_dir())
        self.assertFalse(self.paths.enabled_dir().exists())
        self.assertEqual(doc["data"]["repositories"][0]["outcome"], "cloned")

    def test_a_failed_clone_is_failed_not_done_and_the_others_still_clone(self):
        self.remote("acme", "good")
        self.config(WS_HOST_REPOS=f"{self.rid('acme', 'missing')} {self.rid('acme', 'good')}")
        code, doc = self.run_json("repo", "add", "--all")
        self.assertEqual(code, 1)
        outcomes = {r["id"]: r["outcome"] for r in doc["data"]["repositories"]}
        self.assertEqual(outcomes, {self.rid("acme", "missing"): "failed", self.rid("acme", "good"): "cloned"})
        failed = [r for r in doc["data"]["repositories"] if r["outcome"] == "failed"][0]
        self.assertIn("git", failed)
        self.assertNotIn("done", doc["data"]["plain"].lower().replace("done:", "").replace("copied 1", ""))
        self.assertFalse((self.clone_path("acme", "missing")).exists())

    def test_dry_run_clones_nothing(self):
        self.remote("acme", "site")
        self.config(WS_HOST_REPOS=self.rid("acme", "site"))
        code, doc = self.run_json("repo", "add", "--all", "--dry-run")
        self.assertEqual(code, 0)
        self.assertFalse(self.clone_path("acme", "site").exists())
        self.assertEqual(doc["data"]["repositories"][0]["outcome"], "would-copy")


class _Deny(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="private"')
        self.end_headers()

    def log_message(self, *a):
        pass


class Private(Workspace):
    def setUp(self):
        super().setUp()
        self.srv = HTTPServer(("127.0.0.1", 0), _Deny)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        os.environ["GIT_CONFIG_VALUE_0"] = "https://github.com/"
        os.environ["GIT_CONFIG_KEY_0"] = f"url.http://127.0.0.1:{self.srv.server_port}/.insteadOf"

    def test_a_private_repository_without_sign_in_fails_fast_with_gits_reason_and_the_sign_in_action(self):
        self.config(WS_HOST_REPOS=self.rid("acme", "secret"))
        code, doc = self.run_json("repo", "add", "--all")
        self.assertEqual(code, 1)
        r = doc["data"]["repositories"][0]
        self.assertEqual(r["outcome"], "failed")
        self.assertIn("could not read Username", r["git"])
        self.assertTrue(r["auth"])
        self.assertIn("not signed in", r["plain"])
        self.assertEqual([a["command"] for a in doc["actions"]], ["ws-host auth new github"])
        self.assertFalse(self.clone_path("acme", "secret").exists())

    def test_a_fetch_that_needs_sign_in_fails_without_touching_the_clone(self):
        os.environ["GIT_CONFIG_KEY_0"] = f"url.{self.remotes}/github.com/.insteadOf"
        self.remote("acme", "site")
        self.config(WS_HOST_REPOS=self.rid("acme", "site"))
        self.run_cmd("repo", "add", "--all")
        path = self.clone_path("acme", "site")
        git(path, "remote", "set-url", "origin", f"http://127.0.0.1:{self.srv.server_port}/acme/site")
        before = wgit.snapshot(path)
        code, doc = self.run_json("repo", "advance", "--all")
        self.assertEqual(code, 1)
        self.assertEqual(doc["data"]["repositories"][0]["outcome"], "failed")
        self.assertIn("could not read Username", doc["data"]["repositories"][0]["git"])
        self.assertEqual(doc["actions"][0]["command"], "ws-host auth new github")
        self.assertEqual(wgit.snapshot(path), before)


class Advancing(Workspace):
    def setUp(self):
        super().setUp()
        self.up = self.remote("acme", "site", {"README.md": "one\ntwo\nthree\n", "other.txt": "o\n"})
        self.config(WS_HOST_REPOS=self.rid("acme", "site"))
        self.run_cmd("repo", "add", "--all")
        self.path = self.clone_path("acme", "site")

    def advance(self):
        code, doc = self.run_json("repo", "advance", "--all")
        return code, doc["data"]["repositories"][0], doc

    def assert_untouched(self, before):
        after = wgit.snapshot(self.path)
        self.assertEqual(after["head"], before["head"])
        self.assertEqual(after["branch"], before["branch"])
        self.assertEqual(after["status"], before["status"])
        self.assertEqual(after["index"], before["index"])
        self.assertEqual(after["stash"], "")
        self.assertIsNone(after["operation"])
        self.assertFalse((self.path / ".git" / "rebase-merge").exists())
        self.assertFalse((self.path / ".git" / "MERGE_HEAD").exists())

    def test_it_fast_forwards(self):
        self.upstream_commit(self.up, "new.txt", "n\n")
        self.upstream_commit(self.up, "new2.txt", "n\n")
        code, r, _ = self.advance()
        self.assertEqual((code, r["outcome"], r["commits"]), (0, "updated", 2))
        self.assertTrue((self.path / "new2.txt").exists())

    def test_unpushed_conflicting_work_survives(self):
        (self.path / "README.md").write_text("one\nMINE\nthree\n")
        git(self.path, "commit", "-am", "my unpushed work")
        self.upstream_commit(self.up, "README.md", "one\nTHEIRS\nthree\n")
        before = wgit.snapshot(self.path)
        code, r, doc = self.advance()
        self.assertEqual((code, r["outcome"]), (0, "skipped"))
        self.assertIn("safe", r["plain"])
        self.assertIn("both moved on", r["plain"])
        self.assert_untouched(before)
        self.assertEqual((self.path / "README.md").read_text(), "one\nMINE\nthree\n")
        self.assertIn("my unpushed work", git(self.path, "log", "--format=%s", "-1"))

    def test_unpushed_work_with_nothing_new_upstream_is_up_to_date_and_noted(self):
        (self.path / "mine.txt").write_text("m\n")
        git(self.path, "add", "-A")
        git(self.path, "commit", "-m", "mine")
        before = wgit.snapshot(self.path)
        code, r, _ = self.advance()
        self.assertEqual((code, r["outcome"], r["ahead"]), (0, "current", 1))
        self.assertIn("not pushed", r["plain"])
        self.assert_untouched(before)

    def test_uncommitted_changes_are_skipped_even_when_a_fast_forward_would_work(self):
        (self.path / "other.txt").write_text("edited\n")
        self.upstream_commit(self.up, "new.txt", "n\n")
        before = wgit.snapshot(self.path)
        code, r, _ = self.advance()
        self.assertEqual((code, r["outcome"]), (0, "skipped"))
        self.assertIn("have not committed", r["plain"])
        self.assert_untouched(before)
        self.assertFalse((self.path / "new.txt").exists())

    def test_no_upstream_is_skipped(self):
        git(self.path, "checkout", "-q", "-b", "local-only")
        before = wgit.snapshot(self.path)
        code, r, _ = self.advance()
        self.assertEqual((code, r["outcome"]), (0, "skipped"))
        self.assertIn("not connected", r["plain"])
        self.assert_untouched(before)

    def test_a_detached_head_is_skipped(self):
        git(self.path, "checkout", "-q", "--detach")
        before = wgit.snapshot(self.path)
        code, r, _ = self.advance()
        self.assertEqual((code, r["outcome"]), (0, "skipped"))
        after = wgit.snapshot(self.path)
        self.assertEqual((after["head"], after["status"], after["stash"]), (before["head"], before["status"], ""))

    def test_a_rebase_in_progress_is_left_alone(self):
        (self.path / "README.md").write_text("one\nMINE\nthree\n")
        git(self.path, "commit", "-am", "mine")
        self.upstream_commit(self.up, "README.md", "one\nTHEIRS\nthree\n")
        git(self.path, "fetch", "-q")
        git(self.path, "rebase", "@{u}", check=False)   # conflicts: a rebase is now in progress
        self.assertIsNotNone(wgit.operation_in_progress(self.path))
        before = wgit.snapshot(self.path)
        code, r, _ = self.advance()
        self.assertEqual((code, r["outcome"]), (0, "skipped"))
        self.assertIn("rebase", r["plain"])
        self.assertEqual(wgit.snapshot(self.path), before)

    def test_untracked_files_do_not_block_an_update(self):
        (self.path / "scratch.txt").write_text("s\n")
        self.upstream_commit(self.up, "new.txt", "n\n")
        code, r, _ = self.advance()
        self.assertEqual((code, r["outcome"]), (0, "updated"))
        self.assertEqual((self.path / "scratch.txt").read_text(), "s\n")

    def test_an_untracked_file_in_the_way_is_a_skip_with_gits_reason(self):
        (self.path / "new.txt").write_text("mine, untracked\n")
        self.upstream_commit(self.up, "new.txt", "theirs\n")
        before = wgit.snapshot(self.path)
        code, r, _ = self.advance()
        self.assertEqual((code, r["outcome"]), (0, "skipped"))
        self.assertIn("overwrite", r["plain"])
        self.assertIn("git", r)
        self.assertEqual((self.path / "new.txt").read_text(), "mine, untracked\n")
        self.assertEqual(wgit.snapshot(self.path), before)

    def test_it_never_runs_pull_rebase_or_stash(self):
        calls = []
        real = wgit.run

        def spy(cwd, *args, **kw):
            calls.append(args[0])
            return real(cwd, *args, **kw)
        self.upstream_commit(self.up, "new.txt", "n\n")
        with mock.patch.object(wgit, "run", spy):
            self.advance()
        self.assertFalse({"pull", "rebase", "stash", "reset", "checkout", "merge"} & (set(calls) - {"merge"}))
        self.assertLessEqual({c for c in calls if c == "merge"}, {"merge"})

    def test_a_merge_is_only_ever_ff_only(self):
        seen = []
        real = wgit.run

        def spy(cwd, *args, **kw):
            if args and args[0] == "merge":
                seen.append(args)
            return real(cwd, *args, **kw)
        self.upstream_commit(self.up, "new.txt", "n\n")
        with mock.patch.object(wgit, "run", spy):
            self.advance()
        self.assertTrue(seen and all("--ff-only" in a for a in seen))

    def test_a_skip_is_exit_0_and_listed_in_the_resource(self):
        (self.path / "other.txt").write_text("edited\n")
        code, doc = self.run_json("repo", "advance", "--all")
        self.assertEqual(code, 0)
        self.assertEqual(doc["data"]["repositories"][0]["status"], "skip")
        self.assertIn("left alone", doc["data"]["plain"])

    def test_dry_run_changes_nothing(self):
        self.upstream_commit(self.up, "new.txt", "n\n")
        before = wgit.snapshot(self.path)
        code, doc = self.run_json("repo", "advance", "--all", "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(wgit.snapshot(self.path), before)
        self.assertFalse((self.path / "new.txt").exists())

    def test_status_reports_ahead_behind_and_dirty(self):
        (self.path / "other.txt").write_text("edited\n")
        (self.path / "mine.txt").write_text("m\n")
        git(self.path, "add", "mine.txt")
        git(self.path, "commit", "-m", "mine")
        self.upstream_commit(self.up, "new.txt", "n\n")
        git(self.path, "fetch", "-q")
        _, doc = self.run_json("repo", "status", "site")
        r = doc["data"]["repositories"][0]
        self.assertEqual((r["ahead"], r["behind"], r["dirty"], r["branch"]), (1, 1, True, "main"))


if __name__ == "__main__":
    unittest.main()
