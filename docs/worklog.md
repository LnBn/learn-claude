# Work log

Running notes on the state of the project, for picking work back up. Newest first.

## 2026-09-30 — first day

**State.** The port is complete and in daily use. Repo: https://github.com/LnBn/learn-claude (private). Installed
as a git clone at `~/Documents/Obsidian Vault/.claude`; `vault claude` (shell function) opens Claude Code there.
Update with `git -C .claude pull` from the vault root.

**Built today, in order:** the port itself (skills, agents, md-log hook, render scripts) → quiz as an MCP server
→ tmux popup with in-popup grading, LaTeX-to-Unicode, `?` ask-first → `/lesson` resume/pause/status/reset with
sidecar checkpoints → dated session headers, one-blank-line spacing, no speaker banners except `> **You:**`
→ narration filtering (many rounds, tuned on real notes) → read/ready/quiz section structure, Phase 0 opener
(beginner overview + how-to-start question) → `### Plan` heading, environments as callouts + CSS snippet,
notation rule, equation numbering with block links → optional recall check on resume → MCP backgrounding
disabled (`CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS=0`) → note ordering fixes (prose inserted above a quiz block) →
relink no longer duplicates → rebuild command for notes.

**Notes reformatted by hand** to the new conventions: `lessons/openskill.md` (definitions, 9 notation blocks,
equations (1)–(12) with links), `lessons/game_theory.md`, `lessons/tcp.md`. Backups of every rewritten note are in
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
