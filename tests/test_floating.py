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

    def test_a_quiet_look_is_not_made_again_for_a_few_hours_and_an_update_looks_anyway(self):
        self.pub.release("acme/fake", "v1.0.0", {"fake-linux.tar.gz": tarball("fake", "#!/bin/sh\necho 1.0.0\n")})
        f = self.tool()
        floating.install(f, False, True)
        asked = len(self.pub.hits)
        self.assertEqual(floating.install(f, False, False)["outcome"], "present")
        self.assertEqual(len(self.pub.hits), asked, "no second look so soon")
        with floating.looking_fresh():
            floating.install(f, False)
        self.assertGreater(len(self.pub.hits), asked, "but an update looks")

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
        for n in ("aws", "azure", "cloudflare", "railway", "cloud"):
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
    """`ws-host update` keeps what floats current, whichever kit put it there."""

    def test_an_installed_floating_tool_is_looked_at_and_one_never_installed_is_not(self):
        from unittest import mock
        from ws_host.core import registry as reg
        from ws_host.lib import kitrun
        from ws_host.core.kit import Floating
        seen = []

        def fake_install(d, offline=False):
            seen.append(d.name)
            return {"outcome": "updated", "version": "2", "previous": "1"}
        root = paths.tools_dir() / "wrangler"
        (root / "1").mkdir(parents=True)
        os.symlink("1", root / "current")
        ctx = type("C", (), {"offline": False})()
        with mock.patch.object(fetch, "install", fake_install):
            r = kitrun.refresh_installed(ctx)
        self.assertEqual(seen, ["wrangler"])
        self.assertEqual(r["tools"], 1)
        self.assertIn("updated wrangler 1 to 2", r["plain"])

    def test_with_nothing_floating_installed_it_says_so_and_asks_nobody(self):
        from ws_host.lib import kitrun
        ctx = type("C", (), {"offline": False})()
        r = kitrun.refresh_installed(ctx)
        self.assertEqual(r["tools"], 0)
