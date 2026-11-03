#!/usr/bin/env python3
"""Local review launcher for a Lattice board.

Serves a page on 127.0.0.1 that lists the board's tasks, resolves each
task's commits from its linked branch or from "Task: <ID>" commit
trailers, and opens them in Plannotator or the VS Code multi-diff editor.
Plannotator's decision lands on the task as a comment, bound to the
reviewed revision, and the task can be completed with it only while that
revision is still the task's work.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATUS_ORDER = ["in_review", "in_progress", "todo", "backlog", "done", "cancelled"]
EXTENSION_ID = "agent-alignment.lattice-review-links"
WORKTREE = "WORKTREE"
REVIEWED = "Reviewed: "
INSTALL_HINT = ("Install Plannotator by downloading its installer, reading it, then running it: "
                "<code>curl -fsSLo plannotator-install.sh https://plannotator.ai/install.sh</code>, "
                "<code>less plannotator-install.sh</code>, <code>bash plannotator-install.sh --minimal</code>. "
                "Then restart the launcher.")


# --------------------------------------------------------------------------
# git and board reads (pure functions, covered by the tests)
# --------------------------------------------------------------------------

def run_git(repo, *args, check=True):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git " + " ".join(args) + " failed")
    return result.stdout


def rev(repo, ref):
    """Immutable commit ID for a ref, or None when it does not resolve."""
    out = run_git(repo, "rev-parse", "--verify", "--quiet", ref + "^{commit}", check=False).strip()
    return out or None


def board_config(board):
    return json.loads((Path(board) / ".lattice" / "config.json").read_text())


def task_number(short_id):
    tail = (short_id or "").rsplit("-", 1)[-1]
    return int(tail) if tail.isdigit() else 0


def load_tasks(board):
    tasks = [json.loads(p.read_text()) for p in (Path(board) / ".lattice" / "tasks").glob("*.json")]

    def key(task):
        status = task.get("status") or ""
        rank = STATUS_ORDER.index(status) if status in STATUS_ORDER else len(STATUS_ORDER)
        return (rank, task_number(task.get("short_id")))

    return sorted(tasks, key=key)


def needs_human(task):
    flag = task.get("needs_human")
    return flag.get("reason", "flagged") if isinstance(flag, dict) else ("flagged" if flag else "")


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
    """Name-status rows; renames and copies keep the old path for the base side."""
    args = ["diff", "--name-status", "-M", base] + ([] if head == WORKTREE else [head])
    files = []
    for line in run_git(repo, *args).splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            files.append({"status": parts[0][0], "path": parts[2], "old_path": parts[1]})
        elif len(parts) == 2:
            files.append({"status": parts[0][0], "path": parts[1], "old_path": parts[1]})
    return files


def unpushed(repo, main, remote):
    upstream = remote + "/" + main
    if not rev(repo, upstream):
        return {"upstream": upstream, "exists": False, "commits": []}
    return {"upstream": upstream, "exists": True, "commits": log_commits(repo, upstream + "..HEAD")}


def current_branch(repo):
    return run_git(repo, "rev-parse", "--abbrev-ref", "HEAD", check=False).strip()


def worktree_dirty(repo):
    return bool(run_git(repo, "status", "--porcelain", check=False).strip())


def vscode_uri(repo, base, head, title):
    query = urllib.parse.urlencode({"repo": str(repo), "base": base, "head": head, "title": title})
    return "vscode://" + EXTENSION_ID + "/diff?" + query


def plannotator_args(plannotator, base=None, head=None, live=False):
    """Command for one Plannotator session: the live checked-out tree from base,
    or a static patch of base..head fed on stdin."""
    if live:
        args = [plannotator, "review", "--git", "--no-git-remote-check", "--json"]
        return args + (["--base", base] if base else []), None
    return [plannotator, "review", "--patch-file", "-", "--json"], ["diff", base] + ([] if head == WORKTREE else [head])


def parse_review(stdout):
    """Plannotator's --json record: decision approved, annotated or dismissed."""
    for line in reversed(stdout.strip().splitlines()):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and "decision" in record:
            return record["decision"], (record.get("message") or "").strip()
    return None, stdout.strip()


