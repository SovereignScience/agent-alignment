# CLAUDE.md: agent-alignment (root)

This file is a router. The repository holds two independent toolkits. Do
not work from this folder: `cd` into a track and follow its `CLAUDE.md`.
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
- Push, force-push and `git commit --no-verify` are denied. Never
  amend or rewrite published history; history rewrites are the user's
  to run. Confirm before recursive deletes, dependency removal and CI
  changes. Hooks are best-effort guards; the deny lists, and in
  `swe/` the sandbox, are the boundary.
- No AI attribution anywhere: no AI co-author trailers, no
  "generated with" footers, session links, badges or emoji. Keep human
  co-author trailers. Every commit carries the owner's name and email
  as author and committer: use the identity Git already has and never
  set or override it. If it is missing or names a tool, stop and ask.
  Name branches for the work, never for a tool.
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
- Plan before code. For a task that changes behaviour, write the plan to
  the file `lattice plan AA-<n>` names, set
  `lattice needs-human AA-<n> "Need: approve plan"` and stop until the
  owner approves it.
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
- The board has its own private Git repository at `.lattice/`. Use source
  Git from the task checkout and board Git with `git -C .lattice` from the
  main checkout. Keep `LATTICE_ROOT` at the main checkout; its workspace
  covers both repos.
  Board checkpoints require an explicit request; remote creation and
  pushing remain the owner's.
- End every commit for a task with the trailer line `Task: AA-<n>`, so the
  review section can find it.
- Reviewing a diff or giving a verdict: load `swe/SKEPTIC_ARBITER.md`.
  Answering review threads: use the reply shape and rules in
  `.lattice/context.md`.
- One question per needs_human flag, starting "Need:"; other decisions go
  in the plan, one per line. Clear a flag only when the owner says so,
  quoting the owner's words in the note.
- The comment roles review and plan-review are only for the owner's
  Plannotator results. Agents use validation, or no role.
- At most three workers at once, each in its own task's worktree.
- Write board comments for the owner in plain language: the point first,
  then why, what a thing is before its path, one idea per paragraph, raw
  output attached rather than pasted. The full rule is "Writing on the
  board" in `.lattice/context.md`.
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
- What reaches a cloud session, and the owner's one-time setup, is in
  [swe/README.md](swe/README.md#cloud-sessions).

