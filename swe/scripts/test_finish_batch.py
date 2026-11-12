"""finish_batch.sh in a throwaway copy of the kit's layout: a main checkout with a
bare remote, a board with its own bare remote made by the real lattice command,
the real review tools, and stand-ins for the installer and the board update."""
import fcntl
import json
import os
import pathlib
import pty
import shutil
import subprocess
import tempfile
import termios
import unittest

SWE = pathlib.Path(__file__).resolve().parents[1]
BASH = shutil.which("bash")
LATTICE = shutil.which("lattice")
SUITES = ("swe/.claude/scripts", "swe/scripts", "swe/tools/lattice-review", "flourishing/.claude/scripts")
PASSES = "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_it(self):\n        pass\n"
NEEDS_LATTICE = "import importlib.util\n" + PASSES.replace(
    "class", "@unittest.skipUnless(importlib.util.find_spec('lattice'), 'lattice not importable')\nclass")
INSTALLER = """#!/usr/bin/env bash
case $1 in
    status)
        [ "$2" = --exit-code ] || exit 64
        [ ! -f "$HOME/blocked" ] || { echo "collision in the rules"; exit 2; }
        [ -f "$HOME/installed" ] || { echo "would install the hooks"; exit 3; } ;;
    apply) touch "$HOME/installed" ;;
esac
"""
BOARD_UPDATE = """#!/usr/bin/env bash
echo "$PWD $*" >> "$HOME/board_update.log"
[ "$(basename "$PWD")" != broken ] || exit 1
"""


