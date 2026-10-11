#!/usr/bin/env python3
"""
exam — set, submit and grade an exam paper on a course chapter or a lesson note.

The teacher writes the paper (markdown, in an `exams/` folder beside the note it tests) and its marking scheme
(JSON, in the hidden `.exams/` folder beside that). This script does what must be exact: paths, validation,
reading the filled-in paper, multiple-choice grading, feedback callouts, totals, and the course's state.
"""
import re

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
        qs[qid] = {"part": part, "marks": marks, "options": options, "ticked": ticked, "answer": answer,
                   "has_answer": at is not None, "start": i, "end": end}
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
