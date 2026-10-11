---
name: exam
description: Set, grade and discuss an exam on a course chapter or a lesson note — a written paper the learner sits in Obsidian, graded as a whole with feedback. Use with `/exam [chapter | note.md]`, `/exam submit`, or when the learner asks for an exam or a test on a chapter ("test me on chapter 2", "give me an exam"), says `submit` about an exam paper, or asks to have their exam marked.
argument-hint: [chapter | note.md] | submit [paper] | reopen <paper> | abandon <paper> | list
allowed-tools: Bash(python3 .claude/hooks/exam.py *), Bash(python3 .claude/hooks/md_log.py *), Bash(python3 .claude/hooks/book.py *), Write
---

Arguments: `$ARGUMENTS`

An exam is a paper the learner sits on their own, in Obsidian, and hands in as a whole. They see no feedback until they submit it. Then every answer is graded, with feedback written into the paper beside it. `exam.py` does everything that must be exact: paths, validation, the multiple-choice marks, inserting the feedback, the totals and the course's state. You write the questions, the marking scheme and the feedback on written answers. You never edit a paper by hand once the learner has it.

| Arguments | Section |
|---|---|
| none, a chapter id, or a note | **Setting an exam** |
| `submit [paper]`, or the learner says they have finished the paper | **Grading** |
| `reopen <paper>` | `python3 .claude/hooks/exam.py reopen "<paper>"`: a submitted paper becomes open again, so the learner can change it and submit again; reply with the `🗒` line |
| `abandon <paper>` | `python3 .claude/hooks/exam.py abandon "<paper>"`; reply with the `🗒` line |
| `list` | `python3 .claude/hooks/exam.py list`; show the output |

## Setting an exam

1. **Stop mirroring.** Nothing of setting or sitting an exam belongs in a lesson note:
   ```
   python3 .claude/hooks/md_log.py unlink --session ${CLAUDE_SESSION_ID}
   ```
2. **Ask the length.** One `AskUserQuestion` call, header `Exam`, question *"How long should the exam be?"*, options **Short (about 20 minutes)**, **Standard (about 45 minutes)**, **Long (about 90 minutes)**.
3. **Plan the paper:**
   ```
   python3 .claude/hooks/exam.py new [<chapter> | "<note.md>"] --length <short|standard|long>
   ```
   With no argument it takes the chapter of the current course finished last. If it refuses, say why in a sentence and stop.
   - An `OPEN:` line means a paper on this note is still open. Ask with one `AskUserQuestion` (header `Exam`): **Abandon it and set a new one** (run `exam.py abandon`, then `exam.py new` again) or **Keep it** (reply that `/exam submit` hands it in, and stop).
   - A `DRAFT:` line means an earlier setting stopped before `check` passed. Overwrite those files; do not reuse their questions unread.
4. **Read what was taught.** Read the whole note on the `COVERS` line. In a course, also Read the pages on the `READ` lines (at most 20 PDF pages per Read call). The exam tests what the note taught. It does not test material the note skipped, and nothing from the units on a `LEAVES OUT` line.
5. **Write the marking scheme first**, with the Write tool, to the `SCHEME` path. Writing it before the paper keeps the paper honest: every question has a settled answer and a settled way of marking it.
   ```json
   {
     "paper": "<the PAPER path, as printed>",
     "covers": "<the COVERS path, as printed>",
     "course": "<the course slug, or null>",
     "chapter": "<the chapter id, or null>",
     "attempt": 1,
     "length": "standard",
     "marks": 40,
     "questions": [
       {"id": "q1", "part": "A", "type": "mc", "marks": 2, "correct": ["a"],
        "explanation": "<why a) is right, as a quiz explanation>",
        "why_wrong": {"b": "<what b) would mean>", "c": "…", "d": "…"},
        "section": "<note stem>#<heading>", "unit": "2.3"},
       {"id": "q7", "part": "B", "type": "short", "marks": 4,
        "model_answer": "<a full answer, LaTeX as in the note>",
        "points": [{"text": "<what earns these marks>", "marks": 2}, {"text": "…", "marks": 2}],
        "section": "<note stem>#<heading>", "unit": "2.3"}
     ]
   }
   ```
   - The parts and their marks follow the `BUDGET` lines. Part A is multiple choice (`mc`), Part B short answers (`short`), Part C problems (`long`). You may move a question between B and C when the material calls for it; the total in `marks` must still be the sum.
   - `paper`, `covers` and `attempt` are the `PAPER`, `COVERS` and `ATTEMPT` lines. `course` and `chapter` are the `CHAPTER` line's values (`null` for a lesson note).
   - `section` is the target of one of the `SECTIONS` links, written as `<note stem>#<heading>`. In a course, `unit` is the unit printed beside it; for a lesson note, leave `unit` out. The unit is how a weak score marks a section `shaky`, so `check` refuses a wrong one.
   - Spread the questions over the sections in proportion to how much each one taught. Test understanding and use, not recall of wording: a computation, a derivation, an explanation of why, an application to a new case.
   - Build multiple-choice options with the teach skill's construction procedure: bare claims, the correct one first, each distractor a real misconception in the same form. Every wrong option has a `why_wrong`. "Select all" questions say so in their text and list every correct letter.
   - Check every number in the scheme by running code.
   - A book exercise may be adapted only after `python3 .claude/hooks/book.py exercise <id>` shows it is not `ASSESSED`. Name the source in the question.
