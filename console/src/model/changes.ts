// What changed (0009-workspaces-console FR-069): a page that says, for each repository that differs from its shared branch, what is incoming and what is only here, and why. It is
// built from the command line's own `repo status --details` and holds no reasons of its own: who, when, which part of the repository and the first paragraph of each message are the
// command line's. What a button does is an index into the actions built here.
import { t } from '../l10n';
import { asArray, asNumber, asObject, asString } from './json';
import { esc } from './welcome';

export interface Commit { hash: string; subject: string; date: string; author: string; files: number; why: string }
export interface Side { count: number; who: string; span: string; areas: string; commits: Commit[]; more: number }
export interface Button { label: string; icon: string; primary: boolean; ref: number }
export interface Card {
  name: string;
  where: string;
  chip: string;
  tone: 'ok' | 'warn' | 'bad';
  explain: string;
  rewritten: string;
  incoming: Side | null;
  outgoing: Side | null;
  held: string;
  buttons: Button[];
}
export interface Changes { title: string; intro: string; cards: Card[]; same: string[]; empty: string; top: Button[] }

/** What a button does. The sync is the command line's own `repo sync` for one repository, which goes through the one path every write takes. */
export type ChangesAction =
  | { kind: 'sync'; id: string }
  | { kind: 'fresh'; id: string }
  | { kind: 'again' }
  | { kind: 'copy'; text: string }
  | { kind: 'scm' };

const plural = (n: number, one: string, many = `${one}s`): string => `${n} ${n === 1 ? one : many}`;

function sideOf(raw: unknown): Side | null {
  const o = asObject(raw);
  const count = asNumber(o.count);
  if (!count) return null;
  const who = asArray(o.authors).map(asObject).map((a) => `${asString(a.name)} (${asNumber(a.commits)})`).join(', ');
  const first = asString(o.first);
  const last = asString(o.last);
  const areas = asArray(o.areas).map(asObject).map((a) => `${asString(a.name)} (${asNumber(a.files)})`).join(', ');
  const commits = asArray(o.commits).map(asObject).map((c): Commit => {
    const id = asString(c.id);
    const cut = id.indexOf('  ');
    return { hash: cut < 0 ? id : id.slice(0, cut), subject: cut < 0 ? '' : id.slice(cut + 2), date: asString(c.date), author: asString(c.author), files: asNumber(c.files), why: asString(c.text) };
  });
  return { count, who, span: first && last ? (first === last ? first : `${first} – ${last}`) : '', areas, commits, more: asNumber(o.more) };
}

const report = (c: Card): string => [`${c.name}: ${c.chip}`, c.explain, c.rewritten,
  ...([['Incoming', c.incoming], ['Only here', c.outgoing]] as const).flatMap(([title, s]) => (s ? [`${title} (${s.count}):`, ...s.commits.map((m) => `  ${m.hash} ${m.date} ${m.author}: ${m.subject}${m.why ? ` — ${m.why}` : ''}`)] : []))]
  .filter(Boolean).join('\n');

/** The document `repo status --details` returned (its `repositories`), as the page. */
export function buildChanges(rows: unknown[]): { model: Changes; actions: ChangesAction[] } {
  const actions: ChangesAction[] = [];
  const ref = (a: ChangesAction): number => { actions.push(a); return actions.length - 1; };
  const cards: Card[] = [];
  const same: string[] = [];
  for (const raw of rows) {
    const r = asObject(raw);
    const id = asString(r.id);
    const name = id.split('/').pop() ?? id;
    const incoming = sideOf(r.incoming);
    const outgoing = sideOf(r.outgoing);
    const dirty = r.dirty === true;
    if (r.cloned !== true || (!incoming && !outgoing && !dirty)) { same.push(name); continue; }
    const diverged = incoming !== null && outgoing !== null;
    const outSame = asNumber(r.same_change_outgoing);
    const inSame = asNumber(r.same_change_incoming);
    const held = dirty ? t('You have changes you have not committed yet, so nothing is moved for you.')
      : diverged ? t('Both sides moved on, so ws-host will not join them without you. Source Control shows both histories and lets you choose.') : '';
    const card: Card = {
      name, where: asString(r.path),
      chip: diverged ? t('Both sides moved on') : incoming ? t('{0} to bring in', plural(incoming.count, 'commit')) : outgoing ? t('{0} not shared yet', plural(outgoing.count, 'commit')) : t('Changes not committed'),
      tone: diverged || dirty ? 'bad' : 'warn',
      explain: asString(r.explain),
      rewritten: diverged && (outSame || inSame) ? t('{0} of the commits here and {1} of the incoming ones carry a change the other side already has under a different commit name. That usually means history was rewritten or squashed somewhere, so they are not new work.', outSame, inSame) : '',
      incoming, outgoing, held, buttons: [],
    };
    if (incoming && !outgoing && !dirty) card.buttons.push({ label: t('Update Now'), icon: 'sync', primary: true, ref: ref({ kind: 'sync', id }) });
    if (outgoing || dirty) card.buttons.push({ label: t('Start Fresh from GitHub…'), icon: 'discard', primary: false, ref: ref({ kind: 'fresh', id }) });
    card.buttons.push({ label: t('Open Source Control'), icon: 'source-control', primary: false, ref: ref({ kind: 'scm' }) });
    card.buttons.push({ label: t('Copy a Report'), icon: 'copy', primary: false, ref: ref({ kind: 'copy', text: report(card) }) });
    cards.push(card);
  }
  return {
    actions,
    model: {
      title: t('What changed'),
      intro: t('Each section compares a repository with its shared branch as of the last time GitHub was asked: what is incoming, what is only here, and why, in the words of the commits themselves.'),
      cards, same, empty: t('Everything matches its shared branch. Nothing is incoming and nothing is waiting to be shared.'),
      top: [{ label: t('Ask GitHub Again'), icon: 'refresh', primary: false, ref: ref({ kind: 'again' }) }],
    },
  };
}

