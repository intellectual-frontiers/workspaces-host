"""What changes or runs something, as NDJSON in the state directory (0041-command-line FR-042). Never a secret."""
from __future__ import annotations

import json
import time

from . import paths


def log(surface: str, command: str, args: dict, exit_code: int) -> None:
    try:
        d = paths.logs_dir()
        d.mkdir(parents=True, exist_ok=True)
        line = {"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "surface": surface, "command": command,
                "args": args, "exit": exit_code}
        with open(d / "ws-host.ndjson", "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        pass  # a log that cannot be written never fails a command
