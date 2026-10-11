import json
import unittest
from pathlib import Path

from tests._vault import make_course, make_vault, run, set_status, write_note
from tests._exam_fixtures import PAPER, scheme

CH2 = ["2.1 Intro", "2.2 Rules", "2.3 Bayes' rule"]


class Base(unittest.TestCase):
    def setUp(self):
        self.vault = make_vault(self)
        self.course = make_course(self.vault)
        write_note(self.course / "pml1-ch01.md", ["1.1 What is learning", "1.2 Supervised learning"])
        write_note(self.course / "pml1-ch02.md", CH2)

    def exam(self, *args, stdin=None):
        return run(self.vault, "exam.py", *args, stdin=stdin)

    def finish_chapters(self):
        set_status(self.course, **{"1.1": ("done", "2026-10-01"), "1.2": ("done", "2026-10-01"),
                                    "2.1": ("done", "2026-10-05"), "2.2": ("done", "2026-10-05"),
                                    "2.3": ("done", "2026-10-05")})

    def state(self):
        return json.loads((self.course / ".course" / "state.json").read_text(encoding="utf-8"))

    def place_paper(self, paper=PAPER, sch=None, n=1):
        """Write a paper and its scheme where `new` says they go; return the paper's vault-relative path."""
        p = self.course / "exams" / f"pml1-ch02-exam-{n}.md"
        s = self.course / ".exams" / f"pml1-ch02-exam-{n}.json"
        p.parent.mkdir(exist_ok=True)
        s.parent.mkdir(exist_ok=True)
        p.write_text(paper, encoding="utf-8")
        s.write_text(json.dumps(sch or scheme()), encoding="utf-8")
        return str(p.relative_to(self.vault))


class New(Base):
    def test_defaults_to_latest_complete_chapter(self):
        self.finish_chapters()
        r = self.exam("new", "--length", "standard")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("PAPER: courses/pml1/exams/pml1-ch02-exam-1.md", r.stdout)
        self.assertIn("SCHEME: courses/pml1/.exams/pml1-ch02-exam-1.json", r.stdout)
        self.assertIn("ATTEMPT: 1", r.stdout)
        self.assertIn("Part A: 6 × 2 marks", r.stdout)
        self.assertIn("[[pml1-ch02#2.3 Bayes' rule|§2.3]]", r.stdout)
        self.assertIn("TITLE: Exam — Chapter 2: Probability: univariate models", r.stdout)
        self.assertNotIn("LEAVES OUT", r.stdout)

    def test_partial_chapter(self):
        set_status(self.course, **{"2.1": ("done", "2026-10-05")})
        r = self.exam("new", "2", "--length", "short")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("LEAVES OUT: 2.2, 2.3", r.stdout)
        self.assertIn("§2.1", r.stdout)
        self.assertNotIn("§2.2", r.stdout)

    def test_refusals(self):
        r = self.exam("new", "--length", "short")
        self.assertEqual(r.returncode, 2)
        self.assertIn("/exam <chapter>", r.stderr)
        r = self.exam("new", "notes/missing.md", "--length", "short")
        self.assertEqual(r.returncode, 2)
        r = self.exam("new", "2", "--length", "short")  # nothing of chapter 2 studied
        self.assertEqual(r.returncode, 2)

    def test_lesson_note_paths_with_space_and_dash(self):
        write_note(self.vault / "notes" / "Bayes rule.md", ["Priors", "Posteriors"])
        r = self.exam("new", "notes/Bayes rule.md", "--length", "short")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("PAPER: notes/exams/Bayes rule — Exam 1.md", r.stdout)
        self.assertIn("SCHEME: notes/.exams/Bayes rule — Exam 1.json", r.stdout)
        self.assertIn("[[Bayes rule#Priors]]", r.stdout)
        self.assertIn("TITLE: Exam — Bayes rule", r.stdout)

    def test_lesson_note_without_sections_refused(self):
        (self.vault / "notes").mkdir()
        (self.vault / "notes" / "Empty.md").write_text("Just text.\n", encoding="utf-8")
        self.assertEqual(self.exam("new", "notes/Empty.md", "--length", "short").returncode, 2)

    def test_attempt_counts_up(self):
        self.finish_chapters()
        s = scheme()
        s["status"] = "abandoned"
        self.place_paper(sch=s)
        r = self.exam("new", "2", "--length", "short")
        self.assertIn("ATTEMPT: 2", r.stdout)
        self.assertIn("pml1-ch02-exam-2.md", r.stdout)

    def test_open_paper_reported(self):
        self.finish_chapters()
        p = self.place_paper()
        self.assertEqual(self.exam("check", p).returncode, 0)
        r = self.exam("new", "2", "--length", "short")
        self.assertIn(f"OPEN: {p}", r.stdout)


