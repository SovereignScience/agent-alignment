#!/usr/bin/env python3
"""The Lattice dashboard with a review section on every task.

One local server: the Lattice dashboard (its own handler class, run in
this process) plus, inside each task's detail view, the commits that
belong to the task: a linked branch or the commits whose message carries
a "Task: <ID>" trailer. Buttons open them in Plannotator, or file by
file in VS Code. Plannotator's decision lands on the task as a comment
bound to the reviewed commits, and each of its line notes becomes a
thread of its own, with replies and a resolved state. A task with
work can be marked done, here or with the dashboard's own status control,
only while its latest review approves exactly the commits it has now and
every thread is resolved. Notes and plans opened from the dashboard open
in VS Code.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import os
import re
import secrets
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import ThreadingHTTPServer
from pathlib import Path

REVIEW_PATH = "/review"
WORKTREE = "WORKTREE"
REVIEWED = "Reviewed: "
THREAD = "Thread: "
REVIEW_OF = "From review "
FOLLOW_UP = "Follow-up from review "
LINES = re.compile(r"^lines? (\d+)(?:-(\d+))? \((new|old)\)$")
ANCHOR = re.compile(r"^(.*), (lines? \d+(?:-\d+)? \((?:new|old)\)|whole file) at [0-9a-f]+$")
RESOLVED = "resolved"
REVISION = re.compile(r"^([0-9a-f]{7,40})\.\.([0-9a-f]{7,40})( live| dirty)?$")
DECISION = re.compile(r"^Plannotator (approved|annotated) \(")
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
MAX_BODY = 1_048_576
HOOK = "<script>window.LATTICE_REVIEW_URL=%s</script>" % json.dumps(REVIEW_PATH)
INSTALL_HINT = ("Install Plannotator by downloading its installer, reading it, then running it: "
                "<code>curl -fsSLo plannotator-install.sh https://plannotator.ai/install.sh</code>, "
                "<code>less plannotator-install.sh</code>, <code>bash plannotator-install.sh --minimal</code>. "
                "Then restart this server.")


# --------------------------------------------------------------------------
# git and board reads (pure functions, covered by the tests)
# --------------------------------------------------------------------------

def run_git(repo, *args, check=True, binary=False):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=not binary)
    if check and result.returncode != 0:
        err = result.stderr if not binary else result.stderr.decode(errors="replace")
        raise RuntimeError(err.strip() or "git " + " ".join(args) + " failed")
    return result.stdout


def rev(repo, ref):
    """Immutable commit ID for a ref, or None when it does not resolve."""
    out = run_git(repo, "rev-parse", "--verify", "--quiet", ref + "^{commit}", check=False).strip()
    return out or None


def board_config(board):
    return json.loads((Path(board) / ".lattice" / "config.json").read_text())


def load_tasks(board):
    return [json.loads(p.read_text()) for p in (Path(board) / ".lattice" / "tasks").glob("*.json")]


def find_task(board, short_id):
    for task in load_tasks(board):
        if task.get("short_id") == short_id or task.get("id") == short_id:
            return task
    return None


def log_commits(repo, *args):
    out = run_git(repo, "log", "--reverse", "--format=%H%x1f%s%x1f%cs", *args, check=False)
    commits = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 3:
            commits.append({"hash": parts[0], "subject": parts[1], "date": parts[2]})
    return commits


def task_commits(repo, short_id, refs):
    """Commits with a "Task: <short_id>" trailer on any of the refs, oldest first."""
    pattern = r"^Task:( [A-Z]+-[0-9]+,)* " + re.escape(short_id) + r"(,.*)?$"
    seen = {}
    for ref in dict.fromkeys(refs):
        if not rev(repo, ref):
            continue
        for commit in log_commits(repo, "-E", "--grep=" + pattern, ref):
            seen.setdefault(commit["hash"], commit)
    return sorted(seen.values(), key=lambda c: run_git(repo, "rev-list", "--count", c["hash"]).strip().zfill(9))


def resolve_range(repo, task, main):
    """Where a task's work lives: its linked branch, or its trailer commits.

    base and head are refs for display; base_sha and head_sha are the
    immutable commit IDs a review is bound to."""
    links = [link["branch"] for link in task.get("branch_links", [])]
    for branch in links:
        head_sha = rev(repo, branch)
        if head_sha:
            base = run_git(repo, "merge-base", main, branch).strip()
            return {"mode": "branch", "branch": branch, "base": base, "head": branch, "base_sha": base,
                    "head_sha": head_sha, "commits": log_commits(repo, base + ".." + branch), "contiguous": True}
    commits = task_commits(repo, task["short_id"], ["HEAD", main] + links)
    if not commits:
        return {"mode": "none", "base": None, "head": None, "base_sha": None, "head_sha": None, "commits": [], "contiguous": False}
    oldest, newest = commits[0]["hash"], commits[-1]["hash"]
    between = run_git(repo, "rev-list", "--count", oldest + "^.." + newest, check=False).strip()
    contiguous = between.isdigit() and int(between) == len(commits)
    if not contiguous:
        return {"mode": "commits", "base": None, "head": None, "base_sha": None, "head_sha": None,
                "commits": commits, "contiguous": False}
    return {"mode": "commits", "base": oldest + "^", "head": newest, "base_sha": rev(repo, oldest + "^"),
            "head_sha": newest, "commits": commits, "contiguous": True}


def changed_files(repo, base, head):
    """Name-status rows (NUL-delimited, so any file name survives); renames and
    copies keep the old path for the base side."""
    args = ["diff", "--name-status", "-M", "-z", base] + ([] if head == WORKTREE else [head])
    fields = run_git(repo, *args).split("\0")
    files = []
    i = 0
    while i < len(fields) and fields[i]:
        status = fields[i][0]
        if status in "RC":
            files.append({"status": status, "path": fields[i + 2], "old_path": fields[i + 1]})
            i += 3
        else:
            files.append({"status": status, "path": fields[i + 1], "old_path": fields[i + 1]})
            i += 2
    return files


def current_branch(repo):
    return run_git(repo, "rev-parse", "--abbrev-ref", "HEAD", check=False).strip()


def worktree_dirty(repo):
    return bool(run_git(repo, "status", "--porcelain", check=False).strip())


def plannotator_args(plannotator, base=None, head=None, live=False):
    """Command for one Plannotator session: the live checked-out tree from base,
    or a static patch of base..head fed on stdin. Plannotator opens no browser
    itself; the session URL it prints is opened by the page that asked."""
    if live:
        args = [plannotator, "--browser", "none", "review", "--git", "--no-git-remote-check", "--json"]
        return args + (["--base", base] if base else []), None
    return [plannotator, "--browser", "none", "review", "--patch-file", "-", "--json"], ["diff", base] + ([] if head == WORKTREE else [head])


def parse_review(stdout):
    """Plannotator's --json record: decision approved, annotated or dismissed."""
    for line in reversed(stdout.strip().splitlines()):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and "decision" in record:
            decision, message = record["decision"], record.get("message")
            if not isinstance(message, str):
                message = "" if message is None else json.dumps(message)
            return (decision if isinstance(decision, str) else None), message.strip()
    return None, stdout.strip()


