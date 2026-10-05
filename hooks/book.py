#!/usr/bin/env python3
"""
book — the page map and the progress record of a course that follows a textbook (PDF).

The teacher never loads the whole book. This script maps the book once (outline entry -> page range), keeps
the syllabus and what has been studied, and tells the teacher which pages to Read for a section, an equation
or an exercise. Nothing of the book reaches the context except the pages the teacher then Reads.

    book.py new <book.pdf> [--name SLUG] [--title T] [--dir DIR] [--toc FILE [--offset N]] [--force]
                                     map the book and create the course (courses/<slug>/ by default)
    book.py select <spec>... [--add | --remove]
                                     choose the syllabus: all | unstarred | 2 | 2.3 | 2.1-2.6 | 3-5 ...
    book.py toc [CHAPTER] [--all]    the syllabus with status marks (--all: every section of the book)
    book.py next                     the next unit to study, the pages to Read, the chapter note
    book.py section <id>             the same for a given section
    book.py done <id> [--status done|shaky|skipped|todo]
                                     record a unit's outcome; prints what comes next
    book.py find <eq|ex|fig|table|thm|page> <id>
                                     where the book's Equation 2.51 / Exercise 2.3 / printed page 45 is
    book.py exercise <id> [--hint N] [--status open|attempted|solved|quizzed|shown]
                                     locate an exercise, show and update its record
    book.py exercises [CHAPTER]      the exercises of a chapter with their records
    book.py assess <id>... [--clear] mark exercises as assessed coursework (never quizzed, never solved)
    book.py set <title|goal|solutions|offset> <value>
    book.py status                   progress in a few lines

Every command takes --course DIR; without it the course used last is meant.

A course directory:
    <slug>.md                 the visible index: syllabus, progress, links to the chapter notes (generated)
    <slug>-ch02.md            one lesson note per chapter (the md-log mirror), created when first studied
    <slug>-ch02-exercises.md  exercise help for that chapter
    .course/book.json         the page map (regenerate with `new --force`)
    .course/state.json        syllabus, unit status, exercise records, settings
    .checkpoints/             lesson checkpoints, as for any lesson note

Needs poppler (pdfinfo, pdftotext) and, to read the PDF outline, mutool. No Python dependencies.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from urllib.parse import unquote

HERE = os.path.dirname(os.path.abspath(__file__))
CLAUDE_DIR = os.path.dirname(HERE)
POINTER = os.path.join(CLAUDE_DIR, "md-log-state", "course.json")  # the course used last
READ_CHUNK = 20  # the Read tool takes at most this many PDF pages per call
SOLUTIONS = ("never", "after-attempt", "on-request")
UNIT_STATUS = ("todo", "done", "shaky", "skipped")
EXERCISE_STATUS = ("open", "attempted", "solved", "quizzed", "shown")
MARK = {"todo": "·", "done": "✓", "shaky": "⚠", "skipped": "–"}
EXERCISES_RE = re.compile(r"^(exercises?|problems?|practice problems|review (questions|exercises|problems)|"
                          r"exercises and \w+)\s*$", re.I)
# hyperref-style anchor names per kind ("equation.2.3.51", "exercisectr.2.4", "figure.2.7")
ANCHORS = {
    "eq": ("equation", "eq"),
    "ex": ("exercise", "exercisectr", "exer", "problem", "prob"),
    "fig": ("figure", "fig"),
    "table": ("table", "tab"),
    "thm": ("thm", "theorem", "lemma", "lem", "cor", "corollary", "prop", "proposition", "definition", "defn"),
}
TEXT_PATTERNS = {
    "eq": [r"\({id}\)\s*$"],
    "ex": [r"^\s*(?:Exercise|Problem|Ex\.)\s+{id}\b", r"^\s*{id}[.\s]"],
    "fig": [r"^\s*(?:Figure|Fig\.)\s+{id}[:.]"],
    "table": [r"^\s*Table\s+{id}[:.]"],
    "thm": [r"^\s*(?:Theorem|Lemma|Corollary|Proposition|Definition)\s+{id}\b"],
}


def die(msg, code=2):
    print(msg, file=sys.stderr)
    sys.exit(code)


def run(cmd):
    try:
        p = subprocess.run(cmd, check=False, capture_output=True, text=True, errors="replace", timeout=120)
    except Exception:
        return None
    return p.stdout if p.returncode == 0 else None


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def natural(s):
    """Sort key that puts 2.10 after 2.9."""
    return [(0, int(x), "") if x.isdigit() else (1, 0, x) for x in re.split(r"[.:]", s)]


def rel(path):
    r = os.path.relpath(path)
    return path if r.startswith("..") else r


# ---------------------------------------------------------------- reading the PDF

def pdf_info(pdf):
    out = run(["pdfinfo", pdf])
    if out is None:
        die("pdfinfo could not read the file (is poppler installed, and is this a PDF?): " + pdf)
    info = {"pages": 0, "height": None, "title": ""}
    for ln in out.splitlines():
        key, _, val = ln.partition(":")
        val = val.strip()
        if key == "Pages":
            info["pages"] = int(val)
        elif key == "Title":
            info["title"] = val
        elif key == "Page size":
            m = re.match(r"([\d.]+) x ([\d.]+)", val)
            if m:
                info["height"] = float(m.group(2))
    return info


def named_dests(pdf):
    """{name: (page, y)} from `pdfinfo -dests`; y is in points from the bottom of the page, or None."""
    out = run(["pdfinfo", "-dests", pdf]) or ""
    dests = {}
    for ln in out.splitlines():
        m = re.match(r'^\s*(\d+)\s+\[\s*(\w+)([^\]]*)\]\s+"(.*)"\s*$', ln)
        if not m:
            continue
        nums = re.findall(r"-?\d+(?:\.\d+)?", m.group(3))
        y = None
        if m.group(2) == "XYZ" and len(nums) >= 2:
            y = float(nums[1])
        elif m.group(2) in ("FitH", "FitBH") and nums:
            y = float(nums[0])
        dests[m.group(4)] = (int(m.group(1)), y)
    return dests


def read_outline(pdf, dests):
    """[(depth, title, page, y, dest name)] from `mutool show <pdf> outline`, or None without mutool/outline."""
    out = run(["mutool", "show", pdf, "outline"])
    if not out:
        return None
    rows = []
    for ln in out.splitlines():
        m = re.match(r'^[|+\-]?(\t*)"(.*)"\t#?(.*)$', ln)
        if not m:
            continue
        target = m.group(3)
        page, y, name = None, None, ""
        nd = re.match(r"nameddest=(.*)$", target)
        pg = re.match(r"page=(\d+)", target)
        old = re.match(r"(\d+)(?:,|$)", target)
        if nd:
            name = unquote(nd.group(1))
            page, y = dests.get(name, dests.get(nd.group(1), (None, None)))
        elif pg:
            page = int(pg.group(1))  # the position on the page is in viewer coordinates: not used
        elif old:
            page = int(old.group(1))
        rows.append((len(m.group(1)), m.group(2), page, y, name))
    if not rows:
        return None
    base = min(r[0] for r in rows)
    return [(d - base, t, p, y, n) for d, t, p, y, n in rows]


def read_toc_file(path, offset):
    """A contents list written by hand when the PDF has no outline: `<level>\\t<title>\\t<printed page>` per
    line (level 1 = chapter, 2 = section, 3 = subsection); `=N` in the page column is a literal PDF page."""
    rows = []
    with open(path, encoding="utf-8") as f:
        for n, ln in enumerate(f, 1):
            if not ln.strip() or ln.lstrip().startswith("#"):
                continue
            parts = [p.strip() for p in ln.rstrip("\n").split("\t")]
            if len(parts) != 3 or not parts[0].isdigit() or not re.fullmatch(r"=?\d+", parts[2]):
                die(f"{path}:{n}: expected <level>TAB<title>TAB<page>, got: {ln.strip()}")
            page = int(parts[2][1:]) if parts[2].startswith("=") else int(parts[2]) + offset
            rows.append((int(parts[0]) - 1, parts[1], page, None, ""))
    return rows


def split_id(title):
    """('2.3', "Bayes' rule", keyword) from "2.3 Bayes' rule" / "Chapter 2: ..." / "A Notation" / "II Linear Models"."""
    t = title.strip()
    kw = ""
    m = re.match(r"^(chapter|appendix|part|section)\s+", t, re.I)
    if m:
        kw, t = m.group(1).lower(), t[m.end():]
    m = re.match(r"^(\d+(?:\.\d+)*|[A-Z](?:\.\d+)+|[A-Z]|[IVXLC]+)\s*[.:)–—-]?\s+(\S.*)$", t)
    if m and not (re.fullmatch(r"\d+", m.group(1)) and int(m.group(1)) > 200):
        return m.group(1), m.group(2), kw
    m = re.match(r"^(\d+|[A-Z]|[IVXLC]+)$", t)
    if m and kw:
        return m.group(1), title.strip(), kw
    return None, title.strip(), kw


def clean_title(t):
    return re.sub(r"\s+", " ", t.replace("``", "“").replace("''", "”")).strip()


def build_book(rows, pdf, info, dests, offset):
    """Turn outline rows into entries with ids, levels and page ranges."""
    entries, unresolved = [], 0
    for depth, title, page, y, dest in rows:
        if not page or page < 1 or page > info["pages"]:
            unresolved += 1
            continue
        id_, name, kw = split_id(title)
        starred = name.rstrip().endswith("*")
        entries.append({"id": id_, "title": clean_title(name.rstrip(" *")), "raw": clean_title(title), "depth": depth,
                        "start": page, "y": y, "dest": dest, "kw": kw, "starred": starred})
    if not entries:
        return None, unresolved

    def children(i):
        d = entries[i]["depth"]
        out = []
        for e in entries[i + 1:]:
            if e["depth"] <= d:
                break
            if e["depth"] == d + 1:
                out.append(e)
        return out

    generated = sum(1 for e in entries if e["id"] and e["id"][0].isdigit()) < 3
    if generated:
        # an outline without section numbers: number the entries by their position in the tree
        counters = []
        for e in entries:
            del counters[e["depth"] + 1:]
            while len(counters) <= e["depth"]:
                counters.append(0)
            counters[e["depth"]] += 1
            e["id"] = ".".join(str(c) for c in counters[:e["depth"] + 1])
            e["title"] = clean_title(e["raw"].rstrip(" *"))
            e["kind"] = "chapter" if e["depth"] == 0 else "section" if e["depth"] == 1 else "subsection"
            e["level"] = e["depth"] + 1
    else:
        for i, e in enumerate(entries):
            id_ = e["id"]
            e["kind"] = None
            if id_ and re.fullmatch(r"[A-Z]|[IVXLC]+", id_):
                kids = [k["id"] or "" for k in children(i)]
                if e["kw"] == "part" or e["dest"].startswith("part") or any(re.fullmatch(r"\d+", k) for k in kids):
                    e["kind"] = "part"
                elif re.fullmatch(r"[A-Z]", id_) and (e["kw"] == "appendix" or "appendix" in e["dest"].lower()
                                                     or any(k.startswith(id_ + ".") for k in kids)):
                    e["kind"] = "appendix"
                else:  # "A Tour of ..." is a title, not appendix A
                    e["id"], e["title"] = None, clean_title(e["raw"].rstrip(" *"))
        stack = []  # the ancestors of the current entry in the outline tree
        for e in entries:
            while stack and stack[-1]["depth"] >= e["depth"]:
                stack.pop()
            parent = stack[-1] if stack else None
            if e["kind"] == "part":
                e["level"] = 0
            elif e["kind"] == "appendix":
                e["level"] = 1
            elif e["id"]:
                e["level"] = 1 + e["id"].count(".")
                e["kind"] = "chapter" if e["level"] == 1 else "section" if e["level"] == 2 else "subsection"
            else:
                e["kind"] = "other"
                e["level"] = 1 if parent is None or parent["kind"] == "part" else parent["level"] + 1
            stack.append(e)

    # the chapter each entry belongs to; ids for unnumbered entries ("preface", "3:summary")
    chapter, seen = None, set()
    for e in entries:
        if e["level"] <= 1:
            chapter = e["id"] if e["kind"] in ("chapter", "appendix") else None
        e["chapter"] = chapter
        if not e["id"]:
            e["id"] = (f"{chapter}:" if chapter and e["level"] > 1 else "") + (slugify(e["title"]) or "untitled")
        base, n = e["id"], 2
        while e["id"] in seen:
            e["id"] = f"{base}-{n}"
            n += 1
        seen.add(e["id"])
        e["exercises"] = bool(EXERCISES_RE.match(e["title"]))

    # page ranges: an entry runs to the next entry at its level or above
    top = (info["height"] or 0) * 0.88
    for i, e in enumerate(entries):
        nxt = next((x for x in entries[i + 1:] if x["level"] <= e["level"] and x["start"] >= e["start"]), None)
        e["mid_start"] = bool(e["y"] is not None and top and e["y"] < top)
        if nxt is None:
            e["end"], e["mid_end"] = info["pages"], False
        elif nxt["level"] <= 1 or (nxt["y"] is not None and top and nxt["y"] >= top):
            e["end"], e["mid_end"] = max(nxt["start"] - 1, e["start"]), False  # the next entry opens a page
        else:
            e["end"], e["mid_end"] = nxt["start"], True  # the page is shared (or we cannot tell): include it
    for e in entries:
        for k in ("depth", "y", "dest", "kw", "raw"):
            e.pop(k, None)

    labels = None  # printed page labels, from hyperref's page.<label> anchors
    page_dests = {p: n[5:] for n, (p, _) in dests.items() if n.startswith("page.")}
    if len(page_dests) >= info["pages"] * 0.9:
        labels = [page_dests.get(p, "") for p in range(1, info["pages"] + 1)]
    return {"pdf": pdf, "pages": info["pages"], "labels": labels, "offset": offset, "generated_ids": generated,
            "built": time.strftime("%Y-%m-%d %H:%M"), "entries": entries}, unresolved


# ---------------------------------------------------------------- the course

class Course:
    def __init__(self, cdir):
        self.dir = cdir
        self.book = load_json(os.path.join(cdir, ".course", "book.json"), None)
        self.state = load_json(os.path.join(cdir, ".course", "state.json"), None)
        if not self.book or self.state is None:
            die(f"not a course directory (no .course/book.json): {cdir}")
        self.entries = self.book["entries"]
        self.by_id = {e["id"]: e for e in self.entries}
        self.slug = self.state["slug"]

    def save(self):
        save_json(os.path.join(self.dir, ".course", "state.json"), self.state)
        with open(os.path.join(self.dir, self.slug + ".md"), "w", encoding="utf-8") as f:
            f.write(render_index(self))

    # --- structure
    def chapters(self, appendices=False):
        kinds = ("chapter", "appendix") if appendices else ("chapter",)
        return [e for e in self.entries if e["kind"] in kinds]

    def units_of(self, ch):
        """The study units of a chapter: its sections, or the chapter itself when it has none."""
        secs = [e for e in self.entries if e["level"] == 2 and e["chapter"] == ch["id"] and not e["exercises"]]
        return secs or [ch]

    def units(self, appendices=False):
        return [u for ch in self.chapters(appendices) for u in self.units_of(ch)]

    def part_of(self, ch):
        part = None
        for e in self.entries:
            if e["kind"] == "part":
                part = e
            elif e is ch:
                return part
        return None

    def optional(self, u):
        ch = self.by_id.get(u["chapter"]) if u.get("chapter") else None
        part = self.part_of(ch) if ch else None
        return bool(u["starred"] or (ch and ch["starred"]) or (part and part["starred"]))

    def subsections(self, u):
        return [e for e in self.entries if e["level"] == u["level"] + 1 and e["id"].startswith(u["id"] + ".")]

    def exercise_sections(self, ch_id):
        return [e for e in self.entries if e["exercises"] and e["chapter"] == ch_id]

    # --- pages
    def label(self, page):
        if self.book.get("labels"):
            return self.book["labels"][page - 1] or None
        off = self.book.get("offset")
        return str(page - off) if off is not None and page - off >= 1 else None

    def pdf_page(self, label):
        labels = self.book.get("labels")
        if labels:
            return labels.index(label) + 1 if label in labels else None
        if self.book.get("offset") is not None and label.isdigit():
            return int(label) + self.book["offset"]
        return None

    def pages(self, start, end):
        a, b = self.label(start), self.label(end)
        n = end - start + 1
        printed = ""
        if a and b:
            printed = f"printed p. {a}" if a == b else f"printed pp. {a}–{b}"
        chunks = [str(s) if min(s + READ_CHUNK - 1, end) == s else f"{s}-{min(s + READ_CHUNK - 1, end)}"
                  for s in range(start, end + 1, READ_CHUNK)]
        return ", ".join(chunks), "; ".join(x for x in (printed, f"{n} page{'s' if n != 1 else ''}") if x)

    def cite(self, start, end):
        a, b = self.label(start), self.label(end)
        if not a or not b:
            return f"PDF p. {start}" if start == end else f"PDF pp. {start}–{end}"
        return f"p. {a}" if a == b else f"pp. {a}–{b}"

    # --- progress
    def status(self, uid):
        return (self.state["status"].get(uid) or {}).get("s", "todo")

    def syllabus(self):
        chosen = set(self.state.get("syllabus") or [])
        return [u for u in self.units(appendices=True) if u["id"] in chosen]

    def next_unit(self):
        return next((u for u in self.syllabus() if self.status(u["id"]) == "todo"), None)

    def note(self, ch_id, exercises=False):
        tag = f"ch{int(ch_id):02d}" if ch_id.isdigit() else f"app{ch_id}" if re.fullmatch(r"[A-Z]", ch_id) else slugify(ch_id)
        return os.path.join(self.dir, f"{self.slug}-{tag}{'-exercises' if exercises else ''}.md")


def find_course(arg):
    cands = []
    if arg:
        p = os.path.abspath(os.path.expanduser(arg))
        cands += [os.path.dirname(p) if os.path.isfile(p) else p, os.path.join(os.getcwd(), "courses", arg)]
    else:
        last = load_json(POINTER, {}).get("course")
        if last:
            cands.append(last)
        root = os.path.join(os.getcwd(), "courses")
        if os.path.isdir(root):
            found = [os.path.join(root, d) for d in sorted(os.listdir(root))
                     if os.path.exists(os.path.join(root, d, ".course", "book.json"))]
            if len(found) == 1:
                cands.append(found[0])
    for c in cands:
        if os.path.exists(os.path.join(c, ".course", "book.json")):
            save_json(POINTER, {"course": c})
            return Course(c)
    die("no course found" + (f" at {arg}" if arg else " — create one with: book.py new <book.pdf>, or pass --course DIR"))


def render_index(c):
    st = c.state
    title = st.get("title") or c.slug
    syl = c.syllabus()
    done = sum(1 for u in syl if c.status(u["id"]) in ("done", "shaky"))
    out = [f"# {title}", "",
           "%% Generated by .claude/hooks/book.py from .course/state.json. Edits here are overwritten. %%", "",
           f"Source: `{os.path.basename(c.book['pdf'])}` · {c.book['pages']} pages · "
           f"{done} of {len(syl)} sections studied · full solutions: {st.get('solutions', 'after-attempt')}"]
    if st.get("goal"):
        out += ["", f"Goal: {st['goal']}"]
    out += ["", "## Syllabus"]
    if not syl:
        out += ["", "Not selected yet."]
    by_ch = {}
    for u in syl:
        by_ch.setdefault(u["chapter"] or u["id"], []).append(u)
    for ch_id, us in by_ch.items():
        ch = c.by_id[ch_id]
        note = os.path.splitext(os.path.basename(c.note(ch_id)))[0]
        head = f"{ch['id']} {ch['title']}" if ch["kind"] in ("chapter", "appendix") and not c.book["generated_ids"] else ch["title"]
        out += ["", f"### {head}", "", f"Lesson: [[{note}]]", ""]
        for u in us:
            s = c.status(u["id"])
            box = {"todo": "[ ]", "done": "[x]", "shaky": "[x]", "skipped": "[-]"}[s]
            name = u["title"] if u is ch or c.book["generated_ids"] else f"{u['id']} {u['title']}"
            tail = " — shaky, revisit" if s == "shaky" else " — skipped" if s == "skipped" else ""
            out.append(f"- {box} {name} · {c.cite(u['start'], u['end'])}{tail}")
    ex = st.get("exercises") or {}
    if ex:
        out += ["", "## Exercises", "", "| Exercise | Status | Hints used | Assessed |", "|---|---|---|---|"]
        for eid in sorted(ex, key=natural):
            r = ex[eid]
            out.append(f"| {eid} | {r.get('status', 'open')} | {r.get('hints', 0)} | {'yes' if r.get('assessed') else ''} |")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- locating things

def anchor(dests, kind, id_):
    """Page of the book's Equation/Figure/Exercise <id> from its hyperref anchor, or None."""
    parts = id_.split(".")
    exact, loose = [], []
    for name, (page, y) in dests.items():
        head, _, rest = name.partition(".")
        if head.lower() not in ANCHORS[kind] or not rest:
            continue
        rp = rest.split(".")
        if rest == id_:
            exact.append((page, y))
        elif len(rp) > len(parts) and rp[0] == parts[0] and rp[-1] == parts[-1]:
            loose.append((page, y))  # "equation.2.3.51" is Equation (2.51) when the counter runs per chapter
    if exact:
        return exact[0]
    return loose[0] if len(loose) == 1 else None


