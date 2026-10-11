# Exams — design

Date: 2026-10-11. Status: approved in conversation, awaiting spec review.

## Purpose

The learner can sit an exam on a chapter of a course, or on any lesson note, when the chapter is finished or whenever they ask. An exam mixes multiple-choice questions with written answers. It is graded as a whole, returned with feedback, and kept as its own file. Its weak spots feed back into the course: units done badly become `shaky`, and questions that lost marks are asked first in later recall checks.

**Said by the learner:** exams on a chapter, on request or offered by the teacher; multiple choice and written responses; graded and returned with feedback; stored separately.

**Agreed in the design conversation:**

- The exam is a paper written in Obsidian, not the quiz popup. No feedback is shown until the whole paper is submitted.
- Results feed weak spots back (shaky units, recall checks). Nothing is gated: the next chapter is open whatever the score.
- Scope: a course chapter (the default), or any standalone lesson note.
- Length is chosen per exam: short (about 20 min), standard (about 45 min), long (about 90 min).
- Approach A: the teacher writes the paper directly with the Write tool, and a script, `exam.py`, does the bookkeeping and everything that must be exact.

**Assumed and not contradicted:** questions test only what was taught; `ASSESSED` exercises are never used; every attempt is kept; a retake is a new paper.

## Components

| Component | File | Job |
|---|---|---|
| Exam skill | `skills/exam/SKILL.md` | The procedure: set a paper, grade a submitted one, handle follow-up questions. Invocable as `/exam` and by the model when the learner asks in plain words. |
| Exam script | `hooks/exam.py` | `new`, `submit`, `grade`, `list`. Paths, parsing, multiple-choice grading, inserting feedback, totals, course state, the index table, `shaky` marks. |
| Course helper | `hooks/book.py` | Gains an `exams` list in `state.json`, an **Exams** table in the index, and an `EXAM:` line in the `CHAPTER … COMPLETE` message. `exam.py` imports its course code. |
| Resume helper | `hooks/lesson.py` | `summary` prints a new `EXAM MISSES` block. |
| Note mirror | `hooks/md_log.py` | `exam` joins `ADMIN_COMMANDS`; a plain `submit` line is a typed `/exam submit`. |
| Teach skill | `skills/teach/SKILL.md` | The chapter close offers `/exam` in one sentence; the recall check takes `EXAM MISSES` first. |
| Settings | `settings.json` | `Bash(python3 .claude/hooks/exam.py *)` pre-approved. |
| Docs | `README.md`, `docs/architecture.md` | An "Exams" section and commands-table rows; an architecture section, state files, a fragile-parts entry. |

## Files

The paper goes in a visible `exams/` folder beside the note it tests; the marking scheme and the submitted snapshot go in a hidden `.exams/` folder beside that. Obsidian does not show dot-folders.

| Path | What it is |
|---|---|
| `courses/<slug>/exams/<slug>-ch02-exam-<n>.md` | Paper for chapter 2 of a course, attempt `n`. |
| `courses/<slug>/.exams/<slug>-ch02-exam-<n>.json` | Its marking scheme, and after grading its marks. |
| `courses/<slug>/.exams/<slug>-ch02-exam-<n>.submitted.md` | The paper as submitted. |
| `<dir>/exams/<stem> — Exam <n>.md` | Paper for a standalone lesson note `<dir>/<stem>.md`. |
| `<dir>/.exams/<stem> — Exam <n>.json` | Its scheme. |
| `<dir>/.exams/<stem> — Exam <n>.submitted.md` | Its snapshot. |

`n` is one more than the highest attempt on file for that note, whatever the status of earlier attempts.

## The flow

