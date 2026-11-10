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
  ~/.claude/CLAUDE.md and ~/.codex/AGENTS.md, and keep both copies in step with
  it.
- A review request template in [REVIEW_REQUEST.md](REVIEW_REQUEST.md), for
  handing a change to an independent reviewer.
- Craft rubrics in [CRAFT.md](CRAFT.md): what adequate and excellent work
  look like when building, reviewing and designing. A reference read on
  demand, not a sixth protocol.
- Thirteen specialist subagents in [.claude/agents/](.claude/agents/).
- Sixteen slash commands in [.claude/commands/](.claude/commands/).
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
| A design choice, a review, or a change with more than one way to build it | + the part of `CRAFT.md` for that job |

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
| Check a reported issue is real, then draft its task | `debugger` | `/swe-intake` |
| Compare candidate versions of one task | `code-reviewer` | `/swe-compare` |
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
    Confirm destructive local actions first. Use approved services for
    task-relevant reads. Remote writes and administration: prepare them;
    the user runs them. Never disclose secrets or send private project
    data to unrelated destinations.
11. Ship the smallest useful version. Build what the user needs
    end to end, simply and properly, then stop.
12. Spend rigour where mistakes cost. Full care for security,
    data, money, production and anything hard to undo.

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
| Test the installer, the probe and the worktree script | `python3 -m unittest discover -s scripts -p 'test_*.py'` |
| Make or clear a task's worktrees (owner-run) | `bash scripts/task_worktree.sh add <ID> <slug>`, then `remove <ID>` |
| Preview, then install, the managed layer | `bash scripts/install_isolation.sh`, then `--apply` |
| Check the boundary from inside the sandbox | `bash scripts/check_isolation.sh --client claude` (or `codex`) |
| Try this checkout's rules on this machine, then go back | `bash scripts/switch_rules.sh status`, then `apply`, later `revert` |
| Install the headless browser for screenshots (remove with `apt remove`) | `sudo apt install chromium-headless-shell` |
| Lint hook scripts | `for f in .claude/scripts/*.sh scripts/*.sh; do bash -n "$f"; done; python3 -m py_compile .claude/scripts/*.py .claude/scripts/pre-push` |

