"""merge_approved.py against a throwaway checkout, board and bare remote."""
import json
import tempfile
import unittest
from pathlib import Path

import lattice_review as lr
import merge_approved as ma
from test_lattice_review import commit, git, task


class MergeApproved(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.origin = Path(self.tmp.name, "origin.git")
        self.repo = Path(self.tmp.name, "repo")
        git(self.tmp.name, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(self.tmp.name, "init", "-q", "-b", "main", str(self.repo))
        git(self.repo, "config", "user.name", "t")
        git(self.repo, "config", "user.email", "t@example.invalid")
        (self.repo / ".lattice" / "tasks").mkdir(parents=True)
        (self.repo / ".lattice" / "config.json").write_text(json.dumps({"project_code": "T"}))
        (self.repo / ".gitignore").write_text(".lattice/\n")
        git(self.repo, "add", ".gitignore")
        self.start = commit(self.repo, "a", "init")
        git(self.repo, "remote", "add", "origin", str(self.origin))
        git(self.repo, "push", "-q", "origin", "main")
        self.one = self.branch("T-1", "feature/T-1-one", "one")
        self.two = self.branch("T-2", "feature/T-2-two", "two")
        self.reviews = {}
        self.said = []

    def branch(self, sid, name, file, content=None):
        git(self.repo, "checkout", "-q", "-b", name, "main")
        head = commit(self.repo, file, "feat: %s\n\nTask: %s" % (file, sid), content)
        git(self.repo, "checkout", "-q", "main")
        task(self.repo, sid, "in_review", file, branch=name)
        return head

    def approve(self, sid, base, head):
        self.reviews[sid] = [{"id": "ev_" + sid, "role": "review", "created_at": "2026-01-01T00:00:00Z", "author": "human:t",
                              "body": "Plannotator approved (patch x), s\n%s%s..%s\n\nfine\n" % (lr.REVIEWED, base, head)}]

    def run_merge(self, *sids, checks=("true",)):
        return ma.merge_approved(self.repo, self.repo, "main", sids, checks, lambda sid: self.reviews.get(sid, []),
                                 say=self.said.append)

    def remote_main(self):
        return git(self.origin, "rev-parse", "main")

    def local_main(self):
        return git(self.repo, "rev-parse", "main")

    def test_approved_branches_are_merged_in_order_checked_and_pushed(self):
        self.approve("T-1", self.start, self.one)
        self.approve("T-2", self.start, self.two)
        pushed = self.run_merge("T-1", "T-2", checks=("test -f one && test -f two",))
        self.assertEqual(self.remote_main(), pushed)
        self.assertEqual(self.local_main(), pushed)
        first, second = git(self.repo, "rev-list", "--first-parent", "--reverse", self.start + "..main").split()
        self.assertEqual(git(self.repo, "rev-list", "--parents", "-n", "1", first).split()[1:], [self.start, self.one])
        self.assertEqual(git(self.repo, "rev-list", "--parents", "-n", "1", second).split()[1:], [first, self.two])
        self.assertEqual(git(self.repo, "log", "-1", "--format=%B", first).strip(), "Merge branch 'feature/T-1-one'\n\nTask: T-1")
        self.assertIsNone(self.run_merge("T-1", "T-2"))

    def test_nothing_is_pushed_unless_the_owner_approved_exactly_what_would_land(self):
        with self.assertRaisesRegex(ma.Stop, "T-1 .* is not approved for merge: no Plannotator review"):
            self.run_merge("T-1")
        self.assertEqual(self.local_main(), self.start)
        self.approve("T-1", self.start, self.one)
        with self.assertRaisesRegex(ma.Stop, "T-2 .* is not approved for merge"):
            self.run_merge("T-1", "T-2")
        self.assertEqual(self.remote_main(), self.start)
        git(self.repo, "checkout", "-q", "feature/T-2-two")
        later = commit(self.repo, "late", "feat: late\n\nTask: T-2")
        git(self.repo, "checkout", "-q", "main")
        self.approve("T-2", self.start, self.two)
        with self.assertRaisesRegex(ma.Stop, "T-2 .*%s.* is not approved for merge: commits arrived after" % later[:12]):
            self.run_merge("T-1", "T-2")
        self.assertEqual(self.remote_main(), self.start)

    def test_a_failing_check_stops_before_the_push_and_takes_nothing_back(self):
        self.approve("T-1", self.start, self.one)
        with self.assertRaisesRegex(ma.Stop, "this check failed on the merged files: false"):
            self.run_merge("T-1", checks=("true", "false"))
        merged = self.local_main()
        self.assertEqual(git(self.repo, "rev-list", "--parents", "-n", "1", merged).split()[1:], [self.start, self.one])
        self.assertEqual(self.remote_main(), self.start)
        self.assertEqual(self.run_merge("T-1"), merged)
        self.assertEqual(self.remote_main(), merged)
        self.assertIn("T-1: merged here by an earlier run", self.said)

    def test_without_the_push_it_stops_after_the_checks_and_a_rerun_agrees(self):
        self.approve("T-1", self.start, self.one)
        merged = ma.merge_approved(self.repo, self.repo, "main", ["T-1"], ["true"], lambda sid: self.reviews.get(sid, []),
                                   say=self.said.append, push=False)
        self.assertEqual((self.local_main(), self.remote_main()), (merged, self.start))
        self.assertIn("merged and checked, not pushed: %s" % merged[:12], self.said)
        again = ma.merge_approved(self.repo, self.repo, "main", ["T-1"], ["true"], lambda sid: self.reviews.get(sid, []),
                                  say=self.said.append, push=False)
        self.assertEqual(again, merged)

    def test_an_unapproved_task_can_be_left_out_while_the_approved_ones_merge(self):
        self.approve("T-2", self.start, self.two)
        pushed = ma.merge_approved(self.repo, self.repo, "main", ["T-1", "T-2"], ["true"], lambda sid: self.reviews.get(sid, []),
                                   say=self.said.append, skip_unapproved=True)
        self.assertEqual(self.remote_main(), pushed)
        self.assertEqual(git(self.repo, "rev-list", "--parents", "-n", "1", pushed).split()[1:], [self.start, self.two])
        self.assertTrue(any(line.startswith("T-1: skipped, not approved: no Plannotator review") for line in self.said))
        self.assertEqual(git(self.repo, "rev-list", "--count", "main.." + self.one), "1")

    def test_a_rerun_refuses_a_local_commit_it_would_not_make(self):
        self.approve("T-1", self.start, self.one)
        git(self.repo, "merge", "-q", "--squash", self.one)
        git(self.repo, "commit", "-q", "-m", "feat: one, squashed")
        stray = self.local_main()
        with self.assertRaisesRegex(ma.Stop, "main has commit %s, which is not this run's merge of T-1" % stray[:12]):
            self.run_merge("T-1")
        self.assertEqual(self.remote_main(), self.start)

    def test_a_rerun_refuses_a_merge_with_the_right_parents_and_other_files(self):
        self.approve("T-1", self.start, self.one)
        git(self.repo, "merge", "-q", "--no-ff", "--no-commit", self.one)
        (self.repo / "extra").write_text("not reviewed\n")
        git(self.repo, "add", "extra")
        git(self.repo, "commit", "-q", "-m", "Merge branch 'feature/T-1-one'")
        with self.assertRaisesRegex(ma.Stop, "which is not this run's merge of T-1"):
            self.run_merge("T-1")
        self.assertEqual(self.remote_main(), self.start)

    def test_a_conflict_is_left_in_place_for_the_owner(self):
        clash = self.branch("T-3", "feature/T-3-clash", "one", "another one")
        self.approve("T-1", self.start, self.one)
        self.approve("T-3", self.start, clash)
        with self.assertRaisesRegex(ma.Stop, "merging T-3 did not finish(.|\n)*git merge --abort"):
            self.run_merge("T-1", "T-3")
        self.assertEqual(git(self.repo, "rev-parse", "MERGE_HEAD"), clash)
        self.assertEqual(self.remote_main(), self.start)
        with self.assertRaisesRegex(ma.Stop, "a merge is already in progress"):
            self.run_merge("T-1", "T-3")


if __name__ == "__main__":
    unittest.main()
