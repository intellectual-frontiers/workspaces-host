# Feature Specification: The editor extension

**Spec ID:** 0004-editor-extension
**Status:** Draft

**Input:** The VS Code extension that is the graphical interface of every
orchestrator (0041-command-line FR-050 to FR-053), and the `vscode add`
command that installs it. It lives only in `vscode/` of this repository, is
plain JavaScript with no build step, holds no behavior of its own, and only
renders the resources an orchestrator returns and runs their actions by
invoking that orchestrator. Its rules about decisions, trust and plain
language come from 0041-command-line and 0002-repositories-and-trust.

## What it is

- **FR-001**: The extension MUST live in `vscode/` and nowhere else, as
  `package.json`, `extension.js` and the one icon file the package names
  (`logo.png`), with no TypeScript, no build step and no
  `node_modules`, so that the clone is the installed extension and advancing the
  clone updates it (after a window reload). Anything VS Code requires to be in
  `package.json` is permitted there, because VS Code owns that format
  (0041-command-line FR-049).
- **FR-002**: The extension MUST be a generic orchestrator client. It MUST
  discover the launcher at the root of each trusted repository, run
  `<name> command list --json` and `<name> <noun> <verb> ... --json` or
  `--html`, and run nothing else. It MUST NOT contain a rule, a path, a
  command name or a repository name of any one orchestrator, except that it
  runs `ws-host`, its own, for the list of trusted repositories and for what
  only `ws-host` does.
- **FR-003**: The extension MUST declare `extensionKind: ["workspace"]` and
  `capabilities.untrustedWorkspaces: false`, MUST run no orchestrator in VS
  Code's Restricted Mode and say so in plain words, and MUST run the
  orchestrator of a repository only when `ws-host` reports the repository as
  trusted (0002-repositories-and-trust FR-012).

## What it shows

- **FR-004**: The extension MUST show a status bar item whose text is plain
  language (the first line of a text rendering, 0041-command-line FR-054) and
  which is shown as well, as a warning, or as a failure, from `ws-host doctor`.
- **FR-005**: The extension MUST show a sidebar tree grouped by orchestrator,
  each showing its audience, then its nouns, then its commands that the editor
  exposes (0041-command-line FR-022). Choosing a command that needs no value
  MUST run it and show its resource; one that needs a value MUST ask for it
  (FR-007).
- **FR-006**: The extension MUST show a resource as its HTML rendering in a
  webview with a content security policy that allows only its own nonce'd
  script and inline style, no remote resource, and no other script. Each
  action MUST be a button; an action the editor does not expose
  (0041-command-line FR-022) MUST be shown as disabled with its reason; and
  every action that has a command MUST have a "Show command" link that shows the
  one pasteable line (0041-command-line FR-055) and offers to copy it.
- **FR-007**: A typed argument (0041-command-line FR-013) MUST be asked for
  with a quick-pick when the orchestrator supplies its choices and an input box
  otherwise, never by printing a command with a placeholder. The extension MUST
  take the argument's name, type, choices and whether it is positional from
  `command show`, and MUST build the command line from them.
- **FR-008**: A stream (0041-command-line FR-019) MUST be shown as a progress
  notification that follows each document's plain first line, and the last
  document MUST be shown as a resource.
- **FR-009**: The extension MUST show the findings of `check` in VS Code's
  Problems panel, each at its file and line where the finding names one and
  otherwise at the repository.
- **FR-010**: When a resource's schema (`<name>/<kind>@<n>`,
  0041-command-line FR-019) has a version newer than the extension understands,
  the extension MUST say in plain words that an update is needed, offer to
  update, and show nothing it cannot read.

## What it will not do

- **FR-011**: A `decision` action MUST require a modal confirmation that names
  what will change. No path in the extension MUST run a `decision` without it,
  and the extension MUST register no VS Code command that takes an action, a
  command line or a resource as an argument, so that an AI agent in the
  editor cannot trigger one through VS Code's commands
  (0041-command-line FR-051). The extension MUST pass `--confirmed` only after
  the modal, with the surface `editor`.
