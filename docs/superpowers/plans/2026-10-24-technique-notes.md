# Technique Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One note per problem-solving technique in `techniques/`, each a recognition sheet plus a generated list of every tagged lesson section and interview problem with the learner's record, kept current from tags written during lessons.

**Architecture:** Tags are visible wikilinks in the notes (`*Techniques: [[Symmetry]] · …*` closing a lesson section) and a `techniques` list in interview problem files. `hooks/technique.py` resolves them against the technique notes and their aliases, and rewrites only the problems block of each note and the index. The note mirror calls `sync` after it writes a tag line; `interview.py finish` and `technique.py tag` call it too.

**Tech Stack:** Python 3.10+, standard library only; tests with `unittest` through `tests/_vault.py`.

**Spec:** `docs/superpowers/specs/2026-10-24-technique-notes-design.md`

## Global Constraints

- Notes: `<vault>/techniques/<Name>.md`; index: `<vault>/techniques/Techniques.md` (never itself a technique).
- Problems block markers, exactly: `%% problems: written by technique.py sync; edits inside are replaced %%` … `%% /problems %%`.
- Tag line regex: `^\*Techniques: (.+)\*$`, wikilinks separated by ` · `; target = text before `|` or `#`.
- Resolution: case-insensitive on note name and every `aliases` entry of its frontmatter (`aliases: [a, b]` or a YAML list `- a`).
- Record marks: quiz outcomes `✓` pass; `✗`, `?` miss; `skip`, `unavailable`, `asked`, `(unanswered)` not counted. Interview `solved` pass; `hinted`, `unsolved` miss; `not reached` not listed.
- Record line: `**Record:** <p> ✓ · <m> ✗ — <k> problem[s]`.
- Lesson entry: `- [[<stem>#<heading anchor>|<label>]] (<course slug or "lesson">) <marks>`; label `§<number> <title>` for a numbered heading, else the heading text. Interview entry: `- [[<stem>#Problem <i>|<slug> interview <n>, problem <i>]] — <outcome>`.
- Scanned: every `.md` under the vault except under `techniques/`, `.claude/`, `.obsidian/`, any `exams/` or `interviews/` folder, and review notes (`*-review.md`, `* — Review.md`).
- `sync` writes a file only when its content changes; prints `🗒 techniques: <n> notes, <k> tagged problems, <u> unknown`, where `k` counts tagged sections plus interview problems and `u` counts distinct unknown names.
- Heading anchors use the same normalisation as `lesson.heading_links` (`[#|^:\[\]]` → space, whitespace collapsed).
- Standard library only; match `exam.py`/`interview.py` (`book.die`, short docstrings). README is a tutorial.

## Review Focus

1. **A learner editing a technique note in Obsidian while a lesson runs** (adding a trap, reordering cues): everything outside the problems block survives every `sync` byte for byte. Test in Task 1.
2. **A tag naming a technique whose note does not exist yet** (typo, or the note is written after the tag): listed under unknown techniques, no crash, and it resolves on the next `sync` once the note exists. Test in Task 1.
3. **A section with a quiz the learner asked about first (`?` ask-first block) and then answered**: only the graded block counts. Test in Task 1.
4. **The mirror writing a reply that contains a tag line when no `techniques/` folder exists**: no error, no folder created except by the index write. Test in Task 3.
5. **`tag` on a section that is the last in the note, or followed by a `## Session` header**: the tag line goes before the session header, not after it. Test in Task 2.

---

### Task 1: `technique.py` — reading tags, `sync`, `list`

**Files:**
- Create: `hooks/technique.py`
- Test: `tests/test_technique.py`

**Interfaces:**
- Produces:
  - `VAULT`, `TECH_DIR`, `INDEX`, `START`, `END` (the markers)
  - `load_techniques() -> dict[str, dict]` — canonical name → `{"path": str, "aliases": list[str]}`
  - `resolver(techs) -> dict[str, str]` — lower-cased name or alias → canonical name
  - `scan_tags() -> list[dict]` — one per tagged section: `{"note", "stem", "heading", "anchor", "label", "course", "targets": [str], "marks": [str], "date": str|None}`
  - `interview_problems() -> list[dict]` — one per problem of a finished round: `{"stem", "slug", "number", "i", "techniques": [str], "outcome", "date"}`
  - `sync() -> str` — the summary line; `main(argv)` with `list` and `sync`.

