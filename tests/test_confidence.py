"""Confidence on quiz answers: the popup asks for it, the server returns it, the note keeps it."""
import curses
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests._vault import REPO
import quiz_block

sys.path.insert(0, str(REPO / "mcp"))
import quiz_popup  # noqa: E402

spec = importlib.util.spec_from_file_location("quiz_server", REPO / "mcp" / "quiz_server.py")
quiz_server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quiz_server)

MC = {"question": "What is 2+2?", "details": "", "dontKnow": "I don't know", "multiSelect": False,
      "options": [{"index": 1, "label": "4"}, {"index": 2, "label": "5"}, {"index": 3, "label": "6"},
                  {"index": 4, "label": "22"}],
      "correctIndices": [1], "explanation": "Arithmetic."}
TYPED = {"mode": "typed", "question": "Expected tosses?", "details": "", "dontKnow": "I don't know",
         "answer": "2^(n+1)-2", "variables": {"n": "int 1..12"}, "exact": False, "wrongAnswers": [],
         "explanation": "Condition on the first tail.", "answerDisplay": "2ⁿ⁺¹ − 2"}


class Screen:
    """A stand-in for the curses window: records what is drawn, returns scripted keys."""

    def __init__(self, keys, height=40):
        self.keys = list(keys)
        self.drawn = []
        self.height = height

    def getmaxyx(self):
        return self.height, 100

    def erase(self):
        self.drawn.append([])

    def addstr(self, row, col, text, attr=0):
        self.drawn[-1].append(text)

    def refresh(self):
        pass

    def move(self, *a):
        pass

    def getch(self):
        k = self.keys.pop(0)
        return ord(k) if isinstance(k, str) else k

    def get_wch(self):
        k = self.keys.pop(0)
        return chr(k) if isinstance(k, int) and k < 256 else k

    def screens(self):
        return ["".join(s) for s in self.drawn]


