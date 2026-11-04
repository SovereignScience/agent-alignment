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
- Push, force-push and `--no-verify` are denied. Never amend or
  rewrite published history. Confirm before recursive deletes, local
  history rewrites, dependency removal and CI changes. Hooks are
  best-effort guards; the deny lists, and in `swe/` the sandbox, are
  the boundary.
- No AI attribution anywhere: no AI co-author trailers, no
  "generated with" footers, badges or emoji. Keep human co-author
  trailers.
- Read [CONTRIBUTING.md](CONTRIBUTING.md) before changing a track.
  It has track-specific rubrics.

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
