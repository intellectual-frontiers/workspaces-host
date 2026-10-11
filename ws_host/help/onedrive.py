"""Microsoft OneDrive: signing in to a home or work account, and copying files."""
from __future__ import annotations

from ..core.registry import Step, topic


@topic("onedrive", "Sign in to Microsoft and copy files to and from OneDrive.")
def onedrive():
    return {
        "plain": "Sign in to a home or work Microsoft account with a one-time code, then list, fetch and copy files in its OneDrive. Nothing already there is replaced unless you say so.",
        "sections": (
            ("Set up", "Install the microsoft kit, then sign in: ws-host auth new microsoft --host work. A Microsoft page opens in your browser and you sign in there, with any second factor your account asks for. "
                       "ws-host never sees your password. No app registration or administrator is needed. For a second account give each a name: --host work and --host home."),
            ("Copying", "ws-host onedrive list shows a folder, onedrive sync REMOTE LOCAL copies a file or folder down, and onedrive add LOCAL REMOTE copies one up. "
                        "A file that is already at the other end is left as it is, and said so, unless you add --replace. --dry-run shows what would be copied. With two accounts, name one with --account."),
            ("If Microsoft says you do not have access", "Some organizations allow only one way of signing in. After you pick your account, a page that says 'You don't have access to this' means they block this one: "
                                                        "try ws-host auth new microsoft --host work --method code, which shows a code to type on a page. On a machine with no browser use --method code from the start. "
                                                        "If neither works, an administrator can read the Entra sign-in log, which names the policy that blocked it."),
            ("An app of your own", "If you have an app registration, ws-host auth new microsoft --host work --own-app explains where its two IDs are, asks for them, checks them and keeps them for that account."),
            ("Where the sign-in is kept", "In your system keyring when there is one. On a machine without one, such as most WSL setups, in a file only you can read under ~/.IdentityService, and ws-host says so."),
            ("A synced folder", "OneDrive's own sync program exists only for Windows and macOS. On WSL, let the Windows OneDrive sync, mark the folders you need as Always keep on this device, "
                                "and read them at /mnt/c/Users/<you>/OneDrive."),
        ),
        "steps": (
            Step("Install the Microsoft sign-in library", ("kit", "add"), {"kit": "microsoft"}),
            Step("Sign in to Microsoft", ("auth", "new"), {"forge": "microsoft"}),
            Step("Sign in with the code method instead", ("auth", "new"), {"forge": "microsoft", "method": "code"}),
            Step("See whether I am signed in", ("auth", "status")),
            Step("List the top of my OneDrive", ("onedrive", "list")),
        ),
    }
