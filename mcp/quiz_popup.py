#!/usr/bin/env python3
"""
quiz_popup — the learner-facing quiz UI, run inside `tmux display-popup`.

    quiz_popup.py <spec.json> <result.json>

spec:   {"question", "details", "options": [{"index","label","description"}],
         "multiSelect": bool, "dontKnow": "I don't know",
         "correctIndices": [..], "explanation": str}   # revealed only after answering
result: {"action":"accept","answers":[indices],"dontKnow":bool,"note":str}
        or {"action":"cancel"}

Keys: ↑/↓ or j/k move · 1-9 jump · Space toggle (multi) · Enter submit
      Tab edit note · Esc cancel
"""
import curses
import os
import json
import sys
import textwrap


def main(stdscr, spec, out_path):
    curses.curs_set(0)
    curses.use_default_colors()
    try:
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_YELLOW, -1)
        curses.init_pair(3, curses.COLOR_GREEN, -1)
        curses.init_pair(4, curses.COLOR_RED, -1)
    except Exception:
        pass
    options = spec["options"]
    multi = bool(spec.get("multiSelect"))
    dk_label = spec.get("dontKnow", "I don't know")
    entries = [(o["index"], o["label"], o.get("description") or "") for o in options] + [(0, dk_label, "")]
    cursor = 0
    selected = set()
    note = ""
    editing_note = False
    scroll = 0

    def write(result):
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)

    def show_feedback(result):
        """Instant grading, shown in the popup before it closes (like pi)."""
        correct_idx = sorted(spec.get("correctIndices") or [])
        by_index = {o["index"]: o["label"] for o in options}
        correct_str = ", ".join(f"{i}. {by_index.get(i, '?')}" for i in correct_idx)
        picked = result.get("answers", [])
        while True:
            stdscr.erase()
            h, w = stdscr.getmaxyx()
            width = max(20, w - 4)
            rows = []
            if result.get("dontKnow"):
                rows.append(("No guess made.", curses.A_BOLD | curses.color_pair(2)))
                rows.append((f"Correct answer: {correct_str}", 0))
            elif sorted(picked) == correct_idx:
                rows.append(("✓ Correct.", curses.A_BOLD | curses.color_pair(3)))
            else:
                rows.append(("✗ Incorrect.", curses.A_BOLD | curses.color_pair(4)))
                rows.append((f"Correct answer: {correct_str}", 0))
            rows.append(("", 0))
            for i, (idx, label, _) in enumerate(entries):
                if idx == 0:
                    continue
                mark = "✓" if idx in correct_idx else ("✗" if idx in picked else " ")
                attr = curses.color_pair(3) if idx in correct_idx else (curses.color_pair(4) if idx in picked else curses.A_DIM)
                rows.append((f" {mark} {idx}. {label}", attr))
            if spec.get("explanation"):
                rows.append(("", 0))
                for ln in textwrap.wrap(spec["explanation"], width):
                    rows.append((ln, 0))
            rows.append(("", 0))
            rows.append(("press any key to continue", curses.A_DIM))
            for r, (text, attr) in enumerate(rows[:h]):
                try:
                    stdscr.addnstr(r, 2, text, w - 3, attr)
                except curses.error:
                    pass
            stdscr.refresh()
            ch = stdscr.getch()
            if ch != curses.KEY_RESIZE:
                return

    def finish(result):
        if result.get("action") == "accept":
            show_feedback(result)
        write(result)

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        width = max(20, w - 4)
        lines = []  # (text, attr)
        lines.append(("QUIZ" + ("  (select all that apply)" if multi else ""), curses.A_BOLD | curses.color_pair(1)))
        lines.append(("", 0))
        for ln in textwrap.wrap(spec["question"], width) or [""]:
            lines.append((ln, curses.A_BOLD))
        if spec.get("details"):
            lines.append(("", 0))
            for ln in textwrap.wrap(spec["details"], width):
                lines.append((ln, curses.A_DIM))
        lines.append(("", 0))
        option_rows = {}
        for i, (idx, label, desc) in enumerate(entries):
            is_dk = idx == 0
            mark = ("[x]" if i in selected else "[ ]") if (multi and not is_dk) else "   "
            num = "?" if is_dk else str(idx)
            text = f"{mark} {num}. {label}"
            if desc:
                text += f" — {desc}"
            attr = curses.A_REVERSE if (i == cursor and not editing_note) else (curses.A_DIM if is_dk else 0)
            wrapped = textwrap.wrap(text, width) or [text]
            option_rows[i] = len(lines)
            for k, ln in enumerate(wrapped):
                lines.append((ln if k == 0 else "      " + ln, attr))
            if is_dk and i == len(entries) - 1:
                pass
        lines.append(("", 0))
        note_attr = curses.A_REVERSE if editing_note else curses.A_DIM
        lines.append(("Note: " + (note if note else "(Tab to add a note)"), note_attr))
        lines.append(("", 0))
        help_txt = ("↑/↓ move · Space toggle · Enter submit · Tab note · Esc cancel" if multi
                    else "↑/↓ move · Enter choose · Tab note · Esc cancel")
        if editing_note:
            help_txt = "type your note · Tab/Enter back to options · Esc cancel"
        lines.append((help_txt, curses.A_DIM))

        # keep the cursor row visible
        target = option_rows.get(cursor, 0)
        if target < scroll:
            scroll = target
        if target >= scroll + h - 1:
            scroll = target - h + 2
        for row, (text, attr) in enumerate(lines[scroll:scroll + h]):
            try:
                stdscr.addnstr(row, 2, text, w - 3, attr)
            except curses.error:
                pass
        stdscr.refresh()

        ch = stdscr.getch()
        if editing_note:
            if ch in (27,):
                write({"action": "cancel"})
                return
            if ch in (9, 10, 13):
                editing_note = False
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                note = note[:-1]
            elif 32 <= ch < 0x110000:
                try:
                    note += chr(ch)
                except ValueError:
                    pass
            continue
        if ch in (27, ord("q")):
            write({"action": "cancel"})
            return
        if ch in (curses.KEY_UP, ord("k")):
            cursor = (cursor - 1) % len(entries)
        elif ch in (curses.KEY_DOWN, ord("j")):
            cursor = (cursor + 1) % len(entries)
        elif ch == 9:
            editing_note = True
        elif ord("1") <= ch <= ord("9"):
            n = ch - ord("0")
            for i, (idx, _, _) in enumerate(entries):
                if idx == n:
                    cursor = i
                    if multi:
                        selected ^= {i}
                    break
        elif ch == ord(" ") and multi:
            if entries[cursor][0] != 0:
                selected ^= {cursor}
        elif ch in (10, 13, curses.KEY_ENTER):
            is_dk = entries[cursor][0] == 0
            if is_dk:
                finish({"action": "accept", "answers": [], "dontKnow": True, "note": note.strip()})
                return
            if multi:
                if not selected:
                    selected = {cursor}
                finish({"action": "accept", "answers": sorted(entries[i][0] for i in selected),
                        "dontKnow": False, "note": note.strip()})
                return
            finish({"action": "accept", "answers": [entries[cursor][0]], "dontKnow": False, "note": note.strip()})
            return


if __name__ == "__main__":
    os.environ.setdefault("ESCDELAY", "25")
    spec_path, out_path = sys.argv[1], sys.argv[2]
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)
    try:
        curses.wrapper(main, spec, out_path)
    except Exception as exc:  # never leave the server hanging
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"action": "cancel", "error": str(exc)}, f)
