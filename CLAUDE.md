# CLAUDE.md: agent-alignment (root)

This is a router. The repository contains two independent
agentic toolkits, each self-contained in its own subtree apart from
the shared `CONTRIBUTING.md`. Do not work from this folder. `cd`
into one of the two tracks and follow the conventions you find
there.

---

## The two tracks

| Track | Folder | Use when |
|---|---|---|
| Track A: agentic software engineering | [`swe/`](swe/) | You are doing software engineering: review, debug, test, refactor, audit, ship. |
| Track B: Inner Commons + Flourishing alignment | [`flourishing/`](flourishing/) | You are authoring, composing, or evaluating alignment prompts. |

Each track has:

- Its own `README.md` (start here)
- Its own `CLAUDE.md` (project conventions)
- Its own `AGENTS.md` (symlink to CLAUDE.md)
- Its own `.claude/` (settings, agents, commands, hooks, status line)
- Its own `scripts/check_drift.sh`
- Its own canonical protocol modules

Once you `cd` into a track's folder, you do not need to reference
this file or anything else outside the track apart from
`CONTRIBUTING.md`.

---

## Why two tracks (briefly)

The repository started as the Inner Commons alignment prompt
library. The maintainer also runs serious agentic-coding workflows
that benefit from the same shape (canonical protocols, specialist
subagents, slash commands, hooks). Folding them into one tree
would have forced agents to disambiguate between alignment-prompt
work and software-engineering work on every turn. The two tracks
are independent in content and infrastructure; only the repo and
the cross-cutting `CONTRIBUTING.md` are shared.

The full rationale lives in [docs/ADR-0001-dual-track.md](docs/ADR-0001-dual-track.md).

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
  "generated with" footers, badges or emoji. Keep human co-author
  trailers.
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

## Top-level layout

```
agent-alignment/
├── README.md                 # router
├── CLAUDE.md                 # this file (router)
├── AGENTS.md                 # symlink to CLAUDE.md
├── CONTRIBUTING.md           # PR rubric (both tracks)
├── .claude/                  # SessionStart hook and status line only
│
├── swe/                      # Track A, SWE
├── flourishing/              # Track B, alignment
│
├── docs/
│   └── ADR-0001-dual-track.md
├── presentations/
└── media/
```

The top-level `.claude/` holds only a SessionStart hook and a status
line. Subagents, slash commands and language hooks live inside the
track subtrees.

---

## Cross-tool agent compatibility

`AGENTS.md` is a symlink to this file. The convention applies to
the subtrees too: `swe/AGENTS.md` points to `swe/CLAUDE.md` and
`flourishing/AGENTS.md` to `flourishing/CLAUDE.md`. The Codex
profile and rules the SWE track ships live in `swe/codex/`.

If you opened the repo root in Claude Code / Codex CLI / Cursor
and you are about to do real work, the right move is to `cd swe/`
or `cd flourishing/` and re-open from there. The track-level
`.claude/` will load automatically and you'll get the right
permissions, hooks, status line, and roster.
