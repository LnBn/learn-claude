#!/usr/bin/env python3
"""
interview — a mock interview: a timed round of new problems on the finished units of one course or several.

The model writes the problems (JSON, in a hidden `.interviews/` folder) and plays the interviewer; this script does
what must be exact: paths, validation, the topic mix, the clock, hints, answers (through mcp/answer_check.py),
outcomes, the scores of written tests, the scorecard and the misses that recall checks re-probe.

A round on one course lives in that course's folder (`<slug>-interview-<n>`); a round on several lives at the vault
root (`mixed-interview-<n>`). A firm profile (`--profile`) sets the number of problems, the time, the topic mix and
the interviewer's style; `sig-oa` and `mw-oa` are written tests, sat in Obsidian and scored on `submit`.

    interview.py new (--length short|standard|long | --profile <name>) [--courses gb,bh] [--minutes N]
                                                     plan a round: paths, budget, mix, units, past techniques
    interview.py topic <course> <topic> <chapter | unit | *>...
                                                     tag units with a topic (for profile rounds)
    interview.py check                               validate the problem file; the round becomes ready
    interview.py start --session <id>                start the clock and the status bar; print problem 1 (or
                                                     write the paper of a written test)
    interview.py hook                                (UserPromptSubmit) the clock line, during a running round
    interview.py hint [--error] [--level N]          record a nudge (or a pointed-out error) and its level, 0-5;
                                                     print the next nudge
    interview.py answer "<text>" [--followup]        check a final answer: CORRECT, WRONG or UNREADABLE
    interview.py next [--gave-up]                    close the current problem; print the next one, or ROUND OVER
    interview.py submit                              hand in a written test: read the paper, score it
    interview.py stop                                end the round early (a written test: submit it)
    interview.py finish --marks <file>               write the scorecard into the note; restore the status bar
    interview.py clock                               one short line for the tmux status bar
    interview.py abandon                             drop a round that was set or started
    interview.py list                                every round, in every course and the vault, with its result
"""
import argparse
import glob
import json
import os
import random
import re
import subprocess
import sys
import time

import book
import lesson
import programme
import technique

CLAUDE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAULT = os.path.dirname(CLAUDE_DIR)
sys.path.insert(0, os.path.join(CLAUDE_DIR, "mcp"))
import answer_check  # noqa: E402  (final answers: the typed-answer checker)

LENGTHS = {"short": 2, "standard": 3, "long": 4}
PER_PROBLEM = 720  # seconds, in a round without a profile
OPEN = ("set", "ready", "running", "ended")
KEY_IDEA_RE = re.compile(r"^> \[!summary\][-+]? Key idea", re.I)
# the round that is open, whatever course is current: a course switched mid-round must not lose it
ROUND_POINTER = os.path.join(CLAUDE_DIR, "md-log-state", "interview.json")
MIXED = "mixed"  # the name of a round on several courses: mixed-interview-<n>, at the vault root
TOPICS = ("probability", "statistics", "regression", "linear algebra", "calculus", "brainteasers", "other")

# The evidence behind these is weak (prep sites, Glassdoor): change them here. Weights are relative integers.
PROFILES = {
    "sig": {"title": "SIG quant research, live round", "mode": "live", "problems": 3, "minutes": 20,
            "mix": {"probability": 85, "statistics": 10, "regression": 5},
            "style": [
                "Probability and expected-value puzzles, worked aloud: conditional probability and Bayes, counting, "
                "dice and coin games with optimal stopping (a die you may reroll for $1), order statistics of "
                "uniforms, conditioning on a sum of normals, waiting for a pattern of coin flips.",
                "A statistics or regression problem asks for a number: an estimate, a variance, a slope.",
                "After a correct answer, ask how they would sanity-check it (a limit, a small case, a symmetry), "
                "then give the follow-up. The follow-up generalises: n instead of 6, a general p, one more round "
                "of the game.",
            ]},
    "mw": {"title": "Marshall Wace on-site", "mode": "live", "problems": 3, "minutes": 20,
           "mix": {"brainteasers": 2, "regression": 1},
           "style": [
               "The brainteasers first, then the regression problem.",
               "The regression problem asks for a number or a formula: a slope, a variance, an R². After the "
               "answer, ask which assumptions it rests on and what would break them in real data. That talk is "
               "not graded.",
               "Push for structure: what is given, what is asked, the plan, then the computation.",
           ]},
    "sig-oa": {"title": "SIG online test", "mode": "written", "problems": 17, "minutes": 60,
               "mix": {"probability": 6, "statistics": 4}, "marking": {"right": 1, "wrong": 0, "blank": 0},
               "calculator": True,
               "style": ["Short questions with one exact answer, a few minutes each: probability, expectation, "
                         "variance, distributions, estimators. A calculator is allowed, so a decimal answer is "
                         "fine."]},
    "mw-oa": {"title": "Marshall Wace written test", "mode": "written", "problems": 18, "minutes": 60,
              "mix": {"probability": 7, "statistics": 3, "regression": 3, "linear algebra": 3, "calculus": 2},
              "marking": {"right": 2, "wrong": -1, "blank": 0}, "calculator": False,
              "style": ["Short closed-form questions: probability and counting (grid paths around a blocked "
                        "square, the chance of more heads than a rival), statistics, OLS (the slope formula, its "
                        "assumptions), linear algebra (trace, eigenvalues, the exponential of a diagonal "
                        "matrix), calculus. No calculator: answers are exact."]},
}


