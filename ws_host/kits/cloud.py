"""The `cloud` kit: every official deployment destination's command line, for a deployment engineer or a pipeline that pushes to any of them (0003-kits FR-017)."""
from __future__ import annotations

from ..core.kit import Kit
from .aws import Aws
from .azure import Azure
from .cloudflare import Cloudflare
from .railway import Railway

PARTS = (Aws, Azure, Cloudflare, Railway)


def _each(method: str, distro: dict) -> list:
    seen, out = set(), []
    for part in PARTS:
        for item in getattr(part(), method)(distro):
            key = item if isinstance(item, str) else getattr(item, "name", id(item))
            if key not in seen:
                seen.add(key)
                out.append(item)
    return out


class Cloud(Kit):
    name = "cloud"
    summary = "the aws, azure, cloudflare and railway kits together"
    plain = "deploy to AWS, Azure, Cloudflare or Railway: aws, sam, cdk, az, azd, wrangler, cloudflared and railway."

    def apt(self, distro):
        return _each("apt", distro)

    def downloads(self, distro):
        return _each("downloads", distro)

    def checks(self, distro):
        return _each("checks", distro)
