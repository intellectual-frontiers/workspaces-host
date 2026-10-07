// Quick fixes on the problems this extension reports (0009-workspaces-console FR-066): the lightbulb in the editor and the Problems panel offers each problem's fixes.
import * as vscode from 'vscode';
import type { Diagnostics } from '../services/diagnostics';

export class ProblemFixes implements vscode.CodeActionProvider {
  static readonly kinds = [vscode.CodeActionKind.QuickFix];

  constructor(private readonly diagnostics: Diagnostics) {}

  provideCodeActions(_document: vscode.TextDocument, _range: vscode.Range, context: vscode.CodeActionContext): vscode.CodeAction[] {
    const actions: vscode.CodeAction[] = [];
    for (const d of context.diagnostics) {
      for (const fix of this.diagnostics.fixesFor(d)) {
        const a = new vscode.CodeAction(fix.title, vscode.CodeActionKind.QuickFix);
        a.command = { title: fix.title, command: fix.command, arguments: fix.args };
        a.diagnostics = [d];
        a.isPreferred = fix.preferred === true;
        actions.push(a);
      }
    }
    return actions;
  }
}
