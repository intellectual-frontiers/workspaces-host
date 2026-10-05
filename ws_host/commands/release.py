"""`release build`, `release check` and `release publish`: a release made on a maintainer's machine, checked, and published to GitHub Releases
(0007-releases). No continuous-integration service takes part."""
from __future__ import annotations

from pathlib import Path

from .. import VERSION
from ..core.registry import Arg, command
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
                    actions=[Action(("release", "check"), "Check the release", {"output": str(out)} if output else {})], status=OK)


@command("release", "check", category="check", summary="Check a built release: versions, checksums, contents, that it runs, and with --rebuild that it is reproducible",
         args=(OUTPUT, Arg("rebuild", flag=True, help="build it again and compare every byte")))
def release_check(ctx, output, rebuild=False):
    out = _out(output)
    try:
        findings = release.check(out, rebuild=rebuild)
    except release.ReleaseError as e:
        raise _wrap(e)
    bad = [f for f in findings if not f.ok]
    rows = [{"name": f.name, "status": "ok" if f.ok else "fail", "plain": f.plain} for f in findings]
    plain = (f"Release {VERSION} passes all {len(findings)} checks." if not bad else
             f"Release {VERSION} fails {len(bad)} of {len(findings)} checks: " + "; ".join(f"{f.name} ({f.plain})" for f in bad) + ".")
    return Resource("release", VERSION, {"plain": plain, "output": str(out), "checks": rows, "reproducible": bool(rebuild and not bad)},
                    actions=[] if bad else [Action(("release", "publish"), "Publish the release")],
                    status=FAILED if bad else OK)


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
