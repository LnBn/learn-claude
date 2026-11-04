---
name: course
description: Follow a textbook (PDF) as a course. `/course new <book.pdf>` maps the book and sets the syllabus; `/course next` teaches the next section from the book's own pages; `/course study <section>` teaches a given one; `/course list` and `/course use <name>` switch between courses and programmes; `/course programme ...` builds a programme over several books; `/course status`, `/course toc [chapter]`, `/course select <spec>`, `/course assess <exercise>...`, `/course solutions <policy>`, `/course mode <problems|textbook>` manage one.
argument-hint: new <book.pdf> [name] [--toc <file> --offset <n>] [--problems] | next | study <section> | list | use <name> | programme <new|module|move|remove|goal> ... | status | toc [chapter] | select <spec> | assess <exercise>... | solutions <never|after-attempt|on-request> | mode <problems|textbook>
disable-model-invocation: true
allowed-tools: Bash(python3 .claude/hooks/book.py *), Bash(python3 .claude/hooks/programme.py *), Bash(python3 .claude/hooks/md_log.py *), Bash(python3 .claude/hooks/lesson.py *)
---

Arguments: `$ARGUMENTS`

A course is a textbook, a syllabus chosen from it, and one lesson note per chapter. `book.py` holds the page map and the progress; you never load the whole book, only the pages a command tells you to Read. Every `book.py` command acts on the **current course**: the one created or chosen last. The learner changes it with `/course use <name>`; do not pass `--course` on your own initiative.

## `new <book.pdf> [name] [--toc <file> --offset <n>] [--problems]`

Setup is not lesson content, so nothing of it may reach a note.

1. Stop mirroring first:
   ```
   python3 .claude/hooks/md_log.py unlink --session ${CLAUDE_SESSION_ID}
   ```
2. Map the book:
   ```
   python3 .claude/hooks/book.py new "<book.pdf>" [--name <name>] [--toc <file> --offset <n>] [--problems]
   ```
   Pass on `--toc`, `--offset` and `--problems` when the learner gave them. If it prints `NO OUTLINE`, follow the steps it prints: Read the contents pages, write the contents file under `/tmp/learn-book/`, run it again with `--toc` and `--offset`. When the book prints its solutions apart from the problems, give each problem's solution page in a fourth column.
3. If the output says the title is unknown, Read PDF pages 1-3 and run `book.py set title "<title>"`.
4. Read the front matter the output names (preface, "how to use this book"; at most 20 pages per Read call). Look for: suggested course tracks or chapter dependencies; how optional material is marked; where solutions to the exercises are published; stated prerequisites.
5. Write one short paragraph: what the book covers, how it is organised, and what the author suggests for a first course. Then ask with **one** `AskUserQuestion` call, header `Course`, three questions:
   - *What should the course cover?* Offer what the book itself suggests (a named track, or "core sections only" when the book marks optional material), the whole book, and one or two sensible selections for a learner like this one. Their own list or a pasted syllabus arrives through "Other".
   - *What do you want from it?* Two to four concrete goals for this book, plus their own wording. This is the goal question of the teach skill's Phase 1b, asked once for the whole course.
   - *When may I show a full solution to an exercise?* **After you have shown an attempt and ask for it** (default), **Whenever you ask**, **Never**.

   A problem course needs no solutions policy, since each solution is shown after its attempt. When `--problems` was given, leave the third question out. When it was not and the book is a collection of problems with their solutions (an interview guide, a problem book), replace the third question with *How should each unit run?*: **Problem first** (you attempt each problem before you see its solution) and **Textbook** (read the section, then quizzes).
6. Record the answers:
   ```
   python3 .claude/hooks/book.py select <spec>          # all | unstarred | 2 | 2.1-2.6 | 3-5 8 10.2 ...
   python3 .claude/hooks/book.py set goal "<goal>"
   python3 .claude/hooks/book.py set solutions <after-attempt|on-request|never>
   python3 .claude/hooks/book.py set mode problems                  # for Problem first
   ```
   A pasted syllabus that names sections maps directly onto a spec; check doubtful ids with `book.py toc <chapter>`.
7. Reply with the `🗒 syllabus set` line and one sentence: `/course next` starts the first section, and, in a textbook course, `/course assess <exercise>...` marks exercises that are assessed coursework.

## `next` and `study <section>`

1. Ask the script what to teach:
   ```
   python3 .claude/hooks/programme.py next         # or: programme.py section <section>
   ```
   With no programme current, this is exactly `book.py next` (or `book.py section`). In a programme, see **Programmes** below.
2. Link the chapter note named on the `NOTE` line, from this point on (no backfill):
   ```
   python3 .claude/hooks/md_log.py link "<note>" --session ${CLAUDE_SESSION_ID} --from-now
   ```
