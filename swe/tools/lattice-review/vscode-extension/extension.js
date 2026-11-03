const vscode = require('vscode');

// Handles vscode://agent-alignment.lattice-review-links/diff?repo=<path>&base=<ref>&head=<ref|WORKTREE>&title=<text>
// and opens every file changed between base and head in one multi-diff editor.
async function openDiff(query) {
  const repoPath = query.get('repo');
  const base = query.get('base');
  const head = query.get('head') || 'WORKTREE';
  const title = query.get('title') || base + '..' + head;
  if (!repoPath || !base) {
    throw new Error('expected /diff?repo=<path>&base=<ref>&head=<ref>');
  }
  const gitExtension = vscode.extensions.getExtension('vscode.git');
  if (!gitExtension) {
    throw new Error('the built-in Git extension is not available');
  }
  const exports = gitExtension.isActive ? gitExtension.exports : await gitExtension.activate();
  const git = exports.getAPI(1);
  const root = vscode.Uri.file(repoPath);
  const repo = git.getRepository(root) || (await git.openRepository(root));
  if (!repo) {
    throw new Error('no git repository at ' + repoPath + ' (open its folder in this window first)');
  }
  const changes = head === 'WORKTREE' ? await repo.diffWith(base) : await repo.diffBetween(base, head);
  if (!changes.length) {
    vscode.window.showInformationMessage('No changes between ' + base + ' and ' + head);
    return;
  }
  const resources = changes.map((change) => {
    const file = change.renameUri || change.uri;
    const left = git.toGitUri(change.originalUri || change.uri, base);
    const right = head === 'WORKTREE' ? file : git.toGitUri(file, head);
    return [file, left, right];
  });
  await vscode.commands.executeCommand('vscode.changes', title, resources);
}

function activate(context) {
  context.subscriptions.push(vscode.window.registerUriHandler({
    async handleUri(uri) {
      try {
        if (uri.path !== '/diff') {
          throw new Error('unknown path ' + uri.path);
        }
        await openDiff(new URLSearchParams(uri.query));
      } catch (err) {
        vscode.window.showErrorMessage('Lattice review links: ' + (err && err.message ? err.message : String(err)));
      }
    },
  }));
}

function deactivate() {}

module.exports = { activate, deactivate };
