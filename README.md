# learn (Claude Code edition)

A port of [amosblomqvist/learn](https://github.com/amosblomqvist/learn) — the AI learning system from
[How I Use AI to Learn Things](https://www.youtube.com/watch?v=kzcI5F4tGiU) — from the pi harness to
**Claude Code**, so it runs on a Claude subscription with no API billing.

The teaching philosophy is unchanged. What changed is the plumbing:

| pi piece | Claude Code piece here |
|---|---|
| `skills/teach` | `skills/teach/SKILL.md` — same text, tool names mapped, learner pronouns neutralised |
| `skills/visualize` | `skills/visualize/SKILL.md` — dispatches makers with the Agent tool |
| `extensions/quiz` (graded popup tool) | **Quiz protocol** inside the teach skill: one `AskUserQuestion` with header `Quiz` + an automatic "I don't know" option, then Claude grades (✓/✗, correct answer, explanation) |
| `extensions/ask-user-question` | the built-in `AskUserQuestion` tool |
| `extensions/md-log` | `hooks/md_log.py` wired to `UserPromptSubmit` / `PostToolUse` / `Stop` hooks; `/md-log <file>` and `/md-unlog` skills |
| `extensions/visual-tools` | `scripts/render-mermaid.sh` + `scripts/render-svg.sh` (mermaid-cli via your installed Chrome; rsvg → ImageMagick → headless Chrome for SVG) |
| `agents/researcher`, `mermaid-maker`, `svg-maker` | `agents/*.md` custom subagents (WebSearch/WebFetch for the researcher; Bash/Read/Write/Edit for the makers, which LOOK at their PNG with Read) |

## Install

This directory **is** a `.claude` directory. From your learning project's root (ideally a folder inside your Obsidian vault):

```bash
cp -r /path/to/learn-claude .claude      # or: git clone <this repo> .claude
bash .claude/scripts/install.sh          # installs mermaid-cli (one-off, needs node + npm)
claude                                   # open Claude Code here and accept the trust dialog
```

Requirements: Claude Code ≥ 2.1, Python 3, Node ≥ 18. For visuals: Chrome/Chromium installed (Mermaid), and any of
`rsvg-convert`, ImageMagick or Chrome (SVG). Without them everything still works, you just lose the pictures.

## Use

```
/md-log lessons/2026-09-30-tcp.md    # mirror the session into a note (Obsidian renders math, mermaid, embeds)
teach me how TCP achieves reliability
```

Claude loads the `teach` skill on its own whenever it is explaining something (CLAUDE.md nudges it too). It will
probe your level with graded questions, ask about your goal, present a plan with a mermaid dependency map, wait for
your go-ahead, then teach node by node. Visuals arrive as `![[viz-…png|500]]` embeds pointing into `viz/`.

`/md-unlog` stops mirroring. Logging state lives in `.claude/md-log.json` and `.claude/md-log-state/` (gitignored).

## Notes

- **Quizzes are graded by Claude, not by a tool.** The pi version hid the correct answer inside a tool; here Claude
  holds it and grades in its next message. It is instructed to randomise option order by hand and never to put
  justification in options. If you want tool-side grading, the natural upgrade is an MCP server exposing a `quiz`
  tool that uses MCP elicitation for the popup.
- **The transcript format Claude Code writes is internal** and may change between releases. `md_log.py` parses it
  defensively and never blocks the session; if a release changes the format, assistant prose may stop appearing in
  the log until the parser is updated (prompts and Q&A are logged from hook payloads and are unaffected).
- The `Stop` hook waits up to 8 s for the transcript to flush; prose that still lands late is picked up at your
  next prompt.
- Subagent models are set to `sonnet` in `agents/*.md`; change `model:` there if you prefer.
- The teach skill is written for one learner. Edit it to fit how you learn best.
