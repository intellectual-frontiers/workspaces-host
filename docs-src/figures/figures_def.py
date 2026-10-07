"""The guide's figures, as data: name -> a function that draws it to a path. Labels carry no em dash and no straight quote."""
import layouts

P = ("primary-tint", "primary", "ink", False)
E = ("emphasis-tint", "emphasis", "emphasis", False)
N = ("neutral-tint", "line", "body", False)


def layers(*rows):
    return [(t, f, s, tf, b) for t, (f, s, tf, b) in rows]


def system_map(path):
    layouts.stack_layers(path, "The system in five layers", "Each layer talks only to the one below it", layers(
        ("A person in VS Code, a terminal, or an AI agent", E),
        ("The Workspaces Console: draws what the launcher says, runs nothing of its own", P),
        ("ws-host: a registry of commands, kits and help topics; every command returns one Resource", P),
        ("lib/: git, repositories, trust, kits, mise, chezmoi, fetch. Plain Python with no command line in it", N),
        ("The machine: apt, your home folder, ~/.local/share/workspaces-host, and the clones in ~/workspaces", N)),
        box_w=900)


def bootstrap(path):
    layouts.chain_vertical(path, "From curl to a working machine", "install.sh, then the launcher, then Python", [
        "install.sh checks git, curl, tar and xz, installs missing ones with apt, then clones the repository",
        "It links ~/.local/bin/ws-host to the launcher and runs it once with WS_HOST_BOOTSTRAP_ONLY=1",
        "The launcher fetches mise, and checks its SHA-256 against bootstrap.env before unpacking",
        "mise installs the pinned Python and uv into its own store",
        ("python -m ws_host runs workspace ensure", True)], box_w=860)


def pins(path):
    layouts.converge(path, "Three places a version is pinned", "Each one is checked before anything runs", [
        "bootstrap.env pins mise, Python and uv",
        "toolchain.d pins provider tools, locked in mise.lock",
        "Each kit pins its downloads, a SHA-256 per architecture"],
        "A wrong fingerprint installs nothing")


def toolchain(path):
    layouts.chain_vertical(path, "How a provider names its tools", "This repository is itself a provider", [
        "toolchain.d/NAME.toml: an exact version, an https URL and a SHA-256 per platform",
        "toolchain generate writes mise config under .workspaces-host/mise/.config/mise/conf.d",
        "mise lock writes mise.lock for linux-x64 and linux-arm64",
        ("toolchain ensure refuses stale or unlocked files, then runs mise install --locked", True)], box_w=860)


def kit_life(path):
    layouts.chain_vertical(path, "A kit from declaration to proof", "Declared in code, planned, installed, then checked", [
        "A Kit subclass in ws_host/kits lists apt packages, downloads, links and checks",
        "kitrun.plan resolves what is missing, with no change to the machine",
        "kitrun.install: apt through sudo, then each download verified and unpacked, then links in ~/.local/bin",
        ("kit_report runs each check: the program is there, then it does a small real job", True)], box_w=860)


def managed(path):
    layouts.stack_layers(path, "What ws-host writes, and what it leaves alone", "Three managed files, each by consent", layers(
        ("A marked prompt block in ~/.bashrc, after shell add bash", P),
        ("A marked prompt block in fish config.fish, after shell add fish", P),
        ("Missing keys in the VS Code settings file, never a key you set", P),
        ("Never read: any chezmoi config or source of your own, and any text outside the markers", E)), box_w=900,
        note="Only text between the markers, or a key that was absent, is ever written")


def ensure_flow(path):
    layouts.chain_vertical(path, "How config ensure changes a file", "Idempotent: a current file is not touched", [
        "Render one modify script per target into a throwaway chezmoi source folder",
        "chezmoi cat says what the file would become; compare it with the file",
        "Same text: stop. Nothing is written and no backup is made",
        "Different text: copy the file to ~/.local/state/workspaces-host/backups with a timestamp",
        ("chezmoi apply writes it", True)], box_w=860)


def registry(path):
    layouts.tree(path, "Discovery by presence", "registry.discover imports every module in three packages", "ws_host.core.registry.discover",
                 ["commands/: one module per noun group", "kits/: one module per kit", "help/: one module per topic",
                  "Generators and check sections declared by the modules"])


def resource(path):
    layouts.tree(path, "One Resource, three views", "The same data, drawn for whoever asks", "Resource: kind, id, data, links, actions",
                 ["text: first line is data.plain, then what you can do next", "--json: the wire document, schema ws-host/kind@N",
                  "--html: script-free markup for a page"])


def sync_gate(path):
    layouts.gate(path, "Will repo sync touch this repository?", "It only ever fast-forwards", "Is the copy clean, attached, on a branch, and strictly behind?",
                 "git merge --ff-only. The copy catches up.", "Left exactly as it was. The reason is said in plain words.")


def console_run(path):
    layouts.chain_vertical(path, "How the Console runs a command", "The editor holds no knowledge of ws-host", [
        "Handshake: command list gives commands, titles, icons and views, and the schema is checked",
        "Rows: the list command of each noun fills the trees, with a status turned into an icon",
        "A write runs --dry-run first, and its changes open as a diff",
        "A decision also needs a modal that returns exactly true",
        ("Then the real run, and the result is drawn from JSON", True)], box_w=860)


def release(path):
    layouts.chain_vertical(path, "A release is four files", "Built from pinned tools, so a rebuild gives the same bytes", [
        "uv build makes the wheel with a fixed SOURCE_DATE_EPOCH",
        "The app tarball is rebuilt from the wheel with sorted entries and fixed times",
        "The Console is built from npm ci, then vsce, then a normalized zip",
        "SHA256SUMS lists the three. check reproducible builds twice and compares",
        ("release publish asks a person, then runs gh release create", True)], box_w=860)


def enforcement(path):
    layouts.converge(path, "What says a change is sound", "Run these before you hand work back", [
        "ws-host test: unittest over real temporary git repositories",
        "ws-host check: registry, launcher, specs, fresh, help, providers",
        "ws-host fresh: generated reference and skill match the code",
        "ws-host doctor: the registry has no conflict, this machine is healthy"],
        "Green on all four")


def prompting(path):
    layouts.chain_vertical(path, "The shape of a good maintenance prompt", "Name the layer, the file, the rule and the proof", [
        "The outcome in plain words, and what must stay true",
        "The layer and the files to read first, copied from a task page",
        "The rule that applies: pins, safety, discovery by presence",
        "The checks to run, and what to regenerate",
        ("Ask it to say what it did not verify", True)], box_w=860)


FIGURES = {"fig-1.1": system_map, "fig-2.1": bootstrap, "fig-3.1": pins, "fig-3.2": toolchain, "fig-4.1": kit_life, "fig-5.1": managed,
           "fig-5.2": ensure_flow, "fig-6.1": registry, "fig-6.2": resource, "fig-7.1": sync_gate, "fig-8.1": console_run, "fig-9.1": release,
           "fig-9.2": enforcement, "fig-10.1": prompting}
