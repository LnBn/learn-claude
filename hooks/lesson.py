#!/usr/bin/env python3
"""
lesson — helpers for resuming a multi-session lesson from its markdown log.

    lesson.py summary <lesson.md> [--notes <note.md>]
                                     print a compact resume brief: the hand-off
                                     note if one exists (given, or found as
                                     "<stem> — Resume Here.md" / "<stem> - Resume Here.md"
                                     next to the lesson), latest Checkpoint block,
                                     latest mermaid dependency map, quiz tally +
                                     recent quiz outcomes, and (if there is neither
                                     a note nor a checkpoint) the tail of the lesson
    lesson.py checkpoints <lesson.md>  list every checkpoint (date + Next line)
    lesson.py review <lesson.md>       print the review note that recall checks go to ("<slug>-review.md"
                                     in a course directory, "<stem> — Review.md" next to any other
                                     lesson) and the section headings they may cite, as wikilinks
    lesson.py lastsection <lesson.md>  print the note from its last "### " heading on: the node
                                     the learner stopped in, for a check on a text already written;
                                     the first line says whether it ends with a Key idea callout
    lesson.py reset <lesson.md>        start over: move the note, its sidecar checkpoints and (outside
                                     a course) its review note to <project>/.claude/md-log-state/trash/<timestamp>/
    lesson.py checkpoint <lesson.md>   read a checkpoint from stdin and append it to the
                                     sidecar <dir>/.checkpoints/<name>.md (hidden from
                                     Obsidian; the lesson note stays clean)

The lesson file is the md-log mirror written by hooks/md_log.py and the quiz
server — or by pi's md-log extension (its callout titles are understood too);
nothing here is loaded into context except what this script prints.
"""
import json
import os
import re
import sys

CHECKPOINT_RE = re.compile(r"^> \[!summary\] Checkpoint", re.I)
RESULT_KINDS = {
    # this setup (mcp/quiz_server.py)
    "> [!success] ✓ Correct": "✓",
    "> [!failure] ✗ Incorrect": "✗",
    "> [!info] I don't know": "?",
    "> [!warning] Quiz — cancelled": "skip",
    # pi's md-log extension
    "> [!success] Quiz — correct ✓": "✓",
    "> [!failure] Quiz — incorrect ✗": "✗",
    "> [!question] Quiz — I don't know": "?",
    "> [!warning] Quiz — cancelled": "skip",
}
NOTE_SUFFIXES = (" — Resume Here.md", " - Resume Here.md", " — resume here.md", " - resume here.md")
MAX_NOTE_LINES = 200
MAX_TAIL_LINES = 60
MAX_SECTION_LINES = 250


def course_slug(lesson_path):
    """The course slug when the note sits in a course directory (one with .course/book.json), else None."""
    d = os.path.dirname(os.path.abspath(lesson_path))
    if not os.path.exists(os.path.join(d, ".course", "book.json")):
        return None
    try:
        with open(os.path.join(d, ".course", "state.json"), encoding="utf-8") as f:
            return json.load(f).get("slug")
    except Exception:
        return None


def review_path(lesson_path):
    """Where recall checks go: one review note per course (book.py links it from the index), or one per lesson."""
    slug = course_slug(lesson_path)
    if slug:
        return os.path.join(os.path.dirname(os.path.abspath(lesson_path)), f"{slug}-review.md")
    return os.path.splitext(os.path.abspath(lesson_path))[0] + " — Review.md"


def review_sources(lesson_path):
    """The notes a recall check may test: the lesson note and, in a course, the chapter note before it."""
    slug = course_slug(lesson_path)
    if not slug:
        return [lesson_path]
    d = os.path.dirname(os.path.abspath(lesson_path))
    chapter = re.compile(re.escape(slug) + r"-(ch\d+|app[A-Z]|[\w-]+)\.md$")
    notes = sorted(n for n in os.listdir(d) if chapter.match(n)
                   and not n.endswith(("-exercises.md", "-review.md")))
    here = os.path.basename(lesson_path)
    if here not in notes:
        return [lesson_path]
    i = notes.index(here)
    return [os.path.join(d, n) for n in notes[max(0, i - 1):i + 1]]


