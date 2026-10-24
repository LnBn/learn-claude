# Practice: `/drill` and `/review` — design

Date: 2026-10-24. Status: approved in conversation, awaiting spec review.

## Purpose

Lessons teach one section at a time, so the learner always knows which idea a question is about. An interview gives no such label, and what was learned and then missed fades unless it comes back. Two practice modes close those gaps:

- **`/drill`** — a set of new problems mixed across every technique, unlabelled. For each, the learner first names the technique it needs, then solves it. Recognition and solving are scored separately.
- **`/review`** — every miss (a lesson quiz, an exam question, an interview or drill problem) becomes a card that comes back at growing intervals, each time as a new variant of its idea.

This is the fourth of five planned pieces (typed answers, mock interview, technique notes, practice, mental arithmetic).

**Said by the learner:** the course goal is to solve unseen problems fast; questions should exercise the same trick in different settings.

**Agreed in the design conversation:**

- A drill: about 8 problems; for each, "Which technique?" (a pick from the learner's technique notes), then a typed answer. Scored separately.
- Drill problems are weighted towards weak techniques, with a few strong ones so the mix stays unpredictable. Every problem is new, in a setting different from those already seen.
- Review: every miss becomes a card. It comes back after 1 day; each right answer grows the gap (1 → 3 → 7 → 16 → 35 days) and after the last it retires; a wrong answer sends it back to 1 day. At most about 10 cards a session.
- Misses from before practice existed become cards too, their first due dates spread over the next two weeks.
- Approach: a script (`hooks/practice.py`) finds misses by scanning what already exists (quiz blocks in notes, graded exams, finished interview rounds, drill results), as `technique.py` scans tags. Nothing depends on the model registering a miss.

**Assumed and not contradicted:** recall checks at the start of a resumed lesson stay as they are; nothing starts unasked; no reminders outside Claude Code.

## Cards

A card is one miss. Cards live in `<vault>/practice/.cards.json`:

```json
{"cards": [
  {"id": "c12", "key": "quiz:gb-ch02#2.4.1 Coin piles#3fa2c1d0", "kind": "quiz",
   "source": "gb-ch02#2.4.1 Coin piles", "label": "§2.4.1 Coin piles",
   "section": "gb-ch02#2.4.1 Coin piles", "techniques": ["Symmetry"],
   "prompt": "<the original question>", "missed": "2026-10-23",
   "step": 0, "due": "2026-10-24", "status": "active",
   "history": [{"date": "2026-10-24", "result": "right"}]}
]}
```

**Where misses come from** (`practice.py scan`):

| Kind | A miss is | Key | Missed on | Section, techniques |
|---|---|---|---|---|
| `quiz` | a graded quiz block marked `✗` or `?` in a lesson or review note | `quiz:<stem>#<heading anchor>#<first 8 hex of sha1 of the quiz title>` | the newest `## Session — <date>` above it | the `###` section it is in; that section's techniques (`technique.py` tags) |
| `exam` | a question in the `misses` of a graded exam scheme | `exam:<paper stem>#<question id>` | the scheme's graded date, else its set date | the question's `section`; that section's techniques |
| `interview` | a problem `hinted` or `unsolved` in a finished round | `interview:<round stem>#p<i>` | the round's date | none; the problem's `techniques` |
| `drill` | a drill problem with recognition or solving wrong | `drill:<drill id>#<slot>` | the drill's date | none; the slot's technique |

- Scanned for quiz blocks: every `.md` under the vault except under `.claude/`, `.obsidian/`, `techniques/`, `practice/` and any `exams/` or `interviews/` folder. Review notes (`*-review.md`, `* — Review.md`) **are** scanned: a recall-check miss is a miss. Quiz blocks inside fenced code are not read.
- A key seen before is never added again, whatever happened to its card. A quiz re-asked with the same title in the same section is the same card.
- The prompt is the question as written in the block (the full question when its title was cut), the exam question's text, or the problem's statement.
- **First scan** (no `.cards.json` yet): every miss found becomes a card, oldest first, and their due dates are spread evenly over the 14 days after today (`today + 1 + floor(k × 14 / N)` for the k-th of N). **Later scans:** a new card is due the day after it was missed, or today if that day has passed.
- Card ids are `c1`, `c2`, … in the order cards were created.

**Scheduling.** `INTERVALS = [1, 3, 7, 16, 35]` days. A new card is at step 0.

- **Right:** step + 1. If that passes the last interval, the card is `retired`; otherwise it is due `today + INTERVALS[step]`.
- **Wrong** (or "I don't know"): step 0, due tomorrow.
- A card is **due** when `due <= today` and it is `active`.

## `/review`

1. Link today's practice note (below) and write the heading `### Review`.
2. `practice.py due --limit 10` scans, then prints the due cards, oldest due date first: id, kind, label and source link, techniques, the original prompt, and the key ideas of its section (when it has one).
3. For each card, the teacher writes a **new variant** of the card's idea: the same idea in a different setting, or the original setting with one crucial change (the teach skill's transfer rule). Never the original question.
   - A typed quiz when the answer is a number or a formula, otherwise multiple choice, built as the teach skill's quiz rules say.
   - The question names nothing that gives the idea away (no section, no technique). The explanation, shown after the answer, ends with the source: `From [[gb-ch02#2.4.1 Coin piles|§2.4.1]].`
   - `practice.py result <card> right|wrong` after each answer.
