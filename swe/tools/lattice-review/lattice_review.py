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
import datetime
import difflib
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
REVIEWED = "Reviewed: "
THREAD = "Thread: "
REVIEW_OF = "From review "
FOLLOW_UP = "Follow-up from review "
LINES = re.compile(r"^lines? (\d+)(?:-(\d+))? \((new|old)\)$")
ANCHOR = re.compile(r"^(.*), (lines? \d+(?:-\d+)?(?: \((?:new|old)\))?|whole file|whole document) at (?:plan )?[0-9a-f]+$")
PLAN = "Plan: "
PLAN_DECISION = re.compile(r"^Plannotator plan (approved|annotated) \(")
PLAN_NOTE = re.compile(r"^## \d+\. (.*)$")
RESOLVED = "resolved"
REVISION = re.compile(r"^([0-9a-f]{7,40})\.\.([0-9a-f]{7,40})( live| dirty)?$")
# "Owner approved" is a yes given in the terminal through owner_review.py.
DECISION = re.compile(r"^(?:Plannotator|Owner) (approved|annotated) \(")
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
MAX_BODY = 1_048_576
# The task side panel opens at 60% of the window instead of Lattice's 30rem,
# on an opaque background (the themes' surface is translucent, so the board
# showed through). Each section is a card one step lighter than the panel,
# with a quiet hue by kind (a data-lr attribute set from its heading or
# content): blue description, green criteria, accent review, violet plans,
# cyan comments, slate for the rest. State colours stay for state. Menus
# follow the theme (Lattice sets no color-scheme, so native selects and their
# option lists were drawn light on every theme). The dashboard's own Show
# Plan button is hidden while the review section, which carries the plan's
# buttons, is in the panel; its left edge drags to resize, the width is kept in
# localStorage, and a double-click on the edge resets it. The edge sits outside the panel, so its
# clicks stop before the dashboard's click-outside-closes-the-panel listener.
PANEL = """<style>
.detail-panel{width:var(--lr-panel-w,60vw);max-width:96vw;background:linear-gradient(var(--surface),var(--surface)),var(--bg-base,#111)}
.dp-section,.detail-section{--lr-hue:#94a3b8;margin-top:.75rem;padding:.7rem .9rem .8rem;border:1px solid color-mix(in srgb,var(--lr-hue) 22%,transparent);border-left:3px solid color-mix(in srgb,var(--lr-hue) 70%,transparent);border-radius:10px;background:color-mix(in srgb,var(--lr-hue) 7%,var(--bg-base,#111))}
.dp-section h3,.detail-section h3{margin:0 0 .5rem;font-size:.78rem;letter-spacing:.06em;text-transform:uppercase;color:color-mix(in srgb,var(--lr-hue) 60%,var(--text-primary))}
[data-lr=description]{--lr-hue:#7aa2f7}[data-lr=criteria]{--lr-hue:#4ade80}[data-lr=review]{--lr-hue:var(--accent-primary,#2b6cb0)}
[data-lr=plans]{--lr-hue:#c084fc}[data-lr=comments]{--lr-hue:#38bdf8}[data-lr=history]{--lr-hue:#2dd4bf}
.dp-comment,.comment-item{background:color-mix(in srgb,var(--lr-hue,#38bdf8) 8%,transparent);border-color:color-mix(in srgb,var(--lr-hue,#38bdf8) 20%,transparent)}
@keyframes lrflash{from{box-shadow:0 0 0 3px var(--accent-primary,#2b6cb0)}to{box-shadow:0 0 0 3px transparent}}.lr-flash{animation:lrflash 1.6s ease-out}
:root{color-scheme:dark}[data-theme="linear"]{color-scheme:light}
select{background-color:color-mix(in srgb,var(--text-primary) 8%,var(--bg-base,#111));color:var(--text-primary);border:1px solid color-mix(in srgb,var(--text-primary) 24%,transparent);border-radius:var(--radius-sm,4px)}
select option{background-color:var(--bg-base,#111);color:var(--text-primary)}
.lr-resize{display:none;position:fixed;top:var(--nav-h,52px);bottom:0;right:calc(var(--lr-panel-w,60vw) - 4px);width:8px;cursor:col-resize;z-index:101}
.detail-panel.open+.lr-resize{display:block}
.lr-resize:hover,.lr-resize.dragging{background:var(--accent-primary,#2b6cb0);opacity:.5}
body.lr-dragging{cursor:col-resize;user-select:none}body.lr-dragging iframe{pointer-events:none}
.lr-fold{display:none!important}.lr-clamp{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:6;overflow:hidden}
.lr-earlier{display:block;width:100%;margin:0 0 .375rem;padding:.3rem;border:1px dashed color-mix(in srgb,var(--lr-hue,#38bdf8) 40%,transparent);border-radius:var(--radius-sm,4px);background:none;color:var(--text-muted);font:inherit;font-size:.78rem;cursor:pointer}
.lr-more{display:block;background:none;border:0;padding:.15rem 0 0;color:var(--accent-primary,#2b6cb0);font:inherit;font-size:.78rem;cursor:pointer}
.lr-earlier:hover,.lr-more:hover{color:var(--text-primary)}
</style><script>(function(){
var KEY="lattice-review.panel-width",MIN=360,root=document.documentElement;
function clamp(w){return Math.round(Math.max(MIN,Math.min(w,root.clientWidth*0.96)))}
function wanted(){var w=parseInt(localStorage.getItem(KEY)||"",10);return w>0?w:root.clientWidth*0.6}
function apply(w){root.style.setProperty("--lr-panel-w",clamp(w)+"px")}
function fit(f){f.style.height="1px";var h=f.contentDocument.documentElement.scrollHeight+4;
f.style.height=(f.classList.contains("history-frame")?Math.min(h,Math.round(innerHeight*0.6)):h)+"px"}
function refit(){document.querySelectorAll("iframe.review-frame").forEach(fit)}
var KEEP=3,shown={},opened={};
function meta(c){var m=c.querySelector(".dp-comment-meta,.comment-meta");return m?m.textContent:""}
function stamp(g){var m=meta(g[0]).match(/\\d{4}-\\d\\d-\\d\\dT[\\d:]+/);return m?m[0]:""}
function clip(c){var body=c.querySelector(".comment-body")||c.lastElementChild;if(!body||body.className.indexOf("meta")>=0)return;
body.classList.add("lr-clamp");if(body.scrollHeight<=body.clientHeight+2){body.classList.remove("lr-clamp");return}
var k=meta(c),b=document.createElement("button");b.type="button";b.className="lr-more";
function setMore(open){opened[k]=open;body.classList.toggle("lr-clamp",!open);b.textContent=open?"Less":"More"}
b.onclick=function(){setMore(!opened[k])};body.insertAdjacentElement("afterend",b);setMore(!!opened[k])}
function fold(s){if(s.dataset.lrFold)return;s.dataset.lrFold="1";
var items=[].slice.call(s.querySelectorAll(".dp-comment,.comment-item")),groups=[];
items.forEach(function(c){clip(c);if(groups.length&&c.style.marginLeft)groups[groups.length-1].push(c);else groups.push([c])});
if(groups.length<=KEEP)return;
var newestFirst=stamp(groups[0])>stamp(groups[groups.length-1]);
var old=[].concat.apply([],newestFirst?groups.slice(KEEP):groups.slice(0,-KEEP)),k=meta(items[0]),b=document.createElement("button");b.type="button";b.className="lr-earlier";
function setEarlier(open){shown[k]=open;old.forEach(function(c){c.classList.toggle("lr-fold",!open)});
b.textContent=open?"Hide earlier comments":"Show "+old.length+" earlier comment"+(old.length>1?"s":"")}
b.onclick=function(){setEarlier(!shown[k])};old[0].parentNode.insertBefore(b,old[0]);setEarlier(!!shown[k])}
apply(wanted());
window.addEventListener("resize",function(){apply(wanted())});
var KINDS={description:"description",acceptance:"criteria",plan:"plans",plans:"plans",comments:"comments",history:"history"};
function tag(){document.querySelectorAll(".dp-section,.detail-section").forEach(function(s){
var h=s.querySelector("h3"),k=s.querySelector("iframe.review-frame:not(.history-frame)")?"review":s.querySelector("#dp-comment-text,.comment-item,.dp-comment")?"comments":
KINDS[((h&&h.textContent)||"").trim().split(/\\s+/)[0].toLowerCase()];if(k&&s.dataset.lr!==k)s.dataset.lr=k;
if(k==="comments")fold(s);
if(k==="plans"&&s.parentNode&&s.parentNode.querySelector("iframe.review-frame")){
s.querySelectorAll("button[onclick*='openPlans(']").forEach(function(b){b.hidden=true});
s.hidden=!s.querySelector("button:not([hidden])")}
var rf=k==="history"&&s.parentNode&&s.parentNode.querySelector("iframe.review-frame:not(.history-frame)");
if(rf&&!s.querySelector("iframe.history-frame")){var h3=s.querySelector("h3");s.textContent="";if(h3)s.appendChild(h3);
var hf=document.createElement("iframe");hf.className="review-frame history-frame";hf.src=rf.getAttribute("src")+"/history";
hf.onload=function(){fit(hf)};s.appendChild(hf)}})}
document.addEventListener("DOMContentLoaded",function(){
tag();new MutationObserver(tag).observe(document.body,{childList:true,subtree:true});
var panel=document.getElementById("detail-panel");if(!panel)return;
var edge=document.createElement("div");edge.className="lr-resize";edge.title="Drag to resize; double-click to reset";
panel.insertAdjacentElement("afterend",edge);
edge.addEventListener("click",function(e){e.stopPropagation()});
edge.addEventListener("dblclick",function(e){e.stopPropagation();localStorage.removeItem(KEY);apply(wanted());refit()});
edge.addEventListener("pointerdown",function(e){
e.preventDefault();edge.setPointerCapture(e.pointerId);document.body.classList.add("lr-dragging");edge.classList.add("dragging");
function move(ev){apply(root.clientWidth-ev.clientX)}
function up(ev){edge.removeEventListener("pointermove",move);edge.removeEventListener("pointerup",up);
document.body.classList.remove("lr-dragging");edge.classList.remove("dragging");
localStorage.setItem(KEY,String(clamp(root.clientWidth-ev.clientX)));refit()}
edge.addEventListener("pointermove",move);edge.addEventListener("pointerup",up)})})})();</script>"""
HOOK = "<script>window.LATTICE_REVIEW_URL=%s</script>" % json.dumps(REVIEW_PATH) + PANEL
INSTALL_HINT = ("Install Plannotator by downloading its installer, reading it, then running it: "
                "<code>curl -fsSLo plannotator-install.sh https://plannotator.ai/install.sh</code>, "
                "<code>less plannotator-install.sh</code>, <code>bash plannotator-install.sh --minimal</code>. "
                "Then restart this server.")


# --------------------------------------------------------------------------
# git and board reads (pure functions, covered by the tests)
# --------------------------------------------------------------------------

# A repository's own config can name programs that git runs during ordinary
# reads. Sessions can write any repository's config, and this server runs as the
# owner outside the agent sandbox. So every git call here switches those programs
# off when git runs, not only beforehand: the fsmonitor, hooks, optional index
# writes and the external diff through the environment, and diff drivers and text
# converters with --no-ext-diff and --no-textconv. Git cannot switch off a
# filter's clean program, which runs when git reads a working copy, so this
# server never reads one: it reviews commits only. Plannotator is only ever given
# a patch, so it runs no git of its own. A repository whose config names a diff
# or filter program is also refused before each call.
SAFE_GIT = {"GIT_CONFIG_COUNT": "4", "GIT_CONFIG_KEY_0": "core.fsmonitor", "GIT_CONFIG_VALUE_0": "false",
            "GIT_CONFIG_KEY_1": "core.hooksPath", "GIT_CONFIG_VALUE_1": "/dev/null",
            "GIT_CONFIG_KEY_2": "diff.external", "GIT_CONFIG_VALUE_2": "",
            "GIT_CONFIG_KEY_3": "log.showSignature", "GIT_CONFIG_VALUE_3": "false",
            "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "",
            "GIT_TERMINAL_PROMPT": "0"}
