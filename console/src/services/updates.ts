// Telling a person that newer code waits (0009-workspaces-console FR-061): the extension asks the command line, once soon after it starts and then once an
// hour while the window is open, whether anything is new, and says so where it is seen. The question is a read-only look; nothing is changed until the person
// presses the button, and the extension keeps nothing between windows: what it has told this window lives only in this window.
import { t } from '../l10n';

export interface Waiting { waiting: boolean; plain: string }

export interface UpdatesDeps {
  /** One quiet look through the command line's own read command; null when it could not be made (no network, no command line, a failure). */
  look(): Promise<Waiting | null>;
  /** Tell the person, with buttons; resolves the button chosen. */
  notify(message: string, buttons: string[]): Promise<string | undefined>;
  /** Run the one command that brings everything current. */
  bringCurrent(): void;
  /** What shows the news (the status bar, Home) follows. */
  changed(): void;
  /** Call `fn` once after `ms`; the call returns what cancels it. */
  later(ms: number, fn: () => void): { dispose(): void };
  /** Whether a command is being run just now, in which case the look waits for the next time. */
  busy(): boolean;
}

export const FIRST_LOOK_MS = 30_000;
export const LOOK_EVERY_MS = 60 * 60 * 1000;

export class Updates {
  private news: Waiting = { waiting: false, plain: '' };
  private told = '';
  private timer: { dispose(): void } | null = null;
  private stopped = false;

  constructor(private readonly deps: UpdatesDeps) {}

  /** What the last look found. */
  get current(): Waiting { return this.news; }

  /** Begin looking: soon, so that the window's own start is not slowed, and then every hour. */
  start(): void {
    this.stopped = false;
    this.schedule(FIRST_LOOK_MS);
  }

  stop(): void { this.stopped = true; this.timer?.dispose(); this.timer = null; }

  private schedule(ms: number): void {
    this.timer?.dispose();
    this.timer = this.stopped ? null : this.deps.later(ms, () => { void this.look().finally(() => this.schedule(LOOK_EVERY_MS)); });
  }

  /** Look now. A look that cannot be made leaves what is known as it was, and says nothing. */
  async look(): Promise<void> {
    if (this.deps.busy()) return;
    const found = await this.deps.look().catch(() => null);
    if (found === null || this.stopped) return;
    const changed = found.waiting !== this.news.waiting || found.plain !== this.news.plain;
    this.news = found;
    if (changed) this.deps.changed();
    if (!found.waiting) { this.told = ''; return; }
    if (this.told === found.plain) return;
    this.told = found.plain;
    void this.deps.notify(found.plain.replace(/\s+Update it with:.*$|\s+Bring everything up to date with:.*$/, ''), [t('Update Everything'), t('Later')]).then((pick) => { if (pick === t('Update Everything')) this.deps.bringCurrent(); });
  }
}
