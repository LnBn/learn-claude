#!/usr/bin/env python3
"""
coding — code tasks, judged by hidden tests: a practice track of problems, or tasks inside a lesson.

The teacher writes a task's note, its starter file and its hidden tests (see coding_runner.py for the tests
module). This script does what must be exact: paths, checking the tests against their reference solution, the
speed limit, running a submission case by case in child processes, and recording the result in the task note,
the lesson note or the track index. Run it from the vault root.

    coding.py track new <slug> --title "<title>" [--python <interpreter>]
    coding.py track syllabus <slug> --file <syllabus.json>     [{"topic", "target": 1-5}, ...] in order
    coding.py plan (--track <slug> | --note <lesson.md>) --slug <task-slug>
                        the next task's paths and number (and in a track: topic levels, recent results, the topic
                        to practise next); writes nothing in a track, the lesson's state on first use
    coding.py check <task.md> --topics a,b --level 1-5
                        validate the task against its reference and register it as open
"""
import argparse
import json
import math
import os
import re
import signal
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(HERE, "coding_runner.py")
FLOOR = 0.2  # seconds: the smallest speed limit, so that timing noise does not fail a sound solution
FACTOR = 10  # the limit is this many times the reference's time
CASE_KILL = 5.0  # seconds before a correctness case is killed
TASK_RE = re.compile(r"^(\d\d)-(.+)\.md$")


# ---- paths and state

def track_dir(slug):
    return os.path.join("practice", slug)


def lesson_dir(note):
    d, f = os.path.split(note)
    return os.path.join(d, os.path.splitext(f)[0] + " — code")


def hidden_dir(base):
    """A track keeps its hidden files in .track/, a lesson's tasks in .tests/."""
    return os.path.join(base, ".track" if os.path.isdir(os.path.join(base, ".track")) else ".tests")