6. **Write the paper** to the `PAPER` path:
   ```markdown
   ---
   exam: <note stem>
   covers: "[[<note stem>]]"
   attempt: <ATTEMPT>
   length: <length>
   status: open
   marks: <total>
   set: <today, YYYY-MM-DD>
   ---
   # <TITLE>

   *Closed book. About <minutes> minutes, <total> marks. Tick one box per multiple-choice
   question unless it says "select all". Write each answer under its **Answer:** line;
   LaTeX works, and so does an embedded photo of handwritten work. When you are done,
   type `submit`.*

   ## Part A — Multiple choice (<marks> marks)

   ### Q1 (2 marks)
   <question>

   - [ ] a) <option>
   - [ ] b) <option>
   - [ ] c) <option>
   - [ ] d) <option>

   ## Part B — Short answer (<marks> marks)

   ### Q7 (4 marks)
   <question>

   **Answer:**


   ## Part C — Problems (<marks> marks)

   ### Q10 (8 marks)
   <question>

   **Answer:**

   ```
   - Questions are numbered `Q1…Qn` through the whole paper, in the scheme's order.
   - Nothing of the scheme is in the paper: no answers, no marking points, no hints in the options.
   - When there is a `LEAVES OUT` line, add one sentence to the instructions naming the sections not tested.
   - Name a book figure the way the lesson does ("Figure 2.4"); it is embedded for you.
7. **Validate:**
   ```
   python3 .claude/hooks/exam.py check "<paper>"
   ```
   Fix the scheme or the paper for each problem it lists, and run it again until it prints `🗒 exam ready`.
8. **Reply with one line**, and nothing else: `Your paper is ready: [[<paper stem>]]. Sit it in Obsidian, then type **submit**.`

## Grading

1. **Hand it in.** Stop mirroring first, so nothing of the grading reaches a lesson note:
   ```
   python3 .claude/hooks/md_log.py unlink --session ${CLAUDE_SESSION_ID}
   python3 .claude/hooks/exam.py submit ["<paper>"]
   ```
   - With no argument it takes the only open paper, or else the only submitted one. If it lists several, ask which with one `AskUserQuestion` (header `Exam`).
   - If it says the paper cannot be read, tell the learner which questions to repair, and stop.
   - A paper already submitted (an earlier session stopped before grading) is not handed in again: `submit` prints its brief again, from the paper as it was handed in. Go on to step 2.
2. **Mark each written answer** in the brief against its marking points.
   - Judge meaning, not wording. Equivalent notation, or a different valid method, earns the same marks.
   - A correct method with a slip keeps the method marks. The feedback names the line where the slip is.
   - When you are unsure whether a claim in an answer is true, check it before you mark it: run code for a number, or ask the `researcher`.
   - An answer listed under `IMAGES` is handwritten: find the file in the vault and Read it. If you cannot read it, run `exam.py reopen "<paper>"`, ask the learner to put a clearer photo or a typed answer in the paper, and stop. They submit again when it is done.
   - Feedback is for the learner: what was right, what was missing or wrong and why, in two to four sentences. Do not repeat the model answer; the paper shows it folded under the feedback.
3. **Write the marks** with the Write tool to the file on the brief's `MARKS` line. It stays beside the scheme as the record of the marking.
   ```json
   {"q7": {"awarded": 3, "feedback": "…"},
    "q10": {"awarded": 5.5, "feedback": "…"},
    "revisit": {"<note stem>#<heading>": "<what to revisit there, in a clause>"}}
   ```
   Give every written question, and no multiple-choice one: `submit` marked those. Marks may be halves. Give a `revisit` clause for each section where marks were lost. Then write them into the paper:
   ```
   python3 .claude/hooks/exam.py grade "<paper>" --marks "<MARKS file>"
   ```
   If it refuses, correct the marks file and run it again. An `EDITED AFTER SUBMIT` line means the learner changed answers after handing the paper in: the paper is graded as it was submitted, and their edited copy is kept where the line says. Tell them so in a sentence.
4. **Reply briefly:** the score, the two or three sections most worth revisiting as links (from the paper's summary), and that a question about any answer is welcome. The details are in the paper.
5. **Link the paper**, as the last call of the reply, so that questions about the exam are kept beside the feedback:
   ```
   python3 .claude/hooks/md_log.py link "<paper>" --session ${CLAUDE_SESSION_ID} --from-now --muted --no-header
   ```

## After grading

- **A question about an answer** is answered as an aside on that question: start the reply with `%% aside: q7 %%` (the teach skill, "Questions from the learner"). The mirror puts the question and the answer after Q7's feedback.
- **A disputed mark:** check the answer against the scheme's points again. If the mark was wrong, write `{"q7": {"awarded": 4, "feedback": "…"}}` to the marks file (only that question), and run:
  ```
  python3 .claude/hooks/exam.py grade "<paper>" --regrade q7 --marks "<marks file>"
  ```
  If it stands, say why in terms of the points.
- **When the talk leaves the exam**, the paper must stop receiving the conversation. `/course next` and `/lesson resume` link their own note. If the learner goes on in plain words to something else, unlink first: `python3 .claude/hooks/md_log.py unlink --session ${CLAUDE_SESSION_ID}`.
- **A gap the exam showed** is taught as in any lesson. In a course, a unit that scored under half its marks is now `shaky`. Its misses are asked first in the next recall check.