def text_search(pdf, kind, id_, ranges):
    for start, end in ranges:
        out = run(["pdftotext", "-f", str(start), "-l", str(end), pdf, "-"])
        if not out:
            continue
        pages = out.split("\f")
        for pat in TEXT_PATTERNS[kind]:
            rx = re.compile(pat.format(id=re.escape(id_)), re.M)
            for i, text in enumerate(pages):
                if rx.search(text):
                    return start + i
    return None


def locate(c, kind, id_):
    """(page, how) for an equation / exercise / figure / table / theorem id."""
    dests = named_dests(c.book["pdf"])
    hit = anchor(dests, kind, id_)
    if hit:
        return hit[0], "anchor"
    ch = c.by_id.get(id_.split(".")[0])
    ranges = []
    if ch:
        if kind == "ex":
            ranges += [(e["start"], e["end"]) for e in c.exercise_sections(ch["id"])]
        ranges.append((ch["start"], ch["end"]))
    else:
        ranges.append((1, c.book["pages"]))
    page = text_search(c.book["pdf"], kind, id_, ranges)
    return (page, "text search") if page else (None, None)


def chapter_exercises(c, ch_id):
    """[(id, page)] of a chapter's exercises, from anchors or, failing that, from the text."""
    dests = named_dests(c.book["pdf"])
    found = {}
    for name, (page, y) in dests.items():
        head, _, rest = name.partition(".")
        if head.lower() in ANCHORS["ex"] and rest.startswith(ch_id + ".") and re.fullmatch(r"[\w.]+", rest):
            found[rest] = (page, -(y or 0))
    if not found:
        for sec in c.exercise_sections(ch_id):
            out = run(["pdftotext", "-f", str(sec["start"]), "-l", str(sec["end"]), c.book["pdf"], "-"]) or ""
            for i, text in enumerate(out.split("\f")):
                for m in re.finditer(rf"^\s*(?:Exercise|Problem)\s+({re.escape(ch_id)}\.\d+)\b", text, re.M):
                    found.setdefault(m.group(1), (sec["start"] + i, m.start()))
    return [(k, v[0]) for k, v in sorted(found.items(), key=lambda kv: kv[1])]


