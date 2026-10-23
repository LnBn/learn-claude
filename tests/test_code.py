import json
import unittest
from pathlib import Path

from tests._vault import make_vault, run
from tests import _code_fixtures as fx


def lines_of(out):
    return dict(ln.split(" ", 1) for ln in out.splitlines() if " " in ln)


class Base(unittest.TestCase):
    def setUp(self):
        self.vault = make_vault(self)

    def code(self, *args):
        return run(self.vault, "coding.py", *args)

    def make_track(self, topics=(("lists", 3), ("dicts", 2))):
        r = self.code("track", "new", "quant", "--title", "Quant Python")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        syl = self.vault / "syllabus.json"
        syl.write_text(json.dumps([{"topic": t, "target": n} for t, n in topics]))
        r = self.code("track", "syllabus", "quant", "--file", "syllabus.json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def write_task(self, where, slug="running-max", tests=fx.TESTS, starter=fx.STARTER):
        r = self.code("plan", *where, "--slug", slug)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        p = lines_of(r.stdout)
        note, start, hidden = (self.vault / p[k] for k in ("NOTE", "STARTER", "TESTS"))
        hidden.parent.mkdir(parents=True, exist_ok=True)
        note.write_text(fx.NOTE.format(starter=p["STARTER"], name=start.name))
        start.write_text(starter)
        hidden.write_text(tests)
        return p

    def state(self, base):
        hidden = ".track" if base.startswith("practice/") else ".tests"
        return json.loads((self.vault / base / hidden / "state.json").read_text())


class Tracks(Base):
    def test_track_new_and_syllabus(self):
        self.make_track()
        self.assertTrue((self.vault / "practice/quant/quant.md").exists())
        s = self.state("practice/quant")
        self.assertEqual(s["kind"], "track")
        self.assertEqual(s["python"], "python3")
        self.assertEqual(s["syllabus"][0], {"topic": "lists", "target": 3, "level": 1})

    def test_plan_paths(self):
        self.make_track()
        p = lines_of(self.code("plan", "--track", "quant", "--slug", "running-max").stdout)
        self.assertEqual(p["NOTE"], "practice/quant/01-running-max.md")
        self.assertEqual(p["STARTER"], "practice/quant/01-running-max.py")
        self.assertEqual(p["TESTS"], "practice/quant/.track/01-running-max.py")
        self.assertEqual(p["TASK"], "01")
        self.assertEqual(p["SUGGEST"], "lists")
        (self.vault / "lessons").mkdir()
        (self.vault / "lessons/py.md").write_text("# Py\n")
        p = lines_of(self.code("plan", "--note", "lessons/py.md", "--slug", "x").stdout)
        self.assertEqual(p["NOTE"], "lessons/py — code/01-x.md")
        self.assertEqual(p["TESTS"], "lessons/py — code/.tests/01-x.py")


class Check(Base):
    def check(self, note, *extra):
        return self.code("check", note, "--topics", "lists", "--level", "1", *extra)

    def test_check_accepts(self):
        self.make_track()
        p = self.write_task(["--track", "quant"])
        r = self.check(p["NOTE"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OPEN practice/quant/01-running-max.md", r.stdout)
        self.assertIn("LIMIT 200 ms", r.stdout)
        rec = self.state("practice/quant")["tasks"][0]
        self.assertEqual((rec["n"], rec["slug"], rec["status"], rec["title"]), (1, "running-max", "open", "Running maximum"))
        self.assertEqual(rec["limit"], 0.2)  # the floor: the reference is far under 20 ms
        self.assertEqual(rec["topics"], ["lists"])
        self.assertIn("[[01-running-max]]", (self.vault / "practice/quant/quant.md").read_text())
        p2 = lines_of(self.code("plan", "--track", "quant", "--slug", "next").stdout)
        self.assertEqual(p2["TASK"], "02")

    def test_check_refuses_wrong_expected(self):
        self.make_track()
        p = self.write_task(["--track", "quant"], tests=fx.TESTS.replace('"expected": [3, 3, 4, 4, 5]', '"expected": [9]'))
        r = self.check(p["NOTE"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("REFUSED case example: reference returns [3, 3, 4, 4, 5]", r.stdout)
        self.assertEqual(self.state("practice/quant")["tasks"], [])

    def test_check_refuses_missing_function(self):
        self.make_track()
        p = self.write_task(["--track", "quant"], starter="def other(xs):\n    ...\n")
        r = self.check(p["NOTE"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("REFUSED the starter file does not define running_max()", r.stdout)

    def test_check_refuses_slow_within_limit(self):
        self.make_track()
        p = self.write_task(["--track", "quant"], tests=fx.TESTS.replace("range(10000)", "range(10)"))
        r = self.check(p["NOTE"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("REFUSED the speed tests do not separate slow() from reference()", r.stdout)

    def test_check_refuses_unknown_topic(self):
        self.make_track()
        p = self.write_task(["--track", "quant"])
        r = self.code("check", p["NOTE"], "--topics", "nonsense", "--level", "1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("REFUSED topic nonsense is not in the syllabus", r.stdout)

    def test_lesson_check_writes_open_box(self):
        (self.vault / "lessons").mkdir()
        (self.vault / "lessons/py.md").write_text("# Py\n\nSome text.\n")
        p = self.write_task(["--note", "lessons/py.md"])
        r = self.check(p["NOTE"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = (self.vault / "lessons/py.md").read_text()
        self.assertIn("\n\n> [!question|code]+ Task 01: Running maximum\n", text)
        self.assertEqual(self.state("lessons/py — code")["kind"], "lesson")


if __name__ == "__main__":
    unittest.main()