RUNS_PROGRAM = re.compile(r"^(?:local|worktree)\t(diff\.external|diff\..+\.(?:command|textconv)|"
                          r"filter\..+\.(?:clean|smudge|process))=", re.IGNORECASE | re.MULTILINE)
NO_DIFF_PROGRAMS = ("diff", "diff-tree", "log", "show")


def git_env(repo):
    env = dict(os.environ, **SAFE_GIT)
    env.pop("GIT_CONFIG_PARAMETERS", None)
    scoped = subprocess.run(["git", "-C", str(repo), "config", "--list", "--show-scope", "--includes"],
                            capture_output=True, text=True, env=env)
    if scoped.returncode:
        raise RuntimeError(scoped.stderr.strip() or "cannot read repository config")
    hit = RUNS_PROGRAM.search(scoped.stdout)
    if hit:
        raise RuntimeError("git refused in %s: the repository's own config runs a program (%s)" % (repo, hit.group(1)))
    return env


def git_result(repo, args, *, binary=False, timeout=None):
    if args and args[0] in NO_DIFF_PROGRAMS:
        args = (args[0], "--no-ext-diff", "--no-textconv") + tuple(args[1:])
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=not binary, env=git_env(repo), timeout=timeout)


def run_git(repo, *args, check=True, binary=False):
    result = git_result(repo, args, binary=binary)
    err = result.stderr if not binary else result.stderr.decode(errors="replace")
    if result.returncode and (check or (args[0] == "rev-parse" and err.strip())):
        raise RuntimeError(err.strip() or "git " + " ".join(args) + " failed")
    return result.stdout


# These are the inspected Lattice 0.2.1 modules, with and without our dashboard
# patch. Recheck their Git call paths before accepting a different version.
DASHBOARD_GIT_SOURCES = {
    "server": {"a89969900fbba13c653ae0de2c4773a938dde708b7365cecccab8cd50024093b",
               "9997fd6df2d7594cdf970fe495730a31305fbda0c88a69aea564d9f77a5937d5"},
    "git_reader": {"fcde975b3f9557a532d855c482d37ae62c3a978e096f89e62c1ff44003fa9afc"},
}


def protect_dashboard_git(dashboard, reader):
    for name, module in (("server", dashboard), ("git_reader", reader)):
        digest = hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
        if digest not in DASHBOARD_GIT_SOURCES[name]:
            raise RuntimeError("unsupported Lattice dashboard %s: review its Git paths before starting" % name)

    def protected(args, cwd, *, timeout=reader.GIT_COMMAND_TIMEOUT):
        result = git_result(cwd, args, timeout=timeout)
        if result.returncode and tuple(args) not in (("rev-parse", "--show-toplevel"),
                                                     ("remote", "get-url", "origin")):
            raise RuntimeError(result.stderr.strip() or "dashboard Git read failed")
        return result

    reader._run_git = protected
    reader.invalidate_cache()


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


def task_comments(lattice, board, short_id):
    """The task's comments as the lattice CLI gives them, or none when it fails."""
    env = dict(os.environ, LATTICE_NO_UPDATE_CHECK="1", LATTICE_ROOT=str(board))
    result = subprocess.run([lattice, "comments", short_id, "--json"], cwd=board, env=env, capture_output=True, text=True)
    try:
        return json.loads(result.stdout).get("data", []) if result.returncode == 0 else []
    except json.JSONDecodeError:
        return []


def log_commits(repo, *args):
    out = run_git(repo, "log", "--reverse", "--format=%H%x1f%s%x1f%cs", *args)
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


def carried_tasks(repo, base, head, short_ids):
    """Which of the tasks have a commit of their own, by its Task trailer, in base..head."""
    named = run_git(repo, "log", "--format=%(trailers:key=Task,valueonly,separator=%x2C)", base + ".." + head)
    found = {part.strip() for line in named.splitlines() for part in line.split(",")}
    return [sid for sid in short_ids if sid in found]


def resolve_range(repo, task, main):
    """Where a task's work lives: its linked branch, or its trailer commits.

    base and head are refs for display; base_sha and head_sha are the
    immutable commit IDs a review is bound to. A linked branch with no
    commits of its own is no work yet; empty_branch names it."""
    links = [link["branch"] for link in task.get("branch_links", [])]
    empty_branch = None
    for branch in links:
        head_sha = rev(repo, branch)
        if head_sha:
            base = run_git(repo, "merge-base", main, branch).strip()
            commits = log_commits(repo, base + ".." + branch)
            if commits:
                return {"mode": "branch", "branch": branch, "base": base, "head": branch, "base_sha": base,
                        "head_sha": head_sha, "commits": commits, "contiguous": True}
            empty_branch = empty_branch or branch
    commits = task_commits(repo, task["short_id"], ["HEAD", main] + links)
    if not commits:
        return {"mode": "none", "base": None, "head": None, "base_sha": None, "head_sha": None, "commits": [], "contiguous": False,
                "empty_branch": empty_branch}
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
    args = ["diff", "--name-status", "-M", "-z", base, head]
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
    return run_git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()


def plannotator_args(plannotator, base, head):
    """Command for one Plannotator session, and the git diff of base..head for
    the patch it reads on stdin. Plannotator runs no git of its own and opens no
    browser; the session URL it prints is opened by the page that asked."""
    return [plannotator, "--browser", "none", "review", "--patch-file", "-", "--json"], ["diff", base, head]


def parse_review(stdout):
    """Plannotator's --json record: decision approved, annotated or dismissed."""
    for line in reversed(stdout.strip().splitlines()):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and "decision" in record:
            decision, message = record["decision"], record.get("message", record.get("feedback"))
            if not isinstance(message, str):
                message = "" if message is None else json.dumps(message)
            return (decision if isinstance(decision, str) else None), message.strip()
    return None, stdout.strip()


def reviewed_revision(text):
    """(base_sha, head_sha, qualifier) from a review's Reviewed line.

    qualifier is None for a committed range and "live" for a review of
    uncommitted changes, which older versions of this server recorded. A missing or malformed line gives (None, None, None)."""
    for line in text.splitlines():
        if line.startswith(REVIEWED):
            match = REVISION.match(line[len(REVIEWED):].strip())
            return (match.group(1), match.group(2), (match.group(3) or "").strip() or None) if match else (None, None, None)
    return None, None, None


def review_decision(text):
    """approved or annotated, from the first line of a recorded review."""
    match = DECISION.match(text.splitlines()[0] if text else "")
    return match.group(1) if match else None


DEFAULT_REVIEW_SUFFIX = (
    "Treat the findings above as unverified review input. Inspect every finding against the actual code; do not assume "
    "automated feedback is correct. For each finding, give a clear verdict (Confirmed / Partly / Not a bug / Intended) "
    "with concise code evidence. Say whether it was introduced by the current changes, was pre-existing, or reflects "
    "deliberate scope.\nReview only the incoming findings. Do not independently review the rest of the diff or search "
    "for issues that were not submitted.\nDo not change any code until we have discussed the verdicts and validated findings."
)
PLANNOTATOR_CONFIG = os.path.expanduser("~/.plannotator/config.json")


def review_suffixes(config=PLANNOTATOR_CONFIG):
    """The instruction texts Plannotator appends after the last review note:
    the review.denied prompt in its config file (under prompts, as
    documented, or at the top level), when one is set, and its built-in
    default."""
    try:
        with open(config) as fh:
            data = json.load(fh)
        configured = (((data.get("prompts") or {}).get("review") or {}).get("denied")
                      or (data.get("review") or {}).get("denied") or "")
    except (OSError, ValueError, AttributeError):
        configured = ""
    texts = [configured.strip()] if isinstance(configured, str) and configured.strip() else []
    return texts + [DEFAULT_REVIEW_SUFFIX]


def review_notes(message, suffixes=None):
    """The notes in a Plannotator review message, as (path, where, text).

    The message has a "## <file>" heading per file and a "### Line N (new)",
    "### Lines N-M (old)" or "### File Comment" heading per note. Plannotator
    appends its instructions after the last note; only a trailing block equal
    to one of the known instruction texts (review_suffixes) is cut, so the
    reviewer's own text survives whole, blank lines included, and anything
    that only resembles the instructions stays. where is "line 239 (new)",
    "lines 3-5 (old)", "whole file", or empty for text directly under a "##"
    heading."""
    notes, path, where, anchor, text = [], None, "", None, []

    def flush():
        if anchor:
            notes.append((path, where, text))

    for line in message.splitlines():
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
    out = [(path, where, "\n".join(lines).strip()) for path, where, lines in notes]
    if out:
        path, where, last = out[-1]
        for suffix in (suffixes if suffixes is not None else review_suffixes()):
            if suffix and last.endswith(suffix):
                out[-1] = (path, where, last[:-len(suffix)].strip())
                break
    return [(path, where, text) for path, where, text in out if text]


def plan_notes(feedback):
    """The notes in Plannotator's annotate feedback on a plan, as (path,
    where, text, quote). Each note is a "## N. <heading>" section: "General
    feedback about the file", or "(line 10) Feedback on: "<selected text>"",
    or another kind such as a removal, followed by the comment quoted with
    ">". The feedback ends at a "---" line."""
    notes, heading, body = [], None, []

    def flush():
        if heading is None:
            return
        text = "\n".join(line[2:] if line.startswith("> ") else line.lstrip(">") for line in body).strip()
        place = re.match(r"^\((lines? [\d-]+)\) (.*)$", heading)
        if place:
            where, kind = place.group(1), place.group(2)
            selected = re.match(r'^Feedback on: "(.*)"$', kind)
            quote = ["> " + selected.group(1)] if selected else []
            if not selected:
                text = kind + ("\n" + text if text else "")
        else:
            where, quote = "whole document", []
            if heading != "General feedback about the file":
                text = heading + ("\n" + text if text else "")
        if text:
            notes.append(("plan", where, text, quote))

    for line in feedback.splitlines():
        match = PLAN_NOTE.match(line)
        if match:
            flush()
            heading, body = match.group(1).strip(), []
        elif line.strip() == "---":
            flush()
            heading, body = None, []
        elif heading is not None:
            body.append(line)
    flush()
    return notes


def plan_status(comments, plan_text):
    """The state of a task's plan: not reviewed, changes requested, approved,
    or changed since it was approved (the approval names the plan's sha256).
    A deleted latest review withdraws what came before it. Only plan reviews
    this server recorded for a person count: an agent's comment with the same
    role is not a review."""
    reviews = [(c.get("created_at") or "", i, c) for i, c in enumerate(comments)
               if c.get("role") == "plan-review" and (c.get("author") or "").startswith("human:")
               and (c.get("deleted") or PLAN_DECISION.match(c.get("body") or ""))]
    if not reviews:
        return "not reviewed yet"
    latest = max(reviews)[2]
    if latest.get("deleted"):
        return "the latest plan review was deleted; review it again"
    body = latest.get("body") or ""
    match = PLAN_DECISION.match(body)
    if not match or match.group(1) != "approved":
        return "changes requested"
    recorded = next((line[len(PLAN):].strip() for line in body.splitlines() if line.startswith(PLAN)), None)
    current = hashlib.sha256(plan_text.encode()).hexdigest()
    return "approved" if recorded == current else "changed since it was approved; review it again"


def waits_for_plan_approval(task):
    """True when the task's needs_human flag asks the owner to approve its plan."""
    reason = ((task.get("needs_human") or {}).get("reason") or "").lower()
    return "approv" in reason and "plan" in reason


