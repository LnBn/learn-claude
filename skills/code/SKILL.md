---
name: code
description: Practise programming — a track of coding problems, or a code task inside a lesson — written by the learner in a starter .py file and judged by hidden tests on submit, with hints in steps and an interviewer's review after a pass. Use with `/code [topic | next | submit | hint | solution | list | status]`, when the learner asks to practise coding or interview problems ("give me some Python practice", "quant interview questions"), or says `submit` or `hint` while a code task is unfinished.
argument-hint: [topic | next | submit | hint | solution | list | status]
allowed-tools: Bash(python3 .claude/hooks/coding.py *), Bash(python3 .claude/hooks/md_log.py *), Bash(python3 .claude/hooks/exam.py list), Write
---

Arguments: `$ARGUMENTS`

A code task is a problem the learner solves in a real file, in their own editor. Hidden tests judge it when they type `submit`. `coding.py` does everything that must be exact: paths, checking your tests against your reference solution, the speed limit, running the submission, and recording the result. You write the problem, the tests, the hints and the review. Everything you explain follows the `teach` skill (ground it in what is established, motivate it, no narration); load it if it is not loaded. The work is the learner's: you never write their solution for them, except through `/code solution`.

| Arguments | Section |
|---|---|
| a topic or a track name | **A new track** if `coding.py list` has no such track, else **Setting a task** in it |
| `next` | **Setting a task** in the track named on the newest `TRACK` line of `coding.py list`, or the one the learner names |
| `submit`, or the learner says `submit` | **Submit** |
| `hint`, or the learner says `hint` or that they are stuck | **Hints** |
| `solution` | **The solution** |
| `list` | `python3 .claude/hooks/coding.py list`; show the output |
| `status`, or nothing | **Resuming** |

## A new track

1. **The opener, as its own reply.** Three to six sentences: what the track will practise, how a task works (a note and a starter file; run the file yourself; `submit` runs the hidden tests; `hint` when stuck), and what is about to happen (a question about the goal, then a syllabus to approve). End with `Say **ready** when you have read this.`
2. **The goal.** One `AskUserQuestion` call (header `Track`) with up to three questions: what the practice is for (an interview, a course, a language), how comfortable they are with the language now, and which libraries are in scope.
3. **The syllabus.** Ask the `researcher` what the stated goal actually tests (for quant interviews: which Python skills, which data structures, which kinds of question). Then propose the topics in order, each with a target level from 1 (first contact) to 5 (interview-ready). The learner approves it, or you change it, as a plan is approved in a lesson. Then record it:
   ```
   python3 .claude/hooks/coding.py track new <slug> --title "<title>" [--python <interpreter>]
   python3 .claude/hooks/coding.py track syllabus <slug> --file /tmp/learn-code-syllabus.json
   ```
   The file is `[{"topic": "<topic>", "target": 3}, …]`, in order. Use `--python` only when the learner names a virtual environment, for numpy or pandas.
4. **Placement**, only if they want it: two or three `quiz` questions on the first topics, then set the first task one level above what they showed.

## Setting a task

1. **Plan it:**
   ```
   python3 .claude/hooks/coding.py plan --track <slug> --slug <task-slug>
   ```
   Take the topic on the `SUGGEST` line, at that topic's level on the `LEVELS` line. `LAST` lines show what came before: do not repeat a problem, and after a `shown` or several submissions keep the next one at the same level.
2. **Theory first, when the task needs an idea that is not established.** An idea they have never met: a short reading in the teach skill's way (motivate, establish, one example), ending with the `ready` line, then one or two `quiz` questions on it. An idea they missed before (`REVISIT`, or a `shown` task on that topic): the quizzes only. Neither for an idea they have shown they have.
3. **Write the hidden tests first**, with the Write tool, to the `TESTS` path. Solve the problem yourself in `reference` before writing a case:
   ```python
   FUNCTION = "<the function the learner writes>"

   def reference(<args>): ...         # your solution

   def slow(<args>): ...              # only with a complexity target: a correct solution of the wrong complexity

   CASES = [
       {"name": "example", "args": [<positional args>], "expected": <value>},
       ...
   ]

   def large():                       # only with a complexity target: speed cases, seeded
       import random
       r = random.Random(1)
       yield {"name": "n = 10^5", "args": [<big input>]}

   def check(got, expected, args): ...   # only when == is the wrong test (any order, several valid answers)
   ```
   Every task has the cases a careful interviewer would try: the statement's examples, empty input, one element, duplicates, the boundaries of the constraints, and negatives or zero where the type allows. Six to twelve cases. Give each a short name: it is what the learner sees when it fails.
4. **Write the task note** to the `NOTE` path:
   ```markdown
   # <title>
   *<track title> · task NN · level L · <topics>*

   <the statement: what the function takes and returns, in two to five sentences>

   <f(example args) → result, one line per example, two or three examples>

   **Constraints:** <sizes, value ranges>. Aim for $O(<target>)$.
   **Your file:** `<STARTER path>`. Run it with `python3 <file name>`, then type **submit**.

   ## Submissions
   ```
