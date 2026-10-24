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
import subprocess
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


def tmux(*args):
    """A tmux command for this session's status bar; nothing outside tmux."""
    if not os.environ.get("TMUX"):
        return
    try:
        subprocess.run(["tmux", *args], check=False, capture_output=True, timeout=5)
    except Exception:
        pass


def clear_status_bar():
    tmux("set-option", "-u", "status-right")
    tmux("set-option", "-u", "status-interval")


# ---------------------------------------------------------------- the clock

def mmss(seconds):
    m, s = divmod(int(max(0, seconds)), 60)
    return f"{m}:{s:02d}"


def main_correct_at(pr):
    """The time of the first correct main answer, or None."""
    return next((a["t"] for a in pr["answers"] if a["verdict"] == "correct" and not a["followup"]), None)


def hints_before(pr, t):
    return sum(1 for h in pr["hints"] if t is None or h["t"] <= t)


def followup_result(pr):
    fus = [a for a in pr["answers"] if a["followup"]]
    if any(a["verdict"] == "correct" for a in fus):
        return "solved"
    return "unsolved" if fus else "not asked"


def round_seconds(st):
    return len(st["problems"]) * PER_PROBLEM


def flag(st, t):
    pr = st["problems"][st["current"]]
    used = t - pr["start"]
    if t - st["started"] >= round_seconds(st):
        return "ROUND TIME UP"
    if used >= PER_PROBLEM:
        return "TIME UP"
    if used >= 0.75 * PER_PROBLEM:
        return "TIME NEARLY UP"
    if used >= 0.5 * PER_PROBLEM and not pr["hints"]:
        return "NUDGE IF STUCK"
    if main_correct_at(pr) is not None and followup_result(pr) != "solved":
        return "FOLLOW-UP"
    return ""


def hook_line(st, t):
    pr = st["problems"][st["current"]]
    line = (f"INTERVIEW: problem {st['current'] + 1} of {len(st['problems'])} · {mmss(t - pr['start'])} of "
            f"{mmss(PER_PROBLEM)} · hints {len(pr['hints'])} · round {mmss(t - st['started'])} of {mmss(round_seconds(st))}")
    f = flag(st, t)
    return line + (f" · {f}" if f else "")


def clock_line(st, t):
    pr = st["problems"][st["current"]]
    used = t - pr["start"]
    head = f"P{st['current'] + 1}/{len(st['problems'])}"
    return f"{head} TIME UP" if used >= PER_PROBLEM else f"{head} {mmss(used)}/{mmss(PER_PROBLEM)}"


def running(quiet=False):
    """(course, n, state, problems) of the running round; with quiet, None instead of an error."""
    try:
        c = book.find_course(None)
    except SystemExit:
        if quiet:
            return None
        raise
    op = open_round(c)
    if not op or op[1].get("status") != "running":
        if quiet:
            return None
        book.die("no round is running", 1)
    n, st = op
    return c, n, st, load_problems(c, n)


# ---------------------------------------------------------------- the round

