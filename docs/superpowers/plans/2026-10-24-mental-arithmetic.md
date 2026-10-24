# Mental Arithmetic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/arith [mode]` runs a timed Zetamac-style sprint in a tmux popup (core, fractions, powers, estimate, mixed, weak), records each question's kind and time, and reports the score against the learner's own history.

**Architecture:** `hooks/arith.py` holds pure functions (question generators, answer acceptance, kind speeds, weak-mode selection, summaries) tested directly, a curses `play` loop, and a `run` command that opens `play` in a tmux popup and prints the summary. History is `<vault>/practice/.arith.json`. The `arith` skill starts it and writes the summary into the practice note.

**Tech Stack:** Python 3.10+, standard library only (`random`, `statistics`, `curses`, `fractions.Fraction`); tests with `unittest`.

**Spec:** `docs/superpowers/specs/2026-10-24-mental-arithmetic-design.md`

## Global Constraints

- Ranges, exactly as the spec's mode table (core: `+` a,b ∈ [2,100]; `−` reversed `+`; `×` a ∈ [2,12], b ∈ [2,100]; `÷` reversed `×`. fractions: d ∈ {2..12, 16, 20, 25, 40}, 1 ≤ n < d, 4 places rounded for repeating; percent p ∈ {5, 10, 12.5, 15, 20, 25, 30, 40, 75}, y multiple of 4 in [20, 800], answer ≤ 1 decimal place. powers: n² n ∈ [11,30]; 2^k k ∈ [5,20]; n³ n ∈ [2,12]. estimate: a×b a,b ∈ [12,999] ≥ one 3-digit; a÷b a ∈ [100,9999], b ∈ [3,99]; tolerance 2%.)
- Kinds, exactly: `+ carry`, `+ no carry`, `− borrow`, `− no borrow`, `× <a>`, `÷ <a>`, `/<d>`, `<p>% of`, `square 1x`, `square 2x`, `2^k`, `cube`, `≈ ×`, `≈ ÷`.
- Speed: median ms over a kind's last 50 correct questions; ranked only with ≥ 10; weak: 70% from the five kinds slowest relative to the median of their mode's kinds, 30% uniform `mixed`.
- Acceptance: integer — typed value equals; decimal — value equals and typed decimal places ≥ the answer's shortest form's; estimate — Enter and |typed − true| ≤ 2% of |true|.
- Summary lines exactly: `ARITHMETIC: <mode> · <s> s · score <n> (<k> skipped)`, `BEST: <b> · LAST 5 AVERAGE: <a>` (one decimal; `—` with no complete sprint before), `SLOWEST: <kind> <x.x> s · …` (three, this sprint, ≥ 1 sample each). Partial sprints: `ARITHMETIC: <mode> · stopped at <m:ss> · score <n>` and no BEST line.
- `run` outside tmux prints exactly `NO TMUX: run "python3 .claude/hooks/arith.py play <mode>" in another terminal, then /arith last`, exit 0.
- Popup: `tmux display-popup -E -w 70 -h 14`.
- Standard library only; match `quiz_popup.py` for curses idioms (`get_wch`, colour pairs). README is a tutorial.

## Review Focus

1. **Typing past the answer** (answer 42, learner types "4", "42" advances; answer 4 — "4" advances at once, so the learner who meant 43 for a different question is not affected): decimals — answer 0.5, typed "0.50": "0.5" already advanced. Test in Task 1 that no exact answer is a strict decimal-prefix of a longer accepted form the learner must type.
2. **Terminal too small for the popup** (tmux refuses `-h 14` on a short pane): fall back to `-h 90%`, as the quiz server does. Test in Task 3 with a stubbed tmux returning "too large".
3. **Clock and suspend** (the laptop sleeps mid-sprint): the sprint ends at its deadline by wall clock; nothing is recorded past it. Test in Task 3's pure timing helper.
4. **A corrupt or missing history file**: `play` and `last` still work (missing: empty history; corrupt: refuse to overwrite, as `practice.py`). Test in Task 2.
5. **`weak` before any history**: falls back to uniform `mixed` without error. Test in Task 2.

---

### Task 1: questions and acceptance

**Files:**
- Create: `hooks/arith.py`
- Test: `tests/test_arith.py`

