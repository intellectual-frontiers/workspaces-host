# Spike: mise as the toolchain core, brew 7 and direnv as personal suggestions

Run on 2026-10-05 with mise 2026.10.3. Ubuntu 24.04 (glibc 2.39) directly; Debian 12 (glibc 2.36) and Debian 13 (glibc 2.41) in
chroots; Linux x86_64. This is a spike, not a spec: nothing here is a requirement until a spec states it. Re-run the main script
with `./run.sh [WORK]` (about 30 seconds, 1.5 GB, every download checked against a SHA-256 written in the script).

## Verdict

Assume mise. Every `agora` toolchain entry that is an install step works as plain, checksummed configuration, safe mode keeps the
declarations data-only, and agora's own functional checks pass against what mise installed. Two hazards need ws-host code, both
solved and tested below: content identity and host-environment scrubbing. Brew 7 and direnv are suggestions for a person's own
tools, detected read-only and never managed.

## What was checked

| Check | Result |
|---|---|
| Bootstrap one pinned, verified binary | Pass. The 30 MB `.tar.xz` (153 MB unpacked) matches its SHA-256. `linux-arm64` exists. |
| Registry tools (`node`, `uv`, `python`) | Pass. Per-platform URL and SHA-256 in `mise.lock`; `uv` also records a GitHub attestation. |
| `agora` entries as configuration through the `http:` backend (`jre`, `chromium`, `asciidoctorj`, `tinytex`, `vscode`) | Pass, same URLs and checksums as `agora` pins; four install in parallel in 14 to 18 seconds. |
| `tex-packages` (8 containers) | Pass as eight small `http:` entries with `TEXMFHOME={dir1,dir2,...}`; no overlay or recipe. `xelatex` and `lualatex` load them and the pinned `microtype` is found first. |
| npm entries through the `npm:` backend (TypeScript, esbuild, ESLint, `@vscode/vsce`, Playwright, Paragon with 416 packages) | Pass under `MISE_SAFE=1`. Each tool's graph is locked in a sidecar (`.config/mise/locks/npm-<name>/<version>/aube-lock.yaml`) referenced from `mise.lock` by SHA-256; a fresh machine installs from the lock in 18 seconds, and editing a sidecar is refused (`digest mismatch`). |
| **agora's own functional checks** (`agora_equiv.py`) run against the mise copies | Pass for `jre`, `chromium`, `tinytex` and `asciidoctor`. (`agora toolchain ensure` skips its check when an `AGORA_<ENTRY>` override stands in, so the check functions are called directly.) |
| Tamper (declaration or lock) | Pass. `Checksum mismatch`, nothing installed. |
| Fresh machine from the lock | Pass (`install --locked`, empty data directory, 14 seconds). |
| One file per entry (`.config/mise/conf.d/*.toml`), lock beside them | Pass. |
| `mise -C <provider> exec` from anywhere | Pass. PATH holds only that provider's directories. |
| Untrusted config, `MISE_PARANOID=1` | Refused until `mise trust`. |
| `MISE_SAFE=1` against a config with `exec()`, a hook, a task and `postinstall` | Pass. Nothing ran; tasks refused; `lock` and `install --locked` still work. |
| Offline and a local export (`file://` with a checksum) | Pass. A corrupted local file is refused. |
| Python and uv from mise | Pass (5 seconds); with `UV_PYTHON_DOWNLOADS=never`, `uv run` uses mise's interpreter. |
| **Debian 12** (glibc 2.36) and **Debian 13** (glibc 2.41), minimal systems | Pass for the whole of `run.sh`. Chromium needs the 21 system libraries `agora system ensure` lists (Debian 13 uses the `t64` names); with them it loads a page and `xelatex`, AsciidoctorJ and the JRE work. |
| **`linux-arm64`** | Partly. Archives for `jre`, Chromium and VS Code download and match `agora`'s SHA-256s; the JRE binary is aarch64. Nothing was run (no ARM machine). |
| **Real VS Code** 1.140.0 (the pinned build, installed by mise) under Xvfb, `vscode-terminal-env/` | Pass. An extension asks mise for each workspace folder's environment (safe mode) and scopes it to that folder with `environmentVariableCollection`; the `provider` folder's terminal runs the pinned `java`, the other folder's terminal the system one. It needs `--disable-workspace-trust`, `--skip-welcome` and `--no-cached-data` to start terminals headlessly. |
| `mise activate` in **bash**, in **fish 3.7**, and together with **oh-my-posh** (pinned v31.4.1, either order) | Pass. Entering the provider puts its tools first; leaving restores the PATH. |
| Older mise against a newer lock | Fails across 3 to 6 months (see below). |