# ---------------------------------------------------------------- where rounds live

class Home:
    """Where rounds are kept: a course's folder (rounds on that course) or the vault's (rounds on several)."""

    def __init__(self, d, slug):
        self.dir, self.slug = d, slug


def course_home(c):
    return Home(c.dir, c.slug)


def vault_home():
    return Home(VAULT, MIXED)


def all_courses():
    return [book.Course(d) for d in book.course_dirs()[0]]


def homes():
    return [course_home(c) for c in all_courses()] + [vault_home()]


def paths(h, n):
    name = f"{h.slug}-interview-{n}"
    hidden = os.path.join(h.dir, ".interviews")
    return {"note": os.path.join(h.dir, "interviews", name + ".md"), "problems": os.path.join(hidden, name + ".json"),
            "state": os.path.join(hidden, name + ".state.json"), "marks": os.path.join(hidden, name + ".marks.json")}


def rounds(h):
    """[(n, state)] of every round kept in this home, oldest first."""
    out = []
    for sp in glob.glob(os.path.join(glob.escape(h.dir), ".interviews", f"{glob.escape(h.slug)}-interview-*.state.json")):
        m = re.search(r"-interview-(\d+)\.state\.json$", sp)
        st = book.load_json(sp, None)
        if m and isinstance(st, dict):
            out.append((int(m.group(1)), st))
    return sorted(out, key=lambda x: x[0])


def open_round(h):
    return next(((n, st) for n, st in reversed(rounds(h)) if st.get("status") in OPEN), None)


def open_anywhere():
    """(home, n, state) of an open round in any course or the vault, or None."""
    for h in homes():
        op = open_round(h)
        if op:
            return (h, *op)
    return None


def pointed_home():
    """The home of the round the pointer names, while that round is open; None otherwise. Reads only."""
    ptr = book.load_json(ROUND_POINTER, None)
    d = (ptr.get("home") or ptr.get("course")) if isinstance(ptr, dict) else None  # "course": an older pointer
    if not d:
        return None
    if os.path.exists(os.path.join(str(d), ".course", "book.json")):
        h = course_home(book.Course(d))
    elif os.path.abspath(str(d)) == os.path.abspath(VAULT):
        h = vault_home()
    else:
        return None
    return h if open_round(h) else None


def the_round(statuses):
    """(home, n, state) of the open round, whatever course is current; dies unless it is in one of these statuses."""
    h = pointed_home()
    op = (h, *open_round(h)) if h else open_anywhere()
    if not op or op[2].get("status") not in statuses:
        book.die(f"no round that is {' or '.join(statuses)}: start one with: interview.py new …", 1)
    return op


def point_at(h, n):
    book.save_json(ROUND_POINTER, {"home": h.dir, "number": n})


def clear_pointer():
    try:
        os.remove(ROUND_POINTER)
    except OSError:
        pass


def load(h, n):
    return book.load_json(paths(h, n)["state"], {})


def save(h, n, state):
    book.save_json(paths(h, n)["state"], state)


def load_problems(h, n):
    data = book.load_json(paths(h, n)["problems"], None)
    return (data or {}).get("problems") if isinstance(data, dict) else None


# ---------------------------------------------------------------- courses, units and topics

def finished_units(c):
    return [u for u in c.syllabus() if c.status(u["id"]) in ("done", "shaky")]


def round_courses(h, st):
    """The courses a round draws on; an older round's is its home course. A course since removed is left out."""
    dirs = st.get("courses") or [h.dir]
    return [book.Course(d) for d in dirs if os.path.exists(os.path.join(d, ".course", "book.json"))]


def unit_ref(c, u, multi):
    """How a problem names a unit: `2.4` in a round on one course, `bh:2.4` in a round on several."""
    return f"{c.slug}:{u['id']}" if multi else u["id"]


def resolve_unit(courses, ref):
    """(course, unit) that a unit ref names, or (None, None)."""
    if len(courses) > 1:
        slug, _, uid = str(ref).partition(":")
        c = next((x for x in courses if x.slug == slug), None)
    else:
        c, uid = (courses[0] if courses else None), str(ref)
    u = c.by_id.get(uid) if c else None
    return (c, u) if u else (None, None)


def topic_of(c, u):
    """The unit's topic: its own tag, else its chapter's, else the course's `*`; None when untagged."""
    tags = c.state.get("topics") or {}
    return tags.get(u["id"]) or tags.get(u.get("chapter") or "") or tags.get("*")


