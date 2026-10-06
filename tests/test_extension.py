"""0004-editor-extension: the contract the Workspaces Console relies on, tested from Python, and `vscode ensure`."""
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import unittest
from pathlib import Path

from ws_host.commands import vscode as vs
from ws_host.core import registry as reg
from .helpers import GIT_ENV, REPO, Home, Workspace, git

WIRE_SURFACES = {"terminal", "editor", "mcp"}


class OneExtension(unittest.TestCase):
    def test_this_repository_ships_one_extension_in_console_and_no_other(self):
        self.assertTrue((REPO / "console" / "package.json").is_file())
        self.assertFalse((REPO / "vscode").exists())
        files = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True).stdout.split()
        manifests = [f for f in files if f.endswith("package.json") and not f.startswith("console/")]
        self.assertEqual(manifests, [])
        self.assertFalse([f for f in files if f.endswith(".vsix")])

    def test_there_is_no_command_that_installs_an_extension_of_its_own(self):
        self.assertIsNone(reg.discover().get(("vscode", "add")))
        self.assertIsNotNone(reg.discover().get(("vscode", "ensure")))


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
            self.assertTrue({"id", "category", "group", "surfaces", "help"} <= set(c) <= {"id", "noun", "verb", "category", "group", "surfaces", "help", "title", "icon"})   # a field may be added (0041 FR-064)
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
        self.assertEqual([c["id"] for c in decisions], ["provider add", "provider remove", "release publish", "repo set"])
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
        fakebin = self.home.parent / "gh"
        fakebin.mkdir()
        (fakebin / "gh").write_text("#!/bin/sh\nexit 0\n")
        (fakebin / "gh").chmod(0o755)
        os.environ["PATH"] = f"{fakebin}:{os.environ['PATH']}"
        code, out = self.run_cmd("workspace", "ensure", "--html")
        pages = [p for p in re.split(r"(?=<!doctype html>)", out) if p.strip()]
        self.assertGreaterEqual(len(pages), 6)
        self.assertTrue(all("data-resource" in p for p in pages))

    def test_error_resources_are_resources_in_html_too(self):
        code, html = self.run_cmd("kit", "show", "nope", "--html")
        self.assertEqual(code, 2)
        self.assertIn("data-resource", html)


