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


if __name__ == "__main__":
    unittest.main()
