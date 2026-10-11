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


if __name__ == "__main__":
    unittest.main()
