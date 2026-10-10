"""0003-kits: the installers, with real archives and a stand-in package manager, and the kit contract."""
import hashlib
import io
import json
import os
import stat
import tarfile
import zipfile
from pathlib import Path

from ws_host.core import registry as reg
from ws_host.core.kit import Check, Download, Kit
from ws_host.install import fetch
from .helpers import REPO, Home


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def make_tar(path: Path, files: dict, top="pkg-1.0") -> Path:
    with tarfile.open(path, "w:gz") as t:
        for name, (content, mode) in files.items():
            data = content.encode()
            info = tarfile.TarInfo(f"{top}/{name}")
            info.size, info.mode = len(data), mode
            t.addfile(info, io.BytesIO(data))
    return path


def make_zip(path: Path, files: dict) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for name, (content, mode) in files.items():
            zi = zipfile.ZipInfo(name)
            zi.external_attr = (stat.S_IFREG | mode) << 16
            z.writestr(zi, content)
    return path


class Fetch(Home):
    def setUp(self):
        super().setUp()
        self.src = self.home.parent / "src"
        self.src.mkdir()
        self.a = fetch.arch()

    def dl(self, archive: Path, version="1.0", **kw):
        return Download("tool", version, archive.as_uri(), {self.a: sha(archive)}, binaries=kw.pop("binaries", {"tool": "bin/tool"}), **kw)

    def test_it_verifies_unpacks_repoints_current_and_links(self):
        tar = make_tar(self.src / "t.tar.gz", {"bin/tool": ("#!/bin/sh\necho v1\n", 0o755)})
        d = self.dl(tar)
        r = fetch.install(d)
        self.assertEqual(r["outcome"], "installed")
        link = self.paths.tools_dir() / "tool" / "current"
        self.assertEqual(os.readlink(link), "1.0")
        exe = self.paths.bin_dir() / "tool"
        self.assertTrue(exe.is_symlink())
        self.assertEqual(os.popen(str(exe)).read().strip(), "v1")

    def test_a_wrong_checksum_installs_nothing_and_unpacks_nothing(self):
        tar = make_tar(self.src / "t.tar.gz", {"bin/tool": ("x", 0o755)})
        d = Download("tool", "1.0", tar.as_uri(), {self.a: "0" * 64}, binaries={"tool": "bin/tool"})
        with self.assertRaises(fetch.FetchError) as c:
            fetch.install(d)
        self.assertEqual(c.exception.code, "checksum")
        self.assertIn("nothing was installed", c.exception.message)
        self.assertFalse((self.paths.tools_dir() / "tool").exists())
        self.assertFalse(os.path.lexists(self.paths.bin_dir() / "tool"))
        self.assertEqual(list((self.paths.cache_dir() / "downloads").glob("*")), [])

    def test_a_second_install_changes_nothing_and_an_old_version_stays(self):
        v1 = make_tar(self.src / "v1.tar.gz", {"bin/tool": ("#!/bin/sh\necho v1\n", 0o755)})
        v2 = make_tar(self.src / "v2.tar.gz", {"bin/tool": ("#!/bin/sh\necho v2\n", 0o755)})
        fetch.install(self.dl(v1, "1.0"))
        self.assertEqual(fetch.install(self.dl(v1, "1.0"))["outcome"], "present")
        fetch.install(self.dl(v2, "2.0"))
        base = self.paths.tools_dir() / "tool"
        self.assertEqual(os.readlink(base / "current"), "2.0")
        self.assertTrue((base / "1.0" / "bin" / "tool").exists())
        self.assertEqual(os.popen(str(self.paths.bin_dir() / "tool")).read().strip(), "v2")

    def test_a_failed_download_leaves_the_previous_version_current(self):
        v1 = make_tar(self.src / "v1.tar.gz", {"bin/tool": ("#!/bin/sh\necho v1\n", 0o755)})
        fetch.install(self.dl(v1, "1.0"))
        bad = Download("tool", "2.0", (self.src / "gone.tar.gz").as_uri(), {self.a: "a" * 64}, binaries={"tool": "bin/tool"})
        with self.assertRaises(fetch.FetchError):
            fetch.install(bad)
        self.assertEqual(os.readlink(self.paths.tools_dir() / "tool" / "current"), "1.0")
        self.assertEqual(os.popen(str(self.paths.bin_dir() / "tool")).read().strip(), "v1")
        self.assertFalse((self.paths.tools_dir() / "tool" / "2.0").exists())

    def test_a_zip_keeps_the_executable_bit(self):
        z = make_zip(self.src / "t.zip", {"tool": ("#!/bin/sh\necho z\n", 0o755)})
        d = Download("zt", "1.0", z.as_uri(), {self.a: sha(z)}, binaries={"zt": "tool"}, kind="zip")
        fetch.install(d)
        self.assertEqual(os.popen(str(self.paths.bin_dir() / "zt")).read().strip(), "z")

    def test_install_steps_run_in_the_unpacked_source_into_the_destination(self):
        tar = make_tar(self.src / "i.tar.gz", {"install.sh": ('#!/bin/sh\nfor a in "$@"; do case $a in --prefix=*) p=${a#--prefix=};; esac; done\n'
                                                            'mkdir -p "$p/bin" && printf "#!/bin/sh\\necho built\\n" > "$p/bin/tool" && chmod +x "$p/bin/tool"\n', 0o755)})
        d = Download("tool", "1.0", tar.as_uri(), {self.a: sha(tar)}, binaries={"tool": "bin/tool"}, steps=(("sh", "install.sh", "--prefix={dest}"),))
        fetch.install(d)
        self.assertEqual(os.popen(str(self.paths.bin_dir() / "tool")).read().strip(), "built")
        self.assertFalse((self.paths.tools_dir() / "tool" / "1.0.src").exists())

    def test_a_failing_install_step_leaves_nothing(self):
        tar = make_tar(self.src / "i.tar.gz", {"install.sh": ("#!/bin/sh\nexit 1\n", 0o755)})
        d = Download("tool", "1.0", tar.as_uri(), {self.a: sha(tar)}, binaries={"tool": "bin/tool"}, steps=(("sh", "install.sh"),))
        with self.assertRaises(fetch.FetchError):
            fetch.install(d)
        self.assertEqual(sorted(p.name for p in (self.paths.tools_dir() / "tool").iterdir()), [])

    def test_offline_fetches_nothing(self):
        tar = make_tar(self.src / "t.tar.gz", {"bin/tool": ("x", 0o755)})
        with self.assertRaises(fetch.FetchError) as c:
            fetch.install(self.dl(tar), offline=True)
        self.assertEqual(c.exception.code, "offline")

    def test_an_unsupported_architecture_is_said_plainly(self):
        d = Download("tool", "1.0", "file:///x", {"riscv64": "0" * 64})
        with self.assertRaises(fetch.FetchError) as c:
            fetch.install(d)
        self.assertEqual(c.exception.code, "unsupported-arch")

    def test_an_archive_cannot_escape_its_folder(self):
        evil = self.src / "e.tar.gz"
        with tarfile.open(evil, "w:gz") as t:
            info = tarfile.TarInfo("pkg/../../escape.txt")
            info.size = 1
            t.addfile(info, io.BytesIO(b"x"))
        d = Download("tool", "1.0", evil.as_uri(), {self.a: sha(evil)})
        with self.assertRaises(fetch.FetchError):
            fetch.install(d)
        self.assertFalse((self.paths.tools_dir() / "escape.txt").exists())

    def test_link_program_links_fd_to_fdfind_without_overwriting(self):
        fake = self.home / "bin"
        fake.mkdir()
        (fake / "fdfind").write_text("#!/bin/sh\n")
        (fake / "fdfind").chmod(0o755)
        os.environ["PATH"] = f"{fake}:{os.environ['PATH']}"
        self.assertTrue(fetch.link_program("fd", "fdfind"))
        self.assertEqual(os.readlink(self.paths.bin_dir() / "fd"), str(fake / "fdfind"))
        (self.paths.bin_dir() / "mine").write_text("mine")
        self.assertTrue(fetch.link_program("mine", "fdfind"))
        self.assertEqual((self.paths.bin_dir() / "mine").read_text(), "mine")