@unittest.skipUnless(LATTICE, "lattice is not installed")
class FinishBatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        top = pathlib.Path(self.tmp.name)
        self.home = top / "home"
        self.home.mkdir()
        (self.home / ".gitconfig").write_text("[user]\n\tname = Owner\n\temail = owner@example.com\n")
        self.env = dict(os.environ, HOME=str(self.home), LATTICE_NO_UPDATE_CHECK="1")
        self.env.pop("LATTICE_ROOT", None)
        self.origin, self.board_origin, self.root = top / "origin.git", top / "board.git", top / "kit"
        for bare in (self.origin, self.board_origin):
            self.run_in(top, "git", "init", "-q", "--bare", "-b", "main", str(bare))
        self.run_in(top, "git", "init", "-q", "-b", "main", str(self.root))
        self.write(".gitignore", ".lattice/\n")
        for suite in SUITES:
            self.write(suite + "/test_ok.py", PASSES)
        self.write("swe/scripts/check_drift.sh", "exit 0\n")
        self.write("swe/scripts/switch_rules.sh", INSTALLER)
        self.write("swe/scripts/board_update.sh", BOARD_UPDATE)
        shutil.copy(SWE / "scripts/finish_batch.sh", self.root / "swe/scripts/finish_batch.sh")
        for tool in ("lattice_review.py", "merge_approved.py", "owner_review.py"):
            shutil.copy(SWE / "tools/lattice-review" / tool, self.root / "swe/tools/lattice-review" / tool)
        self.git("add", ".")
        self.git("commit", "-q", "-m", "chore: start the kit")
        self.git("remote", "add", "origin", str(self.origin))
        self.git("push", "-q", "-u", "origin", "main")
        self.start = self.git("rev-parse", "HEAD")
        self.lattice("init", "--path", ".", "--project-code", "T", "--project-name", "t", "--preset", "linear",
                     "--workflow", "classic", "--review-mode", "inline", "--plan-review-mode", "inline",
                     "--plan-approval", "human", "--done-display", "all", "--no-seed", "--no-setup-claude",
                     "--no-setup-agents", "--description", "test board")
        self.task("T-1", "feature/T-1-one", "one.txt", "one\n")
        self.task("T-2", "feature/T-2-two", "two.txt", "two\n")
        self.lattice("criterion", "add", "T-2", "The project's checks pass on the integration branch after the merge.")
        self.board = self.root / ".lattice"
        self.run_in(self.root, "git", "init", "-q", "--initial-branch=main", ".lattice")
        self.run_in(self.board, "git", "add", "-A")
        self.run_in(self.board, "git", "commit", "-q", "-m", "chore(board): start the board")
        self.run_in(self.board, "git", "remote", "add", "origin", str(self.board_origin))
        self.run_in(self.board, "git", "push", "-q", "-u", "origin", "main")

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def run_in(self, cwd, *command):
        done = subprocess.run(command, cwd=cwd, env=self.env, capture_output=True, text=True, input="", timeout=300)
        self.assertEqual(done.returncode, 0, "%s: %s" % (" ".join(command), done.stdout + done.stderr))
        return done.stdout + done.stderr

    def git(self, *args, cwd=None):
        return self.run_in(cwd or self.root, "git", *args).strip()

    def lattice(self, *args):
        return self.run_in(self.root, LATTICE, *args, "--actor", "human:owner")

    def task(self, sid, branch, path, text):
        self.lattice("create", "task " + sid)
        self.git("checkout", "-q", "-b", branch, "main")
        self.write(path, text)
        self.git("add", path)
        self.git("commit", "-q", "-m", "feat: add %s\n\nTask: %s" % (path, sid))
        self.git("checkout", "-q", "main")
        self.lattice("branch-link", sid, branch)
        for status in ("todo", "in_progress", "in_review"):
            self.lattice("status", sid, status, "--no-auto-review")

    def finish(self, answers, *extra, ids=("T-1", "T-2")):
        """owner_review.py takes answers only from the terminal, so the script runs in a session of its
        own on a pty with the answers typed ahead."""
        owner, terminal = pty.openpty()
        try:
            os.write(owner, answers.encode())
            done = subprocess.run([BASH, "swe/scripts/finish_batch.sh", "--actor", "human:owner", "--after-merge", "T-2:AC-1",
                                   *extra, *ids], cwd=self.root, env=self.env, stdin=terminal, capture_output=True, text=True,
                                  timeout=300, start_new_session=True, preexec_fn=lambda: fcntl.ioctl(0, termios.TIOCSCTTY, 0))
        finally:
            os.close(owner)
            os.close(terminal)
        return done.returncode, done.stdout + done.stderr

    def status(self, sid):
        tasks = (json.loads(path.read_text()) for path in (self.root / ".lattice/tasks").glob("*.json"))
        return next(task["status"] for task in tasks if task.get("short_id") == sid)

    def remote_main(self):
        return self.git("rev-parse", "main", cwd=self.origin)

    def test_the_whole_run_stops_once_for_the_push_and_a_rerun_finishes_it(self):
        code, out = self.finish("y\ny\n\n")
        self.assertEqual(code, 1, out)
        self.assertIn("STOP: main is not on the remote yet; push it, then run this again", out)
        for name in ("1: push and fetch", "2: review", "3: merge and test", "4: publish"):
            self.assertIn("== Phase " + name, out)
        self.assertNotIn("== Phase 5", out)
        self.assertIn("== finish_batch ended with exit 1", out)
        self.assertEqual(self.remote_main(), self.start)
        self.assertEqual(self.git("rev-list", "--count", "--first-parent", self.start + "..main"), "2")
        self.assertEqual(self.git("rev-parse", "feature/T-1-one", cwd=self.origin), self.git("rev-parse", "feature/T-1-one"))
        self.assertFalse((self.home / "installed").exists())
        self.git("push", "-q", "origin", "main")
        code, out = self.finish("y\n")
        self.assertEqual(code, 0, out)
        for name in ("5: install", "6: boards", "7: acceptance"):
            self.assertIn("== Phase " + name, out)
        self.assertTrue((self.home / "installed").exists())
        self.assertIn(str(self.root) + " --apply", (self.home / "board_update.log").read_text())
        self.assertIn("T-2 AC-1: evidence recorded", out)
        self.assertEqual((self.status("T-1"), self.status("T-2")), ("done", "done"))
        self.assertRegex(out, r"merged +2  T-1 T-2\nskipped +0  \nclosed +2  T-1 T-2\nstill open +0")
        self.assertEqual(self.git("rev-parse", "main", cwd=self.board_origin), self.git("rev-parse", "HEAD", cwd=self.board))
        self.assertEqual(self.git("status", "--porcelain", cwd=self.board), "")
        settled = (self.remote_main(), self.git("rev-parse", "HEAD", cwd=self.board))
        code, out = self.finish("")
        self.assertEqual(code, 0, out)
        self.assertIn("nothing to install", out)
        self.assertEqual((self.remote_main(), self.git("rev-parse", "HEAD", cwd=self.board)), settled)

    def test_the_evidence_counts_the_tests_and_lattice_review_runs_on_the_python_lattice_runs_on(self):
        self.write("swe/tools/lattice-review/test_dashboard.py", NEEDS_LATTICE)
        self.write("swe/scripts/test_skips.py", PASSES.replace("pass", "self.skipTest('not on this machine')"))
        self.git("add", "swe/tools/lattice-review/test_dashboard.py", "swe/scripts/test_skips.py")
        self.git("commit", "-q", "-m", "test: add a dashboard test and a skipped test")
        self.git("push", "-q", "origin", "main")
        self.finish("y\ny\n\n")
        self.git("push", "-q", "origin", "main")
        code, out = self.finish("")
        self.assertEqual(code, 0, out)
        notes = [event["data"]["body"] for path in (self.board / "events").glob("*.jsonl")
                 for event in map(json.loads, path.read_text().splitlines())
                 if event["type"] == "comment_added" and event["data"].get("role") == "validation"]
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("ran the four test suites (6 tests, 1 skipped)", notes[0])
        self.assertIn("and none failed.", notes[0])

    def test_a_rerun_before_the_push_keeps_the_earlier_merges_and_asks_again(self):
        self.finish("y\ny\n\n")
        merged = self.git("rev-parse", "main")
        code, out = self.finish("y\ny\n\n")
        self.assertEqual(code, 1, out)
        self.assertIn("an approval is already recorded", out)
        self.assertIn("T-1: merged here by an earlier run", out)
        self.assertIn("T-2: merged here by an earlier run", out)
        self.assertIn("STOP: main is not on the remote yet", out)
        self.assertEqual(self.git("rev-parse", "main"), merged)

    def test_a_task_answered_no_is_left_out_and_stays_open(self):
        self.finish("y\nn\n\n")
        self.assertEqual(self.git("rev-list", "--count", "--first-parent", self.start + "..main"), "1")
        self.git("push", "-q", "origin", "main")
        code, out = self.finish("n\n")
        self.assertEqual(code, 0, out)
        self.assertIn("T-2 AC-1: not recorded, the task is not in origin/main yet", out)
        self.assertEqual((self.status("T-1"), self.status("T-2")), ("done", "in_review"))
        self.assertRegex(out, r"merged +1  T-1\nskipped +1  T-2\nclosed +1  T-1\nstill open +1  T-2")

    def test_a_flag_that_still_asks_something_keeps_its_task_open_until_the_owner_clears_it(self):
        self.run_in(self.root, LATTICE, "needs-human", "T-1", "Need: decide the name", "--actor", "agent:x")
        self.finish("y\ny\n\n")
        self.git("push", "-q", "origin", "main")
        code, out = self.finish("y\nn\n")
        self.assertEqual(code, 0, out)
        self.assertIn("T-1: left open: its flag is not cleared", out)
        self.assertEqual((self.status("T-1"), self.status("T-2")), ("in_review", "done"))
        code, out = self.finish("y\n")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.status("T-1"), "done")

    def test_a_no_keeps_out_every_branch_that_contains_the_declined_one(self):
        self.lattice("create", "task T-3")
        self.git("checkout", "-q", "-b", "feature/T-3-three", "feature/T-1-one")
        self.write("three.txt", "three\n")
        self.git("add", "three.txt")
        self.git("commit", "-q", "-m", "feat: add three.txt\n\nTask: T-3")
        self.git("checkout", "-q", "main")
        self.lattice("branch-link", "T-3", "feature/T-3-three")
        for status in ("todo", "in_progress", "in_review"):
            self.lattice("status", "T-3", status, "--no-auto-review")
        ids = ("T-1", "T-2", "T-3")
        code, out = self.finish("n\ny\ny\n\n", ids=ids)
        self.assertIn("its branch also holds the work of 1 other task(s): T-1", out)
        self.assertIn("T-3: skipped, its branch contains T-1, which is not approved", out)
        self.assertEqual(self.git("rev-list", "--count", "--first-parent", self.start + "..main"), "1")
        self.assertFalse((self.root / "one.txt").exists())
        self.assertFalse((self.root / "three.txt").exists())
        self.git("push", "-q", "origin", "main")
        code, out = self.finish("n\nn\ny\n", ids=ids)
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"merged +1  T-2\nskipped +2  T-1 T-3\nclosed +1  T-2\nstill open +2  T-1 T-3")

    def test_an_installer_that_cannot_say_where_the_machine_stands_stops_the_run(self):
        self.finish("y\ny\n\n")
        self.git("push", "-q", "origin", "main")
        (self.home / "blocked").write_text("")
        code, out = self.finish("")
        self.assertEqual(code, 1, out)
        self.assertIn("STOP: the installer could not say where this machine stands (exit 2)", out)
        self.assertNotIn("== Phase 6", out)
        self.assertFalse((self.home / "installed").exists())

    def test_a_failing_check_stops_before_the_push_and_takes_nothing_back(self):
        self.git("checkout", "-q", "feature/T-2-two")
        self.write("swe/scripts/test_bad.py", PASSES.replace("pass", "self.fail('broken')"))
        self.git("add", "swe/scripts/test_bad.py")
        self.git("commit", "-q", "-m", "test: add a failing test\n\nTask: T-2")
        self.git("checkout", "-q", "main")
        code, out = self.finish("y\ny\n\n")
        self.assertEqual(code, 1, out)
        self.assertIn("STOP: the merge phase stopped", out)
        self.assertNotIn("== Phase 4", out)
        self.assertEqual(self.remote_main(), self.start)
        self.assertEqual(self.git("rev-list", "--count", "--first-parent", self.start + "..main"), "2")
        self.assertEqual((self.status("T-1"), self.status("T-2")), ("in_review", "in_review"))

    def test_a_board_that_is_not_ready_stops_the_run_before_anything_is_committed_to_it(self):
        before = self.git("rev-parse", "HEAD", cwd=self.board)
        self.git("checkout", "-q", "-b", "elsewhere", cwd=self.board)
        code, out = self.finish("y\ny\n\n")
        self.assertEqual(code, 1, out)
        self.assertIn("is not on its main branch", out)
        self.assertNotIn("== Phase 2", out)
        self.assertEqual(self.git("rev-parse", "HEAD", cwd=self.board), before)
        self.assertEqual(self.git("rev-parse", "main"), self.start)

    def test_uncommitted_work_in_the_main_checkout_stops_it_at_once(self):
        self.write("swe/scripts/check_drift.sh", "exit 0\n# edited\n")
        code, out = self.finish("y\ny\n\n")
        self.assertEqual(code, 1, out)
        self.assertIn("has uncommitted changes", out)
        self.assertNotIn("== Phase 1", out)

    def test_another_projects_board_that_fails_is_reported_and_the_run_still_closes_the_tasks(self):
        other = pathlib.Path(self.tmp.name, "broken")
        (other / ".lattice").mkdir(parents=True)
        (other / ".lattice/config.json").write_text("{}")
        self.finish("y\ny\n\n", "--project", str(other))
        self.git("push", "-q", "origin", "main")
        code, out = self.finish("y\n", "--project", str(other))
        self.assertEqual(code, 1, out)
        self.assertIn("PROBLEM: the board in %s was not brought up to date" % other, out)
        self.assertIn("STOP: a board was not brought up to date; see phase 6", out)
        self.assertEqual((self.status("T-1"), self.status("T-2")), ("done", "done"))


if __name__ == "__main__":
    unittest.main()