def allocate(mix, available, n, seed):
    """{topic: problems}: the weights of the available topics, n·w/W each rounded down; the slots left over go to
    topics drawn by their remainders (without replacement), with a generator seeded by `seed`."""
    w = {t: x for t, x in mix.items() if t in available and x > 0}
    total = sum(w.values())
    if not total:
        return {}
    out = {t: n * x // total for t, x in w.items()}
    rem = {t: n * x % total for t, x in w.items()}
    rng = random.Random(seed)
    for _ in range(n - sum(out.values())):
        cands = [t for t in rem if rem[t] > 0]
        t = rng.choices(cands, weights=[rem[x] for x in cands])[0]
        out[t] += 1
        rem[t] = 0
    return {t: k for t, k in out.items() if k}


def mix_text(mix):
    return ", ".join(f"{t} {k}" for t, k in mix.items())


def scope(arg):
    """The courses a new round draws on: those named (`gb,bh`), or every course with a finished unit."""
    courses = all_courses()
    if not courses:
        book.die("no course yet — create one with: book.py new <book.pdf>", 1)
    if not arg:
        members = {os.path.realpath(d) for d in programme.member_dirs()}  # a current programme scopes the round
        pool = [c for c in courses if os.path.realpath(c.dir) in members] if members else courses
        chosen = [c for c in pool if finished_units(c)]
        if not chosen:
            book.die("no finished unit yet: a round tests what the courses have covered", 1)
        return chosen
    by = {**{os.path.basename(c.dir): c for c in courses}, **{c.slug: c for c in courses}}
    want = list(dict.fromkeys(s.strip() for s in arg.split(",") if s.strip()))
    missing = [s for s in want if s not in by]
    if missing or not want:
        book.die(f"no course named {', '.join(missing) or '(none)'}; the courses are: "
                 f"{', '.join(c.slug for c in courses)}", 1)
    chosen = list({by[s].dir: by[s] for s in want}.values())
    empty = [c.slug for c in chosen if not finished_units(c)]
    if empty:
        book.die(f"no finished unit in {', '.join(empty)}: a round tests what a course has covered", 1)
    return chosen


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


# ---------------------------------------------------------------- planning a round

def print_unit(c, u, ref, indent):
    print(f"{indent}{ref} {u['title']} — {unit_link(c, u)}")
    for idea in key_ideas(c.note(u["chapter"]), u["id"]):
        print(f"{indent}  key idea: {idea}")


def untagged_lines(units):
    """`  gb 2 Brain Teasers: 2.1, 2.2` for each chapter with a finished unit that has no topic."""
    groups = {}
    for c, u in units:
        if topic_of(c, u) not in TOPICS:
            groups.setdefault((c.slug, u["chapter"]), (c, []))[1].append(u["id"])
    return [f"  {slug} {ch} {(c.by_id.get(ch) or {}).get('title', '')}: {', '.join(ids)}"
            for (slug, ch), (c, ids) in groups.items()]


def cmd_new(a):
    prof = PROFILES.get(a.profile) if a.profile else None
    if prof and a.length:
        book.die("a profile sets the number of problems: drop --length", 1)
    if not prof and not a.length:
        book.die("give --length short|standard|long, or --profile " + "|".join(PROFILES), 1)
    if a.minutes is not None and (not prof or prof["mode"] != "written"):
        book.die("--minutes is for a written test: " + ", ".join(k for k, p in PROFILES.items() if p["mode"] == "written"), 1)
    if a.minutes is not None and a.minutes <= 0:
        book.die("--minutes must be positive", 1)
    h = pointed_home()
    op = (h, *open_round(h)) if h else open_anywhere()
    if op:
        h, n, st = op
        print(f"OPEN: {book.rel(paths(h, n)['note'])} ({st.get('status')})")
        book.die("a round is open: finish it, or drop it with: interview.py abandon", 1)
    courses = scope(a.courses)
    multi = len(courses) > 1
    h = vault_home() if multi else course_home(courses[0])
    units = [(c, u) for c in courses for u in finished_units(c)]
    n = max([k for k, _ in rounds(h)], default=0) + 1
    p = paths(h, n)
    state = {"status": "set", "number": n, "set": time.strftime("%Y-%m-%d"), "courses": [c.dir for c in courses]}
    mix = None
    if prof:
        lines = untagged_lines(units)
        if lines:
            print("UNTAGGED (a profile round needs the topic of every finished unit):")
            print("\n".join(lines))
            book.die("tag them, then run new again: interview.py topic <course> <topic> <chapter | unit | *>…  "
                     f"(topics: {', '.join(TOPICS)})", 1)
        mix = allocate(prof["mix"], {topic_of(c, u) for c, u in units}, prof["problems"], f"{h.slug}-interview-{n}")
        if not mix:
            book.die(f"no finished unit has one of the profile's topics ({', '.join(prof['mix'])})", 1)
        units = [(c, u) for c, u in units if topic_of(c, u) in mix]
        state.update(profile=a.profile, mode=prof["mode"], mix=mix,
                     unit_topics={unit_ref(c, u, multi): topic_of(c, u) for c, u in units})
        if prof["mode"] == "written":
            state.update(minutes=a.minutes or prof["minutes"], marking=prof["marking"])
        else:
            state["per_problem"] = prof["minutes"] * 60
    else:
        state.update(length=a.length, mode="live", per_problem=PER_PROBLEM)
    state["units"] = [unit_ref(c, u, multi) for c, u in units]

    k = expected_count(state)
    print(f"NOTE: {book.rel(p['note'])}")
    print(f"PROBLEMS: {book.rel(p['problems'])}")
    if prof:
        print(f"PROFILE: {a.profile} — {prof['title']}")
    if state["mode"] == "written":
        print(f"BUDGET: {k} problems in {state['minutes']} minutes; {marking_text(state['marking'])}")
    else:
        per = state["per_problem"] // 60
        print(f"BUDGET: {k} problems × {per} minutes (round {k * per} minutes)")
    if mix:
        print(f"MIX: {mix_text(mix)}   (each problem's `topic`; the counts must match)")
    if prof:
        print("STYLE:")
        print("\n".join(f"  {s}" for s in prof["style"]))
    if multi:
        print(f"COURSES: {', '.join(c.slug for c in courses)}")
    print("UNITS (write the problems from these; a problem's `units` are ids from this list):")
    if mix:
        for t in mix:
            print(f"  {t}:")
            for c, u in units:
                if topic_of(c, u) == t:
                    print_unit(c, u, unit_ref(c, u, multi), "    ")
    else:
        for c, u in units:
            print_unit(c, u, unit_ref(c, u, multi), "  ")
    past = [pr["technique"] + (f" [{', '.join(pr['techniques'])}]" if pr.get("techniques") else "")
            for hh in homes() for m, _ in rounds(hh) for pr in (load_problems(hh, m) or []) if pr.get("technique")]
    print("PAST TECHNIQUES:")
    print("\n".join(f"  {t}" for t in past) if past else "  (none)")
    save(h, n, state)


def cmd_topic(a):
    courses = all_courses()
    by = {**{os.path.basename(c.dir): c for c in courses}, **{c.slug: c for c in courses}}
    c = by.get(a.course)
    if c is None:
        book.die(f"no course named {a.course}; the courses are: {', '.join(x.slug for x in courses)}", 1)
    if a.topic not in TOPICS:
        book.die(f"not a topic: {a.topic}; the topics are: {', '.join(TOPICS)}", 1)
    bad = [x for x in a.ids if x != "*" and x not in c.by_id]
    if bad:
        book.die(f"not a chapter or unit of {c.slug}: {', '.join(bad)}", 1)
    tags = c.state.setdefault("topics", {})
    for x in a.ids:
        tags[x] = a.topic
    c.save()
    print(f"🗒 {c.slug}: {', '.join(a.ids)} → {a.topic}")


# ---------------------------------------------------------------- checking the problem file

def expected_count(st):
    return PROFILES[st["profile"]]["problems"] if st.get("profile") else LENGTHS[st["length"]]


def written(st):
    return st.get("mode") == "written"


def allowed_units(h, st):
    if "units" in st:
        return set(st["units"])
    courses = round_courses(h, st)  # a round set before the units were recorded
    return {unit_ref(c, u, len(courses) > 1) for c in courses for u in finished_units(c)}


def _check_answer(where, spec):
    variables = spec.get("variables") or {}
    if not isinstance(variables, dict):
        return [f"{where}: variables must be an object from name to range"]
    try:
        answer_check.parse_ranges(variables)
        answer_check.read(str(spec.get("answer", "")), variables)
        need = min(3, len(answer_check.points(str(spec["answer"]), variables)))
        if answer_check.defined_points(str(spec["answer"]), variables) < need:
            return [f"{where}: answer is undefined at most points of the ranges"]
    except answer_check.AnswerError as exc:
        return [f"{where}: answer: {exc}"]
    return []


def problem_errors(h, st, probs):
    if not isinstance(probs, list):
        return ["the problem file must be {\"problems\": [...]}"]
    k = expected_count(st)
    label = st.get("profile") or st["length"]
    errors = [] if len(probs) == k else [f"{label} needs {k} problems, found {len(probs)}"]
    allowed = allowed_units(h, st)
    mix, topics = st.get("mix"), st.get("unit_topics") or {}
    counts = {}
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
        why = "is not one of the round's units" if mix else "is not finished"
        errors += [f"{pid}: unit {u} {why}" for u in units if u not in allowed]
        names = pr.get("techniques")
        if not isinstance(names, list) or not names or not all(str(t).strip() for t in names):
            errors.append(f"{pid}: techniques is empty")
        if mix:
            t = pr.get("topic")
            counts[t] = counts.get(t, 0) + 1
            if t not in mix:
                errors.append(f"{pid}: topic must be one of {', '.join(mix)}")
            elif units and not any(topics.get(u) == t for u in units):
                errors.append(f"{pid}: none of its units is a {t} unit")
        if written(st):
            continue
        hints = pr.get("hints")
        if not isinstance(hints, list) or len(hints) != 3 or not all(str(x).strip() for x in hints):
            errors.append(f"{pid}: needs exactly 3 hints")
        fu = pr.get("followup")
        if not isinstance(fu, dict) or not str(fu.get("statement") or "").strip():
            errors.append(f"{pid}: the follow-up needs a statement")
        else:
            errors += _check_answer(f"{pid} follow-up", fu)
    if mix and counts != mix:
        found = ", ".join(f"{t or 'no topic'} {x}" for t, x in counts.items())
        errors.append(f"the mix is {mix_text(mix)}; the file has {found}")
    return errors


def cmd_check(a):
    h, n, st = the_round(("set", "ready"))
    probs = load_problems(h, n)
    if probs is None:
        book.die(f"no problem file at {book.rel(paths(h, n)['problems'])}", 1)
    errors = problem_errors(h, st, probs)
    if errors:
        print("\n".join(errors))
        sys.exit(1)
    st["status"] = "ready"
    save(h, n, st)
    print(f"🗒 interview ready: {len(probs)} problems")
    known = technique.resolver(technique.load_techniques())
    new = list(dict.fromkeys(str(t) for pr in probs for t in pr["techniques"] if str(t).lower() not in known))
    if new:  # a note written now would show the learner the round's tricks before it starts
        print(f"NEW TECHNIQUES (write their notes after the round): {', '.join(new)}")


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


def per_problem(st):
    return st.get("per_problem") or PER_PROBLEM


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
    return st["minutes"] * 60 if written(st) else len(st["problems"]) * per_problem(st)


def flag(st, t):
    if t - st["started"] >= round_seconds(st):
        return "TIME UP" if written(st) else "ROUND TIME UP"
    if written(st):
        return ""
    pr = st["problems"][st["current"]]
    used, limit = t - pr["start"], per_problem(st)
    if used >= limit:
        return "TIME UP"
    if main_correct_at(pr) is not None:  # the follow-up phase: the nudge flags are for the main problem
        return "FOLLOW-UP" if followup_result(pr) != "solved" else ""
    if used >= 0.75 * limit:
        return "TIME NEARLY UP"
    if used >= 0.5 * limit and not pr["hints"]:
        return "NUDGE IF STUCK"
    return ""


def hook_line(st, t):
    if written(st):
        line = (f"INTERVIEW: written test, {len(st['problems'])} problems · {mmss(t - st['started'])} of "
                f"{mmss(round_seconds(st))}")
    else:
        pr = st["problems"][st["current"]]
        line = (f"INTERVIEW: problem {st['current'] + 1} of {len(st['problems'])} · {mmss(t - pr['start'])} of "
                f"{mmss(per_problem(st))} · hints {len(pr['hints'])} · round {mmss(t - st['started'])} of "
                f"{mmss(round_seconds(st))}")
    f = flag(st, t)
    return line + (f" · {f}" if f else "")


def clock_line(st, t):
    if written(st):
        used, limit = t - st["started"], round_seconds(st)
        return "Test TIME UP" if used >= limit else f"Test {mmss(used)}/{mmss(limit)}"
    pr = st["problems"][st["current"]]
    used = t - pr["start"]
    limit = min(per_problem(st), st["started"] + round_seconds(st) - pr["start"])  # the round may end first
    head = f"P{st['current'] + 1}/{len(st['problems'])}"
    return f"{head} TIME UP" if used >= limit else f"{head} {mmss(used)}/{mmss(round(limit))}"


def running(quiet=False):
    """(home, n, state, problems) of the running round; with quiet, None instead of an error."""
    h = pointed_home()
    if h is None and quiet:
        return None
    op = (h, *open_round(h)) if h else open_anywhere()
    if not op or op[2].get("status") != "running":
        if quiet:
            return None
        book.die("no round is running", 1)
    h, n, st = op
    return h, n, st, load_problems(h, n)


def live_only(st):
    if written(st):
        book.die("a written test has no hints, answers or follow-ups: the learner writes in the paper, "
                 "then: interview.py submit", 1)


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


def signed(x):
    return f"+{x}" if x > 0 else "0" if x == 0 else f"−{-x}"


def marking_text(m):
    return f"a right answer scores {signed(m['right'])}, a wrong one {signed(m['wrong'])}, a blank one {signed(m['blank'])}"


def write_paper(path, st, probs):
    prof = PROFILES[st["profile"]]
    rules = (f"*{len(probs)} problems, {st['minutes']} minutes. {marking_text(st['marking']).capitalize()}."
             + (" A calculator is allowed." if prof.get("calculator") else "")
             + " Write each answer on its **Answer:** line, as a number or a formula: `7/12`, `2^(n+1)-2`, `0.0228`."
             " Do rough work above that line, not below it. Leave the line empty to skip a problem."
             " When you are done, type `submit`.*")
    body = [f"# {prof['title']}", "", rules, ""]
    for i, pr in enumerate(probs, 1):
        body += [f"### Problem {i}", "", pr["statement"].strip(), "", "**Answer:** ", ""]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(body))


