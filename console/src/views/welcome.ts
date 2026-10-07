// The welcome page (0009-workspaces-console FR-065): a page in the editor that opens when the window has nothing else open, with a section for each repository that declares a
// command line of its own. It draws the model of model/welcome.ts, in the colors and fonts of the person's theme; what its buttons do is an index into the actions that model built.
import * as crypto from 'crypto';
import * as vscode from 'vscode';
import { t } from '../l10n';
import { topicsOf } from '../model/learn';
import { buildWelcome, renderWelcome, type WelcomeAction, type WelcomeRepo } from '../model/welcome';
import type { Repository } from '../services/repository';
import { dist } from './panel';

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

const CSS = `
:root { color-scheme: light dark; }
body { margin: 0; padding: 0; color: var(--vscode-foreground); background: var(--vscode-editor-background); font-family: var(--vscode-font-family); font-size: var(--vscode-font-size); line-height: 1.5; }
main { max-width: 1100px; margin: 0 auto; padding: 40px 32px 56px; }
.hero { padding: 36px 32px; margin-bottom: 24px; border-radius: 12px; border: 1px solid var(--vscode-widget-border, var(--vscode-panel-border, transparent));
  background: linear-gradient(135deg, color-mix(in srgb, var(--vscode-textLink-foreground) 16%, transparent), color-mix(in srgb, var(--vscode-focusBorder) 4%, transparent) 60%), var(--vscode-editorWidget-background, transparent); }
.hero h1 { margin: 0 0 8px; font-size: 2.1em; font-weight: 600; letter-spacing: -0.01em; color: var(--vscode-foreground); }
.hero p { margin: 0; max-width: 62ch; font-size: 1.1em; color: var(--vscode-descriptionForeground); }
.note { display: flex; align-items: center; gap: 12px; padding: 12px 16px; margin-bottom: 12px; border-radius: 8px; border: 1px solid var(--vscode-focusBorder);
  background: color-mix(in srgb, var(--vscode-focusBorder) 10%, transparent); }
.note p { margin: 0; flex: 1; }
.note > .codicon { font-size: 20px; color: var(--vscode-textLink-foreground); }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; margin: 24px 0; }
.card { display: flex; flex-direction: column; gap: 8px; padding: 20px; border-radius: 10px; border: 1px solid var(--vscode-widget-border, var(--vscode-panel-border, transparent));
  background: var(--vscode-editorWidget-background, var(--vscode-sideBar-background)); transition: border-color .15s, transform .15s; }
.card:hover, .card:focus-within { border-color: var(--vscode-focusBorder); transform: translateY(-1px); }
.card header { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.card h2 { margin: 0; font-size: 1.25em; font-weight: 600; }
.card h3 { margin: 12px 0 0; font-size: .8em; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--vscode-descriptionForeground); }
.folder { margin: 0; font-size: .85em; color: var(--vscode-descriptionForeground); font-family: var(--vscode-editor-font-family); }
.summary { margin: 4px 0 0; }
.chip { padding: 1px 10px; border-radius: 999px; font-size: .8em; border: 1px solid currentColor; white-space: nowrap; }
.chip.ok { color: var(--vscode-testing-iconPassed, var(--vscode-charts-green)); }
.chip.warn { color: var(--vscode-editorWarning-foreground, var(--vscode-charts-yellow)); }
.chip.bad { color: var(--vscode-editorError-foreground, var(--vscode-charts-red)); }
.topics { list-style: none; margin: 4px 0 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
.topics li { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.what { color: var(--vscode-descriptionForeground); font-size: .9em; }
.buttons { display: flex; gap: 8px; flex-wrap: wrap; margin-top: auto; padding-top: 12px; }
.note .buttons { margin: 0; padding: 0; }
button { display: inline-flex; align-items: center; gap: 6px; font: inherit; cursor: pointer; border-radius: 2px; padding: 4px 12px; border: 1px solid transparent; }
button.primary { color: var(--vscode-button-foreground); background: var(--vscode-button-background); }
button.primary:hover { background: var(--vscode-button-hoverBackground); }
button.secondary { color: var(--vscode-button-secondaryForeground); background: var(--vscode-button-secondaryBackground); }
button.secondary:hover { background: var(--vscode-button-secondaryHoverBackground); }
button.link { background: none; padding: 0; color: var(--vscode-textLink-foreground); }
button.link:hover { color: var(--vscode-textLink-activeForeground); text-decoration: underline; }
button:focus-visible { outline: 1px solid var(--vscode-focusBorder); outline-offset: 2px; }
footer { margin-top: 8px; }
footer .buttons { padding-top: 0; }
@media (prefers-reduced-motion: reduce) { .card { transition: none; } .card:hover, .card:focus-within { transform: none; } }
@media (max-width: 520px) { main { padding: 20px 16px 32px; } .hero { padding: 24px 20px; } .grid { grid-template-columns: 1fr; } }
`;

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
    const nonce = crypto.randomBytes(16).toString('hex');
    const webview = panel.webview;
    const icons = webview.asWebviewUri(vscode.Uri.joinPath(dist(this.host.extensionUri), 'codicons', 'codicon.css')).toString();
    const csp = `default-src 'none'; img-src ${webview.cspSource} data:; font-src ${webview.cspSource}; style-src ${webview.cspSource} 'nonce-${nonce}'; script-src 'nonce-${nonce}';`;
    webview.html = `<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Content-Security-Policy" content="${csp}"><title>${t('Welcome')}</title>
<link rel="stylesheet" href="${icons}" nonce="${nonce}"><style nonce="${nonce}">${CSS}</style></head>
<body>${renderWelcome(model)}
<script nonce="${nonce}">const api = acquireVsCodeApi(); document.addEventListener('click', (e) => { const b = e.target instanceof Element ? e.target.closest('[data-ref]') : null; if (b) api.postMessage({ ref: Number(b.getAttribute('data-ref')) }); });</script>
</body></html>`;
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
