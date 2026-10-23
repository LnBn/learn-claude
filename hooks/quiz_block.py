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
"""
import os
import re

import figures

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