**Interfaces:**
- Produces: `MODES = ("core", "fractions", "powers", "estimate", "mixed", "weak")`; `generate(mode, rng, weak_kinds=None) -> dict` with keys `text` (as shown, e.g. `"73 × 6"`), `answer` (exact answer string in shortest form, or the true value as a string for an estimate), `kind`, `estimate` (bool), `mode` (the concrete mode it came from); `accepts(typed: str, q: dict, enter: bool = False) -> bool`; `mode_of(kind) -> str`.

- [ ] **Step 1: Write the failing tests** (`tests/test_arith.py`, importing the repo's `arith` via `tests._vault`'s path setup):

```python
def qs(mode, n=2000, seed=1):
    rng = random.Random(seed); return [arith.generate(mode, rng) for _ in range(n)]

def test_core_ranges_and_reversals(self):
    for q in qs("core"):
        a, op, b = q["text"].split(" ")
        a, b, ans = int(a), int(b), int(q["answer"])
        if op == "+": self.assertTrue(2 <= a <= 100 and 2 <= b <= 100 and ans == a + b)
        if op == "−": self.assertTrue(ans >= 2 and a - b == ans and 2 <= b <= 100)
        if op == "×": self.assertTrue(2 <= a <= 12 and 2 <= b <= 100 and ans == a * b)
        if op == "÷": self.assertTrue(2 <= b <= 12 and a == b * ans and 2 <= ans <= 100)
    self.assertEqual({q["text"].split(" ")[1] for q in qs("core")}, {"+", "−", "×", "÷"})
def test_core_kinds(self):
    rng = random.Random(0)
    kinds = {q["kind"] for q in qs("core")}
    self.assertTrue({"+ carry", "+ no carry", "− borrow", "− no borrow", "× 7", "÷ 12"} <= kinds)
def test_fractions(self):
    for q in qs("fractions"):
        if q["kind"].startswith("/"):
            n, d = map(int, q["text"].split("/"))
            self.assertIn(d, list(range(2, 13)) + [16, 20, 25, 40]); self.assertTrue(1 <= n < d)
            self.assertEqual(q["answer"], f"{round(n / d, 4):.4f}".rstrip("0").rstrip("."))
            self.assertEqual(q["kind"], f"/{d}")
        else:
            self.assertRegex(q["text"], r"^\d+(\.5)?% of \d+$")
            self.assertLessEqual(len(q["answer"].split(".")[-1]) if "." in q["answer"] else 0, 1)
def test_powers(self):
    kinds = Counter(q["kind"] for q in qs("powers"))
    self.assertEqual(set(kinds), {"square 1x", "square 2x", "2^k", "cube"})
    for q in qs("powers", 300):
        self.assertEqual(int(q["answer"]), eval(q["text"].replace("²", "**2").replace("³", "**3").replace("^", "**")))
def test_estimate(self):
    for q in qs("estimate", 500):
        self.assertTrue(q["estimate"]); self.assertIn(q["kind"], ("≈ ×", "≈ ÷"))
def test_mixed_draws_every_mode(self):
    self.assertEqual({q["mode"] for q in qs("mixed")}, {"core", "fractions", "powers", "estimate"})
def test_accepts(self):
    q = {"answer": "0.375", "estimate": False}
    self.assertFalse(arith.accepts("0.37", q)); self.assertTrue(arith.accepts("0.375", q)); self.assertTrue(arith.accepts(".375", q))
    self.assertTrue(arith.accepts("0.5", {"answer": "0.5", "estimate": False}))
    self.assertTrue(arith.accepts("438", {"answer": "438", "estimate": False}))
    self.assertFalse(arith.accepts("43", {"answer": "438", "estimate": False}))
    e = {"answer": "1081", "estimate": True}
    self.assertFalse(arith.accepts("1100", e))                 # no Enter
    self.assertTrue(arith.accepts("1100", e, enter=True))      # 1.8%
    self.assertFalse(arith.accepts("1110", e, enter=True))     # 2.7%
    self.assertFalse(arith.accepts("", e, enter=True)); self.assertFalse(arith.accepts("-", q))
def test_no_answer_needs_typing_past_an_accepted_prefix(self):
    for q in qs("mixed", 3000):
        if not q["estimate"]:
            ans = q["answer"]
            self.assertFalse(any(arith.accepts(ans[:k], q) for k in range(1, len(ans))), q)
def test_mode_of(self):
    self.assertEqual(arith.mode_of("× 7"), "core"); self.assertEqual(arith.mode_of("/16"), "fractions")
    self.assertEqual(arith.mode_of("cube"), "powers"); self.assertEqual(arith.mode_of("≈ ÷"), "estimate")
```

