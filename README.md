# learn-claude

A personal AI tutor that runs inside [Claude Code](https://code.claude.com) on a Claude subscription.

It is a port of [amosblomqvist/learn](https://github.com/amosblomqvist/learn), the learning system from [How I Use AI to Learn Things](https://www.youtube.com/watch?v=kzcI5F4tGiU), from the pi harness to Claude Code. The teaching philosophy is his. The plumbing is new.

**What you get**

- **A teacher with a fixed method.** It finds what you already know, agrees a plan with you, then teaches one idea at a time: a text to read, an easy quiz, a harder quiz.
- **Graded quizzes in a popup.** Your answer is marked the moment you give it, with the explanation.
- **A lesson note in Obsidian.** Every lesson is mirrored into a markdown file with rendered math, diagrams and quiz results. It reads like a textbook chapter, not a chat log.
- **Lessons that span days.** Pause with a checkpoint and pick the lesson up again in a later session.
- **Courses that follow a textbook.** Give it a PDF and pick the chapters. Lessons are condensed from the book's own pages, and you get hints in steps on the book's exercises.
- **Exams on a chapter.** A written paper you sit in Obsidian and hand in as a whole. It comes back graded, with feedback beside every answer.
- **Checked facts and checked pictures.** A research subagent verifies claims on the web. Diagram subagents render each picture and look at it before it reaches you.

Everything runs locally except the model calls, which go through your Claude Code login. No API key is needed.

**Contents:** [Quick start](#quick-start) · [How a lesson runs](#how-a-lesson-runs) · [Quizzes](#quizzes) · [Stopping and resuming](#stopping-and-resuming) · [Following a textbook](#following-a-textbook) · [Exams](#exams) · [Interviews](#interviews) · [Technique notes](#technique-notes) · [Practice](#practice) · [Coding practice](#coding-practice) · [The lesson note](#the-lesson-note) · [Commands](#commands) · [Repository layout](#repository-layout) · [Customising](#customising) · [Troubleshooting](#troubleshooting)

## Quick start

### Requirements

| Needed | For |
|---|---|
| Claude Code ≥ 2.1, Python 3.10+ | everything |
| tmux ≥ 3.2 | the quiz popup |
| Obsidian, or any markdown viewer | reading the lesson notes rendered |
| poppler (`pdfinfo`, `pdftotext`, `pdftoppm`) and `mutool` | textbook courses |
| Node ≥ 18 with npm, and Chrome or Chromium | Mermaid diagrams |
| `rsvg-convert`, ImageMagick or Chrome | SVG diagrams |

Only the first row is essential. Without tmux, quizzes fall back to a cramped one-line form. Without Node or Chrome you lose the pictures and nothing else.

### Install

This repository **is** a `.claude` directory. Clone it into the folder you will learn in. The best place is the root of your Obsidian vault, so that notes and diagrams render in place.

```bash
cd ~/path/to/vault
git clone https://github.com/LnBn/learn-claude .claude
bash .claude/scripts/install.sh
```

The install script installs the Mermaid renderer, registers the quiz server in `.mcp.json`, and smoke-tests the renderers. If the folder is an Obsidian vault, it also adds the callout styles to it.

Then start Claude Code from that folder, inside tmux:

```bash
tmux
claude
```

The first time, accept the trust dialog and the prompt to enable the project's `quiz` MCP server.

### Update

```bash
git -C .claude pull
```

Then start a new Claude Code session; a running session keeps the old skills and settings. Your notes and log state are gitignored, so pulling never touches them.

The callout styles are a copy in the vault. When an update changes them, copy them again:

```bash
cp .claude/obsidian/learn-callouts.css .obsidian/snippets/
```

### Your first lesson

```
/md-log lessons/tcp.md
teach me how TCP achieves reliability
```

The first line says where the lesson note goes. The second starts the lesson. Open `lessons/tcp.md` in Obsidian and read along there.

## How a lesson runs

Every lesson has the same four phases. Their size changes with the topic; their order does not.

1. **Opening.** A few sentences on the topic and on what is about to happen. The teacher stops here; type `ready` when you have read it.
   - If you ask to start "from the basics", the opening is a one or two paragraph overview of the subject. It ends with one question: probe my level first, or start from the beginning; and what do you want from this.
2. **Probe.** Graded questions that find the edge of what you know. They get harder until you miss, then narrow in.
3. **Plan.** Under a `### Plan` heading: a short approach and a dependency map. The roots are facts you can accept at face value; the sink is your goal. Nothing is taught until you approve it.
4. **Teach.** One node of the map at a time. Each node is a section with a fixed shape:

   | Step | What happens |
   |---|---|
   | Read | A complete written exposition: why this node now, the fact or derivation, how it hangs off earlier nodes, a worked example. It ends with a `Key idea` callout of one to three sentences. The teacher stops. Read it in the note, then type `ready`. |
   | Check | One quiz that a close reading answers. |
   | Apply | One quiz that needs reasoning, a calculation or running code. It is usually a problem you have not seen worked: the example's setting with one crucial change, or a new setting that needs the same trick. |

   A failed apply is re-taught, with a fresh question, before anything is built on it.

You can type a question at any prompt. The teacher answers it before moving on.

## Quizzes

Quizzes open in a popup over the terminal.

| Key | Action |
|---|---|
| ↑ ↓ or j k | move |
| 1–9 | jump to an option (toggles it in multi-select) |
| Space | toggle an option (multi-select) |
| Enter | submit |
| Tab | type a note that is sent with your answer |
| `?` | ask the teacher a question *before* answering; the quiz comes back after the answer |
| `f` | open the figure the question refers to, in your image viewer (shown only when there is one) |
| PgUp PgDn | scroll |
| Esc | cancel the quiz |

- "I don't know" is always the last option. It is recorded as a gap, not as a wrong answer.
- After you answer, the popup shows ✓ or ✗, the correct answer and the explanation. Any key closes it.
- Math is shown as Unicode in the popup (x², αᵢ, √(a²+b²)). The note keeps the real LaTeX.

### Typed answers

When the answer to a question is a number or a formula, there are no options: you type it.

```
Answer: 2(2^n - 1)
        reads as: 2(2ⁿ − 1)
```

- **What you can type:** numbers and fractions (`7/12`, `0.518`), `+ - * / ^`, brackets, implicit multiplication (`2n`, `2(n+1)`, `np`), `n!`, `sqrt`, `ln`, `log2`, `log10`, `exp`, `abs`, `binom(n,k)` or `C(n,k)`, `pi`, `e`, `inf`. Unicode works too: `π √ × · − ∞`.
- **Any equivalent form counts.** `2^(n+1)-2`, `2*2^n-2` and `2(2^n-1)` are all marked right: the answer is compared with the correct one at several values of the variables.
- **Decimals** count if they match the exact value to three significant figures: `0.333` for $1/3$, not `0.33`. A question that asks for the exact form says so, and refuses a decimal.
- **The line under the field** shows how your answer reads, or what is wrong with it (`can't read: unclosed bracket`). Enter only submits an answer that can be read.
- If your answer is one of the common mistakes the teacher anticipated, the feedback names the mistake.

The keys differ from multiple choice, because letters go into the field:

| Key | Action |
|---|---|
| ← → Home End Backspace Delete | edit the answer |
| Enter | submit |
| ↓ then Enter | "I don't know" |
| Tab | type a note that is sent with your answer |
| `?` | ask the teacher first |
| Ctrl-F | open the figure |
| Esc | cancel the quiz |

### Quizzes in the note

While you answer, the quiz is in the note as an open box with the question and the options, so a long question can be read there too. Once you answer, it becomes one box, folded, at the place it was asked. Its line shows the result and the question, so the note reads as text with a row of short quiz lines in it. Click the line to open the question, the options, your answer and the explanation.

```markdown
> [!failure|quiz]- ✗ Which pirates are the cheapest votes for the proposer to buy?
>
> 1. The pirates who get 0 coins in the $(k-1)$-pirate game
> 2. The pirates who get 1 coin in the $(k-1)$-pirate game
>
> Selected: 2. The pirates who get 1 coin in the $(k-1)$-pirate game
> Correct answer: 1. The pirates who get 0 coins in the $(k-1)$-pirate game
>
> If the proposer's plan fails, …
```

| Line starts with | Meaning |
|---|---|
| ✓ (green) | correct |
| ✗ (red) | wrong |
| ? (blue) | "I don't know" |
| ⊘ Skipped (orange) | you closed the popup without answering |
| Asked first | you asked the teacher with `?`; the teacher's answer and the graded quiz follow it |

A question longer than about 100 characters is cut in the line and given in full inside the box. `|quiz` marks the box as a quiz: Obsidian does not show it, and the callout snippet uses it to draw quiz boxes a little smaller than the lesson's own.

Notes written before quizzes were folded hold two open boxes per quiz. Fold them with:

```bash
python3 .claude/hooks/quiz_block.py convert lessons/openskill.md courses/pml1/pml1-ch01.md   # shows the changes
python3 .claude/hooks/quiz_block.py convert --write lessons/tcp.md courses/pml1/pml1-ch01.md
```

`--write` first copies each note to `.claude/md-log-state/quiz-fold-backup/`. A note that already has folded quizzes is skipped unless you add `--force`, and running the command twice changes nothing.

## Stopping and resuming

A lesson lives in its note, so you can stop and continue in a new session. Keep one note per topic.

```
/lesson pause                    # save a checkpoint: goal, confirmed nodes, shaky nodes, next node
/lesson resume lessons/tcp.md    # another day: continue from the checkpoint
/lesson status lessons/tcp.md    # where the lesson stands, no teaching
/lesson reset lessons/tcp.md     # start over; the note and its checkpoints go to a trash folder
```

- If you simply say you are stopping, the teacher saves a checkpoint too.
- Checkpoints live in a hidden file beside the note (`lessons/.checkpoints/<name>.md`), so the note stays clean.
- On resume the teacher reads the checkpoint, the map and your recent quiz results, and asks whether you want a short recall check before continuing.
- A recall check goes in a review note, so the lesson note stays the lesson: `lessons/tcp — Review.md` beside the note, or one `<name>-review.md` for a whole course. Each check opens with links to the sections it tests. A question you miss there comes up first in the next recall check.
- If you stopped right after reading a section, the next session points you back to that reading, with a link, in the review note. Its check and apply questions follow in the lesson note when you type `ready`.
- Notes written by the original pi version resume the same way. A `… — Resume Here.md` companion note is picked up automatically.

## Following a textbook

A course is a textbook PDF, a syllabus chosen from it, and one lesson note per chapter. The lesson replaces reading the section, as a lecture does. The book stays there for depth.

```
/course new ~/books/murphy-pml1.pdf pml1   # set up a course
/course next                               # study the next section (also how you resume)
/course study 4.2                          # or a section of your choice
/exercise 2.3                              # help with Exercise 2.3
```

### Setting up

`/course new <book.pdf> [name]` maps the book once: every section gets a page range, taken from the PDF's outline. A PDF without an outline is mapped from its contents pages instead.

The teacher then reads the preface and asks three things:

1. **What to cover.** The whole book, only the sections the book does not mark optional, or your own selection such as `2 3.1-3.4 5`.
2. **What you want from it.** This is the goal the whole course is aimed at.
3. **When it may show full solutions** to exercises. The default is: after you have shown an attempt and asked.

If the PDF is outside the folder Claude Code runs in, Claude Code asks once for permission to read it.

### Studying

`/course next` teaches the next section of the syllabus. Use the same command to resume after a pause; it reads the chapter's checkpoint.

- **A new chapter opens with an overview** to read: what the chapter covers section by section, what it rests on, and a map of its sections. Then you choose: `ready` starts the first section, and `probe` first runs a few graded questions on the prerequisites.
- **Each section is taught like any lesson node**: read, `ready`, check, apply. The heading carries the book's section number and page reference.
- **The teacher reads the pages first.** Before each section it reads that section's pages, so the lesson matches your edition of the book.
- **The book is the backbone, not the boundary.** The teacher adds material from outside the book when that helps: a better intuition, a link to another field, what has changed since. It says when something is not in the book, and it may suggest further reading.
- **Notation and equation numbers are the book's.** `(2.51)` in the note is `(2.51)` in the book, so references in the exercises resolve.
- **Apply quizzes may come from the book's exercises**, with the source named.
- **The book's figures come into the note.** The first time the lesson names a figure ("Figure 1.4a"), it is cropped from the page into `viz/` and embedded once, below that paragraph or above the quiz that names it. Every mention of it, then and later, is a link that jumps to the figure. In a quiz that names a figure, `f` opens it in your image viewer.

  For a note written before this, run `python3 .claude/hooks/figures.py <note>` once (it keeps a `.bak` copy).
- **Section references are links.** When the lesson refers to a section by number ("as in §1.1"), the reference links to that section's heading, in this chapter's note or an earlier one. A part of a section links to the section that holds it (§1.2.1.5 to `### 1.2.1`). A section not taught yet stays plain text.

  For a note written before this, run `python3 .claude/hooks/sections.py <note>` once (it keeps a `.bak` copy).

When a chapter is finished the teacher says so, and `/course next` opens the next chapter in a new note.

### Exercises

Run `/exercise 2.3`, or just say you are stuck on Exercise 2.3. You can paste your work or give the path of a photo of it.

Help comes one step per reply:

1. **Orient.** What is asked, and which result of the chapter it rests on.
2. **Strategy.** The approach, without computation.
3. **Next step.** The first move from where your work stops.
4. **Check.** Whether your answer is right, and if not, the first line that goes wrong.
5. **Full solution.** Only as the course allows.

`/course assess 2.5 2.6` marks exercises as assessed coursework. Those get hints and checks, never a full solution, and they are never used as quiz questions.

### Several courses

Each course keeps its own syllabus, progress, notes and checkpoints. Commands act on the current course: the one created or chosen last.

```
/lesson pause        # save where you are in this course
/course list         # all courses, the current one marked
/course use pml1     # switch
/course next         # continue that course from its own checkpoint
```

### Files of a course

| File | What it is |
|---|---|
| `courses/<name>/<name>.md` | The index: syllabus with progress, and a table of exercises. Generated; do not edit. |
| `courses/<name>/<name>-ch02.md` | The lesson note of chapter 2. |
| `courses/<name>/<name>-ch02-exercises.md` | Exercise help for chapter 2. |
| `courses/<name>/<name>-review.md` | Recall checks from every resumed session, linked from the index. |
| `courses/<name>/exams/` | Exam papers, one per attempt: `<name>-ch02-exam-1.md`. |
| `courses/<name>/interviews/` | Mock interviews, one note per round: `<name>-interview-1.md`. |
| `techniques/` | Technique notes, shared by every course, and their index `Techniques.md`. |
| `practice/` | One note per day of review and drills; hidden: the review cards and the drills. |
| `courses/<name>/.course/` | Hidden: the page map and the progress record. |
| `courses/<name>/.exams/` | Hidden: each exam's marking scheme, and your answers as submitted. |
| `courses/<name>/.interviews/` | Hidden: each round's problems, clock record and marks. |
| `courses/<name>/.checkpoints/` | Hidden: checkpoints, as for any lesson. |

## Exams

An exam tests a whole chapter at once. You sit it on your own, in Obsidian, and get it back graded with feedback beside every answer.

```
/exam                # the chapter you finished last
/exam 3              # chapter 3 of the current course
/exam "Bayes.md"     # any lesson note
```

When you finish a chapter, the teacher mentions that `/exam` is there. It never starts one unasked.

### Sitting an exam

The teacher asks how long it should be: short (about 20 minutes), standard (about 45) or long (about 90). It then writes a paper in three parts:

1. **Multiple choice.** Tick a box: `- [x] b) …`.
2. **Short answers.** Write under the **Answer:** line.
3. **Problems.** A derivation, a computation or an explanation, also under **Answer:**.

Each question shows its marks. An answer can be as long as you like, with LaTeX, headings, or an embedded photo of handwritten work. The paper only tests what the chapter's lessons taught, but not with the lessons' own examples: most problems change a crucial detail of a worked example, or ask for the same trick in a new setting. If you take an exam on a chapter you have not finished, the paper says which sections it leaves out.

Nothing is graded until you hand in the whole paper. Type `submit` (or `/exam submit`) in Claude Code when you are done. The paper is graded as you handed it in. To change an answer after that, take the paper back with `/exam reopen <paper>` before it is graded, and submit it again.

### The graded paper

The feedback is written into the paper, under each answer. Your answers are not changed.

```markdown
> [!warning] Q7 — 3/4
> Bayes' rule is stated correctly and the posterior and likelihood are named.
> The marginal likelihood p(D) is called "the prior"; the prior is p(h).
> Tested: [[pml1-ch02#2.3 Bayes' rule|§2.3]]
>
> > [!example]- Model answer
> > …
```

Green means full marks, amber partial, red none. The model answer is folded, so you can try to fix your answer before you look. A summary at the top gives the score per part and the sections to revisit, with links into the chapter note.

Ask about any question afterwards ("why did I lose a mark on Q7?"). The question and the answer are kept in the paper, beside Q7's feedback. If a mark was wrong, say so: the teacher checks it against the marking scheme and corrects it in the paper.

### What an exam changes

- **Recall checks.** The questions you lost marks on are asked first in the next recall check.
- **Course progress.** A section where you scored under half its marks is marked `shaky` in the course index.
- **The index.** The course index lists every exam with its score.

Nothing is blocked: you can go on to the next chapter whatever the score.

### Retakes

Run `/exam 3` again for a new paper with new questions. Every attempt is kept, and the newest one counts for recall checks. A paper you started but do not want to finish can be dropped with `/exam abandon <paper>`. `/exam list` shows every paper with its score.

An exam on a lesson note outside a course works the same way, with its papers in an `exams/` folder beside the note.

## Interviews

A mock interview is a timed round of problems you have not seen, on the units of the course you have finished, with an interviewer who behaves like a real one.

```
/interview            # asks how long
/interview standard   # 3 problems, 12 minutes each
```

| Length | Problems | Time |
|---|---|---|
| short | 2 | 24 minutes |
| standard | 3 | 36 minutes |
| long | 4 | 48 minutes |

The problems are written for the round and checked by running code before it starts. They are not labelled by topic: recognising which idea a problem needs is part of the test.

### During the round

Think aloud in plain messages. The interviewer says little while you make progress, asks you to justify a step a real interviewer would question, and checks your final answer the moment you give it. Give answers as a number or a formula, as in a typed quiz.

- **Hints.** When you are stuck, or time is running short, the interviewer gives a nudge. A pointed-out error ("are you sure about that term?") also counts as a hint. Being asked *why* does not.
- **The clock.** Each problem has 12 minutes, shown in the tmux status bar (`P2/3 9:40/12:00`). Near the end the interviewer gives a stronger nudge; when time is up it sketches the solution and moves on. Your own status bar comes back when the round ends.
- **Follow-ups.** A correct answer with at least two minutes left gets a follow-up: the same problem with one thing changed.
- **Stopping.** `/interview stop`, or saying you want to stop, ends the round and goes to the scorecard.

### The scorecard

The round's note, `courses/<name>/interviews/<name>-interview-1.md`, holds the conversation, one heading per problem, and then the scorecard: each problem's outcome (solved, solved with hints, not solved, not reached), time, hints, follow-up and the idea it needed; feedback on how you explained your reasoning; two or three things to work on, with links to the sections to revisit; and each problem's solution, folded. You can ask about any problem afterwards; the answer goes into the note beside it.

A problem you did not solve unaided comes back in the next recall check of its chapter.

`/interview list` shows every round with its result. `/interview abandon` drops a round you will not finish.

## Technique notes

Interview problems come down to a small set of tricks: symmetry, linearity of expectation, conditioning on the first step, the pigeonhole principle. A technique note collects one of them, from every course and every round, in `techniques/<Name>.md`:

- **The trick**, stated in general.
- **Reach for it when:** the features of a problem that should make you think of it. Under them, **In your words**: your own answers, each linked to the problem it came from.
- **Traps**, and **related** techniques.
- **Problems:** every lesson section and interview problem that used it, with your record on each (the quizzes of a section, ✓ or ✗, or an interview outcome). This part is written by the script; edit anything else in the note freely.

### How notes fill up

At the end of each lesson section the teacher names the techniques it used, in a line like this:

```markdown
*Techniques: [[Symmetry]] · [[Linearity of expectation]]*
```

The first time a technique comes up, the teacher writes its note and asks you one question: *what in this problem should have made you think of it?* Your answer goes under "In your words". Writing the cue yourself is what makes it come back when you meet a new problem.

`techniques/Techniques.md` lists every technique with its problem count and your record, weakest first.

### Commands

```
/techniques backfill   # tag the sections of the current course you finished before technique notes existed
/techniques list       # every technique, its aliases and your record
/techniques sync       # rebuild the problem lists and the index, e.g. after editing tags by hand
```

The backfill proposes the tags for every finished section in one table, for you to approve or correct, then writes them into the lesson notes. Interview problems are tagged when a round is set.

## Practice

Two commands bring back what you have learned, in forms you have not seen.

### Review

Every question you have missed becomes a card: a lesson quiz you got wrong or answered "I don't know", a recall-check question, an exam question that lost marks, an interview problem you needed hints for, a drill problem. `/review` asks the cards that are due, up to 10 at a time, oldest first.

- **Each card is a new question**, not the one you missed: the same idea in a different setting, or the same setting with one thing changed. Where the card came from is shown only after you answer.
- **Spacing.** A card first comes back the day after you missed it. Each time you get it right, the gap grows: 1, 3, 7, 16, then 35 days, after which it retires. A wrong answer brings it back the next day.
- **Your history counts.** The first time cards are made, every miss already in your notes becomes one, spread over the next two weeks so that no single day is a pile.

When you resume a lesson and cards are due, the opening question says how many. Review never starts unless you ask for it.

### Drill

`/drill` (or `/drill 12`) sets new problems mixed across all your technique notes, with nothing to say which technique each one is about. For each:

1. **Which technique does this problem need?** Pick from four of your technique names.
2. **Solve it**, with a typed answer.

The two are scored separately, so you can see whether you missed the trick or the working. Techniques where your record is weak come up more often, and a couple of strong ones are always mixed in, so you cannot assume every problem is a hard one. At the end you get `Recognised 6/8 · solved 5/8` and any techniques you mistook for others. Missed problems become review cards, and your recognition rate shows on each technique note and in the index.

A drill needs at least four technique notes; `/techniques backfill` makes them from the chapters you have done.

### Mental arithmetic

`/arith` runs a timed sprint in a popup over the terminal, like the Zetamac test that trading firms use as a screen.

```
/arith               # core, 120 seconds
/arith fractions     # one mode
/arith weak 60       # a mode and a length in seconds
/arith history       # your last scores per mode
```

| Mode | Questions |
|---|---|
| `core` | + − × ÷ with Zetamac's default ranges (2–100, and 2–12 × 2–100) |
| `fractions` | fractions as decimals (3/8 → 0.375; repeating decimals to 4 places) and percentages (15% of 240) |
| `powers` | squares 11–30, powers of 2 up to 2²⁰, cubes up to 12 |
| `estimate` | 2–3-digit × and ÷; anything within 2% counts |
| `mixed` | all of the above |
| `weak` | mostly the kinds of question you are slowest at |

Type the answer: a correct one moves on at once, with no Enter, and a wrong one waits until you fix it. Estimates are submitted with Enter. Tab skips a question; Esc stops early, and a stopped sprint does not count towards your best or your average.

The end screen shows your score, your best and your last-five average in that mode, and the three kinds of question that took you longest this time (for example `× 7` or `− borrow`, a subtraction that needs a borrow). Every answer's time is kept, so `weak` mode can draw mostly from the kinds you are slowest at, each compared with the other kinds of its own mode. The teacher writes a short summary into the day's practice note, with a tip when one kind stands out.

The popup needs tmux. Without it, run `python3 .claude/hooks/arith.py play <mode>` in another terminal, then `/arith last`.

### The practice note

Each day's review, drills and arithmetic summaries are in `practice/YYYY-MM-DD.md`, with the quizzes as in a lesson.

## Coding practice

Coding problems work like LeetCode. Each problem is a note in Obsidian and a starter file you open in your own editor. You write the function, run the file yourself as often as you like, and type `submit` when you think it is right. Hidden tests then judge it, and the teacher reviews a passing solution the way an interviewer would.

### A practice track

```
/code quant python
```

starts a track on a topic: the teacher asks what it is for (an interview, a course, a language) and how far you are, checks what that goal really tests, and proposes a syllabus of topics, each with a target level from 1 to 5. Once you approve it, the first problem is set. `/code next` sets the next one, and `/code` alone picks up an unfinished problem.

Each topic has a level. A problem passed on the first submission with no hints raises the level of its topics; asking for the solution lowers it and brings the topic back later. The next problem goes to the weakest topic below its target, and every fourth or so revisits an earlier one. When a problem needs an idea you have not met, a short reading and a quiz or two come first.

### A problem

```
practice/quant-python/
  quant-python.md        the track: topics with their levels, every problem with its status
  01-running-max.md      the problem, your submissions, the review
  01-running-max.py      your file: the signature and the examples, ready to run
```

The starter file has the function's signature and the examples under `if __name__ == "__main__":`, so `python3 01-running-max.py` shows your output beside the expected one. The hidden tests are in `.track/`, which Obsidian does not show.

| You type | What happens |
|---|---|
| `submit` | The tests run on your file. The note gets a folded box per submission: the cases passed, the speed result, and the first failing case with its call, the expected value, yours (or the error), and what your code printed. |
| `hint` | One step further: what to look at, then the approach, then a sketch of the hard part. Never the full code. |
| `/code solution` | After you confirm, the teacher's solution, walked through. The problem counts as solved with help. |

Some problems have speed tests: large inputs with a time limit on your function's call (building the input does not count). The limit is ten times what the teacher's own solution takes, and at least 0.2 s, so a sound solution passes easily and one of the wrong complexity misses it by far. A failed speed test shows your time beside the limit.

After a pass the review gives the time and space complexity, any edge case your code gets right only by luck, at most two rewrites in more idiomatic code, and the follow-up an interviewer would ask, which you can take on as the next problem.

Your code runs on your machine, one test at a time, each in its own process with a memory limit and a time limit, so an infinite loop costs a few seconds. A track can use another Python, such as a virtual environment with numpy and pandas: the teacher sets it when the track is created.

### Code tasks in a lesson

In a lesson on a programming topic, the check after a section can be a code task instead of a quiz. Its files go in a folder beside the note (`lessons/python-types — code/`), and the lesson note gets one folded box where the task was set, titled with the outcome (`✓`, `✗`, or `✗→✓` when it passed after failing), with a line per submission. A task you needed the solution for counts as a missed question: the teacher re-teaches the step that went wrong, then sets a variant.

## The lesson note

A note holds the lesson and nothing else. A session writes to a note once you point it there, with `/md-log`, `/lesson resume`, `/course next`, `/course study` or `/exercise`; a session you have not pointed anywhere is not mirrored.

Each session starts with a `## Session — <date>` heading. Under it:

- your prompts, as `> **You:** …` quotes (questions are asides, see below);
- the teacher's prose, written bare;
- quizzes, as folded boxes titled by the result and the question (see [Quizzes in the note](#quizzes-in-the-note));
- diagrams, as `![[viz-….png|500]]` embeds of images in `viz/`, and figures cropped from a course's book (`![[pml1-fig-2-7.png|600]]`).

**Kept out of the note:**

- housekeeping commands and their replies, such as `/course list`, `/course status` or `/lesson pause`;
- session chatter ("I'll load the skill", "waiting on your answer");
- pacing words (`ready`, `ok`, `next`, `probe`);
- the resume question, checkpoints and status lines from the scripts.

`/md-unlog` stops mirroring altogether.

If you ask a question in the quiz popup with `?`, the note shows an "Asked first" box with the quiz and your question, the teacher's answer, then the graded quiz.

### Questions you type

A question you type at the prompt is written with its answer as one `[!aside]` callout, titled by your question and foldable. It sits next to what it asks about. A question about Example 9 goes directly after Example 9 and the paragraphs that discuss it, before the next part of the section. A question about a whole section goes just before that section's key idea, and a general question goes where you asked it. A second question about the same example goes below the first.

The teacher picks the place by starting its reply with a marker such as `%% aside: ex-9 %%`, which you see in the terminal and Obsidian hides. A quiz that follows the answer stays at the end of the note, with the rest of the lesson.

### Definitions, theorems and notation

Definitions, theorems, proofs, notation lists, remarks and intuition boxes are callouts, styled by the CSS snippet the installer adds to the vault:

```markdown
> [!definition] Best response
> A strategy $s_i^*$ is a **best response** to $s_{-i}$ if …

> [!notation]
> - $S_i$ — the set of strategies available to player $i$
```

Every symbol in an equation is defined in the text before it appears, or in a `[!notation]` callout directly after the equation.

### Numbered equations and examples

Equations the lesson refers back to are numbered and linkable, with no plugin:

```markdown
$$
p(\theta \mid x) = \frac{p(x \mid \theta)\,p(\theta)}{p(x)} \tag{3}
$$
^eq-3

By [[#^eq-3|(3)]], the posterior is proportional to likelihood times prior.
```

- Numbers run through the whole note. A resumed session continues from the last one.
- In a course note, equations carry the book's numbers instead: `\tag{2.51}` with the id `^eq-2-51`.
- Worked examples are `> [!example] Example n — …` callouts with a `^ex-n` id, cited as `[[#^ex-n|Example n]]`.
- Each section ends with a `> [!summary] Key idea` callout. Read only these to skim a note.
- Calculations in an example are set out one step per line, so each line can be checked on paper.

### Exporting to PDF

Obsidian's own *Export to PDF* keeps the formatting, but links inside the note (to figures, equations, examples) do nothing in the PDF. Use the community plugin **Better Export PDF** instead. It also gives the PDF an outline of the sessions and sections.

1. Install it under Settings → Community plugins → Browse → "Better Export PDF".
2. Let block links jump as well as heading links. Run this from the vault root, and again after each update of the plugin:
   ```bash
   python3 .claude/scripts/patch-better-export-pdf.py
   ```
   Then turn the plugin off and on.
3. Export from the note's ⋯ menu → *Better Export PDF*.

The callout snippet carries the print rules: a heading stays on the page of the text it introduces, a callout, an equation or a figure is not split across pages unless it is longer than one, and quizzes print open.

## Commands

| Command | What it does |
|---|---|
| `/md-log <note.md>` | Mirror this session into a note, including what was said so far. |
| `/md-unlog` | Stop mirroring. |
| `/lesson pause` | Save a checkpoint for the lesson in progress. |
| `/lesson resume <note.md>` | Continue a lesson from its checkpoint. |
| `/lesson status <note.md>` | Show where a lesson stands. |
| `/lesson reset <note.md>` | Start a lesson over; the note and checkpoints are moved to a trash folder. |
| `/course new <book.pdf> [name]` | Map a textbook and set up a course. |
| `/course next` | Study the next section of the current course, or resume it. |
| `/course study <section>` | Study a given section, for example `4.2`. |
| `/course status` | Progress of the current course. |
| `/course toc [chapter]` | The syllabus, or one chapter's sections, with progress marks. |
| `/course list` | All courses, the current one marked. |
| `/course use <name>` | Make another course the current one. |
| `/course select <spec>` | Change the syllabus: `all`, `unstarred`, or chapters, sections and ranges. |
| `/course assess <exercise>...` | Mark exercises as assessed coursework. |
| `/course solutions <policy>` | When full solutions may be shown: `never`, `after-attempt` or `on-request`. |
| `/exercise <id>` | Step-by-step help with an exercise from the course's book. |
| `/exam [chapter \| note.md]` | Set an exam paper on a chapter (default: the one finished last) or a lesson note. |
| `/exam submit` | Hand in the open paper to be graded. Typing `submit` does the same. |
| `/exam reopen <paper>` | Take back a paper you submitted but that is not graded yet, to change it and submit again. |
| `/exam abandon <paper>` | Drop a paper you will not finish; it stays on file. |
| `/exam list` | Every exam paper, with its status and score. |
| `/interview [short \| standard \| long]` | A timed mock interview on the units finished so far. |
| `/interview stop` | End the round early and get the scorecard. |
| `/interview list` | Every round, with its result. |
| `/interview abandon` | Drop a round you will not finish. |
| `/techniques backfill [course]` | Tag the finished sections of a course with their techniques, once. |
| `/techniques list` | Every technique note, with its aliases and your record. |
| `/techniques sync` | Rebuild the technique notes' problem lists and the index. |
| `/review` | Ask the review cards that are due, each as a new variant. |
| `/drill [n]` | Mixed, unlabelled problems: name the technique, then solve it (8 by default). |
| `/arith [mode] [seconds]` | A timed mental arithmetic sprint (core by default, 120 s). |
| `/arith last`, `/arith history [mode]` | The last sprint's summary; recent scores per mode. |
| `/code <topic>` | Start a practice track on a topic, or set the next problem in it. |
| `/code next` | The next problem of the current track. |
| `/code submit` | Run the hidden tests on the newest unfinished problem (or the one you name). Typing `submit` does the same, unless an exam paper is out. |
| `/code hint` | The next hint for the problem. Typing `hint` does the same. |
| `/code solution` | Show the teacher's solution, after you confirm. |
| `/code status` | Unfinished problems; `/code status <track>` for a track's levels and recent results. |
| `/code list` | Every track and lesson task, with its status. |

Words you type at a prompt: `ready` when you have read a section, `probe` at a chapter overview to be tested first, `submit` and `hint` on a code task, or any question.

## Repository layout

```
.claude/
  CLAUDE.md              house rules for the teacher: teach, do not narrate, plain technical English
  settings.json          hooks, pre-approved commands, and the setting that keeps long quizzes in the foreground
  mcp.json               registers the quiz server; install.sh copies it to <project>/.mcp.json
  skills/
    teach/               the teaching philosophy and process (the heart of it)
    visualize/           when and how to ask for a diagram
    lesson/              /lesson pause | resume | status | reset
    course/              /course new | next | study | status | toc | list | use | select | assess | solutions
    exercise/            hints in steps for a textbook's exercises
    exam/                /exam: set a paper, grade it, discuss the feedback
    code/                /code: practice tracks and code tasks, hints, reviews
    md-log/, md-unlog/   /md-log <file>, /md-unlog
  agents/
    researcher.md        web research and fact verification
    mermaid-maker.md     draws, renders, looks at and publishes a Mermaid diagram
    svg-maker.md         the same for hand-written SVG (geometry, plots)
  mcp/
    quiz_server.py       the quiz tool: an MCP server with no dependencies
    quiz_popup.py        the popup, shown with tmux display-popup
    latex_text.py        LaTeX to Unicode, for the popup
  hooks/
    md_log.py            mirrors the session into the note
    quiz_block.py        the folded quiz box in a note: writes it, reads it back, converts older notes
    lesson.py            checkpoints and the resume brief
    book.py              maps a textbook PDF to page ranges; keeps a course's syllabus and progress
    figures.py           embeds the book figures a course note names, and links the mentions
    sections.py          links "§1.2" references to the heading of that section
    exam.py              exam papers: paths, validation, marking, feedback, results
    coding.py            code tasks: tracks, checking the tests, running a submission, the records
    coding_runner.py     runs one test case of a code task in a limited child process
  tests/                 unit tests for the scripts: python3 -m unittest discover -s tests
  scripts/
    install.sh           one-off setup
    render-mermaid.sh    Mermaid to PNG
    render-svg.sh        SVG to PNG
    patch-better-export-pdf.py  lets block links jump in PDFs exported with Better Export PDF
  visual-tools/          package.json for the Mermaid renderer
  obsidian/
    learn-callouts.css   styles for definition, theorem, proof, notation and the other callouts, and print rules
  docs/
    architecture.md      how the pieces fit and what is fragile
    worklog.md           running notes on the state of the project
```

[docs/architecture.md](docs/architecture.md) explains how the pieces fit, why they are built this way, and what is fragile.

## Customising

- **How it teaches.** The teach skill is written for one learner. Edit `skills/teach/SKILL.md` to fit how you learn.
- **The teacher's voice.** `CLAUDE.md` holds the house rules.
- **The teacher's model.** The teacher is the Claude Code session itself, so it uses that session's model. Use `/model` in a session, or set `"model"` in `.claude/settings.local.json` to pin one for this folder only.
- **The subagents' model.** The researcher and the diagram makers are set to `sonnet` in `agents/*.md`. Change `model:` there.

## Troubleshooting

**The quiz is a one-line form with "Your answer: not set", not a popup.**
Claude Code was probably started outside tmux, and the teacher says so after the first quiz. `.claude/md-log-state/quiz-server.log` gives the reason. Restart Claude Code from inside tmux; the quiz server is started with the session. Until then, read the full question in the note, where it is open while you answer.

**There is no quiz tool; questions come as plain prompts.**
Run `/mcp` and check that `quiz` is listed and enabled. Check that `.mcp.json` exists in the project root.

**"The quiz is running in the background."**
Claude Code moves tool calls longer than two minutes to the background. `settings.json` turns that off for this project (`CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS=0`). If you see the message, the setting is not in effect: restart Claude Code from the project folder.

**The teacher's text is missing from the note.**
The mirror reads Claude Code's session transcript, whose format is internal and may change between releases. Prompts and quizzes are not affected. Regenerate a note with `python3 .claude/hooks/md_log.py rebuild <out.md> <transcript.jsonl>...`.

**Hooks do not fire.**
Claude Code must be started from the folder that contains `.claude`, not from a subfolder.

**A change I pulled has no effect.**
Skills and settings are read when a session starts. Start a new session.

## Credits

Teaching philosophy, skills and agent prompts: [Amos Blomqvist](https://github.com/amosblomqvist/learn).
Port to Claude Code: Lachlan Burton, with Claude.
