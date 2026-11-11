# CLAUDE.md: agent-alignment (root)

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
- Operational rules over aspirational language.
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
  other task that changes behaviour, write the plan to the file
  `lattice plan AA-<n>` names, set
  `lattice needs-human AA-<n> "Need: approve plan"` and stop until the
  owner approves it. A task the owner selected skips that stop, with no
  flag, when its plan fits the small-fix form (Need, Acceptance
  criteria, Steps, Coverage boundary), leaves the owner nothing to
  decide, is easy to revert and touches no guardrail file,
  authentication, permissions, secrets, network access, stored data or
  its format. The plan says which of these it checked. When in doubt it
  is not small. The owner's review of the code is still required before
  a merge.
- If source Git metadata is read-only, the owner runs worktree setup and
  source Git writes. Agents edit and test allowed files in the created
  worktree and keep Lattice updated. Give the owner named-path staging
  and commit commands; never widen Git access or use another Git directory
  to bypass a refusal.
- Before the first edit for AA-<n>, from this checkout:

  ```
  grep -qxF /.worktrees/ .git/info/exclude || echo /.worktrees/ >> .git/info/exclude
  git worktree add .worktrees/AA-<n> -b feature/AA-<n>-<slug> main
  LATTICE_NO_UPDATE_CHECK=1 lattice branch-link AA-<n> feature/AA-<n>-<slug> --actor agent:<tool>
  ```

  Candidate branches for competing versions stay unlinked until the
  owner picks one.
  Then edit, test and run servers only there, with `LATTICE_ROOT` set to
  this checkout.
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

