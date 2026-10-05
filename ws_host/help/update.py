"""Keeping ws-host itself current."""
from __future__ import annotations

from ..core.registry import Step, topic


@topic("update", "Keep ws-host itself up to date, and learn when a newer version is waiting.")
def update():
    return {
        "plain": "ws-host improves often. One command brings the newest version, and a new terminal window tells you when one is waiting.",
        "sections": (
            ("Update ws-host", "This looks for news and moves ws-host forward. It only ever moves forward, and it leaves your copy exactly as it was, "
                               "with a plain reason, when you have changes of your own in it:\n\n    ws-host update advance"),
            ("Is one waiting?", "Every new terminal window looks in the background, at most every six hours, and never makes you wait. When a newer "
                                "version is ready, the window says so in one line. To look right now and see what is new:\n\n    ws-host update status"),
            ("Everything at once", "ws-host workspace advance updates ws-host along with your repositories, so running it is enough. "
                                   "ws-host update advance is the quick way when you only want ws-host."),
            ("Turning the reminder off", "The reminder is a few lines in the marked block of your ~/.bashrc, which is the same block that gives you your prompt. "
                                         "Delete the lines that mention update, or all of the block. ws-host doctor also tells you when an update is waiting."),
        ),
        "steps": (
            Step("See whether a newer ws-host is waiting", ("update", "status")),
            Step("Update ws-host", ("update", "advance")),
            Step("Update everything", ("workspace", "advance")),
            Step("Check your machine", ("doctor",)),
        ),
    }
