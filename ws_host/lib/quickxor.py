"""OneDrive for Business's QuickXorHash of a file's bytes, as Microsoft describes it, so that a local file can be compared with the hash Graph reports for the copy in OneDrive (0003-kits FR-021).
Standard library only."""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path

WIDTH, SHIFT = 160, 11            # a 160-bit state; byte n is xored in at bit n * 11, going round the state
BLOCK = WIDTH                     # 160 bytes: after that many bytes the positions come round to where they began
MASK = (1 << WIDTH) - 1


def quickxor_file(path: Path, chunk: int = BLOCK * 6554) -> str:
    """The base64 QuickXorHash of the file."""
    fold = 0                       # the bytes of every 160-byte block xored together, byte i of a block at bit 8*i
    length = 0
    with open(path, "rb") as f:
        while True:
            data = f.read(chunk)
            if not data:
                break
            length += len(data)
            for start in range(0, len(data), BLOCK):
                fold ^= int.from_bytes(data[start:start + BLOCK], "little")
    state = 0
    raw = fold.to_bytes(BLOCK, "little")
    for i, b in enumerate(raw):
        if b:
            v = b << ((i * SHIFT) % WIDTH)
            state ^= (v & MASK) ^ (v >> WIDTH)
    state ^= (length & ((1 << 64) - 1)) << (WIDTH - 64)
    return base64.b64encode(state.to_bytes(WIDTH // 8, "little")).decode("ascii")


def sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()
