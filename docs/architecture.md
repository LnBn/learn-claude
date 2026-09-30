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
4. The server grades, writes the result block to the note, records the tool-use id in
   `md-log-state/quiz-logged.json` (so the Stop-hook replay does not log it twice), and returns a short text
   result to the model plus a `QUIZ_JSON:` line the log hook can parse when rebuilding a note.

Why a tool rather than the model grading: the model would need a second turn to mark the answer. The server
grades on the keypress, exactly like the original pi extension.

### The note mirror (`hooks/md_log.py`)

Three hooks call the same script:

- `UserPromptSubmit` logs your prompt live (after replaying anything the previous Stop missed).
- `PostToolUse` on `AskUserQuestion` logs non-graded Q&A live.
- `Stop` reads the session transcript from a per-session cursor and logs the teacher's prose. Claude Code
  sometimes fires Stop before the transcript is flushed, so the hook waits up to 8 s for an assistant entry.

The transcript is Claude Code's internal JSONL; the parser is defensive and never blocks the session.
Filters drop harness-injected user messages (`<system-reminder>`, `<task-notification>`, slash-command
payloads) and short assistant narration: text under 300 characters that shares an API message with a tool call,
or that starts like "I'll…", "Let me…", "waiting on your answer". Long text is always kept.

State: `md-log.json` (the vault-wide default file) and `md-log-state/<session>.json` (cursor, the session's own
file, dedup keys). A session linked with `--session` keeps its own file, so two sessions can mirror two notes;
the quiz server only knows the vault-wide default.

`md_log.py rebuild <out.md> <transcript.jsonl>...` regenerates a note from transcripts with the current filters.

### Resuming (`hooks/lesson.py`, `skills/lesson`)

`/lesson pause` makes the teacher end its reply with a `> [!summary] Checkpoint — <date>` callout; the mirror
puts it in the note. `/lesson resume <file>` links the note and runs `lesson.py summary`, which prints only:
the hand-off note if one exists (`<stem> — Resume Here.md`), the latest checkpoint, the latest mermaid map, a
quiz tally and the last twelve quiz outcomes. The teacher reads that brief, never the whole note, re-checks the
established nodes with a few quizzes, and continues. pi's callout titles are understood, so pi-era notes resume too.

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
3. **Narration filter.** Heuristic. Tune `NARRATION_RE` / `NARRATION_ANY_RE` in `md_log.py` if it drops or
   keeps the wrong things. The main defence is the no-narration rule in `CLAUDE.md` and the teach skill.
4. **Elicitation fallback.** Claude Code's form truncates the message to one line. Use tmux.
5. **Multi-select in the popup** is checkboxes; in the elicitation fallback it is one boolean per option.

## Testing notes

Everything here was tested with scripted clients and detached tmux sessions (keys fed through the attached
client's pty), plus headless `claude -p` runs for the hooks, skills and subagents. See the commit messages.
