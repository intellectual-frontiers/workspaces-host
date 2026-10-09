// The what-changed page (0009-workspaces-console FR-069): opens from the Command Palette, from the Welcome page and from the button Home offers when a repository differs; it asks the
// command line that offers `repo status --details` and draws what it said with model/changes.ts.
import * as crypto from 'crypto';
import * as vscode from 'vscode';
import { t } from '../l10n';
import { buildChanges, CHANGES_CSS, renderChanges, type ChangesAction } from '../model/changes';
import { asArray } from '../model/json';
import type { Repository } from '../services/repository';
import { pageHtml } from './page';

export interface ChangesHost {
  readonly extensionUri: vscode.Uri;
  repos(): Repository[];
  /** Run a command the way every command runs: a write is previewed and accepted first. */
  runWords(repo: Repository, words: string[]): Promise<unknown>;
  copy(text: string): Promise<void>;
  fail(e: unknown): void;
}

export class ChangesPage implements vscode.Disposable {
  private panel: vscode.WebviewPanel | null = null;
  private actions: ChangesAction[] = [];

  constructor(private readonly host: ChangesHost) {}

  private owner(): Repository | null { return this.host.repos().find((r) => r.state === 'ready' && r.has('repo status')) ?? null; }

  async show(fresh = false): Promise<void> {
    const owner = this.owner();
    if (!owner) { void vscode.window.showInformationMessage(t('Open the ws-host folder in this window to see what changed, or run "ws-host repo status --details" in a terminal.')); return; }
    if (this.panel) this.panel.reveal(undefined, false);
    else {
      const panel = vscode.window.createWebviewPanel('workspaces-console.changes', t('What Changed'), vscode.ViewColumn.One, { enableScripts: true, enableCommandUris: false });
      this.panel = panel;
      panel.onDidDispose(() => { this.panel = null; });
      panel.webview.onDidReceiveMessage((m: unknown) => { void this.act(m, owner); });
    }
    await this.draw(owner, fresh);
  }

  private async draw(owner: Repository, fresh: boolean): Promise<void> {
    const panel = this.panel;
    if (!panel) return;
    const r = await vscode.window.withProgress({ location: vscode.ProgressLocation.Window, title: fresh ? t('Asking GitHub what changed…') : t('Reading what changed…') },
      () => owner.launcher.run(['repo', 'status', '--details', ...(fresh ? ['--fetch'] : [])]));
    if (!r.doc || r.error) { panel.webview.html = pageHtml(panel.webview, this.host.extensionUri, t('What Changed'), `<main><header class="hero"><h1>${t('What changed')}</h1><p>${t('It could not be read. The Output panel says why.')}</p></header></main>`, crypto.randomBytes(16).toString('hex')); return; }
    const { model, actions } = buildChanges(asArray(r.doc.data.repositories));
    this.actions = actions;
    panel.webview.html = pageHtml(panel.webview, this.host.extensionUri, t('What Changed'), renderChanges(model), crypto.randomBytes(16).toString('hex'), CHANGES_CSS);
  }

  private async act(message: unknown, owner: Repository): Promise<void> {
    const ref = (message as { ref?: unknown } | null)?.ref;
    const action = typeof ref === 'number' ? this.actions[ref] : undefined;
    if (!action) return;
    try {
      if (action.kind === 'again') await this.draw(owner, true);
      else if (action.kind === 'fresh') { await this.host.runWords(owner, ['repo', 'advance', action.id, '--clean']); await this.draw(owner, true); }
      else if (action.kind === 'scm') await vscode.commands.executeCommand('workbench.view.scm');
      else if (action.kind === 'copy') { await this.host.copy(action.text); }
      else { await this.host.runWords(owner, ['repo', 'sync', action.id]); await this.draw(owner, false); }
    } catch (e) { this.host.fail(e); }
  }

  dispose(): void { this.panel?.dispose(); this.panel = null; }
}