class Setup(Home):
    """`vscode ensure` (0006-onboarding FR-007 to FR-009): extensions and settings, never overwriting a person's own."""

    def setUp(self):
        super().setUp()
        self.bin = self.home.parent / "bin"
        self.bin.mkdir()
        self.calls = self.home / "code.calls"
        (self.bin / "code").write_text(f'#!/bin/sh\necho "$@" >> "{self.calls}"\n[ "$1" = --list-extensions ] && printf "ms-python.python\\n"\nexit 0\n')
        (self.bin / "code").chmod(0o755)
        os.environ["PATH"] = f"{self.bin}:{os.environ['PATH']}"
        self.settings = self.home / ".config" / "Code" / "User" / "settings.json"

    def test_it_installs_the_missing_recommended_extensions_and_skips_what_is_there(self):
        code, doc = self.run_json("vscode", "ensure")
        self.assertEqual(code, 0, doc)
        installed = self.calls.read_text()
        for ext_id, _ in vs.RECOMMENDED:
            if ext_id != "ms-python.python":
                self.assertIn(f"--install-extension {ext_id} --force", installed)
        self.assertNotIn("--install-extension ms-python.python", installed)
        by = {s["name"]: s["status"] for s in doc["data"]["steps"]}
        self.assertEqual(by["ms-python.python"], "ok")

    def test_it_adds_settings_the_person_lacks_and_keeps_every_one_they_set(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(json.dumps({"files.autoSave": "off", "editor.fontSize": 18}))
        code, doc = self.run_json("vscode", "ensure")
        self.assertEqual(code, 0)
        merged = json.loads(self.settings.read_text())
        self.assertEqual(merged["files.autoSave"], "off")        # theirs wins
        self.assertEqual(merged["editor.fontSize"], 18)          # untouched
        self.assertIs(merged["git.autofetch"], True)             # added
        self.assertIn("files.autoSave", doc["data"]["settings"]["kept"])
        self.assertTrue(list((self.home / ".local/state/workspaces-host/backups").glob("settings.json.*")))

    def test_a_settings_file_with_comments_is_left_alone_and_the_values_are_listed(self):
        self.settings.parent.mkdir(parents=True)
        original = '{\n  // my notes\n  "editor.fontSize": 18,\n}\n'
        self.settings.write_text(original)
        code, doc = self.run_json("vscode", "ensure")
        self.assertEqual(self.settings.read_text(), original)
        self.assertEqual(doc["data"]["settings"]["status"], "left-alone")
        self.assertIn("git.autofetch", doc["data"]["settings"]["plain"])

    def test_it_is_repeatable_and_dry_run_changes_nothing(self):
        code, doc = self.run_json("vscode", "ensure", "--dry-run")
        self.assertEqual(code, 0)
        self.assertFalse(self.settings.exists())
        self.assertNotIn("--install-extension", self.calls.read_text() if self.calls.exists() else "")
        self.run_cmd("vscode", "ensure")
        first = self.settings.read_text()
        code, doc = self.run_json("vscode", "ensure")
        self.assertEqual(self.settings.read_text(), first)
        self.assertEqual(doc["data"]["settings"]["status"], "unchanged")

    def test_under_wsl_the_machine_settings_file_is_used(self):
        from ws_host.core import machine
        orig = machine.distro
        machine.distro = lambda: {**orig(), "wsl": True}
        self.addCleanup(lambda: setattr(machine, "distro", orig))
        self.run_cmd("vscode", "ensure")
        self.assertTrue((self.home / ".vscode-server" / "data" / "Machine" / "settings.json").exists())
        self.assertFalse(self.settings.exists())

    def test_without_code_it_says_what_to_do_and_still_sets_the_settings_it_can(self):
        (self.bin / "code").unlink()
        os.environ["PATH"] = os.pathsep.join(p for p in os.environ["PATH"].split(os.pathsep) if not shutil.which("code", path=p))
        code, doc = self.run_json("vscode", "ensure")
        self.assertIn("code .", json.dumps(doc["data"]))
        self.assertTrue(self.settings.exists())

    def test_the_baseline_chooses_fish_only_when_it_is_installed(self):
        self.assertIn(vs.baseline_settings()["terminal.integrated.defaultProfile.linux"], ("fish", "bash"))
        self.assertTrue(all(isinstance(v, (str, bool)) for v in vs.baseline_settings().values()))

    def test_setup_is_a_setup_command_on_the_terminal_and_the_editor_never_mcp(self):
        c = reg.discover().get(("vscode", "ensure"))
        self.assertEqual((c.category, c.surfaces), ("setup", ("cli", "editor")))


class Console(Home):
    """The Workspaces Console is installed from this repository's latest release, after its checksum is checked, with `code` (0004-editor-extension, 0007-releases)."""

    def setUp(self):
        super().setUp()
        self.bin = self.home.parent / "bin"
        self.bin.mkdir()
        self.calls = self.home / "code.calls"
        self.installed = self.home / "code.installed"
        self.installed.write_text("ms-python.python\n")
        (self.bin / "code").write_text(
            f'#!/bin/sh\necho "$@" >> "{self.calls}"\n'
            f'[ "$1" = --list-extensions ] && cat "{self.installed}"\n'
            f'[ "$1" = --install-extension ] && echo "$2" | sed -n "s/.*workspaces-console.*/intellectual-frontiers.workspaces-console/p" >> "{self.installed}"\n'
            'exit 0\n')
        (self.bin / "code").chmod(0o755)
        os.environ["PATH"] = f"{self.bin}:{os.environ['PATH']}"
        self.paths.config_dir().mkdir(parents=True, exist_ok=True)
        self.paths.config_file().write_text('WS_HOST_KIT=""\nWS_HOST_REPOS=""\nWS_HOST_PROMPT="no"\n')
        self.root = self.home / "workspaces/github.com/intellectual-frontiers/.github"
        self.root.mkdir(parents=True)
        git(self.root, "init", "-b", "main")
        (self.root / "README.md").write_text("x\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", "first")
        self.settings = self.home / ".config" / "Code" / "User" / "settings.json"
        self.release = None                # what this repository's latest release says; None is "no release"
        self.downloads = []
        saved_get, saved_download = vs._get_json, vs.fetch.download

        def get(url):
            if self.release is None:
                raise OSError("404")
            return self.release

        def download(url, sha, offline=False):
            self.downloads.append((url, sha))
            if getattr(self, "bad_download", False):
                raise vs.fetch.FetchError("checksum", "the file is not the one expected")
            f = self.home.parent / "downloaded"
            f.write_bytes(b"vsix")
            return f

        vs._get_json, vs.fetch.download = get, download
        self.addCleanup(lambda: (setattr(vs, "_get_json", saved_get), setattr(vs.fetch, "download", saved_download)))

    def a_release(self, **kw):
        asset = {"name": "workspaces-console-0.2.0.vsix", "digest": "sha256:" + "ab" * 32,
                 "browser_download_url": "https://github.com/x/releases/download/v0.2.0/workspaces-console-0.2.0.vsix"}
        asset.update(kw)
        self.release = {"tag_name": "v0.2.0", "assets": [asset]}

    def step(self, doc):
        return [s for s in doc["data"]["steps"] if s["name"] == "Workspaces Console extension"][0]

    def test_the_release_comes_from_this_repository(self):
        self.assertIn("intellectual-frontiers/workspaces-host/releases/latest", vs.RELEASE_API)
        self.assertEqual(vs.CONSOLE_ID, "intellectual-frontiers.workspaces-console")

    def test_a_release_with_a_digest_is_downloaded_checked_and_installed(self):
        self.a_release()
        code, doc = self.run_json("vscode", "ensure")
        self.assertEqual(code, 0, doc)
        self.assertEqual(self.downloads, [("https://github.com/x/releases/download/v0.2.0/workspaces-console-0.2.0.vsix", "ab" * 32)])
        self.assertRegex(self.calls.read_text(), r"--install-extension \S+workspaces-console-0\.2\.0\.vsix --force")
        self.assertEqual(self.step(doc)["status"], "ok")
        self.assertIn("after checking its fingerprint", self.step(doc)["plain"])
        self.assertIn("Workspaces Console: Learn a Topic", doc["data"]["next"])
        self.assertIn("workspaces.code-workspace", doc["data"]["next"])
        self.assertEqual(vs.read_stamp()["release"], "v0.2.0")

    def test_the_same_release_is_not_downloaded_or_installed_twice(self):
        self.a_release()
        self.run_json("vscode", "ensure")
        before = self.calls.read_text().count("workspaces-console")
        code, doc = self.run_json("vscode", "ensure")
        self.assertEqual(len(self.downloads), 1)
        self.assertEqual(self.step(doc)["plain"], "The Workspaces Console is installed and current.")
        self.assertEqual(self.calls.read_text().count("workspaces-console"), before)

    def test_no_release_is_said_plainly_and_nothing_is_built_or_installed(self):
        code, doc = self.run_json("vscode", "ensure")
        self.assertEqual(self.step(doc)["status"], "warn")
        self.assertIn("I did not install it", self.step(doc)["plain"])
        self.assertEqual(doc["actions"][0]["cli"], "ws-host vscode ensure")
        self.assertNotIn("workspaces-console", self.calls.read_text() if self.calls.exists() else "")

    def test_a_release_with_no_digest_or_a_wrong_name_or_address_is_ignored(self):
        for kw in ({"digest": None}, {"digest": "sha256:short"}, {"name": "other.vsix"}, {"browser_download_url": "http://insecure/x.vsix"}):
            self.a_release(**kw)
            code, doc = self.run_json("vscode", "ensure")
            self.assertEqual(self.downloads, [], kw)
            self.assertEqual(self.step(doc)["status"], "warn", kw)

    def test_a_download_that_does_not_match_its_digest_installs_nothing(self):
        self.a_release()
        self.bad_download = True
        code, doc = self.run_json("vscode", "ensure")
        self.assertEqual(self.step(doc)["status"], "fail")
        self.assertIn("did not pass its check", self.step(doc)["plain"])
        self.assertNotIn("workspaces-console", self.calls.read_text() if self.calls.exists() else "")

    def test_offline_never_asks_for_a_release(self):
        self.a_release()
        os.environ["WS_HOST_OFFLINE"] = "1"
        code, doc = self.run_json("vscode", "ensure")
        self.assertEqual(self.downloads, [])

    def test_a_dry_run_downloads_and_installs_nothing(self):
        self.a_release()
        code, doc = self.run_json("vscode", "ensure", "--dry-run")
        self.assertEqual(self.downloads, [])
        self.assertIn("I would download and install the Workspaces Console v0.2.0", self.step(doc)["plain"])
        self.assertNotIn("--install-extension", self.calls.read_text() if self.calls.exists() else "")

    def test_the_workspace_file_lists_the_cloned_repositories_and_keeps_the_persons_own(self):
        self.paths.config_file().write_text(f'WS_HOST_KIT=""\nWS_HOST_REPOS="github.com/intellectual-frontiers/.github github.com/acme/none"\nWS_HOST_PROMPT="no"\n')
        f = self.home / "workspaces" / "workspaces.code-workspace"
        self.run_json("vscode", "ensure")
        data = json.loads(f.read_text())
        self.assertEqual(data["folders"], [{"path": "github.com/intellectual-frontiers/.github", "name": ".github"}])
        for folder in data["folders"]:
            self.assertFalse(os.path.isabs(folder["path"]))
            self.assertNotIn("..", Path(folder["path"]).parts)
            self.assertTrue((f.parent / folder["path"] / ".git").exists())
        data["folders"].append({"path": "../mine", "name": "mine"})
        self.assertEqual(data["settings"]["window.title"], vs.WORKSPACE_SETTINGS["window.title"])
        self.assertEqual(data["extensions"]["recommendations"], [vs.CONSOLE_ID])
        data["settings"] = {"editor.fontSize": 18, "window.title": "mine"}
        f.write_text(json.dumps(data))
        self.run_json("vscode", "ensure")
        again = json.loads(f.read_text())
        self.assertEqual(again["settings"]["window.title"], "mine")
        self.assertEqual(again["settings"]["editor.fontSize"], 18)
        self.assertIn({"path": "../mine", "name": "mine"}, again["folders"])
        self.assertEqual(again["extensions"]["recommendations"], [vs.CONSOLE_ID])
        f.write_text("{ // comments\n}")
        self.run_json("vscode", "ensure")
        self.assertEqual(f.read_text(), "{ // comments\n}")

    def test_workspace_ensure_says_what_to_do_until_the_console_is_installed(self):
        (self.home.parent / "fakebin").mkdir()
        gh = self.home.parent / "fakebin" / "gh"
        gh.write_text("#!/bin/sh\nexit 0\n")
        gh.chmod(0o755)
        os.environ["PATH"] = f"{self.home.parent / 'fakebin'}:{os.environ['PATH']}"
        code, doc = self.run_json("workspace", "ensure")
        editor = [s for s in doc["data"]["steps"] if s["name"] == "editor"][0]
        self.assertEqual(editor["status"], "warn")
        self.assertIn("ws-host vscode ensure", editor["plain"])
        self.a_release()
        self.run_json("vscode", "ensure")
        code, doc = self.run_json("workspace", "ensure")
        editor = [s for s in doc["data"]["steps"] if s["name"] == "editor"][0]
        self.assertEqual(editor["status"], "ok")

    def test_release_package_never_raises(self):
        vs._get_json = lambda url: {"assets": "not a list"}
        self.assertIsNone(vs.release_package())
        vs._get_json = lambda url: (_ for _ in ()).throw(ValueError("bad json"))
        self.assertIsNone(vs.release_package())


class ConsoleSection(Home):
    """`ws-host check console` runs the real-VS-Code suite with the Console's own runner (0004-editor-extension FR-027)."""

    def test_the_suite_is_here_and_the_section_runs_only_when_named(self):
        self.assertTrue((REPO / "tests/if_console/vscode/index.js").is_file())
        self.assertTrue((REPO / "tests/if_console/vscode/suite.js").is_file())
        self.assertTrue((REPO / "console/test/vscode/run.js").is_file())
        r = reg.discover()
        self.assertIn("slow", r.sections["console"].suites)
        code, doc = self.run_json("check")
        self.assertNotIn("console", [s["name"] for s in doc["data"]["sections"]])

    def test_without_vs_code_it_is_skipped_naming_the_cause(self):
        os.environ["WS_HOST_VSCODE_DIR"] = str(self.home / "nowhere")
        code, doc = self.run_json("check", "console")
        row = doc["data"]["sections"][0]
        self.assertEqual(row["status"], "skipped")
        self.assertIn("VS Code", row["reason"])

    def test_the_section_needs_no_other_repository(self):
        src = (REPO / "ws_host/commands/check.py").read_text()
        body = src[src.index("def console_section"):src.index("@reg.command(\"check\"")]
        self.assertNotIn("agora", body)
        self.assertNotIn("_public_root", body)


class WorkspaceFileTeaching(unittest.TestCase):
    """The one way to open several repositories is taught in the help and in the guide (0004-editor-extension FR-028)."""

    def test_the_help_page_and_the_chapter_teach_the_rule(self):
        r = reg.discover()
        t = r.topics["workspace-file"]
        text = json.dumps([t.plain, t.sections, [st.label if hasattr(st, "label") else str(st) for st in t.steps]])
        for needle in ("workspaces.code-workspace", "Open Workspace from File", "code ~/workspaces/workspaces.code-workspace", "Make your own", "gitlab.code-workspace", "ws-host repo add", "ws-host vscode ensure"):
            self.assertIn(needle, text)
        chapter = (REPO / "docs-src/chapters/start/workspace-file.adoc").read_text()
        for needle in ("Make your own", "github.code-workspace", "organization", "Open Recent", "Explorer", "ws-host vscode ensure", "https://code.visualstudio.com/"):
            self.assertIn(needle, chapter)
        self.assertIn("workspace-file.adoc", (REPO / "docs-src/manuscript.adoc").read_text())



class OtherWorkspaceFiles(Console):
    def test_a_persons_own_workspace_file_is_never_touched(self):
        self.paths.config_file().write_text('WS_HOST_KIT=""\nWS_HOST_REPOS="github.com/intellectual-frontiers/.github"\nWS_HOST_PROMPT="no"\n')
        mine = self.home / "workspaces" / "gitlab.code-workspace"
        mine.write_text('{ // mine\n"folders": []}')
        self.run_json("vscode", "ensure")
        self.assertEqual(mine.read_text(), '{ // mine\n"folders": []}')
