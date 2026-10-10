"""The `modern-cli` kit: makes bash, fish and git use the modern tools the base kit installs (0003-kits FR-019): eza for ls, bat for cat, btop for top, zoxide's z, fzf's keys and delta for git."""
from __future__ import annotations

from ..core.kit import Check, Kit
from . import _tools

USED = ("eza", "bat", "btop", "zoxide", "fzf", "delta")


class ModernCli(Kit):
    name = "modern-cli"
    summary = "bash, fish and git use eza, bat, btop, zoxide, fzf and delta, with the common aliases"
    plain = "your terminal's ls, cat, top, cd and git diff become the modern, colorful versions, and ll, la, .. work the way you expect."

    def downloads(self, distro):
        return [t for t in _tools.TOOLS if t.name in USED]

    def configure(self, ctx):
        from ..lib import modern
        r = modern.apply(ctx.offline, ctx.dry_run)
        if not r["changed"]:
            return [("ok", "bash, fish and git already use the modern tools.")]
        names = " and ".join(r["files"])
        return [("ok", f"Changed {names}. A copy of each was kept first. Open a new terminal window, or type `exec bash`, to see it. Icons need a Nerd Font in your terminal: the guide has the steps.")]

    def checks(self, distro):
        return [Check(p, p) for p in USED]
