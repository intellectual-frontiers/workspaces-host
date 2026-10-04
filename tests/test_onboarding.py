"""0006-onboarding: the first-run experience: starter repositories, choosing repositories, colour, and the first-steps page."""
import json
import os
import re
import unittest

from ws_host.core import config, render
from ws_host.core.resource import Action, Resource
from .helpers import Home, Workspace

ANSI = re.compile(r"\x1b\[[0-9;]*m")


class Starter(Home):
    def test_until_the_person_says_otherwise_the_starter_repositories_are_the_two_public_ones(self):
        cfg = config.load()
        self.assertEqual(cfg.repos(), ["github.com/intellectual-frontiers/.github", "github.com/intellectual-frontiers/workspaces-host"])
        code, doc = self.run_json("repo", "list")
        self.assertEqual([r["id"] for r in doc["data"]["repositories"]], cfg.repos())
        self.assertEqual(doc["actions"][0]["cli"], "ws-host repo add --all")

    def test_an_explicit_list_replaces_the_starters_and_an_empty_one_means_none(self):
        self.paths.config_dir().mkdir(parents=True)
        self.paths.config_file().write_text('WS_HOST_REPOS="github.com/a/b"\n')
        self.assertEqual(config.load().repos(), ["github.com/a/b"])
        self.paths.config_file().write_text('WS_HOST_REPOS=""\n')
        self.assertEqual(config.load().repos(), [])

    def test_the_starter_repositories_are_cloned_into_the_layout_by_a_plain_update(self):
        class W(Workspace):
            pass
        w = W("run")
        w.setUp()
        self.addCleanup(w.doCleanups)
        w.remote("intellectual-frontiers", ".github")
        w.remote("intellectual-frontiers", "workspaces-host")
        code, doc = w.run_json("repo", "add", "--all")
        self.assertEqual(code, 0, doc)
        for n in (".github", "workspaces-host"):
            self.assertTrue((w.clone_path("intellectual-frontiers", n) / ".git").is_dir())


class Choosing(Workspace):
    def test_naming_a_new_repository_adds_it_to_your_own_list_and_copies_it(self):
        self.remote("acme", "site")
        self.config(WS_HOST_REPOS="")
        code, doc = self.run_json("repo", "add", self.rid("acme", "site"))
        self.assertEqual(code, 0, doc)
        self.assertEqual(doc["data"]["listed"], self.rid("acme", "site"))
        self.assertIn("I added", doc["data"]["plain"])
        self.assertTrue((self.clone_path("acme", "site") / ".git").is_dir())
        self.assertEqual(config.load().repos(), [self.rid("acme", "site")])
        again = self.run_json("repo", "add", self.rid("acme", "site"))[1]
        self.assertNotIn("listed", again["data"])

    def test_adding_keeps_every_other_line_of_the_file(self):
        self.remote("acme", "site")
        self.config(WS_HOST_GIT_NAME="Ada", WS_HOST_REPOS="github.com/x/y")
        self.paths.config_file().write_text('# mine\nWS_HOST_GIT_NAME="Ada"\nWS_HOST_REPOS="github.com/x/y"\nWS_HOST_KIT=""\n')
        self.run_cmd("repo", "add", self.rid("acme", "site"))
        text = self.paths.config_file().read_text()
        self.assertIn("# mine", text)
        self.assertIn('WS_HOST_GIT_NAME="Ada"', text)
        self.assertIn('WS_HOST_REPOS="github.com/x/y github.com/acme/site"', text)

    def test_the_starters_stay_when_you_add_your_first_of_your_own(self):
        self.remote("acme", "site")
        self.paths.config_dir().mkdir(parents=True)
        self.paths.config_file().write_text('WS_HOST_KIT=""\n')
        self.run_cmd("repo", "add", self.rid("acme", "site"), "--dry-run")
        self.assertNotIn("WS_HOST_REPOS", self.paths.config_file().read_text())
        config.add_repo(self.rid("acme", "site"))
        self.assertEqual(config.load().repos(), [*config.STARTER_REPOS, self.rid("acme", "site")])

    def test_dry_run_changes_neither_the_list_nor_the_disk(self):
        self.remote("acme", "site")
        self.config(WS_HOST_REPOS="")
        before = self.paths.config_file().read_text()
        code, doc = self.run_json("repo", "add", self.rid("acme", "site"), "--dry-run")
        self.assertEqual(doc["data"]["would_list"], self.rid("acme", "site"))
        self.assertEqual(self.paths.config_file().read_text(), before)
        self.assertFalse(self.clone_path("acme", "site").exists())


