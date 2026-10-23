import unittest

from tests._vault import make_vault, run
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



# ---- old notes, as the vault holds them (lines shortened)

OLD_PAIR = """Prose before.

> [!question] Quiz
>
> In the $k$-pirate game, which pirates are the cheapest votes for the proposer to buy?
>
> 1. The pirates who get 0 coins in the $(k-1)$-pirate game
> 2. The pirates who get 1 coin in the $(k-1)$-pirate game

> [!success] ✓ Correct
>
> Selected: 1. The pirates who get 0 coins in the $(k-1)$-pirate game
>
> If the proposer's plan fails, he dies.

Prose after.
"""

OLD_INCORRECT = """> [!question] Quiz
>
> Apply the rule. Which packages does dnf install?
>
> 1. perl-5.32.1
> 2. Nothing

> [!failure] ✗ Incorrect
>
> Selected: 2. Nothing
> Correct answer: 1. perl-5.32.1
>
> The stream is the default.
"""

OLD_DONT_KNOW = """> [!question] Quiz
>
> Which likelihood does TrueSkill use?
>
> 1. A normal CDF in the skill difference
> 2. A normal in the skill

> [!info] I don't know
>
> Correct answer: 1. A normal CDF in the skill difference
>
> Given a skill difference $d$, the probability of a win is a sigmoid-like curve in $d$.
"""

OLD_CANCELLED = """> [!question] Quiz
>
> What is $p$ to two decimals?
>
> 1. 0.65
> 2. 0.67

> [!warning] Quiz — cancelled
>
> (user skipped)

The previous question had an error in its answer key.
"""

OLD_ASKED = """> [!question] Quiz
>
> Fresh case. Which packages does dnf admit?
>
> 1. black-24.1, python39-pip-21.3
> 2. black-24.1 fails

> [!note] Asked before answering
>
> What happens if there are multiple repos both declaring a nodejs stream?

Your question, restated: two enabled repos each ship a `nodejs` module.

> [!success] ✓ Correct
>
> Selected: 1. black-24.1, python39-pip-21.3
>
> `python39:3.9` is active.
"""

OLD_UNANSWERED_THEN_REASK = """> [!question] Quiz
>
> For the Iris decision tree of [[#^fig-1-4|Figure 1.4a]], what makes up the parameters $\\boldsymbol{\\theta}$?
>
> 1. For each leaf, the counts of training flowers of each class
> 2. For each internal node, the feature it tests and its threshold


---

## Session — 2026-10-05 (Mon) 13:29

The text is under the heading **1.2.1** in this note.

> [!question] Quiz
>
> For the Iris decision tree of [[#^fig-1-4|Figure 1.4a]], what makes up the parameters $\\boldsymbol{\\theta}$?
>
> 1. For each internal node, the feature it tests and its threshold
> 2. For each leaf, the counts of training flowers of each class

> [!failure] ✗ Incorrect
>
> Selected: 2. For each leaf, the counts of training flowers of each class
> Correct answer: 1. For each internal node, the feature it tests and its threshold
"""

OLD_FIGURE_ABOVE = "![[gb-fig-1-4.png|600]] ^fig-1-4\n\n" + OLD_PAIR.split("\n\n", 1)[1]

FALLBACK = """> [!question] Quiz
>
> Which of these can IP alone guarantee about what arrives?
>
> 1. All three arrive, in order, exactly once
> 2. Whatever arrives is at most three packets

> [!example] Answer
>
> (no answer)
"""

PI_NOTE = """> [!question] Quiz
> Which way does KL(q||p) push q?
>
> 1. Over-disperse
> 2. Under-disperse

> [!success] Quiz — correct ✓
> Your answer: 2
"""


def headers(text):
    return [ln for ln in text.split("\n") if ln.startswith("> [!")]


