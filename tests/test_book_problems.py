"""Problem courses: the contents file's solution column, the problems of a unit, `book.py attempt`, and the misses
that review cards and technique notes pick up."""
import json
import unittest
from pathlib import Path

from tests._vault import make_vault, run

import book


def _e(id_, title, kind, level, chapter, start, end, **extra):
    return {"id": id_, "title": title, "kind": kind, "level": level, "chapter": chapter, "start": start, "end": end,
            "starred": False, "exercises": False, "mid_start": False, "mid_end": False, **extra}


# A Green Book in small: named problems under sections (slug ids), one of them in two parts, and a section that
# opens with exposition before its first problem.
GB = [
    _e("2", "Brain Teasers", "chapter", 1, "2", 19, 30),
    _e("2.2", "Logic Reasoning", "section", 2, "2", 19, 24),
    _e("2:river-crossing", "River crossing", "other", 3, "2", 19, 20),
    _e("2:defective-ball", "Defective ball", "other", 3, "2", 20, 22),
    _e("2:prisoner-problem", "Prisoner problem", "other", 3, "2", 22, 24),
    _e("2:two-hat-colors", "Two hat colors", "other", 4, "2", 22, 23),
    _e("2:three-hat-colors", "Three hat colors", "other", 4, "2", 23, 24),
    _e("2.3", "Distributions", "section", 2, "2", 25, 30),
    _e("2:meeting-probability", "Meeting probability", "other", 3, "2", 27, 30),
]

# A Mosteller in small: the problems are the units, their solutions printed apart.
FIFTY = [
    _e("1", "Problems 1–2", "chapter", 1, "1", 9, 9),
    _e("1.1", "The sock drawer", "section", 2, "1", 9, 9, sol_start=23, sol_end=25),
    _e("1.2", "Successive wins", "section", 2, "1", 9, 9, sol_start=25, sol_end=26),
    _e("solutions", "Solutions", "other", 1, None, 23, 40),
]

NOTE = """## Session — 2026-11-04 (Wed) 10:00

### 2.2.2 Defective ball
*Book: §2.2, pp. 4–6.*

**The problem.** You have 12 balls, one heavier or lighter. Find it in 3 weighings.

> [!summary] Key idea
> Count the outcomes.

*Techniques: [[Information counting]]*
"""


def make(vault: Path, slug: str, entries, syllabus, mode="problems", offset=0) -> Path:
    cdir = vault / "courses" / slug
    (cdir / ".course").mkdir(parents=True)
    bk = {"pdf": str(vault / "book.pdf"), "pages": 40, "generated_ids": False, "labels": None, "offset": offset,
          "entries": entries}
    state = {"slug": slug, "title": slug, "syllabus": syllabus, "status": {}, "exercises": {}, "mode": mode}
    (cdir / ".course" / "book.json").write_text(json.dumps(bk), encoding="utf-8")
    (cdir / ".course" / "state.json").write_text(json.dumps(state), encoding="utf-8")
    (vault / ".claude" / "md-log-state" / "course.json").write_text(json.dumps({"course": str(cdir)}))
    return cdir


def state(cdir: Path) -> dict:
    return json.loads((cdir / ".course" / "state.json").read_text(encoding="utf-8"))


