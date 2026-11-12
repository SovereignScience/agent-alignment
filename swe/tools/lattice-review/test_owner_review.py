"""owner_review.py against a throwaway checkout, a bare remote and a board made by the real lattice command."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import lattice_review as lr
import merge_approved as ma
import owner_review as orv

LATTICE = shutil.which("lattice")


@unittest.skipUnless(LATTICE, "lattice is not installed")
class OwnerReview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        home = Path(self.tmp.name, "home")
        home.mkdir()
        (home / ".gitconfig").write_text("[user]\n\tname = Owner\n\temail = owner@example.com\n")
        patch = {"HOME": str(home), "LATTICE_NO_UPDATE_CHECK": "1"}
        saved = {key: os.environ.get(key) for key in list(patch) + ["LATTICE_ROOT"]}
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v) for k, v in saved.items()])
        os.environ.update(patch)
        os.environ.pop("LATTICE_ROOT", None)
        self.origin = Path(self.tmp.name, "origin.git")
        self.repo = Path(self.tmp.name, "repo")
        self.run_in(self.tmp.name, "git", "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.run_in(self.tmp.name, "git", "init", "-q", "-b", "main", str(self.repo))
        (self.repo / ".gitignore").write_text(".lattice/\n")
        self.commit("a", "init")
        self.git("remote", "add", "origin", str(self.origin))
        self.git("push", "-q", "-u", "origin", "main")
        self.lattice("init", "--path", ".", "--project-code", "T", "--project-name", "t", "--preset", "linear",
                     "--workflow", "classic", "--review-mode", "inline", "--plan-review-mode", "inline",
                     "--plan-approval", "human", "--done-display", "all", "--no-seed", "--no-setup-claude",
                     "--no-setup-agents", "--description", "test board")
        self.lattice("create", "first task")
        self.git("checkout", "-q", "-b", "feature/T-1-first")
        self.head = self.commit("one", "feat: one\n\nTask: T-1")
        self.git("checkout", "-q", "main")
        self.lattice("branch-link", "T-1", "feature/T-1-first")
        for status in ("todo", "in_progress", "in_review"):
            self.lattice("status", "T-1", status, "--no-auto-review")
        self.board = orv.Board(self.repo, self.repo, "main", LATTICE, "human:owner")
        self.said = []

    def run_in(self, cwd, *command):
        done = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, "%s: %s" % (" ".join(command), done.stdout + done.stderr))
        return done.stdout.strip()

    def git(self, *args):
        return self.run_in(self.repo, "git", *args)

    def lattice(self, *args):
        return self.run_in(self.repo, LATTICE, *args, "--actor", "human:owner")

    def commit(self, name, message):
        (self.repo / name).write_text(name + "\n")
        self.git("add", name)
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def approve(self, *answers):
        left = list(answers)

        def ask(prompt):
            self.said.append(prompt)
            if not left:
                raise EOFError
            return left.pop(0)
        return orv.approve(self.board, ["T-1"], ask=ask, say=self.said.append)

    def blocked(self):
        return lr.review_block(self.repo, lr.find_task(self.repo, "T-1"), "main", self.board.comments("T-1"))

    def status(self):
        return lr.find_task(self.repo, "T-1")["status"]

    def merge(self):
        return ma.merge_approved(self.repo, self.repo, "main", ["T-1"], ["true"], self.board.comments, say=self.said.append)

    def test_a_yes_is_recorded_against_the_exact_commit_and_lets_the_task_merge_and_close(self):
        self.assertEqual(self.approve("y"), ["T-1"])
        self.assertTrue(any(self.head in line and "first task" in line for line in self.said), self.said)
        review = lr.latest_review(self.board.comments("T-1"))
        self.assertEqual((review["author"], lr.review_decision(review["body"])), ("human:owner", "approved"))
        self.assertEqual(lr.reviewed_revision(review["body"])[1], self.head)
        self.assertTrue(review["body"].startswith("Owner approved (terminal, "))
        self.assertIsNone(self.blocked())
        self.assertEqual(self.approve(), [])
        self.assertIn("T-1: already approved at %s" % self.head[:12], self.said)
        self.merge()
        self.assertEqual(orv.close(self.board, ["T-1"], say=self.said.append), ["T-1"])
        self.assertEqual(self.status(), "done")
        self.assertEqual(orv.summary(self.board, ["T-1"], say=self.said.append), [])

    def test_a_no_or_no_answer_records_nothing(self):
        self.assertEqual(self.approve("n"), [])
        self.assertEqual(self.approve(), [])
        self.assertIsNone(lr.latest_review(self.board.comments("T-1")))
        with self.assertRaisesRegex(ma.Stop, "not approved for merge"):
            self.merge()

    def test_a_commit_after_the_yes_needs_a_new_yes(self):
        self.approve("y")
        self.git("checkout", "-q", "feature/T-1-first")
        later = self.commit("late", "feat: late\n\nTask: T-1")
        self.git("checkout", "-q", "main")
        self.assertIn("commits arrived after your review", self.blocked())
        self.assertEqual(self.approve("y"), ["T-1"])
        self.assertEqual(lr.reviewed_revision(lr.latest_review(self.board.comments("T-1"))["body"])[1], later)

    def test_an_open_thread_is_shown_and_blocks_the_yes_until_it_is_resolved(self):
        self.lattice("comment", "T-1", "%sone, line 1 (new) at %s\n> one\nrename this" % (lr.THREAD, self.head[:12]))
        self.assertEqual(self.approve("n"), [])
        self.assertIn("T-1: not approved, 1 thread(s) still open", self.said)
        self.assertTrue(any("rename this" in line for line in self.said))
        self.assertEqual(self.approve("y", "y"), ["T-1"])
        self.assertIsNone(self.blocked())

    def test_a_task_with_a_criterion_closes_only_once_it_has_evidence(self):
        self.lattice("criterion", "add", "T-1", "The checks pass on the integration branch after the merge.")
        self.approve("y")
        orv.evidence(self.board, ["T-1:AC-1"], "Met: too early.", say=self.said.append)
        self.assertIn("T-1 AC-1: not recorded, the task is not in origin/main yet", self.said)
        self.merge()
        self.assertEqual(orv.close(self.board, ["T-1"], say=self.said.append), [])
        self.assertTrue(any("left open: no evidence is recorded yet for AC-1" in line for line in self.said), self.said)
        self.assertEqual(orv.summary(self.board, ["T-1"], say=self.said.append), ["T-1"])
        orv.evidence(self.board, ["T-1:AC-1"], "Met: the checks passed on main.", say=self.said.append)
        orv.evidence(self.board, ["T-1:AC-1"], "Met: the checks passed on main.", say=self.said.append)
        self.assertIn("T-1 AC-1: already has evidence", self.said)
        notes = [c for c in self.board.comments("T-1") if c.get("role") == "validation"]
        self.assertEqual(len(notes), 1)
        self.assertEqual(orv.close(self.board, ["T-1"], say=self.said.append), ["T-1"])
        self.assertEqual(self.status(), "done")

    def test_a_task_whose_flag_still_asks_something_closes_only_when_the_owner_clears_it(self):
        self.run_in(self.repo, LATTICE, "needs-human", "T-1", "Need: decide the name", "--actor", "agent:x")
        self.approve("y")
        self.merge()
        answers = iter(["n", "y"])
        for expected in ([], ["T-1"]):
            self.assertEqual(orv.close(self.board, ["T-1"], ask=lambda prompt: next(answers), say=self.said.append), expected)
        self.assertTrue(any("its flag still asks: Need: decide the name" in line for line in self.said), self.said)
        self.assertIn("T-1: left open: its flag is not cleared", self.said)
        self.assertEqual(self.status(), "done")
        self.assertFalse(lr.find_task(self.repo, "T-1").get("needs_human"))


if __name__ == "__main__":
    unittest.main()
