#!/usr/bin/env python3
"""
interview — a mock interview: a timed round of new problems on the course's finished units.

The model writes the problems (JSON, in the course's hidden `.interviews/` folder) and plays the interviewer; this
script does what must be exact: paths, validation, the clock, hints, answers (through mcp/answer_check.py),
outcomes, the scorecard and the misses that recall checks re-probe.

    interview.py new --length short|standard|long   plan a round: paths, budget, studied units, past techniques
    interview.py check                               validate the problem file; the round becomes ready
    interview.py start --session <id>                start the clock and the status bar; print problem 1
    interview.py hook                                (UserPromptSubmit) the clock line, during a running round
    interview.py hint [--error]                      record a nudge (or a pointed-out error); print the next nudge
    interview.py answer "<text>" [--followup]        check a final answer: CORRECT, WRONG or UNREADABLE
    interview.py next [--gave-up]                    close the current problem; print the next one, or ROUND OVER
    interview.py stop                                end the round early
    interview.py finish --marks <file>               write the scorecard into the note; restore the status bar
    interview.py clock                               one short line for the tmux status bar
    interview.py abandon                             drop a round that was set or started
    interview.py list                                every round of the course, with its result
"""
import argparse
import glob
import json
import os
import re
import sys
import time

import book
import lesson

CLAUDE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(CLAUDE_DIR, "mcp"))
import answer_check  # noqa: E402  (final answers: the typed-answer checker)

LENGTHS = {"short": 2, "standard": 3, "long": 4}
PER_PROBLEM = 720  # seconds
OPEN = ("set", "ready", "running", "ended")
KEY_IDEA_RE = re.compile(r"^> \[!summary\][-+]? Key idea", re.I)


# ---------------------------------------------------------------- paths and state

def paths(c, n):
    name = f"{c.slug}-interview-{n}"
    hidden = os.path.join(c.dir, ".interviews")
    return {"note": os.path.join(c.dir, "interviews", name + ".md"), "problems": os.path.join(hidden, name + ".json"),
            "state": os.path.join(hidden, name + ".state.json"), "marks": os.path.join(hidden, name + ".marks.json")}


def rounds(c):
    """[(n, state)] of every round of the course, oldest first."""
    out = []
    for sp in glob.glob(os.path.join(glob.escape(c.dir), ".interviews", f"{glob.escape(c.slug)}-interview-*.state.json")):
        m = re.search(r"-interview-(\d+)\.state\.json$", sp)
        st = book.load_json(sp, None)
        if m and isinstance(st, dict):
            out.append((int(m.group(1)), st))
    return sorted(out, key=lambda x: x[0])


def open_round(c):
    return next(((n, st) for n, st in reversed(rounds(c)) if st.get("status") in OPEN), None)


def load(c, n):
    return book.load_json(paths(c, n)["state"], {})


def save(c, n, state):
    book.save_json(paths(c, n)["state"], state)


def load_problems(c, n):
    data = book.load_json(paths(c, n)["problems"], None)
    return (data or {}).get("problems") if isinstance(data, dict) else None


def finished_units(c):
    return [u for u in c.syllabus() if c.status(u["id"]) in ("done", "shaky")]


# ---------------------------------------------------------------- the notes

def key_ideas(note_path, unit_id):
    """The text of each Key idea callout under the note's ### headings for this unit (its subsections too)."""
    if not os.path.exists(note_path):
        return []
    out, inside, cur = [], False, None
    for ln in lesson.read(note_path):
        if ln.startswith("### "):
            num = re.match(r"### +([A-Z]?\d+(?:\.\d+)*)\s", ln)
            inside = bool(num) and (num.group(1) == unit_id or num.group(1).startswith(unit_id + "."))
            cur = None
            continue
        if not inside:
            continue
        if KEY_IDEA_RE.match(ln):
            cur = []
            out.append(cur)
        elif cur is not None and ln.startswith(">"):
            cur.append(ln.lstrip(">").strip())
        else:
            cur = None
    return [" ".join(x for x in parts if x) for parts in out if any(parts)]


def unit_link(c, u):
    want = f"|§{u['id']}]]"
    return next((ln for ln in lesson.heading_links(c.note(u["chapter"])) if ln.endswith(want)), f"§{u['id']}")


# ---------------------------------------------------------------- commands

