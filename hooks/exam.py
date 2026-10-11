#!/usr/bin/env python3
"""
exam — set, submit and grade an exam paper on a course chapter or a lesson note.

The teacher writes the paper (markdown, in an `exams/` folder beside the note it tests) and its marking scheme
(JSON, in the hidden `.exams/` folder beside that). This script does what must be exact: paths, validation,
reading the filled-in paper, multiple-choice grading, feedback callouts, totals, and the course's state.

    exam.py new [<chapter> | <note.md>] --length short|standard|long
                        where the paper and scheme go, the attempt, the budget, the sections it may test
                        (and in a course the pages to read); writes nothing
    exam.py check <paper>   validate the paper against its scheme; when valid, register it as open
    exam.py submit [<paper>]
                        hand in a paper (default: the only open one): snapshot it, grade the multiple choice,
                        print the brief for marking the written answers
    exam.py grade <paper> [--regrade q7]
                        read the written answers' marks as JSON on stdin ({"q7": {"awarded": 3, "feedback": "…"},
                        "revisit": {"<note>#<heading>": "<clause>"}}), write the feedback and the result into the
                        paper, mark weak units shaky; --regrade rewrites one question's feedback and the totals
"""
import argparse
import glob
import json
import os
import re
import sys
import time

import book
import figures
import lesson

BUDGET = {
    "short": {"minutes": 20, "A": (4, 2), "B": (2, 4), "C": (1, 8), "marks": 24},
    "standard": {"minutes": 45, "A": (6, 2), "B": (3, 4), "C": (2, 8), "marks": 40},
    "long": {"minutes": 90, "A": (8, 2), "B": (4, 4), "C": (3, 10), "marks": 62},
}
TYPES = ("mc", "short", "long")
QUESTION_RE = re.compile(r"^### Q(\d+)\s*\((\d+(?:\.\d+)?) marks?\)")
PART_RE = re.compile(r"^## Part ([A-Z])\b")
OPTION_RE = re.compile(r"^\s*[-*]\s+\[( |x|X)\]\s+([a-z])\)")
ANSWER_RE = re.compile(r"^\*\*Answer:\*\*")


def fmt(x):
    """A mark as written in the paper: 3, 1.5, 2.25."""
    return f"{float(x):g}"


def read_frontmatter(text):
    """({key: value}, body). Values are kept as written."""
    text = text.replace("\r\n", "\n")
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}, text
    fields = {}
    for ln in m.group(1).split("\n"):
        k, sep, v = ln.partition(":")
        if sep and k.strip() and not ln.startswith((" ", "\t")):
            fields[k.strip()] = v.strip()
    return fields, text[m.end():]


def set_frontmatter(text, **fields):
    """The text with these frontmatter fields changed or added; every other line stays as it was."""
    text = text.replace("\r\n", "\n")
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    lines = m.group(1).split("\n") if m else []
    for k, v in fields.items():
        v = "" if v is None else str(v)
        at = next((i for i, ln in enumerate(lines) if re.match(rf"{re.escape(k)}\s*:", ln)), None)
        if at is None:
            lines.append(f"{k}: {v}")
        else:
            lines[at] = f"{k}: {v}"
    return "---\n" + "\n".join(lines) + "\n---\n" + (text[m.end():] if m else text)


