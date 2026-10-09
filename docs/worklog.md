# Work log

Running notes on the state of the project, for picking work back up. Newest first.

## 2026-10-09 — review notes for recall checks

**Built.** A recall check on resume goes in a review note, not in the lesson note.
- The learner chose a recall check at the start of chapter 2, and its questions on chapter 1 landed in the chapter 2 note.
- `lesson.py review <note>` prints the review note (`<slug>-review.md` per course, `<stem> — Review.md` per lesson) and the `###` headings of the lesson note and, in a course, the previous chapter note, as wikilinks.
- The teacher links the review note `--from-now`, asks, ends the reply with `ready`, and links the lesson note back on the next turn.
- `lesson.py summary` lists missed review questions under `EARLIER RECALL CHECKS`. The course index links the review note once it exists.
- `/lesson reset` trashes a lesson's own review note, not a course's.

**Tested** on a fake course and lesson in a scratch directory: `review`, `summary` and `reset` output.

### To verify in a real session

- The switch: the review heading, quizzes and the closing `ready` line land in the review note, and nothing after `ready` does.
- Whether a check of chapter 1 at the start of chapter 2 finds its nodes: the brief comes from the chapter 2 note, whose checkpoint may not list chapter 1's nodes.

## 2026-10-06 — book figures, PDF export

**Built.** The book's figures come into course notes and quizzes.
- `book.py figure <id>` crops a figure with its caption into `viz/<slug>-fig-<id>.png`, in about a second.
  - The crop runs from the caption block (`pdftotext -bbox-layout`) up to the nearest full-width text above it.
  - White margins are trimmed from a 50 dpi grey render, and the final crop is a 150 dpi PNG.
  - `--box TOP BOTTOM` and `--page` override the crop.
  - Spot-checked on ten Murphy figures: photos, vector diagrams with labels, side-by-side panels, a figure mid-page. All were clean.
- `hooks/figures.py` handles every block written to a course note: `md_log.append`, `insert_before_quiz`, and the quiz server's live blocks.
  - The first mention of "Figure N.M" (or "Figure N.Ma", "Fig. N.M") embeds the figure once, as `![[<slug>-fig-1-4.png|600]] ^fig-1-4`.
  - The embed goes below that paragraph or callout, or above a quiz question.
  - Every mention becomes `[[#^fig-1-4|Figure 1.4a]]`.
  - `figures.py <note>` retrofits a note written earlier; it was applied to `courses/pml1/pml1-ch01.md` (Figures 1.3 and 1.4).
- The quiz tool takes an optional `figure`. Without it, a course quiz that names a figure gets it attached by the server.
  - The popup shows "Figure: … press f to view". `f` runs `xdg-open`, detached, on the question screen and the grade screen.
- The teach skill now only names figures; the teacher never embeds them.

**Why the server attaches figures itself.** The first live quiz that named Figure 1.4a had no figure. The rule was
in the exposition guidance, and the resume path skips that. Mechanical rules belong in the hooks, not in the skill.

**PDF export.** Obsidian's built-in export leaves same-note links dead, so we use the community plugin Better Export PDF.
- That plugin only turns heading links into PDF jumps. Block links (`#^…`) stay as fragment hrefs, and those do nothing in the PDF.
- `scripts/patch-better-export-pdf.py` gives each `span.blockid` an `af://blk-<id>` anchor and points block links at `an://blk-<id>`.
  - The patch is idempotent, keeps `main.js.orig`, and refuses a plugin version it was not written for.
  - It is applied to the vault's plugin (2.0.3). The learner confirmed that figure, equation and example links jump.
- `learn-callouts.css` gained print rules: headings and the `---` above a session header stay with what follows; callouts, display math, figures, tables and code don't split across pages.
  - The learner confirmed the PDF is right.
  - `git pull` does not update the vault's copy of the snippet; the README says to copy it again.

**Fixed by hand.** In `pml1-ch01.md`, the `[!remark] Data versus parameters` callout lost its `>` after the first
line, so three paragraphs fell outside it. The lines were re-quoted. The cause is not known; the teacher wrote it that way.

