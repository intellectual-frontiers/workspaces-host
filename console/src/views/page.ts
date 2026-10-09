// The pages this extension draws in the editor (the welcome page, what changed): one strict shell and one stylesheet in the colors and fonts of the person's theme, so that they look
// like parts of one thing. A page's body is made by a model, every word of it escaped there; what its buttons do is an index into actions the extension built.
import * as vscode from 'vscode';
import { dist } from './panel';

export const PAGE_CSS = `
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

/** The whole document: a policy that allows only this page's own script and style by nonce and its own icon font, and the one script that turns a click on [data-ref] into a message. */
export function pageHtml(webview: Pick<vscode.Webview, 'cspSource' | 'asWebviewUri'>, extensionUri: vscode.Uri, title: string, body: string, nonce: string, extraCss = ''): string {
  const icons = webview.asWebviewUri(vscode.Uri.joinPath(dist(extensionUri), 'codicons', 'codicon.css')).toString();
  const csp = `default-src 'none'; img-src ${webview.cspSource} data:; font-src ${webview.cspSource}; style-src ${webview.cspSource} 'nonce-${nonce}'; script-src 'nonce-${nonce}';`;
  return `<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Content-Security-Policy" content="${csp}"><title>${title}</title>
<link rel="stylesheet" href="${icons}" nonce="${nonce}"><style nonce="${nonce}">${PAGE_CSS}${extraCss}</style></head>
<body>${body}
<script nonce="${nonce}">const api = acquireVsCodeApi(); document.addEventListener('click', (e) => { const b = e.target instanceof Element ? e.target.closest('[data-ref]') : null; if (b) api.postMessage({ ref: Number(b.getAttribute('data-ref')) }); });</script>
</body></html>`;
}