def cmd_start(a):
    h, n, st = the_round(("ready",))
    probs = load_problems(h, n)
    t = time.time()
    st["problems"] = [{"id": pr["id"], "start": t if written(st) else None, "end": None, "hints": [], "answers": [],
                       "outcome": None, "followup": "not asked"} for pr in probs]
    st["problems"][0]["start"] = t
    st.update({"status": "running", "session": a.session, "started": t, "current": 0})
    save(h, n, st)
    point_at(h, n)
    note = paths(h, n)["note"]
    if written(st):
        write_paper(note, st, probs)
    fields = {"interview": h.slug, "number": n, "date": time.strftime("%Y-%m-%d")}
    fields.update({"profile": st["profile"]} if st.get("profile") else {"length": st["length"]})
    write_frontmatter(note, {**fields, "status": "running"})
    tmux("set-option", "status-right", f'#(python3 "{os.path.abspath(__file__)}" clock)')
    tmux("set-option", "status-interval", "1")
    if written(st):
        print(f"PAPER: {book.rel(note)}")
        print(f"MINUTES: {st['minutes']}")
        return
    print(f"NOTE: {book.rel(note)}")
    print(f"PROBLEM 1: {probs[0]['statement']}")


def cmd_hook(a):
    try:
        data = json.loads(sys.stdin.read() or "{}")
        r = running(quiet=True)
        if not r or not isinstance(data, dict):
            return
        h, n, st, _ = r
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
    h, n, st, probs = running()
    live_only(st)
    pr = st["problems"][st["current"]]
    hint = {"t": time.time(), "kind": "error" if a.error else "nudge"}
    if a.level is not None:
        hint["level"] = a.level
    pr["hints"].append(hint)
    save(h, n, st)
    k = len(pr["hints"])
    if a.error:
        print(f"ERROR POINTED OUT, recorded as hint {k}.")
        return
    if main_correct_at(pr) is not None:
        print(f"HINT {k} recorded, on the follow-up: there are no prepared nudges for it; give one in your own words.")
        return
    used = sum(1 for x in pr["hints"] if x["kind"] == "nudge")
    prepared = probs[st["current"]]["hints"]
    if used <= len(prepared):
        print(f"HINT {k} recorded. Next prepared nudge: {prepared[used - 1]}")
    else:
        print(f"HINT {k} recorded. No prepared nudges left: give the method, or close the problem.")