def reviewed_revision(text):
    """(base_sha, head_sha, qualifier) from a review's Reviewed line.

    qualifier is None for a committed range and "live" for a working-tree
    review. A missing or malformed line gives (None, None, None)."""
    for line in text.splitlines():
        if line.startswith(REVIEWED):
            match = REVISION.match(line[len(REVIEWED):].strip())
            return (match.group(1), match.group(2), (match.group(3) or "").strip() or None) if match else (None, None, None)
    return None, None, None


def review_decision(text):
    """approved or annotated, from the first line of a recorded review."""
    match = DECISION.match(text.splitlines()[0] if text else "")
    return match.group(1) if match else None


def review_notes(message):
    """The notes in a Plannotator review message, as (path, where, text).

    The message has a "## <file>" heading per file and a "### Line N (new)",
    "### Lines N-M (old)" or "### File Comment" heading per note. Plannotator
    appends its own instructions after three or more blank lines; they belong
    to no note. where is "line 239 (new)", "lines 3-5 (old)", "whole file", or
    empty for text directly under a "##" heading."""
    notes, path, where, anchor, text, blanks = [], None, "", None, [], 0

    def flush():
        note = "\n".join(text).strip()
        if anchor and note:
            notes.append((path, where, note))

    for line in message.splitlines():
        if not line.strip():
            blanks += 1
            if anchor and blanks >= 3:
                break
            text.append(line)
            continue
        blanks = 0
        if line.startswith("## "):
            flush()
            path = anchor = line[3:].strip()
            where, text = "", []
        elif line.startswith("### ") and path:
            flush()
            heading = line[4:].strip()
            where = "whole file" if heading.lower() == "file comment" else heading[:1].lower() + heading[1:]
            anchor, text = path + ", " + where, []
        elif anchor:
            text.append(line)
    flush()
    return notes


def note_anchor(path, where):
    return path + ", " + where if where else path


def quoted_lines(text, where):
    """The reviewed lines of a file's text as "> " quotes, at most five."""
    match = LINES.match(where)
    if not match or text is None:
        return []
    start, end = int(match.group(1)), int(match.group(2) or match.group(1))
    return ["> " + line for line in text.splitlines()[start - 1:min(end, start + 4)]]


def thread_key(path, where, quote):
    """What a later note must share to continue a thread: the file and the
    quoted lines, which survive the lines moving; without a quote, the place."""
    return (path, "\n".join(quote)) if quote else (path, where)


def thread_messages(root):
    """A thread's messages, oldest first: the note and every reply under it."""
    out = []

    def walk(comment):
        if not comment.get("deleted"):
            out.append(comment)
        for reply in comment.get("replies") or []:
            walk(reply)
    walk(root)
    return sorted(out, key=lambda c: c.get("created_at") or "")


def review_threads(comments):
    """Every review thread on a task, oldest first.

    A thread is a top-level comment that starts with the Thread line, opened
    by one note of a review; later notes on the same lines arrive as
    follow-up replies in it. An annotated review whose notes were never split
    is one thread of its own. state is resolved (the owner reacted with
    "resolved"), waiting on you (the agent spoke last) or waiting on the agent;
    status is what the agent's last reply declared on its Status line."""
    live = sorted((c for c in comments if not c.get("deleted")), key=lambda c: c.get("created_at") or "")
    split, items = set(), []
    for c in live:
        for reply in c.get("replies") or []:
            if (reply.get("body") or "").startswith(FOLLOW_UP):
                split.add(reply["body"][len(FOLLOW_UP):].split(",", 1)[0].strip())
        body = c.get("body") or ""
        if not body.startswith(THREAD):
            continue
        first, _, rest = body.partition("\n")
        second, _, note = rest.partition("\n")
        if second.startswith(REVIEW_OF):
            split.add(second[len(REVIEW_OF):].strip())
        else:
            note = rest
        anchor = first[len(THREAD):].strip()
        match = ANCHOR.match(anchor)
        path, where = (match.group(1), match.group(2)) if match else (anchor.rsplit(" at ", 1)[0], "")
        quote = []
        for line in note.splitlines():
            if not line.startswith("> "):
                break
            quote.append(line)
        items.append((c, anchor, note.strip(), thread_key(path, where, quote)))
    for c in live:
        if c.get("role") == "review" and c.get("id") not in split and review_decision(c.get("body") or "") == "annotated":
            notes = review_notes(c.get("body") or "")
            if len(notes) == 1:
                path, where, note = notes[0]
                items.append((c, note_anchor(path, where), note, thread_key(path, where, [])))
            else:
                items.append((c, "; ".join(note_anchor(p, w) for p, w, _ in notes) or "whole review",
                              "\n\n".join("%s: %s" % (note_anchor(p, w), t) for p, w, t in notes), None))
    threads = []
    for root, anchor, note, key in sorted(items, key=lambda item: item[0].get("created_at") or ""):
        messages = thread_messages(root)
        resolved = any(a.startswith("human:") for a in (root.get("reactions") or {}).get(RESOLVED, []))
        last = (messages[-1].get("author") or "") if messages else ""
        status = next((line[len("Status:"):].strip() for m in reversed(messages) if (m.get("author") or "").startswith("agent:")
                       for line in (m.get("body") or "").splitlines() if line.startswith("Status:")), None)
        state = "resolved" if resolved else "waiting on you" if last.startswith("agent:") else "waiting on the agent"
        threads.append({"root": root, "anchor": anchor, "note": note, "key": key, "messages": messages, "state": state, "status": status})
    return threads