5. **Write the starter file** to the `STARTER` path: the signature with type hints and `...` as the body, then `if __name__ == "__main__":` printing each example with the expected value in a comment. Nothing of the solution.
6. **Check it:**
   ```
   python3 .claude/hooks/coding.py check "<NOTE path>" --topics <topic>[,<topic>] --level <L>
   ```
   A `REFUSED` line names what is wrong: fix your tests or reference, and check again, until it prints `OPEN`. Never weaken a case to make it pass; a case that disagrees with your reference means one of them is wrong, so find out which.
7. **Mirror into the task note** (a track only; in a lesson the lesson note stays mirrored):
   ```
   python3 .claude/hooks/md_log.py link "<NOTE path>" --session ${CLAUDE_SESSION_ID} --from-now
   ```
8. **Reply with one line**: `Task NN is ready: [[<note stem>]]. Write your solution in \`<STARTER path>\`, run it, then type **submit**.`

## Submit

1. If an exam paper is open too (`python3 .claude/hooks/exam.py list` shows one `open`), ask which the learner means with one `AskUserQuestion` (header `Submit`), options **The code task** and **The exam paper**. The exam paper goes to the `exam` skill.
2. Run it:
   ```
   python3 .claude/hooks/coding.py submit ["<task note>"]
   ```
   Without a note it takes the newest unfinished task and names it on the `TASK` line. If the learner meant another one, run it again with that note.
3. **Failed** (`RESULT failed`): one or two sentences. Name the failing case and what differed, as the `FIRST FAIL` or `SPEED` lines say. Do not explain the bug or how to fix it. Offer a hint in one line: "Type **hint** if you want one."
   - A `SPEED fail` with a time far over the limit is the complexity: say which complexity the limit expects. One just over the limit may be noise: say so, and that resubmitting costs nothing.
4. **Passed** (`RESULT passed`): Read the file on the `REVIEW` line, then write the review under the heading `## Review`. Keep it short, as an interviewer's debrief:
   - **Complexity.** Time and space, stated, with a sentence on why.
   - **Luck.** An edge case the code handles only by accident, or one the tests did not cover and it gets wrong. Say "none" if there is none.
   - **Idiom.** At most two concrete rewrites in more idiomatic code, each a short before/after code block, each with its reason.
   - **Follow-up.** The question an interviewer would ask next ("now in O(1) extra space", "now the input is a stream"). Offer it as the next task.
   Then the `NEXT` line's topic is the next task's, unless the learner takes the follow-up.

## Hints

Run `python3 .claude/hooks/coding.py hint ["<task note>"]` before each hint. Give **one rung per reply**, starting where they are; never climb unprompted. Then one line asking them to try it.

1. **Look.** What to look at: the failing case and what it has that the others do not, or the part of the statement their code does not yet honour.
2. **Approach.** The idea or data structure in a sentence or two. No code.
3. **Sketch.** The hard part only, as pseudocode or a three-line fragment with gaps, never a runnable solution.

When a hint has a right answer ("which structure gives O(1) membership?"), pose it as a `quiz` instead of stating it.

## The solution

Only when the learner asks for it outright. Confirm first with one `AskUserQuestion` (header `Solution`): **Show it** (the task counts as solved with help) or **One more hint**. Then:
```
python3 .claude/hooks/coding.py solution ["<task note>"]
```
Read the `REFERENCE` file and walk through it like a worked example: the idea, then the code in two or three parts with what each does, then the complexity. Point to the line of their attempt where the approach parted from it. They may still submit their own version; it then counts as `helped`.

## In a lesson

For a programming topic, the teach skill's **Apply** step may be a code task instead of a `quiz`:

1. `python3 .claude/hooks/coding.py plan --note "<lesson note>" --slug <task-slug>`, then steps 3 to 6 of **Setting a task**, with `--topics` naming the node. `check` writes the task's box into the lesson note.
2. Reply with the one line of step 8.
3. On `submit`: as in **Submit**, but the review after a pass is two or three sentences. The outcome is the Apply's outcome:
   - `passed` or `helped`: the Apply is passed; continue as the teach skill says.
   - `shown`: the Apply is missed. Re-teach the move that went wrong, ending the reply with the `ready` line, then set a variant task.

## Resuming

`python3 .claude/hooks/coding.py status` lists the unfinished tasks. Take the newest (the last `TASK` line) unless the learner names another: link the mirror to it (a track) and say in one line where they are ("Task 03, two submissions, the last one 5/8"); they carry on. Older unfinished tasks stay listed; mention them once, in a clause. None unfinished: `coding.py list` shows the tracks; with one, or the one the learner names, run `coding.py status <track>`, then **Setting a task**.
