"""Tab completion for bash and fish, made from the registry (0006-onboarding FR-023)."""
import json
import os
import shutil
import stat
import subprocess
import unittest

from ws_host.core import registry as reg
from ws_host.lib import completion
from .helpers import Home


def complete_bash(script_path, *words):
    """What bash would offer after `words` (the last may be a partial word)."""
    src = f'. "{script_path}"; COMP_WORDS=({" ".join(repr(w) if w else chr(39) * 2 for w in words)}); COMP_CWORD=$((${{#COMP_WORDS[@]}}-1)); COMPREPLY=(); _ws_host; printf "%s\\n" "${{COMPREPLY[@]}}"'
    p = subprocess.run(["bash", "-c", src], capture_output=True, text=True, timeout=60)
    return sorted(p.stdout.split())


class Generated(Home):
    def setUp(self):
        super().setUp()
        self.model = completion.model()
        self.script = self.home.parent / "ws-host.bash"
        self.script.write_text(completion.bash(self.model))

    def test_the_script_is_valid_bash(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(self.script)]).returncode, 0)

    def test_every_command_the_registry_has_completes(self):
        registry = reg.discover()
        first = complete_bash(self.script, "ws-host", "")
        for words, c in registry.commands.items():
            self.assertIn(words[0], first, c.id)
            if len(words) == 2:
                self.assertIn(words[1], complete_bash(self.script, "ws-host", words[0], ""), c.id)

    def test_a_partial_word_is_finished(self):
        self.assertEqual(complete_bash(self.script, "ws-host", "wor"), ["workspace"])
        self.assertEqual(complete_bash(self.script, "ws-host", "kit", "ad"), ["add"])

    def test_options_are_offered_for_the_command_and_the_global_ones(self):
        offered = complete_bash(self.script, "ws-host", "shell", "add", "bash", "--")
        for o in ("--plain", "--dry-run", "--json", "--html", "--debug", "--offline"):
            self.assertIn(o, offered)
        self.assertNotIn("--confirmed", offered)
        self.assertIn("--confirmed", complete_bash(self.script, "ws-host", "repo", "set", "x", "--"))

    def test_the_values_of_arguments_are_offered(self):
        self.assertEqual(complete_bash(self.script, "ws-host", "kit", "add", ""), ["base", "press", "rust", "shell"])
        self.assertEqual(complete_bash(self.script, "ws-host", "shell", "add", ""), ["bash", "fish"])
        self.assertEqual(complete_bash(self.script, "ws-host", "auth", "new", ""), ["github", "gitlab"])
        self.assertIn("start", complete_bash(self.script, "ws-host", "help", ""))
        self.assertIn("registry", complete_bash(self.script, "ws-host", "check", ""))

    def test_the_value_of_an_option_is_not_counted_as_an_argument(self):
        self.assertIn("registry", complete_bash(self.script, "ws-host", "check", "--suite", "all", ""))

    def test_repositories_are_asked_for_when_tab_is_pressed(self):
        shim = self.home.parent / "shim"
        shim.mkdir()
        launcher = os.path.join(os.path.dirname(__file__), "..", "ws-host")
        (shim / "ws-host").write_text(f'#!/bin/sh\nexec "{os.path.abspath(launcher)}" "$@"\n')
        (shim / "ws-host").chmod(0o755)
        os.environ["PATH"] = f"{shim}:{os.environ['PATH']}"
        self.paths.config_dir().mkdir(parents=True, exist_ok=True)
        self.paths.config_file().write_text('WS_HOST_REPOS="github.com/acme/site github.com/acme/lib"\n')
        self.assertEqual(complete_bash(self.script, "ws-host", "repo", "status", ""), ["github.com/acme/lib", "github.com/acme/site"])

    def test_a_dynamic_value_is_not_baked_into_the_script(self):
        self.assertNotIn("intellectual-frontiers", self.script.read_text())
        self.assertIn("ws-host completion list REPO", self.script.read_text())

    def test_the_fish_script_where_fish_is_installed(self):
        fish = shutil.which("fish")
        if not fish:
            self.skipTest("fish is not installed here")
        script = self.home.parent / "ws-host.fish"
        script.write_text(completion.fish(self.model))
        src = f'source {script}; for l in "ws-host " "ws-host re" "ws-host repo " "ws-host kit add " "ws-host shell add bash --" "ws-host check --suite x "; echo "[$l] "(complete -C "$l" | string replace -r "\\t.*" "" | string join " "); end'
        out = subprocess.run([fish, "-c", src], capture_output=True, text=True, timeout=60, env={**os.environ, "HOME": str(self.home)}).stdout
        self.assertIn("[ws-host ] ", out)
        lines = dict(l.split("] ", 1) for l in out.strip().splitlines())
        self.assertIn("workspace", lines["[ws-host "].split())
        self.assertEqual(lines["[ws-host re"].split(), ["repo"])
        self.assertEqual(sorted(lines["[ws-host repo "].split()), sorted(self.model["verbs"]["repo"]))
        self.assertEqual(lines["[ws-host kit add "].split(), ["base", "press", "rust", "shell"])
        self.assertIn("--plain", lines["[ws-host shell add bash --"].split())
        self.assertIn("registry", lines["[ws-host check --suite x "].split())


