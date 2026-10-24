import json
import os
import random
import stat
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from tests._vault import make_vault, run
import arith  # noqa: E402  (the repo copy: pure functions only, nothing that touches a vault)


def qs(mode, n=2000, seed=1):
    rng = random.Random(seed)
    return [arith.generate(mode, rng) for _ in range(n)]


class Questions(unittest.TestCase):
    def test_core_ranges_and_reversals(self):
        for q in qs("core"):
            a, op, b = q["text"].split(" ")
            a, b, ans = int(a), int(b), int(q["answer"])
            if op == "+":
                self.assertTrue(2 <= a <= 100 and 2 <= b <= 100 and ans == a + b, q)
            elif op == "−":
                self.assertTrue(2 <= ans <= 100 and a - b == ans and 2 <= b <= 100, q)
            elif op == "×":
                self.assertTrue(2 <= a <= 12 and 2 <= b <= 100 and ans == a * b, q)
            else:
                self.assertTrue(op == "÷" and 2 <= b <= 12 and a == b * ans and 2 <= ans <= 100, q)
        self.assertEqual({q["text"].split(" ")[1] for q in qs("core")}, {"+", "−", "×", "÷"})

    def test_core_kinds(self):
        for q in qs("core", 500):
            a, op, b = q["text"].split(" ")
            if op == "+":
                carry = int(a) % 10 + int(b) % 10 >= 10
                self.assertEqual(q["kind"], "+ carry" if carry else "+ no carry")
            elif op == "−":
                self.assertEqual(q["kind"], "− borrow" if int(a) % 10 < int(b) % 10 else "− no borrow")
            elif op == "×":
                self.assertEqual(q["kind"], f"× {a}")
            else:
                self.assertEqual(q["kind"], f"÷ {b}")
        self.assertTrue({"+ carry", "+ no carry", "− borrow", "− no borrow", "× 7", "÷ 12"} <= {q["kind"] for q in qs("core")})

    def test_fractions(self):
        kinds = set()
        for q in qs("fractions"):
            kinds.add(q["kind"])
            if q["kind"].startswith("/"):
                n, d = map(int, q["text"].split("/"))
                self.assertIn(d, list(range(2, 13)) + [16, 20, 25, 40])
                self.assertTrue(1 <= n < d)
                self.assertEqual(q["answer"], f"{round(n / d, 4):.4f}".rstrip("0").rstrip("."))
                self.assertEqual(q["kind"], f"/{d}")
            else:
                self.assertRegex(q["text"], r"^\d+(\.5)?% of \d+$")
                p, y = float(q["text"].split("%")[0]), int(q["text"].split(" of ")[1])
                self.assertTrue(20 <= y <= 800 and y % 4 == 0)
                self.assertAlmostEqual(float(q["answer"]), p * y / 100)
                self.assertLessEqual(len(q["answer"].split(".")[1]) if "." in q["answer"] else 0, 1)
                self.assertEqual(q["kind"], f"{q['text'].split('%')[0]}% of")
        self.assertIn("12.5% of", kinds)

    def test_powers(self):
        self.assertEqual({q["kind"] for q in qs("powers")}, {"square 1x", "square 2x", "2^k", "cube"})
        for q in qs("powers", 300):
            expr = q["text"].replace("²", "**2").replace("³", "**3").replace("^", "**")
            self.assertEqual(int(q["answer"]), eval(expr))
            if q["kind"] == "2^k":
                self.assertTrue(5 <= int(q["text"].split("^")[1]) <= 20)
            if q["kind"] == "cube":
                self.assertTrue(2 <= int(q["text"][:-1]) <= 12)
            if q["kind"].startswith("square"):
                n = int(q["text"][:-1])
                self.assertTrue(11 <= n <= 30)
                self.assertEqual(q["kind"], "square 1x" if n < 20 else "square 2x")

    def test_estimate(self):
        for q in qs("estimate", 500):
            self.assertTrue(q["estimate"])
            self.assertIn(q["kind"], ("≈ ×", "≈ ÷"))
            a, op, b = q["text"].split(" ")
            a, b = int(a), int(b)
            if op == "×":
                self.assertTrue(12 <= a <= 999 and 12 <= b <= 999 and max(a, b) >= 100)
                self.assertAlmostEqual(float(q["answer"]), a * b)
            else:
                self.assertTrue(100 <= a <= 9999 and 3 <= b <= 99)
                self.assertAlmostEqual(float(q["answer"]), a / b, places=3)

    def test_mixed_draws_every_mode(self):
        self.assertEqual({q["mode"] for q in qs("mixed")}, {"core", "fractions", "powers", "estimate"})

    def test_accepts(self):
        q = {"answer": "0.375", "estimate": False}
        self.assertFalse(arith.accepts("0.37", q))
        self.assertTrue(arith.accepts("0.375", q))
        self.assertTrue(arith.accepts(".375", q))
        self.assertTrue(arith.accepts("0.5", {"answer": "0.5", "estimate": False}))
        self.assertTrue(arith.accepts("438", {"answer": "438", "estimate": False}))
        self.assertFalse(arith.accepts("43", {"answer": "438", "estimate": False}))
        e = {"answer": "1081", "estimate": True}
        self.assertFalse(arith.accepts("1100", e))
        self.assertTrue(arith.accepts("1100", e, enter=True))
        self.assertFalse(arith.accepts("1110", e, enter=True))
        self.assertFalse(arith.accepts("", e, enter=True))
        self.assertFalse(arith.accepts("-", q))
        self.assertFalse(arith.accepts(".", q))

    def test_no_answer_needs_typing_past_an_accepted_prefix(self):
        for q in qs("mixed", 3000):
            if not q["estimate"]:
                ans = q["answer"]
                self.assertTrue(arith.accepts(ans, q), q)
                self.assertFalse(any(arith.accepts(ans[:k], q) for k in range(1, len(ans))), q)

    def test_mode_of(self):
        self.assertEqual(arith.mode_of("× 7"), "core")
        self.assertEqual(arith.mode_of("− borrow"), "core")
        self.assertEqual(arith.mode_of("/16"), "fractions")
        self.assertEqual(arith.mode_of("12.5% of"), "fractions")
        self.assertEqual(arith.mode_of("cube"), "powers")
        self.assertEqual(arith.mode_of("≈ ÷"), "estimate")



