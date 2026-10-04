"""Resources, links and actions (0041-command-line FR-016 to FR-019). Standard library only."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .. import AUDIENCE, NAME, SCHEMA_PREFIX

SCHEMA_VERSION = 1
OK, FAILED, MISSING = "ok", "failed", "missing"
EXIT = {OK: 0, FAILED: 1, MISSING: 3}
# 0041 FR-055: a displayed command has no shell-specific quoting, so a value outside this set cannot be printed.
SAFE = re.compile(r"^[A-Za-z0-9_./:=@%+,-]+$")


@dataclass
class Action:
    """A library call with typed fields, carrying its category and surfaces (0041 FR-017)."""
    words: tuple[str, ...]
    label: str
    fields: dict[str, Any] = field(default_factory=dict)
    needs: tuple[str, ...] = ()           # argument names only a person can supply: a button or quick-pick, never a printed command
    enabled: bool = True
    reason: str | None = None

    def to_dict(self, registry=None) -> dict:
        cmd = registry.get(self.words) if registry else None
        return {
            "label": self.label,
            "words": list(self.words),
            "fields": self.fields,
            "needs": list(self.needs),
            "category": cmd.category if cmd else None,
            "surfaces": list(cmd.surfaces) if cmd else [],
            "enabled": self.enabled,
            "reason": self.reason,
            "command": command_line(self, registry),
        }


@dataclass
class Link:
    rel: str
    words: tuple[str, ...]
    fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, registry=None) -> dict:
        a = Action(self.words, self.rel, self.fields)
        return {"rel": self.rel, "words": list(self.words), "fields": self.fields, "command": command_line(a, registry)}


def command_line(action: Action, registry=None) -> str | None:
    """One pasteable line generated from the call, or None when it cannot be (a value is missing or needs quoting)."""
    if action.needs:
        return None
    parts = [NAME, *action.words]
    cmd = registry.get(action.words) if registry else None
    fields = dict(action.fields)
    if cmd:
        for a in cmd.args:
            if a.positional and a.name in fields:
                v = fields.pop(a.name)
                for item in (v if isinstance(v, (list, tuple)) else [v]):
                    parts.append(str(item))
    for name, v in fields.items():
        flag = "--" + name.lower().replace("_", "-")
        if v is True:
            parts.append(flag)
        elif v in (False, None):
            continue
        else:
            for item in (v if isinstance(v, (list, tuple)) else [v]):
                parts += [flag, str(item)]
    if any(not SAFE.match(p) for p in parts):
        return None
    return " ".join(parts)


@dataclass
class Resource:
    kind: str
    id: str
    data: dict[str, Any]
    links: list[Link] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    status: str = OK
    version: int = SCHEMA_VERSION

    @property
    def plain(self) -> str:
        return str(self.data.get("plain", ""))

    @property
    def exit_code(self) -> int:
        return EXIT.get(self.status, 1)

    def to_dict(self, registry=None) -> dict:
        return {
            "schema": f"{SCHEMA_PREFIX}/{self.kind}@{self.version}",
            "audience": AUDIENCE,
            "kind": self.kind,
            "id": self.id,
            "data": self.data,
            "links": [l.to_dict(registry) for l in self.links],
            "actions": [a.to_dict(registry) for a in self.actions],
        }


class WsError(Exception):
    """An error that becomes an error resource (0041 FR-020)."""

    def __init__(self, code: str, message: str, plain: str | None = None, actions: list[Action] | None = None,
                 status: str = FAILED, exit_code: int | None = None):
        super().__init__(message)
        self.code, self.message, self.plain = code, message, plain or message
        self.actions, self.status = actions or [], status
        self.exit_code = exit_code

    def resource(self) -> Resource:
        r = Resource("error", self.code, {"code": self.code, "message": self.message, "plain": self.plain},
                     actions=self.actions, status=self.status)
        return r


def usage_error(message: str, plain: str | None = None, actions: list[Action] | None = None) -> WsError:
    e = WsError("usage", message, plain or "That is not a command I understand. Here is what I can do.", actions)
    e.exit_code = 2
    return e