def cmd_answer(a):
    h, n, st, probs = running()
    live_only(st)
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
    save(h, n, st)
    print("CORRECT" if verdict == "correct" else "WRONG")
    if verdict == "correct" and not a.followup:
        left = per_problem(st) - (t - pr["start"])
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
    levels = [x["level"] for x in pr["hints"][:shown] if isinstance(x.get("level"), int)]
    top = f", up to level {max(levels)}" if levels else ""
    return [f"CLOSED: Problem {i + 1} — {pr['outcome']} ({mmss(t - pr['start'])}, {shown} hint{'' if shown == 1 else 's'}{top})",
            f"SOLUTION: {probs[i]['solution']}"]


def end_round(h, n, st):
    for pr in st["problems"]:
        if pr["outcome"] is None:
            pr["outcome"] = "not reached"
            pr["followup"] = "not asked"
    st["status"] = "ended"
    save(h, n, st)
    print(f"ROUND OVER: write the marks to {book.rel(paths(h, n)['marks'])}, then run finish")


def cmd_next(a):
    h, n, st, probs = running()
    live_only(st)
    t = time.time()
    print("\n".join(close_problem(st, probs, t, a.gave_up)))
    if st["current"] + 1 >= len(st["problems"]) or t - st["started"] >= round_seconds(st):
        end_round(h, n, st)
        return
    st["current"] += 1
    st["problems"][st["current"]]["start"] = t
    save(h, n, st)
    print(f"PROBLEM {st['current'] + 1}: {probs[st['current']]['statement']}")


