// Work that goes on without the person having asked for it just now (looking at the repositories, reading what each says about itself) must be seen to be
// going on (0009-workspaces-console FR-063): after a short wait, so that quick work flickers nothing, a status line says what is being done, and it ends
// with the work, whatever the work's end. The extension keeps no state of it.

export interface BusyDeps {
  /** Show that `label` is going on until `done` settles; `onSay` gives the shower a function that is called with each newer, more exact phrase. */
  show(label: string, done: Promise<void>, onSay: (say: (phrase: string) => void) => void): void;
  /** Call `fn` once after `ms`; the call returns what cancels it. */
  later(ms: number, fn: () => void): { dispose(): void };
}

export const SHOW_AFTER_MS = 600;

export class Busy {
  private count = 0;

  constructor(private readonly deps: BusyDeps, private readonly after = SHOW_AFTER_MS) {}

  /** How many pieces of work are going on now. */
  get active(): number { return this.count; }

  /** Run `fn`; if it takes longer than a moment, show `label` (and each phrase `fn` says) until it ends, however it ends. */
  async track<T>(label: string, fn: (say: (phrase: string) => void) => Promise<T>): Promise<T> {
    this.count += 1;
    let finish: () => void = () => undefined;
    const done = new Promise<void>((resolve) => { finish = resolve; });
    let say: (phrase: string) => void = () => undefined;
    let last = '';
    let over = false;
    const timer = this.deps.later(this.after, () => {
      if (over) return;
      this.deps.show(label, done, (f) => { say = f; if (last) f(last); });
    });
    try {
      return await fn((phrase) => { last = phrase; say(phrase); });
    } finally {
      over = true;
      timer.dispose();
      this.count -= 1;
      finish();
    }
  }
}
