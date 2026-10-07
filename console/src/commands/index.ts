// The handlers of the commands the manifest contributes. Each is registered by the local `cmd` function under the prefix `workspaces-console.`, and the repository's check of this
// extension reads this file to prove that every contributed command has a handler and every handler is contributed.
import * as vscode from 'vscode';
import { t } from '../l10n';
import type { App } from '../app';
import { enableProviders } from '../services/enable';
import { manageTrust } from '../services/trust';
import { Node } from '../views/node';
import { ContextCommands } from './context';
import { LearnCommands } from './learn';
import { RunCommands } from './run';
import { StartCommands } from './start';
import { ViewCommands } from './views';

export interface Handlers {
  showResult: RunCommands['showResult'];
  runWords: RunCommands['runWords'];
  learn: LearnCommands;
  context: ContextCommands;
  run: RunCommands;
  views: ViewCommands;
  start: StartCommands;
  /** Register every command; `sub` keeps what it returns until the extension is deactivated. */
  register(sub: (d: vscode.Disposable) => unknown): void;
}

export function registerCommands(app: App): Handlers {
  const run = new RunCommands(app);
  const learn = new LearnCommands(app);
  const context = new ContextCommands(app);
  const views = new ViewCommands(app, run, context);
  const start = new StartCommands(app, run);
  return {
    run, learn, context, views, start,
    showResult: (...a) => run.showResult(...a),
    runWords: (...a) => run.runWords(...a),
    register(sub) {
      const cmd = (id: string, fn: (...args: unknown[]) => unknown): void => {
        sub(vscode.commands.registerCommand(`workspaces-console.${id}`, (...a: unknown[]) => Promise.resolve(fn(...a)).catch((e: unknown) => app.fail(e))));
      };
      cmd('showHome', (arg) => views.showHome(arg));
      cmd('showView', () => views.showView());
      cmd('runCommand', () => run.runCommandPalette());
      cmd('check', () => run.runRepoWide('check', { form: true }));
      cmd('checkChanged', () => run.runRepoWide('check', { args: ['--changed'] }));
      cmd('fresh', () => run.runRepoWide('fresh'));
      cmd('test', () => run.runRepoWide('test'));
      cmd('doctor', () => run.runRepoWide('doctor'));
      cmd('showCommandLine', () => run.showCommandLine());
      cmd('getHelp', () => context.getHelp());
      cmd('learn', () => learn.learn());
      cmd('copyContext', (node) => context.copyContext(node));
      cmd('openView', () => run.openViewCommand());
      cmd('findResource', (node) => views.findResource(node));
      cmd('searchView', (node, text) => views.searchView(node, text));
      cmd('refresh', () => app.refresh());
      cmd('showOutput', () => { app.log.show(true); });
      cmd('enableProvider', () => enableProviders(app));
      const keyOf = (node: unknown): string | undefined => {
        const info = (node as { info?: { key?: string } } | undefined)?.info;
        return info?.key ?? app.services.list()[0]?.key;
      };
      cmd('setUpEverything', () => views.setUpEverything());
      cmd('signIn', () => start.signIn());
      cmd('addRepository', () => start.addRepository());
      cmd('updateEverything', () => start.updateEverything());
      cmd('openWalkthrough', () => start.openWalkthrough());
      cmd('startService', (node) => app.services.start(keyOf(node) ?? ''));
      cmd('stopService', (node) => { app.services.stop(keyOf(node) ?? ''); });
      cmd('openService', (node) => app.services.open(keyOf(node) ?? ''));
      cmd('trust', () => manageTrust());
      cmd('cancelRun', () => views.cancelRun());
      cmd('toggleAllCommands', () => views.toggleAllCommands());
      cmd('showWelcome', () => app.welcome.show());
      cmd('lookForUpdates', async () => {
        await app.updates.look();
        if (!app.updates.current.waiting) void vscode.window.showInformationMessage(t('Everything is up to date.'));
      });
      cmd('toggleSimpleViews', () => { const simple = app.toggleSimpleViews(); void vscode.window.showInformationMessage(simple ? t('Showing the everyday views only.') : t('Showing every view.')); });
      cmd('activateNode', (node) => run.activateNode(node));
      cmd('runSection', (node) => (node instanceof Node && node.kind === 'section' && node.data.name ? app.fromView(node.data.view, () => app.runSectionsShown(node.repo, [node.data.name ?? ''])) : null));
      cmd('runSuggestion', (node) => views.runSuggestion(node));
      cmd('openRow', (node) => views.openRow(node));
      cmd('runRowAction', (node) => views.runRowAction(node));
      cmd('runNounCommand', (node) => views.runNounCommand(node));
      cmd('copyCommandLine', (node) => views.copyCommandLine(node));
      cmd('copyId', (node) => views.copyId(node));
      cmd('followLink', (handle) => views.followLink(handle));
    },
  };
}
