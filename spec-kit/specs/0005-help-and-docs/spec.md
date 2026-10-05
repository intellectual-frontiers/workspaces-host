# Feature Specification: Help, the guide and the shell

**Spec ID:** 0005-help-and-docs
**Status:** Draft

**Input:** How a person learns `ws-host`. The work they do every day is
documented in one place only, the `help` command, so that it cannot drift from
what the code does, and the editor can teach it by letting a person run each
step. The guide, a book in four editions, is a reference and an overview: it
explains how the pieces fit, generates its command and kit reference from the
code, and links to `help` for everything a person does by hand. The guide
carries the project's mascot and graphics. This spec also states what the guide says about shells:
`bash` and `oh-my-posh` are fully supported, `fish` 4 is the best experience, and
everything is extended with AI, in Python, through the registry.
(0041-command-line FR-065 governs `help`.)

## Help

- **FR-001**: `help [TOPIC]` (read) MUST list the topics when given none and
  otherwise return the topic as a resource. A topic MUST be code in
  `ws_host/help/`, found by presence like a command, and MUST have a name, a
  plain one-sentence summary, and sections of plain language (no jargon in the
  first line, 0041-command-line FR-054). A topic MUST NOT be a file that a
  person edits.
- **FR-002**: A topic MUST give each thing a person does as a step that is an
  action (0041-command-line FR-017): a button in the editor, and one pasteable
  line in the terminal. A step the person must do themselves, such as opening a
  browser, MUST be said in words and not as an action.
- **FR-003**: The topics MUST cover at least: `start` (the first day), `repos`
  (copying and updating repositories safely), `signin`, `trust`, `kits`,
  `editor`, `shell`, `recover` (what to do when something fails or a repository
  was left alone), `ai` (working with an AI agent safely) and `extend`
  (adding a command or a kit with an AI).
- **FR-004**: The editor MUST offer the topics as "Learn", a quick-pick of the
  topics `help` lists, and MUST show a topic as any other resource, its steps
  as buttons (0009-workspaces-console FR-031, FR-043,).
- **FR-005**: Topics MUST NOT name a command, a kit or a path that does not
  exist, and every action in a topic MUST name a command the registry has.
  `check` MUST fail when one does.

## The guide

- **FR-006**: The guide MUST be written in AsciiDoc under `docs-src/` and built
  by `docs build` (build) into single-page HTML, a multi-page HTML site
  (0006-onboarding FR-011), a PDF where the converter is on the machine, and an
  EPUB where the converter is on the machine. A converter that is missing MUST be
  said in the result, never reported as built, and `docs build` MUST name the
  `press` kit when `asciidoctor` itself is missing.
- **FR-007**: The guide MUST be a reference and an overview. Its chapters on
  the commands, the kits, the files and the help topics MUST be generated from
  the registry, the kits and the topics by `docs generate` (generate), each file
  carrying a header naming its generator, and proven current by `fresh`. A
  chapter MUST NOT repeat a step that a topic gives: it names the topic
  (`ws-host help repos`) instead.
- **FR-008**: The guide MUST use the project's mascot and graphics (its logo,
  its two mascot pictures and its social preview) from `docs/`, the IF Press
  theme for the PDF (a format asciidoctor-pdf owns, which 0041-command-line
  FR-049 allows), and one stylesheet each for HTML and EPUB.
- **FR-009**: The guide MUST be written in the voice the repository's writing
  rules set: it starts with the point, in the first person, in plain words,
  with no hedging and no throat-clearing.
- **FR-010**: `docs/index.html` MUST be the one hand-written page of the guide:
  the mascot and a link to each edition. Everything else the guide publishes MUST
  be generated.

## Shells

- **FR-011**: The guide and the `shell` topic MUST say that `bash` and
  `oh-my-posh` are fully supported, that `fish` 4 is the best experience with
  `oh-my-posh`, that `fish` 4 comes in the `shell` kit with `oh-my-posh` and the
  prompt themes (0003-kits FR-014), and how to try it and how to make it
  the login shell, as a separate step that only the person takes. `ws-host` MUST
  NOT change a person's login shell, and MUST edit a shell startup file only
  to add the marked prompt block of `shell add`, which setup runs by default
  and a person's `WS_HOST_PROMPT=no` stops (0003-kits FR-015, 0006-onboarding FR-022).
- **FR-012**: The guide and the `extend` topic MUST say that everything is
  extended with AI, in Python: a new command or kit is a Python module added by
  presence to `ws_host/commands/` or `ws_host/kits/`, importing only the
  standard library at module level; a package it needs is a dependency group
  in `pyproject.toml` locked by `uv.lock`, imported inside the function that uses
  it; and `doctor`, `check`, `test` and `fresh` say whether the change is sound.
  They MUST NOT describe any other way to extend it.

## Agents

- **FR-013**: `skill generate` (generate) MUST write the agent skill
  `.claude/skills/ws-host/SKILL.md` from the registry alone, listing every command
  with its category and surfaces, saying that a `decision` is for a person, and
  `fresh` MUST prove it current (0041-command-line FR-037).
- **FR-014**: `fresh [GENERATOR...]` (check) MUST regenerate each generator's
  output (`agent-skill`, `reference-docs`) outside the working tree, compare it
  with the tracked files, and fail naming the generator and the command that
  rewrites it (0041-command-line FR-036). `check` MUST include a section
  `fresh` and a section `help`.

## Out of scope

- Hosting the guide.
- Translations.

## Edge cases

- A topic's action names a command that was removed: `check help` fails, per
  FR-005.
- A generated chapter was edited by hand: `fresh` fails naming `reference-docs`
  and `docs generate`, per FR-007 and FR-014.
- `docs build` on a machine without `press`: the result says which converters
  are missing and which editions were built, per FR-006.
- A person asks for help while offline: topics are code, so they work offline,
  per FR-001.
- A person on `bash` asks about `fish`: the `shell` topic says `bash` is fully
  supported and how to try `fish` without changing anything, per FR-011.
- A person asks an AI to add a command: the `extend` topic names the files and
  the four checks, per FR-012.

## Assumptions

- The `press` kit supplies `asciidoctor` and its PDF converter on Debian and
  Ubuntu; EPUB and multi-page HTML converters may be absent there.
- The repository's licence covers the mascot and graphics.

## Open questions

- **OQ-1**: Whether the guide should be published as a website, and where.

## Key entities

- **A topic** — one `help` subject in code, in plain language, whose steps are
  actions.
- **The guide** — the AsciiDoc book in `docs-src/`, built to HTML, PDF and
  EPUB.
- **A generator** — `agent-skill` or `reference-docs`: code that writes files
  that `fresh` proves current.

## Success criteria

- **SC-001**: Changing a command, a kit or a topic changes the guide's reference
  with no hand edit, and `fresh` fails until it has.
- **SC-002**: A person can learn the daily work from the editor's Learn command
  without reading the guide.

## Review & acceptance checklist

- [x] Every requirement is testable (MUST / MUST NOT), not aspirational
- [x] No company fact is asserted here
- [x] Every open item is marked, not silently decided
- [x] Public-safe: no confidential information, no unverified number stated
      as settled fact
