"""This repository is public: nothing in it names a confidential repository or what it holds (0001-ws-host FR-019).

The words that are not allowed are kept as SHA-256 fingerprints, so this guard does not itself contain what it guards against.
"""
import hashlib
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = frozenset((
    "6f130cfc098f8676886efcfca70b510597913fb9e1adfa6b686a9d1efa92f010",
    "a7340e44c747eac6bf34d5537c3ed2ed153d05bf0e1855e09148ecbe49e2318e",
    "e6f0a1fbb43c89196dcfcbef85908f19ab4c5f7cc4f4c452284697757683d7ef",
))


def words(text: str):
    return {w.lower() for w in re.findall(r"[A-Za-z]+", text)}


class Confidential(unittest.TestCase):
    def test_no_tracked_file_names_a_confidential_repository(self):
        files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split("\n")
        files = [f for f in files if f]
        self.assertGreater(len(files), 50)
        hits = []
        for f in files:
            p = ROOT / f
            if p.suffix in (".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".lock") or not p.is_file():
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for w in words(text) | words(f):
                if hashlib.sha256(w.encode()).hexdigest() in FORBIDDEN:
                    hits.append(f)
        self.assertEqual(hits, [])

    def test_the_guard_recognises_a_forbidden_word(self):
        probe = bytes([101, 105, 100, 111, 108, 111, 110]).decode()
        self.assertTrue(any(hashlib.sha256(w.encode()).hexdigest() in FORBIDDEN for w in words(f"the {probe}'s repo")))
