#!/usr/bin/env python3
"""
quiz — a GRADED question tool for Claude Code, as an MCP server (stdio, no deps).

Port of the pi `quiz` extension. The model supplies the question, the options,
the correct answer (by option value) and an explanation; the server shows the
question to the learner through MCP elicitation (a form in the Claude Code UI),
grades the pick the instant it is made, and returns tight feedback
(correct/incorrect, the correct answer, the explanation) to both the learner
(via the md-log file, if linked) and the model (tool result). No model round
trip is needed for the grade.

Options (single- or multi-select) or a typed answer, a number or formula marked
by answer_check.py. An "I don't know" choice is always added so the learner can
signal a genuine gap instead of guessing. An optional free-text note travels
with any answer.

Logging: if the calling session mirrors a note, one folded quiz block (hooks/quiz_block.py)
is appended once the learner answers, skips, or asks the teacher first. Which note that is comes from
`.claude/md-log-state/quiz-target.json`, written per call by the md-log
PreToolUse hook (the server itself does not know its session); without an
entry it falls back to `.claude/md-log.json`. The tool-use id is recorded in
`.claude/md-log-state/quiz-logged.json` so the md-log Stop hook does not log it
a second time when replaying the transcript.
"""
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
POPUP = os.path.join(HERE, "quiz_popup.py")
CLAUDE_DIR = os.path.dirname(HERE)
VAULT_DIR = os.path.dirname(CLAUDE_DIR)  # relative figure paths resolve here
sys.path.insert(0, os.path.join(CLAUDE_DIR, "hooks"))
sys.path.insert(0, HERE)
import answer_check  # noqa: E402  (typed answers: read, show, compare)
import latex_text  # noqa: E402  (a typed answer's LaTeX shown in the popup)
import figures  # noqa: E402  (book figures named in a course quiz: cropped, embedded once, linked)
import quiz_block  # noqa: E402  (the folded quiz callout written to the note)
import sections  # noqa: E402  ("§1.2" in a quiz: a link to that section's heading)
MDLOG_CONFIG = os.path.join(CLAUDE_DIR, "md-log.json")
STATE_DIR = os.path.join(CLAUDE_DIR, "md-log-state")
QUIZ_LOGGED = os.path.join(STATE_DIR, "quiz-logged.json")
QUIZ_TARGET = os.path.join(STATE_DIR, "quiz-target.json")  # tool-use id -> note, from hooks/md_log.py
LAST_ASKED = os.path.join(STATE_DIR, "quiz-last-asked.json")  # set when the learner asks before answering
SERVER_LOG = os.path.join(STATE_DIR, "quiz-server.log")
DONT_KNOW = "I don't know"
EXAMPLE_RE = re.compile(r"\bExample (\d+)\b(?!\.\d)")  # the note's own examples; "Example 2.3" is the book's

