# Feature Specification: Managed configuration

**Spec ID:** 0010-managed-config
**Status:** Draft

**Input:** `ws-host` changes a few files in a person's home folder when the person asks: the prompt block in `~/.bashrc` or fish's
`config.fish`, and the baseline settings in VS Code's settings file. chezmoi is the engine that writes them. `ws-host` keeps a chezmoi
source state of its own, written from code, in which each file is a `modify_` script that gives a file's new text from its current
text, so a person's own lines and settings are never replaced. chezmoi shows what would change, proves a file current and writes
it only when it differs; `ws-host` adds the consent, the copy kept first and the plain words.

## The source state

- **FR-001**: `ws-host` MUST write every file it manages through `chezmoi`, and MUST NOT write a managed file any other way. The
  managed files are the shell prompt block of `bash` and `fish` (0003-kits FR-015) and VS Code's settings file (0004-editor-extension).
- **FR-002**: `ws-host` MUST run its own pinned `chezmoi`: one exact version and SHA-256 per architecture written in its code, verified
  before anything is unpacked, fetched into `ws-host`'s tools folder, and MUST NOT use a `chezmoi` found on PATH unless the person names
  it in `WS_HOST_CHEZMOI`. Offline, a `chezmoi` that is not already here MUST end the command with exit status 3 naming it.
- **FR-003**: Every `chezmoi` run MUST pass `ws-host`'s own configuration, persistent state, cache and source state, with the person's home
  folder as the destination, and MUST NOT read a person's own `chezmoi` configuration or source state, nor start one.
- **FR-004**: The source state MUST be written from code at every use and replace what was there, so it is a cache of what the code says:
  one `modify_` script per managed file, which runs `ws_host.lib.managed` on the file's current text. Those functions MUST be pure,
  use only the standard library, and give the same text when run twice on their own output.

## What a file keeps

- **FR-005**: A managed file's text outside the markers `ws-host` wrote, and every VS Code setting a person has set, MUST be left exactly as it
  is. A settings file `ws-host` cannot read safely (it has comments) MUST be left alone and said so, with the values to add by hand.
- **FR-006**: Before `chezmoi` changes an existing file `ws-host` MUST keep a copy of it in its state folder and name the copy. A file whose
  text would not change MUST NOT be written and MUST have no copy made. A symbolic link is followed and the file it points to is changed.
- **FR-007**: A prompt block that has lost its end marker MUST be left alone, with the plain words to fix it. A person's chosen theme MUST
  survive an update of the block.
- **FR-008**: `--dry-run` MUST change nothing, run no `chezmoi` and need no network.

## The commands

- **FR-009**: `config show` MUST list the managed files, each `current` or `stale`; a file is managed once a person has asked for it (`shell add`,
  `vscode ensure`), and none is managed before. `config check` MUST end non-zero when any is stale. `config ensure` MUST bring every stale one up to
  date under FR-006 and say what it did in plain words.
- **FR-010**: `shell add` and `vscode ensure` MUST write through `chezmoi` as FR-001 says, and `workspace ensure` MUST never put a theme back
  that a person changed.

## Edge cases

- A managed file outside the person's home folder: refused with the plain reason, never written, per FR-001.
- `chezmoi` fails while writing: the file is left as it was and the message names what chezmoi said, per FR-006.
- Two runs at once: each writes its own copy before it changes the file; the later one finds the file current, per FR-006.

## Assumptions

- The platform is Linux on x86_64 or aarch64 (0008-providers).
- A person's home folder is writable and holds the files named in FR-001.

## Open questions

- **OQ-1**: Whether `config ensure` should also run from `update`, so a new block text reaches people without a command.

## Key entities

- **A managed file** — a file in a person's home that `ws-host` changes, by consent, through `chezmoi`.
- **The source state** — `~/.local/share/workspaces-host/chezmoi/source`, a cache of what the code says.

## Success criteria

- **SC-001**: After `shell add bash`, `config check` passes; after the block's text is made stale, it fails; `config ensure` repairs it and keeps the old file.
- **SC-002**: Everything in a person's `.bashrc` outside the markers is byte-identical after any number of runs.

## Review & acceptance checklist

- [x] Every requirement is testable (MUST / MUST NOT), not aspirational
- [x] No company fact is asserted here
- [x] Every open item is marked, not silently decided
- [x] Public-safe: no confidential information, no unverified number stated as settled fact
