"""The first day, and what to do when something goes wrong."""
from __future__ import annotations

from ..core.registry import Step, topic

INSTALL = "curl -fsSL https://raw.githubusercontent.com/intellectual-frontiers/workspaces-host/main/install.sh | sh"


@topic("start", "Your first steps: sign in, copy your starter repositories, and move into VS Code.")
def start():
    return {
        "plain": "🎉 ws-host is installed. Do these things in order, and you will be working in VS Code.",
        "sections": (
            ("1️⃣  Sign in to GitHub (you only do this once)",
             "Type the line below. It shows a short code and a web address. Open the address in your browser, type the code, and press Authorize. "
             "You never type a password into this window.\n\n    ws-host auth new github"),
            ("2️⃣  Copy your starter repositories",
             "Two repositories come with you: .github, the shared examples and rules, and workspaces-host, this tool. This copies them to your "
             "workspaces folder and keeps them up to date without ever touching your own changes. Run it as often as you like.\n\n    ws-host workspace advance"),
            ("3️⃣  Open VS Code",
             "Install VS Code on Windows from https://code.visualstudio.com/ and add its WSL extension, then open your first repository from here:\n\n"
             "    cd ~/workspaces/github.com/intellectual-frontiers/.github\n    code ."),
            ("4️⃣  Let ws-host set VS Code up",
             "It installs the Workspace extension, a short list of helpful extensions and a few safe settings, and never changes a setting you made. "
             "Then reload VS Code: press Ctrl+Shift+P and run Developer: Reload Window.\n\n    ws-host vscode advance"),
            ("5️⃣  Keep going in VS Code",
             "Press Ctrl+Shift+P and run Workspace: Learn. Every page there has a button for each step, and the status line at the bottom says in plain words whether "
             "your machine is well. You can do everything else from VS Code."),
            ("📂 Choose which repositories you work in",
             "To add one, type its address. It is copied now and every time you update:\n\n    ws-host repo add github.com/ORG/REPO\n\n"
             "To remove one or change the list, open your settings file in VS Code and edit the line that starts with WS_HOST_REPOS:\n\n"
             "    code ~/.config/workspaces-host/ws-host.env"),
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
             "ws-host improves often. A new terminal window tells you in one line when a newer version is waiting. To get it, and see what is new:\n\n"
             "    ws-host update advance"),
            ("🆘 Stuck?",
             "Run ws-host doctor to see what is wrong in plain words, or Workspace: Get help in VS Code for a report with no passwords in it, and paste it to "
             "someone who helps you. The guide's troubleshooting page lists every problem I know of: https://intellectual-frontiers.github.io/workspaces-host/"),
        ),
        "steps": (
            Step("Sign in to GitHub", ("auth", "new"), {"forge": "github"}),
            Step("Copy your starter repositories", ("workspace", "advance")),
            Step("Set VS Code up", ("vscode", "advance")),
            Step("Give your terminal the prompt again", ("shell", "add"), {"shell": "bash"}, "setup already did this once"),
            Step("Update ws-host", ("update", "advance")),
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