TOOL = {
    "name": "quiz",
    "description": (
        "Ask the user a GRADED question with a known correct answer, then instantly grade and give feedback. "
        "Unlike AskUserQuestion (which collects preferences/decisions with no right answer), quiz always has a "
        "correct answer supplied by you, marks the user's selection right/wrong (✓/✗), reveals the correct answer, "
        "and shows an explanation. Use it to (1) assess what the learner already understands before teaching, and "
        "(2) run tight practice/retrieval loops after explaining, or probe understanding whenever you're unsure "
        "they've got it. Two modes. OPTIONS: single-select or multi-select, plus an automatic 'I don't know' choice so "
        "the user can signal a genuine gap instead of guessing — never add your own opt-out option. An optional "
        "note field lets the user attach free text to ANY answer; it reaches you only when non-empty. "
        "correctAnswer is REQUIRED and is the option `value`, not a position. explanation is REQUIRED. "
        "Options are shuffled before display by default. Make every distractor a specific, believable mistake "
        "(so WHICH wrong answer they pick is diagnostic), keep options even in length/specificity/format so the "
        "right one can't be picked from shape alone, and put zero justification inside any option. "
        "TYPED: pass `answer` (and no options) when the result is a number or a formula; the user types it and it "
        "is marked by evaluation, so equivalent forms count and a decimal counts if it matches to 3 significant "
        "figures (set exact to refuse decimals). Syntax: + - * / ^, implicit multiplication (2n, 2(n+1)), n!, "
        "sqrt ln log log2 log10 exp abs binom(n,k), pi e inf. Declare every variable with a range in `variables`; "
        "give `wrongAnswers` (the results of the common wrong moves, each with `why`) and `answerLatex`. Example: "
        "{\"question\": \"Expected tosses to get $n$ heads in a row?\", \"answer\": \"2^(n+1)-2\", "
        "\"answerLatex\": \"2^{n+1}-2\", \"variables\": {\"n\": \"int 1..12\"}, \"wrongAnswers\": "
        "[{\"answer\": \"2^n\", \"why\": \"...\"}], \"explanation\": \"...\"}. "
        "For non-graded questions use AskUserQuestion instead."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "The single quiz question to ask. Exactly one question per call."},
            "details": {"type": "string", "description": "Optional extra context or instructions shown under the question."},
            "options": {
                "type": "array",
                "minItems": 2,
                "description": "The answer options (2 or more), for the options mode; leave out for a typed answer. Give each a stable `value`; you reference the correct one(s) by that value in correctAnswer.",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string", "description": "Display label for the answer option."},
                        "value": {"type": "string", "description": "Optional machine-readable value returned for the option. Defaults to the label."},
                        "description": {"type": "string", "description": "Optional extra detail shown after the option."},
                    },
                    "required": ["label"],
                },
            },
            "multiSelect": {"type": "boolean", "description": "Set true when more than one option is correct and the user must select all of them (graded as an exact-set match)."},
            "correctAnswer": {
                "description": "REQUIRED. The correct answer as the option value(s). Single-select: one string (e.g. \"mercury\"). Multi-select: an array of strings (e.g. [\"belize\",\"niue\"]). Always the value, never a position number.",
                "anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}],
            },
            "explanation": {"type": "string", "description": "REQUIRED. Explanation revealed AFTER the user answers (right or wrong). Say why the correct answer is correct."},
            "figure": {"type": "string", "description": "Optional path of an image the question refers to (e.g. the FILE that `book.py figure` printed, relative to the vault). It is embedded in the note above the options, and the learner can open it from the quiz with `f`."},
            "answer": {"type": "string", "description": "Typed mode: the correct answer as an expression, e.g. \"2^(n+1)-2\" or \"1/3\". Give this instead of options and correctAnswer."},
            "variables": {"type": "object", "additionalProperties": {"type": "string"}, "description": "Typed mode: every variable in the answer with its range, e.g. {\"n\": \"int 1..12\", \"p\": \"0..1\"}."},
            "exact": {"type": "boolean", "description": "Typed mode: refuse decimals; only when the exact form is what is being tested."},
            "wrongAnswers": {"type": "array", "items": {"type": "object", "properties": {"answer": {"type": "string"}, "why": {"type": "string"}}, "required": ["answer", "why"]}, "description": "Typed mode: the results of the common wrong moves, each with what that answer means went wrong; shown to the learner when they type one."},
            "answerLatex": {"type": "string", "description": "Typed mode: the correct answer as LaTeX (no $), for the note and the feedback."},
            "shuffle": {"type": "boolean", "description": "Defaults to true: options are reordered before display. Set false only when order is meaningful (ordered numeric values, or an 'All/None of the above' option that must stay last)."},
        },
        "required": ["question", "explanation"],
    },
}


# ----------------------------------------------------------------- transport

def send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def read_message():
    line = sys.stdin.readline()
    if not line:
        return None
    line = line.strip()
    if not line:
        return {}
    try:
        return json.loads(line)
    except Exception:
        return {}


_next_id = 1000


def request(method, params):
    """Send a server->client request and block until its response arrives,
    servicing any client requests/notifications that come in meanwhile."""
    global _next_id
    _next_id += 1
    rid = _next_id
    send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
    while True:
        m = read_message()
        if m is None:
            sys.exit(0)
        if not m:
            continue
        if m.get("id") == rid and ("result" in m or "error" in m):
            return m
        if "method" in m:
            if m.get("method") == "notifications/cancelled":
                return {"error": {"message": "cancelled"}}
            handle_incoming(m)  # ping etc.


