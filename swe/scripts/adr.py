#!/usr/bin/env python3
"""Decision records: which ones govern a file, the index, and a check.

    adr.py for [--rev REV] PATH...   records whose "applies-to" covers a path
    adr.py index [--write]           the index, printed or written beside the records
    adr.py check                     front matter, links, globs and the index

A record is a Markdown file named ADR-NNNN-<slug>.md under docs/, docs/adr/
or docs/decisions/, opening with front matter. Only this much YAML is read:
"key: value", and a list as "- item" lines or "[a, b]". Anything else is an
error, so a record means the same to every reader.

    ---
    status: proposed            proposed | accepted | rejected | superseded
    date: 2026-11-11
    decision-makers: <name>     required once accepted
    supersedes: ADR-0002        optional
    applies-to:                 globs from the repository root; * also crosses folders
      - swe/scripts/*.py
    review-by: 2027-05-11       optional; check warns once it has passed
    ---

"for" prints accepted records, and proposed ones marked as not yet binding.
With --rev it reads the records as they stood at that revision, which is how
a reviewer judges a change by the decisions in force before it.
"""
import argparse
import datetime
import fnmatch
import os
import re
import subprocess
import sys

PLACES = ("docs/ADR-*.md", "docs/adr/*.md", "docs/decisions/*.md")
NOT_A_RECORD = re.compile(r"INDEX|TEMPLATE|README", re.I)
STATUSES = ("proposed", "accepted", "rejected", "superseded")
LISTS = ("decision-makers", "supersedes", "applies-to")
KEYS = ("status", "date", "review-by") + LISTS
SECTIONS = (("## Context",), ("## Decision",), ("## Rejected options", "## Alternatives considered"),
            ("## Consequences",))
INDEX_NAME = "ADR-INDEX.md"


def git(root, *args):
    out = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("adr: git %s: %s" % (args[0], out.stderr.strip()[:200]))
    return out.stdout


def tracked(root, rev=None):
    if rev:
        return git(root, "ls-tree", "-r", "--name-only", rev).splitlines()
    # The working tree counts a record that is drafted and not yet committed.
    listed = git(root, "ls-files", "--cached", "--others", "--exclude-standard").splitlines()
    return [path for path in listed if os.path.exists(os.path.join(root, path))]


def text_of(root, path, rev=None):
    if rev:
        return git(root, "show", "%s:%s" % (rev, path))
    with open(os.path.join(root, path), encoding="utf-8") as handle:
        return handle.read()


def front_matter(text):
    """The record's facts and what is wrong with how they are written."""
    meta, errors = {}, []
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---" or "---" not in [line.strip() for line in lines[1:]]:
        return meta, ["no front matter between two --- lines at the top"]
    key = None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        item = re.match(r"^\s+-\s+(.+)$", line)
        pair = re.match(r"^([a-z-]+):\s*(.*)$", line)
        if item and key in LISTS and isinstance(meta.get(key), list):
            meta[key].append(item.group(1).strip().strip("\"'"))
        elif pair:
            key, value = pair.group(1), pair.group(2).strip()
            if key not in KEYS:
                errors.append("unknown key %r" % key)
            inline = re.match(r"^\[(.*)\]$", value)
            if key in LISTS:
                parts = inline.group(1).split(",") if inline else ([value] if value else [])
                meta[key] = [part.strip().strip("\"'") for part in parts if part.strip()]
            else:
                meta[key] = value.strip("\"'")
        elif line.strip():
            errors.append("cannot read the line %r" % line.strip()[:60])
    return meta, errors


def records(root, rev=None):
    out = []
    for path in sorted(tracked(root, rev)):
        name = os.path.basename(path)
        number = re.match(r"(?:ADR-)?(\d{4})", name)
        if not number or NOT_A_RECORD.search(name) or not any(fnmatch.fnmatchcase(path, p) for p in PLACES):
            continue
        text = text_of(root, path, rev)
        meta, errors = front_matter(text)
        title = re.search(r"^# (?:ADR-\d{4}:\s*)?(.+)$", text, re.M)
        out.append({"id": "ADR-" + number.group(1), "path": path, "text": text, "meta": meta, "errors": errors,
                    "title": title.group(1).strip() if title else name})
    return out


def replaced_by(found):
    """Each superseded record's id and the accepted record that replaced it."""
    return {old: r["id"] for r in found if r["meta"].get("status") == "accepted"
            for old in r["meta"].get("supersedes", [])}


def status_of(record, replaced):
    status = record["meta"].get("status", "?")
    if status == "superseded" and record["id"] in replaced:
        return "superseded by " + replaced[record["id"]]
    return status


