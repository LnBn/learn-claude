# Confidence and practice rules — design

Date: 2026-11-04. Status: requested by the learner; built in one pass ("fast PRs"), no separate plan. The ideas follow Eero Alvar's learnharness; the text and code here are this repo's own.

## Purpose

The learner sits quant research assessments in two weeks and practises daily with `/drill`, `/review`, problem courses and `/interview`. Two signals are missing. A verdict alone does not say whether a right answer was known or guessed, or whether a wrong one was a slip or a firm belief. And hints, misses and retests are handled loosely: a hint count says nothing about how much was given away, a miss has no kind, and a missed drill problem is never asked again in the drill.

## Confidence

- **Popup.** After an answer (both modes, not "I don't know"), a screen asks *How sure are you?* Keys 1–5 give 20, 40, 60, 80, 100%, with labels from "a guess" to "certain". Five keys are enough to separate the four cases below, and match the thresholds (≤ 40, ≥ 80) exactly. A single-choice question shows the chance of a blind guess. Esc goes back to the question with the answer kept; Esc on the question still cancels. The feedback screen adds "You were 80% sure." `result.json` gains `confidence`.
- **Server.** Validates 0–100; the record gets `confidence`; the result gets `Confidence: 80%`, plus a note when a single-choice answer is at or below chance. The elicitation fallback has an optional enum field.
- **Note.** `quiz_block.render` ends the outcome paragraph with `Confidence: 80%`; `parse` returns `confidence` or `None`, so old blocks read as before.
- **Teach skill.** *Reading confidence* (after the option rules): right+sure solid; right+unsure one reinforcing touch; wrong+sure a misconception, probed and re-taught around; wrong+unsure a small correction; at or below chance, a distrusted pick. Phase 1a's binary-search bullet becomes *Open high, then binary-search*: open near the hardest thing the goal needs, let a miss walk down, jump by confidence, never descend into bracketed territory. Merged into the existing bullet, not a new list.

## Cards

- **Fragile cards.** A `✓` block at ≤ 40% becomes a card with `fragile: true`, due 3 days after the quiz. A right answer above 40% retires it; a wrong one makes it an ordinary card. A miss with the same key wins over a fragile answer in one scan.
- **Refinement (why).** `result` takes `--confidence`. A right answer at ≤ 40% in a review is the same weak evidence as in a lesson, so it keeps a fragile card for another 3 days and holds an ordinary card at its step. Practice notes are not scanned, so this is the only place a review's confidence can act.
- **Order.** `due` sorts misconception cards first, then confident misses (≥ 80%, not fragile), then due date. A wrong `result` stores `miss` and `confidence` on the card; a right one clears them, so a repaired card loses its priority.

## Practice rules (teach skill, one shared section)

Referenced by drill, review, interview, exam, exercise and problem books, as the repo already does for the option rules and the transfer rule.

- **Checked problems.** Solve, run code, hunt for a route past the target method; fix or replace.
- **Fresh surfaces.** A retry never reuses the setting.
- **Hint levels 0–5** (skipped given, kind of pattern, family of methods, result named, move outlined, step worked), one per request, from the first break in the reasoning; a wrong method gets a nudge to check its assumption; clarifying the problem is free.
- **Kinds of miss:** `recall`, `method`, `execution`, `careless`, `misconception`. A misconception gets small targeted nudges, not a re-taught lesson.

## Records

| Where | Command | Stored |
|---|---|---|
| Problem course | `book.py attempt <n> --hint <level>`; `--result unsolved --miss <kind>`; `--transfer missed --miss <kind>` | `hints` (count), `level` (highest), `miss`, `transfer_miss`; all moved to `history` on a new attempt |
| Exercise | `book.py exercise <id> --hint <level>` | `level` |
| Interview | `interview.py hint [--error] --level <level>` | `level` on the hint; `CLOSED` prints the highest |
| Drill | `drill-result … [--miss <kind>] [--hint <level>] [--confidence N]` | on the slot; `--miss` required when a part is wrong |
| Review | `result <card> right\|wrong [--miss <kind>] [--confidence N]` | in the history; `--miss` required when wrong |

- **Shaky** (problem course): unsolved, `level` ≥ 3, or transfer missed. A record without `level` (old, or a bare `--hint`) keeps the old rule, two or more hints. Outcome lines read `solved with hints (up to level 2)`; old records read `solved with 2 hints`.
- Old exercise records hold a rung in `hints`; they print as `up to rung N (old ladder)`.
- Technique notes show the kind after a problem-course miss: `✗ — method miss`.

## Drills

- **Demands.** Each slot gets the first of recall → discrimination → composition its technique has not met cleanly (named and solved, hint level < 3); strong techniques count recall as met. A discrimination slot gets a near twin (most confused with it in earlier drills, else a wrong option), placed among the wrong options. The skill adds the reverse and weaken-a-premise templates.
- **Interleaving.** The shuffle is repeated until no technique comes twice in a row.
- **Retests.** `drill-retests <id>` lists slots missed or hinted at level ≥ 3; each gets a new problem in a new setting, recorded with `drill-retest <id> <slot> right|wrong`. `drill-summary` adds `retests r/k` and the kinds of miss. The name-then-solve scoring is unchanged.

## Not changed

Exam and interview scoring, the scan's sources, intervals, lesson quizzes' miss kinds (lessons classify misses in prose, as before), the resume brief.