# ---------------------------------------------------------------- output

def describe_unit(c, u, heading="UNIT"):
    ch = c.by_id.get(u["chapter"]) if u.get("chapter") else None
    ch = ch or u
    us = c.units_of(ch)
    start = u["start"]
    lines = [f"{heading}: {u['id']} {u['title']}" + (f" — chapter {ch['id']} \"{ch['title']}\"" if ch is not u else "")
             + ("  [optional in the book]" if c.optional(u) else "")
             + (f"  [status: {c.status(u['id'])}]" if c.status(u["id"]) != "todo" else "")]
    opening = u is us[0] and ch is not u and (ch["start"] < u["start"] or u["mid_start"])
    if opening:
        start = ch["start"]
    rng, extra = c.pages(start, u["end"])
    lines.append(f"READ: {c.book['pdf']}")
    lines.append(f"  pages: {rng}   ({extra})")
    if opening:
        lines.append(f"  first unit of the chapter: the range includes the chapter opening (from PDF page {ch['start']})")
    elif u["mid_start"]:
        lines.append(f"  the section begins partway down PDF page {u['start']}; what is above it belongs to the previous section")
    if u["mid_end"]:
        lines.append(f"  the section ends partway down PDF page {u['end']}; what follows belongs to the next section")
    subs = c.subsections(u)
    if subs:
        lines.append("SUBSECTIONS: " + " · ".join(
            f"{s['id']} {s['title']}{' *' if s['starred'] else ''} (PDF {s['start']})" for s in subs)
            + ("   (* = optional in the book)" if any(s["starred"] for s in subs) else ""))
    lines.append(f"CITE AS: §{u['id']}, {c.cite(start, u['end'])}")
    note = c.note(ch["id"])
    if os.path.exists(note) and os.path.getsize(note):
        with open(note, encoding="utf-8") as f:
            n = sum(1 for _ in f)
        lines.append(f"NOTE: {rel(note)}  (exists, {n} lines — resume it)")
    else:
        lines.append(f"NOTE: {rel(note)}  (new — this chapter has no lesson yet)")
    chosen = {x["id"] for x in c.syllabus()}
    marks = []
    for x in us:
        if x["id"] in chosen or x is u:
            marks.append(("→" if x is u else MARK[c.status(x["id"])]) + " " + x["id"])
    left_out = [x["id"] for x in us if x["id"] not in chosen and x is not u]
    lines.append(f"CHAPTER {ch['id']} UNITS: " + "  ".join(marks)
                 + (f"   (not in the syllabus: {', '.join(left_out)})" if left_out else ""))
    exs = c.exercise_sections(ch["id"])
    if exs:
        lines.append("CHAPTER EXERCISES: " + "; ".join(
            f"{e['id']} {e['title']}, PDF pages {c.pages(e['start'], e['end'])[0]}" for e in exs))
    if c.state.get("goal"):
        lines.append(f"COURSE GOAL: {c.state['goal']}")
    return "\n".join(lines)


