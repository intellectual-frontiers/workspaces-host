import test from 'node:test';
import assert from 'node:assert/strict';
import type { Loose } from './support/fake-launcher';
import { createStub, install } from './support/vscode-stub';

function load() {
  const stub = createStub({});
  const restore = install(stub);
  const { StartCommands } = require('../src/commands/start') as Loose;
  return { stub, StartCommands, done: restore };
}

test('FR-055: Add Repository asks for an address, runs the command line that offers repo add, and the repositories that arrived join the window', async () => {
  const t = load();
  const asked: string[][] = [];
  let refreshed = 0;
  const app = { repos: [{ has: (c: string) => c === 'repo add' || c === 'repo' }], refresh: () => { refreshed += 1; return Promise.resolve([]); } };
  const run = { runWords: (_r: Loose, words: string[]) => { asked.push(words); return Promise.resolve({ ran: true, real: { doc: { data: { repositories: [{ path: '/w/github.com/o/a' }, { path: '/w/github.com/o/b' }] } } } }); } };
  t.stub.script.inputs.push('github.com/o/a');
  await new t.StartCommands(app, run).addRepository();
  assert.deepEqual(asked, [['repo', 'add', 'github.com/o/a']]);
  assert.equal(refreshed, 1);
  assert.deepEqual((t.stub.calls as Loose).folderChanges.at(-1).add, ['/w/github.com/o/a', '/w/github.com/o/b']);
  t.done();
});

test('FR-055: an address that is not host/organization/repository is refused where it is typed, and nothing runs without an answer', async () => {
  const t = load();
  const app = { repos: [{ has: () => true }], refresh: () => Promise.resolve([]) };
  const run = { runWords: () => { throw new Error('never'); } };
  const check = (v: string) => { let said: unknown; t.stub.script.inputs.push((opts: Loose) => { said = opts.validateInput(v); return undefined; }); return new t.StartCommands(app, run).addRepository().then(() => said); };
  assert.equal(await check('github.com/o/a'), undefined);
  assert.match(String(await check('not an address')), /host\/organization\/repository/);
  t.done();
});

test('FR-055: with no command line that offers the command, a person is told what to do instead of nothing happening', async () => {
  const t = load();
  const app = { repos: [], refresh: () => Promise.resolve([]) };
  await new t.StartCommands(app, { runWords: () => { throw new Error('never'); } }).signIn();
  assert.ok(t.stub.calls.messages.some((m: Loose) => /ws-host auth new github/.test(String(m.text))));
  t.done();
});
