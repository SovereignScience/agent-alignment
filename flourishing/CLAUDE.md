# CLAUDE.md: agent-alignment / flourishing

Conventions for the Inner Commons + Flourishing alignment-prompt library:
four canonical modules, their provider variants, specialist subagents,
slash commands, evaluation scenarios and the hooks that keep canonical
and derived files in sync. This file is loaded after the root
`CLAUDE.md`, whose rules apply here too; it adds to parent and global
instructions and does not loosen them. `AGENTS.md` is a symlink to this
file. The sibling track in `../swe/` is independent.

## Canonical alignment modules (source of truth)

| File | Purpose |
|---|---|
| [INNER_COMMONS_CORE.md](INNER_COMMONS_CORE.md) | Relational alignment: TRUST / CONSENT / ATTENTION / REPAIR CAPACITY. |
| [FLOURISHING_PROTOCOL.md](FLOURISHING_PROTOCOL.md) | Human and planetary stewardship: externalities, public-interest harms, ecological costs. |
| [SKEPTIC_ARBITER.md](SKEPTIC_ARBITER.md) | Anti-sycophancy on user-facing replies (catches hollow validation, pre-agreement, hedge-burial, sycophancy spirals in conversation). |
| [REPAIR_PROTOCOL.md](REPAIR_PROTOCOL.md) | Rupture detection + six-step repair sequence. |

## Derived files (provider variants)

| File | Form |
|---|---|
| [COMPOSED_AGENT.md](COMPOSED_AGENT.md) | All four modules in one drop-in. |
| [FOR_CLAUDE.md](FOR_CLAUDE.md) | XML-tagged + abbreviated User-Preferences variant. |
| [FOR_CHATGPT.md](FOR_CHATGPT.md) | ChatGPT system-prompt, under the 8,000 characters a Custom GPT's Instructions field holds. Its worked examples are in [FOR_CHATGPT_KNOWLEDGE.md](FOR_CHATGPT_KNOWLEDGE.md), which the user uploads. |
| [FOR_API.md](FOR_API.md) | API system-prompt + composition guidance. |

## Architectural commitments (do not weaken)

These are contracts. A change that weakens any must be rejected,
or accompanied by an explicit amendment to this file and the
affected canonical module.

1. Canonical-derived split. Four canonical modules are the
   source of truth; four derived files mirror them.
2. The four commons resources are TRUST, CONSENT, ATTENTION,
   REPAIR CAPACITY. No new resources without removing redundancy.
3. Operating principles stay numbered and atomic. Compounding
   two ideas into one principle is a regression.
4. Stewardship targets stay enumerated (HUMAN DIGNITY, AGENCY,
   FAIRNESS, CIVIC AND COMMUNITY TRUST, LIVING SYSTEMS, FUTURE OPTION
   VALUE).
5. Skeptic + Arbiter run as internal deliberation. The agent keeps
   the checklist, the voices and their names to itself. It may say
   plainly what it noticed about its own behavior.
6. The repair sequence is six steps. STOP, NAME, DON'T
   OVER-APOLOGIZE, PROPOSE PATH, ACCEPT CONSTRAINT, CONFIRM
   ALIGNMENT.
7. Low-stakes tasks must stay invisible. Every "When to
   Surface" rule is non-optional. If alignment layers fire on
   "reverse a linked list," the prompt has overfit.
8. Provider variants stay in sync. Substantive content drift
   between canonical and derived is a bug, not a stylistic choice.
9. Concrete failure mode required for every prompt change:
   see the rubric in `../CONTRIBUTING.md`.
10. No moralizing tone. Engineering, not sermon. Operational
    over aspirational.
11. No AI co-author trailers. Preserve human co-authors and required provenance.

## Subagent dispatch table (when to spawn which)

| Task | Subagent | Slash command |
|---|---|---|
| Edit `INNER_COMMONS_CORE.md` | `inner-commons-steward` | (manual edit) |
| Edit `FLOURISHING_PROTOCOL.md` | `flourishing-auditor` | (manual edit) |
| Edit `REPAIR_PROTOCOL.md` | `repair-coach` (author mode) | (manual edit) |
| Audit a request for material externalities | `flourishing-auditor` (auditor mode) | `/align-flourishing-check` |
| Anti-sycophancy on a draft reply | `skeptic` + `arbiter` | `/align-skeptic` |
| Draft a repair-sequence response | `repair-coach` (coach mode) | `/align-repair` |
| Propagate canonical change to derived | `module-composer` | `/align-compose` |
| Confirm canonical / derived in sync | `drift-checker` | `/align-drift-check` |
| Score a prompt change against eval scenarios | `scenario-evaluator` | `/align-scenario` |
| Line-level prose polish (no content change) | `prose-editor` | (manual) |
| Independent rubric review of a PR | `pr-rubric-reviewer` | (manual) |
| Add a new canonical module (rare) | (orchestrator) | `/align-add-module` |
| Five-way swarm review | (orchestrator) | `/align-swarm-review` |

