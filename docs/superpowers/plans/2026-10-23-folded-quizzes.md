# Folded Quizzes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every graded quiz in a lesson note becomes one folded callout whose title shows the outcome and the question, and the quizzes already in the vault are converted to it.

**Architecture:** A new module, `hooks/quiz_block.py`, is the only code that knows the block format: `render`, `parse`, `is_quiz_header`, and a `convert` command for old notes. The quiz server writes one rendered block after the learner answers; `md_log.py`, `lesson.py` and `figures.py` call the module instead of matching `> [!question] Quiz`.

**Tech Stack:** Python 3.10+, standard library only; tests with `unittest` (`python3 -m unittest discover -s tests -v`); Obsidian callouts and a CSS snippet.

**Spec:** `docs/superpowers/specs/2026-10-23-folded-quizzes-design.md`

## Global Constraints

- Header: `> [!<kind>|quiz]- <mark> <title>`. Kinds and titles exactly as the spec's outcome table: `success` `✓ `, `failure` `✗ `, `info` `? `, `warning` `⊘ Skipped: ` / `⊘ Unavailable: `, `note` `Asked first: `, `question` (no prefix).
- Title: the question's first line; over 100 characters it is cut at the last space at or before 100 and `…` is appended; never cut inside `$…$`, `$$…$$`, `` `…` ``, `[[…]]` (if no space is left, cut after the span that crosses 100).
- Body order: full question (omitted when the title is the whole question), details, non-book `figure` embed `![[name|500]]`, options + `(select all that apply)`, outcome lines, explanation, `Note: …`; parts separated by a blank `>` line.
- Outcome strings used by `lesson.py`: `"✓"`, `"✗"`, `"?"`, `"skip"`, `"(unanswered)"` (unchanged), plus `"unavailable"` and `"asked"`.
- Backups of converted notes go to `.claude/md-log-state/quiz-fold-backup/<name>-<timestamp>.md`.
- Standard library only. Match the surrounding code: short docstrings, comments only where the reason is not obvious.
- README is a tutorial: describe how things work now, no change history.

**Corrections to the spec found while planning (to be confirmed by the learner):**

- `lessons/tcp.md` holds quizzes from the *fallback* protocol: `> [!question] Quiz` followed by `> [!example] Answer`. The spec keeps the fallback format, so the converter leaves a `Quiz` block whose next callout is `[!example] Answer` untouched (the spec had said it becomes `[!question|quiz]-`).
- `Learn/Probabilistic ML.md` is a pi-era note in which pi wrote two questions before their results, so pairing "next result after the question" gives wrong pairs. The converter refuses any note containing pi result titles (`Quiz — correct ✓`, `Quiz — incorrect ✗`, `[!question] Quiz — I don't know`) and names it; that note is left as it is.

## Review Focus

1. **A multi-paragraph question or one with a code block** (the question string contains `\n`): the title is its first line, the full question is in the body, and `insert_before_quiz` still finds the block. Test in Task 1 and Task 4.
2. **A title whose first 100 characters end inside `$…$` or a `[[#^fig-1-4|Figure 1.4a]]` link**: Obsidian must still render it. Test in Task 1.
3. **The `?` path followed by a re-ask**: the note shows the asked-first block, the teacher's answer, then one full block, and the question block is not written twice. Test in Task 3.
4. **A note with a quiz the learner never answered before the session ended** (`pml1-ch01.md:210`): converts to a folded `[!question|quiz]-` block and the next session's re-ask of the same question is paired with its own result. Test in Task 2.
5. **Running the converter on a note that has fallback quizzes and new blocks**: no refusal, no change. Test in Task 2.

---

### Task 1: `quiz_block.py` — render, parse, title

**Files:**
- Create: `hooks/quiz_block.py`
- Test: `tests/test_quiz_block.py`

**Interfaces:**
- Consumes: `figures.mentions(text) -> list[str]` (existing).
- Produces:
  - `cut_title(line: str, limit: int = 100) -> str`
  - `render(record: dict) -> str` — `record` is the quiz server's record: `status` (`"answered"|"cancelled"|"unavailable"|"asked"`), `question`, `details`, `multiSelect`, `options` (`[{"index", "label"}]`), `correctIndices`, `explanation`, optional `figure`, `answers`, `correct`, `dontKnow`, `note`, `learnerQuestion`, `message`.
  - `is_quiz_header(line: str) -> bool` — true for `> [!<word>|quiz]` with optional `-`/`+`.
  - `parse(block: list[str]) -> dict | None` — `block` is one callout's lines (as `lesson.callout_blocks` yields). Returns `None` unless `is_quiz_header(block[0])`; otherwise `{"kind", "outcome", "title", "text"}`: `title` without the mark or prefix and with any `…`; `text` is the searchable question text, the body when its first paragraph starts with the title (minus `…`), else the title, a newline and the body.

