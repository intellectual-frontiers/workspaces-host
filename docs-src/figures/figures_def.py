"""The guide's figures, as data: name -> a function that draws it to a path."""
import layouts, svgkit


def _boot(path):
    layouts.chain_vertical(path, "From curl to a working machine", "install.sh, the launcher, then ws-host itself",
                           ["install.sh checks git, curl, tar and xz, clones the repository, links ws-host",
                            "ws-host fetches mise, checked against a pinned SHA-256",
                            "mise installs Python and uv from the pins in bootstrap.env",
                            "python -m ws_host runs workspace ensure"])


FIGURES = {"fig-test": _boot}
