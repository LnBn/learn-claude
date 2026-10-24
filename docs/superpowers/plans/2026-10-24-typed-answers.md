# Typed Answers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A graded quiz can ask for a typed number or formula, which the quiz server marks on Enter, and the teach skill uses it for Apply questions whose result is a value or a formula.

**Architecture:** A new module, `mcp/answer_check.py`, is the only code that reads, shows and compares typed answers. The quiz server validates a typed call with it and marks the answer; the popup uses it for the live preview and its feedback screen; `hooks/quiz_block.py` renders the typed record without importing it (the record carries everything the note needs).

**Tech Stack:** Python 3.10+, standard library only (`ast`, `math`, `random`, `hashlib`, `curses`); tests with `unittest` (`python3 -m unittest discover -s tests -v`).

**Spec:** `docs/superpowers/specs/2026-10-24-typed-answers-design.md`

## Global Constraints

- Standard library only. `eval`/`exec` never run on learner or teacher text; only the whitelisted AST is evaluated by a small tree walker.
- All arithmetic is done in floats (numeric literals become floats), so `9^9^9` overflows to "undefined" instead of building a huge integer.
- Six points for a question with variables; one point (`{}`) without. Points are seeded from `hashlib.sha256` of `expected` plus the sorted variable spec, so the popup and the server draw the same points.
- Exact form: relative tolerance `1e-9`, absolute `1e-12` near zero. Decimal (text contains `.`): `|g - x| <= 0.5 * 10**(floor(log10(|x|)) - 2)`, and `5e-4` when `x == 0`.
- Fewer than 3 defined points for `answer` refuses the call.
- Error strings, exactly: `can't read: unclosed bracket`, `can't read: nothing after ^`, `unknown name: m — this question's variables are n` (no `— …` part when there are no variables), `give the exact form, not a decimal`.
- Reserved names that cannot be variables: `e`, `pi`, `inf`, and every function name (`sqrt ln log log2 log10 exp abs binom C`).
- Popup keys in typed mode: Enter submit, ↑/↓ between field and "I don't know", Tab note, `?` ask first, Ctrl-F figure, Esc cancel; `q` and `f` are typed into the field.
- Match the surrounding code: short docstrings, comments only where the reason is not obvious. README is a tutorial: how things work now, no change history.

