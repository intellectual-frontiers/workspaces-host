"""This repository is public: nothing in it names a confidential repository or what it holds (0001-ws-host FR-018)."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = ("eido" + "lon", "the va" + "ult", "va" + "ult's", r"\bei" + r"d\b")


class Confidential(unittest.TestCase):
    def test_no_tracked_file_names_a_confidential_repository(self):
        import re
        files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
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
            for pattern in FORBIDDEN:
                if re.search(pattern, text, re.IGNORECASE):
                    hits.append((f, pattern))
        self.assertEqual(hits, [])