const button = (b: Button): string => `<button class="${b.primary ? 'primary' : 'secondary'}" data-ref="${b.ref}"><span class="codicon codicon-${esc(b.icon)}" aria-hidden="true"></span>${esc(b.label)}</button>`;
const SHOWN = 5;

function commit(c: Commit): string {
  return `<li><div class="line"><code>${esc(c.hash)}</code><strong>${esc(c.subject)}</strong></div>
<div class="meta">${esc(c.date)} · ${esc(c.author)} · ${esc(plural(c.files, t('file')))}</div>${c.why ? `<p class="why">${esc(c.why)}</p>` : ''}</li>`;
}

function side(title: string, icon: string, s: Side | null): string {
  if (!s) return '';
  const head = s.commits.slice(0, SHOWN).map(commit).join('');
  const rest = s.commits.slice(SHOWN);
  const more = rest.length ? `<details><summary>${esc(t('Show {0} more', rest.length))}</summary><ul class="commits">${rest.map(commit).join('')}</ul></details>` : '';
  const cut = s.more ? `<p class="meta">${esc(t('… and {0} more that this list does not show; ask for more with --limit.', s.more))}</p>` : '';
  return `<div class="side"><h3><span class="codicon codicon-${esc(icon)}" aria-hidden="true"></span>${esc(title)} <span class="count">${s.count}</span></h3>
<p class="meta">${esc(t('by {0}', s.who))}${s.span ? ` · ${esc(s.span)}` : ''}</p>${s.areas ? `<p class="meta">${esc(t('touching {0}', s.areas))}</p>` : ''}
<ul class="commits">${head}</ul>${more}${cut}</div>`;
}

/** The page's body: every word of it escaped, every action an index. */
export function renderChanges(m: Changes): string {
  const cards = m.cards.map((c) => `<section class="card wide" aria-label="${esc(c.name)}">
  <header><h2>${esc(c.name)}</h2><span class="chip ${c.tone}">${esc(c.chip)}</span></header>
  <p class="folder">${esc(c.where)}</p>
  <p class="summary">${esc(c.explain)}</p>${c.rewritten ? `<div class="note" role="note"><span class="codicon codicon-history" aria-hidden="true"></span><p>${esc(c.rewritten)}</p></div>` : ''}
  <div class="sides">${side(t('Incoming'), 'arrow-down', c.incoming)}${side(t('Only here'), 'arrow-up', c.outgoing)}</div>${c.held ? `<p class="held">${esc(c.held)}</p>` : ''}
  <div class="buttons">${c.buttons.map(button).join('')}</div>
</section>`).join('\n');
  return `<main>
<header class="hero"><h1>${esc(m.title)}</h1><p>${esc(m.intro)}</p><div class="buttons">${m.top.map(button).join('')}</div></header>
${m.cards.length ? '' : `<div class="note" role="status"><span class="codicon codicon-check" aria-hidden="true"></span><p>${esc(m.empty)}</p></div>`}
<div class="stack">${cards}</div>
${m.same.length ? `<p class="meta">${esc(t('Up to date: {0}.', m.same.join(', ')))}</p>` : ''}
</main>`;
}

export const CHANGES_CSS = `
.stack { display: flex; flex-direction: column; gap: 16px; margin: 24px 0; }
.card.wide { gap: 12px; }
.sides { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 24px; }
.side h3 { display: flex; align-items: center; gap: 8px; margin: 0 0 4px; font-size: 1em; text-transform: none; letter-spacing: 0; color: var(--vscode-foreground); }
.count { padding: 0 8px; border-radius: 999px; background: var(--vscode-badge-background); color: var(--vscode-badge-foreground); font-size: .85em; }
.meta { margin: 2px 0; font-size: .9em; color: var(--vscode-descriptionForeground); }
.commits { list-style: none; margin: 8px 0 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.commits li { padding-left: 12px; border-left: 2px solid var(--vscode-widget-border, var(--vscode-panel-border, transparent)); }
.commits .line { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.commits code { font-family: var(--vscode-editor-font-family); color: var(--vscode-textLink-foreground); }
.why { margin: 2px 0 0; color: var(--vscode-foreground); }
details { margin-top: 8px; } summary { cursor: pointer; color: var(--vscode-textLink-foreground); }
.held { margin: 0; color: var(--vscode-editorWarning-foreground, var(--vscode-foreground)); }
.hero .buttons { padding-top: 16px; }
`;
