"""The first day, and what to do when something goes wrong."""
from __future__ import annotations

from ..core.registry import Step, topic

INSTALL = "curl -fsSL https://raw.githubusercontent.com/intellectual-frontiers/workspaces-host/main/install.sh | sh"


@topic("start", "Your first steps: sign in, set everything up with one command, and move into VS Code.")
def start():
    return {
        "plain": "🎉 ws-host is installed. Do these things in order, and you will be working in VS Code.",
        "sections": (
            ("1️⃣  Sign in to GitHub (you only do this once)",
             "Type the line below. It shows a short code and a web address. Open the address in your browser, type the code, and press Authorize. "
             "You never type a password into this window.\n\n    ws-host auth new github"),
            ("2️⃣  Set everything up",
             "One command does it all. It copies your starter repositories, .github (the shared examples and rules) and workspaces-host (this tool), builds the "
             "Workspaces Console for VS Code, installs every program they need and the helpful VS Code extensions, and keeps it all up to date without ever touching your own "
             "changes. Long steps show a spinner with the seconds and how much has arrived. Run it as often as you like.\n\n    ws-host workspace ensure"),
            ("3️⃣  Open VS Code",
             "Install VS Code on Windows from https://code.visualstudio.com/ and add its WSL extension, then open your workspace from here:\n\n"
             "    code ~/workspaces/workspaces.code-workspace\n\n"
             "The Workspaces Console is in the Activity Bar. Its Home says what needs you, with a button on each line."),
            ("4️⃣  Keep going in VS Code",
             "Press Ctrl+Shift+P and run Workspaces Console: Learn a Topic; every page there has a button for each step. To work in another repository, run "
             "Workspaces Console: Add Repository and type its address; it is copied, joins the workspace and, when it comes from your own organization, needs no trust step. "
             "To get everything up to date later, run Workspaces Console: Update ws-host. You can do everything else from VS Code."),
            ("🎨 Your prompt is ready",
             "Setup already gave your terminal a colorful prompt that shows where you are and what git is doing. It lives in a few marked "
             "lines of your ~/.bashrc, which you can delete any time, and you will see it in a new terminal window, or right now if you type:\n\n"
             "    exec bash -l\n\n"
             "fish is nicer still: it suggests and colors what you type as you go. It is installed too. Type fish to try it, and bash is still "
             "there when you want it.\n\n    fish\n\nTo make fish what every new window opens, see: ws-host help shell.\n\n"
             "Try pressing Tab after typing ws-host and a space: the shell shows every command, and finishes the one you start."),
            ("🔤 One thing on Windows: a Nerd Font",
             "The prompt draws small icons from a Nerd Font. Install one on Windows and choose it in Windows Terminal, and the boxes turn into icons. "
             "The guide has the three steps, and ws-host help shell has the rest. To skip the font, use the plain prompt:\n\n    ws-host shell add bash --plain"),
            ("🔄 Stay up to date",
             "ws-host improves often. A new terminal window tells you in one line when a newer version is waiting. One command brings everything current: ws-host, your repositories, "
             "the editor, and the programs they pin:\n\n"
             "    ws-host update"),
            ("🆘 Stuck?",
             "Run ws-host doctor to see what is wrong in plain words, or Workspaces Console: Get Help in VS Code for a report with no passwords in it, and paste it to "
             "someone who helps you. The guide's troubleshooting page lists every problem I know of: https://intellectual-frontiers.github.io/workspaces-host/"),
        ),
        "steps": (
            Step("Sign in to GitHub", ("auth", "new"), {"forge": "github"}),
            Step("Set everything up", ("workspace", "ensure")),
            Step("Give your terminal the prompt again", ("shell", "add"), {"shell": "bash"}, "setup already did this once"),
            Step("Update everything", ("update",)),
            Step("See where things stand", ("workspace", "status")),
            Step("Check your machine", ("doctor",)),
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