**Addition to the spec found while planning:** the typed record gains `"decimal": bool` (the learner's text contained a decimal point), so `quiz_block.render` can show `Exact value: …` without importing the checker from `mcp/`.

## Review Focus

1. **Answers that would hang or crash the evaluator** (`9^9^9`, `1000!`, `(-8)^(1/3)`, `ln(-1)`): marked wrong (or undefined at that point) at once, never a hang or traceback. Test in Task 1.
2. **Negative and near-zero expected values under the decimal rule** (`-0.333` for $-1/3$, `0.0004` for $0$): the rule uses $|x|$ and the zero case. Test in Task 1.
3. **A teacher declaring a variable named `e`, `pi` or `C`, or `p` and `i` together** (so `pi` is ambiguous): `e`/`pi`/function names are refused as variable names at call time; with `p` and `i` declared, `pi` still reads as π. Test in Task 1.
4. **A learner's answer containing a backtick or spaces and Unicode operators pasted from the note** (`2 ( n + 1 )`, `−1/3`, ``2`^n``): reads correctly, and the note never shows broken inline code. Tests in Tasks 1 and 2.
5. **A typed quiz re-asked after `?`**: the second call writes the graded block after the asked-first block, and a different typed question is not mistaken for the re-ask. Test in Task 3.

---

### Task 1: `mcp/answer_check.py`

**Files:**
- Create: `mcp/answer_check.py`
- Test: `tests/test_answer_check.py`

**Interfaces:**
- Produces:
  - `class AnswerError(ValueError)` — the message is shown to the learner or the teacher as is.
  - `parse_ranges(variables: dict[str, str]) -> dict[str, tuple[str, float, float]]` — `"int 1..12"` → `("int", 1, 12)`, `"0..1"` → `("real", 0, 1)`; raises `AnswerError(f'{name}: bad range "{spec}" — write "int a..b" or "a..b" with a < b')` or `AnswerError(f"{name}: reserved name, choose another")`.
  - `read(text: str, variables: dict[str, str]) -> ast.Expression` — raises `AnswerError`.
  - `display(text: str, variables: dict[str, str]) -> str` — Unicode form; raises `AnswerError`.
  - `is_decimal(text: str) -> bool` — text contains `.`.
  - `points(expected: str, variables: dict[str, str]) -> list[dict[str, float]]`
  - `evaluate(tree: ast.Expression, point: dict[str, float]) -> float | None` — `None` when undefined.
  - `defined_points(expected: str, variables: dict[str, str]) -> int`
  - `check(given: str, expected: str, variables: dict[str, str], exact: bool = False) -> str` — `"correct"` or `"wrong"`; raises `AnswerError` when `given` cannot be read or is a decimal under `exact`.
  - `matches_wrong(given: str, wrong_answers: list[dict], variables: dict[str, str], exact: bool = False) -> int | None`

- [ ] **Step 1: Write the failing tests** in `tests/test_answer_check.py` (import with `sys.path.insert(0, str(REPO / "mcp"))`, `REPO` from `tests._vault`). `N = {"n": "int 1..12"}`, `NP = {"n": "int 1..12", "p": "0..1"}`.

```python
class Reading(unittest.TestCase):
    def test_equal_formulas_written_differently(self):
        for g in ["2^(n+1)-2", "2*2^n-2", "2(2^n-1)", "2**(n+1) - 2", " 2 ( 2^n - 1 ) "]:
            self.assertEqual(check(g, "2^(n+1)-2", N), "correct", g)
    def test_implicit_multiplication(self):
        self.assertEqual(check("np", "n*p", NP), "correct")
        self.assertEqual(check("(n+1)(n+2)", "n^2+3n+2", N), "correct")
        self.assertEqual(check("3pi", "3*pi", {}), "correct")
    def test_functions_constants_unicode(self):
        for g, x, v in [("√2/2", "sqrt(2)/2", {}), ("π/4", "pi/4", {}), ("e^-1", "exp(-1)", {}),
                        ("C(5,2)", "10", {}), ("binom(n,2)", "n(n-1)/2", N), ("(2n)!/(n!)^2", "binom(2n,n)", N),
                        ("3 × 4 − 2", "10", {}), ("2·3", "6", {}), ("ln(e)", "1", {}), ("log(e)", "1", {}),
                        ("log2(8)", "3", {}), ("log10(1000)", "3", {}), ("abs(-2)", "2", {}), ("√(n+1)", "sqrt(n+1)", N),
                        ("∞", "inf", {}), ("−1/3", "-1/3", {})]:
            self.assertEqual(check(g, x, v), "correct", g)
    def test_pi_wins_over_variables_p_and_i(self):
        self.assertEqual(check("pi", "3.14159265358979", {"p": "0..1", "i": "0..1"}), "correct")
    def test_unknown_name(self):
        with self.assertRaisesRegex(AnswerError, "^unknown name: m — this question's variables are n$"):
            check("m+1", "n+1", N)
        with self.assertRaisesRegex(AnswerError, "^unknown name: m$"):
            check("m", "1", {})
    def test_error_messages(self):
        with self.assertRaisesRegex(AnswerError, "^can't read: unclosed bracket$"):
            read("(1+2", {})
        with self.assertRaisesRegex(AnswerError, "^can't read: nothing after \\^$"):
            read("2^", {})
    def test_refused_syntax(self):
        for bad in ["__import__('os')", "n.real", "[1]", "lambda: 1", "1 if 1 else 2", "a=1", "2,3", "'x'"]:
            with self.assertRaises(AnswerError, msg=bad):
                read(bad, N)
    def test_ranges(self):
        self.assertEqual(parse_ranges({"n": "int 1..12", "p": "0..1"}), {"n": ("int", 1, 12), "p": ("real", 0, 1)})
        for bad in [{"n": "int 5..1"}, {"p": "1..1"}, {"p": "zero..1"}, {"e": "0..1"}, {"pi": "0..1"}, {"C": "int 1..3"}]:
            with self.assertRaises(AnswerError, msg=str(bad)):
                parse_ranges(bad)

class Comparing(unittest.TestCase):
    def test_formula_agreeing_at_one_point_is_wrong(self):
        self.assertEqual(check("n^2", "2n", N), "wrong")
    def test_points(self):
        ps = points("2^n", NP)
        self.assertEqual(len(ps), 6)
        self.assertTrue(all(float(p["n"]).is_integer() and 1 <= p["n"] <= 12 and 0 < p["p"] < 1 for p in ps))
        self.assertEqual(ps, points("2^n", NP))
        self.assertEqual(points("1/3", {}), [{}])
    def test_undefined_points(self):
        self.assertEqual(check("1/(n-3)", "1/(n-3)", {"n": "int 1..6"}), "correct")
        self.assertEqual(check("1/(n-n)", "1", N), "wrong")
        self.assertEqual(defined_points("1/(n-n)", N), 0)
    def test_no_hang_no_crash(self):
        for g in ["9^9^9", "1000!", "(-8)^(1/3)", "ln(-1)", "1/0"]:
            self.assertEqual(check(g, "1", {}), "wrong", g)
    def test_decimal_rule(self):
        for g, x, want in [("0.333", "1/3", "correct"), ("0.3333", "1/3", "correct"), ("0.33", "1/3", "wrong"),
                           ("0.334", "1/3", "wrong"), ("-0.333", "-1/3", "correct"), ("33.3", "100/3", "correct"),
                           ("33.4", "100/3", "wrong"), ("0.0004", "0", "correct"), ("0.0006", "0", "wrong"),
                           ("0.5n", "n/2", "correct")]:
            self.assertEqual(check(g, x, N if "n" in x else {}), want, g)
    def test_exact_form(self):
        self.assertEqual(check("333/1000", "1/3", {}), "wrong")
        self.assertEqual(check("1/2", "1/2", {}, exact=True), "correct")
        with self.assertRaisesRegex(AnswerError, "^give the exact form, not a decimal$"):
            check("0.5", "1/2", {}, exact=True)
    def test_infinity(self):
        self.assertEqual(check("inf", "inf", {}), "correct")
        self.assertEqual(check("-inf", "inf", {}), "wrong")
        self.assertEqual(check("1000000", "inf", {}), "wrong")
    def test_matches_wrong(self):
        wrong = [{"answer": "2^n", "why": "a"}, {"answer": "2^(n+1)", "why": "b"}]
        self.assertEqual(matches_wrong("2*2^(n-1)", wrong, N), 0)
        self.assertEqual(matches_wrong("2(2^n)", wrong, N), 1)
        self.assertIsNone(matches_wrong("2^(n+1)-2", wrong, N))

class Showing(unittest.TestCase):
    def test_display(self):
        self.assertEqual(display("2^(n+1)-2", N), "2ⁿ⁺¹ − 2")
        self.assertEqual(display("sqrt(2)/2", {}), "√2/2")
        self.assertEqual(display("binom(n,2)", N), "C(n, 2)")
        self.assertEqual(display("2^(n/2)", N), "2^(n/2)")
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest tests.test_answer_check -v`
Expected: ERROR, `ModuleNotFoundError: No module named 'answer_check'`.

- [ ] **Step 3: Implement `mcp/answer_check.py`**

A tokenizer turns the text into numbers, names, operators and brackets (Unicode `π √ × · − ∞` mapped first; `√` becomes `sqrt` applied to the next factor). Letter runs are split greedily: a function name followed by `(`, then `pi`/`e`/`inf`, then the longest declared variable; leftover letters raise the unknown-name error. Implicit `*` is inserted between a number, name, `)` or `!` and a following number, name, function or `(`. `^` becomes `**`; postfix `!` becomes `fact(…)` around the preceding factor; `C(` becomes `binom(`. Bracket and trailing-operator errors are detected on the tokens, so their messages are the spec's. The rewritten string goes to `ast.parse(mode="eval")`, then a walker refuses any node outside the spec's whitelist. `evaluate` walks the tree in floats, catching `ZeroDivisionError`, `OverflowError`, `ValueError` and complex results as `None`; `fact` uses `math.factorial` for integral arguments up to 170 and `math.gamma(x+1)` otherwise; `binom` uses `math.comb` for integral arguments, else gamma. `display` renders from the tree: `−` for minus, juxtaposition for a number times a name or bracket, superscripts when every character of the rendered exponent is in a superscript table (reuse `latex_text.SUP`), else `^(…)`.

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m unittest tests.test_answer_check -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add mcp/answer_check.py tests/test_answer_check.py
git commit -m "answer_check: read, show and compare typed answers"
```

---

### Task 2: typed records in `hooks/quiz_block.py`

**Files:**
- Modify: `hooks/quiz_block.py` (`_outcome`, `render`)
- Test: `tests/test_quiz_block.py`

**Interfaces:**
- Consumes: the typed record of the spec, plus `"decimal": bool`.
- Produces: `render(r)` handles `r.get("mode") == "typed"`; header, kinds, titles and folding unchanged, so `parse` is unchanged.

- [ ] **Step 1: Write the failing tests** (new class `TypedRender` in `tests/test_quiz_block.py`):

```python
TYPED = {"mode": "typed", "status": "answered", "question": "Expected tosses to get $n$ heads in a row?",
         "details": "", "answer": "2^(n+1)-2", "answerLatex": "2^{n+1}-2", "variables": {"n": "int 1..12"},
         "exact": False, "wrongAnswers": [{"answer": "2^n", "why": "Counted only the last run."}],
         "explanation": "Condition on the first tail.", "typed": "2^n", "decimal": False,
         "correct": False, "dontKnow": False, "matchedWrong": 0, "note": ""}

def test_incorrect_with_common_mistake(self):
    out = quiz_block.render(TYPED)
    self.assertTrue(out.startswith("> [!failure|quiz]- ✗ Expected tosses to get $n$ heads in a row?"))
    self.assertIn("> Your answer: `2^n`\n> Correct answer: $2^{n+1}-2$", out)
    self.assertIn("> Common mistake: Counted only the last run.", out)
    self.assertEqual(quiz_block.parse(out.split("\n"))["outcome"], "✗")
def test_correct_decimal_shows_exact_value(self):
    r = {**TYPED, "answer": "1/3", "answerLatex": "\\frac{1}{3}", "typed": "0.333", "decimal": True,
         "correct": True, "matchedWrong": None, "variables": {}, "wrongAnswers": []}
    out = quiz_block.render(r)
    self.assertIn("> Your answer: `0.333`\n> Exact value: $\\frac{1}{3}$", out)
    self.assertNotIn("Exact value", quiz_block.render({**r, "typed": "1/3", "decimal": False}))
def test_dont_know(self):
    out = quiz_block.render({**TYPED, "typed": "", "dontKnow": True, "matchedWrong": None})
    self.assertTrue(out.startswith("> [!info|quiz]- ? "))
    self.assertIn("> Correct answer: $2^{n+1}-2$", out)
def test_answer_without_latex(self):
    self.assertIn("Correct answer: `2^(n+1)-2`", quiz_block.render({**TYPED, "answerLatex": ""}))
def test_backtick_removed(self):
    self.assertIn("Your answer: `2^n`", quiz_block.render({**TYPED, "typed": "2`^n"}))
def test_pending_leaks_nothing(self):
    out = quiz_block.render({**TYPED, "status": "pending"})
    self.assertTrue(out.startswith("> [!question|quiz]+ "))
    for leak in ["2^{n+1}", "2^n", "Counted", "Condition", "Correct answer"]:
        self.assertNotIn(leak, out)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest tests.test_quiz_block -v`
Expected: the new tests FAIL (`KeyError: 'options'`).

- [ ] **Step 3: Implement** a typed branch in `_outcome` and `render`: no options part; outcome lines exactly as the spec's "The note" section; the correct answer is `$<answerLatex>$` when non-empty, else `` `<answer>` ``; the learner's text has backticks removed. Options rendering stays as is.

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m unittest tests.test_quiz_block tests.test_mirror_quiz -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add hooks/quiz_block.py tests/test_quiz_block.py
git commit -m "quiz_block: render typed-answer quizzes"
```

---

### Task 3: typed mode in `mcp/quiz_server.py`

**Files:**
- Modify: `mcp/quiz_server.py` (`TOOL`, `run_quiz`, `save_last_asked`, `ask_via_tmux`, `ask_via_elicitation`)
- Test: `tests/test_quiz_typed.py`

**Interfaces:**
- Consumes: Task 1's `answer_check` functions; Task 2's `render`.
- Produces: the popup spec for a typed quiz: `{"mode": "typed", "question", "details", "figure", "explanation", "answer", "variables", "exact", "wrongAnswers", "answerDisplay", "dontKnow"}`, where `answerDisplay` is `latex_text.render("$" + answerLatex + "$")` when given, else `answer_check.display(answer)`. Popup result: `{"action": "accept", "typed": str, "dontKnow": bool, "note": str}` or the existing `ask`/`cancel`.

- [ ] **Step 1: Write the failing tests** in `tests/test_quiz_typed.py`, copying the stub set-up and the `headers()` helper of `WritesOneBlock` in `tests/test_quiz_examples.py` (`log_file`, `tmux_available=False`, `set_target`, `ask_via_elicitation`, `LAST_ASKED`, `QUIZ_LOGGED`):

```python
ARGS = {"question": "Expected tosses to get $n$ heads in a row?", "answer": "2^(n+1)-2", "answerLatex": "2^{n+1}-2",
        "variables": {"n": "int 1..12"}, "wrongAnswers": [{"answer": "2^n", "why": "Counted only the last run."}],
        "explanation": "Condition on the first tail."}

def test_validation_errors(self):
    for change, msg in [({"options": [{"label": "1"}, {"label": "2"}]}, "give either answer or options, not both"),
                        ({"answer": "2^(n+1"}, "answer: can't read: unclosed bracket"),
                        ({"variables": {}}, "answer: unknown name: n"),
                        ({"variables": {"n": "int 5..1"}}, 'n: bad range "int 5..1"'),
                        ({"answer": "1/(n-n)"}, "answer is undefined at most points of the ranges"),
                        ({"wrongAnswers": [{"answer": "2(2^n-1)", "why": "x"}]}, "wrong answer 2(2^n-1) is equivalent to answer"),
                        ({"wrongAnswers": [{"answer": "2^(", "why": "x"}]}, "wrong answer 2^(: can't read"),
                        ({"multiSelect": True}, "multiSelect, correctAnswer and shuffle belong to the options mode")]:
        out = quiz_server.run_quiz({**ARGS, **change}, "toolu_1")
        self.assertTrue(out.get("isError"), change)
        self.assertIn(msg, out["content"][0]["text"])
def test_correct(self):
    self.ui = [{"action": "accept", "typed": "2*2^n-2"}]
    text = quiz_server.run_quiz(dict(ARGS), "toolu_1")["content"][0]["text"]
    self.assertTrue(text.startswith("User answered correctly.\nTyped: 2*2^n-2 (reads as "))
    self.assertEqual(self.headers(), ["> [!success|quiz]- ✓ Expected tosses to get $n$ heads in a row?"])
def test_matched_wrong(self):
    self.ui = [{"action": "accept", "typed": "2^n"}]
    text = quiz_server.run_quiz(dict(ARGS), "toolu_1")["content"][0]["text"]
    self.assertIn("User answered incorrectly.", text)
    self.assertIn("Correct: 2^(n+1)-2", text)
    self.assertIn("Matched common mistake: Counted only the last run.", text)
    record = json.loads(text.split("QUIZ_JSON: ", 1)[1])
    self.assertEqual((record["mode"], record["matchedWrong"], record["decimal"]), ("typed", 0, False))
def test_decimal(self):
    self.ui = [{"action": "accept", "typed": "0.333"}]
    args = {"question": "P(A)?", "answer": "1/3", "explanation": "Symmetry."}
    self.assertIn("(decimal, matched to 3 significant figures)", quiz_server.run_quiz(args, "toolu_1")["content"][0]["text"])
def test_dont_know(self):
    self.ui = [{"action": "accept", "typed": "", "dontKnow": True}]
    self.assertIn("User answered \"I don't know\"", quiz_server.run_quiz(dict(ARGS), "toolu_1")["content"][0]["text"])
def test_unreadable_from_fallback_form(self):
    self.ui = [{"action": "accept", "typed": "2^("}]
    text = quiz_server.run_quiz(dict(ARGS), "toolu_1")["content"][0]["text"]
    self.assertIn("User answered incorrectly.", text)
    self.assertIn("could not be read: can't read: unclosed bracket", text)
def test_reask_after_question(self):
    self.ui = [{"action": "ask", "question": "Is n fixed?"}, {"action": "accept", "typed": "2^(n+1)-2"}]
    quiz_server.run_quiz(dict(ARGS), "toolu_1")
    quiz_server.run_quiz(dict(ARGS), "toolu_2")
    self.assertEqual(self.headers(), ["> [!note|quiz]- Asked first: Expected tosses to get $n$ heads in a row?",
                                      "> [!success|quiz]- ✓ Expected tosses to get $n$ heads in a row?"])
def test_other_question_is_not_a_reask(self):
    self.ui = [{"action": "ask", "question": "Is n fixed?"}, {"action": "accept", "typed": "1/3"}]
    quiz_server.run_quiz(dict(ARGS), "toolu_1")
    out = quiz_server.run_quiz({"question": "P(A)?", "answer": "1/3", "explanation": "x"}, "toolu_2")
    self.assertFalse(json.loads(out["content"][0]["text"].split("QUIZ_JSON: ", 1)[1])["reask"])
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest tests.test_quiz_typed -v`
Expected: FAIL (`quiz needs at least two options`).

- [ ] **Step 3: Implement.** In `run_quiz`, branch to a new `run_typed(args, tool_use_id)` when `"answer" in args`; it does the spec's validation in the order of the test table (the error text is `"quiz error: " + message`, via `err`), writes the pending block, asks through `ask_via_tmux` or `ask_via_elicitation`, marks with `answer_check.check` / `matches_wrong` (an `AnswerError` from the learner's text: incorrect, with `could not be read: <error>`), and builds the result text and record of the spec. Keep the shared steps (pending block, `mark_logged`, the ask/cancel paths, the seen-feedback lines) in helpers both modes call rather than duplicating them. `save_last_asked` stores `{"typed": question}` for a typed quiz; the re-ask test for a typed call is `prev.get("typed") == question`. `ask_via_tmux` writes the typed popup spec of the Interfaces block when `record["mode"] == "typed"`, and sizes the popup from the question, details and explanation. `ask_via_elicitation` gives a typed quiz the schema `{"answer": string "Your answer", "dk": boolean "I don't know", "note": string}`. Add a paragraph and an example call for the typed mode to `TOOL["description"]`, and the five fields of the spec to `inputSchema` (`required` becomes `["question", "explanation"]`; the options-mode checks stay in `run_quiz`).

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: all PASS, including the existing `test_quiz_examples`.

