# Architecture

How the pieces of learn-claude fit together, and where it is fragile. Read the [README](../README.md) first.

## The pieces

```
              ┌──────────────────────────── Claude Code session (in tmux) ────────────────────────────┐
              │                                                                                        │
  you ──────▶ │  teach skill ──▶ model ──┬─▶ quiz tool (MCP) ──▶ tmux popup ──▶ graded ──▶ note + model │
              │       ▲                  ├─▶ Agent: researcher (WebSearch/WebFetch)                     │
              │       │                  ├─▶ Agent: mermaid-maker / svg-maker ──▶ render-*.sh ──▶ viz/ │
              │  lesson skill            └─▶ AskUserQuestion (non-graded questions)                    │
              │       ▲                                                                                 │
              │  hooks: UserPromptSubmit / PostToolUse / Stop ──▶ md_log.py ──▶ the note                │
              └────────────────────────────────────────────────────────────────────────────────────────┘
```

### Skills (`skills/*/SKILL.md`)

Prompt files Claude Code loads on demand. `teach` is auto-loaded whenever the model explains something (its
description says so; `CLAUDE.md` reinforces it). `lesson`, `md-log` and `md-unlog` are user-invoked slash
commands; they run a script via Bash and are pre-approved in `settings.json`.

### The quiz tool (`mcp/`)

`quiz_server.py` is a stdio MCP server written against the JSON-RPC protocol directly, so it needs nothing
installed. Claude Code starts it from `.mcp.json` when the session starts. One tool, `quiz`:

1. The model calls it with the question, options (each with a `value`), `correctAnswer` by value, and an
   `explanation`. Bad input (unknown value, a hand-added "not sure" option) is returned as an error.
2. The server shuffles the options, appends "I don't know", and writes the question block to the note.
3. If `$TMUX` is set, it runs `tmux display-popup -E python3 quiz_popup.py spec.json result.json` and blocks.
   The popup is plain curses: wrapped text, bold, Unicode math (`latex_text.py`), a note field, `?` to ask
   first. On submit it shows the grade and explanation, then writes `result.json`.
   Without tmux it falls back to MCP elicitation, which Claude Code renders as a cramped one-line form.
4. The server grades, writes the result block to the note, and returns a short text result to the model plus
   a `QUIZ_JSON:` line the log hook can parse when rebuilding a note. It records the tool-use id in
   `md-log-state/quiz-logged.json` as soon as it has written the question block, so the hook's replay never
   logs that quiz a second time.

`?` in the popup sends a question instead of an answer: the server logs an "Asked before answering" note and
tells the model to answer, then call `quiz` again. The re-ask is recognised by its option set; it reuses the
order the learner saw and does not log the question block again (`md-log-state/quiz-last-asked.json`).

Claude Code moves a tool call to the background after two minutes. `settings.json` sets
`CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS=0` so a quiz can stay open as long as the learner needs. If a call is
backgrounded anyway (setting not loaded), the result arrives as a `<task-notification>`; the teach skill waits
for it, and rebuilds place it where the quiz was asked.

Why a tool rather than the model grading: the model would need a second turn to mark the answer. The server
grades on the keypress, exactly like the original pi extension.

### The note mirror (`hooks/md_log.py`)

Four hooks call the same script:

- `UserPromptSubmit` logs your prompt live (after replaying anything the previous Stop missed). Pacing prompts
  (`ready`, `ok`, `next`, …) are not logged.
- `PreToolUse` on the quiz tool and `AskUserQuestion` replays the transcript first, so prose already persisted
  lands before the tool's own block.
- `PostToolUse` on `AskUserQuestion` logs non-graded Q&A live (except the `Resume` question); on the quiz tool
  it replays the transcript and **inserts** prose that preceded the call above the quiz block. This matters
  because in interactive mode Claude Code persists an assistant message only after its tool call returns, so
  text written in the same message as a quiz call is not on disk when the server logs the question.
- `Stop` reads the session transcript from a per-session cursor and logs the teacher's prose. Claude Code
  sometimes fires Stop before the transcript is flushed, so the hook waits up to 8 s for an assistant entry.

Because of that persistence order, the teach skill ends the reading turn before the check quiz: the learner
types `ready`, and only then is the quiz called. That is the reliable fix; the insertion is the safety net.

The session header (`## Session — date`) is written with the first content block, never on hook entry, so an
abandoned session leaves no header. Every hook invocation is logged to `md-log-state/md-log.log`.

