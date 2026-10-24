# Typed answers — design

Date: 2026-10-24. Status: approved in conversation, awaiting spec review.

## Purpose

Every graded quiz today is multiple choice. With four options on the screen, the learner can often work backwards: check which value fits, or rule out the implausible ones. An interview gives no options. After this change a quiz can instead ask for a typed answer, a number or a formula, which the quiz server marks the moment the learner presses Enter, as it marks a choice now.

This is the first of five planned pieces (typed answers, mock interview, technique notes, practice with `/drill` and `/review`, mental arithmetic). The drill and review modes will use typed answers.

**Said by the learner:** the goal of the gb course is to solve unseen problems fast and explain the reasoning out loud; the system is useful; build typed answers first.

**Agreed in the design conversation:**

- Answers may be numbers, fractions, constants, and formulas in named variables such as $n$ or $p$.
- A decimal counts as correct if it matches the exact value to three significant figures (0.333 for $1/3$, not 0.33). The teacher can demand the exact form on a question where that is the point.
- The quiz server checks the answer itself, with a module written on the standard library. Two formulas are compared by evaluating both at random points. No sympy, no model marking.
- In a lesson, the Apply question is typed when its result is a number or a formula. The Check stays multiple choice. Exams do not change.

**Assumed and not contradicted:** the fallback quiz protocol (no MCP server) stays multiple choice; `ask_user_question` and code tasks are untouched.

## The checker: `mcp/answer_check.py`

Standard library only, imported by both `quiz_server.py` and `quiz_popup.py`. Three jobs: read an answer, show it, compare two answers.

### What it reads

| Form | Examples |
|---|---|
| numbers | `14`, `0.518`, `.5` (no scientific notation: `2e` is $2e$) |
| operators | `+ - * / ^ **`, unary minus, brackets `( )` |
| implicit multiplication | `2n`, `2(n+1)`, `(n+1)(n+2)`, `3pi`, `np` (when $n$ and $p$ are both variables) |
| factorial | `n!`, `(2n)!` |
| functions | `sqrt`, `ln`, `log` (natural), `log2`, `log10`, `exp`, `abs`, `binom(n,k)` and its alias `C(n,k)` |
| constants | `pi`, `e`, `inf` |
| Unicode | `π`, `√` (applies to the next factor: `√2`, `√(n+1)`), `×`, `·`, `−`, `∞` |

Variables are the names the question declares (see the tool, below). A run of letters is read greedily: a function name followed by `(`, then a constant, then a declared variable; anything left over is an error naming it (`unknown name: m — this question's variables are n`).

The text is first tokenised and rewritten into Python syntax (`^` to `**`, implicit `*`, `n!` to `fact(n)`), then parsed with `ast.parse(mode="eval")`. Only these nodes are accepted: `Expression`, `BinOp` with `Add Sub Mult Div Pow`, `UnaryOp` with `USub UAdd`, `Constant` (int or float), `Name` (a declared variable or a constant), `Call` of a whitelisted function with positional arguments. Anything else is refused. `eval` never runs on the text.

Errors are short and say what to fix: `can't read: unclosed bracket`, `can't read: nothing after ^`, `unknown name: m — this question's variables are n`.

### How it shows an answer

`display(text)` returns the parsed expression in Unicode for the popup's preview and feedback: `2^(n+1)-2` shows as `2ⁿ⁺¹ − 2`, `sqrt(2)/2` as `√2/2`, `binom(n,2)` as `C(n, 2)`. Superscripts are used when every character of the exponent has one; otherwise `^(…)`.

### How it compares

`check(given, expected, variables, exact=False)` returns `"correct"`, `"wrong"`, or raises `AnswerError` when `given` cannot be read.

