// The task type `workspaces-console` (0009-workspaces-console FR-010): a repository's repository-wide commands (`check`, `test`, `fresh`, `doctor`) and,
// for `check`, a section or a suite, under Run Task, bindable to a keybinding. A task runs the launcher with `--json` and writes a summary
// to its terminal; the findings of a check go straight to the Problems panel (direct diagnostics), so no problem matcher is needed.
import * as vscode from 'vscode';
import { asString } from '../model/json';
import { checkResult, checkSchema, exposed, type Doc, type CommandDetail } from '../model/wire';
import { CancelSource } from '../services/cancellation';
import type { Repository } from '../services/repository';
import { t } from '../l10n';

export const COMMANDS = ['check', 'test', 'fresh', 'doctor'];

export interface TaskDef extends vscode.TaskDefinition { command: string; section?: string; suite?: string; changed?: boolean; folder?: string }

/** What a task needs of the extension: the repositories, whether the workspace is trusted, and where a result goes. */
export interface TaskHost {
  readonly repos: Repository[];
  trusted(): boolean;
  handleCheck(repo: Repository, doc: Doc): Promise<unknown>;
  refreshViews(): void;
  /** Run a command the way every command runs: a write is previewed and accepted first (0009-workspaces-console FR-014). */
  runWords(repo: Repository, words: string[]): Promise<{ ran: boolean; reason?: string } | null>;
}

export const BUILD_TYPE = 'workspaces-console.build';

/** A build a task can start without asking for anything: the command line's own builds that need no argument. */
export function startable(c: Pick<CommandDetail, 'category' | 'arguments'>): boolean {
  return c.category === 'build' && c.arguments.every((a) => !a.required);
}

/** What a build task's terminal does: the same path a build takes from anywhere (the preview, the accepting, the progress), with its outcome written here so that Run Task has an end. */
export class BuildTerminal implements vscode.Pseudoterminal {
  private readonly writeEmitter = new vscode.EventEmitter<string>();
  private readonly closeEmitter = new vscode.EventEmitter<number | void>();
  readonly onDidWrite = this.writeEmitter.event;
  readonly onDidClose = this.closeEmitter.event;

  constructor(private readonly host: TaskHost, private readonly repo: Repository, private readonly command: string) {}

  private write(line: string): void { this.writeEmitter.fire(`${line}\r\n`); }

  open(): void { void this.start(); }

  private async start(): Promise<void> {
    const words = this.command.split(/\s+/).filter(Boolean);
    this.write(`$ ${this.repo.launcher.line(words)}`);
    if (!this.host.trusted()) { this.write(t('Workspaces Console runs nothing in a workspace that is not trusted.')); this.closeEmitter.fire(1); return; }
    this.write(t('It shows what it would change first, and asks.'));
    const outcome = await this.host.runWords(this.repo, words);
    if (outcome?.ran) { this.write(t('Done.')); this.closeEmitter.fire(0); return; }
    this.write(outcome?.reason === 'cancelled' || outcome === null ? t('Nothing was changed.') : t('It did not finish. The Problems panel and the Output panel say why.'));
    this.closeEmitter.fire(1);
  }

  close(): void { /* a preview or a running build is ended by its own Cancel */ }
}

export function argvOf(def: TaskDef): string[] {
  const argv = [def.command];
  if (def.command === 'check') {
    if (def.suite) argv.push('--suite', def.suite);
    if (def.section) argv.push(def.section);
    if (def.changed) argv.push('--changed');
  }
  return argv;
}

function labelOf(repo: Repository, def: TaskDef): string {
  return [repo.name, def.command, def.section ?? (def.suite ? `--suite ${def.suite}` : '')].filter(Boolean).join(' ');
}

/** What a task writes to its terminal for a result: plain lines. */
export function summaryLines(doc: Doc): string[] {
  const out: string[] = [];
  if (doc.kind === 'check') {
    const r = checkResult(doc);
    for (const s of r.sections) {
      out.push(`${s.status === 'passed' ? 'passed' : s.status === 'skipped' ? 'skipped' : 'FAILED'}  ${s.name}${s.reason ? ` (${s.reason})` : ''}`);
      for (const f of s.findings) out.push(`  ${f.level}: ${f.where ? `${f.where}: ` : ''}${f.message}`);
    }
    out.push(`check: ${r.summary.passed ?? 0} passed, ${r.summary.failed ?? 0} failed, ${r.summary.skipped ?? 0} skipped`);
  } else {
    out.push(`${doc.kind}: ${asString(doc.data.status, 'done')}`);
  }
  return out;
}

export class TaskTerminal implements vscode.Pseudoterminal {
  private readonly writeEmitter = new vscode.EventEmitter<string>();
  private readonly closeEmitter = new vscode.EventEmitter<number | void>();
  readonly onDidWrite = this.writeEmitter.event;
  readonly onDidClose = this.closeEmitter.event;
  private readonly cancel = new CancelSource();

  constructor(private readonly host: TaskHost, private readonly repo: Repository, private readonly def: TaskDef) {}

