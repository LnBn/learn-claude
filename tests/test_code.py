import json
import os
import sys
import time
import unittest
from pathlib import Path

from tests._vault import append, assistant, hook, make_vault, run, tool_result, transcript, user
from tests import _code_fixtures as fx


def lines_of(out):
    return dict(ln.split(" ", 1) for ln in out.splitlines() if " " in ln)


class Base(unittest.TestCase):
    def setUp(self):
        self.vault = make_vault(self)

    def code(self, *args):
        return run(self.vault, "coding.py", *args)

    def make_track(self, topics=(("lists", 3), ("dicts", 2))):
        r = self.code("track", "new", "quant", "--title", "Quant Python")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        syl = self.vault / "syllabus.json"
        syl.write_text(json.dumps([{"topic": t, "target": n} for t, n in topics]))
        r = self.code("track", "syllabus", "quant", "--file", "syllabus.json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def write_task(self, where, slug="running-max", tests=fx.TESTS, starter=fx.STARTER):
        r = self.code("plan", *where, "--slug", slug)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        p = lines_of(r.stdout)
        note, start, hidden = (self.vault / p[k] for k in ("NOTE", "STARTER", "TESTS"))
        hidden.parent.mkdir(parents=True, exist_ok=True)
        note.write_text(fx.NOTE.format(starter=p["STARTER"], name=start.name))
        start.write_text(starter)
        hidden.write_text(tests)
        return p

    def state(self, base):
        hidden = ".track" if base.startswith("practice/") else ".tests"
        return json.loads((self.vault / base / hidden / "state.json").read_text())


class Tracks(Base):
    def test_track_new_and_syllabus(self):
        self.make_track()
        self.assertTrue((self.vault / "practice/quant/quant.md").exists())
        s = self.state("practice/quant")
        self.assertEqual(s["kind"], "track")
        self.assertEqual(s["python"], "python3")
        self.assertEqual(s["syllabus"][0], {"topic": "lists", "target": 3, "level": 1})

    def test_plan_paths(self):
        self.make_track()
        p = lines_of(self.code("plan", "--track", "quant", "--slug", "running-max").stdout)
        self.assertEqual(p["NOTE"], "practice/quant/01-running-max.md")
        self.assertEqual(p["STARTER"], "practice/quant/01-running-max.py")
        self.assertEqual(p["TESTS"], "practice/quant/.track/01-running-max.py")
        self.assertEqual(p["TASK"], "01")
        self.assertEqual(p["SUGGEST"], "lists")
        (self.vault / "lessons").mkdir()
        (self.vault / "lessons/py.md").write_text("# Py\n")
        p = lines_of(self.code("plan", "--note", "lessons/py.md", "--slug", "x").stdout)
        self.assertEqual(p["NOTE"], "lessons/py — code/01-x.md")
        self.assertEqual(p["TESTS"], "lessons/py — code/.tests/01-x.py")


class Check(Base):
    def check(self, note, *extra):
        return self.code("check", note, "--topics", "lists", "--level", "1", *extra)

    def test_check_accepts(self):
        self.make_track()
        p = self.write_task(["--track", "quant"])
        r = self.check(p["NOTE"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OPEN practice/quant/01-running-max.md", r.stdout)
        self.assertIn("LIMIT 200 ms", r.stdout)
        rec = self.state("practice/quant")["tasks"][0]
        self.assertEqual((rec["n"], rec["slug"], rec["status"], rec["title"]), (1, "running-max", "open", "Running maximum"))
        self.assertEqual(rec["limit"], 0.2)  # the floor: the reference is far under 20 ms
        self.assertEqual(rec["topics"], ["lists"])
        self.assertIn("[[01-running-max]]", (self.vault / "practice/quant/quant.md").read_text())
        p2 = lines_of(self.code("plan", "--track", "quant", "--slug", "next").stdout)
        self.assertEqual(p2["TASK"], "02")

    def test_check_refuses_wrong_expected(self):
        self.make_track()
        p = self.write_task(["--track", "quant"], tests=fx.TESTS.replace('"expected": [3, 3, 4, 4, 5]', '"expected": [9]'))
        r = self.check(p["NOTE"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("REFUSED case example: reference returns [3, 3, 4, 4, 5]", r.stdout)
        self.assertEqual(self.state("practice/quant")["tasks"], [])

    def test_check_refuses_missing_function(self):
        self.make_track()
        p = self.write_task(["--track", "quant"], starter="def other(xs):\n    ...\n")
        r = self.check(p["NOTE"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("REFUSED the starter file does not define running_max()", r.stdout)

    def test_check_refuses_slow_within_limit(self):
        self.make_track()
        p = self.write_task(["--track", "quant"], tests=fx.TESTS.replace("range(10000)", "range(10)"))
        r = self.check(p["NOTE"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("REFUSED the speed tests do not separate slow() from reference()", r.stdout)

    def test_check_slow_equal_to_reference_refused_despite_slow_setup(self):
        # building the input takes longer than the kill time; only the call itself may count
        self.make_track()
        tests = fx.TESTS.replace("    import random\n", "    import random, time\n    time.sleep(1.8)\n").replace("def slow(xs):", "def slow(xs):\n    return reference(xs)\n\n\ndef _unused(xs):")
        p = self.write_task(["--track", "quant"], tests=tests)
        r = self.check(p["NOTE"])
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("do not separate", r.stdout)

    def test_check_again_keeps_the_history(self):
        self.make_track()
        p = self.write_task(["--track", "quant"])
        self.check(p["NOTE"])
        (self.vault / p["STARTER"]).write_text(fx.WRONG)
        self.code("submit")
        self.code("hint")
        r = self.check(p["NOTE"])
        self.assertEqual(r.returncode, 0, r.stdout)
        rec = self.state("practice/quant")["tasks"][0]
        self.assertEqual((len(rec["submissions"]), rec["hints"], rec["status"]), (1, 1, "open"))
        self.assertIn("RESULT failed", self.code("submit").stdout)
        self.assertTrue((self.vault / "practice/quant/.track/submissions/01-running-max-2.py").exists())

    def test_check_refuses_unknown_topic(self):
        self.make_track()
        p = self.write_task(["--track", "quant"])
        r = self.code("check", p["NOTE"], "--topics", "nonsense", "--level", "1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("REFUSED topic nonsense is not in the syllabus", r.stdout)

    def test_lesson_check_writes_open_box(self):
        (self.vault / "lessons").mkdir()
        (self.vault / "lessons/py.md").write_text("# Py\n\nSome text.\n")
        p = self.write_task(["--note", "lessons/py.md"])
        r = self.check(p["NOTE"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = (self.vault / "lessons/py.md").read_text()
        self.assertIn("\n\n> [!question|code]+ Task 01: Running maximum\n", text)
        self.assertEqual(self.state("lessons/py — code")["kind"], "lesson")


class Submit(Base):
    def setUp(self):
        super().setUp()
        self.make_track()
        self.p = self.write_task(["--track", "quant"])
        r = self.code("check", self.p["NOTE"], "--topics", "lists", "--level", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.starter = self.vault / self.p["STARTER"]
        self.note = self.vault / self.p["NOTE"]

    def submit(self, solution, *args):
        self.starter.write_text(solution)
        return self.code("submit", *args)

    def record(self):
        return self.state("practice/quant")["tasks"][0]

    def level(self, topic="lists"):
        return next(t["level"] for t in self.state("practice/quant")["syllabus"] if t["topic"] == topic)

    def test_submit_wrong_then_right(self):
        r = self.submit(fx.WRONG)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("RESULT failed", r.stdout)
        self.assertIn("CASES 2/3", r.stdout)
        self.assertIn("FIRST FAIL example", r.stdout)
        self.assertIn("  call running_max([3, 1, 4, 1, 5])", r.stdout)
        self.assertIn("  expected [3, 3, 4, 4, 5]", r.stdout)
        self.assertIn("  yours [3, 1, 4, 1, 5]", r.stdout)
        text = self.note.read_text()
        self.assertIn("## Submissions\n\n> [!failure|code]- ✗ Submission 1 — 2/3 passed", text)
        snap = self.vault / "practice/quant/.track/submissions/01-running-max-1.py"
        self.assertEqual(snap.read_text(), fx.WRONG)
        r = self.submit(fx.GOOD)
        self.assertIn("RESULT passed", r.stdout)
        self.assertIn("SPEED ok", r.stdout)
        self.assertIn("REVIEW practice/quant/.track/submissions/01-running-max-2.py", r.stdout)
        self.assertIn("> [!success|code]- ✓ Submission 2 — 3/3 passed · speed ✓ (", self.note.read_text())
        self.assertEqual(self.record()["status"], "passed")
        self.assertIn("| passed | 2 | 0 |", (self.vault / "practice/quant/quant.md").read_text())

    def test_speed_fail(self):
        r = self.submit(fx.QUADRATIC)
        self.assertIn("RESULT failed", r.stdout)
        self.assertIn("CASES 3/3", r.stdout)
        self.assertIn("SPEED fail n = 10000", r.stdout)
        self.assertIn("✗ Submission 1 — 3/3 passed · speed ✗", self.note.read_text())

    def test_slow_setup_does_not_fail_speed(self):
        tests = self.vault / self.p["TESTS"]
        tests.write_text(fx.TESTS.replace("    import random\n", "    import random, time\n    time.sleep(1.8)\n"))
        r = self.submit(fx.GOOD)
        self.assertIn("RESULT passed", r.stdout)
        self.assertIn("SPEED ok", r.stdout)

    def test_timeout_reported(self):
        start = time.monotonic()
        r = self.submit(fx.LOOPS)
        self.assertLess(time.monotonic() - start, 30)
        self.assertIn("FIRST FAIL example", r.stdout)
        self.assertIn("  yours timeout (over 5 s)", r.stdout)

    def test_broken_solution(self):
        for solution, error in ((fx.SYNTAX_ERROR, "SyntaxError"), (fx.WRONG_NAME, "running_max")):
            r = self.submit(solution)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("RESULT failed", r.stdout)
            self.assertIn("CASES 0/3", r.stdout)
            self.assertIn(error, r.stdout)

    def test_traceback_names_the_learners_file(self):
        r = self.submit(fx.RAISES)
        self.assertIn('File "practice/quant/01-running-max.py", line 2, in running_max', r.stdout)
        self.assertNotIn("submissions", r.stdout.split("REVIEW")[0])
        self.assertIn('File "practice/quant/01-running-max.py", line 2', self.note.read_text())

    def test_level_up_on_first_try(self):
        self.submit(fx.GOOD)
        self.assertEqual(self.level(), 2)
        self.assertIn("LEVELS lists=2/3", self.code("status", "quant").stdout)

    def test_level_unchanged_after_retry(self):
        self.submit(fx.WRONG)
        r = self.submit(fx.GOOD)
        self.assertIn("RESULT passed", r.stdout)
        self.assertEqual(self.level(), 1)

    def test_solution_shown_then_helped(self):
        self.code("hint")
        r = self.code("solution")
        self.assertIn("REFERENCE practice/quant/.track/01-running-max.py", r.stdout)
        rec = self.record()
        self.assertEqual(rec["status"], "shown")
        self.assertEqual(self.level(), 1)  # not below 1
        self.assertEqual(self.state("practice/quant")["revisit"], ["lists"])
        self.submit(fx.GOOD)
        self.assertEqual(self.record()["status"], "helped")
        self.assertEqual(self.level(), 1)

    def test_solution_lowers_level(self):
        self.submit(fx.GOOD)  # lists: 2
        p = self.write_task(["--track", "quant"], slug="again")
        self.code("check", p["NOTE"], "--topics", "lists", "--level", "2")
        self.code("solution", p["NOTE"])
        self.assertEqual(self.level(), 1)

    def test_hint_counts(self):
        self.code("hint")
        r = self.code("hint")
        self.assertIn("HINTS 2", r.stdout)
        self.assertEqual(self.record()["hints"], 2)
        self.assertIn("| open | 0 | 2 |", (self.vault / "practice/quant/quant.md").read_text())

    def test_bare_submit_takes_the_newest_unfinished_task(self):
        p = self.write_task(["--track", "quant"], slug="other")
        self.code("check", p["NOTE"], "--topics", "lists", "--level", "1")
        (self.vault / p["STARTER"]).write_text(fx.GOOD)
        r = self.code("submit")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(r.stdout.splitlines()[0], "TASK practice/quant/02-other.md")
        self.assertIn("RESULT passed", r.stdout)
        self.assertEqual(self.code("hint").stdout.splitlines()[0], "TASK practice/quant/01-running-max.md")

    def test_open_tasks_and_list(self):
        sys.path.insert(0, str(self.vault / ".claude" / "hooks"))
        self.addCleanup(sys.path.remove, str(self.vault / ".claude" / "hooks"))
        import coding
        cwd = os.getcwd()
        os.chdir(self.vault)
        self.addCleanup(os.chdir, cwd)
        self.assertEqual(coding.open_tasks(), ["practice/quant/01-running-max.md"])
        out = self.code("list").stdout
        self.assertIn("practice/quant/01-running-max.md open · 0 submissions, 0 hints", out)
        self.code("hint")
        self.assertIn("· 0 submissions, 1 hint\n", self.code("list").stdout)


class LessonSubmit(Base):
    def setUp(self):
        super().setUp()
        (self.vault / "lessons").mkdir()
        self.lesson = self.vault / "lessons/py.md"
        self.lesson.write_text("# Py\n\nSome text.\n")
        self.p = self.write_task(["--note", "lessons/py.md"])
        self.code("check", self.p["NOTE"], "--topics", "lists", "--level", "1")
        self.lesson.write_text(self.lesson.read_text() + "\nProse written after the task.\n")
        self.starter = self.vault / self.p["STARTER"]

    def test_lesson_box_in_place(self):
        self.starter.write_text(fx.WRONG)
        self.code("submit")
        text = self.lesson.read_text()
        self.assertIn("> [!failure|code]- ✗ Task 01: Running maximum", text)
        self.assertLess(text.index("Task 01"), text.index("Prose written after the task."))
        self.starter.write_text(fx.GOOD)
        self.code("submit")
        text = self.lesson.read_text()
        self.assertIn("> [!success|code]- ✗→✓ Task 01: Running maximum", text)
        self.assertIn("> - Submission 1: ✗ 2/3 passed\n> - Submission 2: ✓ 3/3 passed", text)
        self.assertEqual(text.count("Task 01:"), 1)
        self.assertLess(text.index("Task 01"), text.index("Prose written after the task."))

    def test_lesson_box_deleted_is_appended(self):
        self.lesson.write_text("# Py\n\nEdited by hand.\n")
        self.starter.write_text(fx.GOOD)
        self.code("submit")
        self.assertTrue(self.lesson.read_text().startswith("# Py\n\nEdited by hand.\n\n> [!success|code]- ✓ Task 01"))


class Mirror(Base):
    """A typed submit or hint with a code task unfinished is a pacing word: the reply is lesson content."""

    def setUp(self):
        super().setUp()
        import md_log
        self.md_log = md_log
        cwd = os.getcwd()
        os.chdir(self.vault)
        self.addCleanup(os.chdir, cwd)

    def open_task(self):
        self.make_track()
        p = self.write_task(["--track", "quant"])
        self.code("check", p["NOTE"], "--topics", "lists", "--level", "1")

    def test_typed_submit_is_the_exam_only_with_a_paper_out(self):
        self.assertEqual(self.md_log.command_of("submit"), ("code", "submit"))
        self.assertFalse(self.md_log.is_admin_command(self.md_log.command_of("submit")))
        self.assertFalse(self.md_log.is_user_prose("submit"))
        exams = self.vault / "lessons" / ".exams"
        exams.mkdir(parents=True)
        scheme = {"paper": "lessons/exams/x-exam-1.md", "questions": [], "status": "open"}
        (exams / "x-exam-1.json").write_text(json.dumps(scheme))
        self.assertEqual(self.md_log.command_of("submit"), ("exam", "submit"))
        self.assertEqual(self.md_log.command_of("Submit."), ("exam", "submit"))
        self.assertTrue(self.md_log.is_admin_command(self.md_log.command_of("submit")))
        (exams / "x-exam-1.json").write_text(json.dumps({**scheme, "status": "graded"}))
        self.assertEqual(self.md_log.command_of("submit"), ("code", "submit"))

    def test_review_logged_after_a_pass(self):
        # the replay that reads the typed "submit" runs after coding.py has closed the task
        self.open_task()
        note = "practice/quant/01-running-max.md"
        (self.vault / "practice/quant/01-running-max.py").write_text(fx.GOOD)
        s = "sess"
        tp = transcript(self.vault, s)
        run(self.vault, "md_log.py", "link", note, "--session", s, "--from-now", "--no-header")
        hook(self.vault, {"hook_event_name": "UserPromptSubmit", "session_id": s, "transcript_path": str(tp),
                          "prompt": "submit"})
        append(tp, user("submit"), assistant("m1", tool="Bash"))
        self.assertIn("RESULT passed", self.code("submit").stdout)
        append(tp, tool_result("tu-m1"), assistant("m2", text="## Review\n\nComplexity: O(n) time, one pass."))
        hook(self.vault, {"hook_event_name": "Stop", "session_id": s, "transcript_path": str(tp)})
        self.assertIn("Complexity: O(n) time, one pass.", (self.vault / note).read_text())

    def test_typed_hint_not_logged(self):
        self.assertFalse(self.md_log.is_user_prose("hint"))
        self.assertFalse(self.md_log.is_admin_command(self.md_log.command_of("hint")))

    def test_code_list_muted(self):
        self.assertTrue(self.md_log.is_admin_command(("code", "list")))
        self.assertTrue(self.md_log.is_admin_command(("code", "status")))
        self.assertFalse(self.md_log.is_admin_command(("code", "submit")))


if __name__ == "__main__":
    unittest.main()
