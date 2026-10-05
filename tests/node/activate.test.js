"use strict";
// The extension, activated against a stand-in VS Code and fake orchestrators (shell scripts that answer from files).
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { makeVscode, install } = require("./vscode-stub.js");

const esc = s => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const doc = (schema, data, actions = [], links = [], audience = "private") => ({ schema, audience, kind: schema.split("/")[1].split("@")[0], id: "x", data, links, actions });
const page = d => `<!doctype html><html><head><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"></head><body data-resource="${esc(JSON.stringify(d))}"><h1>${d.data.plain || ""}</h1></body></html>\n`;
const act = (label, command, extra = {}) => Object.assign({ label, command, fields: {}, needs: [], category: "setup", surfaces: ["terminal", "editor"], cli: "x " + command, enabled: true, reason: null }, extra);

class Fake {
  constructor() {
    this.dir = fs.mkdtempSync(path.join(os.tmpdir(), "wsx-"));
    this.bin = path.join(this.dir, "bin"); fs.mkdirSync(this.bin);
    this.log = path.join(this.dir, "calls.log");
    this.resp = path.join(this.dir, "resp"); fs.mkdirSync(this.resp);
    this.repo = path.join(this.dir, "acme"); fs.mkdirSync(this.repo);
    this.other = path.join(this.dir, "untrusted"); fs.mkdirSync(this.other);
    this.launcher(path.join(this.bin, "ws-host"), "ws-host");
    this.launcher(path.join(this.repo, "acme"), "acme");
    this.launcher(path.join(this.other, "evil"), "evil");
    fs.writeFileSync(path.join(this.repo, "notes.txt"), "not a launcher");
    this.setup();
    this.savedPath = process.env.PATH;
    process.env.PATH = this.bin + path.delimiter + process.env.PATH;
  }
  launcher(file, name) {
    fs.writeFileSync(file, `#!/bin/sh\nprintf '%s|%s|%s\\n' "${name}" "$WS_HOST_SURFACE" "$*" >> "${this.log}"\nf="${this.resp}/${name}__$(printf %s "$*" | tr ' /' '__')"\n[ -f "$f" ] && cat "$f" && exit 0\nexit 2\n`);
    fs.chmodSync(file, 0o755);
  }
  put(name, args, content) { fs.writeFileSync(path.join(this.resp, `${name}__${args.replace(/[ /]/g, "_")}`), typeof content === "string" ? content : JSON.stringify(content) + "\n"); }
  calls() { try { return fs.readFileSync(this.log, "utf8").trim().split("\n").filter(Boolean); } catch (_) { return []; } }
  setup() {
    const list = (name, cmds, aud) => doc(`${name}/command-list@1`, { count: cmds.length, commands: cmds }, [], [], aud);
    this.put("ws-host", "command list --json", list("ws-host", [
      { id: "doctor", category: "check", group: null, surfaces: ["terminal", "editor", "mcp"], help: "Check" },
      { id: "repo set", category: "decision", group: null, surfaces: ["terminal", "editor"], help: "Trust" },
      { id: "kit add", category: "setup", group: null, surfaces: ["terminal"], help: "Install a kit" }], "private"));
    this.put("ws-host", "repo list --json", doc("ws-host/repo-list@1", { plain: "x", repositories: [
      { id: "github.com/acme/site", path: this.repo, cloned: true, trusted: true }, { id: "github.com/evil/x", path: this.other, cloned: true, trusted: false }] }));
    this.put("ws-host", "doctor --json", doc("ws-host/doctor@1", { plain: "Your machine is ready.", checks: [{ name: "python", status: "ok" }] }));
    this.put("ws-host", "auth status --json", doc("ws-host/auth-status@1", { plain: "x", forges: [{ name: "github.com", signed_in: true }] }));
    this.put("acme", "command list --json", list("acme", [{ id: "spec list", category: "read", group: "spec", surfaces: ["terminal", "editor", "mcp"], help: "List specs" }, { id: "check", category: "check", group: "core", surfaces: ["terminal", "editor"], help: "Check" }], "public"));
    this.put("evil", "command list --json", list("evil", [], "public"));
    this.put("ws-host", "command show repo set --json", doc("ws-host/command@1", { id: "repo set", arguments: [{ name: "repo", type: "REPO", required: true, choices: ["github.com/acme/site"] }], options: [{ flag: "--trusted" }, { flag: "--untrusted" }, { flag: "--confirmed" }] }));
    this.put("ws-host", "command show auth new --json", doc("ws-host/command@1", { id: "auth new", arguments: [{ name: "forge", type: "FORGE", required: true, choices: ["github", "gitlab"] }], options: [] }));
    this.put("ws-host", "command show kit add --json", doc("ws-host/command@1", { id: "kit add", arguments: [{ name: "kit", type: "KIT", required: true, choices: ["base", "press"] }], options: [] }));
    this.put("ws-host", "command show doctor --json", doc("ws-host/command@1", { id: "doctor", arguments: [], options: [] }));
    this.put("acme", "command show spec list --json", doc("acme/command@1", { id: "spec list", arguments: [], options: [] }));
    this.put("acme", "command show check --json", doc("acme/command@1", { id: "check", arguments: [], options: [] }));
  }
  done() { process.env.PATH = this.savedPath; fs.rmSync(this.dir, { recursive: true, force: true }); }
}

