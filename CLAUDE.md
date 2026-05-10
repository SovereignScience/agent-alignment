# CLAUDE.md — agent-alignment

Project-level engineering guidelines. Loaded automatically by
Claude Code, Codex CLI (via `AGENTS.md` symlink), Cursor, and any
agent that follows the AGENTS.md convention.

This file overrides parent `CLAUDE.md`s. Read it before acting on
any non-trivial change.

---

## What this project is — two tracks, one repo

This repo ships **two independent stacks** of canonical protocols
plus a shared `.claude/` agent infrastructure that serves both.

### Track A — agentic software engineering (primary)

Drop-in protocols + a 10-subagent / 10-command toolkit for keeping
agentic coding work *correct, reversible, verifiable, minimal.*
Use when you are doing software engineering — review, debug, test,
refactor, audit, ship.

### Track B — Inner Commons + Flourishing (alignment prompt library)

A four-module prompt stack for sovereign AI agents that are honest,
consent-aware, repair-capable, and oriented toward human and
planetary flourishing. Use when you are authoring or composing
alignment prompts.

**The two tracks are independent. A SWE agent ignores Track B; an
alignment-prompt author ignores Track A.** Quickstarts route you:

- [QUICKSTART_SWE.md](QUICKSTART_SWE.md) — Track A onboarding (30s)
- [QUICKSTART_FLOURISHING.md](QUICKSTART_FLOURISHING.md) — Track B onboarding (30s)
- [docs/ADR-0001-dual-track.md](docs/ADR-0001-dual-track.md) — why both coexist

---

## Track A — SWE conventions

### Canonical protocols (source of truth)

1. [SWE_CORE.md](SWE_CORE.md) — read first; root-cause; delete
   dead code; one source of truth; verify before claiming done;
   execute with care.
2. [TESTING_PROTOCOL.md](TESTING_PROTOCOL.md) — failing test first
   for bugs; deterministic; behavior-focused; CI gate ordering.
3. [PERFORMANCE_PROTOCOL.md](PERFORMANCE_PROTOCOL.md) — measure
   first; name the budget; tail latency; idle costs nothing.
4. [SECURITY_PROTOCOL.md](SECURITY_PROTOCOL.md) — trust-boundary
   discipline; OWASP top-10 quick-check; least privilege; fail
   closed.

### SWE non-regressions (do not weaken)

- **Read first** — agents do not edit files they have not read.
- **Failing test first** for bugs, before any production change.
- **No symptom patches** — `try/except` around a reproducible bug
  is not a fix.
- **No dead code** — commented-out, `if (false)`, abandoned helpers.
- **One source of truth** — duplicates are findings.
- **Verify before done** — type checks ≠ feature works. Open the
  browser; run the command.
- **Confirm before destructive ops** — `rm -rf`, force-push,
  `--no-verify`, dependency removal, schema migration, CI changes.
- **Hooks are deterministic guards.** Do not `--no-verify` past
  them; fix the underlying issue.
- **Never add `Co-Authored-By` trailers** on commits.

### SWE dispatch table

| Task | Subagent | Slash command |
|---|---|---|
| Map an unfamiliar repo | `architecture-explorer` | `/swe-explore` |
| Independent code review | `code-reviewer` | `/swe-review` |
| Failing test for a bug | `regression-test-writer` | `/swe-add-test` |
| Diagnose to root cause | `debugger` | `/swe-debug` |
| Full bug-fix loop | (orchestrator) | `/swe-fix-bug` |
| Security review | `security-reviewer` | `/swe-security` |
| Perf audit | `perf-auditor` | `/swe-perf` |
| Dependency audit | `dependency-auditor` | `/swe-deps` |
| Plan a refactor | `refactoring-planner` | `/swe-refactor` |
| Browser-verify a UI fix | `dashboard-probe` | `/swe-probe` |
| Write ADR / README / runbook | `docs-writer` | `/swe-docs` |
| Five-way swarm review | (orchestrator) | `/swe-swarm-review` |
| Install protocols in another repo | (orchestrator) | `/swe-init` |