def progress_line(c):
    syl = c.syllabus()
    n = {s: sum(1 for u in syl if c.status(u["id"]) == s) for s in UNIT_STATUS}
    return (f"{len(syl)} units in the syllabus: {n['done']} done, {n['shaky']} shaky, {n['skipped']} skipped, "
            f"{n['todo']} to do")


# ---------------------------------------------------------------- commands

def cmd_new(a):
    pdf = os.path.abspath(os.path.expanduser(a.pdf))
    if not os.path.isfile(pdf):
        die(f"no such file: {pdf}")
    info = pdf_info(pdf)
    dests = named_dests(pdf)
    title = a.title or info["title"]
    slug = slugify(a.name or title or os.path.splitext(os.path.basename(pdf))[0]) or "course"
    cdir = os.path.abspath(os.path.expanduser(a.dir)) if a.dir else os.path.join(os.getcwd(), "courses", slug)
    exists = os.path.exists(os.path.join(cdir, ".course", "book.json"))
    if exists and not a.force:
        die(f"a course already exists at {rel(cdir)} — use --force to map the book again (progress is kept)")
    offset = a.offset if a.offset is not None else (0 if a.toc else None)
    rows = read_toc_file(a.toc, offset) if a.toc else read_outline(pdf, dests)
    book, unresolved = build_book(rows, pdf, info, dests, offset) if rows else (None, 0)
    if not book:
        print(f"NO OUTLINE in {pdf} ({info['pages']} PDF pages)"
              + ("" if shutil.which("mutool") else " — mutool is not installed, so the outline could not be read"))
        print("Build the map by hand:\n"
              "  1. Read the contents pages (try PDF pages 1-15) and find the offset between printed and PDF page\n"
              "     numbers: offset = (PDF page number of the page printed '1') - 1.\n"
              "  2. Write the contents to a file under /tmp/learn-book/, one entry per line, tab-separated:\n"
              "       <level>TAB<title with its number, e.g. 2.3 Bayes' rule>TAB<printed page>\n"
              "     level 1 = chapter, 2 = section, 3 = subsection; write =N for a literal PDF page (front matter).\n"
              f"  3. Run: book.py new \"{pdf}\" --toc <file> --offset <offset>" + (f" --name {a.name}" if a.name else ""))
        sys.exit(3)
    save_json(os.path.join(cdir, ".course", "book.json"), book)
    state = load_json(os.path.join(cdir, ".course", "state.json"), None) or {
        "slug": slug, "title": title, "goal": "", "solutions": "after-attempt", "syllabus": [], "status": {},
        "exercises": {}, "created": time.strftime("%Y-%m-%d")}
    if a.title:
        state["title"] = a.title
    save_json(os.path.join(cdir, ".course", "state.json"), state)
    save_json(POINTER, {"course": cdir})
    c = Course(cdir)
    c.save()

    print(f"🗒 course {'remapped' if exists else 'created'}: {rel(cdir)}  (index: {rel(os.path.join(cdir, c.slug + '.md'))})")
    print(f"BOOK: {pdf} · {info['pages']} PDF pages · {len(c.entries)} outline entries"
          + (f" · {unresolved} entries without a page were dropped" if unresolved else ""))
    if state.get("title"):
        print(f"TITLE: {state['title']}")
    else:
        print("TITLE: unknown — Read PDF pages 1-3 for the title page, then: book.py set title \"<title>\"")
    first = c.pdf_page("1")
    if first:
        print(f"PAGE NUMBERS: printed page 1 is PDF page {first}; every command prints both")
    else:
        print("PAGE NUMBERS: printed page numbers are unknown. Find the PDF page that is printed '1' and run: "
              "book.py set offset <that PDF page - 1>")
    if book["generated_ids"]:
        print("IDS: the outline has no section numbers; ids below are positions in the outline, not the book's numbers")
    chs = c.chapters(appendices=True)
    first_ch = chs[0]["start"] if chs else 1
    front = [e for e in c.entries if e["level"] <= 1 and e["kind"] == "other" and e["start"] < first_ch]
    if front:
        print("FRONT MATTER: " + " · ".join(f"{e['title']} (PDF pages {c.pages(e['start'], e['end'])[0]})" for e in front))
    elif first_ch > 1:
        print(f"FRONT MATTER: PDF pages 1-{first_ch - 1} (no outline entries)")
    print("CHAPTERS (PDF pages; * = marked optional by the book):")
    part = None
    for e in c.entries:
        if e["kind"] == "part":
            part = e
            print(f"  Part {e['id']} {e['title']}{' *' if e['starred'] else ''}")
        elif e["kind"] in ("chapter", "appendix"):
            us = c.units_of(e)
            n = 0 if us == [e] else len(us)
            opt = sum(1 for u in us if u["starred"]) if n else 0
            ex = " · has exercises" if c.exercise_sections(e["id"]) else ""
            print(f"  {'  ' if part else ''}{e['id']:>3} {e['title']}{' *' if e['starred'] else ''}  "
                  f"{e['start']}-{e['end']} · {n} sections" + (f" ({opt} optional)" if opt else "") + ex)
    units = c.units()
    opt = sum(1 for u in units if c.optional(u))
    print(f"UNITS: {len(units)} sections in {len(c.chapters())} chapters" + (f"; {opt} are optional (starred)" if opt else ""))
    if state.get("syllabus"):
        print("SYLLABUS: kept — " + progress_line(c))
    else:
        print("SYLLABUS: not selected yet — book.py select all | unstarred | <chapters, sections, ranges>")


