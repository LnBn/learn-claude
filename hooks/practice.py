#!/usr/bin/env python3
"""
practice — review cards from every miss, and drills that mix every technique.

Misses are found by scanning what already exists: graded quiz blocks in lesson and review notes, graded exam
schemes, finished interview rounds, drill results, and the problems of a problem course that needed hints or were
not solved. Each becomes a card in `<vault>/practice/.cards.json`, which
comes back after 1, 3, 7, 16 and 35 days as long as it is answered right, and after 1 day again when it is not.
A lesson quiz answered right but at 40% confidence or less is a fragile card: it comes back once, after 3 days.
Due cards come misconceptions first, then misses made at 80% confidence or more, then oldest due first.

    practice.py scan                          add cards for new misses; print how many were added
    practice.py due [--limit 10]              scan, then the due cards in that order
    practice.py result <card> right|wrong [--miss <kind>] [--confidence N]
                                              schedule the card; a wrong answer names its kind of miss
    practice.py stats                         active, retired, due today, and the next 7 days' due counts
    practice.py drill [--n 8]                 create a drill and print its slots
    practice.py drill-check <id>              validate the drill's problem file
    practice.py drill-result <id> <slot> --recognised right|wrong [--picked <Name>] --solved right|wrong
                             [--miss <kind>] [--hint <level>] [--confidence N]
    practice.py drill-retests <id>            the slots to retest: misses, and problems that needed hint level 3+
    practice.py drill-retest <id> <slot> right|wrong [--miss <kind>]
    practice.py drill-summary <id>            recognised, solved and retest counts, the kinds of miss, the confusions

Kinds of miss: recall (nothing came to mind), method (the wrong method), execution (the right method, carried out
wrongly), careless, misconception (a wrong belief).
"""
import argparse
import glob
import hashlib
import json
import os
import random
import re
import sys
from datetime import date, timedelta

import book
import lesson
import quiz_block
import technique

sys.path.insert(0, os.path.join(technique.CLAUDE_DIR, "mcp"))
import answer_check  # noqa: E402  (drill answers: the typed-answer checker)

VAULT = technique.VAULT
PRACTICE_DIR = os.path.join(VAULT, "practice")
CARDS = os.path.join(PRACTICE_DIR, ".cards.json")
DRILLS_DIR = os.path.join(PRACTICE_DIR, ".drills")
INTERVALS = [1, 3, 7, 16, 35]
SPREAD_DAYS = 14
SKIP_DIRS = {"exams", "interviews"}
TOP_SKIP = {"techniques", "practice"}
MIN_TECHNIQUES = 4  # the recognition question has four options
MISS_KINDS = ("recall", "method", "execution", "careless", "misconception")
CONFIDENT = 80  # a miss at this confidence or above is a confident miss
UNSURE = 40  # a right answer at this confidence or below is fragile
FRAGILE_DAYS = 3
DEMANDS = ("recall", "discrimination", "composition")  # a drill slot's demand, in the order a technique meets them
RETEST_LEVEL = 3  # a drill problem that needed a hint at this level or above is retested
STRONG_FLOOR = 2


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
    body = p["body"].strip()
    if body.startswith(p["title"].rstrip("…")):  # the block holds the full question when the title is not all of it
        return " ".join(body.split("\n\n", 1)[0].split()) or p["title"]
    return p["title"]


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
        review = stem.endswith("-review") or stem.endswith(" — Review")
        anchor, when = None, None
        for i, ln in enumerate(lines):
            if code[i]:
                continue
            m = technique.SESSION_RE.match(ln)
            if m:
                when = m.group(1)
            if ln.startswith("### "):
                anchor = technique.anchor_of(ln)
            elif ln.startswith("## ") and review:
                anchor = None  # a recall check opens its own "### Before …" section; a lesson session continues one
            if not quiz_block.is_quiz_header(ln):
                continue
            block = [ln]
            for nxt in lines[i + 1:]:
                if not nxt.startswith(">"):
                    break
                block.append(nxt)
            p = quiz_block.parse(block)
            fragile = p["outcome"] == "✓" and p["confidence"] is not None and p["confidence"] <= UNSURE
            if p["outcome"] not in ("✗", "?") and not fragile:
                continue
            title_hash = hashlib.sha1(p["title"].encode("utf-8")).hexdigest()[:8]
            section = f"{stem}#{anchor}" if anchor else stem
            m = {"key": f"quiz:{section}#{title_hash}", "kind": "quiz", "source": section,
                 "label": technique.long_label(anchor) if anchor else stem, "section": section,
                 "techniques": section_tags.get(section, []), "prompt": _quiz_prompt(block), "missed": when}
            if p["confidence"] is not None and p["outcome"] != "?":
                m["confidence"] = p["confidence"]
            if fragile:
                m["fragile"] = True
            out.append(m)
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
    for sp in technique.interview_state_files():
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


