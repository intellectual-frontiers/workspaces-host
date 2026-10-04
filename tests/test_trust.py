"""0002-repositories-and-trust FR-012 to FR-015: trust is a link, never transitive, never from a repository's own file."""
import os
from unittest import mock

from ws_host.core import cli, registry as reg
from .helpers import Workspace, git


class Trust(Workspace):
    def setUp(self):
        super().setUp()
        self.site = self.remote("acme", "site", {"README.md": "x", ".workspaces-host/ws-host.env": 'WS_HOST_REPOS="github.com/acme/lib"\nWS_HOST_TRUSTED=acme\n',
                                                 ".workspaces-host/kits/k.py": "# a kit\n"})
        self.remote("acme", "lib", {"README.md": "l", ".workspaces-host/kits/l.py": "# a kit\n"})
        self.config(WS_HOST_REPOS=self.rid("acme", "site"))
        self.run_cmd("repo", "add", "--all")
        self.link = self.paths.enabled_dir() / "site"

    def decide(self, *argv):
        os.environ["WS_HOST_SURFACE"] = "editor"
        return self.run_json("repo", "set", *argv, "--confirmed")

    def test_cloning_and_listing_trust_nothing(self):
        _, doc = self.run_json("repo", "list")
        self.assertEqual({r["id"]: r["trusted"] for r in doc["data"]["repositories"]},
                         {self.rid("acme", "site"): False, self.rid("acme", "lib"): False})
        self.assertFalse(os.path.lexists(self.link))

    def test_a_repositorys_own_file_cannot_grant_trust_and_doctor_says_so(self):
        # site's file says WS_HOST_TRUSTED=acme: ignored
        _, doc = self.run_json("repo", "list")
        self.assertFalse(any(r["trusted"] for r in doc["data"]["repositories"]))
        _, d = self.run_json("doctor")
        self.assertTrue(any(c["name"] == "trust" and "ignored" in c["detail"] for c in d["data"]["checks"]))

    def test_trusting_makes_a_relative_link_and_records_the_commit(self):
        code, doc = self.decide("site", "--trusted")
        self.assertEqual(code, 0, doc)
        self.assertTrue(self.link.is_symlink())
        target = os.readlink(self.link)
        self.assertFalse(os.path.isabs(target), target)
        self.assertEqual(self.link.resolve(), (self.clone_path("acme", "site") / ".workspaces-host").resolve())
        rec = (self.paths.trust_dir() / "github.com__acme__site.env").read_text()
        self.assertIn(git(self.clone_path("acme", "site"), "rev-parse", "HEAD"), rec)
        _, doc = self.run_json("repo", "list")
        by = {r["id"]: r for r in doc["data"]["repositories"]}
        self.assertTrue(by[self.rid("acme", "site")]["trusted"])
        self.assertFalse(by[self.rid("acme", "lib")]["trusted"])   # not transitive: site lists lib, lib is still untrusted

    def test_untrusting_removes_the_link(self):
        self.decide("site", "--trusted")
        code, doc = self.decide("site", "--untrusted")
        self.assertEqual(code, 0)
        self.assertFalse(os.path.lexists(self.link))
        self.assertFalse(doc["data"]["trusted"])

    def test_a_decision_needs_a_person_so_without_a_terminal_it_is_refused(self):
        code, doc = self.run_json("repo", "set", "site", "--trusted")
        self.assertEqual((code, doc["data"]["code"]), (1, "needs-person"))
        self.assertFalse(os.path.lexists(self.link))

    def test_confirmed_alone_is_not_enough_outside_the_editor(self):
        code, doc = self.run_json("repo", "set", "site", "--trusted", "--confirmed")
        self.assertEqual((code, doc["data"]["code"]), (1, "needs-person"))

    def test_a_person_at_a_terminal_can_confirm(self):
        with mock.patch("sys.stdin") as i, mock.patch("sys.stdout") as o:
            i.isatty.return_value = o.isatty.return_value = True
            i.readline.return_value = "yes\n"
            code, out = self.run_cmd("repo", "set", "site", "--trusted")
        self.assertEqual(code, 0)
        self.assertTrue(self.link.is_symlink())

    def test_a_person_who_does_not_say_yes_changes_nothing(self):
        with mock.patch("sys.stdin") as i, mock.patch("sys.stdout") as o:
            i.isatty.return_value = o.isatty.return_value = True
            i.readline.return_value = "no\n"
            code, _ = self.run_cmd("repo", "set", "site", "--trusted")
        self.assertEqual(code, 1)
        self.assertFalse(os.path.lexists(self.link))

    def test_dry_run_needs_no_confirmation_and_changes_nothing(self):
        code, doc = self.run_json("repo", "set", "site", "--trusted", "--dry-run")
        self.assertEqual(code, 0)
        self.assertFalse(os.path.lexists(self.link))

    def test_repo_set_is_a_decision_and_never_on_mcp(self):
        c = reg.discover().get(("repo", "set"))
        self.assertEqual(c.category, "decision")
        self.assertNotIn("mcp", c.surfaces)
        self.assertEqual(c.surfaces, ("cli", "editor"))

    def test_add_trust_trusts_what_the_person_lists_and_not_what_a_listed_repo_lists(self):
        self.run_cmd("repo", "set", "site", "--untrusted", "--confirmed")
        with mock.patch.object(cli.Ctx, "confirm"):
            code, doc = self.run_json("repo", "add", "--all", "--trust")
        self.assertEqual(code, 0, doc)
        self.assertEqual(doc["data"]["trusted"], [self.rid("acme", "site")])
        self.assertTrue(self.link.is_symlink())
        self.assertFalse(os.path.lexists(self.paths.enabled_dir() / "lib"))

    def test_add_trust_lists_exactly_what_it_would_trust_in_a_dry_run(self):
        code, doc = self.run_json("repo", "add", "--all", "--trust", "--dry-run")
        self.assertEqual(doc["data"]["would_trust"], [self.rid("acme", "site")])
        self.assertFalse(os.path.lexists(self.link))

    def test_add_trust_without_a_person_is_refused(self):
        code, doc = self.run_json("repo", "add", "--all", "--trust")
        self.assertEqual((code, doc["data"]["code"]), (1, "needs-person"))
        self.assertFalse(os.path.lexists(self.link))

    def test_an_organization_in_the_persons_own_configuration_is_trusted(self):
        self.config(WS_HOST_REPOS=self.rid("acme", "site"), WS_HOST_TRUSTED="acme")
        _, doc = self.run_json("repo", "list")
        self.assertTrue(all(r["trusted"] for r in doc["data"]["repositories"]))
        self.assertIn("configuration trusts acme", doc["data"]["repositories"][0]["trust"])

    def test_doctor_warns_but_does_not_fail_when_a_trusted_repos_kits_changed(self):
        self.decide("site", "--trusted")
        up = self.site
        self.upstream_commit(up, ".workspaces-host/kits/k.py", "# changed\n")
        self.run_cmd("repo", "advance", "--all")
        code, doc = self.run_json("doctor")
        self.assertEqual(code, 0)
        self.assertTrue(any(c["name"] == "trust" and c["status"] == "warn" and "changed" in c["detail"] for c in doc["data"]["checks"]))

    def test_a_link_for_another_repository_with_the_same_name_is_not_overwritten(self):
        self.remote("other", "site")
        self.config(WS_HOST_REPOS=f"{self.rid('acme', 'site')} {self.rid('other', 'site')}")
        self.run_cmd("repo", "add", self.rid("other", "site"))
        self.decide(self.rid("acme", "site"), "--trusted")
        code, doc = self.decide(self.rid("other", "site"), "--trusted")
        self.assertNotEqual(code, 0)
        self.assertEqual((self.link.resolve()), (self.clone_path("acme", "site") / ".workspaces-host").resolve())