class Convert(unittest.TestCase):
    def test_pair(self):
        out = quiz_block.convert_text(OLD_PAIR)
        self.assertEqual(headers(out), ["> [!success|quiz]- ✓ In the $k$-pirate game, which pirates are the cheapest "
                                        "votes for the proposer to buy?"])
        self.assertIn("> 2. The pirates who get 1 coin in the $(k-1)$-pirate game", out)
        self.assertIn("> Selected: 1. The pirates who get 0 coins in the $(k-1)$-pirate game", out)
        self.assertIn("> If the proposer's plan fails, he dies.", out)
        self.assertEqual(out.count("which pirates are the cheapest"), 1)
        self.assertTrue(out.startswith("Prose before.\n\n> [!success|quiz]-"))
        self.assertTrue(out.endswith("he dies.\n\nProse after.\n"))
        self.assertEqual(quiz_block.parse(out.split("\n")[2:15])["outcome"], "✓")

    def test_incorrect_dont_know_cancelled(self):
        self.assertEqual(headers(quiz_block.convert_text(OLD_INCORRECT)),
                         ["> [!failure|quiz]- ✗ Apply the rule. Which packages does dnf install?"])
        self.assertEqual(headers(quiz_block.convert_text(OLD_DONT_KNOW)),
                         ["> [!info|quiz]- ? Which likelihood does TrueSkill use?"])
        out = quiz_block.convert_text(OLD_CANCELLED)
        self.assertEqual(headers(out), ["> [!warning|quiz]- ⊘ Skipped: What is $p$ to two decimals?"])
        self.assertTrue(out.endswith("\n\nThe previous question had an error in its answer key.\n"))

    def test_asked(self):
        out = quiz_block.convert_text(OLD_ASKED)
        self.assertEqual(headers(out), ["> [!note|quiz]- Asked first: Fresh case. Which packages does dnf admit?",
                                        "> [!success|quiz]- ✓ Fresh case. Which packages does dnf admit?"])
        asked, rest = out.split("\n\nYour question, restated", 1)
        self.assertIn("> Your question: What happens if there are multiple repos both declaring a nodejs stream?", asked)
        self.assertIn("> 1. black-24.1, python39-pip-21.3", asked)
        self.assertIn("> 1. black-24.1, python39-pip-21.3", rest)
        self.assertIn("> `python39:3.9` is active.", rest)

    def test_unanswered_then_reask(self):
        out = quiz_block.convert_text(OLD_UNANSWERED_THEN_REASK)
        title = ("For the Iris decision tree of [[#^fig-1-4|Figure 1.4a]], what makes up the parameters "
                 "$\\boldsymbol{\\theta}$?")
        self.assertEqual(headers(out), ["> [!question|quiz]- " + quiz_block.cut_title(title),
                                        "> [!failure|quiz]- ✗ " + quiz_block.cut_title(title)])
        self.assertIn("\n\n---\n\n## Session — 2026-10-05 (Mon) 13:29\n\nThe text is under the heading", out)
        self.assertIn("> Correct answer: 1. For each internal node", out)

    def test_figure_stays_above(self):
        out = quiz_block.convert_text(OLD_FIGURE_ABOVE)
        self.assertTrue(out.startswith("![[gb-fig-1-4.png|600]] ^fig-1-4\n\n> [!success|quiz]- ✓ In the $k$"))

    def test_removed_callout_leaves_no_extra_blank_lines(self):
        spaced = OLD_PAIR.replace("buy?\n>\n> 1.", "buy?\n>\n> 1.").replace("\n\n> [!success]", "\n\n\n> [!success]")
        spaced = spaced.replace("he dies.\n\nProse", "he dies.\n\n\nProse")
        out = quiz_block.convert_text(spaced)
        self.assertNotIn("\n\n\n\n", out)
        self.assertTrue(out.endswith("he dies.\n\n\nProse after.\n"))

    def test_fallback_untouched(self):
        self.assertEqual(quiz_block.convert_text(FALLBACK), FALLBACK)

    def test_pi_note_refused(self):
        with self.assertRaises(ValueError) as e:
            quiz_block.convert_text(PI_NOTE)
        self.assertIn("pi", str(e.exception))

    def test_idempotent(self):
        once = quiz_block.convert_text(OLD_PAIR + "\n" + OLD_ASKED)
        self.assertEqual(quiz_block.convert_text(once), once)

    def test_mixed_refused(self):
        mixed = quiz_block.convert_text(OLD_INCORRECT) + "\n" + OLD_PAIR
        with self.assertRaises(ValueError):
            quiz_block.convert_text(mixed)
        self.assertEqual(len(headers(quiz_block.convert_text(mixed, force=True))), 2)
        with_fallback = quiz_block.convert_text(OLD_INCORRECT) + "\n" + FALLBACK
        self.assertEqual(quiz_block.convert_text(with_fallback), with_fallback)

    def test_cli_dry_run_and_write(self):
        vault = make_vault(self)
        note = vault / "lesson.md"
        note.write_text(OLD_PAIR)
        r = run(vault, "quiz_block.py", "convert", "lesson.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("+> [!success|quiz]- ✓ In the $k$-pirate game", r.stdout)
        self.assertEqual(note.read_text(), OLD_PAIR)
        r = run(vault, "quiz_block.py", "convert", "--write", "lesson.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(note.read_text(), quiz_block.convert_text(OLD_PAIR))
        backups = list((vault / ".claude" / "md-log-state" / "quiz-fold-backup").iterdir())
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), OLD_PAIR)

    def test_cli_refusal(self):
        vault = make_vault(self)
        (vault / "pi.md").write_text(PI_NOTE)
        r = run(vault, "quiz_block.py", "convert", "--write", "pi.md")
        self.assertEqual(r.returncode, 1)
        self.assertIn("REFUSED pi.md: pi", r.stdout)
        self.assertEqual((vault / "pi.md").read_text(), PI_NOTE)


if __name__ == "__main__":
    unittest.main()
