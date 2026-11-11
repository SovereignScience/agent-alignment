#!/usr/bin/env python3
"""Bring a project's board context up to date with this kit's template.

    board_context.py status [PROJECT]   say where the project stands; writes nothing
    board_context.py apply  [PROJECT]   merge the template's changes into the context

Run it yourself, from a checkout of this kit, naming the project's main
checkout (default: the current folder). The project's context is its
.lattice/context.md: the template with the project's own names filled in and
its own edits. The template is the block of LATTICE_ONBOARDING.md that holds
"## Conventions".

The changes are worked out against the version the context was made from: the
committed template it differs from least. A placeholder such as <CODE> or
<branch> is filled with the value the project used on its older lines, in the
old template and the new, so a name the project filled in never counts as an
edit and a new line arrives with the project's names in it.

A change that collides with the project's own edits stops apply before the
context is touched. The merge with its conflict markers is written beside it
as context.md.proposed, for a session in that project to resolve.

Exit status: 0 up to date or applied, 1 behind (status only), 2 collision.
"""
import difflib
import os
import re
import subprocess
import sys
import tempfile

KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GUIDE = "swe/LATTICE_ONBOARDING.md"
FILLED = ("<CODE>", "<branch>", "<project>", "<name>", "<path>")


def git(*args):
    out = subprocess.run(["git", "-C", KIT, *args], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("board_context: git %s: %s" % (args[0], out.stderr.strip()[:200]))
    return out.stdout


def template(text):
    """The fenced block of the guide that holds the context template."""
    lines = text.split("\n")
    fences = [i for i, line in enumerate(lines) if line.startswith("```")]
    for start, end in zip(fences[::2], fences[1::2]):
        if any(line.startswith("## Conventions") for line in lines[start + 1:end]):
            return "\n".join(lines[start + 1:end]) + "\n"
    return ""


def made_from(context):
    """The committed template the context differs from least."""
    best, least = "", None
    theirs = context.splitlines()
    for rev in git("log", "--format=%H", "--", GUIDE).split():
        candidate = template(git("show", "%s:%s" % (rev, GUIDE)))
        if not candidate:
            continue
        distance = sum(1 for line in difflib.ndiff(candidate.splitlines(), theirs) if line[:1] in "+-")
        if least is None or distance < least:
            best, least = candidate, distance
    if not best:
        sys.exit("board_context: no committed context template in this kit")
    return best


def fills(base, context):
    """What the project wrote in place of each placeholder, read from its older lines."""
    found, theirs = {}, context.splitlines()
    for line in base.splitlines():
        for mark, value in found.items():
            line = line.replace(mark, value)
        marks = sorted((mark for mark in FILLED if mark in line), key=line.index)
        if not marks:
            continue
        shape = re.escape(line)
        for number, mark in enumerate(marks, 1):
            # The first use captures the value; a repeat must match the same value.
            shape = shape.replace(re.escape(mark), "(.+?)", 1).replace(re.escape(mark), "\\%d" % number)
        for candidate in theirs:
            match = re.fullmatch(shape, candidate)
            if match and all("<" not in value for value in match.groups()):
                found.update(zip(marks, match.groups()))
                break
    return found


def filled(text, values):
    for mark, value in values.items():
        text = text.replace(mark, value)
    return text


def merged(context, base, new):
    with tempfile.TemporaryDirectory() as tmp:
        paths = [os.path.join(tmp, name) for name in ("context.md", "made-from", "template")]
        for path, text in zip(paths, (context, base, new)):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
        out = subprocess.run(["git", "merge-file", "-p", *paths], capture_output=True, text=True)
    if out.returncode < 0 or out.returncode > 127:
        sys.exit("board_context: git merge-file: %s" % out.stderr.strip()[:200])
    return out.stdout, out.returncode


def main(argv):
    if len(argv) not in (1, 2) or argv[0] not in ("status", "apply"):
        sys.exit("usage: board_context.py status|apply [PROJECT]")
    project = os.path.abspath(argv[1] if len(argv) == 2 else ".")
    path = os.path.join(project, ".lattice", "context.md")
    if not os.path.isfile(path):
        sys.exit("board_context: no board context at %s" % path)
    with open(path, encoding="utf-8") as handle:
        context = handle.read()
    with open(os.path.join(KIT, GUIDE), encoding="utf-8") as handle:
        new = template(handle.read())
    base = made_from(context)
    # Compare like with like: the template as this project would have filled it in.
    values = {mark: value for mark, value in fills(base, context).items() if mark not in context}
    result, collisions = merged(context, filled(base, values), filled(new, values))
    name = os.path.basename(project)
    if collisions:
        print("collision  %s: %d template change(s) touch lines this project edited" % (name, collisions))
        if argv[0] == "apply":
            with open(path + ".proposed", "w", encoding="utf-8") as handle:
                handle.write(result)
            print("           context.md is untouched. The merge, with conflict markers, is in\n"
                  "           %s.proposed. Ask a session in that project to resolve the markers\n"
                  "           keeping the project's own wording, then replace context.md with it." % path)
        return 2
    if result == context:
        print("unchanged  %s: the board context has every template rule" % name)
        return 0
    added = sum(1 for line in difflib.ndiff(context.splitlines(), result.splitlines()) if line[:1] == "+")
    left = sorted(mark for mark in FILLED if mark in result and mark not in context)
    if argv[0] == "status":
        print("behind     %s: %d line(s) of template changes would merge cleanly" % (name, added))
        return 1
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(result)
    print("merged     %s: %d line(s) added or changed in %s" % (name, added, path))
    if left:
        print("           fill by hand: %s appears in the new lines" % ", ".join(left))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
