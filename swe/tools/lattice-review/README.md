# Lattice review

One local page: the Lattice dashboard with a review section inside every
task. The section shows the commits that belong to the task and opens
them in Plannotator, or file by file in VS Code. Plannotator's decision
(approved, or annotated with the review text) is recorded on the task as
a comment with role `review`, bound to the commit IDs it covered. A task
with commits can be marked done, from the section or with the
dashboard's own status control, only while its latest review approves
exactly the commits it has now. Notes and plans opened from the
dashboard open in VS Code.

`lattice_review.py` runs Lattice's own dashboard handler in its process
(it re-executes itself with the Python the `lattice` command uses) and
adds the review routes on top, so there is one port and one process.
Writes made through the dashboard carry the actor given with `--actor`
instead of `dashboard:web`.

Everything stays on the machine. The server binds to 127.0.0.1 only,
answers only requests whose Host and Origin name this machine, and
starts Plannotator with its AI and sharing features disabled and with
`--no-git-remote-check`, so a review never contacts the remote.

## How a task's work is found

1. A linked branch (`lattice branch-link <ID> <branch>`): the diff is the
   merge-base with the integration branch to the branch tip.
2. Otherwise, commits whose message ends with a trailer line
   `Task: <ID>` (several IDs may be listed, comma separated). If they are
   consecutive they form one range; if not, each commit opens on its own
   and the task cannot be approved as a whole.
3. Otherwise the task has no work yet. With uncommitted changes in the
   tree, the section still offers a Plannotator review of them, for
   feedback only.

Plannotator gets the task's range as a static patch (`git diff base
head` on stdin) of the commit IDs resolved at the moment the button is
pressed, and the recorded review names those same IDs. The per-commit
buttons do the same for one commit. When the range ends at the
checked-out HEAD and the tree has uncommitted changes, a second button
reviews the live tree from the task's base, which allows staging from
the review; live reviews are recorded as feedback and never complete a
task. Every file of the range has `open` (the file in VS Code, when it
exists in the tree) and `diff` (VS Code's two-file diff through `code
--diff`, with the old path on the base side for renames).

Plannotator is started with `--browser none`, so it never launches a
browser of its own; the button opens the session as a new tab of the
browser the board is in, whatever machine that browser runs on. One
session per task at a time: pressing the button again returns to the
open session, and "Close session" ends an abandoned one (closing its
tab does not; the process waits for a decision until then). Sessions
end with the server.

## What completes a task

The latest comment with role `review` that carries a `Reviewed:` line
decides. "Mark done" appears only when that review is an approval and
its commit IDs are the task's current work; a later annotated review, a
moved branch, a new trailer commit or a live-tree review all withdraw it,
and the section says why. The dashboard's status control is held to the
same rule for tasks that have work; tasks without commits (decisions,
spikes) are not gated. Completion is `lattice status <ID> done` with the
review already on the task (`lattice complete` only works with a status
literally named `review`). A Plannotator run that exits with an error or
without a decision is shown as an error and records nothing. Board
writes that fail are shown in the section, never reported as done.

Annotations typed in Plannotator stay in that session until Send
Feedback or Approve; only then do they land on the task, where every
browser and every agent sees them.

## Run

From a VS Code integrated terminal (so `code` reaches that window),
inside the board directory:

```
python3 <agent-alignment>/swe/tools/lattice-review/lattice_review.py --actor human:<name>
```

Then open http://127.0.0.1:<dashboard_port> and click a task. Options:
`--board DIR`, `--repo DIR` when the git repository is not the board
directory, `--port` (default: the board's `dashboard_port`), `--main`
(integration branch, default `main`), `--remote`, `--state` (review
output, Plannotator logs and temp files for diffs, default
`~/.local/state/lattice-review/<project code>/`).

## The dashboard patch

The review section is rendered by the Lattice dashboard page itself
when the page is served by this server. That needs
`lattice-dashboard-review.patch` applied once to the Lattice checkout
the `lattice` command runs from (two files: an iframe section in the
task views, comments rendered from the materialized thread so replies
nest and deleted or edited ones show as such, and URL artifacts rendered
as links):

```
cd <lattice checkout>
git apply <agent-alignment>/swe/tools/lattice-review/lattice-dashboard-review.patch
```

The patch is inert when the dashboard runs on its own. Re-apply it
after updating Lattice; if it no longer applies, the two insertion
points are `renderDetail` and `_renderPanelContent` in
`src/lattice/dashboard/static/index.html`. The server also builds on
Lattice's handler class (`_make_handler_class`, `_serve_static`, the
notes and plans handlers), written against Lattice 0.2.

## Requirements

- `lattice` and `git` on PATH, python3 (standard library only).
- `plannotator` on PATH for the Plannotator buttons (download, read and
  run its installer with `--minimal`; see `LATTICE_ONBOARDING.md`).
- The `code` command for `open`, `diff`, notes and plans; a VS Code
  integrated terminal provides it.

## Routes

| Route | What it does |
|---|---|
| `/`, `/api/...`, `/static/...` | the Lattice dashboard; `/` carries the hook that renders the review section |
| `/review/t/<ID>` | the review section for one task (what the iframe shows) |
| `POST /review/t/<ID>/plannotator` | `plannotator review --patch-file -` with the range, or `--git --base` for the live tree; redirects to the session; the JSON decision becomes a review comment |
| `POST /review/t/<ID>/close` | ends the task's open session, recording nothing |
| `POST /review/t/<ID>/open`, `/filediff` | `code` on one file of the range, or `code --diff` |
| `POST /review/t/<ID>/complete` | `lattice status <ID> done` when the latest review approves the current work |
| `POST /api/tasks/<id>/status` | the dashboard's status change; `done` is refused with `REVIEW_REQUIRED` under the same rule |
| `POST /api/tasks/<id>/open-notes`, `/open-plans` | Lattice's notes and plans, opened with `code` instead of xdg-open |
| `/t/<ID>` | redirects to the task in the dashboard (older links) |

Review POSTs carry a per-run token; dashboard POSTs must carry an Origin
equal to the address the page was served from, a JSON object body, and
at most 1 MiB. Neither is a boundary against an agent that can already
edit the files and the board.

## Tests

```
python3 -m unittest test_lattice_review
<python with lattice installed> -m unittest test_lattice_review
```

The first run covers the review logic against a stand-in dashboard; the
second, with the interpreter the `lattice` command uses (its shebang
names it), also runs Lattice's real dashboard handler in process. The
tests build a temporary git repository and board, a stand-in
`plannotator` that answers with a fixed decision, and a stand-in `code`
that logs what it was asked to open; they do not need the real
Plannotator or VS Code. Tests that record on a board run only when
`lattice` is on PATH.
