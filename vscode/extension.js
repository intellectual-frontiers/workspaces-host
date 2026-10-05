"use strict";
// The editor extension (0004-editor-extension). Plain JavaScript, no build step, no dependencies.
// It holds no behavior of its own: it discovers the orchestrators of trusted repositories, runs
// `<name> command list --json` and `<name> <noun> <verb> ... --json|--html`, renders what comes back and runs a
// resource's actions by invoking the orchestrator. Its pure logic is exported under `_test` so Node can test it
// with VS Code's API replaced by a stand-in.

const cp = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const SUPPORTED_SCHEMA = 1;          // the newest schema version this extension can read (0041-command-line FR-019)
const OWN = "ws-host";               // the one orchestrator this extension names: its own (0004 FR-002)

// ───────────────────────── pure logic ─────────────────────────

function parseSchema(schema) {
  const m = /^([\w.-]+)\/([\w-]+)@(\d+)$/.exec(String(schema || ""));
  return m ? { name: m[1], kind: m[2], version: Number(m[3]) } : null;
}

/** 0004 FR-010: a document newer than this extension understands, or one that is not a resource at all. */
function readability(doc) {
  const s = parseSchema(doc && doc.schema);
  if (!s) return { ok: false, reason: "not-a-resource" };
  if (s.version > SUPPORTED_SCHEMA) return { ok: false, reason: "update-needed", schema: s };
  return { ok: true, schema: s };
}

const UPDATE_NEEDED = "ws-host has been updated and shows things this editor extension does not know how to read yet. Update the extension to see them.";

function flagName(name) { return "--" + String(name).toLowerCase().replace(/_/g, "-"); }

/** The command line's arguments for an action, built from `command show` (0004 FR-007): positional arguments in
 *  their declared order, then options. `fields` are keyed by argument name (or by the option's flag name). */
function buildArgv(info, action, extra) {
  const words = String(action.command).split(" ").filter(Boolean);
  const fields = Object.assign({}, action.fields || {}, extra || {});
  const argv = words.slice();
  const used = new Set();
  for (const a of (info && info.arguments) || []) {
    if (fields[a.name] === undefined || fields[a.name] === null) continue;
    used.add(a.name);
    for (const v of [].concat(fields[a.name])) argv.push(String(v));
  }
  const flags = new Map(((info && info.options) || []).map(o => [o.flag, o]));
  for (const [name, v] of Object.entries(fields)) {
    if (used.has(name) || v === null || v === undefined || v === false) continue;
    const flag = flags.has(name) ? name : flagName(name);
    if (v === true) argv.push(flag);
    else for (const item of [].concat(v)) argv.push(flag, String(item));
  }
  return argv;
}

/** The arguments an action still needs from the person, by `needs` or by required arguments with no value (0004 FR-007). */
function missingArgs(info, action) {
  const fields = action.fields || {};
  const names = new Set(action.needs || []);
  for (const a of (info && info.arguments) || []) {
    if (a.required && (fields[a.name] === undefined || fields[a.name] === null || [].concat(fields[a.name]).length === 0)) names.add(a.name);
  }
  const all = [...((info && info.arguments) || []), ...((info && info.options) || [])];
  return [...names].map(n => all.find(a => a.name === n || a.flag === n) || { name: n, type: "STRING", choices: [] });
}

function surfaceExposed(surfaces) { return Array.isArray(surfaces) && surfaces.includes("editor"); }

/** Whether and how an action may be offered: exposed ones are buttons; others are shown disabled with the command to show. */
function classifyAction(a) {
  const exposed = surfaceExposed(a.surfaces) && a.enabled !== false;
  return {
    button: exposed,
    decision: a.category === "decision",
    reason: a.enabled === false ? (a.reason || "not available right now") : (!surfaceExposed(a.surfaces) ? "this one is run in a terminal" : null),
    showCommand: typeof a.cli === "string" && a.cli.length > 0,
  };
}

