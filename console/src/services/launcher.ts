// Running a repository's launcher (0009-workspaces-console FR-003, FR-017, FR-020): every call is `<launcher> ... --json`, with
// the repository's root as the working directory and IF_CONSOLE=1 in the environment, so that the launcher logs the surface `editor`
// (0041-command-line FR-042), and a person at the editor, so that progress comes as events the editor draws (0011-archon FR-005, FR-021).
// Nothing else is ever run.
import * as childProcess from 'child_process';
import * as path from 'path';
import { commandLine } from '../model/forms';
import { asString } from '../model/json';
import { errorOf, parseDocuments, readDoc, type Doc, type ErrorInfo } from '../model/wire';

export type SpawnFn = typeof childProcess.spawn;

/**
 * The environment a launcher runs in, with `~/.local/bin` on `PATH` when the window has not got it (0009-workspaces-console FR-017): a window started before that
 * folder existed lacks it, and it is where `ws-host` links `uv`, the one thing a launcher needs of the computer (0011-archon FR-023). It is added last, so a
 * program the person put earlier on `PATH` still wins.
 */
export const withUserBin = (env: NodeJS.ProcessEnv): NodeJS.ProcessEnv => {
  const home = env.HOME ?? env.USERPROFILE;
  if (!home) return env;
  const bin = path.join(home, '.local', 'bin');
  const parts = (env.PATH ?? '').split(path.delimiter).filter(Boolean);
  return parts.includes(bin) ? env : { ...env, PATH: [...parts, bin].join(path.delimiter) };
};

/** What the launcher needs of a cancellation token: structurally VS Code's `CancellationToken`, without importing VS Code. */
export interface Cancellation {
  readonly isCancellationRequested: boolean;
  onCancellationRequested(listener: () => void): { dispose(): void };
}

/** One line of the progress `archon` publishes on standard error when `ARCHON_PROGRESS=events` (0011-archon FR-021). */
export interface ProgressEvent {
  event: 'progress' | 'message';
  step?: number;
  state?: 'start' | 'update' | 'done' | 'failed';
  emoji?: string;
  label?: string;
  text?: string;
  done?: number;
  total?: number;
  seconds?: number;
}

/** The words a person reads for a progress event: the emoji, what is happening, and how far it has come. */
export const progressWords = (p: ProgressEvent): string =>
  p.event === 'message' ? (p.text ?? '') : [p.emoji, p.label, p.text ? `— ${p.text}` : ''].filter(Boolean).join(' ');

const readProgress = (line: string): ProgressEvent | null => {
  if (!line.startsWith('{')) return null;
  try {
    const v: unknown = JSON.parse(line);
    const e = (v as { event?: unknown } | null)?.event;
    return e === 'progress' || e === 'message' ? (v as ProgressEvent) : null;
  } catch { return null; }
};

export interface RunOptions {
  /** Ends the process (SIGTERM) when it is cancelled. */
  token?: Cancellation;
  /** Sees each complete document of a stream as it arrives. */
  onDocument?: (doc: Doc) => void;
  /** Sees each step of progress `archon` publishes: an install, a download, a package set. */
  onProgress?: (event: ProgressEvent) => void;
}

export interface RunResult {
  exit: number | null;
  stdout: string;
  stderr: string;
  docs: Doc[];
  doc: Doc | null;
  error: ErrorInfo | null;
  cancelled: boolean;
  failed: string | null;
}

export interface LauncherInit {
  root: string;
  /** The absolute path that is run. */
  file: string;
  /** The path as shown to a person (`./tool`). */
  program: string;
  log?: (line: string) => void;
  spawn?: SpawnFn;
  env?: NodeJS.ProcessEnv;
}

export class Launcher {
  readonly root: string;
  readonly file: string;
  readonly program: string;
  private readonly log: (line: string) => void;
  private readonly spawn: SpawnFn;
  private readonly env: NodeJS.ProcessEnv;

  constructor({ root, file, program, log, spawn, env }: LauncherInit) {
    this.root = root;
    this.file = file;
    this.program = program;
    this.log = log ?? (() => undefined);
    this.spawn = spawn ?? childProcess.spawn;
    this.env = env ?? process.env;
  }

  line(argv: string[]): string { return commandLine(this.program, argv); }

  /** Run one command. Resolves a result; never rejects for a non-zero exit. */
  run(argv: string[], { token, onDocument, onProgress }: RunOptions = {}): Promise<RunResult> {
    const full = [...argv, '--json'];
    const shown = commandLine(this.program, full);
    this.log(`$ ${shown}`);
    return new Promise<RunResult>((resolve) => {
      let child: ReturnType<typeof childProcess.spawn>;
      try {
        child = this.spawn(this.file, full, { cwd: this.root, env: { ...withUserBin(this.env), IF_CONSOLE: '1', ARCHON_ATTENDANCE: 'attended', ARCHON_PROGRESS: 'events' }, stdio: ['ignore', 'pipe', 'pipe'] });
      } catch (e) {
        const why = e instanceof Error ? e.message : String(e);
        this.log(`could not start: ${why}`);
        resolve({ exit: null, stdout: '', stderr: why, docs: [], doc: null, error: null, cancelled: false, failed: why });
        return;
      }
      let stdout = '';
      let stderr = '';
      let pending = '';
      let cancelled = false;
      let settled = false;
      let subscription: { dispose(): void } | undefined;
      const finish = (exit: number | null, failed?: string): void => {
        if (settled) return;
        settled = true;
        subscription?.dispose();
        this.log(cancelled ? `cancelled (${shown})` : `exit ${String(exit)}${failed ? `: ${failed}` : ''}`);
        let docs: Doc[] = [];
        let problem: string | null = failed ?? null;
        try { docs = parseDocuments(stdout); } catch (e) { problem = problem ?? (e instanceof Error ? e.message : String(e)); }
        const doc = docs.length ? docs[docs.length - 1] ?? null : null;
        resolve({ exit, stdout, stderr, docs, doc, error: errorOf(doc), cancelled, failed: problem });
      };
      const onAbort = (): void => { cancelled = true; try { child.kill('SIGTERM'); } catch { /* already gone */ } };
      if (token) { if (token.isCancellationRequested) onAbort(); else subscription = token.onCancellationRequested(onAbort); }
      child.stdout?.on('data', (b: Buffer) => {
        const text = b.toString('utf8');
        stdout += text;
        pending += text;
        let nl: number;
        while ((nl = pending.indexOf('\n')) >= 0) {
          const line = pending.slice(0, nl);
          pending = pending.slice(nl + 1);
          let parsed: unknown;
          try { parsed = JSON.parse(line); } catch { continue; }   // a line of one pretty document, not a stream's
          const d = readDoc(parsed);
          if (d && d.schema) { this.log(line.length > 400 ? `${line.slice(0, 400)} ...` : line); onDocument?.(d); }
        }
      });
      child.stderr?.on('data', (b: Buffer) => {
        const text = b.toString('utf8');
        stderr += text;
        for (const l of text.split(/\r?\n/)) {
          if (!l.trim()) continue;
          const p = readProgress(l.trim());
          if (p) { this.log(progressWords(p)); onProgress?.(p); } else this.log(l);
        }
      });
      child.on('error', (e: NodeJS.ErrnoException) => finish(null, e.code === 'ENOENT' ? 'the launcher was not found' : asString(e.message)));
      child.on('close', (code: number | null) => finish(code));
    });
  }
}
