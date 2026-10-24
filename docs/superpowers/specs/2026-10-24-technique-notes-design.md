# Technique notes — design

Date: 2026-10-24. Status: approved in conversation, awaiting spec review.

## Purpose

Interview problems are solved by a small set of tricks: symmetry, linearity of expectation, first-step conditioning, the pigeonhole principle. A lesson note follows the book, so each trick is scattered over the sections and books that use it, and the hard part of an interview — recognising which trick a new problem needs — is never practised on its own. A technique note collects one trick: what it is, the cues that should make the learner reach for it, its traps, and every problem that used it, with the learner's record on each.

This is the third of five planned pieces (typed answers, mock interview, technique notes, practice with `/drill` and `/review`, mental arithmetic). The drill and review modes will draw on the technique notes' problem lists and records.

**Said by the learner:** problems should exercise the same "trick" in different settings (the request that started the transfer rule); a technique note should be a recognition sheet and a problem pool.

**Agreed in the design conversation:**

- Each note is a recognition sheet (the trick, cues, traps, related techniques) plus a generated list of the problems that used it, with the learner's record.
- One set of notes for the whole vault, in `techniques/`, shared by every course and lesson.
- Kept up to date automatically: the teacher tags each lesson section with the techniques it used; interview problems carry technique names. A one-time backfill tags the gb chapters already done.
- The teacher drafts a new technique's cues; the first time a technique appears, the learner is asked what in the problem should have made them think of it, and the answer goes into the note in their words.
- Approach: the tags live in the notes as visible wikilinks; a script reads them and writes each note's problem list and an index.

