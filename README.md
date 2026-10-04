# workspaces-host

`ws-host` is the Intellectual Frontiers environment orchestrator. It prepares a
person's machine, clones and updates their repositories, installs kits, checks
health, and ships the VS Code extension that is the graphical interface of
every orchestrator.

It targets a Debian-family Linux machine (Debian, Ubuntu, Ubuntu under WSL) and
needs only `python3` (3.11 or later), `git` and `uv`.

```sh
curl -fsSL https://raw.githubusercontent.com/intellectual-frontiers/workspaces-host/main/install.sh | sh
ws-host workspace advance
```

Specs are in `spec-kit/specs/`, written to the public root's spec format;
`ws-host test` runs the tests and `ws-host check` the checks.
