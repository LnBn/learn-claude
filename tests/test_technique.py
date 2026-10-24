import json
import time
import unittest

from tests._vault import make_course, make_vault, run
import technique  # noqa: E402  (the repo copy, for the marker constants only)

CH02 = """## Session — 2026-10-07 (Wed) 12:32

### 2.4.1 Coin piles

Text.

> [!success|quiz]- ✓ Check question
> body

> [!failure|quiz]- ✗ Apply question
> body

*Techniques: [[Symmetry]]*

### 2.4.2 Wise men

> [!note|quiz]- Asked first: Q?
> body

> [!success|quiz]- ✓ Q?
> body

*Techniques: [[symmetry argument|by symmetry]] · [[Pigeonhole]]*

## Session — 2026-10-09 (Fri) 10:00

### 2.6.1 Handshakes

*Techniques: [[Pigeonhole principle]]*
*Techniques: [[Symmetry]]*
"""


class TechniqueBase(unittest.TestCase):
    def setUp(self):
        self.vault = make_vault(self)
        self.cdir = make_course(self.vault, "gb")
        (self.cdir / "gb-ch02.md").write_text(CH02, encoding="utf-8")

    def tq(self, *args):
        return run(self.vault, "technique.py", *args)

    def tech(self, name, aliases=(), body=""):
        p = self.vault / "techniques" / f"{name}.md"
        p.parent.mkdir(exist_ok=True)
        fm = f"---\ntechnique: {name}\naliases: [{', '.join(aliases)}]\n---\n"
        p.write_text(f"{fm}# {name}\n\n## Reach for it when\n\n- a cue\n\n{body}", encoding="utf-8")
        return p

    def read(self, name):
        return (self.vault / "techniques" / f"{name}.md").read_text(encoding="utf-8")