class TocFile(unittest.TestCase):
    def test_solution_column_gives_solution_ranges(self):
        vault = make_vault(self)
        toc = vault / "toc.tsv"
        toc.write_text("# problems, then their solutions\n"
                       "1\t1 Problems\t1\n2\t1.1 The sock drawer\t1\t15\n2\t1.2 Successive wins\t1\t17\n"
                       "2\t1.3 The flippant juror\t2\t18\n1\tSolutions\t15\n", encoding="utf-8")
        rows = book.read_toc_file(str(toc), 8)
        self.assertEqual(rows[1][5], 23)
        b, _ = book.build_book(rows, "x.pdf", {"pages": 40, "height": None, "title": ""}, {}, 8)
        by = {e["id"]: e for e in b["entries"]}
        self.assertEqual((by["1.1"]["start"], by["1.1"]["end"]), (9, 9))   # shares its page with 1.2
        self.assertEqual((by["1.3"]["start"], by["1.3"]["end"]), (10, 22))  # stops before the solutions
        self.assertEqual((by["1.1"]["sol_start"], by["1.1"]["sol_end"]), (23, 25))
        self.assertEqual((by["1.3"]["sol_start"], by["1.3"]["sol_end"]), (26, 40))
        self.assertNotIn("sol_start", by["1"])

    def test_three_columns_still_read(self):
        vault = make_vault(self)
        toc = vault / "toc.tsv"
        toc.write_text("1\t1 Intro\t1\n2\t1.1 Start\t=12\n", encoding="utf-8")
        self.assertEqual(book.read_toc_file(str(toc), 4), [(0, "1 Intro", 5, None, "", None),
                                                           (1, "1.1 Start", 12, None, "", None)])

    def test_bad_solution_column_is_refused(self):
        vault = make_vault(self)
        toc = vault / "toc.tsv"
        toc.write_text("2\t1.1 Start\t3\tp15\n", encoding="utf-8")
        with self.assertRaises(SystemExit):
            book.read_toc_file(str(toc), 0)


class Problems(unittest.TestCase):
    def setUp(self):
        self.vault = make_vault(self)

    def test_numbers_follow_the_unit_with_letters_for_parts(self):
        c = book.Course(str(make(self.vault, "gb", GB, ["2.2", "2.3"])))
        nums = [n for n, _ in c.problems(c.by_id["2.2"])]
        self.assertEqual(nums, ["2.2.1", "2.2.2", "2.2.3a", "2.2.3b"])
        self.assertEqual(c.find_problem("2.2.3b")[2]["id"], "2:three-hat-colors")
        self.assertEqual(c.find_problem("2:defective-ball")[1], "2.2.2")

    def test_a_unit_without_entries_is_its_own_problem(self):
        c = book.Course(str(make(self.vault, "fifty", FIFTY, ["1.1", "1.2"])))
        self.assertEqual([(n, e["id"]) for n, e in c.problems(c.by_id["1.2"])], [("1.2", "1.2")])

    def test_next_names_the_problem_and_its_pages(self):
        make(self.vault, "gb", GB, ["2.2", "2.3"])
        out = run(self.vault, "book.py", "next").stdout
        self.assertIn("PROBLEM: 2.2.1 River crossing  (1 of 4 in unit 2.2)", out)
        self.assertIn("pages: 19-20", out)
        self.assertIn("SOLUTION: printed with the statement", out)
        self.assertIn("UNIT 2.2 PROBLEMS: → 2.2.1  · 2.2.2  · 2.2.3a  · 2.2.3b", out)
        self.assertNotIn("LEAD-IN", out)

    def test_solution_printed_apart(self):
        make(self.vault, "fifty", FIFTY, ["1.1", "1.2"], offset=8)
        out = run(self.vault, "book.py", "section", "1.2").stdout
        self.assertIn("pages: 9   (printed p. 1; 1 page) — the statement", out)
        self.assertIn("pages: 25-26   (printed pp. 17–18; 2 pages) — printed apart", out)
        self.assertIn("CITE AS: §1.2, p. 1; solution pp. 17–18", out)

    def test_lead_in_before_the_first_problem(self):
        make(self.vault, "gb", GB, ["2.2", "2.3"])
        out = run(self.vault, "book.py", "section", "2.3").stdout
        self.assertIn("LEAD-IN: PDF pages 25-27", out)
        self.assertIn('under "Distributions"', out)

    def test_textbook_mode_is_unchanged(self):
        make(self.vault, "gb", GB, ["2.2", "2.3"], mode="textbook")
        out = run(self.vault, "book.py", "next").stdout
        self.assertNotIn("PROBLEM:", out)
        self.assertIn("pages: 19-24", out)


