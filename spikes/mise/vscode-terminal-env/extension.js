const vscode = require('vscode'); const cp = require('child_process'); const fs = require('fs');
exports.activate = async (ctx) => {
  const out = process.env.SPIKE_OUT; const mise = process.env.SPIKE_MISE;
  // What the Console would do: ask the provider's environment from mise (data only, safe mode) and scope it to that folder.
  for (const f of vscode.workspace.workspaceFolders || []) {
    const env = JSON.parse(cp.execFileSync(mise, ['-C', f.uri.fsPath, 'env', '--json'], { env: { ...process.env, MISE_SAFE: '1' }, encoding: 'utf8' }));
    const sc = ctx.environmentVariableCollection.getScoped({ workspaceFolder: f });
    const provider = env.PATH.split(':').filter((p) => p.includes('/installs/'));
    if (provider.length) sc.prepend('PATH', provider.join(':') + ':');
    fs.appendFileSync(out + '.log', `folder ${f.name}: provider dirs ${provider.length}\n`);
  }
  await new Promise((r) => setTimeout(r, 1500));
  for (const f of vscode.workspace.workspaceFolders || []) {
    const t = vscode.window.createTerminal({ name: f.name, cwd: f.uri.fsPath, shellPath: '/bin/bash', shellArgs: ['--norc','--noprofile','-c', `echo "${f.name}: java=$(command -v java || echo none)" >> ${out}; sleep 3`] });
    t.show(); fs.appendFileSync(out + '.log', `terminal ${f.name} pid ${await Promise.race([t.processId, new Promise(r=>setTimeout(()=>r('timeout'),20000))])}\n`);
  }
  setTimeout(() => vscode.commands.executeCommand('workbench.action.quit'), 30000);
};