## Hazards, and what to do about them

1. **Identity was the name and version, not the content.** Two providers declaring `http:jre` at one version with different
   artifacts shared one install and the second checksum was never compared (`run.sh` step 6). **Fix, tested (step 6b):** put the
   SHA-256 prefix in the tool name (`http:jre-2413149700df`). Different content installs separately; the same content from a
   second provider reuses one directory. ws-host generates the configuration, and a check fails if one name maps to two hashes.
2. **The host environment is not scrubbed by mise.** `TEXMFHOME`, `NODE_PATH`, `PLAYWRIGHT_BROWSERS_PATH` and others pass through.
   **Fix, tested:** run providers from `env -i` plus an allowlist (`HOME`, `LANG`, `TERM`, proxy and certificate variables, `MISE_*`,
   a minimal `PATH`). The scrubbed run kept `xelatex` and AsciidoctorJ working with every host variable unset.
3. **`mise activate` puts a shims directory on PATH,** so outside a provider a pinned-only tool answers `No version is set for shim`
   and suggests `mise use -g`, which would add a global pin. **Fix, tested:** strip the shims directory after activation and on each
   prompt; then the tool is `not found` outside, present inside, and gone after leaving, in bash.
4. **The lock format is tied to the mise version.** A lock written by 2026.10.3 installs with 2026.7.0 and its lock reads back, but
   2026.4.0 recorded no checksums for `http:` entries and 2025.10.0 has no `--locked`. Pin the exact mise version in each repo and
   treat a mise bump as a change of its own that regenerates the locks. mise releases very often (about 18 patch releases in a month),
   so a bump is deliberate, not automatic.
5. **A flat `url` applies to every platform;** always write the per-platform table. TinyTeX needs `bin_path = "bin/x86_64-linux"`.
   AsciidoctorJ's `-Xverify:none` warning returns (set the JVM options in the provider environment).
6. **`mise.lock` includes macOS and Windows entries by default** for registry tools; lock only `linux-x64,linux-arm64`.
7. **Disk.** Chromium 557 MB, TinyTeX 441 MB, node 203 MB, AsciidoctorJ 77 MB, uv 53 MB, the mise binary 153 MB; no sharing across
   versions. Unchanged from today's entries.
8. **`agora` ships no `linux-aarch64` TinyTeX archive,** so TeX is x86_64-only whichever engine is used.
9. **Third-party hosts.** Fixed `http:` entries need only the vendor's own URL. Registry tools also use `mise-versions.jdx.dev`
   (a shared cache of versions and attestations); with it off mise falls back to GitHub's API. mise reads the `gh` CLI's token from
   `hosts.yml` when it needs one, so the sign-in ws-host already prescribes covers rate limits (keep `HOME` in the allowlist).

## What stays ws-host's, not mise's

Functional checks, environment scrubbing and composing each provider's environment (the `TEXMFHOME` list, `PLAYWRIGHT_MODULE`,
the JVM options), the `system ensure` step for Chromium's and VS Code's libraries, and the content-identity naming. There are no
install recipes: nothing in `agora`'s nine entries needs one.

## Brew 7 and direnv: suggestions for personal or custom use

Policy: a provider's pinned tools come from mise. A person's own tools are theirs; brew 7 is a good home for them, direnv is a fine
personal choice, and ws-host detects both read-only (`detect_personal.py`) and reports them in `doctor` as suggestions, never as
problems. ws-host never installs, configures or updates either.

