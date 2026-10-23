# Coding practice — design

Date: 2026-10-23. Status: approved in conversation, awaiting spec review.

## Purpose

The learner can practise programming the way LeetCode works. They write a solution in a starter file in their own editor, type `submit`, and hidden tests judge it. The teacher sets the problems, gives hints in steps, and reviews passing code the way an interviewer would. The first use is basic Python manipulation of the kind quant interviews test. The mechanism is general: it serves any coding topic, and later other languages.

**Said by the learner:**
- One mechanism for every kind of coding practice: algorithm problems, coding inside lessons, and learning a language. The immediate need is basic Python for quant interviews; the tool should generalise beyond that.
- Theory and practice mixed: for example, a multiple-choice question on data types, then code to write.
- The problem is a note in Obsidian, and the solution is a real `.py` file beside it.
- The teacher writes the problems and adapts them to the learner.
- A submission gives the first failing case, speed tests, and a review after passing.

**Agreed in the design conversation:**
- **Approach A.** The tests are data, and a script, `code.py`, does everything that must be exact: validating a task, running it, timing it, recording the result. The teacher writes the problems, hints and reviews.
- **A code task can be set in two places, on one mechanism:**
  - in a *practice track*, where the problems come first and quizzes come where a problem needs them;
  - in a *lesson or course*, as the teach skill's Apply step.
- **The record of a task lives in the task note,** and in the lesson note or the track index.

**Assumed and not contradicted:**
- The learner can run their file at any time. The examples are under `__main__`, and the hidden tests run only on `submit`.
- Resubmitting is unlimited. Hints come on request. The full solution comes only with `/code solution`.
- The learner's code runs locally with time and memory limits, but no further sandbox.
- Only Python is built now.
- There are no timed attempts.

## Files

**A track:**

```
practice/<track>/
  <track>.md                 track index (written by code.py)
  NN-<slug>.md               task note
  NN-<slug>.py               starter file: the learner's solution
  .track/
    state.json               syllabus, topic levels, task records, interpreter
    NN-<slug>.py             hidden tests
    submissions/NN-<slug>-<k>.py   snapshot of submission k
```

**Tasks inside a lesson note** `<dir>/<note>.md`. The lesson's tasks are numbered in their own sequence.

```
<dir>/<note> — code/
  NN-<slug>.md, NN-<slug>.py
  .tests/state.json, .tests/NN-<slug>.py, .tests/submissions/…
```

Obsidian does not show dot-folders. A `.py` file is shown in Obsidian only with *Detect all file extensions* on, so the task note gives the file's path as text.

## The task

**Task note** (written by the teacher; `code.py` appends to it):
- `# <title>`, then an italic line: `*<track or lesson> · task NN · level L · <topics>*`.
- The statement, the examples (input → output), the constraints, and the target complexity when there is one.
- `**Your file:** `<path>`. Run it with `python3 <name>.py`, then type **submit**.`
- `## Submissions`: `code.py` appends one folded box per submission, as described under *Submit*.
- `## Review`: the teacher's debrief, which reaches the note through the mirror.

**Starter file:** the function signature with type hints and `...` as its body, then `if __name__ == "__main__":` with the examples printed and the expected output in comments.

**Hidden tests** (a Python module):

| Name | Required | Meaning |
|---|---|---|
| `FUNCTION` | yes | The name of the function the learner writes. |
| `reference(*args)` | yes | A correct solution. |
| `CASES` | yes | A list of `{"name", "args", "expected"}`. |
| `slow(*args)` | no | A correct but slow solution, which the speed cases must fail. |
| `large()` | no | Yields speed cases `{"name", "args"}`; `expected` is `reference(*args)`. Seeded, so the cases are the same each run. |
| `check(got, expected, args)` | no | Replaces the default comparison. |

**Default comparison.** `==`, except that floats (in nested lists, tuples and dict values too) compare with `math.isclose(rel_tol=1e-9, abs_tol=1e-12)`. numpy arrays compare with `numpy.allclose` when numpy is importable.

## code.py

These commands follow `exam.py`'s style: one brief, machine-readable output with a line per fact.