# ----------------------------------------------------------------- md-log

def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


_NO_TARGET = object()
_target = _NO_TARGET  # the note of the quiz being run: a path, None (mirror nowhere), or unknown


def set_target(tool_use_id):
    global _target
    targets = load_json(QUIZ_TARGET, {})
    _target = targets[tool_use_id] if isinstance(targets, dict) and tool_use_id in targets else _NO_TARGET


def log_file():
    if _target is not _NO_TARGET:
        return _target
    return load_json(MDLOG_CONFIG, {}).get("file")


def append_log(text):
    """Append a block to the note; returns the text written (after figures and section links), or None."""
    path = log_file()
    if not path or not text.strip():
        return None
    try:
        current = ""
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                current = f.read()
        text = sections.process(figures.process(text, path, existing=current), path, existing=current)
        prefix = ("\n" if current.endswith("\n") else "\n\n") if current.strip() else ""
        with open(path, "a", encoding="utf-8") as f:
            f.write(prefix + text.strip("\n") + "\n")
        return text.strip("\n")
    except Exception:
        return None


def replace_log(old, text):
    """Put `text` where `old` (a quiz block this server wrote) is in the note; append it if `old` is gone."""
    path = log_file()
    try:
        with open(path, encoding="utf-8") as f:
            current = f.read()
    except Exception:
        current = ""
    at = current.rfind(old) if old else -1
    if at < 0:
        return append_log(text)
    try:
        text = sections.process(figures.process(text, path, existing=current), path, existing=current).strip("\n")
        with open(path, "w", encoding="utf-8") as f:
            f.write(current[:at] + text + current[at + len(old):])
        return text
    except Exception:
        return None


def quiz_part(written):
    """The quiz block in what append_log wrote: figures.py may have put a figure embed above it."""
    lines = (written or "").split("\n")
    start = next((i for i, ln in enumerate(lines) if quiz_block.is_quiz_header(ln)), None)
    return "\n".join(lines[start:]) if start is not None else None


def diag(msg):
    """Append a line to .claude/md-log-state/quiz-server.log (why a fallback happened, etc.)."""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(SERVER_LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg.rstrip() + "\n")
    except Exception:
        pass


def save_last_asked(displayed, typed=None):
    """Remember the quiz the learner asked about: its option set, or for a typed quiz its question."""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(LAST_ASKED, "w", encoding="utf-8") as f:
            json.dump({"typed": typed} if typed else
                      {"labels": sorted(o["label"].strip().lower() for o in displayed),
                       "order": [o["label"].strip().lower() for o in displayed]}, f)
    except Exception:
        pass


def clear_last_asked():
    try:
        os.remove(LAST_ASKED)
    except Exception:
        pass


def mark_logged(tool_use_id):
    if not tool_use_id or not log_file():
        return  # nothing was written to a note: a later backfill must still log this quiz from the transcript
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        ids = load_json(QUIZ_LOGGED, [])
        if tool_use_id in ids:
            return
        ids = (ids + [tool_use_id])[-500:]
        with open(QUIZ_LOGGED, "w", encoding="utf-8") as f:
            json.dump(ids, f)
    except Exception:
        pass


# ----------------------------------------------------------------- quiz logic

def normalize_options(raw):
    out = []
    for o in raw or []:
        if not isinstance(o, dict):
            continue
        label = str(o.get("label", "")).strip()
        if not label:
            continue
        value = str(o.get("value") or label).strip()
        desc = str(o.get("description") or "").strip()
        out.append({"label": label, "value": value, "description": desc})
    return out


def coerce_correct(ca):
    if isinstance(ca, list):
        return [str(v) for v in ca]
    s = str(ca).strip()
    if s.startswith("[") and s.endswith("]"):
        try:
            v = json.loads(s)
            if isinstance(v, list):
                return [str(x) for x in v]
        except Exception:
            pass
    return [s]