- [ ] **Step 5: Commit**

```bash
git add mcp/quiz_server.py tests/test_quiz_typed.py
git commit -m "quiz server: typed-answer mode"
```

---

### Task 4: typed mode in `mcp/quiz_popup.py`

**Files:**
- Modify: `mcp/quiz_popup.py` (docstring, `main`)
- Test: `tests/test_quiz_popup_typed.py`

**Interfaces:**
- Consumes: Task 3's typed popup spec and result; Task 1's `display`, `is_decimal`, `check`, `matches_wrong`.
- Produces: `typed_status(text: str, spec: dict) -> tuple[bool, str]` — `(True, "reads as: …")`, `(False, "<error>")`, or `(False, "")` for empty text.

- [ ] **Step 1: Write the failing test**

```python
SPEC = {"mode": "typed", "answer": "2^(n+1)-2", "variables": {"n": "int 1..12"}, "exact": False}
def test_typed_status(self):
    self.assertEqual(quiz_popup.typed_status("2^(n+1)-2", SPEC), (True, "reads as: 2ⁿ⁺¹ − 2"))
    self.assertEqual(quiz_popup.typed_status("(1+2", SPEC), (False, "can't read: unclosed bracket"))
    self.assertEqual(quiz_popup.typed_status("0.5", {**SPEC, "exact": True}), (False, "give the exact form, not a decimal"))
    self.assertEqual(quiz_popup.typed_status("  ", SPEC), (False, ""))
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_quiz_popup_typed -v`
Expected: FAIL, `AttributeError: ... 'typed_status'`.

