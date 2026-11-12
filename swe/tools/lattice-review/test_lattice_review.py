import http.client
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
from types import SimpleNamespace
from unittest import mock

import lattice_review as lr

os.environ.pop("LATTICE_ROOT", None)
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


def fake_plannotator(where, decision="annotated", message="line 2: rename it", exit_code=0, delay=0, key="message"):
    """A stand-in that swallows the patch and answers like plannotator --json
    (annotate mode answers with the key "feedback")."""
    script = where / "plannotator"
    record = json.dumps({"decision": decision, key: message}) if decision else "usage error"
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


# What plannotator annotate --gate --json printed for a real session on a
# plan with one line comment and one global comment (v0.28.48).
PLAN_FEEDBACK = ('# File Feedback\n\nI\'ve reviewed this file and have 2 pieces of feedback:\n\n'
                 '## 1. General feedback about the file\n> overall: add a rollback step\n\n'
                 '## 2. (line 10) Feedback on: "list"\n> why refresh instead of invalidating the query?\n\n---\n')


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
        return lr.Context(Namespace(board=str(board or self.repo), repo=str(repo) if repo else None, main="main",
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

    def test_commits_that_mention_a_task_are_referenced_except_its_own(self):
        mention = commit(self.repo, "m", "docs: follow-up for AB-2 in the runbook")
        refs = lr.commit_mentions(self.repo, "AB-2", {self.c})
        self.assertEqual([x["text"] for x in refs], ["mentioned this task in commit %s docs: follow-up for AB-2 in the runbook" % mention[:12]])
        self.assertEqual(lr.commit_mentions(self.repo, "AB-1", {self.b, self.d}), [])

    def test_a_mention_on_an_unmerged_branch_names_the_branch(self):
        git(self.repo, "checkout", "-q", "-b", "feature/AB-2-x-a")
        side = commit(self.repo, "s", "wip: try another way for AB-2")
        git(self.repo, "checkout", "-q", "main")
        landed = commit(self.repo, "m", "docs: follow-up for AB-2 in the runbook")
        texts = [x["text"] for x in lr.commit_mentions(self.repo, "AB-2", {self.c}, "main")]
        self.assertIn("mentioned this task in commit %s wip: try another way for AB-2 (on feature/AB-2-x-a, not merged)" % side[:12], texts)
        self.assertIn("mentioned this task in commit %s docs: follow-up for AB-2 in the runbook" % landed[:12], texts)

    def test_board_writes_report_in_the_owners_words(self):
        self.assertEqual(lr.written(("react", "AB-2", "ev_1", lr.RESOLVED)), "Thread resolved.")
        self.assertEqual(lr.written(("unreact", "AB-2", "ev_1", lr.RESOLVED)), "Thread reopened.")
        self.assertEqual(lr.written(("status", "AB-2", "done", "--no-auto-review")), "Marked done.")
        self.assertEqual(lr.written(("status", "AB-2", "in_progress", "--no-auto-review")), "Moved to in progress.")

    def test_unlinked_task_has_no_work(self):
        self.assertEqual(lr.resolve_range(self.repo, lr.find_task(self.repo, "AB-9"), "main")["mode"], "none")

    def test_candidate_branches_stay_out_until_one_is_linked(self):
        for letter in "ab":
            git(self.repo, "checkout", "-q", "-b", "feature/AB-9-x-" + letter, "main")
            commit(self.repo, "candidate-" + letter, "feat: candidate %s\n\nTask: AB-9" % letter)
        git(self.repo, "checkout", "-q", "main")
        self.assertEqual(lr.resolve_range(self.repo, lr.find_task(self.repo, "AB-9"), "main")["mode"], "none")
        task(self.repo, "AB-9", "in_review", "the owner picked b", branch="feature/AB-9-x-b")
        rng = lr.resolve_range(self.repo, lr.find_task(self.repo, "AB-9"), "main")
        self.assertEqual((rng["mode"], rng["head"]), ("branch", "feature/AB-9-x-b"))
        self.assertEqual([c["subject"] for c in rng["commits"]], ["feat: candidate b"])

    def test_repository_config_cannot_make_git_run_a_program(self):
        marker = self.tools / "ran"
        probe = self.tools / "probe"
        probe.write_text("#!/bin/sh\ntouch '%s'\n" % marker)
        probe.chmod(0o755)
        shutil.copy(probe, self.repo / ".git" / "hooks" / "post-index-change")
        git(self.repo, "config", "core.fsmonitor", str(probe))
        (self.repo / "a").write_text("changed\n")
        lr.run_git(self.repo, "status", "--porcelain")
        self.assertFalse(marker.exists())
        git(self.repo, "config", "--unset", "core.fsmonitor")
        (self.tools / "included").write_text('[diff "x"]\n\ttextconv = %s\n' % probe)
        for key, value in (("diff.external", str(probe)), ("filter.x.clean", str(probe)),
                           ("include.path", str(self.tools / "included"))):
            git(self.repo, "config", key, value)
            with self.assertRaises(RuntimeError):
                lr.changed_files(self.repo, self.a, self.d)
            git(self.repo, "config", "--unset", key)
        self.assertEqual(len(lr.changed_files(self.repo, self.a, self.d)), 3)
        self.assertFalse(marker.exists())

    def test_config_written_after_the_check_does_not_run_a_program(self):
        marker = self.tools / "ran"
        probe = self.tools / "probe"
        probe.write_text("#!/bin/sh\ntouch '%s'\n" % marker)
        probe.chmod(0o755)
        (self.repo / ".git" / "info" / "attributes").write_text("* diff=x\n")
        keys = ("diff.external", "diff.x.command", "diff.x.textconv")
        checked = lr.git_env

        def check_then_change(repo):
            env = checked(repo)
            for key in keys:
                git(self.repo, "config", key, str(probe))
            return env

        lr.git_env = check_then_change
        outputs = []
        try:
            for args in (("diff", self.a, self.d), ("log", "-p", "-1", self.d), ("show", self.d + ":d")):
                outputs.append(lr.run_git(self.repo, *args))
                for key in keys:
                    git(self.repo, "config", "--unset", key)
        finally:
            lr.git_env = checked
        self.assertIn("+d", outputs[0])
        self.assertFalse(marker.exists())

    def test_invalid_repository_config_is_refused(self):
        with (self.repo / ".git" / "config").open("a") as config:
            config.write("\n[invalid config\n")
        with self.assertRaises(RuntimeError):
            lr.run_git(self.repo, "log", "-1")

    def test_git_errors_are_visible_on_the_review_page(self):
        ctx = self.context()
        handler = object.__new__(lr.make_handler(ctx, base=StubDashboard))
        handler.path, handler.headers = "/review/t/AB-2", {"Host": "localhost"}
        handler.send_page = mock.Mock()
        with (self.repo / ".git" / "config").open("a") as config:
            config.write("\n[invalid config\n")
        handler.do_GET()
        body, status = handler.send_page.call_args.args
        self.assertEqual(status, 409)
        self.assertIn(b"bad config", body)

    def signed_commit(self):
        raw = subprocess.check_output(["git", "-C", str(self.repo), "cat-file", "commit", self.c])
        headers, message = raw.split(b"\n\n", 1)
        raw = headers + b"\ngpgsig -----BEGIN PGP SIGNATURE-----\n fake\n -----END PGP SIGNATURE-----\n\n" + message
        return subprocess.check_output(["git", "-C", str(self.repo), "hash-object", "-t", "commit", "-w", "--stdin"],
                                       input=raw).decode().strip()

    def test_signature_helpers_do_not_run_even_if_config_changes_after_the_check(self):
        signed = self.signed_commit()
        marker = self.tools / "signature-ran"
        probe = self.tools / "signature"
        probe.write_text("#!/bin/sh\ntouch '%s'\nexit 1\n" % marker)
        probe.chmod(0o755)
        checked = lr.git_env

        def check_then_change(repo):
            env = checked(repo)
            git(self.repo, "config", "log.showSignature", "true")
            git(self.repo, "config", "gpg.program", str(probe))
            return env

        lr.git_env = check_then_change
        try:
            self.assertEqual(lr.log_commits(self.repo, signed)[-1]["hash"], signed)
        finally:
            lr.git_env = checked
        self.assertFalse(marker.exists())

    def test_missing_promisor_objects_fail_without_starting_a_transport(self):
        marker = self.tools / "transport-ran"
        probe = self.tools / "transport"
        probe.write_text("#!/bin/sh\ntouch '%s'\nexit 1\n" % marker)
        probe.chmod(0o755)
        blob = git(self.repo, "rev-parse", self.c + ":c")
        git(self.repo, "config", "remote.origin.promisor", "true")
        git(self.repo, "config", "remote.origin.url", "ext::" + str(probe))
        git(self.repo, "config", "protocol.ext.allow", "always")
        (self.repo / ".git" / "objects" / blob[:2] / blob[2:]).unlink()
        with self.assertRaises(RuntimeError):
            lr.run_git(self.repo, "show", self.c + ":c")
        self.assertFalse(marker.exists())

    def test_plannotator_args(self):
        args, patch = lr.plannotator_args("pl", base="abc^", head="abc")
        self.assertEqual((args, patch), (["pl", "--browser", "none", "review", "--patch-file", "-", "--json"], ["diff", "abc^", "abc"]))

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
        malformed = {"role": "review", "created_at": "2026-01-05T00:00:00Z", "author": "human:t", "body": "Plannotator approved (x), s\nReviewed: not-yet\n"}
        older = {"role": "review", "created_at": "2026-01-01T00:00:00Z", "author": "human:t", "body": self.approved(self.a, self.b)}
        plain = {"role": "review", "created_at": "2026-01-03T00:00:00Z", "author": "human:t", "body": "own words, no revision"}
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
        approved = {"role": "review", "created_at": "2026-01-01T00:00:00Z", "author": "human:t", "body": self.approved(self.b, self.c)}
        changes = {"role": "review", "created_at": "2026-01-02T00:00:00Z", "author": "human:t",
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

    def test_only_a_persons_review_counts_and_only_a_person_withdraws_it(self):
        task_record = lr.find_task(self.repo, "AB-2")
        by_agent = {"role": "review", "created_at": "2026-01-01T00:00:00Z", "author": "agent:x", "body": self.approved(self.b, self.c)}
        self.assertIsNone(lr.latest_review([by_agent]))
        self.assertIn("no Plannotator review", lr.completion_block(self.repo, task_record, "main", [by_agent]))
        by_owner = dict(by_agent, author="human:t")
        self.assertIs(lr.latest_review([by_agent, by_owner]), by_owner)
        self.assertIsNone(lr.completion_block(self.repo, task_record, "main", [by_agent, by_owner]))
        later_by_agent = dict(by_agent, created_at="2026-01-02T00:00:00Z", body=self.approved(self.a, self.b))
        self.assertIs(lr.latest_review([by_owner, later_by_agent]), by_owner)
        self.assertIsNone(lr.completion_block(self.repo, task_record, "main", [by_owner, later_by_agent]))
        withdrawn = {"role": "review", "created_at": "2026-01-03T00:00:00Z", "author": "human:t", "deleted": True, "body": ""}
        self.assertIn("deleted", lr.completion_block(self.repo, task_record, "main", [by_owner, later_by_agent, withdrawn]))
        self.assertIs(lr.latest_review([by_owner, dict(withdrawn, author="agent:x")]), by_owner)

    def test_an_automatic_merge_adds_nothing_even_when_both_sides_changed_neighbouring_lines(self):
        lines = ["l%d" % n for n in range(1, 9)]
        commit(self.repo, "table", "docs: table", "\n".join(lines))
        git(self.repo, "checkout", "-q", "-b", "left")
        commit(self.repo, "table", "docs: left", "\n".join(lines).replace("l3", "l3 left"))
        git(self.repo, "checkout", "-q", "main")
        commit(self.repo, "table", "docs: right", "\n".join(lines).replace("l5", "l5 right"))
        git(self.repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "merge", "-q", "--no-ff", "left", "-m", "merge left")
        merged = git(self.repo, "rev-parse", "HEAD")
        self.assertTrue(git(self.repo, "diff-tree", "-p", "--cc", "--no-commit-id", merged))
        self.assertTrue(lr.adds_nothing(self.repo, merged))
        git(self.repo, "checkout", "-q", "-b", "other", "HEAD~1")
        commit(self.repo, "other", "docs: other")
        git(self.repo, "checkout", "-q", "main")
        git(self.repo, "merge", "-q", "--no-ff", "--no-commit", "other")
        (self.repo / "table").write_text("written by hand\n")
        git(self.repo, "add", "table")
        git(self.repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "merge other")
        self.assertFalse(lr.adds_nothing(self.repo, git(self.repo, "rev-parse", "HEAD")))
        self.assertFalse(lr.adds_nothing(self.repo, git(self.repo, "rev-parse", "HEAD^2")))

    def test_earlier_approvals_cover_merged_history_but_not_new_work(self):
        record = lr.find_task(self.repo, "AB-2")
        ident = ("-c", "user.name=t", "-c", "user.email=t@example.invalid")

        def approval(day, base, head, **extra):
            return dict({"role": "review", "created_at": "2026-01-0%dT00:00:00Z" % day, "author": "human:t",
                         "body": self.approved(base, head)}, **extra)

        def merge(branch, message, extra=None):
            git(self.repo, "checkout", "-q", "main")
            commit(self.repo, "main-" + branch.replace("/", "-"), "chore: main moves on")
            git(self.repo, *ident, "merge", "-q", "--no-ff", "--no-commit", branch)
            if extra:
                (self.repo / extra).write_text("not reviewed\n")
                git(self.repo, "add", extra)
            git(self.repo, *ident, "commit", "-q", "-m", message)

        first = approval(1, self.b, self.c)
        c2 = commit(self.repo, "c2", "fix: more c\n\nTask: AB-2")
        second = approval(2, self.f, c2)
        self.assertIn("no single commit range", lr.completion_block(self.repo, record, "main", [second]))
        self.assertIsNone(lr.completion_block(self.repo, record, "main", [first, second]))
        withdrawn = {"role": "review", "created_at": "2026-01-01T12:00:00Z", "author": "human:t", "deleted": True, "body": ""}
        self.assertIn("no single commit range", lr.completion_block(self.repo, record, "main", [first, withdrawn, second]))
        live = dict(first, body=self.approved(self.b, self.c, " live"))
        self.assertIn("no single commit range", lr.completion_block(self.repo, record, "main", [live, second]))
        git(self.repo, "checkout", "-q", "-b", "fix/ab-2")
        c3 = commit(self.repo, "c3", "fix: c3\n\nTask: AB-2")
        merge("fix/ab-2", "Merge fix/ab-2\n\nTask: AB-2")
        third = approval(3, c2, c3)
        self.assertIsNone(lr.completion_block(self.repo, record, "main", [first, second, third]))
        git(self.repo, "checkout", "-q", "-b", "fix2/ab-2")
        c4 = commit(self.repo, "c4", "fix: c4\n\nTask: AB-2")
        merge("fix2/ab-2", "Merge fix2/ab-2\n\nTask: AB-2", extra="smuggled")
        fourth = approval(4, git(self.repo, "rev-parse", c4 + "^"), c4)
        self.assertIn("no single commit range", lr.completion_block(self.repo, record, "main", [first, second, third, fourth]))

    def test_completion_waits_until_every_approved_part_has_landed(self):
        record = lr.find_task(self.repo, "AB-4")
        x = commit(self.repo, "x", "fix: x\n\nTask: AB-4")
        reviews = [{"role": "review", "created_at": "2026-01-01T00:00:00Z", "author": "human:t", "body": self.approved(self.b, self.e)},
                   {"role": "review", "created_at": "2026-01-02T00:00:00Z", "author": "human:t", "body": self.approved(self.f, x)}]
        self.assertIn("not merged into main yet", lr.completion_block(self.repo, record, "main", reviews))
        git(self.repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "merge", "-q", "--no-ff", "-m", "merge", "task/ab-4")
        git(self.repo, "update-ref", "refs/remotes/origin/main", x)
        git(self.repo, "config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*")
        git(self.repo, "config", "branch.main.remote", "origin")
        git(self.repo, "config", "branch.main.merge", "refs/heads/main")
        self.assertIn("main is not pushed yet", lr.completion_block(self.repo, record, "main", reviews))
        git(self.repo, "update-ref", "refs/remotes/origin/main", "main")
        self.assertIsNone(lr.completion_block(self.repo, record, "main", reviews))

    def test_completion_waits_until_the_work_is_merged_pushed_and_evidenced(self):
        branch_task = lr.find_task(self.repo, "AB-4")
        approved = [{"role": "review", "created_at": "2026-01-01T00:00:00Z", "author": "human:t", "body": self.approved(self.b, self.e)}]
        self.assertIn("not merged into main yet", lr.completion_block(self.repo, branch_task, "main", approved))
        git(self.repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "merge", "-q", "--no-ff", "-m", "merge", "task/ab-4")
        self.assertIsNone(lr.completion_block(self.repo, branch_task, "main", approved))
        git(self.repo, "update-ref", "refs/remotes/origin/main", self.f)
        git(self.repo, "config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*")
        git(self.repo, "config", "branch.main.remote", "origin")
        git(self.repo, "config", "branch.main.merge", "refs/heads/main")
        self.assertIn("main is not pushed yet", lr.completion_block(self.repo, branch_task, "main", approved))
        git(self.repo, "update-ref", "refs/remotes/origin/main", "main")
        self.assertIsNone(lr.completion_block(self.repo, branch_task, "main", approved))
        criteria = [{"id": "AC-1", "retired": False}, {"id": "AC-2", "retired": False}, {"id": "AC-3", "retired": True}]
        open_work = dict(branch_task, acceptance_criteria=criteria, evidence_refs=[{"id": "ev_1", "criterion_ids": ["AC-2"]}])
        self.assertIn("no evidence is recorded yet for AC-1;", lr.completion_block(self.repo, open_work, "main", approved))
        evidenced = dict(open_work, evidence_refs=open_work["evidence_refs"] + [{"id": "ev_2", "criterion_ids": ["AC-1"]}])
        self.assertIsNone(lr.completion_block(self.repo, evidenced, "main", approved))

    def test_a_criterion_whose_newest_evidence_note_says_not_met_stays_open(self):
        def note(number, body, criteria, **more):
            return dict({"id": "ev_%d" % number, "body": body, "criterion_ids": criteria, "deleted": False,
                         "created_at": "2026-01-01T00:00:0%dZ" % number, "replies": []}, **more)
        task = {"acceptance_criteria": [{"id": "AC-1", "retired": False}, {"id": "AC-2", "retired": False}],
                "evidence_refs": [{"id": "ev_1", "criterion_ids": ["AC-1", "AC-2"]}]}
        met = note(1, "Met: the page loads in both clients.", ["AC-1", "AC-2"])
        self.assertIsNone(lr.criteria_block(task, [met]))
        open_again = note(2, "Not met: Codex has not run it yet.", ["AC-2"])
        self.assertIn("the newest evidence note for AC-2 says it is not met", lr.criteria_block(task, [met, open_again]))
        self.assertIsNone(lr.criteria_block(task, [met, dict(open_again, deleted=True)]))
        answered = note(3, "Met: Codex ran it at 1a2b3c4.", ["AC-2"])
        self.assertIsNone(lr.criteria_block(task, [met, open_again, answered]))
        in_a_reply = dict(met, replies=[note(4, "  not met: the check was mocked.", ["AC-1"])])
        self.assertIn("for AC-1 says it is not met", lr.criteria_block(task, [in_a_reply]))
        self.assertIsNone(lr.criteria_block(task, [note(1, "The earlier wording, with no verdict word.", ["AC-1", "AC-2"])]))

    def test_review_notes_are_split_by_file_and_line_without_the_appended_instructions(self):
        message = ("# Code Review Feedback\n\n**Diff:** static-patch\n\n## README.md\n\n### Line 239 (new)\n"
                   "why do we need this change?\n\nsecond paragraph\n\n### File Comment\nwhere are the replies?\n\n"
                   "## docs/a.md\n\n### Lines 3-5 (old)\nkeep this\n\n\n\n\n" + lr.DEFAULT_REVIEW_SUFFIX + "\n")
        self.assertEqual(lr.review_notes(message), [
            ("README.md", "line 239 (new)", "why do we need this change?\n\nsecond paragraph"),
            ("README.md", "whole file", "where are the replies?"),
            ("docs/a.md", "lines 3-5 (old)", "keep this")])
        text = "".join("line %d\n" % n for n in range(1, 20))
        self.assertEqual(lr.quoted_lines(text, "line 2 (new)"), ["> line 2"])
        self.assertEqual(lr.quoted_lines(text, "lines 3-12 (old)"), ["> line %d" % n for n in range(3, 8)])
        self.assertEqual(lr.quoted_lines(text, "whole file"), [])
        self.assertEqual(lr.review_notes("# Code Review\n\nNo changes requested."), [])
        spaced = "## a\n\n### Line 1 (new)\nfirst\n\n\n\nstill the first note\n\n### Line 5 (new)\nsecond\n\n\n\nown closing words.\n"
        self.assertEqual(lr.review_notes(spaced), [("a", "line 1 (new)", "first\n\n\n\nstill the first note"),
                                                   ("a", "line 5 (new)", "second\n\n\n\nown closing words.")])
        configured = ("Each note above is its own thread on the task. Answer each one in its thread, in the reply shape in "
                      ".lattice/context.md, before changing any code.")
        last = "## a\n\n### Line 5 (new)\nfirst paragraph\n\n\n\nlast paragraph\n\n\n\n" + configured + "\n"
        self.assertEqual(lr.review_notes(last, suffixes=[configured]), [("a", "line 5 (new)", "first paragraph\n\n\n\nlast paragraph")])
        builtin = "## a\n\n### Line 5 (new)\nkeep\n\n\n\n" + lr.DEFAULT_REVIEW_SUFFIX + "\n"
        self.assertEqual(lr.review_notes(builtin, suffixes=[]), [("a", "line 5 (new)", "keep\n\n\n\n" + lr.DEFAULT_REVIEW_SUFFIX)])
        self.assertEqual(lr.review_notes(builtin, suffixes=[lr.DEFAULT_REVIEW_SUFFIX]), [("a", "line 5 (new)", "keep")])
        quoted = "## a\n\n### Line 5 (new)\n" + lr.DEFAULT_REVIEW_SUFFIX.split(".")[0] + ". That is what I want too.\n\nAnd this.\n"
        self.assertEqual(lr.review_notes(quoted, suffixes=[lr.DEFAULT_REVIEW_SUFFIX]), [("a", "line 5 (new)", quoted.split("\n", 3)[3].strip())])
        partial = "## a\n\n### Line 5 (new)\nkeep\n\n\n\nTreat the findings above as unverified review input.\n"
        self.assertEqual(lr.review_notes(partial, suffixes=[lr.DEFAULT_REVIEW_SUFFIX]), [("a", "line 5 (new)", partial.split("\n", 3)[3].strip())])
        config = self.repo / "plannotator.json"
        self.assertEqual(lr.review_suffixes(str(config)), [lr.DEFAULT_REVIEW_SUFFIX])
        config.write_text(json.dumps({"prompts": {"review": {"denied": "\n\n\n\n" + configured + "\nSecond line."}}}))
        self.assertEqual(lr.review_suffixes(str(config)), [configured + "\nSecond line.", lr.DEFAULT_REVIEW_SUFFIX])
        config.write_text(json.dumps({"review": {"denied": "\n\n\n\n" + configured}}))
        self.assertEqual(lr.review_suffixes(str(config)), [configured, lr.DEFAULT_REVIEW_SUFFIX])

    def test_plan_feedback_is_split_into_notes_and_the_plan_has_a_state(self):
        self.assertEqual(lr.plan_notes(PLAN_FEEDBACK), [
            ("plan", "whole document", "overall: add a rollback step", []),
            ("plan", "line 10", "why refresh instead of invalidating the query?", ["> list"])])
        removal = '# File Feedback\n\n## 1. (lines 4-5) Remove: "old step"\n> drop it\n\n---\n'
        self.assertEqual(lr.plan_notes(removal), [("plan", "lines 4-5", 'Remove: "old step"\ndrop it', [])])
        digest = __import__("hashlib").sha256(b"the plan").hexdigest()
        approved = {"role": "plan-review", "created_at": "2", "author": "human:t", "body": "Plannotator plan approved (plan of T-1), s\n%s%s\n\n" % (lr.PLAN, digest)}
        changes = {"role": "plan-review", "created_at": "1", "author": "human:t", "body": "Plannotator plan annotated (plan of T-1), s\n%s%s\n\nx" % (lr.PLAN, digest)}
        self.assertEqual(lr.plan_status([], "the plan"), "not reviewed yet")
        self.assertEqual(lr.plan_status([changes], "the plan"), "changes requested")
        self.assertEqual(lr.plan_status([changes, approved], "the plan"), "approved")
        self.assertIn("changed since it was approved", lr.plan_status([changes, approved], "the plan, edited"))
        agent_note = {"role": "plan-review", "created_at": "3", "author": "agent:x", "body": "Decisions updated for the owner"}
        self.assertEqual(lr.plan_status([changes, approved, agent_note], "the plan"), "approved")
        self.assertEqual(lr.plan_status([agent_note], "the plan"), "not reviewed yet")
        deleted = {"role": "plan-review", "created_at": "3", "author": "human:t", "deleted": True, "body": ""}
        self.assertEqual(lr.plan_status([changes, approved, deleted], "the plan"), "the latest plan review was deleted; review it again")
        self.assertTrue(lr.waits_for_plan_approval({"needs_human": {"reason": "Need: approve plan"}}))
        self.assertTrue(lr.waits_for_plan_approval({"needs_human": {"reason": "Approve or revise the decisions in the AB-10 plan"}}))
        self.assertFalse(lr.waits_for_plan_approval({"needs_human": {"reason": "Need: which OAuth provider?"}}))
        self.assertFalse(lr.waits_for_plan_approval({"needs_human": None}))

    def test_history_says_what_changed_and_why_and_drops_noise(self):
        def ev(i, kind, data, actor="agent:x", **prov):
            return {"id": "ev_%d" % i, "type": kind, "actor": actor, "ts": "2026-11-03T22:%02d:00Z" % i, "data": data,
                    **({"provenance": prov} if prov else {})}
        thread = {"id": "ev_9", "created_at": "2026-11-03T22:09:00Z", "author": "human:t",
                  "body": "%sREADME.md, line 3 at abc\n%sev_8\nwhy?" % (lr.THREAD, lr.REVIEW_OF)}
        events = [
            ev(1, "task_created", {"title": "t"}),
            ev(2, "task_short_id_assigned", {"short_id": "T-1"}),
            ev(3, "status_changed", {"from": "in_progress", "to": "in_review"}, reason="work complete"),
            ev(4, "needs_human_flagged", {"reason": "Need: approve plan"}),
            ev(5, "needs_human_cleared", {"note": "approved in chat"}, on_behalf_of="human:t"),
            ev(6, "field_updated", {"field": "description", "from": "a\nb", "to": "a\nc"}),
            ev(7, "relationship_added", {"type": "blocks", "target_task_id": "task_2"}),
            ev(8, "comment_added", {"body": "just a note"}, actor="human:t"),
            ev(9, "comment_added", {"body": thread["body"]}, actor="human:t"),
            ev(10, "reaction_added", {"comment_id": "ev_9", "emoji": lr.RESOLVED}, actor="human:t"),
            ev(11, "comment_added", {"role": "review", "body": "Plannotator approved (patch a..b), s\n%sa..b\n" % lr.REVIEWED}, actor="human:t"),
            ev(12, "acceptance_criterion_added", {"criterion_id": "AC-1", "outcome": "it works"})]
        commits = [{"hash": "c" * 40, "when": "2026-11-03T14:30:00-08:00", "author": "Pat", "subject": "fix: x"}]
        entries = lr.history(events, [thread], commits, {"task_2": "T-2"})
        texts = [x["text"] for x in entries]
        self.assertEqual(texts, ["committed cccccccccccc fix: x", "added AC-1: it works", "approved the code review of patch a..b",
                                 "resolved the thread on README.md, line 3 at abc", "opened a thread on README.md, line 3 at abc",
                                 "commented: just a note",
                                 "marked this as blocking (it must finish first) T-2", "edited the description", "cleared the owner question: approved in chat",
                                 "asked the owner: Need: approve plan", "moved it from in progress to in review", "created the task"])
        deleted = lr.history([ev(13, "comment_deleted", {"comment_id": "ev_9"}, actor="human:t"),
                              ev(14, "task_created", {"title": "t", "priority": "high", "type": "bug", "status": "backlog"})],
                             [thread], [], {})
        self.assertEqual([x["text"] for x in deleted], ["created the task as a high bug in backlog",
                                                        "deleted a comment by human:t: Thread: README.md, line 3 at abc From review ev_8 why?"])
        by_text = {x["text"]: x for x in entries}
        self.assertEqual(by_text["moved it from in progress to in review"]["why"], "work complete")
        self.assertEqual(by_text["cleared the owner question: approved in chat"]["behalf"], "human:t")
        self.assertEqual(by_text["edited the description"]["details"], "-b\n+c")
        self.assertEqual(by_text["marked this as blocking (it must finish first) T-2"]["link"], ("task", "T-2"))
        self.assertEqual(by_text["resolved the thread on README.md, line 3 at abc"]["link"], ("thread", "ev_9"))
        self.assertEqual(by_text["committed cccccccccccc fix: x"]["link"], ("commit", "c" * 40))
        self.assertEqual(by_text["commented: just a note"]["link"], ("comment", ("human:t", "2026-11-03T22:08:00Z")))
        self.assertEqual(by_text["commented: just a note"]["cat"], "comment")
        self.assertEqual(by_text["added AC-1: it works"]["link"], ("criterion", "AC-1"))
        self.assertEqual(by_text["moved it from in progress to in review"]["cat"], "change")

    def test_bursts_fold_but_decisions_stay_and_other_tasks_cross_reference(self):
        def item(minute, kind, actor="agent:x", behalf=None):
            ts = "2026-11-03T22:%02d:00Z" % minute
            return {"ts": lr.when(ts), "raw_ts": ts, "actor": actor, "kind": kind, "cat": "change", "text": kind,
                    "why": None, "behalf": behalf, "link": None, "details": None}
        newest_first = [item(30, "acceptance_criterion_edited"), item(29, "acceptance_criterion_edited"),
                        item(28, "status_changed"), item(27, "acceptance_criterion_added"), item(26, "acceptance_criterion_added"),
                        item(25, "acceptance_criterion_added"), item(24, "field_updated"), item(1, "field_updated"),
                        item(0, "relationship_added", behalf="human:t")]
        folded = lr.fold_bursts(newest_first)
        self.assertEqual([x["kind"] for x in folded], ["acceptance_criterion_edited", "acceptance_criterion_edited", "status_changed",
                                                       "group", "field_updated", "relationship_added"])
        self.assertEqual(folded[3]["text"], "made 4 changes: added 3 criteria, changed 1 field")
        self.assertEqual(len(folded[3]["group"]), 4)
        me = {"id": "a", "short_id": "T-4"}
        other = {"id": "b", "short_id": "T-12"}
        logs = {"b": [{"id": "e1", "type": "relationship_added", "actor": "agent:x", "ts": "2026-11-03T22:00:00Z",
                       "data": {"type": "depends_on", "target_task_id": "a"}},
                      {"id": "e2", "type": "comment_added", "actor": "human:t", "ts": "2026-11-03T22:01:00Z",
                       "data": {"body": "wait for T-4 first, not T-40"}},
                      {"id": "e3", "type": "comment_added", "actor": "human:t", "ts": "2026-11-03T22:02:00Z",
                       "data": {"body": "about T-40 only"}}]}
        refs = lr.cross_references(me, [me, other], lambda task_id: logs.get(task_id, []))
        self.assertEqual([(x["text"], x["link"], x["cat"]) for x in refs], [
            ("T-12 now waits on this task", ("task", "T-12"), "change"),
            ("mentioned this task in a comment on T-12: wait for T-4 first, not T-40", ("task", "T-12"), "comment")])
        now = lr.when("2026-11-03T22:00:00Z")
        self.assertEqual([lr.ago(lr.when(t), now) for t in ("2026-11-03T21:59:30Z", "2026-11-03T21:15:00Z", "2026-11-03T19:00:00Z",
                                                            "2026-11-02T20:00:00Z")], ["just now", "45m ago", "3h ago", "yesterday"])

    def test_dependencies_read_both_ends_and_warn_when_started_work_still_waits(self):
        a = {"id": "a", "short_id": "T-1", "status": "in_progress", "title": "work",
             "relationships_out": [{"type": "subtask_of", "target_task_id": "p"}, {"type": "depends_on", "target_task_id": "d"}]}
        p = {"id": "p", "short_id": "T-2", "status": "backlog", "title": "parent"}
        d = {"id": "d", "short_id": "T-3", "status": "in_review", "title": "first"}
        b = {"id": "b", "short_id": "T-4", "status": "todo", "title": "blocker", "relationships_out": [{"type": "blocks", "target_task_id": "a"}]}
        c = {"id": "c", "short_id": "T-5", "status": "todo", "title": "child", "relationships_out": [{"type": "subtask_of", "target_task_id": "a"}]}
        w = {"id": "w", "short_id": "T-6", "status": "todo", "title": "waiter", "relationships_out": [{"type": "depends_on", "target_task_id": "a"}]}
        links = lr.dependencies(a, [a, p, d, b, c, w])
        self.assertEqual(sorted((k, o["short_id"]) for k, o, _ in links),
                         [("child", "T-5"), ("holds", "T-6"), ("parent", "T-2"), ("waits", "T-3"), ("waits", "T-4")])
        html = "".join(lr.render_dependencies(a, links))
        self.assertIn("This task is in progress but still waits on T-3 (in review), T-4 (todo).", html)
        self.assertLess(html.index("Waits on"), html.index("Holds up"))
        self.assertIn("<a href='/t/T-2' target='_top'>T-2</a> parent", html)
        self.assertEqual(lr.render_dependencies(a, []), [])

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

    def test_a_note_continues_only_the_one_thread_it_can_belong_to(self):
        def t(where, quote):
            return {"path": "f", "where": where, "quote": quote}
        one, five = t("line 1 (new)", ["> same"]), t("line 5 (new)", ["> same"])
        self.assertIs(lr.thread_for([one, five], "f", "line 1 (new)", ["> same"]), one)
        self.assertIs(lr.thread_for([one, five], "f", "line 5 (new)", ["> same"]), five)
        self.assertIsNone(lr.thread_for([one, five], "f", "line 9 (new)", ["> same"]))
        self.assertIs(lr.thread_for([one], "f", "line 9 (new)", ["> same"]), one)
        self.assertIsNone(lr.thread_for([one], "f", "line 1 (new)", ["> other"]))
        bare = t("line 1 (new)", [])
        self.assertIs(lr.thread_for([bare], "f", "line 1 (new)", ["> same"]), bare)
        self.assertIs(lr.thread_for([bare, five], "f", "line 1 (new)", []), bare)
        self.assertIsNone(lr.thread_for([bare, t("line 1 (new)", ["> x"])], "f", "line 1 (new)", []))
        self.assertIsNone(lr.thread_for([one], "g", "line 1 (new)", ["> same"]))

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


@unittest.skipUnless(HAVE_MODULE, "lattice not importable; use the Python that has lattice installed")
class NativeGitTests(RepoFixture):
    signed_commit = PureTests.signed_commit

    def setUp(self):
        super().setUp()
        from lattice.dashboard import server, git_reader
        self.dashboard, self.reader = server, git_reader
        original = git_reader._run_git
        self.addCleanup(setattr, git_reader, "_run_git", original)
        self.addCleanup(git_reader.invalidate_cache)

    def test_native_dashboard_reads_share_the_controlled_runner(self):
        lr.protect_dashboard_git(self.dashboard, self.reader)
        signed = self.signed_commit()
        git(self.repo, "branch", "signed", signed)
        marker = self.tools / "native-signature-ran"
        probe = self.tools / "native-signature"
        probe.write_text("#!/bin/sh\ntouch '%s'\nexit 1\n" % marker)
        probe.chmod(0o755)
        git(self.repo, "config", "log.showSignature", "true")
        git(self.repo, "config", "gpg.program", str(probe))
        with mock.patch.object(lr, "git_result", wraps=lr.git_result) as runner:
            summary, etag = self.reader.get_git_summary(self.repo / ".lattice")
            commits = self.reader.get_recent_commits(self.repo, "signed")
        self.assertTrue(summary["available"] and etag)
        self.assertEqual(commits[0]["hash"], signed)
        self.assertEqual({c.args[1][0] for c in runner.call_args_list},
                         {"rev-parse", "for-each-ref", "rev-list", "remote", "log"})
        self.assertFalse(marker.exists())

    def test_unknown_installed_git_paths_refuse_startup(self):
        changed = self.tools / "changed.py"
        changed.write_text("# an unreviewed dashboard change\n")
        for dashboard, reader in ((SimpleNamespace(__file__=str(changed)), self.reader),
                                  (self.dashboard, SimpleNamespace(__file__=str(changed)))):
            with self.assertRaisesRegex(RuntimeError, "unsupported Lattice dashboard"):
                lr.protect_dashboard_git(dashboard, reader)

    def test_documented_dashboard_patch_remains_supported(self):
        server = self.tools / "server.py"
        source = Path(self.dashboard.__file__).read_bytes()
        before = b'                info["type"] = meta.get("type")\n'
        added = b'                info["url"] = (meta.get("custom_fields") or {}).get("url")\n'
        if added in source:
            source = source.replace(added, b"")
        self.assertEqual(source.count(before), 1)
        for contents in (source, source.replace(before, before + added)):
            server.write_bytes(contents)
            lr.protect_dashboard_git(SimpleNamespace(__file__=str(server)), self.reader)

    def test_native_missing_objects_are_explicit_without_starting_transport(self):
        lr.protect_dashboard_git(self.dashboard, self.reader)
        marker = self.tools / "native-transport-ran"
        probe = self.tools / "native-transport"
        probe.write_text("#!/bin/sh\ntouch '%s'\nexit 1\n" % marker)
        probe.chmod(0o755)
        git(self.repo, "config", "remote.origin.promisor", "true")
        git(self.repo, "config", "remote.origin.url", "ext::" + str(probe))
        git(self.repo, "config", "protocol.ext.allow", "always")
        (self.repo / ".git" / "objects" / self.b[:2] / self.b[2:]).unlink()
        with self.assertRaises(RuntimeError):
            self.reader.get_recent_commits(self.repo, "main")
        self.assertFalse(marker.exists())

    def test_native_git_errors_return_a_json_failure(self):
        ctx = self.context()
        handler = object.__new__(lr.make_handler(ctx))
        handler.path, handler.headers = "/api/git", {"Host": "localhost"}
        handler.send_json = mock.Mock()
        with mock.patch.object(self.reader, "get_git_summary", side_effect=RuntimeError("missing object")):
            handler.do_GET()
        status, payload = handler.send_json.call_args.args
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"], {"code": "GIT_READ_ERROR", "message": "missing object"})


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
        big = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=10)
        big.putrequest("POST", "/api/tasks/task_AB9/status")
        for name, value in headers.items():
            big.putheader(name, value)
        big.putheader("Content-Length", str(lr.MAX_BODY + 2))
        big.endheaders()
        self.assertEqual(big.getresponse().status, 413)
        big.close()
        self.assertEqual(StubDashboard.received, [])
        self.assertEqual(call(self.base + "/api/tasks/task_AB9/status", body, headers)[0], 200)
        self.assertEqual(StubDashboard.received[-1], ("/api/tasks/task_AB9/status", {"status": "todo", "actor": "human:t"}))

    def test_dashboard_writes_without_an_actor_carry_the_owner(self):
        call(self.base + "/api/tasks/task_AB2/comment", json.dumps({"body": "native comment"}).encode(), origin(self.base))
        self.assertEqual(StubDashboard.received[-1][1], {"body": "native comment", "actor": "human:t"})
        call(self.base + "/api/tasks/task_AB2/comment", json.dumps({"body": "x", "actor": "dashboard:web"}).encode(), origin(self.base))
        self.assertEqual(StubDashboard.received[-1][1]["actor"], "human:t")
        call(self.base + "/api/tasks/task_AB2/comment", json.dumps({"body": "x", "actor": "agent:bot"}).encode(), origin(self.base))
        self.assertEqual(StubDashboard.received[-1][1]["actor"], "agent:bot")

    def test_done_through_the_dashboard_needs_an_approved_current_review(self):
        done = json.dumps({"status": "done", "actor": "dashboard:web"}).encode()
        headers = origin(self.base)
        status, body, _ = call(self.base + "/api/tasks/task_AB2/status", done, headers)
        self.assertEqual((status, json.loads(body)["error"]["code"]), (409, "REVIEW_REQUIRED"))
        self.assertIn("no Plannotator review", json.loads(body)["error"]["message"])
        self.assertEqual(call(self.base + "/api/tasks/task_AB2/status?view=board", b"  \n" + done, headers)[0], 409)
        self.assertEqual(call(self.base + "/api/tasks/task_AB2/status/", done, headers)[0], 409)
        self.assertEqual(StubDashboard.received, [])
        self.reviews["AB-2"] = [{"role": "review", "created_at": "2026-01-01T00:00:00Z", "author": "human:t", "body": self.approved(self.a, self.b)}]
        self.assertIn("commits arrived after your review", json.loads(call(self.base + "/api/tasks/task_AB2/status", done, headers)[1])["error"]["message"])
        self.reviews["AB-2"] = [{"role": "review", "created_at": "2026-01-01T00:00:00Z", "author": "human:t", "body": self.approved(self.b, self.c)}]
        self.assertEqual(call(self.base + "/api/tasks/task_AB2/status", done, headers)[0], 200)
        self.assertEqual(StubDashboard.received[-1][1]["status"], "done")
        self.assertEqual(call(self.base + "/api/tasks/task_AB9/status", done, headers)[0], 200)
        path = self.repo / ".lattice" / "tasks" / "task_AB9.json"
        path.write_text(json.dumps(dict(json.loads(path.read_text()), acceptance_criteria=[{"id": "AC-1", "retired": False}])))
        status, body, _ = call(self.base + "/api/tasks/task_AB9/status", done, headers)
        self.assertEqual(status, 409)
        self.assertIn("no evidence is recorded yet for AC-1", json.loads(body)["error"]["message"])

    def test_merged_history_that_earlier_approvals_cover_offers_mark_done(self):
        c2 = commit(self.repo, "c2", "fix: more c\n\nTask: AB-2")
        self.reviews["AB-2"] = [
            {"role": "review", "created_at": "2026-01-01T00:00:00Z", "author": "human:t", "body": self.approved(self.b, self.c)},
            {"role": "review", "created_at": "2026-01-02T00:00:00Z", "author": "human:t", "body": self.approved(self.f, c2)}]
        self.assertIn("Mark done: approved at " + c2[:12], call(self.base + "/review/t/AB-2")[1])

    def test_review_section_offers_only_what_the_task_allows(self):
        split = call(self.base + "/review/t/AB-1")[1]
        self.assertEqual(split.count(">Review this commit</button>"), 2)
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
        self.assertNotIn("Plannotator", none)
        self.assertIn(">Write the plan in VS Code</button>", none)
        self.assertNotIn("Completion", none)
        (self.repo / "scratch").write_text("x\n")
        for sid in ("AB-2", "AB-9", "AB-10"):
            self.assertNotIn("uncommitted changes in", call(self.base + "/review/t/" + sid)[1])
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
        self.reviews["AB-4"] = [{"role": "review", "created_at": "2026-01-01T00:00:00Z", "author": "human:t", "body": self.approved(self.b, self.e)}]
        page = call(self.base + "/review/t/AB-4")[1]
        self.assertIn("Not ready to complete: the approved commits are not merged into main yet", page)
        self.assertNotIn("Mark done: approved at", page)
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
        self.reviews["AB-2"] = [{"role": "review", "created_at": "2026-01-01T00:00:00Z", "author": "human:t", "body": self.approved(self.a, self.b)}]
        call(self.base + "/review/t/AB-2/complete", form(self.ctx))
        self.assertIn("not completed", call(self.base + "/review/t/AB-2")[1])
        self.assertEqual(self.calls, [])
        self.reviews["AB-2"] = [{"role": "review", "created_at": "2026-01-01T00:00:00Z", "author": "human:t", "body": self.approved(self.b, self.c)}]
        call(self.base + "/review/t/AB-2/complete", form(self.ctx))
        self.assertEqual(self.calls, [("status", "AB-2", "done", "--no-auto-review")])

    def test_plan_and_code_review_are_separate_blocks_and_the_frame_follows_the_page_scheme(self):
        plan = self.repo / ".lattice" / "plans" / "task_AB2.md"
        plan.parent.mkdir(exist_ok=True)
        plan.write_text("# Plan\n")
        thread = lambda cid, anchor: {"id": cid, "created_at": "2026-01-01T00:00:0%s" % cid[-1], "author": "human:t",
                                      "body": "%s%s at abc\n%sev_r\nwhy?" % (lr.THREAD, anchor, lr.REVIEW_OF)}
        self.reviews["AB-2"] = [thread("ev_1", "plan, line 3"), thread("ev_2", "c, whole file")]
        page = call(self.base + "/review/t/AB-2")[1]
        plan_at, code_at = page.index("<h4>Plan</h4>"), page.index("<h4>Code review</h4>")
        self.assertLess(plan_at, page.index("Plannotator: review the plan"))
        self.assertLess(page.index(">Open the plan in VS Code</button>"), code_at)
        self.assertLess(plan_at, page.index("Plan threads"))
        self.assertLess(page.index("plan, line 3"), code_at)
        self.assertLess(code_at, page.index("Code review threads"))
        self.assertLess(code_at, page.index("c, whole file"))
        self.assertIn("colorScheme=s.colorScheme", page)
        call(self.base + "/review/t/AB-2/openplan", form(self.ctx))
        self.assertIn(str(plan), wait_file(self.tools / "code.log"))

    def test_history_is_its_own_frame_with_events_commits_and_jumps_into_the_review(self):
        events = self.repo / ".lattice" / "events"
        events.mkdir(exist_ok=True)
        (events / "task_AB2.jsonl").write_text("\n".join(json.dumps(x) for x in [
            {"id": "ev_1", "type": "status_changed", "actor": "agent:x", "ts": "2026-11-03T22:00:00Z",
             "data": {"from": "in_progress", "to": "in_review"}},
            {"id": "ev_2", "type": "needs_human_cleared", "actor": "agent:x", "ts": "2026-11-03T22:01:00Z",
             "data": {"note": "approved"}, "provenance": {"on_behalf_of": "human:t"}},
            {"id": "ev_3", "type": "comment_added", "actor": "human:t", "ts": "2026-11-03T22:02:00Z",
             "data": {"body": "%sc, whole file at abc\n%sev_r\nwhy?" % (lr.THREAD, lr.REVIEW_OF)}}]) + "\n")
        self.reviews["AB-2"] = [{"id": "ev_3", "created_at": "2026-11-03T22:02:00Z", "author": "human:t",
                                 "body": "%sc, whole file at abc\n%sev_r\nwhy?" % (lr.THREAD, lr.REVIEW_OF)}]
        review = call(self.base + "/review/t/AB-2")[1]
        self.assertNotIn("<h4>History</h4>", review)
        self.assertIn("id='thread-ev_3'", review)
        self.assertIn("<tr id='commit-%s'>" % self.c[:12], review)
        status, history, _ = call(self.base + "/review/t/AB-2/history")
        self.assertEqual(status, 200)
        self.assertIn("moved it from in progress to in review", history)
        self.assertIn("<span class='warn'>on behalf of human:t</span>", history)
        self.assertIn("committed %s fix: c" % self.c[:12], history)
        self.assertIn("lrJump(&quot;commit-%s&quot;)" % self.c[:12], history)
        self.assertIn("lrJump(&quot;thread-ev_3&quot;)", history)
        self.assertIn("data-f='comment'", history)
        self.assertIn("class='event comment'", history)
        self.assertIn("class='event change'", history)
        self.assertIn("iframe.review-frame:not(.history-frame)", history)
        self.assertIn("history-frame", lr.PANEL)
        self.assertIn("Nothing has happened", call(self.base + "/review/t/AB-9/history")[1])

    def test_panel_script_declares_each_top_level_function_once(self):
        import re
        names = re.findall(r"(?m)^function (\w+)\(", lr.PANEL)
        self.assertEqual(sorted({n for n in names if names.count(n) > 1}), [])

    def test_in_progress_work_without_its_own_branch_is_flagged(self):
        record = json.loads((self.repo / ".lattice" / "tasks" / "task_AB1.json").read_text())
        record["status"] = "in_progress"
        (self.repo / ".lattice" / "tasks" / "task_AB1.json").write_text(json.dumps(record))
        self.assertIn("has no branch of its own", call(self.base + "/review/t/AB-1")[1])
        self.assertNotIn("has no branch of its own", call(self.base + "/review/t/AB-4")[1])

    def edit_task(self, name, **fields):
        path = self.repo / ".lattice" / "tasks" / (name + ".json")
        path.write_text(json.dumps(dict(json.loads(path.read_text()), **fields)))

    def test_an_open_request_is_shown_and_named_before_mark_done(self):
        self.edit_task("task_AB2", needs_human={"flagged_by": "agent:x", "reason": "Need: run the checks on your machine"})
        self.reviews["AB-2"] = [{"role": "review", "created_at": "2026-01-01T00:00:00Z", "author": "human:t",
                                 "body": self.approved(self.b, self.c)}]
        page = call(self.base + "/review/t/AB-2")[1]
        self.assertIn("Open request from agent:x:</b> Need: run the checks on your machine", page)
        self.assertIn("lattice needs-human AB-2 --clear", page)
        self.assertIn("data-confirm='Mark AB-2 done? Done is final. The open request is: Need: run the checks on your machine'", page)
        self.assertLess(page.index("Open request"), page.index("Mark done"))
        self.assertNotIn("Open request", call(self.base + "/review/t/AB-1")[1])
        self.assertIn("data-confirm='Mark AB-10 done? Done is final.'", self.approved_page("AB-10", self.d, self.f))

    def approved_page(self, sid, base, head):
        self.reviews[sid] = [{"role": "review", "created_at": "2026-01-01T00:00:00Z", "author": "human:t",
                              "body": self.approved(base, head)}]
        return call(self.base + "/review/t/" + sid)[1]

    def test_the_result_of_a_thread_action_shows_in_that_thread(self):
        self.reviews["AB-2"] = [{"id": "ev_1", "created_at": "2026-01-01T00:00:01Z", "author": "human:t",
                                 "body": lr.THREAD + "c, whole file at abc\n" + lr.REVIEW_OF + "ev_r\nwhy?"}]
        call(self.base + "/review/t/AB-2/reply", form(self.ctx, parent="ev_1", body=" "))
        page = call(self.base + "/review/t/AB-2")[1]
        self.assertIn("the reply is empty", page)
        self.assertGreater(page.index("id='notice'"), page.index("id='thread-ev_1'"))
        call(self.base + "/review/t/AB-2/complete", form(self.ctx))
        page = call(self.base + "/review/t/AB-2")[1]
        self.assertIn("not completed", page)
        self.assertLess(page.index("id='notice'"), page.index("id='thread-ev_1'"))
        self.assertNotIn("id='notice'", call(self.base + "/review/t/AB-2")[1])

    def test_a_typed_reply_survives_the_refresh_and_a_form_is_sent_once(self):
        running = lr.page("t", "<p>x</p>", refresh=True).decode()
        self.assertNotIn("http-equiv", running)
        self.assertIn('if(a&&a.tagName==="TEXTAREA")return', running)
        self.assertIn("t[i].value.trim()", running)
        still = lr.page("t", "<p>x</p>").decode()
        self.assertNotIn("setInterval", still)
        self.assertIn("f.dataset.sent", still)
        self.assertIn("data-confirm='Close it?'", lr.button(self.ctx, "/x", "Close session", confirm="Close it?"))

    def test_branches_the_range_does_not_read_are_named(self):
        for name in ("feature/AB-9-x-a", "feature/AB-9-x-b", "feature/AB-90-other"):
            git(self.repo, "branch", name)
        page = call(self.base + "/review/t/AB-9")[1]
        self.assertIn("Not linked, so not read here: <code>feature/AB-9-x-a</code>, <code>feature/AB-9-x-b</code>", page)
        self.assertIn("lattice branch-link AB-9", page)
        self.assertNotIn("AB-90", page)
        self.edit_task("task_AB4", branch_links=[{"branch": "gone"}, {"branch": "task/ab-4"}, {"branch": "main"}])
        page = call(self.base + "/review/t/AB-4")[1]
        self.assertIn("Linked branch <code>gone</code> is not in this repository", page)
        self.assertIn("Also linked and not read: <code>main</code>", page)
        self.assertIn("branch <code>task/ab-4</code>", page)

    def test_the_section_says_what_is_left_after_done_and_names_a_wrong_base(self):
        self.edit_task("task_AB2", status="done")
        self.assertNotIn("class='next'", call(self.base + "/review/t/AB-2")[1])
        (self.repo / ".worktrees" / "AB-2").mkdir(parents=True)
        (self.repo / ".worktrees" / "AB-20").mkdir()
        page = call(self.base + "/review/t/AB-2")[1]
        self.assertIn("Done. Still on disk: .worktrees/AB-2.", page)
        self.ctx.main = "develop"
        page = call(self.base + "/review/t/AB-1")[1]
        self.assertIn("The integration branch <code>develop</code> is not in this repository", page)

    def test_task_writes_carry_the_owner_and_settings_writes_pass_through(self):
        status = call(self.base + "/api/config/dashboard", json.dumps({"theme": "linear"}).encode(), origin(self.base))[0]
        self.assertEqual(status, 200)
        self.assertEqual(StubDashboard.received[-1], ("/api/config/dashboard", {"theme": "linear"}))
        call(self.base + "/api/tasks/task_AB2/comment", json.dumps({"body": "x"}).encode(), origin(self.base))
        self.assertEqual(StubDashboard.received[-1][1].get("actor"), "human:t")
        with self.assertRaises(SystemExit):
            lr.main(["--actor", "agent:x", "--board", str(self.repo)])

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
        self.ctx.board_write = lambda key, *args: self.calls.append(args) or args[0] != "comment"
        self.reviews["AB-2"] = [{"id": "ev_1", "created_at": "2026-01-01T00:00:01Z", "author": "human:t",
                                 "body": lr.THREAD + "c, whole file at abc\n" + lr.REVIEW_OF + "ev_r\nwhy?"}]
        del self.calls[:]
        call(self.base + "/review/t/AB-2/reply", form(self.ctx, parent="ev_1", body="not lost", resolve="1"))
        self.assertEqual([c[0] for c in self.calls], ["comment"])
        self.assertIn(">not lost</textarea>", call(self.base + "/review/t/AB-2")[1])
        self.ctx.board_write = lambda key, *args: self.calls.append(args) or True
        call(self.base + "/review/t/AB-2/reply", form(self.ctx, parent="ev_1", body="not lost"))
        self.assertIn("></textarea>", call(self.base + "/review/t/AB-2")[1])


class ClosingTests(RepoFixture):
    def summary(self, sid, comments=(), threads=(), plan_state=None):
        rng = lr.resolve_range(self.repo, lr.find_task(self.repo, sid), "main")
        return lr.closing_summary(self.repo, "main", rng, list(comments), list(threads), plan_state)

    def test_says_where_the_landed_commits_are(self):
        self.assertIn("1 commit, merged into main, which has no upstream.", self.summary("AB-2"))
        git(self.repo, "update-ref", "refs/remotes/origin/main", self.f)
        git(self.repo, "config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*")
        git(self.repo, "config", "branch.main.remote", "origin")
        git(self.repo, "config", "branch.main.merge", "refs/heads/main")
        self.assertIn("1 commit, merged into main and pushed. Nothing left to merge or push.", self.summary("AB-2"))
        self.assertNotIn("Mark done, then", self.summary("AB-2"))

    def test_counts_review_rounds_and_quotes_the_latest_agent_note(self):
        comments = [
            {"role": "plan-review", "author": "human:t", "created_at": "2026-01-01T00:00:00Z", "body": "Plannotator plan annotated (plan of AB-2), s\n"},
            {"role": "plan-review", "author": "human:t", "created_at": "2026-01-02T00:00:00Z", "body": "Plannotator plan approved (plan of AB-2), s\n"},
            {"role": "plan-review", "author": "agent:x", "created_at": "2026-01-02T00:00:00Z", "body": "Plannotator plan approved (plan of AB-2), s\n"},
            {"role": "review", "author": "human:t", "created_at": "2026-01-03T00:00:00Z", "body": self.approved(self.b, self.c)},
            {"author": "agent:x", "created_at": "2026-01-04T00:00:00Z", "body": "Installed and checked at <main>. Details follow."},
            {"author": "agent:x", "created_at": "2026-01-02T00:00:00Z", "body": "Older note."},
            {"author": "human:t", "created_at": "2026-01-05T00:00:00Z", "body": "Owner aside."},
        ]
        text = self.summary("AB-2", comments, [{"state": "resolved"}, {"state": "resolved"}], "approved")
        self.assertIn("Plan approved after 2 reviews. Code approved after 1 review, 2 threads resolved.", text)
        self.assertIn("Latest note, agent:x 2026-01-04: Installed and checked at &lt;main&gt;.", text)
        self.assertNotIn("Details follow", text)
        self.assertIn("Code approved after 1 review, no threads.", self.summary("AB-2", comments[3:4]))


@unittest.skipUnless(HAVE_CLI, "lattice not on PATH")
class CliTests(RepoFixture):
    def test_board_writes_go_to_the_served_board_whatever_lattice_root_says(self):
        board = init_board(self.repo)
        decoy = Path(self.tmp.name) / "decoy"
        decoy.mkdir()
        init_board(decoy, "DC")
        sid = lattice(board, "create", "a task", "--actor", "agent:test", "--quiet")
        ctx = self.context(board=board, repo=self.repo)
        os.environ["LATTICE_ROOT"] = str(decoy / "board")
        self.addCleanup(os.environ.pop, "LATTICE_ROOT", None)
        code, out = ctx.lattice_cmd("comment", sid, "a note")
        self.assertEqual(code, 0, out)
        self.assertEqual([c["body"] for c in ctx.comments(sid)], ["a note"])

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
                                      "### File Comment\nname it better\n\n\n\n" + lr.DEFAULT_REVIEW_SUFFIX)
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
    def test_an_approval_whose_notes_were_not_all_recorded_cannot_complete(self):
        board = init_board(self.repo)
        sid = lattice(board, "create", "a task", "--actor", "agent:test", "--quiet")
        commit(self.repo, "m", "feat: m\n\nTask: " + sid, content="one\ntwo")
        ctx = self.context(board=board, repo=self.repo)
        rng = lr.resolve_range(self.repo, lr.find_task(board, sid), "main")
        real = ctx.lattice_cmd
        ctx.lattice_cmd = lambda *args: (1, "disk full") if any(str(a).endswith(".note2.md") for a in args) else real(*args)
        ctx.plannotator = fake_plannotator(self.tools, decision="approved", message="## m\n\n### Line 1 (new)\nfine, but rename\n\n### Line 2 (new)\nand this")
        job = ctx.start_plannotator(sid, record_on=sid, base=rng["base"], head=rng["head"])
        wait_for(job)
        self.assertIn("note 2 of the review was not recorded", job.error)
        comments = ctx.comments(sid)
        self.assertEqual(lr.review_decision(lr.latest_review(comments)["body"]), "approved")
        (thread,) = lr.review_threads(comments)
        lattice(board, "react", sid, thread["root"]["id"], lr.RESOLVED, "--actor", "human:t")
        restarted = self.context(board=board, repo=self.repo)
        self.assertIn("only 1 of the 2 notes", lr.completion_block(self.repo, lr.find_task(board, sid), "main", restarted.comments(sid)))
        StubDashboard.static_dir = self.repo / "static"
        server = serve(lr.make_handler(restarted, base=StubDashboard, static_dir=StubDashboard.static_dir))
        base = "http://127.0.0.1:%d" % server.server_address[1]
        try:
            page = call(base + "/review/t/" + sid)[1]
            self.assertIn("Only 1 of its 2 notes were recorded", page)
            self.assertNotIn("Mark done", page)
            call(base + "/review/t/%s/complete" % sid, form(restarted))
            self.assertIn("not completed: only 1 of the 2 notes", call(base + "/review/t/" + sid)[1])
            self.assertNotEqual(lr.find_task(board, sid)["status"], "done")
        finally:
            server.shutdown()
            server.server_close()

    def test_a_note_on_repeated_lines_continues_the_thread_at_its_own_place(self):
        board = init_board(self.repo)
        sid = lattice(board, "create", "a task", "--actor", "agent:test", "--quiet")
        commit(self.repo, "r", "feat: r\n\nTask: " + sid, content="same\nb\nc\nd\nsame")
        ctx = self.context(board=board, repo=self.repo)
        rng = lr.resolve_range(self.repo, lr.find_task(board, sid), "main")

        def review(message):
            ctx.plannotator = fake_plannotator(self.tools, message=message)
            job = ctx.start_plannotator(sid, record_on=sid, base=rng["base"], head=rng["head"])
            wait_for(job)
            self.assertTrue(job.done and not job.error, job.error)
            return lr.review_threads(ctx.comments(sid))
        threads = review("## r\n\n### Line 1 (new)\ntop\n\n### Line 5 (new)\nbottom")
        self.assertEqual([(t["where"], t["quote"]) for t in threads], [("line 1 (new)", ["> same"]), ("line 5 (new)", ["> same"])])
        threads = review("## r\n\n### Line 1 (new)\ntop again")
        self.assertEqual(len(threads), 2)
        self.assertTrue(threads[0]["messages"][-1]["body"].strip().endswith("top again"))
        self.assertEqual(len(threads[1]["messages"]), 1)

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

    def test_plan_review_records_threads_and_approval_clears_the_plan_flag(self):
        board = init_board(self.repo)
        sid = lattice(board, "create", "a task", "--actor", "agent:test", "--quiet")
        record = lr.find_task(board, sid)
        plan = board / ".lattice" / "plans" / (record["id"] + ".md")
        plan.write_text("# Plan\n\n1. Add a failing test.\n2. Fix the list refresh.\n")
        lattice(board, "needs-human", sid, "Need: approve plan", "--actor", "agent:test")
        ctx = self.context(board=board, repo=self.repo)

        def review(decision, feedback):
            ctx.plannotator = fake_plannotator(self.tools, decision=decision, message=feedback, key="feedback")
            job = ctx.start_plan_review(lr.find_task(board, sid))
            wait_for(job)
            self.assertTrue(job.done and not job.error, job.error)
            return lr.review_threads(ctx.comments(sid))
        threads = review("annotated", PLAN_FEEDBACK)
        digest = __import__("hashlib").sha256(plan.read_bytes()).hexdigest()
        self.assertEqual([(t["anchor"], t["note"], t["state"]) for t in threads], [
            ("plan, whole document at plan " + digest[:12], "overall: add a rollback step", "waiting on the agent"),
            ("plan, line 10 at plan " + digest[:12], "> list\nwhy refresh instead of invalidating the query?", "waiting on the agent")])
        self.assertEqual(lr.plan_status(ctx.comments(sid), plan.read_text()), "changes requested")
        self.assertTrue(lr.waits_for_plan_approval(lr.find_task(board, sid)))
        lattice(board, "comment", sid, "--reply-to", threads[1]["root"]["id"], "Status: answered\nAnswer: invalidation it is", "--actor", "agent:test")
        plan.write_text("# Plan\n\nContext line.\n\n1. Add a failing test.\n2. Fix the list refresh.\n")
        threads = review("annotated", '# File Feedback\n\n## 1. (line 12) Feedback on: "list"\n> still unsure\n\n---\n')
        self.assertEqual(len(threads), 2)
        self.assertTrue(threads[1]["messages"][-1]["body"].strip().endswith("still unsure"))
        self.assertEqual(threads[1]["state"], "waiting on the agent")
        review("approved", "")
        self.assertIsNone(lr.find_task(board, sid).get("needs_human"))
        self.assertEqual(lr.plan_status(ctx.comments(sid), plan.read_text()), "approved")
        lattice(board, "needs-human", sid, "Need: approve plan", "--actor", "agent:test")
        ctx.plannotator = fake_plannotator(self.tools, decision="approved", message="", key="feedback", delay=2)
        job = ctx.start_plan_review(lr.find_task(board, sid))
        wait_file(job.err_path)
        plan.write_text(plan.read_text() + "3. Slipped in during the review.\n")
        wait_for(job)
        self.assertIn("changed during the session", job.error)
        self.assertTrue(lr.waits_for_plan_approval(lr.find_task(board, sid)))
        self.assertIn("changed since it was approved", lr.plan_status(ctx.comments(sid), plan.read_text()))
        job = ctx.start_plan_review(lr.find_task(board, sid))
        wait_file(job.err_path)
        lattice(board, "needs-human", sid, "--clear", "--note", "withdrawn", "--actor", "agent:test")
        lattice(board, "needs-human", sid, "Need: approve plan v2", "--actor", "agent:test")
        wait_for(job)
        self.assertIn("flag changed", job.error)
        self.assertEqual(lr.find_task(board, sid)["needs_human"]["reason"], "Need: approve plan v2")
        self.assertEqual(lr.plan_status(ctx.comments(sid), plan.read_text()), "approved")
        review("approved", "")
        self.assertIsNone(lr.find_task(board, sid).get("needs_human"))
        StubDashboard.static_dir = self.repo / "static"
        server = serve(lr.make_handler(ctx, base=StubDashboard, static_dir=StubDashboard.static_dir))
        base = "http://127.0.0.1:%d" % server.server_address[1]
        try:
            page = call(base + "/review/t/" + sid)[1]
            self.assertIn("Plan: <b>approved</b>", page)
            self.assertIn(">Plannotator: review the plan</button>", page)
            plan.write_text(plan.read_text() + "3. A late edit.\n")
            self.assertIn("changed since it was approved", call(base + "/review/t/" + sid)[1])
        finally:
            server.shutdown()
            server.server_close()


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