def heading_links(note):
    """Each ### heading of a note (Plan and Overview left out) as a wikilink, labelled §<number> when it has one."""
    if not os.path.exists(note):
        return []
    stem = os.path.splitext(os.path.basename(note))[0]
    out = []
    for ln in read(note):
        if not ln.startswith("### "):
            continue
        head = re.sub(r"\s+", " ", re.sub(r"[#|^:\[\]]", " ", ln[4:])).strip()
        if not head or head.lower() in ("plan", "overview"):
            continue
        num = re.match(r"([A-Z]?\d+(?:\.\d+)*)\s", head)
        out.append(f"[[{stem}#{head}|§{num.group(1)}]]" if num else f"[[{stem}#{head}]]")
    return out


def review(lesson_path):
    rp = review_path(lesson_path)
    if os.path.exists(rp):
        lines = read(rp)
        n = sum(1 for ln in lines if ln.startswith("## Session"))
        print(f"REVIEW NOTE: {rp}  (exists, {len(quiz_outcomes(lines))} questions over {n} session(s))")
    else:
        print(f"REVIEW NOTE: {rp}  (new)")
    for src in review_sources(lesson_path):
        links = heading_links(src)
        print()
        print(f"SECTIONS OF {os.path.basename(src)} (cite the ones a question tests, exactly as written):")
        print("\n".join("  " + l for l in links) if links else "  (no section headings)")


def sidecar_path(lesson_path):
    d, name = os.path.split(os.path.abspath(lesson_path))
    return os.path.join(d, ".checkpoints", name)


def sidecar_checkpoints(lesson_path):
    """[(header, [lines])] from the sidecar, oldest first."""
    p = sidecar_path(lesson_path)
    if not os.path.exists(p):
        return []
    out, cur = [], None
    for ln in read(p):
        if ln.startswith("## "):
            cur = (ln[3:].strip(), [])
            out.append(cur)
        elif cur is not None:
            cur[1].append(ln)
    return [(h, [l for l in body]) for h, body in out]


