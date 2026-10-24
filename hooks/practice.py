#!/usr/bin/env python3
"""
practice — review cards from every miss, and drills that mix every technique.

Misses are found by scanning what already exists: graded quiz blocks in lesson and review notes, graded exam
schemes, finished interview rounds and drill results. Each becomes a card in `<vault>/practice/.cards.json`, which
comes back after 1, 3, 7, 16 and 35 days as long as it is answered right, and after 1 day again when it is not.

    practice.py scan                          add cards for new misses; print how many were added
    practice.py due [--limit 10]              scan, then the due cards, oldest due first
    practice.py result <card> right|wrong     schedule the card
    practice.py stats                         active, retired, due today, and the next 7 days' due counts
    practice.py drill [--n 8]                 create a drill and print its slots
    practice.py drill-check <id>              validate the drill's problem file
    practice.py drill-result <id> <slot> --recognised right|wrong [--picked <Name>] --solved right|wrong
    practice.py drill-summary <id>            recognised and solved counts, and the confusions
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys
from datetime import date, timedelta

import book
import lesson
import quiz_block
import technique

VAULT = technique.VAULT
PRACTICE_DIR = os.path.join(VAULT, "practice")
CARDS = os.path.join(PRACTICE_DIR, ".cards.json")
DRILLS_DIR = os.path.join(PRACTICE_DIR, ".drills")
INTERVALS = [1, 3, 7, 16, 35]
SPREAD_DAYS = 14
SKIP_DIRS = {"exams", "interviews"}
TOP_SKIP = {"techniques", "practice"}


# ---------------------------------------------------------------- finding misses

def scanned_notes():
    """Lesson and review notes: every .md but those under hidden folders, techniques/, practice/, exams/, interviews/."""
    for root, dirs, files in os.walk(VAULT):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS
                         and not (root == VAULT and d in TOP_SKIP))
        for f in sorted(files):
            if f.endswith(".md"):
                yield os.path.join(root, f)


def _canonical(targets, res):
    return list(dict.fromkeys(res.get(t.lower(), t) for t in targets))


def _quiz_prompt(block):
    """The question of a quiz block: its title, or the full question when the title was cut."""
    p = quiz_block.parse(block)
    if not p["title"].endswith("…"):
        return p["title"]
    first = p["body"].strip().split("\n\n", 1)[0]
    return " ".join(first.split()) or p["title"]


def quiz_misses(res, section_tags):
    out = []
    for path in scanned_notes():
        try:
            lines = lesson.read(path)
        except (OSError, UnicodeDecodeError):
            continue
        stem = os.path.splitext(os.path.basename(path))[0]
        for i, anchor, body, _ in technique.note_sections(lines):
            section_tags[f"{stem}#{anchor}"] = _canonical(technique.section_tags(body), res)
        code = technique.fenced(lines)
        anchor, when = None, None
        for i, ln in enumerate(lines):
            if code[i]:
                continue
            m = technique.SESSION_RE.match(ln)
            if m:
                when = m.group(1)
            if ln.startswith("### "):
                anchor = technique.anchor_of(ln)
            if not quiz_block.is_quiz_header(ln) or anchor is None:
                continue
            block = [ln]
            for nxt in lines[i + 1:]:
                if not nxt.startswith(">"):
                    break
                block.append(nxt)
            p = quiz_block.parse(block)
            if p["outcome"] not in ("✗", "?"):
                continue
            title_hash = hashlib.sha1(p["title"].encode("utf-8")).hexdigest()[:8]
            section = f"{stem}#{anchor}"
            out.append({"key": f"quiz:{section}#{title_hash}", "kind": "quiz", "source": section,
                        "label": technique.long_label(anchor), "section": section,
                        "techniques": section_tags.get(section, []), "prompt": _quiz_prompt(block), "missed": when})
    return out


def exam_misses(section_tags):
    out = []
    for sp in sorted(glob.glob(os.path.join(glob.escape(VAULT), "courses", "*", ".exams", "*.json"))):
        s = book.load_json(sp, None)
        if not isinstance(s, dict) or s.get("status") != "graded" or "questions" not in s:
            continue
        stem = os.path.splitext(os.path.basename(s.get("paper") or sp))[0]
        for q in s["questions"]:
            if q.get("id") not in (s.get("misses") or []):
                continue
            section = q.get("section") or None
            out.append({"key": f"exam:{stem}#{q['id']}", "kind": "exam", "source": f"{stem}#^{q['id']}",
                        "label": f"{stem} Q{q['id'][1:]}", "section": section,
                        "techniques": section_tags.get(section, []) if section else [],
                        "prompt": " ".join(str(q.get("text") or "").split()),
                        "missed": s.get("graded") or s.get("set")})
    return out


def interview_misses(res):
    out = []
    pattern = os.path.join(glob.escape(VAULT), "courses", "*", ".interviews", "*-interview-*.state.json")
    for sp in sorted(glob.glob(pattern)):
        m = re.search(r"([^/]+)-interview-(\d+)\.state\.json$", sp)
        st = book.load_json(sp, None)
        if not m or not isinstance(st, dict) or st.get("status") != "finished":
            continue
        specs = (book.load_json(sp[:-len(".state.json")] + ".json", None) or {}).get("problems") or []
        stem = f"{m.group(1)}-interview-{m.group(2)}"
        for i, (pr, spec) in enumerate(zip(st.get("problems") or [], specs), 1):
            if pr.get("outcome") not in ("hinted", "unsolved"):
                continue
            out.append({"key": f"interview:{stem}#p{i}", "kind": "interview", "source": f"{stem}#Problem {i}",
                        "label": f"{m.group(1)} interview {m.group(2)}, problem {i}", "section": None,
                        "techniques": _canonical(spec.get("techniques") or [], res),
                        "prompt": " ".join(str(spec.get("statement") or "").split()), "missed": st.get("set")})
    return out


def find_misses():
    res = technique.resolver(technique.load_techniques())
    section_tags = {}
    out = quiz_misses(res, section_tags)
    return out + exam_misses(section_tags) + interview_misses(res)


# ---------------------------------------------------------------- the cards

def load_cards():
    """The cards file, or None when there is none yet (the first scan)."""
    if not os.path.exists(CARDS):
        return None
    try:
        with open(CARDS, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("cards"), list):
            raise ValueError
        return data
    except (OSError, ValueError):
        book.die(f"{book.rel(CARDS)} cannot be read; fix it or move it away (a new one starts the cards afresh)", 1)


def save_cards(data):
    os.makedirs(PRACTICE_DIR, exist_ok=True)
    tmp = CARDS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, CARDS)


def scan(today=None):
    today = today or date.today()
    data = load_cards()
    first = data is None
    data = data or {"cards": []}
    seen = {c["key"] for c in data["cards"]}
    new = sorted((m for m in find_misses() if m["key"] not in seen), key=lambda m: (m["missed"] or "", m["key"]))
    new = list({m["key"]: m for m in new}.values())  # a quiz re-asked with the same title is one card
    nxt = max([int(c["id"][1:]) for c in data["cards"]], default=0) + 1
    for k, m in enumerate(new):
        if first:
            due = today + timedelta(1 + k * SPREAD_DAYS // len(new))
        else:
            missed = date.fromisoformat(m["missed"]) if m["missed"] else today
            due = max(missed + timedelta(1), today)
        data["cards"].append({"id": f"c{nxt + k}", **m, "step": 0, "due": due.isoformat(), "status": "active",
                              "history": []})
    if new or first:
        save_cards(data)
    return len(new)


def schedule(card, result, today=None):
    today = today or date.today()
    card["history"].append({"date": today.isoformat(), "result": result})
    if result == "right":
        card["step"] += 1
        if card["step"] >= len(INTERVALS):
            card["status"] = "retired"
            return
        card["due"] = (today + timedelta(INTERVALS[card["step"]])).isoformat()
    else:
        card["step"] = 0
        card["due"] = (today + timedelta(1)).isoformat()


def due_cards(limit=None, today=None):
    today = (today or date.today()).isoformat()
    data = load_cards() or {"cards": []}
    due = sorted((c for c in data["cards"] if c["status"] == "active" and c["due"] <= today),
                 key=lambda c: (c["due"], int(c["id"][1:])))
    return due[:limit] if limit else due


def note_path(stem):
    return next((p for p in scanned_notes() if os.path.splitext(os.path.basename(p))[0] == stem), None)


def section_key_ideas(section):
    stem, _, anchor = (section or "").partition("#")
    path = note_path(stem) if stem else None
    if not path:
        return []
    for _, a, body, _ in technique.note_sections(lesson.read(path)):
        if a == anchor:
            return technique.key_ideas(body)
    return []


# ---------------------------------------------------------------- commands

def cmd_scan(a):
    print(f"🗒 practice: added {scan()} cards")


def cmd_due(a):
    scan()
    cards = due_cards(a.limit)
    if not cards:
        print("NO CARDS DUE")
        return
    for c in cards:
        print(f"{c['id']} · {c['kind']} · {c['label']} — [[{c['source']}|{c['label']}]]")
        print(f"  techniques: {', '.join(c['techniques']) or '—'}")
        print(f"  prompt: {c['prompt']}")
        for idea in section_key_ideas(c.get("section")):
            print(f"  key idea: {idea}")


def cmd_result(a):
    data = load_cards() or {"cards": []}
    card = next((c for c in data["cards"] if c["id"] == a.card), None)
    if card is None:
        book.die(f"no card {a.card}", 1)
    schedule(card, a.result)
    save_cards(data)
    print(f"🗒 {card['id']}: " + ("retired" if card["status"] == "retired" else f"next due {card['due']}"))


def cmd_stats(a):
    data = load_cards() or {"cards": []}
    today = date.today()
    active = [c for c in data["cards"] if c["status"] == "active"]
    retired = sum(c["status"] == "retired" for c in data["cards"])
    due_now = sum(c["due"] <= today.isoformat() for c in active)
    week = [sum(c["due"] == (today + timedelta(d)).isoformat() for c in active) for d in range(1, 8)]
    print(f"active {len(active)} · retired {retired} · due today {due_now}")
    print("next 7 days: " + " ".join(str(n) for n in week))


def main(argv=None):
    p = argparse.ArgumentParser(prog="practice.py", description="Review cards and drills.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan")
    s = sub.add_parser("due")
    s.add_argument("--limit", type=int, default=None)
    s = sub.add_parser("result")
    s.add_argument("card")
    s.add_argument("result", choices=["right", "wrong"])
    sub.add_parser("stats")
    a = p.parse_args(argv)
    {"scan": cmd_scan, "due": cmd_due, "result": cmd_result, "stats": cmd_stats}[a.cmd](a)


if __name__ == "__main__":
    main()
