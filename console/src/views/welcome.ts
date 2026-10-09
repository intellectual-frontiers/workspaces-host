// The welcome page (0009-workspaces-console FR-065): a page in the editor that opens when the window has nothing else open, with a section for each repository that declares a
// command line of its own. It draws the model of model/welcome.ts, in the colors and fonts of the person's theme; what its buttons do is an index into the actions that model built.
import * as crypto from 'crypto';
import * as vscode from 'vscode';
import { t } from '../l10n';
import { topicsOf } from '../model/learn';
import { buildWelcome, renderWelcome, type WelcomeAction, type WelcomeRepo } from '../model/welcome';
import type { Repository } from '../services/repository';
import { dist } from './panel';
import { pageHtml } from './page';

export const WELCOME_TYPE = 'workspaces-console.welcome';

export interface WelcomeHost {
  readonly extensionUri: vscode.Uri;
  repos(): Repository[];
  signedOut(): boolean;
  updates(): { waiting: boolean; plain: string };
  needs(repo: Repository): number;
  openTopic(repo: Repository, topic: string): Promise<unknown>;
  learn(repo: Repository): Promise<unknown>;
  fail(e: unknown): void;
}


export class WelcomePage implements vscode.Disposable {
  private panel: vscode.WebviewPanel | null = null;
  private actions: WelcomeAction[] = [];

  constructor(private readonly host: WelcomeHost) {}

  /** Open the page, or bring it forward, drawn from what is known now. */
  async show(): Promise<void> {
    if (this.panel) { this.panel.reveal(undefined, false); await this.draw(); return; }
    const root = dist(this.host.extensionUri);
    const panel = vscode.window.createWebviewPanel(WELCOME_TYPE, t('Welcome'), vscode.ViewColumn.One, { enableScripts: true, enableCommandUris: false, localResourceRoots: [root] });
    this.panel = panel;
    panel.onDidDispose(() => { this.panel = null; });
    panel.webview.onDidReceiveMessage((m: unknown) => { void this.act(m); });
    await this.draw();
  }

  /** What the page says changed (a repository arrived, news waits, sign-in changed): draw it again if it is open. */
  async refresh(): Promise<void> { if (this.panel) await this.draw(); }

  get isOpen(): boolean { return this.panel !== null; }

  private async draw(): Promise<void> {
    const panel = this.panel;
    if (!panel) return;
    const repos: WelcomeRepo[] = await Promise.all(this.host.repos().map(async (r) => ({ key: r.key, name: r.name, folder: r.folder.name, summary: r.summary, state: r.state, reason: r.reason,
      needs: this.host.needs(r), topics: r.state === 'ready' && r.has('help') ? topicsOf((await r.launcher.run(['help'])).doc) : [] })));
    const { model, actions } = buildWelcome({ repos, signedOut: this.host.signedOut(), updates: this.host.updates() });
    this.actions = actions;
    panel.webview.html = pageHtml(panel.webview, this.host.extensionUri, t('Welcome'), renderWelcome(model), crypto.randomBytes(16).toString('hex'));
  }

  private async act(message: unknown): Promise<void> {
    const ref = (message as { ref?: unknown } | null)?.ref;
    const action = typeof ref === 'number' ? this.actions[ref] : undefined;
    if (!action) return;
    try {
      if (action.kind === 'ext') await vscode.commands.executeCommand(`workspaces-console.${action.command}`);
      else {
        const repo = this.host.repos().find((r) => r.key === action.repo);
        if (!repo) return;
        if (action.kind === 'learn') await this.host.learn(repo); else await this.host.openTopic(repo, action.topic);
      }
    } catch (e) { this.host.fail(e); }
  }

  dispose(): void { this.panel?.dispose(); this.panel = null; }
}
