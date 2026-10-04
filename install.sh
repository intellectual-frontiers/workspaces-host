#!/bin/sh
# Install ws-host on a Debian-family Linux machine, including Debian or Ubuntu under WSL (0001-ws-host FR-005, FR-006,
# 0006-onboarding FR-001).
#
#   curl -fsSL https://raw.githubusercontent.com/intellectual-frontiers/workspaces-host/main/install.sh | sh
#
# It installs what is missing (python3, git, certificates; it says so and asks for your password first), installs uv, copies
# workspaces-host beside your other repositories (or advances an existing copy by fast-forward only), links ~/.local/bin/ws-host,
# checks your machine, and runs `ws-host workspace advance`. Safe to run again.
#
# Environment, so it can be tested: WS_HOST_URL (where to clone from), WS_HOST_HOME (the workspaces folder), WS_HOST_NO_APT=1
# (never install packages), WS_HOST_NO_ADVANCE=1 (stop after the check).
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

# Packages this script needs and does not find. On Debian and Ubuntu it installs them, after saying so.
missing=""
command -v python3 >/dev/null 2>&1 || missing="$missing python3"
command -v git >/dev/null 2>&1 || missing="$missing git"
[ -e /etc/ssl/certs/ca-certificates.crt ] || missing="$missing ca-certificates"
if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1 && ! command -v uv >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/uv" ]; then
  missing="$missing curl"
fi
if [ -n "$missing" ]; then
  if [ "${WS_HOST_NO_APT:-}" = 1 ] || ! command -v apt-get >/dev/null 2>&1; then
    need "this machine lacks:$missing." "sudo apt install$missing"
  fi
  sudo_cmd=""
  if [ "$(id -u)" != 0 ]; then
    command -v sudo >/dev/null 2>&1 || need "this machine lacks:$missing, and sudo is not here to install them." "ask an administrator to run: apt install$missing"
    sudo_cmd=sudo
    say "I need to install:$missing. That needs administrator rights, so your password may be asked."
  else
    say "Installing:$missing."
  fi
  $sudo_cmd env DEBIAN_FRONTEND=noninteractive apt-get update -qq ||
    need "the package list could not be refreshed." "check your network, then run this again"
  # shellcheck disable=SC2086
  $sudo_cmd env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq $missing ||
    need "the packages could not be installed." "run: sudo apt install$missing"
fi

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
  GIT_TERMINAL_PROMPT=0 git clone --quiet "$url" "$target" || need "could not copy $url." "check your network, then run this again"
fi

mkdir -p "$HOME/.local/bin"
ln -sf "$target/ws-host" "$HOME/.local/bin/ws-host"
say "Linked $HOME/.local/bin/ws-host"

# A new terminal finds ~/.local/bin by itself on Debian and Ubuntu once it exists; this one needs to be told.
"$HOME/.local/bin/ws-host" doctor || true
say ""
if [ "${WS_HOST_NO_ADVANCE:-}" = 1 ]; then
  "$HOME/.local/bin/ws-host" help start || say "Next: run  ws-host help start"
  exit 0
fi
say "Now setting up your workspace..."
"$HOME/.local/bin/ws-host" workspace advance || true
say ""
# The first steps are the program's own help page, so what this prints can never differ from what it teaches.
"$HOME/.local/bin/ws-host" help start || say "Run  ws-host help start  for what to do next."
say ""
say "If a new terminal does not know ws-host, close it and open another."
