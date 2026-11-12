#!/usr/bin/env python3
"""Merge task branches the owner approved into the integration branch, check, then push.

    python3 merge_approved.py --check '<command>' AA-7 [AA-8 ...]

The owner runs this in the main checkout. Each task's linked branch is
merged in the order given, with a merge commit, only while the owner's
latest review on that task approves exactly the commits about to land and
every review thread is resolved. Every commit the branch carries must name
its task in a Task trailer (a merge may name none), and a commit of another
task needs that task's own standing approval. Every --check command must
pass on the merged commit, in a temporary worktree, before the push.

Nothing is undone here. A stop leaves what was done in place, says where
things stand and prints the command that takes it back. A rerun continues
from there, and accepts a merge already on the local branch only when it is
the one this run would make: the same two parents and the same files.
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import lattice_review as lr


class Stop(Exception):
    """Why the run cannot go on. Nothing has been pushed when it is raised."""


def write_git(repo, *args):
    """A Git call that changes something. It runs with the checkout's own
    settings, so the push check and every other hook still run."""
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def run_checks(repo, commit, checks, say):
    """Run each check in a temporary worktree at the commit, so only committed
    files count. Raises Stop on the first failure."""
    tree = os.path.join(str(repo), ".worktrees", "check-" + commit[:12])
    if os.path.isdir(tree):
        write_git(repo, "worktree", "remove", "--force", tree)
    added = write_git(repo, "worktree", "add", "-q", "--force", "--detach", tree, commit)
    if added.returncode:
        raise Stop("could not make a worktree to run the checks in: %s" % added.stderr.strip())
    try:
        for command in checks:
            say("check: " + command)
            if subprocess.run(command, shell=True, cwd=tree, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1")).returncode:
                raise Stop("this check failed on %s: %s" % (commit[:12], command))
    finally:
        write_git(repo, "worktree", "remove", "--force", tree)


def merge_approved(repo, board, main, short_ids, checks, comments_of, say=print, push=True, skip_unapproved=False,
                   confirmed=None):
    """Merge, check and push. Returns the checked commit ID, or None when
    there was nothing to merge. Raises Stop before anything is pushed.
    With push off it stops after the checks. With skip_unapproved a task
    whose review does not cover its commits is left out, not a Stop, and so
    is every task whose branch contains that task's branch or any commit
    carrying that task's trailer, wherever it comes in the order: a yes on
    the outer branch must not carry in work that was not approved on its own
    task. Every commit a branch carries must name its task in a Task trailer
    (a merge may name none), and each named task must be approved for that
    commit, whether or not this run names it. With confirmed, a task this run
    names but the owner did not answer yes to in this run counts as not
    approved, whatever the board records."""
    def out(*args):
        return lr.run_git(repo, *args).strip()

    def inside(sha, ref):
        return lr.git_result(repo, ("merge-base", "--is-ancestor", sha, ref)).returncode == 0

    def clean():
        return not out("status", "--porcelain", "--untracked-files=no")

    if lr.current_branch(repo) != main:
        raise Stop("this checkout is on %s, not %s" % (lr.current_branch(repo), main))
    if lr.rev(repo, "MERGE_HEAD"):
        raise Stop("a merge is already in progress here. Take it back with: git merge --abort")
    if not clean():
        raise Stop("this checkout has uncommitted changes to tracked files")
    fetched = write_git(repo, "fetch", "origin", main)
    if fetched.returncode:
        raise Stop("could not fetch origin/%s: %s" % (main, fetched.stderr.strip()))
    start = lr.rev(repo, "refs/remotes/origin/" + main)
    if not inside(start, main):
        raise Stop("%s does not contain origin/%s; bring it up to date first" % (main, main))
    local = out("rev-list", "--first-parent", "--reverse", start + ".." + main).split()
    at = start
    tasks, notes, held, covered = {}, {}, {}, {}
    for sid in short_ids:
        tasks[sid] = lr.find_task(board, sid)
        if not tasks[sid]:
            raise Stop("%s is not on the board at %s" % (sid, board))
        notes[sid] = comments_of(sid)

    def declined(sid):
        return confirmed is not None and sid in tasks and sid not in confirmed

    def approves(other, sha):
        """Whether the task's own approval, still standing, covers the commit."""
        if other not in covered:
            found = tasks.get(other) or lr.find_task(board, other)
            covered[other] = lr.standing_approvals(repo, notes.get(other) or comments_of(other)) if found else set()
        return sha in covered[other]

    def foreign(sid, head):
        """Why work in at..head that is not sid's own cannot land with it, or None."""
        for sha, ids, merge in lr.range_owners(repo, at, head):
            if not ids:
                if merge:
                    continue
                return "commit %s carries no Task trailer, so whose work it is cannot be told" % sha[:12]
            for other in ids:
                if other == sid:
                    continue
                if other in held or declined(other):
                    return "its branch contains %s, which is not approved" % other
                if not approves(other, sha):
                    return "its branch contains commit %s of %s, which %s's own review does not cover" % (
                        sha[:12], other, other)
        return None

    for sid in short_ids:
        waiting = lr.resolve_range(repo, tasks[sid], start)
        if skip_unapproved and waiting["mode"] == "branch" and (
                declined(sid) or lr.review_block(repo, tasks[sid], start, notes[sid])):
            held[sid] = waiting["head_sha"]

    for sid in short_ids:
        task = tasks[sid]
        rng = lr.resolve_range(repo, task, at)
        if rng["mode"] != "branch":
            if not any(lr.rev(repo, link["branch"]) for link in task.get("branch_links", [])):
                raise Stop("%s has no linked branch in this repository" % sid)
            say("%s: already in %s" % (sid, main))
            continue
        head = rng["head_sha"]
        holds = [other for other, other_head in held.items() if other != sid and inside(other_head, head)]
        block = ("its branch contains %s, which is not approved" % ", ".join(holds) if holds
                 else "not answered yes in this run" if declined(sid)
                 else lr.review_block(repo, task, at, notes[sid]) or foreign(sid, head))
        if block and skip_unapproved:
            say("%s: skipped, %s%s" % (sid, "" if block.startswith(("its branch", "commit ")) else "not approved: ", block))
            held[sid] = head
            continue
        if block:
            raise Stop("%s (%s at %s) is not approved for merge: %s" % (sid, rng["branch"], head[:12], block))
        if local:
            found = local.pop(0)
            parents = out("rev-list", "--parents", "-n", "1", found).split()[1:]
            expected = lr.git_result(repo, ("merge-tree", "--write-tree", at, head)).stdout.split()
            if parents != [at, head] or expected[:1] != [out("rev-parse", found + "^{tree}")]:
                raise Stop("%s has commit %s, which is not this run's merge of %s" % (main, found[:12], sid))
            say("%s: merged here by an earlier run" % sid)
            at = found
            continue
        merged = write_git(repo, "merge", "--no-ff", "--no-edit", "-m",
                           "Merge branch '%s'\n\nTask: %s" % (rng["branch"], sid), head)
        if merged.returncode:
            raise Stop("merging %s did not finish:\n%s\nTake this one merge back with: git merge --abort"
                       % (sid, (merged.stdout + merged.stderr).strip()))
        at = lr.rev(repo, "HEAD")
        say("%s: merged %s at %s" % (sid, rng["branch"], head[:12]))

    if local:
        raise Stop("%s has %d commit(s) this run would not make, starting at %s" % (main, len(local), local[0][:12]))
    if at == start:
        say("nothing was merged: %s" % ("no task left is approved" if held else "every task is already in origin/%s" % main))
        return None
    run_checks(repo, at, checks, say)
    if not push:
        say("merged and checked, not pushed: %s" % at[:12])
        return at
    pushed = write_git(repo, "push", "origin", "%s:refs/heads/%s" % (at, main))
    if pushed.returncode:
        raise Stop("the push failed: %s" % pushed.stderr.strip())
    say("pushed %s to origin/%s" % (at[:12], main))
    return at


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--board", default=os.environ.get("LATTICE_ROOT", "."),
                        help="directory holding .lattice (default: LATTICE_ROOT, then cwd)")
    parser.add_argument("--repo", default=".", help="the main checkout to merge in (default: cwd)")
    parser.add_argument("--main", default="main", help="integration branch name")
    parser.add_argument("--check", action="append", required=True,
                        help="a shell command that must pass on the merged files before the push; repeat for more")
    parser.add_argument("--no-push", action="store_true", help="stop after the checks; the push stays with the owner")
    parser.add_argument("--skip-unapproved", action="store_true",
                        help="leave out a task whose review does not cover its commits, and go on")
    parser.add_argument("--confirmed", help="comma-separated task IDs the owner answered yes to in this run; "
                        "a named task not in it is left out, whatever the board records")
    parser.add_argument("--verify", metavar="REF", help="only run the checks at this commit, and merge nothing")
    parser.add_argument("tasks", nargs="*", help="task IDs, in merge order")
    args = parser.parse_args(argv)
    lattice = shutil.which("lattice")
    if not lattice:
        sys.exit("lattice is not on PATH")
    repo, board = Path(args.repo).resolve(), Path(args.board).resolve()
    if args.verify:
        commit = lr.rev(repo, args.verify)
        if not commit:
            sys.exit("merge_approved: %s is not a commit here" % args.verify)
        try:
            run_checks(repo, commit, args.check, print)
        except Stop as stop:
            print("STOPPED: %s" % stop)
            return 1
        print("every check passed at %s" % commit[:12])
        return 0
    if not args.tasks:
        parser.error("name at least one task, or use --verify")
    confirmed = None if args.confirmed is None else {sid.strip() for sid in args.confirmed.split(",") if sid.strip()}
    try:
        merge_approved(repo, board, args.main, args.tasks, args.check,
                       lambda sid: lr.task_comments(lattice, board, sid),
                       push=not args.no_push, skip_unapproved=args.skip_unapproved, confirmed=confirmed)
    except Stop as stop:
        print("STOPPED, nothing was pushed: %s" % stop)
        ahead = lr.run_git(repo, "rev-list", "--count", "origin/%s..%s" % (args.main, args.main), check=False).strip()
        if ahead.isdigit() and int(ahead):
            print("%s holds %s local commit(s) that are not pushed. A rerun continues from here. To take them back "
                  "instead, which discards them: git reset --hard %s"
                  % (args.main, ahead, lr.rev(repo, "refs/remotes/origin/" + args.main)))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
