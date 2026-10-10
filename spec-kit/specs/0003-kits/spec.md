# Feature Specification: Kits and installers

**Spec ID:** 0003-kits
**Status:** Draft

**Input:** The kits `ws-host` ships (`base`, `press`, `rust` and `shell`), the two
installers that put them on a machine (the distribution's package manager, and
a verified download), and the `kit` commands. A kit is what
0041-command-line FR-058 to FR-062 define: a Python module declaring its
packages, its downloads and its checks. Simplicity is chosen over determinism:
a kit installs what the distribution ships, so two machines may differ, and
`doctor` makes the difference visible.

## The kit commands

- **FR-001**: `kit list` (read) MUST list every kit with one plain sentence for
  a person, whether it is installed, and the programs it provides. `kit show
  KIT` (read) MUST show what installing it would do on this machine: the
  packages, which of them this distribution has and which it lacks, each
  download with its version, address and checksum for this architecture, and
  its checks. `kit add KIT` (setup) MUST install a kit, with `--dry-run`.
- **FR-002**: `kit add` MUST say, before it runs anything that needs
  administrator rights, that it will use `sudo` and which packages it will
  install, MUST NOT be exposed over MCP, and MUST NOT run `sudo` where it
  cannot ask for a password: without a terminal it uses `sudo -n` and, when
  that is refused, says in plain words what to run in a terminal. A person
  without `sudo` MUST still get every download the kit declares, and be told
  what was left.
- **FR-003**: A kit's packages MAY differ by distribution inside its code. A
  package name written `a|b` means the first of them the distribution has. A
  package the distribution does not have MUST be reported, not fail the
  install; the kit's checks then say whether the kit still works.
- **FR-004**: `kit add` MUST end by running the kit's checks and MUST report each
  program's version and each functional check's result. A kit is installed when
  every program it provides is present.

## The installers

- **FR-005**: The package installer MUST use the distribution's package
  manager (`apt-get`, through `sudo` unless the person is already
  administrator), non-interactively, without pinning a snapshot, and MUST
  install only the packages that are missing.
- **FR-006**: The download installer MUST fetch the address the kit declares
  for the machine's architecture (`x86_64` or `aarch64`), verify its SHA-256
  against the kit's before anything is unpacked, and refuse, leaving nothing
  installed, when they differ. It MUST unpack into
  `~/.local/share/workspaces-host/tools/<name>/<version>`, repoint
  `~/.local/share/workspaces-host/tools/<name>/current` atomically, and link the
  kit's binaries into `~/.local/bin` through `current`. A second install of the
  same version MUST change nothing, and an older version MUST stay on disk.
- **FR-007**: Neither installer MUST run when `--dry-run` is given or when the
  person is offline (`WS_HOST_OFFLINE=1` or `--offline`), where a download
  MUST fail with the name of what is missing and exit 3. No other installer, no
  version manager and no second package system MUST exist
  (0041-command-line FR-059).

## The v0.1 kits

- **FR-008**: The `base` kit MUST provide a standard userland (`sed`, `find`,
  `xargs`, `diff`, `cmp`, `patch`, `tar`, `gzip`, `unzip`, `zip`, `bzip2`, `xz`,
  `file`, `less`, `which`, `ps`, `hostname`, `tput`, `rsync`, `bc`, `grep` and
  `awk`), `git`, `gh`, `glab`, `jq`, `ripgrep`, `fd`, `curl`, `wget`, `python3`, `uv`,
  Node.js, ImageMagick able to read and write WebP together with `cwebp` and
  `dwebp`, `sqlite3`, `duckdb`, `shellcheck`, and a Chromium that Playwright
  can drive. Its checks MUST include a functional check of the userland, one
  that ImageMagick reads and writes WebP, and one that Chromium prints a page.
- **FR-009**: The `press` kit MUST provide the distribution's `texlive-luatex`,
  `texlive-xetex`, `texlive-latex-extra`, `texlive-fonts-recommended` and
  `texlive-science`, `latexmk`, `poppler-utils`, `qpdf`, `librsvg2-bin`, a
  headless Java runtime, `epubcheck`, `asciidoctor` with its PDF and EPUB 3
  converters where the distribution has them, and `potrace`. Its checks MUST
  include that `lualatex` compiles a document using `fontspec`, `unicode-math`
  and `lualatex-math`.
- **FR-010**: The `rust` kit MUST provide the current stable Rust from the
  official tarball, fetched and verified (FR-006), with `build-essential`,
  `cmake`, `pkg-config` and `perl`. Its version MUST be at least the
  one the company's website needs (1.87, edition 2024), and its checks MUST
  include that `rustc` compiles a program and that `cargo` is at least that
  version. The kit MUST NOT install or use `rustup`.
- **FR-011**: A kit's download versions, addresses and checksums MUST be in its
  code, and updating one MUST be a change of its own that the tests run
  against.

## The shell kit

