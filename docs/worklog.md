# Work log

Running notes on the state of the project, for picking work back up. Newest first.

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

**Tested.** `book.py` against Murphy, *Probabilistic Machine Learning: An Introduction* (860 pages, 714 outline
entries, 132 units; section 2.3, Equation 2.51, Figure 2.7 and Exercise 2.3 spot-checked against the pages), three other
PDFs (outline with `#page=` targets, outline without numbers, a paper), a PDF without an outline, a hand-written
contents file, and the text-search fallback with anchors disabled. `--from-now` with a simulated session moving
lesson → exercises → lesson. **Not tested:** the skills in a live session.

### To verify in a real session

- `/course new ~/Documents/murphybook/book1.pdf pml1`: nothing mirrored during setup; the three questions; the
  syllabus that results from "core sections only".
- `/course next` on a new chapter: opener, probe, plan as a map of the chapter's units; then whether the teacher
  reads the pages before every unit and stops for `ready`.
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
