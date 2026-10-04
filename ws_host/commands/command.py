"""`command list` and `command show` (0041-command-line FR-012): the registry, read through the orchestrator itself."""
from __future__ import annotations

from ..core.registry import Arg, command, discover
from ..core.resource import Action, Link, Resource, WsError


def _describe(c) -> dict:
    return {
        "id": c.id, "noun": c.noun, "verb": c.verb, "category": c.category, "summary": c.summary,
        "surfaces": list(c.surfaces), "group": c.group, "programs": list(c.programs), "module": c.module,
        "args": [{"name": a.name, "type": a.type, "positional": a.positional, "required": a.required,
                  "multiple": a.multiple, "flag": a.flag, "choices": list(a.choices)} for a in c.args],
    }


@command("command", "list", category="read", summary="List every command")
def command_list(ctx):
    cmds = sorted(discover().commands.values(), key=lambda c: c.id)
    return Resource("command-list", "commands", {
        "plain": f"ws-host can do {len(cmds)} things. Here they are.",
        "commands": [{"id": c.id, "category": c.category, "summary": c.summary} for c in cmds],
    }, links=[Link("show", ("command", "show"), {"ID": c.id.split()}) for c in cmds[:0]])


@command("command", "show", category="read", summary="Show one command in full",
         args=(Arg("ID", "COMMAND", positional=True, required=True, multiple=True, help="the command's words"),))
def command_show(ctx, ID):
    words = tuple(ID)
    c = discover().get(words)
    if not c:
        raise WsError("unknown-command", f"no command '{' '.join(words)}'", f"I do not know a command called '{' '.join(words)}'.",
                      [Action(("command", "list"), "See every command")], exit_code=2)
    return Resource("command", c.id, {"plain": f"'{c.id}': {c.summary}.", **_describe(c)},
                    links=[Link("all commands", ("command", "list"))])
