"""The parser and runner: `ws-host <noun> <verb> [ID] [--options]` (0041-command-line FR-008, FR-010). Standard library only."""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import traceback
import types as _types
from dataclasses import dataclass, field

from .. import NAME, VERSION
from . import logs, registry as reg
from .registry import Command, Registry
from .render import render, use_color
from .resource import Action, Resource, WsError, usage_error
from .types import TYPES

GLOBAL_FLAGS = {"--json": "json", "--html": "html"}


@dataclass
class Ctx:
    registry: Registry
    surface: str = "cli"
    dry_run: bool = False
    debug: bool = False
    offline: bool = False
    values: dict = field(default_factory=dict)
    confirmed: bool = False     # the extension passes --confirmed only after its modal (0041 FR-051)

    def confirm(self, question: str) -> None:
        """A `decision` needs a confirmation only a person can give: a typed answer at a terminal, or the editor's modal
        (0041 FR-014, FR-051). Raises when neither is possible, so an agent without a terminal cannot decide."""
        if self.dry_run:
            return
        if self.surface == "editor" and self.confirmed:
            return
        if sys.stdin.isatty() and sys.stdout.isatty():
            sys.stdout.write(f"{question} Type yes to go ahead: ")
            sys.stdout.flush()
            if sys.stdin.readline().strip().lower() == "yes":
                return
            raise WsError("not-confirmed", "the person did not confirm", "Nothing was changed, because you did not answer yes.", exit_code=1)
        raise WsError("needs-person", "a decision needs a person", "This changes who is trusted, so only you can do it. Run it yourself in a terminal, or use the button in VS Code.", exit_code=1)


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # argparse would exit(2) with a trace-like usage text
        raise usage_error(message, f"I could not read that command ({message}). Run `{NAME} command list` to see what I can do.")


def _opt(name: str) -> str:
    return "--" + name.lower().replace("_", "-")


def build_parser(cmd: Command) -> argparse.ArgumentParser:
    p = _Parser(prog=f"{NAME} {cmd.id}", add_help=False)
    for a in cmd.args:
        if a.positional:
            p.add_argument(a.name, nargs="*" if a.multiple else ("?" if not a.required else None), default=[] if a.multiple else None)
        elif a.flag:
            p.add_argument(_opt(a.name), dest=a.name, action="store_true")
        else:
            p.add_argument(_opt(a.name), dest=a.name, action="append" if a.multiple else "store", default=None)
    if cmd.writes:
        p.add_argument("--dry-run", dest="dry_run", action="store_true")
    if cmd.category == "decision":
        p.add_argument("--confirmed", dest="confirmed", action="store_true")
    p.add_argument("--debug", action="store_true")
    p.add_argument("--offline", action="store_true")
    return p


def _split_global(argv: list[str]) -> tuple[list[str], str]:
    mode, rest = "text", []
    for a in argv:
        if a in GLOBAL_FLAGS:
            mode = GLOBAL_FLAGS[a]
        else:
            rest.append(a)
    return rest, mode


def _validate(cmd: Command, ns: argparse.Namespace, ctx: Ctx) -> dict:
    values = {}
    for a in cmd.args:
        v = getattr(ns, a.name, None)
        if v in (None, [], False):
            if a.required and not a.flag:
                raise usage_error(f"{a.name} is required", f"I need one more thing: {a.name}. Run `{NAME} command show {cmd.id}` to see how.")
            values[a.name] = v if v not in (None,) else ([] if a.multiple else None)
            continue
        items = v if isinstance(v, list) else [v]
        t = TYPES.get(a.type)
        for item in items:
            if a.choices and item not in a.choices:
                raise usage_error(f"{a.name} must be one of {', '.join(a.choices)}", f"{item!r} is not one of the choices: {', '.join(a.choices)}.")
            if t and not a.flag:
                problem = t.validate(item, ctx)
                if problem:
                    raise usage_error(f"{a.name}: {problem}; a {t.name} looks like {', '.join(t.examples)}",
                                      f"That value is not right: {problem}. It should look like {', '.join(t.examples)}.")
        values[a.name] = v
    return values


