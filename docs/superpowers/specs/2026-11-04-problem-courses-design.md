# Problem courses — design

Date: 2026-11-04. Status: requested by the learner; built in one pass ("fast PRs"), no separate plan.

## Purpose

`/course` teaches every unit read → `ready` → check → apply. That suits a textbook. In a problem book (Zhou's *Practical Guide to Quantitative Finance Interviews*, Mosteller's *Fifty Challenging Problems in Probability*) the units are problems and the solutions are printed beside them or at the back. Taught as a textbook, the note explains each solution and the learner never attempts one. In the `gb` course 11 of 19 finished units are shaky. Interviews test finding a solution, not following one, so a problem course runs **problem first**.

## The mode

`state.json` gets `"mode": "textbook" | "problems"` (missing means textbook). It is set by `book.py new --problems` or `book.py set mode problems`, and from the skill by `/course mode problems`. Changing it touches nothing else: progress, notes, checkpoints and exams stay. Units already done stay done. The units still to come are taught the new way.

## Problems of a unit

The unit is still a section, so progress and exams keep working. Its **problems** are its lowest outline entries: the entries directly under the unit are numbered by their own ids when every one has a number, else by position (`2.2.5`, as the old gb notes do), and the entries under one of them get a letter (`2.7.1a`, `2.7.1b`). A unit with no entries under it is its own problem (each Mosteller problem). `book.py attempt`, `section` and `study` accept the number or the entry id.

## Statement and solution pages

The contents file (`new --toc`) takes an optional fourth column: the page where the entry's solution is printed. A solution runs to the next solution's page, which may be shared, and the last one to the end of the book. In problems mode `book.py next` prints:

- `PROBLEM` — number and title; `LEAD-IN` — pages of exposition the book prints before this problem, when there are any;
- `READ` — the statement pages only; `SOLUTION` — the solution pages when printed apart (Read after the statement is written), else a line saying the solution shares the statement's pages;
- `RECORD` — not attempted, in progress with *n* hints, result recorded without the transfer, or attempted before;
- `UNIT … PROBLEMS` — each problem's mark: ✓ unaided, ~ with hints, ✗ not solved, · not yet.

## One problem

The teach skill's new subsection **Problem books** runs five steps per problem, each one section `### <number> <title>`:

1. **Statement** — from the `READ` pages only, in the teacher's words, in a paragraph that opens `**The problem.**`; no method, no answer. The reply ends there.
2. **Attempt** — the exercise skill's hint ladder, one rung per reply; `book.py attempt <n> --hint` per hint; `--result solved|unsolved` at the end (`solved` after any hint is stored as `hinted`).
3. **Reveal and debrief** — the outcome line, the book's solution condensed, the method and the cues for it, anything beyond the book, a Key idea; ends with `ready`.
4. **Transfer** — one apply quiz on a fresh variant; `--transfer passed|missed`.
5. **Close** — the techniques flow and tag line of Phase 3 step 5.

The record is split in two calls so that a pause between the attempt and the transfer loses nothing. A chapter still opens with its Overview reply, and no reply opens with a quiz.

## Records

`state.json` `attempts[<entry id>] = {n, title, unit, note, hints, outcome, transfer, at, history}`. A new attempt at a complete problem moves the old one into `history`. A problem is **shaky** when it was not solved, took two or more hints, or its transfer was missed. When the last problem of a unit is complete, `book.py` records the unit `done` or `shaky` and prints what comes next, as `done` does. The index gets a `## Problems` table and per-unit marks.

**Misses.** `technique.problem_attempts()` reads every course's attempts. `practice.py scan` makes a card for each `hinted` or `unsolved` attempt (key `problem:<slug>/<entry id>#<k>`), with the section found by the problem number (the last section headed by it, so a retry wins), its techniques, and the `**The problem.**` paragraph as the prompt. `technique.py` adds ✓ (solved) or ✗ (hinted, unsolved) to the marks of that section. This matches interview problems, where `hinted` is a miss too.

## Books

- **Mosteller** (scanned, 96 PDF pages, printed p. 1 = PDF 9): a contents file with problems grouped by ten into six chapters, ids `<group>.<problem number>`, and a level-1 `Solutions` entry so the last statements stop before the solutions.
- **Green Book**: the gb map lacks *Glass balls* (§2.5) and splits nothing that holds several problems (A./B. parts in chapters 3–7). A full contents file reproduces the map with those additions, drops the exposition-only *Dynamic programming (DP) algorithm* (it becomes §5.3's lead-in), and adds the index so chapter 7 ends at PDF 208. Existing ids and ranges are unchanged except for two corrections; `new --force` keeps the state.

## Not changed

Textbook courses, exams, interviews, the exercise skill and its solutions policy. The notation bullet of the teach skill is left alone; the new text is a separate subsection.
