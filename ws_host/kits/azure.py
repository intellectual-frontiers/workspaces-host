"""The `azure` kit: the Azure CLI and the Azure Developer CLI, each the newest release (0003-kits FR-017)."""
from __future__ import annotations

from ..core.kit import Check, Floating, Kit
from ..install import floating

AZ = Floating("azure-cli", floating.pypi("azure-cli"), binaries={"az": "bin/az"}, manager="pip", package="azure-cli")
AZD = Floating("azure-dev", floating.github_auto("Azure/azure-dev"), binaries={"azd": "azd-linux-amd64|azd-linux-arm64|azd"}, auto=True)


class Azure(Kit):
    name = "azure"
    summary = "the Azure CLI (az) and the Azure Developer CLI (azd), always the newest release"
    plain = "deploy to Microsoft Azure: the az and azd commands."

    def apt(self, distro):
        return ["ca-certificates"]

    def downloads(self, distro):
        return [AZ, AZD]

    def checks(self, distro):
        return [Check("az", "az"), Check("azd", "azd", version_args=("version",))]
