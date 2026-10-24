#!/usr/bin/env python3
"""
technique — technique notes: one note per problem-solving trick, with every problem that used it.

A lesson section is tagged by a line closing it, `*Techniques: [[Symmetry]] · [[Pigeonhole principle]]*`; an
interview problem by the `techniques` list of its problem file. This script resolves the tags against the notes in
`<vault>/techniques/` (their names and `aliases`), and writes only the block between the problems markers of each
note, and the index `techniques/Techniques.md`. Everything else in a technique note belongs to the teacher and the
learner.

    technique.py list                         every technique: name, aliases, problems, record; then unknown tags
    technique.py sync                         rewrite every note's problems block and the index (changed files only)
    technique.py cue "<Name>" "<text>" --source "<note stem>#<heading>"
                                              add the learner's cue under "In your words"
    technique.py sections <note>              each ### section of a note with its key idea and its tags
    technique.py tag <note> "<heading>" <Name>...
                                              write a tag line at the end of that section, then sync
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
import quiz_block

CLAUDE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAULT = os.path.dirname(CLAUDE_DIR)
TECH_DIR = os.path.join(VAULT, "techniques")
INDEX = os.path.join(TECH_DIR, "Techniques.md")
START = "%% problems: written by technique.py sync; edits inside are replaced %%"
END = "%% /problems %%"
TAG_RE = re.compile(r"^\*Techniques: (.+)\*$")
LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
SESSION_RE = re.compile(r"^## Session — (\d{4}-\d{2}-\d{2})")
NUM_RE = re.compile(r"([A-Z]?\d+(?:\.\d+)*)\s")
SKIP_DIRS = {"exams", "interviews"}
PASS, MISS = {"✓", "solved"}, {"✗", "?", "hinted", "unsolved"}


# ---------------------------------------------------------------- the technique notes

def _aliases(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return []
    fm = m.group(1)
    inline = re.search(r"^aliases:\s*\[(.*?)\]\s*$", fm, re.M)
    if inline:
        return [a.strip().strip("'\"") for a in inline.group(1).split(",") if a.strip()]
    block = re.search(r"^aliases:\s*\n((?:\s+-\s.*\n?)+)", fm, re.M)
    return [ln.strip()[1:].strip().strip("'\"") for ln in block.group(1).splitlines()] if block else []


def load_techniques():
    """{canonical name: {"path", "aliases"}} for every note in techniques/ but the index."""
    out = {}
    for p in sorted(glob.glob(os.path.join(glob.escape(TECH_DIR), "*.md"))):
        if os.path.abspath(p) == os.path.abspath(INDEX):
            continue
        with open(p, encoding="utf-8") as f:
            out[os.path.splitext(os.path.basename(p))[0]] = {"path": p, "aliases": _aliases(f.read())}
    return out


def resolver(techs):
    """{lower-cased name or alias: canonical name}."""
    res = {}
    for name, t in techs.items():
        for key in [name] + t["aliases"]:
            res.setdefault(key.lower(), name)
    return res


def target(link):
    return link.split("|", 1)[0].split("#", 1)[0].strip()


# ---------------------------------------------------------------- reading the tags

def anchor_of(heading_line):
    """'### 2.4.1 Coin piles' -> '2.4.1 Coin piles', the form a heading link takes (as lesson.heading_links)."""
    return re.sub(r"\s+", " ", re.sub(r"[#|^:\[\]]", " ", heading_line.lstrip("#"))).strip()


def short_label(anchor):
    m = NUM_RE.match(anchor + " ")
    return f"§{m.group(1)}" if m else anchor


def long_label(anchor):
    return f"§{anchor}" if NUM_RE.match(anchor + " ") else anchor


def scanned_notes():
    for root, dirs, files in os.walk(VAULT):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS
                         and not (root == VAULT and d == "techniques"))
        for f in sorted(files):
            if f.endswith(".md") and not f.endswith("-review.md") and not f.endswith(" — Review.md"):
                yield os.path.join(root, f)


def note_sections(lines):
    """[(heading line index, anchor, [section lines], session date)] for each ### section."""
    out, cur, date = [], None, None
    for i, ln in enumerate(lines):
        m = SESSION_RE.match(ln)
        if m:
            date = m.group(1)
        if ln.startswith("### "):
            cur = [i, anchor_of(ln), [], date]
            out.append(cur)
        elif cur is not None:
            cur[2].append(ln)
            cur[3] = date
    return [tuple(c) for c in out]


def section_tags(body):
    targets = []
    for ln in body:
        m = TAG_RE.match(ln.strip())
        if m:
            targets += [target(link) for link in LINK_RE.findall(m.group(1)) if target(link)]
    return list(dict.fromkeys(targets))