**Explained, not changed.** A resumed session that left off right after a reading opens with a pointer back to
that reading. Two sessions in a row without progress therefore open with two similar recaps.

### To verify in a real session

- `f` in the real tmux popup opens the image viewer. It was tested only with a stub `xdg-open`. If nothing opens, pass `DISPLAY`/`WAYLAND_DISPLAY` to the popup.
- A fresh lesson unit that names a figure: the embed lands below the right paragraph, and the crop is good. Since the teacher no longer reads the PNG, a bad crop is only caught by the learner.
- A quiz naming a figure not yet in the note: the embed goes above the quiz, and prose written before the quiz still lands above both.

### Ideas

- Repeated-resume recap: when nothing happened since the last pointer, make it one line.
- Callouts missing `>`: a mirror-side repair is possible (a line right after a callout that continues its topic), but it is heuristic.
- Figures whose caption sits above the figure (some books) or beside it: `book.py figure` assumes below.
- Tables (`Table 2.1`) could use the same crop-and-embed path.

## 2026-10-05 — textbook courses

**Fixed.** `insert_before_quiz` matched only the first line of a quiz question, so prose before a multi-line
question landed below the quiz. `lesson.py quiz_outcomes` counted a quiz answered after `?` (ask first) as
unanswered; one such quiz in `lessons/test3.md` now counts.

**Built.** Courses that follow a textbook PDF: `hooks/book.py` (page map, syllabus, progress, exercise
records), `/course` and `/exercise` skills, the section "Teaching from a book" in the teach skill, and
`md_log.py link --from-now` for moving between notes in one session. Design decisions: the lesson replaces
reading the section; one note per chapter plus an exercises note; equations keep the book's numbers; full
solutions by default only after an attempt and on request; assessed exercises are never solved or quizzed;
PDF only for now.

**Later the same day, after the first live runs.** The lesson opener is now a reply of its own, and a course
chapter opens with an `### Overview` (text and map) that ends in a choice: `ready` or `probe`; the probe is
opt-in. Reason: two live `/course next` runs went straight to a probe quiz with no text. In a course the book is
the backbone, not the boundary: outside material and further reading are allowed, marked as not in the book.
`/course list` and `/course use <name>` switch between courses. README and architecture.md rewritten for
readability. Confirmed live by the learner: overview first, `ready` into §1.1, `/lesson pause` writes the
chapter checkpoint. Resume a course with `/course next`, not `/lesson resume`.

**Note hygiene.** A chapter note picked up a `/course list` reply and a mistyped "course next" from two fresh
sessions, because a new session adopted the note linked last. Now only a session that linked a note writes to
it; the quiz server learns the note per call from `quiz-target.json`; replies to housekeeping commands are muted
even inside a linked session (`ADMIN_COMMANDS`). Consequence: a new session that just starts talking is not
mirrored until `/md-log`, `/lesson resume`, `/course next` or `/exercise`.

**Tested.** `book.py` against Murphy, *Probabilistic Machine Learning: An Introduction* (860 pages, 714 outline
entries, 132 units; section 2.3, Equation 2.51, Figure 2.7 and Exercise 2.3 spot-checked against the pages), three other
PDFs (outline with `#page=` targets, outline without numbers, a paper), a PDF without an outline, a hand-written
contents file, and the text-search fallback with anchors disabled. `--from-now` with a simulated session moving
lesson → exercises → lesson. **Not tested:** the skills in a live session.

### To verify in a real session

- `/course new ~/Documents/murphybook/book1.pdf pml1`: nothing mirrored during setup; the three questions; the
  syllabus that results from "core sections only".
- `/course next` on a new chapter: the reply is the `### Overview` with the map and the ready-or-probe line,
  and no quiz (two live runs before this rule went straight to a probe quiz with no text); then whether the
  teacher reads the pages before every unit and stops for `ready`.
