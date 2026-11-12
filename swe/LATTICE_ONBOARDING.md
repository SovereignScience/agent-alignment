# Lattice onboarding

Optional setup for an owner who wants a project board and review flow.
Do not initialize a board, install tools or create backlog items as a side
effect of another task. Words in angle brackets are placeholders.

## What you end up with

- A `.lattice/` board in the project root, versioned in its own private
  repository and ignored by the source repository.
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

### The short way

From the top of the project:

```
bash <agent-alignment>/swe/scripts/board_setup.sh --actor human:<owner>
```

It does steps 1, 2, 3 and 3b below and changes no tracked file. The
project name is the folder name, the code its initials, and the port the
first from 8803 that nothing listens on; if another board already has
that port, change `dashboard_port` in `.lattice/config.json` and the port
line in `context.md`. It ends with a line that starts `READY:`. Add
`--remote <url>` to push the new board to its private repository, which
the owner creates first. It refuses a project that already has a board.

Then fill in the tags in `context.md`, do step 3a, start the review
server (step 6) and give the project's first session the message in
step 4a.

### Bringing a board back

On another machine, or after `.lattice/` was lost, run the same command
with the board's repository:

```
bash <agent-alignment>/swe/scripts/board_setup.sh --remote <url>
```

A repository that already holds a board is cloned into `.lattice/`
instead of a new board being made. Work that was never pushed there is
not in it, so run `board_update.sh --apply` after each session that wrote
to the board.

### Keeping a board current

From the top of a project that has a board:

```
bash <agent-alignment>/swe/scripts/board_update.sh
bash <agent-alignment>/swe/scripts/board_update.sh --apply
```

The first says what is behind and changes no file. With `--apply` it
merges this guide's template changes into `context.md`, commits the
board's own changes, merges what its remote has and pushes. Two sides
that wrote to the same task are merged. Two sides that each created a
task are not: it stops, names the file and pushes nothing, because both
tasks took the same ID. Pull the board before creating tasks on a second
machine.

The steps below are what the command runs, for doing it by hand or
changing a setting.

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
- Stage: <build or lock down>. The owner sets it for the project, and a
  task's description may name the other one. It decides what is left
  out, not how safe the work is. The same at both stages: security,
  secrets, data loss, money, anything hard to undo, the guard and
  sandbox limits, a test for each behaviour changed and each bug fixed,
  and honest claims about what was checked.

  | | build: the first version that works | lock down: before and in production |
  |---|---|---|
  | Scope | one path that works end to end for the first user | every path a user can reach, and each failure case |
  | Options, settings, abstractions | none until a second use exists | only where an operator needs one |
  | Error handling | fail loudly where it happens | recovery, and messages a user can act on |
  | Tests | the acceptance criteria and each fixed bug | also failure paths, upgrade and rollback |
  | Performance | only what a user would notice | measured against a named budget |
  | Docs | how to run it | also how to deploy, recover and roll back |
  | Old data and old callers | kept only where real data or users exist | kept, with a tested migration |
  | Monitoring | none | a health check, and an alert for each failure a user would feel |
  | Review findings that hold a merge | P0 and P1 | P2 too, on a path a user reaches |
  | New features | when the task asks | none: only changes that lower risk |

- Cut for now: what the stage leaves out is not built, not planned and
  not made into a task. Name each item in one line under "Cut for now"
  in the plan, so the owner can pull any of it back. Before a task goes
  to in_review, ask whether the stage needs it at all; if it does not,
  say so in one line and propose parking it.
- Parking: a task that does not make the cut is archived, not left in
  backlog or review: a note that starts "Cut:" and says what would bring
  it back, then `lattice archive <ID>`. It keeps its record and returns
  with `lattice unarchive <ID>`. Parking is the owner's choice: a session
  proposes cuts in one list and archives only the tasks the owner names.
- backlog is captured. todo is selected by the owner; selected work that
  waits for plan approval stays todo with needs_human set. in_progress is
  active implementation, or a research deliverable the owner authorized.
  in_review means prepared and on its way into use: waiting for review,
  merge, install or live checks. A task stays there, with one Need: flag
  naming the owner's next step, until it is done. Remote writes and
  administration are owner-run; approved reads follow the managed access
  policy.
