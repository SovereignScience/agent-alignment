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
Writes made through the dashboard carry the actor given with `--actor`,
whether the page sends `dashboard:web` or no actor at all. Only a review
recorded for a `human:` actor counts, for code as for plans. Actor labels
and the board files are workflow records: anyone who can write the
repository's files can write them, so they are not authentication. The page it serves also opens the task side
panel at 60% of the window on an opaque background; drag the panel's
left edge to resize it (the width is remembered in the browser) and
double-click the edge to reset it. Each panel section is drawn as a card
one step lighter than the panel, with a quiet hue by kind, and the
dropdown menus and the review section follow the theme's color scheme.
Comments show the newest three, with one line above them that shows or
hides the earlier ones, and a comment longer than six lines shows
"More". Replies stay with their comment.

The owner needs to inspect a committed change and return feedback without
starting a program selected by the repository's contents or Git config.
The listener binds to 127.0.0.1, checks Host and Origin, and starts
Plannotator with AI and sharing disabled. Those request checks do not
constrain a Git subprocess, so every custom and inherited dashboard Git
read uses the same controlled runner. It disables fsmonitor, hooks,
external diff, diff drivers, text converters and signature display.
All Git transports are refused, including lazy fetch of missing objects;
missing objects produce an error instead of an incomplete review. Native
Git endpoint failures return JSON with GIT_READ_ERROR and HTTP 409. This
also works with Git versions that do not implement GIT_NO_LAZY_FETCH.
Repositories naming a diff or filter program are refused before each read.

Code review exports a static patch between resolved commit IDs to
Plannotator. It never asks Git to compare the working copy, where clean
filters could run, and Plannotator performs no Git reads of its own.
Only committed changes can be reviewed. Actor labels remain workflow
records, not authentication; they do not protect the board from an agent
that can edit its files.

The inherited Git endpoints use Lattice's installed git_reader module,
with its subprocess runner replaced in this server process. Startup
checks the source fingerprints of both the dashboard server and Git
reader against the inspected Lattice 0.2.1 files, with and without this
repository's dashboard patch. A different version is refused until its
Git call paths are reviewed and the fingerprints updated. No installed
package file is changed. This compatibility check covers the inspected
Git read paths; it is not containment of the owner's account.

## Review flow

