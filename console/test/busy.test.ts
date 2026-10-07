// Work that is going on is seen to be (0009-workspaces-console FR-063).
import test from 'node:test';
import assert from 'node:assert/strict';
import { Busy } from '../src/services/busy';

function rig() {
  const timers: Array<{ fn: () => void; live: boolean }> = [];
  const shown: Array<{ label: string; ended: boolean; said: string[] }> = [];
  const busy = new Busy({
    later: (_ms, fn) => { const t = { fn, live: true }; timers.push(t); return { dispose: () => { t.live = false; } }; },
    show: (label, done, onSay) => { const s = { label, ended: false, said: [] as string[] }; shown.push(s); void done.then(() => { s.ended = true; }); onSay((p) => s.said.push(p)); },
  });
  return { busy, timers, shown, wait: () => timers.forEach((t) => t.live && t.fn()) };
}
const tick = () => new Promise((r) => setImmediate(r));

test('quick work shows nothing: the wait ends with the work', async () => {
  const r = rig();
  assert.equal(await r.busy.track('Looking', () => Promise.resolve(7)), 7);
  r.wait();
  assert.equal(r.shown.length, 0);
  assert.equal(r.busy.active, 0);
});

test('slow work shows its label and each phrase it says, including one said before the line appeared, and the line ends with the work', async () => {
  const r = rig();
  let finish: (v: string) => void = () => undefined;
  const work = r.busy.track('Looking at your repositories…', (say) => { say('agora'); return new Promise<string>((res) => { finish = res; }); });
  assert.equal(r.busy.active, 1);
  r.wait();
  assert.deepEqual(r.shown.map((s) => s.label), ['Looking at your repositories…']);
  assert.deepEqual(r.shown[0]?.said, ['agora']);
  finish('x'); await work; await tick();
  assert.equal(r.shown[0]?.ended, true);
  assert.equal(r.busy.active, 0);
});

test('work that fails still ends the line and is still counted out, and the failure is the caller\'s', async () => {
  const r = rig();
  const work = r.busy.track('Looking', () => Promise.reject(new Error('no')));
  r.wait();
  await assert.rejects(work, /no/);
  await tick();
  assert.equal(r.shown[0]?.ended, true);
  assert.equal(r.busy.active, 0);
});
