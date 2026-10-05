"""The editor, working with an AI, and extending ws-host."""
from __future__ import annotations

from ..core.registry import Step, topic


@topic("editor", "Use VS Code as the way to do everything ws-host does.")
def editor():
    return {
        "plain": "VS Code shows your workspace's state, through the IF Console, and lets you act on it with buttons.",
        "sections": (
            ("The IF Console", "ws-host does not ship an editor extension of its own. VS Code's window onto every repository's command line, ws-host's included, "
                               "is the IF Console, which the public root provides. ws-host vscode ensure installs the package from the public root's latest release when it "
                               "has one, after checking its fingerprint. Otherwise it builds it from that repository's code, and asks you once to trust that repository, "
                               "because building runs its code."),
            ("What you see", "A Home view that says what needs you, each with the exact line that fixes it and a Run button; the views each command line asks "
                             "for (ws-host asks for Workspace, Kits and Setup); checks as tests; and a page for every resource."),
            ("Open your repositories together", "vscode ensure writes workspaces.code-workspace in your workspaces folder, listing the repositories you work in. "
                                                "Open it with File, Open Workspace from File, and the IF Console shows each repository's own commands."),
            ("Learn", "IF Console: Learn a Topic lists the same pages as ws-host help. Each step on a page is a button."),
            ("Decisions", "Anything only you may decide, such as trusting a repository, asks you in a dialog. Nothing, including an AI agent in the editor, can click it for you."),
            ("Safe by design", "The IF Console runs only the command lines of repositories you trust and does nothing in VS Code's Restricted Mode. "
                               "It collects nothing and opens no network connection."),
        ),
        "steps": (
            Step("Set up VS Code with the IF Console, helpful extensions and safe settings", ("vscode", "ensure")),
            Step("Run the checks", ("check",)),
        ),
    }


@topic("workspace-file", "Open all your repositories in one VS Code window, from one file.")
def workspace_file():
    return {
        "plain": "One file, workspaces.code-workspace, lists every repository you work in. Open it and they are all in one window.",
        "sections": (
            ("The default", "Start from workspaces.code-workspace in your workspaces folder, ~/workspaces. ws-host writes it and keeps its list of repositories "
                            "current, so it holds every repository you have copied in one window."),
            ("Make your own", "The default is a starting point. Make other files in ~/workspaces when one list mixes things that do not belong together: one per Git "
                              "service (github.code-workspace, gitlab.code-workspace) or one per organization on the same service "
                              "(intellectual-frontiers.code-workspace). Copy the default, delete the folders you do not want, and open the copy. "
                              "ws-host vscode ensure only manages the default and never touches yours."),
            ("Open it", "In a terminal, run: code ~/workspaces/workspaces.code-workspace. In VS Code, choose File, Open Workspace from File. "
                        "Afterwards VS Code reopens it by itself, and File, Open Recent lists it first; its title bar starts with the word Workspaces, "
                        "so you can tell it from a single-repository window."),
            ("Add a repository", "Run ws-host repo add with its address, then ws-host vscode ensure. The repository appears in the window's Explorer."),
            ("Where the files live", "Workspace files go in your workspaces folder, ~/workspaces, and every repository is listed relative to that folder, "
                                     "for example github.com/acme/tools. That is why the file keeps working if you move or rename the folder."),
            ("What is in the file", "A list of repositories with short names, a title that starts with Workspaces, and the recommendation to use the IF Console. "
                                    "ws-host adds what is missing and never changes a line you wrote yourself."),
            ("When it looks wrong", "If the Explorer shows one repository, you opened a folder instead of the file: close the window and open the file. "
                                    "If a repository is missing, run ws-host vscode ensure."),
        ),
        "steps": (
            Step("Write or refresh the workspace file", ("vscode", "ensure")),
        ),
    }


@topic("ai", "Work with an AI agent without handing it your decisions.")
def ai():
    return {
        "plain": "An AI agent can run everything ws-host does except the decisions that are yours.",
        "sections": (
            ("How it works", "Agents use the terminal and ask for JSON: ws-host doctor --json. Every command returns the same shape, with the actions that can come next."),
            ("What it cannot do", "Trusting a repository needs you at a terminal prompt or at the editor's dialog. Installing packages needs your password. "
                                  "Neither is offered to an agent."),
            ("What it should read first", "ws-host context gives it everything about your machine with no passwords in it, and .claude/skills/ws-host/SKILL.md "
                                          "lists every command. That file is generated from the code, so it is never out of date."),
        ),
        "steps": (
            Step("Give an AI the report", ("context",)),
            Step("List every command", ("command", "list")),
        ),
    }


@topic("extend", "Add a command or a kit by asking an AI to write it in Python.")
def extend():
    return {
        "plain": "Everything ws-host does is Python code, so extending it means asking an AI to add a Python file.",
        "sections": (
            ("The rule", "A command is a Python module in ws_host/commands. A kit is a Python module in ws_host/kits. A help page is a Python module in ws_host/help. "
                         "Adding the file adds the thing; nothing else lists it. I chose code over configuration files because an AI changes code easily and a "
                         "test can run it."),
            ("Packages", "A module imports only the standard library at the top. If it needs a package, that package goes in a dependency group in pyproject.toml, "
                         "uv locks it in uv.lock, and the module imports it inside the function that uses it. That keeps help, the command list and doctor working "
                         "with nothing installed."),
            ("How to ask", "Tell the AI what you want in plain words, point it at .claude/skills/ws-host/SKILL.md and at an existing module to copy, and ask it "
                           "to add tests. Then run the four checks."),
            ("The four checks", "doctor says whether the registry has a conflict. check says whether the pieces agree. test runs the tests. fresh says whether "
                                "the generated reference and the agent skill are current; docs generate and skill generate rewrite them."),
            ("Whose is it", "If it helps you, it helps everyone. Open a pull request."),
        ),
        "steps": (
            Step("Check the registry", ("doctor",)),
            Step("Run every check", ("check",)),
            Step("Run the tests", ("test",)),
            Step("Rewrite the generated reference", ("docs", "generate")),
            Step("Rewrite the agent skill", ("skill", "generate")),
        ),
    }
