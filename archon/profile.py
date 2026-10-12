"""The profile: whether a person is at the invocation (0011-archon FR-005 to FR-007). Standard library only.

Every invocation is `unattended` unless something says a person is there. Nothing about the computer, such as whether `ws-host` is installed, enters the decision.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Mapping

ATTENDED, UNATTENDED = "attended", "unattended"
TRUE = ("1", "true")
# Variables that say an AI agent or a CI job runs the command. A pipe is not among them: the editor reads JSON through one.
UNATTENDED_BY = ("CI", "CLAUDE_CODE_REMOTE")
VARIABLE = "ARCHON_ATTENDANCE"


@dataclass(frozen=True)
class Profile:
    attendance: str
    why: str          # the rule that decided it, for `archon doctor`

    @property
    def attended(self) -> bool:
        return self.attendance == ATTENDED

    @property
    def unattended(self) -> bool:
        return not self.attended

    def to_dict(self) -> dict[str, str]:
        return {"attendance": self.attendance, "attendance decided by": self.why}


def _terminal(stream) -> bool:
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False


def detect(env: Mapping[str, str] | None = None, stdin=None, stderr=None) -> Profile:
    """The explicit variable, else unattended where an agent or a CI job says so, else attended only at a terminal (stdin and stderr both), else unattended."""
    env = os.environ if env is None else env
    said = env.get(VARIABLE, "")
    if said in (ATTENDED, UNATTENDED):
        return Profile(said, VARIABLE)
    for var in UNATTENDED_BY:
        if env.get(var, "").lower() in TRUE:
            return Profile(UNATTENDED, var)
    if _terminal(sys.stdin if stdin is None else stdin) and _terminal(sys.stderr if stderr is None else stderr):
        return Profile(ATTENDED, "a terminal is attached")
    return Profile(UNATTENDED, "no terminal is attached, and nothing says a person is here")


def current() -> Profile:
    return detect()


def exported(env: Mapping[str, str] | None = None, profile: Profile | None = None) -> dict[str, str]:
    """`env` with the decision written into it, for everything archon starts to agree (FR-007)."""
    out = dict(os.environ if env is None else env)
    out[VARIABLE] = (profile or detect(out)).attendance
    return out