RELATIONS = {"subtask_of": "made this a subtask of", "blocks": "marked this as blocking (it must finish first)",
             "blocked_by": "marked this as waiting on", "depends_on": "marked this as waiting on",
             "related_to": "linked this as related to", "duplicate_of": "marked this a duplicate of",
             "spawned_by": "noted this came out of", "supersedes": "marked this as replacing"}
# Which way each link points, read from the task that holds it: waits (this
# task waits on the target), holds (the target waits on this task), parent,
# related. Read from the other end, waits and holds swap and parent becomes
# child.
DIRECTION = {"depends_on": "waits", "blocked_by": "waits", "blocks": "holds", "subtask_of": "parent",
             "related_to": "related", "duplicate_of": "related", "spawned_by": "related", "supersedes": "related"}
FLIP = {"waits": "holds", "holds": "waits", "parent": "child", "related": "related"}


def dependencies(task, tasks):
    """The task's links in both directions as (kind, other task, note): kind is
    waits, holds, parent, child or related."""
    out = []
    by_id = {t["id"]: t for t in tasks}
    for rel in task.get("relationships_out") or []:
        other = by_id.get(rel.get("target_task_id"))
        if other:
            out.append((DIRECTION.get(rel.get("type"), "related"), other, rel.get("note")))
    for other in tasks:
        for rel in other.get("relationships_out") or []:
            if rel.get("target_task_id") == task["id"]:
                out.append((FLIP[DIRECTION.get(rel.get("type"), "related")], other, rel.get("note")))
    return out


def when(ts):
    """A timestamp from an event (UTC, Z) or git (with offset) as an aware datetime."""
    return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def history(events, comments, commits, short_ids):
    """What happened to a task, newest first, one entry per event that says
    what changed, with the reason given and any on-behalf-of actor, plus the
    task's commits. Entries: ts, raw_ts, actor, kind (the event type), cat
    (change or comment, for the filters), text, why, behalf, link, details;
    link is (kind, target) with kind task, thread, plan, code, commit,
    comment or criterion."""
    by_id = {}
    for c in comments:
        by_id[c.get("id")] = c
        for r in c.get("replies") or []:
            by_id[r.get("id")] = r
    anchors = {t["root"].get("id"): t["anchor"] for t in review_threads(comments)}
    out = []
    for ev in events:
        d, kind = ev.get("data") or {}, ev.get("type")
        text, link, details = None, None, None
        if kind == "task_created":
            what = " ".join(w for w in (d.get("priority"), d.get("type")) if w)
            text = "created the task" + (" as a %s" % what if what else "") + (
                " in %s" % d["status"].replace("_", " ") if d.get("status") else "")
        elif kind == "status_changed":
            text = "moved it from %s to %s" % ((d.get("from") or "?").replace("_", " "), (d.get("to") or "?").replace("_", " "))
        elif kind == "assignment_changed":
            text = "assigned it to %s" % d["to"] if d.get("to") else "unassigned it"
        elif kind == "needs_human_flagged":
            text = "asked the owner: %s" % (d.get("reason") or "")
        elif kind == "needs_human_cleared":
            text = "cleared the owner question" + (": " + d["note"] if d.get("note") else "")
        elif kind == "field_updated" and d.get("field") == "description":
            text = "edited the description"
            details = "\n".join(line for line in difflib.unified_diff(
                (d.get("from") or "").splitlines(), (d.get("to") or "").splitlines(), lineterm="", n=0) if line[:3] not in ("---", "+++", "@@ "))
        elif kind == "field_updated":
            text = "changed %s from %s to %s" % (d.get("field"), d.get("from") or "nothing", d.get("to") or "nothing")
        elif kind == "acceptance_criterion_added":
            text = "added %s: %s" % (d.get("criterion_id"), d.get("outcome") or "")
            link = ("criterion", d.get("criterion_id"))
        elif kind == "acceptance_criterion_edited":
            text = "revised %s%s" % (d.get("criterion_id"), ": " + d["outcome"] if d.get("outcome") else "")
            link = ("criterion", d.get("criterion_id"))
        elif kind == "acceptance_criterion_retired":
            text = "retired %s" % d.get("criterion_id")
        elif kind in ("relationship_added", "relationship_removed"):
            target = short_ids.get(d.get("target_task_id"), (d.get("target_task_id") or "")[:12])
            verb = RELATIONS.get(d.get("type"), "linked it (%s) to" % d.get("type"))
            text = ("%s %s" % (verb, target)) if kind == "relationship_added" else "removed the %s link to %s" % ((d.get("type") or "").replace("_", " "), target)
            link = ("task", target)
        elif kind in ("branch_linked", "branch_unlinked"):
            text = "%s branch %s" % ("linked" if kind == "branch_linked" else "unlinked", d.get("branch") or d.get("branch_name"))
            link = ("code", None) if kind == "branch_linked" else None
        elif kind == "artifact_attached":
            text = "attached %s" % (d.get("title") or d.get("artifact_id") or "a file")
        elif kind in ("reaction_added", "reaction_removed") and d.get("emoji") == RESOLVED and d.get("comment_id") in anchors:
            text = "%s the thread on %s" % ("resolved" if kind == "reaction_added" else "reopened", anchors[d["comment_id"]])
            link = ("thread", d["comment_id"])
        elif kind == "comment_added":
            body, role = d.get("body") or "", d.get("role")
            first = body.splitlines()[0] if body else ""
            covered = re.match(r"^Plannotator (?:plan )?\w+ \((.*)\), \S+$", first)
            if role == "review" and review_decision(body):
                text = "%s the code review%s" % ("approved" if review_decision(body) == "approved" else "requested changes in",
                                                 " of " + covered.group(1) if covered else "")
                link = ("code", None)
            elif role == "plan-review" and PLAN_DECISION.match(body):
                text = "%s the plan" % ("approved" if PLAN_DECISION.match(body).group(1) == "approved" else "requested changes on")
                link = ("plan", None)
            elif body.startswith(THREAD):
                text = "opened a thread on %s" % first[len(THREAD):].strip()
                link = ("thread", ev.get("id"))
            elif d.get("parent_id") in anchors:
                text = "replied in the thread on %s" % anchors[d["parent_id"]]
                link = ("thread", d["parent_id"])
            elif body.strip():
                text = "commented: %s" % excerpt(body)
                link = ("comment", (ev.get("actor") or "", ev.get("ts") or ""))
        elif kind == "comment_deleted" and d.get("comment_id") in by_id:
            gone = by_id[d["comment_id"]]
            role = {"review": "code review", "plan-review": "plan review"}.get(gone.get("role"), "comment")
            text = "deleted a %s by %s: %s" % (role, gone.get("author") or "someone", excerpt(gone.get("body") or ""))
        elif kind in ("task_archived", "task_unarchived"):
            text = "archived the task" if kind == "task_archived" else "restored the task from the archive"
        if text:
            out.append(entry(ev, kind, "comment" if kind in ("comment_added", "comment_deleted") else "change", text, link, details))
    for c in commits:
        out.append({"ts": when(c["when"]), "raw_ts": c["when"], "actor": c["author"], "kind": "commit", "cat": "change",
                    "text": "committed %s %s" % (c["hash"][:12], c["subject"]), "why": None, "behalf": None,
                    "link": ("commit", c["hash"]), "details": None})
    return sorted(out, key=lambda item: item["ts"], reverse=True)


def entry(ev, kind, cat, text, link=None, details=None):
    prov = ev.get("provenance") or {}
    return {"ts": when(ev["ts"]), "raw_ts": ev["ts"], "actor": ev.get("actor") or "", "kind": kind, "cat": cat, "text": text,
            "why": prov.get("reason"), "behalf": prov.get("on_behalf_of"), "link": link, "details": details}


def excerpt(body, size=140):
    flat = " ".join(body.split())
    return flat if len(flat) <= size else flat[:size - 3] + "..."


# What another task's link to this one means, read from this task.
INCOMING = {"depends_on": "%s now waits on this task", "blocked_by": "%s now waits on this task",
            "blocks": "%s now blocks this task (it must finish first)", "subtask_of": "%s became a subtask of this task"}


def cross_references(task, tasks, events_of):
    """What other tasks did about this one, like GitHub's cross-referenced
    events: links they made to it (Lattice keeps a link only on the task that
    made it) and their comments that mention its ID."""
    mention = re.compile(r"(?<![A-Za-z0-9-])%s(?!\d)" % re.escape(task["short_id"]))
    out = []
    for other in tasks:
        if other["id"] == task["id"]:
            continue
        for ev in events_of(other["id"]):
            d, kind = ev.get("data") or {}, ev.get("type")
            if kind == "relationship_added" and d.get("target_task_id") == task["id"]:
                text = INCOMING.get(d.get("type"), "%s linked itself to this task (" + (d.get("type") or "").replace("_", " ") + ")")
                out.append(entry(ev, "incoming_link", "change", text % other["short_id"], ("task", other["short_id"])))
            elif kind == "relationship_removed" and d.get("target_task_id") == task["id"]:
                text = "%s removed its %s link to this task" % (other["short_id"], (d.get("type") or "").replace("_", " "))
                out.append(entry(ev, "incoming_link", "change", text, ("task", other["short_id"])))
            elif kind == "comment_added" and mention.search(d.get("body") or ""):
                text = "mentioned this task in a comment on %s: %s" % (other["short_id"], excerpt(d["body"]))
                out.append(entry(ev, "mention", "comment", text, ("task", other["short_id"])))
    return out


def commit_mentions(repo, short_id, exclude, main=None):
    """Commits on any branch whose message mentions the task ID, other than
    the task's own (GitHub's referenced events). A commit that is not on the
    integration branch names the branch it sits on, so a candidate's commit is
    not read as landed work."""
    out = []
    log = run_git(repo, "log", "--all", "-E", "--grep=%s([^0-9]|$)" % short_id, "--format=%H%x1f%cI%x1f%an%x1f%s")
    for line in log.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 4 and parts[0] not in exclude:
            on = ""
            if main and not contains(repo, main, parts[0]):
                branches = run_git(repo, "branch", "--contains", parts[0], "--format=%(refname:short)").split()
                on = " (on %s, not merged)" % branches[0] if branches else " (not merged)"
            out.append({"ts": when(parts[1]), "raw_ts": parts[1], "actor": parts[2], "kind": "referenced", "cat": "change",
                        "text": "mentioned this task in commit %s %s%s" % (parts[0][:12], parts[3], on), "why": None, "behalf": None,
                        "link": None, "details": None})
    return out


# Bookkeeping edits that fold when one actor makes three or more in a row,
# minutes apart, the way GitHub folds a run of label changes. Status changes,
# questions, reviews, comments, commits and anything done on someone's behalf
# always stay on their own line.
FOLDABLE = {"acceptance_criterion_added": ("added", "criterion", "criteria"),
            "acceptance_criterion_edited": ("revised", "criterion", "criteria"),
            "acceptance_criterion_retired": ("retired", "criterion", "criteria"),
            "field_updated": ("changed", "field", "fields"), "relationship_added": ("added", "link", "links"),
            "relationship_removed": ("removed", "link", "links"), "branch_linked": ("linked", "branch", "branches"),
            "branch_unlinked": ("unlinked", "branch", "branches"), "artifact_attached": ("attached", "file", "files"),
            "assignment_changed": ("changed", "assignee", "assignees")}


