"use strict";
const test = require("node:test");
const assert = require("node:assert");
const path = require("path");
const { _test: t } = require("../../vscode/extension.js");

test("schema strings are read as <name>/<kind>@<n>", () => {
  assert.deepStrictEqual(t.parseSchema("ws-host/doctor@1"), { name: "ws-host", kind: "doctor", version: 1 });
  assert.strictEqual(t.parseSchema("nonsense"), null);
});

test("a newer schema says an update is needed, in plain words, and shows nothing it cannot read", () => {
  assert.strictEqual(t.readability({ schema: "x/y@1" }).ok, true);
  const r = t.readability({ schema: "x/y@2" });
  assert.deepStrictEqual([r.ok, r.reason], [false, "update-needed"]);
  assert.match(t.UPDATE_NEEDED, /update/i);
  assert.strictEqual(t.readability({}).ok, false);
});

test("buildArgv puts positional arguments in declared order, then options by flag", () => {
  const info = { arguments: [{ name: "kit" }], options: [{ flag: "--host" }, { flag: "--all" }] };
  assert.deepStrictEqual(t.buildArgv(info, { command: "auth new", fields: { forge: "github", host: "git.x" } }, {}),
    ["auth", "new", "--forge", "github", "--host", "git.x"]);
  const info2 = { arguments: [{ name: "forge" }], options: [{ flag: "--host" }] };
  assert.deepStrictEqual(t.buildArgv(info2, { command: "auth new", fields: { forge: "github", host: "git.x" } }, {}), ["auth", "new", "github", "--host", "git.x"]);
  assert.deepStrictEqual(t.buildArgv({ arguments: [], options: [{ flag: "--all" }] }, { command: "repo add", fields: { all: true } }, {}), ["repo", "add", "--all"]);
  assert.deepStrictEqual(t.buildArgv({ arguments: [{ name: "words", many: true }] }, { command: "command show", fields: { words: ["repo", "list"] } }, {}), ["command", "show", "repo", "list"]);
  assert.deepStrictEqual(t.buildArgv({ arguments: [], options: [] }, { command: "repo set", fields: {} }, { confirmed: true }), ["repo", "set", "--confirmed"]);
});

test("missingArgs asks for what the action needs and required arguments without a value", () => {
  const info = { arguments: [{ name: "kit", required: true, type: "KIT", choices: ["base"] }, { name: "x", required: false }] };
  assert.deepStrictEqual(t.missingArgs(info, { fields: {} }).map(a => a.name), ["kit"]);
  assert.deepStrictEqual(t.missingArgs(info, { fields: { kit: "base" } }), []);
  assert.deepStrictEqual(t.missingArgs(info, { fields: {}, needs: ["x"] }).map(a => a.name).sort(), ["kit", "x"]);
});

test("only an action the editor exposes is a button; others are disabled with a reason and a command to show", () => {
  const c = t.classifyAction({ surfaces: ["terminal"], category: "setup", cli: "ws-host kit add base", enabled: true });
  assert.deepStrictEqual([c.button, c.decision, c.showCommand], [false, false, true]);
  assert.match(c.reason, /terminal/);
  assert.strictEqual(t.classifyAction({ surfaces: ["terminal", "editor"], category: "decision", cli: null, enabled: true }).decision, true);
  const off = t.classifyAction({ surfaces: ["editor"], enabled: false, reason: "nothing to do", cli: "x" });
  assert.deepStrictEqual([off.button, off.reason], [false, "nothing to do"]);
});

test("status is plain language and green, amber or red from the doctor", () => {
  const doc = (checks, plain) => ({ schema: "ws-host/doctor@1", data: { plain, checks } });
  assert.strictEqual(t.statusFor(doc([{ status: "ok" }], "Your machine is ready.")).level, "ok");
  assert.strictEqual(t.statusFor(doc([{ status: "warn" }], "There is 1 suggestion.")).level, "warn");
  const bad = t.statusFor(doc([{ status: "fail" }], "1 thing needs fixing."));
  assert.deepStrictEqual([bad.level, bad.text.includes("1 thing needs fixing.")], ["error", true]);
  assert.strictEqual(t.statusFor({ schema: "ws-host/doctor@9", data: {} }).level, "warn");
});

test("a finding is placed at its file and line, or at the repository", () => {
  const root = "/repo";
  assert.deepStrictEqual(t.parseFinding({ where: "src/a.py:12", message: "m", level: "error" }, root), { file: path.join(root, "src/a.py"), line: 11, message: "m", level: "error" });
  assert.strictEqual(t.parseFinding({ where: "spec-kit/enforcement.tsv:15", message: "m" }, root).line, 14);
  assert.strictEqual(t.parseFinding({ where: "registry", message: "m" }, root).file, root);
  assert.strictEqual(t.parseFinding({ where: "a file with spaces: x", message: "m", level: "warning" }, root).level, "warning");
});

test("the webview policy allows only a nonce'd script and no remote resource", () => {
  const html = '<!doctype html><html><head><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"></head><body>x</body></html>';
  const out = t.wrapHtml(html, "N0NCE");
  assert.match(out, /script-src 'nonce-N0NCE'/);
  assert.match(out, /default-src 'none'/);
  assert.strictEqual((out.match(/<script/g) || []).length, 1);
  assert.ok(!/https?:\/\//.test(out.replace(/<script[\s\S]*<\/script>/, "")));
  assert.match(t.wrapHtml("<html><head></head><body></body></html>", "Z"), /Content-Security-Policy/);
});

test("pages stream one at a time and each carries its resource", () => {
  const page = (n) => `<!doctype html><html><head></head><body data-resource="${JSON.stringify({ schema: "a/b@1", n }).replace(/"/g, "&quot;")}">p${n}</body></html>`;
  const got = [];
  const s = new t.PageSplitter(h => got.push(t.resourceOfPage(h)));
  const all = page(1) + "\n" + page(2) + "\n" + page(3);
  s.push(all.slice(0, 50)); s.push(all.slice(50, 200)); s.push(all.slice(200));
  assert.strictEqual(got.length, 2);       // the last page is complete only when the stream ends
  s.end();
  assert.deepStrictEqual(got.map(r => r.n), [1, 2, 3]);
  assert.strictEqual(t.resourceOfPage("<body>none</body>"), null);
});

test("ndjson lines are split across chunks", () => {
  const got = [];
  const s = new t.LineSplitter(l => got.push(l));
  s.push('{"a":1}\n{"b"'); s.push(':2}\n'); s.push("tail");
  s.end();
  assert.deepStrictEqual(got, ['{"a":1}', '{"b":2}', "tail"]);
});

test("the help report holds only what ws-host gave it", () => {
  const r = t.helpReport({ data: { resource: "machine" } }, { data: { plain: "ok" } });
  assert.match(r, /Workspace help report/);
  assert.match(r, /"resource": "machine"/);
});

test("surfaces: the editor must be named", () => {
  assert.strictEqual(t.surfaceExposed(["terminal", "editor"]), true);
  assert.strictEqual(t.surfaceExposed(["terminal"]), false);
  assert.strictEqual(t.surfaceExposed(undefined), false);
});
