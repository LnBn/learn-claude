# Folded quizzes — design

Date: 2026-10-23. Status: approved in conversation, awaiting spec review.

## Purpose

A lesson note should read like a chapter. Today every graded quiz puts two full callouts in the note, the question and its result. A chapter with 34 quizzes (`gb-ch02`) is mostly quiz boxes. After this change each graded quiz is one callout, folded by default. Its title line shows the outcome and the question, so the note is still easy to scan, and one click opens it.

**Said by the learner:** quizzes clutter the lesson note; a smaller but visually distinct box in place of each quiz. A companion quiz note was proposed first and dropped for a folded callout.

**Agreed in the design conversation:**

- One folded callout per graded quiz, where it was asked. The title is the outcome mark followed by the question.
- Approach A: the quiz server writes the block once, after the learner answers. Nothing is written while the popup is open, so no block is ever rewritten.
- The quizzes already in the vault are converted once, by a script, with a diff shown first.
- A book figure that a quiz names stays above the quiz, as now. Only an image passed to the `quiz` tool goes inside the fold.
- In a PDF export, quizzes print open.

**Assumed and not contradicted:** only graded quizzes change. `ask_user_question` blocks, the fallback quiz protocol, asides and exams keep their format.

## The block

```markdown
> [!failure|quiz]- ✗ Which pirates are the cheapest votes for the proposer to buy?
>
> 1. The pirates who get 0 coins in the $(k-1)$-pirate game
> 2. The pirates who get 1 coin in the $(k-1)$-pirate game
>
> Selected: 2. The pirates who get 1 coin in the $(k-1)$-pirate game
> Correct answer: 1. The pirates who get 0 coins in the $(k-1)$-pirate game
>
> If the proposer's plan fails, he dies and …
```

**Header.** `> [!<kind>|quiz]- <mark> <title>`. The `|quiz` is Obsidian callout metadata. Obsidian does not show it, and it marks the callout as a quiz for code and CSS. The `-` folds the callout by default.

| Outcome | Kind | Title |
|---|---|---|
| correct | `success` | `✓ <title>` |
| incorrect | `failure` | `✗ <title>` |
| I don't know | `info` | `? <title>` |
| skipped | `warning` | `⊘ Skipped: <title>` |
| unavailable | `warning` | `⊘ Unavailable: <title>` |
| asked before answering | `note` | `Asked first: <title>` |
| no result (old notes only) | `question` | `<title>` |

**Title.** The title is the question's first line. A first line longer than 100 characters is cut at the last space before that limit, and `…` is added. The cut never falls inside `$…$`, `$$…$$`, `` `…` `` or `[[…]]`. When those spans leave no space to cut at, the title is cut after the span that crosses the limit.

**Body, in order** (each part separated by a blank `>` line, and only present if it has content):

1. The full question. It is left out when the title is the whole question.
2. `details`.
3. The image passed as `figure`, as `![[name|500]]`, unless it is a book figure that the question names. That case is placed by `figures.py`, see below.
4. The options, numbered in the order shown, then `(select all that apply)` for a multi-select quiz.
5. The outcome lines.
   - correct: `Selected: …`
   - incorrect: `Selected: …` and `Correct answer: …`
   - I don't know: `Correct answer: …`
   - skipped: `(skipped)`
   - unavailable: the server's message
   - asked first: `Your question: …`
6. The explanation. An asked-first block has none, because nothing was graded.
7. `Note: …` when the learner wrote a note in the popup.

## Components

| Component | File | Change |
|---|---|---|
| Quiz block | `hooks/quiz_block.py` (new) | `render(record) -> str`, `parse(lines) -> dict or None`, `is_quiz_header(line) -> bool`, and `convert` as a command-line tool. It is the only module that knows the format. |
| Quiz server | `mcp/quiz_server.py` | Stops writing the question block before the popup opens. Writes one `render(record)` block when the learner answers, skips, presses `?`, or when the quiz is unavailable. `question_block` and `result_block` are removed. |
| Note mirror | `hooks/md_log.py` | `quiz_blocks_from_result` returns `render(record)` for every record, a re-ask included. `quiz_question_block` and `quiz_result_block` are removed. `insert_before_quiz` finds quiz blocks with `parse`. |
| Resume helper | `hooks/lesson.py` | `quiz_outcomes` reads the outcome from each block with `parse` and skips asked-first blocks. `RESULT_KINDS` and the look-ahead pairing are removed. |
| Figures | `hooks/figures.py` | "Is this callout a quiz?" uses `is_quiz_header` instead of `startswith("> [!question]")`. The figure still goes above the quiz. |
| CSS snippet | `obsidian/learn-callouts.css` | Quiz callouts get a smaller title and tighter spacing (`.callout[data-callout-metadata~="quiz"]`). Under `@media print`, quiz callouts print open. |
| Docs | `README.md`, `docs/architecture.md` | The quiz and lesson-note sections describe the folded block, the conversion command, and the print behaviour. |

