"""Tools that float with their newest release (0003-kits FR-017), against stand-in publishers: GitHub's releases, the npm registry, PyPI and a signed download."""
import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from ws_host.core import paths
from ws_host.core.kit import Floating, Resolved
from ws_host.install import fetch, floating
from .helpers import Home


def tarball(name: str, body: str) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        data = body.encode()
        info = tarfile.TarInfo(name)
        info.size, info.mode = len(data), 0o755
        t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class Publisher:
    """One local server standing for GitHub, npm and PyPI at once: what it answers is set by the test."""

    def __init__(self):
        self.routes: dict[str, bytes] = {}
        self.hits: list[str] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                outer.hits.append(self.path)
                body = outer.routes.get(self.path)
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def release(self, repo: str, tag: str, assets: dict[str, bytes], digest=True):
        listed = []
        for name, data in assets.items():
            self.routes[f"/files/{repo}/{tag}/{name}"] = data
            a = {"name": name, "browser_download_url": f"{self.url}/files/{repo}/{tag}/{name}"}
            if digest is True:
                a["digest"] = "sha256:" + hashlib.sha256(data).hexdigest()
            elif digest:
                a["digest"] = digest
            listed.append(a)
        self.routes[f"/repos/{repo}/releases/latest"] = json.dumps({"tag_name": tag, "assets": listed}).encode()

    def stop(self):
        self.server.shutdown()