class Contract(Home):
    def test_kits_are_found_by_presence_with_unique_names(self):
        r = reg.discover()
        self.assertEqual(sorted(r.kits), ["aws", "azure", "base", "cloud", "cloudflare", "embedded-sql", "microsoft", "modern-cli", "press", "railway", "rust", "shell"])
        self.assertEqual(r.conflicts, [])
        for name, cls in r.kits.items():
            self.assertTrue(issubclass(cls, Kit))
            self.assertEqual(cls.name, name)
            self.assertTrue(cls.plain.endswith("."), name)

    def test_every_download_has_a_checksum_per_architecture_it_claims_and_a_real_url(self):
        from ws_host.core import machine
        for name, cls in reg.discover().kits.items():
            for distro in ({"id": "debian", "codename": "trixie", "id_like": ""}, {"id": "ubuntu", "codename": "noble", "id_like": "debian"}):
                for dl in cls().downloads(distro):
                    if dl.__class__.__name__ == "Floating":          # these float with the newest release and are checked against the publisher's own word (0003 FR-017)
                        continue
                    self.assertTrue(dl.sha256, dl.name)
                    for arch, h in dl.sha256.items():
                        self.assertRegex(h, r"^[0-9a-f]{64}$", f"{dl.name} {arch}")
                        url = dl.url_for(arch)
                        self.assertTrue(url.startswith("https://"), url)
                        self.assertNotIn("{", url)

    def test_checks_name_programs_or_a_functional_run(self):
        for cls in reg.discover().kits.values():
            checks = cls().checks({"id": "debian", "codename": "trixie", "id_like": ""})
            self.assertTrue(any(c.program for c in checks))
            for c in checks:
                self.assertTrue(c.program or c.run, c.name)

    def test_base_covers_the_userland_and_the_tools_the_brief_names(self):
        progs = {c.program for c in reg.discover().kits["base"]().checks({"id": "debian", "codename": "trixie", "id_like": ""}) if c.program}
        for p in "sed find xargs diff cmp patch tar gzip unzip zip bzip2 xz file less which ps hostname tput rsync bc grep awk git gh glab jq rg fd curl python3 uv node cwebp dwebp sqlite3 duckdb shellcheck chromium".split():
            self.assertIn(p, progs)

    def test_rust_is_fetched_not_rustup_and_is_at_least_1_87(self):
        from ws_host.kits import rust
        self.assertGreaterEqual(tuple(map(int, rust.RUST_VERSION.split(".")[:2])), rust.MINIMUM)
        self.assertEqual(rust.MINIMUM, (1, 87))
        kit = rust.Rust()
        self.assertNotIn("rustup", " ".join(kit.apt({"id": "debian"})))
        self.assertTrue(kit.downloads({"id": "debian"}))

    def test_press_installs_the_named_texlive_packages(self):
        apt = reg.discover().kits["press"]().apt({"id": "debian"})
        for p in ("texlive-luatex", "texlive-xetex", "texlive-latex-extra", "texlive-fonts-recommended", "texlive-science", "latexmk",
                  "poppler-utils", "qpdf", "librsvg2-bin", "default-jre-headless", "epubcheck", "asciidoctor"):
            self.assertIn(p, apt)

    def test_the_ubuntu_chromium_is_fetched_and_debians_comes_from_apt(self):
        base = reg.discover().kits["base"]()
        deb = {"id": "debian", "codename": "trixie", "id_like": ""}
        ubu = {"id": "ubuntu", "codename": "noble", "id_like": "debian"}
        self.assertIn("chromium", base.apt(deb))
        self.assertNotIn("chromium", base.apt(ubu))
        self.assertIn("chrome-for-testing", [d.name for d in base.downloads(ubu)])
        self.assertNotIn("chrome-for-testing", [d.name for d in base.downloads(deb)])


