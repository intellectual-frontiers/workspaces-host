"""0004-editor-extension: the contract the extension relies on, tested from Python, and `vscode add`."""
import json
import os
import re
import shutil
import stat
import subprocess
import unittest
import zipfile
from pathlib import Path

from ws_host.commands import vscode as vs
from ws_host.core import registry as reg
from .helpers import REPO, Home, Workspace

WIRE_SURFACES = {"terminal", "editor", "mcp"}


class Package(unittest.TestCase):
    def setUp(self):
        self.pkg = json.loads((REPO / "vscode" / "package.json").read_text())

    def test_it_is_plain_javascript_with_no_build_and_no_dependencies(self):
        files = sorted(p.name for p in (REPO / "vscode").iterdir())
        self.assertEqual(files, ["extension.js", "logo.png", "package.json"])
        self.assertEqual(self.pkg["icon"], "logo.png")
        for key in ("dependencies", "devDependencies", "scripts"):
            self.assertNotIn(key, self.pkg)
        self.assertEqual(self.pkg["main"], "./extension.js")
        self.assertFalse((REPO / "vscode" / "node_modules").exists())

    def test_it_runs_where_the_workspace_is_and_refuses_untrusted_workspaces(self):
        self.assertEqual(self.pkg["extensionKind"], ["workspace"])
        self.assertIs(self.pkg["capabilities"]["untrustedWorkspaces"]["supported"], False)

    def test_it_names_no_orchestrator_but_its_own(self):
        text = (REPO / "vscode" / "extension.js").read_text()
        for name in ("ag" + "ora", "ei" + "d ", "eido" + "lon", "intellectualfrontiers"):
            self.assertNotIn(name, text)

    def test_it_writes_nothing_and_changes_no_setting(self):
        text = (REPO / "vscode" / "extension.js").read_text()
        for needle in ("writeFile", "appendFile", "mkdirSync", "unlink", "rmSync", "getConfiguration", ".update(", "git config"):
            self.assertNotIn(needle, text, needle)

    def test_every_contributed_command_is_the_documented_set_and_none_takes_arguments(self):
        cmds = sorted(c["command"] for c in self.pkg["contributes"]["commands"])
        self.assertEqual(cmds, ["wsHost.advance", "wsHost.getHelp", "wsHost.learn", "wsHost.refresh", "wsHost.runChecks", "wsHost.signIn"])


@unittest.skipUnless(shutil.which("node"), "node is needed to test the extension's logic")
class Logic(unittest.TestCase):
    def test_node_tests_pass(self):
        p = subprocess.run(["node", "--test", *map(str, sorted((REPO / "tests" / "node").glob("*.test.js")))], capture_output=True, text=True, timeout=300)
        self.assertEqual(p.returncode, 0, p.stdout[-3000:] + p.stderr[-1000:])


