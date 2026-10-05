"""0005-help-and-docs: help, the generated reference, the guide's build, the agent skill, fresh."""
import hashlib
import json
import os
import re
import shutil
import stat
from pathlib import Path

from ws_host.commands import docs
from ws_host.core import registry as reg
from .helpers import REPO, Home

FAKE_ASCIIDOCTOR = r"""#!/bin/sh
# a stand-in for asciidoctor: one section per chapter file, with a link to another section when the file has one
out=""; file=""
while [ $# -gt 0 ]; do case "$1" in -o) out=$2; shift;; -*) ;; *) file=$1;; esac; shift; done
id=$(sed -n 's/^\[#\([^]]*\)\]$/\1/p' "$file" | head -1)
title=$(sed -n 's/^== \(.*\)$/\1/p' "$file" | head -1)
ref=$(sed -n 's/.*<<\([a-z-]*\)>>.*/\1/p' "$file" | head -1)
page="<div class=\"sect1\"><h2 id=\"${id:-none}\">${title:-Untitled}</h2><p>text"
[ -n "$ref" ] && page="$page <a href=\"#$ref\">[$ref]</a>"
page="$page</p></div>"
if [ "$out" = "-" ]; then echo "$page"; elif [ -n "$out" ]; then echo "<html>$page</html>" > "$out"; fi
exit 0
"""

TOPICS = {"start", "repos", "signin", "trust", "kits", "editor", "shell", "recover", "ai", "extend"}


class Help(Home):
    def test_help_lists_the_topics_the_spec_requires(self):
        code, doc = self.run_json("help")
        self.assertEqual(code, 0)
        self.assertTrue(TOPICS <= {t["name"] for t in doc["data"]["topics"]})
        self.assertEqual(doc["data"]["count"], len(doc["data"]["topics"]))

    def test_a_topic_is_a_resource_with_plain_first_line_sections_and_steps_as_actions(self):
        for name in sorted(TOPICS):
            code, doc = self.run_json("help", name)
            self.assertEqual(code, 0, name)
            self.assertEqual(doc["kind"], "help")
            self.assertTrue(doc["data"]["plain"].endswith("."), name)
            self.assertTrue(doc["data"]["sections"], name)
            self.assertTrue(doc["actions"], name)
            for a in doc["actions"]:
                self.assertIn(a["command"].split()[0], {c.words[0] for c in reg.discover().commands.values()})
                self.assertTrue(a["cli"] is None or a["cli"].startswith("ws-host "))
            _, text = self.run_cmd("help", name)
            self.assertEqual(text.splitlines()[0], doc["data"]["plain"])
            self.assertNotRegex(text.splitlines()[0], r"\b(json|stderr|uv\.lock|fast-forward|symlink)\b")

    def test_an_unknown_topic_lists_the_real_ones(self):
        code, doc = self.run_json("help", "nonesuch")
        self.assertEqual((code, doc["data"]["code"]), (2, "usage"))
        self.assertIn("repos", doc["data"]["message"])

    def test_topics_work_offline_with_nothing_installed(self):
        os.environ["WS_HOST_OFFLINE"] = "1"
        code, _ = self.run_cmd("help", "start", "--offline")
        self.assertEqual(code, 0)

    def test_the_check_section_passes_and_fails_for_a_topic_naming_a_command_that_is_gone(self):
        self.assertEqual(self.run_json("check", "help")[0], 0)
        r = reg.discover()
        from ws_host.core.registry import Step
        t = r.topics["start"]
        saved = t.steps
        t.steps = saved + (Step("Bad", ("nonesuch", "verb")), Step("Worse", ("repo", "list"), {"bogus": 1}))
        try:
            code, doc = self.run_json("check", "help")
        finally:
            t.steps = saved
        self.assertEqual(code, 1)
        msgs = " ".join(f["message"] for f in doc["data"]["sections"][0]["findings"])
        self.assertIn("does not exist", msgs)
        self.assertIn("bogus", msgs)

    def test_topics_mention_nothing_this_ws_host_does_not_have(self):
        for t in reg.discover().topics.values():
            text = t.plain + " ".join(h + x for h, x in t.sections)
            for word in ("persona", "devcontainer", "Codespaces", "Nix", "YAML"):
                self.assertNotIn(word, text, t.name)

    def test_the_shell_topic_says_bash_and_oh_my_posh_are_supported_and_fish_4_is_best(self):
        text = " ".join(h + " " + x for h, x in reg.discover().topics["shell"].sections) + reg.discover().topics["shell"].plain
        for needle in ("bash", "oh-my-posh", "fish 4", "chsh", "never changes your login shell"):
            self.assertIn(needle, text)

    def test_the_extend_topic_describes_only_the_python_registry_way(self):
        t = reg.discover().topics["extend"]
        text = " ".join(x for _, x in t.sections)
        for needle in ("Python", "ws_host/commands", "ws_host/kits", "pyproject.toml", "uv.lock", "standard library", "doctor", "fresh"):
            self.assertIn(needle, text)
        for forbidden in ("YAML", "requirements.txt", "pip install", "Nix"):
            self.assertNotIn(forbidden, text)