There is no test suite for these protocols (they're prose). The
SWE protocols are validated by use.

---

## Trying a checkout and going back

A branch changes three kinds of file, and each reaches a session a
different way.

| What | Where it lives | How a session gets it |
|---|---|---|
| Agents, commands, protocols, project instructions | the checkout | Open the session in a worktree of that branch |
| Managed settings and hooks, the Codex profile, your user rules, the pre-push hook | this machine | `scripts/switch_rules.sh apply` |
| Board conventions | `.lattice/context.md` | `apply --context <file>` |

From a worktree of the branch you want to try:

```bash
bash swe/scripts/switch_rules.sh status   # what would change; writes nothing
bash swe/scripts/switch_rules.sh apply    # saves what is installed, then installs
# restart every Claude Code and Codex session, then test
bash swe/scripts/switch_rules.sh revert   # puts the saved state back
```

A session may run `status` and explain the result. `apply` and `revert`
are yours: they use sudo and change the rules every session runs under.
Each `apply` keeps a snapshot in `~/.config/agent-alignment/snapshots/`,
a folder sessions cannot read or write. `revert` takes the latest, or
the one you name, so two sets of rules can be compared by switching
between them.

---

## sources

The planning guidance draws on [GitHub Spec Kit](https://github.com/github/spec-kit)
for user cases and acceptance checks, and
[Anthropic's guidance on long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
for completing one feature through an end-to-end check. The shared plan
shape combines those practices with this toolkit's approval and testing
rules. Keep source links and required provenance when adapting guidance.

---

## Cloud sessions

A cloud session runs on a fresh clone on a hosted machine, so nothing
installed on your own machine reaches it: the layer under
`/etc/claude-code`, `~/.claude/CLAUDE.md` and the pre-push hook all stay
behind. Sessions in VS Code and the terminal run on your machine and keep
the installed layer.

What a Claude Code cloud session takes from this repository depends on how
it was started:

| Started with | Rule text | Hooks, deny lists and settings |
|---|---|---|
| One repository, outside a project | Root `CLAUDE.md` | Loaded from the root `.claude/settings.json` |
| Several repositories, or a thread in a project | Root `CLAUDE.md` | Not loaded |

The root `CLAUDE.md` is the one file every cloud session reads, so it
tells the session to read [user/CLAUDE.md](user/CLAUDE.md) as its user
rules. Where hooks are not loaded the written rules are the only guard.
The cloud Git proxy refuses branch deletions and tag pushes but does not
limit which branch a push updates, so protect `main` with a GitHub
ruleset.

One owner step per cloud environment, in its dialog at claude.ai/code: add
these environment variables with your own values, so commits made there
carry your name. Git reads them directly.

```text
GIT_AUTHOR_NAME=
GIT_AUTHOR_EMAIL=
GIT_COMMITTER_NAME=
GIT_COMMITTER_EMAIL=
```

The root settings switch off the co-author trailer, the pull request footer
and the session link that the cloud harness adds by default. The session
link key needs Claude Code 2.1.183 or later.

Source: [Configure cloud environments](https://code.claude.com/docs/en/cloud-environments).

---

## Git writes under a managed profile

Some managed profiles mount source Git metadata read-only. The owner
creates the task branch and worktree, then the agent edits and tests
allowed source files there. The owner stages named paths and makes any
requested commit after inspecting the diff. Creating the worktree does
not make its Git index writable to the agent.

Lattice task updates are separate from source Git writes. An agent can
keep the board current when the board is writable. If a Git write is
refused, stop that action and give the owner its exact command. Keep
source Git protected; do not switch Git directories to bypass the block.

---

## OpenAI documentation skill

Install `openai-docs` once from your terminal with the
[official installer](https://github.com/openai/skills/tree/main/skills/.system/skill-installer).
The skill guides documentation lookups for Codex and OpenAI products.

```bash
(
  set -euo pipefail
  mkdir -p "$HOME/.cache"
  docs_skill_src="$(mktemp -d "$HOME/.cache/openai-skills.XXXXXX")"
  git clone --depth 1 https://github.com/openai/skills.git "$docs_skill_src"
  /usr/bin/python3 \
    "$docs_skill_src/skills/.system/skill-installer/scripts/install-skill-from-github.py" \
    --repo openai/skills \
    --path skills/.curated/openai-docs \
    --ref "$(git -C "$docs_skill_src" rev-parse HEAD)" \
    --method download
  test -s "${CODEX_HOME:-$HOME/.codex}/skills/openai-docs/SKILL.md"
)
```

The destination is `$CODEX_HOME/skills/openai-docs`, or
`~/.codex/skills/openai-docs` when CODEX_HOME is unset. The installer stops
if that skill directory already exists.

Open a fresh Codex chat and ask it to use `$openai-docs` and report the
`SKILL.md` path it loaded. A successful install does not establish that
the agent can read the skill. If the file exists in your terminal but a
fresh chat cannot read it, review the managed profile's read access to
that exact skill directory. Do not reinstall or open the whole Codex home
to fix a visibility problem.

The skill does not register the OpenAI Docs MCP server. MCP registration
and managed-policy changes require separate owner approval. Check which
documentation tools the session actually exposes before claiming a lookup
worked.

The managed Codex profile grants read-only access to the attachment cache
at `~/.codex/attachments` and this skill's directory. Cache access includes
past uploads from other sessions. It does not open the rest of Codex home.
Existing input roots must be real directories without symlink components;
the installer refuses unsafe roots and reports missing optional ones.

Before installing this access change, check that both directories exist.
From the reviewed checkout, set SWE_WORKSPACE to the folder containing
your checkouts and preview with the normal installer:

```bash
(
  set -euo pipefail
  test "${CODEX_HOME:-$HOME/.codex}" = "$HOME/.codex"
  test -d "$HOME/.codex/attachments"
  test -d "$HOME/.codex/skills/openai-docs"
  if [ -f /etc/claude-code/managed-settings.d/50-local.json ]; then
    test -f "$HOME/.config/agent-alignment/managed-local.json"
  fi
  env -u SWE_ETC -u SWE_CODEX_ETC PATH=/usr/bin:/bin:/usr/local/bin \
    SWE_WORKSPACE="$HOME/projects" \
    SWE_MANAGED_LOCAL="$HOME/.config/agent-alignment/managed-local.json" \
    bash swe/scripts/install_isolation.sh
)
```

Review the preview before repeating the installer command with `--apply`.
Keep its printed backup and undo commands. Open a fresh Codex session to
check an existing attachment, a new harmless upload and the skill. Check
that the new roots are read-only and existing denials still hold. A passing
installer test does not establish those live checks. To roll back, use the
printed undo commands for changed files, then start another fresh session.

---

## A note on the sibling track

This repository has a sibling subtree at `../flourishing/` for
Inner-Commons + Flourishing alignment-prompt authoring. It is
independent. Ignore it unless you've been explicitly directed
there.