  private write(line: string): void { this.writeEmitter.fire(`${line}\r\n`); }

  open(): void { void this.start(); }

  private async start(): Promise<void> {
    const argv = argvOf(this.def);
    this.write(`$ ${this.repo.launcher.line([...argv, '--json'])}`);
    if (!this.host.trusted()) { this.write('Workspaces Console runs nothing in a workspace that is not trusted.'); this.closeEmitter.fire(1); return; }
    const r = await this.repo.launcher.run(argv, { token: this.cancel.token,
      onDocument: (d) => this.write(asString(d.data.message || d.data.step || d.id)) });
    if (r.cancelled) { this.write('Cancelled.'); this.closeEmitter.fire(1); return; }
    if (!r.doc || r.error) { this.write(r.error ? r.error.message : t('{0} gave no result ({1}).', this.repo.program, r.failed ?? `exit ${String(r.exit)}`)); this.closeEmitter.fire(r.exit || 1); return; }
    const ok = checkSchema(r.doc);
    if (!ok.ok) { this.write(ok.message); this.closeEmitter.fire(1); return; }
    if (r.doc.kind === 'check') await this.host.handleCheck(this.repo, r.doc);
    if (r.doc.kind === 'doctor') { this.repo.doctor = r.doc; this.host.refreshViews(); }
    if (r.doc.kind === 'fresh') { this.repo.fresh = r.doc; this.host.refreshViews(); }
    for (const l of summaryLines(r.doc)) this.write(l);
    this.closeEmitter.fire(r.exit ?? 0);
  }

  close(): void { this.cancel.cancel(); }
}

export class TaskProvider implements vscode.TaskProvider {
  constructor(private readonly host: TaskHost) {}

  private make(repo: Repository, def: TaskDef): vscode.Task {
    const task = new vscode.Task({ ...def, folder: repo.folder.name }, repo.folder, labelOf(repo, def), 'workspaces-console',
      new vscode.CustomExecution(() => Promise.resolve(new TaskTerminal(this.host, repo, def))));
    task.detail = repo.launcher.line([...argvOf(def), '--json']);
    if (def.command === 'test') task.group = vscode.TaskGroup.Test;
    if (def.command === 'check') task.group = vscode.TaskGroup.Build;
    return task;
  }

  private makeBuild(repo: Repository, command: string): vscode.Task {
    const task = new vscode.Task({ type: BUILD_TYPE, command, folder: repo.folder.name }, repo.folder, `${repo.name} ${command}`, 'workspaces-console',
      new vscode.CustomExecution(() => Promise.resolve(new BuildTerminal(this.host, repo, command))));
    task.detail = repo.launcher.line(command.split(/\s+/));
    task.group = vscode.TaskGroup.Build;
    return task;
  }

  /** The builds of a repository that need nothing asked: each is a task, so that Run Task and Run Build Task find them like any build. */
  private async builds(repo: Repository): Promise<vscode.Task[]> {
    const found = await Promise.all(repo.editorCommands().filter((c) => c.category === 'build').map(async (c) => {
      try { return startable(await repo.detail(c.id)) ? this.makeBuild(repo, c.id) : null; } catch { return null; }
    }));
    return found.filter((x): x is vscode.Task => x !== null);
  }

  async provideTasks(): Promise<vscode.Task[]> {
    const tasks: vscode.Task[] = [];
    for (const repo of this.host.repos) {
      if (repo.state !== 'ready') continue;
      for (const command of COMMANDS) {
        const c = repo.command(command);
        if (!c || !exposed(c)) continue;
        tasks.push(this.make(repo, { type: 'workspaces-console', command }));
        if (command === 'check') {
          try {
            const d = await repo.detail('check');
            const suite = d.options.find((o) => o.flag === '--suite');
            for (const s of suite?.choices ?? []) tasks.push(this.make(repo, { type: 'workspaces-console', command, suite: s }));
          } catch { /* the plain check task is still there */ }
        }
      }
      tasks.push(...await this.builds(repo));
    }
    return tasks;
  }

  resolveTask(task: vscode.Task): vscode.Task | undefined {
    const built = task.definition as Partial<TaskDef>;
    if (built.type === BUILD_TYPE && built.command) {
      const id = built.command;
      const owner = this.host.repos.find((r) => (built.folder ? r.folder.name === built.folder : true) && r.state === 'ready' && r.command(id)?.category === 'build');
      return owner ? this.makeBuild(owner, id) : undefined;
    }
    const def = task.definition as Partial<TaskDef>;   // a task's definition is what package.json's taskDefinitions describes; VS Code types it as an open record
    if (def.type !== 'workspaces-console' || !def.command || !COMMANDS.includes(def.command)) return undefined;
    const command = def.command;
    const repo = this.host.repos.find((r) => (def.folder ? r.folder.name === def.folder : true) && r.state === 'ready' && r.has(command));
    return repo ? this.make(repo, { ...def, type: 'workspaces-console', command }) : undefined;
  }
}
