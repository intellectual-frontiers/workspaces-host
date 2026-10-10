"""The `aws` kit: the AWS command line, the SAM CLI and the CDK, each the newest release (0003-kits FR-017)."""
from __future__ import annotations

from ..core.kit import Check, Floating, Kit
from ..install import floating

AWS = Floating("aws-cli", floating.aws_cli, binaries={"aws": "bin/aws", "aws_completer": "bin/aws_completer"}, kind="zip", strip=0, in_place=True,
               steps=(("./aws/install", "-i", "{dest}/aws-cli", "-b", "{dest}/bin"),))
SAM = Floating("aws-sam-cli", floating.github("aws/aws-sam-cli", {"x86_64": r"^aws-sam-cli-linux-x86_64\.zip$", "aarch64": r"^aws-sam-cli-linux-arm64\.zip$"}),
               binaries={"sam": "bin/sam"}, kind="zip", strip=0, in_place=True, steps=(("./install", "-i", "{dest}/sam", "-b", "{dest}/bin"),))
CDK = Floating("aws-cdk", floating.npm("aws-cdk"), binaries={"cdk": "bin/cdk"}, manager="npm", package="aws-cdk")


class Aws(Kit):
    name = "aws"
    summary = "the AWS CLI v2, the SAM CLI and the CDK, always the newest release"
    plain = "deploy to Amazon Web Services: the aws, sam and cdk commands."

    def apt(self, distro):
        return ["ca-certificates", "gnupg", "less"]       # gnupg checks AWS's signature on the download

    def downloads(self, distro):
        return [AWS, SAM, CDK]

    def checks(self, distro):
        return [Check("aws", "aws"), Check("sam", "sam"), Check("cdk", "cdk")]
