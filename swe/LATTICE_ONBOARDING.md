# Lattice onboarding

Optional setup for an owner who wants a project board and review flow.
Do not initialize a board, install tools or create backlog items as a side
effect of another task. Words in angle brackets are placeholders.

## What you end up with

- A `.lattice/` board in the project root, left uncommitted until the
  owner asks for it.
- A backlog with one task per open item, acceptance criteria on the ones
  that can be checked, and decisions flagged `needs_human`.
- The Lattice dashboard run by the review server
  ([tools/lattice-review/](tools/lattice-review/)), one page where each
  task's detail view carries a review section: the task's commits, with
  buttons that open them in Plannotator or file by file in VS Code, one
  thread per review note with Reply and Resolve, and done gated on an
  approval of exactly those commits with every thread resolved.
- Reviews recorded on the task as comments, the owner moving tasks to
  done, and the owner pushing.

## Who does what

The owner initializes the board and selects or authorizes its tasks.
The agent resumes only the selected task and leaves prepared work in
`in_review`; it commits only when asked. The owner installs tools, runs
the review server, reads diffs, completes tasks, pushes and deploys.
Agents never run `lattice next`, `lattice complete`, `lattice status
<ID> done` or `git push`, and never commit `.lattice/` unless told to.

## One-time installs, by the owner

Plannotator, binary only, from the shell the agent sessions run in.
Download the installer, read it, then run it; never pipe a download into
the shell (SECURITY_PROTOCOL.md):

```
curl -fsSLo plannotator-install.sh https://plannotator.ai/install.sh
less plannotator-install.sh
bash plannotator-install.sh --minimal
rm plannotator-install.sh
```

The review server runs the binary itself, so no agent plugin is needed and
the editor extension for Claude Code is enough; the interactive CLI never has
to be opened. The Claude Code plugin is optional: it adds a plan-review
gate at plan exit and an in-session `/plannotator-review`. Add it later
from a terminal with `claude plugin marketplace add backnotprop/plannotator`
and `claude plugin install plannotator@plannotator`, then restart the
editor. Put these two lines in the shell profile so nothing leaves the
machine from a review:

```
export PLANNOTATOR_AI=disabled
export PLANNOTATOR_SHARE=disabled
```

Plannotator ends every review that has notes with its own instruction to
the agent, which asks for a verdict on each note. Replace it so agents
answer in the threads instead: add this `prompts` key to
`~/.plannotator/config.json`, next to any keys already there. The leading
blank lines keep it out of the last note's thread.

```
"prompts": {
  "review": {
    "denied": "\n\n\n\nEach note above is its own thread on the task. Answer each one in its thread, in the reply shape in .lattice/context.md, before changing any code."
  }
}
```

Skip Plannotator's VS Code extension: it does not take over reviews
started from the Claude Code VS Code extension, and the review server
already opens Plannotator in the browser. With the plugin installed, plan mode opens Claude's plans in
Plannotator too; the task's Lattice plan file stays the plan of record.

The dashboard patch, applied once to the Lattice checkout the `lattice`
command runs from, so the dashboard renders the review section when it
is served through the review server (and URL artifacts as links):

```
cd <lattice checkout>
git apply <agent-alignment>/swe/tools/lattice-review/lattice-dashboard-review.patch
```

Re-apply it after updating Lattice.

Lattice itself is assumed present (`lattice --version`).

## Per project, setup by the owner

### 1. Initialise

```
cd <project>
LATTICE_NO_UPDATE_CHECK=1 lattice init --path . \
  --actor human:<owner> --project-code <CODE> --project-name "<name>" \
  --preset linear --workflow classic \
  --review-mode inline --plan-review-mode inline --plan-approval human \
  --done-display all --no-seed --no-setup-claude --no-setup-agents \
  --description "<one line saying what the board covers>"
```

`<CODE>` is one to five capital letters; task IDs become `<CODE>-1`,
`<CODE>-2` and so on. Skip `--no-setup-claude` only when the agent's
global instructions do not already carry the Lattice rules.

### 2. Config

During setup, the owner configures `.lattice/config.json`:

| key | value | why |
|---|---|---|
| `auto_code_review_on_transition` | `false` | a status change never starts a review |
| `auto_plan_review_on_transition` | `false` | same |
| `dashboard.theme` | `"holographic"` | any theme works |
| `dashboard_port` | next free port | one port per board; the review server serves the dashboard there |

Keep a line in `context.md` naming the port the owner opens.

### 3. Context

Write `.lattice/context.md` from this template:

```
# <name>

## Purpose

One board for <project> at <path>: <what it covers, one or two sentences>.

## Related Instances

<other boards with the same conventions, or "None">

## Conventions

- Tags name the area: <tag list, lowercase, one word each>.
- backlog is captured. todo is selected by the owner; selected work that
  waits for plan approval stays todo with needs_human set. in_progress is
  active implementation, or a research deliverable the owner authorized.
  in_review means prepared locally and waiting to be read, pushed and
  deployed by the owner. Nothing leaves the machine from a session.
- needs_human holds one question for the board owner, starting with
  "Need:". Other decisions go in the plan under "Decisions for <owner>",
  one per line, so each can be answered as its own Plannotator note. A
  session clears a flag only when the owner tells it to, and quotes the
  owner's words in the note; being told to start work does not approve a
  plan.
- Lattice is the source of truth for scope, decisions, status,
  criteria, evidence and remaining work. Chat notifies the owner and
  summarizes what Lattice says; a decision made in chat is written to the
  task first, then reported. If task records conflict, stop and say so.
- Every write passes --actor agent:<tool> and runs with
  LATTICE_NO_UPDATE_CHECK=1. Sessions use lattice show to resume the task
  they were given, then lattice comments <ID> --json and the task's plan,
  plus the plans of tasks it depends on; agents never use lattice next,
  lattice complete or lattice status <ID> done.
- An owner comment or plan note is reconciled into the plan, description,
  criteria, needs_human reason and status before the result is reported;
  a comment that asks a question gets a reply. Detailed decisions live in
  one owning task; dependent tasks link to it and inherit them, and a
  proposed deviation is a needs_human on the owning task. Run lattice
  doctor after a reconciliation round.
- Plan before code. For a task that changes behaviour, the session writes
  the plan to the file `lattice plan <ID>` names, sets
  `needs-human <ID> "Need: approve plan"` and stops, in todo. The owner
  reviews it with "Plannotator: review the plan" in the task's review
  section, or comments on the task; a question is not an approval. Notes
  become threads that the session answers like code review threads,
  revising the plan file and setting the flag again. Approve records the
  approval for the plan as it was opened and clears the flag; if the file
  changed during the session, the owner reviews it once more. Keep the
  words approve and plan in that flag: the server clears only such a
  flag, and only if it did not change during the session. Otherwise the
  flag rule above applies.
- in_progress only while implementation, or an authorized research
  deliverable, is active; in_review while the prepared result waits for
  the owner. Record assignment and status before
  dispatching a subagent; the coordinating session owns the board writes
  and records the result when delegated work ends.
- One task, one branch, one worktree. Before its first edit a task gets
  branch feature/<CODE>-<n>-<slug> from <branch> in its own worktree at
  <worktree root>/<CODE>-<n>, linked with lattice branch-link. All edits,
  tests and dev servers for it run there, on its own ports, with
  LATTICE_ROOT=<board directory> set. The main checkout stays on <branch>
  for the owner's merges and board writes; no session edits files there.
  At most three sessions or workers at once.
- The comment roles review and plan-review are written by the review
  server for the owner's Plannotator decisions. Agents use validation for
  evidence and no role otherwise.
- Commits for a task end with a trailer line `Task: <CODE>-<n>` so the
  review section can find them; it looks on the integration branch, the
  checkout's HEAD and linked branches, so branch work is linked with
  lattice branch-link. The integration branch is <branch>.
- The task record holds the request, scope, acceptance criteria, owner,
  revision, coverage boundary, evidence and remaining work. Never secrets.
- Findings, decisions and evidence go on the task they belong to, as
  comments or `lattice attach` artifacts, never in separate report files.
  Attach only sanitized references: no client documents, personal data,
  credentials, transcripts or raw request and response bodies.
- Review flow: the owner opens the board at http://127.0.0.1:<port>
  (the review server, started with --main <branch> and a human: actor,
  which is the dashboard plus a review section on every task). There
  the owner opens the task's commits in Plannotator
  or file by file in VS Code; the review lands on the task as a comment
  bound to the reviewed commits. Each note in it becomes its own thread:
  a top-level comment that starts with `Thread:`, names the file, line
  and commit, and quotes the line. The owner continues a thread with
  Reply in the review section; a later note on the same lines while the
  thread is open lands in that thread. Only the owner resolves a thread.
  A task with commits can be marked done only while its latest review
  approves exactly those commits and every code and plan thread is
  resolved. Done is not deployed.
- Answering a review: read `lattice comments <ID> --json`, then reply
  once in every thread whose last message is the owner's (the section
  shows it as waiting on the agent), with
  `lattice comment <ID> --reply-to <thread id> --file <reply.md>`, in
  this shape (leave out Why and Question when there is nothing to say):

      Status: answered | change proposed | changed in <sha> | declined
      Answer: <the answer to what was asked, in one or two plain sentences;
        yes or no first when the note asks yes or no>
      Why: <what the reader needs to follow the answer: what the line does,
        what was wrong before, what breaks without it>
      Evidence: <file:line, commit, command and its result; say what was
        not checked>
      Change: <none | proposed, not made: <what and where> | made in <sha>:
        <what changed>>
      Question: <one decision needed from the owner>

- Reply rules: answer the note as written; a question gets an answer, not
  a code change. Change code only where a note asks for a change or the
  owner agreed to a proposed one, and touch only what the note is about.
  Check the code before agreeing or disagreeing; disagree with reasons.
  When the answer is something a future reader needs, propose putting it
  in the code, doc or commit message. One reply per thread per round,
  about 120 words, no praise, no restating the diff, no verdict labels in
  place of an answer. A message from the owner that accepts the answer
  and asks nothing gets no reply; it waits for the owner's Resolve. Never
  resolve a thread or edit the owner's words.
  A finding outside the note goes in the round summary, not the thread.
- After answering: one top-level round summary listing each thread
  answered (place, Status, one line), the checks run and what remains;
  then move the task to in_review.
- Writing on the board: every comment, flag, description and plan is
  written for the owner, who did not watch the work. Use plain words and full
  sentences.
  - Start with one or two sentences that say what happened and what you
    need from the owner, if anything. Someone who reads only that much should
    know where things stand.
  - Then explain why: what was wrong or missing, what you changed, and
    what it means for the product or for the owner.
  - Say what a thing is before its name or path: "the PDF form editor
    (frontend/src/pages/FormBuilder.jsx:460)", not the path alone. Spell
    out a code or abbreviation the first time, such as "acceptance
    criterion 4 (each change refreshes only that organization's data)".
  - One idea per paragraph or list item. No walls of text and no chains of
    jargon.
  - Evidence in plain sentences: what you ran and what it showed. Raw
    output, long file lists and hashes go in an attachment
    (lattice attach), not in the comment.
  - A question gives the options and your recommendation.
- The board is not committed until asked.
```