4. After the last card: one line, `Reviewed <k>: <r> right. Next due: <date> (<m> cards).`, from `practice.py stats`.

With no card due, the reply says so with the next due date, and nothing is linked.

## `/drill [n]`

`n` defaults to 8.

1. Link today's practice note and write the heading `### Drill <id>`.
2. `practice.py drill --n <n>` creates the drill (id `<date>-<k>`, the k-th drill of the day) and prints, for each slot:
   - the technique, its trick (the `The trick` callout of its note) and its cues (the `Reach for it when` items, the learner's own included);
   - the problems already used for it (from its note's problems block), so the new problem is set elsewhere;
   - three other technique names, the wrong options of the recognition question;
   - and the path of the drill's problem file.
   It refuses with fewer than 4 technique notes: `a drill needs at least 4 technique notes; /techniques backfill makes them`.
3. **Choosing techniques.** Each technique with a note has weight `1 + 2 × (1 − pass rate) + 2 × (1 − recognition rate)`, where the pass rate is from its `Record` (lessons and interviews) and the recognition rate from its drills; a rate with no data counts as 0.5. Slots are drawn by weight without replacement while techniques remain (with replacement after). At least 2 slots go to strong techniques (pass rate in the top half); if the draw gives fewer, the last drawn weak slots are replaced by strong ones. The draw is seeded by the drill id. Slots are then shuffled.
4. The teacher writes the problem file `practice/.drills/<id>.problems.json`:
   ```json
   {"problems": [{"slot": 1, "statement": "…", "answer": "1/4", "variables": {}, "answerLatex": "\\frac14",
                  "solution": "…"}]}
   ```
   One problem per slot, on the slot's technique, solvable in a few minutes, in a setting unlike the problems already used, with a number or formula as the answer. Every answer is verified by running code. `practice.py drill-check <id>` validates the file (a problem per slot, statements and solutions present, answers readable by `answer_check`).
5. For each slot, two quizzes, the problem statement in both:
   - **Which technique does this problem need?** Multiple choice: the slot's technique and its three wrong options, shuffled. No "explanation" of the method; the explanation names the trick and the cue in the statement that signals it.
   - **Solve it.** A typed quiz with the problem's answer, `answerLatex` and the solution as the explanation. It is asked even after a recognition miss.
   - `practice.py drill-result <id> <slot> --recognised right|wrong [--picked "<Name>"] --solved right|wrong`.
6. `practice.py drill-summary <id>` prints `Recognised <k>/<n> · solved <k>/<n>`, and each confusion (`took Symmetry for Linearity of expectation`). The teacher's last reply gives that line, the confusions, and one sentence on the pattern if there is one.

Drill state: `practice/.drills/<id>.json` (slots, wrong options, results). A drill problem missed in either part becomes a card at the next scan.

## The practice note

`practice/YYYY-MM-DD.md`, one per day, linked with `md_log.py link "<note>" --session ${CLAUDE_SESSION_ID} --from-now`. It holds the `### Review` and `### Drill <id>` sections of that day, with their quiz blocks as in a lesson. It is not scanned for misses (results come from `result` and `drill-result`), and it is not a lesson note for technique tags.

## Technique notes and the brief

- **Technique notes.** `technique.py sync` reads the drills. A technique with drill results gets one line in its problems block, after the `Record` line: `**Drills:** recognised <k>/<n> · solved <k>/<n>`. The index gains a `Recognised` column (`k/n`, or `—`). The `Record` line and the index order stay as they are (lessons and interviews).
- **The resume brief.** `lesson.py summary` runs the scan and prints `REVIEW DUE: <k> cards — /review asks them` when cards are due. The teach skill's `Resume` question then mentions them in its orientation (one clause). Nothing starts unasked.

## The script: `hooks/practice.py`

```
practice.py scan                          add cards for new misses; print how many were added
practice.py due [--limit 10]              scan, then the due cards, oldest due first
practice.py result <card> right|wrong     schedule the card
practice.py stats                         active, retired, due today, and the next 7 days' due counts
practice.py drill [--n 8]                 create a drill and print its slots
practice.py drill-check <id>              validate the drill's problem file
practice.py drill-result <id> <slot> --recognised right|wrong [--picked <Name>] --solved right|wrong
practice.py drill-summary <id>            recognised and solved counts, and the confusions
```

`result` on a card that is not due is allowed (the learner may answer early) and schedules it the same way. `drill-result` refuses a slot already recorded.

## Skills

- `skills/review/SKILL.md` — `/review`, as above.
- `skills/drill/SKILL.md` — `/drill [n]`, as above, with the rules for writing drill problems (new settings, verified answers) and the recognition quiz.
- `skills/teach/SKILL.md` — the `REVIEW DUE` clause in the `Resume` orientation.
- `settings.json` — `Bash(python3 .claude/hooks/practice.py *)`, `Write(practice/**)`.
- README: a `Practice` section; `docs/architecture.md`: cards, the scan, scheduling, drills.

## Testing

- `tests/test_practice.py`, in a throwaway vault with a course, chapter notes holding quiz blocks, a graded exam scheme, a finished interview round and technique notes:
  - scan: a card for each kind of miss, with its key, date, section, techniques and prompt; review notes scanned; practice notes, techniques, fenced code not scanned; no duplicate on a second scan; first-scan spreading over 14 days; later misses due the next day (or today).
  - scheduling: right steps through 1, 3, 7, 16, 35 and retires; wrong resets to tomorrow; `due` order and limit.
  - drill: refusal under 4 notes; slots weighted (a weak technique drawn more often over many seeds); at least 2 strong slots; wrong options are other real techniques; `drill-check` failures; `drill-result` and its refusal of a repeat; `drill-summary` counts and confusions; drill misses become cards.
  - stats.
- `tests/test_technique.py`: the `Drills` line and the `Recognised` column.
- `tests/test_lesson_outcomes.py` (or a new test): the `REVIEW DUE` line in the brief.

## Out of scope

- Reminders or notifications outside a Claude Code session.
- Per-card ease factors (SM-2 and the like); the intervals are fixed.
- Mental arithmetic (the next piece).
- Editing or deleting cards by command (a card can be retired only by answering it).
