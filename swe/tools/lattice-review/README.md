# Lattice review

One local page: the Lattice dashboard with a review section inside every
task. The section shows the commits that belong to the task and opens
them in Plannotator, or file by file in VS Code. Plannotator's decision
(approved, or annotated with the review text) is recorded on the task as
a comment with role `review`, bound to the commit IDs it covered, and
each of its notes becomes a thread with replies and a resolved state. A
task with commits can be marked done, from the section or with the
dashboard's own status control, only while its latest review approves
exactly the commits it has now and every thread is resolved. Notes and
plans opened from the dashboard open in VS Code.

`lattice_review.py` runs Lattice's own dashboard handler in its process
(it re-executes itself with the Python the `lattice` command uses) and
adds the review routes on top, so there is one port and one process.
Writes made through the dashboard carry the actor given with `--actor`
instead of `dashboard:web`. The page it serves also opens the task side
panel at 60% of the window on an opaque background; drag the panel's
left edge to resize it (the width is remembered in the browser) and
double-click the edge to reset it. Each panel section is drawn as a card
one step lighter than the panel, with a quiet hue by kind, and the
dropdown menus and the review section follow the theme's color scheme.

Everything stays on the machine. The server binds to 127.0.0.1 only,
answers only requests whose Host and Origin name this machine, and
starts Plannotator with its AI and sharing features disabled and with
`--no-git-remote-check`, so a review never contacts the remote.

## How a task's work is found

1. A linked branch (`lattice branch-link <ID> <branch>`) with commits of
   its own: the diff is the merge-base with the integration branch to the
   branch tip. A linked branch with no commits of its own is no work yet,
   and the section says so.
2. Otherwise, commits whose message ends with a trailer line
   `Task: <ID>` (several IDs may be listed, comma separated). If they are
   consecutive they form one range; if not, each commit opens on its own
   and the task cannot be approved as a whole.
3. Otherwise the task has no work yet, and an empty range is refused
   before Plannotator starts.

Plannotator gets the task's range as a static patch (`git diff base
head` on stdin) of the commit IDs resolved at the moment the button is
pressed, and the recorded review names those same IDs. The per-commit
buttons do the same for one commit. Uncommitted work is reviewed where
it is: in the checkout that has the task's linked branch checked out
(the repository itself or a `git worktree`), or, for a task without a
branch, in this checkout when its commits end at HEAD or it has none.
When that checkout has uncommitted changes, a second button names it and
reviews them from the task's base; such reviews are recorded as feedback
and never complete a task. Every file of the range has `open` (the file in VS Code, when it
exists in the tree) and `diff` (VS Code's two-file diff through `code
--diff`, with the old path on the base side for renames).

Plannotator is started with `--browser none`, so it never launches a
browser of its own; the button opens the session as a new tab of the
browser the board is in, whatever machine that browser runs on. One
session per task at a time: pressing the button again returns to the
open session, and "Close session" ends an abandoned one (closing its
tab does not; the process waits for a decision until then). Sessions
end with the server.

## Review threads

Plannotator returns a review as one message: a `## <file>` heading per
file and a `### Line N (new)`, `### Lines N-M (old)` or `### File
Comment` heading per note, followed after three or more blank lines by
its instruction to the agent. When a review is recorded, each note
becomes a thread: a top-level comment by the owner's actor (Lattice
nests one level, so replies hang off top-level comments only) in this
shape:

```
Thread: README.md, line 239 (new) at 4c43cb015c54
From review ev_...
> the reviewed line, at most five lines, read from the reviewed commit
the note
```

A note whose file and quoted lines match a thread that is still open,
or whose file and place match when there is no quote, goes into that
thread as a reply starting `Follow-up from review <id>`, so one line
keeps one history even when its line number moves. An annotated review
recorded before notes were split is one thread of its own.

