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
            f.write_text('{"record": "x"}')
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
        f.write_text('{"record": "x"}')
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
    class InteractiveBrowserCredential:
        def __init__(self, **kw): self.kw = kw
        def authenticate(self, scopes):
            import webbrowser
            assert webbrowser.open("https://login.example/authorize?client_id=x&redirect_uri=http%3A%2F%2Flocalhost%3A8400"), "the page is announced, so the library believes it opened"
            return AuthenticationRecord("ada@example.com")
        def get_token(self, *scopes):
            assert self.kw.get("disable_automatic_authentication") is True, "a token is never asked for with a prompt"
            return Tok()
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
        self._real_open = graph.open_url
        graph.open_url = lambda url: True               # a test never starts a real browser
        self.addCleanup(lambda: setattr(graph, "open_url", self._real_open))
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
        os.environ["WS_HOST_MICROSOFT_CLIENT_ID"] = "0a1b2c3d-1111-2222-3333-444455556666"      # a person who set it is not asked

    def test_auth_new_microsoft_shows_the_code_stores_a_private_record_and_the_files_then_open_with_the_token(self):
        code, out = self.run_cmd("auth", "new", "microsoft", "--host", "work", "--method", "code", "--json")
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
        code, out = self.run_cmd("auth", "new", "microsoft", "--method", "code", "--json")
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


class AskingForTheApp(Home):
    """0002 FR-026: nobody is ever told to set an environment variable; a terminal is asked, anything else is told what to do, and an answer is kept for that account."""

    def setUp(self):
        super().setUp()
        self._real_open = graph.open_url
        graph.open_url = lambda url: True               # a test never starts a real browser
        self.addCleanup(lambda: setattr(graph, "open_url", self._real_open))
        pkg = Path(self._tmp.name) / "fakeid" / "azure" / "identity"
        pkg.mkdir(parents=True)
        (pkg.parent / "__init__.py").write_text("")
        (pkg / "__init__.py").write_text(FAKE_IDENTITY)
        os.environ["PYTHONPATH"] = str(Path(self._tmp.name) / "fakeid")
        py = graph.venv_python()
        py.parent.mkdir(parents=True)
        py.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
        py.chmod(py.stat().st_mode | stat.S_IXUSR)
        for k in ("WS_HOST_MICROSOFT_CLIENT_ID", "WS_HOST_MICROSOFT_TENANT"):
            os.environ.pop(k, None)

    def test_where_nothing_can_be_asked_it_says_what_to_do_in_plain_words_and_offers_the_setting_command(self):
        code, doc = self.run_json("auth", "new", "microsoft", "--host", "work", "--own-app")
        self.assertEqual(code, 3, doc)
        self.assertEqual(doc["data"]["code"], "needs-input")
        text = json.dumps(doc)
        self.assertIn("Application (client) ID", text)
        self.assertNotIn("environment variable", text.lower())
        self.assertNotIn("ws-host.env", text)
        self.assertIn("auth", json.dumps(doc["actions"]))
        self.assertIn("set", json.dumps(doc["actions"]))

    def test_auth_set_checks_what_is_typed_and_keeps_it_for_that_account_only(self):
        code, doc = self.run_json("auth", "set", "microsoft", "not-a-guid", "example.com", "--host", "work")
        self.assertEqual(code, 2)
        self.assertIn("Application (client) ID", json.dumps(doc))
        code, doc = self.run_json("auth", "set", "microsoft", "0a1b2c3d-1111-2222-3333-444455556666", "contoso.com", "--host", "work")
        self.assertEqual(code, 0, doc)
        self.assertEqual(graph.app_for("work"), ("0a1b2c3d-1111-2222-3333-444455556666", "contoso.com"))
        self.assertIsNone(graph.app_for("personal"))
        self.assertEqual(stat.S_IMODE(graph.state_file("work").stat().st_mode), 0o600)
        self.assertEqual(graph.accounts(), [], "an app is not yet a sign-in")

    def test_shared_means_microsofts_own_app_and_the_common_tenant(self):
        self.run_json("auth", "set", "microsoft", "shared", "common", "--host", "personal")
        self.assertEqual(graph.app_for("personal"), ("shared", "common"))

    def test_the_saved_app_is_the_one_the_sign_in_uses(self):
        self.run_json("auth", "set", "microsoft", "0a1b2c3d-1111-2222-3333-444455556666", "contoso.com", "--host", "work")
        code, out = self.run_cmd("auth", "new", "microsoft", "--host", "work", "--own-app", "--json")
        self.assertEqual(code, 0, out)
        state = json.loads(graph.state_file("work").read_text())
        self.assertEqual((state["client_id"], state["tenant"]), ("0a1b2c3d-1111-2222-3333-444455556666", "contoso.com"))
        self.assertIn("record", state)

    def test_a_person_who_does_set_the_variables_is_not_asked(self):
        os.environ["WS_HOST_MICROSOFT_CLIENT_ID"] = "0a1b2c3d-1111-2222-3333-444455556666"
        os.environ["WS_HOST_MICROSOFT_TENANT"] = "contoso.com"
        self.assertEqual(graph.app_for("work"), ("0a1b2c3d-1111-2222-3333-444455556666", "contoso.com"))
        code, out = self.run_cmd("auth", "new", "microsoft", "--host", "work", "--json")
        self.assertEqual(code, 0, out)

    def test_at_a_terminal_it_asks_validates_keeps_the_answers_and_does_not_ask_again(self):
        from unittest import mock
        from ws_host.commands import auth as auth_cmd

        class Terminal:
            def interactive(self):
                return True
        answers = iter(["oops", "0a1b2c3d-1111-2222-3333-444455556666", "also bad", "contoso.com"])
        with mock.patch("builtins.input", lambda prompt="": next(answers)), mock.patch("builtins.print"):
            auth_cmd._ask_app(Terminal(), "work")
        self.assertEqual(graph.app_for("work"), ("0a1b2c3d-1111-2222-3333-444455556666", "contoso.com"))
        self.assertEqual(list(answers), [], "every answer was used")

    def test_typing_shared_asks_nothing_more(self):
        from unittest import mock
        from ws_host.commands import auth as auth_cmd

        class Terminal:
            def interactive(self):
                return True
        with mock.patch("builtins.input", lambda prompt="": "shared"), mock.patch("builtins.print"):
            auth_cmd._ask_app(Terminal(), "personal")
        self.assertEqual(graph.app_for("personal"), ("shared", "common"))

    def test_four_bad_answers_stop_it_with_a_plain_message(self):
        from unittest import mock
        from ws_host.commands import auth as auth_cmd
        from ws_host.core.resource import WsError

        class Terminal:
            def interactive(self):
                return True
        with mock.patch("builtins.input", lambda prompt="": "x"), mock.patch("builtins.print"):
            with self.assertRaises(WsError):
                auth_cmd._ask_app(Terminal(), "work")