def latest_review(comments):
    """The newest top-level comment with role review that names a revision, or
    None. Deleted reviews count: a deleted one withdraws what came before it.
    Ties on the one-second timestamps go to the later event."""
    reviews = [(c.get("created_at") or "", i, c) for i, c in enumerate(comments)
               if c.get("role") == "review" and (c.get("deleted") or reviewed_revision(c.get("body") or "")[1])]
    return max(reviews)[2] if reviews else None


def stale_reason(repo, task, main, text):
    """Why a recorded review does not cover the task's work now, or None when it does."""
    base_sha, head_sha, qualifier = reviewed_revision(text)
    if not head_sha:
        return "the recorded review names no revision"
    if qualifier:
        return "the review was taken on the live working tree; review the committed range to complete"
    rng = resolve_range(repo, task, main)
    if not rng["head_sha"]:
        return "the task has no single commit range now"
    if (rng["base_sha"], rng["head_sha"]) != (base_sha, head_sha):
        return "the review covered %s..%s but the task's work is now %s..%s; review again" % (
            base_sha[:12], head_sha[:12], rng["base_sha"][:12], rng["head_sha"][:12])
    return None


def completion_block(repo, task, main, comments):
    """Why the task may not be completed now, or None: its latest bound review
    must approve exactly the commits it has now, and every review thread must
    be resolved."""
    review = latest_review(comments)
    if not review:
        return "no Plannotator review is recorded for this task"
    if review.get("deleted"):
        return "the latest review was deleted; review again"
    if review_decision(review.get("body") or "") != "approved":
        return "the latest review requested changes; approve the current revision first"
    unresolved = [t for t in review_threads(comments) if t["state"] != "resolved"]
    if unresolved:
        return "%d review thread(s) are not resolved; resolve them first" % len(unresolved)
    return stale_reason(repo, task, main, review["body"])


def session_url(log_text):
    """The URL of the Plannotator session a run printed, or None."""
    match = re.search(r"session ready: (http://\S+)", log_text)
    return match.group(1) if match else None


def with_hook(index_html):
    """The dashboard page with the hook that makes it render the review section."""
    return index_html.replace(b"</head>", HOOK.encode() + b"</head>", 1)


def local_host(value):
    """True when a Host or Origin header names this machine."""
    if not value:
        return False
    try:
        host = urllib.parse.urlsplit(value if "//" in value else "//" + value).hostname
    except ValueError:
        return False
    return host in LOCAL_HOSTS


def same_origin(origin, host):
    """True when an Origin header is this server as the browser addresses it."""
    try:
        parts = urllib.parse.urlsplit(origin or "")
    except ValueError:
        return False
    return parts.scheme == "http" and local_host(origin) and parts.netloc.lower() == (host or "").lower()


# --------------------------------------------------------------------------
# state and actions
# --------------------------------------------------------------------------

class Job:
    def __init__(self, key, what, out_path, err_path):
        self.key = key
        self.what = what
        self.out_path = out_path
        self.err_path = err_path
        self.started = time.time()
        self.proc = None
        self.done = False
        self.rc = None
        self.result_path = None
        self.error = None
        self.decision = None
        self.closed = False


