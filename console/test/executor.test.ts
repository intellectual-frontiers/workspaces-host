import test from 'node:test';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import assert from 'node:assert/strict';
import type { Loose } from './support/fake-launcher';
import * as executor from '../src/services/executor';
import { CancelSource } from '../src/services/cancellation';
import { Repository } from '../src/services/repository';
import { makeRepo, secondCommandLine } from './support/fake-launcher';
import { createStub, install } from './support/vscode-stub';

const k = secondCommandLine('other');
const folder = (root: Loose): Loose => ({ name: 'repo', uri: { toString: () => `file://${root}`, fsPath: root } });

const change = { path: 'widgets/w1.txt', change: 'modify', added: 1, removed: 1, diff: ['--- before', '+++ after', '@@ -1 +1 @@', '-old', '+new'] };
const dryDoc = k.doc('widget', 'w1', { dry_run: true, changes: [change] });
const realDoc = k.doc('widget', 'w1', { dry_run: false, changes: [change] }, { actions: [{ label: 'show it', command: 'widget show', fields: { widget: 'w1' }, category: 'read', surfaces: ['editor'], cli: 'other widget show w1', enabled: true }] });
const invalid = { schema: 'other/error@1', audience: 'private', kind: 'error', id: 'invalid-argument', links: [], actions: [],
  data: { code: 'invalid-argument', message: "name: 'bad' is not a valid name", type: 'TEXT', value: 'bad', examples: ['w1', 'w2'] } };

const docs = {
  'command list': { doc: k.list },
  'command show widget approve': { doc: k.detail('widget approve', 'decision', [k.arg('widget', 'WIDGET', { choices: ['w1', 'w2'] })]) },
  'command show widget new': { doc: k.detail('widget new', 'record', [k.arg('name', 'TEXT')]) },
  'command show widget show': { doc: k.detail('widget show', 'read', [k.arg('widget', 'WIDGET')]) },
  'widget approve w1 --dry-run': { doc: dryDoc },
  'widget approve w1': { doc: realDoc },
  'widget new w9': { doc: realDoc },
  'widget new bad': { doc: invalid, exit: 2 },
  'widget new fixed': { doc: realDoc },
  'widget new boom': { doc: k.doc('error', 'boom', { code: 'internal', message: 'it broke' }, { kind: 'error' }), exit: 1 },
  'widget show w1': { doc: k.doc('widget', 'w1', { name: 'w1' }) },
};

async function fixture(answers: Loose) {
  const fake = makeRepo({ docs });
  const repo = new Repository({ source: 'declared', folder: folder(fake.root), root: fake.root, file: fake.file, program: './other', trusted: () => true });
  await repo.load();
  const events: Loose[] = [];
  const ui: Loose = {
    events,
    confirmDecision: async (o: Loose) => { events.push(['confirm', o.detail.id, o.line, o.plain]); return answers.confirm === true; },
    showFailure: async (_r: Loose, _d: Loose, res: Loose) => { events.push(['failure', res.error ? res.error.message : res.failed]); },
    showResult: async (_r: Loose, d: Loose) => { events.push(['result', d.id]); },
    progress: (_title: Loose, fn: Loose) => fn(new CancelSource().token, () => undefined),
    pick: async (o: Loose) => answers.picks.shift()(o), input: async (o: Loose) => answers.inputs.shift()(o), copy: async () => {},
  };
  return { fake, repo, ui, events };
}
const runs = (fake: Loose) => fake.invocations().map((i: Loose) => i.argv.filter((a: Loose) => a !== '--json').join(' '));

test('FR-014: a write that harms nothing anyone else sees runs at once, with its progress, and asks nothing', async () => {
  const { fake, repo, ui, events } = await fixture({});
  const detail = await repo.detail('widget new');
  const out = await executor.runArgv(ui, repo, detail, ['widget', 'new', 'w9']);
  assert.equal(out.ran, true);
  assert.deepEqual(runs(fake).filter((c: Loose) => c.startsWith('widget new')), ['widget new w9'], 'no dry run, no preview');
  assert.deepEqual(events.map((e) => e[0]), ['result'], 'nothing was asked, and the result says what it did');
  fake.cleanup();
});