def fold_bursts(entries, gap=600):
    """entries newest first; runs of three or more foldable entries by one
    actor, each within gap seconds of the next, become one group entry."""
    out, run = [], []

    def close():
        if len(run) >= 3:
            counts = {}
            for item in run:
                counts[item["kind"]] = counts.get(item["kind"], 0) + 1
            parts = []
            for kind, n in sorted(counts.items(), key=lambda kv: -kv[1]):
                verb, one, many = FOLDABLE[kind]
                parts.append("%s %d %s" % (verb, n, one if n == 1 else many))
            out.append(dict(run[0], kind="group", text="made %d changes: %s" % (len(run), ", ".join(parts)),
                            why=None, link=None, details=None, group=list(run)))
        else:
            out.extend(run)
        run.clear()

    for item in entries:
        foldable = item["kind"] in FOLDABLE and not item["behalf"]
        if foldable and run and item["actor"] == run[-1]["actor"] and (run[-1]["ts"] - item["ts"]).total_seconds() <= gap:
            run.append(item)
            continue
        close()
        (run if foldable else out).append(item)
    close()
    return out


def commit_details(repo, hashes):
    """Author and commit time for each commit, for the history."""
    if not hashes:
        return []
    out = []
    for line in run_git(repo, "show", "-s", "--format=%H%x1f%cI%x1f%an%x1f%s", *hashes).splitlines():
        parts = line.split("\x1f")
        if len(parts) == 4:
            out.append({"hash": parts[0], "when": parts[1], "author": parts[2], "subject": parts[3]})
    return out


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
        items.append((c, anchor, note.strip(), thread_key(path, where, quote), path, where, quote))
    for c in live:
        if c.get("role") == "review" and c.get("id") not in split and review_decision(c.get("body") or "") == "annotated":
            notes = review_notes(c.get("body") or "")
            if len(notes) == 1:
                path, where, note = notes[0]
                items.append((c, note_anchor(path, where), note, thread_key(path, where, []), path, where, []))
            else:
                items.append((c, "; ".join(note_anchor(p, w) for p, w, _ in notes) or "whole review",
                              "\n\n".join("%s: %s" % (note_anchor(p, w), t) for p, w, t in notes), None, None, None, []))
    threads = []
    for root, anchor, note, key, path, where, quote in sorted(items, key=lambda item: item[0].get("created_at") or ""):
        messages = thread_messages(root)
        resolved = any(a.startswith("human:") for a in (root.get("reactions") or {}).get(RESOLVED, []))
        last = (messages[-1].get("author") or "") if messages else ""
        status = next((line[len("Status:"):].strip() for m in reversed(messages) if (m.get("author") or "").startswith("agent:")
                       for line in (m.get("body") or "").splitlines() if line.startswith("Status:")), None)
        state = "resolved" if resolved else "waiting on you" if last.startswith("agent:") else "waiting on the agent"
        threads.append({"root": root, "anchor": anchor, "note": note, "key": key, "path": path, "where": where, "quote": quote,
                        "messages": messages, "state": state, "status": status})
    return threads


def recorded_notes(comments):
    """How many notes of each review were recorded, by review id: threads
    opened from it plus follow-ups filed into older threads. Deleted ones
    count; what matters is that the recording finished."""
    counts = {}
    for c in comments:
        lines = (c.get("body") or "").split("\n")
        if lines[0].startswith(THREAD) and len(lines) > 1 and lines[1].startswith(REVIEW_OF):
            rid = lines[1][len(REVIEW_OF):].strip()
            counts[rid] = counts.get(rid, 0) + 1
        for reply in c.get("replies") or []:
            body = reply.get("body") or ""
            if body.startswith(FOLLOW_UP):
                rid = body[len(FOLLOW_UP):].split(",", 1)[0].strip()
                counts[rid] = counts.get(rid, 0) + 1
    return counts


def thread_for(threads, path, where, quote):
    """The open thread a note continues, or None: the one at the same place
    with the same quoted lines; else the only one with those quoted lines
    (the lines moved); else the only one at that place when the note or the
    thread has no quote. Anything ambiguous starts a new thread."""
    quoted = "\n".join(quote)
    same_place = [t for t in threads if t["path"] == path and t["where"] == where]
    if quote:
        candidates = [t for t in same_place if "\n".join(t["quote"]) == quoted]
        if not candidates:
            candidates = [t for t in threads if t["path"] == path and "\n".join(t["quote"]) == quoted]
        if not candidates:
            candidates = [t for t in same_place if not t["quote"]]
    else:
        candidates = same_place
    return candidates[0] if len(candidates) == 1 else None


def latest_review(comments):
    """The newest top-level comment with role review by a person that names a
    revision, or None. As with plan reviews, an agent's comment with the same
    role is not a review; the author label is a board record, not
    authentication, since anyone who can write the board files can write it.
    Deleted reviews count: a deleted one withdraws what came before it.
    Ties on the one-second timestamps go to the later event."""
    reviews = person_reviews(comments)
    return reviews[-1] if reviews else None


def person_reviews(comments):
    """The reviews latest_review chooses from, oldest first."""
    reviews = [(c.get("created_at") or "", i, c) for i, c in enumerate(comments)
               if c.get("role") == "review" and (c.get("author") or "").startswith("human:")
               and (c.get("deleted") or reviewed_revision(c.get("body") or "")[1])]
    return [c for _, _, c in sorted(reviews, key=lambda r: r[:2])]


def approved_commits(repo, comments):
    """Commit IDs inside the ranges a person approved since the last deleted
    review. A review of uncommitted changes approves no commits."""
    ranges = []
    for review in person_reviews(comments):
        base, head, qualifier = reviewed_revision(review.get("body") or "")
        if review.get("deleted"):
            ranges = []
        elif review_decision(review.get("body") or "") == "approved" and not qualifier:
            ranges.append((base, head))
    return {sha for base, head in ranges for sha in run_git(repo, "rev-list", base + ".." + head, check=False).split()}


def adds_nothing(repo, sha):
    """Whether a commit is a merge with nothing of its own: its files are
    exactly Git's automatic merge of its two parents, or every line comes from
    one of its parents (an empty combined diff). Two sides that change
    neighbouring lines give a combined diff without anyone writing a line."""
    parents = run_git(repo, "rev-list", "--parents", "-n", "1", sha).split()[1:]
    if len(parents) < 2:
        return False
    if len(parents) == 2:
        automatic = git_result(repo, ("merge-tree", "--write-tree", parents[0], parents[1]))
        if automatic.returncode == 0 and automatic.stdout.split()[:1] == [run_git(repo, "rev-parse", sha + "^{tree}").strip()]:
            return True
    return not run_git(repo, "diff-tree", "-p", "--cc", "--no-commit-id", sha).strip()


def stale_reason(repo, task, main, text, comments=()):
    """Why a recorded review does not cover the task's work now, or None when
    it does. With the task's comments, work that earlier approvals covered
    counts as reviewed, so merged history need not be one range; a merge that
    adds nothing of its own needs no approval."""
    base_sha, head_sha, qualifier = reviewed_revision(text)
    if not head_sha:
        return "the recorded review names no revision; review the whole range again"
    if qualifier:
        return ("your latest review was of uncommitted changes, which gives feedback but cannot complete a task. "
                "Once the work is committed with the trailer Task: %s, review the whole range" % task["short_id"])
    rng = resolve_range(repo, task, main)
    if (rng["base_sha"], rng["head_sha"]) == (base_sha, head_sha):
        return None
    approved = approved_commits(repo, comments)
    if rng["commits"] and all(c["hash"] in approved or adds_nothing(repo, c["hash"]) for c in rng["commits"]):
        return None
    if not rng["head_sha"]:
        return "the task has no single commit range now (its commits are not consecutive); review them one by one"
    if (rng["base_sha"], rng["head_sha"]) != (base_sha, head_sha):
        return "commits arrived after your review: it covered %s..%s and the work is now %s..%s. Review the whole range again" % (
            base_sha[:12], head_sha[:12], rng["base_sha"][:12], rng["head_sha"][:12])
    return None


def landing_block(repo, main, shas):
    """Why the task's current work has not landed yet, or None: every one of
    its commits must be in main and, when main has an upstream, pushed there."""
    def outside(ref):
        return run_git(repo, "rev-list", *shas, "--not", ref).strip()
    if outside(main):
        return "the approved commits are not merged into %s yet; merge them, push %s, then Mark done" % (main, main)
    upstream = rev(repo, main + "@{upstream}")
    if upstream and outside(upstream):
        return "%s is not pushed yet; push it, then Mark done" % main
    return None


def criteria_block(task, comments=()):
    """Why the task's open acceptance criteria are not all evidenced, or None.
    An install or deploy is written as a criterion, so its evidence is what
    lets the task close. A note linked to a criterion counts for it unless
    the newest such note opens with "Not met": saying a criterion is still
    open must not close it."""
    evidenced = {cid for ref in task.get("evidence_refs", []) for cid in ref.get("criterion_ids") or []}
    wanted = [c["id"] for c in task.get("acceptance_criteria", []) if not c.get("retired")]
    missing = [cid for cid in wanted if cid not in evidenced]
    if missing:
        return "no evidence is recorded yet for %s; record it on the task, then Mark done" % ", ".join(missing)
    notes = [n for c in comments for n in [c] + list(c.get("replies") or []) if not n.get("deleted")]
    newest = {}
    for n in sorted(notes, key=lambda n: n.get("created_at") or ""):
        for cid in n.get("criterion_ids") or []:
            newest[cid] = n.get("body") or ""
    open_ones = [cid for cid in wanted if newest.get(cid, "").lstrip().lower().startswith("not met")]
    if open_ones:
        return ("the newest evidence note for %s says it is not met; record what now meets it, then Mark done"
                % ", ".join(open_ones))
    return None


def review_block(repo, task, main, comments):
    """Why the owner's review does not cover the task's work now, or None: the
    latest bound review must approve exactly the commits the task has now, and
    every review thread must be resolved."""
    review = latest_review(comments)
    if not review:
        return "no Plannotator review is recorded for this task yet"
    if review.get("deleted"):
        return "the latest review was deleted; review the task again"
    if review_decision(review.get("body") or "") != "approved":
        return "your latest review requested changes; when they are answered, review again and approve"
    expected = len(review_notes(review.get("body") or ""))
    recorded = recorded_notes(comments).get(review.get("id"), 0)
    if recorded < expected:
        return "only %d of the %d notes in your latest review were recorded as threads; review again so every note is on the task" % (recorded, expected)
    unresolved = [t for t in review_threads(comments) if t["state"] != "resolved"]
    if unresolved:
        return "%d review thread(s) are not resolved; resolve them first" % len(unresolved)
    return stale_reason(repo, task, main, review["body"], comments)


def completion_block(repo, task, main, comments):
    """Why the task may not be completed now, or None: the owner's review must
    cover its work, the commits must be merged and pushed, and every open
    criterion must have evidence."""
    return (review_block(repo, task, main, comments)
            or landing_block(repo, main, [c["hash"] for c in resolve_range(repo, task, main)["commits"]])
            or criteria_block(task, comments))


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

