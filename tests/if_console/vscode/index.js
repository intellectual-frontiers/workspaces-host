'use strict';
// The entry VS Code calls inside the extension host when the public root's `agora extension test --suite` runs this directory
// (0043-if-console FR-034): it loads the Workspaces Console's own test runner and runs this suite once.
const path = require('path');

async function run() {
  const { runAll } = require(path.join(process.env.IF_CONSOLE_EXTENSION_DIR, 'test', 'vscode', 'suite', 'harness'));
  require('./suite');
  await runAll('ws-host', process.env.IF_CONSOLE_VSCODE_REPORT_DIR);
}

module.exports = { run };
