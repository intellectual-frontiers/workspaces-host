"""The text a person reads at a terminal: sections, aligned rows, marks you read at a glance, and the next step in cyan (0006-onboarding FR-024).

Used only where colour is on. A pipe, a file or NO_COLOR gets the plain form from render.py, which scripts and tests depend on, and JSON and
HTML are never touched. The first line is still the plain sentence. Standard library only."""
from __future__ import annotations

import shutil
import textwrap

KIND_EMOJI = {"doctor": "🩺", "kit-list": "🧰", "kit": "🧰", "kit-add": "🧰", "workspace-ensure": "🚀", "workspace-status": "🗺️", "workspace": "🗺️",
              "repo-list": "📁", "repo-status": "📁", "repo-add": "📁", "repo-sync": "📁", "auth-status": "🔐", "auth-new": "🔐", "check": "🔍",
              "vscode-setup": "💻", "vscode-add": "💻", "shell-add": "🎨", "completion-add": "⌨️", "command-list": "📋", "command": "📋",
              "update-check": "🔄", "update": "🔄", "context": "🧾", "test": "🧪", "docs-build": "📚", "docs-generate": "📚", "fresh": "🧹"}
STATUS_EMOJI = {"ok": "✅", "passed": "✅", "current": "✅", "installed": "✅", "already": "✅", "done": "✅", "cloned": "✅", "updated": "✅",
                "warn": "⚠️", "warning": "⚠️", "skipped": "⏭️", "skip": "⏭️", "left-alone": "⏭️", "missing": "⬜", "would-install": "🔮", "would-add": "🔮",
                "would-write": "🔮", "info": "ℹ️", "fail": "❌", "failed": "❌", "stale": "❌"}
SECTION_EMOJI = {"checks": "🩺", "kits": "🧰", "steps": "🪜", "repositories": "📁", "forges": "🔐", "sections": "🔍", "settings": "⚙️", "distro": "🖥️",
                 "summary": "📊", "whats_new": "🆕", "would": "🔮", "lines": "📝", "commands": "📋", "generators": "🧬", "values": "📋", "files": "📄", "findings": "🔎", "topics": "📖"}
SECTION_TITLE = {"checks": "Health checks", "kits": "Kits", "steps": "What happened", "repositories": "Repositories", "forges": "Accounts",
                 "sections": "Checks", "distro": "This machine", "generators": "Generated files", "values": "Values", "findings": "Findings", "would": "What I would do", "whats_new": "What is new", "lines": "The lines I would add"}
NAME_KEYS = ("name", "id", "title", "heading", "label")
TEXT_KEYS = ("detail", "plain", "message", "reason", "why", "summary", "help", "path")
CATEGORY_EMOJI = {"read": "📖", "check": "🩺", "setup": "🔧", "build": "🏗️", "generate": "🧬", "record": "📝", "decision": "⚖️"}
HIDDEN = {"plain", "status", "audience", "schema", "name", "id", "title", "heading", "label", "text", "cli", "todo", "action"} | set(TEXT_KEYS)
FIX_KEYS = ("next", "fix")


def width() -> int:
    return max(60, min(shutil.get_terminal_size((90, 24)).columns, 100))


def _title(key: str) -> str:
    return SECTION_TITLE.get(key) or key.replace("_", " ").capitalize()


def _is_status_row(v) -> bool:
    return isinstance(v, list) and bool(v) and all(isinstance(x, dict) for x in v)


def _mark(item: dict) -> str:
    s = item.get("status")
    if s is None and item.get("category") in CATEGORY_EMOJI:
        return CATEGORY_EMOJI[item["category"]]
    if s is None:
        for key, ok in (("installed", True), ("signed_in", True), ("cloned", True)):
            if key in item:
                return "✅" if item[key] else "⬜"
        return "🔹"
    return STATUS_EMOJI.get(str(s), "🔹")