def parse_paper(text):
    """({"q7": {"part", "marks", "options", "ticked", "answer", "has_answer", "start", "end"}}, problems).
    A question runs from its `### Q<n>` heading to the next one or the next `## Part`; any other heading
    belongs to the answer."""
    lines = text.replace("\r\n", "\n").split("\n")
    heads = []
    part = None
    for i, ln in enumerate(lines):
        pm = PART_RE.match(ln)
        if pm:
            part = pm.group(1)
            heads.append((i, None, None, None))
            continue
        qm = QUESTION_RE.match(ln)
        if qm:
            heads.append((i, f"q{qm.group(1)}", float(qm.group(2)), part))
    qs, problems = {}, []
    for k, (i, qid, marks, part) in enumerate(heads):
        if qid is None:
            continue
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        if qid in qs:
            problems.append(f"Q{qid[1:]} appears twice in the paper")
            continue
        body = lines[i + 1:end]
        options, ticked = [], set()
        for ln in body:
            om = OPTION_RE.match(ln)
            if om:
                options.append(om.group(2))
                if om.group(1) in "xX":
                    ticked.add(om.group(2))
        at = next((j for j, ln in enumerate(body) if ANSWER_RE.match(ln)), None)
        answer = ""
        if at is not None:
            answer = "\n".join([ANSWER_RE.sub("", body[at]).strip()] + body[at + 1:]).strip("\n")
        stop = next((j for j, ln in enumerate(body) if ANSWER_RE.match(ln) or OPTION_RE.match(ln)), len(body))
        qs[qid] = {"part": part, "marks": marks, "options": options, "ticked": ticked, "answer": answer,
                   "has_answer": at is not None, "text": "\n".join(body[:stop]).strip(), "start": i, "end": end}
    return qs, problems


def check(paper_text, scheme, sections):
    """Problems with a paper and its scheme, each naming its question as Q<n>; empty when they agree.
    `sections`: the "<note stem>#<heading>" strings the exam may cite."""
    qs, problems = parse_paper(paper_text)
    fm, _ = read_frontmatter(paper_text)
    entries = scheme.get("questions") or []
    ids = [e.get("id") for e in entries]
    want = [f"q{n}" for n in range(1, len(ids) + 1)]
    if ids != want:
        problems.append(f"scheme question ids must run q1…q{len(ids)} in order: {', '.join(map(str, ids))}")
    for qid in qs:
        if qid not in ids:
            problems.append(f"Q{qid[1:]} is in the paper but not in the scheme")
    total = 0.0
    for e in entries:
        qid = e.get("id") or "?"
        name = f"Q{qid[1:]}" if qid.startswith("q") else qid
        marks = float(e.get("marks") or 0)
        total += marks
        q = qs.get(qid)
        if q is None:
            problems.append(f"{name} is in the scheme but has no `### {name} (… marks)` heading in the paper")
            continue
        if q["marks"] != marks:
            problems.append(f"{name}: the heading says {fmt(q['marks'])} marks, the scheme {fmt(marks)}")
        if e.get("part") != q["part"]:
            problems.append(f"{name}: in Part {q['part']} of the paper, Part {e.get('part')} in the scheme")
        if e.get("type") not in TYPES:
            problems.append(f"{name}: type must be one of {', '.join(TYPES)}")
        elif e["type"] == "mc":
            correct = e.get("correct") or []
            if not q["options"]:
                problems.append(f"{name}: multiple choice, but the paper has no `- [ ] a)` options")
            if not correct or not set(correct) <= set(q["options"]):
                problems.append(f"{name}: correct answer {correct} is not among the options {q['options']}")
            if not e.get("explanation"):
                problems.append(f"{name}: no explanation")
            missing = [o for o in q["options"] if o not in correct and o not in (e.get("why_wrong") or {})]
            if missing:
                problems.append(f"{name}: no why_wrong for option(s) {', '.join(missing)}")
        else:
            if not q["has_answer"]:
                problems.append(f"{name}: no **Answer:** line in the paper")
            pts = sum(float(p.get("marks") or 0) for p in e.get("points") or [])
            if pts != marks:
                problems.append(f"{name}: marking points add up to {fmt(pts)}, the question is worth {fmt(marks)}")
            if not e.get("model_answer"):
                problems.append(f"{name}: no model answer")
        if e.get("section") not in sections:
            problems.append(f"{name}: section {e.get('section')!r} is not a section this exam may test")
    try:
        paper_marks = float(fm.get("marks", "nan"))
    except ValueError:
        paper_marks = float("nan")
    if not (total == float(scheme.get("marks") or 0) == paper_marks):
        problems.append(f"marks: questions add up to {fmt(total)}, the scheme says {scheme.get('marks')}, "
                        f"the paper's frontmatter {fm.get('marks')}")
    return problems