- **FR-014**: The `shell` kit MUST provide `fish` 4 or later and `oh-my-posh`,
  and its checks MUST include that `fish` is version 4 or later and runs a
  command, and that `oh-my-posh` prints a prompt with each of the
  repository's themes (`themes/ws-host-pretty.omp.json` and
  `themes/ws-host-plain.omp.json`) and sets up both `bash` and `fish`. Where the
  distribution ships `fish` older than 4, the kit MUST fetch the fish project's
  own release package for that distribution, verify it (FR-006) and unpack it
  into the person's tools directory. Installing the kit MUST NOT change the
  person's login shell or their shell startup files (0005-help-and-docs FR-011);
  FR-015 is the one command that edits a startup file, and only when asked.
- **FR-015**: `shell add bash|fish` MUST give that shell the `oh-my-posh` prompt
  with the `ws-host-pretty` theme, or `ws-host-plain` with `--plain`, and `workspace ensure` MUST do the same by default
  (0006-onboarding FR-022); nothing else does. It MUST add one block between
  marker lines to `~/.bashrc` or to fish's `config.fish`, naming the marker so a
  person can delete it, MUST keep a copy of the file in the person's state
  directory first, MUST change nothing outside the markers, MUST change nothing
  on a second run, MUST change nothing under `--dry-run`, and MUST refuse to
  edit a file whose start marker has no end marker. It MUST download
  `oh-my-posh` (FR-006) when it is missing, MUST ask for `fish` to be installed
  first when it is missing, and MUST NOT change the login shell.
- **FR-016**: Installing packages MUST never be silent and MUST never hide a question. When sudo needs a password and there is a terminal, it MUST be asked for before any
  spinner or progress line is drawn, with a line that says why and that nothing shows as you type, and a refused password MUST stop before anything is installed. What the package
  manager says (the lists it fetches, each package it unpacks and sets up) MUST be shown as it says it, on standard error, and in the command's own progress lines
  for a program reading JSON; a step that says nothing for ten seconds MUST say that it is still working, for how long, and what it last said; and another package manager holding the lock MUST be
  waited for with apt saying who holds it, not left as silence. The end MUST say how many packages and how long.
