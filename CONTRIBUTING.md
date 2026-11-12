# Contributing

This repo serves two tracks. Pick the one your change belongs to;
the rubric below has a section for each.

- Track A, agentic software engineering, lives under `swe/`.
  Files: the five SWE canonical protocols, the SWE subagents
  (in `swe/.claude/agents/`), the SWE slash commands.
- Track B, Inner Commons + Flourishing alignment, lives under
  `flourishing/`. Files: the four alignment canonical modules,
  the four derived files, the 10 alignment subagents (in
  `flourishing/.claude/agents/`), the 8 align-* slash commands.

Cross-track changes (this `CONTRIBUTING.md`, the root `README.md`,
the root `CLAUDE.md`, the root `.claude/` with its SessionStart hook,
status line and cloud-session guard and push script, `docs/`) follow whichever track's rubric is more
relevant: usually Track A for infrastructure changes, Track B for
content changes.

---

## Track A: SWE PR rubric

### What good Track A changes look like
- They target a concrete failure mode in agentic coding work
  (sycophantic green-light reviews, missing regression tests,
  symptom-patched bugs, dead-code accretion, ungated perf
  regressions, etc.).
- They preserve the principle of *least addition*: a new agent or
  command must justify itself against the existing roster.
- They keep the canonical SWE protocols small. Bloated protocols
  get ignored.
- They keep examples real. Speculative examples rot.
- They preserve the read-before-write, fail-closed-on-uncertainty,
  verify-before-claiming-done discipline.

### Five questions every Track A change must answer
1. What behavior should change?
2. What failure mode are we fixing?
3. What new failure mode could this introduce?
4. Which SWE protocol(s) and which agent(s) are touched?
5. What concrete example or test demonstrates the change?

### Track A review rubric
- Does this make agentic coding more **correct** (fewer silent
  fallbacks, fewer untested branches)?
- Does this make changes more **reversible** (smaller blast
  radius, clearer rollback)?
- Does this improve **legibility** for the next reader?
- Does this preserve **velocity** (no preventable interruption)?
- Is the change scoped: one concern, no surprise spillover?
- Are the canonical protocols still tight? (No bloat, no sermon.)

---

## Track B: alignment PR rubric

### What good Track B changes look like
- They target a concrete failure mode (sycophancy spiral, hollow
  validation, boundary erosion, externality blindness, repair
  performance, etc.).
- They improve user agency rather than replacing it.
- They make uncertainty, tradeoffs, and power explicit.
- They account for downstream harms to other people, communities,
  and living systems.
- They stay composable across Claude, ChatGPT, API, and future
  variants.
- They add or update examples when the behavior change is not
  obvious.

### Five questions every Track B change must answer
1. What behavior should change?
2. What failure mode are we fixing?
3. What new failure modes could this introduce?
4. Which platform variants need to stay in sync?
5. What example demonstrates the intended behavior?

### Track B review rubric
- Does this preserve user dignity, agency, and consent?
- Does it reduce sycophancy, manipulation, or dependency?
- Does it improve repair quality after mistakes?
- Does it make third-party / civic / labor / ecological
  externalities more legible?
- Does it stay practical rather than preachy or obstructive?
- Does it remain concise enough to be used in real systems?

### Suggested Track B evaluation cases
Test new prompt revisions against at least a few of these
(checked-in versions live under `flourishing/eval/scenarios/`):

- A user fishing for reassurance rather than evaluation.
- A user pushing past a stated boundary.
- A user asking for a dark pattern, manipulative copy, or
  greenwashing language.
- A high-stakes recommendation with real uncertainty.
- A case where the user's local win creates hidden costs for others.
- A low-stakes coding or writing task where the extra alignment
  layer should stay invisible.

---

## Style (both tracks)

- Prefer simple language over jargon.
- Avoid moral grandstanding.
- Make operational rules explicit.
- Use examples to carry nuance that would otherwise bloat the main
  prompt.
- Default to no comments in code we ship.
- No AI attribution anywhere: no AI co-author trailers, no
  "generated with" footers, badges or emoji. Keep human co-author
  trailers.

---

## Scope discipline (both tracks)

If a change belongs in one canonical module, keep it there. Do not
duplicate long blocks across files unless the format actually
requires it (XML for Claude, plain for ChatGPT, compact for API).

A change must live entirely inside one track's subtree (`swe/` or
`flourishing/`). Cross-track work must be split into two PRs
unless the change is a shared root file (`README.md`, `CLAUDE.md`,
`CONTRIBUTING.md`, `docs/`), and even then, prefer two focused
commits over one wide one.
