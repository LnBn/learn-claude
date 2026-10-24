import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from tests._vault import make_course, make_vault, run, set_status

CH01 = """### 1.1 What is learning

Text.

> [!summary] Key idea
> Learning is fitting.

### 1.2 Supervised learning

Text.
"""
CH02 = """### 2.3 Bayes' rule

Text.

> [!summary] Key idea
> Posterior is prior
> times likelihood.
"""
NOTE = "courses/gb/interviews/gb-interview-{n}.md"
MARKS_PATH = "courses/gb/.interviews/gb-interview-1.marks.json"


def problem(i, answer="21", variables=None, units=("1.1",)):
    return {"id": f"p{i}", "statement": f"Problem {i} statement: what is it?", "answer": answer,
            "variables": variables or {}, "answerLatex": answer, "solution": f"Solution {i}.",
            "technique": f"technique {i}", "units": list(units), "hints": ["gentle", "stronger", "nearly"],
            "followup": {"statement": f"Follow-up {i}?", "answer": "5", "variables": {}, "answerLatex": "5",
                         "solution": "Because."}}


def problems(k):
    """A valid problem file: p1 = 21 (unit 1.1), p2 = n+1 (unit 2.3), p3, p4 = 21 (unit 1.1)."""
    out = [problem(1)]
    if k >= 2:
        out.append(problem(2, answer="n+1", variables={"n": "int 1..12"}, units=("2.3",)))
    out += [problem(i) for i in range(3, k + 1)]
    return {"problems": out}