Spawn multiple in parallel for cross-cutting changes. The
`/swe-swarm-review` command bundles a five-way independent review.

---

## Track B — alignment prompt-authoring conventions

### Canonical alignment modules (source of truth)

1. [INNER_COMMONS_CORE.md](INNER_COMMONS_CORE.md) — relational
   layer (TRUST / CONSENT / ATTENTION / REPAIR CAPACITY).
2. [FLOURISHING_PROTOCOL.md](FLOURISHING_PROTOCOL.md) — externalities
   + planetary stewardship.
3. [SKEPTIC_ARBITER.md](SKEPTIC_ARBITER.md) — anti-sycophancy
   internal deliberation.
4. [REPAIR_PROTOCOL.md](REPAIR_PROTOCOL.md) — rupture detection +
   six-step repair sequence.

### Alignment derived files

| File | Form |
|---|---|
| [COMPOSED_AGENT.md](COMPOSED_AGENT.md) | All four modules in one drop-in. |
| [FOR_CLAUDE.md](FOR_CLAUDE.md) | XML-tagged + abbreviated User-Preferences variant. |
| [FOR_CHATGPT.md](FOR_CHATGPT.md) | ChatGPT system-prompt. |
| [FOR_API.md](FOR_API.md) | API system-prompt + composition guidance. |

### Alignment non-regressions (do not weaken)

1. **Canonical-derived split.** Four canonical modules are the
   source of truth; five derived files mirror them.
2. **The four commons resources are TRUST, CONSENT, ATTENTION,
   REPAIR CAPACITY.** No new resources without removing redundancy.
3. **Operating principles stay numbered and atomic.**
4. **Stewardship targets stay enumerated** (HUMAN DIGNITY, AGENCY,
   FAIRNESS, CIVIC TRUST, LIVING SYSTEMS, FUTURE OPTION VALUE).
5. **Skeptic + Arbiter run as internal deliberation.** Never
   surface to the user.
6. **The repair sequence is six steps.** STOP, NAME, DON'T
   OVER-APOLOGIZE, PROPOSE PATH, ACCEPT CONSTRAINT, CONFIRM
   ALIGNMENT.
7. **Low-stakes tasks must stay invisible.** Every "When to
   Surface" rule is non-optional.
8. **Provider variants stay in sync.** Substantive content drift
   is a bug.
9. **Concrete failure mode required** for every prompt change —
   see [CONTRIBUTING.md](CONTRIBUTING.md).
10. **No moralizing tone.** Engineering, not sermon.

### Alignment dispatch table

| Task | Subagent | Slash command |
|---|---|---|
| Edit `INNER_COMMONS_CORE.md` | `inner-commons-steward` | (manual) |
| Edit `FLOURISHING_PROTOCOL.md` | `flourishing-auditor` | (manual) |
| Edit `REPAIR_PROTOCOL.md` | `repair-coach` (author mode) | (manual) |
| Audit a request for externalities | `flourishing-auditor` (auditor mode) | `/align-flourishing-check` |
| Anti-sycophancy on a draft | `skeptic` + `arbiter` | `/align-skeptic` |
| Draft a repair response | `repair-coach` (coach mode) | `/align-repair` |
| Propagate canonical to derived | `module-composer` | `/align-compose` |
| Confirm canonical / derived in sync | `drift-checker` | `/align-drift-check` |
| Score against eval scenarios | `scenario-evaluator` | `/align-scenario` |
| Line-level prose polish | `prose-editor` | (manual) |
| Independent rubric review | `pr-rubric-reviewer` | (manual) |
| Add a new canonical module (rare) | (orchestrator) | `/align-add-module` |
| Five-way swarm review | (orchestrator) | `/align-swarm-review` |

---

## Build, verify (both tracks)

| Goal | Command |
|---|---|
| Print canonical + derived hashes | `bash scripts/check_drift.sh` |
| Smoke-test status line | `bash .claude/scripts/statusline.sh` |
| Validate settings JSON | `python3 -c "import json;json.load(open('.claude/settings.json'))"` |
| Lint all hook scripts | `for f in .claude/scripts/*.sh scripts/*.sh; do bash -n "$f"; done` |

