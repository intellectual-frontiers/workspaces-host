"""auth (with a fake gh on PATH) and the one command, workspace advance (0002 FR-011, FR-016, FR-017)."""
import json
import os
import stat
import subprocess
from pathlib import Path

from ws_host.lib import git as wgit
from .helpers import Workspace, git


def fake(bin_dir: Path, name: str, script: str):
    bin_dir.mkdir(parents=True, exist_ok=True)
    f = bin_dir / name
    f.write_text("#!/bin/sh\n" + script)
    f.chmod(f.stat().st_mode | stat.S_IXUSR)


class Auth(Workspace):
    def setUp(self):
        super().setUp()
        self.bin = self.home.parent / "fakebin"
        # keep real git and python3 reachable, but no real gh or glab
        keep = self.home.parent / "tools"
        keep.mkdir()
        for t in ("git", "sh", "env", "dirname", "cat", "uv", "touch"):
            import shutil
            p = shutil.which(t)
            if p:
                (keep / t).symlink_to(p)
        os.environ["PATH"] = f"{self.bin}:{keep}"

    def test_status_says_whether_you_are_signed_in(self):
        fake(self.bin, "gh", 'exit 0\n')
        code, doc = self.run_json("auth", "status")
        self.assertEqual(code, 0)
        self.assertTrue(doc["data"]["forges"][0]["signed_in"])
        self.assertIn("signed in", doc["data"]["plain"])
        fake(self.bin, "gh", 'echo "not logged in" >&2; exit 1\n')
        _, doc = self.run_json("auth", "status")
        self.assertFalse(doc["data"]["forges"][0]["signed_in"])
        self.assertEqual(doc["actions"][0]["cli"], "ws-host auth new github")

    def test_status_without_gh_points_at_the_base_kit(self):
        _, doc = self.run_json("auth", "status")
        self.assertIsNone(doc["data"]["forges"][0]["signed_in"])
        self.assertTrue(doc["actions"][0]["cli"].startswith("ws-host kit add"))
        self.assertEqual(doc["actions"][0]["fields"], {"kit": "base"})

    def test_gitlab_hosts_come_from_the_persons_configuration(self):
        self.config(WS_HOST_GITLAB_HOSTS="git.example.org")
        fake(self.bin, "gh", "exit 0\n")
        fake(self.bin, "glab", "exit 1\n")
        _, doc = self.run_json("auth", "status")
        self.assertEqual([f["name"] for f in doc["data"]["forges"]], ["github.com", "git.example.org"])
        self.assertIn("ws-host auth new gitlab --host git.example.org", [a["cli"] for a in doc["actions"]])

    def test_new_streams_the_code_then_the_result(self):
        fake(self.bin, "gh", '''case "$1 $2" in
"auth login")
  echo "! First copy your one-time code: ABCD-1234"
  echo "Open this URL to continue in your web browser: https://github.com/login/device"
  printf "Press Enter to open github.com in your browser... "
  read line
  echo "Logged in"
  exit 0;;
"auth setup-git") touch "$HOME/setup-git-ran"; exit 0;;
esac
exit 0
''')
        code, out = self.run_cmd("auth", "new", "github", "--json")
        self.assertEqual(code, 0, out)
        docs = [json.loads(l) for l in out.strip().splitlines()]
        self.assertEqual([d["kind"] for d in docs], ["auth-code", "auth"])
        self.assertEqual(docs[0]["data"]["code"], "ABCD-1234")
        self.assertEqual(docs[0]["data"]["url"], "https://github.com/login/device")
        self.assertTrue(docs[1]["data"]["signed_in"])
        self.assertTrue((self.home / "setup-git-ran").exists())

    def test_a_login_that_fails_says_so_and_offers_to_try_again(self):
        fake(self.bin, "gh", "echo nope >&2; exit 1\n")
        code, out = self.run_cmd("auth", "new", "github", "--json")
        self.assertEqual(code, 1)
        last = json.loads(out.strip().splitlines()[-1])
        self.assertFalse(last["data"]["signed_in"])
        self.assertEqual(last["actions"][0]["cli"], "ws-host auth new github")

    def test_new_without_gh_is_exit_3_with_the_kit_action(self):
        code, doc = self.run_json("auth", "new", "github")
        self.assertEqual((code, doc["data"]["code"]), (3, "missing-program"))
        self.assertTrue(doc["actions"][0]["cli"].startswith("ws-host kit add"))
        self.assertEqual(doc["actions"][0]["fields"], {"kit": "base"})

    def test_new_is_setup_not_on_mcp_and_dry_run_runs_nothing(self):
        from ws_host.core import registry as reg
        self.assertNotIn("mcp", reg.discover().get(("auth", "new")).surfaces)
        fake(self.bin, "gh", "touch $HOME/ran; exit 0\n")
        code, out = self.run_cmd("auth", "new", "github", "--dry-run", "--json")
        self.assertEqual(code, 0)
        self.assertFalse((self.home / "ran").exists())


