#!/bin/sh
# Install ws-host on a Debian-family Linux machine (0001-ws-host FR-005, FR-006).
#
#   curl -fsSL https://raw.githubusercontent.com/intellectual-frontiers/workspaces-host/main/install.sh | sh
#
# Checks python3 and git, installs uv if it is missing, clones workspaces-host beside your other repositories (or advances
# an existing clone by fast-forward only), links ~/.local/bin/ws-host, and runs `ws-host doctor`. Safe to run again.
# WS_HOST_URL (where to clone from) and WS_HOST_HOME (the workspaces folder) exist so it can be tested.
set -eu

url=${WS_HOST_URL:-https://github.com/intellectual-frontiers/workspaces-host}
root=${WS_HOST_HOME:-$HOME/workspaces}
target=$root/github.com/intellectual-frontiers/workspaces-host

say() { printf '%s\n' "$*"; }
need() {
  say "ws-host cannot be installed yet: $1" >&2
  say "Fix: $2" >&2
  exit 3
}

command -v python3 >/dev/null 2>&1 || need "python3 is not installed." "sudo apt install python3"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' ||
  need "python3 is older than 3.11." "use Debian 12 or later, or Ubuntu 24.04 or later"
command -v git >/dev/null 2>&1 || need "git is not installed." "sudo apt install git"

PATH=$HOME/.local/bin:$PATH
export PATH
if ! command -v uv >/dev/null 2>&1; then
  say "Installing uv, the tool ws-host runs on..."
  if command -v curl >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- https://astral.sh/uv/install.sh | sh
  else
    need "uv is not installed, and neither curl nor wget is here to fetch it." "sudo apt install curl, then run this again"
  fi
fi

if [ -d "$target/.git" ]; then
  say "Updating $target (only if nothing of yours is in the way)..."
  if git -C "$target" fetch --quiet origin; then
    git -C "$target" merge --ff-only --quiet '@{upstream}' 2>/dev/null ||
      say "Your copy was left exactly as it was; your work is safe."
  else
    say "Could not reach $url, so your copy was left as it was; your work is safe."
  fi
else
  mkdir -p "$(dirname "$target")"
  GIT_TERMINAL_PROMPT=0 git clone --quiet "$url" "$target" || need "could not copy $url." "check your network, or sign in first with: gh auth login"
fi

mkdir -p "$HOME/.local/bin"
ln -sf "$target/ws-host" "$HOME/.local/bin/ws-host"
say "Linked $HOME/.local/bin/ws-host"

"$HOME/.local/bin/ws-host" doctor
say ""
say "Next: run  ws-host workspace advance"
