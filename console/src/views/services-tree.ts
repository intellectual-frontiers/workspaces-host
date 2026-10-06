// The Services view (0009-workspaces-console FR-053): what a command line can keep running (the website on this computer), each with whether it is running,
// where it answers and the buttons that matter: Start, Open in Browser, Stop. Nothing else is here, so nothing else can confuse a newcomer.
import * as vscode from 'vscode';
import type { ServiceInfo, Services } from '../services/services';
import { icon } from './node';
import { t } from '../l10n';

export class ServiceNode {
  constructor(readonly info: ServiceInfo) {}
}

export class ServicesProvider implements vscode.TreeDataProvider<ServiceNode> {
  private readonly emitter = new vscode.EventEmitter<ServiceNode | undefined>();
  readonly onDidChangeTreeData = this.emitter.event;

  constructor(private readonly services: Services) {}

  refresh(): void { this.emitter.fire(undefined); }

  getTreeItem(node: ServiceNode): vscode.TreeItem {
    const s = node.info;
    const item = new vscode.TreeItem(s.decl.title, vscode.TreeItemCollapsibleState.None);
    item.id = s.key;
    item.description = s.state === 'running' ? s.url ?? '' : s.state === 'stopped' ? '' : s.plain;
    item.tooltip = new vscode.MarkdownString(`${s.decl.description}\n\n${s.plain}`);
    item.iconPath = s.state === 'running' ? icon('circle-filled', 'testing.iconPassed') : s.state === 'failed' ? icon('error', 'testing.iconFailed')
      : s.state === 'stopped' ? icon(s.decl.icon) : icon('loading~spin');
    item.contextValue = `service ${s.state}`;
    item.command = s.state === 'running' ? { command: 'workspaces-console.openService', title: t('Open in Browser'), arguments: [node] }
      : s.state === 'stopped' || s.state === 'failed' ? { command: 'workspaces-console.startService', title: t('Start'), arguments: [node] } : undefined;
    item.accessibilityInformation = { label: `${s.decl.title}, ${s.plain}` };
    return item;
  }

  getChildren(node?: ServiceNode): ServiceNode[] {
    return node ? [] : this.services.list().map((i) => new ServiceNode(i));
  }
}