/** Every warning or failure of the doctor as a suggestion a person can act on (0004 FR-019): the plain words, the line to type, the
 *  action that runs it, or what the person does themselves. */
function suggestionsFor(doc) {
  const checks = (doc && doc.data && doc.data.checks) || [];
  const actions = (doc && doc.actions) || [];
  return checks.filter(c => c.status === "warn" || c.status === "fail").map(c => {
    const a = Number.isInteger(c.action) ? actions[c.action] || null : null;
    return { name: c.name, level: c.status === "fail" ? "error" : "warn", plain: String(c.detail || ""), cli: c.cli || (a && a.cli) || null, action: a, todo: c.todo || null };
  });
}

function statusFor(doc) {
  const r = readability(doc);
  if (!r.ok) return { text: "$(warning) Update needed", level: "warn", tooltip: UPDATE_NEEDED, suggestions: [] };
  const plain = (doc.data && doc.data.plain) || "";
  const suggestions = suggestionsFor(doc);
  const bad = suggestions.filter(s => s.level === "error").length;
  if (bad) return { text: `$(error) ${bad} thing${bad === 1 ? "" : "s"} to fix \u2014 click to fix`, level: "error", tooltip: plain + " Click to see what to do.", suggestions };
  if (suggestions.length) return { text: `$(warning) ${suggestions.length} suggestion${suggestions.length === 1 ? "" : "s"} \u2014 click to fix`, level: "warn", tooltip: plain + " Click to see what to do.", suggestions };
  return { text: "$(pass) " + short(plain), level: "ok", tooltip: plain + " Click to check again.", suggestions: [] };
}

function short(s) { return s.length > 60 ? s.slice(0, 57) + "..." : s; }

/** A finding's file and line where it names one, else the repository (0004 FR-009). */
function parseFinding(f, root) {
  const where = String((f && f.where) || "");
  const m = /^(.+?):(\d+)(?::\d+)?$/.exec(where);
  const rel = m ? m[1] : where.split(" ")[0];
  const line = m ? Math.max(0, Number(m[2]) - 1) : 0;
  const file = rel && !rel.includes(" ") && !path.isAbsolute(rel) && /[./]/.test(rel) ? path.join(root, rel) : root;
  return { file, line, message: String((f && f.message) || ""), level: f && f.level === "warning" ? "warning" : "error" };
}

/** The page the webview shows: ws-host's own HTML with its policy tightened to one nonce'd script that only posts a
 *  button's index back to the extension (0004 FR-006). Nothing remote is allowed. */
function wrapHtml(html, nonce) {
  const csp = `default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}'`;
  const script = `<script nonce="${nonce}">const v=acquireVsCodeApi();document.addEventListener("click",e=>{` +
    `const b=e.target.closest("[data-action]");if(b&&!b.disabled){v.postMessage({type:"action",index:Number(b.dataset.action)})}` +
    `const s=e.target.closest("[data-show]");if(s){v.postMessage({type:"show",index:Number(s.dataset.show)})}});</script>`;
  let out = html.replace(/<meta http-equiv="Content-Security-Policy"[^>]*>/i, `<meta http-equiv="Content-Security-Policy" content="${csp}">`);
  if (!/Content-Security-Policy/i.test(out)) out = out.replace("<head>", `<head><meta http-equiv="Content-Security-Policy" content="${csp}">`);
  return out.replace("</body>", script + "</body>");
}

class LineSplitter {
  constructor(onLine) { this.buf = ""; this.onLine = onLine; }
  push(chunk) {
    this.buf += chunk;
    let i;
    while ((i = this.buf.indexOf("\n")) >= 0) { const line = this.buf.slice(0, i); this.buf = this.buf.slice(i + 1); if (line.trim()) this.onLine(line); }
  }
  end() { if (this.buf.trim()) this.onLine(this.buf); this.buf = ""; }
}