class Floats(Home):
    def setUp(self):
        super().setUp()
        self.pub = Publisher()
        self.addCleanup(self.pub.stop)
        os.environ["WS_HOST_GITHUB_API"] = self.pub.url
        os.environ["GH_TOKEN"] = "not-a-real-token"

    def tool(self, **kw):
        a = fetch.arch()
        return Floating("fake", floating.github("acme/fake", {a: r"^fake-linux\.tar\.gz$"}), binaries={"fake": "fake"}, kind="tar", strip=0, **kw)

    def version_of(self):
        p = subprocess.run([str(paths.bin_dir() / "fake")], capture_output=True, text=True)
        return p.stdout.strip()

    def test_the_newest_release_is_installed_when_the_publishers_checksum_matches_and_a_newer_one_replaces_it(self):
        self.pub.release("acme/fake", "v1.0.0", {"fake-linux.tar.gz": tarball("fake", "#!/bin/sh\necho 1.0.0\n")})
        f = self.tool()
        r = floating.install(f, False, True)
        self.assertEqual((r["outcome"], r["version"]), ("installed", "1.0.0"))
        self.assertEqual(self.version_of(), "1.0.0")
        self.pub.release("acme/fake", "v1.1.0", {"fake-linux.tar.gz": tarball("fake", "#!/bin/sh\necho 1.1.0\n")})
        r = floating.install(f, False, True)
        self.assertEqual((r["outcome"], r["version"], r["previous"]), ("updated", "1.1.0", "1.0.0"))
        self.assertEqual(self.version_of(), "1.1.0")
        self.assertTrue((paths.tools_dir() / "fake" / "1.0.0").is_dir(), "the one before it is kept, so that a bad release can be left behind")

    def test_a_file_that_does_not_match_the_publishers_checksum_installs_nothing(self):
        self.pub.release("acme/fake", "v1.0.0", {"fake-linux.tar.gz": tarball("fake", "#!/bin/sh\necho evil\n")}, digest="sha256:" + "0" * 64)
        with self.assertRaises(fetch.FetchError) as c:
            floating.install(self.tool(), False, True)
        self.assertEqual(c.exception.code, "checksum")
        self.assertFalse((paths.bin_dir() / "fake").exists())
        self.assertFalse((paths.tools_dir() / "fake" / "1.0.0").exists())

    def test_a_release_with_no_checksum_anywhere_is_refused(self):
        self.pub.release("acme/fake", "v1.0.0", {"fake-linux.tar.gz": tarball("fake", "#!/bin/sh\necho 1\n")}, digest=False)
        with self.assertRaises(fetch.FetchError) as c:
            floating.install(self.tool(), False, True)
        self.assertEqual(c.exception.code, "no-checksum")

    def test_a_checksum_file_beside_the_release_is_used_when_the_asset_has_no_digest(self):
        data = tarball("fake", "#!/bin/sh\necho 2.0.0\n")
        self.pub.release("acme/fake", "2.0.0", {"fake-linux.tar.gz": data, "checksums.txt": (hashlib.sha256(data).hexdigest() + "  fake-linux.tar.gz\n").encode()}, digest=False)
        self.assertEqual(floating.install(self.tool(), False, True)["version"], "2.0.0")
        self.assertEqual(self.version_of(), "2.0.0")

    def test_the_version_is_found_in_whatever_the_tag_looks_like(self):
        self.pub.release("acme/fake", "azure-dev-cli_1.23.0", {"fake-linux.tar.gz": tarball("fake", "#!/bin/sh\necho 1.23.0\n")})
        self.assertEqual(floating.install(self.tool(), False, True)["version"], "1.23.0")

    def test_what_is_installed_is_not_looked_into_unless_a_look_is_asked_for(self):
        self.pub.release("acme/fake", "v1.0.0", {"fake-linux.tar.gz": tarball("fake", "#!/bin/sh\necho 1.0.0\n")})
        f = self.tool()
        floating.install(f, False, True)
        asked = len(self.pub.hits)
        self.pub.release("acme/fake", "v1.1.0", {"fake-linux.tar.gz": tarball("fake", "#!/bin/sh\necho 1.1.0\n")})
        self.assertEqual(floating.install(f, False)["outcome"], "present", "an ordinary install or update leaves it alone, so that it stays quick")
        self.assertEqual(self.version_of(), "1.0.0")
        self.assertEqual(len(self.pub.hits), asked, "and asks nobody")
        with floating.looking_fresh():
            self.assertEqual(floating.install(f, False)["outcome"], "updated")
        self.assertEqual(self.version_of(), "1.1.0")

    def test_when_the_publisher_cannot_be_reached_what_is_installed_is_kept_and_nothing_fails(self):
        self.pub.release("acme/fake", "v1.0.0", {"fake-linux.tar.gz": tarball("fake", "#!/bin/sh\necho 1.0.0\n")})
        f = self.tool()
        floating.install(f, False, True)
        os.environ["WS_HOST_GITHUB_API"] = "http://127.0.0.1:9"
        r = floating.install(f, False, True)
        self.assertEqual((r["outcome"], r["version"]), ("present", "1.0.0"))
        self.assertIn("what is installed is kept", r["note"])
        self.assertEqual(self.version_of(), "1.0.0")

    def test_offline_installs_nothing_new_and_leaves_what_is_there(self):
        with self.assertRaises(fetch.FetchError) as c:
            floating.install(self.tool(), True, True)
        self.assertEqual(c.exception.code, "offline")
        self.pub.release("acme/fake", "v1.0.0", {"fake-linux.tar.gz": tarball("fake", "#!/bin/sh\necho 1.0.0\n")})
        f = self.tool()
        floating.install(f, False, True)
        self.assertEqual(floating.install(f, True, True)["outcome"], "present")

    def test_only_the_last_two_versions_are_kept(self):
        f = self.tool()
        for v in ("1.0.0", "1.1.0", "1.2.0"):
            self.pub.release("acme/fake", f"v{v}", {"fake-linux.tar.gz": tarball("fake", f"#!/bin/sh\necho {v}\n")})
            floating.install(f, False, True)
            os.utime(paths.tools_dir() / "fake" / v, None)
        kept = sorted(p.name for p in (paths.tools_dir() / "fake").iterdir() if p.is_dir() and not p.is_symlink())
        self.assertEqual(kept, ["1.1.0", "1.2.0"])