class Context:
    def __init__(self, args):
        self.board = Path(args.board).resolve()
        self.repo = Path(args.repo or args.board).resolve()
        self.config = board_config(self.board)
        self.main = args.main
        self.remote = args.remote
        self.actor = args.actor
        code = self.config.get("project_code", "board")
        self.state = Path(args.state or Path.home() / ".local" / "state" / "lattice-review" / code)
        self.state.mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_hex(16)
        self.jobs = {}
        self.notices = {}
        self.runs = 0
        self.plannotator = shutil.which("plannotator")
        self.code = shutil.which("code")
        self.lattice = shutil.which("lattice")
        self.lock = threading.Lock()

    def lattice_cmd(self, *args):
        env = dict(os.environ, LATTICE_NO_UPDATE_CHECK="1")
        result = subprocess.run([self.lattice, *args, "--actor", self.actor], cwd=self.board, env=env,
                                capture_output=True, text=True)
        return result.returncode, (result.stdout + result.stderr).strip()

    def board_write(self, key, *args):
        """A lattice write whose failure is shown on the page instead of being dropped."""
        rc, msg = self.lattice_cmd(*args)
        self.notices[key] = ("ok", args[0] + " " + " ".join(args[1:3])) if rc == 0 else ("err", "lattice %s failed: %s" % (args[0], msg))
        return rc == 0

    def comments(self, short_id):
        env = dict(os.environ, LATTICE_NO_UPDATE_CHECK="1")
        result = subprocess.run([self.lattice, "comments", short_id, "--json"], cwd=self.board, env=env, capture_output=True, text=True)
        try:
            return json.loads(result.stdout).get("data", []) if result.returncode == 0 else []
        except json.JSONDecodeError:
            return []

    def start_plannotator(self, key, record_on=None, base=None, head=None, live=False):
        """One Plannotator session. The range is resolved to commit IDs once, and
        those IDs feed both the patch and the recorded Reviewed line."""
        if live:
            base_sha = rev(self.repo, base) if base else None
            head_sha = rev(self.repo, "HEAD")
            what = "live tree" + (" from " + base_sha[:12] if base_sha else "")
            revision = "%s..%s live" % (base_sha or "-", head_sha)
            args, patch_args = plannotator_args(self.plannotator, base_sha, live=True)
        else:
            base_sha, head_sha = rev(self.repo, base), rev(self.repo, head)
            if not (base_sha and head_sha):
                raise RuntimeError("the range %s..%s does not resolve to commits" % (base, head))
            what = "patch %s..%s" % (base_sha[:12], head_sha[:12])
            revision = "%s..%s" % (base_sha, head_sha)
            args, patch_args = plannotator_args(self.plannotator, base_sha, head_sha)
        with self.lock:
            running = self.jobs.get(key)
            if running and not running.done:
                raise RuntimeError("a Plannotator session for %s is already open; finish or close it first" % key)
            self.runs += 1
            stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            name = "%s-%s-%d" % (key, stamp, self.runs)
            job = Job(key, what, self.state / (name + ".review.md"), self.state / (name + ".log"))
            self.jobs[key] = job
        env = dict(os.environ, PLANNOTATOR_AI="disabled", PLANNOTATOR_SHARE="disabled")
        out = open(job.out_path, "w")
        err = open(job.err_path, "w")
        try:
            job.proc = subprocess.Popen(args, cwd=self.repo, env=env, stdout=out, stderr=err,
                                        stdin=subprocess.PIPE if patch_args else None)
            if patch_args:
                job.proc.stdin.write(run_git(self.repo, *patch_args).encode())
                job.proc.stdin.close()
        except (OSError, RuntimeError) as exc:
            job.error = str(exc)
            job.done = True
            out.close()
            err.close()
            return job

        def source(side, path):
            """A file's text on the reviewed old or new side, or None."""
            if side == "old":
                return run_git(self.repo, "show", "%s:%s" % (base_sha, path), check=False) if base_sha else None
            if live:
                full = self.repo_path(path)
                return full.read_text(errors="replace") if full.is_file() else None
            return run_git(self.repo, "show", "%s:%s" % (head_sha, path), check=False)

        def finish():
            job.rc = job.proc.wait()
            out.close()
            err.close()
            decision, message = parse_review(job.out_path.read_text(errors="replace"))
            job.decision = "dismissed" if job.closed else decision
            if job.closed:
                job.out_path.unlink(missing_ok=True)
            elif job.rc != 0 or decision not in ("approved", "annotated", "dismissed"):
                detail = (job.err_path.read_text(errors="replace").strip() or job.out_path.read_text(errors="replace").strip())[-400:]
                job.error = "plannotator exited %s without a decision: %s" % (job.rc, detail or "no output")
                job.out_path.unlink(missing_ok=True)
            elif decision == "dismissed" or not record_on:
                job.out_path.unlink(missing_ok=True)
            else:
                body = "Plannotator %s (%s), %s\n%s%s\n\n%s\n" % (decision, what, stamp, REVIEWED, revision, message)
                job.out_path.write_text(body)
                rc, msg = self.lattice_cmd("comment", record_on, "--file", str(job.out_path), "--role", "review")
                if rc != 0:
                    job.error = "the review was not recorded on the task: " + msg
                    return
                job.result_path = job.out_path
                self.record_threads(record_on, body, review_notes(message), source, head_sha, job)

        def wait():
            try:
                finish()
            except Exception as exc:  # noqa: BLE001 - any failure must end the job visibly
                job.error = "the review result could not be handled: %r" % exc
            finally:
                job.done = True

        threading.Thread(target=wait, daemon=True).start()
        return job

    def record_threads(self, sid, body, notes, source, sha, job):
        """Each note of a recorded review becomes a thread: a top-level comment
        (Lattice nests one level only) naming the place, the review and the
        quoted lines. A note on lines that already have an open thread (same
        file and quoted lines, or same file and place for a thread without a
        quote) is a follow-up reply in that thread, so a line keeps one
        history."""
        if not notes:
            return
        comments = self.comments(sid)
        review = next((c for c in reversed(comments) if c.get("role") == "review"
                       and (c.get("body") or "").strip() == body.strip()), None)
        if not review:
            job.error = "the review was recorded but its notes could not be split into threads"
            return
        open_threads = {t["key"]: t for t in review_threads(comments)
                        if t["state"] != "resolved" and t["key"] and t["root"].get("id") != review["id"]}
        for i, (path, where, text) in enumerate(notes, 1):
            side = LINES.match(where)
            quote = quoted_lines(source(side.group(3), path), where) if side else []
            anchor = note_anchor(path, where)
            existing = open_threads.get(thread_key(path, where, quote)) or open_threads.get((path, where))
            if existing:
                content = "%s%s, %s at %s:\n%s\n" % (FOLLOW_UP, review["id"], anchor, sha[:12], text)
                args = ("comment", sid, "--reply-to", existing["root"]["id"])
            else:
                content = "%s%s at %s\n%s%s\n%s%s\n" % (THREAD, anchor, sha[:12], REVIEW_OF, review["id"],
                                                         "".join(q + "\n" for q in quote), text)
                args = ("comment", sid)
            note = job.out_path.with_name(job.out_path.stem + ".note%d.md" % i)
            note.write_text(content)
            rc, msg = self.lattice_cmd(*args, "--file", str(note))
            note.unlink(missing_ok=True)
            if rc != 0:
                job.error = "note %d of the review was not recorded as a thread: %s" % (i, msg)
                return

    def post_reply(self, sid, parent, text):
        """The owner's reply in one thread, from the review section."""
        if not text.strip():
            raise RuntimeError("the reply is empty")
        (self.state / "tmp").mkdir(exist_ok=True)
        path = self.state / "tmp" / ("reply-%s.md" % secrets.token_hex(6))
        path.write_text(text.strip() + "\n")
        try:
            if self.board_write(sid, "comment", sid, "--reply-to", parent, "--file", str(path)):
                self.notices[sid] = ("ok", "reply posted")
        finally:
            path.unlink(missing_ok=True)

    def close_session(self, key):
        """End an abandoned Plannotator session; nothing is recorded."""
        job = self.jobs.get(key)
        if job and not job.done and job.proc:
            job.closed = True
            job.proc.terminate()

    def close_all(self):
        for key in list(self.jobs):
            self.close_session(key)

    def repo_path(self, path):
        full = (self.repo / path).resolve()
        if self.repo not in full.parents:
            raise RuntimeError("not a repository path: " + path)
        return full

    def code_open(self, path):
        """Open one file in the VS Code window this server was started from."""
        subprocess.Popen([self.code, "--reuse-window", str(path)])

    def side(self, sha, path):
        """A temp copy's name: commit, a digest of the full path, the file name."""
        return self.state / "tmp" / ("%s-%s-%s" % (sha[:12], hashlib.sha1(path.encode()).hexdigest()[:8], Path(path).name))

    def code_diff(self, base, head, path, old_path, status):
        """Open one file of the range in VS Code's two-file diff."""
        base_sha = rev(self.repo, base)
        head_sha = None if head == WORKTREE else rev(self.repo, head)
        if not base_sha or (head != WORKTREE and not head_sha):
            raise RuntimeError("the range %s..%s does not resolve to commits" % (base, head))
        (self.state / "tmp").mkdir(exist_ok=True)
        left = self.side(base_sha, old_path or path)
        left.write_bytes(b"" if status == "A" else run_git(self.repo, "show", base_sha + ":" + (old_path or path), binary=True))
        if head == WORKTREE:
            right = self.repo_path(path)
        else:
            right = self.side(head_sha, path)
            right.write_bytes(b"" if status == "D" else run_git(self.repo, "show", head_sha + ":" + path, binary=True))
        subprocess.Popen([self.code, "--reuse-window", "--diff", str(left), str(right)])


