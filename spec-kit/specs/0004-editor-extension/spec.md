# Feature Specification: The editor

**Spec ID:** 0004-editor-extension
**Status:** Draft

**Input:** How `ws-host` is used from VS Code. The editor surface of every orchestrator is one extension, the Workspaces Console
(0041-command-line FR-050), which finds a repository's command line by its own declaration and draws what it returns. It is built
in this repository, in `console/`, and released with `ws-host` (0007-releases). This spec states what `ws-host` does so that the
Workspaces Console works with it: it installs the Console from the latest release, tells the editor how it looks (0001-ws-host FR-018),
and writes a workspace file that lists the repositories a person works in. The older requirements of an extension that `ws-host`
shipped on its own are retired and say what governs now.

## What it was

- **FR-001**: Retired. Ws-host ships no extension; the Workspaces Console is the one extension (0043-if-console FR-001, FR-002).
- **FR-002**: Retired. The Workspaces Console discovers launchers by their own declaration and holds no rule of any orchestrator (0043-if-console FR-003 to FR-005).
- **FR-003**: Retired. The Workspaces Console runs only in a trusted workspace for a trusted repository (0043-if-console FR-006).
- **FR-004**: Retired. The Workspaces Console's status bar item names how many things need a person and what to do (0043-if-console FR-016, FR-048).
- **FR-005**: Retired. The Workspaces Console's views and tree come from the command line's own presentation (0043-if-console FR-008, FR-036; 0001-ws-host FR-018).
- **FR-006**: Retired. The Workspaces Console draws a resource in one panel from its JSON (0043-if-console FR-003, FR-042).
- **FR-007**: Retired. The Workspaces Console builds the input of a command from its typed arguments (0043-if-console FR-013).
- **FR-008**: Retired. The Workspaces Console follows a stream as progress (0043-if-console FR-020).
- **FR-009**: Retired. The Workspaces Console shows the findings of a check in the Problems panel (0043-if-console FR-009).
- **FR-010**: Retired. The Workspaces Console checks each document's schema (0043-if-console FR-021).
- **FR-011**: Retired. A decision needs a modal and no command takes an action (0043-if-console FR-015).
- **FR-012**: Retired. The Workspaces Console writes nothing itself (0043-if-console FR-026).
- **FR-013**: Retired. What a command logs names its surface (0041-command-line FR-042).
- **FR-014**: Retired. Signing in is an action like any other (0043-if-console FR-013 to FR-015); the sign-in code is shown by the resource `auth new` returns.
- **FR-015**: Retired. The Workspaces Console offers Get Help and Copy Context (0043-if-console FR-012, FR-018).
- **FR-018**: Retired. The Workspaces Console offers Learn on the same panel (0043-if-console FR-031, FR-043).
- **FR-019**: Retired. Every suggestion is actionable in the Workspaces Console (0043-if-console FR-048); `doctor` supplies the actions (0001-ws-host FR-017).

## Installing the Workspaces Console

- **FR-016**: Retired. `vscode ensure` installs the Workspaces Console from the public root (FR-021).
- **FR-017**: Retired. The contract the Workspaces Console relies on is tested from Python (FR-025).
- **FR-020**: `ws-host` MUST ship exactly one editor extension, the Workspaces Console, in `console/`, released as 0007-releases states,
  and MUST NOT provide a command that installs any other (0041-command-line FR-050).
- **FR-021**: `vscode ensure` (setup) MUST install the Workspaces Console as 0007-releases FR-013 states, with `code --install-extension`,
  only when `code` is reachable. A call of `code` MUST be a visible step that ends plainly when it takes more than fifteen minutes
  (0006-onboarding FR-020), and `--dry-run` MUST install nothing.
- **FR-022**: Retired. A release is installed as 0007-releases FR-013 states.
- **FR-023**: `vscode ensure` MUST write `workspaces.code-workspace` in the
  person's workspaces folder (never in a clone), listing the cloned repositories
  they work in as relative folders, so that the Workspaces Console finds each one's
  command line (0043-if-console FR-007). It MUST add only folders that are not
  there, keep every folder and setting the person has, and leave a file it
  cannot read safely exactly as it was, saying so.
