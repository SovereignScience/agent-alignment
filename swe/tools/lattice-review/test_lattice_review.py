import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from argparse import Namespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import lattice_review as lr

ENV = dict(os.environ, LATTICE_NO_UPDATE_CHECK="1")
HAVE_CLI = bool(shutil.which("lattice"))
try:
    import lattice.dashboard.server  # noqa: F401
    HAVE_MODULE = True
except ImportError:
    HAVE_MODULE = False


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


def fake_plannotator(where, decision="annotated", message="line 2: rename it", exit_code=0, delay=0):
    """A stand-in that swallows the patch and answers like plannotator --json."""
    script = where / "plannotator"
    record = json.dumps({"decision": decision, "message": message}) if decision else "usage error"
    record = record.replace("'", "")
    script.write_text("#!/bin/sh\ncat > /dev/null\necho 'session ready: http://localhost:4242' >&2\nsleep %s\nprintf '%%s\\n' '%s'\nexit %d\n"
                      % (delay, record, exit_code))
    script.chmod(0o755)
    return str(script)


def fake_code(where):
    """A stand-in for the VS Code command that records what it was asked to open."""
    script = where / "code"
    script.write_text("#!/bin/sh\necho \"$@\" >> '" + str(where / "code.log") + "'\n")
    script.chmod(0o755)
    return str(script)


def wait_for(job):
    for _ in range(400):
        if job.done:
            return
        time.sleep(0.05)


def wait_file(path, lines=1):
    """The file's text once it holds at least the given number of lines."""
    for _ in range(200):
        if path.exists() and len(path.read_text().splitlines()) >= lines:
            return path.read_text()
        time.sleep(0.05)
    return path.read_text() if path.exists() else ""