def expand_spec(c, tokens):
    units = c.units(appendices=True)
    order = [u["id"] for u in units]

    def ids_of(tok):
        e = c.by_id.get(tok)
        if e is None:
            return None
        if e["id"] in order:
            return [e["id"]]
        if e["kind"] in ("chapter", "appendix"):
            return [u["id"] for u in c.units_of(e)]
        if e["kind"] == "part":
            return [u["id"] for ch in c.chapters() if c.part_of(ch) is e for u in c.units_of(ch)]
        if e["exercises"]:
            die(f"{tok} is an exercises section, not a unit of study")
        parent = next((u for u in units if e["id"].startswith(u["id"] + ".")), None)  # a subsection
        if parent:
            print(f"note: {tok} is part of unit {parent['id']}; the whole unit is selected", file=sys.stderr)
            return [parent["id"]]
        return None

    chosen = []
    for tok in [t for raw in tokens for t in raw.split(",") if t]:
        if tok == "all":
            chosen += [u["id"] for u in c.units()]
        elif tok == "unstarred":
            chosen += [u["id"] for u in c.units() if not c.optional(u)]
        elif ids_of(tok) is not None:
            chosen += ids_of(tok)
        else:
            m = re.fullmatch(r"([\w.:]+)-([\w.:]+)", tok)
            a, b = (ids_of(m.group(1)), ids_of(m.group(2))) if m else (None, None)
            if not a or not b:
                die(f"unknown section, chapter or range: {tok}   (see: book.py toc --all)")
            i, j = order.index(a[0]), order.index(b[-1])
            if j < i:
                die(f"range runs backwards: {tok}")
            chosen += order[i:j + 1]
    keep = set(chosen)
    return [i for i in order if i in keep]


