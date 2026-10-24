---
name: techniques
description: Technique notes — one note per problem-solving trick in `techniques/`, each with its cues, traps and every problem that used it. Use with `/techniques list`, `/techniques sync`, `/techniques backfill [course]`, when the learner asks about technique notes or to tag finished chapters, and (from the teach and interview skills) whenever a technique note is written.
argument-hint: list | sync | backfill [course]
allowed-tools: Bash(python3 .claude/hooks/technique.py *), Bash(python3 .claude/hooks/md_log.py *), Bash(python3 .claude/hooks/book.py *), Write, Edit
---

Arguments: `$ARGUMENTS`

A technique note collects one trick: what it is, the cues in a problem that should make the learner reach for it, its traps, and every problem that used it with the learner's record. The tags live in the notes: a lesson section closes with `*Techniques: [[Symmetry]] · [[Linearity of expectation]]*`, and an interview problem has a `techniques` list. `technique.py` reads them and writes only the problems block of each note and the index `techniques/Techniques.md`.

| Arguments | Section |
|---|---|
| `list` | `python3 .claude/hooks/technique.py list`; show the output |
| `sync` | `python3 .claude/hooks/technique.py sync`; reply with the `🗒` line |
| `backfill [course]` | **Backfill** |

## Writing a technique note

Before writing one, run `python3 .claude/hooks/technique.py list`. Reuse an existing name or alias when the trick is the same one; write a new note only for a genuinely different trick. Write it with the Write tool at `techniques/<Name>.md`, where `<Name>` is the canonical name (letters, digits, spaces, hyphens, apostrophes; capitalised like a title: `Linearity of expectation`).

```markdown
---
technique: <Name>
aliases: [<other names the learner or a book uses>]
---
# <Name>

> [!definition] The trick
> <the trick stated in general, two or three sentences: what you do and why it works. Not this problem's version of it.>

## Reach for it when

- <a feature a problem statement can have that signals this trick>
- <two to four of these>

## Traps

- <where the trick fails or is misapplied>

## Related

- [[<another technique>]] — <how the two connect, in a clause>

## Problems

%% problems: written by technique.py sync; edits inside are replaced %%
%% /problems %%
```

- Cues are phrased as what the learner can *see* in a new problem ("the players are interchangeable", "the question asks for an expected count"), never as the method.
- Tags and links use the canonical name only. Obsidian does not resolve a raw link to an alias; `technique.py` does, but the note's own links should not rely on it.
- Never edit inside the problems block, and never edit the learner's items under `**In your words:**`. Add a trap or a cue the note lacks with the Edit tool when a later problem shows one.
- After writing a note, run `python3 .claude/hooks/technique.py sync`.

## Backfill

Tags the finished units of a course that were taught before technique notes existed. Once per course.

1. **Stop mirroring:** `python3 .claude/hooks/md_log.py unlink --session ${CLAUDE_SESSION_ID}`. The backfill is not lesson content.
2. **Read what was taught:** `python3 .claude/hooks/technique.py list`, then `python3 .claude/hooks/book.py status` for the finished units, and `python3 .claude/hooks/technique.py sections <chapter note>` for each chapter note with finished units. Read a section's text in the note only when its key idea does not settle which trick it used.
3. **Propose the tags** in one table, one row per section: the section (`§2.4.1 Coin piles`), its techniques (existing names reused; a new one marked *new*). Most sections use one or two techniques; a section that teaches a definition and uses no trick gets none. Then one `AskUserQuestion` (header `Techniques`): *"Tag the sections like this?"*, options **Looks right** and **Let me correct it** (their corrections come through "Other"). Apply the corrections.
4. **Write a note for every new technique**, as in **Writing a technique note**. No cue question here: the learner's own cues are asked the next time each technique comes up in a lesson.
5. **Tag:** `python3 .claude/hooks/technique.py tag "<chapter note>" "<heading>" <Name>...` for each section (the heading as `sections` printed it, without `### `). Reply with the `🗒` line of the last `tag`, and a link to `[[Techniques]]`.
