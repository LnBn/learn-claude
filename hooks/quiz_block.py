#!/usr/bin/env python3
"""The graded-quiz block of a lesson note: one callout per quiz, folded, titled by its outcome and its question.

    > [!failure|quiz]- ✗ <the question's first line, cut at 100 characters>
    >
    > <the full question, when the title is not all of it>
    >
    > 1. <option>
    > 2. <option>
    >
    > Selected: 2. <option>
    > Correct answer: 1. <option>
    >
    > <explanation>

`|quiz` is callout metadata: Obsidian hides it, and code and CSS find quiz blocks by it. mcp/quiz_server.py and
md_log.py write the block (render); md_log.py, lesson.py and figures.py read it back (parse).

Notes written before this block existed hold a "> [!question] Quiz" callout and a result callout per quiz:

    quiz_block.py convert [--write] [--force] <note>...

prints the diff that folds them; --write applies it, after copying each note to md-log-state/quiz-fold-backup/.
"""
import difflib
import os
import re
import shutil
import sys
import time

import figures

CLAUDE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP_DIR = os.path.join(CLAUDE_DIR, "md-log-state", "quiz-fold-backup")

TITLE_LIMIT = 100
HEADER_RE = re.compile(r"^>\s?\[!(\w+)\|quiz\][-+]?[ \t]*(.*)$")
PROTECTED_RE = re.compile(r"\$\$.*?\$\$|\$[^$]*\$|`[^`]*`|\[\[.*?\]\]")
# (kind, title prefix, outcome) — the outcome strings are the ones lesson.py reports
OUTCOMES = [
    ("success", "✓ ", "✓"),
    ("failure", "✗ ", "✗"),
    ("info", "? ", "?"),
    ("warning", "⊘ Skipped: ", "skip"),
    ("warning", "⊘ Unavailable: ", "unavailable"),
    ("note", "Asked first: ", "asked"),
    ("question", "", "(unanswered)"),
]


def cut_title(line, limit=TITLE_LIMIT):
    """`line` cut at the last space at or before `limit`, with "…", never inside math, code or a link."""
    line = line.strip()
    if len(line) <= limit:
        return line
    spans = [m.span() for m in PROTECTED_RE.finditer(line)]
    for i in range(limit, 0, -1):
        if line[i] == " " and not any(a <= i < b for a, b in spans):
            return line[:i].rstrip() + "…"
    end = next((b for a, b in spans if a <= limit < b), limit)  # no space left: cut after the span that crosses
    return line[:end] + "…"


def block(kind, title, parts):
    """A folded quiz callout; `parts` are paragraphs (each may hold several lines), separated by blank lines."""
    lines = [f"> [!{kind}|quiz]- {title}"]
    for part in parts:
        lines.append(">")
        lines += [f"> {ln}" if ln else ">" for ln in part.split("\n")]
    return "\n".join(lines)


def _outcome(r):
    """(kind, title prefix, outcome paragraphs) for a quiz record."""
    status = r.get("status")
    if status == "cancelled":
        return "warning", "⊘ Skipped: ", ["(skipped)"]
    if status == "unavailable":
        return "warning", "⊘ Unavailable: ", [r.get("message", "")]
    if status == "asked":
        return "note", "Asked first: ", [f"Your question: {r.get('learnerQuestion', '')}"]
    by_index = {o["index"]: o["label"] for o in r["options"]}
    correct = ", ".join(f"{i}. {by_index[i]}" for i in r["correctIndices"])
    if r.get("dontKnow"):
        return "info", "? ", [f"Correct answer: {correct}"]
    selected = ", ".join(f"{i}. {by_index[i]}" for i in r.get("answers", []))
    if r.get("correct"):
        return "success", "✓ ", [f"Selected: {selected}"]
    return "failure", "✗ ", [f"Selected: {selected}\nCorrect answer: {correct}"]


def render(r):
    """The block for a quiz record of mcp/quiz_server.py (the QUIZ_JSON line of its result)."""
    question = r["question"].strip()
    details = (r.get("details") or "").strip()
    title = cut_title(question.split("\n")[0])
    kind, prefix, outcome = _outcome(r)
    parts = [question] if title != question else []
    parts.append(details)
    if r.get("figure") and not figures.mentions(question + " " + details):
        parts.append(f"![[{os.path.basename(r['figure'])}|500]]")  # a book figure the text names is placed by figures.py
    parts.append("\n".join(f"{o['index']}. {o['label']}" for o in r["options"]))
    if r.get("multiSelect"):
        parts.append("(select all that apply)")
    parts += outcome
    if r.get("status") != "asked":
        parts.append((r.get("explanation") or "").strip())
    if r.get("note"):
        parts.append(f"Note: {r['note']}")
    return block(kind, prefix + title, [p for p in parts if p])


def is_quiz_header(line):
    return bool(HEADER_RE.match(line.rstrip()))


def parse(lines):
    """{"kind", "outcome", "title", "text"} for a quiz callout's lines, or None for any other callout.
    `text` is the question followed by the rest of the block, for matching a block to the question asked."""
    m = HEADER_RE.match(lines[0].rstrip()) if lines else None
    if not m:
        return None
    kind, title = m.group(1), m.group(2).strip()
    outcome = "(unanswered)"
    for k, prefix, out in OUTCOMES:
        if kind == k and title.startswith(prefix):
            outcome, title = out, title[len(prefix):]
            break
    body = "\n".join(ln[2:] if ln.startswith("> ") else ln[1:] for ln in lines[1:]).strip("\n")
    core = title[:-1] if title.endswith("…") else title
    text = body if body.startswith(core) else title + "\n" + body
    return {"kind": kind, "outcome": outcome, "title": title, "text": text}