def reviewed_revision(result_path):
    """The (base_sha, head_sha, clean) a recorded review was taken against."""
    for line in Path(result_path).read_text().splitlines():
        if line.startswith(REVIEWED):
            fields = line[len(REVIEWED):].split()
            base_sha, head_sha = fields[0].split("..")
            return base_sha, head_sha, "dirty" not in fields
    return None, None, False


def stale_reason(repo, task, main, result_path):
    """Why a recorded review may not complete the task now, or None when it may."""
    base_sha, head_sha, clean = reviewed_revision(result_path)
    if not head_sha:
        return "the recorded review names no revision"
    if not clean:
        return "the review was taken on a working tree with uncommitted changes; review the committed range instead"
    rng = resolve_range(repo, task, main)
    if not rng["head_sha"]:
        return "the task has no single commit range now"
    if (rng["base_sha"], rng["head_sha"]) != (base_sha, head_sha):
        return "the review covered %s..%s but the task's work is now %s..%s; review again" % (
            base_sha[:12], head_sha[:12], rng["base_sha"][:12], rng["head_sha"][:12])
    return None


# --------------------------------------------------------------------------
# launcher state and actions
# --------------------------------------------------------------------------

class Job:
    def __init__(self, key, out_path, err_path):
        self.key = key
        self.out_path = out_path
        self.err_path = err_path
        self.started = time.time()
        self.proc = None
        self.done = False
        self.rc = None
        self.result_path = None
        self.error = None
        self.decision = None
        self.what = ""


class Context:
    def __init__(self, args):
        self.board = Path(args.board).resolve()
        self.repo = Path(args.repo or args.board).resolve()
        self.config = board_config(self.board)
        self.main = args.main
        self.remote = args.remote
        self.actor = args.actor
        self.dashboard = args.dashboard_url or "http://127.0.0.1:%d" % self.config.get("dashboard_port", 8799)
        code = self.config.get("project_code", "board")
        self.state = Path(args.state or Path.home() / ".local" / "state" / "lattice-review" / code)
        self.state.mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_hex(16)
        self.jobs = {}
        self.notices = {}
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
        rc, out = self.lattice_cmd("comments", short_id, "--json")
        if rc != 0:
            return []
        try:
            return json.loads(out).get("data", [])
        except json.JSONDecodeError:
            return []

    def start_plannotator(self, key, record_on=None, base=None, head=None, live=False):
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        out_path = self.state / (key + "-" + stamp + ".review.md")
        err_path = self.state / (key + "-" + stamp + ".log")
        job = Job(key, out_path, err_path)
        if live:
            base_sha, head_sha = (rev(self.repo, base) if base else None), rev(self.repo, "HEAD")
            dirty = worktree_dirty(self.repo)
            job.what = "live tree" + (" from " + base if base else "") + (", dirty" if dirty else ", clean")
            revision = "%s..%s%s" % (base_sha or "-", head_sha, " dirty" if dirty else "")
        else:
            base_sha, head_sha = rev(self.repo, base), rev(self.repo, head)
            job.what = "patch %s..%s" % (str(base)[:12], str(head)[:12])
            revision = "%s..%s" % (base_sha, head_sha)
        env = dict(os.environ, PLANNOTATOR_AI="disabled", PLANNOTATOR_SHARE="disabled")
        args, patch_args = plannotator_args(self.plannotator, base, head, live)
        out = open(out_path, "w")
        err = open(err_path, "w")
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
        with self.lock:
            self.jobs[key] = job
        if job.error:
            return job

        def wait():
            job.rc = job.proc.wait()
            out.close()
            err.close()
            decision, message = parse_review(out_path.read_text())
            job.decision = decision
            if decision != "dismissed" and (message or decision) and record_on:
                body = "Plannotator %s (%s), %s\n%s%s\n\n%s\n" % (decision or "result", job.what, stamp, REVIEWED, revision, message)
                out_path.write_text(body)
                rc, msg = self.lattice_cmd("comment", record_on, "--file", str(out_path), "--role", "review")
                if rc == 0:
                    job.result_path = out_path
                else:
                    job.error = "the review was not recorded on the task: " + msg
            else:
                out_path.unlink(missing_ok=True)
            job.done = True

        threading.Thread(target=wait, daemon=True).start()
        return job

    def code_diff(self, base, head, path, old_path, status):
        """Open one file of the range in VS Code's two-file diff."""
        tmp = self.state / "tmp"
        tmp.mkdir(exist_ok=True)
        left = tmp / (base[:12].replace("/", "_") + "-" + Path(old_path or path).name)
        left.write_text("" if status == "A" else run_git(self.repo, "show", base + ":" + (old_path or path)))
        if head == WORKTREE:
            right = self.repo / path
        else:
            right = tmp / (head[:12].replace("/", "_") + "-" + Path(path).name)
            right.write_text("" if status == "D" else run_git(self.repo, "show", head + ":" + path))
        subprocess.Popen([self.code, "--diff", str(left), str(right)])