async function boot(fake, opts = {}) {
  const vscode = makeVscode(Object.assign({ folder: fake.dir }, opts));
  const restore = install(vscode);
  delete require.cache[require.resolve("../../vscode/extension.js")];
  const ext = require("../../vscode/extension.js");
  const ctx = { subscriptions: [] };
  ext.activate(ctx);
  await new Promise(r => setTimeout(r, 1500));      // the first refresh
  return { vscode, ext, restore };
}
const children = async (v, parent) => (await v.calls.treeViews[0].provider.getChildren(parent));
const pick = async (v, orch, noun, cmd) => {
  const top = await children(v);
  const o = top.find(n => n.item.label === orch);
  const nouns = await children(v, o);
  const n = nouns.find(x => x.item.label === noun);
  return (await children(v, n)).find(c => c.item.label === cmd);
};
const select = async (v, node) => { for (const h of v.calls.treeViews[0].selectionHandlers) await h({ selection: [node] }); await new Promise(r => setTimeout(r, 800)); };

test("it finds ws-host and the launchers of trusted repositories only, grouped with their audience", async () => {
  const f = new Fake();
  const { vscode, restore } = await boot(f);
  try {
    const top = await children(vscode);
    assert.deepStrictEqual(top.map(n => [n.item.label, n.item.description]), [["ws-host", "private"], ["acme", "public"]]);
    assert.ok(!f.calls().some(c => c.startsWith("evil")), "an untrusted repository's launcher ran");
    assert.ok(!f.calls().some(c => c.includes("notes")));
    const nouns = (await children(vscode, top[1])).map(n => n.item.label);
    assert.deepStrictEqual(nouns.sort(), ["everything", "spec"]);
    const wsNouns = (await children(vscode, top[0])).map(n => n.item.label);
    assert.ok(!(await Promise.all((await children(vscode, (await children(vscode, top[0])).find(n => n.item.label === "kit") || { kind: "none" })))).length, "a terminal-only command is not in the tree");
    assert.ok(wsNouns.includes("repo"));
  } finally { restore(); f.done(); }
});

test("the status bar shows the doctor's plain first line and everything runs with the editor surface", async () => {
  const f = new Fake();
  const { vscode, restore } = await boot(f);
  try {
    assert.match(vscode.calls.statusBars[0].text, /Your machine is ready\./);
    assert.ok(f.calls().every(c => c.split("|")[1] === "editor"), f.calls().join("\n"));
  } finally { restore(); f.done(); }
});

