# agent-alignment

**Two prompt-and-agent stacks in one repository, with shared
infrastructure.** This repo ships:

- **Track A — agentic software engineering** — a complete
  `.claude/` setup (10 SWE subagents, 10 SWE slash commands,
  language-aware hooks, sane permissions) and four canonical
  protocol modules (SWE_CORE, TESTING, PERFORMANCE, SECURITY) that
  any project can adopt.
- **Track B — Inner Commons + Flourishing** — a four-module
  prompt library for sovereign AI agents that are honest,
  consent-aware, repair-capable, and oriented toward human and
  planetary flourishing, plus 10 alignment subagents and 8
  slash commands for authoring, composing, and evaluating those
  prompts.

The two tracks are independent. Pick the one you need and the rest
stays out of the way.

---

## Which track are you on?

| You are… | Read this first |
|---|---|
| A SWE agent dropped into this repo to do coding work | [QUICKSTART_SWE.md](QUICKSTART_SWE.md) |
| A SWE agent that wants to install these protocols in another repo | [QUICKSTART_SWE.md](QUICKSTART_SWE.md) → run `/swe-init` in that repo |
| An agent or human authoring or composing alignment prompts | [QUICKSTART_FLOURISHING.md](QUICKSTART_FLOURISHING.md) |
| Just looking at the project conventions | [CLAUDE.md](CLAUDE.md) |
| Wondering how the two tracks coexist | [docs/ADR-0001-dual-track.md](docs/ADR-0001-dual-track.md) |

A 30-second read of either QUICKSTART tells you exactly which
files to load and which agents to spawn.

---

## Track A — agentic software engineering

**Purpose:** keep agentic coding work *correct, reversible,
verifiable, and minimal.* Four canonical protocols, ten subagents,
ten slash commands, language-aware hooks.

**Canonical protocols** (drop-in system prompts):

| File | Purpose |
|---|---|
| [SWE_CORE.md](SWE_CORE.md) | Universal engineering principles: read first, fix root causes, delete dead code, verify before claiming done, execute with care. |
| [TESTING_PROTOCOL.md](TESTING_PROTOCOL.md) | Failing test first for bugs; deterministic, fast, behavior-focused tests; CI gate ordering. |
| [PERFORMANCE_PROTOCOL.md](PERFORMANCE_PROTOCOL.md) | Measure first; name the budget; tail latency; idle costs nothing. |
| [SECURITY_PROTOCOL.md](SECURITY_PROTOCOL.md) | Trust-boundary discipline; OWASP top-10 quick-check; least privilege; fail closed. |

**SWE subagents** (`.claude/agents/`):

`code-reviewer` · `regression-test-writer` · `security-reviewer` ·
`perf-auditor` · `dashboard-probe` · `dependency-auditor` ·
`architecture-explorer` · `refactoring-planner` · `debugger` ·
`docs-writer`

**SWE slash commands** (`.claude/commands/`):

`/swe-explore` · `/swe-review` · `/swe-add-test` · `/swe-fix-bug` ·
`/swe-debug` · `/swe-perf` · `/swe-security` · `/swe-deps` ·
`/swe-refactor` · `/swe-probe` · `/swe-docs` · `/swe-swarm-review` ·
`/swe-init` (install the protocol stack into another repo)

---

## Track B — Inner Commons + Flourishing

**Purpose:** prompt infrastructure for sovereign AI systems —
relational alignment, externality awareness, anti-sycophancy,
repair after mistakes. Use this stack when you are building or
prompt-engineering an AI agent that interacts with people.

**Canonical alignment modules** (drop-in system prompts):

| File | Purpose |
|---|---|
| [INNER_COMMONS_CORE.md](INNER_COMMONS_CORE.md) | Relational alignment: TRUST / CONSENT / ATTENTION / REPAIR CAPACITY. |
| [FLOURISHING_PROTOCOL.md](FLOURISHING_PROTOCOL.md) | Human and planetary stewardship: externalities, public-interest harms, ecological costs. |
| [SKEPTIC_ARBITER.md](SKEPTIC_ARBITER.md) | Anti-sycophancy internal deliberation. |
| [REPAIR_PROTOCOL.md](REPAIR_PROTOCOL.md) | Rupture detection + six-step repair sequence. |

**Composed and provider variants:**

| File | Use when |
|---|---|
| [COMPOSED_AGENT.md](COMPOSED_AGENT.md) | All four modules in one drop-in system prompt. |
| [FOR_CLAUDE.md](FOR_CLAUDE.md) | Claude.ai (XML-tagged) + abbreviated User-Preferences variant. |
| [FOR_CHATGPT.md](FOR_CHATGPT.md) | ChatGPT system-prompt variant. |
| [FOR_API.md](FOR_API.md) | API system-prompt composition guidance. |

**Alignment subagents** (`.claude/agents/`):

`inner-commons-steward` · `flourishing-auditor` · `skeptic` ·
`arbiter` · `repair-coach` · `module-composer` · `drift-checker` ·
`scenario-evaluator` · `prose-editor` · `pr-rubric-reviewer`

**Alignment slash commands** (`.claude/commands/`):

`/align-compose` · `/align-drift-check` · `/align-skeptic` ·
`/align-repair` · `/align-flourishing-check` · `/align-scenario` ·
`/align-add-module` · `/align-swarm-review`

---

## Repository map (top level)

```
.
├── README.md                         # this file
├── CLAUDE.md                         # project-level engineering guidelines
├── AGENTS.md                         # symlink → CLAUDE.md (cross-tool)
├── QUICKSTART_SWE.md                 # 30-second SWE onboarding
├── QUICKSTART_FLOURISHING.md         # 30-second alignment onboarding
├── CONTRIBUTING.md                   # PR rubric for both tracks
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
│   └── ADR-0001-dual-track.md        # why two tracks coexist
├── eval/
│   └── scenarios/                    # Track B behavioral specs
├── scripts/
│   └── check_drift.sh                # canonical / derived hashes
├── presentations/                    # companion materials
├── media/                            # images / diagrams
│
└── .claude/
    ├── settings.json                 # permissions, env, hooks, status line
    ├── README.md                     # .claude/ structure
    ├── agents/                       # 20 specialist subagents (10 SWE + 10 alignment)
    ├── commands/                     # 18 slash commands (10 SWE + 8 alignment)
    └── scripts/                      # SessionStart / pre-bash / post-edit / statusline
```

---

## Source lineage

The Inner Commons / Flourishing track is based on Patrick Deegan's
2026 essay *Inner Alignment as a Commons* and extends it with a
broader flourishing and externalities layer for sovereign agent
infrastructure.

The SWE track distills industry-wide engineering discipline
(read-before-write, root-cause fixes, failing-test-first, OWASP
top-10, performance budgeting, least privilege) into the same
canonical-module shape so a single agent toolkit can serve both.
