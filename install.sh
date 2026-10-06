#!/bin/sh
# Install ws-host on a Debian-family Linux machine, including Debian or Ubuntu under WSL (0001-ws-host FR-005, FR-006,
# 0006-onboarding FR-001).
#
#   curl -fsSL https://raw.githubusercontent.com/intellectual-frontiers/workspaces-host/main/install.sh | sh
#
# It installs what is missing (git, xz, certificates, curl and wget; it says so and asks for your password first), copies
# workspaces-host beside your other repositories (or updates an existing copy by fast-forward only), links ~/.local/bin/ws-host,
# has the launcher fetch ws-host's own Python and uv through mise, checks your machine, and runs `ws-host workspace ensure`. Safe to run again.
#
# Long steps show one line with a spinner (after half a second, at a terminal only) instead of a wall of output; what a step printed is
# kept in a log and shown only if the step fails. A slow network therefore looks busy, not stuck.
#
# Environment, so it can be tested: WS_HOST_URL (where to clone from), WS_HOST_HOME (the workspaces folder), WS_HOST_NO_APT=1
# (never install packages), WS_HOST_NO_ADVANCE=1 (stop after the check).
set -eu

url=${WS_HOST_URL:-https://github.com/intellectual-frontiers/workspaces-host}
root=${WS_HOST_HOME:-$HOME/workspaces}
target=$root/github.com/intellectual-frontiers/workspaces-host

orig_path=$PATH

# Colour and emoji only at a terminal (and never with NO_COLOR), so a log or a pipe stays plain.
if [ -t 2 ] && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-dumb}" != dumb ]; then
  b=$(printf '\033[1m'); c=$(printf '\033[1;36m'); g=$(printf '\033[32m'); r=$(printf '\033[31m'); d=$(printf '\033[2m'); z=$(printf '\033[0m')
else
  b=""; c=""; g=""; r=""; d=""; z=""
fi
case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in
  *[Uu][Tt][Ff]*) frames='⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏'; tick='✅'; cross='❌' ;;
  *) frames='| / - \'; tick='ok'; cross='x' ;;
esac

say() { printf '%s\n' "$*"; }

# step LABEL COMMAND...: run COMMAND quietly with a one-line spinner. Shows its output only if it fails; returns its status.
step() {
  label=$1; shift
  log=$(mktemp "${TMPDIR:-/tmp}/ws-host-install.XXXXXX")
  # Anywhere but a terminal (a log, a pipe) a slow step still says what it is doing, once, so it never looks stuck.
  [ -t 2 ] && [ "${TERM:-dumb}" != dumb ] || printf '%s...\n' "$label" >&2
  "$@" >"$log" 2>&1 &
  pid=$!
  trap 'kill "$pid" 2>/dev/null; rm -f "$log"; exit 130' INT TERM
  shown=0; ticks=0; start=$(date +%s)
  # shellcheck disable=SC2086
  set -- $frames; nframes=$#
  if [ -t 2 ] && [ "${TERM:-dumb}" != dumb ]; then
    while kill -0 "$pid" 2>/dev/null; do
      ticks=$((ticks + 1))
      if [ "$ticks" -ge 5 ]; then   # about half a second in: a quick step shows nothing at all
        shown=1
        n=$(( ticks % nframes )); f=""; i=0
        for f in $frames; do [ "$i" = "$n" ] && break; i=$((i + 1)); done
        printf '\r\033[K%s%s%s %s %s(%ss)%s' "$c" "$f" "$z" "$label" "$d" "$(( $(date +%s) - start ))" "$z" >&2
      fi
      sleep 0.1
    done
  fi
  rc=0
  wait "$pid" || rc=$?
  trap - INT TERM
  [ "$shown" = 1 ] && printf '\r\033[K' >&2
  if [ "$rc" != 0 ]; then
    printf '%s%s%s %s\n' "$r" "$cross" "$z" "$label" >&2
    tail -n 8 "$log" >&2
  elif [ "$shown" = 1 ] && [ $(( $(date +%s) - start )) -ge 2 ]; then
    printf '%s%s%s %s\n' "$g" "$tick" "$z" "$label" >&2
  fi
  rm -f "$log"
  return "$rc"
}

need() {
  say "ws-host cannot be installed yet: $1" >&2
  say "Fix: $2" >&2
  exit 3
}

