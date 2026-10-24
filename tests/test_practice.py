import json
import re
import subprocess
import sys
import unittest
from collections import Counter
from datetime import date, timedelta

from tests._vault import make_course, make_vault, run

CH02 = """## Session — 2026-10-07 (Wed) 12:32

### 2.4.1 Coin piles

> [!success|quiz]- ✓ Check question
> body

> [!failure|quiz]- ✗ Which pile? $a|b$ #1
> body

*Techniques: [[Symmetry]]*

### 2.4.2 Wise men

> [!info|quiz]- ? How many hats?
> body

```markdown
> [!failure|quiz]- ✗ A quiz quoted in code
```
"""
REVIEW = """### Before 2.5

> [!failure|quiz]- ✗ A recall question
> body
"""
SCHEME = {"paper": "courses/gb/exams/gb-ch02-exam-1.md", "covers": "courses/gb/gb-ch02.md", "course": "gb",
          "chapter": "2", "attempt": 1, "status": "graded", "set": "2026-10-14", "graded": "2026-10-15",
          "misses": ["q7"], "questions": [
              {"id": "q1", "type": "mc", "marks": 2, "text": "Easy one", "section": "gb-ch02#2.4.1 Coin piles"},
              {"id": "q7", "type": "short", "marks": 4, "text": "Explain the hats.", "section": "gb-ch02#2.4.2 Wise men"}]}


class PracticeBase(unittest.TestCase):
    def setUp(self):
        self.vault = make_vault(self)
        self.cdir = make_course(self.vault, "gb")
        (self.cdir / "gb-ch02.md").write_text(CH02, encoding="utf-8")
        (self.cdir / "gb-review.md").write_text(REVIEW, encoding="utf-8")
        t = self.vault / "techniques"
        t.mkdir()
        (t / "Symmetry.md").write_text("# Symmetry\n", encoding="utf-8")
        p = self.vault / "practice"
        p.mkdir()
        (p / "2026-10-20.md").write_text("### Review\n\n> [!failure|quiz]- ✗ A practice quiz\n> body\n")
        e = self.cdir / ".exams"
        e.mkdir()
        (e / "gb-ch02-exam-1.json").write_text(json.dumps(SCHEME))
        i = self.cdir / ".interviews"
        i.mkdir()
        (i / "gb-interview-1.state.json").write_text(json.dumps({
            "status": "finished", "set": "2026-10-18", "length": "short", "number": 1,
            "problems": [{"id": "p1", "outcome": "solved"}, {"id": "p2", "outcome": "hinted"}]}))
        (i / "gb-interview-1.json").write_text(json.dumps({"problems": [
            {"id": "p1", "statement": "First.", "techniques": ["Symmetry"], "technique": "t"},
            {"id": "p2", "statement": "Second problem.", "techniques": ["Symmetry"], "technique": "t"}]}))
        self.cards_path = self.vault / "practice" / ".cards.json"

    def pr(self, *args):
        return run(self.vault, "practice.py", *args)

    def cards(self):
        return json.loads(self.cards_path.read_text(encoding="utf-8"))["cards"]

    def card(self, cid):
        return next(c for c in self.cards() if c["id"] == cid)


