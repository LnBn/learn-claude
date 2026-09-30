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
    lesson.py reset <lesson.md>        start over: move the note and its sidecar checkpoints
                                     to <project>/.claude/md-log-state/trash/<timestamp>/
    lesson.py checkpoint <lesson.md>   read a checkpoint from stdin and append it to the
                                     sidecar <dir>/.checkpoints/<name>.md (hidden from
                                     Obsidian; the lesson note stays clean)

The lesson file is the md-log mirror written by hooks/md_log.py and the quiz
server — or by pi's md-log extension (its callout titles are understood too);
nothing here is loaded into context except what this script prints.
"""
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
    """Pair each Quiz question block with the result callout that follows it."""
    blocks = list(callout_blocks(lines))
    out = []
    for k, (i, blk) in enumerate(blocks):
        if blk[0].strip() != "> [!question] Quiz":
            continue
        body = [ln[2:] if ln.startswith("> ") else ln[1:] for ln in blk[1:]]
        question = next((b for b in body if b.strip()), "").strip()
        outcome = "(unanswered)"
        if k + 1 < len(blocks):
            head = blocks[k + 1][1][0].strip()
            outcome = RESULT_KINDS.get(head, outcome)
        out.append((question, outcome))
    return out


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
        print(f"NO LESSON FILE at {path} — this is a new lesson. Start from Phase 1 of the teach skill.")
        return
    lines = read(path)
    if not any(ln.strip() for ln in lines):
        print(f"LESSON FILE IS EMPTY ({path}) — this is a new lesson. Start from Phase 1 of the teach skill.")
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
          f"checkpoints: {len(side) + len(cps)}" + (f" · hand-off note: {os.path.basename(notes)}" if notes else ""))
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
    elif cmd == "reset":
        import shutil, time
        here = os.path.dirname(os.path.abspath(__file__))
        trash = os.path.join(os.path.dirname(here), "md-log-state", "trash", time.strftime("%Y%m%d-%H%M%S"))
        moved = []
        for src in (path, sidecar_path(path)):
            if os.path.exists(src):
                os.makedirs(trash, exist_ok=True)
                dst = os.path.join(trash, ("checkpoints-" if src != path else "") + os.path.basename(src))
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