class Check(Base):
    def test_registers_and_indexes(self):
        self.finish_chapters()
        p = self.place_paper()
        r = self.exam("check", p)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("🗒 exam ready", r.stdout)
        ex = self.state()["exams"]
        self.assertEqual((len(ex), ex[0]["status"], ex[0]["attempt"], ex[0]["chapter"]), (1, "open", 1, "2"))
        index = (self.course / "pml1.md").read_text(encoding="utf-8")
        self.assertIn("## Exams", index)
        self.assertIn("[[pml1-ch02-exam-1]]", index)
        sch = json.loads((self.course / ".exams" / "pml1-ch02-exam-1.json").read_text(encoding="utf-8"))
        self.assertEqual(sch["status"], "open")
        self.assertEqual(self.exam("check", p).returncode, 0)  # checking again does not register twice
        self.assertEqual(len(self.state()["exams"]), 1)

    def test_reports_problems(self):
        self.finish_chapters()
        s = scheme()
        s["marks"] = 40
        p = self.place_paper(sch=s)
        r = self.exam("check", p)
        self.assertEqual(r.returncode, 1)
        self.assertIn("marks", r.stdout)
        self.assertNotIn("exams", self.state())


TWO_TICKS = PAPER.replace("- [ ] b) $p(D \\mid h)$\n*  [X]  c)", "- [x] b) $p(D \\mid h)$\n*  [X]  c)")


class Submit(Base):
    def setUp(self):
        super().setUp()
        self.finish_chapters()

    def submitted(self, paper=TWO_TICKS, n=1):
        p = self.place_paper(paper, n=n)
        self.assertEqual(self.exam("check", p).returncode, 0)
        return p

    def scheme(self, n=1):
        return json.loads((self.course / ".exams" / f"pml1-ch02-exam-{n}.json").read_text(encoding="utf-8"))

    def test_grades_mc_and_prints_brief(self):
        p = self.submitted()
        r = self.exam("submit", p)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Q1 2/2", r.stdout)
        self.assertIn("Q2 0/2", r.stdout)
        self.assertIn("MULTIPLE CHOICE: 2/4", r.stdout)
        self.assertIn("=== Q3 (4 marks, short, §2.3) ===", r.stdout)
        self.assertIn("ANSWER:", r.stdout)
        self.assertIn("0.3", r.stdout)
        self.assertIn("MODEL ANSWER:", r.stdout)
        self.assertIn("- [2] applies Bayes' rule", r.stdout)
        self.assertTrue((self.course / ".exams" / "pml1-ch02-exam-1.submitted.md").exists())
        self.assertEqual((self.course / ".exams" / "pml1-ch02-exam-1.submitted.md").read_text(encoding="utf-8"),
                         TWO_TICKS)
        self.assertIn("status: submitted", (self.vault / p).read_text(encoding="utf-8"))
        s = self.scheme()
        self.assertEqual(s["status"], "submitted")
        q = {x["id"]: x for x in s["questions"]}
        self.assertEqual((q["q1"]["awarded"], q["q2"]["awarded"], q["q2"]["chosen"]), (2, 0, ["b", "c"]))
        self.assertEqual(q["q3"]["text"], "A test has sensitivity 0.9; the prior is 0.1 and $p(+) = 0.3$. "
                                          "What is $p(h \\mid +)$?")
        self.assertEqual(q["q1"]["text"], "Which of these is Bayes' rule?")
        self.assertEqual(self.state()["exams"][0]["status"], "submitted")

    def test_twice_refused(self):
        p = self.submitted()
        self.exam("submit", p)
        r = self.exam("submit", p)
        self.assertEqual(r.returncode, 1)
        self.assertIn("already submitted", r.stdout + r.stderr)

    def test_finds_the_only_open_paper(self):
        self.submitted()
        r = self.exam("submit")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("PAPER: courses/pml1/exams/pml1-ch02-exam-1.md", r.stdout)

    def test_none_or_several(self):
        r = self.exam("submit")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no open exam paper", r.stdout + r.stderr)
        a = self.submitted(n=1)
        s = scheme()
        s.update(attempt=2, paper="courses/pml1/exams/pml1-ch02-exam-2.md")
        b = self.place_paper(TWO_TICKS.replace("attempt: 1", "attempt: 2"), sch=s, n=2)
        self.assertEqual(self.exam("check", b).returncode, 0)
        r = self.exam("submit")
        self.assertEqual(r.returncode, 1)
        self.assertIn(a, r.stdout + r.stderr)
        self.assertIn(b, r.stdout + r.stderr)

    def test_broken_paper_changes_nothing(self):
        p = self.submitted()
        (self.vault / p).write_text(TWO_TICKS.replace("### Q3 (4 marks)\n", ""), encoding="utf-8")
        r = self.exam("submit", p)
        self.assertEqual(r.returncode, 1)
        self.assertIn("Q3", r.stdout + r.stderr)
        self.assertIn("status: open", (self.vault / p).read_text(encoding="utf-8"))
        self.assertFalse((self.course / ".exams" / "pml1-ch02-exam-1.submitted.md").exists())
        self.assertEqual(self.scheme()["status"], "open")

    def test_lists_images_and_blanks(self):
        paper = TWO_TICKS.replace("Divide by $p(D)$.", "![[work.jpg]]").replace("**Answer:** 0.3", "**Answer:**")
        p = self.submitted(paper)
        r = self.exam("submit", p)
        self.assertIn("IMAGES: work.jpg", r.stdout)
        self.assertIn("BLANK: Q3", r.stdout)
        self.assertIn("(blank)", r.stdout)


if __name__ == "__main__":
    unittest.main()
