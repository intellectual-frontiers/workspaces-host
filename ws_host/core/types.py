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
FORGE = register(Type("FORGE", ("github", "gitlab", "microsoft"), lambda v, ctx: None if v in ("github", "gitlab", "microsoft") else f"{v!r} is not github, gitlab or microsoft",
                      lambda ctx: ["github", "gitlab", "microsoft"]))
GUID_RX = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
DOMAIN_RX = re.compile(r"^(?=.{4,253}$)([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}$")
CLIENTID = register(Type("CLIENTID", ("0a1b2c3d-1111-2222-3333-444455556666", "shared"),
                         lambda v, ctx: None if GUID_RX.match(v) or v == "shared" else f"{v!r} is not an Application (client) ID: it looks like 0a1b2c3d-1111-2222-3333-444455556666, or say shared"))
TENANT = register(Type("TENANT", ("0a1b2c3d-1111-2222-3333-444455556666", "example.com", "common"),
                       lambda v, ctx: None if GUID_RX.match(v) or DOMAIN_RX.match(v) or v in ("common", "organizations", "consumers") else
                       f"{v!r} is not a Directory (tenant) ID: it looks like 0a1b2c3d-1111-2222-3333-444455556666, or is your organization's domain such as example.com"))
SHELL = register(Type("SHELL", ("bash", "fish"), lambda v, ctx: None if v in ("bash", "fish") else f"{v!r} is not bash or fish",
                      lambda ctx: ["bash", "fish"]))
# REPO and KIT resolve against the repositories and kits the machine knows; their validators are installed by the
# modules that own them (commands/repo.py, commands/kit.py) so the core stays free of those rules.
REPO = register(Type("REPO", ("github.com/org/repo", "repo"), lambda v, ctx: None))
KIT = register(Type("KIT", ("base", "press", "rust"), lambda v, ctx: None))
