// The welcome page (0009-workspaces-console FR-065): a section for each repository, its words from the command line, help on each, and buttons that are only indexes.
import test from 'node:test';
import assert from 'node:assert/strict';
import { buildWelcome, renderWelcome, esc, type WelcomeRepo } from '../src/model/welcome';

const repo = (o: Partial<WelcomeRepo> = {}): WelcomeRepo => ({ key: 'file:///a', name: 'tool', folder: 'a', summary: 'The tool for things.', state: 'ready', reason: '', needs: 0,
  topics: [{ topic: 'start', summary: 'Begin here.' }, { topic: 'check', summary: 'Prove it works.' }], ...o });
const quiet = { signedOut: false, updates: { waiting: false, plain: '' } };

test('each repository is a section with its own summary, how it stands, and its help topics, and the buttons are indexes into the actions built with them', () => {
  const { model, actions } = buildWelcome({ ...quiet, repos: [repo(), repo({ key: 'file:///b', name: 'other', folder: 'b', needs: 2 })] });
  assert.deepEqual(model.cards.map((c) => [c.name, c.status, c.statusText]), [['tool', 'ok', 'Ready'], ['other', 'warn', '2 things need you']]);
  const card = model.cards[0];
  assert.deepEqual(card?.topics.map((x) => x.label), ['start', 'check']);
  const topic = card?.topics[0];
  assert.deepEqual(actions[topic?.ref ?? -1], { kind: 'topic', repo: 'file:///a', topic: 'start' });
  assert.equal(card?.buttons[0]?.label, 'All help topics');
  assert.deepEqual(actions[card?.buttons[0]?.ref ?? -1], { kind: 'learn', repo: 'file:///a' });
});

test('a repository that is not ready says why in plain words and offers no help it cannot give; one that lacks a program offers to install it', () => {
  const { model, actions } = buildWelcome({ ...quiet, repos: [repo({ state: 'unavailable', reason: 'A program is missing.', summary: '', topics: [] }), repo({ state: 'untrusted' })] });
  assert.equal(model.cards[0]?.summary, 'A program is missing.');
  assert.equal(model.cards[0]?.status, 'bad');
  assert.deepEqual(model.cards[0]?.topics, []);
  assert.deepEqual(actions[model.cards[0]?.buttons[0]?.ref ?? -1], { kind: 'ext', command: 'setUpEverything' });
  assert.equal(model.cards[1]?.statusText, 'Waiting for you to trust this workspace');
  assert.deepEqual(model.cards[1]?.topics, []);
});

test('being signed out, news waiting, and having no repository each say so with the one button that helps', () => {
  const a = buildWelcome({ repos: [], signedOut: true, updates: { waiting: true, plain: 'Updates are ready for x. Bring everything up to date with:  ws-host update' } });
  assert.deepEqual(a.model.notes.map((n) => n.buttons[0]?.label), ['Sign In to GitHub', 'Update Everything']);
  assert.doesNotMatch(a.model.notes[1]?.text ?? '', /ws-host update/, 'no command line in the words');
  assert.deepEqual(a.model.empty?.buttons.map((b) => b.label), ['Add Repository']);
  assert.equal(buildWelcome({ ...quiet, repos: [repo()] }).model.empty, null);
});

test('everything a person or a command line wrote is escaped, and the page names no command of its own', () => {
  const { model } = buildWelcome({ ...quiet, repos: [repo({ name: '<img src=x onerror=alert(1)>', summary: '"quoted" & <b>', topics: [{ topic: '<script>', summary: "it's" }] })] });
  const html = renderWelcome(model);
  assert.doesNotMatch(html, /<img|<script|<b>/);
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.doesNotMatch(html, /command:|href=/, 'no command links and no links at all');
  assert.equal(esc(`<>&"'`), '&lt;&gt;&amp;&quot;&#39;');
});

import { boot } from './support/boot';
import type { Loose } from './support/fake-launcher';

const pages = (b: Loose): Loose[] => b.stub.calls.webviews.filter((w: Loose) => w.id === 'workspaces-console.welcome');

test('FR-065: the page opens by itself at start unless turned off, names each repository, and a message that names no action does nothing', async () => {
  const off = await boot();
  assert.equal(pages(off).length, 0, 'turned off, it does not open');
  off.cleanup();
  const on = await boot({ config: { showWelcomeOnStart: true } });
  const page = pages(on)[0];
  assert.ok(page, 'it opened');
  assert.equal(page.title, 'Welcome');
  assert.match(page.webview.html, /Welcome to Workspaces/);
  assert.match(page.webview.html, /<h2>other<\/h2>/, 'a section for the repository');
  assert.match(page.webview.html, /Content-Security-Policy/);
  await page.onMessage({ ref: 9999 });
  await page.onMessage({ command: 'workbench.action.quit' });
  assert.equal(page.disposed, false);
  on.cleanup();
});
