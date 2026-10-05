"""A release (0007-releases): one version, four assets, byte-identical rebuilds, a publish that refuses until it is safe, and no service taking part."""
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tests.helpers import Workspace
from ws_host import VERSION
from ws_host.core import registry as reg
from ws_host.lib import release

REPO = Path(__file__).resolve().parent.parent


def fake_wheel(path: Path, extra: dict | None = None) -> Path:
    files = {"ws_host/__init__.py": f'VERSION = "{VERSION}"\n', "ws_host/__main__.py": "def run(): pass\n", "ws_host/data/themes/a.json": "{}",
             f"ws_host-{VERSION}.dist-info/METADATA": f"Name: ws-host\nVersion: {VERSION}\n", **(extra or {})}
    with zipfile.ZipFile(path, "w") as z:
        for n, d in files.items():
            z.writestr(zipfile.ZipInfo(n, (2020, 2, 2, 0, 0, 0)), d)
    return path


class OneVersion(unittest.TestCase):
    """0007-releases FR-001, FR-002."""

    def test_the_version_is_written_once_and_the_console_agrees(self):
        self.assertEqual(release.version_problems(), [])
        self.assertEqual(release.console_manifest()["version"], VERSION)
        self.assertEqual(release.console_manifest()["name"], "workspaces-console")

    def test_pyproject_reads_the_version_from_the_package_and_does_not_state_it(self):
        text = (REPO / "pyproject.toml").read_text()
        self.assertIn('dynamic = ["version"]', text)
        self.assertNotRegex(text, r'(?m)^version\s*=')
        self.assertIn('path = "ws_host/__init__.py"', text)

    def test_a_console_with_another_version_stops_the_release(self):
        with mock.patch.object(release, "console_manifest", return_value={"name": "workspaces-console", "version": "9.9.9"}):
            self.assertTrue(any("9.9.9" in p for p in release.version_problems()))

    def test_the_assets_and_the_tag_are_named_by_the_version(self):
        n = release.names("1.2.3")
        self.assertEqual(n, {"app": "ws-host-1.2.3.tar.gz", "wheel": "ws_host-1.2.3-py3-none-any.whl", "console": "workspaces-console-1.2.3.vsix", "sums": "SHA256SUMS"})
        self.assertEqual(release.tag("1.2.3"), "v1.2.3")


