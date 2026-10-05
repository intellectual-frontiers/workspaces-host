"""Typed arguments (0041-command-line FR-013): each type validates, completes and gives examples, in one place."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Type:
    name: str
    examples: tuple[str, ...]
    validate: Callable[[str, object], str | None]       # (value, ctx) -> problem or None
    complete: Callable[[object], list[str]] = lambda ctx: []


TYPES: dict[str, Type] = {}


def register(t: Type) -> Type:
    TYPES[t.name] = t
    return t


def _pattern(name, regex, examples):
    rx = re.compile(regex)
    return register(Type(name, examples, lambda v, ctx: None if rx.match(v) else f"{v!r} is not a {name}"))


STRING = register(Type("STRING", ("text",), lambda v, ctx: None))
PATH = register(Type("PATH", ("/home/me/file",), lambda v, ctx: None))
COMMAND = _pattern("COMMAND", r"^[a-z][a-z0-9-]*(?: [a-z][a-z0-9-]*)?$", ("doctor", "repo list"))
SECTION = _pattern("SECTION", r"^[a-z][a-z0-9-]*$", ("registry", "launcher"))
FORGE = register(Type("FORGE", ("github", "gitlab"), lambda v, ctx: None if v in ("github", "gitlab") else f"{v!r} is not github or gitlab",
                      lambda ctx: ["github", "gitlab"]))
SHELL = register(Type("SHELL", ("bash", "fish"), lambda v, ctx: None if v in ("bash", "fish") else f"{v!r} is not bash or fish",
                      lambda ctx: ["bash", "fish"]))
# REPO and KIT resolve against the repositories and kits the machine knows; their validators are installed by the
# modules that own them (commands/repo.py, commands/kit.py) so the core stays free of those rules.
REPO = register(Type("REPO", ("github.com/org/repo", "repo"), lambda v, ctx: None))
KIT = register(Type("KIT", ("base", "press", "rust"), lambda v, ctx: None))