def course_figure(text):
    """The book figure a quiz in a course note names ("Figure 1.4a"), cropped by book.py, or None."""
    ids = figures.mentions(text)
    course = figures.course_of(log_file())
    return figures.crop(course, ids[0]) if ids and course else None


def example_sources(note):
    """The notes whose examples a quiz written to `note` may cite: the note itself, plus the lesson a review or
    exercise note belongs to (in a course, every note of the course for its review note)."""
    d, name = os.path.split(note)
    if name.endswith(" — Review.md"):
        return [note, os.path.join(d, name[:-len(" — Review.md")] + ".md")]
    if name.endswith("-exercises.md"):
        return [note, os.path.join(d, name[:-len("-exercises.md")] + ".md")]
    if name.endswith("-review.md") and figures.course_of(note):
        return [os.path.join(d, n) for n in sorted(os.listdir(d)) if n.endswith(".md")]
    return [note]


def missing_examples(text, note):
    """Numbers of the examples `text` names ("Example 20") that are not in the note yet."""
    nums = list(dict.fromkeys(EXAMPLE_RE.findall(text)))
    if not nums or not note or not os.path.exists(note):
        return []
    have = []
    for path in example_sources(note):
        try:
            with open(path, encoding="utf-8") as f:
                have.append(f.read())
        except Exception:
            pass
    have = "\n".join(have)
    return [n for n in nums if not re.search(rf"\^ex-{n}\b|\[!example\][+-]? Example {n}\b", have)]


def check_common(args):
    """(question, details, explanation, figure) of a call, or an error result."""
    question = str(args.get("question", "")).strip()
    details = str(args.get("details") or "").strip()
    explanation = str(args.get("explanation") or "").strip()
    figure = str(args.get("figure") or "").strip()
    if not question:
        return err("question is required")
    if not explanation:
        return err("explanation is required")
    if figure:
        figure = os.path.join(VAULT_DIR, os.path.expanduser(figure))
        if not os.path.isfile(figure):
            return err(f"figure {args.get('figure')!r} not found (paths are relative to {VAULT_DIR})")
    return question, details, explanation, figure


def check_examples(seen):
    missing = missing_examples(seen, log_file())
    if missing:
        names = ", ".join(f"Example {n}" for n in missing)
        return err(f"{names} {'is' if len(missing) == 1 else 'are'} not in the note, so the learner cannot read it. Write it in a reply of its own, "
                   "end that reply with the ready line, and ask this question after they say ready.")
    return None


def ask_learner(record, displayed, tool_use_id, details, multi):
    """Write the open block, show the quiz, and return (ui result, pending block text, whether the popup showed the grade)."""
    # the question goes in the note now, open, so a long quiz can be read there while answering;
    # the outcome replaces this block in place
    pending = quiz_part(append_log(quiz_block.render({**record, "status": "pending"})))
    mark_logged(tool_use_id)  # now, not after the answer: this quiz's block is the server's to write
    clear_last_asked()
    # tmux popup when available (full question + options, like pi), otherwise Claude Code's
    # elicitation form (which truncates the message to one line)
    ui = ask_via_tmux(record) if tmux_available() else None
    seen_feedback = ui is not None  # the tmux popup shows the grade itself
    if ui is None:
        ui = ask_via_elicitation(record, displayed, msg_details=details, multi=multi)
    return ui, pending, seen_feedback


def not_answered(ui, record, pending, tool_use_id, displayed):
    """The result for an ask-first or a cancel, or None when the learner answered."""
    if ui.get("action") == "ask":
        q = str(ui.get("question") or "").strip()
        record["status"] = "asked"
        record["learnerQuestion"] = q
        replace_log(pending, quiz_block.render(record))
        mark_logged(tool_use_id)
        save_last_asked(displayed, typed=record["question"] if record.get("mode") == "typed" else None)
        what = "answer" if record.get("mode") == "typed" else "options, correctAnswer"
        return result(
            "The learner asked a question BEFORE answering (no answer was given, nothing was graded):\n"
            f"  {q}\n"
            f"Answer it now, without giving away the quiz answer. Then call quiz again with the same question, "
            f"{what} and explanation so they can answer.", record)
    if ui.get("action") != "accept":
        record["status"] = "cancelled"
        replace_log(pending, quiz_block.render(record))
        mark_logged(tool_use_id)
        return result("User skipped the quiz (cancelled). Ask whether to continue or move on.", record)
    return None


