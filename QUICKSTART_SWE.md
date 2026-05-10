# QUICKSTART_SWE.md — for agents doing software engineering

You landed in this repo to do coding work. Read this file, then act.

## What this folder gives you

- **Four canonical SWE protocols** ([SWE_CORE.md](SWE_CORE.md),
  [TESTING_PROTOCOL.md](TESTING_PROTOCOL.md),
  [PERFORMANCE_PROTOCOL.md](PERFORMANCE_PROTOCOL.md),
  [SECURITY_PROTOCOL.md](SECURITY_PROTOCOL.md)) — drop-in system
  prompts you can prepend to any session.
- **Ten SWE subagents** in [.claude/agents/](.claude/agents/) — one
  specialist per common review or authoring task.
- **Ten SWE slash commands** in [.claude/commands/](.claude/commands/)
  — pre-wired multi-step workflows.
- **Smart hooks** — language-aware post-edit checks (ruff for `.py`,
  eslint/tsc for `.ts/.tsx`, etc.), pre-bash destructive-pattern
  guard, dirty-flag aware status line.

The Inner Commons / Flourishing track (Track B in
[README.md](README.md)) is independent. Ignore it unless you are
authoring alignment prompts.

---

## What to load into your context

For most coding work, prepend `SWE_CORE.md` and `TESTING_PROTOCOL.md`
to your session. Add the others when relevant:

| Working on… | Add this |
|---|---|
| Anything | `SWE_CORE.md` + `TESTING_PROTOCOL.md` |
| Hot path, render loop, large data path | + `PERFORMANCE_PROTOCOL.md` |
| Auth, input handling, deps, anything crossing a trust boundary | + `SECURITY_PROTOCOL.md` |

Reading the protocol once is enough. They are small on purpose.

---

## What to do first in a fresh repo

```
/swe-explore
```

This dispatches the `architecture-explorer` subagent to produce a
200-400 word brief: layout, entry points, build / test / lint
commands, conventions, gaps. The brief tells you which protocol to
load and which subagent to spawn next.

---

## Subagent dispatch table (when to spawn which)

| Task | Subagent | Slash command |
|---|---|---|
| Map an unfamiliar repo | `architecture-explorer` | `/swe-explore` |
| Independent review of your branch | `code-reviewer` | `/swe-review` |
| Write the failing test for a bug | `regression-test-writer` | `/swe-add-test` |
| Diagnose a failing test or exception | `debugger` | `/swe-debug` |
| Full bug-fix loop (diagnose → test → review) | (orchestrator) | `/swe-fix-bug` |
| Security review of a diff | `security-reviewer` | `/swe-security` |
| Performance audit of a hot path | `perf-auditor` | `/swe-perf` |
| Audit dependency changes | `dependency-auditor` | `/swe-deps` |
| Plan a refactor before changing code | `refactoring-planner` | `/swe-refactor` |
| Verify a UI fix in a real browser | `dashboard-probe` | `/swe-probe` |
| Write or update an ADR / README / runbook | `docs-writer` | `/swe-docs` |
| Five-way swarm review of the branch | (orchestrator) | `/swe-swarm-review` |
| Install these protocols in another repo | (orchestrator) | `/swe-init` |

Spawn multiple in parallel for cross-cutting changes.

---

## The non-negotiable rules (from `SWE_CORE.md`)

1. **Read first.** README, entry point, closest test, config. Do
   not edit files you have not read.
2. **Fix root causes.** A symptom-patched bug returns.
3. **Delete dead code.** Don't comment out, don't `if (false)`.
4. **One source of truth.** Duplicates are a finding.
5. **No comments explaining WHAT.** Only WHY when non-obvious.
6. **No error handling for impossible cases.** Validate at
   boundaries; trust internally.
7. **Don't design for hypotheticals.** Two real consumers earn an
   abstraction.
8. **Verify before claiming done.** Tests passing ≠ feature works.
9. **Execute with care.** Confirm destructive or shared-state
   actions before running.

---

## What you should NOT do

- Surface the alignment-track agents (`inner-commons-steward`,
  `skeptic`, etc.) for SWE tasks. They are for prompt-authoring
  work. Wrong tool, wasted context.
- Edit the four alignment canonical modules
  (`INNER_COMMONS_CORE.md`, `FLOURISHING_PROTOCOL.md`,
  `SKEPTIC_ARBITER.md`, `REPAIR_PROTOCOL.md`) without explicit user
  ask — those belong to Track B.
- Skip `SWE_CORE.md` to "save context." It's the smallest
  load-bearing thing here.

---

## Bringing this stack into another project

```
/swe-init [target-repo-path]
```

Copies the selected canonical protocols into the target project,
sets up an `AGENTS.md`/`CLAUDE.md` pointer, and recommends a
starting subagent roster sized to the project. The protocols are
copies, not symlinks — the target repo evolves them independently.

---

## Build, verify (this repo)

| Goal | Command |
|---|---|
| Print canonical + derived hashes | `bash scripts/check_drift.sh` |
| Smoke-test status line | `bash .claude/scripts/statusline.sh` |
| Validate settings JSON | `python3 -c "import json;json.load(open('.claude/settings.json'))"` |
| Lint all hook scripts | `for f in .claude/scripts/*.sh scripts/*.sh; do bash -n "$f"; done` |

There is no test suite for these protocols (they're prose). The
SWE protocols are validated by use, not by CI.