def _short(v) -> str:
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, list) and v and all(isinstance(x, dict) and "status" in x for x in v):
        counts: dict[str, int] = {}
        for x in v:
            counts[str(x["status"])] = counts.get(str(x["status"]), 0) + 1
        return ", ".join(f"{n} {s}" for s, n in counts.items())
    if isinstance(v, list):
        shown = ", ".join(str(x) if not isinstance(x, dict) else str(x.get("name", x.get("id", "…"))) for x in v[:6])
        return shown + (f" (+{len(v) - 6} more)" if len(v) > 6 else "")
    if isinstance(v, dict):
        return f"{len(v)} found"
    return str(v)


def _wrap(text: str, first: str, rest: str, w: int) -> list[str]:
    return textwrap.wrap(text, width=w, initial_indent=first, subsequent_indent=rest, break_long_words=False, break_on_hyphens=False) or [first.rstrip()]


class Page:
    def __init__(self, st, w: int):
        self.st, self.w, self.lines = st, w, []

    def rule(self):
        self.lines.append(self.st.dim("─" * self.w))

    def blank(self):
        if self.lines and self.lines[-1] != "":
            self.lines.append("")

    def heading(self, emoji: str, title: str, note: str = ""):
        self.blank()
        self.lines.append(f"{emoji}  {self.st.bold(title)}" + (f"  {self.st.dim(note)}" if note else ""))

    def facts(self, rows: list[tuple[str, object]], indent: str = "   "):
        if not rows:
            return
        kw = min(max(len(k) for k, _ in rows), 24)
        for k, v in rows:
            text = _short(v) if not isinstance(v, str) else v
            colored = self.st.green(text) if v is True else self.st.dim(text) if v is False else text
            wrapped = _wrap(text, "", " " * (len(indent) + kw + 2), self.w - len(indent) - kw - 2)
            first = wrapped[0] if wrapped else ""
            self.lines.append(f"{indent}{self.st.dim(k.ljust(kw))}  " + (colored if len(wrapped) <= 1 else first))
            self.lines += [" " * (len(indent) + kw + 2) + ln.strip() for ln in wrapped[1:]]

    def rows(self, items: list[dict], indent: str = "   "):
        names = [str(next((i[k] for k in NAME_KEYS if k in i and i[k] not in (None, "")), "")) for i in items]
        nw = min(max([len(n) for n in names] + [1]), 30)
        pad = " " * (len(indent) + 3 + nw + 2)
        for item, name in zip(items, names):
            text = next((str(item[k]) for k in TEXT_KEYS if item.get(k) not in (None, "", [], {})), "")
            if any(item.get(k) for k in FIX_KEYS):
                text = text.split("; fix: ")[0]       # the fix is shown on its own line
            long_name = len(name) > nw
            head = f"{indent}{_mark(item)} {self.st.bold(name if long_name else name.ljust(nw))}"
            wrapped = _wrap(text, "", pad, self.w - len(pad)) if text else []
            if long_name or not wrapped:
                self.lines.append(head.rstrip())
                self.lines += [" " * (len(indent) + 3) + ln.strip() for ln in (_wrap(text, "", "", self.w - len(indent) - 3) if text else [])]
                pad = " " * (len(indent) + 3)
            else:
                self.lines.append(head + "  " + wrapped[0].strip())
                self.lines += wrapped[1:]
            extras = [(k, v) for k, v in item.items() if k not in HIDDEN and k not in FIX_KEYS and v not in (None, "", [], {}, False) and k not in ("installed", "cloned", "signed_in")]
            if extras:
                line = " · ".join(f"{k.replace('_', ' ')} {_short(v)}" for k, v in extras)
                self.lines += [self.st.dim(ln) for ln in _wrap(line, pad, pad, self.w)]
            if item.get("cli"):
                self.lines.append(pad + self.st.cyan("→ " + str(item["cli"])))
            if item.get("todo"):
                self.lines += [pad + self.st.dim("↳ " + ln) for ln in _wrap(str(item["todo"]), "", "  ", self.w - len(pad) - 2)]
            for k in FIX_KEYS:
                if item.get(k):
                    self.lines += [self.st.cyan("→ " + ln.strip()) if i == 0 else ln for i, ln in enumerate(_wrap(str(item[k]), pad, pad + "  ", self.w))] if False else \
                                  [pad + self.st.cyan("→ " + (str(item[k]) if str(item[k]).startswith(("ws-host", "run ", "edit ")) else "ws-host " + str(item[k])))]

    def bullets(self, items: list, indent: str = "   "):
        for x in items:
            self.lines += _wrap(str(x), f"{indent}• ", indent + "  ", self.w)