def feedback_tail(note, seen_feedback):
    text = ""
    if note:
        text += f"\nNote from user: {note}\nIf this note asks a question, answer it before moving on."
    if seen_feedback:
        text += "\nThe user has already seen this feedback in the popup — do not repeat the grade; continue from it."
    else:
        text += "\nThe user has NOT seen this feedback yet — relay the grade, the correct answer and the explanation in one short block before continuing."
        text += ("\nThe quiz was shown in Claude Code's one-line form, not the popup, so a long question was cut off "
                 "(the full quiz is in the note). If you have not said so this session, tell the learner in one line "
                 "to start Claude Code inside tmux to get the popup.")
    return text


def run_quiz(args, tool_use_id, progress_token=None):
    set_target(tool_use_id)
    if "answer" in args:
        return run_typed(args, tool_use_id)
    options = normalize_options(args.get("options"))
    multi = bool(args.get("multiSelect"))
    shuffle = args.get("shuffle", True) is not False

    if not str(args.get("question", "")).strip():
        return err("question is required")
    if len(options) < 2:
        return err("quiz needs at least two options")
    if any(o["label"].lower() in {DONT_KNOW.lower(), "i dont know", "not sure", "i'm not sure", "unsure"} for o in options):
        return err("do not add your own 'I don't know' / 'not sure' option — it is added automatically")
    if not str(args.get("explanation") or "").strip():
        return err("explanation is required")
    if "correctAnswer" not in args:
        return err("correctAnswer is required")
    wanted = coerce_correct(args["correctAnswer"])
    by_value = {o["value"]: o for o in options}
    bad = [v for v in wanted if v not in by_value]
    if bad:
        known = ", ".join(f'"{o["value"]}"' for o in options)
        return err(f"correctAnswer {bad[0]!r} does not match any option value ({known})")
    if len(wanted) > 1 and not multi:
        return err("several correct answers given but multiSelect is not true")
    common = check_common(args)
    if isinstance(common, dict):
        return common
    question, details, explanation, figure = common
    problem = check_examples(" ".join([question, details, explanation] + [o["label"] for o in options]))
    if problem:
        return problem

    # A re-ask after "ask the teacher first": same option set as the pending question -> keep the
    # displayed order the learner already saw.
    prev = load_json(LAST_ASKED, {})
    key_now = sorted(o["label"].strip().lower() for o in options)
    reask = bool(prev) and prev.get("labels") == key_now
    displayed = list(options)
    if reask:
        order = prev.get("order") or []
        displayed.sort(key=lambda o: order.index(o["label"].strip().lower()) if o["label"].strip().lower() in order else 99)
    elif shuffle:
        random.shuffle(displayed)
    for i, o in enumerate(displayed, 1):
        o["index"] = i
    correct_indices = sorted(o["index"] for o in displayed if o["value"] in wanted)
    record = {
        "status": "answered", "question": question, "details": details, "multiSelect": multi,
        "options": [{"index": o["index"], "label": o["label"]} for o in displayed],
        "correctIndices": correct_indices, "explanation": explanation, "reask": reask,
    }
    add_figure(record, figure, " ".join([question, details] + [o["label"] for o in options]))

    ui, pending, seen_feedback = ask_learner(record, displayed, tool_use_id, details, multi)
    early = not_answered(ui, record, pending, tool_use_id, displayed)
    if early:
        return early

    picked = [i for i in ui.get("answers", []) if i in {o["index"] for o in displayed}]
    dont_know = bool(ui.get("dontKnow")) and not picked
    note = str(ui.get("note") or "").strip()
    correct = (not dont_know) and sorted(picked) == correct_indices
    record.update({"answers": picked, "correct": correct, "dontKnow": dont_know, "note": note})

    replace_log(pending, quiz_block.render(record))
    mark_logged(tool_use_id)

    by_index = {o["index"]: o["label"] for o in displayed}
    correct_str = ", ".join(f"{i}. {by_index[i]}" for i in correct_indices)
    if dont_know:
        text = f"User answered \"I don't know\" — a genuine gap, not a wrong guess.\nCorrect: {correct_str}"
    else:
        sel = ", ".join(f"{i}. {by_index[i]}" for i in picked) or "(nothing)"
        text = f"User answered {'correctly' if correct else 'incorrectly'}.\nSelected: {sel}\nCorrect: {correct_str}"
    text += f"\nExplanation: {explanation}"
    return result(text + feedback_tail(note, seen_feedback), record)


