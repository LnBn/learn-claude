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


if __name__ == "__main__":
    unittest.main()