- needs_human holds one question for the board owner, starting with
  "Need:". Other decisions go in the plan under "Owner decisions",
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
- Ask before the plan. Read the task, the code it touches and the
  related tasks first, and ask only what they cannot answer. A task is
  clear when you can say who needs the change, what goes wrong today,
  the result they expect, how the owner will check it and what is out
  of scope. Until then ask one question at a time, the one whose answer
  changes the most first, each with two to four options and your
  recommendation, answerable in a few words. Leave out style and
  anything cheap to undo; those are Assumptions in the plan. Stop when
  the task is clear or after five questions, write each answer into
  the task in the owner's words, then write the plan.
- Plan before code. Before the first edit to a guardrail file there is a
  board task with an approved plan, however small the request and
  whoever made it. Guardrail files are settings, hooks, scripts, agents,
  commands, rules and instruction files: any CLAUDE.md or AGENTS.md, the
  protocols, anything under .claude/ or codex/, the installers. For any
  other task that changes behaviour, the session writes the plan in the
  plan shape below to the file `lattice plan <ID>` names, sets
  `needs-human <ID> "Need: approve plan"` and stops, in todo. A task the
  owner selected skips that stop, with no flag, when its plan fits the
  small-fix form (Need, Acceptance criteria, Steps, Coverage boundary),
  leaves the owner nothing to decide, is easy to revert and touches no
  guardrail file, authentication, permissions, secrets, network access,
  stored data or its format. The plan says which of these it checked.
  When in doubt it is not small. The owner's review of the code is still
  required before a merge.
  For every other task the owner
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
  .worktrees/<CODE>-<n>, linked with lattice branch-link. .worktrees/ stays
  inside the checkout and in .git/info/exclude: the sandbox reaches only the
  session's own project folder, so a worktree elsewhere is out of reach. The
  project's test, lint and build tools ignore .worktrees/. All edits,
  tests and dev servers for it run there, on its own ports, with
  LATTICE_ROOT=<board directory> set. The main checkout stays on <branch>
  for the owner's merges and board writes; no session edits files there.
  At most three sessions or workers at once.
- One version is the default. A plan proposes competing versions, and
  the owner decides when approving it, only when the approach is open
  and the plan cannot settle it, a mistake would be costly (security,
  data, money, hard to undo), or a first attempt failed review; and
  only when the acceptance criteria can tell the versions apart. Then
  two candidates, three at most, in .worktrees/<CODE>-<n>-a, -b and -c
  on branches feature/<CODE>-<n>-<slug>-a and so on, all from the same
  commit and the same approved plan. One session builds each, from a
  different tool where possible, and sees no other candidate's work.
  Candidate branches are not linked to the task: the review section
  reads only the first linked branch that has commits.
  A session that built none of them compares them against the plan and
  the criteria and attaches the scorecard. The owner picks, links that
  one branch with lattice branch-link and reviews it like any other
  task. Without a clear winner, say so. The rest are removed after the
  merge.
- If source Git metadata is read-only, the owner runs worktree setup and
  source Git writes. Agents edit and test allowed files in the created
  worktree and keep Lattice updated. Give the owner named-path staging
  and commit commands; never widen Git access or use another Git directory
  to bypass a refusal.
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
  resolved. Mark it done only when the work is merged, installed where it
  applies, and every acceptance criterion has recorded evidence. Done is
  final.
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
- Other updates have a shape each. Leave out a line with nothing to say,
  keep each line to one sentence and attach the rest. Post an Evidence
  note when a criterion's result is known, not one for each step.

  Evidence, posted with `--role validation` and `--criterion` for each
  criterion it covers:

      Met: <what now works, in one sentence the owner can check>
      Checked: <each command and its result, and the commit it ran on>
      Not checked: <what was mocked, and what never ran>
      Remains: <the owner's next step, or none>

  When the criterion is still open, the first line is
  `Not met: <what is missing>` instead. The review section reads that
  first word: a criterion whose newest note says Not met cannot be
  marked done.

  Handover, the round summary posted before in_review:

      Result: <what is ready for the owner, in one sentence>
      Threads: <place, Status and one line for each; or none>
      Changed: <each commit or attached patch and what it does, in a few
        words>
      Checked: <as in Evidence>
      Not checked: <as in Evidence>
      Look first at: <the file or decision most worth the owner's time>
      Remains: <what is left for the owner>

  Paused, when a session stops part way through a task:

      Paused: <what is done and checked so far>
      Next: <the exact next step>
      Open: <what is still uncertain, or none>

  Blocked, when a step is refused or cannot be done from the session:

      Blocked: <the command or step, and what refused it>
      Needed for: <what the task cannot do without it>
      For the owner: <the exact command, or the decision>
      Meanwhile: <the steps that did not need it, now done>

  Question, the text of a needs_human flag:

      Need: <one question>. Options: <A>; <B>. Recommended: <A>,
        because <reason>.

  The flag on a task in in_review names the owner's next step in place
  of a question: `Need: <the step>`.