test('FR-014: a write that fails shows its error', async () => {
  const { fake, repo, ui, events } = await fixture({});
  const out = await executor.runArgv(ui, repo, await repo.detail('widget new'), ['widget', 'new', 'boom']);
  assert.equal(out.ran, false);
  assert.deepEqual(runs(fake).filter((c: Loose) => c.startsWith('widget new')), ['widget new boom']);
  assert.deepEqual(events.find((e) => e[0] === 'failure'), ['failure', 'it broke']);
  fake.cleanup();
});

test('FR-014: a read or a check runs without a dry run', async () => {
  const { fake, repo, ui } = await fixture({});
  await executor.runArgv(ui, repo, await repo.detail('widget show'), ['widget', 'show', 'w1']);
  assert.deepEqual(runs(fake).filter((c: Loose) => c.startsWith('widget show')), ['widget show w1']);
  fake.cleanup();
});

test('FR-015: a decision runs only after the dry run has said in words what it would do and a modal confirmation; refused, it is never run for real', async () => {
  const refused = await fixture({ confirm: false });
  const out = await executor.runArgv(refused.ui, refused.repo, await refused.repo.detail('widget approve'), ['widget', 'approve', 'w1']);
  assert.equal(out.ran, false);
  assert.equal(out.reason, 'decision not confirmed');
  assert.deepEqual(runs(refused.fake).filter((c: Loose) => c.startsWith('widget approve')), ['widget approve w1 --dry-run']);
  assert.deepEqual(refused.events.map((e) => e[0]), ['confirm']);
  assert.equal(refused.events.find((e) => e[0] === 'confirm')[2], './other widget approve w1');
  refused.fake.cleanup();

  const given = await fixture({ confirm: true });
  const ran = await executor.runArgv(given.ui, given.repo, await given.repo.detail('widget approve'), ['widget', 'approve', 'w1']);
  assert.equal(ran.ran, true);
  assert.deepEqual(runs(given.fake).filter((c: Loose) => c.startsWith('widget approve')), ['widget approve w1 --dry-run', 'widget approve w1']);
  given.fake.cleanup();
});

test('FR-015: confirmation must be exactly true; nothing else a caller passes confirms', async () => {
  for (const wrong of ['yes', 1, {}, null]) {
    const f = await fixture({});
    f.ui.confirmDecision = async () => wrong;
    const out = await executor.runArgv(f.ui, f.repo, await f.repo.detail('widget approve'), ['widget', 'approve', 'w1']);
    assert.equal(out.ran, false, `${JSON.stringify(wrong)} must not confirm`);
    f.fake.cleanup();
  }
});

test('FR-015: the module exports no way to run a write or a decision without that path', () => {
  assert.deepEqual(Object.keys(executor).sort(), ['refusedValue', 'runArgv', 'runForm', 'runRead', 'runWrite']);
  // runRead is for reads and checks; runArgv chooses by category, so a decision is never run without its question; the exported runRead is not reachable from any command handler (see never.test.js).
});

test('FR-013: a value the launcher refuses puts the person back at that step with the type\'s message and examples', async () => {
  const prompts: Loose[] = [];
  const picks = [async () => 'run', async () => 'run'];
  const inputs = [async () => 'bad', async (o: Loose) => { prompts.push(o.prompt); return 'fixed'; }];
  const { fake, repo, ui } = await fixture({ picks, inputs });
  const out = await executor.runForm(ui, repo, 'widget new');
  assert.equal(out.ran, true);
  assert.match(prompts[0], /not a valid name/);
  assert.match(prompts[0], /For example: w1, w2/);
  assert.deepEqual(runs(fake).filter((c: Loose) => c.startsWith('widget new')), ['widget new bad', 'widget new fixed']);
  fake.cleanup();
});

