"""Fail when a derived file lacks a named item of a canonical module.

A named item is, inside a module's tagged block: the first sentence of a
numbered principle or rule, a repair step's name, a defined term in
capitals, a bullet that opens with a name and then explains it, and a
Skeptic question. Each must appear word for word in every derived file;
case and line breaks are ignored except for the defined terms. A derived
file's abbreviated version, a commented short form after the full prompt,
does not count. The check sees names only: it does not compare the text
after a name, and it does not notice text a derived file should have lost.
"""
import pathlib
import re
import sys

CANONICAL = ["INNER_COMMONS_CORE.md", "FLOURISHING_PROTOCOL.md",
             "SKEPTIC_ARBITER.md", "REPAIR_PROTOCOL.md"]
DERIVED = ["COMPOSED_AGENT.md", "FOR_CLAUDE.md", "FOR_CHATGPT.md", "FOR_API.md"]

TERM = re.compile(r"^([A-Z][A-Z ]+): ")
ABBREVIATED = "\n# ── ABBREVIATED VERSION"
NAMED = [
    re.compile(r"^\d+\. (.+?)\.(?: |$)"),
    re.compile(r"^### Step \d+: (.+?)(?: \(.*\))?$"),
    re.compile(r"^- ([^.\"]+)\. \S"),
    re.compile(r"^- (.+\?)(?: \(.*\))?$"),
]


def block(text):
    opened = re.search(r"^<(\w+)>$", text, re.M)
    if not opened:
        raise ValueError("no tagged block")
    closed = text.index("</%s>" % opened.group(1))
    return text[opened.end():closed]


def squash(text):
    return " ".join(text.replace("’", "'").split())


def items(text):
    terms, names = [], []
    for line in block(text).splitlines():
        found = TERM.match(line)
        if found:
            terms.append(found.group(1))
            continue
        for pattern in NAMED:
            found = pattern.match(line)
            if found:
                names.append(found.group(1))
                break
    return terms, names


def missing(root):
    root = pathlib.Path(root)
    derived = {name: squash((root / name).read_text().split(ABBREVIATED)[0])
               for name in DERIVED}
    lacks = []
    for module in CANONICAL:
        terms, names = items((root / module).read_text())
        if not terms and not names:
            raise ValueError("%s: no named items found" % module)
        for name, text in derived.items():
            for term in terms:
                # TRUST must not be satisfied by CIVIC AND COMMUNITY TRUST.
                if not re.search(r"(?<![A-Z])(?<![A-Z] )%s:" % re.escape(term), text):
                    lacks.append((name, module, term))
            for item in names:
                if squash(item).lower() not in text.lower():
                    lacks.append((name, module, item))
    return lacks


def main(argv):
    root = argv[1] if len(argv) > 1 else pathlib.Path(__file__).resolve().parent.parent
    lacks = missing(root)
    for name, module, item in lacks:
        print("check_drift: %s lacks \"%s\" (%s)" % (name, item, module), file=sys.stderr)
    if lacks:
        print("check_drift: %d named item(s) missing from derived files" % len(lacks), file=sys.stderr)
        return 1
    print("check_drift: every named item of the canonical modules is in all four derived files")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