def drill_misses():
    out = []
    for d in drills():
        problems = {p.get("slot"): p for p in (load_drill_problems(d["id"]) or [])}
        for sl in d["slots"]:
            if "recognised" not in sl or (sl["recognised"] == "right" and sl["solved"] == "right"):
                continue
            m = {"key": f"drill:{d['id']}#{sl['slot']}", "kind": "drill",
                 "source": f"practice/{d['date']}#Drill {d['id']}",
                 "label": f"drill {d['id']}, problem {sl['slot']}", "section": None,
                 "techniques": [sl["technique"]],
                 "prompt": " ".join(str(problems.get(sl["slot"], {}).get("statement") or "").split()),
                 "missed": d["date"]}
            out.append({**m, **{k: sl[k] for k in ("miss", "confidence") if sl.get(k) is not None}})
    return out


def statement(body):
    """The problem as stated in a problem course's section: the paragraph that opens with **The problem.**"""
    for p in "\n".join(body).split("\n\n"):
        m = re.match(r"^\*\*The problem\.?\*\*\s*(.*)$", p.strip(), re.S)
        if m:
            return " ".join(m.group(1).split())
    return ""


def problem_misses(section_tags):
    """Attempts at a problem of a course in problems mode that needed hints or were not solved."""
    out, notes = [], {}
    for a in technique.problem_attempts():
        if a["outcome"] not in ("hinted", "unsolved"):
            continue
        path = os.path.join(a["dir"], a["note"] + ".md")
        if path not in notes:
            try:
                notes[path] = technique.note_sections(lesson.read(path))
            except (OSError, UnicodeDecodeError):
                notes[path] = []
        sections = notes[path]
        k = technique.problem_sections(sections).get(a["n"])
        anchor = sections[k][1] if k is not None else f"{a['n']} {a['title']}".strip()
        body = sections[k][2] if k is not None else []
        section = f"{a['note']}#{anchor}"
        m = {"key": f"problem:{a['slug']}/{a['eid']}#{a['k']}", "kind": "problem", "source": section,
             "label": technique.long_label(anchor), "section": section,
             "techniques": section_tags.get(section, []), "prompt": statement(body) or a["title"],
             "missed": a["at"]}
        if a.get("miss"):
            m["miss"] = a["miss"]
        out.append(m)
    return out


