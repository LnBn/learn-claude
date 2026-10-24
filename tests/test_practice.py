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

    def test_stats(self):
        self.pr("scan")
        self.assertRegex(self.pr("stats").stdout, r"active 5 · retired 0 · due today 0\nnext 7 days: (\d+ ){6}\d+")



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

    def test_drill_result_unknown_drill(self):
        r = self.pr("drill-result", "2020-01-01-1", "1", "--recognised", "right", "--solved", "right")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no drill 2020-01-01-1", r.stderr)


if __name__ == "__main__":
    unittest.main()
