import json
import shutil
import tempfile
import unittest
from pathlib import Path

import tests._vault  # noqa: F401  (puts hooks/ on the path)
import md_log
import quiz_block
from tests.test_quiz_block import CODE_QUESTION, record

LONG_QUESTION = " ".join(["word"] * 35) + " — which one?"


class FromResult(unittest.TestCase):
    def test_from_result_renders_folded(self):
        r = record(answers=[1], correct=True, dontKnow=False, note="")
        self.assertEqual(md_log.quiz_blocks_from_result("ok\nQUIZ_JSON: " + json.dumps(r)), quiz_block.render(r))

    def test_reask_is_a_full_block(self):
        r = record(answers=[1], correct=True, reask=True)
        self.assertEqual(md_log.quiz_blocks_from_result("ok\nQUIZ_JSON: " + json.dumps(r)), quiz_block.render(r))


class InsertBeforeQuiz(unittest.TestCase):
    def setUp(self):
        d = Path(tempfile.mkdtemp(prefix="mirror-quiz-"))
        self.addCleanup(shutil.rmtree, d, True)
        self.note = d / "lesson.md"
        orig = md_log.log_file
        md_log.log_file = lambda: str(self.note)
        self.addCleanup(setattr, md_log, "log_file", orig)

    def check(self, question):
        block = quiz_block.render(record(question=question, answers=[1], correct=True))
        self.note.write_text("Earlier.\n\n" + block + "\n")
        self.assertTrue(md_log.insert_before_quiz("Prose.", question))
        self.assertIn("Prose.\n\n" + block.split("\n")[0], self.note.read_text())

    def test_insert_before_folded_block(self):
        self.check("What is 2+2?")

    def test_insert_before_cut_title(self):
        self.check(LONG_QUESTION)

    def test_insert_before_multiline_question(self):
        self.check(CODE_QUESTION)

    def test_insert_before_code_first_question(self):
        self.check("```python\nprint(1)\n```\nWhat prints?")

    def test_insert_when_a_link_splits_the_cut_title(self):
        # figures.py links "Figure 1.4" in the body; the title was cut between "Figure" and its number
        question = "x" * 88 + " see Figure 1.4 for the tree; what is at the root?"
        lines = quiz_block.render(record(question=question, answers=[1], correct=True)).split("\n")
        self.assertTrue(lines[0].endswith("see Figure…"))
        lines[1:] = [ln.replace("Figure 1.4", "[[#^fig-1-4|Figure 1.4]]") for ln in lines[1:]]
        self.note.write_text("Earlier.\n\n" + "\n".join(lines) + "\n")
        self.assertTrue(md_log.insert_before_quiz("Prose.", question))
        self.assertIn("Prose.\n\n" + lines[0], self.note.read_text())

    def test_insert_picks_last_match(self):
        first = quiz_block.render(record(answers=[2], correct=False))
        second = quiz_block.render(record(answers=[1], correct=True))
        self.note.write_text(first + "\n\nMiddle.\n\n" + second + "\n")
        self.assertTrue(md_log.insert_before_quiz("Prose.", "What is 2+2?"))
        self.assertIn("Middle.\n\nProse.\n\n> [!success|quiz]-", self.note.read_text())

    def test_no_match(self):
        self.note.write_text(quiz_block.render(record(answers=[1], correct=True)) + "\n")
        self.assertFalse(md_log.insert_before_quiz("Prose.", "Another question?"))


if __name__ == "__main__":
    unittest.main()
