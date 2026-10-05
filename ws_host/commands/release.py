"""`release build` and `release publish`, and the `release` and `reproducible` sections of `check`: a release made on a maintainer's machine, checked, and published to GitHub Releases
(0007-releases). No continuous-integration service takes part."""
from __future__ import annotations

import os
from pathlib import Path

from .. import VERSION
from ..core.registry import Arg, command, section
from ..core.resource import Action, FAILED, OK, Resource, WsError
from ..lib import release

OUTPUT = Arg("output", "PATH", help="where the release's files go (default: dist/ in this repository)")


def _out(output) -> Path:
    return Path(output).resolve() if output else release.dist_dir()


def _wrap(e: release.ReleaseError) -> WsError:
    actions = [Action(("doctor",), "Check this machine")] if e.code == "missing-program" else []
    return WsError(f"release-{e.code}", str(e), e.plain, actions, exit_code=3 if e.code == "missing-program" else 1)


@command("release", "build", category="build", summary="Build a release: the wheel, the app tarball, the Workspaces Console and their checksums",
         args=(OUTPUT, Arg("skip_tests", flag=True, help="leave out the Console's unit tests (a release is never published without them)")))
def release_build(ctx, output, skip_tests=False):
    out = _out(output)
    names = release.names()
    if ctx.dry_run:
        return Resource("release", VERSION, {"plain": f"Nothing was built. I would build release {VERSION} into {out}.", "output": str(out),
                                             "files": [{"name": v, "status": "would build"} for v in names.values()]})
    try:
        steps = release.build(out, tests=not skip_tests)
    except release.ReleaseError as e:
        raise _wrap(e)
    files = [{"name": v, "status": "ok", "plain": f"{(out / v).stat().st_size:,} bytes"} for v in names.values()]
    return Resource("release", VERSION, {"plain": f"Release {VERSION} is built in {out}. Check it before you publish it.", "output": str(out),
                                         "steps": steps, "files": files, "tests_run": not skip_tests},
                    actions=[Action(("check",), "Check the release", {"sections": ["release"]})], status=OK)


def _finding(name: str, plain: str) -> dict:
    return {"level": "error", "where": name, "message": plain, "next": "fix it, then run `ws-host release build` and `ws-host check release` again"}


def _built() -> Path:
    out = Path(os.environ.get("WS_HOST_RELEASE_DIR") or release.dist_dir())
    if not (out / release.SUMS).is_file():
        raise FileNotFoundError("a built release (run `ws-host release build`)")
    return out


@section("release", suites=("slow",), summary="a built release is complete, its checksums match, its files hold what they should and it runs (named: it needs a built release)")
def release_section(ctx):
    """0007-releases FR-009: versions, files, checksums, wheel metadata, package contents, the tarball run in place."""
    try:
        return [_finding(f.name, f.plain) for f in release.check(_built()) if not f.ok]
    except release.ReleaseError as e:
        return [_finding("release", e.plain)]


@section("reproducible", suites=("slow",), summary="building the release again gives the same bytes (named: it builds everything a second time)")
def reproducible_section(ctx):
    """0007-releases FR-004, FR-009: a second build, with the Console's tests left out, compared with every byte of the built release."""
    out = _built()
    try:
        rows = release.check(out, rebuild=True)
    except release.ReleaseError as e:
        return [_finding("release", e.plain)]
    return [_finding(f.name, f.plain) for f in rows if not f.ok and f.name.startswith("A rebuild")]


@command("release", "publish", category="decision", summary="Tag this commit and publish the release to GitHub Releases, with your own gh sign-in",
         args=(OUTPUT,))
def release_publish(ctx, output):
    out = _out(output)
    problems = release.publish_problems(out)
    if problems:
        raise WsError("release-not-ready", "; ".join(problems), "I did not publish anything, because " + "; ".join(problems) + ".", exit_code=1)
    notes = release.notes(out)
    names = release.names()
    if ctx.dry_run:
        return Resource("release", VERSION, {"plain": f"Nothing was published. I would tag this commit {release.tag()} and publish {len(names)} files to GitHub Releases.",
                                             "tag": release.tag(), "files": [{"name": v, "status": "would upload"} for v in names.values()], "notes": notes})
    ctx.confirm(f"This publishes {release.tag()} to the public GitHub repository, where anyone can download it and it cannot be quietly taken back.")
    try:
        address = release.publish(out).strip()
    except release.ReleaseError as e:
        raise _wrap(e)
    return Resource("release", VERSION, {"plain": f"Release {VERSION} is published: {address}", "tag": release.tag(), "address": address,
                                         "files": [{"name": v, "status": "uploaded"} for v in names.values()]}, status=OK)
