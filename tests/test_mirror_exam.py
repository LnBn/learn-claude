import unittest

from tests._vault import append, assistant, hook, make_vault, run, tool_result, transcript, user

import md_log

GRADED_PAPER = """---
exam: pml1-ch02
status: graded
---
# Exam — Chapter 2

### Q7 (4 marks)
State Bayes' rule.

**Answer:**
p(h|D) = p(D|h) p(h) / p(D), where p(D) is the prior.

> [!warning] Q7 — 3/4
> The marginal likelihood is called the prior.
^q7

### Q8 (4 marks)
What is a likelihood?

**Answer:**
p(D|h).
"""


class CommandOf(unittest.TestCase):
    def test_typed_forms(self):
        self.assertEqual(md_log.command_of("submit"), ("exam", "submit"))
        self.assertEqual(md_log.command_of("Submit."), ("exam", "submit"))
        self.assertEqual(md_log.command_of("exam"), ("exam", ""))
        self.assertEqual(md_log.command_of("exam 2"), ("exam", "2"))
        self.assertEqual(md_log.command_of("exam submit"), ("exam", "submit"))
        self.assertIsNone(md_log.command_of("exam questions are hard"))
        self.assertIsNone(md_log.command_of("submit it later?"))

    def test_slash_form(self):
        self.assertEqual(md_log.command_of("<command-name>/exam</command-name><command-args>submit</command-args>"),
                         ("exam", "submit"))

    def test_muted(self):
        for c in [("exam", ""), ("exam", "submit"), ("exam", "2")]:
            self.assertTrue(md_log.is_admin_command(c))


class MutedLink(unittest.TestCase):
    def test_grading_reply_muted_and_followup_becomes_aside(self):
        vault = make_vault(self)
        paper = vault / "courses" / "pml1" / "exams" / "pml1-ch02-exam-1.md"
        paper.parent.mkdir(parents=True)
        paper.write_text(GRADED_PAPER, encoding="utf-8")
        s = "sess-1"
        tp = transcript(vault, s)

        append(tp, user("<command-name>/exam</command-name><command-args>submit</command-args>"),
               assistant("m1", tool="Bash"), tool_result("tu-m1"))
        r = run(vault, "md_log.py", "link", str(paper), "--session", s, "--from-now", "--muted", "--no-header")
        self.assertEqual(r.returncode, 0, r.stderr)
        append(tp, assistant("m2", tool="Bash"), tool_result("tu-m2"),
               assistant("m3", text="Score 31/40. Revisit §2.3."))
        hook(vault, {"hook_event_name": "Stop", "session_id": s, "transcript_path": str(tp)})

        q = "why did I lose a mark on Q7?"
        hook(vault, {"hook_event_name": "UserPromptSubmit", "session_id": s, "transcript_path": str(tp), "prompt": q})
        append(tp, user(q), assistant("m4", text="%% aside: q7 %%\nThe evidence is $p(\\mathcal{D})$, not the prior."))
        hook(vault, {"hook_event_name": "Stop", "session_id": s, "transcript_path": str(tp)})

        text = paper.read_text(encoding="utf-8")
        self.assertNotIn("Score 31/40", text)
        self.assertIn("> [!aside]+ why did I lose a mark on Q7?", text)
        at = text.index("> [!aside]+")
        self.assertGreater(at, text.index("^q7"))
        self.assertLess(at, text.index("### Q8"))
        self.assertNotIn("%% aside", text)
        self.assertNotIn("## Session", text)


if __name__ == "__main__":
    unittest.main()
