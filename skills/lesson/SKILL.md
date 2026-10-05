---
name: lesson
description: Multi-session lessons. `/lesson resume <file>` links the markdown lesson log, reads only its checkpoint + dependency map + recent quiz outcomes, re-probes what was established, and continues teaching. `/lesson pause` writes a checkpoint block so the next session can pick up cleanly. `/lesson status <file>` shows where a lesson stands without teaching. `/lesson reset <file>` starts a lesson over (note and checkpoints moved to trash).
argument-hint: resume <lesson.md> [--notes <note.md>] | pause | status <lesson.md> | reset <lesson.md>
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
   python3 .claude/hooks/lesson.py summary "<file>" [--notes "<note.md>"]
   ```
   A hand-off note (`--notes`, or a `<stem> — Resume Here.md` file found automatically next to the lesson) is
   printed in full and counts as the checkpoint. Logs written by pi's md-log (with `PI` blocks and its quiz
   callouts) are understood too — resuming a pi-era lesson is the same command.
3. **New lesson** (no file / empty): start the teach process from Phase 0 (the opener, as its own reply).
4. **Existing lesson:** follow **Resuming a lesson** in the teach skill: the `Resume` question, the optional recall check, then the checkpoint's **Next**. If the learner stopped after reading a node, the session re-opens with a pointer back to that reading, not with its quiz.

## `pause`

The learner is stopping. Save a checkpoint **outside the note** — the note is clean lesson material; checkpoints live in a hidden sidecar the next session reads. Run one Bash command with the checkpoint on stdin (the lesson file is the one linked with `/md-log` or `/lesson resume` this session):

```
python3 .claude/hooks/lesson.py checkpoint "<lesson.md>" <<'EOF'
**Goal:** <the concrete goal from Phase 1b>
**Confirmed nodes:** <node — one line each, quiz-checked this or a previous session>
**Shaky / missed:** <node — what went wrong, the misconception if you found one; or "none">
**Next:** <the next node from the map, and the motivating problem you planned to open it with; if its exposition is already written and unchecked, say so — the next session has the learner re-read it before its check>
**Notes:** <energy, Socratic vs expository preference, anything the next teacher needs>
EOF
```

Keep it under ~15 lines; it is a handoff, not a summary of the lesson. Then reply with only the line the script printed (it starts with `🗒`), nothing else. Do **not** unlink the log.

If you have not been asked to `pause` but the learner says they are stopping, wrapping up, or continuing another day, save the same checkpoint anyway.

## `reset <file>`

The learner wants to start this lesson over. Run:

```
python3 .claude/hooks/lesson.py reset "<file>"
```

It moves the note and its sidecar checkpoints to `.claude/md-log-state/trash/<timestamp>/` (recoverable). Reply with only the `🗒` line the script printed. Do not start teaching; the learner will begin the lesson with a fresh `/md-log` or a teach request.

## `status <file>`

Run the summary script (step 2 above) and report where the lesson stands in a few lines. Do not link, probe or teach.
