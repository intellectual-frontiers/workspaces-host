// The hourly look for news (0009-workspaces-console FR-061).
import test from 'node:test';
import assert from 'node:assert/strict';
import { Updates, FIRST_LOOK_MS, LOOK_EVERY_MS, type UpdatesDeps, type Waiting } from '../src/services/updates';

function rig(answers: Array<Waiting | null>, busy = false) {
  const said: string[] = [];
  const timers: Array<{ ms: number; fn: () => void; live: boolean }> = [];
  let changes = 0, updated = 0, pick: string | undefined;
  const deps: UpdatesDeps = {
    look: () => Promise.resolve(answers.shift() ?? null),
    notify: (m, buttons) => { said.push(`${m} [${buttons.join('|')}]`); return Promise.resolve(pick); },
    bringCurrent: () => { updated += 1; }, changed: () => { changes += 1; }, busy: () => busy,
    later: (ms, fn) => { const t = { ms, fn, live: true }; timers.push(t); return { dispose: () => { t.live = false; } }; },
  };
  return { u: new Updates(deps), said, timers, changes: () => changes, updated: () => updated, choose: (p: string | undefined) => { pick = p; } };
}
const flush = () => new Promise((r) => setImmediate(r));
const news = { waiting: true, plain: 'Updates are ready for ws-host, site. Bring everything up to date with:  ws-host update' };

test('the first look comes soon, not at once, and then one comes every hour', async () => {
  const r = rig([news, news]);
  r.u.start();
  assert.deepEqual(r.timers.map((t) => t.ms), [FIRST_LOOK_MS]);
  r.timers[0]?.fn(); await flush();
  assert.equal(r.timers.length, 2);
  assert.equal(r.timers[1]?.ms, LOOK_EVERY_MS);
});

test('news is told once, in plain words without the command line, and not again while it is the same news', async () => {
  const r = rig([news, news]);
  await r.u.look(); await r.u.look();
  assert.deepEqual(r.said, ['Updates are ready for ws-host, site. [Update Everything|Later]']);
  assert.equal(r.changes(), 1);
  assert.equal(r.u.current.waiting, true);
});

test('pressing the button runs the update; Later and a closed notice do nothing', async () => {
  const a = rig([news]); a.choose('Update Everything'); await a.u.look(); await flush();
  assert.equal(a.updated(), 1);
  const b = rig([news]); b.choose('Later'); await b.u.look(); await flush();
  assert.equal(b.updated(), 0);
});

test('new news after the old was dealt with is told again; a look that could not be made says nothing and changes nothing', async () => {
  const r = rig([news, null, { waiting: false, plain: 'Everything is up to date.' }, news]);
  await r.u.look(); await r.u.look();
  assert.equal(r.u.current.waiting, true, 'a failed look leaves what was known');
  await r.u.look(); assert.equal(r.u.current.waiting, false);
  await r.u.look();
  assert.equal(r.said.length, 2);
});

test('a look waits while a command runs, and stopping ends the timer', async () => {
  const r = rig([news], true);
  await r.u.look();
  assert.equal(r.said.length, 0);
  r.u.start(); r.u.stop();
  assert.equal(r.timers[0]?.live, false);
});