def cmd_stop(a):
    h, n, st, probs = running()
    if written(st):
        submit(h, n, st, probs)
        return
    print("\n".join(close_problem(st, probs, time.time())))
    end_round(h, n, st)


def cmd_abandon(a):
    h, n, st = the_round(OPEN)
    st["status"] = "abandoned"
    save(h, n, st)
    if os.path.exists(paths(h, n)["note"]):
        write_frontmatter(paths(h, n)["note"], {"status": "abandoned"})
    clear_pointer()
    clear_status_bar()
    print(f"🗒 interview abandoned: {book.rel(paths(h, n)['note'])}")


# ---------------------------------------------------------------- written tests

HEADING_RE = re.compile(r"^#{1,6}\s")
PROBLEM_RE = re.compile(r"^###\s+Problem\s+(\d+)\s*$")
ANSWER_RE = re.compile(r"^\*\*Answer:\*\*")


def clean_answer(text):
    """The answer as the checker reads it: `$` signs, blank lines and a final full stop dropped."""
    return re.sub(r"\s+", " ", text.replace("$", "")).strip().rstrip(".").strip()


def read_paper(path, k):
    """([answer of problem 1…k], [problems with the paper]). An answer runs from its **Answer:** line to the next
    heading."""
    lines = lesson.read(path) if os.path.exists(path) else []
    found, cur, buf = {}, None, None
    for ln in lines:
        if HEADING_RE.match(ln):
            m = PROBLEM_RE.match(ln)
            cur, buf = (int(m.group(1)) if m else None), None
            if cur is not None:
                found.setdefault(cur, None)
            continue
        if cur is None:
            continue
        if buf is None and found.get(cur) is None and ANSWER_RE.match(ln):
            buf = found[cur] = [ANSWER_RE.sub("", ln)]
        elif buf is not None:
            buf.append(ln)
    problems = [f"Problem {i}: no `### Problem {i}` heading" if i not in found else
                f"Problem {i}: no `**Answer:**` line" for i in range(1, k + 1) if found.get(i) is None]
    return [clean_answer("\n".join(found.get(i) or [])) for i in range(1, k + 1)], problems


def score_of(st):
    m, c = st["marking"], st["counts"]
    return sum(m[v] * c[v] for v in ("right", "wrong", "blank")), m["right"] * len(st["problems"])


def time_text(st):
    used, limit = st["submitted"] - st["started"], round_seconds(st)
    return f"{mmss(used)} of {mmss(limit)}" + (f", over by {mmss(used - limit)}" if used > limit else "")


def counts_text(c):
    return f"{c['right']} right, {c['wrong']} wrong, {c['blank']} blank"


def submit(h, n, st, probs):
    note = paths(h, n)["note"]
    answers, problems = read_paper(note, len(probs))
    if problems:
        print(f"cannot read {book.rel(note)}; repair it and submit again:")
        print("\n".join(f"  - {p}" for p in problems))
        sys.exit(1)
    verdicts, unreadable = [], []
    for i, (spec, text) in enumerate(zip(probs, answers), 1):
        if not text:
            verdicts.append("blank")
            continue
        try:
            v = answer_check.check(text, str(spec["answer"]), spec.get("variables") or {})
            verdicts.append("right" if v == "correct" else "wrong")
        except answer_check.AnswerError as exc:
            unreadable.append(f"  - Problem {i}: {text} — {exc}")
    if unreadable:
        print("UNREADABLE (nothing is scored yet; the learner writes these as a number or a formula, then submits again):")
        print("\n".join(unreadable))
        sys.exit(1)
    t = time.time()
    for pr, v, text in zip(st["problems"], verdicts, answers):
        pr.update(result=v, answer=text, outcome="solved" if v == "right" else "unsolved", end=t)
    st.update(status="ended", submitted=t, counts={v: verdicts.count(v) for v in ("right", "wrong", "blank")})
    save(h, n, st)
    write_frontmatter(note, {"status": "submitted"})
    score, top = score_of(st)
    print(f"SCORE: {score} of {top} ({counts_text(st['counts'])}) in {time_text(st)}")
    for i, (pr, spec) in enumerate(zip(st["problems"], probs), 1):
        print(f"  Problem {i} {pr['result']}" + (f": {pr['answer']} (the answer is {spec['answer']})"
                                                 if pr["result"] == "wrong" else ""))
    print(f"ROUND OVER: write the marks to {book.rel(paths(h, n)['marks'])}, then run finish")


