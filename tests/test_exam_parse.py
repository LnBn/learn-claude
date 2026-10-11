import unittest

from tests import _vault  # noqa: F401  (puts hooks/ on sys.path)
from tests._exam_fixtures import PAPER, SECTIONS, blank_q3, scheme, with_tags, without_q3_heading

import exam


class ParsePaper(unittest.TestCase):
    def test_ticks_by_letter_in_every_variant(self):
        q, probs = exam.parse_paper(PAPER)
        self.assertEqual(probs, [])
        self.assertEqual(q["q1"]["ticked"], {"a"})
        self.assertEqual(q["q2"]["ticked"], {"c"})
        self.assertEqual(q["q1"]["options"], ["a", "b", "c", "d"])
        self.assertEqual((q["q1"]["part"], q["q3"]["part"], q["q4"]["part"]), ("A", "B", "C"))
        self.assertEqual(q["q4"]["marks"], 8)

    def test_answer_extent(self):
        q, _ = exam.parse_paper(PAPER)
        self.assertIn("### Step 1", q["q4"]["answer"])
        self.assertIn("## Working", q["q4"]["answer"])
        self.assertIn("Divide by $p(D)$.", q["q4"]["answer"])

    def test_answer_on_answer_line(self):
        self.assertEqual(exam.parse_paper(PAPER)[0]["q3"]["answer"].strip(), "0.3")

    def test_blank_answer(self):
        self.assertEqual(exam.parse_paper(blank_q3())[0]["q3"]["answer"].strip(), "")

    def test_missing_heading_reported(self):
        self.assertNotIn("q3", exam.parse_paper(without_q3_heading())[0])
        self.assertTrue(any("Q3" in p for p in exam.check(without_q3_heading(), scheme(), SECTIONS)))

    def test_crlf(self):
        q, _ = exam.parse_paper(PAPER.replace("\n", "\r\n"))
        self.assertEqual(q["q1"]["ticked"], {"a"})
        self.assertEqual(q["q3"]["answer"].strip(), "0.3")


    def test_part_heading_inside_answer_stays_in_it(self):
        paper = PAPER.replace("## Working", "## Part A of the proof")
        q, _ = exam.parse_paper(paper)
        self.assertIn("## Part A of the proof", q["q4"]["answer"])
        self.assertIn("Divide by $p(D)$.", q["q4"]["answer"])
        self.assertEqual(q["q4"]["part"], "C")


class Percent(unittest.TestCase):
    def test_half_rounds_up(self):
        self.assertEqual([exam.pct(33, 40), exam.pct(11.5, 16), exam.pct(1, 3), exam.pct(0, 24)], [83, 72, 33, 0])

    def test_summary_uses_it(self):
        s = scheme()
        s["marks"] = 40
        for q, aw in zip(s["questions"], [2, 2, 4, 25]):
            q["awarded"] = aw
        s["questions"][3]["marks"] = 32
        self.assertIn("Result — 33/40 (83%)", exam.summary_block(s, {}))


class Frontmatter(unittest.TestCase):
    def test_read(self):
        fm, body = exam.read_frontmatter(PAPER)
        self.assertEqual((fm["status"], fm["marks"], fm["covers"]), ("open", "16", '"[[pml1-ch02]]"'))
        self.assertTrue(body.startswith("# Exam"))

    def test_roundtrip_keeps_unknown_keys(self):
        out = exam.set_frontmatter(with_tags(), status="submitted", score="31")
        fm, _ = exam.read_frontmatter(out)
        self.assertEqual((fm["status"], fm["score"], fm["tags"]), ("submitted", "31", "[x]"))
        self.assertEqual(out.split("---\n", 2)[2], with_tags().split("---\n", 2)[2])


class Check(unittest.TestCase):
    def problems(self, mutate, paper=PAPER):
        s = scheme()
        mutate(s)
        return exam.check(paper, s, SECTIONS)

    def test_valid(self):
        self.assertEqual(exam.check(PAPER, scheme(), SECTIONS), [])

    def test_question_missing_from_paper(self):
        def m(s):
            s["questions"].append({**s["questions"][2], "id": "q5"})
            s["marks"] += 4
        self.assertTrue(any("Q5" in p for p in self.problems(m)))

    def test_marks_differ_from_heading(self):
        def m(s):
            s["questions"][2]["marks"] = 3
            s["questions"][2]["points"][1]["marks"] = 1
        self.assertTrue(any("Q3" in p for p in self.problems(m)))

    def test_total_differs(self):
        self.assertTrue(self.problems(lambda s: s.update(marks=40)))

    def test_correct_letter_not_an_option(self):
        self.assertTrue(any("Q1" in p for p in self.problems(lambda s: s["questions"][0].update(correct=["e"]))))

    def test_unknown_section(self):
        p = self.problems(lambda s: s["questions"][3].update(section="pml1-ch02#9.9 Nope"))
        self.assertTrue(any("Q4" in x for x in p))

    def test_points_do_not_sum(self):
        p = self.problems(lambda s: s["questions"][2]["points"][0].update(marks=1))
        self.assertTrue(any("Q3" in x for x in p))

    def test_mc_missing_why_wrong(self):
        p = self.problems(lambda s: s["questions"][1]["why_wrong"].pop("a"))
        self.assertTrue(any("Q2" in x for x in p))

    def test_part_differs(self):
        p = self.problems(lambda s: s["questions"][2].update(part="C"))
        self.assertTrue(any("Q3" in x for x in p))


class Fmt(unittest.TestCase):
    def test_fmt(self):
        self.assertEqual([exam.fmt(3.0), exam.fmt(1.5), exam.fmt(2.25), exam.fmt(4)], ["3", "1.5", "2.25", "4"])


if __name__ == "__main__":
    unittest.main()
