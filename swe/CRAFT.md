# Craft

How to tell adequate work from excellent work in the three jobs an
engineer does: building, reviewing and designing. The five protocols say
what to do and what to avoid. This file is a reference, read on demand:
open the part for the job in hand. Sources are at the end.

## Building

A simple design, in priority order. When two of these pull against each
other, the earlier one wins.

1. It works, and a check shows it.
2. It says what it means. A reader new to the file can tell what each
   name is for and why each branch exists.
3. Each piece of knowledge lives in one place.
4. Nothing is there that the first three do not need.

| Question | Adequate | Excellent |
|---|---|---|
| Does it fit what is already here? | Follows the conventions nearby | Reuses the existing mechanism, or changes it once, where a second one would have been added |
| Is the interface smaller than what it hides? | Callers pass what the function needs | The common case needs no options, and a caller cannot use it wrongly |
| What happens when it fails? | Errors surface at the boundary | The design leaves fewer ways to fail; nothing is swallowed or defaulted away |
| Do the names carry the meaning? | Accurate | State the intent, so no comment is needed to explain what |
| Is the change one thing? | One concern per change | An awkward change is split: first make it easy with no change in behaviour, then make it |
| Is it proven? | The checks pass | The check was seen to fail before the change, and would fail again if the behaviour broke |

Habits that matter most when an agent is doing the building:

- Search before you write. Find what already does the job. Models add
  and copy far more readily than they move, change or delete, which is
  how duplicate code piles up.
- Decide the check before the first edit: the test, command or
  screenshot that will show the need is met.
- After two failed attempts at the same fix, stop patching. Write down
  what is now known and start again from that, in a fresh session if
  this one is full of dead ends.
- Keep the context for the task. Send wide searches to a subagent, and
  hand a reviewer the evidence, never your conclusion.

## Reviewing

Read a change in this order. Report an earlier problem first, and leave
unpolished what its fix would rewrite.

1. Design. Does the change belong here, and does it fit the system
   around it?
2. Behaviour. Does it do what the request needs, for its user and for
   the next developer, in the failure and edge cases too?
3. Complexity. Can a reader follow it quickly? Is anything built for a
   need that does not exist yet?
4. Tests. Would they fail if the code were wrong? Do they pin what the
   code does for its caller, or only how it is written?
5. Names, comments and docs. Do comments say why? Is what a user must
   know written where they will look?
6. Context. Read the whole file around each change, since a diff hides
   what it leaves broken beside it.

| Part of a review | Adequate | Excellent |
|---|---|---|
| A finding | Says something could break | Names the input, the line, the consequence and the smallest fix, and was checked before it was reported |
| Judgement | Lists what was noticed | Separates what must change from what is taste, and says the change is good enough when it is |
| A comment | Says what is wrong | Says why, speaks about the code and never the author, and leaves the choice of fix to the author unless one fix is plainly right |
| An explanation from the author | Accepted in the thread | Put into the code or the commit message when a later reader will need it |
| Coverage | Read the diff | Says what was read, what was run and what was not checked |

The standard for approval is that the change leaves the code better
than it found it. A change that does that is approved even when it is
not how the reviewer would have written it.

## Designing

Use this when a plan has more than one workable approach, or a choice
that is hard to undo.

- State the problem before any solution: who needs it and what goes
  wrong today. Then the goals, and the non-goals, which are things that
  could reasonably have been goals and were left out on purpose.
- Design it twice. Sketch two approaches that really differ and say what
  each costs. A design with no alternative is an announcement.
- Prefer the design that hides more behind less: a small interface over
  a deep implementation.
- Spend effort by how hard the choice is to undo. For a choice that is
  cheap to reverse, pick and move. For a data model, a public interface,
  an auth model or a vendor, write down the context, the decision, what
  follows from it and the alternatives you rejected.
- Build for the next change you can name. A layer added for a future
  nobody has asked for is cost with no user.

Warning signs in a design:

- The same decision is known in two modules, so one cannot change
  without the other.
- A caller has to understand how another module works inside to use it.
- A layer only passes calls through.
- A name is hard to choose, which usually means the thing does two jobs.
- Code is split by the order things happen in, when the split should
  follow what each part needs to know.

| Part of a design | Adequate | Excellent |
|---|---|---|
| The problem | Described | A reader can tell what success is and what was left out |
| The options | One, explained | Two or more that really differ, with the cost of each |
| The choice | Works | The reason names the trade-off accepted, and what would make the other option right |
| Reversibility | Not mentioned | Says how hard the choice is to undo, and puts the care there |

## Sources

- Google, Engineering Practices: the standard of code review, what to
  look for in a review, and how to write review comments.
  https://google.github.io/eng-practices/
- Martin Fowler, "Beck Design Rules", on Kent Beck's four rules of
  simple design. https://www.martinfowler.com/bliki/BeckDesignRules.html
- John Ousterhout, A Philosophy of Software Design: deep modules,
  information hiding, design it twice and the warning signs.
- Malte Ubl, "Design Docs at Google": goals, non-goals, trade-offs and
  alternatives considered.
  https://www.industrialempathy.com/posts/design-docs-at-google/
- Michael Nygard, "Documenting Architecture Decisions": context,
  decision, consequences.
- Anthropic, "Best practices for Claude Code": a way to verify the work,
  explore then plan then code, and starting clean after failed
  corrections. https://code.claude.com/docs/en/best-practices
- GitClear, AI Copilot Code Quality reports: more copied code and less
  refactoring as assistants spread. A vendor study, read with that in
  mind.
