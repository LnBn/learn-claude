import unittest

import tests._vault  # noqa: F401  (puts hooks/ on the path)
import lesson
import quiz_block
from tests.test_quiz_block import ASKED, CANCELLED, CORRECT, DONT_KNOW, INCORRECT


class QuizOutcomes(unittest.TestCase):
    def test_outcomes_in_order(self):
        blocks = [quiz_block.render(r) for r in (CORRECT, ASKED, INCORRECT, DONT_KNOW, CANCELLED)]
        lines = ("Prose.\n\n" + "\n\nMore prose.\n\n".join(blocks) + "\n").split("\n")
        out = lesson.quiz_outcomes(lines)
        self.assertEqual([o for _, o in out], ["✓", "✗", "?", "skip"])
        self.assertEqual({q for q, _ in out}, {"What is 2+2?"})

    def test_unanswered(self):
        lines = quiz_block.convert_text("> [!question] Quiz\n>\n> What is 2+2?\n>\n> 1. 4\n").split("\n")
        self.assertEqual(lesson.quiz_outcomes(lines), [("What is 2+2?", "(unanswered)")])

    def test_other_callouts_ignored(self):
        lines = ["> [!success] ✓ Correct", ">", "> Selected: 1. 4", "", "> [!aside]+ Why?", "> Because."]
        self.assertEqual(lesson.quiz_outcomes(lines), [])


if __name__ == "__main__":
    unittest.main()