class AppTarball(unittest.TestCase):
    """0007-releases FR-003, FR-004."""

    def build(self, d: Path, **kw):
        wheel = fake_wheel(d / f"ws_host-{VERSION}-py3-none-any.whl", **kw)
        return release.build_app_tarball(wheel, d)

    def test_it_holds_the_wheels_package_and_a_launcher_and_nothing_else(self):
        with tempfile.TemporaryDirectory() as t:
            tar = self.build(Path(t))
            with tarfile.open(tar) as z:
                names = z.getnames()
                top = f"ws-host-{VERSION}"
                files = sorted(n for n in names if z.getmember(n).isfile())
                self.assertEqual(files, [f"{top}/bin/ws-host", f"{top}/lib/ws_host/__init__.py", f"{top}/lib/ws_host/__main__.py", f"{top}/lib/ws_host/data/themes/a.json"])
                self.assertEqual(z.getmember(f"{top}/bin/ws-host").mode, 0o755)
                self.assertTrue(z.extractfile(f"{top}/bin/ws-host").read().startswith(b"#!/usr/bin/env python3\n"))

    def test_two_builds_are_the_same_bytes_whatever_the_time_and_the_directory(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            first = self.build(Path(a))
            os.utime(Path(a) / f"ws_host-{VERSION}-py3-none-any.whl", (1, 1))
            second = self.build(Path(b))
            self.assertEqual(hashlib.sha256(first.read_bytes()).hexdigest(), hashlib.sha256(second.read_bytes()).hexdigest())
            with tarfile.open(first) as z:
                self.assertEqual({m.mtime for m in z.getmembers()}, {release.EPOCH})
                self.assertEqual({(m.uid, m.gid, m.uname, m.gname) for m in z.getmembers()}, {(0, 0, "", "")})

    def test_a_different_wheel_is_a_different_tarball(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            self.assertNotEqual(self.build(Path(a)).read_bytes(), self.build(Path(b), extra={"ws_host/x.py": "x = 1\n"}).read_bytes())

    def test_the_launcher_needs_only_python_and_runs_the_library_beside_it(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            with tarfile.open(self.build(t)) as z:
                z.extractall(t / "x", filter="data")
            (t / "x" / f"ws-host-{VERSION}" / "lib" / "ws_host" / "__main__.py").write_text("def run():\n    print('ran from', __file__.split('/lib/')[1])\n")
            link = t / "link"
            link.symlink_to(t / "x" / f"ws-host-{VERSION}" / "bin" / "ws-host")
            out = subprocess.run([str(link)], capture_output=True, text=True, env={"PATH": os.environ["PATH"], "HOME": str(t)})
            self.assertEqual(out.stdout.strip(), "ran from ws_host/__main__.py", out.stderr)


class Deterministic(unittest.TestCase):
    """0007-releases FR-004: the zip a release holds is rewritten with the one time and attributes."""

    def test_a_zip_rewritten_twice_from_different_times_is_the_same_bytes(self):
        def make(p: Path, when):
            with zipfile.ZipFile(p, "w") as z:
                for n in ("b.txt", "a.txt"):
                    z.writestr(zipfile.ZipInfo(n, when), n * 10)
            release.normalize_zip(p)
            return p.read_bytes()
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(make(Path(t) / "one.zip", (2031, 5, 5, 5, 5, 6)), make(Path(t) / "two.zip", (2025, 1, 1, 0, 0, 0)))

    def test_the_translation_bundle_is_every_message_in_a_stable_order(self):
        with tempfile.TemporaryDirectory() as t:
            src = Path(t) / "src"
            src.mkdir()
            (src / "a.ts").write_text("t('Zed'); t(\"Alpha \\u2026\"); t(`Back tick`); x.t('not'); t(dynamic)\n")
            self.assertEqual(release.l10n_messages(src), ["Alpha …", "Back tick", "Zed"])


class Checksums(unittest.TestCase):
    """0007-releases FR-007."""

    def test_the_sums_file_lists_the_three_assets_in_sha256sum_format_and_reads_back(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            for k in ("app", "wheel", "console"):
                (t / release.names()[k]).write_bytes(k.encode())
            release.write_sums(t)
            lines = (t / "SHA256SUMS").read_text().splitlines()
            self.assertEqual(len(lines), 3)
            for line in lines:
                self.assertRegex(line, r"^[0-9a-f]{64}  \S+$")
            sums = release.read_sums(t)
            self.assertEqual(sums[release.names()["app"]], hashlib.sha256(b"app").hexdigest())
            check = subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=t, capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)


class Toolchain(unittest.TestCase):
    """0007-releases FR-005: only what is pinned builds a release."""

    def test_the_build_backend_is_pinned_exactly(self):
        self.assertRegex((REPO / "pyproject.toml").read_text(), r'requires = \["hatchling==\d+\.\d+\.\d+"\]')

    def test_python_uv_and_node_are_locked_with_checksums_for_both_platforms(self):
        lock = (REPO / ".config" / "mise" / "mise.lock").read_text()
        for tool in ("python", "uv", "node"):
            self.assertRegex(lock, rf'\[\[tools\.{tool}\]\]', tool)
        self.assertGreaterEqual(len(re.findall(r'checksum = "sha256:[0-9a-f]{64}"', lock)), 6)
        for platform in ("linux-x64", "linux-arm64"):
            self.assertIn(f'platforms.{platform}', lock)
        for f in (REPO / ".config" / "mise" / "conf.d").glob("*.toml"):
            for line in f.read_text().splitlines():
                m = re.match(r'(python|uv|node)\s*=\s*"([^"]+)"', line)
                if m:
                    self.assertRegex(m.group(2), r"^\d+\.\d+\.\d+$", f"{f.name}: {line}")

    def test_the_console_is_installed_from_its_lock_and_every_package_has_an_integrity_hash(self):
        lock = json.loads((REPO / "console" / "package-lock.json").read_text())
        bare = [n for n, p in lock["packages"].items() if n and not p.get("link") and not p.get("integrity")]
        self.assertEqual(bare, [])
        self.assertTrue(all(re.fullmatch(r"\d+\.\d+\.\d+", v) for v in json.loads((REPO / "console" / "package.json").read_text())["devDependencies"].values()))

    def test_the_console_build_gates_come_before_the_package(self):
        src = (REPO / "ws_host" / "lib" / "release.py").read_text()
        order = [src.index(s) for s in ('"Type-check the Console (strict)"', '"Lint the Console (no warnings)"', '"Run the Console\'s unit tests"', '"Pack the Console"')]
        self.assertEqual(order, sorted(order))
        self.assertIn('"--max-warnings", "0"', src)


class Publishing(Workspace):
    """0007-releases FR-010, FR-011, FR-012."""

    def setUp(self):
        super().setUp()
        self.repo = self.home / "clone"
        self.repo.mkdir()
        for args in (("init", "-b", "main"), ("config", "user.email", "a@b.c"), ("config", "user.name", "T")):
            subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True)
        (self.repo / "f").write_text("x")
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-m", "x"], cwd=self.repo, check=True, capture_output=True)
        self.out = self.home / "dist"
        self.out.mkdir()
        for k in ("app", "wheel", "console"):
            (self.out / release.names()[k]).write_bytes(k.encode())
        release.write_sums(self.out)
        p = mock.patch.object(release, "root", return_value=self.repo)
        p.start()
        self.addCleanup(p.stop)
        q = mock.patch.object(release, "check", return_value=[release.Finding("x", True, "ok")])
        q.start()
        self.addCleanup(q.stop)

    def test_a_dirty_tree_an_unpushed_commit_and_an_existing_tag_each_stop_it(self):
        problems = release.publish_problems(self.out)
        self.assertIn("this commit has not been pushed", problems)
        (self.repo / "g").write_text("y")
        self.assertIn("there are changes that are not committed", release.publish_problems(self.out))
        subprocess.run(["git", "tag", release.tag()], cwd=self.repo, check=True)
        self.assertIn(f"the tag {release.tag()} already exists", release.publish_problems(self.out))

    def test_a_release_that_fails_its_checks_is_never_published(self):
        with mock.patch.object(release, "check", return_value=[release.Finding("The checksums match", False, "differ")]):
            self.assertTrue(any("does not pass its checks" in p for p in release.publish_problems(self.out)))

    def test_the_notes_give_each_file_its_checksum_and_the_exact_mise_entry(self):
        notes = release.notes(self.out)
        sums = release.read_sums(self.out)
        for name, digest in sums.items():
            self.assertIn(digest, notes)
            self.assertIn(name, notes)
        n = release.names()["app"]
        self.assertIn(f'url = "https://github.com/intellectual-frontiers/workspaces-host/releases/download/{release.tag()}/{n}"', notes)
        self.assertIn(f'checksum = "sha256:{sums[n]}"', notes)
        self.assertIn('[tools."http:ws-host"]', notes)

    def test_publishing_uses_the_persons_gh_and_never_takes_a_token(self):
        calls = []
        (self.home.parent / "ghbin").mkdir(exist_ok=True)
        gh = self.home.parent / "ghbin" / "gh"
        gh.write_text(f'#!/bin/sh\necho "$@" >> "{self.home}/gh.calls"\necho https://github.com/x/y/releases/tag/v1\n')
        gh.chmod(0o755)
        with mock.patch.dict(os.environ, {"PATH": f"{gh.parent}:{os.environ['PATH']}"}):
            address = release.publish(self.out)
        text = (self.home / "gh.calls").read_text()
        self.assertIn(f"release create {release.tag()}", text)
        for v in release.names().values():
            self.assertIn(v, text)
        self.assertEqual(address.strip(), "https://github.com/x/y/releases/tag/v1")
        self.assertNotRegex(text, r"--token|GH_TOKEN|GITHUB_TOKEN")
        command = reg.discover().get(("release", "publish"))
        self.assertNotIn("token", [a.name.lower() for a in command.args])

    def test_publish_is_a_decision_a_person_makes_and_never_over_mcp(self):
        c = reg.discover().get(("release", "publish"))
        self.assertEqual(c.category, "decision")
        self.assertNotIn("mcp", c.surfaces)
        self.assertEqual(reg.discover().get(("release", "build")).category, "build")
        self.assertEqual(reg.discover().get(("release", "check")).category, "check")

    def test_nothing_in_the_repository_needs_a_continuous_integration_service_to_make_a_release(self):
        for f in (REPO / ".github" / "workflows").glob("*.yml"):
            text = f.read_text().lower()
            self.assertNotIn("release build", text)
            self.assertNotIn("release publish", text)
            self.assertNotIn("gh release", text)


class Commands(Workspace):
    """0007-releases FR-008, FR-009."""

    def test_a_dry_run_builds_nothing_and_says_what_it_would_make(self):
        code, doc = self.run_json("release", "build", "--dry-run", "--output", str(self.home / "out"))
        self.assertEqual(code, 0, doc)
        self.assertFalse((self.home / "out").exists())
        self.assertEqual([f["name"] for f in doc["data"]["files"]], list(release.names().values()))

    def test_checking_a_folder_with_no_release_fails_in_plain_words(self):
        (self.home / "empty").mkdir()
        code, doc = self.run_json("release", "check", "--output", str(self.home / "empty"))
        self.assertNotEqual(code, 0)
        self.assertIn("fails", doc["data"]["plain"])
        self.assertEqual([c["status"] for c in doc["data"]["checks"]][:2], ["ok", "fail"])

    def test_a_release_made_of_the_real_pieces_passes_every_check(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            wheel = fake_wheel(t / release.names()["wheel"])
            release.build_app_tarball(wheel, t)
            with zipfile.ZipFile(t / release.names()["console"], "w") as z:
                z.writestr("extension/package.json", json.dumps({"name": "workspaces-console", "version": VERSION}))
                for n in ("extension/dist/extension.js", "extension/dist/webview.js", "extension/media/icon.png", "extension/l10n/bundle.l10n.json"):
                    z.writestr(n, "x")
            with zipfile.ZipFile(t / release.names()["wheel"], "a") as z:
                pass
            release.write_sums(t)
            findings = {f.name: f for f in release.check(t)}
            self.assertTrue(findings["One version everywhere"].ok)
            self.assertTrue(findings["The checksums match"].ok, findings["The checksums match"].plain)
            self.assertTrue(findings["The Console package holds what it runs and nothing else"].ok)
            self.assertFalse(findings["The app tarball runs where it is unpacked"].ok, "the fake library prints no version, so this check must notice")
            (t / release.names()["wheel"]).write_bytes(b"tampered")
            self.assertFalse({f.name: f for f in release.check(t)}["The checksums match"].ok)

    def test_a_console_package_that_leaks_its_sources_fails(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            for k in ("app", "wheel"):
                fake_wheel(t / release.names()["wheel"])
            release.build_app_tarball(t / release.names()["wheel"], t)
            with zipfile.ZipFile(t / release.names()["console"], "w") as z:
                z.writestr("extension/package.json", json.dumps({"name": "workspaces-console", "version": VERSION}))
                for n in ("extension/dist/extension.js", "extension/dist/webview.js", "extension/media/icon.png", "extension/l10n/bundle.l10n.json", "extension/src/a.ts", "extension/dist/extension.js.map"):
                    z.writestr(n, "x")
            release.write_sums(t)
            found = {f.name: f for f in release.check(t)}["The Console package holds what it runs and nothing else"]
            self.assertFalse(found.ok)
            self.assertIn("leaks", found.plain)


if __name__ == "__main__":
    unittest.main()