def scan_tags():
    out = []
    for path in scanned_notes():
        try:
            lines = lesson.read(path)
        except (OSError, UnicodeDecodeError):
            continue
        stem = os.path.splitext(os.path.basename(path))[0]
        course = lesson.course_slug(path) or "lesson"
        for _, anchor, body, date in note_sections(lines):
            targets = section_tags(body)
            if not targets:
                continue
            marks = []
            for ln in body:
                if quiz_block.is_quiz_header(ln):
                    o = quiz_block.parse([ln])["outcome"]
                    if o in ("✓", "✗", "?"):
                        marks.append(o)
            out.append({"note": path, "stem": stem, "heading": anchor, "anchor": anchor, "label": long_label(anchor),
                        "course": course, "targets": targets, "marks": marks, "date": date})
    return out


def interview_problems():
    out = []
    pattern = os.path.join(glob.escape(VAULT), "courses", "*", ".interviews", "*-interview-*.state.json")
    for sp in sorted(glob.glob(pattern)):
        m = re.search(r"([^/]+)-interview-(\d+)\.state\.json$", sp)
        st = book.load_json(sp, None)
        if not m or not isinstance(st, dict) or st.get("status") != "finished":
            continue
        data = book.load_json(sp[:-len(".state.json")] + ".json", None) or {}
        specs = data.get("problems") or []
        for i, (pr, spec) in enumerate(zip(st.get("problems") or [], specs), 1):
            if pr.get("outcome") in (None, "not reached"):
                continue
            out.append({"stem": f"{m.group(1)}-interview-{m.group(2)}", "slug": m.group(1), "number": int(m.group(2)),
                        "i": i, "techniques": list(spec.get("techniques") or []), "outcome": pr["outcome"],
                        "date": st.get("set")})
    out.sort(key=lambda p: (p["slug"], p["number"], p["i"]))
    return out


# ---------------------------------------------------------------- building the notes

def collect():
    """(techniques, {name: [entry]}, {unknown name: [(stem, anchor)]}, number of tagged problems)."""
    techs = load_techniques()
    res = resolver(techs)
    entries = {name: [] for name in techs}
    unknown = {}
    sections = scan_tags()
    problems = [p for p in interview_problems() if p["techniques"]]
    for s in sections:
        for t in s["targets"]:
            name = res.get(t.lower())
            if name is None:
                unknown.setdefault(t, []).append((s["stem"], s["anchor"]))
            elif s not in entries[name]:
                entries[name].append(s)
    for p in problems:
        for t in dict.fromkeys(p["techniques"]):
            name = res.get(t.lower())
            if name is None:
                unknown.setdefault(t, []).append((p["stem"], f"Problem {p['i']}"))
            elif p not in entries[name]:
                entries[name].append(p)
    return techs, entries, unknown, len(sections) + len(problems)


def record(entries):
    marks = [m for e in entries for m in (e["marks"] if "marks" in e else [e["outcome"]])]
    return sum(m in PASS for m in marks), sum(m in MISS for m in marks)


def entry_line(e):
    if "marks" in e:
        return f"- [[{e['stem']}#{e['anchor']}|{e['label']}]] ({e['course']}) {''.join(e['marks'])}".rstrip()
    return f"- [[{e['stem']}#Problem {e['i']}|{e['slug']} interview {e['number']}, problem {e['i']}]] — {e['outcome']}"


def render_block(entries):
    p, m = record(entries)
    k = len(entries)
    lines = [START, f"**Record:** {p} ✓ · {m} ✗ — {k} problem{'' if k == 1 else 's'}"]
    if entries:
        lines += [""] + [entry_line(e) for e in entries]
    return "\n".join(lines + [END])


def with_block(text, block):
    if START in text and END in text:
        a, b = text.index(START), text.index(END) + len(END)
        return text[:a] + block + text[b:]
    m = re.search(r"^## Problems[ \t]*\n", text, re.M)
    if m:
        return text[:m.end()] + "\n" + block + "\n" + text[m.end():]
    return text.rstrip("\n") + "\n\n## Problems\n\n" + block + "\n"


def render_index(techs, entries, unknown):
    def key(name):
        p, m = record(entries[name])
        return (p + m == 0, p / (p + m) if p + m else 0, -m, name.lower())
    rows = ["# Techniques", "", "| Technique | Problems | ✓ | ✗ | Last seen |", "|---|---|---|---|---|"]
    for name in sorted(techs, key=key):
        p, m = record(entries[name])
        dates = [e["date"] for e in entries[name] if e.get("date")]
        rows.append(f"| [[{name}]] | {len(entries[name])} | {p} | {m} | {max(dates) if dates else '—'} |")
    text = "\n".join(rows) + "\n"
    if unknown:
        parts = [f"[[{name}]] in " + ", ".join(f"[[{stem}#{anchor}|{short_label(anchor)}]]" for stem, anchor in where)
                 for name, where in unknown.items()]
        text += "\n**Unknown techniques:** " + "; ".join(parts) + "\n"
    return text


def write_if_changed(path, text):
    old = None
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            old = f.read()
    if old == text:
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    return True


