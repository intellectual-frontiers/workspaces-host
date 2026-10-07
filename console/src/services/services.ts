// The commands that go on running, which a command line declares as services (0041-command-line FR-064, 0009-workspaces-console FR-053): the website shown on
// this computer, say. The extension starts one through the command line's own launcher, learns from its first line where it answers, offers to open
// it, and ends it when a person stops it or the window closes. It starts no program of its own, and nothing it starts outlives the window.
import type { ServiceDecl } from '../model/presentation';
import { CancelSource } from './cancellation';
import type { RunResult } from './launcher';
import type { Repository } from './repository';
import { t } from '../l10n';

export type ServiceState = 'stopped' | 'starting' | 'building' | 'running' | 'failed';

export interface ServiceInfo {
  key: string;
  repo: Repository;
  decl: ServiceDecl;
  state: ServiceState;
  url: string | null;
  /** One plain sentence about how it stands: where it answers, what it is doing, or why it stopped. */
  plain: string;
}

export interface ServiceDeps {
  repos(): Repository[];
  log(line: string): void;
  /** Tell the person something, with buttons; resolves the button chosen. */
  notify(message: string, buttons: string[], kind?: 'info' | 'error'): Promise<string | undefined>;
  openExternal(url: string): Promise<void>;
  changed(): void;
  /** A service's trouble in the Problems panel (words), or gone (null) (0009-workspaces-console FR-064). */
  problem?(repo: Repository, key: string, words: string | null): void;
  /** Show progress for something slow that cannot be cancelled by the person (the build before a first start). */
  busy<T>(title: string, fn: () => Promise<T>): Promise<T>;
}

interface Live { info: ServiceInfo; source: CancelSource | null }

const words = (line: string): string[] => line.trim().split(/\s+/).filter(Boolean);

export class Services {
  private readonly live = new Map<string, Live>();

  constructor(private readonly deps: ServiceDeps) {}

  /** Every service the command lines declare, with how each stands now. */
  list(): ServiceInfo[] {
    const out: ServiceInfo[] = [];
    for (const repo of this.deps.repos()) {
      for (const decl of repo.list?.presentation.services ?? []) {
        const key = `${repo.key}#${decl.id}`;
        out.push(this.live.get(key)?.info ?? { key, repo, decl, state: 'stopped', url: null, plain: t('Not running.') });
      }
    }
    return out;
  }

  get(key: string): ServiceInfo | undefined { return this.list().find((s) => s.key === key); }
  running(): ServiceInfo[] { return this.list().filter((s) => s.state === 'running' || s.state === 'starting' || s.state === 'building'); }

  async start(key: string): Promise<void> {
    const found = this.get(key);
    if (!found || found.state === 'running' || found.state === 'starting' || found.state === 'building') return;
    await this.run(found, true);
  }

  private set(info: ServiceInfo, source: CancelSource | null): void {
    this.live.set(info.key, { info, source });
    this.deps.changed();
  }

  private async run(found: ServiceInfo, mayPrepare: boolean): Promise<void> {
    const source = new CancelSource();
    const info: ServiceInfo = { ...found, state: 'starting', url: null, plain: t('Starting…') };
    this.set(info, source);
    let up = false;
    const result: RunResult = await found.repo.launcher.run(words(found.decl.command), {
      token: source.token,
      onDocument: (d) => {
        const url = typeof d.data.url === 'string' ? d.data.url : '';
        if (!url) return;
        up = true;
        this.deps.problem?.(found.repo, `service:${found.decl.id}`, null);
        this.set({ ...info, state: 'running', url, plain: t('Running at {0}', url) }, source);
        void this.deps.notify(t('{0} is running at {1}.', found.decl.title, url), [t('Open in Browser')]).then((pick) => { if (pick) void this.open(found.key); });
      },
    });
    const now = this.live.get(found.key);
    if (source.token.isCancellationRequested) { this.set({ ...found, state: 'stopped', url: null, plain: t('Stopped.') }, null); return; }
    if (now?.info.state === 'running' && result.exit === 0) { this.set({ ...found, state: 'stopped', url: null, plain: t('Stopped.') }, null); return; }
    // It ended before it was up. If what it serves was never built, build it once and try again.
    if (mayPrepare && found.decl.prepare && !up) {
      this.set({ ...found, state: 'building', url: null, plain: t('Building what it shows first… this can take a minute.') }, null);
      const built = await this.deps.busy(t('{0}: building first', found.decl.title), () => found.repo.launcher.run(words(found.decl.prepare ?? '')));
      if (built.exit === 0 && !built.failed) { await this.run(found, false); return; }
      this.fail(found, why(built) || t('Building it did not work. The Output panel says why.'));
      return;
    }
    this.fail(found, why(result) || t('It stopped before it was ready. The Output panel says why.'));
  }

  private fail(found: ServiceInfo, plain: string): void {
    this.deps.log(`${found.decl.title}: ${plain}`);
    this.deps.problem?.(found.repo, `service:${found.decl.id}`, `${found.decl.title}: ${plain}`);
    this.set({ ...found, state: 'failed', url: null, plain }, null);
    void this.deps.notify(t('{0} did not start: {1}', found.decl.title, plain), [], 'error');
  }

  stop(key: string): void {
    const l = this.live.get(key);
    if (!l?.source) return;
    l.source.cancel();
  }

  stopAll(): void { for (const k of [...this.live.keys()]) this.stop(k); }

  async open(key: string): Promise<void> {
    const s = this.get(key);
    if (s?.url) await this.deps.openExternal(s.url);
  }
}

function why(r: RunResult): string {
  if (r.error) return r.error.message;
  const doc = r.doc;
  const plain = doc && typeof doc.data.plain === 'string' ? doc.data.plain : '';
  return plain || (r.stderr.trim().split(/\r?\n/).filter(Boolean).slice(-1)[0] ?? '');
}
