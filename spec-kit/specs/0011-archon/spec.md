# Feature Specification: archon, the command runner

**Spec ID:** 0011-archon
**Status:** Draft

**Input:** `archon` is the Python command runner that every command line of Intellectual Frontiers runs on: `agora`, the command lines of the repositories that use it, and `ws-host`. A
person or an AI agent who has Python's package runner `uv` on a computer, and nothing else, runs `archon`, and `archon` makes whatever a
command needs exist before the command runs: the interpreter, the command's Python packages, and the programs outside Python. Nobody is
asked to install a tool, and nobody wonders whether one is there. `ws-host` is the interactive experience for a person (a friendly command
line, the editor window, setting up a Linux machine) and is built on `archon`; `agora` and the other command lines are command trees that `archon` runs.
`archon` assumes no person is present unless something says one is.

## What archon is

- **FR-001**: `archon` MUST be the Python package `archon/` of this repository, written with the standard library alone, and MUST run on a
  computer that has `uv` and nothing else of its own: `uvx --from git+https://github.com/intellectual-frontiers/workspaces-host@REVISION
  archon ...` from anywhere, or `python -m archon ...` from a clone. `uv` obtains the Python. A command line that uses `archon` MUST pin the
  revision it uses, and MAY name another source in `ARCHON_FROM` (a clone's path, for development and tests).
- **FR-002**: `archon run [--repo DIR] [--path DIR]... -- MODULE [ARGUMENT...]` MUST run `python -m MODULE ARGUMENT...` under the newest
  Python that `requires-python` in the repository's `pyproject.toml` allows, with each `--path` (relative to the repository) and `archon`
  itself importable, and MUST end with the command's own status. Every word after `--` belongs to the command.
- **FR-003**: `archon` MUST NOT write anything into the repository it runs for, into an interpreter it did not create, or onto a person's
  `PATH`. What it creates lives in the user's cache and data folders, which `ws-host` shares (0008-providers FR-007).
- **FR-004**: `archon ensure [--repo DIR] NAME...` MUST make the named requirements available (FR-011) and return, for each, where it came
  from (FR-013), the programs it provides and the environment it adds; with `--json` the answer is JSON. `archon doctor` MUST say, in plain
  words, the profile (FR-005), the package managers it found and what each requirement of the repository would be obtained from, changing
  nothing.

## The profile

- **FR-005**: `archon` MUST decide, once per invocation, whether a person is at the invocation (`attended`) or not (`unattended`), and MUST
  assume `unattended`. It is `attended` only when, in this order: `ARCHON_ATTENDANCE` says `attended` (or `unattended`, which ends the
  search); the invocation surface is an editor (the Workspaces Console sets `ARCHON_ATTENDANCE=attended`); or neither `CI` nor
  `CLAUDE_CODE_REMOTE` is set to `1` or `true` and both standard input and standard error are terminals. A pipe alone never makes an
  invocation attended, and nothing about the computer (`ws-host` present or not) enters the decision.
- **FR-006**: An unattended invocation MUST NOT prompt or ask for confirmation, MUST draw no spinner and write no colour or cursor
  control, and MUST take the yes-answer to every question that is `archon`'s own, including installing a requirement (FR-011); it MUST still
  refuse what no one has authorised, such as a program whose checksum differs. It MAY say what it is doing, as plain lines on standard
  error, because showing progress nobody reads does no harm. An attended invocation MUST say, before an install that needs administrator
  rights, what will be installed and that `sudo` will ask for the password; a person who declines moves the requirement to its next
  source (FR-011).
- **FR-021**: For an attended person, progress is a main feature, not an afterthought. At a terminal, a step that takes a while MUST show
  a spinner with the seconds, what has come so far (megabytes of a download, packages of an install) and an emoji that says what kind of
  step it is, in colour unless `NO_COLOR` is set (0006-onboarding FR-020); a step that took a while MUST leave one line behind saying that it
  finished or failed. Wherever there is no terminal to draw on but a person is looking (the editor window, a web page), `archon` MUST
  publish the same progress as events: with `ARCHON_PROGRESS=events` it writes one JSON object per line to standard error, each naming the
  step, its state (`start`, `update`, `done`, `failed`), its label, its emoji, the amount done and the total when known, and the
  surface draws them. The same steps feed every rendering, so a person sees the same story in a terminal, in the editor and on the web.
- **FR-007**: `archon` MUST set `ARCHON_ATTENDANCE` to the decision in the environment of everything it starts, so that a command and the
  commands it starts agree, and MUST report the decision and the rule that made it.

## Requirements and where they come from

- **FR-008**: A requirement is an entry of `.workspaces-host/toolchain.d/<name>.toml` in the repository (0008-providers FR-002). It MAY also
  give `minimum` (a version of digits and dots), `probe` (`program`, the name of the program to ask, and `args`, default `["--version"]`;
  the version is the first version-looking word the program prints) and `packages` (a table whose keys are package managers, `apt`, `dnf`,
  `apk` and `brew`, and whose values are lists of package names, `a|b` meaning the first the manager has). An entry that gives `minimum`
  and `probe` MAY be satisfied by the computer (FR-011); an entry that does not is satisfied only by its pinned download.
- **FR-009**: A command line MUST name its requirements in its own manifest, and `archon` MUST make them available before the command runs,
  without a flag and without being asked. Requirements an entry `needs` (0008-providers FR-003) MUST be made available first, each by the
  same rules.
- **FR-010**: Versions MUST be compared as dot-separated whole numbers, a missing part counting as 0; what a distribution adds to a version
  (an epoch such as `2:`, a revision such as `-1~deb12u1`, a suffix such as `+dfsg`) MUST be ignored.
- **FR-011**: `archon` MUST obtain a requirement from the first of these sources that yields a program meeting `minimum`, in this order:
  1. `path`: a program on `PATH` whose probe meets `minimum`;
  2. `installed`: a copy of the entry already in the store (its own download or its `mise` tool, of any version) whose version meets
     `minimum`, the newest if several do, reported as `pinned`. A second copy of a tool MUST NOT be installed while one that
     meets `minimum` is in the store (FR-024);
  3. `system`: the computer's package manager, when it offers a version meeting `minimum`, installed non-interactively, and used only when a
     probe of the installed program then meets `minimum`. `archon` MUST use administrator rights only as root or through `sudo` (without a
     password when unattended); when it cannot, the source is skipped, not failed;
  4. `pinned`: the entry's own download, whose SHA-256 is checked before anything is unpacked (0003-kits FR-006; 0008-providers FR-007), or
     the `mise` tool or npm package the entry names, installed from the lock.
  An entry without `minimum` and `probe` has only the pinned source, of the version its lock names.
- **FR-012**: A program found by the first or second source MUST be used as it is: the entry's `env` and `bin` (0008-providers FR-003) MUST
  NOT be applied to it, since they describe the pinned copy. The pinned copy MUST be put first on `PATH` only for what `archon` starts, and
  nothing MUST be put on a person's `PATH` (FR-003).
- **FR-013**: For each requirement `archon` MUST report the source that yielded it (`path`, `system` or `pinned`), the version found, the
  path of each program it provides and the environment it adds (`PATH` and the entry's `env`).
- **FR-014**: A requirement already met MUST be met again without network and without a prompt: `PATH`, an installed package and an
  installed pinned copy all work offline. Offline (`--offline` or `ARCHON_OFFLINE=1`), a source that needs the network MUST be skipped.
- **FR-015**: When no source yields the requirement, `archon` MUST end with exit status 3 and say, for the requirement, its minimum and each
  source, why that source did not yield it (not on `PATH`, no package manager, the manager offers 18.2 and 22 is needed, no administrator
  rights, offline, no build for this platform). It MUST NOT start the command.
- **FR-016**: What `archon` installs MUST be verified: a pinned download by its SHA-256, a package by the package manager's own signature
  check, and a program from `PATH` by its probe. `archon` MUST NOT run a download's own installer script, and MUST NOT install a program
  that no entry names.

- **FR-022**: When an entry lists shared libraries in `system` (a Chromium build links against them), `archon` MUST install the ones the
  computer lacks through its package manager, as root or through `sudo` (FR-011), as part of making the entry available, and MUST end with
  exit status 3 naming the packages when it cannot. `ws-host system ensure` MUST do the same ahead of time for a person, saying first what it
  will run.

## Python environments

- **FR-017**: `archon` MUST prepare the Python environment of a set of dependency groups of the repository's `pyproject.toml`
  (0025-tooling-environment FR-013) with `uv sync --frozen --only-group`, from the repository's `uv.lock`, into one environment per set of
  groups and lock inside the user's cache, and MUST NOT resolve, upgrade or install anything the lock does not hold. Offline, packages
  not already in `uv`'s cache MUST end the command with exit status 3 naming them.
- **FR-018**: A command line that runs on `archon` (`agora` and the others) MUST get its profile, its environments and its programs from `archon`'s
  functions, and MUST NOT keep its own rules for them; the only thing it keeps is which groups and requirements each command names.

## Relation to ws-host

- **FR-019**: `ws-host` MUST do every install, probe and profile decision it makes through `archon`, and MUST add only what a person
  sees and chooses: the friendly command line, the editor window, the setting up of a Linux machine and of a person's repositories. A
  repository does not have to be enabled as a provider (0008-providers FR-010) for `archon` to make its own requirements available: running
  a repository's command line already trusts that repository's code.
- **FR-023**: `ws-host` MUST make the `uv` and `uvx` of its own runtime available to a person's repositories: on every run it links them
  into `~/.local/bin`, which a Debian or Ubuntu login puts on `PATH`, and it MUST NOT replace a `uv` or `uvx` it did not link. A launcher
  that finds no `uv` on `PATH` looks there and in `ws-host`'s store of installed tools before it says `uv` is missing (0041-command-line FR-001, `.github`).
- **FR-024**: A computer MUST hold one copy of a tool. `ws-host` and `archon` share one store, so a tool and version two repositories declare is
  installed once (0008-providers FR-009), and a tool that a `ws-host` kit also provides MUST be the kit's one copy of it: the `rust` kit makes the
  `cargo` requirement available through `archon` and links its programs into `~/.local/bin` as small scripts that set the entry's `env`
  (0003-kits FR-010), instead of installing Rust again.
- **FR-025**: The versions of Python and `uv` in `archon/bootstrap.env` MUST equal the `python` and `uv` entries `ws-host` declares, and every
  entry of one name that two repositories declare MUST be the same declaration (0008-providers FR-009), so a version changes in every
  repository together.
- **FR-020**: A computer that has `ws-host` and one that has only `uv` MUST produce the same results from the same command: `ws-host`
  changes how a person is helped, never what a command does.

## Edge cases

- A requirement's `minimum` is met by `PATH` but the probe prints nothing version-like: the source does not yield, per FR-011, and the next is tried.
- The package manager offers the version but `sudo` needs a password and the invocation is unattended: the source is skipped, per FR-011.
- A computer with no package manager (a minimal container) and no `PATH` program: the pinned download is used, per FR-011.
- A download's checksum differs: nothing is installed, and the requirement fails with exit status 3, per FR-016.
- Two repositories pin different versions of one requirement: each gets its own pinned copy in the shared store, per 0008-providers FR-007.

## Assumptions

- The platform is Linux on x86_64 or aarch64 (0008-providers). `uv` is the one prerequisite.
- A computer can reach `github.com` and the package index once, to fetch `archon` and the interpreter; after that it runs from caches.

## Open questions

- **OQ-1**: Whether `archon` should support package managers beyond `apt`, `dnf`, `apk` and `brew`.

## Key entities

- **A requirement** — a program outside Python that a command needs, declared as an entry.
- **A source** — where a requirement comes from: `path`, `system` or `pinned`.
- **The profile** — attended or unattended, and the rule that decided it.

## Success criteria

- **SC-001**: On a computer with only `uv`, `archon run -- agora check` runs, installing what the commands it runs name.
- **SC-002**: A requirement a package manager can supply at its minimum is supplied by it; one it cannot is downloaded and verified.
- **SC-003**: No invocation without a terminal ever waits for an answer.

## Review & acceptance checklist

- [x] Every requirement is testable (MUST / MUST NOT), not aspirational
- [x] No company fact is asserted here
- [x] Every open item is marked, not silently decided
- [x] Public-safe: no confidential information, no unverified number stated as settled fact
