# Coding Practice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** LeetCode-style code tasks, set by the teacher in a practice track or inside a lesson, written by the learner in a real `.py` file, judged by hidden tests with speed limits, and reviewed after a pass.

**Architecture:** `hooks/coding_runner.py` runs one case in a child process (limits, timing, comparison) and prints one JSON line. `hooks/coding.py` does everything that must be exact: tracks, task paths, validating a task against its reference, the speed limit, running a submission, and writing results into the task note, the lesson note or the track index. `skills/code/SKILL.md` is the teacher's procedure. Small hooks into `md_log.py`, `lesson.py`, the exam and teach skills, the settings and the CSS connect it to the rest.

**Tech Stack:** Python 3.10+, standard library only (`resource`, `subprocess`, `importlib`); tests with `unittest` (`python3 -m unittest discover -s tests -v`).

**Spec:** `docs/superpowers/specs/2026-10-23-code-practice-design.md`

## Global Constraints

- Standard library only. numpy is used only if it can be imported, and only for comparing arrays.
- Paths: track `practice/<track>/`, with `<track>.md`, `NN-<slug>.md`, `NN-<slug>.py`, `.track/state.json`, `.track/NN-<slug>.py`, `.track/submissions/NN-<slug>-<k>.py`. A lesson's tasks go in `<dir>/<stem> — code/`, with `.tests/` in place of `.track/`. `NN` is two digits.
- Limits: `RLIMIT_AS` 2 GiB. A correctness case is killed after 5 s. A speed case is killed at `3 × limit + 1 s`. `limit = max(0.2, 10 × median of 3 reference runs)`. `slow` is killed at `2 × limit` and must exceed `limit`.
- Comparison: `==`. Floats (nested in lists, tuples and dict values) use `math.isclose(rel_tol=1e-9, abs_tol=1e-12)`; numpy arrays use `numpy.allclose`. A `check(got, expected, args)` in the tests replaces the comparison.
- Reported values: `got` and `expected` are `repr`, cut to 300 characters. `stdout` is the first 20 lines. The traceback keeps only frames from the solution file.
- Statuses: `open`, `passed`, `helped`, `shown`. (The spec's `abandoned` has no command that sets it; it is left out until one is needed.) Level changes: a pass on submission 1 with 0 hints gives +1 (up to 5); any other pass, no change; `shown` gives −1 (down to 1) and queues the topic to revisit.
- Box titles: submission `✓ Submission k — p/p passed · speed ✓ (<t> ms, limit <L> ms)` / `✗ Submission k — p/n passed`. Lesson box: open `[!question|code]+ Task NN: <title>`, passed `[!success|code]- ✓ Task NN: <title>`, passed after a failure `✗→✓ Task NN: <title>`, failing `[!failure|code]- ✗ Task NN: <title>`, helped `[!info|code]- ✓ Task NN: <title> (solution shown)`, shown `[!warning|code]- ⊘ Task NN: <title> (solution shown)`.
- Match the house style: `exam.py`-like briefs (one `KEY value` line per fact), short docstrings, the README as a tutorial.

**Rulings against the spec, made while planning:**

- **The script is `hooks/coding.py` and the runner `hooks/coding_runner.py`, not `code.py`.** A `hooks/code.py` would shadow the standard library's `code` module, which `pdb` imports, for every hook in `hooks/`. The command stays `/code`.
- **`plan` takes `--slug <slug>`**, because the paths depend on it.
- **A lesson's code box is found by its header** (`|code]` and `Task NN:`), not by its exact text. `coding.py` rewrites the box's body on every submission, so exact text would not survive; the task number is unique within a note.
- **A typed `submit` or `hint` with a code task open is a pacing word.** The prompt is not logged and the reply is (the review belongs in the note). Otherwise a typed `submit` stays the exam's, whose replies are muted, as now. `/code list` and `/code status` are muted housekeeping. The spec said only "`hint` is a pacing word; typed `submit` already is", but today a typed `submit` mutes the whole reply, which would drop the code review.

## Review Focus

1. **A solution that never returns, or allocates without limit** (`while True`, `[0] * 10**10`): the case is reported as `timeout` or `MemoryError` within the kill time, and the remaining cases still run. Tests in Task 1.
2. **A solution file with a syntax error, or one that does not define `FUNCTION`:** `submit` reports it as a failure of every case, with the error, and does not crash. Tests in Task 3.
3. **Output and return values that are huge or unprintable** (a 10⁶-element list; an object whose `__repr__` raises): `repr` is cut or replaced with `<unprintable>`, and the JSON line is still valid. Test in Task 1.
4. **A lesson note whose code box was edited or deleted by hand:** `submit` appends a fresh box instead of failing. Test in Task 3.
5. **A typed `submit` with both an exam paper and a code task open:** `md_log` does not mute the reply. The skill asks which one is meant. Tests in Task 4.

---

### Task 1: `coding_runner.py` — run one case

**Files:**
- Create: `hooks/coding_runner.py`
- Test: `tests/test_code_runner.py`, fixtures in `tests/_code_fixtures.py` (shared with Tasks 2 and 3)

**Interfaces:**
- Produces:
  - CLI: `python3 coding_runner.py <tests.py> --count`, which prints `{"function": F, "cases": n, "large": m}`.
  - CLI: `python3 coding_runner.py <tests.py> <case> (--solution <file.py> | --impl reference|slow) [--cpu <seconds>]`. `<case>` is `case:i` or `large:i`. It prints one JSON line: `{"name", "passed", "got", "expected", "seconds", "stdout", "error"}`, where `error` is `null` or `"<Type>: <message>\n<traceback>"`.
  - `compare(got, expected) -> bool`, importable.
- For `large:i`, `expected` is `reference(*args)`. The call of `--impl reference` is the reference's own run, which is how `check` times it.

- [ ] **Step 1: Write the failing tests** (`tests/test_code_runner.py`). The fixtures are module strings in `tests/_code_fixtures.py`, written into a temp dir by each test:
  - `TESTS`: `FUNCTION = "running_max"`, a correct `reference`, a quadratic `slow`, 3 `CASES` (example, empty, all equal), and a `large()` yielding one case of `n = 4000`, seeded.
  - Solutions: `GOOD` (linear), `WRONG` (returns `xs`), `RAISES` (`xs[0]` on empty, so `IndexError`), `LOOPS` (`while True`), `PRINTS` (prints 30 lines, then is correct), `MUTATES` (does `xs.append(0)` and returns the right answer of the original), `QUADRATIC` (correct, O(n²)), `HUGE_REPR` (returns an object whose `__repr__` raises).

  Test cases:
  - `test_count`: returns `{"function": "running_max", "cases": 3, "large": 1}`.
  - `test_pass`: `GOOD` on `case:0` gives `passed: true`, `error: null`, and `seconds ≥ 0`.
  - `test_wrong_answer`: `WRONG` on `case:0` gives `passed: false`, `got == "[3, 1, 4, 1, 5]"`, `expected == "[3, 3, 4, 4, 5]"`.
  - `test_exception_traceback_trimmed`: `RAISES` on `case:1` gives an `error` that starts `IndexError:` and names the solution file, but not `coding_runner.py`.
  - `test_cpu_limit`: `LOOPS` with `--cpu 1` exits within 5 s of wall time and prints no `passed: true`. The parent in Task 3 reports this as `timeout`; here, assert only that the process ends.
  - `test_stdout_captured`: `PRINTS` gives a `stdout` of exactly 20 lines and `passed: true`.
  - `test_float_tolerance`: `compare([0.1 + 0.2], [0.3])` is true; `compare({"a": (1.0, 2.0)}, {"a": (1.0, 2.0 + 1e-12)})` is true; `compare([1.0], [1.1])` is false.
  - `test_custom_check`: a tests module whose `check` accepts any permutation, with a solution that returns the expected list reversed, passes.
  - `test_mutation_does_not_leak`: `MUTATES` passes `case:0`.
  - `test_reference_and_slow_impls`: `--impl reference` on `large:0` passes. `--impl slow` on `large:0` passes, and its `seconds` is more than 10× the reference's.
  - `test_unprintable_value`: `HUGE_REPR` gives valid JSON, with `got == "<unprintable>"`.

- [ ] **Step 2: Run** `python3 -m unittest tests.test_code_runner -v`. Expected: FAIL, because the runner file does not exist.

- [ ] **Step 3: Implement `hooks/coding_runner.py`.**
  - Set `resource.RLIMIT_AS` to 2 GiB. With `--cpu N`, also set `RLIMIT_CPU` to `N`.
  - Load both files with `importlib.util.spec_from_file_location`, under the module names `hidden_tests` and `solution`.
  - Capture stdout with `contextlib.redirect_stdout` into a `StringIO`.
  - Time only the function call with `time.perf_counter()`. Call on `copy.deepcopy(args)`.
  - `expected` for `case:i` is `CASES[i]["expected"]`. For `large:i`, it is `reference(*copy.deepcopy(args))`, computed before the timed call.
  - The comparison is `tests.check(got, expected, args)` if `check` is defined, else `compare`.
  - Trim the traceback with `traceback.extract_tb`, keeping only frames whose filename is the solution's path. For `--impl`, keep the tests file's frames instead.
  - `repr` is wrapped in `try`, falling back to `"<unprintable>"`, then cut to 300 characters with `…`.
  - Print `json.dumps(result)` as the last line, to the real stdout.

- [ ] **Step 4: Run** `python3 -m unittest tests.test_code_runner -v`. Expected: all PASS.

- [ ] **Step 5: Commit:** `git add hooks/coding_runner.py tests/test_code_runner.py tests/_code_fixtures.py && git commit -m "coding_runner.py: run one code-task case in a limited child process"`.

### Task 2: `coding.py` — tracks, plan, check

**Files:**
- Create: `hooks/coding.py`
- Test: `tests/test_code.py` (class `Check`, class `Tracks`)

**Interfaces:**
- Consumes: the `coding_runner.py` CLI from Task 1.
- Produces (all importable, plus subcommands of the same name):
  - `track_dir(slug) -> str`, which is `practice/<slug>`.
  - `lesson_dir(note) -> str`, which is `<dir>/<stem> — code`.
  - `hidden_dir(base) -> str`: `.track` for a track, `.tests` for a lesson.
  - `load_state(base) -> dict`, `save_state(base, state)`.
  - `task_paths(base, n, slug) -> dict`, with keys `note`, `starter`, `tests`.
  - `run_case(tests, case, solution=None, impl=None, kill=5.0) -> dict`. This is the runner's JSON, plus `"timeout": bool`. It uses `subprocess.run(..., timeout=kill)` and passes `--cpu` as `ceil(kill)`.
  - CLI `track new <slug> --title T [--python P]`: writes `practice/<slug>/<slug>.md` and a `state.json` of `{"kind": "track", "slug", "title", "python": P or "python3", "syllabus": [], "revisit": [], "tasks": []}`.
  - CLI `track syllabus <slug> --file F`: sets `syllabus` to `[{"topic", "target", "level": 1}]`.
  - CLI `plan (--track S | --note N) --slug X`: prints `NOTE`, `STARTER`, `TESTS`, `TASK NN`. In a track it also prints `LEVELS <topic>=<level>/<target>,…`, `LAST <n> <slug> <status>` for up to 8 tasks, and `SUGGEST <topic>`: a revisit when `len(tasks) % 4 == 3` and `revisit` is non-empty; otherwise the first topic whose level is below its target. A lesson's state is created on first use: `{"kind": "lesson", "note", "python": "python3", "tasks": []}`.
  - CLI `check <task.md> --topics a,b --level L`. It either prints `OPEN <task.md>` and `LIMIT <ms> ms` when there are speed cases, or refuses with `REFUSED <reason>` lines and exit status 1. On success, it appends the task record `{"n", "slug", "title", "topics", "level", "status": "open", "submissions": [], "hints": 0, "limit", "created", "passed_at": null}`. The title is the note's `# ` line. In a lesson it also appends the open box to the lesson note. In a track it rewrites the index.
  - `write_index(base, state)`: the track index is the title, a `## Topics` table (Topic | Level | Target), and a `## Tasks` table (# | Task | Topics | Level | Status | Submissions | Hints), with the task linked as `[[NN-slug]]`.

- [ ] **Step 1: Write the failing tests.** Each test uses a vault from `tests._vault.make_vault` and runs the script with `tests._vault.run(vault, "coding.py", …)`. The fixtures come from `tests/_code_fixtures.py` (Task 1).
  - `test_track_new_and_syllabus`: the index and state exist. After `track syllabus` with two topics, `state["syllabus"][0] == {"topic": "lists", "target": 3, "level": 1}`.
  - `test_plan_paths`: `plan --track quant --slug running-max` prints `NOTE practice/quant/01-running-max.md`, `TESTS practice/quant/.track/01-running-max.py` and `TASK 01`. `plan --note lessons/py.md --slug x` prints `NOTE lessons/py — code/01-x.md`.
  - `test_check_accepts`: with the three files written from the fixtures, `check` exits 0 and prints `OPEN` and `LIMIT`. The record has `status: "open"`. The index lists `[[01-running-max]]`.
  - `test_check_refuses_wrong_expected`: a case with `expected: [9]` gives `REFUSED case example: reference returns …`.
  - `test_check_refuses_missing_function`: a starter without `def running_max` is refused.
  - `test_check_refuses_slow_within_limit`: with a `large()` of `n = 10` and a `slow` that is quadratic, the task is refused with `the speed tests do not separate slow() from reference()`.
  - `test_check_refuses_unknown_topic`: `--topics nonsense` in a track is refused.
  - `test_limit_floor`: for the fixture, `record["limit"] == 0.2` (the reference is far under 20 ms).
  - `test_lesson_check_writes_open_box`: after `check` on a lesson task, the lesson note ends with `> [!question|code]+ Task 01: Running maximum`.

- [ ] **Step 2: Run** `python3 -m unittest tests.test_code -v`. Expected: FAIL, because `coding.py` does not exist.

- [ ] **Step 3: Implement** the interfaces above with `argparse` subcommands, as `exam.py` does.
  - The working directory is the vault. Paths are printed relative to it.
  - The task directory comes from the task note's path. If its parent contains `.track/`, it is a track; if it contains `.tests/`, a lesson.
  - **Validation in `check`:**
    1. `--count` gives the case counts and `FUNCTION`; a starter that does not define `FUNCTION` is refused (a text search for `def <FUNCTION>(`).
    2. Every `case:i` with `--impl reference` must pass.
    3. Every `large:i` with `--impl reference` is run 3 times; the median of its `seconds` is the reference time.
    4. `limit = max(0.2, 10 × the largest median)`.
    5. If `slow` exists, every large case is run with `--impl slow` and `kill = 2 × limit`; at least one must time out or exceed `limit`.

- [ ] **Step 4: Run** `python3 -m unittest tests.test_code -v`. Expected: all PASS.

- [ ] **Step 5: Commit:** `git add hooks/coding.py tests/test_code.py && git commit -m "coding.py: tracks, task paths, and check against the reference"`.

### Task 3: `coding.py` — submit, hint, solution, status, list

**Files:**
- Modify: `hooks/coding.py`
- Test: `tests/test_code.py` (class `Submit`, class `Help`)

**Interfaces:**
- Consumes: Task 2's `run_case`, `load_state`, `save_state` and `write_index`, and its task record.
- Produces:
  - `open_tasks(root=".") -> list[str]`: the task notes with status `open`, found by globbing `**/.track/state.json` and `**/.tests/state.json`.
  - CLI `submit [task.md]`, `hint [task.md]`, `solution [task.md]`, `status [track | task.md]` and `list`. With no argument they take the only open task. With several open tasks they print `CHOOSE <task.md>` lines and exit with status 2.
  - The `submit` brief:
    - `RESULT passed|failed`;
    - `CASES p/n`;
    - `SPEED ok <t> ms / <L> ms` or `SPEED fail <case> <t> ms / <L> ms`;
    - `FIRST FAIL <name>` with indented `input`, `expected`, `yours` or `error`, and `printed` lines;
    - `REVIEW <snapshot>` when passed;
    - in a track, `LEVELS …` and `NEXT <topic>`.

- [ ] **Step 1: Write the failing tests.** Set up a checked track task from the Task 2 fixtures, then copy a solution fixture over the starter before each `submit`:
  - `test_submit_wrong_then_right`:
    - After `WRONG`: exit 0, `RESULT failed`, `CASES 1/3` (the all-equal case passes), and `FIRST FAIL example`. The task note has `> [!failure|code]- ✗ Submission 1 — 1/3 passed` under `## Submissions`. `.track/submissions/01-running-max-1.py` equals `WRONG`.
    - After `GOOD`: `RESULT passed`, `SPEED ok`, and `REVIEW …-2.py`. The note has `✓ Submission 2 — 3/3 passed · speed ✓`. The status is `passed`.
  - `test_speed_fail`: `QUADRATIC` gives `RESULT failed`, `CASES 3/3` and `SPEED fail n = 4000`.
  - `test_timeout_reported`: `LOOPS` reports `yours: timeout` for the first case within 20 s of wall time. Assert the time with `time.monotonic`.
  - `test_broken_solution`: a starter with a syntax error, and one that defines `other_name`, each give `RESULT failed`, with the error in `FIRST FAIL`. Neither crashes.
  - `test_levels`:
    - A first-try pass raises each topic by 1.
    - A pass on submission 2 changes nothing.
    - `solution` on an open task sets `shown`, lowers the level by 1 (not below 1) and adds the topic to `revisit`.
    - A pass after `solution` sets `helped`.
  - `test_hint_counts`: `hint` twice gives `HINTS 2` and `hints == 2` in the record. The index row shows 2.
  - `test_lesson_box_in_place`:
    - A lesson task with prose written after its open box.
    - After `WRONG`, the box reads `> [!failure|code]- ✗ Task 01: Running maximum`, in the same place, before the prose.
    - After `GOOD`, it reads `> [!success|code]- ✗→✓ Task 01: Running maximum`, with two submission lines.
  - `test_lesson_box_deleted_is_appended`: delete the box from the lesson note, then submit. The box is appended at the end.
  - `test_choose_between_open_tasks`: with two open tasks, `submit` with no argument exits 2 and prints two `CHOOSE` lines.
  - `test_open_tasks_and_list`: `open_tasks()` lists the open task. `list` prints each track and lesson task with its status.

- [ ] **Step 2: Run** `python3 -m unittest tests.test_code -v`. Expected: the new tests FAIL.

- [ ] **Step 3: Implement.**
  - `submit` snapshots the starter first, then runs all cases (kill 5 s each).
  - If all cases pass, it runs the large cases with `kill = 3 × limit + 1`. A large case fails when it fails, times out, or takes longer than `limit`.
  - **Records:** the record's `submissions` gets `{"k", "passed", "cases": "p/n", "speed", "at"}`. The note's box is appended at the end of the `## Submissions` section; create the section if it is missing.
  - **Lesson box:** found with the regex `^> \[!\w+\|code\][-+] .*Task NN: `. Its span is the following run of `>` lines. The body is: the statement's first paragraph (the first non-italic paragraph after the title), `[[<stem> — code/NN-slug|Task note]] · file `<starter path>``, a blank line, then one `- Submission k: ✓|✗ p/n passed` line per submission. If the box is not found, append it.
  - **Status, levels, revisit and the index** follow the Global Constraints. A task that passed once does not change levels again.

- [ ] **Step 4: Run** `python3 -m unittest discover -s tests -v`. Expected: all PASS.

- [ ] **Step 5: Commit:** `git commit -am "coding.py: submit, hint, solution, status, list"`.

### Task 4: Connect to the mirror, the resume brief, settings and CSS

**Files:**
- Modify: `hooks/md_log.py` (`ADMIN_COMMANDS` at about :493, `TYPED_*` regexes at about :499-506, `command_of` at about :509-528), `hooks/lesson.py` (`summary`, quiz tally at about :253), `settings.json` (`permissions.allow`), `obsidian/learn-callouts.css`
- Test: `tests/test_code.py` (class `Mirror`), `tests/test_lesson_outcomes.py`

**Interfaces:**
- Consumes: `coding.open_tasks()` (Task 3).
- Produces:
  - `md_log.command_of`: typed `submit` gives `("code", "submit")` when `coding.open_tasks()` is non-empty, else `("exam", "submit")`. Typed `hint` gives `("code", "hint")`. `ADMIN_COMMANDS["code"] = {"list", "status"}`.
  - `lesson.code_outcomes(lines) -> list[tuple[str, str]]`: `(title, "✓" | "✗" | "open" | "shown")` from `|code` box headers.

- [ ] **Step 1: Write the failing tests:**
  - `test_typed_submit_goes_to_open_code_task`: in a vault with an open task (from Task 3's setup), `md_log.command_of("submit") == ("code", "submit")`, and `md_log.is_admin_command` of it is false. Without one, it is `("exam", "submit")` and admin. Run `md_log` from the vault's copy, or change into the vault directory around the call.
  - `test_typed_hint_not_logged`: `md_log.is_user_prose("hint")` is false. `md_log.is_admin_command(md_log.command_of("hint"))` is false.
  - `test_code_list_muted`: `is_admin_command(("code", "list"))` is true; `("code", "submit")` is false.
  - `test_code_outcomes` (in `test_lesson_outcomes.py`): lines with `> [!success|code]- ✗→✓ Task 01: A`, `> [!failure|code]- ✗ Task 02: B` and `> [!question|code]+ Task 03: C` give `[("A", "✓"), ("B", "✗"), ("C", "open")]`.

- [ ] **Step 2: Run** `python3 -m unittest tests.test_code tests.test_lesson_outcomes -v`. Expected: the new tests FAIL.

- [ ] **Step 3: Implement.**
  - In `md_log.py`, `import coding` lazily, inside `command_of`, only when the text matches typed `submit`, so most prompts pay nothing. Add `TYPED_HINT_RE = re.compile(r"^\W*hint\W*$", re.I)`.
  - In `lesson.summary`, after the `quizzes:` part of the summary line, add ` · code tasks: n (✓ m)` when the note has `|code` boxes.
  - Add `"Bash(python3 .claude/hooks/coding.py *)"` to `settings.json`.
  - In the CSS, extend both quiz selectors to `.callout[data-callout-metadata~="quiz"], .callout[data-callout-metadata~="code"]`, and the print rule likewise.

- [ ] **Step 4: Run** `python3 -m unittest discover -s tests -v`. Expected: all PASS.

- [ ] **Step 5: Commit:** `git commit -am "Code tasks: typed submit/hint, resume tally, settings, CSS"`.

### Task 5: The code skill, and the exam and teach skills

**Files:**
- Create: `skills/code/SKILL.md`
- Modify: `skills/exam/SKILL.md` (the `submit` row of its command table and the start of *Grading*), `skills/teach/SKILL.md` (Phase 3, step 4 *Apply*, at about :174, and the missed-Apply bullet at about :178)

- [ ] **Step 1: Write `skills/code/SKILL.md`** with this frontmatter:
  - `name: code`
  - `description`: Practise programming: a track of coding problems, or a code task in a lesson. Each task is written in a starter `.py` file and judged by hidden tests on `submit`, with hints in steps and a review after a pass. Use with `/code [topic | next | submit | hint | solution | list | status]`, when the learner asks to practise coding or interview problems, or says `submit` or `hint` with a code task open.
  - `argument-hint: [topic | next | submit | hint | solution | list | status]`
  - `allowed-tools: Bash(python3 .claude/hooks/coding.py *), Bash(python3 .claude/hooks/md_log.py *), Bash(python3 .claude/hooks/exam.py list)`

  Body sections, from the spec's *The code skill*, with the exact commands from Tasks 2 and 3:
  - **Dispatch:** a table of argument → section.
  - **A new track:** opener, goal question, researcher, syllabus, `track new`, `track syllabus`, optional probe.
  - **Setting a task:**
    - `plan`, then the reading and quizzes when needed;
    - the tests file first, with the required edge cases: empty, single element, duplicates, boundaries, and negative numbers where the type allows;
    - then the task note and the starter, in the formats from the spec's *The task*;
    - `check` until it prints `OPEN`, then `md_log.py link "<task note>" --session ${CLAUDE_SESSION_ID} --from-now` in a track;
    - a one-line reply.
  - **Submit:** handle `CHOOSE` and an open exam paper. On failure, one line and an offer of a hint; on a pass, the review in four parts.
  - **Hints:** the three steps, and `hint` before each one.
  - **Solution:** confirm, `solution`, then the walk-through.
  - **In a lesson:** `plan --note`, no link change (the lesson note stays mirrored), and how a pass, `helped` or `shown` maps to the Apply outcome.
  - **Resuming.**

  Write it in the house style: second person, short sentences, no narration.

- [ ] **Step 2: Exam skill.** Typed `submit` with `coding.py status` showing an open task as well: ask with one `AskUserQuestion` (header `Submit`), with the options **The exam paper** and **The code task**.

- [ ] **Step 3: Teach skill.** In step 4 (*Apply*), add: for a programming topic, the Apply may be a code task, following the code skill's *In a lesson* section. Its outcome counts as the Apply's: passed or helped counts as passed; shown counts as missed, so re-teach, then set a variant task.

- [ ] **Step 4: Check the skill against the scripts.** Grep that every `coding.py` subcommand and flag named in the three skill files exists in `coding.py --help` and its subcommand help. Expected: no mismatches.

- [ ] **Step 5: Commit:** `git commit -am "Code skill; exam and teach skills hand over to it"`.

### Task 6: Docs, and an end-to-end run

**Files:**
- Modify: `README.md` (contents line, a new `## Coding practice` section after `## Exams`, rows in the Commands table, the Repository layout), `docs/architecture.md` (components table, a new `## Coding practice` section, state files, a fragile-parts entry for timing noise, the Testing paragraph)

- [ ] **Step 1: README.** Write it as a tutorial:
  - starting a track;
  - what a task note and a starter file look like;
  - running your file, `submit`, `hint` and `/code solution`;
  - what a submission box shows;
  - code tasks inside a lesson;
  - the files of a track;
  - the command rows: `/code <topic>`, `/code next`, `/code submit`, `/code hint`, `/code solution`, `/code list`, `/code status`.

- [ ] **Step 2: Architecture.**
  - the runner's limits and kill times;
  - the speed-limit rule;
  - the state schemas;
  - the typed-`submit` routing;
  - the lesson box found by its header;
  - timing noise as a fragile part.

- [ ] **Step 3: End-to-end run in a throwaway vault** (`tests._vault.make_vault` from a `python3 -c`, or a temp dir with `.claude/hooks` copied). Run:
  1. `track new`, then `track syllabus`, then `plan`;
  2. write the fixture task, then `check`;
  3. `submit` with `WRONG`, `hint`, then `submit` with `GOOD`.

  Read the task note and the index note it produces. Expected: the boxes and rows match the Global Constraints. Then delete the temp dir.

- [ ] **Step 4: Run** `python3 -m unittest discover -s tests -v`. Expected: all PASS.

- [ ] **Step 5: Commit:** `git commit -am "Docs: coding practice"`.

### Task 7: Merge and install (needs the learner)

- [ ] **Step 1:** Ask before merging to `master` and pushing.
- [ ] **Step 2:** `git -C "<vault>/.claude" pull`, then copy the CSS into `<vault>/.obsidian/snippets/`. The new skill and the settings entry load in the next Claude Code session.
- [ ] **Step 3:** The learner starts Claude Code in tmux and runs `/code quant python` for a first real track.
