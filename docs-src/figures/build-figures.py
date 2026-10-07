#!/usr/bin/env python3
"""Draw the guide's architecture figures with the house figure kit (frontiers-figures) and theme them.

    python3 docs-src/figures/build-figures.py [--kit DIR]

DIR is a `design-systems` folder holding `frontiers-figures` and `frontiers-brand`: the public root's
(`intellectual-frontiers/.github`), found through --kit, WS_HOST_DESIGN_SYSTEMS, or a clone beside the workspace. Edit
this script, never the SVG it writes. For each figure it writes the semantic source to docs-src/figures/src/fig-N.svg
(roles, no colors), the themed SVG with the sans embedded to docs/figures/fig-N.svg, and, when cairosvg is installed,
a PNG beside it for the PDF and EPUB, whose converters cannot read a themed SVG.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def find_kit(arg: str | None) -> Path:
    for c in (arg, os.environ.get("WS_HOST_DESIGN_SYSTEMS"),
              Path.home() / "workspaces/github.com/intellectual-frontiers/.github/design-systems",
              Path.home() / "intellectual-frontiers/.github/design-systems", Path("/home/user/intellectual-frontiers/.github/design-systems")):
        if c and (Path(c) / "frontiers-figures" / "layouts.py").exists():
            return Path(c)
    sys.exit("I cannot find the figure kit. Pass --kit PATH to the public root's design-systems folder.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kit")
    ap.add_argument("--only", help="draw only figures whose name contains this")
    a = ap.parse_args()
    kit = find_kit(a.kit)
    sys.path.insert(0, str(kit / "frontiers-figures"))
    import svgkit
    svgkit.use_brand(kit / "frontiers-brand")
    import figures_def
    src, out = HERE / "src", ROOT / "docs" / "figures"
    src.mkdir(exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    for name, draw in figures_def.FIGURES.items():
        if a.only and a.only not in name:
            continue
        s = src / f"{name}.svg"
        draw(str(s))
        themed = out / f"{name}.svg"
        subprocess.run([sys.executable, str(kit / "frontiers-figures" / "theme.py"), "apply", str(s), "--brand", str(kit / "frontiers-brand"),
                        "--embed-fonts", "-o", str(themed)], check=True)
        bad = subprocess.run([sys.executable, str(kit / "frontiers-figures" / "figcheck.py"), "--brand", str(kit / "frontiers-brand"), str(s)])
        if bad.returncode:
            sys.exit(f"{name} fails the figure check")
        try:
            import cairosvg
            cairosvg.svg2png(url=str(themed), write_to=str(out / f"{name}.png"), scale=2)
        except ImportError:
            print("cairosvg is not installed: no PNG for", name)
        print("drew", name)


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    main()