The transcript is Claude Code's internal JSONL; the parser is defensive and never blocks the session.
Filters drop harness-injected user messages (`<system-reminder>`, `<task-notification>`, slash-command
payloads) and short assistant narration: text under 300 characters that shares an API message with a tool call,
or that starts like "I'll…", "Let me…", "waiting on your answer". Long text is always kept.

State: `md-log.json` (the vault-wide default file) and `md-log-state/<session>.json` (cursor, the session's own
file, dedup keys). A session linked with `--session` keeps its own file, so two sessions can mirror two notes;
the quiz server only knows the vault-wide default. Linking a note the session is already mirroring (for
example `/lesson resume` after `/lesson pause`) keeps the cursor and dedup keys; only a different file resets
them for a backfill.

`md_log.py rebuild <out.md> <transcript.jsonl>...` regenerates a note from transcripts with the current filters.

### Resuming (`hooks/lesson.py`, `skills/lesson`)

`/lesson pause` has the teacher run `lesson.py checkpoint <note>` with the handoff on stdin; it is appended to
the hidden sidecar `<dir>/.checkpoints/<name>.md`, never to the note. `/lesson resume <file>` links the note
and runs `lesson.py summary`, which prints only: the latest sidecar checkpoint (or a legacy in-note checkpoint,
or a pi hand-off note `<stem> — Resume Here.md`), the latest mermaid map, a quiz tally, the last twelve quiz
outcomes and the highest equation number used. The teacher reads that brief, never the whole note, asks once
whether to run a recall check (that question is not logged), and continues from the next node. `/lesson reset`
moves the note and sidecar to `md-log-state/trash/`. pi's callout titles are understood, so pi-era notes resume.

### Visuals (`agents/*-maker.md`, `scripts/render-*.sh`)

The `visualize` skill has the teacher brief a maker subagent with one idea and few elements. The maker writes
source to `/tmp/learn-viz/`, renders with the script, **reads the PNG** (Claude Code's Read tool shows images),
iterates, then renders with `--publish <slug>` which copies the PNG to `<project>/viz/viz-<slug>-<ts>.png`.
The teacher embeds `![[viz-….png|500]]`; Obsidian resolves embeds by filename anywhere in the vault.

Mermaid renders through the bundled `@mermaid-js/mermaid-cli` driven by an installed Chrome (puppeteer
downloads nothing). SVG tries `rsvg-convert`, then ImageMagick 7 (`magick`), then 6 (`convert`), then headless
Chrome.

## Fragile parts, in order

1. **Transcript format.** Internal to Claude Code. A release could change it and silence the prose mirror until
   the parser is updated. Prompts and quizzes are unaffected.
2. **Stop-hook timing.** The 8 s wait covers what has been observed; late prose is picked up at the next prompt.
3. **Narration filter.** Heuristic. Text under 300 characters is dropped when it starts like narration
   ("I'll…", "Let me load…", "Trying…", "The researcher is…"), says it is waiting or paused, or prefaces a tool
   call while announcing an intent or being under 120 characters; short narration paragraphs at the edges of a
   longer block are trimmed. Harness messages ("[Request interrupted by user]", task notifications) never appear. Tune
   `NARRATION_RE` / `NARRATION_ANY_RE` / `NARRATION_INTENT_RE` in `md_log.py`. The main defence is the
   no-narration rule in `CLAUDE.md` and the teach skill.
4. **Elicitation fallback.** Claude Code's form truncates the message to one line. Use tmux.
5. **Multi-select in the popup** is checkboxes; in the elicitation fallback it is one boolean per option.

## Obsidian side

`obsidian/learn-callouts.css` styles the environment callouts (`definition`, `theorem`, `lemma`,
`proposition`, `corollary`, `proof`, `notation`, `remark`, `intuition`, and `example` for worked examples);
`install.sh` copies it into `<vault>/.obsidian/snippets/` and enables it in `appearance.json`. Equation and
example references use core features only: `\tag{n}` for an equation number, `Example n — …` in the callout
title for a worked example, a `^eq-n` / `^ex-n` block id on the line after the block, and `[[#^eq-n|(n)]]` /
`[[#^ex-n|Example n]]` links. Both counters run through the whole note; `lesson.py summary` reports the last
value of each so a resumed session continues them. Calculations inside an example are set out one step per
line (a list or an `aligned` display block), not run inline.

## Testing notes

Everything here was tested with scripted clients and detached tmux sessions (keys fed through the attached
client's pty), plus headless `claude -p` runs for the hooks, skills and subagents. See the commit messages.