| Command | What it does |
|---|---|
| `track new <slug> --title "<t>" [--python <path>]` | Creates the folder, the index note, and `state.json` with an empty syllabus. |
| `track syllabus <slug> --file <json>` | Sets the syllabus: `[{"topic", "target": 1-5}]` in order. Levels start at 1. |
| `plan (--track <slug> \| --note <lesson.md>)` | Prints the paths of the next task (`NOTE`, `STARTER`, `TESTS`), its number `NN`, and in a track the brief: topic levels, the last 8 results and the suggested next topic. Writes nothing. |
| `check <task.md> --topics t1,t2 --level L` | Validates the task and registers it as open. In a lesson it writes the open code box. Prints `OPEN`, or refuses with one line per problem. |
| `submit [<task.md>]` | Runs the tests and records the result (see *Submit*). |
| `hint [<task.md>]` | Counts a hint and prints the count. |
| `solution [<task.md>]` | Marks the task "solution shown" and prints the reference's path. |
| `status [<track> \| <task.md>]` | A track's brief, or a task's record. With no argument: the open tasks. |
| `list` | Every track and lesson task under the working directory, with its status. |

`<task.md>` is optional wherever the open task is the only one.

**`check` refuses a task when:**
- a required name is missing;
- the starter file does not define `FUNCTION`;
- `reference(*args)` differs from any case's `expected` under the comparison;
- `large()` yields cases and `slow` is given, but `slow` runs within the limit on any of them;
- a topic is not in the track's syllabus (in a track).

**Speed limit.** It is fixed at `check`:
- The reference runs each `large()` case 3 times, and the median is its time.
- `limit = max(0.2 s, 10 × median)`, stored in the task record.
- `slow` is run with a kill at `2 × limit`, and must exceed `limit`.

**Task statuses:** `open`, `passed`, `helped` (passed after `solution`), `shown` (`solution` used, not passed), `abandoned`.

**Task record** in `state.json`: `{"n", "slug", "topics", "level", "status", "submissions", "hints", "limit", "created", "passed_at"}`.

## Submit