# --------------------------------------------------------------------------
# html
# --------------------------------------------------------------------------

STYLE = """
body{font:14px/1.45 system-ui,sans-serif;margin:0;padding:1.2rem 2rem;background:#14171c;color:#e4e7eb}
a{color:#7fb3ff}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:.3rem .5rem;border-bottom:1px solid #2a2f37;vertical-align:top}
th{color:#9aa4b2;font-weight:600}pre{white-space:pre-wrap;background:#1c2128;padding:.6rem;border-radius:4px}
form{display:inline}button,input[type=submit]{background:#2b6cb0;color:#fff;border:0;padding:.25rem .6rem;border-radius:3px;cursor:pointer;margin:.1rem}
button.quiet{background:#3a4250}textarea{width:100%;min-height:6rem;background:#1c2128;color:#e4e7eb;border:1px solid #3a4250}
.tag{background:#2a2f37;border-radius:3px;padding:0 .35rem;margin-right:.2rem;font-size:12px}
.muted{color:#9aa4b2}.warn{color:#f6c343}.err{color:#ff7b72}.ok{color:#7ee787}h1,h2{margin:.4rem 0}
"""


def e(value):
    return html.escape("" if value is None else str(value))


def page(title, body):
    return ("<!doctype html><html><head><meta charset='utf-8'><title>" + e(title) + "</title><style>" + STYLE
            + "</style></head><body>" + body + "</body></html>").encode()


def button(ctx, action, label, fields=None, quiet=False):
    hidden = "".join("<input type='hidden' name='%s' value='%s'>" % (e(k), e(v)) for k, v in (fields or {}).items())
    cls = " class='quiet'" if quiet else ""
    return ("<form method='post' action='%s'><input type='hidden' name='token' value='%s'>%s<button%s>%s</button></form>"
            % (e(action), ctx.token, hidden, cls, e(label)))


def tool_notes(ctx):
    notes = []
    if not ctx.plannotator:
        notes.append("<p class='warn'>plannotator is not on PATH. " + INSTALL_HINT + "</p>")
    if not ctx.code:
        notes.append("<p class='warn'>The <code>code</code> command is not on PATH. Start the launcher from a VS Code terminal for per-file diffs.</p>")
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


