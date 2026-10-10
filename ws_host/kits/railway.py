"""The `railway` kit: the Railway command line, the newest release (0003-kits FR-017)."""
from __future__ import annotations

from ..core.kit import Check, Floating, Kit
from ..install import floating

RAILWAY = Floating("railway", floating.github_auto("railwayapp/cli"), binaries={"railway": "railway"}, auto=True)


class Railway(Kit):
    name = "railway"
    summary = "the Railway CLI, always the newest release"
    plain = "deploy to Railway: the railway command."

    def apt(self, distro):
        return ["ca-certificates"]

    def downloads(self, distro):
        return [RAILWAY]

    def checks(self, distro):
        return [Check("railway", "railway")]
