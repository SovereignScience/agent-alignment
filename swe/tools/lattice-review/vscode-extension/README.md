# Lattice review links

A VS Code extension with one job: turn a link of the form

```
vscode://agent-alignment.lattice-review-links/diff?repo=<path>&base=<ref>&head=<ref>&title=<text>
```

into the multi-diff editor showing every file changed between `base`
and `head` in the repository at `repo`. `head=WORKTREE` compares `base`
with the working tree. The Lattice review launcher generates these
links; nothing else is needed.

It runs in the workspace extension host (so inside a WSL or SSH remote
when that is where the repository lives) and uses the built-in Git
extension to read the diffs.

Install the packaged file from a terminal that can reach the editor:

```
code --install-extension lattice-review-links-0.1.0.vsix
```

Build the package again after a change:

```
python3 ../build_vsix.py
```