# --------------------------------------------------------------------------
# the review section
# --------------------------------------------------------------------------

STYLE = """
body{margin:0;padding:0 0 .5rem;background:transparent;color:var(--text-primary,#e4e7eb);font:.85rem/1.45 var(--font-body,system-ui,sans-serif)}
table{border-collapse:collapse;width:100%;margin:.3rem 0}td,th{text-align:left;padding:.15rem .4rem;border-bottom:1px solid var(--border,#2a2f37);vertical-align:top}
th{color:var(--text-muted,#9aa4b2);font-weight:600}code{font-family:var(--font-mono,monospace);font-size:.8rem}
pre{white-space:pre-wrap;font:.8rem/1.4 var(--font-mono,monospace);margin:.3rem 0;padding:.4rem;border:1px solid var(--border,#2a2f37);border-radius:var(--radius-sm,4px)}
form{display:inline}button{padding:.125rem .5rem;margin:.1rem .2rem .1rem 0;border:1px solid var(--border,#3a4250);border-radius:var(--radius-sm,4px);background:var(--surface,#2a2f37);color:var(--text-primary,#e4e7eb);font-size:.8rem;cursor:pointer}
button:hover{background:var(--surface-hover,#3a4250)}button.primary{background:var(--accent-primary,#2b6cb0);color:var(--text-on-accent,#fff);border-color:var(--accent-primary,#2b6cb0)}
p{margin:.3rem 0}.muted{color:var(--text-muted,#9aa4b2)}.warn{color:var(--color-warning,#f6c343)}.err{color:var(--color-danger,#ff7b72)}.ok{color:var(--color-success,#7ee787)}
.next{padding:.4rem;border:1px solid var(--accent-primary,#2b6cb0);border-radius:var(--radius-sm,4px)}
.thread{margin:.5rem 0;padding:.2rem 0 .2rem .6rem;border-left:3px solid var(--color-warning,#f6c343)}.thread.resolved{border-left-color:var(--color-success,#7ee787)}
.msg{margin:.25rem 0}.msg .text{white-space:pre-wrap}form.reply{display:flex;gap:.3rem;align-items:flex-end;margin:.3rem 0}
textarea{flex:1;min-height:2.6rem;font:inherit;color:inherit;background:var(--surface,#2a2f37);border:1px solid var(--border,#3a4250);border-radius:var(--radius-sm,4px);padding:.25rem}
"""

INHERIT = """<script>try{var s=getComputedStyle(parent.document.documentElement);
["--text-primary","--text-muted","--accent-primary","--text-on-accent","--surface","--surface-hover","--border","--radius-sm",
"--font-body","--font-mono","--color-warning","--color-danger","--color-success"].forEach(function(v){
document.documentElement.style.setProperty(v,s.getPropertyValue(v))})}catch(e){}</script>"""


def e(value):
    return html.escape("" if value is None else str(value))


def page(title, body, refresh=False):
    meta = "<meta http-equiv='refresh' content='5'>" if refresh else ""
    return ("<!doctype html><html><head><meta charset='utf-8'><title>" + e(title) + "</title>" + meta + INHERIT
            + "<style>" + STYLE + "</style></head><body>" + body + "</body></html>").encode()


def button(ctx, action, label, fields=None, primary=False, tab=False):
    """A one-button form. tab=True submits into a new tab of the same browser
    and reloads this page shortly after, so the section shows the new state."""
    hidden = "".join("<input type='hidden' name='%s' value='%s'>" % (e(k), e(v)) for k, v in (fields or {}).items())
    cls = " class='primary'" if primary else ""
    target = " target='_blank' onsubmit=\"setTimeout(function(){location.reload()},1500)\"" if tab else ""
    return ("<form method='post' action='%s'%s><input type='hidden' name='token' value='%s'>%s<button%s>%s</button></form>"
            % (e(action), target, ctx.token, hidden, cls, e(label)))


def reply_form(ctx, action, parent):
    return ("<form method='post' action='%s' class='reply'><input type='hidden' name='token' value='%s'>"
            "<input type='hidden' name='parent' value='%s'><textarea name='body' placeholder='Reply in this thread'></textarea>"
            "<button>Reply</button><button name='resolve' value='1'>Reply and resolve</button></form>" % (e(action), ctx.token, e(parent)))


def render_threads(ctx, sid, threads):
    """Each review thread with its whole history, a reply box and Resolve."""
    act = REVIEW_PATH + "/t/" + sid + "/"
    unresolved = sum(1 for t in threads if t["state"] != "resolved")
    out = ["<p><b>Review threads</b> <span class='muted'>%d open of %d. Continue a thread here; a new Plannotator note starts a new one.</span></p>"
           % (unresolved, len(threads))]
    for t in threads:
        resolved = t["state"] == "resolved"
        status = " <span class='muted'>agent: %s</span>" % e(t["status"]) if t["status"] and not resolved else ""
        out.append("<div class='thread%s'><p><b>%s</b> <span class='%s'>%s</span>%s</p>"
                   % (" resolved" if resolved else "", e(t["anchor"]), "ok" if resolved else "warn", e(t["state"]), status))
        for m in t["messages"]:
            text = t["note"] if m is t["root"] else m.get("body") or ""
            out.append("<div class='msg'><span class='muted'>%s, %s%s</span><div class='text'>%s</div></div>"
                       % (e(m.get("author")), e(m.get("created_at")), ", edited" if m.get("edited") else "", e(text)))
        if resolved:
            out.append(button(ctx, act + "reopen", "Reopen", {"comment": t["root"]["id"]}))
        else:
            out.append(reply_form(ctx, act + "reply", t["root"]["id"]))
            out.append(button(ctx, act + "resolve", "Resolve", {"comment": t["root"]["id"]}))
        out.append("</div>")
    return "".join(out)