- **Points.** With no variables there is one point. With variables, six points are drawn from the declared ranges: an `int a..b` variable takes integers in $[a, b]$; a real `a..b` variable takes values strictly inside $(a, b)$. The random generator is seeded from a hash of `expected` and the variable spec, so the popup and the server always draw the same points.
- **Evaluation.** Floats, with factorial and binomial through `math.gamma` (exact `math.factorial` / `math.comb` for integer arguments). A point where the expected value is undefined (division by zero, a domain error, overflow, a complex result) is skipped. If fewer than three points remain, the question is refused when it is set (see validation), so this never happens at answer time. A point where the given answer is undefined but the expected one is not counts as a mismatch.
- **Exact form.** If `given` contains no decimal point, it must equal `expected` within a relative tolerance of $10^{-9}$ (absolute $10^{-12}$ near zero) at every point.
- **Decimals.** If `given` contains a decimal point, at every point $|g - x| \le \tfrac12 \cdot 10^{\lfloor \log_{10}|x| \rfloor - 2}$, where $x$ is the expected value: a match to three significant figures. At $x = 0$ the tolerance is $5 \times 10^{-4}$.
- **`exact=True`.** A given answer with a decimal point is not compared. `check` raises `AnswerError("give the exact form, not a decimal")`, which the popup shows in its preview line, so Enter does nothing until the learner types an exact form.
- **Infinity.** `inf` matches only an expected value that is infinite with the same sign.

`matches_wrong(given, wrong_answers, variables, exact)` returns the index of the first entry of `wrongAnswers` that `given` is equivalent to, by the same comparison, or `None`.

## The `quiz` tool

A quiz is **typed** when the call has `answer` and no `options`. The options mode is unchanged.

| Field | Meaning |
|---|---|
| `answer` | Required for a typed quiz. The correct answer in the checker's syntax: `2^(n+1)-2`, `1/3`. |
| `variables` | Required when `answer` names a variable. An object from name to range: `{"n": "int 1..12", "p": "0..1"}`. |
| `exact` | Optional, default false. Refuse decimals. |
| `wrongAnswers` | Optional. `[{"answer": "2^n", "why": "<what that answer means went wrong>"}]`: the results of the common wrong moves, the role distractors play in a multiple-choice quiz. |
| `answerLatex` | Optional. The correct answer as LaTeX, for the note and the feedback: `2^{n+1}-2`. Without it, the note shows `answer` as inline code. |

`question`, `details`, `explanation` and `figure` work as now. `multiSelect`, `shuffle` and `correctAnswer` belong to the options mode.

**Validation**, returned as a tool error before anything is shown or written:

- both `answer` and `options` given, or neither;
- `answer` does not parse;
- a name in `answer` or in a wrong answer that is not declared in `variables`;
- a range that does not parse, or has $a \ge b$;
- fewer than three of the six points give a defined value for `answer`;
- a wrong answer that does not parse, or is equivalent to `answer`;
- `multiSelect`, `correctAnswer` or `shuffle` given with `answer`.

The tool description gains one paragraph on the typed mode, with an example call.

**Re-ask after `?`.** For a typed quiz, `quiz-last-asked.json` stores `{"typed": <question>}`. A later typed call with the same question is the re-ask: it writes the full graded block after the teacher's answer, as for options.

## The popup

`quiz_popup.py` gets a typed mode, chosen by `"mode": "typed"` in the spec. The spec carries `answer`, `variables`, `exact`, `wrongAnswers` and the display form of the correct answer, so the popup can mark the answer and show feedback itself, as it does for options.

```
 Expected tosses to get n heads in a row?

 Answer: 2^(n+1)-2▏
         reads as: 2ⁿ⁺¹ − 2

   I don't know

 Enter submit · ↓ I don't know · Tab note · ? ask first · Ctrl-F figure · Esc cancel
```