def governing(found, paths):
    out = []
    for record in found:
        if record["meta"].get("status") not in ("accepted", "proposed"):
            continue
        if any(fnmatch.fnmatchcase(path, glob) for path in paths for glob in record["meta"].get("applies-to", [])):
            out.append(record)
    return out


def index_text(found):
    replaced = replaced_by(found)
    lines = ["# Decision records", "",
             "Generated by `adr.py index --write` from each record's front matter. Do not edit by hand.", "",
             "| Record | Status | Decision | Applies to |", "|---|---|---|---|"]
    for record in found:
        globs = ", ".join("`%s`" % glob for glob in record["meta"].get("applies-to", []))
        lines.append("| [%s](%s) | %s | %s | %s |" % (record["id"], os.path.basename(record["path"]),
                                                      status_of(record, replaced), record["title"], globs))
    return "\n".join(lines) + "\n"


def problems(root, found, today):
    errors, warnings = [], []
    files, ids, replaced = tracked(root), {r["id"]: r for r in found}, replaced_by(found)
    for record in found:
        meta, said = record["meta"], lambda what, r=record: errors.append("%s: %s" % (r["path"], what))
        for error in record["errors"]:
            said(error)
        if meta.get("status") not in STATUSES:
            said("status must be one of " + ", ".join(STATUSES))
        for key in ("date", "review-by"):
            if key in meta or key == "date":
                try:
                    datetime.date.fromisoformat(meta.get(key, ""))
                except ValueError:
                    said("%s must be a date as YYYY-MM-DD" % key)
        if meta.get("status") == "accepted" and not meta.get("decision-makers"):
            said("an accepted record names its decision-makers")
        if not meta.get("applies-to"):
            said("applies-to names at least one glob")
        for glob in meta.get("applies-to", []):
            if not any(fnmatch.fnmatchcase(path, glob) for path in files):
                said("applies-to %r matches no file" % glob)
        for old in meta.get("supersedes", []):
            if old not in ids:
                said("supersedes %s, which is not a record here" % old)
            elif meta.get("status") == "accepted" and ids[old]["meta"].get("status") != "superseded":
                errors.append("%s: status must be superseded, since %s is accepted and replaces it"
                              % (ids[old]["path"], record["id"]))
        if meta.get("status") == "superseded" and record["id"] not in replaced:
            said("status is superseded but no accepted record supersedes it")
        for names in SECTIONS:
            if not any(re.search("^" + re.escape(name) + r"\b", record["text"], re.M) for name in names):
                said("no section %r" % names[0])
        review = meta.get("review-by", "")
        if meta.get("status") == "accepted" and re.fullmatch(r"\d{4}-\d\d-\d\d", review) and review < today:
            warnings.append("%s: review-by %s has passed; confirm the decision or supersede it" % (record["path"], review))
    if found:
        index = os.path.join(os.path.dirname(found[0]["path"]), INDEX_NAME)
        if index not in files:
            errors.append("%s is missing; run adr.py index --write" % index)
        elif text_of(root, index) != index_text(found):
            errors.append("%s is out of date; run adr.py index --write" % index)
    return errors, warnings


def main(argv=None):
    parser = argparse.ArgumentParser(description="Decision records: lookup, index and check.", allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    lookup = commands.add_parser("for", help="records that govern the given paths")
    lookup.add_argument("--rev", help="read the records as they stood at this revision")
    lookup.add_argument("paths", nargs="+")
    index = commands.add_parser("index", help="print the index, or write it with --write")
    index.add_argument("--write", action="store_true")
    commands.add_parser("check", help="check every record and the index")
    args = parser.parse_args(argv)
    root = git(os.getcwd(), "rev-parse", "--show-toplevel").strip()

    if args.command == "for":
        found = records(root, args.rev)
        paths = [os.path.relpath(os.path.abspath(path), root) for path in args.paths]
        hits = governing(found, paths)
        if not hits:
            print("No decision record applies to these files.")
        for record in hits:
            note = "" if record["meta"]["status"] == "accepted" else " (proposed, not yet binding)"
            print("%s  %s%s\n    %s" % (record["id"], record["title"], note, record["path"]))
        return 0
    found = records(root)
    if args.command == "index":
        if not args.write:
            sys.stdout.write(index_text(found))
        elif found:
            path = os.path.join(root, os.path.dirname(found[0]["path"]), INDEX_NAME)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(index_text(found))
            print("wrote %s" % os.path.relpath(path, root))
        return 0
    errors, warnings = problems(root, found, datetime.date.today().isoformat())
    for line in warnings:
        print("warning: " + line)
    for line in errors:
        print("error: " + line)
    if not errors:
        print("%d decision records, no errors." % len(found))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
