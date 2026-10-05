"""The three renderings of a resource (0041-command-line FR-018): text, JSON and HTML, all views of the one resource."""
from __future__ import annotations

import html
import json

from .. import AUDIENCE, NAME
from .resource import Resource


def to_json(r: Resource, registry=None) -> str:
    return json.dumps(r.to_dict(registry), ensure_ascii=False, sort_keys=False)


def _scalar(v) -> str:
    if isinstance(v, bool):
        return "yes" if v else "no"
    return str(v)


def _lines(value, indent: int = 0) -> list[str]:
    pad = "  " * indent
    out: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            if k == "plain":
                continue
            if isinstance(v, (dict, list)) and v:
                out.append(f"{pad}{k}:")
                out += _lines(v, indent + 1)
            else:
                out.append(f"{pad}{k}: {_scalar(v) if not isinstance(v, (dict, list)) else '-'}")
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                head = _scalar(item.get("name", item.get("id", item.get("title", item.get("heading", "")))))
                status = item.get("status")
                rest = [f"{k}: {_scalar(v)}" for k, v in item.items() if k not in ("name", "id", "title", "heading", "status", "text") and not isinstance(v, (dict, list))]
                mark = {"ok": "ok", "passed": "passed", "warn": "warning", "fail": "FAILED", "failed": "FAILED", "skip": "skipped", "skipped": "skipped"}.get(status, status or "")
                line = f"{pad}- {head}" + (f" [{mark}]" if mark else "")
                if rest:
                    line += " - " + "; ".join(rest)
                out.append(line)
                if item.get("text"):
                    out += [f"{pad}    {ln}" if ln else "" for ln in str(item["text"]).splitlines()]
                for k, v in item.items():
                    if isinstance(v, (dict, list)) and v:
                        out.append(f"{pad}    {k}:")
                        out += _lines(v, indent + 3)
            else:
                out.append(f"{pad}- {_scalar(item)}")
    else:
        out.append(f"{pad}{_scalar(value)}")
    return out


class Style:
    """Colour and emoji for a person's terminal (0006-onboarding FR-016). Off when the output is a pipe, a file or NO_COLOR is set."""

    def __init__(self, on: bool):
        self.on = on

    def _c(self, code: str, s: str) -> str:
        return f"\033[{code}m{s}\033[0m" if self.on else s

    def bold(self, s): return self._c("1", s)
    def dim(self, s): return self._c("2", s)
    def cyan(self, s): return self._c("1;36", s)
    def green(self, s): return self._c("32", s)
    def yellow(self, s): return self._c("33", s)
    def red(self, s): return self._c("31", s)

    def mark(self, status: str) -> str:
        if not self.on:
            return {"ok": "ok", "passed": "passed", "warn": "warning", "fail": "FAILED", "failed": "FAILED", "skip": "skipped", "skipped": "skipped"}.get(status, status)
        return {"ok": "✅", "passed": "✅", "warn": "⚠️ ", "fail": "❌", "failed": "❌", "skip": "⏭️ ", "skipped": "⏭️ "}.get(status, status)


PLAIN = Style(False)


def use_color(out) -> bool:
    """Colour only for a person at a terminal; NO_COLOR and TERM=dumb turn it off, WS_HOST_COLOR=always or never decides."""
    import os
    want = os.environ.get("WS_HOST_COLOR", "")
    if want in ("always", "never"):
        return want == "always"
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    try:
        return bool(out.isatty())
    except (AttributeError, ValueError):
        return False


def _wrap(text: str, indent: str = "  ") -> list[str]:
    import shutil
    import textwrap
    width = max(50, min(shutil.get_terminal_size((90, 24)).columns, 96))
    return textwrap.wrap(text, width=width, initial_indent=indent, subsequent_indent=indent) or [""]


def _help_text(r: Resource, d: dict, st: Style) -> str:
    """A help topic as a page a person can follow: its sections, then the commands to type, in order (0005-help-and-docs FR-001)."""
    lines = [st.bold(r.plain), ""]
    for sec in r.data.get("sections", []):
        lines.append(st.bold(sec["heading"]))
        for ln in str(sec["text"]).splitlines():
            if ln.startswith("    "):
                lines.append("  " + st.cyan(ln.strip()))
            elif ln.strip():
                lines += _wrap(ln.strip())
            else:
                lines.append("")
        lines.append("")
    steps = r.data.get("steps", [])
    if steps:
        lines.append(st.bold("👉 The commands, in order" if st.on else "The commands, in order"))
        for s in steps:
            lines.append(f"  {s['n']}. {s['name']}")
            lines.append("     " + (st.cyan(s["command"]) if s["command"] else "use the button in VS Code") + (f"   {st.dim('(' + s['note'] + ')')}" if s.get("note") else ""))
        lines.append("")
    lines.append(st.dim(f"audience: {AUDIENCE}"))
    return "\n".join(lines)