- [ ] **Step 1: Write the failing tests** in `tests/test_technique.py`. Set-up: `make_vault`; `make_course(vault, "gb")`; helper `tech(name, aliases=(), body="")` writes `techniques/<name>.md` with frontmatter, a `# name` heading, a `## Reach for it when` list and `body`; helper `tq(*args)` = `run(vault, "technique.py", *args)`. A chapter note `courses/gb/gb-ch02.md`:

```markdown
## Session — 2026-10-07 (Wed) 12:32

### 2.4.1 Coin piles

Text.

> [!success|quiz]- ✓ Check question
> body

> [!failure|quiz]- ✗ Apply question
> body

*Techniques: [[Symmetry]]*

### 2.4.2 Wise men

> [!note|quiz]- Asked first: Q?
> body

> [!success|quiz]- ✓ Q?
> body

*Techniques: [[symmetry argument|by symmetry]] · [[Pigeonhole]]*

## Session — 2026-10-09 (Fri) 10:00

### 2.6.1 Handshakes

*Techniques: [[Pigeonhole principle]]*
*Techniques: [[Symmetry]]*
```

```python
def test_sync_writes_problem_blocks(self):
    self.tech("Symmetry", aliases=["symmetry argument"]); self.tech("Pigeonhole principle", aliases=["pigeonhole"])
    self.assertIn("🗒 techniques: 2 notes, 3 tagged problems, 0 unknown", self.tq("sync").stdout)  # 3 sections
    sym = (self.vault / "techniques" / "Symmetry.md").read_text()
    self.assertIn(technique.START, sym)
    self.assertIn("**Record:** 2 ✓ · 1 ✗ — 3 problems", sym)
    self.assertIn("- [[gb-ch02#2.4.1 Coin piles|§2.4.1 Coin piles]] (gb) ✓✗", sym)
    self.assertIn("- [[gb-ch02#2.4.2 Wise men|§2.4.2 Wise men]] (gb) ✓", sym)   # the asked-first block not counted
    self.assertIn("- [[gb-ch02#2.6.1 Handshakes|§2.6.1 Handshakes]] (gb)", sym)  # two tag lines merged
def test_edits_outside_block_survive(self):
    self.tech("Symmetry", body="## Traps\n\n- my own trap\n")
    self.tq("sync")
    p = self.vault / "techniques" / "Symmetry.md"
    before = p.read_text().split(technique.START)[0]
    p.write_text(p.read_text().replace("my own trap", "my edited trap"))
    self.tq("sync")
    after = p.read_text()
    self.assertIn("my edited trap", after)
    self.assertEqual(after.split(technique.START)[0], before.replace("my own trap", "my edited trap"))
    self.assertEqual(after.count(technique.START), 1)
def test_unchanged_files_not_written(self):
    self.tech("Symmetry"); self.tq("sync")
    p = self.vault / "techniques" / "Symmetry.md"; m = p.stat().st_mtime_ns
    time.sleep(0.01); self.tq("sync")
    self.assertEqual(p.stat().st_mtime_ns, m)
def test_unknown_then_resolved(self):
    self.tech("Symmetry", aliases=["symmetry argument"])
    self.assertIn("2 unknown", self.tq("sync").stdout)  # Pigeonhole and Pigeonhole principle: distinct names
    idx = (self.vault / "techniques" / "Techniques.md").read_text()
    self.assertIn("**Unknown techniques:** [[Pigeonhole]] in [[gb-ch02#2.4.2 Wise men|§2.4.2]]", idx)
    self.assertIn("[[Pigeonhole principle]] in [[gb-ch02#2.6.1 Handshakes|§2.6.1]]", idx)
    self.tech("Pigeonhole principle", aliases=["pigeonhole"])
    self.assertIn("0 unknown", self.tq("sync").stdout)
def test_index_order_counts_last_seen(self):
    self.tech("Symmetry", aliases=["symmetry argument"]); self.tech("Pigeonhole principle", aliases=["pigeonhole"])
    self.tq("sync")
    idx = (self.vault / "techniques" / "Techniques.md").read_text()
    rows = [ln for ln in idx.splitlines() if ln.startswith("| [[")]
    self.assertEqual(rows[0], "| [[Symmetry]] | 3 | 2 | 1 | 2026-10-09 |")          # pass rate 2/3
    self.assertEqual(rows[1], "| [[Pigeonhole principle]] | 2 | 1 | 0 | 2026-10-09 |")  # 1/1
def test_interview_problems(self):
    # a finished round gb-interview-1 with p1 solved (techniques ["Symmetry"]), p2 not reached; an abandoned round ignored
    ...
    sym = (self.vault / "techniques" / "Symmetry.md").read_text()
    self.assertIn("- [[gb-interview-1#Problem 1|gb interview 1, problem 1]] — solved", sym)
    self.assertNotIn("problem 2", sym)
def test_excluded_notes(self):
    self.tech("Symmetry")
    for rel in ["courses/gb/gb-review.md", "courses/gb/exams/x.md", "courses/gb/interviews/y.md", "techniques/Other.md"]:
        (self.vault / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.vault / rel).write_text("### 1 A\n\n*Techniques: [[Symmetry]]*\n")
    self.tq("sync")
    self.assertIn("2 problems", (self.vault / "techniques" / "Symmetry.md").read_text())  # 2.4.1, 2.6.1; no alias
def test_note_without_markers_gets_block(self):
    p = self.vault / "techniques" / "Symmetry.md"; p.parent.mkdir(); p.write_text("# Symmetry\n\nMine.\n")
    self.tq("sync")
    t = p.read_text()
    self.assertTrue(t.startswith("# Symmetry\n\nMine.\n"))
    self.assertIn("## Problems\n\n" + technique.START, t)
def test_list(self):
    self.tech("Symmetry", aliases=["symmetry argument"])
    out = self.tq("list").stdout
    self.assertIn("Symmetry (aliases: symmetry argument) — 3 problems, 2 ✓ 1 ✗", out)
    self.assertIn("UNKNOWN: Pigeonhole", out)
```

  (`technique` is imported from the repo's `hooks/` for the marker constants only.)

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest tests.test_technique -v`
Expected: FAIL — `technique.py` does not exist.

- [ ] **Step 3: Implement** `hooks/technique.py` with the Interfaces above and the Global Constraints. `scan_tags` walks the vault (pruning excluded directories in `os.walk`), splits each note into `### ` sections, takes the newest `## Session — YYYY-MM-DD` above each section as its date, reads quiz outcomes with `quiz_block.is_quiz_header` / `quiz_block.parse` (header line only), and merges the targets of every tag line in the section. `interview_problems` reads `courses/*/.interviews/*.state.json` with status `finished` and the matching problem file. `sync` builds each technique's entries (lesson sections in note-path then section order, interview problems by round), renders the block and the index, and writes only changed files. A note's date for an interview entry is the round's `set` date.

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m unittest tests.test_technique -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hooks/technique.py tests/test_technique.py
git commit -m "technique.py: read tags, sync the notes and the index, list"
```

---

### Task 2: `cue`, `sections`, `tag`

**Files:**
- Modify: `hooks/technique.py`
- Test: `tests/test_technique.py`

**Interfaces:**
- Consumes: Task 1's `load_techniques`, `resolver`, `sync`.
- Produces: `cue`, `sections`, `tag` subcommands.

- [ ] **Step 1: Write the failing tests:**

```python
def test_cue_appends_under_in_your_words(self):
    self.tech("Symmetry", body="**In your words:**\n- \"old\" — [[gb-ch02#2.4.1 Coin piles|§2.4.1]], 2026-10-01\n\n## Traps\n")
    r = self.tq("cue", "symmetry argument", "Two piles that could be swapped", "--source", "gb-ch02#2.4.2 Wise men")
    self.assertEqual(r.returncode, 0, r.stderr)
    t = (self.vault / "techniques" / "Symmetry.md").read_text()
    self.assertRegex(t, r'- "old" — .*\n- "Two piles that could be swapped" — \[\[gb-ch02#2.4.2 Wise men\|§2.4.2\]\], \d{4}-\d{2}-\d{2}\n\n## Traps')
def test_cue_creates_the_line(self):
    self.tech("Symmetry")   # helper writes "## Reach for it when\n\n- a cue\n"
    self.tq("cue", "Symmetry", "x", "--source", "gb-ch02#2.4.1 Coin piles")
    self.assertIn("- a cue\n\n**In your words:**\n- \"x\" — ", (self.vault / "techniques" / "Symmetry.md").read_text())
def test_cue_refuses_unknown(self):
    self.assertNotEqual(self.tq("cue", "Nope", "x", "--source", "a#b").returncode, 0)
def test_sections(self):
    out = self.tq("sections", "courses/gb/gb-ch02.md").stdout
    self.assertIn("### 2.4.1 Coin piles", out); self.assertIn("  tags: Symmetry", out)
def test_tag_places_line_before_session_header(self):
    self.tech("Symmetry"); self.tech("Pigeonhole principle", aliases=["pigeonhole"])
    note = self.vault / "courses" / "gb" / "gb-ch02.md"
    note.write_text(note.read_text().replace("*Techniques: [[Symmetry]] · [[Pigeonhole]]*\n", ""))  # untag 2.4.2
    self.tq("tag", "courses/gb/gb-ch02.md", "2.4.2 Wise men", "Symmetry")
    t = note.read_text()
    self.assertIn("> body\n\n*Techniques: [[Symmetry]]*\n\n## Session — 2026-10-09", t)
def test_tag_merges_into_existing_line(self):
    self.tech("Symmetry"); self.tech("Linearity of expectation")
    self.tq("tag", "courses/gb/gb-ch02.md", "2.4.1 Coin piles", "Linearity of expectation", "Symmetry")
    t = (self.vault / "courses" / "gb" / "gb-ch02.md").read_text()
    self.assertIn("*Techniques: [[Symmetry]] · [[Linearity of expectation]]*", t)
    self.assertEqual(t.count("*Techniques:"), 4)
def test_tag_at_note_end_and_runs_sync(self):
    self.tech("Symmetry")
    self.tq("tag", "courses/gb/gb-ch02.md", "2.6.1 Handshakes", "Symmetry")
    self.assertTrue((self.vault / "techniques" / "Techniques.md").exists())
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest tests.test_technique -v`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement** the three commands per the spec. `cue` resolves the name through `resolver`, refuses an unknown one (`book.die`), and inserts after the last `- ` item following `**In your words:**`, creating that line after the `## Reach for it when` list when missing; the source label is `§<number>` of the heading, else the heading. `sections` prints each `### ` heading, then `  key idea: …` lines (from `[!summary] Key idea` callouts) and `  tags: <names>`. `tag` finds the section by heading text (exact match after the `### `), merges into its tag line or inserts a new one at its end (before the next `##`/`###` line, with one blank line on each side), writes canonical names for resolvable targets, then calls `sync()`.

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m unittest tests.test_technique -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hooks/technique.py tests/test_technique.py
git commit -m "technique.py: cue, sections and tag"
```

---

### Task 3: the mirror and interviews

**Files:**
- Modify: `hooks/md_log.py` (`append`), `hooks/interview.py` (`problem_errors`, `cmd_new`, `scorecard`, `cmd_finish`)
- Test: `tests/test_technique.py`, `tests/test_interview.py`

**Interfaces:**
- Consumes: Task 1's `sync`, `load_techniques`, `resolver`.

- [ ] **Step 1: Write the failing tests.** In `tests/test_technique.py` (mirror, with `transcript`, `append`, `user`, `assistant`, `hook` from `tests/_vault.py`, as in `tests/test_mirror_exam.py`):

```python
def test_mirror_syncs_after_a_tag_line(self):
    self.tech("Symmetry")
    note = self.vault / "courses" / "gb" / "gb-ch03.md"; note.write_text("### 3.1 New\n\nText.\n")
    s = "sess-t"; tp = transcript(self.vault, s)
    run(self.vault, "md_log.py", "link", str(note), "--session", s, "--from-now", "--no-header")
    append(tp, user("ready"), assistant("m1", text="Both passed.\n\n*Techniques: [[Symmetry]]*"))
    hook(self.vault, {"hook_event_name": "Stop", "session_id": s, "transcript_path": str(tp)})
    self.assertIn("[[gb-ch03#3.1 New|§3.1 New]]", (self.vault / "techniques" / "Symmetry.md").read_text())
def test_mirror_without_techniques_folder(self):
    note = self.vault / "lessons" / "a.md"; note.parent.mkdir(); note.write_text("### A\n")
    s = "sess-u"; tp = transcript(self.vault, s)
    run(self.vault, "md_log.py", "link", str(note), "--session", s, "--from-now", "--no-header")
    append(tp, user("ready"), assistant("m1", text="Done.\n\n*Techniques: [[Symmetry]]*"))
    r = hook(self.vault, {"hook_event_name": "Stop", "session_id": s, "transcript_path": str(tp)})
    self.assertEqual(r.returncode, 0)
    self.assertIn("*Techniques: [[Symmetry]]*", note.read_text())
```

In `tests/test_interview.py`: `problem(i)` gains `"techniques": ["Symmetry"]`, and `InterviewBase.setUp` writes `techniques/Symmetry.md` (with alias `symmetry argument`); then:

```python
def test_check_technique_names(self):
    self.iv("new", "--length", "short")
    p = problems(2); p["problems"][0]["techniques"] = ["Symetry"]; self.write_problems(p)
    self.assertIn('p1: technique "Symetry" has no note in techniques/', self.iv("check").stdout)
    p["problems"][0]["techniques"] = []; self.write_problems(p)
    self.assertIn("p1: techniques is empty", self.iv("check").stdout)
    p["problems"][0]["techniques"] = ["symmetry argument"]; self.write_problems(p)
    self.assertEqual(self.iv("check").returncode, 0)
def test_scorecard_links_techniques_and_finish_syncs(self):
    # Scorecard.ended_round + finish, then:
    note = (self.vault / NOTE.format(n=1)).read_text()
    self.assertIn("| Problem 1 | solved | 6:12 | 0 | not asked | [[Symmetry]] — technique 1 |", note)
    self.assertIn("gb interview 1, problem 1]] — solved", (self.vault / "techniques" / "Symmetry.md").read_text())
def test_past_techniques_name_the_notes(self):
    # a finished round 1 whose p1 has techniques ["Symmetry"] and technique "symmetry of piles"
    self.assertIn("  symmetry of piles [Symmetry]", self.iv("new", "--length", "short").stdout)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest tests.test_technique tests.test_interview -v`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement.** In `md_log.append`, after the file is written, `if "*Techniques:" in text:` import `technique` and call `technique.sync()` inside `try/except Exception: pass`. In `interview.py`: `problem_errors` checks `techniques` (non-empty list; each name resolves through `technique.resolver(technique.load_techniques())`); `cmd_new` prints each past problem as `  <technique text> [<names joined by ", ">]`; the scorecard's Technique cell is `[[A]], [[B]] — <technique text>` (canonical names; plain text when a name no longer resolves); `cmd_finish` calls `technique.sync()` after writing the note.

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: all PASS (update any earlier interview test whose expected scorecard row changed, and ledger it).

- [ ] **Step 5: Commit**

```bash
git add hooks/md_log.py hooks/interview.py tests/test_technique.py tests/test_interview.py
git commit -m "Technique notes: synced from the mirror; interview problems carry techniques"
```

---

### Task 4: skills, settings and docs

**Files:**
- Create: `skills/techniques/SKILL.md`
- Modify: `skills/teach/SKILL.md`, `skills/interview/SKILL.md`, `settings.json`, `README.md`, `docs/architecture.md`

- [ ] **Step 1: `skills/techniques/SKILL.md`.** Frontmatter as the other skills (`name: techniques`, description triggering on `/techniques`, "technique notes", "tag the chapters"; `argument-hint: list | sync | backfill [course]`; `allowed-tools: Bash(python3 .claude/hooks/technique.py *), Bash(python3 .claude/hooks/md_log.py *), Bash(python3 .claude/hooks/book.py *), Write, Edit`). Sections: `list`/`sync`; `backfill [course]` exactly as the spec's five steps; **Writing a technique note** — the template from the spec, with the rules: the trick in general, two to four cues phrased as features a problem statement can have, traps, related techniques, the empty problems block (both markers), canonical names only, never editing inside the block or the learner's "In your words" items.
- [ ] **Step 2: Teach skill.** In Phase 3 step 5 ("Both passed"), the closing of a section per the spec's "In lessons" list: `technique.py list`, a new technique's note (pointing to the techniques skill's template), the cue question as the end of a reply and `technique.py cue` with the answer, at most one question per section, the tag line as the section's last line, adding traps or cues to existing notes with Edit. In "Teaching from a book", one sentence that every unit's sections are tagged.
- [ ] **Step 3: Interview skill.** The problem file's `techniques` field (names from `technique.py list`; a new trick gets its note first) in "Write the problem file".
- [ ] **Step 4: Settings and docs.** `settings.json`: `Bash(python3 .claude/hooks/technique.py *)` after the interview permission. README: a `## Technique notes` section after `## Interviews` (what a note holds, the tag line, the "In your words" question, the index weakest first, `/techniques backfill`, `/techniques list` and `sync`), the contents line, the commands table, the repository layout row for `techniques/`. Architecture: a `## Technique notes` section (the tag format, resolution, the block markers, when `sync` runs and why from the mirror, interview problems).
- [ ] **Step 5: Verify and commit.** `python3 -m unittest discover -s tests -v` (all PASS); `python3 -c "import json; json.load(open('settings.json'))"`.

```bash
git add skills/techniques/SKILL.md skills/teach/SKILL.md skills/interview/SKILL.md settings.json README.md docs/architecture.md
git commit -m "Techniques skill, teach and interview skills, docs"
```
