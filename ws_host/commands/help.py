"""`help [TOPIC]`: the one place daily-work documentation lives (0005-help-and-docs FR-001 to FR-005, 0041-command-line FR-065)."""
from __future__ import annotations

from ..core import registry as reg, types
from ..core.registry import Arg, command, section
from ..core.resource import Action, Link, Resource, WsError

types.register(types.Type("TOPIC", ("start", "repos", "kits"), lambda v, ctx: None if v in reg.discover().topics else
                          f"{v!r} is not a help topic ({', '.join(sorted(reg.discover().topics))})",
                          lambda ctx: sorted(reg.discover().topics)))


def step_actions(t) -> list[Action]:
    return [Action(s.words, s.label, dict(s.fields)) for s in t.steps]


@command("help", category="read", summary="Learn how to do the daily work, one topic at a time",
         args=(Arg("topic", "TOPIC", positional=True, help="a topic; none lists them"),))
def help_(ctx, topic):
    topics = reg.discover().topics
    if not topic:
        return Resource("help-list", "topics", {"plain": f"I can teach you {len(topics)} things. Pick one.", "count": len(topics),
                                                "topics": [{"name": t.name, "summary": t.summary} for t in sorted(topics.values(), key=lambda t: t.name)]},
                        actions=[Action(("help",), t.summary, {"topic": t.name}) for t in sorted(topics.values(), key=lambda t: t.name)])
    t = topics.get(topic)
    if t is None:
        raise WsError("unknown-topic", f"no help topic '{topic}'", f"I do not have a page called '{topic}'. The pages are: {', '.join(sorted(topics))}.",
                      [Action(("help",), "See every page")], exit_code=2)
    acts = step_actions(t)
    return Resource("help", t.name, {"plain": t.plain, "summary": t.summary,
                                     "sections": [{"heading": h, "text": x} for h, x in t.sections],
                                     "steps": [{"n": i + 1, "name": s.label, "command": a.to_dict(reg.discover())["cli"], "note": s.note}
                                               for i, (s, a) in enumerate(zip(t.steps, acts))]},
                    links=[Link("all pages", ("help",))], actions=acts)


@section("help", suites=("quick",), summary="every help topic names real commands and fields")
def help_section(ctx):
    out, r = [], reg.discover()
    for t in r.topics.values():
        if not t.plain.endswith("."):
            out.append(_f(t.module, f"topic {t.name}: its first line is not a plain sentence"))
        for s in t.steps:
            c = r.get(s.words)
            if c is None:
                out.append(_f(t.module, f"topic {t.name}: step '{s.label}' names a command that does not exist: {' '.join(s.words)}"))
                continue
            known = {a.name for a in c.args}
            for k in s.fields:
                if k not in known:
                    out.append(_f(t.module, f"topic {t.name}: step '{s.label}' gives {k}, which {c.id} does not take"))
        names = " ".join(h + " " + x for h, x in t.sections) + " " + t.plain
        for word in ("persona", "devcontainer", "Nix", "nix", "Codespaces"):
            if word in names:
                out.append(_f(t.module, f"topic {t.name} mentions {word}, which this ws-host does not have"))
    return out


def _f(where, message):
    return {"level": "error", "where": where, "message": message, "next": f"edit {where}, then run `check help`"}