The section lists every thread with the quoted line and its messages in
order, a Reply box (posted as the owner's actor), Reply and resolve for
a last word that also closes the thread, and Resolve or Reopen, which
add or remove a `resolved` reaction on the thread. Only a
reaction from a `human:` actor counts. A thread waits on the agent when
the owner spoke last and waits on the owner when an agent did; an agent
reply's `Status:` line is shown next to it. A line at the top of the
section says what the owner does next, including the closing page
Plannotator shows after Send Feedback, and offers "Move to in progress"
when threads wait on the agent. Once the latest review approves the
current commits, it asks for the open threads to be resolved instead. Agents reply with `lattice comment <ID>
--reply-to <thread id>` in the shape given in the board's `context.md`.

To keep Plannotator's own instruction out of the agent's way, set
`prompts.review.denied` in `~/.plannotator/config.json` (see
`LATTICE_ONBOARDING.md`). The split does not depend on it.

## Plan review

The section has two blocks: Plan, then Code review. The Plan block shows
the state of the task's plan file (`.lattice/plans/<task id>.md`, the
one `lattice plan <ID>` names) with "Plannotator: review the plan" and
"Open the plan in VS Code", which scaffolds a plan the way the
dashboard's own button does when there is none. While the section is on
the page the dashboard's own Show Plan button is hidden, so the plan has
one place. "Plannotator: review the plan" opens the plan in Plannotator's
annotate mode (`plannotator annotate <plan> --gate --json`), where the
owner comments on selected text or on the whole plan, marks text for
removal, or edits the plan in place (saved edits are written to the
file). Send Feedback or Approve is recorded on the task as a comment with
role `plan-review` and a `Plan: <sha256>` line for the plan as it stood
when the session ended. Each note becomes a thread, anchored
`plan, line N` with the selected text quoted, is listed in the Plan
block, and follows the thread rules above. An approval also clears a `needs_human` flag whose reason
asks for the plan's approval, so the agent never has to clear it. The
state reads not reviewed yet, changes requested, approved, or changed
since it was approved. Plan reviews never complete a task.

## History

Below Plan and Code review, a History block replaces the dashboard's
own (which is hidden while the section is on the page). It reads the
task's event log and its commits and says, newest first and grouped by
day in local time, what changed: status from and to, the question asked
or the note that cleared it, criteria text, description edits (expand
"What changed"), links to related tasks, reviews and plan reviews,
threads opened and resolved, and commits. Each entry shows the reason
given, and an agent acting "on behalf of" a person is highlighted.
Related tasks open in the dashboard; reviews, threads and commits jump to
their place in the section. Plain comments stay in Comments, and
bookkeeping events (short IDs, comment edits) are left out.

## What completes a task

The latest comment with role `review` that carries a `Reviewed:` line
decides. "Mark done" appears only when that review is an approval, its
commit IDs are the task's current work and every review thread is
resolved; a later annotated review, a moved branch, a new trailer
commit, a live-tree review or an open thread all withdraw it, and the
section says why. The dashboard's status control is held to the
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
nest and deleted or edited ones show as such, URL artifacts rendered as
links, and a background refresh that keeps the task panel open, redraws
it only when its own task changed and nothing in it has focus, and keeps
its scroll position):

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
| `POST /review/t/<ID>/plannotator` | `plannotator review --patch-file -` with the range, or `--git --base` in the checkout that holds the task's uncommitted work; redirects to the session; the JSON decision becomes a review comment |
| `POST /review/t/<ID>/close` | ends the task's open session, recording nothing |
| `POST /review/t/<ID>/open`, `/filediff` | `code` on one file of the range, or `code --diff` |
| `POST /review/t/<ID>/openplan` | the plan in VS Code, scaffolded when missing |
| `POST /review/t/<ID>/plan` | `plannotator annotate <plan file> --gate --json`; redirects to the session; the decision becomes a `plan-review` comment and threads |
| `POST /review/t/<ID>/complete` | `lattice status <ID> done` when the latest review approves the current work and no thread is open |
| `POST /review/t/<ID>/reply` | `lattice comment <ID> --reply-to <thread> --file` with the owner's reply; with `resolve=1` also the `resolved` reaction |
| `POST /review/t/<ID>/resolve`, `/reopen` | `lattice react` or `unreact` with `resolved` on a thread |
| `POST /review/t/<ID>/rework` | `lattice status <ID> in_progress --no-auto-review` |
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
