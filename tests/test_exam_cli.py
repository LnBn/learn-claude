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


class Placed(Base):
    """Chapters 1 and 2 finished; helpers for a paper that has passed `check`."""
    def setUp(self):
        super().setUp()
        self.finish_chapters()

    def submitted(self, paper=TWO_TICKS, n=1):
        p = self.place_paper(paper, n=n)
        self.assertEqual(self.exam("check", p).returncode, 0)
        return p

    def scheme(self, n=1):
        return json.loads((self.course / ".exams" / f"pml1-ch02-exam-{n}.json").read_text(encoding="utf-8"))


class Submit(Placed):
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


GRADES = {"q3": {"awarded": 1.5, "feedback": "Bayes' rule is applied,\nbut the arithmetic slips."},
          "q4": {"awarded": 8, "feedback": "Complete."},
          "revisit": {"pml1-ch02#2.3 Bayes' rule": "the arithmetic of the posterior"}}


class Grade(Placed):
    def graded(self, grades=GRADES):
        p = self.submitted()
        self.assertEqual(self.exam("submit", p).returncode, 0)
        self.before = (self.vault / p).read_text(encoding="utf-8")
        r = self.exam("grade", p, stdin=json.dumps(grades))
        return p, r

    def test_inserts_feedback_without_touching_answers(self):
        p, r = self.graded()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = (self.vault / p).read_text(encoding="utf-8")
        snap = (self.course / ".exams" / "pml1-ch02-exam-1.submitted.md").read_text(encoding="utf-8")
        from tests._vault import REPO  # noqa: F401
        import exam
        for q in exam.parse_paper(snap)[0].values():
            self.assertIn(q["answer"], text)
        self.assertIn("> [!warning] Q3 — 1.5/4", text)
        self.assertIn("> but the arithmetic slips.", text)
        self.assertIn("> [!success] Q4 — 8/8", text)
        self.assertIn("> [!success] Q1 — 2/2", text)
        self.assertIn("> [!failure] Q2 — 0/2", text)
        self.assertIn("**You chose b):** is the likelihood", text)
        self.assertIn("> > [!example]- Model answer", text)
        self.assertIn("Tested: [[pml1-ch02#2.3 Bayes' rule|§2.3]]", text)
        self.assertIn("\n^q3\n", text)
        summary = text.index("> [!summary] Result — 11.5/16 (72%)")
        self.assertGreater(summary, text.index("# Exam"))
        self.assertLess(summary, text.index("## Part A"))
        self.assertIn("Part A 2/4 · Part B 1.5/4 · Part C 8/8", text)
        self.assertIn("[[pml1-ch02#2.3 Bayes' rule|§2.3]] (Q2, Q3): the arithmetic of the posterior", text)
        self.assertIn("status: graded", text)
        self.assertIn("🗒 exam graded: 11.5/16 (72%)", r.stdout)
        s = self.scheme()
        self.assertEqual((s["status"], s["score"], s["misses"]), ("graded", 11.5, ["q2", "q3"]))
        # the callout sits after the answer, before the next part
        self.assertLess(text.index("**Answer:** 0.3"), text.index("> [!warning] Q3"))
        self.assertLess(text.index("> [!warning] Q3"), text.index("## Part C"))

    def test_one_blank_line_after_each_callout(self):
        p, _ = self.graded()
        text = (self.vault / p).read_text(encoding="utf-8")
        self.assertIn("\n^q1\n\n### Q2", text)
        self.assertIn("\n^q2\n\n## Part B", text)
        self.assertTrue(text.endswith("\n^q4\n"))

    def test_half_marks_format(self):
        p, r = self.graded()
        text = (self.vault / p).read_text(encoding="utf-8")
        self.assertNotIn(".50", text)
        self.assertRegex(text, r"Result — \d+(\.5)?/16")

    def test_refusals_change_nothing(self):
        p = self.submitted()
        before_open = (self.vault / p).read_text(encoding="utf-8")
        self.assertEqual(self.exam("grade", p, stdin=json.dumps(GRADES)).returncode, 1)  # still open
        self.assertEqual((self.vault / p).read_text(encoding="utf-8"), before_open)
        self.exam("submit", p)
        before = (self.vault / p).read_text(encoding="utf-8")
        for bad in [{"q3": GRADES["q3"]},                                       # q4 missing
                    {**GRADES, "q3": {"awarded": 5, "feedback": "x"}},          # above the marks
                    {**GRADES, "q3": {"awarded": -1, "feedback": "x"}},
                    {**GRADES, "q1": {"awarded": 2, "feedback": "x"}}]:         # mc is the script's
            r = self.exam("grade", p, stdin=json.dumps(bad))
            self.assertEqual(r.returncode, 1, bad)
            self.assertEqual((self.vault / p).read_text(encoding="utf-8"), before)
        r = self.exam("grade", p, stdin="not json")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.scheme()["status"], "submitted")

    def test_shaky_only_from_done(self):
        set_status(self.course, **{"2.2": ("skipped", "2026-10-05")})
        s = scheme()
        s["questions"][3]["unit"] = "2.2"
        p = self.place_paper(TWO_TICKS, sch=s)
        # 2.2 is skipped, so the scheme cannot cite it; mark it done for check, then skipped again
        set_status(self.course, **{"2.2": ("done", "2026-10-05")})
        self.assertEqual(self.exam("check", p).returncode, 0)
        set_status(self.course, **{"2.2": ("skipped", "2026-10-05")})
        self.exam("submit", p)
        r = self.exam("grade", p, stdin=json.dumps({"q3": {"awarded": 0, "feedback": "No."},
                                                    "q4": {"awarded": 0, "feedback": "No."}}))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        st = self.state()
        self.assertEqual(st["status"]["2.3"]["s"], "shaky")
        self.assertEqual(st["status"]["2.2"]["s"], "skipped")
        self.assertIn("SHAKY: 2.3", r.stdout)
        index = (self.course / "pml1.md").read_text(encoding="utf-8")
        self.assertIn("| graded | 2/16 (12%) |", index)

    def test_regrade(self):
        p, _ = self.graded()
        r = self.exam("grade", p, "--regrade", "q3", stdin=json.dumps({"q3": {"awarded": 4, "feedback": "Right after all."}}))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = (self.vault / p).read_text(encoding="utf-8")
        self.assertIn("> [!success] Q3 — 4/4", text)
        self.assertIn("Regraded", text)
        self.assertIn("1.5 → 4", text)
        self.assertNotIn("[!warning] Q3", text)
        self.assertEqual(text.count("> [!summary] Result"), 1)
        self.assertIn("Result — 14/16 (88%)", text)
        self.assertEqual(text.count("^q3"), 1)
        self.assertEqual(self.scheme()["misses"], ["q2"])

    def test_regrade_needs_graded_paper(self):
        p = self.submitted()
        r = self.exam("grade", p, "--regrade", "q3", stdin=json.dumps({"q3": {"awarded": 4, "feedback": "x"}}))
        self.assertEqual(r.returncode, 1)

    def test_followup_aside_still_placed_after_grading(self):
        from tests._vault import append, assistant, hook, tool_result, transcript, user
        p, _ = self.graded()
        paper = self.vault / p
        s = "sess-2"
        tp = transcript(self.vault, s)
        append(tp, user("<command-name>/exam</command-name><command-args>submit</command-args>"),
               assistant("m1", tool="Bash"), tool_result("tu-m1"))
        run(self.vault, "md_log.py", "link", str(paper), "--session", s, "--from-now", "--muted", "--no-header")
        append(tp, assistant("m3", text="Score 11.5/16."))
        hook(self.vault, {"hook_event_name": "Stop", "session_id": s, "transcript_path": str(tp)})
        q = "why only 1.5 on Q3?"
        hook(self.vault, {"hook_event_name": "UserPromptSubmit", "session_id": s, "transcript_path": str(tp), "prompt": q})
        append(tp, user(q), assistant("m4", text="%% aside: q3 %%\nThe division was wrong."))
        hook(self.vault, {"hook_event_name": "Stop", "session_id": s, "transcript_path": str(tp)})
        text = paper.read_text(encoding="utf-8")
        at = text.index("> [!aside]+ why only 1.5 on Q3?")
        self.assertGreater(at, text.index("\n^q3\n"))
        self.assertLess(at, text.index("## Part C"))
        self.assertNotIn("Score 11.5/16.", text)


