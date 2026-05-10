# CLAUDE.md — agent-alignment (root)

This is a **router**. The repository contains two independent
agentic toolkits, each fully self-contained in its own subtree.
**Do not work from this folder.** `cd` into one of the two tracks
and follow the conventions you find there.

---

## The two tracks

| Track | Folder | Use when |
|---|---|---|
| Track A — agentic software engineering | [`swe/`](swe/) | You are doing software engineering — review, debug, test, refactor, audit, ship. |
| Track B — Inner Commons + Flourishing alignment | [`flourishing/`](flourishing/) | You are authoring, composing, or evaluating alignment prompts. |

Each track has:

- Its own `README.md` (start here)
- Its own `CLAUDE.md` (project conventions)
- Its own `AGENTS.md` (symlink → CLAUDE.md)
- Its own `.claude/` (settings, agents, commands, hooks, status line)
- Its own `scripts/check_drift.sh`
- Its own canonical protocol modules

Once you `cd` into a track's folder, you do not need to reference
this file or anything else outside the track.

---

## Why two tracks (briefly)

The repository started as the **Inner Commons** alignment prompt
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

- **Plain language over jargon.**
- **Operational rules over aspirational language.**
- **Confirm before destructive ops** (`rm -rf`, force-push,
  `--no-verify`).
- **Never add `Co-Authored-By` trailers** on commits.
- **Read [CONTRIBUTING.md](CONTRIBUTING.md)** before opening a PR.
  It has track-specific rubrics.

---

## Top-level layout

```
agent-alignment/
├── README.md                 # router
├── CLAUDE.md                 # this file (router)
├── AGENTS.md                 # symlink → CLAUDE.md
├── CONTRIBUTING.md           # PR rubric (both tracks)
│
├── swe/                      # Track A — fully self-contained
├── flourishing/              # Track B — fully self-contained
│
├── docs/
│   └── ADR-0001-dual-track.md
├── presentations/
└── media/
```

There is no top-level `.claude/`, no top-level subagent or slash-
command roster, no top-level hooks. All agent infrastructure lives
inside the track subtrees.

---

## Cross-tool agent compatibility

`AGENTS.md` is a symlink to this file. The convention applies to
the subtrees too — `swe/AGENTS.md → swe/CLAUDE.md` and
`flourishing/AGENTS.md → flourishing/CLAUDE.md`.

If you opened the repo root in Claude Code / Codex CLI / Cursor
and you are about to do real work, the right move is to `cd swe/`
or `cd flourishing/` and re-open from there. The track-level
`.claude/` will load automatically and you'll get the right
permissions, hooks, status line, and roster.
