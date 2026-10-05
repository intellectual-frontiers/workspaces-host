"""Every warning and failure is actionable, and nothing points at something a reader cannot see (0001-ws-host FR-017)."""
import os
import re
from pathlib import Path

from ws_host.commands import doctor
from .helpers import Home

SOURCE = (Path(__file__).resolve().parent.parent / "ws_host/commands/doctor.py").read_text()


class Actionable(Home):
    def checks(self):
        code, doc = self.run_json("doctor")
        return doc, {c["name"]: c for c in doc["data"]["checks"]}

    def assert_actionable(self, doc):
        for c in doc["data"]["checks"]:
            if c["status"] in ("warn", "fail"):
                self.assertTrue(isinstance(c.get("action"), int) or c.get("cli") or c.get("todo"), f"{c['name']} says what is wrong and nothing else: {c}")
                if isinstance(c.get("action"), int):
                    self.assertTrue(doc["actions"][c["action"]]["cli"] or doc["actions"][c["action"]]["command"])

    def test_every_check_in_the_source_that_can_warn_or_fail_carries_a_fix_or_what_to_do(self):
        import ast
        tree = ast.parse(SOURCE)
        seen = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_check":
                segment = ast.get_source_segment(SOURCE, node) or ""
                if '"warn"' in segment or '"fail"' in segment:
                    seen += 1
                    self.assertTrue({k.arg for k in node.keywords} & {"action", "cli", "todo"}, segment[:140])
        self.assertGreater(seen, 10)

    def test_a_finding_with_neither_gets_a_plain_line_that_asks_for_help(self):
        checks = [{"name": "x", "status": "warn", "detail": "odd"}, {"name": "y", "status": "ok", "detail": "fine"}]
        doctor._actionable(checks)
        self.assertIn("ws-host context", checks[0]["todo"])
        self.assertNotIn("todo", checks[1])

    def test_a_loose_secrets_file_a_bad_configuration_and_a_missing_launcher_say_what_to_do(self):
        self.paths.config_dir().mkdir(parents=True, exist_ok=True)
        self.paths.secrets_file().write_text("TOKEN=x\n")
        os.chmod(self.paths.secrets_file(), 0o644)
        self.paths.config_file().write_text("WS_HOST_REPOS='unclosed\nNOPE_KEY=1\n")
        doc, c = self.checks()
        self.assertIn("chmod 600", c["secrets file"]["cli"])
        self.assertIn("code ", c["configuration"]["cli"])
        self.assertIn("install.sh", c["launcher"]["cli"])
        self.assert_actionable(doc)

    def test_an_unset_pull_setting_is_a_button_and_a_waiting_update_is_a_button(self):
        from ws_host.lib import selfupdate
        selfupdate.write_notice(2)
        doc, c = self.checks()
        self.assertEqual(doc["actions"][c["git pull setting"]["action"]]["cli"], "ws-host workspace set --pull-ff-only")
        self.assertEqual(doc["actions"][c["ws-host version"]["action"]]["cli"], "ws-host update")
        self.assert_actionable(doc)

    def test_the_plain_sentence_points_at_nothing_below(self):
        for checks in ([{"status": "warn"}], [{"status": "warn"}] * 3, [{"status": "fail"}], [{"status": "ok"}]):
            self.assertNotRegex(doctor._plain(checks), r"(?i)\b(below|above)\b")
        self.assertEqual(doctor._plain([{"status": "warn"}]), "Your machine is ready, with 1 suggestion.")
        self.assertEqual(doctor._plain([{"status": "warn"}] * 2), "Your machine is ready, with 2 suggestions.")

    def test_the_terminal_shows_each_fix_under_its_finding(self):
        os.environ["WS_HOST_COLOR"] = "always"
        _, out = self.run_cmd("doctor")
        text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", out)
        self.assertIn("→ ws-host workspace set --pull-ff-only", text)
        self.assertIn("→ curl -fsSL", text)

    def test_context_still_holds_no_action_objects(self):
        code, doc = self.run_json("context")
        import json
        json.dumps(doc)
        self.assertEqual(code, 0)
