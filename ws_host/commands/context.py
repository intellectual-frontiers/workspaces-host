"""`context [RESOURCE]`: what a person or an AI needs to be helped (0041-command-line FR-038, FR-057).

Together with `doctor` it is the "Get help" report: bounded, deterministic in shape, and with every secret removed.
"""
from __future__ import annotations

from .. import VERSION
from ..core import config, paths, registry as reg
from ..core.registry import Arg
from ..core.resource import Action, Resource, WsError
from . import doctor as doctor_cmd, command as command_cmd

SECRET_HINTS = ("TOKEN", "SECRET", "PASSWORD", "KEY", "CREDENTIAL")


def public_config(cfg: config.Config) -> dict:
    return {k: ("(set)" if any(h in k.upper() for h in SECRET_HINTS) else v) for k, v in sorted(cfg.values.items())}


@reg.command("context", category="read", summary="Everything needed to get help with this machine, with secrets removed",
             args=(Arg("RESOURCE", "STRING", positional=True, help="machine (default) or command:WORDS"),))
def context(ctx, RESOURCE):
    kind, _, ident = (RESOURCE or "machine").partition(":")
    registry = reg.discover()
    if kind == "command":
        c = registry.get(tuple(ident.replace("+", " ").split()))
        if not c:
            raise WsError("unknown-resource", f"no command '{ident}'", f"I do not know a command called '{ident}'.", exit_code=2)
        parts = {"command": command_cmd._describe(c)}
    elif kind == "machine":
        d = doctor_cmd.report()
        parts = {"doctor": {"checks": d["checks"], "kits": d["kits"], "distro": d["distro"], "python": d["python"], "uv": d["uv"], "git": d["git"]}}
    else:
        raise WsError("unknown-resource", f"no resource kind '{kind}'", "I can describe `machine` or `command:WORDS`.", exit_code=2)
    cfg = config.load()
    data = {
        "plain": "This is a report you can paste to a person or an AI to get help. It holds no passwords or tokens.",
        "resource": f"{kind}:{ident}" if ident else kind,
        "version": VERSION,
        "paths": {"config": str(paths.config_file()), "data": str(paths.data_dir()), "state": str(paths.state_dir()),
                  "cache": str(paths.cache_dir()), "workspaces": str(cfg.workspaces)},
        "configuration": public_config(cfg),
        **parts,
        "left_out": ["the contents of secrets.env", "environment variables", "file contents"],
    }
    return Resource("context", data["resource"], data, actions=[Action(("doctor",), "Check this machine")])