def written(args):
    """What a finished board write did, in the owner's words."""
    if args[0] == "status":
        return {"done": "Marked done.", "in_progress": "Moved to in progress."}.get(args[2], "Status changed.")
    return {"react": "Thread resolved.", "unreact": "Thread reopened.", "comment": "Reply posted."}.get(
        args[0], args[0] + " " + " ".join(args[1:3]))


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
        self.actor = args.actor
        code = self.config.get("project_code", "board")
        self.state = Path(args.state or Path.home() / ".local" / "state" / "lattice-review" / code)
        self.state.mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_hex(16)
        self.jobs = {}
        self.notices = {}
        self.notice_at = {}
        self.drafts = {}
        self.runs = 0
        self.plannotator = shutil.which("plannotator")
        self.code = shutil.which("code")
        self.lattice = shutil.which("lattice")
        self.lock = threading.Lock()

    def lattice_cmd(self, *args):
        env = dict(os.environ, LATTICE_NO_UPDATE_CHECK="1", LATTICE_ROOT=str(self.board))
        result = subprocess.run([self.lattice, *args, "--actor", self.actor], cwd=self.board, env=env,
                                capture_output=True, text=True)
        return result.returncode, (result.stdout + result.stderr).strip()

    def board_write(self, key, *args):
        """A lattice write whose failure is shown on the page instead of being dropped."""
        rc, msg = self.lattice_cmd(*args)
        self.notices[key] = ("ok", written(args)) if rc == 0 else ("err", "lattice %s failed: %s" % (args[0], msg))
        return rc == 0

    def events(self, task_id):
        """The task's event log lines, oldest first."""
        path = self.board / ".lattice" / "events" / (task_id + ".jsonl")
        return [line for line in path.read_text().splitlines() if line.strip()] if path.is_file() else []

    def comments(self, short_id):
        return task_comments(self.lattice, self.board, short_id)

    def start_plannotator(self, key, record_on=None, base=None, head=None):
        """One Plannotator code review. The range is resolved to commit IDs once,
        and those IDs feed both the patch and the recorded Reviewed line. Only
        commits are reviewed: reading a working copy through git can run a filter
        program its config names, and git cannot switch that off."""
        base_sha, head_sha = rev(self.repo, base), rev(self.repo, head)
        if not (base_sha and head_sha):
            raise RuntimeError("the range %s..%s does not resolve to commits" % (base, head))
        if base_sha == head_sha:
            raise RuntimeError("the range %s..%s is empty: there are no commits to review" % (base, head))
        what = "patch %s..%s" % (base_sha[:12], head_sha[:12])
        revision = "%s..%s" % (base_sha, head_sha)
        args, patch_args = plannotator_args(self.plannotator, base_sha, head_sha)

        def source(side, path):
            """A file's text on the reviewed old or new side, or None."""
            if side == "old":
                return run_git(self.repo, "show", "%s:%s" % (base_sha, path), check=False) if base_sha else None
            return run_git(self.repo, "show", "%s:%s" % (head_sha, path), check=False)

        def record(job, decision, message, stamp):
            body = "Plannotator %s (%s), %s\n%s%s\n\n%s\n" % (decision, what, stamp, REVIEWED, revision, message)
            if self.post_review(job, record_on, body, "review"):
                notes = []
                for path, where, text in review_notes(message):
                    side = LINES.match(where)
                    notes.append((path, where, text, quoted_lines(source(side.group(3), path), where) if side else []))
                self.record_threads(record_on, body, notes, head_sha[:12], job)

        stdin = run_git(self.repo, *patch_args).encode()
        return self.session(key, what, args, self.repo, stdin, record if record_on else None)

    def start_plan_review(self, task):
        """A Plannotator annotate session on the task's plan file. The decision
        is bound to the plan as it was opened (its sha256). When the file is
        different by the end of the session, edits saved from Plannotator
        included, the approval names the opened version and the plan reads as
        changed since, so the owner reviews it once more. An approval clears
        the needs_human flag that asked for it, if that same flag is still set."""
        sid = task["short_id"]
        plan = self.board / ".lattice" / "plans" / (task["id"] + ".md")
        if not plan.is_file():
            raise RuntimeError("%s has no plan file yet" % sid)
        what = "plan of %s" % sid
        args = [self.plannotator, "--browser", "none", "annotate", str(plan), "--gate", "--json"]
        opened = hashlib.sha256(plan.read_bytes()).hexdigest()
        flag = task.get("needs_human")

        def record(job, decision, message, stamp):
            body = "Plannotator plan %s (%s), %s\n%s%s\n\n%s\n" % (decision, what, stamp, PLAN, opened, message)
            if not self.post_review(job, sid, body, "plan-review"):
                return
            self.record_threads(sid, body, plan_notes(message), "plan " + opened[:12], job)
            if decision != "approved" or job.error:
                return
            if hashlib.sha256(plan.read_bytes()).hexdigest() != opened:
                job.error = ("approved as opened (plan %s), but the plan file changed during the session; "
                             "review the plan again to approve what it says now" % opened[:12])
                return
            current = find_task(self.board, sid)
            if not (flag and current and waits_for_plan_approval(current)):
                return
            if current.get("needs_human") != flag:
                job.error = "the approval flag changed during the session, so it was left set"
                return
            rc, msg = self.lattice_cmd("needs-human", sid, "--clear", "--note", "Plan approved in Plannotator (plan %s)" % opened[:12])
            if rc != 0:
                job.error = "the plan approval was recorded but the needs_human flag was not cleared: " + msg

        return self.session(sid, what, args, self.board, None, record)

    def open_plan(self, task):
        """The task's plan in VS Code, scaffolded from the task the way the
        dashboard's own plan button does when there is none yet."""
        if not self.code:
            raise RuntimeError("the code command is not on PATH; start this server from a VS Code terminal")
        plan = self.board / ".lattice" / "plans" / (task["id"] + ".md")
        if not plan.is_file():
            from lattice.storage.operations import scaffold_plan
            scaffold_plan(self.board / ".lattice", task["id"], task.get("title", "Untitled"), task.get("short_id"), task.get("description"))
        self.code_open(plan)

    def post_review(self, job, sid, body, role):
        job.out_path.write_text(body)
        rc, msg = self.lattice_cmd("comment", sid, "--file", str(job.out_path), "--role", role)
        if rc != 0:
            job.error = "the review was not recorded on the task: " + msg
            return False
        job.result_path = job.out_path
        return True

    def session(self, key, what, args, cwd, stdin, record):
        """Run one Plannotator session in the background; one per task at a
        time. record(job, decision, message, stamp) is called for an approved or
        annotated decision; None records nothing."""
        env = dict(git_env(cwd), PLANNOTATOR_AI="disabled", PLANNOTATOR_SHARE="disabled")
        with self.lock:
            running = self.jobs.get(key)
            if running and not running.done:
                raise RuntimeError("a Plannotator session for %s is already open; finish or close it first" % key)
            self.runs += 1
            stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            name = "%s-%s-%d" % (key, stamp, self.runs)
            job = Job(key, what, self.state / (name + ".review.md"), self.state / (name + ".log"))
            self.jobs[key] = job
        out = open(job.out_path, "w")
        err = open(job.err_path, "w")
        try:
            job.proc = subprocess.Popen(args, cwd=cwd, env=env, stdout=out, stderr=err,
                                        stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL)
            if stdin is not None:
                job.proc.stdin.write(stdin)
                job.proc.stdin.close()
        except OSError as exc:
            job.error = str(exc)
            job.done = True
            out.close()
            err.close()
            return job

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
            elif decision == "dismissed" or not record:
                job.out_path.unlink(missing_ok=True)
            else:
                record(job, decision, message, stamp)

        def wait():
            try:
                finish()
            except Exception as exc:  # noqa: BLE001 - any failure must end the job visibly
                job.error = "the review result could not be handled: %r" % exc
            finally:
                job.done = True

        threading.Thread(target=wait, daemon=True).start()
        return job

    def record_threads(self, sid, body, notes, at, job):
        """Each note of a recorded review becomes a thread: a top-level comment
        (Lattice nests one level only) naming the place, what was reviewed, the
        review and the quoted lines. A note on lines that already have an open
        thread (same file and quoted lines, or same file and place for a
        thread without a quote) is a follow-up reply in that thread, so a line
        keeps one history; when several open threads could take it, it starts
        its own. notes are (path, where, text, quote)."""
        if not notes:
            return
        comments = self.comments(sid)
        review = next((c for c in reversed(comments) if c.get("role") in ("review", "plan-review")
                       and (c.get("body") or "").strip() == body.strip()), None)
        if not review:
            job.error = "the review was recorded but its notes could not be split into threads"
            return
        open_threads = [t for t in review_threads(comments)
                        if t["state"] != "resolved" and t["key"] and t["root"].get("id") != review["id"]]
        for i, (path, where, text, quote) in enumerate(notes, 1):
            anchor = note_anchor(path, where)
            existing = thread_for(open_threads, path, where, quote)
            if existing:
                content = "%s%s, %s at %s:\n%s\n" % (FOLLOW_UP, review["id"], anchor, at, text)
                args = ("comment", sid, "--reply-to", existing["root"]["id"])
            else:
                content = "%s%s at %s\n%s%s\n%s%s\n" % (THREAD, anchor, at, REVIEW_OF, review["id"],
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
        """The owner's reply in one thread, from the review section. False when
        it was not posted; the text then comes back in the reply box."""
        if not text.strip():
            raise RuntimeError("the reply is empty")
        (self.state / "tmp").mkdir(exist_ok=True)
        path = self.state / "tmp" / ("reply-%s.md" % secrets.token_hex(6))
        path.write_text(text.strip() + "\n")
        try:
            posted = self.board_write(sid, "comment", sid, "--reply-to", parent, "--file", str(path))
        finally:
            path.unlink(missing_ok=True)
        if posted:
            self.notices[sid] = ("ok", "Reply posted.")
            self.drafts.pop((sid, parent), None)
        else:
            self.drafts[(sid, parent)] = text
        return posted

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
        head_sha = rev(self.repo, head)
        if not (base_sha and head_sha):
            raise RuntimeError("the range %s..%s does not resolve to commits" % (base, head))
        (self.state / "tmp").mkdir(exist_ok=True)
        left = self.side(base_sha, old_path or path)
        left.write_bytes(b"" if status == "A" else run_git(self.repo, "show", base_sha + ":" + (old_path or path), binary=True))
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
form{display:inline}
button{padding:.3rem .8rem;margin:.15rem .3rem .15rem 0;line-height:1.3;border:1px solid color-mix(in srgb,var(--accent-primary,#2b6cb0) 60%,var(--border,#3a4250));border-radius:var(--radius-sm,4px);background:color-mix(in srgb,var(--accent-primary,#2b6cb0) 16%,var(--surface-raised,#252a33));color:var(--text-primary,#e4e7eb);font:600 .85rem var(--font-body,system-ui,sans-serif);cursor:pointer}
button:hover{background:color-mix(in srgb,var(--accent-primary,#2b6cb0) 32%,var(--surface-raised,#252a33))}
button:focus-visible{outline:2px solid var(--accent-primary,#2b6cb0);outline-offset:2px}
button.primary{border:2px solid var(--accent-primary,#2b6cb0);background:color-mix(in srgb,var(--accent-primary,#2b6cb0) 34%,var(--surface-raised,#252a33))}button.primary:hover{filter:brightness(1.15)}
button.small{padding:.25rem .6rem;font-size:.78rem;font-weight:500}button[disabled]{opacity:.55;cursor:default}
code,pre{overflow-wrap:anywhere}td:last-child,td:first-child code,.when{white-space:nowrap}
@media (max-width:480px){.when{display:none}td:last-child,td:first-child code{white-space:normal}}
p{margin:.3rem 0}.muted{color:var(--text-muted,#9aa4b2)}.warn{color:var(--color-warning,#f6c343)}.err{color:var(--color-danger,#ff7b72)}.ok{color:var(--color-success,#7ee787)}
.block,.thread{--hue:#94a3b8;margin:.6rem 0;padding:.55rem .75rem;border:1px solid color-mix(in srgb,var(--hue) 22%,transparent);border-left:3px solid color-mix(in srgb,var(--hue) 70%,transparent);border-radius:8px;background:color-mix(in srgb,var(--hue) 9%,transparent)}
.block h4{margin:0 0 .35rem;font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;color:color-mix(in srgb,var(--hue) 60%,var(--text-primary,#e4e7eb))}
.block.plan{--hue:#c084fc}.block.changes{--hue:#7aa2f7}.block.verdict{--hue:var(--accent-primary,#2b6cb0)}.block.deps{--hue:#f59e0b}
.day{margin:.6rem 0 .2rem;font-size:.72rem;font-weight:700;letter-spacing:.04em;color:var(--text-muted,#9aa4b2)}
.event{margin:.15rem 0;padding:.3rem .5rem;border-radius:6px;border:1px solid color-mix(in srgb,#2dd4bf 14%,transparent);background:color-mix(in srgb,#2dd4bf 7%,transparent)}
.event .who{font-weight:600}.event .who.owner{color:color-mix(in srgb,var(--accent-primary,#2b6cb0) 70%,var(--text-primary,#e4e7eb))}
a{color:color-mix(in srgb,var(--accent-primary,#2b6cb0) 75%,var(--text-primary,#e4e7eb))}
@keyframes lrflash{from{box-shadow:0 0 0 3px var(--accent-primary,#2b6cb0)}to{box-shadow:0 0 0 3px transparent}}.lr-flash{animation:lrflash 1.6s ease-out}
body[data-f=change] .event.comment,body[data-f=comment] .event.change{display:none}.filters{margin:.2rem 0 .4rem}
.event.group>details>summary{cursor:pointer}.event.group .event{margin-left:1rem}
.next.ask{border-color:var(--color-warning,#f6c343);background:color-mix(in srgb,var(--color-warning,#f6c343) 12%,transparent)}
.next{margin:.2rem 0 .6rem;padding:.55rem .75rem;border:1px solid var(--accent-primary,#2b6cb0);border-left-width:4px;border-radius:8px;background:color-mix(in srgb,var(--accent-primary,#2b6cb0) 12%,transparent)}
.thread{--hue:var(--color-warning,#f6c343);border-left-width:4px}.thread.resolved{--hue:var(--color-success,#7ee787)}
.msg{margin:.35rem 0;padding:.35rem .5rem;border-radius:6px;background:color-mix(in srgb,var(--hue,#94a3b8) 8%,transparent)}.msg .text{white-space:pre-wrap}
.msg.owner{background:color-mix(in srgb,var(--accent-primary,#2b6cb0) 11%,transparent)}.msg .who{font-weight:600;color:var(--text-primary,#e4e7eb)}form.reply{display:flex;gap:.3rem;align-items:flex-end;margin:.3rem 0}
textarea{flex:1;min-height:2.6rem;font:inherit;color:inherit;background:var(--surface,#2a2f37);border:1px solid var(--border,#3a4250);border-radius:var(--radius-sm,4px);padding:.25rem}
"""

INHERIT = """<script>try{var s=getComputedStyle(parent.document.documentElement);
["--text-primary","--text-muted","--accent-primary","--text-on-accent","--surface","--surface-hover","--surface-raised","--border","--radius-sm",
"--font-body","--font-mono","--color-warning","--color-danger","--color-success","--bg-base"].forEach(function(v){
document.documentElement.style.setProperty(v,s.getPropertyValue(v))});
document.documentElement.style.colorScheme=s.colorScheme}catch(e){}</script>"""


def e(value):
    return html.escape("" if value is None else str(value))


# While a Plannotator session runs the section reloads to show its result, but
# never while a reply is being typed or holds text. A form is sent once, after
# its question if it has one. The result of an action is scrolled into view.
RELOAD = """<script>setInterval(function(){var a=document.activeElement,t=document.querySelectorAll("textarea");
if(a&&a.tagName==="TEXTAREA")return;for(var i=0;i<t.length;i++)if(t[i].value.trim())return;location.reload()},5000)</script>"""
FORMS = """<script>document.addEventListener("submit",function(ev){var f=ev.target,q=f.getAttribute("data-confirm");
if(f.dataset.sent||(q&&!confirm(q))){ev.preventDefault();ev.stopPropagation();return}
f.dataset.sent="1";setTimeout(function(){delete f.dataset.sent},4000)},true);
addEventListener("load",function(){var n=document.getElementById("notice");
if(n)setTimeout(function(){n.scrollIntoView({block:"center"})},300)})</script>"""


def page(title, body, refresh=False):
    return ("<!doctype html><html><head><meta charset='utf-8'><title>" + e(title) + "</title>" + INHERIT
            + "<style>" + STYLE + "</style></head><body>" + body + FORMS + (RELOAD if refresh else "") + "</body></html>").encode()


def button(ctx, action, label, fields=None, primary=False, tab=False, small=False, confirm=None):
    """A one-button form. tab=True submits into a new tab of the same browser
    and reloads this page shortly after, so the section shows the new state.
    confirm is a question the owner answers before the form is sent."""
    hidden = "".join("<input type='hidden' name='%s' value='%s'>" % (e(k), e(v)) for k, v in (fields or {}).items())
    cls = " class='%s'" % " ".join(c for c, on in (("primary", primary), ("small", small)) if on) if primary or small else ""
    target = " target='_blank' onsubmit=\"setTimeout(function(){location.reload()},1500)\"" if tab else ""
    if confirm:
        target += " data-confirm='%s'" % e(confirm)
    return ("<form method='post' action='%s'%s><input type='hidden' name='token' value='%s'>%s<button%s>%s</button></form>"
            % (e(action), target, ctx.token, hidden, cls, e(label)))


def reply_form(ctx, action, parent, draft=""):
    return ("<form method='post' action='%s' class='reply'><input type='hidden' name='token' value='%s'>"
            "<input type='hidden' name='parent' value='%s'><textarea name='body' placeholder='Reply in this thread'>%s</textarea>"
            "<button>Reply</button><button name='resolve' value='1'>Reply and resolve</button></form>" % (e(action), ctx.token, e(parent), e(draft)))


def is_plan_thread(thread):
    return thread["anchor"].startswith("plan,") or thread["anchor"] == "plan"


def render_threads(ctx, sid, threads, title, notes=None):
    """Each review thread with its whole history, a reply box and Resolve.
    notes maps a thread's root comment to the result of the last action on it."""
    if not threads:
        return ""
    act = REVIEW_PATH + "/t/" + sid + "/"
    unresolved = sum(1 for t in threads if t["state"] != "resolved")
    out = ["<p><b>%s</b> <span class='muted'>%d open of %d. Continue a thread here; a new Plannotator note starts a new one.</span></p>"
           % (e(title), unresolved, len(threads))]
    for t in threads:
        resolved = t["state"] == "resolved"
        status = " <span class='muted'>agent: %s</span>" % e(t["status"]) if t["status"] and not resolved else ""
        out.append("<div class='thread%s' id='thread-%s'><p><b>%s</b> <span class='%s'>%s</span>%s</p>"
                   % (" resolved" if resolved else "", e(t["root"].get("id")), e(t["anchor"]), "ok" if resolved else "warn", e(t["state"]), status))
        for m in t["messages"]:
            text = t["note"] if m is t["root"] else m.get("body") or ""
            owner = (m.get("author") or "").startswith("human:")
            out.append("<div class='msg%s'><span class='who'>%s</span> <span class='muted'>%s%s</span><div class='text'>%s</div></div>"
                       % (" owner" if owner else "", e(m.get("author")), e(m.get("created_at")), ", edited" if m.get("edited") else "", e(text)))
        out.append((notes or {}).get(t["root"].get("id"), ""))
        if resolved:
            out.append(button(ctx, act + "reopen", "Reopen", {"comment": t["root"]["id"]}))
        else:
            out.append(reply_form(ctx, act + "reply", t["root"]["id"], ctx.drafts.get((sid, t["root"]["id"]), "")))
            out.append(button(ctx, act + "resolve", "Resolve", {"comment": t["root"]["id"]}))
        out.append("</div>")
    return "".join(out)


def task_history(ctx, task):
    """The entries of a task's history: its event log, comments and commits."""
    rng = resolve_range(ctx.repo, task, ctx.main)
    tasks = load_tasks(ctx.board)

    def events_of(task_id):
        return [json.loads(line) for line in ctx.events(task_id)]
    own = [c["hash"] for c in rng["commits"]]
    entries = history(events_of(task["id"]), ctx.comments(task["short_id"]), commit_details(ctx.repo, own),
                      {t["id"]: t.get("short_id") for t in tasks})
    entries += cross_references(task, tasks, events_of) + commit_mentions(ctx.repo, task["short_id"], set(own), ctx.main)
    return fold_bursts(sorted(entries, key=lambda item: item["ts"], reverse=True))


# The history frame is capped and the review frame is as tall as its content;
# it is the panel around them (or the page) that scrolls. A jump scrolls that
# to the target, in the review frame or in the dashboard's own sections
# (comments, criteria), and flashes it. The filters show all entries, only
# changes or only comments, as Jira's History and Activity views do.
JUMP = """<script>function lrScroll(el,f){var P=parent.document,pane=P.getElementById("detail-panel"),
inPane=pane&&pane.contains(f||el),top=el.getBoundingClientRect().top+(f?f.getBoundingClientRect().top:0),
dy=top-(inPane?pane.getBoundingClientRect().top:0)-90;(inPane?pane:parent).scrollBy({top:dy,behavior:"smooth"});
el.classList.remove("lr-flash");void el.offsetWidth;el.classList.add("lr-flash");return false}
function lrJump(id){var f=parent.document.querySelector("iframe.review-frame:not(.history-frame)"),t=f&&f.contentDocument.getElementById(id);
return t?lrScroll(t,f):false}
function lrFind(sel,test){var hit=[].find.call(parent.document.querySelectorAll(sel),test);return hit?lrScroll(hit.closest("div")||hit,null):false}
function lrComment(who,ts){return lrFind(".dp-comment,.comment-item",function(c){return c.textContent.indexOf(who+" \\u00b7 "+ts)>=0})}
function lrCriterion(id){return lrFind("[data-lr=criteria] strong",function(s){return s.textContent.trim()===id})}
function lrFilter(f){document.body.dataset.f=f;[].forEach.call(document.querySelectorAll(".filters button"),function(b){
b.classList.toggle("primary",b.dataset.f===f)});var fe=frameElement;if(fe){fe.style.height="1px";
fe.style.height=Math.min(document.documentElement.scrollHeight+4,Math.round(parent.innerHeight*0.6))+"px"}}</script>"""


def ago(ts, now):
    """A relative time like GitHub's: just now, 5m ago, 3h ago, yesterday, or the date."""
    seconds = (now - ts).total_seconds()
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return "%dm ago" % (seconds // 60)
    if seconds < 86400:
        return "%dh ago" % (seconds // 3600)
    if seconds < 172800:
        return "yesterday"
    return ts.astimezone().strftime("%b %d").replace(" 0", " ")


def js(value):
    """A value as a JavaScript literal inside a double-quoted HTML attribute."""
    return e(json.dumps(value))


def render_dependencies(task, links):
    """Waits on, holds up, part of, subtasks and related, each linked task with
    its status, and a warning when work has started on a task that still waits
    on unfinished ones."""
    if not links:
        return []
    titles = {"waits": "Waits on", "holds": "Holds up", "parent": "Part of", "child": "Subtasks", "related": "Related"}
    out = []
    started = task.get("status") in ("in_progress", "in_review", "done")
    open_waits = [o for kind, o, _ in links if kind == "waits" and o.get("status") not in ("done", "cancelled")]
    if started and open_waits:
        out.append("<p class='warn'>This task is %s but still waits on %s.</p>" % (
            e((task.get("status") or "").replace("_", " ")),
            ", ".join("%s (%s)" % (e(o["short_id"]), e((o.get("status") or "").replace("_", " "))) for o in open_waits)))
    for kind in ("waits", "holds", "parent", "child", "related"):
        rows = [(o, note) for k, o, note in links if k == kind]
        if rows:
            items = ["<a href='/t/%s' target='_top'>%s</a> %s <span class='muted'>%s%s</span>" % (
                e(o["short_id"]), e(o["short_id"]), e(o.get("title")), e((o.get("status") or "").replace("_", " ")),
                ", " + e(note) if note else "") for o, note in rows]
            out.append("<p><b>%s</b><br>%s</p>" % (titles[kind], "<br>".join(items)))
    return out


def render_entry(item, now):
    who = item["actor"]
    kind, target = item["link"] or (None, None)
    show = " <a href='#' onclick=\"return %s\">show</a>"
    if kind == "task":
        more = " <a href='/t/%s' target='_top'>open %s</a>" % (e(target), e(target))
    elif kind == "thread":
        more = show % ("lrJump(%s)" % js("thread-" + target))
    elif kind in ("plan", "code"):
        more = show % ("lrJump(%s)" % js(kind))
    elif kind == "commit":
        more = show % ("lrJump(%s)" % js("commit-" + target[:12]))
    elif kind == "comment":
        more = show % ("lrComment(%s,%s)" % (js(target[0]), js(target[1])))
    elif kind == "criterion":
        more = show % ("lrCriterion(%s)" % js(target))
    else:
        more = ""
    local = item["ts"].astimezone()
    line = "<span class='muted' title='%s, %s'>%s</span> <span class='who%s'>%s</span> %s%s" % (
        e(ago(item["ts"], now)), e(local.strftime("%a %b %d %Y")), e(local.strftime("%H:%M")),
        " owner" if who.startswith("human:") else "", e(who), e(item["text"]), more)
    if item["behalf"]:
        line += " <span class='%s'>on behalf of %s</span>" % ("warn" if not who.startswith("human:") else "muted", e(item["behalf"]))
    if item["why"]:
        line += "<br><span class='muted'>Why: %s</span>" % e(item["why"])
    if item["details"]:
        line += "<details><summary>What changed</summary><pre>%s</pre></details>" % e(item["details"])
    return line


def render_history(ctx, sid, entries):
    """The history, grouped by day in local time, newest first, with filters.
    It is served in its own frame at the bottom of the task, below the
    comments; its links jump to their place in the review section's frame or
    the dashboard's own sections."""
    if not entries:
        return ""
    now = datetime.datetime.now(datetime.timezone.utc)
    out = [JUMP, "<p class='filters'>%s</p>" % "".join(
        "<button type='button' class='small%s' data-f='%s' onclick=\"lrFilter('%s')\">%s</button>" % (
            " primary" if f == "all" else "", f, f, label) for f, label in (("all", "All"), ("change", "Changes"), ("comment", "Comments")))]
    day = None
    for item in entries:
        local = item["ts"].astimezone()
        if local.date() != day:
            day = local.date()
            out.append("<p class='day'>%s</p>" % e(local.strftime("%a %b %d").replace(" 0", " ")))
        if item.get("group"):
            inner = "".join("<div class='event %s'>%s</div>" % (g["cat"], render_entry(g, now)) for g in item["group"])
            out.append("<div class='event %s group'><details><summary>%s</summary>%s</details></div>" % (
                item["cat"], render_entry(item, now), inner))
        else:
            out.append("<div class='event %s'>%s</div>" % (item["cat"], render_entry(item, now)))
    return "".join(out)


def next_step(ctx, task, rng, review, threads, running, block, plan_state, comments):
    """One line that says what the owner does now."""
    sid, status = task["short_id"], task.get("status")
    act = REVIEW_PATH + "/t/" + sid + "/"
    on_agent = sum(1 for t in threads if t["state"] == "waiting on the agent")
    on_you = sum(1 for t in threads if t["state"] == "waiting on you")
    if status == "done":
        trees = sorted(p.name for p in (ctx.repo / ".worktrees").glob(sid + "*") if p.name in (sid, sid + "-a", sid + "-b", sid + "-c"))
        if not trees:
            return ""
        return "<p class='next'>Done. Still on disk: %s. Remove each with <code>git worktree remove .worktrees/&lt;name&gt;</code>.</p>" % e(
            ", ".join(".worktrees/" + name for name in trees))
    if running:
        text = ("Write your notes in the Plannotator tab, then Send Feedback or Approve. Plannotator then says the feedback "
                "went back to the agent: close that tab and come back here. Each note becomes a thread below.")
    elif status in ("done", "cancelled"):
        return ""
    elif plan_state and plan_state != "approved" and waits_for_plan_approval(task):
        text = ("The agent is waiting for you to approve its plan. Use Plannotator: review the plan. Comment on lines or "
                "edit it in place, then Send Feedback (each note becomes a thread the agent answers) or Approve, which "
                "also clears the agent's approval flag.")
    elif rng["mode"] == "none":
        if not rng.get("empty_branch"):
            if plan_state != "approved":
                return ""
            return "<p class='next'>%s</p>" % e("Plan approved. Nothing for you to do until the agent commits its work and "
                                                "returns the task to review.")
        text = "Nothing is committed for %s yet, so there is nothing to approve. " % sid
        text += "To complete the task, the agent commits the work with the trailer Task: %s." % sid
    elif review and review_decision(review.get("body") or "") == "approved" and not stale_reason(ctx.repo, task, ctx.main, review["body"], comments) \
            and on_agent + on_you:
        text = ("Approved at %s. %d thread(s) still open: Resolve each one you are done with, or Reply and resolve to add a "
                "last word. If one needs more work, reply in it and move the task back to in progress."
                % (reviewed_revision(review["body"])[1][:12], on_agent + on_you))
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
        text = "Approved, every thread resolved, the work merged and every criterion evidenced. The summary above Mark done below says what was reviewed."
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
    return "<p class='%s' id='notice' role='status'>%s</p>" % (kind, e(text)) if kind else ""


def open_request(ctx, task, plan_state):
    """The agent's open Need: flag, so a question is never below the fold or
    behind a hover. The plan approval flag clears itself on Approve."""
    flag = task.get("needs_human") or {}
    if not flag.get("reason") or task.get("status") in ("done", "cancelled"):
        return ""
    how = ""
    if not (plan_state != "approved" and waits_for_plan_approval(task)):
        how = ("<br>When you have answered it, clear it: <code>lattice needs-human %s --clear --note \"&lt;your answer&gt;\" --actor %s</code>"
               % (e(task["short_id"]), e(ctx.actor)))
    return "<p class='next ask'><b>Open request from %s:</b> %s%s</p>" % (e(flag.get("flagged_by") or "the agent"), e(flag["reason"]), how)


def branch_notes(ctx, task, rng):
    """Branches the range does not read, named: unlinked branches of the task
    (candidates), a linked branch that is missing, and further linked ones."""
    sid, links = task["short_id"], [link["branch"] for link in task.get("branch_links", [])]
    own = run_git(ctx.repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/feature/%s-*" % sid).split()
    out = []
    unlinked = [b for b in own if b not in links]
    if unlinked and task.get("status") not in ("done", "cancelled"):
        out.append("<p class='warn'>Not linked, so not read here: %s. If these are competing versions, compare them, then link "
                   "the one you pick: <code>lattice branch-link %s &lt;branch&gt; --actor %s</code></p>"
                   % (", ".join("<code>%s</code>" % e(b) for b in unlinked), e(sid), e(ctx.actor)))
    for branch in links:
        if not rev(ctx.repo, branch):
            out.append("<p class='err'>Linked branch <code>%s</code> is not in this repository. Fetch it, or unlink it.</p>" % e(branch))
        elif rng["mode"] == "branch" and branch != rng["branch"]:
            out.append("<p>Also linked and not read: <code>%s</code>. Only the first linked branch with commits is reviewed.</p>" % e(branch))
    return out


def contains(repo, ref, sha):
    """Whether commit sha is in the history of ref."""
    try:
        run_git(repo, "merge-base", "--is-ancestor", sha, ref)
    except RuntimeError:
        return False
    return True


def closing_summary(repo, main, rng, comments, threads, plan_state):
    """What the owner needs before closing an approved task whose work has
    landed: the review rounds, the threads resolved, where the commits are,
    and the newest agent note, since agents record installs and deploys there."""
    def count(n, word):
        return "%d %s%s" % (n, word, "" if n == 1 else "s")
    people = [c for c in comments if (c.get("author") or "").startswith("human:") and not c.get("deleted")]
    plans = sum(1 for c in people if c.get("role") == "plan-review" and PLAN_DECISION.match(c.get("body") or ""))
    reviews = sum(1 for c in people if c.get("role") == "review" and reviewed_revision(c.get("body") or "")[1])
    resolved = sum(1 for t in threads if t["state"] == "resolved")
    facts = "Plan approved after %s. " % count(plans, "review") if plan_state == "approved" else ""
    facts += "Code approved after %s, %s." % (count(reviews, "review"), count(resolved, "thread") + " resolved" if resolved else "no threads")
    where = count(len(rng["commits"]), "commit") + ", "
    if rev(repo, main + "@{upstream}"):
        where += "merged into %s and pushed. Nothing left to merge or push." % main
    else:
        where += "merged into %s, which has no upstream." % main
    lines = [facts, where]
    notes = [c for c in comments if (c.get("author") or "").startswith("agent:") and not c.get("deleted") and (c.get("body") or "").strip()]
    if notes:
        note = max(notes, key=lambda c: c.get("created_at") or "")
        first = re.split(r"(?<=[.!?])\s", note["body"].strip(), maxsplit=1)[0]
        lines.append("Latest note, %s %s: %s" % (note["author"], (note.get("created_at") or "")[:10], first[:300]))
    return "<p>%s</p>" % "<br>".join(e(line) for line in lines)


def range_summary(task, rng):
    if rng["mode"] == "branch":
        return "branch <code>%s</code> from <code>%s</code>" % (e(rng["branch"]), e(rng["base"][:12]))
    if rng["mode"] == "commits" and rng["contiguous"]:
        return "%d commit(s) with trailer <code>Task: %s</code>, range <code>%s..%s</code>" % (
            len(rng["commits"]), e(task["short_id"]), e(rng["base_sha"][:12]), e(rng["head_sha"][:12]))
    if rng["mode"] == "commits":
        return "%d commit(s) with trailer <code>Task: %s</code>, not contiguous: review them one by one" % (
            len(rng["commits"]), e(task["short_id"]))
    if rng.get("empty_branch"):
        return ("branch <code>%s</code> has no commits of its own yet. Uncommitted work cannot be approved: "
                "commit it with the trailer <code>Task: %s</code>" % (e(rng["empty_branch"]), e(task["short_id"])))
    return "no linked branch and no commit carries <code>Task: %s</code> yet" % e(task["short_id"])


def render_review(ctx, task):
    sid = task["short_id"]
    act = REVIEW_PATH + "/t/" + sid + "/"
    if not rev(ctx.repo, ctx.main):
        return page(sid + " review", "<p class='err'>The integration branch <code>%s</code> is not in this repository. "
                                     "Restart the server with <code>--main &lt;branch&gt;</code>.</p>" % e(ctx.main))
    rng = resolve_range(ctx.repo, task, ctx.main)
    head_now = rev(ctx.repo, "HEAD")
    comments = ctx.comments(sid)
    plan = ctx.board / ".lattice" / "plans" / (task["id"] + ".md")
    plan_state = plan_status(comments, plan.read_text(errors="replace")) if plan.is_file() else None
    review = latest_review(comments)
    threads = review_threads(comments)
    block = completion_block(ctx.repo, task, ctx.main, comments) if rng["mode"] != "none" else None
    job = ctx.jobs.get(sid)
    running = bool(job and not job.done)
    said, at = notice(ctx, sid), ctx.notice_at.pop(sid, None)
    notes = {at: said} if at in {t["root"].get("id") for t in threads} else {}

    plan_part = ["<p>Plan: <b>%s</b></p>" % e(plan_state or "none yet")]
    plan_buttons = []
    if plan_state and ctx.plannotator:
        waiting = plan_state != "approved" and waits_for_plan_approval(task)
        plan_buttons.append(button(ctx, act + "plan", "Plannotator: review the plan", tab=True, primary=waiting))
    if ctx.code:
        plan_buttons.append(button(ctx, act + "openplan", "Open the plan in VS Code" if plan_state else "Write the plan in VS Code"))
    if plan_buttons:
        plan_part.append("<p>" + " ".join(plan_buttons) + "</p>")
    plan_part.append(render_threads(ctx, sid, [t for t in threads if is_plan_thread(t)], "Plan threads", notes))

    code = ["<p>Work: %s</p>" % range_summary(task, rng)]
    named = branch_notes(ctx, task, rng)
    code.extend(named)
    if task.get("status") in ("in_progress", "in_review") and not task.get("branch_links") and not named:
        code.insert(0, "<p class='warn'>This task is %s but has no branch of its own. Task work belongs on its own branch in its "
                       "own worktree (see .lattice/context.md); work in the main checkout cannot be reviewed as this task.</p>"
                    % e(task["status"].replace("_", " ")))
    if rng["mode"] == "branch" and rng["branch"] != current_branch(ctx.repo):
        code.append("<p>The repo is on <code>%s</code>, this task's branch is <code>%s</code>. The range review and the diffs use the task's branch.</p>"
                    % (e(current_branch(ctx.repo)), e(rng["branch"])))
    actions = []
    if ctx.plannotator:
        if rng["base_sha"]:
            actions.append(button(ctx, act + "plannotator", "Plannotator: the whole range", {"base": rng["base"], "head": rng["head"]}, primary=True, tab=True))
    if actions:
        code.append("<p>" + " ".join(actions) + "</p>")
    if job:
        state = "Plannotator running since " + time.strftime("%H:%M:%S", time.localtime(job.started)) if running else "Plannotator finished"
        session = ["<p>%s (%s). Log <code>%s</code></p>" % (e(state), e(job.what), e(job.err_path))]
        url = session_url(job.err_path.read_text()) if job.err_path.is_file() else None
        if running:
            link = "<a href='%s' target='_blank' rel='noopener'>Open the session</a>. " % e(url) if url else ""
            session.append("<p>%sNotes stay in that session until you click Send Feedback or Approve; then they land on the task and show here. %s</p>"
                           % (link, button(ctx, act + "close", "Close session",
                                           confirm="Close the Plannotator session? Notes you have not sent are discarded.")))
        if job.error:
            session.append("<p class='err'>%s</p>" % e(job.error))
        elif job.done and not job.result_path:
            session.append("<p class='muted'>Plannotator closed without a review.</p>")
        (plan_part if job.what.startswith("plan of ") else code).extend(session)
    if rng["commits"]:
        code.append("<table><tr><th>Commit</th><th>Subject</th><th class='when'>Date</th><th></th></tr>")
        for c in rng["commits"]:
            code.append("<tr id='commit-%s'><td><code>%s</code></td><td>%s</td><td class='when'>%s</td><td>%s</td></tr>" % (
                e(c["hash"][:12]), e(c["hash"][:12]), e(c["subject"]), e(c["date"]),
                button(ctx, act + "plannotator", "Review this commit", {"base": c["hash"] + "^", "head": c["hash"]}, tab=True, small=True) if ctx.plannotator else ""))
        code.append("</table>")
    if rng["base_sha"]:
        try:
            files = changed_files(ctx.repo, rng["base"], rng["head"])
        except RuntimeError as exc:
            files = []
            code.append("<p class='err'>%s</p>" % e(exc))
        code.append("<table><tr><th></th><th>File (%d)</th><th></th></tr>" % len(files))
        for f in files:
            shown = f["path"] if f["old_path"] == f["path"] else f["old_path"] + " → " + f["path"]
            cells = ""
            if ctx.code:
                if rng["head_sha"] == head_now and (ctx.repo / f["path"]).is_file():
                    cells += button(ctx, act + "open", "open", {"path": f["path"]}, small=True)
                cells += button(ctx, act + "filediff", "diff", {"path": f["path"], "old_path": f["old_path"], "status": f["status"],
                                                                "base": rng["base"], "head": rng["head"]}, small=True)
            code.append("<tr><td>%s</td><td><code>%s</code></td><td>%s</td></tr>" % (e(f["status"]), e(shown), cells))
        code.append("</table>")
    if review:
        text = review.get("body") or ""
        label = {"approved": "approved", "annotated": "changes requested"}.get(review_decision(text), "review")
        covered = re.match(r"^Plannotator \w+ \((.*)\), \S+$", text.splitlines()[0] if text else "")
        code.append("<p>Latest review: <b>%s</b>%s <span class='muted'>%s %s</span></p><details><summary>Full review text</summary><pre>%s</pre></details>" % (
            e(label), ", of " + e(covered.group(1)) if covered else "", e(review.get("author")), e(review.get("created_at")), e(text)))
        expected, recorded = len(review_notes(text)), recorded_notes(comments).get(review.get("id"), 0)
        if recorded < expected:
            code.append("<p class='err'>Only %d of its %d notes were recorded as threads; the full text above has them all. Review again to record the rest.</p>"
                        % (recorded, expected))
    if task.get("status") not in ("done", "cancelled") and rng["mode"] != "none":
        if block:
            code.append("<p>Completion: %s.</p>" % e(block))
        else:
            code.append(closing_summary(ctx.repo, ctx.main, rng, comments, threads, plan_state))
            ask = (task.get("needs_human") or {}).get("reason")
            code.append(button(ctx, act + "complete", "Mark done: approved at %s" % reviewed_revision(review["body"])[1][:12], primary=True,
                               confirm="Mark %s done? Done is final.%s" % (sid, " The open request is: " + ask if ask else "")))
    code.append(render_threads(ctx, sid, [t for t in threads if not is_plan_thread(t)], "Code review threads", notes))

    def section(kind, anchor, title, parts):
        return "<section class='block %s' id='%s'><h4>%s</h4>%s</section>" % (kind, anchor, title, "".join(parts))
    deps = render_dependencies(task, dependencies(task, load_tasks(ctx.board)))
    body = [tool_notes(ctx), "" if notes else said, open_request(ctx, task, plan_state), next_step(ctx, task, rng, review, threads, running, block, plan_state, comments),
            section("deps", "deps", "Dependencies", deps) if deps else "",
            section("plan", "plan", "Plan", plan_part), section("verdict", "code", "Code review", code)]
    return page(sid + " review", "".join(body), refresh=running)


# --------------------------------------------------------------------------
# http: the dashboard's handler class, with the review routes on top
# --------------------------------------------------------------------------

def make_handler(ctx, base=None, static_dir=None):
    """The dashboard handler class extended with the review routes.

    base and static_dir default to Lattice's own; the tests pass a stand-in."""
    if base is None:
        from lattice.dashboard import server as dashboard, git_reader
        protect_dashboard_git(dashboard, git_reader)
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
                try:
                    return super().do_GET()
                except RuntimeError as exc:
                    return self.send_json(409, {"ok": False, "error": {"code": "GIT_READ_ERROR", "message": str(exc)}})
            if parts[1:2] == ["t"] and len(parts) in (3, 4):
                task = find_task(ctx.board, parts[2])
                try:
                    if task and len(parts) == 3:
                        return self.send_page(render_review(ctx, task))
                    if task and parts[3] == "history":
                        entries = task_history(ctx, task)
                        return self.send_page(page(task["short_id"] + " history", render_history(ctx, task["short_id"], entries)
                                                   or "<p class='muted'>Nothing has happened on this task yet.</p>"))
                except RuntimeError as exc:
                    return self.send_page(page("Git read refused", "<p class='err'>%s</p>" % e(exc)), 409)
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
            """Task writes from the dashboard carry this server's actor (the page
            sends none or dashboard:web); other writes, such as the dashboard's
            own settings, which reject unknown keys, pass through unchanged.
            Done needs what Mark done needs; a task without commits needs
            evidence on every open criterion. False means a reply was sent."""
            if parts[:2] == ["api", "tasks"] and record.get("actor") in (None, "dashboard:web"):
                record["actor"] = ctx.actor
            if parts[:2] == ["api", "tasks"] and parts[3:] == ["status"] and record.get("status") == "done":
                task = find_task(ctx.board, parts[2])
                if task:
                    if resolve_range(ctx.repo, task, ctx.main)["mode"] != "none":
                        block = completion_block(ctx.repo, task, ctx.main, ctx.comments(task["short_id"]))
                    else:
                        block = criteria_block(task, ctx.comments(task["short_id"]))
                    if block:
                        self.send_json(409, {"ok": False, "error": {"code": "REVIEW_REQUIRED", "message": "not completed: " + block}})
                        return False
            return True

        def review_post(self, parts, raw):
            form = {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode()).items()}
            if form.get("token") != ctx.token:
                return self.forbidden("This page is from before the review server restarted (bad token). "
                                      "Reload the dashboard page, then try again.")
            if len(parts) != 4 or parts[1] != "t":
                return self.send_page(page("not found", "<p>not found</p>"), 404)
            sid, action = parts[2], parts[3]
            task = find_task(ctx.board, sid)
            if not task:
                return self.send_page(page("not found", "<p>not found</p>"), 404)
            try:
                if action == "plannotator":
                    return self.open_session(sid, form)
                if action == "plan":
                    return self.to_session(sid, lambda: ctx.start_plan_review(task))
                if action == "openplan":
                    ctx.open_plan(task)
                elif action == "close":
                    ctx.close_session(sid)
                elif action == "open":
                    ctx.code_open(ctx.repo_path(form["path"]))
                    ctx.notices[sid] = ("ok", "Opened %s in VS Code." % form["path"])
                elif action == "filediff":
                    ctx.code_diff(form["base"], form["head"], form["path"], form.get("old_path"), form.get("status", "M"))
                    ctx.notices[sid] = ("ok", "Opened the diff of %s in VS Code." % form["path"])
                elif action == "complete":
                    block = completion_block(ctx.repo, task, ctx.main, ctx.comments(sid))
                    if block:
                        ctx.notices[sid] = ("err", "not completed: " + block)
                    else:
                        ctx.board_write(sid, "status", sid, "done", "--no-auto-review")
                elif action == "reply":
                    ctx.notice_at[sid] = form.get("parent")
                    posted = True
                    if form.get("body", "").strip() or form.get("resolve") != "1":
                        posted = ctx.post_reply(sid, form["parent"], form.get("body", ""))
                    if posted and form.get("resolve") == "1":
                        ctx.board_write(sid, "react", sid, form["parent"], RESOLVED)
                elif action in ("resolve", "reopen"):
                    ctx.notice_at[sid] = form.get("comment")
                    ctx.board_write(sid, "react" if action == "resolve" else "unreact", sid, form["comment"], RESOLVED)
                elif action == "rework":
                    ctx.board_write(sid, "status", sid, "in_progress", "--no-auto-review")
            except (RuntimeError, OSError, KeyError) as exc:
                ctx.notices[sid] = ("err", str(exc))
            self.redirect(REVIEW_PATH + "/t/" + sid)

        def open_session(self, sid, form):
            """A code review of the task's range."""
            def start():
                return ctx.start_plannotator(sid, record_on=sid, base=form.get("base") or None, head=form.get("head") or None)
            return self.to_session(sid, start)

        def to_session(self, sid, start):
            """Start a Plannotator session and send this tab to it; the task page
            reloads on its own. Runs in the browser the owner already uses."""
            try:
                job = start()
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
    parser.add_argument("--actor", default="human:" + os.environ.get("USER", "owner"), help="actor recorded on writes")
    parser.add_argument("--state", help="where review output, logs and temp files for diffs are kept")
    args = parser.parse_args(argv)
    if not args.actor.startswith("human:"):
        sys.exit("--actor must be a person (human:<name>): resolving threads and approving plans count only for a person")
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
