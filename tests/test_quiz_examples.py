import importlib.util
import json
import shlex
import shutil
import subprocess
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
        self.meanwhile = None  # what happens to the note while the popup is open
        def ask(record, displayed, msg_details, multi):
            self.seen.append(self.note.read_text())
            if self.meanwhile:
                self.meanwhile()
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

    def test_open_block_while_answering(self):
        self.ui = [{"action": "accept", "answers": [2]}]
        quiz_server.run_quiz(dict(ARGS), "toolu_1")
        self.assertTrue(self.seen[0].startswith("> [!question|quiz]+ What is 2+2?"))
        self.assertIn("> 2. 5", self.seen[0])
        self.assertNotIn("Arithmetic.", self.seen[0])
        self.assertEqual(self.headers(), ["> [!failure|quiz]- ✗ What is 2+2?"])

    def test_open_block_replaced_in_place(self):
        self.note.write_text("Before.\n")
        self.meanwhile = lambda: self.note.write_text(self.note.read_text() + "\nWritten meanwhile.\n")
        self.ui = [{"action": "accept", "answers": [1]}]
        quiz_server.run_quiz(dict(ARGS), "toolu_1")
        text = self.note.read_text()
        self.assertTrue(text.startswith("Before.\n\n> [!success|quiz]- ✓ What is 2+2?"))
        self.assertTrue(text.endswith("> Arithmetic.\n\nWritten meanwhile.\n"))

    def test_open_block_edited_away(self):
        self.meanwhile = lambda: self.note.write_text("Edited.\n")
        self.ui = [{"action": "accept", "answers": [1]}]
        quiz_server.run_quiz(dict(ARGS), "toolu_1")
        self.assertTrue(self.note.read_text().startswith("Edited.\n\n> [!success|quiz]- ✓ What is 2+2?"))

    def test_figure_above_open_block_is_kept(self):
        (self.d / ".course").mkdir()
        (self.d / ".course" / "book.json").write_text("{}")
        (self.d / ".course" / "state.json").write_text(json.dumps({"slug": "pml1"}))
        for name, value in [("crop", lambda c, fid: str(self.d / f"pml1-fig-{fid}.png"))]:
            self.addCleanup(setattr, quiz_server.figures, name, getattr(quiz_server.figures, name))
            setattr(quiz_server.figures, name, value)
        self.addCleanup(setattr, quiz_server, "course_figure", quiz_server.course_figure)
        quiz_server.course_figure = lambda text: None
        self.ui = [{"action": "accept", "answers": [1]}]
        quiz_server.run_quiz({**ARGS, "question": "In Figure 1.4, what is 2+2?"}, "toolu_1")
        text = self.note.read_text()
        self.assertEqual(text.count("![[pml1-fig-1.4.png|600]] ^fig-1-4"), 1)
        self.assertTrue(text.startswith("![[pml1-fig-1.4.png|600]] ^fig-1-4\n\n> [!success|quiz]- ✓ In "))
        self.assertNotIn("[!question|quiz]+", text)

    def test_form_tells_teacher_about_tmux(self):
        self.ui = [{"action": "accept", "answers": [1]}]
        out = quiz_server.run_quiz(dict(ARGS), "toolu_1")
        self.assertIn("start Claude Code inside tmux", out["content"][0]["text"])

    def test_popup_too_tall_retries(self):
        calls = []
        def fake_run(cmd, **kw):
            calls.append(cmd)
            if len(calls) == 1:
                return subprocess.CompletedProcess(cmd, 1, "", "height too large")
            out_path = shlex.split(cmd[-1])[-1]
            with open(out_path, "w") as f:
                json.dump({"action": "accept", "answers": [1]}, f)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        for name, value in [("tmux_available", lambda: True), ("subprocess", type("S", (), {
                "run": staticmethod(fake_run), "DEVNULL": subprocess.DEVNULL, "PIPE": subprocess.PIPE}))]:
            self.addCleanup(setattr, quiz_server, name, getattr(quiz_server, name))
            setattr(quiz_server, name, value)
        out = quiz_server.run_quiz(dict(ARGS), "toolu_1")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][calls[1].index("-h") + 1], "90%")
        self.assertEqual(self.seen, [])  # the form was not used
        self.assertNotIn("tmux", out["content"][0]["text"].split("QUIZ_JSON")[0])
        self.assertEqual(self.headers(), ["> [!success|quiz]- ✓ What is 2+2?"])

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