def cmd_submit(a):
    h, n, st, probs = running()
    if not written(st):
        book.die("submit is for a written test; a live round ends with: interview.py stop", 1)
    submit(h, n, st, probs)


# ---------------------------------------------------------------- the scorecard

def marks_errors(st, marks):
    if not isinstance(marks, dict) or not isinstance(marks.get("problems", {} if written(st) else None), dict):
        return ["marks: the file must have a \"problems\" object"]
    given = {pr["id"] for pr in st["problems"] if pr["outcome"] != "not reached"}
    fb = marks.get("problems") or {}
    errors = [] if written(st) else [f"marks: no feedback for {pid}" for pid in sorted(given)
                                     if not str(fb.get(pid) or "").strip()]
    errors += [f"marks: {pid} was not reached" for pid in sorted(fb) if pid not in given]
    return errors


def technique_cell(spec):
    """`[[Symmetry]], [[…]] — <description>`; a name that no longer resolves stays plain text."""
    known = technique.resolver(technique.load_techniques())
    names = [f"[[{known[str(t).lower()]}]]" if str(t).lower() in known else str(t) for t in spec.get("techniques") or []]
    return " — ".join(x for x in (", ".join(names), spec.get("technique", "")) if x)


def feedback_blocks(st, marks):
    import exam  # for section_label; imports lesson and book, already loaded
    out = []
    for i, pr in enumerate(st["problems"], 1):
        if pr["id"] in (marks.get("problems") or {}):
            out.append(f"**Problem {i}:** {marks['problems'][pr['id']]}")
    comm = marks.get("communication") or {}
    if comm:
        out.append("**How you explained:** " + "; ".join(f"{k} — {v}" for k, v in comm.items()))
    if marks.get("work_on"):
        out.append("**Work on:** " + "; ".join(marks["work_on"]))
    if marks.get("revisit"):
        out.append("**Revisit:** " + "; ".join(f"[[{target}|{exam.section_label(target)}]] — {why}"
                                               for target, why in marks["revisit"].items()))
    return out


def folded(title, body):
    quoted = "\n".join(("> " + ln) if ln else ">" for ln in "\n".join(body).strip().split("\n"))
    return f"> [!example]- {title}\n{quoted}"


def scorecard(st, probs, marks):
    rows = ["### Scorecard", "", "| | Outcome | Time | Hints | Follow-up | Technique |", "|---|---|---|---|---|---|"]
    for i, (pr, spec) in enumerate(zip(st["problems"], probs), 1):
        if pr["outcome"] == "not reached":
            rows.append(f"| Problem {i} | not reached | — | — | — | {technique_cell(spec)} |")
            continue
        hints = hints_before(pr, main_correct_at(pr)) if main_correct_at(pr) is not None else len(pr["hints"])
        rows.append(f"| Problem {i} | {pr['outcome']} | {mmss(pr['end'] - pr['start'])} | {hints} | "
                    f"{pr['followup']} | {technique_cell(spec)} |")
    out = ["\n".join(rows)] + feedback_blocks(st, marks)
    for i, (pr, spec) in enumerate(zip(st["problems"], probs), 1):
        if pr["outcome"] == "not reached":
            continue
        fu = spec["followup"]
        out.append(folded(f"Problem {i} — solution", [spec["statement"], "", spec["solution"], "",
                                                      f"**Follow-up:** {fu['statement']}", "", fu.get("solution") or ""]))
    return "\n\n".join(out) + "\n"


def cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def written_scorecard(st, probs, marks):
    score, top = score_of(st)
    m = st["marking"]
    head = [f"> [!summary] Score — {score} of {top}",
            f"> {counts_text(st['counts'])} · marking {signed(m['right'])} / {signed(m['wrong'])} / "
            f"{signed(m['blank'])} · {time_text(st)}"]
    rows = ["| | Result | Your answer | Answer | Topic | Technique |", "|---|---|---|---|---|---|"]
    for i, (pr, spec) in enumerate(zip(st["problems"], probs), 1):
        mine = f"`{cell(pr['answer'])}`" if pr["answer"] else "—"
        right = f"${cell(spec['answerLatex'])}$" if spec.get("answerLatex") else f"`{cell(spec['answer'])}`"
        rows.append(f"| Problem {i} | {pr['result']} | {mine} | {right} | {spec.get('topic', '')} | "
                    f"{technique_cell(spec)} |")
    out = ["### Result", "\n".join(head), "\n".join(rows)] + feedback_blocks(st, marks)
    out += [folded(f"Problem {i} — solution", [spec["statement"], "", spec["solution"]])
            for i, spec in enumerate(probs, 1)]
    return "\n\n".join(out) + "\n"


