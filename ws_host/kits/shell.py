"""The `shell` kit: fish 4 and oh-my-posh (0003-kits FR-014). bash and oh-my-posh work without it; fish is the best experience."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ..core import paths
from ..core.kit import Check, Download, Kit

POSH_VERSION = "31.4.1"
POSH = Download("oh-my-posh", POSH_VERSION, "https://cdn.ohmyposh.dev/releases/v{version}/posh-linux-{goarch}",
                {"x86_64": "bfd0ccab85dc031c848b09b68226f1be942d2ce18978f94c9659b6e7e1b259af",
                 "aarch64": "9649d66f978e65dc669307546bee61b7ff45fa0621c333be85db029382f1e859"},
                binaries={"oh-my-posh": "oh-my-posh"}, kind="file")
# Ubuntu 24.04 ships fish 3.7; fish 4 comes from the fish project's own release package, fetched and verified, then unpacked
# into the person's tools directory. Debian 13 ships fish 4.0, so it uses its own package.
FISH_VERSION = "4.9.3-1~noble"
FISH_NOBLE = Download("fish", FISH_VERSION, "https://ppa.launchpadcontent.net/fish-shell/release-4/ubuntu/pool/main/f/fish/fish_{version}_{goarch}.deb",
                      {"x86_64": "09f92e3f6105fce327dea84cb025c453926e0fce1bc80c1b9d5455c1536dcef9",
                       "aarch64": "c667726aa756b3efc15b9ae526e034b02f39529b533e3ce7a45e8b990584bc65"},
                      binaries={"fish": "usr/bin/fish"}, kind="deb", steps=(("dpkg-deb", "-x", "{src}/fish.deb", "{dest}"),))


def theme_path() -> Path:
    return paths.repo_root() / "themes" / "coach.omp.json"


def fish_is_four(work: Path) -> str:
    out = subprocess.run(["fish", "--version"], capture_output=True, text=True).stdout
    major = int(out.split()[-1].split(".")[0])
    assert major >= 4, f"fish is {out.strip()}, not 4 or later"
    return out.strip()


def fish_runs(work: Path) -> str:
    p = subprocess.run(["fish", "-c", "echo (math 1 + 2) and (string upper ok)"], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0 and "3" in p.stdout and "OK" in p.stdout, f"fish could not run a command: {(p.stderr or p.stdout).strip()[-200:]}"
    return "fish runs commands"


def prompt(work: Path) -> str:
    """oh-my-posh prints a prompt with the coach theme, in both shells' initialisation."""
    theme = theme_path()
    p = subprocess.run(["oh-my-posh", "print", "primary", "--config", str(theme), "--shell", "bash"], capture_output=True, text=True, timeout=60, cwd=work)
    assert p.returncode == 0 and p.stdout.strip(), f"oh-my-posh printed no prompt: {(p.stderr or '').strip()[-200:]}"
    for shell, init in (("bash", "bash"), ("fish", "fish")):
        q = subprocess.run(["oh-my-posh", "init", init, "--config", str(theme)], capture_output=True, text=True, timeout=60)
        assert q.returncode == 0 and q.stdout.strip(), f"oh-my-posh could not set up {shell}: {(q.stderr or '').strip()[-200:]}"
    return "oh-my-posh prints the coach prompt and sets up bash and fish"


class Shell(Kit):
    name = "shell"
    summary = "fish 4 and oh-my-posh, with the coach prompt theme; bash works as well"
    plain = "a friendlier terminal: fish, which suggests and colors as you type, and oh-my-posh for the prompt."

    def apt(self, distro):
        if distro["id"] == "debian":
            return ["fish"]
        return ["libpcre2-32-0", "libpcre2-8-0", "man-db|man", "bsdextrautils", "file", "python3"]

    def downloads(self, distro):
        return [POSH] + ([] if distro["id"] == "debian" else [FISH_NOBLE])

    def checks(self, distro):
        return [Check("fish", "fish"), Check("oh-my-posh", "oh-my-posh", ("--version",)),
                Check("fish is version 4 or later", run=fish_is_four, needs=("fish",)),
                Check("fish runs commands", run=fish_runs, needs=("fish",)),
                Check("oh-my-posh prints the coach prompt", run=prompt, needs=("oh-my-posh",))]
