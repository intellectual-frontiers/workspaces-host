"""`completion list|add`: Tab completion for ws-host in bash and fish (0006-onboarding FR-023)."""
from __future__ import annotations

from ..core import registry as reg
from ..core.registry import Arg, command
from ..core.resource import OK, Resource, WsError
from ..core.types import TYPES
from ..lib import completion


@command("completion", "list", category="read", summary="List the values an argument can take, which is what Tab offers",
         args=(Arg("kind", "STRING", positional=True, required=True, help="the kind of argument, such as REPO or KIT"),))
def completion_list(ctx, kind):
    t = TYPES.get(kind.upper())
    if t is None:
        raise WsError("unknown-kind", f"no argument kind '{kind}'", f"I do not know an argument kind called '{kind}'. The kinds are: {', '.join(sorted(TYPES))}.", exit_code=2)
    try:
        values = sorted(str(v) for v in t.complete(None))
    except Exception:
        values = []
    return Resource("completion", t.name, {"plain": f"{len(values)} values for {t.name}.", "values": values})


@command("completion", "add", category="setup", summary="Set up Tab completion for ws-host in bash or fish",
         args=(Arg("shell", "SHELL", positional=True, required=True, help="bash or fish"),), surfaces=("cli", "editor"))
def completion_add(ctx, shell):
    r = completion.install(shell, ctx.dry_run)
    plain = (f"Nothing was changed. I would set up Tab completion for {shell} in {r['file']}." if ctx.dry_run else r["plain"])
    return Resource("completion-add", shell, {**r, "plain": plain}, status=OK)