class Cards(PracticeBase):
    def test_scan_finds_every_kind(self):
        r = self.pr("scan")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("added 5", r.stdout)
        keys = {c["key"]: c for c in self.cards()}
        quiz = next(c for k, c in keys.items() if k.startswith("quiz:gb-ch02#2.4.1 Coin piles#"))
        self.assertEqual((quiz["missed"], quiz["techniques"], quiz["section"]),
                         ("2026-10-07", ["Symmetry"], "gb-ch02#2.4.1 Coin piles"))
        self.assertEqual(quiz["prompt"], "Which pile? $a|b$ #1")
        self.assertEqual(quiz["kind"], "quiz")
        self.assertTrue(any(k.startswith("quiz:gb-ch02#2.4.2 Wise men#") for k in keys))
        self.assertTrue(any(k.startswith("quiz:gb-review#Before 2.5#") for k in keys))
        self.assertEqual(keys["exam:gb-ch02-exam-1#q7"]["section"], "gb-ch02#2.4.2 Wise men")
        self.assertEqual(keys["exam:gb-ch02-exam-1#q7"]["prompt"], "Explain the hats.")
        self.assertEqual(keys["exam:gb-ch02-exam-1#q7"]["missed"], "2026-10-15")
        self.assertEqual(keys["interview:gb-interview-1#p2"]["techniques"], ["Symmetry"])
        self.assertEqual(keys["interview:gb-interview-1#p2"]["prompt"], "Second problem.")
        self.assertFalse(any("practice" in k or "#p1" in k or "quoted" in c["prompt"] for k, c in keys.items()))
        self.assertEqual(sorted(c["id"] for c in self.cards()), ["c1", "c2", "c3", "c4", "c5"])

    def test_scan_is_idempotent(self):
        self.pr("scan")
        self.assertIn("added 0", self.pr("scan").stdout)
        self.assertEqual(len(self.cards()), 5)

    def test_first_scan_spreads_later_scans_due_next_day(self):
        self.pr("scan")
        dues = sorted(date.fromisoformat(c["due"]) for c in self.cards())
        self.assertTrue(all(date.today() + timedelta(1) <= d <= date.today() + timedelta(14) for d in dues), dues)
        self.assertGreater(len(set(dues)), 1)
        oldest = min(self.cards(), key=lambda c: c["missed"] or "")  # no session header: undated, first
        self.assertEqual(oldest["due"], (date.today() + timedelta(1)).isoformat())
        past = (date.today() - timedelta(3)).isoformat()
        with open(self.cdir / "gb-ch02.md", "a", encoding="utf-8") as f:
            f.write(f"\n## Session — {past} (Mon) 10:00\n\n### 2.5 Later\n\n> [!failure|quiz]- ✗ New miss\n> body\n")
        self.pr("scan")
        new = max(self.cards(), key=lambda c: int(c["id"][1:]))
        self.assertEqual((new["missed"], new["due"]), (past, date.today().isoformat()))

    def test_scheduling(self):
        self.pr("scan")
        for gap in [3, 7, 16, 35]:
            self.pr("result", "c1", "right")
            self.assertEqual(self.card("c1")["due"], (date.today() + timedelta(gap)).isoformat())
        self.pr("result", "c1", "right")
        self.assertEqual(self.card("c1")["status"], "retired")

    def test_wrong_resets(self):
        self.pr("scan")
        self.pr("result", "c1", "right")
        self.pr("result", "c1", "wrong")
        c = self.card("c1")
        self.assertEqual((c["step"], c["due"]), (0, (date.today() + timedelta(1)).isoformat()))
        self.assertEqual([h["result"] for h in c["history"]], ["right", "wrong"])

    def test_due_order_and_limit(self):
        self.pr("scan")
        data = json.loads(self.cards_path.read_text())
        for i, c in enumerate(data["cards"]):
            c["due"] = (date.today() - timedelta(10 - i)).isoformat()
        data["cards"][0]["status"] = "retired"
        self.cards_path.write_text(json.dumps(data))
        out = self.pr("due", "--limit", "2").stdout
        self.assertEqual(re.findall(r"^(c\d+) · ", out, re.M), ["c2", "c3"])
        self.assertIn("  prompt: ", out)
        self.assertIn("  techniques: ", out)

    def test_unknown_card_and_corrupt_file(self):
        self.pr("scan")
        r = self.pr("result", "c99", "right")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no card c99", r.stderr)
        self.cards_path.write_text("{not json")
        r = self.pr("scan")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.cards_path.read_text(), "{not json")

    def test_review_due_in_brief(self):
        self.pr("scan")
        out = run(self.vault, "lesson.py", "summary", "courses/gb/gb-ch02.md").stdout
        self.assertNotIn("REVIEW DUE", out)
        data = json.loads(self.cards_path.read_text())
        data["cards"][0]["due"] = date.today().isoformat()
        self.cards_path.write_text(json.dumps(data))
        out = run(self.vault, "lesson.py", "summary", "courses/gb/gb-ch02.md").stdout
        self.assertIn("REVIEW DUE: 1 cards — /review asks them", out)

    def test_stats(self):
        self.pr("scan")
        self.assertRegex(self.pr("stats").stdout, r"active 5 · retired 0 · due today 0\nnext 7 days: (\d+ ){6}\d+")



