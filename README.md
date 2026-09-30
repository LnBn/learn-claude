# learn-claude

A personal AI tutor that runs inside [Claude Code](https://code.claude.com) on a Claude subscription.
It is a port of [amosblomqvist/learn](https://github.com/amosblomqvist/learn), the learning system from
[How I Use AI to Learn Things](https://www.youtube.com/watch?v=kzcI5F4tGiU), from the pi harness to Claude Code.
The teaching philosophy is his. The plumbing is new.

**What you get**

- A teacher that follows a fixed process: probe what you know, agree a plan with a dependency map, then teach one
  node at a time as a *section*: written exposition, an easy check quiz, a harder apply quiz.
- Graded quizzes in a terminal popup, marked the instant you answer, with the explanation.
- A markdown mirror of every lesson that renders in Obsidian (LaTeX, mermaid maps, diagrams), split by session.
- Lessons that span days: pause with a checkpoint, resume later from the note, not from the chat.
- Fact checks by a web-research subagent and diagrams drawn, rendered and visually verified by maker subagents.

Everything runs locally except the model calls, which go through your Claude Code login. No API key.

## Requirements

| Needed | For |
|---|---|
| Claude Code ≥ 2.1, Python 3.10+ | everything |
| tmux ≥ 3.2 | the quiz popup (outside tmux you get Claude Code's cramped form) |
| Obsidian (or any markdown viewer) | reading the lesson notes rendered |
| Node ≥ 18 + npm, Chrome or Chromium | Mermaid diagrams |
| `rsvg-convert`, ImageMagick, or Chrome | SVG diagrams |

Without Node or Chrome everything still works; you lose the pictures.

## Install

This repository **is** a `.claude` directory. Clone it into the folder you will learn in, ideally a folder inside
your Obsidian vault so the notes and diagrams render in place.

```bash
cd ~/path/to/vault
git clone https://github.com/LnBn/learn-claude .claude
bash .claude/scripts/install.sh      # installs mermaid-cli, writes .mcp.json, smoke-tests the renderers
```

Then start Claude Code **from that folder, inside tmux**:

```bash
tmux
claude
```

The first time, accept the trust dialog and the prompt to enable the project's `quiz` MCP server.
Update later with `git -C .claude pull`. Your log state is gitignored, so pulling never touches it.

## Daily use

```
/md-log lessons/tcp.md                  # mirror this session into a note
teach me how TCP achieves reliability
```

or, to continue a lesson from an earlier day:

```
/lesson resume lessons/tcp.md
```

You can type a question at any prompt. The teacher answers it before moving on.

### What a lesson looks like

1. **Probe.** Graded questions to find the edge of what you know, and a question about what you want.
2. **Plan.** A short approach and a mermaid dependency map: unconditional truths at the roots, your goal at the
   sink. Nothing is taught until you approve it.
3. **Teach**, one node per section:
   - `### Node name`
   - **Read.** A complete written exposition: why this node now, the truth or derivation, how it hangs off earlier
     nodes, a worked example or code.
   - **Check.** One quiz answerable from a close reading.
   - **Apply.** One quiz that needs reasoning, a calculation, or running code.
   - A failed apply is re-taught before anything is built on it.

### The quiz popup

| Key | Action |
|---|---|
| ↑ ↓ or j k | move |
| 1–9 | jump to an option (toggles it in multi-select) |
| Space | toggle (multi-select) |
| Enter | submit |
| Tab | type a note that is sent with your answer |
| `?` | ask the teacher a question *before* answering; the quiz is re-asked after the answer |
| PgUp PgDn | scroll |
| Esc | cancel the quiz |

"I don't know" is always the last option. Choosing it is recorded as a gap, not a wrong answer.
After you answer, the popup shows ✓ or ✗, the correct answer and the explanation. Any key closes it.
Math is shown as Unicode in the popup (x², αᵢ, √(a²+b²), ∑ᵢ₌₁ⁿ); the note keeps the real LaTeX.

### Lessons over several sessions

The note is the state, not the chat. One note per topic.

```
/lesson pause                    # writes a Checkpoint block: goal, confirmed nodes, shaky nodes, next node
/lesson resume lessons/tcp.md    # next time: links the note, reads only the checkpoint + map + recent quiz
                                 #   outcomes, re-checks what was established, continues from "next"
/lesson status lessons/tcp.md    # where the lesson stands, no teaching
```

The teacher writes the checkpoint by itself when you say you are stopping. A lesson started under pi resumes the
same way; its `… — Resume Here.md` companion note is picked up automatically.

### The note

Each session starts with `## Session — <date>`. Your prompts appear as `YOU` quotes, the teacher's prose is
written bare, quizzes are callouts with the result, and diagrams are `![[viz-….png|500]]` embeds into `viz/`.
Session chatter ("I'll load the skill", "waiting on your answer") is filtered out, so the note reads like a
textbook chapter. `/md-unlog` stops mirroring.

## Layout

```
.claude/
  CLAUDE.md              project rules: teach, don't narrate, plain technical English
  settings.json          hooks (md-log) and pre-approved commands
  mcp.json               copied to <project>/.mcp.json by install.sh: registers the quiz server
  skills/
    teach/               the teaching philosophy and process (the heart of it)
    visualize/           when and how to ask a maker for a diagram
    lesson/              /lesson resume | pause | status
    md-log/, md-unlog/   /md-log <file>, /md-unlog
  agents/
    researcher.md        web research and fact verification
    mermaid-maker.md     draws, renders, LOOKS at, and publishes a Mermaid diagram
    svg-maker.md         same for hand-written SVG (geometry, plots)
  mcp/
    quiz_server.py       the quiz tool: an MCP server, no dependencies
    quiz_popup.py        the curses popup shown via tmux display-popup
    latex_text.py        LaTeX → Unicode for the popup
  hooks/
    md_log.py            mirrors the session into the note (UserPromptSubmit / PostToolUse / Stop hooks)
    lesson.py            extracts the resume brief from a note
  scripts/
    install.sh           one-off setup
    render-mermaid.sh    Mermaid → PNG (mermaid-cli + local Chrome)
    render-svg.sh        SVG → PNG (rsvg-convert → ImageMagick → Chrome)
  visual-tools/          package.json for mermaid-cli
```

See [docs/architecture.md](docs/architecture.md) for how the pieces fit and what is fragile.

## Customising

- The teach skill is written for one learner. Edit `skills/teach/SKILL.md` to fit how you learn.
- Subagent models are `sonnet` in `agents/*.md`. Change `model:` there.
- `CLAUDE.md` holds the house rules for the teacher's voice.

## Troubleshooting

- **Quiz shows a one-line form with "Your answer: not set"** instead of a popup: the popup did not trigger. See
  `.claude/md-log-state/quiz-server.log` for the reason (usually Claude Code was started outside tmux). Restart
  Claude Code from inside tmux; the server is spawned at session start.
- **No quiz tool at all** (questions come as plain AskUserQuestion prompts): run `/mcp` and check `quiz` is listed
  and enabled; make sure `.mcp.json` exists in the project root.
- **Teacher prose missing from the note**: Claude Code's transcript format is internal and may change between
  releases. `md_log.py` parses it defensively; prompts and quizzes come from hook payloads and are unaffected.
  Regenerate a note with `python3 .claude/hooks/md_log.py rebuild <out.md> <transcript.jsonl>...`.
- **Hooks not firing**: Claude Code must be started from the folder that contains `.claude`, not a subfolder.

## Credits

Teaching philosophy, skills and agent prompts: [Amos Blomqvist](https://github.com/amosblomqvist/learn).
Port to Claude Code: Lachlan Burton, with Claude.
