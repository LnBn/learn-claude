# Mental arithmetic — design

Date: 2026-10-24. Status: approved in conversation, awaiting spec review.

## Purpose

Trading-firm screens test arithmetic speed: a timed sprint of additions, subtractions, multiplications and divisions (the Zetamac test is the common benchmark), often with fractions, percentages and estimates. The skill is speed, so it cannot go through the model one question at a time. A small timed program in a tmux popup generates the questions, checks every keypress, keeps time and records how long each kind of question takes; the model starts it and reports afterwards.

This is the fifth and last of the planned pieces (typed answers, mock interview, technique notes, practice, mental arithmetic).

**Agreed in the design conversation:**

- Content: the Zetamac core plus quant extras (fractions ↔ decimals and percentages, squares and powers, estimates); one mode per sprint.
- Sprints are uniformly random, so scores are comparable over time and with the standard test. A separate `weak` mode draws mostly from the learner's slowest kinds of question.
- Approach: a standalone program (`hooks/arith.py`) run in a tmux popup; the skill opens it, waits, and reports from the summary it prints.

**Assumed and not contradicted:** arithmetic misses do not become review cards and do not touch technique notes; Zetamac's input style (a correct answer advances without Enter).

## Modes

`/arith [mode] [seconds]`, mode `core` by default, 120 seconds by default.

| Mode | Questions | Answer |
|---|---|---|
| `core` | Zetamac's default ranges: addition `a + b`, `a, b ∈ [2, 100]`; subtraction as addition reversed (`(a + b) − a`); multiplication `a × b`, `a ∈ [2, 12]`, `b ∈ [2, 100]`; division as multiplication reversed (`(a × b) ÷ a`). One of the four at random. | exact integer |
| `fractions` | fraction to decimal `n/d`, `d ∈ {2..12, 16, 20, 25, 40}`, `1 ≤ n < d`, answers to at most 4 decimal places (repeating decimals such as 1/3 are typed to 4 places, rounded: `0.3333`); percent of `p% of y`, `p ∈ {5, 10, 12.5, 15, 20, 25, 30, 40, 75}`, `y` a multiple of 4 in `[20, 800]` chosen so the answer has at most one decimal place | exact decimal |
| `powers` | squares `n²`, `n ∈ [11, 30]`; powers of two `2^k`, `k ∈ [5, 20]`; cubes `n³`, `n ∈ [2, 12]` | exact integer |
| `estimate` | `a × b` with `a, b ∈ [12, 999]`, at least one of them 3-digit; `a ÷ b` with `a ∈ [100, 9999]`, `b ∈ [3, 99]` | any number within 2% of the true value, submitted with Enter |
| `mixed` | each question from `core`, `fractions`, `powers` or `estimate` at random | as its kind |
| `weak` | 70% from the learner's five slowest kinds (below), 30% uniform from `mixed` | as its kind |

## Kinds of question

Every question has a kind, the unit the learner's speed is measured in:

- core: `+ carry` / `+ no carry` (a carry in the units digit), `− borrow` / `− no borrow`, `× <a>` (the 2–12 factor: `× 7`), `÷ <a>`
- fractions: `/<d>` (the denominator: `/16`), `<p>% of`
- powers: `square 1x` / `square 2x` (n in 11–19 / 20–30), `2^k`, `cube`
- estimate: `≈ ×`, `≈ ÷`

A kind's **speed** is the median time to a correct answer over its last 50 questions in any sprint. `weak` mode picks the five kinds whose median is highest relative to the median of all kinds that come from the same mode (so a fraction is not compared with an addition); with fewer than 10 recorded questions of a kind, that kind is not ranked. With fewer than five ranked kinds, `weak` uses the ranked ones and fills the rest uniformly.

## The popup

```
  ARITHMETIC · core                              score 14 · 1:12

                     73 × 6 = 43█

  type the answer · Tab skip · Esc stop
```