**Running the cases:**
- Each case runs in a child process: `<python> hooks/code_runner.py <tests> <solution> <case index | large:i>`. `<python>` is the track's interpreter, default `python3`, run without `-I`, so user site-packages stay importable.
- The child sets `RLIMIT_AS` to 2 GiB and `RLIMIT_CPU` to the kill time. It imports both files by path and calls the function on `copy.deepcopy(args)`, timing the call with `time.perf_counter`. It compares the result itself, and prints one JSON line: `passed`, `got` and `expected` (as `repr`, cut to 300 characters), `seconds`, `stdout` (the first 20 lines), and `error` (the exception's type and message, and its traceback cut to the frames in the solution file).
- **Kill times:** a correctness case after 5 s; a speed case after `3 × limit + 1 s`. A killed case is reported as `timeout`.
- All of `CASES` run first. `large()` cases run only if every correctness case passed.

**Writing the result:**
- A folded box is appended under `## Submissions`:
  - `> [!success|code]- ✓ Submission k — p/p passed · speed ✓ (<t> ms, limit <L> ms)`; or
  - `> [!failure|code]- ✗ Submission k — p/n passed`, with the first failing case's name, input, expected value, the learner's value or error, and printed output.
- The solution file is copied to `submissions/NN-<slug>-<k>.py`.
- **In a lesson:** the task's box in the lesson note is replaced in place, found by its exact text as the quiz server does, or appended if that text is gone. Its title is `✓ Task NN: <title>`, `✗ Task NN: <title>`, or `✗→✓ Task NN: <title>` when it passed after failing. Inside: the statement's first paragraph, a link to the task note, and one line per submission.
- **In a track:** the index row for the task is updated (status, submissions, hints), and the topic levels change on the first pass, on `solution`, or not at all:

| Outcome | Change to each of the task's topics |
|---|---|
| passed on submission 1 with 0 hints | level +1, up to 5 |
| passed otherwise | unchanged |
| `shown` | level −1, down to 1, and the topic is queued to revisit |

**The brief printed for the teacher:** `RESULT passed|failed`, `FIRST FAIL …` when failed, `REVIEW <snapshot path>` when passed, `LEVELS …` in a track, and `NEXT <topic>` in a track.

## The code skill

`skills/code/SKILL.md` is invocable as `/code` and by the model when the learner asks to practise coding, says `submit` or `hint` with a task open, or asks for the solution. It follows the teach skill's principles and its no-narration rule.

**A new track.**
1. An opener: its own reply, ending with the `ready` line.
2. One `ask_user_question` on the goal, the current level, and which libraries are in scope.
3. A syllabus, proposed after the `researcher` checks what the stated goal (for example, quant interviews) actually tests. The learner approves it, then `track new` and `track syllabus` record it.
4. An optional placement probe of 2 or 3 quizzes.

**Each problem.** Run `plan`, and choose the topic it suggests unless a revisit is due (every fourth problem). Then:
1. If the problem needs an idea that is not established, write a reading first (ending with the `ready` line), then one or two quizzes.
2. Write the hidden tests first (with `slow` when a complexity target is set), then the task note and the starter.
3. Run `check`; fix and rerun until it prints `OPEN`. Link the session's mirror to the task note.
4. Reply with one line naming the file and the note.

**Submit.** Run `code.py submit`.
- **Failed:** say in one line which case failed and offer a hint. Do not explain the bug unasked.
- **Passed:** Read the snapshot and write the review. The review gives:
  - the time and space complexity;
  - any edge case the code handles only by luck;
  - at most two concrete rewrites in more idiomatic code;
  - the follow-up an interviewer would ask, offered as a variant task.

**Hints.** Run `code.py hint`, then give the next step: 1. what to look at; 2. the approach or data structure; 3. a sketch of the hard part. Never the full code.

**`/code solution`.** Ask for confirmation with one `ask_user_question`, then run `code.py solution`, then walk through the reference.

**`submit` with an exam paper open too.** The code skill and the exam skill both run `code.py status` and `exam.py list`. If both have something open, ask which with one `ask_user_question`.

**In a lesson** (teach skill change). For a programming topic, the Apply step may be a code task, with `plan --note` and `check`:
- `passed` or `helped` counts as a passed Apply. The review is two or three sentences.
- `shown` counts as a missed Apply: re-teach the step that went wrong, then set a variant task.

**Resuming.** `/code` with no argument runs `code.py status` and continues the open task, or plans the next one.

## Other changes

| File | Change |
|---|---|
| `hooks/md_log.py` | `code` joins `ADMIN_COMMANDS` (`list`, `status`). A typed `hint` is a pacing word, not logged; typed `submit` already is. |
| `hooks/lesson.py` | The resume brief of a lesson note adds `code tasks: n (✓ m)` from the note's `|code` boxes. |
| `skills/exam/SKILL.md` | Typed `submit` with a code task open as well: ask which. |
| `skills/teach/SKILL.md` | The Apply step for a programming topic may be a code task (see above). |
| `settings.json` | `Bash(python3 .claude/hooks/code.py *)` pre-approved. |
| `obsidian/learn-callouts.css` | `|code` boxes are styled like `|quiz` boxes. |
| `README.md` | A "Coding practice" section, Commands rows, and the repository layout. |
| `docs/architecture.md` | A "Coding practice" section, the state files, and a fragile-parts entry for timing noise. |

## Tests

Standard library only, in `tests/test_code.py` and `tests/test_code_runner.py`, using `tests/_vault.py`:

- **`check`:**
  - accepts a valid task;
  - refuses a wrong `expected`, a missing `FUNCTION` in the starter, a `slow` within the limit, and an unknown topic;
  - stores `limit = max(0.2, 10 × median)`.
- **The runner:**
  - a pass;
  - a wrong answer, reported as the first failing case;
  - an exception, with its traceback cut to the solution's frames;
  - an infinite loop, killed and reported as `timeout`;
  - printed output captured, up to 20 lines;
  - float tolerance, and a custom `check`;
  - a solution that mutates its argument does not change the stored case;
  - speed cases skipped after a correctness failure;
  - a quadratic solution failing a speed case that a linear one passes.
- **`submit`:**
  - the box appended under `## Submissions`;
  - the snapshot, numbered by submission;
  - the lesson box replaced in place (and appended when its text is gone), with titles `✗`, then `✗→✓`;
  - the track row and the level changes for each outcome in the table.
- **`hint` and `solution`:** the counts and statuses.
- **`md_log`:** typed `hint` and `/code list` are not logged.
- **`lesson.py`:** the code-task tally.

## Risks

- **Timing noise.** A loaded machine can make a sound solution miss its limit. The 10× factor and the 0.2 s floor make this rare. A speed failure prints the measured time beside the limit, so the teacher can tell noise from complexity, and a resubmit costs nothing.
- **The teacher's tests are only as good as its cases.** `check` proves that every case agrees with the reference, but not that the cases cover the edge cases. The skill asks for empty, single-element, duplicate and boundary cases in every task, and the review names an edge case the tests missed when it sees one.
- **Hidden tests can be read.** They sit in a dot-folder the learner could open. This is a study tool, so the honour system is enough.
- **Obsidian and `.py` files.** Whether a link to a `.py` file opens in an external editor depends on Obsidian's settings, so the note gives the path as text.
