"""How ws-host looks in an editor (0041-command-line FR-064): its views, its nouns, and each command's palette title and icon.

Nothing here runs anything. `command list` and `command show` emit it, `check registry` checks it (0041 FR-072), and the IF Console
draws its sidebar, rows and command palette from it, so the editor holds no knowledge of ws-host."""
from __future__ import annotations

from ..core import registry as reg

# Views, in the order the editor lists them; 10 is the editor's own Home (0041 FR-064).
reg.view("workspace", "Workspace", "repo", 20, "Your repositories and how they stand")
reg.view("kits", "Kits", "package", 30, "The tools each kind of work needs")
reg.view("setup", "Setup", "settings-gear", 40, "Sign-in, the editor, your prompt and Tab completion")

reg.noun("repo", "Repository", "repo", "workspace", {
    "command": "repo list", "rows": "repositories", "id": "id", "label": "id", "description": "path", "status": "status", "tooltip": ["trust", "listed_by"]})
reg.noun("workspace", "Workspace", "home", "workspace")
reg.noun("kit", "Kit", "package", "kits", {
    "command": "kit list", "rows": "kits", "id": "name", "label": "name", "description": "plain", "status": "status",
    "status_map": {"ok": "ok", "warn": "warning"}, "tooltip": ["missing"]})
reg.noun("auth", "Sign-in", "account", "setup")
reg.noun("vscode", "VS Code", "extensions", "setup")
reg.noun("shell", "Prompt", "terminal", "setup")
reg.noun("completion", "Tab completion", "keyboard", "setup")
reg.noun("docs", "Guide", "book")
reg.noun("skill", "Agent skill", "sparkle")
reg.noun("command", "Command", "terminal-cmd")

# The title a command has in the editor's command palette: a verb and an object, with an ellipsis when it asks for a value first.
for _id, _title, _icon in (
    ("auth new", "Sign In…", "key"), ("auth status", "Show Sign-In Status", "account"),
    ("check", "Run Checks", "checklist"), ("command list", "List Commands", None), ("command show", "Show Command", None),
    ("completion add", "Set Up Tab Completion…", "keyboard"), ("completion list", "List Completion Values…", None),
    ("context", "Show Context", None), ("docs build", "Build Guide", "book"), ("docs generate", "Generate Guide Reference", None),
    ("doctor", "Check Machine", "pulse"), ("fresh", "Check Generated Files", None), ("help", "Learn Daily Work", "book"),
    ("kit add", "Install Kit…", "cloud-download"), ("kit list", "List Kits", None), ("kit show", "Show Kit…", None),
    ("repo add", "Add Repository", "add"), ("repo list", "List Repositories", None), ("repo set", "Set Repository Trust…", "shield"),
    ("repo status", "Show Repository Status", None), ("repo sync", "Sync Repositories", "sync"),
    ("shell add", "Set Up Prompt…", "terminal"), ("skill generate", "Generate Agent Skill", None), ("test", "Run Tests", "beaker"),
    ("update", "Update ws-host", "versions"), ("vscode ensure", "Set Up VS Code", None),
    ("workspace ensure", "Set Up Workspace", "rocket"), ("workspace set", "Make Git Sync Safe", None),
    ("workspace status", "Show Workspace Status", "home"),
):
    reg.present(_id, _title, _icon)