- Finishing: the acceptance criteria are the finish line. Work until
  each has evidence or waits on the owner. An error, a timeout or a
  failing tool is ordinary work to diagnose and fix; a guard, sandbox or
  rule refusal is the owner's to lift and is never worked around. When
  one step waits on the owner, finish every step that does not depend on
  it, then stop once.
- Context: a chat may run long and cover several tasks. Never ask the
  owner to start a new one; keep the chat sound yourself.
  - When the task changes, or after the chat has been compacted, read
    the task again (lattice show, its plan and its comments) and work
    from that record, not from memory of the chat.
  - Before stopping part way, post a Paused note, so this chat or any
    other can resume from the board.
  - Give work that needs none of this chat's history to a subagent,
    with a brief that stands alone: the goal, the paths, what to return
    and a word limit. A search, a long log and a bug reproduction are
    such work. Keep the raw output out of this chat.
  - If an answer contradicts the task record or an earlier result, say
    so in one line and read the record again.
- Sessions talk through the board. To use another session's result, read
  its note with lattice comments. Each session writes its own results;
  no note repeats what another session said, and the owner is never
  asked to carry text between sessions.
- Before in_review, check what the owner most often sends back. The
  first lines of the plan or handover say what is wrong today and what
  changes. Every claim that something is recommended practice names its
  source. Every choice left to the owner has options and a
  recommendation, and a choice that is cheap to undo is already taken
  and listed under Assumptions.
- Keeping review small: a finding is graded P0 to P3 by its harm, as
  the code reviewer's file defines them, and this rule decides what a
  grade holds. P0 and P1 hold a merge. P2 holds it only in lock down, on
  a path a user reaches. P3 never does. A P0 or P1 says what confirmed
  it, and an unconfirmed one holds nothing. A finding that holds
  nothing is fixed in passing or dropped;
  if it matters later it becomes a task the owner authorizes. Tests
  cover each behaviour in the acceptance criteria and each fixed bug,
  nothing more; a request for another test names the behaviour left
  unpinned. A thread gets two rounds: if the owner's note after the
  second reply still disagrees, set one Need: flag that gives both
  positions, and the owner decides.
- How much review a change gets, by what it touches. Docs or a small
  fix: the author's own read, labelled as the author's. Other changes
  in behaviour: the owner's review in build, and in lock down the code
  reviewer first. A guardrail file, authentication, permissions,
  secrets, network access or stored data, at either stage: before
  in_review the session starts the code reviewer, which has not seen
  its chat, then the skeptic and arbiter pair, and the handover asks
  the owner for a pass by the other tool. Where a tool cannot start an
  agent, the handover asks for the review instead. No other review
  starts unasked, and an author never records a verdict on its own work.
- Decisions that last are records in the repository, listed in its
  decision index (docs/ADR-INDEX.md where the project follows this
  kit). Before planning, open each accepted record that governs a file
  the task will touch, and name them in the plan. A plan that goes
  against an accepted record proposes the record that supersedes it.
  When a task settles something hard to undo, or rejects an option
  someone will try again, its last step drafts a record with status
  proposed. Only the owner changes a status to accepted, and an
  accepted decision is never edited: a new record supersedes it.
