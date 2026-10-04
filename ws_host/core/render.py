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
                head = _scalar(item.get("name", item.get("id", item.get("title", ""))))
                status = item.get("status")
                rest = [f"{k}: {_scalar(v)}" for k, v in item.items() if k not in ("name", "id", "title", "status") and not isinstance(v, (dict, list))]
                mark = {"ok": "ok", "warn": "warning", "fail": "FAILED", "skip": "skipped"}.get(status, status or "")
                line = f"{pad}- {head}" + (f" [{mark}]" if mark else "")
                if rest:
                    line += " - " + "; ".join(rest)
                out.append(line)
                for k, v in item.items():
                    if isinstance(v, (dict, list)) and v:
                        out.append(f"{pad}    {k}:")
                        out += _lines(v, indent + 3)
            else:
                out.append(f"{pad}- {_scalar(item)}")
    else:
        out.append(f"{pad}{_scalar(value)}")
    return out


def to_text(r: Resource, registry=None) -> str:
    """0041 FR-054: the first line is plain language; jargon only in the lines after it."""
    d = r.to_dict(registry)
    lines = [r.plain or f"{r.kind}", f"audience: {AUDIENCE}"]
    lines += _lines(r.data)
    printable = [a for a in d["actions"] if a["enabled"]]
    if printable:
        lines.append("")
        lines.append("What you can do next:")
        for a in printable:
            lines.append(f"  {a['label']}: {a['command']}" if a["command"] else f"  {a['label']}: use the button in VS Code")
    for a in d["actions"]:
        if not a["enabled"] and a["reason"]:
            lines.append(f"  ({a['label']} is not available: {a['reason']})")
    return "\n".join(lines)


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
        + (f' <code>{_h(a["command"])}</code>' if a["command"] else " <em>asks you for a value</em>")
        + (f' <small>{_h(a["reason"])}</small>' if a["reason"] else "") + "</li>"
        for i, a in enumerate(d["actions"]))
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">"
        f"<title>{_h(r.plain or r.kind)}</title>"
        "<style>body{font-family:var(--vscode-font-family,sans-serif);margin:1.5rem;line-height:1.5}"
        "code{background:rgba(127,127,127,.15);padding:0 .3em}dt{font-weight:600}dd{margin:0 0 .4rem 1rem}</style></head><body>"
        f"<h1>{_h(r.plain or r.kind)}</h1><p><small>audience: {_h(AUDIENCE)} &middot; {_h(d['schema'])}</small></p>"
        f"{_html_value(r.data)}"
        + (f"<h2>What you can do next</h2><ul>{acts}</ul>" if acts else "")
        + "</body></html>")


def render(r: Resource, mode: str, registry=None) -> str:
    return {"json": to_json, "html": to_html}.get(mode, to_text)(r, registry)