def load_state(base):
    try:
        with open(os.path.join(hidden_dir(base), "state.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_state(base, state):
    os.makedirs(hidden_dir(base), exist_ok=True)
    path = os.path.join(hidden_dir(base), "state.json")
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(path + ".tmp", path)


def task_paths(base, n, slug):
    stem = f"{n:02d}-{slug}"
    return {"note": os.path.join(base, stem + ".md"), "starter": os.path.join(base, stem + ".py"),
            "tests": os.path.join(hidden_dir(base), stem + ".py")}


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def task_title(note_text):
    return next((ln[2:].strip() for ln in note_text.splitlines() if ln.startswith("# ")), "")


def statement(note_text):
    """The task's first paragraph of prose: after the title, skipping the italic line under it."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", note_text) if p.strip()]
    return next((p for p in paras if not p.startswith("#") and not (p.startswith("*") and p.endswith("*"))), "")


# ---- running cases

def run_case(tests, case, solution=None, impl=None, kill=CASE_KILL, python="python3"):
    """The runner's result for one case, plus "timeout"; a case that dies without a result is a failure."""
    cmd = [python, RUNNER, tests, case] + (["--solution", solution] if solution else ["--impl", impl]) \
        + ["--cpu", str(math.ceil(kill))]
    blank = {"name": case, "passed": False, "got": None, "expected": None, "seconds": None, "stdout": "",
             "error": None, "timeout": False}
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=kill)
    except subprocess.TimeoutExpired:
        return {**blank, "timeout": True}
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    try:
        return {**json.loads(lines[-1]), "timeout": False}
    except (IndexError, ValueError):
        if proc.returncode == -signal.SIGXCPU:
            return {**blank, "timeout": True}
        last = (proc.stderr.strip().splitlines() or [f"the case ended with exit status {proc.returncode}"])[-1]
        return {**blank, "error": last}


def count(tests, python="python3"):
    proc = subprocess.run([python, RUNNER, tests, "--count"], capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise ValueError((proc.stderr.strip().splitlines() or ["the tests file does not load"])[-1])
    return json.loads(proc.stdout)


# ---- the track index and the lesson box

def write_index(base, state):
    rows = [f"# {state['title']}", "", "## Topics", "", "| Topic | Level | Target |", "|---|---|---|"]
    rows += [f"| {t['topic']} | {t['level']} | {t['target']} |" for t in state["syllabus"]]
    rows += ["", "## Tasks", "", "| # | Task | Topics | Level | Status | Submissions | Hints |",
             "|---|---|---|---|---|---|---|"]
    for t in state["tasks"]:
        rows.append(f"| {t['n']:02d} | [[{t['n']:02d}-{t['slug']}]] | {', '.join(t['topics'])} | {t['level']} | "
                    f"{t['status']} | {len(t['submissions'])} | {t['hints']} |")
    write(os.path.join(base, os.path.basename(base) + ".md"), "\n".join(rows) + "\n")


def lesson_box(base, rec):
    """The task's callout in its lesson note: titled by the outcome, with the statement and one line per submission."""
    subs = rec["submissions"]
    passed = any(s["passed"] for s in subs)
    title = f"Task {rec['n']:02d}: {rec['title']}"
    if rec["status"] == "helped":
        kind, head = "info", f"✓ {title} (solution shown)"
    elif rec["status"] == "shown":
        kind, head = "warning", f"⊘ {title} (solution shown)"
    elif passed:
        kind, head = "success", ("✗→✓ " if not subs[0]["passed"] else "✓ ") + title
    elif subs:
        kind, head = "failure", "✗ " + title
    else:
        kind, head = "question", title
    paths = task_paths(base, rec["n"], rec["slug"])
    stem = os.path.splitext(os.path.basename(paths["note"]))[0]
    body = [statement(read(paths["note"])), "",
            f"[[{os.path.basename(base)}/{stem}|Task note]] · file `{paths['starter']}`"]
    if subs:
        body.append("")
        body += [f"- Submission {s['k']}: {'✓' if s['passed'] else '✗'} {s['cases']} passed" for s in subs]
    lines = [f"> [!{kind}|code]{'+' if kind == 'question' else '-'} {head}", ">"]
    lines += [f"> {ln}" if ln else ">" for part in body for ln in part.split("\n")]
    return "\n".join(lines)


def put_lesson_box(state, base, rec):
    """Replace the task's box in the lesson note (found by its "Task NN:" header), or append it."""
    note = state["note"]
    text = read(note) if os.path.exists(note) else ""
    lines = text.split("\n")
    head = re.compile(rf"^> \[!\w+\|code\][-+] .*Task {rec['n']:02d}: ")
    start = next((i for i, ln in enumerate(lines) if head.match(ln)), None)
    box = lesson_box(base, rec)
    if start is None:
        write(note, text.rstrip("\n") + ("\n\n" if text.strip() else "") + box + "\n")
        return
    end = start
    while end < len(lines) and lines[end].startswith(">"):
        end += 1
    write(note, "\n".join(lines[:start] + box.split("\n") + lines[end:]))


# ---- commands

def fail(msg, code=1):
    print(msg)
    return code


def cmd_track(a):
    base = track_dir(a.slug)
    if a.action == "new":
        if load_state(base):
            return fail(f"REFUSED track {a.slug} exists: {base}")
        os.makedirs(os.path.join(base, ".track"), exist_ok=True)
        state = {"kind": "track", "slug": a.slug, "title": a.title or a.slug, "python": a.python or "python3",
                 "syllabus": [], "revisit": [], "tasks": []}
        save_state(base, state)
        write_index(base, state)
        print(f"TRACK {base}")
        print(f"INDEX {os.path.join(base, a.slug + '.md')}")
        return 0
    state = load_state(base)
    if not state:
        return fail(f"REFUSED no track {a.slug} (coding.py track new {a.slug} --title …)")
    with open(a.file, encoding="utf-8") as f:
        topics = json.load(f)
    old = {t["topic"]: t["level"] for t in state["syllabus"]}
    state["syllabus"] = [{"topic": t["topic"], "target": int(t["target"]), "level": old.get(t["topic"], 1)}
                         for t in topics]
    save_state(base, state)
    write_index(base, state)
    print("SYLLABUS " + ", ".join(f"{t['topic']}={t['level']}/{t['target']}" for t in state["syllabus"]))
    return 0


def suggest(state):
    if state["revisit"] and len(state["tasks"]) % 4 == 3:
        return state["revisit"][0]
    return next((t["topic"] for t in state["syllabus"] if t["level"] < t["target"]), None)


def cmd_plan(a):
    if a.track:
        base = track_dir(a.track)
        state = load_state(base)
        if not state:
            return fail(f"REFUSED no track {a.track} (coding.py track new {a.track} --title …)")
    else:
        if not os.path.exists(a.note):
            return fail(f"REFUSED no note {a.note}")
        base = lesson_dir(a.note)
        state = load_state(base)
        if not state:
            state = {"kind": "lesson", "note": a.note, "python": "python3", "tasks": []}
            save_state(base, state)
    n = max((t["n"] for t in state["tasks"]), default=0) + 1
    p = task_paths(base, n, a.slug)
    print(f"NOTE {p['note']}")
    print(f"STARTER {p['starter']}")
    print(f"TESTS {p['tests']}")
    print(f"TASK {n:02d}")
    if state["kind"] == "track":
        print("LEVELS " + ", ".join(f"{t['topic']}={t['level']}/{t['target']}" for t in state["syllabus"]))
        for t in state["tasks"][-8:]:
            print(f"LAST {t['n']:02d} {t['slug']} {t['status']} topics={','.join(t['topics'])} "
                  f"submissions={len(t['submissions'])} hints={t['hints']}")
        if state["revisit"]:
            print("REVISIT " + ", ".join(state["revisit"]))
        nxt = suggest(state)
        print(f"SUGGEST {nxt}" if nxt else "SUGGEST none: every topic is at its target")
    return 0


def check_task(note, topics, python):
    """(problems, limit) for a task: the tests against the reference, the speed limit, slow() against it."""
    base = os.path.dirname(note)
    m = TASK_RE.match(os.path.basename(note))
    p = task_paths(base, int(m.group(1)), m.group(2))
    try:
        info = count(p["tests"], python)
    except ValueError as e:
        return [f"the tests file does not load: {e}"], None
    if not re.search(rf"^\s*def\s+{re.escape(info['function'])}\s*\(", read(p["starter"]), re.M):
        return [f"the starter file does not define {info['function']}()"], None
    problems = []
    for i, name in enumerate(info["cases"]):
        r = run_case(p["tests"], f"case:{i}", impl="reference", python=python)
        if not r["passed"]:
            problems.append(f"case {name}: reference returns {r['got']}, the case expects {r['expected']}"
                            + (f" ({r['error'].splitlines()[0]})" if r["error"] else ""))
    if problems or not info["large"]:
        return problems, None
    medians = []
    for i, name in enumerate(info["large"]):
        runs = [run_case(p["tests"], f"large:{i}", impl="reference", kill=60, python=python) for _ in range(3)]
        if not all(r["passed"] for r in runs):
            problems.append(f"speed case {name}: reference() fails or times out")
            continue
        medians.append(statistics.median(r["seconds"] for r in runs))
    if problems:
        return problems, None
    limit = round(max(FLOOR, FACTOR * max(medians)), 3)
    if info["slow"]:
        runs = [run_case(p["tests"], f"large:{i}", impl="slow", kill=2 * limit, python=python)
                for i in range(len(info["large"]))]
        if not any(r["timeout"] or (r["seconds"] or 0) > limit for r in runs):
            problems.append("the speed tests do not separate slow() from reference(): make the inputs larger")
    return problems, limit


def cmd_check(a):
    note = os.path.normpath(a.note)
    base = os.path.dirname(note)
    state = load_state(base)
    m = TASK_RE.match(os.path.basename(note))
    if not state or not m:
        return fail(f"REFUSED {note} is not a planned task (coding.py plan … first)")
    problems = []
    topics = [t.strip() for t in a.topics.split(",") if t.strip()]
    if state["kind"] == "track":
        known = {t["topic"] for t in state["syllabus"]}
        problems += [f"topic {t} is not in the syllabus" for t in topics if t not in known]
    p = task_paths(base, int(m.group(1)), m.group(2))
    problems += [f"missing {k} file {p[k]}" for k in ("note", "starter", "tests") if not os.path.exists(p[k])]
    limit = None
    if not problems:
        found, limit = check_task(note, topics, state["python"])
        problems += found
    if problems:
        for msg in problems:
            print(f"REFUSED {msg}")
        return 1
    n = int(m.group(1))
    state["tasks"] = [t for t in state["tasks"] if t["n"] != n]  # a re-check replaces the record
    rec = {"n": n, "slug": m.group(2), "title": task_title(read(note)), "topics": topics, "level": a.level,
           "status": "open", "submissions": [], "hints": 0, "limit": limit,
           "created": time.strftime("%Y-%m-%d %H:%M"), "passed_at": None}
    state["tasks"].append(rec)
    state["tasks"].sort(key=lambda t: t["n"])
    save_state(base, state)
    if state["kind"] == "track":
        write_index(base, state)
    else:
        put_lesson_box(state, base, rec)
    print(f"OPEN {note}")
    if limit is not None:
        print(f"LIMIT {round(limit * 1000)} ms")
    return 0


def main(argv):
    p = argparse.ArgumentParser(prog="coding.py", description=__doc__.strip().splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("track")
    t.add_argument("action", choices=["new", "syllabus"])
    t.add_argument("slug")
    t.add_argument("--title")
    t.add_argument("--python")
    t.add_argument("--file")
    pl = sub.add_parser("plan")
    g = pl.add_mutually_exclusive_group(required=True)
    g.add_argument("--track")
    g.add_argument("--note")
    pl.add_argument("--slug", required=True)
    c = sub.add_parser("check")
    c.add_argument("note")
    c.add_argument("--topics", required=True)
    c.add_argument("--level", type=int, choices=range(1, 6), required=True)
    a = p.parse_args(argv[1:])
    if a.cmd == "track" and a.action == "syllabus" and not a.file:
        p.error("track syllabus needs --file")
    return {"track": cmd_track, "plan": cmd_plan, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