def write_frontmatter(path, fields):
    """Set these frontmatter fields, keeping the rest of the note."""
    text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    lines = m.group(1).split("\n") if m else []
    body = text[m.end():] if m else text
    for k, v in fields.items():
        lines = [ln for ln in lines if not ln.startswith(f"{k}:")] + [f"{k}: {v}"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("---\n" + "\n".join(lines) + "\n---\n" + body)


def cmd_start(a):
    c = book.find_course(None)
    n, st = current_round(c, ("ready",))
    probs = load_problems(c, n)
    t = time.time()
    st["problems"] = [{"id": pr["id"], "start": None, "end": None, "hints": [], "answers": [], "outcome": None,
                       "followup": "not asked"} for pr in probs]
    st["problems"][0]["start"] = t
    st.update({"status": "running", "session": a.session, "started": t, "current": 0})
    save(c, n, st)
    write_frontmatter(paths(c, n)["note"], {"interview": c.slug, "number": n, "date": time.strftime("%Y-%m-%d"),
                                            "length": st["length"], "status": "running"})
    tmux("set-option", "status-right", f'#(python3 "{os.path.abspath(__file__)}" clock)')
    tmux("set-option", "status-interval", "1")
    print(f"NOTE: {book.rel(paths(c, n)['note'])}")
    print(f"PROBLEM 1: {probs[0]['statement']}")


def cmd_hook(a):
    try:
        data = json.loads(sys.stdin.read() or "{}")
        r = running(quiet=True)
        if not r or not isinstance(data, dict):
            return
        c, n, st, _ = r
        if data.get("session_id") and data.get("session_id") == st.get("session"):
            print(hook_line(st, time.time()))
    except Exception:
        pass  # a hook never gets in the learner's way


def cmd_clock(a):
    try:
        r = running(quiet=True)
        if r:
            print(clock_line(r[2], time.time()))
    except Exception:
        pass


def cmd_hint(a):
    c, n, st, probs = running()
    pr = st["problems"][st["current"]]
    pr["hints"].append({"t": time.time(), "kind": "error" if a.error else "nudge"})
    save(c, n, st)
    k = len(pr["hints"])
    if a.error:
        print(f"ERROR POINTED OUT, recorded as hint {k}.")
        return
    used = sum(1 for h in pr["hints"] if h["kind"] == "nudge")
    prepared = probs[st["current"]]["hints"]
    if used <= len(prepared):
        print(f"HINT {k} recorded. Next prepared nudge: {prepared[used - 1]}")
    else:
        print(f"HINT {k} recorded. No prepared nudges left: give the method, or close the problem.")


def cmd_answer(a):
    c, n, st, probs = running()
    pr, spec = st["problems"][st["current"]], probs[st["current"]]
    t = time.time()
    if a.followup:
        if main_correct_at(pr) is None:
            book.die("the follow-up is not open: the main answer is not correct yet", 1)
        if followup_result(pr) == "solved":
            book.die("the follow-up is already answered correctly: close the problem with next", 1)
        spec = spec["followup"]
    elif main_correct_at(pr) is not None:
        book.die("the main answer is already answered correctly; the follow-up takes --followup", 1)
    try:
        verdict = answer_check.check(a.text, str(spec["answer"]), spec.get("variables") or {})
    except answer_check.AnswerError as exc:
        print(f"UNREADABLE: {exc}")
        return
    pr["answers"].append({"t": t, "text": a.text, "verdict": verdict, "followup": bool(a.followup)})
    save(c, n, st)
    print("CORRECT" if verdict == "correct" else "WRONG")
    if verdict == "correct" and not a.followup:
        left = PER_PROBLEM - (t - pr["start"])
        print(f"FOLLOW-UP: {spec['followup']['statement']}" if left >= 120
              else "NO TIME FOR THE FOLLOW-UP: close the problem with next")


def close_problem(st, probs, t, gave_up=False):
    """Close the current problem; return its CLOSED and SOLUTION lines."""
    i = st["current"]
    pr = st["problems"][i]
    at = main_correct_at(pr)
    hints = hints_before(pr, at)
    pr["outcome"] = "unsolved" if at is None else ("solved" if hints == 0 else "hinted")
    pr["followup"] = followup_result(pr)
    pr["end"] = t
    pr["gaveUp"] = bool(gave_up)
    shown = len(pr["hints"]) if at is None else hints
    return [f"CLOSED: Problem {i + 1} — {pr['outcome']} ({mmss(t - pr['start'])}, {shown} hint{'' if shown == 1 else 's'})",
            f"SOLUTION: {probs[i]['solution']}"]


def end_round(c, n, st):
    for pr in st["problems"]:
        if pr["outcome"] is None:
            pr["outcome"] = "not reached"
            pr["followup"] = "not asked"
    st["status"] = "ended"
    save(c, n, st)
    print(f"ROUND OVER: write the marks to {book.rel(paths(c, n)['marks'])}, then run finish")


def cmd_next(a):
    c, n, st, probs = running()
    t = time.time()
    print("\n".join(close_problem(st, probs, t, a.gave_up)))
    if st["current"] + 1 >= len(st["problems"]) or t - st["started"] >= round_seconds(st):
        end_round(c, n, st)
        return
    st["current"] += 1
    st["problems"][st["current"]]["start"] = t
    save(c, n, st)
    print(f"PROBLEM {st['current'] + 1}: {probs[st['current']]['statement']}")


def cmd_stop(a):
    c, n, st, probs = running()
    print("\n".join(close_problem(st, probs, time.time())))
    end_round(c, n, st)


def cmd_abandon(a):
    c = book.find_course(None)
    n, st = current_round(c, OPEN)
    st["status"] = "abandoned"
    save(c, n, st)
    clear_status_bar()
    print(f"🗒 interview abandoned: {book.rel(paths(c, n)['note'])}")


# ---------------------------------------------------------------- the scorecard

def marks_errors(st, marks):
    if not isinstance(marks, dict) or not isinstance(marks.get("problems"), dict):
        return ["marks: the file must have a \"problems\" object"]
    given = {pr["id"] for pr in st["problems"] if pr["outcome"] != "not reached"}
    errors = [f"marks: no feedback for {pid}" for pid in sorted(given) if not str(marks["problems"].get(pid) or "").strip()]
    errors += [f"marks: {pid} was not reached" for pid in sorted(marks["problems"]) if pid not in given]
    return errors


def scorecard(st, probs, marks):
    import exam  # for section_label; imports lesson and book, already loaded
    rows = ["### Scorecard", "", "| | Outcome | Time | Hints | Follow-up | Technique |", "|---|---|---|---|---|---|"]
    for i, (pr, spec) in enumerate(zip(st["problems"], probs), 1):
        if pr["outcome"] == "not reached":
            rows.append(f"| Problem {i} | not reached | — | — | — | {spec['technique']} |")
            continue
        hints = hints_before(pr, main_correct_at(pr)) if main_correct_at(pr) is not None else len(pr["hints"])
        rows.append(f"| Problem {i} | {pr['outcome']} | {mmss(pr['end'] - pr['start'])} | {hints} | "
                    f"{pr['followup']} | {spec['technique']} |")
    out = ["\n".join(rows)]
    for i, pr in enumerate(st["problems"], 1):
        if pr["id"] in marks["problems"]:
            out.append(f"**Problem {i}:** {marks['problems'][pr['id']]}")
    comm = marks.get("communication") or {}
    if comm:
        out.append("**How you explained:** " + "; ".join(f"{k} — {v}" for k, v in comm.items()))
    if marks.get("work_on"):
        out.append("**Work on:** " + " ".join(marks["work_on"]))
    if marks.get("revisit"):
        out.append("**Revisit:** " + "; ".join(f"[[{target}|{exam.section_label(target)}]] — {why}"
                                               for target, why in marks["revisit"].items()))
    for i, (pr, spec) in enumerate(zip(st["problems"], probs), 1):
        if pr["outcome"] == "not reached":
            continue
        fu = spec["followup"]
        body = [spec["statement"], "", spec["solution"], "", f"**Follow-up:** {fu['statement']}", "",
                fu.get("solution") or ""]
        quoted = "\n".join(("> " + ln) if ln else ">" for ln in "\n".join(body).strip().split("\n"))
        out.append(f"> [!example]- Problem {i} — solution\n{quoted}")
    return "\n\n".join(out) + "\n"


def cmd_finish(a):
    c = book.find_course(None)
    n, st = current_round(c, ("ended",))
    marks = book.load_json(a.marks, None)
    errors = marks_errors(st, marks)
    if errors:
        book.die("\n".join(errors), 1)
    note = paths(c, n)["note"]
    text = open(note, encoding="utf-8").read() if os.path.exists(note) else ""
    with open(note, "w", encoding="utf-8") as f:
        f.write(text.rstrip("\n") + "\n\n" + scorecard(st, load_problems(c, n), marks))
    solved = sum(pr["outcome"] == "solved" for pr in st["problems"])  # unaided; hinted solves are in the table
    write_frontmatter(note, {"status": "finished", "solved": f"{solved}/{len(st['problems'])}"})
    st.update({"status": "finished", "solved": solved})
    save(c, n, st)
    clear_status_bar()
    print(f"🗒 interview finished: {solved}/{len(st['problems'])} solved")


def cmd_list(a):
    c = book.find_course(None)
    for n, st in rounds(c):
        line = f"{c.slug}-interview-{n}  {st.get('set', '')}  {st.get('length', '')}  {st.get('status', '')}"
        if st.get("status") == "finished":
            line += f"  {st.get('solved', 0)}/{len(st.get('problems', []))} solved"
        print(line)


def interview_misses(note):
    """Lines for the resume brief: the problems not solved unaided in the newest finished round of the note's
    course, on units of this note or the chapter before it."""
    import figures
    cdir = figures.course_of(note)
    if not cdir:
        return []
    c = book.Course(cdir)
    done = [(n, st) for n, st in rounds(c) if st.get("status") == "finished"]
    if not done:
        return []
    n, st = done[-1]
    probs = load_problems(c, n) or []
    sources = {os.path.abspath(s) for s in lesson.review_sources(note)}
    out = []
    for i, (pr, spec) in enumerate(zip(st["problems"], probs), 1):
        unit = c.by_id.get((spec.get("units") or [""])[0])
        if pr["outcome"] not in ("hinted", "unsolved") or not unit:
            continue
        if os.path.abspath(c.note(unit["chapter"])) not in sources:
            continue
        text = re.sub(r"\s+", " ", spec["statement"])
        out.append(f"  - Problem {i} {pr['outcome']} §{unit['id']} — {spec['technique']}: "
                   f"{text[:90]}{'…' if len(text) > 90 else ''}")
    return [f"INTERVIEW MISSES ({c.slug}-interview-{n}): re-probe these first"] + out if out else []


def main(argv=None):
    p = argparse.ArgumentParser(prog="interview.py", description="Mock interviews on the current course.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("new")
    s.add_argument("--length", choices=sorted(LENGTHS), required=True)
    sub.add_parser("check")
    s = sub.add_parser("start")
    s.add_argument("--session", required=True)
    sub.add_parser("hook")
    sub.add_parser("clock")
    s = sub.add_parser("hint")
    s.add_argument("--error", action="store_true")
    s = sub.add_parser("answer")
    s.add_argument("text")
    s.add_argument("--followup", action="store_true")
    s = sub.add_parser("next")
    s.add_argument("--gave-up", action="store_true")
    sub.add_parser("stop")
    s = sub.add_parser("finish")
    s.add_argument("--marks", required=True)
    sub.add_parser("abandon")
    sub.add_parser("list")
    a = p.parse_args(argv)
    {"new": cmd_new, "check": cmd_check, "start": cmd_start, "hook": cmd_hook, "clock": cmd_clock, "hint": cmd_hint,
     "answer": cmd_answer, "next": cmd_next, "stop": cmd_stop, "finish": cmd_finish, "abandon": cmd_abandon,
     "list": cmd_list}[a.cmd](a)


if __name__ == "__main__":
    main()
