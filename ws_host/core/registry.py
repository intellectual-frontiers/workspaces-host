"""The registry, kept in code and discovered by presence (0041-command-line FR-007, 0001-ws-host FR-010).

A module under `ws_host/commands/` adds its commands; a module under `ws_host/kits/` adds its kits; nothing lists them.
"""
from __future__ import annotations

import ast
import importlib
import pkgutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

CATEGORIES = ("read", "check", "record", "build", "generate", "decision", "setup")
VERBS = ("list", "show", "status", "check", "build", "generate", "add", "set", "record", "new", "advance", "publish", "serve")
SURFACES = ("cli", "editor", "mcp")
# 0041 FR-022: the default exposure beyond the terminal, by category.
DEFAULT_SURFACES = {
    "read": ("cli", "editor", "mcp"), "check": ("cli", "editor", "mcp"), "record": ("cli", "editor", "mcp"),
    "build": ("cli", "editor", "mcp"), "generate": ("cli", "editor", "mcp"),
    "decision": ("cli", "editor"), "setup": ("cli",),
}
REPOWIDE = ("check", "test", "doctor", "context")


@dataclass
class Arg:
    name: str                      # in capitals for a positional (an ID), the option's name otherwise
    type: str = "STRING"
    positional: bool = False
    required: bool = False
    multiple: bool = False
    flag: bool = False             # a boolean option
    help: str = ""
    choices: tuple[str, ...] = ()


@dataclass
class Command:
    words: tuple[str, ...]
    category: str
    summary: str
    fn: Callable
    args: tuple[Arg, ...] = ()
    surfaces: tuple[str, ...] = ()
    programs: tuple[str, ...] = ()
    group: str | None = None       # a dependency group of pyproject.toml, None for the plain interpreter
    module: str = ""

    @property
    def id(self) -> str:
        return " ".join(self.words)

    @property
    def noun(self) -> str | None:
        return self.words[0] if len(self.words) == 2 else None

    @property
    def verb(self) -> str:
        return self.words[-1]

    @property
    def writes(self) -> bool:
        return self.category not in ("read", "check")


@dataclass
class Section:
    name: str
    fn: Callable
    suites: tuple[str, ...] = ()
    programs: tuple[str, ...] = ()
    watched: tuple[str, ...] = ()
    summary: str = ""
    module: str = ""


@dataclass
class Registry:
    commands: dict[tuple[str, ...], Command] = field(default_factory=dict)
    sections: dict[str, Section] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)
    kits: dict[str, type] = field(default_factory=dict)
    modules: list[str] = field(default_factory=list)

    def get(self, words) -> Command | None:
        return self.commands.get(tuple(words))

    def add(self, cmd: Command) -> None:
        prev = self.commands.get(cmd.words)
        if prev is not None:
            self.conflicts.append(f"two commands are named '{cmd.id}': {prev.module} and {cmd.module}")
            return
        self.commands[cmd.words] = cmd

    def add_section(self, s: Section) -> None:
        if s.name in self.sections:
            self.conflicts.append(f"two check sections are named '{s.name}': {self.sections[s.name].module} and {s.module}")
            return
        self.sections[s.name] = s

    def resolve(self, argv: list[str]) -> tuple[Command | None, list[str]]:
        """The command whose words open argv (a noun and a verb, or a repository-wide name), and the rest."""
        words = [a for a in argv[:2]]
        if len(words) == 2 and tuple(words) in self.commands:
            return self.commands[tuple(words)], argv[2:]
        if words and (words[0],) in self.commands:
            return self.commands[(words[0],)], argv[1:]
        return None, argv


REGISTRY = Registry()
_loading: str = ""


def command(*words: str, category: str, summary: str, args: tuple[Arg, ...] = (), surfaces: tuple[str, ...] | None = None,
            programs: tuple[str, ...] = (), group: str | None = None):
    """Declare a command: `@command("repo", "list", category="read", summary="...")`."""
    def deco(fn):
        REGISTRY.add(Command(tuple(words), category, summary, fn, tuple(args),
                             tuple(surfaces) if surfaces is not None else DEFAULT_SURFACES[category],
                             tuple(programs), group, _loading or fn.__module__))
        return fn
    return deco


def section(name: str, *, suites: tuple[str, ...] = (), programs: tuple[str, ...] = (), watched: tuple[str, ...] = (), summary: str = ""):
    def deco(fn):
        REGISTRY.add_section(Section(name, fn, tuple(suites), tuple(programs), tuple(watched), summary, _loading or fn.__module__))
        return fn
    return deco


def _modules(package: str) -> list[str]:
    pkg = importlib.import_module(package)
    return sorted(m.name for m in pkgutil.iter_modules(pkg.__path__, package + "."))


def discover() -> Registry:
    """Import every module under the commands and kits packages; adding a module adds its commands and kits."""
    global _loading
    if REGISTRY.modules:
        return REGISTRY
    from .kit import Kit
    for package in ("ws_host.commands", "ws_host.kits"):
        for name in _modules(package):
            REGISTRY.modules.append(name)
            _loading = name
            try:
                mod = importlib.import_module(name)
            finally:
                _loading = ""
            if package.endswith("kits"):
                for obj in vars(mod).values():
                    if isinstance(obj, type) and issubclass(obj, Kit) and obj is not Kit and obj.__module__ == name:
                        if obj.name in REGISTRY.kits:
                            REGISTRY.conflicts.append(f"two kits are named '{obj.name}': {REGISTRY.kits[obj.name].__module__} and {name}")
                        else:
                            REGISTRY.kits[obj.name] = obj
    REGISTRY.conflicts.extend(module_level_imports())
    return REGISTRY


def module_level_imports(package_dirs=None) -> list[str]:
    """0041 FR-005: a command or kit module imports only the standard library at module level."""
    from .paths import repo_root
    out = []
    dirs = package_dirs or [repo_root() / "ws_host" / "commands", repo_root() / "ws_host" / "kits"]
    stdlib = set(sys.stdlib_module_names) | {"ws_host", "__future__"}
    for d in dirs:
        for f in sorted(Path(d).glob("*.py")):
            tree = ast.parse(f.read_text(encoding="utf-8"), str(f))
            for node in _toplevel(tree.body):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module.split(".")[0]]
                for n in names:
                    if n not in stdlib:
                        out.append(f"{f.parent.name}/{f.name}:{node.lineno} imports {n}, which is not the standard library, at module level")
    return out


def _toplevel(body):
    """Statements that run when a module is imported: not the bodies of functions."""
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        yield node
        for attr in ("body", "orelse", "finalbody"):
            sub = getattr(node, attr, None)
            if isinstance(sub, list):
                yield from _toplevel(sub)
        for h in getattr(node, "handlers", []) or []:
            yield from _toplevel(h.body)
