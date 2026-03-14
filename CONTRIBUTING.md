# Contributing

This repository is for prompt infrastructure, not prompt theater. Changes should make agent behavior more legible, more honest, more consent-aware, and more supportive of human and planetary flourishing.

## What Good Changes Look Like

- They target a concrete failure mode.
- They improve user agency rather than replacing it.
- They make uncertainty, tradeoffs, and power explicit.
- They account for downstream harms to other people, communities, and living systems.
- They stay composable across Claude, ChatGPT, API, and future variants.
- They add or update examples when the behavior change is not obvious.

## Pull Request Expectations

Every prompt change should answer:

1. What behavior should change?
2. What failure mode are we fixing?
3. What new failure modes could this introduce?
4. Which platform variants need to stay in sync?
5. What example demonstrates the intended behavior?

## Review Rubric

Review changes against these questions:

- Does this preserve user dignity, agency, and consent?
- Does it reduce sycophancy, manipulation, or dependency?
- Does it improve repair quality after mistakes?
- Does it make third-party, civic, labor, or ecological externalities more legible?
- Does it keep the model practical rather than preachy or obstructive?
- Does it remain concise enough to be used in real systems?

## Suggested Evaluation Cases

Test new prompt revisions against at least a few of these:

- A user fishing for reassurance rather than evaluation.
- A user pushing past a stated boundary.
- A user asking for a dark pattern, manipulative copy, or greenwashing language.
- A high-stakes recommendation with real uncertainty.
- A case where the user's local win creates hidden costs for others.
- A low-stakes coding or writing task where the extra alignment layer should stay invisible.

## Style

- Prefer simple language over jargon.
- Avoid moral grandstanding.
- Make operational rules explicit.
- Use examples to carry nuance that would otherwise bloat the main prompt.

## Scope Discipline

If a change belongs in one module, keep it there. Do not duplicate long blocks across files unless the platform-specific format actually requires it.
