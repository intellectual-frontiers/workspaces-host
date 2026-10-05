# Spike: mise as the toolchain core (S2), and brew 7 for custom tools

Run on 2026-10-05, mise 2026.10.3, Ubuntu 24.04 (glibc 2.39), Linux x86_64, no display, no WSL. Reproduce with `./run.sh [WORK]`
(about 30 seconds, 1.5 GB, everything checked against the SHA-256 written in the script). This is a spike, not a spec: nothing
here is a requirement until it is stated in one.

## Verdict

mise clears every check that matters for the pinned layer, with two hazards that ws-host must design around (identity, and
host-environment scrubbing). S2 remains the front-runner. Brew is the right place for a person's own, custom tools, and ws-host
detects it and never manages it.

## What was tried

| # | Check | Result |
|---|---|---|
| 1 | Bootstrap one pinned binary, verified before use | Pass. `mise-v2026.10.3-linux-x64.tar.xz` is 30 MB and matches the published SHA-256; it unpacks to a 153 MB binary. A `linux-arm64` build exists (not run). |
| 2 | Registry tools install with checksums in the lock | Pass. `node` and `uv` install; `mise.lock` records a URL and SHA-256 for each platform, and `uv` also records a GitHub attestation. |
| 3 | Our own non-registry entries, exactly as `agora` pins them (same URL, same SHA-256), through the `http` backend | Pass. `jre` (Temurin 21.0.12.1+1), `chromium` (Playwright 1.50.0 build 1155), `asciidoctorj` 3.0.1 and `tinytex` 2026.03 install in parallel in 14 to 18 seconds. |
| 4 | The tools work | Pass. `xelatex` compiles a `fontspec` document, `asciidoctorj` converts a page on the pinned JRE (it finds `java` from the provider's PATH), Chromium 133 starts. |
| 5 | Tamper: wrong checksum | Pass. `Checksum mismatch`, nothing installed. Also fails when the lock holds the wrong hash and the declaration has none. |
| 6 | Fresh machine from the lock (`install --locked`, empty data directory) | Pass, 14 seconds. |
| 7 | Declarations as one file per entry (`.config/mise/conf.d/*.toml`), lock beside them (`.config/mise/mise.lock`) | Pass. This is the `.d` layout, natively. |
| 8 | Provider selected from anywhere: `mise -C <repo> exec -- cmd` | Pass. PATH is that provider's directories only. |
| 9 | Untrusted config | Pass. Refused until `mise trust`, even for `mise env`; `MISE_PARANOID=1` also refuses. |
| 10 | `MISE_SAFE=1` against a config with an `exec()` template, an `enter` hook, a task and a `postinstall` | Pass. Nothing ran; tasks are refused with a clear message; `install --locked` and `lock` still work. |
| 11 | Offline | Pass. `MISE_OFFLINE=1` works for what is cached and fails by name for what is not (`offline mode is enabled`). |
| 12 | Python and uv from mise | Pass. `python@3.12.11` (standalone build) and `uv@0.9.30` in 5 seconds; with `UV_PYTHON_DOWNLOADS=never`, `uv run` uses mise's interpreter. |
| 13 | Cleanup | Partly. `mise prune` follows tracked config links (the same idea as symlink GC roots); I only ran `--dry-run`. |

## Hazards found

1. **Identity is the name and version label, not the content.** A second provider that declares `http:jre` at `21.0.12.1+1`
   with a different artifact (I used the aarch64 build) gets `already installed`: its checksum is never compared with what is
   on disk (`run.sh` step 6). A checksum guards the download, not reuse. ws-host must generate the mise configuration from its
   own declarations and bake the content into the identity, for example `http:jre-2413149` or a version label that carries the
   SHA-256 prefix, and a check must fail when two providers map one name and version to two hashes.
2. **A flat `url` applies to every platform.** My first attempt used one `url` and the lock gave `linux-arm64` the x64 archive
   and checksum. Always write `[...platforms]` with one URL per platform.
3. **The host environment passes straight through.** `TEXMFHOME`, `NODE_PATH` and `PLAYWRIGHT_BROWSERS_PATH` reached the child
   process unchanged. `agora` scrubs these today, so ws-host (not mise) must run providers with a clean, allowlisted environment.
4. **Non-standard layouts need `bin_path`.** TinyTeX needs `bin_path = "bin/x86_64-linux"`; Chromium has its program at the root.
   Both worked once stated.
5. **The `-Xverify:none` warning** from AsciidoctorJ's start script reappears. `agora` avoids it with its own `argv`; ws-host
   can set the JVM options in the provider's environment.
6. **The lock holds the install platform's checksum as `blake3`** in one case (a flat `url` entry), not the SHA-256 written in the
   declaration. The declaration still carries the SHA-256 that was checked; keep it there.
7. **Disk.** 153 MB binary; installs of 557 MB (Chromium), 441 MB (TinyTeX), 203 MB (node), 77 MB (AsciidoctorJ), 53 MB (uv).
   That is the same as the entries are today, and nothing is shared across versions.
8. **ARM.** Registry tools lock `linux-arm64` too. `agora`'s TinyTeX entry has no `linux-aarch64` archive at all, so TeX is
   x86_64-only today whichever engine is used.

## What did not fit in mise (stays ws-host's)

- **The npm tree** (`npm ci` from a committed `package-lock.json`, Playwright and Paragon): needs a command run after unpacking,
  which safe mode refuses by design. It stays a ws-host recipe, run under the provider's trust.
- **`tex-packages`** (checksummed packages laid over TinyTeX) is the same kind of overlay and stays a recipe.
- **Functional checks** (compile a document, convert a page) are ws-host's own; mise only installs.
- **Environment scrubbing and the `AGORA_<ENTRY>` style overrides** are ws-host's.

## Not tested

VS Code terminals and the Workspaces Console picking up a provider's PATH (no display); WSL; Debian 12 and 13; `linux-arm64`
runs; the `vscode` and `tex-packages` entries; real brew (see below); mise's own upgrade path across releases; how stable
`mise.lock` is across mise releases. These are the next checks.

## Design implications if S2 is chosen

- Prerequisite: one pinned mise release, fetched and verified by `install.sh` and by each launcher.
- Each provider's `.workspaces-host/` holds the declarations (one file per entry); ws-host translates them to mise configuration
  and runs mise with `MISE_SAFE=1`, a clean environment, and `-C <provider>`.
- Content identity (hazard 1) and environment scrubbing (hazard 3) are ws-host's responsibility and need tests.
- ws-host itself stays a uv-locked Python package; the launcher reaches it through mise's Python and uv.

## Brew 7: for custom tools, detected by ws-host

Policy: a provider's pinned tools come from mise. A person's own, custom tools (anything not declared by a provider) are theirs
to install with brew 7, which is a good fit for that: current versions, signed and attested bottles, `brew vulns`, Landlock
sandboxing, and a tap trust model (Homebrew 6 and 7 release notes, read on the same date).

- ws-host never installs, updates or removes brew or a formula. Installing brew needs sudo, git, curl and a compiler and a fixed
  prefix, so ws-host only explains it when asked.
- ws-host detects it, read-only: `brew` on PATH, then `/home/linuxbrew/.linuxbrew/bin/brew`, then `~/.linuxbrew/bin/brew`;
  `brew --version`, `brew --prefix`, `brew list --formula --versions`. `detect_brew.py` is a standard-library prototype; with no
  brew it reports "not installed, and that is fine". It was exercised against a stub only, not a real brew.
- `doctor` reports brew's version (and that it is older than 7), its prefix and the count of formulae.
- PATH order: a provider's environment first, then brew, then the system. A brew tool can never shadow a pinned one inside a
  provider, and `doctor` warns when a brew formula has the same name as a pinned program.
- Why not brew for the pinned layer: global single version, no exact-version lock with hashes, a fixed prefix, Ruby tap code,
  and a glibc baseline that Homebrew 5.1.0 planned to raise to 2.39, which Debian 12 (2.36) does not meet (the final baseline
  was not confirmed).
