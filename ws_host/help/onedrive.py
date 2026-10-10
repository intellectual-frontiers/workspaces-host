"""Microsoft OneDrive: signing in to a home or work account, and copying files."""
from __future__ import annotations

from ..core.registry import Step, topic


@topic("onedrive", "Sign in to Microsoft and copy files to and from OneDrive.")
def onedrive():
    return {
        "plain": "Sign in to a home or work Microsoft account with a one-time code, then list, fetch and copy files in its OneDrive. Nothing already there is replaced unless you say so.",
        "sections": (
            ("Set up", "Install the microsoft kit, then sign in. For a second account give each a name: ws-host auth new microsoft --host work, and --host home. "
                       "Microsoft shows a code and an address; you open the address in your browser, type the code and approve. No password is typed into a terminal."),
            ("Copying", "ws-host onedrive list shows a folder, onedrive sync REMOTE LOCAL copies a file or folder down, and onedrive add LOCAL REMOTE copies one up. "
                        "A file that is already at the other end is left as it is, and said so, unless you add --replace. --dry-run shows what would be copied. With two accounts, name one with --account."),
            ("Work accounts", "Many organizations make an administrator approve the app that signs you in. If sign-in stops with that message, register an app of your own once: "
                              "in the Microsoft Entra admin center choose App registrations, New registration, accept work accounts and Microsoft accounts for home use, add the platform Mobile and desktop "
                              "with the redirect https://login.microsoftonline.com/common/oauth2/nativeclient, turn on Allow public client flows, and add the delegated Microsoft Graph "
                              "permissions Files.ReadWrite.All and User.Read. Put its Application (client) ID in WS_HOST_MICROSOFT_CLIENT_ID in ~/.config/workspaces-host/ws-host.env."),
            ("Where the sign-in is kept", "In your system keyring when there is one. On a machine without one, such as most WSL setups, in a file only you can read under ~/.IdentityService, and ws-host says so."),
            ("A synced folder", "OneDrive's own sync program exists only for Windows and macOS. On WSL, let the Windows OneDrive sync, mark the folders you need as Always keep on this device, "
                                "and read them at /mnt/c/Users/<you>/OneDrive."),
        ),
        "steps": (
            Step("Install the Microsoft sign-in library", ("kit", "add"), {"kit": "microsoft"}),
            Step("Sign in to Microsoft", ("auth", "new"), {"forge": "microsoft"}),
            Step("See whether I am signed in", ("auth", "status")),
            Step("List the top of my OneDrive", ("onedrive", "list")),
        ),
    }