class Attempts(unittest.TestCase):
    def setUp(self):
        self.vault = make_vault(self)
        self.cdir = make(self.vault, "gb", GB, ["2.2", "2.3"])

    def book(self, *args):
        r = run(self.vault, "book.py", *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def finish(self, n, result="solved", hints=0, transfer="passed"):
        for _ in range(hints):
            self.book("attempt", n, "--hint")
        self.book("attempt", n, "--result", result, *(["--miss", "recall"] if result == "unsolved" else []))
        return self.book("attempt", n, "--transfer", transfer, *(["--miss", "method"] if transfer == "missed" else []))

    def test_hint_levels(self):
        self.assertIn("hints up to level 1 so far", self.book("attempt", "2.2.1", "--hint", "1"))
        self.assertIn("hints up to level 2 so far", self.book("attempt", "2.2.1", "--hint", "2"))
        self.book("attempt", "2.2.1", "--hint", "0")
        out = self.book("attempt", "2.2.1", "--result", "solved")
        self.assertIn("solved with hints (up to level 2)", out)
        self.assertNotIn("shaky", self.book("attempt", "2.2.1", "--transfer", "passed"))
        r = state(self.cdir)["attempts"]["2:river-crossing"]
        self.assertEqual((r["outcome"], r["hints"], r["level"]), ("hinted", 3, 2))
        self.book("attempt", "2.2.2", "--hint", "3")
        self.book("attempt", "2.2.2", "--result", "solved")
        self.assertIn("— shaky", self.book("attempt", "2.2.2", "--transfer", "passed"))
        r = run(self.vault, "book.py", "attempt", "2.2.3a", "--hint", "6")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--hint takes the hint's level, 0-5", r.stderr)

    def test_kind_of_miss(self):
        r = run(self.vault, "book.py", "attempt", "2.2.1", "--result", "unsolved")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("a miss needs its kind: --miss recall|method|execution|careless|misconception", r.stderr)
        r = run(self.vault, "book.py", "attempt", "2.2.1", "--result", "solved", "--miss", "method")
        self.assertIn("--miss goes with --result unsolved or --transfer missed", r.stderr)
        self.book("attempt", "2.2.1", "--hint", "4")
        self.book("attempt", "2.2.1", "--result", "unsolved", "--miss", "method")
        self.book("attempt", "2.2.1", "--transfer", "missed", "--miss", "execution")
        r = state(self.cdir)["attempts"]["2:river-crossing"]
        self.assertEqual((r["miss"], r["transfer_miss"]), ("method", "execution"))
        self.book("attempt", "2.2.1", "--hint", "1")  # a new attempt: the old one, its level and kinds go to history
        r = state(self.cdir)["attempts"]["2:river-crossing"]
        self.assertEqual((r["history"][0]["level"], r["history"][0]["miss"], r["level"]), (4, "method", 1))
        self.assertNotIn("miss", r)

    def test_hints_are_counted_and_the_outcome_follows(self):
        self.assertIn("1 hint so far", self.book("attempt", "2.2.1", "--hint"))
        self.assertIn("2 hints so far", self.book("attempt", "2.2.1", "--hint"))
        out = self.book("attempt", "2.2.1", "--result", "solved")
        self.assertIn("solved with 2 hints", out)
        self.assertIn("RECORD: solved with 2 hints; the transfer quiz is not recorded yet", self.book("next"))
        out = self.book("attempt", "2.2.1", "--transfer", "passed")
        self.assertIn("— shaky", out)
        self.assertIn("PROBLEM: 2.2.2 Defective ball", out)
        r = state(self.cdir)["attempts"]["2:river-crossing"]
        self.assertEqual((r["outcome"], r["hints"], r["n"], r["note"]), ("hinted", 2, "2.2.1", "gb-ch02"))

    def test_the_unit_is_recorded_when_its_last_problem_is(self):
        for n in ("2.2.1", "2.2.2", "2.2.3a"):
            self.finish(n)
        self.assertNotIn("2.2", state(self.cdir)["status"])
        out = self.finish("2.2.3b")
        self.assertIn("🗒 2.2 Logic Reasoning: done", out)
        self.assertIn("PROBLEM: 2.3.1 Meeting probability", out)
        self.assertEqual(state(self.cdir)["status"]["2.2"]["s"], "done")

    def test_one_shaky_problem_makes_the_unit_shaky(self):
        self.finish("2.2.1")
        self.finish("2.2.2", result="unsolved")
        self.finish("2.2.3a", hints=1)
        self.finish("2.2.3b", transfer="missed")
        self.assertEqual(state(self.cdir)["status"]["2.2"]["s"], "shaky")
        index = (self.cdir / "gb.md").read_text(encoding="utf-8")
        self.assertIn("| [[gb-ch02#2.2.2 Defective ball\\|2.2.2 Defective ball]] | not solved ⚠ | passed |", index)
        self.assertIn("4/4 problems: ✓ ✗ ~ ✓", index)

    def test_a_new_attempt_keeps_the_old_one(self):
        self.finish("2.2.1", result="unsolved")
        self.book("attempt", "2.2.1", "--hint")
        r = state(self.cdir)["attempts"]["2:river-crossing"]
        self.assertEqual(r["history"][0]["outcome"], "unsolved")
        self.assertEqual((r["hints"], r.get("outcome")), (1, None))

    def test_switching_mode_keeps_progress(self):
        make(self.vault, "pml", GB, ["2.2", "2.3"], mode="textbook")
        p = self.vault / "courses" / "pml" / ".course" / "state.json"
        st = json.loads(p.read_text())
        st["status"] = {"2.2": {"s": "shaky", "at": "2026-10-25"}}
        p.write_text(json.dumps(st))
        self.book("set", "mode", "problems")
        st = json.loads(p.read_text())
        self.assertEqual((st["mode"], st["status"]), ("problems", {"2.2": {"s": "shaky", "at": "2026-10-25"}}))
        self.assertIn("PROBLEM: 2.3.1", self.book("next"))
        self.assertIn("UNIT: 2.2 Logic Reasoning", self.book("section", "2.2.2"))

    def test_unknown_problem(self):
        r = run(self.vault, "book.py", "attempt", "9.9.9", "--hint")
        self.assertNotEqual(r.returncode, 0)


class Misses(unittest.TestCase):
    def setUp(self):
        self.vault = make_vault(self)
        self.cdir = make(self.vault, "gb", GB, ["2.2", "2.3"])
        (self.cdir / "gb-ch02.md").write_text(NOTE, encoding="utf-8")
        (self.vault / "techniques").mkdir()
        (self.vault / "techniques" / "Information counting.md").write_text("# Information counting\n")
        for args in (["--hint", "1"], ["--hint", "3"], ["--result", "unsolved", "--miss", "method"],
                     ["--transfer", "passed"]):
            run(self.vault, "book.py", "attempt", "2.2.2", *args)
        for args in (["--result", "solved"], ["--transfer", "passed"]):
            run(self.vault, "book.py", "attempt", "2.2.1", *args)

    def test_review_card_for_a_hinted_problem(self):
        out = run(self.vault, "practice.py", "due", "--limit", "20").stdout
        cards = json.loads((self.vault / "practice" / ".cards.json").read_text())["cards"]
        problem = [c for c in cards if c["kind"] == "problem"]
        self.assertEqual(len(problem), 1)  # the unaided one is not a miss
        c = problem[0]
        self.assertEqual(c["key"], "problem:gb/2:defective-ball#0")
        self.assertEqual(c["source"], "gb-ch02#2.2.2 Defective ball")
        self.assertEqual(c["techniques"], ["Information counting"])
        self.assertTrue(c["prompt"].startswith("You have 12 balls"))
        self.assertEqual(c["miss"], "method")
        self.assertIsInstance(out, str)

    def test_technique_record_counts_the_attempt(self):
        run(self.vault, "technique.py", "sync")
        note = (self.vault / "techniques" / "Information counting.md").read_text(encoding="utf-8")
        self.assertIn("**Record:** 0 ✓ · 1 ✗ — 1 problem", note)
        self.assertIn("[[gb-ch02#2.2.2 Defective ball|§2.2.2 Defective ball]] (gb) ✗ — method miss", note)


if __name__ == "__main__":
    unittest.main()
