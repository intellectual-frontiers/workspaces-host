"""Run agora's own functional check of each toolchain entry against the copy that mise installed, not against agora's cache.

usage (from the public root's tools/ directory):  MISE_INSTALLS=<mise data>/installs PYTHONPATH=. python3 agora_equiv.py
`agora toolchain ensure` skips its check when an AGORA_<ENTRY> override stands in, so the checks are called directly here.
"""
import os
from pathlib import Path

from agora.core import toolchain as T

installs = Path(os.environ["MISE_INSTALLS"])
entries = T.discover()
tc = T.Toolchain(entries, cache=Path(os.environ.get("TMPDIR", "/tmp")) / "agora-empty-cache", offline=True)
where = {"jre": installs / "http-jre/21.0.12.1+1", "chromium": installs / "http-chromium/1.50.0",
         "tinytex": installs / "http-tinytex/2026.03", "asciidoctor": installs / "http-asciidoctorj/3.0.1"}
for name in where:
    try:
        print(f"PASS {name}: {entries[name].check(T.Resolved(tc, tc.platform, dirs=dict(where)))[:100]}")
    except Exception as e:  # a failed check says why
        print(f"FAIL {name}: {type(e).__name__}: {str(e)[:300]}")