### 3a. Agent instructions

Sessions read the project's AGENTS.md (or CLAUDE.md) at start and
`context.md` only when they follow a pointer to it. Put the rules that
must hold from the first edit in AGENTS.md as well:

```
## Working a task (every agent)

- Never edit files in this checkout for task work. It stays on <branch>
  for the owner's merges and for board writes.
- Before the first edit for <CODE>-<n>:
    git worktree add <worktree root>/<CODE>-<n> -b feature/<CODE>-<n>-<slug> <branch>
    LATTICE_NO_UPDATE_CHECK=1 lattice branch-link <CODE>-<n> feature/<CODE>-<n>-<slug> --actor agent:<tool>
  Then edit, test and run servers only there, with
  LATTICE_ROOT=<board directory>.
- One question per needs_human flag, starting "Need:"; other decisions
  go in the plan, one per line. Clear a flag only when the owner says so,
  quoting the owner's words in the note.
- The comment roles review and plan-review are only for the owner's
  Plannotator results. Agents use validation, or no role.
- At most three workers at once, each in its own task's worktree.
- Write board comments for the owner in plain language: the point first, then
  why, what a thing is before its path, one idea per paragraph, raw output
  attached rather than pasted. The full rule is "Writing on the board" in
  .lattice/context.md.
- Never run lattice status <ID> done, lattice complete or lattice next;
  completion is the owner's, through the review section.
```

### 4. Backlog

Capture only items the owner explicitly authorizes. Findings and earlier
session notes are input, not permission to create or start more tasks.
Keep one record per authorized task.

Every create carries `--actor agent:<tool>` and a description in this
shape:

```
Request: <where it came from and what is wrong or wanted>.
Scope: <the change, named files or commands>.
Owner: <who prepares; who runs the remote or destructive part>.
Coverage boundary: <what local checks prove; what stays unverified until deployed>.
Remaining: not started.
```

Rules for the fields:

- Title: imperative, under 80 characters, no ticket prefix.
- Type: `task` for a change, `bug` for broken behaviour, `chore` for
  cleanup, `spike` for research with no change.
- Priority: `high` for exposure or data risk, `medium` for correctness and
  robustness, `low` for cleanup and nice-to-have.
- Tags: areas from `context.md`, two or three at most.
- Criteria: `lattice criterion add <ID> "<observable outcome>"` for each
  thing a reviewer can check. Skip criteria that restate the title.
- Decisions: `lattice needs-human <ID> "Need: <the exact question>"`.
  One question per flag.

Create an onboarding task only if the owner asks for that record. Existing
task records remain private unless the owner asks to share them.

### 5. Working a task

1. `lattice show <ID>` to resume, then `lattice comments <ID> --json` for
   the full review threads (`show` cuts comment bodies short). Before any
   change, reply in every thread that waits on the agent, in the shape
   and under the rules in `context.md`. A thread is a top-level comment
   that starts with `Thread:`; an older annotated review with no
   `Thread:` comments is one thread itself. Once the plan is approved
   and work starts, `lattice status <ID> in_progress --no-auto-review`.
