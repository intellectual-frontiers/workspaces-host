"""`archon`: run a repository's command line, and make what it needs exist first (0011-archon FR-002, FR-004). Standard library only."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from . import profile, provider as prov, pyenv, requirements, system, toolchain as tc, versions

OK, MISSING, FAILED, USAGE = 0, 3, 1, 2


def _repo(a) -> Path:
    return Path(a.repo or os.getcwd()).resolve()


def _provider(a) -> prov.Provider:
    p = prov.load(_repo(a))
    if p is None:
        print(f"archon: {_repo(a)} declares no requirements (no {prov.FOLDER}/provider.toml)", file=sys.stderr)
        raise SystemExit(USAGE)
    return p


def _fail(e: Exception) -> int:
    print(f"❎ archon: {e}", file=sys.stderr)
    return getattr(e, "exit_code", FAILED)


def run(a) -> int:
    repo = _repo(a)
    env = profile.exported()
    if a.offline:
        env["ARCHON_OFFLINE"] = "1"
    try:
        if a.needs:
            env = requirements.environment(requirements.ensure(_provider(a), a.needs), env)
        exe = pyenv.uv()
    except (requirements.Unavailable, tc.ToolchainError, pyenv.EnvError) as e:
        return _fail(e)
    here = str(Path(__file__).resolve().parents[1])
    pythonpath = [str((repo / p).resolve()) for p in a.path] + [here] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath)
    env["ARCHON_PATH"] = here
    env.pop("VIRTUAL_ENV", None)
    argv = [exe, "run", "--no-project", "--quiet", "--python", pyenv.requires_python(repo), *(["--offline"] if a.offline or env.get("ARCHON_OFFLINE") else []),
            "--", "python", "-W", "ignore", "-m", a.module, *a.args]
    os.chdir(os.getcwd())
    os.execve(exe, argv, env)
    return FAILED


def ensure(a) -> int:
    try:
        results = requirements.ensure(_provider(a), a.names, offline=True if a.offline else None)
    except (requirements.Unavailable, tc.ToolchainError) as e:
        return _fail(e)
    if a.json:
        print(json.dumps({"requirements": [r.to_dict() for r in results]}, ensure_ascii=False))
    else:
        for r in results:
            print(f"✅ {r.name} {r.version} from {r.source}" + "".join(f"\n   {k}: {v}" for k, v in r.programs.items()))
    return OK


def generate(a) -> int:
    """Write a repository's translation of its entries into `mise` configuration and lock (0008-providers FR-006)."""
    try:
        changed = tc.lock(_provider(a), offline=bool(a.offline))
    except tc.ToolchainError as e:
        return _fail(e)
    print("\n".join(f"✅ {c}" for c in changed) if changed else "✅ the generated files are current")
    return OK


def doctor(a) -> int:
    prof = profile.current()
    print(f"profile      {prof.attendance} ({prof.why})")
    print(f"uv           {shutil.which('uv') or 'NOT FOUND: ' + pyenv.UV_HINT}")
    manager = system.detect()
    print(f"packages     {manager or 'no package manager found (apt, dnf, apk or brew)'}")
    p = prov.load(_repo(a))
    if p is None:
        print(f"repository   {_repo(a)} declares no requirements")
        return OK
    for name, e in sorted(p.entries.items()):
        if not e.satisfiable_by_computer:
            how = "pinned download (" + ("installed" if tc.install_path(p, e) else "not installed") + ")"
        else:
            exe, found = requirements._probe(e)
            if exe and found and versions.meets(found, e.minimum):
                how = f"path ({found})"
            else:
                offered = system.candidate(manager, e.packages.get(manager, [""])[0])[1] if manager and e.packages.get(manager) else None
                how = f"{manager} would install {offered}" if offered and versions.meets(offered, e.minimum) else "pinned download"
        print(f"{name:14} {how}")
    return OK


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="archon", description="Run a repository's command line and make what it needs exist first.")
    sub = ap.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="python -m MODULE ARGS, under the repository's Python, with its requirements available")
    r.add_argument("--repo"), r.add_argument("--path", action="append", default=[]), r.add_argument("--needs", action="append", default=[])
    r.add_argument("--offline", action="store_true")
    r.set_defaults(fn=run)
    e = sub.add_parser("ensure", help="make the named requirements available")
    e.add_argument("--repo"), e.add_argument("--json", action="store_true"), e.add_argument("--offline", action="store_true")
    e.add_argument("names", nargs="+")
    e.set_defaults(fn=ensure)
    g = sub.add_parser("generate", help="write the generated mise files and lock of a repository's entries")
    g.add_argument("--repo"), g.add_argument("--offline", action="store_true")
    g.set_defaults(fn=generate)
    d = sub.add_parser("doctor", help="say the profile and where each requirement would come from")
    d.add_argument("--repo")
    d.set_defaults(fn=doctor)
    argv = sys.argv[1:] if argv is None else argv
    rest: list[str] = []
    if argv and argv[0] == "run":         # every word after `--` belongs to the command (FR-002)
        if "--" not in argv or len(argv) == argv.index("--") + 1:
            ap.error("run needs `-- MODULE [ARGUMENT...]`")
        i = argv.index("--")
        argv, rest = argv[:i], argv[i + 1:]
    a = ap.parse_args(argv)
    if rest:
        a.module, a.args = rest[0], rest[1:]
    return a.fn(a)


def run_main() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    run_main()
