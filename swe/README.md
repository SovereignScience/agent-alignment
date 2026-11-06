# swe: agentic software-engineering toolkit

You are in the SWE track of `agent-alignment`. Everything you need
is in this folder apart from `CONTRIBUTING.md` at the root. Read
this file, then act.

## What this folder gives you

- Five canonical SWE protocols ([SWE_CORE.md](SWE_CORE.md),
  [TESTING_PROTOCOL.md](TESTING_PROTOCOL.md),
  [PERFORMANCE_PROTOCOL.md](PERFORMANCE_PROTOCOL.md),
  [SECURITY_PROTOCOL.md](SECURITY_PROTOCOL.md),
  [SKEPTIC_ARBITER.md](SKEPTIC_ARBITER.md)): drop-in system prompts.
- A user-level rules template in [user/CLAUDE.md](user/CLAUDE.md): copy it to
  ~/.claude/CLAUDE.md and ~/.codex/AGENTS.md.
- Thirteen specialist subagents in [.claude/agents/](.claude/agents/).
- Fourteen slash commands in [.claude/commands/](.claude/commands/).
- Hooks in [.claude/scripts/](.claude/scripts/): `guard_outward.py`
  runs on PreToolUse for Bash and MCP tools and denies outward
  actions and secret reads; `tells_check.py` runs on PostToolUse for
  Write and Edit; `session_start.sh` prints the branch, the protocol
  hashes and the agent and command roster; `after_summary.sh` runs on
  SessionStart for compact, resume and fork; `post_edit_verify.sh`
  runs available file checks (ruff and mypy for `.py`, eslint for
  `.js/.ts/.tsx`, gofmt for `.go`, clang-format for C/C++, and a
  checkpoint reminder for `.rs` and `.go`) when they are installed
  and does nothing when they are absent. Plus a status line.
- Permissions: the allow list runs interpreters and build tools
  (pytest, ruff, mypy, npm, eslint, tsc, cargo, go, make, docker, gh
  reads, rg). The deny list and the sandbox are the boundary:
  outward actions and secret reads are denied.

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
| Reviewing a diff, signing off, claiming "done" | + `SKEPTIC_ARBITER.md` (or run `/swe-skeptic`) |

Reading each protocol once is enough. They are small on purpose.

---

## Optional orientation in a fresh repo

```
/swe-explore
```

Invoke this only when you want the `architecture-explorer` brief:
layout, entry points, build / test / lint commands, conventions and
gaps. Otherwise read the repository directly within the task scope.

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
| Update a README or runbook | `docs-writer` | `/swe-docs` |
| Web research without local file or shell access | `web-researcher` | (none) |
| Anti-sycophancy review of a change | `code-skeptic` + `code-arbiter` | `/swe-skeptic` |
| Five-specialist review | (orchestrator) | `/swe-swarm-review` |
| Install the protocols in another repo | (orchestrator) | `/swe-init` |

Use subagents to keep research out of the main context, at most
three at once. Run review and audit agents only when the user asks.

---

## The non-negotiable rules (from `SWE_CORE.md`)

1. Read first. README, entry point, closest test, config. Do
   not edit files you have not read.
2. Fix root causes. A symptom-patched bug returns.
3. Delete dead code. Don't comment out, don't `if (false)`.
4. One source of truth. Duplicates are a finding.
5. No comments explaining WHAT. Only WHY when non-obvious.
6. No error handling for impossible cases. Validate at
   boundaries; trust internally.
7. Don't design for hypotheticals. Two real consumers earn an
   abstraction.
8. Verify before claiming done. Tests passing ≠ feature works.
9. Cite evidence on every approval. File:line, test name, or
   measurement. No "looks good" without specifics.
10. Execute with care. Local reversible actions: take freely.
    Confirm destructive local actions first. Anything that leaves
    the machine or changes a live system: prepare it and ask; the
    user runs it.

---

## Bringing this stack into another project

```
/swe-init [target-repo-path]
```

Copies the five canonical protocols, including `SKEPTIC_ARBITER.md`,
into the target project and nothing else. The protocols are copies,
not symlinks; the target repo evolves them independently. Agents,
commands, scripts and settings are copied by hand from `.claude/`
if you want them there. The scripts and commands default to `main`
as the base branch.

---

## Task board and review flow

[LATTICE_ONBOARDING.md](LATTICE_ONBOARDING.md) is an optional owner-run
setup for projects where the user wants a Lattice board and review flow.
[tools/lattice-review/](tools/lattice-review/) holds the server that adds
a review section to the Lattice dashboard, and the dashboard patch it needs.

---

## Build, verify

| Goal | Command |
|---|---|
| Print canonical protocol hashes | `bash scripts/check_drift.sh` |
| Smoke-test status line | `bash .claude/scripts/statusline.sh` |
| Validate settings JSON | `python3 -c "import json;json.load(open('.claude/settings.json'))"` |
| Test the guard's WebFetch check | `python3 -m unittest discover -s .claude/scripts -p 'test_*.py'` |
| Test the installer and the probe | `python3 -m unittest discover -s scripts -p 'test_*.py'` |
| Preview, then install, the managed layer | `bash scripts/install_isolation.sh`, then `--apply` |
| Check the boundary from inside the sandbox | `bash scripts/check_isolation.sh --client claude` (or `codex`) |
| Lint hook scripts | `for f in .claude/scripts/*.sh scripts/*.sh; do bash -n "$f"; done; python3 -m py_compile .claude/scripts/*.py .claude/scripts/pre-push` |

There is no test suite for these protocols (they're prose). The
SWE protocols are validated by use.

---

## A note on the sibling track

This repository has a sibling subtree at `../flourishing/` for
Inner-Commons + Flourishing alignment-prompt authoring. It is
independent. Ignore it unless you've been explicitly directed
there.
