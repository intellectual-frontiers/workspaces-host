# Feature Specification: Providers and the toolchain

**Spec ID:** 0008-providers
**Status:** Draft

**Input:** A provider is a repository that declares what it needs in a `.workspaces-host/` folder of small TOML files and ships a
launcher that speaks the command-line protocol (0041-command-line). `ws-host` is the one owner of installing, finding and pruning the
programs providers pin: it reads the declarations as data, translates them into a pinned `mise` configuration, and runs `mise` with
nothing that can execute. A provider's programs are reached only through that provider's own environment, so two providers may pin
different versions of one program without conflict. Nothing here installs a program onto a person's PATH.

## Declarations

- **FR-001**: A provider MUST declare itself in `.workspaces-host/provider.toml` at its root: `name` (letters, digits and hyphens),
  `summary` (one sentence), `launcher` (an executable file at the root, named `./<file>`) and `protocol` (the integer `1`). Keys not
  named here MUST be ignored. Reading declarations MUST run no code of the provider.
- **FR-002**: A provider MAY declare what it needs in `.workspaces-host/toolchain.d/<name>.toml`, one entry per file, the file's
  stem being the entry's `name`. An entry MUST have an exact `version` (digits and dots, no range and no floating tag), a `summary`
  and a `kind`: `archive` (a downloaded file), `npm` (a package of the npm registry) or `tool` (a tool of `mise`'s own registry).
- **FR-003**: An `archive` entry MUST give, for the platform `linux-x64` and optionally `linux-arm64`, an `https` `url` and a 64-digit
  `sha256`. It MAY give `strip` (leading path parts removed on unpacking, default 1), `bin` (the folder, relative to the unpacked
  root, whose programs are put first on PATH by `provider run`; none when absent; also allowed in a platform's table, which wins), `provides` (a program and its path under the root), `env`
  (variables whose values may use `{dir}` for the unpacked root), `needs` (names of other entries of the same provider, without a
  cycle) and `system` (shared libraries the program links, as package names for the distribution, `a|b` meaning the first the
  distribution has).
- **FR-004**: An `npm` entry MUST give `package`, and a `tool` entry `tool`; both give the exact `version`. Neither runs an install
  script or any command of its own.
- **FR-005**: `ws-host` MUST reject, naming the file and the key: a missing required key; a version that is a range or a floating
  tag; a URL that is not `https`; a checksum that is not 64 hex digits; an entry whose `needs` names an entry that is not in the same
  provider or forms a cycle; a name different from the file's stem; and a provider whose launcher is not an executable file at its root.

## Translation and the store

- **FR-006**: `toolchain generate PROVIDER` (a `generate` command) MUST write the provider's translation into `.workspaces-host/mise/`:
  one `mise` configuration file per entry in `.config/mise/conf.d/`, and the `mise.lock` and dependency sidecars `mise` writes beside
  them, each generated file starting with a line that says it is generated and by which command. `fresh` MUST prove they are current.
- **FR-007**: Every install MUST use only that translation, with `mise install --locked`, in `MISE_SAFE=1` mode, from a configuration
  and data directory that are `ws-host`'s own, never a person's or a repository's. One store, `~/.local/share/workspaces-host/mise`,
  holds every provider's programs.
- **FR-008**: `ws-host` MUST fetch the `mise` it uses itself, at one exact version and SHA-256 per architecture written in its code,
  verified before anything is unpacked, and MUST NOT use a `mise` found on PATH unless the person names it in `WS_HOST_MISE`. Offline,
  a `mise` that is not already here MUST end the command with exit status 3 naming it.
- **FR-009**: Two enabled providers MUST NOT declare one entry name and version with different URLs, checksums or packages. The `providers` check section
  and `provider add` MUST fail naming both providers when they do, because the store identifies a program by its name and version.

## Providers and trust

- **FR-010**: A provider is in use when a person enabled it with `provider add PATH` (a `decision`: it links the provider's `.workspaces-host/` folder
  into `~/.config/workspaces-host/providers.d/<name>`; `provider remove NAME` removes it), or when it needs no enabling: the clone of `ws-host` that is
  running, which is the code the person installed, and every cloned repository the person trusts (0002-repositories-and-trust FR-012), which until their
  own configuration says otherwise includes the organization `ws-host` itself comes from. A repository MUST NOT be able to enable itself. `provider list`
  MUST say why each is in use. Only a provider in use has its declarations installed or run.
- **FR-011**: `provider list` and `provider show NAME` (read) MUST say, in plain words, each enabled provider, its launcher, its
  entries with their versions, and whether each is installed.

## Using a provider's programs

- **FR-012**: `toolchain ensure NAME` (setup) MUST install one entry and the entries it needs, or every entry of a provider with
  `--all`; `toolchain show NAME` and `toolchain list` (read) MUST return, as a resource, each entry's version, state,
  installed path, the environment it sets and the programs it provides, so that a provider's own command line can find what it pinned.
- **FR-013**: `provider run PROVIDER -- COMMAND...` MUST run the command with that provider's environment: its entries' folders first on
  `PATH` and their `env` set; a variable several entries set holds each value in entry-name order joined by a colon. `provider show` MUST return that environment, as the PATH pieces and variables it adds, so a provider's own command line can run its programs itself.
  No pinned program MUST be put on a person's PATH. A stop asked for at the terminal while the command runs (Ctrl+C, SIGINT)
  reaches the command itself, which is the one to answer it: `provider run` MUST wait for the command to end and MUST end with
  the command's status (128 plus the signal's number when a signal ended it), printing nothing of its own and never a traceback.
- **FR-014**: Environment variables that change what a program's output is, such as those of TeX, Node and Playwright, MUST be left
  to the provider to remove from the programs it starts; `ws-host` MUST pass through only the variables `mise` needs and the person's own.
- **FR-015**: `toolchain remove --unused` MUST remove stored programs that no enabled provider's lock names, and with `--dry-run` MUST say what it
  would remove and write nothing.
- **FR-016**: `system ensure` (setup) MUST install, with the distribution's package manager after saying that it needs administrator
  rights, the shared libraries the enabled providers' entries declare in `system`, and MUST say what it did not install.

## Reporting

- **FR-017**: `doctor` MUST report each enabled provider and each entry's state, and MUST report Homebrew and direnv, where present, as
  suggestions for a person's own use and never as problems; `ws-host` MUST never install, configure or update either.

## Out of scope

- Programs a person installs for themselves: Homebrew and direnv are their own choices.
- A provider that wants a program on a person's PATH: it says so in its own documentation.

## Edge cases

- An entry file whose name differs from its `name`: rejected, per FR-005.
- Two providers pin `chromium` at one version with the same URL and checksum: one copy in the store, per FR-007 and FR-009.
- A provider's generated translation is older than its entries: `fresh` fails and `toolchain generate` rewrites it, per FR-006.
- A person's own `mise` configuration in a repository: never read, per FR-007.

## Assumptions

- The platform is Linux on x86_64 or aarch64; other systems run it inside WSL, a virtual machine or a container.

## Open questions

- **OQ-1**: Whether a provider may name a program for the person's PATH through a reviewed list in the person's own configuration.

## Key entities

- **A provider** — a repository with `.workspaces-host/provider.toml` and a launcher.
- **An entry** — one pinned program or package, one file.
- **The translation** — the generated `mise` configuration and lock in `.workspaces-host/mise/`.
- **The store** — `~/.local/share/workspaces-host/mise`, shared by every provider.

## Success criteria

- **SC-001**: A provider with an archive entry, enabled, has its program installed by `toolchain ensure` and run by `provider run`, from the lock only.
- **SC-002**: A tampered archive installs nothing.

## Review & acceptance checklist

- [x] Every requirement is testable (MUST / MUST NOT), not aspirational
- [x] No company fact is asserted here
- [x] Every open item is marked, not silently decided
- [x] Public-safe: no confidential information, no unverified number stated as settled fact