- Condensing: is a 10-page section (2.2) a readable lesson, or should long sections always split by subsection?
- Book equation tags (`\tag{2.51}`, `^eq-2-51`) and links in Obsidian.
- `book.py done` after a unit: silent in the note, next unit follows without `/course next`.
- `/exercise 2.3` mid-lesson: the exercises note gets only the exercise; `/course next` returns to the chapter
  note without a second session header.
- The hint ladder: one rung per reply, and the refusal of a full solution before an attempt.

### Ideas

- Render a book figure into `viz/` (crop a page with `pdftoppm`) so lessons can embed the book's own figures.
- A reader subagent that returns a digest of a long section, if reading 20+ pages per unit proves heavy.
- Other sources: lecture-note PDFs work as they are; web pages and video transcripts would need their own mapper.
- The lists from 2026-09-30 below are still open (no real session has run since).

## 2026-09-30 — first day

**State.** The port is complete and in daily use. Repo: https://github.com/LnBn/learn-claude (private). Installed
as a git clone at `~/Documents/Obsidian Vault/.claude`; `vault claude` (shell function) opens Claude Code there.
Update with `git -C .claude pull` from the vault root.

**Built today, in order:** the port itself (skills, agents, md-log hook, render scripts) → quiz as an MCP server
→ tmux popup with in-popup grading, LaTeX-to-Unicode, `?` ask-first → `/lesson` resume/pause/status/reset with
sidecar checkpoints → dated session headers, one-blank-line spacing, no speaker banners except `> **You:**`
→ narration filtering (many rounds, tuned on real notes) → read/ready/quiz section structure, Phase 0 opener
(beginner overview + how-to-start question) → `### Plan` heading, environments as callouts + CSS snippet,
notation rule, equation numbering with block links, numbered worked-example callouts → optional recall check on resume → MCP backgrounding
disabled (`CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS=0`) → note ordering fixes (prose inserted above a quiz block) →
relink no longer duplicates → rebuild command for notes.

**Notes reformatted by hand** to the new conventions: `lessons/openskill.md` (definitions, 9 notation blocks,
equations (1)–(12) with links, Examples 1–4 as aligned calculations), `lessons/game_theory.md` (definitions,
theorems, notation, Example 1), `lessons/tcp.md` (plan heading only). Backups of every rewritten note are in
`.claude/md-log-state/*.bak`. `Learn/Probabilistic ML.md` (pi-era) was only de-duplicated, not reformatted.

**Lessons in progress:** game theory (`lessons/game_theory.md`, at the dominance node), OpenSkill
(`lessons/openskill.md`, σ update done), TCP (`lessons/tcp.md`, plan approved, no sections yet).

### To verify in a real session tomorrow

- The read → `ready` → check → apply rhythm: does the teacher stop after the exposition every time?
- Phase 0 for a beginner request: overview paragraphs, then the Start/Goal question, nothing else.
- `/lesson resume`: only the Resume question in the terminal, nothing in the note; "Continue" goes straight to
  the next section.
- Environments and notation blocks in freshly generated sections (quality, not just presence).
- Equation numbering continues across sessions.

### Known rough edges / ideas

- The narration filter is heuristic (`is_narration` in `hooks/md_log.py`). Keep tuning from real notes; every
  miss so far was a new phrasing. A structural alternative: have the teacher wrap any non-lesson remark in a
  marker the hook strips.
- Duplicate defence: `append()` could refuse a block identical to one of the last few blocks in the file. Cheap
  insurance against the next relink/replay bug.
- Session `tool_ids` in `md-log-state/<session>.json` absorb the quiz-logged ids on every replay (cosmetic).
- `md-log.log` and `quiz-server.log` grow without bound; rotate or cap.
- The quiz server only knows the vault-wide `md-log.json`; two lessons open at once would log quiz blocks to the
  last linked note.
- Elicitation fallback (outside tmux) is poor; consider refusing to run a quiz outside tmux instead.
- `Learn/Probabilistic ML.md` could get the same environment/notation pass if it will be resumed.
- Multi-select in the popup is checkboxes; untested with a real multi-answer question in a lesson.