class Sync(TechniqueBase):
    def test_sync_writes_problem_blocks(self):
        self.tech("Symmetry", aliases=["symmetry argument"])
        self.tech("Pigeonhole principle", aliases=["pigeonhole"])
        r = self.tq("sync")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("🗒 techniques: 2 notes, 3 tagged problems, 0 unknown", r.stdout)
        sym = self.read("Symmetry")
        self.assertIn(technique.START, sym)
        self.assertIn(technique.END, sym)
        self.assertIn("**Record:** 2 ✓ · 1 ✗ — 3 problems", sym)
        self.assertIn("- [[gb-ch02#2.4.1 Coin piles|§2.4.1 Coin piles]] (gb) ✓✗", sym)
        self.assertIn("- [[gb-ch02#2.4.2 Wise men|§2.4.2 Wise men]] (gb) ✓\n", sym)
        self.assertIn("- [[gb-ch02#2.6.1 Handshakes|§2.6.1 Handshakes]] (gb)", sym)
        pig = self.read("Pigeonhole principle")
        self.assertIn("**Record:** 1 ✓ · 0 ✗ — 2 problems", pig)

    def test_edits_outside_block_survive(self):
        self.tech("Symmetry", body="## Traps\n\n- my own trap\n")
        self.tq("sync")
        p = self.vault / "techniques" / "Symmetry.md"
        before = p.read_text().split(technique.START)[0]
        p.write_text(p.read_text().replace("my own trap", "my edited trap"))
        self.tq("sync")
        after = p.read_text()
        self.assertEqual(after.split(technique.START)[0], before.replace("my own trap", "my edited trap"))
        self.assertEqual(after.count(technique.START), 1)
        self.assertEqual(after.count("## Problems"), 1)

    def test_unchanged_files_not_written(self):
        self.tech("Symmetry")
        self.tq("sync")
        p = self.vault / "techniques" / "Symmetry.md"
        idx = self.vault / "techniques" / "Techniques.md"
        m, mi = p.stat().st_mtime_ns, idx.stat().st_mtime_ns
        time.sleep(0.02)
        self.tq("sync")
        self.assertEqual(p.stat().st_mtime_ns, m)
        self.assertEqual(idx.stat().st_mtime_ns, mi)

    def test_unknown_then_resolved(self):
        self.tech("Symmetry", aliases=["symmetry argument"])
        self.assertIn("2 unknown", self.tq("sync").stdout)
        idx = (self.vault / "techniques" / "Techniques.md").read_text()
        self.assertIn("**Unknown techniques:** [[Pigeonhole]] in [[gb-ch02#2.4.2 Wise men|§2.4.2]]", idx)
        self.assertIn("[[Pigeonhole principle]] in [[gb-ch02#2.6.1 Handshakes|§2.6.1]]", idx)
        self.tech("Pigeonhole principle", aliases=["pigeonhole"])
        self.assertIn("0 unknown", self.tq("sync").stdout)
        self.assertNotIn("Unknown techniques", (self.vault / "techniques" / "Techniques.md").read_text())

    def test_index_order_counts_last_seen(self):
        self.tech("Symmetry", aliases=["symmetry argument"])
        self.tech("Pigeonhole principle", aliases=["pigeonhole"])
        self.tech("Induction")
        self.tq("sync")
        idx = (self.vault / "techniques" / "Techniques.md").read_text()
        rows = [ln for ln in idx.splitlines() if ln.startswith("| [[")]
        self.assertEqual(rows, ["| [[Symmetry]] | 3 | 2 | 1 | 2026-10-09 |",
                                "| [[Pigeonhole principle]] | 2 | 1 | 0 | 2026-10-09 |",
                                "| [[Induction]] | 0 | 0 | 0 | — |"])
        self.assertNotIn("[[Techniques]]", idx)

    def test_interview_problems(self):
        self.tech("Symmetry")
        d = self.cdir / ".interviews"
        d.mkdir()
        for n, status in [(1, "finished"), (2, "abandoned")]:
            (d / f"gb-interview-{n}.state.json").write_text(json.dumps({
                "status": status, "set": "2026-10-20", "length": "short", "number": n,
                "problems": [{"id": "p1", "outcome": "solved"}, {"id": "p2", "outcome": "not reached"}]}))
            (d / f"gb-interview-{n}.json").write_text(json.dumps({"problems": [
                {"id": "p1", "techniques": ["Symmetry"], "technique": "t"},
                {"id": "p2", "techniques": ["Symmetry"], "technique": "t"}]}))
        self.tq("sync")
        sym = self.read("Symmetry")
        self.assertIn("- [[gb-interview-1#Problem 1|gb interview 1, problem 1]] — solved", sym)
        self.assertNotIn("problem 2", sym)
        self.assertNotIn("gb-interview-2", sym)
        self.assertIn("**Record:** 2 ✓ · 1 ✗ — 3 problems", sym)  # 2.4.1 ✓✗, 2.6.1 —, interview solved

    def test_excluded_notes(self):
        self.tech("Symmetry")
        for rel in ["courses/gb/gb-review.md", "courses/gb/exams/x.md", "courses/gb/interviews/y.md",
                    "techniques/Other.md", ".obsidian/z.md"]:
            p = self.vault / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("### 1 A\n\n*Techniques: [[Symmetry]]*\n")
        self.tq("sync")
        self.assertIn("2 problems", self.read("Symmetry"))  # 2.4.1 and 2.6.1; the alias is not declared

    def test_lesson_outside_a_course(self):
        self.tech("Symmetry")
        p = self.vault / "lessons" / "puzzles.md"
        p.parent.mkdir()
        p.write_text("### Two envelopes\n\n*Techniques: [[Symmetry]]*\n")
        self.tq("sync")
        self.assertIn("- [[puzzles#Two envelopes|Two envelopes]] (lesson)", self.read("Symmetry"))

    def test_note_without_markers_gets_block(self):
        p = self.vault / "techniques" / "Symmetry.md"
        p.parent.mkdir()
        p.write_text("# Symmetry\n\nMine.\n")
        self.tq("sync")
        t = p.read_text()
        self.assertTrue(t.startswith("# Symmetry\n\nMine.\n"))
        self.assertIn("## Problems\n\n" + technique.START, t)

    def test_list(self):
        self.tech("Symmetry", aliases=["symmetry argument"])
        out = self.tq("list").stdout
        self.assertIn("Symmetry (aliases: symmetry argument) — 3 problems, 2 ✓ 1 ✗", out)
        self.assertIn("UNKNOWN: Pigeonhole", out)

    def test_no_techniques_folder(self):
        r = self.tq("sync")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("0 notes", r.stdout)


if __name__ == "__main__":
    unittest.main()
