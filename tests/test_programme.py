"""programme.py: a programme over several book courses, in a throwaway vault with fake book.json files."""
import json
import unittest

from tests._vault import make_course, make_vault, run, set_status, write_note


class ProgrammeTest(unittest.TestCase):
    def setUp(self):
        self.vault = make_vault(self)
        self.bh = make_course(self.vault, "bh")
        self.strang = make_course(self.vault, "strang")  # the current course now
        self.state_dir = self.vault / ".claude" / "md-log-state"

    def pg(self, *args, ok=True):
        r = run(self.vault, "programme.py", *args)
        if ok:
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        return r

    def book(self, *args):
        r = run(self.vault, "book.py", *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def state(self, cdir):
        return json.loads((cdir / ".course" / "state.json").read_text(encoding="utf-8"))

    def pointer(self):
        return json.loads((self.state_dir / "course.json").read_text(encoding="utf-8"))["course"]

    def note(self):
        return (self.vault / "courses" / "quant" / "quant.md").read_text(encoding="utf-8")

    def setup_two_modules(self):
        self.pg("new", "quant", "--title", "Quant revision", "--goal", "pass the SIG test")
        self.pg("module", "Probability", "bh:1.1-1.2", "strang:2.1")
        self.pg("module", "Regression", "strang:2.2", "bh:2.3", "2.1")

    def write_module_heading(self, n, title):
        with open(self.vault / "courses" / "quant" / "quant.md", "a", encoding="utf-8") as f:
            f.write(f"\n## Module {n} — {title}\n\n### Overview\n\nText.\n")

    # --- setup

    def test_new_and_module_set_syllabi_and_order(self):
        self.setup_two_modules()
        self.assertEqual(self.state(self.bh)["syllabus"], ["1.1", "1.2", "2.1", "2.3"])
        self.assertEqual(self.state(self.strang)["syllabus"], ["2.1", "2.2"])
        p = json.loads((self.vault / "courses" / "quant" / ".programme" / "programme.json").read_text())
        self.assertEqual(p["modules"][1]["units"], [["strang", "2.2"], ["bh", "2.3"], ["bh", "2.1"]])
        self.assertEqual(p["modules"][1]["spec"], ["strang:2.2", "bh:2.3", "bh:2.1"])
        self.assertTrue(self.pointer().endswith("courses/bh"))  # the book of the first unit
        text = self.note()
        self.assertIn("# Quant revision", text)
        self.assertIn("1. **Probability** — 0 of 3 studied", text)
        self.assertIn("    - [ ] bh §1.1 What is learning · pp. 10–19", text)

    def test_done_units_stay_in_the_syllabus(self):
        set_status(self.bh, **{"2.2": ("done", "2026-10-01")})
        self.pg("new", "quant", "--title", "Q")
        self.pg("module", "Probability", "bh:1.1")
        self.assertEqual(self.state(self.bh)["syllabus"], ["1.1", "2.2"])

    def test_module_errors(self):
        self.pg("new", "quant", "--title", "Q")
        self.pg("module", "A", "bh:1.1")
        r = self.pg("module", "B", "bh:1.1-1.2", ok=False)
        self.assertIn("already in module 1", r.stderr)
        r = self.pg("module", "C", "1.1", ok=False)
        self.assertIn("name the course", r.stderr)
        r = self.pg("module", "D", "bh:9.9", ok=False)
        self.assertIn("unknown section", r.stderr)
        r = self.pg("new", "bh", ok=False)
        self.assertIn("already holds a course", r.stderr)

    def test_module_replace_insert_move_remove(self):
        self.setup_two_modules()
        self.pg("module", "Probability", "bh:1.1")  # same title: its units are replaced in place
        self.assertEqual(self.state(self.bh)["syllabus"], ["1.1", "2.1", "2.3"])
        self.assertEqual(self.state(self.strang)["syllabus"], ["2.2"])
        self.pg("module", "First", "strang:1.1", "--at", "1")
        r = self.pg("move", "1", "3")
        self.assertIn('"First" is now module 3', r.stdout)
        p = json.loads((self.vault / "courses" / "quant" / ".programme" / "programme.json").read_text())
        self.assertEqual([m["title"] for m in p["modules"]], ["Probability", "Regression", "First"])
        self.pg("remove", "2")
        p = json.loads((self.vault / "courses" / "quant" / ".programme" / "programme.json").read_text())
        self.assertEqual([m["title"] for m in p["modules"]], ["Probability", "First"])
        self.assertEqual(self.state(self.bh)["syllabus"], ["1.1"])
        self.assertEqual(self.state(self.strang)["syllabus"], ["1.1"])

    # --- next and section

    def test_next_at_module_start_switches_the_course(self):
        self.setup_two_modules()
        self.book("use", "strang")
        out = self.pg("next").stdout
        self.assertTrue(self.pointer().endswith("courses/bh"))
        self.assertIn('PROGRAMME: Quant revision — module 1 of 2 "Probability", unit 1 of 3 · bh §1.1', out)
        self.assertIn("MODULE START", out)
        self.assertIn("HEADING: ## Module 1 — Probability", out)
        self.assertIn("  → bh §1.1 What is learning", out)
        self.assertIn("  · strang §2.1 Intro", out)
        self.assertIn("NEXT: 1.1 What is learning", out)
        self.assertIn("PROGRAMME CHAPTER START", out)
        self.assertIn("[[quant#Module 1 — Probability|module 1 overview]]", out)
        self.assertIn("PROGRAMME GOAL: pass the SIG test", out)
        self.assertIn("programme.py done bh:1.1", out)

    def test_next_after_module_overview(self):
        self.setup_two_modules()
        self.write_module_heading(1, "Probability")
        out = self.pg("next").stdout
        self.assertNotIn("MODULE START", out)
        self.assertIn("PROGRAMME CHAPTER START", out)
        write_note(self.bh / "bh-ch01.md", ["Overview"])
        out = self.pg("next").stdout
        self.assertNotIn("PROGRAMME CHAPTER START", out)
        self.assertIn("(exists", out)

    def test_section_names_the_book(self):
        self.setup_two_modules()
        out = self.pg("section", "strang:2.2").stdout
        self.assertTrue(self.pointer().endswith("courses/strang"))
        self.assertIn('module 2 of 2 "Regression", unit 1 of 3 · strang §2.2', out)
        out = self.pg("section", "1.2").stdout  # the current book: strang
        self.assertIn("is not in the programme", out)

    # --- done

    def test_done_outcomes(self):
        self.setup_two_modules()
        self.write_module_heading(1, "Probability")
        self.pg("next")
        out = self.pg("done", "1.1").stdout  # same note next: bh 1.2
        self.assertIn("🗒 bh 1.1 What is learning: done — programme: 6 units: 1 done", out)
        self.assertIn("NEXT: 1.2 Supervised learning", out)
        out = self.pg("done", "bh:1.2").stdout  # chapter 1 of bh complete; strang 2.1 is in another note
        self.assertIn("CHAPTER 1 OF bh COMPLETE", out)
        self.assertIn("EXAM: /exam 1", out)
        self.assertIn("NEXT IN ANOTHER NOTE: strang §2.1 Intro (strang-ch02)", out)
        self.assertTrue(self.pointer().endswith("courses/bh"))  # /exam 1 is about bh
        self.pg("next")
        out = self.pg("done", "2.1").stdout
        self.assertIn('MODULE 1 "Probability" COMPLETE', out)
        self.assertIn("opens module 2", out)
        self.assertIn("`/course next` opens module 2 with its overview", out)
        self.assertEqual(self.state(self.bh)["status"]["1.1"]["s"], "done")
        for unit in ("strang:2.2", "bh:2.3"):
            self.pg("done", unit)
        out = self.pg("done", "bh:2.1", "--status", "shaky").stdout
        self.assertIn("PROGRAMME COMPLETE", out)
        self.assertIn("PROGRAMME COMPLETE", self.pg("next").stdout)

    # --- status, list, use

    def test_status(self):
        self.setup_two_modules()
        set_status(self.bh, **{"1.1": ("done", "2026-11-01"), "1.2": ("shaky", "2026-11-01")})
        out = self.pg("status").stdout
        self.assertIn("PROGRAMME: Quant revision", out)
        self.assertIn("PROGRESS: 6 units: 1 done, 1 shaky", out)
        self.assertIn("… 1 Probability — 2 of 3 (bh:1.1-1.2 strang:2.1)", out)
        self.assertIn("· 2 Regression — 0 of 3", out)
        self.assertIn("SHAKY: bh:1.2", out)
        self.assertIn('NEXT: module 1 "Probability" — strang §2.1 Intro', out)
        self.assertIn("  bh: 4 units in the syllabus", out)

    def test_list_and_use(self):
        make_course(self.vault, "pml1")
        self.setup_two_modules()
        out = self.pg("list").stdout
        self.assertIn("→ quant: Quant revision  (programme, 2 modules)", out)
        self.assertIn("    ▸ bh:", out)
        self.assertIn("  pml1:", out)
        out = self.pg("use", "pml1").stdout  # not a member: the programme is no longer current
        self.assertIn("🗒 current course: pml1", out)
        self.assertNotIn("PROGRAMME", out)
        out = self.pg("next").stdout
        self.assertNotIn("PROGRAMME", out)
        self.assertIn("NEXT: 1.1", out)
        self.assertIn("→ pml1:", self.pg("list").stdout)
        out = self.pg("use", "strang").stdout  # a member: the programme is current again
        self.assertIn("PROGRAMME: quant stays current", out)
        out = self.pg("use", "quant").stdout
        self.assertIn("🗒 current programme: quant", out)
        self.assertTrue(self.pointer().endswith("courses/bh"))
        self.assertEqual(self.pg("members").stdout.split(),
                         [str(self.vault / "courses" / "bh"), str(self.vault / "courses" / "strang")])
        self.pg("off")
        self.assertEqual(self.pg("members").stdout, "")

    def test_without_a_programme_it_is_book_py(self):
        out = self.pg("next").stdout
        self.assertIn("NEXT: 1.1", out)
        self.assertNotIn("PROGRAMME", out)
        out = self.pg("done", "bh:1.1").stdout
        self.assertIn("🗒 1.1 What is learning: done", out)
        self.assertEqual(self.state(self.bh)["status"]["1.1"]["s"], "done")
        self.assertIn("COURSE:", self.pg("status").stdout)

    # --- the programme note

    def test_index_keeps_the_body_and_links_taught_units(self):
        self.setup_two_modules()
        self.write_module_heading(1, "Probability")
        body = self.note().split("%% /programme index %%\n", 1)[1]
        write_note(self.bh / "bh-ch01.md", ["Overview", "1.1 What is learning"])
        set_status(self.bh, **{"1.1": ("done", "2026-11-01")})
        self.pg("status")
        text = self.note()
        self.assertEqual(text.split("%% /programme index %%\n", 1)[1], body)
        self.assertIn("1. **Probability** — 1 of 3 studied · [[#Module 1 — Probability|overview]]", text)
        self.assertIn("- [x] bh [[bh-ch01#1.1 What is learning|§1.1 What is learning]]", text)
        self.assertIn("- [ ] bh §1.2 Supervised learning", text)
        self.assertEqual(text.count("# Quant revision\n"), 1)

    # --- with problem courses and interviews

    def test_problem_course_hands_the_next_unit_to_the_programme(self):
        self.setup_two_modules()
        st = self.state(self.bh)
        st["mode"] = "problems"
        (self.bh / ".course" / "state.json").write_text(json.dumps(st), encoding="utf-8")
        out = self.pg("next").stdout
        self.assertIn("PROGRAMME RECORD:", out)
        self.assertNotIn("RECORD: when every node", out)
        self.book("attempt", "1.1", "--result", "solved")
        r = self.book("attempt", "1.1", "--transfer", "passed")
        self.assertIn("PROGRAMME: record the unit in the programme with: programme.py done bh:1.1", r.stdout)
        self.assertNotIn("NEXT:", r.stdout)

    def test_interview_scope_defaults_to_the_programme(self):
        other = make_course(self.vault, "pml1")
        set_status(other, **{"1.1": ("done", "2026-10-01")})
        set_status(self.bh, **{"1.1": ("done", "2026-10-01")})
        self.pg("new", "quant", "--title", "Q")
        self.pg("module", "Probability", "bh:1.1-1.2")
        r = run(self.vault, "interview.py", "new", "--length", "short")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertNotIn("pml1", r.stdout)


if __name__ == "__main__":
    unittest.main()
