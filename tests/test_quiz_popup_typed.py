import sys
import unittest

from tests._vault import REPO

sys.path.insert(0, str(REPO / "mcp"))
import quiz_popup  # noqa: E402

SPEC = {"mode": "typed", "answer": "2^(n+1)-2", "variables": {"n": "int 1..12"}, "exact": False}


class TypedStatus(unittest.TestCase):
    def test_typed_status(self):
        self.assertEqual(quiz_popup.typed_status("2^(n+1)-2", SPEC), (True, "reads as: 2ⁿ⁺¹ − 2"))
        self.assertEqual(quiz_popup.typed_status("(1+2", SPEC), (False, "can't read: unclosed bracket"))
        self.assertEqual(quiz_popup.typed_status("0.5", {**SPEC, "exact": True}), (False, "give the exact form, not a decimal"))
        self.assertEqual(quiz_popup.typed_status("  ", SPEC), (False, ""))


if __name__ == "__main__":
    unittest.main()