- The board is versioned separately from source, in its own private
  repository at .lattice/. A board checkpoint requires an explicit request;
  remote creation and pushing remain the owner's. In a cloud session the
  owner has no shell, so a push the owner asks for there is run by the
  session, with the repository's own push script and nothing else.
- Writing on the board: every comment, flag, description and plan is
  written for the owner, who did not watch the work. Use plain words and full
  sentences.
  - State the owner or customer requirement and its reason instead of
    recounting who requested it. Use roles in reusable guidance and name
    people only when their identity matters. Credit sources with links
    and preserve required provenance.
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

## Plan shape

Use this plan shape on every board created or updated from this guide.
Update existing boards through authorized work in their own projects.

A plan fits one screen, about sixty lines. When it would run longer, the
task is too big: say where it splits and plan the first part.

For a small fix with no unresolved design choice, write only Need,
Acceptance criteria, Steps and Coverage boundary. State the problem,
expected result, change and check. For example:

    ## Need
    Empty input causes an exception instead of a validation response.
    ## Acceptance criteria
    Empty input receives the documented validation response.
    ## Steps
    Fix the input check; the focused empty-input test fails before
    the fix and passes afterwards.
    ## Coverage boundary
    The local handler test runs; the browser path is unverified.

Use the full shape below for work with multiple cases, open decisions or
wider consequences. The full shape always waits for approval; the
small-fix form does only when the task does not qualify under "Plan
before code".

- Need: who needs the change, what they are trying to do and what goes
  wrong today. No solution yet.
- Behaviour: one item per case the change must handle, most important
  first, with the cases the first usable version needs marked. Each gives
  the situation, what happens, the expected result and how a reviewer can
  see it. Include the failure cases, such as bad input or a step that
  stops part way.
- Acceptance criteria: the outcomes the owner will check, each added
  with lattice criterion add and checkable without reading the code.
- Out of scope: what the task leaves alone, and the task that owns it.
- Cut for now: what the project's stage leaves out of this task, one
  line each.
- Assumptions: guesses made instead of asking, one sentence each, so the
  owner can reject any of them.
- Owner decisions: at most three, one per line, each with the
  options and a recommendation, answered when the owner reviews the
  plan.
- Candidates, only when the plan proposes competing versions: which
  reason in the conventions applies, what each one tries and which
  criteria will tell them apart. Drop one that differs only in wording
  or style.
- Approach: the files, commands and dependencies the change touches, and
  how it follows the project's engineering and testing rules. Name any
  departure from them and say why. Where more than one approach would
  work, or the choice is hard to undo, name the one you rejected and
  what it would have cost.
- Steps: in order, the first usable version first. Each names the files
  it touches and the check that shows it worked, with the result
  expected. For a bug fix, prefer a test that fails before the step and
  passes after it.
- Coverage boundary: what local checks will prove, what is mocked, and
  what stays unverified until the owner installs or deploys it.

Before setting the approval flag, read the plan back against itself.
Every behaviour case has a criterion and a step. Every step serves a
case. Every criterion can be checked from outside the code. The plan
uses the task's own terms. No open question sits in Approach or Steps;
it belongs in Assumptions or Decisions.

What a plan holds, and when the task is done, depends on its type:

| Type | The plan holds | Done when |
|---|---|---|
| bug | The reproduction (command and output), the cause with file:line, and the test that fails today | That test passes and the reproduction no longer fails |
| task | The full shape, or the small-fix form | Every criterion has evidence |
| spike | The question, what would decide it and a time box; no code is merged | The findings, a recommendation and what it rests on are on the task |
| chore | What changes, why now and how to undo it | The checks pass and nothing a user sees has changed |

A spike or a chore waits for plan approval like any other task.
```

### 3a. Agent instructions

Sessions read the project's AGENTS.md (or CLAUDE.md) at start and
`context.md` only when they follow a pointer to it. Put the rules that
must hold from the first edit in AGENTS.md as well:

```
## Working a task (every agent)

Tasks are on the owner's Lattice board in .lattice/ (a separate private
repository, ignored by source Git). Read .lattice/context.md before working
a task: it holds the plan-first step, the branch and worktree per task,
the Task: <CODE>-<n> commit trailer, the review flow, and the reply shape
and rules for answering review threads.