def sprint(mode, score, complete=True, questions=(), skipped=0, seconds=120):
    return {"date": "2026-10-24", "time": "12:00", "mode": mode, "seconds": seconds, "complete": complete,
            "score": score, "skipped": skipped, "questions": [{"kind": k, "ms": ms} for k, ms in questions]}


class History(unittest.TestCase):
    def test_kind_speeds_last_50_and_ranking_floor(self):
        h = {"sprints": [sprint("core", 0, questions=[("× 7", 5000)] * 30 + [("× 7", 1000)] * 50 + [("× 2", 900)] * 9)]}
        sp = arith.kind_speeds(h)
        self.assertEqual(sp["× 7"], 1000)
        self.assertNotIn("× 2", sp)

    def test_weak_kinds_relative_within_mode(self):
        qsx = ([("× 7", 3000)] * 12 + [("× 3", 1000)] * 12 + [("+ carry", 1200)] * 12
               + [("/16", 4000)] * 12 + [("/2", 3800)] * 12 + [("/4", 3900)] * 12)
        w = arith.weak_kinds({"sprints": [sprint("mixed", 0, questions=qsx)]})
        self.assertEqual(w[0], "× 7")
        self.assertLessEqual(len(w), 5)

    def test_weak_generation_share(self):
        h = {"sprints": [sprint("mixed", 0, questions=[("× 7", 3000)] * 12 + [("× 3", 1000)] * 12
                                + [("+ carry", 1000)] * 12)]}
        rng = random.Random(3)
        w = arith.weak_kinds(h)
        share = sum(arith.generate("weak", rng, w)["kind"] in w for _ in range(2000)) / 2000
        self.assertTrue(0.6 < share < 0.85, share)

    def test_weak_without_history(self):
        self.assertEqual(arith.weak_kinds({"sprints": []}), [])
        arith.generate("weak", random.Random(1), [])

    def test_summary(self):
        h = {"sprints": [sprint("core", s) for s in (30, 41, 35, 36, 37, 38)] + [sprint("core", 99, complete=False)]
             + [sprint("fractions", 60)]}
        new = sprint("core", 38, questions=[("× 7", 2400), ("− borrow", 2100), ("÷ 8", 1900), ("+ carry", 800)],
                     skipped=1)
        self.assertEqual(arith.summary(new, h), "ARITHMETIC: core · 120 s · score 38 (1 skipped)\n"
                                                 "BEST: 41 · LAST 5 AVERAGE: 37.4\n"
                                                 "SLOWEST: × 7 2.4 s · − borrow 2.1 s · ÷ 8 1.9 s")

    def test_summary_first_sprint(self):
        new = sprint("core", 20, questions=[("× 7", 2000)])
        self.assertEqual(arith.summary(new, {"sprints": []}).split("\n")[1], "BEST: — · LAST 5 AVERAGE: —")

    def test_partial_summary(self):
        s = sprint("core", 9, complete=False)
        s["stopped"] = 47
        out = arith.summary(s, {"sprints": []})
        self.assertEqual(out.split("\n")[0], "ARITHMETIC: core · stopped at 0:47 · score 9")
        self.assertNotIn("BEST", out)