def render_index(ctx):
    tasks = load_tasks(ctx.board)
    up = unpushed(ctx.repo, ctx.main, ctx.remote)
    body = ["<h1>%s</h1>" % e(ctx.config.get("project_name", "Board")),
            "<p class='muted'>board <code>%s</code>, repo <code>%s</code> on <code>%s</code>. <a href='%s'>Lattice dashboard</a></p>"
            % (e(ctx.board), e(ctx.repo), e(current_branch(ctx.repo)), e(ctx.dashboard)), tool_notes(ctx), notice(ctx, "index")]
    if up["exists"]:
        body.append("<p>Unpushed on this branch: %d commit(s) past <code>%s</code>. " % (len(up["commits"]), e(up["upstream"])))
        if up["commits"]:
            body.append("<a href='%s'>VS Code multi-diff</a> " % e(vscode_uri(ctx.repo, up["upstream"], "HEAD", "unpushed vs " + up["upstream"])))
        if ctx.plannotator:
            body.append(button(ctx, "/unpushed/plannotator", "Plannotator (working tree, not recorded)", {"base": up["upstream"]}))
        body.append("</p>")
    body.append("<table><tr><th>ID</th><th>Title</th><th>Status</th><th>Prio</th><th>Tags</th><th>Work</th><th></th></tr>")
    for task in tasks:
        sid = task.get("short_id") or task["id"]
        rng = resolve_range(ctx.repo, task, ctx.main)
        flag = " <span class='warn' title='%s'>needs human</span>" % e(needs_human(task)) if needs_human(task) else ""
        actions = []
        if rng["base_sha"]:
            actions.append("<a href='%s'>VS Code</a>" % e(vscode_uri(ctx.repo, rng["base"], rng["head"], sid + " " + task.get("title", ""))))
            if ctx.plannotator:
                actions.append(button(ctx, "/t/%s/plannotator" % sid, "Plannotator", {"base": rng["base"], "head": rng["head"]}, quiet=True))
        body.append("<tr><td><a href='/t/%s'>%s</a></td><td>%s%s</td><td>%s</td><td>%s</td><td>%s</td><td class='muted'>%s</td><td>%s</td></tr>" % (
            e(sid), e(sid), e(task.get("title")), flag, e(task.get("status")), e(task.get("priority")),
            "".join("<span class='tag'>%s</span>" % e(t) for t in task.get("tags", [])), range_summary(task, rng), " ".join(actions)))
    body.append("</table>")
    return page(ctx.config.get("project_name", "Board"), "".join(body))