- Open the window at this checkout: a session reaches only the folder it
  was opened in, and Git, the board and every task worktree are here.
- Never edit files in this checkout for task work. It stays on <branch>
  for the owner's merges and for board writes.
- Plan before code. Before the first edit to a guardrail file (settings,
  hooks, scripts, agents, commands, rules, instruction files) there is a
  board task with an approved plan, however small the request. For any
  other task that changes behaviour, write the plan to
  the file lattice plan <CODE>-<n> names, set
  lattice needs-human <CODE>-<n> "Need: approve plan" and stop until the
  owner approves it. A small fix on a task the owner selected goes ahead
  without that stop, under the conditions in .lattice/context.md.
- The acceptance criteria are the finish line: work until each has
  evidence or waits on the owner, and when one step is blocked finish
  the others before stopping.
- If source Git metadata is read-only, the owner runs worktree setup and
  source Git writes. Agents edit and test allowed files in the created
  worktree and keep Lattice updated. Give the owner named-path staging
  and commit commands; never widen Git access or use another Git directory
  to bypass a refusal.
- Before the first edit for <CODE>-<n>:
    grep -qxF /.worktrees/ .git/info/exclude || echo /.worktrees/ >> .git/info/exclude
    git worktree add .worktrees/<CODE>-<n> -b feature/<CODE>-<n>-<slug> <branch>
    LATTICE_NO_UPDATE_CHECK=1 lattice branch-link <CODE>-<n> feature/<CODE>-<n>-<slug> --actor agent:<tool>
  Then edit, test and run servers only there, with
  LATTICE_ROOT=<board directory>.
- End every commit for a task with the trailer line Task: <CODE>-<n>, so
  the review section can find it.
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

### 3b. Private board history

Keep the board in its existing `<project>/.lattice/` directory and initialize
that directory as a separate Git repository. Keep .lattice/ ignored by the
source repository. No submodule, symlink or shared checkout is needed.

The owner runs this once, after reviewing the board contents:

```bash
(
  set -euo pipefail
  cd <project>
  test -d .lattice
  test ! -e .lattice/.git
  git check-ignore --quiet .lattice/config.json
  git init --initial-branch=main .lattice
  git -C .lattice status --short
)
```

Keep tasks, events, plans, notes, configuration, archives and sanitized
attachments together. Preserve the board's .gitignore for locks and other
runtime files. Stage named paths and inspect the staged diff before a
requested checkpoint. The owner creates a private remote and checks its
visibility before pushing; source repository visibility is independent.

Set LATTICE_ROOT to the main project checkout, not its .lattice/ directory.
Source task worktrees share that board. Run source Git commands from the
source checkout and board Git commands with git -C <project>/.lattice.
Both repositories stay under the existing project workspace grant; no
additional project access is needed. If protected Git metadata blocks a
necessary step, give the owner its exact command without widening policy.

### 4. Backlog

Capture only items the owner explicitly authorizes. Findings and earlier
session notes are input, not permission to create or start more tasks.
Keep one record per authorized task. `/swe-intake` checks that a report
is real and drafts the task; the owner still authorizes it.

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
- Request, for a bug: what was run, what happened and what was expected.
- Type: `task` for a change, `bug` for broken behaviour, `chore` for
  cleanup, `spike` for research with no change.
- Priority: `high` for exposure or data risk, `medium` for correctness and
  robustness, `low` for cleanup and nice-to-have.
- Tags: areas from `context.md`, two or three at most.
- Criteria: `lattice criterion add <ID> "<observable outcome>"` for each
  thing a reviewer can check. Skip criteria that restate the title. For
  a code change, add one criterion that the project's checks pass on
  the integration branch after the merge; its evidence is the command
  run there and its result.
- Decisions: `lattice needs-human <ID> "Need: <the exact question>"`.
  One question per flag.

Create an onboarding task only if the owner asks for that record. Existing
task records remain private unless the owner asks to share them.

### 4a. The first session

A session new to a project should learn it before it takes a task. Give
the first session this message. It reads and reports, and it creates
only the tasks the message authorizes:

