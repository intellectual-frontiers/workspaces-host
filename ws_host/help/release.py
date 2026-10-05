"""Making a release of ws-host and the Workspaces Console (for the people who maintain them)."""
from __future__ import annotations

from ..core.registry import Step, topic


@topic("release", "Make a release: build it, check that anyone could rebuild it, and publish it to GitHub Releases.")
def release():
    return {
        "plain": "A release is four files on GitHub Releases. You build it on your own machine, prove it is reproducible, and publish it yourself; no hosted service is involved.",
        "sections": (
            ("Before you start", "Install the pinned tools once in your copy of workspaces-host, and sign in to GitHub. You only need the tools to build:\n\n"
                                 "    mise install --locked\n    ws-host auth new github"),
            ("Set the version", "The version is written once, as VERSION in ws_host/__init__.py. The Workspaces Console's console/package.json must say the same; "
                                "the build stops and tells you if they differ. Commit and push the change."),
            ("Build it", "This makes the program tarball, the wheel, the Workspaces Console package and their checksums in dist/, after type-checking, "
                         "linting and testing the Console:\n\n    ws-host release build"),
            ("Check it", "This checks the versions, the checksums, what each file holds, and that the tarball runs where it is unpacked. The second line "
                         "builds everything again and compares every byte, which proves anyone could repeat your build:\n\n"
                         "    ws-host check release\n    ws-host check reproducible"),
            ("Publish it", "This is your decision, and it cannot be quietly taken back, so it asks you to type yes. It tags this commit and uploads the files "
                           "with your own GitHub sign-in. It refuses while there are changes that are not committed, the commit is not pushed, the tag exists "
                           "or a check fails:\n\n    ws-host release publish"),
            ("What people use", "Nobody follows a tag. They pin a file by its address and its SHA-256; the release notes show the exact lines."),
        ),
        "steps": (
            Step("Build the release", ("release", "build")),
            Step("Check the release", ("check",), {"sections": ["release"]}),
            Step("Check that building it again gives the same bytes", ("check",), {"sections": ["reproducible"]}),
            Step("Publish the release", ("release", "publish")),
            Step("Check your machine", ("doctor",)),
        ),
    }
