// Finding each repository's launcher by that repository's own declaration (0043-console-protocol FR-004): a workspace folder holds
// `.workspaces-host/provider.toml`, whose `launcher` key names an executable file at the folder's root. The extension carries no list of
// launcher names; a person may add names, in their own settings only, for a folder that declares none. Reading the declaration needs no
// trust (0041-command-line FR-062); running the launcher does (FR-006).
import * as path from 'path';

export const DECLARATION = '.workspaces-host/provider.toml';
export const KEY = 'launcher';

/** The top-level string keys of a TOML file: what discovery needs of `provider.toml`, read as data and never run. */
export function parseTopLevel(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (line.startsWith('[')) break;                       // a table: the top level ended
    const m = /^([A-Za-z0-9_-]+)\s*=\s*"((?:[^"\\]|\\.)*)"\s*(?:#.*)?$/.exec(line);
    if (m) out[m[1]] = m[2].replace(/\\(.)/g, '$1');
  }
  return out;
}

export type RootRelative = { file: string; program: string; problem?: undefined } | { problem: string; file?: undefined; program?: undefined };

/** A launcher name is a file at the root: no directory above it, no absolute path, nothing that leaves the clone. */
export function rootRelative(root: string, name: string): RootRelative {
  const clean = name.trim();
  if (clean === '') return { problem: 'names no launcher' };
  if (path.isAbsolute(clean)) return { problem: `names ${clean}, an absolute path; a launcher is a file at the repository's root` };
  const normal = path.normalize(clean);
  if (normal.startsWith('..') || normal.split(path.sep).includes('..')) {
    return { problem: `names ${clean}, which leaves the repository; a launcher is a file at the repository's root` };
  }
  if (normal.includes(path.sep)) return { problem: `names ${clean}, which is not at the repository's root` };
  return { file: path.join(root, normal), program: `./${normal}` };
}

/** What discovery needs of the file system: the text of a file or null, and whether a path is an executable file. */
export interface DiscoveryFs {
  readFile(p: string): Promise<string | null>;
  isExecutable(p: string): Promise<boolean>;
}

export interface FolderRef<F> { name: string; root: string; raw: F }

export interface Candidate<F> {
  folder: FolderRef<F>;
  root: string;
  status: 'candidate' | 'rejected';
  source: 'declared' | 'setting';
  file?: string;
  program?: string;
  reason?: string;
  /** What the repository's own declaration says it is, in one sentence, for people. */
  summary?: string;
}

/** One entry for each folder that has a candidate. */
export async function discover<F>({ folders, personLaunchers, fs }: { folders: Array<FolderRef<F>>; personLaunchers: string[]; fs: DiscoveryFs }): Promise<Array<Candidate<F>>> {
  const out: Array<Candidate<F>> = [];
  for (const folder of folders) {
    const root = folder.root;
    const text = await fs.readFile(path.join(root, DECLARATION));
    const top = text === null ? {} : parseTopLevel(text);
    const declared = top[KEY];
    const summary = top.summary;
    const names: Array<{ name: string; source: 'declared' | 'setting' }> = declared
      ? [{ name: declared, source: 'declared' }]
      : personLaunchers.map((name) => ({ name, source: 'setting' as const }));   // a folder that declares none
    for (const { name, source } of names) {
      const r = rootRelative(root, name);
      if (r.problem !== undefined) { out.push({ folder, root, status: 'rejected', source, reason: `${DECLARATION} ${r.problem}.` }); continue; }
      if (!(await fs.isExecutable(r.file))) {
        out.push({ folder, root, status: 'rejected', source, program: r.program, reason: `${r.program} is not an executable file at the repository's root.` });
        continue;
      }
      out.push({ folder, root, status: 'candidate', source, file: r.file, program: r.program, summary });
    }
  }
  return out;
}
