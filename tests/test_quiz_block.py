import unittest

import tests._vault  # noqa: F401  (puts hooks/ on the path)
import quiz_block


def record(**kw):
    r = {
        "status": "answered", "question": "What is 2+2?", "details": "", "multiSelect": False,
        "options": [{"index": 1, "label": "4"}, {"index": 2, "label": "5"}],
        "correctIndices": [1], "explanation": "Arithmetic.",
    }
    r.update(kw)
    return r


CORRECT = record(answers=[1], correct=True, dontKnow=False, note="")
INCORRECT = record(answers=[2], correct=False, dontKnow=False, note="")
DONT_KNOW = record(answers=[], correct=False, dontKnow=True, note="")
CANCELLED = record(status="cancelled")
UNAVAILABLE = record(status="unavailable", message="No form available.")
ASKED = record(status="asked", learnerQuestion="Is 4 even?")
CODE_QUESTION = "Run this:\n```\nprint(1)\n```\nWhat prints?"


def lines(r):
    return quiz_block.render(r).split("\n")


class Render(unittest.TestCase):
    def test_render_correct(self):
        out = lines(CORRECT)
        self.assertEqual(out[0], "> [!success|quiz]- ✓ What is 2+2?")
        self.assertEqual(sum("What is 2+2?" in ln for ln in out), 1)
        self.assertIn("> 1. 4", out)
        self.assertIn("> Selected: 1. 4", out)
        self.assertIn("> Arithmetic.", out)

    def test_render_incorrect(self):
        out = lines(INCORRECT)
        self.assertEqual(out[0], "> [!failure|quiz]- ✗ What is 2+2?")
        self.assertIn("> Selected: 2. 5", out)
        self.assertIn("> Correct answer: 1. 4", out)

    def test_render_dont_know(self):
        out = lines(DONT_KNOW)
        self.assertEqual(out[0], "> [!info|quiz]- ? What is 2+2?")
        self.assertIn("> Correct answer: 1. 4", out)
        self.assertFalse(any(ln.startswith("> Selected:") for ln in out))

    def test_render_cancelled(self):
        out = lines(CANCELLED)
        self.assertEqual(out[0], "> [!warning|quiz]- ⊘ Skipped: What is 2+2?")
        self.assertIn("> (skipped)", out)

    def test_render_unavailable(self):
        out = lines(UNAVAILABLE)
        self.assertEqual(out[0], "> [!warning|quiz]- ⊘ Unavailable: What is 2+2?")
        self.assertIn("> No form available.", out)

    def test_render_asked(self):
        out = lines(ASKED)
        self.assertEqual(out[0], "> [!note|quiz]- Asked first: What is 2+2?")
        self.assertIn("> Your question: Is 4 even?", out)
        self.assertNotIn("> Arithmetic.", out)

    def test_render_multiline_question(self):
        text = quiz_block.render(record(question=CODE_QUESTION, answers=[1], correct=True))
        self.assertEqual(text.split("\n")[0], "> [!success|quiz]- ✓ Run this:")
        self.assertIn("> Run this:\n> ```\n> print(1)\n> ```\n> What prints?", text)

    def test_render_details_and_multiselect(self):
        text = quiz_block.render(record(details="Adapted from Exercise 2.3.", multiSelect=True,
                                        answers=[1], correct=True))
        self.assertIn("> Adapted from Exercise 2.3.", text)
        self.assertIn("> (select all that apply)", text)

    def test_render_note(self):
        self.assertIn("> Note: I guessed.", quiz_block.render(record(answers=[1], correct=True, note="I guessed.")))


class CutTitle(unittest.TestCase):
    def test_cut_title_short(self):
        self.assertEqual(quiz_block.cut_title("Short question?"), "Short question?")

    def test_cut_title_long(self):
        line = " ".join(["word"] * 28)  # 139 characters
        out = quiz_block.cut_title(line)
        self.assertTrue(out.endswith("…"))
        self.assertLessEqual(len(out), 101)
        self.assertTrue(line.startswith(out[:-1]))
        self.assertEqual(line[len(out) - 1], " ")  # cut at a space

    def test_cut_title_in_math(self):
        line = "x" * 80 + r" then $\mathrm{KL}(q \,\|\, p)$ is minimized over every member of the family"
        out = quiz_block.cut_title(line)
        self.assertTrue(out.endswith("…"))
        self.assertEqual(out[:-1].count("$") % 2, 0)

    def test_cut_title_in_link(self):
        line = "a " * 45 + "see [[#^fig-1-4|Figure 1.4a]] for the tree and its leaves"
        out = quiz_block.cut_title(line)
        self.assertEqual(out[:-1].count("[["), out[:-1].count("]]"))
        self.assertTrue(out.endswith(" see…"))  # the link crosses the limit, so the cut falls before it

    def test_cut_title_no_space_left(self):
        line = "$" + "x" * 120 + "$ and more words after the math"
        out = quiz_block.cut_title(line)
        self.assertEqual(out, "$" + "x" * 120 + "$…")


class Parse(unittest.TestCase):
    def test_parse_round_trip(self):
        cases = [(CORRECT, "success", "✓"), (INCORRECT, "failure", "✗"), (DONT_KNOW, "info", "?"),
                 (CANCELLED, "warning", "skip"), (UNAVAILABLE, "warning", "unavailable"), (ASKED, "note", "asked")]
        for r, kind, outcome in cases:
            p = quiz_block.parse(lines(r))
            self.assertEqual((p["kind"], p["outcome"]), (kind, outcome), r["status"])
            self.assertEqual(p["title"], "What is 2+2?")
            self.assertTrue(p["text"].startswith("What is 2+2?"))

    def test_parse_cut_title_text_is_full_question(self):
        q = " ".join(["word"] * 40) + "?"
        p = quiz_block.parse(lines(record(question=q, answers=[1], correct=True)))
        self.assertTrue(p["title"].endswith("…"))
        self.assertTrue(p["text"].startswith(q))

    def test_parse_multiline_text(self):
        p = quiz_block.parse(lines(record(question=CODE_QUESTION, answers=[1], correct=True)))
        self.assertTrue(p["text"].startswith(CODE_QUESTION))

    def test_parse_unanswered(self):
        p = quiz_block.parse(["> [!question|quiz]- What is 2+2?", ">", "> 1. 4"])
        self.assertEqual(p["outcome"], "(unanswered)")
        self.assertEqual(p["title"], "What is 2+2?")

    def test_parse_rejects_other_callouts(self):
        self.assertIsNone(quiz_block.parse(["> [!success] ✓ Correct", ">", "> x"]))
        self.assertIsNone(quiz_block.parse(["> [!aside]+ Why?"]))
        self.assertTrue(quiz_block.is_quiz_header("> [!question|quiz]- Foo"))
        self.assertFalse(quiz_block.is_quiz_header("> [!question] Quiz"))


if __name__ == "__main__":
    unittest.main()
