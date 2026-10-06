// Getting started (0009-workspaces-console FR-055): the few things a newcomer does first, each one button that goes through the one path every command takes, so that nobody
// has to know a command line exists. The walkthrough opens by itself the first time because VS Code does that for a newly installed extension; the extension keeps no state of its own (FR-026). Each finds the command line that offers the command (ws-host's, for setting up and signing in), never a program of its own.
import * as vscode from 'vscode';
import type { App } from '../app';
import { t } from '../l10n';
import { asArray, asObject, asString } from '../model/json';
import type { RunCommands } from './run';

export const WALKTHROUGH = 'intellectual-frontiers.workspaces-console#getStarted';

export class StartCommands {
  constructor(private readonly app: App, private readonly run: RunCommands) {}

  private owner(command: string) { return this.app.repos.find((r) => r.has(command)) ?? null; }

  private async ownerRun(words: string[], missing: string): Promise<unknown> {
    const repo = this.owner(words.slice(0, 2).join(' ')) ?? this.owner(words[0] ?? '');
    if (!repo) { void vscode.window.showInformationMessage(missing); return null; }
    const outcome = await this.run.runWords(repo, words);
    await this.app.refresh();
    return outcome;
  }

  /** Sign in to GitHub: ws-host shows a short code and an address; the person opens the address and types the code. */
  signIn(): Promise<unknown> {
    return this.ownerRun(['auth', 'new', 'github'], t('Open the ws-host folder in this window to sign in from here, or run "ws-host auth new github" in a terminal.'));
  }

  /** Add a repository by its address (copied now and kept up to date), which joins this window. */
  async addRepository(): Promise<unknown> {
    const address = await vscode.window.showInputBox({ title: t('Add a repository'), prompt: t('Its address on GitHub, like github.com/organization/repository'),
      placeHolder: t('github.com/organization/repository'), ignoreFocusOut: true,
      validateInput: (v) => (/^[\w.-]+(\/[\w.-]+){1,2}$/.test(v.trim()) ? undefined : t('Type it as host/organization/repository, for example github.com/organization/repository')) });
    if (!address) return null;
    const outcome = await this.ownerRun(['repo', 'add', address.trim()], t('Open the ws-host folder in this window to add repositories from here, or run "ws-host repo add" in a terminal.'));
    this.joinWindow(outcome);
    return outcome;
  }

  /** A repository that arrived joins this window at once, so its command line shows without reloading anything. */
  private joinWindow(outcome: unknown): void {
    const rows = asArray(asObject(((outcome as { real?: { doc?: { data?: unknown } } } | null)?.real?.doc?.data)).repositories).map(asObject);
    const have = new Set((vscode.workspace.workspaceFolders ?? []).map((f) => f.uri.fsPath));
    const fresh = rows.map((r) => asString(r.path)).filter((p) => p !== '' && !have.has(p));
    if (fresh.length) vscode.workspace.updateWorkspaceFolders(vscode.workspace.workspaceFolders?.length ?? 0, 0, ...fresh.map((p) => ({ uri: vscode.Uri.file(p) })));
  }

  /** One button that brings everything current: ws-host, the repositories, the editor and what they need. */
  updateEverything(): Promise<unknown> {
    return this.ownerRun(['update'], t('Open the ws-host folder in this window to update from here, or run "ws-host update" in a terminal.'));
  }

  openWalkthrough(): Thenable<unknown> {
    return vscode.commands.executeCommand('workbench.action.openWalkthrough', WALKTHROUGH, false);
  }
}
