# Feature Specification: Onboarding on Windows 11 with WSL, and the Pages site

**Spec ID:** 0006-onboarding
**Status:** Draft

**Input:** The path a non-technical person takes from a Windows 11 computer to
working in VS Code with `ws-host`, and the written guide that walks them down it.
The person knows the very basics: they can open an app, copy a line and paste it
into a terminal, and click. They run Debian, installed from the Microsoft Store,
under WSL. The installer does the bootstrapping, one prescribed sign-in
connects them to GitHub, VS Code opens with the extension and a sensible set of
extensions and settings already in place, and Learn teaches the rest. The
README gives the high-level flow; a site on GitHub Pages gives the next level of
detail, troubleshooting, and how to take over in VS Code.

## The bootstrap

- **FR-001**: `install.sh` MUST install what it needs and the machine lacks
  (`python3`, `git`, certificates and `curl`, by the distribution's package
  manager), MUST say what it will install and that it needs administrator
  rights before it asks, MUST name the command to run when it cannot (no `sudo`,
  no network), and MUST do none of this when `WS_HOST_NO_APT=1`. It MUST work
  for an ordinary user and for administrator alike.
- **FR-002**: Unless `WS_HOST_NO_ADVANCE=1`, `install.sh` MUST end by running
  `ws-host workspace advance`, and MUST say, in plain words, what to do next if
  that asked the person to sign in.
- **FR-003**: Every instruction for the bootstrap MUST work in Debian from the
  Microsoft Store under WSL on Windows 11, as a person finds it: a minimal system
  with `sudo` and an account they created at first launch.
- **FR-004**: A person MAY name the kits they always want in `WS_HOST_KIT` of
  their own configuration; it is `base` when they say nothing and none when it is
  empty. `workspace advance` MUST install them before anything else, because the
  sign-in tool is in `base`.
- **FR-005**: Signing in to GitHub MUST be prescribed one way: `ws-host auth new
  github`, the one-time code and the browser, never a password, a token or an
  SSH key. `workspace advance` MUST stop, before copying anything, when GitHub
  says the person is not signed in, with that one command as the next action
  and exit status 0, and MUST go on when it cannot tell.
- **FR-006**: `workspace advance` MUST, when the `code` command is on the
  machine, install the extension (0004-editor-extension FR-016) and offer
  `vscode advance` as an action; and MUST, when it is not, say in plain words
  how to get VS Code reachable from the terminal. It MUST NOT apply VS Code
  settings or install other extensions by itself.

## The first run

- **FR-016**: What `ws-host` shows a person at a terminal MUST be friendly: colour
  and emoji when the output is a terminal, never when it is a pipe or a file,
  never when `NO_COLOR` is set or `TERM` is `dumb`, never in JSON or HTML, and
  settable by `WS_HOST_COLOR` (`always` or `never`). Colour MUST add to the
  words and never replace them: the first line is the same plain sentence
  (0041-command-line FR-054) and every status is also a word.
- **FR-017**: After the bootstrap `install.sh` MUST show the `start` help page, so
  that what it prints is the program's own text and cannot drift. The page MUST
  give, in order and each with the one line to type: signing in to GitHub, copying
  the starter repositories, opening VS Code from the terminal, `ws-host vscode
  advance`, continuing in VS Code with Learn, choosing which repositories to work
  in, trying `fish`, and what to do when stuck.
- **FR-018**: Until a person's own configuration says otherwise, their
  repositories MUST be the two starter repositories, the public root
  (`.github`) for examples and this repository (`workspaces-host`);
  an explicit `WS_HOST_REPOS`, even empty, replaces them.
- **FR-019**: `repo add` given a full repository address that is not on the
  person's list MUST put it on their own list, keeping every other line of their
  file and the starters while they have not chosen a list of their own, and then
  copy it; `--dry-run` MUST change neither the list nor the disk, and the
  page MUST also say how to edit the file by hand in VS Code.

## Setting VS Code up

- **FR-007**: `vscode advance` (setup) MUST install the extension, install the
  recommended extensions the person lacks, and add the baseline settings the
  person has not set. It MUST take `--dry-run`, MUST be repeatable, and MUST
  change nothing the person set: a setting they have stays as they have it.
- **FR-008**: The recommended extensions and the baseline settings MUST be
  code, MUST be listed in the guide's generated reference, and MUST be
  chosen so that a person never has to decide: GitHub pull requests, GitLens,
  Python, AsciiDoc and ShellCheck; automatic saving, automatic fetching,
  no smart commit, no startup page, workspace trust on, a terminal profile
  that is `fish` when it is installed and `bash` otherwise, and a terminal font
  that falls back to one that exists.
