"""The spinner for slow steps, and the prompt command (0006-onboarding FR-020, 0003-kits FR-015)."""
import io
import json
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
        self.assertIn("ws-host-pretty.omp.json", text)
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


class Themes(ShellAdd):
    def test_the_plain_theme_holds_no_font_glyph_and_the_pretty_one_does(self):
        from ws_host.kits import shell
        def private(path):
            import json
            return [c for c in json.dumps(json.loads(path.read_text(encoding="utf-8")), ensure_ascii=False) if 0xE000 <= ord(c) <= 0xF8FF]
        self.assertEqual(private(shell.theme_path(shell.PLAIN)), [])
        self.assertTrue(private(shell.theme_path(shell.PRETTY)))
        for name in (shell.PRETTY, shell.PLAIN):
            import json
            json.loads(shell.theme_path(name).read_text(encoding="utf-8"))

    def test_both_themes_print_a_prompt_when_oh_my_posh_is_here(self):
        import shutil
        import subprocess
        from ws_host.kits import shell
        omp = shutil.which("oh-my-posh") or next(iter(__import__("glob").glob("/tmp/*/.local/bin/oh-my-posh")), None)
        if not omp or not os.access(omp, os.X_OK) or os.path.getsize(omp) < 1000:
            self.skipTest("oh-my-posh is not on this machine")
        for name in (shell.PRETTY, shell.PLAIN):
            p = subprocess.run([omp, "print", "primary", "--config", str(shell.theme_path(name)), "--shell", "bash"], capture_output=True, text=True, timeout=60)
            self.assertTrue(p.returncode == 0 and p.stdout.strip(), name)

    def test_the_plain_flag_chooses_the_plain_theme_and_the_default_goes_back(self):
        self.run_cmd("shell", "add", "bash", "--plain")
        self.assertIn("ws-host-plain.omp.json", self.bashrc.read_text())
        self.assertNotIn("ws-host-pretty.omp.json", self.bashrc.read_text())
        self.run_cmd("shell", "add", "bash")
        text = self.bashrc.read_text()
        self.assertIn("ws-host-pretty.omp.json", text)
        self.assertEqual(text.count("workspaces-host: prompt"), 1)

    def test_the_prompt_theme_setting(self):
        from ws_host.core import config
        for value, expect in ((None, "ws-host-pretty"), ("yes", "ws-host-pretty"), ("pretty", "ws-host-pretty"), ("plain", "ws-host-plain"),
                              ("no", None), ("off", None), ("NO", None)):
            self.paths.config_dir().mkdir(parents=True, exist_ok=True)
            self.paths.config_file().write_text("" if value is None else f'WS_HOST_PROMPT="{value}"\n')
            self.assertEqual(config.load().prompt_theme(), expect, value)


class SetupPrompt(Home):
    """workspace ensure gives the shells the prompt by default (0006-onboarding FR-022)."""

    def setUp(self):
        super().setUp()
        import shutil
        self.bin = self.home / ".local" / "bin"
        self.bin.mkdir(parents=True)
        (self.bin / "oh-my-posh").write_text("#!/bin/sh\n")
        (self.bin / "oh-my-posh").chmod(0o755)
        self.bashrc = self.home / ".bashrc"
        self.bashrc.write_text("alias a=b\n")
        self.paths.config_dir().mkdir(parents=True, exist_ok=True)
        self.fakebin = self.home.parent / "fakebin"
        self.fakebin.mkdir()
        (self.fakebin / "gh").write_text("#!/bin/sh\nexit 0\n")
        (self.fakebin / "gh").chmod(0o755)
        os.environ["PATH"] = f"{self.fakebin}:{os.environ['PATH']}"

    def ensure(self, **conf):
        self.paths.config_file().write_text('WS_HOST_KIT=""\nWS_HOST_REPOS=""\n' + "".join(f'{k}="{v}"\n' for k, v in conf.items()))
        code, doc = self.run_json("workspace", "ensure")
        return code, doc

    def step(self, doc):
        return [s for s in doc["data"]["steps"] if s["name"] == "prompt"]

    def test_it_is_given_by_default_with_nothing_to_add(self):
        code, doc = self.ensure()
        self.assertEqual(code, 0)
        self.assertIn("ws-host-pretty.omp.json", self.bashrc.read_text())
        self.assertEqual(self.step(doc)[0]["status"], "ok")

    def test_the_plain_setting_gives_the_plain_theme(self):
        self.ensure(WS_HOST_PROMPT="plain")
        self.assertIn("ws-host-plain.omp.json", self.bashrc.read_text())

    def test_no_keeps_the_persons_own_prompt(self):
        _, doc = self.ensure(WS_HOST_PROMPT="no")
        self.assertEqual(self.bashrc.read_text(), "alias a=b\n")
        self.assertEqual(self.step(doc), [])

    def test_a_dry_run_changes_nothing(self):
        self.paths.config_file().write_text('WS_HOST_KIT=""\nWS_HOST_REPOS=""\n')
        code, doc = self.run_json("workspace", "ensure", "--dry-run")
        self.assertEqual(self.bashrc.read_text(), "alias a=b\n")
        self.assertIn("would give your terminal the ws-host-pretty prompt", doc["data"]["would"])

    def test_a_block_the_person_edited_is_never_put_back(self):
        self.ensure()
        edited = self.bashrc.read_text().replace("ws-host-pretty.omp.json", "my-own.omp.json")
        self.bashrc.write_text(edited)
        _, doc = self.ensure()
        self.assertEqual(self.bashrc.read_text(), edited)
        self.assertIn("already has its prompt", self.step(doc)[0]["plain"])

    def test_a_prompt_that_cannot_be_set_up_never_fails_the_setup(self):
        (self.bin / "oh-my-posh").unlink()
        os.environ["WS_HOST_OFFLINE"] = "1"
        code, doc = self.ensure()
        self.assertEqual(code, 0, doc)
        self.assertEqual(self.step(doc)[0]["status"], "warn")
        self.assertIn("ws-host shell add bash", self.step(doc)[0]["plain"])
        self.assertEqual(self.bashrc.read_text(), "alias a=b\n")