class Browser(Home):
    """The browser sign-in, which is the default and needs no app registration of the person's own."""

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
        for k in ("WS_HOST_MICROSOFT_CLIENT_ID", "WS_HOST_MICROSOFT_TENANT"):
            os.environ.pop(k, None)
        self.opened = []
        self._real_open = graph.open_url
        graph.open_url = lambda url: self.opened.append(url) or True
        self.addCleanup(lambda: setattr(graph, "open_url", self._real_open))
        self.g = FakeGraph()
        self.addCleanup(self.g.stop)
        os.environ["WS_HOST_GRAPH_URL"] = self.g.url
        self.g.files["hello.txt"] = b"hi"

    def test_it_signs_in_in_a_browser_by_default_with_no_app_and_nothing_asked(self):
        code, out = self.run_cmd("auth", "new", "microsoft", "--host", "work", "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.opened), 1)
        self.assertTrue(self.opened[0].startswith("https://login.example/authorize"))
        self.assertIn("login.example", out, "the address is shown too, in case the browser did not open")
        state = json.loads(graph.state_file("work").read_text())
        self.assertEqual(state["method"], "browser")
        self.assertEqual(state["client_id"], graph.SHARED_CLIENT)
        self.assertEqual(state["tenant"], "common")

    def test_a_saved_app_of_the_persons_own_is_named_and_the_way_back_to_the_shared_one_is_given(self):
        self.run_json("auth", "set", "microsoft", "0a1b2c3d-1111-2222-3333-444455556666", "contoso.com", "--host", "work")
        code, out = self.run_cmd("auth", "new", "microsoft", "--host", "work", "--json")
        self.assertEqual(code, 0, out)
        self.assertIn("0a1b2c3d-1111-2222-3333-444455556666", out)
        self.assertIn("ws-host auth set microsoft shared common --host work", out)
        self.run_json("auth", "set", "microsoft", "shared", "common", "--host", "work")
        code, out = self.run_cmd("auth", "new", "microsoft", "--host", "work", "--json")
        self.assertNotIn("you saved", out)
        self.assertEqual(json.loads(graph.state_file("work").read_text())["client_id"], graph.SHARED_CLIENT)

    def test_the_files_open_with_the_token_the_browser_sign_in_left(self):
        self.run_cmd("auth", "new", "microsoft", "--host", "work", "--json")
        code, doc = self.run_json("onedrive", "list")
        self.assertEqual(code, 0, doc)
        self.assertEqual(self.g.calls[0][2], "Bearer faketoken")

    def test_the_code_method_is_still_there_for_a_machine_with_no_browser(self):
        code, out = self.run_cmd("auth", "new", "microsoft", "--method", "code", "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.opened, [])
        self.assertIn("ABCD1234E", out)

    def test_without_a_desktop_or_wsl_no_program_is_started_and_the_address_is_only_shown(self):
        import platform
        from unittest import mock
        for k in ("DISPLAY", "WAYLAND_DISPLAY"):
            os.environ.pop(k, None)
        with mock.patch.object(platform, "uname", lambda: platform.uname_result("Linux", "h", "6.1.0-generic", "v", "x86_64")), mock.patch("subprocess.run") as run:
            self.assertFalse(self._real_open("https://login.example/authorize?x=1"))
            run.assert_not_called()

    def test_an_address_that_could_break_out_of_a_command_is_never_opened(self):
        for bad in ("http://insecure.example/", 'https://x/"; calc', "https://x/`id`", "https://x/ y", "file:///etc/passwd", "https://x/$(id)"):
            self.assertFalse(self._real_open(bad), bad)

    def test_a_browser_that_did_not_open_still_gets_the_address(self):
        graph.open_url = lambda url: False
        code, out = self.run_cmd("auth", "new", "microsoft", "--json")
        self.assertEqual(code, 0, out)
        self.assertIn("Open this address", out)
