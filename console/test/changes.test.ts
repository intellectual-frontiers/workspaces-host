// The what-changed page (0009-workspaces-console FR-069): built from the command line's own details, every word escaped, and a button only where it is safe.
import test from 'node:test';
import assert from 'node:assert/strict';
import { boot, defaultDocs, k } from './support/boot';
import type { Loose } from './support/fake-launcher';
import { buildChanges, renderChanges } from '../src/model/changes';

const side = (n: number, o: Loose = {}) => ({ count: n, authors: [{ name: 'Ana', commits: n }], first: '2026-10-01', last: '2026-10-09', areas: [{ name: 'specs/0050', files: 2 }], more: 0,
  commits: Array.from({ length: Math.min(n, 7) }, (_, i) => ({ id: `abc${i}12  Accept ${i}`, author: 'Ana', date: '2026-10-0' + (i + 1), files: 2, text: `Agreed in review ${i}.` })), ...o });
const row = (o: Loose = {}) => ({ id: 'github.com/acme/site', path: '/w/site', cloned: true, dirty: false, ahead: 0, behind: 3, explain: 'Three commits are on the shared branch.', incoming: side(3), outgoing: side(0), same_change_outgoing: 0, same_change_incoming: 0, ...o });

test('a repository that is only behind says what is incoming, with who and why, and offers the update; one that differs the other way offers none', () => {
  const { model, actions } = buildChanges([row(), row({ id: 'github.com/acme/lib', incoming: side(0), outgoing: side(2), ahead: 2, behind: 0 }), row({ id: 'github.com/acme/same', incoming: side(0), outgoing: side(0) })]);
  assert.deepEqual(model.cards.map((c) => [c.name, c.chip]), [['site', '3 commits to bring in'], ['lib', '2 commits not shared yet']]);
  assert.deepEqual(model.same, ['same']);
  const site = model.cards[0];
  assert.deepEqual(site?.buttons.map((b) => b.label), ['Update Now', 'Open Source Control', 'Copy a Report']);
  assert.deepEqual(actions[site?.buttons[0]?.ref ?? -1], { kind: 'sync', id: 'github.com/acme/site' });
  assert.deepEqual(model.cards[1]?.buttons.map((b) => b.label), ['Start Fresh from GitHub…', 'Open Source Control', 'Copy a Report'], 'nothing to bring in, so no update; something only here, so a fresh start is offered');
  assert.equal(site?.incoming?.commits[0]?.subject, 'Accept 0');
  assert.equal(site?.incoming?.commits[0]?.why, 'Agreed in review 0.');
  assert.equal(site?.incoming?.areas, 'specs/0050 (2)');
});

test('when both sides moved on, or something is uncommitted, nothing is moved for the person, the page says why, and rewritten history is named', () => {
  const both = buildChanges([row({ outgoing: side(4), ahead: 4, same_change_outgoing: 3, same_change_incoming: 2 })]).model.cards[0];
  assert.equal(both?.chip, 'Both sides moved on');
  assert.deepEqual(both?.buttons.map((b) => b.label), ['Start Fresh from GitHub…', 'Open Source Control', 'Copy a Report']);
  const fresh = buildChanges([row({ outgoing: side(4), ahead: 4 })]);
  assert.deepEqual(fresh.actions[fresh.model.cards[0]?.buttons[0]?.ref ?? -1], { kind: 'fresh', id: 'github.com/acme/site' });
  assert.match(both?.held ?? '', /will not join them without you/);
  assert.match(both?.rewritten ?? '', /3 of the commits here and 2 of the incoming ones/);
  const dirty = buildChanges([row({ dirty: true })]).model.cards[0];
  assert.deepEqual(dirty?.buttons.map((b) => b.label), ['Start Fresh from GitHub…', 'Open Source Control', 'Copy a Report']);
  assert.match(dirty?.held ?? '', /not committed/);
});

test('the copied report holds the explanation and each commit, and a clean workspace says so', () => {
  const { model, actions } = buildChanges([row()]);
  const copy = actions[model.cards[0]?.buttons[2]?.ref ?? -1];   // update, source control, report
  assert.equal(copy?.kind, 'copy');
  assert.match((copy as Loose).text, /Incoming \(3\):\n {2}abc012 2026-10-01 Ana: Accept 0 — Agreed in review 0\./);
  assert.match(renderChanges(buildChanges([]).model), /Everything matches its shared branch/);
});

test('every word is escaped, the first five commits show and the rest wait behind a native disclosure, and nothing in the page can name a command', () => {
  const html = renderChanges(buildChanges([row({ explain: '<b>x</b>', incoming: side(7, { commits: Array.from({ length: 7 }, (_, i) => ({ id: `h${i}  <script>${i}`, author: '<i>', date: 'd', files: 1, text: '"q" & <u>' })) }) })]).model);
  assert.doesNotMatch(html, /<script>|<b>|<i>|<u>/);
  assert.match(html, /&lt;script&gt;0/);
  assert.equal((html.match(/<li>/g) ?? []).length, 7);
  assert.match(html, /<details><summary>Show 2 more<\/summary>/);
  assert.doesNotMatch(html, /command:|href=/);
});

test('Show What Changed asks the command line that offers repo status, draws what it said, and Ask GitHub Again asks with --fetch', async () => {
  const doc = JSON.parse(JSON.stringify(defaultDocs()['command list'].doc));
  doc.data.commands.push({ id: 'repo status', category: 'read', group: 'g', surfaces: ['terminal', 'editor'], help: 'status' });
  const status = k.doc('repo-status', 'all', { plain: 'x', repositories: [row()] });
  const b = await boot({ docs: defaultDocs({ 'command list': { doc }, 'repo status --details': { doc: status }, 'repo status --details --fetch': { doc: status } }) });
  const registered = b.stub.calls.registered.get('workspaces-console.showChanges');
  await registered();
  const page = b.stub.calls.webviews.find((w: Loose) => w.id === 'workspaces-console.changes');
  assert.ok(page, 'the page opened');
  assert.match(page.webview.html, /Accept 0/);
  assert.match(page.webview.html, /Content-Security-Policy/);
  const again = /data-ref="(\d+)">[^<]*<span[^>]*><\/span>Ask GitHub Again/.exec(page.webview.html);
  await page.onMessage({ ref: Number(again?.[1]) });
  await new Promise((r) => setTimeout(r, 150));
  assert.ok(b.first.invocations().some((i: Loose) => i.argv.join(' ') === 'repo status --details --fetch --json'));
  await page.onMessage({ ref: 9999 });
  assert.equal(page.disposed, false);
  b.cleanup();
});
