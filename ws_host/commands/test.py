"""`test`: the repository's tests with the standard library's runner (0001-ws-host FR-014, 0041-command-line FR-034)."""
from __future__ import annotations

import io
import unittest

from ..core import paths, registry as reg
from ..core.resource import FAILED, OK, Resource


@reg.command("test", category="check", summary="Run this repository's tests")
def test(ctx):
    root = paths.repo_root()
    suite = unittest.defaultTestLoader.discover(str(root / "tests"), top_level_dir=str(root))
    buf = io.StringIO()
    res = unittest.TextTestRunner(stream=buf, verbosity=0).run(suite)
    failing = [str(t) for t, _ in res.failures + res.errors]
    ok = res.testsRun > 0 and res.wasSuccessful()
    plain = (f"All {res.testsRun} tests passed." if ok else
             "No tests ran, so nothing is proven." if res.testsRun == 0 else f"{len(failing)} of {res.testsRun} tests failed.")
    data = {"plain": plain, "ran": res.testsRun, "failures": len(res.failures), "errors": len(res.errors),
            "skipped": len(res.skipped), "passed": res.testsRun - len(res.failures) - len(res.errors) - len(res.skipped),
            "failing": failing}
    if failing and ctx.debug:
        data["output"] = buf.getvalue()
    return Resource("test", "ws-host", data, status=OK if ok else FAILED)
