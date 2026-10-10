"""Signing in to a Microsoft account (0002-repositories-and-trust FR-025). Runs in the `microsoft` kit's own Python, where Microsoft's azure-identity library is, through
`python -m ws_host.lib.msauth login|token`; it writes one JSON object per line on standard output and never prints a token except as the answer to `token`.

Standard library only at module level, and no import of the rest of ws-host."""
from __future__ import annotations

import json
import os
import sys

# Microsoft's own public client for Graph command-line tools; a person's own registered app (WS_HOST_MICROSOFT_CLIENT_ID) replaces it, which a work tenant may require.
DEFAULT_CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
SCOPES = ("https://graph.microsoft.com/Files.ReadWrite.All", "https://graph.microsoft.com/User.Read")


def say(**kw) -> None:
    print(json.dumps(kw), flush=True)


def _credential(state: dict, name: str, unencrypted: bool, record=None, prompt=None):
    from azure.identity import DeviceCodeCredential, TokenCachePersistenceOptions
    options = TokenCachePersistenceOptions(name=name, allow_unencrypted_storage=unencrypted)
    kw = {"client_id": state.get("client_id") or DEFAULT_CLIENT_ID, "tenant_id": state.get("tenant") or "common", "cache_persistence_options": options}
    if record is not None:
        kw.update(authentication_record=record, disable_automatic_authentication=True)
    if prompt is not None:
        kw["prompt_callback"] = prompt
    return DeviceCodeCredential(**kw)


def _write(path: str, state: dict) -> None:
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = path + ".new"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(state, f)
    os.replace(tmp, path)


def login(label: str, path: str, client_id: str, tenant: str) -> int:
    """Device-code sign-in: the code and where to type it are printed as a `code` line; the token is kept by Microsoft's library in the system keyring where there is one,
    and otherwise in a private file, which is said."""
    def prompt(url, code, expires):
        say(event="code", url=url, code=code)
    state = {"label": label, "client_id": client_id, "tenant": tenant}
    name = f"ws-host-microsoft-{label}"
    stored = "keyring"
    try:
        record = _credential(state, name, False, prompt=prompt).authenticate(scopes=list(SCOPES))
    except Exception as e:
        if "persist" not in (type(e).__name__ + str(e)).lower() and "keyring" not in str(e).lower() and "libsecret" not in str(e).lower():
            say(event="error", message=str(e)[:300])
            return 1
        stored = "file"
        say(event="note", message="There is no system keyring here, so the sign-in is kept in a private file only you can read.")
        try:
            record = _credential(state, name, True, prompt=prompt).authenticate(scopes=list(SCOPES))
        except Exception as e2:
            say(event="error", message=str(e2)[:300])
            return 1
    state.update(record=record.serialize(), stored=stored)
    _write(path, state)
    say(event="done", username=getattr(record, "username", ""), tenant=getattr(record, "tenant_id", ""), stored=stored)
    return 0


def token(path: str) -> int:
    """The access token for Graph, from what the sign-in left; nothing is shown on a terminal and no question is asked."""
    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
        from azure.identity import AuthenticationRecord
        record = AuthenticationRecord.deserialize(state["record"])
        cred = _credential(state, f"ws-host-microsoft-{state['label']}", state.get("stored") == "file", record=record)
        t = cred.get_token(*SCOPES)
    except FileNotFoundError:
        say(event="error", code="not-signed-in", message="not signed in")
        return 2
    except Exception as e:
        say(event="error", code="expired", message=str(e)[:300])
        return 2
    say(event="token", token=t.token, expires_on=t.expires_on)
    return 0


def main(argv: list[str]) -> int:
    if argv and argv[0] == "login" and len(argv) == 5:
        return login(*argv[1:])
    if argv and argv[0] == "token" and len(argv) == 2:
        return token(argv[1])
    print("usage: msauth login LABEL FILE CLIENT_ID TENANT | msauth token FILE", file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
