---
description: Run the Skeptic-Arbiter pipeline over a draft engineering verdict. code-skeptic flags hollow approvals, missing specificity, hedge-burial, sycophancy spirals, and unverified completion claims; code-arbiter rewrites if flagged. Use to dry-run a review or sign-off before it reaches the user.
argument-hint: <path-to-draft-or-quoted-text>
allowed-tools: Read, Agent
model: inherit
---

Inspect a draft engineering verdict for sycophancy, missing
evidence, hedge-burial, and unverified completion claims.

Input: `$ARGUMENTS` is either a path to a file containing the draft,
or the draft itself enclosed in triple backticks.

Steps:

1. Spawn `code-skeptic` with the draft and any visible context
   (the diff under review, prior turns of this review, etc.).
   Brief: "return your flag list per the format defined in your
   agent definition. SILENT if no flags fire."
2. If `code-skeptic` returns flags, spawn `code-arbiter` with both
   the draft and the flag list. Brief: "produce the final review
   verdict, calibrated to flag severity. Cite file:line evidence,
   name severity, no hedge-burial."
3. Output to the user: the Skeptic flag list, then the Arbiter's
   rewritten verdict (or "No rewrite — Skeptic was silent.").

Do not modify any file in the repo.
