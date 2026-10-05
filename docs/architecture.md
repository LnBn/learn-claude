# Architecture

How the pieces of learn-claude fit together, why they are built the way they are, and where the system is fragile. Read the [README](../README.md) first; this document is for changing the code.

**Contents:** [Components](#components) · [One lesson section, step by step](#one-lesson-section-step-by-step) · [The quiz tool](#the-quiz-tool) · [The note mirror](#the-note-mirror) · [Pause and resume](#pause-and-resume) · [Courses](#courses) · [Visuals](#visuals) · [Obsidian side](#obsidian-side) · [State files](#state-files) · [Fragile parts](#fragile-parts) · [Testing](#testing)

## Components

The teacher is the Claude Code session itself. Everything else is a prompt it loads, a tool it calls, or a hook that runs around it.

| Component | Files | Job |
|---|---|---|
| Skills | `skills/*/SKILL.md` | Prompts loaded on demand. `teach` holds the method; `lesson`, `course`, `exercise`, `md-log`, `md-unlog` and `visualize` are procedures. |
| House rules | `CLAUDE.md` | Always in context: teach, do not narrate, open with text. |
| Quiz tool | `mcp/quiz_server.py`, `quiz_popup.py`, `latex_text.py` | An MCP server with one tool. Shows a quiz, grades it, writes it to the note. |
| Note mirror | `hooks/md_log.py` | Called by four hooks. Copies prompts and the teacher's prose into the note. |
| Resume helper | `hooks/lesson.py` | Writes checkpoints; prints a short brief of a note for resuming. |
| Course helper | `hooks/book.py` | Maps a textbook PDF to page ranges; keeps syllabus and progress. |
| Subagents | `agents/*.md` | `researcher` checks facts on the web. `mermaid-maker` and `svg-maker` draw diagrams. |
| Renderers | `scripts/render-*.sh` | Turn Mermaid or SVG source into a PNG. |

Skills come in two kinds. `teach`, `visualize` and `exercise` can be loaded by the model when their description fits. `lesson`, `course`, `md-log` and `md-unlog` are slash commands only the user can invoke. The scripts they run are pre-approved in `settings.json`.

## One lesson section, step by step

This sequence explains most of the design. It is the "read, ready, check, apply" loop of one node.

1. The teacher writes the exposition and **ends its reply**.
2. The `Stop` hook runs `md_log.py`, which reads the new text from the session transcript and appends it to the note.
3. The learner reads the note in Obsidian and types `ready`. The `UserPromptSubmit` hook sees a pacing word and logs nothing.
4. The teacher calls the `quiz` tool. The server writes the question to the note, opens the popup and waits.
5. The learner answers. The popup shows the grade. The server writes the result to the note and returns it to the teacher.
6. The teacher calls `quiz` again for the apply question, then continues from the outcome.

**Why the reply ends at step 1.** In interactive mode Claude Code writes an assistant message to the transcript only after the tool calls in it have returned. Text written in the same reply as a quiz call is therefore not on disk when the quiz appears, and the popup covers the terminal. If the teacher wrote the exposition and called the quiz in one reply, the learner would get the quiz first. Ending the reply is the reliable fix. The lesson opener and a course chapter's overview are replies of their own for the same reason.

## The quiz tool

`quiz_server.py` is a stdio MCP server written directly against JSON-RPC, so it needs nothing installed. Claude Code starts it from `.mcp.json` when a session starts. It has one tool, `quiz`.

**A call, in order:**

1. The model sends the question, the options (each with a `value`), `correctAnswer` by value and an `explanation`. Bad input is returned as an error: an unknown value, or a hand-added "not sure" option.
2. The server shuffles the options, appends "I don't know", and writes the question block to the note.
3. It records the tool-use id in `quiz-logged.json`. From now on this quiz's blocks are the server's to write, and the mirror will not log it a second time.
4. It shows the quiz.
   - Inside tmux: `tmux display-popup -E python3 quiz_popup.py spec.json result.json`. The popup is plain curses, with wrapped text, bold, Unicode math from `latex_text.py`, and a note field. On submit it shows the grade and the explanation, then writes `result.json`.
   - Outside tmux: MCP elicitation, which Claude Code renders as a cramped one-line form.
5. It grades, writes the result block to the note, and returns a short text result to the model. The result ends with a `QUIZ_JSON:` line that `md_log.py rebuild` can parse.

**Asking first.** `?` in the popup sends a question instead of an answer. The server logs an "Asked before answering" note and tells the model to answer, then call `quiz` again. The second call is recognised by its option set (`quiz-last-asked.json`). It reuses the order the learner saw and does not log the question block again.

**Long quizzes.** Claude Code moves a tool call to the background after two minutes. `settings.json` sets `CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS=0` so a quiz can stay open as long as the learner needs. If a call is backgrounded anyway, its result arrives as a `<task-notification>`; the teach skill waits for it, and a rebuild places it where the quiz was asked.

**Why a tool, and not the model grading.** The model would need a second turn to mark the answer. The server grades on the keypress, as the original pi extension did.

## The note mirror

`hooks/md_log.py` is called by four hooks. It also has commands: `link`, `unlink`, `status` and `rebuild`.

| Hook | When | What the script does |
|---|---|---|
| `UserPromptSubmit` | the learner sends a prompt | Replays anything the last `Stop` missed, then logs the prompt. Pacing words (`ready`, `ok`, `next`, `probe`) and commands are not logged. |
| `PreToolUse` | before `quiz` or `AskUserQuestion` | For a quiz, records which note it belongs to. Replays the transcript, so prose already on disk lands before the tool's own block. |
| `PostToolUse` | after `quiz` | Replays the transcript and **inserts** prose that preceded the call above the quiz block. |
| `PostToolUse` | after `AskUserQuestion` | Logs the question and the answer. Questions with the header `Resume` are not logged. |
| `Stop` | the teacher's reply ends | Logs the teacher's prose from the transcript. |

**Who writes to a note.** Only a session that linked it. Each session's state file names its note; a hook called by a session with no note does nothing. A fresh session therefore mirrors nowhere until `/md-log`, `/lesson resume`, `/course next`, `/course study` or `/exercise` links one.

**Replay.** The script reads Claude Code's session transcript (JSONL) from a per-session cursor and writes everything new. The transcript format is internal, so the parser is defensive and never blocks the session.

**Late prose.** Because of the persistence order described above, prose can arrive after the quiz block it preceded. There are two defences. The teach skill ends the reading reply before any quiz; that is the real fix. The `PostToolUse` insertion is the safety net. The `PreToolUse` replay has rarely found anything in the sessions observed so far, because the message is usually not on disk yet.

**Timing.** Claude Code sometimes fires `Stop` before the transcript is flushed, so the hook waits up to 8 seconds for an assistant entry.

**What is filtered out:**

- Harness messages: `<system-reminder>`, `<task-notification>`, slash-command payloads, "[Request interrupted by user]".
- Status lines from the scripts (they start with `🗒`), and checkpoint callouts.
- Housekeeping turns. The reply to a command that manages the course or the log is not lesson content: `/course new`, `list`, `use`, `status`, `toc`, `select`, `assess`, `solutions`; `/lesson pause`, `status`, `reset`; `/md-log`, `/md-unlog`. The replay mutes everything from such a command to the learner's next prompt. `/course next`, `/course study`, `/lesson resume` and `/exercise` start teaching and are not muted. A command typed without its slash ("course list") is treated the same way and is not logged as a prompt. The list is `ADMIN_COMMANDS` in `md_log.py`.
- Narration. Text of up to 300 characters is dropped when it starts like narration ("I'll…", "Let me load…"), says it is waiting or paused, or shares a message with a tool call while being very short or announcing an intent. Short narration paragraphs at the start or end of a longer block are trimmed. Longer text is always kept.

**The session header** (`## Session — date`) is written with the first content block, never on hook entry, so an abandoned session leaves no header.

**Linking a note** (`md_log.py link <file> --session <id>`) has three behaviours:

| Situation | Cursor | Effect |
|---|---|---|
| A new note for this session | reset to 0 | The whole session so far is backfilled into the note. |
| The note this session already mirrors | kept | Nothing is logged twice (for example `/lesson resume` after `/lesson pause`). |
| `--from-now` | end of the transcript | Nothing said earlier is backfilled. Used when a session moves between notes. |

With `--from-now` the script finds the transcript by session id under `~/.claude/projects/*/`. It also remembers which notes already carry this session's header, so returning to a note adds no second header.

**Two notes at once.** Two sessions can mirror two notes. The quiz server does not know which session calls it, so the `PreToolUse` hook, which does, writes the calling session's note into `quiz-target.json` under the tool-use id. The server looks its call up there. A quiz from a session with no note is written nowhere and is left unmarked, so a later `/md-log` backfill still logs it from the transcript. Without an entry (hooks not running) the server falls back to `md-log.json`, the note linked last.

**Rebuild.** `md_log.py rebuild <out.md> <transcript.jsonl>...` regenerates a note from transcripts with the current filters.

## Pause and resume

**Pause.** The teacher runs `lesson.py checkpoint <note>` with the handoff on stdin: goal, confirmed nodes, shaky nodes, next node, notes. It is appended to the hidden sidecar `<dir>/.checkpoints/<name>.md`, never to the note.

**Resume.** `/lesson resume <note>` links the note and runs `lesson.py summary`, which prints only:

- the latest checkpoint (from the sidecar, or a legacy checkpoint inside the note, or a pi hand-off note named `<stem> — Resume Here.md`);
- the latest mermaid map;
- a quiz tally and the last twelve quiz outcomes;
- the highest equation and example numbers used.

The teacher reads that brief, never the whole note. It asks once whether to run a recall check, then continues from the checkpoint's next node.

**Quiz outcomes** are read from the note: each `[!question] Quiz` block is paired with the next result callout before the following quiz. pi's callout titles are understood, so pi-era notes resume.

**Reset.** `/lesson reset` moves the note and its sidecar to `md-log-state/trash/<timestamp>/`.

## Courses

A course follows a textbook. The design rule: **the teacher never loads the book.** It reads only the pages of the unit it is about to teach, and `book.py` is what knows which pages those are.

### The page map

`book.py new <pdf>` builds the map once.

- **Outline.** From `mutool show <pdf> outline`. Named destinations are resolved to pages with `pdfinfo -dests`, which also gives the position on the page.
- **Ranges.** An entry runs to the next entry at its level or above. When that one starts part-way down a page, the page is shared and belongs to both ranges; the teacher is told so. Ranges err on the side of one page too many.
- **Ids.** The book's own numbers, parsed from the outline titles ("2.3", appendix "A", part "II"). An outline without numbers gets positional ids.
- **Printed page numbers.** From hyperref's `page.<label>` anchors, else from an offset set by hand.
- **No outline.** The teacher reads the contents pages and writes a contents file; `new --toc <file> --offset <n>` builds the map from it.
- **Conventions.** Sections titled "Exercises" are not study units. A trailing `*` in a title marks the section optional.

### Units and state

The study **unit** is a section (level 2 of the outline), or a chapter that has no sections. A unit is `todo`, `done`, `shaky` or `skipped`.

State is two hidden files in the course folder. `.course/book.json` is the map and can be regenerated. `.course/state.json` holds the syllabus, unit status, exercise records, the goal and the solutions policy. The visible index `<name>.md` is regenerated from the state on every change.

Commands act on the **current course**, remembered in `md-log-state/course.json`. `book.py use <name>` changes it.

### Finding things in the book

`find` and `exercise` locate an equation, figure or exercise by its hyperref anchor (`equation.2.3.51`, `exercisectr.2.3`). Without an anchor they fall back to a `pdftotext` search of the chapter, for "Exercise 2.3" at a line start or "(2.51)" at a line end. Nothing is cached; `pdfinfo -dests` takes under half a second on an 860-page book.

### Teaching a unit

`/course next` runs `book.py next`, links the chapter note with `--from-now`, and hands over to the teach skill's section "Teaching from a book".

1. **A new chapter starts with an `### Overview` reply:** text and the chapter's map, no question. The learner answers `ready` or `probe`. Only `probe` runs the level-finding quizzes.
2. **Before each unit the teacher reads its pages**, then teaches it as ordinary nodes, in the book's notation.
3. **Equations keep the book's numbers** as tags (`\tag{2.51}`, `^eq-2-51`), so references in the exercises resolve in the note.
4. **`book.py done <id>`** records the unit and prints the next one with its pages.

The book is the backbone, not the boundary. The teacher may add outside material and further reading. That material is marked as not in the book, and it is held to the usual accuracy rule (the researcher), not to the page.

### Exercises

The `exercise` skill gives one rung of a five-rung hint ladder per reply and records the rung with `book.py exercise <id> --hint <n>`.

The solutions policy and the `ASSESSED` flag are printed by `book.py exercise <id>` on every lookup. The rule is therefore in front of the model each time, not something it has to remember.

### Moving between notes

A course session can touch several notes: none during setup, a chapter's lesson note, its exercises note. `/course new` unlinks first, so setup is mirrored nowhere. The course and exercise skills link with `--from-now`, so each note receives only what belongs to it.

## Visuals

The `visualize` skill has the teacher brief a maker subagent with one idea and few elements. The maker:

1. writes the source to `/tmp/learn-viz/`;
2. renders it with the script;
3. **reads the PNG** (Claude Code's Read tool shows images) and iterates until the picture is correct;
4. renders with `--publish <slug>`, which copies the PNG to `<project>/viz/viz-<slug>-<timestamp>.png`.

The teacher embeds `![[viz-….png|500]]`. Obsidian resolves embeds by filename anywhere in the vault.

Mermaid renders through the bundled `@mermaid-js/mermaid-cli`, driven by an installed Chrome, so puppeteer downloads nothing. SVG tries `rsvg-convert`, then ImageMagick 7 (`magick`), then ImageMagick 6 (`convert`), then headless Chrome.

## Obsidian side

`obsidian/learn-callouts.css` styles the environment callouts: `definition`, `theorem`, `lemma`, `proposition`, `corollary`, `proof`, `notation`, `remark`, `intuition`, and `example` for worked examples. `install.sh` copies it into `<vault>/.obsidian/snippets/` and enables it in `appearance.json`.

Equation and example references use core Obsidian features only:

| Thing | In the note | Cited as |
|---|---|---|
| Equation | `\tag{n}` inside the math, `^eq-n` on the line after | `[[#^eq-n\|(n)]]` |
| Worked example | `> [!example] Example n — …`, `^ex-n` on the line after | `[[#^ex-n\|Example n]]` |

Both counters run through the whole note. `lesson.py summary` reports the last value of each, so a resumed session continues them. Course notes use the book's equation numbers instead.

## State files

Everything under `.claude/` in this table is gitignored.

| File | Holds | Written by |
|---|---|---|
| `<project>/.mcp.json` | registration of the quiz server | `install.sh` |
| `.claude/md-log.json` | the note linked last and the session that linked it | `md_log.py link` / `unlink` |
| `.claude/md-log-state/<session>.json` | per session: transcript cursor, linked note, dedup keys, header dates | `md_log.py` |
| `.claude/md-log-state/quiz-logged.json` | tool-use ids of quizzes the server has logged | `quiz_server.py` |
| `.claude/md-log-state/quiz-last-asked.json` | option order of a quiz waiting to be re-asked | `quiz_server.py` |
| `.claude/md-log-state/quiz-target.json` | which note each recent quiz call belongs to | `md_log.py` (`PreToolUse`) |
| `.claude/md-log-state/course.json` | the current course | `book.py` |
| `.claude/md-log-state/md-log.log` | one line per hook invocation | `md_log.py` |
| `.claude/md-log-state/quiz-server.log` | why a popup fell back to the form | `quiz_server.py` |
| `.claude/md-log-state/trash/` | reset lessons | `lesson.py reset` |
| `<notes>/.checkpoints/<note>.md` | checkpoints of a lesson note | `lesson.py checkpoint` |
| `courses/<name>/.course/book.json` | the page map | `book.py new` |
| `courses/<name>/.course/state.json` | syllabus, progress, exercise records, settings | `book.py` |
| `<project>/viz/` | published diagrams | the render scripts |

## Fragile parts

In order of how likely they are to bite.

1. **Transcript format.** It is internal to Claude Code. A release could change it and silence the prose mirror until the parser is updated. Prompts and quizzes are unaffected.
2. **The teacher skipping written text.** When a skill lets text and a quiz share a reply, the model can go straight to the quiz and write no text at all. The rule that the opener is its own reply prevents this; keep to it in any new skill.
3. **Stop-hook timing.** The 8-second wait covers what has been observed. Late prose is picked up at the next prompt.
4. **The narration filter.** It is a heuristic; every miss so far was a new phrasing. Tune `NARRATION_RE`, `NARRATION_ANY_RE` and `NARRATION_INTENT_RE` in `md_log.py`. The main defence is the no-narration rule in `CLAUDE.md` and the teach skill.
5. **The first prompt of a fresh session.** A session mirrors nowhere until a skill links a note, so a first message typed as plain text ("I am stuck on 2.3") is not in the note, though the teacher's later replies are. Starting with the command (`/exercise 2.3`) avoids the gap.
6. **The housekeeping list.** Which commands are muted is a fixed list. A new command, or a new sub-command of `/course` or `/lesson`, has to be added to `ADMIN_COMMANDS` if its reply is not lesson content.
7. **The book map.** It is good when the PDF was made with LaTeX and hyperref. An outline with wrong or missing destinations gives wrong ranges; `book.py toc --all` shows the map, and `new --toc` replaces it. A scanned book has no text layer, so the text-search fallback finds nothing; the Read tool still sees the pages.
8. **The elicitation fallback.** Claude Code's form truncates the question to one line. Use tmux.
9. **Multi-select quizzes.** Checkboxes in the popup; one boolean per option in the fallback. Not yet used in a real lesson.

## Testing

There is no test suite. Changes have been tested in three ways:

- **Scripts directly.** `book.py`, `lesson.py` and the `md_log.py` commands run from a shell. A hook is tested by piping it a JSON payload with a hand-made transcript.
- **The popup** in detached tmux sessions, with keys fed through the attached client's pty.
- **Skills** with a headless run in a scratch copy of the project:

  ```bash
  claude -p "/course next" --allowedTools "Read" "Bash(python3 .claude/hooks/*)" "Skill" --output-format json
  ```

  A scratch folder is not trusted, so the allow list in `settings.json` is ignored there; pass `--allowedTools`. The hooks still run, so the note is written and can be inspected.

See the commit messages and [worklog.md](worklog.md) for what was verified when.
