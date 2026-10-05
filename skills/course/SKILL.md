---
name: course
description: Follow a textbook (PDF) as a course. `/course new <book.pdf>` maps the book and sets the syllabus; `/course next` teaches the next section from the book's own pages; `/course study <section>` teaches a given one; `/course list` and `/course use <name>` switch between courses; `/course status`, `/course toc [chapter]`, `/course select <spec>`, `/course assess <exercise>...`, `/course solutions <policy>` manage one.
argument-hint: new <book.pdf> [name] | next | study <section> | list | use <name> | status | toc [chapter] | select <spec> | assess <exercise>... | solutions <never|after-attempt|on-request>
disable-model-invocation: true
allowed-tools: Bash(python3 .claude/hooks/book.py *), Bash(python3 .claude/hooks/md_log.py *), Bash(python3 .claude/hooks/lesson.py *)
---

Arguments: `$ARGUMENTS`

A course is a textbook, a syllabus chosen from it, and one lesson note per chapter. `book.py` holds the page map and the progress; you never load the whole book, only the pages a command tells you to Read. Every `book.py` command acts on the **current course**: the one created or chosen last. The learner changes it with `/course use <name>`; do not pass `--course` on your own initiative.

## `new <book.pdf> [name]`

Setup is not lesson content, so nothing of it may reach a note.

1. Stop mirroring first:
   ```
   python3 .claude/hooks/md_log.py unlink --session ${CLAUDE_SESSION_ID}
   ```
2. Map the book:
   ```
   python3 .claude/hooks/book.py new "<book.pdf>" [--name <name>]
   ```
   If it prints `NO OUTLINE`, follow the steps it prints: Read the contents pages, write the contents file under `/tmp/learn-book/`, run it again with `--toc` and `--offset`.
3. If the output says the title is unknown, Read PDF pages 1-3 and run `book.py set title "<title>"`.
4. Read the front matter the output names (preface, "how to use this book"; at most 20 pages per Read call). Look for: suggested course tracks or chapter dependencies; how optional material is marked; where solutions to the exercises are published; stated prerequisites.
5. Write one short paragraph: what the book covers, how it is organised, and what the author suggests for a first course. Then ask with **one** `AskUserQuestion` call, header `Course`, three questions:
   - *What should the course cover?* Offer what the book itself suggests (a named track, or "core sections only" when the book marks optional material), the whole book, and one or two sensible selections for a learner like this one. Their own list or a pasted syllabus arrives through "Other".
   - *What do you want from it?* Two to four concrete goals for this book, plus their own wording. This is the goal question of the teach skill's Phase 1b, asked once for the whole course.
   - *When may I show a full solution to an exercise?* **After you have shown an attempt and ask for it** (default), **Whenever you ask**, **Never**.
6. Record the answers:
   ```
   python3 .claude/hooks/book.py select <spec>          # all | unstarred | 2 | 2.1-2.6 | 3-5 8 10.2 ...
   python3 .claude/hooks/book.py set goal "<goal>"
   python3 .claude/hooks/book.py set solutions <after-attempt|on-request|never>
   ```
   A pasted syllabus that names sections maps directly onto a spec; check doubtful ids with `book.py toc <chapter>`.
7. Reply with the `🗒 syllabus set` line and one sentence: `/course next` starts the first section, and `/course assess <exercise>...` marks exercises that are assessed coursework.

## `next` and `study <section>`

1. Ask the script what to teach:
   ```
   python3 .claude/hooks/book.py next              # or: book.py section <section>
   ```
2. Link the chapter note named on the `NOTE` line, from this point on (no backfill):
   ```
   python3 .claude/hooks/md_log.py link "<note>" --session ${CLAUDE_SESSION_ID} --from-now
   ```
3. Load the `teach` skill if it is not loaded and follow its section **Teaching from a book**.
   - **The note is new** (first unit of a chapter): run the chapter start described there. Your reply to this command is the `### Overview` of the chapter and nothing else: it ends with the ready-or-probe choice, and no quiz or question is asked in it. A probe happens only if the learner then asks for one.
   - **The note exists**: get the resume brief with `python3 .claude/hooks/lesson.py summary "<note>"` and follow steps 4 to 6 of the `lesson` skill's `resume` (the `Resume` question, the optional recall check, then continue). Which unit comes next is what `book.py` printed; where things stand inside that unit is what the checkpoint says.
4. Read the pages on the `READ` line before you write anything about the unit.

`/lesson pause` works as in any lesson: the checkpoint belongs to the chapter note.

## `list`, `use <name>`

Several courses can exist side by side; each keeps its own syllabus, progress, notes and checkpoints.

```
python3 .claude/hooks/book.py list            # every course, the current one marked
python3 .claude/hooks/book.py use <name>      # make <name> the current course
```

For `list`, show the output. For `use`, reply with only the `🗒` line and the progress line under it. Nothing else changes: the next `/course next` continues that course from its own checkpoint. If a lesson of another course is open in this session and has not been paused, save its checkpoint first (as `/lesson pause` does).

## `status`, `toc [chapter]`

Run `book.py status` or `book.py toc [chapter]` and report in a few lines. Do not link, probe or teach.

## `select <spec>`, `assess <exercise>...`, `solutions <policy>`

Run the matching command and reply with only the `🗒` line it prints:

```
python3 .claude/hooks/book.py select <spec> [--add | --remove]
python3 .claude/hooks/book.py assess <exercise>... [--clear]
python3 .claude/hooks/book.py set solutions <never|after-attempt|on-request>
```
