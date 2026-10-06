"""What ws-host puts in the files it manages, as plain functions from a file's text to its new text (0010-managed-config).

Standard library only, and no import of the rest of ws-host: chezmoi runs these as its `modify_` scripts through
`python -m ws_host.lib.managed KIND ARGS`, with the file's current text on stdin and the new text on stdout. Running one twice gives
the same text, so `chezmoi verify` can say a file is current."""
from __future__ import annotations

import json
import os
import sys

BEGIN = "# >>> workspaces-host: prompt (ws-host shell add {shell}) >>>"
END = "# <<< workspaces-host <<<"
COMMENT = ("# Delete these lines to go back to your old prompt. To change the look, edit the theme name on the next lines: ws-host-pretty needs a\n"
           "# Nerd Font in your terminal, ws-host-plain does not. Or run: ws-host shell add {shell} --plain")


class MarkersLost(ValueError):
    """The start marker is there and the end marker is not."""


def block(shell: str, theme: str) -> str:
    """The marked lines in a shell's startup file: the prompt, the PATH entry and the background look for a newer ws-host."""
    comment = COMMENT.format(shell=shell)
    if shell == "bash":
        body = (f'{comment}\n'
                'case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) PATH="$HOME/.local/bin:$PATH" ;; esac\n'
                'if command -v oh-my-posh >/dev/null 2>&1; then\n'
                f'  eval "$(oh-my-posh init bash --config "{theme}")"\n'
                'fi\n'
                '# ws-host looks for a newer version in the background, at most every six hours, and says here when one is waiting (not in the terminal inside VS Code, where the Console says it).\n'
                '_wsh_state="${XDG_STATE_HOME:-$HOME/.local/state}/workspaces-host"\n'
                'if [ -s "$_wsh_state/update-available" ] && [ "${TERM_PROGRAM:-}" != vscode ]; then\n'
                '  if [ -z "${NO_COLOR:-}" ]; then printf \'\\033[1;36m🔄 %s\\033[0m\\n\' "$(cat "$_wsh_state/update-available")"; else cat "$_wsh_state/update-available"; fi\n'
                'fi\n'
                'if command -v ws-host >/dev/null 2>&1 && [ -z "$(find "$_wsh_state/update-checked" -mmin -360 2>/dev/null)" ]; then\n'
                '  (ws-host update --check --background >/dev/null 2>&1 &)\n'
                'fi\n'
                'unset _wsh_state')
    else:
        body = (f'{comment}\n'
                'if status is-interactive\n'
                '  fish_add_path -g $HOME/.local/bin\n'
                '  if command -q oh-my-posh\n'
                f'    oh-my-posh init fish --config "{theme}" | source\n'
                '  end\n'
                '  # ws-host looks for a newer version in the background, at most every six hours, and says here when one is waiting (not in the terminal inside VS Code, where the Console says it).\n'
                '  set -l _wsh_state (set -q XDG_STATE_HOME; and echo $XDG_STATE_HOME; or echo $HOME/.local/state)/workspaces-host\n'
                '  if test -s $_wsh_state/update-available; and test "$TERM_PROGRAM" != vscode\n'
                '    set_color brcyan; echo "🔄 "(cat $_wsh_state/update-available); set_color normal\n'
                '  end\n'
                '  set -l _wsh_recent (find $_wsh_state/update-checked -mmin -360 2>/dev/null)\n'
                '  if command -q ws-host; and test (count $_wsh_recent) -eq 0\n'
                '    ws-host update --check --background >/dev/null 2>&1 &\n'
                '    disown\n'
                '  end\n'
                'end')
    return f"{BEGIN.format(shell=shell)}\n{body}\n{END}\n"


def with_block(text: str, shell: str, theme: str, keep_existing: bool = False) -> str:
    """The file's text with the block added, or the existing block replaced (kept as it is when `keep_existing`, so a theme a person
    edited into it is never put back); nothing outside the markers is touched."""
    new = block(shell, theme)
    begin = BEGIN.format(shell=shell)
    if begin in text:
        head, _, rest = text.partition(begin)
        if END not in rest:
            raise MarkersLost(shell)
        if keep_existing:
            return text
        _, _, tail = rest.partition(END + "\n")
        return head + new + tail
    return text + ("" if not text or text.endswith("\n") else "\n") + ("\n" if text else "") + new


def with_settings(text: str, wanted: dict) -> str | None:
    """A VS Code settings file with the settings the person has not set added, and none they have changed; None when the file cannot be
    read safely (it probably has comments), in which case the file is left exactly as it is."""
    try:
        current = json.loads(text or "{}")
        if not isinstance(current, dict):
            return None
    except ValueError:
        return None
    added = {k: v for k, v in wanted.items() if k not in current}
    if not added and text:
        return text
    return json.dumps({**current, **added}, indent=2) + "\n"


def main(argv: list[str]) -> int:
    kind, args = argv[0], argv[1:]
    text = sys.stdin.read()
    try:
        if kind in ("bash", "fish"):
            out = with_block(text, kind, args[0], keep_existing=os.environ.get("WS_HOST_KEEP_BLOCK") == "1")
        elif kind == "vscode-settings":
            out = with_settings(text, json.loads(args[0]))
            out = text if out is None else out
        else:
            print(f"unknown kind {kind}", file=sys.stderr)
            return 2
    except MarkersLost:
        out = text           # a block that lost its end line is left alone; `config check` says so
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
