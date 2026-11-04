---
name: drill
description: A drill of new, unlabelled problems mixed across every technique note, weighted to weak ones — for each, name the technique first, then solve it; misses are retested at the end in a new setting. Use with `/drill [n]`, or when the learner asks for a drill or mixed practice.
argument-hint: [n]
allowed-tools: Bash(python3 .claude/hooks/practice.py *), Bash(python3 .claude/hooks/md_log.py *), Bash(python3 .claude/hooks/technique.py *), Write
---

Arguments: `$ARGUMENTS`

A drill trains what an interview tests and a lesson cannot: recognising which trick a problem needs when nothing says so. Each problem is asked twice: **which technique?**, then **solve it**. The two are scored separately, so the learner sees whether they missed the trick or the working. The teach skill's *Practice rules* hold throughout: checked problems, fresh surfaces, hint levels, kinds of miss.

1. **Plan the drill** (n is the argument, default 8):
   ```
   python3 .claude/hooks/practice.py drill --n <n>
   ```
   If it refuses for want of technique notes, say in one sentence that `/techniques backfill` makes them, and stop. Otherwise it prints the drill id, the problem file's path, and per slot the technique, its demand, its trick and cues, the problems already used for it, and three wrong options. The script picks each demand: a technique meets recall first, then discrimination, then composition, moving on once it has been named and solved cleanly at a demand. The slots are already interleaved: keep their order.
2. **Write the problem file** with the Write tool, at the `PROBLEMS` path:
   ```json
   {"problems": [{"slot": 1, "statement": "…", "answer": "1/4", "variables": {}, "answerLatex": "\\frac14",
                  "solution": "<a worked solution, a few lines>"}]}
   ```
   - One problem per slot, on the slot's technique, solvable in a few minutes, shaped by its **demand**:
     - `recall`: one or two decision points, in a setting the learner has not seen the technique in.
     - `discrimination`: a problem that looks like one for its `near twin`, where a single feature of the statement decides between the two techniques. The twin is one of the wrong options.
     - `composition`: a short chain of results run as a whole, with the slot's technique as one link.
   - On one or two slots, use a template where it fits: **reverse** (give the conclusion, ask for the grounds: the parameter, condition or count that makes it true) or **weaken a premise** (drop or change one assumption of a known result, and ask for what follows now).
   - **A setting unlike every problem listed as already used**, and unlike the trick's textbook examples: the point is that the surface does not give the technique away. Do not use the technique's name, or words from its cues, in the statement.
   - The answer is a number or a formula in the typed-answer syntax, with every variable's range in `variables`.
   - **Check every problem** as *Practice rules* say: solve it, run code on the answer (simulate any probability or expectation), and look for a route that skips the technique. Fix or replace a problem that has one.
3. **Validate:** `python3 .claude/hooks/practice.py drill-check <id>`; fix the file for each line it prints until it says `🗒 drill ready`.
4. **Link today's practice note:**
   ```
   python3 .claude/hooks/md_log.py link "practice/<today, YYYY-MM-DD>.md" --session ${CLAUDE_SESSION_ID} --from-now
   ```
   The reply is the heading `### Drill <id>` and one line: `<n> problems. For each: name the technique, then solve it.` Then the first quiz.
5. **For each slot, two quizzes, with no lead-in text:**
   - **Which technique does this problem need?** The statement in the question. Options: the slot's technique and its three wrong options, as bare names (`shuffle` left on). The explanation names the trick and quotes the feature of *this* statement that signals it.
   - **Solve it.** A typed quiz: the statement again, `answer`, `answerLatex`, two or three `wrongAnswers` from the common wrong moves, and the solution as the explanation. Ask it even when the technique was missed. A question sent with `?` before answering gets a hint at the lowest level that helps (*Hint levels*), and the quiz again.
   - Then record both: `python3 .claude/hooks/practice.py drill-result <id> <slot> --recognised right|wrong [--picked "<the name they chose>"] --solved right|wrong [--miss <kind>] [--hint <level>] [--confidence <the solve quiz's>]`. A wrong part needs `--miss`, the kind of miss; `--hint` is the highest level given. Write nothing about the call.
6. **Retests:** `python3 .claude/hooks/practice.py drill-retests <id>`. For each `RETEST` line, one new typed quiz on the same technique and demand, in a setting unlike the problem it replaces, checked as in step 2. Head the first with `#### Retests` and one line: `<k> retests: the problems missed or hinted, in new settings.` Record each: `python3 .claude/hooks/practice.py drill-retest <id> <slot> right|wrong [--miss <kind>]`. On `NO RETESTS`, go to the close.
7. **Close:** `python3 .claude/hooks/practice.py drill-summary <id>`. The last reply gives its first line, the kinds of miss, each confusion it lists, and one sentence on the pattern if there is one (the same pair confused twice, every miss of one kind, or every miss on solving rather than naming). Misses come back in `/review`.

No narration of tool calls; everything written is mirrored into the practice note.
