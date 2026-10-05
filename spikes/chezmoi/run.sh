#!/bin/sh
# Spike: ws-host's managed configuration (shell prompt, completions, themes, VS Code settings) as a chezmoi source, applied into a throwaway HOME.
# usage: run.sh CHEZMOI_BINARY [WORK]     (the binary is `mise exec -- which chezmoi`; see ../mise/)
set -u
CZ=$1; WORK=${2:-${TMPDIR:-/tmp}/chezmoi-spike}; here=$(cd "$(dirname "$0")" && pwd)
rm -rf "$WORK"; mkdir -p "$WORK/home" "$WORK/state"; H=$WORK/home
say() { printf '\n== %s\n' "$*"; }
# ws-host owns the chezmoi configuration, state and data, so a person's own chezmoi (their ~/.local/share/chezmoi) is never involved.
printf '{"prompt":"yes","theme":"ws-host-pretty","wsl":false,"protect":[]}' > "$WORK/data.json"
cz() { HOME=$H "$CZ" --source "$here/home" --destination "$H" --config "$WORK/chezmoi.toml" --persistent-state "$WORK/state/chezmoistate.boltdb" \
        --override-data-file "$WORK/data.json" --no-tty "$@" </dev/null; }
: > "$WORK/chezmoi.toml"

say "1 first apply into a home that already has a .bashrc and settings.json"
mkdir -p "$H/.config/Code/User"
printf 'export EDITOR=vim\nalias ll="ls -l"\n' > "$H/.bashrc"
printf '{\n  "editor.fontSize": 14,\n  "files.autoSave": "off"\n}\n' > "$H/.config/Code/User/settings.json"
echo "-- chezmoi status (what would change; A add, M modify):"; cz status 2>&1 | sed 's|^|   |'
cz apply >/dev/null 2>&1; echo "apply rc=$?"
echo "-- .bashrc (the person's two lines are first and untouched):"; head -4 "$H/.bashrc" | sed 's|^|   |'
echo "-- settings: the person's files.autoSave=off is kept, missing keys added:"; grep -c . "$H/.config/Code/User/settings.json" | sed 's|^|   lines: |'; grep '"files.autoSave"\|"editor.fontSize"\|git.autofetch' "$H/.config/Code/User/settings.json" | sed 's|^|   |'
echo "-- written:"; (cd "$H" && find . -type f | sort | sed 's|^|   |')

say "2 a second apply changes nothing (drift check: verify exits 0, status empty)"
cz verify; echo "verify rc=$?"; echo "status: [$(cz status 2>&1)]"; before=$(find "$H" -type f -exec sha256sum {} + | sha256sum); cz apply >/dev/null 2>&1; [ "$before" = "$(find "$H" -type f -exec sha256sum {} + | sha256sum)" ] && echo "bytes identical after a second apply"

say "3 the person edits a file ws-host owns completely: apply (no --force, no terminal) leaves it alone"
echo '# my own tweak' >> "$H/.config/fish/conf.d/ws-host.fish"
cz apply >"$WORK/out3" 2>&1; echo "apply rc=$?"; head -3 "$WORK/out3" | cut -c1-200 | sed 's|^|   |'; tail -1 "$H/.config/fish/conf.d/ws-host.fish" | sed 's|^|   still: |'
echo "-- status marks it as modified outside chezmoi (column 1 = target changed since chezmoi wrote it):"; cz status 2>&1 | sed 's|^|   |'
cz apply --force >/dev/null 2>&1; echo "-- (only --force would restore it)"; tail -1 "$H/.config/fish/conf.d/ws-host.fish" | cut -c1-40 | sed 's|^|   |'