- Keys: digits, `.`, `-`, Backspace. **A typed answer that equals the exact answer advances at once**, with no Enter; a wrong one just does not advance until it is corrected. In `estimate` (and an estimate question in `mixed` or `weak`), Enter submits, and an answer within 2% counts; a wrong estimate flashes `not within 2%` and stays.
- The check runs on every keypress and is numeric (`.375` equals `0.375`). An integer answer advances when the typed value equals it. A decimal answer advances when the typed value equals it and the typed text has at least as many decimal places as the answer's shortest form, so `0.37` never advances for `0.375`, and `0.5` advances for `0.5` without waiting for a second digit.
- **Tab** skips (counted as skipped, no time recorded). **Esc** stops: the sprint is recorded as partial and does not count for best and average.
- The clock starts with the first question and the sprint ends at 0:00; the question on screen then is not counted.
- **End screen:** the score; best and average of the last 5 complete sprints in this mode; the three slowest kinds of this sprint with their median times; `press any key`.

The popup is `tmux display-popup -E -w 70 -h 14`; the result is written to the history file before the popup closes.

## History

`<vault>/practice/.arith.json`:

```json
{"sprints": [{"date": "2026-10-24", "time": "14:02", "mode": "core", "seconds": 120, "complete": true,
              "score": 38, "skipped": 1, "questions": [{"kind": "× 7", "ms": 1830}]}]}
```

`questions` holds every question answered correctly (with its time from display to the advancing keypress, or to Enter for an estimate).

## The script: `hooks/arith.py`

```
arith.py run [mode] [--seconds 120]     open the popup (tmux), wait for it to close, print the summary
arith.py play [mode] [--seconds 120]    the sprint itself, in the current terminal (the popup runs this)
arith.py last                           the summary of the newest sprint
arith.py history [mode]                 the last 10 complete sprints per mode, best and average
arith.py kinds [mode]                   every ranked kind's median time, slowest first
```

**Summary** (printed by `run` and `last`):

```
ARITHMETIC: core · 120 s · score 38 (1 skipped)
BEST: 41 · LAST 5 AVERAGE: 36.4
SLOWEST: × 7 2.4 s · − borrow 2.1 s · ÷ 8 1.9 s
```

`run` outside tmux prints `NO TMUX: run "python3 .claude/hooks/arith.py play <mode>" in another terminal, then /arith last` and exits 0.

## The skill: `skills/arith/SKILL.md`

`/arith [mode] [seconds]`, `/arith last`, `/arith history [mode]`:

1. `python3 .claude/hooks/arith.py run <mode> [--seconds <n>]`, called with a Bash timeout of 600000 ms: a 120-second sprint and its end screen take longer than the default two minutes.
2. On `NO TMUX`, relay the line and stop.
3. Link today's practice note (`practice/YYYY-MM-DD.md`, `--from-now`) and write `### Arithmetic — <mode>`, then two or three sentences from the summary: the score, how it compares with the best and the recent average, the slowest kinds, and — when one kind is clearly slow — a concrete tip for it (e.g. for `× 7`: 7 × n = 5n + 2n). No other content.
4. `last` and `history` show the command's output.

## Files

- `hooks/arith.py` (new), `skills/arith/SKILL.md` (new).
- `settings.json`: `Bash(python3 .claude/hooks/arith.py *)`.
- README: a `Mental arithmetic` section in `Practice`; `docs/architecture.md`: the program, the history, kinds and weak mode, why it runs outside the model.

## Testing

- `tests/test_arith.py`:
  - generators: every mode's questions within its ranges over many seeds; answers exact (fractions to 4 places, percents to one decimal); each question's kind; subtraction and division as reversed addition and multiplication (no negative or fractional core answers).
  - acceptance: integer advance on the value; decimal advance only at full precision (`0.37` does not advance for `0.375`, `0.375` does, `.375` does); estimate within and outside 2%; Tab skip; partial sprints excluded from best and average.
  - weak mode: from a fabricated history, the five slowest kinds (relative within their mode) get about 70% of the questions; unranked kinds (< 10 questions) excluded; fill when fewer than five.
  - summary, `last`, `history`, `kinds` output; `run` outside tmux.
- The popup driven by hand in a detached tmux session (`send-keys`, `capture-pane`) with a 10-second sprint: auto-advance, a wrong answer that does not advance, Tab, Esc, an estimate with Enter, the end screen, the history written.

## Out of scope

- Market-making or sequence questions; word problems.
- Comparison with other people's scores (the summary compares only with the learner's own).
- Sound, colour themes, a configurable range editor.