class Resolvers(Home):
    def setUp(self):
        super().setUp()
        self.pub = Publisher()
        self.addCleanup(self.pub.stop)

    def test_npm_and_pypi_name_the_newest_version_and_the_registrys_integrity(self):
        os.environ["WS_HOST_NPM_REGISTRY"] = self.pub.url
        os.environ["WS_HOST_PYPI"] = self.pub.url
        self.pub.routes["/wrangler/latest"] = json.dumps({"version": "9.9.9", "dist": {"integrity": "sha512-abc"}}).encode()
        self.pub.routes["/pypi/azure-cli/json"] = json.dumps({"info": {"version": "8.8.8"}}).encode()
        n = floating.npm("wrangler")("x86_64")
        self.assertEqual((n.version, n.integrity), ("9.9.9", "sha512-abc"))
        self.assertEqual(floating.pypi("azure-cli")("x86_64").version, "8.8.8")

    def test_the_aws_cli_version_comes_from_its_changelog_and_the_zip_and_signature_are_named_from_it(self):
        os.environ["WS_HOST_AWS_CLI_CHANGELOG"] = self.pub.url + "/CHANGELOG.rst"
        os.environ["WS_HOST_AWS_CLI_URL"] = self.pub.url
        self.pub.routes["/CHANGELOG.rst"] = b"=========\nCHANGELOG\n=========\n\n2.37.12\n=======\n\n* x\n\n2.37.11\n=======\n"
        r = floating.aws_cli("aarch64")
        self.assertEqual(r.version, "2.37.12")
        self.assertEqual((r.url, r.signature_url), (self.pub.url + "/awscli-exe-linux-aarch64-2.37.12.zip", self.pub.url + "/awscli-exe-linux-aarch64-2.37.12.zip.sig"))
        self.assertEqual(r.fingerprint, "FB5DB77FD5C118B80511ADA8A6310ACC4672475C")

    def test_the_key_shipped_for_aws_is_the_one_aws_publishes(self):
        shown = subprocess.run(["gpg", "--batch", "--with-colons", "--show-keys", str(floating.AWS_KEY)], capture_output=True, text=True).stdout
        self.assertIn(floating.AWS_FINGERPRINT, shown)