class Bookkeeping(Placed):
    def grade(self, paper, grades):
        self.assertEqual(self.exam("submit", paper).returncode, 0)
        r = self.exam("grade", paper, stdin=json.dumps(grades))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def second_attempt(self):
        s = scheme()
        s.update(attempt=2, paper="courses/pml1/exams/pml1-ch02-exam-2.md", set="2026-10-12")
        p = self.place_paper(PAPER.replace("attempt: 1", "attempt: 2").replace("set: 2026-10-11", "set: 2026-10-12"),
                             sch=s, n=2)
        self.assertEqual(self.exam("check", p).returncode, 0)
        return p

    def test_abandon_then_new_attempt(self):
        p = self.submitted()
        r = self.exam("abandon", p)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("🗒 exam abandoned", r.stdout)
        self.assertEqual(self.scheme()["status"], "abandoned")
        self.assertIn("status: abandoned", (self.vault / p).read_text(encoding="utf-8"))
        self.assertEqual(self.state()["exams"][0]["status"], "abandoned")
        self.assertIn("ATTEMPT: 2", self.exam("new", "2", "--length", "short").stdout)
        self.assertEqual(self.exam("abandon", p).returncode, 1)

    def test_list(self):
        self.assertIn("no exam papers yet", self.exam("list").stdout)
        a = self.submitted()
        self.grade(a, GRADES)
        b = self.second_attempt()
        out = self.exam("list").stdout.splitlines()
        self.assertEqual(len(out), 2)
        self.assertIn("graded", next(x for x in out if a in x))
        self.assertIn("11.5/16", next(x for x in out if a in x))
        self.assertIn("open", next(x for x in out if b in x))

    def test_summary_prints_exam_misses(self):
        a = self.submitted()
        self.grade(a, GRADES)
        out = run(self.vault, "lesson.py", "summary", "courses/pml1/pml1-ch02.md").stdout
        self.assertIn("EXAM MISSES (pml1-ch02-exam-1, 11.5/16)", out)
        self.assertIn("Q3 1.5/4 §2.3 Bayes' rule — A test has sensitivity 0.9", out)
        self.assertIn("Q2 0/2", out)
        b = self.second_attempt()
        self.grade(b, {"q3": {"awarded": 4, "feedback": "Right."}, "q4": {"awarded": 8, "feedback": "Right."}})
        out = run(self.vault, "lesson.py", "summary", "courses/pml1/pml1-ch02.md").stdout
        self.assertNotIn("EXAM MISSES", out)

    def test_chapter_complete_offers_exam(self):
        set_status(self.course, **{"1.2": ("todo", "")})
        r = run(self.vault, "book.py", "done", "1.2")
        self.assertIn("EXAM: /exam 1 sets an exam on this chapter.", r.stdout)
        set_status(self.course, **{"2.3": ("todo", "")})
        r = run(self.vault, "book.py", "done", "2.3")
        self.assertIn("COURSE COMPLETE", r.stdout)
        self.assertIn("EXAM: /exam 2 sets an exam on this chapter.", r.stdout)


if __name__ == "__main__":
    unittest.main()
