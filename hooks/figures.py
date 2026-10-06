#!/usr/bin/env python3
"""
figures — bring the book's figures into a course note.

When a block written to a course note names one of the book's figures ("Figure 1.4", "Figure 1.4a",
"Fig. 2.7"), the figure is cropped from the book (book.py figure) and embedded once in the note, as
`![[pml1-fig-1-4.png|600]] ^fig-1-4`, and every mention becomes a link to that block. The embed goes below
the paragraph or callout of the first mention, or above it when that is a quiz question, so the figure is in
view before the question is answered.

Used by md_log.py (prose, replayed quiz blocks) and mcp/quiz_server.py (quiz blocks written live).
Only notes inside a course directory (one with .course/book.json) are touched.

    figures.py <note.md>    apply to a note written before figures were embedded (keeps <note>.md.bak)
"""
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOOK = os.path.join(HERE, "book.py")
VAULT_DIR = os.path.dirname(os.path.dirname(HERE))  # book.py writes viz/ under its working directory
MENTION_RE = re.compile(r"\b(?:Figure|Fig\.)\s+(\d+(?:\.\d+)+)[a-z]?\b")
PROTECTED_RE = re.compile(r"\[\[.*?\]\]|`[^`\n]*`|\$[^$\n]*\$")


def course_of(note):
    """The course directory a note belongs to, or None."""
    if not note:
        return None
    d = os.path.dirname(os.path.abspath(note))
    return d if os.path.exists(os.path.join(d, ".course", "book.json")) else None


def crop(course, fig_id):
    """Absolute path of the cropped figure (cropped now, or earlier), or None."""
    try:
        out = subprocess.run([sys.executable, BOOK, "figure", fig_id, "--course", course], cwd=VAULT_DIR,
                             capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return None
    rel = next((ln[len("FILE: "):].strip() for ln in out.splitlines() if ln.startswith("FILE: ")), None)
    path = os.path.join(VAULT_DIR, rel) if rel else None
    return path if path and os.path.isfile(path) else None


def block_id(fig_id):
    return "fig-" + fig_id.replace(".", "-")


def mentions(text):
    """Figure ids named in text, in order of first mention (links and code excluded)."""
    ids = []
    for gap in PROTECTED_RE.split(text):
        for m in MENTION_RE.finditer(gap):
            if m.group(1) not in ids:
                ids.append(m.group(1))
    return ids


def _link_line(line, linked):
    def sub(m):
        return f"[[#^{block_id(m.group(1))}|{m.group(0)}]]" if m.group(1) in linked else m.group(0)
    out, pos = [], 0
    for p in PROTECTED_RE.finditer(line):
        out.append(MENTION_RE.sub(sub, line[pos:p.start()]))
        out.append(p.group(0))
        pos = p.end()
    out.append(MENTION_RE.sub(sub, line[pos:]))
    return "".join(out)


def _skip_lines(lines):
    """Indices of lines that are left alone: headings, embeds, fenced code and display math."""
    skip, fence = set(), None
    for i, ln in enumerate(lines):
        s = ln.lstrip("> ").strip()
        if fence:
            skip.add(i)
            if s.startswith(fence):
                fence = None
            continue
        if s.startswith("```") or s == "$$":
            fence = "```" if s.startswith("```") else "$$"
            skip.add(i)
        elif s.startswith("#") or "![[" in s:
            skip.add(i)
    return skip


def _span(lines, i):
    """(first, last) line of the paragraph or callout that line i belongs to."""
    if lines[i].startswith(">"):
        a = b = i
        while a > 0 and lines[a - 1].startswith(">"):
            a -= 1
        while b + 1 < len(lines) and lines[b + 1].startswith(">"):
            b += 1
        return a, b
    a = b = i
    while a > 0 and lines[a - 1].strip() and not lines[a - 1].startswith(">"):
        a -= 1
    while b + 1 < len(lines) and lines[b + 1].strip() and not lines[b + 1].startswith(">"):
        b += 1
    return a, b


def process(text, note, existing=None):
    """`text` (a block about to be written to `note`, or a whole note) with the figures it names embedded
    once and every mention linked. `existing`: the note's current content (read from `note` when None)."""
    course = course_of(note)
    if not course or not MENTION_RE.search(text):
        return text
    if existing is None:
        try:
            with open(note, encoding="utf-8") as f:
                existing = f.read()
        except Exception:
            existing = ""
    lines = text.split("\n")
    skip = _skip_lines(lines)
    first = {}
    for i, ln in enumerate(lines):
        if i not in skip:
            for fid in mentions(ln):
                first.setdefault(fid, i)
    linked, inserts = set(), []
    for fid, i in first.items():
        if f"^{block_id(fid)}" in existing or f"^{block_id(fid)}" in text:
            linked.add(fid)
            continue
        path = crop(course, fid)
        if not path:
            continue
        linked.add(fid)
        a, b = _span(lines, i)
        before = lines[a].strip().startswith("> [!question]")
        inserts.append((a if before else b + 1, before, f"![[{os.path.basename(path)}|600]] ^{block_id(fid)}"))
    for i in range(len(lines)):
        if i not in skip:
            lines[i] = _link_line(lines[i], linked)
    for at, before, embed in sorted(inserts, key=lambda x: x[0], reverse=True):
        new = [embed]
        if at > 0 and lines[at - 1].strip():
            new.insert(0, "")
        if at < len(lines) and lines[at].strip():
            new.append("")
        lines[at:at] = new
    return "\n".join(lines)


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[-1].strip(), file=sys.stderr)
        return 2
    note = os.path.abspath(argv[1])
    if not course_of(note):
        print(f"{note} is not in a course directory", file=sys.stderr)
        return 1
    with open(note, encoding="utf-8") as f:
        text = f.read()
    new = process(text, note, existing="")
    if new == text:
        print("no figures named, nothing changed")
        return 0
    shutil.copyfile(note, note + ".bak")
    with open(note, "w", encoding="utf-8") as f:
        f.write(new)
    embeds = re.findall(r"\^(fig-[\d-]+)$", new, re.M)
    print(f"embedded {len(embeds)} figure(s): {', '.join(embeds) or '-'}; backup at {os.path.basename(note)}.bak")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
