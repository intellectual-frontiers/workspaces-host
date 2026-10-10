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
            ("Work accounts", "Many organizations do not allow Microsoft's shared sign-in app. The first time you sign in, ws-host tells you where to click in the Microsoft Entra admin center to register one, "
                              "asks for its Application (client) ID and Directory (tenant) ID, checks them as you type and keeps them for that account; you set no variable and edit no file. "
                              "For a home account answer shared. ws-host auth set microsoft CLIENT_ID TENANT --host work changes them later."),
            ("If Microsoft says you do not have access", "After you pick your account, a page that says 'You don't have access to this' means your organization has not allowed the shared sign-in app. "
                                                        "It is not a problem with your account. Register an app of your own and give ws-host its two IDs, as above."),
            ("Where the sign-in is kept", "In your system keyring when there is one. On a machine without one, such as most WSL setups, in a file only you can read under ~/.IdentityService, and ws-host says so."),
            ("A synced folder", "OneDrive's own sync program exists only for Windows and macOS. On WSL, let the Windows OneDrive sync, mark the folders you need as Always keep on this device, "
                                "and read them at /mnt/c/Users/<you>/OneDrive."),
        ),
        "steps": (
            Step("Install the Microsoft sign-in library", ("kit", "add"), {"kit": "microsoft"}),
            Step("Sign in to Microsoft", ("auth", "new"), {"forge": "microsoft"}),
            Step("Change which app signs an account in", ("auth", "set"), {"forge": "microsoft"}),
            Step("See whether I am signed in", ("auth", "status")),
            Step("List the top of my OneDrive", ("onedrive", "list")),
        ),
    }
