import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests._vault import REPO
import tests._vault  # noqa: F401  (puts hooks/ on the path)
import coding_runner
from tests import _code_fixtures as fx

RUNNER = REPO / "hooks" / "coding_runner.py"


class Runner(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="code-runner-"))
        self.addCleanup(shutil.rmtree, self.d, True)
        self.tests = self.d / "tests.py"
        self.tests.write_text(fx.TESTS)

    def run_case(self, case, solution=None, *extra, tests=None, timeout=30):
        args = [sys.executable, str(RUNNER), str(tests or self.tests), case]
        if solution is not None:
            sol = self.d / "solution.py"
            sol.write_text(solution)
            args += ["--solution", str(sol)]
        args += list(extra)
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        return json.loads(lines[-1]) if lines else None, proc

    def test_count(self):
        out = subprocess.run([sys.executable, str(RUNNER), str(self.tests), "--count"],
                             capture_output=True, text=True).stdout
        self.assertEqual(json.loads(out), {"function": "running_max", "cases": 3, "large": 1})

    def test_pass(self):
        r, _ = self.run_case("case:0", fx.GOOD)
        self.assertTrue(r["passed"])
        self.assertIsNone(r["error"])
        self.assertGreaterEqual(r["seconds"], 0)
        self.assertEqual(r["name"], "example")

    def test_wrong_answer(self):
        r, _ = self.run_case("case:0", fx.WRONG)
        self.assertFalse(r["passed"])
        self.assertEqual(r["got"], "[3, 1, 4, 1, 5]")
        self.assertEqual(r["expected"], "[3, 3, 4, 4, 5]")

    def test_exception_traceback_trimmed(self):
        r, _ = self.run_case("case:1", fx.RAISES)
        self.assertFalse(r["passed"])
        self.assertTrue(r["error"].startswith("IndexError:"))
        self.assertIn("solution.py", r["error"])
        self.assertNotIn("coding_runner.py", r["error"])

    def test_cpu_limit(self):
        start = time.monotonic()
        r, proc = self.run_case("case:0", fx.LOOPS, "--cpu", "1", timeout=10)
        self.assertLess(time.monotonic() - start, 5)
        self.assertNotEqual(proc.returncode, 0)
        self.assertTrue(r is None or not r["passed"])

    def test_stdout_captured(self):
        r, _ = self.run_case("case:0", fx.PRINTS)
        self.assertTrue(r["passed"])
        self.assertEqual(len(r["stdout"].splitlines()), 20)

    def test_float_tolerance(self):
        self.assertTrue(coding_runner.compare([0.1 + 0.2], [0.3]))
        self.assertTrue(coding_runner.compare({"a": (1.0, 2.0)}, {"a": (1.0, 2.0 + 1e-12)}))
        self.assertFalse(coding_runner.compare([1.0], [1.1]))
        self.assertFalse(coding_runner.compare([1, 2], (1, 2)))

    def test_custom_check(self):
        tests = self.d / "perm.py"
        tests.write_text(fx.TESTS + "\n\ndef check(got, expected, args):\n    return sorted(got) == sorted(expected)\n")
        r, _ = self.run_case("case:0", "def running_max(xs):\n    return [5, 4, 4, 3, 3]\n", tests=tests)
        self.assertTrue(r["passed"])

    def test_mutation_does_not_leak(self):
        r, _ = self.run_case("case:0", fx.MUTATES)
        self.assertTrue(r["passed"])

    def test_reference_and_slow_impls(self):
        ref, _ = self.run_case("large:0", None, "--impl", "reference")
        slow, _ = self.run_case("large:0", None, "--impl", "slow")
        self.assertTrue(ref["passed"])
        self.assertTrue(slow["passed"])
        self.assertGreater(slow["seconds"], 10 * ref["seconds"])

    def test_unprintable_value(self):
        r, _ = self.run_case("case:0", fx.UNPRINTABLE)
        self.assertFalse(r["passed"])
        self.assertEqual(r["got"], "<unprintable>")

    def test_broken_solution(self):
        r, _ = self.run_case("case:0", fx.SYNTAX_ERROR)
        self.assertFalse(r["passed"])
        self.assertTrue(r["error"].startswith("SyntaxError:"))
        r, _ = self.run_case("case:0", fx.WRONG_NAME)
        self.assertFalse(r["passed"])
        self.assertIn("running_max", r["error"])


if __name__ == "__main__":
    unittest.main()
