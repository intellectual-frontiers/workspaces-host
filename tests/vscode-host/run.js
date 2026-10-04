"use strict";
// Starts a real VS Code (Electron) with the extension loaded and runs suite/index.js inside it (0004-editor-extension FR-017).
// Needs `@vscode/test-electron` (install it outside the repository, for example `npm i --prefix /tmp/vt @vscode/test-electron`,
// and point NODE_PATH at its node_modules) and a display (xvfb-run). Not part of `ws-host test`: it downloads VS Code.
const path = require("path");
const fs = require("fs");
const os = require("os");
const { runTests } = require("@vscode/test-electron");

(async () => {
  const root = path.resolve(__dirname, "../..");
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "wsvscode-"));
  const bin = path.join(dir, "bin"); fs.mkdirSync(bin);
  // a stand-in ws-host that answers the few commands the extension asks for
  fs.writeFileSync(path.join(bin, "ws-host"), `#!/bin/sh
printf '%s\\n' "$*" >> "${dir}/calls.log"
case "$*" in
 "command list --json") echo '{"schema":"ws-host/command-list@1","audience":"private","kind":"command-list","id":"c","data":{"count":1,"commands":[{"id":"doctor","category":"check","group":null,"surfaces":["terminal","editor"],"help":"Check"}]},"links":[],"actions":[]}';;
 "repo list --json") echo '{"schema":"ws-host/repo-list@1","audience":"private","kind":"repo-list","id":"r","data":{"plain":"x","repositories":[]},"links":[],"actions":[]}';;
 "doctor --json") echo '{"schema":"ws-host/doctor@1","audience":"private","kind":"doctor","id":"m","data":{"plain":"Your machine is ready.","checks":[]},"links":[],"actions":[]}';;
 "auth status --json") echo '{"schema":"ws-host/auth-status@1","audience":"private","kind":"auth-status","id":"a","data":{"plain":"x","forges":[{"name":"github.com","signed_in":true}]},"links":[],"actions":[]}';;
 "context --json") echo '{"schema":"ws-host/context@1","audience":"private","kind":"context","id":"c","data":{"plain":"report","resource":"machine"},"links":[],"actions":[]}';;
 *) exit 2;;
esac
`, { mode: 0o755 });
  process.env.PATH = bin + path.delimiter + process.env.PATH;
  const work = path.join(dir, "work"); fs.mkdirSync(work);
  try {
    await runTests({
      extensionDevelopmentPath: path.join(root, "vscode"),
      extensionTestsPath: path.join(__dirname, "suite", "index.js"),
      launchArgs: [work, "--no-sandbox", "--disable-gpu", "--disable-workspace-trust", "--user-data-dir", path.join(dir, "ud"), "--extensions-dir", path.join(dir, "ext")],
      extensionTestsEnv: { WS_TEST_DIR: dir },
    });
  } catch (e) { console.error("VS Code test run failed:", e && e.message); process.exit(1); }
})();