class Commands(unittest.TestCase):
    def setUp(self):
        self.vault = make_vault(self)
        self.hist = self.vault / "practice" / ".arith.json"
        self.hist.parent.mkdir()

    def write(self, sprints):
        self.hist.write_text(json.dumps({"sprints": sprints}))

    def test_last_history_kinds(self):
        q = [("× 7", 2500)] * 12 + [("× 3", 900)] * 12
        self.write([sprint("core", 30, questions=q), sprint("core", 34, questions=q), sprint("fractions", 20)])
        last = run(self.vault, "arith.py", "last")
        self.assertEqual(last.returncode, 0, last.stderr)
        self.assertIn("ARITHMETIC: fractions", last.stdout)
        hist = run(self.vault, "arith.py", "history", "core").stdout
        self.assertIn("core: 30 34 · best 34 · average 32.0", hist)
        kinds = run(self.vault, "arith.py", "kinds").stdout
        self.assertLess(kinds.index("× 7"), kinds.index("× 3"))
        self.assertIn("× 7 2.5 s", kinds)

    def test_missing_and_corrupt_history(self):
        r = run(self.vault, "arith.py", "last")
        self.assertEqual(r.returncode, 0)
        self.assertIn("NO SPRINT RECORDED", r.stdout)
        self.hist.write_text("{bad")
        r = run(self.vault, "arith.py", "last")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.hist.read_text(), "{bad")



class Popup(unittest.TestCase):
    def setUp(self):
        self.vault = make_vault(self)

    def fake_tmux(self):
        d = Path(tempfile.mkdtemp(prefix="fake-tmux-"))
        log = d / "calls.log"
        hist = self.vault / "practice" / ".arith.json"
        sprint_json = json.dumps({"sprints": [sprint("core", 12, seconds=10, questions=[("× 7", 1500)])]})
        script = d / "tmux"
        script.write_text("#!/bin/sh\n"
                          f'echo "$@" >> "{log}"\n'
                          'case "$*" in *"-h 14 "*) echo "height too large" >&2; exit 1;; esac\n'
                          f'mkdir -p "{hist.parent}"\n'
                          f"printf '%s' '{sprint_json}' > \"{hist}\"\n")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        return {"PATH": f"{d}:{os.environ['PATH']}", "TMUX": "x"}, log

    def test_deadline(self):
        self.assertEqual(arith.deadline_left(100.0, 120, 150.0), 70.0)
        self.assertEqual(arith.deadline_left(100.0, 120, 900.0), 0.0)

    def test_run_outside_tmux(self):
        r = run(self.vault, "arith.py", "run", "core", env={"TMUX": ""})
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), 'NO TMUX: run "python3 .claude/hooks/arith.py play core" in another terminal, '
                                           'then /arith last')

    def test_run_retries_a_tall_popup_and_prints_the_summary(self):
        env, log = self.fake_tmux()
        r = run(self.vault, "arith.py", "run", "core", "--seconds", "10", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ARITHMETIC: core · 10 s · score 12", r.stdout)
        calls = log.read_text()
        self.assertIn("display-popup -E -w 70 -h 14 ", calls)
        self.assertIn("-h 90% ", calls)
        self.assertIn("arith.py play core --seconds 10", calls)

    def test_run_with_nothing_recorded(self):
        env, log = self.fake_tmux()
        script = Path(env["PATH"].split(":")[0]) / "tmux"
        script.write_text("#!/bin/sh\nexit 0\n")
        r = run(self.vault, "arith.py", "run", "core", env=env)
        self.assertIn("NO SPRINT RECORDED", r.stdout)


if __name__ == "__main__":
    unittest.main()
