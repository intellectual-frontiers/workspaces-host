"""`command list` and `command show` (0041-command-line FR-012): the registry, read through the orchestrator itself."""
from __future__ import annotations

from ..core.registry import Arg, command, discover
from ..core.types import TYPES
from ..core.resource import Action, Link, Resource, WsError, wire_surfaces


def _choices(a) -> list[str]:
    """What the type can complete (0041 FR-013): the editor offers these in a quick-pick."""
    t = TYPES.get(a.type)
    try:
        return list(t.complete(None)) if t else []
    except Exception:
        return []


def _describe(c) -> dict:
    """The wire shape of `command show` that every orchestrator uses (0041-command-line FR-064)."""
    usage = ["ws-host", *c.words]
    for a in c.args:
        usage.append(("[" + a.name.upper() + ("..." if a.multiple else "") + "]") if a.positional and not a.required else
                     (a.name.upper() + ("..." if a.multiple else "")) if a.positional else f"[--{_flag(a.name)}{'' if a.flag else ' ' + a.type}]")
    return {
        "id": c.id, "noun": c.noun, "verb": c.verb, "category": c.category, "help": c.summary, "group": c.group,
        "arguments": [{"name": a.name, "type": a.type, "help": a.help, "required": a.required, "words": a.multiple and a.positional,
                       "many": a.multiple, "choices": list(a.choices or _choices(a))} for a in c.args if a.positional],
        "options": [{"flag": "--" + _flag(a.name), "type": "flag" if a.flag else a.type, "help": a.help, "multiple": a.multiple,
                     "required": a.required, "choices": list(a.choices or _choices(a))} for a in c.args if not a.positional],
        "usage": " ".join(usage), "surfaces": wire_surfaces(c.surfaces), "programs": list(c.programs), "isolated": False,
    }


def _flag(name: str) -> str:
    return name.lower().replace("_", "-")


@command("command", "list", category="read", summary="List every command")
def command_list(ctx):
    cmds = sorted(discover().commands.values(), key=lambda c: c.id)
    return Resource("command-list", "commands", {
        "plain": f"ws-host can do {len(cmds)} things. Here they are.", "count": len(cmds),
        "commands": [{"id": c.id, "category": c.category, "group": c.group, "surfaces": wire_surfaces(c.surfaces), "help": c.summary} for c in cmds],
    })


@command("command", "show", category="read", summary="Show one command in full",
         args=(Arg("words", "COMMAND", positional=True, required=True, multiple=True, help="the command's words"),))
def command_show(ctx, words):
    words = tuple(words)
    c = discover().get(words)
    if not c:
        raise WsError("unknown-command", f"no command '{' '.join(words)}'", f"I do not know a command called '{' '.join(words)}'.",
                      [Action(("command", "list"), "See every command")], exit_code=2)
    return Resource("command", c.id, {"plain": f"'{c.id}': {c.summary}.", **_describe(c)},
                    links=[Link("all commands", ("command", "list"))])
