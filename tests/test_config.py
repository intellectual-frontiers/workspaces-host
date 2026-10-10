"""0010-managed-config: the files ws-host manages for a person are written by chezmoi, from ws-host's own source state."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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

    def test_the_tested_chezmoi_names_a_checksum_for_both_architectures(self):
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

    def fake(self, version: str):
        d = self.home / "fakebin"
        d.mkdir(exist_ok=True)
        (d / "chezmoi").write_text(f'#!/bin/sh\ncase "$1" in --version) echo "chezmoi version v{version}, commit x";; *) exec "{chezmoi_for_tests()}" "$@";; esac\n')
        (d / "chezmoi").chmod(0o755)
        return d

    def test_the_chezmoi_on_the_path_is_the_one_used_and_nothing_is_installed(self):
        os.environ.pop("WS_HOST_CHEZMOI", None)
        os.environ["PATH"] = f"{self.fake('9.9.9')}:{os.environ['PATH']}"
        self.assertEqual(chezmoi.program(), self.home / "fakebin" / "chezmoi")
        (self.home / ".bashrc").write_text("")
        self.assertEqual(self.run_json("shell", "add", "bash")[0], 0)
        self.assertFalse((self.home / ".local" / "bin" / "chezmoi").exists())

    def test_a_chezmoi_older_than_the_tested_one_ends_with_exit_3_and_says_how_to_upgrade(self):
        os.environ.pop("WS_HOST_CHEZMOI", None)
        os.environ["PATH"] = f"{self.fake('2.1.0')}:{os.environ['PATH']}"
        (self.home / ".bashrc").write_text("")
        code, doc = self.run_json("shell", "add", "bash")
        self.assertEqual(code, 3, doc)
        self.assertIn("chezmoi upgrade", doc["data"]["plain"])

    def test_a_newer_chezmoi_is_accepted(self):
        os.environ["WS_HOST_CHEZMOI"] = str(self.fake("99.0.0") / "chezmoi")
        self.assertEqual(chezmoi.program().name, "chezmoi")

    def test_with_none_here_the_fetched_one_is_a_plain_file_the_person_owns(self):
        os.environ.pop("WS_HOST_CHEZMOI", None)
        os.environ["PATH"] = "/usr/bin:/bin"
        if chezmoi.on_path():
            self.skipTest("this machine has a chezmoi on its system PATH")
        (self.home / ".bashrc").write_text("")
        code, doc = self.run_json("shell", "add", "bash")
        self.assertEqual(code, 0, doc)
        mine = self.home / ".local" / "bin" / "chezmoi"
        self.assertTrue(mine.is_file() and not mine.is_symlink())
        mine.write_text(mine.read_text(errors="ignore")[:0] + "#!/bin/sh\necho 'chezmoi version v99.0.0, commit x'\n")      # the person replaces it
        mine.chmod(0o755)
        self.assertEqual(chezmoi.version_of(chezmoi.program()), (99, 0, 0))

    def test_a_missing_chezmoi_while_offline_exits_3(self):
        os.environ.pop("WS_HOST_CHEZMOI", None)
        os.environ["PATH"] = "/nonexistent"
        (self.home / ".bashrc").write_text("")
        os.environ["WS_HOST_OFFLINE"] = "1"
        self.run_json("shell", "add", "bash", "--dry-run")
        (self.home / ".bashrc").write_text(managed.with_block("", "bash", "t"))
        code, doc = self.run_json("config", "show")
        self.assertEqual(code, 3, doc)


class Modern(Home):
    """0003-kits FR-019: the modern-cli lines in bash, fish and git, from pure text functions, checked by the shells and by git themselves."""

    def test_each_file_gets_the_lines_once_and_a_second_run_changes_nothing(self):
        for kind in ("bash", "fish", "git"):
            a = managed.with_modern("mine\n", kind)
            self.assertTrue(a.startswith("mine\n") if kind != "git" else a.endswith("mine\n"), kind)
            self.assertEqual(managed.with_modern(a, kind), a)
            self.assertEqual(managed.with_modern(a, kind, icons=False).count(managed.MODERN_BEGIN), 1)

    def test_icons_are_on_unless_the_plain_prompt_was_chosen(self):
        self.assertIn("--icons=auto", managed.modern_block("bash"))
        self.assertNotIn("--icons", managed.modern_block("bash", icons=False))
        self.assertIn("alias ll", managed.modern_block("fish"))

    def test_bash_accepts_the_lines_and_the_old_commands_stay_when_a_tool_is_missing(self):
        text = managed.with_modern("", "bash")
        self.assertEqual(subprocess.run(["bash", "-n"], input=text, text=True, capture_output=True).returncode, 0)
        out = subprocess.run(["bash", "--norc", "-i", "-c", text + '\nalias ll'], text=True, capture_output=True, env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("ls -lh", out.stdout)

    def test_git_reads_the_lines_and_a_value_set_below_them_wins(self):
        text = managed.with_modern("[core]\n\tpager = less\n", "git")
        f = Path(tempfile.mkdtemp()) / "gitconfig"
        f.write_text(text)
        out = subprocess.run(["git", "config", "--file", str(f), "--get-all", "core.pager"], capture_output=True, text=True)
        self.assertEqual(out.stdout.split(), ["delta", "less"])
        self.assertEqual(subprocess.run(["git", "config", "--file", str(f), "core.pager"], capture_output=True, text=True).stdout.strip(), "less")

    def test_a_block_without_its_end_line_is_refused(self):
        with self.assertRaises(managed.MarkersLost):
            managed.with_modern(managed.MODERN_BEGIN + "\nx\n", "bash")

    def test_one_script_can_run_the_prompt_and_the_modern_lines_in_turn(self):
        both = managed.run("chain", [json.dumps([["bash", "$HOME/t.json"], ["modern-bash", "icons"]])], "keep\n")
        self.assertIn("oh-my-posh", both)
        self.assertIn("zoxide", both)
        self.assertTrue(both.startswith("keep\n"))


@unittest.skipUnless(chezmoi_for_tests(), "chezmoi could not be had")
class ModernApplied(Home):
    def test_apply_writes_bash_and_git_through_chezmoi_keeps_the_prompt_and_is_current_the_second_time(self):
        from ws_host.lib import modern
        (self.home / ".bashrc").write_text("alias a=b\n")
        self.run_json("shell", "add", "bash")
        with_prompt = (self.home / ".bashrc").read_text()
        r = modern.apply()
        self.assertIn("bash modern tools", r["changed"])
        text = (self.home / ".bashrc").read_text()
        self.assertTrue(text.startswith(with_prompt.rstrip("\n")))
        self.assertIn("oh-my-posh", text)
        self.assertIn("zoxide init bash", text)
        self.assertTrue((self.home / ".gitconfig").read_text().startswith(managed.MODERN_BEGIN))
        self.assertEqual(modern.apply()["changed"], [])
        self.assertTrue(modern.configured())
        code, doc = self.run_json("config", "check")
        self.assertEqual(code, 0, doc)
