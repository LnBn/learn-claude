---
name: drill
description: A drill of new, unlabelled problems mixed across every technique note, weighted to weak ones — for each, name the technique first, then solve it. Use with `/drill [n]`, or when the learner asks for a drill or mixed practice.
argument-hint: [n]
allowed-tools: Bash(python3 .claude/hooks/practice.py *), Bash(python3 .claude/hooks/md_log.py *), Bash(python3 .claude/hooks/technique.py *), Write
---

Arguments: `$ARGUMENTS`

A drill trains what an interview tests and a lesson cannot: recognising which trick a problem needs when nothing says so. Each problem is asked twice: **which technique?**, then **solve it**. The two are scored separately, so the learner sees whether they missed the trick or the working.

1. **Plan the drill** (n is the argument, default 8):
   ```
   python3 .claude/hooks/practice.py drill --n <n>
   ```
   If it refuses for want of technique notes, say in one sentence that `/techniques backfill` makes them, and stop. Otherwise it prints the drill id, the problem file's path, and per slot the technique, its trick and cues, the problems already used for it, and three wrong options.
2. **Write the problem file** with the Write tool, at the `PROBLEMS` path:
   ```json
   {"problems": [{"slot": 1, "statement": "…", "answer": "1/4", "variables": {}, "answerLatex": "\\frac14",
                  "solution": "<a worked solution, a few lines>"}]}
   ```
   - One problem per slot, on the slot's technique, solvable in a few minutes.
   - **A setting unlike every problem listed as already used**, and unlike the trick's textbook examples: the point is that the surface does not give the technique away. Do not use the technique's name, or words from its cues, in the statement.
   - The answer is a number or a formula in the typed-answer syntax, with every variable's range in `variables`.
   - **Verify every answer by running code**: compute it, and simulate any probability or expectation.
3. **Validate:** `python3 .claude/hooks/practice.py drill-check <id>`; fix the file for each line it prints until it says `🗒 drill ready`.
4. **Link today's practice note:**
   ```
   python3 .claude/hooks/md_log.py link "practice/<today, YYYY-MM-DD>.md" --session ${CLAUDE_SESSION_ID} --from-now
   ```
   The reply is the heading `### Drill <id>` and one line: `<n> problems. For each: name the technique, then solve it.` Then the first quiz.
5. **For each slot, two quizzes, with no lead-in text:**
   - **Which technique does this problem need?** The statement in the question. Options: the slot's technique and its three wrong options, as bare names (`shuffle` left on). The explanation names the trick and quotes the feature of *this* statement that signals it.
   - **Solve it.** A typed quiz: the statement again, `answer`, `answerLatex`, two or three `wrongAnswers` from the common wrong moves, and the solution as the explanation. Ask it even when the technique was missed.
   - Then record both: `python3 .claude/hooks/practice.py drill-result <id> <slot> --recognised right|wrong [--picked "<the name they chose>"] --solved right|wrong`. Write nothing about the call.
6. **Close:** `python3 .claude/hooks/practice.py drill-summary <id>`. The last reply gives its first line, each confusion it lists, and one sentence on the pattern if there is one (the same pair confused twice, or every miss on solving rather than naming). Misses come back in `/review`.

No narration of tool calls; everything written is mirrored into the practice note.