def write_checkpoint(lesson_path, text):
    p = sidecar_path(lesson_path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    import time
    stamp = time.strftime("%Y-%m-%d (%a) %H:%M")
    block = f"## {stamp}\n\n{text.strip()}\n"
    with open(p, "a", encoding="utf-8") as f:
        f.write(("\n" if os.path.getsize(p) else "") + block)
    return p


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read().splitlines()


def callout_blocks(lines):
    """Yield (start_index, [lines]) for every '>'-prefixed block."""
    i = 0
    while i < len(lines):
        if lines[i].startswith(">"):
            j = i
            while j < len(lines) and lines[j].startswith(">"):
                j += 1
            yield i, lines[i:j]
            i = j
        else:
            i += 1


def checkpoints(lines):
    return [(i, blk) for i, blk in callout_blocks(lines) if CHECKPOINT_RE.match(blk[0])]


def last_mermaid(lines):
    text = "\n".join(lines)
    blocks = re.findall(r"```mermaid\n(.*?)```", text, flags=re.S)
    return blocks[-1].rstrip() if blocks else None


def quiz_outcomes(lines):
    """Pair each Quiz question block with the result callout that follows it.

    The result is usually the very next block. When the learner asked the teacher first (`?` in the popup),
    an "Asked before answering" note and the teacher's answer (which may hold callouts of its own) sit
    between the question and its grade, so look ahead as far as the next Quiz block."""
    blocks = list(callout_blocks(lines))
    out = []
    for k, (i, blk) in enumerate(blocks):
        if blk[0].strip() != "> [!question] Quiz":
            continue
        body = [ln[2:] if ln.startswith("> ") else ln[1:] for ln in blk[1:]]
        question = next((b for b in body if b.strip()), "").strip()
        outcome = "(unanswered)"
        for _, nxt in blocks[k + 1:]:
            head = nxt[0].strip()
            if head in RESULT_KINDS:
                outcome = RESULT_KINDS[head]
                break
            if head == "> [!question] Quiz":
                break
        out.append((question, outcome))
    return out


def max_equation_number(lines):
    """Highest \\tag{n} / ^eq-n used, so a resumed session continues the numbering."""
    text = "\n".join(lines)
    nums = [int(n) for n in re.findall(r"\\tag\{(\d+)\}", text)] + [int(n) for n in re.findall(r"^\^eq-(\d+)\s*$", text, re.M)]
    return max(nums) if nums else 0


def max_example_number(lines):
    text = "\n".join(lines)
    nums = [int(n) for n in re.findall(r"^> \[!example\] Example (\d+)", text, re.M)] + \
           [int(n) for n in re.findall(r"^\^ex-(\d+)\s*$", text, re.M)]
    return max(nums) if nums else 0


def session_count(lines):
    return sum(1 for ln in lines if ln.startswith("## Session"))


def user_prose(lines):
    """Rough count of learner prompts, for the brief (assistant prose has no banner)."""
    return sum(1 for ln in lines if ln.strip() == "> [!quote] YOU" or ln.startswith("> **You:**"))


def find_note(path):
    stem = os.path.splitext(path)[0]
    for suf in NOTE_SUFFIXES:
        cand = stem + suf
        if os.path.exists(cand):
            return cand
    return None


def summary(path, notes=None):
    if not os.path.exists(path):
        print(f"NO LESSON FILE at {path} — this is a new lesson. Start from Phase 0 of the teach skill.")
        return
    lines = read(path)
    if not any(ln.strip() for ln in lines):
        print(f"LESSON FILE IS EMPTY ({path}) — this is a new lesson. Start from Phase 0 of the teach skill.")
        return
    notes = notes or find_note(path)
    cps = checkpoints(lines)  # legacy: checkpoint callouts inside the note
    side = sidecar_checkpoints(path)
    outcomes = quiz_outcomes(lines)
    tally = {"✓": 0, "✗": 0, "?": 0, "skip": 0}
    for _, o in outcomes:
        if o in tally:
            tally[o] += 1

    print(f"LESSON: {path}")
    print(f"sessions: {session_count(lines) or 'unmarked (pi-era log)'} · prompts from learner: {user_prose(lines)} · quizzes: {len(outcomes)} "
          f"(✓ {tally['✓']} · ✗ {tally['✗']} · don't-know {tally['?']} · skipped {tally['skip']}) · "
          f"checkpoints: {len(side) + len(cps)}" + (f" · hand-off note: {os.path.basename(notes)}" if notes else "")
          + f" · equations numbered so far: {max_equation_number(lines)} · worked examples so far: "
          f"{max_example_number(lines)} (continue both from the next number)")
    print()
    if notes:
        note_lines = read(notes)
        print(f"HAND-OFF NOTE ({notes}) — written at the end of the previous session; treat it as the checkpoint:")
        print("\n".join(note_lines[:MAX_NOTE_LINES]))
        if len(note_lines) > MAX_NOTE_LINES:
            print(f"… ({len(note_lines) - MAX_NOTE_LINES} more lines — Read the file if you need them)")
        print()
    if side:
        stamp, body = side[-1]
        print(f"LATEST CHECKPOINT ({stamp}, from {sidecar_path(path)}):")
        print("\n".join(body).strip())
        print()
        print("(Anything in the note written after this checkpoint belongs to the session that saved it; "
              "see the tail of the note only if the quiz outcomes below suggest more happened.)")
    elif cps:
        i, blk = cps[-1]
        print("LATEST CHECKPOINT:")
        print("\n".join(blk))
        after = [ln for ln in lines[i + len(blk):] if ln.strip()]
        if after:
            print()
            print(f"NOTE: {len(after)} non-empty lines were written AFTER this checkpoint "
                  f"(the session continued past it). Recent tail follows.")
            print("--- tail after checkpoint ---")
            print("\n".join(lines[i + len(blk):][-MAX_TAIL_LINES:]))
    elif not notes and not side:
        print("NO CHECKPOINT FOUND. Reconstruct where things stand from the map, the quiz outcomes and the tail "
              "below, then CONFIRM your reading with the learner before teaching.")
        print("--- tail of the lesson ---")
        print("\n".join(lines[-MAX_TAIL_LINES:]))
    print()
    mm = last_mermaid(lines)
    if mm:
        print("LATEST DEPENDENCY MAP (from the plan):")
        print("```mermaid")
        print(mm)
        print("```")
        print()
    if outcomes:
        print("RECENT QUIZ OUTCOMES (oldest → newest, last 12):")
        for q, o in outcomes[-12:]:
            print(f"  [{o:>4}] {q[:110]}")
        missed = [q for q, o in outcomes if o in ("✗", "?")]
        if missed:
            print()
            print("MISSED OR UNKNOWN (candidates for the re-probe):")
            for q in missed[-8:]:
                print(f"  - {q[:110]}")
    rp = review_path(path)
    recall = quiz_outcomes(read(rp)) if os.path.exists(rp) else []
    if recall:
        missed = [q for q, o in recall if o in ("✗", "?")]
        print()
        print(f"EARLIER RECALL CHECKS ({os.path.basename(rp)}): {len(recall)} questions, {len(missed)} missed or unknown"
              + (". Missed, most recent last (re-probe these first):" if missed else "."))
        for q in missed[-8:]:
            print(f"  - {q[:110]}")


def list_checkpoints(path):
    for stamp, body in sidecar_checkpoints(path):
        nxt = next((ln for ln in body if "**Next:**" in ln), "")
        print(f"{stamp}  {nxt.strip()}")
    if not os.path.exists(path):
        return
    for i, blk in checkpoints(read(path)):
        head = blk[0].split("Checkpoint", 1)[-1].strip(" —-")
        nxt = next((ln for ln in blk if "**Next:**" in ln), "")
        print(f"line {i + 1}: {head or '(undated)'}  {nxt.lstrip('> ').strip()}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    cmd, path = sys.argv[1], os.path.expanduser(sys.argv[2])
    if cmd == "summary":
        notes = None
        if "--notes" in sys.argv:
            notes = os.path.expanduser(sys.argv[sys.argv.index("--notes") + 1])
        summary(path, notes)
    elif cmd == "checkpoints":
        list_checkpoints(path)
    elif cmd == "review":
        review(path)
    elif cmd == "lastsection":
        lines = read(path) if os.path.exists(path) else []
        heads = [i for i, ln in enumerate(lines) if ln.startswith("### ")]
        if not heads:
            print("no section heading in " + path)
            sys.exit(1)
        body = lines[heads[-1]:]
        key = any(re.match(r"> \[!summary\][-+]? Key idea", ln) for ln in body)
        print("KEY IDEA: yes — the re-entry is one line" if key else
              "KEY IDEA: none — recall what the node established in two or three sentences")
        print("\n".join(body[:MAX_SECTION_LINES]))
        if len(body) > MAX_SECTION_LINES:
            print(f"… ({len(body) - MAX_SECTION_LINES} more lines)")
    elif cmd == "reset":
        import shutil, time
        here = os.path.dirname(os.path.abspath(__file__))
        trash = os.path.join(os.path.dirname(here), "md-log-state", "trash", time.strftime("%Y%m%d-%H%M%S"))
        moved = []
        own_review = [] if course_slug(path) else [review_path(path)]  # a course's review note serves every chapter
        for src in [path, sidecar_path(path)] + own_review:
            if os.path.exists(src):
                os.makedirs(trash, exist_ok=True)
                dst = os.path.join(trash, ("checkpoints-" if src == sidecar_path(path) else "") + os.path.basename(src))
                shutil.move(src, dst)
                moved.append(dst)
        if moved:
            print("🗒 lesson reset — moved to " + trash + ":\n  " + "\n  ".join(moved))
        else:
            print("🗒 nothing to reset for " + path)
    elif cmd == "checkpoint":
        text = sys.stdin.read()
        if not text.strip():
            print("checkpoint text expected on stdin", file=sys.stderr)
            sys.exit(2)
        print(f"🗒 checkpoint saved to {write_checkpoint(path, text)}")
    else:
        print(f"unknown command {cmd}")
        sys.exit(2)