test("a failing doctor turns the status red; a newer schema says update needed", async () => {
  const f = new Fake();
  f.put("ws-host", "doctor --json", doc("ws-host/doctor@1", { plain: "1 thing needs fixing.", checks: [{ status: "fail" }] }));
  let b = await boot(f);
  try { assert.strictEqual(b.vscode.calls.statusBars[0].backgroundColor.id, "statusBarItem.errorBackground"); } finally { b.restore(); }
  f.put("ws-host", "doctor --json", doc("ws-host/doctor@2", { plain: "future" }));
  b = await boot(f);
  try { assert.match(b.vscode.calls.statusBars[0].text, /Update needed/); assert.match(b.vscode.calls.statusBars[0].tooltip, /update/i); } finally { b.restore(); f.done(); }
});

test("in Restricted Mode nothing runs and the status says why", async () => {
  const f = new Fake();
  const { vscode, restore } = await boot(f, { trusted: false });
  try {
    assert.deepStrictEqual(f.calls(), []);
    assert.match(vscode.calls.statusBars[0].text, /workspace trust/i);
    const top = await children(vscode);
    assert.match(top[0].item.label, /trust/i);
    await vscode.calls.commands.get("wsHost.runChecks")();
    await vscode.calls.commands.get("wsHost.ensure")();
    assert.deepStrictEqual(f.calls(), []);
  } finally { restore(); f.done(); }
});

test("it registers no command that takes an action, a command line or a resource", async () => {
  const f = new Fake();
  const { vscode, restore } = await boot(f);
  try {
    assert.deepStrictEqual([...vscode.calls.commands.keys()].sort(), ["wsHost.ensure", "wsHost.getHelp", "wsHost.learn", "wsHost.refresh", "wsHost.runChecks", "wsHost.showSuggestions", "wsHost.signIn"]);
    const before = f.calls().length;
    for (const [, fn] of vscode.calls.commands) { if (fn.length > 0) assert.fail("a command declares parameters"); }
    // fabricated arguments change nothing: none of them runs a decision
    await vscode.calls.commands.get("wsHost.refresh")({ command: "repo set", category: "decision", fields: { repo: "x" } });
    assert.ok(!f.calls().slice(before).some(c => /\|repo set /.test(c)));
    const package_ = JSON.parse(fs.readFileSync(path.join(__dirname, "../../vscode/package.json"), "utf8"));
    assert.deepStrictEqual(package_.contributes.commands.map(c => c.command).sort(), [...vscode.calls.commands.keys()].sort());
  } finally { restore(); f.done(); }
});

