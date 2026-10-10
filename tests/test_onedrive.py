"""0003-kits FR-021, 0002 FR-025: signing in to Microsoft with Microsoft's own library, and OneDrive through Graph, against a stand-in Graph and a stand-in azure-identity."""
import json
import os
import stat
import sys
import tempfile
import textwrap
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from ws_host.lib import graph, msauth
from .helpers import Home


class FakeGraph:
    """An in-memory OneDrive that answers the calls ws-host makes, and notes who was sent a bearer token."""

    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.folders: set[str] = set()
        self.calls: list[tuple[str, str, str | None]] = []
        self.sessions: dict[str, dict] = {}
        outer = self

        class H(BaseHTTPRequestHandler):
            def _send(self, code, body=b"", ctype="application/json"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _json(self, code, obj):
                self._send(code, json.dumps(obj).encode())

            def _body(self):
                n = int(self.headers.get("Content-Length") or 0)
                return self.rfile.read(n) if n else b""

            def _note(self):
                outer.calls.append((self.command, self.path.split("?")[0], self.headers.get("Authorization")))

            def _item(self, rel):
                if rel in outer.files:
                    return {"name": rel.rsplit("/", 1)[-1], "size": len(outer.files[rel]), "lastModifiedDateTime": "2026-10-01T00:00:00Z", "id": rel, "webUrl": "https://x/" + rel,
                            "@microsoft.graph.downloadUrl": f"{outer.url}/dl/{urllib.parse.quote(rel)}", "file": {}}
                if rel == "" or rel in outer.folders:
                    kids = [k for k in list(outer.files) + list(outer.folders) if k.rpartition("/")[0] == rel and k != rel]
                    return {"name": rel.rsplit("/", 1)[-1] or "root", "size": 0, "lastModifiedDateTime": "2026-10-01T00:00:00Z", "id": rel or "root", "folder": {"childCount": len(kids)}}
                return None

            def _target(self):
                path = urllib.parse.unquote(self.path.split("?")[0])
                if path == "/me":
                    return "me", ""
                pre = "/me/drive/root"
                if not path.startswith(pre):
                    return None, ""
                rest = path[len(pre):]
                for suffix in ("/children", "/content", "/createUploadSession"):
                    if rest.endswith(suffix):
                        rest, kind = rest[:-len(suffix)], suffix[1:]
                        break
                else:
                    kind = "item"
                if rest.startswith(":/") and rest.endswith(":"):
                    rest = rest[2:-1]
                elif rest == "":
                    pass
                return kind, rest

            def do_GET(self):
                self._note()
                path = urllib.parse.unquote(self.path.split("?")[0])
                if path.startswith("/dl/"):
                    rel = path[4:]
                    return self._send(200, outer.files[rel], "application/octet-stream") if rel in outer.files else self._send(404)
                kind, rel = self._target()
                if kind == "me":
                    return self._json(200, {"displayName": "Ada", "mail": "ada@example.com"})
                if kind == "children":
                    return self._json(200, {"value": [outer_item for k in sorted(set(outer.files) | outer.folders) if k.rpartition("/")[0] == rel and (outer_item := self._item(k))]})
                item = self._item(rel)
                return self._json(200, item) if item else self._json(404, {"error": {"message": "not found"}})

            def do_PUT(self):
                self._note()
                body = self._body()
                path = urllib.parse.unquote(self.path.split("?")[0])
                if path.startswith("/upload/"):
                    s = outer.sessions[path[8:]]
                    s["data"] += body
                    if self.headers["Content-Range"].split("/")[0].endswith(str(int(self.headers["Content-Range"].split("/")[1]) - 1)):
                        outer.files[s["path"]] = s["data"]
                    return self._json(202, {})
                kind, rel = self._target()
                outer.files[rel] = body
                return self._json(201, {"name": rel})

            def do_POST(self):
                self._note()
                body = json.loads(self._body() or b"{}")
                kind, rel = self._target()
                if kind == "children":
                    name = f"{rel}/{body['name']}".lstrip("/")
                    if name in outer.folders:
                        return self._json(409, {"error": {"message": "nameAlreadyExists"}})
                    outer.folders.add(name)
                    return self._json(201, {"name": body["name"]})
                if kind == "createUploadSession":
                    sid = str(len(outer.sessions))
                    outer.sessions[sid] = {"path": rel, "data": b""}
                    return self._json(200, {"uploadUrl": f"{outer.url}/upload/{sid}"})
                return self._json(400, {})

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()


class OneDrive(Home):
    def setUp(self):
        super().setUp()
        self.g = FakeGraph()
        self.addCleanup(self.g.stop)
        os.environ["WS_HOST_GRAPH_URL"] = self.g.url + "/"
        self._real = graph.token_for
        graph.token_for = lambda label: "tok-" + label
        self.addCleanup(lambda: setattr(graph, "token_for", self._real))
        for label in ("work",):
            f = graph.state_file(label)
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("{}")
        self.g.files.update({"Docs/a.txt": b"alpha", "Docs/sub/b.txt": b"bravo!", "top.txt": b"t"})
        self.g.folders.update({"Docs", "Docs/sub"})
        self.local = Path(self._tmp.name) / "local"
        self.local.mkdir()

    def test_list_shows_folders_first_with_sizes_and_sends_the_token_only_to_graph(self):
        code, doc = self.run_json("onedrive", "list")
        self.assertEqual(code, 0, doc)
        self.assertEqual([i["name"] for i in doc["data"]["items"]], ["Docs", "top.txt"])
        self.assertEqual(self.g.calls[0][2], "Bearer tok-work")
        code, doc = self.run_json("onedrive", "list", "Docs")
        self.assertEqual([i["name"] for i in doc["data"]["items"]], ["sub", "a.txt"])

    def test_show_names_a_file_and_a_folder_and_a_missing_one_is_said_in_words(self):
        self.assertIn("a file of 5 bytes", self.run_json("onedrive", "show", "Docs/a.txt")[1]["data"]["plain"])
        self.assertIn("folder", self.run_json("onedrive", "show", "Docs")[1]["data"]["plain"])
        code, doc = self.run_json("onedrive", "show", "nope.txt")
        self.assertNotEqual(code, 0)
        self.assertIn("not in your OneDrive", json.dumps(doc))

    def test_sync_copies_a_folder_down_without_sending_the_token_to_the_download_link(self):
        code, doc = self.run_json("onedrive", "sync", "Docs", str(self.local))
        self.assertEqual(code, 0, doc)
        self.assertEqual((self.local / "a.txt").read_bytes(), b"alpha")
        self.assertEqual((self.local / "sub" / "b.txt").read_bytes(), b"bravo!")
        self.assertTrue(all(auth is None for m, p, auth in self.g.calls if p.startswith("/dl/")))
        self.assertFalse(list(self.local.rglob("*.part")))

    def test_sync_keeps_a_different_local_file_unless_replace_is_given_and_leaves_one_that_is_the_same(self):
        (self.local / "a.txt").write_bytes(b"mine!!")
        code, doc = self.run_json("onedrive", "sync", "Docs/a.txt", str(self.local))
        self.assertEqual((self.local / "a.txt").read_bytes(), b"mine!!")
        self.assertIn("left it", json.dumps(doc))
        self.run_json("onedrive", "sync", "Docs/a.txt", str(self.local), "--replace")
        self.assertEqual((self.local / "a.txt").read_bytes(), b"alpha")

    def test_a_name_that_would_leave_the_folder_is_never_written(self):
        self.g.files["Docs/..x"] = b"ok"
        self.assertFalse(graph.safe_name("../x"))
        self.assertFalse(graph.safe_name(".."))
        self.assertTrue(graph.safe_name("..x"))

    def test_sync_dry_run_writes_nothing(self):
        code, doc = self.run_json("onedrive", "sync", "Docs", str(self.local), "--dry-run")
        self.assertEqual(code, 0, doc)
        self.assertEqual(list(self.local.iterdir()), [])
        self.assertIn("Would copy", json.dumps(doc))

    def test_add_uploads_a_folder_with_its_folders_and_leaves_what_is_already_there(self):
        (self.local / "p").mkdir()
        (self.local / "p" / "one.txt").write_bytes(b"1")
        (self.local / "p" / "deep").mkdir()
        (self.local / "p" / "deep" / "two.txt").write_bytes(b"22")
        code, doc = self.run_json("onedrive", "add", str(self.local / "p"), "Up/p")
        self.assertEqual(code, 0, doc)
        self.assertEqual(self.g.files["Up/p/one.txt"], b"1")
        self.assertEqual(self.g.files["Up/p/deep/two.txt"], b"22")
        self.assertTrue({"Up", "Up/p", "Up/p/deep"} <= self.g.folders)
        (self.local / "p" / "one.txt").write_bytes(b"changed")
        code, doc = self.run_json("onedrive", "add", str(self.local / "p"), "Up/p")
        self.assertEqual(self.g.files["Up/p/one.txt"], b"1", "nothing already in OneDrive is replaced")
        self.assertIn("left it", json.dumps(doc))
        self.run_json("onedrive", "add", str(self.local / "p" / "one.txt"), "Up/p/one.txt", "--replace")
        self.assertEqual(self.g.files["Up/p/one.txt"], b"changed")

    def test_a_large_file_goes_up_in_an_upload_session_in_pieces(self):
        big = self.local / "big.bin"
        big.write_bytes(os.urandom(graph.SIMPLE_LIMIT + graph.CHUNK + 5))
        code, doc = self.run_json("onedrive", "add", str(big), "Big/big.bin")
        self.assertEqual(code, 0, doc)
        self.assertEqual(self.g.files["Big/big.bin"], big.read_bytes())
        puts = [c for c in self.g.calls if c[0] == "PUT" and c[1].startswith("/upload/")]
        self.assertGreaterEqual(len(puts), 2)
        self.assertTrue(all(c[2] is None for c in puts), "the session link is not sent the sign-in")

    def test_add_dry_run_changes_nothing(self):
        (self.local / "x.txt").write_bytes(b"x")
        code, doc = self.run_json("onedrive", "add", str(self.local / "x.txt"), "X/x.txt", "--dry-run")
        self.assertEqual(code, 0, doc)
        self.assertNotIn("X/x.txt", self.g.files)

    def test_two_sign_ins_must_be_told_apart(self):
        f = graph.state_file("personal")
        f.write_text("{}")
        code, doc = self.run_json("onedrive", "list")
        self.assertEqual(code, 2)
        self.assertIn("--account", json.dumps(doc))
        self.assertEqual(self.run_json("onedrive", "list", "--account", "personal")[0], 0)

    def test_with_no_sign_in_it_says_how_to_sign_in(self):
        graph.state_file("work").unlink()
        code, doc = self.run_json("onedrive", "list")
        self.assertNotEqual(code, 0)
        self.assertIn("auth", json.dumps(doc["actions"]) if "actions" in doc else json.dumps(doc))


FAKE_IDENTITY = textwrap.dedent('''
    import datetime, json, os
    class TokenCachePersistenceOptions:
        def __init__(self, name, allow_unencrypted_storage=False):
            self.name, self.allow_unencrypted_storage = name, allow_unencrypted_storage
    class AuthenticationRecord:
        def __init__(self, username): self.username, self.tenant_id = username, "t"
        def serialize(self): return json.dumps({"u": self.username})
        @staticmethod
        def deserialize(s): return AuthenticationRecord(json.loads(s)["u"])
    class Tok:
        token, expires_on = "faketoken", 9999999999
    class DeviceCodeCredential:
        def __init__(self, **kw): self.kw = kw
        def authenticate(self, scopes):
            if os.environ.get("FAKE_NO_KEYRING") and not self.kw["cache_persistence_options"].allow_unencrypted_storage:
                raise RuntimeError("no keyring: could not persist the cache")
            self.kw["prompt_callback"]("https://microsoft.com/devicelogin", "ABCD1234E", datetime.datetime.now(datetime.timezone.utc))
            return AuthenticationRecord("ada@example.com")
        def get_token(self, *scopes):
            assert self.kw.get("disable_automatic_authentication") is True, "a token is never asked for with a prompt"
            return Tok()
''')


class Signing(Home):
    """The sign-in and the token, with a stand-in for azure-identity run by the kit's Python (here, a script that runs this machine's)."""

    def setUp(self):
        super().setUp()
        pkg = Path(self._tmp.name) / "fakeid" / "azure" / "identity"
        pkg.mkdir(parents=True)
        (pkg.parent / "__init__.py").write_text("")
        (pkg / "__init__.py").write_text(FAKE_IDENTITY)
        os.environ["PYTHONPATH"] = str(Path(self._tmp.name) / "fakeid")
        py = graph.venv_python()
        py.parent.mkdir(parents=True)
        py.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
        py.chmod(py.stat().st_mode | stat.S_IXUSR)
        self.g = FakeGraph()
        self.addCleanup(self.g.stop)
        os.environ["WS_HOST_GRAPH_URL"] = self.g.url
        self.g.files["hello.txt"] = b"hi"

    def test_auth_new_microsoft_shows_the_code_stores_a_private_record_and_the_files_then_open_with_the_token(self):
        code, out = self.run_cmd("auth", "new", "microsoft", "--host", "work", "--json")
        self.assertEqual(code, 0, out)
        self.assertIn("ABCD1234E", out)
        f = graph.state_file("work")
        self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600)
        self.assertEqual(json.loads(f.read_text())["stored"], "keyring")
        code, doc = self.run_json("onedrive", "list")
        self.assertEqual(code, 0, doc)
        self.assertEqual([i["name"] for i in doc["data"]["items"]], ["hello.txt"])
        self.assertEqual(self.g.calls[0][2], "Bearer faketoken")
        code, doc = self.run_json("auth", "status")
        self.assertIn("microsoft work", json.dumps(doc))
        self.assertTrue([r for r in doc["data"]["forges"] if r["name"] == "microsoft work"][0]["signed_in"])

    def test_without_a_system_keyring_the_sign_in_is_kept_in_a_private_file_and_that_is_said(self):
        os.environ["FAKE_NO_KEYRING"] = "1"
        code, out = self.run_cmd("auth", "new", "microsoft", "--json")
        self.assertEqual(code, 0, out)
        self.assertIn("private file", out)
        self.assertEqual(json.loads(graph.state_file("default").read_text())["stored"], "file")

    def test_a_missing_kit_says_how_to_install_it(self):
        graph.venv_python().unlink()
        code, doc = self.run_json("auth", "new", "microsoft")
        self.assertNotEqual(code, 0)
        self.assertIn("microsoft", json.dumps(doc))

    def test_the_token_command_never_asks_a_question_and_a_missing_record_is_a_plain_failure(self):
        self.assertEqual(msauth.main(["token", str(Path(self._tmp.name) / "none.json")]), 2)

    def test_a_signed_out_account_is_reported_not_crashed_on(self):
        graph.state_file("work").parent.mkdir(parents=True, exist_ok=True)
        graph.state_file("work").write_text('{"label": "work", "record": "{bad", "stored": "keyring"}')
        code, doc = self.run_json("onedrive", "list")
        self.assertNotEqual(code, 0)
        self.assertIn("sign in", json.dumps(doc).lower())