- [ ] **Step 1: Write the failing tests** in `tests/test_quiz_block.py` (`import tests._vault` first, as `test_sections.py` does):
  - `test_render_correct`: a record with `question="What is 2+2?"`, options `4`, `5`, `correctIndices=[1]`, `answers=[1]`, `correct=True`, `explanation="Arithmetic."`; the first line is exactly `> [!success|quiz]- ✓ What is 2+2?`, the body does not contain a second `What is 2+2?`, it contains `> 1. 4`, `> Selected: 1. 4` and `> Arithmetic.`.
  - `test_render_incorrect`, `test_render_dont_know`, `test_render_cancelled`, `test_render_unavailable`, `test_render_asked`: first lines `> [!failure|quiz]- ✗ …`, `> [!info|quiz]- ? …`, `> [!warning|quiz]- ⊘ Skipped: …`, `> [!warning|quiz]- ⊘ Unavailable: …`, `> [!note|quiz]- Asked first: …`; incorrect has `Selected:` and `Correct answer:`; I don't know has only `Correct answer:`; asked has `> Your question: …` and no explanation.
  - `test_render_multiline_question`: question `"Run this:\n```\nprint(1)\n```\nWhat prints?"`; title `Run this:`, body contains the whole question.
  - `test_cut_title_long`, `test_cut_title_in_math`, `test_cut_title_in_link`: a 140-char plain line is cut to ≤101 chars ending `…` at a space; a line whose 100th char is inside `$\mathrm{KL}(q \,\|\, p)$` never ends with an odd number of `$` before `…`; a line with `[[#^fig-1-4|Figure 1.4a]]` across char 100 keeps the link whole.
  - `test_parse_round_trip`: for each record above, `parse(render(r).split("\n"))` has the matching `kind` and `outcome` (`"✓"`, `"✗"`, `"?"`, `"skip"`, `"unavailable"`, `"asked"`) and `parse(...)["text"]` starts with the question's first line.
  - `test_parse_rejects_other_callouts`: `parse(["> [!success] ✓ Correct", ">", "> x"])` and `parse(["> [!aside]+ Why?"])` are `None`; `is_quiz_header("> [!question|quiz]- Foo")` is true.

- [ ] **Step 2: Run** `python3 -m unittest tests.test_quiz_block -v` — Expected: FAIL, `No module named 'quiz_block'`.