def next_step(ctx, task, rng, review, threads, running, block):
    """One line that says what the owner does now."""
    sid, status = task["short_id"], task.get("status")
    act = REVIEW_PATH + "/t/" + sid + "/"
    on_agent = sum(1 for t in threads if t["state"] == "waiting on the agent")
    on_you = sum(1 for t in threads if t["state"] == "waiting on you")
    if running:
        text = ("Write your notes in the Plannotator tab, then Send Feedback or Approve. Plannotator then says the feedback "
                "went back to the agent: close that tab and come back here. Each note becomes a thread below.")
    elif status in ("done", "cancelled") or rng["mode"] == "none":
        return ""
    elif review and review_decision(review.get("body") or "") == "approved" and not stale_reason(ctx.repo, task, ctx.main, review["body"]) \
            and on_agent + on_you:
        text = ("Approved at %s. %d thread(s) still open: Resolve each one you are done with, or Reply and resolve to add a "
                "last word. If one needs more work, reply in it and move the task back to in progress." % (rng["head_sha"][:12], on_agent + on_you))
    elif on_agent:
        text = ("%d thread(s) wait on the agent. Nothing notifies it: send the agent session the task ID %s. "
                "It answers each thread here before changing code, then returns the task to review." % (on_agent, sid))
        if status != "in_progress" and "in_progress" in ctx.config.get("workflow", {}).get("transitions", {}).get(status, []):
            text = "Next: move the task back to in progress and send the agent session the task ID %s. " % sid + text
            return "<p class='next'>%s %s</p>" % (e(text), button(ctx, act + "rework", "Move to in progress", primary=True))
    elif on_you:
        text = "%d thread(s) have an answer from the agent. Reply in the thread, or Resolve it when you are satisfied." % on_you
    elif not review:
        text = "Open Plannotator on the range below. Each note you send becomes its own thread on this task."
    elif block is None:
        text = "Approved and every thread resolved: Mark done below, then merge and push."
    else:
        text = "Not ready to complete: %s." % block
    return "<p class='next'>%s</p>" % e(text)


def tool_notes(ctx):
    notes = []
    if not ctx.plannotator:
        notes.append("<p class='warn'>plannotator is not on PATH. " + INSTALL_HINT + "</p>")
    if not ctx.code:
        notes.append("<p class='warn'>The <code>code</code> command is not on PATH. Start this server from a VS Code terminal to open files.</p>")
    return "".join(notes)


def notice(ctx, key):
    kind, text = ctx.notices.pop(key, (None, None))
    return "<p class='%s'>%s</p>" % (kind, e(text)) if kind else ""


def range_summary(task, rng):
    if rng["mode"] == "branch":
        return "branch <code>%s</code> from <code>%s</code>" % (e(rng["branch"]), e(rng["base"][:12]))
    if rng["mode"] == "commits" and rng["contiguous"]:
        return "%d commit(s) with trailer <code>Task: %s</code>, range <code>%s..%s</code>" % (
            len(rng["commits"]), e(task["short_id"]), e(rng["base_sha"][:12]), e(rng["head_sha"][:12]))
    if rng["mode"] == "commits":
        return "%d commit(s) with trailer <code>Task: %s</code>, not contiguous: review them one by one" % (
            len(rng["commits"]), e(task["short_id"]))
    return "no linked branch and no commit carries <code>Task: %s</code> yet" % e(task["short_id"])


def render_review(ctx, task):
    sid = task["short_id"]
    act = REVIEW_PATH + "/t/" + sid + "/"
    rng = resolve_range(ctx.repo, task, ctx.main)
    head_now = rev(ctx.repo, "HEAD")
    dirty = worktree_dirty(ctx.repo)
    body = [tool_notes(ctx), notice(ctx, sid), "<p>Work: %s</p>" % range_summary(task, rng)]
    if rng["mode"] == "branch" and rng["branch"] != current_branch(ctx.repo):
        body.append("<p class='warn'>The repo is on <code>%s</code>, this task's branch is <code>%s</code>. The range review and the diffs use the task's branch.</p>"
                    % (e(current_branch(ctx.repo)), e(rng["branch"])))
    actions = []
    if ctx.plannotator:
        if rng["base_sha"]:
            actions.append(button(ctx, act + "plannotator", "Plannotator: the whole range", {"base": rng["base"], "head": rng["head"]}, primary=True, tab=True))
            if rng["head_sha"] == head_now and dirty:
                actions.append(button(ctx, act + "plannotator", "Plannotator: live tree, feedback only", {"base": rng["base"], "live": "1"}, tab=True))
        elif rng["mode"] == "none" and dirty:
            actions.append(button(ctx, act + "plannotator", "Plannotator: uncommitted changes, feedback only", {"base": "HEAD", "live": "1"}, tab=True))
    if actions:
        body.append("<p>" + " ".join(actions) + "</p>")
    if rng["commits"]:
        body.append("<table><tr><th>Commit</th><th>Subject</th><th>Date</th><th></th></tr>")
        for c in rng["commits"]:
            body.append("<tr><td><code>%s</code></td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                e(c["hash"][:12]), e(c["subject"]), e(c["date"]),
                button(ctx, act + "plannotator", "Plannotator", {"base": c["hash"] + "^", "head": c["hash"]}, tab=True) if ctx.plannotator else ""))
        body.append("</table>")
    if rng["base_sha"]:
        try:
            files = changed_files(ctx.repo, rng["base"], rng["head"])
        except RuntimeError as exc:
            files = []
            body.append("<p class='err'>%s</p>" % e(exc))
        body.append("<table><tr><th></th><th>File (%d)</th><th></th></tr>" % len(files))
        for f in files:
            shown = f["path"] if f["old_path"] == f["path"] else f["old_path"] + " → " + f["path"]
            cells = ""
            if ctx.code:
                if rng["head_sha"] == head_now and (ctx.repo / f["path"]).is_file():
                    cells += button(ctx, act + "open", "open", {"path": f["path"]})
                cells += button(ctx, act + "filediff", "diff", {"path": f["path"], "old_path": f["old_path"], "status": f["status"],
                                                                "base": rng["base"], "head": rng["head"]})
            body.append("<tr><td>%s</td><td><code>%s</code></td><td>%s</td></tr>" % (e(f["status"]), e(shown), cells))
        body.append("</table>")
    job = ctx.jobs.get(sid)
    running = bool(job and not job.done)
    if job:
        state = "Plannotator running since " + time.strftime("%H:%M:%S", time.localtime(job.started)) if running else "Plannotator finished"
        body.append("<p>%s (%s). Log <code>%s</code></p>" % (e(state), e(job.what), e(job.err_path)))
        url = session_url(job.err_path.read_text()) if job.err_path.is_file() else None
        if running:
            link = "<a href='%s' target='_blank' rel='noopener'>Open the session</a>. " % e(url) if url else ""
            body.append("<p>%sAnnotations stay in that session until you click Send Feedback or Approve; then they land on the task and show here. %s</p>"
                        % (link, button(ctx, act + "close", "Close session")))
        if job.error:
            body.append("<p class='err'>%s</p>" % e(job.error))
        elif job.done and not job.result_path:
            body.append("<p class='muted'>Plannotator closed without a review.</p>")
    comments = ctx.comments(sid)
    review = latest_review(comments)
    threads = review_threads(comments)
    block = completion_block(ctx.repo, task, ctx.main, comments) if rng["mode"] != "none" else None
    body.insert(2, next_step(ctx, task, rng, review, threads, running, block))
    if review:
        text = review.get("body") or ""
        label = {"approved": "approved", "annotated": "changes requested"}.get(review_decision(text), "review")
        body.append("<p>Latest review: <b>%s</b> <span class='muted'>%s %s</span></p><details><summary>Full review text</summary><pre>%s</pre></details>" % (
            e(label), e(review.get("author")), e(review.get("created_at")), e(text)))
    if threads:
        body.append(render_threads(ctx, sid, threads))
    if task.get("status") not in ("done", "cancelled") and rng["mode"] != "none":
        if block:
            body.append("<p class='muted'>Completion: %s.</p>" % e(block))
        else:
            body.append(button(ctx, act + "complete", "Mark done: approved at %s" % rng["head_sha"][:12], primary=True))
    return page(sid + " review", "".join(body), refresh=running)