def cmd_select(a):
    c = find_course(a.course)
    ids = expand_spec(c, a.spec)
    current = c.state.get("syllabus") or []
    if a.add:
        ids = [u["id"] for u in c.units(appendices=True) if u["id"] in set(current) | set(ids)]
    elif a.remove:
        ids = [i for i in current if i not in set(ids)]
    c.state["syllabus"] = ids
    c.save()
    syl = c.syllabus()
    pages = sum(u["end"] - u["start"] + 1 for u in syl)
    chapters = []
    for u in syl:
        if (u["chapter"] or u["id"]) not in chapters:
            chapters.append(u["chapter"] or u["id"])
    print(f"🗒 syllabus set: {len(syl)} sections in {len(chapters)} chapters (about {pages} pages) — {rel(c.dir)}")
    print("CHAPTERS: " + ", ".join(chapters))
    nxt = c.next_unit()
    if nxt:
        print(f"FIRST UNIT TO STUDY: {nxt['id']} {nxt['title']}")


def cmd_toc(a):
    c = find_course(a.course)
    chosen = {u["id"] for u in c.syllabus()}
    print(f"{c.state.get('title') or c.slug} — " + progress_line(c))
    print("marks: ✓ done · ⚠ shaky · – skipped · · to do · (blank) not in the syllabus; * optional in the book")
    for ch in c.chapters(appendices=True):
        if a.chapter and ch["id"] != a.chapter:
            continue
        us = c.units_of(ch)
        if not a.all and not a.chapter and not any(u["id"] in chosen for u in us):
            continue
        print(f"{ch['id']} {ch['title']}{' *' if ch['starred'] else ''}  (PDF {ch['start']}-{ch['end']})")
        for u in us:
            if u is ch:
                continue
            if u["id"] not in chosen and not (a.all or a.chapter):
                continue
            mark = MARK[c.status(u["id"])] if u["id"] in chosen else " "
            print(f"  {mark} {u['id']} {u['title']}{' *' if u['starred'] else ''}  ({c.cite(u['start'], u['end'])})")
        for e in c.exercise_sections(ch["id"]):
            if a.all or a.chapter:
                print(f"    {e['id']} {e['title']}  ({c.cite(e['start'], e['end'])})")