2. When asked to commit, use the project's convention and end with a
   blank line and `Task: <ID>`. Several IDs: `Task: <ID>, <ID>`.
3. Before the first edit, the task's worktree and branch:
   `git worktree add <worktree root>/<ID> -b feature/<ID>-<slug> <branch>`
   and `LATTICE_NO_UPDATE_CHECK=1 lattice branch-link <ID>
   feature/<ID>-<slug> --actor agent:<tool>`. Edit, test and run
   dev servers only there. Lattice finds the board by walking up from the
   working directory, so the session sets `LATTICE_ROOT=<board
   directory>`.
4. Before handing over: the round summary, a top-level comment with each
   thread answered and its Status, the checks run, their results, what
   was mocked, what never ran, and what remains for the owner.
   `lattice attach <ID> <file or URL> --title "<what it is>"` for
   evidence files.
5. `lattice status <ID> in_review --no-auto-review`. Stop there.

### 6. The review flow, by the owner

From a VS Code integrated terminal in the project (so files open in
that window):

```
python3 <agent-alignment>/swe/tools/lattice-review/lattice_review.py --actor human:<name> --main <integration branch>
```

`--main` defaults to `main`; a task's branch is diffed from its
merge-base with it. Restart the server after updating this tool. Open
http://127.0.0.1:<port> and click a task. Its detail view has a Review
section with two blocks, after a Dependencies block when the task has
links. Plan shows the plan's state with "Plannotator: review the plan"
and "Open the plan in VS Code"; with no plan file its one button is
"Write the plan in VS Code" (see the plan rule in `context.md`). Code
review says where the task's work is (branch, trailer commits, or
nothing yet) and offers: Plannotator on the whole range, Plannotator per
commit, and for every file of the range `diff` in VS Code's two-file
view, and `open` when the range ends at this checkout's HEAD. The task's
History section, below Comments, says what changed on the task, by whom
and why. Plannotator opens as a new
tab of the same browser; annotations stay there until Send Feedback
(changes requested) or Approve, and only then do they land on the task
as a comment with role `review`, visible to every browser and every
agent. Plannotator then shows a page saying the feedback went back to
the agent: close that tab and return to the board. Each note lands as
its own thread in the Review section, with the quoted line, every reply
in order, a Reply box, Reply and resolve, and Resolve; a resolved thread
has Reopen. To accept an answer with a last word use Reply and resolve;
a plain Reply leaves the thread waiting on the agent. While a thread is
open, a second note on the same lines adds to it instead of starting
another. A line at the top of the section says what to do next. One
Plannotator session per task, plan and code together: any Plannotator
button returns to the open one, and "Close session" ends one that was
abandoned. When the checkout that has the task's branch checked out
(often the task's worktree) has uncommitted changes, a second button
names that checkout and reviews them, for feedback only: it never
completes a task and, as the latest review, it withdraws an earlier
approval until the range is reviewed again. Status, comments,
notes and plans are the dashboard's own controls on the same page;
writes made there carry the owner's actor. The review is bound to the
commit IDs it covered: "Mark done" appears only while the latest review
is an approval of the task's current commits and every thread is
resolved, the dashboard's status control refuses `done` under the same
rule, and the section says why otherwise. Mark done before merging a
linked branch: after the merge the task's work is found only through
its `Task:` trailers, and a task whose commits lack them reads as having
no work and is no longer gated. Then merge locally; pushing can wait for
a checkpoint, since every commit was reviewed.

Feedback that needs more work: "Move to in progress" in the section, or
the status control when the section offers no button, then give the
agent the task ID. Lattice has no notifications; the side
panel refreshes when the task record changes, the full task page does
so when it was reached from the board or list, and the Refresh button
in the top bar forces it.

### 7. Reporting

When the board is set up, the reply to the owner lists: the init command
used, the ports, the number of tasks and which carry `needs_human`, what
the owner must install or run, and what is unverified (Plannotator and
the browser flow are unverified until the owner has used them once).

## Day to day

The owner: start the review server, read the in-review tasks, review,
reply in or resolve threads, complete, push and deploy, approve plans
in Plannotator (which clears that flag) and answer other `needs_human`
questions by clearing the flag with a note
(`lattice needs-human <ID> --clear --note "<decision>" --actor human:<name>`).

The agent: take only the task it was given, answer every thread that
waits on the agent in the reply shape before changing code, keep the task record current
(evidence, coverage boundary, remaining work), commit with the trailer,
leave the task in review, never resolve a thread, complete or push. A
new finding becomes a comment on the task it belongs to, or a question
to the owner, never a new task without being asked.

## Keeping this file current

This file is the template. When a project onboarding changes the way the
board, review server or review flow is used, change this file in the same
piece of work and say so in the task comment. Project-specific details
belong in that project's `context.md`, never here.