def render_task(ctx, task):
    sid = task["short_id"]
    rng = resolve_range(ctx.repo, task, ctx.main)
    branch_now = current_branch(ctx.repo)
    body = ["<p><a href='/'>all tasks</a> | <a href='%s/#/task/%s'>open in the Lattice dashboard</a></p>" % (e(ctx.dashboard), e(task["id"])),
            "<h1>%s %s</h1>" % (e(sid), e(task.get("title"))),
            "<p>%s, %s, %s %s</p>" % (e(task.get("status")), e(task.get("priority")), e(task.get("type")),
                                      "".join("<span class='tag'>%s</span>" % e(t) for t in task.get("tags", []))),
            tool_notes(ctx), notice(ctx, sid)]
    if needs_human(task):
        body.append("<p class='warn'>Needs human: %s</p>" % e(needs_human(task)))
    body.append("<pre>%s</pre>" % e(task.get("description") or "No description"))
    criteria = [c for c in task.get("acceptance_criteria", []) if not c.get("retired")]
    if criteria:
        body.append("<h2>Acceptance criteria</h2><ul>" + "".join("<li>%s</li>" % e(c.get("outcome")) for c in criteria) + "</ul>")
    body.append("<h2>Work</h2><p>%s</p>" % range_summary(task, rng))
    if rng["mode"] == "branch" and rng["branch"] != branch_now:
        body.append("<p class='warn'>The repo is on <code>%s</code>, this task's branch is <code>%s</code>. The exact-range review and the VS Code links use the task's branch.</p>" % (e(branch_now), e(rng["branch"])))
    actions = []
    if rng["base_sha"]:
        actions.append("<a href='%s'><button type='button'>VS Code multi-diff</button></a>" % e(vscode_uri(ctx.repo, rng["base"], rng["head"], sid + " " + task.get("title", ""))))
        if ctx.plannotator:
            actions.append(button(ctx, "/t/%s/plannotator" % sid, "Plannotator: exact range", {"base": rng["base"], "head": rng["head"]}))
            if rng["head_sha"] == rev(ctx.repo, "HEAD"):
                actions.append(button(ctx, "/t/%s/plannotator" % sid, "Plannotator: live tree from base", {"base": rng["base"], "live": "1"}, quiet=True))
    body.append("<p>" + " ".join(actions) + "</p>")
    if rng["commits"]:
        body.append("<table><tr><th>Commit</th><th>Subject</th><th>Date</th><th></th></tr>")
        for c in rng["commits"]:
            body.append("<tr><td><code>%s</code></td><td>%s</td><td>%s</td><td><a href='%s'>VS Code</a> %s</td></tr>" % (
                e(c["hash"][:12]), e(c["subject"]), e(c["date"]), e(vscode_uri(ctx.repo, c["hash"] + "^", c["hash"], c["subject"])),
                button(ctx, "/t/%s/plannotator" % sid, "Plannotator", {"base": c["hash"] + "^", "head": c["hash"]}, quiet=True) if ctx.plannotator else ""))
        body.append("</table>")
    if rng["base_sha"]:
        try:
            files = changed_files(ctx.repo, rng["base"], rng["head"])
        except RuntimeError as exc:
            files = []
            body.append("<p class='err'>%s</p>" % e(exc))
        body.append("<h2>Files (%d)</h2><table>" % len(files))
        for f in files:
            shown = f["path"] if f["old_path"] == f["path"] else f["old_path"] + " → " + f["path"]
            row = "<tr><td>%s</td><td><a href='vscode://file%s'>%s</a></td><td>" % (e(f["status"]), e(urllib.parse.quote(str(ctx.repo / f["path"]))), e(shown))
            if ctx.code:
                row += button(ctx, "/t/%s/filediff" % sid, "diff in VS Code",
                              {"path": f["path"], "old_path": f["old_path"], "status": f["status"], "base": rng["base"], "head": rng["head"]}, quiet=True)
            body.append(row + "</td></tr>")
        body.append("</table>")
    job = ctx.jobs.get(sid)
    if job:
        state = "running since " + time.strftime("%H:%M:%S", time.localtime(job.started)) if not job.done else "finished, exit %s, decision %s" % (job.rc, job.decision)
        body.append("<h2>Plannotator</h2><p>%s (%s). Log <code>%s</code></p>" % (e(state), e(job.what), e(job.err_path)))
        if job.error:
            body.append("<p class='err'>%s</p>" % e(job.error))
        if job.result_path:
            body.append("<p class='ok'>Recorded on %s as a comment with role review.</p><pre>%s</pre>" % (e(sid), e(job.result_path.read_text())))
            stale = stale_reason(ctx.repo, task, ctx.main, job.result_path)
            if stale:
                body.append("<p class='warn'>Cannot complete with this review: %s.</p>" % e(stale))
            else:
                body.append(button(ctx, "/t/%s/complete" % sid, "Mark done with this review", {"result": str(job.result_path)}))
        elif job.done and not job.error:
            body.append("<p class='muted'>Plannotator closed without a review (dismissed).</p>")
    body.append("<h2>Comments</h2>")
    for c in ctx.comments(sid)[-10:]:
        body.append("<p><b>%s</b> <span class='muted'>%s%s</span></p><pre>%s</pre>" % (
            e(c.get("author")), e(c.get("created_at")), " (" + e(c["role"]) + ")" if c.get("role") else "", e(c.get("body"))))
    body.append("<form method='post' action='/t/%s/comment' style='display:block'><input type='hidden' name='token' value='%s'>"
                "<textarea name='body' placeholder='Comment as %s'></textarea><br><input type='submit' value='Add comment'></form>" % (e(sid), ctx.token, e(ctx.actor)))
    body.append("<h2>Status</h2><p>")
    for to in ctx.config.get("workflow", {}).get("transitions", {}).get(task.get("status"), []):
        body.append(button(ctx, "/t/%s/status" % sid, "set " + to, {"to": to}, quiet=True))
    body.append("</p><form method='post' action='/t/%s/complete' style='display:block'><input type='hidden' name='token' value='%s'>"
                "<textarea name='review' placeholder='Review findings to record with lattice complete (your own words, not bound to a revision)'></textarea><br>"
                "<input type='submit' value='Mark done with this text'></form>" % (e(sid), ctx.token))
    return page(sid, "".join(body))


# --------------------------------------------------------------------------
# http
# --------------------------------------------------------------------------

