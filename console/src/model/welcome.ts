// The welcome page (0009-workspaces-console FR-065): one page that is the first thing a person sees, with a section for each repository that declares a command line of its own,
// what each is for, how it stands, and where to get help on it. It is built from what the command lines said (their summaries and their help topics) and holds no
// words about any repository of its own. What a button does is an index into the actions built here, so that nothing a page says can name a command of its own.
import { t } from '../l10n';

export interface WelcomeRepo {
  key: string;
  name: string;
  folder: string;
  summary: string;
  state: 'unloaded' | 'untrusted' | 'ready' | 'unavailable' | 'update';
  reason: string;
  /** How many things need the person, from Home. */
  needs: number;
  topics: Array<{ topic: string; summary: string }>;
}

export interface WelcomeInput { repos: WelcomeRepo[]; signedOut: boolean; updates: { waiting: boolean; plain: string } }

/** What a button does. Only these commands of this extension can be named, and only by this module. */
export type WelcomeAction =
  | { kind: 'ext'; command: 'signIn' | 'updateEverything' | 'addRepository' | 'openWalkthrough' | 'showHome' | 'setUpEverything' | 'lookForUpdates' }
  | { kind: 'learn'; repo: string }
  | { kind: 'topic'; repo: string; topic: string };

export interface Button { label: string; icon: string; primary: boolean; ref: number }
export interface Note { icon: string; text: string; buttons: Button[] }
export interface Card {
  name: string;
  folder: string;
  summary: string;
  status: 'ok' | 'warn' | 'bad';
  statusText: string;
  topics: Array<{ label: string; summary: string; ref: number }>;
  buttons: Button[];
}
export interface Welcome { title: string; intro: string; notes: Note[]; cards: Card[]; empty: Note | null; footer: Button[] }

export function buildWelcome(input: WelcomeInput): { model: Welcome; actions: WelcomeAction[] } {
  const actions: WelcomeAction[] = [];
  const ref = (a: WelcomeAction): number => { actions.push(a); return actions.length - 1; };
  const ext = (command: Extract<WelcomeAction, { kind: 'ext' }>['command'], label: string, icon: string, primary = false): Button => ({ label, icon, primary, ref: ref({ kind: 'ext', command }) });

  const notes: Note[] = [];
  if (input.signedOut) notes.push({ icon: 'github', text: t('You are not signed in to GitHub yet. Sign in to copy private repositories.'), buttons: [ext('signIn', t('Sign In to GitHub'), 'github', true)] });
  if (input.updates.waiting) notes.push({ icon: 'cloud-download', text: input.updates.plain.replace(/\s+(Update it with|Bring everything up to date with):.*$/, ''), buttons: [ext('updateEverything', t('Update Everything'), 'sync', true)] });

  const cards = input.repos.map((r): Card => {
    const learnable = r.state === 'ready' && r.topics.length > 0;
    const status = r.state === 'ready' ? (r.needs ? 'warn' : 'ok') : 'bad';
    const statusText = r.state === 'ready' ? (r.needs ? t('{0} {1} you', r.needs, r.needs === 1 ? t('thing needs') : t('things need')) : t('Ready'))
      : r.state === 'untrusted' ? t('Waiting for you to trust this workspace')
      : r.state === 'update' ? t('Update Workspaces Console to read it')
      : t('Not ready yet');
    const buttons: Button[] = [];
    if (r.state === 'ready') buttons.push({ label: t('Open in Home'), icon: 'home', primary: !learnable, ref: ref({ kind: 'ext', command: 'showHome' }) });
    if (learnable) buttons.unshift({ label: t('All help topics'), icon: 'book', primary: true, ref: ref({ kind: 'learn', repo: r.key }) });
    if (r.state === 'unavailable') buttons.push(ext('setUpEverything', t('Install Everything'), 'rocket', true));
    return { name: r.name, folder: r.folder, summary: r.summary || r.reason, status, statusText,
      topics: r.state === 'ready' ? r.topics.slice(0, 6).map((x) => ({ label: x.topic, summary: x.summary, ref: ref({ kind: 'topic', repo: r.key, topic: x.topic }) })) : [], buttons };
  });

  const empty: Note | null = input.repos.length ? null
    : { icon: 'repo', text: t('No repository in this window has a command line of its own yet. Add one by its address and it appears here.'), buttons: [ext('addRepository', t('Add Repository'), 'repo-clone', true)] };

  return {
    actions,
    model: {
      title: t('Welcome to Workspaces'),
      intro: t('Everything for your work, set up and kept up to date. Each section below is a repository with its own tools: see what it is for, how it stands, and ask for help on any part of it.'),
      notes, cards, empty,
      footer: [ext('addRepository', t('Add Repository'), 'repo-clone'), ext('openWalkthrough', t('Getting Started'), 'rocket'), ext('lookForUpdates', t('Look for Updates'), 'cloud-download')],
    },
  };
}

export const esc = (s: string): string => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');

const button = (b: Button): string => `<button class="${b.primary ? 'primary' : 'secondary'}" data-ref="${b.ref}"><span class="codicon codicon-${esc(b.icon)}" aria-hidden="true"></span>${esc(b.label)}</button>`;
const note = (n: Note): string => `<div class="note" role="status"><span class="codicon codicon-${esc(n.icon)}" aria-hidden="true"></span><p>${esc(n.text)}</p><div class="buttons">${n.buttons.map(button).join('')}</div></div>`;

/** The page's body: every word of it escaped, every action an index. */
export function renderWelcome(w: Welcome): string {
  const cards = w.cards.map((c) => `<section class="card" aria-label="${esc(c.name)}">
  <header><h2>${esc(c.name)}</h2><span class="chip ${c.status}">${esc(c.statusText)}</span></header>
  <p class="folder">${esc(c.folder)}</p>
  <p class="summary">${esc(c.summary)}</p>${c.topics.length ? `
  <h3>${esc(t('Get help on'))}</h3>
  <ul class="topics">${c.topics.map((x) => `<li><button class="link" data-ref="${x.ref}" title="${esc(x.summary)}"><span class="codicon codicon-book" aria-hidden="true"></span>${esc(x.label)}</button>${x.summary ? `<span class="what">${esc(x.summary)}</span>` : ''}</li>`).join('')}</ul>` : ''}
  <div class="buttons">${c.buttons.map(button).join('')}</div>
</section>`).join('\n');
  return `<main>
<header class="hero"><h1>${esc(w.title)}</h1><p>${esc(w.intro)}</p></header>
${w.notes.map(note).join('\n')}
${w.empty ? note(w.empty) : ''}
<div class="grid">${cards}</div>
<footer><div class="buttons">${w.footer.map(button).join('')}</div></footer>
</main>`;
}