class Signed(Home):
    """A download proved by a detached signature from the publisher's key."""

    def setUp(self):
        super().setUp()
        if not shutil.which("gpg"):
            self.skipTest("gpg is not installed")
        self.gpg = self.home.parent / "gnupg"
        self.gpg.mkdir(mode=0o700)
        self.env = {**os.environ, "GNUPGHOME": str(self.gpg)}
        subprocess.run(["gpg", "--batch", "--passphrase", "", "--quick-generate-key", "Test Publisher <p@example.com>", "rsa2048", "sign", "1d"], env=self.env, capture_output=True, check=True)
        out = subprocess.run(["gpg", "--batch", "--with-colons", "--list-keys"], env=self.env, capture_output=True, text=True).stdout
        self.fpr = next(l.split(":")[9] for l in out.splitlines() if l.startswith("fpr"))
        self.key = self.home.parent / "pub.asc"
        self.key.write_bytes(subprocess.run(["gpg", "--armor", "--export", self.fpr], env=self.env, capture_output=True).stdout)
        self.file = self.home.parent / "tool.zip"
        self.file.write_bytes(b"the tool")
        self.sig = self.home.parent / "tool.zip.sig"
        subprocess.run(["gpg", "--batch", "--detach-sign", "-o", str(self.sig), str(self.file)], env=self.env, capture_output=True, check=True)

    def test_a_good_signature_from_the_known_key_passes(self):
        floating.verify_signature(self.file, self.sig, self.key, self.fpr)

    def test_a_changed_file_fails(self):
        self.file.write_bytes(b"the tool, changed")
        with self.assertRaises(fetch.FetchError) as c:
            floating.verify_signature(self.file, self.sig, self.key, self.fpr)
        self.assertEqual(c.exception.code, "bad-signature")

    def test_a_key_that_is_not_the_one_the_tool_is_known_by_fails(self):
        with self.assertRaises(fetch.FetchError) as c:
            floating.verify_signature(self.file, self.sig, self.key, "0" * 40)
        self.assertEqual(c.exception.code, "wrong-key")

    def test_a_signed_download_installs_by_the_checksum_of_the_file_that_was_proved(self):
        self.pub = Publisher()
        self.addCleanup(self.pub.stop)
        data = tarball("signedtool", "#!/bin/sh\necho signed\n")
        (self.home.parent / "t.tar.gz").write_bytes(data)
        subprocess.run(["gpg", "--batch", "--detach-sign", "-o", str(self.home.parent / "t.tar.gz.sig"), str(self.home.parent / "t.tar.gz")], env=self.env, capture_output=True, check=True)
        self.pub.routes["/t.tar.gz"] = data
        self.pub.routes["/t.tar.gz.sig"] = (self.home.parent / "t.tar.gz.sig").read_bytes()
        key, fpr, url = str(self.key), self.fpr, self.pub.url

        def resolve(arch):
            return Resolved(version="3.0.0", url=url + "/t.tar.gz", signature_url=url + "/t.tar.gz.sig", key=key, fingerprint=fpr)
        f = Floating("signedtool", resolve, binaries={"signedtool": "signedtool"}, kind="tar", strip=0)
        self.assertEqual(floating.install(f, False, True)["version"], "3.0.0")
        self.assertEqual(subprocess.run([str(paths.bin_dir() / "signedtool")], capture_output=True, text=True).stdout.strip(), "signed")
        self.pub.routes["/t.tar.gz"] = b"tampered"                      # the same name, other bytes: a new version is looked for and refused
        shutil.rmtree(paths.cache_dir() / "downloads")
        def resolve2(arch):
            return Resolved(version="3.0.1", url=url + "/t.tar.gz", signature_url=url + "/t.tar.gz.sig", key=key, fingerprint=fpr)
        f2 = Floating("signedtool", resolve2, binaries={"signedtool": "signedtool"}, kind="tar", strip=0)
        with self.assertRaises(fetch.FetchError):
            floating.install(f2, False, True)
        self.assertEqual(floating.installed_version(f2), "3.0.0")


class CloudKits(Home):
    """The four cloud kits and the one that holds them all."""

    def test_the_four_kits_and_the_cloud_kit_are_there_and_the_cloud_kit_is_exactly_their_programs(self):
        from ws_host.core import registry as reg
        kits = reg.discover().kits
        for n in ("aws", "azure", "cloudflare", "railway", "cloud", "modern-cli"):
            self.assertIn(n, kits)
        names = lambda k: [d.name for d in kits[k]().downloads({})]
        self.assertEqual(names("aws"), ["aws-cli", "aws-sam-cli", "aws-cdk"])
        self.assertEqual(names("azure"), ["azure-cli", "azure-dev"])
        self.assertEqual(names("cloudflare"), ["wrangler", "cloudflared"])
        self.assertEqual(names("railway"), ["railway"])
        self.assertEqual(names("cloud"), names("aws") + names("azure") + names("cloudflare") + names("railway"))
        programs = [c.program for c in kits["cloud"]().checks({})]
        self.assertEqual(programs, ["aws", "sam", "cdk", "az", "azd", "wrangler", "cloudflared", "railway"])

    def test_every_tool_floats_and_none_carries_a_version_or_a_checksum_of_its_own(self):
        from ws_host.core import registry as reg
        for d in reg.discover().kits["cloud"]().downloads({}):
            self.assertIsInstance(d, Floating, d.name)
            self.assertEqual((d.version, d.sha256), ("latest", {}), d.name)
            self.assertTrue(d.supports("x86_64") and d.supports("aarch64"), d.name)

    def test_kit_show_says_what_would_be_installed_without_asking_anyone(self):
        code, doc = self.run_json("kit", "show", "cloud")
        self.assertEqual(code, 0)
        self.assertEqual(len(doc["data"]["downloads"]), 8)
        self.assertIn("gnupg", doc["data"]["packages"], "gpg checks AWS's signature")

    def test_the_packages_that_come_from_a_registry_are_the_ones_with_a_manager(self):
        from ws_host.core import registry as reg
        managed = {d.name: d.manager for d in reg.discover().kits["cloud"]().downloads({}) if d.manager}
        self.assertEqual(managed, {"aws-cdk": "npm", "azure-cli": "pip", "wrangler": "npm"})