class Advance(Workspace):
    def setUp(self):
        super().setUp()
        self.site = self.remote("acme", "site", {"README.md": "x", ".workspaces-host/ws-host.env": 'WS_HOST_REPOS="github.com/acme/lib"\n'})
        self.lib = self.remote("acme", "lib")
        self.config(WS_HOST_REPOS=self.rid("acme", "site"))
        os.environ["PATH"] = os.environ["PATH"]

    def advance(self, *extra):
        code, out = self.run_cmd("workspace", "advance", "--json", *extra)
        return code, [json.loads(l) for l in out.strip().splitlines()]

    def test_the_one_command_copies_updates_and_reports_each_step(self):
        code, docs = self.advance()
        self.assertEqual(code, 0, docs[-1])
        self.assertEqual([d["kind"] for d in docs[:-1]], ["progress"] * 5)  # one streamed line per step
        final = docs[-1]
        self.assertEqual(final["kind"], "workspace-advance")
        self.assertEqual([s["name"] for s in final["data"]["steps"]], ["sign-in", "copy", "update", "kits", "doctor"])
        for n in ("site", "lib"):
            self.assertTrue((self.clone_path("acme", n) / ".git").is_dir())

    def test_a_second_run_changes_nothing(self):
        self.advance()
        before = wgit.snapshot(self.clone_path("acme", "site"))
        code, docs = self.advance()
        self.assertEqual(code, 0)
        self.assertEqual(wgit.snapshot(self.clone_path("acme", "site")), before)
        self.assertEqual({r["outcome"] for r in docs[-1]["data"]["repositories"]}, {"current"})

    def test_it_updates_what_is_behind_and_leaves_unsaved_work_alone(self):
        self.advance()
        site, lib = self.clone_path("acme", "site"), self.clone_path("acme", "lib")
        (lib / "README.md").write_text("my edit\n")
        self.upstream_commit(self.lib, "x.txt", "1\n")
        self.upstream_commit(self.site, "y.txt", "1\n")
        code, docs = self.advance()
        self.assertEqual(code, 0)
        by = {r["id"]: r["outcome"] for r in docs[-1]["data"]["repositories"]}
        self.assertEqual(by[self.rid("acme", "site")], "updated")
        self.assertEqual(by[self.rid("acme", "lib")], "skipped")
        self.assertEqual((lib / "README.md").read_text(), "my edit\n")

    def test_it_continues_past_a_failure_and_reports_it(self):
        self.config(WS_HOST_REPOS=f"{self.rid('acme', 'site')} {self.rid('acme', 'gone')}")
        code, docs = self.advance()
        self.assertEqual(code, 1)
        self.assertTrue((self.clone_path("acme", "lib") / ".git").is_dir())
        self.assertEqual([s["status"] for s in docs[-1]["data"]["steps"] if s["name"] == "copy"], ["fail"])

    def test_dry_run_changes_and_fetches_nothing(self):
        code, docs = self.advance("--dry-run")
        self.assertEqual(code, 0)
        self.assertFalse(self.root.exists())
        self.assertIn("would copy " + self.rid("acme", "site"), docs[-1]["data"]["would"])

    def test_status_changes_nothing_and_says_what_to_do(self):
        code, doc = self.run_json("workspace", "status")
        self.assertEqual(code, 0)
        self.assertEqual(doc["actions"][0]["cli"], "ws-host workspace advance")
        self.assertFalse(self.root.exists())

    def test_pull_ff_is_recommended_and_applied_only_on_request(self):
        gc = self.home / "gitconfig"
        gc.write_text("")
        os.environ["GIT_CONFIG_GLOBAL"] = str(gc)
        _, doc = self.run_json("doctor")
        rec = [c for c in doc["data"]["checks"] if c["name"] == "git pull setting"][0]
        self.assertEqual(rec["status"], "warn")
        self.assertIn("ws-host workspace set --pull-ff-only", [a["cli"] for a in doc["actions"]])
        self.assertEqual(gc.read_text(), "")   # never applied unasked
        code, _ = self.run_cmd("workspace", "set", "--pull-ff-only")
        self.assertEqual(code, 0)
        self.assertIn("ff = only", gc.read_text())
        _, doc = self.run_json("doctor")
        self.assertEqual([c for c in doc["data"]["checks"] if c["name"] == "git pull setting"][0]["status"], "ok")

    def test_workspace_set_dry_run_changes_nothing(self):
        gc = self.home / "gitconfig"
        gc.write_text("")
        os.environ["GIT_CONFIG_GLOBAL"] = str(gc)
        self.run_cmd("workspace", "set", "--pull-ff-only", "--dry-run")
        self.assertEqual(gc.read_text(), "")

    def test_it_writes_nothing_into_a_clone_and_does_not_touch_git_config(self):
        gc = self.home / "gitconfig"
        gc.write_text("")
        os.environ["GIT_CONFIG_GLOBAL"] = str(gc)
        self.advance()
        for n in ("site", "lib"):
            p = self.clone_path("acme", n)
            self.assertEqual(git(p, "status", "--porcelain", "--ignored"), "")
        self.assertEqual(gc.read_text(), "")
