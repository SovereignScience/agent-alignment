# CLAUDE.md — agent-alignment / swe

Project-level conventions for the **agentic software-engineering**
toolkit. Loaded automatically by Claude Code, Codex CLI (via the
`AGENTS.md` symlink), Cursor, and any agent that follows the
AGENTS.md convention.

This file overrides parent `CLAUDE.md`s. If you are doing software
engineering work in this folder, read this first; you do not need
to read anything outside this subtree.

---

## What this folder is

A complete agentic-coding toolkit: five canonical protocols, twelve
specialist subagents, fourteen slash commands, language-aware hooks,
sane permissions. Drop into this folder and you have everything
you need — there is no other folder you must visit.

(There is a sibling track in `../flourishing/` for alignment-prompt
authoring. It is independent. You can ignore it.)

---

## Canonical SWE protocols (source of truth)

| File | Purpose |
|---|---|
| [SWE_CORE.md](SWE_CORE.md) | Read first; root cause; delete dead code; verify before claiming done; execute with care. |
| [TESTING_PROTOCOL.md](TESTING_PROTOCOL.md) | Failing test first for bugs; deterministic; behavior-focused; CI gate ordering. |
| [PERFORMANCE_PROTOCOL.md](PERFORMANCE_PROTOCOL.md) | Measure first; name the budget; tail latency; idle costs nothing. |
| [SECURITY_PROTOCOL.md](SECURITY_PROTOCOL.md) | Trust-boundary discipline; OWASP top-10 quick-check; least privilege; fail closed. |
| [SKEPTIC_ARBITER.md](SKEPTIC_ARBITER.md) | Anti-sycophancy on engineering claims (cite evidence; name severity; no hedge-burial; no unverified completion claims). |

For most coding work, prepend `SWE_CORE.md` and `TESTING_PROTOCOL.md`
to your session. Add `PERFORMANCE_PROTOCOL.md` when touching hot
paths or render loops; add `SECURITY_PROTOCOL.md` when touching any
trust boundary; `SKEPTIC_ARBITER.md` is layered automatically by the
`code-skeptic` / `code-arbiter` subagent pair before any review
sign-off.

---

## Architectural commitments (do not weaken)

These are contracts. A change that weakens any must be rejected
or accompanied by an explicit amendment to this file and the
affected protocol.

1. **Read first** — agents do not edit files they have not read.
2. **Failing test first** for bugs, before any production change.
3. **No symptom patches** — `try/except` around a reproducible bug
   is not a fix.
4. **No dead code** — commented-out, `if (false)`, abandoned helpers.
5. **One source of truth** — duplicates are findings.
6. **Verify before done** — type checks ≠ feature works. Open the
   browser; run the command.
7. **Confirm before destructive ops** — `rm -rf`, force-push,
   `--no-verify`, dependency removal, schema migration, CI changes.
8. **Hooks are deterministic guards.** Do not `--no-verify` past
   them; fix the underlying issue.
9. **Cite evidence on every approval** — file:line, test name, or
   measurement. No "looks good" without specifics.
10. **Never add `Co-Authored-By` trailers** on commits.

---

## Subagent dispatch table (when to spawn which)

| Task | Subagent | Slash command |
|---|---|---|
| Map an unfamiliar repo (first command in any new project) | `architecture-explorer` | `/swe-explore` |
| Independent code review of a diff or branch | `code-reviewer` | `/swe-review` |
| Failing test for a bug, before the fix | `regression-test-writer` | `/swe-add-test` |
| Diagnose a failing test or exception to root cause | `debugger` | `/swe-debug` |
| Full bug-fix loop (diagnose → test → review) | (orchestrator) | `/swe-fix-bug` |
| Security review against OWASP top-10 | `security-reviewer` | `/swe-security` |
| Performance audit against named budgets | `perf-auditor` | `/swe-perf` |
| Audit dependency adds / removes / bumps | `dependency-auditor` | `/swe-deps` |
| Plan a behavior-preserving refactor | `refactoring-planner` | `/swe-refactor` |
| Browser-verify a UI fix (headless Chromium) | `dashboard-probe` | `/swe-probe` |
| Write or update an ADR / README / runbook | `docs-writer` | `/swe-docs` |
| Anti-sycophancy on a draft review verdict | `code-skeptic` + `code-arbiter` | `/swe-skeptic` |
| Five-way swarm review of the branch | (orchestrator) | `/swe-swarm-review` |
| Install these protocols in another repo | (orchestrator) | `/swe-init` |

Spawn multiple in parallel for cross-cutting changes. The
`/swe-swarm-review` command bundles a five-way independent review
(code, security, perf, deps, architecture).

---

## Build, verify

| Goal | Command |
|---|---|
| Print canonical protocol hashes | `bash scripts/check_drift.sh` |
| Smoke-test status line | `bash .claude/scripts/statusline.sh` |
| Validate settings JSON | `python3 -c "import json;json.load(open('.claude/settings.json'))"` |
| Lint hook scripts | `for f in .claude/scripts/*.sh scripts/*.sh; do bash -n "$f"; done` |

There is no test suite for these protocols (they're prose). They
are validated by use.

---

## Repo map (this subtree)

```
swe/
├── README.md                     # quickstart + dispatch table
├── CLAUDE.md                     # this file
├── AGENTS.md                     # symlink → CLAUDE.md
│
├── SWE_CORE.md                   # canonical
├── TESTING_PROTOCOL.md           # canonical
├── PERFORMANCE_PROTOCOL.md       # canonical
├── SECURITY_PROTOCOL.md          # canonical
├── SKEPTIC_ARBITER.md            # canonical (anti-sycophancy)
│
├── scripts/
│   └── check_drift.sh
│
└── .claude/
    ├── settings.json             # SWE-only permissions, hooks, status line
    ├── README.md                 # roster + hook architecture
    ├── agents/                   # 12 specialists
    └── commands/                 # 14 slash commands
```

---

## How to add things

### Add a new SWE protocol
Rare. Promote from a working pattern, not from speculation. Mirror
the existing five (Identity → Operating Principles → When to Surface
→ Anti-patterns → Examples). Update this CLAUDE.md, the README, and
`/swe-init`.

### Add a new SWE subagent
Drop a `.claude/agents/<name>.md` with frontmatter (`name`,
`description`, `tools`, `model`). Body uses the canonical shape:
"Read first" → "Invariants you defend" → "How you work" → "What you
do not do" → "Report back with". Update the dispatch table above.

### Add a new SWE slash command
Drop a `.claude/commands/<name>.md` with frontmatter (`description`,
`argument-hint`, `allowed-tools`). Body is the command prompt.
Multi-step workflows hand off to specialists with explicit
`subagent_type`.

---

## Tone and standards

- Plain language over jargon.
- Operational rules over aspirational language.
- Default to no comments; protocols speak for themselves.
- Examples carry nuance that would otherwise bloat the main prompt.
- Confirm before destructive ops (`rm -rf`, force-push,
  `--no-verify`).
- Never add `Co-Authored-By` trailers on commits.

---

## Cross-tool agent compatibility

`AGENTS.md` is a symlink to this file. Agent-specific config lives
in `.claude/`. The instructions in this file apply to **all** agents
that drop into this subtree.

When in doubt: read this file, read `README.md`, read the relevant
canonical protocol, then act.