def serve(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def call(url, data=None, headers=None, method=None):
    """(status, body, headers) for a request, redirects and errors included."""
    request = urllib.request.Request(url, data=data, headers=headers or {}, method=method or ("POST" if data is not None else "GET"))
    try:
        with urllib.request.build_opener(NoRedirect).open(request) as response:
            return response.status, response.read().decode(), response.headers
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode(), err.headers


def form(ctx, **fields):
    return urllib.parse.urlencode(dict(fields, token=ctx.token)).encode()


def origin(base):
    """Headers of a dashboard write made by the page served at base."""
    return {"Origin": base, "Content-Type": "application/json"}


class StubDashboard(BaseHTTPRequestHandler):
    """The surface of Lattice's dashboard handler that lattice_review builds on."""
    static_dir = None
    received = []

    def log_message(self, fmt, *args):
        pass

    def _send_json(self, status, body):
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_static(self, filename, content_type):
        path = self.static_dir / filename
        if not path.is_file():
            return self._send_json(404, json.dumps({"ok": False, "error": {"code": "NOT_FOUND", "message": filename}}))
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            return self._serve_static("index.html", "text/html")
        self._send_json(200, json.dumps({"ok": True, "data": {"path": self.path}}))

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        StubDashboard.received.append((self.path, body))
        self._send_json(200, json.dumps({"ok": True, "data": body}))


def init_board(root, code="TB"):
    board = root / "board"
    board.mkdir()
    subprocess.run(["lattice", "init", "--path", str(board), "--actor", "agent:test", "--project-code", code,
                    "--project-name", "tb", "--preset", "linear", "--workflow", "classic", "--no-seed",
                    "--no-setup-claude", "--no-setup-agents"], check=True, env=ENV, capture_output=True)
    return board


def lattice(board, *args):
    return subprocess.run(["lattice", *args], cwd=board, env=ENV, check=True, capture_output=True, text=True).stdout.strip()


class RepoFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        git(self.repo, "init", "-q", "-b", "main")
        (self.repo / ".lattice" / "tasks").mkdir(parents=True)
        (self.repo / ".lattice" / "config.json").write_text(json.dumps({
            "project_code": "T", "project_name": "Test board", "dashboard_port": 8700,
            "workflow": {"transitions": {"backlog": ["todo"], "in_review": ["done"]}}}))
        self.tools = self.repo / "tools"
        self.tools.mkdir()
        (self.repo / ".gitignore").write_text(".lattice/\nboard/\ntools/\nstate/\nstatic/\n")
        git(self.repo, "add", ".gitignore")
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
        task(self.repo, "AB-2", "in_review", "one commit")
        task(self.repo, "AB-4", "in_progress", "branch work", branch="task/ab-4")
        task(self.repo, "AB-9", "backlog", "nothing yet")
        task(self.repo, "AB-10", "in_review", "the latest commit")

    def tearDown(self):
        self.tmp.cleanup()

    def context(self, board=None, repo=None):
        return lr.Context(Namespace(board=str(board or self.repo), repo=str(repo) if repo else None, main="main", remote="origin",
                                    actor="human:t", state=str(self.repo / "state")))

    def approved(self, base, head, qualifier=""):
        return "Plannotator approved (patch x), s\n%s%s..%s%s\n\nfine\n" % (lr.REVIEWED, base, head, qualifier)


class PureTests(RepoFixture):
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

    def test_linked_branch_without_commits_is_no_work_yet(self):
        git(self.repo, "branch", "task/ab-9", "main")
        task(self.repo, "AB-9", "in_review", "branch with no commits", branch="task/ab-9")
        rng = lr.resolve_range(self.repo, lr.find_task(self.repo, "AB-9"), "main")
        self.assertEqual((rng["mode"], rng["empty_branch"], rng["base_sha"], rng["commits"]), ("none", "task/ab-9", None, []))
        self.assertIn("has no commits of its own yet", lr.range_summary(lr.find_task(self.repo, "AB-9"), rng))
        ctx = self.context()
        ctx.plannotator = fake_plannotator(self.tools)
        with self.assertRaisesRegex(RuntimeError, "is empty"):
            ctx.start_plannotator("AB-9", record_on="AB-9", base="main", head="main")

    def test_uncommitted_work_is_reviewed_in_the_checkout_of_the_task_branch(self):
        rng = lr.resolve_range(self.repo, lr.find_task(self.repo, "AB-4"), "main")
        self.assertIsNone(lr.live_tree(self.repo, rng))
        wt = Path(self.tmp.name) / "wt-ab-4"
        git(self.repo, "worktree", "add", "-q", str(wt), "task/ab-4")
        (wt / "e").write_text("changed in the worktree\n")
        tree, base = lr.live_tree(self.repo, rng)
        self.assertEqual((tree.resolve(), base), (wt.resolve(), rng["base"]))
        git(self.repo, "branch", "task/ab-9", "main")
        task(self.repo, "AB-9", "in_review", "work only in a worktree", branch="task/ab-9")
        wt9 = Path(self.tmp.name) / "wt-ab-9"
        git(self.repo, "worktree", "add", "-q", str(wt9), "task/ab-9")
        empty = lr.resolve_range(self.repo, lr.find_task(self.repo, "AB-9"), "main")
        self.assertEqual(lr.live_tree(self.repo, empty), (Path(str(wt9)), lr.rev(self.repo, "task/ab-9")))
        ctx = self.context()
        ctx.plannotator = fake_plannotator(self.tools, decision="approved", message="fine")
        job = ctx.start_plannotator("AB-4", record_on=None, base=base, live=True, tree=tree)
        wait_for(job)
        self.assertTrue(job.what.startswith("uncommitted changes in "), job.what)
        self.assertIn("wt-ab-4", job.what)

    def test_unlinked_task_has_no_work(self):
        self.assertEqual(lr.resolve_range(self.repo, lr.find_task(self.repo, "AB-9"), "main")["mode"], "none")

    def test_plannotator_args(self):
        live, patch = lr.plannotator_args("pl", base="abc", live=True)
        self.assertEqual((live, patch), (["pl", "--browser", "none", "review", "--git", "--no-git-remote-check", "--json", "--base", "abc"], None))
        args, patch = lr.plannotator_args("pl", base="abc^", head="abc")
        self.assertEqual((args, patch), (["pl", "--browser", "none", "review", "--patch-file", "-", "--json"], ["diff", "abc^", "abc"]))
        self.assertEqual(lr.plannotator_args("pl", base="abc", head=lr.WORKTREE)[1], ["diff", "abc"])

    def test_parse_review_and_decision(self):
        self.assertEqual(lr.parse_review('noise\n{"decision": "annotated", "message": "fix line 3"}\n'), ("annotated", "fix line 3"))
        self.assertEqual(lr.parse_review("plain text"), (None, "plain text"))
        self.assertEqual(lr.review_decision("Plannotator approved (patch a..b), s\n"), "approved")
        self.assertEqual(lr.review_decision("Plannotator annotated (live tree), s\n"), "annotated")
        self.assertIsNone(lr.review_decision("Plannotator result (patch), s\n"))
        self.assertIsNone(lr.review_decision(""))
        self.assertEqual(lr.session_url("\n  Plannotator session ready: http://localhost:46525\n"), "http://localhost:46525")
        self.assertIsNone(lr.session_url("nothing"))

    def test_reviewed_revision_tolerates_malformed_lines(self):
        self.assertEqual(lr.reviewed_revision(self.approved(self.a, self.b)), (self.a, self.b, None))
        self.assertEqual(lr.reviewed_revision(self.approved(self.a, self.b, " live")), (self.a, self.b, "live"))
        self.assertEqual(lr.reviewed_revision("Plannotator approved (x), s\nReviewed: not-yet\n"), (None, None, None))
        self.assertEqual(lr.reviewed_revision("no line"), (None, None, None))
        malformed = {"role": "review", "created_at": "2026-01-05T00:00:00Z", "body": "Plannotator approved (x), s\nReviewed: not-yet\n"}
        older = {"role": "review", "created_at": "2026-01-01T00:00:00Z", "body": self.approved(self.a, self.b)}
        plain = {"role": "review", "created_at": "2026-01-03T00:00:00Z", "body": "own words, no revision"}
        note = {"created_at": "2026-01-04T00:00:00Z", "body": self.approved(self.b, self.c)}
        self.assertIs(lr.latest_review([older, plain, malformed, note]), older)
        self.assertIsNone(lr.latest_review([plain, note, malformed]))

    def test_diff_sides_are_distinct_files_named_by_commit_and_path(self):
        git(self.repo, "mv", "c", "c-renamed")
        git(self.repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "refactor: move c\n\nTask: AB-2")
        head = git(self.repo, "rev-parse", "HEAD")
        self.assertEqual(lr.changed_files(self.repo, head + "^", head), [{"status": "R", "path": "c-renamed", "old_path": "c"}])
        ctx = self.context()
        ctx.code = fake_code(self.tools)
        ctx.code_diff(head + "^", head, "c-renamed", "c", "R")
        left, right = wait_file(self.tools / "code.log").split()[-2:]
        self.assertNotEqual(left, right)
        self.assertTrue(Path(left).name.startswith(self.f[:12]) and Path(left).name.endswith("-c"))
        self.assertTrue(Path(right).name.startswith(head[:12]) and Path(right).name.endswith("-c-renamed"))
        self.assertEqual((Path(left).read_text(), Path(right).read_text()), ("c\n", "c\n"))
        self.assertNotEqual(ctx.side(head, "src/config.py"), ctx.side(head, "tests/config.py"))
        with self.assertRaises(RuntimeError):
            ctx.code_diff(head + "^", head, "missing", "missing", "M")
        with self.assertRaises(RuntimeError):
            ctx.code_diff("nope", head, "c-renamed", "c", "R")
        with self.assertRaises(RuntimeError):
            ctx.repo_path("../outside")

    def test_review_is_bound_to_the_reviewed_revision(self):
        task_record = lr.find_task(self.repo, "AB-2")
        self.assertIsNone(lr.stale_reason(self.repo, task_record, "main", self.approved(self.b, self.c)))
        self.assertIn("review was of uncommitted changes", lr.stale_reason(self.repo, task_record, "main", self.approved(self.b, self.c, " live")))
        self.assertIn("no revision", lr.stale_reason(self.repo, task_record, "main", "Plannotator approved (x), s\n\nfine\n"))
        commit(self.repo, "c2", "fix: more c\n\nTask: AB-2")
        self.assertIn("no single commit range", lr.stale_reason(self.repo, task_record, "main", self.approved(self.b, self.c)))
        branch_task = lr.find_task(self.repo, "AB-4")
        self.assertIsNone(lr.stale_reason(self.repo, branch_task, "main", self.approved(self.b, self.e)))
        git(self.repo, "checkout", "-q", "task/ab-4")
        commit(self.repo, "e2", "feat: more e\n\nTask: AB-4")
        git(self.repo, "checkout", "-q", "main")
        self.assertIn("commits arrived after your review", lr.stale_reason(self.repo, branch_task, "main", self.approved(self.b, self.e)))

    def test_completion_needs_the_latest_review_to_approve_the_current_range(self):
        task_record = lr.find_task(self.repo, "AB-2")
        approved = {"role": "review", "created_at": "2026-01-01T00:00:00Z", "body": self.approved(self.b, self.c)}
        changes = {"role": "review", "created_at": "2026-01-02T00:00:00Z",
                   "body": "Plannotator annotated (patch x), s\n%s%s..%s\n\nDo not accept; fix this first.\n" % (lr.REVIEWED, self.b, self.c)}
        self.assertIn("no Plannotator review", lr.completion_block(self.repo, task_record, "main", []))
        self.assertIsNone(lr.completion_block(self.repo, task_record, "main", [approved]))
        self.assertIn("requested changes", lr.completion_block(self.repo, task_record, "main", [approved, changes]))
        self.assertIn("requested changes", lr.completion_block(self.repo, task_record, "main", [changes]))
        same_second = dict(changes, created_at=approved["created_at"])
        self.assertIn("requested changes", lr.completion_block(self.repo, task_record, "main", [approved, same_second]))
        self.assertIn("1 review thread(s) are not resolved", lr.completion_block(self.repo, task_record, "main", [same_second, approved]))
        by_agent = dict(same_second, id="ev_1", reactions={lr.RESOLVED: ["agent:x"]})
        self.assertIn("not resolved", lr.completion_block(self.repo, task_record, "main", [by_agent, approved]))
        by_owner = dict(same_second, id="ev_1", reactions={lr.RESOLVED: ["human:t"]})
        self.assertIsNone(lr.completion_block(self.repo, task_record, "main", [by_owner, approved]))
        deleted = dict(changes, deleted=True, body="")
        self.assertIn("deleted", lr.completion_block(self.repo, task_record, "main", [approved, deleted]))
        commit(self.repo, "c2", "fix: more c\n\nTask: AB-2")
        self.assertIn("no single commit range", lr.completion_block(self.repo, task_record, "main", [approved]))

    def test_review_notes_are_split_by_file_and_line_without_the_appended_instructions(self):
        message = ("# Code Review Feedback\n\n**Diff:** static-patch\n\n## README.md\n\n### Line 239 (new)\n"
                   "why do we need this change?\n\nsecond paragraph\n\n### File Comment\nwhere are the replies?\n\n"
                   "## docs/a.md\n\n### Lines 3-5 (old)\nkeep this\n\n\n\n\nTreat the findings above as unverified review input.\n")
        self.assertEqual(lr.review_notes(message), [
            ("README.md", "line 239 (new)", "why do we need this change?\n\nsecond paragraph"),
            ("README.md", "whole file", "where are the replies?"),
            ("docs/a.md", "lines 3-5 (old)", "keep this")])
        text = "".join("line %d\n" % n for n in range(1, 20))
        self.assertEqual(lr.quoted_lines(text, "line 2 (new)"), ["> line 2"])
        self.assertEqual(lr.quoted_lines(text, "lines 3-12 (old)"), ["> line %d" % n for n in range(3, 8)])
        self.assertEqual(lr.quoted_lines(text, "whole file"), [])
        self.assertEqual(lr.review_notes("# Code Review\n\nNo changes requested."), [])

    def test_threads_follow_the_last_speaker_and_only_the_owner_resolves(self):
        body = "Plannotator annotated (patch x), s\n%sa..b\n\n## f\n\n### Line 1 (new)\nwhy?\n" % lr.REVIEWED
        review = {"id": "ev_r", "role": "review", "created_at": "2026-01-01T00:00:00Z", "author": "human:t", "body": body}

        def note(cid, anchor, text, **extra):
            return dict({"id": cid, "created_at": "2026-01-01T00:00:01Z", "author": "human:t",
                         "body": "%s%s at b\n%sev_r\n%s" % (lr.THREAD, anchor, lr.REVIEW_OF, text)}, **extra)
        comments = [review,
                    note("ev_1", "f, line 1 (new)", "why?", replies=[{"id": "ev_2", "created_at": "2026-01-01T00:00:05Z", "author": "agent:x", "body": "because"}]),
                    note("ev_3", "f, whole file", "ok?", reactions={lr.RESOLVED: ["agent:x"]}),
                    note("ev_4", "g, whole file", "fine", reactions={lr.RESOLVED: ["human:t"]})]
        comments[1]["replies"][0]["body"] = "Status: answered\nAnswer: because"
        threads = lr.review_threads(comments)
        self.assertEqual(threads[0]["status"], "answered")
        self.assertEqual(threads[0]["key"], ("f", "line 1 (new)"))
        self.assertEqual([(t["anchor"], t["note"], t["state"]) for t in threads], [
            ("f, line 1 (new) at b", "why?", "waiting on you"),
            ("f, whole file at b", "ok?", "waiting on the agent"),
            ("g, whole file at b", "fine", "resolved")])
        self.assertEqual([m["id"] for m in threads[0]["messages"]], ["ev_1", "ev_2"])
        legacy = dict(review, replies=[{"id": "ev_5", "created_at": "2026-01-01T00:00:09Z", "author": "agent:x", "body": "answer"}])
        (thread,) = lr.review_threads([legacy])
        self.assertEqual((thread["anchor"], thread["note"], thread["state"]), ("f, line 1 (new)", "why?", "waiting on you"))
        self.assertEqual(lr.review_threads([{"role": "review", "created_at": "x", "body": self.approved("a", "b")}]), [])

    def test_plannotator_runs_resolve_the_range_once_and_record_only_decisions(self):
        ctx = self.context()
        ctx.lattice = "false"
        seen = []
        original = lr.plannotator_args
        lr.plannotator_args = lambda *args, **kw: seen.append((args, kw)) or original(*args, **kw)
        try:
            ctx.plannotator = fake_plannotator(self.tools)
            job = ctx.start_plannotator("AB-2", record_on="AB-2", base=self.c + "^", head=self.c)
            wait_for(job)
        finally:
            lr.plannotator_args = original
        self.assertEqual(seen[0][0][1:], (self.b, self.c))
        self.assertEqual(job.what, "patch %s..%s" % (self.b[:12], self.c[:12]))
        self.assertIsNone(job.result_path)
        self.assertIn("not recorded", job.error)
        self.assertEqual(job.decision, "annotated")
        ctx.plannotator = fake_plannotator(self.tools, decision=None, exit_code=2)
        job = ctx.start_plannotator("AB-2", record_on="AB-2", base=self.c + "^", head=self.c)
        wait_for(job)
        self.assertIn("exited 2", job.error)
        self.assertIsNone(job.result_path)
        self.assertFalse(job.out_path.exists())
        ctx.plannotator = fake_plannotator(self.tools, decision="dismissed", message="")
        job = ctx.start_plannotator("AB-2", record_on="AB-2", base=self.c + "^", head=self.c)
        wait_for(job)
        self.assertTrue(job.done and not job.error)
        self.assertIsNone(job.result_path)
        self.assertFalse(job.out_path.exists())
        ctx.plannotator = fake_plannotator(self.tools, decision="approved", message={"not": "a string"})
        job = ctx.start_plannotator("AB-2", record_on="AB-2", base=self.c + "^", head=self.c)
        wait_for(job)
        self.assertEqual((job.done, job.decision), (True, "approved"))
        self.assertIn("not recorded", job.error)
        with self.assertRaises(RuntimeError):
            ctx.start_plannotator("AB-2", record_on="AB-2", base="nope", head=self.c)
        ctx.plannotator = fake_plannotator(self.tools, delay=1)
        first = ctx.start_plannotator("AB-2", record_on="AB-2", base=self.c + "^", head=self.c)
        with self.assertRaises(RuntimeError):
            ctx.start_plannotator("AB-2", record_on="AB-2", base=self.c + "^", head=self.c)
        second = ctx.start_plannotator("AB-4", record_on="AB-4", base=self.b, head="task/ab-4")
        self.assertNotEqual(first.out_path, second.out_path)
        wait_for(first)
        wait_for(second)
        self.assertEqual(lr.session_url(first.err_path.read_text()), "http://localhost:4242")
        ctx.plannotator = fake_plannotator(self.tools, delay=5)
        abandoned = ctx.start_plannotator("AB-2", record_on="AB-2", base=self.c + "^", head=self.c)
        wait_file(abandoned.err_path)
        ctx.close_session("AB-2")
        wait_for(abandoned)
        self.assertEqual((abandoned.decision, abandoned.error, abandoned.result_path), ("dismissed", None, None))
        self.assertFalse(abandoned.out_path.exists())
        self.assertIsNotNone(ctx.start_plannotator("AB-2", record_on="AB-2", base=self.c + "^", head=self.c))
        ctx.close_all()

    def test_file_names_and_binary_content_survive(self):
        (self.repo / "caf\u00e9.txt").write_text("caf\u00e9\n")
        blob = bytes(range(256)) * 4
        (self.repo / "blob.bin").write_bytes(blob)
        git(self.repo, "add", "caf\u00e9.txt", "blob.bin")
        git(self.repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "feat: odd files\n\nTask: AB-11")
        head = git(self.repo, "rev-parse", "HEAD")
        self.assertEqual(lr.changed_files(self.repo, head + "^", head),
                         [{"status": "A", "path": "blob.bin", "old_path": "blob.bin"}, {"status": "A", "path": "caf\u00e9.txt", "old_path": "caf\u00e9.txt"}])
        ctx = self.context()
        ctx.code = fake_code(self.tools)
        ctx.code_diff(head + "^", head, "blob.bin", "blob.bin", "A")
        left, right = wait_file(self.tools / "code.log").split()[-2:]
        self.assertEqual((Path(left).read_bytes(), Path(right).read_bytes()), (b"", blob))
        ctx.code_diff(head + "^", head, "caf\u00e9.txt", "caf\u00e9.txt", "A")
        right = wait_file(self.tools / "code.log", lines=2).splitlines()[-1].split()[-1]
        self.assertTrue(right.endswith("-caf\u00e9.txt"))
        self.assertEqual(Path(right).read_text(), "caf\u00e9\n")

    def test_local_host(self):
        for value in ("127.0.0.1:8798", "localhost:45119", "http://127.0.0.1:8798", "http://localhost:45119", "[::1]:8798"):
            self.assertTrue(lr.local_host(value), value)
        for value in ("evil.example:8798", "http://evil.example", "", None, "127.0.0.1.evil.example"):
            self.assertFalse(lr.local_host(value), value)
        self.assertTrue(lr.same_origin("http://localhost:45119", "localhost:45119"))
        self.assertTrue(lr.same_origin("http://127.0.0.1:8798", "127.0.0.1:8798"))
        for value in ("http://127.0.0.1:1", "https://127.0.0.1:8798", "http://localhost:8798", "null", ""):
            self.assertFalse(lr.same_origin(value, "127.0.0.1:8798"), value)


class SectionTests(RepoFixture):
    def setUp(self):
        super().setUp()
        StubDashboard.received = []
        StubDashboard.static_dir = self.repo / "static"
        StubDashboard.static_dir.mkdir()
        (StubDashboard.static_dir / "index.html").write_text("<html><head><title>d</title></head><body>board</body></html>")
        self.ctx = self.context()
        self.ctx.plannotator = "/nonexistent/plannotator"
        self.ctx.code = fake_code(self.tools)
        self.calls = []
        self.ctx.board_write = lambda key, *args: self.calls.append(args) or True
        self.reviews = {}
        self.ctx.comments = lambda sid: self.reviews.get(sid, [])
        self.server = serve(lr.make_handler(self.ctx, base=StubDashboard, static_dir=StubDashboard.static_dir))
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def test_dashboard_pages_get_the_hook_and_writes_are_guarded(self):
        status, index, _ = call(self.base + "/")
        self.assertEqual(status, 200)
        self.assertIn(lr.HOOK + "</head>", index)
        self.assertIn("board</body>", index)
        self.assertEqual(json.loads(call(self.base + "/api/tasks/task_AB2")[1])["data"]["path"], "/api/tasks/task_AB2")
        self.assertEqual(call(self.base + "/", headers={"Host": "evil.example:1"})[0], 403)
        body = json.dumps({"status": "todo", "actor": "dashboard:web"}).encode()
        headers = origin(self.base)
        self.assertEqual(call(self.base + "/api/tasks/task_AB9/status", body, dict(headers, Origin="http://evil.example"))[0], 403)
        self.assertEqual(call(self.base + "/api/tasks/task_AB9/status", body, dict(headers, Origin="http://127.0.0.1:1"))[0], 403)
        self.assertEqual(call(self.base + "/api/tasks/task_AB9/status", body, {"Content-Type": "application/json"})[0], 403)
        self.assertEqual(call(self.base + "/api/tasks/task_AB9/status", b"not json", headers)[0], 400)
        self.assertEqual(call(self.base + "/api/tasks/task_AB9/status", b"[1]", headers)[0], 400)
        self.assertEqual(call(self.base + "/api/tasks/task_AB9/status", b"{" + b" " * lr.MAX_BODY + b"}", headers)[0], 413)
        self.assertEqual(StubDashboard.received, [])
        self.assertEqual(call(self.base + "/api/tasks/task_AB9/status", body, headers)[0], 200)
        self.assertEqual(StubDashboard.received[-1], ("/api/tasks/task_AB9/status", {"status": "todo", "actor": "human:t"}))

    def test_done_through_the_dashboard_needs_an_approved_current_review(self):
        done = json.dumps({"status": "done", "actor": "dashboard:web"}).encode()
        headers = origin(self.base)
        status, body, _ = call(self.base + "/api/tasks/task_AB2/status", done, headers)
        self.assertEqual((status, json.loads(body)["error"]["code"]), (409, "REVIEW_REQUIRED"))
        self.assertIn("no Plannotator review", json.loads(body)["error"]["message"])
        self.assertEqual(call(self.base + "/api/tasks/task_AB2/status?view=board", b"  \n" + done, headers)[0], 409)
        self.assertEqual(call(self.base + "/api/tasks/task_AB2/status/", done, headers)[0], 409)
        self.assertEqual(StubDashboard.received, [])
        self.reviews["AB-2"] = [{"role": "review", "created_at": "2026-01-01T00:00:00Z", "body": self.approved(self.a, self.b)}]
        self.assertIn("commits arrived after your review", json.loads(call(self.base + "/api/tasks/task_AB2/status", done, headers)[1])["error"]["message"])
        self.reviews["AB-2"] = [{"role": "review", "created_at": "2026-01-01T00:00:00Z", "body": self.approved(self.b, self.c)}]
        self.assertEqual(call(self.base + "/api/tasks/task_AB2/status", done, headers)[0], 200)
        self.assertEqual(StubDashboard.received[-1][1]["status"], "done")
        self.assertEqual(call(self.base + "/api/tasks/task_AB9/status", done, headers)[0], 200)

    def test_review_section_offers_only_what_the_task_allows(self):
        split = call(self.base + "/review/t/AB-1")[1]
        self.assertEqual(split.count(">Plannotator</button>"), 2)
        self.assertNotIn("the whole range", split)
        self.assertIn("Completion: no Plannotator review", split)
        branch = call(self.base + "/review/t/AB-4")[1]
        self.assertIn("the whole range", branch)
        self.assertNotIn("feedback only", branch)
        self.assertIn(">diff</button>", branch)
        self.assertNotIn(">open</button>", branch)
        self.assertNotIn("vscode://", branch)
        self.assertIn("no Plannotator review", branch)
        none = call(self.base + "/review/t/AB-9")[1]
        self.assertIn("no linked branch", none)
        self.assertNotIn("<button", none)
        self.assertNotIn("Completion", none)
        (self.repo / "scratch").write_text("x\n")
        here = lr.home_short(self.repo)
        self.assertIn("uncommitted changes in %s, feedback only" % here, call(self.base + "/review/t/AB-9")[1])
        self.assertIn("uncommitted changes in %s, feedback only" % here, call(self.base + "/review/t/AB-10")[1])
        self.assertNotIn("uncommitted changes in", call(self.base + "/review/t/AB-2")[1])
        self.reviews["AB-2"] = [{"id": "ev_r1", "role": "review", "created_at": "2026-01-01T00:00:00Z", "author": "human:t",
                                 "body": "Plannotator annotated (patch x), s\n%s%s..%s\n\nDo not accept; fix this first.\n" % (lr.REVIEWED, self.b, self.c)}]
        page = call(self.base + "/review/t/AB-2")[1]
        self.assertIn("changes requested", page)
        self.assertIn("Do not accept", page)
        self.assertIn("waiting on the agent", page)
        self.assertIn("send the agent session the task ID AB-2", page)
        self.assertNotIn("Mark done", page)
        self.reviews["AB-2"].append({"role": "review", "created_at": "2026-01-02T00:00:00Z", "author": "human:t", "body": self.approved(self.b, self.c)})
        page = call(self.base + "/review/t/AB-2")[1]
        self.assertIn("1 review thread(s) are not resolved", page)
        self.assertIn("Approved at " + self.c[:12] + ". 1 thread(s) still open", page)
        self.assertNotIn("Move to in progress", page)
        self.assertNotIn("Mark done", page)
        self.reviews["AB-2"][0]["reactions"] = {lr.RESOLVED: ["human:t"]}
        page = call(self.base + "/review/t/AB-2")[1]
        self.assertIn("Mark done: approved at " + self.c[:12], page)
        self.assertIn(">Reopen</button>", page)
        self.assertEqual(call(self.base + "/review/t/AB-99")[0], 404)
        status, _, headers = call(self.base + "/t/AB-2")
        self.assertEqual((status, headers["Location"]), (303, "/#/task/task_AB2"))

    def test_plannotator_button_lands_in_the_session_in_this_browser(self):
        self.ctx.plannotator = fake_plannotator(self.tools, delay=5)
        status, _, headers = call(self.base + "/review/t/AB-2/plannotator", form(self.ctx, base=self.c + "^", head=self.c))
        self.assertEqual((status, headers["Location"]), (303, "http://localhost:4242"))
        status, _, headers = call(self.base + "/review/t/AB-2/plannotator", form(self.ctx, base=self.c + "^", head=self.c))
        self.assertEqual((status, headers["Location"]), (303, "http://localhost:4242"))
        section = call(self.base + "/review/t/AB-2")[1]
        self.assertIn("Plannotator running", section)
        self.assertIn("href='http://localhost:4242'", section)
        self.assertIn(">Close session</button>", section)
        self.assertIn("target='_blank'", section)
        self.assertEqual(call(self.base + "/review/t/AB-2/close", form(self.ctx))[0], 303)
        wait_for(self.ctx.jobs["AB-2"])
        section = call(self.base + "/review/t/AB-2")[1]
        self.assertIn("closed without a review", section)
        self.assertNotIn("Close session", section)
        self.ctx.plannotator = "/nonexistent/plannotator"
        status, body, _ = call(self.base + "/review/t/AB-2/plannotator", form(self.ctx, base=self.c + "^", head=self.c))
        self.assertEqual(status, 200)
        self.assertIn("No such file", body)

    def test_review_actions_need_the_token_and_the_gate(self):
        self.assertEqual(call(self.base + "/review/t/AB-2/open", b"token=wrong&path=f")[0], 403)
        self.assertEqual(call(self.base + "/review/t/AB-2/open", form(self.ctx, path="f"), {"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(call(self.base + "/review/t/AB-2/open", form(self.ctx, path="f"))[0], 303)
        self.assertIn("--reuse-window " + str(self.repo / "f"), wait_file(self.tools / "code.log"))
        call(self.base + "/review/t/AB-2/open", form(self.ctx, path="../outside"))
        self.assertIn("not a repository path", call(self.base + "/review/t/AB-2")[1])
        self.reviews["AB-2"] = [{"role": "review", "created_at": "2026-01-01T00:00:00Z", "body": self.approved(self.a, self.b)}]
        call(self.base + "/review/t/AB-2/complete", form(self.ctx))
        self.assertIn("not completed", call(self.base + "/review/t/AB-2")[1])
        self.assertEqual(self.calls, [])
        self.reviews["AB-2"] = [{"role": "review", "created_at": "2026-01-01T00:00:00Z", "body": self.approved(self.b, self.c)}]
        call(self.base + "/review/t/AB-2/complete", form(self.ctx))
        self.assertEqual(self.calls, [("status", "AB-2", "done", "--no-auto-review")])

    def test_thread_actions_write_to_the_board_as_the_owner(self):
        call(self.base + "/review/t/AB-2/reply", form(self.ctx, parent="ev_1", body="  still unclear  "))
        self.assertEqual(self.calls[0][:4], ("comment", "AB-2", "--reply-to", "ev_1"))
        self.assertEqual(self.calls[0][4], "--file")
        call(self.base + "/review/t/AB-2/reply", form(self.ctx, parent="ev_1", body=" "))
        self.assertIn("the reply is empty", call(self.base + "/review/t/AB-2")[1])
        call(self.base + "/review/t/AB-2/resolve", form(self.ctx, comment="ev_1"))
        call(self.base + "/review/t/AB-2/reopen", form(self.ctx, comment="ev_1"))
        call(self.base + "/review/t/AB-2/rework", form(self.ctx))
        self.assertEqual(self.calls[1:], [("react", "AB-2", "ev_1", lr.RESOLVED), ("unreact", "AB-2", "ev_1", lr.RESOLVED),
                                          ("status", "AB-2", "in_progress", "--no-auto-review")])
        del self.calls[:]
        call(self.base + "/review/t/AB-2/reply", form(self.ctx, parent="ev_1", body="ok, works for me", resolve="1"))
        self.assertEqual([c[0] for c in self.calls], ["comment", "react"])
        self.assertEqual(self.calls[1], ("react", "AB-2", "ev_1", lr.RESOLVED))
        del self.calls[:]
        call(self.base + "/review/t/AB-2/reply", form(self.ctx, parent="ev_1", body="", resolve="1"))
        self.assertEqual(self.calls, [("react", "AB-2", "ev_1", lr.RESOLVED)])
        self.assertEqual(call(self.base + "/review/t/AB-2/resolve", b"token=wrong&comment=ev_1")[0], 403)


@unittest.skipUnless(HAVE_CLI, "lattice not on PATH")
class CliTests(RepoFixture):
    def test_review_lands_on_the_task_and_completes_it_through_the_cli(self):
        board = init_board(self.repo)
        sid = lattice(board, "create", "a task", "--actor", "agent:test", "--quiet")
        commit(self.repo, "g", "feat: g\n\nTask: " + sid)
        lattice(board, "status", sid, "in_progress", "--no-auto-review", "--actor", "agent:test")
        lattice(board, "status", sid, "in_review", "--no-auto-review", "--actor", "agent:test")
        ctx = self.context(board=board, repo=self.repo)
        ctx.plannotator = fake_plannotator(self.tools, decision="approved", message="Code review completed")
        rng = lr.resolve_range(self.repo, lr.find_task(board, sid), "main")
        job = ctx.start_plannotator(sid, record_on=sid, base=rng["base"], head=rng["head"])
        wait_for(job)
        self.assertTrue(job.done and not job.error, job.error)
        comments = ctx.comments(sid)
        self.assertEqual([c["role"] for c in comments], ["review"])
        self.assertIn(lr.REVIEWED + rng["base_sha"] + ".." + rng["head_sha"], comments[0]["body"])
        self.assertEqual(lr.review_decision(comments[0]["body"]), "approved")
        self.assertIsNone(lr.completion_block(self.repo, lr.find_task(board, sid), "main", comments))
        StubDashboard.static_dir = self.repo / "static"
        server = serve(lr.make_handler(ctx, base=StubDashboard, static_dir=StubDashboard.static_dir))
        base = "http://127.0.0.1:%d" % server.server_address[1]
        try:
            self.assertIn("Mark done: approved at " + rng["head_sha"][:12], call(base + "/review/t/" + sid)[1])
            call(base + "/review/t/%s/complete" % sid, form(ctx))
            self.assertEqual(lr.find_task(board, sid)["status"], "done")
            self.assertNotIn("Mark done", call(base + "/review/t/" + sid)[1])
        finally:
            server.shutdown()
            server.server_close()

    def test_line_notes_become_threads_that_keep_one_history_per_line_and_gate_completion(self):
        board = init_board(self.repo)
        sid = lattice(board, "create", "a task", "--actor", "agent:test", "--quiet")
        commit(self.repo, "h", "feat: h\n\nTask: " + sid, content="first line\nsecond line")
        ctx = self.context(board=board, repo=self.repo)
        rng = lr.resolve_range(self.repo, lr.find_task(board, sid), "main")
        sha = rng["head_sha"][:12]

        def review(decision, message):
            ctx.plannotator = fake_plannotator(self.tools, decision=decision, message=message)
            job = ctx.start_plannotator(sid, record_on=sid, base=rng["base"], head=rng["head"])
            wait_for(job)
            self.assertTrue(job.done and not job.error, job.error)
            return lr.review_threads(ctx.comments(sid))
        threads = review("annotated", "# Code Review Feedback\n\n## h\n\n### Line 2 (new)\nwhy this line?\n\n"
                                      "### File Comment\nname it better\n\n\n\nTreat the findings above as input.")
        self.assertEqual([(t["anchor"], t["note"], t["state"]) for t in threads], [
            ("h, line 2 (new) at " + sha, "> second line\nwhy this line?", "waiting on the agent"),
            ("h, whole file at " + sha, "name it better", "waiting on the agent")])
        lattice(board, "comment", sid, "--reply-to", threads[0]["root"]["id"], "Status: answered\nAnswer: it closes the loop", "--actor", "agent:test")
        self.assertEqual([t["state"] for t in lr.review_threads(ctx.comments(sid))], ["waiting on you", "waiting on the agent"])
        threads = review("annotated", "# Code Review Feedback\n\n## h\n\n### Line 2 (new)\nstill not clear why")
        self.assertEqual(len(threads), 2)
        bodies = [m["body"].strip() for m in threads[0]["messages"][1:]]
        self.assertEqual(bodies[0], "Status: answered\nAnswer: it closes the loop")
        self.assertTrue(bodies[1].startswith(lr.FOLLOW_UP) and bodies[1].endswith("still not clear why"), bodies[1])
        self.assertEqual(threads[0]["state"], "waiting on the agent")
        review("approved", "Code review completed")
        self.assertIn("2 review thread(s) are not resolved", lr.completion_block(self.repo, lr.find_task(board, sid), "main", ctx.comments(sid)))
        StubDashboard.static_dir = self.repo / "static"
        server = serve(lr.make_handler(ctx, base=StubDashboard, static_dir=StubDashboard.static_dir))
        base = "http://127.0.0.1:%d" % server.server_address[1]
        try:
            self.assertIn("&gt; second line", call(base + "/review/t/" + sid)[1])
            call(base + "/review/t/%s/reply" % sid, form(ctx, parent=threads[1]["root"]["id"], body="ok, leave it"))
            for t in threads:
                call(base + "/review/t/%s/resolve" % sid, form(ctx, comment=t["root"]["id"]))
            final = lr.review_threads(ctx.comments(sid))
            self.assertEqual([t["state"] for t in final], ["resolved", "resolved"])
            self.assertEqual([m["body"].strip() for m in final[1]["messages"][1:]], ["ok, leave it"])
            self.assertIsNone(lr.completion_block(self.repo, lr.find_task(board, sid), "main", ctx.comments(sid)))
            self.assertIn("Mark done", call(base + "/review/t/" + sid)[1])
        finally:
            server.shutdown()
            server.server_close()
    def test_a_note_on_the_place_of_an_older_unsplit_review_continues_its_thread(self):
        board = init_board(self.repo)
        sid = lattice(board, "create", "a task", "--actor", "agent:test", "--quiet")
        commit(self.repo, "k", "feat: k\n\nTask: " + sid)
        ctx = self.context(board=board, repo=self.repo)
        rng = lr.resolve_range(self.repo, lr.find_task(board, sid), "main")
        older = self.repo / "older.md"
        older.write_text("Plannotator annotated (patch x), s\n%s%s..%s\n\n## k\n\n### File Comment\nwhere are the replies?\n" % (
            lr.REVIEWED, rng["base_sha"], rng["head_sha"]))
        lattice(board, "comment", sid, "--file", str(older), "--role", "review", "--actor", "human:t")
        ctx.plannotator = fake_plannotator(self.tools, decision="annotated", message="## k\n\n### File Comment\nstill looking")
        job = ctx.start_plannotator(sid, record_on=sid, base=rng["base"], head=rng["head"])
        wait_for(job)
        self.assertTrue(job.done and not job.error, job.error)
        (thread,) = lr.review_threads(ctx.comments(sid))
        self.assertEqual(thread["anchor"], "k, whole file")
        self.assertTrue(thread["messages"][-1]["body"].strip().endswith("still looking"))


@unittest.skipUnless(HAVE_CLI and HAVE_MODULE, "lattice not importable; run with the Python that has lattice installed")
class DashboardTests(RepoFixture):
    def test_the_real_dashboard_runs_in_process_with_the_review_section(self):
        board = init_board(self.repo)
        sid = lattice(board, "create", "a task", "--actor", "agent:test", "--quiet")
        commit(self.repo, "g", "feat: g\n\nTask: " + sid)
        lattice(board, "status", sid, "in_progress", "--no-auto-review", "--actor", "agent:test")
        lattice(board, "status", sid, "in_review", "--no-auto-review", "--actor", "agent:test")
        ctx = self.context(board=board, repo=self.repo)
        ctx.plannotator = fake_plannotator(self.tools, decision="approved", message="fine")
        ctx.code = fake_code(self.tools)
        server = serve(lr.make_handler(ctx))
        base = "http://127.0.0.1:%d" % server.server_address[1]
        try:
            status, index, _ = call(base + "/")
            self.assertEqual(status, 200)
            self.assertIn(lr.HOOK + "</head>", index)
            self.assertIn("<html", index)
            tasks = json.loads(call(base + "/api/tasks")[1])["data"]
            self.assertEqual([t["short_id"] for t in tasks], [sid])
            task_id = tasks[0]["id"]
            self.assertIn("the whole range", call(base + "/review/t/" + sid)[1])
            done = json.dumps({"status": "done", "actor": "dashboard:web"}).encode()
            headers = origin(base)
            status, body, _ = call(base + "/api/tasks/%s/status" % task_id, done, headers)
            self.assertEqual((status, json.loads(body)["error"]["code"]), (409, "REVIEW_REQUIRED"))
            self.assertEqual(lr.find_task(board, sid)["status"], "in_review")
            rng = lr.resolve_range(self.repo, lr.find_task(board, sid), "main")
            job = ctx.start_plannotator(sid, record_on=sid, base=rng["base"], head=rng["head"])
            wait_for(job)
            self.assertTrue(job.done and not job.error, job.error)
            status, body, _ = call(base + "/api/tasks/%s/status" % task_id, done, headers)
            self.assertEqual(status, 200, body)
            self.assertEqual(lr.find_task(board, sid)["status"], "done")
            status, body, _ = call(base + "/api/tasks/%s/open-plans" % task_id, b"{}", headers)
            self.assertEqual(status, 200, body)
            plan = board / ".lattice" / "plans" / (task_id + ".md")
            self.assertTrue(plan.is_file())
            self.assertEqual(json.loads(body)["data"]["opened"], str(plan.resolve()))
            self.assertIn("--reuse-window " + str(plan.resolve()), wait_file(self.tools / "code.log"))
            status, body, _ = call(base + "/api/tasks/%s/open-notes" % task_id, b"{}", headers)
            self.assertEqual((status, json.loads(body)["error"]["code"]), (404, "NOT_FOUND"))
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
