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
  look like when building, reviewing and designing. A reference, read on
  demand.
- Thirteen specialist subagents in [.claude/agents/](.claude/agents/).
- Sixteen slash commands in [.claude/commands/](.claude/commands/).
- Hooks in [.claude/scripts/](.claude/scripts/): `guard_outward.py`
  runs on PreToolUse for Bash and MCP tools and denies outward
  actions and secret reads; `tells_check.py` runs on PostToolUse for
  Write and Edit; `session_start.sh` prints the branch, the protocol
  hashes and the agent and command roster; `after_summary.sh` runs on
  SessionStart for compact, resume and fork; `post_edit_verify.sh`
  names the check that fits the edited file for the session to run
  itself, and reminds it when a protocol or a dependency manifest
  changed; it runs no tool. Plus a status line.
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
| Screenshot or browser-verify a UI fix | `dashboard-probe` | `/swe-probe` |
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

A project's sessions read the kit from a clone at `.agent-alignment`;
[LATTICE_ONBOARDING.md](LATTICE_ONBOARDING.md#getting-the-kit-into-a-project)
has the commands that make it.

---

## Task board and review flow

[LATTICE_ONBOARDING.md](LATTICE_ONBOARDING.md) is an optional owner-run
setup for projects where the user wants a Lattice board and review flow.
`scripts/board_setup.sh` sets a project's board up, or brings it back
from its private repository.
[tools/lattice-review/](tools/lattice-review/) holds the server that adds
a review section to the Lattice dashboard, and the dashboard patch it needs.

---

## Keeping a project's board context current

Each project's `.lattice/context.md` is this kit's template with the
project's own names and edits. When the template gains a rule, run this
from a checkout of the kit, naming the project:

| Goal | Command |
|---|---|
| See whether a project is behind | `python3 swe/scripts/board_context.py status <project>` |
| Merge the template's changes in | `python3 swe/scripts/board_context.py apply <project>` |

A change that collides with the project's own edits leaves the context
untouched and writes the merge beside it as `context.md.proposed`.
`scripts/board_update.sh --apply`, run from the top of a project, does the
same merge and then commits the board, merges its remote and pushes.

---

## Decision records

A choice that is hard to undo, or that rejects an option someone will
try again, is written down in `docs/` as a decision record, in the shape
of [ADR_TEMPLATE.md](ADR_TEMPLATE.md). Sessions read the records that
govern a file before they plan, and reviewers read them before they
judge a change. A session may draft a record as proposed; only you
accept one, by changing its status.

| Goal | Command |
|---|---|
| Records that govern a file | `python3 swe/scripts/adr.py for <file>` |
| Rebuild the index after any change | `python3 swe/scripts/adr.py index --write` |
| Check the records and the index | `python3 swe/scripts/adr.py check` |

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
| Bring every project in the workspace up to date with the kit: push checks, agent and command copies, and boards (owner-run, after `apply`; folders named in `~/.config/agent-alignment/skip`, one a line, are left out, and it stops when that file is missing; with `--push` the push check may ask at the terminal) | `bash scripts/update_all.sh --yes --push` |
| Install the headless browser for screenshots (remove with `apt remove`) | `sudo apt install chromium-headless-shell` |
| Screenshot or click through a local page, app started in the same command | `python3 scripts/local_browser.py --app '<start command>' http://127.0.0.1:<port>/ shot:page` (`--help` lists the steps) |
| Run a project's own Playwright check in the sandbox ([security rule 12](SECURITY_PROTOCOL.md) has the limits) | Launch with `executablePath: '/usr/bin/chromium-headless-shell'` and make the context with `serviceWorkers: 'block'`. With Playwright Test, its `webServer` starts the app; otherwise start the app in the same command as the script. Under Codex a `webServer` check of a `url` timed out and waiting for a line the app prints passed (`wait: { stdout: /.../ }`, Playwright 1.64) |
| Lint hook scripts | `for f in .claude/scripts/*.sh scripts/*.sh; do bash -n "$f"; done; python3 -m py_compile .claude/scripts/*.py .claude/scripts/pre-push` |

There is no test suite for these protocols (they're prose). The
SWE protocols are validated by use.

---

## Trying a checkout and going back

A branch changes three kinds of file, and each reaches a session a
different way.

| What | Where it lives | How a session gets it |
|---|---|---|
| Agents, commands, protocols, project instructions | the checkout | They load from the folder a window is opened in. A window opened in a worktree can read them but loses Git and the board, so use one for a look and merge the branch to work under it |
| Managed settings and hooks, the Codex profile and rules, your user rules, the Git hooks (push check and privacy check), the kit's agents and slash commands for every project | this machine | `scripts/switch_rules.sh apply` |
| Board conventions | `.lattice/context.md` | `apply --context <file>` |

From a worktree of the branch you want to try:

```bash
bash swe/scripts/switch_rules.sh status   # what would change; writes nothing
bash swe/scripts/switch_rules.sh apply    # saves what is installed, then installs
# restart every Claude Code and Codex session, then test
bash swe/scripts/switch_rules.sh revert   # puts the saved state back
```

Run `status` in your own terminal: inside a session the sandbox hides
your home folder and remaps /etc, so its answer there is wrong. `apply`
and `revert` are yours: they use sudo and change the rules every session runs under.
Each `apply` keeps a snapshot in `~/.config/agent-alignment/snapshots/`,
a folder sessions cannot read or write. `revert` goes back to the state
before the first `apply` you have not reverted, or to the snapshot you
name, so two sets of rules can be compared by switching between them.
The script takes your checkouts to live in the folder this one is in;
set `SWE_WORKSPACE` if they do not. A plain `revert` after everything is
already reverted changes nothing and says so.

In VS Code, restarting means "Developer: Reload Window" in each window
and then a new chat in each extension. Codex reads its profile and rules
when a chat starts, and a resumed chat keeps the old ones. To try the
checkout's own agents, commands and project rules as well, open a window
on the worktree's `swe/` folder with `code <worktree>/swe`. On WSL, run
all of this from the distribution's shell: the files are on the Linux
side. A Codex rule can be checked without a session:

```bash
codex execpolicy check --pretty --rules ~/.codex/rules/default.rules -- git commit -n -m x
```

### Recover a Codex chat that requests `:read-only`

If a saved VS Code chat fails to send with `invalid thread settings
override` and the error names `:read-only` and `alignment_workstation`,
try a fresh chat in the same project. If it works, carry over the task
summary and continue there. The managed profile stays in effect.

#### Recover the original chat in VS Code (AA-93)

Ask:

> Give me the AA-93 temporary `:read-only` allowlist toggle for the
> VS Code picker, with `--enable` and `--restore`. Verify the current
> policy hash first.

The owner runs the toggle from a normal WSL terminal. It allows the
built-in profile machine-wide for the time needed to switch the chat.
That profile lacks the managed filesystem denials. Close other Codex
windows and avoid tasks or tool calls while the exception is enabled.
Wait until the policy is restored before running another policy install.

Run this read-only check while the policy is locked, and save both hashes
until the policy is restored.

```bash
(
  set -euo pipefail
  trap 'rc=$?; printf "exit=%s\nAA93_POLICY_CHECK_END\n" "$rc"; exit "$rc"' EXIT
  /usr/bin/python3 -I - <<'PY'
import hashlib
import tomllib
from pathlib import Path

raw = Path("/etc/codex/requirements.toml").read_bytes()
policy = tomllib.loads(raw.decode())
profile = {"alignment_workstation": True}
if policy.get("default_permissions") != "alignment_workstation" or policy.get("allowed_permission_profiles") != profile:
    raise SystemExit("Expected a locked alignment_workstation policy.")
header = b"[allowed_permission_profiles]\n"
if raw.count(header) != 1:
    raise SystemExit("Expected one exact allowlist header.")
enabled = raw.replace(header, header + b'":read-only" = true\n', 1)
policy["allowed_permission_profiles"][":read-only"] = True
if tomllib.loads(enabled.decode()) != policy:
    raise SystemExit("The temporary file changes more than the allowlist.")
print("Locked SHA-256:", hashlib.sha256(raw).hexdigest())
print("Enabled SHA-256:", hashlib.sha256(enabled).hexdigest())
PY
)
```

Run the block below with `--enable`, and enter the checked hashes.
In the affected VS Code window, run **Developer: Reload Window** and
open the old chat. Confirm that it selects `alignment_workstation` or
select it in the permission picker.

Run the same block with `--restore` and the same hashes, even if the
picker fails. Reload every window that loaded the exception. Send
`Reply OK. Do not use tools.` in the same old chat to check that the
selection survived. A fresh chat in the same project is the fallback.

```bash
(
  set -euo pipefail
  trap 'rc=$?; printf "exit=%s\nAA93_ALLOWLIST_TOGGLE_END\n" "$rc"; exit "$rc"' EXIT
  read -r -p 'Enter --enable or --restore: ' mode
  read -r -p 'Locked SHA-256: ' locked
  read -r -p 'Enabled SHA-256: ' enabled

  sudo /bin/bash -s -- "$mode" "$locked" "$enabled" <<'AA93'
set -euo pipefail
policy=/etc/codex/requirements.toml
hash() { sha256sum | cut -d' ' -f1; }
add='/^\[allowed_permission_profiles\]$/a ":read-only" = true'
remove='/^":read-only" = true$/d'

case "$1" in
  --enable) before=$2; after=$3; edit=$add; undo=$remove ;;
  --restore) before=$3; after=$2; edit=$remove; undo=$add ;;
  *) printf '%s\n' 'Enter --enable or --restore.' >&2; exit 2 ;;
esac
if [[ ! -f "$policy" || -L "$policy" || -L "${policy%/*}" ]]; then
  printf '%s\n' 'Unexpected policy path.' >&2; exit 1
fi
current=$(hash < "$policy")
if [[ "$current" == "$after" ]]; then
  if [[ "$before" == "$after" || "$(sed "$undo" "$policy" | hash)" != "$before" ]]; then
    printf '%s\n' 'Locked and enabled hashes do not match the toggle.' >&2; exit 1
  fi
  printf 'Already applied: %s\n' "$1"
  exit 0
fi
if [[ "$current" != "$before" ]]; then printf '%s\n' 'Policy hash differs from the checked version.' >&2; exit 1; fi

staged=$(mktemp -- "$policy.aa93.XXXXXXXX")
trap 'if [[ -e "$staged" ]]; then unlink -- "$staged"; fi' EXIT
cp --preserve=all -- "$policy" "$staged"
sed "$edit" "$policy" > "$staged"
if [[ "$(hash < "$staged")" != "$after" || "$(hash < "$policy")" != "$before" ]]; then
  printf '%s\n' 'Policy verification failed before replacement.' >&2; exit 1
fi
mv -fT -- "$staged" "$policy"
test "$(hash < "$policy")" = "$after"
printf 'Applied and verified: %s\n' "$1"
AA93
)
```

---

## sources

The planning guidance draws on [GitHub Spec Kit](https://github.com/github/spec-kit)
for user cases and acceptance checks, and
[Anthropic's guidance on long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
for completing one feature through an end-to-end check. The shared plan
shape combines those practices with this toolkit's approval and testing
rules. Keep source links and required provenance when adapting guidance.

Other kits give an agent a planning and review workflow:
[Superpowers](https://github.com/obra/superpowers),
[OpenSpec](https://github.com/Fission-AI/OpenSpec) and the
[BMAD Method](https://github.com/bmad-code-org/BMAD-METHOD), besides
Spec Kit. Felipe Fontoura
[ran one small feature through all four](https://felipefontoura.com/articles/spec-driven-development-tools-compared/)
in October 2026, and two of his results match choices made here. The
heaviest process cost about nine times the lightest and passed the same
thirteen acceptance checks, so here the plan grows with the task and a
small fix skips the approval stop. None of the four recorded a human
approval that code could check, so here the plan approval, the evidence
for each acceptance criterion and each review thread are records on the
board, and the review section does not offer Mark done while a criterion
lacks evidence or a thread is open.

The command guard is closest to [guard](https://github.com/TracineHQ/guard)
and [Leash](https://github.com/hoophq/leash), hooks that stop a harmful
command before it runs. guard calls itself defense in depth and not a
security boundary. The same holds here: a hook reads the text of a
command, so the sandbox and the deny lists are the boundary.

The review rules follow published practice. Findings are graded P0 to
P3, the letters [Codex review](https://developers.openai.com/codex/use-cases/github-code-reviews)
uses, and a P0 or P1 says what confirmed it, as
[Anthropic's Code Review](https://code.claude.com/docs/en/code-review)
checks each finding against the code before reporting it. A sensitive
change gets a skeptic that must cite the code, not a second reviewer of
the same kind, after [a 2026 study](https://arxiv.org/abs/2608.18167)
in which two like reviewers did no better than one.

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
rules. Where the root settings load, they also run the guard in
[.claude/scripts/](.claude/scripts/) for a cloud session. Where hooks are
not loaded the written rules are the only guard.

You have no shell in a cloud session, so its work reaches you only if
the session pushes. It does that when you ask, with
`bash .claude/scripts/cloud_push.sh` from the repository root: the
current `feature/<ID>-<slug>` branch, fast-forward only, or the board
with `--board`. The cloud Git proxy refuses branch deletions and tag
pushes but does not limit which branch a push updates, so protect `main`
with a GitHub ruleset; that is the boundary, and the script is the
routine path.

One owner step per cloud environment, in its dialog at claude.ai/code: add
these environment variables with your own values, so commits made there
carry your name. Git reads them directly. Until they are set the push
script refuses, because a commit under the tool's name cannot be taken
back once it is public.

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
independent.
