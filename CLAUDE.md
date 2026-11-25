# CLAUDE.md: agent-alignment (root)

Reading this from a project's `.agent-alignment` clone? This file is for
work on the kit itself. Read the kit from the clone and never write to
it; in a project with no `.lattice/` board, offer the owner "Start here"
in [swe/LATTICE_ONBOARDING.md](swe/LATTICE_ONBOARDING.md) once.

This file is a router. The repository holds two independent toolkits.
Open the window at this folder, the main checkout: a session reaches only
the folder it was opened in, and Git, the board and every task worktree
are here. Then follow the `CLAUDE.md` of the track the work is in. A
window opened in a track folder or a worktree loads that track's
settings, agents and commands but loses Git or the board.
`AGENTS.md` is a symlink to this file, here and in each track.

| Track | Folder | Use when |
|---|---|---|
| Agentic software engineering | [`swe/`](swe/) | Review, debug, test, refactor, audit, ship. |
| Inner Commons + Flourishing alignment | [`flourishing/`](flourishing/) | Author, compose or evaluate alignment prompts. |

The layout is in [README.md](README.md) and the reason for two tracks in
[docs/ADR-0001-dual-track.md](docs/ADR-0001-dual-track.md).

---

## Repo-wide rules (apply to both tracks)

- Plain language over jargon.
- Operational rules over aspirational language: a rule says when it
  applies and what to do then. A limit or a number that a new or
  changed rule sets gives its reason or its source, or says it is a
  guide. A new rule sharpens or replaces an existing line where it can,
  and its plan names what it lets the kit delete.
- Push, force-push and `git commit --no-verify` are denied; the one
  exception for a push is under Cloud sessions below. Never
  amend or rewrite published history; history rewrites are the user's
  to run. Confirm before recursive deletes, dependency removal and CI
  changes. Hooks are best-effort guards; the deny lists, and in
  `swe/` the sandbox, are the boundary.
- No AI attribution anywhere, and every commit under the owner's own
  Git identity: the user rules have both in full, and hooks check them.
- Read [CONTRIBUTING.md](CONTRIBUTING.md) before changing a track.
  It has track-specific rubrics.

---

## Working a task (every agent)

Tasks for this repository are on the owner's Lattice board in `.lattice/`
(kept out of source Git history). Read `.lattice/context.md` before working
a task: it holds the plan-first step, the branch and worktree per task,
the `Task: AA-<n>` commit trailer, the review flow, and the reply shape
and rules for answering review threads.

- Never edit files in this checkout for task work. It stays on main for
  the owner's merges and for board writes.
- Plan before code. Before the first edit to a guardrail file there is a
  board task with an approved plan, however small the request and
  whoever made it. Guardrail files are settings, hooks, scripts, agents,
  commands, rules and instruction files: any CLAUDE.md or AGENTS.md, the
  protocols, anything under .claude/ or codex/, the installers. For any
  other task that changes behaviour, write the plan to the task's plan
  file (`lattice plan AA-<n> --json` gives its path), set
  `lattice needs-human AA-<n> "Need: approve plan"` and stop until the
  owner approves it. A task selected by the owner or a coordinator under
  a direct release mandate skips that stop, with no flag, when its plan
  fits the small-fix form (Need, Acceptance
  criteria, Steps, Coverage boundary), leaves the owner nothing to
  decide, is easy to revert and touches no guardrail file,
  authentication, permissions, secrets, network access, stored data or
  its format. The plan says which of these it checked. When in doubt it
  is not small. The owner's review of the code is still required before
  a merge.
- In a managed local session, the owner creates worktrees and runs
  source Git writes. Use `git worktree list` to find the task worktree
  before editing. If it is missing, give the owner a block for their
  normal terminal before trying any Git write. Replace the sample
  checkout path, task ID and slug with the actual values:

  ```bash
  (
    set -euo pipefail
    trap 'rc=$?; printf "exit=%s\nTASK_WORKTREE_SETUP_END\n" "$rc"; exit "$rc"' EXIT
    cd "$HOME/projects/agent-alignment"
    bash swe/scripts/task_worktree.sh add AA-12 fix-widget --base main
    git -C .worktrees/AA-12 status --short --branch
  )
  ```

  Continue any reads and checks that can run without the worktree.
  Once the worktree exists, verify its path and branch. From this
  checkout with `LATTICE_ROOT` set here, link the branch if needed with
  `LATTICE_NO_UPDATE_CHECK=1 lattice branch-link AA-<n>
  feature/AA-<n>-<slug> --actor agent:<tool>`. Candidate branches stay
  unlinked until the owner picks one. Edit, test and run servers only in
  the task worktree. Give the owner named-path staging and commit
  commands.
- End every commit for a task with the trailer line `Task: AA-<n>`, so the
  review section can find it.
- One question per needs_human flag, starting "Need:"; other decisions go
  in the plan, one per line. Clear a flag only when the owner says so,
  quoting the owner's words in the note.
- At most three workers at once, each in its own task's worktree.
- Write board notes for the owner in plain language, one sentence a line
  with raw output attached; "Writing on the board" in
  `.lattice/context.md` has the rule.
- Never run lattice status <ID> done, lattice complete or lattice next;
  completion is the owner's, through the review section.

---

## Cloud sessions

A cloud session starts from a fresh clone on a hosted machine. The owner's
machine rules are not installed there, and the hooks and deny lists in this
repository are not always loaded.

- If neither `~/.claude/CLAUDE.md` nor `~/.codex/AGENTS.md` exists, read
  `swe/user/CLAUDE.md` before any work and follow it as your user rules.
- Follow every rule as written even when nothing enforces it.
- The owner has no shell there, so a push the owner asks for in that
  session is yours to run, with `bash .claude/scripts/cloud_push.sh`. It
  sends the current task branch and nothing else; `--board` sends the
  board's commits. Never push any other way, and never unasked.
- What reaches a cloud session, and the owner's one-time setup, is in
  [swe/README.md](swe/README.md#cloud-sessions).