## Data flow

**Normal quiz.** PreToolUse flushes the prose that is already persisted, as now. The server shows the popup. On the answer it appends `render(record)` to the note and marks the call logged. On PostToolUse the replay finds prose that was persisted late and calls `insert_before_quiz`, which puts it above the block, as now.

**`?` in the popup.** The server appends an asked-first block holding the question, the options and the learner's question. The teacher's answer is mirrored below it as normal prose. The re-ask is a new `quiz` call. It keeps the option order from `last-asked.json`, as now, and appends a full block with the result. The note shows: asked-first block, the answer, the result block.

**Rebuild and background quizzes.** `md_log.py` renders the block from the `QUIZ_JSON` record in the tool result, so a rebuilt note matches a live one.

**`insert_before_quiz` match.** A block matches the question when the question, normalized as now by `_norm`, starts the block's question text. That text is the body's first paragraph when it repeats the title; otherwise it is the title. When several blocks match, the last one wins, as now.

## Conversion

`python3 .claude/hooks/quiz_block.py convert <note>...` prints a unified diff and changes nothing. With `--write` it first copies each note to `.claude/md-log-state/quiz-fold-backup/<name>-<timestamp>.md`, then rewrites the note in place.

The old format: a `> [!question] Quiz` callout (question, details, an optional figure and the options, which cannot be told apart reliably), then a result callout. Results recognised: `✓ Correct`, `✗ Incorrect`, `I don't know`, `Quiz — cancelled`, `Quiz — unavailable`, `Asked before answering`, and pi's `Quiz — correct ✓`, `Quiz — incorrect ✗`, `Quiz — I don't know`.

For each old question block:

- **The next callout is its result.** Both are replaced, at the question's position, by one new block. The header is built from the result's kind and the first line of the old question body. The body is the old question body, with the first paragraph dropped when it equals the title, followed by the old result body.
- **The next callout is `Asked before answering`.** The question block and that note become one asked-first block, with the note's text after `Your question: `. The teacher's answer that follows is left in place. The next result callout before the following quiz becomes a full block at its own position. Its body copies the question body from the original question block.
- **No result before the next quiz or the end of the note.** The block becomes `[!question|quiz]-` with its body unchanged.

Lines between a question and its result that are not callouts, such as a figure embed, are left where they are. The converter refuses a note that already has `|quiz]` blocks and old blocks mixed together, unless `--force` is given. Running it twice changes nothing.

Notes to convert: the ten notes in the vault that hold old quiz blocks, including `Learn/Probabilistic ML.md`. Checkpoint files hold no quizzes.

## Tests

- `tests/test_quiz_block.py`: `render` for every outcome; `parse(render(r))` round-trips the kind, outcome and question; title cutting near the limit, inside `$…$`, inside `[[…]]`, and on a multi-line question; `is_quiz_header` on quiz and non-quiz callouts.
- Conversion tests on fixtures copied from real notes: a correct pair, an incorrect pair, I don't know and skipped (`openskill`), asked-first with a teacher answer between (`test3`), an unanswered question (`tcp`), a figure embed above a quiz (`gb-ch02`), pi titles, and the idempotence and mixed-note refusal.
- `lesson.quiz_outcomes` on a note in the new format.
- `md_log.insert_before_quiz` puts prose above the matching block, on a repeated-question title and on a cut title.
- `figures.process` still places a named figure above a quiz block.
- The existing suite passes.

## Risks

- **The print rule is not verified yet.** Whether a folded callout's content is in the DOM when Better Export PDF prints is not known. The implementation checks this in Obsidian first. If the content is not there, the print rule is dropped and the README says quizzes print folded.
- **Callout metadata.** `|quiz` needs an Obsidian version that supports callout metadata. Versions from the last few years do. Older versions show `|quiz` as part of the type and fall back to the default callout style.
- **A crash while the popup is open** leaves no block in the note. The rebuild from the transcript still recovers the quiz once its result is in the transcript. A quiz that never got a result is lost from the note, which is acceptable.
