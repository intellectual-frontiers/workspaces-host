// The manifest's contributions (0009-workspaces-console FR-036, FR-037, FR-038, FR-039, FR-024): the views, the welcome content, the commands'
// categories, titles and icons, the keys, the menus' groups and the settings.
import test from 'node:test';
import assert from 'node:assert/strict';
import * as fs from 'fs';
import * as path from 'path';
import type { Loose } from './support/fake-launcher';
import { EXT_ROOT, readManifest } from './support/paths';

const manifest = readManifest() as Loose;
const c = manifest.contributes as Loose;
const COMMANDS = c.commands as Loose[];

test('FR-036: the activity bar has one container with a monochrome icon, and its views are Home, Services, the slots, Checks and All commands, in that order', () => {
  assert.equal(c.viewsContainers.activitybar.length, 1);
  const svg = fs.readFileSync(path.join(EXT_ROOT, c.viewsContainers.activitybar[0].icon), 'utf8');
  assert.match(svg, /currentColor/);
  assert.doesNotMatch(svg, /#[0-9a-f]{3,8}\b|fill="(?!none|currentColor)|stroke="(?!none|currentColor)/i, 'it draws in no color of its own');
  const ids = c.views['workspaces-console'].map((v: Loose) => v.id);
  assert.equal(ids[0], 'workspaces-console.home');
  assert.equal(ids[1], 'workspaces-console.services');
  assert.deepEqual(ids.slice(2, -2), Array.from({ length: 16 }, (_, i) => `workspaces-console.view.${i}`));
  assert.deepEqual(ids.slice(-2), ['workspaces-console.checks', 'workspaces-console.commands']);
  const slots = c.views['workspaces-console'].filter((v: Loose) => /\.view\./.test(v.id));
  assert.ok(slots.every((v: Loose, i: number) => v.when === `workspaces-console.slot.${i}`), 'a slot shows only when a view is planned into it');
  assert.match(c.views['workspaces-console'].at(-1).when, /allCommands/);
});

test('FR-037: Home has welcome content, with buttons, for no command line, an untrusted workspace and a missing toolchain', () => {
  const home = c.viewsWelcome.filter((w: Loose) => w.view === 'workspaces-console.home');
  const when = (re: RegExp) => home.find((w: Loose) => re.test(w.when));
  assert.ok(when(/hasRepository/) && when(/untrusted/) && when(/toolchainMissing/));
  for (const w of home) assert.match(w.contents, /\]\(command:[a-zA-Z.]+/, 'each has a button');
  assert.match(home.find((w: Loose) => w.when === 'workspaces-console.untrusted').contents, /\(command:workspaces-console\.trust\)/);
  assert.match(home.find((w: Loose) => w.when.endsWith(' && workspaces-console.toolchainMissing')).contents, /doctor/);
});

test('FR-039: every command has the category Workspaces Console, a title that is a verb and an object, an icon and a when or an enablement', () => {
  const palette = Object.fromEntries(c.menus.commandPalette.map((m: Loose) => [m.command, m]));
  for (const cmd of COMMANDS) {
    assert.equal(cmd.category, 'Workspaces Console', cmd.command);
    assert.ok(cmd.icon && /^\$\([a-z-]+\)$/.test(cmd.icon), `${cmd.command} has an icon`);
    assert.ok(cmd.title.replace('…', '').trim().split(/\s+/).length >= 2, `${cmd.command}: ${cmd.title}`);
    assert.ok(cmd.enablement || palette[cmd.command]?.when, `${cmd.command} is offered only when it can run`);
  }
  const titles = COMMANDS.map((x) => x.title);
  for (const want of ['Show Home', 'Run Command…', 'Run Check…', 'Learn a Topic…', 'Copy Context…']) assert.ok(titles.includes(want), want);
});

test('FR-039, FR-015: the keys are for Home, Run Check, Learn, Copy Context, the welcome page and looking for updates only, and no key runs a decision or a write', () => {
  const keys = c.keybindings as Loose[];
  assert.deepEqual(keys.map((k) => k.command).sort(), ['workspaces-console.check', 'workspaces-console.copyContext', 'workspaces-console.learn', 'workspaces-console.lookForUpdates', 'workspaces-console.showHome', 'workspaces-console.showWelcome']);
  for (const k of keys) assert.match(k.when, /hasRepository/);
  const reads = new Set(['workspaces-console.showHome', 'workspaces-console.check', 'workspaces-console.learn', 'workspaces-console.copyContext', 'workspaces-console.doctor', 'workspaces-console.checkOnChanges', 'workspaces-console.showWelcome', 'workspaces-console.lookForUpdates']);
  for (const k of keys) assert.ok(reads.has(k.command));
  assert.ok(!keys.some((k) => /runCommand|runSuggestion|followLink|activateNode|runRowAction/.test(k.command)));
});

test('FR-038: a row\'s menus are in the groups inline, navigation, 1_run, 2_copy and 9_cutcopypaste, each command in them is one the code registers, and the palette hides them', () => {
  const groups = new Set<string>();
  const palette = Object.fromEntries(c.menus.commandPalette.map((m: Loose) => [m.command, m]));
  for (const m of c.menus['view/item/context'] as Loose[]) {
    groups.add(m.group.split('@')[0]);
    assert.ok(COMMANDS.some((x) => x.command === m.command), m.command);
  }
  assert.deepEqual([...groups].sort(), ['1_run', '2_copy', '9_cutcopypaste', 'inline', 'navigation']);
  for (const hidden of ['runSuggestion', 'openRow', 'copyCommandLine', 'followLink']) assert.equal(palette[`workspaces-console.${hidden}`].when, 'false');
  const titleActions = (c.menus['view/title'] as Loose[]).filter((m) => m.group.startsWith('navigation'));
  assert.ok(titleActions.length >= 6, 'the views have title actions with icons');
  for (const m of titleActions) assert.ok(COMMANDS.find((x) => x.command === m.command)?.icon, m.command);
});

test('FR-024, FR-040: each setting has a markdownDescription and the scope application; the code reads no other', () => {
  const props = c.configuration.properties as Record<string, Loose>;
  assert.deepEqual(Object.keys(props).sort(), ['workspaces-console.checkOnSave', 'workspaces-console.launchers', 'workspaces-console.rowLimit', 'workspaces-console.showAllCommands', 'workspaces-console.showWelcomeOnStart', 'workspaces-console.simpleViews']);
  for (const p of Object.values(props)) { assert.equal(p.scope, 'application'); assert.ok(p.markdownDescription.length > 20); }
  assert.equal(props['workspaces-console.showAllCommands'].default, false, 'All commands is hidden by default');
});

test('FR-055: the getting-started walkthrough has its steps, each with a page in the extension and buttons that run commands the extension contributes', () => {
  const w = c.walkthroughs[0];
  assert.equal(w.id, 'getStarted');
  assert.ok(w.steps.length >= 6);
  const known = new Set(COMMANDS.map((x: Loose) => x.command));
  for (const step of w.steps) {
    assert.ok(fs.existsSync(path.join(EXT_ROOT, step.media.markdown)), `${step.id} has its page`);
    const text = String(step.description);      // the manifest is read with its words filled in
    for (const m of text.matchAll(/\(command:([\w.-]+)\)/g)) assert.ok(known.has(m[1]), `${step.id}: ${m[1]} is a command of this extension`);
    assert.ok(/\(command:/.test(text), `${step.id} has a button`);
  }
});

test('FR-062: Home\'s title bar offers Add Repository, and Sign In only while GitHub is not signed in', () => {
  const title = c.menus['view/title'] as Loose[];
  const mine = (command: string) => title.find((m) => m.command === `workspaces-console.${command}` && /workspaces-console\.home/.test(m.when));
  assert.ok(mine('addRepository'));
  assert.match(mine('signIn')?.when ?? '', /workspaces-console\.signedOut/);
  assert.doesNotMatch(mine('addRepository')?.when ?? '', /signedOut/);
});

test('FR-068: the walkthrough\'s doing-steps complete when the person does them, and each names a command this extension contributes', () => {
  const steps = c.walkthroughs[0].steps as Loose[];
  const done = steps.filter((s) => s.completionEvents);
  assert.deepEqual(done.map((s) => s.id), ['signIn', 'setUp', 'addRepo', 'check', 'website']);
  const ids = new Set(COMMANDS.map((x) => x.command));
  for (const s of done) for (const e of s.completionEvents as string[]) assert.ok(ids.has(e.replace('onCommand:', '')), e);
  assert.deepEqual((c.taskDefinitions as Loose[]).map((d) => d.type), ['workspaces-console'], 'one task type, which the provider is registered for');
  assert.ok(c.taskDefinitions[0].properties.build);
});