def find_misses():
    res = technique.resolver(technique.load_techniques())
    section_tags = {}
    out = quiz_misses(res, section_tags)
    return out + exam_misses(section_tags) + interview_misses(res) + drill_misses() + problem_misses(section_tags)


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
    merged = {}  # a quiz re-asked with the same title is one card: the last answer, but a miss wins over a fragile one
    for m in new:
        old = merged.get(m["key"])
        if old is None or not m.get("fragile") or old.get("fragile"):
            merged[m["key"]] = m
    new = list(merged.values())
    nxt = max([int(c["id"][1:]) for c in data["cards"]], default=0) + 1
    for k, m in enumerate(new):
        if first:
            due = today + timedelta(1 + k * SPREAD_DAYS // len(new))
        else:
            missed = date.fromisoformat(m["missed"]) if m["missed"] else today
            due = max(missed + timedelta(FRAGILE_DAYS if m.get("fragile") else 1), today)
        data["cards"].append({"id": f"c{nxt + k}", **m, "step": 0, "due": due.isoformat(), "status": "active",
                              "history": []})
    if new or first:
        save_cards(data)
    return len(new)


def schedule(card, result, today=None, miss=None, confidence=None):
    """Right moves the card a step (a fragile card retires); wrong sends it back to tomorrow and records the kind of
    miss and the confidence, which order the due cards. Right at 40% or less is not a step forward: the gap repeats."""
    today = today or date.today()
    entry = {"date": today.isoformat(), "result": result}
    entry.update({k: v for k, v in (("miss", miss), ("confidence", confidence)) if v is not None})
    card["history"].append(entry)
    unsure = confidence is not None and confidence <= UNSURE
    if result == "right":
        card.pop("miss", None)
        card.pop("confidence", None)
        if card.get("fragile") and not unsure:
            card["status"] = "retired"
            return
        if card.get("fragile") or unsure:
            gap = FRAGILE_DAYS if card.get("fragile") else INTERVALS[card["step"]]
            card["due"] = (today + timedelta(gap)).isoformat()
            return
        card["step"] += 1
        if card["step"] >= len(INTERVALS):
            card["status"] = "retired"
            return
        card["due"] = (today + timedelta(INTERVALS[card["step"]])).isoformat()
    else:
        card.pop("fragile", None)
        for k, v in (("miss", miss), ("confidence", confidence)):
            if v is None:
                card.pop(k, None)
            else:
                card[k] = v
        card["step"] = 0
        card["status"] = "active"
        card["due"] = (today + timedelta(1)).isoformat()


def priority(card):
    """0 a misconception, 1 a confident miss, 2 any other card."""
    if card.get("miss") == "misconception":
        return 0
    if not card.get("fragile") and (card.get("confidence") or 0) >= CONFIDENT:
        return 1
    return 2


def due_cards(limit=None, today=None):
    today = (today or date.today()).isoformat()
    data = load_cards() or {"cards": []}
    due = sorted((c for c in data["cards"] if c["status"] == "active" and c["due"] <= today),
                 key=lambda c: (priority(c), c["due"], int(c["id"][1:])))
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


# ---------------------------------------------------------------- drills

def drill_path(drill_id, problems=False):
    return os.path.join(DRILLS_DIR, f"{drill_id}{'.problems' if problems else ''}.json")


def drills():
    """Every drill, oldest first."""
    out = []
    for p in sorted(glob.glob(os.path.join(glob.escape(DRILLS_DIR), "*.json"))):
        if p.endswith(".problems.json"):
            continue
        d = book.load_json(p, None)
        if isinstance(d, dict) and isinstance(d.get("slots"), list):
            out.append(d)
    return out


def load_drill(drill_id):
    d = book.load_json(drill_path(drill_id), None)
    if not isinstance(d, dict):
        book.die(f"no drill {drill_id}", 1)
    return d


def save_drill(d):
    book.save_json(drill_path(d["id"]), d)


def load_drill_problems(drill_id):
    data = book.load_json(drill_path(drill_id, problems=True), None)
    return data.get("problems") if isinstance(data, dict) else None


def drill_rates():
    """{technique: (recognised right, recognised total, solved right, solved total)} over every drill."""
    out = {}
    for d in drills():
        for sl in d["slots"]:
            if "recognised" not in sl:
                continue
            r = out.setdefault(sl["technique"], [0, 0, 0, 0])
            r[0] += sl["recognised"] == "right"
            r[1] += 1
            r[2] += sl["solved"] == "right"
            r[3] += 1
    return {k: tuple(v) for k, v in out.items()}


def _rate(right, total):
    return right / total if total else 0.5


def clean(sl):
    """A drill slot named and solved, with no hint at level 3 or above."""
    return sl.get("recognised") == "right" and sl.get("solved") == "right" and (sl.get("hint") or 0) < RETEST_LEVEL


def demands_shown():
    """{technique: the demands it has met cleanly in a drill}; a slot from before demands existed counts as recall."""
    out = {}
    for d in drills():
        for sl in d["slots"]:
            if clean(sl):
                out.setdefault(sl["technique"], set()).add(sl.get("demand") or "recall")
    return out


def confusions():
    """{technique: {other technique: times one was taken for the other}} over every drill."""
    out = {}
    for d in drills():
        for sl in d["slots"]:
            if sl.get("recognised") == "wrong" and sl.get("picked"):
                for a, b in ((sl["technique"], sl["picked"]), (sl["picked"], sl["technique"])):
                    out.setdefault(a, {})[b] = out.get(a, {}).get(b, 0) + 1
    return out


def plan_drill(n, drill_id):
    """[{"slot", "technique", "wrong"}]: techniques drawn by weakness, at least two strong ones, shuffled."""
    techs, entries, _, _ = technique.collect()
    names = sorted(techs)
    if len(names) < MIN_TECHNIQUES:
        book.die("a drill needs at least 4 technique notes; /techniques backfill makes them", 1)
    passes = {}
    for name in names:
        p, m = technique.record(entries[name])
        passes[name] = _rate(p, p + m)
    recog = drill_rates()
    weight = {name: 1 + 2 * (1 - passes[name]) + 2 * (1 - _rate(*recog.get(name, (0, 0))[:2])) for name in names}
    rng = random.Random(hashlib.sha256(drill_id.encode()).hexdigest())

    def draw(pool):
        return rng.choices(pool, weights=[weight[x] for x in pool])[0]

    picks = []
    for _ in range(n):
        left = [x for x in names if x not in picks]
        picks.append(draw(left or names))
    tie = {x: rng.random() for x in names}  # equal records: no alphabetical bias
    strong = sorted(names, key=lambda x: (-passes[x], tie[x]))[:len(names) // 2]
    need = min(STRONG_FLOOR, n // 2)  # a small drill keeps room for weak techniques
    for i in reversed(range(len(picks))):  # replace the last drawn weak slots until the floor is met
        if sum(x in strong for x in picks) >= need:
            break
        if picks[i] not in strong:
            unused = [x for x in strong if x not in picks]
            picks[i] = draw(unused or strong)
    for _ in range(100):  # interleaved: no technique twice in a row, unless no order avoids it
        rng.shuffle(picks)
        if all(x != y for x, y in zip(picks, picks[1:])):
            break
    shown, confused = demands_shown(), confusions()
    out = []
    for i, t in enumerate(picks, 1):
        met = set(shown.get(t, set())) | ({"recall"} if t in strong else set())
        demand = next((x for x in DEMANDS if x not in met), DEMANDS[-1])
        wrong = rng.sample([x for x in names if x != t], 3)
        slot = {"slot": i, "technique": t, "demand": demand, "wrong": wrong}
        if demand == "discrimination":  # the near twin: the technique most often confused with it, else a wrong option
            seen = {k: v for k, v in confused.get(t, {}).items() if k in names and k != t}
            twin = max(sorted(seen), key=lambda k: seen[k]) if seen else wrong[0]
            if twin not in wrong:
                wrong[0] = twin
            slot["twin"] = twin
        out.append(slot)
    return out


def _callout(lines, head):
    for i, ln in enumerate(lines):
        if ln.startswith(head):
            out = []
            for nxt in lines[i + 1:]:
                if not nxt.startswith(">"):
                    break
                out.append(nxt.lstrip(">").strip())
            return " ".join(x for x in out if x)
    return ""


def _items_after(lines, marker):
    out, inside = [], False
    for ln in lines:
        if ln.strip() == marker:
            inside = True
            continue
        if inside:
            if ln.startswith("- "):
                out.append(ln[2:].strip())
            elif ln.strip():
                break
    return out


def technique_brief(name):
    """(trick, cues, problems already used) from a technique note."""
    t = technique.load_techniques().get(name)
    lines = lesson.read(t["path"]) if t else []
    trick = _callout(lines, "> [!definition] The trick")
    cues = _items_after(lines, "## Reach for it when")
    cues += [re.sub(r'^"(.*?)".*$', r"\1", c) for c in _items_after(lines, "**In your words:**")]
    text = "\n".join(lines)
    used = []
    if technique.START in text and technique.END in text:
        block = text[text.index(technique.START):text.index(technique.END)]
        used = [ln[2:] for ln in block.split("\n") if ln.startswith("- ")]
    return trick, cues, used


def cmd_drill(a):
    if a.n < 1:
        book.die("a drill needs at least 1 problem", 1)
    today = date.today().isoformat()
    taken = [int(m.group(1)) for p in glob.glob(os.path.join(glob.escape(DRILLS_DIR), f"{today}-*.json"))
             for m in [re.search(r"-(\d+)(?:\.problems)?\.json$", p)] if m]
    drill_id = f"{today}-{max(taken, default=0) + 1}"
    slots = plan_drill(a.n, drill_id)
    os.makedirs(DRILLS_DIR, exist_ok=True)
    save_drill({"id": drill_id, "date": today, "n": a.n, "slots": slots})
    print(f"DRILL: {drill_id}")
    print(f"PROBLEMS: {book.rel(drill_path(drill_id, problems=True))}")
    for sl in slots:
        trick, cues, used = technique_brief(sl["technique"])
        print(f"SLOT {sl['slot']}: {sl['technique']}")
        print(f"  demand: {sl['demand']}" + (f" — near twin: {sl['twin']}" if sl.get("twin") else ""))
        print(f"  trick: {trick or '—'}")
        print(f"  cues: {'; '.join(cues) or '—'}")
        print(f"  already used: {'; '.join(used) or '(none)'}")
        print(f"  wrong options: {', '.join(sl['wrong'])}")


def cmd_drill_check(a):
    d = load_drill(a.id)
    problems = load_drill_problems(a.id)
    if problems is None:
        book.die(f"no problem file at {book.rel(drill_path(a.id, problems=True))}", 1)
    by_slot = {p.get("slot"): p for p in problems if isinstance(p, dict)}
    errors = []
    missing = [str(sl["slot"]) for sl in d["slots"] if sl["slot"] not in by_slot]
    if missing:
        errors.append(f"a problem for every slot: missing {', '.join(missing)}")
    known = {sl["slot"] for sl in d["slots"]}
    errors += [f"slot {slot} is not in the drill" for slot in by_slot if slot not in known]
    for slot, p in sorted(by_slot.items(), key=lambda x: str(x[0])):
        for field in ("statement", "solution"):
            if not str(p.get(field) or "").strip():
                errors.append(f"slot {slot}: {field} is empty")
        variables = p.get("variables") or {}
        try:
            answer_check.parse_ranges(variables)
            answer = str(p.get("answer", ""))
            answer_check.read(answer, variables)
            if answer_check.defined_points(answer, variables) < min(3, len(answer_check.points(answer, variables))):
                errors.append(f"slot {slot}: answer is undefined at most points of the ranges")
        except answer_check.AnswerError as exc:
            errors.append(f"slot {slot}: answer: {exc}")
    if errors:
        print("\n".join(errors))
        sys.exit(1)
    d["ready"] = True
    save_drill(d)
    print(f"🗒 drill ready: {len(by_slot)} problems")


def cmd_drill_result(a):
    d = load_drill(a.id)
    sl = next((x for x in d["slots"] if str(x["slot"]) == a.slot), None)
    if sl is None:
        book.die(f"drill {a.id} has no slot {a.slot}", 1)
    if "recognised" in sl:
        book.die(f"slot {a.slot} of drill {a.id} is already recorded", 1)
    if a.picked and a.picked not in sl["wrong"]:
        book.die(f"--picked {a.picked!r} is not one of the options: {', '.join(sl['wrong'])}", 1)
    missed = "wrong" in (a.recognised, a.solved)
    if missed and not a.miss:
        book.die(f"a part is wrong: give its kind with --miss {'|'.join(MISS_KINDS)}", 1)
    if a.miss and not missed:
        book.die("--miss is for a slot with a part wrong", 1)
    sl.update({"recognised": a.recognised, "solved": a.solved, "date": date.today().isoformat()})
    for k in ("picked", "miss", "hint", "confidence"):
        if getattr(a, k) is not None:
            sl[k] = getattr(a, k)
    save_drill(d)
    print(f"🗒 slot {a.slot}: recognised {a.recognised}, solved {a.solved}"
          + (f", {a.miss} miss" if a.miss else "") + (f", hints up to level {a.hint}" if a.hint is not None else ""))


def needs_retest(sl):
    """Why a recorded slot is retested at the end of its drill, or None."""
    if "recognised" not in sl:
        return None
    if sl["recognised"] == "wrong" or sl["solved"] == "wrong":
        return f"missed ({sl.get('miss') or 'kind not recorded'})"
    if (sl.get("hint") or 0) >= RETEST_LEVEL:
        return f"needed a hint at level {sl['hint']}"
    return None


def cmd_drill_retests(a):
    d = load_drill(a.id)
    problems = {p.get("slot"): p for p in (load_drill_problems(a.id) or [])}
    due = [sl for sl in d["slots"] if needs_retest(sl) and "retest" not in sl]
    if not due:
        print("NO RETESTS" if not any(needs_retest(sl) for sl in d["slots"]) else "RETESTS DONE")
        return
    for sl in due:
        print(f"RETEST {sl['slot']}: {sl['technique']} — {needs_retest(sl)}")
        print(f"  demand: {sl.get('demand') or 'recall'}")
        print(f"  the problem it replaces: {' '.join(str(problems.get(sl['slot'], {}).get('statement') or '').split())}")


def cmd_drill_retest(a):
    d = load_drill(a.id)
    sl = next((x for x in d["slots"] if str(x["slot"]) == a.slot), None)
    if sl is None:
        book.die(f"drill {a.id} has no slot {a.slot}", 1)
    if not needs_retest(sl):
        book.die(f"slot {a.slot} of drill {a.id} needs no retest", 1)
    if "retest" in sl:
        book.die(f"the retest of slot {a.slot} is already recorded", 1)
    if a.result == "wrong" and not a.miss:
        book.die(f"give the kind of miss with --miss {'|'.join(MISS_KINDS)}", 1)
    sl["retest"] = a.result
    if a.miss:
        sl["retest_miss"] = a.miss
    save_drill(d)
    print(f"🗒 retest of slot {a.slot}: {a.result}")


def cmd_drill_summary(a):
    d = load_drill(a.id)
    done = [sl for sl in d["slots"] if "recognised" in sl]
    rec = sum(sl["recognised"] == "right" for sl in done)
    sol = sum(sl["solved"] == "right" for sl in done)
    retests = [sl for sl in done if needs_retest(sl)]
    line = f"Recognised {rec}/{len(done)} · solved {sol}/{len(done)}"
    if retests:
        line += f" · retests {sum(sl.get('retest') == 'right' for sl in retests)}/{len(retests)}"
    print(line)
    kinds = {}
    for sl in done:
        if sl.get("miss"):
            kinds[sl["miss"]] = kinds.get(sl["miss"], 0) + 1
    if kinds:
        print("kinds of miss: " + " · ".join(f"{k} {n}" for k, n in sorted(kinds.items(), key=lambda x: (-x[1], x[0]))))
    for sl in done:
        if sl["recognised"] == "wrong" and sl.get("picked"):
            print(f"took {sl['picked']} for {sl['technique']}")
    try:
        technique.sync()  # the notes' Drills lines and the index's Recognised column
    except Exception:
        pass


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
        if c.get("fragile"):
            how = f"at {c['confidence']}% confidence" if c.get("confidence") is not None else "but unsure"
            print(f"  fragile: answered right {how}; one right answer above {UNSURE}% retires it")
        elif c.get("miss") or c.get("confidence") is not None:
            print("  last miss: " + " · ".join(x for x in (c.get("miss"), f"{c['confidence']}% sure"
                                                           if c.get("confidence") is not None else "") if x))
        for idea in section_key_ideas(c.get("section")):
            print(f"  key idea: {idea}")


def cmd_result(a):
    data = load_cards() or {"cards": []}
    card = next((c for c in data["cards"] if c["id"] == a.card), None)
    if card is None:
        book.die(f"no card {a.card}", 1)
    if a.result == "wrong" and not a.miss:
        book.die(f"a wrong answer needs its kind: --miss {'|'.join(MISS_KINDS)}", 1)
    if a.result == "right" and a.miss:
        book.die("--miss is for a wrong answer", 1)
    schedule(card, a.result, miss=a.miss, confidence=a.confidence)
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
    if active:
        first = min(c["due"] for c in active)
        print(f"next due: {first} ({sum(c['due'] == first for c in active)} cards)")
    else:
        print("next due: none")


def confidence_arg(text):
    n = int(text)
    if not 0 <= n <= 100:
        raise argparse.ArgumentTypeError("a percentage, 0-100")
    return n


def main(argv=None):
    p = argparse.ArgumentParser(prog="practice.py", description="Review cards and drills.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan")
    s = sub.add_parser("due")
    s.add_argument("--limit", type=int, default=None)
    s = sub.add_parser("result")
    s.add_argument("card")
    s.add_argument("result", choices=["right", "wrong"])
    s.add_argument("--miss", choices=MISS_KINDS)
    s.add_argument("--confidence", type=confidence_arg)
    sub.add_parser("stats")
    s = sub.add_parser("drill")
    s.add_argument("--n", type=int, default=8)
    s = sub.add_parser("drill-check")
    s.add_argument("id")
    s = sub.add_parser("drill-result")
    s.add_argument("id")
    s.add_argument("slot")
    s.add_argument("--recognised", choices=["right", "wrong"], required=True)
    s.add_argument("--picked")
    s.add_argument("--solved", choices=["right", "wrong"], required=True)
    s.add_argument("--miss", choices=MISS_KINDS)
    s.add_argument("--hint", type=int, choices=range(6), help="the highest hint level given, 0-5")
    s.add_argument("--confidence", type=confidence_arg)
    s = sub.add_parser("drill-retests")
    s.add_argument("id")
    s = sub.add_parser("drill-retest")
    s.add_argument("id")
    s.add_argument("slot")
    s.add_argument("result", choices=["right", "wrong"])
    s.add_argument("--miss", choices=MISS_KINDS)
    s = sub.add_parser("drill-summary")
    s.add_argument("id")
    a = p.parse_args(argv)
    {"scan": cmd_scan, "due": cmd_due, "result": cmd_result, "stats": cmd_stats, "drill": cmd_drill,
     "drill-check": cmd_drill_check, "drill-result": cmd_drill_result, "drill-retests": cmd_drill_retests,
     "drill-retest": cmd_drill_retest, "drill-summary": cmd_drill_summary}[a.cmd](a)


if __name__ == "__main__":
    main()
