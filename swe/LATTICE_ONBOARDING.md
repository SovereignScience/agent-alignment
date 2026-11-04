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
the review server, reads diffs, completes tasks, pushes and deploys. Agents never run `lattice next`, `lattice complete`
or `git push`, and never commit `.lattice/` unless told to.

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
started from the Claude Code VS Code extension (backnotprop/plannotator
issue 496), and the review server already opens Plannotator in the
browser. With the plugin installed, plan mode opens Claude's plans in
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
| `dashboard.theme` | `"holographic"` | the theme the existing boards use; any theme works |
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
- backlog is captured. todo is selected by the owner. in_progress is being
  worked. in_review means prepared locally and waiting to be read, pushed
  and deployed by the owner. Nothing leaves the machine from a session.
- needs_human marks a decision for the board owner. The flag reason says
  exactly what is being asked.
- Every write passes --actor agent:<tool> and runs with
  LATTICE_NO_UPDATE_CHECK=1. Sessions use lattice show to resume the task
  they were given; agents never use lattice next or lattice complete.
- Plan before code. For a task that changes behaviour, the session writes
  the plan to the file `lattice plan <ID>` names, sets
  `needs-human <ID> "Need: approve plan"` and stops. The owner reviews it
  with "Plannotator: review the plan" in the task's review section. Notes
  become threads that the session answers like code review threads,
  revising the plan file and setting the flag again. Approve records the
  approval and clears the flag. The session never clears that flag itself.
- Commits for a task end with a trailer line `Task: <CODE>-<n>` so the
  review section can find them. Branch work is linked with lattice
  branch-link. The integration branch is <branch>.
- The task record holds the request, scope, acceptance criteria, owner,
  revision, coverage boundary, evidence and remaining work. Never secrets.
- Findings, decisions and evidence go on the task they belong to, as
  comments or `lattice attach` artifacts, never in separate report files.
  Attach only sanitized references: no client documents, personal data,
  credentials, transcripts or raw request and response bodies.
- Review flow: the owner opens the board at http://127.0.0.1:<port>
  (the review server, which is the dashboard plus a review section on
  every task). There the owner opens the task's commits in Plannotator
  or file by file in VS Code; the review lands on the task as a comment
  bound to the reviewed commits. Each note in it becomes its own thread:
  a top-level comment that starts with `Thread:`, names the file, line
  and commit, and quotes the line. The owner continues a thread with
  Reply in the review section; a later note on the same lines while the
  thread is open lands in that thread. Only the owner resolves a thread.
  A task with commits can be marked done only while its latest review
  approves exactly those commits and every thread is resolved. Done is
  not deployed.
- Answering a review: read `lattice comments <ID> --json`, then reply
  once in every thread that waits on you, with
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
- The board is not committed until asked.
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
   `Thread:` comments is one thread itself. `lattice status <ID>
   in_progress --no-auto-review`.
2. When asked to commit, use the project's convention and end with a
   blank line and `Task: <ID>`. Several IDs: `Task: <ID>, <ID>`.
3. Branch work: `lattice branch-link <ID> <branch>`. Lattice finds the
   board by walking up from the working directory, so a session in a
   separate worktree sets `LATTICE_ROOT=<board directory>`.
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
section with two blocks. Plan shows the plan's state with "Plannotator:
review the plan" and "Open the plan in VS Code" (see the plan rule in
`context.md`). Code review says where the task's work is (branch,
trailer commits, or nothing yet) and offers: Plannotator on the whole
range, Plannotator per commit, and for every file of the range `open` in
VS Code or `diff` in VS Code's two-file view. A History block below says
what changed on the task, by whom and why. Plannotator opens as a new
tab of the same browser; annotations stay there until Send Feedback
(changes requested) or Approve, and only then do they land on the task
as a comment with role `review`, visible to every browser and every
agent. Plannotator then shows a page saying the feedback went back to
the agent: close that tab and return to the board. Each note lands as
its own thread in the Review section, with the quoted line, every reply
in order, a Reply box, Reply and resolve, and Resolve. While a thread is
open, a second note on the same lines adds to it instead of starting
another. A line at the top of the section says what to do next. One
session per task at a time: the button returns to the open one, and
"Close session" ends one that was abandoned. When the checkout that has
the task's branch checked out (often the task's worktree) has
uncommitted changes, a second button names that checkout and reviews
them, for feedback only: it never completes a task. Status, comments,
notes and plans are the dashboard's own controls on the same page;
writes made there carry the owner's actor. The review is bound to the
commit IDs it covered: "Mark done" appears only while the latest review
is an approval of the task's current commits and every thread is
resolved, the dashboard's status control refuses `done` under the same
rule, and the section says why otherwise. Mark done before merging a
linked branch into the integration branch: after the merge the branch's
range is empty and the review no longer matches it. Then merge locally;
pushing can wait for a checkpoint, since every commit was reviewed.

Feedback that needs more work: "Move to in progress" in the section,
then give the agent the task ID. Lattice has no notifications; the side
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
reply in or resolve threads, complete, push and deploy, answer the
`needs_human` questions by clearing the flag with a note
(`lattice needs-human <ID> --clear --note "<decision>" --actor human:<name>`).

The agent: take only the task it was given, answer every open thread in
the reply shape before changing code, keep the task record current
(evidence, coverage boundary, remaining work), commit with the trailer,
leave the task in review, never resolve a thread, complete or push. A
new finding becomes a comment on the task it belongs to, or a question
to the owner, never a new task without being asked.

## Keeping this file current

This file is the template. When a project onboarding changes the way the
board, review server or review flow is used, change this file in the same
piece of work and say so in the task comment. Project-specific details
belong in that project's `context.md`, never here.
