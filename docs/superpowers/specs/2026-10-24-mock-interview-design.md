# Mock interview — design

Date: 2026-10-24. Status: approved in conversation, awaiting spec review.

## Purpose

The gb course's goal is to pass quant research interviews: solve unseen problems fast and explain the reasoning out loud. Lessons, quizzes and exams build the understanding; none of them practises the interview itself. A mock interview is a timed round of problems the learner has not seen, on topics they have studied, with an interviewer who behaves like a real one, ending with a scorecard.

This is the second of five planned pieces (typed answers, mock interview, technique notes, practice with `/drill` and `/review`, mental arithmetic).

**Said by the learner:** they were already thinking about a mock interview mode; the course goal is to solve unseen problems fast and explain the reasoning out loud.

**Agreed in the design conversation:**

- A session is a timed round: 2–4 problems back to back, a clock running, a scorecard at the end.
- Problems are new, written for the round, on the units the learner has finished, and not labelled by topic.
- The interviewer behaves like a real one: mostly quiet, asks for justification, points out an error, offers a nudge when the learner is stuck, asks a follow-up after a solve. Every nudge, and every pointed-out error, counts as a hint.
- Each problem has a time budget; past it the interviewer closes the problem and moves on.
- Approach: a state script (`hooks/interview.py`) plus a `UserPromptSubmit` hook that puts the clock in front of the model on every message, plus a live clock in the tmux status bar.

**Assumed and not contradicted:** rounds are for the current course only; text in the terminal (no voice); final answers are checked with the typed-answer checker (`mcp/answer_check.py`).

## Lengths

| Length | Problems | Per problem | Round |
|---|---|---|---|
| short | 2 | 12 min | 24 min |
| standard | 3 | 12 min | 36 min |
| long | 4 | 12 min | 48 min |

## Commands

The `interview` skill (`/interview`, or "give me a mock interview") drives `hooks/interview.py`:

```
interview.py new --length short|standard|long   plan a round: paths, budget, studied units, past techniques
interview.py check                               validate the problem file; the round becomes ready
interview.py start --session <id>                start the clock and the status bar; print problem 1
interview.py hook                                (UserPromptSubmit) the clock line, during a running round
interview.py hint [--error]                      record a nudge (or a pointed-out error); print the next prepared nudge
interview.py answer "<text>" [--followup]        check a final answer: CORRECT, WRONG or UNREADABLE
interview.py next [--gave-up]                    close the current problem; print the next one, or ROUND OVER
interview.py stop                                end the round early
interview.py finish --marks <file>               write the scorecard into the note; restore the status bar
interview.py clock                               one short line for the tmux status bar
interview.py abandon                             drop a round that was set or started
interview.py list                                every round of the course, with its result
```

Every command acts on the current course (`book.py`) and its one open round. `new` refuses while a round is open (an `OPEN:` line, as `exam.py`), or when no unit is done.

## Setting the round

Nothing of the setting reaches a note: the skill unlinks the mirror first (`md_log.py unlink`).

1. The skill asks the length with one `AskUserQuestion` (header `Interview`): **Short (2 problems, about 25 minutes)**, **Standard (3 problems, about 40 minutes)**, **Long (4 problems, about 50 minutes)**.
2. `interview.py new --length <length>` prints:
   - `NOTE:` `courses/<slug>/interviews/<slug>-interview-<n>.md`
   - `PROBLEMS:` `courses/<slug>/.interviews/<slug>-interview-<n>.json`, the file the model writes
   - `BUDGET:` the number of problems and the minutes per problem
   - `UNITS:` one line per finished unit (done or shaky): its id, title, section link (`<note stem>#<heading>`), and the text of the `Key idea` callouts under that heading in the chapter note. The model writes problems from these, not from the book's pages.
   - `PAST TECHNIQUES:` the `technique` of every problem in earlier rounds of the course, so a round does not repeat them
3. The model writes the problem file:

```json
{"problems": [
  {"id": "p1",
   "statement": "<the problem, as the interviewer will say it; LaTeX as in a note>",
   "answer": "21", "variables": {}, "answerLatex": "21",
   "solution": "<a worked solution in markdown, a few lines>",
   "technique": "<the trick, in a few words: first-step conditioning>",
   "units": ["2.4"],
   "hints": ["<gentle>", "<stronger>", "<nearly the method>"],
   "followup": {"statement": "…", "answer": "…", "variables": {}, "answerLatex": "…", "solution": "…"}}
]}
```

   - New problems in the style of quant interviews, solvable with the listed units' ideas. Not a worked example or exercise from the book, and not a problem from an earlier round.
   - Every answer, the follow-up's too, is verified before the round by running code: a computation, or a simulation for a probability or an expectation.
4. `interview.py check` validates the file and fails with one line per problem: the right number of problems for the length; ids `p1…pn`; a non-empty statement, solution and technique; `answer` (and the follow-up's) readable by `answer_check` with its `variables`, and defined at the test points; `units` all finished units of the course; exactly three hints. When it passes, the round is `ready`.

## The round

**Start.** `interview.py start --session ${CLAUDE_SESSION_ID}` records the session and the start time, sets the status-bar clock, and prints problem 1. The skill then links the note (`md_log.py link "<note>" --session ${CLAUDE_SESSION_ID} --from-now --no-header`), and the reply is a one-line greeting, the heading `### Problem 1`, and the statement.

**The clock line.** `interview.py hook` is registered in `settings.json` under `UserPromptSubmit`. It reads the hook's JSON from stdin and prints nothing unless a round is running and its session is this session. Otherwise it prints one line, which Claude Code adds to the model's context:

```
INTERVIEW: problem 2 of 3 · 9:40 of 12:00 · hints 1 · round 21:15 of 36:00 · TIME NEARLY UP
```

The flag at the end is the first that applies:

| Flag | When |
|---|---|
| `ROUND TIME UP` | the round's time is spent: close this problem now and finish |
| `TIME UP` | the problem's 12 minutes are spent: close it |
| `TIME NEARLY UP` | 75% of the problem's time is spent: give the strongest useful nudge |
| `NUDGE IF STUCK` | 50% spent and no hint yet |
| `FOLLOW-UP` | the main answer is correct: the follow-up is open |

**The status bar.** Inside tmux, `start` sets the session's `status-right` to `#(python3 <path>/interview.py clock)` and `status-interval` to 1, both as session options (`tmux set-option`, not `-g`). `clock` prints `P2/3 9:40/12:00`, then `TIME UP` once the problem's time is spent. `finish`, `stop` and `abandon` unset both options (`set-option -u`), which restores the learner's own setting. Outside tmux nothing is set.

**The interviewer** (the skill's rules):

- Neutral, brief, professional. While the learner is making progress a reply is a few words ("Go on.", "OK.", "Why?"). It never teaches during a problem, never names the technique, and never says whether an intermediate step is right unless asked "is that right?", and then only "yes" or the pointed-out error.
- Asking the learner to justify a step is not a hint.
- Pointing out an error ("Are you sure about the second term?") is a hint: `interview.py hint --error`.
- A nudge comes when the learner is stuck (no progress over two messages, or they say so), or on `TIME NEARLY UP`. `interview.py hint` records it and prints the next prepared nudge, which the interviewer adapts to where the learner is.
- A final answer is always checked: `interview.py answer "<what the learner said>"`, rewritten into the checker's syntax if the learner wrote it in words. `CORRECT`: "Right." and, with at least 2 minutes left on the problem, the follow-up (`answer --followup` for its answer). `WRONG`: "That's not right." and the learner goes on. `UNREADABLE`: ask them to state it as a number or a formula.
- On `TIME UP`, or when the learner gives up: two or three sentences on how the problem goes, then `interview.py next` (`--gave-up` if they did) and the next problem under its own `### Problem n` heading.
- `/interview stop`, or the learner saying they want to stop: `interview.py stop`, then the scorecard.
- Questions about the problem's meaning are answered as an interviewer would (clarify the setup, do not hint).

**Outcomes**, computed by `next` and `stop` from what was recorded, never chosen by the model:

| Outcome | When |
|---|---|
| `solved` | a correct main answer, no hints |
| `hinted` | a correct main answer after one or more hints |
| `unsolved` | no correct main answer when the problem closed |
| `not reached` | the round ended before the problem was given |

The follow-up's result is `solved`, `unsolved` or `not asked`.

## The scorecard

After the last problem (or `stop`, or `ROUND TIME UP`), the model writes the marks file beside the problem file, `<slug>-interview-<n>.marks.json`:

```json
{"problems": {"p1": "<how the learner reasoned and explained on this problem: two to three sentences>"},
 "communication": {"structure": "…", "assumptions": "…", "sanity checks": "…", "clarity": "…"},
 "work_on": ["<one concrete thing>", "…"],
 "revisit": {"<note stem>#<heading>": "<what to revisit there, in a clause>"}}
```

`interview.py finish --marks <file>` appends to the note:

```markdown
### Scorecard

| | Outcome | Time | Hints | Follow-up | Technique |
|---|---|---|---|---|---|
| Problem 1 | solved | 6:12 | 0 | solved | first-step conditioning |
| Problem 2 | hinted | 11:40 | 2 | not asked | linearity of expectation |

**How you explained:** structure — …; assumptions — …; sanity checks — …; clarity — …

**Work on:** …

**Revisit:** [[gb-ch02#2.4 …|§2.4]] — …

> [!example]- Problem 1 — solution
> <the statement, the solution, the follow-up and its solution>
```

and sets the note's frontmatter (`interview`, `number`, `date`, `length`, `status: finished`, `solved: 1/2`). The reply after `finish` is short: the outcomes in one line, the one thing most worth working on, and that questions about any problem are welcome. Questions after the round are answered as asides in the note, as after an exam.

## Into recall checks

A problem whose outcome is not `solved` is a miss. `lesson.py summary` (the resume brief) prints, after `EXAM MISSES`, the misses of the newest finished round whose units belong to the note being resumed (or the chapter before it, as `lesson.review_sources`):

```
INTERVIEW MISSES (gb-interview-2): re-probe these first
  - Problem 2 hinted §2.4 — first-step conditioning: <statement, cut at 90 characters>
```

The teach skill already takes everything listed under the brief's miss headings first in a recall check; one word in that sentence adds `INTERVIEW MISSES`.

## Files and state

- `courses/<slug>/interviews/<slug>-interview-<n>.md` — the note: frontmatter, the transcript (mirrored), the scorecard.
- `courses/<slug>/.interviews/<slug>-interview-<n>.json` — the problem file, written by the model.
- `courses/<slug>/.interviews/<slug>-interview-<n>.state.json` — the script's record: status (`set`, `ready`, `running`, `ended`, `finished`, `abandoned`), length, session, start time, and per problem the start and end times, hints (time, nudge or error), answers (time, text, verdict, main or follow-up) and outcome.
- `courses/<slug>/.interviews/<slug>-interview-<n>.marks.json` — the marks.
- `skills/interview/SKILL.md` — the skill; `settings.json` — the hook and the `Bash(python3 .claude/hooks/interview.py *)` permission.
- README: an `Interviews` section; `docs/architecture.md`: the script, the hook and the status bar.

## Testing

- `tests/test_interview.py`, with a fake clock (the script reads time through one function the tests replace) and a temporary course from `tests/_vault.py`:
  - `new`: paths, numbering, budget, finished units with their key ideas, past techniques, refusal with an open round or no finished unit.
  - `check`: each validation failure, and a valid file.
  - the hook line at each threshold, and silence for another session or no running round.
  - `hint` order and counting; `answer` verdicts through `answer_check`; follow-up availability.
  - outcomes from `next`, `next --gave-up` and `stop`, including `not reached`.
  - `finish`: the scorecard table, times, frontmatter, solutions folded; refusal of a marks file without every problem.
  - `INTERVIEW MISSES` in `lesson.py summary` for the right chapter note.
  - the tmux commands issued by `start` and `finish` (the runner is stubbed).
- One short round driven by hand in tmux before hand-over.

## Out of scope

- Rounds on a lesson note outside a course; problems from topics not yet studied.
- Voice; a separate chat window.
- Scoring communication with numbers; the scorecard's communication part is written feedback.
- Problems with an answer the checker cannot read (a proof, a strategy in words). Such a problem stays out of a round; the follow-up may ask "why", but its graded part is a value or a formula.