class Contract(Workspace):
    """What the extension reads from `ws-host`, checked on every command that runs without a value."""

    def docs(self):
        self.remote("acme", "site")
        self.config(WS_HOST_REPOS=self.rid("acme", "site"))
        argvs = [("command", "list"), ("command", "show", "repo", "list"), ("doctor",), ("context",), ("repo", "list"), ("repo", "status"),
                 ("kit", "list"), ("kit", "show", "press"), ("workspace", "status"), ("auth", "status"), ("check", "registry"), ("repo", "add", "--all", "--dry-run")]
        for argv in argvs:
            code, doc = self.run_json(*argv)
            yield argv, doc

    def test_every_resource_has_the_documented_fields_and_schema(self):
        for argv, doc in self.docs():
            self.assertEqual(set(doc), {"schema", "audience", "kind", "id", "data", "links", "actions"}, argv)
            self.assertRegex(doc["schema"], r"^ws-host/[\w-]+@\d+$")
            self.assertEqual(doc["schema"].split("/")[1].split("@")[0], doc["kind"])
            self.assertTrue(doc["data"]["plain"], argv)

    def test_command_list_and_show_have_the_wire_shape(self):
        _, lst = self.run_json("command", "list")
        self.assertEqual(lst["data"]["count"], len(lst["data"]["commands"]))
        for c in lst["data"]["commands"]:
            self.assertEqual(set(c), {"id", "category", "group", "surfaces", "help"})
            self.assertTrue(set(c["surfaces"]) <= WIRE_SURFACES)
            self.assertIn("terminal", c["surfaces"])
        for c in lst["data"]["commands"]:
            _, show = self.run_json("command", "show", *c["id"].split())
            d = show["data"]
            for key in ("id", "noun", "verb", "category", "help", "group", "arguments", "options", "usage", "surfaces", "programs"):
                self.assertIn(key, d, c["id"])
            for a in d["arguments"]:
                self.assertTrue({"name", "type", "help", "required", "words", "many"} <= set(a))
            for o in d["options"]:
                self.assertTrue({"flag", "type", "help", "multiple", "required"} <= set(o))
                self.assertTrue(o["flag"].startswith("--"))

    def test_actions_and_links_have_the_wire_shape_and_print_one_line_or_none(self):
        seen = 0
        for argv, doc in self.docs():
            for a in doc["actions"]:
                seen += 1
                self.assertTrue({"label", "command", "fields", "category", "surfaces", "cli", "enabled", "needs"} <= set(a), a)
                self.assertTrue(set(a["surfaces"]) <= WIRE_SURFACES)
                if a["cli"] is not None:
                    self.assertTrue(a["cli"].startswith("ws-host "))
                    self.assertNotIn("\n", a["cli"])
                    self.assertNotRegex(a["cli"], r"[\"'$`\\<>|;&()*? ]{2}|['\"]")     # no shell-specific quoting
            for l in doc["links"]:
                self.assertTrue({"rel", "command", "fields", "cli"} <= set(l))
        self.assertGreater(seen, 3)

    def test_decisions_are_flagged_and_never_on_mcp(self):
        _, lst = self.run_json("command", "list")
        self.assertIn("help", [c["id"] for c in lst["data"]["commands"]])
        decisions = [c for c in lst["data"]["commands"] if c["category"] == "decision"]
        self.assertEqual([c["id"] for c in decisions], ["repo set"])
        for c in decisions:
            self.assertEqual(c["surfaces"], ["terminal", "editor"])

    def test_the_html_carries_its_resource_and_a_strict_policy_and_one_button_per_action(self):
        self.remote("acme", "site")
        self.config(WS_HOST_REPOS=self.rid("acme", "site"))
        code, html = self.run_cmd("repo", "list", "--html")
        _, doc = self.run_json("repo", "list")
        self.assertIn("default-src 'none'", html)
        self.assertNotIn("<script", html.lower())
        self.assertNotRegex(html, r"https?://")
        m = re.search(r'<body data-resource="([^"]*)"', html)
        import html as h
        carried = json.loads(h.unescape(m.group(1)))
        self.assertEqual(carried, doc)
        self.assertEqual(len(re.findall(r'data-action="\d+"', html)), len(doc["actions"]))
        for a in doc["actions"]:
            self.assertIn(a["label"], html)

    def test_a_stream_in_html_is_one_page_per_resource(self):
        self.remote("acme", "site")
        self.config(WS_HOST_REPOS=self.rid("acme", "site"))
        code, out = self.run_cmd("workspace", "advance", "--html")
        pages = [p for p in re.split(r"(?=<!doctype html>)", out) if p.strip()]
        self.assertGreaterEqual(len(pages), 6)
        self.assertTrue(all("data-resource" in p for p in pages))

    def test_a_resource_with_a_schema_newer_than_the_extension_can_be_detected(self):
        from ws_host.core.resource import SCHEMA_VERSION
        node = json.loads(subprocess.run(["node", "-e", "console.log(JSON.stringify(require('./vscode/extension.js')._test.SUPPORTED_SCHEMA))"],
                                         cwd=REPO, capture_output=True, text=True).stdout) if shutil.which("node") else SCHEMA_VERSION
        self.assertGreaterEqual(node, SCHEMA_VERSION)

    def test_error_resources_are_resources_in_html_too(self):
        code, html = self.run_cmd("kit", "show", "nope", "--html")
        self.assertEqual(code, 2)
        self.assertIn("data-resource", html)