say "4 a start marker without an end marker: that file is left as it was, the rest still applies with --keep-going"
printf 'export A=1\n# >>> workspaces-host: prompt (ws-host shell add bash) >>>\nbroken\n' > "$H/.bashrc"; cp "$H/.bashrc" "$WORK/bashrc.broken"
echo '{"prompt":"yes","theme":"ws-host-plain","wsl":false,"protect":[]}' > "$WORK/data.json"
cz apply --keep-going >"$WORK/out4" 2>&1; echo "apply rc=$?"; grep -m1 "^chezmoi" "$WORK/out4" | cut -c1-230 | sed 's|^|   |'
cmp -s "$H/.bashrc" "$WORK/bashrc.broken" && echo "   .bashrc untouched"; grep -c "ws-host-plain" "$H/.config/fish/conf.d/ws-host.fish" | sed 's|^|   other files still updated (fish theme now plain): |'

say "5 prompt off removes the block and nothing else"
printf 'export EDITOR=vim\n' > "$H/.bashrc"; echo '{"prompt":"yes","theme":"ws-host-pretty","wsl":false,"protect":[]}' > "$WORK/data.json"; cz apply >/dev/null 2>&1
echo '{"prompt":"no","theme":"ws-host-pretty","wsl":false,"protect":[]}' > "$WORK/data.json"; cz apply --force >/dev/null 2>&1; cat "$H/.bashrc" | sed 's|^|   |'; wc -c < "$H/.config/fish/conf.d/ws-host.fish" | sed 's|^|   fish file is now bytes: |'

say "6 settings.json with comments cannot be read safely: untouched, an error says why"
printf '{\n  // my comment\n  "editor.fontSize": 14\n}\n' > "$H/.config/Code/User/settings.json"; cp "$H/.config/Code/User/settings.json" "$WORK/settings.comments"
cz apply --keep-going >"$WORK/out6" 2>&1; grep -m1 "^chezmoi" "$WORK/out6" | cut -c1-200 | sed 's|^|   |'; cmp -s "$H/.config/Code/User/settings.json" "$WORK/settings.comments" && echo "   settings.json untouched"

say "7 a backup of every file that is about to change, before the apply (chezmoi keeps none of its own)"
printf 'export EDITOR=vim\nalias ll="ls -l"\n' > "$H/.bashrc"; printf '{\n  "editor.fontSize": 14\n}\n' > "$H/.config/Code/User/settings.json"
echo '{"prompt":"yes","theme":"ws-host-pretty","wsl":false,"protect":[]}' > "$WORK/data.json"
BK=$WORK/backups/$(date +%Y%m%d-%H%M%S); mkdir -p "$BK"
cz status 2>/dev/null | while read -r flags path; do case "$flags" in M*|MM) mkdir -p "$BK/$(dirname "$path")"; cp -p "$H/$path" "$BK/$path";; esac; done
cz apply >/dev/null 2>&1; echo "apply rc=$?"; (cd "$BK" && find . -type f | sort | sed 's|^|   backed up: |')
cp -p "$BK/.bashrc" "$H/.bashrc"; head -2 "$H/.bashrc" | sed 's|^|   restored: |'; grep -c workspaces-host "$H/.bashrc" | sed 's|^|   ws-host lines after restore (undo works): |'
cz apply --force >/dev/null 2>&1

say "8 a person's own chezmoi (default source, config and state) is untouched, and the two do not see each other"
mkdir -p "$H/.local/share/chezmoi" "$H/.config/chezmoi"; printf '[user]\n  name = Someone\n' > "$H/.local/share/chezmoi/dot_gitconfig"
HOME=$H "$CZ" apply --no-tty </dev/null >/dev/null 2>&1; echo "their apply rc=$?"; echo "their managed: [$(HOME=$H "$CZ" managed --include=files </dev/null | tr '\n' ' ')]"
echo "ws-host managed: [$(cz managed --include=files | wc -l) files, none is .gitconfig: $(cz managed --include=files | grep -c '^.gitconfig$')]"
echo "-- if their chezmoi manages the WHOLE .bashrc, their apply replaces ws-host's block and ws-host's apply puts it back:"
printf 'their own bashrc\n' > "$H/.local/share/chezmoi/dot_bashrc"; HOME=$H "$CZ" apply --no-tty --force </dev/null >/dev/null 2>&1; grep -c workspaces-host "$H/.bashrc" | sed 's|^|   after their apply, ws-host lines: |'
cz apply --force >/dev/null 2>&1; grep -c workspaces-host "$H/.bashrc" | sed 's|^|   after ws-host apply, ws-host lines: |'; grep -c "their own" "$H/.bashrc" | sed 's|^|   and their line is kept: |'
rm -f "$H/.local/share/chezmoi/dot_bashrc"

