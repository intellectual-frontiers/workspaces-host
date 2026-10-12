"""archon (0011-archon): the profile, versions, the sources of a requirement, progress as events, Python environments and the command line."""
from __future__ import annotations

import io
import json
import os
import stat
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from archon import profile, progress, provider as prov, pyenv, requirements, system, toolchain as tc, versions
from .helpers import REPO, Home


def script(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class Tty(io.StringIO):
    def isatty(self):
        return True


class Profile(unittest.TestCase):
    def test_a_run_is_unattended_unless_something_says_a_person_is_there(self):  # FR-005
        self.assertEqual(profile.detect({}, io.StringIO(), io.StringIO()).attendance, "unattended")
        both = dict(stdin=Tty(), stderr=Tty())
        self.assertEqual(profile.detect({}, **both).attendance, "attended")
        self.assertEqual(profile.detect({}, stdin=Tty(), stderr=io.StringIO()).attendance, "unattended", "a pipe on one side is not enough")

    def test_the_variable_decides_first_and_ci_and_agents_beat_a_terminal(self):
        both = dict(stdin=Tty(), stderr=Tty())
        self.assertEqual(profile.detect({"ARCHON_ATTENDANCE": "attended"}, io.StringIO(), io.StringIO()).attendance, "attended")
        self.assertEqual(profile.detect({"ARCHON_ATTENDANCE": "unattended", "CI": "1"}, **both).why, "ARCHON_ATTENDANCE")
        self.assertEqual(profile.detect({"CI": "true"}, **both), profile.Profile("unattended", "CI"))
        self.assertEqual(profile.detect({"CLAUDE_CODE_REMOTE": "1"}, **both).attendance, "unattended")

    def test_the_computers_ws_host_does_not_enter_the_decision(self):
        with mock.patch("shutil.which", return_value="/usr/bin/ws-host"):
            self.assertEqual(profile.detect({"WS_HOST": "1"}, io.StringIO(), io.StringIO()).attendance, "unattended")

    def test_the_decision_is_written_for_what_archon_starts(self):  # FR-007
        env = profile.exported({"CI": "1"})
        self.assertEqual(env["ARCHON_ATTENDANCE"], "unattended")


class Versions(unittest.TestCase):
    def test_versions_are_compared_as_dotted_numbers_and_distribution_decoration_is_ignored(self):  # FR-010
        self.assertTrue(versions.meets("2:21.0.4+7-1~deb12u1", "21"))
        self.assertTrue(versions.meets("21", "21.0.0"))
        self.assertTrue(versions.meets("22.1", "22.0.9"))
        self.assertFalse(versions.meets("18.20.4+dfsg-1", "22"))
        self.assertFalse(versions.meets("1.9", "1.10"))
        self.assertFalse(versions.meets("nonsense", "1"))

    def test_the_first_version_looking_word_is_taken(self):
        self.assertEqual(versions.first_in('openjdk version "21.0.12" 2026-07-21'), "21.0.12")
        self.assertEqual(versions.first_in("v22.9.0"), "22.9.0")
        self.assertIsNone(versions.first_in("nothing here"))


ENTRY = """name = "jre"
version = "21.0.12.1+1"
summary = "a Java runtime"
kind = "archive"
bin = "bin"
minimum = "21"
probe = {{ program = "java", args = ["-version"] }}
packages = {{ apt = ["openjdk-21-jre-headless"], dnf = ["java-21-openjdk-headless"] }}
provides = {{ java = "bin/java" }}

[platforms.linux-x64]
url = "https://example.test/jre.tar.gz"
sha256 = "{sha}"
"""


class Sources(Home):
    """A provider whose one entry may come from PATH, the package manager or its pinned download, with stand-ins for java, apt and sudo."""

    def setUp(self):
        super().setUp()
        self.root = self.home.parent / "repo"
        (self.root / ".workspaces-host" / "toolchain.d").mkdir(parents=True)
        (self.root / ".workspaces-host" / "provider.toml").write_text('name = "demo"\nsummary = "x"\nlauncher = "./run"\nprotocol = 1\n')
        script(self.root / "run", "exit 0\n")
        (self.root / ".workspaces-host" / "toolchain.d" / "jre.toml").write_text(ENTRY.format(sha="0" * 64))
        self.bin = self.home.parent / "bin"
        self.bin.mkdir()
        self.log = self.home.parent / "calls.log"
        self.said: list[str] = []
        for tool in ("cat", "chmod", "true", "env", "grep"):          # the only programs the stand-ins use; a java or apt of the machine's own must not be found
            os.symlink(Path("/bin") / tool if (Path("/bin") / tool).exists() else Path("/usr/bin") / tool, self.bin / tool)
        self.path = str(self.bin)
        os.environ["PATH"] = self.path
        os.environ.pop("ARCHON_OFFLINE", None)
        self.p = prov.load(self.root)
        self.assertEqual(self.p.problems, [])
        self.unattended = profile.Profile("unattended", "test")
        self.attended = profile.Profile("attended", "test")

    def java(self, version: str):
        script(self.bin / "java", f'echo \'openjdk version "{version}" 2026-01-01\' >&2\n')

    def apt(self, offered: str, installs_version: str | None = None, sudo: bool = True):
        """apt-cache offers `offered`; an install puts a java of `installs_version` on PATH."""
        make = f'echo \'openjdk version "{installs_version}"\' >&2' if installs_version else ""
        script(self.home.parent / "tools" / "mkjava", f'cat > {self.bin}/java <<\'EOF\'\n#!/bin/sh\n{make}\nEOF\nchmod +x {self.bin}/java\n')
        install = f'{self.home.parent}/tools/mkjava' if installs_version else "true"
        script(self.bin / "apt-get", f'echo "apt-get $*" >> {self.log}\ncase "$*" in *install*) {install};; esac\nexit 0\n')
        script(self.bin / "apt-cache", f'printf "%s:\\n  Candidate: {offered}\\n" "$2"\n')
        if sudo:
            script(self.bin / "sudo", f'echo "sudo $*" >> {self.log}\nif [ "$1" = -n ]; then shift; fi\nexec "$@"\n')
        patcher = mock.patch("os.geteuid", return_value=1000)
        patcher.start()
        self.addCleanup(patcher.stop)

    def ensure(self, **kw):
        kw.setdefault("profile", self.unattended)
        kw.setdefault("say", self.said.append)
        return requirements.ensure(self.p, ["jre"], **kw)

    def test_a_program_on_path_that_meets_the_minimum_is_used_as_it_is(self):  # FR-011, FR-012
        self.java("21.0.4")
        [r] = self.ensure()
        self.assertEqual((r.source, r.version, r.programs["java"], r.env), ("path", "21.0.4", str(self.bin / "java"), {}))
        self.assertEqual(requirements.environment([r], {"PATH": "/x"}), {"PATH": "/x"})

    def test_a_program_that_is_too_old_is_not_used_and_the_package_manager_is_asked(self):
        self.java("17.0.1")
        self.apt("21.0.5-1", installs_version="21.0.5")
        [r] = self.ensure()
        self.assertEqual((r.source, r.version), ("system", "21.0.5"))
        self.assertIn("sudo -n env DEBIAN_FRONTEND=noninteractive apt-get", self.log.read_text(), "unattended, sudo may not ask for a password")
        self.assertTrue(any("Installing" in s for s in self.said))

    def test_the_package_manager_is_used_before_the_pinned_download(self):
        self.apt("21.0.5-1", installs_version="21.0.5")
        with mock.patch.object(tc, "ensure", side_effect=AssertionError("the pinned copy must not be fetched")):
            [r] = self.ensure()
        self.assertEqual(r.source, "system")

    def test_an_offer_that_is_too_old_falls_to_the_pinned_download_and_says_why(self):
        self.apt("18.0.2-1")
        with mock.patch.object(tc, "ensure"), mock.patch.object(tc, "install_path", return_value=Path("/store/jre")):
            [r] = self.ensure()
        self.assertEqual((r.source, r.version), ("pinned", "21.0.12.1+1"))
        self.assertEqual(r.env["PATH"], "/store/jre/bin")
        self.assertEqual(requirements.environment([r], {"PATH": "/x"})["PATH"], "/store/jre/bin:/x")

    def test_without_administrator_rights_the_system_source_is_skipped_not_failed(self):
        self.apt("21.0.5-1", installs_version="21.0.5", sudo=False)
        with mock.patch.object(tc, "ensure", side_effect=tc.ToolchainError("install", "no network", "no network")), \
                self.assertRaises(requirements.Unavailable) as e:
            self.ensure()
        reasons = dict(e.exception.reasons)
        self.assertIn("no sudo", reasons["system"])
        self.assertEqual(e.exception.exit_code, 3)
        self.assertIn("pinned: no network", str(e.exception))

    def test_an_entry_without_a_minimum_has_only_the_pinned_source(self):  # FR-008
        (self.root / ".workspaces-host" / "toolchain.d" / "jre.toml").write_text(ENTRY.format(sha="0" * 64).replace('minimum = "21"\n', ""))
        self.p = prov.load(self.root)
        self.java("21.0.4")
        with mock.patch.object(tc, "ensure"), mock.patch.object(tc, "install_path", return_value=Path("/store/jre")):
            [r] = self.ensure()
        self.assertEqual(r.source, "pinned")

    def test_an_attended_person_is_told_what_sudo_will_install_and_may_decline(self):  # FR-006
        self.apt("21.0.5-1", installs_version="21.0.5")
        asked = []
        with mock.patch.object(tc, "ensure", side_effect=tc.ToolchainError("install", "declined too", "declined too")), \
                self.assertRaises(requirements.Unavailable) as e:
            self.ensure(profile=self.attended, ask=lambda q: asked.append(q) or False)
        self.assertEqual(len(asked), 1)
        self.assertTrue(any("sudo will ask for your password" in s for s in self.said))
        self.assertIn("you chose not to install it", dict(e.exception.reasons)["system"])
        self.assertFalse(self.log.exists() and "install" in self.log.read_text())

    def test_an_unattended_run_never_asks(self):
        self.apt("21.0.5-1", installs_version="21.0.5")
        [r] = self.ensure(ask=lambda q: self.fail("asked: " + q))
        self.assertEqual(r.source, "system")

    def test_offline_skips_the_package_manager_but_still_finds_a_program_on_path(self):  # FR-014
        self.java("21.0.4")
        self.assertEqual(self.ensure(offline=True)[0].source, "path")
        os.remove(self.bin / "java")
        self.apt("21.0.5-1", installs_version="21.0.5")
        with mock.patch.object(tc, "ensure", side_effect=tc.ToolchainError("install", "offline", "offline")), self.assertRaises(requirements.Unavailable) as e:
            self.ensure(offline=True)
        self.assertIn("offline", dict(e.exception.reasons)["system"])

    def test_the_failure_names_every_source_and_why(self):  # FR-015
        os.environ["PATH"] = str(self.bin)
        with mock.patch.object(system, "detect", return_value=None), mock.patch.object(tc, "ensure", side_effect=tc.ToolchainError("install", "x", "no build for this platform")), \
                self.assertRaises(requirements.Unavailable) as e:
            self.ensure()
        self.assertEqual([s for s, _ in e.exception.reasons], ["path", "system", "pinned"])
        self.assertIn("21 or newer", str(e.exception))

    def test_a_wrong_declaration_is_not_hidden_behind_a_source(self):
        with mock.patch.object(tc, "ensure", side_effect=tc.ToolchainError("stale", "x", "stale", 1)), self.assertRaises(tc.ToolchainError):
            self.ensure()

    def test_a_requirement_an_entry_needs_comes_first(self):  # FR-009
        (self.root / ".workspaces-host" / "toolchain.d" / "tool.toml").write_text(ENTRY.format(sha="1" * 64).replace('name = "jre"', 'name = "tool"')
                                                                                   .replace('minimum = "21"\n', "").replace("provides = ", 'needs = ["jre"]\nprovides = ').replace("java =", "tool ="))
        self.p = prov.load(self.root)
        self.assertEqual(self.p.problems, [])
        self.java("21.0.4")
        with mock.patch.object(tc, "ensure"), mock.patch.object(tc, "install_path", return_value=Path("/store/tool")):
            got = requirements.ensure(self.p, ["tool"], profile=self.unattended, say=self.said.append)
        self.assertEqual([(r.name, r.source) for r in got], [("jre", "path"), ("tool", "pinned")])

    def libs(self, have: str, offered: str = "1.0"):
        """A stand-in dpkg-query that knows which libraries are installed, with apt-cache and apt-get from `apt`."""
        self.have = self.home.parent / "have"
        self.have.write_text(have)
        script(self.bin / "dpkg-query", f'grep -qx "$3" {self.have} && printf "install ok installed" || exit 1\n')
        self.apt(offered)
        script(self.bin / "apt-get", f'echo "apt-get $*" >> {self.log}\ncase "$*" in *install*) for p in "$@"; do echo $p >> {self.have}; done;; esac\nexit 0\n')
        (self.root / ".workspaces-host" / "toolchain.d" / "jre.toml").write_text(
            ENTRY.format(sha="0" * 64).replace('minimum = "21"\n', "").replace("provides = ", 'system = ["libfoo1"]\nprovides = '))
        self.p = prov.load(self.root)
        self.assertEqual(self.p.problems, [])

    def test_the_libraries_a_pinned_program_links_against_are_installed_as_part_of_the_entry(self):  # FR-022
        self.libs("coreutils\n")
        with mock.patch.object(tc, "ensure"), mock.patch.object(tc, "install_path", return_value=Path("/store/jre")):
            [r] = self.ensure()
        self.assertEqual(r.source, "pinned")
        self.assertIn("openjdk" if False else "libfoo1", self.log.read_text())
        self.assertIn("sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install", self.log.read_text())

    def test_libraries_already_there_install_nothing(self):
        self.libs("libfoo1\n")
        with mock.patch.object(tc, "ensure"), mock.patch.object(tc, "install_path", return_value=Path("/store/jre")):
            self.ensure()
        self.assertFalse(self.log.exists() and "install" in self.log.read_text())

    def test_missing_libraries_with_no_rights_end_with_exit_3_naming_them(self):
        self.libs("coreutils\n")
        os.remove(self.bin / "sudo")
        with mock.patch.object(tc, "ensure"), mock.patch.object(tc, "install_path", return_value=Path("/store/jre")), self.assertRaises(requirements.Unavailable) as e:
            self.ensure()
        self.assertEqual(e.exception.exit_code, 3)
        self.assertIn("libfoo1", str(e.exception))

    def test_obtainable_says_what_can_come_from_no_source_and_installs_nothing(self):  # FR-004
        self.assertEqual(requirements.obtainable(self.p, ["jre"], offline=False), [])
        [(name, why)] = requirements.obtainable(self.p, ["jre"], offline=True)
        self.assertEqual(name, "jre")
        self.assertIn("offline", why)
        self.java("21.0.4")
        self.assertEqual(requirements.obtainable(self.p, ["jre"], offline=True), [])
        self.assertFalse(self.log.exists())

    def test_the_declaration_is_checked(self):  # FR-008
        (self.root / ".workspaces-host" / "toolchain.d" / "jre.toml").write_text(ENTRY.format(sha="0" * 64).replace('minimum = "21"', 'minimum = "twenty"').replace("apt =", "pacman ="))
        p = prov.load(self.root)
        text = " ".join(map(str, p.problems))
        self.assertIn("'minimum' is 'twenty'", text)
        self.assertIn("'packages' must be a table", text)


class Events(unittest.TestCase):
    def setUp(self):
        self.old = dict(os.environ)
        os.environ["ARCHON_PROGRESS"] = "events"
        self.err = io.StringIO()
        enabled = progress.ENABLED
        progress.ENABLED = True            # another test's command line may have switched drawing off
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self.old), setattr(progress, "ENABLED", enabled)))

    def test_progress_is_published_as_json_lines_for_a_surface_to_draw(self):  # FR-021
        with mock.patch("sys.stderr", self.err):
            with progress.step("📥 Downloading jre 21"):
                progress.detail("1.0 of 4.0 MB", 1_000_000, 4_000_000)
            try:
                with progress.step("📦 Installing x"):
                    raise ValueError("boom")
            except ValueError:
                pass
        events = [json.loads(line) for line in self.err.getvalue().splitlines()]
        self.assertEqual([(e["state"], e["emoji"], e["label"]) for e in events],
                         [("start", "📥", "Downloading jre 21"), ("update", "📥", "Downloading jre 21"), ("done", "📥", "Downloading jre 21"),
                          ("start", "📦", "Installing x"), ("failed", "📦", "Installing x")])
        self.assertEqual((events[1]["done"], events[1]["total"], events[1]["text"]), (1_000_000, 4_000_000, "1.0 of 4.0 MB"))
        self.assertNotEqual(events[0]["step"], events[3]["step"])

    def test_an_unattended_terminal_draws_no_spinner_and_a_message_is_a_plain_line(self):
        os.environ.pop("ARCHON_PROGRESS")
        os.environ["ARCHON_ATTENDANCE"] = "unattended"
        self.assertFalse(progress.visible(Tty()))
        with mock.patch("sys.stderr", self.err):
            progress.say("📦 Installing x")
        self.assertEqual(self.err.getvalue(), "📦 Installing x\n")

    def test_an_attended_terminal_draws_and_never_in_events_mode(self):
        os.environ.pop("ARCHON_PROGRESS")
        os.environ["ARCHON_ATTENDANCE"] = "attended"
        os.environ.pop("TERM", None)
        self.assertTrue(progress.visible(Tty()))
        os.environ["ARCHON_PROGRESS"] = "events"
        self.assertFalse(progress.visible(Tty()))


