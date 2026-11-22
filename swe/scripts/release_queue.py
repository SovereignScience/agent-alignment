#!/usr/bin/env python3
"""Preview independent assignments from one coordinator's release batch."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import subprocess


def item(value):
    task, separator, paths = value.partition("=")
    scopes = paths.split(",")
    if (not separator or not task or task != task.strip()
            or any(p != p.strip() or p.startswith("/") or "\\" in p or not PurePosixPath(p).parts
                   or ".." in PurePosixPath(p).parts for p in scopes)):
        raise argparse.ArgumentTypeError("use TASK=repo/path[,other/path]")
    return task, tuple(PurePosixPath(p) for p in scopes)


def check_scopes(root, items):
    for _, scopes in items:
        for scope in scopes:
            path = root
            for part in scope.parts:
                path /= part
                if path.is_symlink():
                    raise ValueError("name the underlying repo path for " + scope.as_posix())


def overlaps(left, right):
    return any(a == b or a in b.parents or b in a.parents for a in left for b in right)


def preview(rows, items, workers, review_limit, deferred=()):
    batch = dict(items)
    if len(batch) != len(items):
        raise ValueError("a task is listed twice")
    active = {row["short_id"]: row for row in rows if not row.get("archived")}
    unknown = batch.keys() - active.keys()
    if unknown:
        raise ValueError("unknown or archived batch tasks: " + ", ".join(sorted(unknown)))

    builds = [task for task, row in active.items() if row["status"] == "in_progress"]
    outside = set(builds) - batch.keys()
    if outside:
        raise ValueError("active builds need a scope in the batch: " + ", ".join(sorted(outside)))
    reviews = [task for task, row in active.items() if row["status"] == "in_review"]
    outside_reviews = set(reviews) - batch.keys()
    if set(deferred) - outside_reviews:
        raise ValueError("defer only reviews outside the batch")
    unscoped = [task for task in reviews if task in outside_reviews and task not in deferred]
    handoffs = [task for task in reviews if task in batch]
    reserved = builds + handoffs
    by_id = {row["id"]: row for row in rows}
    predecessors = {row["id"]: set() for row in rows}
    for row in rows:
        for edge in row.get("relationships_out", []):
            if edge["type"] == "depends_on":
                predecessors[row["id"]].add(edge["target_task_id"])
            elif edge["type"] == "blocks" and edge["target_task_id"] in predecessors:
                predecessors[edge["target_task_id"]].add(row["id"])
    result = {"builds": builds, "handoffs": handoffs,
              "unscoped_reviews": unscoped,
              "deferred_reviews": [task for task in reviews if task in deferred],
              "suggested": [], "held": {}}
    for task in batch:
        row = active[task]
        if row["status"] != "todo":
            continue
        reason = None
        conflict = next((other for other in reserved if overlaps(batch[task], batch[other])), None)
        if row.get("needs_human"):
            reason = "waiting for the owner"
        elif row.get("assigned_to"):
            reason = "already assigned"
        elif any(by_id.get(dep, {}).get("status") != "done" for dep in predecessors[row["id"]]):
            reason = "open or missing dependency"
        elif len(handoffs) + len(unscoped) >= review_limit:
            reason = "owner handoff limit reached"
        elif unscoped:
            reason = "scope or defer the outside reviews"
        elif conflict:
            reason = "write scope overlaps " + conflict
        elif len(builds) + len(result["suggested"]) >= workers:
            reason = "build limit reached"
        if reason:
            result["held"][task] = reason
        else:
            result["suggested"].append(task)
            reserved.append(task)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, choices=(1, 2, 3), required=True)
    parser.add_argument("--review-limit", type=int, choices=(1, 2), default=2)
    parser.add_argument("--defer-review", action="append", default=[], metavar="TASK")
    parser.add_argument("items", type=item, nargs="+", metavar="TASK=PATH[,PATH]")
    args = parser.parse_args()
    root = os.environ.get("LATTICE_ROOT")
    if not root:
        parser.error("set LATTICE_ROOT to the project main checkout")
    try:
        check_scopes(Path(root), args.items)
    except ValueError as error:
        parser.error(str(error))
    reply = subprocess.run(
        ["lattice", "list", "--include-archived", "--json"], check=True, text=True,
        stdout=subprocess.PIPE, env=dict(os.environ, LATTICE_NO_UPDATE_CHECK="1"),
    )
    try:
        result = preview(json.loads(reply.stdout)["data"], args.items, args.workers, args.review_limit, args.defer_review)
    except (KeyError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
