"""The `press` kit: TeX, PDF and EPUB tools, Java, asciidoctor (0003-kits FR-009)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from ..core.kit import Check, Kit

DOC = r"""\documentclass{article}
\usepackage{fontspec}
\usepackage{unicode-math}
\usepackage{lualatex-math}
\setmainfont{Latin Modern Roman}
\setmathfont{Latin Modern Math}
\begin{document}
H\'ello, w\"orld: $\alpha + \beta = \sum_{i=1}^{n} i$
\end{document}
"""


def lualatex(work: Path) -> str:
    """lualatex compiles a document that uses fontspec, unicode-math and lualatex-math."""
    (work / "t.tex").write_text(DOC)
    p = subprocess.run(["lualatex", "-interaction=nonstopmode", "-halt-on-error", "t.tex"], cwd=work, capture_output=True, text=True, timeout=600)
    assert p.returncode == 0 and (work / "t.pdf").is_file(), "lualatex could not compile the test document: " + (p.stdout or p.stderr)[-300:]
    return "lualatex compiled a fontspec, unicode-math and lualatex-math document"


class Press(Kit):
    name = "press"
    summary = "TeX Live (LuaLaTeX, XeTeX), latexmk, poppler, qpdf, rsvg, Java, epubcheck, asciidoctor, potrace"
    plain = "everything needed to typeset and check books, PDFs and EPUBs."

    def apt(self, distro):
        return ["texlive-luatex", "texlive-xetex", "texlive-latex-extra", "texlive-fonts-recommended", "texlive-science", "texlive-latex-recommended",
                "texlive-plain-generic", "lmodern", "fonts-lmodern", "latexmk", "poppler-utils", "qpdf", "librsvg2-bin", "default-jre-headless",
                "epubcheck", "asciidoctor", "ruby-asciidoctor-pdf", "ruby-asciidoctor-epub3|asciidoctor-epub3", "potrace", "ghostscript"]

    def checks(self, distro):
        return [Check("lualatex", "lualatex"), Check("xelatex", "xelatex"), Check("latexmk", "latexmk", ("-v",)), Check("pdftotext", "pdftotext", ("-v",)),
                Check("qpdf", "qpdf"), Check("rsvg-convert", "rsvg-convert"), Check("java", "java", ("-version",)), Check("asciidoctor", "asciidoctor"),
                Check("potrace", "potrace"),
                Check("lualatex compiles fontspec, unicode-math and lualatex-math", run=lualatex, needs=("lualatex",))]