class CardFixes(PracticeBase):
    def test_quiz_before_any_section_and_review_session_starts(self):
        (self.vault / "lessons").mkdir()
        (self.vault / "lessons" / "intro.md").write_text(
            "## Session — 2026-10-01 (Wed) 10:00\n\n> [!failure|quiz]- ✗ Probe question\n> body\n")
        (self.cdir / "gb-review.md").write_text(
            REVIEW + "\n## Session — 2026-10-12 (Mon) 10:00\n\n> [!failure|quiz]- ✗ Door to offer\n> body\n")
        self.pr("scan")
        by_prompt = {c["prompt"]: c for c in self.cards()}
        self.assertEqual(by_prompt["Probe question"]["section"], "intro")
        self.assertEqual(by_prompt["Probe question"]["label"], "intro")
        self.assertEqual(by_prompt["Door to offer"]["section"], "gb-review")   # not "Before 2.5"
        self.assertEqual(by_prompt["Door to offer"]["missed"], "2026-10-12")

    def test_lesson_session_continues_its_section(self):
        with open(self.cdir / "gb-ch02.md", "a", encoding="utf-8") as f:
            f.write("\n## Session — 2026-10-08 (Thu) 10:00\n\n> [!failure|quiz]- ✗ Continued check\n> body\n")
        self.pr("scan")
        c = next(c for c in self.cards() if c["prompt"] == "Continued check")
        self.assertEqual(c["section"], "gb-ch02#2.4.2 Wise men")

    def test_multiline_question_prompt(self):
        (self.vault / "lessons").mkdir()
        (self.vault / "lessons" / "q.md").write_text(
            "### A\n\n> [!failure|quiz]- ✗ Let $X$ be uniform on $[0,1]$.\n>\n> Let $X$ be uniform on $[0,1]$.\n"
            "> What is $E[X^2]$?\n>\n> 1. 1/3\n> 2. 1/2\n")
        self.pr("scan")
        self.assertIn("Let $X$ be uniform on $[0,1]$. What is $E[X^2]$?", [c["prompt"] for c in self.cards()])

    def test_retired_card_answered_wrong_comes_back(self):
        self.pr("scan")
        for _ in range(5):
            self.pr("result", "c1", "right")
        self.pr("result", "c1", "wrong")
        self.assertEqual(self.card("c1")["status"], "active")

    def test_stats_next_due(self):
        self.pr("scan")
        out = self.pr("stats").stdout
        first = min(c["due"] for c in self.cards())
        n = sum(c["due"] == first for c in self.cards())
        self.assertIn(f"next due: {first} ({n} cards)", out)



def tech_note(name):
    return (f"# {name}\n\n> [!definition] The trick\n> Trick of {name}.\n\n## Reach for it when\n\n- cue of {name}\n\n"
            f"**In your words:**\n- \"my cue for {name}\" — x, 2026-10-01\n")


