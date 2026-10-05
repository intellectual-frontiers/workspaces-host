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


@topic("shell", "Your prompt, bash and fish.")
def shell():
    return {
        "plain": "Setup gave your terminal its prompt. bash with oh-my-posh is fully supported, and fish 4 with oh-my-posh is the best way to work.",
        "sections": (
            ("bash", "Your login shell is bash, and it stays bash. Setup added a few marked lines to ~/.bashrc, after keeping a copy of the file, so "
                     "oh-my-posh draws the ws-host-pretty prompt in every new window. To see it in this one, type exec bash -l. To put the lines back "
                     "after deleting them, or after an edit, run:\n\n    ws-host shell add bash\n\n"
                     "To go back to your old prompt, delete the lines between '>>> workspaces-host' and '<<< workspaces-host'. To stop setup "
                     "adding them again, put WS_HOST_PROMPT=no in ~/.config/workspaces-host/ws-host.env."),
            ("A Nerd Font, once, on Windows", "ws-host-pretty draws icons from a Nerd Font, a font made for terminals. Install one on Windows, "
                                              "then choose it in Windows Terminal. Without one you see boxes. The guide has the three steps with links. "
                                              "If you would rather not install a font, use the plain theme:\n\n    ws-host shell add bash --plain\n\n"
                                              "and put WS_HOST_PROMPT=plain in ~/.config/workspaces-host/ws-host.env so setup keeps it plain."),
            ("fish 4", "fish suggests and colors as you type, and oh-my-posh looks best in it. The shell kit installs fish 4 and oh-my-posh by default, "
                       "and setup gives fish the same prompt in ~/.config/fish/config.fish. Try it without changing anything by typing fish."),
            ("Making fish your login shell", "That is one separate step, and only you take it:\n\n    command -v fish | sudo tee -a /etc/shells\n    chsh -s $(command -v fish)\n\n"
                                              "ws-host never changes your login shell, and it edits a shell file only when you run shell add."),
            ("Tab completion", "Press Tab and the shell finishes ws-host for you: its commands, their options, and the things they work on, such as your "
                               "repositories and kits. Setup sets this up in bash, and in fish when it is installed, by putting one file where each shell "
                               "looks for completions, so no startup file is touched and the file is renewed whenever setup runs. To redo it by hand:\n\n"
                               "    ws-host completion add bash\n    ws-host completion add fish\n\n"
                               "It starts in a new terminal window. In bash it needs the bash-completion package, which the base kit installs."),
            ("The themes", "Both are in the themes folder of your workspaces-host copy. ws-host-pretty is the default, with Nerd Font icons. "
                         "ws-host-plain uses only emoji and lines, so it needs no special font. To change one, copy it to your own folder, edit it "
                         "(the settings are explained at https://ohmyposh.dev/docs/configuration/overview), and put its path in the marked lines "
                         "of ~/.bashrc, or of fish's config.fish, in place of the theme path."),
        ),
        "steps": (
            Step("Give bash the prompt again", ("shell", "add"), {"shell": "bash"}),
            Step("Use the plain prompt, with no Nerd Font", ("shell", "add"), {"shell": "bash", "plain": True}),
            Step("Give fish the prompt", ("shell", "add"), {"shell": "fish"}),
            Step("Set up Tab completion in bash again", ("completion", "add"), {"shell": "bash"}),
            Step("Set up Tab completion in fish again", ("completion", "add"), {"shell": "fish"}),
            Step("Install fish and oh-my-posh if setup could not", ("kit", "add"), {"kit": "shell"}, "Run this one in a terminal; it asks for your password."),
            Step("Check the shell kit", ("kit", "show"), {"kit": "shell"}),
        ),
    }
