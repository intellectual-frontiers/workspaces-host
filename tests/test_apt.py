"""The package installer against a stand-in apt-get, apt-cache, dpkg-query and sudo on PATH."""
import json
import os
import stat
from pathlib import Path

from ws_host.install import apt
from .helpers import Home


def script(path: Path, body: str):
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class FakeApt(Home):
    def setUp(self):
        super().setUp()
        self.bin = self.home.parent / "aptbin"
        self.bin.mkdir()
        self.log = self.home.parent / "apt.log"
        self.have = self.home.parent / "have"
        self.have.write_text("coreutils\n")
        self.known = self.home.parent / "known"
        self.known.write_text("coreutils\nsed\ntexlive-luatex\nlibatk1.0-0t64\n")
        script(self.bin / "dpkg-query", f'grep -qx "$3" {self.have} && printf "install ok installed" || exit 1\n')
        script(self.bin / "apt-cache", f'grep -qx "$2" {self.known} && printf "%s:\\n  Candidate: 1.0\\n" "$2" || printf "%s:\\n  Candidate: (none)\\n" "$2"\n')
        script(self.bin / "apt-get", f'echo "apt-get $*" >> {self.log}\ncase "$1" in install) shift; for p in "$@"; do case $p in -*) ;; *) echo $p >> {self.have};; esac; done;; esac\nexit 0\n')
        script(self.bin / "sudo", f'echo "sudo $*" >> {self.log}\nif [ "$1" = -n ]; then shift; fi\nexec "$@"\n')
        os.environ["PATH"] = f"{self.bin}:{os.environ['PATH']}"
        self._euid = os.geteuid
        os.geteuid = lambda: 1000
        self.addCleanup(lambda: setattr(os, "geteuid", self._euid))

    def test_resolve_picks_the_first_available_and_reports_what_is_missing(self):
        names, missing = apt.resolve(["sed", "libatk1.0-0t64|libatk1.0-0", "nonesuch", "ruby-x|ruby-y"])
        self.assertEqual(names, ["sed", "libatk1.0-0t64"])
        self.assertEqual(missing, ["nonesuch", "ruby-x|ruby-y"])

    def test_only_missing_packages_are_installed_through_sudo_without_a_terminal_using_n(self):
        self.assertEqual(apt.to_install(["coreutils", "sed"]), ["sed"])
        apt.install(["sed"])
        log = self.log.read_text()
        self.assertIn("sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends sed", log)
        self.assertEqual(apt.to_install(["coreutils", "sed"]), [])

    def test_a_missing_sudo_is_said_not_attempted(self):
        (self.bin / "sudo").unlink()
        os.environ["PATH"] = str(self.bin) + ":/usr/bin:/bin"
        # sudo may exist in /usr/bin on this machine; hide it by naming only our directory plus tools we need
        keep = self.home.parent / "keep"
        keep.mkdir()
        for t in ("sh", "env", "grep", "cat", "echo"):
            import shutil
            if shutil.which(t, path="/usr/bin:/bin"):
                (keep / t).symlink_to(shutil.which(t, path="/usr/bin:/bin"))
        os.environ["PATH"] = f"{self.bin}:{keep}"
        self.assertIsNone(apt.sudo_prefix())
        with self.assertRaises(apt.AptError) as c:
            apt.install(["sed"])
        self.assertEqual(c.exception.code, "no-sudo")

    def test_root_does_not_use_sudo(self):
        os.geteuid = lambda: 0
        apt.install(["sed"])
        self.assertNotIn("sudo", self.log.read_text())

    def test_kit_add_says_it_will_use_sudo_before_it_runs_and_installs_what_is_missing(self):
        code, out = self.run_cmd("kit", "add", "press", "--json", "--offline")
        docs = [json.loads(l) for l in out.strip().splitlines()]
        said = [i for i, d in enumerate(docs) if d["kind"] == "progress" and "sudo" in d["data"]["plain"]]
        self.assertTrue(said)
        self.assertIn("texlive-luatex", docs[said[0]]["data"]["plain"])
        self.assertEqual(sum(l.startswith("apt-get install") for l in self.log.read_text().splitlines()), 1)
        done = [i for i, d in enumerate(docs) if d["kind"] == "progress" and d["data"]["plain"].startswith("Installed")]
        self.assertLess(said[0], done[0])   # said before it ran

    def test_a_package_the_distribution_lacks_is_reported_and_does_not_stop_the_install(self):
        code, out = self.run_cmd("kit", "add", "press", "--json", "--offline")
        docs = [json.loads(l) for l in out.strip().splitlines()]
        unavailable = [d for d in docs if d["kind"] == "progress" and "no package for" in d["data"]["plain"]]
        self.assertTrue(unavailable)
        self.assertIn("epubcheck", unavailable[0]["data"]["plain"])
        self.assertTrue(any(d["kind"] == "progress" and d["data"]["status"] == "ok" and "Installed" in d["data"]["plain"] for d in docs))

    def test_sudo_that_needs_a_password_without_a_terminal_says_what_to_run(self):
        script(self.bin / "sudo", 'echo "sudo: a password is required" >&2\nexit 1\n')
        code, out = self.run_cmd("kit", "add", "press", "--json", "--offline")
        docs = [json.loads(l) for l in out.strip().splitlines()]
        msgs = " ".join(d["data"]["plain"] for d in docs)
        self.assertIn("In a terminal, run: ws-host kit add press", msgs)
