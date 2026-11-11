# agent-alignment

Two independent agentic toolkits in one repository. Pick a track,
`cd` into its folder, and everything you need is there apart from
`CONTRIBUTING.md` at the root.

## Two tracks

### `swe/`: agentic software-engineering toolkit

Drop-in protocols + a subagent and slash-command Claude Code setup
for keeping agentic coding work correct, reversible, verifiable and
minimal. Use when you are doing software engineering: review,
debug, test, refactor, audit, ship.

Start here: [swe/README.md](swe/README.md)
Project conventions: [swe/CLAUDE.md](swe/CLAUDE.md)

### `flourishing/`: Inner Commons + Flourishing alignment library

A four-canonical-module prompt library for sovereign AI agents
that are honest, consent-aware, repair-capable, and oriented
toward human and planetary flourishing. Plus 10 alignment
subagents and 8 slash commands for authoring, composing, and
evaluating those prompts.

Start here: [flourishing/README.md](flourishing/README.md)
Project conventions: [flourishing/CLAUDE.md](flourishing/CLAUDE.md)

---

## Which one are you?

| You are… | `cd` into | Then read |
|---|---|---|
| A SWE agent doing coding work | `swe/` | `swe/README.md` |
| A SWE agent installing these protocols in another repo | `swe/` | `swe/README.md`, then launch Claude Code in `swe/` and run `/swe-init <path-to-other-repo>` |
| Authoring or composing alignment prompts | `flourishing/` | `flourishing/README.md` |
| Just looking at the project structure | (stay) | this file + [docs/ADR-0001-dual-track.md](docs/ADR-0001-dual-track.md) |

Once you `cd` into a track's folder, you do not need to read
anything outside it apart from `CONTRIBUTING.md`. Each track has
its own canonical protocols,
its own `.claude/` (subagents, commands, hooks, settings), its own
status line, its own drift-check script.

---

## Top-level layout

```
agent-alignment/
├── README.md                         # this file (router)
├── CLAUDE.md                         # repo-level conventions (router)
├── AGENTS.md                         # symlink to CLAUDE.md
├── CONTRIBUTING.md                   # PR rubric (both tracks)
├── .claude/                          # SessionStart hook and status line only
│
├── swe/                              # Track A, SWE
│   ├── README.md
│   ├── CLAUDE.md
│   ├── AGENTS.md (symlink to CLAUDE.md)
│   ├── SWE_CORE.md
│   ├── TESTING_PROTOCOL.md
│   ├── PERFORMANCE_PROTOCOL.md
│   ├── SECURITY_PROTOCOL.md
│   ├── SKEPTIC_ARBITER.md
│   ├── codex/                        # Codex profile and rules
│   ├── scripts/check_drift.sh
│   └── .claude/                      # SWE-only settings, agents, commands, scripts
│
├── flourishing/                      # Track B, alignment
│   ├── README.md
│   ├── CLAUDE.md
│   ├── AGENTS.md (symlink to CLAUDE.md)
│   ├── INNER_COMMONS_CORE.md
│   ├── FLOURISHING_PROTOCOL.md
│   ├── SKEPTIC_ARBITER.md
│   ├── REPAIR_PROTOCOL.md
│   ├── COMPOSED_AGENT.md
│   ├── FOR_CLAUDE.md
│   ├── FOR_CHATGPT.md
│   ├── FOR_API.md
│   ├── eval/scenarios/
│   ├── scripts/check_drift.sh
│   └── .claude/                      # alignment-only settings, agents, commands, scripts
│
├── docs/
│   ├── ADR-INDEX.md                  # every decision record, generated
│   └── ADR-0001-dual-track.md        # why two tracks coexist
├── presentations/
└── media/
```

---

## A note on Skeptic-Arbiter

Both tracks ship a `SKEPTIC_ARBITER.md` because each track has its
own anti-sycophancy failure surface:

- `swe/SKEPTIC_ARBITER.md` targets engineering sycophancy:
  hollow approvals, "looks good" without specifics, hedge-burial of
  bugs, completion claims without verification.
- `flourishing/SKEPTIC_ARBITER.md` targets relational
  sycophancy: hollow validation in user-facing replies, pre-agreement
  with the question's framing, sycophancy spirals across turns.

Same Three-Voices pattern (Advocate / Skeptic / Arbiter), different
failure surface. Each is wired into its own track's subagents and
commands; they do not interact.

---

## Source lineage

The `flourishing/` track is based on Patrick Deegan's 2026 essay
*Inner Alignment as a Commons* and extends it with a broader
flourishing and externalities layer for sovereign agent
infrastructure.

The `swe/` track distills industry-wide engineering discipline
(read-before-write, root-cause fixes, failing-test-first, OWASP
top-10, performance budgeting, least privilege) into the same
canonical-module shape used by the alignment track.
