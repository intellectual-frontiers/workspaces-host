# Feature Specification: Releases

**Spec ID:** 0007-releases
**Status:** Draft

**Input:** How `workspaces-host` ships. One version names one release, which is four files on GitHub Releases: the program and its
library as one tarball, the same code as a Python wheel, the Workspaces Console as a VS Code package, and a file of checksums. A
release is built on a maintainer's machine from pinned tools, is byte-for-byte reproducible so that anyone can rebuild it and compare,
and is published by a person with their own `gh` sign-in. A consumer pins a file by its address and its SHA-256 (0025-tooling-environment
FR-015 to FR-018, in the public root), never by a tag. No continuous-integration service takes part.

## The release

- **FR-001**: One version MUST name a release. It MUST be written once, as `VERSION` in `ws_host/__init__.py`, which `pyproject.toml`
  reads and does not restate; the Workspaces Console's `package.json` MUST say the same version and the name `workspaces-console`;
  the tag MUST be `v<version>`.
- **FR-002**: A release MUST consist of exactly these files, named by the version: `ws-host-<version>.tar.gz`,
  `ws_host-<version>-py3-none-any.whl`, `workspaces-console-<version>.vsix` and `SHA256SUMS`.
- **FR-003**: The tarball MUST hold the wheel's `ws_host/` files unchanged under `lib/`, and a launcher at `bin/ws-host` in Python
  that needs only `python3` (3.11 or later) and runs the library beside it, also through a symbolic link. It MUST hold nothing else,
  so that unpacking it is installing it. The wheel MUST name no dependency.
- **FR-004**: Building a release twice from one commit MUST give byte-identical files: every file in a tarball, wheel or package has the
  time 2020-02-02T00:00:00Z, entries are in a fixed order, a tarball records no owner and a gzip stream no name or time, and a package
  is rewritten with those attributes after `vsce` writes it.
- **FR-005**: A release MUST be built only with what is pinned: `python`, `uv` and `node` at exact versions in `.config/mise/` with
  a checksum for each in `mise.lock` for `linux-x64` and `linux-arm64`; the build backend at an exact version in `pyproject.toml`;
  and the Console's packages from `console/package-lock.json`, every one with an integrity hash, installed with `npm ci`.
- **FR-006**: Before the Console is packed, its build MUST type-check both of its projects in strict mode, lint with no warning, and
  pass every unit test; a failure of any step MUST stop the release with that step's last lines.
- **FR-007**: `SHA256SUMS` MUST list the tarball, the wheel and the package in `sha256sum` format, one line each.

## The commands

- **FR-008**: `release build` (a `build` command) MUST write the release into one directory, `dist/` unless `--output` names another,
  emptied first, and the Console's build outputs under `console/`; with `--dry-run` it MUST write nothing and name the files it would
  make. It MUST refuse to build when the versions of FR-001 differ.
- **FR-009**: Two sections of `check`, named and never part of a plain `check` (0041-command-line FR-010), MUST judge a built release:
  `release` MUST say, as findings in plain words, that the one version is the same everywhere; that every file is there; that the
  checksums match; that the wheel names this version and no dependency; that the package holds what it runs (`dist/extension.js`,
  `dist/webview.js`, its icon and translation bundle) and no source, test, source map, `node_modules` or lock; and that the tarball runs
  where it is unpacked and finds its commands. `reproducible` MUST build the release again and say which file's bytes differ. A
  checksum that differs MUST end `release` there. Both read `dist/` unless `WS_HOST_RELEASE_DIR` names another folder, and are skipped,
  naming the cause, where there is no built release.
- **FR-010**: `release publish` MUST be a `decision`: never over MCP, and confirmed by a person at a terminal or in the editor's modal.
  It MUST refuse, saying why, unless the working tree is clean, the commit is on a remote branch, the tag does not exist, and the release
  passes `check release`. It MUST create the tag and the GitHub release with the person's own `gh` sign-in, MUST take no token as an
  argument and keep no credential, and with `--dry-run` MUST upload nothing and show the files and the notes.
- **FR-011**: The release's notes MUST give each file's purpose and SHA-256, and the exact mise entry that pins the tarball: its
  `https` address and its checksum, for `linux-x64` and `linux-arm64`.
- **FR-012**: Making and publishing a release MUST need only a maintainer's machine with the pinned toolchain and `gh` signed in. No
  workflow of a hosted service MUST be required to build, check or publish it.

## Installing the Console

- **FR-013**: `vscode ensure` MUST put the Workspaces Console in VS Code from the source in the clone `ws-host` runs from, so that everyone who
  installed `ws-host` has it with no release to wait for: it MUST build it with `ws-host`'s own Node (an entry of `ws-host`'s own provider
  declarations, installed from its lock), from the Console's own npm lock, install the package with `code`, and rebuild only when the Console's
  source has changed. Only a `ws-host` that has no copy of that source (an installed wheel) MUST take the latest release instead: it MUST use only
  an asset named `workspaces-console-<version>.vsix` with an `https` address and a SHA-256 digest, MUST check the digest before anything uses the
  file, MUST install a given release once, and MUST say in plain words when there is no usable release or the file does not match its digest,
  installing nothing. Publishing a release (FR-010) is for people who do not run `ws-host` from a clone.

## Out of scope

- A package index. A release is on GitHub Releases only.
- Signing beyond the checksums. Integrity is the consumer's pin plus a reproducible build anyone can repeat.
- The prompt, shell and editor configuration ws-host applies, and how a person's machine comes to run a release (their own specs).

## Edge cases

- The Console's version and `ws_host/__init__.py` differ: the build stops before anything is made, per FR-008.
- A rebuild differs from the published files: `check reproducible` fails naming the file, per FR-009.
- `gh` is not signed in or not installed: `release publish` says so and does nothing, per FR-010.
- A release exists on GitHub without a digest on the package: `vscode ensure` ignores it, per FR-013 (and a clone does not use a release at all).

## Assumptions

- The maintainer's machine is Linux with the repository's `mise` toolchain installed with `mise install --locked`.
- GitHub reports a SHA-256 digest for release assets.

## Open questions

- **OQ-1**: How a person's installed `ws-host` moves to a newer release (the tarball is pinned by address and checksum, so the move is a
  change of that pin); 0001-ws-host's `update` still describes updating a clone.
- **OQ-2**: Whether a published release should also carry a signature or an attestation, beyond the reproducible build and the checksums.

## Key entities

- **A release** — the four files of FR-002 for one version.
- **The app tarball** — `bin/ws-host` and `lib/ws_host/`, run in place.
- **A pin** — a file's address and SHA-256 together.

## Success criteria

- **SC-001**: `release build`, then `check release` and `check reproducible`, pass on a clean clone with only `mise install --locked` done.
- **SC-002**: A tampered file fails `check release` at the checksums.

## Review & acceptance checklist

- [x] Every requirement is testable (MUST / MUST NOT), not aspirational
- [x] No company fact is asserted here
- [x] Every open item is marked, not silently decided
- [x] Public-safe: no confidential information, no unverified number stated as settled fact
