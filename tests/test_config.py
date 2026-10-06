"""0010-managed-config: the files ws-host manages for a person are written by chezmoi, from ws-host's own source state."""
import json
import os
import subprocess
import sys
import unittest

from ws_host.lib import chezmoi, managed

from .helpers import REPO, Home, chezmoi_for_tests


class Managed(unittest.TestCase):
    """The text functions chezmoi's modify scripts run: pure, and the same twice."""

    def test_a_block_is_added_once_and_then_left_as_it_is(self):
        a = managed.with_block("alias x=y\n", "bash", "$HOME/t.json")
        self.assertTrue(a.startswith("alias x=y\n"))
        self.assertEqual(managed.with_block(a, "bash", "$HOME/t.json"), a)

    def test_a_block_is_replaced_in_place_and_nothing_outside_it_changes(self):
        old = managed.with_block("top\n", "bash", "$HOME/old.json") + "bottom\n"
        new = managed.with_block(old, "bash", "$HOME/new.json")
        self.assertIn("new.json", new)
        self.assertNotIn("old.json", new)
        self.assertTrue(new.startswith("top\n") and new.endswith("bottom\n"))

    def test_keep_existing_never_puts_a_theme_back(self):
        mine = managed.with_block("", "bash", "$HOME/mine.json")
        self.assertEqual(managed.with_block(mine, "bash", "$HOME/other.json", keep_existing=True), mine)

    def test_a_block_without_its_end_line_is_refused(self):
        with self.assertRaises(managed.MarkersLost):
            managed.with_block(managed.BEGIN.format(shell="bash") + "\nx\n", "bash", "t")

    def test_settings_add_what_is_missing_and_change_nothing_a_person_set(self):
        out = json.loads(managed.with_settings('{"a": 1}', {"a": 2, "b": 3}))
        self.assertEqual(out, {"a": 1, "b": 3})
        self.assertEqual(managed.with_settings('{"a": 1}', {"a": 2}), '{"a": 1}')
        self.assertIsNone(managed.with_settings("// a comment\n{}", {"b": 1}))

    def test_run_as_a_script_it_reads_stdin_and_writes_stdout(self):
        p = subprocess.run([sys.executable, "-m", "ws_host.lib.managed", "vscode-settings", '{"b": 1}'], input='{"a": 1}', capture_output=True, text=True, cwd=REPO)
        self.assertEqual(json.loads(p.stdout), {"a": 1, "b": 1})

    def test_the_pinned_chezmoi_names_a_checksum_for_both_architectures(self):
        for arch in ("x86_64", "aarch64"):
            self.assertRegex(chezmoi.DOWNLOAD.sha256[arch], r"^[0-9a-f]{64}$")
        self.assertIn("{goarch}", chezmoi.DOWNLOAD.url)


@unittest.skipUnless(chezmoi_for_tests(), "chezmoi could not be had")
class Config(Home):
    def test_nothing_is_managed_until_a_person_asks(self):
        code, doc = self.run_json("config", "show")
        self.assertEqual(code, 0)
        self.assertEqual(doc["data"]["files"], [])

    def test_shell_add_writes_through_chezmoi_and_a_stale_block_is_found_and_repaired_with_a_copy_kept(self):
        (self.home / ".bashrc").write_text("alias a=b\n")
        code, doc = self.run_json("shell", "add", "bash")
        self.assertEqual(code, 0, doc)
        text = (self.home / ".bashrc").read_text()
        self.assertTrue(text.startswith("alias a=b\n"))
        self.assertTrue((self.paths.data_dir() / "chezmoi" / "source" / "modify_dot_bashrc").is_file())
        self.assertEqual(self.run_json("config", "check")[0], 0)
        (self.home / ".bashrc").write_text(text.replace("update --check", "update --old"))
        self.assertEqual(self.run_json("config", "check")[0], 1)
        code, doc = self.run_json("config", "ensure")
        self.assertEqual(code, 0, doc)
        self.assertEqual((self.home / ".bashrc").read_text(), text)
        self.assertTrue(list((self.paths.state_dir() / "backups").glob(".bashrc.*")))
        self.assertEqual(self.run_json("config", "check")[0], 0)

    def test_a_theme_a_person_chose_survives_an_update_of_the_block(self):
        (self.home / ".bashrc").write_text("")
        self.run_json("shell", "add", "bash")
        f = self.home / ".bashrc"
        f.write_text(f.read_text().replace("ws-host-pretty", "my-theme").replace("update --check", "update --old"))
        self.assertEqual(self.run_json("config", "ensure")[0], 0)
        self.assertIn("my-theme", f.read_text())
        self.assertNotIn("update --old", f.read_text())

    def test_a_dry_run_changes_nothing(self):
        (self.home / ".bashrc").write_text("x\n")
        code, doc = self.run_json("shell", "add", "bash", "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual((self.home / ".bashrc").read_text(), "x\n")

    def test_vscode_settings_are_merged_by_chezmoi_and_a_set_value_is_kept(self):
        from ws_host.commands import vscode
        f = vscode.settings_file()
        f.parent.mkdir(parents=True)
        f.write_text('{"files.autoSave": "off"}')
        r = vscode.merge_settings(f, vscode.baseline_settings(), False)
        self.assertEqual(r["status"], "added")
        data = json.loads(f.read_text())
        self.assertEqual(data["files.autoSave"], "off")
        self.assertIn("git.autofetch", data)
        self.assertEqual(vscode.merge_settings(f, vscode.baseline_settings(), False)["status"], "unchanged")

    def test_a_missing_chezmoi_while_offline_exits_3(self):
        os.environ.pop("WS_HOST_CHEZMOI", None)
        (self.home / ".bashrc").write_text("")
        os.environ["WS_HOST_OFFLINE"] = "1"
        self.run_json("shell", "add", "bash", "--dry-run")
        (self.home / ".bashrc").write_text(managed.with_block("", "bash", "t"))
        code, doc = self.run_json("config", "show")
        self.assertEqual(code, 3, doc)
