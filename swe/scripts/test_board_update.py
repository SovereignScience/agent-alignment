"""board_update.sh against two checkouts of one board, a bare remote and the real lattice command."""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

HERE = pathlib.Path(__file__).parent
BASH = shutil.which("bash")


@unittest.skipUnless(shutil.which("lattice"), "lattice is not installed")
class BoardUpdate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        home = pathlib.Path(self.tmp.name, "home")
        home.mkdir()
        (home / ".gitconfig").write_text("[user]\n\tname = Owner\n\temail = owner@example.com\n")
        self.env = dict(os.environ, HOME=str(home), LATTICE_NO_UPDATE_CHECK="1")
        self.env.pop("LATTICE_ROOT", None)
        self.remote = pathlib.Path(self.tmp.name, "board.git")
        self.run_in(self.tmp.name, "git", "init", "-q", "--bare", "-b", "main", str(self.remote))
        self.here, self.there = self.project("one"), self.project("two")
        for repo in (self.here, self.there):
            self.script("board_setup.sh", "--actor", "human:owner", "--remote", str(self.remote), cwd=repo)

    def project(self, parent):
        repo = pathlib.Path(self.tmp.name, parent, "demo-project")
        repo.mkdir(parents=True)
        self.run_in(repo, "git", "init", "-q", "-b", "main")
        (repo / "README.md").write_text("demo\n")
        self.run_in(repo, "git", "add", "README.md")
        self.run_in(repo, "git", "commit", "-q", "-m", "add readme")
        return repo

    def run_in(self, cwd, *command, check=True):
        run = subprocess.run(command, cwd=cwd, env=dict(self.env, LATTICE_ROOT=str(cwd)), capture_output=True,
                             text=True, timeout=120)
        if check and run.returncode:
            self.fail("%s: %s" % (" ".join(command), run.stdout + run.stderr))
        return run.returncode, run.stdout + run.stderr

    def script(self, name, *args, cwd, check=True):
        return self.run_in(cwd, BASH, str(HERE / name), *args, check=check)

    def head(self, where):
        return self.run_in(where, "git", "rev-parse", "HEAD" if where != self.remote else "main")[1].strip()

    def task(self, repo, title):
        self.run_in(repo, "lattice", "create", title, "--actor", "human:owner")

    def test_without_apply_it_says_what_is_behind_and_changes_no_file(self):
        self.task(self.here, "first")
        before = self.head(self.here / ".lattice")
        code, out = self.script("board_update.sh", cwd=self.here)
        self.assertEqual(code, 0, out)
        self.assertIn("unchanged  demo-project", out)
        self.assertRegex(out, r"to commit  [1-9]\d* board file")
        self.assertIn("to push    0 commit(s)", out)
        self.assertIn("healthy", out)
        self.assertEqual(self.head(self.here / ".lattice"), before)
        self.assertEqual(self.head(self.remote), before)

    def test_one_sides_work_reaches_the_remote_and_then_the_other_side(self):
        self.task(self.here, "first")
        code, out = self.script("board_update.sh", "--apply", cwd=self.here)
        self.assertEqual(code, 0, out)
        self.assertIn("DONE: the board is in step with its remote", out)
        self.assertEqual(self.head(self.remote), self.head(self.here / ".lattice"))
        self.script("board_update.sh", "--apply", cwd=self.there)
        self.assertEqual(self.head(self.there / ".lattice"), self.head(self.remote))
        self.assertIn("first", self.run_in(self.there, "lattice", "show", "DP-1")[1])

    def test_two_sides_that_wrote_the_same_task_are_merged_and_nothing_is_lost(self):
        self.task(self.here, "first")
        self.script("board_update.sh", "--apply", cwd=self.here)
        self.script("board_update.sh", "--apply", cwd=self.there)
        self.run_in(self.here, "lattice", "comment", "DP-1", "said here", "--actor", "human:owner")
        self.run_in(self.there, "lattice", "comment", "DP-1", "said there", "--actor", "human:owner")
        self.script("board_update.sh", "--apply", cwd=self.here)
        code, out = self.script("board_update.sh", "--apply", cwd=self.there)
        self.assertEqual(code, 0, out)
        self.script("board_update.sh", "--apply", cwd=self.here)
        for repo in (self.here, self.there):
            comments = self.run_in(repo, "lattice", "comments", "DP-1", "--json")[1]
            self.assertIn("said here", comments)
            self.assertIn("said there", comments)
            self.assertEqual(self.head(repo / ".lattice"), self.head(self.remote))
            self.assertEqual(self.run_in(repo / ".lattice", "git", "status", "--porcelain")[1], "")
        self.assertIn("merge the remote board", self.run_in(self.there / ".lattice", "git", "log", "--format=%s")[1])

    def test_two_sides_that_each_made_a_task_are_not_merged(self):
        self.task(self.here, "made here")
        self.task(self.there, "made there")
        self.script("board_update.sh", "--apply", cwd=self.here)
        pushed = self.head(self.remote)
        code, out = self.script("board_update.sh", "--apply", cwd=self.there, check=False)
        self.assertEqual(code, 1, out)
        self.assertRegex(out, r"changed on both sides; nothing was merged or pushed")
        self.assertEqual(self.head(self.remote), pushed)
        board = self.there / ".lattice"
        self.assertEqual(self.run_in(board, "git", "rev-parse", "-q", "--verify", "MERGE_HEAD", check=False)[0], 1)
        self.assertEqual(self.run_in(board, "git", "status", "--porcelain")[1], "")
        self.assertIn("made there", self.run_in(self.there, "lattice", "show", "DP-1")[1])

    def test_a_project_without_a_board_is_sent_to_the_setup_command(self):
        bare = self.project("three")
        code, out = self.script("board_update.sh", "--apply", cwd=bare, check=False)
        self.assertEqual(code, 1)
        self.assertIn("board_setup.sh makes one", out)


if __name__ == "__main__":
    unittest.main()
