"""Kits and the shell."""
from __future__ import annotations

from ..core.registry import Step, topic


@topic("kits", "Install the tools a kind of work needs, one kit at a time.")
def kits():
    return {
        "plain": "A kit is a set of tools for one kind of work, and ws-host installs it for you.",
        "sections": (
            ("The kits", "base is the everyday tools: git, gh, glab, search, images, a browser. press typesets books and PDFs. rust builds Rust programs. "
                         "shell gives you fish 4 and oh-my-posh."),
            ("Installing", "Packages come from your distribution, which needs your password, so ws-host tells you before it asks. Everything else is "
                           "downloaded, checked against a fingerprint, and unpacked in ~/.local/share/workspaces-host/tools. Without administrator rights you get "
                           "every download and are told what was left."),
            ("Which kit does a repository want", "It says so in its own .workspaces-host/ws-host.env (WS_HOST_KIT), and the update installs it."),
            ("Machines differ", "Debian and Ubuntu ship different versions. That is allowed. ws-host doctor prints your distribution and the version of every "
                                "tool in your kits so you can see the difference."),
        ),
        "steps": (
            Step("See the kits", ("kit", "list")),
            Step("See what a kit would install", ("kit", "show"), {"kit": "press"}),
            Step("Install the base kit", ("kit", "add"), {"kit": "base"}, "Run this one in a terminal; it asks for your password."),
            Step("Check everything again", ("doctor",)),
        ),
    }


@topic("shell", "bash and oh-my-posh work fine; fish 4 is the best experience.")
def shell():
    return {
        "plain": "bash with oh-my-posh is fully supported, and fish 4 with oh-my-posh is the best way to work.",
        "sections": (
            ("bash", "Your login shell is bash, and it stays bash. oh-my-posh works in it. Add this line to ~/.bashrc:\n\n"
                     "    eval \"$(oh-my-posh init bash --config ~/workspaces/github.com/intellectual-frontiers/workspaces-host/themes/coach.omp.json)\""),
            ("fish 4", "fish suggests and colors as you type, and oh-my-posh looks best in it. The shell kit installs fish 4 and oh-my-posh. "
                       "Try it without changing anything by typing fish. Add this line to ~/.config/fish/config.fish:\n\n"
                       "    oh-my-posh init fish --config ~/workspaces/github.com/intellectual-frontiers/workspaces-host/themes/coach.omp.json | source"),
            ("Making fish your login shell", "That is one separate step, and only you take it:\n\n    command -v fish | sudo tee -a /etc/shells\n    chsh -s $(command -v fish)\n\n"
                                              "ws-host never changes your login shell or your shell files."),
            ("The theme", "The coach theme is themes/coach.omp.json in your workspaces-host copy. oh-my-posh draws icons, so use a Nerd Font in your terminal."),
        ),
        "steps": (
            Step("Install fish and oh-my-posh", ("kit", "add"), {"kit": "shell"}, "Run this one in a terminal; it asks for your password."),
            Step("Check the shell kit", ("kit", "show"), {"kit": "shell"}),
        ),
    }