const ENTITIES = { "&quot;": '"', "&#x27;": "'", "&#39;": "'", "&lt;": "<", "&gt;": ">", "&amp;": "&" };
function unescapeHtml(s) { return s.replace(/&(?:quot|#x27|#39|lt|gt|amp);/g, m => ENTITIES[m]); }

/** The resource an HTML rendering carries (`data-resource` on its body), so a page can be acted on without running the
 *  command again. Null when the page carries none. */
function resourceOfPage(html) {
  const m = /<body[^>]*\sdata-resource="([^"]*)"/.exec(html);
  if (!m) return null;
  try { return JSON.parse(unescapeHtml(m[1])); } catch (_) { return null; }
}

/** Splits a stream of HTML pages, one per resource, as they complete (0004 FR-008). */
class PageSplitter {
  constructor(onPage) { this.buf = ""; this.onPage = onPage; }
  push(chunk) {
    this.buf += chunk;
    const re = /<!doctype html>/ig; const at = []; let m;
    while ((m = re.exec(this.buf))) at.push(m.index);
    for (let i = 0; i + 1 < at.length; i++) this.onPage(this.buf.slice(at[i], at[i + 1]));
    if (at.length > 1) this.buf = this.buf.slice(at[at.length - 1]);
  }
  end() { if (this.buf.trim()) this.onPage(this.buf); this.buf = ""; }
}

/** Gather the report a person can paste to a person or an AI (0004 FR-015). `ws-host` already removed every secret. */
function helpReport(context, doctor) {
  const lines = ["# Workspace help report", "", "Generated by the Workspace extension from `ws-host context` and `ws-host doctor`. It holds no passwords or tokens.", ""];
  for (const [title, doc] of [["Context", context], ["Doctor", doctor]]) {
    lines.push("## " + title, "", "```json", JSON.stringify(doc && doc.data !== undefined ? doc.data : doc, null, 2), "```", "");
  }
  return lines.join("\n");
}

/** Which launcher files at a repository's root could be an orchestrator: executable, extensionless, a POSIX sh script. */
function launcherCandidates(root, fsApi) {
  const f = fsApi || fs;
  let names = [];
  try { names = f.readdirSync(root); } catch (_) { return []; }
  const out = [];
  for (const n of names) {
    if (n.includes(".")) continue;
    const p = path.join(root, n);
    try {
      const st = f.statSync(p);
      if (!st.isFile() || !(st.mode & 0o111)) continue;
      const head = f.readFileSync(p, "utf8").slice(0, 64);
      if (/^#!\s*\/bin\/sh\b/.test(head)) out.push(p);
    } catch (_) { /* unreadable: not a candidate */ }
  }
  return out;
}

// ───────────────────────── running orchestrators ─────────────────────────

function run(launcher, argv, opts) {
  opts = opts || {};
  return new Promise(resolve => {
    const env = Object.assign({}, process.env, { WS_HOST_SURFACE: "editor" }, opts.env || {});
    let child;
    try { child = cp.spawn(launcher, argv, { cwd: opts.cwd, env }); }
    catch (e) { return resolve({ code: 127, docs: [], text: "", err: String(e) }); }
    const docs = []; let text = ""; let err = "";
    const split = new LineSplitter(line => {
      if (opts.raw) { text += line + "\n"; return; }
      try { const d = JSON.parse(line); docs.push(d); if (opts.onDoc) opts.onDoc(d); } catch (_) { text += line + "\n"; }
    });
    child.stdout.on("data", c => split.push(String(c)));
    child.stderr.on("data", c => { err += String(c); });
    const timer = opts.timeout ? setTimeout(() => child.kill(), opts.timeout) : null;
    child.on("error", e => { if (timer) clearTimeout(timer); resolve({ code: 127, docs, text, err: String(e) }); });
    child.on("close", code => { if (timer) clearTimeout(timer); split.end(); resolve({ code, docs, text, err }); });
  });
}

/** Runs a command once with --html and returns each page and the resource it carries. Nothing is run twice. */
function runPages(launcher, argv, opts) {
  opts = opts || {};
  return new Promise(resolve => {
    const env = Object.assign({}, process.env, { WS_HOST_SURFACE: "editor" });
    let child;
    try { child = cp.spawn(launcher, [...argv, "--html"], { cwd: opts.cwd, env }); } catch (e) { return resolve({ code: 127, pages: [], err: String(e) }); }
    const pages = []; let err = "";
    const split = new PageSplitter(html => { const page = { html, doc: resourceOfPage(html) }; pages.push(page); if (opts.onPage) opts.onPage(page); });
    child.stdout.on("data", c => split.push(String(c)));
    child.stderr.on("data", c => { err += String(c); });
    child.on("error", e => resolve({ code: 127, pages, err: String(e) }));
    child.on("close", code => { split.end(); resolve({ code, pages, err }); });
  });
}

async function runJson(launcher, argv, opts) {
  const r = await run(launcher, [...argv, "--json"], opts);
  return Object.assign(r, { doc: r.docs[r.docs.length - 1] });
}

function findOwn() {
  const dirs = (process.env.PATH || "").split(path.delimiter).concat([path.join(os.homedir(), ".local", "bin")]);
  for (const d of dirs) { const p = path.join(d, OWN); try { fs.accessSync(p, fs.constants.X_OK); return p; } catch (_) { /* next */ } }
  return null;
}

/** 0004 FR-002, FR-003: ws-host itself, then the launcher of every trusted, cloned repository that answers `command list`. */
async function discover(log) {
  const found = [];
  const own = findOwn();
  if (!own) return { orchestrators: [], problem: "ws-host is not installed on this machine, so there is nothing to show yet." };
  const seen = new Set();
  const addFrom = async (launcher, root) => {
    const r = await runJson(launcher, ["command", "list"], { cwd: root, timeout: 20000 });
    const d = r.doc; const s = d && parseSchema(d.schema);
    if (!s || s.kind !== "command-list") return;
    if (seen.has(s.name)) return;
    seen.add(s.name);
    const rd = readability(d);
    found.push({ name: s.name, launcher, root, audience: d.audience || "unstated", commands: (d.data && d.data.commands) || [], readable: rd.ok });
  };
  await addFrom(own, undefined);
  const repos = await runJson(own, ["repo", "list"], { timeout: 30000 });
  const list = (repos.doc && repos.doc.data && repos.doc.data.repositories) || [];
  for (const r of list) {
    if (!r.trusted || !r.cloned) continue;
    for (const c of launcherCandidates(r.path)) { try { await addFrom(c, r.path); } catch (e) { if (log) log(String(e)); } }
  }
  return { orchestrators: found };
}

// ───────────────────────── VS Code ─────────────────────────

function activate(context) {
  const vscode = require("vscode");
  const out = vscode.window.createOutputChannel("Workspace");
  const log = m => out.appendLine(m);
  const diagnostics = vscode.languages.createDiagnosticCollection("workspace");
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
  status.command = "wsHost.showSuggestions";
  status.show();
  context.subscriptions.push(out, diagnostics, status);

  let state = { orchestrators: [], problem: null };
  const infoCache = new Map();
  const tree = new vscode.EventEmitter();

  const restricted = () => vscode.workspace.isTrusted === false;     // 0004 FR-003
  const refuseRestricted = () => {
    if (!restricted()) return false;
    status.text = "$(shield) Turn on workspace trust to use Workspace";
    status.tooltip = "VS Code is in Restricted Mode, so no tool of your repositories is run. Trust this folder to continue.";
    status.backgroundColor = new vscode.ThemeColor("statusBarItem.warningBackground");
    return true;
  };

  const orchestrator = name => state.orchestrators.find(o => o.name === name);

  async function commandInfo(o, id) {
    const key = o.name + ":" + id;
    if (infoCache.has(key)) return infoCache.get(key);
    const r = await runJson(o.launcher, ["command", "show", ...id.split(" ")], { cwd: o.root, timeout: 20000 });
    const info = r.doc && r.doc.data ? r.doc.data : null;
    infoCache.set(key, info);
    return info;
  }

  async function ask(arg) {
    const label = `${arg.name}${arg.help ? " - " + arg.help : ""}`;
    if (arg.choices && arg.choices.length) {
      const pick = await vscode.window.showQuickPick(arg.choices, { title: arg.name, placeHolder: label, canPickMany: !!arg.many && arg.type !== "FORGE" });
      return pick;
    }
    return vscode.window.showInputBox({ title: arg.name, prompt: label, ignoreFocusOut: true });
  }

  /** Runs an action by invoking the orchestrator. A `decision` always goes through a modal first (0004 FR-011). */
  async function runAction(o, action) {
    if (refuseRestricted()) return;
    const info = await commandInfo(o, action.command);
    const fields = Object.assign({}, action.fields || {});
    for (const arg of missingArgs(info, action)) {
      const v = await ask(arg);
      if (v === undefined || (Array.isArray(v) && v.length === 0)) return;   // cancelled: nothing runs
      fields[arg.name || arg.flag] = v;
    }
    const act = Object.assign({}, action, { fields });
    const extra = {};
    if (action.category === "decision") {
      const what = action.label || action.command;
      const yes = "Yes, do it";
      const answer = await vscode.window.showWarningMessage(
        `Only you can decide this: ${what}. ${act.cli ? "It runs: " + act.cli : ""}`.trim(), { modal: true, detail: "Nothing changes unless you choose Yes." }, yes);
      if (answer !== yes) return;
      extra.confirmed = true;
    }
    const argv = buildArgv(info, act, extra);
    await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: action.label || action.command, cancellable: false }, async progress => {
      const r = await runPages(o.launcher, argv, {
        cwd: o.root,
        onPage: page => {
          const d = page.doc;
          const p = d && d.data && d.data.plain;
          if (p) progress.report({ message: p });
          if (d && d.kind === "auth-code") offerCode(d);
        },
      });
      const last = r.pages[r.pages.length - 1];
      if (last && last.doc) await showPage(o, last, argv);
      else vscode.window.showErrorMessage("That did not give an answer I could read. " + (r.err || "").slice(0, 200));
      await refresh();
    });
  }

  function offerCode(d) {
    const code = d.data.code, url = d.data.url;
    const copy = "Copy code and open browser";
    vscode.window.showInformationMessage(`To sign in, open ${url} and type this code: ${code}`, copy).then(async a => {
      if (a === copy) { await vscode.env.clipboard.writeText(code); await vscode.env.openExternal(vscode.Uri.parse(url)); }
    });
  }

  const panels = new Map();
  async function showPage(o, page, argv) {
    const doc = page.doc;
    const rd = readability(doc);
    const title = (doc.data && doc.data.plain) || doc.kind || "Result";
    const key = o.name + " " + (argv || []).join(" ");
    let entry = panels.get(key);
    if (!entry) {
      const panel = vscode.window.createWebviewPanel("wsHostResource", short(title), vscode.ViewColumn.Beside, { enableScripts: true, localResourceRoots: [] });
      entry = { panel, listener: null, actions: [] };
      panels.set(key, entry);
      panel.onDidDispose(() => panels.delete(key));
      entry.listener = panel.webview.onDidReceiveMessage(async m => {
        const a = entry.actions[m.index];
        if (!a) return;
        if (m.type === "show") return showCommand(a);
        if (!classifyAction(a).button) return showCommand(a);
        await runAction(o, a);
      });
    }
    entry.panel.title = short(title);
    if (!rd.ok) {
      entry.actions = [];
      entry.panel.webview.html = wrapHtml(`<!doctype html><html><head></head><body><h1>Update needed</h1><p>${UPDATE_NEEDED}</p></body></html>`, nonce());
      return;
    }
    entry.actions = doc.actions || [];
    entry.panel.webview.html = wrapHtml(page.html, nonce());
    if (doc.kind === "check") reportFindings(o, doc);
  }

  function showCommand(a) {
    if (!a.cli) return vscode.window.showInformationMessage("This one asks you for a value, so there is no single line to paste. Use its button.");
    return vscode.window.showInformationMessage(a.cli, "Copy").then(x => x === "Copy" && vscode.env.clipboard.writeText(a.cli));
  }

  function reportFindings(o, doc) {
    diagnostics.clear();
    const by = new Map();
    for (const s of (doc.data && doc.data.sections) || []) for (const f of s.findings || []) {
      const p = parseFinding(f, o.root || (vscode.workspace.workspaceFolders || [{ uri: { fsPath: os.homedir() } }])[0].uri.fsPath);
      const range = new vscode.Range(p.line, 0, p.line, 1000);
      const d = new vscode.Diagnostic(range, `${s.name}: ${p.message}`, p.level === "warning" ? vscode.DiagnosticSeverity.Warning : vscode.DiagnosticSeverity.Error);
      d.source = o.name;
      const k = p.file;
      if (!by.has(k)) by.set(k, []);
      by.get(k).push(d);
    }
    for (const [file, ds] of by) diagnostics.set(vscode.Uri.file(file), ds);
  }

  async function refresh() {
    if (refuseRestricted()) { tree.fire(); return; }
    status.backgroundColor = undefined;
    status.text = "$(sync~spin) Checking your workspace...";
    state = await discover(log);
    infoCache.clear();
    const own = orchestrator(OWN);
    if (!own) { status.text = "$(warning) Workspace tools not installed"; status.tooltip = state.problem || ""; tree.fire(); return; }
    const d = (await runJson(own.launcher, ["doctor"], { timeout: 120000 })).doc;
    const s = statusFor(d);
    lastStatus = s;
    status.text = s.text; status.tooltip = s.tooltip;
    status.backgroundColor = s.level === "error" ? new vscode.ThemeColor("statusBarItem.errorBackground") : s.level === "warn" ? new vscode.ThemeColor("statusBarItem.warningBackground") : undefined;
    tree.fire();
    notifySuggestions(s);
    const auth = (await runJson(own.launcher, ["auth", "status"], { timeout: 60000 })).doc;
    const out_ = auth && auth.data && auth.data.forges && auth.data.forges.find(f => f.signed_in === false && f.name === "github.com");
    if (out_ && !signInOffered) {
      signInOffered = true;
      const go = "Sign in";
      vscode.window.showInformationMessage("You are not signed in to GitHub, so private repositories cannot be copied.", go).then(a => { if (a === go) signIn(); });
    }
  }
  let signInOffered = false;
  let lastStatus = { suggestions: [], level: "ok" };
  let notifiedFor = "";

  /** One suggestion: what is wrong, the line that fixes it, and buttons to run or copy it, or what the person does themselves (0004 FR-019). */
  async function showSuggestion(s) {
    const own = orchestrator(OWN);
    const lines = [s.plain];
    if (s.cli) lines.push(`Type: ${s.cli}`);
    if (s.todo) lines.push(s.todo);
    const run = s.action ? `Run: ${s.action.label}` : null;
    const buttons = [run, s.cli ? "Copy command" : null].filter(Boolean);
    const picked = await vscode.window.showInformationMessage(lines.join("  "), ...buttons);
    if (picked && picked === run && own) await runAction(own, s.action);
    else if (picked === "Copy command") await vscode.env.clipboard.writeText(s.cli);
  }

  /** A click on the status bar: the list of what to do, never a silent refresh. When all is well it checks again and says so. */
  async function showSuggestions() {
    if (refuseRestricted()) return;
    if (!lastStatus.suggestions.length) {
      await refresh();
      if (lastStatus.suggestions.length) return showSuggestions();
      vscode.window.showInformationMessage(lastStatus.level === "ok" && lastStatus.tooltip ? lastStatus.tooltip.replace(/ Click to check again\.$/, "") : "Your workspace is ready.");
      return;
    }
    const items = lastStatus.suggestions.map(s => ({
      label: `${s.level === "error" ? "$(error)" : "$(warning)"} ${s.name}`, description: s.plain,
      detail: s.cli ? `Type: ${s.cli}` : s.todo ? `What you do yourself: ${s.todo}` : "", suggestion: s,
    }));
    const pick = await vscode.window.showQuickPick(items, { title: "What to fix", placeHolder: "Pick one to see how to fix it", matchOnDescription: true });
    if (pick) await showSuggestion(pick.suggestion);
  }

  /** Once per set of suggestions: a message with the fix to run and a way to see them all (0004 FR-019). */
  function notifySuggestions(s) {
    const key = s.suggestions.map(x => x.name).join("|");
    if (!key || key === notifiedFor) return;
    notifiedFor = key;
    const first = s.suggestions[0];
    const run = s.suggestions.length === 1 && first.action ? `Run: ${first.action.label}` : null;
    const all = "Show all";
    const n = s.suggestions.length;
    const text = n === 1 ? `One suggestion for your machine: ${first.plain}` : `${n} suggestions for your machine. The first: ${first.plain}`;
    vscode.window.showInformationMessage(text, ...[run, all].filter(Boolean)).then(async a => {
      if (a === run) { const own = orchestrator(OWN); if (own) await runAction(own, first.action); }
      else if (a === all) await showSuggestions();
    });
  }

  async function signIn() {
    const own = orchestrator(OWN);
    if (own) await runAction(own, { label: "Sign in to GitHub", command: "auth new", fields: { forge: "github" }, category: "setup", surfaces: ["terminal", "editor"], cli: "ws-host auth new github" });
  }

  async function runChecks() {
    if (refuseRestricted()) return;
    diagnostics.clear();
    for (const o of state.orchestrators) {
      if (!o.commands.some(c => c.id === "check")) continue;
      const r = await runJson(o.launcher, ["check"], { cwd: o.root, timeout: 600000 });
      if (r.doc && r.doc.kind === "check") reportFindings(o, r.doc);
    }
    vscode.window.showInformationMessage("Checks finished. Anything found is in the Problems panel.");
  }

  /** Learn: the topics the orchestrator's own `help` lists, as a quick-pick, shown as any other resource (0004 FR-018). */
  async function learn() {
    if (refuseRestricted()) return;
    const o = orchestrator(OWN);
    if (!o || !o.commands.some(c => c.id === "help")) { vscode.window.showInformationMessage("There are no help pages to show yet."); return; }
    const info = await commandInfo(o, "help");
    const arg = ((info && info.arguments) || []).find(a => a.choices && a.choices.length);
    const topic = arg ? await vscode.window.showQuickPick(arg.choices, { title: "Learn", placeHolder: "What do you want to learn?" }) : undefined;
    if (!topic) return;
    const argv = ["help", topic];
    const r = await runPages(o.launcher, argv, { cwd: o.root });
    const last = r.pages[r.pages.length - 1];
    if (last && last.doc) await showPage(o, last, argv);
  }

  async function getHelp() {
    const own = orchestrator(OWN) || { launcher: findOwn() };
    if (!own.launcher) { vscode.window.showErrorMessage("ws-host is not installed, so there is nothing to report yet."); return; }
    const ctx = await runJson(own.launcher, ["context"], { timeout: 120000 });
    const dr = await runJson(own.launcher, ["doctor"], { timeout: 120000 });
    const text = helpReport(ctx.doc, dr.doc);
    await vscode.env.clipboard.writeText(text);
    const doc = await vscode.workspace.openTextDocument({ content: text, language: "markdown" });
    await vscode.window.showTextDocument(doc, { preview: true });
    vscode.window.showInformationMessage("The help report is copied. Paste it to a person or an AI to get help.");
  }

  // The tree: orchestrator (with its audience) > noun > command (0004 FR-005).
  const provider = {
    onDidChangeTreeData: tree.event,
    getTreeItem: n => n.item,
    getChildren: n => {
      if (!n) {
        if (restricted()) return [leaf("Turn on workspace trust to use Workspace", "shield")];
        if (state.problem) return [leaf(state.problem, "warning")];
        return state.orchestrators.map(o => {
          const it = new vscode.TreeItem(o.name, vscode.TreeItemCollapsibleState.Expanded);
          it.description = `${o.audience}${o.readable ? "" : " - update needed"}`;
          it.iconPath = new vscode.ThemeIcon("symbol-namespace");
          return { item: it, o, kind: "orchestrator" };
        });
      }
      if (n.kind === "orchestrator") {
        if (!n.o.readable) return [leaf(UPDATE_NEEDED, "warning")];
        const nouns = new Map();
        for (const c of n.o.commands.filter(c => surfaceExposed(c.surfaces))) {
          const noun = c.id.includes(" ") ? c.id.split(" ")[0] : "everything";
          if (!nouns.has(noun)) nouns.set(noun, []);
          nouns.get(noun).push(c);
        }
        return [...nouns].map(([noun, cmds]) => {
          const it = new vscode.TreeItem(noun, vscode.TreeItemCollapsibleState.Collapsed);
          return { item: it, o: n.o, kind: "noun", cmds };
        });
      }
      if (n.kind === "noun") return n.cmds.map(c => {
        const it = new vscode.TreeItem(c.id, vscode.TreeItemCollapsibleState.None);
        it.description = c.help || "";
        it.tooltip = `${c.id} (${c.category})`;
        return { item: it, run: { o: n.o, action: { label: c.id, command: c.id, category: c.category, surfaces: c.surfaces, fields: {} } } };
      });
      return [];
    },
  };
  function leaf(text, icon) { const it = new vscode.TreeItem(text); it.iconPath = new vscode.ThemeIcon(icon); return { item: it }; }
  const view = vscode.window.createTreeView("wsHost.orchestrators", { treeDataProvider: provider });
  context.subscriptions.push(view, view.onDidChangeSelection(async e => {
    const n = e.selection[0];
    if (!n || !n.run) return;
    await runAction(n.run.o, n.run.action);
  }));

  // Registered commands take no action, command line or resource (0004 FR-011): the tree runs a node on selection, and a
  // decision always goes through runAction's modal, whoever asks.
  context.subscriptions.push(
    vscode.commands.registerCommand("wsHost.refresh", () => refresh()),
    vscode.commands.registerCommand("wsHost.showSuggestions", () => showSuggestions()),
    vscode.commands.registerCommand("wsHost.ensure", async () => { const o = orchestrator(OWN); if (o) await runAction(o, { label: "Ensure everything is set up and up to date", command: "workspace ensure", category: "setup", surfaces: ["terminal", "editor"], fields: {} }); }),
    vscode.commands.registerCommand("wsHost.signIn", () => signIn()),
    vscode.commands.registerCommand("wsHost.runChecks", () => runChecks()),
    vscode.commands.registerCommand("wsHost.getHelp", () => getHelp()),
    vscode.commands.registerCommand("wsHost.learn", () => learn()),
    vscode.workspace.onDidGrantWorkspaceTrust(() => refresh()),
  );
  refresh();
}

function nonce() { let s = ""; const c = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"; for (let i = 0; i < 32; i++) s += c[Math.floor(Math.random() * c.length)]; return s; }
function escapeHtml(s) { return String(s).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch])); }
function deactivate() {}

module.exports = {
  activate, deactivate,
  _test: { parseSchema, readability, buildArgv, missingArgs, classifyAction, statusFor, suggestionsFor, parseFinding, wrapHtml, LineSplitter, helpReport,
           launcherCandidates, surfaceExposed, resourceOfPage, PageSplitter, unescapeHtml, flagName, run, runJson, runPages, discover, UPDATE_NEEDED, SUPPORTED_SCHEMA },
};