def add_figure(record, figure, text):
    if figure:
        record["figure"] = figure
    else:
        auto = course_figure(text)
        if auto:
            record["figure"] = auto


def check_typed(args):
    """The typed-answer fields of a call, checked: (answer, variables, wrong answers), or an error result."""
    if "options" in args:
        return err("give either answer or options, not both")
    if any(k in args for k in ("multiSelect", "correctAnswer", "shuffle")):
        return err("multiSelect, correctAnswer and shuffle belong to the options mode")
    answer = str(args.get("answer") or "").strip()
    variables = args.get("variables") or {}
    if not isinstance(variables, dict):
        return err('variables must be an object from name to range, e.g. {"n": "int 1..12"}')
    variables = {str(k): str(v) for k, v in variables.items()}
    try:
        answer_check.parse_ranges(variables)
    except answer_check.AnswerError as exc:
        return err(str(exc))
    try:
        answer_check.read(answer, variables)
    except answer_check.AnswerError as exc:
        return err(f"answer: {exc}")
    if answer_check.defined_points(answer, variables) < min(3, len(answer_check.points(answer, variables))):
        return err("answer is undefined at most points of the ranges; narrow the variables' ranges")
    wrong = []
    for w in args.get("wrongAnswers") or []:
        a = str((w or {}).get("answer") or "").strip() if isinstance(w, dict) else ""
        try:
            same = answer_check.check(a, answer, variables) == "correct"
        except answer_check.AnswerError as exc:
            return err(f"wrong answer {a}: {exc}")
        if same:
            return err(f"wrong answer {a} is equivalent to answer")
        wrong.append({"answer": a, "why": str(w.get("why") or "").strip()})
    return answer, variables, wrong


def run_typed(args, tool_use_id):
    typed_args = check_typed(args)
    if isinstance(typed_args, dict):
        return typed_args
    answer, variables, wrong = typed_args
    common = check_common(args)
    if isinstance(common, dict):
        return common
    question, details, explanation, figure = common
    problem = check_examples(" ".join([question, details, explanation]))
    if problem:
        return problem
    exact = bool(args.get("exact"))
    latex = str(args.get("answerLatex") or "").strip()
    prev = load_json(LAST_ASKED, {})
    record = {
        "mode": "typed", "status": "answered", "question": question, "details": details,
        "answer": answer, "answerLatex": latex, "variables": variables, "exact": exact,
        "wrongAnswers": wrong, "explanation": explanation, "reask": prev.get("typed") == question,
    }
    add_figure(record, figure, " ".join([question, details]))

    ui, pending, seen_feedback = ask_learner(record, [], tool_use_id, details, False)
    early = not_answered(ui, record, pending, tool_use_id, [])
    if early:
        return early

    typed = str(ui.get("typed") or "").strip()
    dont_know = bool(ui.get("dontKnow"))
    note = str(ui.get("note") or "").strip()
    unreadable, correct, matched = "", False, None
    if not dont_know:
        try:
            correct = answer_check.check(typed, answer, variables, exact) == "correct"
        except answer_check.AnswerError as exc:
            unreadable = str(exc)
        if not correct and not unreadable:
            matched = answer_check.matches_wrong(typed, wrong, variables, exact)
    decimal = answer_check.is_decimal(typed)
    record.update({"typed": typed, "correct": correct, "dontKnow": dont_know, "decimal": decimal,
                   "matchedWrong": matched, "note": note})

    replace_log(pending, quiz_block.render(record))
    mark_logged(tool_use_id)

    if dont_know:
        text = f"User answered \"I don't know\" — a genuine gap, not a wrong guess.\nCorrect: {answer}"
    else:
        text = f"User answered {'correctly' if correct else 'incorrectly'}.\n"
        if unreadable:
            text += f"Typed: {typed} — could not be read: {unreadable}"
        else:
            text += f"Typed: {typed} (reads as {answer_check.display(typed, variables)})"
        if correct and decimal:
            text += "\n(decimal, matched to 3 significant figures)"
        text += f"\nCorrect: {answer}"
        if matched is not None:
            text += f"\nMatched common mistake: {wrong[matched]['why']}"
    text += f"\nExplanation: {explanation}"
    return result(text + feedback_tail(note, seen_feedback), record)


