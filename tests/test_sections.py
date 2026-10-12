import json
import shutil
import tempfile
import unittest
from pathlib import Path

import tests._vault  # noqa: F401  (puts hooks/ on the path)
import md_log
import sections

CH01 = """## Session — 2026-10-05 (Mon) 12:42

### Overview

- **§1.1 What is machine learning?** Mitchell's definition.

### 1.1 What is machine learning?

*Book: §1.1, p. 1.*

Text.

### 1.2.1 Classification: the setup and a first classifier

*Book: §1.2 opening and §1.2.1.1–1.2.1.3, pp. 1–6.*
"""


class Process(unittest.TestCase):
    def setUp(self):
        self.course = Path(tempfile.mkdtemp(prefix="sections-"))
        self.addCleanup(shutil.rmtree, self.course, True)
        (self.course / ".course").mkdir()
        (self.course / ".course" / "book.json").write_text("{}")
        (self.course / ".course" / "state.json").write_text(json.dumps({"slug": "pml1"}))
        (self.course / "pml1-ch01.md").write_text(CH01)
        (self.course / "pml1.md").write_text("### 1 Introduction\n\n### 2 Probability\n")
        self.ch01 = str(self.course / "pml1-ch01.md")
        self.ch02 = str(self.course / "pml1-ch02.md")

    def test_same_note(self):
        out = sections.process("In §1.1, $E$ was fixed.", self.ch01, existing=CH01)
        self.assertEqual(out, "In [[#1.1 What is machine learning?|§1.1]], $E$ was fixed.")

    def test_other_chapter_note(self):
        out = sections.process("Recall (§1.1).", self.ch02, existing="")
        self.assertEqual(out, "Recall ([[pml1-ch01#1.1 What is machine learning?|§1.1]]).")

    def test_containing_heading_then_first_inside(self):
        out = sections.process("See §1.2.1.5 and §1.2.", self.ch01, existing=CH01)
        target = "#1.2.1 Classification the setup and a first classifier"
        self.assertEqual(out, f"See [[{target}|§1.2.1.5]] and [[{target}|§1.2]].")

    def test_untaught_section_stays_plain(self):
        for text in ("Later, in §5.1.", "§1.2.2 is next.", "Chapter §2.7."):
            self.assertEqual(sections.process(text, self.ch02, existing=""), text)  # pml1.md's "### 2" is no target

    def test_left_alone(self):
        text = "\n".join(["### 1.3 Unlike §1.1", "*Book: §1.1, p. 1.*", "`§1.1`", "$§1.1$",
                          "[[pml1-ch01#1.1 What is machine learning?|§1.1]]", "```", "§1.1", "```"])
        self.assertEqual(sections.process(text, self.ch01, existing=CH01), text)

    def test_heading_in_the_same_block(self):
        text = "### 1.2.2 Regression\n\nUnlike §1.2.2's neighbour, §1.2.1."
        out = sections.process(text, self.ch01, existing=CH01)
        self.assertIn("[[#1.2.2 Regression|§1.2.2]]", out)

    def test_table_row_escapes_the_pipe(self):
        out = sections.process("| §1.1 | yes |", self.ch01, existing=CH01)
        self.assertEqual(out, "| [[#1.1 What is machine learning?\\|§1.1]] | yes |")

    def test_quiz_matching_reads_link_labels(self):
        self.assertEqual(md_log._norm("In [[#1.1 What is machine learning?|§1.1]], why?"), "in §1.1, why?")


if __name__ == "__main__":
    unittest.main()