- **FR-017**: A tool that the publisher changes often MAY float: a kit then names it with no version and no checksum of its own, and ws-host MUST find the newest release from the
  publisher when it installs, and MUST install nothing that does not match what that publisher publishes for that release: the checksum GitHub states for each release file (or one in a
  checksum file beside it), or the SHA3-256 a publisher lists for it on its own download page (sqlite.org), or the publisher's detached signature checked with `gpg` against a key that ships with ws-host and has the fingerprint the publisher publishes, or, for an npm or
  PyPI package, the registry's own integrity for the version, which its manager checks; with none of these it MUST refuse. A package MUST be installed with ws-host's own Node or uv into a folder of its
  own, and the program a person runs MUST find that Node by asking ws-host. A newer version MUST be installed beside the one in use and made current only when complete, the one before it kept
  and older ones removed. What is installed MUST NOT be looked into by an ordinary `ws-host update`, `workspace ensure` or install, so that they stay quick; `kit sync [KIT]` and `ws-host update --tools` MUST look for a newer release of every floating tool that is installed (or of one kit's), whichever kit put it there, and `kit add` MUST look for those of the kit it installs;
  a look that cannot be made MUST leave what is installed alone and not fail, and `--offline` MUST install nothing new. The `cloud` kit MUST be exactly the `aws`
  (aws, sam, cdk), `azure` (az, azd), `cloudflare` (wrangler, cloudflared) and `railway` kits together. This replaces FR-006's pinned checksum for these tools alone.
- **FR-018**: The `base` kit MUST install `duckdb` and SQLite's own command-line tools (`sqlite3`, `sqldiff`, `sqlite3_analyzer`) as floating tools (FR-017), where sqlite.org builds them
  (x86-64; elsewhere the distribution's `sqlite3` is the one used and ws-host MUST say so and not fail), and these modern command-line tools as floating tools (FR-017): eza, zoxide, fzf, yazi, bat, delta, sd, yq, glow, btop, dust, duf, procs, just,
  watchexec, hyperfine, scc, lazygit, tealdeer, xh, shfmt and actionlint; `tree` and `ncdu` come from the distribution's own packages. Each is found by the name of its release file for
  the machine's architecture, and refused unless it matches the checksum GitHub states for that file. When the newest release was made without its programs, or without a checksum from its publisher for them, the newest release before it that has both MUST be used, and the version installed MUST be named. `kit check` MUST ask each publisher for the newest release and say which
  installed tools are behind, and MUST change nothing.
- **FR-019**: The `modern-cli` kit MUST make `bash`, `fish` (where installed) and `git` use those tools, through chezmoi (0010-managed-config), in marked lines that never touch
  anything outside them: `ls`, `ll`, `la`, `lt` and `tree` by eza (with icons, which need a Nerd Font), `cat` by bat in plain form without a pager, `top` by btop, `..` and `...`, zoxide's
  `z` and fzf's keys; and in `~/.gitconfig`, placed first so a person's own settings win, delta as git's pager and diff filter and `zdiff3` conflicts. Every shell line MUST be used only
  when its program is installed, and `grep`, `find`, `sed`, `ps`, `du` and `df` MUST NOT be replaced. `workspace ensure` MUST apply it by default when the tools are installed, and
  `WS_HOST_MODERN=no` MUST opt out; `WS_HOST_PROMPT=plain` MUST leave the icons out. After a kit installs, ws-host MUST suggest `ws-host kit add modern-cli` until it is applied.
- **FR-020**: The `embedded-sql` kit MUST hold the house tools for lightweight and embedded SQL, each floating (FR-017): `turso` (the Turso command line), `usql`, `litestream`, `sqruff`,
  `dbmate`, and, from PyPI into folders of their own, `sqlite-utils`, `datasette`, `harlequin` and `visidata`. MotherDuck needs no program of its own (it is DuckDB with `ATTACH 'md:'`
  and a `MOTHERDUCK_TOKEN`), and ClickHouse MUST NOT be part of it. `workspace ensure` MUST install it by default with `base` and `shell`.

- **FR-021**: The `microsoft` kit MUST install Microsoft's `azure-identity` library (from PyPI, newest, with the registry's integrity) into a folder of its own, and `ms-python`, a Python that has it. The
  `onedrive` commands MUST reach the signed-in account's OneDrive over Microsoft Graph's REST API with a token from that library: `onedrive list` and `show` MUST change nothing; `onedrive add LOCAL REMOTE`
  and `onedrive sync REMOTE LOCAL` MUST NOT replace or delete a file that is already there unless `--replace` is given, MUST say what they left, MUST send a file over 4 MiB in an upload session, MUST never send
  the sign-in to a link Microsoft made for a download or an upload, MUST never write a file whose name would leave the folder, and MUST write nothing under `--dry-run`. With more than one sign-in,
  `--account` MUST be required.
## Declared kits

- **FR-012**: `workspace ensure` MUST install the kits the cloned repositories
  declare in `WS_HOST_KIT` of their `.workspaces-host/ws-host.env`, skipping
  those already installed, and MUST report a kit that is unknown or needs
  `sudo` that cannot be asked for, with the one command that fixes it, without
  failing the other steps' work.
- **FR-013**: A kit shipped by a repository (`<repo>/.workspaces-host/kits/`)
  follows the same contract (0041-command-line FR-061). Loading it is a later
  phase; until then `ws-host` MUST NOT load or run any repository's code, and
  `doctor` MUST say so when a trusted repository ships kits.

## Out of scope

- A `shell` kit, other distributions, generated containers.
- Pinning distribution package versions.

## Edge cases

- `kit add press` on a machine that has everything: nothing is installed and it
  says so, per FR-004 and FR-005.
- A download whose checksum differs: nothing is unpacked or linked, per FR-006.
- An older version of a download is on disk and a newer one is installed:
  `current` moves, the older stays, per FR-006.
- `kit add` with no terminal and no passwordless `sudo`: it installs the
  downloads, then says what to run in a terminal, per FR-002.
- A package this distribution lacks (an asciidoctor converter, `epubcheck`):
  reported and skipped; the checks decide, per FR-003.
- An unknown kit name: a usage error listing the kits, per FR-001.
- `--offline` with a download needed: exit 3 naming it, per FR-007.
- A repository names a kit `ws-host` does not have: reported with the kits it
  does have, per FR-012.
- `fd` is installed as `fdfind` by the distribution: the kit links `fd` to it in
  `~/.local/bin`, per FR-008.

## Assumptions

- The distribution is Debian or Ubuntu with `apt-get`; `sudo` exists for a
  person who may install packages.
- Downloads are reachable from the person's network.

## Open questions

- **OQ-1**: How a Chromium that Playwright can drive reaches Ubuntu on
  `aarch64`, where the distribution's package is a snap and the fetched build is
  `x86_64` only.

## Key entities

- **A kit** — a class declaring packages, downloads and checks.
- **A download** — a name, a version, an address, and a checksum per
  architecture.
- **`current`** — the link that names the installed version of a download.

## Success criteria

- **SC-001**: On Debian and Ubuntu, `kit add base press rust` leaves a machine
  where the userland check passes, `lualatex` compiles the test document,
  ImageMagick writes WebP, and `cargo` builds a crate using `reqwest` with
  `rustls`.
- **SC-002**: A download with the wrong checksum installs nothing.

## Review & acceptance checklist

- [x] Every requirement is testable (MUST / MUST NOT), not aspirational
- [x] No company fact is asserted here
- [x] Every open item is marked, not silently decided
- [x] Public-safe: no confidential information, no unverified number stated
      as settled fact
