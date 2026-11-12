---
description: Run the Skeptic-Arbiter pair over a code change. code-skeptic flags hollow approvals, missing specificity, hedge-burial, sycophancy spirals, and unverified completion claims about the change; code-arbiter writes the verdict from the change and the flags. Reviews the change itself, never a draft review of it.
argument-hint: "[base-branch]"
allowed-tools: Bash, Read, Agent
model: inherit
---

Run the Skeptic-Arbiter pair over the current branch against `$1`.
The base branch defaults to `main`. The input is the change itself,
never a draft review of it.

Capture what is under review first:

```bash
git rev-parse "${1:-main}" HEAD
git diff "${1:-main}"...HEAD --stat
git diff HEAD --stat
git ls-files --others --exclude-standard
```

That is the boundary, not the content. The reviewer reads the diff
itself, file by file; a whole diff pasted into this chat or into a brief
crowds out the lines that matter. Include committed and uncommitted
changes when they are in the requested scope, and name the untracked
source files, leaving out credentials and generated binaries. State the
base, HEAD and working-tree boundary; an empty committed diff does not
establish that prepared work is empty.

Steps:

1. Spawn `code-skeptic`. Open the brief with these tags, defined in
   `code-reviewer` under Inputs, and put prior turns of this review in
   `<author_claims>`:

   ```text
   <revisions>base <sha>, head <sha>; uncommitted: yes or no; untracked: <files or none></revisions>
   <request><what the owner asked for, in the owner's words where you have them></request>
   <acceptance_criteria><the task's criteria, one per line, or "none given"></acceptance_criteria>
   <author_claims><the author's summary, validation results and known limits, or "none"></author_claims>
   Read the change and return your flag list per the format defined in
   your agent definition. SILENT if no flags fire.
   ```
2. Spawn `code-arbiter` with the same tagged block and the flag list (or
   `SILENT`). Brief: "produce the final verdict on the change,
   calibrated to flag severity. Cite file:line evidence, name
   severity, no hedge-burial."
3. Output to the user: the Skeptic flag list, then the Arbiter's
   verdict.

Do not modify any file in the repo.
