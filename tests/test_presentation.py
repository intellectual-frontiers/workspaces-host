"""How ws-host presents itself to an editor (0041-command-line FR-064, FR-072; 0001-ws-host FR-018)."""
import os
import re
import unittest
from pathlib import Path

from ws_host.core import env, presentation, registry as reg
from ws_host.core.registry import Arg, Command, Noun, Registry, View
from .helpers import Home

ROOT = Path(__file__).resolve().parent.parent


def cmd(words, args=(), surfaces=("cli", "editor"), category="read", title=None, icon=None):
    return Command(tuple(words.split()), category, "x", lambda ctx: None, tuple(args), tuple(surfaces), (), None, "m", title, icon)


def registry_with(*commands, views=(), nouns=()):
    r = Registry()
    for c in commands:
        r.commands[c.words] = c
    r.views = {v.id: v for v in views}
    r.nouns = {n.name: n for n in nouns}
    return r


class Declared(Home):
    def setUp(self):
        super().setUp()
        self.reg = reg.discover()

    def test_the_real_declarations_are_well_formed(self):
        self.assertEqual(presentation.problems(self.reg), [])

    def test_every_command_the_editor_offers_has_a_title_and_it_agrees_with_what_it_asks(self):
        for c in self.reg.commands.values():
            if "editor" in c.surfaces:
                self.assertTrue(c.title, c.id)
                self.assertEqual(c.title.endswith("…"), presentation.needs_value(c), c.id)
                self.assertLessEqual(len(c.title), 40, c.id)

    def test_command_list_carries_titles_icons_views_and_nouns(self):
        code, doc = self.run_json("command", "list")
        rows = {c["id"]: c for c in doc["data"]["commands"]}
        self.assertEqual(rows["kit add"]["title"], "Install Kit…")
        self.assertEqual(rows["doctor"]["icon"], "pulse")
        self.assertEqual(rows["doctor"]["noun"], None)
        self.assertEqual((rows["repo sync"]["noun"], rows["repo sync"]["verb"]), ("repo", "sync"))
        p = doc["data"]["presentation"]
        orders = [v["order"] for v in p["views"]]
        self.assertEqual(orders, sorted(orders))
        self.assertTrue(all(o > 10 for o in orders), "10 is the editor's own Home")
        self.assertEqual(len({v["id"] for v in p["views"]}), len(orders))
        nouns = {n["noun"]: n for n in p["nouns"]}
        self.assertEqual(nouns["repo"]["view"], "workspace")
        self.assertEqual(nouns["repo"]["list"]["command"], "repo list")
        self.assertTrue(all(n.get("view") in (None, *[v["id"] for v in p["views"]]) for n in nouns.values()))
        icons = presentation.codicons()
        self.assertTrue(all(n["icon"] in icons for n in nouns.values()) and all(v["icon"] in icons for v in p["views"]))

    def test_command_show_carries_the_title_and_icon(self):
        code, doc = self.run_json("command", "show", "repo", "set")
        self.assertEqual(doc["data"]["title"], "Set Repository Trust…")
        self.assertEqual(doc["data"]["icon"], "shield")

    def test_the_rows_of_each_list_have_the_fields_the_list_names_and_a_status_something_maps(self):
        self.paths.config_dir().mkdir(parents=True, exist_ok=True)
        self.paths.config_file().write_text('WS_HOST_REPOS="github.com/acme/site github.com/acme/lib"\n')
        for noun in self.reg.nouns.values():
            if not noun.list:
                continue
            lst = noun.list
            code, doc = self.run_json(*lst["command"].split())
            rows = doc["data"][lst["rows"]]
            self.assertTrue(rows, noun.name)
            for row in rows:
                for key in ("id", "label", "description", "status"):
                    self.assertIn(lst[key], row, f"{noun.name}: a row has no {lst[key]!r}")
                for field in lst.get("tooltip", []):
                    self.assertIn(field, row, f"{noun.name}: a row has no {field!r}")
                status = lst.get("status_map", {}).get(row[lst["status"]], row[lst["status"]])
                self.assertIn(status, presentation.STATUSES, f"{noun.name}: {row[lst['status']]!r} maps to nothing")

    def test_a_list_command_asks_for_nothing_and_is_a_read_command_the_editor_runs(self):
        for noun in self.reg.nouns.values():
            if noun.list:
                c = self.reg.get(tuple(noun.list["command"].split()))
                self.assertEqual((c.category, "editor" in c.surfaces, presentation.needs_value(c)), ("read", True, False), noun.name)

    def test_the_icon_list_is_the_public_roots_where_that_is_on_this_machine(self):
        for root in (os.environ.get("WS_HOST_PUBLIC_ROOT"), "/home/user/.github", str(Path.home() / "workspaces/github.com/intellectual-frontiers/.github")):
            f = Path(root or "/nonexistent") / "tools/agora/lib/codicons.txt"
            if f.is_file():
                theirs = [l for l in f.read_text(encoding="utf-8").splitlines() if l and not l.startswith("#")]
                ours = [l for l in presentation.CODICONS.read_text(encoding="utf-8").splitlines() if l and not l.startswith("#")]
                self.assertEqual(ours, theirs)
                return
        self.skipTest("the public root is not on this machine")

    def test_the_repository_declares_its_launcher_for_the_editor(self):
        values = env.parse((ROOT / ".if-console.env").read_text(encoding="utf-8"))
        self.assertEqual(values["IF_CONSOLE_LAUNCHER"], "./ws-host")
        self.assertTrue(os.access(ROOT / "ws-host", os.X_OK))


