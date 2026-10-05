# Feature Specification: ws-host, the environment orchestrator

**Spec ID:** 0001-ws-host
**Status:** Draft

**Input:** `workspaces-host` is the Intellectual Frontiers environment
orchestrator, built to 0041-command-line. Its command, `ws-host`, prepares a
person's machine, clones and updates their repositories, installs kits,
checks health, and sets VS Code up with the Workspaces Console, the one extension that
is the graphical interface of every orchestrator. This spec states what it is, what it needs
on a host, how it is installed, where it keeps files, and its first commands:
`doctor`, `check`, `test`, `context` and `command`. Repositories and trust
are 0002-repositories-and-trust, kits 0003-kits, the editor
0004-editor-extension. The specs of 0041-command-line, 0025-tooling-environment
and 0026-workspaces, held in the public root, govern all of them.

## Identity and prerequisites

- **FR-001**: The repository MUST provide one orchestrator, `ws-host`, that
  follows 0041-command-line in every respect these specs do not state
  otherwise. It is a new repository with no legacy path.
- **FR-002**: `ws-host` MUST need only `python3` (3.11 or later) and `uv` on the
  host. It targets a Debian-family Linux distribution, on bare metal, under
  WSL, or inside a virtual machine or container (which is how macOS is
  supported), and MUST NOT require a container, a Nix or a version manager
  (0026-workspaces FR-001).
- **FR-003**: The launcher MUST be `ws-host` at the repository root, in POSIX
  `sh`, finding the repository from its own location even when it is run
  through a symbolic link, and running the orchestrator on the plain
  standard-library interpreter unless a command declares packages
  (0041-command-line FR-001, FR-002).
- **FR-004**: `ws-host` MUST need no third-party Python package. The
  repository's `pyproject.toml` and `uv.lock` MUST exist, name no
  dependency, and be the only TOML it keeps (0041-command-line FR-003,
  FR-049).

## Installing

- **FR-005**: `install.sh` MUST be one POSIX `sh` script that a person runs
  with one line. It MUST install what the machine lacks to get going, install
  `uv` if it is missing, clone the repository into
  `~/workspaces/github.com/intellectual-frontiers/workspaces-host` or update
  an existing clone by fast-forward only, link `~/.local/bin/ws-host`, run
  `ws-host doctor`, and set the workspace up (0006-onboarding FR-001, FR-002). It
  MUST be safe to run again, MUST change nothing a person has changed in the
  clone, and MUST say in plain words what it needs when it cannot go on.
- **FR-006**: `install.sh` MUST take its clone source and its target from
  environment variables (`WS_HOST_URL`, `WS_HOST_HOME`) so that it can be
  tested against a local repository, and MUST NOT write anywhere else.

## Where files live

- **FR-007**: `ws-host` MUST keep a person's files at these places, following
  the XDG conventions (`XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_STATE_HOME` and
  `XDG_CACHE_HOME` where set): configuration in
  `~/.config/workspaces-host/ws-host.env`; secrets in
  `~/.config/workspaces-host/secrets.env`; fetched tools, and the links of
  trusted repositories, in `~/.local/share/workspaces-host/`; logs and trust
  records in `~/.local/state/workspaces-host/`; its cache in
  `~/.cache/workspaces-host/`; and its launcher link in `~/.local/bin/ws-host`.
- **FR-008**: The person's configuration is an environment file
  (0041-command-line FR-047) whose keys are `WS_HOST_GIT_NAME`,
  `WS_HOST_GIT_EMAIL`, `WS_HOST_WORKSPACES` (the folder repositories are cloned
  under, default `~/workspaces`), `WS_HOST_GITLAB_HOSTS` and `WS_HOST_REPOS`
  (space-separated lists), and `WS_HOST_TRUSTED` (space-separated
  organizations). `ws-host` MUST refuse to read `secrets.env` unless only its
  owner can read it (mode 600), MUST prefer the credential storage of `gh` and
  `glab` to it, and MUST NOT write a secret to a log, a resource or a report.
- **FR-009**: `ws-host` MUST export to the programs it runs what they need as
  environment variables (`WORKSPACES_HOME`, the workspaces folder) and MUST NOT
  expect another orchestrator to read its files (0041-command-line FR-048).

## The registry and the first commands

- **FR-010**: The registry MUST be code, found by presence: a module under
  `ws_host/commands/` adds its commands and a module under `ws_host/kits/` adds
  its kits, and no file lists them (0041-command-line FR-007). Every such
  module MUST import only the standard library at module level
  (0041-command-line FR-005). The core, in `ws_host/core/`, MUST use the
  standard library only.
- **FR-011**: `ws-host` MUST provide `command list` and `command show ID`
  (read); `doctor` and `check [SECTION...]` (check); `test` and `fresh` (check);
  `context [RESOURCE]` and `help [TOPIC]` (read); `docs build` (build);
  `docs generate` and `skill generate` (generate); `vscode ensure`, `shell add`,
  `completion add`, `workspace ensure` and `repo sync` (setup); and `update`, each as 0041-command-line states them, with
  `--json`, `--html` and, where a command writes, `--dry-run`. Its audience is
  `private`: what it reports is about one person's machine.
- **FR-012**: `doctor` MUST change nothing and MUST report: the distribution
  and whether it is under WSL; the versions of Python and `uv`; the version of
  every program an installed kit provides (0003-kits); the registry's
  conflicts, which fail it: two commands with one name, two kits with one name,
  and a module that declares a command or a kit and imports a third-party
  package at module level (0041-command-line FR-029); the permission of
  `secrets.env`; and what it recommends. A missing optional program MUST be a
  warning that names the kit that supplies it, never a failure. Its report
  MUST hold no secret.