def cmd_next(a):
    c = find_course(a.course)
    if not c.state.get("syllabus"):
        die("no syllabus selected yet — book.py select all | unstarred | <chapters, sections, ranges>")
    u = c.next_unit()
    if not u:
        shaky = [x["id"] for x in c.syllabus() if c.status(x["id"]) == "shaky"]
        print("COURSE COMPLETE: every unit of the syllabus is done." + (f" Shaky, worth revisiting: {', '.join(shaky)}" if shaky else ""))
        return
    print(describe_unit(c, u, "NEXT"))
    shaky = [x["id"] for x in c.syllabus() if c.status(x["id"]) == "shaky"]
    if shaky:
        print(f"SHAKY UNITS: {', '.join(shaky)}")


def unit_for(c, id_):
    e = c.by_id.get(id_)
    if e is None:
        die(f"unknown section: {id_}   (see: book.py toc --all)")
    units = c.units(appendices=True)
    if e in units:
        return e
    if e["kind"] in ("chapter", "appendix"):
        return c.units_of(e)[0]
    parent = next((u for u in units if e["id"].startswith(u["id"] + ".")), None)
    if parent:
        return parent
    die(f"{id_} is not a unit of study (part, exercises or front matter)")


def cmd_section(a):
    c = find_course(a.course)
    print(describe_unit(c, unit_for(c, a.id)))


def cmd_done(a):
    c = find_course(a.course)
    u = unit_for(c, a.id)
    if a.status == "todo":
        c.state["status"].pop(u["id"], None)
    else:
        c.state["status"][u["id"]] = {"s": a.status, "at": time.strftime("%Y-%m-%d")}
    if u["id"] not in (c.state.get("syllabus") or []):  # studied out of the syllabus: it is part of the course now
        c.state["syllabus"] = [x["id"] for x in c.units(appendices=True) if x["id"] in set(c.state.get("syllabus") or []) | {u["id"]}]
    c.save()
    print(f"🗒 {u['id']} {u['title']}: {a.status} — " + progress_line(c))
    nxt = c.next_unit()
    if not nxt:
        print("COURSE COMPLETE: no unit left to do.")
    elif (nxt["chapter"] or nxt["id"]) != (u["chapter"] or u["id"]):
        print(f"CHAPTER {u['chapter'] or u['id']} COMPLETE. The next unit, {nxt['id']} {nxt['title']}, opens chapter "
              f"{nxt['chapter'] or nxt['id']} and has its own note: save a checkpoint; `/course next` starts it.")
    else:
        print(describe_unit(c, nxt, "NEXT"))


def cmd_find(a):
    c = find_course(a.course)
    if a.kind == "page":
        page = c.pdf_page(a.id)
        if not page:
            die(f"printed page {a.id} not found (page labels unknown? set the offset: book.py set offset N)")
        print(f"printed page {a.id} is PDF page {page}")
        return
    page, how = locate(c, a.kind, a.id)
    if not page:
        die(f"{a.kind} {a.id} not found in the book's anchors or text; look it up from: book.py toc {a.id.split('.')[0]}", 1)
    sec = [e for e in c.entries if e["level"] >= 2 and e["start"] <= page <= e["end"]]
    where = f" — in §{sec[-1]['id']} {sec[-1]['title']}" if sec else ""
    print(f"{a.kind} {a.id}: PDF page {page} ({c.cite(page, page)}; found by {how}){where}")
    print(f"READ: {c.book['pdf']}  pages: {page}")


def exercise_record(c, id_):
    return c.state.setdefault("exercises", {}).setdefault(id_, {"status": "open", "hints": 0, "assessed": False})


def cmd_exercise(a):
    c = find_course(a.course)
    ch_id = a.id.split(".")[0]
    listing = chapter_exercises(c, ch_id) if ch_id in c.by_id else []
    pages = dict(listing)
    page, how = (pages[a.id], "anchor") if a.id in pages else locate(c, "ex", a.id)
    changed = a.hint is not None or a.status is not None
    known = a.id in (c.state.get("exercises") or {})
    if not page and not known:
        die(f"exercise {a.id} not found; see: book.py exercises {ch_id}", 1)
    rec = exercise_record(c, a.id)
    if a.hint is not None:
        rec["hints"] = max(rec.get("hints", 0), a.hint)
        if rec["status"] == "open":
            rec["status"] = "attempted"
    if a.status:
        rec["status"] = a.status
    if changed:
        rec["updated"] = time.strftime("%Y-%m-%d")
        c.save()
        print(f"🗒 exercise {a.id}: {rec['status']}, hints used up to level {rec.get('hints', 0)}")
        return
    if not known:
        del c.state["exercises"][a.id]  # looking is not attempting
    print(f"EXERCISE {a.id}" + (f" — chapter {ch_id} \"{c.by_id[ch_id]['title']}\"" if ch_id in c.by_id else ""))
    if page:
        ids = [i for i, _ in listing]
        end = page
        if a.id in ids and ids.index(a.id) + 1 < len(ids):
            end = max(page, listing[ids.index(a.id) + 1][1])
        elif ch_id in c.by_id:
            end = min(page + 1, c.by_id[ch_id]["end"])
        print(f"READ: {c.book['pdf']}")
        print(f"  pages: {c.pages(page, end)[0]}   ({c.cite(page, end)}; found by {how}; the exercise starts on PDF page {page})")
    else:
        print("READ: location unknown — find it from: book.py toc " + ch_id)
    print(f"RECORD: status {rec['status']} · hints used up to level {rec.get('hints', 0)}"
          + (" · ASSESSED coursework: hints only, no full solution, never a quiz" if rec.get("assessed") else ""))
    print(f"FULL SOLUTIONS POLICY: {c.state.get('solutions', 'after-attempt')}")
    if ch_id in c.by_id:
        lesson = c.note(ch_id)
        print(f"EXERCISES NOTE: {rel(c.note(ch_id, exercises=True))}")
        print(f"LESSON NOTE: {rel(lesson)}" + ("" if os.path.exists(lesson) else "  (not written yet)"))
        done = [u["id"] for u in c.units_of(c.by_id[ch_id]) if c.status(u["id"]) in ("done", "shaky")]
        print(f"CHAPTER {ch_id} UNITS STUDIED: {', '.join(done) or 'none yet'}")


