import random
import unittest
from collections import Counter

import tests._vault  # noqa: F401  (puts hooks/ on the path)
import arith


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


if __name__ == "__main__":
    unittest.main()