# --------------------------------------------------------------------------
# http: the dashboard's handler class, with the review routes on top
# --------------------------------------------------------------------------

def make_handler(ctx, base=None, static_dir=None):
    """The dashboard handler class extended with the review routes.

    base and static_dir default to Lattice's own; the tests pass a stand-in."""
    if base is None:
        from lattice.dashboard import server as dashboard
        base = dashboard._make_handler_class(ctx.board / ".lattice")
        static_dir = dashboard.STATIC_DIR

    class Handler(base):
        def log_message(self, fmt, *args):
            if not self.path.startswith("/api/"):
                sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

        def send_page(self, data, status=200, content_type="text/html; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def send_json(self, status, record):
            self.send_page(json.dumps(record).encode(), status, "application/json; charset=utf-8")

        def redirect(self, location):
            self.send_response(303)
            self.send_header("Location", location)
            self.end_headers()

        def forbidden(self, why):
            self.send_page(page("forbidden", "<p>" + e(why) + "</p>"), 403)

        def do_GET(self):
            if not local_host(self.headers.get("Host")):
                return self.forbidden("requests must address this machine")
            parts = [p for p in urllib.parse.urlsplit(self.path).path.split("/") if p]
            if parts[:1] == ["t"] and len(parts) == 2:
                task = find_task(ctx.board, parts[1])
                return self.redirect("/#/task/" + task["id"]) if task else self.send_page(page("not found", "<p>not found</p>"), 404)
            if parts[:1] != [REVIEW_PATH.strip("/")]:
                return super().do_GET()
            if parts[1:2] == ["t"] and len(parts) == 3:
                task = find_task(ctx.board, parts[2])
                if task:
                    return self.send_page(render_review(ctx, task))
            if len(parts) == 1:
                return self.redirect("/")
            self.send_page(page("not found", "<p>not found</p>"), 404)

        def _serve_static(self, filename, content_type):
            path = static_dir / filename
            if filename != "index.html" or not path.is_file():
                return super()._serve_static(filename, content_type)
            self.send_page(with_hook(path.read_bytes()))

        def do_POST(self):
            host = self.headers.get("Host")
            if not local_host(host):
                return self.forbidden("requests must address this machine")
            origin = self.headers.get("Origin")
            if origin and not same_origin(origin, host):
                return self.forbidden("cross-site request refused")
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length < 0 or length > MAX_BODY:
                return self.send_json(413, {"ok": False, "error": {"code": "PAYLOAD_TOO_LARGE", "message": "request body too large"}})
            raw = self.rfile.read(length)
            parts = [p for p in urllib.parse.urlsplit(self.path).path.split("/") if p]
            if parts[:1] == [REVIEW_PATH.strip("/")]:
                return self.review_post(parts, raw)
            if not origin:
                return self.forbidden("dashboard writes need an Origin header from this machine")
            try:
                record = json.loads(raw)
            except ValueError:
                record = None
            if not isinstance(record, dict):
                return self.send_json(400, {"ok": False, "error": {"code": "BAD_REQUEST", "message": "the body must be a JSON object"}})
            if not self.gate(parts, record):
                return
            raw = json.dumps(record).encode()
            self.rfile = io.BytesIO(raw)
            del self.headers["Content-Length"]
            self.headers["Content-Length"] = str(len(raw))
            super().do_POST()

        def gate(self, parts, record):
            """Dashboard writes carry this server's actor; done needs an approved
            review of the task's current work. False means a reply was sent."""
            if record.get("actor") == "dashboard:web":
                record["actor"] = ctx.actor
            if parts[:2] == ["api", "tasks"] and parts[3:] == ["status"] and record.get("status") == "done":
                task = find_task(ctx.board, parts[2])
                if task and resolve_range(ctx.repo, task, ctx.main)["mode"] != "none":
                    block = completion_block(ctx.repo, task, ctx.main, ctx.comments(task["short_id"]))
                    if block:
                        self.send_json(409, {"ok": False, "error": {"code": "REVIEW_REQUIRED", "message": "not completed: " + block}})
                        return False
            return True

        def review_post(self, parts, raw):
            form = {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode()).items()}
            if form.get("token") != ctx.token:
                return self.forbidden("bad token")
            if len(parts) != 4 or parts[1] != "t":
                return self.send_page(page("not found", "<p>not found</p>"), 404)
            sid, action = parts[2], parts[3]
            task = find_task(ctx.board, sid)
            if not task:
                return self.send_page(page("not found", "<p>not found</p>"), 404)
            try:
                if action == "plannotator":
                    return self.open_session(sid, form)
                elif action == "close":
                    ctx.close_session(sid)
                elif action == "open":
                    ctx.code_open(ctx.repo_path(form["path"]))
                elif action == "filediff":
                    ctx.code_diff(form["base"], form["head"], form["path"], form.get("old_path"), form.get("status", "M"))
                elif action == "complete":
                    block = completion_block(ctx.repo, task, ctx.main, ctx.comments(sid))
                    if block:
                        ctx.notices[sid] = ("err", "not completed: " + block)
                    else:
                        ctx.board_write(sid, "status", sid, "done", "--no-auto-review")
                elif action == "reply":
                    if form.get("body", "").strip() or form.get("resolve") != "1":
                        ctx.post_reply(sid, form["parent"], form.get("body", ""))
                    if form.get("resolve") == "1":
                        ctx.board_write(sid, "react", sid, form["parent"], RESOLVED)
                elif action in ("resolve", "reopen"):
                    ctx.board_write(sid, "react" if action == "resolve" else "unreact", sid, form["comment"], RESOLVED)
                elif action == "rework":
                    ctx.board_write(sid, "status", sid, "in_progress", "--no-auto-review")
            except (RuntimeError, OSError, KeyError) as exc:
                ctx.notices[sid] = ("err", str(exc))
            self.redirect(REVIEW_PATH + "/t/" + sid)

        def open_session(self, sid, form):
            """Start Plannotator and send this tab to its session; the task page
            reloads on its own. Runs in the browser the owner already uses."""
            try:
                job = ctx.start_plannotator(sid, record_on=sid, base=form.get("base") or None, head=form.get("head") or None,
                                            live=form.get("live") == "1")
            except RuntimeError as exc:
                job = ctx.jobs.get(sid)
                url = session_url(job.err_path.read_text()) if job and not job.done and job.err_path.is_file() else None
                if url:
                    return self.redirect(url)
                return self.send_page(page("Plannotator", "<p class='err'>%s</p>" % e(exc)))
            for _ in range(100):
                if job.err_path.is_file():
                    url = session_url(job.err_path.read_text())
                    if url:
                        return self.redirect(url)
                if job.done:
                    break
                time.sleep(0.2)
            why = job.error or "Plannotator printed no session URL within 20 seconds; see %s" % job.err_path
            self.send_page(page("Plannotator", "<p class='err'>%s</p>" % e(why)))

        def _handle_post_open_notes(self, ld, task_id):
            self.open_prose(ld, task_id, "notes")

        def _handle_post_open_plans(self, ld, task_id):
            self.open_prose(ld, task_id, "plan")

        def open_prose(self, ld, task_id, kind):
            """Lattice's notes and plans buttons, opening in VS Code instead of xdg-open."""
            from lattice.core.ids import validate_id
            from lattice.storage.operations import resolve_task_prose_path, scaffold_plan
            if not validate_id(task_id, "task"):
                return self.send_json(400, {"ok": False, "error": {"code": "INVALID_ID", "message": "Invalid task ID format"}})
            if not ctx.code:
                return self.send_json(500, {"ok": False, "error": {"code": "OPEN_ERROR", "message": "the code command is not on PATH; start the server from a VS Code terminal"}})
            path, authority = resolve_task_prose_path(ld, task_id, kind)
            if path is None:
                if kind != "plan" or authority.location != "active":
                    return self.send_json(404, {"ok": False, "error": {"code": "NOT_FOUND", "message": "No %s file for task %s" % (kind, task_id)}})
                snapshot = authority.snapshot
                scaffold_plan(ld, task_id, snapshot.get("title", "Untitled"), snapshot.get("short_id"), snapshot.get("description"))
                path = ld / "plans" / (task_id + ".md")
            resolved = path.resolve()
            if not str(resolved).startswith(str(ld.resolve())):
                return self.send_json(403, {"ok": False, "error": {"code": "FORBIDDEN", "message": "Path traversal not allowed"}})
            ctx.code_open(resolved)
            self.send_json(200, {"ok": True, "data": {"opened": str(resolved)}})

    return Handler