class Commands(Home):
    def test_list_show_and_an_unknown_kit(self):
        code, doc = self.run_json("kit", "list")
        self.assertEqual(code, 0)
        self.assertEqual({k["name"] for k in doc["data"]["kits"]}, {"aws", "azure", "base", "cloud", "cloudflare", "embedded-sql", "microsoft", "modern-cli", "press", "railway", "rust", "shell"})
        code, doc = self.run_json("kit", "show", "rust")
        self.assertEqual(code, 0)
        self.assertEqual(doc["data"]["downloads"][0]["name"], "rust")
        code, doc = self.run_json("kit", "show", "nope")
        self.assertEqual(code, 2)

    def test_actions_print_as_pasteable_lines(self):
        _, doc = self.run_json("kit", "show", "press")
        self.assertEqual(doc["actions"][0]["cli"], "ws-host kit add press")

    def test_kit_add_is_setup_cli_only_and_never_mcp(self):
        c = reg.discover().get(("kit", "add"))
        self.assertEqual((c.category, c.surfaces), ("setup", ("cli",)))

    def test_dry_run_installs_nothing_and_says_whether_it_needs_sudo(self):
        code, out = self.run_cmd("kit", "add", "rust", "--dry-run", "--json")
        self.assertEqual(code, 0)
        doc = json.loads(out.strip().splitlines()[-1])
        self.assertIn("uses_sudo", doc["data"])
        self.assertFalse(self.paths_exist())

    def paths_exist(self):
        from ws_host.core import paths
        return paths.tools_dir().exists()

    def test_offline_with_a_download_needed_is_exit_3_naming_it(self):
        from ws_host.core import machine
        import shutil
        os.environ["PATH"] = os.pathsep.join(p for p in os.environ["PATH"].split(os.pathsep) if ".cargo" not in p and ".local" not in p)
        code, out = self.run_cmd("kit", "add", "rust", "--offline", "--json")
        docs = [json.loads(l) for l in out.strip().splitlines()]
        steps = {s["name"]: s for s in docs[-1]["data"]["steps"]}
        self.assertEqual(steps["download rust"]["status"], "missing")
        self.assertIn("offline", steps["download rust"]["plain"])
        self.assertEqual(code, 3)