test('FR-013: refusedValue maps an invalid-argument error to the argument of that type', () => {
  const d: Loose = { words: ['widget', 'show'], arguments: [{ name: 'widget', type: 'WIDGET' }], options: [{ flag: '--owner', type: 'USER' }] };
  const r = executor.refusedValue(d, { code: 'invalid-argument', type: 'WIDGET', message: 'nope', examples: ['w1'] } as Loose);
  assert.deepEqual(r, { key: 'widget', message: 'nope For example: w1.' });
  assert.equal(executor.refusedValue(d, { code: 'other', type: 'WIDGET', message: 'x' } as Loose), null);
  assert.equal(executor.refusedValue(d, { code: 'invalid-argument', type: 'NOPE', message: 'x' } as Loose), null);
});

test('FR-013: the form ends with the whole command line, one line with no placeholder, before anything runs', async () => {
  const seen: Loose[] = [];
  const picks = [async (o: Loose) => { seen.push(o.placeholder); return 'copy'; }];
  const inputs = [async () => 'w9'];
  const { fake, repo, ui } = await fixture({ picks, inputs });
  const copied: Loose[] = [];
  ui.copy = async (t: Loose) => copied.push(t);
  const out = await executor.runForm(ui, repo, 'widget new');
  assert.equal(out.reason, 'copied');
  assert.deepEqual(seen, ['./other widget new w9']);
  assert.deepEqual(copied, ['./other widget new w9']);
  assert.deepEqual(runs(fake).filter((c: Loose) => c.startsWith('widget new')), []);
  fake.cleanup();
});

test('FR-058: what a build made is offered as buttons that open it or show it in its folder; paths that leave the repository or are not there are never offered', async () => {
  const stub = createStub({});
  const restore = install(stub);
  const { createUi, DiffDocuments } = require('../src/views/ui') as Loose;
  const ui = createUi({ docs: new DiffDocuments(), output: { appendLine() { /* none */ } } });
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'outputs-'));
  fs.mkdirSync(path.join(root, 'build'));
  fs.writeFileSync(path.join(root, 'build', 'Book.pdf'), 'x');
  const real = (outputs: string[]) => ({ doc: { data: { outputs } } });
  const asked = (): Loose[] => stub.calls.messages.filter((m: Loose) => m.kind === 'info');
  stub.script.infos.push('Open');
  await ui.offerOutputs({ root }, real(['build/Book.pdf', '../escape.pdf', '/etc/passwd', 'build/missing.pdf']));
  assert.equal(asked().length, 1);
  assert.match(asked()[0].text, /^Built Book\.pdf\.$/);
  assert.deepEqual(asked()[0].rest, ['Open', 'Show in Folder']);
  await ui.offerOutputs({ root }, real(['../escape.pdf', 'nothing']));
  assert.equal(asked().length, 1, 'nothing real, nothing offered');
  fs.rmSync(root, { recursive: true, force: true });
  restore();
});

test('FR-059: a failure offers the output and a report for help, and one that is a missing prerequisite (exit 3) also offers the one button that installs everything', async () => {
  const stub = createStub({});
  const restore = install(stub);
  const { createUi, DiffDocuments } = require('../src/views/ui') as Loose;
  const ui = createUi({ docs: new DiffDocuments(), output: { appendLine() { /* none */ } }, log: { error() { /* none */ }, info() { /* none */ }, show() { /* none */ } } });
  await ui.showFailure({ program: './x' }, { id: 'check' }, { error: { message: 'nothing is here' }, exit: 3 });
  const one = stub.calls.messages.filter((m: Loose) => m.kind === 'error').at(-1);
  assert.deepEqual(one.rest, ['Install everything', 'Show Output', 'Copy a report for help']);
  await ui.showFailure({ program: './x' }, { id: 'check' }, { error: { message: 'bad value' }, exit: 1 });
  assert.deepEqual(stub.calls.messages.filter((m: Loose) => m.kind === 'error').at(-1).rest, ['Show Output', 'Copy a report for help']);
  restore();
});