# Packages this script needs and does not find. On Debian and Ubuntu it installs them, after saying so.
missing=""
command -v git >/dev/null 2>&1 || missing="$missing git"
[ -e /etc/ssl/certs/ca-certificates.crt ] || missing="$missing ca-certificates"
# curl and wget both: VS Code's server in WSL is fetched with one or the other, and a person's own tools use either.
command -v curl >/dev/null 2>&1 || missing="$missing curl"
command -v wget >/dev/null 2>&1 || missing="$missing wget"
# tar and xz: the launcher unpacks the pinned mise (a .tar.xz) with them.
command -v tar >/dev/null 2>&1 || missing="$missing tar"
command -v xz >/dev/null 2>&1 || missing="$missing xz-utils"
if [ -n "$missing" ]; then
  if [ "${WS_HOST_NO_APT:-}" = 1 ] || ! command -v apt-get >/dev/null 2>&1; then
    need "this machine lacks:$missing." "sudo apt install$missing"
  fi
  sudo_cmd=""
  if [ "$(id -u)" != 0 ]; then
    command -v sudo >/dev/null 2>&1 || need "this machine lacks:$missing, and sudo is not here to install them." "ask an administrator to run: apt install$missing"
    sudo_cmd=sudo
    say "${b}I need to install:${z}$missing. That needs administrator rights, so your password may be asked."
    sudo -v || need "the password was not accepted." "run this again and type your Linux password (nothing shows while you type)"
  else
    say "Installing:$missing."
  fi
  step "📋 Refreshing the package list" $sudo_cmd env DEBIAN_FRONTEND=noninteractive apt-get update -qq ||
    need "the package list could not be refreshed." "check your network, then run this again"
  # shellcheck disable=SC2086
  step "📦 Installing$missing" $sudo_cmd env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq $missing ||
    need "the packages could not be installed." "run: sudo apt install$missing"
fi

command -v git >/dev/null 2>&1 || need "git is not installed." "sudo apt install git"

PATH=$HOME/.local/bin:$PATH
export PATH

if [ -d "$target/.git" ]; then
  if step "🔄 Checking workspaces-host for news" git -C "$target" fetch --quiet origin; then
    git -C "$target" merge --ff-only --quiet '@{upstream}' 2>/dev/null ||
      say "Your copy was left exactly as it was; your work is safe."
  else
    say "Could not reach $url, so your copy was left as it was; your work is safe."
  fi
else
  mkdir -p "$(dirname "$target")"
  GIT_TERMINAL_PROMPT=0 step "📂 Copying workspaces-host" git clone --quiet "$url" "$target" || need "could not copy $url." "check your network, then run this again"
fi

mkdir -p "$HOME/.local/bin"
ln -sf "$target/ws-host" "$HOME/.local/bin/ws-host"

ws="$HOME/.local/bin/ws-host"
# ws-host's own runtime (the pinned mise, Python and uv, in ws-host's store): fetched once, here, so the first command is not the slow one. The
# launcher shows its own spinner and sizes, so this is not wrapped in a quiet step.
WS_HOST_BOOTSTRAP_ONLY=1 "$ws" || need "ws-host's runtime could not be prepared." "check your network, then run this again"
if [ "${WS_HOST_NO_ADVANCE:-}" = 1 ]; then
  "$ws" doctor || true
  say ""
  "$ws" help start || say "Next: run  ws-host help start"
else
  say ""
  say "${b}Setting up your workspace...${z}"
  "$ws" workspace ensure || true
  say ""
  # The first steps are the program's own help page, so what this prints can never differ from what it teaches.
  "$ws" help start || say "Run  ws-host help start  for what to do next."
fi

# A new terminal finds ~/.local/bin by itself on Debian and Ubuntu once it exists. This window cannot be changed from here, so say how.
case ":$orig_path:" in
  *":$HOME/.local/bin:"*) ;;
  *)
    sh_name=${SHELL:-bash}; sh_name=${sh_name##*/}
    say ""
    say "${b}🔄 One last thing:${z} this window does not know the ws-host command, or your new prompt, yet. Type the line below, or close this window and open a new one."
    say ""
    say "    ${c}exec $sh_name -l${z}"
    say ""
    say "Then try:  ${c}ws-host help start${z}"
    ;;
esac
