import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tests._vault import REPO

spec = importlib.util.spec_from_file_location("quiz_server", REPO / "mcp" / "quiz_server.py")
quiz_server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quiz_server)

NOTE = """### 2.3.3 Door to offer

> [!example] Example 19 — All four cases
> | a | b |
^ex-19
"""


class MissingExamples(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="quiz-examples-"))
        self.addCleanup(shutil.rmtree, self.d, True)
        self.note = self.d / "lesson.md"
        self.note.write_text(NOTE)

    def test_example_in_the_note(self):
        self.assertEqual(quiz_server.missing_examples("Use Example 19.", str(self.note)), [])

    def test_example_not_written(self):
        self.assertEqual(quiz_server.missing_examples("Use the signs of Example 20: write", str(self.note)), ["20"])
        self.assertEqual(quiz_server.missing_examples("Example 2 and Example 20", str(self.note)), ["2", "20"])

    def test_book_examples_are_not_checked(self):
        self.assertEqual(quiz_server.missing_examples("As in Example 2.3 of the book.", str(self.note)), [])

    def test_no_note(self):
        self.assertEqual(quiz_server.missing_examples("Example 20", None), [])
        self.assertEqual(quiz_server.missing_examples("Example 20", str(self.d / "absent.md")), [])

    def test_review_note_cites_its_lesson(self):
        review = self.d / "lesson — Review.md"
        review.write_text("### Before 2.3.4\n")
        self.assertEqual(quiz_server.missing_examples("Example 19", str(review)), [])

    def test_course_review_note_cites_any_chapter(self):
        (self.d / ".course").mkdir()
        (self.d / ".course" / "book.json").write_text("{}")
        (self.d / ".course" / "state.json").write_text(json.dumps({"slug": "gb"}))
        (self.d / "gb-ch02.md").write_text(NOTE)
        review = self.d / "gb-review.md"
        review.write_text("### Before 2.3.4\n")
        self.assertEqual(quiz_server.missing_examples("Example 19", str(review)), [])
        self.assertEqual(quiz_server.missing_examples("Example 19", str(self.d / "gb-ch03.md")), [])  # absent note
        (self.d / "gb-ch03.md").write_text("### 3.1 Start\n")
        self.assertEqual(quiz_server.missing_examples("Example 19", str(self.d / "gb-ch03.md")), ["19"])

    def test_run_quiz_refuses(self):
        orig = quiz_server.log_file
        quiz_server.log_file = lambda: str(self.note)
        self.addCleanup(setattr, quiz_server, "log_file", orig)
        out = quiz_server.run_quiz({
            "question": "He answers no. What follows?", "details": "Use the signs of Example 20.",
            "options": [{"label": "Left", "value": "l"}, {"label": "Right", "value": "r"}],
            "correctAnswer": "r", "explanation": "Signs.",
        }, "toolu_test")
        self.assertTrue(out["isError"])
        self.assertIn("Example 20 is not in the note", out["content"][0]["text"])


ARGS = {
    "question": "What is 2+2?", "options": [{"label": "4", "value": "four"}, {"label": "5", "value": "five"}],
    "correctAnswer": "four", "explanation": "Arithmetic.", "shuffle": False,
}


class WritesOneBlock(unittest.TestCase):
    """The server writes one folded block per quiz call, after the learner acts, and nothing before."""

    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="quiz-block-"))
        self.addCleanup(shutil.rmtree, self.d, True)
        self.note = self.d / "lesson.md"
        self.note.write_text("")
        self.ui = []  # scripted popup results, one per call
        self.seen = []  # the note's content when the popup opened
        def ask(record, displayed, msg_details, multi):
            self.seen.append(self.note.read_text())
            return self.ui.pop(0)
        for name, value in [("log_file", lambda: str(self.note)), ("tmux_available", lambda: False),
                            ("set_target", lambda tool_use_id: None), ("ask_via_elicitation", ask),
                            ("LAST_ASKED", str(self.d / "last-asked.json")),
                            ("QUIZ_LOGGED", str(self.d / "quiz-logged.json"))]:
            self.addCleanup(setattr, quiz_server, name, getattr(quiz_server, name))
            setattr(quiz_server, name, value)

    def headers(self):
        return [ln for ln in self.note.read_text().split("\n") if ln.startswith("> [!")]

    def test_answer_writes_one_block(self):
        self.ui = [{"action": "accept", "answers": [1]}]
        quiz_server.run_quiz(dict(ARGS), "toolu_1")
        self.assertEqual(self.headers(), ["> [!success|quiz]- ✓ What is 2+2?"])

    def test_nothing_written_before_answer(self):
        self.ui = [{"action": "accept", "answers": [2]}]
        quiz_server.run_quiz(dict(ARGS), "toolu_1")
        self.assertEqual(self.seen, [""])
        self.assertEqual(self.headers(), ["> [!failure|quiz]- ✗ What is 2+2?"])

    def test_ask_then_reask(self):
        self.ui = [{"action": "ask", "question": "Why?"}, {"action": "accept", "answers": [1]}]
        quiz_server.run_quiz(dict(ARGS), "toolu_1")
        quiz_server.run_quiz(dict(ARGS), "toolu_2")
        self.assertEqual(self.headers(), ["> [!note|quiz]- Asked first: What is 2+2?",
                                          "> [!success|quiz]- ✓ What is 2+2?"])
        self.assertEqual(self.note.read_text().count("What is 2+2?"), 2)
        self.assertIn("> Your question: Why?", self.note.read_text())

    def test_cancel(self):
        self.ui = [{"action": "decline"}]
        quiz_server.run_quiz(dict(ARGS), "toolu_1")
        self.assertEqual(self.headers(), ["> [!warning|quiz]- ⊘ Skipped: What is 2+2?"])


if __name__ == "__main__":
    unittest.main()
