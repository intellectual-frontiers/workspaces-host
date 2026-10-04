"""Installing the kits repositories declare (0003-kits). The installers arrive with the kits."""
from __future__ import annotations


def ensure(ctx, declared: dict[str, list[str]]) -> dict:
    if not declared:
        return {"status": "ok", "plain": "No repository asked for a kit."}
    return {"status": "ok", "plain": "Kits are asked for: " + ", ".join(sorted(declared)) + "."}
