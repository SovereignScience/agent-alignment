import json
import urllib.parse
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.request
from argparse import Namespace
from http.server import ThreadingHTTPServer
from pathlib import Path

import lattice_review as lr

ENV = dict(os.environ, LATTICE_NO_UPDATE_CHECK="1")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def commit(repo, name, message, content=None):
    (repo / name).write_text((content or name) + "\n")
    git(repo, "add", name)
    git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def task(board, sid, status, title, branch=None):
    record = {"id": "task_" + sid.replace("-", ""), "short_id": sid, "status": status, "title": title,
              "priority": "medium", "type": "task", "tags": ["x"], "description": "desc " + sid,
              "acceptance_criteria": [], "branch_links": [{"branch": branch}] if branch else []}
    (board / ".lattice" / "tasks" / (record["id"] + ".json")).write_text(json.dumps(record))


def fake_plannotator(where, decision="annotated", message="line 2: rename it"):
    script = where / "plannotator"
    script.write_text("#!/bin/sh\ncat > /dev/null\nprintf '%s\\n' '" + json.dumps({"decision": decision, "message": message}) + "'\n")
    script.chmod(0o755)
    return str(script)


def wait_for(job):
    for _ in range(200):
        if job.done:
            return
        subprocess.run(["sleep", "0.05"])


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        git(self.repo, "init", "-q", "-b", "main")
        (self.repo / ".lattice" / "tasks").mkdir(parents=True)
        (self.repo / ".lattice" / "config.json").write_text(json.dumps({
            "project_code": "T", "project_name": "Test board", "dashboard_port": 8700,
            "workflow": {"transitions": {"backlog": ["todo"], "in_review": ["done"]}}}))
        self.a = commit(self.repo, "a", "init")
        self.b = commit(self.repo, "b", "feat: b\n\nTask: AB-1")
        git(self.repo, "branch", "task/ab-4")
        self.c = commit(self.repo, "c", "fix: c\n\nTask: AB-2")
        self.d = commit(self.repo, "d", "feat: d\n\nTask: AB-1, AB-3")
        self.f = commit(self.repo, "f", "chore: f\n\nTask: AB-10")
        git(self.repo, "checkout", "-q", "task/ab-4")
        self.e = commit(self.repo, "e", "feat: e\n\nTask: AB-4")
        git(self.repo, "checkout", "-q", "main")
        task(self.repo, "AB-1", "in_review", "two commits apart")
        task(self.repo, "AB-2", "backlog", "one commit")
        task(self.repo, "AB-4", "in_progress", "branch work", branch="task/ab-4")
        task(self.repo, "AB-9", "backlog", "nothing yet")

    def tearDown(self):
        self.tmp.cleanup()

    def context(self, board=None, repo=None):
        return lr.Context(Namespace(board=str(board or self.repo), repo=str(repo) if repo else None, main="main", remote="origin",
                                    actor="human:t", dashboard_url=None, state=str(self.repo / "state")))

    def test_trailer_match_is_exact(self):
        self.assertEqual([c["hash"] for c in lr.task_commits(self.repo, "AB-1", ["HEAD"])], [self.b, self.d])
        self.assertEqual([c["hash"] for c in lr.task_commits(self.repo, "AB-10", ["HEAD"])], [self.f])
        self.assertEqual([c["hash"] for c in lr.task_commits(self.repo, "AB-3", ["HEAD"])], [self.d])

    def test_single_commit_is_a_bound_range(self):
        rng = lr.resolve_range(self.repo, lr.find_task(self.repo, "AB-2"), "main")
        self.assertEqual((rng["mode"], rng["contiguous"], rng["base"], rng["head"]), ("commits", True, self.c + "^", self.c))
        self.assertEqual((rng["base_sha"], rng["head_sha"]), (self.b, self.c))
        self.assertEqual([f["path"] for f in lr.changed_files(self.repo, rng["base"], rng["head"])], ["c"])

    def test_split_commits_have_no_range(self):
        rng = lr.resolve_range(self.repo, lr.find_task(self.repo, "AB-1"), "main")
        self.assertEqual((rng["mode"], rng["contiguous"], rng["base"], rng["head_sha"]), ("commits", False, None, None))
        self.assertEqual([c["hash"] for c in rng["commits"]], [self.b, self.d])

    def test_linked_branch_resolves_to_commit_ids(self):
        rng = lr.resolve_range(self.repo, lr.find_task(self.repo, "AB-4"), "main")
        self.assertEqual((rng["mode"], rng["base"], rng["head"], rng["base_sha"], rng["head_sha"]), ("branch", self.b, "task/ab-4", self.b, self.e))
        self.assertEqual([c["hash"] for c in rng["commits"]], [self.e])

    def test_unlinked_task_has_no_work(self):
        self.assertEqual(lr.resolve_range(self.repo, lr.find_task(self.repo, "AB-9"), "main")["mode"], "none")

    def test_needs_human_reason(self):
        self.assertEqual(lr.needs_human({"needs_human": {"reason": "Need: pick one", "since": "x"}}), "Need: pick one")
        self.assertEqual(lr.needs_human({"needs_human": None}), "")

    def test_tasks_sort_by_status_then_number(self):
        self.assertEqual([t["short_id"] for t in lr.load_tasks(self.repo)], ["AB-1", "AB-4", "AB-2", "AB-9"])

    def test_vscode_uri(self):
        uri = lr.vscode_uri("/r/p q", "abc^", "WORKTREE", "AB-1 title")
        self.assertTrue(uri.startswith("vscode://" + lr.EXTENSION_ID + "/diff?"))
        self.assertIn("repo=%2Fr%2Fp+q", uri)
        self.assertIn("base=abc%5E", uri)

    def test_plannotator_args(self):
        live, patch = lr.plannotator_args("pl", base="abc", live=True)
        self.assertEqual((live, patch), (["pl", "review", "--git", "--no-git-remote-check", "--json", "--base", "abc"], None))
        args, patch = lr.plannotator_args("pl", base="abc^", head="abc")
        self.assertEqual((args, patch), (["pl", "review", "--patch-file", "-", "--json"], ["diff", "abc^", "abc"]))
        self.assertEqual(lr.plannotator_args("pl", base="abc", head=lr.WORKTREE)[1], ["diff", "abc"])

    def test_parse_review(self):
        self.assertEqual(lr.parse_review('noise\n{"decision": "annotated", "message": "fix line 3"}\n'), ("annotated", "fix line 3"))
        self.assertEqual(lr.parse_review("plain text"), (None, "plain text"))

    def test_renamed_file_keeps_old_path_for_the_base_side(self):
        git(self.repo, "mv", "c", "c-renamed")
        git(self.repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "refactor: move c\n\nTask: AB-2")
        head = git(self.repo, "rev-parse", "HEAD")
        files = lr.changed_files(self.repo, head + "^", head)
        self.assertEqual(files, [{"status": "R", "path": "c-renamed", "old_path": "c"}])
        ctx = self.context()
        ctx.code = "true"
        ctx.code_diff(head + "^", head, "c-renamed", "c", "R")
        left = next((self.repo / "state" / "tmp").glob("*-c"))
        self.assertEqual(left.read_text(), "c\n")
        with self.assertRaises(RuntimeError):
            ctx.code_diff(head + "^", head, "missing", "missing", "M")

    def test_review_is_bound_to_the_reviewed_revision(self):
        task_record = lr.find_task(self.repo, "AB-2")
        result = self.repo / "review.md"
        result.write_text("Plannotator approved\n%s%s..%s\n\nfine\n" % (lr.REVIEWED, self.b, self.c))
        self.assertIsNone(lr.stale_reason(self.repo, task_record, "main", result))
        result.write_text("Plannotator approved\n%s%s..%s dirty\n\nfine\n" % (lr.REVIEWED, self.b, self.c))
        self.assertIn("uncommitted", lr.stale_reason(self.repo, task_record, "main", result))
        result.write_text("Plannotator approved\n\nfine\n")
        self.assertIn("no revision", lr.stale_reason(self.repo, task_record, "main", result))
        result.write_text("Plannotator approved\n%s%s..%s\n\nfine\n" % (lr.REVIEWED, self.b, self.c))
        commit(self.repo, "c2", "fix: more c\n\nTask: AB-2")
        self.assertIn("no single commit range", lr.stale_reason(self.repo, task_record, "main", result))
        branch_task = lr.find_task(self.repo, "AB-4")
        result.write_text("Plannotator approved\n%s%s..%s\n\nfine\n" % (lr.REVIEWED, self.b, self.e))
        self.assertIsNone(lr.stale_reason(self.repo, branch_task, "main", result))
        git(self.repo, "checkout", "-q", "task/ab-4")
        commit(self.repo, "e2", "feat: more e\n\nTask: AB-4")
        git(self.repo, "checkout", "-q", "main")
        self.assertIn("review again", lr.stale_reason(self.repo, branch_task, "main", result))

    def test_failed_board_write_is_not_reported_as_recorded(self):
        ctx = self.context()
        ctx.plannotator = fake_plannotator(self.repo)
        ctx.lattice = "false"
        job = ctx.start_plannotator("AB-2", record_on="AB-2", base=self.c + "^", head=self.c)
        wait_for(job)
        self.assertIsNone(job.result_path)
        self.assertIn("not recorded", job.error)
        self.assertEqual(job.decision, "annotated")

    @unittest.skipUnless(shutil.which("lattice"), "lattice not on PATH")
    def test_review_lands_on_the_task_with_its_revision(self):
        board = Path(self.tmp.name) / "board"
        board.mkdir()
        subprocess.run(["lattice", "init", "--path", str(board), "--actor", "agent:test", "--project-code", "TB",
                        "--project-name", "tb", "--preset", "linear", "--workflow", "classic", "--no-seed",
                        "--no-setup-claude", "--no-setup-agents"], check=True, env=ENV, capture_output=True)
        sid = subprocess.run(["lattice", "create", "a task", "--actor", "agent:test", "--quiet"], cwd=board, env=ENV,
                             check=True, capture_output=True, text=True).stdout.strip()
        ctx = self.context(board=board, repo=self.repo)
        ctx.plannotator = fake_plannotator(self.repo)
        job = ctx.start_plannotator(sid, record_on=sid, base=self.c + "^", head=self.c)
        wait_for(job)
        self.assertTrue(job.done and not job.error, job.error)
        self.assertEqual(job.result_path, job.out_path)
        comments = json.loads(subprocess.run(["lattice", "comments", sid, "--json"], cwd=board, env=ENV, check=True,
                                             capture_output=True, text=True).stdout)["data"]
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["role"], "review")
        self.assertIn("line 2: rename it", comments[0]["body"])
        self.assertIn(lr.REVIEWED + self.b + ".." + self.c, comments[0]["body"])

    def test_pages_tokens_and_stale_completion(self):
        ctx = self.context()
        ctx.plannotator = "/nonexistent/plannotator"
        calls = []
        ctx.board_write = lambda key, *args: calls.append(args) or True
        server = ThreadingHTTPServer(("127.0.0.1", 0), lr.make_handler(ctx))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = "http://127.0.0.1:%d" % server.server_address[1]

        def rows(html):
            return {row.split("</a>")[0].split(">")[-1]: row for row in html.split("<tr>")[2:]}

        try:
            index = urllib.request.urlopen(base + "/").read().decode()
            self.assertIn("http://127.0.0.1:8700", index)
            by_id = rows(index)
            self.assertIn("Plannotator", by_id["AB-2"])
            self.assertIn("Plannotator", by_id["AB-4"])
            self.assertNotIn("Plannotator", by_id["AB-1"])
            self.assertNotIn("Plannotator", by_id["AB-9"])
            split = urllib.request.urlopen(base + "/t/AB-1").read().decode()
            self.assertEqual(split.count("<button class='quiet'>Plannotator</button>"), 2)
            self.assertNotIn("exact range", split)
            self.assertNotIn("live tree", split)
            detail = urllib.request.urlopen(base + "/t/AB-4").read().decode()
            self.assertIn("vscode://" + lr.EXTENSION_ID, detail)
            self.assertIn("exact range", detail)
            self.assertNotIn("live tree", detail)
            req = urllib.request.Request(base + "/t/AB-4/status", data=b"token=wrong&to=done", method="POST")
            with self.assertRaises(urllib.error.HTTPError) as err:
                urllib.request.urlopen(req)
            self.assertEqual(err.exception.code, 403)
            stale = self.repo / "stale.md"
            stale.write_text("Plannotator approved\n%s%s..%s\n\nfine\n" % (lr.REVIEWED, self.a, self.b))
            form = urllib.parse.urlencode({"token": ctx.token, "result": str(stale)}).encode()
            after = urllib.request.urlopen(urllib.request.Request(base + "/t/AB-2/complete", data=form, method="POST")).read().decode()
            self.assertIn("not completed", after)
            self.assertEqual(calls, [])
            with self.assertRaises(urllib.error.HTTPError) as err:
                urllib.request.urlopen(base + "/t/AB-99")
            self.assertEqual(err.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