- The cursor starts in the answer field. Printable keys type; ←/→, Home/End, Backspace and Delete edit.
- The line under the field updates on every key: `reads as: …` when the checker can read it, otherwise its error (`can't read: unclosed bracket`, `give the exact form, not a decimal`). An empty field shows nothing.
- Enter on the field submits only when the line says `reads as`. Otherwise it does nothing.
- ↓ moves to the **I don't know** row and ↑ back; Enter there answers "I don't know".
- `?` asks the teacher first. `?` never occurs in an answer, so it is not typed into the field.
- Tab edits the note, as now. Ctrl-F opens the figure, since `f` is a letter the learner may type. `q` no longer cancels; Esc does.
- **Feedback:** the mark, `Your answer: 2ⁿ`, `Correct answer: 2ⁿ⁺¹ − 2` (from `answerLatex` through `latex_text.py`, else the checker's display), the `why` of a matched wrong answer under the heading `Common mistake`, then the explanation. A correct decimal also shows the exact value: `Correct. Exact value: 1/3`.

**Result:** `{"action": "accept", "typed": "<text>", "dontKnow": false, "note": "…"}`, or the existing `ask` and `cancel` results. The server marks the text again with the same seeded check; the popup's own mark is only for the feedback screen.

## The fallback form (no tmux)

The elicitation form for a typed quiz has a string field `Your answer`, a boolean `I don't know`, and the note. An answer the checker cannot read is marked wrong, and the result text says it could not be read and quotes the error, so the teacher can ask again if it was a typo.

## The record and the result

The record a typed quiz writes (and puts on the `QUIZ_JSON:` line):

```json
{"mode": "typed", "status": "answered", "question": "…", "details": "…",
 "answer": "2^(n+1)-2", "answerLatex": "2^{n+1}-2", "variables": {"n": "int 1..12"},
 "exact": false, "wrongAnswers": [{"answer": "2^n", "why": "…"}], "explanation": "…",
 "typed": "2^n", "correct": false, "dontKnow": false, "matchedWrong": 0, "note": ""}
```

The text returned to the model:

```
User answered incorrectly.
Typed: 2^n (reads as 2ⁿ)
Correct: 2^(n+1)-2
Matched common mistake: <why>
Explanation: …
```

followed by the note and the already-seen line, as now. A correct decimal adds `(decimal, matched to 3 significant figures)`.

## The note

`quiz_block.render` learns the typed record. The header, kinds, marks, titles and folding are unchanged, so `quiz_block.parse`, `lesson.py` outcomes and `md_log.py rebuild` work without change.

Body, in order:

1. the full question, when the title is not all of it;
2. `details`;
3. a non-book figure, as now;
4. the outcome lines:
   - correct: ``Your answer: `0.333` `` and, for a decimal, `Exact value: $\frac{1}{3}$`
   - incorrect: ``Your answer: `2^n` `` and `Correct answer: $2^{n+1}-2$`, then `Common mistake: <why>` if one matched
   - I don't know: `Correct answer: $2^{n+1}-2$`
   - skipped, unavailable, asked first: as now
5. the explanation;
6. the learner's note.

The correct answer is `$<answerLatex>$` when given, else `` `<answer>` ``. The learner's text is inline code, with any backtick removed. A pending typed block holds only the question, the details and the figure: nothing of the answer.

## The skills and the docs

- **`skills/teach/SKILL.md`, Phase 3 step 4 (Apply).** An Apply whose result is a number or a formula is a typed quiz: give `answer`, the `variables` and their ranges, `answerLatex`, and two or three `wrongAnswers` from the common wrong moves, each with its `why`. An Apply whose result is a claim, a choice of method or a conclusion stays multiple choice. Set `exact` only when the exact form is what is being tested. The transfer rule added on 2026-10-24 applies to both. The check stays multiple choice.
- **Recall checks** use a typed quiz where the question has a value or formula as its answer.
- **"Writing quiz options"** gets one line: in a typed quiz the wrong answers are built the same way, as the result of a specific wrong move.
- **README, Quizzes:** a short subsection on typed answers: what can be typed, the preview line, the decimal rule, the keys.
- **`docs/architecture.md`, The quiz tool:** the typed mode, the checker, the seeded points, the popup's mode.

## Testing

- `tests/test_answer_check.py`: reading every form in the table, implicit multiplication, greedy names and the unknown-name error, the refused AST nodes; equivalence of equal formulas written differently (`2^(n+1)-2`, `2*2^n-2`, `2(2^n-1)`); a wrong formula that agrees at one point but not at six; integer ranges with factorial and binomial; skipped undefined points; the decimal rule on both sides of the limit and at zero; `exact`; infinity; `matches_wrong`; the same points on two calls.
- `tests/test_quiz_block.py`: typed records in each status, the pending block leaking nothing, LaTeX and inline-code answers, the common-mistake line.
- `tests/test_quiz_typed.py`: the server's validation errors, through `run_quiz` with the UI stubbed, and the result text for correct, decimal, wrong, matched-wrong and I-don't-know answers.
- The popup is tested by hand in tmux: typing, the preview, the refused Enter, ↓ to I don't know, `?`, Tab, Ctrl-F, the feedback screen.

## Out of scope

- Exams, code tasks, the fallback quiz protocol.
- Answers that are sets, intervals, vectors or several values ("both 2 and 3"). A question with such an answer stays multiple choice, or asks for one quantity of it (the larger root, the sum).
- Symbolic simplification or showing the learner an equivalent simpler form.
- Units.
