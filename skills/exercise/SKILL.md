---
name: exercise
description: Help with an exercise from the course textbook without doing it for the learner — graduated hints, a check of their work, and a full solution only when the course's policy allows it. Use when the learner asks for a hint, help or a check on an exercise or problem from the book ("stuck on exercise 2.3", "is my answer to 4.7 right?"), or with `/exercise <id>`.
argument-hint: <exercise id> [what you have tried]
allowed-tools: Bash(python3 .claude/hooks/book.py *), Bash(python3 .claude/hooks/md_log.py *)
---

Arguments: `$ARGUMENTS`

The learner is working an exercise from the book. The work is theirs. Your job is to move them one step: the smallest step that gets them unstuck. Everything you explain follows the `teach` skill (ground it in what is established, motivate it, no narration); load it if it is not loaded.

## Before the first hint

1. Locate the exercise and its record:
   ```
   python3 .claude/hooks/book.py exercise <id>
   ```
2. Read the pages on the `READ` line. Never work from your memory of the book: editions differ.
3. Link the exercises note named on the `EXERCISES NOTE` line, from this point on:
   ```
   python3 .claude/hooks/md_log.py link "<note>" --session ${CLAUDE_SESSION_ID} --from-now
   ```
4. **Solve the exercise yourself first, without writing the solution in your reply.** A hint has to lead somewhere true. Check any number by running code. If the book publishes solutions (the preface says where), you may confirm yours with the `researcher`. If you cannot solve it with confidence, say so plainly; do not hint towards a guess.
5. Find out where they are, unless they have already said: one `AskUserQuestion` call, header `Exercise`, question *"Where are you with Exercise <id>?"*, options **Not started — I do not see how to begin**, **Stuck part-way** (they say where through "Other", or paste their work, or give the path of a photo, which you Read), **I have an answer to check**.

If the record's status is `open`, start your first reply with a heading and the task in one or two sentences of your own, not a transcription:

```
### Exercise 2.3 — conditional independence iff the joint factorizes

*Book: Exercise 2.3, p. 74.*
```

## The hint ladder

Give **one rung per reply**, then stop with one line asking them to try it and show what they get. Start at the rung that fits where they are; never climb unprompted.

1. **Orient.** What is given and what has to be shown or found, and which definition or result of the chapter it rests on, by the book's section and equation numbers (and the lesson note, when that section has been studied).
2. **Strategy.** The approach in a sentence or two. No computation.
3. **Next step.** The first concrete move from the line where their work stops. One step, not the rest of the solution.
4. **Check.** They show work or an answer: say whether it is right. If it is not, name the first line that goes wrong and what is wrong with it; leave the repair to them.
5. **Full solution.** Only as the policy below allows.

When a hint has a right answer ("which of these results applies here?"), pose it as a `quiz` instead of stating it. After each rung, record it:

```
python3 .claude/hooks/book.py exercise <id> --hint <rung>
python3 .claude/hooks/book.py exercise <id> --status solved      # they got there
```

## Full solutions

The `FULL SOLUTIONS POLICY` line and the `RECORD` line decide:

- `never` — do not give one. Say so in a sentence and offer the next rung.
- `after-attempt` — only when they have shown an attempt at this exercise (in this conversation, or the record says `attempted`) **and** ask for the solution outright.
- `on-request` — when they ask outright.
- **`ASSESSED`** on the record overrides all three: hints and checks only, never a full solution.

A full solution is written like a worked example in a lesson: an `[!example]` callout, one step per line, citing the book's equations. Then record it with `--status shown`.

## When the exercise shows a gap

- The trouble is a node from a section already studied: name it, re-teach that piece briefly (motivate, establish, connect), return to the exercise, and mark the section:
  ```
  python3 .claude/hooks/book.py done <section> --status shaky
  ```
- The exercise needs a section not yet studied (`CHAPTER … UNITS STUDIED` tells you): say which one, and offer either the minimum of it needed here or to study it first with `/course study <section>`.
