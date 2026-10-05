# Feature Specification: Repositories, sign-in and trust

**Spec ID:** 0002-repositories-and-trust
**Status:** Draft

**Input:** How `ws-host` finds, clones and updates a person's repositories,
signs them in, and decides whose code may run. The `repo`, `auth` and
`workspace` nouns follow 0041-command-line FR-063 and 0026-workspaces FR-015
to FR-024, which govern them. The rules guard against two
failures that cost people work: a reattach that rebases someone's unpushed
work, and a failed clone reported as done. Each is a test here.

## Where repositories live and where they are listed

- **FR-001**: A repository MUST be identified as `<host>/<org>/<repo>` (for
  example `github.com/acme/site`) and live at
  `<workspaces folder>/<host>/<org>/<repo>`, the workspaces folder being
  `WS_HOST_WORKSPACES` or `~/workspaces`. A command that takes a repository
  MUST also accept `<org>/<repo>` or `<repo>` when exactly one known
  repository matches, and MUST say which matched.
- **FR-002**: The repositories `ws-host` knows MUST be those the person lists in
  `WS_HOST_REPOS` of their own configuration, and those listed in
  `WS_HOST_REPOS` of the `.workspaces-host/ws-host.env` of any listed repository
  that is cloned, to any depth. Reading such a file is reading information
  and MUST need no trust (0041-command-line FR-062). A list entry is
  `<host>/<org>/<repo>`; an entry that is not MUST be reported and ignored.
- **FR-003**: `repo list` MUST list every known repository with its place, whether
  it is cloned, whether it is trusted and why, and what named it. `repo status
  [ID]` MUST report for each cloned repository its branch, its upstream, how
  many commits it is ahead and behind that upstream as last fetched, and
  whether it has changes not yet committed to files Git tracks. Both are `read`
  commands and change nothing.

## Cloning

- **FR-004**: `repo add [ID|--all]` MUST clone each known repository that is
  missing, into its place (FR-001), and MUST NOT trust any (FR-012). With `--all`
  or no ID it clones every missing known repository. A clone MUST run without
  prompting (`GIT_TERMINAL_PROMPT=0`).
- **FR-005**: A clone or fetch that fails MUST be reported as failed, never as
  done, with git's own message as its reason and, where the reason is that
  the person is not signed in, the one action that signs in
  (`ws-host auth new github` for a GitHub host). A failure in one repository
  MUST NOT stop the others. The command MUST exit 1 when any clone or fetch
  failed.
- **FR-006**: A repository that is named only by a cloned repository's
  environment file MUST be cloned by `repo add --all` and MUST NOT be trusted by
  that (FR-013).

## Updating without harm

- **FR-007**: `repo sync [ID|--all]` MUST update a cloned repository only by
  `git fetch` followed by `git merge --ff-only` of its upstream. It MUST NOT
  run `git pull`, a rebase, a merge that is not a fast-forward, a stash, a
  reset or a checkout.
- **FR-008**: `repo sync` MUST leave a repository exactly as it was, and
  report it as skipped in plain words, when: it has changes not yet committed
  to files Git tracks; its commits and its upstream's have diverged; it has no
  upstream; it is on no branch; or a rebase, merge or other operation is in
  progress in it. "Exactly as it was" means its `HEAD`, its index, its
  working tree and its branch are unchanged, and no rebase, merge or stash
  exists that did not before. A skip MUST NOT make the command fail: it exits
  0 and the resource lists each skip with its reason.
- **FR-009**: The reason of a skip MUST be plain language that says the
  person's work is safe, names the repository, and says why it was not
  updated, in the form "your changes in X are safe; it was not updated
  because ...". A repository with commits not yet pushed and nothing new
  upstream MUST be reported as up to date, with a note that it holds work not
  yet pushed.
- **FR-010**: `repo sync` MUST say what it did for each repository: updated
  (with how many commits), already up to date, skipped, or failed.

## Sign-in

- **FR-011**: `auth status` MUST report, for GitHub and for each host in
  `WS_HOST_GITLAB_HOSTS`, whether the person is signed in, by asking `gh` and
  `glab`, and MUST change nothing. `auth new github` and `auth new gitlab`
  MUST sign the person in with the device-flow login of `gh` or `glab`
  (setting `gh` up as git's credential helper for GitHub), MUST be the only
  commands that are interactive, and MUST offer the one-time code and its
  address as a resource in a stream, so that an editor can show them
  (0041-command-line FR-019, FR-050). A missing `gh` or `glab` MUST be an error
  with exit 3 whose action installs the `base` kit.

## Trust

- **FR-012**: A repository is trusted when a link for it exists in the
  person's `enabled/` directory, or when its organization is named in
  `WS_HOST_TRUSTED` of the person's own configuration (0026-workspaces
  FR-014). The link, named for the repository, MUST point, relatively where
  both lie in the person's home, to the repository's `.workspaces-host`
  directory (0026-workspaces FR-023). Nothing but the person's own act,
  `repo add --trust` or `repo set ID --trusted`, MUST create it.
