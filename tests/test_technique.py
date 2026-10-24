import json
import time
import unittest

from tests._vault import append, assistant, hook, make_course, make_vault, run, transcript, user
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



class Commands(TechniqueBase):
    def test_cue_appends_under_in_your_words(self):
        self.tech("Symmetry", aliases=["symmetry argument"],
                  body="**In your words:**\n- \"old\" — [[gb-ch02#2.4.1 Coin piles|§2.4.1]], 2026-10-01\n\n## Traps\n")
        r = self.tq("cue", "symmetry argument", "Two piles that could be swapped", "--source", "gb-ch02#2.4.2 Wise men")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(self.read("Symmetry"),
                         r'- "old" — .*\n- "Two piles that could be swapped" — \[\[gb-ch02#2.4.2 Wise men\|§2.4.2\]\], '
                         r'\d{4}-\d{2}-\d{2}\n\n## Traps')

    def test_cue_creates_the_line(self):
        self.tech("Symmetry")
        self.tq("cue", "Symmetry", "x", "--source", "gb-ch02#2.4.1 Coin piles")
        self.assertIn('- a cue\n\n**In your words:**\n- "x" — [[gb-ch02#2.4.1 Coin piles|§2.4.1]], ', self.read("Symmetry"))

    def test_cue_refuses_unknown(self):
        r = self.tq("cue", "Nope", "x", "--source", "a#b")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no technique note", r.stderr)

    def test_sections(self):
        note = self.cdir / "gb-ch02.md"
        note.write_text(note.read_text().replace("Text.\n", "Text.\n\n> [!summary] Key idea\n> Swap the piles.\n", 1))
        out = self.tq("sections", "courses/gb/gb-ch02.md").stdout
        self.assertIn("### 2.4.1 Coin piles\n  key idea: Swap the piles.\n  tags: Symmetry", out)
        self.assertIn("### 2.4.2 Wise men\n  tags: symmetry argument, Pigeonhole", out)

    def test_tag_places_line_before_session_header(self):
        self.tech("Symmetry")
        note = self.cdir / "gb-ch02.md"
        note.write_text(note.read_text().replace("*Techniques: [[symmetry argument|by symmetry]] · [[Pigeonhole]]*\n", ""))
        r = self.tq("tag", "courses/gb/gb-ch02.md", "2.4.2 Wise men", "Symmetry")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("> body\n\n*Techniques: [[Symmetry]]*\n\n## Session — 2026-10-09", note.read_text())

    def test_tag_merges_into_existing_line(self):
        self.tech("Symmetry")
        self.tech("Linearity of expectation")
        self.tq("tag", "courses/gb/gb-ch02.md", "2.4.1 Coin piles", "Linearity of expectation", "Symmetry")
        t = (self.cdir / "gb-ch02.md").read_text()
        self.assertIn("*Techniques: [[Symmetry]] · [[Linearity of expectation]]*", t)
        self.assertEqual(t.count("*Techniques:"), 4)

    def test_tag_writes_canonical_names_at_note_end_and_syncs(self):
        self.tech("Symmetry", aliases=["by symmetry"])
        note = self.cdir / "gb-ch02.md"
        note.write_text(note.read_text() + "\n### 2.6.2 Have we met before?\n\nText.\n")
        self.tq("tag", "courses/gb/gb-ch02.md", "2.6.2 Have we met before?", "by symmetry")
        self.assertTrue(note.read_text().endswith("Text.\n\n*Techniques: [[Symmetry]]*\n"))
        self.assertIn("§2.6.2 Have we met before", self.read("Symmetry"))

    def test_tag_unknown_section(self):
        self.tech("Symmetry")
        r = self.tq("tag", "courses/gb/gb-ch02.md", "9.9 Nothing", "Symmetry")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no section", r.stderr)



class Mirror(TechniqueBase):
    def mirror(self, note, text, s="sess-t"):
        tp = transcript(self.vault, s)
        r = run(self.vault, "md_log.py", "link", str(note), "--session", s, "--from-now", "--no-header")
        self.assertEqual(r.returncode, 0, r.stderr)
        append(tp, user("ready"), assistant("m1", text=text))
        return hook(self.vault, {"hook_event_name": "Stop", "session_id": s, "transcript_path": str(tp)})

    def test_mirror_syncs_after_a_tag_line(self):
        self.tech("Symmetry")
        note = self.cdir / "gb-ch03.md"
        note.write_text("### 3.1 New\n\nText.\n")
        self.mirror(note, "Both passed.\n\n*Techniques: [[Symmetry]]*")
        self.assertIn("*Techniques: [[Symmetry]]*", note.read_text())
        self.assertIn("[[gb-ch03#3.1 New|§3.1 New]]", self.read("Symmetry"))

    def test_mirror_without_techniques_folder(self):
        note = self.vault / "lessons" / "a.md"
        note.parent.mkdir()
        note.write_text("### A\n\nText.\n")
        r = self.mirror(note, "Done.\n\n*Techniques: [[Symmetry]]*")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("*Techniques: [[Symmetry]]*", note.read_text())
        idx = (self.vault / "techniques" / "Techniques.md").read_text()
        self.assertIn("**Unknown techniques:** [[Symmetry]] in ", idx)
        self.assertIn(", [[a#A|A]];", idx)

    def test_mirror_without_a_tag_line_does_not_sync(self):
        note = self.cdir / "gb-ch03.md"
        note.write_text("### 3.1 New\n\nText.\n")
        self.mirror(note, "No tags here.")
        self.assertFalse((self.vault / "techniques").exists())


if __name__ == "__main__":
    unittest.main()