say "9 the source is package data and can be read-only (run as an ordinary user)"
if id brewtest >/dev/null 2>&1; then
  cp "$CZ" /tmp/cz-bin && chmod 755 /tmp/cz-bin; rm -rf /tmp/cz-ro && cp -r "$here/home" /tmp/cz-ro && chmod -R a-w /tmp/cz-ro; mkdir -p /tmp/cz-h /tmp/cz-s; chown -R brewtest /tmp/cz-h /tmp/cz-s; mkdir -p /tmp/cz-cfg && cp "$WORK/data.json" "$WORK/chezmoi.toml" /tmp/cz-cfg/ && chmod -R a+rX /tmp/cz-cfg
  su brewtest -c "HOME=/tmp/cz-h /tmp/cz-bin --source /tmp/cz-ro --destination /tmp/cz-h --config /tmp/cz-cfg/chezmoi.toml --persistent-state /tmp/cz-s/s.boltdb --override-data-file /tmp/cz-cfg/data.json --no-tty apply </dev/null >/dev/null 2>&1; echo apply rc=\$?; ls /tmp/cz-h/.config/fish/conf.d" | sed 's|^|   |'
  chmod -R u+w /tmp/cz-ro; rm -rf /tmp/cz-ro /tmp/cz-h /tmp/cz-s /tmp/cz-bin /tmp/cz-cfg
else echo "   (skipped: no ordinary user here)"; fi

say "10 WSL: ws-host says so in the data, and the settings go to ~/.vscode-server instead of ~/.config/Code"
rm -rf "$H/.config/Code" "$H/.vscode-server"; echo '{"prompt":"yes","theme":"ws-host-pretty","wsl":true,"protect":[]}' > "$WORK/data.json"; cz apply --force >/dev/null 2>&1
(cd "$H" && ls .vscode-server/data/Machine/settings.json .config/Code 2>&1 | sed 's|^|   |'); echo '{"prompt":"yes","theme":"ws-host-pretty","wsl":false,"protect":[]}' > "$WORK/data.json"

say "11 the workspace file lives in the person's workspaces folder, which is wherever they chose: a second source and destination"
WS=$WORK/workspaces; mkdir -p "$WS"
printf '{"wsl":false,"folders":[{"path":"github.com/org/.github","name":".github"},{"path":"github.com/org/workspaces-host","name":"workspaces-host"}]}' > "$WORK/wsdata.json"
czw() { HOME=$H "$CZ" --source "$here/workspace-home" --destination "$WS" --config "$WORK/chezmoi.toml" --persistent-state "$WORK/state/ws.boltdb" --override-data-file "$WORK/wsdata.json" --no-tty "$@" </dev/null; }
czw apply >/dev/null 2>&1; echo "first apply rc=$?"; python3 -c "import json;d=json.load(open('$WS/workspaces.code-workspace'));print('   folders:',[f['path'] for f in d['folders']]);print('   settings:',sorted(d['settings']));print('   recommendations:',d['extensions']['recommendations'])"
python3 - "$WS/workspaces.code-workspace" <<'P'
import json,sys
p=sys.argv[1]; d=json.load(open(p)); d['folders'].insert(0,{"path":"mine/own-repo"}); d['settings']['window.title']="my title"; json.dump(d,open(p,'w'),indent=2)
P
printf '{"wsl":false,"folders":[{"path":"github.com/org/.github","name":".github"},{"path":"github.com/org/workspaces-host","name":"workspaces-host"},{"path":"github.com/org/eidolon","name":"eidolon"}]}' > "$WORK/wsdata.json"
czw apply --force >/dev/null 2>&1; python3 -c "import json;d=json.load(open('$WS/workspaces.code-workspace'));print('   after a third repo is cloned:',[f['path'] for f in d['folders']]);print('   their title kept:',d['settings']['window.title'])"
czw apply --force >/dev/null 2>&1; czw verify; echo "   second apply verify rc=$?"