def to_text(r: Resource, registry=None, color: bool = False) -> str:
    """0041 FR-054: the first line is plain language; jargon only in the lines after it."""
    st = Style(color)
    d = r.to_dict(registry)
    if r.kind == "help":
        return _help_text(r, d, st)
    if r.kind == "progress":      # a step reporting as it goes: one friendly line, not a page (0041 FR-019)
        return (f"⏳ {r.plain}" if st.on else r.plain)
    if st.on:
        from . import pretty
        from .. import VERSION
        return pretty.render(r, d, st, VERSION, AUDIENCE)
    lines = [st.bold(r.plain or f"{r.kind}"), st.dim(f"audience: {AUDIENCE}")]
    lines += [_mark_line(x, st) for x in _lines(r.data)]
    printable = [a for a in d["actions"] if a["enabled"]]
    if printable:
        lines.append("")
        lines.append(st.bold("👉 What you can do next:" if st.on else "What you can do next:"))
        for a in printable:
            lines.append(f"  {a['label']}: {st.cyan(a['cli'])}" if a["cli"] else f"  {a['label']}: use the button in VS Code")
    for a in d["actions"]:
        if not a["enabled"] and a["reason"]:
            lines.append(f"  ({a['label']} is not available: {a['reason']})")
    return "\n".join(lines)


_MARKS = {"ok": "ok", "passed": "passed", "warning": "warn", "FAILED": "fail", "skipped": "skip"}


def _mark_line(line: str, st: Style) -> str:
    """Swap the words _lines wrote for a status ([ok], [FAILED]...) for a mark a person reads at a glance."""
    if not st.on:
        return line
    for word, status in _MARKS.items():
        tag = f" [{word}]"
        if tag in line:
            return line.replace(tag, " " + st.mark(status), 1)
    return line


def _h(v) -> str:
    return html.escape(str(v), quote=True)


def _html_value(v) -> str:
    if isinstance(v, dict):
        return "<dl>" + "".join(f"<dt>{_h(k)}</dt><dd>{_html_value(x)}</dd>" for k, x in v.items() if k != "plain") + "</dl>"
    if isinstance(v, list):
        return "<ul>" + "".join(f"<li>{_html_value(x)}</li>" for x in v) + "</ul>"
    return _h(_scalar(v))


def to_html(r: Resource, registry=None) -> str:
    """A page of local markup only: no script, no remote reference. The extension's webview hosts it under a strict CSP."""
    d = r.to_dict(registry)
    acts = "".join(
        f'<li><button type="button" data-action="{i}"{"" if a["enabled"] else " disabled"}>{_h(a["label"])}</button>'
        + (f' <code>{_h(a["cli"])}</code> <button type="button" class="link" data-show="{i}">Show command</button>' if a["cli"] else " <em>asks you for a value</em>")
        + (f' <small>{_h(a["reason"])}</small>' if a["reason"] else "") + "</li>"
        for i, a in enumerate(d["actions"]))
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">"
        f"<title>{_h(r.plain or r.kind)}</title>"
        "<style>body{font-family:var(--vscode-font-family,sans-serif);margin:1.5rem;line-height:1.5}"
        "code{background:rgba(127,127,127,.15);padding:0 .3em}dt{font-weight:600}dd{margin:0 0 .4rem 1rem}"
        "button{margin-right:.4rem}button.link{background:none;border:none;color:var(--vscode-textLink-foreground,#06c);cursor:pointer;text-decoration:underline}</style></head>"
        # The page carries the whole resource, so a reader can act on it without running the command again (0004 FR-006).
        f"<body data-resource=\"{_h(json.dumps(d, ensure_ascii=False))}\">"
        f"<h1>{_h(r.plain or r.kind)}</h1><p><small>audience: {_h(AUDIENCE)} &middot; {_h(d['schema'])}</small></p>"
        f"{_html_value(r.data)}"
        + (f"<h2>What you can do next</h2><ul>{acts}</ul>" if acts else "")
        + "</body></html>")


def render(r: Resource, mode: str, registry=None, color: bool = False) -> str:
    if mode == "text":
        return to_text(r, registry, color)
    return {"json": to_json, "html": to_html}.get(mode, to_text)(r, registry)