**Assumed and not contradicted:** individual quizzes are not tagged (a section's tag covers its quizzes); exams are not tagged; review notes (recall checks) are not tagged.

## A technique note

`techniques/<Name>.md`. The file name is the technique's canonical name (letters, digits, spaces, hyphens, apostrophes). The teacher writes everything above the problems block; the script writes only inside it.

```markdown
---
technique: Symmetry
aliases: [symmetry argument, by symmetry]
---
# Symmetry

> [!definition] The trick
> Find a transformation that leaves the problem unchanged. Quantities that the transformation swaps
> must have equal answers, so you only need their sum or one of them.

## Reach for it when

- the players, positions or objects are interchangeable
- the question asks for P(A before B) and nothing favours either

**In your words:**
- "Two piles that could be swapped without changing anything" — [[gb-ch02#2.4.1 Coin piles|§2.4.1]], 2026-10-23

## Traps

- the symmetry is broken by who moves first, or by an unequal starting position

## Related

- [[Linearity of expectation]] — often the next step once the symmetric pieces are equal

## Problems

%% problems: written by technique.py sync; edits inside are replaced %%
**Record:** 4 ✓ · 2 ✗ — 5 problems

- [[gb-ch02#2.4.1 Coin piles|§2.4.1 Coin piles]] (gb) ✓✓
- [[gb-ch02#2.4.3 Wise men|§2.4.3 Wise men]] (gb) ✓✗
- [[gb-interview-1#Problem 2|gb interview 1, problem 2]] — hinted
%% /problems %%
```

- `aliases` serve two readers. Obsidian offers them when a link is typed, and writes the link as `[[Symmetry|symmetry argument]]`; `technique.py` resolves a raw `[[symmetry argument]]` to this note, so a tag written under an alias still counts. The teacher always writes the canonical name.
- **Records.** For a lesson section: the marks of the graded quizzes in that section, in order (`✓` passed, `✗` wrong, `?` I don't know); a section without graded quizzes shows nothing. For an interview problem: its outcome. The `Record` line counts a `✓` or a `solved` problem as a pass, and `✗`, `?`, `hinted` and `unsolved` as a miss; skipped, unavailable and unanswered quizzes and `not reached` problems do not count.
- Problems are listed lesson sections first (in note order, then section order), then interview problems (oldest round first).

## The index

`techniques/Techniques.md`, written whole by the script:

```markdown
# Techniques

| Technique | Problems | ✓ | ✗ | Last seen |
|---|---|---|---|---|
| [[Pigeonhole principle]] | 3 | 1 | 3 | 2026-10-24 |
| [[Symmetry]] | 5 | 4 | 2 | 2026-10-23 |

**Unknown techniques:** [[Backwards induction]] in [[gb-ch02#2.1.1 Screwy pirates|§2.1.1]]
```

- Sorted weakest first: by pass rate (passes ÷ (passes + misses)), lowest first; a technique with no counted outcome comes last; ties by misses, most first.
- `Last seen` is the date of the newest session heading (`## Session — YYYY-MM-DD`) above any of its tagged sections, or the interview's date.
- **Unknown techniques** lists tags that resolve to no note or alias, with where they are, so a typo or a missing note is visible. The line is left out when there are none.

## Tags

**In a lesson note**, a tag line closes a section:

```markdown
*Techniques: [[Symmetry]] · [[Linearity of expectation]]*
```

- Pattern: a line that is exactly `*Techniques: ` + wikilinks separated by ` · ` + `*`. A wikilink may carry a display text (`[[Symmetry|symmetric]]`); the target is what counts.
- The tag belongs to the nearest `### ` heading above it. A section has at most one tag line; if it has several, their techniques are merged.
- Scanned notes: every `.md` file under the vault except `techniques/`, `.claude/`, `.obsidian/`, `exams/` folders, `interviews/` folders and review notes (`*-review.md`, `* — Review.md`).

**In an interview problem file**, each problem gains `"techniques": ["Symmetry"]`, a non-empty list of technique names. `interview.py check` refuses a name that resolves to no technique note (`p2: technique "Symetry" has no note in techniques/`). The free-text `technique` field stays, for the scorecard. An interview problem's link is the `### Problem n` heading of its round's note; only `finished` rounds count.

## The script: `hooks/technique.py`

```
technique.py list                         every technique: name, aliases, problems, record; then unknown tags
technique.py sync                         rewrite every note's problems block and the index (only files that change)
technique.py cue "<Name>" "<text>" --source "<note stem>#<heading>"
                                          add the learner's cue under "In your words"
technique.py sections <note>              for the backfill: each ### section with its key idea and its tags
technique.py tag <note> "<heading>" <Name>...
                                          for the backfill: write a tag line at the end of that section
```

- **`sync`** reads every scanned note and every finished interview round, resolves tags through note names and aliases (case-insensitive), and rewrites the block between `%% problems: … %%` and `%% /problems %%` in each technique note, and the index. A note without the markers gets the block appended under a `## Problems` heading. A file whose new content equals its old content is not written. It prints one line, `🗒 techniques: <n> notes, <k> tagged problems, <u> unknown`.
- **`cue`** inserts `- "<text>" — [[<source>|§<n>]], <date>` as the last item of the list under `**In your words:**`, creating that line (after the `## Reach for it when` list) if it is missing. It refuses a technique that has no note.
- **`sections`** prints, for each `### ` heading of a note: the heading, its `Key idea` text, and its tags if any. It is how the backfill reads a chapter without loading it whole.
- **`tag`** writes the tag line at the end of the named section: after its last line and before the next `##`/`###` heading, separated by a blank line. If the section already has a tag line, the techniques are merged into it. Then it runs `sync`.
- Section labels use the heading's number (`§2.4.1`) when it has one, else the heading text.

**When `sync` runs:**

- From the note mirror: `md_log.py`, after writing a turn's prose to a note in the `Stop` hook, calls `technique.sync()` when the text it wrote contains `*Techniques:`. (Claude Code may run a hook event's commands in parallel, so a separate `Stop` hook entry could read the note before the mirror writes it.)
- From `interview.py finish`, after the scorecard is written.
- From `technique.py tag`, `list` and `cue`.
- By hand: `technique.py sync`, or `/techniques sync`.

## In lessons (the teach skill)

At the close of a section (both quizzes passed):

1. `python3 .claude/hooks/technique.py list` to see the existing names. Reuse a name or an alias when the trick is the same one; a new note only for a genuinely different trick. Most sections use one or two techniques; a section that teaches a definition and uses no trick gets no tag.
2. **A new technique:** write its note with the Write tool, from the template above: the trick in general (not this problem's version of it), two to four cues phrased as features a problem statement can have, the traps, related techniques, and the empty problems block. Then ask the learner, as plain text ending the reply: *What in this problem should have made you think of <technique>?* When they answer, record it with `technique.py cue` and close the section.
3. **A known technique** in a setting that disguised it well: the same question may be asked, at most once per section. Otherwise no question.
4. The section's closing line is followed by the tag line, `*Techniques: [[…]] · [[…]]*`, as the last line of the section.
5. When a later problem shows a trap or a cue the note lacks, add it to the note with the Edit tool. The teacher never edits inside the problems block or the learner's "In your words" items.

In a course the tags are written for every unit; in a lesson outside a course too, when the lesson is about problem-solving.

## The `techniques` skill

`/techniques [list | sync | backfill [course]]`:

- `list` and `sync`: run the command and show its output.
- `backfill [course]` (default: the current course), once per course:
  1. Unlink the mirror (the backfill is not lesson content).
  2. `technique.py list`, then `technique.py sections <note>` for each chapter note of the course that has finished units.
  3. Propose the tags for every section in one table (section, techniques; existing names reused, new ones marked *new*) and ask the learner to approve or correct it with one `AskUserQuestion` (header `Techniques`): **Looks right**, **Let me correct it** (free text through "Other").
  4. Write a note for every new technique, as in a lesson, without the cue question: the learner's cues come the next time the technique appears.
  5. `technique.py tag` for each section, then reply with the `🗒` line of the last `sync` and a link to the index.

## Interviews

- The interview skill's problem file gains `techniques` (names from `technique.py list`; a problem on a trick with no note gets its note written first, as in a lesson).
- `interview.py new` prints, under `PAST TECHNIQUES`, the technique names of earlier rounds alongside the free-text descriptions.
- The scorecard's Technique column shows the `techniques` as links (`[[Symmetry]]`), with the free-text description after them.

## Files

- `hooks/technique.py` (new); `hooks/md_log.py` (call `sync` after mirroring a tag line); `hooks/interview.py` (`techniques` in `check`, `new`, the scorecard; `sync` after `finish`).
- `skills/techniques/SKILL.md` (new); `skills/teach/SKILL.md` (closing a section); `skills/interview/SKILL.md` (the `techniques` field).
- `settings.json`: `Bash(python3 .claude/hooks/technique.py *)` in the permissions.
- README: a `Technique notes` section; `docs/architecture.md`: the script, the tag format, when `sync` runs.

## Testing

- `tests/test_technique.py`, in a throwaway vault:
  - `sync`: a tag line assigned to the right section; several tag lines in a section merged; display texts and aliases resolved, case-insensitive; records from quiz blocks in the section (✓ ✗ ? counted, skipped and unanswered not); interview problems from finished rounds only, with outcomes; the problems block replaced and everything outside it kept byte for byte; a note without markers gets the block; unchanged files not written (mtime kept); excluded folders and review notes not scanned; the index's order, counts, `Last seen` and unknown techniques.
  - `cue`: appended under "In your words", the line created when missing, refusal for an unknown technique.
  - `sections` and `tag`: key ideas printed; the tag line placed at the section's end before the next heading; merged into an existing tag line.
  - `list`: names, aliases, counts, unknown tags.
- `tests/test_interview.py`: `check` refuses an unknown technique name and accepts an alias; the scorecard's links.
- `tests/test_mirror_*`: mirroring a reply that contains a tag line updates the technique note's problems block.

## Out of scope

- Tagging individual quizzes, exam questions or recall checks.
- Merging or renaming techniques by command (rename the note in Obsidian, which updates the links, then `sync`).
- Using the records to choose problems: that is `/drill` and `/review`, the next piece.