- [ ] **Step 2: Run to verify they fail** — `python3 -m unittest tests.test_arith -v` → FAIL (no module `arith`).
- [ ] **Step 3: Implement** the generators and `accepts` per the Global Constraints. Use `fractions.Fraction`/`decimal` rounding for the 4-place answers (half-up), and strip trailing zeros for the shortest form. For percent questions, draw `y` until `p × y / 100` has at most one decimal place.
- [ ] **Step 4: Run to verify they pass** — same command → PASS.
- [ ] **Step 5: Commit** — `git add hooks/arith.py tests/test_arith.py && git commit -m "arith.py: questions, kinds and answer acceptance"`

---

### Task 2: history, speeds, weak mode, summaries

**Files:**
- Modify: `hooks/arith.py`
- Test: `tests/test_arith.py`

**Interfaces:**
- Produces: `HISTORY` path; `load_history() -> dict` (missing → `{"sprints": []}`; corrupt → `book.die`), `save_sprint(sprint)`; `kind_speeds(history) -> dict[str, float]` (median ms, ranked kinds only); `weak_kinds(history) -> list[str]` (≤ 5); `summary(sprint, history) -> str`; commands `last`, `history`, `kinds`.

- [ ] **Step 1: Write the failing tests:** fabricated histories (helper `sprint(mode, score, complete=True, questions=[(kind, ms), …])`):

