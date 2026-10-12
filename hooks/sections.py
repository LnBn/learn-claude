#!/usr/bin/env python3
"""
sections — link the section references in a note ("§1.1", "(§1.2.2", "§A.3") to the heading of that section.

A section taught in this note becomes `[[#1.1 What is machine learning?|§1.1]]`; in a course, a section taught in
another chapter's note becomes `[[pml1-ch01#1.1 What is machine learning?|§1.1]]`. A section without a heading of
its own links to the nearest heading that contains it (§1.2.1.5 -> ### 1.2.1), or else to the first heading inside
it (§1.2 -> ### 1.2.1, when the unit was taught in parts). A section with no heading yet stays plain text. So do
headings, code, math, existing links and the source line under a heading ("*Book: §2.3, pp. 44–49.*"), which
cites the book.

Used by md_log.py and mcp/quiz_server.py, after figures.py, on every block written to a note.

    sections.py <note.md>    link the references in a note written earlier (keeps <note>.md.bak)
"""
import json
import os
import re
import shutil
import sys

import figures

REF_RE = re.compile(r"(?<![\w|])§([A-Z]?\d+(?:\.\d+)*)(?!\w)")
HEADING_RE = re.compile(r"^### +([A-Z]?\d+(?:\.\d+)*)\s")


def _anchor(line):
    """'### 1.2.1 Classification: the setup' -> '1.2.1 Classification the setup', the form a heading link takes."""
    return re.sub(r"\s+", " ", re.sub(r"[#|^:\[\]]", " ", line.lstrip("#"))).strip()


def headings(text):
    """[(number, anchor)] of the numbered ### headings in text, in order."""
    out = []
    for ln in text.split("\n"):
        m = HEADING_RE.match(ln)
        if m:
            out.append((m.group(1), _anchor(ln)))
    return out


def _chapter_notes(course, note):
    """The other lesson notes of the course: <slug>-*.md, without the exercise and review notes."""
    try:
        with open(os.path.join(course, ".course", "state.json"), encoding="utf-8") as f:
            slug = json.load(f).get("slug")
        names = sorted(os.listdir(course))
    except Exception:
        return []
    here = os.path.abspath(note)
    return [os.path.join(course, n) for n in names
            if slug and n.startswith(slug + "-") and n.endswith(".md")
            and not n.endswith(("-exercises.md", "-review.md")) and os.path.join(course, n) != here]


def targets(note, text, existing):
    """[(number, link target)] for every section with a heading: this note's first, then the course's other
    notes. A target is '#anchor' in this note, 'stem#anchor' in another."""
    out = [(num, "#" + a) for num, a in headings(existing + "\n" + text)]
    course = figures.course_of(note)
    for path in _chapter_notes(course, note) if course else []:
        try:
            with open(path, encoding="utf-8") as f:
                other = f.read()
        except Exception:
            continue
        stem = os.path.splitext(os.path.basename(path))[0]
        out += [(num, f"{stem}#{a}") for num, a in headings(other)]
    return out


def resolve(ref, found):
    """The link target for section `ref`: its own heading, else the nearest containing one, else the first inside it."""
    by_num = {}
    for num, target in found:
        by_num.setdefault(num, target)
    parts = ref.split(".")
    for i in range(len(parts), 0, -1):
        if ".".join(parts[:i]) in by_num:
            return by_num[".".join(parts[:i])]
    return next((target for num, target in found if num.startswith(ref + ".")), None)


def _link_line(line, found):
    sep = "\\|" if line.lstrip("> ").startswith("|") else "|"  # inside a table row the pipe is escaped

    def sub(m):
        target = resolve(m.group(1), found)
        return f"[[{target}{sep}{m.group(0)}]]" if target else m.group(0)
    out, pos = [], 0
    for p in figures.PROTECTED_RE.finditer(line):
        out.append(REF_RE.sub(sub, line[pos:p.start()]))
        out.append(p.group(0))
        pos = p.end()
    out.append(REF_RE.sub(sub, line[pos:]))
    return "".join(out)


def process(text, note, existing=None):
    """`text` (a block about to be written to `note`, or a whole note) with its section references linked.
    `existing`: the note's current content (read from `note` when None)."""
    if not note or "§" not in text:
        return text
    if existing is None:
        try:
            with open(note, encoding="utf-8") as f:
                existing = f.read()
        except Exception:
            existing = ""
    found = targets(note, text, existing)
    if not found:
        return text
    lines = text.split("\n")
    skip = figures._skip_lines(lines)
    for i, ln in enumerate(lines):
        if i not in skip and "§" in ln and not ln.lstrip("> ").startswith("*Book:"):
            lines[i] = _link_line(ln, found)
    return "\n".join(lines)


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[-1].strip(), file=sys.stderr)
        return 2
    note = os.path.abspath(argv[1])
    with open(note, encoding="utf-8") as f:
        text = f.read()
    new = process(text, note, existing="")
    if new == text:
        print("no section references to link, nothing changed")
        return 0
    shutil.copyfile(note, note + ".bak")
    with open(note, "w", encoding="utf-8") as f:
        f.write(new)
    n = len(re.findall(r"\\?\|§[^\]]*\]\]", new)) - len(re.findall(r"\\?\|§[^\]]*\]\]", text))
    print(f"linked {n} section reference(s); backup at {os.path.basename(note)}.bak")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