class Generated(Home):
    def test_the_committed_reference_and_skill_are_current(self):
        code, doc = self.run_json("fresh")
        self.assertEqual(code, 0, doc["data"])
        self.assertEqual({g["name"] for g in doc["data"]["generators"]}, {"agent-skill", "reference-docs"})

    def test_every_generated_file_carries_a_header_naming_its_generator_and_command(self):
        for rel, text in reg.discover().generators["reference-docs"].render().items():
            self.assertIn("Generated by ws-host: reference-docs", text.splitlines()[0], rel)
            self.assertIn("ws-host docs generate", text.splitlines()[0])
        skill = reg.discover().generators["agent-skill"].render()[".claude/skills/ws-host/SKILL.md"]
        self.assertTrue(skill.startswith("---\nname: ws-host\n"))
        self.assertIn("ws-host skill generate", skill)

    def test_a_hand_edit_makes_fresh_fail_naming_the_generator_and_the_command(self):
        f = REPO / "docs-src" / "chapters" / "reference" / "commands.adoc"
        original = f.read_text()
        try:
            f.write_text(original + "\nedited by hand\n")
            code, doc = self.run_json("fresh")
            self.assertEqual(code, 1)
            self.assertEqual(doc["actions"][0]["cli"], "ws-host docs generate")
            self.assertIn("reference-docs", json.dumps(doc["data"]))
            code, doc = self.run_json("check", "fresh")
            self.assertEqual(code, 1)
            self.assertIn("docs generate", doc["data"]["sections"][0]["findings"][0]["message"])
        finally:
            f.write_text(original)
        self.assertEqual(self.run_json("fresh")[0], 0)

    def test_a_missing_generated_file_is_stale(self):
        f = REPO / "docs-src" / "chapters" / "reference" / "kits.adoc"
        original = f.read_text()
        f.unlink()
        try:
            self.assertEqual(self.run_json("fresh")[0], 1)
        finally:
            f.write_text(original)

    def test_generate_dry_run_writes_nothing_and_a_real_run_is_idempotent(self):
        code, doc = self.run_json("docs", "generate", "--dry-run")
        self.assertEqual(code, 0)
        self.assertTrue(all(f["status"] == "unchanged" for f in doc["data"]["files"]))
        code, doc = self.run_json("docs", "generate")
        self.assertTrue(all(f["status"] == "unchanged" for f in doc["data"]["files"]))
        code, doc = self.run_json("skill", "generate")
        self.assertEqual(code, 0)

    def test_the_reference_lists_every_command_kit_topic_and_config_key(self):
        out = reg.discover().generators["reference-docs"].render()
        commands = out["docs-src/chapters/reference/commands.adoc"]
        for c in reg.discover().commands.values():
            self.assertIn(c.summary, commands)
        for k in reg.discover().kits:
            self.assertIn(f"=== {k}", out["docs-src/chapters/reference/kits.adoc"])
        for t in reg.discover().topics:
            self.assertIn(f"=== {t}", out["docs-src/chapters/reference/help-topics.adoc"])
        from ws_host.core import config
        for k in list(config.KEYS) + list(config.REPO_KEYS):
            self.assertIn(k, out["docs-src/chapters/reference/files.adoc"])

    def test_the_skill_says_decisions_are_for_a_person_and_lists_every_command(self):
        skill = reg.discover().generators["agent-skill"].render()[".claude/skills/ws-host/SKILL.md"]
        self.assertIn("`decision` category is for a person", skill)
        for c in reg.discover().commands.values():
            self.assertIn(f"`{c.id}`", skill)

    def test_a_change_to_a_topic_changes_the_reference(self):
        t = reg.discover().topics["start"]
        before = reg.discover().generators["reference-docs"].render()["docs-src/chapters/reference/help-topics.adoc"]
        saved = t.plain
        t.plain = "A different plain line."
        try:
            after = reg.discover().generators["reference-docs"].render()["docs-src/chapters/reference/help-topics.adoc"]
            self.assertNotEqual(before, after)
            self.assertEqual(self.run_json("fresh")[0], 1)
        finally:
            t.plain = saved


