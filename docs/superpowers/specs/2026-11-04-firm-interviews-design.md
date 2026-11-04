# Firm interviews — design

Date: 2026-11-04. Status: agreed in conversation ("fast PRs": no plan document).

## Purpose

The learner sits quant research assessments at SIG and Marshall Wace in two weeks, and studies several courses side by side (Blitzstein & Hwang, Wasserman, Strang, the Green book). A real round mixes probability, statistics, linear algebra and brainteasers, so a mock round on one course is too narrow. This piece lets `/interview` draw on every course, and adds firm profiles that set the mix, the number of problems, the time and the interviewer's style.

## Scope across courses

`interview.py new [--courses gb,bh]` draws on the finished units (done or shaky) of the named courses; with no `--courses`, of every course that has a finished unit. A named course with nothing finished is refused.

**Where a round lives.** A round on one course stays where rounds always were: `courses/<slug>/interviews/` and `courses/<slug>/.interviews/`, named `<slug>-interview-<n>`. A round on two or more courses lives at the vault root: `interviews/mixed-interview-<n>.md`, with its files in `.interviews/`. The name keeps the `<prefix>-interview-<n>` shape, so the scans in `practice.py` and `technique.py` read it once their glob includes the vault's `.interviews/` (one shared helper, `technique.interview_state_files`). Old rounds, old pointers (`{"course": …}`) and old state files without the new fields read as before.

**Units.** In a cross-course round a unit is named `<slug>:<id>` (`bh:2.4`), because ids collide across books. The state records the round's courses and its allowed units at `new`, and `check` validates against that list. `INTERVIEW MISSES` in the resume brief also reads the newest finished cross-course round, keeping the misses whose first unit is in the note's course and chapter.

**One open round anywhere.** `new` refuses while any round in any course or the vault is open. `list` shows every round, in every course and the vault.

## Firm profiles

`--profile` replaces `--length`. Each profile fixes the problem count, the time, the topic weights, the marking (written tests) and a few `STYLE` lines for the interviewer.

| Profile | Mode | Problems | Time | Mix (weights) |
|---|---|---|---|---|
| `sig` | live | 3 | 20 min each | probability 85, statistics 10, regression 5 |
| `mw` | live | 3 | 20 min each | brainteasers 2, regression 1 |
| `sig-oa` | written | 17 | 60 min | probability 6, statistics 4; +1 right, 0 wrong, 0 blank; calculator |
| `mw-oa` | written | 18 | 60 min (`--minutes`) | probability 7, statistics 3, regression 3, linear algebra 3, calculus 2; +2 right, −1 wrong, 0 blank |

The evidence is weak (prep sites, Glassdoor snippets), so the numbers live in one table in `interview.py`, easy to change.

**Topics.** Units carry a topic, one of `probability`, `statistics`, `regression`, `linear algebra`, `calculus`, `brainteasers`, `other`. A course's state holds `topics: {"*": "probability", "3": "calculus", "3.5": "linear algebra"}`; a unit's topic is its own entry, else its chapter's, else the course's `*`. The model tags with `interview.py topic <course> <topic> <chapter | unit | *>…`. A profile round refuses to plan while a finished unit in scope has no topic, and lists them on `UNTAGGED:` lines; a round without a profile needs no tags.

**The mix.** The weights are restricted to the topics that have a finished unit, and each gets `floor(n·w/W)` problems; the slots left over go to topics drawn by their remainders, with a random generator seeded by the round's name. So `mw-oa` is exactly 7/3/3/3/2 when every topic is finished, and a `sig` round has a statistics problem about a third of the time. `new` prints `MIX:` and the units grouped by topic; every problem has a `topic`, the counts must equal the mix, and at least one of a problem's units must have that topic.

## Written tests: hosted by `/interview`, not `/exam`

The written tests (`sig-oa`, `mw-oa`) are sat in Obsidian and scored as a whole, like an exam, but they are hosted by `interview.py`:

- `exam.py` is built around one note: the paper sits beside the chapter note it covers, questions cite that note's sections, written answers are marked by the model, and the result changes the course's unit statuses. A cross-course paper fits none of this, and short exact answers would need a new auto-marked question type and negative marking.
- `interview.py` already has, after the change above, cross-course scope, a problem file whose answers `answer_check` reads, the clock and status bar, `list`, and the scans into `/review` and technique notes. A written mode adds a paper and a `submit` command.

**The flow.** `start` writes the paper (`### Problem n`, the statement, an `**Answer:**` line), starts the round clock and the status bar, and the reply is one line linking the paper. The hook line reads `INTERVIEW: written test, 18 problems · 23:10 of 60:00`, with `TIME UP` once the time is spent. `submit` reads each answer (a number or a formula; `$` signs are dropped). If an answer cannot be read, it lists those problems and records nothing, so the learner can fix the form. Otherwise it checks each answer with `answer_check`, counts right, wrong and blank, and computes the score from the profile's marking: `right·R + wrong·W + blank·B`. The script does this, never the model. A right answer is the outcome `solved`; a wrong or blank one is `unsolved`, so `/review` and technique notes treat it as a miss. `finish --marks` appends the result: the score, a table (result, your answer, the answer, topic, technique), optional comments on problems, things to work on, sections to revisit, and the solutions, folded. Time over the limit is shown. The test is not cut off.

Written problems have no hints or follow-ups; `hint`, `answer` and `next` refuse in a written round, and `stop` is `submit`.

## Problems

New problems, as before: not a book exercise, a worked example or a lesson quiz the learner has seen, and verified by running code. They use the vault's shared notation sheet `Notation.md` (one line in the skill). In a live profile round, the follow-up follows the `STYLE` lines (SIG: generalise and ask for a sanity check; MW: ask for the model's assumptions after the regression problem).

## Testing

`tests/test_interview.py`: scope and storage (one course, several, `--courses`, refusals); a full cross-course round with `list`, the resume brief, `practice.py scan` and `technique.py sync`; an old-format pointer; topic tags, `UNTAGGED`, the mix allocation and its check; written tests: the paper, the hook line, unreadable answers, exact negative-marking scores, the result, refusals of live-only commands.

## Out of scope

Multiple-choice questions in written tests; per-problem time limits in written tests; scoring a research discussion.
