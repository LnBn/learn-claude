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
4. **Existing lesson:** ask, with one `AskUserQuestion` call and **nothing else in the reply** (no prose before or after — the note must not show this exchange, and the hook drops questions with this header):
   - `header`: exactly `Resume`
   - `question`: one or two sentences of orientation (the goal, the last confirmed node, what comes next per the latest checkpoint or hand-off note; the newer wins; ignore tooling notes about another harness) followed by: *"Run a short recall check on what was established before continuing?"*
   - options: **Continue where we left off** — pick up at the next node, no recall check; **Recall check first** — 2 to 4 quizzes on the established nodes, then continue.
   If there is no checkpoint and no hand-off note, add a third option **Let me say where we got to** and reconstruct the state from the map, quiz outcomes and tail with their answer before going on.
5. **Continue where we left off** → say nothing about the choice; go straight to step 6. **Recall check first** → run a short retrieval check — 2 to 4 `quiz` questions — over the confirmed nodes, prioritising anything listed as shaky or missed and the node(s) the next step depends on. Anything that fails is re-established (motivate → establish → connect → check) before you move on.
6. Then continue the Phase 3 loop from the checkpoint's **Next** node. Re-present the dependency map only if it changed.

## `pause`

The learner is stopping. Save a checkpoint **outside the note** — the note is clean lesson material; checkpoints live in a hidden sidecar the next session reads. Run one Bash command with the checkpoint on stdin (the lesson file is the one linked with `/md-log` or `/lesson resume` this session):

```
python3 .claude/hooks/lesson.py checkpoint "<lesson.md>" <<'EOF'
**Goal:** <the concrete goal from Phase 1b>
**Confirmed nodes:** <node — one line each, quiz-checked this or a previous session>
**Shaky / missed:** <node — what went wrong, the misconception if you found one; or "none">
**Next:** <the next node from the map, and the motivating problem you planned to open it with>
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