class ShellKit(Home):
    def test_the_shell_kit_provides_fish_4_and_oh_my_posh_and_both_prompt_themes(self):
        from ws_host.kits import shell
        kit = reg.discover().kits["shell"]()
        deb = {"id": "debian", "codename": "trixie", "id_like": ""}
        ubu = {"id": "ubuntu", "codename": "noble", "id_like": "debian"}
        self.assertEqual(kit.apt(deb), ["fish"])                                   # Debian 13 ships fish 4.0
        self.assertEqual([d.name for d in kit.downloads(deb)], ["oh-my-posh"])
        self.assertEqual([d.name for d in kit.downloads(ubu)], ["oh-my-posh", "fish"])   # Ubuntu 24.04 ships 3.7: fish 4 is fetched
        fish = kit.downloads(ubu)[1]
        self.assertEqual(fish.kind, "deb")
        self.assertEqual(fish.steps[0][0], "dpkg-deb")
        self.assertTrue(shell.theme_path().is_file())
        self.assertTrue(shell.theme_path(shell.PLAIN).is_file())
        self.assertEqual({c.program for c in kit.checks(deb) if c.program}, {"fish", "oh-my-posh"})
        self.assertGreaterEqual(len([c for c in kit.checks(deb) if c.run]), 3)

    def test_a_deb_download_is_unpacked_by_its_step_into_the_versioned_directory(self):
        tool = self.home.parent / "bin"
        tool.mkdir()
        (tool / "dpkg-deb").write_text('#!/bin/sh\nmkdir -p "$3/usr/bin" && printf "#!/bin/sh\\necho fish, version 4.9.3\\n" > "$3/usr/bin/fish" && chmod +x "$3/usr/bin/fish"\n')
        (tool / "dpkg-deb").chmod(0o755)
        os.environ["PATH"] = f"{tool}:{os.environ['PATH']}"
        src = self.home.parent / "src"
        src.mkdir()
        deb = src / "fish.deb"
        deb.write_bytes(b"not really a deb")
        a = fetch.arch()
        d = Download("fish", "4.9.3", deb.as_uri(), {a: sha(deb)}, binaries={"fish": "usr/bin/fish"}, kind="deb", steps=(("dpkg-deb", "-x", "{src}/fish.deb", "{dest}"),))
        fetch.install(d)
        self.assertEqual(os.popen(str(self.paths.bin_dir() / "fish")).read().strip(), "fish, version 4.9.3")

    def test_a_single_downloaded_program_is_executable(self):
        src = self.home.parent / "src"
        src.mkdir()
        f = src / "posh"
        f.write_text("#!/bin/sh\necho 31\n")
        f.chmod(0o644)
        a = fetch.arch()
        fetch.install(Download("posh", "1", f.as_uri(), {a: sha(f)}, binaries={"posh": "posh"}, kind="file"))
        self.assertEqual(os.popen(str(self.paths.bin_dir() / "posh")).read().strip(), "31")

    def test_nothing_in_ws_host_changes_a_login_shell_or_shell_files(self):
        text = "".join(p.read_text() for p in (REPO / "ws_host").rglob("*.py"))
        for needle in ("chsh", ".bashrc", "config.fish", "/etc/shells"):
            for p in (REPO / "ws_host").rglob("*.py"):
                if "help" in p.parts or p.name == "shell.py" and p.parent.name == "commands":   # `shell add` is the one command that edits one (0003 FR-015)
                    continue
                self.assertNotIn(needle, p.read_text(), f"{needle} in {p}")
