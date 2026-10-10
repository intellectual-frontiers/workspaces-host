"""The modern command-line tools every machine gets (0003-kits FR-018): each the newest release of its project, found when it is installed and checked against the checksum GitHub states
for the file (0003-kits FR-017). Not a kit itself: the `base` kit installs them and the `modern-cli` kit makes the shell use them."""
from __future__ import annotations

from ..core.kit import Check, Floating
from ..install import floating

# name in ws-host's tools folder, GitHub repository, {program linked into ~/.local/bin: the file names it may have in the release}
_TOOLS = (
    ("eza", "eza-community/eza", {"eza": "eza"}),
    ("zoxide", "ajeetdsouza/zoxide", {"zoxide": "zoxide"}),
    ("fzf", "junegunn/fzf", {"fzf": "fzf"}),
    ("yazi", "sxyazi/yazi", {"yazi": "yazi", "ya": "ya"}),
    ("bat", "sharkdp/bat", {"bat": "bat"}),
    ("delta", "dandavison/delta", {"delta": "delta"}),
    ("sd", "chmln/sd", {"sd": "sd"}),
    ("yq", "mikefarah/yq", {"yq": "yq_linux_amd64|yq_linux_arm64|yq"}),
    ("glow", "charmbracelet/glow", {"glow": "glow"}),
    ("btop", "aristocratos/btop", {"btop": "btop"}),
    ("dust", "bootandy/dust", {"dust": "dust"}),
    ("duf", "muesli/duf", {"duf": "duf"}),
    ("procs", "dalance/procs", {"procs": "procs"}),
    ("just", "casey/just", {"just": "just"}),
    ("watchexec", "watchexec/watchexec", {"watchexec": "watchexec"}),
    ("hyperfine", "sharkdp/hyperfine", {"hyperfine": "hyperfine"}),
    ("tokei", "XAMPPRocky/tokei", {"tokei": "tokei"}),
    ("lazygit", "jesseduffield/lazygit", {"lazygit": "lazygit"}),
    ("tealdeer", "tealdeer-rs/tealdeer", {"tldr": "tldr"}),
    ("xh", "ducaale/xh", {"xh": "xh"}),
    ("shfmt", "mvdan/sh", {"shfmt": "shfmt"}),
    ("actionlint", "rhysd/actionlint", {"actionlint": "actionlint"}),
)

TOOLS = [Floating(name, floating.github_auto(repo), binaries=dict(binaries), auto=True) for name, repo, binaries in _TOOLS]

# programs whose version flag is not --version
_VERSION_ARGS = {"actionlint": ("-version",), "tldr": ("--version",)}


def checks() -> list[Check]:
    return [Check(program, program, version_args=_VERSION_ARGS.get(program, ("--version",))) for _name, _repo, binaries in _TOOLS for program in binaries]
