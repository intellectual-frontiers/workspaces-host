"use strict";
// A stand-in for VS Code's API, enough to activate the extension and drive it (0004-editor-extension FR-017).
const Module = require("module");

function makeVscode(opts = {}) {
  const calls = { statusBars: [], panels: [], messages: [], warnings: [], inputs: [], clipboard: [], opened: [], commands: new Map(), diagnostics: new Map(), progress: [], treeViews: [] };
  const answers = Object.assign({ warning: undefined, quickPick: undefined, info: undefined }, opts.answers || {});
  const emitter = () => { const l = []; return { event: f => { l.push(f); return { dispose() {} }; }, fire: x => l.forEach(f => f(x)) }; };
  class TreeItem { constructor(label, state) { this.label = label; this.collapsibleState = state; } }
  class ThemeIcon { constructor(id) { this.id = id; } }
  class ThemeColor { constructor(id) { this.id = id; } }
  class Range { constructor(a, b, c, d) { this.start = { line: a, character: b }; this.end = { line: c, character: d }; } }
  class Diagnostic { constructor(range, message, severity) { Object.assign(this, { range, message, severity }); } }
  const vscode = {
    calls,
    StatusBarAlignment: { Left: 1 }, TreeItemCollapsibleState: { None: 0, Collapsed: 1, Expanded: 2 }, ProgressLocation: { Notification: 15 },
    ViewColumn: { Beside: -2 }, DiagnosticSeverity: { Error: 0, Warning: 1 },
    TreeItem, ThemeIcon, ThemeColor, Range, Diagnostic,
    EventEmitter: function () { return emitter(); },
    Uri: { file: p => ({ fsPath: p, scheme: "file" }), parse: s => ({ toString: () => s, raw: s }) },
    window: {
      createOutputChannel: () => ({ appendLine() {}, dispose() {} }),
      createStatusBarItem: () => { const s = { show() {}, dispose() {} }; calls.statusBars.push(s); return s; },
      createTreeView: (id, o) => { const v = { id, provider: o.treeDataProvider, selectionHandlers: [], onDidChangeSelection(f) { v.selectionHandlers.push(f); return { dispose() {} }; }, dispose() {} }; calls.treeViews.push(v); return v; },
      createWebviewPanel: (type, title, col, o) => {
        const p = { type, title, options: o, handlers: [], webview: { html: "", onDidReceiveMessage(f) { p.handlers.push(f); return { dispose() {} }; } }, onDidDispose() {}, dispose() {} };
        calls.panels.push(p); return p;
      },
      showWarningMessage: async (msg, o, ...btn) => { calls.warnings.push({ msg, o, btn }); return answers.warning; },
      showInformationMessage: async (msg, ...btn) => { calls.messages.push({ msg, btn }); return typeof answers.info === "function" ? answers.info(msg, btn) : answers.info; },
      showErrorMessage: async msg => { calls.messages.push({ msg, error: true }); },
      showQuickPick: async (items, o) => { calls.inputs.push({ items, o }); return typeof answers.quickPick === "function" ? answers.quickPick(items, o) : answers.quickPick; },
      showInputBox: async o => { calls.inputs.push({ input: o }); return answers.input; },
      showTextDocument: async () => {},
      withProgress: async (o, f) => { const reports = []; calls.progress.push({ o, reports }); return f({ report: r => reports.push(r) }); },
    },
    workspace: {
      isTrusted: opts.trusted !== false,
      workspaceFolders: [{ uri: { fsPath: opts.folder || "/tmp" } }],
      onDidGrantWorkspaceTrust: () => ({ dispose() {} }),
      openTextDocument: async o => ({ content: o.content }),
    },
    commands: { registerCommand: (name, f) => { calls.commands.set(name, f); return { dispose() {} }; } },
    languages: { createDiagnosticCollection: () => ({ clear() { calls.diagnostics.clear(); }, set(uri, ds) { calls.diagnostics.set(uri.fsPath, ds); }, dispose() {} }) },
    env: { clipboard: { writeText: async t => { calls.clipboard.push(t); } }, openExternal: async u => { calls.opened.push(u.raw); } },
  };
  return vscode;
}

function install(vscode) {
  const orig = Module._load;
  Module._load = function (request, ...rest) { return request === "vscode" ? vscode : orig.call(this, request, ...rest); };
  return () => { Module._load = orig; };
}

module.exports = { makeVscode, install };
