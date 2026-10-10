"""The `embedded-sql` kit: the house defaults for lightweight and embedded SQL (0003-kits FR-020). SQLite and DuckDB themselves are in `base`; this adds what manages, queries, formats, migrates,
backs up and explores them, and the Turso command line. Every tool floats with its newest release (FR-017). MotherDuck needs no program of its own: it is DuckDB with `ATTACH 'md:'`."""
from __future__ import annotations

from ..core.kit import Check, Floating, Kit
from ..install import floating

_GH = (("turso", "tursodatabase/turso-cli", {"turso": "turso"}),
       ("usql", "xo/usql", {"usql": "usql"}),
       ("litestream", "benbjohnson/litestream", {"litestream": "litestream"}),
       ("sqruff", "quarylabs/sqruff", {"sqruff": "sqruff"}),
       ("dbmate", "amacneil/dbmate", {"dbmate": "dbmate-linux-amd64|dbmate-linux-arm64|dbmate"}))
_PY = (("sqlite-utils", "sqlite-utils", {"sqlite-utils": "bin/sqlite-utils"}),
       ("datasette", "datasette", {"datasette": "bin/datasette"}),
       ("harlequin", "harlequin", {"harlequin": "bin/harlequin"}),
       ("visidata", "visidata", {"vd": "bin/vd", "visidata": "bin/visidata"}))

_VERSION_ARGS = {"litestream": ("version",)}

TOOLS = ([Floating(n, floating.github_auto(repo), binaries=dict(b), auto=True) for n, repo, b in _GH]
         + [Floating(n, floating.pypi(pkg), binaries=dict(b), manager="pip", package=pkg) for n, pkg, b in _PY])


class EmbeddedSql(Kit):
    name = "embedded-sql"
    summary = "tools for SQLite, DuckDB, Turso and MotherDuck: turso, usql, litestream, sqruff, dbmate, sqlite-utils, datasette, harlequin and visidata"
    plain = "work with small, embedded SQL databases: query, explore, migrate, back up and format them, and use Turso and MotherDuck."

    def downloads(self, distro):
        return list(TOOLS)

    def checks(self, distro):
        return [Check(p, p, version_args=_VERSION_ARGS.get(p, ("--version",))) for t in TOOLS for p in t.binaries]