def make_handler(ctx):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

        def send_page(self, data, status=200):
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def redirect(self, location):
            self.send_response(303)
            self.send_header("Location", location)
            self.end_headers()

        def do_GET(self):
            url = urllib.parse.urlsplit(self.path)
            parts = [p for p in url.path.split("/") if p]
            if not parts:
                return self.send_page(render_index(ctx))
            if parts[0] == "t" and len(parts) == 2:
                task = find_task(ctx.board, parts[1])
                if task:
                    return self.send_page(render_task(ctx, task))
            if parts[0] == "vscode":
                q = urllib.parse.parse_qs(url.query)
                return self.redirect(vscode_uri(ctx.repo, q.get("base", [""])[0], q.get("head", [WORKTREE])[0], q.get("title", [""])[0]))
            self.send_page(page("not found", "<p>not found</p>"), 404)

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            form = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(length).decode()).items()}
            if form.get("token") != ctx.token:
                return self.send_page(page("forbidden", "<p>bad token</p>"), 403)
            parts = [p for p in self.path.split("/") if p]
            if parts == ["unpushed", "plannotator"]:
                ctx.start_plannotator("unpushed", base=form.get("base") or None, live=True)
                return self.redirect("/")
            if len(parts) != 3 or parts[0] != "t":
                return self.send_page(page("not found", "<p>not found</p>"), 404)
            sid, action = parts[1], parts[2]
            task = find_task(ctx.board, sid)
            if not task:
                return self.send_page(page("not found", "<p>not found</p>"), 404)
            try:
                if action == "plannotator":
                    ctx.start_plannotator(sid, record_on=sid, base=form.get("base") or None, head=form.get("head") or None,
                                          live=form.get("live") == "1")
                elif action == "filediff":
                    ctx.code_diff(form["base"], form["head"], form["path"], form.get("old_path"), form.get("status", "M"))
                elif action == "comment" and form.get("body", "").strip():
                    path = ctx.state / ("%s-comment-%d.md" % (sid, int(time.time())))
                    path.write_text(form["body"].strip() + "\n")
                    ctx.board_write(sid, "comment", sid, "--file", str(path))
                elif action == "status":
                    ctx.board_write(sid, "status", sid, form["to"], "--no-auto-review")
                elif action == "complete":
                    result = form.get("result")
                    if result:
                        stale = stale_reason(ctx.repo, task, ctx.main, result)
                        if stale:
                            ctx.notices[sid] = ("err", "not completed: " + stale)
                            return self.redirect("/t/" + sid)
                    else:
                        result = str(ctx.state / ("%s-review-%d.md" % (sid, int(time.time()))))
                        Path(result).write_text(form.get("review", "").strip() + "\n")
                    ctx.board_write(sid, "complete", sid, "--review-file", result)
            except (RuntimeError, OSError) as exc:
                ctx.notices[sid] = ("err", str(exc))
            self.redirect("/t/" + sid)

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--board", default=".", help="directory holding .lattice (default: cwd)")
    parser.add_argument("--repo", help="git repository to read commits from (default: the board directory)")
    parser.add_argument("--port", type=int, default=8798)
    parser.add_argument("--main", default="main", help="integration branch name")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--actor", default="human:" + os.environ.get("USER", "owner"), help="actor recorded on writes")
    parser.add_argument("--dashboard-url", help="Lattice dashboard URL (default: 127.0.0.1 and the board's dashboard_port)")
    parser.add_argument("--state", help="where review output and logs are kept")
    parser.add_argument("--with-dashboard", action="store_true", help="also start lattice dashboard on the board's port")
    args = parser.parse_args(argv)
    ctx = Context(args)
    if not ctx.lattice:
        sys.exit("lattice is not on PATH")
    dashboard = None
    if args.with_dashboard:
        env = dict(os.environ, LATTICE_NO_UPDATE_CHECK="1")
        dashboard = subprocess.Popen([ctx.lattice, "dashboard", "--port", str(ctx.config.get("dashboard_port", 8799))], cwd=ctx.board, env=env)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(ctx))
    print("review launcher at http://127.0.0.1:%d (board %s, actor %s)" % (args.port, ctx.board, ctx.actor))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if dashboard:
            dashboard.terminate()


if __name__ == "__main__":
    main()
