"""How ws-host presents itself to an editor (0041-command-line FR-064, FR-072): views, a title and icon for each noun and command, and what
the rows of a list show. Declared in code (ws_host/commands/presentation.py), emitted by `command list` and `command show`, and checked
here by `check registry`. Standard library only."""
from __future__ import annotations

import re
from pathlib import Path

STATUSES = ("ok", "warning", "error", "pending", "skipped", "info", "muted")
CODICONS = Path(__file__).resolve().parent / "codicons.txt"
ID = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
TITLE = re.compile(r"[A-Z][A-Za-z0-9 /'-]*…?")
MAX_TITLE = 40
LIST_KEYS = ("command", "rows", "id", "label", "description", "status", "status_map", "badge", "tooltip")


def codicons() -> set[str]:
    return {l.strip() for l in CODICONS.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")} if CODICONS.is_file() else set()


def needs_value(c) -> bool:
    """Whether a command asks for something before it can run, so its palette title ends with an ellipsis."""
    return any(a.required and not a.multiple for a in c.args)


def of_command(c) -> dict:
    """The `title` and `icon` a command row and `command show` carry."""
    out = {}
    if c.title:
        out["title"] = c.title
    if c.icon:
        out["icon"] = c.icon
    return out


def block(reg) -> dict:
    """The `presentation` object of `command list`."""
    views = [{"id": v.id, "title": v.title, "icon": v.icon, "order": v.order, **({"description": v.description} if v.description else {})}
             for v in sorted(reg.views.values(), key=lambda v: (v.order, v.id))]
    nouns = []
    for n in sorted(reg.nouns.values(), key=lambda n: n.name):
        row = {"noun": n.name, "title": n.title, "icon": n.icon}
        if n.view:
            row["view"] = n.view
        if n.list:
            row["list"] = dict(n.list)
        nouns.append(row)
    return {"views": views, "nouns": nouns}


def problems(reg) -> list[str]:
    """What is wrong with the declarations themselves (0041 FR-072); the data the commands return is checked by the tests."""
    out: list[str] = []
    icons = codicons()
    if not icons:
        out.append(f"{CODICONS.name} lists no codicon, so icons cannot be checked (0041 FR-072)")
    bad = lambda who, v: out.append(f"{who}: icon {v!r} is not a codicon id of the glyph map this repository pins (0041 FR-072)") if v not in icons else None
    for vid, v in sorted(reg.views.items()):
        if not ID.fullmatch(vid):
            out.append(f"view {vid}: an id is lowercase words joined by hyphens (0041 FR-072)")
        if not v.title:
            out.append(f"view {vid}: needs a title (0041 FR-072)")
        bad(f"view {vid}", v.icon)
    commands_by_noun = {c.noun for c in reg.commands.values() if c.noun}
    for name, n in sorted(reg.nouns.items()):
        if name not in commands_by_noun:
            out.append(f"noun {name}: presented, but no command has it as its noun (0041 FR-072)")
        if not n.title:
            out.append(f"noun {name}: needs a title (0041 FR-072)")
        bad(f"noun {name}", n.icon)
        if n.view is not None and n.view not in reg.views:
            out.append(f"noun {name}: view {n.view!r} is declared by no one (0041 FR-072)")
        if n.list is not None:
            out += _list_problems(reg, name, n.list)
    for noun in sorted(commands_by_noun - set(reg.nouns)):
        out.append(f"noun {noun}: has commands and no icon or title (0041 FR-064)")
    for c in sorted(reg.commands.values(), key=lambda c: c.id):
        who = f"command {c.id}"
        if c.title is None:
            if "editor" in c.surfaces:
                out.append(f"{who}: is offered to the editor and has no palette title (0041 FR-072)")
            continue
        if not TITLE.fullmatch(c.title) or len(c.title) > MAX_TITLE:
            out.append(f"{who}: the title {c.title!r} is a verb and an object in capitals, at most {MAX_TITLE} characters, with nothing else (0041 FR-072)")
        elif c.title.endswith("…") != needs_value(c):
            out.append(f"{who}: the title {c.title!r} " + ("ends with an ellipsis though nothing is asked for" if c.title.endswith("…")
                                                          else "needs an ellipsis: the command asks for a value") + " (0041 FR-072)")
        if c.icon:
            bad(who, c.icon)
    return out


def _list_problems(reg, noun: str, lst: dict) -> list[str]:
    who = f"noun {noun}: list"
    out = [f"{who}: {k!r} is not a field of a list's presentation (0041 FR-064)" for k in lst if k not in LIST_KEYS]
    for k in ("command", "rows", "id", "label"):
        if not isinstance(lst.get(k), str) or not lst[k]:
            out.append(f"{who} needs {k} (0041 FR-072)")
    c = reg.commands.get(tuple(str(lst.get("command", "")).split()))
    if c is None:
        out.append(f"{who}: the command {lst.get('command')!r} is not in the registry (0041 FR-072)")
    else:
        if c.category != "read" or "editor" not in c.surfaces:
            out.append(f"{who}: {c.id} is not a read command the editor runs (0041 FR-072)")
        if needs_value(c):
            out.append(f"{who}: {c.id} asks for a value, so an editor cannot run it to list rows (0041 FR-072)")
    for k, v in (lst.get("status_map") or {}).items():
        if v not in STATUSES:
            out.append(f"{who}: the status {v!r} (for {k!r}) is not one of {', '.join(STATUSES)} (0041 FR-064)")
    if lst.get("status_map") and not lst.get("status"):
        out.append(f"{who}: a status_map needs the status field it maps (0041 FR-072)")
    return out
