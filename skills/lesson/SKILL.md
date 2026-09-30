---
name: lesson
description: Multi-session lessons. `/lesson resume <file>` links the markdown lesson log, reads only its checkpoint + dependency map + recent quiz outcomes, re-probes what was established, and continues teaching. `/lesson pause` writes a checkpoint block so the next session can pick up cleanly. `/lesson status <file>` shows where a lesson stands without teaching.
argument-hint: resume <lesson.md> | pause | status <lesson.md>
disable-model-invocation: true
allowed-tools: Bash(python3 .claude/hooks/md_log.py *), Bash(python3 .claude/hooks/lesson.py *)
---

Arguments: `$ARGUMENTS`

Load the `teach` skill first if it is not already loaded — everything below runs inside its process and principles.

## `resume <file>`

1. Link the log so this session appends to the same note:
   ```
   python3 .claude/hooks/md_log.py link "<file>" --session ${CLAUDE_SESSION_ID}
   ```
2. Get the resume brief — this is the ONLY part of the lesson file you read; do not open the whole file:
   ```
   python3 .claude/hooks/lesson.py summary "<file>"
   ```
3. **New lesson** (no file / empty): say so in one line and start the teach process from Phase 1 (probe).
4. **Existing lesson:** in a few sentences, tell the learner where things stand — the goal, which nodes are confirmed, which were shaky or missed, and what comes next — using the latest checkpoint. If there is no checkpoint, reconstruct this from the map, the quiz outcomes and the tail, and **confirm your reading with the learner** (`ask_user_question`) before going on. If the brief says the session continued past the checkpoint, fold the tail into your reading.
5. **Re-probe before building.** Nodes established last time are only as solid as they are *today*. Run a short retrieval check — 2 to 4 `quiz` questions — over the confirmed nodes, prioritising anything listed as shaky or missed and the node(s) the next step depends on. Same construction rules as always. Anything that fails is re-established (motivate → establish → connect → quiz-check) before you move on.
6. Then continue the Phase 3 loop from the checkpoint's **Next** node. Re-present the dependency map only if it changed.

## `pause`

The learner is stopping. Write a checkpoint **as the last thing in your reply** (the md-log hook mirrors your reply into the lesson file, so this lands in the note). Use exactly this shape so the next session can find it:

```
> [!summary] Checkpoint — <YYYY-MM-DD>
> **Goal:** <the concrete goal from Phase 1b>
> **Confirmed nodes:** <node — one line each, quiz-checked this or a previous session>
> **Shaky / missed:** <node — what went wrong, the misconception if you found one; or "none">
> **Next:** <the next node from the map, and the motivating problem you planned to open it with>
> **Notes:** <energy, Socratic vs expository preference, anything the next teacher needs>
```

Keep it under ~15 lines; it is a handoff, not a summary of the lesson. Before the block, one sentence to the learner is enough. Do **not** unlink the log.

If you have not been asked to `pause` but the learner says they are stopping, wrapping up, or continuing another day, write the same checkpoint anyway.

## `status <file>`

Run the summary script (step 2 above) and report where the lesson stands in a few lines. Do not link, probe or teach.