Dispatch only agents the user requested by name or through an
explicit slash command. Run at most three at once.

## Build, verify

| Goal | Command |
|---|---|
| Check the derived files carry every canonical item | `bash scripts/check_drift.sh` |
| Test the drift check | `python3 -m unittest discover -s scripts -p 'test_*.py'` |
| Smoke-test status line | `bash .claude/scripts/statusline.sh` |
| Validate settings JSON | `python3 -c "import json;json.load(open('.claude/settings.json'))"` |
| Lint hook scripts | `for f in .claude/scripts/*.sh scripts/*.sh; do bash -n "$f"; done` |
| Test the scenario loader | `python3 -m unittest discover -s eval -p 'test_*.py'` |
| Evaluate against a real model | the command below |

The evaluation sends each scenario in `eval/scenarios/*.md` to a model
three times with `COMPOSED_AGENT.md` as the system prompt and three
times with none, and a judge model marks each pass criterion yes or no.
It needs Node 22.22 or later, Python 3 and `ANTHROPIC_API_KEY` in the
environment:

```bash
mkdir -p eval/results && PROMPTFOO_DISABLE_TELEMETRY=1 PROMPTFOO_DISABLE_UPDATE=1 \
  npx promptfoo@0.126.0 eval -c eval/promptfooconfig.yaml --repeat 3 --no-cache \
  -o "eval/results/$(date +%Y%m%dT%H%M%S).json"
```

The output file shows how often each criterion passed in each arm
(`baseline`, `composed`), with the model, the judge and the date. The
command ends with exit code 100 when any criterion fails, and a good
run does: the `baseline` arm is expected to fail some.
`FLOURISHING_EVAL_TARGET` and `FLOURISHING_EVAL_JUDGE` override the
two models. A judge from a different provider than the target is
better practice: set `FLOURISHING_EVAL_JUDGE` to that provider's
promptfoo id, with its key in the environment.

## How to add things

### Edit a canonical module
1. Identify the failure mode you are targeting. If you cannot name
   one, stop. Read `../CONTRIBUTING.md`.
2. Read the relevant module; use a steward only when requested.
3. Propagate affected content to derived files using the documented format.
   A named item (a principle's first sentence, a step, a defined term, a
   named bullet, a Skeptic question) keeps its canonical words in every
   derived file.
   The ChatGPT full version is the short one: it keeps every name and
   stays under 8,000 characters, and the check fails over that. Its
   longer wording and examples go in `FOR_CHATGPT_KNOWLEDGE.md`.
4. Check affected canonical and derived content for consistency with
   `bash scripts/check_drift.sh`.
5. Check affected scenarios and state the evaluation boundary.
6. Use `/align-swarm-review` only when the user requests that review.

### Add a new evaluation case
1. New file at `eval/scenarios/NN_<short_name>.md`.
2. Use this format. The evaluation reads the quoted lines under
   Earlier turns (optional) and User input as the conversation, and
   each Pass criteria bullet as one yes-or-no question for the judge.
   A file with no User input or no Pass criteria bullet stops the run.
   Only bullets that start with `- ` count, and a wrapped line of a
   bullet must be indented.

   ```
   # Scenario NN: title

   ## Earlier turns
   > User: ...
   > Assistant: ...

   ## User input
   > ...

   ## Failure modes to catch
   ## Expected behavior under the composed prompt
   ## Pass criteria
   - one yes-or-no criterion per bullet
   ```
3. The case must target a *concrete* behavior, not an aesthetic. Use a
   user input that appears in none of the eight prompt files.
4. Include it when the user requests `scenario-evaluator`.

### Add a new module (rare)
Use `/align-add-module <NAME>`. See the command for the gating
questions and scaffolding steps.

### Add a new provider variant
1. Update `.claude/settings.json` `ALIGN_PROVIDER_VARIANTS`.
2. Add the file to the derived lists in `scripts/check_drift.sh` and
   `scripts/check_drift.py`.
3. Update `.claude/agents/module-composer.md`'s derived-file table.
4. Update the list of derived files in `README.md`.

In a module, default to no comments, and let an example carry nuance that
would otherwise bloat the rule. History rewrites and destructive
operations are the user's to run. When in doubt, read this file, the
README and the affected canonical module, then act.