def ensure_lattice(argv):
    """Run under the interpreter the lattice command uses, so its dashboard imports."""
    try:
        import lattice.dashboard.server  # noqa: F401
        return
    except ImportError:
        pass
    script = shutil.which("lattice")
    first = Path(script).read_text(errors="replace").splitlines()[0] if script else ""
    command = shlex.split(first[2:]) if first.startswith("#!") else []
    if not command or os.environ.get("LATTICE_REVIEW_REEXEC"):
        sys.exit("lattice is not importable from %s; run this with the Python that has lattice installed" % sys.executable)
    os.environ["LATTICE_REVIEW_REEXEC"] = "1"
    os.execv(command[0], command + [os.path.abspath(__file__), *argv])


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--board", default=".", help="directory holding .lattice (default: cwd)")
    parser.add_argument("--repo", help="git repository to read commits from (default: the board directory)")
    parser.add_argument("--port", type=int, help="the one port to open in the browser (default: the board's dashboard_port)")
    parser.add_argument("--main", default="main", help="integration branch name")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--actor", default="human:" + os.environ.get("USER", "owner"), help="actor recorded on writes")
    parser.add_argument("--state", help="where review output, logs and temp files for diffs are kept")
    args = parser.parse_args(argv)
    ensure_lattice(argv)
    ctx = Context(args)
    if not ctx.lattice:
        sys.exit("lattice is not on PATH")
    port = args.port or ctx.config.get("dashboard_port", 8799)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(ctx))
    print("board with review at http://127.0.0.1:%d (board %s, repo %s, actor %s, logs %s)" % (port, ctx.board, ctx.repo, ctx.actor, ctx.state))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        ctx.close_all()


if __name__ == "__main__":
    main()
