// The quick fixes offered on a problem in the Problems panel (0009-workspaces-console FR-066): the lightbulb on a problem lists what can be done about it, each one a command of
// this extension that goes through the one path the same thing takes from anywhere else. Which fixes a problem has is decided here, from what is known of it, and nothing else.
import { t } from '../l10n';

export interface Fix { title: string; command: string; args?: unknown[]; preferred?: boolean }

export const SHOW_OUTPUT: Fix = { title: t('Show Output'), command: 'workspaces-console.showOutput' };
export const COPY_REPORT: Fix = { title: t('Copy a Report for Help'), command: 'workspaces-console.getHelp' };
export const INSTALL_EVERYTHING: Fix = { title: t('Install Everything'), command: 'workspaces-console.setUpEverything', preferred: true };

/** A command that failed: a missing prerequisite (exit status 3) is fixed by installing everything; every failure can show its output and ask for help. */
export function fixesForFailure(exit: number | null | undefined): Fix[] {
  return [...(exit === 3 ? [INSTALL_EVERYTHING] : []), SHOW_OUTPUT, COPY_REPORT];
}

/** A repository that would not load: a program it needs is missing, it needs enabling (a decision only a person makes), or this extension is too old to read it. */
export function fixesForLoad(o: { missing: boolean; needsProvider: boolean; state: string }): Fix[] {
  const out: Fix[] = [];
  if (o.state === 'update') out.push({ title: t('Check for Extension Updates'), command: 'workbench.extensions.action.checkForUpdates', preferred: true });
  if (o.needsProvider) out.push({ title: t('Set Repository Trust…'), command: 'workspaces-console.trust', preferred: true });
  if (o.missing) out.push(INSTALL_EVERYTHING);
  return [...out, SHOW_OUTPUT, COPY_REPORT];
}

/** A service that would not start. */
export const fixesForService = (): Fix[] => [SHOW_OUTPUT, COPY_REPORT];