- [ ] **Step 3: Implement** `hooks/quiz_block.py` with the four functions above and a module docstring naming the format. `callout(kind, title, body_lines)` is copied from `md_log.py:callout` (same quoting). The book-figure rule is the one in `quiz_server.question_block`: embed `figure` only when `not figures.mentions(question + " " + details)`. `cut_title` finds protected spans with one regex (`\$\$.*?\$\$|\$[^$]*\$|`[^`]*`|\[\[.*?\]\]`) and only cuts at spaces outside them.

- [ ] **Step 4: Run** `python3 -m unittest tests.test_quiz_block -v` — Expected: all PASS.

- [ ] **Step 5: Commit** `git add hooks/quiz_block.py tests/test_quiz_block.py && git commit -m "quiz_block.py: one folded callout per graded quiz"`

### Task 2: `quiz_block.py convert` — old notes to folded blocks

**Files:**
- Modify: `hooks/quiz_block.py`
- Test: `tests/test_quiz_block.py` (class `Convert`), fixtures as module constants in the test file

**Interfaces:**
- Consumes: Task 1's `cut_title`, `callout`, `is_quiz_header`.
- Produces:
  - `convert_text(text: str, force: bool = False) -> str` — raises `ValueError` with a one-line reason for a pi-era note, or a note with new blocks and old graded blocks unless `force`.
  - CLI: `python3 hooks/quiz_block.py convert [--write] [--force] <note>...` — without `--write` prints a unified diff per changed note (`difflib.unified_diff`, file names as labels) and changes nothing; with `--write`, copies each changed note to the backup directory first. Prints `REFUSED <note>: <reason>` for a refused note and carries on; exit status 1 if any note was refused.

- [ ] **Step 1: Write the failing tests.** Fixtures are copied from the vault (trim long lines, keep structure):
  - `OLD_PAIR` (a correct pair from `gb-ch02.md:96-109`) → one block starting `> [!success|quiz]- ✓ In the $k$-pirate game, which pirates are the cheapest votes for the proposer to buy?`, containing the four options, `Selected: 1.` and the explanation, and no `[!question] Quiz`.
  - `OLD_INCORRECT`, `OLD_DONT_KNOW`, `OLD_CANCELLED` (from `openskill.md:336-338`): kinds `failure`, `info`, `warning` with `⊘ Skipped:`.
  - `OLD_ASKED` (`test3.md`: question, `[!note] Asked before answering`, a prose paragraph, `[!success] ✓ Correct`): result has, in order, `> [!note|quiz]- Asked first: …` containing `Your question: What happens if there are multiple repos…`, the unchanged prose paragraph, then `> [!success|quiz]- ✓ …` whose body holds the options again.
  - `OLD_UNANSWERED_THEN_REASK` (`pml1-ch01.md:210-237`: a question with no result, a session header, the same question and an `✗ Incorrect`): first becomes `> [!question|quiz]- For the Iris decision tree of [[#^fig-1-4|Figure 1.4a]], …`; the second becomes `[!failure|quiz]-`; the session header and prose between are unchanged.
  - `OLD_FIGURE_ABOVE`: `![[fig-1-4.png|600]] ^fig-1-4`, blank line, then an old pair: the embed line stays above the new block.
  - `FALLBACK` (`tcp.md:5-17`, `[!question] Quiz` + `[!example] Answer`): `convert_text` returns it unchanged.
  - `test_pi_note_refused`: text containing `> [!success] Quiz — correct ✓` raises `ValueError` whose message contains `pi`.
  - `test_idempotent`: `convert_text(convert_text(OLD_PAIR)) == convert_text(OLD_PAIR)`.
  - `test_mixed_refused`: new block + `OLD_PAIR` raises `ValueError`; with `force=True` converts the old pair; new block + `FALLBACK` does not raise and is unchanged.
  - `test_cli_dry_run_and_write` (uses `tests._vault.make_vault` and `run`): dry run prints `+> [!success|quiz]-` and leaves the file unchanged; `--write` changes it and creates exactly one file in `.claude/md-log-state/quiz-fold-backup/` equal to the original.

- [ ] **Step 2: Run** `python3 -m unittest tests.test_quiz_block.Convert -v` — Expected: FAIL, `has no attribute 'convert_text'`.

- [ ] **Step 3: Implement** `convert_text` and `main(argv)`. Old question header: the stripped line equals `> [!question] Quiz`. Old result headers (stripped) and their new kind/prefix: `> [!success] ✓ Correct` → success; `> [!failure] ✗ Incorrect` → failure; `> [!info] I don't know` → info; `> [!warning] Quiz — cancelled` → warning `⊘ Skipped: `; `> [!warning] Quiz — unavailable` → warning `⊘ Unavailable: `; `> [!note] Asked before answering` → asked-first. Walk the callout blocks in order; for each old question, look at callouts after it up to the next old question: the first result header found decides the case in the spec's *Conversion* section; a first callout of `> [!example] Answer` means fallback, leave it. Title from the first non-empty line of the old question body; drop the body's first paragraph when it equals that line. Rebuild the text from untouched line ranges plus new blocks, so all non-quiz lines stay byte-identical. Backup directory: `os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "md-log-state", "quiz-fold-backup")`, the same root as `md_log.STATE_DIR`.

- [ ] **Step 4: Run** `python3 -m unittest tests.test_quiz_block -v` — Expected: all PASS.

- [ ] **Step 5: Commit** `git commit -am "quiz_block.py convert: old quiz pairs become folded blocks"` (add the test file if new hunks are untracked).

### Task 3: Quiz server writes one block after the answer

**Files:**
- Modify: `mcp/quiz_server.py` (`question_block`, `result_block` at :239-281 removed; `run_quiz` at :348-471)
- Test: `tests/test_quiz_examples.py` (new class `WritesOneBlock`)

**Interfaces:**
- Consumes: `quiz_block.render(record)` (Task 1).
- Produces: unchanged tool result and `QUIZ_JSON` record; the note gets exactly one `render(record)` block per call.

- [ ] **Step 1: Write the failing tests.** In `WritesOneBlock.setUp`, point the server at a temp note (patch `quiz_server.log_file` to return its path), patch `tmux_available` to `False`, `set_target` to a no-op, and `ask_via_elicitation` to return a scripted dict; patch `LAST_ASKED` and `QUIZ_LOGGED` to temp paths.
  - `test_answer_writes_one_block`: UI `{"action": "accept", "answers": [<index of the correct option>]}`; the note contains exactly one line starting `> [!success|quiz]-` and no `[!question] Quiz`.
  - `test_nothing_written_before_answer`: in the patched `ask_via_elicitation`, read the note and record its content; that content is empty.
  - `test_ask_then_reask`: first call UI `{"action": "ask", "question": "Why?"}`, second call same args with UI accept; the note holds, in order, one `> [!note|quiz]- Asked first:` block and one `> [!success|quiz]-` (or `failure`) block, and the question text appears in each block once.
  - `test_cancel`: UI `{"action": "decline"}` → one `> [!warning|quiz]- ⊘ Skipped:` block.

- [ ] **Step 2: Run** `python3 -m unittest tests.test_quiz_examples -v` — Expected: the new tests FAIL (two blocks / `[!question] Quiz` present).

- [ ] **Step 3: Implement.** `import quiz_block` beside the other `hooks` imports. In `run_quiz`, remove the `append_log(question_block(record))` before the popup (keep `mark_logged` and `clear_last_asked` where they are); replace each `append_log(result_block(record))` with `append_log(quiz_block.render(record))`. Delete `question_block`, `result_block`, and `callout` if nothing else uses it.

- [ ] **Step 4: Run** `python3 -m unittest discover -s tests -v` — Expected: all PASS.

- [ ] **Step 5: Commit** `git commit -am "Quiz server: one folded block, written after the answer"`

### Task 4: Note mirror renders and finds folded blocks

**Files:**
- Modify: `hooks/md_log.py` (`quiz_question_block`, `quiz_result_block` :203-242 removed; `quiz_blocks_from_result` :245-255; `insert_before_quiz` :303-339; module docstring line 19)
- Test: `tests/test_mirror_quiz.py` (new)

**Interfaces:**
- Consumes: `quiz_block.render`, `quiz_block.parse` (Task 1).
- Produces: `quiz_blocks_from_result(text) -> str` returns `quiz_block.render(record)` for every record, a re-ask included; `insert_before_quiz(text, question) -> bool` unchanged in signature.

- [ ] **Step 1: Write the failing tests:**
  - `test_from_result_renders_folded`: `quiz_blocks_from_result("ok\nQUIZ_JSON: " + json.dumps(record))` equals `quiz_block.render(record)`; with `"reask": True` it is the same full block.
  - `test_insert_before_folded_block`: a note holding `render(r)` for a short question; `insert_before_quiz("Prose.", r["question"])` returns `True` and `Prose.` is directly above the block's header.
  - `test_insert_before_cut_title` and `test_insert_before_multiline_question`: same, with a 150-char question and with the code-block question from Task 1.
  - `test_insert_picks_last_match`: two blocks with the same question; prose lands above the second.
  Point `md_log` at the note the way `test_mirror_exam.py` does (a vault from `tests._vault.make_vault`, linked with the md-log config), or by patching `md_log.log_file`.

- [ ] **Step 2: Run** `python3 -m unittest tests.test_mirror_quiz -v` — Expected: FAIL.

- [ ] **Step 3: Implement.** `import quiz_block`. `quiz_blocks_from_result` parses the record as now and returns `quiz_block.render(r)`. In `insert_before_quiz`, iterate callout blocks; for each where `quiz_block.parse(block)` is not `None`, compare `_norm(parsed["text"]).startswith(want)`; keep the last match. Remove the two old block functions; update the docstring line that names `> [!question] Quiz`.

- [ ] **Step 4: Run** `python3 -m unittest discover -s tests -v` — Expected: all PASS.

- [ ] **Step 5: Commit** `git add tests/test_mirror_quiz.py && git commit -am "md_log.py: quiz blocks come from quiz_block.py"`

### Task 5: Resume brief and figures read the new block

**Files:**
- Modify: `hooks/lesson.py` (`RESULT_KINDS` :36-47 removed; `quiz_outcomes` :182-205), `hooks/figures.py:141`
- Test: `tests/test_lesson_outcomes.py` (new), `tests/test_quiz_block.py` (one figures test)

**Interfaces:**
- Consumes: `quiz_block.parse`, `quiz_block.is_quiz_header`.
- Produces: `lesson.quiz_outcomes(lines) -> list[tuple[str, str]]`, `(title, outcome)` per quiz block in note order, asked-first blocks left out.

- [ ] **Step 1: Write the failing tests:**
  - `test_outcomes_in_order`: lines of a note with prose, `render` blocks for correct, asked, incorrect, I don't know, skipped; `quiz_outcomes` returns four tuples (the asked block is left out) with outcomes `["✓", "✗", "?", "skip"]`.
  - `test_unanswered`: a `[!question|quiz]-` block (from Task 2's converter output) gives `"(unanswered)"`.
  - `test_figure_above_quiz` (in `test_quiz_block.py`, using a course dir like `test_sections.py`'s `setUp` and a stubbed `figures.crop` returning a path): `figures.process` on a rendered block whose question names `Figure 1.4` inserts the embed line above the block's header, not inside it.

- [ ] **Step 2: Run** `python3 -m unittest tests.test_lesson_outcomes tests.test_quiz_block -v` — Expected: FAIL.

- [ ] **Step 3: Implement.** `lesson.quiz_outcomes`: for each `callout_blocks` block, `p = quiz_block.parse(blk)`; skip `None` and `p["outcome"] == "asked"`; append `(p["title"], p["outcome"])`. `figures.py:141`: `before = quiz_block.is_quiz_header(lines[a])`. Update the `docs/architecture.md:134` sentence on quiz outcomes in the same commit.

- [ ] **Step 4: Run** `python3 -m unittest discover -s tests -v` — Expected: all PASS.

- [ ] **Step 5: Commit** `git commit -am "lesson.py, figures.py: read the folded quiz block"`

### Task 6: CSS and docs

**Files:**
- Modify: `obsidian/learn-callouts.css`, `README.md` (*Quizzes* and *The lesson note* sections, *Commands* table, *Repository layout*), `docs/architecture.md` (component table row for `quiz_block.py`, the quiz data-flow paragraphs, the test list at :326)

- [ ] **Step 1: CSS.** Add a block for `.callout[data-callout-metadata~="quiz"]`: title `font-size: 0.9em`, callout `padding` and `margin` about two thirds of the default. Inside the existing `@media print` block add: `.callout[data-callout-metadata~="quiz"] > .callout-content { display: block !important; }` and `.callout[data-callout-metadata~="quiz"] .callout-fold { display: none; }`.

- [ ] **Step 2: Docs.** README: a quiz in the note is one folded box whose line shows ✓/✗ and the question; what each mark means; quizzes print open; `python3 .claude/hooks/quiz_block.py convert <note>…` for notes written before (dry run, then `--write`, backups under `.claude/md-log-state/`). Architecture: `quiz_block.py` owns the format; the server writes once after the answer; the asked-first sequence.

- [ ] **Step 3: Run** `python3 -m unittest discover -s tests -v` — Expected: all PASS. `grep -rn "\[!question\] Quiz" README.md docs/architecture.md hooks mcp` — Expected: only `hooks/quiz_block.py` (the converter), `hooks/md_log.py`'s fallback `question_block` for `AskUserQuestion`, and the README sentence on the fallback, if any.

- [ ] **Step 4: Commit** `git commit -am "Docs and CSS: folded quizzes"`

### Task 7: Install and convert the vault (needs the learner)

The learner's vault is `~/Documents/Obsidian Vault`, with this repo cloned at `.claude`. Nothing in this task runs without the learner's go-ahead at each step.

- [ ] **Step 1: Push and pull.** Ask before pushing `master` to GitHub. Then `git -C "~/Documents/Obsidian Vault/.claude" pull` and copy the CSS: `cp obsidian/learn-callouts.css "<vault>/.obsidian/snippets/"`.

- [ ] **Step 2: Dry run.** From the vault: `python3 .claude/hooks/quiz_block.py convert courses/gb/gb-ch01.md courses/gb/gb-ch02.md courses/gb/gb-review.md courses/pml1/pml1-ch01.md lessons/openskill.md lessons/reality_fracture.md lessons/test3.md lessons/tcp.md lessons/lessons/test.md lessons/lessons/test2.md "Learn/Probabilistic ML.md"`. Expected: diffs for the course notes and the lessons with graded quizzes; no diff for `tcp.md`; `REFUSED Learn/Probabilistic ML.md: pi-era note …`. Show the learner a summary (blocks per note) and one full diff hunk of each case.

- [ ] **Step 3: Write**, on the learner's yes: the same command with `--write`. Check: `grep -c "|quiz\]-"` per note equals the old quiz count from the dry run; the backup directory holds one file per changed note.

- [ ] **Step 4: Check in Obsidian (the learner).** Open `gb-ch02.md`: quizzes are folded, titles render math and links, opening one shows the question, options and explanation. Export it with Better Export PDF: quizzes print open. If they print folded or empty, remove the print rule from the CSS and change the README sentence to "quizzes print folded", and commit that.