- **FR-012**: The extension MUST NOT write any file, change any setting, or
  change any configuration of git, of VS Code or of the person: only the
  orchestrators it runs do, and only by the actions a person chose.
- **FR-013**: The extension MUST run orchestrators with the environment
  variable `WS_HOST_SURFACE=editor`, so that what they log names the surface
  (0041-command-line FR-042).

## Signing in and help

- **FR-014**: When `ws-host` reports the person is not signed in, the extension
  MUST offer, as a notification, to sign in. Signing in MUST run `ws-host auth
  new github` as a stream, show the one-time code and its address in a
  notification with the action "Copy code and open browser", and report the
  result in plain words.
- **FR-018**: The extension MUST offer "Learn", a command that lists the topics
  of the orchestrator's `help` as a quick-pick and shows the chosen topic as a
  resource, its steps as buttons (0005-help-and-docs FR-004).
- **FR-015**: The extension MUST offer a "Get help" command that gathers
  `ws-host context` and `ws-host doctor`, which hold no secret, into one text
  the person can paste to a person or an AI, copies it, and shows it.

## Installing it

- **FR-016**: `vscode add` (setup) MUST link `vscode/` into
  `~/.vscode/extensions`, or into `~/.vscode-server/extensions` where VS Code
  runs in WSL mode, as `<publisher>.<name>-<version>`; and MUST register it in
  that directory's `extensions.json` index when one is present, keeping every
  other entry. Where the index is absent it MUST build a `.vsix` with Python's
  `zipfile` and install it with `code --install-extension`, and where `code` is
  absent it MUST link the directory and say in plain words what remains. It MUST
  take `--dry-run`, be repeatable, and change no VS Code setting.
- **FR-017**: The contract the extension relies on MUST be tested from
  Python: the shape of `command list`, `command show`, every resource and its
  actions, the HTML rendering's buttons and security policy, the schema string,
  the `decision` category, and the surfaces. The extension's own logic MUST be
  structured so that Node can test it with VS Code's API replaced by a stand-in,
  and its activation MUST be tested in VS Code where one can run.

## Out of scope

- Repo-shipped kits and MCP.
- Editors other than VS Code.

## Edge cases

- VS Code is in Restricted Mode: nothing runs and the status bar says why, per
  FR-003.
- A repository is cloned but not trusted: its orchestrator does not appear and
  nothing of it runs, per FR-003.
- An orchestrator answers with a newer schema: "update needed", per FR-010.
- A decision is offered by a resource: it is a button, and clicking it opens a
  modal; cancelling changes nothing, per FR-011.
- An AI agent calls a VS Code command to run a decision: no such command
  exists, per FR-011.
- An action needs a repository name: a quick-pick lists the known ones, per
  FR-007.
- An action is `setup` and not exposed to the editor: disabled, with its
  command to show, per FR-006.
- A `check` finding names `src/a.py:12`: it is shown at that file and line, per
  FR-009.
- The person is not signed in: a notification offers it; the code and address
  appear in a second notification, per FR-014.
- `vscode add` run twice: one link and one index entry, per FR-016.
- `~/.vscode/extensions/extensions.json` holds other extensions: they are kept,
  per FR-016.
- VS Code runs under WSL: the link is in `~/.vscode-server/extensions`, per
  FR-016.

## Assumptions

- VS Code 1.85 or later, with the extension host in the same machine or WSL
  distribution as the repositories.
- `ws-host` is installed and on the person's `PATH` or at `~/.local/bin`.

## Open questions

- **OQ-1**: Whether the extension should offer to run `workspace advance` when
  a window opens, and how often.

## Key entities

- **The extension** — `vscode/`, the one graphical interface.
- **An editor view** — a resource and its actions, shown in a webview.

## Success criteria

- **SC-001**: With the extension installed, a person sees whether their machine
  is well, signs in with a code, and brings their repositories up to date
  without typing a command.
- **SC-002**: No decision runs without a person's click on a modal.

## Review & acceptance checklist

- [x] Every requirement is testable (MUST / MUST NOT), not aspirational
- [x] No company fact is asserted here
- [x] Every open item is marked, not silently decided
- [x] Public-safe: no confidential information, no unverified number stated
      as settled fact
