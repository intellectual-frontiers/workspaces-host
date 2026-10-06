// Enabling a repository as a provider of ws-host is a decision only a person makes (0008-providers): the person is asked in plain words, then `ws-host provider add`
// runs in a terminal they can see, where ws-host asks for the final yes itself. The extension starts no program of its own (0009-workspaces-console FR-003).
import * as vscode from 'vscode';
import type { App } from '../app';
import { t } from '../l10n';

const quoted = (s: string): string => `'${s.replace(/'/g, `'\\''`)}'`;

export async function enableProviders(app: App): Promise<void> {
  const roots = [...app.unenabled];
  if (roots.length === 0) { await app.refresh(); return; }
  const names = roots.map((r) => r.split(/[\\/]/).pop() ?? r).join(', ');
  const open = t('Open the terminal');
  const pick = await vscode.window.showInformationMessage(
    t('To use {0} here, ws-host must be allowed to run its command line and install the programs it lists.', names),
    { modal: true, detail: t('A terminal opens with the command typed in for you. Read the question it asks and type yes. Then choose Refresh in the Workspaces Console.') }, open);
  if (pick !== open) return;
  const terminal = vscode.window.createTerminal({ name: 'ws-host' });
  terminal.show();
  terminal.sendText(roots.map((r) => `ws-host provider add ${quoted(r)}`).join(' && '), true);
}
