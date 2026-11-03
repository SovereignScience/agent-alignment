# swe — agentic software-engineering toolkit

You are in the SWE track of `agent-alignment`. **Everything you need
is in this folder.** Read this file, then act.

## What this folder gives you

- **Five canonical SWE protocols** ([SWE_CORE.md](SWE_CORE.md),
  [TESTING_PROTOCOL.md](TESTING_PROTOCOL.md),
  [PERFORMANCE_PROTOCOL.md](PERFORMANCE_PROTOCOL.md),
  [SECURITY_PROTOCOL.md](SECURITY_PROTOCOL.md),
  [SKEPTIC_ARBITER.md](SKEPTIC_ARBITER.md)) — drop-in system prompts.
- **Twelve specialist subagents** in [.claude/agents/](.claude/agents/).
- **Fourteen slash commands** in [.claude/commands/](.claude/commands/).
- **Smart hooks** — language-aware post-edit checks (ruff for `.py`,
  eslint+tsc for `.ts/.tsx`, cargo check for `.rs`, gofmt+go vet
  for `.go`, clang-format for C/C++), pre-bash destructive-pattern
  guard, status line.
- **Sane permissions** — pytest, ruff, mypy, npm, eslint, tsc,
  cargo, go, make, docker (read-only), gh PR/issue (read-only), rg.

For full project conventions read [CLAUDE.md](CLAUDE.md).

---

## What to load into your context

Most coding work needs `SWE_CORE.md` + `TESTING_PROTOCOL.md`. Add
others when relevant:

| Working on… | Add this |
|---|---|
| Anything | `SWE_CORE.md` + `TESTING_PROTOCOL.md` |
| Hot path, render loop, large data path | + `PERFORMANCE_PROTOCOL.md` |
| Auth, input handling, deps, anything crossing a trust boundary | + `SECURITY_PROTOCOL.md` |
| Reviewing a diff, signing off, claiming "done" | + `SKEPTIC_ARBITER.md` (or just rely on `code-skeptic`/`code-arbiter`) |

Reading each protocol once is enough. They are small on purpose.

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
| Independent code review | `code-reviewer` | `/swe-review` |
| Failing test for a bug | `regression-test-writer` | `/swe-add-test` |
| Diagnose a failing test | `debugger` | `/swe-debug` |
| Full bug-fix loop | (orchestrator) | `/swe-fix-bug` |
| Security review | `security-reviewer` | `/swe-security` |
| Performance audit | `perf-auditor` | `/swe-perf` |
| Dependency audit | `dependency-auditor` | `/swe-deps` |
| Plan a refactor | `refactoring-planner` | `/swe-refactor` |
| Browser-verify a UI fix | `dashboard-probe` | `/swe-probe` |
| Write ADR / README / runbook | `docs-writer` | `/swe-docs` |
| Anti-sycophancy on a sign-off | `code-skeptic` + `code-arbiter` | `/swe-skeptic` |
| Five-way swarm review | (orchestrator) | `/swe-swarm-review` |
| Install protocols in another repo | (orchestrator) | `/swe-init` |

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
9. **Cite evidence on every approval.** File:line, test name, or
   measurement. No "looks good" without specifics.
10. **Execute with care.** Confirm destructive or shared-state
    actions before running.

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

## Task board and review flow

[LATTICE_ONBOARDING.md](LATTICE_ONBOARDING.md) is an optional owner-run
setup for projects where the user wants a Lattice board and review flow.
[tools/lattice-review/](tools/lattice-review/) holds the review launcher
and the VS Code extension its links open.

---

## Build, verify

| Goal | Command |
|---|---|
| Print canonical protocol hashes | `bash scripts/check_drift.sh` |
| Smoke-test status line | `bash .claude/scripts/statusline.sh` |
| Validate settings JSON | `python3 -c "import json;json.load(open('.claude/settings.json'))"` |
| Lint hook scripts | `for f in .claude/scripts/*.sh scripts/*.sh; do bash -n "$f"; done` |

There is no test suite for these protocols (they're prose). The
SWE protocols are validated by use.

---

## A note on the sibling track

This repository has a sibling subtree at `../flourishing/` for
Inner-Commons + Flourishing alignment-prompt authoring. It is
fully independent. Ignore it unless you've been explicitly directed
there.
