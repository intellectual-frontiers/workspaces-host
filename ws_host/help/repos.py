"""Repositories, signing in and trust."""
from __future__ import annotations

from ..core.registry import Step, topic


@topic("repos", "Copy your repositories and keep them up to date without risking your work.")
def repos():
    return {
        "plain": "Your repositories live in one folder, and updating them never touches anything you changed.",
        "sections": (
            ("Where they go", "Every repository lives at ~/workspaces/<host>/<org>/<repo>. Your own list is WS_HOST_REPOS in "
                              "~/.config/workspaces-host/ws-host.env, and each repository can list the ones it works beside in its own "
                              ".workspaces-host/ws-host.env."),
            ("Updating", "ws-host fetches, then moves a repository forward only when that is a plain fast-forward. It never pulls, rebases, "
                         "merges, or stashes. If anything of yours is in the way, the repository is left exactly as it was, and ws-host says why."),
            ("Git's own Sync button", "VS Code's Sync button follows your git settings. Set pull.ff to only so it behaves the same way; "
                                      "ws-host doctor offers that as a button and never does it unasked."),
        ),
        "steps": (
            Step("See the repositories I know", ("repo", "list")),
            Step("Copy the missing ones", ("repo", "add"), {"all": True}),
            Step("Bring them up to date", ("repo", "advance"), {"all": True}),
            Step("See each one's state", ("repo", "status")),
            Step("Make git's Sync button safe", ("workspace", "set"), {"pull_ff_only": True}),
        ),
    }


@topic("signin", "Sign in to GitHub or GitLab with a one-time code.")
def signin():
    return {
        "plain": "Signing in takes a code and a web page; you never type a password into a terminal.",
        "sections": (
            ("What happens", "ws-host asks GitHub for a one-time code and shows you the code and an address. You open the address in your browser, "
                             "type the code, and approve. In VS Code the notification has a button that copies the code and opens the browser."),
            ("GitLab", "List your GitLab hosts in WS_HOST_GITLAB_HOSTS and sign in to each one the same way."),
            ("Where it is kept", "In the credential storage of gh and glab, which is where they keep it. ws-host stores no password."),
        ),
        "steps": (
            Step("See whether I am signed in", ("auth", "status")),
            Step("Sign in to GitHub", ("auth", "new"), {"forge": "github"}),
            Step("Sign in to GitLab", ("auth", "new"), {"forge": "gitlab"}),
        ),
    }


@topic("trust", "Decide whose code may run on your machine.")
def trust():
    return {
        "plain": "Copying a repository never lets its code run; only you can allow that.",
        "sections": (
            ("What trust means", "A trusted repository's own tools can run in the editor, and its kits can be used. An untrusted one is only files."),
            ("Trust is never inherited", "A repository that another repository lists is copied and not trusted. A repository's own file can never grant trust, "
                                         "not even to its own organization. Only your own configuration (WS_HOST_TRUSTED) or your own act can."),
            ("How", "Trusting is a decision: you confirm it yourself, at the prompt in a terminal or in the dialog in VS Code. An AI agent cannot do it for you."),
            ("What it is", "One link in ~/.local/share/workspaces-host/enabled/, and the commit at which you trusted it. ws-host doctor warns you, without "
                           "blocking, when a trusted repository's kits have changed since."),
        ),
        "steps": (
            Step("See which repositories are trusted", ("repo", "list")),
            Step("Trust a repository", ("repo", "set"), {"trusted": True}),
            Step("Stop trusting a repository", ("repo", "set"), {"untrusted": True}),
        ),
    }
