#!/usr/bin/env python3
"""
lesson — helpers for resuming a multi-session lesson from its markdown log.

    lesson.py summary <lesson.md>    print a compact resume brief:
                                     latest Checkpoint block, latest mermaid
                                     dependency map, quiz tally + recent
                                     quiz outcomes, and (if no checkpoint
                                     exists) the tail of the lesson
    lesson.py checkpoints <lesson.md>  list every checkpoint (date + Next line)

The lesson file is the md-log mirror written by hooks/md_log.py and the quiz
server; nothing here is loaded into context except what this script prints.
"""
import os
import re
import sys

CHECKPOINT_RE = re.compile(r"^> \[!summary\] Checkpoint", re.I)
RESULT_KINDS = {
    "> [!success] ✓ Correct": "✓",
    "> [!failure] ✗ Incorrect": "✗",
    "> [!info] I don't know": "?",
    "> [!warning] Quiz — cancelled": "skip",
}
MAX_TAIL_LINES = 60


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


def user_prose(lines):
    """Rough count of learner prompts, for the brief."""
    return sum(1 for ln in lines if ln.strip() == "> [!quote] YOU")


def summary(path):
    if not os.path.exists(path):
        print(f"NO LESSON FILE at {path} — this is a new lesson. Start from Phase 1 of the teach skill.")
        return
    lines = read(path)
    if not any(ln.strip() for ln in lines):
        print(f"LESSON FILE IS EMPTY ({path}) — this is a new lesson. Start from Phase 1 of the teach skill.")
        return
    cps = checkpoints(lines)
    outcomes = quiz_outcomes(lines)
    tally = {"✓": 0, "✗": 0, "?": 0, "skip": 0}
    for _, o in outcomes:
        if o in tally:
            tally[o] += 1

    print(f"LESSON: {path}")
    print(f"prompts from learner: {user_prose(lines)} · quizzes: {len(outcomes)} "
          f"(✓ {tally['✓']} · ✗ {tally['✗']} · don't-know {tally['?']} · skipped {tally['skip']}) · "
          f"checkpoints: {len(cps)}")
    print()
    if cps:
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
    else:
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
    if not os.path.exists(path):
        print("no lesson file")
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
        summary(path)
    elif cmd == "checkpoints":
        list_checkpoints(path)
    else:
        print(f"unknown command {cmd}")
        sys.exit(2)
