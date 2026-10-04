#!/bin/sh
# Verify install and kits on a fresh Debian-family container (0001-ws-host SC-001, 0003-kits SC-001). Run on a machine with
# docker, from the repository root (the host's `uv` binary is mounted so the container needs only python3 and git):
#
#   for image in debian:trixie ubuntu:24.04; do
#     docker run --rm -v "$PWD":/src:ro -v "$(dirname "$(command -v uv)")":/uvbin:ro \
#       -v "$PWD/tests/containers/verify.sh":/verify.sh:ro $image sh /verify.sh [kit ...]
#   done
#
# With no kit named it runs install, doctor and the tests only. Naming kits (base press rust) also installs each.
set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null
apt-get install -y -qq python3 git ca-certificates >/dev/null 2>&1
cp /uvbin/uv /usr/local/bin/uv
git config --global --add safe.directory '*'
git clone -q --bare /src /tmp/remote.git
WS_HOST_URL=/tmp/remote.git sh /src/install.sh
export PATH="$HOME/.local/bin:$PATH"
ws-host doctor --json >/dev/null
ws-host test
for kit in "$@"; do
  ws-host kit add "$kit"
done