say "12 a file that exists and is not ws-host's is never replaced the first time: chezmoi alone would overwrite it, so ws-host finds it first and protects it"
rm -rf "$WORK/h2" "$WORK/state2"; mkdir -p "$WORK/h2/.config/fish/completions" "$WORK/state2"; echo '# the person wrote this' > "$WORK/h2/.config/fish/completions/ws-host.fish"
cz2() { HOME=$WORK/h2 "$CZ" --source "$here/home" --destination "$WORK/h2" --config "$WORK/chezmoi.toml" --persistent-state "$WORK/state2/s.boltdb" --override-data-file "$WORK/data2.json" --no-tty "$@" </dev/null; }
echo '{"prompt":"yes","theme":"ws-host-pretty","wsl":false,"protect":[]}' > "$WORK/data2.json"
echo "-- without the check, chezmoi replaces it silently:"; cp -r "$WORK/h2" "$WORK/h2.copy"; HOME=$WORK/h2.copy "$CZ" --source "$here/home" --destination "$WORK/h2.copy" --config "$WORK/chezmoi.toml" --persistent-state "$WORK/state2/copy.boltdb" --override-data-file "$WORK/data2.json" --no-tty apply </dev/null >/dev/null 2>&1; head -1 "$WORK/h2.copy/.config/fish/completions/ws-host.fish" | cut -c1-60 | sed 's|^|   |'
echo "-- ws-host's check: a whole-file target that exists, differs and has no ws-host header is protected:"
prot=""; for f in $(cz2 managed --include=files); do
  src=$(cz2 source-path "$WORK/h2/$f" 2>/dev/null); case "$(basename "$src")" in modify_*) continue;; esac
  if [ -f "$WORK/h2/$f" ] && ! head -1 "$WORK/h2/$f" | grep -q 'ws-host'; then prot="$prot\"$f\","; fi; done
echo "{\"prompt\":\"yes\",\"theme\":\"ws-host-pretty\",\"wsl\":false,\"protect\":[${prot%,}]}" > "$WORK/data2.json"; echo "   protect list: $(python3 -c "import json;print(json.load(open('$WORK/data2.json'))['protect'])")"
cz2 apply >/dev/null 2>&1; echo "   apply rc=$?"; head -1 "$WORK/h2/.config/fish/completions/ws-host.fish" | sed 's|^|   still: |'; ls "$WORK/h2/.config/fish/conf.d" | sed 's|^|   other files applied: |'

say "13 cost: how long a first and a second apply take"
rm -rf "$WORK/h3" "$WORK/state3"; mkdir -p "$WORK/h3" "$WORK/state3"; echo '{"prompt":"yes","theme":"ws-host-pretty","wsl":false,"protect":[]}' > "$WORK/data3.json"
cz3() { HOME=$WORK/h3 "$CZ" --source "$here/home" --destination "$WORK/h3" --config "$WORK/chezmoi.toml" --persistent-state "$WORK/state3/s.boltdb" --override-data-file "$WORK/data3.json" --no-tty "$@" </dev/null; }
ms() { date +%s%N; }; a=$(ms); cz3 apply >/dev/null 2>&1; b=$(ms); cz3 apply >/dev/null 2>&1; c=$(ms); echo "   first apply: $(( (b - a) / 1000000 )) ms; second apply: $(( (c - b) / 1000000 )) ms"
echo "   with nothing to do, apply --dry-run --verbose prints: [$(cz3 apply --dry-run --verbose 2>&1 | head -2)]"; cz3 verify; echo "   verify rc=$?"
echo done