class Environments(Home):
    def project(self) -> Path:
        d = self.home.parent / "proj"
        d.mkdir()
        (d / "pyproject.toml").write_text('[project]\nname = "demo-env"\nversion = "0"\nrequires-python = ">=3.12"\ndependencies = []\n'
                                          '[tool.uv]\npackage = false\n[dependency-groups]\ng = []\n')
        subprocess.run(["uv", "lock", "--quiet", "--offline"], cwd=d, check=True, capture_output=True)
        return d

    def test_a_group_gets_one_environment_per_lock_and_it_is_reused(self):  # FR-017
        d = self.project()
        py = pyenv.prepare(d, ["g"], offline=True)
        self.assertTrue(py.is_file())
        self.assertIn(str(self.home), str(py), "inside the user's cache, never in the repository")
        self.assertEqual(pyenv.prepare(d, ["g"], offline=True), py)
        self.assertFalse((d / ".venv").exists())
        self.assertEqual(sorted(p.name for p in d.iterdir()), ["pyproject.toml", "uv.lock"])

    def test_a_missing_lock_is_refused_with_exit_status_3(self):
        d = self.home.parent / "nolock"
        d.mkdir()
        (d / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0"\n')
        with self.assertRaises(pyenv.EnvError) as e:
            pyenv.prepare(d, ["g"], offline=True)
        self.assertEqual(e.exception.exit_code, 3)

    def test_the_python_floor_is_read_from_pyproject(self):
        d = self.project()
        self.assertEqual(pyenv.requires_python(d), ">=3.12")
        self.assertEqual(pyenv.requires_python(d.parent), ">=3.14")


class CommandLine(Home):
    def run_archon(self, *args, env=None, cwd=None):
        full = {**os.environ, "PYTHONPATH": str(REPO), "ARCHON_ATTENDANCE": "unattended", **(env or {})}
        return subprocess.run([sys.executable, "-m", "archon", *args], capture_output=True, text=True, env=full, cwd=cwd or REPO)

    def test_run_starts_the_module_under_the_repositorys_python_and_returns_its_status(self):  # FR-002
        repo = self.home.parent / "r"
        (repo / "tools" / "hello").mkdir(parents=True)
        (repo / "pyproject.toml").write_text('[project]\nname = "r"\nversion = "0"\nrequires-python = ">=3.12"\n')
        (repo / "tools" / "hello" / "__init__.py").write_text("")
        (repo / "tools" / "hello" / "__main__.py").write_text(
            "import sys, os, archon\nprint(sys.version_info[:2] >= (3, 12), os.environ['ARCHON_ATTENDANCE'], sys.argv[1:])\nsys.exit(7)\n")
        r = self.run_archon("run", "--repo", str(repo), "--path", "tools", "--", "hello", "--help", "x")
        self.assertEqual((r.returncode, r.stdout.strip()), (7, "True unattended ['--help', 'x']"), r.stderr)
        self.assertEqual(sorted(p.name for p in repo.iterdir()), ["pyproject.toml", "tools"], "nothing is written into the repository")

    def test_ensure_reports_json_and_exit_3_when_nothing_yields(self):  # FR-004, FR-015
        repo = self.home.parent / "r2"
        (repo / ".workspaces-host" / "toolchain.d").mkdir(parents=True)
        (repo / ".workspaces-host" / "provider.toml").write_text('name = "d"\nsummary = "x"\nlauncher = "./run"\nprotocol = 1\n')
        script(repo / "run", "exit 0\n")
        (repo / ".workspaces-host" / "toolchain.d" / "jre.toml").write_text(ENTRY.format(sha="0" * 64))
        bin = self.home.parent / "bin"
        script(bin / "java", 'echo \'openjdk version "21.0.4"\' >&2\n')
        r = self.run_archon("ensure", "--repo", str(repo), "--json", "jre", env={"PATH": f"{bin}:{os.path.dirname(sys.executable)}"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["requirements"][0]["source"], "path")
        from archon.__main__ import main
        with mock.patch.object(requirements, "ensure", side_effect=requirements.Unavailable("jre", "21", [("path", "java is not on PATH")])), \
                mock.patch("sys.stderr", io.StringIO()) as err:
            self.assertEqual(main(["ensure", "--repo", str(repo), "jre"]), 3)
        self.assertIn("jre at 21 or newer is needed", err.getvalue())

    def test_doctor_changes_nothing_and_says_the_profile(self):
        r = self.run_archon("doctor", "--repo", str(self.home))
        self.assertEqual(r.returncode, 0)
        self.assertIn("unattended (ARCHON_ATTENDANCE)", r.stdout)


if __name__ == "__main__":
    unittest.main()