# ---------------------------------------------------------------- what an exam covers

def latest_complete_chapter(c):
    """The chapter finished last: every syllabus unit of it is done, shaky or skipped, and one at least is studied."""
    chosen = {u["id"] for u in c.syllabus()}
    best = None
    for ch in c.chapters(appendices=True):
        us = [u for u in c.units_of(ch) if u["id"] in chosen]
        if not us or any(c.status(u["id"]) == "todo" for u in us):
            continue
        if not any(c.status(u["id"]) in ("done", "shaky") for u in us):
            continue
        at = max((c.state["status"].get(u["id"]) or {}).get("at", "") for u in us)
        key = (at, book.natural(ch["id"]))
        if best is None or key > best[0]:
            best = (key, ch["id"])
    return best[1] if best else None


def _chapter(c, ch_id):
    ch = c.by_id.get(ch_id)
    if not ch or ch["kind"] not in ("chapter", "appendix"):
        book.die(f"not a chapter of {c.slug}: {ch_id}")
    chosen = {u["id"] for u in c.syllabus()}
    us = [u for u in c.units_of(ch) if u["id"] in chosen]
    tested = [u["id"] for u in us if c.status(u["id"]) in ("done", "shaky")]
    if not tested:
        book.die(f"nothing of chapter {ch_id} has been studied yet, so there is nothing to examine")
    return {"note": os.path.abspath(c.note(ch_id)), "course": c, "chapter": ch_id, "units": tested,
            "left_out": [u["id"] for u in us if u["id"] not in tested],
            "title": f"Exam — Chapter {ch_id}: {ch['title']}"}


def resolve(target):
    """What an exam on `target` covers: a chapter id, a note, or (None) the chapter finished last."""
    if target and target.endswith(".md"):
        note = os.path.abspath(os.path.expanduser(target))
        cdir = figures.course_of(note)
        if cdir:
            c = book.Course(cdir)
            ch = next((x["id"] for x in c.chapters(appendices=True)
                       if os.path.abspath(c.note(x["id"])) == note), None)
            if ch:
                return _chapter(c, ch)
        if not os.path.exists(note):
            book.die(f"no such note: {target}")
        stem = os.path.splitext(os.path.basename(note))[0]
        return {"note": note, "course": None, "chapter": None, "units": [], "left_out": [],
                "title": f"Exam — {stem}"}
    c = book.find_course(None)
    ch = target or latest_complete_chapter(c)
    if not ch:
        book.die("no chapter is finished yet — name the one to examine: /exam <chapter>")
    return _chapter(c, ch)


def section_key(link):
    """"[[stem#heading|§2.3]]" -> "stem#heading", the form a scheme's `section` takes."""
    return link[2:].rstrip("]").split("|")[0]


def sections_of(r):
    """[(wikilink, unit id or None)] for the sections an exam on `r` may test."""
    out = []
    for link in lesson.heading_links(r["note"]):
        if not r["course"]:
            out.append((link, None))
            continue
        m = re.search(r"\|§([A-Z]?\d+(?:\.\d+)*)\]\]$", link)
        num = m.group(1) if m else ""
        unit = next((u for u in r["units"] if num == u or num.startswith(u + ".")), None)
        if unit:
            out.append((link, unit))
    return out


# ---------------------------------------------------------------- paths and files

def _name(note, attempt):
    stem = os.path.splitext(os.path.basename(note))[0]
    return f"{stem}-exam-{attempt}" if figures.course_of(note) else f"{stem} — Exam {attempt}"


def paths(note, attempt):
    """(paper, scheme, snapshot) of an attempt at an exam on `note`."""
    d = os.path.dirname(os.path.abspath(note))
    name = _name(note, attempt)
    return (os.path.join(d, "exams", name + ".md"), os.path.join(d, ".exams", name + ".json"),
            os.path.join(d, ".exams", name + ".submitted.md"))