- [ ] **Step 3: Implement** `typed_status`, and a typed branch of `main` (a separate `main_typed(stdscr, spec, out_path)` called from `main` when `spec.get("mode") == "typed"`, sharing `write`, `addline`, `wrap_keep_bold`, the note and ask-first editing). Layout and keys exactly as the spec's popup section; the cursor is visible in the field (`curses.curs_set(1)` while it has focus). Enter on the field submits only when `typed_status` is `(True, …)`. The feedback screen: `✓ Correct.` (plus `Exact value: <answerDisplay>` for a correct decimal) / `✗ Incorrect.` / `No guess made.`, then `Your answer: <display>`, `Correct answer: <answerDisplay>`, `Common mistake` and its `why` when `matches_wrong` finds one, then the explanation. Update the module docstring's spec, result and keys.

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest tests.test_quiz_popup_typed -v`
Expected: PASS.

- [ ] **Step 5: Test by hand in tmux.** Write a typed spec to `/tmp/claude-…/scratchpad/spec.json` and run `tmux display-popup -E -w 85% -h 20 python3 mcp/quiz_popup.py spec.json out.json`. Check: typing and editing with ←/→/Home/End/Delete; the preview on every key; Enter refused on `(1+2` and on a decimal with `exact`; ↓ then Enter gives `dontKnow`; `?` opens ask-first; Tab edits the note; `q` and `f` type into the field; Ctrl-F opens the figure; Esc cancels; the feedback screen for correct, decimal, wrong, matched-wrong. Read `out.json` after each.

- [ ] **Step 6: Commit**

```bash
git add mcp/quiz_popup.py tests/test_quiz_popup_typed.py
git commit -m "quiz popup: typed-answer field with live preview"
```

---

### Task 5: skills and docs

**Files:**
- Modify: `skills/teach/SKILL.md` (Tools list, "Writing quiz options", Phase 3 step 4, Resuming step 2)
- Modify: `README.md` (Quizzes)
- Modify: `docs/architecture.md` (The quiz tool)

- [ ] **Step 1: Teach skill.** As the spec's "The skills and the docs" section: in step 4, an Apply whose result is a number or a formula is a typed quiz with `answer`, `variables`, `answerLatex` and two or three `wrongAnswers` with `why`; a claim, choice of method or conclusion stays multiple choice; `exact` only when the exact form is tested; the check stays multiple choice. In the recall check, typed where the answer is a value or a formula. In "Writing quiz options", one line on building wrong answers the same way. In the Tools list, one clause that `quiz` also takes a typed answer.
- [ ] **Step 2: README.** A `### Typed answers` subsection under Quizzes: what can be typed (the spec's table, condensed), the preview line, the three-significant-figure rule, the keys that differ from multiple choice. Present tense, no history.
- [ ] **Step 3: Architecture.** In "The quiz tool": the typed mode, `answer_check.py` and the whitelisted AST, the seeded points, the popup's typed mode and why the server marks again.
- [ ] **Step 4: Verify.** Run `python3 -m unittest discover -s tests -v` (all PASS) and `grep -n "typed" skills/teach/SKILL.md README.md docs/architecture.md` shows each section.
- [ ] **Step 5: Commit**

```bash
git add skills/teach/SKILL.md README.md docs/architecture.md
git commit -m "Docs and teach skill: typed answers for value and formula applies"
```
