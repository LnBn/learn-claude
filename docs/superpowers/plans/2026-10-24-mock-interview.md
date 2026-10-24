# Mock Interview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/interview` runs a timed round of new problems on the course's finished units, with an interviewer who behaves like a real one, a clock the model sees on every message, and a scorecard that feeds recall checks.

**Architecture:** `hooks/interview.py` owns the round: paths, the problem file's validation, the clock, hints, answers (through `mcp/answer_check.py`), outcomes, the scorecard and the misses. A `UserPromptSubmit` hook (`interview.py hook`) prints the clock line into the model's context; the tmux status bar shows a live clock. `skills/interview/SKILL.md` holds the interviewer's rules.

**Tech Stack:** Python 3.10+, standard library only; tests with `unittest` (`python3 -m unittest discover -s tests -v`), through `tests/_vault.py`'s throwaway vault and subprocess `run`.

**Spec:** `docs/superpowers/specs/2026-10-24-mock-interview-design.md`

## Global Constraints

- Lengths: short 2 problems, standard 3, long 4; 12 minutes (720 s) per problem; round = problems × 720 s.
- Flags, first that applies: `ROUND TIME UP` (round spent), `TIME UP` (problem's 720 s spent), `TIME NEARLY UP` (≥ 75%), `NUDGE IF STUCK` (≥ 50% and no hint yet), `FOLLOW-UP` (main answer correct, problem open).
- Hook line, exactly: `INTERVIEW: problem 2 of 3 · 9:40 of 12:00 · hints 1 · round 21:15 of 36:00` then ` · <FLAG>` when a flag applies. Times are `m:ss`.
- Clock line: `P2/3 9:40/12:00`, or `P2/3 TIME UP`; empty when no round is running.
- Outcomes: `solved` (correct main answer, 0 hints), `hinted` (correct main answer, ≥ 1 hint), `unsolved`, `not reached`. Follow-up: `solved` (a correct follow-up answer recorded), `unsolved` (follow-up answers recorded, none correct), `not asked` (none recorded). The follow-up is offered only with ≥ 120 s left on the problem.
- Paths: note `courses/<slug>/interviews/<slug>-interview-<n>.md`; `courses/<slug>/.interviews/<slug>-interview-<n>.json` (problems), `.state.json`, `.marks.json`.
- State statuses: `set`, `ready`, `running`, `ended`, `finished`, `abandoned`. A round is open while `set`, `ready`, `running` or `ended`.
- tmux: session options only (`tmux set-option status-right …`, `tmux set-option status-interval 1`; unset with `set-option -u`), and only when `$TMUX` is set.
- Standard library only. Match the surrounding scripts (`exam.py`, `book.py`): `book.die` for refusals, `book.rel` for printed paths, short docstrings. README is a tutorial: how things work now, no change history.

**Additions to the spec found while planning:**

- `figures.course_of` recognises a note in an `interviews/` folder (as it does `exams/`), so the note mirror's `§2.4` links and figure handling work in an interview note.
- Time is tested by moving the recorded start times into the past in the `.state.json` file, so the script needs no test-only clock override.
- `tests/_vault.py`: `make_vault` also copies `mcp/` (the script imports `answer_check`), and `run` takes an optional `env` (to put a fake `tmux` on `PATH`).

## Review Focus

1. **The hook firing in a session that is not the interview's** (a lesson in another terminal while a round is open): prints nothing. Test in Task 2.
2. **The learner never sends a message after time runs out** (stares at the problem): the status bar says `TIME UP`; the next message carries the flag; `next` called long after the round's end closes the rest as `not reached`. Test in Task 2.
3. **A crash or a closed terminal mid-round** (state `running`, no session): `new` reports it as `OPEN`, `abandon` clears it and the tmux options. Test in Task 2.
4. **A follow-up answered before the main answer is correct, or a second correct main answer**: refused, and outcome counting is unaffected. Test in Task 2.
5. **A marks file that leaves out a problem that was given, or names one that was not reached**: `finish` refuses and names it. Test in Task 3.

---

### Task 1: `interview.py` — paths, `new`, `check`

**Files:**
- Create: `hooks/interview.py`
- Modify: `hooks/figures.py` (`course_of`), `tests/_vault.py` (`make_vault`, `run`)
- Test: `tests/test_interview.py`

**Interfaces:**
- Produces (in `hooks/interview.py`):
  - `LENGTHS = {"short": 2, "standard": 3, "long": 4}`, `PER_PROBLEM = 720`
  - `paths(c: book.Course, n: int) -> dict` with keys `note`, `problems`, `state`, `marks`
  - `rounds(c) -> list[tuple[int, dict]]` — `(n, state)` for every round of the course, oldest first
  - `open_round(c) -> tuple[int, dict] | None`
  - `load(c, n) -> dict`, `save(c, n, state)` — the `.state.json`
  - `key_ideas(note_path: str, unit_id: str) -> list[str]`
  - `main(argv)` with subcommands; this task adds `new`, `check`.
- `new` prints `NOTE:`, `PROBLEMS:`, `BUDGET: <k> problems × 12 minutes (round <k×12> minutes)`, `UNITS:` lines (`  <id> <title> — <heading link>` then `    key idea: <text>` per key idea), `PAST TECHNIQUES:` (one per line, or `  (none)`), and writes the state `{"status": "set", "length": …, "number": n, "set": <YYYY-MM-DD>}`.

- [ ] **Step 1: Update the test vault.** `make_vault` copies `REPO / "mcp"` to `vault/.claude/mcp` (same ignore); `run(vault, script, *args, stdin=None, env=None)` merges `env` over its environment.

- [ ] **Step 2: Write the failing tests** in `tests/test_interview.py`. Set-up: `make_vault`, `make_course(vault, "gb")`, `set_status(cdir, **{"1.1": ("done", "2026-10-05"), "2.3": ("shaky", "2026-10-06")})`, and chapter notes written with `### 1.1 What is learning` + a `> [!summary] Key idea\n> Learning is fitting.` callout, `### 2.3 Bayes' rule` + `> [!summary] Key idea\n> Posterior is prior times likelihood.`. Helper `iv(*args, **kw)` = `run(vault, "interview.py", *args, **kw)`; helper `problems(k)` returns a valid problem file with `k` problems (answers `"21"`, `"n+1"` with `{"n": "int 1..12"}`, units `["1.1"]`/`["2.3"]`, three hints, a follow-up).

```python
def test_new_prints_paths_budget_units(self):
    out = iv("new", "--length", "standard").stdout
    self.assertIn("NOTE: courses/gb/interviews/gb-interview-1.md", out)
    self.assertIn("PROBLEMS: courses/gb/.interviews/gb-interview-1.json", out)
    self.assertIn("BUDGET: 3 problems × 12 minutes (round 36 minutes)", out)
    self.assertIn("  1.1 What is learning — [[gb-ch01#1.1 What is learning|§1.1]]", out)
    self.assertIn("    key idea: Posterior is prior times likelihood.", out)
    self.assertNotIn("1.2 Supervised", out)  # not finished
    self.assertIn("PAST TECHNIQUES:\n  (none)", out)
def test_new_refuses_open_round_and_no_units(self):
    iv("new", "--length", "short")
    r = iv("new", "--length", "short")
    self.assertNotEqual(r.returncode, 0)
    self.assertIn("OPEN: courses/gb/interviews/gb-interview-1.md (set)", r.stdout + r.stderr)
    # a course with nothing finished
    set_status(self.cdir, **{"1.1": ("todo", ""), "2.3": ("todo", "")})
    iv("abandon")
    self.assertIn("no finished unit", iv("new", "--length", "short").stderr)
def test_numbering_and_past_techniques(self):
    # round 1 finished with technique "symmetry" -> round 2 lists it
    ...  # write a finished state + problem file for n=1, then:
    out = iv("new", "--length", "short").stdout
    self.assertIn("NOTE: courses/gb/interviews/gb-interview-2.md", out)
    self.assertIn("PAST TECHNIQUES:\n  symmetry", out)
def test_check_failures(self):
    iv("new", "--length", "short")
    for change, msg in [(lambda p: p["problems"].pop(), "short needs 2 problems, found 1"),
                        (lambda p: p["problems"][0].update(id="q1"), "problem 1: id must be p1"),
                        (lambda p: p["problems"][0].update(answer="2^("), "p1: answer: can't read: unclosed bracket"),
                        (lambda p: p["problems"][0].update(units=["1.2"]), "p1: unit 1.2 is not finished"),
                        (lambda p: p["problems"][0].update(hints=["a"]), "p1: needs exactly 3 hints"),
                        (lambda p: p["problems"][0].update(technique=""), "p1: technique is empty"),
                        (lambda p: p["problems"][0]["followup"].update(answer="m"), "p1 follow-up: answer: unknown name: m")]:
        p = problems(2); change(p); write_problems(p)
        r = iv("check")
        self.assertNotEqual(r.returncode, 0, msg)
        self.assertIn(msg, r.stdout + r.stderr)
def test_check_passes(self):
    iv("new", "--length", "short"); write_problems(problems(2))
    self.assertIn("🗒 interview ready", iv("check").stdout)
    self.assertEqual(self.state(1)["status"], "ready")
def test_course_of_interviews_folder(self):
    import figures  # the repo copy; course_of only reads the filesystem
    note = self.cdir / "interviews" / "gb-interview-1.md"
    note.parent.mkdir(); note.write_text("")
    self.assertEqual(figures.course_of(str(note)), str(self.cdir))
```

- [ ] **Step 3: Run to verify they fail**

Run: `python3 -m unittest tests.test_interview -v`
Expected: FAIL/ERROR — `interview.py` does not exist (non-zero return codes, empty stdout).

- [ ] **Step 4: Implement** `hooks/interview.py` (module docstring listing every command as in the spec, `argparse` like `exam.py`), the `new` and `check` commands, `abandon` far enough for the test (status `abandoned`; Task 2 adds the tmux part), and `figures.course_of` accepting a parent folder named `interviews`. The course comes from `book.find_course(None)`. `key_ideas` reads the chapter note (`c.note(unit["chapter"])`), takes every `### ` heading whose number is the unit id or starts with `<id>.`, and returns the text of each `> [!summary] Key idea` callout under it (callout lines joined with spaces). The heading link comes from `lesson.heading_links`. `check` reports every failure, one line each, then exits 1; on success prints `🗒 interview ready: <k> problems` and sets status `ready`. `answer_check` is imported after `sys.path.insert(0, os.path.join(CLAUDE_DIR, "mcp"))`.

- [ ] **Step 5: Run to verify they pass**

Run: `python3 -m unittest tests.test_interview -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add hooks/interview.py hooks/figures.py tests/_vault.py tests/test_interview.py
git commit -m "interview.py: new and check"
```

---

### Task 2: the running round — `start`, `hook`, `clock`, `hint`, `answer`, `next`, `stop`, `abandon`

**Files:**
- Modify: `hooks/interview.py`
- Test: `tests/test_interview.py`

**Interfaces:**
- Consumes: Task 1's `paths`, `open_round`, `load`, `save`; `answer_check.check`.
- Produces:
  - state per problem: `{"id", "start": float|None, "end": float|None, "hints": [{"t", "kind": "nudge"|"error"}], "answers": [{"t", "text", "verdict", "followup": bool}], "outcome": str|None, "followup": "solved"|"unsolved"|"not asked"}`; round fields `started`, `session`, `current` (index).
  - `flag(state, now: float) -> str` — `""` or one flag; `hook_line(state, now) -> str`; `clock_line(state, now) -> str`.
  - Command output: `start` → `PROBLEM 1: <statement>`; `answer` → `CORRECT`, `WRONG`, or `UNREADABLE: <error>`, and after a correct main answer `FOLLOW-UP: <statement>` or `NO TIME FOR THE FOLLOW-UP: close the problem with next`; `hint` → `HINT <k> recorded. Next prepared nudge: <text>` / `ERROR POINTED OUT, recorded as hint <k>.` / `HINT <k> recorded. No prepared nudges left: give the method, or close the problem.`; `next` → `CLOSED: Problem <i> — <outcome> (<m:ss>, <h> hint[s])`, `SOLUTION: <solution>`, then `PROBLEM <i+1>: <statement>` or `ROUND OVER: write the marks to <marks path>, then run finish`; `stop` → the CLOSED line for the current problem and `ROUND OVER: …`.

- [ ] **Step 1: Write the failing tests.** Helpers: `ready_round(k)` (new + problems + check), `shift(seconds)` (subtract `seconds` from every recorded time in the state: `started`, each problem's `start`, hint and answer `t`), `hook(session)` = `iv("hook", stdin=json.dumps({"session_id": session, "hook_event_name": "UserPromptSubmit", "prompt": "x"}))`, and `fake_tmux()` which writes an executable `tmux` script into a temp dir that appends its arguments to a log file, returning `{"PATH": f"{dir}:{os.environ['PATH']}", "TMUX": "x"}` and the log path.

```python
def test_start_and_hook_line(self):
    self.ready_round(3)
    self.assertIn("PROBLEM 1: ", iv("start", "--session", "s1").stdout)
    shift(580)
    self.assertEqual(hook("s1").stdout.strip(),
                     "INTERVIEW: problem 1 of 3 · 9:40 of 12:00 · hints 0 · round 9:40 of 36:00 · TIME NEARLY UP")
    self.assertEqual(hook("s2").stdout, "")           # another session
def test_flags_in_order(self):
    self.ready_round(2); iv("start", "--session", "s1")
    shift(370); self.assertTrue(hook("s1").stdout.strip().endswith("NUDGE IF STUCK"))
    iv("hint"); self.assertFalse(hook("s1").stdout.strip().endswith("NUDGE IF STUCK"))
    shift(360); self.assertTrue(hook("s1").stdout.strip().endswith("· TIME UP"))
    shift(800); self.assertTrue(hook("s1").stdout.strip().endswith("ROUND TIME UP"))
def test_clock_line(self):
    self.ready_round(3); iv("start", "--session", "s1"); shift(580)
    self.assertEqual(iv("clock").stdout.strip(), "P1/3 9:40/12:00")
    shift(200); self.assertEqual(iv("clock").stdout.strip(), "P1/3 TIME UP")
def test_hints(self):
    self.ready_round(2); iv("start", "--session", "s1")
    self.assertIn("HINT 1 recorded. Next prepared nudge: gentle", iv("hint").stdout)
    self.assertIn("ERROR POINTED OUT, recorded as hint 2.", iv("hint", "--error").stdout)
    self.assertIn("Next prepared nudge: stronger", iv("hint").stdout)  # errors do not use up nudges
    iv("hint"); self.assertIn("No prepared nudges left", iv("hint").stdout)
def test_answers_and_followup(self):
    self.ready_round(2); iv("start", "--session", "s1")
    self.assertEqual(iv("answer", "20").stdout.strip(), "WRONG")
    self.assertIn("UNREADABLE: can't read: unclosed bracket", iv("answer", "2(").stdout)
    r = iv("answer", "--followup", "5"); self.assertIn("follow-up is not open", r.stdout + r.stderr)
    out = iv("answer", "21").stdout
    self.assertTrue(out.startswith("CORRECT\nFOLLOW-UP: "))
    self.assertTrue(hook("s1").stdout.strip().endswith("FOLLOW-UP"))
    r = iv("answer", "21"); self.assertIn("already answered", r.stdout + r.stderr)
def test_no_time_for_followup(self):
    self.ready_round(2); iv("start", "--session", "s1"); shift(650)
    self.assertIn("NO TIME FOR THE FOLLOW-UP", iv("answer", "21").stdout)
def test_outcomes(self):
    self.ready_round(3); iv("start", "--session", "s1")
    iv("answer", "21")
    self.assertIn("CLOSED: Problem 1 — solved", iv("next").stdout)
    iv("hint"); iv("answer", "n+1")
    out = iv("next").stdout
    self.assertIn("CLOSED: Problem 2 — hinted", out); self.assertIn("PROBLEM 3: ", out)
    self.assertIn("CLOSED: Problem 3 — unsolved", iv("next", "--gave-up").stdout)
    st = self.state(1)
    self.assertEqual([p["outcome"] for p in st["problems"]], ["solved", "hinted", "unsolved"])
    self.assertEqual(st["problems"][0]["followup"], "not asked")
    self.assertEqual(st["status"], "ended")
def test_stop_and_round_time_up(self):
    self.ready_round(3); iv("start", "--session", "s1")
    out = iv("stop").stdout
    self.assertIn("ROUND OVER: write the marks to courses/gb/.interviews/gb-interview-1.marks.json", out)
    self.assertEqual([p["outcome"] for p in self.state(1)["problems"]], ["unsolved", "not reached", "not reached"])
    # a round whose time ran out: next closes the rest
    iv("abandon"); self.ready_round(3, n=2); iv("start", "--session", "s1"); shift(3000)
    iv("next")
    self.assertEqual([p["outcome"] for p in self.state(2)["problems"]], ["unsolved", "not reached", "not reached"])
def test_tmux_options(self):
    env, log = fake_tmux()
    self.ready_round(2); iv("start", "--session", "s1", env=env); iv("abandon", env=env)
    calls = Path(log).read_text()
    self.assertIn("set-option status-right #(python3 ", calls)
    self.assertIn("set-option status-interval 1", calls)
    self.assertIn("set-option -u status-right", calls)
    self.assertIn("set-option -u status-interval", calls)
    self.assertNotIn(" -g ", calls)
def test_crashed_round_is_open_and_abandonable(self):
    self.ready_round(2); iv("start", "--session", "s1")
    self.assertIn("OPEN: courses/gb/interviews/gb-interview-1.md (running)", iv("new", "--length", "short").stdout)
    iv("abandon"); self.assertEqual(self.state(1)["status"], "abandoned")
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest tests.test_interview -v`
Expected: the new tests FAIL (unknown subcommands).

- [ ] **Step 3: Implement** the commands. `start` refuses unless the round is `ready`; it creates the note with frontmatter (`interview: <slug>`, `number`, `date`, `length`, `status: running`) and nothing else, records `session`, `started` and problem 1's `start`, and issues the tmux commands when `$TMUX` is set (the clock command is `python3 "<abs path of interview.py>" clock`). `hook` reads stdin JSON, never fails (any error: print nothing, exit 0). `next` and `stop` compute outcomes from the record per the Global Constraints; when `ROUND TIME UP` applies, `next` closes the current problem and marks the rest `not reached`. After the last problem closes, status becomes `ended` and the tmux options stay until `finish`/`abandon`. `abandon` works from any open status and unsets the tmux options. Time is `time.time()` everywhere.

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m unittest tests.test_interview -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hooks/interview.py tests/test_interview.py
git commit -m "interview.py: the running round, the clock line and the status bar"
```

---

### Task 3: `finish`, `list`, and misses in the resume brief

**Files:**
- Modify: `hooks/interview.py`, `hooks/lesson.py` (`summary`)
- Test: `tests/test_interview.py`

**Interfaces:**
- Consumes: Task 2's state.
- Produces: `interview_misses(note: str) -> list[str]` — lines for the brief; `finish` and `list` commands.

- [ ] **Step 1: Write the failing tests.** Helper `ended_round()`: a 3-problem round with outcomes solved (6:12), hinted (2 hints), not reached, via the commands and `shift`.

```python
MARKS = {"problems": {"p1": "Clear.", "p2": "Needed a push."},
         "communication": {"structure": "good", "assumptions": "stated", "sanity checks": "none", "clarity": "fine"},
         "work_on": ["Check small cases."], "revisit": {"gb-ch02#2.3 Bayes' rule": "the update step"}}

def test_finish_writes_scorecard(self):
    self.ended_round(); write_marks(MARKS)
    out = iv("finish", "--marks", "courses/gb/.interviews/gb-interview-1.marks.json")
    self.assertEqual(out.returncode, 0, out.stderr)
    note = (self.cdir / "interviews" / "gb-interview-1.md").read_text()
    self.assertIn("### Scorecard", note)
    self.assertIn("| Problem 1 | solved | 6:12 | 0 | not asked | ", note)
    self.assertIn("| Problem 2 | hinted |", note)
    self.assertIn("| Problem 3 | not reached | — | — | — | ", note)
    self.assertIn("**How you explained:** structure — good; assumptions — stated; sanity checks — none; clarity — fine", note)
    self.assertIn("**Work on:** Check small cases.", note)
    self.assertIn("**Revisit:** [[gb-ch02#2.3 Bayes' rule|§2.3]] — the update step", note)
    self.assertIn("> [!example]- Problem 1 — solution", note)
    self.assertNotIn("Problem 3 — solution", note)
    self.assertIn("status: finished", note); self.assertIn("solved: 1/3", note)
    self.assertEqual(self.state(1)["status"], "finished")
def test_finish_refuses_incomplete_marks(self):
    self.ended_round()
    write_marks({**MARKS, "problems": {"p1": "x"}})
    self.assertIn("marks: no feedback for p2", iv("finish", "--marks", MARKS_PATH).stderr)
    write_marks({**MARKS, "problems": {**MARKS["problems"], "p3": "x"}})
    self.assertIn("marks: p3 was not reached", iv("finish", "--marks", MARKS_PATH).stderr)
def test_list(self):
    self.ended_round(); write_marks(MARKS); iv("finish", "--marks", MARKS_PATH)
    self.assertIn("gb-interview-1", iv("list").stdout); self.assertIn("finished  1/3 solved", iv("list").stdout)
def test_misses_in_resume_brief(self):
    self.ended_round(); write_marks(MARKS); iv("finish", "--marks", MARKS_PATH)
    out = run(self.vault, "lesson.py", "summary", "courses/gb/gb-ch02.md").stdout
    self.assertIn("INTERVIEW MISSES (gb-interview-1): re-probe these first", out)
    self.assertIn("  - Problem 2 hinted §2.3 — ", out)   # problem 2's unit is 2.3
    self.assertNotIn("Problem 1", out.split("INTERVIEW MISSES")[1])
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest tests.test_interview -v`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement** `finish` (refuses unless status `ended`; validates the marks against the given problems, one `marks: …` line per problem on stderr; appends the scorecard block of the spec to the note; rewrites the frontmatter's `status` and adds `solved: <k>/<n>`; sets status `finished`; unsets the tmux options; prints `🗒 interview finished: <k>/<n> solved`). The revisit links use `exam.section_label` for the `§2.3` label. `list` prints one line per round: `<name>  <set date>  <length>  <status>[  <k>/<n> solved]`. `interview_misses(note)`: the newest `finished` round of the note's course; problems whose outcome is `hinted` or `unsolved` and whose first unit's chapter note (`c.note(unit chapter)`) is among `lesson.review_sources(note)`; line format `  - Problem <i> <outcome> §<unit> — <technique>: <statement cut at 90 characters with …>`. In `lesson.summary`, after the exam misses, print these lines the same way (import inside a `try`, as for `exam`).

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add hooks/interview.py hooks/lesson.py tests/test_interview.py
git commit -m "interview.py: scorecard, list, and misses in the resume brief"
```

---

### Task 4: the skill, the hook registration and the docs

**Files:**
- Create: `skills/interview/SKILL.md`
- Modify: `settings.json`, `skills/teach/SKILL.md` (recall-check sentence; "Record progress" paragraph), `README.md`, `docs/architecture.md`

- [ ] **Step 1: Write `skills/interview/SKILL.md`.** Frontmatter like `skills/exam/SKILL.md`: `name: interview`; a description that triggers on `/interview`, "mock interview", "interview me"; `argument-hint: [short | standard | long] | stop | abandon | list`; `allowed-tools: Bash(python3 .claude/hooks/interview.py *), Bash(python3 .claude/hooks/md_log.py *), Bash(python3 .claude/hooks/lesson.py *), Write`. Sections, in the spec's words: Setting the round (unlink, ask the length unless given, `new`, the `OPEN:` choice as in the exam skill, writing the problem file with the rules on new problems and verifying every answer by running code, `check` until ready, then `start` and `link`, and the reply: greeting, `### Problem 1`, statement); The interviewer (every rule of the spec's list, the flags and what each asks of the interviewer, the `hint`/`answer`/`next` calls, `### Problem n` headings, no narration of tool calls, never the quiz tool); Ending (stop, writing the marks, `finish`, the short reply, asides after the round, unlinking when the talk leaves the interview).
- [ ] **Step 2: Register the hook and the permission** in `settings.json`: a second entry in the `UserPromptSubmit` hooks list, `{"type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/interview.py\" hook", "timeout": 5}`, and `"Bash(python3 .claude/hooks/interview.py *)"` in `permissions.allow`.
- [ ] **Step 3: Teach and course skills.** In the teach skill's recall check, the list of brief headings taken first gains `INTERVIEW MISSES`. In the teach skill's "Record progress" paragraph, after the sentence on `/exam`, one sentence that `/interview` runs a mock interview on everything finished so far (not started unasked).
- [ ] **Step 4: README and architecture.** README: an `## Interviews` section after `## Exams` (what a round is, lengths, the clock in the status bar, how the interviewer behaves and what counts as a hint, the scorecard, misses in recall checks, `/interview stop`, `/interview abandon`, `/interview list`), the contents line, and the commands table. Architecture: an `## Interviews` section (the script, the state, the hook, the status bar, outcomes computed by the script).
- [ ] **Step 5: Drive a round by hand.** In a detached tmux session with the vault's course, run `new`, write a two-problem file, `check`, `start --session t`, `hook` (stdin JSON), `hint`, `answer`, `next`, `stop`, write marks, `finish`; check the note, the status-bar options during the round (`tmux show-options status-right` in that session) and their removal after `finish`. Ledger anything that differs.
- [ ] **Step 6: Verify and commit.** Run `python3 -m unittest discover -s tests -v` (all PASS) and `python3 -c "import json; json.load(open('settings.json'))"`.

```bash
git add skills/interview/SKILL.md settings.json skills/teach/SKILL.md README.md docs/architecture.md
git commit -m "Interview skill, hook registration and docs"
```
