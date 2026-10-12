"""archon, the runner underneath every command line, and how it tells a person from an agent."""
from __future__ import annotations

from ..core.registry import Step, topic


@topic("archon", "How archon makes everything a command needs exist, and how it knows whether a person is there.")
def archon():
    return {
        "plain": ("archon is the runner under ws-host, agora and every other command line. It gets whatever a command needs before the command runs, "
                  "so nobody installs a tool by hand, and it behaves the same for a person, an AI agent and a CI job."),
        "sections": (
            ("What it needs", "Only uv. A computer with uv runs a repository's command line through archon, and archon fetches the Python, the "
                              "packages and the programs the command names. ws-host is the friendly front for a person and is never required:\n\n"
                              "    uvx --from git+https://github.com/intellectual-frontiers/workspaces-host archon doctor --repo ."),
            ("Where a program comes from", "In this order: a program already on your computer that is new enough; your package manager, when it "
                                           "offers a new enough version (apt, dnf, apk or brew, installed without questions); the entry's own download, "
                                           "checked against its fingerprint before it is unpacked. When none works the command stops and says why for each."),
            ("A person or nobody", "archon assumes nobody is there unless something says a person is: the Workspaces Console, or a terminal with no CI or "
                                   "agent variable set. For a person it shows a spinner, colour, emoji and a progress bar, in the terminal and in VS Code. "
                                   "For an agent it asks nothing and prints plain lines. To say which, set ARCHON_ATTENDANCE to attended or unattended."),
            ("See it work", "doctor says who archon thinks is there, which package manager it found, and where each program would come from. "
                            "It changes nothing."),
        ),
        "steps": (
            Step("See whether your machine is well", ("doctor",)),
            Step("Learn the daily work", ("help",), {"topic": "start"}),
        ),
    }
