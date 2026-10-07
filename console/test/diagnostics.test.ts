import test from 'node:test';
import assert from 'node:assert/strict';
import type { Loose } from './support/fake-launcher';
import { createStub, install, folderOf, Uri } from './support/vscode-stub';

function setup() {
  const stub = createStub({ folders: [folderOf('repo', '/clone')] });
  const restore = install(stub);
  const { Diagnostics, locate } = require('../src/services/diagnostics') as Loose;
  const resolve = async (_folder: Loose, file: Loose) => (file.endsWith('.md') || file.endsWith('.tsv') ? Uri.file(`/clone/${file}`) : null);
  return { stub, restore, Diagnostics, locate, d: new Diagnostics(resolve), folder: stub.vscode.workspace.workspaceFolders[0] };
}

test('FR-009: a finding\'s `where` that names a file is a location, with its line', () => {
  const { restore, locate } = setup();
  assert.deepEqual(locate('docs/guide.md:12'), { file: 'docs/guide.md', line: 12, column: 1 });
  assert.deepEqual(locate('docs/guide.md:12:5'), { file: 'docs/guide.md', line: 12, column: 5 });
  assert.deepEqual(locate('README.md'), { file: 'README.md', line: 1, column: 1 });
  assert.equal(locate('ontology/x.ttl (design system)').file, 'ontology/x.ttl');
  restore();
});

test('FR-009: a finding with no location is not placed at a file it does not name', () => {
  const { restore, locate } = setup();
  for (const w of ['', 'commands', 'spec 0020 FR-001', 'a section name', '(none)']) assert.equal(locate(w), null, w);
  restore();
});

test('FR-009: one diagnostic per located finding, with severity, message and the section as the source', async () => {
  const { restore, d, folder, stub } = setup();
  const unplaced = await d.setSection(folder, 'other', 'docs', [
    { level: 'error', where: 'docs/guide.md:3', message: 'broken link', next: '' },
    { level: 'warning', where: 'docs/guide.md:9', message: 'long line', next: '' },
    { level: 'error', where: 'tools', message: 'a directory, not a file', next: '' },
    { level: 'error', where: 'general', message: 'no location', next: '' }]);
  const got = stub.diagnostics.get(Uri.file('/clone/docs/guide.md').toString());
  assert.equal(got.length, 2);
  assert.equal(got[0].range.start.line, 2);
  assert.equal(got[0].severity, stub.vscode.DiagnosticSeverity.Error);
  assert.equal(got[1].severity, stub.vscode.DiagnosticSeverity.Warning);
  assert.equal(got[0].source, 'other check docs');
  assert.deepEqual(unplaced.map((f: Loose) => f.message), ['a directory, not a file', 'no location']);
  restore();
});

test('FR-009: a section\'s diagnostics are cleared when that section runs again, and only that section\'s', async () => {
  const { restore, d, folder, stub } = setup();
  await d.setSection(folder, 'other', 'docs', [{ level: 'error', where: 'a.md:1', message: 'one', next: '' }]);
  await d.setSection(folder, 'other', 'ledger', [{ level: 'error', where: 'a.md:2', message: 'two', next: '' }]);
  assert.equal(d.count(), 2);
  await d.setSection(folder, 'other', 'docs', []);
  assert.equal(d.count(), 1);
  assert.equal(stub.diagnostics.get(Uri.file('/clone/a.md').toString())[0].message, 'two');
  restore();
});

test('FR-064: a command that failed is one entry in the Problems panel at the file that is run, replaced by the next report and gone when it works', () => {
  const { restore, d, folder, stub } = setup();
  const file = Uri.file('/clone/tool');
  d.setProblem(folder, 'command:build book', file, 'it broke', 'error', 'tool build book', 'missing-toolchain');
  const first = stub.diagnostics.get(file.toString());
  assert.equal(first.length, 1);
  assert.equal(first[0].message, 'it broke');
  assert.equal(first[0].source, 'tool build book');
  assert.equal(first[0].code, 'missing-toolchain');
  assert.equal(first[0].severity, 0, 'an error');
  d.setProblem(folder, 'command:build book', file, 'it broke again', 'error', 'tool build book');
  assert.equal(stub.diagnostics.get(file.toString()).length, 1, 'the same key replaces, it does not pile up');
  d.setProblem(folder, 'load', file, 'newer reading needed', 'warning', 'tool');
  assert.equal(stub.diagnostics.get(file.toString()).length, 2);
  d.clearProblem(folder, 'command:build book');
  assert.deepEqual(stub.diagnostics.get(file.toString()).map((x: Loose) => x.message), ['newer reading needed']);
  d.clearProblem(folder, 'load');
  assert.equal(stub.diagnostics.get(file.toString()), undefined);
  restore();
});

test('FR-066: a problem\'s fixes are found by its source and words, and the provider offers each as a quick fix on that diagnostic', () => {
  const { restore, d, folder, stub } = setup();
  const { ProblemFixes } = require('../src/views/fixes') as Loose;
  const { fixesForFailure, fixesForLoad } = require('../src/model/fixes') as Loose;
  const file = Uri.file('/clone/tool');
  d.setProblem(folder, 'command:build', file, 'a program is missing', 'error', 'tool build', 'missing', fixesForFailure(3));
  d.setProblem(folder, 'other', file, 'unrelated', 'error', 'tool other', undefined, []);
  const shown = stub.diagnostics.get(file.toString());
  const mine = shown.find((x: Loose) => x.message === 'a program is missing');
  const actions = new ProblemFixes(d).provideCodeActions({}, {}, { diagnostics: [mine, shown.find((x: Loose) => x.message === 'unrelated')] });
  assert.deepEqual(actions.map((a: Loose) => a.title), ['Install Everything', 'Show Output', 'Copy a Report for Help']);
  assert.equal(actions[0].isPreferred, true);
  assert.equal(actions[0].command.command, 'workspaces-console.setUpEverything');
  assert.equal(actions[1].isPreferred, false);
  assert.deepEqual(fixesForFailure(1).map((f: Loose) => f.title), ['Show Output', 'Copy a Report for Help'], 'only a missing prerequisite offers the install');
  assert.deepEqual(fixesForLoad({ missing: false, needsProvider: true, state: 'unavailable' }).map((f: Loose) => f.command)[0], 'workspaces-console.trust');
  assert.equal(fixesForLoad({ missing: false, needsProvider: false, state: 'update' })[0].command, 'workbench.extensions.action.checkForUpdates');
  restore();
});