test("declining the modal runs nothing; accepting runs it once, with --confirmed", async () => {
  for (const [answer, runs] of [[undefined, 0], ["Yes, do it", 1]]) {
    const f = new Fake();
    f.put("ws-host", "repo set github.com/acme/site --trusted --confirmed --html", page(doc("ws-host/repo@1", { plain: "You now trust site." })));
    f.put("ws-host", "repo set github.com/acme/site --trusted --html", page(doc("ws-host/repo@1", { plain: "no" })));
    const { vscode, restore } = await boot(f, { answers: { warning: answer, quickPick: "github.com/acme/site" } });
    try {
      // a result page offering the decision, shown by running a command the fake answers with it
      f.put("ws-host", "doctor --html", page(doc("ws-host/doctor@1", { plain: "Look", checks: [] }, [act("Trust site", "repo set", { category: "decision", fields: { repo: "github.com/acme/site", trusted: true }, cli: "ws-host repo set github.com/acme/site --trusted" })])));
      await select(vscode, await pick(vscode, "ws-host", "everything", "doctor"));
      const panel = vscode.calls.panels[0];
      assert.ok(panel, "no panel");
      assert.match(panel.webview.html, /script-src 'nonce-/);
      for (const h of panel.handlers) await h({ type: "action", index: 0 });
      await new Promise(r => setTimeout(r, 800));
      assert.strictEqual(vscode.calls.warnings.length, 1);
      assert.strictEqual(vscode.calls.warnings[0].o.modal, true);
      const ran = f.calls().filter(c => /^ws-host\|editor\|repo set /.test(c));
      assert.strictEqual(ran.length, runs, ran.join("\n"));
      if (runs) { assert.ok(ran[0].includes("--confirmed")); assert.ok(ran[0].startsWith("ws-host|editor|")); }
    } finally { restore(); f.done(); }
  }
});

test("an action the editor does not expose shows its command instead of running", async () => {
  const f = new Fake();
  f.put("ws-host", "doctor --html", page(doc("ws-host/doctor@1", { plain: "Look", checks: [] }, [act("Install base", "kit add", { surfaces: ["terminal"], fields: { kit: "base" }, cli: "ws-host kit add base" })])));
  const { vscode, restore } = await boot(f, { answers: { info: undefined } });
  try {
    await select(vscode, await pick(vscode, "ws-host", "everything", "doctor"));
    const before = f.calls().length;
    for (const h of vscode.calls.panels[0].handlers) await h({ type: "action", index: 0 });
    assert.ok(vscode.calls.messages.some(m => m.msg === "ws-host kit add base" && m.btn.includes("Copy")));
    assert.strictEqual(f.calls().length, before);
  } finally { restore(); f.done(); }
});

test("an action that needs a value asks with a quick-pick and runs nothing if cancelled", async () => {
  const f = new Fake();
  f.put("ws-host", "doctor --html", page(doc("ws-host/doctor@1", { plain: "Look", checks: [] }, [act("Sign in", "auth new", { needs: ["forge"], cli: null })])));
  const { vscode, restore } = await boot(f, { answers: { quickPick: undefined } });
  try {
    await select(vscode, await pick(vscode, "ws-host", "everything", "doctor"));
    const before = f.calls().length;
    vscode.calls.inputs.length = 0;
    for (const h of vscode.calls.panels[0].handlers) await h({ type: "action", index: 0 });
    assert.deepStrictEqual(vscode.calls.inputs[0].items, ["github", "gitlab"]);
    assert.ok(!f.calls().slice(before).some(c => /\|auth new /.test(c)));
  } finally { restore(); f.done(); }
});

test("signing in shows the code and address with Copy code and open browser", async () => {
  const f = new Fake();
  f.put("ws-host", "auth status --json", doc("ws-host/auth-status@1", { plain: "no", forges: [{ name: "github.com", signed_in: false }] }));
  f.put("ws-host", "auth new github --html", page(doc("ws-host/auth-code@1", { plain: "Open it", code: "ABCD-1234", url: "https://github.com/login/device" })) + page(doc("ws-host/auth@1", { plain: "You are signed in to github.com.", signed_in: true })));
  const copy = "Copy code and open browser";
  const { vscode, restore } = await boot(f, { answers: { info: (msg, btn) => (btn.includes("Sign in") ? "Sign in" : btn.includes(copy) ? copy : undefined) } });
  try {
    await new Promise(r => setTimeout(r, 1500));
    assert.deepStrictEqual(vscode.calls.clipboard, ["ABCD-1234"]);
    assert.deepStrictEqual(vscode.calls.opened, ["https://github.com/login/device"]);
    assert.ok(vscode.calls.messages.some(m => /not signed in/.test(m.msg)));
    assert.ok(vscode.calls.progress.some(p => p.reports.some(r => /Open it/.test(r.message))));
  } finally { restore(); f.done(); }
});

test("check findings land in the Problems panel at their file and line", async () => {
  const f = new Fake();
  f.put("acme", "check --json", doc("acme/check@1", { sections: [{ name: "specs", status: "failed", findings: [{ level: "error", where: "spec-kit/a.md:7", message: "bad", next: "edit" }, { level: "warning", where: "spec-kit/b.md:3", message: "meh", next: "edit" }] }] }));
  f.put("ws-host", "check --json", doc("ws-host/check@1", { sections: [] }));
  const { vscode, restore } = await boot(f);
  try {
    await vscode.calls.commands.get("wsHost.runChecks")();
    const d = vscode.calls.diagnostics.get(path.join(f.repo, "spec-kit/a.md"));
    assert.strictEqual(d[0].range.start.line, 6);
    assert.match(d[0].message, /specs: bad/);
    assert.strictEqual(vscode.calls.diagnostics.get(path.join(f.repo, "spec-kit/b.md"))[0].severity, 1);
  } finally { restore(); f.done(); }
});

test("Get help gathers context and doctor, copies the report and shows it", async () => {
  const f = new Fake();
  f.put("ws-host", "context --json", doc("ws-host/context@1", { plain: "report", resource: "machine" }));
  const { vscode, restore } = await boot(f);
  try {
    await vscode.calls.commands.get("wsHost.getHelp")();
    assert.match(vscode.calls.clipboard[0], /Workspace help report/);
    assert.match(vscode.calls.clipboard[0], /"resource": "machine"/);
  } finally { restore(); f.done(); }
});

test("a resource with a newer schema shows update needed, not its content", async () => {
  const f = new Fake();
  f.put("ws-host", "doctor --html", page(doc("ws-host/doctor@7", { plain: "SECRET FUTURE CONTENT" })));
  const { vscode, restore } = await boot(f);
  try {
    await select(vscode, await pick(vscode, "ws-host", "everything", "doctor"));
    const html = vscode.calls.panels[0].webview.html;
    assert.match(html, /Update needed/);
    assert.ok(!html.includes("SECRET FUTURE CONTENT"));
  } finally { restore(); f.done(); }
});

test("Learn lists the topics help offers, and shows the chosen topic as a page with its steps as buttons", async () => {
  const f = new Fake();
  f.put("ws-host", "command list --json", doc("ws-host/command-list@1", { count: 1, commands: [{ id: "help", category: "read", group: null, surfaces: ["terminal", "editor", "mcp"], help: "Learn" }] }));
  f.put("ws-host", "command show help --json", doc("ws-host/command@1", { id: "help", arguments: [{ name: "topic", type: "TOPIC", required: false, choices: ["repos", "start"] }], options: [] }));
  f.put("ws-host", "help repos --html", page(doc("ws-host/help@1", { plain: "Your repositories live in one folder." }, [act("Copy the missing ones", "repo add", { fields: { all: true }, cli: "ws-host repo add --all" })])));
  const { vscode, restore } = await boot(f, { answers: { quickPick: "repos" } });
  try {
    vscode.calls.inputs.length = 0;
    await vscode.calls.commands.get("wsHost.learn")();
    assert.deepStrictEqual(vscode.calls.inputs[0].items, ["repos", "start"]);
    const panel = vscode.calls.panels[0];
    assert.ok(panel, "no page");
    assert.match(panel.title, /Your repositories/);
    assert.match(panel.webview.html, /script-src 'nonce-/);
  } finally { restore(); f.done(); }
});

const sugg = (f) => f.put("ws-host", "doctor --json", doc("ws-host/doctor@1", {
  plain: "Your machine is ready, with 2 suggestions.",
  checks: [
    { name: "git pull setting", status: "warn", detail: "git's Sync button may rewrite your work", action: 0, cli: "ws-host workspace set --pull-ff-only" },
    { name: "launcher", status: "warn", detail: "the launcher is not linked", cli: "curl -fsSL x | sh", todo: "Then open a new terminal window." }],
}, [act("Make git's Sync button safe", "workspace set", { fields: { pull_ff_only: true }, cli: "ws-host workspace set --pull-ff-only" })]));

test("with suggestions the status bar says how many and a click opens them, each with its fix", async () => {
  const f = new Fake();
  sugg(f);
  f.put("ws-host", "command show workspace set --json", doc("ws-host/command@1", { id: "workspace set", arguments: [], options: [{ flag: "--pull-ff-only" }] }));
  f.put("ws-host", "workspace set --pull-ff-only --json", doc("ws-host/workspace@1", { plain: "Git's Sync button now only moves forward." }));
  const { vscode, restore } = await boot(f, { answers: { quickPick: items => items[0], info: msg => (/^git's Sync button/.test(msg) ? "Run: Make git's Sync button safe" : undefined) } });
  try {
    const bar = vscode.calls.statusBars[0];
    assert.strictEqual(bar.text, "$(warning) 2 suggestions — click to fix");
    assert.strictEqual(bar.command, "wsHost.showSuggestions");
    assert.ok(!/below/i.test(bar.text + bar.tooltip));
    const note = vscode.calls.messages[0];                    // shown once, with a way to see them all
    assert.match(note.msg, /2 suggestions for your machine/);
    assert.deepStrictEqual(note.btn, ["Show all"]);
    const before = f.calls().length;
    await vscode.calls.commands.get("wsHost.showSuggestions")();
    const list = vscode.calls.inputs.find(i => i.items);
    assert.deepStrictEqual(list.items.map(i => i.label), ["$(warning) git pull setting", "$(warning) launcher"]);
    assert.match(list.items[0].detail, /Type: ws-host workspace set --pull-ff-only/);
    assert.match(list.items[1].detail, /Type: curl -fsSL x \| sh/);
    const one = vscode.calls.messages.find(m => /^git's Sync button/.test(m.msg));
    assert.deepStrictEqual(one.btn, ["Run: Make git's Sync button safe", "Copy command"]);
    assert.match(one.msg, /Type: ws-host workspace set --pull-ff-only/);
    await new Promise(r => setTimeout(r, 800));
    assert.ok(f.calls().slice(before).some(c => /ws-host\|editor\|workspace set --pull-ff-only/.test(c)), f.calls().slice(before).join("\n"));
  } finally { restore(); f.done(); }
});

test("a suggestion with no command says what the person does themselves, and Copy puts the line on the clipboard", async () => {
  const f = new Fake();
  sugg(f);
  const { vscode, restore } = await boot(f, { answers: { quickPick: items => items[1], info: msg => (/launcher/.test(msg) ? "Copy command" : undefined) } });
  try {
    await vscode.calls.commands.get("wsHost.showSuggestions")();
    const m = vscode.calls.messages.find(x => /the launcher is not linked/.test(x.msg));
    assert.match(m.msg, /Then open a new terminal window\./);
    assert.deepStrictEqual(m.btn, ["Copy command"]);
    assert.strictEqual(vscode.calls.clipboard[vscode.calls.clipboard.length - 1], "curl -fsSL x | sh");
  } finally { restore(); f.done(); }
});

test("one suggestion with a command is notified with Run and Show all", async () => {
  const f = new Fake();
  f.put("ws-host", "doctor --json", doc("ws-host/doctor@1", { plain: "Your machine is ready, with 1 suggestion.",
    checks: [{ name: "git pull setting", status: "warn", detail: "git may rewrite your work", action: 0, cli: "ws-host workspace set --pull-ff-only" }] },
    [act("Make git's Sync button safe", "workspace set", { fields: { pull_ff_only: true }, cli: "ws-host workspace set --pull-ff-only" })]));
  const { vscode, restore } = await boot(f);
  try {
    const note = vscode.calls.messages[0];
    assert.match(note.msg, /One suggestion for your machine: git may rewrite your work/);
    assert.deepStrictEqual(note.btn, ["Run: Make git's Sync button safe", "Show all"]);
  } finally { restore(); f.done(); }
});

test("when all is well a click checks again and says so, and no notification is shown", async () => {
  const f = new Fake();
  const { vscode, restore } = await boot(f);
  try {
    assert.ok(!vscode.calls.messages.some(m => /suggestion/.test(m.msg)));
    const before = f.calls().filter(c => /doctor/.test(c)).length;
    await vscode.calls.commands.get("wsHost.showSuggestions")();
    assert.ok(f.calls().filter(c => /doctor/.test(c)).length > before, "a click re-checks");
    assert.match(vscode.calls.messages[vscode.calls.messages.length - 1].msg, /Your machine is ready\./);
  } finally { restore(); f.done(); }
});