1. **Request or offer.** `/exam` with no argument covers the last chapter marked complete in the current course. `/exam 3` covers chapter 3. `/exam "<note.md>"` covers a lesson note. A plain-words request ("give me an exam on chapter 2") loads the skill. When `book.py done` completes a chapter, the teacher's chapter close says in one sentence that `/exam <chapter>` sets an exam; it never starts one unasked.
2. **Unlink.** The skill's first step is `md_log.py unlink --session ${CLAUDE_SESSION_ID}`. Nothing of setting or sitting the exam reaches any note.
3. **Open paper check.** If a paper for the same note is `open`, one `AskUserQuestion` (header `Exam`): abandon it (status `abandoned`, kept on file) or keep it and submit it first.
4. **Length.** One `AskUserQuestion` (header `Exam`): short, standard, long.
5. **`exam.py new <target> --length <l>`** prints: `PAPER`, `SCHEME`, `ATTEMPT`, `COVERS` (the note), `SECTIONS` (the `###` headings the exam may test, as wikilinks, with each heading's unit id in a course), `READ` (in a course, the book pages of the tested units), `LEAVES OUT` (units of the chapter not yet studied), and the length's budget (see "Paper shape"). It refuses when the note does not exist or has no `###` sections.
6. **Read.** The teacher reads the whole note being tested (setting an exam is the one place a note is read in full) and, in a course, the pages on the `READ` line.
7. **Write the scheme, then the paper.** Scheme first, with the Write tool, to the `SCHEME` path; then the paper to the `PAPER` path. Every numeric answer is checked by running code before it goes in the scheme. A book exercise is used only after `book.py exercise <id>` shows it is not `ASSESSED`.
8. **`exam.py check <paper>`** validates the pair before the learner sees it: every `### Q<n>` in the paper has a scheme entry and vice versa, marks agree and add up to the frontmatter total, multiple-choice option letters in the scheme exist in the paper, every `section` link resolves to a heading of the note. The teacher fixes whatever it reports.
9. **Reply.** One line: the paper as a wikilink, and that `/exam submit` (or `submit`) hands it in.
10. **The learner sits it** in Obsidian, at their own pace, closed book on their honour.
11. **Submit and grade** — see "Grading".
12. **Follow-up.** The graded paper is linked with `--from-now`. Questions about it become asides beside the question's feedback (`%% aside: q7 %%`).

## Paper shape

Every paper has three parts. Marks per question are shown in its heading.

| Length | Part A: multiple choice | Part B: short answer | Part C: problems | Total |
|---|---|---|---|---|
| short (~20 min) | 4 × 2 marks | 2 × 4 marks | 1 × 8 marks | 24 |
| standard (~45 min) | 6 × 2 marks | 3 × 4 marks | 2 × 8 marks | 40 |
| long (~90 min) | 8 × 2 marks | 4 × 4 marks | 3 × 10 marks | 62 |

`exam.py new` prints this budget; the teacher may move a question between parts B and C when the material calls for it, and `check` accepts any total that matches the frontmatter. Questions are spread across the tested sections in proportion to how much each taught. Multiple-choice options follow the teach skill's construction procedure. A "select all" question says so in its text and is graded as an exact-set match.

## The paper

```markdown
---
exam: pml1-ch02
covers: "[[pml1-ch02]]"
attempt: 1
length: standard
status: open
marks: 40
set: 2026-10-11
---
# Exam — Chapter 2: Probability: univariate models

*Closed book. About 45 minutes, 40 marks. Tick one box per multiple-choice
question unless it says "select all". Write each answer under its
**Answer:** line; LaTeX works, and so does an embedded photo of handwritten
work. When you are done, type `/exam submit`.*

## Part A — Multiple choice (12 marks)

### Q1 (2 marks)
<question>

- [ ] a) …
- [ ] b) …
- [ ] c) …
- [ ] d) …

## Part B — Short answer (12 marks)

### Q7 (4 marks)
<question>

**Answer:**


## Part C — Problems (16 marks)

### Q10 (8 marks)
<question>

**Answer:**

```

- Questions are numbered `Q1…Qn` through the whole paper.
- A question's extent is from its `### Q<n>` heading to the next `### Q` or `## ` heading.
- A written answer is everything in that extent after the `**Answer:**` line.
- A multiple-choice answer is the set of ticked boxes (`- [x]` or `- [X]`) in that extent.
- Questions naming a book figure get it embedded, through `figures.process`, as in chapter notes. `exam.py` runs the pass on the paper after `check`.
- No "I don't know" option. A blank answer scores 0. No negative marks.

## The scheme

```json
{
  "paper": "courses/pml1/exams/pml1-ch02-exam-1.md",
  "covers": "courses/pml1/pml1-ch02.md",
  "course": "pml1",
  "chapter": "2",
  "attempt": 1,
  "length": "standard",
  "marks": 40,
  "questions": [
    {"id": "q1", "part": "A", "type": "mc", "marks": 2, "correct": ["a"],
     "explanation": "…", "why_wrong": {"b": "…", "c": "…", "d": "…"},
     "section": "pml1-ch02#2.3 Bayes' rule", "unit": "2.3"},
    {"id": "q7", "part": "B", "type": "short", "marks": 4,
     "model_answer": "…",
     "points": [{"text": "states Bayes' rule correctly", "marks": 2},
                {"text": "names prior, likelihood, posterior, evidence", "marks": 2}],
     "section": "pml1-ch02#2.3 Bayes' rule", "unit": "2.3"}
  ]
}
```

`unit` is present only in a course. After grading, `exam.py` adds `status`, `submitted`, `graded`, `score`, and per question `awarded` and `feedback`.

## Grading

**`exam.py submit [<paper>]`**

1. With no argument it finds papers with `status: open` (in the current course and, for lesson notes, under the project). None: it says so. More than one: it lists them and stops; the teacher asks which.
2. A paper already `submitted` or `graded` is refused with its status.
3. It parses the paper. A scheme question with no matching `### Q<n>` heading, or a multiple-choice question whose option lines cannot be found, is reported by name, and nothing is changed: the teacher asks the learner to repair the paper and submit again.
4. It writes the snapshot, sets `status: submitted` in the paper and the scheme, and grades multiple choice: full marks for the exact correct set, 0 otherwise (two ticks on a single-answer question score 0).
5. It prints the grading brief: the multiple-choice results, then for each written question its text, model answer, marking points, and the learner's answer verbatim (with embedded image paths listed), and the list of blank answers.

**The teacher marks** each written answer against its points, by meaning not wording. Equivalent notation or a different valid method earns the same marks. A correct method with a slip keeps the method marks, and the feedback names the line where the slip is. A claim it is unsure of is checked (code for numbers, the `researcher` otherwise) before it is marked. An embedded image is Read; if it cannot be read, grading stops and the learner is asked to re-upload or type the answer. For multiple choice the feedback is written by the script from `explanation` and the chosen option's `why_wrong`.

**`exam.py grade <paper>`** takes JSON on stdin, one entry per written question: `{"q7": {"awarded": 3, "feedback": "…"}}`. It refuses a missing question, an award above the question's marks, or a paper not `submitted`. Then it:

1. inserts a feedback callout after each question's extent, never editing the answer text;
2. inserts the result summary under the title;
3. sets `status: graded`, `score`, `graded` in paper and scheme;
4. records misses: every question with `awarded < marks`;
5. in a course: updates the `exams` list in `state.json`, regenerates the index, and marks `shaky` every unit whose questions scored under 50% of their marks, only from `done` (a `shaky` unit stays `shaky`; a good score never clears it);
6. prints the score, the part totals and the units marked `shaky`.

**`exam.py grade <paper> --regrade q7`** takes one entry on stdin, rewrites that question's callout with a line `*Regraded <date>: <old> → <new>.*`, and recomputes everything in steps 2–5.

**Feedback callout** (`success` for full marks, `warning` for partial, `failure` for zero):

```markdown
> [!warning] Q7 — 3/4
> <feedback>
> Tested: [[pml1-ch02#2.3 Bayes' rule|§2.3]]
>
> > [!example]- Model answer
> > <model answer>
^q7
```

**Result summary:**

```markdown
> [!summary] Result — 31/40 (78%)
> Part A 10/12 · Part B 9/12 · Part C 12/16
> **Revisit:** [[pml1-ch02#2.3 Bayes' rule|§2.3]] (Q7, Q10): <one clause>. …
```

The revisit clauses come from the grade JSON's optional `"revisit": {"pml1-ch02#2.3 Bayes' rule": "<clause>"}`; sections with misses but no clause are listed with their question numbers only.

**The reply** is short: the score, the two or three sections most worth revisiting as links, and that questions about any answer are welcome. Then the paper is linked: `md_log.py link "<paper>" --session ${CLAUDE_SESSION_ID} --from-now`.

## Weak spots in recall checks

`lesson.py summary <note>` prints, after `EARLIER RECALL CHECKS`:

```
EXAM MISSES (pml1-ch02-exam-1, 31/40): re-probe these first
  - Q7 3/4 §2.3 Bayes' rule — State Bayes' rule for a discrete hypothesis…
  - Q10 5/8 §2.3 Bayes' rule — …
```

Source: the newest graded attempt of each exam whose `covers` is this note, and in a course also the previous chapter's note. The teach skill's recall check takes `EXAM MISSES` together with `EARLIER RECALL CHECKS` as the first candidates.

## The note mirror

- `ADMIN_COMMANDS["exam"] = None`: every reply to `/exam` is muted up to the learner's next prompt.
- `TYPED_COMMAND_RE` treats `exam …` and a prompt that is exactly `submit` (any case, optional trailing punctuation) as typed commands, muted the same way and not logged as a prompt.
- The skill unlinks at the start, so a plain-words request ("give me an exam") reaches the chapter note at most as the learner's own prompt line, and nothing after it.
- After grading, the paper is linked with `--from-now` inside the muted reply. The learner's next typed question is logged as a prompt in the paper, and the teacher's `%% aside: q<n> %%` reply makes it an aside after `^q<n>`. **This is the riskiest interaction and is tested first.** If it fails, the fallback is to not link the paper: follow-up discussion is not mirrored, and the paper stands on its own.

## Edge cases

| Case | Behaviour |
|---|---|
| Paper structure changed by the learner | Parsed by `### Q<n>` headings; a missing question is reported by name; nothing graded from a guess. |
| Paper edited after submit | Grading uses the snapshot; `submit` refuses a paper not `open`. |
| No open paper / several | Says so / lists them and asks. |
| New exam while one is open | Ask: abandon (status `abandoned`) or submit it first. |
| Session ends before submit | Paper and scheme are on disk; `/exam submit` in any session finds them. |
| Unreadable photo answer | Grading stops; learner re-uploads or types it. |
| Disputed mark | Teacher re-checks against the scheme; `--regrade` rewrites the callout and totals with a note. |
| Note missing or without sections | `exam.py new` refuses. |
| Chapter not finished | Allowed; `LEAVES OUT` names the units not tested, and the paper's instructions say so in a sentence. |

## Out of scope

Timed exams, letter grades, exams over several chapters, a PDF version (Obsidian's export covers it), exams in the quiz popup, and clearing `shaky` from a good score.

## Testing

1. **`exam.py` directly** in a scratch copy of a course: `new`, `check`, `submit`, `grade`, `--regrade`, `list`, with hand-filled papers covering ticked boxes, multiple ticks, `[X]`, blank answers, a deleted heading, text above `**Answer:**`, display math, an embedded image. Inspect the callouts, totals, frontmatter, scheme, `state.json`, the index table, `shaky` marks, and `lesson.py summary`'s `EXAM MISSES`.
2. **Hooks** with hand-made transcripts piped to `md_log.py`: `/exam` and plain `submit` muted and not logged; nothing reaches the chapter note; after the link during grading, a typed question with `%% aside: q7 %%` lands after `^q7`. Run this first.
3. **The skill headless** in a scratch copy: `claude -p "/exam 1"` with `--allowedTools`, fill in the paper by script, then `claude -p "/exam submit"`; read the paper and scheme.
