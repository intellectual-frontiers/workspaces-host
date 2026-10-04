"""The editor, working with an AI, and extending ws-host."""
from __future__ import annotations

from ..core.registry import Step, topic


@topic("editor", "Use VS Code as the way to do everything ws-host does.")
def editor():
    return {
        "plain": "VS Code shows your workspace's state and lets you act on it with buttons.",
        "sections": (
            ("What you see", "A status line that says in plain words whether your machine is well. A Workspace view with every trusted tool, grouped by what "
                             "it is for. Every result is a page with buttons for what you can do next, and each button has a Show command link that gives "
                             "you the one line to paste in a terminal."),
            ("Learn", "The Learn command lists these same pages. Each step on a page is a button."),
            ("Decisions", "Anything only you may decide, such as trusting a repository, asks you in a dialog. Nothing, including an AI agent in the editor, can click it for you."),
            ("Safe by design", "The extension runs only the tools of repositories you trust and does nothing in VS Code's Restricted Mode. "
                               "It changes no setting and writes no file; the tools it runs do, when you choose."),
        ),
        "steps": (
            Step("Set up VS Code with the extension, helpful extensions and safe settings", ("vscode", "advance")),
            Step("Install only the extension", ("vscode", "add")),
            Step("Run the checks", ("check",)),
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