def cmd_exercises(a):
    c = find_course(a.course)
    chapters = [a.chapter] if a.chapter else [ch["id"] for ch in c.chapters(appendices=True) if c.exercise_sections(ch["id"])]
    recs = c.state.get("exercises") or {}
    for ch_id in chapters:
        if ch_id not in c.by_id:
            die(f"unknown chapter: {ch_id}")
        listing = chapter_exercises(c, ch_id)
        secs = c.exercise_sections(ch_id)
        where = "; ".join(f"PDF pages {c.pages(e['start'], e['end'])[0]}" for e in secs) or "no exercises section in the outline"
        print(f"CHAPTER {ch_id} {c.by_id[ch_id]['title']} — {len(listing)} exercises ({where})")
        if a.chapter:
            for eid, page in listing:
                r = recs.get(eid) or {}
                extra = " · ".join(x for x in (r.get("status", ""), f"hints {r['hints']}" if r.get("hints") else "",
                                               "ASSESSED" if r.get("assessed") else "") if x)
                print(f"  {eid}  PDF page {page}" + (f"  [{extra}]" if extra else ""))


def cmd_assess(a):
    c = find_course(a.course)
    for eid in a.ids:
        exercise_record(c, eid)["assessed"] = not a.clear
    c.save()
    marked = sorted(k for k, r in c.state["exercises"].items() if r.get("assessed"))
    print(f"🗒 assessed exercises (hints only, never solved or quizzed): {', '.join(marked) or 'none'}")


def cmd_set(a):
    c = find_course(a.course)
    value = " ".join(a.value).strip()
    if a.key == "solutions":
        if value not in SOLUTIONS:
            die(f"solutions must be one of: {', '.join(SOLUTIONS)}")
        c.state["solutions"] = value
    elif a.key == "offset":
        if not re.fullmatch(r"-?\d+", value):
            die("offset must be a whole number: (PDF page number of the page printed '1') - 1")
        c.book["offset"], c.book["labels"] = int(value), None
        save_json(os.path.join(c.dir, ".course", "book.json"), c.book)
    else:
        c.state[a.key] = value
    c.save()
    print(f"🗒 {a.key} set: {value}")


def cmd_status(a):
    c = find_course(a.course)
    print(f"COURSE: {c.state.get('title') or c.slug}  ({rel(c.dir)})")
    print(f"BOOK: {c.book['pdf']}" + ("" if os.path.exists(c.book["pdf"]) else "   (FILE MISSING)"))
    if c.state.get("goal"):
        print(f"GOAL: {c.state['goal']}")
    print("PROGRESS: " + progress_line(c))
    shaky = [u["id"] for u in c.syllabus() if c.status(u["id"]) == "shaky"]
    if shaky:
        print(f"SHAKY: {', '.join(shaky)}")
    nxt = c.next_unit()
    if nxt:
        print(f"NEXT: {nxt['id']} {nxt['title']}  ({c.cite(nxt['start'], nxt['end'])})")
    ex = c.state.get("exercises") or {}
    if ex:
        n = {s: sum(1 for r in ex.values() if r.get("status") == s) for s in EXERCISE_STATUS}
        print("EXERCISES: " + ", ".join(f"{v} {k}" for k, v in n.items() if v)
              + f"; {sum(1 for r in ex.values() if r.get('assessed'))} assessed")
    print(f"FULL SOLUTIONS POLICY: {c.state.get('solutions', 'after-attempt')}")


def main():
    p = argparse.ArgumentParser(prog="book.py", description="Page map and progress for a course that follows a textbook.")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--course", help="course directory (default: the course used last)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("new")
    s.add_argument("pdf")
    s.add_argument("--name")
    s.add_argument("--title")
    s.add_argument("--dir")
    s.add_argument("--toc")
    s.add_argument("--offset", type=int)
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_new)

    s = sub.add_parser("select", parents=[common])
    s.add_argument("spec", nargs="+")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--add", action="store_true")
    g.add_argument("--remove", action="store_true")
    s.set_defaults(fn=cmd_select)

    s = sub.add_parser("toc", parents=[common])
    s.add_argument("chapter", nargs="?")
    s.add_argument("--all", action="store_true")
    s.set_defaults(fn=cmd_toc)

    sub.add_parser("next", parents=[common]).set_defaults(fn=cmd_next)

    s = sub.add_parser("section", parents=[common])
    s.add_argument("id")
    s.set_defaults(fn=cmd_section)

    s = sub.add_parser("done", parents=[common])
    s.add_argument("id")
    s.add_argument("--status", choices=UNIT_STATUS, default="done")
    s.set_defaults(fn=cmd_done)

    s = sub.add_parser("find", parents=[common])
    s.add_argument("kind", choices=sorted(ANCHORS) + ["page"])
    s.add_argument("id")
    s.set_defaults(fn=cmd_find)

    s = sub.add_parser("exercise", parents=[common])
    s.add_argument("id")
    s.add_argument("--hint", type=int, choices=range(1, 6))
    s.add_argument("--status", choices=EXERCISE_STATUS)
    s.set_defaults(fn=cmd_exercise)

    s = sub.add_parser("exercises", parents=[common])
    s.add_argument("chapter", nargs="?")
    s.set_defaults(fn=cmd_exercises)

    s = sub.add_parser("assess", parents=[common])
    s.add_argument("ids", nargs="+")
    s.add_argument("--clear", action="store_true")
    s.set_defaults(fn=cmd_assess)

    s = sub.add_parser("set", parents=[common])
    s.add_argument("key", choices=("title", "goal", "solutions", "offset"))
    s.add_argument("value", nargs="+")
    s.set_defaults(fn=cmd_set)

    sub.add_parser("status", parents=[common]).set_defaults(fn=cmd_status)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
