# flourishing: Inner Commons + Flourishing alignment-prompt library

You are in the alignment-prompt-authoring track of `agent-alignment`.
Everything you need is in this folder. Read this file, then act.

## What this folder gives you

- Four canonical alignment modules, the source of truth:
  - [INNER_COMMONS_CORE.md](INNER_COMMONS_CORE.md): relational layer
  - [FLOURISHING_PROTOCOL.md](FLOURISHING_PROTOCOL.md): externalities
  - [SKEPTIC_ARBITER.md](SKEPTIC_ARBITER.md): anti-sycophancy
  - [REPAIR_PROTOCOL.md](REPAIR_PROTOCOL.md): rupture + repair
- Four derived files, provider-specific renders:
  - [COMPOSED_AGENT.md](COMPOSED_AGENT.md) (drop-in)
  - [FOR_CLAUDE.md](FOR_CLAUDE.md) (XML-tagged)
  - [FOR_CHATGPT.md](FOR_CHATGPT.md)
  - [FOR_API.md](FOR_API.md)
- Ten alignment subagents in [.claude/agents/](.claude/agents/):
  one steward per canonical module + composer / drift-checker /
  scenario-evaluator / prose-editor / skeptic / arbiter /
  pr-rubric-reviewer.
- Eight slash commands in [.claude/commands/](.claude/commands/).
- Six checked-in evaluation scenarios in
  [eval/scenarios/](eval/scenarios/).

For full project conventions read [CLAUDE.md](CLAUDE.md).

---

## What to load into your context

For any change to a canonical module, load:

- The canonical module itself
- `../CONTRIBUTING.md`: review rubric and the five PR-expectation
  questions

Optional but useful:

- [COMPOSED_AGENT.md](COMPOSED_AGENT.md): to see how the change
  composes with the other three modules
- The matching provider variant (`FOR_CLAUDE.md` etc.): to see how
  the change renders per-provider

The eval scenarios are loaded automatically by `scenario-evaluator`
when you run `/align-scenario`.

---

## What to do first

```
/align-drift-check
```

Confirms canonical-vs-derived consistency before you start editing.
If the verdict is `NEEDS-COMPOSER`, run `/align-compose <changed-canonical>`
first to bring derived files in sync.

---

## Subagent dispatch table (when to spawn which)

| Task | Subagent | Slash command |
|---|---|---|
| Edit `INNER_COMMONS_CORE.md` | `inner-commons-steward` | (manual edit) |
| Edit `FLOURISHING_PROTOCOL.md` | `flourishing-auditor` | (manual edit) |
| Edit `REPAIR_PROTOCOL.md` | `repair-coach` (author mode) | (manual edit) |
| Audit a request for material externalities | `flourishing-auditor` (auditor mode) | `/align-flourishing-check` |
| Anti-sycophancy on a draft response | `skeptic` + `arbiter` | `/align-skeptic` |
| Draft repair-sequence response | `repair-coach` (coach mode) | `/align-repair` |
| Propagate canonical change to derived | `module-composer` | `/align-compose` |
| Confirm canonical / derived in sync | `drift-checker` | `/align-drift-check` |
| Score a prompt change against eval scenarios | `scenario-evaluator` | `/align-scenario` |
| Line-level prose polish (no content change) | `prose-editor` | (manual) |
| Independent rubric review of a PR | `pr-rubric-reviewer` | (manual) |
| Add a new canonical module (rare) | (orchestrator) | `/align-add-module` |
| Five-way swarm review | (orchestrator) | `/align-swarm-review` |

Dispatch only agents the user requested by name or through an
explicit slash command. Run at most three at once.

---

## The non-negotiable architectural commitments

These are contracts. A change that weakens any of them must be
rejected, or accompanied by an explicit amendment to
[CLAUDE.md](CLAUDE.md):

1. Canonical-derived split. The four canonical modules are the
   source of truth; the four derived files mirror them.
2. The four commons resources are TRUST, CONSENT, ATTENTION,
   REPAIR CAPACITY. No new resources without removing redundancy.
3. Operating principles stay numbered and atomic. Compounding
   two ideas into one principle is a regression.
4. Stewardship targets stay enumerated (HUMAN DIGNITY, AGENCY,
   FAIRNESS, CIVIC TRUST, LIVING SYSTEMS, FUTURE OPTION VALUE).
5. Skeptic + Arbiter run as internal deliberation. Never
   surface their output to the user.
6. The repair sequence is six steps. STOP, NAME, DON'T
   OVER-APOLOGIZE, PROPOSE PATH, ACCEPT CONSTRAINT, CONFIRM
   ALIGNMENT.
7. Low-stakes tasks must stay invisible. The "When to Surface"
   rule is non-optional.
8. Provider variants stay in sync. Substantive content drift
   is a bug.
9. Concrete failure mode required. Every change must name the
   failure mode it targets.
10. No moralizing tone. Engineering, not sermon.

---

## How to add things (canonical procedures)

### Edit a canonical module
1. Identify the failure mode you are targeting. If you cannot name
   one, stop. Read `../CONTRIBUTING.md`.
2. Read the relevant module; use a steward only when requested.
3. Propagate affected content to derived files using the documented format.
4. Check affected canonical and derived content for consistency with
   `bash scripts/check_drift.sh`.
5. Check affected scenarios and state the evaluation boundary.
6. Use `/align-swarm-review` only when the user requests that review.

### Add a new evaluation case
1. New file at `eval/scenarios/NN_<short_name>.md`.
2. Sections required: User input · Failure modes to catch ·
   Expected behavior under the composed prompt · Pass criteria.
3. The case must target a *concrete* behavior, not an aesthetic.

### Add a new module (rare)
Use `/align-add-module <NAME>`. See the command for the gating
questions and scaffolding steps.

---

## Build, verify

| Goal | Command |
|---|---|
| Print canonical + derived hashes | `bash scripts/check_drift.sh` |
| Validate settings JSON | `python3 -c "import json;json.load(open('.claude/settings.json'))"` |
| Smoke-test status line | `bash .claude/scripts/statusline.sh` |

There is no test suite for prose. Evaluation runs through
`scenario-evaluator` and `eval/scenarios/*.md`.

---

## A note on the sibling track

This repository has a sibling subtree at `../swe/` for agentic
software-engineering work. It is fully independent. Ignore it
unless you've been explicitly directed there.
