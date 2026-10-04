import tempfile
import unittest
from pathlib import Path

from ws_host.core import registry as reg
from ws_host.core.resource import Action, Resource, command_line


class Registry(unittest.TestCase):
    def test_commands_are_found_by_presence_and_have_no_conflicts(self):
        r = reg.discover()
        self.assertEqual(r.conflicts, [])
        for words in (("doctor",), ("check",), ("test",), ("context",), ("command", "list"), ("command", "show")):
            self.assertIn(words, r.commands)

    def test_every_command_has_one_category_and_a_known_verb(self):
        for c in reg.discover().commands.values():
            self.assertIn(c.category, reg.CATEGORIES, c.id)
            if c.noun:
                self.assertIn(c.verb, reg.VERBS, c.id)
            else:
                self.assertIn(c.words[0], reg.REPOWIDE, c.id)

    def test_decisions_are_never_on_mcp(self):
        for c in reg.discover().commands.values():
            if c.category == "decision":
                self.assertNotIn("mcp", c.surfaces, c.id)

    def test_setup_is_terminal_only_by_default(self):
        self.assertEqual(reg.DEFAULT_SURFACES["setup"], ("cli",))

    def test_a_duplicate_command_is_a_conflict(self):
        r = reg.Registry()
        c = reg.Command(("x", "list"), "read", "s", lambda ctx: None, module="m1")
        r.add(c)
        r.add(reg.Command(("x", "list"), "read", "s", lambda ctx: None, module="m2"))
        self.assertEqual(len(r.conflicts), 1)
        self.assertIn("m1", r.conflicts[0])

    def test_a_module_level_third_party_import_is_found_but_a_function_one_is_not(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "bad.py").write_text("import os\nimport requests\n")
            (Path(d) / "good.py").write_text("import os\nfrom . import x\ndef f():\n    import requests\n")
            (Path(d) / "tried.py").write_text("try:\n    import yaml\nexcept ImportError:\n    yaml = None\n")
            found = reg.module_level_imports([d])
        self.assertEqual(len(found), 2, found)
        self.assertTrue(any("bad.py" in f and "requests" in f for f in found))
        self.assertTrue(any("tried.py" in f for f in found))

    def test_the_real_modules_import_only_the_standard_library(self):
        self.assertEqual(reg.module_level_imports(), [])

    def test_the_core_uses_the_standard_library_only(self):
        import ast, sys
        std = set(sys.stdlib_module_names) | {"ws_host", "__future__"}
        core = Path(__file__).resolve().parents[1] / "ws_host" / "core"
        for f in core.glob("*.py"):
            for node in ast.walk(ast.parse(f.read_text())):
                names = [a.name.split(".")[0] for a in node.names] if isinstance(node, ast.Import) else \
                        [node.module.split(".")[0]] if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module else []
                for n in names:
                    self.assertIn(n, std, f"{f.name} imports {n}")


class ActionsPrintOneLine(unittest.TestCase):
    def test_a_command_line_is_generated_from_the_call(self):
        r = reg.discover()
        self.assertEqual(command_line(Action(("command", "show"), "x", {"words": ["repo", "list"]}), r), "ws-host command show repo list")
        self.assertEqual(command_line(Action(("doctor",), "x"), r), "ws-host doctor")

    def test_a_value_that_needs_quoting_or_is_missing_is_never_printed(self):
        r = reg.discover()
        self.assertIsNone(command_line(Action(("command", "show"), "x", {"words": ["a b's"]}), r))
        self.assertIsNone(command_line(Action(("command", "show"), "x", needs=("words",)), r))
