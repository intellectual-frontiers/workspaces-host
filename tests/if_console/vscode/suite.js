'use strict';
// ws-host in a real VS Code, served by the Workspaces Console (0001-ws-host FR-018, 0004-editor-extension FR-027). It needs nothing but
// the public root's runner, which names this directory and the ws-host clone as a workspace folder called ws-host.
const assert = require('assert');
const cp = require('child_process');
const path = require('path');
const vscode = require('vscode');

const support = require(path.join(process.env.IF_CONSOLE_EXTENSION_DIR, 'test', 'vscode', 'suite', 'support'));
const { test } = require(path.join(process.env.IF_CONSOLE_EXTENSION_DIR, 'test', 'vscode', 'suite', 'harness'));
const { hook, waitFor } = support;

// The Console's runner names the clone under test `real`; this repository is that clone.
const FOLDER = 'real';
const root = () => process.env.IF_CONSOLE_REAL_ROOT;
// What ws-host itself says, run as the test's own reference and never through the extension.
const ws = (...argv) => JSON.parse(cp.execFileSync(path.join(root(), 'ws-host'), [...argv, '--json'], { cwd: root(), encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 }).trim().split('\n').pop());
const entry = (view, folder) => view.find((e) => e.description.startsWith(folder));
const labels = (e) => e.children.map((c) => c.label);
const ALL = (e) => e.children.flatMap((c) => [c, ...(c.children ? ALL(c) : [])]);

test('the Workspaces Console finds ws-host by its .if-console.env and reads what it says about itself', async () => {
  const ext = vscode.extensions.getExtension('intellectual-frontiers.workspaces-console');
  assert.ok(ext, 'VS Code loaded the Workspaces Console');
  await ext.activate();
  const snap = await waitFor(async () => { const s = await hook().describe(); return s.repositories.find((r) => r.folder === FOLDER && r.state === 'ready') ? s : null; }, 'ws-host to be ready');
  const me = snap.repositories.find((r) => r.folder === FOLDER);
  assert.strictEqual(me.name, 'ws-host', 'its name is the one its documents state');
  assert.strictEqual(me.audience, 'private', 'what it reports is about one person\'s machine');
});

test('the views ws-host asks for are planned, in the order it asks', async () => {
  const snap = await hook().describe({ rows: true });
  const declared = ws('command', 'list').data.presentation.views;
  const slots = snap.views.slots.filter((v) => declared.some((d) => d.title === v.title));
  assert.deepStrictEqual(slots.map((v) => v.title), declared.map((d) => d.title));
  assert.deepStrictEqual(declared.map((d) => d.title), ['Workspace', 'Kits', 'Setup']);
});

test('the Workspace view holds the repository list with a status for each, and the Kits view the kits', async () => {
  const snap = await hook().describe({ rows: true });
  const workspace = snap.views.slots.find((v) => v.title === 'Workspace');
  assert.deepStrictEqual(workspace.entries.map((n) => n.label), ['Repository', 'Workspace']);
  const repos = ws('repo', 'list').data.repositories;
  const repo = workspace.entries.find((n) => n.label === 'Repository');
  assert.deepStrictEqual(repo.children.map((r) => r.label), repos.map((r) => r.id));
  for (const [i, row] of repo.children.entries()) {
    assert.strictEqual(row.status, repos[i].status === 'ok' ? 'testing.iconPassed' : 'testing.iconQueued', `${row.label} is ${repos[i].status}`);
  }
  const kits = snap.views.slots.find((v) => v.title === 'Kits');
  const kit = kits.entries.find((n) => n.label === 'Kit');
  const list = ws('kit', 'list').data.kits;
  assert.deepStrictEqual(kit.children.map((r) => r.label), list.map((k) => k.name));
  for (const row of kit.children) assert.ok(['testing.iconPassed', 'list.warningForeground'].includes(row.status), `${row.label}: ${row.status}`);
});

test('every command the editor offers is titled by ws-host, and All commands lists its nouns and repository-wide commands', async () => {
  const snap = await hook().describe({ rows: true });
  const commands = entry(snap.views.commands, FOLDER);
  assert.ok(commands, 'ws-host is in All commands');
  const want = ws('command', 'list').data.commands.filter((c) => c.surfaces.includes('editor'));
  for (const c of want) assert.ok(c.title, `${c.id} has a title`);
  const nouns = [...new Set(want.filter((c) => c.noun).map((c) => c.noun))];
  for (const noun of nouns) assert.ok(labels(commands).includes(noun), `the noun ${noun} is listed`);
  const wide = commands.children.find((c) => c.label === 'Repository-wide').children.map((c) => c.label);
  for (const id of ['doctor', 'help', 'update', 'check']) assert.ok(wide.includes(id), `${id} is repository-wide`);
});

test('what needs a person is on Home with the exact line that fixes it, from doctor\'s own actions', async () => {
  const doctor = ws('doctor');
  const fixes = (doctor.actions || []).filter((a) => a.enabled !== false && a.cli).map((a) => a.cli);
  const snap = await hook().describe({ rows: true });
  const home = entry(snap.views.home, FOLDER);
  // With one command line in the window Home lists what needs a person directly; with several it groups them by repository.
  const rows = home ? ALL(home) : snap.views.home.flatMap((e) => [e, ...(e.children ? ALL(e) : [])]);
  const lines = rows.map((r) => r.description);
  for (const cli of fixes) assert.ok(lines.includes(cli), `Home shows ${cli}`);
  for (const c of doctor.data.checks.filter((k) => k.status === 'warn' || k.status === 'fail')) {
    assert.ok(c.action !== undefined || c.cli || c.todo, `${c.name} is actionable`);
  }
});

test('ws-host runs with the editor as its surface, and nothing it was asked is a decision run without a modal', async () => {
  const snap = await hook().describe();
  assert.ok(snap.status.text.length > 0, 'the status bar says how things are');
  const decisions = ws('command', 'list').data.commands.filter((c) => c.category === 'decision');
  assert.deepStrictEqual(decisions.map((c) => c.id), ['release publish', 'repo set']);
  assert.ok(decisions[0].surfaces.includes('editor') && !decisions[0].surfaces.includes('mcp'), 'a decision is never offered over MCP');
});