class Popup(unittest.TestCase):
    def setUp(self):
        for name, value in [("curs_set", lambda n: None), ("use_default_colors", lambda: None),
                            ("init_pair", lambda *a: None), ("color_pair", lambda n: 0)]:
            p = mock.patch.object(curses, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.d = Path(tempfile.mkdtemp(prefix="popup-"))
        self.addCleanup(shutil.rmtree, self.d, True)
        self.out = self.d / "result.json"

    def run_popup(self, spec, keys):
        scr = Screen(keys)
        quiz_popup.main(scr, spec, str(self.out))
        return json.loads(self.out.read_text()), scr

    def test_choice_then_confidence(self):
        result, scr = self.run_popup(MC, ["2", 10, "4", " "])  # option 2, Enter, 80%, any key past the feedback
        self.assertEqual(result, {"action": "accept", "answers": [2], "dontKnow": False, "note": "", "confidence": 80})
        sure = next(s for s in scr.screens() if "HOW SURE ARE YOU?" in s)
        for text in ("Your answer: 2. 5", "1    20%   a guess", "5   100%   certain", "right 25% of the time"):
            self.assertIn(text, sure)
        self.assertIn("You were 80% sure.", scr.screens()[-1])

    def test_other_keys_wait_and_esc_goes_back(self):
        result, _ = self.run_popup(MC, ["1", 10, "x", "9", 27, "j", 10, "5", " "])  # Esc: back, move down, pick 2
        self.assertEqual((result["answers"], result["confidence"]), ([2], 100))

    def test_dont_know_skips_confidence(self):
        result, scr = self.run_popup(MC, ["k", 10, " "])  # up from option 1 wraps to "I don't know"
        self.assertEqual(result, {"action": "accept", "answers": [], "dontKnow": True, "note": ""})
        self.assertFalse(any("HOW SURE" in s for s in scr.screens()))

    def test_esc_on_the_question_still_cancels(self):
        result, _ = self.run_popup(MC, [27])
        self.assertEqual(result, {"action": "cancel"})

    def test_multi_select_has_no_chance_line(self):
        result, scr = self.run_popup({**MC, "multiSelect": True, "correctIndices": [1, 3]}, ["1", "3", 10, "3", " "])
        self.assertEqual((result["answers"], result["confidence"]), ([1, 3], 60))
        self.assertFalse(any("blind guess" in s for s in scr.screens()))

    def test_typed(self):
        result, scr = self.run_popup(TYPED, list("2*2^n-2") + [10, "2", " "])
        self.assertEqual(result, {"action": "accept", "typed": "2*2^n-2", "dontKnow": False, "note": "",
                                  "confidence": 40})
        sure = next(s for s in scr.screens() if "HOW SURE ARE YOU?" in s)
        self.assertIn("Your answer: 2 · 2ⁿ − 2", sure)

    def test_typed_dont_know(self):
        result, scr = self.run_popup(TYPED, [curses.KEY_DOWN, 10, " "])
        self.assertEqual(result, {"action": "accept", "typed": "", "dontKnow": True, "note": ""})

    def test_short_popup_keeps_the_scale(self):
        scr = Screen(["3"], height=12)
        self.assertEqual(quiz_popup.ask_confidence(scr, "1. 4", scr.getch, 25), 60)
        shown = scr.screens()[-1]
        for text in ("Your answer: 1. 4", "100%   certain", "right 25% of the time", "1–5 choose"):
            self.assertIn(text, shown)

    def test_keys(self):
        self.assertEqual([quiz_popup.confidence_key(k) for k in ("1", "5", ord("3"), "0", "6", 27, "\x1b", 410)],
                         [20, 100, 60, None, None, "back", "back", None])


ARGS = {"question": "What is 2+2?", "explanation": "Arithmetic.", "shuffle": False, "correctAnswer": "four",
        "options": [{"label": "4", "value": "four"}, {"label": "5", "value": "five"},
                    {"label": "6", "value": "six"}, {"label": "22", "value": "tt"}]}


class Server(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="quiz-conf-"))
        self.addCleanup(shutil.rmtree, self.d, True)
        self.note = self.d / "lesson.md"
        self.note.write_text("")
        self.ui = []
        for name, value in [("log_file", lambda: str(self.note)), ("tmux_available", lambda: False),
                            ("set_target", lambda tool_use_id: None),
                            ("ask_via_elicitation", lambda *a, **k: self.ui.pop(0)),
                            ("LAST_ASKED", str(self.d / "last-asked.json")),
                            ("QUIZ_LOGGED", str(self.d / "quiz-logged.json"))]:
            self.addCleanup(setattr, quiz_server, name, getattr(quiz_server, name))
            setattr(quiz_server, name, value)

    def run_quiz(self, ui, args=ARGS):
        self.ui = [ui]
        out = quiz_server.run_quiz(dict(args), "toolu_1")
        text = out["content"][0]["text"]
        return text, json.loads(text.split("QUIZ_JSON: ", 1)[1])

    def test_confidence_reaches_the_model_and_the_note(self):
        text, record = self.run_quiz({"action": "accept", "answers": [2], "confidence": 80})
        self.assertIn("Selected: 2. 5\nCorrect: 1. 4\nConfidence: 80%\n", text)
        self.assertEqual(record["confidence"], 80)
        self.assertIn("> Confidence: 80%", self.note.read_text())

    def test_at_or_below_chance(self):
        text, _ = self.run_quiz({"action": "accept", "answers": [1], "confidence": 20})
        self.assertIn("Confidence: 20% (at or below the 25% chance of a blind guess: they distrust their pick)", text)

    def test_none_without_a_value_or_on_dont_know(self):
        for ui in ({"action": "accept", "answers": [1]}, {"action": "accept", "answers": [], "dontKnow": True,
                                                         "confidence": 80},
                   {"action": "accept", "answers": [1], "confidence": 140}):
            text, record = self.run_quiz(ui)
            self.assertNotIn("Confidence", text.split("QUIZ_JSON")[0])
            self.assertNotIn("confidence", record)

    def test_typed(self):
        args = {"question": "P?", "answer": "1/3", "explanation": "x"}
        text, record = self.run_quiz({"action": "accept", "typed": "1/3", "confidence": 100}, args)
        self.assertIn("Confidence: 100%", text)
        self.assertNotIn("chance", text.split("QUIZ_JSON")[0])
        self.assertEqual(record["confidence"], 100)


class Block(unittest.TestCase):
    RECORD = {"status": "answered", "question": "What is 2+2?", "details": "", "multiSelect": False,
              "options": [{"index": 1, "label": "4"}, {"index": 2, "label": "5"}], "correctIndices": [1],
              "explanation": "Arithmetic.", "answers": [2], "correct": False, "dontKnow": False, "note": ""}

    def test_render_and_parse(self):
        text = quiz_block.render({**self.RECORD, "confidence": 80})
        self.assertIn("> Selected: 2. 5\n> Correct answer: 1. 4\n> Confidence: 80%\n>\n> Arithmetic.", text)
        self.assertEqual(quiz_block.parse(text.split("\n"))["confidence"], 80)
        right = quiz_block.render({**self.RECORD, "answers": [1], "correct": True, "confidence": 40})
        self.assertIn("> Selected: 1. 4\n> Confidence: 40%", right)
        typed = quiz_block.render({"mode": "typed", "status": "answered", "question": "P?", "answer": "1/3",
                                   "answerLatex": "", "typed": "0.333", "correct": True, "decimal": True,
                                   "explanation": "x", "confidence": 60})
        self.assertIn("> Your answer: `0.333`\n> Exact value: `1/3`\n> Confidence: 60%", typed)

    def test_old_blocks_still_parse(self):
        old = quiz_block.render(self.RECORD).split("\n")
        p = quiz_block.parse(old)
        self.assertEqual((p["outcome"], p["confidence"]), ("✗", None))
        self.assertNotIn("Confidence", "\n".join(old))
        self.assertEqual(quiz_block.parse(["> [!success|quiz]- ✓ A title only"])["confidence"], None)


if __name__ == "__main__":
    unittest.main()