class Installing(Home):
    def test_it_writes_each_shell_where_it_looks_by_itself(self):
        code, out = self.run_cmd("completion", "add", "bash")
        self.assertEqual(code, 0, out)
        f = self.home / ".local/share/bash-completion/completions/ws-host"
        self.assertTrue(f.is_file())
        self.assertIn("complete -F _ws_host ws-host", f.read_text())
        self.run_cmd("completion", "add", "fish")
        self.assertTrue((self.home / ".config/fish/completions/ws-host.fish").is_file())

    def test_a_second_run_changes_nothing_and_a_dry_run_writes_nothing(self):
        self.run_cmd("completion", "add", "bash")
        f = self.home / ".local/share/bash-completion/completions/ws-host"
        before = f.stat().st_mtime_ns
        code, doc = self.run_json("completion", "add", "bash")
        self.assertEqual((doc["data"]["status"], f.stat().st_mtime_ns), ("current", before))
        f.unlink()
        code, doc = self.run_json("completion", "add", "bash", "--dry-run")
        self.assertEqual(doc["data"]["status"], "would-write")
        self.assertFalse(f.exists())

    def test_a_file_the_person_wrote_is_left_alone(self):
        f = self.home / ".local/share/bash-completion/completions/ws-host"
        f.parent.mkdir(parents=True)
        f.write_text("# mine\ncomplete -W 'a b' ws-host\n")
        code, doc = self.run_json("completion", "add", "bash")
        self.assertEqual(doc["data"]["status"], "left-alone")
        self.assertEqual(f.read_text(), "# mine\ncomplete -W 'a b' ws-host\n")

    def test_it_edits_no_startup_file(self):
        (self.home / ".bashrc").write_text("alias a=b\n")
        self.run_cmd("completion", "add", "bash")
        self.assertEqual((self.home / ".bashrc").read_text(), "alias a=b\n")

    def test_completion_list_prints_one_value_per_line_for_a_shell_to_read(self):
        code, out = self.run_cmd("completion", "list", "KIT")
        self.assertEqual([l[4:] for l in out.splitlines() if l.startswith("  - ")], ["base", "press", "rust", "shell"])
        code, out = self.run_cmd("completion", "list", "NOPE")
        self.assertEqual(code, 2)

    def test_setup_renews_the_files_and_says_so(self):
        (self.home.parent / "fakebin").mkdir()
        gh = self.home.parent / "fakebin" / "gh"
        gh.write_text("#!/bin/sh\nexit 0\n")
        gh.chmod(0o755)
        os.environ["PATH"] = f"{self.home.parent / 'fakebin'}:{os.environ['PATH']}"
        self.paths.config_dir().mkdir(parents=True, exist_ok=True)
        self.paths.config_file().write_text('WS_HOST_KIT=""\nWS_HOST_REPOS=""\nWS_HOST_PROMPT="no"\n')
        code, out = self.run_cmd("workspace", "advance", "--json")
        docs = [json.loads(l) for l in out.strip().splitlines()]
        step = [s for s in docs[-1]["data"]["steps"] if s["name"] == "completions"][0]
        self.assertEqual(step["status"], "ok")
        self.assertTrue((self.home / ".local/share/bash-completion/completions/ws-host").is_file())
        self.assertFalse((self.home / ".bashrc").exists())

    def test_the_base_kit_installs_bash_completion(self):
        kit = reg.discover().kits["base"]()
        self.assertIn("bash-completion", kit.apt({"id": "debian", "codename": "trixie", "id_like": ""}))