def cmd_new(a):
    c = book.find_course(None)
    op = open_round(c)
    if op:
        n, st = op
        print(f"OPEN: {book.rel(paths(c, n)['note'])} ({st.get('status')})")
        book.die("a round is open: finish it, or drop it with: interview.py abandon", 1)
    units = finished_units(c)
    if not units:
        book.die("no finished unit yet: a round tests what the course has covered", 1)
    n = max([k for k, _ in rounds(c)], default=0) + 1
    p = paths(c, n)
    k = LENGTHS[a.length]
    print(f"NOTE: {book.rel(p['note'])}")
    print(f"PROBLEMS: {book.rel(p['problems'])}")
    print(f"BUDGET: {k} problems × {PER_PROBLEM // 60} minutes (round {k * PER_PROBLEM // 60} minutes)")
    print("UNITS (write the problems from these; a problem's `units` are ids from this list):")
    for u in units:
        print(f"  {u['id']} {u['title']} — {unit_link(c, u)}")
        for idea in key_ideas(c.note(u["chapter"]), u["id"]):
            print(f"    key idea: {idea}")
    past = [pr.get("technique", "") for m, _ in rounds(c) for pr in (load_problems(c, m) or []) if pr.get("technique")]
    print("PAST TECHNIQUES:")
    print("\n".join(f"  {t}" for t in past) if past else "  (none)")
    save(c, n, {"status": "set", "length": a.length, "number": n, "set": time.strftime("%Y-%m-%d")})


def _check_answer(where, spec):
    variables = spec.get("variables") or {}
    if not isinstance(variables, dict):
        return [f"{where}: variables must be an object from name to range"]
    try:
        answer_check.parse_ranges(variables)
        answer_check.read(str(spec.get("answer") or ""), variables)
        need = min(3, len(answer_check.points(str(spec["answer"]), variables)))
        if answer_check.defined_points(str(spec["answer"]), variables) < need:
            return [f"{where}: answer is undefined at most points of the ranges"]
    except answer_check.AnswerError as exc:
        return [f"{where}: answer: {exc}"]
    return []


def problem_errors(c, length, probs):
    if not isinstance(probs, list):
        return ["the problem file must be {\"problems\": [...]}"]
    k = LENGTHS[length]
    errors = [] if len(probs) == k else [f"{length} needs {k} problems, found {len(probs)}"]
    finished = {u["id"] for u in finished_units(c)}
    for i, pr in enumerate(probs, 1):
        if not isinstance(pr, dict):
            errors.append(f"problem {i}: not an object")
            continue
        if pr.get("id") != f"p{i}":
            errors.append(f"problem {i}: id must be p{i}")
        pid = f"p{i}"
        for field in ("statement", "solution", "technique"):
            if not str(pr.get(field) or "").strip():
                errors.append(f"{pid}: {field} is empty")
        errors += _check_answer(pid, pr)
        units = pr.get("units") or []
        if not units:
            errors.append(f"{pid}: units is empty")
        errors += [f"{pid}: unit {u} is not finished" for u in units if u not in finished]
        hints = pr.get("hints")
        if not isinstance(hints, list) or len(hints) != 3 or not all(str(h).strip() for h in hints):
            errors.append(f"{pid}: needs exactly 3 hints")
        fu = pr.get("followup")
        if not isinstance(fu, dict) or not str(fu.get("statement") or "").strip():
            errors.append(f"{pid}: the follow-up needs a statement")
        else:
            errors += _check_answer(f"{pid} follow-up", fu)
    return errors


def current_round(c, statuses):
    op = open_round(c)
    if not op or op[1].get("status") not in statuses:
        book.die(f"no round that is {' or '.join(statuses)}: start one with: interview.py new --length …", 1)
    return op


def cmd_check(a):
    c = book.find_course(None)
    n, st = current_round(c, ("set", "ready"))
    probs = load_problems(c, n)
    if probs is None:
        book.die(f"no problem file at {book.rel(paths(c, n)['problems'])}", 1)
    errors = problem_errors(c, st["length"], probs)
    if errors:
        print("\n".join(errors))
        sys.exit(1)
    st["status"] = "ready"
    save(c, n, st)
    print(f"🗒 interview ready: {len(probs)} problems")


def cmd_abandon(a):
    c = book.find_course(None)
    n, st = current_round(c, OPEN)
    st["status"] = "abandoned"
    save(c, n, st)
    print(f"🗒 interview abandoned: {book.rel(paths(c, n)['note'])}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="interview.py", description="Mock interviews on the current course.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("new")
    s.add_argument("--length", choices=sorted(LENGTHS), required=True)
    sub.add_parser("check")
    sub.add_parser("abandon")
    a = p.parse_args(argv)
    {"new": cmd_new, "check": cmd_check, "abandon": cmd_abandon}[a.cmd](a)


if __name__ == "__main__":
    main()
