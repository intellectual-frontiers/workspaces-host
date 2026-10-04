import json
import re

from .helpers import Home

JARGON = re.compile(r"\b(json|stderr|stdout|exit code|argv|uv\.lock|ff-only|fast-forward|symlink|ndjson)\b", re.I)


class Cli(Home):
    def test_command_list_text_json_and_html_say_the_same(self):
        _, text = self.run_cmd("command", "list")
        _, doc = self.run_json("command", "list")
        _, page = self.run_cmd("command", "list", "--html")
        for c in doc["data"]["commands"]:
            self.assertIn(c["id"], text)
            self.assertIn(c["id"], page)
        self.assertEqual(doc["schema"], "ws-host/command-list@1")
        self.assertEqual(doc["audience"], "private")
        self.assertNotIn("<script", page.lower())
        self.assertNotIn("http://", page)
        self.assertIn("default-src 'none'", page)

    def test_the_first_line_of_every_read_and_check_is_plain(self):
        for argv in (("command", "list"), ("doctor",), ("context",), ("command", "show", "doctor"), ("check", "registry")):
            _, text = self.run_cmd(*argv)
            first = text.splitlines()[0]
            self.assertTrue(first.endswith((".", "?")), (argv, first))
            self.assertIsNone(JARGON.search(first), (argv, first))

    def test_command_show_names_arguments_and_unknown_is_a_usage_error(self):
        code, doc = self.run_json("command", "show", "command", "show")
        self.assertEqual(code, 0)
        self.assertEqual(doc["data"]["args"][0]["name"], "ID")
        code, doc = self.run_json("command", "show", "nope")
        self.assertEqual((code, doc["kind"], doc["data"]["code"]), (2, "error", "unknown-command"))

    def test_an_unknown_command_is_an_error_resource_with_a_next_action(self):
        code, doc = self.run_json("frobnicate")
        self.assertEqual((code, doc["data"]["code"]), (2, "usage"))
        self.assertEqual(doc["actions"][0]["command"], "ws-host command list")

    def test_a_bad_option_is_a_usage_error_not_a_trace(self):
        code, text = self.run_cmd("doctor", "--nope")
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", text)

    def test_dry_run_is_refused_on_a_read_command(self):
        code, _ = self.run_cmd("command", "list", "--dry-run")
        self.assertEqual(code, 2)

    def test_an_unexpected_exception_becomes_an_internal_error_resource(self):
        from ws_host.core import registry as reg
        c = reg.discover().get(("command", "list"))
        real = c.fn
        c.fn = lambda ctx: 1 / 0
        try:
            code, doc = self.run_json("command", "list")
        finally:
            c.fn = real
        self.assertEqual((code, doc["data"]["code"]), (1, "internal"))
        self.assertNotIn("Traceback", json.dumps(doc))

    def test_reads_are_not_logged_but_a_check_is_with_the_surface(self):
        from ws_host.core import paths
        self.run_cmd("command", "list")
        self.assertFalse(paths.logs_dir().exists())
        import os
        os.environ["WS_HOST_SURFACE"] = "editor"
        self.run_cmd("check", "registry")
        line = json.loads((paths.logs_dir() / "ws-host.ndjson").read_text().splitlines()[-1])
        self.assertEqual((line["surface"], line["command"], line["exit"]), ("editor", "check", 0))

    def test_help_with_no_arguments_lists_commands(self):
        code, text = self.run_cmd()
        self.assertEqual(code, 0)
        self.assertIn("command list", text)


class Doctor(Home):
    def test_doctor_passes_here_and_holds_no_secret(self):
        from ws_host.core import paths
        paths.config_dir().mkdir(parents=True)
        paths.secrets_file().write_text("GH_TOKEN=supersecretvalue\n")
        paths.secrets_file().chmod(0o600)
        code, text = self.run_cmd("doctor", "--json")
        self.assertEqual(code, 0, text)
        self.assertNotIn("supersecretvalue", text)
        doc = json.loads(text)
        names = {c["name"] for c in doc["data"]["checks"]}
        self.assertTrue({"python", "uv", "git", "distribution", "registry", "secrets file"} <= names)
        self.assertIn("id", doc["data"]["distro"])

    def test_a_secrets_file_others_can_read_fails_doctor(self):
        from ws_host.core import paths
        paths.config_dir().mkdir(parents=True)
        paths.secrets_file().write_text("A=b\n")
        paths.secrets_file().chmod(0o644)
        code, doc = self.run_json("doctor")
        self.assertEqual(code, 1)
        self.assertTrue(any(c["name"] == "secrets file" and c["status"] == "fail" for c in doc["data"]["checks"]))

    def test_a_malformed_configuration_fails_doctor_with_the_line(self):
        from ws_host.core import paths
        paths.config_dir().mkdir(parents=True)
        paths.config_file().write_text("A=1\nbroken\n")
        code, doc = self.run_json("doctor")
        self.assertEqual(code, 1)
        self.assertTrue(any("line 2" in c["detail"] for c in doc["data"]["checks"]))

    def test_doctor_fails_on_a_registry_conflict(self):
        from ws_host.core import registry as reg
        r = reg.discover()
        r.conflicts.append("two commands are named 'x': a and b")
        try:
            code, doc = self.run_json("doctor")
        finally:
            r.conflicts.pop()
        self.assertEqual(code, 1)

    def test_context_holds_no_secret_and_masks_secret_looking_keys(self):
        from ws_host.core import paths
        paths.config_dir().mkdir(parents=True)
        paths.config_file().write_text("WS_HOST_GIT_NAME=Ada\nWS_HOST_API_TOKEN=abc123\n")
        paths.secrets_file().write_text("GH=zzz\n")
        paths.secrets_file().chmod(0o600)
        code, text = self.run_cmd("context", "--json")
        self.assertEqual(code, 0)
        self.assertNotIn("abc123", text)
        self.assertNotIn("zzz", text)
        self.assertIn("Ada", text)


class Check(Home):
    def test_registry_and_launcher_sections_pass(self):
        code, doc = self.run_json("check", "registry", "launcher")
        self.assertEqual(code, 0, doc)
        self.assertEqual(doc["data"]["summary"], {"run": 2, "failed": 0, "skipped": 0})

    def test_a_section_that_could_not_run_is_skipped_and_fails_the_run(self):
        code, doc = self.run_json("check", "specs")
        # no public root on this machine unless WS_HOST_PUBLIC_ROOT is set: skipped, never passed
        if doc["data"]["sections"][0]["status"] == "skip":
            self.assertEqual(code, 3)
            self.assertEqual(doc["data"]["summary"]["skipped"], 1)

    def test_an_unknown_section_is_a_usage_error(self):
        code, _ = self.run_cmd("check", "nope")
        self.assertEqual(code, 2)