- **FR-024**: `workspace ensure` MUST say, from a record `vscode ensure` keeps
  and without calling VS Code, whether the Workspaces Console is installed, and when it
  is not give the one action `vscode ensure`; it MUST NOT build or install it.
- **FR-025**: The contract the Workspaces Console relies on MUST be tested from Python:
  the shape of `command list` and `command show` with their titles and icons,
  every resource and its actions, the HTML rendering, the schema string, the
  `decision` category, the surfaces, and that every warning has an action, a
  line or what to do (0001-ws-host FR-017, FR-018).

- **FR-026**: Retired. A release is installed as 0007-releases FR-013 states.

- **FR-027**: The Workspaces Console serving `ws-host` MUST be tested in a real VS Code, under a display server, with the Console's own
  runner (`console/test/vscode/run.js`) and this repository's suite in `tests/if_console/vscode/`, run by `ws-host check console`. It MUST
  cover: the Workspaces Console finding `ws-host` by its `.if-console.env` and reading its name and audience; the views `ws-host` asks
  for, planned in the order it asks; the repository and kit lists with a status icon for each row; every editor command titled and All
  commands listing its nouns and repository-wide commands; what doctor says needs a person shown on Home with the exact line that fixes
  it; and that a decision is never offered over MCP. The section MUST be skipped, naming the cause, where VS Code or a display server is
  not on the machine, and MUST run only when named.

- **FR-028**: A person MUST be taught `workspaces.code-workspace` in the
  workspaces folder (`~/workspaces`, where every `*.code-workspace` file lives)
  as the default way to open their repositories together, and MUST be told they
  may make other workspace files there, such as one per Git service (GitHub,
  GitLab) or one per organization on the same service. Nothing MAY forbid a
  person's own file. `vscode ensure` MUST write only the default file, with a folder
  and a short name for each repository that is copied here, each folder's `path`
  relative to the workspaces folder itself (`github.com/<owner>/<repo>`, so the
  file works wherever the folder is and is never written with an absolute path),
  the window title `Workspaces` first, folders not compacted, and the Workspaces Console
  recommended; it MUST add only what is missing, keep every folder, setting and
  recommendation the person wrote, never touch another workspace file, and leave
  a file it cannot read as JSON alone, saying so. The `workspace-file` help page
  and a chapter of the guide MUST teach the default, how to make one's own, how
  to open a file from a terminal and from VS Code, how to add a repository and
  what to do when only one repository shows.

## Out of scope- The Workspaces Console's own behavior: 0043-if-console in the public root.
- Repo-shipped kits and MCP.
- Editors other than VS Code.

## Edge cases

- The public root is not trusted: nothing of it runs, and the trust is offered as
  a decision, per FR-021.
- The public root is not cloned: the step says to copy it first, per FR-021.
- The public root has published a release with the package and its digest: it is
  installed without a build or trust, per FR-026.
- The release's download does not match its digest: plain words, and the build
  is tried after trust, per FR-026.
- The build fails: plain words, the end of its output, nothing installed, per
  FR-021.
- The public root has not moved since the last build: it is not built again, per
  FR-021.
- The older extension is installed: it is removed, per FR-022.
- The workspace file has the person's own folders and settings: they are kept,
  per FR-023.
- The workspace file has comments: it is left alone, per FR-023.
- VS Code is not reachable from the terminal: the step says to open it once with
  `code .` and run this again, per FR-021.

## Assumptions

- VS Code 1.85 or later, with the extension host in the same machine or WSL
  distribution as the repositories.
- The public root builds its extension with `python3` and `uv` alone
  (0043-if-console FR-027).

## Open questions

- **OQ-1**: Answered by FR-026.

## Key entities

- **The Workspaces Console** — the public root's one extension, built and installed by
  `vscode ensure`.
- **The workspace file** — `workspaces.code-workspace`, the repositories a person
  works in, as one VS Code window.

## Success criteria

- **SC-001**: A person runs `ws-host vscode ensure`, trusts the public root once,
  opens the workspace file, and sees what needs them and the commands of every
  repository in VS Code.
- **SC-002**: No code of the public root runs before the person trusts it.

## Review & acceptance checklist

- [x] Every requirement is testable (MUST / MUST NOT), not aspirational
- [x] No company fact is asserted here
- [x] Every open item is marked, not silently decided
- [x] Public-safe: no confidential information, no unverified number stated
      as settled fact