def _summary(items: list[dict]) -> str:
    counts: dict[str, int] = {}
    for i in items:
        m = _mark(i)
        counts[m] = counts.get(m, 0) + 1
    names = {"✅": "ok", "⚠️": "to look at", "❌": "failed", "⏭️": "skipped", "⬜": "pending", "🔮": "would change"}
    parts = [f"{n} {names.get(m, '')}".strip() for m, n in counts.items() if m in names]
    return " · ".join(parts) if len(counts) > 1 or "✅" not in counts else f"{counts['✅']} ok"


def render(r, d: dict, st, version: str, audience: str) -> str:
    w = width()
    page = Page(st, w)
    emoji = KIND_EMOJI.get(r.kind) or STATUS_EMOJI.get(r.status, "ℹ️")
    if r.kind == "error":
        emoji = "❌" if r.status == "failed" else "⚠️"
    page.lines.append(f"{emoji}  {st.bold(r.plain or r.kind)}")
    page.rule()
    data = {k: v for k, v in r.data.items() if k != "plain"}
    scalars = [(k.replace("_", " "), v) for k, v in data.items() if not isinstance(v, (dict, list)) and v not in (None, "") and k != "count"]
    if scalars:
        if len(scalars) > 1:
            page.heading("📌", "Details")
        else:
            page.blank()
        page.facts(scalars)
    for k, v in data.items():
        if v in (None, "", [], {}) or not isinstance(v, (dict, list)):
            continue
        emoji_k = SECTION_EMOJI.get(k, "▫️")
        if isinstance(v, dict) and k == "distro" and v.get("pretty"):
            page.heading(emoji_k, _title(k))
            page.lines.append("   " + " · ".join([str(v["pretty"]), str(v.get("arch", "")), "Windows (WSL)" if v.get("wsl") not in (False, "no", None, "") else "not WSL"]))
        elif isinstance(v, dict):
            page.heading(emoji_k, _title(k))
            flat = [(a.replace("_", " "), b) for a, b in v.items() if b not in (None, "")]
            if flat and all(isinstance(b, int) and not isinstance(b, bool) for _, b in flat):
                page.lines.append("   " + st.dim(" · ").join(f"{st.bold(str(b))} {a}" for a, b in flat))
            else:
                page.facts(flat)
        elif _is_status_row(v):
            page.heading(emoji_k, _title(k), _summary(v) if any("status" in i or "installed" in i for i in v) else f"{len(v)}")
            page.rows(v)
        elif k == "lines":
            page.heading(emoji_k, _title(k))
            page.lines += [st.dim("   │ ") + str(x) for x in v]
        else:
            page.heading(emoji_k, _title(k))
            page.bullets(v)
    acts = [a for a in d["actions"] if a["enabled"]]
    if acts:
        page.blank()
        page.rule()
        page.lines.append(f"👉  {st.bold('What you can do next')}")
        for a in acts:
            page.lines.append(f"   {st.bold(a['label'])}")
            page.lines.append("   " + (st.cyan(a["cli"]) if a["cli"] else st.dim("use the button in VS Code")))
    for a in d["actions"]:
        if not a["enabled"] and a["reason"]:
            page.lines.append(st.dim(f"   ({a['label']} is not available: {a['reason']})"))
    page.blank()
    page.lines.append(st.dim(f"audience: {audience} · ws-host {version}"))
    return "\n".join(page.lines)