- **FR-013**: Trust MUST NOT be transitive, and no repository's file can grant
  it. `WS_HOST_TRUSTED` in a repository's file MUST be ignored and `doctor`
  MUST say so.
- **FR-014**: `repo add --trust` MUST list exactly the repositories it trusts, in
  its `--dry-run` and in its result, and MUST trust only repositories the
  person's own configuration lists or the person names, never those only
  another repository's file names. `repo set ID --trusted` and `--untrusted`
  MUST be a `decision` command (0041-command-line FR-014, FR-023): it MUST
  NOT be exposed over MCP, and it MUST need a confirmation only a person can
  give: in the terminal an answer typed at a prompt that needs a terminal,
  and in the editor the extension's modal confirmation
  (0041-command-line FR-051).
- **FR-015**: When trust is granted `ws-host` MUST record the repository's
  commit in its state directory, and `doctor` MUST warn, without failing,
  when the repository's `.workspaces-host/kits/` has changed since.

## The one command

- **FR-016**: `workspace ensure` MUST, in order: report whether the person is
  signed in; clone the missing known repositories (FR-004); fast-forward the
  rest (FR-007); install the kits the repositories declare, as 0003-kits
  states; and run `doctor`. It MUST be safe to run as often as the person
  likes, MUST continue past a failure and report every one, and MUST take
  `--dry-run`, which fetches and installs nothing and lists what it would do.
  `workspace status` MUST report the same facts without changing anything.
- **FR-017**: `workspace set --pull-ff-only` MUST set git's `pull.ff` to
  `only` for the person, and `doctor` MUST recommend it, with that command as
  an action the editor can offer, whenever it is not set. Nothing MUST apply
  it unasked, and nothing else MUST change the person's git or editor
  configuration.
- **FR-018**: `ws-host` MUST write nothing into a clone's working tree, MUST
  NOT edit a clone's ignore rules or `.vscode/`, and MUST NOT commit or push.

## Out of scope

- Kits and installers: 0003-kits.
- The extension's sign-in notification: 0004-editor-extension.
- Hosts other than GitHub and GitLab.

## Edge cases

- Unpushed commits that conflict with new upstream commits: `repo sync`
  leaves the repository exactly as it was and says its work is safe, per
  FR-007 to FR-009.
- A repository with a changed tracked file and new upstream commits: skipped,
  per FR-008.
- A repository with only untracked files: it is updated, since they are not
  changes to tracked files and a fast-forward cannot overwrite them without
  Git refusing, per FR-007 and FR-008.
- A fast-forward that Git refuses because an untracked file is in the way: the
  repository is reported as skipped with Git's reason, per FR-008.
- A repository whose branch has no upstream: skipped, per FR-008.
- A repository mid-rebase: skipped and untouched, per FR-008.
- A private repository with no sign-in: the clone fails at once with Git's
  "could not read Username" and the `auth new` action, per FR-005.
- One of three repositories fails to clone: the other two are cloned and the
  exit is 1, per FR-005.
- A repository listed by a trusted repository: cloned, not trusted, per
  FR-006 and FR-013.
- A repository's file names its own organization as trusted: ignored, per
  FR-013.
- An AI agent runs `repo set` over MCP: not offered and refused, per FR-014.
- A repository's kits change after it was trusted: `doctor` warns, per FR-015.
- A list entry that is not `<host>/<org>/<repo>`: reported and ignored, per
  FR-002.
- Two known repositories named alike: a short name that matches both is
  refused and the full identifiers are offered, per FR-001.
- `workspace ensure` run twice: the second run changes nothing, per FR-016.
- `pull.ff` unset: `doctor` recommends and offers the fix, per FR-017.

## Assumptions

- The person's repositories are on GitHub or on GitLab hosts they name.
- `git` is installed (the `base` kit installs it) and `gh` or `glab` is
  installed to sign in.

## Open questions

- **OQ-1**: Whether an update should also be skipped when a fast-forward
  would change a file that is open and unsaved in the person's editor.

## Key entities

- **A known repository** — one the person's configuration or a cloned
  repository's file lists.
- **A skip** — a repository deliberately left exactly as it was, with a plain
  reason; never a failure.
- **A trust link** — the link in `enabled/` that records, and is, the trust of a
  repository.

## Success criteria

- **SC-001**: Unpushed work that conflicts with upstream survives `repo
  sync`: its `HEAD` and `git status` are unchanged and no rebase, merge or
  stash exists.
- **SC-002**: A failed clone is never reported as done.
- **SC-003**: Trust is never created by cloning, by listing, or by a
  repository's own file.

## Review & acceptance checklist

- [x] Every requirement is testable (MUST / MUST NOT), not aspirational
- [x] No company fact is asserted here
- [x] Every open item is marked, not silently decided
- [x] Public-safe: no confidential information, no unverified number stated
      as settled fact
