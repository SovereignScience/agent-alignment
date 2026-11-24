"""Build promptfoo test cases from scenarios/NN_*.md."""
import pathlib
import re

SCENARIOS = pathlib.Path(__file__).with_name("scenarios")
ROLE = re.compile(r"(User|Assistant):\s*(.*)")


def quoted(section):
    return [line[1:].removeprefix(" ") for line in section.splitlines()
            if line.startswith(">")]


def parse(path):
    """Return one promptfoo test case; raise ValueError naming a bad file."""
    path = pathlib.Path(path)
    parts = re.split(r"^## +(.+?) *$", path.read_text(encoding="utf-8"), flags=re.M)
    sections = dict(zip(map(str.lower, parts[1::2]), parts[2::2]))

    messages = []
    for line in quoted(sections.get("earlier turns", "")):
        turn = ROLE.fullmatch(line)
        if turn:
            messages.append({"role": turn[1].lower(), "content": turn[2]})
        elif messages:
            messages[-1]["content"] += "\n" + line
        else:
            raise ValueError("%s: Earlier turns must start with 'User:' or 'Assistant:'" % path.name)
    if "earlier turns" in sections and not messages:
        raise ValueError("%s: Earlier turns has no quoted turn" % path.name)

    user_input = "\n".join(quoted(sections.get("user input", ""))).strip()
    if not user_input:
        raise ValueError("%s: no quoted text under '## User input'" % path.name)
    messages.append({"role": "user", "content": user_input})

    for line in sections.get("pass criteria", "").splitlines():
        if line.strip() and not line.startswith(("- ", " ", "\t")):
            raise ValueError("%s: line under '## Pass criteria' is neither a '- ' bullet "
                             "nor an indented continuation: %r" % (path.name, line))
    criteria = [" ".join(bullet.split()) for bullet in
                re.findall(r"^- +(.+(?:\n[ \t]+\S.*)*)", sections.get("pass criteria", ""), flags=re.M)]
    if not criteria:
        raise ValueError("%s: no bullet under '## Pass criteria'" % path.name)

    # The judge sees only the reply and the rubric, so the rubric carries the conversation.
    conversation = "\n\n".join("%s: %s" % (m["role"].capitalize(), m["content"]) for m in messages)
    return {
        "description": path.stem,
        "vars": {"messages": messages},
        "assert": [{
            "type": "llm-rubric",
            "metric": "%s.%d" % (path.stem, number),
            "value": "%s\n\nThe reply being graded answers the last message of this conversation:\n\n%s"
                     % (criterion, conversation),
        } for number, criterion in enumerate(criteria, 1)],
    }


def generate_tests():
    return [parse(path) for path in sorted(SCENARIOS.glob("[0-9][0-9]_*.md"))]
