import sys
import unittest

from tests._vault import REPO

sys.path.insert(0, str(REPO / "mcp"))
from answer_check import (AnswerError, check, defined_points, display, matches_wrong,  # noqa: E402
                          parse_ranges, points, read)

N = {"n": "int 1..12"}
NP = {"n": "int 1..12", "p": "0..1"}


class Reading(unittest.TestCase):
    def test_equal_formulas_written_differently(self):
        for g in ["2^(n+1)-2", "2*2^n-2", "2(2^n-1)", "2**(n+1) - 2", " 2 ( 2^n - 1 ) "]:
            self.assertEqual(check(g, "2^(n+1)-2", N), "correct", g)

    def test_implicit_multiplication(self):
        self.assertEqual(check("np", "n*p", NP), "correct")
        self.assertEqual(check("(n+1)(n+2)", "n^2+3n+2", N), "correct")
        self.assertEqual(check("3pi", "3*pi", {}), "correct")

    def test_functions_constants_unicode(self):
        for g, x, v in [("√2/2", "sqrt(2)/2", {}), ("π/4", "pi/4", {}), ("e^-1", "exp(-1)", {}),
                        ("C(5,2)", "10", {}), ("binom(n,2)", "n(n-1)/2", N), ("(2n)!/(n!)^2", "binom(2n,n)", N),
                        ("3 × 4 − 2", "10", {}), ("2·3", "6", {}), ("ln(e)", "1", {}), ("log(e)", "1", {}),
                        ("log2(8)", "3", {}), ("log10(1000)", "3", {}), ("abs(-2)", "2", {}),
                        ("√(n+1)", "sqrt(n+1)", N), ("∞", "inf", {}), ("−1/3", "-1/3", {})]:
            self.assertEqual(check(g, x, v), "correct", g)

    def test_pi_wins_over_variables_p_and_i(self):
        self.assertEqual(check("pi", "3.14159265358979", {"p": "0..1", "i": "0..1"}), "correct")

    def test_unknown_name(self):
        with self.assertRaisesRegex(AnswerError, "^unknown name: m — this question's variables are n$"):
            check("m+1", "n+1", N)
        with self.assertRaisesRegex(AnswerError, "^unknown name: m$"):
            check("m", "1", {})

    def test_error_messages(self):
        with self.assertRaisesRegex(AnswerError, "^can't read: unclosed bracket$"):
            read("(1+2", {})
        with self.assertRaisesRegex(AnswerError, "^can't read: nothing after \\^$"):
            read("2^", {})

    def test_refused_syntax(self):
        for bad in ["__import__('os')", "n.real", "[1]", "lambda: 1", "1 if 1 else 2", "a=1", "2,3", "'x'"]:
            with self.assertRaises(AnswerError, msg=bad):
                read(bad, N)

    def test_ranges(self):
        self.assertEqual(parse_ranges({"n": "int 1..12", "p": "0..1"}), {"n": ("int", 1, 12), "p": ("real", 0, 1)})
        for bad in [{"n": "int 5..1"}, {"p": "1..1"}, {"p": "zero..1"}, {"e": "0..1"}, {"pi": "0..1"}, {"C": "int 1..3"}]:
            with self.assertRaises(AnswerError, msg=str(bad)):
                parse_ranges(bad)


class Comparing(unittest.TestCase):
    def test_formula_agreeing_at_one_point_is_wrong(self):
        self.assertEqual(check("n^2", "2n", N), "wrong")

    def test_points(self):
        ps = points("2^n", NP)
        self.assertEqual(len(ps), 6)
        self.assertTrue(all(float(p["n"]).is_integer() and 1 <= p["n"] <= 12 and 0 < p["p"] < 1 for p in ps))
        self.assertEqual(ps, points("2^n", NP))
        self.assertEqual(points("1/3", {}), [{}])

    def test_undefined_points(self):
        self.assertEqual(check("1/(n-3)", "1/(n-3)", {"n": "int 1..6"}), "correct")
        self.assertEqual(check("1/(n-n)", "1", N), "wrong")
        self.assertEqual(defined_points("1/(n-n)", N), 0)

    def test_no_hang_no_crash(self):
        for g in ["9^9^9", "1000!", "(-8)^(1/3)", "ln(-1)", "1/0"]:
            self.assertEqual(check(g, "1", {}), "wrong", g)

    def test_decimal_rule(self):
        for g, x, want in [("0.333", "1/3", "correct"), ("0.3333", "1/3", "correct"), ("0.33", "1/3", "wrong"),
                           ("0.334", "1/3", "wrong"), ("-0.333", "-1/3", "correct"), ("33.3", "100/3", "correct"),
                           ("33.4", "100/3", "wrong"), ("0.0004", "0", "correct"), ("0.0006", "0", "wrong"),
                           ("0.5n", "n/2", "correct")]:
            self.assertEqual(check(g, x, N if "n" in x else {}), want, g)

    def test_exact_form(self):
        self.assertEqual(check("333/1000", "1/3", {}), "wrong")
        self.assertEqual(check("1/2", "1/2", {}, exact=True), "correct")
        with self.assertRaisesRegex(AnswerError, "^give the exact form, not a decimal$"):
            check("0.5", "1/2", {}, exact=True)

    def test_infinity(self):
        self.assertEqual(check("inf", "inf", {}), "correct")
        self.assertEqual(check("-inf", "inf", {}), "wrong")
        self.assertEqual(check("1000000", "inf", {}), "wrong")

    def test_matches_wrong(self):
        wrong = [{"answer": "2^n", "why": "a"}, {"answer": "2^(n+1)", "why": "b"}]
        self.assertEqual(matches_wrong("2*2^(n-1)", wrong, N), 0)
        self.assertEqual(matches_wrong("2(2^n)", wrong, N), 1)
        self.assertIsNone(matches_wrong("2^(n+1)-2", wrong, N))


class Showing(unittest.TestCase):
    def test_display(self):
        self.assertEqual(display("2^(n+1)-2", N), "2ⁿ⁺¹ − 2")
        self.assertEqual(display("sqrt(2)/2", {}), "√2/2")
        self.assertEqual(display("binom(n,2)", N), "C(n, 2)")
        self.assertEqual(display("2^(n/2)", N), "2^(n/2)")


if __name__ == "__main__":
    unittest.main()
