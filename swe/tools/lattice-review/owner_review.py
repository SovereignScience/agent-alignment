#!/usr/bin/env python3
"""Approve, evidence and close tasks from the terminal, as the owner.

    owner_review.py approve  --actor human:<name> AA-7 [AA-8 ...]
    owner_review.py evidence --actor human:<name> --note "<what ran and passed>" AA-7:AC-4 [...]
    owner_review.py close    --actor human:<name> AA-7 [AA-8 ...]
    owner_review.py summary  AA-7 [AA-8 ...]
    owner_review.py branches AA-7 [AA-8 ...]

Run it yourself; it writes to the board as a person. approve shows each
task's exact head commit and a one-line summary, names the other tasks of
the batch that its branch holds, asks y or n (d lists the commits and files
first), and records a yes as a review bound to those commits, in the form the review section and
merge_approved.py read. An open review thread is shown first and can be
resolved there; a task with a thread left open is not approved. evidence
records the note on each named criterion that has none yet, once the task
is in the pushed integration branch. close marks done
every task the review section would let you mark done, and says why for the
rest; where a task's flag still asks you something it shows the flag and
closes the task only if you clear it there. summary says where each task stands, and branches prints each task's
linked branch.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import lattice_review as lr


class Board:
    def __init__(self, repo, board, main, lattice, actor=None):
        self.repo, self.board, self.main, self.lattice, self.actor = repo, board, main, lattice, actor

    def task(self, sid):
        task = lr.find_task(self.board, sid)
        if not task:
            sys.exit("owner_review: %s is not on the board at %s" % (sid, self.board))
        return task

    def comments(self, sid):
        return lr.task_comments(self.lattice, self.board, sid)

    def write(self, *args):
        env = dict(os.environ, LATTICE_NO_UPDATE_CHECK="1", LATTICE_ROOT=str(self.board))
        done = subprocess.run([self.lattice, *args, "--actor", self.actor], cwd=self.board, env=env,
                              capture_output=True, text=True)
        if done.returncode:
            sys.exit("owner_review: lattice %s failed: %s" % (args[0], (done.stdout + done.stderr).strip()))


def first_line(text):
    return next((line.strip() for line in (text or "").splitlines() if line.strip()), "")


def approve(board, sids, ask=input, say=print):
    """Ask about each task in turn. Returns the IDs approved in this run."""
    approved = []
    heads = {}
    for sid in sids:
        waiting = lr.resolve_range(board.repo, board.task(sid), board.main)
        if waiting["mode"] == "branch":
            heads[sid] = waiting["head_sha"]

    def contains(outer, inner):
        return lr.git_result(board.repo, ("merge-base", "--is-ancestor", heads[inner], heads[outer])).returncode == 0

    for sid in sids:
        task = board.task(sid)
        rng = lr.resolve_range(board.repo, task, board.main)
        if rng["mode"] != "branch":
            say("%s: nothing to approve, its linked branch has no commits past %s" % (sid, board.main))
            continue
        if lr.review_block(board.repo, task, board.main, board.comments(sid)) is None:
            say("%s: already approved at %s" % (sid, rng["head_sha"][:12]))
            continue
        try:
            for thread in lr.review_threads(board.comments(sid)):
                if thread["state"] == "resolved":
                    continue
                last = thread["messages"][-1] if thread["messages"] else {}
                say("%s has an open thread (%s) on %s" % (sid, thread["state"], thread["anchor"]))
                say("    note: %s" % first_line("\n".join(l for l in thread["note"].splitlines() if not l.startswith("> "))))
                say("    last word, %s: %s" % (last.get("author") or "nobody", first_line(last.get("body"))))
                if ask("    Resolve this thread? [y/N] ").strip().lower() == "y":
                    board.write("react", sid, thread["root"]["id"], lr.RESOLVED)
            left = [t for t in lr.review_threads(board.comments(sid)) if t["state"] != "resolved"]
            if left:
                say("%s: not approved, %d thread(s) still open" % (sid, len(left)))
                continue
            stat = first_line(lr.run_git(board.repo, "diff", "--shortstat", rng["base_sha"], rng["head_sha"]))
            say("%s  %s  %s" % (sid, rng["head_sha"], task.get("title") or ""))
            say("    %d commit(s) past %s; %s" % (len(rng["commits"]), board.main, stat or "no file changed"))
            others = [other for other in sids if other != sid and other in heads]
            carried = lr.carried_tasks(board.repo, rng["base_sha"], rng["head_sha"], others)
            inner = [other for other in others if other in carried or contains(sid, other)]
            if inner:
                say("    its branch also holds %d other task(s) of this batch: %s" % (len(inner), " ".join(inner)))
                say("    a yes here approves their commits too")
                waiting = [other for other in inner
                           if lr.review_block(board.repo, board.task(other), board.main, board.comments(other))]
                if waiting:
                    say("    not approved themselves: %s; this task is not merged until they are" % " ".join(waiting))
            answer = "d"
            while answer == "d":
                answer = ask("    Approve %s at %s? [y/N/d for the commits and files/q] " % (sid, rng["head_sha"][:12])).strip().lower()
                if answer == "d":
                    span = "%s..%s" % (rng["base_sha"], rng["head_sha"])
                    say(lr.run_git(board.repo, "log", "--oneline", "--no-merges", span).rstrip())
                    say(lr.run_git(board.repo, "diff", "--stat", rng["base_sha"], rng["head_sha"]).rstrip())
        except EOFError:
            say("no more answers; the remaining tasks were not asked about")
            break
        if answer == "q":
            break
        if answer != "y":
            say("%s: not approved" % sid)
            continue
        body = "Owner approved (terminal, patch %s..%s), %s\n%s%s..%s\n\nApproved from the terminal.\n" % (
            rng["base_sha"][:12], rng["head_sha"][:12], time.strftime("%Y-%m-%d %H:%M:%S"),
            lr.REVIEWED, rng["base_sha"], rng["head_sha"])
        with tempfile.NamedTemporaryFile("w", suffix=".md") as note:
            note.write(body)
            note.flush()
            board.write("comment", sid, "--file", note.name, "--role", "review")
        say("%s: approved at %s" % (sid, rng["head_sha"][:12]))
        approved.append(sid)
    return approved


def evidence(board, pairs, note, say=print):
    for pair in pairs:
        sid, _, criterion = pair.partition(":")
        task = board.task(sid)
        if criterion not in {c["id"] for c in task.get("acceptance_criteria", [])}:
            sys.exit("owner_review: %s has no criterion %s" % (sid, criterion))
        if any(criterion in (ref.get("criterion_ids") or []) for ref in task.get("evidence_refs", [])):
            say("%s %s: already has evidence" % (sid, criterion))
            continue
        if lr.resolve_range(board.repo, task, "refs/remotes/origin/" + board.main)["mode"] == "branch":
            say("%s %s: not recorded, the task is not in origin/%s yet" % (sid, criterion, board.main))
            continue
        board.write("comment", sid, note, "--role", "validation", "--criterion", criterion)
        say("%s %s: evidence recorded" % (sid, criterion))


def close(board, sids, ask=input, say=print):
    """Mark done what the review section would allow. A task whose flag still
    asks the owner something is closed only if the owner clears the flag
    here. Returns the IDs closed."""
    closed = []
    for sid in sids:
        task = board.task(sid)
        if task.get("status") == "done":
            continue
        block = lr.completion_block(board.repo, task, board.main, board.comments(sid))
        if block:
            say("%s: left open: %s" % (sid, block))
            continue
        flag = (task.get("needs_human") or {}).get("reason")
        if flag:
            say("%s is ready to close, and its flag still asks: %s" % (sid, flag))
            try:
                answer = ask("    Clear that flag and close %s? [y/N] " % sid).strip().lower()
            except EOFError:
                answer = ""
            if answer != "y":
                say("%s: left open: its flag is not cleared" % sid)
                continue
            board.write("needs-human", sid, "--clear", "--note", "Cleared by the owner in the terminal when closing the task.")
        board.write("status", sid, "done", "--no-auto-review")
        say("%s: closed" % sid)
        closed.append(sid)
    return closed


def summary(board, sids, say=print):
    """Where each task stands. Returns the IDs that are not done."""
    groups = {"merged": [], "skipped": [], "closed": [], "still open": []}
    reasons = {}
    for sid in sids:
        task = board.task(sid)
        waiting = lr.resolve_range(board.repo, task, "refs/remotes/origin/" + board.main)["mode"] == "branch"
        groups["skipped" if waiting else "merged"].append(sid)
        if task.get("status") == "done":
            groups["closed"].append(sid)
        else:
            groups["still open"].append(sid)
            reasons[sid] = (lr.completion_block(board.repo, task, board.main, board.comments(sid))
                            or ("its flag is not cleared: %s" % task["needs_human"]["reason"] if task.get("needs_human") else "ready to close"))
    for name in ("merged", "skipped", "closed", "still open"):
        say("%-10s %2d  %s" % (name, len(groups[name]), " ".join(groups[name])))
    for sid in groups["still open"]:
        say("    %s: %s" % (sid, reasons[sid]))
    return groups["still open"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("approve", "evidence", "close", "summary", "branches"))
    parser.add_argument("--board", default=os.environ.get("LATTICE_ROOT", "."),
                        help="directory holding .lattice (default: LATTICE_ROOT, then cwd)")
    parser.add_argument("--repo", default=".", help="the main checkout (default: cwd)")
    parser.add_argument("--main", default="main", help="integration branch name")
    parser.add_argument("--actor", help="the person writing, human:<name>; needed by approve, evidence and close")
    parser.add_argument("--note", help="the evidence text, for evidence")
    parser.add_argument("items", nargs="+", help="task IDs, or <ID>:<criterion> pairs for evidence")
    args = parser.parse_args(argv)
    lattice = shutil.which("lattice")
    if not lattice:
        sys.exit("owner_review: lattice is not on PATH")
    writes = args.action in ("approve", "evidence", "close")
    if writes and not (args.actor or "").startswith("human:"):
        sys.exit("owner_review: --actor must be a person, human:<name>")
    board = Board(Path(args.repo).resolve(), Path(args.board).resolve(), args.main, lattice, args.actor)
    if args.action == "approve":
        approve(board, args.items)
    elif args.action == "evidence":
        if not args.note:
            sys.exit("owner_review: evidence needs --note")
        evidence(board, args.items, args.note)
    elif args.action == "close":
        close(board, args.items)
    elif args.action == "summary":
        summary(board, args.items)
    else:
        for sid in args.items:
            links = [link["branch"] for link in board.task(sid).get("branch_links", [])]
            if not links:
                sys.exit("owner_review: %s has no linked branch" % sid)
            print(sid, links[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
