"""board_setup.sh against throwaway repositories, a bare remote and the real lattice command."""
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).with_name("board_setup.sh")
BASH = shutil.which("bash")


@unittest.skipUnless(shutil.which("lattice"), "lattice is not installed")
class BoardSetup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = pathlib.Path(self.tmp.name, "home")
        self.home.mkdir()
        (self.home / ".gitconfig").write_text("[user]\n\tname = Owner\n\temail = owner@example.com\n")
        self.env = dict(os.environ, HOME=str(self.home), LATTICE_NO_UPDATE_CHECK="1")
        self.env.pop("LATTICE_ROOT", None)
        self.repo = self.project("one")
        self.remote = pathlib.Path(self.tmp.name, "board.git")
        self.git("init", "-q", "--bare", "-b", "main", str(self.remote), cwd=self.tmp.name)

    def project(self, parent):
        repo = pathlib.Path(self.tmp.name, parent, "demo-project")
        repo.mkdir(parents=True)
        self.git("init", "-q", "-b", "main", cwd=repo)
        (repo / "README.md").write_text("demo\n")
        self.git("add", "README.md", cwd=repo)
        self.git("commit", "-q", "-m", "add readme", cwd=repo)
        return repo

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.repo, env=self.env, capture_output=True, text=True,
                              check=True).stdout.strip()

    def run_script(self, *args, cwd=None):
        run = subprocess.run([BASH, str(SCRIPT), *args], cwd=cwd or self.repo, env=self.env, capture_output=True,
                             text=True, timeout=120)
        return run.returncode, run.stdout + run.stderr

    def test_a_project_with_no_board_gets_one_and_no_tracked_file_changes(self):
        code, out = self.run_script("--actor", "human:owner")
        self.assertEqual(code, 0, out)
        config = json.loads((self.repo / ".lattice/config.json").read_text())
        self.assertRegex(out, r"READY: board DP \(demo-project\), review page port %d, new, remote none" % config["dashboard_port"])
        self.assertEqual((config["project_code"], config["default_actor"], config["plan_approval"]), ("DP", "human:owner", "human"))
        self.assertEqual((config["auto_code_review_on_transition"], config["auto_plan_review_on_transition"]), (False, False))
        context = (self.repo / ".lattice/context.md").read_text()
        self.assertTrue(context.startswith("# demo-project\n"))
        self.assertIn("Task: DP-<n>", context)
        self.assertIn("http://127.0.0.1:%d" % config["dashboard_port"], context)
        for left in ("<name>", "<project>", "<path>", "<CODE>", "<port>"):
            self.assertNotIn(left, context)
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual((self.repo / ".git/info/exclude").read_text().splitlines()[-2:], [".lattice/", "/.worktrees/"])
        board = self.repo / ".lattice"
        self.assertEqual(self.git("log", "--format=%an %s", cwd=board), "Owner chore(board): start the board")
        self.assertEqual(self.git("status", "--porcelain", cwd=board), "")
        self.assertIn("context.md", self.git("ls-files", cwd=board).splitlines())

    def test_a_project_that_has_a_board_is_refused_and_left_alone(self):
        self.assertEqual(self.run_script()[0], 0)
        before = self.git("rev-parse", "HEAD", cwd=self.repo / ".lattice")
        code, out = self.run_script()
        self.assertEqual(code, 1)
        self.assertIn("already has a board", out)
        self.assertEqual(self.git("rev-parse", "HEAD", cwd=self.repo / ".lattice"), before)

    def test_a_new_board_is_pushed_and_comes_back_in_another_checkout(self):
        code, out = self.run_script("--remote", str(self.remote))
        self.assertEqual(code, 0, out)
        pushed = self.git("rev-parse", "main", cwd=self.remote)
        self.assertEqual(pushed, self.git("rev-parse", "HEAD", cwd=self.repo / ".lattice"))
        other = self.project("two")
        code, out = self.run_script("--remote", str(self.remote), cwd=other)
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"READY: board DP \(demo-project\), review page port \d+, brought back, remote ")
        self.assertEqual(self.git("rev-parse", "HEAD", cwd=other / ".lattice"), pushed)
        self.assertEqual(self.git("log", "--oneline", cwd=other / ".lattice").count("\n"), 0)
        self.assertEqual(self.git("status", "--porcelain", cwd=other), "")

    def test_what_it_cannot_do_safely_is_refused_before_anything_is_made(self):
        (self.repo / "sub").mkdir()
        for args, cwd, said in ((("--actor", "agent:x"), None, "is a person"),
                                (("--remote", str(self.remote) + "-missing"), None, "cannot reach"),
                                (("--port", "1"), None, "unknown argument"),
                                ((), self.repo / "sub", "from the top of the repository")):
            code, out = self.run_script(*args, cwd=cwd)
            self.assertEqual(code, 1, out)
            self.assertIn(said, out)
            self.assertFalse((self.repo / ".lattice").exists(), out)


if __name__ == "__main__":
    unittest.main()
