import test from 'node:test';
import assert from 'node:assert/strict';
import { Services, type ServiceDeps } from '../src/services/services';
import { CancelSource } from '../src/services/cancellation';

type Loose = any;

/** A repository whose launcher answers as the test says: the commands it was asked, and what each does. */
function repo(behave: (words: string[], o: Loose) => Promise<Loose>) {
  const asked: string[] = [];
  return { asked, key: 'file:///tool', list: { presentation: { services: [{ id: 'website', title: 'Website on this computer', icon: 'globe', command: 'site serve', prepare: 'site build', description: 'Shows the site.' }] } },
    launcher: { run: (words: string[], o: Loose) => { asked.push(words.join(' ')); return behave(words, o); } } } as Loose;
}

const deps = (r: Loose, said: string[] = []): { d: ServiceDeps; opened: string[]; said: string[]; changes: () => number } => {
  const opened: string[] = [];
  let changes = 0;
  return { opened, said, changes: () => changes, d: { repos: () => [r], log: () => undefined, changed: () => { changes += 1; },
    notify: (m: string) => { said.push(m); return Promise.resolve(undefined); }, openExternal: (u: string) => { opened.push(u); return Promise.resolve(); },
    busy: (_t: string, fn: () => Promise<unknown>) => fn() as Promise<never> } };
};

const upDoc = { schema: 'x/service@1', kind: 'service', id: 'site serve', audience: 'x', data: { url: 'http://127.0.0.1:8790/', plain: 'up' }, links: [], actions: [] };
const result = (o: Loose = {}) => ({ exit: 0, stdout: '', stderr: '', docs: [], doc: null, error: null, cancelled: false, failed: null, ...o });

test('a declared service starts through its launcher, is running once its first line says where it answers, and stops when asked', async () => {
  let finish: (r: Loose) => void = () => undefined;
  const r = repo((_w, o) => new Promise((resolve) => { finish = resolve; o.onDocument(upDoc); o.token.onCancellationRequested(() => resolve(result({ exit: null, cancelled: true }))); }));
  const { d, said } = deps(r);
  const s = new Services(d);
  const key = s.list()[0].key;
  assert.equal(s.list()[0].state, 'stopped');
  const started = s.start(key);
  await new Promise((x) => setTimeout(x, 5));
  assert.equal(s.get(key)?.state, 'running');
  assert.equal(s.get(key)?.url, 'http://127.0.0.1:8790/');
  assert.deepEqual(r.asked, ['site serve']);
  assert.match(said[0] ?? '', /is running at http:\/\/127.0.0.1:8790\//);
  s.stop(key);
  await started;
  assert.equal(s.get(key)?.state, 'stopped');
  void finish;
});

test('opening a running service opens its address, and a service that is not running opens nothing', async () => {
  const r = repo((_w, o) => new Promise((resolve) => { o.onDocument(upDoc); o.token.onCancellationRequested(() => resolve(result({ cancelled: true }))); }));
  const { d, opened } = deps(r);
  const s = new Services(d);
  const key = s.list()[0].key;
  await s.open(key);
  assert.deepEqual(opened, []);
  const p = s.start(key);
  await new Promise((x) => setTimeout(x, 5));
  await s.open(key);
  assert.deepEqual(opened, ['http://127.0.0.1:8790/']);
  s.stopAll();
  await p;
});

test('a service that stops before it is up is built once and started again; a second failure says why in plain words', async () => {
  let served = 0;
  const r = repo((w, o) => {
    if (w.join(' ') === 'site build') return Promise.resolve(result());
    served += 1;
    if (served === 1) return Promise.resolve(result({ exit: 1, doc: { data: { plain: 'the website is not built yet' } } }));
    o.onDocument(upDoc);
    return new Promise((resolve) => { o.token.onCancellationRequested(() => resolve(result({ cancelled: true }))); });
  });
  const { d } = deps(r);
  const s = new Services(d);
  const key = s.list()[0].key;
  const p = s.start(key);
  await new Promise((x) => setTimeout(x, 20));
  assert.deepEqual(r.asked, ['site serve', 'site build', 'site serve']);
  assert.equal(s.get(key)?.state, 'running');
  s.stopAll();
  await p;

  const bad = repo(() => Promise.resolve(result({ exit: 1, doc: { data: { plain: 'port 8790 is in use' } } })));
  const again = deps(bad);
  const t = new Services(again.d);
  await t.start(t.list()[0].key);
  assert.equal(bad.asked.join(','), 'site serve,site build');      // it built once, and the build itself failed: no second try
  assert.equal(t.list()[0].state, 'failed');
  assert.match(t.list()[0].plain, /port 8790 is in use/);
  assert.match(again.said.at(-1) ?? '', /did not start: port 8790 is in use/);
});

test('a command line that declares no services has none, and starting an unknown one does nothing', async () => {
  const r = { key: 'k', list: { presentation: { services: [] } }, launcher: { run: () => { throw new Error('never'); } } } as Loose;
  const s = new Services(deps(r).d);
  assert.deepEqual(s.list(), []);
  await s.start('nothing');
});

void CancelSource;
