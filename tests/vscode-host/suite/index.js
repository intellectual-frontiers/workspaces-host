"use strict";
// Runs inside VS Code: the extension activates, registers its commands, shows its status and answers Get help.
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vscode = require("vscode");

exports.run = async function () {
  const ext = vscode.extensions.getExtension("intellectual-frontiers.workspaces-host");
  assert.ok(ext, "the extension is not loaded");
  await ext.activate();
  assert.strictEqual(ext.isActive, true);
  const cmds = await vscode.commands.getCommands(true);
  for (const c of ["wsHost.refresh", "wsHost.advance", "wsHost.signIn", "wsHost.runChecks", "wsHost.getHelp"]) assert.ok(cmds.includes(c), c + " is not registered");
  assert.ok(!cmds.includes("wsHost.openNode"));
  await vscode.commands.executeCommand("wsHost.refresh");
  await new Promise(r => setTimeout(r, 3000));
  const log = fs.readFileSync(path.join(process.env.WS_TEST_DIR, "calls.log"), "utf8");
  assert.match(log, /command list --json/);
  assert.match(log, /doctor --json/);
  await vscode.commands.executeCommand("wsHost.getHelp");
  const clip = await vscode.env.clipboard.readText();
  assert.match(clip, /Workspace help report/);
  assert.match(clip, /"resource": "machine"/);
  console.log("WS_VSCODE_SUITE_PASSED");
};
