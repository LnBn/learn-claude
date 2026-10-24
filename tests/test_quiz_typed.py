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

ARGS = {"question": "Expected tosses to get $n$ heads in a row?", "answer": "2^(n+1)-2", "answerLatex": "2^{n+1}-2",
        "variables": {"n": "int 1..12"}, "wrongAnswers": [{"answer": "2^n", "why": "Counted only the last run."}],
        "explanation": "Condition on the first tail."}


def text_of(out):
    return out["content"][0]["text"]


def record_of(out):
    return json.loads(text_of(out).split("QUIZ_JSON: ", 1)[1])


class TypedQuiz(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="quiz-typed-"))
        self.addCleanup(shutil.rmtree, self.d, True)
        self.note = self.d / "lesson.md"
        self.note.write_text("")
        self.ui = []  # scripted popup results, one per call
        self.asked_with = []  # the records the UI was shown

        def ask(record, displayed, msg_details, multi):
            self.asked_with.append(record)
            return self.ui.pop(0)
        for name, value in [("log_file", lambda: str(self.note)), ("tmux_available", lambda: False),
                            ("set_target", lambda tool_use_id: None), ("ask_via_elicitation", ask),
                            ("LAST_ASKED", str(self.d / "last-asked.json")),
                            ("QUIZ_LOGGED", str(self.d / "quiz-logged.json"))]:
            self.addCleanup(setattr, quiz_server, name, getattr(quiz_server, name))
            setattr(quiz_server, name, value)

    def headers(self):
        return [ln for ln in self.note.read_text().split("\n") if ln.startswith("> [!")]

    def test_validation_errors(self):
        for change, msg in [({"options": [{"label": "1"}, {"label": "2"}]}, "give either answer or options, not both"),
                            ({"answer": "2^(n+1"}, "answer: can't read: unclosed bracket"),
                            ({"variables": {}}, "answer: unknown name: n"),
                            ({"variables": {"n": "int 5..1"}}, 'n: bad range "int 5..1"'),
                            ({"answer": "1/(n-n)"}, "answer is undefined at most points of the ranges"),
                            ({"wrongAnswers": [{"answer": "2(2^n-1)", "why": "x"}]},
                             "wrong answer 2(2^n-1) is equivalent to answer"),
                            ({"wrongAnswers": [{"answer": "2^(", "why": "x"}]}, "wrong answer 2^(: can't read"),
                            ({"multiSelect": True}, "multiSelect, correctAnswer and shuffle belong to the options mode")]:
            out = quiz_server.run_quiz({**ARGS, **change}, "toolu_1")
            self.assertTrue(out.get("isError"), change)
            self.assertIn(msg, text_of(out))
        self.assertEqual(self.note.read_text(), "")

    def test_correct(self):
        self.ui = [{"action": "accept", "typed": "2*2^n-2"}]
        text = text_of(quiz_server.run_quiz(dict(ARGS), "toolu_1"))
        self.assertTrue(text.startswith("User answered correctly.\nTyped: 2*2^n-2 (reads as "), text)
        self.assertEqual(self.headers(), ["> [!success|quiz]- ✓ Expected tosses to get $n$ heads in a row?"])

    def test_matched_wrong(self):
        self.ui = [{"action": "accept", "typed": "2^n"}]
        out = quiz_server.run_quiz(dict(ARGS), "toolu_1")
        text = text_of(out)
        self.assertIn("User answered incorrectly.", text)
        self.assertIn("Correct: 2^(n+1)-2", text)
        self.assertIn("Matched common mistake: Counted only the last run.", text)
        record = record_of(out)
        self.assertEqual((record["mode"], record["matchedWrong"], record["decimal"]), ("typed", 0, False))

    def test_decimal(self):
        self.ui = [{"action": "accept", "typed": "0.333"}]
        args = {"question": "P(A)?", "answer": "1/3", "explanation": "Symmetry."}
        self.assertIn("(decimal, matched to 3 significant figures)", text_of(quiz_server.run_quiz(args, "toolu_1")))

    def test_dont_know(self):
        self.ui = [{"action": "accept", "typed": "", "dontKnow": True}]
        self.assertIn("User answered \"I don't know\"", text_of(quiz_server.run_quiz(dict(ARGS), "toolu_1")))

    def test_unreadable_from_fallback_form(self):
        self.ui = [{"action": "accept", "typed": "2^("}]
        text = text_of(quiz_server.run_quiz(dict(ARGS), "toolu_1"))
        self.assertIn("User answered incorrectly.", text)
        self.assertIn("could not be read: can't read: unclosed bracket", text)

    def test_reask_after_question(self):
        self.ui = [{"action": "ask", "question": "Is n fixed?"}, {"action": "accept", "typed": "2^(n+1)-2"}]
        quiz_server.run_quiz(dict(ARGS), "toolu_1")
        quiz_server.run_quiz(dict(ARGS), "toolu_2")
        self.assertEqual(self.headers(), ["> [!note|quiz]- Asked first: Expected tosses to get $n$ heads in a row?",
                                          "> [!success|quiz]- ✓ Expected tosses to get $n$ heads in a row?"])

    def test_other_question_is_not_a_reask(self):
        self.ui = [{"action": "ask", "question": "Is n fixed?"}, {"action": "accept", "typed": "1/3"}]
        quiz_server.run_quiz(dict(ARGS), "toolu_1")
        out = quiz_server.run_quiz({"question": "P(A)?", "answer": "1/3", "explanation": "x"}, "toolu_2")
        self.assertFalse(record_of(out)["reask"])



class TypedUI(unittest.TestCase):
    RECORD = {"mode": "typed", "question": "Q?", "details": "", "answer": "2^(n+1)-2", "answerLatex": "2^{n+1}-2",
              "variables": {"n": "int 1..12"}, "exact": False, "wrongAnswers": [{"answer": "2^n", "why": "w"}],
              "explanation": "E."}

    def test_popup_spec(self):
        spec = quiz_server.popup_spec(self.RECORD)
        self.assertEqual(spec["mode"], "typed")
        self.assertEqual(spec["answerDisplay"], "2ⁿ⁺¹-2")
        self.assertEqual(quiz_server.popup_spec({**self.RECORD, "answerLatex": ""})["answerDisplay"], "2ⁿ⁺¹ − 2")
        for key in ("answer", "variables", "exact", "wrongAnswers", "explanation", "question", "dontKnow"):
            self.assertIn(key, spec)
        self.assertNotIn("options", spec)

    def test_fallback_form(self):
        sent = []

        def request(method, params):
            sent.append(params)
            return {"result": {"action": "accept", "content": {"answer": " 2^n ", "dk": False, "note": "hm"}}}
        self.addCleanup(setattr, quiz_server, "request", quiz_server.request)
        quiz_server.request = request
        ui = quiz_server.ask_via_elicitation(self.RECORD, [], msg_details="", multi=False)
        self.assertEqual(ui, {"action": "accept", "typed": "2^n", "dontKnow": False, "note": "hm"})
        props = sent[0]["requestedSchema"]["properties"]
        self.assertEqual(props["answer"]["type"], "string")
        self.assertNotIn("enum", props["answer"])


if __name__ == "__main__":
    unittest.main()