class Mistakes(unittest.TestCase):
    """The check fails on each thing 0041 FR-072 names."""

    def problems(self, *commands, views=(), nouns=()):
        return presentation.problems(registry_with(*commands, views=views, nouns=nouns))

    def test_a_title_that_is_lowercase_too_long_or_with_the_wrong_ellipsis(self):
        out = self.problems(cmd("a list", title="list things"), cmd("b list", title="List " + "x" * 40),
                            cmd("c show", args=(Arg("x", "STRING", positional=True, required=True),), title="Show Thing"),
                            cmd("d list", title="List Things…"))
        text = "\n".join(out)
        self.assertIn("a list: the title 'list things'", text)
        self.assertIn("b list: the title", text)
        self.assertIn("c show: the title 'Show Thing' needs an ellipsis", text)
        self.assertIn("d list: the title 'List Things…' ends with an ellipsis though nothing is asked for", text)

    def test_an_editor_command_without_a_title_but_not_a_terminal_only_one(self):
        out = self.problems(cmd("a list"), cmd("b list", surfaces=("cli",)))
        self.assertEqual([m for m in out if "has no palette title" in m], ["command a list: is offered to the editor and has no palette title (0041 FR-072)"])

    def test_an_icon_that_is_not_a_codicon(self):
        out = self.problems(cmd("a list", title="List Things", icon="not-an-icon"), views=(View("v", "V", "nope", 20),),
                            nouns=(Noun("a", "A", "bad-icon"),))
        self.assertEqual(sum("is not a codicon id" in m for m in out), 3)

    def test_a_view_nobody_declares_and_a_bad_view_id(self):
        out = self.problems(cmd("a list", title="List Things"), views=(View("Bad_ID", "V", "repo", 20),), nouns=(Noun("a", "A", "repo", "ghost"),))
        text = "\n".join(out)
        self.assertIn("view 'ghost' is declared by no one", text)
        self.assertIn("an id is lowercase words joined by hyphens", text)

    def test_a_list_that_asks_for_a_value_is_not_read_or_maps_to_a_status_outside_the_vocabulary(self):
        ask = cmd("a list", args=(Arg("x", "STRING", positional=True, required=True),), title="List Things…")
        write = cmd("a add", category="setup", title="Add Thing")
        lst = lambda c, **kw: {"command": c, "rows": "rows", "id": "id", "label": "id", **kw}
        out = self.problems(ask, write, nouns=(Noun("a", "A", "repo", None, lst("a list")),))
        self.assertTrue(any("asks for a value" in m for m in out))
        out = self.problems(write, nouns=(Noun("a", "A", "repo", None, lst("a add")),))
        self.assertTrue(any("is not a read command" in m for m in out))
        out = self.problems(cmd("a list", title="List Things"), nouns=(Noun("a", "A", "repo", None, lst("a list", status="s", status_map={"x": "great"})),))
        self.assertTrue(any("'great'" in m for m in out))
        out = self.problems(cmd("a list", title="List Things"), nouns=(Noun("a", "A", "repo", None, lst("a list", colour="red")),))
        self.assertTrue(any("'colour' is not a field of a list" in m for m in out))

    def test_a_noun_with_commands_and_no_presentation(self):
        out = self.problems(cmd("thing list", title="List Things"))
        self.assertTrue(any("noun thing: has commands and no icon or title" in m for m in out))

    def test_the_check_reports_these_through_check_registry(self):
        from ws_host.commands import check
        r = reg.discover()
        saved = r.commands[("kit", "list")].title
        r.commands[("kit", "list")].title = "list kits"
        try:
            found = check.registry_section(None)
        finally:
            r.commands[("kit", "list")].title = saved
        self.assertTrue(any("kit list: the title" in f["message"] for f in found))
