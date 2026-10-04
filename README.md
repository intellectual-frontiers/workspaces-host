<p align="center"><img src="docs/mascot.jpg" alt="Workspaces Host mascot: a Clydesdale draft horse pulling a cart loaded with CODE, CONFIG and TOOLS crates" width="640"></p>

# workspaces-host

`ws-host` is the Intellectual Frontiers environment orchestrator. It prepares your machine, copies your repositories
and keeps them current without touching your work, installs kits, checks health, and ships the VS Code extension that
is the graphical interface for every orchestrator.

It targets Debian and Ubuntu on bare metal, including Ubuntu under WSL. It needs `python3` (3.11 or later), `git` and
`uv`; the installer adds `uv` if you lack it.

```sh
curl -fsSL https://raw.githubusercontent.com/intellectual-frontiers/workspaces-host/main/install.sh | sh
ws-host workspace advance
```

## Learn it

The daily work is documented in one place, the program: `ws-host help`, or **Learn** in VS Code, where every step is a
button. The guide in `docs-src/` is a reference and an overview; build it with `ws-host docs build`. Its command, kit,
file and help-topic chapters are generated from the code, so they cannot drift, and `ws-host fresh` fails until they
are current.

| | |
| --- | --- |
| `ws-host help` | the topics: start, repos, signin, trust, kits, shell, editor, recover, ai, extend |
| `ws-host doctor` | is my machine well? |
| `ws-host workspace advance` | do everything: sign in, copy, update, install kits, check |
| `ws-host kit add KIT` | install `base`, `press`, `rust` or `shell` |
| `ws-host vscode add` | install the VS Code extension |

## Shells

`bash` and `oh-my-posh` are fully supported. `fish` 4 is the best experience with `oh-my-posh`; the `shell` kit installs
both with the coach theme. `ws-host` never changes your login shell or your shell files.

## Extend it with AI

Everything is Python, found by presence: add a module to `ws_host/commands/`, `ws_host/kits/` or `ws_host/help/` and it
exists. A module imports only the standard library at the top; a package goes in a dependency group of `pyproject.toml`
and `uv.lock` and is imported inside the function that uses it. Point an AI at `.claude/skills/ws-host/SKILL.md`, then
run `ws-host doctor`, `check`, `test` and `fresh`.

## The pieces

- `ws-host`, `install.sh` — the launcher and the installer
- `ws_host/` — the core (standard library only), commands, kits, help topics, installers
- `vscode/` — the extension: `package.json`, `extension.js`, `logo.png`
- `docs-src/` — the guide; `docs/` — its home page and the mascot and graphics from the earlier environment
- `spec-kit/` — the specs, in the public root's format
- `tests/` — standard-library `unittest` with real temporary git repositories, Node tests for the extension with a stand-in
  VS Code, and `tests/containers/verify.sh` and `tests/vscode-host/run.js` for fresh Debian/Ubuntu containers and a real
  VS Code

The mascot and graphics come from the earlier environment (MIT; `docs/LICENSE-the earlier environment`).
