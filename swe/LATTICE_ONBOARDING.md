# Lattice onboarding

Optional setup for an owner who wants a project board and review flow.
Do not initialize a board, install tools or create backlog items as a side
effect of another task. Words in angle brackets are placeholders.

## What you end up with

- A `.lattice/` board in the project root, left uncommitted until the
  owner asks for it.
- A backlog with one task per open item, acceptance criteria on the ones
  that can be checked, and decisions flagged `needs_human`.
- The review launcher ([tools/lattice-review/](tools/lattice-review/))
  running beside the Lattice dashboard, so the owner clicks a task and
  lands in Plannotator or the VS Code multi-diff.
- Reviews recorded on the task as comments, the owner moving tasks to
  done, and the owner pushing.

## Who does what

The owner initializes the board and selects or authorizes its tasks.
The agent resumes only the selected task and leaves prepared work in
`in_review`; it commits only when asked. The owner installs tools, runs
the launcher, reads diffs, completes tasks, pushes and deploys. Agents never run `lattice next`, `lattice complete`
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

The launcher runs the binary itself, so no agent plugin is needed and the
editor extension for Claude Code is enough; the interactive CLI never has
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

The VS Code extension, from a terminal inside the remote where the
repositories live (WSL, SSH), so it installs into that extension host:

```
code --install-extension <agent-alignment>/swe/tools/lattice-review/lattice-review-links-0.1.0.vsix
```

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
| `dashboard_port` | next free port | one port per board; the launcher runs on the port above it (`--port`) |

Keep a line in `context.md` naming the two ports.

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
- Commits for a task end with a trailer line `Task: <CODE>-<n>` so the
  review launcher can find them. Branch work is linked with lattice
  branch-link.
- The task record holds the request, scope, acceptance criteria, owner,
  revision, coverage boundary, evidence and remaining work. Never secrets.
- Review flow: the owner runs the review launcher (port <p+1>) beside the
  dashboard (port <p>), opens a task's commits in Plannotator or the VS
  Code multi-diff, and the review lands on the task as a comment. Done is
  not deployed.
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

1. `lattice show <ID>` to resume. `lattice status <ID> in_progress --no-auto-review`.
2. When asked to commit, use the project's convention and end with a
   blank line and `Task: <ID>`. Several IDs: `Task: <ID>, <ID>`.
3. Branch work: `lattice branch-link <ID> <branch>`.
4. Before handing over: a comment with the checks run, their results,
   what was mocked, what never ran, and what remains for the owner.
   `lattice attach <ID> <file or URL> --title "<what it is>"` for
   evidence files.
5. `lattice status <ID> in_review --no-auto-review`. Stop there.

### 6. The review flow, by the owner

From a VS Code integrated terminal in the project:

```
python3 <agent-alignment>/swe/tools/lattice-review/lattice_review.py --with-dashboard --actor human:<name> --port <p+1>
```

Open http://127.0.0.1:<p+1>. Each task row shows where its work is and two
buttons. Plannotator opens the browser review of the task's exact commit
range; Send Feedback or Approve there, and the decision with the review
text lands on the task as a comment with role `review`. When the range
ends at the checked-out HEAD, the task page also offers the live tree,
which allows staging from the review. VS Code opens the same range in
the multi-diff editor through the extension. On the task page:
per-commit and per-file links, add a comment, move the status, or "Mark
done" with the recorded review. The review is bound to the commit IDs it
covered; if the task's work moves on after the review, the page says so
and offers no completion until a new review. Then push.

Feedback that needs more work: set the task back to `in_progress` and
give the agent the task ID; it reads the comment with `lattice show`.

### 7. Reporting

When the board is set up, the reply to the owner lists: the init command
used, the ports, the number of tasks and which carry `needs_human`, what
the owner must install or run, and what is unverified (Plannotator, the
extension and the browser flow are unverified until the owner has used
them once).

## Keeping this file current

This file is the template. When a project onboarding changes the way the
board, launcher or review flow is used, change this file in the same
piece of work and say so in the task comment. Project-specific details
belong in that project's `context.md`, never here.
