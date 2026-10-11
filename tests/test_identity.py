"""0002-repositories-and-trust FR-027: commits go in as the person who signed in to GitHub, and as their work address in their trusted organizations' folders."""
import json
import os
import stat
import subprocess
from pathlib import Path

from ws_host.lib import identity
from .helpers import Home


class Identity(Home):
    PROFILE = {"login": "ada", "id": 4242, "name": "Ada Lovelace", "email": "ada@public.example"}

    def setUp(self):
        super().setUp()
        self.gitconfig = Path(self._tmp.name) / "gitconfig"
        self.gitconfig.write_text("")
        os.environ["GIT_CONFIG_GLOBAL"] = str(self.gitconfig)
        os.environ.pop("GIT_CONFIG_SYSTEM", None)
        os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
        for k in ("WS_HOST_GIT_NAME", "WS_HOST_GIT_EMAIL"):
            os.environ.pop(k, None)
        self.fake_gh(self.PROFILE)

    def fake_gh(self, profile):
        bin_ = Path(self._tmp.name) / "ghbin"
        bin_.mkdir(exist_ok=True)
        f = bin_ / "gh"
        f.write_text("#!/bin/sh\n" + ('if [ "$1" = api ]; then cat <<\'EOF\'\n' + json.dumps(profile) + "\nEOF\nexit 0\nfi\nexit 1\n" if profile else "exit 1\n"))
        f.chmod(f.stat().st_mode | stat.S_IXUSR)
        os.environ["PATH"] = f"{bin_}{os.pathsep}" + os.environ["PATH"].replace(f"{bin_}{os.pathsep}", "")

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd, env={**os.environ}).stdout.strip()

    def cfg(self):
        from ws_host.core import config
        return config.load()

    def test_a_person_with_no_git_identity_gets_their_github_name_and_the_noreply_address_not_the_public_one(self):
        r = identity.ensure(self.cfg())
        self.assertEqual(r["changed"], ["name", "email"])
        self.assertEqual(self.git("config", "--global", "user.name"), "Ada Lovelace")
        self.assertEqual(self.git("config", "--global", "user.email"), "4242+ada@users.noreply.github.com")
        self.assertIn("Commits will be made as Ada Lovelace <4242+ada@users.noreply.github.com>", identity.sentence(r))

    def test_what_a_person_set_themselves_is_never_changed_and_a_second_run_changes_nothing(self):
        self.git("config", "--global", "user.name", "A. Lovelace")
        self.git("config", "--global", "user.email", "ada@mine.example")
        r = identity.ensure(self.cfg())
        self.assertEqual(r["changed"], [])
        self.assertEqual(self.git("config", "--global", "user.name"), "A. Lovelace")
        self.assertEqual(self.git("config", "--global", "user.email"), "ada@mine.example")
        identity.ensure(self.cfg())
        self.assertEqual(self.git("config", "--global", "--get-all", "user.email"), "ada@mine.example")

    def test_only_what_is_missing_is_filled(self):
        self.git("config", "--global", "user.name", "A. Lovelace")
        r = identity.ensure(self.cfg())
        self.assertEqual(r["changed"], ["email"])
        self.assertEqual(self.git("config", "--global", "user.name"), "A. Lovelace")

    def test_a_name_or_email_in_the_persons_own_configuration_is_set_over_what_git_has(self):
        self.git("config", "--global", "user.name", "Old Name")
        self.paths.config_file().parent.mkdir(parents=True, exist_ok=True)
        self.paths.config_file().write_text('WS_HOST_GIT_NAME="New Name"\nWS_HOST_GIT_EMAIL=new@mine.example\n')
        r = identity.ensure(self.cfg())
        self.assertEqual(r["changed"], ["name", "email"])
        self.assertEqual(self.git("config", "--global", "user.name"), "New Name")
        self.assertEqual(self.git("config", "--global", "user.email"), "new@mine.example")

    def test_a_github_account_with_no_name_says_how_to_give_one_and_still_sets_the_address(self):
        self.fake_gh({"login": "ada", "id": 4242, "name": None})
        r = identity.ensure(self.cfg())
        self.assertTrue(r["needs_name"])
        self.assertIn("--git-name", identity.sentence(r))
        self.assertEqual(self.git("config", "--global", "user.email"), "4242+ada@users.noreply.github.com")

    def test_without_gh_nothing_is_guessed(self):
        self.fake_gh(None)
        r = identity.ensure(self.cfg())
        self.assertEqual(r["changed"], [])
        self.assertTrue(r["needs_name"])

    def test_a_work_address_is_used_in_the_trusted_organizations_folder_and_nowhere_else(self):
        identity.ensure(self.cfg(), work="ada@work.example")
        mine = self.home / "workspaces" / "github.com" / "intellectual-frontiers" / "demo"
        other = self.home / "workspaces" / "github.com" / "someone-else" / "demo"
        for d in (mine, other):
            d.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(d)], check=True, env={**os.environ})
        self.assertEqual(self.git("config", "user.email", cwd=mine), "ada@work.example")
        self.assertEqual(self.git("config", "user.email", cwd=other), "4242+ada@users.noreply.github.com")
        self.assertEqual(self.git("config", "--global", "--get-all", "user.email"), "4242+ada@users.noreply.github.com", "the global address is the noreply one")
        self.assertEqual(identity.work_email(self.cfg()), {"intellectual-frontiers": "ada@work.example"})
        identity.ensure(self.cfg(), work="ada@work.example")
        self.assertEqual(len(self.git("config", "--global", "--get-all", "includeif.gitdir:~/workspaces/github.com/intellectual-frontiers/.path").splitlines()), 1, "once")
        identity.ensure(self.cfg(), work="none")
        self.assertEqual(self.git("config", "user.email", cwd=mine), "4242+ada@users.noreply.github.com")
        self.assertEqual(identity.work_email(self.cfg()), {})

    def test_a_work_address_set_before_the_global_address_still_wins_in_its_folder(self):
        self.fake_gh(None)
        identity.ensure(self.cfg(), work="ada@work.example")
        identity.ensure(self.cfg(), name="Ada", email="ada@mine.example")
        mine = self.home / "workspaces" / "github.com" / "intellectual-frontiers" / "demo"
        mine.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(mine)], check=True, env={**os.environ})
        self.assertEqual(self.git("config", "user.email", cwd=mine), "ada@work.example")

    def test_the_command_checks_what_it_is_given_and_a_dry_run_changes_nothing(self):
        for args in (("--git-email", "not-an-email"), ("--work-email", "x@"), ("--git-name", "A <b>")):
            code, doc = self.run_json("workspace", "set", *args)
            self.assertEqual(code, 2, args)
        code, doc = self.run_json("workspace", "set")
        self.assertEqual(code, 2)
        code, doc = self.run_json("workspace", "set", "--git-identity", "--dry-run")
        self.assertEqual(code, 0, doc)
        self.assertEqual(self.git("config", "--global", "user.name"), "")
        self.assertIn("name", doc["data"]["plain"])

    def test_the_command_sets_it_and_says_so(self):
        code, doc = self.run_json("workspace", "set", "--git-identity")
        self.assertEqual(code, 0, doc)
        self.assertIn("Commits will be made as Ada Lovelace", doc["data"]["plain"])
        code, doc = self.run_json("workspace", "set", "--git-name", "Ada L", "--git-email", "ada@mine.example")
        self.assertEqual((self.git("config", "--global", "user.name"), self.git("config", "--global", "user.email")), ("Ada L", "ada@mine.example"))

    def test_doctor_says_when_commits_have_no_identity_and_offers_the_fix(self):
        code, doc = self.run_json("doctor")
        rows = [c for c in doc["data"].get("checks", []) if c.get("name") == "git identity"]
        self.assertTrue(rows and rows[0]["status"] == "warn", rows)
        identity.ensure(self.cfg())
        code, doc = self.run_json("doctor")
        rows = [c for c in doc["data"].get("checks", []) if c.get("name") == "git identity"]
        self.assertEqual(rows[0]["status"], "ok")
