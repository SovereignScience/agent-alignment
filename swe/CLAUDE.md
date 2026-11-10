# CLAUDE.md: agent-alignment / swe

Conventions for the agentic software-engineering toolkit: five canonical
protocols, specialist subagents, slash commands and hooks. This file is
loaded after the root `CLAUDE.md`, whose rules apply here too.
`AGENTS.md` is a symlink to this file; the Codex profile and rules are in
`codex/`. The sibling track in `../flourishing/` is independent.

## Canonical SWE protocols (source of truth)

| File | Purpose |
|---|---|
| [SWE_CORE.md](SWE_CORE.md) | Read first; root cause; delete dead code; verify before claiming done; execute with care; ship the smallest useful version; rigour where mistakes cost. |
| [TESTING_PROTOCOL.md](TESTING_PROTOCOL.md) | Reproduce bugs with a focused test; smallest useful check; deterministic; check ordering. |
| [PERFORMANCE_PROTOCOL.md](PERFORMANCE_PROTOCOL.md) | Measure first; name the budget; tail latency; idle costs nothing. |
| [SECURITY_PROTOCOL.md](SECURITY_PROTOCOL.md) | Trust-boundary discipline; OWASP top-10 quick-check; least privilege; fail closed. |
| [SKEPTIC_ARBITER.md](SKEPTIC_ARBITER.md) | Anti-sycophancy on engineering claims (cite evidence; name severity; no hedge-burial; no unverified completion claims). |

For most coding work, prepend `SWE_CORE.md` and `TESTING_PROTOCOL.md`
to your session. Add `PERFORMANCE_PROTOCOL.md` when touching hot
paths or render loops; add `SECURITY_PROTOCOL.md` when touching any
trust boundary; add `SKEPTIC_ARBITER.md` before a review verdict or
sign-off. `/swe-skeptic` runs the code-skeptic and code-arbiter pair
when the user asks.

[CRAFT.md](CRAFT.md) is a reference, read when the work is to build,
review or design something that will last: what adequate and excellent
look like, and the measures a reviewer can count.

## Architectural commitments (do not weaken)

These are contracts. A change that weakens any must be rejected
or accompanied by an explicit amendment to this file and the
affected protocol.

1. Read first: agents do not edit files they have not read.
2. Reproduce bugs; prefer a focused failing regression where practical.
3. No symptom patches: `try/except` around a reproducible bug
   is not a fix.
4. No dead code: commented-out, `if (false)`, abandoned helpers.
5. One source of truth: duplicates are findings.
6. Verify before claiming done: type checks are not feature checks;
   open the browser, run the command. Reuse valid evidence and state
   material paths that were not exercised.
7. Push, force-push and `--no-verify` are denied, apart from the cloud
   session push in the root guide. Never amend or
   rewrite published history. Confirm before recursive deletes, local
   history rewrites, dependency removal, schema migrations and CI
   changes.
8. Hooks are best-effort guards; the sandbox and the deny list are
   the boundary. Do not work around either; fix the underlying
   issue.
9. Cite evidence on every approval: file:line, test name, or
   measurement. No "looks good" without specifics.

## Subagent dispatch table (when to spawn which)

| Task | Subagent | Slash command |
|---|---|---|
| Map an unfamiliar repo when requested | `architecture-explorer` | `/swe-explore` |
| Independent code review of a diff or branch | `code-reviewer` | `/swe-review` |
| Failing test for a bug, before the fix | `regression-test-writer` | `/swe-add-test` |
| Diagnose a failing test or exception to root cause | `debugger` | `/swe-debug` |
| Full bug-fix loop (diagnose, test, then offer review) | (orchestrator) | `/swe-fix-bug` |
| Security review against OWASP top-10 | `security-reviewer` | `/swe-security` |
| Performance audit against the repository's budgets | `perf-auditor` | `/swe-perf` |
| Audit dependency adds / removes / bumps | `dependency-auditor` | `/swe-deps` |
| Plan a behavior-preserving refactor | `refactoring-planner` | `/swe-refactor` |
| Browser-verify a UI fix (headless Chromium) | `dashboard-probe` | `/swe-probe` |
| Update a README or runbook; write an ADR the user names | `docs-writer` | `/swe-docs` |
| Web research without local file or shell access | `web-researcher` | (none) |
| Anti-sycophancy review of a change | `code-skeptic` + `code-arbiter` | `/swe-skeptic` |
| Five-specialist review of the branch | (orchestrator) | `/swe-swarm-review` |
| Check a reported issue is real, then draft its task | `debugger` | `/swe-intake` |
| Compare candidate versions of one task | `code-reviewer` | `/swe-compare` |
| Install the five protocols in another repo | (orchestrator) | `/swe-init` |

Codex has no slash commands: open the command's file in
`.claude/commands/` and follow it.

Use subagents to keep research out of the main context, a few at a
time and at most three at once. Run the review and audit agents only
when the user asks. `/swe-swarm-review` runs five independent reviews
(code, security, perf, deps, architecture), three at a time.

## Build, verify

| Goal | Command |
|---|---|
| Print canonical protocol hashes | `bash scripts/check_drift.sh` |
| Smoke-test status line | `bash .claude/scripts/statusline.sh` |
| Validate settings JSON | `python3 -c "import json;json.load(open('.claude/settings.json'))"` |
| Lint hook scripts | `for f in .claude/scripts/*.sh scripts/*.sh; do bash -n "$f"; done; python3 -m py_compile .claude/scripts/*.py .claude/scripts/pre-push` |

The protocols are prose and are validated by use. The hooks, scripts and
review tool have tests beside them: `python3 -m unittest discover -s <folder> -p 'test_*.py'`.

## Adding things

A new protocol is rare: promote it from a working pattern, mirror the
existing five (Identity, Operating principles, When to surface,
Anti-patterns, Examples) and update this file, the README and `/swe-init`.
Agents and commands: see [.claude/README.md](.claude/README.md), and add
the row to the dispatch table above. In a protocol, an example carries
nuance that would otherwise bloat the rule.