def scheme_path(paper):
    paper = os.path.abspath(paper)
    name = os.path.splitext(os.path.basename(paper))[0]
    return os.path.join(os.path.dirname(os.path.dirname(paper)), ".exams", name + ".json")


def snapshot_path(paper):
    return scheme_path(paper)[:-len(".json")] + ".submitted.md"


def attempts(note):
    """{attempt: scheme path} of every exam on `note` that has a paper or a scheme."""
    pat = re.compile(re.escape(_name(note, 0))[:-1] + r"(\d+)\.(md|json)$")
    d = glob.escape(os.path.dirname(os.path.abspath(note)))
    found = {}
    for f in glob.glob(os.path.join(d, "exams", "*")) + glob.glob(os.path.join(d, ".exams", "*")):
        m = pat.fullmatch(os.path.basename(f))
        if m:
            found[int(m.group(1))] = paths(note, int(m.group(1)))[1]
    return found


def next_attempt(note):
    return max(attempts(note), default=0) + 1


def load_scheme(path):
    return book.load_json(path, None)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def find_papers(root, status=None):
    """[(scheme path, scheme)] of every exam under `root`, newest first; hidden folders other than `.exams`
    (.claude, .git, .obsidian) are not searched."""
    found = []
    for sp in glob.glob(os.path.join(glob.escape(root), "**", ".exams", "*.json"), recursive=True):
        s = load_scheme(sp)
        if not isinstance(s, dict) or "paper" not in s:
            continue
        if status is None or s.get("status", "open") == status:
            found.append((sp, s))
    found.sort(key=lambda x: (x[1].get("set") or "", x[1].get("attempt") or 0), reverse=True)
    return found


def section_label(section):
    """"pml1-ch02#2.3 Bayes' rule" -> "§2.3"; a heading without a number is its own label."""
    head = (section or "").split("#", 1)[-1]
    m = re.match(r"([A-Z]?\d+(?:\.\d+)*)\s", head)
    return f"§{m.group(1)}" if m else head


def record(scheme, **fields):
    """Update this paper's entry in its course's state, and so the index. A lesson note has no state."""
    cdir = figures.course_of(os.path.abspath(scheme["covers"]))
    if not cdir or not scheme.get("chapter"):
        return None
    c = book.Course(cdir)
    paper = os.path.relpath(os.path.abspath(scheme["paper"]), cdir)
    entries = c.state.setdefault("exams", [])
    e = next((x for x in entries if x.get("paper") == paper), None)
    if e is None:
        e = {"chapter": scheme["chapter"], "attempt": scheme["attempt"], "paper": paper,
             "set": scheme.get("set"), "status": "open", "score": None, "marks": scheme["marks"]}
        entries.append(e)
    e.update(fields)
    c.save()
    return c


# ---------------------------------------------------------------- commands

def cmd_new(a):
    r = resolve(a.target)
    links = sections_of(r)
    if not links:
        book.die(f"{book.rel(r['note'])} has no ### sections, so there is nothing to examine")
    n = next_attempt(r["note"])
    paper, scheme, _ = paths(r["note"], n)
    b = BUDGET[a.length]
    print(f"PAPER: {book.rel(paper)}")
    print(f"SCHEME: {book.rel(scheme)}")
    print(f"ATTEMPT: {n}")
    print(f"TITLE: {r['title']}")
    print(f"COVERS: {book.rel(r['note'])}")
    if r["chapter"]:
        print(f"CHAPTER: {r['chapter']}   COURSE: {r['course'].slug}")
    for k, sp in sorted(attempts(r["note"]).items()):
        if (load_scheme(sp) or {}).get("status") == "open":
            print(f"OPEN: {book.rel(paths(r['note'], k)[0])}")
    print(f"BUDGET ({a.length}, about {b['minutes']} minutes):")
    for part in "ABC":
        print(f"  Part {part}: {b[part][0]} × {fmt(b[part][1])} marks")
    print(f"  Total: {b['marks']} marks")
    print("SECTIONS (a question's `section` is the link's target, \"<note>#<heading>\""
          + ("; its `unit` is the unit named" if r["course"] else "") + "):")
    for link, unit in links:
        print(f"  {link}" + (f"   unit {unit}" if unit else ""))
    if r["course"]:
        c = r["course"]
        print(f"READ: {c.book['pdf']}")
        for uid in r["units"]:
            u = c.by_id[uid]
            print(f"  {uid}: pages {c.pages(u['start'], u['end'])[0]}")
        if r["left_out"]:
            print(f"LEAVES OUT: {', '.join(r['left_out'])}")