**Brew, checked against a real Homebrew 7.0.8.** It installed at the default prefix `/home/linuxbrew/.linuxbrew` as a non-root user on
Ubuntu 24.04 and Debian 12 (it needs git, curl and a compiler, not sudo, when that directory is writable). On Debian 12, `brew install jq`
worked and `jq` ran, but `brew doctor` warned that glibc 2.36 is too old and Homebrew would install a newer one itself, and the
installer's first `brew update` step failed; Debian 13 avoids the warning. Detection works with brew off PATH. `brew leaves` (what the
person chose) is the right list, not `brew list`, which includes dependencies. Brew's own PATH-shadow hints name programs
(`rg` is shadowed by `/usr/bin/rg`), so ws-host compares program names in brew's `bin`, not formula names, against a provider's
pinned programs.

**direnv.** Detected by presence and by a `direnv hook` line in the shell startup files. mise's documentation calls direnv together
with mise unsupported, so `doctor` says so and suggests trying without the direnv hook first if PATH looks wrong inside a provider.

Wording in `doctor`: `suggest`, a third level beside `ok` and `warn`, borrowed from the original repository (below).

## Ideas from the original `strategy-coach/workspaces-host`

A chezmoi-based setup (Fish, Homebrew, mise, pkgx, eget, direnv, SDKMAN, Deno scripts), written for a technical person who treats a
WSL instance as disposable. It has no pinning, Chromium or TeX. What may simplify this repository:

- **The decision table brew / pkgx / mise / eget / direnv** is the right "personal tools" guidance. With mise as the core it
  collapses: mise covers `eget` (GitHub release binaries), `pkgx` (per-project versions), SDKMAN (Java vendors: `java@temurin-...`,
  `corretto-...`) and `nvm`; brew is for convenience tools; direnv is optional.
- **`conf.d` directories for Fish** (`strategy-coach.fish`, `java.fish`, `direnv.fish`): one file per concern, which is the `.d`
  model. ws-host should write Fish snippets as `~/.config/fish/conf.d/ws-host-*.fish` and keep its marker block only for bash.
- **Managed-file headers.** Every generated file says `managed by ..., DO NOT EDIT; to change it use ...`. ws-host's marker blocks
  and generated files should say the same.
- **chezmoi for the person's own dotfiles** (shared data in `.chezmoidata.toml`, machine data in `chezmoi.toml`, `create_private_`
  files, `run_after_once` scripts re-run when their content changes, `chezmoi diff` and `apply --dry-run`). chezmoi is a single
  binary mise can pin, so ws-host could apply its managed configuration (prompt theme, completions, git config) through it and give
  a person a diff before anything changes. This is optional and worth a follow-up spike; ws-host's bespoke marker-block editing is
  the part it would replace.
- **Disposable instances and rebuilds.** The original treats WSL as something to delete and recreate (`wsl --unregister`,
  `wsl --install -d Debian`), keeps all configuration in Git, and backs up the few sensitive files to a OneDrive Personal Vault
  (`sensitivectl backup-to-onedrive-vault`, `restore-from-onedrive-vault`, both with `--dry-run`, vault path resolved from the
  Windows environment). For non-technical people this is the missing "undo" and "move to a new computer" story: a rebuild that
  loses nothing.
- **A Windows-side bootstrap.** It points to Microsoft's `windows-dev-box-setup-scripts` and gives the PowerShell lines; and a
  one-liner to move Debian 12 to 13, which also avoids brew's glibc warning above. ws-host's guide could do the same.
- **`doctor` with `ok`, `warn` and `suggest`** results per category, each diagnostic a small function.
- **Secrets:** a private per-machine file, `.pgpass`-style files created private, and `gopass` for the rest. With mise reading the
  `gh` token itself, ws-host does not need to carry a token into tool configuration the way the original does for `eget`.
- **`README.prompt.md`**, a document written to be pasted into an AI as context; ws-host's `context` and `help` do this already.

## Not tested

WSL itself and the Windows-side VS Code attaching to it (no Windows here); running anything on arm64; the Workspaces Console's own
code (only the underlying VS Code mechanism); fish with oh-my-posh; mise's behavior when `mise-versions.jdx.dev` or a vendor URL is
down; Chromium inside a sandbox-enabled desktop session; mise upgrades beyond the four versions above.

## Files

`run.sh` (main reproducible script; steps 1 to 7 and 6b), `agora_equiv.py` (agora's checks against mise installs),
`vscode-terminal-env/` (real VS Code per-folder terminal environment), `detect_personal.py` (read-only brew and direnv detection).
