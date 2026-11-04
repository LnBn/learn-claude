---
name: review
description: Spaced review of past misses — every missed lesson quiz, exam question, interview or drill problem is a card that comes back after 1, 3, 7, 16 and 35 days, each time as a new variant of its idea. Use with `/review`, or when the learner asks to review their misses or for spaced repetition.
allowed-tools: Bash(python3 .claude/hooks/practice.py *), Bash(python3 .claude/hooks/md_log.py *), Bash(python3 .claude/hooks/lesson.py *)
---

A card is one miss. `practice.py` finds misses by scanning the notes, exams, interviews and drills, and schedules each card: right moves it to the next interval (1 → 3 → 7 → 16 → 35 days, then it retires), wrong brings it back tomorrow. A lesson quiz answered right at 40% confidence or less is a **fragile** card: it comes back once, and one sure right answer retires it. You write the questions; the script keeps the schedule. The teach skill's *Practice rules* hold throughout.

1. **What is due:**
   ```
   python3 .claude/hooks/practice.py due --limit 10
   ```
   It prints misconceptions first, then misses made at 80% confidence or more, then the rest, oldest due first. A `last miss` line gives the kind of the last miss and its confidence; a `fragile` line marks a fragile card.
   On `NO CARDS DUE`, run `python3 .claude/hooks/practice.py stats` and reply with one line: nothing is due, and the `next due` date and count it prints. Link nothing, and stop.
2. **Link today's practice note** and open the section:
   ```
   python3 .claude/hooks/md_log.py link "practice/<today, YYYY-MM-DD>.md" --session ${CLAUDE_SESSION_ID} --from-now
   ```
   The reply starts with the heading `### Review`, then the first question.
3. **For each card, in the order printed, one `quiz`:**
   - **A new variant of the card's idea,** never the original prompt: the same idea in a different setting, or the original setting with one crucial change, as the teach skill's transfer rule says (Phase 3, step 4). The prompt, the key ideas and the techniques printed with the card tell you what the idea is. Check it for shortcuts before you pose it (*Checked problems*).
   - A typed quiz when the answer is a number or a formula; otherwise multiple choice, built with the teach skill's option rules. Verify any number by running code first.
   - The question names nothing that gives the idea away: no section, no technique, no "recall that…".
   - The explanation says why the answer is right and ends with the source, as printed: `From [[<source>|<label>]].`
   - After the result, record it with the quiz's confidence:
     ```
     python3 .claude/hooks/practice.py result <card> right --confidence <n>
     python3 .claude/hooks/practice.py result <card> wrong --miss <kind> --confidence <n>
     ```
     "I don't know" is wrong, with no confidence. `<kind>` is the kind of miss (*Practice rules*). Write nothing about the call. Then the next card's quiz, with no lead-in text.
   - **A misconception** (a `misconception` card missed again, or a wrong answer given at 80% or more) gets a nudge before the next card, as *Kinds of miss* says, not a re-taught lesson: two or three sentences that point at the belief and give a case to test it on. End the reply there. When they answer, go on to the next card; state the correction only if they cannot find it. Any other miss: the explanation in the popup is the whole response.
   - A question asked with `?` in the popup, or a quiz moved to the background, is handled as the teach skill says.
4. **Close:** run `python3 .claude/hooks/practice.py stats` and end with one line: `Reviewed <k>: <r> right. Next due: <date> (<m> cards).`, the date and count from its `next due` line.

No narration of tool calls; everything written is mirrored into the practice note.