class Refresh(Home):
    """`kit sync` and `ws-host update --tools` keep what floats current, whichever kit put it there; an ordinary update does not."""

    def setUp(self):
        super().setUp()
        root = paths.tools_dir() / "wrangler"
        (root / "1").mkdir(parents=True)
        os.symlink("1", root / "current")

    def test_an_installed_floating_tool_is_looked_at_and_one_never_installed_is_not(self):
        from unittest import mock
        from ws_host.lib import kitrun
        seen = []

        def fake_install(d, offline=False):
            seen.append((d.name, floating._FRESH))
            return {"outcome": "updated", "version": "2", "previous": "1"}
        ctx = type("C", (), {"offline": False})()
        with mock.patch.object(fetch, "install", fake_install):
            r = kitrun.refresh_installed(ctx)
        self.assertEqual(seen, [("wrangler", True)], "asked to look, and only about what is installed")
        self.assertEqual(r["tools"], 1)
        self.assertIn("updated wrangler 1 to 2", r["plain"])

    def test_with_nothing_floating_installed_it_says_so_and_asks_nobody(self):
        shutil.rmtree(paths.tools_dir() / "wrangler")
        from ws_host.lib import kitrun
        r = kitrun.refresh_installed(type("C", (), {"offline": False})())
        self.assertEqual(r["tools"], 0)

    def test_kit_sync_can_be_for_one_kit(self):
        from unittest import mock
        from ws_host.lib import kitrun
        seen = []
        with mock.patch.object(fetch, "install", lambda d, offline=False: seen.append(d.name) or {"outcome": "present", "version": "1", "previous": ""}):
            kitrun.refresh_installed(type("C", (), {"offline": False})(), "aws")
            self.assertEqual(seen, [], "wrangler belongs to the cloudflare kit, not aws")
            kitrun.refresh_installed(type("C", (), {"offline": False})(), "cloud")
        self.assertEqual(seen, ["wrangler"])

    def test_the_command_exists_and_names_an_unknown_kit(self):
        code, doc = self.run_json("kit", "sync", "nope")
        self.assertEqual(code, 2)
        code, doc = self.run_json("kit", "sync", "--offline")
        self.assertEqual(code, 0, doc)