class Guide(Home):
    def test_the_graphics_are_here_and_the_licence_is_this_repositorys_own(self):
        expected = {"logo.png": "32375", "mascot.jpg": "183738", "mascot-workflows.jpg": "145214", "social-preview.jpg": "204239"}
        for name, size in expected.items():
            self.assertEqual(str((REPO / "docs" / name).stat().st_size), size, name)
        self.assertIn("MIT License", (REPO / "LICENSE").read_text())

    def test_the_theme_files_are_here_and_the_book_uses_the_mascot(self):
        for f in ("html.css", "epub.css", "if-press-pdf-theme.yml"):
            self.assertTrue((REPO / "docs-src" / "theme" / f).is_file(), f)
        text = (REPO / "docs-src" / "chapters" / "front-matter" / "preface.adoc").read_text()
        self.assertIn("image::mascot.jpg", text)
        self.assertIn("image::mascot-workflows.jpg", text)
        self.assertIn("mascot.jpg", (REPO / "docs" / "index.html").read_text())

    def test_the_manuscript_includes_every_chapter_and_every_include_exists(self):
        ms = (REPO / "docs-src" / "manuscript.adoc").read_text()
        for inc in re.findall(r"include::([^\[]+)\[\]", ms):
            self.assertTrue((REPO / "docs-src" / inc).is_file(), inc)
        for f in (REPO / "docs-src" / "chapters").rglob("*.adoc"):
            self.assertIn(str(f.relative_to(REPO / "docs-src")), ms, f"{f} is not in the manuscript")

    def test_the_book_does_not_repeat_what_help_says_and_links_to_it(self):
        day = (REPO / "docs-src" / "chapters" / "overview" / "day-to-day.adoc").read_text()
        self.assertIn("ws-host help", day)
        self.assertIn("reference-help", day)
        for t in reg.discover().topics.values():
            for _h, text in t.sections:
                for para in text.split("\n"):
                    if len(para) > 120:
                        for f in (REPO / "docs-src" / "chapters" / "overview").glob("*.adoc"):
                            self.assertNotIn(para.strip(), f.read_text(), f"{f.name} repeats a help topic's paragraph")

    def test_the_shell_chapter_states_the_shell_policy_and_the_extend_chapter_the_python_strategy(self):
        shells = (REPO / "docs-src" / "chapters" / "overview" / "shells.adoc").read_text()
        for needle in ("`bash` and `oh-my-posh` are fully supported", "`fish` 4 is the best experience", "shell` kit", "never takes it for you"):
            self.assertIn(needle, shells)
        ext = (REPO / "docs-src" / "chapters" / "overview" / "extend-with-ai.adoc").read_text()
        for needle in ("AI", "Python module", "pyproject.toml", "uv.lock", "inside\nthe function that uses it", "dependency group"):
            self.assertIn(needle, ext)

    def test_the_book_is_in_the_documented_voice(self):
        banned = ("It is important to note", "It is worth mentioning", "In conclusion", "Let us begin", "At its core", "Before diving in")
        for f in (REPO / "docs-src").rglob("*.adoc"):
            for b in banned:
                self.assertNotIn(b, f.read_text(), f.name)

    def test_build_without_converters_says_which_are_missing_and_builds_nothing_it_cannot(self):
        bin_ = self.home.parent / "bin"
        bin_.mkdir()
        (bin_ / "asciidoctor").write_text(FAKE_ASCIIDOCTOR)
        (bin_ / "asciidoctor").chmod(0o755)
        keep = self.home.parent / "keep"
        keep.mkdir()
        for t in ("sh", "cat", "env"):
            shutil.copy(shutil.which(t), keep / t) if False else (keep / t).symlink_to(shutil.which(t))
        os.environ["PATH"] = f"{bin_}:{keep}"
        out = self.home / "site"
        code, doc = self.run_json("docs", "build", "--output", str(out))
        by = {e["name"]: e for e in doc["data"]["editions"]}
        self.assertEqual(by["single-page HTML"]["status"], "built")
        self.assertEqual(by["multi-page HTML"]["status"], "built")
        for name in ("PDF", "EPUB"):
            self.assertEqual(by[name]["status"], "skipped", name)
            self.assertIn("not on this machine", by[name]["reason"])
        self.assertTrue((out / "book" / "single-page.html").is_file())
        self.assertTrue((out / "mascot.jpg").is_file() and (out / "index.html").is_file())
        self.assertEqual(code, 0)
        self.assertIn("Left out because a converter is missing", doc["data"]["plain"])
        self.assertEqual(doc["actions"][0]["cli"], "ws-host kit add press")
        self.assertFalse((REPO / "docs-src" / "theme" / "logo.png").exists())   # the repository is not touched

    def test_build_with_no_asciidoctor_names_the_press_kit(self):
        os.environ["PATH"] = str(self.home)
        code, doc = self.run_json("docs", "build")
        self.assertEqual((code, doc["data"]["code"]), (3, "missing-program"))
        self.assertEqual(doc["actions"][0]["cli"], "ws-host kit add press")

    def test_build_dry_run_changes_nothing(self):
        code, doc = self.run_json("docs", "build", "--output", str(self.home / "x"), "--dry-run")
        self.assertEqual(code, 0)
        self.assertFalse((self.home / "x").exists())