```python
def test_kind_speeds_last_50_and_ranking_floor(self):
    h = {"sprints": [sprint("core", 0, questions=[("× 7", 5000)] * 30 + [("× 7", 1000)] * 50 + [("× 2", 900)] * 9)]}
    sp = arith.kind_speeds(h)
    self.assertEqual(sp["× 7"], 1000)          # only the last 50
    self.assertNotIn("× 2", sp)                # fewer than 10
def test_weak_kinds_relative_within_mode(self):
    qsx = [("× 7", 3000)] * 12 + [("× 3", 1000)] * 12 + [("+ carry", 1200)] * 12 + [("/16", 4000)] * 12 + [("/2", 3800)] * 12 + [("/4", 3900)] * 12
    w = arith.weak_kinds({"sprints": [sprint("mixed", 0, questions=qsx)]})
    self.assertEqual(w[0], "× 7")              # 3000 vs a core median of 1200; /16 is near its fractions median
def test_weak_generation_share(self):
    h = {"sprints": [sprint("mixed", 0, questions=[("× 7", 3000)] * 12 + [("× 3", 1000)] * 12 + [("+ carry", 1000)] * 12)]}
    rng = random.Random(3); w = arith.weak_kinds(h)
    share = sum(arith.generate("weak", rng, w)["kind"] in w for _ in range(2000)) / 2000
    self.assertTrue(0.6 < share < 0.85)
def test_weak_without_history(self):
    self.assertEqual(arith.weak_kinds({"sprints": []}), [])
    arith.generate("weak", random.Random(1), [])   # no error
def test_summary(self):
    h = {"sprints": [sprint("core", s) for s in (30, 41, 35, 36, 37, 38)] + [sprint("core", 99, complete=False)]}
    new = sprint("core", 38, questions=[("× 7", 2400), ("− borrow", 2100), ("÷ 8", 1900), ("+ carry", 800)], skipped=1)
    self.assertEqual(arith.summary(new, h), "ARITHMETIC: core · 120 s · score 38 (1 skipped)\n"
                                             "BEST: 41 · LAST 5 AVERAGE: 37.4\n"
                                             "SLOWEST: × 7 2.4 s · − borrow 2.1 s · ÷ 8 1.9 s")
def test_partial_summary(self):
    s = sprint("core", 9, complete=False); s["stopped"] = 47
    self.assertEqual(arith.summary(s, {"sprints": []}).split("\n")[0], "ARITHMETIC: core · stopped at 0:47 · score 9")
def test_last_history_kinds_commands(self):   # in a throwaway vault via run(...)
    ...write .arith.json with three sprints...
    self.assertIn("ARITHMETIC: core", run(v, "arith.py", "last").stdout)
    self.assertRegex(run(v, "arith.py", "history", "core").stdout, r"core: .*best \d+")
    self.assertIn("× 7", run(v, "arith.py", "kinds").stdout)
def test_corrupt_history_refused(self):
    ...write "{bad"...; r = run(v, "arith.py", "last"); self.assertNotEqual(r.returncode, 0)
```

  (`summary`'s BEST and average use the complete sprints of that mode *before* the new one: best 41, last five 41, 35, 36, 37, 38 → 37.4.)

- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3: Implement** per the spec's Kinds, History and Summary sections.
- [ ] **Step 4: Run to verify they pass.**
- [ ] **Step 5: Commit** — `git commit -m "arith.py: history, kind speeds, weak mode, summaries"`

---

### Task 3: the popup — `play` and `run`

**Files:**
- Modify: `hooks/arith.py`
- Test: `tests/test_arith.py`

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces: `deadline_left(start: float, seconds: int, now: float) -> float`; `run_command(mode, seconds) -> list[str]` (the tmux argv, height `14`); commands `play`, `run`.

- [ ] **Step 1: Write the failing tests:**

```python
def test_deadline(self):
    self.assertEqual(arith.deadline_left(100.0, 120, 150.0), 70.0)
    self.assertEqual(arith.deadline_left(100.0, 120, 900.0), 0.0)     # suspended past the end
def test_run_outside_tmux(self):
    r = run(v, "arith.py", "run", "core", env={"TMUX": ""})
    self.assertEqual(r.returncode, 0)
    self.assertEqual(r.stdout.strip(), 'NO TMUX: run "python3 .claude/hooks/arith.py play core" in another terminal, then /arith last')
def test_run_retries_tall_popup(self):
    # fake tmux on PATH: exits 1 with "too large" when given -h 14, else appends a sprint to .arith.json and exits 0
    r = run(v, "arith.py", "run", "core", "--seconds", "10", env=fake_tmux_env)
    self.assertIn("ARITHMETIC: core", r.stdout)
    self.assertIn("-h 90%", calls_log.read_text())
```

- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3: Implement** `play` (curses, `get_wch`; layout and keys exactly as the spec's popup section; on time-out or Esc, the end screen, `save_sprint` before returning) and `run` (`tmux display-popup -E -w 70 -h 14 <python> <arith.py> play <mode> --seconds <s>`, retry with `-h 90%` on "too large", then print `summary` of the newest sprint; nothing new recorded → print `NO SPRINT RECORDED`).
- [ ] **Step 4: Run to verify they pass.**
- [ ] **Step 5: Drive by hand** in a detached tmux session with a throwaway vault: `play core --seconds 10`, read the question with `capture-pane`, type the right answer (auto-advance), a wrong one (no advance), Tab, then let it time out; check the end screen and `.arith.json`. Repeat with `estimate` (Enter, a 3% answer refused) and Esc (partial). Ledger the results.
- [ ] **Step 6: Commit** — `git commit -m "arith.py: the sprint popup"`

---

### Task 4: skill, settings, docs

**Files:**
- Create: `skills/arith/SKILL.md`
- Modify: `settings.json`, `README.md`, `docs/architecture.md`

- [ ] **Step 1: The skill** — frontmatter (`name: arith`; description triggering on `/arith`, "mental arithmetic", "Zetamac", "speed maths"; `argument-hint: [core | fractions | powers | estimate | mixed | weak] [seconds] | last | history [mode]`; `allowed-tools: Bash(python3 .claude/hooks/arith.py *), Bash(python3 .claude/hooks/md_log.py *)`). Steps exactly as the spec's skill section, including the 600000 ms Bash timeout and the practice-note summary with at most one tip.
- [ ] **Step 2: Settings and docs.** `settings.json`: `Bash(python3 .claude/hooks/arith.py *)`. README: a `### Mental arithmetic` subsection in `## Practice` (modes table, the auto-advance and Enter-for-estimates rule, Tab/Esc, the end screen, weak mode, history), commands table rows, contents unchanged. Architecture: a `## Mental arithmetic` section.
- [ ] **Step 3: Verify and commit.** Full suite passes; settings parse.

```bash
git add skills/arith/SKILL.md settings.json README.md docs/architecture.md
git commit -m "Arith skill and docs"
```