- **FR-013**: `check` MUST run its sections through
  0041-command-line FR-031 to FR-033. Its sections are `registry` (the
  conflicts of FR-012), `launcher` (the launcher and `install.sh` are
  executable and pass `sh -n`), `help` and `fresh` (0005-help-and-docs FR-005,
  FR-014) and `specs` (the repository's specs and
  register pass the public root's checker, where it is on the machine; a
  section whose program is missing is skipped and fails the run).
- **FR-014**: `test` MUST run the repository's tests with the standard
  library's test runner, fail on any failing test, and fail when it ran none.
- **FR-015**: The first line of every text rendering MUST be plain language
  (0041-command-line FR-054), and every displayed command MUST be one
  pasteable line (0041-command-line FR-055).
- **FR-016**: Every write MUST go through `--dry-run` first available, every
  action MUST carry its category and surfaces, and `ws-host` MUST log what
  changes or runs something to NDJSON in its state directory as
  0041-command-line FR-042 states, with the surface in the environment
  variable `WS_HOST_SURFACE` (`cli` when unset).

## Out of scope

- Repositories, trust, kits and the editor: the other specs.
- Generated container files, MCP, repo-shipped kits' loading, running on
  macOS itself and other distributions: later specs.

- **FR-017**: Every warning and every failure in `doctor`'s report MUST be
  actionable (0041-command-line FR-017, FR-055): it MUST say in plain words what
  is wrong; give the exact line that fixes it, one that can be pasted in a
  terminal, and, where a `ws-host` command fixes it, the action that runs it,
  which `doctor` returns; and, where no line fixes it, say what the person does
  themselves. A finding MUST NOT be left with none of these, and `doctor`'s
  plain sentence MUST NOT say "below", "above" or point at anything else a
  reader of it may not see.

- **FR-018**: `ws-host` MUST say how it is presented to an editor, as 0041-command-line
  FR-064 asks of every orchestrator: each command row of `command list` and
  `command show` MUST carry a `title`, a verb and an object in capitals of at
  most 40 characters whose ellipsis is present exactly when the command asks
  for a value, and an `icon` where it has one; `command list` MUST carry
  `presentation` with its `views` (each ordered above the editor's own Home) and
  its `nouns`, each with a title, an icon, the view that lists it and, where the
  noun has a `list` command that asks for nothing, how its rows read; and the
  rows of such a list MUST carry the fields it names and a status that is, or is
  mapped to, one of ok, warning, error, pending, skipped, info or muted. The
  declarations live in code (`ws_host/commands/presentation.py`), `check
  registry` MUST fail on what 0041-command-line FR-072 names, and the icons MUST
  be named in the glyph map this repository pins, copied from the public root's.
  The repository MUST declare its launcher for the editor and for ws-host in
  `.workspaces-host/provider.toml` (0008-providers FR-001), so that the Workspaces Console serves
  `ws-host` like any other orchestrator.
- **FR-019**: Nothing in this repository, its history or its published guide MAY
  name a confidential repository or say what one holds. It is public, and it
  knows only the public root.

## Edge cases

- `uv` is missing when the launcher runs: it exits 3 and says in plain words
  how to install it, per FR-003 and 0041-command-line FR-021.
- `install.sh` is run twice: the second run advances by fast-forward and
  changes nothing else, per FR-005.
- `install.sh` finds a clone with edits not yet committed: it leaves the clone
  as it is and still links the launcher, per FR-005.
- `~/.local/bin` is not on the person's `PATH`: `doctor` warns and says the one
  line that adds it, per FR-012.
- `secrets.env` is readable by others: it is refused and `doctor` fails,
  naming the fix, per FR-008 and FR-012.
- Two modules declare a command with one name: `doctor` and `check registry`
  fail naming both, per FR-010 and FR-012.
- A command module imports a package at module level: `doctor` fails, per
  FR-010 and FR-012.
- `git` is missing: `doctor` warns and names the `base` kit, per FR-012.
- `ws-host` is run through the `~/.local/bin` link: it still finds its
  repository, per FR-003.

## Assumptions

- The host has `python3` 3.11 or later and `git`, or the person can install
  them with the distribution's package manager.
- The person's home directory is writable.

## Open questions

- **OQ-1**: Whether `install.sh` should also be offered as a release asset,
  for hosts that cannot reach the repository's raw files.

## Key entities

- **ws-host** — the orchestrator of this repository.
- **The launcher** — `ws-host`, the POSIX `sh` file that starts it.
- **The person's configuration** — `ws-host.env` and `secrets.env`.
- **The registry** — the commands and kits found by presence.

## Success criteria

- **SC-001**: In a fresh Debian and a fresh Ubuntu container with only `python3`,
  `git` and `uv`, the install line works, and `ws-host doctor --json` and
  `ws-host test` pass.
- **SC-002**: `doctor` holds no secret.
- **SC-003**: Adding a module to the commands package adds its commands with
  no other edit.

## Review & acceptance checklist

- [x] Every requirement is testable (MUST / MUST NOT), not aspirational
- [x] No company fact is asserted here
- [x] Every open item is marked, not silently decided
- [x] Public-safe: no confidential information, no unverified number stated
      as settled fact