```
Goal: learn this repository well enough that later sessions can take tasks
here, and tell me what most needs doing. This is read-only: change no code,
config or instruction file.

Context: this is the first session in this project. The board in .lattice/
is new and empty. Read .lattice/context.md first; it holds the rules for
tasks.

How to go about it
1. Start broad, then narrow. README and docs, the agent instruction files,
   then the build, test, lint, run and CI setup, then the layout and what
   each main module is for.
2. Then what the layout does not show: the main data models, where outside
   input is validated, how configuration and secrets reach the code (names
   and paths only, never values), and one request or job traced from entry
   to result.
3. Run the project's own checks where they are local and safe (tests, lint,
   type check). Give each command with its result, and say which you did
   not run and why.
4. Read recent history: what changed lately and what looks half finished.
5. Read the files that matter yourself; use a subagent only for a wide
   search. Say nothing about code you have not opened, and mark anything
   you could not confirm.

Report in the reply, short, in this order
- What this is: purpose, stack, how it is built, tested, run and deployed.
- A map: each main folder or module and its job, the traced flow, and a
  glossary of the project's own terms.
- The exact commands for install, test, lint, type check and run, and
  which worked here.
- Gotchas: code that misleads, conventions nobody wrote down, what broke
  when you ran it.
- Findings, ten at most: only what could break, leak, lose data or cost
  money, or what stops an agent working here safely. Rank by impact against
  effort, grade P0 to P3, give file:line and how you confirmed each. Skip
  style.
- What you checked and found sound.
- Text I could add to AGENTS.md: only what the code does not show. And
  three or four one-word tags for the board.

Then on the board. I authorize these and nothing else:
- one task "Map the codebase" with your report attached;
- one backlog task for each confirmed P0 to P2 finding, with acceptance
  criteria and a description in this shape: Request, Scope, Owner,
  Coverage boundary, Remaining: not started.
Start none of them.

Done when: the report is in your reply, the tasks are in backlog, lattice
doctor is clean, and you have listed what you did not look at.
```

The order (broad, then narrow, then one traced flow) and the request for
commands with their results follow the tool makers' guidance:
[Claude Code common workflows](https://code.claude.com/docs/en/common-workflows)
and [best practices](https://code.claude.com/docs/en/best-practices), and
[Codex prompting](https://learn.chatgpt.com/docs/prompting).

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
   `git worktree add .worktrees/<ID> -b feature/<ID>-<slug> <branch>`
   and `LATTICE_NO_UPDATE_CHECK=1 lattice branch-link <ID>
   feature/<ID>-<slug> --actor agent:<tool>`. Edit, test and run
   dev servers only there. Lattice finds the board by walking up from the
   working directory, so the session sets `LATTICE_ROOT=<board
   directory>`. The owner can make the worktree with
   `<agent-alignment>/swe/scripts/task_worktree.sh add <ID> <slug>`,
   adding `--candidates 2` when the approved plan has competing versions.
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
abandoned. Only commits are reviewed: uncommitted work is committed
first. Status, comments,
notes and plans are the dashboard's own controls on the same page;
writes made there carry the owner's actor. The review is bound to the
commit IDs it covered: "Mark done" appears only while the latest review
is an approval of the task's current commits and every thread is
resolved, the approved commits are merged into main and pushed, and
every open acceptance criterion has evidence. The dashboard's status
control refuses `done` under the same rule, and the section says why
otherwise. Merge and push first, then Mark done. After the merge the
task's work is found only through its `Task:` trailers, and earlier
approvals still cover the commits they reviewed, so give every commit
the trailer.

After Mark done, clear the task's worktrees:
`<agent-alignment>/swe/scripts/task_worktree.sh remove <ID>` shows what
it would do and `--apply` does it. It removes merged branches only;
`--drop-unmerged` also discards the candidates that were not picked.

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

Review rules: when you send the same thing back twice, write it down in
a `REVIEW.md` at the top of the project. Give the thing that must stay
true, where a diff hides it, and the safe way to do it. Keep it to what
a formatter or a test cannot catch, and delete a rule that no longer
changes a review. The reviewer agents read that file as it stood before
the change they are reviewing.

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