class Colour(Home):
    def resource(self):
        return Resource("demo", "d", {"plain": "Everything looks fine.", "items": [{"name": "a", "status": "ok"}, {"name": "b", "status": "warn"}, {"name": "c", "status": "fail"}]},
                        actions=[Action(("doctor",), "Check again")])

    def test_text_has_no_escape_codes_or_emoji_when_it_is_not_for_a_terminal(self):
        text = render.to_text(self.resource(), None, color=False)
        self.assertNotIn("\x1b", text)
        self.assertFalse(re.search(r"[\U0001F300-\U0001FAFF✅❌⚠]", text))
        self.assertEqual(text.splitlines()[0], "Everything looks fine.")

    def test_a_terminal_gets_bold_marks_and_a_coloured_command(self):
        text = render.to_text(self.resource(), None, color=True)
        self.assertIn("\x1b[1m", text)
        for mark in ("✅", "⚠️", "❌", "👉"):
            self.assertIn(mark, text)
        self.assertIn("\x1b[1;36mws-host doctor\x1b[0m", text)
        self.assertEqual(ANSI.sub("", text).splitlines()[0], "Everything looks fine.")

    def test_colour_follows_the_terminal_and_the_environment(self):
        class T:
            def isatty(self): return True
        class P:
            def isatty(self): return False
        self.assertTrue(render.use_color(T()))
        self.assertFalse(render.use_color(P()))
        os.environ["NO_COLOR"] = "1"
        self.assertFalse(render.use_color(T()))
        del os.environ["NO_COLOR"]
        os.environ["TERM"] = "dumb"
        self.assertFalse(render.use_color(T()))
        os.environ["WS_HOST_COLOR"] = "always"
        self.assertTrue(render.use_color(P()))
        os.environ["WS_HOST_COLOR"] = "never"
        self.assertFalse(render.use_color(T()))

    def test_json_and_html_never_carry_colour(self):
        os.environ["WS_HOST_COLOR"] = "always"
        _, out = self.run_cmd("doctor", "--json")
        self.assertNotIn("\x1b", out)
        _, html = self.run_cmd("doctor", "--html")
        self.assertNotIn("\x1b", html)
        _, text = self.run_cmd("doctor")
        self.assertIn("\x1b[", text)


class FirstSteps(Home):
    def test_the_start_page_walks_through_every_first_step_in_order(self):
        _, doc = self.run_json("help", "start")
        headings = [s["heading"] for s in doc["data"]["sections"]]
        order = ["Sign in to GitHub", "starter repositories", "Open VS Code", "set VS Code up", "Keep going in VS Code", "which repositories", "fish", "Stuck"]
        positions = [next(i for i, h in enumerate(headings) if o.lower() in h.lower()) for o in order]
        self.assertEqual(positions, sorted(positions))
        text = " ".join(s["text"] for s in doc["data"]["sections"])
        for needle in ("ws-host auth new github", "ws-host workspace advance", "code .", "ws-host vscode advance", "Workspace: Learn", "ws-host repo add github.com/ORG/REPO",
                       "WS_HOST_REPOS", "code ~/.config/workspaces-host/ws-host.env", "ws-host kit add shell", "fish", "ws-host doctor", "intellectual-frontiers.github.io/workspaces-host"):
            self.assertIn(needle, text, needle)
        self.assertIn(".github", text)
        self.assertIn("workspaces-host", text)

    def test_the_page_reads_well_with_and_without_colour(self):
        os.environ["WS_HOST_COLOR"] = "always"
        _, coloured = self.run_cmd("help", "start")
        os.environ["WS_HOST_COLOR"] = "never"
        _, plain = self.run_cmd("help", "start")
        self.assertEqual(ANSI.sub("", coloured).replace("👉 ", ""), plain)
        self.assertTrue(plain.splitlines()[0].startswith("🎉"))
        for n in range(1, 6):
            self.assertIn(f"{n}️⃣", plain)
        self.assertLess(max(len(l) for l in plain.splitlines() if not l.startswith("  ") or l.startswith("  ws")) , 140)
        self.assertTrue(all(len(l) <= 100 for l in plain.splitlines() if l.startswith("  ") and not l.strip().startswith(("ws-host", "cd ", "code", "fish"))))

    def test_the_installer_ends_by_showing_the_start_page(self):
        text = open(os.path.join(os.path.dirname(__file__), "..", "install.sh")).read()
        self.assertIn('ws-host" help start', text)
        self.assertGreaterEqual(text.count("help start"), 2)


class Progress(Home):
    def test_a_progress_step_is_one_line_in_text(self):
        from ws_host.core.resource import Resource
        r = Resource("progress", "copy", {"plain": "Copying repositories that are missing...", "step": "copy"})
        self.assertEqual(render.to_text(r), "Copying repositories that are missing...")
        self.assertEqual(render.to_text(r, None, color=True), "⏳ Copying repositories that are missing...")
        self.assertIn("step", json.loads(render.to_json(r))["data"])