class InterviewBase(unittest.TestCase):
    def setUp(self):
        self.vault = make_vault(self)
        self.cdir = make_course(self.vault, "gb")
        set_status(self.cdir, **{"1.1": ("done", "2026-10-05"), "2.3": ("shaky", "2026-10-06")})
        (self.cdir / "gb-ch01.md").write_text(CH01, encoding="utf-8")
        (self.cdir / "gb-ch02.md").write_text(CH02, encoding="utf-8")

    def iv(self, *args, stdin=None, env=None):
        # TMUX is cleared unless a test passes its own: the tests must never change the real status bar
        return run(self.vault, "interview.py", *args, stdin=stdin, env={"TMUX": "", **(env or {})})

    def state_path(self, n=1):
        return self.cdir / ".interviews" / f"gb-interview-{n}.state.json"

    def state(self, n=1):
        return json.loads(self.state_path(n).read_text(encoding="utf-8"))

    def write_problems(self, data, n=1):
        p = self.cdir / ".interviews" / f"gb-interview-{n}.json"
        p.parent.mkdir(exist_ok=True)
        p.write_text(json.dumps(data), encoding="utf-8")

    def ready_round(self, k, n=1):
        length = {2: "short", 3: "standard", 4: "long"}[k]
        r = self.iv("new", "--length", length)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.write_problems(problems(k), n)
        r = self.iv("check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def shift(self, seconds, n=1):
        """Move every recorded time `seconds` into the past, as if that much time had gone by."""
        st = self.state(n)
        if st.get("started"):
            st["started"] -= seconds
        for pr in st.get("problems", []):
            for key in ("start", "end"):
                if pr.get(key):
                    pr[key] -= seconds
            for ev in pr.get("hints", []) + pr.get("answers", []):
                ev["t"] -= seconds
        self.state_path(n).write_text(json.dumps(st), encoding="utf-8")

    def hook(self, session):
        return self.iv("hook", stdin=json.dumps({"session_id": session, "hook_event_name": "UserPromptSubmit",
                                                 "prompt": "x"}))

    def fake_tmux(self):
        d = Path(tempfile.mkdtemp(prefix="fake-tmux-"))
        log = d / "calls.log"
        script = d / "tmux"
        script.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\n')
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        return {"PATH": f"{d}:{os.environ['PATH']}", "TMUX": "x"}, log


class SettingTheRound(InterviewBase):
    def test_new_prints_paths_budget_units(self):
        r = self.iv("new", "--length", "standard")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        self.assertIn("NOTE: courses/gb/interviews/gb-interview-1.md", out)
        self.assertIn("PROBLEMS: courses/gb/.interviews/gb-interview-1.json", out)
        self.assertIn("BUDGET: 3 problems × 12 minutes (round 36 minutes)", out)
        self.assertIn("  1.1 What is learning — [[gb-ch01#1.1 What is learning|§1.1]]", out)
        self.assertIn("    key idea: Learning is fitting.", out)
        self.assertIn("    key idea: Posterior is prior times likelihood.", out)
        self.assertNotIn("1.2 Supervised", out)  # not finished
        self.assertIn("PAST TECHNIQUES:\n  (none)", out)
        self.assertEqual(self.state()["status"], "set")

    def test_new_refuses_open_round_and_no_units(self):
        self.iv("new", "--length", "short")
        r = self.iv("new", "--length", "short")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("OPEN: courses/gb/interviews/gb-interview-1.md (set)", r.stdout + r.stderr)
        self.iv("abandon")
        set_status(self.cdir, **{"1.1": ("todo", ""), "2.3": ("todo", "")})
        r = self.iv("new", "--length", "short")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no finished unit", r.stderr)

    def test_numbering_and_past_techniques(self):
        d = self.cdir / ".interviews"
        d.mkdir()
        (d / "gb-interview-1.state.json").write_text(json.dumps({"status": "finished", "length": "short", "number": 1}))
        data = problems(2)
        data["problems"][0]["technique"] = "symmetry"
        data["problems"][1]["technique"] = "first-step conditioning"
        (d / "gb-interview-1.json").write_text(json.dumps(data))
        out = self.iv("new", "--length", "short").stdout
        self.assertIn("NOTE: courses/gb/interviews/gb-interview-2.md", out)
        self.assertIn("PAST TECHNIQUES:\n  symmetry\n  first-step conditioning", out)

    def test_check_failures(self):
        self.iv("new", "--length", "short")
        cases = [
            (lambda p: p["problems"].pop(), "short needs 2 problems, found 1"),
            (lambda p: p["problems"][0].update(id="q1"), "problem 1: id must be p1"),
            (lambda p: p["problems"][0].update(answer="2^("), "p1: answer: can't read: unclosed bracket"),
            (lambda p: p["problems"][0].update(units=["1.2"]), "p1: unit 1.2 is not finished"),
            (lambda p: p["problems"][0].update(hints=["a"]), "p1: needs exactly 3 hints"),
            (lambda p: p["problems"][0].update(technique=""), "p1: technique is empty"),
            (lambda p: p["problems"][0]["followup"].update(answer="m"), "p1 follow-up: answer: unknown name: m"),
        ]
        for change, msg in cases:
            p = problems(2)
            change(p)
            self.write_problems(p)
            r = self.iv("check")
            self.assertNotEqual(r.returncode, 0, msg)
            self.assertIn(msg, r.stdout + r.stderr)
        self.assertEqual(self.state()["status"], "set")

    def test_check_passes(self):
        self.iv("new", "--length", "short")
        self.write_problems(problems(2))
        self.assertIn("🗒 interview ready: 2 problems", self.iv("check").stdout)
        self.assertEqual(self.state()["status"], "ready")

    def test_course_of_interviews_folder(self):
        import figures  # the repo copy; course_of only reads the filesystem
        note = self.cdir / "interviews" / "gb-interview-1.md"
        note.parent.mkdir()
        note.write_text("")
        self.assertEqual(figures.course_of(str(note)), str(self.cdir))



class RunningRound(InterviewBase):
    def test_start_and_hook_line(self):
        self.ready_round(3)
        self.assertIn("PROBLEM 1: Problem 1 statement", self.iv("start", "--session", "s1").stdout)
        self.shift(580)
        self.assertEqual(self.hook("s1").stdout.strip(),
                         "INTERVIEW: problem 1 of 3 · 9:40 of 12:00 · hints 0 · round 9:40 of 36:00 · TIME NEARLY UP")
        self.assertEqual(self.hook("s2").stdout, "")
        self.assertEqual(self.state()["status"], "running")
        self.assertIn("status: running", (self.vault / NOTE.format(n=1)).read_text())

    def test_hook_is_silent_without_a_running_round(self):
        self.assertEqual(self.hook("s1").stdout, "")
        self.ready_round(2)
        self.assertEqual(self.hook("s1").stdout, "")
        self.assertEqual(self.iv("hook", stdin="not json").returncode, 0)

    def test_flags_in_order(self):
        self.ready_round(2)
        self.iv("start", "--session", "s1")
        self.assertEqual(self.hook("s1").stdout.strip(),
                         "INTERVIEW: problem 1 of 2 · 0:00 of 12:00 · hints 0 · round 0:00 of 24:00")
        self.shift(370)
        self.assertTrue(self.hook("s1").stdout.strip().endswith("· NUDGE IF STUCK"))
        self.iv("hint")
        self.assertTrue(self.hook("s1").stdout.strip().endswith("hints 1 · round 6:10 of 24:00"))
        self.shift(360)
        self.assertTrue(self.hook("s1").stdout.strip().endswith("· TIME UP"))
        self.shift(800)
        self.assertTrue(self.hook("s1").stdout.strip().endswith("· ROUND TIME UP"))

    def test_clock_line(self):
        self.assertEqual(self.iv("clock").stdout, "")
        self.ready_round(3)
        self.iv("start", "--session", "s1")
        self.shift(580)
        self.assertEqual(self.iv("clock").stdout.strip(), "P1/3 9:40/12:00")
        self.shift(200)
        self.assertEqual(self.iv("clock").stdout.strip(), "P1/3 TIME UP")

    def test_hints(self):
        self.ready_round(2)
        self.iv("start", "--session", "s1")
        self.assertIn("HINT 1 recorded. Next prepared nudge: gentle", self.iv("hint").stdout)
        self.assertIn("ERROR POINTED OUT, recorded as hint 2.", self.iv("hint", "--error").stdout)
        self.assertIn("HINT 3 recorded. Next prepared nudge: stronger", self.iv("hint").stdout)
        self.assertIn("Next prepared nudge: nearly", self.iv("hint").stdout)
        self.assertIn("No prepared nudges left: give the method, or close the problem.", self.iv("hint").stdout)
        self.assertEqual([h["kind"] for h in self.state()["problems"][0]["hints"]],
                         ["nudge", "error", "nudge", "nudge", "nudge"])

    def test_answers_and_followup(self):
        self.ready_round(2)
        self.iv("start", "--session", "s1")
        self.assertEqual(self.iv("answer", "20").stdout.strip(), "WRONG")
        self.assertIn("UNREADABLE: can't read: unclosed bracket", self.iv("answer", "2(").stdout)
        r = self.iv("answer", "--followup", "5")
        self.assertIn("follow-up is not open", r.stdout + r.stderr)
        out = self.iv("answer", "21").stdout
        self.assertTrue(out.startswith("CORRECT\nFOLLOW-UP: Follow-up 1?"), out)
        self.assertTrue(self.hook("s1").stdout.strip().endswith("· FOLLOW-UP"))
        r = self.iv("answer", "21")
        self.assertIn("already answered", r.stdout + r.stderr)
        self.assertEqual(self.iv("answer", "--followup", "4").stdout.strip(), "WRONG")
        self.assertEqual(self.iv("answer", "--followup", "5").stdout.strip(), "CORRECT")
        self.iv("next")
        p1 = self.state()["problems"][0]
        self.assertEqual((p1["outcome"], p1["followup"]), ("solved", "solved"))

    def test_no_time_for_followup(self):
        self.ready_round(2)
        self.iv("start", "--session", "s1")
        self.shift(650)
        self.assertIn("NO TIME FOR THE FOLLOW-UP: close the problem with next", self.iv("answer", "21").stdout)

    def test_outcomes(self):
        self.ready_round(3)
        self.iv("start", "--session", "s1")
        self.iv("answer", "21")
        out = self.iv("next").stdout
        self.assertIn("CLOSED: Problem 1 — solved (0:00, 0 hints)", out)
        self.assertIn("SOLUTION: Solution 1.", out)
        self.assertIn("PROBLEM 2: Problem 2 statement", out)
        self.iv("hint")
        self.iv("answer", "n+1")
        out = self.iv("next").stdout
        self.assertIn("CLOSED: Problem 2 — hinted (0:00, 1 hint)", out)
        self.assertIn("PROBLEM 3: ", out)
        out = self.iv("next", "--gave-up").stdout
        self.assertIn("CLOSED: Problem 3 — unsolved", out)
        self.assertIn("ROUND OVER: write the marks to courses/gb/.interviews/gb-interview-1.marks.json, then run finish", out)
        st = self.state()
        self.assertEqual([p["outcome"] for p in st["problems"]], ["solved", "hinted", "unsolved"])
        self.assertEqual(st["problems"][0]["followup"], "not asked")
        self.assertEqual(st["status"], "ended")
        self.assertEqual(self.hook("s1").stdout, "")

    def test_gave_up_after_a_correct_answer_still_counts_it(self):
        self.ready_round(2)
        self.iv("start", "--session", "s1")
        self.iv("answer", "21")
        self.iv("answer", "--followup", "9")
        self.iv("next", "--gave-up")
        p1 = self.state()["problems"][0]
        self.assertEqual((p1["outcome"], p1["followup"]), ("solved", "unsolved"))

    def test_stop_and_round_time_up(self):
        self.ready_round(3)
        self.iv("start", "--session", "s1")
        out = self.iv("stop").stdout
        self.assertIn("CLOSED: Problem 1 — unsolved", out)
        self.assertIn("ROUND OVER: write the marks to courses/gb/.interviews/gb-interview-1.marks.json", out)
        self.assertEqual([p["outcome"] for p in self.state(1)["problems"]], ["unsolved", "not reached", "not reached"])
        self.iv("abandon")
        self.ready_round(3, n=2)
        self.iv("start", "--session", "s1")
        self.shift(3000, n=2)
        out = self.iv("next").stdout
        self.assertIn("ROUND OVER", out)
        self.assertEqual([p["outcome"] for p in self.state(2)["problems"]], ["unsolved", "not reached", "not reached"])

    def test_tmux_options(self):
        env, log = self.fake_tmux()
        self.ready_round(2)
        self.iv("start", "--session", "s1", env=env)
        self.iv("abandon", env=env)
        calls = log.read_text()
        self.assertIn("set-option status-right #(python3 ", calls)
        self.assertIn("interview.py\" clock)", calls)
        self.assertIn("set-option status-interval 1", calls)
        self.assertIn("set-option -u status-right", calls)
        self.assertIn("set-option -u status-interval", calls)
        self.assertNotIn(" -g", calls)

    def test_no_tmux_calls_outside_tmux(self):
        env, log = self.fake_tmux()
        env["TMUX"] = ""
        self.ready_round(2)
        self.iv("start", "--session", "s1", env=env)
        self.iv("abandon", env=env)
        self.assertFalse(log.exists())

    def test_crashed_round_is_open_and_abandonable(self):
        self.ready_round(2)
        self.iv("start", "--session", "s1")
        self.assertIn("OPEN: courses/gb/interviews/gb-interview-1.md (running)", self.iv("new", "--length", "short").stdout)
        self.iv("abandon")
        self.assertEqual(self.state(1)["status"], "abandoned")
        self.assertEqual(self.hook("s1").stdout, "")

    def test_start_needs_a_ready_round(self):
        self.iv("new", "--length", "short")
        r = self.iv("start", "--session", "s1")
        self.assertNotEqual(r.returncode, 0)



MARKS = {"problems": {"p1": "Clear.", "p2": "Needed a push."},
         "communication": {"structure": "good", "assumptions": "stated", "sanity checks": "none", "clarity": "fine"},
         "work_on": ["Check small cases."], "revisit": {"gb-ch02#2.3 Bayes' rule": "the update step"}}


class Scorecard(InterviewBase):
    def ended_round(self):
        """Problem 1 solved in 6:12, problem 2 solved after a hint, problem 3 not reached."""
        self.ready_round(3)
        self.iv("start", "--session", "s1")
        self.shift(372)
        self.iv("answer", "21")
        self.iv("next")
        self.iv("hint")
        self.iv("answer", "n+1")
        self.iv("stop")

    def write_marks(self, marks):
        (self.vault / MARKS_PATH).write_text(json.dumps(marks), encoding="utf-8")

    def test_finish_writes_scorecard(self):
        env, log = self.fake_tmux()
        self.ended_round()
        self.write_marks(MARKS)
        r = self.iv("finish", "--marks", MARKS_PATH, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("🗒 interview finished: 1/3 solved", r.stdout)
        note = (self.vault / NOTE.format(n=1)).read_text()
        self.assertIn("### Scorecard", note)
        self.assertIn("| Problem 1 | solved | 6:12 | 0 | not asked | technique 1 |", note)
        self.assertIn("| Problem 2 | hinted | 0:00 | 1 | not asked | technique 2 |", note)
        self.assertIn("| Problem 3 | not reached | — | — | — | technique 3 |", note)
        self.assertIn("**How you explained:** structure — good; assumptions — stated; sanity checks — none; "
                      "clarity — fine", note)
        self.assertIn("**Work on:** Check small cases.", note)
        self.assertIn("**Revisit:** [[gb-ch02#2.3 Bayes' rule|§2.3]] — the update step", note)
        self.assertIn("> [!example]- Problem 1 — solution", note)
        self.assertIn("> Problem 1 statement: what is it?", note)
        self.assertIn("> **Follow-up:** Follow-up 1?", note)
        self.assertNotIn("Problem 3 — solution", note)
        self.assertIn("status: finished", note)
        self.assertIn("solved: 1/3", note)
        self.assertNotIn("status: running", note)
        self.assertEqual(self.state()["status"], "finished")
        self.assertIn("set-option -u status-right", log.read_text())

    def test_finish_refuses_incomplete_marks(self):
        self.ended_round()
        self.write_marks({**MARKS, "problems": {"p1": "x"}})
        r = self.iv("finish", "--marks", MARKS_PATH)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("marks: no feedback for p2", r.stderr)
        self.write_marks({**MARKS, "problems": {**MARKS["problems"], "p3": "x"}})
        self.assertIn("marks: p3 was not reached", self.iv("finish", "--marks", MARKS_PATH).stderr)
        self.assertEqual(self.state()["status"], "ended")

    def test_finish_needs_an_ended_round(self):
        self.ready_round(2)
        self.iv("start", "--session", "s1")
        self.write_marks(MARKS)
        self.assertNotEqual(self.iv("finish", "--marks", MARKS_PATH).returncode, 0)

    def test_list(self):
        self.ended_round()
        self.write_marks(MARKS)
        self.iv("finish", "--marks", MARKS_PATH)
        out = self.iv("list").stdout
        self.assertRegex(out, r"gb-interview-1  \d{4}-\d{2}-\d{2}  standard  finished  1/3 solved")

    def test_misses_in_resume_brief(self):
        self.ended_round()
        self.write_marks(MARKS)
        self.iv("finish", "--marks", MARKS_PATH)
        out = run(self.vault, "lesson.py", "summary", "courses/gb/gb-ch02.md").stdout
        self.assertIn("INTERVIEW MISSES (gb-interview-1): re-probe these first", out)
        self.assertIn("  - Problem 2 hinted §2.3 — technique 2: Problem 2 statement: what is it?", out)
        self.assertNotIn("Problem 1", out.split("INTERVIEW MISSES")[1])

    def test_no_misses_from_an_unfinished_round(self):
        self.ended_round()
        out = run(self.vault, "lesson.py", "summary", "courses/gb/gb-ch02.md").stdout
        self.assertNotIn("INTERVIEW MISSES", out)



class ReviewFixes(InterviewBase):
    def test_round_survives_a_course_switch(self):
        self.ready_round(2)
        self.iv("start", "--session", "s1")
        other = make_course(self.vault, "other")  # also makes "other" the course used last
        pointer = self.vault / ".claude" / "md-log-state" / "course.json"
        before = pointer.read_text()
        self.assertIn("INTERVIEW: problem 1 of 2", self.hook("s1").stdout)
        self.assertEqual(pointer.read_text(), before)  # the hook and the clock only read
        self.assertTrue(self.iv("clock").stdout.startswith("P1/2 "))
        self.assertEqual(pointer.read_text(), before)
        self.assertEqual(self.iv("answer", "21").stdout.split("\n")[0], "CORRECT")
        r = self.iv("new", "--length", "short")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("OPEN: courses/gb/interviews/gb-interview-1.md (running)", r.stdout)
        self.assertFalse((other / ".interviews").exists())

    def test_hook_and_clock_silent_after_finish_or_abandon(self):
        self.ready_round(2)
        self.iv("start", "--session", "s1")
        self.iv("abandon")
        self.assertEqual(self.hook("s1").stdout, "")
        self.assertEqual(self.iv("clock").stdout, "")

    def test_clock_counts_down_to_the_round_end(self):
        self.ready_round(2)
        self.iv("start", "--session", "s1")
        self.shift(1200)  # problem 1 overran to 20:00
        self.iv("next")
        self.assertEqual(self.iv("clock").stdout.strip(), "P2/2 0:00/4:00")
        self.shift(240)
        self.assertEqual(self.iv("clock").stdout.strip(), "P2/2 TIME UP")

    def test_followup_flag_wins_over_nudge_flags(self):
        self.ready_round(2)
        self.iv("start", "--session", "s1")
        self.iv("answer", "21")
        self.shift(370)
        self.assertTrue(self.hook("s1").stdout.strip().endswith("· FOLLOW-UP"))
        self.shift(200)
        self.assertTrue(self.hook("s1").stdout.strip().endswith("· FOLLOW-UP"))
        self.shift(200)
        self.assertTrue(self.hook("s1").stdout.strip().endswith("· TIME UP"))

    def test_hint_during_followup_has_no_prepared_nudge(self):
        self.ready_round(2)
        self.iv("start", "--session", "s1")
        self.iv("answer", "21")
        out = self.iv("hint").stdout
        self.assertIn("HINT 1 recorded, on the follow-up: there are no prepared nudges for it; give one in your own words.", out)
        self.assertNotIn("gentle", out)

    def test_answer_zero_passes_check(self):
        self.iv("new", "--length", "short")
        data = problems(2)
        data["problems"][0]["answer"] = 0
        self.write_problems(data)
        r = self.iv("check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_work_on_items_are_separate(self):
        self.ready_round(2)
        self.iv("start", "--session", "s1")
        self.iv("stop")
        marks = {"problems": {"p1": "x"}, "work_on": ["Set up first", "Check small cases"]}
        (self.vault / MARKS_PATH).write_text(json.dumps(marks))
        self.iv("finish", "--marks", MARKS_PATH)
        self.assertIn("**Work on:** Set up first; Check small cases", (self.vault / NOTE.format(n=1)).read_text())

    def test_abandon_marks_the_note(self):
        self.ready_round(2)
        self.iv("start", "--session", "s1")
        self.iv("abandon")
        note = (self.vault / NOTE.format(n=1)).read_text()
        self.assertIn("status: abandoned", note)
        self.assertNotIn("status: running", note)


if __name__ == "__main__":
    unittest.main()