- **FR-009**: Under WSL the settings MUST be written to VS Code's machine
  settings in `~/.vscode-server/data/Machine/settings.json`, and elsewhere to
  the user's own file. A settings file `ws-host` cannot read safely, such as one
  with comments, MUST be left exactly as it is, with the values listed so the
  person can add them. A backup of a file MUST be kept in `ws-host`'s state
  directory before it is changed.

## The site

- **FR-010**: The guide MUST be deployed to GitHub Pages from this repository
  by `.github/workflows/pages.yml`, on every push to `main`, using the Pages
  actions, after the tests and `fresh` pass. The one setting only the owner can
  change, Pages' source set to GitHub Actions, MUST be said in the guide's
  maintainer notes and in the workflow's header.
- **FR-011**: The site MUST be a multi-page HTML site with a navigation on
  every page and a home page that links to each part, built by `docs build`
  with no converter beyond `asciidoctor` (0005-help-and-docs FR-006).
- **FR-012**: The site MUST have, in this order: getting started on Windows 11
  with WSL and Debian from the Microsoft Store; signing in to GitHub; VS Code
  (installing it, the WSL extension, opening the workspace in WSL, `vscode
  add` and `vscode advance`, reloading, Learn); how the extension works and why it
  is installed locally and not from the Marketplace; typical uses; the reference;
  and a FAQ with troubleshooting. Each step MUST say where to type it
  (Windows Terminal, the Debian window, VS Code) and what the person will see.
- **FR-013**: The FAQ MUST cover every failure that stops the bootstrap or VS
  Code from opening, each as a symptom, a cause and the fix, in plain words:
  WSL not installed or virtualization off; Debian not starting; no `sudo`
  password remembered; `curl` or `git` missing; no network, a proxy or a
  certificate error; `~/.local/bin` not on `PATH`; `ws-host: command not
  found`; the sign-in code or browser not opening; a wrong or stale clock;
  "could not read Username"; `code` not found in Debian; VS Code opening in
  Windows and not in WSL; the extension not showing; Restricted Mode; the
  settings file with comments; and a repository that was left alone.
- **FR-014**: The guide MUST link, for the steps it does not own (turning on
  WSL, the Store, installing VS Code, the WSL extension, GitHub's device
  login), to the vendor's own full instructions by `https` address, and MUST
  NOT copy them.
- **FR-015**: The README MUST give only the high-level flow, in five steps, and
  link to the site for everything else. It MUST NOT repeat a step the site or
  `help` explains in detail.

## Out of scope

- Installing WSL or VS Code: the vendors' instructions.
- Windows 10, running on macOS itself and other distributions; a Mac works through a Debian or Ubuntu virtual machine or container.

## Edge cases

- `install.sh` run as an ordinary user with no `curl`: it installs `curl` and
  the rest after saying so, per FR-001.
- No network: it says so and names what to check, per FR-001.
- A person who is not signed in runs the installer: it stops before copying
  and shows one command, per FR-002 and FR-005.
- `gh` is missing when `advance` runs: `base` installs it first, per FR-004.
- VS Code is not installed: `advance` says how to get `code` reachable, per
  FR-006.
- A person's settings file has their own `files.autoSave`: it stays, per FR-007.
- A settings file with comments: left alone, with the values listed, per
  FR-009.
- A person runs `vscode advance` twice: the second changes nothing, per FR-007.
- Pages is not yet switched to GitHub Actions: the deploy job says so and the
  guide's maintainer notes name the setting, per FR-010.

## Assumptions

- The person has Windows 11 with virtualization available, an internet
  connection, and a GitHub account.
- `code`, installed on Windows, is reachable from the Debian window after VS
  Code has opened a folder in WSL once.

## Open questions

- **OQ-1**: Whether `vscode advance` should also offer to install the Nerd Font
  that `oh-my-posh` draws with, which lives on the Windows side.

## Key entities

- **The bootstrap** — `install.sh` and the first `workspace advance`.
- **The baseline** — the recommended extensions and settings of `vscode advance`.
- **The site** — the guide's multi-page HTML on GitHub Pages.

## Success criteria

- **SC-001**: A person with Windows 11 follows the site from the Microsoft Store
  to VS Code with the extension, using only copy, paste and clicks.
- **SC-002**: No setting a person made is ever changed.

## Review & acceptance checklist

- [x] Every requirement is testable (MUST / MUST NOT), not aspirational
- [x] No company fact is asserted here
- [x] Every open item is marked, not silently decided
- [x] Public-safe: no confidential information, no unverified number stated
      as settled fact
