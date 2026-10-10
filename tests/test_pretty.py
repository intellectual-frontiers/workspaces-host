"""What a person sees at a terminal: sections, rows, marks and the next step (0006-onboarding FR-024)."""
import json
import os
import re

from ws_host.core import pretty, render
from ws_host.core.resource import Action, Resource
from .helpers import Home

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class Pretty(Home):
    def setUp(self):
        super().setUp()
        os.environ.pop("NO_COLOR", None)
        os.environ["COLUMNS"] = "90"

    def styled(self, *argv):
        os.environ["WS_HOST_COLOR"] = "always"
        code, out = self.run_cmd(*argv)
        return code, ANSI.sub("", out)

    def plain(self, *argv):
        os.environ["WS_HOST_COLOR"] = "never"
        return self.run_cmd(*argv)[1]

    def test_doctor_has_sections_marks_and_a_next_step(self):
        _, text = self.styled("doctor")
        for heading in ("Details", "This machine", "Health checks", "Kits", "What you can do next"):
            self.assertIn(heading, text)
        self.assertRegex(text, r"✅ python\s+python ")
        self.assertIn("─" * 20, text)
        self.assertRegex(text.splitlines()[0], r"^🩺  \S")

    def test_the_first_line_is_still_the_plain_sentence(self):
        _, styled = self.styled("doctor")
        plain = self.plain("doctor")
        self.assertEqual(re.sub(r"^[^A-Za-z0-9]+", "", styled.splitlines()[0]), plain.splitlines()[0])

    def test_a_pipe_gets_the_plain_text_scripts_depend_on(self):
        text = self.plain("doctor")
        self.assertNotIn("\x1b", text)
        self.assertNotIn("─", text)
        self.assertEqual(text.splitlines()[1], "audience: private")
        out = self.plain("completion", "list", "KIT")
        self.assertEqual([l[4:] for l in out.splitlines() if l.startswith("  - ")], ["aws", "azure", "base", "cloud", "cloudflare", "press", "railway", "rust", "shell"])

    def test_json_and_html_are_never_decorated(self):
        os.environ["WS_HOST_COLOR"] = "always"
        _, out = self.run_cmd("doctor", "--json")
        self.assertNotIn("\x1b", out)
        json.loads(out.splitlines()[-1])
        _, html = self.run_cmd("doctor", "--html")
        self.assertNotIn("\x1b", html)

    def test_nothing_is_wider_than_the_terminal(self):
        for argv in (("doctor",), ("kit", "list"), ("command", "list"), ("repo", "list")):
            _, text = self.styled(*argv)
            for line in text.splitlines():
                if line.startswith("─") or line.strip().startswith("→"):
                    continue          # a line to type is never broken, so that copying it gives one line
                self.assertLessEqual(len(line), 100, (argv, line))

    def test_every_status_has_a_mark_and_a_word_nearby(self):
        r = Resource("check", "x", {"plain": "Two things.", "sections": [{"name": "a", "status": "passed"}, {"name": "b", "status": "failed", "message": "broke", "next": "fix b"},
                                                                         {"name": "c", "status": "skipped", "reason": "no agora"}]})
        text = ANSI.sub("", render.to_text(r, None, color=True))
        self.assertRegex(text, r"✅ a")
        self.assertRegex(text, r"❌ b\s+broke")
        self.assertIn("→ ws-host fix b", text)
        self.assertRegex(text, r"⏭️ c\s+no agora")
        self.assertIn("1 ok · 1 failed · 1 skipped", text)

    def test_a_long_name_does_not_push_its_text_out_of_line(self):
        r = Resource("repo-list", "x", {"plain": "Two.", "repositories": [{"id": "github.com/intellectual-frontiers/workspaces-host", "status": "ok", "plain": "up to date"},
                                                                            {"id": "a/b", "status": "ok", "plain": "up to date"}]})
        lines = ANSI.sub("", render.to_text(r, None, color=True)).splitlines()
        i = next(n for n, l in enumerate(lines) if "workspaces-host" in l)
        self.assertEqual(lines[i + 1].strip(), "up to date")

    def test_actions_show_the_command_on_its_own_line_in_cyan(self):
        os.environ["WS_HOST_COLOR"] = "always"
        _, out = self.run_cmd("kit", "list")
        self.assertIn("\x1b[1;36mws-host kit add", out)
        text = ANSI.sub("", out)
        i = text.splitlines().index("👉  What you can do next")
        self.assertTrue(text.splitlines()[i + 2].strip().startswith("ws-host"))

    def test_an_error_is_shown_with_a_cross(self):
        _, text = self.styled("kit", "show", "nope")
        self.assertTrue(text.splitlines()[0].startswith(("❌", "⚠️")))

    def test_progress_lines_stay_one_line(self):
        r = Resource("progress", "x", {"plain": "Doing it...", "step": "x"})
        self.assertEqual(render.to_text(r, None, color=True), "⏳ Doing it...")
