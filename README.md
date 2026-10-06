# learn-claude

A personal AI tutor that runs inside [Claude Code](https://code.claude.com) on a Claude subscription.

It is a port of [amosblomqvist/learn](https://github.com/amosblomqvist/learn), the learning system from [How I Use AI to Learn Things](https://www.youtube.com/watch?v=kzcI5F4tGiU), from the pi harness to Claude Code. The teaching philosophy is his. The plumbing is new.

**What you get**

- **A teacher with a fixed method.** It finds what you already know, agrees a plan with you, then teaches one idea at a time: a text to read, an easy quiz, a harder quiz.
- **Graded quizzes in a popup.** Your answer is marked the moment you give it, with the explanation.
- **A lesson note in Obsidian.** Every lesson is mirrored into a markdown file with rendered math, diagrams and quiz results. It reads like a textbook chapter, not a chat log.
- **Lessons that span days.** Pause with a checkpoint and pick the lesson up again in a later session.
- **Courses that follow a textbook.** Give it a PDF and pick the chapters. Lessons are condensed from the book's own pages, and you get hints in steps on the book's exercises.
- **Checked facts and checked pictures.** A research subagent verifies claims on the web. Diagram subagents render each picture and look at it before it reaches you.

Everything runs locally except the model calls, which go through your Claude Code login. No API key is needed.

**Contents:** [Quick start](#quick-start) · [How a lesson runs](#how-a-lesson-runs) · [Quizzes](#quizzes) · [Stopping and resuming](#stopping-and-resuming) · [Following a textbook](#following-a-textbook) · [The lesson note](#the-lesson-note) · [Commands](#commands) · [Repository layout](#repository-layout) · [Customising](#customising) · [Troubleshooting](#troubleshooting)

## Quick start

### Requirements

| Needed | For |
|---|---|
| Claude Code ≥ 2.1, Python 3.10+ | everything |
| tmux ≥ 3.2 | the quiz popup |
| Obsidian, or any markdown viewer | reading the lesson notes rendered |
| poppler (`pdfinfo`, `pdftotext`, `pdftoppm`) and `mutool` | textbook courses |
| Node ≥ 18 with npm, and Chrome or Chromium | Mermaid diagrams |
| `rsvg-convert`, ImageMagick or Chrome | SVG diagrams |

Only the first row is essential. Without tmux, quizzes fall back to a cramped one-line form. Without Node or Chrome you lose the pictures and nothing else.

### Install

This repository **is** a `.claude` directory. Clone it into the folder you will learn in. The best place is the root of your Obsidian vault, so that notes and diagrams render in place.

```bash
cd ~/path/to/vault
git clone https://github.com/LnBn/learn-claude .claude
bash .claude/scripts/install.sh
```

The install script installs the Mermaid renderer, registers the quiz server in `.mcp.json`, and smoke-tests the renderers. If the folder is an Obsidian vault, it also adds the callout styles to it.

Then start Claude Code from that folder, inside tmux:

```bash
tmux
claude
```

The first time, accept the trust dialog and the prompt to enable the project's `quiz` MCP server.

### Update

```bash
git -C .claude pull
```

Then start a new Claude Code session; a running session keeps the old skills and settings. Your notes and log state are gitignored, so pulling never touches them.

### Your first lesson

```
/md-log lessons/tcp.md
teach me how TCP achieves reliability
```

The first line says where the lesson note goes. The second starts the lesson. Open `lessons/tcp.md` in Obsidian and read along there.

## How a lesson runs

Every lesson has the same four phases. Their size changes with the topic; their order does not.

1. **Opening.** A few sentences on the topic and on what is about to happen. The teacher stops here; type `ready` when you have read it.
   - If you ask to start "from the basics", the opening is a one or two paragraph overview of the subject. It ends with one question: probe my level first, or start from the beginning; and what do you want from this.
2. **Probe.** Graded questions that find the edge of what you know. They get harder until you miss, then narrow in.
3. **Plan.** Under a `### Plan` heading: a short approach and a dependency map. The roots are facts you can accept at face value; the sink is your goal. Nothing is taught until you approve it.
4. **Teach.** One node of the map at a time. Each node is a section with a fixed shape:

   | Step | What happens |
   |---|---|
   | Read | A complete written exposition: why this node now, the fact or derivation, how it hangs off earlier nodes, a worked example. The teacher stops. Read it in the note, then type `ready`. |
   | Check | One quiz that a close reading answers. |
   | Apply | One quiz that needs reasoning, a calculation or running code. |

   A failed apply is re-taught, with a fresh question, before anything is built on it.

You can type a question at any prompt. The teacher answers it before moving on.

## Quizzes

Quizzes open in a popup over the terminal.

| Key | Action |
|---|---|
| ↑ ↓ or j k | move |
| 1–9 | jump to an option (toggles it in multi-select) |
| Space | toggle an option (multi-select) |
| Enter | submit |
| Tab | type a note that is sent with your answer |
| `?` | ask the teacher a question *before* answering; the quiz comes back after the answer |
| `f` | open the figure the question refers to, in your image viewer (shown only when there is one) |
| PgUp PgDn | scroll |
| Esc | cancel the quiz |

- "I don't know" is always the last option. It is recorded as a gap, not as a wrong answer.
- After you answer, the popup shows ✓ or ✗, the correct answer and the explanation. Any key closes it.
- Math is shown as Unicode in the popup (x², αᵢ, √(a²+b²)). The note keeps the real LaTeX.

## Stopping and resuming

A lesson lives in its note, so you can stop and continue in a new session. Keep one note per topic.

```
/lesson pause                    # save a checkpoint: goal, confirmed nodes, shaky nodes, next node
/lesson resume lessons/tcp.md    # another day: continue from the checkpoint
/lesson status lessons/tcp.md    # where the lesson stands, no teaching
/lesson reset lessons/tcp.md     # start over; the note and its checkpoints go to a trash folder
```

- If you simply say you are stopping, the teacher saves a checkpoint too.
- Checkpoints live in a hidden file beside the note (`lessons/.checkpoints/<name>.md`), so the note stays clean.
- On resume the teacher reads the checkpoint, the map and your recent quiz results, and asks whether you want a short recall check before continuing.
- If you stopped right after reading a section, the next session points you back to that reading. Its check and apply questions follow when you type `ready`.
- Notes written by the original pi version resume the same way. A `… — Resume Here.md` companion note is picked up automatically.

## Following a textbook

A course is a textbook PDF, a syllabus chosen from it, and one lesson note per chapter. The lesson replaces reading the section, as a lecture does. The book stays there for depth.

```
/course new ~/books/murphy-pml1.pdf pml1   # set up a course
/course next                               # study the next section (also how you resume)
/course study 4.2                          # or a section of your choice
/exercise 2.3                              # help with Exercise 2.3
```

### Setting up

`/course new <book.pdf> [name]` maps the book once: every section gets a page range, taken from the PDF's outline. A PDF without an outline is mapped from its contents pages instead.

The teacher then reads the preface and asks three things:

1. **What to cover.** The whole book, only the sections the book does not mark optional, or your own selection such as `2 3.1-3.4 5`.
2. **What you want from it.** This is the goal the whole course is aimed at.
3. **When it may show full solutions** to exercises. The default is: after you have shown an attempt and asked.

If the PDF is outside the folder Claude Code runs in, Claude Code asks once for permission to read it.

### Studying

`/course next` teaches the next section of the syllabus. Use the same command to resume after a pause; it reads the chapter's checkpoint.

- **A new chapter opens with an overview** to read: what the chapter covers section by section, what it rests on, and a map of its sections. Then you choose: `ready` starts the first section, and `probe` first runs a few graded questions on the prerequisites.
- **Each section is taught like any lesson node**: read, `ready`, check, apply. The heading carries the book's section number and page reference.
- **The teacher reads the pages first.** Before each section it reads that section's pages, so the lesson matches your edition of the book.
- **The book is the backbone, not the boundary.** The teacher adds material from outside the book when that helps: a better intuition, a link to another field, what has changed since. It says when something is not in the book, and it may suggest further reading.
- **Notation and equation numbers are the book's.** `(2.51)` in the note is `(2.51)` in the book, so references in the exercises resolve.
- **Apply quizzes may come from the book's exercises**, with the source named.
- **The book's figures come into the note.** When a section or a quiz leans on a figure, the teacher crops it from the page into `viz/` and embeds it. A quiz about a figure shows it in the note, and `f` in the popup opens it.

When a chapter is finished the teacher says so, and `/course next` opens the next chapter in a new note.

### Exercises

Run `/exercise 2.3`, or just say you are stuck on Exercise 2.3. You can paste your work or give the path of a photo of it.

Help comes one step per reply:

1. **Orient.** What is asked, and which result of the chapter it rests on.
2. **Strategy.** The approach, without computation.
3. **Next step.** The first move from where your work stops.
4. **Check.** Whether your answer is right, and if not, the first line that goes wrong.
5. **Full solution.** Only as the course allows.

`/course assess 2.5 2.6` marks exercises as assessed coursework. Those get hints and checks, never a full solution, and they are never used as quiz questions.

### Several courses

Each course keeps its own syllabus, progress, notes and checkpoints. Commands act on the current course: the one created or chosen last.

```
/lesson pause        # save where you are in this course
/course list         # all courses, the current one marked
/course use pml1     # switch
/course next         # continue that course from its own checkpoint
```

### Files of a course

| File | What it is |
|---|---|
| `courses/<name>/<name>.md` | The index: syllabus with progress, and a table of exercises. Generated; do not edit. |
| `courses/<name>/<name>-ch02.md` | The lesson note of chapter 2. |
| `courses/<name>/<name>-ch02-exercises.md` | Exercise help for chapter 2. |
| `courses/<name>/.course/` | Hidden: the page map and the progress record. |
| `courses/<name>/.checkpoints/` | Hidden: checkpoints, as for any lesson. |

## The lesson note

A note holds the lesson and nothing else. A session writes to a note once you point it there, with `/md-log`, `/lesson resume`, `/course next`, `/course study` or `/exercise`; a session you have not pointed anywhere is not mirrored.

Each session starts with a `## Session — <date>` heading. Under it:

- your prompts, as `> **You:** …` quotes;
- the teacher's prose, written bare;
- quizzes, as callouts with your answer, the result and the explanation;
- diagrams, as `![[viz-….png|500]]` embeds of images in `viz/`, and figures cropped from a course's book (`![[pml1-fig-2-7.png|600]]`).

**Kept out of the note:**

- housekeeping commands and their replies, such as `/course list`, `/course status` or `/lesson pause`;
- session chatter ("I'll load the skill", "waiting on your answer");
- pacing words (`ready`, `ok`, `next`, `probe`);
- the resume question, checkpoints and status lines from the scripts.

`/md-unlog` stops mirroring altogether.

If you ask a question in the quiz popup with `?`, the note shows the quiz, an "Asked before answering" note, the teacher's answer, then the grade.

### Definitions, theorems and notation

Definitions, theorems, proofs, notation lists, remarks and intuition boxes are callouts, styled by the CSS snippet the installer adds to the vault:

```markdown
> [!definition] Best response
> A strategy $s_i^*$ is a **best response** to $s_{-i}$ if …

> [!notation]
> - $S_i$ — the set of strategies available to player $i$
```

Every symbol in an equation is defined in the text before it appears, or in a `[!notation]` callout directly after the equation.

### Numbered equations and examples

Equations the lesson refers back to are numbered and linkable, with no plugin:

```markdown
$$
p(\theta \mid x) = \frac{p(x \mid \theta)\,p(\theta)}{p(x)} \tag{3}
$$
^eq-3

By [[#^eq-3|(3)]], the posterior is proportional to likelihood times prior.
```

- Numbers run through the whole note. A resumed session continues from the last one.
- In a course note, equations carry the book's numbers instead: `\tag{2.51}` with the id `^eq-2-51`.
- Worked examples are `> [!example] Example n — …` callouts with a `^ex-n` id, cited as `[[#^ex-n|Example n]]`.
- Calculations in an example are set out one step per line, so each line can be checked on paper.

## Commands

| Command | What it does |
|---|---|
| `/md-log <note.md>` | Mirror this session into a note, including what was said so far. |
| `/md-unlog` | Stop mirroring. |
| `/lesson pause` | Save a checkpoint for the lesson in progress. |
| `/lesson resume <note.md>` | Continue a lesson from its checkpoint. |
| `/lesson status <note.md>` | Show where a lesson stands. |
| `/lesson reset <note.md>` | Start a lesson over; the note and checkpoints are moved to a trash folder. |
| `/course new <book.pdf> [name]` | Map a textbook and set up a course. |
| `/course next` | Study the next section of the current course, or resume it. |
| `/course study <section>` | Study a given section, for example `4.2`. |
| `/course status` | Progress of the current course. |
| `/course toc [chapter]` | The syllabus, or one chapter's sections, with progress marks. |
| `/course list` | All courses, the current one marked. |
| `/course use <name>` | Make another course the current one. |
| `/course select <spec>` | Change the syllabus: `all`, `unstarred`, or chapters, sections and ranges. |
| `/course assess <exercise>...` | Mark exercises as assessed coursework. |
| `/course solutions <policy>` | When full solutions may be shown: `never`, `after-attempt` or `on-request`. |
| `/exercise <id>` | Step-by-step help with an exercise from the course's book. |

Words you type at a prompt: `ready` when you have read a section, `probe` at a chapter overview to be tested first, or any question.

## Repository layout

```
.claude/
  CLAUDE.md              house rules for the teacher: teach, do not narrate, plain technical English
  settings.json          hooks, pre-approved commands, and the setting that keeps long quizzes in the foreground
  mcp.json               registers the quiz server; install.sh copies it to <project>/.mcp.json
  skills/
    teach/               the teaching philosophy and process (the heart of it)
    visualize/           when and how to ask for a diagram
    lesson/              /lesson pause | resume | status | reset
    course/              /course new | next | study | status | toc | list | use | select | assess | solutions
    exercise/            hints in steps for a textbook's exercises
    md-log/, md-unlog/   /md-log <file>, /md-unlog
  agents/
    researcher.md        web research and fact verification
    mermaid-maker.md     draws, renders, looks at and publishes a Mermaid diagram
    svg-maker.md         the same for hand-written SVG (geometry, plots)
  mcp/
    quiz_server.py       the quiz tool: an MCP server with no dependencies
    quiz_popup.py        the popup, shown with tmux display-popup
    latex_text.py        LaTeX to Unicode, for the popup
  hooks/
    md_log.py            mirrors the session into the note
    lesson.py            checkpoints and the resume brief
    book.py              maps a textbook PDF to page ranges; keeps a course's syllabus and progress
  scripts/
    install.sh           one-off setup
    render-mermaid.sh    Mermaid to PNG
    render-svg.sh        SVG to PNG
  visual-tools/          package.json for the Mermaid renderer
  obsidian/
    learn-callouts.css   styles for definition, theorem, proof, notation and the other callouts
  docs/
    architecture.md      how the pieces fit and what is fragile
    worklog.md           running notes on the state of the project
```

[docs/architecture.md](docs/architecture.md) explains how the pieces fit, why they are built this way, and what is fragile.

## Customising

- **How it teaches.** The teach skill is written for one learner. Edit `skills/teach/SKILL.md` to fit how you learn.
- **The teacher's voice.** `CLAUDE.md` holds the house rules.
- **The teacher's model.** The teacher is the Claude Code session itself, so it uses that session's model. Use `/model` in a session, or set `"model"` in `.claude/settings.local.json` to pin one for this folder only.
- **The subagents' model.** The researcher and the diagram makers are set to `sonnet` in `agents/*.md`. Change `model:` there.

## Troubleshooting

**The quiz is a one-line form with "Your answer: not set", not a popup.**
Claude Code was probably started outside tmux. `.claude/md-log-state/quiz-server.log` gives the reason. Restart Claude Code from inside tmux; the quiz server is started with the session.

**There is no quiz tool; questions come as plain prompts.**
Run `/mcp` and check that `quiz` is listed and enabled. Check that `.mcp.json` exists in the project root.

**"The quiz is running in the background."**
Claude Code moves tool calls longer than two minutes to the background. `settings.json` turns that off for this project (`CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS=0`). If you see the message, the setting is not in effect: restart Claude Code from the project folder.

**The teacher's text is missing from the note.**
The mirror reads Claude Code's session transcript, whose format is internal and may change between releases. Prompts and quizzes are not affected. Regenerate a note with `python3 .claude/hooks/md_log.py rebuild <out.md> <transcript.jsonl>...`.

**Hooks do not fire.**
Claude Code must be started from the folder that contains `.claude`, not from a subfolder.

**A change I pulled has no effect.**
Skills and settings are read when a session starts. Start a new session.

## Credits

Teaching philosophy, skills and agent prompts: [Amos Blomqvist](https://github.com/amosblomqvist/learn).
Port to Claude Code: Lachlan Burton, with Claude.
