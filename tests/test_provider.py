"""Providers and the toolchain (0008-providers): declarations read as data, translated into a pinned mise configuration, installed from the lock only and
reached through one provider's environment. The install tests run the real `mise` (WS_HOST_MISE, or the one ws-host fetched) against a real archive."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import Home, REPO
from ws_host.lib import mise, provider as prov, toolchain as tc

MISE_URL = "https://mise.jdx.dev/v2026.10.3/mise-v2026.10.3-linux-%s.tar.xz"
SHA = {"x64": "ff0870ddad7f8c5ba673ceb3e7659f0353da8263eabe8b82220f5816a772c786", "arm64": "a5141f834d883239c2542b9a2136e75428779b2040206537399714d8c534d91f"}


def archive(name="minitool", version="2026.10.3", sha=None, extra=""):
    sha = sha or SHA["x64"]
    return (f'name = "{name}"\nversion = "{version}"\nsummary = "a test archive"\nkind = "archive"\nstrip = 1\n{extra if "bin =" in extra else extra + chr(10) + "bin = " + chr(34) + "bin" + chr(34)}\n'
            f'[platforms.linux-x64]\nurl = "{MISE_URL % "x64"}"\nsha256 = "{sha}"\n[platforms.linux-arm64]\nurl = "{MISE_URL % "arm64"}"\nsha256 = "{SHA["arm64"]}"\n')


def make_provider(base: Path, name="demo", entries=None, launcher=True) -> Path:
    root = base / (name if not (base / name).exists() else f"{name}-{len(list(base.iterdir()))}")
    (root / ".workspaces-host" / "toolchain.d").mkdir(parents=True)
    (root / ".workspaces-host" / "provider.toml").write_text(f'name = "{name}"\nsummary = "A demo"\nlauncher = "./{name}"\nprotocol = 1\n')
    if launcher:
        (root / name).write_text("#!/bin/sh\nexit 0\n")
        (root / name).chmod(0o755)
    for fn, text in (entries if entries is not None else {"minitool": archive()}).items():
        (root / ".workspaces-host" / "toolchain.d" / f"{fn}.toml").write_text(text)
    return root


def real_mise() -> bool:
    try:
        mise.program()
        return True
    except mise.MiseMissing:
        return False


class Declarations(Home):
    """0008-providers FR-001 to FR-005."""

    def load(self, entries=None, **kw):
        return prov.load(make_provider(self.home, entries=entries, **kw))

    def problems(self, text, name="minitool"):
        return [str(x) for x in self.load({name: text}).problems]

    def test_a_valid_provider_has_no_problems_and_its_entries(self):
        p = self.load()
        self.assertEqual(p.problems, [])
        self.assertEqual(p.name, "demo")
        self.assertEqual(p.entries["minitool"].version, "2026.10.3")

    def test_a_folder_without_provider_toml_is_not_a_provider(self):
        self.assertIsNone(prov.load(self.home))

    def test_unknown_keys_are_ignored(self):
        self.assertEqual(self.problems(archive(extra='future = "x"')), [])

    def test_ranges_and_floating_tags_are_rejected_naming_file_and_key(self):
        for v in ("^1.2", ">=1", "latest", "1.*", "1.2, 1.3"):
            ps = self.problems(archive(version=v))
            self.assertTrue(any("toolchain.d/minitool.toml" in x and "'version'" in x for x in ps), (v, ps))

    def test_a_missing_key_a_bad_checksum_a_plain_http_url_and_a_wrong_name_are_rejected(self):
        self.assertTrue(any("'summary'" in x for x in self.problems(archive().replace('summary = "a test archive"\n', ""))))
        self.assertTrue(any("64 hexadecimal" in x for x in self.problems(archive(sha="abc"))))
        self.assertTrue(any("not an https" in x for x in self.problems(archive().replace("https://", "http://"))))
        self.assertTrue(any("must be the same" in x for x in self.problems(archive(name="other"), name="minitool")))

    def test_needs_must_name_an_entry_of_the_same_provider_without_a_cycle(self):
        ps = [str(x) for x in self.load({"a": archive("a", extra='needs = ["zzz"]')}).problems]
        self.assertTrue(any("'zzz'" in x for x in ps))
        ps = [str(x) for x in self.load({"a": archive("a", extra='needs = ["b"]'), "b": archive("b", extra='needs = ["a"]')}).problems]
        self.assertTrue(any("cycle" in x for x in ps))

    def test_a_launcher_that_is_not_an_executable_file_is_rejected(self):
        self.assertTrue(any("launcher" in str(x) for x in self.load(launcher=False).problems))

    def test_npm_and_tool_entries_need_their_own_key(self):
        text = 'name = "{n}"\nversion = "1.2.3"\nsummary = "s"\nkind = "{k}"\n'
        self.assertTrue(any("'package'" in str(x) for x in self.load({"p": text.format(n="p", k="npm")}).problems))
        self.assertTrue(any("'tool'" in str(x) for x in self.load({"p": text.format(n="p", k="tool")}).problems))
        self.assertEqual(self.load({"p": text.format(n="p", k="npm") + 'package = "@a/b"\n'}).problems, [])


class Translation(Home):
    """0008-providers FR-006, FR-009."""

    def test_translation_is_deterministic_and_each_file_says_it_is_generated(self):
        p = prov.load(make_provider(self.home))
        a = prov.translate(p)
        self.assertEqual(a, prov.translate(p))
        for text in a.values():
            self.assertTrue(text.startswith("# Generated by `ws-host toolchain generate`"))
        self.assertIn('[tools."http:minitool"]', a[".config/mise/conf.d/minitool.toml"])
        self.assertIn('checksum = "sha256:' + SHA["x64"], a[".config/mise/conf.d/minitool.toml"])

    def test_stale_names_changed_and_orphaned_generated_files_and_write_fixes_them(self):
        root = make_provider(self.home, entries={"a": archive("a"), "b": archive("b")})
        p = prov.load(root)
        self.assertEqual(len(prov.stale(p)), 3)
        prov.write(p)
        self.assertEqual(prov.stale(p), [])
        (root / ".workspaces-host/toolchain.d/b.toml").unlink()
        p = prov.load(root)
        self.assertEqual(prov.stale(p), [".workspaces-host/mise/.config/mise/conf.d/b.toml"])
        self.assertTrue(any("removed" in c for c in prov.write(p)))
        self.assertEqual(prov.stale(p), [])

    def test_two_providers_declaring_one_name_and_version_differently_conflict_and_identically_do_not(self):
        a = prov.load(make_provider(self.home, "one"))
        same = prov.load(make_provider(self.home, "two"))
        self.assertEqual(prov.conflicts([a, same]), [])
        other = prov.load(make_provider(self.home, "three", entries={"minitool": archive(sha="0" * 64)}))
        c = prov.conflicts([a, other])
        self.assertEqual(len(c), 1)
        self.assertIn("one and three", c[0])
        different_version = prov.load(make_provider(self.home, "four", entries={"minitool": archive(version="2026.10.4", sha="0" * 64)}))
        self.assertEqual(prov.conflicts([a, different_version]), [])


class Environment(Home):
    """0008-providers FR-003, FR-013: the PATH pieces and variables a provider's installed entries add."""

    def test_bin_per_platform_and_variables_joined_in_name_order(self):
        plat = prov.platform()
        other = "linux-arm64" if plat == "linux-x64" else "linux-x64"
        a = archive("a", extra='bin = "bin"\nenv = { TEXMFHOME = "{dir}" }').replace(f"[platforms.{plat}]", f'[platforms.{plat}]\nbin = "bin/{plat}"')
        b = archive("b", extra='env = { TEXMFHOME = "{dir}/x", JAVA_HOME = "{dir}" }')
        c = archive("c", extra='bin = "."')
        p = prov.load(make_provider(self.home, entries={"a": a, "b": b, "c": c}))
        self.assertEqual(p.problems, [])
        store = mise.data_dir() / "installs"
        for n in "abc":
            (store / f"http-{n}" / "2026.10.3").mkdir(parents=True)
        d = tc.delta_of(p)
        self.assertEqual(d["PATH"], os.pathsep.join([str(store / "http-a/2026.10.3" / "bin" / plat), str(store / "http-b/2026.10.3" / "bin"), str(store / "http-c/2026.10.3")]))
        self.assertEqual(d["TEXMFHOME"], f"{store / 'http-a/2026.10.3'}:{store / 'http-b/2026.10.3'}/x")
        self.assertEqual(d["JAVA_HOME"], str(store / "http-b/2026.10.3"))
        env = tc.environment(p, {"PATH": "/usr/bin", "HOME": "/h"})
        self.assertTrue(env["PATH"].endswith(os.pathsep + "/usr/bin"))
        self.assertNotIn(other, d["PATH"])