def _plan(cmd: Command, argv: list[str]) -> None:
    """0041 FR-002: a command that needs packages runs under uv against uv.lock, never resolving or upgrading."""
    if cmd.group and os.environ.get("WS_HOST_IN_GROUP") != cmd.group:
        uv = shutil.which("uv")
        if not uv:
            raise WsError("missing-prerequisite", "uv is not on PATH", "I need a tool called uv to run that command.", status="missing")
        env = dict(os.environ, WS_HOST_IN_GROUP=cmd.group)
        flags = ["--offline"] if os.environ.get("WS_HOST_OFFLINE") == "1" or "--offline" in argv else []
        os.execvpe(uv, [uv, "run", "--frozen", "--no-dev", "--group", cmd.group, *flags, "python", "-m", "ws_host", *argv], env)


def _programs(cmd: Command, registry: Registry) -> None:
    """0041 FR-006: a command whose program is missing fails with a hint naming the kit that supplies it."""
    from . import machine
    gone = [p for p in cmd.programs if shutil.which(p) is None]
    if not gone:
        return
    d = machine.distro()
    kits = [n for n, k in sorted(registry.kits.items()) if any(c.program in gone for c in k().checks(d))]
    acts = [Action(("kit", "add"), f"Install the {k} kit", {"kit": k}) for k in kits]
    raise WsError("missing-program", f"{', '.join(gone)} is not installed", f"I need {', '.join(gone)} for that, and it is not on this machine."
                  + (f" The {kits[0]} kit has it." if kits else ""), acts, status="missing")


def _emit(results, mode: str, registry: Registry, out) -> int:
    code = 0
    color = mode == "text" and use_color(out)
    for r in results:
        out.write(render(r, mode, registry, color) + "\n")
        code = max(code, r.exit_code)
        out.flush()
    return code


def run(argv: list[str], surface: str = "cli", out=None, err=None) -> int:
    out, err = out or sys.stdout, err or sys.stderr
    argv, mode = _split_global(list(argv))
    try:
        registry = reg.discover()
    except Exception as e:  # a broken module must not print a trace (0041 FR-020)
        err_r = WsError("internal", f"the registry could not be loaded: {type(e).__name__}: {e}",
                        "ws-host could not start because one of its own files is broken. Reinstalling it usually fixes this.").resource()
        out.write(render(err_r, mode) + "\n")
        return 1
    ctx = Ctx(registry, surface=os.environ.get("WS_HOST_SURFACE", surface),
              offline=os.environ.get("WS_HOST_OFFLINE") == "1")
    cmd, rest = None, []
    try:
        if not argv or argv[0] in ("-h", "--help"):
            cmd, rest = registry.get(("command", "list")), []
        elif argv[0] == "--version":
            out.write(f"{NAME} {VERSION}\n")
            return 0
        else:
            cmd, rest = registry.resolve(argv)
            if cmd is None:
                raise usage_error(f"no command '{' '.join(argv[:2])}'",
                                  f"I do not know a command called '{' '.join(argv[:2])}'.",
                                  [Action(("command", "list"), "See every command")])
        ns = build_parser(cmd).parse_args(rest)
        ctx.dry_run, ctx.debug = bool(getattr(ns, "dry_run", False)), ns.debug
        ctx.confirmed = bool(getattr(ns, "confirmed", False))
        ctx.offline = ctx.offline or ns.offline
        ctx.values = _validate(cmd, ns, ctx)
        _plan(cmd, argv)
        if not ctx.dry_run:
            _programs(cmd, registry)
        result = cmd.fn(ctx, **ctx.values)
        # A stream is emitted as it is produced, one document per line under --json (0041 FR-019).
        code = _emit(result if isinstance(result, _types.GeneratorType) else [result], mode, registry, out)
    except WsError as e:
        r = e.resource()
        out.write(render(r, mode, registry, mode == "text" and use_color(out)) + "\n")
        code = e.exit_code if e.exit_code is not None else r.exit_code
    except BrokenPipeError:
        return 0
    except Exception as e:  # 0041 FR-020: no stack trace as an error; the trace goes to the log, shown under --debug
        trace = traceback.format_exc()
        if ctx.debug:
            err.write(trace)
        err_r = WsError("internal", f"{type(e).__name__}: {e}", "Something went wrong inside ws-host. Run `ws-host doctor`, and use Get help if it keeps happening.").resource()
        out.write(render(err_r, mode, registry) + "\n")
        code = 1
    if cmd is not None and cmd.category != "read":
        logs.log(ctx.surface, cmd.id, _loggable(cmd, ctx), code)
    return code


def _loggable(cmd: Command, ctx: Ctx) -> dict:
    return {k: v for k, v in ctx.values.items() if v not in (None, [], False)} | ({"dry_run": True} if ctx.dry_run else {})


def main(argv: list[str]) -> int:
    return run(argv)
