"""The first day, and what to do when something goes wrong."""
from __future__ import annotations

from ..core.registry import Step, topic

INSTALL = "curl -fsSL https://raw.githubusercontent.com/intellectual-frontiers/workspaces-host/main/install.sh | sh"


@topic("start", "Your first day: install ws-host and bring your workspace up.")
def start():
    return {
        "plain": "You need two commands today: one to install ws-host, and one to set up everything else.",
        "sections": (
            ("Install it", f"Paste this into a terminal on Debian or Ubuntu, including Ubuntu under WSL on Windows:\n\n    {INSTALL}\n\n"
                           "It needs python3 and git, and installs uv for you if it is missing. Run it again any time; it never touches your work."),
            ("Bring everything up", "ws-host workspace advance signs you in if you are not, copies the repositories your workspace lists, "
                                    "brings the ones you already have up to date without touching your changes, installs the kits they ask for, "
                                    "and checks your machine. Run it as often as you like."),
            ("Put the editor on top", "ws-host vscode add installs the VS Code extension. After that you can do all of this with buttons: "
                                      "open the Workspace view and use Learn to read these same pages."),
        ),
        "steps": (
            Step("Check your machine", ("doctor",)),
            Step("Install the VS Code extension", ("vscode", "add")),
            Step("Bring everything up", ("workspace", "advance")),
            Step("See where things stand", ("workspace", "status")),
        ),
    }


@topic("recover", "What to do when something fails, or when a repository was left alone.")
def recover():
    return {
        "plain": "Nothing ws-host does can lose your work, so when something fails, start by reading what it says.",
        "sections": (
            ("A repository was left alone", "That is not an error. ws-host leaves a repository exactly as it was when you have changes you have not "
                                            "committed, when your commits and the shared ones have both moved on, when it is not on a branch, or when a rebase or "
                                            "merge is in progress. Your work is safe. Commit or push it yourself, then run the update again."),
            ("A copy or update failed", "It says why in git's own words. If it says you are not signed in, sign in, then run the update again."),
            ("A kit is partly installed", "Run kit add again for it. Installing a package needs your password, so run it in a terminal; "
                                          "ws-host says so before it asks."),
            ("Ask for help", "Get help in the editor, or ws-host context and ws-host doctor in a terminal, gives you one report with no passwords in it. "
                             "Paste it to a person or to an AI."),
        ),
        "steps": (
            Step("Check your machine", ("doctor",)),
            Step("See each repository's state", ("repo", "status")),
            Step("Sign in again", ("auth", "new"), {"forge": "github"}),
            Step("Gather a report to paste", ("context",)),
        ),
    }