def cmd_finish(a):
    h, n, st = the_round(("ended",))
    marks = book.load_json(a.marks, None)
    errors = marks_errors(st, marks)
    if errors:
        book.die("\n".join(errors), 1)
    note = paths(h, n)["note"]
    probs = load_problems(h, n)
    text = open(note, encoding="utf-8").read() if os.path.exists(note) else ""
    card = written_scorecard(st, probs, marks) if written(st) else scorecard(st, probs, marks)
    with open(note, "w", encoding="utf-8") as f:
        f.write(text.rstrip("\n") + "\n\n" + card)
    solved = sum(pr["outcome"] == "solved" for pr in st["problems"])  # unaided; hinted solves are in the table
    if written(st):
        score, top = score_of(st)
        write_frontmatter(note, {"status": "finished", "score": f"{score}/{top}"})
        st.update({"status": "finished", "solved": solved, "score": score})
        done = f"{score} of {top} ({counts_text(st['counts'])})"
    else:
        write_frontmatter(note, {"status": "finished", "solved": f"{solved}/{len(st['problems'])}"})
        st.update({"status": "finished", "solved": solved})
        done = f"{solved}/{len(st['problems'])} solved"
    save(h, n, st)
    try:
        technique.sync()  # the round's problems join their technique notes
    except Exception:
        pass  # a broken technique note must not stop the round from finishing
    clear_pointer()
    clear_status_bar()
    print(f"🗒 interview finished: {done}")


def cmd_list(a):
    found = False
    for h in homes():
        for n, st in rounds(h):
            found = True
            line = (f"{h.slug}-interview-{n}  {st.get('set', '')}  {st.get('profile') or st.get('length', '')}  "
                    f"{st.get('status', '')}")
            if st.get("status") == "finished":
                if written(st):
                    score, top = score_of(st)
                    line += f"  {score}/{top} ({counts_text(st['counts'])})"
                else:
                    line += f"  {st.get('solved', 0)}/{len(st.get('problems', []))} solved"
            print(line)
    if not found:
        print("no interviews yet")


def interview_misses(note):
    """Lines for the resume brief: the problems not solved unaided in the newest finished round of the note's course,
    and in the newest finished round on several courses, on units of this note or the chapter before it."""
    import figures
    cdir = figures.course_of(note)
    if not cdir:
        return []
    sources = {os.path.abspath(s) for s in lesson.review_sources(note)}
    out = []
    for h in (course_home(book.Course(cdir)), vault_home()):
        done = [(n, st) for n, st in rounds(h) if st.get("status") == "finished"]
        if not done:
            continue
        n, st = done[-1]
        probs = load_problems(h, n) or []
        courses = round_courses(h, st)
        lines = []
        for i, (pr, spec) in enumerate(zip(st["problems"], probs), 1):
            c, unit = resolve_unit(courses, (spec.get("units") or [""])[0])
            if pr["outcome"] not in ("hinted", "unsolved") or not unit or os.path.abspath(c.dir) != os.path.abspath(cdir):
                continue
            if os.path.abspath(c.note(unit["chapter"])) not in sources:
                continue
            text = re.sub(r"\s+", " ", spec["statement"])
            lines.append(f"  - Problem {i} {pr['outcome']} §{unit['id']} — {spec['technique']}: "
                         f"{text[:90]}{'…' if len(text) > 90 else ''}")
        if lines:
            out += [f"INTERVIEW MISSES ({h.slug}-interview-{n}): re-probe these first"] + lines
    return out


def main(argv=None):
    p = argparse.ArgumentParser(prog="interview.py", description="Mock interviews on the finished units of the courses.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("new")
    s.add_argument("--length", choices=sorted(LENGTHS))
    s.add_argument("--profile", choices=list(PROFILES))
    s.add_argument("--courses", help="comma-separated course names (default: every course with a finished unit)")
    s.add_argument("--minutes", type=int, help="a written test's time (default: the profile's)")
    s = sub.add_parser("topic")
    s.add_argument("course")
    s.add_argument("topic")
    s.add_argument("ids", nargs="+", metavar="chapter|unit|*")
    sub.add_parser("check")
    s = sub.add_parser("start")
    s.add_argument("--session", required=True)
    sub.add_parser("hook")
    sub.add_parser("clock")
    s = sub.add_parser("hint")
    s.add_argument("--error", action="store_true")
    s.add_argument("--level", type=int, choices=range(6), help="the hint's level, 0-5 (the practice rules)")
    s = sub.add_parser("answer")
    s.add_argument("text")
    s.add_argument("--followup", action="store_true")
    s = sub.add_parser("next")
    s.add_argument("--gave-up", action="store_true")
    sub.add_parser("submit")
    sub.add_parser("stop")
    s = sub.add_parser("finish")
    s.add_argument("--marks", required=True)
    sub.add_parser("abandon")
    sub.add_parser("list")
    a = p.parse_args(argv)
    {"new": cmd_new, "topic": cmd_topic, "check": cmd_check, "start": cmd_start, "hook": cmd_hook, "clock": cmd_clock,
     "hint": cmd_hint, "answer": cmd_answer, "next": cmd_next, "submit": cmd_submit, "stop": cmd_stop,
     "finish": cmd_finish, "abandon": cmd_abandon, "list": cmd_list}[a.cmd](a)


if __name__ == "__main__":
    main()