def cmd_check(a):
    paper = os.path.abspath(a.paper)
    sp = scheme_path(paper)
    scheme = load_scheme(sp)
    if not os.path.exists(paper) or scheme is None:
        book.die(f"need both the paper and its scheme: {book.rel(paper)}, {book.rel(sp)}")
    r = resolve(book.rel(os.path.abspath(scheme.get("covers", ""))))
    text = read(paper)
    problems = check(text, scheme, {section_key(link) for link, _ in sections_of(r)})
    if problems:
        print(f"{len(problems)} problem(s) in {book.rel(paper)}:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    new = figures.process(text, paper, existing="")
    if new != text:
        write(paper, new)
    fm, _ = read_frontmatter(text)
    scheme.setdefault("status", "open")
    scheme.setdefault("set", fm.get("set") or time.strftime("%Y-%m-%d"))
    book.save_json(sp, scheme)
    record(scheme)
    print(f"🗒 exam ready: {book.rel(paper)}")


def grade_mc(scheme, parsed):
    """{qid: awarded} for the multiple-choice questions: full marks for exactly the correct set, else 0."""
    return {e["id"]: (float(e["marks"]) if parsed[e["id"]]["ticked"] == set(e.get("correct") or []) else 0.0)
            for e in scheme["questions"] if e["type"] == "mc" and e["id"] in parsed}


IMAGE_RE = re.compile(r"!\[\[([^\]|]+)(?:\|[^\]]*)?\]\]|!\[[^\]]*\]\(([^)]+)\)")


def pick_paper(arg, status="open"):
    """The paper a command acts on: the one named, or the only paper with this status."""
    if arg:
        return os.path.abspath(arg)
    found = find_papers(os.getcwd(), status)
    if not found:
        print(f"no {status} exam paper — name one, or see: exam.py list")
        sys.exit(1)
    if len(found) > 1:
        print(f"{len(found)} {status} exam papers — name the one to use:")
        for _, s in found:
            print(f"  {s['paper']}")
        sys.exit(1)
    return os.path.abspath(found[0][1]["paper"])


def cmd_submit(a):
    paper = pick_paper(a.paper)
    sp = scheme_path(paper)
    scheme = load_scheme(sp)
    if not os.path.exists(paper) or scheme is None:
        book.die(f"need both the paper and its scheme: {book.rel(paper)}, {book.rel(sp)}")
    if scheme.get("status", "open") != "open":
        print(f"already {scheme['status']}: {book.rel(paper)}")
        sys.exit(1)
    text = read(paper)
    qs, problems = parse_paper(text)
    for e in scheme["questions"]:
        name = f"Q{e['id'][1:]}"
        if e["id"] not in qs:
            problems.append(f"{name}: its heading `### {name} ({fmt(e['marks'])} marks)` is not in the paper")
        elif e["type"] == "mc" and not qs[e["id"]]["options"]:
            problems.append(f"{name}: its options (`- [ ] a) …`) are not in the paper")
    if problems:
        print(f"cannot read {book.rel(paper)}; repair it and submit again:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)

    write(snapshot_path(paper), text)
    today = time.strftime("%Y-%m-%d")
    mc = grade_mc(scheme, qs)
    for e in scheme["questions"]:
        q = qs[e["id"]]
        e["text"] = q["text"]
        if e["type"] == "mc":
            e["awarded"] = mc[e["id"]]
            e["chosen"] = sorted(q["ticked"])
    scheme.update(status="submitted", submitted=today)
    book.save_json(sp, scheme)
    write(paper, set_frontmatter(text, status="submitted", submitted=today))
    record(scheme, status="submitted")

    print(f"PAPER: {book.rel(paper)}")
    mcs = [e for e in scheme["questions"] if e["type"] == "mc"]
    if mcs:
        print(f"MULTIPLE CHOICE: {fmt(sum(mc.values()))}/{fmt(sum(float(e['marks']) for e in mcs))}")
        for e in mcs:
            chosen = ", ".join(e["chosen"]) or "none"
            tail = "" if e["awarded"] else f"; correct {', '.join(e['correct'])}"
            print(f"  Q{e['id'][1:]} {fmt(e['awarded'])}/{fmt(e['marks'])} ({chosen}{tail})")
    blank, images = [], []
    for e in scheme["questions"]:
        if e["type"] == "mc":
            continue
        ans = qs[e["id"]]["answer"].strip()
        if not ans:
            blank.append(f"Q{e['id'][1:]}")
        images += [m.group(1) or m.group(2) for m in IMAGE_RE.finditer(ans)]
        print()
        print(f"=== Q{e['id'][1:]} ({fmt(e['marks'])} marks, {e['type']}, {section_label(e.get('section'))}) ===")
        print(f"QUESTION:\n{e['text']}")
        print(f"MODEL ANSWER:\n{e.get('model_answer', '')}")
        print("POINTS:")
        for p in e.get("points") or []:
            print(f"- [{fmt(p['marks'])}] {p['text']}")
        print(f"ANSWER:\n{ans or '(blank)'}")
    if images:
        print()
        print(f"IMAGES: {', '.join(images)}   (embedded in answers; find each in the vault by name and Read it)")
    if blank:
        print(f"BLANK: {', '.join(blank)}")


CALLOUT_START = r"^> \[!(?:success|warning|failure)\] Q{n} — "
SUMMARY_RE = re.compile(r"^> \[!summary\] Result — ")


def quote(text):
    return ["> " + ln if ln.strip() else ">" for ln in text.strip("\n").split("\n")]


def link_of(section):
    return f"[[{section}|{section_label(section)}]]"


def mc_feedback(q):
    lines = [f"**Correct:** {', '.join(x + ')' for x in q['correct'])} {q.get('explanation', '')}".rstrip()]
    chosen = q.get("chosen") or []
    if not chosen:
        lines.append("No answer.")
    for x in chosen:
        if x not in q["correct"]:
            lines.append(f"**You chose {x}):** {(q.get('why_wrong') or {}).get(x, '')}".rstrip())
    return "\n".join(lines)


def callout(q, awarded, feedback, link, regraded=None):
    """The feedback block under a graded question, ending with its `^q<n>` block id."""
    marks = float(q["marks"])
    kind = "success" if awarded >= marks else "failure" if awarded <= 0 else "warning"
    out = [f"> [!{kind}] Q{q['id'][1:]} — {fmt(awarded)}/{fmt(marks)}"] + quote(feedback)
    if regraded:
        out.append(f"> *Regraded {regraded}.*")
    out.append(f"> Tested: {link}")
    if q["type"] != "mc" and q.get("model_answer"):
        out += [">", "> > [!example]- Model answer"] + ["> " + ln for ln in quote(q["model_answer"])]
    out.append(f"^{q['id']}")
    return "\n".join(out)


def summary_block(scheme, revisit):
    qs = scheme["questions"]
    score = sum(float(q.get("awarded", 0)) for q in qs)
    marks = float(scheme["marks"])
    out = [f"> [!summary] Result — {fmt(score)}/{fmt(marks)} ({round(100 * score / marks)}%)"]
    parts = []
    for part in sorted({q["part"] for q in qs}):
        ps = [q for q in qs if q["part"] == part]
        parts.append(f"Part {part} {fmt(sum(float(q.get('awarded', 0)) for q in ps))}/"
                     f"{fmt(sum(float(q['marks']) for q in ps))}")
    out.append("> " + " · ".join(parts))
    lost = {}
    for q in qs:
        if float(q.get("awarded", 0)) < float(q["marks"]):
            lost.setdefault(q.get("section"), []).append(f"Q{q['id'][1:]}")
    if lost:
        out.append("> **Revisit:**")
        for sec, names in lost.items():
            clause = (revisit or {}).get(sec)
            out.append(f"> - {link_of(sec)} ({', '.join(names)})" + (f": {clause}" if clause else ""))
    else:
        out.append("> Full marks.")
    return "\n".join(out)


def shaky_units(scheme):
    """Units whose questions scored under half their marks."""
    got, of = {}, {}
    for q in scheme["questions"]:
        u = q.get("unit")
        if u:
            got[u] = got.get(u, 0.0) + float(q.get("awarded", 0))
            of[u] = of.get(u, 0.0) + float(q["marks"])
    return [u for u in of if got[u] < 0.5 * of[u]]


def _insert_feedback(text, scheme):
    lines = text.split("\n")
    qs, _ = parse_paper(text)
    for q in sorted(scheme["questions"], key=lambda q: qs[q["id"]]["start"], reverse=True):
        p = qs[q["id"]]
        at = p["end"]
        while at > p["start"] + 1 and not lines[at - 1].strip():
            at -= 1
        block = callout(q, float(q["awarded"]), q["feedback"], link_of(q.get("section")))
        lines[at:at] = [""] + block.split("\n") + ([""] if at < len(lines) and lines[at].strip() else [])
    return "\n".join(lines)


def _replace_feedback(text, q, block):
    lines = text.split("\n")
    start_re = re.compile(CALLOUT_START.format(n=q["id"][1:]))
    s = next((i for i, ln in enumerate(lines) if start_re.match(ln)), None)
    e = next((i for i in range(s or 0, len(lines)) if lines[i].strip() == f"^{q['id']}"), None) if s is not None else None
    if s is None or e is None:
        book.die(f"Q{q['id'][1:]}: its feedback block is not in the paper")
    lines[s:e + 1] = block.split("\n")
    return "\n".join(lines)


def _put_summary(text, block):
    lines = text.split("\n")
    s = next((i for i, ln in enumerate(lines) if SUMMARY_RE.match(ln)), None)
    if s is not None:
        e = s
        while e + 1 < len(lines) and lines[e + 1].startswith(">"):
            e += 1
        lines[s:e + 1] = block.split("\n")
    else:
        fm = re.match(r"---\n.*?\n---\n", text, re.S)
        skip = fm.group(0).count("\n") if fm else 0
        t = next((i for i in range(skip, len(lines)) if lines[i].startswith("# ")), skip - 1)
        lines[t + 1:t + 1] = [""] + block.split("\n")
    return "\n".join(lines)


def _refuse(msg):
    print(msg)
    sys.exit(1)


def cmd_grade(a):
    paper = os.path.abspath(a.paper)
    sp = scheme_path(paper)
    scheme = load_scheme(sp)
    if not os.path.exists(paper) or scheme is None:
        book.die(f"need both the paper and its scheme: {book.rel(paper)}, {book.rel(sp)}")
    want = "graded" if a.regrade else "submitted"
    if scheme.get("status", "open") != want:
        _refuse(f"{book.rel(paper)} is {scheme.get('status', 'open')}; "
                + ("only a graded paper can be regraded" if a.regrade else "submit it first: exam.py submit"))
    try:
        grades = json.loads(sys.stdin.read())
        assert isinstance(grades, dict)
    except Exception:
        _refuse("expected the marks as a JSON object on stdin: {\"q7\": {\"awarded\": 3, \"feedback\": \"…\"}}")
    by_id = {q["id"]: q for q in scheme["questions"]}
    entries = {k: v for k, v in grades.items() if k != "revisit"}
    problems = []
    if a.regrade:
        if a.regrade not in by_id:
            problems.append(f"no question {a.regrade}")
        if set(entries) != {a.regrade}:
            problems.append(f"give exactly one entry, for {a.regrade}")
    else:
        for q in scheme["questions"]:
            if q["type"] != "mc" and q["id"] not in entries:
                problems.append(f"Q{q['id'][1:]}: no mark given")
        for k in entries:
            if k not in by_id:
                problems.append(f"no question {k}")
            elif by_id[k]["type"] == "mc":
                problems.append(f"Q{k[1:]}: multiple choice is graded by submit, not here")
    for k, v in entries.items():
        if k not in by_id or not isinstance(v, dict):
            continue
        try:
            aw = float(v.get("awarded"))
        except (TypeError, ValueError):
            problems.append(f"Q{k[1:]}: awarded must be a number")
            continue
        if not 0 <= aw <= float(by_id[k]["marks"]):
            problems.append(f"Q{k[1:]}: awarded {fmt(aw)} is outside 0…{fmt(by_id[k]['marks'])}")
        if by_id[k]["type"] != "mc" and not str(v.get("feedback") or "").strip():
            problems.append(f"Q{k[1:]}: no feedback")
    if problems:
        print("nothing graded:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)

    today = time.strftime("%Y-%m-%d")
    text = read(paper)
    if a.regrade:
        q = by_id[a.regrade]
        old, v = float(q["awarded"]), entries[a.regrade]
        q["awarded"] = float(v["awarded"])
        q["feedback"] = str(v.get("feedback") or "").strip() or q.get("feedback") or mc_feedback(q)
        q["regraded"] = f"{today}: {fmt(old)} → {fmt(q['awarded'])}"
        text = _replace_feedback(text, q, callout(q, q["awarded"], q["feedback"], link_of(q.get("section")),
                                                  q["regraded"]))
    else:
        for q in scheme["questions"]:
            if q["type"] == "mc":
                q["feedback"] = mc_feedback(q)
            else:
                q["awarded"] = float(entries[q["id"]]["awarded"])
                q["feedback"] = str(entries[q["id"]]["feedback"]).strip()
        text = _insert_feedback(text, scheme)
    if "revisit" in grades:
        scheme["revisit"] = grades["revisit"]
    score = sum(float(q["awarded"]) for q in scheme["questions"])
    scheme.update(status="graded", score=score, misses=[q["id"] for q in scheme["questions"]
                                                        if float(q["awarded"]) < float(q["marks"])])
    scheme.setdefault("graded", today)
    text = _put_summary(text, summary_block(scheme, scheme.get("revisit")))
    text = set_frontmatter(text, status="graded", score=fmt(score), graded=scheme["graded"])
    write(paper, text)
    book.save_json(sp, scheme)

    shaky = []
    c = record(scheme, status="graded", score=score)
    if c:
        for u in shaky_units(scheme):
            if c.status(u) == "done":
                c.state["status"][u] = {"s": "shaky", "at": today}
                shaky.append(u)
        if shaky:
            c.save()
    pct = round(100 * score / float(scheme["marks"]))
    print(f"🗒 exam graded: {fmt(score)}/{fmt(scheme['marks'])} ({pct}%)")
    print(summary_block(scheme, scheme.get("revisit")).split("\n")[1][2:])
    if shaky:
        print(f"SHAKY: {', '.join(shaky)}")


def main():
    p = argparse.ArgumentParser(prog="exam.py", description="Exam papers on a course chapter or a lesson note.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("new")
    s.add_argument("target", nargs="?")
    s.add_argument("--length", choices=sorted(BUDGET), required=True)
    s.set_defaults(fn=cmd_new)
    s = sub.add_parser("check")
    s.add_argument("paper")
    s.set_defaults(fn=cmd_check)
    s = sub.add_parser("submit")
    s.add_argument("paper", nargs="?")
    s.set_defaults(fn=cmd_submit)
    s = sub.add_parser("grade")
    s.add_argument("paper")
    s.add_argument("--regrade", metavar="Q", type=str.lower)
    s.set_defaults(fn=cmd_grade)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
