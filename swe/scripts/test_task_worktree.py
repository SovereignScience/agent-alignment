"""task_worktree.sh against a throwaway repository."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).with_name("task_worktree.sh")
BASH = shutil.which("bash")


class TaskWorktree(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = pathlib.Path(self.tmp.name, "repo")
        self.repo.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Owner")
        self.git("config", "user.email", "owner@example.com")
        self.commit(self.repo, "base")

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.repo, capture_output=True, text=True,
                              check=True).stdout.strip()

    def commit(self, where, name):
        (where / name).write_text(name)
        self.git("add", name, cwd=where)
        self.git("commit", "-q", "-m", "add " + name, cwd=where)

    def run_script(self, *args):
        run = subprocess.run([BASH, str(SCRIPT), *args], cwd=self.repo, capture_output=True, text=True,
                             timeout=60)
        return run.returncode, run.stdout + run.stderr

    def tree(self, name):
        return self.repo / ".worktrees" / name

    def test_add_makes_one_worktree_on_the_task_branch(self):
        code, out = self.run_script("add", "AA-7", "fix-empty-input")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "HEAD", cwd=self.tree("AA-7")),
                         "feature/AA-7-fix-empty-input")
        self.assertIn("/.worktrees/", (self.repo / ".git/info/exclude").read_text().splitlines())
        self.assertIn("lattice branch-link AA-7 feature/AA-7-fix-empty-input", out)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_candidates_start_from_the_same_commit(self):
        code, out = self.run_script("add", "AA-7", "fix-empty-input", "--candidates", "3")
        self.assertEqual(code, 0, out)
        heads = {self.git("rev-parse", "HEAD", cwd=self.tree("AA-7-" + letter)) for letter in "abc"}
        self.assertEqual(heads, {self.git("rev-parse", "main")})
        self.assertFalse(self.tree("AA-7").exists())
        self.assertIn("Link only the branch you pick", out)

    def test_bad_input_is_refused_before_anything_is_made(self):
        for args in (("add", "aa-7", "x"), ("add", "AA-7", "Bad Slug"), ("add", "AA-7", "x", "--candidates", "4"),
                     ("add", "AA-7", "x", "--base", "missing"), ("remove", "AA-7"), ("prune", "AA-7")):
            with self.subTest(args=args):
                code, _ = self.run_script(*args)
                self.assertNotEqual(code, 0)
                self.assertFalse((self.repo / ".worktrees").exists())

    def test_remove_previews_then_clears_only_what_is_safe(self):
        self.run_script("add", "AA-7", "x", "--candidates", "3")
        self.run_script("add", "AA-70", "other")
        self.commit(self.tree("AA-7-a"), "picked")
        self.commit(self.tree("AA-7-b"), "not-picked")
        (self.tree("AA-7-c") / "draft").write_text("unsaved")
        self.git("merge", "-q", "--no-ff", "-m", "merge", "feature/AA-7-x-a")

        code, out = self.run_script("remove", "AA-7")
        self.assertEqual(code, 0, out)
        self.assertIn("Nothing changed", out)
        self.assertTrue(self.tree("AA-7-a").exists())

        code, out = self.run_script("remove", "AA-7", "--apply")
        self.assertEqual(code, 0, out)
        self.assertFalse(self.tree("AA-7-a").exists())
        self.assertIn("not merged into main", out)
        self.assertIn("uncommitted changes", out)
        self.assertTrue(self.tree("AA-7-b").exists())
        self.assertTrue(self.tree("AA-7-c").exists())

        code, out = self.run_script("remove", "AA-7", "--drop-unmerged", "--apply")
        self.assertEqual(code, 0, out)
        self.assertFalse(self.tree("AA-7-b").exists())
        self.assertTrue(self.tree("AA-7-c").exists())
        branches = self.git("branch", "--format=%(refname:short)").split()
        self.assertEqual(sorted(branches), ["feature/AA-7-x-c", "feature/AA-70-other", "main"])
        self.assertTrue(self.tree("AA-70").exists())

    def test_remove_leaves_a_folder_that_is_a_link(self):
        outside = pathlib.Path(self.tmp.name, "outside")
        self.git("worktree", "add", "-q", str(outside), "-b", "production")
        self.tree("AA-8").parent.mkdir()
        self.tree("AA-8").symlink_to(outside)

        code, out = self.run_script("remove", "AA-8", "--drop-unmerged", "--apply")
        self.assertEqual(code, 0, out)
        self.assertIn("a link to another folder", out)
        self.assertTrue(outside.exists())
        self.assertIn("production", self.git("branch", "--format=%(refname:short)").split())

    def test_remove_keeps_a_worktree_on_a_branch_of_another_task(self):
        self.run_script("add", "AA-8", "x")
        self.run_script("add", "AA-9", "y")
        self.commit(self.tree("AA-9"), "unmerged")
        self.git("switch", "-q", "--detach", cwd=self.tree("AA-9"))
        self.git("switch", "-q", "feature/AA-9-y", cwd=self.tree("AA-8"))

        code, out = self.run_script("remove", "AA-8", "--drop-unmerged", "--apply")
        self.assertEqual(code, 0, out)
        self.assertIn("not a branch of AA-8", out)
        self.assertIn("feature/AA-9-y", self.git("branch", "--format=%(refname:short)").split())


if __name__ == "__main__":
    unittest.main()
