"""The `cloudflare` kit: Wrangler (Workers and Pages) and cloudflared (tunnels), each the newest release (0003-kits FR-017)."""
from __future__ import annotations

from ..core.kit import Check, Floating, Kit
from ..install import floating

WRANGLER = Floating("wrangler", floating.npm("wrangler"), binaries={"wrangler": "bin/wrangler"}, manager="npm", package="wrangler")
CLOUDFLARED = Floating("cloudflared", floating.github("cloudflare/cloudflared", {"x86_64": r"^cloudflared-linux-amd64$", "aarch64": r"^cloudflared-linux-arm64$"}),
                       binaries={"cloudflared": "cloudflared"}, kind="file")


class Cloudflare(Kit):
    name = "cloudflare"
    summary = "Wrangler (Workers, Pages) and cloudflared (tunnels), always the newest release"
    plain = "deploy to Cloudflare: the wrangler and cloudflared commands."

    def apt(self, distro):
        return ["ca-certificates"]

    def downloads(self, distro):
        return [WRANGLER, CLOUDFLARED]

    def checks(self, distro):
        return [Check("wrangler", "wrangler"), Check("cloudflared", "cloudflared")]
