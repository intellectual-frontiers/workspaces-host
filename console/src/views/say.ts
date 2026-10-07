// A small confirmation is said in the status bar for a few seconds, as VS Code says "Copied" and "Saved", and not as a message that has to be closed (0009-workspaces-console FR-067):
// a message is for what needs a choice or a next step; a confirmation is not one.
import * as vscode from 'vscode';
import * as testMode from '../test-mode';

export const SAY_FOR_MS = 5000;

export function say(text: string): void {
  testMode.note('say', { text });
  vscode.window.setStatusBarMessage(text, SAY_FOR_MS);
}
