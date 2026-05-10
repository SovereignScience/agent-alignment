---
description: Run the Skeptic-Arbiter pipeline over a draft response. Skeptic flags hollow validation, pre-agreement, hedge-burial, and sycophancy spirals; Arbiter rewrites if flagged. Use to dry-run a reply before it goes back to the user.
argument-hint: <path-to-draft-or-quoted-text>
allowed-tools: Read, Agent
model: inherit
---

Inspect a draft response for sycophancy, hollow validation, hedge-buried
disagreement, and pre-agreement with the question's framing.

Input: `$ARGUMENTS` is either a path to a file containing the draft, or
the draft itself enclosed in triple backticks.

Steps:

1. Spawn `skeptic` with the draft and any visible user-side context
   (e.g., the prior turns the user pastes in). Brief: "return your
   flag list in the format defined in your agent definition. SILENT
   if no flags fire."
2. If skeptic returns flags, spawn `arbiter` with both the draft and
   the flag list. Brief: "produce the final response, calibrated to
   flag severity. Do not over-correct. Do not lecture."
3. Output to the user: the Skeptic flag list, then the Arbiter's
   rewritten response (or "No rewrite — Skeptic was silent.").

Do not modify any file in the repo.