# ---- converting notes written before the folded block

OLD_QUESTION = "> [!question] Quiz"
OLD_ASKED = "> [!note] Asked before answering"
OLD_RESULTS = {  # result callout -> (kind, title prefix) of the folded block
    "> [!success] ✓ Correct": ("success", "✓ "),
    "> [!failure] ✗ Incorrect": ("failure", "✗ "),
    "> [!info] I don't know": ("info", "? "),
    "> [!warning] Quiz — cancelled": ("warning", "⊘ Skipped: "),
    "> [!warning] Quiz — unavailable": ("warning", "⊘ Unavailable: "),
}
FALLBACK_ANSWER = "> [!example] Answer"  # the fallback quiz protocol's answer: ungraded, left as it is
PI_TITLES = ("Quiz — correct ✓", "Quiz — incorrect ✗", "[!question] Quiz — I don't know")


def _callouts(lines):
    """(start, end) line ranges, end exclusive, of every '>'-prefixed block."""
    out, i = [], 0
    while i < len(lines):
        if lines[i].startswith(">"):
            j = i
            while j < len(lines) and lines[j].startswith(">"):
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def _body(lines):
    body = [ln[2:] if ln.startswith("> ") else ln[1:] for ln in lines]
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    return body


def convert_text(text, force=False):
    """`text` with each old question callout and its result folded into one quiz block.
    Raises ValueError for a pi-era note, or for a note that already has folded blocks unless `force`."""
    if any(t in text for t in PI_TITLES):
        raise ValueError("pi-era note: its questions and results are not in pairs")
    lines = text.split("\n")
    spans = _callouts(lines)
    head = [lines[a].strip() for a, _ in spans]
    olds = [k for k, h in enumerate(head)
            if h == OLD_QUESTION and not (k + 1 < len(spans) and head[k + 1] == FALLBACK_ANSWER)]
    if olds and not force and any(is_quiz_header(lines[a]) for a, _ in spans):
        raise ValueError("the note has folded quiz blocks and old ones; --force converts the old ones")
    new = {}  # span index -> replacement text, "" to remove the callout
    for k in olds:
        a, b = spans[k]
        question = _body(lines[a + 1:b])
        title = cut_title(question[0]) if question else ""
        para = question.index("") if "" in question else len(question)
        if "\n".join(question[:para]).strip() == title:
            question = question[para + 1:]  # the title is the whole question
        asked = result = None
        for j in range(k + 1, len(spans)):
            if head[j] == OLD_QUESTION:
                break
            if head[j] == OLD_ASKED and asked is None:
                asked = j
            elif head[j] in OLD_RESULTS:
                result = j
                break
        q = "\n".join(question)
        if asked is not None:
            note = "\n".join(_body(lines[spans[asked][0] + 1:spans[asked][1]]))
            new[k] = block("note", "Asked first: " + title, [q, "Your question: " + note])
            new[asked] = ""
        if result is not None:
            kind, prefix = OLD_RESULTS[head[result]]
            r = "\n".join(_body(lines[spans[result][0] + 1:spans[result][1]]))
            folded = block(kind, prefix + title, [p for p in (q, r) if p])
            if asked is None:
                new[k], new[result] = folded, ""
            else:
                new[result] = folded
        elif asked is None:
            new[k] = block("question", title, [q])
    out, i, starts = [], 0, {spans[k][0]: k for k in new}
    while i < len(lines):
        k = starts.get(i)
        if k is None:
            out.append(lines[i])
            i += 1
            continue
        if new[k]:
            out.append(new[k])
        elif spans[k][1] < len(lines) and not lines[spans[k][1]].strip():
            while out and not out[-1].strip():
                out.pop()  # a removed callout takes the blank lines before it; those after it stay
        i = spans[k][1]
    return "\n".join(out)


def convert(paths, write=False, force=False):
    refused = False
    for path in paths:
        with open(path, encoding="utf-8") as f:
            old = f.read()
        try:
            text = convert_text(old, force=force)
        except ValueError as e:
            print(f"REFUSED {path}: {e}")
            refused = True
            continue
        if text == old:
            print(f"unchanged {path}")
        elif not write:
            sys.stdout.writelines(difflib.unified_diff(old.splitlines(True), text.splitlines(True), path, path))
        else:
            os.makedirs(BACKUP_DIR, exist_ok=True)
            stem = os.path.splitext(os.path.basename(path))[0]
            shutil.copy2(path, os.path.join(BACKUP_DIR, f"{stem}-{time.strftime('%Y%m%d-%H%M%S')}.md"))
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"converted {path}: {sum(1 for ln in text.split(chr(10)) if is_quiz_header(ln))} quiz blocks")
    return 1 if refused else 0


def main(argv):
    args = argv[1:]
    flags = {a for a in args[1:] if a.startswith("--")}
    paths = [a for a in args[1:] if not a.startswith("--")]
    if not args or args[0] != "convert" or flags - {"--write", "--force"} or not paths:
        print("usage: quiz_block.py convert [--write] [--force] <note>...", file=sys.stderr)
        return 2
    return convert(paths, write="--write" in flags, force="--force" in flags)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