The task states the need, harm, scope and acceptance before the plan is
reviewed. The shared plan shape is in
[the onboarding guide](../../LATTICE_ONBOARDING.md#3-context).

```text
Task: need, harm, expected result and acceptance
Plan: [Plannotator: review the plan] [Open the plan in VS Code]
Code: Base <commit>  Head <commit>
      [Plannotator: the whole range] [diff] [open]
Threads: file and line | owner note | agent reply | [Reply] [Resolve]
```

The owner sends plan feedback, the agent answers and revises, and the
owner approves the revised plan. After implementation, the owner reviews
the committed patch. Feedback returns to task threads automatically.
Changed commits require another approval; only the owner resolves threads
and completes the task. Merging and publishing remain owner actions.

The section opens with the agent's open `Need:` request, when the task
has one, and then one line that says what you do next. Mark done asks
first and repeats an open request, because done is final. The result of
a reply, Resolve or Reopen shows inside its thread. While a Plannotator
session runs the section reloads every five seconds, except while a
reply box holds text. Branches of the task that are not read are named:
unlinked `feature/<ID>-*` branches, a linked branch that is missing, and
any linked branch after the first one with commits.

## How a task's work is found

1. A linked branch (`lattice branch-link <ID> <branch>`) with commits of
   its own: the diff is the merge-base with the integration branch to the
   branch tip. A linked branch with no commits of its own is no work yet,
   and the section says so.
2. Otherwise, commits on this checkout's HEAD, the integration branch
   or a linked branch whose message has a line `Task: <ID>` (several
   IDs separated by `, `). If they are consecutive they form one range;
   if not, each commit opens on its own and the task cannot be approved
   or marked done until its commits form one range.
3. Otherwise the task has no work yet, and an empty range is refused
   before Plannotator starts.

Candidate branches for competing versions of one task stay unlinked
until the owner picks one. Only the first linked branch with commits is
read, and trailer commits on an unlinked branch are not found while the
checkout is on the integration branch, so the candidates that were not
picked never count as the task's work.

Plannotator gets the task's range as a static patch (`git diff base
head` on stdin) of the commit IDs resolved at the moment the button is
pressed, and the recorded review names those same IDs. The per-commit
buttons do the same for one commit. Uncommitted work is not reviewed
here: the agent commits it first. Every file of the range has `diff` (VS
Code's two-file diff through `code --diff`, with the old path on the
base side for renames), and `open` (the file in VS Code) when the range
ends at this checkout's HEAD and the file exists there.

Plannotator is started with `--browser none`, so it never launches a
browser of its own; the button opens the session as a new tab of the
browser the board is in, whatever machine that browser runs on. One
Plannotator session per task, plan and code together: any of its
Plannotator buttons returns to the open session, and "Close session"
ends an abandoned one (closing its
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
Thread: <file>, line <N> (new) at <commit>
From review ev_...
> the reviewed line, at most five lines, read from the reviewed commit
the note
```

A note whose file and quoted lines match a thread that is still open,
or whose file and place match when there is no quote, goes into that
thread as a reply starting `Follow-up from review <id>`, so one line
keeps one history even when its line number moves. When more than one
open thread could take the note (the same text on two lines, say), it
starts a thread of its own. An annotated review with no `Thread:`
comments of its own (no file notes, or the split failed) is one thread
of its own and must be resolved like any other.

The section lists every thread with the quoted line and its messages in
order, a Reply box (posted as the owner's actor), Reply and resolve for
a last word that also closes the thread, and Resolve or Reopen, which
add or remove a `resolved` reaction on the thread. Only a
reaction from a `human:` actor counts. A thread waits on the agent when
the owner spoke last and waits on the owner when an agent did; an agent
reply's `Status:` line is shown next to it. A line at the top of the
section says what the owner does next, including the closing page
Plannotator shows after Send Feedback, and offers "Move to in progress"
when threads wait on the agent and the workflow allows the move;
otherwise the dashboard's status control does it. Once the latest
review approves the current commits, it asks for the open threads to be
resolved instead. Agents reply with `lattice comment <ID> --reply-to
<thread id>` in the shape given in the board's `context.md`.

To keep Plannotator's own instruction out of the agent's way, set
`prompts.review.denied` in `~/.plannotator/config.json` (see
`LATTICE_ONBOARDING.md`). The split does not depend on it.

## Plan review

The section has two blocks, Plan then Code review, after a Dependencies
block when the task has links. The Plan block shows the state of the
task's plan file (`.lattice/plans/<task id>.md`, whose path `lattice
plan <ID> --json` gives) with "Plannotator: review the plan" and "Open the plan in
VS Code"; with no plan file its one button is "Write the plan in VS
Code", which scaffolds it the way the dashboard's own button does. While
the section is on
the page the dashboard's own Show Plan button is hidden, so the plan has
one place. "Plannotator: review the plan" opens the plan in Plannotator's
annotate mode (`plannotator annotate <plan> --gate --json`), where the
owner comments on selected text or on the whole plan, marks text for
removal, or edits the plan in place (saved edits are written to the
file). Send Feedback or Approve is recorded on the task as a comment with
role `plan-review` and a `Plan: <sha256>` line for the plan as it was
opened. If the file is different when the session ends, edits saved
from Plannotator included, the approval still names the opened version,
the plan reads as changed since it was approved and the flag stays set:
review it once more. Each note becomes a thread, anchored
`plan, line N` with the selected text quoted, is listed in the Plan
block, and follows the thread rules above. An approval also clears the
`needs_human` flag that asked for the plan's approval when the session
started, if that same flag is still set, so the agent never has to clear
it. The state reads none yet, not reviewed yet, changes requested,
approved, changed since it was approved, or the latest plan review was
deleted. Plan reviews never complete a task, but an open plan thread
blocks done like a code thread.

## Dependencies and the branch check

When the task has links, a Dependencies block opens the section: what
it waits on (depends_on or blocked_by from this task, blocks pointing at
it), what it holds up, its parent, its subtasks and related tasks, each
with its status and a link that opens it. Links are read from both ends,
since Lattice stores each one on the task that made it. A task in
progress, in review or done that still waits on unfinished tasks gets a
warning, and so does one in progress or in review with no branch of its
own, because its work is then outside a task worktree. The DAG tab in
the dashboard draws the whole graph.

## History

At the bottom of the task, below Comments, the dashboard's own History
section shows this server's history instead, in its own frame
(`/review/t/<ID>/history`), which stops growing at 60% of the window and
scrolls inside. It shows:

- The task's log, newest first, grouped by day, with the
  time and, on hover, how long ago: what the task was created as, status
  from and to, the question asked or the note that cleared it, criteria
  text, description edits (expand "What changed"), links, reviews, plan
  reviews, threads, comments and deleted comments. Each shows the reason given, and an
  agent acting "on behalf of" a person is highlighted.
- Cross-references: links other tasks made to this one (Lattice keeps a
  link only on the task that made it) and their comments that mention its
  ID, plus commits on any branch whose message mentions it. The task's
  own commits appear as commits.
- Bursts: three or more bookkeeping edits by one actor, minutes apart
  (criteria, fields, links, branches, attachments, assignment), fold into
  one expandable line. Status changes, questions, reviews, comments,
  commits and anything done on someone's behalf stay on their own lines.
- Filters: All, Changes, Comments.
- Links: related tasks open in the dashboard; "show" scrolls the panel to
  the review, thread, commit, comment or criterion and flashes it.

Bookkeeping events (short IDs, comment edits, other reactions) are left out.

## What completes a task

The latest comment with role `review` that carries a `Reviewed:` line
decides. "Mark done" appears only when that review is an approval, its
commit IDs are the task's current work, every one of its notes was
recorded as a thread and every review thread is resolved. Once work is
merged, its commits need not be one range: each must lie in a range a
person approved since the last deleted review, or be a merge with
nothing of its own: Git's automatic merge of its two parents, or one
whose combined diff is empty. A later
annotated review, a deleted review, a moved branch, a new trailer
commit, a review of uncommitted changes from an older version, a note whose recording failed or an open
code or plan thread all withdraw it, and the section says why. It also
waits until the approved commits are merged into main and pushed to its
upstream, and every open acceptance criterion has evidence. Write an
install or deploy as a criterion; its evidence is what lets the task
close. The dashboard's status control is held to the
same rule for tasks that have work; tasks without commits (decisions,
spikes) need only evidence on every open criterion. A criterion whose
newest linked note opens with "Not met" counts as open. Completion is `lattice status <ID> done
--no-auto-review` with the review already on the task; the command
itself is not gated, so agents never run it (`lattice complete` only
works with a status literally named `review`). A Plannotator run that exits with an error or
without a decision is shown as an error and records nothing. Board
writes that fail are shown in the section, never reported as done.

Above Mark done, a short summary gives the plan and code review rounds,
the threads resolved, where the commits landed, and the first sentence
of the newest agent note,
where agents record installs and deploys.

Annotations typed in Plannotator stay in that session until Send
Feedback or Approve; only then do they land on the task, where every
browser and every agent sees them.

## Merging approved work

The owner merges from the main checkout, with the board in `LATTICE_ROOT`
or the current folder:

```
python3 <kit>/swe/tools/lattice-review/merge_approved.py --check '<command>' AA-7 [AA-8 ...]
```

Each task's linked branch is merged in the order given, with a merge
commit, only while the review rule above holds for the commits about to
land. Every `--check` command must then pass on the merged files, and
only then is main pushed. A stop undoes nothing: it says where things
stand and prints the command that takes it back. A rerun continues, and
accepts a merge already on local main only when it has the same two
parents and the same files as the one it would make. `--no-push` stops
after the checks, and `--skip-unapproved` leaves out a task whose review
does not cover its commits, together with every task whose branch
contains that task's branch or a commit carrying its trailer.

`owner_review.py` takes the same decisions in the terminal. `approve`
shows a task's head commit and a one-line summary, lets you resolve an
open thread, and records a yes as a review bound to those commits. The
record starts "Owner approved (terminal", so it says no diff was opened
in Plannotator. `close` marks done what Mark done would allow, and asks
before clearing a flag that still asks you something.
`swe/scripts/finish_batch.sh` runs a batch of this kit's tasks through
both in named phases: push, review, merge and test, publish, install,
boards, acceptance. A stop exits nonzero and undoes nothing, and a rerun
goes on from there.

## Run

The short way is `board`, a bash function in [board.bash](board.bash).
In any folder of a repository with a board, including a linked worktree,
it prints the URL when the board's port already answers, and otherwise
starts the server in the foreground (Ctrl-C stops it). It fails when the
repository has no board. Install or update it from the main checkout,
then open a new terminal:

```
(
set -euo pipefail
kit=$(git rev-parse --show-toplevel)
f="$kit/swe/tools/lattice-review/board.bash"
start=$(head -n 1 "$f"); end=$(tail -n 1 "$f")
touch ~/.bashrc
awk -v s="$start" -v e="$end" '$0 == s {skip = 1} !skip {print} $0 == e {skip = 0}' ~/.bashrc > ~/.bashrc.board.new
sed "s|@KIT@|$kit|" "$f" >> ~/.bashrc.board.new
cat ~/.bashrc.board.new > ~/.bashrc
rm ~/.bashrc.board.new
)
```

This copies the function into `~/.bashrc` in place of any earlier copy,
with the path of the checkout it was installed from, so a later change in
the checkout runs only after you install it again. It starts the server
as the board's `default_actor`, else `human:$USER`.
The base branch is the repository's `lattice-review.base`, else `main`.
Set it once where reviews run against another branch:

```
git -C ~/SOFTWARE/lilly-backend-and-frontend config lattice-review.base develop
```

The long way, from a VS Code integrated terminal (so `code` reaches that
window), inside the board directory:

```
python3 <agent-alignment>/swe/tools/lattice-review/lattice_review.py --actor human:<name>
```

Then open http://127.0.0.1:<dashboard_port> and click a task. Options:
`--board DIR`, `--repo DIR` when the git repository is not the board
directory, `--port` (default: the board's `dashboard_port`, else
8799), `--main` (integration branch, default `main`), `--actor` (default
`human:$USER`; it must be a `human:` actor, since only those resolve
threads and approve plans), `--state` (review output, Plannotator logs
and temp files for diffs, default
`~/.local/state/lattice-review/<project code>/`).
The server reads and writes only the board it serves, even when
`LATTICE_ROOT` names another.

## The dashboard patch

The review section is rendered by the Lattice dashboard page itself
when the page is served by this server. That needs
`lattice-dashboard-review.patch` applied once to the Lattice checkout
the `lattice` command runs from (two files: an iframe section in the
task views, comments rendered from the materialized thread so replies
nest and deleted or edited ones show as such, URL artifacts rendered as
links, and a background refresh that keeps the task panel open, redraws
it only when its own task changed, waits while an input in the view or
the panel has focus and catches up once focus leaves, drops a panel
response that arrives after the panel moved to another task, and keeps
the scroll position):

```
cd <lattice checkout>
git apply <agent-alignment>/swe/tools/lattice-review/lattice-dashboard-review.patch
```

Without this server the patch adds no review section; its comment,
artifact and refresh changes still apply. Re-apply it after updating
Lattice; if it no longer applies, it touches `_read_artifact_info` in
`src/lattice/dashboard/server.py` and, in
`src/lattice/dashboard/static/index.html`, one CSS rule,
`openDetailPanel`, `_renderPanelContent`, `_refreshAfterPanelEdit`,
`route`, `renderDetail` and `startAutoRefresh`. The server also builds on
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
| `POST /review/t/<ID>/plannotator` | `plannotator review --patch-file -` with the range; redirects to the session; the JSON decision becomes a review comment |
| `POST /review/t/<ID>/close` | ends the task's open session, recording nothing |
| `POST /review/t/<ID>/open`, `/filediff` | `code` on one file of the range, or `code --diff` |
| `/review/t/<ID>/history` | the task's history, shown in the dashboard's History section |
| `POST /review/t/<ID>/openplan` | the plan in VS Code, scaffolded when missing |
| `POST /review/t/<ID>/plan` | `plannotator annotate <plan file> --gate --json`; redirects to the session; the decision becomes a `plan-review` comment and threads |
| `POST /review/t/<ID>/complete` | `lattice status <ID> done --no-auto-review` under the rule in What completes a task |
| `POST /review/t/<ID>/reply` | `lattice comment <ID> --reply-to <thread> --file` with the owner's reply; with `resolve=1` also the `resolved` reaction, once the reply posted |
| `POST /review/t/<ID>/resolve`, `/reopen` | `lattice react` or `unreact` with `resolved` on a thread |
| `POST /review/t/<ID>/rework` | `lattice status <ID> in_progress --no-auto-review` |
| `POST /api/tasks/<id>/status` | the dashboard's status change; `done` is refused with `REVIEW_REQUIRED` under the same rule |
| `POST /api/tasks/<id>/open-notes`, `/open-plans` | Lattice's notes and plans, opened with `code` instead of xdg-open |
| `/t/<ID>` | redirects to the task in the dashboard; the Dependencies and History links use it |
| `/review` | redirects to `/` |

Review POSTs carry a per-run token; dashboard POSTs must carry an Origin
equal to the address the page was served from, a JSON object body, and
at most 1 MiB. Neither is a boundary against an agent that can already
edit the files and the board.

## Tests

From `swe/tools/lattice-review`:

```
python3 -m unittest test_lattice_review test_merge_approved test_owner_review
<python with lattice installed> -m unittest test_lattice_review
```

Non-socket checks can run separately:

```
<python with lattice installed> -m unittest test_lattice_review.PureTests test_lattice_review.NativeGitTests
```

They cover the signature-helper and missing-object regressions with
harmless marker programs, real disposable Git repositories and the
installed native Git reader. The native handler error check invokes the
handler directly, without binding a socket. The full suite above still
requires loopback sockets. A fake Plannotator checks patch handoff and
feedback handling; it does not verify the real browser or binary. The
owner checks that round trip after installation.

The first full run covers the review logic against a stand-in dashboard; the
second, with the interpreter the `lattice` command uses (its shebang
names it), also runs Lattice's real dashboard handler in process. The
tests build a temporary git repository and board, a stand-in
`plannotator` that answers with a fixed decision, and a stand-in `code`
that logs what it was asked to open; they do not need the real
Plannotator or VS Code. Tests that record on a board run only when
`lattice` is on PATH.
They ignore `LATTICE_ROOT`, so a session that has it set never writes
test tasks to a real board.
