---
description: Run the Skeptic-Arbiter pair over a code change. code-skeptic flags hollow approvals, missing specificity, hedge-burial, sycophancy spirals, and unverified completion claims about the change; code-arbiter writes the verdict from the change and the flags. Reviews the change itself, never a draft review of it.
argument-hint: "[base-branch]"
allowed-tools: Bash, Read, Agent
model: inherit
---

Run the Skeptic-Arbiter pair over the current branch against `$1`.
The base branch defaults to `main`. The input is the change itself,
never a draft review of it.

Capture the diff first:

```bash
git diff "${1:-main}"...HEAD --stat
git diff "${1:-main}"...HEAD
git diff HEAD --stat
git diff HEAD
git ls-files --others --exclude-standard
```

Include committed and uncommitted changes when they are in the requested
scope. Read the listed untracked source files without opening credentials
or generated binaries. State the base, HEAD and working-tree boundary;
an empty committed diff does not establish that prepared work is empty.

Steps:

1. Spawn `code-skeptic` with the diff and any visible context (the
   original request, prior turns of this review). Brief: "read the
   change and return your flag list per the format defined in your
   agent definition. SILENT if no flags fire."
2. Spawn `code-arbiter` with the diff and the flag list (or
   `SILENT`). Brief: "produce the final verdict on the change,
   calibrated to flag severity. Cite file:line evidence, name
   severity, no hedge-burial."
3. Output to the user: the Skeptic flag list, then the Arbiter's
   verdict.

Do not modify any file in the repo.
