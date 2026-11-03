# Lattice review launcher

A local web page that turns a Lattice board into a review queue. Each
task shows the commits that belong to it and two buttons: open them in
Plannotator, or open them in the VS Code multi-diff editor. Plannotator's
decision (approved or annotated, with the review text) is recorded on the
task as a comment with role `review`, and the page can move the task
through its statuses or complete it with that review.

Everything stays on the machine. The launcher binds to 127.0.0.1 only and
starts Plannotator with its AI and sharing features disabled.

## How a task's work is found

1. A linked branch (`lattice branch-link <ID> <branch>`): the diff is the
   merge-base with the integration branch to the branch tip.
2. Otherwise, commits whose message ends with a trailer line
   `Task: <ID>` (several IDs may be listed, comma separated). If they are
   consecutive they form one range; if not, each commit opens on its own.
3. Otherwise the task has no work yet and nothing can be reviewed as that
   task. The index still offers an unrecorded review of the working tree.

Plannotator gets the task's exact range as a static patch (`git diff
base head` on stdin), so it works for any task regardless of the current
branch; the per-commit buttons do the same for one commit. When the
task's range ends at the checked-out HEAD, a second button opens the
live tree from the task's base instead, which allows staging from the
review. The VS Code links carry the exact refs. Plannotator runs with
`--no-git-remote-check`, so it never contacts the remote.

Every recorded review names the commit IDs it covered (a `Reviewed:`
line in the comment). "Mark done with this review" is offered only while
the task's work still resolves to those IDs; a review of a dirty working
tree never completes a task. Board writes that fail (comment, status,
complete) are shown on the page, never reported as done.

## Run

From a VS Code integrated terminal (so `code` and the browser opener are
on PATH), inside the board directory:

```
python3 <agent-alignment>/swe/tools/lattice-review/lattice_review.py --with-dashboard --actor human:<name>
```

Then open http://127.0.0.1:8798. The Lattice dashboard runs on the board's
`dashboard_port`. Options: `--board DIR`, `--repo DIR` when the git
repository is not the board directory, `--port`, `--main` (integration
branch, default `main`), `--remote`, `--dashboard-url`, `--state` (where
review output and logs are kept, default
`~/.local/state/lattice-review/<project code>/`).

## Requirements

- `lattice` and `git` on PATH, python3 (standard library only).
- `plannotator` on PATH for the Plannotator buttons (download, read and
  run its installer with `--minimal`; see `LATTICE_ONBOARDING.md`).
- The `lattice-review-links` VS Code extension from `vscode-extension/`
  for the multi-diff links. Without it, the per-file "diff in VS Code"
  buttons still work through `code --diff`.

## Routes

| Route | What it does |
|---|---|
| `/` | all tasks, status order, with buttons; unpushed commits past `<remote>/<main>` |
| `/t/<ID>` | one task: description, criteria, commits, files, Plannotator result, comments, status buttons |
| `POST /t/<ID>/plannotator` | `plannotator review --patch-file -` with the range, or `--git --base` for the live tree; the JSON decision becomes a review comment |
| `POST /t/<ID>/filediff` | `code --diff` for one file of the range |
| `POST /t/<ID>/comment`, `/status`, `/complete` | `lattice comment`, `lattice status --no-auto-review`, `lattice complete --review-file` as the launcher's actor |
| `POST /unpushed/plannotator` | review the working tree without a task |

Requests require the loopback Host, and browser requests with an Origin
must match it. Every POST also carries a per-run token. These checks reject
cross-site browser requests and unexpected hostnames. Plannotator failures
are not recorded as successful reviews. Real editor and Plannotator
integration still require an owner-run acceptance check.

## Tests

```
python3 -m unittest test_lattice_review
```

The tests build a temporary git repository and board and use a stand-in
`plannotator` that answers with a fixed decision; they do not need the
real Plannotator or VS Code.