class Add(Home):
    def setUp(self):
        super().setUp()
        self.ext = self.home / ".vscode" / "extensions"
        self.pub = "intellectual-frontiers.workspaces-host"
        self.ver = json.loads((REPO / "vscode" / "package.json").read_text())["version"]
        self.folder = f"{self.pub}-{self.ver}"

    def index(self, entries):
        self.ext.mkdir(parents=True, exist_ok=True)
        (self.ext / "extensions.json").write_text(json.dumps(entries))

    def test_it_links_and_registers_keeping_other_entries_and_is_repeatable(self):
        other = {"identifier": {"id": "ms-python.python"}, "version": "1.0", "location": {"path": "/x", "scheme": "file"}, "relativeLocation": "ms-python.python-1.0"}
        self.index([other])
        code, doc = self.run_json("vscode", "add")
        self.assertEqual(code, 0, doc)
        link = self.ext / self.folder
        self.assertTrue(link.is_symlink())
        self.assertEqual(Path(os.readlink(link)).resolve(), (REPO / "vscode").resolve())
        entries = json.loads((self.ext / "extensions.json").read_text())
        self.assertEqual([e["identifier"]["id"] for e in entries], ["ms-python.python", self.pub])
        self.assertEqual(entries[0], other)
        self.assertEqual(entries[1]["relativeLocation"], self.folder)
        code, _ = self.run_json("vscode", "add")
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads((self.ext / "extensions.json").read_text())), 2)
        self.assertEqual([p.name for p in self.ext.iterdir() if p.name != "extensions.json"], [self.folder])

    def test_under_wsl_the_server_directory_is_used(self):
        from ws_host.core import machine
        orig = machine.distro
        machine.distro = lambda: {**orig(), "wsl": True}
        self.addCleanup(lambda: setattr(machine, "distro", orig))
        server = self.home / ".vscode-server" / "extensions"
        server.mkdir(parents=True)
        (server / "extensions.json").write_text("[]")
        code, doc = self.run_json("vscode", "add")
        self.assertEqual(code, 0)
        self.assertTrue((server / self.folder).is_symlink())
        self.assertFalse((self.home / ".vscode").exists())

    def test_without_an_index_it_builds_a_vsix_and_installs_it_with_code(self):
        bin_ = self.home.parent / "codebin"
        bin_.mkdir()
        (bin_ / "code").write_text(f'#!/bin/sh\necho "$@" > "{self.home}/code.args"\ncp "$2" "{self.home}/installed.vsix"\n')
        (bin_ / "code").chmod(0o755)
        os.environ["PATH"] = f"{bin_}:{os.environ['PATH']}"
        code, doc = self.run_json("vscode", "add")
        self.assertEqual(code, 0, doc)
        self.assertIn("--install-extension", (self.home / "code.args").read_text())
        self.assertFalse((self.ext / self.folder).exists())      # VS Code made its own copy; no link
        with zipfile.ZipFile(self.home / "installed.vsix") as z:
            names = set(z.namelist())
            self.assertTrue({"[Content_Types].xml", "extension.vsixmanifest", "extension/package.json", "extension/extension.js"} <= names)
            self.assertIn(self.ver, z.read("extension.vsixmanifest").decode())

    def test_without_an_index_or_code_it_links_and_says_what_remains(self):
        os.environ["PATH"] = os.pathsep.join(p for p in os.environ["PATH"].split(os.pathsep) if not shutil.which("code", path=p))
        code, doc = self.run_json("vscode", "add")
        self.assertEqual(code, 0)
        self.assertTrue((self.ext / self.folder).is_symlink())
        self.assertIn("not been run", doc["data"]["plain"])

    def test_dry_run_changes_nothing(self):
        self.index([])
        before = (self.ext / "extensions.json").read_text()
        code, doc = self.run_json("vscode", "add", "--dry-run")
        self.assertEqual(code, 0)
        self.assertFalse((self.ext / self.folder).exists())
        self.assertEqual((self.ext / "extensions.json").read_text(), before)

    def test_it_never_replaces_something_of_the_persons_that_is_in_the_way(self):
        self.index([])
        (self.ext / self.folder).mkdir()
        code, doc = self.run_json("vscode", "add")
        self.assertEqual((code, doc["data"]["code"]), (1, "in-the-way"))
        self.assertTrue((self.ext / self.folder).is_dir() and not (self.ext / self.folder).is_symlink())

    def test_it_changes_no_vscode_setting(self):
        self.index([])
        self.run_cmd("vscode", "add")
        self.assertFalse((self.home / ".config" / "Code").exists())
        self.assertFalse((self.home / ".vscode" / "settings.json").exists())

    def test_the_vsix_is_buildable_and_holds_the_extension(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            v = vs.build_vsix(Path(d))
            with zipfile.ZipFile(v) as z:
                self.assertIsNone(z.testzip())
                self.assertEqual(z.read("extension/package.json"), (REPO / "vscode" / "package.json").read_bytes())
