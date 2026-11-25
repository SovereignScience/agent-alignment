---
status: proposed
date: 2026-11-24
applies-to:
  - swe/scripts/kit_pull.sh
  - swe/scripts/update_all.sh
  - swe/scripts/install_isolation.sh
  - swe/scripts/check_isolation.sh
  - swe/.claude/managed-settings.example.json
  - swe/.claude/settings.json
  - swe/codex/config.snippet.toml
  - swe/LATTICE_ONBOARDING.md
review-by: 2027-05-24
---

# ADR-0004: A project takes a signed release of the kit; nothing pushes the kit into projects

## Context

A project's sessions read the kit from a clone at `.agent-alignment`,
at the top of the project. Until now the owner brought projects up to
date with `swe/scripts/update_all.sh`, which loops over every repository
in the workspace with the owner's full rights, copies kit files in,
commits and pushes. It copies whatever is in the checkout it runs from.
Four audit rounds each found another way for it to write outside the
repository it meant to touch: links, predictable temporary names, merges,
inherited Git variables and branch setups. Each fix added a case to a
list, and a developer other than the owner had nothing to run.

Git can check who approved a commit without any new tool. A tag signed
with an SSH key is verified by `git verify-tag` against an allowed
signers file the verifier holds, and Git fails the check for any other
key.

- https://git-scm.com/docs/git-verify-tag
- https://git-scm.com/docs/git-config (`gpg.format`,
  `gpg.ssh.allowedSignersFile`, `gpg.program`, `gpg.x509.program`)
- https://man7.org/linux/man-pages/man1/ssh-keygen.1.html (ALLOWED
  SIGNERS)

## Decision

A kit is released as a Git tag that whoever runs the kit signs with an
SSH key in their own terminal. A release is named `v` and exactly three
numbers without leading zeros, such as `v1.2.0`, so no two names mean
the same release. The last number rises for a fix, the middle one for a
new rule or tool, and the first for a change that needs action in
projects.

A project is moved to a release by the person in that project, one
project at a time, with `swe/scripts/kit_pull.sh`. Git fetches one tag
and checks its signature before the clone is moved. The script names the
tag it verifies: the name inside the signed tag must be the name asked
for. A signature of any kind other than SSH does not pass. The script
reports where the clone is, where it would go and which files differ,
and with `--report` it stops there. It writes only inside
`.agent-alignment`, and never commits or pushes.

The release is named, or it is `latest`: the newest release the kit
lists, by number, verified like a named one. `latest` moves the clone
only when that release's commit descends from the commit the clone is
on, so a stale or hostile kit cannot move a project back. Going back, or
across to another line of history, is done by naming the release.

Who is trusted is one file on each developer's machine,
`~/.config/agent-alignment/allowed_signers`. It is outside every project
and is never read from a project or a clone. A developer fills it in one
of two ways. They take the kit owner's releases: the owner's public key
line and its fingerprint are printed in `swe/README.md`, and the same
key is listed on the owner's account at the hosting site. Or they run a
kit of their own, in a folder or anywhere else, and sign its releases
with their own key. No account and no service is needed for the second.
Their kit holds no release but their own, and their file lists only
their own key. Listing two keys means trusting both.

Sessions are meant not to write a project's clone. The managed settings
deny it to Claude Code's file tools in every checkout of the workspace,
with `Edit(~/projects/**/.agent-alignment/**)`, and the installer names
each clone it finds in a write denial for Claude Code and a read-only
entry for Codex. It does not look into the folders in the owner's skip
list, `~/.config/agent-alignment/skip`. `check_isolation.sh`, run by a
session in the project, is the check that this holds. The rule is
prepared and locally tested. It had not been seen to hold in a live
session when this record was written.

`update_all.sh` is deprecated. It stays in the kit, says so when it
runs, and is no longer the way a project gets an update.

## Rejected options

- Keep pushing from one script and harden it further. The risk comes
  from the shape: one run, many repositories, the owner's rights. Each
  audit found a new case.
- Taking whatever the server lists as newest, with no floor. A stale or
  hostile server could then move a project back to an older signed
  release.
- A floor kept as a release name recorded in the clone. It needed a
  record at every move and got stuck where one was missing. The commit
  history already says what is ahead.
- One machine-wide rule for the folder name in the Codex profile. Codex
  cannot hold a rule for a path that does not exist, and most projects
  have no clone.
- Release names made from the date. A number says what kind of change a
  release is; a date does not.
- The owner handing the key line to each developer. It puts a person in
  the way of every new user, and of anyone who wants their own kit.
- A submodule pinned to a commit. It adds a tracked link to every
  project, some owned by others, and records a commit, not a signed tag.
- A package, a template tool or an update bot. Each adds a tool or an
  account to trust for a kit that has no build.
- A Claude Code plugin pinned by commit. It carries agents and commands
  only, renames every command, and does nothing for Codex, Git hooks or
  the board.
- The "Verified" badge on the hosting site, or build attestations.
  Nothing on the developer's machine checks the first, and the second
  proves where a file was built, not who approved it.
- Reading the allowed signers file from the kit or the project. Whoever
  can write that copy would choose who is trusted.

## Consequences

- A release is a deliberate act by whoever runs the kit, and a server
  that hosts the kit is not trusted for its content.
- A developer who runs their own kit trusts only themselves. One who
  takes the owner's releases reads the key from the README, which the
  same server hosts, so the first time the key has to be found in a
  second place as well: the owner's list of signing keys at the hosting
  site, with the owner's account confirmed outside the repository, since
  a change to the repository could alter the key and the account name
  together.
- `latest` cannot tell when a server hides a newer release. It can only
  refuse to go back.
- A clone added to a project is writable by sessions until the installer
  has run again and named it.
- Each clone the installer names becomes readable to every Codex session
  on the machine, whichever project that session is opened in. What a
  clone holds is the kit, which is public, or the developer's own copy
  of it. A folder in the skip list is never looked into, so a clone
  inside one is never named and stays writable.
- A lost or leaked key means every developer replaces one line. There is
  no revocation list.
- The first clone in a project is checked by hand, because a new clone
  cannot be trusted to check itself.
- The pull runs a script and Git settings read from the clone, so its
  checks hold only where sessions cannot write the clone.
- Files copied into a project earlier, such as Git hooks, are not
  refreshed by a pull.
- A tag the owner signed in another repository under the same name and
  key would also pass.

## Confirmation

`swe/scripts/test_kit_pull.py` passes: it signs tags with throwaway keys
and shows each refusal, and it runs the guide's first-run, release and
own-kit commands as printed. In a project that has a clone, a fresh
session of each client runs `check_isolation.sh` from the clone and it
prints `ok    the kit clone is not writable`.