def zipball(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, body in files.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = 0o755 << 16
            z.writestr(info, body)
    return buf.getvalue()


class Chosen(Home):
    """A release file chosen by its name, and its programs found wherever the archive put them."""

    def setUp(self):
        super().setUp()
        self.pub = Publisher()
        self.addCleanup(self.pub.stop)
        os.environ["WS_HOST_GITHUB_API"] = self.pub.url
        os.environ["GH_TOKEN"] = "not-a-real-token"

    def test_the_file_for_linux_on_this_machine_is_chosen_by_its_name_from_what_real_projects_publish(self):
        pick = floating.pick_asset
        bat = ["bat-v0.25.0-x86_64-unknown-linux-gnu.tar.gz", "bat-v0.25.0-x86_64-unknown-linux-musl.tar.gz", "bat-v0.25.0-aarch64-unknown-linux-gnu.tar.gz", "bat_0.25.0_amd64.deb",
               "bat-v0.25.0-x86_64-apple-darwin.tar.gz", "bat-v0.25.0-x86_64-pc-windows-msvc.zip", "sha256sums.txt", "bat-v0.25.0-arm-unknown-linux-gnueabihf.tar.gz"]
        self.assertEqual(pick(bat, "x86_64"), "bat-v0.25.0-x86_64-unknown-linux-musl.tar.gz", "a static build is preferred")
        self.assertEqual(pick(bat, "aarch64"), "bat-v0.25.0-aarch64-unknown-linux-gnu.tar.gz")
        self.assertEqual(pick(["tealdeer-linux-x86_64-musl", "tealdeer-linux-x86_64-musl.sha256", "tealdeer-macos-x86_64"], "x86_64"), "tealdeer-linux-x86_64-musl", "a plain program")
        self.assertEqual(pick(["btop-x86_64-linux-musl.tbz", "btop-aarch64-linux-musl.tbz", "btop-x86_64-linux-musl.tbz.sha256"], "x86_64"), "btop-x86_64-linux-musl.tbz")
        self.assertEqual(pick(["procs-v0.14.10-x86_64-linux.zip", "procs-v0.14.10-aarch64-linux.zip", "procs-v0.14.10-x86_64-mac.zip"], "aarch64"), "procs-v0.14.10-aarch64-linux.zip")
        self.assertEqual(pick(["cloudflared-linux-amd64", "cloudflared-linux-amd64.deb", "cloudflared-linux-amd64.rpm", "cloudflared-linux-arm64"], "x86_64"), "cloudflared-linux-amd64")
        self.assertIsNone(pick(["tool-darwin-amd64.tar.gz", "tool-windows-amd64.zip"], "x86_64"), "nothing fits: it refuses rather than guess")

    def tool(self, binaries):
        return Floating("chosen", floating.github_auto("acme/chosen"), binaries=binaries, auto=True)

    def arch_words(self):
        return "x86_64" if fetch.arch() == "x86_64" else "aarch64"

    def test_a_program_in_a_folder_of_an_archive_is_found_and_linked(self):
        a = self.arch_words()
        data = tarball(f"chosen-1.2.3-{a}-unknown-linux-musl/chosen", "#!/bin/sh\necho chosen 1.2.3\n")
        self.pub.release("acme/chosen", "v1.2.3", {f"chosen-1.2.3-{a}-unknown-linux-musl.tar.gz": data, "chosen-1.2.3-x86_64-apple-darwin.tar.gz": b"no"})
        r = floating.install(self.tool({"chosen": "chosen"}), False, True)
        self.assertEqual((r["outcome"], r["version"]), ("installed", "1.2.3"))
        self.assertEqual(subprocess.run([str(paths.bin_dir() / "chosen")], capture_output=True, text=True).stdout.strip(), "chosen 1.2.3")

    def test_a_single_downloaded_program_is_kept_under_the_name_it_is_linked_by(self):
        a = "amd64" if fetch.arch() == "x86_64" else "arm64"
        self.pub.release("acme/chosen", "v2.0.0", {f"chosen-linux-{a}": b"#!/bin/sh\necho chosen 2\n"})
        floating.install(self.tool({"chosen": "chosen"}), False, True)
        self.assertEqual(subprocess.run([str(paths.bin_dir() / "chosen")], capture_output=True, text=True).stdout.strip(), "chosen 2")

    def test_a_program_that_has_another_name_in_the_release_is_found_by_the_names_it_may_have(self):
        a = "amd64" if fetch.arch() == "x86_64" else "arm64"
        data = zipball({f"yq_linux_{a}": "#!/bin/sh\necho yq\n", "yq.1": "man page"})
        self.pub.release("acme/chosen", "v4.0.0", {f"yq_linux_{a}.zip": data})
        floating.install(self.tool({"yq": "yq_linux_amd64|yq_linux_arm64|yq"}), False, True)
        self.assertEqual(subprocess.run([str(paths.bin_dir() / "yq")], capture_output=True, text=True).stdout.strip(), "yq")

    def test_a_release_without_the_program_installs_nothing(self):
        a = self.arch_words()
        self.pub.release("acme/chosen", "v1.0.0", {f"chosen-{a}-linux.tar.gz": tarball("other", "#!/bin/sh\n")})
        with self.assertRaises(fetch.FetchError) as c:
            floating.install(self.tool({"chosen": "chosen"}), False, True)
        self.assertEqual(c.exception.code, "no-program")
        self.assertFalse((paths.bin_dir() / "chosen").exists())
        self.assertFalse((paths.tools_dir() / "chosen" / "1.0.0").exists())

    def test_a_release_with_no_file_for_this_machine_is_refused_in_words(self):
        self.pub.release("acme/chosen", "v1.0.0", {"chosen-windows-amd64.zip": b"x"})
        with self.assertRaises(fetch.FetchError) as c:
            floating.install(self.tool({"chosen": "chosen"}), False, True)
        self.assertEqual(c.exception.code, "no-asset")

    def test_kit_check_asks_each_publisher_and_installs_nothing(self):
        from ws_host.lib import kitrun
        os.environ["WS_HOST_NPM_REGISTRY"] = os.environ["WS_HOST_PYPI"] = self.pub.url
        rows = kitrun.verify("railway")
        self.assertEqual([r["name"] for r in rows], ["railway"])
        self.assertEqual(rows[0]["status"], "fail", "the stand-in has no such release, and that is said, not hidden")
        self.assertFalse((paths.tools_dir() / "railway").exists())


class BaseTools(Home):
    def test_base_has_the_modern_tools_as_floating_binaries_and_checks_each(self):
        from ws_host.core import registry as reg
        base = reg.discover().kits["base"]()
        d = {"id": "debian", "codename": "trixie", "id_like": ""}
        floats = [x.name for x in base.downloads(d) if isinstance(x, Floating)]
        want = ["duckdb", "sqlite", "eza", "zoxide", "fzf", "yazi", "bat", "delta", "sd", "yq", "glow", "btop", "dust", "duf", "procs", "just", "watchexec", "hyperfine", "tokei", "lazygit", "tealdeer", "xh", "shfmt", "actionlint"]
        self.assertEqual(floats, want)
        programs = {c.program for c in base.checks(d) if c.program}
        for p in ("eza", "zoxide", "fzf", "yazi", "ya", "bat", "delta", "sd", "yq", "glow", "btop", "dust", "duf", "procs", "just", "watchexec", "hyperfine", "tokei", "lazygit", "tldr", "xh", "shfmt", "actionlint"):
            self.assertIn(p, programs, p)
        self.assertNotIn("tree", programs, "eza --tree stands in for it")


class SqlTools(Home):
    """0003-kits FR-020: SQLite and DuckDB float in base, and the embedded-sql kit holds the tools around them."""

    def setUp(self):
        super().setUp()
        self.pub = Publisher()
        self.addCleanup(self.pub.stop)
        os.environ["WS_HOST_SQLITE_URL"] = self.pub.url
        os.environ["WS_HOST_GITHUB_API"] = self.pub.url
        os.environ["GH_TOKEN"] = "not-a-real-token"

    def zip_of(self, body=b"#!/bin/sh\necho 3.99.0\n"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for n in ("sqlite3", "sqldiff", "sqlite3_analyzer"):
                info = zipfile.ZipInfo(f"sqlite-tools-linux-x64-3990000/{n}")
                info.external_attr = 0o755 << 16
                z.writestr(info, body)
        return buf.getvalue()

    def page(self, data, sha=None):
        sha = sha or hashlib.sha3_256(data).hexdigest()
        self.pub.routes["/download.html"] = (f"<html><!--\nPRODUCT,3.99.0,2026/sqlite-amalgamation-3990000.zip,100,{'0' * 64}\n"
                                             f"PRODUCT,3.99.0,2026/sqlite-tools-linux-x64-3990000.zip,{len(data)},{sha}\n-->").encode()
        self.pub.routes["/2026/sqlite-tools-linux-x64-3990000.zip"] = data

    def test_sqlite_org_is_asked_for_the_newest_tools_and_their_sha3(self):
        data = self.zip_of()
        self.page(data)
        r = floating.sqlite_org("x86_64")
        self.assertEqual((r.version, r.sha3, r.kind), ("3.99.0", hashlib.sha3_256(data).hexdigest(), "zip"))
        self.assertTrue(r.url.endswith("/2026/sqlite-tools-linux-x64-3990000.zip"))

    def test_sqlite_org_has_nothing_for_arm_and_that_is_said_in_words(self):
        self.page(self.zip_of())
        with self.assertRaises(fetch.FetchError) as e:
            floating.sqlite_org("aarch64")
        self.assertEqual(e.exception.code, "unsupported-arch")

    def test_the_tools_install_when_the_sha3_matches_and_nothing_does_when_it_does_not(self):
        if fetch.arch() != "x86_64":
            self.skipTest("sqlite.org builds the tools for x86-64 only")
        from ws_host.kits import base
        self.page(self.zip_of())
        self.assertEqual(fetch.install(base.SQLITE)["outcome"], "installed")
        self.assertEqual(subprocess.run([str(paths.bin_dir() / "sqlite3")], capture_output=True, text=True).stdout.strip(), "3.99.0")
        self.assertTrue((paths.bin_dir() / "sqldiff").exists())
        shutil.rmtree(paths.tools_dir() / "sqlite")
        for n in ("sqlite3", "sqldiff", "sqlite3_analyzer"):
            (paths.bin_dir() / n).unlink()
        self.page(self.zip_of(), sha="1" * 64)
        with self.assertRaises(fetch.FetchError) as e:
            fetch.install(base.SQLITE)
        self.assertEqual(e.exception.code, "checksum")
        self.assertFalse((paths.bin_dir() / "sqlite3").exists())

    def test_an_architecture_the_publisher_does_not_build_for_is_skipped_not_failed(self):
        from ws_host.core import registry as reg
        from ws_host.lib import kitrun
        from ws_host.core import cli  # noqa: F401
        from ws_host.core.kit import Floating as F

        class Arm(reg.discover().kits["base"]):
            def apt(self, d):
                return []

            def downloads(self, d):
                return [F("nothing-here", lambda a: None, binaries={"x": "x"}, archs=("riscv",))]

            def links(self, d):
                return {}

            def configure(self, ctx):
                return []

        class Ctx:
            offline, dry_run = False, False

        steps = list(kitrun.install(Ctx(), Arm(), "base"))
        row = [s for s in steps if s[0] == "download nothing-here"][0]
        self.assertEqual(row[1], "ok", row)
        self.assertIn("skipped", row[2])

    def test_duckdb_is_chosen_by_its_cli_zip_and_not_by_the_library_zip(self):
        from ws_host.kits import base
        a = fetch.arch()
        word = "amd64" if a == "x86_64" else "arm64"
        cli = f"duckdb_cli-linux-{word}.zip"
        self.pub.release("duckdb/duckdb", "v9.9.9", {f"libduckdb-linux-{word}.zip": b"lib", cli: b"cli", "duckdb_cli-osx-universal.zip": b"mac"})
        r = base.DUCKDB.resolve(a)
        self.assertEqual((r.version, r.url.rsplit("/", 1)[1]), ("9.9.9", cli))

    def test_the_embedded_sql_kit_holds_the_tools_and_checks_each(self):
        from ws_host.core import registry as reg
        kit = reg.discover().kits["embedded-sql"]()
        d = {"id": "debian", "codename": "trixie", "id_like": ""}
        self.assertEqual([x.name for x in kit.downloads(d)], ["turso", "usql", "litestream", "sqruff", "dbmate", "sqlite-utils", "datasette", "harlequin", "visidata"])
        self.assertTrue(all(isinstance(x, Floating) for x in kit.downloads(d)))
        self.assertEqual({x.name for x in kit.downloads(d) if x.manager == "pip"}, {"sqlite-utils", "datasette", "harlequin", "visidata"})
        self.assertEqual({c.program for c in kit.checks(d)}, {"turso", "usql", "litestream", "sqruff", "dbmate", "sqlite-utils", "datasette", "harlequin", "vd", "visidata"})