class Commands(Home):
    """0008-providers FR-010, FR-011, FR-016, FR-017 without installing anything."""

    def setUp(self):
        super().setUp()
        os.environ["WS_HOST_SURFACE"] = "editor"

    def test_nothing_is_enabled_until_a_person_adds_it_and_a_repository_cannot_add_itself(self):
        root = make_provider(self.home)
        code, r = self.run_json("provider", "list")
        self.assertEqual(r["data"]["providers"], [])
        os.environ["WS_HOST_SURFACE"] = "cli"
        code, _ = self.run_json("provider", "add", str(root))
        self.assertNotEqual(code, 0)
        self.assertEqual(prov.enabled(), [])

    def test_add_links_the_provider_and_remove_unlinks_it(self):
        root = make_provider(self.home)
        code, r = self.run_json("provider", "add", str(root), "--confirmed")
        self.assertEqual(code, 0, r)
        self.assertTrue((prov.providers_dir() / "demo").is_symlink())
        code, r = self.run_json("provider", "show", "demo")
        self.assertEqual(r["data"]["entries"][0]["state"], "missing")
        code, r = self.run_json("provider", "remove", "demo", "--confirmed")
        self.assertEqual(code, 0)
        self.assertEqual(prov.enabled(), [])

    def test_a_provider_with_problems_or_a_conflict_is_not_enabled(self):
        bad = make_provider(self.home, "bad", entries={"minitool": archive(version="latest")})
        code, r = self.run_json("provider", "add", str(bad), "--confirmed")
        self.assertEqual(code, 1)
        self.assertIn("version", r["data"]["plain"])
        self.assertEqual(self.run_json("provider", "add", str(make_provider(self.home, "one")), "--confirmed")[0], 0)
        clash = make_provider(self.home, "three", entries={"minitool": archive(sha="0" * 64)})
        code, r = self.run_json("provider", "add", str(clash), "--confirmed")
        self.assertEqual(code, 1)
        self.assertIn("one and three", r["data"]["plain"])

    def test_the_providers_section_reports_stale_files_and_conflicts(self):
        root = make_provider(self.home)
        self.run_json("provider", "add", str(root), "--confirmed")
        from ws_host.commands import provider as cmd
        found = cmd.providers_section(None)
        self.assertTrue(any("not what the entries say" in f["message"] for f in found))
        prov.write(prov.load(root))
        self.assertEqual(cmd.providers_section(None), [])

    def test_system_ensure_with_no_provider_needing_libraries_installs_nothing(self):
        code, r = self.run_json("system", "ensure")
        self.assertEqual(code, 0)
        self.assertEqual(r["data"]["installed"], [])

    def test_system_ensure_dry_run_names_the_libraries_without_installing(self):
        root = make_provider(self.home, entries={"minitool": archive(extra='system = ["libdoesnotexist0|libalsonot1"]')})
        self.run_json("provider", "add", str(root), "--confirmed")
        code, r = self.run_json("system", "ensure", "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(r["data"]["installed"], [])
        self.assertEqual(r["data"]["unavailable"], ["libdoesnotexist0|libalsonot1"])


class Doctor(Home):
    """0008-providers FR-017."""

    def test_doctor_reports_each_provider_and_brew_and_direnv_only_as_suggestions(self):
        from ws_host.commands import doctor
        root = make_provider(self.home)
        os.environ["WS_HOST_SURFACE"] = "editor"
        self.run_json("provider", "add", str(root), "--confirmed")
        bin_ = self.home / "bin"
        bin_.mkdir()
        for n in ("brew", "direnv"):
            (bin_ / n).write_text("#!/bin/sh\n")
            (bin_ / n).chmod(0o755)
        os.environ["PATH"] = f"{bin_}{os.pathsep}{os.environ['PATH']}"
        r, _ = doctor._build()
        self.assertEqual({s["name"] for s in r["suggestions"]}, {"brew", "direnv"})
        self.assertFalse([c for c in r["checks"] if "brew" in c["name"] or "direnv" in c["name"]])
        mine = [c for c in r["checks"] if c["name"] == "provider demo"]
        self.assertEqual(mine[0]["status"], "warn")
        self.assertIn("minitool", mine[0]["detail"])


@unittest.skipUnless(real_mise() and os.environ.get("WS_HOST_OFFLINE") != "1", "needs mise and the network")
class Installing(Home):
    """0008-providers FR-006, FR-007, FR-012, FR-013, FR-015, SC-001, SC-002: the real mise, a real archive, one store."""

    def setUp(self):
        super().setUp()
        self.mise = str(mise.program())
        os.environ["WS_HOST_MISE"] = self.mise
        os.environ["WS_HOST_SURFACE"] = "editor"

    def run_json_before_dashes(self, *argv):
        """--json goes before `--`: after it, it is the program's."""
        i = argv.index("--")
        return self.run_json(*argv[:i]) if False else self._json(*argv[:i], "--json", *argv[i:])

    def _json(self, *argv):
        import json
        code, out = self.run_cmd(*argv)
        return code, json.loads(out.strip().splitlines()[-1])

    def enable(self, **kw):
        root = make_provider(self.home, **kw)
        self.assertEqual(self.run_json("toolchain", "generate", "--root", str(root))[0], 0)
        self.assertEqual(self.run_json("provider", "add", str(root), "--confirmed")[0], 0)
        return root

    def test_generate_ensure_run_and_prune_through_one_store(self):
        root = self.enable()
        self.assertTrue((root / ".workspaces-host/mise/.config/mise/mise.lock").is_file())
        code, r = self.run_json("toolchain", "ensure", "--all")
        self.assertEqual(code, 0, r)
        installed = Path(self.paths.data_dir()) / "mise" / "data" / "installs" / "http-minitool" / "2026.10.3" / "bin" / "mise"
        self.assertTrue(installed.is_file())
        code, r = self.run_json("toolchain", "show", "minitool")
        self.assertEqual(r["data"]["state"], "ready")
        code, r = self.run_json_before_dashes("provider", "run", "demo", "--", "mise", "--version")
        self.assertEqual(code, 0, r)
        self.assertEqual(r["data"]["exit"], 0)
        code, r = self.run_json_before_dashes("provider", "run", "demo", "--", "sh", "-c", "exit 7")
        self.assertEqual(code, 1)
        self.assertEqual(r["data"]["exit"], 7)
        self.assertEqual(self.run_json("toolchain", "remove", "--unused")[1]["data"]["removed"], [])
        self.run_json("provider", "remove", "demo", "--confirmed")
        code, r = self.run_json("toolchain", "remove", "--unused", "--dry-run")
        self.assertEqual([x["name"] for x in r["data"]["removed"]], ["http-minitool"])
        self.assertTrue(installed.is_file())
        code, r = self.run_json("toolchain", "remove", "--unused")
        self.assertFalse(installed.exists())

    def test_run_in_text_mode_prints_only_the_programs_output_and_passes_its_status_and_ensure_installs_first(self):
        self.enable()
        code, out = self.run_cmd("provider", "run", "demo", "--ensure", "minitool", "--", "sh", "-c", "echo hello; exit 7")
        self.assertEqual((code, out), (7, ""), "the child writes to the real stdout, so this process's capture holds nothing")
        self.assertTrue((Path(self.paths.data_dir()) / "mise" / "data" / "installs" / "http-minitool" / "2026.10.3").is_dir())
        r = subprocess.run([sys.executable, "-m", "ws_host", "provider", "run", "demo", "--", "sh", "-c", "echo hello; exit 3"], capture_output=True, text=True, cwd=REPO)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "hello"))
        r = subprocess.run([sys.executable, "-m", "ws_host", "provider", "run", "demo", "--", "echo", "--json", "--offline"], capture_output=True, text=True, cwd=REPO)
        self.assertEqual(r.stdout.strip(), "--json --offline", "a flag after -- is the program's, not ws-host's")

    def test_a_tampered_archive_installs_nothing(self):
        root = self.enable(entries={"minitool": archive(sha="0" * 64)})
        code, r = self.run_json("toolchain", "ensure", "--all")
        self.assertNotEqual(code, 0)
        self.assertFalse((Path(self.paths.data_dir()) / "mise" / "data" / "installs" / "http-minitool" / "2026.10.3").exists())

    def test_ensure_refuses_when_the_generated_files_are_stale_and_installs_only_from_the_lock(self):
        root = make_provider(self.home)
        self.run_json("provider", "add", str(root), "--confirmed")
        code, r = self.run_json("toolchain", "ensure", "--all")
        self.assertEqual(code, 1)
        self.assertIn("toolchain generate", r["data"]["plain"])

    def test_a_configuration_above_the_provider_is_never_read(self):
        root = self.enable()
        (root / "mise.toml").write_text('[tools]\nnode = "22"\n')
        (root / ".workspaces-host" / "mise.toml").write_text('[tools]\nnode = "22"\n')
        code, r = self.run_json("toolchain", "ensure", "--all")
        self.assertEqual(code, 0, r)
        self.assertFalse((Path(self.paths.data_dir()) / "mise" / "data" / "installs" / "node").exists())


if __name__ == "__main__":
    unittest.main()