class Site(Home):
    """0006-onboarding FR-010 to FR-015: the site, its content, and the README."""

    def build(self, out):
        bin_ = self.home.parent / "bin"
        bin_.mkdir(exist_ok=True)
        (bin_ / "asciidoctor").write_text(FAKE_ASCIIDOCTOR)
        (bin_ / "asciidoctor").chmod(0o755)
        keep = self.home.parent / "keep"
        keep.mkdir(exist_ok=True)
        for t in ("sh", "cat", "env", "sed", "head"):
            if not (keep / t).exists():
                (keep / t).symlink_to(shutil.which(t))
        os.environ["PATH"] = f"{bin_}:{keep}"
        return self.run_json("docs", "build", "--output", str(out))

    def test_every_chapter_is_a_page_with_the_navigation_and_a_pager(self):
        out = self.home / "site"
        code, doc = self.build(out)
        self.assertEqual(code, 0, doc)
        slugs = [p.stem for p in (REPO / "docs-src" / "chapters").rglob("*.adoc")]
        for slug in slugs:
            page = (out / "book" / f"{slug}.html").read_text()
            self.assertIn('<nav class="site-nav">', page, slug)
            self.assertIn('class="current"', page, slug)
            self.assertIn("../index.html", page)
            self.assertIn('rel="stylesheet" href="site.css"', page)
            for other in ("windows-wsl", "troubleshooting", "commands"):
                self.assertIn(f'href="{other}.html"', page, f"{slug} does not link to {other}")
        self.assertTrue((out / "book" / "index.html").is_file())
        self.assertTrue((out / "book" / "site.css").is_file() and (out / "book" / "html.css").is_file())

    def test_a_cross_reference_becomes_a_link_to_the_page_that_holds_it_with_its_title(self):
        out = self.home / "site"
        self.build(out)
        page = (out / "book" / "windows-wsl.html").read_text()      # its source says <<troubleshooting>> and <<sign-in>>
        self.assertIn('href="troubleshooting.html#troubleshooting">Troubleshooting</a>', page)
        self.assertNotIn(">[troubleshooting]<", page)

    def test_the_site_has_the_parts_the_spec_requires_in_order(self):
        order = [re.search(r"/(\w[\w-]*)\.adoc", m).group(1) for m in re.findall(r"include::[^\[]+\[\]", (REPO / "docs-src" / "manuscript.adoc").read_text())]
        for a, b in (("windows-wsl", "sign-in"), ("sign-in", "vscode"), ("vscode", "extension"), ("extension", "typical-uses"),
                     ("typical-uses", "commands"), ("commands", "troubleshooting")):
            self.assertLess(order.index(a), order.index(b), f"{a} must come before {b}")

    def test_each_getting_started_step_says_where_to_type(self):
        for name in ("windows-wsl", "sign-in", "vscode"):
            text = (REPO / "docs-src" / "chapters" / "start" / f"{name}.adoc").read_text()
            self.assertRegex(text, r"Debian window|PowerShell|VS Code", name)
        text = (REPO / "docs-src" / "chapters" / "start" / "windows-wsl.adoc").read_text()
        for needle in ("Microsoft Store", "sudo apt update && sudo apt install -y curl", "install.sh | sh", "Windows 11", "password"):
            self.assertIn(needle, text)

    def test_the_sign_in_chapter_prescribes_one_way_and_none_of_the_others(self):
        text = (REPO / "docs-src" / "chapters" / "start" / "sign-in.adoc").read_text()
        self.assertIn("ws-host auth new github", text)
        self.assertIn("never create a token or an SSH key", " ".join(text.split()).replace("you never type a password into the Debian window, and you", "you"))
        for forbidden in ("ssh-keygen", "personal access token", "gh auth login --with-token"):
            self.assertNotIn(forbidden, text)

    def test_the_faq_covers_every_blocker_the_spec_names(self):
        text = (REPO / "docs-src" / "chapters" / "faq" / "troubleshooting.adoc").read_text()
        for needle in ("WSL is not installed", "Debian window opens and closes", "password", "curl: command not found", "certificate", "sudo", "ws-host: command not found",
                       "sign-in code", "clock", "could not read Username", "code: command not found", "opens on Windows, not inside Debian",
                       "IF Console does not show up", "Restricted Mode", "settings alone", "left alone", "boxes instead of icons"):
            self.assertIn(needle, text, needle)
        self.assertGreaterEqual(text.count("*Why:*"), 16)
        self.assertEqual(text.count("*Why:*"), text.count("*Fix:*"))

    def test_the_guide_links_the_vendors_for_what_it_does_not_own_over_https(self):
        text = "".join(p.read_text() for p in (REPO / "docs-src" / "chapters" / "start").glob("*.adoc")) + (REPO / "docs-src" / "chapters" / "faq" / "troubleshooting.adoc").read_text()
        for needle in ("learn.microsoft.com/en-us/windows/wsl/install", "code.visualstudio.com/", "code.visualstudio.com/docs/remote/wsl", "cli.github.com/manual/gh_auth_login", "docs.github.com"):
            self.assertIn("https://" + needle.split("//")[-1], text, needle)
        self.assertNotRegex(text, r"http://(?!PROXY)")

    def test_the_extension_chapter_says_it_is_local_and_not_from_the_marketplace(self):
        text = (REPO / "docs-src" / "chapters" / "start" / "extension.adoc").read_text()
        for needle in ("not on the VS Code Marketplace", "ws-host vscode\nensure", "IF Console", "trust", "decide", "Restricted Mode", ".if-console.env"):
            self.assertIn(needle, text.replace("Reload", "reload").replace("Restricted Mode", "Restricted Mode"))

    def test_the_readme_is_the_five_step_flow_and_links_the_site(self):
        text = (REPO / "README.md").read_text()
        self.assertIn("https://intellectual-frontiers.github.io/workspaces-host/", text)
        flow = text[text.index("## The flow"):text.index("## For contributors")]
        self.assertEqual(len(re.findall(r"^\d\. \*\*", flow, re.M)), 5)
        for needle in ("Microsoft Store", "install.sh", "ws-host auth new github", "ws-host vscode ensure", "IF Console: Learn a Topic"):
            self.assertIn(needle, flow)
        self.assertLess(len(text.splitlines()), 45)

    def test_the_pages_workflow_deploys_main_with_the_pages_actions_after_tests_and_fresh(self):
        text = (REPO / ".github" / "workflows" / "pages.yml").read_text()
        for needle in ("branches: [main]", "pages: write", "id-token: write", "./ws-host test", "./ws-host fresh", "./ws-host docs build", "actions/configure-pages",
                       "actions/upload-pages-artifact", "actions/deploy-pages", "environment:", "github-pages", "GitHub Actions"):
            self.assertIn(needle, text, needle)
        self.assertLess(text.index("./ws-host test"), text.index("./ws-host docs build"))
        self.assertIn("Source", (REPO / "docs-src" / "chapters" / "overview" / "maintainers.adoc").read_text())

    def test_the_home_page_links_every_part_and_the_links_exist_in_the_build(self):
        home = (REPO / "docs" / "index.html").read_text()
        for page in ("windows-wsl", "vscode", "troubleshooting", "commands"):
            self.assertIn(f'href="book/{page}.html"', home)
            self.assertTrue(list((REPO / "docs-src" / "chapters").rglob(f"{page}.adoc")), page)

    def test_the_repository_never_names_the_environment_it_replaced(self):
        import subprocess as sp
        needle = "workspaces-host" + "-v3"
        tracked = sp.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True).stdout.split("\0")
        self.assertTrue(tracked)
        for rel in filter(None, tracked):
            f = REPO / rel
            if f.is_file() and f.suffix not in (".png", ".jpg", ".pdf"):
                try:
                    self.assertNotIn(needle, f.read_text(), rel)
                except UnicodeDecodeError:
                    pass
        self.assertFalse([r for r in tracked if r.startswith("docs/LICENSE-")])