3. Load the `teach` skill if it is not loaded and follow its section **Teaching from a book**.
   - **The note is new** (first unit of a chapter): run the chapter start described there. Your reply to this command is the `### Overview` of the chapter and nothing else: it ends with the ready-or-probe choice, and no quiz or question is asked in it. A probe happens only if the learner then asks for one.
   - **The note exists**: get the resume brief with `python3 .claude/hooks/lesson.py summary "<note>"` and follow **Resuming a lesson** in the teach skill (the `Resume` question, the optional recall check, then the checkpoint's Next). Which unit comes next is what `book.py` printed; where things stand inside that unit is what the checkpoint says. This holds every time the command is run, also part-way through a session that has been teaching this note: `/course next` is never a `ready`, and the `Resume` question is never skipped. If this session has taught past the latest checkpoint, what it taught since counts over the checkpoint.
4. Read the pages on the `READ` line before you write anything about the unit.

When the output has a `MODE: problems` line, the course is a problem course: the unit is taught problem by problem, as the teach skill's **Problem books** says. The `READ` line then holds only the statement of the problem on the `PROBLEM` line, and the `SOLUTION` line says when to Read the solution.

`/lesson pause` works as in any lesson: the checkpoint belongs to the chapter note.

## `list`, `use <name>`

Several courses can exist side by side; each keeps its own syllabus, progress, notes and checkpoints.

```
python3 .claude/hooks/programme.py list       # every programme and course, the current one marked
python3 .claude/hooks/programme.py use <name> # make <name> the current course or programme
```

For `list`, show the output. For `use`, reply with only the `🗒` line and the progress line under it. Nothing else changes: the next `/course next` continues that course from its own checkpoint. If a lesson of another course is open in this session and has not been paused, save its checkpoint first (as `/lesson pause` does).

## `status`, `toc [chapter]`

Run `programme.py status` or `book.py toc [chapter]` and report in a few lines. Do not link, probe or teach.

## `select <spec>`, `assess <exercise>...`, `solutions <policy>`, `mode <problems|textbook>`

Run the matching command and reply with only the `🗒` line it prints:

```
python3 .claude/hooks/book.py select <spec> [--add | --remove]
python3 .claude/hooks/book.py assess <exercise>... [--clear]
python3 .claude/hooks/book.py set solutions <never|after-attempt|on-request>
python3 .claude/hooks/book.py set mode <problems|textbook>
```

`mode` changes how the units still to come are taught. Progress, notes and checkpoints stay as they are.

## Programmes

A programme is one course made of units from several book courses, grouped into topic modules. Each book keeps its page map, figures, exercises, equation numbers, chapter notes and progress. The programme adds the order and the modules. Its note, `courses/<name>/<name>.md`, holds the index (generated) and, below it, one `## Module n — <title>` section per module with its overview.

`programme.py` acts like `book.py` when no programme is current, which is why `next`, `study`, `status`, `list` and `use` above always call it. While a programme is current, `next` and `study` make the unit's book the current course, so every `book.py` command, `/exercise`, `/exam` and the figures act on that book. Do not pass `--course`.

### `programme <args>`

Setup is not lesson content. Run the matching command (`goal` is `set goal`) and reply with only the `🗒` line it prints:

```
python3 .claude/hooks/programme.py new <name> --title "<title>" [--goal "<goal>"]
python3 .claude/hooks/programme.py module "<title>" <course>:<spec> [<course>:<spec> ...] [--at <n>]
python3 .claude/hooks/programme.py move <n> <to>
python3 .claude/hooks/programme.py remove <n>
python3 .claude/hooks/programme.py set goal "<goal>"
```

A spec is as in `select`: `bh:7.1-7.5 strang:3.3`. A spec without a prefix belongs to the book named before it. Units are taught in the order given. `module` with the title of an existing module replaces its units. Every change also sets each book's syllabus to its units in the programme, so do not use `select` while a programme is current. If the programme has no goal, ask for it once, as in step 5 of `new` (header `Programme`), and record it with `set goal`.

### `next` and `study` in a programme

`programme.py next` prints `PROGRAMME:` and `COURSE:` lines before the unit, and `study` takes `<course>:<section>` (`/course study bh:7.3`).

- **`MODULE START`** (the module has no overview yet): link the programme note on the `PROGRAMME NOTE` line instead of the chapter note, with `--from-now --no-header`. Your reply is the module overview, as **Teaching from a book** in the teach skill describes, under the `HEADING` line and `### Overview`, and nothing else. When the learner says ready, link the chapter note on the `NOTE` line with `--from-now`, Read the unit's pages, and go on as step 3 above.
- **`PROGRAMME CHAPTER START`** (the chapter note is new): the note opens with the short overview the teach skill describes, not the chapter-sized one.
- Otherwise the steps above apply unchanged.

The output ends with a `RECORD` line: a unit is recorded with `programme.py done <course>:<unit>`, and the next unit comes from that command's output.

To work on an exercise or an exam of another book in the programme, `/course use <book>` first. The programme stays current, and the next `/course next` follows it again.
