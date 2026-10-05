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
- Courses that follow a textbook: give it a PDF, pick the chapters, and the lessons are condensed from the book's
  own pages, with hints in steps for the book's exercises.
- Fact checks by a web-research subagent and diagrams drawn, rendered and visually verified by maker subagents.

Everything runs locally except the model calls, which go through your Claude Code login. No API key.

## Requirements

| Needed | For |
|---|---|
| Claude Code ≥ 2.1, Python 3.10+ | everything |
| tmux ≥ 3.2 | the quiz popup (outside tmux you get Claude Code's cramped form) |
| Obsidian (or any markdown viewer) | reading the lesson notes rendered |
| Node ≥ 18 + npm, Chrome or Chromium | Mermaid diagrams |
| poppler (`pdfinfo`, `pdftotext`), `mutool` | textbook courses (`mutool` reads the PDF's outline) |
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

0. **Open.** A written opening before any question. For a beginner request ("from the basics") it is a one or
   two paragraph overview of the subject, then one question: probe my level first, or start from the beginning,
   and what do you want from this. Otherwise a few sentences on the topic and what is about to happen; the
   teacher stops there, and the first quiz comes after you type `ready`. A quiz is never the first thing you read.
1. **Probe.** Graded questions to find the edge of what you know, with a step of reasoning where possible.
2. **Plan.** Under a `### Plan` heading: a short approach and a mermaid dependency map, unconditional truths at
   the roots, your goal at the sink. Nothing is taught until you approve it.
3. **Teach**, one node per section:
   - `### Node name`
   - **Read.** A complete written exposition: why this node now, the truth or derivation, how it hangs off earlier
     nodes, a worked example or code. The teacher stops here; read it in the note, then type `ready`.
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
/lesson pause                    # saves a checkpoint (goal, confirmed nodes, shaky nodes, next node) to
                                 #   lessons/.checkpoints/<name>.md — hidden from Obsidian, the note stays clean
/lesson resume lessons/tcp.md    # next time: links the note, reads only the checkpoint + map + recent quiz
                                 #   outcomes, asks once whether to run a recall check, continues from "next"
/lesson status lessons/tcp.md    # where the lesson stands, no teaching
/lesson reset lessons/tcp.md     # start over: note + checkpoints moved to .claude/md-log-state/trash/
```

The teacher writes the checkpoint by itself when you say you are stopping. The resume question (recall check or
continue) is asked in the terminal only and never appears in the note; declining it resumes straight from the
next node. A lesson started under pi resumes the same way; its `… — Resume Here.md` companion note is picked up
automatically.

### Following a textbook

A course is a textbook (PDF), a syllabus chosen from it, and one lesson note per chapter. The lesson replaces
reading the section, like a lecture; the book stays there for depth.

```
/course new ~/books/murphy-pml1.pdf pml1   # map the book, read the preface, ask what to cover and why
/course next                               # teach the next section of the syllabus
/course study 4.2                          # or a section of your choice
/course status                             # progress; /course toc 4 lists a chapter
/course list                               # all your courses; /course use <name> switches to another
/exercise 2.3                              # help with Exercise 2.3 (or just say you are stuck on it)
/course assess 2.5 2.6                     # these exercises are assessed coursework
```

- **Setup.** The book is mapped once, from its PDF outline: every section gets a page range. The teacher reads
  the preface for suggested tracks and asks three things: what to cover (the whole book, the sections the book
  does not mark optional, or your own list such as `2 3.1-3.4 5`), what you want from it, and when it may show
  full solutions. A PDF without an outline is mapped from its contents pages instead.
- **Lessons.** A new chapter opens with an overview to read: what the chapter covers, section by section, what
  it rests on, and a map of its sections. Then you choose: `ready` starts the first section, `probe` first runs
  a few graded questions on the prerequisites. You are never probed unasked. Before each section the teacher reads that section's
  pages, nothing else, and never quotes the book from memory. The section is taught as usual (read, `ready`, check, apply) in the book's notation, with
  the page reference under each heading. The book is the backbone, not the boundary: the teacher adds material
  from outside it when that helps (a better intuition, a link to another field, what has changed since), says
  when something is not in the book, and may suggest further reading. Equations keep the book's numbers, `(2.51)` in the note is `(2.51)`
  in the book, so the exercises' references resolve. Apply quizzes may be adapted from the book's exercises,
  with the source named.
- **Exercises.** Help comes one step at a time: what the exercise rests on, the strategy, the next step from
  where your work stops, a check of your answer. You can paste your work or give the path of a photo. A full
  solution is shown only as the course allows (by default: after you have shown an attempt and asked), and
  never for an exercise marked assessed, which is also never used as a quiz.
- **Files.** `courses/<name>/<name>.md` is the index (syllabus with progress, exercise table; generated, do not
  edit), `<name>-ch02.md` the lesson note of chapter 2, `<name>-ch02-exercises.md` its exercise help. The page
  map and the progress are in the hidden `.course/` folder beside them. `/lesson pause` and checkpoints work on
  a chapter note as on any lesson.
- **Several courses.** Each course keeps its own syllabus, progress, notes and checkpoints. Commands act on the
  current course, the one created or chosen last. `/lesson pause` the one you are in, `/course use <name>` to
  switch, `/course next` to continue the other from where it stopped.

If the PDF is outside the folder Claude Code runs in, it asks once for permission to read it.

### Environments, notation and equation numbers

Definitions, theorems, proofs, notation lists, remarks and intuition boxes are written as callouts
(`> [!definition] Best response`, `> [!theorem] …`, `> [!notation]`, …), styled by the CSS snippet the installer
adds to the vault. Every symbol in an equation is defined in the text before it appears, or in a `[!notation]`
callout directly after the equation.

Equations the lesson refers back to are numbered and linkable, with no plugin:

```markdown
$$
p(\theta \mid x) = \frac{p(x \mid \theta)\,p(\theta)}{p(x)} \tag{3}
$$
^eq-3

By [[#^eq-3|(3)]], the posterior is proportional to likelihood times prior.
```

Numbers run through the whole note; a resumed session continues from the last one. Worked examples are
`> [!example] Example n — …` callouts with a `^ex-n` id, numbered the same way and cited as `[[#^ex-n|Example n]]`.
Their calculations are set out one step per line, in a list or an `aligned` display block, so each line can be
checked on paper.

### The note

Each session starts with `## Session — <date>`. Your prompts appear as `> **You:** …` quotes, the teacher's
prose is written bare, quizzes are callouts with the result, and diagrams are `![[viz-….png|500]]` embeds
into `viz/`. Blocks are separated by one blank line. Kept out of the note: session chatter ("I'll load the
skill", "waiting on your answer", "the lesson is paused at…"), pacing prompts (`ready`, `ok`, `next`), the
resume question, checkpoints (they live in the sidecar) and status lines from the scripts. The note reads like
a textbook chapter. `/md-unlog` stops mirroring.

If you ask a question in the quiz popup with `?`, the note shows the quiz block, an "Asked before answering"
note, the teacher's answer, then the grade; the re-asked quiz is not repeated.

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
    course/              /course new | next | study | status | toc | select | assess | solutions
    exercise/            hints in steps for the textbook's exercises
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
    book.py              maps a textbook PDF to page ranges; keeps a course's syllabus and progress
  scripts/
    install.sh           one-off setup
    render-mermaid.sh    Mermaid → PNG (mermaid-cli + local Chrome)
    render-svg.sh        SVG → PNG (rsvg-convert → ImageMagick → Chrome)
  visual-tools/          package.json for mermaid-cli
  obsidian/
    learn-callouts.css   styles for the lesson environments (definition, theorem, proof, notation, …);
                         install.sh copies it into <vault>/.obsidian/snippets and enables it
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
- **"The quiz is running in the background"**: Claude Code moves tool calls that run longer than two minutes to
  the background. `settings.json` sets `CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS=0` to turn that off for this project,
  so a quiz can wait as long as you need. If you see the message, the setting is not in effect: restart Claude
  Code from the project folder.

## Credits

Teaching philosophy, skills and agent prompts: [Amos Blomqvist](https://github.com/amosblomqvist/learn).
Port to Claude Code: Lachlan Burton, with Claude.