def sync():
    techs, entries, unknown, tagged = collect()
    for name, t in techs.items():
        with open(t["path"], encoding="utf-8") as f:
            text = f.read()
        write_if_changed(t["path"], with_block(text, render_block(entries[name])))
    write_if_changed(INDEX, render_index(techs, entries, unknown))
    return f"🗒 techniques: {len(techs)} notes, {tagged} tagged problems, {len(unknown)} unknown"


# ---------------------------------------------------------------- commands

def cmd_sync(a):
    print(sync())


def cmd_list(a):
    sync()
    techs, entries, unknown, _ = collect()
    for name, t in techs.items():
        p, m = record(entries[name])
        al = f" (aliases: {', '.join(t['aliases'])})" if t["aliases"] else ""
        print(f"{name}{al} — {len(entries[name])} problems, {p} ✓ {m} ✗")
    for name in unknown:
        print(f"UNKNOWN: {name}")


def resolve_or_die(name, res):
    canon = res.get(name.lower())
    if canon is None:
        book.die(f"no technique note for {name!r} in techniques/: write the note first", 1)
    return canon


def write_lines(path, lines):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip("\n") + "\n")


def cmd_cue(a):
    techs = load_techniques()
    t = techs[resolve_or_die(a.name, resolver(techs))]
    lines = lesson.read(t["path"])
    head = a.source.split("#", 1)[-1]
    item = f'- "{a.text.strip()}" — [[{a.source}|{short_label(anchor_of(head))}]], {time.strftime("%Y-%m-%d")}'
    if "**In your words:**" in lines:
        k = lines.index("**In your words:**") + 1
        while k < len(lines) and lines[k].startswith("- "):
            k += 1
        lines[k:k] = [item]
    else:
        reach = next((i for i, ln in enumerate(lines) if ln.strip() == "## Reach for it when"), None)
        if reach is None:
            lines += ["", "**In your words:**", item]
        else:
            last, k = reach, reach + 1  # after the last item of the cues list
            while k < len(lines) and (not lines[k].strip() or lines[k].startswith("- ")):
                if lines[k].startswith("- "):
                    last = k
                k += 1
            lines[last + 1:last + 1] = ["", "**In your words:**", item]
    write_lines(t["path"], lines)
    print(f"🗒 cue added to [[{os.path.splitext(os.path.basename(t['path']))[0]}]]")
    sync()


def key_ideas(body):
    out, cur = [], None
    for ln in body:
        if re.match(r"^> \[!summary\][-+]? Key idea", ln):
            cur = []
            out.append(cur)
        elif cur is not None and ln.startswith(">"):
            cur.append(ln.lstrip(">").strip())
        else:
            cur = None
    return [" ".join(x for x in parts if x) for parts in out if any(parts)]


def cmd_sections(a):
    lines = lesson.read(os.path.abspath(a.note))
    for i, _, body, _ in note_sections(lines):
        print(lines[i])
        for idea in key_ideas(body):
            print(f"  key idea: {idea}")
        tags = section_tags(body)
        if tags:
            print(f"  tags: {', '.join(tags)}")


def cmd_tag(a):
    path = os.path.abspath(a.note)
    lines = lesson.read(path)
    want = anchor_of("### " + a.heading)
    start = next((i for i, ln in enumerate(lines) if ln.startswith("### ") and anchor_of(ln) == want), None)
    if start is None:
        book.die(f"no section {a.heading!r} in {book.rel(path)}", 1)
    res = resolver(load_techniques())
    names = [res.get(n.lower(), n) for n in a.names]
    nxt = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("### ")), len(lines))
    existing = next((i for i in range(start + 1, nxt) if TAG_RE.match(lines[i].strip())), None)
    if existing is not None:
        links = LINK_RE.findall(TAG_RE.match(lines[existing].strip()).group(1))
        have = {res.get(target(l).lower(), target(l)).lower() for l in links}
        links += [n for n in names if n.lower() not in have]
        lines[existing] = "*Techniques: " + " · ".join(f"[[{l}]]" for l in dict.fromkeys(links)) + "*"
    else:
        end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith(("## ", "### "))), len(lines))
        k = end
        while k > start + 1 and not lines[k - 1].strip():
            k -= 1
        tag = "*Techniques: " + " · ".join(f"[[{n}]]" for n in dict.fromkeys(names)) + "*"
        lines = lines[:k] + ["", tag] + ([""] + lines[end:] if end < len(lines) else [])
    write_lines(path, lines)
    print(sync())


def main(argv=None):
    p = argparse.ArgumentParser(prog="technique.py", description="Technique notes.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("sync")
    s = sub.add_parser("cue")
    s.add_argument("name")
    s.add_argument("text")
    s.add_argument("--source", required=True)
    s = sub.add_parser("sections")
    s.add_argument("note")
    s = sub.add_parser("tag")
    s.add_argument("note")
    s.add_argument("heading")
    s.add_argument("names", nargs="+")
    a = p.parse_args(argv)
    {"list": cmd_list, "sync": cmd_sync, "cue": cmd_cue, "sections": cmd_sections, "tag": cmd_tag}[a.cmd](a)


if __name__ == "__main__":
    main()
