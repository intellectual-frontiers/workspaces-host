#!/bin/sh
# Real VS Code (the pinned 1.140.0 build, installed by mise) under Xvfb: an extension asks mise for each workspace folder's environment
# (data only, MISE_SAFE=1) and scopes it to that folder, so the integrated terminal of one folder gets the provider's pinned `java` and the
# other folder's terminal gets the system one. Needs the provider's tools installed (../run.sh), Xvfb, and VS Code's libraries.
# usage: run.sh PROVIDER_DIR OTHER_DIR VSCODE_DIR MISE_BIN   (VSCODE_DIR is `mise where http:vscode`)
set -eu
P=$1 O=$2 C=$3 M=$4; here=$(cd "$(dirname "$0")" && pwd); W=$(mktemp -d)
mkdir -p "$W/ws"; ln -s "$P" "$W/ws/provider"; ln -s "$O" "$W/ws/other"
printf '{ "folders": [ {"path": "provider"}, {"path": "other"} ], "settings": {"security.workspace.trust.enabled": false} }' > "$W/ws/spike.code-workspace"
SPIKE_OUT=$W/out SPIKE_MISE=$M timeout 150 xvfb-run -a -s "-screen 0 1280x800x24" "$C/code" --no-sandbox --disable-gpu-sandbox --disable-gpu \
  --disable-updates --skip-welcome --skip-release-notes --no-cached-data --disable-workspace-trust --user-data-dir="$W/ud" \
  --extensions-dir="$W/exts" --extensionDevelopmentPath="$here" "$W/ws/spike.code-workspace" >"$W/code.log" 2>&1 || true
cat "$W/out.log" "$W/out"