# ----------------------------------------------------------------- learner UI

def tmux_available():
    if not os.environ.get("TMUX"):
        diag("no tmux popup: $TMUX is not set — Claude Code was started outside tmux; using the elicitation form")
        return False
    if shutil.which("tmux") is None:
        diag("no tmux popup: tmux binary not on PATH; using the elicitation form")
        return False
    return True


def popup_spec(record):
    """What quiz_popup.py is given: everything it shows, and what it needs to grade the answer itself."""
    spec = {"question": record["question"], "details": record.get("details", ""), "dontKnow": DONT_KNOW,
            "explanation": record.get("explanation", ""), "figure": record.get("figure", "")}
    if record.get("mode") == "typed":
        latex = record.get("answerLatex") or ""
        shown = latex_text.render(f"${latex}$") if latex else answer_check.display(record["answer"], record["variables"])
        spec.update({"mode": "typed", "answer": record["answer"], "variables": record["variables"],
                     "exact": record.get("exact", False), "wrongAnswers": record.get("wrongAnswers", []),
                     "answerDisplay": shown})
    else:
        spec.update({"options": record["options"], "multiSelect": record.get("multiSelect", False),
                     "correctIndices": record["correctIndices"]})
    return spec


def ask_via_tmux(record):
    """Show the quiz in a tmux popup. Returns the popup's result dict, or None if
    the popup could not be shown (caller then falls back to elicitation)."""
    work = tempfile.mkdtemp(prefix="learn-quiz.")
    spec_path = os.path.join(work, "spec.json")
    out_path = os.path.join(work, "result.json")
    spec = popup_spec(record)
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False)
    # size the popup from the content, assuming ~70 usable columns; PgUp/PgDn cover the rest
    def rows(text):
        return sum(max(1, len(par) // 70 + 1) for par in str(text).split("\n")) if text else 0
    n_lines = 9 + rows(record["question"]) + rows(record.get("details")) \
        + sum(rows(o["label"]) for o in record.get("options", [])) + rows(record.get("explanation")) \
        + (4 if record.get("mode") == "typed" else 0) \
        + (2 if record.get("figure") else 0)
    height = str(min(max(n_lines, 14), 45))
    def popup(height):
        cmd = ["tmux", "display-popup", "-E", "-w", "85%", "-h", height, "-T", " quiz ",
               f"{shlex_quote(sys.executable)} {shlex_quote(POPUP)} {shlex_quote(spec_path)} {shlex_quote(out_path)}"]
        return subprocess.run(cmd, check=False, timeout=3600, stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        proc = popup(height)
        if proc.returncode != 0 and "too large" in (proc.stderr or "") and not os.path.exists(out_path):
            diag(f"popup of height {height} is taller than the terminal; trying 90%")
            proc = popup("90%")  # PgUp/PgDn scroll the rest
    except Exception as exc:
        diag(f"tmux display-popup failed to start: {exc}; using the elicitation form")
        shutil.rmtree(work, ignore_errors=True)
        return None
    try:
        with open(out_path, encoding="utf-8") as f:
            res = json.load(f)
    except Exception:
        diag(f"tmux display-popup produced no result (exit {proc.returncode}): {proc.stderr.strip()[:300]}; "
             "using the elicitation form")
        return None
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if res.get("error"):
        diag(f"popup UI error: {res['error']}; using the elicitation form")
        return None
    return res


def shlex_quote(s):
    return "'" + str(s).replace("'", "'\\''") + "'"


def ask_via_elicitation(record, displayed, msg_details, multi):
    """Fallback: MCP elicitation form. Claude Code shows the message on ONE line,
    so the question is pushed into the option titles as far as possible."""
    def choice(o):
        return f"{o['index']}. {o['label']}" + (f" — {o['description']}" if o.get("description") else "")

    labels = [choice(o) for o in displayed]
    msg = record["question"] + (f"\n\n{msg_details}" if msg_details else "")
    if record.get("mode") == "typed":
        schema = {"type": "object",
                  "properties": {"answer": {"type": "string", "title": "Your answer"},
                                 "dk": {"type": "boolean", "title": DONT_KNOW, "default": False},
                                 "note": {"type": "string", "title": "Note (optional)"}},
                  "required": []}
        resp = request("elicitation/create", {"message": msg, "requestedSchema": schema})
        if "error" in resp or (resp.get("result") or {}).get("action") != "accept":
            return {"action": "cancel"}
        content = resp["result"].get("content") or {}
        typed = str(content.get("answer") or "").strip()
        return {"action": "accept", "typed": typed, "dontKnow": content.get("dk") is True and not typed,
                "note": str(content.get("note") or "").strip()}
    if multi:
        props = {f"opt{o['index']}": {"type": "boolean", "title": choice(o), "default": False} for o in displayed}
        props["dk"] = {"type": "boolean", "title": DONT_KNOW, "default": False}
        props["note"] = {"type": "string", "title": "Note (optional)"}
        schema = {"type": "object", "properties": props, "required": []}
        msg += "\n\nSelect ALL that apply."
    else:
        schema = {"type": "object",
                  "properties": {"answer": {"type": "string", "title": "Your answer", "enum": labels + [DONT_KNOW]},
                                 "note": {"type": "string", "title": "Note (optional)"}},
                  "required": ["answer"]}
    resp = request("elicitation/create", {"message": msg, "requestedSchema": schema})
    if "error" in resp or (resp.get("result") or {}).get("action") != "accept":
        return {"action": "cancel"}
    content = (resp["result"].get("content") or {})
    note = str(content.get("note") or "").strip()
    if multi:
        picked = [o["index"] for o in displayed if content.get(f"opt{o['index']}") is True]
        return {"action": "accept", "answers": picked, "dontKnow": content.get("dk") is True and not picked, "note": note}
    ans = str(content.get("answer") or "").strip()
    if ans == DONT_KNOW:
        return {"action": "accept", "answers": [], "dontKnow": True, "note": note}
    picked = [o["index"] for o in displayed if choice(o) == ans or ans in (o["label"], str(o["index"]))]
    return {"action": "accept", "answers": picked[:1], "dontKnow": False, "note": note}


def err(message):
    return {"content": [{"type": "text", "text": f"quiz error: {message}"}], "isError": True}


def result(text, record):
    return {"content": [{"type": "text", "text": text + "\nQUIZ_JSON: " + json.dumps(record, ensure_ascii=False)}]}


# ----------------------------------------------------------------- dispatch

def handle_incoming(m):
    method = m.get("method")
    mid = m.get("id")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": (m.get("params") or {}).get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "quiz", "version": "0.1.0"},
        }})
    elif method == "ping":
        send({"jsonrpc": "2.0", "id": mid, "result": {}})
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": mid, "result": {"tools": [TOOL]}})
    elif method == "tools/call":
        params = m.get("params") or {}
        if params.get("name") != "quiz":
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": "unknown tool"}})
            return
        meta = params.get("_meta") or {}
        tool_use_id = meta.get("claudecode/toolUseId")
        try:
            res = run_quiz(params.get("arguments") or {}, tool_use_id, meta.get("progressToken"))
        except SystemExit:
            raise
        except Exception as exc:
            res = err(f"internal error: {exc}")
        send({"jsonrpc": "2.0", "id": mid, "result": res})
    elif mid is not None and method:
        send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}})
    # notifications: ignore


def main():
    while True:
        m = read_message()
        if m is None:
            return
        if m:
            handle_incoming(m)


if __name__ == "__main__":
    main()
