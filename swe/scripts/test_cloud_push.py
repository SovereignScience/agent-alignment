"""cloud_push.sh against a throwaway repository and bare remotes."""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / ".claude/scripts/cloud_push.sh"
BASH = shutil.which("bash")


class CloudPush(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.remote = root / "remote.git"
        self.repo = root / "repo"
        self.git("init", "-q", "--bare", "-b", "main", str(self.remote), cwd=root)
        self.git("init", "-q", "-b", "main", str(self.repo), cwd=root)
        self.git("config", "user.name", "Owner")
        self.git("config", "user.email", "owner@example.com")
        self.git("remote", "add", "origin", str(self.remote))
        self.commit("base")
        self.git("push", "-q", "origin", "main")

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.repo, capture_output=True, text=True,
                              check=True).stdout.strip()

    def commit(self, name, cwd=None):
        where = cwd or self.repo
        (where / name).write_text(name)
        self.git("add", name, cwd=where)
        self.git("commit", "-q", "-m", "add " + name, cwd=where)

    def push(self, *args, cloud=True):
        env = dict(os.environ, HOME=self.tmp.name)
        env.pop("CLAUDE_CODE_REMOTE", None)
        env.pop("LATTICE_ROOT", None)
        if cloud:
            env["CLAUDE_CODE_REMOTE"] = "true"
        run = subprocess.run([BASH, str(SCRIPT), *args], cwd=self.repo, env=env, capture_output=True,
                             text=True, timeout=60)
        return run.returncode, run.stdout + run.stderr

    def remote_branches(self, remote=None):
        return self.git("branch", "--format=%(refname:short)", cwd=remote or self.remote).split()

    def test_a_task_branch_is_pushed_from_a_cloud_session_only(self):
        self.git("switch", "-q", "-c", "feature/AA-7-fix-empty-input")
        self.commit("work")
        code, out = self.push(cloud=False)
        self.assertNotEqual(code, 0)
        self.assertIn("not a cloud session", out)
        self.assertEqual(self.remote_branches(), ["main"])
        code, out = self.push()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.remote_branches(), ["feature/AA-7-fix-empty-input", "main"])

    def test_other_branches_and_unsaved_work_are_refused(self):
        self.commit("on-main")
        for branch in ("main", "claude/fix", "feature/no-task-id", "integration/x"):
            if branch != "main":
                self.git("switch", "-q", "-c", branch)
            code, out = self.push()
            self.assertNotEqual(code, 0, branch)
            self.assertIn("is not a task branch", out)
        self.git("switch", "-q", "-c", "feature/AA-8-x")
        (self.repo / "draft").write_text("unsaved")
        code, out = self.push()
        self.assertNotEqual(code, 0)
        self.assertIn("uncommitted changes", out)
        self.assertEqual(self.git("rev-parse", "main", cwd=self.remote),
                         self.git("rev-parse", "origin/main"))
        self.assertEqual(self.remote_branches(), ["main"])

    def test_a_push_that_would_rewrite_the_remote_branch_is_rejected(self):
        self.git("switch", "-q", "-c", "feature/AA-9-x")
        self.commit("one")
        self.assertEqual(self.push()[0], 0)
        pushed = self.git("rev-parse", "HEAD")
        self.git("reset", "-q", "--hard", "HEAD~1")
        self.commit("other")
        code, _ = self.push()
        self.assertNotEqual(code, 0)
        self.assertEqual(self.git("rev-parse", "feature/AA-9-x", cwd=self.remote), pushed)

    def test_the_board_goes_to_its_own_main_and_nowhere_else(self):
        board_remote = pathlib.Path(self.tmp.name, "board.git")
        board = self.repo / ".lattice"
        self.git("init", "-q", "--bare", "-b", "main", str(board_remote), cwd=self.tmp.name)
        self.git("init", "-q", "-b", "main", str(board), cwd=self.tmp.name)
        self.git("config", "user.name", "Owner", cwd=board)
        self.git("config", "user.email", "owner@example.com", cwd=board)
        self.git("remote", "add", "origin", str(board_remote), cwd=board)
        self.commit("task.json", cwd=board)
        code, out = self.push("--board")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.git("rev-parse", "main", cwd=board_remote), self.git("rev-parse", "HEAD", cwd=board))
        self.assertEqual(self.remote_branches(), ["main"])
        self.assertNotEqual(self.push("--board", cloud=False)[0], 0)
        self.assertNotEqual(self.push("--force")[0], 0)

    def test_the_root_guard_hook_runs_only_in_a_cloud_session(self):
        import json
        root = SCRIPT.parents[2]
        hook = json.loads((root / ".claude/settings.json").read_text())["hooks"]["PreToolUse"][0]["hooks"][0]
        call = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push origin main"}})
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
        env.pop("CLAUDE_CODE_REMOTE", None)
        local = subprocess.run([BASH, "-c", hook["command"]], input=call, env=env, capture_output=True, text=True)
        self.assertEqual((local.returncode, local.stdout), (0, ""))
        cloud = subprocess.run([BASH, "-c", hook["command"]], input=call, env=dict(env, CLAUDE_CODE_REMOTE="true"),
                               capture_output=True, text=True)
        self.assertEqual(json.loads(cloud.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")


if __name__ == "__main__":
    unittest.main()