class Drills(PracticeBase):
    def setUp(self):
        super().setUp()
        (self.vault / "techniques" / "Symmetry.md").unlink()
        for n in "ABCDE":
            (self.vault / "techniques" / f"{n}.md").write_text(tech_note(n), encoding="utf-8")
        marks = {"A": "✗✗", "B": "✗✗", "D": "✓✓", "E": "✓✓"}  # C has no record
        body = ""
        for name, ms in marks.items():
            body += f"### {name} problem\n\n"
            for m in ms:
                kind = "success" if m == "✓" else "failure"
                body += f"> [!{kind}|quiz]- {m} Q on {name}\n> body\n\n"
            body += f"*Techniques: [[{name}]]*\n\n"
        (self.vault / "lessons").mkdir()
        (self.vault / "lessons" / "drills.md").write_text(body, encoding="utf-8")
        run(self.vault, "technique.py", "sync")

    def start_drill(self, n):
        r = self.pr("drill", "--n", str(n))
        self.assertEqual(r.returncode, 0, r.stderr)
        return re.search(r"^DRILL: (\S+)", r.stdout, re.M).group(1)

    def slots(self, d):
        return json.loads((self.vault / "practice" / ".drills" / f"{d}.json").read_text())["slots"]

    def write_drill_problems(self, d, problems):
        (self.vault / "practice" / ".drills" / f"{d}.problems.json").write_text(json.dumps({"problems": problems}))

    def valid_problems(self, n):
        return [{"slot": i, "statement": f"Problem {i}?", "answer": "1/4", "variables": {}, "answerLatex": "\\frac14",
                 "solution": "Because."} for i in range(1, n + 1)]

    def test_drill_refuses_with_few_notes(self):
        for n in "CDE":
            (self.vault / "techniques" / f"{n}.md").unlink()
        r = self.pr("drill")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("a drill needs at least 4 technique notes; /techniques backfill makes them", r.stderr)

    def test_drill_prints_slots(self):
        r = self.pr("drill", "--n", "8")
        out = r.stdout
        self.assertRegex(out, r"DRILL: " + date.today().isoformat() + "-1")
        self.assertEqual(len(re.findall(r"^SLOT \d+: ", out, re.M)), 8)
        self.assertIn("  trick: Trick of ", out)
        self.assertIn("  cues: cue of ", out)
        self.assertIn("my cue for ", out)
        self.assertIn("  wrong options: ", out)
        self.assertIn("PROBLEMS: practice/.drills/" + date.today().isoformat() + "-1.problems.json", out)
        self.assertRegex(self.pr("drill").stdout, r"DRILL: \d{4}-\d{2}-\d{2}-2")

    def test_weighting_and_strong_floor(self):
        # plan_drill in a subprocess with the VAULT's hooks first on sys.path: importing it here would bind the
        # repo's technique.py, whose VAULT is outside the test vault
        code = ("import sys, json; sys.path.insert(0, '.claude/hooks'); import practice; "
                "print(json.dumps([[s['technique'] for s in practice.plan_drill(4, f'2026-01-01-{k}')] for k in range(300)]))")
        r = subprocess.run([sys.executable, "-c", code], cwd=self.vault, capture_output=True, text=True)
        runs = json.loads(r.stdout)
        for slots in runs:
            self.assertGreaterEqual(sum(t in ("D", "E") for t in slots), 2, slots)
        counts = Counter(t for slots in runs for t in slots)
        self.assertGreater(counts["A"], counts["C"])

    def test_wrong_options_with_more_slots_than_techniques(self):
        d = self.start_drill(8)
        for s in self.slots(d):
            self.assertEqual(len(set(s["wrong"])), 3)
            self.assertNotIn(s["technique"], s["wrong"])
            self.assertTrue(set(s["wrong"]) <= set("ABCDE"))

    def test_drill_check(self):
        d = self.start_drill(2)
        self.write_drill_problems(d, [{"slot": 1, "statement": "s", "answer": "2^(", "solution": "x"}])
        r = self.pr("drill-check", d)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("a problem for every slot: missing 2", r.stdout)
        self.assertIn("slot 1: answer: can't read", r.stdout)
        self.write_drill_problems(d, self.valid_problems(2))
        self.assertIn("🗒 drill ready: 2 problems", self.pr("drill-check", d).stdout)

    def test_results_summary_and_cards(self):
        d = self.start_drill(2)
        self.write_drill_problems(d, self.valid_problems(2))
        self.pr("drill-check", d)
        slots = self.slots(d)
        self.pr("drill-result", d, "1", "--recognised", "wrong", "--picked", slots[0]["wrong"][0], "--solved", "right")
        self.pr("drill-result", d, "2", "--recognised", "right", "--solved", "wrong")
        r = self.pr("drill-result", d, "2", "--recognised", "right", "--solved", "right")
        self.assertNotEqual(r.returncode, 0)
        out = self.pr("drill-summary", d).stdout
        self.assertIn("Recognised 1/2 · solved 1/2", out)
        self.assertIn(f"took {slots[0]['wrong'][0]} for {slots[0]['technique']}", out)
        self.pr("scan")
        by_key = {c["key"]: c for c in self.cards()}
        self.assertEqual(by_key[f"drill:{d}#1"]["prompt"], "Problem 1?")
        self.assertEqual(by_key[f"drill:{d}#1"]["techniques"], [slots[0]["technique"]])
        self.assertIn(f"drill:{d}#2", by_key)

    def test_drill_ids_never_overwrite(self):
        d1 = self.start_drill(2)
        d2 = self.start_drill(2)
        (self.vault / "practice" / ".drills" / f"{d1}.json").unlink()
        d3 = self.start_drill(2)
        self.assertNotIn(d3, (d1, d2))
        self.assertTrue(d3.endswith("-3"))

    def test_small_drills_can_hold_weak_techniques(self):
        code = ("import sys, json; sys.path.insert(0, '.claude/hooks'); import practice; "
                "print(json.dumps([[s['technique'] for s in practice.plan_drill(2, f'2026-01-01-{k}')] for k in range(100)]))")
        runs = json.loads(subprocess.run([sys.executable, "-c", code], cwd=self.vault, capture_output=True, text=True).stdout)
        self.assertTrue(any(t in ("A", "B", "C") for slots in runs for t in slots))
        self.assertTrue(all(any(t in ("D", "E") for t in slots) for slots in runs))   # one strong of two

    def test_n_must_be_positive(self):
        r = self.pr("drill", "--n", "0")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("at least 1", r.stderr)

    def test_drill_check_undefined_answer_and_unknown_slot(self):
        d = self.start_drill(2)
        probs = self.valid_problems(2)
        probs[0]["answer"] = "1/0"
        probs.append({"slot": 9, "statement": "x", "answer": "1", "solution": "y"})
        self.write_drill_problems(d, probs)
        out = self.pr("drill-check", d).stdout
        self.assertIn("slot 1: answer is undefined", out)
        self.assertIn("slot 9 is not in the drill", out)

    def test_picked_must_be_an_option(self):
        d = self.start_drill(1)
        r = self.pr("drill-result", d, "1", "--recognised", "wrong", "--picked", "Nonsense", "--solved", "right")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not one of the options", r.stderr)

    def test_drill_card_links_into_practice_folder(self):
        d = self.start_drill(1)
        self.write_drill_problems(d, self.valid_problems(1))
        self.pr("drill-result", d, "1", "--recognised", "right", "--solved", "wrong")
        self.pr("scan")
        c = next(c for c in self.cards() if c["kind"] == "drill")
        self.assertEqual(c["source"], f"practice/{date.today().isoformat()}#Drill {d}")

    def test_summary_syncs_technique_notes(self):
        d = self.start_drill(1)
        self.write_drill_problems(d, self.valid_problems(1))
        slot = self.slots(d)[0]
        self.pr("drill-result", d, "1", "--recognised", "right", "--solved", "right")
        self.pr("drill-summary", d)
        note = (self.vault / "techniques" / f"{slot['technique']}.md").read_text()
        self.assertIn("**Drills:** recognised 1/1 · solved 1/1", note)

    def test_practice_notes_do_not_feed_technique_records(self):
        (self.vault / "practice" / "2026-10-24.md").write_text(
            "### Drill x\n\n> [!failure|quiz]- ✗ Q\n> Technique: [[A]]\n\n*Techniques: [[A]]*\n")
        run(self.vault, "technique.py", "sync")
        self.assertNotIn("2026-10-24#Drill x", (self.vault / "techniques" / "A.md").read_text())

    def test_drill_result_unknown_drill(self):
        r = self.pr("drill-result", "2020-01-01-1", "1", "--recognised", "right", "--solved", "right")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no drill 2020-01-01-1", r.stderr)


if __name__ == "__main__":
    unittest.main()