There is no test suite for the protocols (they're prose).
Track A protocols are validated by use; Track B protocols are
validated by `scenario-evaluator` against `eval/scenarios/*.md`.

---

## Repo map

```
.
├── README.md                         # router (two tracks)
├── CLAUDE.md                         # this file
├── AGENTS.md                         # symlink → CLAUDE.md
├── QUICKSTART_SWE.md                 # Track A onboarding
├── QUICKSTART_FLOURISHING.md         # Track B onboarding
├── CONTRIBUTING.md                   # PR rubric (both tracks)
│
├── SWE_CORE.md                       # Track A canonical
├── TESTING_PROTOCOL.md               # Track A canonical
├── PERFORMANCE_PROTOCOL.md           # Track A canonical
├── SECURITY_PROTOCOL.md              # Track A canonical
│
├── INNER_COMMONS_CORE.md             # Track B canonical
├── FLOURISHING_PROTOCOL.md           # Track B canonical
├── SKEPTIC_ARBITER.md                # Track B canonical
├── REPAIR_PROTOCOL.md                # Track B canonical
├── COMPOSED_AGENT.md                 # Track B derived
├── FOR_CLAUDE.md                     # Track B derived
├── FOR_CHATGPT.md                    # Track B derived
├── FOR_API.md                        # Track B derived
│
├── docs/
│   └── ADR-0001-dual-track.md        # why two tracks
├── eval/
│   └── scenarios/                    # Track B behavioral specs
├── scripts/
│   └── check_drift.sh
├── presentations/                    # companion materials
├── media/                            # images / diagrams
│
└── .claude/
    ├── settings.json
    ├── README.md
    ├── agents/                       # 20 specialists (10 SWE + 10 alignment)
    ├── commands/                     # 18 commands (10 SWE + 8 alignment)
    └── scripts/                      # SessionStart / pre-bash / post-edit / statusline
```

---

## How to add things

### Add a new SWE protocol
Rare. Promote it from a working pattern, not from speculation. New
file `<NAME>_PROTOCOL.md` mirroring the existing four (Identity ·
Operating Principles · When to Surface · Anti-patterns ·
Examples). Update README, CLAUDE.md, and `/swe-init`.

### Add a new SWE subagent
Drop a `.claude/agents/<name>.md` with frontmatter (`name`,
`description`, `tools`, `model`). Body becomes the system prompt:
"Read first" → "Invariants you defend" → "How you work" → "What you
do not do" → "Report back with". Update the SWE dispatch table
above.

### Add a new alignment canonical module
Use `/align-add-module <NAME>` — gates on the failure-mode question
and scaffolds the module + derived sections.

### Add a new evaluation case (Track B)
New file at `eval/scenarios/NN_<short_name>.md`. Sections: User
input · Failure modes to catch · Expected behavior · Pass criteria.
Picked up automatically by `scenario-evaluator`.

### Add a new provider variant (Track B)
1. Update `.claude/settings.json` `ALIGN_PROVIDER_VARIANTS`.
2. Add the file to `scripts/check_drift.sh`'s derived list.
3. Update `module-composer.md`'s derived-file table.
4. Update this CLAUDE.md's repo map.

---

## Tone and standards (both tracks)

- Plain language over jargon.
- Operational rules over aspirational language.
- Default to no comments; prose modules speak for themselves.
- Examples carry nuance that would otherwise bloat the main prompt.
- Confirm before destructive ops (`rm -rf`, force-push,
  `--no-verify`).
- Never add `Co-Authored-By` trailers on commits.

---

## Cross-tool agent compatibility

This project supports Claude Code, Codex CLI, Cursor, and any agent
that follows the AGENTS.md convention. `AGENTS.md` is a symlink to
this file. Agent-specific config lives in `.claude/`. The
instructions in this file apply to **all** agents.

When in doubt: read this file, read the relevant QUICKSTART, read
the affected canonical module, then act.