class SlowEditor(Home):
    """VS Code's `code` command is a slow, silent step the first time in WSL (0006-onboarding FR-020)."""

    def setUp(self):
        super().setUp()
        self.fakebin = self.home.parent / "fakebin"
        self.fakebin.mkdir()
        os.environ["PATH"] = f"{self.fakebin}:{os.environ['PATH']}"
        from ws_host.core import machine
        real = machine.distro
        machine.distro = lambda: {**real(), "wsl": True}
        self.addCleanup(lambda: setattr(machine, "distro", real))

    def fake_code(self, script):
        f = self.fakebin / "code"
        f.write_text("#!/bin/sh\n" + script)
        f.chmod(0o755)

    def test_the_first_call_in_wsl_is_known_and_a_later_one_is_not(self):
        from ws_host.commands import vscode
        self.assertTrue(vscode.first_time_in_wsl())
        (self.home / ".vscode-server" / "bin").mkdir(parents=True)
        self.assertFalse(vscode.first_time_in_wsl())

    def test_the_spinner_says_how_much_the_helper_has_downloaded(self):
        from ws_host.commands import vscode
        saved = (progress.DELAY, progress.ENABLED)
        progress.DELAY, progress.ENABLED = 0.1, True
        self.addCleanup(lambda: (setattr(progress, "DELAY", saved[0]), setattr(progress, "ENABLED", saved[1])))
        os.environ.update(TERM="xterm", LANG="C.UTF-8")
        self.fake_code(f'mkdir -p "{self.home}/.vscode-server/bin"\ndd if=/dev/zero of="{self.home}/.vscode-server/bin/vscode-server.tar.gz" bs=1000000 count=3 2>/dev/null\nsleep 0.8\nexit 0\n')
        out = Tty()
        real_working = progress.Working
        progress.working = lambda label, probe=None: real_working(label, out, probe)
        self.addCleanup(lambda: setattr(progress, "working", lambda label, probe=None: real_working(label, probe=probe)))
        p = vscode.run_code(["--list-extensions"], "Asking VS Code what is installed")
        self.assertEqual(p.returncode, 0)
        text = ANSI.sub("", out.getvalue())
        self.assertIn("Asking VS Code what is installed", text)
        self.assertRegex(text, r"3 MB downloaded")

    def test_a_code_command_that_takes_too_long_is_a_plain_error_not_a_trace(self):
        from ws_host.commands import vscode
        from ws_host.core.resource import WsError
        self.fake_code("sleep 5\n")
        with self.assertRaises(WsError) as caught:
            vscode.run_code(["--list-extensions"], "Asking VS Code", timeout=1)
        self.assertEqual(caught.exception.code, "code-timeout")
        self.assertIn("carry on", caught.exception.plain)

    def test_setup_warns_before_the_slow_first_step(self):
        self.paths.config_dir().mkdir(parents=True, exist_ok=True)
        self.paths.config_file().write_text('WS_HOST_KIT=""\nWS_HOST_REPOS=""\nWS_HOST_PROMPT="no"\n')
        self.fake_code("exit 0\n")
        (self.fakebin / "gh").write_text("#!/bin/sh\nexit 0\n")
        (self.fakebin / "gh").chmod(0o755)
        code, out = self.run_cmd("workspace", "ensure", "--json")
        docs = [json.loads(l) for l in out.strip().splitlines()]
        editor = [d for d in docs if d["kind"] == "progress" and d["id"] == "editor"][0]
        self.assertIn("downloads a small helper", editor["data"]["plain"])
        self.assertIn("a few minutes", editor["data"]["plain"])

    def test_vscode_advance_explains_itself_first_and_ends_with_what_to_do_next(self):
        self.fake_code('case "$1" in --list-extensions) echo some.other;; esac\nexit 0\n')
        code, out = self.run_cmd("vscode", "ensure", "--json")
        docs = [json.loads(l) for l in out.strip().splitlines()]
        self.assertEqual(docs[0]["kind"], "progress")
        self.assertIn("nothing for you to do", docs[0]["data"]["plain"])
        self.assertIn("a few minutes", docs[0]["data"]["plain"])        # the first call in WSL downloads the helper
        self.assertEqual(docs[-1]["kind"], "vscode-setup")
        self.assertIn("Workspace: Learn", docs[-1]["data"]["next"])
        self.assertIn("Reload", docs[-1]["data"]["reload"])
        code, out = self.run_cmd("vscode", "ensure", "--dry-run", "--json")
        self.assertEqual([json.loads(l)["kind"] for l in out.strip().splitlines()], ["vscode-setup"])
