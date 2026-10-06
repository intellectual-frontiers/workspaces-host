// What a command made (0041-command-line FR-075): `data.outputs`, paths relative to the repository, that an editor offers to open. A path that leaves the repository,
// is absolute or is not text names nothing.
import * as path from 'path';
import { asArray, asString } from './json';
import type { Doc } from './wire';

export function outputsOf(doc: Doc | null): string[] {
  if (!doc) return [];
  const out: string[] = [];
  for (const v of asArray(doc.data.outputs)) {
    const p = asString(v).trim();
    if (!p || path.isAbsolute(p) || p.split(/[\\/]/).includes('..')) continue;
    out.push(p);
  }
  return [...new Set(out)];
}
